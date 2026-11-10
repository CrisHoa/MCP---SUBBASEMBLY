"""
Đồng bộ skill từ .claude/skills/ (bản gốc, Claude Code đọc) sang .agents/skills/ (bản sao).

Lý do có hai bản:
  - Claude Code chỉ đọc .claude/skills/.
  - Google Antigravity đọc <workspace>/.agents/skills/ (không đọc .claude/skills/).
  - OpenCode đọc cả hai thư mục.
Symlink trên Windows cần quyền Developer Mode và git thường checkout thành file text, nên dùng bản sao.

Chạy sau mỗi lần sửa skill:  .venv/Scripts/python.exe scripts/sync_agent_skills.py
Kiểm tra (không ghi gì):      .venv/Scripts/python.exe scripts/sync_agent_skills.py --check
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SOURCE = ROOT_DIR / ".claude" / "skills"
MIRROR = ROOT_DIR / ".agents" / "skills"


def _files(base: Path) -> dict[str, bytes]:
    if not base.exists():
        return {}
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def diff() -> list[str]:
    """Danh sách khác biệt giữa bản gốc và bản sao (rỗng = đã đồng bộ)."""
    src, dst = _files(SOURCE), _files(MIRROR)
    out = [f"thiếu trong .agents: {k}" for k in src if k not in dst]
    out += [f"thừa trong .agents: {k}" for k in dst if k not in src]
    out += [f"khác nội dung: {k}" for k in src if k in dst and src[k] != dst[k]]
    return out


def sync() -> None:
    if MIRROR.exists():
        shutil.rmtree(MIRROR)
    shutil.copytree(SOURCE, MIRROR)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--check" in sys.argv:
        problems = diff()
        for line in problems:
            print(line)
        print("Đã đồng bộ." if not problems else f"{len(problems)} khác biệt: chạy lại không kèm --check.")
        return 1 if problems else 0
    sync()
    print(f"Đã chép {len(_files(MIRROR))} file từ {SOURCE} sang {MIRROR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
