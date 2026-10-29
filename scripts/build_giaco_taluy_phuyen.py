"""
Script tự động sinh Subassembly .pkt chuẩn Civil 3D 2025-2027: Gia Cố Mái Taluy Phú Yên
Theo đúng hồ sơ thiết kế bản vẽ: 02.KCAD - GIA CO MAI TALUY - CHI TIET BO VIA.dwg
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(r"C:\Users\Admin\Desktop\MCP - SUBBASEMBLY")
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
    ReportMessageType,
)


def build_giaco_taluy_phuyen_pkt(output_pkt_path: str | Path) -> str:
    out_path = Path(output_pkt_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pkg = PktPackage.create_from_template(
        output_path=out_path,
        subassembly_name="GiaCo_MaiTaluy_PhuYen",
        description="Gia cố mái taluy dự án Phú Yên (Tấm đan bê tông 12cm, đệm lót 2cm, chân khay bê tông 40x100cm có bê tông lót móng 10cm)",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # 1. Khai báo Parameters chuẩn Hoa_C3D và bản vẽ thiết kế
    params = [
        ("Slope_Taluy", ParameterCategory.INPUT, ParameterDataType.SLOPE, "1.5", "Độ dốc mái taluy (1:m)", "Tỷ lệ mái dốc ngang/đứng (ví dụ 1.5 = 1:1.5)"),
        ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (EG)", "Bề mặt địa hình hiện trạng cần bắt chân taluy"),
        ("B_DinhKhoa", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Bề rộng khóa đỉnh mái (m)", "Bề rộng đoạn gia cố phẳng khóa mép vỉa hè"),
        ("T_GiaCo", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.12", "Chiều dày tấm gia cố (m)", "Chiều dày tấm đan BTXM gia cố mái (12cm)"),
        ("T_Dem", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.02", "Chiều dày đệm lót (m)", "Chiều dày vữa xi măng / đá dăm đệm (2cm)"),
        ("B_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.40", "Bề rộng chân khay (m)", "Bề rộng đáy chân khay bê tông"),
        ("H_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.00", "Chiều sâu chân khay (m)", "Chiều sâu chân khay cắm vào đất"),
        ("H_BTLot_CK", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Chiều dày BT lót chân khay (m)", "Chiều dày lớp bê tông lót đáy chân khay"),
        ("H_NgoamTrong", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.93", "Chiều cao ngoàm trong (m)", "Chiều cao vách trong chân khay ngoàm lên khóa tấm gia cố"),
    ]
    for pname, cat, dt, def_val, disp, desc in params:
        ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
        pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

    # 2. Điểm xuất phát P1 (Gốc gắn tại mép vỉa hè / mép rãnh)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P1",
        from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="0.0",
        point_codes_str='"DinhTaluy", "Crown"',
        add_link=False,
    )

    # Khóa đỉnh mái taluy P2 (rộng B_DinhKhoa)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P2",
        from_point="P1",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="B_DinhKhoa",
        param_2_expr="0.0",
        point_codes_str='"Mep_GiaCo_Dinh"',
        add_link=True,
        link_name="L1",
        link_codes_str='"Top", "Pave"',
    )

    # Chân mái taluy P3 (Slope to Surface EG)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P3",
        from_point="P2",
        point_type=PointGeometryType.SLOPE_TO_SURFACE,
        param_1_expr="-Slope_Taluy",
        param_2_expr="EG",
        point_codes_str='"ChanTaluy", "Daylight"',
        add_link=True,
        link_name="L2",
        link_codes_str='"Top", "Pave", "Daylight"',
    )

    # 3. Dựng Khối Chân Khay Bê Tông (S_ChanKhay)
    # P4: Gờ ngoài đỉnh chân khay (0.25m)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P4",
        from_point="P3",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.25",
        param_2_expr="0.0",
        point_codes_str='"ChanKhay_Ngoai"',
        add_link=True,
        link_name="L3",
        link_codes_str='"ChanKhay", "Top"',
    )
    # P5: Vách ngoài cắm sâu xuống (-H_ChanKhay = -1.00m)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P5",
        from_point="P4",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="-H_ChanKhay",
        point_codes_str='"ChanKhay_Day_Ngoai"',
        add_link=True,
        link_name="L4",
        link_codes_str='"ChanKhay", "Datum"',
    )
    # P6: Đáy chân khay rộng B_ChanKhay (-0.40m)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P6",
        from_point="P5",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="-B_ChanKhay",
        param_2_expr="0.0",
        point_codes_str='"ChanKhay_Day_Trong"',
        add_link=True,
        link_name="L5",
        link_codes_str='"ChanKhay", "Datum"',
    )
    # P7: Vách trong chân khay ngoàm lên (H_NgoamTrong = 0.93m)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P7",
        from_point="P6",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="H_NgoamTrong",
        point_codes_str='"ChanKhay_Ngoam"',
        add_link=True,
        link_name="L6",
        link_codes_str='"ChanKhay"',
    )
    # Link L7 kết nối P7 -> P3 khép kín khối chân khay
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L7",
        start_point="P7",
        end_point="P3",
        link_codes_str='"ChanKhay"',
    )
    # Shape Chân khay bê tông S_ChanKhay
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_ChanKhay",
        link_names=["L3", "L4", "L5", "L6", "L7"],
        shape_codes_str='"S_Chân Khay", "Concrete"',
    )

    # 4. Lớp Bê Tông Lót Móng Chân Khay (dưới đáy L5):
    # P8: Vách ngoài BT lót (-H_BTLot_CK = -0.10m từ P5)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P8",
        from_point="P5",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="-H_BTLot_CK",
        point_codes_str='"BTLot_Ngoai"',
        add_link=True,
        link_name="L8",
        link_codes_str='"Datum"',
    )
    # P9: Đáy BT lót rộng B_ChanKhay (-0.40m từ P8)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P9",
        from_point="P8",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="-B_ChanKhay",
        param_2_expr="0.0",
        point_codes_str='"BTLot_Day"',
        add_link=True,
        link_name="L9",
        link_codes_str='"Datum"',
    )
    # Link L10 nối P9 -> P6 khép kín khối BT lót móng chân khay
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L10",
        start_point="P9",
        end_point="P6",
        link_codes_str='"Datum"',
    )
    # Shape BT Lót Chân Khay S_BTLot_ChanKhay
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_BTLot_ChanKhay",
        link_names=["L5", "L8", "L9", "L10"],
        shape_codes_str='"S_BTLChân Khay", "SubBase"',
    )

    # 5. Dựng Lớp Tấm Đan Bê Tông Gia Cố Mái (dày T_GiaCo = 12cm)
    # P10: Mép đỉnh đáy tấm đan (-T_GiaCo từ P1)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P10",
        from_point="P1",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="-T_GiaCo",
        point_codes_str='"DinhTaluy_Day"',
        add_link=True,
        link_name="L11",
        link_codes_str='"GiaCo"',
    )
    # P11: Mép khóa đỉnh đáy tấm đan (+B_DinhKhoa từ P10)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P11",
        from_point="P10",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="B_DinhKhoa",
        param_2_expr="0.0",
        point_codes_str='"Mep_GiaCo_Dinh_Day"',
        add_link=True,
        link_name="L12",
        link_codes_str='"GiaCo"',
    )
    # P12: Khớp nối mép dưới tấm đan ngàm vào ngoàm chân khay (+0.02, +0.01 từ P7 theo chuẩn Taluy Phú Yên)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P12",
        from_point="P7",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.02",
        param_2_expr="0.01",
        point_codes_str='"KhopNgoam_GiaCo"',
        add_link=False,
    )
    # Link L13 nối P7 -> P12 (mặt đáy ngoàm đệm)
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L13",
        start_point="P7",
        end_point="P12",
        link_codes_str='"GiaCo"',
    )
    # Link L14 nối P11 -> P12 (mặt dưới tấm đan bê tông theo sườn dốc)
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L14",
        start_point="P11",
        end_point="P12",
        link_codes_str='"GiaCo"',
    )
    # Link L15 nối P12 -> P3 (đầu mũi tấm đan khóa vào chân taluy)
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L15",
        start_point="P12",
        end_point="P3",
        link_codes_str='"GiaCo"',
    )
    # Shape Tấm Đan Bê Tông Gia Cố Mái
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_GiaCoMai",
        link_names=["L1", "L2", "L15", "L14", "L12", "L11"],
        shape_codes_str='"S_Gia Cố Mái", "Concrete"',
    )

    # 6. Dựng Lớp Đệm Lót Vữa / Đá Dăm (dày T_Dem = 2cm dưới đáy L12, L14)
    # P13: Đáy đệm tại mép đỉnh (-T_Dem từ P10)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P13",
        from_point="P10",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="-T_Dem",
        point_codes_str='"Dem_Dinh"',
        add_link=True,
        link_name="L16",
        link_codes_str='"Datum"',
    )
    # P14: Đáy đệm tại khóa đỉnh (+B_DinhKhoa từ P13)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P14",
        from_point="P13",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="B_DinhKhoa",
        param_2_expr="0.0",
        point_codes_str='"Dem_Khoa_Dinh"',
        add_link=True,
        link_name="L17",
        link_codes_str='"Datum"',
    )
    # Link L18 nối P14 -> P7 (mặt dưới đệm lót bắt vào đỉnh ngoàm chân khay)
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L18",
        start_point="P14",
        end_point="P7",
        link_codes_str='"Datum"',
    )
    # Shape Lớp Đệm Lót Gia Cố Mái
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_DemGiaCo",
        link_names=["L12", "L14", "L13", "L18", "L17", "L16"],
        shape_codes_str='"S_BTL GIA CỐ MÁI", "SubBase"',
    )

    pkg.set_xaml_text(engine.to_xaml_string())

    pkg.save()
    print(f"Đã tạo thành công file PKT: {out_path} ({out_path.stat().st_size} bytes)")
    return str(out_path)


if __name__ == "__main__":
    phuyen_out = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    examples_out = Path(r"C:\Users\Admin\Desktop\MCP - SUBBASEMBLY\examples\GiaCo_MaiTaluy_PhuYen.pkt")
    
    build_giaco_taluy_phuyen_pkt(phuyen_out)
    build_giaco_taluy_phuyen_pkt(examples_out)
