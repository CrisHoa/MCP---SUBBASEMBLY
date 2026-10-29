"""
Cơ sở tri thức (Knowledge Base) chuyên sâu cho Autodesk Subassembly Composer (SAC).
Được trích xuất và chuẩn hóa từ tài liệu chuyên đề:
"HƯỚNG DẪN SỬ DỤNG SUBASSEMBLY COMPOSER - HOA_C3D GROUP".

Bao gồm:
1. Danh mục toàn bộ Toolbox (Geometry, Advanced Geometry, Auxiliary, Workflow, Miscellaneous).
2. Quy chuẩn đặt tên biến Việt Nam (H_, B_, i_, KHT, DTK, LaneWidth, LaneSlope) & kiểu dữ liệu Siêu cao.
3. Bộ sinh công thức quay siêu cao tự động (Superelevation VB Expression Generator).
4. Từ điển tra cứu nhanh các hàm VB Expressions (Math, Logic) & SAC API (Point, Link, Target, Baseline).
"""

from __future__ import annotations

from typing import Any, Dict, List


# ============================================================================
# 1. DANH MỤC TOOLBOX TRONG SUBASSEMBLY COMPOSER (Trang 1, 4, 5)
# ============================================================================
SAC_TOOLBOX_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "Geometry": [
        {
            "element": "Point",
            "prefix": "P (P1, P2...)",
            "xaml_tag": "sac:PointGeometry",
            "role": "Điểm -> Tạo các đường Feature Line để tính khối lượng theo chiều dài L.",
        },
        {
            "element": "Link",
            "prefix": "L (L1, L2...)",
            "xaml_tag": "sac:LinkGeometry",
            "role": "Liên kết nối từ các điểm -> Tính khối lượng theo diện tích theo chiều dài L.",
        },
        {
            "element": "Shape",
            "prefix": "S (S1, S2...)",
            "xaml_tag": "sac:ShapeGeometry",
            "role": "Tạo diện tích khép kín từ các Link và Point -> Tính khối lượng theo thể tích theo chiều dài L.",
        },
    ],
    "Advanced_Geometry": [
        {"element": "Intersection Point", "xaml_tag": "sac:IntersectionPoint", "role": "Tạo Point từ giao điểm (Two Links, Link and Point Slope, Two Points Slope)."},
        {"element": "Curve", "xaml_tag": "sac:CurveGeometry", "role": "Tạo đường cong / đường tròn qua 3 điểm, tâm-bán kính..."},
        {"element": "Surface Link", "xaml_tag": "sac:SurfaceLink", "role": "Tạo liên kết bám theo bề mặt (Surface Target khai báo trong Target Parameters)."},
        {"element": "Daylight Rounding", "xaml_tag": "sac:DaylightRounding", "role": "Tạo vuốt tròn giữa mái taluy với bề mặt tự nhiên."},
        {"element": "Get Mark Point", "xaml_tag": "sac:GetMarkPoint", "role": "Lấy điểm đánh dấu từ Subassembly trước đó trong Assembly."},
        {"element": "Fillet Arc", "xaml_tag": "sac:FilletArc", "role": "Tạo đường vuốt cung tròn giữa 2 Link."},
        {"element": "Offset Geometry", "xaml_tag": "sac:OffsetGeometry", "role": "Tạo chuỗi phần tử song song (offset) từ các Link có sẵn."},
        {"element": "Loop Geometry", "xaml_tag": "sac:LoopGeometry", "role": "Tạo vòng lặp hình học (VD: bậc cấp taluy, cơ taluy lặp lại)."},
    ],
    "Auxiliary": [
        {"element": "Auxiliary Point", "prefix": "AP (AP1, AP2...)", "xaml_tag": "sac:AuxiliaryPointGeometry", "role": "Điểm hình học phụ trợ (chỉ dùng tính toán, không xuất ra Civil 3D)."},
        {"element": "Auxiliary Link", "prefix": "AL (AL1, AL2...)", "xaml_tag": "sac:AuxiliaryLinkGeometry", "role": "Đường liên kết phụ trợ (dùng tìm giao điểm/đo khoảng cách, không xuất ra Civil 3D)."},
        {"element": "Auxiliary Surface", "xaml_tag": "sac:AuxiliarySurface", "role": "Bề mặt phụ trợ."},
        {"element": "Auxiliary Intersection Point", "xaml_tag": "sac:AuxiliaryIntersectionPoint", "role": "Điểm giao phụ trợ."},
        {"element": "Auxiliary Mark Point", "xaml_tag": "sac:AuxiliaryMarkPoint", "role": "Điểm đánh dấu phụ trợ."},
    ],
    "Workflow": [
        {"element": "Flowchart", "xaml_tag": "Flowchart", "role": "Tạo thêm Flowchart con lồng bên trong để tổ chức module."},
        {"element": "Sequence", "xaml_tag": "Sequence", "role": "Tạo phân nhánh chia mục tuần tự."},
        {"element": "Decision", "xaml_tag": "FlowDecision", "role": "Tạo rẽ nhánh điều kiện IF (True / False)."},
        {"element": "Switch", "xaml_tag": "FlowSwitch", "role": "Tạo phân nhánh chia nhiều kiểu (Switch-Case)."},
    ],
    "Miscellaneous": [
        {"element": "Set Output Parameter", "xaml_tag": "sac:SetOutputParameter", "role": "Gán giá trị tính toán trả về cho Output Parameter."},
        {"element": "Define Variable", "xaml_tag": "sac:DefineVariable", "role": "Định nghĩa biến cục bộ trong Flowchart."},
        {"element": "Set Variable Value", "xaml_tag": "sac:SetVariableValue", "role": "Cập nhật giá trị mới cho biến cục bộ."},
        {"element": "Set Mark Point", "xaml_tag": "sac:SetMarkPoint", "role": "Đặt tên Mark Point tại 1 Point để Subassembly sau bắt vào."},
        {"element": "Report Message", "xaml_tag": "sac:ReportMessage", "role": "Xuất thông báo/cảnh báo/lỗi ra Event Viewer của Civil 3D."},
    ],
}


# ============================================================================
# 2. QUY ĐỊNH ĐẶT TÊN BIẾN & BIẾN MẶC ĐỊNH (Trang 3)
# ============================================================================
NAMING_CONVENTIONS: Dict[str, Any] = {
    "prefixes": {
        "H_": "Chiều cao / Chiều dày (Ví dụ: H_bonen = Chiều cao bó nền, H_ketcau = Chiều dày kết cấu)",
        "B_": "Bề rộng (Ví dụ: B_lan = Bề rộng làn, B_le = Bề rộng lề)",
        "i_": "Độ dốc (Ví dụ: i_matduong = Độ dốc mặt đường, i_taluy = Độ dốc mái taluy)",
    },
    "standard_default_parameters": [
        {
            "name": "KHT",
            "data_type": "String",
            "default_value": "Không hiển thị",
            "display_name": "Không hiển thị",
            "description": "Biến phân nhóm/tiêu đề ẩn trên bảng Properties",
        },
        {
            "name": "DTK",
            "data_type": "String",
            "default_value": "Điền thiết kế",
            "display_name": "Điền thiết kế",
            "description": "Nhãn phân mục thông số thiết kế",
        },
        {
            "name": "LaneWidth",
            "data_type": "Double",
            "default_value": "3.5",
            "display_name": "Bề rộng làn",
            "description": "Bề rộng làn xe tiêu chuẩn (m)",
        },
        {
            "name": "LaneSlope",
            "data_type": "Grade",
            "default_value": "-0.02",
            "display_name": "Độ dốc ngang đường",
            "description": "Độ dốc ngang mặt đường mặc định khi không áp siêu cao",
        },
    ],
}


# ============================================================================
# 3. HÀM SINH BIỂU THỨC QUAY SIÊU CAO (SUPERELEVATION EXPRESSION - Trang 3 & 4)
# ============================================================================
def build_superelevation_slope_expression(
    fallback_slope_param: str = "LaneSlope",
    use_superelevation_param: str = "UseSuperelevation",
    side_param: str = "Side",
) -> str:
    """
    Sinh công thức VB.NET chuẩn (8 nhánh Left/Right Inside/Outside Lane & Shoulder)
    điền vào mục Slope của Point/Link khi cần quay siêu cao tự động theo Civil 3D.

    Tham chiếu: Trang 3 & Trang 4 - Chuyên đề Subassembly Composer (HOA_C3D GROUP).
    """
    u = use_superelevation_param.strip()
    s = side_param.strip()
    fb = fallback_slope_param.strip()

    return (
        f"IF(({u}=LeftInsideLane)AND(({s}=Left)AND(SE.HasLeftLI)), SE.LeftLI, "
        f"IF(({u}=LeftOutsideLane)AND(({s}=Left)AND(SE.HasLeftLO)), SE.LeftLO, "
        f"IF(({u}=LeftInsideShoulder)AND(({s}=Left)AND(SE.HasLeftSI)), SE.LeftSI, "
        f"IF(({u}=LeftOutsideShoulder)AND(({s}=Left)AND(SE.HasLeftSO)), SE.LeftSO, "
        f"IF(({u}=RightInsideLane)AND(({s}=Right)AND(SE.HasRightLI)), SE.RightLI, "
        f"IF(({u}=RightOutsideLane)AND(({s}=Right)AND(SE.HasRightLO)), SE.RightLO, "
        f"IF(({u}=RightInsideShoulder)AND(({s}=Right)AND(SE.HasRightSI)), SE.RightSI, "
        f"IF(({u}=RightOutsideShoulder)AND(({s}=Right)AND(SE.HasRightSO)), SE.RightSO, "
        f"CType({fb},Double)))))))))"
    )


# ============================================================================
# 4. TỪ ĐIỂN VB EXPRESSIONS & SAC API FUNCTIONS (Trang 6, 7, 8, 9)
# ============================================================================
SAC_API_REFERENCE: Dict[str, List[Dict[str, str]]] = {
    "Math_Expressions": [
        {"syntax": "math.round(val, decimals)", "example": "math.round(2.568, 2) -> 2.57", "description": "Làm tròn đến số chữ số thập phân chỉ định (-2=hàng trăm, -1=hàng chục, 0=số nguyên, 1=phần mười, 2=phần trăm)."},
        {"syntax": "math.floor(val)", "example": "math.floor(2.568) -> 2", "description": "Làm tròn xuống số nguyên gần nhất <= giá trị chỉ định."},
        {"syntax": "math.ceiling(val)", "example": "math.ceiling(2.568) -> 3", "description": "Làm tròn lên số nguyên gần nhất >= giá trị chỉ định."},
        {"syntax": "math.max(a, b)", "example": "math.max(2.568, 0.813) -> 2.568", "description": "Trả về giá trị lớn hơn giữa 2 số."},
        {"syntax": "math.min(a, b)", "example": "math.min(2.568, 0.813) -> 0.813", "description": "Trả về giá trị nhỏ hơn giữa 2 số."},
        {"syntax": "math.abs(val)", "example": "math.abs(-2.568) -> 2.568", "description": "Trả về giá trị tuyệt đối."},
        {"syntax": "math.pi / math.e", "example": "math.pi -> 3.14159..., math.e -> 2.71828...", "description": "Hằng số Pi và hằng số e."},
        {"syntax": "math.sin(rad) / math.cos(rad) / math.tan(rad)", "example": "math.cos(math.pi) -> -1", "description": "Các hàm lượng giác (đơn vị góc tính bằng Radian)."},
        {"syntax": "math.asin(v) / math.acos(v) / math.atan(v)", "example": "math.atan(1) -> 0.78539...", "description": "Các hàm lượng giác ngược trả về góc tính bằng Radian."},
        {"syntax": "math.log(v) / math.log10(v) / math.exp(v)", "example": "math.log10(10) -> 1", "description": "Logarit tự nhiên (cơ số e), logarit cơ số 10 và hàm mũ e^x."},
        {"syntax": "math.pow(base, exp)", "example": "math.pow(2, 3) -> 8", "description": "Lũy thừa base^exp."},
        {"syntax": "math.sqrt(val)", "example": "math.sqrt(81) -> 9", "description": "Căn bậc hai."},
    ],
    "Logic_Expressions": [
        {"syntax": "IF(condition, true_val, false_val)", "example": "IF(P1.Y>P2.Y, 2, 3)", "description": "Hàm điều kiện 3 ngôi trong VB Expression."},
        {"syntax": "P1.Y > P2.Y / >= / < / <= / = / <>", "example": "P1.Y <> P2.Y", "description": "Các toán tử so sánh bằng (=), khác (<>), lớn/nhỏ hơn."},
        {"syntax": "(cond1)AND(cond2)", "example": "(P1.Y>P2.Y)AND(P2.X>P3.X)", "description": "Trả về True nếu cả 2 điều kiện cùng đúng."},
        {"syntax": "(cond1)OR(cond2)", "example": "(P1.Y>P2.Y)OR(P2.X>P3.X)", "description": "Trả về True nếu ít nhất 1 trong 2 điều kiện đúng."},
        {"syntax": "(cond1)XOR(cond2)", "example": "(P1.Y>P2.Y)XOR(P2.X>P3.X)", "description": "Trả về True nếu chỉ đúng 1 trong 2 điều kiện (cùng đúng hoặc cùng sai trả về False)."},
    ],
    "Point_And_AuxiliaryPoint_API": [
        {"syntax": "P1.X", "description": "Khoảng cách ngang từ điểm P1 đến Origin."},
        {"syntax": "P1.Y", "description": "Khoảng cách đứng từ điểm P1 đến Origin."},
        {"syntax": "P1.Offset", "description": "Khoảng cách ngang từ điểm P1 đến Assembly Baseline."},
        {"syntax": "P1.Elevation", "description": "Cao độ tuyệt đối của điểm P1 so với mốc 0."},
        {"syntax": 'P1.DistanceTo("P2")', "description": "Khoảng cách hình học giữa P1 và P2 (luôn dương)."},
        {"syntax": 'P1.SlopeTo("P2")', "description": "Độ dốc từ P1 đến P2 (hướng lên = dương, hướng xuống = âm)."},
        {"syntax": "P1.IsValid", "description": "Kiểm tra điểm P1 đã được gán và hợp lệ hay chưa (True/False)."},
        {"syntax": "P1.DistanceToSurface(SurfaceTarget)", "description": "Khoảng cách đứng từ P1 đến bề mặt SurfaceTarget (nằm trên bề mặt = dương, nằm dưới = âm)."},
    ],
    "Link_And_AuxiliaryLink_API": [
        {"syntax": "L1.Slope", "description": "Độ dốc của Link L1."},
        {"syntax": "L1.Length", "description": "Chiều dài nghiêng của Link L1 (luôn dương)."},
        {"syntax": "L1.Xlength", "description": "Chiều dài hình chiếu ngang từ điểm đầu đến điểm cuối của L1 (luôn dương)."},
        {"syntax": "L1.Ylength", "description": "Chiều cao hình chiếu đứng từ điểm đầu đến điểm cuối của L1 (luôn dương)."},
        {"syntax": "L1.StartPoint / L1.EndPoint", "description": "Đối tượng Point tại điểm đầu / điểm cuối của L1 (có thể chấm tiếp .X, .Y, .Elevation...)."},
        {"syntax": "L1.MaxY / L1.MinY", "description": "Cao độ Y lớn nhất / nhỏ nhất từ các điểm của Link L1."},
        {"syntax": "L1.MaxInterceptY(slope) / L1.MinInterceptY(slope)", "description": "Áp dụng tung độ giao cắt cao nhất / thấp nhất của các điểm trên Link với độ dốc cho trước."},
        {"syntax": "L1.LinearRegressionSlope / L1.LinearRegressionInterceptY", "description": "Độ dốc và tung độ gốc tính theo hồi quy tuyến tính qua các điểm của Link."},
        {"syntax": "L1.IsValid", "description": "Kiểm tra Link L1 đã được tạo hợp lệ hay chưa (True/False)."},
        {"syntax": 'L1.HasIntersection("L2", extendL1, extendL2)', "description": 'Kiểm tra L1 và L2 có giao nhau không. Có thể gọi L1.HasIntersection("L2") hoặc L1.HasIntersection("L2", true, true) để kéo dài tìm giao.'},
    ],
    "Targets_API": [
        {"syntax": "OffsetTarget.IsValid", "description": "Kiểm tra Offset Target có được gán hợp lệ trong Corridor hay không (True/False)."},
        {"syntax": "OffsetTarget.Offset", "description": "Khoảng cách ngang từ Offset Target đến Assembly Baseline."},
        {"syntax": "ElevationTarget.IsValid", "description": "Kiểm tra Elevation Target có được gán hợp lệ hay không (True/False)."},
        {"syntax": "ElevationTarget.Elevation", "description": "Khoảng cách đứng / cao độ từ Elevation Target đến Assembly Baseline."},
        {"syntax": "SurfaceTarget.IsValid", "description": "Kiểm tra Surface Target có tồn tại và hợp lệ hay không (True/False)."},
    ],
    "Baseline_And_Enum_API": [
        {"syntax": "Baseline.Station", "description": "Lý trình (Station) hiện tại trên Assembly Baseline."},
        {"syntax": "Baseline.Elevation", "description": "Cao độ thiết kế tại tim tuyến (Assembly Baseline)."},
        {"syntax": "Baseline.RegionStart / Baseline.RegionEnd", "description": "Lý trình đầu / cuối của Corridor Region hiện tại."},
        {"syntax": "Baseline.Grade", "description": "Độ dốc dọc của tim tuyến (Assembly Baseline)."},
        {"syntax": "Baseline.TurnDirection", "description": "Hướng rẽ đường cong nằm của Baseline (Left = -1, Non-curve = 0, Right = 1)."},
        {"syntax": "EnumerationType.Value", "description": "Giá trị chuỗi (String) của phần tử Enumeration hiện tại."},
    ],
}
