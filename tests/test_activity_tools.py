"""
Kiểm thử các tool MCP activity bổ sung (add_curve, add_offset_geometry, add_get_mark_point,
add_set_mark_point, add_define_variable, add_set_variable, add_set_output_parameter, add_flow_decision)
và các sửa lỗi của add_report_message / add_point_and_link / cảnh báo Tầng 2 trong _mutate_pkt.

Mỗi tool: JSON success, file qua validate_pkt (is_valid + tier3_native_ok nếu máy có SAC),
không có lỗi ngữ nghĩa tĩnh, và nối luồng Flowchart đúng.
"""

import json
from pathlib import Path

import pytest

from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.semantic_checks import check_semantics
from sac_mcp.core.validator import PktValidator
from sac_mcp.native.host import installed_sac_dirs
from sac_mcp.server import (
    add_curve,
    add_define_variable,
    add_fillet_arc,
    add_flow_decision,
    add_get_mark_point,
    add_intersection_point,
    add_link,
    add_loop_geometry,
    add_offset_geometry,
    add_shape,
    add_parameter,
    add_point_and_link,
    add_report_message,
    add_set_mark_point,
    add_set_output_parameter,
    add_set_variable,
    create_pkt_from_template,
    inspect_pkt,
)

HAS_SAC = bool(installed_sac_dirs())


@pytest.fixture(autouse=True)
def _no_native_on_save(monkeypatch):
    # Tầng 3 được kiểm riêng ở cuối mỗi test (nhanh hơn chạy sau mỗi lần sửa).
    monkeypatch.setenv("SAC_MCP_NATIVE_ON_SAVE", "0")


def _ok(res: str) -> dict:
    data = json.loads(res)
    assert data["success"] is True, data
    return data


def _new_pkt(tmp_path: Path, name: str = "ActTools") -> Path:
    pkt = tmp_path / f"{name}.pkt"
    _ok(create_pkt_from_template(str(pkt), name, civil_version="2026"))
    return pkt


def _base_geometry(pkt: Path) -> None:
    """P1 (gốc) -> P2 (L1) -> P3 (L2) -> P4 (không Link)."""
    _ok(add_point_and_link(str(pkt), "P1", param_1_expr="1.0", param_2_expr="0.0", add_link=False))
    _ok(add_point_and_link(str(pkt), "P2", from_point="P1", param_1_expr="1.0", param_2_expr="-1.0", link_name="L1"))
    _ok(add_point_and_link(str(pkt), "P3", from_point="P2", param_1_expr="1.0", param_2_expr="1.0", link_name="L2"))
    _ok(add_point_and_link(str(pkt), "P4", from_point="P2", param_1_expr="0.0", param_2_expr="-0.5", add_link=False))


def _nodes(pkt: Path) -> dict:
    data = json.loads(inspect_pkt(str(pkt)))
    return {"start": data["start_node_id"], "nodes": {n["reference_id"]: n for n in data["flowchart_nodes"]}}


def _assert_valid(pkt: Path) -> None:
    rep = PktValidator.validate_pkt(pkt, run_native_test=True)
    errors = [f"{i.category}: {i.message}" for i in rep.issues if i.severity == "ERROR"]
    assert rep.is_valid, errors
    sem = [i for i in check_semantics(PktPackage.open(pkt).get_xaml_text()) if i.severity == "ERROR"]
    assert not sem, [i.message for i in sem]
    if HAS_SAC:
        assert rep.tier3_native_ok, errors


def _xaml(pkt: Path) -> str:
    return PktPackage.open(pkt).get_xaml_text()


def _assert_linked_after(pkt: Path, prev_ref: str, new_ref: str) -> None:
    g = _nodes(pkt)
    assert g["nodes"][prev_ref]["next_reference_id"] == new_ref


def _last_step(pkt: Path) -> str:
    g = _nodes(pkt)
    tails = [r for r, n in g["nodes"].items() if n["node_kind"] == "FlowStep" and not n["next_reference_id"]]
    assert len(tails) == 1
    return tails[0]


# ---------------------------------------------------------------------------
# add_curve
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "creation_type,kwargs,arg_key,arg_xml",
    [
        ("ArcGeneral", {"center_point": "P4"}, "CenterPoint", ">P4<"),
        ("Arc3Points", {"arc_point": "P2"}, "ArcPoint2", ">P2<"),
        ("ParabolaGeneral", {"mid_ordinate_expr": "0.2"}, "MidOrdinate", ">0.2<"),
    ],
)
def test_add_curve_each_type(tmp_path, creation_type, kwargs, arg_key, arg_xml):
    pkt = _new_pkt(tmp_path, f"Curve{creation_type}")
    _base_geometry(pkt)
    tail = _last_step(pkt)
    res = _ok(add_curve(str(pkt), "L5", "P1", "P3", creation_type=creation_type, link_codes_str='"Pipe"', **kwargs))
    ref = res["details"]["reference_id"]
    assert res["created_reference_ids"] == [ref]
    assert res["details"]["curve_argument"] == {arg_key: arg_xml.strip("<>")}
    x = _xaml(pkt)
    assert f'x:Key="{arg_key}"' in x and arg_xml in x
    assert f'CreationType="{creation_type}"' in x
    _assert_linked_after(pkt, tail, ref)
    _assert_valid(pkt)


def test_add_curve_requires_type_argument(tmp_path):
    pkt = _new_pkt(tmp_path, "CurveMissing")
    _base_geometry(pkt)
    before = _xaml(pkt)
    data = json.loads(add_curve(str(pkt), "L5", "P1", "P3", creation_type="Arc3Points"))
    assert data["success"] is False and "arc_point" in data["message"]
    assert _xaml(pkt) == before


def test_add_aux_curve(tmp_path):
    pkt = _new_pkt(tmp_path, "AuxCurve")
    _base_geometry(pkt)
    _ok(add_curve(str(pkt), "AL1", "P1", "P3", creation_type="ArcGeneral", center_point="P4", is_auxiliary=True))
    assert "CreateAuxCurve" in _xaml(pkt)
    _assert_valid(pkt)


# ---------------------------------------------------------------------------
# add_offset_geometry
# ---------------------------------------------------------------------------
def test_add_offset_geometry(tmp_path):
    pkt = _new_pkt(tmp_path, "OffsetTool")
    _base_geometry(pkt)
    tail = _last_step(pkt)
    res = _ok(add_offset_geometry(str(pkt), "O1", ["L1", "L2"], offset_distance=-0.15, offset_codes_str='"SubBase"'))
    ref = res["details"]["reference_id"]
    x = _xaml(pkt)
    assert 'Links="L1,L2"' in x  # DLL tách bằng ',' (CreateOffset.get_ComponentNames)
    _assert_linked_after(pkt, tail, ref)
    _assert_valid(pkt)

    bad = json.loads(add_offset_geometry(str(pkt), "O2", []))
    assert bad["success"] is False


# ---------------------------------------------------------------------------
# Mark Point
# ---------------------------------------------------------------------------
def test_add_get_and_set_mark_point(tmp_path):
    pkt = _new_pkt(tmp_path, "MarkPoints")
    _base_geometry(pkt)
    tail = _last_step(pkt)
    r1 = _ok(add_set_mark_point(str(pkt), "P3", "EdgePoint"))
    r2 = _ok(add_get_mark_point(str(pkt), "P11", "EdgePoint", point_codes_str='"ETW"', prev_offset_expr="3.5"))
    r3 = _ok(add_get_mark_point(str(pkt), "AP5", "[\"Other\"]", is_auxiliary=True))
    _assert_linked_after(pkt, tail, r1["details"]["reference_id"])
    _assert_linked_after(pkt, r1["details"]["reference_id"], r2["details"]["reference_id"])
    _assert_linked_after(pkt, r2["details"]["reference_id"], r3["details"]["reference_id"])
    x = _xaml(pkt)
    assert 'PrevOffset="3.5"' in x and "GetAuxMarkPointActivity" in x and "SetMarkPointActivity" in x
    _assert_valid(pkt)


# ---------------------------------------------------------------------------
# Biến nội bộ & Output Parameter
# ---------------------------------------------------------------------------
def test_define_and_set_variable(tmp_path):
    pkt = _new_pkt(tmp_path, "Variables")
    _base_geometry(pkt)
    tail = _last_step(pkt)
    d1 = _ok(add_define_variable(str(pkt), "Var_H", "Double", "P1.X * 2"))
    assert d1["details"]["default_value"] == "[P1.X * 2]"  # luôn bọc [...] như SAC GUI
    d2 = _ok(add_define_variable(str(pkt), "Var_Code", "String", '"Pave"'))
    d3 = _ok(add_define_variable(str(pkt), "Var_Flag", "YesNo", "No"))
    d4 = _ok(add_define_variable(str(pkt), "Var_N", "Integer", "3"))
    s1 = _ok(add_set_variable(str(pkt), "Var_H", "Math.Abs(P2.Y - P1.Y)"))
    assert s1["details"]["clr_type"] == "x:Double"
    s2 = _ok(add_set_variable(str(pkt), "Var_Flag", "Yes"))
    assert s2["details"]["clr_type"] == "asw:EnumType"  # suy ra từ khai báo

    chain = [tail] + [r["details"]["reference_id"] for r in (d1, d2, d3, d4, s1, s2)]
    for a, b in zip(chain, chain[1:]):
        _assert_linked_after(pkt, a, b)
    x = _xaml(pkt)
    assert 'VariableType="Yes\\No"' in x and 'VariableType="Integer"' in x
    _assert_valid(pkt)

    bad = json.loads(add_set_variable(str(pkt), "KhongCo", "1"))
    assert bad["success"] is False and "add_define_variable" in bad["message"]
    bad2 = json.loads(add_define_variable(str(pkt), "2Bad", "Double", "0"))
    assert bad2["success"] is False


def test_set_output_parameter(tmp_path):
    pkt = _new_pkt(tmp_path, "OutputParam")
    _base_geometry(pkt)
    _ok(add_parameter(str(pkt), "OutWidth", param_category="Output", data_type="Double", default_value="0"))
    _ok(add_parameter(str(pkt), "LaneWidth", param_category="Input", data_type="Double", default_value="3.5"))
    tail = _last_step(pkt)
    r = _ok(add_set_output_parameter(str(pkt), "OutWidth", "P3.X - P1.X"))
    assert r["details"]["clr_type"] == "x:Double"
    _assert_linked_after(pkt, tail, r["details"]["reference_id"])
    assert "SetOutputParameterValue.OutputParammeter" in _xaml(pkt)  # đúng chính tả DLL gốc
    _assert_valid(pkt)

    assert json.loads(add_set_output_parameter(str(pkt), "Missing", "1"))["success"] is False
    assert json.loads(add_set_output_parameter(str(pkt), "LaneWidth", "1"))["success"] is False


# ---------------------------------------------------------------------------
# add_flow_decision
# ---------------------------------------------------------------------------
def test_flow_decision_branches(tmp_path):
    pkt = _new_pkt(tmp_path, "Decision")
    _base_geometry(pkt)
    tail = _last_step(pkt)
    dec = _ok(add_flow_decision(str(pkt), "P2.Y < P1.Y", display_name="Đắp?"))
    d = dec["details"]["decision_node_id"]
    assert dec["created_reference_ids"] == [d]
    assert "element" not in dec["details"]
    assert dec["details"]["true_branch_parent_id"] == f"{d}:True"
    _assert_linked_after(pkt, tail, d)

    t1 = _ok(add_point_and_link(str(pkt), "P5", from_point="P3", param_1_expr="2", param_2_expr="-1",
                                link_name="L3", parent_node_id=f"{d}:True"))["details"]["reference_id"]
    t2 = _ok(add_set_mark_point(str(pkt), "P5", "FillToe", parent_node_id=t1))["details"]["reference_id"]
    f1 = _ok(add_point_and_link(str(pkt), "P5", from_point="P3", param_1_expr="2", param_2_expr="1",
                                link_name="L3", allow_duplicate_link=True,
                                parent_node_id=f"{d}:False"))["details"]["reference_id"]
    # Khối hội tụ: parent rỗng -> nối vào mọi đầu ra mở (cuối nhánh True và cuối nhánh False)
    j = _ok(add_report_message(str(pkt), '"Xong"', message_type="Information"))
    j_ref = j["created_reference_ids"][0]

    g = _nodes(pkt)["nodes"]
    assert g[d]["node_kind"] == "FlowDecision"
    assert g[d]["true_reference_id"] == t1
    assert g[d]["false_reference_id"] == f1
    assert g[t1]["next_reference_id"] == t2
    assert g[t2]["next_reference_id"] == j_ref
    assert g[f1]["next_reference_id"] == j_ref
    _assert_valid(pkt)


def test_flow_decision_inserted_mid_flow(tmp_path):
    pkt = _new_pkt(tmp_path, "DecisionMid")
    _base_geometry(pkt)
    g0 = _nodes(pkt)
    first = g0["start"]
    second = g0["nodes"][first]["next_reference_id"]
    d = _ok(add_flow_decision(str(pkt), "P1.X > 0", parent_node_id=first))["details"]["decision_node_id"]
    g = _nodes(pkt)["nodes"]
    assert g[first]["next_reference_id"] == d
    # Luồng cũ được nối vào cả 2 nhánh
    assert g[d]["true_reference_id"] == second and g[d]["false_reference_id"] == second
    _assert_valid(pkt)


# ---------------------------------------------------------------------------
# Sửa lỗi review chéo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("level,expected", [("Information", "Informational"), ("Informational", "Informational")])
def test_report_message_information_alias(tmp_path, level, expected):
    pkt = _new_pkt(tmp_path, f"Report{level}")
    _base_geometry(pkt)
    _ok(add_report_message(str(pkt), '"Thông báo"', message_type=level))
    assert f'ErrorLevel="{expected}"' in _xaml(pkt)
    _assert_valid(pkt)


def _link_numbers(pkt: Path) -> list:
    return [lk["link_number"] for lk in json.loads(inspect_pkt(str(pkt)))["links"]]


def test_point_and_link_link_defaults(tmp_path):
    pkt = _new_pkt(tmp_path, "LinkDefaults")
    # Lệnh đầu tiên phổ biến nhất: chỉ tạo Point, không cần add_link=False
    _ok(add_point_and_link(str(pkt), "P1", param_1_expr="0", param_2_expr="0"))
    assert _link_numbers(pkt) == []
    # Có link_name -> ngầm tạo Link
    _ok(add_point_and_link(str(pkt), "P2", from_point="P1", param_1_expr="1", param_2_expr="0", link_name="L1"))
    assert _link_numbers(pkt) == ["L1"]
    # add_link=False tường minh thắng link_name
    _ok(add_point_and_link(str(pkt), "P3", from_point="P2", param_1_expr="1", link_name="L2", add_link=False))
    assert _link_numbers(pkt) == ["L1"]
    # add_link=True mà thiếu link_name -> lỗi, file không đổi
    before = _xaml(pkt)
    r = json.loads(add_point_and_link(str(pkt), "AP1", from_point="P1", is_auxiliary=True, add_link=True))
    assert r["success"] is False and "link_name" in r["message"]
    assert _xaml(pkt) == before
    _assert_valid(pkt)


def test_point_and_link_rejects_duplicates(tmp_path):
    pkt = _new_pkt(tmp_path, "LinkSafety")
    _base_geometry(pkt)
    before = _xaml(pkt)
    r1 = json.loads(add_point_and_link(str(pkt), "P9", from_point="P3", link_name="L1"))
    assert r1["success"] is False and "L1" in r1["message"]
    r2 = json.loads(add_point_and_link(str(pkt), "P2", from_point="P3", param_1_expr="1"))
    assert r2["success"] is False and "P2" in r2["message"]
    assert _xaml(pkt) == before


DUPLICATE_CASES = [
    ("add_link L1", lambda p: add_link(p, "L1", "P2", "P1")),
    ("add_link reuse P-name", lambda p: add_link(p, "P2", "P1", "P3")),
    ("add_curve L2", lambda p: add_curve(p, "L2", "P1", "P3", creation_type="Arc3Points", arc_point="P2")),
    ("add_fillet_arc L1", lambda p: add_fillet_arc(p, "L1", "L1", "L2")),
    ("add_fillet_arc same links", lambda p: add_fillet_arc(p, "L9", "L1", "L1")),
    ("add_fillet_arc point name", lambda p: add_fillet_arc(p, "L9", "L1", "L2", start_point_name="P3")),
    ("add_offset O1", lambda p: add_offset_geometry(p, "O1", ["L1"])),
    ("add_loop LO1", lambda p: add_loop_geometry(p, "LO1", ["L1", "L2"])),
    ("add_shape S1", lambda p: add_shape(p, "S1", ["L1", "L2", "L3"])),
    ("add_intersection P1", lambda p: add_intersection_point(p, "P1", "L1", "L2")),
    ("add_get_mark_point P3", lambda p: add_get_mark_point(p, "P3", "M")),
]


@pytest.mark.parametrize("label,call", DUPLICATE_CASES, ids=[c[0] for c in DUPLICATE_CASES])
def test_every_geometry_tool_rejects_duplicate_names(tmp_path, label, call):
    pkt = _new_pkt(tmp_path, "Dups")
    _base_geometry(pkt)
    _ok(add_link(str(pkt), "L3", "P3", "P1"))
    _ok(add_offset_geometry(str(pkt), "O1", ["L1", "L2"], offset_distance=-0.1))
    _ok(add_loop_geometry(str(pkt), "LO1", ["L1", "L2"], repetition_count=2))
    _ok(add_shape(str(pkt), "S1", ["L1", "L2", "L3"]))
    before = _xaml(pkt)
    res = json.loads(call(str(pkt)))
    assert res["success"] is False, (label, res)
    assert _xaml(pkt) == before


def test_duplicate_curve_twice_and_escape_hatch(tmp_path):
    pkt = _new_pkt(tmp_path, "DupCurve")
    _base_geometry(pkt)
    _ok(add_curve(str(pkt), "AL1", "P1", "P3", center_point="P4", is_auxiliary=True))
    again = json.loads(add_curve(str(pkt), "AL1", "P1", "P3", center_point="P4", is_auxiliary=True))
    assert again["success"] is False and "AL1" in again["message"]
    # Hai nhánh loại trừ của FlowDecision được phép dùng lại tên khi chủ động cho phép
    d = _ok(add_flow_decision(str(pkt), "P1.X > 0"))["details"]["decision_node_id"]
    _ok(add_link(str(pkt), "L9", "P1", "P3", parent_node_id=f"{d}:True"))
    _ok(add_link(str(pkt), "L9", "P3", "P1", parent_node_id=f"{d}:False", allow_duplicate_name=True))
    _assert_valid(pkt)


@pytest.mark.parametrize("bad", ["Next", "if", "End", "Step", "String", "Nothing", "Mod"])
def test_define_variable_rejects_vb_keywords(tmp_path, bad):
    pkt = _new_pkt(tmp_path, "VarKw")
    _base_geometry(pkt)
    res = json.loads(add_define_variable(str(pkt), bad, "Double", "0"))
    assert res["success"] is False and "từ khóa" in res["message"]


def test_define_variable_rejects_redefine_and_shadowing(tmp_path):
    pkt = _new_pkt(tmp_path, "VarDup")
    _base_geometry(pkt)
    _ok(add_parameter(str(pkt), "LaneWidth", param_category="Input", data_type="Double", default_value="3.5"))
    _ok(add_define_variable(str(pkt), "Var_H", "Double", "0"))
    before = _xaml(pkt)
    for name in ("Var_H", "var_h", "LaneWidth", "P2", "L1"):
        res = json.loads(add_define_variable(str(pkt), name, "Double", "1"))
        assert res["success"] is False, (name, res)
    assert _xaml(pkt) == before
    assert _xaml(pkt).count("InternalVariableDefine ") == 1


def test_mutation_reports_new_tier2_warnings_only(tmp_path):
    pkt = _new_pkt(tmp_path, "Tier2Warn")
    _base_geometry(pkt)
    r = _ok(add_link(str(pkt), "L9", start_point="P1", end_point="P99"))
    new_warn = [w for w in r["warnings"] if w.startswith("Tầng 2") and "P99" in w]
    assert new_warn, r["warnings"]
    # Lần sửa sau không lặp lại cảnh báo đã có từ trước
    r2 = _ok(add_set_mark_point(str(pkt), "P2", "Mark2"))
    assert not [w for w in r2["warnings"] if "P99" in w], r2["warnings"]
