"""The goon loop: find -> download -> dedupe -> look/listen -> judge -> keep or yeet."""
import hashlib
import os
import itertools
import random
import re
import shutil
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from . import collect, ears, media, tools
from .brain import BrainError, GeminiBrain, OllamaBrain, _ollama_exe
from .paths import data_dir, thumbs_dir, tmp_dir
from .lang import ai_style, localize_verdict, say


def _safe(name: str, n=60) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f#]+', " ", name or "vida")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:n] or "vida").strip()


# A broad word like "brainrot" is too vague for one YouTube search, so it gets mixed with
# lots of different kinds of weird/brainrot videos (not just Italian brainrot).
GENERIC_WORDS = {"brainrot", "brain rot", "brainrot videos", "brainrot vids", "rot", "weird",
                 "weird videos", "weird vids", "random", "memes", "meme", "cursed"}
BRAINROT_MIX = [
    "brainrot memes", "weird tiktok memes", "cursed videos", "skibidi toilet", "sigma edit",
    "ohio memes", "67 meme", "italian brainrot", "tung tung tung sahur", "subway surfers split screen",
    "gen alpha slang meme", "random weird videos", "bass boosted meme", "npc meme", "fanum tax meme",
    "cat meme loud music", "ai slop funny", "brainrot compilation shorts", "unhinged memes",
    "deep fried memes",
]


class Engine:
    def __init__(self, cfg, db, hw):
        self.cfg, self.db, self.hw = cfg, db, hw
        self.log_lines = deque(maxlen=400)
        self._n = itertools.count(1)
        self.stop = threading.Event()
        self.thread = None
        self.progress = {"kept": 0, "checked": 0, "target": 0, "step": "", "title": "", "pct": None}
        self.brain_label = ""
        self._ear_broken = False
        self.tally = {"found": 0, "seen": 0, "long": 0, "live": 0, "fail": 0,
                      "nope": 0, "dupe": 0, "kept": 0, "best": -1}
        self.sources, self.src_off = ["youtube"], set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------ logging --
    def log(self, key, kind="info", **kw):
        with self._lock:
            line = {"i": next(self._n), "t": time.time(), "kind": kind,
                    "key": key, "text": say(key, self.cfg["lang"], **kw)}
            self.log_lines.append(line)
            try:  # thoughts.txt: for when something goes wrong and you need to show someone
                f = data_dir() / "thoughts.txt"
                if f.exists() and f.stat().st_size > 2_000_000:
                    f.replace(f.with_suffix(".old.txt"))
                with open(f, "a", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"[{kind}] {line['text']}\n")
            except OSError:
                pass

    def step(self, step, title=None, pct=None):
        self.progress["step"] = step
        if title is not None:
            self.progress["title"] = title
        self.progress["pct"] = pct

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    # -------------------------------------------------------------- brain --
    def pick_backend(self) -> str:
        b = self.cfg["backend"]
        if b in ("ollama", "gemini"):
            return b
        has_key = bool(self.cfg["gemini_key"])
        if self.hw["recommend"] == "ollama":
            if not _ollama_exe() and has_key and not self._ollama().alive():
                return "gemini"
            return "ollama"
        return "gemini" if has_key else "ollama"

    def ollama_model(self):
        return self.cfg["ollama_model"] or self.hw["model"]

    def _ollama(self):
        return OllamaBrain(self.cfg["ollama_url"], self.ollama_model(), self.cfg["taste"])

    def make_brain(self):
        if self.pick_backend() == "gemini":
            return GeminiBrain(self.cfg["gemini_key"], self.cfg["gemini_model"], self.cfg["taste"],
                               log=lambda k, **kw: self.log(k, "warn", **kw))
        return self._ollama()

    def brain_status(self) -> dict:
        backend = self.pick_backend()
        if backend == "gemini":
            b = GeminiBrain(self.cfg["gemini_key"], self.cfg["gemini_model"])
            st = b.status()
        else:
            b = self._ollama()
            st = b.status()
        st.update({"backend": backend, "label": b.label})
        return st

    def prepare_brain(self, brain):
        if isinstance(brain, GeminiBrain):
            st = brain.status()
            if st["state"] != "ready":
                self.log({"no_key": "no_key", "bad_key": "bad_key", "bad_model": "bad_model"}
                         .get(st["state"], "offline"), "bad",
                         error=st.get("error", ""), model=brain.model)
                return False
            return True
        if not brain.alive():
            self.log("ollama_starting")
            self.step("waking brain")
            if not brain.try_start():
                self.log("no_ollama", "bad")
                return False
        if not brain.has_model():
            self.step("downloading brain", brain.model, 0)
            last = [-10]

            def prog(status, done, total):
                pct = int(done * 100 / total) if total else 0
                self.progress["pct"] = pct
                if pct >= last[0] + 10:
                    last[0] = pct
                    self.log("pull", model=brain.model, pct=pct)
            brain.pull(prog, self.stop)
            self.log("pull_done", "good")
        return True

    # -------------------------------------------------------------- chill --
    def _apply_chill(self, brain):
        """'Go easy on me pc': low priority for us + everything we start, fewer threads."""
        chill = bool(self.cfg["chill_cpu"])
        media.CHILL = chill
        try:
            import psutil
            me = psutil.Process()
            if os.name == "nt":
                me.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if chill else psutil.NORMAL_PRIORITY_CLASS)
            elif chill:
                me.nice(max(me.nice(), 10))
        except Exception:
            pass
        # local AI running on the CPU (no GPU): don't let it take every core
        if hasattr(brain, "num_thread"):
            no_gpu = self.hw.get("recommend") != "ollama"
            brain.num_thread = max(2, (self.hw.get("cores") or 4) // 2) if (chill and no_gpu) else None

    # -------------------------------------------------------------- tools --
    def prepare_tools(self) -> bool:
        """ffmpeg + deno + yt-dlp must exist. First run downloads them (~75MB)."""
        st = tools.status()
        if not st["core_ready"] or st["busy"]:
            self.log("tools_wait")
            self.step("tools")
        try:
            tools.ensure_core(refresh=False)
        except tools.ToolError as e:
            self.log("tools_fail", "bad", err=str(e)[:220])
            return False
        before = tools.ytdlp_version()
        now = tools.activate_ytdlp()   # safe here: nothing is downloading yet
        if now and before and now != before:
            self.log("ytdlp_updated", "good", v=now)
        return True

    # --------------------------------------------------------------- run --
    def start(self, query: str, links: str, count: int) -> bool:
        if self.running:
            return False
        self.stop.clear()
        self.thread = threading.Thread(target=self._run_safe, args=(query, links, count), daemon=True)
        self.thread.start()
        return True

    def _run_safe(self, *a):
        try:
            self._run(*a)
        except Exception as e:
            self.log("crash", "bad", err=f"{type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            self.step("")
            self.progress["title"] = ""

    def _search_gens(self, q, n, kind, sites):
        """One search per site for these words: (kind, q, generator, log extras)."""
        out = []
        if "tiktok" in sites:
            out.append(("web_search", q, collect.search_tiktok(q, max(n // 2, 20), self.cfg),
                        {"site": "TikTok"}))
        if "instagram" in sites:
            out.append(("web_search", q, collect.search_instagram(q, max(n // 3, 12), self.cfg),
                        {"site": "Instagram"}))
        if "youtube" in sites:
            out.append((kind, q, collect.search_youtube(q, n, self.cfg), {}))
        return out

    def _phase(self, words, sites, pool, mix, generic):
        """Search these sites: the words (+5 kinds of rot for a broad word), then dig deeper."""
        gens = []
        for w in words:
            gens += self._search_gens(w, pool, "search", sites)
        for q in (mix[:5] if generic else []):
            gens += self._search_gens(q, max(pool // 3, 20), "search", sites)
        yield from self._round_robin(gens)
        if self.stop.is_set():
            return
        extra = []
        for q in (mix[5:] if generic else []):
            extra += self._search_gens(q, max(pool // 3, 20), "widen", sites)
        for w in words:
            if w in generic:
                continue
            for more in ("shorts", "meme", "edit", "funny"):
                if more not in w.lower():
                    extra += self._search_gens(f"{w} {more}", pool // 2, "widen", sites)
        yield from self._round_robin(extra)

    def _sources(self, query, links, count):
        pool = min(max(count * 6, 40), 250)
        link_list = [l.strip() for l in (links or "").splitlines() if l.strip().startswith("http")]
        words = [w.strip() for w in (query or "").split(",") if w.strip()]
        mix = BRAINROT_MIX[:]
        random.shuffle(mix)
        generic = [w for w in words if w.lower() in GENERIC_WORDS]
        mode = self.cfg["source_mode"]
        main = ["tiktok", "instagram"] if mode in ("only", "first") else ["tiktok", "instagram", "youtube"]
        backup = ["youtube"] if mode == "first" else []
        self.sources = main + backup
        # pasted links always count, whatever site they are
        yield from self._round_robin([("link", l, collect.expand_link(l, pool, self.cfg), {})
                                      for l in link_list])
        yield from self._phase(words, main, pool, mix, generic)
        if backup and not self.stop.is_set():   # TikTok + Insta ran dry: fill the rest from YouTube
            self.log("backup", "warn")
            yield from self._phase(words, backup, pool, mix, generic)

    def _round_robin(self, gens):
        """Take turns between searches/links/sites so every word and site gets a go."""
        started = set()
        while gens:
            if self.stop.is_set():
                return
            for g in list(gens):
                if self.stop.is_set():
                    return
                kind, q, it, extra = g
                if (kind, q, tuple(extra.items())) not in started:
                    started.add((kind, q, tuple(extra.items())))
                    self.log(kind, q=q[:80], **extra)
                    self.step("searching", q)
                try:
                    c = next(it)
                    if c["src"] in self.src_off:
                        continue
                    self.tally["found"] += 1
                    yield c
                except StopIteration:
                    gens.remove(g)
                except Exception as e:
                    self.log("search_fail", "bad", q=(extra.get("site", "") + " " + q).strip()[:60],
                             err=str(e).replace("ERROR: ", "")[:200])
                    gens.remove(g)

    def _run(self, query, links, count):
        cfg = self.cfg
        count = max(1, min(int(count or 10), 500))
        self.progress.update({"kept": 0, "checked": 0, "target": count})
        self.log("start", "good")

        brain = self.make_brain()
        self.brain_label = brain.label
        self.log("brain_pick", brain=brain.label)
        if not self.prepare_tools():
            return
        if not self.prepare_brain(brain):
            return

        threshold = cfg["threshold"]
        cave = cfg.cave()
        ear = cfg["ear_mode"]
        wsize = cfg["whisper_size"]
        if wsize == "auto":
            wsize = self.hw.get("whisper", "base")
        self._apply_chill(brain)
        fails_in_row, last_err = 0, ""
        self.sources = [x for x in (cfg["sources"] or "youtube").split(",") if x]
        self.src_off, src_fails = set(), {}
        self._ear_broken = False
        self.tally = {"found": 0, "seen": 0, "long": 0, "live": 0, "fail": 0,
                      "nope": 0, "dupe": 0, "kept": 0, "best": -1}
        collect.warn = lambda k, **kw: self.log(k, "warn", **kw)
        collect.warned.clear()

        for cand in self._sources(query, links, count):
            if self.stop.is_set():
                self.log("stopped", "warn")
                return
            if self.progress["kept"] >= count:
                break
            if cand["src"] in self.src_off:
                continue
            if self.db.seen(cand["key"]):
                self.tally["seen"] += 1
                continue
            if cand["live"]:
                self.tally["live"] += 1
                self.log("live")
                continue
            if cand["duration"] and cand["duration"] > cfg["max_secs"]:
                self.tally["long"] += 1
                self.log("too_long", s=int(cand["duration"]))
                continue

            work = tmp_dir() / hashlib.sha1(cand["key"].encode()).hexdigest()[:12]
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
            try:
                result = self._one(cand, work, brain, threshold, cave, ear, wsize)
            except collect.TooLong as e:
                self.tally["long"] += 1
                self.log("too_long", s=int(e.args[0]))
                result = "skip"
            except Exception as e:
                if self.stop.is_set():
                    break
                result, last_err = "fail", str(e)
                fail_kind = "dl_fail" if "download" in self.progress["step"] else "brain_fail"
                self.log(fail_kind, "bad", err=str(e)[:220])
                self.db.add(key=cand["key"], url=cand["url"], title=cand["title"], status="fail",
                            query=cand["query"])
            finally:
                shutil.rmtree(work, ignore_errors=True)

            if result in self.tally:
                self.tally[result] += 1
            src = cand["src"]
            src_fails[src] = src_fails.get(src, 0) + 1 if result == "fail" else 0
            if result == "fail" and src_fails[src] >= 4 and src != "youtube" and \
                    len(set(self.sources) - self.src_off) > 1:
                # one site keeps breaking (e.g. Instagram wants login): skip it, keep the rest
                self.src_off.add(src)
                self.log("src_off", "warn", site=src.capitalize(), err=last_err[:140])
                fails_in_row = 0
                continue
            if result == "fail":
                fails_in_row += 1
                if fails_in_row >= 8:
                    self.log(fail_kind + "_many", "bad", err=last_err[:200])
                    self._summary(threshold, last_err)
                    return
            elif result != "skip":
                fails_in_row = 0
                self.progress["checked"] += 1

        k = self.progress["kept"]
        if self.stop.is_set():
            self.log("stopped", "warn")
        elif k >= count:
            self.log("done", "good", k=k)
        else:
            self.log("empty", "warn", k=k)
        self._summary(threshold, last_err)

    def _summary(self, threshold, last_err=""):
        """Say what happened, and the most likely fix when not enough rot was found."""
        t = self.tally
        self.log("summary", n=t["found"], kept=t["kept"], nope=t["nope"], dupe=t["dupe"],
                 long=t["long"], seen=t["seen"], fail=t["fail"])
        if t["kept"]:
            self.log("sites_got", tt=t.get("site_tiktok", 0), ig=t.get("site_instagram", 0),
                     yt=t.get("site_youtube", 0))
        if self.progress["kept"] >= self.progress["target"] or self.stop.is_set():
            return
        tt_ig = t.get("site_tiktok", 0) + t.get("site_instagram", 0)
        if self.cfg["source_mode"] == "only" and tt_ig == 0:
            self.log("hint_ttig", "warn")
        elif t["found"] == 0:
            self.log("no_results", "warn")
        elif t["nope"] and t["best"] < threshold:
            self.log("hint_low", "warn", best=max(t["best"], 0), th=threshold)
        elif t["seen"] >= max(t["found"] // 2, 1):
            self.log("hint_seen", "warn")
        elif t["long"] >= max(t["found"] // 3, 1):
            self.log("hint_long", "warn")
        elif t["fail"] >= max(t["found"] // 3, 1):
            self.log("hint_fail", "warn", err=last_err[:160])

    def _one(self, cand, work, brain, threshold, cave, ear, wsize) -> str:
        title = cand["title"] or cand["url"]
        self.step("downloading", title)
        self.log("dl", title=title[:90])
        path, info = collect.download(cand, work, self.cfg, stop=self.stop)
        meta = {**cand,
                "title": info.get("title") or cand["title"],
                "uploader": info.get("uploader") or info.get("channel") or cand["uploader"],
                "duration": info.get("duration") or cand["duration"],
                "tags": info.get("tags") or cand["tags"],
                "description": info.get("description") or cand["description"]}
        dur = media.duration(path) or meta["duration"] or 0
        meta["duration"] = dur

        if self.stop.is_set():
            return "skip"

        # dedupe by what's on screen, not by url
        self.step("checking dupes", meta["title"])
        hashes = media.frame_hashes(path)
        dup = self.db.find_dupe(hashes)
        if dup:
            self.log("dupe", id=dup)
            self.db.add(key=cand["key"], url=cand["url"], title=meta["title"], status="dupe",
                        dupe_of=dup, duration=dur, query=cand["query"])
            return "dupe"

        self.step("looking", meta["title"])
        self.log("look")
        frames = media.grab_frames(path, work / "frames", n=4, dur=dur)

        transcript = ""
        if ear and not self._ear_broken and media.has_audio(path):
            self.step("listening", meta["title"])
            self.log("listen")
            try:
                transcript = ears.listen(path, work, wsize,
                                         log=lambda k, **kw: self.log(k, **kw), stop=self.stop)
                if transcript:
                    self.log("heard", text=transcript[:120])
            except Exception as e:
                self.log("ear_fail", "warn", err=str(e)[:160])
                self._ear_broken = True

        if self.stop.is_set():
            return "skip"
        self.step("judging", meta["title"])
        brain.style = ai_style(self.cfg["lang"])
        try:
            v = brain.rate(meta, frames, transcript)
        except BrainError as e:
            raise RuntimeError(str(e)) from e
        v = localize_verdict(v, self.cfg["lang"])

        self.tally["best"] = max(self.tally["best"], v["score"])
        keep = v["score"] >= threshold
        if keep:
            self.tally["site_" + cand["src"]] = self.tally.get("site_" + cand["src"], 0) + 1
        thumb = thumbs_dir() / (hashlib.sha1(cand["key"].encode()).hexdigest()[:16] + ".jpg")
        dest = None
        if keep:
            dest = cave / f"{v['score']:02d}_{_safe(meta['title'])}_{_safe(cand['id'], 20)}{path.suffix}"
            shutil.move(str(path), dest)
            media.thumb(dest, thumb, dur)
            self.progress["kept"] += 1
            self.log("keep", "good", score=v["score"], why=v["why"])
        else:
            if self.cfg["keep_rejects"]:
                nope = cave / "_nope"
                nope.mkdir(exist_ok=True)
                dest = nope / f"{v['score']:02d}_{_safe(meta['title'])}_{_safe(cand['id'], 20)}{path.suffix}"
                shutil.move(str(path), dest)
            self.log("nope", score=v["score"], why=v["why"])

        vid = self.db.add(key=cand["key"], url=cand["url"], title=meta["title"],
                          uploader=meta["uploader"], duration=dur,
                          status="kept" if keep else "nope", score=v["score"], vibe=v["vibe"],
                          why=v["why"], path=str(dest) if dest else None,
                          thumb=str(thumb) if keep and thumb.exists() else None,
                          query=cand["query"], brain=brain.label)
        self.db.add_hashes(vid, hashes)
        return "kept" if keep else "nope"
