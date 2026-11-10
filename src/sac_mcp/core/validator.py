"""
Engine kiểm định toàn diện cho file Subassembly Composer (.pkt), gồm 3 tầng:
  1. Tầng 1: OPC Package & XML (đủ 6 file GUID, Content_Types, XML hợp lệ, escape '&').
  2. Tầng 2: WF4 / XAML tĩnh, chạy được khi máy không cài SAC:
     - BOM, không có header <?xml, tên biến VB hợp lệ, biểu thức bọc [...], không dùng thẻ mock 'sac:'.
     - Ngữ nghĩa (core/semantic_checks.py): activity có thật, x:Reference không treo,
       node không mồ côi, tham chiếu Point/Link đã được tạo.
  3. Tầng 3: Native Autodesk (native/host.py -> SacHost.exe, dùng DLL gốc của đúng phiên bản SAC):
     - Nạp XAML thành cây activity (bắt tag sai, x:Reference treo).
     - Biên dịch MỌI biểu thức VB (biến chưa khai báo, cú pháp hỏng, sai kiểu).
     - (Tuỳ chọn document_check) mở bằng SubassemblyDocument giống SAC GUI.
"""

from __future__ import annotations

import re
import sys
import zipfile

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from lxml import etree

from sac_mcp.core.semantic_checks import check_semantics
from sac_mcp.core.version_manager import VersionManager

_VB_EXPR_RE = re.compile(r'processing expression "(?P<expr>.*?)"\.\s*(?P<detail>.*)', re.DOTALL)
_ACTIVITY_LIB_NS = "Autodesk.SubassemblyComposer.ActivityLibrary"
_WF_PRIVATE_PREFIX_RE = re.compile(
    r"^The private implementation of activity '.*?' has the following validation error:\s*", re.DOTALL
)


@dataclass
class ValidationIssue:
    severity: str  # "ERROR" | "WARNING" | "INFO"
    category: str
    message: str
    location: Optional[str] = None


@dataclass
class ValidationReport:
    pkt_path: str
    is_valid: bool
    tier1_opc_ok: bool = False
    tier2_xaml_ok: bool = False
    tier3_native_ok: bool = False
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_issue(self, severity: str, category: str, message: str, location: Optional[str] = None) -> None:
        self.issues.append(ValidationIssue(severity=severity, category=category, message=message, location=location))
        if severity == "ERROR":
            self.is_valid = False

    def print_summary(self) -> None:
        p = Path(self.pkt_path)
        status_icon = "✅ PASS" if self.is_valid else "❌ FAIL"
        print(f"\n{'='*70}")
        print(f"BÁO CÁO KIỂM ĐỊNH SAC: {p.name} -> {status_icon}")
        print(f"{'='*70}")
        print(f"  - Tầng 1 (OPC Package & XML):  {'✅ OK' if self.tier1_opc_ok else '❌ LỖI'}")
        print(f"  - Tầng 2 (WF4 / XAML Semantics): {'✅ OK' if self.tier2_xaml_ok else '❌ LỖI'}")
        if self.tier3_native_ok:
            t3 = f"✅ OK (SAC {self.metadata.get('sac_version', '?')})"
        elif self.metadata.get("tier3_skipped"):
            t3 = f"⏭️ BỎ QUA ({self.metadata['tier3_skipped']})"
        else:
            t3 = "❌ LỖI"
        print(f"  - Tầng 3 (Native Autodesk DLL):  {t3}")

        if self.metadata:
            print(f"  - Tên Subassembly: {self.metadata.get('name', 'N/A')}")
            print(f"  - Số tham số:      {self.metadata.get('parameters_count', 0)}")
            print(f"  - Kích thước:      {self.metadata.get('size_bytes', 0)} bytes")

        if self.issues:
            print(f"\nChi tiết cảnh báo & lỗi ({len(self.issues)} mục):")
            for iss in self.issues:
                loc = f" [{iss.location}]" if iss.location and iss.location not in iss.message else ""
                color_prefix = {"ERROR": "❌ [ERROR]", "WARNING": "⚠️ [WARN]"}.get(iss.severity, "ℹ️ [INFO]")
                print(f"  {color_prefix}{loc} {iss.message}")
        print(f"{'='*70}\n")


class PktValidator:
    """Kiểm định .pkt 3 tầng. Tầng 3 dùng tiến trình SacHost chạy nền (~10 ms/file khi đã khởi động)."""

    @classmethod
    def validate_pkt(
        cls,
        pkt_path: str | Path,
        run_native_test: bool = True,
        document_check: bool = False,
    ) -> ValidationReport:
        """
        run_native_test: chạy Tầng 3 (cần cài Subassembly Composer; nếu không có thì ghi INFO và bỏ qua).
        document_check:  Tầng 3 mở thêm file bằng SubassemblyDocument như SAC GUI (chậm hơn ~2 giây).
        """
        p = Path(pkt_path).resolve()
        report = ValidationReport(pkt_path=str(p), is_valid=True)

        if not p.exists():
            report.add_issue("ERROR", "File", f"File không tồn tại: {p}")
            return report

        report.metadata["size_bytes"] = p.stat().st_size

        # --------------------------------------------------------------------
        # TẦNG 1: Kiểm định cấu trúc ZIP / OPC và các file GUID
        # --------------------------------------------------------------------
        cls._validate_tier1_opc(p, report)

        # --------------------------------------------------------------------
        # TẦNG 2: Kiểm định cú pháp XAML và Workflow Foundation 4
        # --------------------------------------------------------------------
        if report.is_valid:
            cls._validate_tier2_xaml(p, report)

        # --------------------------------------------------------------------
        # TẦNG 3: Kiểm định Runtime trực tiếp bằng DLL Autodesk Subassembly Composer
        # --------------------------------------------------------------------
        # Chạy Tầng 3 khi Tầng 1 đạt (kể cả khi Tầng 2 lỗi) để có thêm chẩn đoán từ DLL gốc
        if report.tier1_opc_ok and run_native_test:
            cls._validate_tier3_native(p, report, document_check=document_check)
        elif not run_native_test:
            report.metadata["tier3_skipped"] = "không yêu cầu"

        return report

    @classmethod
    def _validate_tier1_opc(cls, pkt_path: Path, report: ValidationReport) -> None:
        try:
            with zipfile.ZipFile(pkt_path, "r") as z:
                names = z.namelist()
                has_content_types = "[Content_Types].xml" in names
                if not has_content_types:
                    report.add_issue("ERROR", "OPC", "Thiếu file [Content_Types].xml bắt buộc của chuẩn OPC Package.")

                extensions = {Path(n).suffix.lower() for n in names}
                for required_ext in (".atc", ".cfg", ".xaml", ".pvd", ".emd", ".cdmd"):
                    if required_ext not in extensions:
                        report.add_issue("ERROR", "OPC", f"Thiếu file định dạng {required_ext} bắt buộc trong gói .pkt.")

                # Kiểm tra XML parsing trên từng file con
                for name in names:
                    if name.endswith((".xml", ".atc", ".cfg", ".xaml", ".pvd", ".emd", ".cdmd")):
                        raw = z.read(name)
                        try:
                            # Cảnh báo lỗi unescaped ampersand
                            raw_str = raw.decode("utf-8-sig", errors="replace")
                            unescaped_amp = re.findall(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", raw_str)
                            if unescaped_amp:
                                report.add_issue(
                                    "ERROR",
                                    "XML",
                                    f"File '{name}' chứa ký tự '&' chưa được escape thành '&amp;' (tìm thấy {len(unescaped_amp)} chỗ).",
                                    location=name,
                                )

                            etree.fromstring(raw)
                        except Exception as e:
                            report.add_issue("ERROR", "XML", f"File '{name}' lỗi cú pháp XML: {e}", location=name)

                if report.is_valid:
                    report.tier1_opc_ok = True
        except zipfile.BadZipFile:
            report.add_issue("ERROR", "OPC", f"File '{pkt_path.name}' không phải file nén ZIP / OPC hợp lệ.")
        except Exception as e:
            report.add_issue("ERROR", "OPC", f"Lỗi đọc file .pkt: {e}")

    @classmethod
    def _validate_tier2_xaml(cls, pkt_path: Path, report: ValidationReport) -> None:
        try:
            with zipfile.ZipFile(pkt_path, "r") as z:
                xaml_names = [n for n in z.namelist() if n.lower().endswith(".xaml")]
                if not xaml_names:
                    return

                xaml_name = xaml_names[0]
                raw_bytes = z.read(xaml_name)

                # 1. Kiểm tra UTF-8 BOM
                if not raw_bytes.startswith(b"\xef\xbb\xbf"):
                    report.add_issue(
                        "ERROR",
                        "XAML_BOM",
                        f"File '{xaml_name}' thiếu UTF-8 BOM (\\xef\\xbb\\xbf). SAC sẽ báo lỗi '.pkt file is invalid'.",
                        location=xaml_name,
                    )

                # 2. Kiểm tra không có header <?xml...
                head_snippet = raw_bytes[:50].decode("utf-8", errors="ignore")
                if "<?xml" in head_snippet:
                    report.add_issue(
                        "ERROR",
                        "XAML_HEADER",
                        f"File '{xaml_name}' không được chứa '<?xml...>' header ở đầu file.",
                        location=xaml_name,
                    )

                root = etree.fromstring(raw_bytes)
                report.metadata["name"] = root.get("{http://schemas.microsoft.com/winfx/2006/xaml}Class", "Subassembly")

                # 3. Kiểm tra biến trong Flowchart.Variables
                for var in root.xpath("//*[local-name()='Variable']"):
                    vname = var.get("Name", "")
                    # Tên biến phải là VB identifier hợp lệ (không chứa tiếng Việt, khoảng trắng, ngoặc đơn, hai chấm)
                    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", vname):
                        report.add_issue(
                            "ERROR",
                            "VB_IDENTIFIER",
                            f"Tên biến '{vname}' trong Flowchart.Variables chứa ký tự không hợp lệ. Phải tuân thủ định danh VB.NET.",
                            location=xaml_name,
                        )

                # 4. Kiểm tra InArgument expression: biến/biểu thức phải bọc trong [...]
                for arg in root.xpath("//*[contains(local-name(), '.Arguments')]/*[local-name()='InArgument']"):
                    arg_key = arg.get("{http://schemas.microsoft.com/winfx/2006/xaml}Key", "")
                    arg_type = arg.get("{http://schemas.microsoft.com/winfx/2006/xaml}TypeArguments", "")
                    txt = (arg.text or "").strip()
                    if txt and not txt.startswith("["):
                        # Nếu là x:Double hoặc số nhưng lại chứa chữ (tên biến, biểu thức phép tính)
                        if arg_type in ("x:Double", "asw:Slope", "asw:Grade"):
                            try:
                                float(txt)
                            except ValueError:
                                report.add_issue(
                                    "ERROR",
                                    "ARG_EXPRESSION",
                                    f"Đối số '{arg_key}' ({arg_type}) có giá trị biến '{txt}' nhưng chưa được bọc trong '[...]'.",
                                    location=xaml_name,
                                )

                # 5. Kiểm tra activity hợp lệ (phải là asa2 hoặc asa1, không dùng mock sac:)
                illegal_tags = root.xpath("//*[starts-with(name(), 'sac:')]")
                if illegal_tags:
                    report.add_issue(
                        "ERROR",
                        "XAML_TAGS",
                        f"Tìm thấy {len(illegal_tags)} thẻ namespace 'sac:' không tồn tại trong SAC DLL (ví dụ PointGeometry). Phải dùng 'asa2:CreatePoint'.",
                        location=xaml_name,
                    )

                # Đếm số parameters
                props = root.xpath("./*[local-name()='Members']/*[local-name()='Property']")
                report.metadata["parameters_count"] = len(props)

                # 6. Ngữ nghĩa tĩnh: activity có thật, x:Reference, node mồ côi, tham chiếu Point/Link
                for iss in check_semantics(raw_bytes.decode("utf-8-sig")):
                    report.add_issue(iss.severity, iss.category, iss.message, location=iss.location)

                if report.is_valid:
                    report.tier2_xaml_ok = True
        except Exception as e:
            report.add_issue("ERROR", "XAML", f"Lỗi phân tích cú pháp XAML: {e}")

    @classmethod
    def _validate_tier3_native(cls, pkt_path: Path, report: ValidationReport, document_check: bool = False) -> None:
        from sac_mcp.native.host import NativeHostError, check_pkt

        pkt_version = cls._detect_version(pkt_path)
        try:
            res = check_pkt(pkt_path, pkt_version=pkt_version, document_check=document_check)
        except NativeHostError as exc:
            report.metadata["tier3_skipped"] = "lỗi SacHost"
            report.add_issue("WARNING", "NATIVE_HOST", f"Không chạy được Tầng 3: {exc}")
            return
        if res is None:
            report.metadata["tier3_skipped"] = "máy không cài Subassembly Composer"
            report.add_issue("INFO", "NATIVE", "Không tìm thấy Autodesk Subassembly Composer trên máy, bỏ qua Tầng 3.")
            return

        report.metadata["sac_version"] = res.sac_version
        report.metadata["native_elapsed_ms"] = res.elapsed_ms
        if pkt_version and res.sac_version not in (pkt_version, "custom"):
            report.add_issue(
                "INFO",
                "NATIVE",
                f"File dành cho Civil 3D {pkt_version} nhưng máy không cài SAC {pkt_version}; "
                f"đã kiểm định bằng SAC {res.sac_version}.",
            )

        xaml_root = cls._read_xaml_root(pkt_path)
        if not res.xaml_load_ok:
            report.add_issue("ERROR", "NATIVE_XAML_LOAD", f"SAC không nạp được XAML: {res.xaml_load_error}")
        static_required = {
            (i.location or "").split(".")[-1] for i in report.issues if i.category == "ARGUMENT_REQUIRED"
        }
        for err in res.validation_errors:
            # Kiểm tra tĩnh đã chỉ đúng activity thiếu đối số này -> không lặp lại lỗi chung của WF4
            if "required activity argument" in (err.get("message") or "") and err.get("property") in static_required:
                continue
            category, message, location = cls._describe_native_error(err, xaml_root)
            report.add_issue("ERROR", category, message, location=location)
        for warn in res.validation_warnings:
            report.add_issue("WARNING", "NATIVE_VALIDATION", warn.get("message", ""), location=warn.get("activity"))
        if res.document_ok is False:
            report.add_issue("ERROR", "NATIVE_DOCUMENT", f"SubassemblyDocument không mở được file: {res.document_error}")
        report.tier3_native_ok = res.ok

    @staticmethod
    def _detect_version(pkt_path: Path) -> Optional[str]:
        try:
            with zipfile.ZipFile(pkt_path) as z:
                for name in z.namelist():
                    if name.lower().endswith(".cfg") or name == "PacketSettings.xml":
                        text = z.read(name).decode("utf-8-sig", errors="replace")
                        m = re.search(r"<VersionNumber>\s*13\.(\d)\.", text)
                        if m:
                            return {"6": "2024", "7": "2025", "8": "2026", "9": "2027"}.get(m.group(1))
                        return VersionManager.detect_version_from_cfg_or_settings(text)
        except (OSError, zipfile.BadZipFile):
            pass
        return None

    @staticmethod
    def _read_xaml_root(pkt_path: Path) -> Optional[etree._Element]:
        try:
            with zipfile.ZipFile(pkt_path) as z:
                name = next((n for n in z.namelist() if n.lower().endswith(".xaml")), None)
                return etree.fromstring(z.read(name)) if name else None
        except Exception:
            return None

    @classmethod
    def _describe_native_error(cls, err: Dict[str, Any], xaml_root: Optional[etree._Element]) -> tuple:
        """Rút gọn lỗi của WF4 và chỉ ra activity chứa biểu thức VB bị lỗi."""
        raw = _WF_PRIVATE_PREFIX_RE.sub("", (err.get("message") or "").strip())
        m = _VB_EXPR_RE.search(raw)
        if not m:
            msg = re.sub(r"\s+", " ", raw)
            category = "NATIVE_ACTIVITY" if "unknown type" in raw else (
                "NATIVE_REFERENCE" if "Unresolved reference" in raw else "NATIVE_VALIDATION"
            )
            return category, msg, err.get("activity")
        expr = m.group("expr")
        detail = re.sub(r"\s+", " ", m.group("detail")).strip()
        location = cls._locate_expression(xaml_root, expr) if xaml_root is not None else None
        where = f" (trong {location})" if location else ""
        return "VB_EXPRESSION", f"Biểu thức [{expr}]{where}: {detail}", location

    @staticmethod
    def _locate_expression(root: etree._Element, expr: str) -> Optional[str]:
        """
        Mọi vị trí dùng biểu thức lỗi (WF4 chỉ báo nội dung biểu thức, không báo activity).
        Cùng một biểu thức có thể xuất hiện ở nhiều nơi (VD [W] trong CreatePoint và Condition của
        FlowDecision), nên liệt kê tối đa 3 vị trí thay vì đoán một.
        """
        target = f"[{expr}]"
        found: List[str] = []
        for el in root.iter(etree.Element):
            attr_hits = [k for k, v in el.attrib.items() if v.strip() == target]
            text_hit = (el.text or "").strip() == target
            if not (attr_hits or text_hit):
                continue
            for anc in [el, *el.iterancestors()]:
                q = etree.QName(anc)
                ln = q.localname
                if (_ACTIVITY_LIB_NS in (q.namespace or "") and "." not in ln) or ln in ("FlowDecision", "FlowSwitch"):
                    label = anc.get("DisplayName") or anc.get("PointNumber") or anc.get("LinkNumber") or ""
                    key = el.get("{http://schemas.microsoft.com/winfx/2006/xaml}Key")
                    if not key and attr_hits:
                        key = etree.QName(attr_hits[0]).localname
                    arg = f", đối số {key}" if key else ""
                    loc = f"{ln} '{label}'{arg}" if label else f"{ln}{arg}"
                    if loc not in found:
                        found.append(loc)
                    break
        if not found:
            return None
        more = f" và {len(found) - 3} chỗ khác" if len(found) > 3 else ""
        return "; ".join(found[:3]) + more


def main() -> None:
    # Chỉ đổi encoding khi chạy CLI (không làm ở cấp module vì server MCP dùng stdout làm kênh JSON-RPC)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Sử dụng: python -m sac_mcp.core.validator <duong_dan_file.pkt>")
        sys.exit(1)

    target = sys.argv[1]
    rep = PktValidator.validate_pkt(target, run_native_test=True, document_check="--doc" in sys.argv)
    rep.print_summary()
    sys.exit(0 if rep.is_valid else 1)


if __name__ == "__main__":
    main()
