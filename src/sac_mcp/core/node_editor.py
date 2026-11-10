"""
Chỉnh sửa trực tiếp các node đã có trong Flowchart của Subassembly Composer:

  - remove_node(engine, node_id, keep_branch=None): xoá một FlowStep / FlowDecision và NỐI LẠI luồng
    (mọi nhánh đang trỏ vào node bị xoá sẽ trỏ sang phần luồng phía sau nó).
  - update_node(engine, node_id, attributes, arguments): sửa thuộc tính của activity trong FlowStep
    (hoặc Condition / DisplayName của FlowDecision) và giá trị các InArgument theo x:Key.

Hỗ trợ cả 2 kiểu lưu Flowchart: node lồng inline (FlowStep.Next chứa FlowStep - kiểu SAC GUI lưu)
và node phẳng nối bằng <x:Reference> (kiểu builder sinh ra).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from lxml import etree

from sac_mcp.core.builders.geom_builder import format_arg_expr
from sac_mcp.core.semantic_checks import load_activity_catalog
from sac_mcp.core.xaml_engine import FLOW_NODE_TAGS, SLOT_PROPS, FlowchartEngine, _local

X_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
X_NAME = f"{{{X_NS}}}Name"
X_KEY = f"{{{X_NS}}}Key"
X_TYPEARGS = f"{{{X_NS}}}TypeArguments"
LIB_NS_MARK = "Autodesk.SubassemblyComposer.ActivityLibrary"

# Thuộc tính định nghĩa tên Point / Link (để cảnh báo khi xoá node đang được tham chiếu)
_DEF_ATTRS = ("PointNumber", "StartPointName", "EndPointName", "LinkNumber", "LoopNumber", "ShapeNumber", "OffsetNumber")
_REF_ATTRS = ("FromPoint", "StartPoint", "EndPoint", "FirstLink", "SecondLink")
_REF_LIST_ATTRS = ("Links",)
_REF_ARG_KEYS = ("FirstLink1", "SecondLink1", "DestPoint", "CenterPoint", "ArcPoint2")

# Đối số dạng chuỗi tên hình học (không bọc [..])
_STRING_ARG_KEYS = {"FirstLink1", "SecondLink1", "DestPoint", "CenterPoint", "ArcPoint2"}

# Thuộc tính là TÊN / mã / giá trị enum (ghi nguyên văn, không bọc [..])
_NAME_ATTRS = {
    "PointNumber", "LinkNumber", "ShapeNumber", "LoopNumber", "OffsetNumber", "FromPoint", "StartPoint",
    "EndPoint", "FirstLink", "SecondLink", "Links", "CenterPoint", "ArcPoint2", "MarkName", "DisplayName",
    "CreationType", "Positioning", "RoundBy", "ErrorLevel", "VariableName", "VariableType", "AutoLinkGeometryName",
    "Id",
}
# Thuộc tính định nghĩa tên Point / Link: đổi tên thì cập nhật tham chiếu
_RENAMEABLE_ATTRS = {
    "PointNumber", "LinkNumber", "LoopNumber", "OffsetNumber", "AutoLinkGeometryName",
    "StartPointName", "EndPointName",
}
# Đối số bắt buộc theo CreationType của CreateCurve / CreateAuxCurve
_CURVE_ARGS = {"ArcGeneral": "CenterPoint", "Arc3Points": "ArcPoint2", "ParabolaGeneral": "MidOrdinate"}


# ============================================================================
# Tiện ích chung
# ============================================================================

def get_node(engine: FlowchartEngine, node_id: str) -> etree._Element:
    """Tìm FlowStep / FlowDecision / FlowSwitch theo x:Name; raise ValueError kèm gợi ý nếu không có."""
    index = engine._node_index()
    node = index.get((node_id or "").strip())
    if node is None:
        sample = ", ".join(list(index)[:12])
        raise ValueError(
            f"Không tìm thấy node '{node_id}' trong Flowchart. Các node hiện có: {sample}"
            + (" ..." if len(index) > 12 else "")
            + ". Dùng inspect_pkt để xem danh sách reference_id."
        )
    return node


def get_activity(node: etree._Element) -> Optional[etree._Element]:
    """Activity chính bên trong một FlowStep (bỏ qua property element 'X.Y' và ViewState)."""
    for child in node.iterchildren(etree.Element):
        ln = _local(child)
        if "." in ln or ln in FLOW_NODE_TAGS:
            continue
        return child
    return None


def _is_null(val: Optional[str]) -> bool:
    return not val or val.strip() in ("{x:Null}", "")


def _slot_holder(node: etree._Element, slot: str) -> Optional[etree._Element]:
    prop_name = f"{_local(node)}.{slot}"
    for prop in node.iterchildren(etree.Element):
        if _local(prop) == prop_name:
            return prop
    return None


def _clear_slot(node: etree._Element, slot: str) -> None:
    """Xoá hẳn nhánh `slot` của node (để trống)."""
    if slot in node.attrib:
        del node.attrib[slot]
    holder = _slot_holder(node, slot)
    if holder is not None:
        node.remove(holder)


def _flowchart_ref_entries(engine: FlowchartEngine, name: str) -> List[etree._Element]:
    """Các <x:Reference>name</x:Reference> nằm TRỰC TIẾP trong <Flowchart> (danh sách Flowchart.Nodes)."""
    fc = engine.get_flowchart_element()
    return [
        c
        for c in fc.iterchildren(etree.Element)
        if _local(c) == "Reference" and etree.QName(c).namespace == X_NS and (c.text or "").strip() == name
    ]


def _move_to_flowchart_level(engine: FlowchartEngine, node: etree._Element) -> str:
    """
    Đưa một node đang lồng inline ra cấp <Flowchart> để tham chiếu được bằng x:Reference.
    Nếu Flowchart.Nodes đã có <x:Reference> tới node này thì thay đúng vị trí đó (tránh trùng lặp).
    """
    name = node.get(X_NAME)
    if not name:
        name = engine.next_reference_id()
        node.set(X_NAME, name)
    fc = engine.get_flowchart_element()
    if node.getparent() is fc:
        return name
    entries = _flowchart_ref_entries(engine, name)
    if entries:
        entries[0].addprevious(node)  # addprevious tự tách node khỏi vị trí cũ
        for e in entries:
            fc.remove(e)
    else:
        fc.append(node)
    return name


def _remove_view_state(engine: FlowchartEngine, node: etree._Element) -> List[str]:
    """Xoá <sap2010:ViewStateData> ứng với node và các activity bên trong (theo WorkflowViewState.IdRef)."""
    idref_attr = engine.qn("sap2010", "WorkflowViewState.IdRef")
    ids: Set[str] = set()
    for el in _own_elements(node):  # Không đụng tới các FlowNode con (chúng được giữ lại)
        v = el.get(idref_attr)
        if v:
            ids.add(v)
    removed: List[str] = []
    vsm = engine.get_view_state_manager()
    if vsm is None or not ids:
        return removed
    for vsd in list(vsm.iterchildren(etree.Element)):
        if _local(vsd) == "ViewStateData" and vsd.get("Id") in ids:
            vsm.remove(vsd)
            removed.append(vsd.get("Id"))
    return removed


def _inline_children(node: etree._Element) -> List[etree._Element]:
    """Các FlowNode lồng inline TRỰC TIẾP trong các nhánh của node (Next / True / False / Default / Case)."""
    result: List[etree._Element] = []
    for prop in node.iterchildren(etree.Element):
        ln = _local(prop)
        if ln in FLOW_NODE_TAGS:  # Case của FlowSwitch lồng trực tiếp
            result.append(prop)
        elif "." in ln:
            for c in prop.iterchildren(etree.Element):
                if _local(c) in FLOW_NODE_TAGS:
                    result.append(c)
    return result


def _own_elements(node: etree._Element) -> List[etree._Element]:
    """Mọi phần tử thuộc riêng node (KHÔNG đi vào các FlowNode con lồng inline)."""
    out: List[etree._Element] = [node]
    stack = list(node.iterchildren(etree.Element))
    while stack:
        el = stack.pop()
        if _local(el) in FLOW_NODE_TAGS:
            continue
        out.append(el)
        stack.extend(el.iterchildren(etree.Element))
    return out


def _defined_names(node: etree._Element) -> Set[str]:
    names: Set[str] = set()
    for el in _own_elements(node):
        if _local(el) == "SetMarkPointActivity":
            continue  # PointNumber ở đây là THAM CHIẾU tới Point có sẵn, không phải định nghĩa
        for a in _DEF_ATTRS:
            if not _is_null(el.get(a)):
                names.add(el.get(a).strip())
        if (el.get("AutoLink") or "").lower() == "true" and not _is_null(el.get("AutoLinkGeometryName")):
            names.add(el.get("AutoLinkGeometryName").strip())
    return names


def _all_defined_names(engine: FlowchartEngine) -> Set[str]:
    names: Set[str] = set()
    for node in engine._node_index().values():
        names |= _defined_names(node)
    return names


def _geometry_users(engine: FlowchartEngine, names: Set[str]) -> List[str]:
    """Liệt kê activity còn lại đang tham chiếu tới các tên Point/Link trong `names`."""
    if not names:
        return []
    found: List[str] = []
    expr_res = {n: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(n)}\.") for n in names}
    fc = engine.get_flowchart_element()
    for el in fc.iter(etree.Element):
        ns = etree.QName(el).namespace or ""
        ln = _local(el)
        if LIB_NS_MARK not in ns or "." in ln:
            continue
        label = el.get("DisplayName") or ln
        hits: List[str] = []
        for a in _REF_ATTRS:
            v = (el.get(a) or "").strip()
            if v in names or v.split(".", 1)[0] in names:
                hits.append(f"{a}={v}")
        for a in _REF_LIST_ATTRS:
            for item in (s.strip() for s in (el.get(a) or "").split(",")):
                if item in names:
                    hits.append(f"{a}∋{item}")
        if ln == "SetMarkPointActivity" and (el.get("PointNumber") or "").strip() in names:
            hits.append(f"PointNumber={el.get('PointNumber')}")
        for arg in el.iter(etree.Element):
            if _local(arg) == "InArgument" and arg.get(X_KEY) in _REF_ARG_KEYS:
                v = (arg.text or "").strip()
                if v in names:
                    hits.append(f"{arg.get(X_KEY)}={v}")
        # Biểu thức VB dạng P2.Y / L1.Slope trong thuộc tính hoặc đối số
        texts = [v for v in el.attrib.values() if v.startswith("[")]
        texts += [(t.text or "") for t in el.iter(etree.Element) if (t.text or "").strip().startswith("[")]
        for n, rx in expr_res.items():
            if any(rx.search(t) for t in texts):
                hits.append(f"biểu thức dùng {n}.")
        if hits:
            found.append(f"{ln} '{label}' ({'; '.join(sorted(set(hits)))})")
    return found


# ============================================================================
# remove_node
# ============================================================================

def remove_node(engine: FlowchartEngine, node_id: str, keep_branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Xoá một FlowStep / FlowDecision khỏi Flowchart và nối lại luồng.

    - FlowStep: mọi nhánh đang trỏ vào node sẽ trỏ sang Next của nó.
    - FlowDecision: chỉ xoá được khi 2 nhánh cùng trống hoặc cùng trỏ một node; nếu không phải truyền
      keep_branch='True' / 'False' để giữ lại nhánh đó (nhánh còn lại bị tách khỏi luồng, có cảnh báo).
    - Node con đang lồng inline được đưa ra cấp Flowchart và tham chiếu bằng x:Name.
    - Xoá mục <sap2010:ViewStateData> tương ứng (nếu có).
    Trả về dict mô tả những gì đã nối lại.
    """
    node = get_node(engine, node_id)
    node_id = node.get(X_NAME)
    kind = _local(node)
    index = engine._node_index()
    warnings: List[str] = []

    if kind == "FlowSwitch":
        raise ValueError(f"Chưa hỗ trợ xoá FlowSwitch ('{node_id}'). Hãy sửa trong Subassembly Composer.")

    if kind == "FlowStep":
        if keep_branch:
            raise ValueError(f"Node '{node_id}' là FlowStep, không dùng keep_branch (chỉ dành cho FlowDecision).")
        cont = engine.get_slot_target(node, "Next", index)
        dropped: List[etree._Element] = []
    else:  # FlowDecision
        t = engine.get_slot_target(node, "True", index)
        f = engine.get_slot_target(node, "False", index)
        if keep_branch is not None:
            kb = str(keep_branch).strip().capitalize()
            if kb not in ("True", "False"):
                raise ValueError(f"keep_branch phải là 'True' hoặc 'False' (nhận '{keep_branch}').")
            cont, other = (t, f) if kb == "True" else (f, t)
            dropped = [other] if other is not None and other is not cont and (
                cont is None or other.get(X_NAME) != cont.get(X_NAME)
            ) else []
        else:
            same = (t is None and f is None) or (
                t is not None and f is not None and t.get(X_NAME) and t.get(X_NAME) == f.get(X_NAME)
            )
            if not same:
                raise ValueError(
                    f"FlowDecision '{node_id}' có 2 nhánh khác nhau (True -> "
                    f"{t.get(X_NAME) if t is not None else 'trống'}, False -> "
                    f"{f.get(X_NAME) if f is not None else 'trống'}). "
                    "Truyền keep_branch='True' hoặc 'False' để chọn nhánh được giữ lại."
                )
            cont = t
            dropped = []

    if cont is not None and cont.get(X_NAME) == node_id:
        cont = None  # tự trỏ vào chính nó

    # 1. Đưa mọi node con lồng inline ra cấp Flowchart (để không bị xoá theo node cha)
    moved: List[str] = []
    for child in _inline_children(node):
        moved.append(_move_to_flowchart_level(engine, child))
    cont_name: Optional[str] = None
    if cont is not None:
        # Node nối tiếp nằm ở chỗ khác (không lồng trong node bị xoá): chỉ cần có x:Name để tham chiếu
        cont_name = cont.get(X_NAME)
        if not cont_name:
            cont_name = engine.next_reference_id()
            cont.set(X_NAME, cont_name)

    # Tên do node định nghĩa (để cảnh báo tham chiếu treo)
    defined = _defined_names(node)

    # 2. Nối lại mọi nhánh đang trỏ vào node
    rewired: List[str] = []
    index = engine._node_index()
    for other_name, other in index.items():
        if other_name == node_id:
            continue
        okind = _local(other)
        for slot in SLOT_PROPS.get(okind, ()):
            tgt = engine.get_slot_target(other, slot, index)
            if tgt is not None and tgt.get(X_NAME) == node_id:
                if cont_name:
                    engine.set_slot_reference(other, slot, cont_name)
                else:
                    _clear_slot(other, slot)
                rewired.append(other_name if slot == "Next" else f"{other_name}:{slot}")
        if okind == "FlowSwitch":
            for child in list(other.iterchildren(etree.Element)):
                ln = _local(child)
                is_ref = ln == "Reference" and (child.text or "").strip() == node_id
                is_inline = ln in FLOW_NODE_TAGS and child.get(X_NAME) == node_id
                if not (is_ref or is_inline):
                    continue
                case_key = child.get(X_KEY)
                if cont_name:
                    new_ref = etree.Element(engine.qn("x", "Reference"))
                    new_ref.text = cont_name
                    if case_key is not None:
                        new_ref.set(X_KEY, case_key)
                    child.addprevious(new_ref)
                other.remove(child)
                rewired.append(f"{other_name}:Case[{case_key}]")

    # 3. StartNode
    start = engine.get_start_node(index)
    if start is not None and start.get(X_NAME) == node_id:
        fc = engine.get_flowchart_element()
        if cont_name:
            engine._set_start_reference(cont_name)
        else:
            if "StartNode" in fc.attrib:
                del fc.attrib["StartNode"]
            for p in [p for p in fc.iterchildren(etree.Element) if _local(p) == "Flowchart.StartNode"]:
                fc.remove(p)
            warnings.append("Flowchart không còn node nào sau khi xoá StartNode.")
        rewired.append("Flowchart.StartNode")

    # 4. Xoá ViewState, tham chiếu trong Flowchart.Nodes và bản thân node
    removed_vs = _remove_view_state(engine, node)
    fc = engine.get_flowchart_element()
    for e in _flowchart_ref_entries(engine, node_id):
        fc.remove(e)
    parent = node.getparent()
    if parent is not None:
        parent.remove(node)
        # Nếu node nằm trong property element (VD: FlowStep.Next) thì xoá luôn holder rỗng
        if _local(parent) != "Flowchart" and "." in _local(parent) and len(parent) == 0:
            gp = parent.getparent()
            if gp is not None:
                gp.remove(parent)
    # x:Reference còn sót (attribute dạng {x:Reference id} hoặc phần tử) trong Flowchart chính
    for el in list(fc.iter(etree.Element)):
        if _local(el) == "Reference" and etree.QName(el).namespace == X_NS and (el.text or "").strip() == node_id:
            holder = el.getparent()
            if holder is not None:
                holder.remove(el)
                if "." in _local(holder) and len(holder) == 0 and holder.getparent() is not None:
                    holder.getparent().remove(holder)

    # 5. Cảnh báo
    unreachable: List[str] = []
    reachable = {n.get(X_NAME) for n in engine.reachable_nodes()}
    for name in engine._node_index():
        if name not in reachable:
            unreachable.append(name)
    if dropped and unreachable:
        warnings.append(
            f"Nhánh bị bỏ của FlowDecision '{node_id}' không còn nối vào luồng: {', '.join(unreachable)}. "
            "Có thể xoá tiếp các node này bằng remove_node."
        )
    still_defined = _all_defined_names(engine)
    orphan_names = {n for n in defined if n not in still_defined}
    users = _geometry_users(engine, orphan_names)
    if users:
        warnings.append(
            f"Node '{node_id}' định nghĩa {', '.join(sorted(orphan_names))} nhưng các activity sau vẫn tham chiếu: "
            + " | ".join(users)
        )
    engine.warnings.extend(warnings)

    return {
        "removed_node_id": node_id,
        "node_kind": kind,
        "continuation_node_id": cont_name,
        "rewired": rewired,
        "moved_inline_nodes": moved,
        "removed_view_states": removed_vs,
        "removed_geometry_names": sorted(defined),
        "unreachable_nodes": unreachable,
        "warnings": warnings,
    }


# ============================================================================
# update_node
# ============================================================================

def _format_attr_value(key: str, value: Any) -> str:
    """Tên / mã / enum: nguyên văn; số: nguyên văn; biểu thức: bọc [..]."""
    if value is None:
        return "{x:Null}"
    if isinstance(value, bool):
        return "True" if value else "False"
    s = str(value).strip()
    if s in ("{x:Null}", "True", "False") or key in _NAME_ATTRS or key.endswith("Name"):
        return s
    return format_arg_expr(s)


def _all_defined_names_except(engine: FlowchartEngine, own_node: etree._Element) -> Set[str]:
    """Tên Point / Link được định nghĩa ở các node KHÁC `own_node`."""
    own = own_node.get(X_NAME)
    names: Set[str] = set()
    for name, node in engine._node_index().items():
        if name != own:
            names |= _defined_names(node)
    return names


def _rename_references(engine: FlowchartEngine, old: str, new: str) -> List[str]:
    """Đổi mọi tham chiếu tới tên `old` sang `new` trong Flowchart (thuộc tính định nghĩa đã đổi trước đó)."""
    changed: List[str] = []
    expr_re = re.compile(r"(?<![A-Za-z0-9_.])" + re.escape(old) + r"\.")
    for el in engine.get_flowchart_element().iter(etree.Element):
        ln = _local(el)
        label = el.get("DisplayName") or el.get(X_NAME) or ln
        for a in _REF_ATTRS:
            v = (el.get(a) or "").strip()
            if v == old or v.startswith(old + "."):
                el.set(a, new + v[len(old):])
                changed.append(f"{ln} '{label}'.{a}")
        for a in _REF_LIST_ATTRS:
            v = el.get(a)
            if v and not v.startswith("[") and old in [x.strip() for x in v.split(",")]:
                el.set(a, ",".join(new if x.strip() == old else x for x in v.split(",")))
                changed.append(f"{ln} '{label}'.{a}")
        if ln == "SetMarkPointActivity" and (el.get("PointNumber") or "").strip() == old:
            el.set("PointNumber", new)
            changed.append(f"{ln} '{label}'.PointNumber")
        parent = el.getparent()
        if (
            ln == "String" and etree.QName(el).namespace == X_NS and (el.text or "").strip() == old
            and parent is not None and _local(parent).endswith(".ComponentNames")
        ):
            el.text = new
            changed.append(_local(parent))
        if ln in ("InArgument", "OutArgument") and el.get(X_KEY) in _REF_ARG_KEYS and (el.text or "").strip() == old:
            el.text = new
            changed.append(f"đối số {el.get(X_KEY)}")
        for a, v in list(el.attrib.items()):
            if v.startswith("[") and expr_re.search(v):
                el.set(a, expr_re.sub(new + ".", v))
                changed.append(f"{ln} '{label}'.{etree.QName(a).localname} (biểu thức)")
        if (el.text or "").strip().startswith("[") and expr_re.search(el.text):
            el.text = expr_re.sub(new + ".", el.text)
            where = el.get(X_KEY) or (_local(parent) if parent is not None else ln)
            changed.append(f"{where} (biểu thức)")
    return changed


def _check_curve_args(act: etree._Element, changed_args: Dict[str, List[Optional[str]]]) -> None:
    """CreationType của cung phải đi kèm đúng đối số; đối số của kiểu khác bị xoá."""
    tag = _local(act)
    ctype = act.get("CreationType") or "ArcGeneral"
    if ctype not in _CURVE_ARGS:
        raise ValueError(f"CreationType '{ctype}' không hợp lệ (chỉ {', '.join(_CURVE_ARGS)}).")
    need = _CURVE_ARGS[ctype]
    holder = next((c for c in act.iterchildren(etree.Element) if _local(c) == f"{tag}.Arguments"), None)
    present = {a.get(X_KEY): a for a in (holder.iterchildren(etree.Element) if holder is not None else [])}
    if need not in present or not (present[need].text or "").strip():
        raise ValueError(
            f"{tag} '{act.get('DisplayName')}' kiểu {ctype} cần đối số '{need}'. "
            f"Truyền kèm arguments={{'{need}': ...}} khi đổi CreationType."
        )
    for key, a in present.items():
        if key in _CURVE_ARGS.values() and key != need:
            holder.remove(a)
            changed_args[key] = [a.text, None]


def _retype_variable(engine: FlowchartEngine, act: etree._Element, new_type: str) -> str:
    """Đổi kiểu biến nội bộ: VariableType, khai báo <Variable> và mọi đối số gán cho biến này."""
    from sac_mcp.core.builders.logic_builder import SAC_VARIABLE_TYPES

    if new_type not in SAC_VARIABLE_TYPES:
        raise ValueError(f"VariableType '{new_type}' không hợp lệ. SAC chỉ hỗ trợ: Double, Integer, String, YesNo.")
    sac_type, clr = SAC_VARIABLE_TYPES[new_type]
    name = act.get("VariableName") or ""
    fc = engine.get_flowchart_element()
    for v in fc.xpath("./*[local-name()='Flowchart.Variables']/*[local-name()='Variable' and @Name=$n]", n=name):
        v.set(X_TYPEARGS, clr)
    for el in act.iter(etree.Element):
        if _local(el) in ("InArgument", "OutArgument"):
            el.set(X_TYPEARGS, clr)
    for sv in fc.iter(etree.Element):
        if _local(sv) != "SetVariableValue":
            continue
        args = [a for a in sv.iter(etree.Element) if _local(a) in ("InArgument", "OutArgument")]
        if any(_local(a) == "OutArgument" and (a.text or "").strip() == f"[{name}]" for a in args):
            for a in args:
                a.set(X_TYPEARGS, clr)
    return sac_type


def _guess_arg_type(key: str, value: Any) -> str:
    if key in _STRING_ARG_KEYS:
        return "x:String"
    if "SurfaceTarget" in key:
        return "asw:SurfaceTarget"
    if isinstance(value, bool) or str(value).strip() in ("True", "False"):
        return "x:Boolean"
    return "x:Double"


def _format_arg_value(type_args: str, value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    s = str(value).strip()
    if s in ("{x:Null}", ""):
        return s  # Đối số để trống (VD: OffsetTarget2 không gán) giữ nguyên trống
    if type_args == "x:String":
        if s.startswith("[") and s.endswith("]"):
            return s
        return s.strip('"')
    if type_args == "x:Boolean":
        if s.lower() in ("true", "false"):
            return s.capitalize()
        return format_arg_expr(s)
    return format_arg_expr(s)


def _set_codes(engine: FlowchartEngine, act: etree._Element, prop: str, value: Any) -> None:
    """Ghi danh sách Code (PointCodes / LinkCodes / AutoLinkCodes / ShapeCodes...) dạng phần tử con."""
    tag = _local(act)
    ns = etree.QName(act).namespace
    if isinstance(value, str):
        codes = [c.strip().strip('"').strip("'") for c in value.split(",")]
    elif value is None:
        codes = []
    else:
        codes = [str(c).strip().strip('"').strip("'") for c in value]
    codes = [c for c in codes if c]
    for c in list(act.iterchildren(etree.Element)):
        if _local(c) == f"{tag}.{prop}":
            act.remove(c)
    if not codes:
        act.set(prop, "{x:Null}")
        return
    if prop in act.attrib:
        del act.attrib[prop]
    holder = etree.Element(f"{{{ns}}}{tag}.{prop}")
    # Đặt trước ViewState (giữ thứ tự giống SAC)
    vs = [c for c in act.iterchildren(etree.Element) if _local(c).endswith("WorkflowViewStateService.ViewState")]
    if vs:
        vs[0].addprevious(holder)
    else:
        act.append(holder)
    lst = etree.SubElement(
        holder,
        engine.qn("scg", "List"),
        attrib={X_TYPEARGS: "InArgument(x:String)", "Capacity": str(max(4, len(codes)))},
    )
    for c in codes:
        etree.SubElement(lst, engine.qn("wf", "InArgument"), attrib={X_TYPEARGS: "x:String"}).text = c


def update_node(
    engine: FlowchartEngine,
    node_id: str,
    attributes: Optional[Dict[str, Any]] = None,
    arguments: Optional[Dict[str, Any]] = None,
    rename_references: bool = True,
) -> Dict[str, Any]:
    """
    Sửa thuộc tính / đối số của node.
    Thuộc tính tên / mã / enum (PointNumber, FromPoint, Links, CreationType, DisplayName...) ghi nguyên văn;
    thuộc tính số nhận số hoặc biểu thức VB (tự bọc [..]).
    Đổi tên PointNumber / LinkNumber...: rename_references=True cập nhật mọi tham chiếu (FromPoint, StartPoint,
    EndPoint, Links, FirstLink/SecondLink, ComponentNames, đối số CenterPoint/ArcPoint2..., biểu thức 'P4.X');
    False -> chỉ cảnh báo. Đổi VariableType của InternalVariableDefine cập nhật khai báo biến và các
    SetVariableValue liên quan. CreateCurve: CreationType phải đi kèm đúng đối số (ArcGeneral-CenterPoint,
    Arc3Points-ArcPoint2, ParabolaGeneral-MidOrdinate); đối số của kiểu cũ bị xoá.

    - FlowDecision: attributes chỉ nhận 'Condition' (tự bọc [..]) và 'DisplayName'.
    - FlowStep: attributes là thuộc tính của activity bên trong (phải có trong danh mục activity của SAC).
      Giá trị đang là biểu thức [..] thì giá trị mới cũng được bọc [..]; None -> {x:Null}.
      Thuộc tính '*Codes' nhận danh sách hoặc chuỗi phân tách dấu phẩy.
    - arguments: {x:Key: giá trị} cho các <InArgument x:Key=...> trong '<Activity>.Arguments'
      (VD: DeltaX1, DeltaY1, Slope2...), hoặc tên property element chứa một InArgument
      (VD: 'VariableValue', 'Message', 'DefaultValue', 'Value'). Giá trị None để xoá đối số.
    """
    attributes = dict(attributes or {})
    arguments = dict(arguments or {})
    if not attributes and not arguments:
        raise ValueError("Cần truyền ít nhất một trong 'attributes' hoặc 'arguments'.")
    node = get_node(engine, node_id)
    node_id = node.get(X_NAME)
    kind = _local(node)
    changed_attrs: Dict[str, List[Optional[str]]] = {}
    changed_args: Dict[str, List[Optional[str]]] = {}

    if kind == "FlowDecision":
        if arguments:
            raise ValueError(f"FlowDecision '{node_id}' không có arguments; chỉ sửa được 'Condition' và 'DisplayName'.")
        bad = [k for k in attributes if k not in ("Condition", "DisplayName")]
        if bad:
            raise ValueError(f"FlowDecision chỉ cho sửa 'Condition' và 'DisplayName' (không có: {', '.join(bad)}).")
        for k, v in attributes.items():
            old = node.get(k)
            s = str(v).strip() if v is not None else ""
            if k == "Condition":
                if not s:
                    raise ValueError("Condition không được để trống.")
                s = s if s.startswith("[") else f"[{s}]"
            node.set(k, s)
            changed_attrs[k] = [old, s]
        return {"node_id": node_id, "node_kind": kind, "activity": "FlowDecision",
                "changed_attributes": changed_attrs, "changed_arguments": changed_args}

    if kind != "FlowStep":
        raise ValueError(f"Chưa hỗ trợ sửa node loại {kind} ('{node_id}').")

    act = get_activity(node)
    if act is None:
        raise ValueError(f"FlowStep '{node_id}' không chứa activity nào để sửa.")
    tag = _local(act)
    catalog = load_activity_catalog()
    spec = catalog.get(tag)

    renames: List[tuple] = []
    warnings: List[str] = []
    if attributes:
        if spec is None:
            raise ValueError(
                f"Activity '{tag}' trong node '{node_id}' không có trong danh mục activity của SAC "
                "nên không sửa thuộc tính được bằng công cụ này."
            )
        unknown = [k for k in attributes if k not in spec.properties]
        if unknown:
            raise ValueError(
                f"{tag} không có thuộc tính: {', '.join(unknown)}. "
                f"Thuộc tính hợp lệ: {', '.join(sorted(spec.properties))}."
            )
        for k, v in attributes.items():
            if k == "Arguments":
                raise ValueError("Không sửa 'Arguments' qua attributes; dùng tham số arguments={x:Key: giá trị}.")
            old_el = [c for c in act.iterchildren(etree.Element) if _local(c) == f"{tag}.{k}"]
            old = act.get(k)
            if k.endswith("Codes"):
                old_codes = None
                if old_el:
                    old_codes = ", ".join((a.text or "").strip() for a in old_el[0].iter(etree.Element)
                                          if _local(a) == "InArgument")
                _set_codes(engine, act, k, v)
                new_codes = act.get(k)
                if new_codes is None:
                    new_codes = ", ".join(
                        (a.text or "").strip()
                        for c in act.iterchildren(etree.Element) if _local(c) == f"{tag}.{k}"
                        for a in c.iter(etree.Element) if _local(a) == "InArgument"
                    )
                changed_attrs[k] = [old if old is not None else old_codes, new_codes]
                continue
            if old_el:
                raise ValueError(
                    f"Thuộc tính '{k}' của {tag} đang lưu dạng phần tử con; chưa hỗ trợ sửa qua attributes."
                )
            if k == "VariableName" and tag == "InternalVariableDefine" and v != old:
                raise ValueError(
                    "Không đổi được VariableName của InternalVariableDefine bằng update_node "
                    "(biến được dùng trong nhiều biểu thức). Hãy tạo biến mới rồi xoá biến cũ."
                )
            new = _format_attr_value(k, v)
            if k == "VariableType" and tag == "InternalVariableDefine":
                new = _retype_variable(engine, act, new)
            act.set(k, new)
            changed_attrs[k] = [old, new]
            if k in _RENAMEABLE_ATTRS and not _is_null(old) and not _is_null(new) and old != new:
                renames.append((old.strip(), new.strip()))

    if arguments:
        args_holder = next((c for c in act.iterchildren(etree.Element) if _local(c) == f"{tag}.Arguments"), None)
        for k, v in arguments.items():
            # Cho phép {"value": ..., "type": "asw:OffsetTarget"} để chỉ rõ x:TypeArguments
            forced_type: Optional[str] = None
            if isinstance(v, dict):
                forced_type = v.get("type")
                v = v.get("value")
            target: Optional[etree._Element] = None
            if args_holder is not None:
                target = next(
                    (a for a in args_holder.iterchildren(etree.Element) if a.get(X_KEY) == k), None
                )
            if target is None:
                prop = next((c for c in act.iterchildren(etree.Element) if _local(c) == f"{tag}.{k}"), None)
                if prop is not None:
                    target = next(
                        (a for a in prop.iterchildren(etree.Element) if _local(a) in ("InArgument", "OutArgument")),
                        None,
                    )
            if target is None:
                if v is None:
                    continue
                if args_holder is None:
                    raise ValueError(
                        f"{tag} trong node '{node_id}' không có đối số '{k}' (không có phần tử '{tag}.Arguments')."
                    )
                type_args = forced_type or _guess_arg_type(k, v)
                target = etree.SubElement(
                    args_holder, engine.qn("wf", "InArgument"), attrib={X_TYPEARGS: type_args, X_KEY: k}
                )
                old = None
            else:
                old = target.text
                if v is None:
                    if target.getparent() is args_holder:
                        args_holder.remove(target)
                        changed_args[k] = [old, None]
                        continue
                    raise ValueError(f"Đối số '{k}' là bắt buộc của {tag}, không xoá được.")
            if forced_type and target.get(X_TYPEARGS) != forced_type:
                target.set(X_TYPEARGS, forced_type)
            type_args = target.get(X_TYPEARGS) or "x:Double"
            if _local(target) == "OutArgument":
                s = str(v).strip()
                new = s if s.startswith("[") else f"[{s}]"
            else:
                new = _format_arg_value(type_args, v)
            target.text = new
            changed_args[k] = [old, new]

    if tag in ("CreateCurve", "CreateAuxCurve") and (
        "CreationType" in attributes or any(k in arguments for k in _CURVE_ARGS.values())
    ):
        _check_curve_args(act, changed_args)

    renamed_refs: List[str] = []
    for old_name, new_name in renames:
        others = _all_defined_names_except(engine, node)
        if old_name in others:
            warnings.append(f"'{old_name}' còn được định nghĩa ở node khác nên KHÔNG đổi tham chiếu sang '{new_name}'.")
            continue
        if new_name in others:
            warnings.append(f"Tên mới '{new_name}' đã được định nghĩa ở node khác (trùng tên).")
        if rename_references:
            renamed_refs += _rename_references(engine, old_name, new_name)
        else:
            users = _geometry_users(engine, {old_name})
            if users:
                warnings.append(
                    f"Đã đổi '{old_name}' -> '{new_name}' nhưng các activity sau vẫn tham chiếu tên cũ: "
                    + " | ".join(users)
                )
    engine.warnings.extend(warnings)

    return {
        "node_id": node_id,
        "node_kind": kind,
        "activity": tag,
        "changed_attributes": changed_attrs,
        "changed_arguments": changed_args,
        "renamed_references": renamed_refs,
        "warnings": warnings,
    }
