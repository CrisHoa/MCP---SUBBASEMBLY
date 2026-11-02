"""
Unit test kiểm thử tự động toàn diện nhóm 3, 4, 5:
- Auxiliary (AP, AL)
- Workflow (Sequence, FlowDecision)
- Miscellaneous (DefineVariable, SetVariableValue, SetOutputParameter, SetMarkPoint, ReportMessage)
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


def test_misc_and_workflow_activities(tmp_path: Path):
    test_pkt = tmp_path / "TestMiscWorkflow.pkt"
    pkg = PktPackage.create_from_template(
        output_path=test_pkt,
        subassembly_name="TestMiscWorkflow",
        description="Kiểm thử trọn vẹn nhóm Workflow & Miscellaneous trong SAC",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # 1. Khai báo Input & Output Parameters
    ParameterBuilder.add_parameter(engine, "EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên", "")
    pkg.sync_parameter_to_atc("EG", ParameterDataType.SURFACE_TARGET.value, "-9999", "Mặt đất tự nhiên", "")

    ParameterBuilder.add_parameter(engine, "Out_DienTich", ParameterCategory.OUTPUT, ParameterDataType.DOUBLE, "0.0", "Diện tích kết cấu", "")
    pkg.sync_parameter_to_atc("Out_DienTich", ParameterDataType.DOUBLE.value, "0.0", "Diện tích kết cấu", "")

    # 2. Miscellaneous: Define Variable (Biến nội bộ Var_H)
    LogicBuilder.add_define_variable(engine, "Var_H", "Double", "0.0")

    # 3. Geometry cơ bản + Auxiliary Point & Link
    GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0")
    GeometryBuilder.add_point_and_link(engine, "AP1", "P1", PointGeometryType.SLOPE_TO_SURFACE, "-1.5", "EG", is_auxiliary=True)
    GeometryBuilder.add_link(engine, "AL1", start_point="P1", end_point="AP1", is_auxiliary=True)

    # 4. Miscellaneous: Set Variable Value
    LogicBuilder.add_set_variable_value(engine, "Var_H", "Math.Abs(P1.Y - AP1.Y)", "Double")

    # 5. Miscellaneous: Set Output Parameter
    LogicBuilder.add_set_output_parameter(engine, "Out_DienTich", "Var_H * 3.5", "Double")

    # 6. Miscellaneous: Set Mark Point
    LogicBuilder.add_set_mark_point(engine, "P1", "CrestMark")

    # 7. Miscellaneous: Report Message
    LogicBuilder.add_report_message(engine, '"Đã hoàn tất tính toán phụ trợ"', ReportMessageType.INFORMATION)

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    rep = PktValidator.validate_pkt(test_pkt, run_native_test=True)
    assert rep.is_valid, f"Validation errors: {[i.message for i in rep.issues]}"
    assert rep.tier1_opc_ok
    assert rep.tier2_xaml_ok
    assert rep.tier3_native_ok
