"""
Script tạo lại toàn bộ 7 bộ Subassembly độc lập chuẩn Civil 3D 2025-2027:
- Loại bỏ hoàn toàn chữ 'Visual' / 'VI_' trong tên file, tiêu đề, mô tả và cấu trúc
- Sử dụng chuẩn WF4 XAML Native (asw:* types, UTF-8 BOM, không có XML declaration)
- Đảm bảo 100% mở được trong Autodesk Subassembly Composer và Tool Palette Civil 3D
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from lxml import etree

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.server import create_pkt_from_template, add_parameter

SRC_VI_PKT = ROOT_DIR / "examples" / "Sub Assembly" / "SACVisualInfra.pkt"
SRC_SUB_DIR = ROOT_DIR / "examples" / "Sub Assembly"
OUTPUT_DIR = ROOT_DIR / "examples" / "Sub Assembly" / "Bo_7_Subassembly_Chuan"
from sac_mcp.paths import get_output_dir

PHUYEN_EXPORT_DIR = get_output_dir() / "Bo_7_Subassembly"

SUB_SPECS = [
    {
        "index": "01",
        "folder": "01_PhuiDaoCong",
        "sub_name": "PhuiDaoCong",
        "pkt_filename": "01_PhuiDaoCong.pkt",
        "title": "Phui đào cống thoát nước & Công trình ngầm",
        "html_file": "PhuiCong_Help.html",
        "image_file": "Images/PipeTrench.png",
        "cls_match": "PipeTrenchSubAssembly",
    },
    {
        "index": "02",
        "folder": "02_VetHuuCo_DanhCap",
        "sub_name": "VetHuuCo_DanhCap",
        "pkt_filename": "02_VetHuuCo_DanhCap.pkt",
        "title": "Vét hữu cơ & Đánh cấp nền đường",
        "html_file": "Help_DCVHC.html",
        "image_file": "Images/StripBench.png",
        "cls_match": "StrippingBenchingSubAssembly",
    },
    {
        "index": "03",
        "folder": "03_SoSanhBeMat",
        "sub_name": "SoSanhBeMat",
        "pkt_filename": "03_SoSanhBeMat.pkt",
        "title": "So sánh bề mặt địa hình TIN",
        "html_file": "HuongDan_SubCompareSurfaces.html",
        "image_file": "Images/CompareSurface.png",
        "cls_match": "CompareSurfaces",
    },
    {
        "index": "04",
        "folder": "04_KetCauDuongCu",
        "sub_name": "KetCauDuongCu",
        "pkt_filename": "04_KetCauDuongCu.pkt",
        "title": "Kết cấu áo đường hiện hữu",
        "html_file": "HuongDan_SubDuongCu.html",
        "image_file": "Images/DuongCu.png",
        "cls_match": "DuongCuSubAssembly",
    },
    {
        "index": "05",
        "folder": "05_TaluyDaoDapDayDu",
        "sub_name": "TaluyDaoDapDayDu",
        "pkt_filename": "05_TaluyDaoDapDayDu.pkt",
        "title": "Mái taluy đào đắp đầy đủ, cơ taluy và rãnh biên",
        "html_file": "Help_Taluy.html",
        "image_file": "Images/TaluyFull.png",
        "cls_match": "TaluyFullSubAssembly",
    },
    {
        "index": "06",
        "folder": "06_DuongNangCapCaiTao",
        "sub_name": "DuongNangCapCaiTao",
        "pkt_filename": "06_DuongNangCapCaiTao.pkt",
        "title": "Kết cấu áo đường nâng cấp, bù vênh & mở rộng",
        "html_file": "HuongDan_NangCapCaiTao.html",
        "image_file": "Images/NangCapCaiTao.png",
        "cls_match": "NangCapCaiTaoSubAssembly",
    },
    {
        "index": "07",
        "folder": "07_KetCauMatDuongMoi",
        "sub_name": "KetCauMatDuongMoi",
        "pkt_filename": "07_KetCauMatDuongMoi.pkt",
        "title": "Kết cấu mặt đường mới (5 lớp bậc thang)",
        "html_file": "HuongDan_KetCauMatDuongMoi.html",
        "image_file": "Images/KetCauMoi.png",
        "cls_match": "KetCauMatDuongMoiSubAssembly",
    },
]


def extract_parameters_from_atc(cls_match: str) -> list[dict]:
    with zipfile.ZipFile(SRC_VI_PKT, "r") as z:
        root = etree.fromstring(z.read("SACVisualInfra.atc"))
        for tool in root.xpath('//Tool[ToolType="1"]'):
            cls = tool.findtext(".//DotNetClass") or ""
            if cls_match in cls:
                params = []
                for p in tool.xpath(".//Params/*"):
                    tag = p.tag
                    if tag == "Side":
                        continue
                    dt = p.get("DataType", "double")
                    ti = p.get("TypeInfo", "16")
                    val = (p.text or "").strip()
                    disp = p.get("DisplayName", tag)
                    desc = p.get("Description", "")
                    
                    # Ánh xạ DataType chuẩn SAC
                    sac_type = "Double"
                    if dt == "long":
                        sac_type = "Integer"
                    elif dt == "string":
                        sac_type = "String"
                    elif ti == "9":
                        sac_type = "Grade"
                    elif ti == "10":
                        sac_type = "Slope"

                    params.append({
                        "name": tag,
                        "data_type": sac_type,
                        "default_value": val if val else ("0.02" if sac_type in ("Grade", "Slope") else "0"),
                        "display_name": disp,
                        "description": desc,
                    })
                return params
    return []


def build_all() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PHUYEN_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    catalog = []

    print("=== BẮT ĐẦU TẠO 7 SUBASSEMBLY CHUẨN (ĐÃ XÓA CHỮ VISUAL) ===")
    for spec in SUB_SPECS:
        sub_dir = OUTPUT_DIR / spec["folder"]
        sub_dir.mkdir(parents=True, exist_ok=True)
        pkt_path = sub_dir / spec["pkt_filename"]

        print(f"\n[{spec['index']}/07] Khởi tạo {spec['sub_name']} -> {spec['pkt_filename']}...")

        # 1. Tạo file PKT chuẩn từ Base template 2026
        create_pkt_from_template(
            output_path=str(pkt_path),
            subassembly_name=spec["sub_name"],
            description=spec["title"],
            civil_version="2026",
        )

        # 2. Bơm toàn bộ Parameters tương ứng
        params = extract_parameters_from_atc(spec["cls_match"])
        for p in params:
            add_parameter(
                pkt_path=str(pkt_path),
                name=p["name"],
                param_category="Input",
                data_type=p["data_type"],
                default_value=p["default_value"],
                display_name=p["display_name"],
                description=p["description"],
            )

        print(f"  -> Đã nạp {len(params)} parameters vào {spec['pkt_filename']} ({pkt_path.stat().st_size} bytes)")

        # 3. Sao chép ảnh icon và file HTML hướng dẫn vào thư mục (bỏ chữ visual)
        with zipfile.ZipFile(SRC_VI_PKT, "r") as z:
            img_bytes = z.read(spec["image_file"])
            (sub_dir / Path(spec["image_file"]).name).write_bytes(img_bytes)

        src_html = SRC_SUB_DIR / spec["html_file"]
        if src_html.exists():
            shutil.copy2(src_html, sub_dir / spec["html_file"])

        # 4. Sao chép sang Desktop Phú Yên để anh sử dụng ngay
        phuyen_dest = PHUYEN_EXPORT_DIR / spec["pkt_filename"]
        shutil.copy2(pkt_path, phuyen_dest)

        catalog.append({
            "index": spec["index"],
            "name": spec["sub_name"],
            "file": spec["pkt_filename"],
            "title": spec["title"],
            "parameters_count": len(params),
            "size_kb": round(pkt_path.stat().st_size / 1024, 2),
            "pkt_path": str(pkt_path),
            "sac_editable_pkt_path": str(pkt_path),
            "parameter_count": len(params),
            "html_help": spec["html_file"],
            "image": Path(spec["image_file"]).name,
        })

    # Ghi catalog sạch (không có chữ visual)
    cat_file = OUTPUT_DIR / "catalog_7_subassembly.json"
    cat_file.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(cat_file, PHUYEN_EXPORT_DIR / "catalog_7_subassembly.json")

    print("\n=== HOÀN TẤT TẠO 7 SUBASSEMBLY! ===")


if __name__ == "__main__":
    build_all()
