"""
Script khởi tạo sẵn 3 file Base Template (.pkt) cho Civil 3D 2025, 2026, 2027
và tạo 1 file Subassembly mẫu hoàn chỉnh (SimpleLane_2026.pkt) bằng chính 5 MCP Tools.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.server import (
    ensure_default_templates_exist,
    create_pkt_from_template,
    add_parameter,
    add_point_and_link,
    add_report_message,
    inspect_pkt,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("1. Đang khởi tạo Base Templates (base_2025.pkt, base_2026.pkt, base_2027.pkt)...")
    ensure_default_templates_exist()

    examples_dir = ROOT_DIR / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    sample_pkt = str(examples_dir / "SimpleLane_2026.pkt")

    print(f"2. Đang tạo file mẫu '{sample_pkt}' cho Civil 3D 2026...")
    create_pkt_from_template(
        output_path=sample_pkt,
        subassembly_name="SimpleLane_C3D2026",
        description="Subassembly mặt đường 1 lớp tự động tạo bởi sac-mcp-server",
        civil_version="2026",
    )

    print("3. Đang thêm Parameters (LaneWidth, LaneSlope, Thickness, TargetSurface)...")
    add_parameter(
        pkt_path=sample_pkt,
        name="LaneWidth",
        param_category="Input",
        data_type="Double",
        default_value="3.5",
        display_name="Chiều rộng làn xe (m)",
    )
    add_parameter(
        pkt_path=sample_pkt,
        name="LaneSlope",
        param_category="Input",
        data_type="Slope",
        default_value="-0.02",
        display_name="Độ dốc ngang làn xe (%)",
    )
    add_parameter(
        pkt_path=sample_pkt,
        name="EG_Surface",
        param_category="Target",
        data_type="SurfaceTarget",
        default_value="-9999",
        display_name="Bề mặt tự nhiên (EG)",
    )

    print("4. Đang thêm Points (P1, P2, P3) và nối Links (L1, L2)...")
    add_point_and_link(
        pkt_path=sample_pkt,
        point_code="P1",
        from_point="Origin",
        point_type="DeltaX_DeltaY",
        param_1_expr="0.0",
        param_2_expr="0.0",
        point_codes_str='"Crown"',
        add_link=False,
    )
    add_point_and_link(
        pkt_path=sample_pkt,
        point_code="P2",
        from_point="P1",
        point_type="Slope_DeltaX",
        param_1_expr="LaneSlope",
        param_2_expr="LaneWidth",
        point_codes_str='"ETW"',
        add_link=True,
        link_name="L1",
        link_codes_str='"Top", "Pave"',
    )
    add_point_and_link(
        pkt_path=sample_pkt,
        point_code="P3",
        from_point="P2",
        point_type="Slope_To_Surface",
        param_1_expr="-0.67",
        param_2_expr="EG_Surface",
        point_codes_str='"Daylight"',
        add_link=True,
        link_name="L2",
        link_codes_str='"Top", "Daylight"',
    )

    print("5. Đang thêm khối kiểm tra điều kiện Decision + Report Message...")
    add_report_message(
        pkt_path=sample_pkt,
        message_expr='"Chiều rộng làn xe (LaneWidth) phải lớn hơn 0!"',
        message_type="Error",
        condition_expr="LaneWidth <= 0",
    )

    print("\n6. Kết quả inspect_pkt trên file vừa tạo:")
    print(inspect_pkt(sample_pkt, include_raw_xaml=False))


if __name__ == "__main__":
    main()
