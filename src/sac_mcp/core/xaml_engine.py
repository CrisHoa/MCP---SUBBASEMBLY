"""
WF4 XAML AST Parser & Mutator Engine cho Autodesk Subassembly Composer.
Hỗ trợ 100% cấu trúc XAML thực tế của Autodesk Subassembly Composer:
  - CreatePoint, CreateAuxPoint, LinkIntersection, AuxIntersection, StripSurfaceActivity
  - CreateLink, CreateAuxLink, FilletArcActivity
  - CreateShape, CreateLoop
  - FlowDecision, FlowSwitch, Sequence, ReportMessage
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from lxml import etree

from sac_mcp.models.schemas import (
    FlowNodeInfo,
    LinkInfo,
    ParameterInfo,
    PointInfo,
    ShapeInfo,
)


DEFAULT_NS = {
    "wf": "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "asa": "clr-namespace:Autodesk.SubassemblyComposer.API;assembly=Subassembly.API",
    "asa1": "clr-namespace:Autodesk.SubassemblyComposer.ActivityLibrary;assembly=Subassembly.ActivityLibrary",
    "asa2": "clr-namespace:Autodesk.SubassemblyComposer.ActivityLibrary;assembly=Subassembly.ActivityLibrary",
    "asw": "clr-namespace:Autodesk.SubassemblyComposer.WorkflowEngine;assembly=Subassembly.WorkflowEngine",
    "av": "http://schemas.microsoft.com/winfx/2006/xaml/presentation",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "mva": "clr-namespace:Microsoft.VisualBasic.Activities;assembly=System.Activities",
    "s": "clr-namespace:System;assembly=mscorlib",
    "sa": "clr-namespace:System.Activities;assembly=System.Activities",
    "sads": "http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger",
    "sap": "http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation",
    "sap2010": "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
    "sac": "clr-namespace:Autodesk.Civil.SubassemblyComposer.workflows;assembly=Autodesk.Civil.SubassemblyComposer.workflows",
    "scg": "clr-namespace:System.Collections.Generic;assembly=mscorlib",
    "this": "clr-namespace:",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml",
}

INTERNAL_SAC_PROPS = {"Geometry", "SubassemblyErrorCenter", "SubassemblyRunMode"}

# Các loại node trong WF4 Flowchart và các nhánh (slot) nối tiếp của từng loại
FLOW_NODE_TAGS = {"FlowStep", "FlowDecision", "FlowSwitch"}
SLOT_PROPS: Dict[str, Tuple[str, ...]] = {
    "FlowStep": ("Next",),
    "FlowDecision": ("True", "False"),
    "FlowSwitch": ("Default",),
}
_XREF_ATTR_RE = re.compile(r"^\{x:Reference\s+([^}\s]+)\s*\}$")


def _local(el: etree._Element) -> str:
    """Local name của element (bỏ namespace); trả '' cho comment / processing instruction."""
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


class FlowchartEngine:
    """Engine phân tích và chỉnh sửa cây cú pháp WF4 XAML của Subassembly Composer."""

    def __init__(self, xaml_text: str) -> None:
        self.parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
        self.root: etree._Element = etree.fromstring(xaml_text.encode("utf-8"), self.parser)
        self.warnings: List[str] = []
        self.nsmap: Dict[str, str] = dict(DEFAULT_NS)
        for prefix, uri in (self.root.nsmap or {}).items():
            if prefix is None:
                self.nsmap["wf"] = uri
            else:
                self.nsmap[prefix] = uri

    def qn(self, prefix: str, tag: str) -> str:
        """Tạo Qualified Name chuẩn Clark notation: {namespace_uri}tag."""
        uri = self.nsmap.get(prefix, DEFAULT_NS[prefix])
        return f"{{{uri}}}{tag}"

    def to_xaml_string(self) -> str:
        """Serialize cây XML trở lại chuỗi XAML chuẩn UTF-8 (không kèm XML declaration để WF4 XAML reader đọc được)."""
        etree.indent(self.root, space="  ")
        xml_bytes = etree.tostring(
            self.root,
            encoding="utf-8",
            xml_declaration=False,
            pretty_print=True,
        )
        return xml_bytes.decode("utf-8")

    def get_subassembly_class_short_name(self) -> str:
        x_class = self.root.get(self.qn("x", "Class"), "Subassembly")
        return x_class.split(".")[-1]

    def get_flowchart_element(self) -> etree._Element:
        nodes = self.root.xpath("//*[local-name()='Flowchart']")
        if not nodes:
            raise ValueError("Không tìm thấy phần tử <Flowchart> trong file XAML.")
        return nodes[0]

    def add_flowchart_variable(
        self,
        name: str,
        type_arguments: str = "x:Double",
        default_expr: Optional[str] = None,
    ) -> None:
        """Đăng ký một biến trong <Flowchart.Variables> chuẩn Native SAC."""
        flowchart = self.get_flowchart_element()
        vars_elements = flowchart.xpath("./*[local-name()='Flowchart.Variables']")
        if not vars_elements:
            vars_el = etree.Element(self.qn("wf", "Flowchart.Variables"))
            flowchart.insert(0, vars_el)
        else:
            vars_el = vars_elements[0]

        existing = vars_el.xpath("./*[local-name()='Variable' and @Name=$n]", n=name)
        if existing:
            return

        var_attrib = {
            self.qn("x", "TypeArguments"): type_arguments,
            "Name": name,
        }
        if default_expr is not None:
            var_attrib["Default"] = default_expr

        etree.SubElement(vars_el, self.qn("wf", "Variable"), attrib=var_attrib)

    def get_view_state_manager(self) -> Optional[etree._Element]:
        nodes = self.root.xpath("//*[local-name()='ViewStateManager']")
        return nodes[0] if nodes else None

    # ========================================================================
    # Quản lý ID (__ReferenceID0, __ReferenceID1...) & Tọa độ ViewState
    # ========================================================================

    def next_reference_id(self) -> str:
        """Sinh __ReferenceID{N} tiếp theo chưa từng được sử dụng trong Flowchart.xaml."""
        xml_str = etree.tostring(self.root, encoding="unicode")
        matches = re.findall(r"__ReferenceID(\d+)", xml_str)
        if not matches:
            return "__ReferenceID0"
        max_idx = max(int(m) for m in matches)
        return f"__ReferenceID{max_idx + 1}"

    def next_activity_id(self) -> str:
        """Sinh ActivityId số nguyên tuần tự (1, 2, 3...) chuẩn Native SAC."""
        xml_str = etree.tostring(self.root, encoding="unicode")
        matches = re.findall(r'ActivityId="(\d+)"', xml_str)
        next_idx = max((int(m) for m in matches), default=0) + 1
        return str(next_idx)

    def next_viewstate_idref(self, base_type: str) -> str:
        """Sinh sap2010:WorkflowViewState.IdRef duy nhất."""
        xml_str = etree.tostring(self.root, encoding="unicode")
        pattern = rf"{re.escape(base_type)}_(\d+)"
        matches = re.findall(pattern, xml_str)
        next_idx = max((int(m) for m in matches), default=0) + 1
        return f"{base_type}_{next_idx}"

    def get_view_locations(self) -> Dict[str, str]:
        """Trả về bảng ánh xạ {Id_hoặc_RefId: 'X,Y'} từ cả Inline ViewState lẫn ViewStateManager."""
        locations: Dict[str, str] = {}
        # 1. Inline ViewState bên trong các khối FlowStep / FlowDecision (Chuẩn Native SAC)
        flowchart = self.get_flowchart_element()
        for step in flowchart.xpath(".//*[local-name()='FlowStep' or local-name()='FlowDecision']"):
            ref_id = step.get(self.qn("x", "Name"))
            pts = step.xpath(
                "./*[local-name()='WorkflowViewStateService.ViewState']"
                "//*[local-name()='Point' and @*[local-name()='Key']='ShapeLocation']"
            )
            if ref_id and pts and pts[0].text:
                locations[ref_id] = pts[0].text.strip()

        # 2. ViewStateManager ở cuối file (nếu có)
        vsm = self.get_view_state_manager()
        if vsm is not None:
            for vsd in vsm.xpath(".//*[local-name()='ViewStateData']"):
                vs_id = vsd.get("Id")
                if not vs_id:
                    continue
                pts = vsd.xpath(".//*[local-name()='Point' and @*[local-name()='Key']='ShapeLocation']")
                if pts and pts[0].text:
                    locations[vs_id] = pts[0].text.strip()
        return locations

    def compute_next_shape_location(self) -> Tuple[float, float]:
        """Tính tọa độ (X, Y) cho khối tiếp theo để không bị đè lên nhau trên màn hình SAC."""
        locs = self.get_view_locations()
        max_y = 77.5
        base_x = 200.0
        for _, coord in locs.items():
            try:
                parts = coord.split(",")
                x_val = float(parts[0].strip())
                y_val = float(parts[1].strip())
                if y_val > max_y:
                    max_y = y_val
                    base_x = x_val
            except Exception:
                continue
        return (base_x, round(max_y + 85.0, 1))

    def register_view_state(
        self,
        id_ref: str,
        x: float,
        y: float,
        width: float = 200.0,
        height: float = 52.0,
        connector_from: Optional[Tuple[float, float]] = None,
        connector_to: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Thêm <sap2010:ViewStateData> cho một FlowStep / Activity mới."""
        vsm = self.get_view_state_manager()
        if vsm is None:
            return

        vsd = etree.SubElement(
            vsm,
            self.qn("sap2010", "ViewStateData"),
            attrib={
                "Id": id_ref,
                self.qn("sap", "VirtualizedContainerService.HintSize"): f"{int(width)},{int(height)}",
            },
        )
        wvss = etree.SubElement(vsd, self.qn("sap", "WorkflowViewStateService.ViewState"))
        dictionary = etree.SubElement(
            wvss,
            self.qn("scg", "Dictionary"),
            attrib={self.qn("x", "TypeArguments"): "x:String, x:Object"},
        )

        is_exp = etree.SubElement(
            dictionary,
            self.qn("x", "Boolean"),
            attrib={self.qn("x", "Key"): "IsExpanded"},
        )
        is_exp.text = "True"

        shape_loc = etree.SubElement(
            dictionary,
            self.qn("av", "Point"),
            attrib={self.qn("x", "Key"): "ShapeLocation"},
        )
        shape_loc.text = f"{x},{y}"

        shape_size = etree.SubElement(
            dictionary,
            self.qn("av", "Size"),
            attrib={self.qn("x", "Key"): "ShapeSize"},
        )
        shape_size.text = f"{int(width)},{int(height)}"

        if connector_from and connector_to:
            conn = etree.SubElement(
                dictionary,
                self.qn("av", "PointCollection"),
                attrib={self.qn("x", "Key"): "ConnectorLocation"},
            )
            conn.text = f"{connector_from[0]},{connector_from[1]} {connector_to[0]},{connector_to[1]}"

    # ========================================================================
    # Tìm kiếm & Nối dây các Node trong Flowchart
    # ========================================================================

    def find_node_by_reference_id(self, ref_id: str) -> Optional[etree._Element]:
        return self._node_index().get(ref_id.strip())

    # ------------------------------------------------------------------------
    # Mô hình đồ thị Flowchart (hỗ trợ cả node lồng inline lẫn <x:Reference>)
    # ------------------------------------------------------------------------

    def _node_index(self) -> Dict[str, etree._Element]:
        """Bảng {x:Name: element} cho mọi FlowStep / FlowDecision / FlowSwitch trong Flowchart."""
        index: Dict[str, etree._Element] = {}
        x_name = self.qn("x", "Name")
        main_fc = self.get_flowchart_element()
        for el in main_fc.iter(etree.Element):
            if _local(el) in FLOW_NODE_TAGS:
                # Bỏ qua node thuộc Flowchart con lồng bên trong (phạm vi tham chiếu riêng)
                owner = next((a for a in el.iterancestors() if _local(a) == "Flowchart"), None)
                if owner is not main_fc:
                    continue
                name = el.get(x_name)
                if name:
                    index[name] = el
        return index

    def _resolve_holder(
        self, holder: etree._Element, index: Dict[str, etree._Element]
    ) -> Optional[etree._Element]:
        """Đọc node đích bên trong một property element (VD: <FlowStep.Next>)."""
        for child in holder.iterchildren(etree.Element):
            ln = _local(child)
            if ln == "Reference":
                return index.get((child.text or "").strip())
            if ln in FLOW_NODE_TAGS:
                return child
            if ln == "Null":
                return None
        return None

    def get_slot_target(
        self, node: etree._Element, slot: str, index: Dict[str, etree._Element]
    ) -> Optional[etree._Element]:
        """Node đích của nhánh `slot` ('Next' / 'True' / 'False' / 'Default')."""
        attr_val = node.get(slot)
        if attr_val:
            m = _XREF_ATTR_RE.match(attr_val.strip())
            if m:
                return index.get(m.group(1))
        prop_name = f"{_local(node)}.{slot}"
        for prop in node.iterchildren(etree.Element):
            if _local(prop) == prop_name:
                return self._resolve_holder(prop, index)
        return None

    def get_start_node(self, index: Dict[str, etree._Element]) -> Optional[etree._Element]:
        flowchart = self.get_flowchart_element()
        attr_val = flowchart.get("StartNode")
        if attr_val:
            m = _XREF_ATTR_RE.match(attr_val.strip())
            if m:
                return index.get(m.group(1))
        for prop in flowchart.iterchildren(etree.Element):
            if _local(prop) == "Flowchart.StartNode":
                return self._resolve_holder(prop, index)
        return None

    def _successors(
        self, node: etree._Element, index: Dict[str, etree._Element]
    ) -> List[etree._Element]:
        kind = _local(node)
        result = [
            t for slot in SLOT_PROPS.get(kind, ()) if (t := self.get_slot_target(node, slot, index)) is not None
        ]
        if kind == "FlowSwitch":
            # Các nhánh Case nằm trực tiếp bên trong FlowSwitch (có x:Key)
            for child in node.iterchildren(etree.Element):
                ln = _local(child)
                if ln == "Reference":
                    t = index.get((child.text or "").strip())
                    if t is not None:
                        result.append(t)
                elif ln in FLOW_NODE_TAGS:
                    result.append(child)
        return result

    def reachable_nodes(self) -> List[etree._Element]:
        """Danh sách node tới được từ StartNode (thứ tự BFS)."""
        index = self._node_index()
        start = self.get_start_node(index)
        if start is None:
            return []
        seen = {id(start)}
        order = [start]
        i = 0
        while i < len(order):
            for nxt in self._successors(order[i], index):
                if id(nxt) not in seen:
                    seen.add(id(nxt))
                    order.append(nxt)
            i += 1
        return order

    def find_open_exits(self) -> List[Tuple[etree._Element, str]]:
        """
        Các "đầu ra mở" (chưa nối tiếp) của những node tới được từ StartNode:
          - FlowStep chưa có Next
          - FlowDecision thiếu nhánh True hoặc False
        (FlowSwitch không tính: thiếu Default là hợp lệ.)
        """
        index = self._node_index()
        exits: List[Tuple[etree._Element, str]] = []
        for node in self.reachable_nodes():
            kind = _local(node)
            if kind == "FlowSwitch":
                continue
            for slot in SLOT_PROPS.get(kind, ()):
                if self.get_slot_target(node, slot, index) is None:
                    exits.append((node, slot))
        return exits

    def set_slot_reference(self, node: etree._Element, slot: str, target_ref_id: str) -> None:
        """Gán nhánh `slot` của node trỏ tới `<x:Reference>target_ref_id</x:Reference>`."""
        if slot in node.attrib:
            del node.attrib[slot]
        prop_name = f"{_local(node)}.{slot}"
        for prop in list(node.iterchildren(etree.Element)):
            if _local(prop) == prop_name:
                node.remove(prop)
        ns_uri = etree.QName(node).namespace
        prop_el = etree.SubElement(node, f"{{{ns_uri}}}{prop_name}" if ns_uri else prop_name)
        etree.SubElement(prop_el, self.qn("x", "Reference")).text = target_ref_id

    def _set_start_reference(self, target_ref_id: str) -> None:
        flowchart = self.get_flowchart_element()
        if "StartNode" in flowchart.attrib:
            del flowchart.attrib["StartNode"]
        holders = [p for p in flowchart.iterchildren(etree.Element) if _local(p) == "Flowchart.StartNode"]
        if holders:
            sn = holders[0]
            for child in list(sn):
                sn.remove(child)
        else:
            sn = etree.SubElement(flowchart, self.qn("wf", "Flowchart.StartNode"))
        etree.SubElement(sn, self.qn("x", "Reference")).text = target_ref_id

    def _detach_slot_target(
        self, node: etree._Element, slot: str, index: Dict[str, etree._Element]
    ) -> Optional[str]:
        """
        Lấy tên node đang nối sau `node.slot`. Nếu node đó đang lồng inline bên trong,
        chuyển nó ra cấp Flowchart (đặt x:Name nếu thiếu) để có thể tham chiếu bằng x:Reference.
        """
        target = self.get_slot_target(node, slot, index)
        if target is None:
            return None
        x_name = self.qn("x", "Name")
        name = target.get(x_name)
        if not name:
            name = self.next_reference_id()
            target.set(x_name, name)
        holder = target.getparent()
        if holder is not None and holder.getparent() is node:
            self.get_flowchart_element().append(target)
        return name

    def _default_exits(self, node: etree._Element) -> List[Tuple[etree._Element, str]]:
        kind = _local(node)
        if kind == "FlowSwitch":
            return []
        index = self._node_index()
        return [(node, s) for s in SLOT_PROPS.get(kind, ()) if self.get_slot_target(node, s, index) is None]

    def attach_node_to_flowchart(
        self,
        new_node: etree._Element,
        new_ref_id: str,
        parent_ref_id: Optional[str] = None,
        exits: Optional[List[Tuple[etree._Element, str]]] = None,
    ) -> Optional[str]:
        """
        Gắn node mới vào luồng Flowchart.

        - parent_ref_id = None: nối vào MỌI đầu ra mở của luồng (tất cả nhánh hội tụ về node mới).
          Nếu Flowchart rỗng thì node mới thành StartNode.
        - parent_ref_id = '__ReferenceIDn' (FlowStep) hoặc '__ReferenceIDn:True' / ':False' (FlowDecision):
          CHÈN node mới ngay sau nhánh đó; phần luồng phía sau được nối tiếp vào `exits` của node mới
          (mặc định: Next của FlowStep, hoặc các nhánh còn trống của FlowDecision).

        Trả về chuỗi mô tả node cha đã nối (None nếu node mới là StartNode).
        """
        flowchart = self.get_flowchart_element()
        if new_node.getparent() is None:
            flowchart.append(new_node)
        if exits is None:
            exits = self._default_exits(new_node)

        index = self._node_index()

        if parent_ref_id:
            parent_name, _, branch = parent_ref_id.strip().partition(":")
            parent_name, branch = parent_name.strip(), branch.strip()
            parent = index.get(parent_name)
            if parent is None or parent is new_node:
                raise ValueError(
                    f"Không tìm thấy node cha '{parent_name}' trong Flowchart. "
                    "Dùng inspect_pkt để xem danh sách reference_id hợp lệ."
                )
            kind = _local(parent)
            if kind == "FlowStep":
                if branch and branch != "Next":
                    raise ValueError(f"Node '{parent_name}' là FlowStep, chỉ có nhánh 'Next' (không có '{branch}').")
                slot = "Next"
            elif kind == "FlowDecision":
                if branch:
                    if branch not in ("True", "False"):
                        raise ValueError(f"Nhánh '{branch}' không hợp lệ cho FlowDecision (chỉ 'True' hoặc 'False').")
                    slot = branch
                else:
                    open_slots = [s for s in ("True", "False") if self.get_slot_target(parent, s, index) is None]
                    if len(open_slots) != 1:
                        raise ValueError(
                            f"Node '{parent_name}' là FlowDecision: hãy chỉ rõ nhánh bằng "
                            f"'{parent_name}:True' hoặc '{parent_name}:False'."
                        )
                    slot = open_slots[0]
            else:
                raise ValueError(f"Chưa hỗ trợ chèn sau node loại {kind} ('{parent_name}').")

            old_target = self._detach_slot_target(parent, slot, index)
            self.set_slot_reference(parent, slot, new_ref_id)
            if old_target:
                if not exits:
                    self.warnings.append(
                        f"Node '{new_ref_id}' không còn nhánh trống nên phần luồng sau "
                        f"'{parent_name}.{slot}' (bắt đầu từ '{old_target}') đã bị tách khỏi luồng."
                    )
                for ex_node, ex_slot in exits:
                    self.set_slot_reference(ex_node, ex_slot, old_target)
            return parent_name if slot == "Next" else f"{parent_name}:{slot}"

        start = self.get_start_node(index)
        if start is None or start is new_node:
            self._set_start_reference(new_ref_id)
            return None

        open_exits = [(n, s) for n, s in self.find_open_exits() if n is not new_node]
        if not open_exits:
            raise ValueError(
                "Flowchart không còn đầu ra mở nào để nối tiếp (luồng khép kín hoặc kết thúc bằng FlowSwitch). "
                "Hãy truyền parent_node_id để chỉ định vị trí chèn."
            )
        x_name = self.qn("x", "Name")
        labels = []
        for ex_node, ex_slot in open_exits:
            if not ex_node.get(x_name):
                ex_node.set(x_name, self.next_reference_id())
            self.set_slot_reference(ex_node, ex_slot, new_ref_id)
            nm = ex_node.get(x_name)
            labels.append(nm if ex_slot == "Next" else f"{nm}:{ex_slot}")
        if len(open_exits) > 1:
            self.warnings.append(
                f"Luồng có {len(open_exits)} đầu ra mở ({', '.join(labels)}); tất cả đã được nối hội tụ về '{new_ref_id}'."
            )
        return ", ".join(labels)

    def create_sequence_step(
        self,
        display_name: str,
        x: float = 200.0,
        y: float = 100.0,
        parent_ref_id: Optional[str] = None,
        auto_attach: bool = True,
    ) -> Tuple[etree._Element, etree._Element, str]:
        """
        Tạo một FlowStep chứa khối <Sequence DisplayName="..."> chuẩn Autodesk Subassembly Composer.
        Trả về: (flow_step_el, sequence_el, ref_id)
        """
        ref_id = self.next_reference_id()
        step_vs_id = self.next_viewstate_idref("FlowStep")
        seq_vs_id = self.next_viewstate_idref("Sequence")

        flow_step = etree.Element(
            self.qn("wf", "FlowStep"),
            attrib={
                self.qn("x", "Name"): ref_id,
                self.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        seq_el = etree.SubElement(
            flow_step,
            self.qn("wf", "Sequence"),
            attrib={
                "DisplayName": display_name,
                self.qn("sap2010", "WorkflowViewState.IdRef"): seq_vs_id,
            },
        )
        seq_vss = etree.SubElement(seq_el, self.qn("sap", "WorkflowViewStateService.ViewState"))
        seq_scg = etree.SubElement(
            seq_vss,
            self.qn("scg", "Dictionary"),
            attrib={self.qn("x", "TypeArguments"): "x:String, x:Object"},
        )
        seq_exp = etree.SubElement(seq_scg, self.qn("x", "Boolean"), attrib={self.qn("x", "Key"): "IsExpanded"})
        seq_exp.text = "True"

        if auto_attach:
            self.attach_node_to_flowchart(
                new_node=flow_step,
                new_ref_id=ref_id,
                parent_ref_id=parent_ref_id,
            )
        else:
            self.get_flowchart_element().append(flow_step)

        self.register_view_state(
            id_ref=step_vs_id,
            x=x,
            y=y,
            width=200.0,
            height=52.0,
        )
        return flow_step, seq_el, ref_id

    def create_flow_decision(
        self,
        condition_expr: str,
        display_name: str = "",
        true_ref_id: Optional[str] = None,
        false_ref_id: Optional[str] = None,
        x: float = 260.0,
        y: float = 100.0,
        parent_ref_id: Optional[str] = None,
        auto_attach: bool = True,
    ) -> Tuple[etree._Element, str]:
        """
        Tạo khối <FlowDecision> chuẩn WF4/SAC với biểu thức điều kiện và 2 nhánh True / False.
        """
        ref_id = self.next_reference_id()
        dec_vs_id = self.next_viewstate_idref("FlowDecision")
        cond_formatted = condition_expr.strip()
        if not cond_formatted.startswith("["):
            cond_formatted = f"[{cond_formatted}]"

        disp = display_name.strip() or f"If ({condition_expr.strip()})"
        dec_el = etree.Element(
            self.qn("wf", "FlowDecision"),
            attrib={
                self.qn("x", "Name"): ref_id,
                "Condition": cond_formatted,
                "DisplayName": disp,
                self.qn("sap2010", "WorkflowViewState.IdRef"): dec_vs_id,
            },
        )
        if true_ref_id:
            tb = etree.SubElement(dec_el, self.qn("wf", "FlowDecision.True"))
            etree.SubElement(tb, self.qn("x", "Reference")).text = true_ref_id
        if false_ref_id:
            fb = etree.SubElement(dec_el, self.qn("wf", "FlowDecision.False"))
            etree.SubElement(fb, self.qn("x", "Reference")).text = false_ref_id

        if auto_attach:
            self.attach_node_to_flowchart(
                new_node=dec_el,
                new_ref_id=ref_id,
                parent_ref_id=parent_ref_id,
            )
        else:
            self.get_flowchart_element().append(dec_el)

        self.register_view_state(
            id_ref=dec_vs_id,
            x=x,
            y=y,
            width=79.0,
            height=87.0,
        )
        return dec_el, ref_id

    def set_decision_branches(
        self,
        decision_el: etree._Element,
        true_ref_id: Optional[str] = None,
        false_ref_id: Optional[str] = None,
    ) -> None:
        """Thiết lập hoặc cập nhật tham chiếu 2 nhánh True / False cho FlowDecision."""
        if true_ref_id:
            for child in decision_el.xpath("./*[local-name()='FlowDecision.True']"):
                decision_el.remove(child)
            tb = etree.SubElement(decision_el, self.qn("wf", "FlowDecision.True"))
            etree.SubElement(tb, self.qn("x", "Reference")).text = true_ref_id

        if false_ref_id:
            for child in decision_el.xpath("./*[local-name()='FlowDecision.False']"):
                decision_el.remove(child)
            fb = etree.SubElement(decision_el, self.qn("wf", "FlowDecision.False"))
            etree.SubElement(fb, self.qn("x", "Reference")).text = false_ref_id

    # ========================================================================
    # Các hàm Inspect / Trích xuất dữ liệu từ Flowchart.xaml (Chuẩn Native + Builder)
    # ========================================================================

    def extract_parameters(self) -> List[ParameterInfo]:
        """Trích xuất toàn bộ danh sách Input / Output / Target Parameters (bỏ qua 3 biến hệ thống của SAC)."""
        params: List[ParameterInfo] = []
        short_class = self.get_subassembly_class_short_name()

        meta_direction: Dict[str, str] = {}
        meta_display: Dict[str, str] = {}
        meta_desc: Dict[str, str] = {}
        for var in self.root.xpath("//*[local-name()='Variable']"):
            vname = var.get("Name", "")
            vdef = var.get("Default", "")
            m_dir = re.match(r"__SAC_Meta_Param_(.+)_Direction__(.+)", vname)
            if m_dir:
                meta_direction[m_dir.group(1)] = vdef or m_dir.group(2)
            m_disp = re.match(r"__SAC_Meta_Param_(.+)_DisplayName__(.*)", vname)
            if m_disp:
                meta_display[m_disp.group(1)] = vdef or m_disp.group(2)
            m_desc = re.match(r"__SAC_Meta_Param_(.+)_Description", vname)
            if m_desc:
                meta_desc[m_desc.group(1)] = vdef

        for prop in self.root.xpath("//*[local-name()='Members']/*[local-name()='Property']"):
            pname = prop.get("Name", "")
            ptype = prop.get("Type", "")
            if not pname or pname in INTERNAL_SAC_PROPS:
                continue

            if "OutArgument" in ptype and "InOutArgument" not in ptype:
                category = "Output"
            elif any(t in ptype for t in ("ElevationTarget", "OffsetTarget", "SurfaceTarget")):
                category = "Target"
            else:
                category = meta_direction.get(pname, "Input")

            clean_type = ptype
            m_arg = re.search(r"Argument\((?:[a-zA-Z0-9_]+:)?([a-zA-Z0-9_]+)\)", ptype)
            if m_arg:
                clean_type = m_arg.group(1)

            # Đọc DisplayName2Attribute & Description2Attribute chuẩn Native SAC
            disp_attr = prop.xpath(".//*[local-name()='DisplayName2Attribute']")
            disp_name = (
                disp_attr[0].get("DisplayName")
                if disp_attr and disp_attr[0].get("DisplayName")
                else meta_display.get(pname, pname)
            )
            desc_attr = prop.xpath(".//*[local-name()='Description2Attribute']")
            desc_val = (
                desc_attr[0].get("Description")
                if desc_attr and desc_attr[0].get("Description")
                else meta_desc.get(pname)
            )

            default_val = self.root.get(self.qn("this", f"{short_class}.{pname}"))
            if default_val is None:
                for attr_k, attr_v in self.root.attrib.items():
                    if attr_k.endswith(f".{pname}"):
                        default_val = attr_v
                        break

            params.append(
                ParameterInfo(
                    name=pname,
                    category=category,
                    data_type=clean_type,
                    default_value=default_val,
                    display_name=disp_name,
                    description=desc_val,
                )
            )
        return params

    def extract_points(self) -> List[PointInfo]:
        """
        Trích xuất danh sách Points (P1, P2...) và AuxPoints (AP1, AP2...) từ cả:
          - Native SAC: CreatePoint, CreateAuxPoint, LinkIntersection, AuxIntersection, StripSurfaceActivity
          - Builder: PointGeometry, AuxiliaryPointGeometry
        """
        points: List[PointInfo] = []
        flowchart = self.get_flowchart_element()

        xpath_query = (
            ".//*["
            "local-name()='CreatePoint' or "
            "local-name()='CreateAuxPoint' or "
            "local-name()='LinkIntersection' or "
            "local-name()='AuxIntersection' or "
            "local-name()='StripSurfaceActivity' or "
            "local-name()='PointGeometry' or "
            "local-name()='AuxiliaryPointGeometry' or "
            "local-name()='GeometryPoint'"
            "]"
        )

        for el in flowchart.xpath(xpath_query):
            tag = etree.QName(el).localname
            p_num = (
                el.get("PointNumber")
                or el.get("EndPointName")
                or el.get("Code")
                or el.get("DisplayName")
                or "P?"
            )
            p_type = (
                el.get("Positioning")
                or el.get("CreationType")
                or el.get("PointType")
                or el.get("GeometryType")
                or tag
            )
            from_pt = el.get("FromPoint") or el.get("StartPoint") or "Origin"
            if from_pt == "{x:Null}":
                from_pt = "Origin"

            # Đọc Arguments con của CreatePoint / CreateAuxPoint / LinkIntersection
            arg_map: Dict[str, str] = {}
            for in_arg in el.xpath(".//*[local-name()='InArgument' and @*[local-name()='Key']]"):
                k = in_arg.get(self.qn("x", "Key")) or ""
                val = (in_arg.text or "").strip()
                if k and val:
                    arg_map[k] = val

            p1 = (
                el.get("Param1")
                or el.get("DeltaX")
                or el.get("Slope")
                or el.get("Angle")
                or el.get("Depth")
                or next(
                    (
                        v
                        for k, v in arg_map.items()
                        if any(prefix in k for prefix in ("DeltaX", "Slope", "Angle", "Link1"))
                    ),
                    None,
                )
            )
            p2 = (
                el.get("Param2")
                or el.get("DeltaY")
                or el.get("Distance")
                or el.get("SurfaceTarget")
                or next(
                    (
                        v
                        for k, v in arg_map.items()
                        if any(
                            prefix in k
                            for prefix in ("DeltaY", "DeltaX2", "Distance", "SurfaceTarget", "Link2")
                        )
                    ),
                    None,
                )
            )

            # Đọc PointCodes
            p_codes = el.get("PointCodes") or el.get("Codes")
            if not p_codes or p_codes == "{x:Null}":
                code_args = el.xpath(
                    "./*[contains(local-name(), 'PointCodes')]//*[local-name()='InArgument']"
                )
                code_vals = [(c.text or "").strip() for c in code_args if (c.text or "").strip()]
                p_codes = ", ".join(code_vals) if code_vals else None

            add_link = (
                el.get("AutoLink", "False").lower() == "true"
                or el.get("AddLink", "False").lower() == "true"
            )
            link_num = el.get("AutoLinkGeometryName") or el.get("LinkNumber") or el.get("LinkCode")
            if link_num == "{x:Null}":
                link_num = None

            parent_step = el.xpath("ancestor::*[local-name()='FlowStep'][1]")
            step_id = parent_step[0].get(self.qn("x", "Name")) if parent_step else None

            points.append(
                PointInfo(
                    point_number=p_num,
                    point_type=p_type,
                    from_point=from_pt,
                    param_1_expr=p1,
                    param_2_expr=p2,
                    point_codes=p_codes,
                    add_link=add_link,
                    link_number=link_num,
                    flow_step_id=step_id,
                )
            )
        return points

    def extract_links(self) -> List[LinkInfo]:
        """
        Trích xuất danh sách Links (L1, L2...) và AuxLinks (AL1, AL2...) từ cả:
          - CreateLink, CreateAuxLink, FilletArcActivity, LinkGeometry
          - AutoLink="True" trên CreatePoint / CreateAuxPoint / PointGeometry
        """
        links: List[LinkInfo] = []
        flowchart = self.get_flowchart_element()

        # 1. Links khai báo qua CreateLink / CreateAuxLink / FilletArcActivity / LinkGeometry
        for el in flowchart.xpath(
            ".//*["
            "local-name()='CreateLink' or "
            "local-name()='CreateAuxLink' or "
            "local-name()='FilletArcActivity' or "
            "local-name()='LinkGeometry' or "
            "local-name()='GeometryLink'"
            "]"
        ):
            l_num = el.get("LinkNumber") or el.get("DisplayName") or "L?"
            sp = el.get("StartPoint") or el.get("FirstLink") or el.get("Point1")
            ep = el.get("EndPoint") or el.get("SecondLink") or el.get("EndPointName") or el.get("Point2")
            l_codes = el.get("LinkCodes") or el.get("Codes")
            if not l_codes or l_codes == "{x:Null}":
                code_args = el.xpath(
                    "./*[contains(local-name(), 'LinkCodes')]//*[local-name()='InArgument']"
                )
                code_vals = [(c.text or "").strip() for c in code_args if (c.text or "").strip()]
                l_codes = ", ".join(code_vals) if code_vals else None

            parent_step = el.xpath("ancestor::*[local-name()='FlowStep'][1]")
            step_id = parent_step[0].get(self.qn("x", "Name")) if parent_step else None

            links.append(
                LinkInfo(
                    link_number=l_num,
                    start_point=sp,
                    end_point=ep,
                    link_codes=l_codes,
                    flow_step_id=step_id,
                )
            )

        # 2. Links gộp chung trong CreatePoint / CreateAuxPoint / PointGeometry (AutoLink="True" hoặc AddLink="True")
        existing_link_nums = {lk.link_number for lk in links}
        for pt_el in flowchart.xpath(
            ".//*["
            "(local-name()='CreatePoint' or local-name()='CreateAuxPoint' or "
            "local-name()='PointGeometry' or local-name()='AuxiliaryPointGeometry') "
            "and (@AutoLink='True' or @AddLink='True')"
            "]"
        ):
            l_num = pt_el.get("AutoLinkGeometryName") or pt_el.get("LinkNumber")
            if l_num and l_num != "{x:Null}" and l_num not in existing_link_nums:
                existing_link_nums.add(l_num)
                parent_step = pt_el.xpath("ancestor::*[local-name()='FlowStep'][1]")
                step_id = parent_step[0].get(self.qn("x", "Name")) if parent_step else None

                l_codes = pt_el.get("LinkCodes") or pt_el.get("AutoLinkCodes")
                if not l_codes or l_codes == "{x:Null}":
                    code_args = pt_el.xpath(
                        "./*[contains(local-name(), 'AutoLinkCodes')]//*[local-name()='InArgument']"
                    )
                    code_vals = [(c.text or "").strip() for c in code_args if (c.text or "").strip()]
                    l_codes = ", ".join(code_vals) if code_vals else None

                from_pt = pt_el.get("FromPoint", "Origin")
                if from_pt == "{x:Null}":
                    from_pt = "Origin"

                links.append(
                    LinkInfo(
                        link_number=l_num,
                        start_point=from_pt,
                        end_point=pt_el.get("PointNumber"),
                        link_codes=l_codes,
                        flow_step_id=step_id,
                    )
                )
        return links

    def extract_shapes(self) -> List[ShapeInfo]:
        """Trích xuất danh sách Shapes (S1, S2...) từ CreateShape hoặc ShapeGeometry."""
        shapes: List[ShapeInfo] = []
        flowchart = self.get_flowchart_element()
        for el in flowchart.xpath(
            ".//*[local-name()='CreateShape' or local-name()='ShapeGeometry' or local-name()='GeometryShape']"
        ):
            s_num = el.get("ShapeNumber") or el.get("DisplayName") or "S?"
            links_raw = el.get("Links") or el.get("LinkList") or ""
            link_list = [item.strip() for item in links_raw.split(",") if item.strip()]

            s_codes = el.get("ShapeCodes") or el.get("Codes")
            if not s_codes or s_codes == "{x:Null}":
                code_args = el.xpath(
                    "./*[contains(local-name(), 'ShapeCodes')]//*[local-name()='InArgument']"
                )
                code_vals = [(c.text or "").strip() for c in code_args if (c.text or "").strip()]
                s_codes = ", ".join(code_vals) if code_vals else None

            parent_step = el.xpath("ancestor::*[local-name()='FlowStep'][1]")
            step_id = parent_step[0].get(self.qn("x", "Name")) if parent_step else None
            shapes.append(
                ShapeInfo(
                    shape_number=s_num,
                    link_list=link_list,
                    shape_codes=s_codes,
                    flow_step_id=step_id,
                )
            )
        return shapes

    def extract_flowchart_nodes(self) -> Tuple[Optional[str], List[FlowNodeInfo]]:
        """Trích xuất toàn bộ sơ đồ kết nối các khối trong Flowchart."""
        flowchart = self.get_flowchart_element()
        view_locs = self.get_view_locations()

        start_ref: Optional[str] = None
        sn_ref = flowchart.xpath("./*[local-name()='Flowchart.StartNode']/*[local-name()='Reference']")
        if sn_ref and sn_ref[0].text:
            start_ref = sn_ref[0].text.strip()
        else:
            sn_step = flowchart.xpath("./*[local-name()='Flowchart.StartNode']/*[@*[local-name()='Name']]")
            if sn_step:
                start_ref = sn_step[0].get(self.qn("x", "Name"))

        nodes: List[FlowNodeInfo] = []
        for step in flowchart.xpath(".//*[local-name()='FlowStep' or local-name()='FlowDecision']"):
            ref_id = step.get(self.qn("x", "Name"))
            if not ref_id:
                continue

            node_kind = etree.QName(step).localname
            step_vs_id = step.get(self.qn("sap2010", "WorkflowViewState.IdRef"))
            loc = view_locs.get(ref_id) or view_locs.get(step_vs_id or "")

            if node_kind == "FlowStep":
                act_type = "UnknownActivity"
                disp_name = None
                for child in step:
                    cname = etree.QName(child).localname
                    if cname not in (
                        "FlowStep.Next",
                        "WorkflowViewState.IdRef",
                        "WorkflowViewStateService.ViewState",
                    ):
                        act_type = cname
                        disp_name = (
                            child.get("DisplayName")
                            or child.get("PointNumber")
                            or child.get("LinkNumber")
                            or child.get("ShapeNumber")
                        )
                        if not loc:
                            c_vs_id = child.get(self.qn("sap2010", "WorkflowViewState.IdRef"))
                            loc = view_locs.get(c_vs_id or "")
                        break

                next_ref = None
                nxt = step.xpath("./*[local-name()='FlowStep.Next']//*[local-name()='Reference']")
                if nxt and nxt[0].text:
                    next_ref = nxt[0].text.strip()
                else:
                    nxt_inline = step.xpath("./*[local-name()='FlowStep.Next']/*[@*[local-name()='Name']]")
                    if nxt_inline:
                        next_ref = nxt_inline[0].get(self.qn("x", "Name"))

                nodes.append(
                    FlowNodeInfo(
                        reference_id=ref_id,
                        node_kind="FlowStep",
                        activity_type=act_type,
                        display_name=disp_name,
                        next_reference_id=next_ref,
                        view_location=loc,
                    )
                )
            elif node_kind == "FlowDecision":
                cond = step.get("Condition") or step.get("DisplayName") or "Decision"
                t_ref = None
                f_ref = None
                t_el = step.xpath("./*[local-name()='FlowDecision.True']//*[local-name()='Reference']")
                if t_el and t_el[0].text:
                    t_ref = t_el[0].text.strip()
                else:
                    t_inline = step.xpath("./*[local-name()='FlowDecision.True']/*[@*[local-name()='Name']]")
                    if t_inline:
                        t_ref = t_inline[0].get(self.qn("x", "Name"))

                f_el = step.xpath("./*[local-name()='FlowDecision.False']//*[local-name()='Reference']")
                if f_el and f_el[0].text:
                    f_ref = f_el[0].text.strip()
                else:
                    f_inline = step.xpath("./*[local-name()='FlowDecision.False']/*[@*[local-name()='Name']]")
                    if f_inline:
                        f_ref = f_inline[0].get(self.qn("x", "Name"))

                nodes.append(
                    FlowNodeInfo(
                        reference_id=ref_id,
                        node_kind="FlowDecision",
                        activity_type="FlowDecision",
                        display_name=cond,
                        true_reference_id=t_ref,
                        false_reference_id=f_ref,
                        view_location=loc,
                    )
                )

        return start_ref, nodes
