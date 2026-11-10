"""
Đồng bộ Parameter sang <guid>.atc phải giống cách Subassembly Composer tự ghi
(đối chiếu examples/99.pkt và file 09_TuongChan do SAC 2025 lưu lại):
  - Target không có trong .atc.
  - Side / YesNo ghi mã số enum kèm khối <Enum>.
  - Slope / Grade ghi số thuần với TypeInfo 10 / 9.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.sac_enums import enum_xaml_default
from sac_mcp.core.validator import PktValidator
from sac_mcp.native.host import installed_sac_dirs
from sac_mcp.server import add_parameter, create_pkt_from_template


def _params(pkg: PktPackage) -> dict:
    root = etree.fromstring(pkg.files[pkg.find_atc_filename()])
    return {etree.QName(e).localname: e for e in root.xpath("//*[local-name()='Params']/*")}


def _new_pkg(tmp_path: Path) -> PktPackage:
    return PktPackage.create_from_template(tmp_path / "A.pkt", "AtcTest", civil_version="2026")


def test_targets_are_not_written_and_are_removed(tmp_path: Path) -> None:
    pkg = _new_pkg(tmp_path)
    for name, dt in (("EG", "SurfaceTarget"), ("OffT", "OffsetTarget"), ("ElT", "ElevationTarget")):
        pkg.sync_parameter_to_atc(name, dt, "-9999", name, name)
    assert not {"EG", "OffT", "ElT"} & set(_params(pkg))

    # File cũ đã ghi nhầm Target vào .atc -> lần đồng bộ sau xoá đi
    pkg.sync_parameter_to_atc("EG", "Double", "0", "EG", "EG")
    assert "EG" in _params(pkg)
    pkg.sync_parameter_to_atc("EG", "SurfaceTarget", "-9999", "EG", "EG")
    assert "EG" not in _params(pkg)


def test_enum_values_are_numeric_codes(tmp_path: Path) -> None:
    pkg = _new_pkg(tmp_path)
    pkg.sync_parameter_to_atc("Side", "Side", "Right", "Phía", "Phía")
    pkg.sync_parameter_to_atc("OnSub", "YesNo", "Yes", "Bật", "Bật")
    pkg.sync_parameter_to_atc("Flag", "YesNo", '[new EnumType(11, "No", "Yes\\No")]', "F", "F")
    p = _params(pkg)

    assert p["Side"].get("DataType") == "long" and (p["Side"].text or "").strip() == "0"
    assert [(e.tag, e.text) for e in p["Side"].find("Enum")] == [("Left", "1"), ("Right", "0")]
    assert len(p["Side"].findall("Enum")) == 1

    assert (p["OnSub"].text or "").strip() == "10"
    assert [(e.tag, e.text) for e in p["OnSub"].find("Enum")] == [("Yes", "10"), ("No", "11")]
    assert (p["Flag"].text or "").strip() == "11"


def test_side_none_is_not_written(tmp_path: Path) -> None:
    """99.pkt dùng Side = EnumType(-1, "None"): SAC không ghi Side vào .atc."""
    pkg = _new_pkg(tmp_path)
    assert "Side" in _params(pkg)  # template có sẵn Side
    pkg.sync_parameter_to_atc("Side", "Side", '[new EnumType(-1, "None", "Side")]', "Side", "Side")
    assert "Side" not in _params(pkg)


def test_superelevation_written_like_sac(tmp_path: Path) -> None:
    pkg = _new_pkg(tmp_path)
    pkg.sync_parameter_to_atc("UseSE", "Superelevation", "RightOutsideLane", "Superelevation", "SE")
    el = _params(pkg)["UseSE"]
    assert (el.get("DataType"), (el.text or "").strip()) == ("long", "26")
    choices = [(e.tag, e.get("DisplayName"), e.text) for e in el.find("Enum")]
    assert choices[0] == ("LeftInsideLane", "Left Inside Lane Slope", "20")
    assert choices[-1] == ("None", "None", "-1") and len(choices) == 9


@pytest.mark.parametrize(
    "data_type, value, expected",
    [
        ("Side", "Right", '[new EnumType(0, "Right", "Side")]'),
        ("Side", "Left", '[new EnumType(1, "Left", "Side")]'),
        # File thật (99.pkt, HEM_KCAD) dùng Side = None (-1)
        ("Side", '[new EnumType(-1, "None", "Side")]', '[new EnumType(-1, "None", "Side")]'),
        ("Side", "None", '[new EnumType(-1, "None", "Side")]'),
        ("YesNo", "No", '[new EnumType(11, "No", "Yes\\No")]'),
        ("YesNo", "True", '[new EnumType(10, "Yes", "Yes\\No")]'),
        ("Superelevation", "", '[new EnumType(-1, "None", "Superelevation")]'),
        ("Superelevation", "RightOutsideLane", '[new EnumType(26, "RightOutsideLane", "Superelevation")]'),
    ],
)
def test_enum_xaml_defaults_match_sac(data_type: str, value: str, expected: str) -> None:
    assert enum_xaml_default(data_type, value) == expected


def test_invalid_enum_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="Left"):
        enum_xaml_default("Side", "Center")


@pytest.mark.skipif(not installed_sac_dirs(), reason="Máy không cài Subassembly Composer")
def test_enum_parameters_pass_native_validation(tmp_path: Path) -> None:
    pkt = tmp_path / "E.pkt"
    create_pkt_from_template(str(pkt), "EnumTest", civil_version="2026")
    for name, dt, val in (("Side", "Side", "Left"), ("OnSub", "YesNo", "No"), ("UseSE", "Superelevation", "RightOutsideLane")):
        res = json.loads(add_parameter(str(pkt), name, data_type=dt, default_value=val))
        assert res["success"] is True, res
    rep = PktValidator.validate_pkt(pkt, document_check=True)
    assert rep.is_valid and rep.tier3_native_ok, [i.message for i in rep.issues]


def test_slope_and_grade_type_info_and_plain_numbers(tmp_path: Path) -> None:
    pkg = _new_pkg(tmp_path)
    pkg.sync_parameter_to_atc("s_Dap", "Slope", "[new Slope(0.666666666666667)]", "Dốc", "Dốc")
    pkg.sync_parameter_to_atc("i_Le", "Grade", "-0.04", "Dốc lề", "Dốc lề")
    pkg.sync_parameter_to_atc("B_Le", "Double", "0.5", "Rộng lề", "Rộng lề")
    p = _params(pkg)
    assert (p["s_Dap"].get("TypeInfo"), p["s_Dap"].text) == ("10", "0.666666666666667")
    assert (p["i_Le"].get("TypeInfo"), p["i_Le"].text) == ("9", "-0.04")
    assert (p["B_Le"].get("TypeInfo"), p["B_Le"].text) == ("16", "0.5")
    assert not pkg.warnings
