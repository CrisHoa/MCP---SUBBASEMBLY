"""
SAC MCP Server (sac-mcp-server)
Model Context Protocol Server chuyên dụng cho Autodesk Civil 3D Subassembly Composer (2025 - 2027).

Nhóm công cụ (23 tool):
  - Đọc / tra cứu: inspect_pkt, validate_pkt_native, get_sac_reference_and_formulas,
    list_examples_and_split_catalog
  - Tạo mới: create_pkt_from_template, generate_assembly_recipe
  - Sửa file - hình học: add_parameter, add_point_and_link, add_link, add_curve, add_fillet_arc,
    add_offset_geometry, add_loop_geometry, add_intersection_point, add_strip_surface, add_shape,
    add_get_mark_point, add_set_mark_point
  - Sửa file - logic: add_flow_decision, add_define_variable, add_set_variable,
    add_set_output_parameter, add_report_message
"""

from __future__ import annotations

import functools
import json
import os
import zipfile
from pathlib import Path
from typing import Callable, List, Literal, Optional, Tuple

from lxml import etree

try:
    from mcp.server.mcpserver import MCPServer as _MCPServerClass
except ImportError:
    from mcp.server.fastmcp import FastMCP as _MCPServerClass


from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.knowledge_base import (
    NAMING_CONVENTIONS,
    SAC_API_REFERENCE,
    SAC_TOOLBOX_CATALOG,
    build_superelevation_slope_expression,
)
from sac_mcp.core.opc_package import PktPackage, PktValidationError
from sac_mcp.core.recipes import create_highway_lane_assembly, create_urban_road_assembly
from sac_mcp.core.version_manager import VersionManager
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ErrorResult,
    InspectPktResult,
    MutationResult,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
    ReportMessageType,
)

mcp = _MCPServerClass(
    "sac-mcp-server",
    instructions=(
        "MCP Server chuyên thiết kế, giải phẫu và tự động hóa file Subassembly (.pkt) "
        "cho Autodesk Civil 3D phiên bản 2025, 2026, 2027. "
        "Mọi tool sửa file đều kiểm định Tầng 1+2 trước khi ghi; nếu lỗi, file gốc giữ nguyên "
        "và kết quả trả về success=false. Bản sao lưu trước mỗi lần sửa nằm ở '<tên>.pkt.bak'. "
        "parent_node_id nhận '__ReferenceIDn' (FlowStep) hoặc '__ReferenceIDn:True' / ':False' (FlowDecision); "
        "bỏ trống để nối vào MỌI đầu ra đang mở của luồng (các nhánh hội tụ). "
        "Rẽ nhánh: add_flow_decision trả reference id D; đặt khối đầu nhánh bằng parent_node_id='D:True' / 'D:False', "
        "các khối sau trong nhánh dùng reference id của khối liền trước. "
        "Kết quả có 'warnings' (Tầng 2 mới phát sinh + Tầng 3 DLL gốc) - hãy đọc và sửa nếu có."
    ),
)


def _error_json(action: str, pkt_path: Optional[str], exc: Exception) -> str:
    """Chuyển exception thành JSON lỗi có cấu trúc để LLM đọc và tự sửa tham số."""
    hint: Optional[str] = None
    issues: list[dict] = []
    if isinstance(exc, PktValidationError):
        hint = "Kiểm tra lại biểu thức / tên đối tượng vừa truyền vào. File gốc không bị thay đổi."
        issues = [
            {"severity": i.severity, "category": i.category, "message": i.message, "location": i.location}
            for i in exc.issues
        ]
    elif isinstance(exc, FileNotFoundError):
        hint = "Kiểm tra lại đường dẫn (nên dùng đường dẫn tuyệt đối)."
    elif isinstance(exc, zipfile.BadZipFile):
        hint = "File không phải gói .pkt (ZIP/OPC) hợp lệ."
    elif isinstance(exc, etree.XMLSyntaxError):
        hint = "Nội dung XML/XAML trong gói .pkt bị hỏng."
    res = ErrorResult(
        action=action,
        pkt_path=pkt_path,
        error_type=type(exc).__name__,
        message=str(exc),
        hint=hint,
        issues=issues,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


def _safe_tool(action: str):
    """Decorator: bắt mọi exception của tool đọc/tạo mới và trả JSON lỗi có cấu trúc."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                path = kwargs.get("pkt_path") or kwargs.get("output_path") or (args[0] if args else None)
                return _error_json(action, str(path) if path is not None else None, exc)

        return wrapper

    return deco


MutationFn = Callable[[PktPackage, FlowchartEngine], Tuple[dict, str, List[Optional[str]]]]


NATIVE_ON_SAVE_ENV = "SAC_MCP_NATIVE_ON_SAVE"


def _native_warnings(pkt_path: Path) -> List[str]:
    """
    Chạy Tầng 3 (biên dịch VB bằng DLL gốc) sau khi lưu và trả lỗi dưới dạng cảnh báo.
    Không chặn thao tác: khi dựng dần từng bước, việc tạm tham chiếu Parameter chưa thêm là bình thường.
    Tắt bằng biến môi trường SAC_MCP_NATIVE_ON_SAVE=0.
    """
    if os.environ.get(NATIVE_ON_SAVE_ENV, "1") == "0":
        return []
    from sac_mcp.core.validator import PktValidator

    rep = PktValidator.validate_pkt(pkt_path, run_native_test=True)
    return [
        f"Tầng 3 [{i.category}]: {i.message}"
        for i in rep.issues
        if i.severity == "ERROR" and (i.category.startswith("NATIVE") or i.category == "VB_EXPRESSION")
    ]


# Thuộc tính ĐỊNH NGHĨA tên hình học trong các activity của SAC (theo activity_catalog.json).
# SetMarkPointActivity.PointNumber chỉ THAM CHIẾU Point có sẵn nên không tính.
_GEOMETRY_NAME_ATTRS = (
    "PointNumber", "LinkNumber", "ShapeNumber", "LoopNumber", "OffsetNumber",
    "StartPointName", "EndPointName",
)
_NAME_REFERENCE_ONLY = {"SetMarkPointActivity"}


def _existing_geometry_names(engine: FlowchartEngine) -> dict:
    """{tên: activity} của mọi Point / Link / Curve / Shape / Loop / Offset đã định nghĩa trong Flowchart."""
    names: dict = {}
    flowchart = engine.get_flowchart_element()
    for el in flowchart.iter(etree.Element):
        local = etree.QName(el).localname
        if "." in local or local in _NAME_REFERENCE_ONLY:
            continue
        for attr in _GEOMETRY_NAME_ATTRS:
            val = (el.get(attr) or "").strip()
            if val and not val.startswith("{") and not val.startswith("["):
                names.setdefault(val, local)
        if el.get("AutoLink") == "True":
            val = (el.get("AutoLinkGeometryName") or "").strip()
            if val and not val.startswith("{"):
                names.setdefault(val, local)
    return names


def _guard_new_names(engine: FlowchartEngine, new_names: List[Optional[str]], allow_duplicate_name: bool) -> None:
    """
    Chặn tạo trùng tên hình học (Point / Link / Shape / Loop / Offset) - dùng chung cho mọi tool tạo hình học.
    allow_duplicate_name=True chỉ dùng khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ
    (VD: nhánh Đào và nhánh Đắp cùng tạo 'P5' / 'L5').
    """
    wanted = [n.strip() for n in new_names if n and n.strip()]
    dup_in_call = sorted({n for n in wanted if wanted.count(n) > 1})
    if dup_in_call:
        raise ValueError(f"Tên hình học bị lặp trong cùng một lệnh: {dup_in_call}.")
    if allow_duplicate_name:
        return
    existing = _existing_geometry_names(engine)
    clash = [f"'{n}' (đã có trong {existing[n]})" for n in wanted if n in existing]
    if clash:
        raise ValueError(
            f"Tên đã tồn tại trong file: {', '.join(clash)}. Chọn tên khác; chỉ dùng "
            "allow_duplicate_name=True khi tạo lại tên này ở nhánh FlowDecision loại trừ."
        )


def _static_warning_set(xaml_text: str) -> List[Tuple[str, str]]:
    """Các WARNING Tầng 2 (ngữ nghĩa tĩnh: GEOMETRY_REFERENCE, FLOW_UNREACHABLE...) của một XAML."""
    from sac_mcp.core.semantic_checks import check_semantics

    try:
        return [(i.category, i.message) for i in check_semantics(xaml_text) if i.severity == "WARNING"]
    except Exception:
        return []


def _new_static_warnings(before_xaml: str, after_xaml: str) -> List[str]:
    """
    Chỉ trả các WARNING Tầng 2 MỚI phát sinh do lần sửa này (so với file trước khi sửa),
    để cảnh báo sẵn có trong file thật không lặp lại ở mọi lần gọi tool.
    """
    before = set(_static_warning_set(before_xaml))
    out: List[str] = []
    for cat, msg in _static_warning_set(after_xaml):
        if (cat, msg) not in before:
            line = f"Tầng 2 [{cat}]: {msg}"
            if line not in out:
                out.append(line)
    return out


def _mutate_pkt(action: str, pkt_path: str, fn: MutationFn) -> str:
    """
    Khung chung cho mọi tool sửa file .pkt:
    mở gói -> sửa XAML -> kiểm định Tầng 1+2 -> sao lưu .bak -> ghi nguyên tử
    -> chạy Tầng 3 (báo dưới dạng cảnh báo) -> trả JSON.
    `fn(pkg, engine)` trả về (details, message, created_reference_ids).
    """
    try:
        pkg = PktPackage.open(pkt_path)
        original_xaml = pkg.get_xaml_text()
        engine = FlowchartEngine(original_xaml)
        details, message, ref_ids = fn(pkg, engine)
        new_xaml = engine.to_xaml_string()
        pkg.set_xaml_text(new_xaml)
        pkg.save(backup=True, validate=True)
        res = MutationResult(
            success=True,
            pkt_path=str(pkg.pkt_path),
            action=action,
            message=message,
            created_reference_ids=[r for r in ref_ids if r],
            details=details,
            warnings=engine.warnings
            + pkg.warnings
            + _new_static_warnings(original_xaml, new_xaml)
            + _native_warnings(pkg.pkt_path),
            backup_path=str(pkg.last_backup_path) if pkg.last_backup_path else None,
        )
        return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)
    except Exception as exc:
        return _error_json(action, pkt_path, exc)


# ============================================================================
# TOOL 1: inspect_pkt
# ============================================================================
@mcp.tool()
@_safe_tool("inspect_pkt")
def inspect_pkt(
    pkt_path: str,
    include_raw_xaml: bool = False,
) -> str:
    """
    Giải nén và đọc toàn bộ danh sách Parameters, Points, Links, Shapes và cấu trúc
    Flowchart WF4 XAML (hoặc .atc/.dll) của một file .pkt có sẵn.

    Args:
        pkt_path: Đường dẫn tuyệt đối hoặc tương đối tới file .pkt cần phân tích.
        include_raw_xaml: Nếu True, trả kèm toàn bộ mã nguồn Flowchart.xaml gốc.
    """
    pkg = PktPackage.open(pkt_path)
    meta = pkg.get_metadata()
    xaml_filename = pkg.find_xaml_filename()

    if xaml_filename:
        xaml_text = pkg.get_xaml_text()
        engine = FlowchartEngine(xaml_text)
        start_node_id, flow_nodes = engine.extract_flowchart_nodes()
        params = engine.extract_parameters()
        points = engine.extract_points()
        links = engine.extract_links()
        shapes = engine.extract_shapes()
    else:
        # Trường hợp gói .pkt biên dịch bằng .NET .dll (như SACVisualInfra.pkt)
        xaml_text = None
        start_node_id = None
        flow_nodes = []
        params = pkg.extract_atc_parameters()
        points = []
        links = []
        shapes = []

    result = InspectPktResult(
        pkt_path=str(pkg.pkt_path),
        subassembly_name=meta["subassembly_name"],
        description=meta["description"],
        detected_civil_version=meta["detected_civil_version"],
        packet_version_tag=meta["packet_version_tag"],
        xaml_file_name=xaml_filename or (pkg.find_atc_filename() or "Compiled_DLL_Package"),
        opc_files=pkg.list_opc_files(),
        start_node_id=start_node_id,
        parameters=params,
        points=points,
        links=links,
        shapes=shapes,
        flowchart_nodes=flow_nodes,
        raw_xaml=xaml_text if include_raw_xaml else None,
    )
    return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)


# ============================================================================
# TOOL 2: create_pkt_from_template
# ============================================================================
@mcp.tool()
@_safe_tool("create_pkt_from_template")
def create_pkt_from_template(
    output_path: str,
    subassembly_name: str,
    description: str = "",
    civil_version: Literal["2025", "2026", "2027"] = "2025",
    custom_template_path: Optional[str] = None,
) -> str:
    """
    Tạo một file .pkt mới dựa trên file .pkt gốc (Base Template) chuẩn theo phiên bản
    Civil 3D (2025, 2026, 2027) để đảm bảo không bao giờ bị lỗi schema của Autodesk.

    Args:
        output_path: Đường dẫn lưu file .pkt mới (VD: 'C:/output/LaneSubassembly.pkt').
        subassembly_name: Tên hiển thị và Class của Subassembly (tự động chuẩn hóa không dấu cách).
        description: Mô tả chức năng của Subassembly.
        civil_version: Phiên bản Civil 3D mục tiêu ('2025', '2026', hoặc '2027').
        custom_template_path: (Tùy chọn) Đường dẫn tới file .pkt mẫu riêng của người dùng.
    """
    ver_enum = CivilVersion(civil_version)
    pkg = PktPackage.create_from_template(
        output_path=output_path,
        subassembly_name=subassembly_name,
        description=description,
        civil_version=ver_enum,
        custom_template_path=custom_template_path,
    )
    spec = VersionManager.get_spec(ver_enum)
    safe_name = VersionManager.sanitize_subassembly_name(subassembly_name)

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="create_pkt_from_template",
        message=(
            f"Đã khởi tạo thành công file '{pkg.pkt_path.name}' "
            f"(SubassemblyName='{safe_name}', Civil 3D {civil_version})."
        ),
        created_reference_ids=[],
        details={
            "subassembly_name": safe_name,
            "civil_version": civil_version,
            "product_version": spec.product_version,
            "packet_version": spec.packet_version,
            "dotnet_target": spec.dotnet_target,
            "opc_files": pkg.list_opc_files(),
        },
        warnings=pkg.warnings,
        backup_path=str(pkg.last_backup_path) if pkg.last_backup_path else None,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


# ============================================================================
# TOOL 3: add_parameter
# ============================================================================
@mcp.tool()
def add_parameter(
    pkt_path: str,
    name: str,
    param_category: Literal["Input", "Output", "Target"] = "Input",
    data_type: Literal[
        "Double",
        "Integer",
        "String",
        "Boolean",
        "YesNo",
        "Grade",
        "Slope",
        "Side",
        "Superelevation",
        "SuperelevationAxisOfRotation",
        "SlopeDirection",
        "PotentialPivot",
        "Cant",
        "ElevationTarget",
        "OffsetTarget",
        "SurfaceTarget",
    ] = "Double",
    default_value: str = "0.0",
    display_name: str = "",
    description: str = "",
) -> str:
    """
    Thêm hoặc cập nhật một Input / Output / Target Parameter vào file .pkt.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        name: Tên biến Parameter trong công thức (VD: 'LaneWidth', 'LaneSlope', 'EG_Surface').
        param_category: Phân loại tham số ('Input', 'Output', hoặc 'Target').
        data_type: Kiểu dữ liệu SAC ('Double', 'Slope', 'Grade', 'SurfaceTarget', 'OffsetTarget'...).
        default_value: Giá trị mặc định khi dựng hình trong Preview (VD: '3.5', '-0.02', 'Right').
        display_name: Tên hiển thị trong hộp thoại Properties của Civil 3D.
        description: Mô tả chi tiết ý nghĩa tham số.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        info = ParameterBuilder.add_parameter(
            engine=engine,
            name=name,
            category=ParameterCategory(param_category),
            data_type=ParameterDataType(data_type),
            default_value=default_value,
            display_name=display_name,
            description=description,
        )
        if param_category == "Input":
            pkg.sync_parameter_to_atc(
                name=info["parameter_name"],
                data_type=data_type,
                default_value=default_value,
                display_name=info["display_name"],
                description=description,
            )
        msg = f"Đã thêm {param_category} Parameter '{info['parameter_name']}' ({data_type} = {default_value})."
        return info, msg, []

    return _mutate_pkt("add_parameter", pkt_path, _apply)


# ============================================================================
# TOOL 4: add_point_and_link
# ============================================================================
@mcp.tool()
def add_point_and_link(
    pkt_path: str,
    point_code: str,
    from_point: str = "Origin",
    point_type: Literal[
        "DeltaX_DeltaY",
        "Slope_DeltaX",
        "Slope_DeltaY",
        "Angle_Distance",
        "Slope_To_Surface",
        "Interpolate",
    ] = "DeltaX_DeltaY",
    param_1_expr: str = "0.0",
    param_2_expr: str = "0.0",
    point_codes_str: str = "",
    add_link: Optional[bool] = None,
    link_name: str = "",
    link_codes_str: str = "",
    is_auxiliary: bool = False,
    use_superelevation_formula: bool = False,
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
    allow_duplicate_link: bool = False,
) -> str:
    """
    Thêm Point hoặc Auxiliary Point (P1, P2... hoặc AP1, AP2...) theo Delta X & Delta Y,
    Slope & Delta X, Slope to Surface... và (tùy chọn) nối Link từ from_point tới Point mới.

    Ý nghĩa param_1_expr / param_2_expr theo point_type:
      - 'DeltaX_DeltaY'   : DeltaX (m)          / DeltaY (m)
      - 'Slope_DeltaX'    : Slope (VD -0.02)    / DeltaX (m)
      - 'Slope_DeltaY'    : Slope               / DeltaY (m)
      - 'Angle_Distance'  : Góc (độ)            / Khoảng cách (m)
      - 'Slope_To_Surface': Slope               / TÊN Target Parameter kiểu SurfaceTarget (VD 'EG');
                            phải add_parameter(param_category='Target', data_type='SurfaceTarget') trước.
      - 'Interpolate'     : TÊN Point đích (VD 'P5') / tỉ lệ nội suy từ from_point tới Point đích
                            (0 = trùng from_point, 1 = trùng Point đích, VD 0.5 = trung điểm).
    Số được giữ nguyên, biến/biểu thức tự bọc [...].

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        point_code: Mã Point (VD: 'P1', 'P2' hoặc 'AP1' nếu is_auxiliary=True). Không được trùng tên đã có.
        from_point: Điểm tham chiếu bắt đầu (VD: 'Origin', 'P1', 'AP1').
        point_type: Phương thức xác định điểm (xem bảng trên).
        param_1_expr: Tham số 1 theo point_type (xem bảng trên).
        param_2_expr: Tham số 2 theo point_type (xem bảng trên).
        point_codes_str: Chuỗi Code cho Point trong Civil 3D (VD: '\"Crown\"' hoặc '\"ETW\"').
        add_link: Bỏ trống (mặc định) = tạo Link khi và chỉ khi có link_name. True bắt buộc kèm link_name;
                  False = chỉ tạo Point dù có link_name.
        link_name: Mã Link nối from_point -> point_code (VD: 'L1' hoặc 'AL1' cho điểm phụ).
                   Không được trùng tên đã có (tool trả lỗi thay vì âm thầm tạo Link trùng).
        link_codes_str: Chuỗi Code cho Link (VD: '\"Top\", \"Pave\"').
        is_auxiliary: Nếu True, tạo phần tử phụ trợ Auxiliary Point / Auxiliary Link (AP/AL).
        use_superelevation_formula: Nếu True và point_type là Slope_DeltaX / Slope_DeltaY / Slope_To_Surface,
                                    tự động điền công thức quay siêu cao 8 nhánh chuẩn vào param_1_expr
                                    với biến độ dốc mặc định lấy từ param_1_expr (VD: 'LaneSlope').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha. Nếu bỏ trống sẽ tự nối vào cuối Flowchart.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên Point/Link ở nhánh FlowDecision loại trừ
                              (VD: nhánh Đào và nhánh Đắp cùng tạo 'P5' & 'L5').
        allow_duplicate_link: Bí danh cũ của allow_duplicate_name (giữ để tương thích).
    """
    lname = (link_name or "").strip()
    do_link = bool(lname) if add_link is None else bool(add_link)
    allow_dup = allow_duplicate_name or allow_duplicate_link
    actual_param_1 = param_1_expr
    if use_superelevation_formula and point_type in (
        "Slope_DeltaX",
        "Slope_DeltaY",
        "Slope_To_Surface",
    ):
        fallback_var = param_1_expr if param_1_expr and param_1_expr != "0.0" else "LaneSlope"
        actual_param_1 = build_superelevation_slope_expression(fallback_slope_param=fallback_var)

    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        if do_link and not lname:
            raise ValueError(
                "add_link=True nhưng chưa truyền link_name. Truyền link_name (VD: 'L1' / 'AL1') "
                "hoặc bỏ add_link nếu chỉ tạo Point."
            )
        _guard_new_names(engine, [point_code, lname if do_link else None], allow_dup)
        info = GeometryBuilder.add_point_and_link(
            engine=engine,
            point_code=point_code,
            from_point=from_point,
            point_type=PointGeometryType(point_type),
            param_1_expr=actual_param_1,
            param_2_expr=param_2_expr,
            point_codes_str=point_codes_str,
            add_link=do_link,
            link_name=lname if do_link else "",
            link_codes_str=link_codes_str,
            is_auxiliary=is_auxiliary,
            parent_node_id=parent_node_id,
        )
        kind_str = "Auxiliary Point" if is_auxiliary else "Point"
        msg = (
            f"Đã thêm {kind_str} '{point_code}' (từ {from_point}, kiểu {point_type})"
            + (f" kèm Link '{lname}'" if do_link else "")
            + f" tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_point_and_link", pkt_path, _apply)


# ============================================================================
# TOOL 4B: add_link (Nối Link giữa 2 Point có sẵn để khép kín Shape)
# ============================================================================
@mcp.tool()
def add_link(
    pkt_path: str,
    link_name: str,
    start_point: str,
    end_point: str,
    link_codes_str: str = "",
    apply_aor: bool = False,
    is_auxiliary: bool = False,
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm Link hoặc Auxiliary Link (CreateLink / CreateAuxLink) nối giữa 2 Point có sẵn
    để khép kín hình học Shape (ví dụ: đáy kết cấu, ngoàm chân khay, vách trong...).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        link_name: Tên/Mã Link (VD: 'L7' hoặc 'AL2'). Không được trùng tên hình học đã có.
        start_point: Tên điểm bắt đầu (VD: 'P7').
        end_point: Tên điểm kết thúc (VD: 'P3').
        link_codes_str: Chuỗi mã LinkCode cách nhau bởi dấu phẩy (VD: '"Datum"' hoặc '"Top", "Pave"').
        apply_aor: Có áp dụng siêu cao (Apply AOR) cho Link này không.
        is_auxiliary: True nếu là Link phụ trợ (AL).
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        _guard_new_names(engine, [link_name], allow_duplicate_name)
        info = GeometryBuilder.add_link(
            engine=engine,
            link_name=link_name,
            start_point=start_point,
            end_point=end_point,
            link_codes_str=link_codes_str,
            apply_aor=apply_aor,
            is_auxiliary=is_auxiliary,
            parent_node_id=parent_node_id,
        )
        msg = f"Đã thêm {'AuxLink' if is_auxiliary else 'Link'} '{link_name}' nối từ {start_point} đến {end_point}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_link", pkt_path, _apply)


# ============================================================================
# TOOL BỔ SUNG: add_shape & get_sac_reference_and_formulas (từ tài liệu HOA_C3D)
# ============================================================================
@mcp.tool()
def add_fillet_arc(
    pkt_path: str,
    link_number: str,
    first_link: str,
    second_link: str,
    round_radius: float = 0.05,
    end_point_name: Optional[str] = None,
    link_codes_str: str = "",
    parent_node_id: Optional[str] = None,
    start_point_name: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối bo tròn góc cong Fillet Arc (<asa1:FilletArcActivity>) vào Flowchart.
    Thường dùng bo tròn mượt mà cho gờ mép bó vỉa (bán kính R) hoặc rãnh tam giác.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        link_number: Mã Link cong mới (VD: 'L6').
        first_link: Mã Link phụ trợ đầu tiên tiếp xúc (VD: 'AL1').
        second_link: Mã Link thứ 2 tiếp xúc (bắt buộc, VD: 'AL2').
        round_radius: Bán kính bo cong (m), mặc định 0.05m = 5cm.
        end_point_name: (Tùy chọn) Mã Point tại điểm kết thúc cung tròn (VD: 'P8'); bỏ trống thì tự đặt '<link>_End'.
        link_codes_str: Chuỗi Code gán cho đường cong (VD: '\"Top\", \"Link_Bo DPC\"').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        start_point_name: (Tùy chọn) Mã Point tại điểm đầu cung tròn (VD: 'P7'); bỏ trống thì tự đặt '<link>_Start'.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        if first_link.strip() == (second_link or "").strip():
            raise ValueError("first_link và second_link phải là 2 Link khác nhau.")
        _guard_new_names(engine, [link_number, (start_point_name or f"{link_number.strip()}_Start"), (end_point_name or f"{link_number.strip()}_End")], allow_duplicate_name)
        info = GeometryBuilder.add_fillet_arc(
            engine=engine,
            link_number=link_number,
            first_link=first_link,
            second_link=second_link,
            round_radius=round_radius,
            end_point_name=end_point_name,
            link_codes_str=link_codes_str,
            parent_node_id=parent_node_id,
            start_point_name=start_point_name,
        )
        msg = f"Đã thêm cung bo cong Fillet Arc '{link_number}' (R={round_radius}m) tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_fillet_arc", pkt_path, _apply)


@mcp.tool()
def add_loop_geometry(
    pkt_path: str,
    loop_code: str,
    links: list[str],
    repetition_count: int = 10,
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối vòng lặp hình học (<asa2:CreateLoop>) vào Flowchart.
    Tự động giật cơ / đánh cấp taluy nhiều tầng (L11 mái dốc + L12 bề rộng cơ) khi chiều cao đào/đắp lớn.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        loop_code: Mã vòng lặp (VD: 'LO1').
        links: Danh sách các Link cấu thành một chu kỳ lặp (VD: ['L11', 'L12']).
        repetition_count: Số lần lặp tối đa (mặc định 10).
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        _guard_new_names(engine, [loop_code], allow_duplicate_name)
        info = GeometryBuilder.add_loop_geometry(
            engine=engine,
            loop_code=loop_code,
            links=links,
            repetition_count=repetition_count,
            parent_node_id=parent_node_id,
        )
        msg = (
            f"Đã thêm vòng lặp CreateLoop '{loop_code}' (Links={links}, max={repetition_count}) "
            f"tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_loop_geometry", pkt_path, _apply)


@mcp.tool()
def add_intersection_point(
    pkt_path: str,
    point_code: str,
    link1: str,
    link2: str,
    is_auxiliary: bool = False,
    point_codes_str: str = "",
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối tạo giao điểm giữa 2 Link (<LinkIntersection> hoặc <AuxIntersection>).
    Dùng để tìm giao điểm cắt gọt đáy móng áo đường với địa hình tự nhiên hoặc bù vênh mặt đường cũ.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        point_code: Mã điểm giao cắt (VD: 'P5' hoặc 'AP3' nếu is_auxiliary=True).
        link1: Mã Link thứ nhất (VD: 'L13' hoặc 'AL1').
        link2: Mã Link thứ hai (VD: 'L_EG' hoặc 'AL2').
        is_auxiliary: Nếu True, tạo điểm phụ trợ AuxIntersection (AP).
        point_codes_str: (Tùy chọn) Chuỗi Code cho Point trong Civil 3D.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        _guard_new_names(engine, [point_code], allow_duplicate_name)
        info = GeometryBuilder.add_intersection_point(
            engine=engine,
            point_code=point_code,
            link1=link1,
            link2=link2,
            is_auxiliary=is_auxiliary,
            point_codes_str=point_codes_str,
            parent_node_id=parent_node_id,
        )
        kind = "AuxIntersection (AP)" if is_auxiliary else "LinkIntersection (P)"
        msg = f"Đã thêm điểm giao cắt {kind} '{point_code}' giữa ({link1} x {link2}) tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_intersection_point", pkt_path, _apply)


@mcp.tool()
def add_strip_surface(
    pkt_path: str,
    display_name: str,
    depth_expr: str,
    end_point_name: str,
    end_offset: float = -5.0,
    end_offset_target: Optional[str] = None,
    link_codes_str: str = "Link_VHC",
    parent_node_id: Optional[str] = None,
    surface_target: str = "EG",
    start_point_name: Optional[str] = None,
    start_offset: Optional[str] = None,
    link_number: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối bóc hữu cơ / bề mặt (<asa2:StripSurfaceActivity>).
    Tự động bóc tách bề mặt địa hình tự nhiên theo chiều sâu quy định (VD: H_VHC = 0.3m).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        display_name: Tên hiển thị của khối (VD: 'P35&L36&P36').
        depth_expr: Biểu thức chiều sâu bóc hữu cơ (VD: 'H_VHC' hoặc '0.3').
        end_point_name: Tên Point kết thúc dải bóc tách (VD: 'P35').
        end_offset: Khoảng cách offset kết thúc (m, mặc định -5.0m).
        end_offset_target: (Tùy chọn) Biến Target offset giới hạn (VD: 'Offset_Tim_Tuyen').
        link_codes_str: Chuỗi Link Code gán cho đáy lớp bóc hữu cơ (mặc định 'Link_VHC').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        surface_target: Tên Target Parameter kiểu SurfaceTarget của bề mặt cần bóc (mặc định 'EG').
        start_point_name: (Tùy chọn) Tên Point tại đầu dải bóc (VD: 'P36').
        start_offset: (Tùy chọn) Offset bắt đầu, số hoặc biểu thức (VD: 'P32.X').
        link_number: (Tùy chọn) Mã Link đáy lớp bóc (VD: 'L36').
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        # StripSurface TẠO MỚI 2 Point + 1 Link (đối chiếu Dam.pkt, ShoulderBacking.pkt của Autodesk).
        # Trùng tên chỉ cảnh báo (không chặn) để giữ tương thích các file / script cũ.
        try:
            _guard_new_names(engine, [end_point_name, start_point_name, link_number], allow_duplicate_name)
        except ValueError as exc:
            engine.warnings.append(f"StripSurface: {exc} StripSurface tạo Point/Link MỚI, nên đặt tên chưa dùng.")
        info = GeometryBuilder.add_strip_surface(
            engine=engine,
            display_name=display_name,
            depth_expr=depth_expr,
            end_point_name=end_point_name,
            end_offset=end_offset,
            end_offset_target=end_offset_target,
            link_codes_str=link_codes_str,
            parent_node_id=parent_node_id,
            surface_target=surface_target,
            start_point_name=start_point_name,
            start_offset=start_offset,
            link_number=link_number,
        )
        msg = (
            f"Đã thêm khối bóc hữu cơ StripSurface '{display_name}' (Depth={depth_expr}) "
            f"tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_strip_surface", pkt_path, _apply)


@mcp.tool()
def add_shape(
    pkt_path: str,
    shape_code: str,
    link_names: list[str],
    shape_codes_str: str = "",
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối Shape (S1, S2...) tạo diện tích khép kín từ danh sách các Link
    để tính khối lượng thể tích theo chiều dài L trong Civil 3D.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        shape_code: Mã Shape (VD: 'S1', 'S2').
        link_names: Danh sách mã các Link bao quanh Shape (VD: ['L1', 'L2', 'L3', 'L4']).
        shape_codes_str: Chuỗi Code cho Shape trong Civil 3D (VD: '\"Pave1\"', '\"Base\"').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        _guard_new_names(engine, [shape_code], allow_duplicate_name)
        info = GeometryBuilder.add_shape(
            engine=engine,
            shape_code=shape_code,
            link_names=link_names,
            shape_codes_str=shape_codes_str,
            parent_node_id=parent_node_id,
        )
        msg = f"Đã thêm Shape '{shape_code}' từ các Link {link_names} tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_shape", pkt_path, _apply)


@mcp.tool()
@_safe_tool("get_sac_reference_and_formulas")
def get_sac_reference_and_formulas(
    topic: Literal[
        "all",
        "toolbox",
        "naming_and_defaults",
        "superelevation_formula",
        "math_and_logic_expressions",
        "api_functions",
    ] = "all",
    fallback_slope_param: str = "LaneSlope",
) -> str:
    """
    Tra cứu cơ sở tri thức Subassembly Composer (Toolbox, Quy định đặt tên biến H_/B_/i_,
    Công thức quay siêu cao 8 nhánh, các hàm VB Math/Logic và API P1/L1/Target/Baseline).

    Args:
        topic: Chủ đề cần tra cứu ('all', 'toolbox', 'naming_and_defaults',
               'superelevation_formula', 'math_and_logic_expressions', 'api_functions').
        fallback_slope_param: Tên biến độ dốc mặc định để điền vào cuối công thức quay siêu cao.
    """
    se_formula = build_superelevation_slope_expression(fallback_slope_param=fallback_slope_param)
    payload = {}
    if topic in ("all", "toolbox"):
        payload["toolbox_catalog"] = SAC_TOOLBOX_CATALOG
    if topic in ("all", "naming_and_defaults"):
        payload["naming_conventions"] = NAMING_CONVENTIONS
    if topic in ("all", "superelevation_formula"):
        payload["superelevation_slope_expression"] = se_formula
    if topic in ("all", "math_and_logic_expressions"):
        payload["math_expressions"] = SAC_API_REFERENCE["Math_Expressions"]
        payload["logic_expressions"] = SAC_API_REFERENCE["Logic_Expressions"]
    if topic in ("all", "api_functions"):
        payload["point_api"] = SAC_API_REFERENCE["Point_And_AuxiliaryPoint_API"]
        payload["link_api"] = SAC_API_REFERENCE["Link_And_AuxiliaryLink_API"]
        payload["targets_api"] = SAC_API_REFERENCE["Targets_API"]
        payload["baseline_and_enum_api"] = SAC_API_REFERENCE["Baseline_And_Enum_API"]

    return json.dumps(payload, ensure_ascii=False, indent=2)


# ============================================================================
# TOOL 5: add_report_message
# ============================================================================
@mcp.tool()
def add_report_message(
    pkt_path: str,
    message_expr: str,
    message_type: Literal["Informational", "Information", "Warning", "Error"] = "Warning",
    condition_expr: Optional[str] = None,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Thêm khối Report Message (hoặc kết hợp biểu thức điều kiện Decision -> Report Message)
    vào Flowchart của file .pkt.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        message_expr: Biểu thức chuỗi VB.NET cần thông báo (VD: '\"Chiều rộng làn <= 0!\"').
        message_type: Cấp độ thông báo trên Event Viewer ('Informational', 'Warning', 'Error');
                      'Information' được chấp nhận như bí danh của 'Informational'.
        condition_expr: (Tùy chọn) Biểu thức điều kiện VB.NET (VD: 'LaneWidth <= 0'). Nếu truyền vào,
                        công cụ sẽ tự động sinh một khối <FlowDecision> và nối nhánh True vào ReportMessage.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha cần nối vào.
    """
    level = "Informational" if message_type == "Information" else message_type

    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        info = LogicBuilder.add_report_message(
            engine=engine,
            message_expr=message_expr,
            message_type=ReportMessageType(level),
            condition_expr=condition_expr,
            parent_node_id=parent_node_id,
        )
        msg = (
            f"Đã thêm khối ReportMessage ({level})"
            + (
                f" kèm điều kiện Decision '{condition_expr}' (nhánh False và sau ReportMessage cùng đi tiếp)"
                if condition_expr
                else ""
            )
            + "."
        )
        return info, msg, info["created_reference_ids"]

    return _mutate_pkt("add_report_message", pkt_path, _apply)


# ============================================================================
# NHÓM TOOL ACTIVITY BỔ SUNG: Curve, Offset, Mark Point, Biến, Output, FlowDecision
# ============================================================================
@mcp.tool()
def add_curve(
    pkt_path: str,
    link_number: str,
    start_point: str,
    end_point: str,
    creation_type: Literal["ArcGeneral", "Arc3Points", "ParabolaGeneral"] = "ArcGeneral",
    center_point: Optional[str] = None,
    arc_point: Optional[str] = None,
    mid_ordinate_expr: Optional[str] = None,
    num_increments: int = 8,
    link_codes_str: str = "",
    is_auxiliary: bool = False,
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm Link cong (<CreateCurve> hoặc <CreateAuxCurve>) nối 2 Point có sẵn bằng cung tròn / parabol.
    Dùng cho đáy cống tròn, rãnh hình cung, mui luyện, gờ bó vỉa cong...

    Mỗi kiểu cung cần ĐÚNG MỘT đối số phụ (thiếu thì SAC báo lỗi khi chạy):
      - 'ArcGeneral'      : cung tròn qua tâm -> bắt buộc center_point (Point tâm, VD 'AP1').
      - 'Arc3Points'      : cung tròn qua 3 điểm -> bắt buộc arc_point (Point thứ 2 nằm trên cung, VD 'P5').
      - 'ParabolaGeneral' : parabol -> bắt buộc mid_ordinate_expr (tung độ giữa dây cung, VD '0.15' hoặc 'H_Vong').

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        link_number: Mã Link cong mới (VD: 'L10' hoặc 'AL3' nếu is_auxiliary=True).
        start_point: Point đầu cung (đã tạo trước, VD: 'P14').
        end_point: Point cuối cung (đã tạo trước, VD: 'P13').
        creation_type: Kiểu cung ('ArcGeneral', 'Arc3Points', 'ParabolaGeneral').
        center_point: Point tâm cung - chỉ dùng cho 'ArcGeneral'.
        arc_point: Point thứ 2 trên cung - chỉ dùng cho 'Arc3Points'.
        mid_ordinate_expr: Tung độ giữa (số hoặc biểu thức VB) - chỉ dùng cho 'ParabolaGeneral'.
        num_increments: Số đoạn thẳng chia nhỏ để xấp xỉ đường cong (NoIncrements, mặc định 8).
        link_codes_str: Chuỗi Link Code cách nhau dấu phẩy (VD: '\"Pipe\"' hoặc '\"Top\", \"Ditch\"').
        is_auxiliary: True để tạo Auxiliary Curve (CreateAuxCurve, không xuất sang Civil 3D).
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    required = {
        "ArcGeneral": ("center_point", center_point),
        "Arc3Points": ("arc_point", arc_point),
        "ParabolaGeneral": ("mid_ordinate_expr", mid_ordinate_expr),
    }[creation_type]

    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        if not (required[1] and str(required[1]).strip()):
            raise ValueError(f"creation_type='{creation_type}' bắt buộc truyền {required[0]}.")
        if num_increments < 1:
            raise ValueError("num_increments phải >= 1.")
        _guard_new_names(engine, [link_number], allow_duplicate_name)
        info = GeometryBuilder.add_curve(
            engine=engine,
            link_number=link_number,
            start_point=start_point,
            end_point=end_point,
            center_point=center_point if creation_type == "ArcGeneral" else None,
            arc_point=arc_point if creation_type == "Arc3Points" else None,
            mid_ordinate_expr=mid_ordinate_expr if creation_type == "ParabolaGeneral" else None,
            creation_type=creation_type,
            num_increments=num_increments,
            link_codes_str=link_codes_str,
            is_auxiliary=is_auxiliary,
            parent_node_id=parent_node_id,
        )
        kind = "AuxCurve" if is_auxiliary else "Curve"
        msg = (
            f"Đã thêm {kind} '{link_number}' ({creation_type}) từ {start_point} đến {end_point} "
            f"tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_curve", pkt_path, _apply)


@mcp.tool()
def add_offset_geometry(
    pkt_path: str,
    offset_code: str,
    links: list[str],
    offset_distance: float = 0.15,
    offset_codes_str: str = "",
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm khối Offset (<CreateOffset>): tạo đường song song cách một chuỗi Link có sẵn một khoảng cố định
    (VD: đáy lớp móng song song mặt đường, lớp đệm lót dưới đáy cống).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        offset_code: Mã Offset (VD: 'O1').
        links: Danh sách Link liên tiếp tạo thành polyline cần offset (VD: ['L1', 'L2']).
        offset_distance: Khoảng offset (m). Dương/âm quyết định phía offset (VD: -0.15 = xuống dưới 15cm).
        offset_codes_str: Chuỗi Code cho Offset cách nhau dấu phẩy (VD: '\"SubBase\"').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        clean = [lk.strip() for lk in links if lk and lk.strip()]
        if not clean:
            raise ValueError("links phải có ít nhất 1 mã Link (VD: ['L1']).")
        if any("," in lk for lk in clean):
            raise ValueError("Mỗi phần tử của links là MỘT mã Link, không chứa dấu phẩy.")
        _guard_new_names(engine, [offset_code], allow_duplicate_name)
        info = GeometryBuilder.add_offset_geometry(
            engine=engine,
            offset_code=offset_code,
            links=clean,
            offset_distance=offset_distance,
            offset_codes_str=offset_codes_str,
            parent_node_id=parent_node_id,
        )
        msg = (
            f"Đã thêm Offset '{offset_code}' (Links={clean}, d={offset_distance}m) "
            f"tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_offset_geometry", pkt_path, _apply)


@mcp.tool()
def add_get_mark_point(
    pkt_path: str,
    point_number: str,
    mark_name: str,
    point_codes_str: str = "",
    prev_offset_expr: str = "0",
    prev_delta_elevation_expr: str = "0",
    is_auxiliary: bool = False,
    parent_node_id: Optional[str] = None,
    allow_duplicate_name: bool = False,
) -> str:
    """
    Thêm Point lấy từ Mark Point (<GetMarkPointActivity> / <GetAuxMarkPointActivity>): bắt vào
    điểm đã được một Subassembly khác trong Assembly đánh dấu bằng Set Mark Point.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        point_number: Mã Point mới tạo tại vị trí Mark Point (VD: 'P11' hoặc 'AP2' nếu is_auxiliary=True).
        mark_name: Tên Mark Point cần bắt (VD: 'EdgePoint') hoặc biểu thức chuỗi trong ngoặc vuông (VD: '[MarkPtName]').
        point_codes_str: Chuỗi Point Code cách nhau dấu phẩy (VD: '\"ETW\"').
        prev_offset_expr: Offset (m) của điểm khi Preview trong SAC (chưa có Mark Point thật), số hoặc biểu thức.
        prev_delta_elevation_expr: Chênh cao (m) của điểm khi Preview trong SAC.
        is_auxiliary: True để tạo Auxiliary Point (GetAuxMarkPointActivity).
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
        allow_duplicate_name: True chỉ khi CỐ Ý tạo lại cùng tên ở nhánh FlowDecision loại trừ.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        _guard_new_names(engine, [point_number], allow_duplicate_name)
        info = GeometryBuilder.add_get_mark_point(
            engine=engine,
            point_number=point_number,
            mark_name=mark_name,
            point_codes_str=point_codes_str,
            is_auxiliary=is_auxiliary,
            parent_node_id=parent_node_id,
            prev_offset_expr=prev_offset_expr,
            prev_delta_elevation_expr=prev_delta_elevation_expr,
        )
        msg = f"Đã thêm Point '{point_number}' lấy từ Mark Point '{mark_name}' tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_get_mark_point", pkt_path, _apply)


@mcp.tool()
def add_set_mark_point(
    pkt_path: str,
    point_number: str,
    mark_name: str,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Đánh dấu một Point thành Mark Point (<SetMarkPointActivity>) để Subassembly đặt sau trong Assembly
    bắt vào bằng Get Mark Point (VD: đánh dấu mép làn 'EdgePoint' cho lề / bó vỉa bám theo).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        point_number: Mã Point đã tạo trước đó cần đánh dấu (VD: 'P2').
        mark_name: Tên Mark Point (VD: 'EdgePoint'); phải trùng tên dùng ở add_get_mark_point của Subassembly kia.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        if not point_number.strip() or not mark_name.strip():
            raise ValueError("point_number và mark_name không được để trống.")
        info = LogicBuilder.add_set_mark_point(
            engine=engine,
            point_number=point_number,
            mark_name=mark_name,
            parent_node_id=parent_node_id,
        )
        msg = f"Đã đánh dấu Point '{point_number}' thành Mark Point '{mark_name}' tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_set_mark_point", pkt_path, _apply)


@mcp.tool()
def add_define_variable(
    pkt_path: str,
    variable_name: str,
    variable_type: Literal["Double", "Integer", "String", "YesNo"] = "Double",
    default_value_expr: str = "0.0",
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Khai báo biến nội bộ (<InternalVariableDefine>, mục Define Variable trong SAC) để lưu kết quả trung gian
    và dùng lại trong biểu thức của các khối phía sau.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        variable_name: Tên biến (bắt đầu bằng chữ cái, chỉ gồm chữ/số/'_'; VD: 'Var_H'). Bị từ chối nếu trùng
                       từ khóa VB (Next, If, End, Step...), trùng biến đã khai báo, trùng Parameter
                       hoặc trùng tên Point/Link đã có (VB không phân biệt hoa thường).
        variable_type: Kiểu biến ('Double', 'Integer', 'String', 'YesNo').
        default_value_expr: Giá trị khởi tạo - biểu thức VB (VD: '0.0', 'LaneWidth / 2', '\"Pave\"' cho String,
                            'Yes' / 'No' cho YesNo). Tự bọc [...] nếu chưa có.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        from sac_mcp.core.builders.logic_builder import check_identifier

        name = check_identifier(variable_name, "biến")
        low = name.lower()
        flowchart = engine.get_flowchart_element()
        declared = {
            (v.get("Name") or "").lower()
            for v in flowchart.xpath("./*[local-name()='Flowchart.Variables']/*[local-name()='Variable']")
        } | {
            (el.get("VariableName") or "").lower()
            for el in flowchart.xpath(".//*[local-name()='InternalVariableDefine']")
        }
        if low in declared:
            raise ValueError(
                f"Biến '{name}' đã được khai báo. Dùng add_set_variable để gán giá trị mới."
            )
        params = {
            (p.get("Name") or "").lower()
            for p in engine.root.xpath("./*[local-name()='Members']/*[local-name()='Property']")
        }
        if low in params:
            raise ValueError(f"Tên '{name}' trùng một Parameter đã có (biến sẽ che Parameter). Hãy đặt tên khác.")
        if low in {n.lower() for n in _existing_geometry_names(engine)}:
            raise ValueError(f"Tên '{name}' trùng tên Point/Link/Shape đã có. Hãy đặt tên khác.")
        info = LogicBuilder.add_define_variable(
            engine=engine,
            variable_name=variable_name,
            variable_type=variable_type,
            default_value_expr=default_value_expr,
            parent_node_id=parent_node_id,
        )
        msg = (
            f"Đã khai báo biến '{info['variable_name']}' <{info['variable_type']}> = {info['default_value']} "
            f"tại node {info['reference_id']}."
        )
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_define_variable", pkt_path, _apply)


@mcp.tool()
def add_set_variable(
    pkt_path: str,
    variable_name: str,
    value_expr: str,
    variable_type: Optional[Literal["Double", "Integer", "String", "YesNo"]] = None,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Gán lại giá trị cho biến nội bộ đã khai báo bằng add_define_variable (<SetVariableValue>).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        variable_name: Tên biến đã khai báo (VD: 'Var_H').
        value_expr: Biểu thức VB tính giá trị mới (VD: 'Math.Abs(P2.Y - AP1.Y)'). Tự bọc [...] nếu chưa có.
        variable_type: (Tùy chọn) Kiểu biến; bỏ trống để tự lấy theo khai báo của biến.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        from sac_mcp.core.builders.logic_builder import lookup_declared_type

        if lookup_declared_type(engine, variable_name.strip()) is None:
            raise ValueError(
                f"Biến '{variable_name}' chưa được khai báo. Gọi add_define_variable trước."
            )
        info = LogicBuilder.add_set_variable_value(
            engine=engine,
            variable_name=variable_name,
            value_expr=value_expr,
            variable_type=variable_type,
            parent_node_id=parent_node_id,
        )
        msg = f"Đã gán {info['variable_name']} = {value_expr} tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_set_variable", pkt_path, _apply)


@mcp.tool()
def add_set_output_parameter(
    pkt_path: str,
    parameter_name: str,
    value_expr: str,
    parameter_type: Optional[Literal["Double", "Integer", "String", "Boolean", "YesNo", "Slope", "Grade"]] = None,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Gán giá trị cho Output Parameter (<SetOutputParameterValue>) để Civil 3D / Subassembly khác đọc được
    (VD: xuất chiều cao đào đắp, bề rộng thực tế). Output Parameter phải được tạo trước bằng
    add_parameter(param_category='Output').

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        parameter_name: Tên Output Parameter (VD: 'OutLaneWidth').
        value_expr: Biểu thức VB tính giá trị (VD: 'P11.X - P1.X', 'L1.Slope'). Tự bọc [...] nếu chưa có.
        parameter_type: (Tùy chọn) Kiểu dữ liệu; bỏ trống để tự lấy theo khai báo của Output Parameter.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        name = parameter_name.strip()
        props = engine.root.xpath(
            "./*[local-name()='Members']/*[local-name()='Property' and @Name=$n]", n=name
        )
        if not props:
            raise ValueError(
                f"Chưa có Output Parameter '{name}'. Gọi add_parameter(param_category='Output') trước."
            )
        if not (props[0].get("Type") or "").startswith("OutArgument("):
            raise ValueError(f"Parameter '{name}' không phải Output Parameter (Type={props[0].get('Type')}).")
        info = LogicBuilder.add_set_output_parameter(
            engine=engine,
            parameter_name=name,
            value_expr=value_expr,
            parameter_type=parameter_type,
            parent_node_id=parent_node_id,
        )
        msg = f"Đã gán Output Parameter {name} = {value_expr} tại node {info['reference_id']}."
        return info, msg, [info["reference_id"]]

    return _mutate_pkt("add_set_output_parameter", pkt_path, _apply)


@mcp.tool()
def add_flow_decision(
    pkt_path: str,
    condition_expr: str,
    display_name: str = "",
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Thêm khối rẽ nhánh điều kiện (<FlowDecision>) vào Flowchart. Hai nhánh True / False ban đầu để trống.

    Cách đặt các khối tiếp theo vào từng nhánh (dùng reference id trả về trong
    details.decision_node_id / created_reference_ids[0], ví dụ '__ReferenceID7'):
      - Khối ĐẦU TIÊN của nhánh True : gọi tool khác với parent_node_id='__ReferenceID7:True'.
      - Khối ĐẦU TIÊN của nhánh False: gọi tool khác với parent_node_id='__ReferenceID7:False'.
      - Các khối tiếp theo trong cùng nhánh: parent_node_id = reference id của khối ngay trước trong nhánh đó.
      - Nhánh để trống nghĩa là "không làm gì" và luồng đi tiếp từ nhánh đó.
      - Gọi tool với parent_node_id bỏ trống sẽ nối vào MỌI đầu ra đang mở (cả 2 nhánh hội tụ về khối mới).
        Vì vậy hãy dựng xong nội dung các nhánh bằng parent_node_id tường minh trước khi nối khối hội tụ.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        condition_expr: Biểu thức VB BẮT BUỘC trả về Boolean - phép so sánh / logic (VD: 'AP1.Y < P2.Y',
                        'EG.IsValid', 'Side = Right', 'H > 2 And B < 5'). Một giá trị trần (VD: 'H', '1.5',
                        'P2.Y') không phải Boolean nên bị DLL gốc báo lỗi ở Tầng 3.
        display_name: (Tùy chọn) Tên hiển thị khối trên Flowchart; mặc định 'If (<điều kiện>)'.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha ('__ReferenceIDn' hoặc '__ReferenceIDn:True'/':False').
                        Khi chèn vào giữa luồng, phần luồng phía sau được nối vào CẢ HAI nhánh của Decision mới
                        (luồng cũ chạy tiếp dù điều kiện đúng hay sai); sau đó chèn khối vào từng nhánh như trên.
    """
    def _apply(pkg: PktPackage, engine: FlowchartEngine):
        if not condition_expr or not condition_expr.strip():
            raise ValueError("condition_expr không được để trống.")
        info = LogicBuilder.add_flow_decision(
            engine=engine,
            condition_expr=condition_expr,
            display_name=display_name,
            parent_node_id=parent_node_id,
        )
        ref_id = info["decision_node_id"]
        details = {k: v for k, v in info.items() if k != "element"}
        details["reference_id"] = ref_id
        details["true_branch_parent_id"] = f"{ref_id}:True"
        details["false_branch_parent_id"] = f"{ref_id}:False"
        msg = (
            f"Đã thêm FlowDecision '{ref_id}' (điều kiện: {condition_expr.strip()}). "
            f"Đặt khối vào nhánh bằng parent_node_id='{ref_id}:True' hoặc '{ref_id}:False'."
        )
        return details, msg, [ref_id]

    return _mutate_pkt("add_flow_decision", pkt_path, _apply)


@mcp.tool()
@_safe_tool("generate_assembly_recipe")
def generate_assembly_recipe(
    recipe_type: Literal["urban_road", "highway_lane"],
    output_path: str,
    subassembly_name: Optional[str] = None,
    lane_width: float = 3.5,
    civil_version: Literal["2025", "2026", "2027"] = "2026",
) -> str:
    """
    Tự động sinh mặt cắt tổ hợp hoàn chỉnh theo công thức chuẩn Việt Nam (Assembly Recipes):
      - 'urban_road': Đường đô thị (Áo đường 4 lớp + Bó vỉa bo cong Fillet + Vỉa hè đi bộ).
      - 'highway_lane': Làn cao tốc (Công thức siêu cao 8 nhánh tự động + Lề gia cố + Lề đất).

    Args:
        recipe_type: Loại mặt cắt ('urban_road' hoặc 'highway_lane').
        output_path: Đường dẫn lưu file .pkt tạo ra.
        subassembly_name: Tên hiển thị của Subassembly.
        lane_width: Bề rộng làn xe (m, mặc định 3.5m).
        civil_version: Phiên bản Civil 3D ('2025', '2026', '2027').
    """
    if recipe_type == "urban_road":
        name = subassembly_name or "DuongDoThi_BoVia_ViaHe"
        res_path = create_urban_road_assembly(
            output_path=output_path,
            subassembly_name=name,
            lane_width=lane_width,
            civil_version=civil_version,
        )
    else:
        name = subassembly_name or "LanCaoToc_SieuCao"
        res_path = create_highway_lane_assembly(
            output_path=output_path,
            subassembly_name=name,
            lane_width=lane_width,
            civil_version=civil_version,
        )

    res = MutationResult(
        success=True,
        pkt_path=res_path,
        action="generate_assembly_recipe",
        message=f"Đã tự động khởi tạo thành công mặt cắt tổ hợp chuẩn '{recipe_type}' tại '{res_path}'.",
        created_reference_ids=[],
        details={
            "recipe_type": recipe_type,
            "output_path": res_path,
            "civil_version": civil_version,
        },
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
@_safe_tool("list_examples_and_split_catalog")
def list_examples_and_split_catalog() -> str:
    """
    Liệt kê toàn bộ danh mục 14 file .pkt mẫu thực tế trong thư mục examples/
    cùng 7 bộ Subassembly chuyên sâu đã được tách riêng từ gói Visual Infra
    (trong examples/Sub Assembly/Tach_Rieng_7_Subassembly/).
    """
    root_dir = Path(__file__).resolve().parent.parent.parent
    examples_dir = root_dir / "examples"
    split_catalog_file = (
        examples_dir / "Sub Assembly" / "Bo_7_Subassembly_Chuan" / "catalog_7_subassembly.json"
    )
    if not split_catalog_file.exists():
        split_catalog_file = (
            examples_dir / "Sub Assembly" / "Tach_Rieng_7_Subassembly" / "visual_infra_catalog.json"
        )

    real_pkts = []
    if examples_dir.exists():
        for pkt in sorted(examples_dir.glob("*.pkt")):
            if pkt.stat().st_size == 0:
                real_pkts.append({"file_name": pkt.name, "status": "EMPTY_0_BYTES", "path": str(pkt)})
                continue
            try:
                pkg = PktPackage.open(pkt)
                meta = pkg.get_metadata()
                real_pkts.append(
                    {
                        "file_name": pkt.name,
                        "subassembly_name": meta["subassembly_name"],
                        "description": meta["description"],
                        "civil_version": meta["detected_civil_version"],
                        "size_bytes": pkt.stat().st_size,
                        "path": str(pkt),
                    }
                )
            except Exception as exc:
                real_pkts.append({"file_name": pkt.name, "error": str(exc), "path": str(pkt)})

    visual_infra_split = []
    if split_catalog_file.exists():
        visual_infra_split = json.loads(split_catalog_file.read_text(encoding="utf-8"))

    return json.dumps(
        {
            "examples_pkt_count": len(real_pkts),
            "examples_pkt_files": real_pkts,
            "visual_infra_split_count": len(visual_infra_split),
            "visual_infra_7_modules": visual_infra_split,
        },
        ensure_ascii=False,
        indent=2,
    )


# ============================================================================
# TOOL: validate_pkt_native
# ============================================================================
@mcp.tool()
@_safe_tool("validate_pkt_native")
def validate_pkt_native(pkt_path: str, document_check: bool = False) -> str:
    """Kiểm định 3 tầng file Subassembly (.pkt) trước khi mở bằng Subassembly Composer hoặc nạp vào Civil 3D.

    Tầng 1: Cấu trúc OPC Package & XML.
    Tầng 2: XAML tĩnh: BOM, biểu thức bọc [...], tên biến VB; activity / thuộc tính / đối số bắt buộc
            có thật trong Subassembly.ActivityLibrary; x:Reference không treo; node mồ côi;
            tham chiếu Point / Link đã được tạo.
    Tầng 3: DLL gốc của đúng phiên bản SAC: nạp cây activity và biên dịch MỌI biểu thức VB
            (biến chưa khai báo, cú pháp hỏng, sai kiểu). Bỏ qua nếu máy không cài SAC.

    Args:
        pkt_path: Đường dẫn file .pkt.
        document_check: True để mở thêm bằng SubassemblyDocument như SAC GUI (chậm hơn ~2 giây).
    """
    from sac_mcp.core.validator import PktValidator
    rep = PktValidator.validate_pkt(pkt_path, run_native_test=True, document_check=document_check)
    return json.dumps(
        {
            "pkt_path": rep.pkt_path,
            "is_valid": rep.is_valid,
            "tier1_opc_ok": rep.tier1_opc_ok,
            "tier2_xaml_ok": rep.tier2_xaml_ok,
            "tier3_native_ok": rep.tier3_native_ok,
            "metadata": rep.metadata,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "location": i.location,
                }
                for i in rep.issues
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def ensure_default_templates_exist(overwrite: bool = False) -> None:
    """
    Sinh 3 file base_2025.pkt, base_2026.pkt, base_2027.pkt trong thư mục templates/.
    Mặc định chỉ tạo file còn thiếu; truyền overwrite=True để sinh lại toàn bộ
    (dùng bởi scripts/generate_base_templates.py). Server KHÔNG gọi hàm này khi khởi động.
    """
    tpl_dir: Path = VersionManager.TEMPLATES_DIR
    tpl_dir.mkdir(parents=True, exist_ok=True)
    for ver in (CivilVersion.C3D_2025, CivilVersion.C3D_2026, CivilVersion.C3D_2027):
        tpl_path = VersionManager.get_template_path(ver)
        if tpl_path.exists() and not overwrite:
            continue
        PktPackage.create_from_template(
            output_path=tpl_path,
            subassembly_name=f"BaseTemplate_{ver.value}",
            description=f"Base Subassembly Template for Autodesk Civil 3D {ver.value}",
            civil_version=ver,
        )


# ============================================================================
# Nhóm tool sửa / xoá node và spec khai báo (định nghĩa trong sac_mcp/tools_ext.py):
#   remove_node, update_node, export_spec, build_from_spec
# ============================================================================
from sac_mcp import tools_ext as _tools_ext  # noqa: E402

_tools_ext.register(mcp, _mutate_pkt, _safe_tool)


def main() -> None:
    """Entrypoint khởi chạy SAC MCP Server qua giao thức stdio (không ghi file nào khi khởi động)."""
    mcp.run()


if __name__ == "__main__":
    main()
