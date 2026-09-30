"""The AI judge. Local (Ollama) or Google (Gemini free tier), or both as a tag team. All free.

Every judge call can be interrupted: STOP never waits for the AI to finish thinking.
"""
import base64
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
AI_LIMIT = 5   # "ai" score from the judge at or above this = AI-made video = yeet

PROMPT = """You are the Brainrot Judge. You rate short-form videos for BRAINROT: absurd, chaotic, \
overstimulating, low-context internet meme content MADE BY REAL PEOPLE that is weirdly addictive.

High brainrot examples: Skibidi Toilet, sigma / rizz / gyatt / fanum tax / Ohio / mewing / "6 7" slang \
memes, split-screen with Subway Surfers or Minecraft parkour, deep-fried or ear-blasting edits, weird \
meme edits and phonk edits, nonsense remixes, cursed clips, shitposts, goofy sound effects, random \
animals with loud distorted music, unhinged real people.
Low brainrot: normal vlogs, tutorials, news, sports, music videos, ads, calm or informative content, \
anything that makes normal sense.
Many of the best brainrot videos have NO caption, title or hashtags at all. Never score lower because \
the text is empty or unrelated: judge by what you SEE and HEAR.

NO AI CONTENT: the user HATES AI-generated videos. Rate "ai" 0-10 = how likely this video is AI-made or \
about AI: made with Sora, Veo, Kling, Hailuo, Runway, Pika, Grok Imagine, Midjourney etc., AI images or \
AI animation, AI voices or AI songs, "Italian brainrot" AI creatures (Tralalero Tralala, Tung Tung Tung \
Sahur, Ballerina Cappuccina, Bombardiro Crocodilo...), AI babies / talking animals / fruit soap operas, \
anything showing or talking about AI. Signs: waxy too-smooth skin and surfaces, glossy plastic look, \
morphing or melting shapes, warped hands or extra fingers, garbled text or signs, glossy realistic scenes \
that are physically impossible, floaty dreamlike camera, AI labels or watermarks (Sora, Veo, Kling, \
Hailuo, Pika). Real camera footage, real people, video games, hand-made edits and classic memes = 0-2.
If "ai" is {ai_limit} or more, "score" MUST be 0.

Score 0-10: 0 = totally normal, 4 = a bit memey, 7 = clear brainrot, 10 = peak unhinged.
{taste}
The user searched for: "{query}"

VIDEO INFO
Title: {title}
Uploader: {uploader}
Duration: {duration}s
Tags/description: {desc}
Transcript (may be empty or gibberish): {transcript}

{images_note}

Write "vibe" and "why" in this style: {style}

Reply ONLY with JSON:
{{"score": <integer 0-10>, "ai": <integer 0-10>, "vibe": "<2-4 word label>", "why": "<one short sentence>"}}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "ai": {"type": "integer"},
        "vibe": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["score", "ai", "vibe", "why"],
}


class BrainError(Exception):
    pass


class Busy(BrainError):
    """Google says slow down. In a tag team the other brain takes the video meanwhile."""
    def __init__(self, delay, msg="busy"):
        super().__init__(msg)
        self.delay = delay


class Tired(BrainError):
    """Google free tries used up for today."""


class Refused(BrainError):
    """This brain won't judge this one video (e.g. Google's filter). Another brain may."""


class Stopped(BrainError):
    pass


def _nap(stop, secs):
    """Sleep, but wake up the moment STOP is pressed."""
    if stop is None:
        time.sleep(secs)
    elif stop.wait(secs):
        raise Stopped("stopped")


DEFAULT_STYLE = ("funny broken caveman English, like "
                 "'dis vida hav toilet man singing and loud noise, very rot'")


def build_prompt(meta: dict, transcript: str, n_images: int, taste: str,
                 style: str = DEFAULT_STYLE, sheet: bool = False) -> str:
    desc = " ".join(filter(None, [
        " ".join("#" + t for t in (meta.get("tags") or [])[:20]),
        (meta.get("description") or "")[:400],
    ])).strip()
    if sheet:
        note = ("The image is a 2x2 grid of 4 frames from the video, in time order "
                "(top-left, top-right, bottom-left, bottom-right).")
    elif n_images:
        note = f"The {n_images} images are frames from the video, in order."
    else:
        note = "No frames available; judge from the text."
    return PROMPT.format(
        ai_limit=AI_LIMIT,
        taste=f"The user especially likes this kind of rot: {taste}\n" if taste else "",
        query=meta.get("query") or "anything",
        title=(meta.get("title") or "(no caption)")[:200],
        uploader=meta.get("uploader") or "?",
        duration=int(meta.get("duration") or 0),
        desc=desc or "(none)",
        transcript=(transcript or "").strip()[:800] or "(none)",
        images_note=note,
        style=style or DEFAULT_STYLE,
    )


def _int(v, default=0):
    try:
        return max(0, min(10, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def parse_verdict(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    data = None
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = None
    if data is None:
        sm = re.search(r'"?score"?\s*[:=]\s*"?(\d+(?:\.\d+)?)', text)
        if not sm:
            raise BrainError(f"brain say nonsense: {text[:120]!r}")
        am = re.search(r'"?ai"?\s*[:=]\s*"?(\d+(?:\.\d+)?)', text)
        data = {"score": sm.group(1), "ai": am.group(1) if am else 0}
    ai = _int(data.get("ai"))
    score = _int(data.get("score"))
    if ai >= AI_LIMIT:
        score = 0
    return {
        "score": score,
        "ai": ai,
        "vibe": str(data.get("vibe") or "unknown vibe")[:60],
        "why": str(data.get("why") or "")[:240],
    }


def _b64(p: Path) -> str:
    return base64.b64encode(Path(p).read_bytes()).decode()


# ---------------------------------------------------------------- Ollama ----

def _ollama_exe():
    cands = []
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        cands += [Path(la) / "Programs" / "Ollama" / "ollama.exe",
                  Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Ollama" / "ollama.exe"]
    w = shutil.which("ollama")
    if w:
        cands.insert(0, Path(w))
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    return None


class OllamaBrain:
    kind = "ollama"
    style = DEFAULT_STYLE
    num_thread = None   # set in chill mode when the model runs on the CPU
    stop = None         # threading.Event: STOP pressed

    def __init__(self, url: str, model: str, taste: str = ""):
        self.url = url.rstrip("/")
        self.model = model
        self.taste = taste
        self.s = requests.Session()
        self.s.trust_env = False  # never proxy localhost
        self._conn = None

    @property
    def label(self):
        return f"ollama · {self.model}"

    def alive(self) -> bool:
        try:
            return self.s.get(self.url + "/api/version", timeout=3).ok
        except requests.RequestException:
            return False

    def try_start(self, stop=None) -> bool:
        if self.alive():
            return True
        exe = _ollama_exe()
        if not exe:
            return False
        try:
            subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        for _ in range(30):
            _nap(stop, 0.5)
            if self.alive():
                return True
        return False

    def installed(self) -> list[str]:
        try:
            r = self.s.get(self.url + "/api/tags", timeout=5)
            return [m["name"] for m in r.json().get("models", [])]
        except (requests.RequestException, ValueError):
            return []

    def has_model(self) -> bool:
        names = self.installed()
        want = self.model if ":" in self.model else self.model + ":latest"
        return want in names

    def status(self) -> dict:
        if not self.alive():
            return {"state": "no_ollama", "installed": bool(_ollama_exe())}
        if not self.has_model():
            return {"state": "no_model", "model": self.model}
        return {"state": "ready", "model": self.model}

    def pull(self, progress=None, stop=None):
        with self.s.post(self.url + "/api/pull", json={"model": self.model, "stream": True},
                         stream=True, timeout=(10, 600)) as r:
            if not r.ok:
                raise BrainError(f"pull fail: {r.text[:200]}")
            for line in r.iter_lines():
                if stop is not None and stop.is_set():
                    raise Stopped("stopped")
                if not line:
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise BrainError(d["error"])
                if progress and d.get("total"):
                    progress(d.get("status", ""), d.get("completed", 0), d["total"])
                if d.get("status") == "success":
                    return

    def warm(self):
        """Load the model into memory now, so the first video doesn't wait for it."""
        try:
            self.s.post(self.url + "/api/generate", json={"model": self.model, "keep_alive": "30m"},
                        timeout=180)
        except requests.RequestException:
            pass

    def abort(self):
        """STOP: cut the connection. Ollama sees that and stops thinking right away."""
        c = self._conn
        try:
            if c is not None and c.sock is not None:
                c.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _chat(self, body) -> str:
        """Streamed /api/chat on a connection we can cut (see abort)."""
        u = urlparse(self.url)
        https = u.scheme == "https"
        conn = (http.client.HTTPSConnection if https else http.client.HTTPConnection)(
            u.hostname, u.port or (443 if https else 80), timeout=600)
        self._conn = conn
        try:
            conn.request("POST", u.path.rstrip("/") + "/api/chat", body=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                err = resp.read(600).decode("utf-8", "ignore")
                raise BrainError(f"ollama error {resp.status}: {err[:200]}")
            out = []
            while True:
                line = resp.readline()
                if self.stop is not None and self.stop.is_set():
                    raise Stopped("stopped")
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise BrainError(f"ollama error: {d['error']}")
                out.append((d.get("message") or {}).get("content", ""))
                if d.get("done"):
                    break
            return "".join(out)
        except (OSError, http.client.HTTPException, ValueError) as e:
            if self.stop is not None and self.stop.is_set():
                raise Stopped("stopped") from e
            raise BrainError(f"ollama no answer: {e}") from e
        finally:
            self._conn = None
            conn.close()

    def rate(self, meta, frames, transcript, sheet=False) -> dict:
        prompt = build_prompt(meta, transcript, len(frames), self.taste, self.style, sheet)
        msg = {"role": "user", "content": prompt}
        if frames:
            msg["images"] = [_b64(f) for f in frames]
        body = {
            "model": self.model, "messages": [msg], "stream": True, "format": SCHEMA,
            "options": {"temperature": 0.2, "num_ctx": 4096,
                        **({"num_thread": self.num_thread} if self.num_thread else {})},
            "keep_alive": "30m",
        }
        try:
            text = self._chat(body)
        except Stopped:
            raise
        except BrainError as e:
            if not (frames and "image" in str(e).lower()):
                raise
            # this model can't see pictures: judge from the words only
            body["messages"] = [{"role": "user", "content": build_prompt(
                meta, transcript, 0, self.taste, self.style)}]
            text = self._chat(body)
        return parse_verdict(text)


# ---------------------------------------------------------------- Gemini ----

class GeminiBrain:
    kind = "gemini"
    style = DEFAULT_STYLE
    BASE = os.environ.get("GOON_GEMINI", "https://generativelanguage.googleapis.com") + "/v1beta/models/"
    GAP = 6.5       # seconds between calls (free tier ~10/min); grows if Google says "slow down"
    MAX_GAP = 15.0
    stop = None     # threading.Event: STOP pressed
    handoff = False # tag team: on "slow down" give the video to the other brain instead of waiting

    def __init__(self, key: str, model: str, taste: str = "", log=None):
        self.key = key.strip()
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self.taste = taste
        self.log = log
        self.s = requests.Session()
        self._last = 0.0
        self.gap = self.GAP

    @property
    def label(self):
        return f"gemini · {self.model}"

    def status(self) -> dict:
        if not self.key:
            return {"state": "no_key"}
        try:
            r = self.s.get(self.BASE + self.model, headers={"x-goog-api-key": self.key}, timeout=10)
        except requests.RequestException as e:
            return {"state": "offline", "error": str(e)[:120]}
        if r.ok:
            return {"state": "ready", "model": self.model}
        if r.status_code == 404:
            return {"state": "bad_model", "model": self.model}
        return {"state": "bad_key", "error": r.text[:160]}

    def _retry_after(self, r) -> float:
        try:
            for d in r.json()["error"].get("details", []):
                if "retryDelay" in d:
                    return float(str(d["retryDelay"]).rstrip("s")) + 1
        except (ValueError, KeyError, TypeError):
            pass
        return 30.0

    def turn_in(self) -> float:
        """Seconds until the next call is allowed (free tier = a few calls per minute)."""
        return max(0.0, self.gap - (time.time() - self._last))

    def wait_turn(self):
        w = self.turn_in()
        if w > 0:
            _nap(self.stop, w)

    def rate(self, meta, frames, transcript, sheet=False) -> dict:
        parts = [{"text": build_prompt(meta, transcript, len(frames), self.taste, self.style, sheet)}]
        parts += [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(f)}} for f in frames]
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {"score": {"type": "INTEGER"}, "ai": {"type": "INTEGER"},
                                   "vibe": {"type": "STRING"}, "why": {"type": "STRING"}},
                    "required": ["score", "ai", "vibe", "why"],
                },
            },
            # crude meme humour is the whole point: don't let the filter refuse to look
            "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in (
                "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")],
        }
        for attempt in range(4):
            self.wait_turn()
            self._last = time.time()
            try:
                r = self.s.post(self.BASE + self.model + ":generateContent",
                                headers={"x-goog-api-key": self.key}, json=body, timeout=60)
            except requests.RequestException as e:
                if self.stop is not None and self.stop.is_set():
                    raise Stopped("stopped") from e
                if self.handoff:
                    raise Busy(15, f"google no answer: {e}") from e
                raise BrainError(f"google no answer: {e}") from e
            if self.stop is not None and self.stop.is_set():
                raise Stopped("stopped")
            if r.status_code == 429 or r.status_code >= 500:
                low = r.text.lower()
                if "perday" in low or "per day" in low or "per_day" in low:
                    raise Tired("google say u used all free tries today. come back tomorrow "
                                "or use local brain")
                delay = self._retry_after(r) if r.status_code == 429 else 10.0
                if r.status_code == 429:
                    self.gap = min(self.gap + 1.5, self.MAX_GAP)   # go slower from now on
                if self.handoff:
                    raise Busy(delay, f"google busy ({r.status_code})")
                if self.log:
                    self.log("gemini_slow", s=int(delay))
                _nap(self.stop, delay)
                continue
            if not r.ok:
                raise BrainError(f"google error {r.status_code}: {r.text[:200]}")
            try:
                d = r.json()
                cands = d.get("candidates") or []
                if not cands or not (cands[0].get("content") or {}).get("parts"):
                    why = ((d.get("promptFeedback") or {}).get("blockReason")
                           or (cands[0].get("finishReason") if cands else "") or "empty answer")
                    raise Refused(f"google no want to judge dis one ({why})")
                text = "".join(p.get("text", "") for p in cands[0]["content"]["parts"])
            except (ValueError, KeyError, IndexError, TypeError):
                raise BrainError(f"google say weird thing: {r.text[:200]}")
            return parse_verdict(text)
        raise Busy(30, "google too busy, tried 4 times")
