"""
Unit test kiểm thử toàn diện 100% bộ 8 Cấu kiện Native XAML thay thế Visual Infra.
Kiểm định tự động qua 3 Tầng:
  - Tầng 1: Chuẩn gói OPC Package (Content_Types, ATC, CFG, PVD, EMD, CDMD, UTF-8 BOM).
  - Tầng 2: Cú pháp WF4 / XAML Semantic.
  - Tầng 3: Native Autodesk Subassembly Composer Runtime reflection hook trực tiếp.
"""

from pathlib import Path
import pytest
from sac_mcp.core.native_suite_builder import NativeSuiteBuilder
from sac_mcp.core.validator import PktValidator


@pytest.fixture(scope="module")
def suite_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("native_suite")
    return d


def test_build_and_validate_all_8_subassemblies(suite_dir: Path):
    builders = [
        ("01_PhuiDaoCong", NativeSuiteBuilder.build_01_phui_dao_cong),
        ("02_VetHuuCo_DanhCap", NativeSuiteBuilder.build_02_vet_huu_co_danh_cap),
        ("03_SoSanhBeMat", NativeSuiteBuilder.build_03_so_sanh_be_mat),
        ("04_KetCauDuongCu", NativeSuiteBuilder.build_04_ket_cau_duong_cu),
        ("05_TaluyDaoDapDayDu", NativeSuiteBuilder.build_05_taluy_dao_dap_day_du),
        ("06_DuongNangCapCaiTao", NativeSuiteBuilder.build_06_duong_nang_cap_cai_tao),
        ("07_KetCauMatDuongMoi", NativeSuiteBuilder.build_07_ket_cau_mat_duong_moi),
        ("08_GiaCoMaiTaluy_GiatCo", NativeSuiteBuilder.build_08_giaco_maitaluy_giatco),
    ]

    for name, build_fn in builders:
        pkt_path = suite_dir / f"{name}.pkt"
        build_fn(pkt_path, version="2026")

        # Kiểm định 3 tầng
        rep = PktValidator.validate_pkt(pkt_path, run_native_test=True)
        errors = [f"[{i.category}] {i.message}" for i in rep.issues if i.severity == "ERROR"]
        assert rep.is_valid, f"Cấu kiện '{name}' kiểm định thất bại: {errors}"
        assert rep.tier1_opc_ok, f"Cấu kiện '{name}' lỗi Tầng 1 (OPC Package)"
        assert rep.tier2_xaml_ok, f"Cấu kiện '{name}' lỗi Tầng 2 (WF4 Semantics)"
        assert rep.tier3_native_ok, f"Cấu kiện '{name}' lỗi Tầng 3 (Autodesk Runtime Hook)"
