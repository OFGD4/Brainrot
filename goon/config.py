import json
import threading
from pathlib import Path

from .paths import data_dir, default_cave

DEFAULTS = {
    "backend": "auto",          # auto | ollama | gemini
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "",         # blank = pick from hardware
    "gemini_key": "",
    "gemini_model": "gemini-3.5-flash-lite",
    "threshold": 6,             # keep if rot score >= this
    "ear_mode": True,           # whisper transcript
    "whisper_size": "auto",       # auto | tiny | base | small
    "max_secs": 180,            # skip videos longer than this (Shorts go up to 3 min)
    "cookies_browser": "none",  # none | firefox | edge | chrome | brave | opera | vivaldi
    "cave_dir": str(default_cave()),
    "keep_rejects": False,
    "taste": "",                # extra description of the rot the user likes
    "lang": "caveman",          # caveman | illsonois | olde
    "sources": "youtube,tiktok,instagram",  # (old setting, kept for compatibility)
    "chill_cpu": True,          # go easy on the PC: low priority, fewer threads, lighter ear mode
    "source_mode": "first",     # only = TikTok+Insta only | first = TikTok+Insta, YouTube backup | mix
    "skip_version": "",         # update the user said "skip" to
    "last_version": "",         # to say "me updated!" once after an update
}
LANG_CODES = ("caveman", "illsonois", "olde")

_lock = threading.Lock()


class Config:
    def __init__(self):
        self.path = data_dir() / "config.json"
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text("utf-8"))
                if saved.get("cfg_version", 1) < 2 and saved.get("max_secs") == 90:
                    saved["max_secs"] = 180          # old default was too short for Shorts
                self.data.update(saved)
            except Exception:
                pass
        self.data["cfg_version"] = 2
        self.save()

    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def update(self, new: dict):
        with _lock:
            if new.get("gemini_key_clear"):
                self.data["gemini_key"] = ""
            for k, v in new.items():
                if k not in DEFAULTS:
                    continue
                if k == "gemini_key" and not str(v).strip():
                    continue  # UI never sends the saved key back; blank = keep it
                d = DEFAULTS[k]
                try:
                    if isinstance(d, bool):
                        v = bool(v)
                    elif isinstance(d, int):
                        v = int(float(v))
                    else:
                        v = str(v).strip()
                except (TypeError, ValueError):
                    continue
                self.data[k] = v
            self.data["threshold"] = max(0, min(10, self.data["threshold"]))
            srcs = [x for x in str(self.data["sources"]).split(",") if x in ("youtube", "tiktok", "instagram")]
            self.data["sources"] = ",".join(srcs) or "youtube"
            if self.data["source_mode"] not in ("only", "first", "mix"):
                self.data["source_mode"] = "first"
            if self.data["lang"] not in LANG_CODES:
                self.data["lang"] = "caveman"
            self.data["max_secs"] = max(5, min(1800, self.data["max_secs"]))
            if not self.data["cave_dir"]:
                self.data["cave_dir"] = str(default_cave())
            self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
        tmp.replace(self.path)

    def cave(self) -> Path:
        p = Path(self.data["cave_dir"]).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def public(self) -> dict:
        d = dict(self.data)
        k = d.get("gemini_key", "")
        d["gemini_key"] = ""
        d["gemini_key_set"] = bool(k)
        d["gemini_key_hint"] = ("…" + k[-4:]) if len(k) > 8 else ""
        return d
