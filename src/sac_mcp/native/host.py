"""
Cầu nối Python <-> SacHost.exe (tiến trình .NET Framework chạy nền dùng DLL gốc của Subassembly Composer).

- Tự biên dịch SacHost.cs bằng csc.exe có sẵn của .NET Framework 4.x và cache theo hash mã nguồn
  tại %LOCALAPPDATA%/sac_mcp/host/<hash>/SacHost.exe.
- Giữ một tiến trình chạy nền cho mỗi thư mục cài SAC; tự khởi động lại nếu tiến trình chết hoặc timeout.
- Chọn đúng phiên bản SAC theo phiên bản của file .pkt (fallback: bản mới nhất đã cài).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

SOURCE_FILE = Path(__file__).resolve().parent / "SacHost.cs"
SAC_ROOT = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"
SAC_DIR_ENV = "SAC_INSTALL_DIR"
SUPPORTED_SAC_VERSIONS = ("2027", "2026", "2025", "2024")

_FRAMEWORK_REFS = (
    "System.Activities.dll",
    "System.Xaml.dll",
    "System.IO.Compression.dll",
    "System.IO.Compression.FileSystem.dll",
    "System.Web.Extensions.dll",
    "System.Core.dll",
)


class NativeHostError(RuntimeError):
    """Không khởi động / giao tiếp được với SacHost.exe."""


# ----------------------------------------------------------------------------
# Tìm thư mục cài Subassembly Composer
# ----------------------------------------------------------------------------

def installed_sac_dirs() -> Dict[str, Path]:
    """{phiên bản: thư mục} của các bản Subassembly Composer có WorkflowEditor.dll trên máy."""
    found: Dict[str, Path] = {}
    for ver in SUPPORTED_SAC_VERSIONS:
        d = SAC_ROOT / f"Subassembly Composer {ver}"
        if (d / "WorkflowEditor.dll").exists():
            found[ver] = d
    return found


def select_sac_dir(pkt_version: Optional[str] = None) -> Optional[tuple[str, Path]]:
    """
    Chọn bản SAC để kiểm định:
      1. Biến môi trường SAC_INSTALL_DIR (nếu có).
      2. Đúng phiên bản của file .pkt.
      3. Bản mới nhất đã cài (SAC mới mở được file cũ).
    Trả về (nhãn phiên bản, thư mục) hoặc None nếu máy không cài SAC.
    """
    env_dir = os.environ.get(SAC_DIR_ENV)
    if env_dir and (Path(env_dir) / "WorkflowEditor.dll").exists():
        return ("custom", Path(env_dir))
    dirs = installed_sac_dirs()
    if not dirs:
        return None
    if pkt_version and pkt_version in dirs:
        return (pkt_version, dirs[pkt_version])
    newest = max(dirs)
    return (newest, dirs[newest])


# ----------------------------------------------------------------------------
# Biên dịch SacHost.exe
# ----------------------------------------------------------------------------

def _framework_dir() -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for sub in ("Framework64", "Framework"):
        d = windir / "Microsoft.NET" / sub / "v4.0.30319"
        if (d / "csc.exe").exists():
            return d
    raise NativeHostError("Không tìm thấy csc.exe của .NET Framework 4.x để biên dịch SacHost.")


def _cache_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "sac_mcp" / "host"


def ensure_host_exe() -> Path:
    """Biên dịch SacHost.cs (nếu chưa có bản cache khớp mã nguồn) và trả về đường dẫn SacHost.exe."""
    src = SOURCE_FILE.read_bytes()
    digest = hashlib.sha256(src).hexdigest()[:16]
    out_dir = _cache_root() / digest
    exe = out_dir / "SacHost.exe"
    if exe.exists():
        return exe

    fw = _framework_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Tên file quyết định tên assembly .NET (AppDomain con nạp lại theo tên này), nên phải biên dịch
    # đúng tên "SacHost.exe" vào thư mục tạm rồi mới chuyển sang.
    tmp_dir = out_dir / f"build-{os.getpid()}-{threading.get_ident()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_exe = tmp_dir / "SacHost.exe"
    cmd = [
        str(fw / "csc.exe"),
        "-nologo",
        "-target:exe",
        "-optimize+",
        f"-out:{tmp_exe}",
        *[f"-r:{fw / ref}" if (fw / ref).exists() else f"-r:{ref}" for ref in _FRAMEWORK_REFS],
        str(SOURCE_FILE),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not tmp_exe.exists():
            raise NativeHostError(f"Biên dịch SacHost.cs thất bại:\n{res.stdout}\n{res.stderr}")
        try:
            os.replace(tmp_exe, exe)
        except OSError:
            if not exe.exists():  # không phải do tiến trình khác vừa biên dịch xong cùng lúc
                raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return exe


# ----------------------------------------------------------------------------
# Tiến trình chạy nền
# ----------------------------------------------------------------------------

@dataclass
class NativeCheckResult:
    pkt: str
    sac_version: str
    sac_dir: str
    xaml_load_ok: bool
    validation_ok: bool
    document_ok: Optional[bool]
    xaml_load_error: Optional[str]
    document_error: Optional[str]
    validation_errors: List[Dict[str, Any]]
    validation_warnings: List[Dict[str, Any]]
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return self.xaml_load_ok and self.validation_ok and self.document_ok is not False


class SacHostProcess:
    """Một tiến trình SacHost.exe gắn với một thư mục cài SAC. An toàn đa luồng."""

    STARTUP_TIMEOUT = 60.0

    def __init__(self, sac_version: str, sac_dir: Path) -> None:
        self.sac_version = sac_version
        self.sac_dir = sac_dir
        self._proc: Optional[subprocess.Popen] = None
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._lock = threading.Lock()

    def _start(self) -> None:
        exe = ensure_host_exe()
        self._lines = queue.Queue()
        self._proc = subprocess.Popen(
            [str(exe), str(self.sac_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = self._lines
        stdout = self._proc.stdout

        def _pump() -> None:
            for ln in stdout:  # type: ignore[union-attr]
                lines.put(ln)
            lines.put(None)

        threading.Thread(target=_pump, daemon=True).start()
        pong = self._request("__PING__", self.STARTUP_TIMEOUT)
        if not pong.get("pong"):
            raise NativeHostError(f"SacHost không phản hồi đúng: {pong}")

    def _request(self, line: str, timeout: float) -> Dict[str, Any]:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except OSError as exc:
            self.close()
            raise NativeHostError(f"Mất kết nối với SacHost: {exc}") from exc
        try:
            raw = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise NativeHostError(f"SacHost không trả lời sau {timeout:.0f} giây (đã dừng tiến trình).")
        if raw is None:
            self.close()
            raise NativeHostError("SacHost đã thoát bất thường.")
        return json.loads(raw)

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def call(self, line: str, timeout: float) -> Dict[str, Any]:
        with self._lock:
            if not self._alive():
                self._start()
            return self._request(line, timeout)

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    proc.stdin.write("\n")  # type: ignore[union-attr]
                    proc.stdin.flush()  # type: ignore[union-attr]
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        finally:
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass


_POOL: Dict[str, SacHostProcess] = {}
_POOL_LOCK = threading.Lock()


def _get_host(sac_version: str, sac_dir: Path) -> SacHostProcess:
    key = str(sac_dir).lower()
    with _POOL_LOCK:
        host = _POOL.get(key)
        if host is None:
            host = SacHostProcess(sac_version, sac_dir)
            _POOL[key] = host
        return host


@atexit.register
def shutdown_hosts() -> None:
    with _POOL_LOCK:
        for host in _POOL.values():
            host.close()
        _POOL.clear()


def native_available() -> bool:
    return select_sac_dir() is not None and shutil.which(str(_safe_csc())) is not None


def _safe_csc() -> Path:
    try:
        return _framework_dir() / "csc.exe"
    except NativeHostError:
        return Path("csc.exe-not-found")


def check_pkt(
    pkt_path: str | Path,
    pkt_version: Optional[str] = None,
    document_check: bool = False,
    timeout: float = 60.0,
) -> Optional[NativeCheckResult]:
    """
    Kiểm định file .pkt bằng DLL gốc của SAC. Trả về None nếu máy không cài Subassembly Composer.
    document_check=True chạy thêm bước mở file bằng SubassemblyDocument (chậm hơn ~2 giây).
    """
    sel = select_sac_dir(pkt_version)
    if sel is None:
        return None
    ver, sac_dir = sel
    path = str(Path(pkt_path).resolve())
    if "\n" in path or "\r" in path:
        raise ValueError("Đường dẫn .pkt không được chứa ký tự xuống dòng.")
    line = path if document_check else f"nodoc|{path}"
    data = _get_host(ver, sac_dir).call(line, timeout)
    if "host_error" in data:
        raise NativeHostError(f"SacHost lỗi nội bộ: {data['host_error']}")
    return NativeCheckResult(
        pkt=data.get("pkt", path),
        sac_version=ver,
        sac_dir=str(sac_dir),
        xaml_load_ok=bool(data.get("xaml_load_ok")),
        validation_ok=bool(data.get("validation_ok")),
        document_ok=data.get("document_ok"),
        xaml_load_error=data.get("xaml_load_error"),
        document_error=data.get("document_error"),
        validation_errors=list(data.get("validation_errors") or []),
        validation_warnings=list(data.get("validation_warnings") or []),
        elapsed_ms=int(data.get("elapsed_ms") or 0),
    )


def activity_catalog(sac_version: Optional[str] = None, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
    """Danh mục activity của Subassembly.ActivityLibrary trên máy (None nếu không cài SAC)."""
    sel = select_sac_dir(sac_version)
    if sel is None:
        return None
    ver, sac_dir = sel
    data = _get_host(ver, sac_dir).call("__CATALOG__", timeout)
    data["sac_version"] = ver
    return data
