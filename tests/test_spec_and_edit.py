"""
Kiểm thử node_editor (remove_node / update_node), spec_builder (export_spec / build_from_spec)
và đăng ký tool mở rộng tools_ext.register.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from sac_mcp.core.native_suite_builder import NativeSuiteBuilder
from sac_mcp.core.node_editor import remove_node, update_node
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.spec_builder import build_from_spec, export_spec
from sac_mcp.core.validator import PktValidator
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.native.host import installed_sac_dirs

ROOT = Path(__file__).resolve().parent.parent
X_NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
HAS_SAC = bool(installed_sac_dirs())

SUITE = [
    ("01_PhuiDaoCong", NativeSuiteBuilder.build_01_phui_dao_cong),
    ("02_VetHuuCo_DanhCap", NativeSuiteBuilder.build_02_vet_huu_co_danh_cap),
    ("03_SoSanhBeMat", NativeSuiteBuilder.build_03_so_sanh_be_mat),
    ("04_KetCauDuongCu", NativeSuiteBuilder.build_04_ket_cau_duong_cu),
    ("05_TaluyDaoDapDayDu", NativeSuiteBuilder.build_05_taluy_dao_dap_day_du),
    ("06_DuongNangCapCaiTao", NativeSuiteBuilder.build_06_duong_nang_cap_cai_tao),
    ("07_KetCauMatDuongMoi", NativeSuiteBuilder.build_07_ket_cau_mat_duong_moi),
    ("08_GiaCoMaiTaluy_GiatCo", NativeSuiteBuilder.build_08_giaco_maitaluy_giatco),
    ("09_TuongChan_Cat_III_III", NativeSuiteBuilder.build_09_tuong_chan_cat_3_3),
]

TWO_LANE_SPEC = {
    "format_version": 1,
    "name": "Duong2Lan",
    "civil_version": "2026",
    "description": "Mặt đường 2 làn",
    "parameters": [
        {"name": "Side", "category": "Input", "data_type": "Side", "default": "Right",
         "display_name": "Side", "description": ""},
        {"name": "LaneWidth", "category": "Input", "data_type": "Double", "default": "3.5",
         "display_name": "Bề rộng 1 làn (m)", "description": "Bề rộng mỗi làn xe"},
        {"name": "LaneSlope", "category": "Input", "data_type": "Grade", "default": "-0.02",
         "display_name": "Độ dốc ngang (%)", "description": ""},
        {"name": "PaveDepth", "category": "Input", "data_type": "Double", "default": "0.3",
         "display_name": "Chiều dày áo đường (m)", "description": ""},
    ],
    "steps": [
        {"id": "P1", "type": "point", "point_code": "P1", "from_point": "Origin", "point_type": "DeltaX_DeltaY",
         "param_1": "0.0", "param_2": "0.0", "point_codes": ["Crown"]},
        {"id": "P2", "type": "point", "point_code": "P2", "from_point": "P1", "point_type": "Slope_DeltaX",
         "param_1": "LaneSlope", "param_2": "-LaneWidth", "point_codes": ["ETW"], "add_link": True,
         "link_name": "L1", "link_codes": ["Top", "Pave"]},
        {"id": "P3", "type": "point", "point_code": "P3", "from_point": "P1", "point_type": "Slope_DeltaX",
         "param_1": "LaneSlope", "param_2": "LaneWidth", "point_codes": ["ETW"], "add_link": True,
         "link_name": "L2", "link_codes": ["Top", "Pave"]},
        {"id": "P4", "type": "point", "point_code": "P4", "from_point": "P1", "point_type": "DeltaX_DeltaY",
         "param_1": "0.0", "param_2": "-PaveDepth"},
        {"id": "P5", "type": "point", "point_code": "P5", "from_point": "P2", "point_type": "DeltaX_DeltaY",
         "param_1": "0.0", "param_2": "-PaveDepth", "add_link": True, "link_name": "L3", "link_codes": ["Pave"]},
        {"id": "P6", "type": "point", "point_code": "P6", "from_point": "P3", "point_type": "DeltaX_DeltaY",
         "param_1": "0.0", "param_2": "-PaveDepth", "add_link": True, "link_name": "L4", "link_codes": ["Pave"]},
        {"id": "L5", "type": "link", "link_name": "L5", "start_point": "P5", "end_point": "P6",
         "link_codes": ["Datum"]},
        {"id": "S1", "type": "shape", "shape_code": "S1", "links": ["L1", "L2", "L4", "L5", "L3"],
         "shape_codes": ["Pave1"]},
        {"id": "D1", "type": "decision", "condition": "LaneWidth <= 0", "display_name": "Bề rộng làn <= 0?"},
        {"id": "R1", "type": "report", "parent": "D1:True", "message": "Bề rộng làn phải lớn hơn 0",
         "message_type": "Error"},
    ],
}


# ----------------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------------

def _edit(pkt: Path, fn):
    """Mở pkt -> fn(engine) -> lưu (kiểm định Tầng 1+2) -> trả kết quả của fn."""
    pkg = PktPackage.open(pkt)
    eng = FlowchartEngine(pkg.get_xaml_text())
    res = fn(eng)
    pkg.set_xaml_text(eng.to_xaml_string())
    pkg.save(validate=True)
    return res


def _engine(pkt: Path) -> FlowchartEngine:
    return FlowchartEngine(PktPackage.open(pkt).get_xaml_text())


def _reachable(pkt: Path):
    return [n.get(X_NAME) for n in _engine(pkt).reachable_nodes()]


def _next_of(pkt: Path, node_id: str, slot: str = "Next"):
    eng = _engine(pkt)
    idx = eng._node_index()
    tgt = eng.get_slot_target(idx[node_id], slot, idx)
    return tgt.get(X_NAME) if tgt is not None else None


def _assert_valid(pkt: Path):
    rep = PktValidator.validate_pkt(pkt, run_native_test=HAS_SAC)
    errors = [f"[{i.category}] {i.message}" for i in rep.issues if i.severity == "ERROR"]
    assert rep.is_valid, errors
    assert rep.tier1_opc_ok and rep.tier2_xaml_ok
    if HAS_SAC:
        assert rep.tier3_native_ok, errors
    return rep


def _geometry(pkt: Path):
    eng = _engine(pkt)

    def strip(items):
        return [{k: v for k, v in it.model_dump().items() if k != "flow_step_id"} for it in items]

    return (
        strip(eng.extract_points()),
        strip(eng.extract_links()),
        strip(eng.extract_shapes()),
        [p.model_dump() for p in eng.extract_parameters()],
    )


@pytest.fixture()
def two_lane(tmp_path: Path) -> Path:
    res = build_from_spec(TWO_LANE_SPEC, tmp_path / "Duong2Lan.pkt")
    return Path(res["pkt_path"])


# ----------------------------------------------------------------------------
# remove_node
# ----------------------------------------------------------------------------

def test_remove_middle_node_keeps_chain(two_lane: Path):
    before = _reachable(two_lane)
    # Bước thứ 7 (L5) là node __ReferenceID6, nằm giữa P6 (__ReferenceID5) và S1 (__ReferenceID7)
    assert _next_of(two_lane, "__ReferenceID5") == "__ReferenceID6"
    info = _edit(two_lane, lambda e: remove_node(e, "__ReferenceID6"))

    assert info["continuation_node_id"] == "__ReferenceID7"
    assert info["rewired"] == ["__ReferenceID5"]
    assert _next_of(two_lane, "__ReferenceID5") == "__ReferenceID7"
    after = _reachable(two_lane)
    assert after == [n for n in before if n != "__ReferenceID6"]
    # L5 vẫn được S1 tham chiếu -> có cảnh báo
    assert any("L5" in w and "S1" in w for w in info["warnings"])
    assert "FlowStep_7" in info["removed_view_states"]
    _assert_valid(two_lane)


def test_remove_start_node(two_lane: Path):
    info = _edit(two_lane, lambda e: remove_node(e, "__ReferenceID0"))
    assert "Flowchart.StartNode" in info["rewired"]
    eng = _engine(two_lane)
    start = eng.get_start_node(eng._node_index())
    assert start is not None and start.get(X_NAME) == "__ReferenceID1"
    assert "__ReferenceID0" not in _reachable(two_lane)
    _assert_valid(two_lane)


def test_remove_inline_nested_node_in_real_example(tmp_path: Path):
    pkt = tmp_path / "BV-TYPE1.pkt"
    shutil.copy(ROOT / "examples" / "BV-TYPE1.pkt", pkt)
    before = _reachable(pkt)
    assert _next_of(pkt, "__ReferenceID3") == "__ReferenceID4"

    info = _edit(pkt, lambda e: remove_node(e, "__ReferenceID4"))
    assert info["moved_inline_nodes"] == ["__ReferenceID5"]
    assert _next_of(pkt, "__ReferenceID3") == "__ReferenceID5"
    assert _reachable(pkt) == [n for n in before if n != "__ReferenceID4"]
    # Node bị xoá định nghĩa P5 / L4 vẫn được dùng -> cảnh báo
    assert info["warnings"] and "P5" in info["warnings"][0]
    xaml = PktPackage.open(pkt).get_xaml_text()
    assert "__ReferenceID4<" not in xaml and 'x:Name="__ReferenceID4"' not in xaml
    _assert_valid(pkt)

    # Xoá tiếp StartNode lồng inline trong <Flowchart.StartNode>
    _edit(pkt, lambda e: remove_node(e, "__ReferenceID0"))
    assert _reachable(pkt)[0] == "__ReferenceID1"
    _assert_valid(pkt)


def _decision_layout(pkt: Path, display_name: str):
    """(id decision, id node đứng trước, id nhánh True, id nhánh False) tra theo DisplayName."""
    eng = _engine(pkt)
    idx = eng._node_index()
    dec_id = next(n for n, el in idx.items() if el.get("DisplayName") == display_name)
    pred = next(
        n for n, el in idx.items()
        if any((t := eng.get_slot_target(el, s, idx)) is not None and t.get(X_NAME) == dec_id
               for s in ("Next", "True", "False"))
    )
    t = eng.get_slot_target(idx[dec_id], "True", idx)
    f = eng.get_slot_target(idx[dec_id], "False", idx)
    return dec_id, pred, t.get(X_NAME), f.get(X_NAME)


def test_remove_decision_requires_keep_branch(tmp_path: Path):
    pkt = NativeSuiteBuilder.build_05_taluy_dao_dap_day_du(tmp_path / "05.pkt")
    dec, pred, t, f = _decision_layout(pkt, "Đắp hay Đào?")
    assert t != f
    with pytest.raises(ValueError, match="keep_branch"):
        _edit(pkt, lambda e: remove_node(e, dec))

    info = _edit(pkt, lambda e: remove_node(e, dec, keep_branch="True"))
    assert info["continuation_node_id"] == t
    assert _next_of(pkt, pred) == t
    reach = _reachable(pkt)
    assert dec not in reach and t in reach
    _assert_valid(pkt)


def test_remove_decision_keep_false_warns_unreachable(tmp_path: Path):
    pkt = NativeSuiteBuilder.build_05_taluy_dao_dap_day_du(tmp_path / "05.pkt")
    dec, pred, t, f = _decision_layout(pkt, "Đắp hay Đào?")
    info = _edit(pkt, lambda e: remove_node(e, dec, keep_branch="False"))
    assert _next_of(pkt, pred) == f
    assert t in info["unreachable_nodes"]
    assert any("không còn nối vào luồng" in w for w in info["warnings"])


# ----------------------------------------------------------------------------
# update_node
# ----------------------------------------------------------------------------

def test_update_node_changes_delta_x_and_rejects_unknown_attribute(two_lane: Path):
    # P4 (__ReferenceID3) dựng bằng DeltaX_DeltaY
    info = _edit(
        two_lane,
        lambda e: update_node(e, "__ReferenceID3", {"DisplayName": "Đáy tim"}, {"DeltaX1": "LaneWidth / 2", "DeltaY1": 0.5}),
    )
    assert info["changed_arguments"]["DeltaX1"] == ["0.0", "[LaneWidth / 2]"]
    assert info["changed_arguments"]["DeltaY1"][1] == "0.5"
    p4 = next(p for p in _engine(two_lane).extract_points() if p.point_number == "P4")
    assert p4.param_1_expr == "[LaneWidth / 2]"
    _assert_valid(two_lane)

    with pytest.raises(ValueError, match="không có thuộc tính: Foo"):
        _edit(two_lane, lambda e: update_node(e, "__ReferenceID3", {"Foo": "1"}))

    # FlowDecision: sửa Condition (tự bọc [..]); không nhận arguments
    _edit(two_lane, lambda e: update_node(e, "__ReferenceID8", {"Condition": "LaneWidth < 0.5"}))
    dec = _engine(two_lane)._node_index()["__ReferenceID8"]
    assert dec.get("Condition") == "[LaneWidth < 0.5]"
    with pytest.raises(ValueError):
        _edit(two_lane, lambda e: update_node(e, "__ReferenceID8", arguments={"X": 1}))
    _assert_valid(two_lane)


def test_update_node_codes_and_typed_argument(two_lane: Path):
    _edit(
        two_lane,
        lambda e: update_node(e, "__ReferenceID1", {"PointCodes": ["ETW", "EOP"], "ApplyAOR": "True"}),
    )
    p2 = next(p for p in _engine(two_lane).extract_points() if p.point_number == "P2")
    assert p2.point_codes == "ETW, EOP"
    _assert_valid(two_lane)


# ----------------------------------------------------------------------------
# Spec
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("name,build_fn", SUITE, ids=[s[0] for s in SUITE])
def test_spec_round_trip_native_suite(tmp_path: Path, name, build_fn):
    orig = build_fn(tmp_path / f"{name}.pkt", version="2026")
    spec1 = export_spec(orig)
    assert spec1["steps"] and not spec1.get("warnings")
    assert all(st["type"] != "raw" for st in spec1["steps"])

    res = build_from_spec(json.dumps(spec1, ensure_ascii=False), tmp_path / f"{name}_rebuilt.pkt")
    rebuilt = Path(res["pkt_path"])
    assert set(res["reference_ids"]) == {st["id"] for st in spec1["steps"]}

    spec2 = export_spec(rebuilt)
    assert spec2 == spec1
    assert _geometry(rebuilt) == _geometry(orig)
    assert _reachable(rebuilt) and len(_reachable(rebuilt)) == len(_reachable(orig))
    _assert_valid(rebuilt)


def test_two_lane_example_round_trip(two_lane: Path, tmp_path: Path):
    spec = export_spec(two_lane)
    assert spec["steps"] == TWO_LANE_SPEC["steps"]
    assert spec["parameters"] == TWO_LANE_SPEC["parameters"]
    _assert_valid(two_lane)

    # Spec từ file .json
    js = tmp_path / "spec.json"
    js.write_text(json.dumps(TWO_LANE_SPEC, ensure_ascii=False), encoding="utf-8")
    res = build_from_spec(str(js), tmp_path / "from_file.pkt", civil_version="2025")
    assert res["civil_version"] == "2025"
    assert export_spec(res["pkt_path"])["civil_version"] == "2025"


def test_spec_round_trip_real_example_with_targets(tmp_path: Path):
    # LTT_Le Dat: Slope_DeltaX có OffsetTarget2 / ElevationTarget2 (đối số phụ có kiểu riêng)
    spec = export_spec(ROOT / "examples" / "LTT_Le Dat.pkt")
    p2 = next(st for st in spec["steps"] if st["id"] == "P2")
    assert p2["arguments"]["OffsetTarget2"] == {"value": "[Targ_Off]", "type": "asw:OffsetTarget"}
    res = build_from_spec(spec, tmp_path / "LeDat.pkt")
    assert export_spec(res["pkt_path"])["steps"] == spec["steps"]
    _assert_valid(Path(res["pkt_path"]))


def test_build_from_spec_bad_step_messages(tmp_path: Path):
    out = tmp_path / "bad.pkt"

    bad = json.loads(json.dumps(TWO_LANE_SPEC))
    del bad["steps"][3]["point_code"]
    with pytest.raises(ValueError, match=r"steps\[3\] \(id='P4'\).*thiếu trường bắt buộc 'point_code'"):
        build_from_spec(bad, out)

    bad = json.loads(json.dumps(TWO_LANE_SPEC))
    bad["steps"][9]["parent"] = "D9:True"
    with pytest.raises(ValueError, match=r"steps\[9\] \(id='R1'\).*'D9:True'.*TRƯỚC"):
        build_from_spec(bad, out)

    bad = json.loads(json.dumps(TWO_LANE_SPEC))
    bad["steps"][9]["parent"] = "D1"
    with pytest.raises(ValueError, match=r"steps\[9\].*D1:True"):
        build_from_spec(bad, out)

    bad = json.loads(json.dumps(TWO_LANE_SPEC))
    bad["steps"][1]["type"] = "pointt"
    with pytest.raises(ValueError, match=r"steps\[1\].*type 'pointt' không hợp lệ"):
        build_from_spec(bad, out)

    bad = json.loads(json.dumps(TWO_LANE_SPEC))
    bad["parameters"][2]["data_type"] = "Percent"
    with pytest.raises(ValueError, match=r"parameters\[2\] \('LaneSlope'\)"):
        build_from_spec(bad, out)

    assert not out.exists()


# ----------------------------------------------------------------------------
# Tool MCP
# ----------------------------------------------------------------------------

def test_tools_ext_register_and_call(two_lane: Path, tmp_path: Path):
    from sac_mcp import server, tools_ext

    mcp = server._MCPServerClass("test-ext")
    tools_ext.register(mcp, server._mutate_pkt, server._safe_tool)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"remove_node", "update_node", "export_spec", "build_from_spec"} <= names

    def call(name, args):
        res = asyncio.run(mcp.call_tool(name, args))
        content = getattr(res, "content", res)
        if isinstance(content, tuple):
            content = content[0]
        return json.loads(content[0].text)

    out_json = tmp_path / "spec.json"
    r = call("export_spec", {"pkt_path": str(two_lane), "output_json_path": str(out_json)})
    assert r["success"] and out_json.exists() and r["step_count"] == len(TWO_LANE_SPEC["steps"])

    r = call("build_from_spec", {"spec_json": str(out_json), "output_path": str(tmp_path / "rb.pkt")})
    assert r["success"], r
    assert r["details"]["step_reference_ids"]["S1"] == "__ReferenceID7"

    r = call("update_node", {"pkt_path": str(tmp_path / "rb.pkt"), "node_id": "__ReferenceID3",
                             "arguments": {"DeltaY1": "-PaveDepth * 2"}})
    assert r["success"], r
    r = call("update_node", {"pkt_path": str(tmp_path / "rb.pkt"), "node_id": "__ReferenceID3",
                             "attributes": {"NotAProp": "1"}})
    assert r["success"] is False and "NotAProp" in r["message"]

    r = call("remove_node", {"pkt_path": str(tmp_path / "rb.pkt"), "node_id": "__ReferenceID8",
                             "keep_branch": "False"})
    assert r["success"], r
    assert r["details"]["continuation_node_id"] is None  # nhánh False của D1 đang trống

    r = call("build_from_spec", {"spec_json": "{\"name\": \"X\", \"steps\": [{\"type\": \"point\"}]}",
                                 "output_path": str(tmp_path / "x.pkt")})
    assert r["success"] is False and "steps[0]" in r["message"]


# ----------------------------------------------------------------------------
# Vòng 2: file SAC thật có Flowchart con / chuỗi rỗng, và các tool mới của server
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("example", ["99.pkt", "HEM_KCAD TANG CUONG.pkt"])
def test_raw_steps_rebuild_valid(tmp_path: Path, example: str):
    # 99.pkt: Sequence chứa <x:String></x:String> (chuỗi rỗng); HEM: Flowchart con có x:Name trùng với file đích
    spec = export_spec(ROOT / "examples" / example)
    assert any(st["type"] == "raw" for st in spec["steps"])
    res = build_from_spec(spec, tmp_path / "rb.pkt")
    xaml = PktPackage.open(res["pkt_path"]).get_xaml_text()
    assert "<x:String/>" not in xaml
    spec2 = export_spec(res["pkt_path"])
    strip = lambda s: [{k: v for k, v in st.items() if k != "xml"} for st in s["steps"]]  # noqa: E731
    assert strip(spec2) == strip(spec)
    assert spec2["parameters"] == spec["parameters"]
    _assert_valid(Path(res["pkt_path"]))


def test_server_tools_round_trip_and_edit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAC_MCP_NATIVE_ON_SAVE", "0")
    from sac_mcp import server as S

    p = str(tmp_path / "all.pkt")

    def ok(r):
        r = json.loads(r)
        assert r.get("success", True), r
        return r

    ok(S.create_pkt_from_template(output_path=p, subassembly_name="AllTools", civil_version="2026"))
    ok(S.add_parameter(pkt_path=p, name="W", default_value="3.0"))
    ok(S.add_parameter(pkt_path=p, name="OutH", param_category="Output"))
    ok(S.add_parameter(pkt_path=p, name="UseX", data_type="YesNo", default_value="No"))
    ok(S.add_define_variable(pkt_path=p, variable_name="Half", default_value_expr="W / 2"))
    ok(S.add_define_variable(pkt_path=p, variable_name="Flag", variable_type="YesNo", default_value_expr="Yes"))
    ok(S.add_set_variable(pkt_path=p, variable_name="Half", value_expr="W / 2.5"))
    ok(S.add_point_and_link(pkt_path=p, point_code="P1"))
    ok(S.add_point_and_link(pkt_path=p, point_code="P2", from_point="P1", param_1_expr="W", link_name="L1"))
    ok(S.add_point_and_link(pkt_path=p, point_code="P3", from_point="P1", param_1_expr="Half",
                            param_2_expr="-0.5", link_name="L2"))
    ok(S.add_set_mark_point(pkt_path=p, point_number="P2", mark_name="Edge"))
    ok(S.add_get_mark_point(pkt_path=p, point_number="P4", mark_name="Edge", prev_offset_expr="P2.X",
                            prev_delta_elevation_expr="0.1"))
    ok(S.add_curve(pkt_path=p, link_number="C1", start_point="P2", end_point="P3", center_point="P1"))
    ok(S.add_curve(pkt_path=p, link_number="C2", start_point="P2", end_point="P3", creation_type="Arc3Points",
                   arc_point="P4"))
    ok(S.add_curve(pkt_path=p, link_number="C3", start_point="P1", end_point="P3",
                   creation_type="ParabolaGeneral", mid_ordinate_expr="W / 10"))
    ok(S.add_offset_geometry(pkt_path=p, offset_code="O1", links=["L1"], offset_distance=0.2))
    ok(S.add_set_output_parameter(pkt_path=p, parameter_name="OutH", value_expr="P3.Y - P1.Y"))
    dec = ok(S.add_flow_decision(pkt_path=p, condition_expr="W > 4", display_name="Rộng?"))["created_reference_ids"][0]
    ok(S.add_point_and_link(pkt_path=p, point_code="P5", from_point="P2", param_1_expr="1",
                            parent_node_id=f"{dec}:True"))
    ok(S.add_report_message(pkt_path=p, message_expr="Hẹp", parent_node_id=f"{dec}:False"))

    spec = export_spec(p)
    assert not spec.get("warnings")
    by_id = {st["id"]: st for st in spec["steps"]}
    # Không có ghi đè DisplayName thừa: export khớp mặc định mới của builder
    assert not any("attributes" in st for st in spec["steps"]), [st for st in spec["steps"] if "attributes" in st]
    assert by_id["C1"]["center_point"] == "P1"
    assert by_id["C2"]["arc_point"] == "P4" and by_id["C2"]["creation_type"] == "Arc3Points"
    assert by_id["C3"]["mid_ordinate"] == "W / 10"
    assert by_id["P4"]["prev_offset"] == "P2.X" and by_id["P4"]["prev_delta_elevation"] == "0.1"
    assert by_id["def_Flag"]["var_type"] == "YesNo"
    assert by_id["R1"]["parent"] == "D1:False" and by_id["P5"]["parent"] == "D1:True"

    res = build_from_spec(spec, tmp_path / "rb.pkt")
    rb = Path(res["pkt_path"])
    assert export_spec(rb) == spec
    assert _geometry(rb) == _geometry(Path(p))
    _assert_valid(rb)

    ids = res["reference_ids"]
    info = _edit(rb, lambda e: update_node(e, ids["C2"], arguments={"ArcPoint2": "P5"}))
    assert info["changed_arguments"]["ArcPoint2"] == ["P4", "P5"]
    info = _edit(rb, lambda e: update_node(e, ids["C3"], arguments={"MidOrdinate": "W / 8"}))
    assert info["changed_arguments"]["MidOrdinate"] == ["[W / 10]", "[W / 8]"]
    info = _edit(rb, lambda e: remove_node(e, ids["D1"], keep_branch="True"))
    assert info["continuation_node_id"] == ids["P5"]
    assert info["unreachable_nodes"] == [ids["R1"]]
    assert export_spec(rb)["steps"][-1]["id"] == "P5"
    _assert_valid(rb)


# ----------------------------------------------------------------------------
# Vòng 3: update_node - định dạng thuộc tính số, CreationType của cung, đổi tên, đổi kiểu biến
# ----------------------------------------------------------------------------

ALL_TOOLS_SPEC = {
    "format_version": 1, "name": "AllTools", "civil_version": "2026", "description": "",
    "parameters": [
        {"name": "Side", "category": "Input", "data_type": "Side", "default": "Right", "display_name": "Side",
         "description": ""},
        {"name": "W", "category": "Input", "data_type": "Double", "default": "3.0", "display_name": "W",
         "description": ""},
        {"name": "OutH", "category": "Output", "data_type": "Double", "default": None, "display_name": "OutH",
         "description": ""},
    ],
    "steps": [
        {"id": "def_K", "type": "define_variable", "name": "K", "var_type": "Double", "default": "1"},
        {"id": "set_K", "type": "set_variable", "name": "K", "value": "2"},
        {"id": "def_Flag", "type": "define_variable", "name": "Flag", "var_type": "YesNo", "default": "Yes"},
        {"id": "set_Flag", "type": "set_variable", "name": "Flag", "value": "No"},
        {"id": "P1", "type": "point", "point_code": "P1"},
        {"id": "P2", "type": "point", "point_code": "P2", "from_point": "P1", "param_1": "W",
         "add_link": True, "link_name": "L1"},
        {"id": "P3", "type": "point", "point_code": "P3", "from_point": "P1", "param_1": "W / 2",
         "param_2": "-0.5", "add_link": True, "link_name": "L2"},
        {"id": "mark1", "type": "set_mark_point", "point_number": "P2", "mark_name": "Edge"},
        {"id": "P4", "type": "get_mark_point", "point_number": "P4", "mark_name": "Edge", "prev_offset": "P2.X"},
        {"id": "C1", "type": "curve", "link_number": "C1", "start_point": "P2", "end_point": "P3",
         "center_point": "P1"},
        {"id": "O1", "type": "offset", "offset_code": "O1", "links": ["L1"], "offset_distance": 0.2},
        {"id": "S1", "type": "shape", "shape_code": "S1", "links": ["L1", "L2"]},
        {"id": "out_OutH", "type": "set_output", "name": "OutH", "value": "P2.Y - P1.Y"},
        {"id": "P5", "type": "point", "point_code": "P5", "from_point": "P2", "param_1": "1"},
    ],
}


@pytest.fixture()
def all_tools(tmp_path: Path):
    res = build_from_spec(ALL_TOOLS_SPEC, tmp_path / "all.pkt")
    return Path(res["pkt_path"]), res["reference_ids"]


def test_set_variable_infers_declared_type(all_tools):
    # set_variable không ghi var_type: builder suy ra kiểu từ khai báo (Flag là YesNo -> asw:EnumType)
    pkt, _ = all_tools
    _assert_valid(pkt)
    spec = export_spec(pkt)
    by_id = {st["id"]: st for st in spec["steps"]}
    assert by_id["set_Flag"]["var_type"] == "YesNo"


def test_update_numeric_attributes_are_bracketed(all_tools):
    pkt, ids = all_tools
    info = _edit(pkt, lambda e: update_node(e, ids["C1"], {"NoIncrements": "CInt(W * 2)"}))
    assert info["changed_attributes"]["NoIncrements"][1] == "[CInt(W * 2)]"
    info = _edit(pkt, lambda e: update_node(e, ids["O1"], {"OffsetDistance": "-W/10", "DisplayName": "Off 1"}))
    assert info["changed_attributes"]["OffsetDistance"][1] == "[-W/10]"
    assert info["changed_attributes"]["DisplayName"][1] == "Off 1"
    info = _edit(pkt, lambda e: update_node(e, ids["C1"], {"NoIncrements": 12, "EndPoint": "P4"}))
    assert info["changed_attributes"]["NoIncrements"][1] == "12"
    assert info["changed_attributes"]["EndPoint"][1] == "P4"
    _assert_valid(pkt)


def test_update_curve_creation_type_requires_matching_argument(all_tools):
    pkt, ids = all_tools
    with pytest.raises(ValueError, match="cần đối số 'ArcPoint2'"):
        _edit(pkt, lambda e: update_node(e, ids["C1"], {"CreationType": "Arc3Points"}))
    info = _edit(pkt, lambda e: update_node(e, ids["C1"], {"CreationType": "Arc3Points"}, {"ArcPoint2": "P4"}))
    assert info["changed_arguments"]["CenterPoint"] == ["P1", None]  # đối số của kiểu cũ bị xoá
    c1 = {st["id"]: st for st in export_spec(pkt)["steps"]}["C1"]
    assert c1["creation_type"] == "Arc3Points" and c1["arc_point"] == "P4" and "center_point" not in c1
    _edit(pkt, lambda e: update_node(e, ids["C1"], {"CreationType": "ParabolaGeneral"}, {"MidOrdinate": "W / 10"}))
    _assert_valid(pkt)


def test_update_rename_point_updates_references(all_tools):
    pkt, ids = all_tools
    info = _edit(pkt, lambda e: update_node(e, ids["P2"], {"PointNumber": "P20", "DisplayName": "P20&L1"}))
    refs = " | ".join(info["renamed_references"])
    for expected in ("FromPoint", "StartPoint", "SetMarkPointActivity", "PrevOffset", "Value"):
        assert expected in refs, refs
    by_id = {st["id"]: st for st in export_spec(pkt)["steps"]}
    assert by_id["P5"]["from_point"] == "P20"
    assert by_id["C1"]["start_point"] == "P20"
    assert by_id["mark1"]["point_number"] == "P20"
    assert by_id["P4"]["prev_offset"] == "P20.X"
    assert by_id["out_OutH"]["value"] == "P20.Y - P1.Y"
    _assert_valid(pkt)

    # Đổi tên Link (AutoLinkGeometryName) -> cập nhật Links của Shape / Offset
    _edit(pkt, lambda e: update_node(e, ids["P2"], {"AutoLinkGeometryName": "L10"}))
    by_id = {st["id"]: st for st in export_spec(pkt)["steps"]}
    assert by_id["S1"]["links"] == ["L10", "L2"] and by_id["O1"]["links"] == ["L10"]
    _assert_valid(pkt)


def test_update_rename_without_references_warns(all_tools):
    pkt, ids = all_tools
    info = _edit(pkt, lambda e: update_node(e, ids["P3"], {"PointNumber": "P30"}, rename_references=False))
    assert not info["renamed_references"]
    assert info["warnings"] and "P3" in info["warnings"][0] and "C1" in info["warnings"][0]


def test_update_variable_type_updates_declaration(all_tools):
    pkt, ids = all_tools
    info = _edit(pkt, lambda e: update_node(e, ids["def_K"], {"VariableType": "Integer"}))
    assert info["changed_attributes"]["VariableType"] == ["Double", "Integer"]
    eng = _engine(pkt)
    var = eng.get_flowchart_element().xpath(".//*[local-name()='Variable' and @Name='K']")[0]
    assert var.get("{http://schemas.microsoft.com/winfx/2006/xaml}TypeArguments") == "x:Int32"
    assert {st["id"]: st for st in export_spec(pkt)["steps"]}["set_K"]["var_type"] == "Integer"
    _assert_valid(pkt)
    with pytest.raises(ValueError, match="VariableName"):
        _edit(pkt, lambda e: update_node(e, ids["def_K"], {"VariableName": "K2"}))
