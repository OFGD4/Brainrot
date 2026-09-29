"""Update from inside the app. No GitHub visit needed.

1. Ask GitHub for the latest release of GITHUB_REPO.
2. Newer than APP_VERSION and has a *-Setup.exe? -> tell the UI.
3. User clicks update -> download Setup to %TEMP% (with progress, checks size + sha256).
4. Run Setup silently, quit. Setup replaces the app and starts the new version.
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

from app_info import APP_NAME, APP_VERSION, GITHUB_REPO

FROZEN = bool(getattr(sys, "frozen", False))
API = os.environ.get("GOON_UPDATE_API", "https://api.github.com")
# Testing hook: lets the updater run from source against a fake server.
FORCE = os.environ.get("GOON_UPDATE_FORCE") == "1"
SETUP_FLAGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def parse_version(v: str) -> tuple:
    out = []
    for part in str(v).strip().lstrip("vV").split("-")[0].split(".")[:4]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


class Updater:
    def __init__(self, cfg, on_exit=None):
        self.cfg = cfg
        self.on_exit = on_exit or (lambda: os._exit(0))
        self.lock = threading.Lock()
        self.asset = None
        self.state = {
            "current": APP_VERSION, "latest": None, "available": False, "skipped": False,
            "phase": "idle",  # idle | checking | none | available | downloading | installing | error
            "pct": 0, "error": "", "notes": "", "size": 0,
            "can_install": FROZEN or FORCE, "repo": GITHUB_REPO,
        }

    def public(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    # ------------------------------------------------------------- check --
    def check(self):
        if self.state["phase"] in ("downloading", "installing"):
            return self.public()
        self._set(phase="checking", error="")
        try:
            r = requests.get(f"{API}/repos/{GITHUB_REPO}/releases/latest", timeout=10,
                             headers={"Accept": "application/vnd.github+json",
                                      "User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            if r.status_code == 404:
                self._set(phase="none", available=False)
                return self.public()
            r.raise_for_status()
            rel = r.json()
            tag = rel.get("tag_name") or ""
            asset = next((a for a in rel.get("assets", [])
                          if a.get("name", "").lower().endswith("-setup.exe")), None)
            newer = parse_version(tag) > parse_version(APP_VERSION)
            available = bool(newer and asset)
            self.asset = asset if available else None
            self._set(latest=tag, available=available,
                      skipped=available and self.cfg["skip_version"] == tag,
                      phase="available" if available else "none",
                      notes=(rel.get("body") or "")[:1500],
                      size=(asset or {}).get("size", 0))
        except Exception as e:
            self._set(phase="error", error=str(e)[:200])
        return self.public()

    def check_later(self, delay=4.0):
        def go():
            time.sleep(delay)
            self.check()
        threading.Thread(target=go, daemon=True).start()

    def skip(self):
        if self.state["latest"]:
            self.cfg.update({"skip_version": self.state["latest"]})
            self._set(skipped=True)

    # ----------------------------------------------------------- install --
    def install(self, before_exit=None) -> bool:
        if not self.state["can_install"] or not self.asset:
            return False
        if self.state["phase"] in ("downloading", "installing"):
            return True
        self._set(phase="downloading", pct=0, error="")
        threading.Thread(target=self._download_and_run, args=(before_exit,), daemon=True).start()
        return True

    def _download_and_run(self, before_exit):
        a = self.asset
        path = Path(tempfile.gettempdir()) / "BrainrotGoonMachine-Setup.exe"
        try:
            sha = hashlib.sha256()
            done, total = 0, int(a.get("size") or 0)
            with requests.get(a["browser_download_url"], stream=True, timeout=(10, 60),
                              headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}) as r:
                r.raise_for_status()
                total = total or int(r.headers.get("content-length") or 0)
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        sha.update(chunk)
                        done += len(chunk)
                        if total:
                            self._set(pct=int(done * 100 / total))
            if total and done != total:
                raise IOError(f"download cut off ({done} of {total} bytes)")
            digest = str(a.get("digest") or "")
            if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
                raise IOError("download damaged (sha256 no match)")
            self._set(phase="installing", pct=100)
            if before_exit:
                before_exit()
            if os.name != "nt":
                path.chmod(0o755)
            subprocess.Popen([str(path), *SETUP_FLAGS], creationflags=NO_WINDOW)
            time.sleep(2.5)  # let the UI show "installing" before we vanish
            self.on_exit()
        except Exception as e:
            self._set(phase="error", error=str(e)[:200])
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
