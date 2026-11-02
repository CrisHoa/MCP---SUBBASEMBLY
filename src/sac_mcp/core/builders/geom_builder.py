"""
Builder chuyên trách tạo các đối tượng hình học chuẩn Native Autodesk Subassembly Composer:
CreatePoint, CreateAuxPoint, CreateLink, CreateAuxLink, CreateShape, CreateLoop,
FilletArcActivity, LinkIntersection, AuxIntersection, StripSurfaceActivity.
"""

from __future__ import annotations

from typing import Any, Optional
from lxml import etree

from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import PointGeometryType


def format_arg_expr(expr_val: Any) -> str:
    """Format đối số InArgument chuẩn WF4/SAC: nếu là biến hoặc biểu thức thì bọc [expr], nếu là số thì để nguyên."""
    s = str(expr_val).strip()
    if not s:
        return "0.0"
    if s.startswith("[") and s.endswith("]"):
        return s
    try:
        float(s)
        return s
    except ValueError:
        return f"[{s}]"



class GeometryBuilder:
    """Tạo các khối <FlowStep> chứa Activity hình học chuẩn Autodesk Subassembly Composer."""

    @classmethod
    def add_point_and_link(
        cls,
        engine: FlowchartEngine,
        point_code: str,
        from_point: str = "Origin",
        point_type: PointGeometryType = PointGeometryType.DELTA_X_DELTA_Y,
        param_1_expr: str = "0.0",
        param_2_expr: str = "0.0",
        point_codes_str: str = "",
        add_link: bool = False,
        link_name: str = "",
        link_codes_str: str = "",
        is_auxiliary: bool = False,
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        point_code = point_code.strip()
        from_point = from_point.strip() or "Origin"

        act_id = engine.next_activity_id()
        tag_name = "CreateAuxPoint" if is_auxiliary else "CreatePoint"

        display_title = (
            f"{point_code}&{link_name}" if (add_link and link_name) else point_code
        )

        pos_str = "DeltaXAndDeltaY"
        if point_type == PointGeometryType.SLOPE_DELTA_X:
            pos_str = "SlopeAndDeltaX"
        elif point_type == PointGeometryType.SLOPE_DELTA_Y:
            pos_str = "SlopeAndDeltaY"
        elif point_type == PointGeometryType.SLOPE_TO_SURFACE:
            pos_str = "SlopeToSurface"
        elif point_type == PointGeometryType.DELTA_X_ON_SURFACE:
            pos_str = "DeltaXOnSurface"
        elif point_type == PointGeometryType.ANGLE_DELTA_X:
            pos_str = "AngleAndDeltaX"
        elif point_type == PointGeometryType.ANGLE_DELTA_Y:
            pos_str = "AngleAndDeltaY"
        elif point_type == PointGeometryType.ANGLE_DISTANCE:
            pos_str = "AngleAndDistance"
        elif point_type == PointGeometryType.INTERPOLATE:
            pos_str = "InterpolatePoint"

        pt_attrs = {
            "ActivityId": act_id,
            "ApplyAOR": "False",
            "DisplayName": display_title,
            "Geometry": "[Geometry]",
            "PointNumber": point_code,
            "Positioning": pos_str,
            "ShowErrors": "True",
            "Side": "[Side]",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        if from_point == "Origin":
            pt_attrs["FromPoint"] = "{x:Null}"
        else:
            pt_attrs["FromPoint"] = from_point

        if add_link and link_name:
            pt_attrs["AutoLink"] = "True"
            pt_attrs["AutoLinkGeometryName"] = link_name.strip()
        else:
            pt_attrs["AutoLink"] = "False"
            pt_attrs["AutoLinkGeometryName"] = "{x:Null}"

        p_codes_list = [
            c.strip().strip('"').strip("'")
            for c in point_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not p_codes_list:
            pt_attrs["PointCodes"] = "{x:Null}"

        l_codes_list = [
            c.strip().strip('"').strip("'")
            for c in link_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not l_codes_list:
            pt_attrs["AutoLinkCodes"] = "{x:Null}"

        pt_el = etree.Element(engine.qn("asa2", tag_name), attrib=pt_attrs)

        args_el = etree.SubElement(pt_el, engine.qn("asa2", f"{tag_name}.Arguments"))
        p1_val = str(param_1_expr).strip()
        p2_val = str(param_2_expr).strip()

        if pos_str == "DeltaXAndDeltaY":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaX1"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaY1"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "SlopeAndDeltaX":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Slope2"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaX2"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "SlopeAndDeltaY":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Slope5"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaY5"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "SlopeToSurface":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Slope3"},
            )
            a1.text = format_arg_expr(p1_val)
            rev = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Boolean", engine.qn("x", "Key"): "ReverseSlopeDirection3"},
            )
            rev.text = "False"
            st = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "asw:SurfaceTarget", engine.qn("x", "Key"): "SurfaceTarget3"},
            )
            st.text = format_arg_expr(p2_val)
            dx = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaXForLayout3"},
            )
            dx.text = "5"
            se = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Boolean", engine.qn("x", "Key"): "ShowErrors"},
            )
            se.text = "True"
        elif pos_str == "DeltaXOnSurface":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaX4"},
            )
            a1.text = format_arg_expr(p1_val)
            st = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "asw:SurfaceTarget", engine.qn("x", "Key"): "SurfaceTarget4"},
            )
            st.text = format_arg_expr(p2_val)
        elif pos_str == "AngleAndDeltaX":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Angle6"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaX6"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "AngleAndDeltaY":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Angle7"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "DeltaY7"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "AngleAndDistance":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Angle8"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Distance8"},
            )
            a2.text = format_arg_expr(p2_val)
        elif pos_str == "InterpolatePoint":
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:String", engine.qn("x", "Key"): "DestPoint"},
            )
            a1.text = p1_val.strip('"').strip("'")
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "InterpolateParam"},
            )
            a2.text = format_arg_expr(p2_val)
        else:
            a1 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Param1"},
            )
            a1.text = format_arg_expr(p1_val)
            a2 = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "Param2"},
            )
            a2.text = format_arg_expr(p2_val)


        if p_codes_list:
            pc_el = etree.SubElement(pt_el, engine.qn("asa2", f"{tag_name}.PointCodes"))
            scg_p = etree.SubElement(
                pc_el,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(p_codes_list))),
                },
            )
            for c in p_codes_list:
                arg = etree.SubElement(
                    scg_p,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                arg.text = c

        if l_codes_list:
            lc_el = etree.SubElement(pt_el, engine.qn("asa2", f"{tag_name}.AutoLinkCodes"))
            scg_l = etree.SubElement(
                lc_el,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(l_codes_list))),
                },
            )
            for c in l_codes_list:
                arg = etree.SubElement(
                    scg_l,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                arg.text = c

        vss = etree.SubElement(pt_el, engine.qn("sap", "WorkflowViewStateService.ViewState"))
        scg_d = etree.SubElement(
            vss,
            engine.qn("scg", "Dictionary"),
            attrib={engine.qn("x", "TypeArguments"): "x:String, x:Object"},
        )
        exp = etree.SubElement(scg_d, engine.qn("x", "Boolean"), attrib={engine.qn("x", "Key"): "IsExpanded"})
        exp.text = "True"

        if target_container is not None:
            target_container.append(pt_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "point_code": point_code,
                "is_auxiliary": is_auxiliary,
                "from_point": from_point,
                "point_type": point_type.value,
                "param_1_expr": param_1_expr,
                "param_2_expr": param_2_expr,
                "add_link": add_link,
                "link_name": link_name if add_link else None,
                "view_location": None,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(pt_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
            connector_from=(x_pos + 100.0, y_pos - 33.0),
            connector_to=(x_pos + 100.0, y_pos),
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "point_code": point_code,
            "is_auxiliary": is_auxiliary,
            "from_point": from_point,
            "point_type": point_type.value,
            "param_1_expr": param_1_expr,
            "param_2_expr": param_2_expr,
            "add_link": add_link,
            "link_name": link_name if add_link else None,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_link(
        cls,
        engine: FlowchartEngine,
        link_name: str = "",
        start_point: str = "",
        end_point: str = "",
        link_codes_str: str = "",
        apply_aor: bool = False,
        is_auxiliary: bool = False,
        parent_node_id: Optional[str] = None,
        link_code: str = "",
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        actual_link_name = (link_name or link_code).strip()
        start_point = start_point.strip()
        end_point = end_point.strip()
        act_id = engine.next_activity_id()
        tag_name = "CreateAuxLink" if is_auxiliary else "CreateLink"

        link_attrs = {
            "ActivityId": act_id,
            "ApplyAOR": "True" if apply_aor else "False",
            "DisplayName": actual_link_name,
            "LinkNumber": actual_link_name,
            "StartPoint": start_point,
            "EndPoint": end_point,
            "Geometry": "[Geometry]",
            "IsEnabled": "True",
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in link_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not codes_list:
            link_attrs["LinkCodes"] = "{x:Null}"

        link_el = etree.Element(engine.qn("asa2", tag_name), attrib=link_attrs)

        if codes_list:
            codes_container = etree.SubElement(link_el, engine.qn("asa2", f"{tag_name}.LinkCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        if target_container is not None:
            target_container.append(link_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "link_name": actual_link_name,
                "start_point": start_point,
                "end_point": end_point,
                "link_codes": codes_list,
                "is_auxiliary": is_auxiliary,
                "view_location": None,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(link_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
            connector_from=(x_pos + 100.0, y_pos - 33.0),
            connector_to=(x_pos + 100.0, y_pos),
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "link_name": actual_link_name,
            "start_point": start_point,
            "end_point": end_point,
            "link_codes": codes_list,
            "is_auxiliary": is_auxiliary,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_fillet_arc(
        cls,
        engine: FlowchartEngine,
        link_number: str,
        first_link: str,
        second_link: Optional[str] = None,
        round_radius: float = 0.05,
        end_point_name: Optional[str] = None,
        link_codes_str: str = "",
        parent_node_id: Optional[str] = None,
    ) -> dict:
        link_number = link_number.strip()
        first_link = first_link.strip()
        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        act_id = engine.next_activity_id()

        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )

        arc_attrs = {
            "ActivityId": act_id,
            "ApplyAOR": "False",
            "DisplayName": link_number,
            "LinkNumber": link_number,
            "FirstLink": first_link,
            "RoundRadius": str(round_radius),
            "Geometry": "[Geometry]",
            "IsEnabled": "True",
            "ShowErrors": "True",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }
        if second_link:
            arc_attrs["SecondLink"] = second_link.strip()
        if end_point_name:
            arc_attrs["EndPointName"] = end_point_name.strip()

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in link_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not codes_list:
            arc_attrs["LinkCodes"] = "{x:Null}"

        arc_el = etree.SubElement(flow_step, engine.qn("asa2", "FilletArcActivity"), attrib=arc_attrs)

        if codes_list:
            codes_container = etree.SubElement(arc_el, engine.qn("asa2", "FilletArcActivity.LinkCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
            connector_from=(x_pos + 100.0, y_pos - 33.0),
            connector_to=(x_pos + 100.0, y_pos),
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "link_number": link_number,
            "first_link": first_link,
            "round_radius": round_radius,
            "link_codes": codes_list,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_loop_geometry(
        cls,
        engine: FlowchartEngine,
        loop_code: str,
        links: list[str],
        repetition_count: int = 1,
        parent_node_id: Optional[str] = None,
    ) -> dict:
        loop_code = loop_code.strip()
        links_joined = ",".join(lk.strip() for lk in links if lk.strip())

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        act_id = engine.next_activity_id()

        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        etree.SubElement(
            flow_step,
            engine.qn("asa2", "CreateLoop"),
            attrib={
                "ActivityId": act_id,
                "DisplayName": loop_code,
                "LoopNumber": loop_code,
                "Links": links_joined,
                "LoopDRepetition": str(repetition_count),
                "Geometry": "[Geometry]",
                "ShowErrors": "True",
                engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
            },
        )

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "loop_code": loop_code,
            "links": [lk.strip() for lk in links if lk.strip()],
            "repetition_count": repetition_count,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_intersection_point(
        cls,
        engine: FlowchartEngine,
        point_code: str,
        link1: str,
        link2: str,
        is_auxiliary: bool = False,
        point_codes_str: str = "",
        parent_node_id: Optional[str] = None,
    ) -> dict:
        point_code = point_code.strip()
        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        act_id = engine.next_activity_id()
        tag_name = "AuxIntersection" if is_auxiliary else "LinkIntersection"

        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )

        int_el = etree.SubElement(
            flow_step,
            engine.qn("asa2", tag_name),
            attrib={
                "ActivityId": act_id,
                "DisplayName": point_code,
                "PointNumber": point_code,
                "CreationType": "IntersectionTwoLinks",
                "Index": "0",
                "Geometry": "[Geometry]",
                "ShowErrors": "True",
                "Side": "[Side]",
                engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
            },
        )

        args_el = etree.SubElement(int_el, engine.qn("asa2", f"{tag_name}.Arguments"))
        arg1 = etree.SubElement(
            args_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:String", engine.qn("x", "Key"): "FirstLink1"},
        )
        arg1.text = link1.strip()
        arg2 = etree.SubElement(
            args_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:String", engine.qn("x", "Key"): "SecondLink1"},
        )
        arg2.text = link2.strip()
        ext1 = etree.SubElement(
            args_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:Boolean", engine.qn("x", "Key"): "ExtendFirstLink1"},
        )
        ext1.text = "True"
        ext2 = etree.SubElement(
            args_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:Boolean", engine.qn("x", "Key"): "ExtendSecondLink1"},
        )
        ext2.text = "True"

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in point_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if codes_list:
            pc_el = etree.SubElement(int_el, engine.qn("asa2", f"{tag_name}.PointCodes"))
            scg_p = etree.SubElement(
                pc_el,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                arg = etree.SubElement(
                    scg_p,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                arg.text = c

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "point_code": point_code,
            "is_auxiliary": is_auxiliary,
            "link1": link1,
            "link2": link2,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_strip_surface(
        cls,
        engine: FlowchartEngine,
        display_name: str = "Strip_VHC",
        depth_expr: str = "0.3",
        end_point_name: Optional[str] = None,
        end_offset: float = -5.0,
        end_offset_target: Optional[str] = None,
        link_codes_str: str = "Link_VHC",
        parent_node_id: Optional[str] = None,
    ) -> dict:
        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        act_id = engine.next_activity_id()

        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )

        strip_el = etree.SubElement(
            flow_step,
            engine.qn("asa2", "StripSurfaceActivity"),
            attrib={
                "ActivityId": act_id,
                "DisplayName": display_name,
                "Geometry": "[Geometry]",
                "ShowErrors": "True",
                engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
            },
        )
        args_el = etree.SubElement(strip_el, engine.qn("asa2", "StripSurfaceActivity.Arguments"))
        dp_arg = etree.SubElement(
            args_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:Double", engine.qn("x", "Key"): "StripDepth"},
        )
        dp_arg.text = str(depth_expr)

        if end_point_name:
            ep_arg = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:String", engine.qn("x", "Key"): "EndPointName"},
            )
            ep_arg.text = str(end_point_name)

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in link_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if codes_list:
            codes_container = etree.SubElement(strip_el, engine.qn("asa2", "StripSurfaceActivity.LinkCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "display_name": display_name,
            "depth_expr": depth_expr,
            "end_point_name": end_point_name,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_curve(
        cls,
        engine: FlowchartEngine,
        link_number: str,
        start_point: str,
        end_point: str,
        center_point: Optional[str] = None,
        creation_type: str = "ArcGeneral",
        num_increments: int = 5,
        link_codes_str: str = "",
        is_auxiliary: bool = False,
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo đối tượng CreateCurve hoặc CreateAuxCurve chuẩn Native SAC."""
        link_number = link_number.strip()
        start_point = start_point.strip()
        end_point = end_point.strip()
        act_id = engine.next_activity_id()
        tag_name = "CreateAuxCurve" if is_auxiliary else "CreateCurve"

        curve_attrs = {
            "ActivityId": act_id,
            "CreationType": creation_type,
            "DisplayName": link_number,
            "EndPoint": end_point,
            "Geometry": "[Geometry]",
            "LinkNumber": link_number,
            "NoIncrements": str(num_increments),
            "ShowErrors": "True",
            "Side": "[Side]",
            "StartPoint": start_point,
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in link_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not codes_list:
            curve_attrs["LinkCodes"] = "{x:Null}"

        curve_el = etree.Element(engine.qn("asa2", tag_name), attrib=curve_attrs)

        args_el = etree.SubElement(curve_el, engine.qn("asa2", f"{tag_name}.Arguments"))
        if center_point:
            cp_arg = etree.SubElement(
                args_el,
                engine.qn("wf", "InArgument"),
                attrib={engine.qn("x", "TypeArguments"): "x:String", engine.qn("x", "Key"): "CenterPoint"},
            )
            cp_arg.text = center_point.strip()

        if codes_list:
            codes_container = etree.SubElement(curve_el, engine.qn("asa2", f"{tag_name}.LinkCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        if target_container is not None:
            target_container.append(curve_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "link_number": link_number,
                "start_point": start_point,
                "end_point": end_point,
                "creation_type": creation_type,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(curve_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "link_number": link_number,
            "start_point": start_point,
            "end_point": end_point,
            "creation_type": creation_type,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_offset_geometry(
        cls,
        engine: FlowchartEngine,
        offset_code: str,
        links: list[str],
        offset_distance: float = 0.15,
        offset_codes_str: str = "",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo khối CreateOffset chuẩn Native SAC."""
        offset_code = offset_code.strip()
        links_joined = ",".join(lk.strip() for lk in links if lk.strip())
        act_id = engine.next_activity_id()

        off_attrs = {
            "ActivityId": act_id,
            "DisplayName": offset_code,
            "Geometry": "[Geometry]",
            "Links": links_joined,
            "OffsetDistance": str(offset_distance),
            "OffsetNumber": offset_code,
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in offset_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not codes_list:
            off_attrs["OffsetCodes"] = "{x:Null}"

        off_el = etree.Element(engine.qn("asa2", "CreateOffset"), attrib=off_attrs)

        comp_el = etree.SubElement(off_el, engine.qn("asa2", "CreateOffset.ComponentNames"))
        for lk in links:
            s_el = etree.SubElement(comp_el, engine.qn("x", "String"))
            s_el.text = lk.strip()

        if codes_list:
            codes_container = etree.SubElement(off_el, engine.qn("asa2", "CreateOffset.OffsetCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        if target_container is not None:
            target_container.append(off_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "offset_code": offset_code,
                "links": links,
                "distance": offset_distance,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(off_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "offset_code": offset_code,
            "links": links,
            "distance": offset_distance,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_get_mark_point(
        cls,
        engine: FlowchartEngine,
        point_number: str,
        mark_name: str,
        point_codes_str: str = "",
        is_auxiliary: bool = False,
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo Activity GetMarkPointActivity hoặc GetAuxMarkPointActivity."""
        point_number = point_number.strip()
        mark_name = mark_name.strip()
        act_id = engine.next_activity_id()
        tag_name = "GetAuxMarkPointActivity" if is_auxiliary else "GetMarkPointActivity"

        mp_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"{point_number}({mark_name})",
            "Geometry": "[Geometry]",
            "MarkName": mark_name,
            "PointNumber": point_number,
            "ShowErrors": "True",
            "Side": "[Side]",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        codes_list = [
            c.strip().strip('"').strip("'")
            for c in point_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if not codes_list:
            mp_attrs["PointCodes"] = "{x:Null}"

        mp_el = etree.Element(engine.qn("asa2", tag_name), attrib=mp_attrs)

        if codes_list:
            codes_container = etree.SubElement(mp_el, engine.qn("asa2", f"{tag_name}.PointCodes"))
            scg_list = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(codes_list))),
                },
            )
            for c in codes_list:
                in_arg = etree.SubElement(
                    scg_list,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                in_arg.text = c

        if target_container is not None:
            target_container.append(mp_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "point_number": point_number,
                "mark_name": mark_name,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(mp_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "point_number": point_number,
            "mark_name": mark_name,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_shape(
        cls,
        engine: FlowchartEngine,
        shape_code: str = "",
        link_names: list[str] | None = None,
        shape_codes_str: str = "",
        parent_node_id: Optional[str] = None,
        shape_name: str = "",
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        actual_shape_code = (shape_code or shape_name).strip()
        links_list = [lk.strip() for lk in (link_names or []) if lk.strip()]
        links_csv = ",".join(links_list)
        act_id = engine.next_activity_id()

        shape_el = etree.Element(
            engine.qn("asa2", "CreateShape"),
            attrib={
                "ActivityId": act_id,
                "DisplayName": actual_shape_code,
                "Geometry": "[Geometry]",
                "Links": links_csv,
                "ShapeNumber": actual_shape_code,
                "ShowErrors": "True",
                "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
                "SubassemblyRunMode": "[SubassemblyRunMode]",
                engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
            },
        )

        comp_el = etree.SubElement(shape_el, engine.qn("asa2", "CreateShape.ComponentNames"))
        for lk in links_list:
            s_el = etree.SubElement(comp_el, engine.qn("x", "String"))
            s_el.text = lk

        sh_codes_list = [
            c.strip().strip('"').strip("'")
            for c in shape_codes_str.split(",")
            if c.strip().strip('"').strip("'")
        ]
        if sh_codes_list:
            codes_container = etree.SubElement(shape_el, engine.qn("asa2", "CreateShape.ShapeCodes"))
            scg_s = etree.SubElement(
                codes_container,
                engine.qn("scg", "List"),
                attrib={
                    engine.qn("x", "TypeArguments"): "InArgument(x:String)",
                    "Capacity": str(max(4, len(sh_codes_list))),
                },
            )
            for c in sh_codes_list:
                arg = etree.SubElement(
                    scg_s,
                    engine.qn("wf", "InArgument"),
                    attrib={engine.qn("x", "TypeArguments"): "x:String"},
                )
                arg.text = c

        vss = etree.SubElement(shape_el, engine.qn("sap", "WorkflowViewStateService.ViewState"))
        scg_d = etree.SubElement(
            vss,
            engine.qn("scg", "Dictionary"),
            attrib={engine.qn("x", "TypeArguments"): "x:String, x:Object"},
        )
        exp = etree.SubElement(scg_d, engine.qn("x", "Boolean"), attrib={engine.qn("x", "Key"): "IsExpanded"})
        exp.text = "True"

        if target_container is not None:
            target_container.append(shape_el)
            return {
                "reference_id": None,
                "linked_from_reference_id": None,
                "shape_code": actual_shape_code,
                "link_list": links_list,
                "shape_codes": shape_codes_str,
                "view_location": None,
            }

        ref_id = engine.next_reference_id()
        step_vs_id = engine.next_viewstate_idref("FlowStep")
        flow_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id,
            },
        )
        flow_step.append(shape_el)

        x_pos, y_pos = engine.compute_next_shape_location()
        linked_from = engine.attach_node_to_flowchart(
            new_node=flow_step,
            new_ref_id=ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.register_view_state(
            id_ref=step_vs_id,
            x=x_pos,
            y=y_pos,
            width=200.0,
            height=52.0,
            connector_from=(x_pos + 100.0, y_pos - 33.0),
            connector_to=(x_pos + 100.0, y_pos),
        )

        return {
            "reference_id": ref_id,
            "linked_from_reference_id": linked_from or "Flowchart.StartNode",
            "shape_code": actual_shape_code,
            "link_list": links_list,
            "shape_codes": shape_codes_str,
            "view_location": f"{x_pos},{y_pos}",
        }
