"""
Skill phải đọc được bởi Claude Code (.claude/skills/), Antigravity (.agents/skills/) và OpenCode (cả hai),
nên bản sao .agents/skills/ phải luôn trùng bản gốc, và frontmatter phải theo chuẩn Agent Skills.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ROOT_DIR / "scripts" / "sync_agent_skills.py"


def _load_sync():
    spec = importlib.util.spec_from_file_location("sync_agent_skills", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agents_mirror_matches_claude_skills() -> None:
    problems = _load_sync().diff()
    assert problems == [], "Chạy: .venv/Scripts/python.exe scripts/sync_agent_skills.py\n" + "\n".join(problems)


def test_skill_frontmatter_is_portable() -> None:
    for skill_md in (ROOT_DIR / ".claude" / "skills").glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        assert m, f"{skill_md}: thiếu frontmatter YAML"
        fields = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        name = fields.get("name", "").strip()
        desc = fields.get("description", "").strip()
        # Chuẩn Agent Skills: tên kebab-case 1-64 ký tự, trùng tên thư mục; mô tả 1-1024 ký tự
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64, name
        assert name == skill_md.parent.name
        assert 0 < len(desc) <= 1024, len(desc)
