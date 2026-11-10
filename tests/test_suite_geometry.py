"""
Kiểm tra hình học cho 9 cấu kiện NativeSuiteBuilder và 2 recipe:
  - Mỗi Shape: các Link liệt kê (đầu/cuối lấy từ inspect_pkt) phải tạo thành đúng MỘT vòng khép kín.
  - Không có 2 Link khác tên nối cùng một cặp điểm (Link trùng làm Shape suy biến).
  - Kiểm định 3 tầng: is_valid và tier3_native_ok (khi máy có SAC).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from sac_mcp import server
from sac_mcp.core.native_suite_builder import NativeSuiteBuilder
from sac_mcp.core.recipes import create_highway_lane_assembly, create_urban_road_assembly
from sac_mcp.core.validator import PktValidator

BUILDERS = [
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

RECIPES = [
    ("recipe_urban_road", lambda p: create_urban_road_assembly(str(p), civil_version="2026")),
    ("recipe_highway_lane", lambda p: create_highway_lane_assembly(str(p), civil_version="2026")),
]


def shape_closure_errors(pkt_path: Path) -> List[str]:
    """Trả danh sách lỗi khép kín Shape / Link trùng; rỗng nếu hình học hợp lệ."""
    info = json.loads(server.inspect_pkt(pkt_path=str(pkt_path)))
    errors: List[str] = []

    links: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for lk in info["links"]:
        links[lk["link_number"]].append((lk["start_point"], lk["end_point"]))

    # Link khác tên nhưng nối cùng cặp điểm
    pair_names: Dict[frozenset, set] = defaultdict(set)
    for name, ends in links.items():
        for a, b in ends:
            pair_names[frozenset((a, b))].add(name)
    for pair, names in pair_names.items():
        if len(names) > 1:
            errors.append(f"Các Link {sorted(names)} cùng nối {sorted(pair)}")

    for shape in info["shapes"]:
        sname, link_list = shape["shape_number"], shape["link_list"]
        edges = []
        for ln in link_list:
            ends = links.get(ln)
            if not ends:
                errors.append(f"{sname}: Link '{ln}' không tồn tại")
                continue
            if len(set(ends)) > 1:
                errors.append(f"{sname}: Link '{ln}' được định nghĩa nhiều lần với đầu/cuối khác nhau {ends}")
                continue
            edges.append(ends[0])
        if len(edges) != len(link_list):
            continue
        if len(edges) < 3:
            errors.append(f"{sname}: chỉ có {len(edges)} Link, không thể khép kín")
            continue
        degree = Counter()
        adj: Dict[str, set] = defaultdict(set)
        for a, b in edges:
            degree[a] += 1
            degree[b] += 1
            adj[a].add(b)
            adj[b].add(a)
        bad = {p: d for p, d in degree.items() if d != 2}
        if bad:
            errors.append(f"{sname} {link_list}: điểm có bậc khác 2 {bad} (không khép kín)")
            continue
        # Liên thông -> đúng một vòng
        start = next(iter(adj))
        seen, stack = {start}, [start]
        while stack:
            for nb in adj[stack.pop()]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(seen) != len(degree):
            errors.append(f"{sname} {link_list}: tách thành nhiều vòng rời nhau")
    return errors


@pytest.mark.parametrize("name,build_fn", BUILDERS + RECIPES, ids=[n for n, _ in BUILDERS + RECIPES])
def test_shapes_closed_and_valid(tmp_path: Path, name, build_fn):
    pkt = tmp_path / f"{name}.pkt"
    if name.startswith("recipe_"):
        build_fn(pkt)
    else:
        build_fn(pkt, version="2026")

    errs = shape_closure_errors(pkt)
    assert not errs, f"{name}: " + "; ".join(errs)

    rep = PktValidator.validate_pkt(pkt, run_native_test=True)
    problems = [f"[{i.category}] {i.message}" for i in rep.issues if i.severity == "ERROR"]
    problems += [
        f"[{i.category}] {i.message}"
        for i in rep.issues
        if i.category in ("GEOMETRY_REFERENCE", "FLOW_UNREACHABLE")
    ]
    assert rep.is_valid and not problems, f"{name}: {problems}"
    if rep.metadata.get("tier3_skipped") is None:
        assert rep.tier3_native_ok, f"{name}: Tầng 3 thất bại"


def test_closure_checker_detects_open_shape(tmp_path: Path):
    """Bộ kiểm tra phải bắt được Shape hở."""
    pkt = tmp_path / "open.pkt"
    server.create_pkt_from_template(output_path=str(pkt), subassembly_name="OpenShape", civil_version="2026")
    server.add_point_and_link(str(pkt), "P1", add_link=False)
    server.add_point_and_link(str(pkt), "P2", "P1", param_1_expr="1", param_2_expr="0", add_link=True, link_name="L1")
    server.add_point_and_link(str(pkt), "P3", "P2", param_1_expr="0", param_2_expr="-1", add_link=True, link_name="L2")
    server.add_point_and_link(str(pkt), "P4", "P1", param_1_expr="0", param_2_expr="-1", add_link=True, link_name="L3")
    server.add_shape(str(pkt), "S1", ["L1", "L2", "L3"])
    errs = shape_closure_errors(pkt)
    assert errs and "S1" in errs[0]


def test_build_05_both_decisions_have_two_branches(tmp_path: Path):
    pkt = tmp_path / "05.pkt"
    NativeSuiteBuilder.build_05_taluy_dao_dap_day_du(pkt, version="2026")
    info = json.loads(server.inspect_pkt(pkt_path=str(pkt)))
    decisions = [n for n in info["flowchart_nodes"] if n["node_kind"] == "FlowDecision"]
    assert len(decisions) == 2
    for d in decisions:
        assert d["true_reference_id"] and d["false_reference_id"], d
    # Mỗi nhánh kết thúc ở chân taluy chạm EG
    codes = {p["point_number"] for p in info["points"]}
    assert {"P5", "P8"} <= codes
