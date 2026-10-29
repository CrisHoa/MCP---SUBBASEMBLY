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


class FlowchartEngine:
    """Engine phân tích và chỉnh sửa cây cú pháp WF4 XAML của Subassembly Composer."""

    def __init__(self, xaml_text: str) -> None:
        self.parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
        self.root: etree._Element = etree.fromstring(xaml_text.encode("utf-8"), self.parser)
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
        xpath_expr = f"//*[@*[local-name()='Name']='{ref_id}']"
        matches = self.root.xpath(xpath_expr)
        return matches[0] if matches else None

    def find_tail_flow_step(self) -> Optional[etree._Element]:
        flowchart = self.get_flowchart_element()
        flow_steps = flowchart.xpath(".//*[local-name()='FlowStep' and @*[local-name()='Name']]")
        if not flow_steps:
            return None

        for step in reversed(flow_steps):
            next_nodes = step.xpath("./*[local-name()='FlowStep.Next']")
            if not next_nodes:
                return step
        return flow_steps[-1]

    def attach_node_to_flowchart(
        self,
        new_node: etree._Element,
        new_ref_id: str,
        parent_ref_id: Optional[str] = None,
    ) -> Optional[str]:
        flowchart = self.get_flowchart_element()
        parent_node: Optional[etree._Element] = None

        if parent_ref_id:
            parent_node = self.find_node_by_reference_id(parent_ref_id)
        else:
            parent_node = self.find_tail_flow_step()

        start_node_container = flowchart.xpath("./*[local-name()='Flowchart.StartNode']")
        has_valid_start = False
        if start_node_container:
            null_children = start_node_container[0].xpath("./*[local-name()='Null']")
            if not null_children and len(start_node_container[0]) > 0:
                has_valid_start = True

        flowchart.append(new_node)

        if not has_valid_start or parent_node is None:
            if not start_node_container:
                sn = etree.SubElement(flowchart, self.qn("wf", "Flowchart.StartNode"))
            else:
                sn = start_node_container[0]
                for child in list(sn):
                    sn.remove(child)
            xref = etree.SubElement(sn, self.qn("x", "Reference"))
            xref.text = new_ref_id
            return None

        parent_name = parent_node.get(self.qn("x", "Name"))
        existing_next = parent_node.xpath("./*[local-name()='FlowStep.Next']")
        for el in existing_next:
            parent_node.remove(el)

        next_el = etree.SubElement(parent_node, self.qn("wf", "FlowStep.Next"))
        xref = etree.SubElement(next_el, self.qn("x", "Reference"))
        xref.text = new_ref_id
        return parent_name

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
