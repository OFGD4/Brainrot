"""Build dist/BrainrotGoonMachine/ with PyInstaller. Used by build.bat AND GitHub Actions.

    python build_exe.py                                   local build (version stays as-is)
    python build_exe.py --version 1.2.3 --repo OFGD4/x    stamp app_info.py first (CI does this)
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def stamp(version: str | None, repo: str | None):
    p = ROOT / "app_info.py"
    s = p.read_text("utf-8")
    if version:
        s = re.sub(r"APP_VERSION = '.*?'", f"APP_VERSION = '{version.lstrip('vV')}'", s)
    if repo:
        s = re.sub(r"GITHUB_REPO = '.*?'", f"GITHUB_REPO = '{repo}'", s)
    p.write_text(s, "utf-8")
    print(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version")
    ap.add_argument("--repo")
    a = ap.parse_args()
    if a.version or a.repo:
        stamp(a.version, a.repo)

    sep = os.pathsep  # ';' on Windows, ':' elsewhere
    # ffmpeg, deno, yt-dlp updates and whisper are NOT shipped: goon/tools.py downloads them
    # on first run. yt-dlp is still bundled as a fallback if the download ever fails.
    args = [
        "--noconfirm", "--clean", "--windowed",
        "--name", "BrainrotGoonMachine",
        "--icon", "icon.ico",
        "--add-data", f"web{sep}web",
        "--collect-all", "yt_dlp_ejs",
        "--collect-all", "curl_cffi",          # Chrome look-alike HTTP (TikTok 403 fix)
        "--hidden-import", "_cffi_backend",
        "--collect-submodules", "webview",
    ]
    # Windows curl_cffi keeps its libcurl DLL next to the package (delvewheel "curl_cffi.libs")
    import importlib.util
    spec = importlib.util.find_spec("curl_cffi")
    if spec and spec.origin:
        libs = Path(spec.origin).parent.parent / "curl_cffi.libs"
        if libs.is_dir():
            args += ["--add-binary", f"{libs}{sep}curl_cffi.libs"]
    for mod in ("pandas", "scipy", "matplotlib", "pyarrow", "IPython", "tkinter",
                "faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers",
                "huggingface_hub", "imageio_ffmpeg", "deno", "PIL", "sympy"):
        args += ["--exclude-module", mod]
    args.append("main.py")

    import PyInstaller.__main__
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    sys.exit(main())
