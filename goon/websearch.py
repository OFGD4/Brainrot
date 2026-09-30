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


def _tikwm_item(v):
    """tikwm video -> our dict. None for photo slideshows (not videos)."""
    vid = str(v.get("video_id") or v.get("id") or "")
    if not vid or v.get("images"):
        return None
    user = ((v.get("author") or {}).get("unique_id") or "").strip()
    mi = v.get("music_info") or {}
    return {"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
            "title": v.get("title") or "", "duration": v.get("duration") or 0,
            "author": user, "play": _abs(v.get("play") or v.get("wmplay")),
            "music_id": str(mi.get("id") or ""), "music": mi.get("title") or "",
            "ai_label": aifilter.label_hit(v)}


def _tikwm_feed(path, params, n, max_pages=3):
    """Page through a tikwm list (user posts / sound posts)."""
    cursor, got = "0", 0
    for _page in range(max_pages):
        data = _tikwm_call(path, {**params, "count": 30, "cursor": cursor})
        for v in data.get("videos") or []:
            it = _tikwm_item(v)
            if it:
                got += 1
                yield it
                if got >= n:
                    return
        nxt = str(data.get("cursor") or "")
        if not data.get("hasMore") or not nxt or nxt == cursor:
            return
        cursor = nxt


def tikwm_user_posts(user: str, n: int = 15):
    """A creator's newest videos (captions or not)."""
    yield from _tikwm_feed("/api/user/posts", {"unique_id": user.lstrip("@")}, n)


def tikwm_sound_posts(music_id: str, n: int = 20):
    """Other videos using the same sound."""
    yield from _tikwm_feed("/api/music/posts", {"music_id": music_id}, n)


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
            it = _tikwm_item(v)
            if not it:
                continue
            yield it
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
            if it.get("imagePost"):
                continue                               # photo slideshow, not a video
            mu = it.get("music") or {}
            yield {"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
                   "title": it.get("desc") or "", "duration": (it.get("video") or {}).get("duration") or 0,
                   "author": user, "play": "", "ai_label": aifilter.label_hit(it),
                   "music_id": str(mu.get("id") or ""), "music": mu.get("title") or "",
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
        code = obj.get("code") or obj.get("shortcode")
        is_video = obj.get("media_type") == 2 or obj.get("product_type") == "clips" or \
            bool(obj.get("video_versions")) or obj.get("is_video") is True
        if isinstance(code, str) and is_video and code not in seen:
            seen.add(code)
            cap = obj.get("caption") or {}
            if not isinstance(cap, dict) or not cap:      # older style: edge_media_to_caption
                edges = ((obj.get("edge_media_to_caption") or {}).get("edges") or [{}])
                cap = {"text": ((edges[0] or {}).get("node") or {}).get("text", "")}
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


def _ig_session(cookie_path):
    jar = load_cookies(cookie_path, "instagram.com")
    if not jar:
        raise BlockedError("no instagram login in cookies.txt")
    csrf = next((c.value for c in jar if c.name == "csrftoken" and "instagram" in c.domain), "")
    return net.session(cookies=[c for c in jar if "instagram" in c.domain],
                       headers={"X-IG-App-ID": IG_APP_ID, "X-Requested-With": "XMLHttpRequest",
                                "X-CSRFToken": csrf, "Referer": "https://www.instagram.com/"})


def instagram_user(username: str, cookie_path, n: int = 12) -> list[dict]:
    """A creator's newest reels (captions or not). Needs the Instagram login in cookies.txt."""
    s = _ig_session(cookie_path)
    out, seen = [], set()
    d = _ig_get(s, f"{IG}/api/v1/users/web_profile_info/", {"username": username})
    user = (d.get("data") or {}).get("user") or {}
    if user.get("id"):
        try:
            _ig_videos(_ig_get(s, f"{IG}/api/v1/clips/user/", data={
                "target_user_id": user["id"], "page_size": n, "include_feed_video": "true"}), out, seen)
        except Exception:
            pass
    _ig_videos(user, out, seen)                    # the profile page itself lists recent posts
    for v in out:
        v["author"] = v["author"] or username
    return out[:n]


_ig_lock = threading.Lock()
_ig = {"next": 0.0}
IG_GAP = 3.0   # Instagram flags accounts that click too fast: one call every 3s, for everything


def _ig_get(s, url, params=None, data=None):
    """One polite Instagram call. Raises BlockedError with a clear reason."""
    with _ig_lock:
        now = time.time()
        slot = max(now, _ig["next"])
        _ig["next"] = slot + IG_GAP
    if slot > now:
        time.sleep(slot - now)
    r = s.post(url, data=data, timeout=20) if data is not None else s.get(url, params=params, timeout=20)
    if r.status_code in (401, 403) or "login" in str(r.url) or "checkpoint" in str(r.url):
        raise BlockedError("instagram says log in again (cookies.txt old? export a fresh one)")
    if r.status_code == 429 or "wait a few minutes" in r.text[:500].lower():
        raise BlockedError("instagram says slow down (429): too many searches, wait ~10 min")
    if r.status_code != 200:
        raise BlockedError(f"instagram said {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise BlockedError("instagram sent a web page, not data (cookies.txt old?)")


def _find(obj, key, depth=0):
    """First value of `key` anywhere in Instagram's JSON."""
    if depth > 8:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        vals = obj.values()
    elif isinstance(obj, list):
        vals = obj
    else:
        return None
    for v in vals:
        r = _find(v, key, depth + 1)
        if r is not None:
            return r
    return None


def instagram_api(query: str, cookie_path, n: int = 30):
    """Instagram's own search as you (cookies.txt): keyword search + the hashtag's TOP and
    RECENT reels, several pages each, so every run finds new videos, not the same top 20."""
    s = _ig_session(cookie_path)
    out, seen, errors = [], set(), []
    tag = re.sub(r"[^\w]", "", query).lower()

    def take(d):
        before = len(out)
        _ig_videos(d, out, seen)
        yield from out[before:]

    # 1) keyword search, then its next pages
    try:
        d = _ig_get(s, f"{IG}/api/v1/fbsearch/web/top_serp/", {"query": query})
        yield from take(d)
        for _page in range(3):
            if len(out) >= n:
                return
            grid = d.get("media_grid") or d
            nxt, more = _find(grid, "next_max_id"), _find(grid, "has_more") or _find(grid, "more_available")
            if not nxt or not more:
                break
            params = {"query": query, "next_max_id": nxt}
            rank = _find(grid, "rank_token")
            if rank:
                params["rank_token"] = rank
            d = _ig_get(s, f"{IG}/api/v1/fbsearch/web/top_serp/", params)
            got = len(out)
            yield from take(d)
            if len(out) == got:
                break
    except BlockedError as e:
        errors.append(str(e))
        if "log in" in str(e) or "slow down" in str(e):
            raise
    except Exception as e:
        errors.append(net.nice(e)[:80])
    if len(out) >= n or not tag:
        return
    # 2) hashtag page: top + RECENT reels (recent = fresh stuff every time), then recent pages
    try:
        d = _ig_get(s, f"{IG}/api/v1/tags/web_info/", {"tag_name": tag})
        yield from take(d)
        recent = _find(d, "recent") or {}
        for _page in range(3):
            if len(out) >= n or not isinstance(recent, dict):
                break
            nxt = recent.get("next_max_id")
            if not nxt or not recent.get("more_available"):
                break
            d = _ig_get(s, f"{IG}/explore/tags/{tag}/", {"__a": 1, "__d": "dis", "max_id": nxt})
            got = len(out)
            yield from take(d)
            recent = _find(d, "recent") or {}
            if len(out) == got:
                break
    except Exception as e:
        errors.append(str(e)[:120])
    if not out and errors:
        raise BlockedError("; ".join(dict.fromkeys(errors)))
