"""The AI judge. Local (Ollama) or Google (Gemini free tier). Both free."""
import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

PROMPT = """You are the Brainrot Judge. You rate short-form videos for BRAINROT: absurd, chaotic, \
overstimulating, low-context internet meme content that is weirdly addictive.

High brainrot examples: Italian brainrot AI creatures (Tralalero Tralala, Bombardiro Crocodilo, \
Tung Tung Tung Sahur, Ballerina Cappuccina), Skibidi Toilet, sigma / rizz / gyatt / fanum tax / Ohio / \
mewing / "6 7" slang, split-screen with Subway Surfers or Minecraft parkour, TTS voices reading stories \
over random gameplay, deep-fried or ear-blasting edits, nonsense remixes, absurd looping AI videos, \
random animals with loud distorted music.
Low brainrot: normal vlogs, tutorials, news, sports, music videos, ads, calm or informative content, \
anything that makes normal sense.

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
{{"score": <integer 0-10>, "vibe": "<2-4 word label>", "why": "<one short sentence>"}}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "vibe": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["score", "vibe", "why"],
}


class BrainError(Exception):
    pass


DEFAULT_STYLE = ("funny broken caveman English, like "
                 "'dis vida hav toilet man singing and loud noise, very rot'")


def build_prompt(meta: dict, transcript: str, n_images: int, taste: str,
                 style: str = DEFAULT_STYLE) -> str:
    desc = " ".join(filter(None, [
        " ".join("#" + t for t in (meta.get("tags") or [])[:20]),
        (meta.get("description") or "")[:400],
    ])).strip()
    return PROMPT.format(
        taste=f"The user especially likes this kind of rot: {taste}\n" if taste else "",
        query=meta.get("query") or "anything",
        title=(meta.get("title") or "?")[:200],
        uploader=meta.get("uploader") or "?",
        duration=int(meta.get("duration") or 0),
        desc=desc or "(none)",
        transcript=transcript.strip() or "(none)",
        images_note=(f"The {n_images} images are frames from the video, in order."
                     if n_images else "No frames available; judge from the text."),
        style=style or DEFAULT_STYLE,
    )


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
        data = {"score": sm.group(1)}
    try:
        score = int(round(float(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {
        "score": max(0, min(10, score)),
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

    def __init__(self, url: str, model: str, taste: str = ""):
        self.url = url.rstrip("/")
        self.model = model
        self.taste = taste
        self.s = requests.Session()
        self.s.trust_env = False  # never proxy localhost

    @property
    def label(self):
        return f"ollama · {self.model}"

    def alive(self) -> bool:
        try:
            return self.s.get(self.url + "/api/version", timeout=3).ok
        except requests.RequestException:
            return False

    def try_start(self) -> bool:
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
            time.sleep(0.5)
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
                    raise BrainError("stopped")
                if not line:
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise BrainError(d["error"])
                if progress and d.get("total"):
                    progress(d.get("status", ""), d.get("completed", 0), d["total"])
                if d.get("status") == "success":
                    return

    def rate(self, meta, frames, transcript) -> dict:
        prompt = build_prompt(meta, transcript, len(frames), self.taste, self.style)
        msg = {"role": "user", "content": prompt}
        if frames:
            msg["images"] = [_b64(f) for f in frames]
        body = {
            "model": self.model, "messages": [msg], "stream": False, "format": SCHEMA,
            "options": {"temperature": 0.2, "num_ctx": 8192,
                        **({"num_thread": self.num_thread} if self.num_thread else {})},
            "keep_alive": "15m",
        }
        try:
            r = self.s.post(self.url + "/api/chat", json=body, timeout=(10, 600))
        except requests.RequestException as e:
            raise BrainError(f"ollama no answer: {e}") from e
        if not r.ok and frames and "image" in r.text.lower():
            body["messages"] = [{"role": "user", "content": build_prompt(meta, transcript, 0, self.taste, self.style)}]
            r = self.s.post(self.url + "/api/chat", json=body, timeout=(10, 600))
        if not r.ok:
            raise BrainError(f"ollama error {r.status_code}: {r.text[:200]}")
        return parse_verdict(r.json().get("message", {}).get("content", ""))


# ---------------------------------------------------------------- Gemini ----

class GeminiBrain:
    kind = "gemini"
    style = DEFAULT_STYLE
    BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
    MIN_GAP = 6.5  # free tier is ~10 requests/min

    def __init__(self, key: str, model: str, taste: str = "", log=None):
        self.key = key.strip()
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self.taste = taste
        self.log = log
        self.s = requests.Session()
        self._last = 0.0

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

    def rate(self, meta, frames, transcript) -> dict:
        parts = [{"text": build_prompt(meta, transcript, len(frames), self.taste, self.style)}]
        parts += [{"inline_data": {"mime_type": "image/jpeg", "data": _b64(f)}} for f in frames]
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {"score": {"type": "INTEGER"}, "vibe": {"type": "STRING"},
                                   "why": {"type": "STRING"}},
                    "required": ["score", "vibe", "why"],
                },
            },
        }
        for attempt in range(4):
            wait = self.MIN_GAP - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.s.post(self.BASE + self.model + ":generateContent",
                                headers={"x-goog-api-key": self.key}, json=body, timeout=120)
            except requests.RequestException as e:
                raise BrainError(f"google no answer: {e}") from e
            if r.status_code == 429 or r.status_code >= 500:
                delay = self._retry_after(r) if r.status_code == 429 else 10.0
                if "PerDay" in r.text or "per day" in r.text.lower():
                    raise BrainError("google say u used all free tries today. come back tomorrow "
                                     "or use local brain")
                if self.log:
                    self.log("gemini_slow", s=int(delay))
                time.sleep(delay)
                continue
            if not r.ok:
                raise BrainError(f"google error {r.status_code}: {r.text[:200]}")
            try:
                cands = r.json().get("candidates") or []
                text = "".join(p.get("text", "") for p in cands[0]["content"]["parts"])
            except (ValueError, KeyError, IndexError, TypeError):
                raise BrainError(f"google say weird thing: {r.text[:200]}")
            return parse_verdict(text)
        raise BrainError("google too busy, tried 4 times")
