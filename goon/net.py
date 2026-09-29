"""HTTP that looks like a real Chrome browser.

TikTok, tikwm.com (Cloudflare) and Instagram check HOW a program connects (its TLS
fingerprint), not just the User-Agent text. Plain Python gets "403 Forbidden".
curl_cffi connects exactly like Chrome does, so they let us in. If curl_cffi is missing
(dev setup without it), falls back to plain requests.
"""
import requests

try:
    from curl_cffi import requests as _cr
except Exception:          # not installed / broken: plain requests
    _cr = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
BROWSER = "chrome"


def browser_ok() -> bool:
    return _cr is not None


def session(cookies=None, headers=None):
    """A session that looks like Chrome (curl_cffi), or plain requests as a fallback."""
    if _cr is not None:
        s = _cr.Session(impersonate=BROWSER, timeout=20)
        if headers:
            s.headers.update(headers)
        if cookies is not None:
            for c in cookies:
                s.cookies.set(c.name, c.value, domain=c.domain, path=c.path or "/")
        return s
    s = requests.Session()
    s.headers.update({**HEADERS, **(headers or {})})
    if cookies is not None:
        s.cookies = cookies
    return s


def get(url, **kw):
    kw.setdefault("timeout", 20)
    if _cr is not None:
        return _cr.get(url, impersonate=BROWSER, **kw)
    kw["headers"] = {**HEADERS, **(kw.get("headers") or {})}
    return requests.get(url, **kw)


def post(url, **kw):
    kw.setdefault("timeout", 20)
    if _cr is not None:
        return _cr.post(url, impersonate=BROWSER, **kw)
    kw["headers"] = {**HEADERS, **(kw.get("headers") or {})}
    return requests.post(url, **kw)


def nice(e) -> str:
    """Short error text (curl errors are long)."""
    s = str(e).replace("\n", " ")
    for cut in (" See https://curl.se", "(Caused by", " (caused by"):
        if cut in s:
            s = s.split(cut)[0]
    return s.strip()[:220]
