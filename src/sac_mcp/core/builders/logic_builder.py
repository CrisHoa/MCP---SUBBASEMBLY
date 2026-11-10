"""
Builder chuyên trách thêm khối Report Message và biểu thức điều kiện (FlowDecision)
vào Flowchart.xaml của Subassembly Composer.
"""

from __future__ import annotations

import re
from typing import List, Optional
from lxml import etree

from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import ReportMessageType

# Kiểu biến nội bộ (InternalVariableDefine.VariableType) mà SAC GUI ghi ra -> x:TypeArguments.
# Đối chiếu các gói .pkt mẫu của Autodesk (C3D 2024-2027): chỉ gặp Double / Integer / String / Yes\No.
SAC_VARIABLE_TYPES = {
    "Double": ("Double", "x:Double"),
    "Integer": ("Integer", "x:Int32"),
    "Int32": ("Integer", "x:Int32"),
    "String": ("String", "x:String"),
    "YesNo": ("Yes\\No", "asw:EnumType"),
    "Yes\\No": ("Yes\\No", "asw:EnumType"),
}

# Kiểu dùng cho SetVariableValue / SetOutputParameterValue (thêm Boolean, Slope, Grade cho Output Parameter).
CLR_TYPE_MAP = {
    "Double": "x:Double",
    "Integer": "x:Int32",
    "Int32": "x:Int32",
    "String": "x:String",
    "Boolean": "x:Boolean",
    "YesNo": "asw:EnumType",
    "Yes\\No": "asw:EnumType",
    "Slope": "asw:Slope",
    "Grade": "asw:Grade",
}


# Từ khóa dành riêng của VB.NET (không phân biệt hoa thường) - không dùng làm tên biến.
VB_RESERVED_WORDS = frozenset(
    w.lower()
    for w in """
    AddHandler AddressOf Alias And AndAlso As Boolean ByRef Byte ByVal Call Case Catch CBool CByte CChar
    CDate CDbl CDec Char CInt Class CLng CObj Const Continue CSByte CShort CSng CStr CType CUInt CULng
    CUShort Date Decimal Declare Default Delegate Dim DirectCast Do Double Each Else ElseIf End EndIf
    Enum Erase Error Event Exit False Finally For Friend Function Get GetType GetXMLNamespace Global
    GoSub GoTo Handles If Implements Imports In Inherits Integer Interface Is IsNot Let Lib Like Long
    Loop Me Mod Module MustInherit MustOverride MyBase MyClass Namespace Narrowing New Next Not Nothing
    NotInheritable NotOverridable Object Of On Operator Option Optional Or OrElse Out Overloads
    Overridable Overrides ParamArray Partial Private Property Protected Public RaiseEvent ReadOnly
    ReDim REM RemoveHandler Resume Return SByte Select Set Shadows Shared Short Single Static Step Stop
    String Structure Sub SyncLock Then Throw To True Try TryCast TypeOf UInteger ULong UShort Using
    Variant Wend When While Widening With WithEvents WriteOnly Xor
    """.split()
)


def check_identifier(name: str, kind: str = "biến") -> str:
    """Tên định danh VB hợp lệ: bắt đầu bằng chữ cái, chỉ chữ/số/'_', không trùng từ khóa VB."""
    n = (name or "").strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", n):
        raise ValueError(f"Tên {kind} '{name}' không hợp lệ: phải bắt đầu bằng chữ cái, chỉ gồm chữ, số và '_'.")
    if n.lower() in VB_RESERVED_WORDS:
        raise ValueError(f"Tên {kind} '{n}' trùng từ khóa VB.NET dành riêng. Hãy đặt tên khác (VD: 'Var_{n}').")
    return n


def _bracket(expr: str) -> str:
    """Bọc biểu thức VB trong [...] như SAC GUI (kể cả hằng số)."""
    s = str(expr).strip()
    if not s:
        raise ValueError("Biểu thức giá trị không được để trống.")
    return s if (s.startswith("[") and s.endswith("]")) else f"[{s}]"


def lookup_declared_type(engine: FlowchartEngine, name: str) -> Optional[str]:
    """
    Tìm x:TypeArguments đã khai báo cho tên `name`:
      - biến nội bộ trong <Flowchart.Variables>/<Variable Name=...>
      - Parameter trong <x:Members>/<x:Property Name=... Type="OutArgument(x:Double)">
    Trả về None nếu chưa khai báo.
    """
    flowchart = engine.get_flowchart_element()
    for v in flowchart.xpath("./*[local-name()='Flowchart.Variables']/*[local-name()='Variable' and @Name=$n]", n=name):
        t = v.get(engine.qn("x", "TypeArguments"))
        if t:
            return t
    for p in engine.root.xpath("./*[local-name()='Members']/*[local-name()='Property' and @Name=$n]", n=name):
        t = p.get("Type") or ""
        if "(" in t and t.endswith(")"):
            return t[t.index("(") + 1 : -1]
    return None


def _resolve_clr_type(engine: FlowchartEngine, name: str, type_name: Optional[str]) -> str:
    """Kiểu tường minh nếu có, ngược lại suy ra từ khai báo; mặc định x:Double."""
    if type_name:
        key = type_name.strip()
        if key not in CLR_TYPE_MAP:
            raise ValueError(f"Kiểu '{type_name}' không hỗ trợ. Chọn một trong: {', '.join(CLR_TYPE_MAP)}.")
        return CLR_TYPE_MAP[key]
    return lookup_declared_type(engine, name) or "x:Double"


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
        """
        Tạo Activity InternalVariableDefine chuẩn Native SAC.
        DefaultValue luôn được bọc [...] như SAC GUI (biểu thức trần như 'P1.X*2' sẽ bị
        WF4 hiểu là hằng chuỗi và báo 'Input string was not in a correct format').
        """
        variable_name = check_identifier(variable_name, "biến")
        vt_key = str(variable_type).strip()
        if vt_key not in SAC_VARIABLE_TYPES:
            raise ValueError(
                f"VariableType '{variable_type}' không hợp lệ. SAC chỉ hỗ trợ: Double, Integer, String, YesNo."
            )
        sac_type, clr_type = SAC_VARIABLE_TYPES[vt_key]
        act_id = engine.next_activity_id()

        # Đăng ký biến vào <Flowchart.Variables>
        engine.add_flowchart_variable(name=variable_name, type_arguments=clr_type)

        var_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"{variable_name} <{sac_type}>",
            "OldVariableName": "",
            "ShowErrors": "True",
            "SubassemblyErrorCenter": "[SubassemblyErrorCenter]",
            "SubassemblyRunMode": "[SubassemblyRunMode]",
            "VariableName": variable_name,
            "VariableType": sac_type,
            engine.qn("sap", "VirtualizedContainerService.HintSize"): "200,22.4",
        }

        var_el = etree.Element(engine.qn("asa2", "InternalVariableDefine"), attrib=var_attrs)

        def_val = etree.SubElement(var_el, engine.qn("asa2", "InternalVariableDefine.DefaultValue"))
        in_arg = etree.SubElement(
            def_val,
            engine.qn("wf", "InArgument"),
            attrib={engine.qn("x", "TypeArguments"): clr_type},
        )
        in_arg.text = _bracket(default_value_expr)

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
                "variable_type": sac_type,
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
            "variable_type": sac_type,
            "clr_type": clr_type,
            "default_value": in_arg.text,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_set_variable_value(
        cls,
        engine: FlowchartEngine,
        variable_name: str,
        value_expr: str,
        variable_type: Optional[str] = "Double",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """
        Tạo Activity SetVariableValue chuẩn Native SAC.
        variable_type=None: tự suy ra kiểu từ khai báo <Flowchart.Variables> (mặc định Double).
        """
        variable_name = variable_name.strip()
        clr_type = _resolve_clr_type(engine, variable_name, variable_type)
        act_id = engine.next_activity_id()

        set_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"{variable_name} = {str(value_expr).strip().strip('[]')}"[:60],
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
        in_arg.text = _bracket(value_expr)

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
            "clr_type": clr_type,
            "view_location": f"{x_pos},{y_pos}",
        }

    @classmethod
    def add_set_output_parameter(
        cls,
        engine: FlowchartEngine,
        parameter_name: str,
        value_expr: str,
        parameter_type: Optional[str] = "Double",
        parent_node_id: Optional[str] = None,
        target_container: Optional[etree._Element] = None,
    ) -> dict:
        """
        Tạo Activity SetOutputParameterValue chuẩn Native SAC.
        Lưu ý: tên đối số trong DLL gốc là 'OutputParammeter' (lỗi chính tả của Autodesk) - giữ nguyên.
        parameter_type=None: tự suy ra kiểu từ <x:Property Type="OutArgument(...)"> (mặc định Double).
        """
        parameter_name = parameter_name.strip()
        clr_type = _resolve_clr_type(engine, parameter_name, parameter_type)
        act_id = engine.next_activity_id()

        out_attrs = {
            "ActivityId": act_id,
            "DisplayName": f"{parameter_name} = {str(value_expr).strip().strip('[]')}"[:60],
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
        in_arg.text = _bracket(value_expr)

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
            "clr_type": clr_type,
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
        x: Optional[float] = None,
        y: Optional[float] = None,
        auto_attach: bool = True,
    ) -> dict:
        """
        Tạo khối phân nhánh điều kiện FlowDecision trong Flowchart.
        x/y = None: tự đặt ngay dưới khối thấp nhất hiện có (không đè lên nhau trong SAC GUI).
        Kết quả có khóa 'element' (lxml) chỉ dùng nội bộ - không serialize ra JSON.
        """
        if x is None or y is None:
            nx, ny = engine.compute_next_shape_location()
            x = nx + 60.0 if x is None else x
            y = ny if y is None else y
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
            "view_location": f"{x},{y}",
            "element": dec_el,
        }
