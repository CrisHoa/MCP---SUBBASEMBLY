"""
SAC MCP Server (sac-mcp-server)
Model Context Protocol Server chuyên dụng cho Autodesk Civil 3D Subassembly Composer (2025 - 2027).
Cung cấp 5 công cụ lõi:
  1. inspect_pkt
  2. create_pkt_from_template
  3. add_parameter
  4. add_point_and_link
  5. add_report_message
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

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
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.recipes import create_highway_lane_assembly, create_urban_road_assembly
from sac_mcp.core.version_manager import VersionManager
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
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
        "cho Autodesk Civil 3D phiên bản 2025, 2026, 2027."
    ),
)


# ============================================================================
# TOOL 1: inspect_pkt
# ============================================================================
@mcp.tool()
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
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = ParameterBuilder.add_parameter(
        engine=engine,
        name=name,
        category=ParameterCategory(param_category),
        data_type=ParameterDataType(data_type),
        default_value=default_value,
        display_name=display_name,
        description=description,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    if param_category == "Input":
        pkg.sync_parameter_to_atc(
            name=info["parameter_name"],
            data_type=data_type,
            default_value=default_value,
            display_name=info["display_name"],
            description=description,
        )
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_parameter",
        message=f"Đã thêm {param_category} Parameter '{info['parameter_name']}' ({data_type} = {default_value}).",
        created_reference_ids=[],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


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
    add_link: bool = True,
    link_name: str = "L1",
    link_codes_str: str = "",
    is_auxiliary: bool = False,
    use_superelevation_formula: bool = False,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Thêm Point hoặc Auxiliary Point (P1, P2... hoặc AP1, AP2...) theo Delta X & Delta Y,
    Slope & Delta X, Slope to Surface... và tự động nối Link (L1 / AL1) trong file .pkt.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        point_code: Mã Point (VD: 'P1', 'P2' hoặc 'AP1' nếu is_auxiliary=True).
        from_point: Điểm tham chiếu bắt đầu (VD: 'Origin', 'P1', 'AP1').
        point_type: Phương thức xác định điểm ('DeltaX_DeltaY', 'Slope_DeltaX', 'Slope_DeltaY', 'Angle_Distance', 'Slope_To_Surface', 'Interpolate').
        param_1_expr: Biểu thức tham số 1 (VD: DeltaX cho 'DeltaX_DeltaY', hoặc Slope cho 'Slope_DeltaX').
        param_2_expr: Biểu thức tham số 2 (VD: DeltaY cho 'DeltaX_DeltaY', hoặc DeltaX cho 'Slope_DeltaX').
        point_codes_str: Chuỗi Code cho Point trong Civil 3D (VD: '\"Crown\"' hoặc '\"ETW\"').
        add_link: Nếu True, tự động nối Link từ `from_point` tới `point_code`.
        link_name: Mã Link (VD: 'L1', 'L2' hoặc 'AL1').
        link_codes_str: Chuỗi Code cho Link (VD: '\"Top\", \"Pave\"').
        is_auxiliary: Nếu True, tạo phần tử phụ trợ Auxiliary Point / Auxiliary Link (AP/AL).
        use_superelevation_formula: Nếu True và point_type là Slope_DeltaX / Slope_DeltaY / Slope_To_Surface,
                                    tự động điền công thức quay siêu cao 8 nhánh chuẩn vào param_1_expr
                                    với biến độ dốc mặc định lấy từ param_1_expr (VD: 'LaneSlope').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha. Nếu bỏ trống sẽ tự nối vào cuối Flowchart.
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    actual_param_1 = param_1_expr
    if use_superelevation_formula and point_type in (
        "Slope_DeltaX",
        "Slope_DeltaY",
        "Slope_To_Surface",
    ):
        fallback_var = param_1_expr if param_1_expr and param_1_expr != "0.0" else "LaneSlope"
        actual_param_1 = build_superelevation_slope_expression(fallback_slope_param=fallback_var)

    info = GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code=point_code,
        from_point=from_point,
        point_type=PointGeometryType(point_type),
        param_1_expr=actual_param_1,
        param_2_expr=param_2_expr,
        point_codes_str=point_codes_str,
        add_link=add_link,
        link_name=link_name,
        link_codes_str=link_codes_str,
        is_auxiliary=is_auxiliary,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    kind_str = "Auxiliary Point" if is_auxiliary else "Point"
    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_point_and_link",
        message=(
            f"Đã thêm {kind_str} '{point_code}' (từ {from_point}, kiểu {point_type})"
            + (f" kèm Link '{link_name}'" if add_link else "")
            + f" tại node {info['reference_id']}."
        ),
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


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
) -> str:
    """
    Thêm Link hoặc Auxiliary Link (CreateLink / CreateAuxLink) nối giữa 2 Point có sẵn
    để khép kín hình học Shape (ví dụ: đáy kết cấu, ngoàm chân khay, vách trong...).

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        link_name: Tên/Mã Link (VD: 'L7' hoặc 'AL2').
        start_point: Tên điểm bắt đầu (VD: 'P7').
        end_point: Tên điểm kết thúc (VD: 'P3').
        link_codes_str: Chuỗi mã LinkCode cách nhau bởi dấu phẩy (VD: '"Datum"' hoặc '"Top", "Pave"').
        apply_aor: Có áp dụng siêu cao (Apply AOR) cho Link này không.
        is_auxiliary: True nếu là Link phụ trợ (AL).
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

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

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_link",
        message=f"Đã thêm {'AuxLink' if is_auxiliary else 'Link'} '{link_name}' nối từ {start_point} đến {end_point}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


# ============================================================================
# TOOL BỔ SUNG: add_shape & get_sac_reference_and_formulas (từ tài liệu HOA_C3D)
# ============================================================================
@mcp.tool()
def add_fillet_arc(
    pkt_path: str,
    link_number: str,
    first_link: str,
    second_link: Optional[str] = None,
    round_radius: float = 0.05,
    end_point_name: Optional[str] = None,
    link_codes_str: str = "",
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Thêm khối bo tròn góc cong Fillet Arc (<asa1:FilletArcActivity>) vào Flowchart.
    Thường dùng bo tròn mượt mà cho gờ mép bó vỉa (bán kính R) hoặc rãnh tam giác.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        link_number: Mã Link cong mới (VD: 'L6').
        first_link: Mã Link phụ trợ đầu tiên tiếp xúc (VD: 'AL1').
        second_link: (Tùy chọn) Mã Link thứ 2 tiếp xúc.
        round_radius: Bán kính bo cong (m), mặc định 0.05m = 5cm.
        end_point_name: (Tùy chọn) Mã Point tại điểm kết thúc cung tròn (VD: 'P8').
        link_codes_str: Chuỗi Code gán cho đường cong (VD: '\"Top\", \"Link_Bo DPC\"').
        parent_node_id: (Tùy chọn) __ReferenceID của node cha.
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = GeometryBuilder.add_fillet_arc(
        engine=engine,
        link_number=link_number,
        first_link=first_link,
        second_link=second_link,
        round_radius=round_radius,
        end_point_name=end_point_name,
        link_codes_str=link_codes_str,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_fillet_arc",
        message=f"Đã thêm cung bo cong Fillet Arc '{link_number}' (R={round_radius}m) tại node {info['reference_id']}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
def add_loop_geometry(
    pkt_path: str,
    loop_code: str,
    links: list[str],
    repetition_count: int = 10,
    parent_node_id: Optional[str] = None,
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
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = GeometryBuilder.add_loop_geometry(
        engine=engine,
        loop_code=loop_code,
        links=links,
        repetition_count=repetition_count,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_loop_geometry",
        message=f"Đã thêm vòng lặp CreateLoop '{loop_code}' (Links={links}, max={repetition_count}) tại node {info['reference_id']}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
def add_intersection_point(
    pkt_path: str,
    point_code: str,
    link1: str,
    link2: str,
    is_auxiliary: bool = False,
    point_codes_str: str = "",
    parent_node_id: Optional[str] = None,
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
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = GeometryBuilder.add_intersection_point(
        engine=engine,
        point_code=point_code,
        link1=link1,
        link2=link2,
        is_auxiliary=is_auxiliary,
        point_codes_str=point_codes_str,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    kind = "AuxIntersection (AP)" if is_auxiliary else "LinkIntersection (P)"
    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_intersection_point",
        message=f"Đã thêm điểm giao cắt {kind} '{point_code}' giữa ({link1} x {link2}) tại node {info['reference_id']}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


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
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = GeometryBuilder.add_strip_surface(
        engine=engine,
        display_name=display_name,
        depth_expr=depth_expr,
        end_point_name=end_point_name,
        end_offset=end_offset,
        end_offset_target=end_offset_target,
        link_codes_str=link_codes_str,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_strip_surface",
        message=f"Đã thêm khối bóc hữu cơ StripSurface '{display_name}' (Depth={depth_expr}) tại node {info['reference_id']}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
def add_shape(
    pkt_path: str,
    shape_code: str,
    link_names: list[str],
    shape_codes_str: str = "",
    parent_node_id: Optional[str] = None,
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
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_string() if hasattr(pkg, "get_xaml_string") else pkg.get_xaml_text())

    info = GeometryBuilder.add_shape(
        engine=engine,
        shape_code=shape_code,
        link_names=link_names,
        shape_codes_str=shape_codes_str,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_shape",
        message=f"Đã thêm Shape '{shape_code}' từ các Link {link_names} tại node {info['reference_id']}.",
        created_reference_ids=[info["reference_id"]],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
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
    message_type: Literal["Information", "Warning", "Error"] = "Warning",
    condition_expr: Optional[str] = None,
    parent_node_id: Optional[str] = None,
) -> str:
    """
    Thêm khối Report Message (hoặc kết hợp biểu thức điều kiện Decision -> Report Message)
    vào Flowchart của file .pkt.

    Args:
        pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
        message_expr: Biểu thức chuỗi VB.NET cần thông báo (VD: '\"Chiều rộng làn <= 0!\"').
        message_type: Cấp độ thông báo trên Event Viewer ('Information', 'Warning', 'Error').
        condition_expr: (Tùy chọn) Biểu thức điều kiện VB.NET (VD: 'LaneWidth <= 0'). Nếu truyền vào,
                        công cụ sẽ tự động sinh một khối <FlowDecision> và nối nhánh True vào ReportMessage.
        parent_node_id: (Tùy chọn) __ReferenceID của node cha cần nối vào.
    """
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    info = LogicBuilder.add_report_message(
        engine=engine,
        message_expr=message_expr,
        message_type=ReportMessageType(message_type),
        condition_expr=condition_expr,
        parent_node_id=parent_node_id,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    res = MutationResult(
        success=True,
        pkt_path=str(pkg.pkt_path),
        action="add_report_message",
        message=(
            f"Đã thêm khối ReportMessage ({message_type})"
            + (f" kèm điều kiện Decision '{condition_expr}'" if condition_expr else "")
            + "."
        ),
        created_reference_ids=info["created_reference_ids"],
        details=info,
    )
    return json.dumps(res.model_dump(), ensure_ascii=False, indent=2)


@mcp.tool()
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
def validate_pkt_native(pkt_path: str) -> str:
    """Kiểm định toàn diện 3 tầng file Subassembly (.pkt) trước khi mở bằng Subassembly Composer hoặc import vào Civil 3D.
    Tầng 1: Cấu trúc OPC Package & XML Escaping
    Tầng 2: WF4 / XAML Semantics (Bọc [...] biểu thức tham số, tên biến VB.NET hợp lệ, activity hợp lệ)
    Tầng 3: Native Autodesk Runtime Hook (Gọi SubassemblyDocument trực tiếp từ DLL gốc Autodesk WorkflowEditor.dll)
    """
    from sac_mcp.core.validator import PktValidator
    rep = PktValidator.validate_pkt(pkt_path, run_native_test=True)
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


def ensure_default_templates_exist() -> None:
    """Đảm bảo 3 file base_2025.pkt, base_2026.pkt, base_2027.pkt luôn sẵn sàng trong thư mục templates/."""
    tpl_dir: Path = VersionManager.TEMPLATES_DIR
    tpl_dir.mkdir(parents=True, exist_ok=True)
    for ver in (CivilVersion.C3D_2025, CivilVersion.C3D_2026, CivilVersion.C3D_2027):
        tpl_path = VersionManager.get_template_path(ver)
        PktPackage.create_from_template(
            output_path=tpl_path,
            subassembly_name=f"BaseTemplate_{ver.value}",
            description=f"Base Subassembly Template for Autodesk Civil 3D {ver.value}",
            civil_version=ver,
        )


def main() -> None:
    """Entrypoint khởi chạy SAC MCP Server qua giao thức stdio."""
    ensure_default_templates_exist()
    mcp.run()


if __name__ == "__main__":
    main()
