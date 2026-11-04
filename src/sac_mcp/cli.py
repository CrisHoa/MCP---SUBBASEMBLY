"""
CLI Tooling chuyên dụng cho Autodesk Subassembly Composer (.pkt).
Cung cấp các lệnh tức thì:
  - sac-cli validate <file.pkt>   : Kiểm định 3 tầng (OPC, XAML, Native DLL)
  - sac-cli build --giaco         : Tự động dựng và kiểm định mái taluy Phú Yên
  - sac-cli build --sub7          : Tự động dựng và kiểm định bộ 7 subassemblies
  - sac-cli build --all [--out D] : Dựng toàn bộ, kiểm định và xuất ra thư mục D
  - sac-cli test                  : Chạy toàn bộ unit test pytest
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sac_mcp.paths import OUTPUT_DIR_ENV, get_output_dir

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def cmd_validate(args: argparse.Namespace) -> int:
    from sac_mcp.core.validator import PktValidator
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"❌ File không tồn tại: {target}")
        return 1

    report = PktValidator.validate_pkt(target, run_native_test=not args.no_native)
    report.print_summary()
    return 0 if report.is_valid else 1


def cmd_build(args: argparse.Namespace) -> int:
    from sac_mcp.core.validator import PktValidator

    out_dir = get_output_dir(args.out)
    # Truyền thư mục xuất cho các script con qua biến môi trường
    child_env = {**os.environ, OUTPUT_DIR_ENV: str(out_dir)}
    built_files = []

    if args.giaco or args.all:
        print("\n🔨 [1/2] Dựng Subassembly: Gia Cố Mái Taluy Phú Yên...")
        script_giaco = ROOT_DIR / "scripts" / "build_giaco_taluy_phuyen.py"
        res = subprocess.run([sys.executable, str(script_giaco)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env)
        if res.returncode != 0:
            print(f"❌ Lỗi khi dựng Gia Cố Mái Taluy:\n{res.stderr}")
            return 1
        if res.stdout:
            print(res.stdout.strip())
        built_files.append(out_dir / "GiaCo_MaiTaluy_PhuYen.pkt")

    if args.sub7 or args.all:
        print("\n🔨 [2/2] Dựng Bộ 7 Subassembly chuẩn (đã xóa chữ visual)...")
        script_sub7 = ROOT_DIR / "scripts" / "rebuild_7_subassemblies.py"
        res = subprocess.run([sys.executable, str(script_sub7)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env)
        if res.returncode != 0:
            print(f"❌ Lỗi khi dựng Bộ 7 Subassembly:\n{res.stderr}")
            return 1
        if res.stdout:
            print(res.stdout.strip())
        sub7_dir = out_dir / "Bo_7_Subassembly"
        built_files.extend(list(sub7_dir.glob("*.pkt")))


    print("\n🔍 [KIỂM ĐỊNH TỰ ĐỘNG BẰNG NATIVE DLL AUTODESK]")
    all_ok = True
    for pkt in built_files:
        if pkt.exists():
            rep = PktValidator.validate_pkt(pkt, run_native_test=True)
            status = "✅ PASS" if rep.is_valid else "❌ FAIL"
            print(f"  [{status}] {pkt.name} ({pkt.stat().st_size} bytes)")
            if not rep.is_valid:
                all_ok = False
                for iss in rep.issues:
                    print(f"      -> {iss.message}")

    print("\n" + ("=" * 60))
    if all_ok:
        print("🎉 TẤT CẢ FILE ĐÃ ĐƯỢC DỰNG & KIỂM ĐỊNH THÀNH CÔNG 100%!")
        print(f"📁 Thư mục xuất: {out_dir}")
    else:
        print("❌ CÓ FILE BỊ LỖI KIỂM ĐỊNH!")
    print("=" * 60 + "\n")
    return 0 if all_ok else 1


def cmd_test(args: argparse.Namespace) -> int:
    print("\n🧪 Chạy toàn bộ kiểm thử pytest...")
    res = subprocess.run([sys.executable, "-m", "pytest", "-v"], cwd=str(ROOT_DIR))
    return res.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sac-cli",
        description="Bộ công cụ tự động hóa & kiểm định Autodesk Civil 3D Subassembly Composer (.pkt)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lệnh validate
    p_val = subparsers.add_parser("validate", help="Kiểm định file .pkt qua 3 tầng (OPC, XAML, Native DLL)")
    p_val.add_argument("target", help="Đường dẫn file .pkt cần kiểm định")
    p_val.add_argument("--no-native", action="store_true", help="Bỏ qua tầng kiểm thử native DLL")
    p_val.set_defaults(func=cmd_validate)

    # Lệnh build
    p_build = subparsers.add_parser("build", help="Dựng nhanh subassembly và tự động kiểm định")
    p_build.add_argument("--giaco", action="store_true", help="Dựng riêng GiaCo_MaiTaluy_PhuYen.pkt")
    p_build.add_argument("--sub7", action="store_true", help="Dựng riêng Bộ 7 Subassembly chuẩn")
    p_build.add_argument("--all", action="store_true", help="Dựng toàn bộ tất cả file và kiểm định")
    p_build.add_argument("--out", help=f"Thư mục xuất (mặc định: biến môi trường {OUTPUT_DIR_ENV} hoặc ~/Desktop/SUB PHU YEN)")
    p_build.set_defaults(func=cmd_build)

    # Lệnh test
    p_test = subparsers.add_parser("test", help="Chạy toàn bộ pytest suite")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
