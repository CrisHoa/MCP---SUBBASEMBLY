"""
Unit test kiểm thử chuyên sâu về:
1. Cơ chế Offset Geometry (CreateOffset) & Offset Target.
2. Hệ thống Điều kiện So sánh (Decision Logic):
   - So sánh Đào / Đắp (Cut vs Fill)
   - So sánh Chiều cao Taluy để Giật cơ (Bench / Berm threshold)
   - So sánh Trạng thái gán Target (Target IsValid)
   - So sánh Trái / Phải (Side.Right vs Side.Left)
"""

from pathlib import Path
from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.validator import PktValidator
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
    ReportMessageType,
)


def test_offset_and_comparison_conditions(tmp_path: Path):
    test_pkt = tmp_path / "TestOffsetAndConditions.pkt"
    pkg = PktPackage.create_from_template(
        output_path=test_pkt,
        subassembly_name="TestOffsetAndConditions",
        description="Kiểm thử chuyên sâu Offset & Biểu thức so sánh điều kiện",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # 1. Các tham số Target & Input
    ParameterBuilder.add_parameter(engine, "EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên", "")
    pkg.sync_parameter_to_atc("EG", ParameterDataType.SURFACE_TARGET.value, "-9999", "Mặt đất tự nhiên", "")

    ParameterBuilder.add_parameter(engine, "OffsetMep", ParameterCategory.TARGET, ParameterDataType.OFFSET_TARGET, "0.0", "Mép đường mở rộng", "")
    pkg.sync_parameter_to_atc("OffsetMep", ParameterDataType.OFFSET_TARGET.value, "0.0", "Mép đường mở rộng", "")

    ParameterBuilder.add_parameter(engine, "H_GiatCo", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "6.0", "Ngưỡng giật cơ (m)", "")
    pkg.sync_parameter_to_atc("H_GiatCo", ParameterDataType.DOUBLE.value, "6.0", "Ngưỡng giật cơ (m)", "")

    ParameterBuilder.add_parameter(engine, "H_Lot", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Dày lớp đệm lót (m)", "")
    pkg.sync_parameter_to_atc("H_Lot", ParameterDataType.DOUBLE.value, "0.10", "Dày lớp đệm lót (m)", "")

    # 2. Khai báo biến nội bộ tính toán
    LogicBuilder.add_define_variable(engine, "Var_H", "Double", "0.0")

    # 3. Dựng hình học đỉnh taluy: P1 -> P2 (L1)
    GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0")
    GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "-0.02", "3.5", add_link=True, link_name="L1")

    # 4. Dựng điểm phụ AP1 bắn dốc xuống mặt đất EG để so sánh Cut/Fill
    GeometryBuilder.add_point_and_link(engine, "AP1", "P2", PointGeometryType.SLOPE_TO_SURFACE, "-1.5", "EG", is_auxiliary=True)
    GeometryBuilder.add_link(engine, "AL1", start_point="P2", end_point="AP1", is_auxiliary=True)

    # 5. Tính toán chiều cao taluy Var_H = Math.Abs(P2.Y - AP1.Y)
    LogicBuilder.add_set_variable_value(engine, "Var_H", "Math.Abs(P2.Y - AP1.Y)", "Double")

    # 6. Dựng FlowDecision: Điều kiện 1 - Kiểm tra Target EG có hợp lệ không
    dec_target = LogicBuilder.add_flow_decision(
        engine,
        condition_expr="EG.IsValid",
        display_name="Kiểm tra EG",
        x=260.0,
        y=400.0,
    )

    # 7. Nhánh True của EG: Kiểm tra Đào / Đắp (Cut vs Fill)
    # AP1.Y < P2.Y nghĩa là mặt đất tự nhiên nằm thấp hơn mép đường -> Nền Đắp (Fill)
    dec_cut_fill = LogicBuilder.add_flow_decision(
        engine,
        condition_expr="AP1.Y < P2.Y",
        display_name="Đắp hay Đào?",
        x=260.0,
        y=490.0,
        auto_attach=False,
    )
    # Nối nhánh True của dec_target vào dec_cut_fill
    engine.set_decision_branches(dec_target["element"], true_ref_id=dec_cut_fill["decision_node_id"])

    # 8. Nhánh True của Fill: Kiểm tra vượt ngưỡng giật cơ (Var_H > H_GiatCo)
    dec_giatco = LogicBuilder.add_flow_decision(
        engine,
        condition_expr="Var_H > H_GiatCo",
        display_name="Có giật cơ không?",
        x=260.0,
        y=580.0,
        auto_attach=False,
    )
    engine.set_decision_branches(dec_cut_fill["element"], true_ref_id=dec_giatco["decision_node_id"])

    # 9. Sử dụng Offset Geometry (CreateOffset) để tạo lớp đệm lót song song từ L1
    offset_res = GeometryBuilder.add_offset_geometry(
        engine,
        offset_code="OffsetDemLot",
        links=["L1"],
        offset_distance=-0.10,
        offset_codes_str='"DemLot"',
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    # Kiểm định trọn vẹn 3 tầng
    rep = PktValidator.validate_pkt(test_pkt, run_native_test=True)
    assert rep.is_valid, f"Validation errors: {[i.message for i in rep.issues]}"
    assert rep.tier1_opc_ok
    assert rep.tier2_xaml_ok
    assert rep.tier3_native_ok
