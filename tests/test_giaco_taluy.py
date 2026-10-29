import json
import pytest
from pathlib import Path
from sac_mcp.server import inspect_pkt, validate_pkt_native
from sac_mcp.core.validator import PktValidator


def test_giaco_taluy_phuyen_structure():
    pkt_path = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    assert pkt_path.exists(), f"File not found: {pkt_path}"

    # Kiểm tra qua công cụ inspect_pkt của MCP Server
    res = json.loads(inspect_pkt(str(pkt_path)))
    assert res["subassembly_name"] == "GiaCo_MaiTaluy_PhuYen"
    assert len(res["parameters"]) >= 10
    assert len(res["points"]) >= 14
    assert len(res["shapes"]) == 4

    shape_names = [sh["shape_number"] for sh in res["shapes"]]
    for es in ["S_ChanKhay", "S_BTLot_ChanKhay", "S_GiaCoMai", "S_DemGiaCo"]:
        assert es in shape_names, f"Missing shape {es}"


def test_pkt_validator_3_tiers():
    pkt_path = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    rep = PktValidator.validate_pkt(pkt_path, run_native_test=True)
    assert rep.is_valid, f"Validation failed: {[i.message for i in rep.issues]}"
    assert rep.tier1_opc_ok
    assert rep.tier2_xaml_ok
    assert rep.tier3_native_ok

    # Kiểm tra qua tool validate_pkt_native của MCP Server
    mcp_res = json.loads(validate_pkt_native(str(pkt_path)))
    assert mcp_res["is_valid"] is True
    assert mcp_res["tier3_native_ok"] is True


def test_giaco_taluy_flowchart_sequences_and_decisions():
    """Kiểm tra file PKT mới có đủ FlowDecision và Sequence gom nhóm trực quan."""
    from sac_mcp.core.opc_package import PktPackage
    from sac_mcp.core.xaml_engine import FlowchartEngine

    pkt_path = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    pkg = PktPackage.open(pkt_path)
    engine = FlowchartEngine(pkg.get_xaml_text())

    # Kiểm tra FlowDecision
    decisions = engine.root.xpath("//*[local-name()='FlowDecision']")
    assert len(decisions) >= 1, "Phải có ít nhất 1 khối FlowDecision"
    assert "ApDungGiaCo" in decisions[0].get("Condition", "")

    # Kiểm tra Sequence containers
    sequences = engine.root.xpath("//*[local-name()='Sequence']")
    assert len(sequences) >= 4, "Phải có đủ 4 khối Sequence (3 khối gia cố + 1 khối taluy đất)"

    seq_names = [s.get("DisplayName", "") for s in sequences]
    assert any("Khóa Đỉnh" in name for name in seq_names)
    assert any("Chân Khay" in name for name in seq_names)
    assert any("Tấm Đan" in name for name in seq_names)
    assert any("Đất Tự Nhiên" in name for name in seq_names)

