# SAC MCP Server & Toolchain (`sac-mcp-server`)

**Model Context Protocol (MCP) Server & CLI Toolchain** chuyên biệt để đọc hiểu, thiết kế, giải phẫu, kiểm định và tự động khởi tạo file **Subassembly (`.pkt`)** cho **Autodesk Civil 3D Subassembly Composer**.

- Tạo / sửa file: Civil 3D **2025, 2026, 2027**.
- Đọc / kiểm định: thêm cả file **2024**.

---

## 1. Công Cụ CLI (`sac-cli`)

Chạy qua [sac-cli.bat](sac-cli.bat) (dùng Python trong `.venv`):

```powershell
# 1. Kiểm định 3 tầng một file .pkt bất kỳ
.\sac-cli.bat validate "D:\duong\dan\file.pkt"
.\sac-cli.bat validate "D:\duong\dan\file.pkt" --doc         # thêm bước mở bằng SubassemblyDocument (~2 giây)
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
> `build --sub7` (`scripts/rebuild_7_subassemblies.py`) ghi vào **cùng thư mục** `Bo_7_Subassembly_Chuan/`
> với các file do `NativeSuiteBuilder` sinh, nhưng nội dung khác (chỉ có tham số, không có hình học).

---

## 2. Kiến Trúc Kiểm Định 3 Tầng

```text
[File .pkt] ──> Tầng 1: OPC & XML ──> Tầng 2: XAML tĩnh + ngữ nghĩa ──> Tầng 3: DLL gốc của SAC
```

1. **Tầng 1 (OPC Package & XML):**
   - Đủ 6 file định danh GUID (`.atc`, `.cfg`, `.xaml`, `.pvd`, `.emd`, `.cdmd`) và `[Content_Types].xml`.
   - XML hợp lệ, ký tự `&` đã được escape.
2. **Tầng 2 (XAML tĩnh, chạy được khi máy không cài SAC):**
   - File `.xaml` có UTF-8 BOM và không có header `<?xml...>`.
   - Tên biến là định danh VB.NET hợp lệ; biểu thức trong `<InArgument>` được bọc `[...]`; không dùng thẻ mock `sac:`.
   - Ngữ nghĩa ([semantic_checks.py](src/sac_mcp/core/semantic_checks.py)), dựa trên danh mục lấy từ `Subassembly.ActivityLibrary.dll`:

   | Mã lỗi | Mức | Ý nghĩa |
   | :--- | :--- | :--- |
   | `ACTIVITY_UNKNOWN` | ERROR | Thẻ activity không tồn tại. |
   | `ATTRIBUTE_UNKNOWN` | ERROR | Activity không có thuộc tính đó (SAC không mở được file). |
   | `ARGUMENT_REQUIRED` | ERROR | Thiếu đối số bắt buộc (`[RequiredArgument]`). |
   | `FLOW_REFERENCE` | ERROR | `x:Reference` trỏ tới node không tồn tại. |
   | `FLOW_UNREACHABLE` | WARNING | Node không nối vào luồng từ StartNode nên không bao giờ chạy. |
   | `GEOMETRY_REFERENCE` | WARNING | `FromPoint` / `StartPoint` / `Links`... tham chiếu Point / Link chưa được tạo. |

3. **Tầng 3 (DLL gốc của Subassembly Composer):** qua tiến trình nền `SacHost.exe` ([native/](src/sac_mcp/native/)).
   - Nạp XAML thành cây activity, rồi `ActivityValidationServices.Validate` **biên dịch mọi biểu thức VB**: bắt biến chưa khai báo, cú pháp hỏng, sai kiểu. Lỗi chỉ rõ vị trí, ví dụ *Biểu thức [LaneWidthh * 2] (trong CreatePoint 'P2&L1', đối số DeltaX1): 'LaneWidthh' is not declared*.
   - Dùng **đúng phiên bản SAC** theo `.cfg` của file (13.6 → 2024 … 13.9 → 2027); nếu máy không có bản đó thì dùng bản mới nhất và ghi INFO. Ghi đè bằng biến môi trường `SAC_INSTALL_DIR`.
   - Tuỳ chọn `document_check` / `--doc`: mở thêm bằng `SubassemblyDocument` giống SAC GUI, trong một AppDomain riêng (~2 giây/file).
   - Máy không cài SAC: Tầng 3 được bỏ qua kèm INFO, Tầng 1–2 vẫn chạy đủ.

**Tốc độ:** tiến trình nền được giữ lại giữa các lần gọi. Lần đầu mất khoảng 0,5 giây; các lần sau khoảng 10 ms/file (40 file mẫu: ~2,6 giây).

**Lần chạy đầu tiên:** `SacHost.cs` được biên dịch bằng `csc.exe` có sẵn của .NET Framework 4.x và lưu tại `%LOCALAPPDATA%\sac_mcp\host\<hash>\SacHost.exe`. Bản này tự biên dịch lại khi mã nguồn đổi.

---

## 3. An Toàn Khi Sửa File

Mọi tool MCP sửa file `.pkt` đều đi qua cùng một quy trình:

1. **Sửa trong bộ nhớ, ghi ra file tạm** cùng thư mục.
2. **Kiểm định Tầng 1 + 2** trên file tạm. Nếu phát sinh lỗi *mới* so với file gốc, thay đổi bị huỷ, file gốc giữ nguyên, tool trả về `success: false` kèm danh sách `issues`.
3. **Sao lưu** file gốc thành `<tên>.pkt.bak` (chỉ giữ bản gần nhất).
4. **Thay thế nguyên tử** (`os.replace`), nên không bao giờ để lại file ghi dở.

Sau khi lưu, tool chạy thêm **Tầng 3** (khi máy có SAC) và đưa lỗi biên dịch VB vào `warnings`, **không chặn** thao tác.
Lý do: khi dựng dần, việc tạm dùng một Parameter chưa thêm là bình thường. Tắt bằng `SAC_MCP_NATIVE_ON_SAVE=0`.

Kết quả JSON của tool có thêm:

- `warnings`: các vấn đề không chặn nhưng cần biết, ví dụ lỗi Tầng 3, không đồng bộ được Parameter sang `.atc`, hoặc nhiều nhánh luồng được nối hội tụ.
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

## 4. Danh Sách 27 Công Cụ MCP

Docstring của từng tool là nguồn chính xác nhất về tham số. Quy tắc chung cho các tool tạo đối tượng có tên
(Point / Link / Shape / Loop / Offset): **tên phải chưa tồn tại**. Nếu cần dùng lại cùng tên ở hai nhánh loại
trừ nhau của một FlowDecision, truyền `allow_duplicate_name=True`.

| Nhóm | Tool | Chức năng |
| :--- | :--- | :--- |
| Đọc | `inspect_pkt` | Giải nén `.pkt`, đọc metadata, Parameters, Points, Links, Shapes và sơ đồ Flowchart (kèm `reference_id`). |
| Đọc | `validate_pkt_native` | Kiểm định 3 tầng; `document_check=True` để mở thêm bằng SubassemblyDocument. |
| Đọc | `get_sac_reference_and_formulas` | Tra cứu Toolbox, quy ước đặt tên, công thức siêu cao 8 nhánh, hàm VB và API của SAC. |
| Đọc | `list_examples_and_split_catalog` | Liệt kê các file `.pkt` mẫu và bộ 7 subassembly mô-đun hóa. |
| Tạo | `create_pkt_from_template` | Tạo `.pkt` mới chuẩn 7 file cho Civil 3D 2025 / 2026 / 2027 (ghi đè thì tự lưu `.bak`). |
| Tạo | `generate_assembly_recipe` | Sinh mặt cắt mẫu `urban_road` / `highway_lane`. |
| Sửa | `add_parameter` | Thêm Input/Output/Target Parameter; Input được đồng bộ vào `<Params>` của `.atc`. |
| Sửa | `add_point_and_link` | Thêm Point / AuxPoint (6 kiểu định vị qua MCP); truyền `link_name` để tự nối Link từ `from_point`. |
| Sửa | `add_link` | Nối 2 điểm có sẵn bằng `CreateLink` / `CreateAuxLink`. |
| Sửa | `add_fillet_arc` | Bo cong góc giữa 2 Link (`FilletArcActivity`); cần `second_link`, tự đặt tên điểm đầu/cuối nếu bỏ trống. |
| Sửa | `add_loop_geometry` | Vòng lặp hình học `CreateLoop` (giật cơ nhiều tầng). |
| Sửa | `add_intersection_point` | Giao điểm 2 Link (`LinkIntersection` / `AuxIntersection`). |
| Sửa | `add_strip_surface` | Bóc hữu cơ theo chiều sâu (`StripSurfaceActivity`) trên bề mặt `surface_target` (mặc định `EG`). |
| Sửa | `add_shape` | Tạo `CreateShape` từ danh sách Link khép kín. |
| Sửa | `add_report_message` | Thêm `CustomErrorReportActivity` (`Informational` / `Warning` / `Error`), có thể kèm điều kiện `FlowDecision`. |
| Sửa | `add_curve` | Đường cong `CreateCurve` / `CreateAuxCurve`: `ArcGeneral` (cần `center_point`), `Arc3Points` (cần `arc_point`), `ParabolaGeneral` (cần `mid_ordinate_expr`). |
| Sửa | `add_offset_geometry` | Đường song song `CreateOffset` từ danh sách Link (VD lớp đệm lót). |
| Sửa | `add_get_mark_point` / `add_set_mark_point` | Đánh dấu điểm để subassembly khác trong Assembly lấy lại (`MarkName`). |
| Sửa | `add_define_variable` / `add_set_variable` | Biến nội bộ (`Double`, `Integer`, `String`, `YesNo`); chặn tên trùng Parameter / biến / từ khoá VB. |
| Sửa | `add_set_output_parameter` | Gán giá trị cho Output Parameter đã khai báo. |
| Sửa | `add_flow_decision` | Rẽ nhánh điều kiện; đặt node vào nhánh bằng `parent_node_id='<id>:True'` / `'<id>:False'`. |
| Sửa | `update_node` | Đổi thuộc tính / đối số của một node; đổi tên Point / Link sẽ cập nhật mọi tham chiếu (`rename_references`). |
| Sửa | `remove_node` | Xoá node và nối lại luồng; FlowDecision cần `keep_branch` nếu hai nhánh khác nhau. |
| Spec | `export_spec` | Xuất subassembly thành spec JSON khai báo (xem [docs/spec_format.md](docs/spec_format.md)). |
| Spec | `build_from_spec` | Dựng nguyên một file `.pkt` từ spec JSON trong một lần gọi, kiểm định trước khi lưu. |

### Claude Code Skill đi kèm

[.claude/skills/sac-subassembly-design/](.claude/skills/sac-subassembly-design/SKILL.md) hướng dẫn Claude quy trình thiết kế
subassembly bằng các tool trên, gồm: đọc bản vẽ, đặt tên và chọn kiểu tham số, thứ tự dựng, rẽ nhánh, kiểm định
và cách sửa theo từng mã lỗi. Các mẫu đã kiểm chứng (làn xe siêu cao, bó vỉa, đào/đắp, giật cơ, tường chắn,
kết cấu áo đường) nằm trong `reference/patterns.md`.

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
│   ├── update_activity_catalog.py       # Sinh lại native/activity_catalog.json từ DLL của SAC
│   ├── test_doc_ctor.ps1 / test_load_sac.ps1
├── src/sac_mcp/
│   ├── server.py                        # MCP server (23 tool + 4 tool từ tools_ext.py)
│   ├── tools_ext.py                     # remove_node, update_node, export_spec, build_from_spec
│   ├── cli.py                           # sac-cli: validate / build / test
│   ├── paths.py                         # Thư mục xuất (SAC_OUTPUT_DIR)
│   ├── models/schemas.py                # Pydantic schemas & enums
│   ├── native/
│   │   ├── SacHost.cs                   # Host .NET dùng DLL gốc của SAC (Tầng 3)
│   │   ├── host.py                      # Biên dịch, cache và quản lý tiến trình SacHost
│   │   └── activity_catalog.json        # Danh mục activity / thuộc tính / đối số bắt buộc
│   └── core/
│       ├── validator.py                 # Kiểm định 3 tầng (PktValidator)
│       ├── semantic_checks.py           # Kiểm tra ngữ nghĩa tĩnh (Tầng 2)
│       ├── node_editor.py               # Sửa / xoá node, nối lại luồng
│       ├── spec_builder.py              # export_spec / build_from_spec
│       ├── sac_enums.py                 # Nhóm EnumType chuẩn SAC (Side, Yes\No, Superelevation)
│       ├── opc_package.py               # Đọc / ghi an toàn gói .pkt
│       ├── xaml_engine.py               # Parser, mutator và mô hình đồ thị Flowchart
│       ├── version_manager.py           # Cấu hình theo phiên bản Civil 3D
│       ├── native_suite_builder.py      # Builder 8 subassembly mẫu
│       ├── knowledge_base.py / recipes.py
│       └── builders/                    # param_builder, geom_builder, logic_builder
└── tests/
```

Server **không ghi file nào khi khởi động**. Thư mục `templates/` chỉ được sinh lại khi chạy `scripts/generate_base_templates.py`.

---

## 6. Dùng Với Claude Code, Antigravity Và OpenCode

Skill `sac-subassembly-design` theo chuẩn mở Agent Skills (`SKILL.md` + frontmatter `name` / `description`),
nên cả ba công cụ đều đọc được. Mỗi công cụ quét một thư mục khác nhau:

| Công cụ | Skill đọc từ | MCP server `sac` cấu hình ở |
| :--- | :--- | :--- |
| Claude Code | `.claude/skills/` | cấu hình MCP của Claude Code |
| Google Antigravity (IDE / CLI) | `.agents/skills/` | `.agents/mcp_config.json` (workspace) |
| OpenCode | `.claude/skills/` và `.agents/skills/` | `opencode.json` (gốc dự án) |

- **Bản gốc của skill là `.claude/skills/`.** `.agents/skills/` là bản sao cho Antigravity.
  Sau khi sửa skill, chạy:
  ```powershell
  .venv\Scripts\python.exe scripts\sync_agent_skills.py
  ```
  Test `tests/test_skill_mirror.py` sẽ trượt nếu hai bản lệch nhau.
- **Skill cần MCP server mới dùng được** (nó hướng dẫn gọi 27 tool). Hai file `.agents/mcp_config.json` và
  `opencode.json` khởi động server bằng `.venv` của dự án qua đường dẫn **tuyệt đối** của máy này
  (`C:/Users/Admin/Desktop/MCP - SUBBASEMBLY`). Chuyển dự án sang máy / thư mục khác thì sửa lại đường dẫn.
- Antigravity App (bản desktop, khác IDE / CLI) chưa ghi rõ có đọc cấu hình MCP cấp workspace không;
  nếu không thấy tool, thêm mục `sac` giống `.agents/mcp_config.json` vào cấu hình MCP toàn cục của App.
- OpenCode thấy skill ở cả hai thư mục với cùng tên; nội dung giống hệt nên dùng bản nào cũng như nhau.
