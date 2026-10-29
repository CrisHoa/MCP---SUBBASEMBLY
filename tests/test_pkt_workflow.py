"""
Unit Tests kiểm thử toàn diện 5 công cụ MCP cho Civil 3D 2025, 2026, 2027.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sac_mcp.server import (
    add_fillet_arc,
    add_intersection_point,
    add_loop_geometry,
    add_parameter,
    add_point_and_link,
    add_report_message,
    add_shape,
    add_strip_surface,
    create_pkt_from_template,
    generate_assembly_recipe,
    get_sac_reference_and_formulas,
    inspect_pkt,
    list_examples_and_split_catalog,
)


@pytest.mark.parametrize("civil_ver", ["2025", "2026", "2027"])
def test_full_pkt_lifecycle_across_civil_versions(tmp_path: Path, civil_ver: str) -> None:
    pkt_file = tmp_path / f"TestSub_{civil_ver}.pkt"

    # 1. Test create_pkt_from_template
    res_create = json.loads(
        create_pkt_from_template(
            output_path=str(pkt_file),
            subassembly_name=f"RoadLane {civil_ver}",
            description=f"Test Subassembly cho Civil 3D {civil_ver}",
            civil_version=civil_ver,
        )
    )
    assert res_create["success"] is True
    assert pkt_file.exists()
    assert res_create["details"]["civil_version"] == civil_ver

    # 2. Test add_parameter (Input, Output, Target)
    res_p1 = json.loads(
        add_parameter(
            pkt_path=str(pkt_file),
            name="Width",
            param_category="Input",
            data_type="Double",
            default_value="3.75",
            display_name="Width (m)",
        )
    )
    assert res_p1["success"] is True

    res_p2 = json.loads(
        add_parameter(
            pkt_path=str(pkt_file),
            name="TargetEG",
            param_category="Target",
            data_type="SurfaceTarget",
            default_value="-9999",
            display_name="Existing Ground",
        )
    )
    assert res_p2["success"] is True

    # 3. Test add_point_and_link
    res_pt1 = json.loads(
        add_point_and_link(
            pkt_path=str(pkt_file),
            point_code="P1",
            from_point="Origin",
            point_type="DeltaX_DeltaY",
            param_1_expr="0.0",
            param_2_expr="0.0",
            point_codes_str='"Crown"',
            add_link=False,
        )
    )
    assert res_pt1["success"] is True
    assert res_pt1["details"]["reference_id"] == "__ReferenceID0"

    res_pt2 = json.loads(
        add_point_and_link(
            pkt_path=str(pkt_file),
            point_code="P2",
            from_point="P1",
            point_type="Slope_DeltaX",
            param_1_expr="-0.02",
            param_2_expr="Width",
            point_codes_str='"ETW"',
            add_link=True,
            link_name="L1",
            link_codes_str='"Top", "Pave"',
        )
    )
    assert res_pt2["success"] is True
    assert res_pt2["details"]["linked_from_reference_id"] == "__ReferenceID0"

    # 4. Test add_report_message kèm điều kiện Decision
    res_msg = json.loads(
        add_report_message(
            pkt_path=str(pkt_file),
            message_expr='"Width không hợp lệ!"',
            message_type="Warning",
            condition_expr="Width <= 0",
        )
    )
    assert res_msg["success"] is True
    assert len(res_msg["created_reference_ids"]) == 2

    # 5. Test inspect_pkt
    inspected = json.loads(inspect_pkt(str(pkt_file), include_raw_xaml=True))
    assert inspected["detected_civil_version"] == civil_ver
    assert inspected["start_node_id"] == "__ReferenceID0"

    param_names = [p["name"] for p in inspected["parameters"]]
    assert "Side" in param_names
    assert "Width" in param_names
    assert "TargetEG" in param_names

    point_codes = [pt["point_number"] for pt in inspected["points"]]
    assert point_codes == ["P1", "P2"]

    link_codes = [lk["link_number"] for lk in inspected["links"]]
    assert link_codes == ["L1"]

    assert len(inspected["flowchart_nodes"]) == 4  # P1, P2, Decision, ReportMessage


def test_hoa_c3d_knowledge_base_and_superelevation_shape(tmp_path: Path) -> None:
    pkt_file = tmp_path / "SuperelevationLane_2026.pkt"
    create_pkt_from_template(
        output_path=str(pkt_file),
        subassembly_name="Sub_SieuCao_2026",
        civil_version="2026",
    )

    # Thêm biến theo quy chuẩn HOA_C3D (B_lan, H_ketcau, UseSuperelevation)
    add_parameter(str(pkt_file), name="B_lan", param_category="Input", data_type="Double", default_value="3.5", display_name="Bề rộng làn")
    add_parameter(str(pkt_file), name="H_ketcau", param_category="Input", data_type="Double", default_value="0.25", display_name="Chiều dày kết cấu")
    add_parameter(str(pkt_file), name="i_matduong", param_category="Input", data_type="Grade", default_value="-0.02", display_name="Độ dốc ngang đường")
    add_parameter(str(pkt_file), name="UseSuperelevation", param_category="Input", data_type="Superelevation", default_value="RightInsideLane", display_name="Siêu cao")

    # Tạo P1 -> P2 dùng công thức quay siêu cao 8 nhánh tự động
    add_point_and_link(str(pkt_file), point_code="P1", from_point="Origin", add_link=False)
    res_se = json.loads(
        add_point_and_link(
            str(pkt_file),
            point_code="P2",
            from_point="P1",
            point_type="Slope_DeltaX",
            param_1_expr="i_matduong",
            param_2_expr="B_lan",
            add_link=True,
            link_name="L1",
            use_superelevation_formula=True,
        )
    )
    assert "SE.HasLeftLI" in res_se["details"]["param_1_expr"]
    assert "CType(i_matduong,Double)" in res_se["details"]["param_1_expr"]

    # Tạo Auxiliary Point AP1 & Shape S1
    add_point_and_link(
        str(pkt_file),
        point_code="AP1",
        from_point="P1",
        point_type="DeltaX_DeltaY",
        param_1_expr="0.0",
        param_2_expr="-H_ketcau",
        add_link=True,
        link_name="AL1",
        is_auxiliary=True,
    )
    res_shape = json.loads(
        add_shape(
            str(pkt_file),
            shape_code="S1",
            link_names=["L1", "L2", "L3", "L4"],
            shape_codes_str='"Pave1"',
        )
    )
    assert res_shape["success"] is True

    # Kiểm tra inspect_pkt và get_sac_reference_and_formulas
    inspected = json.loads(inspect_pkt(str(pkt_file)))
    assert len(inspected["shapes"]) == 1
    assert inspected["shapes"][0]["shape_number"] == "S1"

    kb = json.loads(get_sac_reference_and_formulas(topic="all", fallback_slope_param="i_matduong"))
    assert "toolbox_catalog" in kb
    assert "superelevation_slope_expression" in kb
    assert "point_api" in kb


def test_inspect_real_examples_and_split_visual_infra() -> None:
    examples_dir = Path(__file__).resolve().parent.parent / "examples"

    # 1. Kiểm tra inspect_pkt trên file thực tế A_Taluy co ranh-Giatco-VHC v1.pkt
    taluy_pkt = examples_dir / "A_Taluy co ranh-Giatco-VHC v1.pkt"
    res_taluy = json.loads(inspect_pkt(str(taluy_pkt)))
    assert res_taluy["subassembly_name"] == "QP2_Taluycoranh_GiatCo_VHC"
    assert res_taluy["detected_civil_version"] == "2026"
    assert len(res_taluy["parameters"]) == 13
    assert len(res_taluy["points"]) >= 25
    assert len(res_taluy["links"]) >= 22
    assert len(res_taluy["shapes"]) == 2

    # 2. Kiểm tra inspect_pkt trên file thực tế LTT_KCAD PXC.pkt
    pxc_pkt = examples_dir / "LTT_KCAD PXC.pkt"
    res_pxc = json.loads(inspect_pkt(str(pxc_pkt)))
    assert res_pxc["subassembly_name"] == "LTT_PXC"
    assert len(res_pxc["parameters"]) == 12
    assert len(res_pxc["shapes"]) == 8

    # 3. Kiểm tra 7 module đã tách riêng từ SACVisualInfra.pkt
    catalog = json.loads(list_examples_and_split_catalog())
    assert catalog["visual_infra_split_count"] == 7
    for mod in catalog["visual_infra_7_modules"]:
        vi_pkt = Path(mod["pkt_path"])
        sac_pkt = Path(mod["sac_editable_pkt_path"])
        assert vi_pkt.exists()
        assert sac_pkt.exists()
        inspected_vi = json.loads(inspect_pkt(str(vi_pkt)))
        assert len(inspected_vi["parameters"]) == mod["parameter_count"] + 1


def test_advanced_sac_activities(tmp_path: Path) -> None:
    pkt_file = tmp_path / "AdvancedActivities_2026.pkt"
    create_pkt_from_template(str(pkt_file), subassembly_name="AdvSub", civil_version="2026")

    # 1. Test Fillet Arc
    res_arc = json.loads(
        add_fillet_arc(
            pkt_path=str(pkt_file),
            link_number="L_Arc",
            first_link="L1",
            second_link="L2",
            round_radius=0.08,
            link_codes_str='"Top", "Fillet"',
        )
    )
    assert res_arc["success"] is True

    # 2. Test Loop Geometry
    res_loop = json.loads(
        add_loop_geometry(
            pkt_path=str(pkt_file),
            loop_code="LO1",
            links=["L11", "L12"],
            repetition_count=8,
        )
    )
    assert res_loop["success"] is True

    # 3. Test Intersection Point
    res_int = json.loads(
        add_intersection_point(
            pkt_path=str(pkt_file),
            point_code="P_Int",
            link1="L1",
            link2="L2",
            is_auxiliary=False,
            point_codes_str='"Intersect"',
        )
    )
    assert res_int["success"] is True

    # 4. Test Strip Surface
    res_strip = json.loads(
        add_strip_surface(
            pkt_path=str(pkt_file),
            display_name="Strip_VHC",
            depth_expr="0.3",
            end_point_name="P_Int",
        )
    )
    assert res_strip["success"] is True

    # Inspect và xác nhận các phần tử đã nằm trong Flowchart
    inspected = json.loads(inspect_pkt(str(pkt_file), include_raw_xaml=True))
    assert "FilletArcActivity" in inspected["raw_xaml"]
    assert "CreateLoop" in inspected["raw_xaml"]
    assert "LinkIntersection" in inspected["raw_xaml"]
    assert "StripSurfaceActivity" in inspected["raw_xaml"]


def test_generate_assembly_recipes(tmp_path: Path) -> None:
    urban_pkt = tmp_path / "UrbanRoad_Recipe.pkt"
    res_urban = json.loads(
        generate_assembly_recipe(
            recipe_type="urban_road",
            output_path=str(urban_pkt),
            lane_width=3.75,
            civil_version="2026",
        )
    )
    assert res_urban["success"] is True
    inspected_urban = json.loads(inspect_pkt(str(urban_pkt)))
    param_names = [p["name"] for p in inspected_urban["parameters"]]
    assert "B_lan" in param_names
    assert "B_he" in param_names
    assert len(inspected_urban["points"]) >= 5
    assert len(inspected_urban["links"]) >= 5
    assert len(inspected_urban["shapes"]) >= 1

    hwy_pkt = tmp_path / "Highway_Recipe.pkt"
    res_hwy = json.loads(
        generate_assembly_recipe(
            recipe_type="highway_lane",
            output_path=str(hwy_pkt),
            lane_width=3.75,
            civil_version="2026",
        )
    )
    assert res_hwy["success"] is True
    inspected_hwy = json.loads(inspect_pkt(str(hwy_pkt)))
    p2 = [pt for pt in inspected_hwy["points"] if pt["point_number"] == "P2"][0]
    assert "SE.HasLeftLI" in p2["param_1_expr"]




