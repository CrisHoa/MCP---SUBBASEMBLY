# Mẫu dựng hình (chuỗi lời gọi tool)

Các mẫu dưới đây viết dạng `tool(tham_số=...)`; luôn kèm `pkt_path` (bỏ qua cho gọn). Tên tham số, kiểu dữ liệu, Code
lấy từ `native_suite_builder.py` / `recipes.py`. Mẫu A, B, D, E, F đã được chạy thử nguyên văn và qua kiểm định
3 tầng (`is_valid: true`, `tier3_native_ok: true`). Mẫu C chạy nguyên văn qua tool MCP, qua cả `document_check=True`.

Quy ước chung:
- `add_point_and_link` mặc định `point_type="DeltaX_DeltaY"`, `from_point="Origin"`, `add_link=True` (khi đó bắt buộc `link_name` duy nhất). Điểm không có Link → `add_link=False`.
- `param_1_expr` / `param_2_expr` theo `point_type`: `DeltaX_DeltaY` (ΔX, ΔY) · `Slope_DeltaX` (dốc, ΔX) · `Slope_DeltaY` (dốc, ΔY) · `Slope_To_Surface` (dốc, tên SurfaceTarget) · `Angle_Distance` (góc, khoảng cách) · `Interpolate` (tên điểm đích, tỷ lệ).
- ΔX dương = hướng ra xa tim theo `Side` (SAC tự lật khi `Side=Left`).

---

## A. Làn xe có siêu cao + lề + đáy kết cấu (1 Shape)

```text
create_pkt_from_template(output_path=".../LanXe_SieuCao.pkt", subassembly_name="LanXe_SieuCao", civil_version="2026")
add_parameter(name="Side", data_type="Side", default_value="Right", display_name="Phía")          # Side có sẵn, chỉ đổi mặc định
add_parameter(name="B_lan", data_type="Double", default_value="3.5", display_name="Bề rộng làn (m)")
add_parameter(name="i_lan", data_type="Grade", default_value="-0.02", display_name="Dốc ngang làn (%)")
add_parameter(name="UseSuperelevation", data_type="Superelevation", default_value="RightOutsideLane", display_name="Siêu cao")
add_parameter(name="B_le", data_type="Double", default_value="0.5")
add_parameter(name="i_le", data_type="Grade", default_value="-0.04")
add_parameter(name="H_kc", data_type="Double", default_value="0.5", display_name="Chiều dày kết cấu (m)")

add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Crown"')
add_point_and_link(point_code="P2", from_point="P1", point_type="Slope_DeltaX", param_1_expr="i_lan", param_2_expr="B_lan",
                   use_superelevation_formula=True, link_name="L1", link_codes_str='"Top", "Pave"', point_codes_str='"ETW"')
add_point_and_link(point_code="P3", from_point="P2", point_type="Slope_DeltaX", param_1_expr="i_le", param_2_expr="B_le",
                   link_name="L2", link_codes_str='"Top", "Shoulder"', point_codes_str='"EPS"')
add_point_and_link(point_code="P4", from_point="P1", param_1_expr="0", param_2_expr="-H_kc", link_name="L3", link_codes_str='"Crown"')
add_point_and_link(point_code="P5", from_point="P3", param_1_expr="0", param_2_expr="-H_kc", link_name="L4", link_codes_str='"Pave"')
add_link(link_name="L5", start_point="P4", end_point="P5", link_codes_str='"Datum"')
add_shape(shape_code="S1", link_names=["L1", "L2", "L4", "L5", "L3"], shape_codes_str='"Pave"')
add_report_message(message_expr='"B_lan phải > 0"', message_type="Error", condition_expr="B_lan <= 0")   # để cuối
validate_pkt_native()
```

`use_superelevation_formula=True` thay `param_1_expr` bằng công thức 8 nhánh, `i_lan` thành giá trị dự phòng
(`CType(i_lan,Double)`). Lề gia cố muốn quay theo siêu cao: dùng lại công thức (xem `get_sac_reference_and_formulas(topic="superelevation_formula", fallback_slope_param="i_le")`).

---

## B. Bó vỉa bo cong (Fillet) + vỉa hè

Góc bó vỉa dựng bằng 2 Link phụ trợ `AL1`, `AL2`, rồi bo cong giữa chúng; điểm đầu/cuối cung được đặt tên `P2`, `P3` để nối tiếp.

```text
create_pkt_from_template(output_path=".../BoVia_ViaHe.pkt", subassembly_name="BoVia_ViaHe", civil_version="2026")
add_parameter(name="H_bovia", default_value="0.15")   # Double mặc định
add_parameter(name="B_bovia", default_value="0.18")
add_parameter(name="B_he", default_value="3.0")
add_parameter(name="i_he", data_type="Grade", default_value="0.015")

add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Gutter"')
add_point_and_link(point_code="AP1", from_point="P1", param_1_expr="0", param_2_expr="H_bovia", is_auxiliary=True, link_name="AL1")
add_point_and_link(point_code="AP2", from_point="AP1", param_1_expr="B_bovia", param_2_expr="0", is_auxiliary=True, link_name="AL2")
add_fillet_arc(link_number="L1", first_link="AL1", second_link="AL2", round_radius=0.05,
               start_point_name="P2", end_point_name="P3", link_codes_str='"Top", "Curb"')
add_link(link_name="L2", start_point="P1", end_point="P2", link_codes_str='"Top", "Curb"')
add_point_and_link(point_code="P4", from_point="AP2", add_link=False, point_codes_str='"Back_Curb"')
add_link(link_name="L3", start_point="P3", end_point="P4", link_codes_str='"Top", "Curb"')
add_point_and_link(point_code="P5", from_point="P4", point_type="Slope_DeltaX", param_1_expr="i_he", param_2_expr="B_he",
                   link_name="L4", link_codes_str='"Top", "Sidewalk"', point_codes_str='"Mep_he"')
validate_pkt_native()
```

`round_radius` là số (m), không nhận biểu thức. Cần Shape bó vỉa thì dựng thêm điểm đáy và `add_shape` với các Link thật (không dùng `AL*`).

---

## C. Taluy đào / đắp có Decision (AP1.Y so với P2.Y)

Bản rút gọn của `build_05_taluy_dao_dap_day_du` (bản đầy đủ có thêm Decision lồng "Giật cơ đắp?" trong nhánh True; mọi node trong nhánh đều truyền `parent_node_id` rõ ràng).

```text
add_parameter(name="EG", param_category="Target", data_type="SurfaceTarget", display_name="Mặt đất tự nhiên")
add_parameter(name="Ble", default_value="0.5");  add_parameter(name="i_le", data_type="Grade", default_value="-0.04")
add_parameter(name="s_Dap", data_type="Slope", default_value="-0.6667")    # 1:1.5
add_parameter(name="s_Dao", data_type="Slope", default_value="1.0")        # 1:1
add_parameter(name="b_ranh", default_value="0.4");  add_parameter(name="h_ranh", default_value="0.4")
add_parameter(name="Out_H", param_category="Output", data_type="Double", display_name="Chiều cao taluy (m)")

add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Mep_Le"')
add_point_and_link(point_code="P2", from_point="P1", point_type="Slope_DeltaX", param_1_expr="i_le", param_2_expr="Ble",
                   link_name="L1", link_codes_str='"Top", "LeDat"', point_codes_str='"Vai_Taluy"')
add_point_and_link(point_code="AP1", from_point="P2", point_type="Slope_To_Surface", param_1_expr="-1.5", param_2_expr="EG", is_auxiliary=True, add_link=False)
add_define_variable(variable_name="Var_H", variable_type="Double", default_value_expr="0.0")
add_set_variable(variable_name="Var_H", value_expr="Math.Abs(P2.Y - AP1.Y)")
add_flow_decision(condition_expr="AP1.Y < P2.Y", display_name="Đắp hay Đào?")   # created_reference_ids[0] -> "__ReferenceID<d>"

# Nhánh True = ĐẮP
add_point_and_link(point_code="P3", from_point="P2", point_type="Slope_To_Surface", param_1_expr="s_Dap", param_2_expr="EG",
                   link_name="L2", link_codes_str='"Daylight", "TaluyDap"', point_codes_str='"Chan_Taluy"',
                   parent_node_id="__ReferenceID<d>:True")
# Nhánh False = ĐÀO: rãnh biên rồi mái đào
add_point_and_link(point_code="P4", from_point="P2", param_1_expr="0", param_2_expr="-h_ranh",
                   link_name="L3", link_codes_str='"Ditch"', parent_node_id="__ReferenceID<d>:False")      # -> "__ReferenceID<f1>"
add_point_and_link(point_code="P5", from_point="P4", param_1_expr="b_ranh", param_2_expr="0",
                   link_name="L4", link_codes_str='"Ditch"', parent_node_id="__ReferenceID<f1>")           # -> "__ReferenceID<f2>"
add_point_and_link(point_code="P3", from_point="P5", point_type="Slope_To_Surface", param_1_expr="s_Dao", param_2_expr="EG",
                   link_name="L5", link_codes_str='"Daylight", "TaluyDao"', point_codes_str='"Chan_Taluy"',
                   parent_node_id="__ReferenceID<f2>")
# Hội tụ: bỏ trống parent_node_id -> nối từ cuối CẢ HAI nhánh (tool báo warning "Luồng có 2 đầu ra mở ..." - đúng ý đồ)
add_set_output_parameter(parameter_name="Out_H", value_expr="Var_H")
add_set_mark_point(point_number="P3", mark_name="ChanTaluy")
validate_pkt_native(document_check=True)     # is_valid: true, tier3_native_ok: true
```

- Cùng mã `P3` ở hai nhánh để subassembly sau bắt vào một tên điểm duy nhất.
- Sau Decision, node thêm với `parent_node_id` bỏ trống sẽ chạy ở **cả hai** nhánh (hội tụ) – chỉ dùng cho phần chung (VD `add_set_output_parameter`).
- Hai Link khác mã (`L2`, `L5`) nên không cần `allow_duplicate_link`. Muốn cùng mã Link ở hai nhánh: truyền `allow_duplicate_link=True` ở lần tạo thứ hai.
- Lồng Decision thứ hai (`Var_H > H_GiatCo_Dap`) vào nhánh: `add_flow_decision(..., parent_node_id="__ReferenceID<d>:True")` (xem `build_05`).

---

## D. Taluy giật cơ bằng Loop + bóc hữu cơ

```text
add_parameter(name="EG", param_category="Target", data_type="SurfaceTarget")
add_parameter(name="s_Dap", data_type="Slope", default_value="-0.6667")
add_parameter(name="H_Co", default_value="6.0");  add_parameter(name="B_Co", default_value="2.0")
add_parameter(name="i_Co", data_type="Grade", default_value="0.04");  add_parameter(name="H_VHC", default_value="0.3")

add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Vai_Taluy"')
add_point_and_link(point_code="P2", from_point="P1", point_type="Slope_DeltaY", param_1_expr="s_Dap", param_2_expr="-H_Co",
                   link_name="L1", link_codes_str='"Daylight", "TaluyDap"')
add_point_and_link(point_code="P3", from_point="P2", point_type="Slope_DeltaX", param_1_expr="i_Co", param_2_expr="B_Co",
                   link_name="L2", link_codes_str='"Top", "MatCo"')
add_loop_geometry(loop_code="LO1", links=["L1", "L2"], repetition_count=5)
add_point_and_link(point_code="P4", from_point="LO1.EndPoint", point_type="Slope_To_Surface", param_1_expr="s_Dap", param_2_expr="EG",
                   link_name="L3", link_codes_str='"Daylight", "TaluyDap"', point_codes_str='"Chan_Taluy"')
add_strip_surface(display_name="P5&L4&P6", depth_expr="H_VHC", surface_target="EG", start_point_name="P6", start_offset="P4.X",
                  end_point_name="P5", end_offset=-5.0, link_number="L4")
validate_pkt_native()
```

`LO1.EndPoint` = điểm cuối chu kỳ lặp cuối cùng. Số tầng thực tế nên khống chế bằng Decision theo chiều cao
(`Var_H > H_Co`) nếu không muốn lặp cứng `repetition_count`.

---

## E. Tường chắn 3 Shape (thân, bản móng, bê tông lót) – rút gọn từ `build_09_tuong_chan_cat_3_3`

```text
add_parameter(name=..., default_value=...) cho H_Than 0.80, B_Dinh 0.30, B_Day_Than 0.35, B_Mui_Trai 0.20,
              B_Got_Phai 0.45, H_Mong 0.30, H_Lot 0.10, B_Lot_Ext 0.10
# Thân tường
add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Top"')
add_point_and_link(point_code="P2", from_point="P1", param_1_expr="B_Dinh", param_2_expr="0", link_name="L1", link_codes_str='"Top"')
add_point_and_link(point_code="P4", from_point="P1", param_1_expr="0", param_2_expr="-H_Than", add_link=False)
add_point_and_link(point_code="P5", from_point="P4", param_1_expr="B_Day_Than", param_2_expr="0", add_link=False)
add_link("L3", "P2", "P5", '"WallStem"');  add_link("L4", "P4", "P5", '"StemBase"');  add_link("L5", "P1", "P4", '"WallStem"')
add_shape(shape_code="S1", link_names=["L1", "L3", "L4", "L5"], shape_codes_str='"ThanTuong"')
# Bản móng: dùng chung cạnh L4 với thân
add_point_and_link(point_code="P6", from_point="P4", param_1_expr="-B_Mui_Trai", param_2_expr="0", add_link=False)
add_link("L6", "P6", "P4", '"Top", "Footing"')
add_point_and_link(point_code="P7", from_point="P5", param_1_expr="B_Got_Phai", param_2_expr="0", add_link=False)
add_link("L7", "P5", "P7", '"Top", "Footing"')
add_point_and_link(point_code="P8", from_point="P6", param_1_expr="0", param_2_expr="-H_Mong", link_name="L8", link_codes_str='"Footing"')
add_point_and_link(point_code="P9", from_point="P7", param_1_expr="0", param_2_expr="-H_Mong", link_name="L9", link_codes_str='"Footing"')
add_link("L10", "P8", "P9", '"FootingBottom"')
add_shape(shape_code="S2", link_names=["L6", "L4", "L7", "L9", "L10", "L8"], shape_codes_str='"BanMong"')
# Bê tông lót: dùng chung cạnh L10
add_point_and_link(point_code="P10", from_point="P8", param_1_expr="-B_Lot_Ext", param_2_expr="-H_Lot", add_link=False)
add_point_and_link(point_code="P11", from_point="P9", param_1_expr="B_Lot_Ext", param_2_expr="-H_Lot", add_link=False)
add_link("L11", "P10", "P11", '"Datum"');  add_link("L12", "P8", "P10", '"BTLot"');  add_link("L13", "P9", "P11", '"BTLot"')
add_shape(shape_code="S3", link_names=["L10", "L13", "L11", "L12"], shape_codes_str='"BTLot"')
validate_pkt_native()
```

(`add_link("L3", "P2", "P5", '"WallStem"')` viết tắt cho `add_link(link_name=, start_point=, end_point=, link_codes_str=)`.)
Hai Shape kề nhau **dùng chung Link** ở cạnh tiếp giáp (L4, L10) – không tạo Link trùng.
Bản đầy đủ có vát đỉnh (`Vat_Dinh`), Target `EG` / `Target_Elevation` / `Target_Offset`: xem `build_09`.

---

## F. Kết cấu áo đường nhiều lớp mở rộng so le (giống `build_07` / `build_06`)

Mỗi lớp: điểm đáy tại tim + điểm đáy tại mép (mở rộng `mr_bac` so với lớp trên), Link đáy, Link mép, Link tim, rồi
Shape dùng chung Link đáy của lớp trên. **AutoLink của `add_point_and_link` luôn nối `from_point` → điểm mới**, nên
điểm đáy mép (`P4`) dựng từ `P2` không được tự nối Link – tạo nó với `add_link=False` rồi nối đáy `P3→P4` bằng `add_link`.

```text
add_parameter(name="B_lan", default_value="3.5");  add_parameter(name="i_lan", data_type="Grade", default_value="-0.02")
add_parameter(name="t1", default_value="0.05");  add_parameter(name="t2", default_value="0.07");  add_parameter(name="mr_bac", default_value="0.10")

add_point_and_link(point_code="P1", add_link=False, point_codes_str='"Crown"')
add_point_and_link(point_code="P2", from_point="P1", point_type="Slope_DeltaX", param_1_expr="i_lan", param_2_expr="B_lan",
                   link_name="L1", link_codes_str='"Top", "Pave"', point_codes_str='"Mep_PXC"')
# Lớp 1
add_point_and_link(point_code="P3", from_point="P1", param_1_expr="0", param_2_expr="-t1", link_name="L4", link_codes_str='"Crown"')
add_point_and_link(point_code="P4", from_point="P2", param_1_expr="0", param_2_expr="-t1", link_name="L3", link_codes_str='"Pave"')
add_link("L2", "P3", "P4", '"Pave1"')
add_shape(shape_code="S1", link_names=["L1", "L3", "L2", "L4"], shape_codes_str='"Pave1"')
# Lớp 2 (mở rộng mr_bac)
add_point_and_link(point_code="P5", from_point="P3", param_1_expr="0", param_2_expr="-t2", link_name="L7", link_codes_str='"Crown"')
add_point_and_link(point_code="P6", from_point="P4", param_1_expr="mr_bac", param_2_expr="-t2", link_name="L6", link_codes_str='"Pave"')
add_link("L5", "P5", "P6", '"Pave2"')
add_shape(shape_code="S2", link_names=["L2", "L6", "L5", "L7"], shape_codes_str='"Pave2"')
validate_pkt_native()
```

Ở đây AutoLink được dùng cho các cạnh đứng (tim `P1→P3`, mép `P2→P4`) vì đúng chiều `from_point → điểm mới`.
Lớp dày đều song song mặt trên có thể dùng `add_offset_geometry(offset_code=..., links=["L1"], offset_distance=...)` thay
cho dựng từng điểm (xem docstring tool).
