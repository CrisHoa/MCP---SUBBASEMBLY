"""
Các nhóm EnumType của Subassembly Composer, đúng như SAC tự ghi (đối chiếu file .pkt trong examples/):

  XAML:  this:Subassembly.Side="[new EnumType(0, &quot;Right&quot;, &quot;Side&quot;)]"
  .atc:  <Side DataType="long" TypeInfo="16" ...>0<Enum><Left DisplayName="Left">1</Left>...</Enum></Side>

Dùng chung cho ParameterBuilder (giá trị mặc định trong XAML) và PktPackage.sync_parameter_to_atc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import re


@dataclass(frozen=True)
class EnumGroup:
    group: str                                  # tham số thứ 3 của EnumType(...), VD 'Side', 'Yes\No'
    choices: Tuple[Tuple[str, int, str], ...]   # (tên, mã số, DisplayName trong .atc) theo thứ tự SAC ghi
    default: str
    # Giá trị hợp lệ trong XAML nhưng SAC không liệt kê trong <Enum> của .atc
    # (VD file thật dùng Side = EnumType(-1, "None", "Side")).
    hidden: Tuple[Tuple[str, int], ...] = ()

    def _all(self) -> Tuple[Tuple[str, int], ...]:
        return tuple((n, c) for n, c, _ in self.choices) + self.hidden

    def code_of(self, value: str) -> Optional[int]:
        """Mã số của một lựa chọn theo tên (không phân biệt hoa thường) hoặc theo mã số dạng chuỗi."""
        v = value.strip().strip('"').strip()
        for name, code in self._all():
            if v.lower() == name.lower():
                return code
        if re.fullmatch(r"-?\d+", v):
            code = int(v)
            if any(c == code for _, c in self._all()):
                return code
        return None

    def name_of(self, code: int) -> str:
        for name, c in self._all():
            if c == code:
                return name
        valid = ", ".join(f"{n} ({c})" for n, c in self._all())
        raise ValueError(f"Mã {code} không thuộc nhóm enum '{self.group}'. Hợp lệ: {valid}.")


ENUM_GROUPS: Dict[str, EnumGroup] = {
    "Side": EnumGroup("Side", (("Left", 1, "Left"), ("Right", 0, "Right")), "Right", hidden=(("None", -1),)),
    "YesNo": EnumGroup("Yes\\No", (("Yes", 10, "Yes"), ("No", 11, "No")), "Yes"),
    "Superelevation": EnumGroup(
        "Superelevation",
        (
            ("LeftInsideLane", 20, "Left Inside Lane Slope"),
            ("LeftInsideShoulder", 21, "Left Inside Shoulder Slope"),
            ("LeftOutsideLane", 22, "Left Outside Lane Slope"),
            ("LeftOutsideShoulder", 23, "Left Outside Shoulder Slope"),
            ("RightInsideLane", 24, "Right Inside Lane Slope"),
            ("RightInsideShoulder", 25, "Right Inside Shoulder Slope"),
            ("RightOutsideLane", 26, "Right Outside Lane Slope"),
            ("RightOutsideShoulder", 27, "Right Outside Shoulder Slope"),
            ("None", -1, "None"),
        ),
        "None",
    ),
}

# Giá trị kiểu boolean thường gặp cho tham số Yes/No
_YESNO_ALIASES = {"true": "Yes", "false": "No", "co": "Yes", "có": "Yes", "khong": "No", "không": "No"}
_ENUM_EXPR_RE = re.compile(r"EnumType\(\s*(-?\d+)")


def resolve_enum(data_type: str, value: Optional[str]) -> Tuple[int, str]:
    """
    Trả về (mã số, tên lựa chọn) cho giá trị mặc định của tham số enum.
    Chấp nhận tên ('Left'), mã số ('1'), biểu thức có sẵn ('[new EnumType(1, ...)]') hoặc rỗng (dùng mặc định).
    Raise ValueError nếu giá trị không thuộc nhóm.
    """
    grp = ENUM_GROUPS[data_type]
    raw = (value or "").strip()
    m = _ENUM_EXPR_RE.search(raw)
    if m:
        code = int(m.group(1))
        return code, grp.name_of(code)
    if not raw or raw in ("0.0",):
        raw = grp.default
    if data_type == "YesNo":
        raw = _YESNO_ALIASES.get(raw.lower(), raw)
    code = grp.code_of(raw)
    if code is None:
        valid = ", ".join(f"{n} ({c})" for n, c, _ in grp.choices)
        raise ValueError(f"Giá trị '{value}' không hợp lệ cho tham số kiểu {data_type}. Chọn một trong: {valid}.")
    return code, grp.name_of(code)


def enum_xaml_default(data_type: str, value: Optional[str]) -> str:
    """Biểu thức mặc định trong XAML, VD '[new EnumType(1, "Left", "Side")]'."""
    code, name = resolve_enum(data_type, value)
    return f'[new EnumType({code}, "{name}", "{ENUM_GROUPS[data_type].group}")]'
