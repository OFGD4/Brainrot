"""TikTok search in a real, hidden Edge (or Chrome), driven over the DevTools protocol.

Why: tikwm often blocks whole internet connections (403), and TikTok's own search API only
answers a real browser (its web page signs every search request with JavaScript). So the app
opens the Edge that is already on every Windows PC, hidden (no window), logs in with YOUR
cookies.txt, opens tiktok.com/search like a person would, and reads the search answers the
page receives. No extra download. Used only when tikwm can't search.

Tries headless first; if TikTok shows nothing there, an off-screen (not headless) window.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .paths import data_dir

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TT = os.environ.get("GOON_TT", "https://www.tiktok.com")
_lock = threading.Lock()      # one search at a time in the one hidden tab
_browser = [None]
_gen = [0]                    # bumped by shutdown(): a search from an old run must not restart it


class BrowserError(Exception):
    pass


def find_browser() -> str | None:
    env = os.environ.get("GOON_BROWSER")
    if env and Path(env).exists():
        return env
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                     os.environ.get("LOCALAPPDATA")):
            for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe",
                        "BraveSoftware/Brave-Browser/Application/brave.exe"):
                if base and (Path(base) / rel).exists():
                    return str(Path(base) / rel)
        return None
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        w = shutil.which(name)
        if w:
            return w
    return None


class _CDP:
    """Tiny DevTools protocol client over one websocket."""

    def __init__(self, ws_url):
        from websockets.sync.client import connect
        try:
            self.ws = connect(ws_url, max_size=None, open_timeout=15, proxy=None)   # never via a proxy
        except TypeError:                                                       # older websockets
            self.ws = connect(ws_url, max_size=None, open_timeout=15)
        self.n = 0
        self.events = []

    def send(self, method, params=None, timeout=20):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise BrowserError(f"browser no answer to {method}")
            msg = json.loads(self.ws.recv(timeout=left))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise BrowserError(str(msg["error"].get("message"))[:120])
                return msg.get("result") or {}
            if "method" in msg:
                self.events.append(msg)

    def pump(self, secs):
        """Collect events for a while."""
        end = time.time() + secs
        while True:
            left = end - time.time()
            if left <= 0:
                return
            try:
                msg = json.loads(self.ws.recv(timeout=left))
            except TimeoutError:
                return
            if "method" in msg:
                self.events.append(msg)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


class Browser:
    def __init__(self, exe, headless=True):
        self.headless = headless
        self.profile = data_dir() / "tiktok-browser"
        self.profile.mkdir(parents=True, exist_ok=True)
        port_file = self.profile / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        args = [exe, f"--user-data-dir={self.profile}", "--remote-debugging-port=0",
                "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                "--mute-audio", "--disable-blink-features=AutomationControlled",
                "--disable-background-networking", "--window-size=1280,900", "--lang=en-US",
                "--autoplay-policy=user-gesture-required"]
        if headless:
            args.append("--headless=new")
        else:   # a real window, but far off screen
            args += ["--window-position=-32000,-32000"]
        if os.name != "nt" and os.geteuid() == 0:
            args.append("--no-sandbox")
        args.append("about:blank")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=NO_WINDOW)
        end = time.time() + 20
        while not (port_file.exists() and port_file.stat().st_size > 0):
            if self.proc.poll() is not None or time.time() > end:
                self.close()
                raise BrowserError("browser would not start")
            time.sleep(0.1)
        port = int(port_file.read_text().split()[0])
        s = requests.Session()
        s.trust_env = False
        pages = [p for p in s.get(f"http://127.0.0.1:{port}/json/list", timeout=5).json()
                 if p.get("type") == "page"]
        if not pages:
            pages = [s.put(f"http://127.0.0.1:{port}/json/new?about:blank", timeout=5).json()]
        ver = s.get(f"http://127.0.0.1:{port}/json/version", timeout=5).json()
        self.cdp = _CDP(pages[0]["webSocketDebuggerUrl"])
        self.cdp.send("Network.enable", {"maxResourceBufferSize": 20_000_000})
        self.cdp.send("Page.enable")
        # look like the normal browser, not "HeadlessChrome" controlled by a robot
        ua = ver.get("User-Agent", "").replace("HeadlessChrome", "Chrome").replace("HeadlessEdg", "Edg")
        major = (ua.split("Chrome/")[-1].split(".")[0] if "Chrome/" in ua else "140") or "140"
        edge = "Edg/" in ua
        self.cdp.send("Network.setUserAgentOverride", {
            "userAgent": ua, "acceptLanguage": "en-US,en;q=0.9", "platform": "Win32",
            "userAgentMetadata": {
                "brands": [{"brand": "Chromium", "version": major},
                           {"brand": "Microsoft Edge" if edge else "Google Chrome", "version": major},
                           {"brand": "Not=A?Brand", "version": "24"}],
                "platform": "Windows", "platformVersion": "10.0.0", "architecture": "x86",
                "model": "", "mobile": False}})
        self.cdp.send("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"})
        self.cookies_done = False

    def alive(self):
        return self.proc.poll() is None

    def set_cookies(self, cookies):
        items = []
        for c in cookies:
            dom = c.domain if c.domain.startswith(".") else "." + c.domain.lstrip(".")
            it = {"name": c.name, "value": c.value, "domain": dom, "path": c.path or "/",
                  "secure": bool(c.secure),
                  "httpOnly": bool(c.has_nonstandard_attr("HTTPOnly") or c.has_nonstandard_attr("HttpOnly"))}
            if c.expires:
                it["expires"] = float(c.expires)
            items.append(it)
        if items:
            self.cdp.send("Network.setCookies", {"cookies": items})
        self.cookies_done = True

    def js(self, expr, timeout=15):
        r = self.cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                               "awaitPromise": True}, timeout=timeout)
        return (r.get("result") or {}).get("value")

    def close(self):
        try:
            self.cdp.close()
        except Exception:
            pass
        try:
            if os.name == "nt":      # the whole Edge process tree, not just the main one
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               capture_output=True, creationflags=NO_WINDOW, timeout=10)
            self.proc.terminate()
            self.proc.wait(5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def shutdown():
    """Close the hidden browser (end of a run / STOP / app exit). Never waits for a search:
    killing the browser makes a running search fail at once."""
    _gen[0] += 1
    b, _browser[0] = _browser[0], None
    if b:
        b.close()


def _get(headless=True, gen=None) -> Browser:
    if gen is not None and gen != _gen[0]:
        raise BrowserError("stopped")
    b = _browser[0]
    if b and b.alive() and b.headless == headless:
        return b
    if b:
        b.close()
    exe = find_browser()
    if not exe:
        raise BrowserError("no Edge / Chrome found on this pc")
    _browser[0] = Browser(exe, headless)
    return _browser[0]


def _items_from(data) -> list[dict]:
    """TikTok search answers: item_list[] (video tab) or data[].item (general tab)."""
    items = list(data.get("item_list") or [])
    for e in data.get("data") or []:
        if isinstance(e, dict) and e.get("type") == 1 and e.get("item"):
            items.append(e["item"])
    return items


_DOM_JS = r"""(() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href*="/video/"]')) {
    const m = a.href.match(/@([\w.\-]+)\/video\/(\d+)/);
    if (!m) continue;
    const box = a.closest('[data-e2e="search_video-item"], [class*="DivItemContainer"]') || a;
    const cap = box.querySelector('[data-e2e="search-card-video-caption"], [data-e2e="search-card-desc"]');
    const img = a.querySelector('img');
    out.push({user: m[1], id: m[2], desc: (cap && cap.innerText) || (img && img.alt) || ''});
  }
  return out;
})()"""
_CAPTCHA_JS = r"""!!document.querySelector('#captcha-verify-container, [id*="captcha"], [class*="captcha"], .captcha_verify_container')"""


def _search_once(b, query, n):
    from .websearch import BlockedError
    b.cdp.events.clear()
    b.cdp.send("Page.navigate", {"url": f"{TT}/search/video?q={quote(query)}"})
    found, order, want = {}, [], set()
    quiet_since, scrolls = time.time(), 0
    end = time.time() + 40
    while time.time() < end and len(order) < n:
        b.cdp.pump(0.7)
        evs, b.cdp.events = b.cdp.events, []
        for ev in evs:
            p = ev.get("params") or {}
            if ev["method"] == "Network.responseReceived":
                url = (p.get("response") or {}).get("url", "")
                if "/api/search/" in url:
                    want.add(p["requestId"])
            elif ev["method"] == "Network.loadingFinished" and p.get("requestId") in want:
                want.discard(p["requestId"])
                try:
                    body = b.cdp.send("Network.getResponseBody", {"requestId": p["requestId"]})
                    data = json.loads(body.get("body") or "{}")
                except Exception:
                    continue
                for it in _items_from(data):
                    vid = str(it.get("id") or "")
                    if vid and vid not in found:
                        found[vid] = it
                        order.append(vid)
                        quiet_since = time.time()
        if time.time() - quiet_since > 3.5:          # nothing new for a bit: scroll for more
            if scrolls >= 6:
                break
            if scrolls == 0 and not order and b.js(_CAPTCHA_JS):
                raise BlockedError("tiktok wants a captcha (open tiktok.com in Edge once, then retry)")
            b.js("window.scrollBy(0, document.body.scrollHeight)")
            scrolls += 1
            quiet_since = time.time()
    items = [found[v] for v in order]
    if not items:                                   # no search answers caught: read the page itself
        for d in b.js(_DOM_JS) or []:
            if d["id"] not in found:
                found[d["id"]] = 1
                items.append({"id": d["id"], "desc": d.get("desc") or "",
                              "author": {"uniqueId": d["user"]}})
    return items[:n]


def tiktok_search(query: str, n: int = 30, cookie_path=None) -> list[dict]:
    """TikTok videos for these words, from TikTok's own website in a hidden browser.
    Returns the same dicts as websearch.tikwm_search (no 'play' link)."""
    from . import aifilter
    from .websearch import BlockedError, load_cookies
    gen = _gen[0]
    with _lock:
        items, last = [], None
        for headless in (True, False):
            if gen != _gen[0]:
                raise BlockedError("stopped")
            try:
                b = _get(headless, gen)
                if not b.cookies_done:
                    jar = load_cookies(cookie_path, "tiktok.com") if cookie_path else None
                    b.set_cookies([c for c in jar if "tiktok" in c.domain] if jar else [])
                items = _search_once(b, query, n)
            except BlockedError:
                raise
            except Exception as e:
                last = e
                items = []
            if items:
                break
        if not items:
            raise BlockedError("tiktok in hidden browser showed nothing" +
                               (f" ({str(last)[:80]})" if last else "") +
                               ("" if cookie_path else " (give me cookies.txt with ur tiktok login)"))
    out = []
    for it in items:
        vid = str(it.get("id") or "")
        user = ((it.get("author") or {}).get("uniqueId") or "").strip()
        if not vid or it.get("imagePost"):
            continue
        mu = it.get("music") or {}
        vd = it.get("video") or {}
        play = vd.get("playAddr") or vd.get("downloadAddr") or ""     # backup download link
        if isinstance(play, dict):
            play = (play.get("UrlList") or play.get("url_list") or [""])[0]
        out.append({"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
                    "title": it.get("desc") or "", "duration": vd.get("duration") or 0,
                    "author": user, "play": play if str(play).startswith("http") else "",
                    "ai_label": aifilter.label_hit(it),
                    "music_id": str(mu.get("id") or ""), "music": mu.get("title") or "",
                    "tags": [c.get("title") for c in (it.get("challenges") or []) if c.get("title")]})
    return out
