"""Find TikTok / Instagram video links with a normal web search.

yt-dlp can download single TikTok videos, TikTok profiles and Instagram reels, but it has no
working search for those sites. So: ask DuckDuckGo (Bing as backup) for
"<words> site:tiktok.com" and pull the video / profile / reel links out of the results page.
"""
import base64
import os
import re
import time
from urllib.parse import quote_plus, unquote

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
_last = [0.0]

TT_VIDEO = re.compile(r"https?://(?:www\.|m\.)?tiktok\.com/@([\w.\-]+)/video/(\d+)")
TT_USER = re.compile(r"https?://(?:www\.|m\.)?tiktok\.com/@([\w.\-]+)")
IG_REEL = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[\w.\-]+/)?(?:reels?|tv)/([\w\-]{5,})")


class BlockedError(Exception):
    pass


def _polite():
    """Don't hammer the search engines (they block fast)."""
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
    r = requests.get(f"https://html.duckduckgo.com/html/?q={quote_plus(q)}", headers=HEADERS, timeout=15)
    if r.status_code != 200 or "anomaly" in r.text.lower():
        raise BlockedError(f"duckduckgo said {r.status_code}")
    return r.text


def _bing(q):
    _polite()
    r = requests.get(f"https://www.bing.com/search?q={quote_plus(q)}&count=50", headers=HEADERS,
                     timeout=15)
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
        except (requests.RequestException, BlockedError) as e:
            errors.append(str(e)[:80])
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
# tikwm.com: free public TikTok search (used by many open-source tools). No login, no
# web search. Limit: about 1 request per second.
TIKWM = os.environ.get("GOON_TIKWM", "https://www.tikwm.com")
_tikwm_last = [0.0]


def tikwm_search(query: str, n: int = 30):
    """Yield TikTok videos for these words: dicts with id, url, title, duration, author, play."""
    cursor, got = 0, 0
    for _page in range(6):
        wait = 1.1 - (time.time() - _tikwm_last[0])
        if wait > 0:
            time.sleep(wait)
        _tikwm_last[0] = time.time()
        r = requests.get(f"{TIKWM}/api/feed/search", headers=HEADERS, timeout=20,
                         params={"keywords": query, "count": 30, "cursor": cursor, "hd": 1})
        if r.status_code != 200:
            raise BlockedError(f"tikwm said {r.status_code}")
        d = r.json()
        if d.get("code") not in (0, None):
            raise BlockedError(f"tikwm: {d.get('msg') or d.get('code')}")
        data = d.get("data") or {}
        for v in data.get("videos") or []:
            vid = str(v.get("video_id") or v.get("id") or "")
            user = ((v.get("author") or {}).get("unique_id") or "").strip()
            if not vid:
                continue
            play = v.get("play") or v.get("wmplay") or ""
            if play.startswith("/"):
                play = TIKWM + play
            yield {"id": vid, "url": f"https://www.tiktok.com/@{user or 'user'}/video/{vid}",
                   "title": v.get("title") or "", "duration": v.get("duration") or 0,
                   "author": user, "play": play}
            got += 1
            if got >= n:
                return
        if not data.get("hasMore") or data.get("cursor") in (None, cursor):
            return
        cursor = data.get("cursor")


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
                        "author": (obj.get("user") or {}).get("username") or ""})
        for v in obj.values():
            _ig_videos(v, out, seen)
    elif isinstance(obj, list):
        for v in obj:
            _ig_videos(v, out, seen)


def instagram_api(query: str, cookie_path, n: int = 30) -> list[dict]:
    jar = load_cookies(cookie_path, "instagram.com")
    if not jar:
        raise BlockedError("no instagram login in cookies.txt")
    s = requests.Session()
    s.cookies = jar
    csrf = next((c.value for c in jar if c.name == "csrftoken" and "instagram" in c.domain), "")
    s.headers.update({**HEADERS, "X-IG-App-ID": IG_APP_ID, "X-Requested-With": "XMLHttpRequest",
                      "X-CSRFToken": csrf, "Referer": "https://www.instagram.com/"})
    out, seen, errors = [], set(), []
    tag = re.sub(r"[^\w]", "", query).lower()
    for url, params in ((f"{IG}/api/v1/fbsearch/web/top_serp/", {"query": query}),
                        (f"{IG}/api/v1/tags/web_info/", {"tag_name": tag})):
        try:
            r = s.get(url, params=params, timeout=20)
            if r.status_code in (401, 403) or "login" in r.url:
                errors.append("instagram says log in again (cookies.txt old?)")
                continue
            if r.status_code != 200:
                errors.append(f"instagram said {r.status_code}")
                continue
            _ig_videos(r.json(), out, seen)
        except (requests.RequestException, ValueError) as e:
            errors.append(str(e)[:80])
        if len(out) >= n:
            break
    if not out and errors:
        raise BlockedError("; ".join(errors))
    return out[:n]
