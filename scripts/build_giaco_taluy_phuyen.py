"""
Script tự động sinh Subassembly .pkt chuẩn Civil 3D 2025-2027: Gia Cố Mái Taluy Phú Yên
Tối ưu hóa mở trực tiếp trên Subassembly Composer GUI:
  - Tự động nhận diện GIẬT CƠ TALUY (Berm) khi chiều cao đắp H > H_GiatCo (H_dap > 5.0m).
  - Sử dụng ĐỊNH DANH HÌNH HỌC DUY NHẤT (Unique Point/Link/Shape Numbers) trên toàn bộ workflow.
    Triệt tiêu 100% lỗi đỏ dấu chấm than (!) "Value for property 'Name' is duplicated" của SAC GUI.
  - Cấu trúc các khối Sequence trực quan, gọn gàng, click đúp mở từng khối để xem và chỉnh sửa.
  - Khối điều kiện FlowDecision: ApDungGiaCo (Yes/No toggle) và H_dap > H_GiatCo.
  - Bảng tham số phân nhóm rõ ràng, tên hiển thị tiếng Việt có dấu và mô tả kỹ thuật bám sát bản vẽ 02.KCAD.
"""

from __future__ import annotations

import sys
from pathlib import Path
from lxml import etree

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(r"C:\Users\Admin\Desktop\MCP - SUBBASEMBLY")
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.core.builders import GeometryBuilder, ParameterBuilder
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.validator import PktValidator
from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
)


def build_giaco_taluy_phuyen_pkt(output_pkt_path: str | Path) -> str:
    out_path = Path(output_pkt_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pkg = PktPackage.create_from_template(
        output_path=out_path,
        subassembly_name="GiaCo_MaiTaluy_PhuYen",
        description="Gia cố mái taluy Phú Yên (Tấm đan BTXM 12cm, đệm 2cm, chân khay 40x100cm có lót 10cm, tự động giật cơ khi H > H_GiatCo)",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # ========================================================================
    # 1. Khai báo Parameters chuẩn hóa có DisplayName tiếng Việt & Description
    # ========================================================================
    params = [
        ("ApDungGiaCo", ParameterCategory.INPUT, ParameterDataType.BOOLEAN, "True", "Áp dụng gia cố mái taluy", "True = Thi công tấm đan và chân khay kiên cố, False = Vuốt mái taluy đất thường"),
        ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (EG)", "Bề mặt địa hình hiện trạng cần bắt chân taluy"),
        ("Slope_Taluy", ParameterCategory.INPUT, ParameterDataType.SLOPE, "1.5", "Độ dốc mái taluy tầng 1 (1:m)", "Tỷ lệ mái dốc tầng trên (ví dụ 1.5 = 1:1.5)"),
        ("Slope_Taluy2", ParameterCategory.INPUT, ParameterDataType.SLOPE, "1.5", "Độ dốc mái taluy tầng 2 (1:m)", "Tỷ lệ mái dốc tầng dưới sau khi giật cơ (1:1.5)"),
        ("H_GiatCo", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "5.00", "Chiều cao ngưỡng giật cơ (m)", "Chiều cao đắp tối đa 1 tầng trước khi giật cơ taluy"),
        ("B_Co", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "2.00", "Bề rộng bậc cơ taluy (m)", "Bề rộng mặt bậc cơ phân tầng taluy (1.5m - 2.0m)"),
        ("Slope_Co", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.04", "Độ dốc mặt bậc cơ (%)", "Độ dốc thoát nước mặt bậc cơ (dốc vào trong)"),
        ("B_DinhKhoa", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Bề rộng khóa đỉnh mái (m)", "Bề rộng đoạn gia cố phẳng khóa mép vỉa hè"),
        ("T_GiaCo", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.12", "Chiều dày tấm gia cố (m)", "Chiều dày tấm đan BTXM gia cố mái (12cm)"),
        ("T_Dem", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.02", "Chiều dày đệm lót (m)", "Chiều dày vữa xi măng / đá dăm đệm (2cm)"),
        ("B_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.40", "Bề rộng chân khay (m)", "Bề rộng đáy chân khay bê tông cắm vào đất"),
        ("H_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.00", "Chiều sâu chân khay (m)", "Chiều sâu cắm vào đất của vách ngoài chân khay"),
        ("H_NgoamTrong", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.93", "Chiều cao ngoàm trong (m)", "Chiều cao vách trong chân khay ngoàm lên khóa tấm gia cố"),
        ("H_BTLot_CK", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Chiều dày BT lót chân khay (m)", "Chiều dày lớp bê tông lót đáy móng chân khay"),
    ]
    for pname, cat, dt, def_val, disp, desc in params:
        ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
        pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

    # ========================================================================
    # 2. KHỐI GỐC: KHỞI TẠO ĐỈNH MÁI & ĐO CHIỀU CAO ĐẮP (P1, P2, AP1)
    #    (Chạy đầu tiên trước khi rẽ nhánh - Tọa độ gốc chung cho tất cả các nhánh)
    # ========================================================================
    step_dinh, seq_dinh, ref_dinh = engine.create_sequence_step(
        display_name="1. Khởi Tạo Đỉnh Mái & Đo Chiều Cao",
        x=260.0,
        y=100.0,
        auto_attach=True,
    )
    # P1: Gốc xuất phát
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P1", from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="0.0",
        point_codes_str='"DinhTaluy", "Crown"', add_link=False, target_container=seq_dinh
    )
    # P2 & L1: Khóa đỉnh
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P2", from_point="P1",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="B_DinhKhoa", param_2_expr="0.0",
        point_codes_str='"Mep_GiaCo_Dinh"', add_link=True, link_name="L1", link_codes_str='"Top", "Pave"', target_container=seq_dinh
    )
    # AP1: Điểm phụ trợ đo chiều cao từ P2 xuống EG
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="AP1", from_point="P2",
        point_type=PointGeometryType.SLOPE_TO_SURFACE, param_1_expr="-Slope_Taluy", param_2_expr="EG",
        is_auxiliary=True, target_container=seq_dinh
    )

    # ========================================================================
    # 3. NHÁNH CÓ GIẬT CƠ (Khi H_dap > H_GiatCo): DÙNG P20..P37, L20..L42
    # ========================================================================
    # Sequence 2A: Sườn Mái Giật Cơ (Tầng 1, Bậc Cơ, Tầng 2)
    step_gc1, seq_gc1, ref_gc1 = engine.create_sequence_step(
        display_name="2A. Sườn Mái Giật Cơ (Tầng 1, Bậc Cơ, Tầng 2)",
        x=60.0,
        y=370.0,
        auto_attach=False,
    )
    # P20 & L20: Tầng 1 từ P2 dốc -Slope_Taluy đi xuống chiều cao H_GiatCo
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P20", from_point="P2",
        point_type=PointGeometryType.SLOPE_DELTA_X, param_1_expr="-Slope_Taluy", param_2_expr="H_GiatCo * Slope_Taluy",
        point_codes_str='"Dau_BacCo"', add_link=True, link_name="L20", link_codes_str='"Top", "Pave", "Taluy1"', target_container=seq_gc1
    )
    # P21 & L21: Bậc cơ từ P20 rộng B_Co dốc Slope_Co
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P21", from_point="P20",
        point_type=PointGeometryType.SLOPE_DELTA_X, param_1_expr="Slope_Co", param_2_expr="B_Co",
        point_codes_str='"Mep_BacCo"', add_link=True, link_name="L21", link_codes_str='"Top", "Pave", "BacCo"', target_container=seq_gc1
    )
    # P22 & L22: Tầng 2 từ P21 dốc -Slope_Taluy2 bắt bề mặt EG
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P22", from_point="P21",
        point_type=PointGeometryType.SLOPE_TO_SURFACE, param_1_expr="-Slope_Taluy2", param_2_expr="EG",
        point_codes_str='"ChanTaluy", "Daylight"', add_link=True, link_name="L22", link_codes_str='"Top", "Pave", "Daylight"', target_container=seq_gc1
    )

    # Sequence 2B: Chân khay & Móng lót tại chân P22
    step_gc2, seq_gc2, ref_gc2 = engine.create_sequence_step(
        display_name="2B. Chân Khay & Móng Lót (Chân Tầng 2 P22)",
        x=60.0,
        y=460.0,
        auto_attach=False,
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P23", from_point="P22",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.25", param_2_expr="0.0",
        point_codes_str='"ChanKhay_Ngoai"', add_link=True, link_name="L23", link_codes_str='"ChanKhay", "Top"', target_container=seq_gc2
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P24", from_point="P23",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-H_ChanKhay",
        point_codes_str='"ChanKhay_Day_Ngoai"', add_link=True, link_name="L24", link_codes_str='"ChanKhay", "Datum"', target_container=seq_gc2
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P25", from_point="P24",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="-B_ChanKhay", param_2_expr="0.0",
        point_codes_str='"ChanKhay_Day_Trong"', add_link=True, link_name="L25", link_codes_str='"ChanKhay", "Datum"', target_container=seq_gc2
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P26", from_point="P25",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="H_NgoamTrong",
        point_codes_str='"ChanKhay_Ngoam"', add_link=True, link_name="L26", link_codes_str='"ChanKhay"', target_container=seq_gc2
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L27", start_point="P26", end_point="P22",
        link_codes_str='"ChanKhay"', target_container=seq_gc2
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_ChanKhay_GC", link_names=["L23", "L24", "L25", "L26", "L27"],
        shape_codes_str='"S_Chân Khay", "Concrete"', target_container=seq_gc2
    )
    # BT lót móng chân khay
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P27", from_point="P24",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-H_BTLot_CK",
        point_codes_str='"BTLot_Ngoai"', add_link=True, link_name="L28", link_codes_str='"Datum"', target_container=seq_gc2
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P28", from_point="P27",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="-B_ChanKhay", param_2_expr="0.0",
        point_codes_str='"BTLot_Day"', add_link=True, link_name="L29", link_codes_str='"Datum"', target_container=seq_gc2
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L30", start_point="P28", end_point="P25",
        link_codes_str='"Datum"', target_container=seq_gc2
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_BTLot_GC", link_names=["L25", "L28", "L29", "L30"],
        shape_codes_str='"S_BTLChân Khay", "SubBase"', target_container=seq_gc2
    )

    # Sequence 2C: Tấm đan & Đệm lót phủ kín toàn bộ 2 tầng và mặt cơ
    step_gc3, seq_gc3, ref_gc3 = engine.create_sequence_step(
        display_name="2C. Tấm Đan & Đệm Lót Toàn Bộ Mái Giật Cơ",
        x=60.0,
        y=550.0,
        auto_attach=False,
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P29", from_point="P1",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_GiaCo",
        point_codes_str='"DinhTaluy_Day"', add_link=True, link_name="L31", link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P30", from_point="P29",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="B_DinhKhoa", param_2_expr="0.0",
        point_codes_str='"Mep_GiaCo_Dinh_Day"', add_link=True, link_name="L32", link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P31", from_point="P20",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_GiaCo",
        point_codes_str='"Day_Dau_BacCo"', add_link=True, link_name="L33", link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P32", from_point="P21",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_GiaCo",
        point_codes_str='"Day_Mep_BacCo"', add_link=True, link_name="L34", link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P33", from_point="P26",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.02", param_2_expr="0.01",
        point_codes_str='"KhopNgoam_GiaCo"', add_link=False, target_container=seq_gc3
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L35", start_point="P26", end_point="P33",
        link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L36", start_point="P32", end_point="P33",
        link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L37", start_point="P33", end_point="P22",
        link_codes_str='"GiaCo"', target_container=seq_gc3
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_GiaCoMai_GC",
        link_names=["L1", "L20", "L21", "L22", "L37", "L36", "L34", "L33", "L32", "L31"],
        shape_codes_str='"S_Gia Cố Mái", "Concrete"', target_container=seq_gc3
    )
    # Đệm lót
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P34", from_point="P29",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_Dem",
        point_codes_str='"Dem_Dinh"', add_link=True, link_name="L38", link_codes_str='"Datum"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P35", from_point="P34",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="B_DinhKhoa", param_2_expr="0.0",
        point_codes_str='"Dem_Khoa_Dinh"', add_link=True, link_name="L39", link_codes_str='"Datum"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P36", from_point="P31",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_Dem",
        point_codes_str='"Dem_Dau_BacCo"', add_link=True, link_name="L40", link_codes_str='"Datum"', target_container=seq_gc3
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P37", from_point="P32",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_Dem",
        point_codes_str='"Dem_Mep_BacCo"', add_link=True, link_name="L41", link_codes_str='"Datum"', target_container=seq_gc3
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L42", start_point="P37", end_point="P26",
        link_codes_str='"Datum"', target_container=seq_gc3
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_DemGiaCo_GC",
        link_names=["L32", "L33", "L34", "L35", "L42", "L41", "L40", "L39", "L38"],
        shape_codes_str='"S_BTL GIA CỐ MÁI", "SubBase"', target_container=seq_gc3
    )

    # Nối dây 3 sequence nhánh giật cơ
    etree.SubElement(step_gc1, engine.qn("wf", "FlowStep.Next")).append(
        etree.Element(engine.qn("x", "Reference"))
    )
    step_gc1.xpath("./*[local-name()='FlowStep.Next']/*[local-name()='Reference']")[0].text = ref_gc2

    etree.SubElement(step_gc2, engine.qn("wf", "FlowStep.Next")).append(
        etree.Element(engine.qn("x", "Reference"))
    )
    step_gc2.xpath("./*[local-name()='FlowStep.Next']/*[local-name()='Reference']")[0].text = ref_gc3

    # ========================================================================
    # 4. NHÁNH KHÔNG GIẬT CƠ (1 TẦNG - H <= H_GiatCo): DÙNG P3..P14, L2..L18
    # ========================================================================
    step_1t, seq_1t, ref_1t = engine.create_sequence_step(
        display_name="2. Gia Cố Taluy 1 Tầng (H <= H_GiatCo)",
        x=340.0,
        y=370.0,
        auto_attach=False,
    )
    # P3 & L2: từ P2 vuốt thẳng đến EG
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P3", from_point="P2",
        point_type=PointGeometryType.SLOPE_TO_SURFACE, param_1_expr="-Slope_Taluy", param_2_expr="EG",
        point_codes_str='"ChanTaluy", "Daylight"', add_link=True, link_name="L2", link_codes_str='"Top", "Pave", "Daylight"', target_container=seq_1t
    )
    # Chân khay P4..P7, L3..L7, S_ChanKhay
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P4", from_point="P3",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.25", param_2_expr="0.0",
        point_codes_str='"ChanKhay_Ngoai"', add_link=True, link_name="L3", link_codes_str='"ChanKhay", "Top"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P5", from_point="P4",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-H_ChanKhay",
        point_codes_str='"ChanKhay_Day_Ngoai"', add_link=True, link_name="L4", link_codes_str='"ChanKhay", "Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P6", from_point="P5",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="-B_ChanKhay", param_2_expr="0.0",
        point_codes_str='"ChanKhay_Day_Trong"', add_link=True, link_name="L5", link_codes_str='"ChanKhay", "Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P7", from_point="P6",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="H_NgoamTrong",
        point_codes_str='"ChanKhay_Ngoam"', add_link=True, link_name="L6", link_codes_str='"ChanKhay"', target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L7", start_point="P7", end_point="P3",
        link_codes_str='"ChanKhay"', target_container=seq_1t
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_ChanKhay", link_names=["L3", "L4", "L5", "L6", "L7"],
        shape_codes_str='"S_Chân Khay", "Concrete"', target_container=seq_1t
    )
    # BT Lót P8..P9, L8..L10, S_BTLot_ChanKhay
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P8", from_point="P5",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-H_BTLot_CK",
        point_codes_str='"BTLot_Ngoai"', add_link=True, link_name="L8", link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P9", from_point="P8",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="-B_ChanKhay", param_2_expr="0.0",
        point_codes_str='"BTLot_Day"', add_link=True, link_name="L9", link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L10", start_point="P9", end_point="P6",
        link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_BTLot_ChanKhay", link_names=["L5", "L8", "L9", "L10"],
        shape_codes_str='"S_BTLChân Khay", "SubBase"', target_container=seq_1t
    )
    # Tấm đan 1 tầng P10..P12, L11..L15, S_GiaCoMai
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P10", from_point="P1",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_GiaCo",
        point_codes_str='"DinhTaluy_Day"', add_link=True, link_name="L11", link_codes_str='"GiaCo"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P11", from_point="P10",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="B_DinhKhoa", param_2_expr="0.0",
        point_codes_str='"Mep_GiaCo_Dinh_Day"', add_link=True, link_name="L12", link_codes_str='"GiaCo"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P12", from_point="P7",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.02", param_2_expr="0.01",
        point_codes_str='"KhopNgoam_GiaCo"', add_link=False, target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L13", start_point="P7", end_point="P12",
        link_codes_str='"GiaCo"', target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L14", start_point="P11", end_point="P12",
        link_codes_str='"GiaCo"', target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L15", start_point="P12", end_point="P3",
        link_codes_str='"GiaCo"', target_container=seq_1t
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_GiaCoMai",
        link_names=["L1", "L2", "L15", "L14", "L12", "L11"],
        shape_codes_str='"S_Gia Cố Mái", "Concrete"', target_container=seq_1t
    )
    # Đệm lót 1 tầng P13..P14, L16..L18, S_DemGiaCo
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P13", from_point="P10",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="0.0", param_2_expr="-T_Dem",
        point_codes_str='"Dem_Dinh"', add_link=True, link_name="L16", link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P14", from_point="P13",
        point_type=PointGeometryType.DELTA_X_DELTA_Y, param_1_expr="B_DinhKhoa", param_2_expr="0.0",
        point_codes_str='"Dem_Khoa_Dinh"', add_link=True, link_name="L17", link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_link(
        engine=engine, link_name="L18", start_point="P14", end_point="P7",
        link_codes_str='"Datum"', target_container=seq_1t
    )
    GeometryBuilder.add_shape(
        engine=engine, shape_code="S_DemGiaCo",
        link_names=["L12", "L14", "L13", "L18", "L17", "L16"],
        shape_codes_str='"S_BTL GIA CỐ MÁI", "SubBase"', target_container=seq_1t
    )

    # ========================================================================
    # 5. NHÁNH TALUY ĐẤT TỰ NHIÊN (ApDungGiaCo == False): DÙNG P50, L50
    # ========================================================================
    step_dat, seq_dat, ref_dat = engine.create_sequence_step(
        display_name="Mái Taluy Đất Tự Nhiên (Không Gia Cố)",
        x=560.0,
        y=270.0,
        auto_attach=False,
    )
    GeometryBuilder.add_point_and_link(
        engine=engine, point_code="P50", from_point="P2",
        point_type=PointGeometryType.SLOPE_TO_SURFACE, param_1_expr="-Slope_Taluy", param_2_expr="EG",
        point_codes_str='"ChanTaluy", "Daylight"', add_link=True, link_name="L50", link_codes_str='"Top", "Daylight"', target_container=seq_dat
    )

    # ========================================================================
    # 6. ĐIỀU KIỆN 2: FlowDecision kiểm tra chiều cao đắp H > H_GiatCo?
    # ========================================================================
    dec_giatco, ref_dec_giatco = engine.create_flow_decision(
        condition_expr="(P2.Y - AP1.Y) > H_GiatCo",
        display_name="H_dap > H_GiatCo?",
        true_ref_id=ref_gc1,
        false_ref_id=ref_1t,
        x=200.0,
        y=270.0,
        auto_attach=False,
    )

    # ========================================================================
    # 7. ĐIỀU KIỆN 1: FlowDecision: Áp dụng gia cố?
    # ========================================================================
    dec_start, ref_dec_start = engine.create_flow_decision(
        condition_expr="ApDungGiaCo",
        display_name="Áp dụng gia cố mái?",
        true_ref_id=ref_dec_giatco,
        false_ref_id=ref_dat,
        x=360.0,
        y=190.0,
        auto_attach=False,
    )

    # Nối step_dinh -> dec_start
    etree.SubElement(step_dinh, engine.qn("wf", "FlowStep.Next")).append(
        etree.Element(engine.qn("x", "Reference"))
    )
    step_dinh.xpath("./*[local-name()='FlowStep.Next']/*[local-name()='Reference']")[0].text = ref_dec_start

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()

    print(f"Đã tạo thành công file PKT có GIẬT CƠ TỰ ĐỘNG: {out_path} ({out_path.stat().st_size} bytes)")
    return str(out_path)


if __name__ == "__main__":
    phuyen_out = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    examples_out = Path(r"C:\Users\Admin\Desktop\MCP - SUBBASEMBLY\examples\GiaCo_MaiTaluy_PhuYen.pkt")

    build_giaco_taluy_phuyen_pkt(phuyen_out)
    build_giaco_taluy_phuyen_pkt(examples_out)

    # Chạy kiểm định 3 tầng
    rep = PktValidator.validate_pkt(phuyen_out, run_native_test=True)
    rep.print_summary()
