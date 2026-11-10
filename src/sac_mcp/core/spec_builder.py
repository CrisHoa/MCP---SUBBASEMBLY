"""
Spec khai báo (JSON) cho một Subassembly:

  - export_spec(pkt_path) -> dict: đọc file .pkt và mô tả lại thành danh sách Parameter + các bước dựng (steps)
    tương ứng 1-1 với các lời gọi builder (point / link / shape / decision / define_variable ...).
  - build_from_spec(spec, output_path, civil_version=None) -> dict: dựng lại file .pkt từ spec
    (tạo từ template, thêm Parameter, chạy từng bước qua builder theo thứ tự, lưu MỘT lần).

Mỗi bước có 'id' (do spec đặt, không phải __ReferenceID) và tuỳ chọn:
  - parent: '<id>' / '<id>:True' / '<id>:False' hoặc danh sách các chuỗi đó (node có nhiều nhánh đổ vào).
            Bỏ trống = nối vào MỌI đầu ra đang mở của luồng (giống builder).
  - goto:   {'Next' | 'True' | 'False': '<id bước trước>'} - nhánh quay về một bước đã dựng (vòng lặp).
  - attributes / arguments: ghi đè thuộc tính / đối số mà builder không có tham số riêng
            (áp dụng bằng node_editor.update_node sau khi dựng).
Định dạng chi tiết: docs/spec_format.md.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lxml import etree

from sac_mcp.core.builders import GeometryBuilder, LogicBuilder, ParameterBuilder
from sac_mcp.core.node_editor import _guess_arg_type, get_activity, update_node
from sac_mcp.core.opc_package import PktPackage
from sac_mcp.core.version_manager import VersionManager
from sac_mcp.core.xaml_engine import FLOW_NODE_TAGS, SLOT_PROPS, FlowchartEngine, _local
from sac_mcp.models.schemas import (
    CivilVersion,
    ParameterCategory,
    ParameterDataType,
    PointGeometryType,
    ReportMessageType,
)

SPEC_FORMAT_VERSION = 1
X_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
X_NAME = f"{{{X_NS}}}Name"
X_KEY = f"{{{X_NS}}}Key"
X_TYPEARGS = f"{{{X_NS}}}TypeArguments"

# Positioning của CreatePoint -> (PointGeometryType, key tham số 1, key tham số 2, {đối số phụ: giá trị builder ghi})
_POSITIONING: Dict[str, Tuple[str, str, str, Dict[str, str]]] = {
    "DeltaXAndDeltaY": ("DeltaX_DeltaY", "DeltaX1", "DeltaY1", {}),
    "SlopeAndDeltaX": ("Slope_DeltaX", "Slope2", "DeltaX2", {}),
    "SlopeToSurface": (
        "Slope_To_Surface", "Slope3", "SurfaceTarget3",
        {"ReverseSlopeDirection3": "False", "DeltaXForLayout3": "5", "ShowErrors": "True"},
    ),
    "DeltaXOnSurface": ("DeltaX_On_Surface", "DeltaX4", "SurfaceTarget4", {}),
    "SlopeAndDeltaY": ("Slope_DeltaY", "Slope5", "DeltaY5", {}),
    "AngleAndDeltaX": ("Angle_DeltaX", "Angle6", "DeltaX6", {}),
    "AngleAndDeltaY": ("Angle_DeltaY", "Angle7", "DeltaY7", {}),
    "AngleAndDistance": ("Angle_Distance", "Angle8", "Distance8", {}),
    "InterpolatePoint": ("Interpolate", "DestPoint", "InterpolateParam", {}),
}

_CLR_TO_VAR_TYPE = {
    "x:Double": "Double", "x:Int32": "Integer", "x:String": "String", "x:Boolean": "Boolean",
    "asw:EnumType": "YesNo", "asw:Slope": "Slope", "asw:Grade": "Grade",
}

_PARAM_TYPE_FROM_XAML = {
    "Double": "Double",
    "Int32": "Integer",
    "String": "String",
    "Boolean": "Boolean",
    "Grade": "Grade",
    "Slope": "Slope",
    "CrossSegmentType": "Superelevation",
    "SlopeDirection": "SlopeDirection",
    "PotentialPivot": "PotentialPivot",
    "CantParam": "Cant",
    "ElevationTarget": "ElevationTarget",
    "OffsetTarget": "OffsetTarget",
    "SurfaceTarget": "SurfaceTarget",
}

_CATEGORY_ALIASES = {"In": "Input", "Out": "Output", "InOut": "Input"}

# Các trường của từng loại bước: (bắt buộc, tuỳ chọn)
STEP_FIELDS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "point": (("point_code",), ("from_point", "point_type", "param_1", "param_2", "point_codes", "add_link",
                                "link_name", "link_codes", "is_auxiliary")),
    "link": (("link_name", "start_point", "end_point"), ("link_codes", "apply_aor", "is_auxiliary")),
    "shape": (("shape_code", "links"), ("shape_codes",)),
    "fillet_arc": (("link_number", "first_link", "second_link"),
                   ("round_radius", "start_point_name", "end_point_name", "link_codes")),
    "loop": (("loop_code", "links"), ("repetition_count",)),
    "intersection": (("point_code", "link1", "link2"), ("is_auxiliary", "point_codes")),
    "strip_surface": (("display_name", "depth", "end_point_name"),
                      ("end_offset", "end_offset_target", "link_codes", "surface_target", "start_point_name",
                       "start_offset", "link_number")),
    "curve": (("link_number", "start_point", "end_point"),
              ("center_point", "arc_point", "mid_ordinate", "creation_type", "num_increments", "link_codes", "is_auxiliary")),
    "offset": (("offset_code", "links"), ("offset_distance", "offset_codes")),
    "get_mark_point": (("point_number", "mark_name"),
                       ("point_codes", "is_auxiliary", "prev_offset", "prev_delta_elevation")),
    "set_mark_point": (("point_number", "mark_name"), ()),
    "report": (("message",), ("message_type",)),
    "define_variable": (("name",), ("var_type", "default")),
    "set_variable": (("name", "value"), ("var_type",)),
    "set_output": (("name", "value"), ("var_type",)),
    "decision": (("condition",), ("display_name",)),
    "raw": ((), ("activity", "xml", "node")),
}
_COMMON_FIELDS = {"id", "type", "parent", "goto", "attributes", "arguments", "comment"}


# ============================================================================
# Tiện ích đọc XAML
# ============================================================================

def _unwrap(expr: Optional[str]) -> Optional[str]:
    """'[B_day / 2]' -> 'B_day / 2'; số giữ nguyên; '{x:Null}' -> None."""
    if expr is None:
        return None
    s = expr.strip()
    if s in ("{x:Null}", ""):
        return None
    if s.startswith("[") and s.endswith("]"):
        return s[1:-1].strip()
    return s


def _null(v: Optional[str]) -> bool:
    return v is None or v.strip() in ("", "{x:Null}")


def _read_codes(act: etree._Element, prop: str) -> List[str]:
    tag = _local(act)
    val = act.get(prop)
    if not _null(val):
        return [c.strip().strip('"') for c in val.split(",") if c.strip()]
    for c in act.iterchildren(etree.Element):
        if _local(c) == f"{tag}.{prop}":
            return [(a.text or "").strip() for a in c.iter(etree.Element) if _local(a) == "InArgument"]
    return []


def _read_args(act: etree._Element) -> Dict[str, str]:
    tag = _local(act)
    out: Dict[str, str] = {}
    for c in act.iterchildren(etree.Element):
        if _local(c) == f"{tag}.Arguments":
            for a in c.iterchildren(etree.Element):
                k = a.get(X_KEY)
                if k:
                    out[k] = (a.text or "").strip()
    return out


def _read_arg_types(act: etree._Element) -> Dict[str, str]:
    tag = _local(act)
    out: Dict[str, str] = {}
    for c in act.iterchildren(etree.Element):
        if _local(c) == f"{tag}.Arguments":
            for a in c.iterchildren(etree.Element):
                k = a.get(X_KEY)
                if k:
                    out[k] = a.get(X_TYPEARGS) or "x:Double"
    return out


def _extra_args(act: etree._Element, values: Dict[str, str]) -> Dict[str, Any]:
    """Đối số phụ: giá trị thường nếu kiểu đoán được, ngược lại {'value', 'type'} (VD: OffsetTarget2)."""
    types = _read_arg_types(act)
    out: Dict[str, Any] = {}
    for k, v in values.items():
        t = types.get(k, "x:Double")
        out[k] = v if _guess_arg_type(k, v) == t else {"value": v, "type": t}
    return out


def _prop_arg(act: etree._Element, prop: str) -> Optional[etree._Element]:
    tag = _local(act)
    for c in act.iterchildren(etree.Element):
        if _local(c) == f"{tag}.{prop}":
            for a in c.iterchildren(etree.Element):
                if _local(a) in ("InArgument", "OutArgument"):
                    return a
    return None


def _num(v: Optional[str]) -> Any:
    """Chuỗi số -> float/int để JSON gọn; giữ chuỗi nếu là biểu thức."""
    if v is None:
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if re.fullmatch(r"-?\d+", v.strip()) else f


def _diff_attrs(act: etree._Element, defaults: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, d in defaults.items():
        v = act.get(k)
        if v is not None and v != d:
            out[k] = v
    return out


# ============================================================================
# Activity -> step
# ============================================================================

def _point_step(act: etree._Element) -> Optional[Dict[str, Any]]:
    pos = act.get("Positioning") or "DeltaXAndDeltaY"
    if pos not in _POSITIONING:
        return None
    ptype, k1, k2, builder_extra = _POSITIONING[pos]
    args = _read_args(act)
    is_aux = _local(act) == "CreateAuxPoint"
    code = (act.get("PointNumber") or "").strip()
    if not code:
        return None
    from_pt = act.get("FromPoint")
    add_link = (act.get("AutoLink") or "").lower() == "true" and not _null(act.get("AutoLinkGeometryName"))
    link_name = act.get("AutoLinkGeometryName") if add_link else ""
    p1 = args.get(k1)
    if ptype == "Interpolate":
        p1 = (p1 or "").strip()
    else:
        p1 = _unwrap(p1)
    step: Dict[str, Any] = {
        "type": "point",
        "point_code": code,
        "from_point": "Origin" if _null(from_pt) else from_pt.strip(),
        "point_type": ptype,
        "param_1": p1 if p1 is not None else "0.0",
        "param_2": _unwrap(args.get(k2)) if args.get(k2) is not None else "0.0",
    }
    codes = _read_codes(act, "PointCodes")
    if codes:
        step["point_codes"] = codes
    if add_link:
        step["add_link"] = True
        step["link_name"] = link_name
        lc = _read_codes(act, "AutoLinkCodes")
        if lc:
            step["link_codes"] = lc
    if is_aux:
        step["is_auxiliary"] = True
    attrs = _diff_attrs(act, {"ApplyAOR": "False"})
    disp = act.get("DisplayName")
    default_disp = f"{code}&{link_name}" if add_link else code
    if disp is not None and disp != default_disp:
        attrs["DisplayName"] = disp
    if attrs:
        step["attributes"] = attrs
    extra_args = {
        k: v for k, v in args.items() if k not in (k1, k2) and builder_extra.get(k) != v
    }
    if extra_args:
        step["arguments"] = _extra_args(act, extra_args)
    return step


def _display_extra(step: Dict[str, Any], act: etree._Element, default: str, extra: Optional[Dict[str, str]] = None) -> None:
    attrs = dict(extra or {})
    disp = act.get("DisplayName")
    if disp is not None and disp != default:
        attrs["DisplayName"] = disp
    if attrs:
        step["attributes"] = attrs


def activity_to_step(act: etree._Element) -> Optional[Dict[str, Any]]:
    """Chuyển activity trong FlowStep thành bước spec; None nếu chưa hỗ trợ (sẽ xuất dạng 'raw')."""
    tag = _local(act)
    if tag in ("CreatePoint", "CreateAuxPoint"):
        return _point_step(act)

    if tag in ("CreateLink", "CreateAuxLink"):
        name = act.get("LinkNumber") or ""
        if not name or _null(act.get("StartPoint")) or _null(act.get("EndPoint")):
            return None
        step = {"type": "link", "link_name": name, "start_point": act.get("StartPoint"),
                "end_point": act.get("EndPoint")}
        codes = _read_codes(act, "LinkCodes")
        if codes:
            step["link_codes"] = codes
        if (act.get("ApplyAOR") or "").lower() == "true":
            step["apply_aor"] = True
        if tag == "CreateAuxLink":
            step["is_auxiliary"] = True
        _display_extra(step, act, name, _diff_attrs(act, {"IsEnabled": "True"}))
        return step

    if tag == "CreateShape":
        code = act.get("ShapeNumber") or ""
        links = [s.strip() for s in (act.get("Links") or "").split(",") if s.strip()]
        if not links:
            for c in act.iterchildren(etree.Element):
                if _local(c) == "CreateShape.ComponentNames":
                    links = [(s.text or "").strip() for s in c.iterchildren(etree.Element) if (s.text or "").strip()]
        if not code or not links:
            return None
        step = {"type": "shape", "shape_code": code, "links": links}
        codes = _read_codes(act, "ShapeCodes")
        if codes:
            step["shape_codes"] = codes
        _display_extra(step, act, code)
        return step

    if tag == "FilletArcActivity":
        num = act.get("LinkNumber") or ""
        if not num or _null(act.get("FirstLink")) or _null(act.get("SecondLink")):
            return None
        step = {
            "type": "fillet_arc", "link_number": num, "first_link": act.get("FirstLink"),
            "second_link": act.get("SecondLink"), "round_radius": _num(act.get("RoundParameter") or "0.05"),
        }
        if not _null(act.get("StartPointName")):
            step["start_point_name"] = act.get("StartPointName")
        if not _null(act.get("EndPointName")):
            step["end_point_name"] = act.get("EndPointName")
        codes = _read_codes(act, "LinkCodes")
        if codes:
            step["link_codes"] = codes
        _display_extra(step, act, num, _diff_attrs(act, {"RoundBy": "ByRadius", "Tessellation": "10"}))
        return step

    if tag == "CreateLoop":
        code = act.get("LoopNumber") or ""
        links = [s.strip() for s in (act.get("Links") or "").split(",") if s.strip()]
        if not code:
            return None
        step = {"type": "loop", "loop_code": code, "links": links,
                "repetition_count": _num(act.get("LoopDRepetition") or "1")}
        _display_extra(step, act, code)
        return step

    if tag in ("LinkIntersection", "AuxIntersection"):
        if (act.get("CreationType") or "IntersectionTwoLinks") != "IntersectionTwoLinks":
            return None
        args = _read_args(act)
        code = act.get("PointNumber") or ""
        if not code or "FirstLink1" not in args or "SecondLink1" not in args:
            return None
        step = {"type": "intersection", "point_code": code, "link1": args["FirstLink1"],
                "link2": args["SecondLink1"]}
        if tag == "AuxIntersection":
            step["is_auxiliary"] = True
        codes = _read_codes(act, "PointCodes")
        if codes:
            step["point_codes"] = codes
        extra_args = {k: v for k, v in args.items()
                      if k not in ("FirstLink1", "SecondLink1")
                      and not (k in ("ExtendFirstLink1", "ExtendSecondLink1") and v == "True")}
        if extra_args:
            step["arguments"] = _extra_args(act, extra_args)
        _display_extra(step, act, code, _diff_attrs(act, {"Index": "0"}))
        return step

    if tag == "StripSurfaceActivity":
        disp = act.get("DisplayName") or "Strip"
        step = {
            "type": "strip_surface",
            "display_name": disp,
            "depth": _unwrap(act.get("Depth")) or "0",
            "end_point_name": act.get("EndPointName") or f"{disp}_End",
            "end_offset": _num(_unwrap(act.get("EndOffset")) or "0"),
            "surface_target": _unwrap(act.get("Surface")) or "EG",
            "start_offset": _unwrap(act.get("StartOffset")) or "0",
        }
        if not _null(act.get("EndOffsetTarget")):
            step["end_offset_target"] = _unwrap(act.get("EndOffsetTarget"))
        if not _null(act.get("StartPointName")):
            step["start_point_name"] = act.get("StartPointName")
        if not _null(act.get("LinkNumber")):
            step["link_number"] = act.get("LinkNumber")
        step["link_codes"] = _read_codes(act, "LinkCodes")
        extra = _diff_attrs(act, {"DepthForLayoutMode": "0", "StartOffsetTarget": "{x:Null}"})
        if extra:
            step["attributes"] = extra
        return step

    if tag in ("CreateCurve", "CreateAuxCurve"):
        num = act.get("LinkNumber") or ""
        if not num:
            return None
        args = _read_args(act)
        step = {"type": "curve", "link_number": num, "start_point": act.get("StartPoint") or "",
                "end_point": act.get("EndPoint") or "",
                "creation_type": act.get("CreationType") or "ArcGeneral",
                "num_increments": _num(act.get("NoIncrements") or "5")}
        if args.get("ArcPoint2"):
            step["arc_point"] = args["ArcPoint2"]
        if args.get("MidOrdinate"):
            step["mid_ordinate"] = _unwrap(args["MidOrdinate"])
        if args.get("CenterPoint"):
            step["center_point"] = args["CenterPoint"]
        codes = _read_codes(act, "LinkCodes")
        if codes:
            step["link_codes"] = codes
        if tag == "CreateAuxCurve":
            step["is_auxiliary"] = True
        extra_args = {k: v for k, v in args.items() if k not in ("CenterPoint", "ArcPoint2", "MidOrdinate")}
        if extra_args:
            step["arguments"] = _extra_args(act, extra_args)
        _display_extra(step, act, num)
        return step

    if tag == "CreateOffset":
        code = act.get("OffsetNumber") or ""
        links = [s.strip() for s in (act.get("Links") or "").split(",") if s.strip()]
        if not code:
            return None
        step = {"type": "offset", "offset_code": code, "links": links,
                "offset_distance": _num(act.get("OffsetDistance") or "0.15")}
        codes = _read_codes(act, "OffsetCodes")
        if codes:
            step["offset_codes"] = codes
        _display_extra(step, act, code)
        return step

    if tag in ("GetMarkPointActivity", "GetAuxMarkPointActivity"):
        pn, mk = act.get("PointNumber") or "", act.get("MarkName") or ""
        if not pn or not mk:
            return None
        step = {"type": "get_mark_point", "point_number": pn, "mark_name": mk}
        for attr, key in (("PrevOffset", "prev_offset"), ("PrevDeltaElevation", "prev_delta_elevation")):
            v = _unwrap(act.get(attr))
            if v is not None and v != "0":
                step[key] = v
        codes = _read_codes(act, "PointCodes")
        if codes:
            step["point_codes"] = codes
        if tag == "GetAuxMarkPointActivity":
            step["is_auxiliary"] = True
        _display_extra(step, act, pn)
        return step

    if tag == "SetMarkPointActivity":
        pn, mk = act.get("PointNumber") or "", act.get("MarkName") or ""
        if not pn or not mk:
            return None
        step = {"type": "set_mark_point", "point_number": pn, "mark_name": mk}
        _display_extra(step, act, f"Mark {pn}->{mk}")
        return step

    if tag == "CustomErrorReportActivity":
        msg = _prop_arg(act, "Message")
        if msg is None:
            return None
        level = act.get("ErrorLevel") or "Informational"
        if level not in ("Informational", "Warning", "Error"):
            return None
        text = (msg.text or "").strip()
        m_lit = re.fullmatch(r'\["([^"]*)"\]', text)
        # Chuỗi hằng ["..."] -> văn bản thuần (builder tự bọc lại); biểu thức khác giữ nguyên [..]
        step = {"type": "report", "message": m_lit.group(1) if m_lit else text, "message_type": level}
        _display_extra(step, act, f"Report {level}")
        return step

    if tag == "InternalVariableDefine":
        name = act.get("VariableName") or ""
        dv = _prop_arg(act, "DefaultValue")
        if not name:
            return None
        step = {"type": "define_variable", "name": name, "var_type": act.get("VariableType") or "Double",
                "default": (_unwrap(dv.text) or "0.0") if dv is not None else "0.0"}
        if step["var_type"] == r"Yes\No":
            step["var_type"] = "YesNo"
        # DisplayName mặc định của LogicBuilder: 'Ten <Kieu>' (SAC GUI ghi giống vậy)
        _display_extra(step, act, f"{name} <{act.get('VariableType') or 'Double'}>")
        return step

    if tag in ("SetVariableValue", "SetOutputParameterValue"):
        is_var = tag == "SetVariableValue"
        out = _prop_arg(act, "VariableName" if is_var else "OutputParammeter")
        val = _prop_arg(act, "VariableValue" if is_var else "Value")
        if out is None or val is None:
            return None
        name = _unwrap(out.text) or ""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            return None
        step = {"type": "set_variable" if is_var else "set_output", "name": name,
                "value": _unwrap(val.text) or "0",
                "var_type": _CLR_TO_VAR_TYPE.get(val.get(X_TYPEARGS) or "x:Double", "Double")}
        # DisplayName mặc định của LogicBuilder: 'Ten = bieu thuc' (cắt 60 ký tự)
        _display_extra(step, act, f"{name} = {str(step['value']).strip().strip('[]')}"[:60])
        return step

    return None


def _raw_step(node: etree._Element, act: Optional[etree._Element]) -> Dict[str, Any]:
    step: Dict[str, Any] = {"type": "raw", "activity": _local(act) if act is not None else None}
    if act is not None:
        step["xml"] = etree.tostring(act, encoding="unicode")
    return step


# ============================================================================
# Parameters
# ============================================================================

def _scratch_engine(name: str = "Scratch") -> FlowchartEngine:
    return FlowchartEngine(VersionManager.build_base_flowchart_xaml(subassembly_name=name))


def _builder_default(data_type: str, category: str, value: str) -> Optional[str]:
    """Giá trị ParameterBuilder sẽ ghi lên Activity root cho value (để kiểm tra dạng rút gọn có tái tạo đúng)."""
    try:
        eng = _scratch_engine()
        ParameterBuilder.add_parameter(eng, "Pchk", ParameterCategory(category), ParameterDataType(data_type), value)
        short = eng.get_subassembly_class_short_name()
        return eng.root.get(eng.qn("this", f"{short}.Pchk"))
    except Exception:
        return None


def _export_parameters(engine: FlowchartEngine) -> List[Dict[str, Any]]:
    params = []
    for p in engine.extract_parameters():
        raw_default = p.default_value
        category = _CATEGORY_ALIASES.get(p.category, p.category)
        xaml_t = p.data_type
        dtype = _PARAM_TYPE_FROM_XAML.get(xaml_t, xaml_t)
        if xaml_t == "EnumType":
            # Phân loại theo nhóm (tham số thứ 3 của EnumType): "Side", "Yes\No", "Superelevation"
            m_grp = re.search(r'EnumType\(\s*-?\d+\s*,\s*"([^"]*)"\s*(?:,\s*"([^"]*)")?', raw_default or "")
            label, group = (m_grp.group(1), m_grp.group(2) or "") if m_grp else ("", "")
            if group.replace("\\", "").lower() == "yesno" or label in ("Yes", "No"):
                dtype = "YesNo"
            elif group == "Superelevation":
                dtype = "Superelevation"
            else:
                dtype = "Side"
        default: Optional[str] = raw_default
        if category == "Output":
            default = None
        elif raw_default is not None and dtype in [d.value for d in ParameterDataType]:
            # Rút gọn '[new Slope(-0.6667)]' -> '-0.6667', '[new EnumType(0, "Right", "Side")]' -> 'Right'
            cand = None
            m = re.fullmatch(r"\[new (?:Slope|Grade)\(\s*([^)]+?)\s*\)\]", raw_default)
            if m:
                cand = m.group(1)
            m = re.fullmatch(r'\[new EnumType\(\s*-?\d+\s*,\s*"([^"]*)".*\)\]', raw_default)
            if m:
                cand = m.group(1)
            if cand is not None and _builder_default(dtype, category, cand) == raw_default:
                default = cand
            elif raw_default is not None and dtype in ("SurfaceTarget", "OffsetTarget", "ElevationTarget"):
                if _builder_default(dtype, category, "-9999").replace('"Pchk"', f'"{p.name}"') == raw_default:
                    default = None  # dạng Preview chuẩn builder tự sinh
        item: Dict[str, Any] = {
            "name": p.name,
            "category": category,
            "data_type": dtype,
            "default": default,
            "display_name": p.display_name or p.name,
            "description": p.description or "",
        }
        params.append(item)
    return params


# ============================================================================
# export_spec
# ============================================================================

def _successor_slots(engine: FlowchartEngine, node: etree._Element, index) -> List[Tuple[str, Optional[etree._Element]]]:
    kind = _local(node)
    return [(slot, engine.get_slot_target(node, slot, index)) for slot in SLOT_PROPS.get(kind, ())]


def export_spec_from_engine(
    engine: FlowchartEngine,
    name: str = "Subassembly",
    description: str = "",
    civil_version: str = "2026",
) -> Dict[str, Any]:
    """Xuất spec từ một FlowchartEngine đã nạp XAML."""
    warnings: List[str] = []
    index = engine._node_index()
    names_in_doc = list(index.keys())  # thứ tự tài liệu
    doc_pos = {n: i for i, n in enumerate(names_in_doc)}
    reachable = [n.get(X_NAME) for n in engine.reachable_nodes()]
    reach_set = set(reachable)
    for n in names_in_doc:
        if n not in reach_set:
            warnings.append(f"Node '{n}' không nối vào luồng từ StartNode nên không được xuất.")

    # Cạnh (nguồn, slot) -> đích
    succ: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    preds: Dict[str, List[Tuple[str, str]]] = {n: [] for n in reachable}
    for n in reachable:
        node = index[n]
        if _local(node) == "FlowSwitch":
            succ[n] = []
            warnings.append(f"FlowSwitch '{n}' chưa hỗ trợ trong spec; xuất dạng raw (không dựng lại được).")
            for child in node.iterchildren(etree.Element):
                tname = None
                if _local(child) == "Reference":
                    tname = (child.text or "").strip()
                elif _local(child) in FLOW_NODE_TAGS:
                    tname = child.get(X_NAME)
                if tname in preds:
                    preds[tname].append((n, f"Case[{child.get(X_KEY)}]"))
            continue
        lst = []
        for slot, tgt in _successor_slots(engine, node, index):
            tname = tgt.get(X_NAME) if tgt is not None else None
            lst.append((slot, tname))
            if tname in preds:
                preds[tname].append((n, slot))
        succ[n] = lst

    start = reachable[0] if reachable else None
    order: List[str] = []
    emitted: Set[str] = set()
    remaining = set(reachable)
    while remaining:
        if not order and start:
            pick = start
        else:
            avail = [n for n in remaining if all(p in emitted for p, _ in preds[n])]
            pool = avail or list(remaining)  # vòng lặp: phá bằng node đầu tiên theo thứ tự tài liệu
            pick = min(pool, key=lambda n: doc_pos[n])
        order.append(pick)
        emitted.add(pick)
        remaining.discard(pick)

    # Đặt id dễ đọc cho từng bước
    step_ids: Dict[str, str] = {}
    used: Set[str] = set()
    counters: Dict[str, int] = {}
    steps_raw: Dict[str, Dict[str, Any]] = {}
    for n in order:
        node = index[n]
        kind = _local(node)
        if kind == "FlowDecision":
            cond = _unwrap(node.get("Condition")) or "True"
            step = {"type": "decision", "condition": cond,
                    "display_name": node.get("DisplayName") or f"If ({cond})"}
        elif kind == "FlowStep":
            act = get_activity(node)
            step = activity_to_step(act) if act is not None else None
            if step is None:
                step = _raw_step(node, act)
                warnings.append(
                    f"Node '{n}' ({_local(act) if act is not None else 'rỗng'}) chưa có builder tương ứng; xuất dạng raw."
                )
        else:
            step = {"type": "raw", "node": kind, "activity": None}
        base = {
            "point": step.get("point_code"), "link": step.get("link_name"), "shape": step.get("shape_code"),
            "fillet_arc": step.get("link_number"), "loop": step.get("loop_code"),
            "intersection": step.get("point_code"), "curve": step.get("link_number"),
            "offset": step.get("offset_code"), "get_mark_point": step.get("point_number"),
            "define_variable": f"def_{step.get('name')}", "set_variable": f"set_{step.get('name')}",
            "set_output": f"out_{step.get('name')}",
        }.get(step["type"])
        if not base or not re.fullmatch(r"[A-Za-z0-9_\-.]+", str(base)):
            prefix = {"decision": "D", "report": "R", "raw": "raw", "strip_surface": "strip",
                      "set_mark_point": "mark"}.get(step["type"], step["type"])
            counters[prefix] = counters.get(prefix, 0) + 1
            base = f"{prefix}{counters[prefix]}"
        sid, k = str(base), 2
        while sid in used:
            sid = f"{base}_{k}"
            k += 1
        used.add(sid)
        step_ids[n] = sid
        steps_raw[n] = {"id": sid, **step}

    # Mô phỏng lại cách builder nối node để quyết định parent / goto
    steps: List[Dict[str, Any]] = []
    done: Set[str] = set()
    for i, n in enumerate(order):
        step = steps_raw[n]
        incoming = sorted(
            [(p, s) for p, s in preds[n] if p in done and not s.startswith("Case[")],
            key=lambda ps: (order.index(ps[0]), ps[1]),
        )
        open_exits = sorted(
            [
                (p, s)
                for p in done
                for s, t in succ.get(p, [])
                if t is None or t not in done
            ],
            key=lambda ps: (order.index(ps[0]), ps[1]),
        )
        if i > 0:
            if not incoming:
                warnings.append(f"Bước '{step['id']}' chỉ tới được qua FlowSwitch/vòng lặp; dựng lại có thể khác.")
            if incoming and incoming != open_exits:
                labels = [
                    step_ids[p] if _local(index[p]) == "FlowStep" else f"{step_ids[p]}:{s}" for p, s in incoming
                ]
                step["parent"] = labels[0] if len(labels) == 1 else labels
        done.add(n)
        gotos = {s: step_ids[t] for s, t in succ.get(n, []) if t is not None and t in done}
        if gotos:
            step["goto"] = gotos
        steps.append(step)

    # Sắp xếp khoá cho dễ đọc: id, type, parent trước
    ordered_steps = []
    for st in steps:
        head = {k: st[k] for k in ("id", "type", "parent") if k in st}
        rest = {k: v for k, v in st.items() if k not in head}
        ordered_steps.append({**head, **rest})

    spec: Dict[str, Any] = {
        "format_version": SPEC_FORMAT_VERSION,
        "name": name,
        "civil_version": civil_version,
        "description": description,
        "parameters": _export_parameters(engine),
        "steps": ordered_steps,
    }
    if warnings:
        spec["warnings"] = warnings
    return spec


def export_spec(pkt_path: str | Path) -> Dict[str, Any]:
    """Đọc file .pkt và trả về spec khai báo (dict JSON-serializable)."""
    pkg = PktPackage.open(pkt_path)
    meta = pkg.get_metadata()
    engine = FlowchartEngine(pkg.get_xaml_text())
    detected = str(meta.get("detected_civil_version") or "2026")
    supported = [v.value for v in CivilVersion]
    version = detected if detected in supported else supported[0]
    spec = export_spec_from_engine(
        engine,
        name=meta.get("subassembly_name") or Path(pkt_path).stem,
        description=meta.get("description") or "",
        civil_version=version,
    )
    if version != detected:
        spec.setdefault("warnings", []).append(
            f"File gốc thuộc Civil 3D {detected} (chưa hỗ trợ dựng lại); spec ghi civil_version='{version}'."
        )
    return spec


# ============================================================================
# Kiểm tra spec
# ============================================================================

def _codes_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return ", ".join(f'"{str(c).strip().strip(chr(34))}"' for c in v if str(c).strip())


def _parse_parent(ref: str) -> Tuple[str, str]:
    sid, _, branch = str(ref).strip().partition(":")
    return sid.strip(), branch.strip()


def validate_spec(spec: Dict[str, Any]) -> None:
    """Kiểm tra spec trước khi dựng; raise ValueError chỉ rõ vị trí lỗi."""
    if not isinstance(spec, dict):
        raise ValueError("Spec phải là một object JSON (dict).")
    if not str(spec.get("name") or "").strip():
        raise ValueError("Spec thiếu 'name' (tên Subassembly).")
    cv = spec.get("civil_version")
    if cv is not None and str(cv) not in [v.value for v in CivilVersion]:
        raise ValueError(f"civil_version '{cv}' không hợp lệ (chỉ 2025, 2026, 2027).")

    params = spec.get("parameters") or []
    if not isinstance(params, list):
        raise ValueError("'parameters' phải là danh sách.")
    seen_p: Set[str] = set()
    dtypes = {d.value for d in ParameterDataType}
    cats = {c.value for c in ParameterCategory}
    for i, p in enumerate(params):
        where = f"parameters[{i}]"
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            raise ValueError(f"Spec không hợp lệ tại {where}: mỗi Parameter cần 'name'.")
        if p["name"] in seen_p:
            raise ValueError(f"Spec không hợp lệ tại {where}: Parameter '{p['name']}' bị trùng.")
        seen_p.add(p["name"])
        if str(p.get("data_type", "Double")) not in dtypes:
            raise ValueError(
                f"Spec không hợp lệ tại {where} ('{p['name']}'): data_type '{p.get('data_type')}' không hợp lệ. "
                f"Chọn một trong: {', '.join(sorted(dtypes))}."
            )
        if str(p.get("category", "Input")) not in cats:
            raise ValueError(
                f"Spec không hợp lệ tại {where} ('{p['name']}'): category '{p.get('category')}' "
                "phải là Input / Output / Target."
            )

    steps = spec.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("'steps' phải là danh sách.")
    kinds: Dict[str, str] = {}
    ptypes = {t.value for t in PointGeometryType}
    for i, st in enumerate(steps):
        def bad(msg: str) -> ValueError:
            sid = st.get("id") if isinstance(st, dict) else None
            return ValueError(f"Spec không hợp lệ tại steps[{i}]" + (f" (id='{sid}')" if sid else "") + f": {msg}")

        if not isinstance(st, dict):
            raise bad("mỗi bước phải là object JSON.")
        sid = str(st.get("id") or "").strip()
        if not sid:
            raise bad("thiếu 'id'.")
        if ":" in sid:
            raise bad("'id' không được chứa dấu ':'.")
        if sid in kinds:
            raise bad(f"id '{sid}' bị trùng với một bước trước.")
        stype = st.get("type")
        if stype not in STEP_FIELDS:
            raise bad(f"type '{stype}' không hợp lệ. Chọn một trong: {', '.join(STEP_FIELDS)}.")
        req, opt = STEP_FIELDS[stype]
        for f in req:
            v = st.get(f)
            if v is None or (isinstance(v, (str, list)) and len(v) == 0):
                raise bad(f"bước '{stype}' thiếu trường bắt buộc '{f}'.")
        unknown = set(st) - set(req) - set(opt) - _COMMON_FIELDS
        if unknown:
            raise bad(f"trường không hợp lệ cho bước '{stype}': {', '.join(sorted(unknown))}.")
        if stype == "point":
            pt = st.get("point_type", "DeltaX_DeltaY")
            if pt not in ptypes:
                raise bad(f"point_type '{pt}' không hợp lệ. Chọn một trong: {', '.join(sorted(ptypes))}.")
            if st.get("add_link") and not str(st.get("link_name") or "").strip():
                raise bad("add_link=true cần 'link_name'.")
        if stype in ("shape", "loop", "offset") and not isinstance(st.get("links"), list):
            raise bad("'links' phải là danh sách tên Link.")
        if stype == "report" and str(st.get("message_type", "Warning")) not in (
            "Information", "Informational", "Warning", "Error"
        ):
            raise bad("message_type phải là Informational / Warning / Error.")
        if stype == "raw":
            if st.get("node") == "FlowSwitch":
                raise bad("FlowSwitch chưa hỗ trợ dựng lại từ spec.")
            if st.get("xml"):
                try:
                    etree.fromstring(st["xml"].encode("utf-8"))
                except etree.XMLSyntaxError as exc:
                    raise bad(f"'xml' không phải XML hợp lệ: {exc}") from exc
        if stype in ("decision", "raw") and st.get("arguments"):
            raise bad(f"bước '{stype}' không nhận 'arguments'.")
        for f in ("attributes", "arguments", "goto"):
            if st.get(f) is not None and not isinstance(st.get(f), dict):
                raise bad(f"'{f}' phải là object JSON.")

        parents = st.get("parent")
        plist = [parents] if isinstance(parents, str) else (parents or [])
        if not isinstance(plist, list):
            raise bad("'parent' phải là chuỗi hoặc danh sách chuỗi.")
        if i == 0 and plist:
            raise bad("bước đầu tiên là StartNode, không có 'parent'.")
        for ref in plist:
            pid, branch = _parse_parent(ref)
            if pid not in kinds:
                raise bad(f"parent '{ref}' trỏ tới id chưa được định nghĩa ở các bước TRƯỚC.")
            if kinds[pid] == "decision":
                if branch not in ("True", "False"):
                    raise bad(f"parent '{ref}': bước '{pid}' là decision, cần ghi rõ '{pid}:True' hoặc '{pid}:False'.")
            elif branch not in ("", "Next"):
                raise bad(f"parent '{ref}': bước '{pid}' chỉ có nhánh 'Next'.")
        for slot, target in (st.get("goto") or {}).items():
            valid_slots = ("True", "False") if stype == "decision" else ("Next",)
            if slot not in valid_slots:
                raise bad(f"goto: nhánh '{slot}' không hợp lệ (chỉ {', '.join(valid_slots)}).")
            if target not in kinds and target != sid:
                raise bad(f"goto '{slot}' -> '{target}': chỉ được trỏ về bước đã định nghĩa trước đó.")
        kinds[sid] = stype


# ============================================================================
# build_from_spec
# ============================================================================

def _add_raw_step(engine: FlowchartEngine, xml: Optional[str], parent: Optional[str]) -> str:
    ref_id = engine.next_reference_id()
    step_vs_id = engine.next_viewstate_idref("FlowStep")
    flow_step = etree.Element(
        engine.qn("wf", "FlowStep"),
        attrib={engine.qn("x", "Name"): ref_id, engine.qn("sap2010", "WorkflowViewState.IdRef"): step_vs_id},
    )
    # Gắn FlowStep vào tài liệu TRƯỚC khi chép activity để các phần tử con dùng đúng prefix của file đích
    engine.get_flowchart_element().append(flow_step)
    if xml:
        src = etree.fromstring(xml.encode("utf-8"))
        root_ns = {k: v for k, v in (engine.root.nsmap or {}).items()}
        # Prefix được nhắc tới trong NỘI DUNG giá trị (VD: x:TypeArguments="asw:OffsetTarget", "{x:Null}")
        used_in_values: Set[str] = set()
        for el in src.iter(etree.Element):
            for v in list(el.attrib.values()) + [el.text or ""]:
                used_in_values.update(re.findall(r"(?<![\w.])([A-Za-z_][\w]*):[A-Za-z_]", v))
        extra_ns: Dict[str, str] = {}
        for prefix, uri in (src.nsmap or {}).items():
            if prefix is None or prefix not in used_in_values:
                continue
            if root_ns.get(prefix) == uri:
                continue
            if prefix in root_ns:
                raise ValueError(
                    f"Không chép được activity raw: prefix '{prefix}' trỏ tới '{uri}' khác với file đích."
                )
            extra_ns[prefix] = uri

        def _copy(s_el: etree._Element, parent: etree._Element, nsmap: Optional[Dict[str, str]] = None) -> None:
            if not isinstance(s_el.tag, str):
                return
            new = etree.SubElement(parent, s_el.tag, attrib=dict(s_el.attrib), nsmap=nsmap or None)
            new.text = s_el.text
            # <x:String></x:String> (chuỗi rỗng) KHÔNG được thành <x:String/>: XAML sẽ gọi constructor mặc định của String
            if s_el.text is None and len(s_el) == 0 and s_el.tag == f"{{{X_NS}}}String":
                new.text = ""
            new.tail = s_el.tail
            for c in s_el:
                _copy(c, new)

        _copy(src, flow_step, extra_ns)
        act = flow_step[len(flow_step) - 1]

        # x:Name trong activity raw (VD: Flowchart con) dùng chung namescope với file đích -> đặt lại tên mới
        renames: Dict[str, str] = {}
        for el in act.iter(etree.Element):
            old_name = el.get(X_NAME)
            if old_name:
                renames[old_name] = engine.next_reference_id()
                el.set(X_NAME, renames[old_name])
        if renames:
            for el in act.iter(etree.Element):
                if _local(el) == "Reference" and etree.QName(el).namespace == X_NS:
                    key = (el.text or "").strip()
                    if key in renames:
                        el.text = renames[key]
                for k, v in list(el.attrib.items()):
                    if "x:Reference" in v:
                        el.set(k, re.sub(
                            r"\{x:Reference\s+([^}\s]+)\s*\}",
                            lambda m: "{x:Reference " + renames.get(m.group(1), m.group(1)) + "}",
                            v,
                        ))
        idref = engine.qn("sap2010", "WorkflowViewState.IdRef")
        for el in act.iter(etree.Element):
            if el.get("ActivityId") is not None:
                el.set("ActivityId", engine.next_activity_id())
            old = el.get(idref)
            if old:
                el.set(idref, engine.next_viewstate_idref(old.rsplit("_", 1)[0]))
    x_pos, y_pos = engine.compute_next_shape_location()
    engine.attach_node_to_flowchart(new_node=flow_step, new_ref_id=ref_id, parent_ref_id=parent)
    engine.register_view_state(id_ref=step_vs_id, x=x_pos, y=y_pos, width=200.0, height=52.0)
    return ref_id


def _run_step(engine: FlowchartEngine, st: Dict[str, Any], parent: Optional[str]) -> str:
    t = st["type"]
    if t == "point":
        info = GeometryBuilder.add_point_and_link(
            engine,
            point_code=st["point_code"],
            from_point=st.get("from_point") or "Origin",
            point_type=PointGeometryType(st.get("point_type", "DeltaX_DeltaY")),
            param_1_expr=str(st.get("param_1", "0.0")),
            param_2_expr=str(st.get("param_2", "0.0")),
            point_codes_str=_codes_str(st.get("point_codes")),
            add_link=bool(st.get("add_link", False)),
            link_name=st.get("link_name") or "",
            link_codes_str=_codes_str(st.get("link_codes")),
            is_auxiliary=bool(st.get("is_auxiliary", False)),
            parent_node_id=parent,
        )
        return info["reference_id"]
    if t == "link":
        return GeometryBuilder.add_link(
            engine, link_name=st["link_name"], start_point=st["start_point"], end_point=st["end_point"],
            link_codes_str=_codes_str(st.get("link_codes")), apply_aor=bool(st.get("apply_aor", False)),
            is_auxiliary=bool(st.get("is_auxiliary", False)), parent_node_id=parent,
        )["reference_id"]
    if t == "shape":
        return GeometryBuilder.add_shape(
            engine, shape_code=st["shape_code"], link_names=list(st["links"]),
            shape_codes_str=_codes_str(st.get("shape_codes")), parent_node_id=parent,
        )["reference_id"]
    if t == "fillet_arc":
        return GeometryBuilder.add_fillet_arc(
            engine, link_number=st["link_number"], first_link=st["first_link"], second_link=st["second_link"],
            round_radius=st.get("round_radius", 0.05), end_point_name=st.get("end_point_name"),
            link_codes_str=_codes_str(st.get("link_codes")), parent_node_id=parent,
            start_point_name=st.get("start_point_name"),
        )["reference_id"]
    if t == "loop":
        return GeometryBuilder.add_loop_geometry(
            engine, loop_code=st["loop_code"], links=list(st["links"]),
            repetition_count=int(st.get("repetition_count", 1)), parent_node_id=parent,
        )["reference_id"]
    if t == "intersection":
        return GeometryBuilder.add_intersection_point(
            engine, point_code=st["point_code"], link1=st["link1"], link2=st["link2"],
            is_auxiliary=bool(st.get("is_auxiliary", False)), point_codes_str=_codes_str(st.get("point_codes")),
            parent_node_id=parent,
        )["reference_id"]
    if t == "strip_surface":
        return GeometryBuilder.add_strip_surface(
            engine, display_name=st["display_name"], depth_expr=str(st["depth"]),
            end_point_name=st["end_point_name"], end_offset=st.get("end_offset", -5.0),
            end_offset_target=st.get("end_offset_target"),
            link_codes_str=_codes_str(st.get("link_codes", "Link_VHC")), parent_node_id=parent,
            surface_target=st.get("surface_target", "EG"), start_point_name=st.get("start_point_name"),
            start_offset=None if st.get("start_offset") is None else str(st.get("start_offset")),
            link_number=st.get("link_number"),
        )["reference_id"]
    if t == "curve":
        return GeometryBuilder.add_curve(
            engine, link_number=st["link_number"], start_point=st["start_point"], end_point=st["end_point"],
            center_point=st.get("center_point"), creation_type=st.get("creation_type", "ArcGeneral"),
            arc_point=st.get("arc_point"),
            mid_ordinate_expr=None if st.get("mid_ordinate") is None else str(st.get("mid_ordinate")),
            num_increments=int(st.get("num_increments", 5)), link_codes_str=_codes_str(st.get("link_codes")),
            is_auxiliary=bool(st.get("is_auxiliary", False)), parent_node_id=parent,
        )["reference_id"]
    if t == "offset":
        return GeometryBuilder.add_offset_geometry(
            engine, offset_code=st["offset_code"], links=list(st["links"]),
            offset_distance=st.get("offset_distance", 0.15), offset_codes_str=_codes_str(st.get("offset_codes")),
            parent_node_id=parent,
        )["reference_id"]
    if t == "get_mark_point":
        return GeometryBuilder.add_get_mark_point(
            engine, point_number=st["point_number"], mark_name=st["mark_name"],
            point_codes_str=_codes_str(st.get("point_codes")), is_auxiliary=bool(st.get("is_auxiliary", False)),
            prev_offset_expr=str(st.get("prev_offset", "0")),
            prev_delta_elevation_expr=str(st.get("prev_delta_elevation", "0")),
            parent_node_id=parent,
        )["reference_id"]
    if t == "set_mark_point":
        return LogicBuilder.add_set_mark_point(
            engine, point_number=st["point_number"], mark_name=st["mark_name"], parent_node_id=parent
        )["reference_id"]
    if t == "report":
        info = LogicBuilder.add_report_message(
            engine, message_expr=str(st["message"]),
            message_type=ReportMessageType(st.get("message_type", "Warning")), condition_expr=None,
            parent_node_id=parent,
        )
        return info["report_node_id"]
    if t == "define_variable":
        return LogicBuilder.add_define_variable(
            engine, variable_name=st["name"], variable_type=st.get("var_type") or "Double",
            default_value_expr=str(st.get("default", "0.0")), parent_node_id=parent,
        )["reference_id"]
    if t == "set_variable":
        return LogicBuilder.add_set_variable_value(
            engine, variable_name=st["name"], value_expr=str(st["value"]), variable_type=st.get("var_type"),
            parent_node_id=parent,
        )["reference_id"]
    if t == "set_output":
        return LogicBuilder.add_set_output_parameter(
            engine, parameter_name=st["name"], value_expr=str(st["value"]),
            parameter_type=st.get("var_type"), parent_node_id=parent,
        )["reference_id"]
    if t == "decision":
        x, y = engine.compute_next_shape_location()
        return LogicBuilder.add_flow_decision(
            engine, condition_expr=str(st["condition"]), display_name=st.get("display_name") or "",
            parent_node_id=parent, x=x, y=y,
        )["decision_node_id"]
    if t == "raw":
        return _add_raw_step(engine, st.get("xml"), parent)
    raise ValueError(f"type '{t}' không hợp lệ.")


def apply_spec_to_engine(
    engine: FlowchartEngine, spec: Dict[str, Any], pkg: Optional[PktPackage] = None
) -> Dict[str, str]:
    """Thêm Parameter và chạy các bước của spec trên engine. Trả {step_id: __ReferenceID}."""
    for p in spec.get("parameters") or []:
        dtype = ParameterDataType(p.get("data_type", "Double"))
        cat = ParameterCategory(p.get("category", "Input"))
        default = p.get("default")
        if default is None:
            default = "-9999" if cat == ParameterCategory.TARGET else "0.0"
        default = str(default)
        disp = p.get("display_name") or ""
        desc = p.get("description") or ""
        info = ParameterBuilder.add_parameter(engine, p["name"], cat, dtype, default, disp, desc)
        if pkg is not None:
            pkg.sync_parameter_to_atc(info["parameter_name"], dtype.value, default, info["display_name"], desc)

    ids: Dict[str, str] = {}
    for i, st in enumerate(spec.get("steps") or []):
        try:
            parents = st.get("parent")
            plist = [parents] if isinstance(parents, str) else list(parents or [])
            first = None
            if plist:
                pid, branch = _parse_parent(plist[0])
                first = ids[pid] + (f":{branch}" if branch and branch != "Next" else "")
            ref = _run_step(engine, st, first)
            ids[st["id"]] = ref
            index = engine._node_index()
            for extra in plist[1:]:
                pid, branch = _parse_parent(extra)
                pnode = index[ids[pid]]
                slot = branch if branch in ("True", "False") else "Next"
                engine.set_slot_reference(pnode, slot, ref)
            for slot, target in (st.get("goto") or {}).items():
                engine.set_slot_reference(engine._node_index()[ref], slot, ids[target])
            if st.get("attributes") or st.get("arguments"):
                update_node(engine, ref, st.get("attributes"), st.get("arguments"))
        except Exception as exc:
            raise ValueError(
                f"Lỗi khi dựng steps[{i}] (id='{st.get('id')}', type='{st.get('type')}'): {exc}"
            ) from exc
    return ids


def build_from_spec(
    spec: Dict[str, Any] | str,
    output_path: str | Path,
    civil_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dựng file .pkt từ spec. spec có thể là dict, chuỗi JSON hoặc đường dẫn file .json.
    Trả về {'pkt_path', 'reference_ids': {step_id: __ReferenceID}, 'warnings'}.
    """
    spec = load_spec(spec)
    validate_spec(spec)
    version = str(civil_version or spec.get("civil_version") or "2026")
    if version not in [v.value for v in CivilVersion]:
        raise ValueError(f"civil_version '{version}' không hợp lệ (chỉ 2025, 2026, 2027).")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.building.pkt")
    try:
        pkg = PktPackage.create_from_template(
            output_path=tmp,
            subassembly_name=str(spec["name"]),
            description=str(spec.get("description") or ""),
            civil_version=CivilVersion(version),
        )
        engine = FlowchartEngine(pkg.get_xaml_text())
        ids = apply_spec_to_engine(engine, spec, pkg)
        pkg.set_xaml_text(engine.to_xaml_string())
        saved = pkg.save(target_path=out, backup=True, validate=True)
    finally:
        for p in (tmp, tmp.with_name(tmp.name + ".bak")):
            if p.exists():
                p.unlink()
    return {
        "pkt_path": str(saved),
        "reference_ids": ids,
        "civil_version": version,
        "backup_path": str(pkg.last_backup_path) if pkg.last_backup_path else None,
        "warnings": engine.warnings + pkg.warnings,
    }


def load_spec(spec: Dict[str, Any] | str) -> Dict[str, Any]:
    """Nhận dict, chuỗi JSON hoặc đường dẫn file .json và trả về dict spec."""
    if isinstance(spec, dict):
        return spec
    if not isinstance(spec, str):
        raise ValueError("Spec phải là dict, chuỗi JSON hoặc đường dẫn file .json.")
    s = spec.strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Chuỗi JSON của spec không hợp lệ: {exc}") from exc
    p = Path(s)
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy file spec: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"File spec '{p.name}' không phải JSON hợp lệ: {exc}") from exc
