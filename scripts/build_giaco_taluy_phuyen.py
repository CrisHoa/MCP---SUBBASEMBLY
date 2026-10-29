"""
Script tự động sinh Subassembly .pkt chuẩn Civil 3D 2025-2027: Gia Cố Mái Taluy Phú Yên
Tối ưu hóa mở trực tiếp trên Subassembly Composer GUI:
  - Cấu trúc 3 khối Sequence trực quan, gọn gàng, click đúp mở từng khối để sửa.
  - Khối điều kiện FlowDecision: ApDungGiaCo (Yes/No toggle) chuyển đổi giữa gia cố kiên cố và taluy đất thường.
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

from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.opc_package import PktPackage
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
        description="Gia cố mái taluy dự án Phú Yên (Tấm đan BTXM 12cm, đệm lót 2cm, chân khay 40x100cm có móng BT lót 10cm)",
        civil_version=CivilVersion.C3D_2026,
    )
    engine = FlowchartEngine(pkg.get_xaml_text())

    # ========================================================================
    # 1. Khai báo Parameters chuẩn hóa có DisplayName tiếng Việt & Description
    # ========================================================================
    params = [
        ("ApDungGiaCo", ParameterCategory.INPUT, ParameterDataType.BOOLEAN, "True", "Áp dụng gia cố mái taluy", "True = Thi công tấm đan và chân khay kiên cố, False = Vuốt mái taluy đất thường"),
        ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (EG)", "Bề mặt địa hình hiện trạng cần bắt chân taluy"),
        ("Slope_Taluy", ParameterCategory.INPUT, ParameterDataType.SLOPE, "1.5", "Độ dốc mái taluy (1:m)", "Tỷ lệ mái dốc ngang/đứng (ví dụ 1.5 = 1:1.5)"),
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
    # 2. Tạo 3 Khối Sequence cho Nhánh True (Áp dụng Gia Cố)
    # ========================================================================
    # Sequence 1: Khóa đỉnh & Mái taluy
    step1, seq1, ref1 = engine.create_sequence_step(
        display_name="1. Khóa Đỉnh Mái & Mái Taluy Đắp",
        x=120.0,
        y=230.0,
        auto_attach=False,
    )
    # P1: Gốc xuất phát
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P1",
        from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="0.0",
        point_codes_str='"DinhTaluy", "Crown"',
        add_link=False,
        target_container=seq1,
    )
    # P2 & L1: Khóa đỉnh
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
        target_container=seq1,
    )
    # P3 & L2: Mái dốc bắt bề mặt EG
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
        target_container=seq1,
    )

    # Sequence 2: Chân khay bê tông & Móng BT lót
    step2, seq2, ref2 = engine.create_sequence_step(
        display_name="2. Chân Khay Bê Tông & Móng Lót",
        x=120.0,
        y=330.0,
        auto_attach=False,
    )
    # P4: Gờ ngoài đỉnh chân khay
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
        target_container=seq2,
    )
    # P5: Vách ngoài cắm sâu xuống (-H_ChanKhay)
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
        target_container=seq2,
    )
    # P6: Đáy chân khay (-B_ChanKhay)
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
        target_container=seq2,
    )
    # P7: Vách trong ngoàm lên (+H_NgoamTrong)
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
        target_container=seq2,
    )
    # Link L7 nối P7 -> P3 khép kín khối chân khay
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L7",
        start_point="P7",
        end_point="P3",
        link_codes_str='"ChanKhay"',
        target_container=seq2,
    )
    # Shape Chân khay bê tông S_ChanKhay
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_ChanKhay",
        link_names=["L3", "L4", "L5", "L6", "L7"],
        shape_codes_str='"S_Chân Khay", "Concrete"',
        target_container=seq2,
    )
    # P8: Vách ngoài BT lót (-H_BTLot_CK từ P5)
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
        target_container=seq2,
    )
    # P9: Đáy BT lót (-B_ChanKhay từ P8)
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
        target_container=seq2,
    )
    # Link L10 nối P9 -> P6 khép kín móng lót
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L10",
        start_point="P9",
        end_point="P6",
        link_codes_str='"Datum"',
        target_container=seq2,
    )
    # Shape BT Lót Chân Khay S_BTLot_ChanKhay
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_BTLot_ChanKhay",
        link_names=["L5", "L8", "L9", "L10"],
        shape_codes_str='"S_BTLChân Khay", "SubBase"',
        target_container=seq2,
    )

    # Sequence 3: Tấm đan & Đệm lót gia cố mái
    step3, seq3, ref3 = engine.create_sequence_step(
        display_name="3. Tấm Đan & Đệm Lót Gia Cố Mái",
        x=120.0,
        y=430.0,
        auto_attach=False,
    )
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
        target_container=seq3,
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
        target_container=seq3,
    )
    # P12: Khớp nối mép dưới tấm đan ngàm vào chân khay (+0.02, +0.01 từ P7)
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P12",
        from_point="P7",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.02",
        param_2_expr="0.01",
        point_codes_str='"KhopNgoam_GiaCo"',
        add_link=False,
        target_container=seq3,
    )
    # Link L13 nối P7 -> P12
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L13",
        start_point="P7",
        end_point="P12",
        link_codes_str='"GiaCo"',
        target_container=seq3,
    )
    # Link L14 nối P11 -> P12
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L14",
        start_point="P11",
        end_point="P12",
        link_codes_str='"GiaCo"',
        target_container=seq3,
    )
    # Link L15 nối P12 -> P3
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L15",
        start_point="P12",
        end_point="P3",
        link_codes_str='"GiaCo"',
        target_container=seq3,
    )
    # Shape Tấm Đan Bê Tông Gia Cố Mái
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_GiaCoMai",
        link_names=["L1", "L2", "L15", "L14", "L12", "L11"],
        shape_codes_str='"S_Gia Cố Mái", "Concrete"',
        target_container=seq3,
    )
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
        target_container=seq3,
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
        target_container=seq3,
    )
    # Link L18 nối P14 -> P7
    GeometryBuilder.add_link(
        engine=engine,
        link_name="L18",
        start_point="P14",
        end_point="P7",
        link_codes_str='"Datum"',
        target_container=seq3,
    )
    # Shape Lớp Đệm Lót Gia Cố Mái
    GeometryBuilder.add_shape(
        engine=engine,
        shape_code="S_DemGiaCo",
        link_names=["L12", "L14", "L13", "L18", "L17", "L16"],
        shape_codes_str='"S_BTL GIA CỐ MÁI", "SubBase"',
        target_container=seq3,
    )

    # Nối dây tuần tự 3 Sequence của nhánh True: step1 -> step2 -> step3
    next1 = etree.SubElement(step1, engine.qn("wf", "FlowStep.Next"))
    etree.SubElement(next1, engine.qn("x", "Reference")).text = ref2

    next2 = etree.SubElement(step2, engine.qn("wf", "FlowStep.Next"))
    etree.SubElement(next2, engine.qn("x", "Reference")).text = ref3

    # ========================================================================
    # 3. Tạo Sequence cho Nhánh False (Taluy Đất Thường - Không Gia Cố)
    # ========================================================================
    step_false, seq_false, ref_false = engine.create_sequence_step(
        display_name="Mái Taluy Đất Tự Nhiên (Không Gia Cố)",
        x=420.0,
        y=230.0,
        auto_attach=False,
    )
    # P1 đất
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P1",
        from_point="Origin",
        point_type=PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr="0.0",
        param_2_expr="0.0",
        point_codes_str='"DinhTaluy", "Crown"',
        add_link=False,
        target_container=seq_false,
    )
    # P2 đất vuốt thẳng ra mặt đất tự nhiên EG
    GeometryBuilder.add_point_and_link(
        engine=engine,
        point_code="P2",
        from_point="P1",
        point_type=PointGeometryType.SLOPE_TO_SURFACE,
        param_1_expr="-Slope_Taluy",
        param_2_expr="EG",
        point_codes_str='"ChanTaluy", "Daylight"',
        add_link=True,
        link_name="L1",
        link_codes_str='"Top", "Daylight"',
        target_container=seq_false,
    )

    # ========================================================================
    # 4. Gắn FlowDecision làm StartNode của Flowchart
    # ========================================================================
    dec_el, dec_ref = engine.create_flow_decision(
        condition_expr="ApDungGiaCo",
        display_name="Áp dụng gia cố mái?",
        true_ref_id=ref1,
        false_ref_id=ref_false,
        x=260.0,
        y=100.0,
        auto_attach=True,
    )

    pkg.set_xaml_text(engine.to_xaml_string())
    pkg.save()
    print(f"Đã tạo thành công file PKT tối ưu SAC GUI: {out_path} ({out_path.stat().st_size} bytes)")
    return str(out_path)


if __name__ == "__main__":
    phuyen_out = Path(r"C:\Users\Admin\Desktop\SUB PHU YEN\GiaCo_MaiTaluy_PhuYen.pkt")
    examples_out = Path(r"C:\Users\Admin\Desktop\MCP - SUBBASEMBLY\examples\GiaCo_MaiTaluy_PhuYen.pkt")
    
    build_giaco_taluy_phuyen_pkt(phuyen_out)
    build_giaco_taluy_phuyen_pkt(examples_out)
