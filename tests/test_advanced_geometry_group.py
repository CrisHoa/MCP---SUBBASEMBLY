"""
Unit test kiểm thử tự động toàn diện nhóm 2: Advanced Geometry
(Intersection Point, Curve, Fillet Arc, Surface Link, Offset Geometry, Loop Geometry, Get Mark Point).
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


def test_advanced_geometry_activities(tmp_path: Path):
    test_pkt = tmp_path / "TestAdvancedGeometry.pkt"
    pkg = PktPackage.create_from_template(
        output_path=test_pkt,
        subassembly_name="TestAdvancedGeometry",
        description="Kiểm thử trọn vẹn các Activity nhóm Advanced Geometry trong SAC",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # 1. Parameter EG
    ParameterBuilder.add_parameter(engine, "EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên", "")
    pkg.sync_parameter_to_atc("EG", ParameterDataType.SURFACE_TARGET.value, "-9999", "Mặt đất tự nhiên", "")

    # Khởi tạo khung hình học cơ bản
    GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0")
    GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "-0.02", "3.5", add_link=True, link_name="L1")
    GeometryBuilder.add_point_and_link(engine, "P3", "P2", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-0.15", add_link=True, link_name="L2")
    GeometryBuilder.add_point_and_link(engine, "P4", "P3", PointGeometryType.DELTA_X_DELTA_Y, "-3.5", "0.0", add_link=True, link_name="L3")

    # 2. Advanced: Intersection Point (L1 giao L3 kéo dài)
    GeometryBuilder.add_intersection_point(engine, "P5", "L1", "L3", point_codes_str='"GiaoDiem"')

    # 3. Advanced: Fillet Arc bo mép
    GeometryBuilder.add_fillet_arc(engine, "L4", first_link="L1", second_link="L2", round_radius=0.03, link_codes_str='"Fillet"')

    # 4. Advanced: CreateCurve (Cung cong đáy rãnh từ P3 -> P4)
    GeometryBuilder.add_curve(engine, "L5", start_point="P3", end_point="P4", creation_type="ArcGeneral", num_increments=6, link_codes_str='"Curve"')

    # 5. Advanced: CreateOffset (Offset lớp móng song song từ L1)
    GeometryBuilder.add_offset_geometry(engine, "Off1", links=["L1"], offset_distance=-0.2, offset_codes_str='"SubBase"')

    # 6. Advanced: GetMarkPoint (Nhận điểm mác Edge)
    GeometryBuilder.add_get_mark_point(engine, "P6", mark_name="EdgePoint", point_codes_str='"Marked"')

    # 7. Advanced: StripSurface (Bóc đất hữu cơ)
    GeometryBuilder.add_strip_surface(engine, display_name="BocHuuCo", depth_expr="0.25", link_codes_str='"Strip"')

    # 8. Advanced: CreateLoop (Lặp lại bậc giật cơ)
    GeometryBuilder.add_loop_geometry(engine, "Loop1", links=["L1", "L2"], repetition_count=3)

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    rep = PktValidator.validate_pkt(test_pkt, run_native_test=True)
    assert rep.is_valid, f"Validation errors: {[i.message for i in rep.issues]}"
    assert rep.tier1_opc_ok
    assert rep.tier2_xaml_ok
    assert rep.tier3_native_ok
