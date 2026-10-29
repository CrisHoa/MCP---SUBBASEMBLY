# SAC MCP Server & Toolchain (`sac-mcp-server`)

**Model Context Protocol (MCP) Server & CLI Toolchain** chuyên biệt để đọc hiểu, thiết kế, giải phẫu, kiểm định và tự động khởi tạo file **Subassembly (`.pkt`)** cho **Autodesk Civil 3D Subassembly Composer** (tương thích toàn diện Civil 3D 2024 – 2027).

---

## 1. Công Cụ Tối Ưu Nhanh (`sac-cli`)

Hệ thống cung cấp lệnh CLI tức thì qua file thực thi [sac-cli.bat](file:///c:/Users/Admin/Desktop/MCP%20-%20SUBBASEMBLY/sac-cli.bat):

```powershell
# 1. Kiểm định 3 tầng một file .pkt bất kỳ (chỉ mất ~0.5 giây)
.\sac-cli.bat 

# 2. Dựng nhanh riêng sub và tự động kiểm định:
.\sac-cli.bat build --giaco

# 3. Dựng nhanh Bộ Subassembly chuẩn và tự động kiểm định:
.\sac-cli.bat build --sub7

# 4. DỰNG TẤT CẢ, tự động chạy kiểm định Native DLL 100% và xuất ra Desktop:
.\sac-cli.bat build --all

# 5. Chạy toàn bộ bộ kiểm thử tự động pytest (9/9 passed):
.\sac-cli.bat test
```

---

## 2. Kiến Trúc Kiểm Định 3 Tầng (`3-Tier Validation Engine`)

Mọi file `.pkt` trước khi được mở trong Subassembly Composer hay nạp vào Civil 3D đều phải vượt qua 3 tầng chốt chặn:

```text
[File .pkt] ──> Tầng 1: OPC & XML Format ──> Tầng 2: WF4 / XAML Semantics ──> Tầng 3: Native SAC Runtime Hook ──> [100% SUCCESS]
                 • Đủ 6 file GUID + Content_Types  • Biểu thức bọc [...]            • Gọi SubassemblyDocument
                 • UTF-8 BOM, không xml header     • Định danh VB.NET hợp lệ          trực tiếp từ WorkflowEditor.dll
                 • Escape &amp; trong .atc         • Native Activity Library          của Autodesk (<0.5s)
```

1. **Tầng 1 (OPC Package & XML Escaping):**
   - Đảm bảo đủ cấu trúc 6 file định danh GUID (`.atc`, `.cfg`, `.xaml`, `.pvd`, `.emd`, `.cdmd`) và `[Content_Types].xml`.
   - Kiểm tra và tự động escape XML (`&` $\rightarrow$ `&amp;`) trong các thẻ mô tả `<Description>` và `<ToolTip>`.
2. **Tầng 2 (WF4 / XAML Semantic Syntax):**
   - Đảm bảo file `.xaml` có UTF-8 BOM (`\xef\xbb\xbf`) và không có header `<?xml...>` để WF4 không từ chối nạp.
   - Kiểm tra toàn bộ đối số `<InArgument>`: bất kỳ biến hoặc biểu thức nào (như `[B_DinhKhoa]`, `[-H_ChanKhay]`, `[EG]`) **bắt buộc phải bọc trong `[...]`**.
   - Kiểm tra thẻ Activity: chỉ sử dụng các thẻ Native chính quy của Autodesk (`<asa2:CreatePoint>`, `<asa2:CreateLink>`, `<asa2:CreateShape>`).
3. **Tầng 3 (Native Autodesk Runtime Hook):**
   - Khởi tạo trực tiếp đối tượng `Autodesk.SubassemblyComposer.WorkflowEditor.SubassemblyDocument` từ thư viện DLL gốc `WorkflowEditor.dll` của Autodesk trên máy.
   - Đảm bảo Subassembly Composer GUI mở lên **100% không báo lỗi, không popup và không có hộp đỏ XAML**.

---

## 3. Cấu Trúc Thư Mục Repository

```text
MCP - SUBBASEMBLY/
├── .gitignore                           # Bỏ qua virtualenv, cache, file rác và temp
├── pyproject.toml                       # Khai báo package & CLI scripts (sac-cli, sac-validate)
├── sac-cli.bat                          # File batch chạy lệnh CLI nhanh 1 cú click
├── README.md                            # Hướng dẫn chi tiết
├── scripts/
│   ├── build_giaco_taluy_phuyen.py      # Dựng sub Gia Cố Mái Taluy Phú Yên chuẩn bản vẽ DWG
│   ├── rebuild_7_subassemblies.py       # Dựng 7 subassembly mô-đun hóa độc lập (sạch chữ visual)
│   ├── split_visual_infra.py            # Giải phẫu & bóc tách gói lớn SACVisualInfra.pkt
│   ├── generate_base_templates.py       # Sinh base templates Civil 3D 2024 - 2027
│   ├── test_doc_ctor.ps1                # Script PowerShell kiểm thử native SubassemblyDocument
│   └── test_load_sac.ps1                # Script PowerShell kiểm thử DynamicActivity XAML
├── src/
│   └── sac_mcp/
│       ├── cli.py                       # CLI Handler đa năng (validate, build, test)
│       ├── server.py                    # FastMCP Server với 12 công cụ (thêm validate_pkt_native)
│       ├── models/schemas.py            # Schemas Pydantic & Enums
│       └── core/
│           ├── validator.py             # Engine kiểm định 3 tầng (PktValidator)
│           ├── version_manager.py       # Quản lý phiên bản Civil 3D 2024 - 2027 & escape XML
│           ├── opc_package.py           # Đóng mở gói .pkt chuẩn OPC
│           ├── xaml_engine.py           # Parser & Mutation engine cho WF4 XAML
│           └── builders/
│               ├── param_builder.py     # Nạp tham số chuẩn In/Out/Target
│               ├── geom_builder.py      # Tạo Point, Link, Shape & tự động bọc [...] biểu thức
│               └── logic_builder.py     # CustomErrorReportActivity chuẩn Autodesk
└── tests/
    ├── test_giaco_taluy.py              # Test kiểm định hình học & 3-tier validator
    └── test_pkt_workflow.py             # Test chu trình vòng đời PKT từ 2024 - 2027
```

---

## 4. Danh Sách 12 Công Cụ MCP (`Tools`)

| STT | Tên Tool | Mô Tả Chức Năng |
| :-: | :--- | :--- |
| 1 | `validate_pkt_native` | **(Mới)** Kiểm định 3 tầng file `.pkt` trước khi xuất bản hoặc mở bằng Subassembly Composer. |
| 2 | `inspect_pkt` | Giải nén `.pkt`, đọc toàn bộ metadata, trích xuất Points, Links, Shapes, Parameters. |
| 3 | `create_pkt_from_template` | Tạo mới file `.pkt` theo chuẩn 7-file native của Autodesk theo phiên bản (`2024` - `2027`). |
| 4 | `add_parameter` | Thêm Input/Output/Target Parameter vào `.xaml` và tự động đồng bộ vào mục `<Params>` của `.atc`. |
| 5 | `add_point_and_link` | Thêm Point, tự động tạo Link và bọc dấu `[...]` cho mọi biến số/công thức. |
| 6 | `add_link` | Nối 2 điểm hình học bằng đối tượng `CreateLink`. |
| 7 | `add_shape` | Tạo `CreateShape` từ danh sách các Link khép kín. |
| 8 | `add_report_message` | Thêm `CustomErrorReportActivity` chuẩn Autodesk để cảnh báo khi áp sai điều kiện. |
| 9 | `get_knowledge_base` | Tra cứu tiêu chuẩn thiết kế Hoa_C3D, mã Code mặt đường, lề, vỉa hè. |
| 10 | `generate_assembly_recipe` | Sinh kịch bản trắc ngang đường cao tốc / đô thị đầy đủ. |
| 11 | `list_examples_and_split_catalog` | Liệt kê các file ví dụ thực tế và bộ 7 subassembly mô-đun hóa. |
| 12 | `split_visual_infra_module` | Bóc tách từng mô-đun độc lập từ file thư viện cũ. |
