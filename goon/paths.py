"""Where stuff lives. Works from source and from a PyInstaller build."""
import os
import sys
from pathlib import Path

from . import APP_NAME

FROZEN = getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Folder holding bundled read-only files (web/, deno.exe)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Folder for config, database, logs, temp downloads."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def tmp_dir() -> Path:
    d = data_dir() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumbs_dir() -> Path:
    d = data_dir() / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_cave() -> Path:
    videos = Path.home() / "Videos"
    return (videos if videos.exists() else Path.home()) / "GoonCave"


def web_dir() -> Path:
    return bundle_dir() / "web"


def ffmpeg_exe() -> str:
    """Downloaded ffmpeg (goon/tools.py). Fallbacks for running from source."""
    from . import tools
    p = tools.path("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        return which("ffmpeg") or "ffmpeg"


def deno_exe() -> str | None:
    """Deno is needed by yt-dlp to solve YouTube's JS challenges."""
    from . import tools
    p = tools.path("deno")
    if p:
        return p
    name = "deno.exe" if os.name == "nt" else "deno"
    local = bundle_dir() / name
    if local.exists():
        return str(local)
    try:
        import deno
        p = deno.find_deno_bin()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    from shutil import which
    return which("deno")
