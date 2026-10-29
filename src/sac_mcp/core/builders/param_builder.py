"""
Builder chuyên trách thêm Input / Output / Target Parameters vào Flowchart.xaml của Subassembly Composer.
"""

from __future__ import annotations

import re
from typing import Dict
from lxml import etree

from sac_mcp.core.xaml_engine import FlowchartEngine
from sac_mcp.models.schemas import ParameterCategory, ParameterDataType


XAML_TYPE_MAP: Dict[ParameterDataType, str] = {
    ParameterDataType.DOUBLE: "x:Double",
    ParameterDataType.INTEGER: "x:Int32",
    ParameterDataType.STRING: "x:String",
    ParameterDataType.BOOLEAN: "x:Boolean",
    ParameterDataType.YES_NO: "asw:EnumType",
    ParameterDataType.GRADE: "asw:Grade",
    ParameterDataType.SLOPE: "asw:Slope",
    ParameterDataType.SIDE: "asw:EnumType",
    ParameterDataType.SUPERELEVATION: "asw:CrossSegmentType",
    ParameterDataType.SUPERELEVATION_AXIS_OF_ROTATION: "asw:CrossSegmentType",
    ParameterDataType.SLOPE_DIRECTION: "asw:SlopeDirection",
    ParameterDataType.POTENTIAL_PIVOT: "asw:PotentialPivot",
    ParameterDataType.CANT: "asw:CantParam",
    ParameterDataType.ELEVATION_TARGET: "asw:ElevationTarget",
    ParameterDataType.OFFSET_TARGET: "asw:OffsetTarget",
    ParameterDataType.SURFACE_TARGET: "asw:SurfaceTarget",
}


class ParameterBuilder:
    """Thêm hoặc cập nhật Input/Output/Target Parameter trong Flowchart.xaml."""

    @staticmethod
    def validate_param_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
        if not cleaned or cleaned[0].isdigit():
            raise ValueError(
                f"Tên Parameter '{name}' không hợp lệ. Phải bắt đầu bằng chữ cái và chỉ chứa A-Z, 0-9, _."
            )
        return cleaned

    @classmethod
    def add_parameter(
        cls,
        engine: FlowchartEngine,
        name: str,
        category: ParameterCategory,
        data_type: ParameterDataType,
        default_value: str,
        display_name: str = "",
        description: str = "",
    ) -> dict:
        param_name = cls.validate_param_name(name)
        disp = display_name.strip() or param_name
        xaml_inner_type = XAML_TYPE_MAP[data_type]

        # Xác định InArgument / OutArgument chuẩn WF4
        if category == ParameterCategory.OUTPUT:
            wf_arg_type = f"OutArgument({xaml_inner_type})"
            direction_tag = "Out"
        elif category == ParameterCategory.TARGET:
            wf_arg_type = f"InArgument({xaml_inner_type})"
            direction_tag = "Target"
        else:
            wf_arg_type = f"InArgument({xaml_inner_type})"
            direction_tag = "In"

        # 1. Đảm bảo có khối <x:Members> ở đầu <Activity>
        members_list = engine.root.xpath("./*[local-name()='Members']")
        if members_list:
            members_el = members_list[0]
        else:
            members_el = etree.Element(engine.qn("x", "Members"))
            engine.root.insert(0, members_el)

        # Kiểm tra nếu <x:Property Name="..."> đã tồn tại thì cập nhật, chưa có thì tạo mới
        existing_props = members_el.xpath(f"./*[local-name()='Property' and @Name='{param_name}']")
        if existing_props:
            prop_el = existing_props[0]
            prop_el.set("Type", wf_arg_type)
        else:
            prop_el = etree.SubElement(
                members_el,
                engine.qn("x", "Property"),
                attrib={"Name": param_name, "Type": wf_arg_type},
            )

        # Thêm attributes chuẩn SAC để hiển thị DisplayName & Description trong giao diện SAC GUI
        attrs_el_list = prop_el.xpath("./*[local-name()='Property.Attributes']")
        if attrs_el_list:
            attrs_el = attrs_el_list[0]
            for child in list(attrs_el):
                attrs_el.remove(child)
        else:
            attrs_el = etree.SubElement(prop_el, engine.qn("x", "Property.Attributes"))

        etree.SubElement(attrs_el, engine.qn("asw", "EnabledFlag2Attribute"), attrib={"EnabledFlag": "True"})
        if disp:
            etree.SubElement(attrs_el, engine.qn("asw", "DisplayName2Attribute"), attrib={"DisplayName": disp})
        if description:
            etree.SubElement(attrs_el, engine.qn("asw", "Description2Attribute"), attrib={"Description": description.strip()})

        # 2. Gán giá trị mặc định lên thẻ <Activity this:{Class}.{ParamName}="default_value">
        # (Chỉ áp dụng cho Input & Target; Output Parameter trong WF4 không gắn giá trị mặc định trên Activity root)
        short_class = engine.get_subassembly_class_short_name()
        default_attr_qname = engine.qn("this", f"{short_class}.{param_name}")
        if category != ParameterCategory.OUTPUT and default_value is not None:
            def_str = str(default_value).strip()
            if data_type == ParameterDataType.SLOPE:
                if not def_str.startswith("[new Slope"):
                    try:
                        val_num = float(def_str)
                        def_str = f"[new Slope({val_num})]"
                    except Exception:
                        def_str = f"[new Slope(0.666666666666667)]"
            elif data_type == ParameterDataType.GRADE:
                if not def_str.startswith("[new Grade"):
                    try:
                        val_num = float(def_str)
                        def_str = f"[new Grade({val_num})]"
                    except Exception:
                        def_str = f"[new Grade(0.04)]"
            elif data_type == ParameterDataType.SURFACE_TARGET:
                if not def_str.startswith("[new PreviewSurfaceTarget"):
                    def_str = f'[new PreviewSurfaceTarget("{param_name}", True, 1000, -4.417, -1000, -4.417)]'
            elif data_type == ParameterDataType.OFFSET_TARGET:
                if not def_str.startswith("[new PreviewOffsetTarget"):
                    def_str = f'[new PreviewOffsetTarget("{param_name}", True, 5)]'
            elif data_type == ParameterDataType.ELEVATION_TARGET:
                if not def_str.startswith("[new PreviewElevationTarget"):
                    def_str = f'[new PreviewElevationTarget("{param_name}", True, 0)]'
            elif data_type in (ParameterDataType.SIDE, ParameterDataType.YES_NO):
                if not def_str.startswith("[new EnumType"):
                    def_str = f'[new EnumType(0, "{def_str}", "{param_name}")]'

            engine.root.set(default_attr_qname, def_str)

        return {
            "parameter_name": param_name,
            "category": category.value,
            "wf4_type": wf_arg_type,
            "default_value": str(default_value),
            "display_name": disp,
            "description": description,
        }

