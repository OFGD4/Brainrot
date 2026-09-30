import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from app_info import APP_VERSION
from .brain import BrainError
from .paths import web_dir
from . import tools
from .lang import pack, say, war

last_ping = [time.time()]


def create_app(cfg, db, engine, hw, updater):
    app = Flask(__name__, static_folder=None)
    pull_state = {"running": False}

    @app.get("/")
    def index():
        return send_from_directory(web_dir(), "index.html")

    @app.get("/web/<path:name>")
    def web(name):
        return send_from_directory(web_dir(), name)

    @app.get("/api/ping")
    def ping():
        last_ping[0] = time.time()
        return {"ok": True}

    @app.get("/api/hello")
    def hello():
        return {"version": APP_VERSION, "hello": say("hello", cfg["lang"]), "hw": hw,
                "config": cfg.public(), "stats": db.stats(), "lang": cfg["lang"],
                "update": updater.public()}

    @app.get("/api/lang")
    def lang():
        return pack(request.args.get("code") or cfg["lang"])

    @app.get("/api/status")
    def status():
        last_ping[0] = time.time()
        since = request.args.get("since", 0, type=int)
        lines = [l for l in list(engine.log_lines) if l["i"] > since]
        return {"running": engine.running or pull_state["running"], "progress": engine.progress,
                "log": lines, "brain": engine.brain_label, "update": updater.public(),
                "tools": tools.status()}

    @app.get("/api/war")
    def lang_war():
        return war(request.args.get("from", ""), request.args.get("to", ""))

    # ----------------------------------------------------------- cookies --
    def _cookie_rows(text):
        """Netscape cookies.txt lines keyed by (domain, path, name). Keeps #HttpOnly_ lines."""
        out = {}
        for line in (text or "").splitlines():
            line = line.rstrip("\r")
            if not line.strip() or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            out[(parts[0].replace("#HttpOnly_", "").lstrip("."), parts[2], parts[5])] = line
        return out

    def _cookie_status():
        from .collect import cookie_file
        f = cookie_file()
        if not f:
            return {"loaded": False, "sites": []}
        text = f.read_text("utf-8", errors="ignore")
        login = {"tiktok.com": ("sessionid", "sid_tt"), "instagram.com": ("sessionid",)}
        rows = _cookie_rows(text)
        sites = []
        for name, dom in (("TikTok", "tiktok.com"), ("Instagram", "instagram.com"), ("YouTube", "youtube.com")):
            mine = {k[2] for k in rows if k[0].endswith(dom)}
            if mine:   # say if it's a real login or just visitor cookies
                sites.append(name + (" ✓" if any(n in mine for n in login.get(dom, ())) else " (not logged in)"))
        return {"loaded": True, "sites": sites}

    @app.get("/api/cookies")
    def cookies_get():
        return _cookie_status()

    @app.post("/api/cookies")
    def cookies_set():
        """Add a cookies.txt. MERGED with the one already there, so you can give the TikTok file
        and the Instagram file one after the other (same cookie in both = the new one wins)."""
        text = request.get_data(as_text=True) or ""
        rows = _cookie_rows(text)
        if not rows:
            return {**_cookie_status(), "bad": True}, 400
        from .paths import data_dir
        f = data_dir() / "cookies.txt"
        have = _cookie_rows(f.read_text("utf-8", errors="ignore")) if f.exists() else {}
        have.update(rows)
        f.write_text("# Netscape HTTP Cookie File\n" + "\n".join(have.values()) + "\n", "utf-8")
        from . import collect
        collect.COOKIES_BROKEN.clear()
        return _cookie_status()

    @app.post("/api/cookies/clear")
    def cookies_clear():
        from .paths import data_dir
        (data_dir() / "cookies.txt").unlink(missing_ok=True)
        return _cookie_status()

    # ------------------------------------------------------------- tools --
    @app.get("/api/tools")
    def tools_state():
        return tools.status()

    @app.post("/api/tools/retry")
    def tools_retry():
        tools.warmup(on_done=lambda: None if engine.running else tools.activate_ytdlp())
        return tools.status()

    # ----------------------------------------------------------- updates --
    @app.get("/api/update")
    def update_state():
        return updater.public()

    @app.post("/api/update/check")
    def update_check():
        return updater.check()

    @app.post("/api/update/skip")
    def update_skip():
        updater.skip()
        return updater.public()

    @app.post("/api/update/install")
    def update_install():
        ok = updater.install(before_exit=engine.request_stop)
        return {"ok": ok, **updater.public()}

    @app.get("/api/config")
    def get_config():
        return cfg.public()

    @app.post("/api/config")
    def set_config():
        cfg.update(request.get_json(force=True) or {})
        return cfg.public()

    @app.get("/api/brain")
    def brain():
        try:
            st = engine.brain_status()
        except Exception as e:
            st = {"state": "error", "error": str(e)[:200]}
        st["hw_model"] = hw["model"]
        return st

    @app.post("/api/brain/pull")
    def brain_pull():
        if engine.running or pull_state["running"]:
            return {"ok": False}

        def go():
            pull_state["running"] = True
            try:
                b = engine._ollama()
                if not b.alive():
                    engine.log("ollama_starting")
                    if not b.try_start():
                        engine.log("no_ollama", "bad")
                        return
                engine.prepare_brain(b, threading.Event())
            except BrainError as e:
                engine.log("brain_fail", "bad", err=str(e))
            except Exception as e:
                engine.log("crash", "bad", err=str(e)[:200])
            finally:
                pull_state["running"] = False
                engine.step("")
        threading.Thread(target=go, daemon=True).start()
        return {"ok": True}

    @app.post("/api/start")
    def start():
        d = request.get_json(force=True) or {}
        ok = engine.start(d.get("query", ""), d.get("links", ""), d.get("count", 10))
        return {"ok": ok}

    @app.post("/api/stop")
    def stop():
        engine.request_stop()
        t0 = time.time()                       # the engine walks away from slow stuff in <0.2s
        while engine.running and time.time() - t0 < 1.5:
            time.sleep(0.03)
        return {"ok": True, "running": engine.running}

    @app.get("/api/vids")
    def vids():
        sort = request.args.get("sort", "new")
        out = []
        for v in db.kept(sort):
            if not v["path"] or not Path(v["path"]).exists():
                continue
            out.append({k: v[k] for k in ("id", "title", "uploader", "duration", "score",
                                          "vibe", "why", "url", "query", "brain", "created")}
                       | {"has_thumb": bool(v["thumb"] and Path(v["thumb"]).exists()),
                          "gem": bool(v.get("gem")),
                          "site": (v["key"] or "web:").split(":")[0]})
        return jsonify(out)

    @app.get("/vid/<int:vid>/file")
    def vid_file(vid):
        v = db.get(vid)
        if not v or not v["path"] or not Path(v["path"]).exists():
            abort(404)
        return send_file(v["path"], conditional=True)

    @app.get("/vid/<int:vid>/thumb")
    def vid_thumb(vid):
        v = db.get(vid)
        if not v or not v["thumb"] or not Path(v["thumb"]).exists():
            abort(404)
        return send_file(v["thumb"], max_age=86400)

    @app.post("/vid/<int:vid>/yeet")
    def vid_yeet(vid):
        v = db.get(vid)
        if not v:
            abort(404)
        for p in (v["path"], v["thumb"]):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
        db.set_status(vid, "yeeted")
        return {"ok": True}

    @app.post("/vid/<int:vid>/show")
    def vid_show(vid):
        v = db.get(vid)
        if v and v["path"] and Path(v["path"]).exists():
            _reveal(Path(v["path"]))
        return {"ok": True}

    @app.post("/api/open_cave")
    def open_cave():
        _open(cfg.cave())
        return {"ok": True}

    @app.post("/api/open_link")
    def open_link():
        url = (request.get_json(force=True) or {}).get("url", "")
        if url.startswith("https://"):
            import webbrowser
            webbrowser.open(url)
        return {"ok": True}

    return app


def _open(p: Path):
    if os.name == "nt":
        os.startfile(str(p))  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def _reveal(p: Path):
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        _open(p.parent)
