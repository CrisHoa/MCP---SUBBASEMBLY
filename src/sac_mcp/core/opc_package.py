"""
OPC (Open Packaging Conventions) .pkt Zip Manager.
Hỗ trợ 100% cả 3 biến thể file .pkt:
  1. Native Autodesk Subassembly Composer (.atc, .cfg, .xaml, .pvd, .emd, .cdmd, [Content_Types].xml)
  2. Compiled .NET DLL Subassembly Package (như SACVisualInfra.pkt chứa .atc + .dll + Images + HTML)
  3. Legacy PacketSettings.xml / LogicalNameMapping.xml
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import uuid
import zipfile
from typing import Any, Dict, List, Optional
from lxml import etree

from sac_mcp.core.version_manager import VersionManager
from sac_mcp.models.schemas import CivilVersion, ParameterInfo


class PktValidationError(ValueError):
    """Thay đổi bị từ chối vì file .pkt sau khi sửa không qua được kiểm định Tầng 1/2."""

    def __init__(self, issues: list) -> None:
        self.issues = issues
        detail = "; ".join(i.message for i in issues[:5])
        super().__init__(
            f"Thay đổi bị huỷ, file gốc được giữ nguyên: kết quả không qua kiểm định ({len(issues)} lỗi). {detail}"
        )


class PktPackage:
    """Đại diện cho một gói file Subassembly (.pkt) trong bộ nhớ (RAM)."""

    def __init__(self, pkt_path: str | Path, files_map: Dict[str, bytes]) -> None:
        self.pkt_path = Path(pkt_path).resolve()
        self.files: Dict[str, bytes] = files_map
        self.warnings: List[str] = []
        self.last_backup_path: Optional[Path] = None

    @classmethod
    def open(cls, pkt_path: str | Path) -> "PktPackage":
        """Mở và đọc toàn bộ nội dung file .pkt vào bộ nhớ (RAM)."""
        path = Path(pkt_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file .pkt tại đường dẫn: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"File .pkt '{path.name}' đang rỗng (0 bytes).")

        files_map: Dict[str, bytes] = {}
        with zipfile.ZipFile(path, mode="r") as zf:
            for member in zf.namelist():
                files_map[member] = zf.read(member)

        return cls(path, files_map)

    @classmethod
    def create_from_template(
        cls,
        output_path: str | Path,
        subassembly_name: str,
        description: str = "",
        civil_version: str | CivilVersion = CivilVersion.C3D_2025,
        custom_template_path: Optional[str | Path] = None,
    ) -> "PktPackage":
        """
        Tạo một gói .pkt mới theo đúng chuẩn 7-file thực tế của Autodesk Subassembly Composer
        cho phiên bản Civil 3D mục tiêu (2025 / 2026 / 2027).
        """
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if custom_template_path:
            tpl_path = Path(custom_template_path).resolve()
            if tpl_path.exists():
                shutil.copy2(tpl_path, out_path)
                pkg = cls.open(out_path)
                pkg.update_metadata(
                    subassembly_name=subassembly_name,
                    description=description,
                    civil_version=civil_version,
                )
                pkg.save(backup=True)
                return pkg

        guid_hex = uuid.uuid4().hex
        files_map: Dict[str, bytes] = {
            "[Content_Types].xml": VersionManager.build_content_types_xml().encode("utf-8"),
            f"{guid_hex}.atc": VersionManager.build_atc_xml(
                guid_hex=guid_hex,
                subassembly_name=subassembly_name,
                description=description,
            ).encode("utf-8"),
            f"{guid_hex}.cfg": VersionManager.build_cfg_xml(version=civil_version).encode("utf-8"),
            f"{guid_hex}.xaml": VersionManager.build_base_flowchart_xaml(
                subassembly_name=subassembly_name,
                version=civil_version,
            ).encode("utf-8"),
            f"{guid_hex}.pvd": VersionManager.build_pvd_xml().encode("utf-8"),
            f"{guid_hex}.emd": VersionManager.build_emd_xml().encode("utf-8"),
            f"{guid_hex}.cdmd": VersionManager.build_cdmd_xml().encode("utf-8"),
        }
        pkg = cls(out_path, files_map)
        pkg.save(backup=True)
        return pkg

    def list_opc_files(self) -> List[str]:
        return list(self.files.keys())

    def find_atc_filename(self) -> Optional[str]:
        for fname in self.files:
            if fname.lower().endswith(".atc"):
                return fname
        return None

    def find_cfg_filename(self) -> Optional[str]:
        for fname in self.files:
            if fname.lower().endswith(".cfg"):
                return fname
        return None

    def find_xaml_filename(self) -> Optional[str]:
        """Tìm file .xaml chính trong gói .pkt (trả về None nếu là gói .dll thuần như SACVisualInfra.pkt)."""
        for fname in self.files:
            if fname.lower().endswith(".xaml"):
                return fname
        return None

    def is_dll_based_package(self) -> bool:
        """Kiểm tra xem gói .pkt có phải là dạng biên dịch .NET .dll (như SACVisualInfra.pkt) hay không."""
        return self.find_xaml_filename() is None and any(
            f.lower().endswith(".dll") for f in self.files
        )

    def get_xaml_text(self) -> str:
        xaml_name = self.find_xaml_filename()
        if not xaml_name:
            raise ValueError(
                f"Gói .pkt '{self.pkt_path.name}' là gói biên dịch .NET (.dll) không chứa file .xaml."
            )
        return self.files[xaml_name].decode("utf-8-sig")

    def set_xaml_text(self, xaml_content: str) -> None:
        xaml_name = self.find_xaml_filename()
        if not xaml_name:
            xaml_name = "Flowchart.xaml"
        # Thêm UTF-8 BOM chuẩn Autodesk Subassembly Composer để tránh lỗi '.pkt file is invalid'
        raw_bytes = xaml_content.encode("utf-8")
        if not raw_bytes.startswith(b"\xef\xbb\xbf"):
            raw_bytes = b"\xef\xbb\xbf" + raw_bytes
        self.files[xaml_name] = raw_bytes

    def extract_atc_parameters(self) -> List[ParameterInfo]:
        """Trích xuất danh sách Parameters từ file .atc (dùng cho cả gói XAML và gói DLL)."""
        atc_name = self.find_atc_filename()
        if not atc_name:
            return []
        params: List[ParameterInfo] = []
        try:
            root = etree.fromstring(self.files[atc_name])
            for p_el in root.xpath("//*[local-name()='Params']/*"):
                pname = etree.QName(p_el).localname
                dt = p_el.get("DataType", "Double")
                disp = p_el.get("DisplayName", pname)
                desc = p_el.get("Description", "")
                def_val = (p_el.text or "").strip()
                params.append(
                    ParameterInfo(
                        name=pname,
                        category="Input",
                        data_type=dt,
                        default_value=def_val,
                        display_name=disp,
                        description=desc,
                    )
                )
        except Exception as exc:
            self.warnings.append(f"Không đọc được Params trong '{atc_name}': {exc}")
        return params

    def sync_parameter_to_atc(
        self,
        name: str,
        data_type: str,
        default_value: str,
        display_name: str,
        description: str,
    ) -> None:
        """Đồng bộ Input Parameter mới thêm vào mục <Params> của file <guid>.atc."""
        atc_name = self.find_atc_filename()
        if not atc_name:
            self.warnings.append(f"Gói không có file .atc nên Parameter '{name}' chưa được đồng bộ sang Civil 3D.")
            return
        try:
            parser = etree.XMLParser(remove_blank_text=False)
            root = etree.fromstring(self.files[atc_name], parser)
            params_containers = root.xpath("//*[local-name()='Params']")
            if not params_containers:
                self.warnings.append(f"File '{atc_name}' không có mục <Params>; Parameter '{name}' chưa được đồng bộ.")
                return
            params_el = params_containers[0]

            # Ánh xạ kiểu dữ liệu sang chuẩn .atc của Civil 3D
            atc_dt = "double"
            type_info = "16"
            if data_type in ("Grade",):
                atc_dt, type_info = "double", "9"
            elif data_type in ("Slope",):
                atc_dt, type_info = "double", "10"
            elif data_type in ("Integer", "Side", "Superelevation", "Boolean", "YesNo"):
                atc_dt, type_info = "long", "16"
            elif data_type in ("String",):
                atc_dt, type_info = "string", "16"

            existing = params_el.xpath(f"./*[local-name()='{name}']")
            if existing:
                el = existing[0]
            else:
                el = etree.SubElement(params_el, name)

            el.set("DataType", atc_dt)
            el.set("TypeInfo", type_info)
            el.set("DisplayName", display_name or name)
            el.set("Description", description or name)
            el.text = str(default_value)

            self.files[atc_name] = etree.tostring(
                root, encoding="utf-8", xml_declaration=True, pretty_print=True
            )
        except Exception as exc:
            self.warnings.append(f"Đồng bộ Parameter '{name}' sang '{atc_name}' thất bại: {exc}")

    def get_metadata(self) -> Dict[str, Any]:
        """Đọc thông tin SubassemblyName, Description, Version từ .atc/.cfg hoặc PacketSettings.xml."""
        result: Dict[str, Any] = {
            "subassembly_name": self.pkt_path.stem,
            "description": "",
            "packet_version_tag": "13.8.1516.0",
            "detected_civil_version": "2026",
        }

        cfg_name = self.find_cfg_filename()
        if cfg_name:
            raw_cfg = self.files[cfg_name].decode("utf-8-sig", errors="replace")
            result["detected_civil_version"] = VersionManager.detect_version_from_cfg_or_settings(raw_cfg)
            try:
                cfg_root = etree.fromstring(self.files[cfg_name])
                vn = cfg_root.xpath("//*[local-name()='VersionNumber']")
                if vn and vn[0].text:
                    result["packet_version_tag"] = vn[0].text.strip()
            except Exception as exc:
                self.warnings.append(f"Không đọc được VersionNumber trong '{cfg_name}': {exc}")

        atc_name = self.find_atc_filename()
        if atc_name:
            try:
                atc_root = etree.fromstring(self.files[atc_name])
                # Nếu có các Tool con (ToolType=1 hoặc Tool trong Category)
                tools = atc_root.xpath("//*[local-name()='Tool']")
                names = []
                descs = []
                for t in tools:
                    t_type = t.findtext("ToolType")
                    if t_type and t_type != "1":
                        continue
                    iname = t.xpath("./*[local-name()='Properties']/*[local-name()='ItemName']")
                    idesc = t.xpath("./*[local-name()='Properties']/*[local-name()='Description']")
                    if iname and iname[0].text:
                        names.append(iname[0].text.strip())
                    if idesc and idesc[0].text:
                        descs.append(idesc[0].text.strip())
                if names:
                    result["subassembly_name"] = " | ".join(names)
                if descs:
                    result["description"] = " | ".join(descs)
            except Exception as exc:
                self.warnings.append(f"Không đọc được metadata trong '{atc_name}': {exc}")

        if "PacketSettings.xml" in self.files:
            raw_ps = self.files["PacketSettings.xml"].decode("utf-8-sig", errors="replace")
            result["detected_civil_version"] = VersionManager.detect_version_from_cfg_or_settings(raw_ps)
            try:
                ps_root = etree.fromstring(self.files["PacketSettings.xml"])
                sn = ps_root.xpath("//*[local-name()='SubassemblyName']")
                sd = ps_root.xpath("//*[local-name()='Description']")
                sv = ps_root.xpath("//*[local-name()='Version']")
                if sn and sn[0].text:
                    result["subassembly_name"] = sn[0].text.strip()
                if sd and sd[0].text:
                    result["description"] = sd[0].text.strip()
                if sv and sv[0].text:
                    result["packet_version_tag"] = sv[0].text.strip()
            except Exception as exc:
                self.warnings.append(f"Không đọc được PacketSettings.xml: {exc}")

        return result

    def update_metadata(
        self,
        subassembly_name: Optional[str] = None,
        description: Optional[str] = None,
        civil_version: Optional[str | CivilVersion] = None,
    ) -> None:
        """Cập nhật tên Subassembly, Description và VersionNumber trong .atc và .cfg."""
        safe_name = (
            VersionManager.sanitize_subassembly_name(subassembly_name)
            if subassembly_name
            else None
        )
        cfg_name = self.find_cfg_filename()
        if cfg_name and civil_version is not None:
            spec = VersionManager.get_spec(civil_version)
            self.files[cfg_name] = VersionManager.build_cfg_xml(version=spec.civil_version).encode("utf-8")

        atc_name = self.find_atc_filename()
        if atc_name and (safe_name or description is not None):
            try:
                parser = etree.XMLParser(remove_blank_text=False)
                root = etree.fromstring(self.files[atc_name], parser)
                for tool in root.xpath("//*[local-name()='Tool']"):
                    if safe_name:
                        tool.set("Name", safe_name)
                        for el in tool.xpath("./*[local-name()='Properties']/*[local-name()='ItemName']"):
                            el.text = safe_name
                        for el in tool.xpath(".//*[local-name()='DotNetClass']"):
                            el.text = f"Subassembly.{safe_name}"
                    if description is not None:
                        for el in tool.xpath("./*[local-name()='Properties']/*[local-name()='Description']"):
                            el.text = description
                self.files[atc_name] = etree.tostring(
                    root, encoding="utf-8", xml_declaration=True, pretty_print=True
                )
            except Exception as exc:
                self.warnings.append(f"Cập nhật tên/mô tả trong '{atc_name}' thất bại: {exc}")

    def save(
        self,
        target_path: Optional[str | Path] = None,
        *,
        backup: bool = False,
        validate: bool = False,
    ) -> Path:
        """
        Đóng gói lại thành file .pkt chuẩn ZIP (DEFLATED) theo cách an toàn:
          1. Ghi ra file tạm cùng thư mục.
          2. (validate=True) Kiểm định Tầng 1 + 2 trên file tạm. Nếu phát sinh lỗi MỚI so với
             file gốc -> xoá file tạm, giữ nguyên file gốc và raise PktValidationError.
          3. (backup=True) Sao lưu file gốc thành '<tên>.pkt.bak'.
          4. Thay thế nguyên tử (os.replace) -> không bao giờ để lại file .pkt ghi dở.
        """
        out_path = Path(target_path).resolve() if target_path else self.pkt_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for member_name, data in self.files.items():
                zf.writestr(member_name, data)

        tmp_path = out_path.with_name(f".{out_path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp_path.write_bytes(buf.getvalue())
        self.last_backup_path = None
        try:
            if validate:
                self._validate_before_commit(tmp_path, out_path)
            if backup and out_path.exists():
                bak_path = out_path.with_name(out_path.name + ".bak")
                shutil.copy2(out_path, bak_path)
                self.last_backup_path = bak_path
            os.replace(tmp_path, out_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        self.pkt_path = out_path
        return out_path

    @staticmethod
    def _validate_before_commit(tmp_path: Path, out_path: Path) -> None:
        from sac_mcp.core.validator import PktValidator

        new_rep = PktValidator.validate_pkt(tmp_path, run_native_test=False)
        if new_rep.is_valid:
            return
        baseline: set = set()
        if out_path.exists():
            old_rep = PktValidator.validate_pkt(out_path, run_native_test=False)
            baseline = {(i.category, i.location) for i in old_rep.issues if i.severity == "ERROR"}
        new_errors = [
            i for i in new_rep.issues if i.severity == "ERROR" and (i.category, i.location) not in baseline
        ]
        if new_errors:
            raise PktValidationError(new_errors)
