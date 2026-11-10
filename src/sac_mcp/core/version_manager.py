"""
Quản lý cấu hình đa phiên bản Autodesk Civil 3D Subassembly Composer (2024 - 2027).
Chuẩn hóa theo đúng cấu trúc 7-file thực tế của Autodesk Subassembly Composer:
  - [Content_Types].xml
  - <guid>.atc  (AutoCAD Tool Palette & Parameter Metadata)
  - <guid>.cfg  (SAC Version Configuration: 13.6=2024, 13.7=2025, 13.8=2026, 13.9=2027)
  - <guid>.xaml (WF4 Flowchart với Autodesk.SubassemblyComposer.ActivityLibrary)
  - <guid>.pvd  (PreviewData cho Superelevation & Rail Cant)
  - <guid>.emd  (EnumData)
  - <guid>.cdmd (CodeData cho Point/Link/Shape codes)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import uuid
from xml.sax.saxutils import escape as xml_escape
from typing import Dict

from sac_mcp.models.schemas import CivilVersion


@dataclass(frozen=True)
class CivilVersionSpec:
    """Thông số kỹ thuật bên trong gói .pkt tương ứng với từng phiên bản Civil 3D."""
    civil_version: CivilVersion
    product_version: str        # VersionNumber trong .cfg (13.7.1516.0 = 2025, 13.8.1516.0 = 2026, 13.9.1516.0 = 2027)
    packet_version: str         # Phiên bản hiển thị
    dotnet_target: str          # Từ C3D 2025 trở đi dùng .NET 8.0
    sac_assembly_name: str      # Assembly CLR trong XAML namespace
    template_filename: str


VERSION_SPECS: Dict[CivilVersion, CivilVersionSpec] = {
    CivilVersion.C3D_2025: CivilVersionSpec(
        civil_version=CivilVersion.C3D_2025,
        product_version="13.7.1516.0",
        packet_version="2025.0",
        dotnet_target="net8.0-windows",
        sac_assembly_name="Subassembly.ActivityLibrary",
        template_filename="base_2025.pkt",
    ),
    CivilVersion.C3D_2026: CivilVersionSpec(
        civil_version=CivilVersion.C3D_2026,
        product_version="13.8.1516.0",
        packet_version="2026.0",
        dotnet_target="net8.0-windows",
        sac_assembly_name="Subassembly.ActivityLibrary",
        template_filename="base_2026.pkt",
    ),
    CivilVersion.C3D_2027: CivilVersionSpec(
        civil_version=CivilVersion.C3D_2027,
        product_version="13.9.1516.0",
        packet_version="2027.0",
        dotnet_target="net8.0-windows",
        sac_assembly_name="Subassembly.ActivityLibrary",
        template_filename="base_2027.pkt",
    ),
}


class VersionManager:
    """Quản lý nhận diện phiên bản và cung cấp nội dung XML chuẩn Native SAC (2025 - 2027)."""

    TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

    @classmethod
    def get_spec(cls, version: str | CivilVersion) -> CivilVersionSpec:
        if isinstance(version, str):
            version = CivilVersion(version)
        return VERSION_SPECS[version]

    @classmethod
    def get_template_path(cls, version: str | CivilVersion) -> Path:
        spec = cls.get_spec(version)
        return cls.TEMPLATES_DIR / spec.template_filename

    @classmethod
    def sanitize_subassembly_name(cls, name: str) -> str:
        """Chuẩn hóa tên Subassembly hợp lệ làm định danh .NET."""
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
        if not cleaned:
            return "CustomSubassembly"
        if cleaned[0].isdigit():
            cleaned = f"Sub_{cleaned}"
        return cleaned

    @classmethod
    def detect_version_from_cfg_or_settings(cls, xml_text: str) -> str:
        """Phát hiện phiên bản Civil 3D từ nội dung <guid>.cfg hoặc PacketSettings.xml."""
        if "13.9" in xml_text or "2027" in xml_text:
            return "2027"
        if "13.8" in xml_text or "2026" in xml_text:
            return "2026"
        if "13.7" in xml_text or "2025" in xml_text:
            return "2025"
        if "13.6" in xml_text or "2024" in xml_text:
            return "2024"
        return "2026"

    # ========================================================================
    # Các hàm sinh bộ 7 file XML chuẩn Native Autodesk Subassembly Composer
    # ========================================================================

    @staticmethod
    def build_content_types_xml() -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="atc" ContentType="" />'
            '<Default Extension="cfg" ContentType="" />'
            '<Default Extension="xaml" ContentType="" />'
            '<Default Extension="pvd" ContentType="" />'
            '<Default Extension="emd" ContentType="" />'
            '<Default Extension="cdmd" ContentType="" />'
            '</Types>'
        )

    @classmethod
    def build_cfg_xml(cls, version: str | CivilVersion = CivilVersion.C3D_2026) -> str:
        spec = cls.get_spec(version)
        return (
            '<?xml version="1.0"?>\n'
            '<Configuration xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '  <CreatedWith>\n'
            '    <ProductName>Autodesk Subassembly Composer</ProductName>\n'
            '    <Version>ForVail</Version>\n'
            f'    <VersionNumber>{spec.product_version}</VersionNumber>\n'
            '  </CreatedWith>\n'
            '</Configuration>\n'
        )

    @classmethod
    def build_atc_xml(
        cls,
        guid_hex: str,
        subassembly_name: str,
        description: str = "",
    ) -> str:
        safe_name = cls.sanitize_subassembly_name(subassembly_name)
        cat_id = f"{{{uuid.uuid4()}}}"
        tool_id = f"{{{uuid.uuid4()}}}"
        desc_text = xml_escape(description or safe_name)
        return (
            '<?xml version="1.0"?>\n'
            '<Category xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            f'  <ItemID idValue="{cat_id}" />\n'
            '  <Properties>\n'
            '    <ItemName>Category1</ItemName>\n'
            '    <Images>\n'
            '      <Image cx="93" cy="123" />\n'
            '    </Images>\n'
            '  </Properties>\n'
            '  <CustomData />\n'
            '  <Source />\n'
            '  <Palettes />\n'
            '  <Packages />\n'
            '  <Tools>\n'
            f'    <Tool Name="{safe_name}">\n'
            f'      <ItemID idValue="{tool_id}" />\n'
            '      <Properties>\n'
            f'        <ItemName>{safe_name}</ItemName>\n'
            '        <Images>\n'
            '          <Image cx="64" cy="64" />\n'
            '        </Images>\n'
            f'        <Description>{desc_text}</Description>\n'
            f'        <ToolTip>{desc_text}\\nVersion: 0.1</ToolTip>\n'
            '        <Help>\n'
            '          <HelpFile />\n'
            '          <HelpCommand />\n'
            '          <HelpData />\n'
            '        </Help>\n'
            '      </Properties>\n'
            '      <Source />\n'
            '      <StockToolRef idValue="{7F55AAC0-0256-48D7-BFA5-914702663FDE}" />\n'
            '      <Data>\n'
            '        <AeccDbSubassembly>\n'
            '          <GeometryGenerateMode>UseDotNet</GeometryGenerateMode>\n'
            f'          <DotNetClass Assembly="{guid_hex}.xaml">Subassembly.{safe_name}</DotNetClass>\n'
            '          <Version>0.1</Version>\n'
            '          <Params>\n'
            '            <Side DataType="long" TypeInfo="16" DisplayName="Side" Description="Side">0'
            '<Enum><Left DisplayName="Left">1</Left><Right DisplayName="Right">0</Right></Enum></Side>\n'
            '          </Params>\n'
            '        </AeccDbSubassembly>\n'
            '        <Units>m</Units>\n'
            '      </Data>\n'
            '    </Tool>\n'
            '  </Tools>\n'
            '  <StockTools />\n'
            '</Category>\n'
        )

    @staticmethod
    def build_pvd_xml() -> str:
        return (
            '<?xml version="1.0"?>\n'
            '<PreviewData xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '  <Superelevation>\n'
            '    <CrossSlopes>\n'
            '      <PreviewCrossSlope CrossSegmentType="LeftInsideLane" Slope="-0.02" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="LeftInsideShoulder" Slope="-0.05" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="LeftOutsideLane" Slope="-0.02" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="LeftOutsideShoulder" Slope="-0.05" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="RightInsideLane" Slope="-0.02" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="RightInsideShoulder" Slope="-0.05" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="RightOutsideLane" Slope="-0.02" IsDefined="true" />\n'
            '      <PreviewCrossSlope CrossSegmentType="RightOutsideShoulder" Slope="-0.05" IsDefined="true" />\n'
            '    </CrossSlopes>\n'
            '  </Superelevation>\n'
            '  <Cant>\n'
            '    <CantParams>\n'
            '      <PreviewCantParam Name="CantPivotType" Value="CenterLine" />\n'
            '      <PreviewCantParam Name="LeftRail" Value="" />\n'
            '      <PreviewCantParam Name="LeftRailDeltaElevation" Value="0" />\n'
            '      <PreviewCantParam Name="RightRail" Value="" />\n'
            '      <PreviewCantParam Name="RightRailDeltaElevation" Value="0" />\n'
            '    </CantParams>\n'
            '  </Cant>\n'
            '</PreviewData>\n'
        )

    @staticmethod
    def build_emd_xml() -> str:
        return (
            '<?xml version="1.0"?>\n'
            '<EnumData xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '  <EnumDatas>\n'
            '    <Groups />\n'
            '    <DefinedVariables />\n'
            '  </EnumDatas>\n'
            '</EnumData>\n'
        )

    @staticmethod
    def build_cdmd_xml() -> str:
        return (
            '<?xml version="1.0"?>\n'
            '<CodeData xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '  <CodeItems>\n'
            '    <CodeItem Name="Top" Point="false" Link="true" Shape="false" Category="Standard">\n'
            '      <OldPoint>false</OldPoint>\n'
            '      <OldLink>false</OldLink>\n'
            '      <OldShape>false</OldShape>\n'
            '    </CodeItem>\n'
            '    <CodeItem Name="Datum" Point="false" Link="true" Shape="false" Category="Standard">\n'
            '      <OldPoint>false</OldPoint>\n'
            '      <OldLink>false</OldLink>\n'
            '      <OldShape>false</OldShape>\n'
            '    </CodeItem>\n'
            '  </CodeItems>\n'
            '</CodeData>\n'
        )

    @classmethod
    def build_base_flowchart_xaml(
        cls,
        subassembly_name: str = "Subassembly",
        version: str | CivilVersion = CivilVersion.C3D_2026,
    ) -> str:
        """
        Tạo file <guid>.xaml gốc chuẩn Native WF4 của Autodesk Subassembly Composer
        (tương thích 100% với các file thực tế trong examples/).
        """
        return """<Activity mc:Ignorable="sads sap sap2010" x:Class="Subassembly" this:Subassembly.Side="[new EnumType(0, &quot;Right&quot;, &quot;Side&quot;)]"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:asa="clr-namespace:Autodesk.SubassemblyComposer.API;assembly=Subassembly.API"
 xmlns:asa1="clr-namespace:Autodesk.SubassemblyComposer.ActivityLibrary;assembly=Subassembly.ActivityLibrary"
 xmlns:asa2="clr-namespace:Autodesk.SubassemblyComposer.ActivityLibrary;assembly=Subassembly.ActivityLibrary"
 xmlns:asw="clr-namespace:Autodesk.SubassemblyComposer.WorkflowEngine;assembly=Subassembly.WorkflowEngine"
 xmlns:av="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:mva="clr-namespace:Microsoft.VisualBasic.Activities;assembly=System.Activities"
 xmlns:s="clr-namespace:System;assembly=mscorlib"
 xmlns:sa="clr-namespace:System.Activities;assembly=System.Activities"
 xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"
 xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
 xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
 xmlns:sac="clr-namespace:Autodesk.Civil.SubassemblyComposer.workflows;assembly=Autodesk.Civil.SubassemblyComposer.workflows"
 xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
 xmlns:this="clr-namespace:"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <x:Members>
    <x:Property Name="Geometry" Type="InOutArgument(asw:Geometry)" />
    <x:Property Name="SubassemblyErrorCenter" Type="InOutArgument(asw:SubassemblyErrorCenter)" />
    <x:Property Name="SubassemblyRunMode" Type="InOutArgument(asw:SubassemblyRunMode)" />
    <x:Property Name="Side" Type="InArgument(asw:EnumType)">
      <x:Property.Attributes>
        <asw:EnabledFlag2Attribute EnabledFlag="True" />
      </x:Property.Attributes>
    </x:Property>
  </x:Members>
  <sap:VirtualizedContainerService.HintSize>654.4,676.8</sap:VirtualizedContainerService.HintSize>
  <mva:VisualBasic.Settings>Assembly references and imported namespaces serialized as XML namespaces</mva:VisualBasic.Settings>
  <Flowchart sap:VirtualizedContainerService.HintSize="614.4,636.8" mva:VisualBasic.Settings="Assembly references and imported namespaces serialized as XML namespaces">
    <Flowchart.Variables>
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(41, &quot;AwayFromCrown&quot;)]" Modifiers="ReadOnly" Name="AwayFromCrown" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(1, &quot;Left&quot;)]" Modifiers="ReadOnly" Name="Left" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(20, &quot;LeftInsideLane&quot;)]" Modifiers="ReadOnly" Name="LeftInsideLane" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(21, &quot;LeftInsideShoulder&quot;)]" Modifiers="ReadOnly" Name="LeftInsideShoulder" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(22, &quot;LeftOutsideLane&quot;)]" Modifiers="ReadOnly" Name="LeftOutsideLane" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(23, &quot;LeftOutsideShoulder&quot;)]" Modifiers="ReadOnly" Name="LeftOutsideShoulder" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(11, &quot;No&quot;)]" Modifiers="ReadOnly" Name="No" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(-1, &quot;None&quot;)]" Modifiers="ReadOnly" Name="None" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(0, &quot;Right&quot;)]" Modifiers="ReadOnly" Name="Right" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(24, &quot;RightInsideLane&quot;)]" Modifiers="ReadOnly" Name="RightInsideLane" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(25, &quot;RightInsideShoulder&quot;)]" Modifiers="ReadOnly" Name="RightInsideShoulder" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(26, &quot;RightOutsideLane&quot;)]" Modifiers="ReadOnly" Name="RightOutsideLane" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(27, &quot;RightOutsideShoulder&quot;)]" Modifiers="ReadOnly" Name="RightOutsideShoulder" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(30, &quot;Supported&quot;)]" Modifiers="ReadOnly" Name="Supported" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(40, &quot;TowardsCrown&quot;)]" Modifiers="ReadOnly" Name="TowardsCrown" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(31, &quot;Unsupported&quot;)]" Modifiers="ReadOnly" Name="Unsupported" />
      <Variable x:TypeArguments="asw:EnumType" Default="[new EnumType(10, &quot;Yes&quot;)]" Modifiers="ReadOnly" Name="Yes" />
    </Flowchart.Variables>
    <sap:WorkflowViewStateService.ViewState>
      <scg:Dictionary x:TypeArguments="x:String, x:Object">
        <x:Boolean x:Key="IsExpanded">False</x:Boolean>
        <av:Point x:Key="ShapeLocation">270,2.5</av:Point>
        <av:Size x:Key="ShapeSize">60,75.2</av:Size>
      </scg:Dictionary>
    </sap:WorkflowViewStateService.ViewState>
    <Flowchart.StartNode>
      <x:Null />
    </Flowchart.StartNode>
  </Flowchart>
  <sap2010:WorkflowViewState.ViewStateManager>
    <sap2010:ViewStateManager />
  </sap2010:WorkflowViewState.ViewStateManager>
</Activity>
"""
