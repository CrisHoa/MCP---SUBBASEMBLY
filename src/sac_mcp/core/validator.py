"""
Engine kiểm định toàn diện (Comprehensive Validator) cho file Subassembly Composer (.pkt).
Thực hiện 3 tầng kiểm tra (3-Tier Validation):
  1. Tầng 1: OPC Package & XML Escaping (6 GUID files, Content_Types, BOM, &amp;)
  2. Tầng 2: WF4 / XAML Semantic Syntax (Bọc [...] biểu thức, tên biến hợp lệ, activity hợp lệ)
  3. Tầng 3: Native Autodesk Subassembly Composer Runtime Hook (gọi SubassemblyDocument trực tiếp từ DLL gốc)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import zipfile

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from lxml import etree


AUTODESK_SAC_DIRS = [
    Path(r"C:\Program Files\Autodesk\Subassembly Composer 2027"),
    Path(r"C:\Program Files\Autodesk\Subassembly Composer 2026"),
    Path(r"C:\Program Files\Autodesk\Subassembly Composer 2025"),
    Path(r"C:\Program Files\Autodesk\Subassembly Composer 2024"),
]


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
        print(f"  - Tầng 3 (Native Autodesk DLL):  {'✅ OK' if self.tier3_native_ok else '⚠️ CHƯA ĐẠT / KHÔNG CÓ DLL'}")
        
        if self.metadata:
            print(f"  - Tên Subassembly: {self.metadata.get('name', 'N/A')}")
            print(f"  - Số tham số:      {self.metadata.get('parameters_count', 0)}")
            print(f"  - Kích thước:      {self.metadata.get('size_bytes', 0)} bytes")

        if self.issues:
            print(f"\nChi tiết cảnh báo & lỗi ({len(self.issues)} mục):")
            for iss in self.issues:
                loc = f" [{iss.location}]" if iss.location else ""
                color_prefix = "❌ [ERROR]" if iss.severity == "ERROR" else "⚠️ [WARN]"
                print(f"  {color_prefix}{loc} {iss.message}")
        print(f"{'='*70}\n")


class PktValidator:
    """Validator kiểm định .pkt nhanh trong < 0.5s."""

    @classmethod
    def get_sac_install_dir(cls) -> Optional[Path]:
        for d in AUTODESK_SAC_DIRS:
            if (d / "WorkflowEditor.dll").exists():
                return d
        return None

    @classmethod
    def validate_pkt(cls, pkt_path: str | Path, run_native_test: bool = True) -> ValidationReport:
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
        if report.is_valid and run_native_test:
            cls._validate_tier3_native(p, report)

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

                if report.is_valid:
                    report.tier2_xaml_ok = True
        except Exception as e:
            report.add_issue("ERROR", "XAML", f"Lỗi phân tích cú pháp XAML: {e}")

    @classmethod
    def _validate_tier3_native(cls, pkt_path: Path, report: ValidationReport) -> None:
        sac_dir = cls.get_sac_install_dir()
        if not sac_dir:
            report.add_issue("INFO", "NATIVE", "Không tìm thấy Autodesk Subassembly Composer trên máy để chạy kiểm thử Tầng 3.")
            return

        ps_script = f"""
$sacDir = '{sac_dir}'
$resolving = $false
[System.AppDomain]::CurrentDomain.add_AssemblyResolve({{
    param($sender, $args)
    if ($resolving) {{ return $null }}
    try {{
        $resolving = $true
        $name = ($args.Name -split ',')[0]
        $targetPath = Join-Path $sacDir "$name.dll"
        if (Test-Path $targetPath) {{ return [System.Reflection.Assembly]::LoadFrom($targetPath) }}
    }} finally {{ $resolving = $false }}
    return $null
}})
Add-Type -AssemblyName 'System.Activities'
Add-Type -AssemblyName 'System.Activities.Presentation'
Add-Type -AssemblyName 'WindowsBase'
$wfe = [System.Reflection.Assembly]::LoadFrom("$sacDir\\WorkflowEditor.dll")
$docType = $wfe.GetType('Autodesk.SubassemblyComposer.WorkflowEditor.SubassemblyDocument')
try {{
    $doc = [System.Activator]::CreateInstance($docType, @('{str(pkt_path)}'))
    Write-Host "SAC_DOCUMENT_LOAD_SUCCESS"
}} catch {{
    Write-Host "SAC_DOCUMENT_LOAD_FAIL: $($_.Exception.InnerException.ToString())"
}}
"""
        try:
            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            out = res.stdout.strip()
            if "SAC_DOCUMENT_LOAD_SUCCESS" in out:
                report.tier3_native_ok = True
            else:
                fail_msg = out.replace("SAC_DOCUMENT_LOAD_FAIL:", "").strip()
                report.add_issue("ERROR", "NATIVE_RUNTIME", f"Autodesk Subassembly Composer nạp thất bại: {fail_msg}")
        except subprocess.TimeoutExpired:
            report.add_issue("ERROR", "NATIVE_TIMEOUT", "Kiểm thử native DLL timeout quá 10 giây.")
        except Exception as e:
            report.add_issue("ERROR", "NATIVE_ERROR", f"Lỗi chạy kiểm thử native DLL: {e}")


def main() -> None:
    # Chỉ đổi encoding khi chạy CLI (không làm ở cấp module vì server MCP dùng stdout làm kênh JSON-RPC)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Sử dụng: python -m sac_mcp.core.validator <duong_dan_file.pkt>")
        sys.exit(1)

    target = sys.argv[1]
    rep = PktValidator.validate_pkt(target, run_native_test=True)
    rep.print_summary()
    sys.exit(0 if rep.is_valid else 1)


if __name__ == "__main__":
    main()
