# Playbook kiểm định và sửa lỗi

Mọi thông điệp dưới đây là **thông điệp thật** sinh bằng cách cố ý làm hỏng file mẫu (làn xe mẫu A) rồi chạy
`PktValidator` / tool MCP (SAC 2026 cài trên máy).

## 1. Đọc kết quả `validate_pkt_native`

```json
{
  "pkt_path": "...", "is_valid": false,
  "tier1_opc_ok": true, "tier2_xaml_ok": true, "tier3_native_ok": false,
  "metadata": {"name": "...", "parameters_count": 11, "sac_version": "2026", "native_elapsed_ms": 12},
  "issues": [{"severity": "ERROR", "category": "VB_EXPRESSION", "message": "...", "location": "CreatePoint 'P6&L6', đối số DeltaX1"}]
}
```

- `is_valid` = không còn issue mức ERROR ở bất kỳ tầng nào. Mục tiêu: `is_valid: true` **và** `tier3_native_ok: true`.
- `tier3_native_ok: null/false` kèm `NATIVE` (INFO) "Không tìm thấy Autodesk Subassembly Composer" hoặc `NATIVE_HOST` (WARNING) → Tầng 3 **không chạy**; báo người dùng rằng biểu thức VB chưa được biên dịch thử.
- `location` của Tầng 2 là `Activity.Thuộc_tính` hoặc `__ReferenceIDn`; của `VB_EXPRESSION` là `Activity 'DisplayName', đối số Key`. DisplayName của Point có Link là `P2&L1`.
- WARNING không làm `is_valid=false` nhưng `GEOMETRY_REFERENCE` / `FLOW_UNREACHABLE` gần như luôn là lỗi thiết kế – phải xử lý.
- Thứ tự sửa: Tầng 1 (OPC/XML) → Tầng 2 ERROR → Tầng 3 → WARNING. Một lỗi Tầng 2 thường kéo theo lỗi `NATIVE_*` trùng ý; sửa lỗi Tầng 2 là hết cả hai.

## 2. Kết quả của tool sửa file

- Thành công: `success: true`, `created_reference_ids`, `details`, `warnings`, `backup_path`.
- `warnings` gồm: lỗi Tầng 3 (`"Tầng 3 [VB_EXPRESSION]: ..."`), WARNING Tầng 2 **mới** do lần sửa này (`"Tầng 2 [GEOMETRY_REFERENCE]: ..."`), auto-đặt tên (Fillet), hội tụ luồng, đồng bộ `.atc`.
  Lỗi Tầng 3 cũ được nhắc lại ở mọi lần gọi cho tới khi sửa; WARNING Tầng 2 chỉ báo một lần → vẫn chạy `validate_pkt_native` cuối cùng.
- Thất bại: `success: false`, `error_type`, `message`, `hint`, `issues`; file **không đổi**. Ví dụ thật:

```text
error_type: ValueError
message: Không tìm thấy node cha '__ReferenceID99' trong Flowchart. Dùng inspect_pkt để xem danh sách reference_id hợp lệ.

error_type: ValueError
message: Tên Parameter '1abc' không hợp lệ. Phải bắt đầu bằng chữ cái và chỉ chứa A-Z, 0-9, _.

error_type: FileNotFoundError
message: Không tìm thấy file .pkt tại đường dẫn: ...\nope.pkt
hint: Kiểm tra lại đường dẫn (nên dùng đường dẫn tuyệt đối).
```

  Khi thay đổi bị từ chối vì phát sinh lỗi Tầng 1–2 mới: `error_type: PktValidationError`, `issues` liệt kê đúng các
  category bên dưới, `hint: "Kiểm tra lại biểu thức / tên đối tượng vừa truyền vào. File gốc không bị thay đổi."`.

## 3. Từng category

### VB_EXPRESSION (ERROR, Tầng 3) – biến chưa khai báo / cú pháp
```text
Biểu thức [B_leX * 2] (trong CreatePoint 'P6&L6', đối số DeltaX1): 'B_leX' is not declared. It may be inaccessible due to its protection level.
Biểu thức [Bề_rộng] (trong CreatePoint 'P8', đối số DeltaX1): 'Bề_rộng' is not declared. ...
Biểu thức [B_lan * ] (trong CreatePoint 'P2&L1', đối số DeltaX2): Expression expected.
```
Sửa: tên gõ sai → `update_node(node_id, arguments={"DeltaX1": "B_le * 2"})` (khoá đối số = phần sau "đối số");
biến thật sự thiếu → `add_parameter` / `add_define_variable` (không cần sửa node). Tên có dấu → đổi sang tên không dấu.
Lỗi này xuất hiện ngay trong `warnings` của tool vừa thêm biểu thức – sửa luôn, đừng để tới cuối.
Khoá đối số theo `point_type`: `DeltaX1/DeltaY1`, `Slope2/DeltaX2`, `Slope5/DeltaY5`, `Slope3/SurfaceTarget3`, `Angle8/Distance8`.

### ARGUMENT_REQUIRED (ERROR, Tầng 2)
```text
CreateLink 'L5' thiếu đối số bắt buộc 'LinkNumber'.
```
Thường đi kèm `GEOMETRY_REFERENCE` ở Shape dùng Link đó. Sửa: `update_node(node_id, attributes={"LinkNumber": "L5"})`,
hoặc `remove_node` rồi tạo lại bằng tool chuẩn (tool chuẩn luôn ghi đủ đối số bắt buộc). Danh sách đối số bắt buộc:
`src/sac_mcp/native/activity_catalog.json` (VD `FilletArcActivity` cần `FirstLink`, `SecondLink`, `StartPointName`, `EndPointName`, `RoundBy`, `RoundParameter`; `StripSurfaceActivity` cần `Surface`, `Depth`, `StartOffset`, `EndOffset`, `StartPointName`, `EndPointName`, `LinkNumber`).

### ATTRIBUTE_UNKNOWN (ERROR, Tầng 2) + NATIVE_VALIDATION
```text
CreatePoint 'P1' không có thuộc tính 'Foo' (SAC sẽ không mở được file).
Cannot set unknown member 'Autodesk.SubassemblyComposer.ActivityLibrary.CreatePoint.Foo'.
```
Sửa: `update_node(node_id, attributes={"Foo": None})` để xoá (xem docstring `update_node` cho cách xoá), hoặc đổi sang thuộc tính đúng trong catalog. Hay gặp khi chép XAML từ phiên bản / tài liệu khác (VD `FilletArcActivity` **không** có `ApplyAOR`, `RoundRadius`).

### ACTIVITY_UNKNOWN (ERROR, Tầng 2) + NATIVE_ACTIVITY
```text
Activity 'CreateShapeX' không tồn tại trong Subassembly.ActivityLibrary (DisplayName='S1').
Cannot create unknown type '{clr-namespace:Autodesk.SubassemblyComposer.ActivityLibrary;assembly=Subassembly.ActivityLibrary}CreateShapeX'.
```
Sửa: `remove_node` rồi tạo lại bằng tool tương ứng. Thẻ `sac:PointGeometry`... (mock) báo riêng là `XAML_TAGS`.

### FLOW_REFERENCE (ERROR, Tầng 2) + NATIVE_REFERENCE
```text
x:Reference trỏ tới '__ReferenceID99' không tồn tại.
Unresolved reference '__ReferenceID99'.
```
Kéo theo hàng loạt `FLOW_UNREACHABLE` cho các node phía sau. Sửa: `inspect_pkt` xem `flowchart_nodes`, nối lại node trước
vào node đúng (`update_node` / `remove_node` với `keep_branch`), rồi kiểm lại.

### FLOW_UNREACHABLE (WARNING, Tầng 2)
```text
Node '__ReferenceID3' (P4&L3) không nối vào luồng từ StartNode nên sẽ không bao giờ chạy.
```
File vẫn `is_valid: true` nhưng hình học đó không bao giờ được dựng. Sửa: nối lại (tạo lại node với `parent_node_id` đúng)
hoặc `remove_node` nếu thừa. Nguyên nhân hay gặp: dùng `parent_node_id` của node đã bị xoá, sửa tay `FlowStep.Next`.

### GEOMETRY_REFERENCE (WARNING, Tầng 2)
```text
CreateLink 'L9': EndPoint='P99' tham chiếu Point chưa được tạo ở đâu trong file.
CreateShape 'S1': Links='L5' tham chiếu Link chưa được tạo ở đâu trong file.
```
Tool tạo vẫn `success: true`, cảnh báo xuất hiện một lần trong `warnings` (`Tầng 2 [GEOMETRY_REFERENCE]: ...`). Sửa: tạo Point/Link còn thiếu (trước node tham chiếu
trong luồng) hoặc `update_node(attributes={"EndPoint": "P9"})`. Chấp nhận dạng `LO1.EndPoint`, `L3.StartPoint`.
Kiểm tra chỉ xét tên có tồn tại **ở đâu đó trong file**, không xét thứ tự chạy hay nhánh Decision.

Dương tính giả đã biết: `FromPoint='O1.EndPoint'` (điểm cuối của `add_offset_geometry`) bị báo vì kiểm tra tĩnh chưa nhận
`OffsetNumber` là tên đã định nghĩa; Tầng 3 vẫn qua.

### Lỗi thường gặp với tool activity mới
```text
Biểu thức [P2.X] (trong FlowDecision 'If (P2.X)'): Option Strict On disallows implicit conversions from 'Double' to 'Boolean'.
Biểu thức [Next] (trong InternalVariableDefine 'Next <Double>'): Expression expected.      <- tên biến là từ khoá VB
Biểu thức [MarkName] (trong GetMarkPointActivity 'P4'): 'MarkName' is not declared. ...    <- mark_name dạng [..] là biểu thức
```
Điều kiện Decision phải là Boolean (`P2.X > 0`, `EG.IsValid`); đổi tên biến khác từ khoá; `mark_name` dùng chuỗi trần.

### Các lỗi khác
| Category | Ý nghĩa | Cách xử lý |
| :--- | :--- | :--- |
| `OPC`, `XML` | Thiếu file con trong gói, XML hỏng, `&` chưa escape | Tạo lại bằng `create_pkt_from_template` / `export_spec` → `build_from_spec` |
| `XAML_BOM`, `XAML_HEADER` | XAML thiếu BOM hoặc có `<?xml ...?>` | Do sửa tay; ghi lại qua bất kỳ tool sửa file nào (engine ghi chuẩn) |
| `VB_IDENTIFIER` | Tên biến trong `Flowchart.Variables` không hợp lệ (dấu, khoảng trắng) | `remove_node` biến đó, tạo lại tên không dấu |
| `ARG_EXPRESSION` | Đối số Double/Slope/Grade chứa tên biến không bọc `[...]` | Do sửa tay; tool tự bọc `[...]` |
| `NATIVE_XAML_LOAD` | SAC không nạp được XAML | Sửa các lỗi Tầng 2 trước; nếu vẫn còn, `export_spec` → `build_from_spec` |
| `NATIVE_DOCUMENT` | `document_check=True`: SubassemblyDocument (như SAC GUI) không mở được | Thường do default Parameter sai kiểu; kiểm tra `default_value` của Target/Enum |
| `NATIVE_VALIDATION` (WARNING) | Cảnh báo của WF4 | Đọc message; thường không chặn |

## 4. Những gì kiểm định KHÔNG bắt được

- Hai Link trùng cặp điểm, Shape suy biến hoặc không khép kín về hình học.
- Tham chiếu tới điểm được tạo **sau** trong luồng hoặc ở nhánh Decision khác.
- Dấu độ dốc / chiều ΔX sai ý đồ (VD đáy kết cấu đi lên).
- Kiểu biểu thức được ép ngầm (VD `Side` truyền vào đối số Double vẫn biên dịch được).

Vì vậy sau khi `is_valid: true`, luôn `inspect_pkt` đối chiếu bảng điểm/Link/Shape với bản vẽ, và đề nghị người dùng
Preview trong SAC với vài giá trị Target (đào và đắp).
