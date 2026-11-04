"""
Kiểm thử Giai đoạn 0:
  - Nối Flowchart: chèn giữa không làm đứt luồng, nhánh FlowDecision hội tụ đúng.
  - Lưu an toàn: kiểm định trước khi ghi, file gốc giữ nguyên khi lỗi, có bản .bak.
  - Lỗi có cấu trúc thay cho traceback.
  - Không ghi đè template.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sac_mcp.core.opc_package import PktPackage, PktValidationError
from sac_mcp.core.version_manager import VersionManager
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.server import (
    add_point_and_link,
    add_report_message,
    create_pkt_from_template,
    ensure_default_templates_exist,
    inspect_pkt,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _graph(pkt: Path) -> tuple[str, dict]:
    data = json.loads(inspect_pkt(str(pkt)))
    return data["start_node_id"], {n["reference_id"]: n for n in data["flowchart_nodes"]}


def _walk(start: str, nodes: dict) -> list[str]:
    """Danh sách display_name theo luồng chính (đi theo Next / nhánh False)."""
    names, cur, seen = [], start, set()
    while cur and cur not in seen:
        seen.add(cur)
        node = nodes[cur]
        names.append(node["display_name"])
        cur = node.get("next_reference_id") or node.get("false_reference_id")
    return names


def _new_pkt(tmp_path: Path, name: str = "T") -> Path:
    pkt = tmp_path / f"{name}.pkt"
    res = json.loads(create_pkt_from_template(str(pkt), name, civil_version="2026"))
    assert res["success"] is True
    return pkt


def _add_point(pkt: Path, code: str, **kw) -> dict:
    res = json.loads(
        add_point_and_link(str(pkt), code, param_1_expr="1", param_2_expr="0", link_name=f"L{code}", **kw)
    )
    return res


def test_insert_in_middle_keeps_downstream_chain(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    ids = [_add_point(pkt, f"P{i}")["created_reference_ids"][0] for i in (1, 2, 3)]

    res = _add_point(pkt, "P9", parent_node_id=ids[0])
    assert res["success"] is True
    assert res["details"]["linked_from_reference_id"] == ids[0]

    start, nodes = _graph(pkt)
    assert _walk(start, nodes) == ["P1&LP1", "P9&LP9", "P2&LP2", "P3&LP3"]


def test_conditional_report_both_branches_continue(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    _add_point(pkt, "P1")
    rep = json.loads(add_report_message(str(pkt), '"Canh bao"', condition_expr="1 > 0"))
    assert rep["success"] is True
    dec_id, msg_id = rep["details"]["decision_node_id"], rep["details"]["report_node_id"]

    p2 = _add_point(pkt, "P2")
    p2_id = p2["created_reference_ids"][0]
    # P2 được nối từ 2 đầu ra (Decision.False và ReportMessage.Next) -> có cảnh báo hội tụ
    assert any("hội tụ" in w for w in p2["warnings"])

    _, nodes = _graph(pkt)
    dec = nodes[dec_id]
    assert dec["true_reference_id"] == msg_id
    assert dec["false_reference_id"] == p2_id
    assert nodes[msg_id]["next_reference_id"] == p2_id
    # Condition phải được bọc [...] để WF4 hiểu là biểu thức VB
    assert dec["display_name"] == "[1 > 0]"


def test_conditional_report_inserted_mid_chain(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    p1 = _add_point(pkt, "P1")["created_reference_ids"][0]
    p2 = _add_point(pkt, "P2")["created_reference_ids"][0]

    rep = json.loads(add_report_message(str(pkt), '"x"', condition_expr="1 > 0", parent_node_id=p1))
    dec_id, msg_id = rep["details"]["decision_node_id"], rep["details"]["report_node_id"]

    _, nodes = _graph(pkt)
    assert nodes[p1]["next_reference_id"] == dec_id
    assert nodes[dec_id]["false_reference_id"] == p2
    assert nodes[msg_id]["next_reference_id"] == p2


def test_decision_parent_branch_selection(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    _add_point(pkt, "P1")
    rep = json.loads(add_report_message(str(pkt), '"x"', condition_expr="1 > 0"))
    dec_id, msg_id = rep["details"]["decision_node_id"], rep["details"]["report_node_id"]
    _add_point(pkt, "P2")

    # Decision đã đủ 2 nhánh -> không chỉ rõ nhánh thì phải báo lỗi, file giữ nguyên
    before = pkt.read_bytes()
    err = _add_point(pkt, "P8", parent_node_id=dec_id)
    assert err["success"] is False
    assert err["error_type"] == "ValueError"
    assert pkt.read_bytes() == before

    # Chỉ rõ nhánh True -> P8 chèn giữa Decision và ReportMessage
    ok = _add_point(pkt, "P8", parent_node_id=f"{dec_id}:True")
    assert ok["success"] is True
    _, nodes = _graph(pkt)
    p8 = ok["created_reference_ids"][0]
    assert nodes[dec_id]["true_reference_id"] == p8
    assert nodes[p8]["next_reference_id"] == msg_id


def test_unknown_parent_returns_structured_error(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    _add_point(pkt, "P1")
    before = pkt.read_bytes()

    err = _add_point(pkt, "P2", parent_node_id="__ReferenceID999")
    assert err["success"] is False
    assert "__ReferenceID999" in err["message"]
    assert pkt.read_bytes() == before


def test_missing_file_returns_structured_error(tmp_path: Path) -> None:
    err = json.loads(inspect_pkt(str(tmp_path / "khong_co.pkt")))
    assert err["success"] is False
    assert err["error_type"] == "FileNotFoundError"
    assert err["hint"]


def test_mutation_creates_backup(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    before = pkt.read_bytes()
    res = _add_point(pkt, "P1")
    assert res["backup_path"] == str(pkt.with_name(pkt.name + ".bak"))
    assert Path(res["backup_path"]).read_bytes() == before


def test_save_rejects_new_validation_errors_and_keeps_original(tmp_path: Path) -> None:
    pkt = _new_pkt(tmp_path)
    original = pkt.read_bytes()

    pkg = PktPackage.open(pkt)
    xaml_name = pkg.find_xaml_filename()
    # Thêm header <?xml ...> -> lỗi Tầng 2 mới
    pkg.files[xaml_name] = b'\xef\xbb\xbf<?xml version="1.0"?>' + pkg.files[xaml_name][3:]
    with pytest.raises(PktValidationError):
        pkg.save(backup=True, validate=True)

    assert pkt.read_bytes() == original
    assert not pkt.with_name(pkt.name + ".bak").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_save_tolerates_preexisting_errors(tmp_path: Path) -> None:
    """File gốc đã có lỗi (vd. thiếu .cdmd) vẫn sửa được, miễn không phát sinh lỗi mới."""
    pkt = _new_pkt(tmp_path)
    pkg = PktPackage.open(pkt)
    cdmd = next(n for n in pkg.files if n.endswith(".cdmd"))
    del pkg.files[cdmd]
    pkg.save()

    res = _add_point(pkt, "P1")
    assert res["success"] is True


def test_splice_into_inline_nested_example(tmp_path: Path) -> None:
    """File SAC thật lồng FlowStep inline: chèn giữa vẫn giữ đủ node trong luồng."""
    pkt = tmp_path / "BV.pkt"
    shutil.copy2(EXAMPLES_DIR / "BV-TYPE1.pkt", pkt)

    engine = FlowchartEngine(PktPackage.open(pkt).get_xaml_text())
    before_reachable = len(engine.reachable_nodes())
    start_id = engine.reachable_nodes()[0].get(engine.qn("x", "Name"))

    res = _add_point(pkt, "P99", parent_node_id=start_id)
    assert res["success"] is True

    engine = FlowchartEngine(PktPackage.open(pkt).get_xaml_text())
    assert len(engine.reachable_nodes()) == before_reachable + 1
    assert len(engine.find_open_exits()) == 1


def test_ensure_templates_does_not_overwrite_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(VersionManager, "TEMPLATES_DIR", tmp_path)
    ensure_default_templates_exist()
    snapshot = {p.name: p.read_bytes() for p in tmp_path.glob("*.pkt")}
    assert len(snapshot) == 3

    ensure_default_templates_exist()
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.pkt")} == snapshot

    ensure_default_templates_exist(overwrite=True)
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.pkt")} != snapshot
