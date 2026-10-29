import sys
from pathlib import Path

# Thêm thư mục src vào sys.path để pytest luôn tìm thấy sac_mcp
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
