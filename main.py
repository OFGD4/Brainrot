"""Brainrot Goon Machine 9000 — entry point.

Starts a tiny local server and opens the UI in its own window.
"""
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

from goon.paths import data_dir

# Windowed .exe has no console: send prints to a log file instead of crashing.
_logf = open(data_dir() / "log.txt", "a", encoding="utf-8", buffering=1)
if sys.stdout is None or getattr(sys, "frozen", False):
    sys.stdout = _logf
if sys.stderr is None or getattr(sys, "frozen", False):
    sys.stderr = _logf

PORT = 7676
TITLE = "Brainrot Goon Machine 9000"


def _msgbox(text):
    print(text)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)
        except Exception:
            pass


def _info(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x40)
    except Exception:
        pass


def _port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _already_running(port):
    import requests
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/ping", timeout=1,
                         proxies={"http": None, "https": None})
        return r.ok and r.json().get("ok")
    except Exception:
        return False


def _edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            p = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if p.exists():
                return str(p)
    return None


def open_window(url, engine=None):
    """Prefer a real app window (pywebview). Fallback: Edge app mode, then any browser."""
    try:
        import webview  # pywebview
        webview.create_window(TITLE, url, width=1280, height=860, min_size=(720, 560),
                              background_color="#0d0717")
        webview.start()
        return "closed"
    except Exception as e:
        print("pywebview no work:", e)

    edge = _edge()
    if edge:
        import subprocess
        prof = data_dir() / "edge-profile"
        subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={prof}",
                          "--window-size=1280,860", "--no-first-run"])
    else:
        webbrowser.open(url)
    return "browser"


def selftest():
    """Check every bundled part loads. Run: BrainrotGoonMachine.exe --selftest"""
    import tempfile

    from goon import hw as hwmod, media
    from goon.paths import deno_exe, ffmpeg_exe, web_dir
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            print(f"[ok]   {name}: {fn()}")
        except Exception as e:
            ok = False
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")

    check("version", lambda: __import__("app_info").APP_VERSION + " @ " + __import__("app_info").GITHUB_REPO)
    check("web ui", lambda: (web_dir() / "index.html").exists() or 1 / 0)

    def langs():
        from goon.lang import CODES, pack
        return " | ".join(pack(c)["ui"]["go"] for c in CODES)
    check("languages", langs)
    from goon import tools

    def get_tools():   # first run downloads them (needs internet)
        tools.ensure_core()
        return {t: tools.status()[t]["version"] for t in tools.CORE}
    check("tools download", get_tools)
    check("ffmpeg", lambda: Path(ffmpeg_exe()).exists() and ffmpeg_exe() or 1 / 0)
    check("deno", lambda: deno_exe() or 1 / 0)
    check("yt-dlp", lambda: tools.activate_ytdlp() + " @ " + __import__("yt_dlp").__file__)
    check("yt-dlp-ejs", lambda: __import__("yt_dlp_ejs").__file__)

    def browser_http():   # TikTok / tikwm / Insta answer 403 without this
        from goon import collect, net
        if not net.browser_ok():
            raise RuntimeError("curl_cffi missing")
        return f"curl_cffi {__import__('curl_cffi').__version__}, yt-dlp impersonate: " \
               f"{collect.impersonate_target() or 1 / 0}"
    check("tiktok 403 fix", browser_http)

    def no_ai():
        from goon import aifilter
        assert aifilter.check({"title": "Tralalero Tralala #brainrot"})
        assert aifilter.check({"title": "funny cat", "uploader": "brainrot.ai"})
        assert not aifilter.check({"title": "skibidi toilet sigma edit #fyp", "uploader": "memes"})
        return "AI filter ok"
    check("no AI filter", no_ai)

    def hidden_browser():   # TikTok search in hidden Edge when tikwm is blocked
        import websockets.sync.client  # noqa: F401  (needed to drive it)
        from goon import browser
        return browser.find_browser() or "none found (TikTok uses the other searches)"
    check("hidden browser", hidden_browser)
    check("hardware", lambda: {k: v for k, v in hwmod.detect().items() if k != "all_gpus"})

    def clip():
        import subprocess
        d = Path(tempfile.mkdtemp())
        p = d / "t.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=360x640:rate=15:duration=4", "-f", "lavfi", "-i",
                        "sine=duration=4", "-shortest", "-pix_fmt", "yuv420p", str(p)],
                       check=True, creationflags=0x08000000 if os.name == "nt" else 0)
        fr = media.grab_frames(p, d / 'f', width=360)
        sheet = media.frame_sheet(fr, d / "sheet.jpg")
        return (f"dur={media.duration(p):.1f}s frames={len(fr)} sheet={bool(sheet)} "
                f"hashes={len(media.frame_hashes(p))} sound={media.audio_wav(p, d / 'a.wav')}")
    check("media pipeline", clip)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        report = data_dir() / "selftest.txt"
        with open(report, "w", encoding="utf-8") as f:
            sys.stdout = f
            code = selftest()
        text = report.read_text("utf-8")
        if sys.__stdout__:
            sys.__stdout__.write(text)
            sys.__stdout__.flush()
        if getattr(sys, "frozen", False) and "--quiet" not in sys.argv:
            _msgbox(text) if code else (os.name == "nt" and _info(text))
        os._exit(code)
    port = PORT
    if not _port_free(port):
        if _already_running(port):
            open_window(f"http://127.0.0.1:{port}/")
            return
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    from werkzeug.serving import make_server

    from goon import hw as hwmod
    from goon.config import Config
    from goon.db import DB
    from goon.engine import Engine
    from app_info import APP_VERSION
    from goon.server import create_app, last_ping
    from goon.updater import Updater, parse_version

    cfg = Config()
    db = DB()
    hw = hwmod.detect()
    print("version:", APP_VERSION, "hardware:", hw)
    engine = Engine(cfg, db, hw)
    updater = Updater(cfg)
    if cfg["last_version"] and parse_version(APP_VERSION) > parse_version(cfg["last_version"]):
        engine.log("updated", "good", v="v" + APP_VERSION)
    cfg.update({"last_version": APP_VERSION})
    if updater.state["can_install"]:
        updater.check_later(4)

    # download / refresh ffmpeg, deno, yt-dlp in the background (first run ~75MB)
    from goon import tools
    tools.activate_ytdlp()
    tools.warmup(on_done=lambda: None if engine.running else tools.activate_ytdlp())
    app = create_app(cfg, db, engine, hw, updater)

    srv = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print("serving", url)

    if "--no-window" in sys.argv:
        webbrowser.open(url)
        mode = "browser"
    else:
        mode = open_window(url, engine)

    if mode == "closed":
        engine.request_stop()
        from goon import browser
        browser.shutdown()
        os._exit(0)

    # Browser mode: quit when the page has been gone a while and nothing is running.
    last_ping[0] = time.time()
    while True:
        time.sleep(5)
        idle = time.time() - last_ping[0]
        if idle > 600 and not engine.running:
            from goon import browser
            browser.shutdown()
            os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _msgbox("me crash on start :(\n\n" + traceback.format_exc()[-1500:])
        raise
