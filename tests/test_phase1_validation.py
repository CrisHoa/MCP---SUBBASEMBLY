"""
Kiểm thử Giai đoạn 1: validator thực sự bắt lỗi.
  - Tầng 2 tĩnh (không cần cài SAC): activity / thuộc tính / đối số bắt buộc, x:Reference, node mồ côi,
    tham chiếu Point / Link.
  - Tầng 3 (cần cài SAC, tự bỏ qua nếu không có): biên dịch biểu thức VB bằng DLL gốc, chọn đúng phiên bản,
    tiến trình chạy nền không bị "nhiễm" giữa các file.
  - Tool sửa file trả lỗi Tầng 3 dưới dạng cảnh báo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import pytest

from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.semantic_checks import check_semantics, load_activity_catalog
from sac_mcp.core.validator import PktValidator
from sac_mcp.native import host
from sac_mcp.server import (
    add_fillet_arc,
    add_parameter,
    add_point_and_link,
    add_strip_surface,
    create_pkt_from_template,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
needs_sac = pytest.mark.skipif(not host.installed_sac_dirs(), reason="Máy không cài Subassembly Composer")


# ----------------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------------

def _good_pkt(tmp_path: Path, name: str = "Good") -> Path:
    pkt = tmp_path / f"{name}.pkt"
    create_pkt_from_template(str(pkt), name, civil_version="2026")
    add_parameter(str(pkt), "LaneWidth", default_value="3.5")
    add_point_and_link(str(pkt), "P1", param_1_expr="0", param_2_expr="0", add_link=False)
    add_point_and_link(str(pkt), "P2", from_point="P1", param_1_expr="LaneWidth", param_2_expr="0", link_name="L1")
    return pkt


def _mutated(src: Path, dst: Path, fn: Callable[[str], str]) -> Path:
    pkg = PktPackage.open(src)
    before = pkg.get_xaml_text()
    after = fn(before)
    assert after != before, "phép biến đổi không thay đổi XAML"
    pkg.set_xaml_text(after)
    pkg.save(dst)
    return dst


def _categories(issues) -> set:
    return {i.category for i in issues}


# ----------------------------------------------------------------------------
# Tầng 2 tĩnh
# ----------------------------------------------------------------------------

def test_catalog_has_required_arguments() -> None:
    cat = load_activity_catalog()
    assert "CreatePoint" in cat and "StripSurfaceActivity" in cat
    assert {"StartPointName", "EndPointName", "LinkNumber", "Surface"} <= cat["StripSurfaceActivity"].required
    assert "ApplyAOR" not in cat["FilletArcActivity"].properties


def test_good_file_has_no_static_errors(tmp_path: Path) -> None:
    pkt = _good_pkt(tmp_path)
    issues = check_semantics(PktPackage.open(pkt).get_xaml_text())
    assert [i for i in issues if i.severity == "ERROR"] == []


@pytest.mark.parametrize(
    "case, transform, expected",
    [
        ("unknown_activity", lambda x: re.sub(r"(</?\w+:)CreatePoint\b", r"\1CreatePointXYZ", x),
         "ACTIVITY_UNKNOWN"),
        ("unknown_attribute", lambda x: x.replace('ApplyAOR="False"', 'ApplyAOR="False" RoundRadius="1"', 1),
         "ATTRIBUTE_UNKNOWN"),
        ("missing_required", lambda x: x.replace('SubassemblyRunMode="[SubassemblyRunMode]"', "", 1),
         "ARGUMENT_REQUIRED"),
        ("dangling_reference", lambda x: x.replace("<x:Reference>__ReferenceID1</x:Reference>",
                                                   "<x:Reference>__ReferenceID999</x:Reference>", 1),
         "FLOW_REFERENCE"),
        ("unreachable_node", lambda x: x.replace("<x:Reference>__ReferenceID1</x:Reference>", "<x:Null />", 1)
         .replace("<FlowStep.Next>\n        <x:Null />\n      </FlowStep.Next>", "", 1),
         "FLOW_UNREACHABLE"),
        ("undefined_point", lambda x: x.replace('FromPoint="P1"', 'FromPoint="P99"', 1),
         "GEOMETRY_REFERENCE"),
    ],
)
def test_static_checks_detect(tmp_path: Path, case: str, transform, expected: str) -> None:
    good = _good_pkt(tmp_path)
    bad = _mutated(good, tmp_path / f"{case}.pkt", transform)
    issues = check_semantics(PktPackage.open(bad).get_xaml_text())
    assert expected in _categories(issues), [i.message for i in issues]

    rep = PktValidator.validate_pkt(bad, run_native_test=False)
    severity = {i.category: i.severity for i in issues}[expected]
    assert rep.tier2_xaml_ok is (severity != "ERROR")


def test_static_checks_have_no_false_positives_on_examples() -> None:
    noisy = {}
    for pkt in sorted(EXAMPLES_DIR.rglob("*.pkt")):
        try:
            xaml = PktPackage.open(pkt).get_xaml_text()
        except Exception:
            continue  # gói hỏng / gói DLL: thuộc phạm vi Tầng 1
        found = [i.message for i in check_semantics(xaml)]
        if found:
            noisy[pkt.name] = found
    assert noisy == {}


def test_open_and_resave_keeps_examples_valid(tmp_path: Path) -> None:
    """Mở rồi lưu lại không đổi gì không được làm hỏng file (VD <x:String></x:String> trong 99.pkt)."""
    broken = {}
    for src in sorted(EXAMPLES_DIR.rglob("*.pkt")):
        dst = tmp_path / src.name
        dst.write_bytes(src.read_bytes())
        if not PktValidator.validate_pkt(dst, run_native_test=False).is_valid:
            continue
        pkg = PktPackage.open(dst)
        from sac_mcp.core.xaml_engine import FlowchartEngine

        pkg.set_xaml_text(FlowchartEngine(pkg.get_xaml_text()).to_xaml_string())
        pkg.save()
        rep = PktValidator.validate_pkt(dst)
        if not rep.is_valid:
            broken[src.name] = [i.message for i in rep.issues if i.severity == "ERROR"]
    assert broken == {}


# ----------------------------------------------------------------------------
# Tầng 3: DLL gốc của Subassembly Composer
# ----------------------------------------------------------------------------

@needs_sac
def test_native_catches_vb_errors_with_location(tmp_path: Path) -> None:
    good = _good_pkt(tmp_path)
    undeclared = _mutated(good, tmp_path / "undeclared.pkt", lambda x: x.replace("[LaneWidth]", "[LaneWidthh * 2]", 1))
    syntax = _mutated(good, tmp_path / "syntax.pkt", lambda x: x.replace("[LaneWidth]", "[LaneWidth +* (]", 1))

    rep = PktValidator.validate_pkt(undeclared)
    assert rep.tier2_xaml_ok and not rep.tier3_native_ok
    vb = [i for i in rep.issues if i.category == "VB_EXPRESSION"]
    assert vb and "LaneWidthh" in vb[0].message and "is not declared" in vb[0].message
    assert vb[0].location and "P2" in vb[0].location and "DeltaX1" in vb[0].location

    rep = PktValidator.validate_pkt(syntax)
    assert any(i.category == "VB_EXPRESSION" for i in rep.issues)


@needs_sac
def test_native_host_is_not_poisoned_between_files(tmp_path: Path) -> None:
    good = _good_pkt(tmp_path)
    bad = _mutated(good, tmp_path / "bad.pkt", lambda x: x.replace("[LaneWidth]", "[KhongCo]", 1))
    order = [bad, good, bad, good]
    results = [host.check_pkt(p, "2026", document_check=(i == 1)) for i, p in enumerate(order)]
    assert [r.validation_ok for r in results] == [False, True, False, True]
    assert results[1].document_ok is True


@needs_sac
def test_native_uses_matching_sac_version() -> None:
    dirs = host.installed_sac_dirs()
    for ver in dirs:
        ver_used, path = host.select_sac_dir(ver)
        assert ver_used == ver and path == dirs[ver]
    hem = EXAMPLES_DIR / "HEM_KCAD TANG CUONG.pkt"  # file Civil 3D 2024
    if "2024" in dirs:
        assert PktValidator.validate_pkt(hem).metadata["sac_version"] == "2024"


@needs_sac
def test_all_valid_examples_pass_native() -> None:
    failed = {}
    for pkt in sorted(EXAMPLES_DIR.rglob("*.pkt")):
        rep = PktValidator.validate_pkt(pkt)
        if rep.tier1_opc_ok and rep.tier2_xaml_ok and not rep.tier3_native_ok:
            failed[pkt.name] = [i.message for i in rep.issues if i.severity == "ERROR"]
    assert failed == {}


# ----------------------------------------------------------------------------
# Tool MCP
# ----------------------------------------------------------------------------

@needs_sac
def test_mutation_reports_native_errors_as_warnings(tmp_path: Path) -> None:
    pkt = tmp_path / "W.pkt"
    create_pkt_from_template(str(pkt), "W", civil_version="2026")
    res = json.loads(add_point_and_link(str(pkt), "P1", param_1_expr="B_Le", param_2_expr="0", link_name="L1"))
    assert res["success"] is True
    assert any("B_Le" in w and "VB_EXPRESSION" in w for w in res["warnings"])

    res = json.loads(add_parameter(str(pkt), "B_Le", default_value="0.5"))
    assert not any(w.startswith("Tầng 3") for w in res["warnings"])


def test_fillet_requires_second_link(tmp_path: Path) -> None:
    pkt = _good_pkt(tmp_path)
    res = json.loads(add_fillet_arc(str(pkt), "L9", first_link="L1", second_link=""))
    assert res["success"] is False and "second_link" in res["message"]


def test_builders_emit_required_arguments(tmp_path: Path) -> None:
    pkt = _good_pkt(tmp_path)
    add_parameter(str(pkt), "EG", param_category="Target", data_type="SurfaceTarget")
    add_point_and_link(str(pkt), "P3", from_point="P2", param_1_expr="0", param_2_expr="-0.2", link_name="L2")
    fil = json.loads(add_fillet_arc(str(pkt), "L5", first_link="L1", second_link="L2", round_radius=0.05))
    strip = json.loads(add_strip_surface(str(pkt), "BocHuuCo", depth_expr="0.3", end_point_name="P8"))
    assert fil["success"] and strip["success"]
    assert any("tự đặt tên" in w for w in strip["warnings"])

    issues = check_semantics(PktPackage.open(pkt).get_xaml_text())
    assert not [i for i in issues if i.category in ("ARGUMENT_REQUIRED", "ATTRIBUTE_UNKNOWN")]
