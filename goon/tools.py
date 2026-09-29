"""Outside tools the app downloads once (and keeps fresh) instead of shipping them.
Keeps the installer + app updates small, and lets yt-dlp fix itself without a new release.

  tool      comes from                                 re-check every
  ffmpeg    PyPI imageio-ffmpeg wheel (exe inside)     30 days
  deno      PyPI deno wheel (exe inside)               7 days   (YouTube needs it)
  yt-dlp    PyPI yt-dlp + yt-dlp-ejs wheels            1 day    (sites break it often)
  whisper   whisper.cpp GitHub release + ggml model    30 days  (only if ear mode is used)

Lives in %LOCALAPPDATA%\\BrainrotGoonMachine\\tools. Every download is checked against the
sha256 that PyPI / GitHub publish. Old versions stay until the new one works.
If a download fails, the last working version (or the copy bundled in the app) is used.
"""
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import requests

from app_info import APP_NAME, APP_VERSION

from .paths import data_dir

PYPI = os.environ.get("GOON_PYPI", "https://pypi.org/pypi")
GH_API = os.environ.get("GOON_GH_API", "https://api.github.com")
HF = os.environ.get("GOON_HF", "https://huggingface.co")
UA = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
DAY = 86400
REFRESH = {"ffmpeg": 30 * DAY, "deno": 7 * DAY, "yt-dlp": 1 * DAY, "whisper": 30 * DAY}
CORE = ("ffmpeg", "deno", "yt-dlp")

_lock = threading.RLock()
_manifest = None
STATUS = {t: {"state": "unknown", "version": "", "pct": 0, "error": ""}
          for t in (*CORE, "whisper", "model")}


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- places --
def root() -> Path:
    d = data_dir() / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sub(name) -> Path:
    d = root() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest() -> dict:
    global _manifest
    if _manifest is None:
        try:
            _manifest = json.loads((root() / "manifest.json").read_text("utf-8"))
        except (OSError, ValueError):
            _manifest = {}
    return _manifest


def _save_manifest():
    p = root() / "manifest.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest(), indent=2), "utf-8")
    tmp.replace(p)


def _set(tool, **kw):
    STATUS[tool].update(kw)


def _nice(e) -> str:
    """Short human error instead of a Python stack line."""
    from urllib.parse import urlparse
    req = getattr(e, "request", None)
    host = urlparse(getattr(req, "url", "") or "").hostname or "the internet"
    if isinstance(e, requests.exceptions.ConnectionError):
        return f"can't reach {host} (offline or blocked?)"
    if isinstance(e, requests.exceptions.Timeout):
        return f"{host} too slow, timed out"
    if isinstance(e, requests.exceptions.HTTPError) and getattr(e, "response", None) is not None:
        return f"{host} said {e.response.status_code}"
    return str(e)[:200]


def path(tool) -> str | None:
    """Installed path of a tool, or None. Cheap, no network."""
    m = manifest().get(tool)
    if m and m.get("path") and Path(m["path"]).exists():
        return m["path"]
    return None


def status() -> dict:
    out = {}
    for t, s in STATUS.items():
        s = dict(s)
        if s["state"] == "unknown":
            s["state"] = "ok" if (path(t) or (t == "yt-dlp" and bundled_ytdlp())) else "missing"
        m = manifest().get(t) or {}
        s["version"] = s["version"] or m.get("version", "")
        out[t] = s
    out["core_ready"] = all(out[t]["state"] in ("ok", "old") for t in CORE)
    out["busy"] = any(out[t]["state"] == "downloading" for t in out if isinstance(out[t], dict))
    return out


# ------------------------------------------------------------- download --
def _get(url, headers=None, timeout=20, **kw):
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def _download(url, dest: Path, tool, sha256=None, size=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    done = 0
    with requests.get(url, headers=UA, stream=True, timeout=(15, 120)) as r:
        r.raise_for_status()
        total = int(size or r.headers.get("content-length") or 0)
        with open(part, "wb") as f:
            # raw bytes: never let requests un-gzip a .tar.gz (breaks size + sha256 check)
            for chunk in r.raw.stream(1 << 20, decode_content=False):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    _set(tool, pct=min(99, int(done * 100 / total)))
    if total and done != total:
        part.unlink(missing_ok=True)
        raise ToolError(f"download cut off ({done} of {total} bytes)")
    if sha256 and h.hexdigest() != sha256.lower():
        part.unlink(missing_ok=True)
        raise ToolError("download damaged (sha256 no match)")
    part.replace(dest)
    return dest


def _plat_ok(filename: str) -> bool:
    f = filename.lower()
    mach = platform.machine().lower()
    if IS_WIN:
        return "win_amd64" in f if mach in ("amd64", "x86_64") else "win_arm64" in f
    if sys.platform == "darwin":
        return "macosx" in f and (("arm64" in f) if mach == "arm64" else ("x86_64" in f or "intel" in f))
    arch = "aarch64" if mach in ("aarch64", "arm64") else "x86_64"
    return "linux" in f and arch in f


def _pypi(pkg, version=None) -> dict:
    url = f"{PYPI}/{pkg}/{version}/json" if version else f"{PYPI}/{pkg}/json"
    return _get(url).json()


def _pypi_wheel(pkg, version=None, pure=False):
    d = _pypi(pkg, version)
    ver = d["info"]["version"]
    wheels = [f for f in d["urls"] if f["packagetype"] == "bdist_wheel" and not f.get("yanked")]
    pick = next((f for f in wheels if (f["filename"].endswith("-none-any.whl") if pure
                                        else _plat_ok(f["filename"]))), None)
    if not pick:
        raise ToolError(f"no {pkg} build for this computer")
    return ver, pick, d["info"]


def _ver(v) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", str(v))[:4])


def _chmod_x(p: Path):
    if not IS_WIN:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _cleanup(folder: Path, keep: set):
    for p in folder.iterdir():
        if p.name not in keep and not p.name.endswith(".part"):
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
            except OSError:
                pass  # in use (Windows); try again next time


# ---------------------------------------------------- ffmpeg + deno (exe) --
def _install_exe_from_wheel(tool, pkg, pick_member):
    ver, f, _ = _pypi_wheel(pkg)
    old = manifest().get(tool, {})
    if old.get("version") == ver and path(tool):
        old["checked"] = time.time()
        return
    whl = _download(f["url"], _sub("dl") / f["filename"], tool, f["digests"].get("sha256"), f["size"])
    bindir = _sub("bin")
    out = bindir / f"{tool}-{ver}{EXE}"          # versioned name: never overwrite a file in use
    with zipfile.ZipFile(whl) as z:
        member = next((n for n in z.namelist() if pick_member(n)), None)
        if not member:
            raise ToolError(f"{tool} not found inside {f['filename']}")
        with z.open(member) as src, open(out.with_suffix(out.suffix + ".part"), "wb") as dst:
            shutil.copyfileobj(src, dst)
    out.with_suffix(out.suffix + ".part").replace(out)
    _chmod_x(out)
    whl.unlink(missing_ok=True)
    manifest()[tool] = {"version": ver, "path": str(out), "checked": time.time()}
    _save_manifest()
    _cleanup(bindir, {Path(m["path"]).name for m in manifest().values()
                      if m.get("path") and Path(m["path"]).parent == bindir})


def _ffmpeg_member(n):
    base = n.rsplit("/", 1)[-1].lower()
    return n.startswith("imageio_ffmpeg/binaries/") and base.startswith("ffmpeg")


def _deno_member(n):
    return n.rsplit("/", 1)[-1] in ("deno", "deno.exe")


# ------------------------------------------------------------- yt-dlp ----
class _PreferDownloaded(importlib.abc.MetaPathFinder):
    """Makes `import yt_dlp` load the downloaded copy instead of the bundled one."""
    names = ("yt_dlp", "yt_dlp_ejs")

    def __init__(self):
        self.root = None

    def find_spec(self, name, path=None, target=None):
        if not self.root or name.split(".")[0] not in self.names:
            return None
        if "." not in name:
            return importlib.machinery.PathFinder.find_spec(name, [self.root])
        return importlib.machinery.PathFinder.find_spec(name, path)


_finder = _PreferDownloaded()


def _purge_ytdlp_modules():
    for k in [k for k in sys.modules if k.split(".")[0] in _PreferDownloaded.names]:
        del sys.modules[k]
    importlib.invalidate_caches()


def bundled_ytdlp() -> bool:
    """Is there a yt-dlp shipped with the app / installed with pip (the fallback)?"""
    for f in sys.meta_path:
        if f is _finder or not hasattr(f, "find_spec"):
            continue
        try:
            if f.find_spec("yt_dlp", None) is not None:
                return True
        except Exception:
            pass
    return False


def ytdlp_version() -> str:
    try:
        import yt_dlp.version as v
        return v.__version__
    except Exception:
        return ""


def activate_ytdlp() -> str:
    """Point imports at the downloaded yt-dlp. Falls back to the bundled one if it's broken.
    Only call while no download is running."""
    m = manifest().get("yt-dlp") or {}
    want = m.get("path") if m.get("path") and Path(m["path"]).is_dir() else None
    if _finder.root == want and "yt_dlp" in sys.modules:
        return ytdlp_version()
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    _finder.root = want
    _purge_ytdlp_modules()
    try:
        import yt_dlp  # noqa: F401
        from yt_dlp import YoutubeDL  # noqa: F401
    except Exception as e:
        if want:  # broken download: go back to the bundled copy
            m["bad"] = m.get("version")
            m["path"] = ""
            _save_manifest()
            _finder.root = None
            _purge_ytdlp_modules()
            _set("yt-dlp", error=f"new yt-dlp broke ({e}), using built-in one")
            import yt_dlp  # noqa: F401
        else:
            raise
    return ytdlp_version()


def _install_ytdlp():
    ver, f, info = _pypi_wheel("yt-dlp", pure=True)
    m = manifest().get("yt-dlp", {})
    have = m.get("version") if m.get("path") and Path(m["path"]).is_dir() else ytdlp_version()
    if _ver(have) >= _ver(ver) or m.get("bad") == ver:
        m["checked"] = time.time()
        manifest()["yt-dlp"] = m
        _save_manifest()
        return False
    rp = (info.get("requires_python") or "").replace(" ", "")
    mm = re.match(r">=(\d+)\.(\d+)", rp)
    if mm and sys.version_info[:2] < (int(mm.group(1)), int(mm.group(2))):
        raise ToolError(f"yt-dlp {ver} needs newer Python")
    ejs = next((re.search(r"==([\w.]+)", r).group(1) for r in (info.get("requires_dist") or [])
                if r.startswith("yt-dlp-ejs") and "==" in r), None)

    libdir = _sub("pylib")
    target = libdir / f"yt-dlp-{ver}"
    work = libdir / f"yt-dlp-{ver}.part"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    pkgs = [("yt_dlp", f)]
    if ejs:
        _, ef, _ = _pypi_wheel("yt-dlp-ejs", ejs, pure=True)
        pkgs.append(("yt_dlp_ejs", ef))
    for top, wf in pkgs:
        whl = _download(wf["url"], _sub("dl") / wf["filename"], "yt-dlp", wf["digests"].get("sha256"),
                        wf["size"])
        with zipfile.ZipFile(whl) as z:
            for n in z.namelist():
                if n.startswith(top + "/"):
                    z.extract(n, work)
        whl.unlink(missing_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    work.rename(target)
    manifest()["yt-dlp"] = {"version": ver, "path": str(target), "ejs": ejs or "",
                            "checked": time.time()}
    _save_manifest()
    keep = {target.name}
    if m.get("path"):
        keep.add(Path(m["path"]).name)  # keep the previous one as a fallback
    _cleanup(libdir, keep)
    return True


# ------------------------------------------------------------ whisper ----
_BAD_WHISPER = ("cublas", "cuda", "blas", "vulkan", "openvino", "win32", "arm", "xcframework", "sycl")


def _whisper_asset_ok(name: str) -> int:
    """0 = no, 2 = the plain CPU build we want, 1 = acceptable look-alike."""
    n = name.lower()
    if any(b in n for b in _BAD_WHISPER):
        return 0
    if IS_WIN:
        if n == "whisper-bin-x64.zip":
            return 2
        return 1 if re.match(r"whisper.*bin.*(x64|win).*\.zip$", n) else 0
    if sys.platform.startswith("linux"):
        if n == "whisper-bin-ubuntu-x64.tar.gz":
            return 2
        return 1 if re.match(r"whisper.*bin.*(ubuntu|linux).*x64.*\.tar\.gz$", n) else 0
    return 0


def _install_whisper():
    if platform.machine().lower() not in ("amd64", "x86_64") or not (IS_WIN or sys.platform.startswith("linux")):
        raise ToolError("ear mode no work on dis computer (needs 64-bit Windows or Linux)")
    # Newest release is not always one with program files (some are source-only), so look back.
    rels = _get(f"{GH_API}/repos/ggml-org/whisper.cpp/releases?per_page=30",
                headers={"Accept": "application/vnd.github+json"}).json()
    rel, a = None, None
    for r in rels:
        if r.get("draft") or r.get("prerelease"):
            continue
        ok = sorted(((_whisper_asset_ok(x["name"]), x) for x in r.get("assets", [])),
                    key=lambda t: -t[0])
        if ok and ok[0][0]:
            rel, a = r, ok[0][1]
            break
    if not a:
        raise ToolError("no whisper.cpp release with a program for dis computer")
    tag, name = rel["tag_name"], a["name"]
    m = manifest().get("whisper", {})
    if m.get("version") == tag and path("whisper"):
        m["checked"] = time.time()
        _save_manifest()
        return
    digest = str(a.get("digest") or "")
    arc = _download(a["browser_download_url"], _sub("dl") / name, "whisper",
                    digest[7:] if digest.startswith("sha256:") else None, a.get("size"))
    wdir = _sub("whisper")
    target = wdir / tag
    work = wdir / (tag + ".part")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    if name.endswith(".zip"):
        with zipfile.ZipFile(arc) as z:
            z.extractall(work)
    else:
        with tarfile.open(arc) as t:
            t.extractall(work, filter="data")
    arc.unlink(missing_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    work.rename(target)
    cli = next((p for n in (f"whisper-cli{EXE}", f"main{EXE}") for p in target.rglob(n)), None)
    if not cli:
        raise ToolError("whisper-cli not found in download")
    _chmod_x(cli)
    manifest()["whisper"] = {"version": tag, "path": str(cli), "checked": time.time()}
    _save_manifest()
    _cleanup(wdir, {tag})


def model_path(size) -> Path:
    return _sub("models") / f"ggml-{size}.bin"


def ensure_model(size) -> str:
    p = model_path(size)
    if p.exists() and p.stat().st_size > 1_000_000:
        _set("model", state="ok", version=size)
        return str(p)
    with _lock:
        if p.exists() and p.stat().st_size > 1_000_000:
            return str(p)
        _set("model", state="downloading", pct=0, error="", version=size)
        try:
            _download(f"{HF}/ggerganov/whisper.cpp/resolve/main/ggml-{size}.bin", p, "model")
            with open(p, "rb") as f:
                if f.read(4) != b"lmgg":
                    p.unlink(missing_ok=True)
                    raise ToolError("model file looks wrong")
            _set("model", state="ok", pct=100)
            return str(p)
        except Exception as e:
            _set("model", state="error", error=_nice(e))
            raise ToolError(f"ear model download failed: {_nice(e)}") from e


# ---------------------------------------------------------------- ensure --
_INSTALL = {
    "ffmpeg": lambda: _install_exe_from_wheel("ffmpeg", "imageio-ffmpeg", _ffmpeg_member),
    "deno": lambda: _install_exe_from_wheel("deno", "deno", _deno_member),
    "yt-dlp": _install_ytdlp,
    "whisper": _install_whisper,
}


def ensure(tool, refresh=True) -> str | None:
    """Make sure a tool is installed. Downloads if missing; re-checks for updates when due.
    Returns its path (yt-dlp: the version string). Raises ToolError only if there is no
    working copy at all."""
    with _lock:
        m = manifest().get(tool, {})
        have = path(tool) or (tool == "yt-dlp" and bundled_ytdlp())
        due = time.time() - float(m.get("checked", 0)) > REFRESH[tool]
        if have and not (refresh and due):
            _set(tool, state="ok", version=m.get("version", "") or
                 (ytdlp_version() if tool == "yt-dlp" else ""))
            return path(tool) or (ytdlp_version() if tool == "yt-dlp" else None)
        _set(tool, state="downloading", pct=0, error="")
        try:
            changed = _INSTALL[tool]()
            m = manifest().get(tool, {})
            _set(tool, state="ok", pct=100, version=m.get("version", ""))
            if tool == "yt-dlp":
                _set(tool, updated=bool(changed))
        except Exception as e:
            err = _nice(e)
            if have:  # keep using what we have; try again next time
                m = manifest().setdefault(tool, m)
                m["checked"] = time.time() - REFRESH[tool] + 3600  # retry in an hour
                _save_manifest()
                _set(tool, state="ok", error=f"update check failed: {err}")
            else:
                _set(tool, state="error", error=err)
                raise ToolError(f"{tool}: {err}") from e
        return path(tool) or (ytdlp_version() if tool == "yt-dlp" else None)


def ensure_core(refresh=True):
    errors = []
    for t in CORE:
        try:
            ensure(t, refresh)
        except ToolError as e:
            errors.append(str(e))
    if errors:
        raise ToolError("; ".join(errors))


def warmup(on_done=None):
    """Background: install/refresh core tools at startup."""
    def go():
        try:
            ensure_core()
        except ToolError:
            pass
        if on_done:
            on_done()
    threading.Thread(target=go, daemon=True).start()
