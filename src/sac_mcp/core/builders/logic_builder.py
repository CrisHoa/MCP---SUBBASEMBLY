"""
Builder chuyên trách thêm khối Report Message và biểu thức điều kiện (FlowDecision)
vào Flowchart.xaml của Subassembly Composer.
"""

from __future__ import annotations

from typing import List, Optional
from lxml import etree

from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import ReportMessageType


class LogicBuilder:
    """Tạo khối <asa2:CustomErrorReportActivity> kèm hoặc không kèm khối điều kiện <FlowDecision>."""

    @classmethod
    def add_report_message(
        cls,
        engine: FlowchartEngine,
        message_expr: str,
        message_type: ReportMessageType = ReportMessageType.WARNING,
        condition_expr: Optional[str] = None,
        parent_node_id: Optional[str] = None,
    ) -> dict:
        created_refs: List[str] = []
        x_pos, y_pos = engine.compute_next_shape_location()

        # 1. Khởi tạo FlowStep chứa <asa2:CustomErrorReportActivity>
        msg_ref_id = engine.next_reference_id()
        msg_step_vs_id = engine.next_viewstate_idref("FlowStep")
        act_id = engine.next_activity_id()

        # ErrorLevel map (Autodesk Native ErrorLevel: Informational, Warning, Error)
        level_map = {
            ReportMessageType.INFORMATIONAL: "Informational",
            ReportMessageType.WARNING: "Warning",
            ReportMessageType.ERROR: "Error",
        }

        level_val = level_map.get(message_type, "Informational")

        msg_step = etree.Element(
            engine.qn("wf", "FlowStep"),
            attrib={
                engine.qn("x", "Name"): msg_ref_id,
                engine.qn("sap2010", "WorkflowViewState.IdRef"): msg_step_vs_id,
            },
        )
        msg_activity = etree.SubElement(
            msg_step,
            engine.qn("asa2", "CustomErrorReportActivity"),
            attrib={
                "ActivityId": act_id,
                "DisplayName": f"Report {level_val}",
                "ErrorLevel": level_val,
                "ShowErrors": "True",
                "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
                "SubassemblyRunMode": "[SubassemblyRunMode]",
                engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
            },
        )
        msg_in_arg = etree.SubElement(
            msg_activity,
            engine.qn("asa2", "CustomErrorReportActivity.Message"),
        )
        msg_text_el = etree.SubElement(
            msg_in_arg,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): "x:String"},
        )
        raw_msg = message_expr.strip()
        msg_text_el.text = raw_msg if raw_msg.startswith("[") else f'["{raw_msg.strip(chr(34))}"]'


        # Trường hợp 1: Không có biểu thức điều kiện -> Nối thẳng vào Flowchart
        if not condition_expr or not condition_expr.strip():
            linked_from = engine.attach_node_to_flowchart(
                new_node=msg_step,
                new_ref_id=msg_ref_id,
                parent_ref_id=parent_node_id,
            )
            engine.register_view_state(
                id_ref=msg_step_vs_id,
                x=x_pos,
                y=y_pos,
                width=200.0,
                height=52.0,
            )
            created_refs.append(msg_ref_id)
            return {
                "created_reference_ids": created_refs,
                "has_condition": False,
                "report_node_id": msg_ref_id,
                "linked_from": linked_from or "Flowchart.StartNode",
                "message_type": message_type.value,
                "message_expr": message_expr,
                "view_location": f"{x_pos},{y_pos}",
            }

        # Trường hợp 2: Có biểu thức điều kiện (condition_expr) -> Tạo <FlowDecision> trước,
        # nhánh True trỏ sang khối ReportMessage. Luồng phía sau được nối tiếp vào CẢ HAI:
        #   - FlowDecision.False (điều kiện sai -> đi tiếp bình thường)
        #   - ReportMessage.Next (điều kiện đúng -> báo lỗi rồi đi tiếp)
        flowchart = engine.get_flowchart_element()
        dec_ref_id = msg_ref_id
        dec_vs_id = engine.next_viewstate_idref("FlowDecision")
        cond = condition_expr.strip()
        cond_attr = cond if cond.startswith("[") else f"[{cond}]"

        decision_el = etree.Element(
            engine.qn("wf", "FlowDecision"),
            attrib={
                engine.qn("x", "Name"): dec_ref_id,
                "Condition": cond_attr,
                "DisplayName": f"If ({cond})",
                engine.qn("sap2010", "WorkflowViewState.IdRef"): dec_vs_id,
            },
        )
        flowchart.append(decision_el)

        msg_ref_id = engine.next_reference_id()
        msg_step.set(engine.qn("x", "Name"), msg_ref_id)
        msg_step.set(engine.qn("sap2010", "WorkflowViewState.IdRef"), engine.next_viewstate_idref("FlowStep"))
        msg_step_vs_id = msg_step.get(engine.qn("sap2010", "WorkflowViewState.IdRef"))
        flowchart.append(msg_step)
        engine.set_slot_reference(decision_el, "True", msg_ref_id)

        linked_from = engine.attach_node_to_flowchart(
            new_node=decision_el,
            new_ref_id=dec_ref_id,
            parent_ref_id=parent_node_id,
            exits=[(decision_el, "False"), (msg_step, "Next")],
        )

        # Đặt tọa độ cho Decision ở luồng chính (X, Y) và ReportMessage lệch sang nhánh phải (X + 260, Y)
        engine.register_view_state(
            id_ref=dec_vs_id,
            x=x_pos + 60.0,
            y=y_pos,
            width=79.0,
            height=87.0,
        )
        engine.register_view_state(
            id_ref=msg_step_vs_id,
            x=x_pos + 260.0,
            y=y_pos + 15.0,
            width=200.0,
            height=52.0,
        )

        created_refs.extend([dec_ref_id, msg_ref_id])
        return {
            "created_reference_ids": created_refs,
            "has_condition": True,
            "decision_node_id": dec_ref_id,
            "condition_expr": condition_expr.strip(),
            "report_node_id": msg_ref_id,
            "linked_from": linked_from or "Flowchart.StartNode",
            "message_type": message_type.value,
            "message_expr": message_expr,
            "decision_location": f"{x_pos + 60.0},{y_pos}",
            "report_location": f"{x_pos + 260.0},{y_pos + 15.0}",
        }

    @classmethod
    def add_define_variable(
        cls,
        engine: FlowchartEngine,
        variable_name: str,
        variable_type: str = "Double",
        default_value_expr: str = "0.0",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo Activity InternalVariableDefine chuẩn Native SAC."""
        variable_name = variable_name.strip()
        act_id = engine.next_activity_id()

        # Ánh xạ kiểu biến CLR
        type_map = {
            "Double": "x:Double",
            "Int32": "x:Int32",
            "Integer": "x:Int32",
            "String": "x:String",
            "Boolean": "x:Boolean",
        }
        clr_type = type_map.get(variable_type, "x:Double")

        # Đăng ký biến vào <Flowchart.Variables>
        engine.add_flowchart_variable(name=variable_name, type_arguments=clr_type)

        var_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"Define {variable_name}",
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            "VariableName": variable_name,
            "VariableType": variable_type,
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        var_el = etree.Element(engine.qn("asa2", "InternalVariableDefine"), attrib=var_attrs)

        def_val = etree.SubElement(var_el, engine.qn("asa2", "InternalVariableDefine.DefaultValue"))
        in_arg = etree.SubElement(
            def_val,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        in_arg.text = str(default_value_expr).strip()

        # Variable OutArgument [VariableName]
        var_slot = etree.SubElement(var_el, engine.qn("asa2", "InternalVariableDefine.Variable"))
        var_out_arg = etree.SubElement(
            var_slot,
            engine.qn("wf", "OutArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        var_out_arg.text = f"[{variable_name}]"

        if target_container is not None:
            target_container.append(var_el)
            return {
                "reference_id": None,
                "variable_name": variable_name,
                "variable_type": variable_type,
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
        flow_step.append(var_el)

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
            "variable_name": variable_name,
            "variable_type": variable_type,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_set_variable_value(
        cls,
        engine: FlowchartEngine,
        variable_name: str,
        value_expr: str,
        variable_type: str = "Double",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo Activity SetVariableValue chuẩn Native SAC."""
        variable_name = variable_name.strip()
        act_id = engine.next_activity_id()

        type_map = {
            "Double": "x:Double",
            "Int32": "x:Int32",
            "Integer": "x:Int32",
            "String": "x:String",
            "Boolean": "x:Boolean",
        }
        clr_type = type_map.get(variable_type, "x:Double")

        set_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"Set {variable_name}",
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        set_el = etree.Element(engine.qn("asa2", "SetVariableValue"), attrib=set_attrs)

        vn_el = etree.SubElement(set_el, engine.qn("asa2", "SetVariableValue.VariableName"))
        out_arg = etree.SubElement(
            vn_el,
            engine.qn("wf", "OutArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        out_arg.text = f"[{variable_name}]"

        vv_el = etree.SubElement(set_el, engine.qn("asa2", "SetVariableValue.VariableValue"))
        in_arg = etree.SubElement(
            vv_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        s_val = str(value_expr).strip()
        in_arg.text = s_val if (s_val.startswith("[") and s_val.endswith("]")) else f"[{s_val}]"

        if target_container is not None:
            target_container.append(set_el)
            return {
                "reference_id": None,
                "variable_name": variable_name,
                "value_expr": value_expr,
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
        flow_step.append(set_el)

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
            "variable_name": variable_name,
            "value_expr": value_expr,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_set_output_parameter(
        cls,
        engine: FlowchartEngine,
        parameter_name: str,
        value_expr: str,
        parameter_type: str = "Double",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo Activity SetOutputParameterValue chuẩn Native SAC."""
        parameter_name = parameter_name.strip()
        act_id = engine.next_activity_id()

        type_map = {
            "Double": "x:Double",
            "Int32": "x:Int32",
            "Integer": "x:Int32",
            "String": "x:String",
            "Boolean": "x:Boolean",
        }
        clr_type = type_map.get(parameter_type, "x:Double")

        out_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"Out {parameter_name}",
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        out_el = etree.Element(engine.qn("asa2", "SetOutputParameterValue"), attrib=out_attrs)

        op_el = etree.SubElement(out_el, engine.qn("asa2", "SetOutputParameterValue.OutputParammeter"))
        out_arg = etree.SubElement(
            op_el,
            engine.qn("wf", "OutArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        out_arg.text = f"[{parameter_name}]"

        val_el = etree.SubElement(out_el, engine.qn("asa2", "SetOutputParameterValue.Value"))
        in_arg = etree.SubElement(
            val_el,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        s_val = str(value_expr).strip()
        in_arg.text = s_val if (s_val.startswith("[") and s_val.endswith("]")) else f"[{s_val}]"

        if target_container is not None:
            target_container.append(out_el)
            return {
                "reference_id": None,
                "parameter_name": parameter_name,
                "value_expr": value_expr,
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
        flow_step.append(out_el)

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
            "parameter_name": parameter_name,
            "value_expr": value_expr,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_set_mark_point(
        cls,
        engine: FlowchartEngine,
        point_number: str,
        mark_name: str,
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """Tạo Activity SetMarkPointActivity chuẩn Native SAC."""
        point_number = point_number.strip()
        mark_name = mark_name.strip()
        act_id = engine.next_activity_id()

        smp_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"Mark {point_number}->{mark_name}",
            "Geometry": "[Geometry]",
            "MarkName": mark_name,
            "PointNumber": point_number,
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        smp_el = etree.Element(engine.qn("asa2", "SetMarkPointActivity"), attrib=smp_attrs)

        if target_container is not None:
            target_container.append(smp_el)
            return {
                "reference_id": None,
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
        flow_step.append(smp_el)

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
    def add_flow_decision(
        cls,
        engine: FlowchartEngine,
        condition_expr: str,
        display_name: str = "",
        true_ref_id: Optional[str] = None,
        false_ref_id: Optional[str] = None,
        parent_node_id: Optional[str] = None,
        x: float = 260.0,
        y: float = 100.0,
        auto_attach: bool = True,
    ) -> dict:
        """Tạo khối phân nhánh điều kiện FlowDecision trong Flowchart."""
        dec_el, ref_id = engine.create_flow_decision(
            condition_expr=condition_expr,
            display_name=display_name,
            true_ref_id=true_ref_id,
            false_ref_id=false_ref_id,
            x=x,
            y=y,
            parent_ref_id=parent_node_id,
            auto_attach=auto_attach,
        )
        return {
            "decision_node_id": ref_id,
            "condition": condition_expr,
            "display_name": display_name,
            "true_branch": true_ref_id,
            "false_branch": false_ref_id,
            "element": dec_el,
        }
