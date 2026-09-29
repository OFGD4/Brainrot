"""Find and download vidas with yt-dlp (YouTube Shorts search + any link yt-dlp knows)."""
import itertools
from pathlib import Path

from .paths import deno_exe, ffmpeg_exe


def YoutubeDL(opts):
    """Imported on every use so the daily-updated yt-dlp (goon/tools.py) takes over."""
    import yt_dlp
    return yt_dlp.YoutubeDL(opts)


class _Log:
    """Swallow yt-dlp chatter; keep the last error for the UI."""
    def __init__(self):
        self.last_error = ""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.last_error = str(msg).replace("ERROR: ", "")[:300]


COOKIES_BROKEN = set()   # browsers whose cookies could not be read this session
warn = None               # engine sets this to log a warning: warn(key, **kw)


def _needs_cookies(url) -> bool:
    """YouTube works without cookies (and Chrome's are usually locked). Only TikTok/Insta/etc."""
    from urllib.parse import urlparse
    host = (urlparse(str(url or "")).hostname or "").lower()
    return bool(host) and not any(h in host for h in ("youtube.com", "youtu.be"))


def base_opts(cfg, url=None) -> dict:
    o = {
        "quiet": True, "no_warnings": True, "noprogress": True,
        "socket_timeout": 20, "retries": 3, "extractor_retries": 2,
        "ffmpeg_location": ffmpeg_exe(),
        "logger": _Log(),
    }
    d = deno_exe()
    if d:
        o["js_runtimes"] = {"deno": {"path": d}}
        o["remote_components"] = ["ejs:github"]  # if yt-dlp wants newer challenge scripts
    if _needs_cookies(url):
        cf = cookie_file()
        b = (cfg["cookies_browser"] or "none").lower()
        if cf:                       # uploaded cookies.txt: works with any browser
            o["cookiefile"] = str(cf)
        elif b != "none" and b not in COOKIES_BROKEN:
            o["cookiesfrombrowser"] = (b,)
    return o


def cookie_file():
    from .paths import data_dir
    p = data_dir() / "cookies.txt"
    return p if p.exists() and p.stat().st_size > 20 else None


def _extract(opts, url, download=False):
    """extract_info, but if the browser's cookies can't be read, carry on without them."""
    try:
        with YoutubeDL(opts) as y:
            return y.extract_info(url, download=download)
    except Exception as e:
        b = (opts.get("cookiesfrombrowser") or [None])[0]
        msg = (str(e) + " " + getattr(opts.get("logger"), "last_error", "")).lower()
        if not b or not any(w in msg for w in ("cookie", "dpapi", "decrypt", "keyring")):
            raise
        COOKIES_BROKEN.add(b)
        if warn:
            warn("cookies_broke", b=b)
        opts = {k: v for k, v in opts.items() if k != "cookiesfrombrowser"}
        with YoutubeDL(opts) as y:
            return y.extract_info(url, download=download)


def _cand(e: dict, query: str) -> dict | None:
    if not e:
        return None
    url = e.get("webpage_url") or e.get("url")
    vid = e.get("id")
    if not url or not vid:
        return None
    if not str(url).startswith("http"):
        if (e.get("ie_key") or "").lower() == "youtube":
            url = f"https://www.youtube.com/watch?v={vid}"
        else:
            return None
    src = (e.get("extractor_key") or e.get("ie_key") or e.get("extractor") or "web").lower()
    src = src.replace("youtubetab", "youtube").split(":")[0]
    return {
        "key": f"{src}:{vid}", "url": url, "id": vid, "src": src,
        "title": e.get("title") or "", "uploader": e.get("uploader") or e.get("channel") or "",
        "duration": e.get("duration") or 0, "tags": e.get("tags") or [],
        "description": e.get("description") or "", "query": query,
        "live": bool(e.get("is_live") or e.get("live_status") == "is_live"),
    }


SHORT_VIDEOS = "EgQQARgB"   # YouTube search filter: type=video + duration under 4 minutes


def search_url(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={SHORT_VIDEOS}"


def search_youtube(query: str, n: int, cfg):
    """YouTube search limited to short videos (Shorts + clips under 4 min)."""
    url = search_url(query)
    opts = {**base_opts(cfg, url), "extract_flat": "in_playlist", "skip_download": True,
            "playlistend": n}
    info = _extract(opts, url) or {}
    for e in itertools.islice(info.get("entries") or [], n):
        c = _cand(e, query)
        if c:
            yield c


def _cand_from_url(url, src, query):
    vid = url.rstrip("/").rsplit("/", 1)[-1]
    return {"key": f"{src}:{vid}", "url": url, "id": vid, "src": src, "title": "", "uploader": "",
            "duration": 0, "tags": [], "description": "", "query": query, "live": False}


warned = set()   # (site, reason) already told to the user this run


def _say(site, why, q):
    if warn and (site, why) not in warned:
        warned.add((site, why))
        warn("site_empty", site=site, q=q[:40], why=why[:160])


def search_tiktok(query: str, n: int, cfg):
    """TikTok: 1) tikwm search (no login)  2) web search for videos + creators."""
    from . import websearch
    got = 0
    try:
        for v in websearch.tikwm_search(query, n):
            c = _cand_from_url(v["url"], "tiktok", query)
            c.update(id=v["id"], key=f"tiktok:{v['id']}", title=v["title"], duration=v["duration"],
                     uploader=v["author"], direct=v["play"])
            got += 1
            yield c
    except Exception as e:
        _say("TikTok", f"tikwm: {e}", query)
    if got:
        return
    try:
        videos, users = websearch.tiktok_links(query)
    except Exception as e:
        _say("TikTok", f"web search: {e}", query)
        return
    if not videos and not users:
        _say("TikTok", "web search found no tiktok links", query)
    for url in videos[:n]:
        yield _cand_from_url(url, "tiktok", query)
    for u in users[:10]:           # creators who post this stuff: grab their recent vids
        try:
            yield from expand_link(f"https://www.tiktok.com/@{u}", 12, cfg, query=query)
        except Exception:
            continue               # private / gone profile: next creator


def search_instagram(query: str, n: int, cfg):
    """Instagram: 1) its own search as you (needs cookies.txt)  2) web search for reels."""
    from . import websearch
    got = 0
    cf = cookie_file()
    if cf:
        try:
            for v in websearch.instagram_api(query, cf, n):
                c = _cand_from_url(v["url"], "instagram", query)
                c.update(title=v["title"][:200], duration=v["duration"], uploader=v["author"])
                got += 1
                yield c
        except Exception as e:
            _say("Instagram", f"logged-in search: {e}", query)
    else:
        _say("Instagram", "no cookies.txt with instagram login, only web search", query)
    if got:
        return
    try:
        reels = websearch.instagram_links(query)
    except Exception as e:
        _say("Instagram", f"web search: {e}", query)
        return
    if not reels:
        _say("Instagram", "web search found no reels", query)
    for url in reels[:n]:
        yield _cand_from_url(url, "instagram", query)


def expand_link(url: str, n: int, cfg, query=None):
    """A single video, a playlist, a channel's Shorts tab, a TikTok user/tag, etc."""
    opts = {**base_opts(cfg, url), "extract_flat": "in_playlist", "skip_download": True,
            "playlistend": n}
    info = _extract(opts, url) or {}
    entries = info.get("entries")
    if entries is None:
        c = _cand(info, query or url)
        if c:
            yield c
        return
    for e in itertools.islice(entries, n):
        c = _cand(e, query or url)
        if c:
            yield c


def download(cand: dict, out_dir: Path, cfg, stop=None) -> tuple[Path, dict]:
    log = _Log()
    max_secs = cfg["max_secs"]

    def hook(d):   # STOP pressed: abort the download right away
        if stop is not None and stop.is_set():
            from yt_dlp.utils import DownloadCancelled
            raise DownloadCancelled("stopped")
    opts = {
        **base_opts(cfg, cand["url"]), "logger": log,
        "outtmpl": str(Path(out_dir) / "%(id)s.%(ext)s"),
        "format": "bv*+ba/b",
        "format_sort": ["res:720", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "noplaylist": True, "overwrites": True,
        "max_filesize": 300 * 1024 * 1024,
        "match_filter": _filter(max_secs),
        "progress_hooks": [hook],
    }
    try:
        info = _extract(opts, cand["url"], download=True)
    except Exception as e:  # yt-dlp raises DownloadError with the useful text
        if cand.get("direct") and not (stop is not None and stop.is_set()):
            return _direct(cand, out_dir, stop)
        raise RuntimeError(log.last_error or str(e)) from e
    if not info:
        raise RuntimeError(log.last_error or "no info")
    if info.get("entries"):
        info = next(iter(info["entries"]), None) or {}
    dl = (info.get("requested_downloads") or [{}])[0]
    path = Path(dl.get("filepath") or dl.get("_filename") or "")
    if not path.is_file():
        dur = info.get("duration") or 0
        if dur and dur > max_secs:
            raise TooLong(dur)
        raise RuntimeError(log.last_error or "file no appear")
    return path, info


def _direct(cand, out_dir, stop=None):
    """Plain download of a video file link (tikwm gives these for TikTok)."""
    import requests
    from .websearch import HEADERS
    path = Path(out_dir) / f"{cand['id']}.mp4"
    with requests.get(cand["direct"], headers=HEADERS, stream=True, timeout=(15, 60)) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if stop is not None and stop.is_set():
                    raise RuntimeError("stopped")
                f.write(chunk)
    if path.stat().st_size < 10_000:
        raise RuntimeError("tiktok video file came back empty")
    return path, {"title": cand.get("title"), "duration": cand.get("duration"),
                  "uploader": cand.get("uploader")}


class TooLong(Exception):
    pass


def _filter(max_secs):
    def f(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            return "live stream"
        d = info.get("duration")
        if d and d > max_secs:
            return f"too long ({d}s)"
        return None
    return f
