# Định dạng SPEC khai báo của Subassembly (`export_spec` / `build_from_spec`)

Spec là một file JSON mô tả **toàn bộ** một Subassembly: thông tin chung, danh sách Parameter và
danh sách các **bước dựng** (`steps`) theo đúng thứ tự. Mỗi bước tương ứng 1-1 với một lời gọi builder
(`add_point_and_link`, `add_link`, `add_shape`, `add_flow_decision`...). Quy trình điển hình:

1. `export_spec(pkt_path, output_json_path)` — xuất file `.pkt` có sẵn ra JSON.
2. Sửa JSON (thêm / bớt / đổi bước, đổi Parameter).
3. `build_from_spec(spec_json, output_path)` — dựng lại `.pkt` từ đầu (template chuẩn → Parameter → các bước →
   lưu một lần → kiểm định 3 tầng).

**Dạng chuẩn hoá.** `export_spec` luôn xuất spec ở dạng chuẩn hoá: các trường có giá trị mặc định được ghi đầy đủ
(VD `from_point`, `point_type`, `param_1`/`param_2` của point; `var_type` của biến; `display_name` của decision;
`creation_type`, `num_increments` của curve...), trường tuỳ chọn rỗng / false bị lược bỏ, biểu thức bỏ ngoặc `[...]`.
Vì vậy:

- Với spec đã ở dạng chuẩn hoá (VD spec do `export_spec` sinh ra rồi sửa), `export_spec(build_from_spec(spec)) == spec`
  (đã kiểm chứng trên 9 cấu kiện của `NativeSuiteBuilder` và file dựng bằng mọi tool của server).
- Với spec viết tay thiếu trường, kết quả xuất lại bằng spec đó **sau khi điền giá trị mặc định** (ngữ nghĩa giống hệt).
- Phần `raw` chỉ giống về ngữ nghĩa: XML được đánh lại `ActivityId` / `x:Name` nên chuỗi `xml` có thể khác.

## 1. Cấu trúc cấp cao

| Khoá | Kiểu | Ý nghĩa |
|---|---|---|
| `format_version` | số | Phiên bản định dạng (hiện tại `1`). |
| `name` | chuỗi | Tên Subassembly (bắt buộc; ký tự lạ được đổi thành `_`). |
| `civil_version` | `"2025"` / `"2026"` / `"2027"` | Phiên bản Civil 3D. Tool `build_from_spec` có tham số ghi đè. |
| `description` | chuỗi | Mô tả. |
| `parameters` | danh sách | Xem mục 2. |
| `steps` | danh sách | Xem mục 3–5. |
| `warnings` | danh sách chuỗi | Chỉ có trong kết quả `export_spec` (phần không xuất được chính xác). Bị bỏ qua khi dựng. |

## 2. Parameter

```json
{"name": "LaneSlope", "category": "Input", "data_type": "Grade", "default": "-0.02",
 "display_name": "Độ dốc ngang (%)", "description": "Độ dốc mái mặt đường"}
```

- `category`: `Input` | `Output` | `Target`.
- `data_type`: `Double`, `Integer`, `String`, `Boolean`, `YesNo`, `Grade`, `Slope`, `Side`, `Superelevation`,
  `SuperelevationAxisOfRotation`, `SlopeDirection`, `PotentialPivot`, `Cant`, `ElevationTarget`, `OffsetTarget`,
  `SurfaceTarget`.
- `default`: giá trị dạng rút gọn (`"-0.02"` cho Grade/Slope, `"Right"` cho Side) hoặc biểu thức XAML đầy đủ
  (`"[new PreviewOffsetTarget(\"Targ\", True, 0.5)]"`). `null` = mặc định của builder (Target dùng Preview chuẩn,
  Output không có giá trị mặc định).
- Template chuẩn luôn có sẵn Parameter `Side`; khai báo lại trong spec chỉ cập nhật nó.

## 3. Bước dựng — trường chung

| Khoá | Bắt buộc | Ý nghĩa |
|---|---|---|
| `id` | có | Định danh do spec đặt (duy nhất, không chứa `:`). `export_spec` dùng mã hình học (`P3`, `L5`, `S1`), `D1`.. cho decision, `R1`.. cho report, `def_X` / `set_X` / `out_X` cho biến. |
| `type` | có | Loại bước (mục 4). |
| `parent` | không | Nơi nối node mới vào luồng (mục 5). |
| `goto` | không | `{"Next" \| "True" \| "False": "<id bước TRƯỚC>"}` — nhánh quay ngược (vòng lặp). |
| `attributes` | không | Ghi đè thuộc tính activity mà builder không có tham số riêng, VD `{"ApplyAOR": "True"}`, `{"DisplayName": "..."}`. Tên phải có trong danh mục activity của SAC. |
| `arguments` | không | Ghi đè / thêm InArgument theo `x:Key`, VD `{"OffsetTarget2": {"value": "[Targ_Off]", "type": "asw:OffsetTarget"}}` (giá trị đơn nếu kiểu là `x:Double`). |
| `comment` | không | Ghi chú tự do, bị bỏ qua. |

Biểu thức VB viết **không** có ngoặc vuông (`"-LaneWidth"`, `"B_day / 2.0"`); builder tự bọc `[...]`. Danh sách Code
(`point_codes`, `link_codes`, `shape_codes`...) là mảng chuỗi không kèm dấu nháy.

## 4. Các loại bước

| `type` | Bắt buộc | Tuỳ chọn (mặc định) | Builder |
|---|---|---|---|
| `point` | `point_code` | `from_point` (`Origin`), `point_type` (`DeltaX_DeltaY`), `param_1`, `param_2` (`"0.0"`), `point_codes`, `add_link` (false), `link_name`, `link_codes`, `is_auxiliary` (false) | `GeometryBuilder.add_point_and_link` |
| `link` | `link_name`, `start_point`, `end_point` | `link_codes`, `apply_aor`, `is_auxiliary` | `add_link` |
| `shape` | `shape_code`, `links` | `shape_codes` | `add_shape` |
| `fillet_arc` | `link_number`, `first_link`, `second_link` | `round_radius` (0.05), `start_point_name`, `end_point_name`, `link_codes` | `add_fillet_arc` |
| `loop` | `loop_code`, `links` | `repetition_count` (1) | `add_loop_geometry` |
| `intersection` | `point_code`, `link1`, `link2` | `is_auxiliary`, `point_codes` | `add_intersection_point` |
| `strip_surface` | `display_name`, `depth`, `end_point_name` | `end_offset`, `end_offset_target`, `surface_target` (`EG`), `start_point_name`, `start_offset`, `link_number`, `link_codes` | `add_strip_surface` |
| `curve` | `link_number`, `start_point`, `end_point` | `creation_type` (`ArcGeneral` cần `center_point`; `Arc3Points` cần `arc_point`; `ParabolaGeneral` cần `mid_ordinate`), `num_increments`, `link_codes`, `is_auxiliary` | `add_curve` |
| `offset` | `offset_code`, `links` | `offset_distance` (0.15), `offset_codes` | `add_offset_geometry` |
| `get_mark_point` | `point_number`, `mark_name` | `point_codes`, `is_auxiliary`, `prev_offset` (`0`), `prev_delta_elevation` (`0`) | `add_get_mark_point` |
| `set_mark_point` | `point_number`, `mark_name` | | `LogicBuilder.add_set_mark_point` |
| `report` | `message` | `message_type` (`Warning`; `Informational` / `Warning` / `Error`) | `add_report_message` (không điều kiện) |
| `define_variable` | `name` | `var_type` (`Double` / `Integer` / `String` / `YesNo`), `default` (`"0.0"`) | `add_define_variable` |
| `set_variable` | `name`, `value` | `var_type` (bỏ trống = suy ra từ khai báo biến) | `add_set_variable_value` |
| `set_output` | `name`, `value` | `var_type` (bỏ trống = suy ra từ kiểu Output Parameter) | `add_set_output_parameter` |
| `decision` | `condition` | `display_name` (`If (<condition>)`) | `add_flow_decision` |
| `raw` | | `activity`, `xml` | Chép nguyên văn XAML activity vào một FlowStep mới |

`point_type`: `DeltaX_DeltaY`, `Slope_DeltaX`, `Slope_DeltaY`, `Slope_To_Surface` (param_2 = Target bề mặt),
`DeltaX_On_Surface`, `Angle_DeltaX`, `Angle_DeltaY`, `Angle_Distance`, `Interpolate`.

Report có điều kiện: viết thành 2 bước `decision` + `report` với `"parent": "<D>:True"` (xem ví dụ).

`raw`: `export_spec` dùng cho activity chưa có builder (VD `Sequence`, `StripSurfaceAuxActivity`). Khi dựng lại,
XAML được chép nguyên (đánh lại `ActivityId`). `FlowSwitch` chưa hỗ trợ — `build_from_spec` báo lỗi.

## 5. Nối luồng: `parent`

- **Bỏ trống**: node mới được nối vào **mọi đầu ra đang mở** của luồng (giống builder khi không truyền
  `parent_node_id`). Bước đầu tiên luôn là `StartNode`. Sau một `decision` chưa có nhánh, bước tiếp theo không có
  `parent` sẽ nhận **cả hai** nhánh True/False; sau `decision` + `report` ở nhánh True, bước tiếp theo nhận
  `D:False` và `R.Next` (luồng hội tụ).
- **`"<id>"`**: chèn ngay sau FlowStep `<id>` (nhánh `Next`; phần luồng cũ phía sau được nối tiếp vào node mới).
- **`"<id>:True"` / `"<id>:False"`**: chèn vào nhánh của decision `<id>` (bắt buộc ghi rõ nhánh).
- **Danh sách** `["D2:False", "P3"]`: node có nhiều nhánh đổ vào; phần tử đầu dùng để chèn, các phần tử sau được
  trỏ thẳng tới node mới.

`parent` / `goto` chỉ được tham chiếu tới bước đã khai báo **phía trước**.

## 6. Lỗi kiểm tra spec

Spec được kiểm tra hết trước khi ghi file. Lỗi báo dạng:

```
Spec không hợp lệ tại steps[3] (id='P4'): bước 'point' thiếu trường bắt buộc 'point_code'.
Spec không hợp lệ tại steps[9] (id='R1'): parent 'D9:True' trỏ tới id chưa được định nghĩa ở các bước TRƯỚC.
Spec không hợp lệ tại parameters[2] ('LaneSlope'): data_type 'Percent' không hợp lệ. ...
```

Lỗi phát sinh khi chạy builder được báo `Lỗi khi dựng steps[i] (id=..., type=...): ...` và file đích không bị ghi.

## 7. Ví dụ đầy đủ: mặt đường 2 làn có 1 Shape

```json
{
  "format_version": 1,
  "name": "Duong2Lan",
  "civil_version": "2026",
  "description": "Mặt đường 2 làn xe dốc 2 mái, có 1 lớp kết cấu áo đường",
  "parameters": [
    {"name": "Side", "category": "Input", "data_type": "Side", "default": "Right",
     "display_name": "Side", "description": ""},
    {"name": "LaneWidth", "category": "Input", "data_type": "Double", "default": "3.5",
     "display_name": "Bề rộng 1 làn (m)", "description": "Bề rộng mỗi làn xe"},
    {"name": "LaneSlope", "category": "Input", "data_type": "Grade", "default": "-0.02",
     "display_name": "Độ dốc ngang (%)", "description": "Độ dốc mái mặt đường"},
    {"name": "PaveDepth", "category": "Input", "data_type": "Double", "default": "0.3",
     "display_name": "Chiều dày áo đường (m)", "description": ""}
  ],
  "steps": [
    {"id": "P1", "type": "point", "point_code": "P1", "from_point": "Origin",
     "point_type": "DeltaX_DeltaY", "param_1": "0.0", "param_2": "0.0", "point_codes": ["Crown"]},
    {"id": "P2", "type": "point", "point_code": "P2", "from_point": "P1",
     "point_type": "Slope_DeltaX", "param_1": "LaneSlope", "param_2": "-LaneWidth",
     "point_codes": ["ETW"], "add_link": true, "link_name": "L1", "link_codes": ["Top", "Pave"]},
    {"id": "P3", "type": "point", "point_code": "P3", "from_point": "P1",
     "point_type": "Slope_DeltaX", "param_1": "LaneSlope", "param_2": "LaneWidth",
     "point_codes": ["ETW"], "add_link": true, "link_name": "L2", "link_codes": ["Top", "Pave"]},
    {"id": "P4", "type": "point", "point_code": "P4", "from_point": "P1",
     "point_type": "DeltaX_DeltaY", "param_1": "0.0", "param_2": "-PaveDepth"},
    {"id": "P5", "type": "point", "point_code": "P5", "from_point": "P2",
     "point_type": "DeltaX_DeltaY", "param_1": "0.0", "param_2": "-PaveDepth",
     "add_link": true, "link_name": "L3", "link_codes": ["Pave"]},
    {"id": "P6", "type": "point", "point_code": "P6", "from_point": "P3",
     "point_type": "DeltaX_DeltaY", "param_1": "0.0", "param_2": "-PaveDepth",
     "add_link": true, "link_name": "L4", "link_codes": ["Pave"]},
    {"id": "L5", "type": "link", "link_name": "L5", "start_point": "P5", "end_point": "P6",
     "link_codes": ["Datum"]},
    {"id": "S1", "type": "shape", "shape_code": "S1", "links": ["L1", "L2", "L4", "L5", "L3"],
     "shape_codes": ["Pave1"]},
    {"id": "D1", "type": "decision", "condition": "LaneWidth <= 0", "display_name": "Bề rộng làn <= 0?"},
    {"id": "R1", "type": "report", "parent": "D1:True", "message": "Bề rộng làn phải lớn hơn 0",
     "message_type": "Error"}
  ]
}
```

Dựng: `build_from_spec(spec_json="C:/spec/Duong2Lan.json", output_path="C:/out/Duong2Lan.pkt")`. Kết quả qua
kiểm định 3 tầng; `export_spec` của file vừa dựng trả lại đúng spec trên. Một bước thêm vào cuối (không `parent`)
sẽ được nối từ cả `D1:False` lẫn `R1`.

## 8. Giới hạn

- Toạ độ khối trên màn hình Flowchart (ViewState) không lưu trong spec; builder tự xếp lại.
- `Sequence`, `FlowSwitch` và activity chưa có builder chỉ xuất dạng `raw` (Sequence dựng lại được, FlowSwitch thì không).
- Node không nối vào luồng từ StartNode không được xuất (có cảnh báo trong `warnings`).
- File gốc của Civil 3D cũ hơn 2025 được xuất với `civil_version: "2025"` (có cảnh báo).
