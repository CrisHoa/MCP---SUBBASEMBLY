"""
Engine xây dựng trọn bộ 8 Cấu kiện Subassembly Native XAML 100% của mình.
Giải phẫu từ Visual Infra và bộ PKT thực tế, loại bỏ hoàn toàn DLL/License lock,
đảm bảo 100% mở và chỉnh sửa trực tiếp được trong Autodesk Subassembly Composer GUI.

Danh mục 8 cấu kiện:
  1. 01_PhuiDaoCong (Phui đào cống / Hào kỹ thuật)
  2. 02_VetHuuCo_DanhCap (Vét hữu cơ song song + Đánh cấp sườn dốc)
  3. 03_SoSanhBeMat (So sánh cao độ bề mặt tính đào đắp)
  4. 04_KetCauDuongCu (Mô hình hóa móng mặt đường hiện trạng)
  5. 05_TaluyDaoDapDayDu (Taluy đào đắp đa tầng giật cơ + rãnh biên)
  6. 06_DuongNangCapCaiTao (Bù vênh + Cạp mở rộng giật cấp móng mặt)
  7. 07_KetCauMatDuongMoi (5 lớp kết cấu tiêu chuẩn + mở rộng so le + siêu cao)
  8. 08_GiaCoMaiTaluy_GiatCo (Gia cố đỉnh, mái taluy giật cơ giữ nguyên H lớp lót + Chân khay)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

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


class NativeSuiteBuilder:
    """Builder tái thiết lập toàn bộ 8 PKT Native chuẩn XAML của riêng mình."""

    @classmethod
    def build_01_phui_dao_cong(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 1: Phui đào cống & Hào kỹ thuật."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="PhuiDaoCong",
            description="Phui đào cống và hào kỹ thuật có bê tông lót đáy gối cống",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        # Parameters
        params = [
            ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (EG)", "Mặt đất tự nhiên để đào phui"),
            ("Side", ParameterCategory.INPUT, ParameterDataType.SIDE, "Right", "Phía", "Phía đặt cống"),
            ("B_day", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.60", "Bề rộng đáy phui (m)", "Bề rộng đáy đào phui cống"),
            ("H_dao", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "2.20", "Chiều sâu đáy phui (m)", "Độ sâu từ tim đường xuống đáy phui"),
            ("SideSlope", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Mái dốc phui đào (H:V)", "Mái dốc vách đất đào 1:0.5"),
            ("BTLotThick", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Dày BT lót (m)", "Chiều dày lớp bê tông lót đáy gối"),
            ("BTLotExt", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Mở rộng BT lót (m)", "Mở rộng bê tông lót mỗi bên"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Biến: Khởi tạo literal 0.0 và gán biểu thức bằng SetVariableValue
        LogicBuilder.add_define_variable(engine, "Half_B", "Double", "0.0")
        LogicBuilder.add_set_variable_value(engine, "Half_B", "B_day / 2.0", "Double")

        # Hình học:
        # P1: Đáy tim phui
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_dao", point_codes_str='"Day_Cong"')
        # P2, P3: Đáy phui đào trái & phải
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.DELTA_X_DELTA_Y, "-Half_B", "0.0", point_codes_str='"Day_Phui_L"')
        GeometryBuilder.add_point_and_link(engine, "P3", "P1", PointGeometryType.DELTA_X_DELTA_Y, "Half_B", "0.0", point_codes_str='"Day_Phui_R"', add_link=True, link_name="L1", link_codes_str='"DayPhui"')

        # P4, P5: Đáy bê tông lót
        GeometryBuilder.add_point_and_link(engine, "P4", "P2", PointGeometryType.DELTA_X_DELTA_Y, "BTLotExt", "0.0", point_codes_str='"BTLot_L"')
        GeometryBuilder.add_point_and_link(engine, "P5", "P4", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "BTLotThick", point_codes_str='"BTLot_TopL"', add_link=True, link_name="L2", link_codes_str='"BTLot"')
        GeometryBuilder.add_point_and_link(engine, "P6", "P3", PointGeometryType.DELTA_X_DELTA_Y, "-BTLotExt", "0.0", point_codes_str='"BTLot_R"')
        GeometryBuilder.add_point_and_link(engine, "P7", "P6", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "BTLotThick", point_codes_str='"BTLot_TopR"', add_link=True, link_name="L3", link_codes_str='"BTLot"')
        # Link đỉnh BT lót
        GeometryBuilder.add_link(engine, "L4", "P5", "P7", link_codes_str='"BTLot", "Top"')
        # Shape BT lót
        GeometryBuilder.add_shape(engine, "S1", ["L2", "L4", "L3"], shape_codes_str='"BTLot"')

        # Vách đào phui dốc lên mặt đất EG: P8 từ P2 lên EG, P9 từ P3 lên EG
        GeometryBuilder.add_point_and_link(engine, "P8", "P2", PointGeometryType.SLOPE_TO_SURFACE, "-SideSlope", "EG", point_codes_str='"Top_Phui_L"', add_link=True, link_name="L5", link_codes_str='"VachPhui"')
        GeometryBuilder.add_point_and_link(engine, "P9", "P3", PointGeometryType.SLOPE_TO_SURFACE, "SideSlope", "EG", point_codes_str='"Top_Phui_R"', add_link=True, link_name="L6", link_codes_str='"VachPhui"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_02_vet_huu_co_danh_cap(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 2: Vét hữu cơ & Đánh cấp sườn dốc."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="VetHuuCo_DanhCap",
            description="Vét hữu cơ song song mặt đất tự nhiên và tự động đánh cấp sườn dốc",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên (EG)", "Bề mặt địa hình"),
            ("StrippingDepth", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.30", "Chiều sâu vét hữu cơ (m)", "Chiều sâu bóc lớp đất hữu cơ"),
            ("BenchWidth", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.00", "Bề rộng bậc cấp (m)", "Bề rộng mặt bậc đánh cấp"),
            ("BenchSlope", ParameterCategory.INPUT, ParameterDataType.GRADE, "0.02", "Độ dốc bậc cấp (%)", "Độ dốc thoát nước ngược vào sườn đồi"),
            ("SlopeThreshold", ParameterCategory.INPUT, ParameterDataType.SLOPE, "0.20", "Ngưỡng độ dốc đánh cấp", "Độ dốc sườn đồi > 20% thì đánh cấp"),
            ("B_vet", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "3.00", "Bề rộng dải vét (m)", "Phạm vi bề rộng vét hữu cơ"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Dựng điểm chuẩn trên mặt đất EG
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_ON_SURFACE, "0.0", "EG", point_codes_str='"EG_Start"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.DELTA_X_ON_SURFACE, "B_vet", "EG", point_codes_str='"EG_End"', add_link=True, link_name="L1", link_codes_str='"Top", "EG"')

        # Đáy lớp vét hữu cơ song song hạ StrippingDepth
        GeometryBuilder.add_point_and_link(engine, "P3", "P1", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-StrippingDepth", point_codes_str='"VHC_Start"')
        GeometryBuilder.add_point_and_link(engine, "P4", "P2", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-StrippingDepth", point_codes_str='"VHC_End"', add_link=True, link_name="L2", link_codes_str='"Datum", "VHC"')

        # Khép link vách 2 bên
        GeometryBuilder.add_link(engine, "L3", "P1", "P3", link_codes_str='"VHC"')
        GeometryBuilder.add_link(engine, "L4", "P2", "P4", link_codes_str='"VHC"')

        # Shape Vét hữu cơ
        GeometryBuilder.add_shape(engine, "S1", ["L1", "L4", "L2", "L3"], shape_codes_str='"VHC", "VetHuuCo"')

        # Bậc đánh cấp: P4 -> P5 (bậc ngang rộng BenchWidth, dốc BenchSlope)
        GeometryBuilder.add_point_and_link(engine, "P5", "P4", PointGeometryType.SLOPE_DELTA_X, "BenchSlope", "BenchWidth", point_codes_str='"DC_MatBac"', add_link=True, link_name="L5", link_codes_str='"DanhCap"')
        GeometryBuilder.add_point_and_link(engine, "P6", "P5", PointGeometryType.DELTA_X_ON_SURFACE, "0.0", "EG", point_codes_str='"DC_VachBac"', add_link=True, link_name="L6", link_codes_str='"DanhCap"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_03_so_sanh_be_mat(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 3: So sánh cao độ bề mặt tính khối lượng đào đắp."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="SoSanhBeMat",
            description="So sánh cao độ giữa 2 bề mặt tự nhiên và thiết kế",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("Surface_TN", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt tự nhiên (TN)", "Mặt đất hiện trạng"),
            ("Surface_TK", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Bề mặt thiết kế (TK)", "Mặt hoàn thiện"),
            ("B_quet", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "10.0", "Bề rộng quét (m)", "Phạm vi quét so sánh"),
            ("Out_ChenhCao", ParameterCategory.OUTPUT, ParameterDataType.DOUBLE, "0.0", "Chênh cao tại tim (m)", "Chênh lệch cao độ thiết kế - tự nhiên"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Lấy điểm tim trên 2 bề mặt
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_ON_SURFACE, "0.0", "Surface_TN", point_codes_str='"TN_Tim"')
        GeometryBuilder.add_point_and_link(engine, "P2", "Origin", PointGeometryType.DELTA_X_ON_SURFACE, "0.0", "Surface_TK", point_codes_str='"TK_Tim"')

        # Điểm biên phải
        GeometryBuilder.add_point_and_link(engine, "P3", "Origin", PointGeometryType.DELTA_X_ON_SURFACE, "B_quet", "Surface_TN", point_codes_str='"TN_Bien"', add_link=True, link_name="L1", link_codes_str='"TN"')
        GeometryBuilder.add_point_and_link(engine, "P4", "Origin", PointGeometryType.DELTA_X_ON_SURFACE, "B_quet", "Surface_TK", point_codes_str='"TK_Bien"', add_link=True, link_name="L2", link_codes_str='"TK"')

        # Khép link 2 đầu
        GeometryBuilder.add_link(engine, "L3", "P1", "P2", link_codes_str='"ChenhCao"')
        GeometryBuilder.add_link(engine, "L4", "P3", "P4", link_codes_str='"ChenhCao"')

        # Shape so sánh
        GeometryBuilder.add_shape(engine, "S1", ["L2", "L4", "L1", "L3"], shape_codes_str='"SoSanhBeMat"')

        # Set Output Parameter
        LogicBuilder.add_set_output_parameter(engine, "Out_ChenhCao", "P2.Y - P1.Y", "Double")

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_04_ket_cau_duong_cu(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 4: Mô hình hóa kết cấu mặt đường cũ."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="KetCauDuongCu",
            description="Mô phỏng lớp móng mặt kết cấu đường cũ hiện trạng",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("WL", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "3.00", "Bề rộng trái (m)", "Mép đường cũ bên trái"),
            ("WR", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "3.00", "Bề rộng phải (m)", "Mép đường cũ bên phải"),
            ("H", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.30", "Chiều dày kết cấu (m)", "Độ dày móng mặt đường cũ"),
            ("i_L", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.02", "Độ dốc trái (%)", "Độ dốc ngang mặt cũ trái"),
            ("i_R", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.02", "Độ dốc phải (%)", "Độ dốc ngang mặt cũ phải"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Mặt trên đường cũ: P1 (Tim), P2 (Mép trái), P3 (Mép phải)
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0", point_codes_str='"Crown_Cu"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "-i_L", "-WL", point_codes_str='"Mep_Cu_L"', add_link=True, link_name="L1", link_codes_str='"MDC", "Top"')
        GeometryBuilder.add_point_and_link(engine, "P3", "P1", PointGeometryType.SLOPE_DELTA_X, "i_R", "WR", point_codes_str='"Mep_Cu_R"', add_link=True, link_name="L2", link_codes_str='"MDC", "Top"')

        # Đáy kết cấu đường cũ: P4 (Đáy tim), P5 (Đáy trái), P6 (Đáy phải)
        GeometryBuilder.add_point_and_link(engine, "P4", "P1", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H", point_codes_str='"Day_Cu_Tim"')
        GeometryBuilder.add_point_and_link(engine, "P5", "P4", PointGeometryType.SLOPE_DELTA_X, "-i_L", "-WL", point_codes_str='"Day_Cu_L"', add_link=True, link_name="L3", link_codes_str='"Datum"')
        GeometryBuilder.add_point_and_link(engine, "P6", "P4", PointGeometryType.SLOPE_DELTA_X, "i_R", "WR", point_codes_str='"Day_Cu_R"', add_link=True, link_name="L4", link_codes_str='"Datum"')

        # Khép cạnh bên & tim
        GeometryBuilder.add_link(engine, "L5", "P2", "P5", link_codes_str='"KCDC"')
        GeometryBuilder.add_link(engine, "L6", "P3", "P6", link_codes_str='"KCDC"')
        GeometryBuilder.add_link(engine, "L7", "P1", "P4", link_codes_str='"KCDC"')

        # 2 Shape nửa trái & phải
        GeometryBuilder.add_shape(engine, "S1", ["L1", "L5", "L3", "L7"], shape_codes_str='"KCDC"')
        GeometryBuilder.add_shape(engine, "S2", ["L2", "L6", "L4", "L7"], shape_codes_str='"KCDC"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_05_taluy_dao_dap_day_du(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 5: Taluy đào đắp đa tầng giật cơ & rãnh biên toàn năng."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="TaluyDaoDapDayDu",
            description="Mái taluy đào đắp đa tầng giật cơ tự động kết hợp rãnh biên và lớp gia cố",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên (EG)", "Bề mặt địa hình"),
            ("Side", ParameterCategory.INPUT, ParameterDataType.SIDE, "Right", "Phía", "Lề trái hoặc phải"),
            ("Ble", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Rộng lề đất (m)", "Bề rộng lề vuốt đỉnh taluy"),
            ("i_le", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.04", "Dốc lề đất (%)", "Độ dốc thoát nước lề"),
            ("H_GiatCo_Dap", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "6.00", "Ngưỡng giật cơ đắp (m)", "Chiều cao đắp vượt ngưỡng thì giật cơ"),
            ("s_Dap", ParameterCategory.INPUT, ParameterDataType.SLOPE, "-0.6667", "Dốc mái đắp (1:1.5)", "Mái dốc đắp đất"),
            ("B_Co_Dap", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "2.00", "Rộng cơ đắp (m)", "Bề rộng bậc giật cơ"),
            ("i_Co_Dap", ParameterCategory.INPUT, ParameterDataType.GRADE, "0.08", "Dốc mặt cơ đắp (%)", "Độ dốc thoát nước mặt cơ"),
            ("H_GiatCo_Dao", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "8.00", "Ngưỡng giật cơ đào (m)", "Chiều cao đào vượt ngưỡng thì giật cơ"),
            ("s_Dao", ParameterCategory.INPUT, ParameterDataType.SLOPE, "1.3333", "Dốc mái đào (1:0.75)", "Mái dốc đào đất"),
            ("B_Co_Dao", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "2.00", "Rộng cơ đào (m)", "Bề rộng mặt cơ đào"),
            ("b_ranh", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.40", "Đáy rãnh biên (m)", "Bề rộng đáy rãnh đào"),
            ("h_ranh", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.40", "Sâu rãnh biên (m)", "Chiều sâu rãnh thoát nước biên"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Biến chiều cao taluy
        LogicBuilder.add_define_variable(engine, "Var_H", "Double", "0.0")

        # 1. Điểm đỉnh taluy P1 -> P2 (Lề đất L1)
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0", point_codes_str='"Mep_Le"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "i_le", "Ble", point_codes_str='"Vai_Taluy"', add_link=True, link_name="L1", link_codes_str='"Top", "LeDat"')

        # 2. Điểm phụ AP1 dốc thẳng đứng xuống EG để kiểm tra Cut/Fill
        GeometryBuilder.add_point_and_link(engine, "AP1", "P2", PointGeometryType.SLOPE_TO_SURFACE, "-1.5", "EG", is_auxiliary=True)
        LogicBuilder.add_set_variable_value(engine, "Var_H", "Math.Abs(P2.Y - AP1.Y)", "Double")

        # 3. Decision Đào hay Đắp: AP1.Y < P2.Y -> Đắp (Fill)
        dec_cut_fill = LogicBuilder.add_flow_decision(
            engine,
            condition_expr="AP1.Y < P2.Y",
            display_name="Đắp hay Đào?",
            x=260.0,
            y=380.0,
        )

        # 4. Nhánh Đắp: Decision Giật cơ đắp Var_H > H_GiatCo_Dap
        dec_dap_co = LogicBuilder.add_flow_decision(
            engine,
            condition_expr="Var_H > H_GiatCo_Dap",
            display_name="Giật cơ đắp?",
            x=150.0,
            y=480.0,
            auto_attach=False,
        )
        engine.set_decision_branches(dec_cut_fill["element"], true_ref_id=dec_dap_co["decision_node_id"])

        # Nhánh Đắp có giật cơ: P2 -> P3 (mái tầng 1 hạ H_GiatCo_Dap) -> P4 (mặt cơ B_Co_Dap) -> P5 (mái 2 xuống EG)
        GeometryBuilder.add_point_and_link(engine, "P3", "P2", PointGeometryType.SLOPE_DELTA_Y, "s_Dap", "-H_GiatCo_Dap", point_codes_str='"Dinh_Co_Dap"', add_link=True, link_name="L2", link_codes_str='"Daylight", "TaluyDap"', parent_node_id=f"{dec_dap_co['decision_node_id']}:True")
        GeometryBuilder.add_point_and_link(engine, "P4", "P3", PointGeometryType.SLOPE_DELTA_X, "i_Co_Dap", "B_Co_Dap", point_codes_str='"Mep_Co_Dap"', add_link=True, link_name="L3", link_codes_str='"Top", "MatCo"')
        GeometryBuilder.add_point_and_link(engine, "P5", "P4", PointGeometryType.SLOPE_TO_SURFACE, "s_Dap", "EG", point_codes_str='"Chan_Taluy_Dap"', add_link=True, link_name="L4", link_codes_str='"Daylight", "TaluyDap"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_06_duong_nang_cap_cai_tao(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 6: Nâng cấp cải tạo bù vênh & cạp mở rộng móng mặt."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="DuongNangCapCaiTao",
            description="Bù vênh trên mặt đường cũ kết hợp cạp mở rộng so le các lớp móng mặt",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("B_cap", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.00", "Bề rộng cạp (m)", "Phần mặt đường cạp mở rộng"),
            ("i_mat", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.02", "Độ dốc mặt (%)", "Độ dốc ngang mặt đường"),
            ("t1", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.05", "Dày BTNC C12.5 (m)", "Lớp bê tông nhựa trên"),
            ("t2", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.07", "Dày BTNC C19 (m)", "Lớp bê tông nhựa dưới"),
            ("t3", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.15", "Dày Base CPĐD 1 (m)", "Móng cấp phối loại 1"),
            ("t4", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.20", "Dày SubBase CPĐD 2 (m)", "Móng cấp phối loại 2"),
            ("mr_bac", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Mở rộng giật bậc (m)", "Mỗi lớp móng giật rộng ra ngoài"),
            ("b_cap_vao", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.30", "Cạp vào mép cũ (m)", "Độ sâu cắt ngàm vào mặt đường cũ"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Mặt trên lớp cạp P1 -> P2
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0", point_codes_str='"Mep_Cu"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "i_mat", "B_cap", point_codes_str='"Mep_Moi"', add_link=True, link_name="L1", link_codes_str='"Top", "Pave"')

        # Đáy lớp 1 Pave1: P3, P4
        GeometryBuilder.add_point_and_link(engine, "P3", "P1", PointGeometryType.DELTA_X_DELTA_Y, "-b_cap_vao", "-t1", point_codes_str='"Ngam_Cu_1"')
        GeometryBuilder.add_point_and_link(engine, "P4", "P2", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t1", point_codes_str='"Day_Pave1"', add_link=True, link_name="L2", link_codes_str='"Pave1"')
        GeometryBuilder.add_link(engine, "L3", "P2", "P4", link_codes_str='"Pave"')
        GeometryBuilder.add_link(engine, "L4", "P1", "P3", link_codes_str='"Ngam"')
        GeometryBuilder.add_shape(engine, "S1", ["L1", "L3", "L2", "L4"], shape_codes_str='"Pave1"')

        # Đáy lớp 2 Pave2: P5, P6
        GeometryBuilder.add_point_and_link(engine, "P5", "P3", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t2", point_codes_str='"Ngam_Cu_2"')
        GeometryBuilder.add_point_and_link(engine, "P6", "P4", PointGeometryType.DELTA_X_DELTA_Y, "mr_bac", "-t2", point_codes_str='"Day_Pave2"', add_link=True, link_name="L5", link_codes_str='"Pave2"')
        GeometryBuilder.add_link(engine, "L6", "P4", "P6", link_codes_str='"Pave"')
        GeometryBuilder.add_link(engine, "L7", "P3", "P5", link_codes_str='"Ngam"')
        GeometryBuilder.add_shape(engine, "S2", ["L2", "L6", "L5", "L7"], shape_codes_str='"Pave2"')

        # Đáy lớp 3 Base: P7, P8
        GeometryBuilder.add_point_and_link(engine, "P7", "P5", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t3", point_codes_str='"Ngam_Cu_3"')
        GeometryBuilder.add_point_and_link(engine, "P8", "P6", PointGeometryType.DELTA_X_DELTA_Y, "mr_bac", "-t3", point_codes_str='"Day_Base"', add_link=True, link_name="L8", link_codes_str='"Base"')
        GeometryBuilder.add_link(engine, "L9", "P6", "P8", link_codes_str='"Base"')
        GeometryBuilder.add_link(engine, "L10", "P5", "P7", link_codes_str='"Ngam"')
        GeometryBuilder.add_shape(engine, "S3", ["L5", "L9", "L8", "L10"], shape_codes_str='"Base"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_07_ket_cau_mat_duong_moi(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 7: Kết cấu áo đường mới 5 lớp tiêu chuẩn."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="KetCauMatDuongMoi",
            description="Kết cấu áo đường mềm 5 lớp tiêu chuẩn có mở rộng giật bậc so le và xoay siêu cao",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("B_lan", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "3.50", "Bề rộng làn xe (m)", "Bề rộng phần xe chạy 1 bên"),
            ("i_lan", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.02", "Độ dốc ngang (%)", "Độ dốc mặt đường khi không siêu cao"),
            ("t1", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.05", "Dày BTNC C12.5 (m)", "Lớp bê tông nhựa mặt trên"),
            ("t2", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.07", "Dày BTNC C19 (m)", "Lớp bê tông nhựa mặt dưới"),
            ("t3", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.15", "Dày Base CPĐD 1 (m)", "Móng cấp phối loại 1"),
            ("t4", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.20", "Dày SubBase CPĐD 2 (m)", "Móng cấp phối loại 2"),
            ("t5", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.30", "Dày Đất K98 (m)", "Lớp đệm cát hoặc đất K98"),
            ("mr_bac", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Mở rộng giật bậc (m)", "Giật rộng so le mỗi lớp móng"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Mặt trên áo đường P1 (Tim) -> P2 (Mép)
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0", point_codes_str='"Crown"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "i_lan", "B_lan", point_codes_str='"Mep_PXC"', add_link=True, link_name="L1", link_codes_str='"Top", "Pave"')

        # Lớp 1 Pave1: P3 (Tim), P4 (Mép)
        GeometryBuilder.add_point_and_link(engine, "P3", "P1", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t1", point_codes_str='"Day_Pave1_Tim"')
        GeometryBuilder.add_point_and_link(engine, "P4", "P2", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t1", point_codes_str='"Day_Pave1_Mep"', add_link=True, link_name="L2", link_codes_str='"Pave1"')
        GeometryBuilder.add_link(engine, "L3", "P2", "P4", link_codes_str='"Pave"')
        GeometryBuilder.add_link(engine, "L4", "P1", "P3", link_codes_str='"Crown"')
        GeometryBuilder.add_shape(engine, "S1", ["L1", "L3", "L2", "L4"], shape_codes_str='"Pave1"')

        # Lớp 2 Pave2: P5 (Tim), P6 (Mép mở rộng mr_bac)
        GeometryBuilder.add_point_and_link(engine, "P5", "P3", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t2", point_codes_str='"Day_Pave2_Tim"')
        GeometryBuilder.add_point_and_link(engine, "P6", "P4", PointGeometryType.DELTA_X_DELTA_Y, "mr_bac", "-t2", point_codes_str='"Day_Pave2_Mep"', add_link=True, link_name="L5", link_codes_str='"Pave2"')
        GeometryBuilder.add_link(engine, "L6", "P4", "P6", link_codes_str='"Pave"')
        GeometryBuilder.add_link(engine, "L7", "P3", "P5", link_codes_str='"Crown"')
        GeometryBuilder.add_shape(engine, "S2", ["L2", "L6", "L5", "L7"], shape_codes_str='"Pave2"')

        # Lớp 3 Base: P7 (Tim), P8 (Mép mở rộng thêm mr_bac)
        GeometryBuilder.add_point_and_link(engine, "P7", "P5", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-t3", point_codes_str='"Day_Base_Tim"')
        GeometryBuilder.add_point_and_link(engine, "P8", "P6", PointGeometryType.DELTA_X_DELTA_Y, "mr_bac", "-t3", point_codes_str='"Day_Base_Mep"', add_link=True, link_name="L8", link_codes_str='"Base"')
        GeometryBuilder.add_link(engine, "L9", "P6", "P8", link_codes_str='"Base"')
        GeometryBuilder.add_link(engine, "L10", "P5", "P7", link_codes_str='"Crown"')
        GeometryBuilder.add_shape(engine, "S3", ["L5", "L9", "L8", "L10"], shape_codes_str='"Base"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p

    @classmethod
    def build_08_giaco_maitaluy_giatco(cls, output_path: str | Path, version: str = "2026") -> Path:
        """Cấu kiện 8: Gia cố đỉnh, mái taluy giật cơ (giữ nguyên H lớp lót liên tục) & Chân khay."""
        out_p = Path(output_path)
        pkg = PktPackage.create_from_template(
            output_path=out_p,
            subassembly_name="GiaCoMaiTaluy_GiatCo",
            description="Gia cố mái taluy giật cơ liên tục giữ nguyên chiều dày H qua thân cơ và chân khay khóa đáy",
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())

        params = [
            ("EG", ParameterCategory.TARGET, ParameterDataType.SURFACE_TARGET, "-9999", "Mặt đất tự nhiên (EG)", "Bề mặt địa hình hiện trạng"),
            ("Ble", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Rộng lề đỉnh (m)", "Lề khóa đỉnh taluy"),
            ("i_le", ParameterCategory.INPUT, ParameterDataType.GRADE, "-0.04", "Dốc lề đỉnh (%)", "Độ dốc thoát nước lề"),
            ("H_GiatCo", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "6.00", "Ngưỡng giật cơ (m)", "Chiều cao taluy vượt ngưỡng thì giật cơ"),
            ("B_Co", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "1.50", "Rộng bậc cơ (m)", "Bề rộng bậc giật cơ thoát nước"),
            ("i_Co", ParameterCategory.INPUT, ParameterDataType.GRADE, "0.04", "Dốc bậc cơ (%)", "Độ dốc thoát nước mặt cơ"),
            ("s_Taluy", ParameterCategory.INPUT, ParameterDataType.SLOPE, "-0.6667", "Dốc mái taluy (1:1.5)", "Mái dốc 1:1.5"),
            ("H_GC", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.10", "Dày tấm đan gia cố (m)", "Chiều dày tấm đan BTCT"),
            ("H_Lot", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.08", "Dày đệm lót (m)", "Chiều dày lớp đá dăm đệm lót"),
            ("B_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.50", "Rộng chân khay (m)", "Bề rộng móng chân khay khóa mái"),
            ("H_ChanKhay", ParameterCategory.INPUT, ParameterDataType.DOUBLE, "0.80", "Sâu chân khay (m)", "Chiều sâu chôn chân khay vào đất"),
        ]
        for pname, cat, dt, def_val, disp, desc in params:
            ParameterBuilder.add_parameter(engine, pname, cat, dt, def_val, disp, desc)
            pkg.sync_parameter_to_atc(pname, dt.value, def_val, disp, desc)

        # Biến
        LogicBuilder.add_define_variable(engine, "Var_H", "Double", "0.0")

        # 1. Đỉnh taluy: P1 (Mép lề), P2 (Bờ vai taluy L1)
        GeometryBuilder.add_point_and_link(engine, "P1", "Origin", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "0.0", point_codes_str='"P1", "Crown"')
        GeometryBuilder.add_point_and_link(engine, "P2", "P1", PointGeometryType.SLOPE_DELTA_X, "i_le", "Ble", point_codes_str='"P2", "TopLe"', add_link=True, link_name="L1", link_codes_str='"Top", "LeDat"')

        # Khóa đỉnh: hạ P10 (-H_GC), P13 (-H_GC - H_Lot)
        GeometryBuilder.add_point_and_link(engine, "P10", "P1", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_GC", point_codes_str='"P10"')
        GeometryBuilder.add_point_and_link(engine, "P11", "P2", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_GC", point_codes_str='"P11"', add_link=True, link_name="L12", link_codes_str='"Day_GiaCo"')
        GeometryBuilder.add_link(engine, "L11", "P1", "P10", link_codes_str='"KhoaDinh"')
        GeometryBuilder.add_shape(engine, "S1", ["L1", "L11", "L12"], shape_codes_str='"S_DinhGC"')

        # Lớp đệm lót đỉnh P13, P14
        GeometryBuilder.add_point_and_link(engine, "P13", "P10", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_Lot", point_codes_str='"P13"')
        GeometryBuilder.add_point_and_link(engine, "P14", "P11", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_Lot", point_codes_str='"P14"', add_link=True, link_name="L17", link_codes_str='"Day_Lot"')

        # Điểm phụ AP1 bắn xuống mặt đất EG
        GeometryBuilder.add_point_and_link(engine, "AP1", "P2", PointGeometryType.SLOPE_TO_SURFACE, "-1.5", "EG", is_auxiliary=True)
        LogicBuilder.add_set_variable_value(engine, "Var_H", "Math.Abs(P2.Y - AP1.Y)", "Double")

        # 2. Mái dốc taluy tầng 1: P2 -> P21 (Đỉnh cơ)
        GeometryBuilder.add_point_and_link(engine, "P21", "P2", PointGeometryType.SLOPE_DELTA_Y, "s_Taluy", "-H_GiatCo", point_codes_str='"P21", "DinhCo"', add_link=True, link_name="L20", link_codes_str='"Daylight", "MaiTaluy"')

        # Mặt cơ: P21 -> P22 (Rộng B_Co, dốc i_Co)
        GeometryBuilder.add_point_and_link(engine, "P22", "P21", PointGeometryType.SLOPE_DELTA_X, "i_Co", "B_Co", point_codes_str='"P22", "MatCo"', add_link=True, link_name="L21", link_codes_str='"Top", "MatCo"')

        # GIỮ NGUYÊN CHIỀU DÀY LỚP GIA CỐ VÀ LỚP LÓT LIÊN TỤC QUA CƠ:
        # P32, P37 chạy song song qua thân cơ
        GeometryBuilder.add_point_and_link(engine, "P32", "P21", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_GC", point_codes_str='"P32"')
        GeometryBuilder.add_point_and_link(engine, "P37", "P32", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_Lot", point_codes_str='"P37"')

        # 3. Chân khay taluy (S_ChanKhayGC): P22 -> P23 -> P24 -> P26 -> P36 -> P38
        GeometryBuilder.add_point_and_link(engine, "P23", "P22", PointGeometryType.DELTA_X_DELTA_Y, "B_ChanKhay", "0.0", point_codes_str='"P23"', add_link=True, link_name="L23", link_codes_str='"ChanKhay"')
        GeometryBuilder.add_point_and_link(engine, "P24", "P23", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-H_ChanKhay", point_codes_str='"P24"', add_link=True, link_name="L24", link_codes_str='"ChanKhay"')
        GeometryBuilder.add_point_and_link(engine, "P26", "P24", PointGeometryType.DELTA_X_DELTA_Y, "-B_ChanKhay", "0.0", point_codes_str='"P26"', add_link=True, link_name="L26", link_codes_str='"ChanKhay"')
        GeometryBuilder.add_point_and_link(engine, "P36", "P26", PointGeometryType.DELTA_X_DELTA_Y, "0.10", "H_ChanKhay * 0.8", point_codes_str='"P36"', add_link=True, link_name="L36", link_codes_str='"ChanKhay"')
        GeometryBuilder.add_point_and_link(engine, "P38", "P36", PointGeometryType.DELTA_X_DELTA_Y, "0.0", "-0.15", point_codes_str='"P38"')

        # Khép shape Chân khay S_ChanKhayGC
        GeometryBuilder.add_link(engine, "L37", "P26", "P22", link_codes_str='"ChanKhay"')
        GeometryBuilder.add_shape(engine, "S2", ["L23", "L24", "L26", "L37"], shape_codes_str='"S_ChanKhayGC"')

        pkg.set_xaml_text(engine.to_xaml_string())
        pkg.save()
        return out_p
