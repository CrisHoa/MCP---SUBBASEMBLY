"""
Pydantic Schemas & Enums for Civil 3D Subassembly Composer (.pkt) MCP Server.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CivilVersion(str, Enum):
    """Phiên bản Autodesk Civil 3D / Subassembly Composer hỗ trợ (2025 - 2027)."""
    C3D_2025 = "2025"
    C3D_2026 = "2026"
    C3D_2027 = "2027"


class ParameterCategory(str, Enum):
    """Phân loại Parameter trong Subassembly Composer."""
    INPUT = "Input"
    OUTPUT = "Output"
    TARGET = "Target"


class ParameterDataType(str, Enum):
    """Kiểu dữ liệu của Parameter trong SAC (bao gồm cả kiểu Siêu cao & Đường sắt trang 2-3)."""
    # Input / Output types
    DOUBLE = "Double"
    INTEGER = "Integer"
    STRING = "String"
    BOOLEAN = "Boolean"
    YES_NO = "YesNo"
    GRADE = "Grade"
    SLOPE = "Slope"
    SIDE = "Side"
    # Superelevation & Rail Cant types (Trang 2-3)
    SUPERELEVATION = "Superelevation"
    SUPERELEVATION_AXIS_OF_ROTATION = "SuperelevationAxisOfRotation"
    SLOPE_DIRECTION = "SlopeDirection"
    POTENTIAL_PIVOT = "PotentialPivot"
    CANT = "Cant"
    # Target types (Trang 4)
    ELEVATION_TARGET = "ElevationTarget"
    OFFSET_TARGET = "OffsetTarget"
    SURFACE_TARGET = "SurfaceTarget"


class PointGeometryType(str, Enum):
    """Đầy đủ 9 phương thức xác định tọa độ Point trong Autodesk Subassembly Composer."""
    DELTA_X_DELTA_Y = "DeltaX_DeltaY"
    SLOPE_DELTA_X = "Slope_DeltaX"
    SLOPE_DELTA_Y = "Slope_DeltaY"
    SLOPE_TO_SURFACE = "Slope_To_Surface"
    DELTA_X_ON_SURFACE = "DeltaX_On_Surface"
    ANGLE_DELTA_X = "Angle_DeltaX"
    ANGLE_DELTA_Y = "Angle_DeltaY"
    ANGLE_DISTANCE = "Angle_Distance"
    INTERPOLATE = "Interpolate"


class CurveType(str, Enum):
    """Kiểu dựng cung cong trong SAC."""
    ARC_GENERAL = "ArcGeneral"
    ARC_3_POINTS = "Arc3Points"
    PARABOLA_GENERAL = "ParabolaGeneral"


class IntersectionType(str, Enum):
    """Kiểu tìm giao điểm hình học trong SAC."""
    TWO_LINKS = "IntersectionTwoLinks"
    LINK_POINT_SLOPE = "IntersectionLinkPointSlope"
    TWO_POINTS_SLOPE = "IntersectionTwoPointsSlope"


class RoundDaylightType(str, Enum):
    """Kiểu bo cong chân taluy tiếp giáp mặt đất."""
    BY_RADIUS = "Radius"
    BY_LENGTH = "Length"


class ReportMessageType(str, Enum):
    """Mức độ cảnh báo của khối Report Message trong Civil 3D Event Viewer."""
    INFORMATION = "Information"
    WARNING = "Warning"
    ERROR = "Error"


# ============================================================================
# Data Transfer Models cho inspect_pkt
# ============================================================================

class ParameterInfo(BaseModel):
    name: str = Field(..., description="Tên biến nội bộ (VD: LaneWidth, TargetSurface)")
    category: str = Field(..., description="Input, Output hoặc Target")
    data_type: str = Field(..., description="Kiểu dữ liệu XAML/CLR")
    default_value: Optional[str] = Field(None, description="Giá trị mặc định hoặc preview value")
    display_name: Optional[str] = Field(None, description="Tên hiển thị trên bảng Properties của Civil 3D")
    description: Optional[str] = Field(None, description="Mô tả tham số")


class PointInfo(BaseModel):
    point_number: str = Field(..., description="Mã định danh Point (VD: P1, P2)")
    point_type: str = Field(..., description="Kiểu dựng điểm (DeltaX_DeltaY, Slope_DeltaX...)")
    from_point: Optional[str] = Field(None, description="Điểm gốc tham chiếu (Origin, P1...)")
    param_1_expr: Optional[str] = Field(None, description="Biểu thức tham số 1 (VD: DeltaX, Slope, Angle...)")
    param_2_expr: Optional[str] = Field(None, description="Biểu thức tham số 2 (VD: DeltaY, Distance, SurfaceTarget...)")
    point_codes: Optional[str] = Field(None, description="Point Codes xuất sang Civil 3D")
    add_link: bool = Field(False, description="Có tự động tạo Link kèm theo trong cùng node hay không")
    link_number: Optional[str] = Field(None, description="Mã Link tạo kèm (VD: L1)")
    flow_step_id: Optional[str] = Field(None, description="__ReferenceID của FlowStep chứa Point này")


class LinkInfo(BaseModel):
    link_number: str = Field(..., description="Mã định danh Link (VD: L1, L2)")
    start_point: Optional[str] = Field(None, description="Điểm đầu (VD: P1)")
    end_point: Optional[str] = Field(None, description="Điểm cuối (VD: P2)")
    link_codes: Optional[str] = Field(None, description="Link Codes xuất sang Civil 3D (VD: 'Top', 'Pave')")
    flow_step_id: Optional[str] = Field(None, description="__ReferenceID của FlowStep chứa Link này")


class ShapeInfo(BaseModel):
    shape_number: str = Field(..., description="Mã định danh Shape (VD: S1)")
    link_list: List[str] = Field(default_factory=list, description="Danh sách các Link tạo thành Shape")
    shape_codes: Optional[str] = Field(None, description="Shape Codes (VD: 'Pave1')")
    flow_step_id: Optional[str] = Field(None, description="__ReferenceID của FlowStep chứa Shape này")


class FlowNodeInfo(BaseModel):
    reference_id: str = Field(..., description="x:Name của khối trong Flowchart (VD: __ReferenceID0)")
    node_kind: str = Field(..., description="FlowStep, FlowDecision, FlowSwitch...")
    activity_type: str = Field(..., description="PointGeometry, LinkGeometry, ReportMessage, Decision...")
    display_name: Optional[str] = Field(None, description="Tên hiển thị của khối trên Flowchart")
    next_reference_id: Optional[str] = Field(None, description="Node tiếp theo (cho FlowStep)")
    true_reference_id: Optional[str] = Field(None, description="Nhánh True (cho FlowDecision)")
    false_reference_id: Optional[str] = Field(None, description="Nhánh False (cho FlowDecision)")
    view_location: Optional[str] = Field(None, description="Tọa độ (X,Y) trên màn hình Flowchart")


class InspectPktResult(BaseModel):
    pkt_path: str
    subassembly_name: str
    description: str
    detected_civil_version: str
    packet_version_tag: str
    xaml_file_name: str
    opc_files: List[str]
    start_node_id: Optional[str] = None
    parameters: List[ParameterInfo] = Field(default_factory=list)
    points: List[PointInfo] = Field(default_factory=list)
    links: List[LinkInfo] = Field(default_factory=list)
    shapes: List[ShapeInfo] = Field(default_factory=list)
    flowchart_nodes: List[FlowNodeInfo] = Field(default_factory=list)
    raw_xaml: Optional[str] = None


class MutationResult(BaseModel):
    success: bool
    pkt_path: str
    action: str
    message: str
    created_reference_ids: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
