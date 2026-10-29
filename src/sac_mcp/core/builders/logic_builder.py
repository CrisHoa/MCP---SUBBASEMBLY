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

        # ErrorLevel map
        level_map = {
            ReportMessageType.INFORMATION: "Information",
            ReportMessageType.WARNING: "Warning",
            ReportMessageType.ERROR: "Error",
        }

        level_val = level_map.get(message_type, "Warning")

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
        # nhánh True trỏ sang khối ReportMessage
        # Vì msg_step chưa gắn vào cây XML của engine, lấy ID tuần tự cho Decision và ReportMessage:
        dec_ref_id = msg_ref_id
        dec_idx = int(dec_ref_id.replace("__ReferenceID", ""))
        msg_ref_id = f"__ReferenceID{dec_idx + 1}"
        msg_step.set(engine.qn("x", "Name"), msg_ref_id)

        dec_vs_id = engine.next_viewstate_idref("FlowDecision")

        decision_el = etree.Element(
            engine.qn("wf", "FlowDecision"),
            attrib={
                engine.qn("x", "Name"): dec_ref_id,
                "Condition": condition_expr.strip(),
                "DisplayName": f"If ({condition_expr.strip()})",
                engine.qn("sap2010", "WorkflowViewState.IdRef"): dec_vs_id,
            },
        )
        true_branch = etree.SubElement(decision_el, engine.qn("wf", "FlowDecision.True"))
        xref_true = etree.SubElement(true_branch, engine.qn("x", "Reference"))
        xref_true.text = msg_ref_id

        # Gắn FlowDecision vào luồng chính và thêm msg_step vào Flowchart
        linked_from = engine.attach_node_to_flowchart(
            new_node=decision_el,
            new_ref_id=dec_ref_id,
            parent_ref_id=parent_node_id,
        )
        engine.get_flowchart_element().append(msg_step)

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
