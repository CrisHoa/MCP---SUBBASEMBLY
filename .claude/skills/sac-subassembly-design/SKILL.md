---
name: sac-subassembly-design
description: Thiết kế, tạo mới, sửa, kiểm tra subassembly Autodesk Civil 3D Subassembly Composer (SAC, file .pkt) bằng MCP server sac-mcp-server. Dùng khi người dùng muốn dựng / sửa / kiểm định mặt cắt ngang (cross-section), làn xe, siêu cao, lề, taluy đào đắp, giật cơ, rãnh biên, bó vỉa, vỉa hè, tường chắn, kết cấu áo đường, vét hữu cơ, phui đào cống, hoặc khi nhắc tới Subassembly Composer, file .pkt, Point / Link / Shape, Target Parameter, "design a subassembly", "create/fix/validate a .pkt", "SAC flowchart", "cross section for Civil 3D".
---

# Thiết kế Subassembly (.pkt) với `sac-mcp-server`

Skill này hướng dẫn dựng một Subassembly SAC **từ bản vẽ mặt cắt tới file `.pkt` qua được kiểm định 3 tầng**
(`validate_pkt_native` → `is_valid: true`, `tier3_native_ok: true`).

Tài liệu tham khảo (chỉ mở khi cần):
- [reference/patterns.md](reference/patterns.md): 6 mẫu dựng hình dạng chuỗi lời gọi tool (làn siêu cao, bó vỉa bo cong, taluy đào/đắp có Decision, giật cơ bằng Loop, tường chắn 3 Shape, áo đường nhiều lớp).
- [reference/naming_and_types.md](reference/naming_and_types.md): quy ước đặt tên H_/B_/i_, bảng kiểu dữ liệu Parameter, mã Point/Link/Shape.
- [reference/validation_playbook.md](reference/validation_playbook.md): đọc kết quả kiểm định và sửa từng loại lỗi, kèm thông điệp lỗi thật.
- [reference/tools.md](reference/tools.md): chữ ký tóm tắt của mọi tool, đặc biệt 8 tool activity bổ sung và quy tắc `link_name` của `add_point_and_link`.

## Khi nào dùng

- Người dùng gửi bản vẽ / mô tả mặt cắt ngang và muốn có subassembly cho Civil 3D 2025 / 2026 / 2027.
- Sửa, bổ sung, gỡ lỗi một file `.pkt` có sẵn (kể cả file 2024 – chỉ đọc / kiểm định).
- Kiểm tra vì sao SAC không mở được file hoặc Preview báo lỗi.

## Bộ tool

| Nhóm | Tool |
| :--- | :--- |
| Đọc / tra cứu | `inspect_pkt`, `validate_pkt_native`, `get_sac_reference_and_formulas`, `list_examples_and_split_catalog`, `export_spec` |
| Tạo mới | `create_pkt_from_template`, `generate_assembly_recipe`, `build_from_spec` |
| Tham số / biến | `add_parameter`, `add_define_variable`, `add_set_variable`, `add_set_output_parameter` |
| Hình học | `add_point_and_link`, `add_link`, `add_shape`, `add_fillet_arc`, `add_curve`, `add_offset_geometry`, `add_intersection_point`, `add_loop_geometry`, `add_strip_surface`, `add_get_mark_point`, `add_set_mark_point` |
| Luồng | `add_flow_decision`, `add_report_message` |
| Sửa / xoá | `update_node`, `remove_node` |

Chữ ký tóm tắt: [reference/tools.md](reference/tools.md); **docstring của tool là nguồn chuẩn**.
`build_from_spec` / `export_spec` dùng spec JSON khai báo, định dạng mô tả trong `docs/spec_format.md`.

## Quy trình thiết kế

### 1. Làm rõ mặt cắt từ bản vẽ
Trước khi gọi tool, lập **bảng điểm**: mã điểm, điểm gốc, cách định vị (ΔX/ΔY, dốc + ΔX, dốc tới mặt đất...),
offset / cao độ tương đối, Point Code. Xác định Origin (thường là mép gắn vào subassembly trước, hoặc tim).
Liệt kê Link (cặp điểm + Link Code) và Shape (chuỗi Link khép kín + Shape Code). Hỏi lại người dùng khi thiếu
kích thước, phía áp dụng (trái/phải) hoặc cần điều kiện đào/đắp.

### 2. Chọn tham số
- Tên theo quy ước: `H_` chiều cao/dày, `B_` bề rộng, `i_` độ dốc (xem naming_and_types.md). Chỉ dùng A-Z, 0-9, `_`; **không dấu tiếng Việt** (tiếng Việt để ở `display_name`).
- Kiểu dữ liệu đúng: độ dốc ngang dạng % → `Grade` (-0.02); mái dốc taluy dạng tỷ lệ → `Slope`; kích thước → `Double`.
- Bề mặt / offset / cao độ khống chế → `param_category="Target"` với `SurfaceTarget` / `OffsetTarget` / `ElevationTarget`.
- `Side` **đã có sẵn** trong template; chỉ gọi `add_parameter(name="Side", data_type="Side", default_value="Right")` khi muốn đổi mặc định / tên hiển thị.

### 3. Tạo file
`create_pkt_from_template(output_path, subassembly_name, description, civil_version)` – hỏi người dùng dùng Civil 3D bản nào
(`"2025" | "2026" | "2027"`, mặc định tool là 2025). Dùng đường dẫn tuyệt đối.

### 4. Thêm Parameter TRƯỚC hình học tham chiếu tới nó
Tool vẫn cho thêm Point dùng biến chưa có (Tầng 3 chỉ báo `warnings`), nhưng thêm Parameter trước giúp mọi
bước sau sạch cảnh báo và dễ phát hiện gõ sai tên.

### 5. Dựng Point / Link theo thứ tự luồng
- Mỗi lời gọi `add_point_and_link` thêm 1 FlowStep; luồng chạy **đúng thứ tự gọi**. Điểm được tham chiếu (`from_point`, `start_point`, `LO1.EndPoint`...) phải được tạo ở bước **trước** đó – thứ tự sai chỉ lộ lỗi khi chạy Preview / Corridor.
- Mặc định `add_link=True` và khi đó **bắt buộc** `link_name` duy nhất (thiếu hoặc trùng → `success: false`). Điểm đầu tiên và mọi điểm không cần Link (kể cả `AP*` dò mặt đất) truyền `add_link=False`. Cùng mã Link ở hai nhánh Decision loại trừ: `allow_duplicate_link=True`.
- Điểm phụ trợ (`is_auxiliary=True`, mã `AP*`/`AL*`) để tính toán, không xuất ra Civil 3D.
- Làn chịu siêu cao: `point_type="Slope_DeltaX"`, `param_1_expr="i_lan"`, `use_superelevation_formula=True` (cần Parameter `UseSuperelevation` kiểu `Superelevation`).
- `Slope_To_Surface`: `param_1_expr` = dốc, `param_2_expr` = **tên Target bề mặt** (VD `EG`).

### 6. Shape từ vòng Link khép kín
Nối các cạnh còn thiếu bằng `add_link(start_point, end_point)`, rồi `add_shape(link_names=[...])` theo thứ tự đi vòng quanh
miền (không cần cùng chiều nhưng phải khép kín). Mỗi lớp vật liệu = 1 Shape với Shape Code riêng.

### 7. Điều kiện (Decision)
- `add_flow_decision(condition_expr=...)` trả về id `__ReferenceIDn`. Node thuộc nhánh nào thì truyền
  `parent_node_id="__ReferenceIDn:True"` hoặc `":False"` cho node **đầu tiên** của nhánh; các node tiếp theo của
  cùng nhánh truyền `parent_node_id` = reference_id của node vừa tạo (hoặc dùng `created_reference_ids`).
- **Bỏ trống `parent_node_id` sẽ nối node mới vào MỌI đầu ra mở** (cả hai nhánh hội tụ). Chỉ bỏ trống khi thật sự muốn hội tụ sau Decision; tool sẽ báo `warnings: "Luồng có 2 đầu ra mở ... nối hội tụ"`.
- `add_report_message(condition_expr=...)` cũng tạo một FlowDecision: nhánh True báo lỗi rồi đi tiếp, nhánh False đi tiếp ngay, nên các node thêm sau đó sẽ nhận cảnh báo hội tụ – điều đó là bình thường. Đặt report kiểm tra đầu vào ở **cuối** để tránh cảnh báo.
- Điểm cùng tên có thể được tạo ở cả hai nhánh (VD P5 chân taluy đào và đắp).

### 8. Kiểm định và sửa
`validate_pkt_native(pkt_path)` sau khi hoàn tất (và bất cứ khi nào tool trả `warnings` bắt đầu bằng `Tầng 3`).
Đích: `is_valid: true` và `tier3_native_ok: true`; WARNING `GEOMETRY_REFERENCE` / `FLOW_UNREACHABLE` cũng phải xử lý.
Thêm `document_check=True` ở lần kiểm cuối để mở thử bằng `SubassemblyDocument` như SAC GUI.

| Category | Mức | Nguyên nhân thường gặp | Cách sửa |
| :--- | :--- | :--- | :--- |
| `VB_EXPRESSION` | ERROR (Tầng 3) | Biến chưa khai báo / gõ sai, cú pháp hỏng, tên có dấu | `add_parameter` / `add_define_variable` cho biến thiếu, hoặc `update_node(arguments=...)` sửa biểu thức |
| `ARGUMENT_REQUIRED` | ERROR | Activity thiếu đối số bắt buộc (`LinkNumber`, `SecondLink`, `Surface`...) | `update_node(attributes=...)` bổ sung, hoặc `remove_node` rồi tạo lại bằng tool đúng |
| `ATTRIBUTE_UNKNOWN` | ERROR | Thuộc tính không có trong activity (thường do sửa XAML tay) | `update_node` xoá/đổi tên thuộc tính; tra `src/sac_mcp/native/activity_catalog.json` |
| `ACTIVITY_UNKNOWN` | ERROR | Thẻ activity không tồn tại | `remove_node`, tạo lại bằng tool tương ứng |
| `FLOW_REFERENCE` | ERROR | `x:Reference` trỏ tới node không còn | `remove_node` / `update_node` nối lại; kiểm tra bằng `inspect_pkt` |
| `FLOW_UNREACHABLE` | WARNING | Node không nối từ StartNode, không bao giờ chạy | Nối lại với `parent_node_id` đúng hoặc `remove_node` |
| `GEOMETRY_REFERENCE` | WARNING | `FromPoint` / `StartPoint` / `Links` trỏ tên chưa tạo | Tạo điểm/link đó trước, hoặc sửa tên bằng `update_node` |
| `NATIVE_ACTIVITY`, `NATIVE_REFERENCE`, `NATIVE_VALIDATION`, `NATIVE_XAML_LOAD`, `NATIVE_DOCUMENT` | ERROR (Tầng 3) | Bản gốc của lỗi Tầng 2 phía trên, hoặc lỗi chỉ SAC thấy | Sửa lỗi Tầng 2 tương ứng trước; còn lại xem playbook |
| `NATIVE_HOST` (WARNING) / `NATIVE` (INFO) | – | Không chạy được / không có SAC trên máy | Tầng 3 bị bỏ qua: báo người dùng, không coi là đã qua |

Chi tiết và thông điệp mẫu: [reference/validation_playbook.md](reference/validation_playbook.md).

### 9. Rà soát
`inspect_pkt` để đối chiếu danh sách Parameters / Points / Links / Shapes và sơ đồ luồng (`flowchart_nodes` với
`reference_id`, `next_reference_id`, `true_reference_id` / `false_reference_id`) với bảng điểm ở bước 1.
`export_spec` để xuất spec JSON, đọc lại / chỉnh / dựng lại bằng `build_from_spec`. Báo cho người dùng đường dẫn file,
kết quả kiểm định và các giả định đã dùng.

## Lưu ý quan trọng (rút ra từ dự án)

- **An toàn khi sửa:** mọi tool sửa file ghi `<tên>.pkt.bak` (chỉ giữ bản gần nhất) và **từ chối** thay đổi nếu sinh lỗi Tầng 1–2 *mới*: kết quả `success: false` + `issues`, file gốc giữ nguyên. Đọc `message` / `issues`, sửa tham số rồi gọi lại – đừng sửa XAML tay.
- **Lỗi Tầng 3 chỉ là `warnings`**, không chặn: cho phép thêm Parameter sau, nhưng trước khi kết thúc mọi biến phải tồn tại (chạy `validate_pkt_native`).
- **WARNING Tầng 2 mới phát sinh** (`GEOMETRY_REFERENCE`, `FLOW_UNREACHABLE`) được trả trong `warnings` dạng `"Tầng 2 [GEOMETRY_REFERENCE]: ..."` nhưng **không chặn**: `add_link(end_point="P99")` vẫn `success: true`. Đọc `warnings` sau mỗi lời gọi.
- **`parent_node_id` bỏ trống = nối vào mọi đầu ra mở.** `__ReferenceIDn` = chèn ngay sau FlowStep n (phần sau được nối tiếp vào node mới). `__ReferenceIDn:True/False` = vào nhánh của Decision n.
- **Target / Output không nằm trong `.atc`**: chỉ Input Parameter được đồng bộ vào `<Params>` của `.atc`; Target / Output chỉ có trong XAML – đúng như SAC, không phải lỗi.
- **Tham số enum** (`Side`, `YesNo`, `Superelevation`): truyền tên lựa chọn (`"Left"`, `"No"`, `"RightOutsideLane"`), tool tự ghi `[new EnumType(mã, "tên", "nhóm")]` đúng mã SAC (Side Right=0/Left=1, Yes=10/No=11, Superelevation 20..27, None=-1). Trong biểu thức: `Side=Left`, `Opt=Yes`.
- **FilletArc cần `second_link`**: hai Link (thường `AL*` phụ trợ) gặp nhau tại góc cần bo; nên đặt `start_point_name` / `end_point_name` (VD `P2`, `P3`) để nối tiếp, nếu không tool tự đặt `<link>_Start` / `<link>_End` và báo warning.
- **StripSurface cần `surface_target`** = tên Target Parameter kiểu `SurfaceTarget` (mặc định `EG`) – phải thêm Target đó trước.
- **Thứ tự tham chiếu điểm quan trọng khi chạy**: Point/Link chỉ dùng được sau khi FlowStep tạo nó đã chạy trên đúng nhánh. Tham chiếu chéo nhánh Decision sẽ lỗi lúc Preview dù kiểm định tĩnh vẫn qua.
- **AutoLink luôn nối `from_point` → điểm mới.** Điểm đáy lớp dựng thẳng đứng từ điểm mặt sẽ tạo cạnh *đứng*, không phải cạnh đáy; cạnh đáy giữa hai điểm đáy phải tạo bằng `add_link`. Đừng tạo hai Link trùng cặp điểm (Shape suy biến – kiểm định tĩnh không bắt được; `tests/test_suite_geometry.py::shape_closure_errors` kiểm tra Shape khép kín từ kết quả `inspect_pkt`). Không tạo lại một mã Point đã có trên cùng nhánh.
- `LO1.EndPoint`, `L3.StartPoint` là tham chiếu hợp lệ (điểm cuối vòng lặp / đầu Link).
- Biến (`add_define_variable`): không trùng tên Parameter (sẽ che Parameter), không khai báo hai lần, không dùng từ khoá VB (`Next`, `Step`...) – tool chưa chặn.
- `add_report_message`: `message_type` là `"Informational"` (chấp nhận bí danh `"Information"`), `"Warning"` hoặc `"Error"`.
- Tên Link/Point trong `link_names`, `from_point`: chuỗi trần (`"L1"`), còn Code: chuỗi có ngoặc kép, nhiều code cách bằng dấu phẩy (`'"Top", "Pave"'`).
- Biểu thức VB: `IF(cond, a, b)`, `Math.Abs(...)`, `P1.Y`, `L1.Slope`, `EG.IsValid`... tra bằng `get_sac_reference_and_formulas(topic="api_functions")`.
- Mẫu có sẵn để tham khảo: `generate_assembly_recipe` (`urban_road`, `highway_lane`) và các hàm `build_0x_*` trong `src/sac_mcp/core/native_suite_builder.py`.
