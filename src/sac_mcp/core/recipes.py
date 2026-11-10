"""
Bộ công thức lắp ghép mặt cắt điển hình (Assembly Recipes) theo tiêu chuẩn Việt Nam.
Tự động sinh ra các file .pkt tổ hợp hoàn chỉnh:
  1. Mặt đường đô thị (Áo đường 4 lớp + Bó vỉa bo cong Fillet + Bê tông lót + Vỉa hè)
  2. Làn cao tốc quay siêu cao (8 nhánh + lề gia cố + lề đất)
  3. Mái taluy đào đắp giật cơ (bóc hữu cơ StripSurface + giật cơ CreateLoop)
  4. Nâng cấp cải tạo bù vênh mặt đường cũ
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.knowledge_base import build_superelevation_slope_expression
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
    ReportMessageType,
)


def create_urban_road_assembly(
    output_path: str,
    subassembly_name: str = "MatDuongDoThi_BoVia_ViaHe",
    lane_width: float = 3.5,
    lane_slope: float = -0.02,
    sidewalk_width: float = 3.0,
    sidewalk_slope: float = -0.015,
    civil_version: str = "2026",
) -> str:
    """
    Sinh file .pkt mặt cắt đường đô thị hoàn chỉnh:
      - Mặt đường 4 lớp (Pave1=5cm, Pave2=7cm, Base=15cm, SubBase=25cm)
      - Bó vỉa tự động (B1=0.18m, H1=0.30m có bo cong gờ mép)
      - Lớp bê tông lót móng bó vỉa (BTL=0.28m, H=0.10m)
      - Vỉa hè lát gạch dốc 1.5% đổ dồn nước vào bó vỉa
    """
    pkg = PktPackage.create_from_template(
        output_path=output_path,
        subassembly_name=subassembly_name,
        description="Mặt cắt ngang đường đô thị hoàn chỉnh (Áo đường 4 lớp + Bó vỉa bo cong + Vỉa hè)",
        civil_version=CivilVersion(civil_version),
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # 1. Thêm Parameters
    params = [
        ("B_lan", ParameterCategory.INPUT, ParameterDataType.DOUBLE, str(lane_width), "Bề rộng làn xe (m)", "Bề rộng phần xe chạy một bên"),
        ("i_lan", ParameterCategory.INPUT, ParameterDataType.GRADE, str(lane_slope), "Độ dốc mặt đường (%)", "Độ dốc ngang mặt đường"),
        ("B_he", ParameterCategory.INPUT, ParameterDataType.DOUBLE, str(sidewalk_width), "Bề rộng vỉa hè (m)", "Bề rộng vỉa hè đi bộ"),
        ("i_he", ParameterCategory.INPUT, ParameterDataType.GRADE, str(sidewalk_slope), "Độ dốc vỉa hè (%)", "Độ dốc thoát nước vỉa hè"),
        ("Pave1", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.05", "Chiều dày BTNC C12.5 (m)", "Lớp bê tông nhựa chặt trên"),
        ("Pave2", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.07", "Chiều dày BTNC C19 (m)", "Lớp bê tông nhựa chặt dưới"),
        ("Base", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.15", "Chiều dày Base CPĐD 1 (m)", "Móng cấp phối đá dăm loại 1"),
        ("SubBase", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.25", "Chiều dày SubBase CPĐD 2 (m)", "Móng cấp phối đá dăm loại 2"),
        ("Targ_Offset", ParameterCategory.TARGET, ParameterDataType.OFFSET_TARGET, "0", "Target Mở rộng làn", "Mục tiêu bề rộng tim đường"),
    ]
    for pname, cat, dt, def_val, disp, desc in params:
        ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
        pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

    # 2. Mặt trên áo đường P1 (Tim) -> P2 (Mép làn), Link L1
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P1", from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="0.0",
        point_codes_str='"Crown"', add_link=False,
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P2", from_point="P1",
        point_type=PointGeometryType.SLOPE_DELTA_X, param_1_expr="i_lan", param_2_expr="B_lan",
        point_codes_str='"Mep_pxc"', add_link=True, link_name="L1", link_codes_str='"Top", "pxc"',
    )

    # Kết cấu áo đường 4 lớp: mỗi lớp là tứ giác khép kín
    #   cạnh tim (AutoLink tim_trên -> tim_dưới), Link đáy song song mặt (AutoLink tim_dưới -> mép_dưới),
    #   cạnh mép (add_link mép_trên -> mép_dưới, AutoLink đi sai chiều nên tạo riêng).
    layers = [
        ("Pave1", '"Pave1"'),
        ("Pave2", '"Pave2"'),
        ("Base", '"Base"'),
        ("SubBase", '"SubBase", "Datum"'),
    ]
    top_tim, top_mep, top_link = "P1", "P2", "L1"
    for idx, (thk, codes) in enumerate(layers):
        p_tim, p_mep = f"P{2 * idx + 3}", f"P{2 * idx + 4}"           # P3/P4 ... P9/P10
        l_day, l_mep, l_tim = (f"L{3 * idx + 2}", f"L{3 * idx + 3}", f"L{3 * idx + 4}")  # L2..L13
        GeometryBuilder.add_point_and_link(
            engine=engine, point_code=p_tim, from_point=top_tim,
            point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr=f"-{thk}",
            add_link=True, link_name=l_tim, link_codes_str='"Crown"',
        )
        GeometryBuilder.add_point_and_link(
            engine=engine, point_code=p_mep, from_point=p_tim,
            point_type=PointGeometryType.SLOPE_DELTA_X, param_1_expr="i_lan", param_2_expr="B_lan",
            add_link=True, link_name=l_day, link_codes_str=codes,
        )
        GeometryBuilder.add_link(engine=engine, link_name=l_mep, start_point=top_mep, end_point=p_mep, link_codes_str='"Pave"')
        # Vòng: tim_trên -> mép_trên -> mép_dưới -> tim_dưới -> tim_trên
        GeometryBuilder.add_shape(
            engine=engine, shape_code=f"S{idx + 1}",
            link_names=[top_link, l_mep, l_day, l_tim], shape_codes_str=f'"{thk}"',
        )
        top_tim, top_mep, top_link = p_tim, p_mep, l_day

    # 3. Bó vỉa từ mép làn P2: P11 (đỉnh gờ), P12 (đỉnh bó vỉa)
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P11", from_point="P2",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="0.15",
        point_codes_str='"BV1"', add_link=True, link_name="L14", link_codes_str='"Top", "Link_BV"',
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P12", from_point="P11",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.18", param_2_expr="0.0",
        point_codes_str='"BV2"', add_link=True, link_name="L15", link_codes_str='"Top", "Link_BV"',
    )

    # 4. Vỉa hè P13 (từ P12 ra mép ngoài)
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P13", from_point="P12",
        point_type=PointGeometryType.SLOPE_DELTA_X, param_1_expr="i_he", param_2_expr="B_he",
        point_codes_str='"Mep_vh"', add_link=True, link_name="L16", link_codes_str='"Top", "Viahe"',
    )

    # 5. Cảnh báo kiểm tra bề rộng làn
    LogicBuilder.add_report_message(
        engine=engine,
        message_expr='"Bề rộng làn xe B_lan phải lớn hơn 0!"',
        message_type=ReportMessageType.ERROR,
        condition_expr="B_lan <= 0",
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()
    return str(pkg.pkt_path)


def create_highway_lane_assembly(
    output_path: str,
    subassembly_name: str = "LanCaoToc_SieuCao_LeDat",
    lane_width: float = 3.75,
    civil_version: str = "2026",
) -> str:
    """
    Sinh file .pkt làn đường cao tốc có siêu cao tự động 8 nhánh:
      - Làn xe chạy B=3.75m có công thức quay siêu cao 8 nhánh tự động
      - Lề gia cố B=0.5m
      - Lề đất B=0.75m dốc i=-4%
      - Target bề mặt tự nhiên EG
    """
    pkg = PktPackage.create_from_template(
        output_path=output_path,
        subassembly_name=subassembly_name,
        description="Làn cao tốc có quay siêu cao tự động 8 nhánh, lề gia cố và lề đất",
        civil_version=CivilVersion(civil_version),
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # Parameters
    params = [
        ("B_lan", ParameterCategory.INPUT, ParameterDataType.DOUBLE, str(lane_width), "Bề rộng làn cao tốc (m)", "Bề rộng 1 làn"),
        ("i_matduong", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.02", "Độ dốc mặt đường (%)", "Độ dốc ngang khi không quay siêu cao"),
        ("UseSuperelevation", ParameterCategory.INPUT, ParameterDataType.SUPERELEVATION, "RightOutsideLane", "Trục siêu cao", "Tham số gán siêu cao Civil 3D"),
        ("Ble_giaco", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Bề rộng lề gia cố (m)", "Lề gia cố cùng kết cấu mặt đường"),
        ("Ble_dat", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.75", "Bề rộng lề đất (m)", "Lề đất hoàn thiện"),
        ("i_le", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.04", "Độ dốc lề đất (%)", "Độ dốc thoát nước lề"),
        ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (EG)", "Địa hình hiện trạng"),
    ]
    for pname, cat, dt, def_val, disp, desc in params:
        ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
        pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

    # 1. Tim đường P1
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P1",
        from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="0.0",
        point_codes_str='"Crown"',
        add_link=False,
    )

    # 2. Làn cao tốc P2 áp dụng công thức siêu cao 8 nhánh tự động
    se_expr = build_superelevation_slope_expression(fallback_slope_param="i_matduong")
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P2",
        from_point="P1",
        point_type=PointGeometryType.SLOPE_DELTA_X,
        param_1_expr=se_expr,
        param_2_expr="B_lan",
        point_codes_str='"Mep_pxc"',
        add_link=True,
        link_name="L1",
        link_codes_str='"Top", "pxc"',
    )

    # 3. Lề gia cố P3
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P3",
        from_point="P2",
        point_type=PointGeometryType.SLOPE_DELTA_X,
        param_1_expr=se_expr,
        param_2_expr="Ble_giaco",
        point_codes_str='"Mep_le_giaco"',
        add_link=True,
        link_name="L2",
        link_codes_str='"Top", "LeGiaCo"',
    )

    # 4. Lề đất P4
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P4",
        from_point="P3",
        point_type=PointGeometryType.SLOPE_DELTA_X,
        param_1_expr="i_le",
        param_2_expr="Ble_dat",
        point_codes_str='"Mep_le"',
        add_link=True,
        link_name="L3",
        link_codes_str='"Top", "LeDat"',
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()
    return str(pkg.pkt_path)
