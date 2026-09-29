"""Find TikTok / Instagram video links with a normal web search.

yt-dlp can download single TikTok videos, TikTok profiles and Instagram reels, but it has no
working search for those sites. So: ask DuckDuckGo (Bing as backup) for
"<words> site:tiktok.com" and pull the video / profile / reel links out of the results page.
"""
import base64
import os
import re
import threading
import time
from urllib.parse import quote_plus, unquote

from . import aifilter, net

_last = [0.0]
_pace = threading.Lock()   # searches run side by side: keep ONE polite queue per website

TT_VIDEO = re.compile(r"https?://(?:www\.|m\.)?tiktok\.com/@([\w.\-]+)/video/(\d+)")
TT_USER = re.compile(r"https?://(?:www\.|m\.)?tiktok\.com/@([\w.\-]+)")
IG_REEL = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[\w.\-]+/)?(?:reels?|tv)/([\w\-]{5,})")


class BlockedError(Exception):
    pass


def _polite():
    """Don't hammer the search engines (they block fast)."""
    with _pace:
        wait = 1.5 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def urls_in(html: str) -> list[str]:
    """Every result URL on a search page, including DuckDuckGo (uddg=) and Bing (u=a1...) redirects."""
    html = html.replace("&amp;", "&")
    found = []
    for m in re.finditer(r"uddg=([^&\"'>\s]+)", html):
        found.append(unquote(m.group(1)))
    for m in re.finditer(r"[?&]u=a1([A-Za-z0-9_\-]+)", html):
        b = m.group(1)
        try:
            found.append(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "ignore"))
        except ValueError:
            pass
    found += re.findall(r"https?://(?:www\.|m\.)?(?:tiktok|instagram)\.com/[^\s\"'<>\\]+", html)
    out, seen = [], set()
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _ddg(q):
    _polite()
    r = net.get(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}", timeout=15)
    if r.status_code != 200 or "anomaly" in r.text.lower():
        raise BlockedError(f"duckduckgo said {r.status_code}")
    return r.text


def _bing(q):
    _polite()
    r = net.get(f"https://www.bing.com/search?q={quote_plus(q)}&count=50", timeout=15)
    if r.status_code != 200:
        raise BlockedError(f"bing said {r.status_code}")
    return r.text


def search(query: str, site: str) -> list[str]:
    """Result URLs for `query site:<site>`. Tries DuckDuckGo, then Bing."""
    q = f"{query} site:{site}"
    errors = []
    for engine in (_ddg, _bing):
        try:
            domain = site.split("/")[0]
            urls = [u for u in urls_in(engine(q)) if domain in u]
            if urls:
                return urls
        except Exception as e:
            errors.append(net.nice(e)[:80])
    if errors and len(errors) == 2:
        raise BlockedError("search engines blocked me: " + "; ".join(errors))
    return []


_NOT_USERS = {"discover", "tag", "music", "explore", "search", "foryou", "live"}


def _both(query, site):
    """Search the words AND the hashtag (#italianbrainrot): hashtags pull more real posts."""
    urls, errs = [], []
    tag = "#" + re.sub(r"[^\w]", "", query)
    for q in (query, tag):
        try:
            urls += search(q, site)
        except BlockedError as e:
            errs.append(e)
    if not urls and errs:
        raise errs[0]
    return urls


def tiktok_links(query: str) -> tuple[list[str], list[str]]:
    """(video urls, creator names) found for these words."""
    videos, users, vseen, useen = [], [], set(), set()
    for u in _both(query, "tiktok.com"):
        m = TT_VIDEO.match(u)
        if m and m.group(2) not in vseen:
            vseen.add(m.group(2))
            videos.append(f"https://www.tiktok.com/@{m.group(1)}/video/{m.group(2)}")
        m = TT_USER.match(u)
        if m and m.group(1).lower() not in _NOT_USERS and m.group(1) not in useen:
            useen.add(m.group(1))
            users.append(m.group(1))
    return videos, users


def instagram_links(query: str) -> list[str]:
    reels, seen = [], set()
    for u in _both(query, "instagram.com/reel"):
        m = IG_REEL.match(u)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            reels.append(f"https://www.instagram.com/reel/{m.group(1)}/")
    return reels


# ================================================================ TikTok ====
# tikwm.com: free public TikTok search (used by many open-source tools). No login.
# Its free limit is per internet connection: too many calls close together and it answers
# 403 for a minute or more. So: one call every 2.5s for the whole app, never a second try
# on a 403, and a growing rest (20s, 45s, 90s, 180s) after each 403.
TIKWM = os.environ.get("GOON_TIKWM", "https://www.tikwm.com")
TIKWM_GAP = 2.5
_REST = tuple(int(x) for x in os.environ.get("GOON_TIKWM_REST", "20,45,90,180").split(","))
_tikwm = {"next": 0.0, "until": 0.0, "strikes": 0}
_tikwm_lock = threading.Lock()
_TIKWM_HEADERS = {"Referer": TIKWM + "/", "Origin": TIKWM, "X-Requested-With": "XMLHttpRequest"}


class TikwmResting(BlockedError):
    """tikwm said 403 (too many searches from this internet). Try again after `wait` seconds."""
    def __init__(self, wait, msg):
        super().__init__(msg)
        self.wait = wait


def tikwm_rest_left() -> float:
    return max(0.0, _tikwm["until"] - time.time())


def tikwm_strikes() -> int:
    return _tikwm["strikes"]


def _tikwm_slot(max_wait):
    """Book the next free moment to call tikwm (shared by every search). Sleeps until then."""
    with _tikwm_lock:
        now = time.time()
        if _tikwm["until"] - now > max_wait:
            raise TikwmResting(_tikwm["until"] - now, "tikwm is resting (it said 403: too many "
                               f"searches from ur internet), back in {int(_tikwm['until'] - now)}s")
        slot = max(now, _tikwm["next"], _tikwm["until"])
        _tikwm["next"] = slot + TIKWM_GAP
    if slot > now:
        time.sleep(slot - now)


def _tikwm_blocked(status):
    with _tikwm_lock:
        _tikwm["strikes"] += 1
        rest = _REST[min(_tikwm["strikes"], len(_REST)) - 1]
        _tikwm["until"] = max(_tikwm["until"], time.time() + rest)
    return TikwmResting(rest, f"tikwm said {status} (too many searches from ur internet), "
                              f"it rests {rest}s")


def _tikwm_call(path, params, max_wait=25):
    """One polite tikwm call (POST, like its website). Returns the 'data' part."""
    _tikwm_slot(max_wait)
    try:
        r = net.post(TIKWM + path, data=params, headers=_TIKWM_HEADERS, timeout=20)
        if r.status_code in (404, 405):                  # POST not allowed: try GET once
            r = net.get(TIKWM + path, params=params, headers=_TIKWM_HEADERS, timeout=20)
    except Exception as e:
        raise BlockedError(f"tikwm unreachable ({net.nice(e)[:80]})") from e
    if r.status_code in (403, 429):
        raise _tikwm_blocked(r.status_code)
    if r.status_code != 200:
        raise BlockedError(f"tikwm said {r.status_code}")
    try:
        d = r.json()
    except ValueError:
        raise BlockedError("tikwm sent a web page, not data")
    if d.get("code") not in (0, None):
        msg = str(d.get("msg") or d.get("code"))
        if "limit" in msg.lower():                       # "Free Api Limit: 1 request/second"
            raise _tikwm_blocked("'limit'")
        raise BlockedError(f"tikwm: {msg}")
    with _tikwm_lock:
        _tikwm["strikes"] = 0
    return d.get("data") or {}


def _abs(u):
    return TIKWM + u if u and u.startswith("/") else (u or "")


def tikwm_search(query: str, n: int = 30, on_wait=None):
    """Yield TikTok videos for these words: dicts with id, url, title, duration, author, play.
    tikwm resting (it said 403)? Raises TikwmResting at once; the caller tries other searches."""
    cursor, got, waited = 0, 0, False
    for _page in range(max(1, min(5, -(-n // 30)))):
        while True:
            try:
                data = _tikwm_call("/api/feed/search",
                                   {"keywords": query, "count": 30, "cursor": cursor, "hd": 1})
                break
            except TikwmResting as e:
                if on_wait:
                    on_wait(int(e.wait))
                if waited or e.wait > 5 or got:
                    raise                    # the caller uses TikTok's own search meanwhile
                waited = True
        for v in data.get("videos") or []:
            vid = str(v.get("video_id") or v.get("id") or "")
            user = ((v.get("author") or {}).get("unique_id") or "").strip()
            if not vid:
                continue
            yield {"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
                   "title": v.get("title") or "", "duration": v.get("duration") or 0,
                   "author": user, "play": _abs(v.get("play") or v.get("wmplay")),
                   "ai_label": aifilter.label_hit(v)}
            got += 1
            if got >= n:
                return
        if not data.get("hasMore") or data.get("cursor") in (None, cursor):
            return
        cursor = data.get("cursor")


def tikwm_video(url: str) -> dict:
    """Fresh no-watermark video link for any TikTok video url (last resort for downloads)."""
    v = _tikwm_call("/api/", {"url": url, "hd": 1}, max_wait=5)
    play = _abs(v.get("play") or v.get("hdplay") or v.get("wmplay"))
    if not play:
        raise BlockedError("tikwm gave no video link")
    return {"play": play, "title": v.get("title") or "", "duration": v.get("duration") or 0,
            "author": ((v.get("author") or {}).get("unique_id") or ""),
            "ai_label": aifilter.label_hit(v)}


# TikTok's own website search (the call tiktok.com makes when you search). Works best with
# your TikTok login in cookies.txt. Used when tikwm is resting or finds nothing.
TT = os.environ.get("GOON_TT", "https://www.tiktok.com")
_tt_lock = threading.Lock()
_tt = {"next": 0.0}


def _tt_slot(gap=2.0):
    with _tt_lock:
        now = time.time()
        slot = max(now, _tt["next"])
        _tt["next"] = slot + gap
    if slot > now:
        time.sleep(slot - now)


def tiktok_search(query: str, n: int = 30, cookie_path=None):
    """Yield TikTok videos from TikTok's own search. Same dicts as tikwm_search (no 'play')."""
    import secrets
    from urllib.parse import quote
    jar = load_cookies(cookie_path, "tiktok.com") if cookie_path else None
    page = f"{TT}/search/video?q={quote(query)}"
    s = net.session(cookies=[c for c in jar if "tiktok" in c.domain] if jar else None,
                    headers={"Referer": page})
    _tt_slot()
    try:
        s.get(page, timeout=20)                       # picks up the cookies the site hands out
    except Exception as e:
        raise BlockedError(f"tiktok.com unreachable ({net.nice(e)[:80]})") from e
    search_id = time.strftime("%Y%m%d%H%M%S") + secrets.token_hex(9).upper()
    offset, got = 0, 0
    for _page in range(max(1, min(5, -(-n // 12)))):
        _tt_slot()
        try:
            r = s.get(f"{TT}/api/search/general/full/", timeout=20, params={
                "keyword": query, "offset": offset, "search_id": search_id, "aid": "1988",
                "app_language": "en", "app_name": "tiktok_web", "browser_language": "en-US",
                "browser_platform": "Win32", "channel": "tiktok_web", "cookie_enabled": "true",
                "device_platform": "web_pc", "from_page": "search", "os": "windows"})
        except Exception as e:
            raise BlockedError(f"tiktok.com unreachable ({net.nice(e)[:80]})") from e
        if r.status_code != 200:
            raise BlockedError(f"tiktok search said {r.status_code}")
        try:
            d = r.json() if r.text.strip() else {}
        except ValueError:
            d = {}
        items = [e.get("item") for e in (d.get("data") or []) if isinstance(e, dict)
                 and e.get("type") == 1 and e.get("item")]
        if not items and not got:
            raise BlockedError("tiktok search gave nothing" +
                               ("" if jar else " (give me cookies.txt with ur tiktok login)"))
        for it in items:
            vid = str(it.get("id") or "")
            user = ((it.get("author") or {}).get("uniqueId") or "").strip()
            if not vid:
                continue
            yield {"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
                   "title": it.get("desc") or "", "duration": (it.get("video") or {}).get("duration") or 0,
                   "author": user, "play": "", "ai_label": aifilter.label_hit(it),
                   "tags": [c.get("title") for c in (it.get("challenges") or []) if c.get("title")]}
            got += 1
            if got >= n:
                return
        if not d.get("has_more"):
            return
        offset = d.get("cursor") or offset + len(items)


# ============================================================= Instagram ====
# With the user's cookies.txt (logged in), ask Instagram's own website API, the same
# calls instagram.com makes: keyword search + hashtag page. Keeps only videos (reels).
IG_APP_ID = "936619743392459"   # public id of Instagram's web app
IG = os.environ.get("GOON_IG", "https://www.instagram.com")


def load_cookies(path, domain):
    import http.cookiejar
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(str(path), ignore_discard=True, ignore_expires=True)
    except (OSError, http.cookiejar.LoadError):
        return None
    mine = [c for c in jar if domain in c.domain]
    return jar if mine else None


def _ig_videos(obj, out, seen):
    """Walk any Instagram JSON and pick out video posts (reels)."""
    if isinstance(obj, dict):
        code = obj.get("code")
        is_video = obj.get("media_type") == 2 or obj.get("product_type") == "clips" or \
            bool(obj.get("video_versions"))
        if isinstance(code, str) and is_video and code not in seen:
            seen.add(code)
            cap = obj.get("caption") or {}
            out.append({"code": code, "url": f"https://www.instagram.com/reel/{code}/",
                        "title": (cap.get("text") if isinstance(cap, dict) else "") or "",
                        "duration": obj.get("video_duration") or 0,
                        "author": (obj.get("user") or {}).get("username") or "",
                        "ai_label": aifilter.label_hit(obj)})
        for v in obj.values():
            _ig_videos(v, out, seen)
    elif isinstance(obj, list):
        for v in obj:
            _ig_videos(v, out, seen)


def instagram_api(query: str, cookie_path, n: int = 30) -> list[dict]:
    jar = load_cookies(cookie_path, "instagram.com")
    if not jar:
        raise BlockedError("no instagram login in cookies.txt")
    csrf = next((c.value for c in jar if c.name == "csrftoken" and "instagram" in c.domain), "")
    s = net.session(cookies=[c for c in jar if "instagram" in c.domain],
                    headers={"X-IG-App-ID": IG_APP_ID, "X-Requested-With": "XMLHttpRequest",
                             "X-CSRFToken": csrf, "Referer": "https://www.instagram.com/"})
    out, seen, errors = [], set(), []
    tag = re.sub(r"[^\w]", "", query).lower()
    for url, params in ((f"{IG}/api/v1/fbsearch/web/top_serp/", {"query": query}),
                        (f"{IG}/api/v1/tags/web_info/", {"tag_name": tag})):
        try:
            r = s.get(url, params=params, timeout=20)
            if r.status_code in (401, 403) or "login" in str(r.url):
                errors.append("instagram says log in again (cookies.txt old?)")
                continue
            if r.status_code != 200:
                errors.append(f"instagram said {r.status_code}")
                continue
            _ig_videos(r.json(), out, seen)
        except Exception as e:
            errors.append(net.nice(e)[:80])
        if len(out) >= n:
            break
    if not out and errors:
        raise BlockedError("; ".join(errors))
    return out[:n]
