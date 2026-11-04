"""
Sinh lại src/sac_mcp/native/activity_catalog.json từ Subassembly.ActivityLibrary.dll trên máy
(danh mục dùng cho kiểm tra tĩnh ACTIVITY_UNKNOWN khi máy không cài Subassembly Composer).

Chạy:  .venv/Scripts/python.exe scripts/update_activity_catalog.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from sac_mcp.core.semantic_checks import ACTIVITY_CATALOG_FILE  # noqa: E402
from sac_mcp.native.host import activity_catalog, installed_sac_dirs  # noqa: E402


def main() -> int:
    versions = installed_sac_dirs()
    if not versions:
        print("Máy không cài Subassembly Composer.")
        return 1
    merged: dict = {}
    per_version: dict = {}
    for ver in sorted(versions):
        cat = activity_catalog(ver)
        per_version[ver] = cat["assembly_version"]
        for name, info in cat["activities"].items():
            entry = merged.setdefault(name, {"properties": set(), "required": set()})
            entry["properties"].update(info["properties"])
            entry["required"].update(info["required"])
    out = {
        "source": "Subassembly.ActivityLibrary.dll",
        "versions": per_version,
        "activities": {
            name: {"properties": sorted(e["properties"]), "required": sorted(e["required"])}
            for name, e in sorted(merged.items())
        },
    }
    ACTIVITY_CATALOG_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Đã ghi {len(merged)} activity ({', '.join(per_version)}) vào {ACTIVITY_CATALOG_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
