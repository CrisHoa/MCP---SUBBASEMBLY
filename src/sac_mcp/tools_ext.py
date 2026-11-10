"""
Nhóm tool mở rộng cho SAC MCP Server: sửa / xoá node có sẵn và spec khai báo (JSON) của Subassembly.

Server gọi `register(mcp, _mutate_pkt, _safe_tool)` ở cuối server.py để đăng ký 4 tool:
  - remove_node, update_node (sửa file, đi qua khung _mutate_pkt: kiểm định + sao lưu .bak)
  - export_spec, build_from_spec (đọc / tạo mới, bọc bằng _safe_tool)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional

from sac_mcp.core.node_editor import remove_node as _remove_node
from sac_mcp.core.node_editor import update_node as _update_node
from sac_mcp.core.spec_builder import build_from_spec as _build_from_spec
from sac_mcp.core.spec_builder import export_spec as _export_spec
from sac_mcp.models.schemas import MutationResult


def _native_issue_warnings(pkt_path: str) -> list:
    """Chạy kiểm định 3 tầng sau khi dựng và trả các lỗi dưới dạng cảnh báo (tắt bằng SAC_MCP_NATIVE_ON_SAVE=0)."""
    if os.environ.get("SAC_MCP_NATIVE_ON_SAVE", "1") == "0":
        return []
    from sac_mcp.core.validator import PktValidator

    rep = PktValidator.validate_pkt(pkt_path, run_native_test=True)
    return [f"[{i.category}] {i.message}" for i in rep.issues if i.severity == "ERROR"]


def register(mcp: Any, mutate_pkt: Callable[..., str], safe_tool: Callable[[str], Callable]) -> None:
    """Đăng ký các tool mở rộng lên instance MCP server `mcp`."""

    @mcp.tool()
    def remove_node(pkt_path: str, node_id: str, keep_branch: Optional[Literal["True", "False"]] = None) -> str:
        """
        Xoá một node (FlowStep hoặc FlowDecision) khỏi Flowchart và tự NỐI LẠI luồng:
        mọi nhánh đang trỏ vào node bị xoá (kể cả StartNode) sẽ trỏ sang phần luồng phía sau nó.
        Hỗ trợ cả file do SAC lưu (node lồng inline) lẫn file do builder sinh (x:Reference).
        Cảnh báo nếu Point / Link mà node định nghĩa vẫn còn được activity khác tham chiếu.

        Args:
            pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
            node_id: reference_id của node cần xoá (VD: '__ReferenceID4'), xem bằng inspect_pkt.
            keep_branch: Chỉ dùng khi xoá FlowDecision có 2 nhánh khác nhau: 'True' hoặc 'False' là nhánh
                         được giữ lại để nối tiếp; nhánh còn lại bị tách khỏi luồng (có cảnh báo).
        """
        def _apply(pkg, engine):
            info = _remove_node(engine, node_id, keep_branch=keep_branch)
            cont = info["continuation_node_id"] or "(trống - cuối luồng)"
            msg = (
                f"Đã xoá {info['node_kind']} '{info['removed_node_id']}'; nối lại {len(info['rewired'])} nhánh "
                f"sang '{cont}'."
            )
            return info, msg, []

        return mutate_pkt("remove_node", pkt_path, _apply)

    @mcp.tool()
    def update_node(
        pkt_path: str,
        node_id: str,
        attributes: Optional[Dict[str, Any]] = None,
        arguments: Optional[Dict[str, Any]] = None,
        rename_references: bool = True,
    ) -> str:
        """
        Sửa một node có sẵn trong Flowchart mà không phải xoá rồi tạo lại.
        - FlowStep: sửa thuộc tính của activity bên trong (VD: CreatePoint: 'FromPoint', 'PointNumber',
          'DisplayName', 'ApplyAOR', 'PointCodes'; CreateLink: 'StartPoint', 'EndPoint', 'LinkCodes'...).
          Tên thuộc tính phải có trong danh mục activity của SAC, nếu không sẽ bị từ chối.
        - FlowDecision: chỉ sửa 'Condition' (biểu thức VB, tự bọc [..]) và 'DisplayName'.

        Args:
            pkt_path: Đường dẫn tới file .pkt cần chỉnh sửa.
            node_id: reference_id của node (VD: '__ReferenceID3'), xem bằng inspect_pkt.
            attributes: (Tùy chọn) {tên thuộc tính: giá trị}. Thuộc tính tên / mã / enum (PointNumber, FromPoint,
                        Links, CreationType, DisplayName...) ghi nguyên văn; thuộc tính số nhận số hoặc biểu thức VB
                        (tự bọc [..], VD {"OffsetDistance": "-W/10"}); null -> {x:Null}; '*Codes' nhận danh sách
                        hoặc chuỗi phân tách dấu phẩy (VD: {"PointCodes": ["Crown", "Top"]}).
                        Đổi CreationType của cung phải truyền kèm đối số tương ứng (ArcGeneral -> CenterPoint,
                        Arc3Points -> ArcPoint2, ParabolaGeneral -> MidOrdinate). Đổi VariableType của biến nội bộ
                        tự cập nhật khai báo biến và các khối Set gán cho biến đó.
            arguments: (Tùy chọn) {x:Key: giá trị} của các InArgument (VD: {"DeltaX1": "B_lan", "DeltaY1": "-t1"},
                       Slope2 / DeltaX2 cho Slope_DeltaX, SurfaceTarget3...). Biểu thức tự bọc [..], số giữ nguyên.
                       Với SetVariableValue / CustomErrorReportActivity dùng tên property: 'VariableValue', 'Message'.
                       Giá trị dạng {"value": "[Targ]", "type": "asw:OffsetTarget"} để chỉ rõ kiểu; null để xoá đối số.
            rename_references: Khi đổi tên PointNumber / LinkNumber / AutoLinkGeometryName...: True (mặc định) tự
                       cập nhật mọi tham chiếu (FromPoint, StartPoint, EndPoint, Links, FirstLink/SecondLink,
                       CenterPoint/ArcPoint2, biểu thức 'P4.X'); False chỉ cảnh báo danh sách chỗ còn dùng tên cũ.
        """
        def _apply(pkg, engine):
            info = _update_node(engine, node_id, attributes, arguments, rename_references=rename_references)
            n = len(info["changed_attributes"]) + len(info["changed_arguments"])
            msg = f"Đã cập nhật {n} giá trị của {info['activity']} trong node '{info['node_id']}'."
            return info, msg, []

        return mutate_pkt("update_node", pkt_path, _apply)

    @mcp.tool()
    @safe_tool("export_spec")
    def export_spec(pkt_path: str, output_json_path: Optional[str] = None) -> str:
        """
        Xuất một file .pkt thành SPEC khai báo dạng JSON: tên, phiên bản Civil 3D, mô tả, danh sách Parameter
        và danh sách 'steps' theo đúng thứ tự dựng (point / link / shape / decision / define_variable /
        set_variable / report ...). Nhánh của FlowDecision ghi bằng 'parent': '<id>:True' (dùng id của bước,
        không dùng __ReferenceID). Activity chưa hỗ trợ được xuất dạng {"type": "raw", ...}.
        Sửa spec rồi gọi build_from_spec để dựng lại file .pkt. Định dạng: docs/spec_format.md.

        Args:
            pkt_path: Đường dẫn tới file .pkt cần xuất.
            output_json_path: (Tùy chọn) Đường dẫn file .json để ghi spec ra đĩa (UTF-8).
        """
        spec = _export_spec(pkt_path)
        written = None
        if output_json_path:
            out = Path(output_json_path).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            written = str(out)
        return json.dumps(
            {
                "success": True,
                "action": "export_spec",
                "pkt_path": str(Path(pkt_path).resolve()),
                "output_json_path": written,
                "step_count": len(spec.get("steps", [])),
                "parameter_count": len(spec.get("parameters", [])),
                "spec": spec,
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.tool()
    @safe_tool("build_from_spec")
    def build_from_spec(
        spec_json: str,
        output_path: str,
        civil_version: Optional[Literal["2025", "2026", "2027"]] = None,
    ) -> str:
        """
        Dựng một file .pkt hoàn chỉnh từ SPEC khai báo (định dạng của export_spec, xem docs/spec_format.md):
        tạo từ template chuẩn, thêm Parameter, chạy lần lượt các bước qua builder, lưu MỘT lần rồi kiểm định 3 tầng.
        Spec sai được báo lỗi kèm vị trí 'steps[i]' trước khi ghi bất kỳ file nào.

        Args:
            spec_json: Nội dung spec dạng chuỗi JSON, HOẶC đường dẫn tới file .json chứa spec.
            output_path: Đường dẫn file .pkt sẽ tạo (ghi đè nếu đã có, bản cũ sao lưu thành .pkt.bak).
            civil_version: (Tùy chọn) Ghi đè phiên bản Civil 3D trong spec ('2025', '2026', '2027').
        """
        res = _build_from_spec(spec_json, output_path, civil_version=civil_version)
        warnings = list(res["warnings"]) + _native_issue_warnings(res["pkt_path"])
        out = MutationResult(
            success=True,
            pkt_path=res["pkt_path"],
            action="build_from_spec",
            message=(
                f"Đã dựng '{Path(res['pkt_path']).name}' từ spec ({len(res['reference_ids'])} bước, "
                f"Civil 3D {res['civil_version']})."
            ),
            created_reference_ids=list(res["reference_ids"].values()),
            details={"step_reference_ids": res["reference_ids"], "civil_version": res["civil_version"]},
            warnings=warnings,
            backup_path=res.get("backup_path"),
        )
        return json.dumps(out.model_dump(), ensure_ascii=False, indent=2)
