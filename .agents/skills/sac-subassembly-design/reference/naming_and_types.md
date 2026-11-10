# Quy ước đặt tên và kiểu dữ liệu

Nguồn: `src/sac_mcp/core/knowledge_base.py` (tài liệu HOA_C3D GROUP), `core/builders/param_builder.py`,
và các builder mẫu trong `native_suite_builder.py`. Tra trực tiếp: `get_sac_reference_and_formulas(topic="naming_and_defaults")`.

## 1. Tên Parameter / biến

| Tiền tố | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| `H_` | Chiều cao / chiều dày | `H_bonen`, `H_ketcau`, `H_Than`, `H_Mong`, `H_VHC` |
| `B_` | Bề rộng | `B_lan`, `B_le`, `B_Co`, `B_Mui_Trai` |
| `i_` | Độ dốc ngang (Grade, %) | `i_lan`, `i_le`, `i_Co`, `i_matduong` |
| `s_` | Mái dốc taluy (Slope, tỷ lệ) – dùng trong builder mẫu | `s_Dap`, `s_Dao`, `s_Taluy` |
| `t1..tn` | Chiều dày lớp áo đường | `t1` BTNC C12.5, `t2` BTNC C19, `t3` CPĐD loại 1 |
| `Var_` | Biến cục bộ (`add_define_variable`) | `Var_H`, `Half_B` |
| `Out_` | Output Parameter | `Out_ChenhCao` |

- Tên phải là định danh VB.NET: chữ cái đầu, chỉ `A-Z a-z 0-9 _`. **Không dấu, không khoảng trắng** – tiếng Việt đặt ở `display_name` / `description`. `add_parameter` tự thay ký tự lạ bằng `_` và từ chối tên bắt đầu bằng số.
- VB không phân biệt hoa thường: `B_Lan` và `B_lan` là **cùng một biến** – tránh đặt hai tên chỉ khác hoa/thường.
- Tham số mặc định theo tài liệu: `KHT` (String, nhãn ẩn), `DTK` (String, "Điền thiết kế"), `LaneWidth` (Double 3.5), `LaneSlope` (Grade -0.02).
- Tên Target thường gặp: `EG` / `Surface_TN` (SurfaceTarget), `Target_Offset` / `Targ_Offset` (OffsetTarget), `Target_Elevation` (ElevationTarget).

## 2. Kiểu dữ liệu (`add_parameter.data_type`)

| `data_type` | Kiểu XAML | `default_value` truyền vào | Được ghi thành | Dùng cho |
| :--- | :--- | :--- | :--- | :--- |
| `Double` | `x:Double` | `"3.5"` | `3.5` | Kích thước (m) |
| `Integer` | `x:Int32` | `"3"` | `3` | Số đếm |
| `String` | `x:String` | `"abc"` | – | Nhãn |
| `Boolean` | `x:Boolean` | `"True"` | – | Cờ nội bộ |
| `Grade` | `asw:Grade` | `"-0.02"` (= -2%) | `[new Grade(-0.02)]` | Độ dốc ngang mặt đường / lề / cơ |
| `Slope` | `asw:Slope` | `"-0.6667"` (1:1.5) | `[new Slope(-0.6667)]` | Mái taluy đào/đắp, vách phui |
| `Side` | `asw:EnumType` | `"Right"` / `"Left"` | `[new EnumType(0, "Right", "Side")]` / `EnumType(1, "Left", ...)` | Phía áp dụng (đã có sẵn trong template) |
| `YesNo` | `asw:EnumType` | `"Yes"` / `"No"` | `[new EnumType(10, "Yes", "Yes\No")]` / `11, "No"` | Bật/tắt tùy chọn; so sánh `X = Yes` |
| `Superelevation` | `asw:CrossSegmentType` | `"RightOutsideLane"`, `"None"`... | `[new EnumType(26, "RightOutsideLane", "Superelevation")]` (20..27, None=-1) | Gán làn/lề cho siêu cao (biến `UseSuperelevation`) |
| `SuperelevationAxisOfRotation`, `SlopeDirection`, `PotentialPivot`, `Cant` | `asw:*` | – | – | Trục quay, đường sắt |
| `SurfaceTarget` | `asw:SurfaceTarget` | bỏ qua | `[new PreviewSurfaceTarget("EG", True, ...)]` | Bề mặt (EG, mặt thiết kế) – `param_category="Target"` |
| `OffsetTarget` | `asw:OffsetTarget` | bỏ qua | `[new PreviewOffsetTarget(..., True, 5)]` | Khống chế bề rộng (mở rộng làn) – Target |
| `ElevationTarget` | `asw:ElevationTarget` | bỏ qua | `[new PreviewElevationTarget(..., True, 0)]` | Khống chế cao độ – Target |

Phân biệt:
- **Grade vs Slope**: cùng là số thập phân "dọc/ngang". Grade hiển thị dạng % trong Civil 3D (mặt đường, lề, mặt cơ); Slope hiển thị dạng tỷ lệ 1:n (mái dốc). Dấu: âm = đi xuống khi đi ra xa tim.
- **Side**: ΔX dương hướng ra xa tim; SAC tự lật khi `Side=Left`. Trong biểu thức: `Side=Left`, `Side=Right`.
- **Target**: là Parameter `param_category="Target"`; không ghi vào `.atc` (chỉ Input mới có) – đúng như SAC. Kiểm tra trước khi dùng: `EG.IsValid`, `Target_Offset.IsValid`, `Target_Offset.Offset`, `Target_Elevation.Elevation`.
- **Output**: `param_category="Output"`, gán giá trị bằng `add_set_output_parameter`; không có default trên Activity.
- Biến cục bộ (`add_define_variable`): kiểu `Double` / `Integer` / `String` / `YesNo`; giá trị khởi tạo có thể là biểu thức (`"B_day / 2.0"`) hoặc literal rồi gán bằng `add_set_variable`. Tên không trùng Parameter / từ khoá VB.

## 3. Mã Point / Link / Shape

| Đối tượng | Mã định danh | Ví dụ Code (Civil 3D) |
| :--- | :--- | :--- |
| Point | `P1, P2, ...` | `"Crown"`, `"ETW"`, `"EPS"`, `"Mep_PXC"`, `"Vai_Taluy"`, `"Chan_Taluy"`, `"Day_Cong"` |
| Auxiliary Point | `AP1, AP2, ...` | (không xuất ra Civil 3D) |
| Link | `L1, L2, ...` | `"Top"`, `"Datum"`, `"Pave"`, `"Pave1"`, `"Daylight"`, `"TaluyDap"`, `"MatCo"`, `"Ditch"` |
| Auxiliary Link | `AL1, AL2, ...` | – |
| Shape | `S1, S2, ...` | `"Pave1"`, `"Pave2"`, `"Base"`, `"SubBase"`, `"BTLot"`, `"ThanTuong"`, `"BanMong"`, `"VHC"` |
| Loop / Offset | `LO1`, `OF1` | Tham chiếu điểm cuối: `LO1.EndPoint` |
| Fillet | tên Link (VD `L6`) + `start_point_name` / `end_point_name` | |

- Code truyền dạng chuỗi có ngoặc kép, nhiều code cách bằng dấu phẩy: `'"Top", "Pave"'`.
- Link mặt hoàn thiện luôn có `"Top"` (Corridor surface Top), đáy kết cấu có `"Datum"` (Corridor surface Datum). Mái taluy có `"Daylight"`.
- Đặt mã theo thứ tự xuất hiện trên bản vẽ, giữ cùng mã cho điểm tương đương ở các nhánh Decision (VD điểm chân taluy) để subassembly sau / Feature Line bắt được.

## 4. Biểu thức VB thường dùng

- `IF(cond, a, b)`, `(c1)AND(c2)`, `(c1)OR(c2)`, so sánh `=`, `<>`.
- `Math.Abs`, `Math.Max`, `Math.Min`, `Math.Round(x, 2)`, `Math.Sqrt`, `Math.Pow`, góc tính bằng radian.
- Point: `P1.X`, `P1.Y`, `P1.Offset`, `P1.Elevation`, `P1.DistanceTo("P2")`, `P1.SlopeTo("P2")`, `P1.IsValid`, `P1.DistanceToSurface(EG)`.
- Link: `L1.Slope`, `L1.Length`, `L1.XLength`, `L1.YLength`, `L1.StartPoint`, `L1.EndPoint`, `L1.MaxY`, `L1.MinY`, `L1.HasIntersection("L2", True, True)`.
- Baseline: `Baseline.Station`, `Baseline.Elevation`, `Baseline.Grade`, `Baseline.TurnDirection`.
- Siêu cao: công thức 8 nhánh `IF((UseSuperelevation=LeftInsideLane)AND((Side=Left)AND(SE.HasLeftLI)), SE.LeftLI, ... CType(i_lan,Double))` – sinh bằng `use_superelevation_formula=True` hoặc `get_sac_reference_and_formulas(topic="superelevation_formula", fallback_slope_param="i_lan")`.
