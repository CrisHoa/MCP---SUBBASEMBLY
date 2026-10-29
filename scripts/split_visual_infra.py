"""
Script tối ưu hóa và tách riêng gói SACVisualInfra.pkt (12 MB) cùng 7 file HTML hướng dẫn
trong thư mục 'examples/Sub Assembly' thành 7 bộ Subassembly độc lập, gọn nhẹ.
"""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Dict, List
import zipfile
from lxml import etree, html

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.server import create_pkt_from_template, add_parameter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SUB_DIR = ROOT_DIR / "examples" / "Sub Assembly"
OUTPUT_SPLIT_DIR = SUB_DIR / "Tach_Rieng_7_Subassembly"

# Ánh xạ chính xác từng Class trong SACVisualInfra.atc với mã thư mục, tên file PKT tách riêng và file HTML hướng dẫn
TOOL_MAPPING: Dict[str, Dict[str, str]] = {
    "SACVisualInfra._02.PhuiCong.PipeTrenchSubAssembly": {
        "index": "01",
        "folder": "01_PhuiDaoCong",
        "pkt_name": "VI_01_PhuiDaoCong.pkt",
        "short_code": "PhuiDaoCong",
        "html_file": "PhuiCong_Help.html",
        "image_file": "Images/PipeTrench.png",
        "category_group": "Hạ tầng thoát nước & Công trình ngầm",
    },
    "SACVisualInfra._03.DCVHC.StrippingBenchingSubAssembly": {
        "index": "02",
        "folder": "02_VetHuuCo_DanhCap",
        "pkt_name": "VI_02_VetHuuCo_DanhCap.pkt",
        "short_code": "VetHuuCo_DanhCap",
        "html_file": "Help_DCVHC.html",
        "image_file": "Images/StripBench.png",
        "category_group": "Xử lý nền đất yếu, Vét hữu cơ & Đánh cấp",
    },
    "SACVisualInfra._04.SoBeSurface.CompareSurfaces": {
        "index": "03",
        "folder": "03_SoSanhBeMat",
        "pkt_name": "VI_03_SoSanhBeMat.pkt",
        "short_code": "SoSanhBeMat",
        "html_file": "HuongDan_SubCompareSurfaces.html",
        "image_file": "Images/CompareSurface.png",
        "category_group": "Bề mặt & Phân tích địa hình TIN",
    },
    "SACVisualInfra._05.DuongCu.DuongCuSubAssembly": {
        "index": "04",
        "folder": "04_KetCauDuongCu",
        "pkt_name": "VI_04_KetCauDuongCu.pkt",
        "short_code": "KetCauDuongCu",
        "html_file": "HuongDan_SubDuongCu.html",
        "image_file": "Images/DuongCu.png",
        "category_group": "Kết cấu áo đường hiện hữu",
    },
    "SACVisualInfra._06.Taluy.TaluyFullSubAssembly": {
        "index": "05",
        "folder": "05_TaluyDaoDapDayDu",
        "pkt_name": "VI_05_TaluyDaoDapDayDu.pkt",
        "short_code": "TaluyDaoDapDayDu",
        "html_file": "Help_Taluy.html",
        "image_file": "Images/TaluyFull.png",
        "category_group": "Mái Taluy Đào/Đắp, Rãnh biên & Cơ taluy",
    },
    "SACVisualInfra._07.CaiTao.NangCapCaiTaoSubAssembly": {
        "index": "06",
        "folder": "06_DuongNangCapCaiTao",
        "pkt_name": "VI_06_DuongNangCapCaiTao.pkt",
        "short_code": "DuongNangCapCaiTao",
        "html_file": "HuongDan_NangCapCaiTao.html",
        "image_file": "Images/NangCapCaiTao.png",
        "category_group": "Kết cấu áo đường Nâng cấp, Bù vênh & Mở rộng",
    },
    "SACVisualInfra._08.KetCau.KetCauMatDuongMoiSubAssembly": {
        "index": "07",
        "folder": "07_KetCauMatDuongMoi",
        "pkt_name": "VI_07_KetCauMatDuongMoi.pkt",
        "short_code": "KetCauMatDuongMoi",
        "html_file": "HuongDan_KetCauMatDuongMoi.html",
        "image_file": "Images/KetCauMoi.png",
        "category_group": "Kết cấu áo đường làm mới (5 lớp bậc thang)",
    },
}


def extract_html_documentation(html_path: Path) -> Dict[str, Any]:
    """Trích xuất toàn bộ bảng biểu, thông số, Targets, Codes và hướng dẫn từ file HTML."""
    if not html_path.exists():
        return {}

    raw = html_path.read_text(encoding="utf-8", errors="replace")
    doc = html.fromstring(raw)

    title = (doc.findtext(".//title") or "").strip()
    headings = [
        re.sub(r"\s+", " ", h.text_content()).strip()
        for h in doc.xpath("//h1|//h2|//h3")
        if h.text_content().strip()
    ]

    tables_data: List[List[Dict[str, str]]] = []
    for tbl in doc.xpath("//table"):
        headers = [
            re.sub(r"\s+", " ", th.text_content()).strip()
            for th in tbl.xpath(".//thead//th | .//tr[1]/th | .//tr[1]/td")
        ]
        rows = []
        tr_list = tbl.xpath(".//tbody/tr") or tbl.xpath(".//tr")[1:]
        for tr in tr_list:
            cells = [
                re.sub(r"\s+", " ", td.text_content()).strip()
                for td in tr.xpath("./td|./th")
            ]
            if not cells:
                continue
            if headers and len(headers) == len(cells):
                rows.append(dict(zip(headers, cells)))
            else:
                rows.append({f"col_{idx+1}": val for idx, val in enumerate(cells)})
        if rows:
            tables_data.append(rows)

    return {
        "html_filename": html_path.name,
        "title": title,
        "sections": headings,
        "extracted_tables": tables_data,
    }


def extract_atc_tool_spec(tool_el: etree._Element) -> Dict[str, Any]:
    """Trích xuất toàn bộ Parameters và Enum options từ thẻ <Tool> trong SACVisualInfra.atc."""
    item_id = tool_el.xpath("ItemID/@idValue")[0]
    item_name = tool_el.findtext("Properties/ItemName") or ""
    description = (tool_el.findtext("Properties/Description") or "").strip()
    dotnet_class = tool_el.findtext(".//DotNetClass") or ""
    units = tool_el.findtext(".//Units") or "m"

    params: List[Dict[str, Any]] = []
    for p_el in tool_el.xpath(".//Params/*"):
        p_name = p_el.tag
        data_type = p_el.get("DataType", "string")
        type_info = p_el.get("TypeInfo", "")
        disp_name = p_el.get("DisplayName", p_name)
        desc = p_el.get("Description", "")
        default_val = (p_el.text or "").strip()

        enums = []
        for enum_item in p_el.xpath("./Enum/*"):
            enums.append(
                {
                    "key": enum_item.tag,
                    "display_name": enum_item.get("DisplayName", enum_item.tag),
                    "value": (enum_item.text or "").strip(),
                }
            )

        params.append(
            {
                "name": p_name,
                "data_type": data_type,
                "type_info": type_info,
                "default_value": default_val,
                "display_name": disp_name,
                "description": desc,
                "enum_options": enums,
            }
        )

    return {
        "item_id": item_id,
        "item_name": item_name,
        "description": description,
        "dotnet_class": dotnet_class,
        "units": units,
        "parameter_count": len(params),
        "parameters": params,
    }


def build_single_tool_atc_bytes(
    original_palette_root: etree._Element,
    header_tools: List[etree._Element],
    target_tool_el: etree._Element,
    help_filename: str,
) -> bytes:
    """
    Tạo nội dung file SACVisualInfra.atc mới chỉ chứa duy nhất 1 Subassembly Tool,
    đồng thời gắn đường dẫn HelpFile tới file HTML hướng dẫn.
    """
    new_root = deepcopy(original_palette_root)
    tools_container = new_root.find("Tools")
    for child in list(tools_container):
        tools_container.remove(child)

    # Giữ lại 2 header tool định danh Palette nếu có
    for h_tool in header_tools:
        tools_container.append(deepcopy(h_tool))

    single_tool = deepcopy(target_tool_el)
    tool_name = single_tool.findtext("Properties/ItemName") or "Visual Infra Subassembly"

    # Cập nhật tên Palette theo tên Subassembly riêng biệt
    palette_name_el = new_root.find("Properties/ItemName")
    if palette_name_el is not None:
        palette_name_el.text = tool_name

    # Bổ sung thẻ <Help><HelpFile> vào Properties của Tool
    props_el = single_tool.find("Properties")
    if props_el is not None and help_filename:
        existing_help = props_el.find("Help")
        if existing_help is None:
            existing_help = etree.SubElement(props_el, "Help")
        hf_el = existing_help.find("HelpFile")
        if hf_el is None:
            hf_el = etree.SubElement(existing_help, "HelpFile")
        hf_el.text = f".\\{help_filename}"

    tools_container.append(single_tool)
    return etree.tostring(new_root, encoding="utf-8", xml_declaration=True, pretty_print=True)


def build_content_types_for_visual_infra() -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="atc" ContentType="" />'
        '<Default Extension="dll" ContentType="application/octet-stream" />'
        '<Default Extension="png" ContentType="image/png" />'
        '<Default Extension="html" ContentType="text/html" />'
        "</Types>"
    ).encode("utf-8")


def build_part_readme(meta: Dict[str, str], spec: Dict[str, Any], doc_info: Dict[str, Any], pkt_size_kb: float) -> str:
    lines = [
        f"# {meta['index']}. {spec['item_name']}",
        "",
        f"- **Phân nhóm:** {meta['category_group']}",
        f"- **File Subassembly (.pkt) độc lập:** `{meta['pkt_name']}` ({pkt_size_kb:.1f} KB)",
        f"- **Tài liệu hướng dẫn HTML:** `{meta['html_file']}`",
        f"- **Hình minh họa:** `{Path(meta['image_file']).name}`",
        f"- **.NET Class:** `{spec['dotnet_class']}`",
        f"- **Đơn vị:** `{spec['units']}`",
        "",
        "## 1. Mô tả chức năng",
        "",
        spec["description"],
        "",
        f"## 2. Danh sách Tham số đầu vào ({spec['parameter_count']} Parameters)",
        "",
        "| STT | Tên biến (`Name`) | Tên hiển thị (`DisplayName`) | Kiểu | Mặc định | Tùy chọn Enum / Giải thích |",
        "| :-: | :--- | :--- | :---: | :---: | :--- |",
    ]

    for idx, p in enumerate(spec["parameters"], start=1):
        enum_str = ""
        if p["enum_options"]:
            opts = [f"`{e['value']}`={e['display_name']}" for e in p["enum_options"]]
            enum_str = "**Enum:** " + ", ".join(opts) + ". "
        desc_clean = re.sub(r"\s+", " ", p["description"]).strip()
        lines.append(
            f"| {idx} | `{p['name']}` | {p['display_name']} | `{p['data_type']}` | `{p['default_value']}` | {enum_str}{desc_clean} |"
        )

    if doc_info.get("sections"):
        lines.extend(
            [
                "",
                "## 3. Cấu trúc mục lục trong file HTML Hướng dẫn",
                "",
            ]
        )
        for sec in doc_info["sections"]:
            lines.append(f"- {sec}")

    return "\n".join(lines) + "\n"


def main() -> None:
    sac_vi_path = SUB_DIR / "SACVisualInfra.pkt"
    if not sac_vi_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {sac_vi_path}")

    OUTPUT_SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    orig_size_mb = sac_vi_path.stat().st_size / (1024 * 1024)
    print(f"Đang đọc gói gốc: {sac_vi_path.name} ({orig_size_mb:.2f} MB)...")

    summary_catalog: List[Dict[str, Any]] = []

    with zipfile.ZipFile(sac_vi_path, "r") as zf:
        dll_bytes = zf.read("SACVisualInfra.dll")
        atc_bytes = zf.read("SACVisualInfra.atc")
        palette_root = etree.fromstring(atc_bytes)

        header_tools = palette_root.xpath("//Tool[ToolType!='1']")
        sub_tools = palette_root.xpath("//Tool[ToolType='1']")

        for tool_el in sub_tools:
            cls_name = (tool_el.findtext(".//DotNetClass") or "").strip()
            if cls_name not in TOOL_MAPPING:
                print(f"[Cảnh báo] Bỏ qua class chưa ánh xạ: {cls_name}")
                continue

            meta = TOOL_MAPPING[cls_name]
            part_dir = OUTPUT_SPLIT_DIR / meta["folder"]
            part_dir.mkdir(parents=True, exist_ok=True)

            # 1. Trích xuất thông số từ .atc và .html
            spec = extract_atc_tool_spec(tool_el)
            src_html = SUB_DIR / meta["html_file"]
            doc_info = extract_html_documentation(src_html)

            # 2. Tạo file .atc tối ưu riêng cho Subassembly này
            single_atc_bytes = build_single_tool_atc_bytes(
                original_palette_root=palette_root,
                header_tools=header_tools,
                target_tool_el=tool_el,
                help_filename=meta["html_file"],
            )

            # 3. Đọc duy nhất 1 ảnh icon của Subassembly này từ gói gốc
            img_arcname = meta["image_file"]
            img_bytes = zf.read(img_arcname)

            # 4. Đóng gói file .pkt độc lập đã tối ưu (nén LZMA/DEFLATED tối đa, loại bỏ 6 ảnh thừa)
            out_pkt_path = part_dir / meta["pkt_name"]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out_zf:
                out_zf.writestr("[Content_Types].xml", build_content_types_for_visual_infra())
                out_zf.writestr("SACVisualInfra.atc", single_atc_bytes)
                out_zf.writestr("SACVisualInfra.dll", dll_bytes)
                out_zf.writestr(img_arcname, img_bytes)
                if src_html.exists():
                    out_zf.writestr(meta["html_file"], src_html.read_bytes())

            out_pkt_path.write_bytes(buf.getvalue())
            pkt_size_kb = out_pkt_path.stat().st_size / 1024.0

            # 4b. Tạo thêm bản Pure SAC Flowchart (.xaml) siêu nhẹ (~5 KB) nạp sẵn toàn bộ Parameters
            # để có thể mở trực tiếp trong phần mềm Autodesk Subassembly Composer!
            sac_editable_name = f"SAC_{meta['index']}_{meta['short_code']}_Flowchart.pkt"
            sac_editable_path = part_dir / sac_editable_name
            create_pkt_from_template(
                output_path=str(sac_editable_path),
                subassembly_name=meta["short_code"],
                description=spec["description"].splitlines()[0] if spec["description"] else spec["item_name"],
                civil_version="2026",
            )
            for p in spec["parameters"]:
                if p["name"] == "Side":
                    continue
                sac_dt = "Double"
                if p["data_type"] == "long":
                    sac_dt = "Integer"
                elif p["data_type"] == "string":
                    sac_dt = "String"
                elif p["type_info"] == "9":
                    sac_dt = "Grade"
                elif p["type_info"] == "10":
                    sac_dt = "Slope"
                add_parameter(
                    pkt_path=str(sac_editable_path),
                    name=p["name"],
                    param_category="Input",
                    data_type=sac_dt,
                    default_value=p["default_value"] or "0",
                    display_name=p["display_name"],
                    description=p["description"],
                )
            sac_editable_kb = sac_editable_path.stat().st_size / 1024.0

            # 5. Sao chép file HTML, xuất ảnh PNG riêng và lưu spec.json + README.md vào thư mục phần đó
            if src_html.exists():
                shutil.copy2(src_html, part_dir / meta["html_file"])
            (part_dir / Path(img_arcname).name).write_bytes(img_bytes)

            full_spec_payload = {
                "index": meta["index"],
                "short_code": meta["short_code"],
                "category_group": meta["category_group"],
                "pkt_file": meta["pkt_name"],
                "pkt_size_kb": round(pkt_size_kb, 2),
                "sac_editable_flowchart_pkt": sac_editable_name,
                "sac_editable_size_kb": round(sac_editable_kb, 2),
                "html_help_file": meta["html_file"],
                "image_file": Path(img_arcname).name,
                "atc_specification": spec,
                "html_documentation": doc_info,
            }
            (part_dir / "spec.json").write_text(
                json.dumps(full_spec_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (part_dir / "README.md").write_text(
                build_part_readme(meta, spec, doc_info, pkt_size_kb),
                encoding="utf-8",
            )

            summary_catalog.append(
                {
                    "index": meta["index"],
                    "folder": meta["folder"],
                    "subassembly_name": spec["item_name"],
                    "short_code": meta["short_code"],
                    "category_group": meta["category_group"],
                    "dotnet_class": spec["dotnet_class"],
                    "pkt_path": str(out_pkt_path),
                    "pkt_size_kb": round(pkt_size_kb, 2),
                    "sac_editable_pkt_path": str(sac_editable_path),
                    "sac_editable_size_kb": round(sac_editable_kb, 2),
                    "image_size_kb": round(len(img_bytes) / 1024.0, 2),
                    "html_file": meta["html_file"],
                    "parameter_count": spec["parameter_count"],
                    "parameter_names": [p["name"] for p in spec["parameters"]],
                }
            )
            print(
                f"  + [{meta['index']}] Đã tách riêng: {meta['folder']}/\n"
                f"      - Gói Civil 3D (.dll) : {meta['pkt_name']} ({pkt_size_kb / 1024:.2f} MB)\n"
                f"      - Gói mở SAC (.xaml)  : {sac_editable_name} ({sac_editable_kb:.1f} KB | {spec['parameter_count']} params)\n"
                f"      - Tài liệu & Đặc tả   : {meta['html_file']} + spec.json + README.md"
            )

    # Lưu bảng tổng hợp catalog của cả 7 Subassembly
    catalog_path = OUTPUT_SPLIT_DIR / "visual_infra_catalog.json"
    catalog_path.write_text(
        json.dumps(summary_catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nHoàn tất! Đã lưu danh mục tổng hợp tại: {catalog_path}")


if __name__ == "__main__":
    main()
