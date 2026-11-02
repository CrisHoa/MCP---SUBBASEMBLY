"""
Unit test kiểm thử tự động toàn diện nhóm 1: Geometry (9 kiểu Positioning của Point, Link & Shape).
"""

from pathlib import Path
from sac_mcp.core.builders import GeometryBuilder, ParameterBuilder
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.validator import PktValidator
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
)


def test_all_9_point_positioning_types(tmp_path: Path):
    test_pkt = tmp_path / "TestAll9PointTypes.pkt"
    pkg = PktPackage.create_from_template(
        output_path=test_pkt,
        subassembly_name="TestAll9PointTypes",
        description="Kiểm thử 9 kiểu Positioning Point",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    ParameterBuilder.add_parameter(engine, "EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên", "")
    pkg.sync_parameter_to_atc("EG", ParameterDataType.SURFACE_TARGET.value, "-9999", "Mặt đất tự nhiên", "")

    # 1. DeltaXAndDeltaY
    GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0")

    # 2. SlopeAndDeltaX
    GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "-0.02", "3.5", add_link=True, link_name="L1")

    # 3. SlopeAndDeltaY
    GeometryBuilder.add_point_and_link(engine, "P3", "P2", PointGeometryType.SLOPE_DELTA_Y, "-1.5", "-5.0", add_link=True, link_name="L2")

    # 4. SlopeToSurface
    GeometryBuilder.add_point_and_link(engine, "P4", "P3", PointGeometryType.SLOPE_TO_SURFACE, "-1.5", "EG", add_link=True, link_name="L3")

    # 5. DeltaXOnSurface
    GeometryBuilder.add_point_and_link(engine, "P5", "P4", PointGeometryType.DELTA_X_ON_SURFACE, "2.0", "EG", add_link=True, link_name="L4")

    # 6. AngleAndDeltaX
    GeometryBuilder.add_point_and_link(engine, "P6", "P5", PointGeometryType.ANGLE_DELTA_X, "45.0", "1.0", add_link=True, link_name="L5")

    # 7. AngleAndDeltaY
    GeometryBuilder.add_point_and_link(engine, "P7", "P6", PointGeometryType.ANGLE_DELTA_Y, "60.0", "1.5", add_link=True, link_name="L6")

    # 8. AngleAndDistance
    GeometryBuilder.add_point_and_link(engine, "P8", "P7", PointGeometryType.ANGLE_DISTANCE, "30.0", "2.0", add_link=True, link_name="L7")

    # 9. InterpolatePoint
    GeometryBuilder.add_point_and_link(engine, "P9", "P1", PointGeometryType.INTERPOLATE, "P8", "0.5")

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    rep = PktValidator.validate_pkt(test_pkt, run_native_test=True)
    assert rep.is_valid, f"Validation errors: {[i.message for i in rep.issues]}"
    assert rep.tier1_opc_ok
    assert rep.tier2_xaml_ok
    assert rep.tier3_native_ok
