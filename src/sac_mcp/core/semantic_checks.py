"""
Kiểm tra ngữ nghĩa tĩnh cho Flowchart XAML của Subassembly Composer (chạy được cả khi máy không cài SAC).

Bổ sung cho Tầng 3 (biên dịch VB bằng DLL gốc). Các tham chiếu tên hình học như FromPoint="P5",
StartPoint / EndPoint, FirstLink / SecondLink, Links="L1,L2" là chuỗi thường nên trình biên dịch VB
không kiểm tra; sai tên chỉ lộ ra khi Preview trong SAC hoặc khi dựng Corridor trong Civil 3D.

Các kiểm tra:
  - ACTIVITY_UNKNOWN (ERROR): thẻ thuộc Subassembly.ActivityLibrary không có trong danh mục activity thật.
  - FLOW_REFERENCE   (ERROR): <x:Reference> / {x:Reference ...} trỏ tới x:Name không tồn tại.
  - FLOW_UNREACHABLE (WARNING): node trong Flowchart chính không tới được từ StartNode (không bao giờ chạy).
  - GEOMETRY_REFERENCE (WARNING): tham chiếu tới Point / Link chưa được tạo ở bất kỳ đâu trong file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from lxml import etree

from sac_mcp.core.xaml_engine import FLOW_NODE_TAGS, FlowchartEngine, _local

ACTIVITY_CATALOG_FILE = Path(__file__).resolve().parent.parent / "native" / "activity_catalog.json"
X_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
_XREF_ATTR_RE = re.compile(r"\{x:Reference\s+([^}\s]+)\s*\}")

# Thuộc tính định nghĩa tên Point / Link
_POINT_DEF_ATTRS = ("PointNumber", "StartPointName", "EndPointName")
# OffsetNumber: CreateOffset tạo đối tượng tham chiếu được như link (VD FromPoint="O1.EndPoint")
_LINK_DEF_ATTRS = ("LinkNumber", "LoopNumber", "OffsetNumber")
# Thuộc tính tham chiếu tới Point / Link đã có
_POINT_REF_ATTRS = ("FromPoint", "StartPoint", "EndPoint")
_LINK_REF_ATTRS = ("FirstLink", "SecondLink")
_LINK_LIST_ATTRS = ("Links",)


@dataclass
class SemanticIssue:
    severity: str  # "ERROR" | "WARNING"
    category: str
    message: str
    location: Optional[str] = None


@dataclass
class ActivitySpec:
    properties: Set[str]
    required: Set[str]


def load_activity_catalog() -> Dict[str, ActivitySpec]:
    """
    {tên activity: ActivitySpec(thuộc tính public, đối số bắt buộc)} sinh từ Subassembly.ActivityLibrary.dll
    (xem scripts/update_activity_catalog.py). Trả {} nếu thiếu file danh mục.
    """
    try:
        data = json.loads(ACTIVITY_CATALOG_FILE.read_text(encoding="utf-8"))
        return {
            name: ActivitySpec(set(info["properties"]), set(info.get("required", [])))
            for name, info in data["activities"].items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _is_null(val: Optional[str]) -> bool:
    return not val or val.strip() in ("{x:Null}", "")


def _label(el: etree._Element) -> str:
    return el.get("DisplayName") or el.get("PointNumber") or el.get("LinkNumber") or _local(el)


def check_semantics(
    xaml_text: str, catalog: Optional[Dict[str, ActivitySpec]] = None
) -> List[SemanticIssue]:
    engine = FlowchartEngine(xaml_text)
    root = engine.root
    issues: List[SemanticIssue] = []
    known_activities = catalog if catalog is not None else load_activity_catalog()

    # 1. Activity không có trong danh mục
    lib_elements: List[etree._Element] = []
    for el in root.iter(etree.Element):
        ns = etree.QName(el).namespace or ""
        ln = _local(el)
        if "Autodesk.SubassemblyComposer.ActivityLibrary" in ns and "." not in ln:
            lib_elements.append(el)
            if not known_activities:
                continue
            if ln not in known_activities:
                issues.append(
                    SemanticIssue(
                        "ERROR",
                        "ACTIVITY_UNKNOWN",
                        f"Activity '{ln}' không tồn tại trong Subassembly.ActivityLibrary "
                        f"(DisplayName='{el.get('DisplayName', '')}').",
                        location=ln,
                    )
                )
                continue
            # Thuộc tính (attribute không namespace + property element 'Tag.Member') phải có thật
            spec = known_activities[ln]
            members = [a for a in el.attrib if not a.startswith("{")]
            members += [
                _local(c).split(".", 1)[1]
                for c in el.iterchildren(etree.Element)
                if _local(c).startswith(f"{ln}.") and etree.QName(c).namespace == ns
            ]
            for member in sorted(spec.required - set(members)):
                issues.append(
                    SemanticIssue(
                        "ERROR",
                        "ARGUMENT_REQUIRED",
                        f"{ln} '{_label(el)}' thiếu đối số bắt buộc '{member}'.",
                        location=f"{ln}.{member}",
                    )
                )
            for member in members:
                if member not in spec.properties:
                    issues.append(
                        SemanticIssue(
                            "ERROR",
                            "ATTRIBUTE_UNKNOWN",
                            f"{ln} '{_label(el)}' không có thuộc tính '{member}' (SAC sẽ không mở được file).",
                            location=f"{ln}.{member}",
                        )
                    )

    # 2. x:Reference treo
    names = {v for el in root.iter(etree.Element) if (v := el.get(f"{{{X_NS}}}Name"))}
    for el in root.iter(etree.Element):
        if _local(el) == "Reference" and etree.QName(el).namespace == X_NS:
            ref = (el.text or "").strip()
            if ref and ref not in names:
                issues.append(
                    SemanticIssue("ERROR", "FLOW_REFERENCE", f"x:Reference trỏ tới '{ref}' không tồn tại.", location=ref)
                )
        for attr_val in el.attrib.values():
            for ref in _XREF_ATTR_RE.findall(attr_val):
                if ref not in names:
                    issues.append(
                        SemanticIssue(
                            "ERROR", "FLOW_REFERENCE", f"{{x:Reference {ref}}} trỏ tới node không tồn tại.", location=ref
                        )
                    )

    # 3. Node không tới được từ StartNode
    try:
        # So khớp theo x:Name: id() của proxy lxml không ổn định giữa các lần truy cập
        x_name = f"{{{X_NS}}}Name"
        reachable = {n.get(x_name) for n in engine.reachable_nodes()}
        for name, node in engine._node_index().items():
            if name not in reachable:
                issues.append(
                    SemanticIssue(
                        "WARNING",
                        "FLOW_UNREACHABLE",
                        f"Node '{name}' ({_flow_label(node)}) không nối vào luồng từ StartNode nên sẽ không bao giờ chạy.",
                        location=name,
                    )
                )
    except ValueError:
        pass  # Không có <Flowchart>

    # 4. Tham chiếu Point / Link chưa được tạo
    points: Set[str] = set()
    links: Set[str] = set()
    for el in lib_elements:
        for a in _POINT_DEF_ATTRS:
            if not _is_null(el.get(a)):
                points.add(el.get(a).strip())
        for a in _LINK_DEF_ATTRS:
            if not _is_null(el.get(a)):
                links.add(el.get(a).strip())
        if (el.get("AutoLink") or "").lower() == "true" and not _is_null(el.get("AutoLinkGeometryName")):
            links.add(el.get("AutoLinkGeometryName").strip())

    for el in lib_elements:
        for a in _POINT_REF_ATTRS:
            val = el.get(a)
            if _is_null(val) or val.startswith("["):
                continue
            if not _name_defined(val, points, links):
                issues.append(_geom_issue(el, a, val, "Point"))
        for a in _LINK_REF_ATTRS:
            val = el.get(a)
            if _is_null(val) or val.startswith("["):
                continue
            if not _name_defined(val, links, points):
                issues.append(_geom_issue(el, a, val, "Link"))
        for a in _LINK_LIST_ATTRS:
            val = el.get(a)
            if _is_null(val) or val.startswith("["):
                continue
            for item in (s.strip() for s in val.split(",")):
                if item and not _name_defined(item, links, points):
                    issues.append(_geom_issue(el, a, item, "Link"))
    return issues


def _name_defined(ref: str, primary: Set[str], secondary: Set[str]) -> bool:
    """
    Tên tham chiếu có được định nghĩa không. Chấp nhận dạng 'Tên.ThuộcTính'
    (VD: 'LO1.EndPoint' = điểm cuối vòng lặp LO1, 'L3.StartPoint').
    """
    ref = ref.strip()
    if ref in primary:
        return True
    base = ref.split(".", 1)[0]
    return "." in ref and (base in primary or base in secondary)


def _flow_label(node: etree._Element) -> str:
    for child in node.iterchildren(etree.Element):
        ln = _local(child)
        if "." not in ln and ln not in FLOW_NODE_TAGS:
            return _label(child)
    return node.get("DisplayName") or node.get("Condition") or _local(node)


def _geom_issue(el: etree._Element, attr: str, name: str, kind: str) -> SemanticIssue:
    return SemanticIssue(
        "WARNING",
        "GEOMETRY_REFERENCE",
        f"{_local(el)} '{_label(el)}': {attr}='{name}' tham chiếu {kind} chưa được tạo ở đâu trong file.",
        location=_label(el),
    )

