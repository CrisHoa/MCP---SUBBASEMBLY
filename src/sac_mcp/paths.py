"""Đường dẫn dùng chung (không gắn cứng tên người dùng / máy)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

OUTPUT_DIR_ENV = "SAC_OUTPUT_DIR"
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "SUB PHU YEN"


def get_output_dir(override: Optional[str | Path] = None) -> Path:
    """Thư mục xuất file build: tham số `override` > biến môi trường SAC_OUTPUT_DIR > ~/Desktop/SUB PHU YEN."""
    if override:
        return Path(override).expanduser().resolve()
    env_val = os.environ.get(OUTPUT_DIR_ENV)
    if env_val:
        return Path(env_val).expanduser().resolve()
    return DEFAULT_OUTPUT_DIR
