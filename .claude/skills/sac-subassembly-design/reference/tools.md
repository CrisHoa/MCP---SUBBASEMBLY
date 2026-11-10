# Chữ ký tool (tóm tắt)

Nguồn chuẩn vẫn là docstring trong `src/sac_mcp/server.py`. Mọi tool sửa file nhận `pkt_path` đầu tiên và `parent_node_id`
(tuỳ chọn) cuối cùng: `None` = nối vào mọi đầu ra mở; `'__ReferenceIDn'` = chèn sau FlowStep n; `'__ReferenceIDn:True'` /
`':False'` = vào nhánh của FlowDecision n. Kết quả trả `created_reference_ids[0]` = id node vừa tạo (dùng làm parent cho node sau).

## add_point_and_link (đã đổi)

```text
add_point_and_link(pkt_path, point_code, from_point="Origin",
    point_type="DeltaX_DeltaY" | "Slope_DeltaX" | "Slope_DeltaY" | "Angle_Distance" | "Slope_To_Surface" | "Interpolate",
    param_1_expr="0.0", param_2_expr="0.0", point_codes_str="",
    add_link=True, link_name="", link_codes_str="", is_auxiliary=False,
    use_superelevation_formula=False, parent_node_id=None, allow_duplicate_link=False)
```

- `add_link=True` (mặc định) **bắt buộc** có `link_name`; thiếu → `success: false` ("add_link=True nhưng chưa truyền link_name").
- `link_name` không được trùng Link đã có (kể cả AutoLink, Curve) → lỗi "Link 'L1' đã tồn tại trong file".
  `allow_duplicate_link=True` chỉ khi cố ý tạo lại cùng mã Link ở hai nhánh Decision loại trừ nhau.
- Điểm không cần Link (điểm gốc, `AP*` dò mặt đất): `add_link=False`.
- Lưu ý: kiểm tra trùng mã chỉ có ở tool này; `add_link`, `add_curve`, `add_fillet_arc` **không** chặn trùng mã Link – tự giữ mã duy nhất.

## 8 tool hoạt động bổ sung

| Tool | Chữ ký (sau `pkt_path`) | Ghi chú |
| :--- | :--- | :--- |
| `add_flow_decision` | `condition_expr, display_name="", parent_node_id=None` | Trả id Decision (`created_reference_ids[0]`, `details.true_branch_parent_id` / `false_branch_parent_id`). Điều kiện phải là Boolean (`P2.X` trần → lỗi Tầng 3 *Option Strict On disallows implicit conversions from 'Double' to 'Boolean'*). Chèn giữa luồng (`parent_node_id='__ReferenceIDn'`): phần phía sau được nối vào **cả hai** nhánh. |
| `add_define_variable` | `variable_name, variable_type="Double"\|"Integer"\|"String"\|"YesNo", default_value_expr="0.0", parent_node_id=None` | Giá trị khởi tạo có thể là biểu thức (`"B_lan / 2"`), String cần ngoặc kép (`'"Pave"'`), YesNo dùng `Yes`/`No`. Không đặt trùng tên Parameter, không khai báo hai lần, không dùng từ khoá VB (`Next`, `Step`, `End`...) – tool chưa chặn các trường hợp này. |
| `add_set_variable` | `variable_name, value_expr, variable_type=None, parent_node_id=None` | Biến phải khai báo trước (nếu không → lỗi "Biến 'X' chưa được khai báo"). |
| `add_set_output_parameter` | `parameter_name, value_expr, parameter_type=None, parent_node_id=None` | Cần `add_parameter(param_category="Output")` trước; Input → lỗi "không phải Output Parameter". Hay đặt ở điểm hội tụ sau Decision. |
| `add_curve` | `link_number, start_point, end_point, creation_type="ArcGeneral"\|"Arc3Points"\|"ParabolaGeneral", center_point=None, arc_point=None, mid_ordinate_expr=None, num_increments=8, link_codes_str="", is_auxiliary=False, parent_node_id=None` | Mỗi kiểu cần đúng một đối số phụ: ArcGeneral→`center_point`, Arc3Points→`arc_point`, ParabolaGeneral→`mid_ordinate_expr`. |
| `add_offset_geometry` | `offset_code, links, offset_distance=0.15, offset_codes_str="", parent_node_id=None` | `links` là danh sách Link liên tiếp; `offset_distance` âm = phía dưới. Tham chiếu `O1.EndPoint` bị kiểm tra tĩnh báo `GEOMETRY_REFERENCE` (dương tính giả, Tầng 3 vẫn qua). |
| `add_set_mark_point` | `point_number, mark_name, parent_node_id=None` | Đánh dấu điểm đã tạo cho subassembly sau bắt vào. |
| `add_get_mark_point` | `point_number, mark_name, point_codes_str="", prev_offset_expr="0", prev_delta_elevation_expr="0", is_auxiliary=False, parent_node_id=None` | `mark_name` là chuỗi trần (`"EdgePoint"`); dạng `"[Bien]"` là biểu thức – biến phải tồn tại. `prev_*` chỉ dùng khi Preview trong SAC. |

## Khác

- `add_report_message(message_expr, message_type="Warning", condition_expr=None, parent_node_id=None)`: `message_type` ∈ `Informational` (bí danh `Information`), `Warning`, `Error`.
- `add_link(link_name, start_point, end_point, link_codes_str="", apply_aor=False, is_auxiliary=False, parent_node_id=None)`.
- `add_fillet_arc(link_number, first_link, second_link, round_radius=0.05, end_point_name=None, link_codes_str="", parent_node_id=None, start_point_name=None)`.
- `add_shape(shape_code, link_names, shape_codes_str="", parent_node_id=None)`.
- `add_loop_geometry(loop_code, links, repetition_count=10, parent_node_id=None)`.
- `add_intersection_point(point_code, link1, link2, is_auxiliary=False, point_codes_str="", parent_node_id=None)`.
- `add_strip_surface(display_name, depth_expr, end_point_name, end_offset=-5.0, end_offset_target=None, link_codes_str="Link_VHC", parent_node_id=None, surface_target="EG", start_point_name=None, start_offset=None, link_number=None)`.
- `remove_node`, `update_node`, `export_spec`, `build_from_spec`: xem docstring và `docs/spec_format.md`.
