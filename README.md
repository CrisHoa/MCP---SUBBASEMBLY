# SAC MCP Server & Toolchain (`sac-mcp-server`)

**Model Context Protocol (MCP) Server & CLI Toolchain** chuyên biệt để đọc hiểu, thiết kế, giải phẫu, kiểm định và tự động khởi tạo file **Subassembly (`.pkt`)** cho **Autodesk Civil 3D Subassembly Composer**.

- Tạo / sửa file: Civil 3D **2025, 2026, 2027**.
- Đọc / kiểm định: thêm cả file **2024**.

---

## 1. Công Cụ CLI (`sac-cli`)

Chạy qua [sac-cli.bat](sac-cli.bat) (dùng Python trong `.venv`):

```powershell
# 1. Kiểm định 3 tầng một file .pkt bất kỳ (~1 giây / file khi chạy cả Tầng 3)
.\sac-cli.bat validate "D:\duong\dan\file.pkt"
.\sac-cli.bat validate "D:\duong\dan\file.pkt" --no-native   # bỏ qua Tầng 3

# 2. Dựng sub Gia Cố Mái Taluy Phú Yên và tự động kiểm định
.\sac-cli.bat build --giaco

# 3. Dựng Bộ 7 Subassembly chuẩn và tự động kiểm định
.\sac-cli.bat build --sub7

# 4. Dựng tất cả, kiểm định và xuất ra thư mục chỉ định
.\sac-cli.bat build --all --out "D:\Xuat\SUB PHU YEN"

# 5. Chạy bộ kiểm thử pytest
.\sac-cli.bat test
```

**Thư mục xuất** của lệnh `build` được chọn theo thứ tự:

1. `--out`
2. Biến môi trường `SAC_OUTPUT_DIR`
3. Mặc định `~/Desktop/SUB PHU YEN`

> Lưu ý: `build --giaco` / `--sub7` cũng ghi lại các file mẫu tương ứng trong `examples/`.

---

## 2. Kiến Trúc Kiểm Định 3 Tầng

```text
[File .pkt] ──> Tầng 1: OPC & XML ──> Tầng 2: WF4 / XAML ──> Tầng 3: Native SAC (WorkflowEditor.dll)
```

1. **Tầng 1 (OPC Package & XML Escaping):**
   - Đủ 6 file định danh GUID (`.atc`, `.cfg`, `.xaml`, `.pvd`, `.emd`, `.cdmd`) và `[Content_Types].xml`.
   - XML hợp lệ, ký tự `&` đã được escape.
2. **Tầng 2 (WF4 / XAML Semantic Syntax):**
   - File `.xaml` có UTF-8 BOM và không có header `<?xml...>`.
   - Tên biến là định danh VB.NET hợp lệ.
   - Đối số `<InArgument>` dạng biến / biểu thức được bọc trong `[...]`.
   - Không dùng thẻ mock `sac:`.
3. **Tầng 3 (Native Autodesk Runtime Hook):** khởi tạo `SubassemblyDocument` từ `WorkflowEditor.dll` của Subassembly Composer cài trên máy.

> ⚠️ **Giới hạn hiện tại của Tầng 3:** bước này chỉ xác nhận SAC **mở được gói** (bắt được ví dụ `x:Reference` trỏ tới node không tồn tại).
>
> Nó **chưa** dựng activity và **chưa** biên dịch biểu thức VB, nên **không** phát hiện:
> - Tag activity sai tên.
> - Biến chưa khai báo.
> - Cú pháp VB hỏng.
>
> Vẫn cần mở thử trong Subassembly Composer để chắc chắn. Nâng cấp phần này nằm trong Giai đoạn 1 của lộ trình.

---

## 3. An Toàn Khi Sửa File

Mọi tool MCP sửa file `.pkt` đều đi qua cùng một quy trình:

1. **Sửa trong bộ nhớ, ghi ra file tạm** cùng thư mục.
2. **Kiểm định Tầng 1 + 2** trên file tạm. Nếu phát sinh lỗi *mới* so với file gốc, thay đổi bị huỷ, file gốc giữ nguyên, tool trả về `success: false` kèm danh sách `issues`.
3. **Sao lưu** file gốc thành `<tên>.pkt.bak` (chỉ giữ bản gần nhất).
4. **Thay thế nguyên tử** (`os.replace`), nên không bao giờ để lại file ghi dở.

Kết quả JSON của tool có thêm:

- `warnings`: các vấn đề không chặn nhưng cần biết, ví dụ không đồng bộ được Parameter sang `.atc`, hoặc nhiều nhánh luồng được nối hội tụ.
- `backup_path`: đường dẫn bản sao lưu.

Khi lỗi, tool trả về JSON `{ "success": false, "error_type", "message", "hint", "issues" }` thay vì traceback.

### Nối node vào Flowchart (`parent_node_id`)

| Giá trị | Hành vi |
| :--- | :--- |
| *(bỏ trống)* | Nối node mới vào **mọi đầu ra mở** của luồng (FlowStep chưa có Next, nhánh True/False còn trống), tức tất cả nhánh hội tụ về node mới. Flowchart rỗng thì node mới thành StartNode. |
| `__ReferenceIDn` | **Chèn** ngay sau FlowStep `n`. Phần luồng phía sau được nối tiếp vào node mới, không bị đứt. |
| `__ReferenceIDn:True` / `:False` | Chèn vào nhánh True / False của FlowDecision `n`. |

`add_report_message` có `condition_expr` sẽ tạo `FlowDecision`:

- Nhánh **True** chạy ReportMessage rồi đi tiếp.
- Nhánh **False** đi tiếp ngay.
- Các node thêm sau đó chạy ở **cả hai** trường hợp.

---

## 4. Danh Sách 15 Công Cụ MCP

| Nhóm | Tool | Chức năng |
| :--- | :--- | :--- |
| Đọc | `inspect_pkt` | Giải nén `.pkt`, đọc metadata, Parameters, Points, Links, Shapes và sơ đồ Flowchart (kèm `reference_id`). |
| Đọc | `validate_pkt_native` | Kiểm định 3 tầng (xem giới hạn của Tầng 3 ở mục 2). |
| Đọc | `get_sac_reference_and_formulas` | Tra cứu Toolbox, quy ước đặt tên, công thức siêu cao 8 nhánh, hàm VB và API của SAC. |
| Đọc | `list_examples_and_split_catalog` | Liệt kê các file `.pkt` mẫu và bộ 7 subassembly mô-đun hóa. |
| Tạo | `create_pkt_from_template` | Tạo `.pkt` mới chuẩn 7 file cho Civil 3D 2025 / 2026 / 2027 (ghi đè thì tự lưu `.bak`). |
| Tạo | `generate_assembly_recipe` | Sinh mặt cắt mẫu `urban_road` / `highway_lane`. |
| Sửa | `add_parameter` | Thêm Input/Output/Target Parameter; Input được đồng bộ vào `<Params>` của `.atc`. |
| Sửa | `add_point_and_link` | Thêm Point / AuxPoint (6 kiểu định vị qua MCP) và tự nối Link. |
| Sửa | `add_link` | Nối 2 điểm có sẵn bằng `CreateLink` / `CreateAuxLink`. |
| Sửa | `add_fillet_arc` | Bo cong góc giữa các Link (`FilletArcActivity`). |
| Sửa | `add_loop_geometry` | Vòng lặp hình học `CreateLoop` (giật cơ nhiều tầng). |
| Sửa | `add_intersection_point` | Giao điểm 2 Link (`LinkIntersection` / `AuxIntersection`). |
| Sửa | `add_strip_surface` | Bóc hữu cơ theo chiều sâu (`StripSurfaceActivity`). |
| Sửa | `add_shape` | Tạo `CreateShape` từ danh sách Link khép kín. |
| Sửa | `add_report_message` | Thêm `CustomErrorReportActivity`, có thể kèm điều kiện `FlowDecision`. |

---

## 5. Cấu Trúc Thư Mục

```text
MCP - SUBBASEMBLY/
├── pyproject.toml / sac-cli.bat / README.md
├── scripts/
│   ├── build_giaco_taluy_phuyen.py      # Dựng sub Gia Cố Mái Taluy Phú Yên
│   ├── rebuild_7_subassemblies.py       # Dựng bộ 7 subassembly mô-đun hóa
│   ├── split_visual_infra.py            # Bóc tách gói SACVisualInfra.pkt
│   ├── generate_base_templates.py       # Sinh lại templates/base_2025..2027.pkt (ghi đè)
│   ├── test_doc_ctor.ps1 / test_load_sac.ps1
├── src/sac_mcp/
│   ├── server.py                        # MCP server (15 tool)
│   ├── cli.py                           # sac-cli: validate / build / test
│   ├── paths.py                         # Thư mục xuất (SAC_OUTPUT_DIR)
│   ├── models/schemas.py                # Pydantic schemas & enums
│   └── core/
│       ├── validator.py                 # Kiểm định 3 tầng (PktValidator)
│       ├── opc_package.py               # Đọc / ghi an toàn gói .pkt
│       ├── xaml_engine.py               # Parser, mutator và mô hình đồ thị Flowchart
│       ├── version_manager.py           # Cấu hình theo phiên bản Civil 3D
│       ├── native_suite_builder.py      # Builder 8 subassembly mẫu
│       ├── knowledge_base.py / recipes.py
│       └── builders/                    # param_builder, geom_builder, logic_builder
└── tests/
```

Server **không ghi file nào khi khởi động**. Thư mục `templates/` chỉ được sinh lại khi chạy `scripts/generate_base_templates.py`.
