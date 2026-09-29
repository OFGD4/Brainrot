"""The goon loop, as a pipeline so nothing waits on anything else:

  search (main thread) -> fetch (download, AI check, dupe check, frames, ears) -> judge (1-2 AI brains)

While the brain judges video 1, video 2 is already downloading.

STOP is instant: every slow step (search, download, AI thinking, waits) runs where STOP can walk
away from it. Leftovers of a stopped run finish quietly in the background and never touch
anything (each run has its own `halt` switch).

NO AI SLOP: AI videos + AI accounts are thrown out before download (aifilter.py) and again by
the AI judge after looking (brain.py "ai" score). Accounts caught posting AI get blocked.
"""
import hashlib
import os
import itertools
import queue
import random
import re
import shutil
import threading
import time
import traceback
from collections import deque

from . import aifilter, collect, ears, media, net, tools
from .brain import (AI_LIMIT, Busy, GeminiBrain, OllamaBrain, Refused, Stopped as
                    BrainStopped, Tired, _ollama_exe)
from .paths import data_dir, thumbs_dir, tmp_dir
from .lang import ai_style, localize_verdict, say


def _safe(name: str, n=60) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f#]+', " ", name or "vida")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:n] or "vida").strip()


# A broad word like "brainrot" is too vague for one search, so it gets mixed with lots of
# different kinds of weird / meme / edit videos. No AI topics (no Italian brainrot, no AI slop).
GENERIC_WORDS = {"brainrot", "brain rot", "brainrot videos", "brainrot vids", "rot", "weird",
                 "weird videos", "weird vids", "random", "memes", "meme", "cursed", "edits",
                 "weird edits", "funny", "funny videos"}
BRAINROT_MIX = [
    "brainrot memes", "weird tiktok memes", "cursed videos", "skibidi toilet", "sigma edit",
    "ohio memes", "67 meme", "subway surfers split screen", "gen alpha slang meme", "goofy ahh memes",
    "random weird videos", "bass boosted meme", "npc meme", "fanum tax meme", "cat meme loud music",
    "brainrot edit", "weird edits", "cursed edit", "meme edit", "phonk meme edit", "shitpost",
    "unhinged memes", "deep fried memes", "dank memes", "funny memes tiktok", "mewing meme",
    "rizz meme", "brainrot compilation shorts", "meme compilation", "among us meme",
]


class Stopped(Exception):
    """STOP pressed (or the run is over): walk away now."""


class Run:
    """One press of START. Everything belonging to it checks its own `halt`."""
    _ids = itertools.count(1)

    def __init__(self, count):
        self.n = next(self._ids)
        self.count = count
        self.halt = threading.Event()        # STOP pressed, or run finished: everybody quit
        self.cands = queue.Queue(maxsize=3)  # found -> fetch
        self.ready = queue.Queue(maxsize=3)  # fetched -> judge
        self.retry = deque()                 # videos a brain handed back (busy / refused)
        self.pending = 0                     # videos somewhere in the pipeline
        self.search_done = False
        self.tried = set()                   # videos already in this run (found by 2 searches)
        self.enough = False
        self.end = None                      # fatal reason key, if the run gave up
        self.lock = threading.RLock()
        self.brains = []
        self.work = tmp_dir() / f"run{self.n}"

    def over(self):
        return self.halt.is_set()

    def done_one(self):
        with self.lock:
            self.pending -= 1


class Team:
    """Who judges. Gemini (fast, free tries per minute/day) + Ollama (your PC, never runs out).
    parallel=True: both judge at the same time. False (weak PC): Ollama only steps in while
    Google says 'slow down' or is out of free tries."""

    def __init__(self, brains, parallel):
        self.brains = brains
        self.parallel = parallel
        self.out = set()          # retired brains
        self.rest_until = 0.0     # Gemini told to slow down until then

    def alive(self):
        return [b for b in self.brains if b.kind not in self.out]

    def has(self, kind):
        return any(b.kind == kind for b in self.alive())

    def gemini_ready(self):
        return self.has("gemini") and time.time() >= self.rest_until

    def ollama_turn(self):
        return self.parallel or not self.gemini_ready()


class Engine:
    def __init__(self, cfg, db, hw):
        self.cfg, self.db, self.hw = cfg, db, hw
        self.log_lines = deque(maxlen=400)
        self._n = itertools.count(1)
        self.stop = threading.Event()        # user pressed STOP
        self.thread = None
        self.run = None
        self.progress = {"kept": 0, "checked": 0, "target": 0, "step": "", "title": "", "pct": None}
        self.brain_label = ""
        self._ear_broken = False
        self._judging = 0                    # brains thinking right now
        self.tally = self._new_tally()
        self.sources, self.src_off = ["youtube"], set()
        self._lock = threading.Lock()

    @staticmethod
    def _new_tally():
        return {"found": 0, "seen": 0, "long": 0, "live": 0, "fail": 0, "nope": 0, "dupe": 0,
                "kept": 0, "ai": 0, "best": -1}

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

    def _rlog(self, run, key, kind="info", **kw):
        """Log for a run: silent once that run is stopped/over."""
        if not run.over():
            self.log(key, kind, **kw)

    def step(self, step, title=None, pct=None):
        self.progress["step"] = step
        if title is not None:
            self.progress["title"] = title
        self.progress["pct"] = pct

    def _step(self, run, step, title=None):
        """Progress line. While a brain is judging, that's what the user sees."""
        if not run.over() and self._judging <= 0:
            self.step(step, title)

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    # --------------------------------------------------------- STOP helpers --
    def request_stop(self):
        """STOP: everything of this run quits now; the AI stops thinking too."""
        self.stop.set()
        run = self.run
        if run is not None:
            run.halt.set()
            for b in run.brains:
                if hasattr(b, "abort"):
                    b.abort()

    def _call(self, run, fn, *a, **kw):
        """Do a slow thing in a helper thread. STOP returns at once and leaves it behind."""
        box = {}
        done = threading.Event()

        def job():
            try:
                box["v"] = fn(*a, **kw)
            except BaseException as e:   # noqa: B036 - hand everything back to the caller
                box["e"] = e
            finally:
                done.set()
        threading.Thread(target=job, daemon=True).start()
        while not done.wait(0.05):
            if run.over():
                raise Stopped()
        if run.over():
            raise Stopped()
        if "e" in box:
            raise box["e"]
        return box["v"]

    @staticmethod
    def _put(run, q, item):
        while True:
            try:
                q.put(item, timeout=0.1)
                return
            except queue.Full:
                if run.over():
                    raise Stopped()

    @staticmethod
    def _get(run, q, timeout=0.1):
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    # -------------------------------------------------------------- brain --
    def pick_backend(self) -> str:
        """auto: both brains as a tag team if you have a Google key AND Ollama, else whichever."""
        b = self.cfg["backend"]
        if b in ("ollama", "gemini", "both"):
            return b
        has_key = bool(self.cfg["gemini_key"])
        has_ollama = bool(_ollama_exe()) or self._ollama().alive()
        if has_key and has_ollama:
            return "both"
        if has_key:
            return "gemini"
        return "ollama"

    def ollama_model(self):
        return self.cfg["ollama_model"] or self.hw["model"]

    def _ollama(self):
        return OllamaBrain(self.cfg["ollama_url"], self.ollama_model(), self.cfg["taste"])

    def _gemini(self):
        return GeminiBrain(self.cfg["gemini_key"], self.cfg["gemini_model"], self.cfg["taste"],
                           log=lambda k, **kw: self.log(k, "warn", **kw))

    def make_brain(self):
        return self._gemini() if self.pick_backend() == "gemini" else self._ollama()

    def brain_status(self) -> dict:
        backend = self.pick_backend()
        if backend == "both":
            g, o = self._gemini(), self._ollama()
            gs, os_ = g.status(), o.status()
            gs.update(backend="gemini", label=g.label)
            os_.update(backend="ollama", label=o.label)
            if gs["state"] == "ready" and os_["state"] == "ready":
                return {"state": "ready", "backend": "both", "team": True,
                        "label": "gemini + ollama", "model": o.model}
            if gs["state"] == "ready" or os_["state"] == "ready":
                ok, other = (gs, os_) if gs["state"] == "ready" else (os_, gs)
                return {**ok, "backend": "both", "team": True, "other": other}
            return {**os_, "backend": "both", "team": True, "other": gs}
        b = self._gemini() if backend == "gemini" else self._ollama()
        st = b.status()
        st.update({"backend": backend, "label": b.label})
        return st

    def prepare_brain(self, brain, stop=None, pull=True):
        """Ready a brain: check the Google key, or wake Ollama + download its model."""
        stop = stop or threading.Event()
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
            if not brain.try_start(stop):
                self.log("no_ollama", "bad")
                return False
        if not brain.has_model():
            if not pull:
                return False
            self.step("downloading brain", brain.model, 0)
            last = [-10]

            def prog(status, done, total):
                pct = int(done * 100 / total) if total else 0
                self.progress["pct"] = pct
                if pct >= last[0] + 10:
                    last[0] = pct
                    self.log("pull", model=brain.model, pct=pct)
            brain.pull(prog, stop)
            self.log("pull_done", "good")
        return True

    def _brains(self, run):
        """The judges for this run: [brain] or [gemini, ollama] (tag team)."""
        backend = self.pick_backend()
        if backend != "both":
            b = self._gemini() if backend == "gemini" else self._ollama()
            b.stop = run.halt
            self.log("brain_pick", brain=b.label)
            return [b] if self.prepare_brain(b, run.halt) else []
        g, o = self._gemini(), self._ollama()
        team = []
        gs = g.status()
        if gs["state"] == "ready":
            team.append(g)
        else:
            self.log("team_half", "warn", brain="Gemini", why=gs.get("error") or gs["state"],
                     other="Ollama")
        if o.alive() or o.try_start(run.halt):
            if o.has_model():
                team.append(o)
            elif not team:                   # Google no work: local brain must do it, download it
                if self.prepare_brain(o, run.halt):
                    team.append(o)
            else:
                self.log("team_no_model", "warn", model=o.model)
        elif team:
            self.log("team_half", "warn", brain="Ollama", why="not running / not installed",
                     other="Gemini")
        if not team:
            self.log("no_ollama", "bad")
            return []
        for b in team:
            b.stop = run.halt
        if len(team) == 1:
            self.log("brain_pick", brain=team[0].label)
        else:
            g.handoff = True                 # Google busy: hand the video to Ollama, don't wait
            g.gap = 4.5                      # push Google harder: a "slow down" costs nothing now
            parallel = self.hw.get("recommend") == "ollama" or not self.cfg["chill_cpu"]
            self.log("team" if parallel else "team_backup", "good", g=g.model, o=o.model)
        return team

    # -------------------------------------------------------------- chill --
    def _apply_chill(self, brains):
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
        for brain in brains:
            if hasattr(brain, "num_thread"):
                no_gpu = self.hw.get("recommend") != "ollama"
                brain.num_thread = max(2, (self.hw.get("cores") or 4) // 2) if (chill and no_gpu) \
                    else None

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
        count = max(1, min(int(count or 10), 500))
        run = Run(count)
        self.run = run
        self.thread = threading.Thread(target=self._run_safe, args=(run, query, links), daemon=True)
        self.thread.start()
        return True

    def _run_safe(self, run, *a):
        try:
            self._run(run, *a)
        except Exception as e:
            self.log("crash", "bad", err=f"{type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            run.halt.set()
            self.step("")
            self.progress["title"] = ""

    def _count(self, run, key, n=1):
        with run.lock:
            self.tally[key] = self.tally.get(key, 0) + n

    def _run(self, run, query, links):
        cfg = self.cfg
        count = run.count
        self.progress.update({"kept": 0, "checked": 0, "target": count, "pct": None})
        self.tally = self._new_tally()
        self.log("start", "good")
        collect.warn = lambda k, **kw: self._rlog(run, k, "warn", **kw)
        collect.warned = set()
        collect.user_blocked = self.db.ai_blocked
        self.src_off, self.src_fails, self.fails_in_row, self.last_err = set(), {}, 0, ""
        self._ear_broken = False
        self._judging = 0
        self._ai_users_said = set()
        for old in tmp_dir().glob("run*"):          # leftovers of earlier runs
            shutil.rmtree(old, ignore_errors=True)

        try:
            if not self._call(run, self.prepare_tools):
                return
            brains = self._call(run, self._brains, run)
        except (Stopped, BrainStopped):
            self.log("stopped", "warn")
            return
        if not brains:
            return
        run.brains = brains
        self.brain_label = " + ".join(b.kind for b in brains) if len(brains) > 1 else brains[0].label
        self._apply_chill(brains)
        style = ai_style(cfg["lang"])
        for b in brains:
            b.style = style
            if isinstance(b, OllamaBrain):   # load the model while we search + download
                threading.Thread(target=b.warm, daemon=True).start()
        # good GPU (or "go easy on me pc" off): both brains judge at once. Weak PC: the local
        # brain only jumps in when Google can't, so the CPU stays calm.
        team = Team(brains, parallel=self.hw.get("recommend") == "ollama" or not cfg["chill_cpu"])

        if not net.browser_ok():
            self.log("no_disguise", "warn")
        words = [w.strip() for w in (query or "").split(",") if w.strip()]
        if any(aifilter.query_is_ai(w) for w in words):
            self.log("ai_query", "warn")

        wsize = cfg["whisper_size"]
        if wsize == "auto":
            wsize = self.hw.get("whisper", "base")
        opts = {"threshold": cfg["threshold"], "cave": cfg.cave(), "ear": cfg["ear_mode"],
                "wsize": wsize, "team": team}
        for _ in range(1 if cfg["chill_cpu"] else 2):
            threading.Thread(target=self._fetch_loop, args=(run, opts), daemon=True).start()
        for b in brains:
            threading.Thread(target=self._judge_loop, args=(run, b, opts), daemon=True).start()

        try:
            for cand in self._sources(run, query, links, count):
                if run.over():
                    break
                if not self._precheck(run, cand):
                    continue
                with run.lock:
                    run.pending += 1
                self._put(run, run.cands, cand)
            run.search_done = True
            while not run.over():                     # let the last videos finish
                with run.lock:
                    if run.pending <= 0:
                        break
                run.halt.wait(0.1)
        except Stopped:
            pass
        finally:
            run.halt.set()                            # workers: quit

        k = self.progress["kept"]
        if self.stop.is_set():
            self.log("stopped", "warn")
        elif run.end:
            pass                                      # already said why
        elif k >= count:
            self.log("done", "good", k=k)
        else:
            self.log("empty", "warn", k=k)
        self._summary(run)

    # --------------------------------------------------------- searching --
    def _search_gens(self, q, n, kind, sites):
        """One search per site for these words: (kind, q, generator, log extras)."""
        out = []
        if "tiktok" in sites:
            out.append(("web_search", q, collect.search_tiktok(q, max(n // 2, 20), self.cfg),
                        {"site": "TikTok", "src": "tiktok"}))
        if "instagram" in sites:
            out.append(("web_search", q, collect.search_instagram(q, max(n // 3, 12), self.cfg),
                        {"site": "Instagram", "src": "instagram"}))
        if "youtube" in sites:
            out.append((kind, q, collect.search_youtube(q, n, self.cfg), {"src": "youtube"}))
        return out

    def _phase(self, run, words, sites, pool, mix, generic):
        """Search these sites: the words (+5 kinds of rot for a broad word), then dig deeper."""
        gens = []
        for w in words:
            gens += self._search_gens(w, pool, "search", sites)
        for q in (mix[:5] if generic else []):
            gens += self._search_gens(q, max(pool // 3, 20), "search", sites)
        yield from self._round_robin(run, gens)
        extra = []
        for q in (mix[5:] if generic else []):
            extra += self._search_gens(q, max(pool // 3, 20), "widen", sites)
        for w in words:
            if w in generic:
                continue
            for more in ("shorts", "meme", "edit", "funny"):
                if more not in w.lower():
                    extra += self._search_gens(f"{w} {more}", pool // 2, "widen", sites)
        yield from self._round_robin(run, extra)

    def _sources(self, run, query, links, count):
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
        yield from self._round_robin(run, [("link", l, collect.expand_link(l, pool, self.cfg), {})
                                           for l in link_list])
        yield from self._phase(run, words, main, pool, mix, generic)
        if backup and not run.over():   # TikTok + Insta ran dry: fill the rest from YouTube
            self.log("backup", "warn")
            yield from self._phase(run, words, backup, pool, mix, generic)

    FEEDERS = 6   # searches running at the same time

    def _round_robin(self, run, gens):
        """Take turns between searches/links/sites so every word and site gets a go.
        Every search runs in its own background feeder, so a slow site (or a slow web search)
        never holds up the fast ones, and STOP never waits for any of them."""
        todo = list(gens)
        live = []           # [kind, q, queue, extra]
        started = set()

        def feed(it, q):
            try:
                for c in it:
                    while not run.over():
                        try:
                            q.put(("c", c), timeout=0.2)
                            break
                        except queue.Full:
                            pass
                    if run.over():
                        return
                q.put(("end", None))
            except Exception as e:      # noqa: BLE001 - reported by the reader
                q.put(("err", e))

        while todo or live:
            if run.over():
                raise Stopped()
            while todo and len(live) < self.FEEDERS:
                kind, q, it, extra = todo.pop(0)
                if extra.get("src") in self.src_off:
                    continue                 # that site was switched off for this run
                key = (kind, q, tuple(extra.items()))
                if key not in started:
                    started.add(key)
                    self.log(kind, q=q[:80], **extra)
                    self._step(run, "searching", q)
                box = queue.Queue(maxsize=40)
                threading.Thread(target=feed, args=(it, box), daemon=True).start()
                live.append([kind, q, box, extra])
            got = False
            for f in list(live):
                kind, q, box, extra = f
                try:
                    what, c = box.get_nowait()
                except queue.Empty:
                    continue
                got = True
                if what == "end":
                    live.remove(f)
                elif what == "err":
                    live.remove(f)
                    self.log("search_fail", "bad", q=(extra.get("site", "") + " " + q).strip()[:60],
                             err=str(c).replace("ERROR: ", "")[:200])
                elif c["src"] not in self.src_off:
                    self._count(run, "found")
                    yield c
                    if run.over():
                        raise Stopped()
            if not got:
                run.halt.wait(0.05)

    # ------------------------------------------------------ cheap checks --
    def _precheck(self, run, cand) -> bool:
        """Before downloading anything: seen? live? too long? AI?"""
        if cand["src"] in self.src_off or cand["key"] in run.tried:
            return False
        run.tried.add(cand["key"])
        if self.db.seen(cand["key"]):
            self._count(run, "seen")
            return False
        if cand["live"]:
            self._count(run, "live")
            self.log("live")
            return False
        if cand["duration"] and cand["duration"] > self.cfg["max_secs"]:
            self._count(run, "long")
            self.log("too_long", s=int(cand["duration"]))
            return False
        user = cand.get("uploader") or ""
        if user and self.db.ai_blocked(cand["src"], user):
            self._ai(run, cand, f"account {user}", strikes=0)
            return False
        why = aifilter.check(cand)
        if why:
            sure = why.startswith(("account ", "site label"))
            self._ai(run, cand, why, strikes=2 if sure else 1)
            return False
        return True

    def _ai(self, run, cand, why, strikes=1, score_ai=None, hashes=None):
        """An AI video: never keep it, remember it, and strike its account."""
        with run.lock:
            if run.over():
                return
            self.tally["ai"] += 1
            user = cand.get("uploader") or ""
            if score_ai is None:
                if strikes or user.lower() not in self._ai_users_said:
                    self.log("ai_skip", "warn", why=why[:60], title=(cand.get("title") or cand["url"])[:60])
            else:
                self.log("ai_nope", "warn", ai=score_ai, why=why[:160])
            vid = self.db.add(key=cand["key"], url=cand["url"], title=cand.get("title") or "",
                              uploader=user, status="ai", score=0, vibe="AI", why=why[:200],
                              duration=cand.get("duration") or 0, query=cand.get("query"))
            if hashes is not None and len(hashes):
                self.db.add_hashes(vid, hashes)
            if strikes and self.db.ai_strike(cand["src"], user, strikes, why):
                self.log("ai_user", "warn", user=user)
            if user and not strikes:
                self._ai_users_said.add(user.lower())

    # ------------------------------------------------------------- fetch --
    def _fetch_loop(self, run, o):
        while not run.over():
            cand = self._get(run, run.cands)
            if cand is None:
                continue
            item = None
            stage = ["download"]
            try:
                item = self._prep(run, cand, o, stage)
            except collect.TooLong as e:
                self._count(run, "long")
                self._rlog(run, "too_long", s=int(e.args[0]))
            except Exception as e:
                if run.over():
                    return
                self._fail(run, cand, e, "dl_fail" if stage[0] == "download" else "brain_fail")
            if item is None:
                run.done_one()
                continue
            try:
                self._put(run, run.ready, item)
            except Stopped:
                shutil.rmtree(item["work"], ignore_errors=True)
                return

    def _prep(self, run, cand, o, stage):
        """Download + everything that isn't the AI judge. Returns a ready item, or None."""
        work = run.work / hashlib.sha1(cand["key"].encode()).hexdigest()[:12]
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        ok = False
        try:
            title = cand["title"] or cand["url"]
            self._step(run, "downloading", title)
            self._rlog(run, "dl", title=title[:90])
            path, info = collect.download(cand, work, self.cfg, stop=run.halt)
            stage[0] = "check"
            if run.over():
                return None
            meta = {**cand,
                    "title": info.get("title") or cand["title"],
                    "uploader": info.get("uploader") or info.get("channel") or cand["uploader"],
                    "duration": info.get("duration") or cand["duration"],
                    "tags": info.get("tags") or cand["tags"],
                    "description": info.get("description") or cand["description"],
                    "ai_label": info.get("ai_label") or cand.get("ai_label")
                    or aifilter.label_hit(info)}
            # full info (tags, description, account) can show AI stuff the search didn't
            if meta["uploader"] and self.db.ai_blocked(cand["src"], meta["uploader"]):
                self._ai(run, meta, f"account {meta['uploader']}", strikes=0)
                return None
            why = aifilter.check(meta)
            if why:
                sure = why.startswith(("account ", "site label"))
                self._ai(run, meta, why, strikes=2 if sure else 1)
                return None
            dur = media.duration(path) or meta["duration"] or 0
            meta["duration"] = dur
            if dur > self.cfg["max_secs"] + 1:
                raise collect.TooLong(dur)

            # dedupe by what's on screen, not by url
            self._step(run, "checking dupes", meta["title"])
            hashes = media.frame_hashes(path)
            dup = self.db.find_dupe(hashes)
            if dup and not run.over():
                old = self.db.get(dup) or {}
                if old.get("status") == "ai":        # re-upload of an AI video
                    self._ai(run, meta, f"copy of AI vida #{dup}", strikes=1)
                    return None
                self._rlog(run, "dupe", id=dup)
                self.db.add(key=cand["key"], url=cand["url"], title=meta["title"], status="dupe",
                            dupe_of=dup, duration=dur, query=cand["query"])
                self._count(run, "dupe")
                self._ok(run, cand)
                return None
            if run.over():
                return None

            self._step(run, "looking", meta["title"])
            frames = media.grab_frames(path, work / "frames", n=4, width=360, dur=dur)
            sheet = media.frame_sheet(frames, work / "sheet.jpg") if len(frames) > 1 else None
            pics = [sheet] if sheet else frames

            transcript = ""
            if o["ear"] and not self._ear_broken and media.has_audio(path) and not run.over():
                self._step(run, "listening", meta["title"])
                try:
                    transcript = ears.listen(path, work, o["wsize"],
                                             log=lambda k, **kw: self._rlog(run, k, **kw),
                                             stop=run.halt)
                    if transcript:
                        self._rlog(run, "heard", text=transcript[:120])
                        why = aifilter.speech_hit(transcript)
                        if why:
                            self._ai(run, meta, why, strikes=1, hashes=hashes)
                            return None
                except Exception as e:
                    if not run.over():
                        self._rlog(run, "ear_fail", "warn", err=str(e)[:160])
                        self._ear_broken = True
            if run.over():
                return None
            ok = True
            return {"cand": cand, "meta": meta, "path": path, "work": work, "hashes": hashes,
                    "pics": pics, "sheet": bool(sheet), "transcript": transcript, "dur": dur,
                    "avoid": set()}
        finally:
            if not ok:
                shutil.rmtree(work, ignore_errors=True)

    # ------------------------------------------------------------- judge --
    def _next_item(self, run):
        try:
            return run.retry.popleft()
        except IndexError:
            return self._get(run, run.ready, timeout=0.1)

    def _judge_loop(self, run, brain, o):
        team = o["team"]
        fails = 0
        while not run.over():
            if brain.kind in team.out:
                return
            if brain.kind == "ollama" and len(team.alive()) > 1 and not team.ollama_turn():
                run.halt.wait(0.15)          # backup brain: only when Google can't
                continue
            if brain.kind == "gemini":
                if not team.gemini_ready():
                    run.halt.wait(0.15)
                    continue
                w = brain.turn_in()          # free tier pacing: wait BEFORE taking a video
                if w > 0:
                    run.halt.wait(min(w, 0.25))
                    continue
            item = self._next_item(run)
            if item is None:
                continue
            if brain.kind in item["avoid"]:
                if any(b.kind not in item["avoid"] for b in team.alive()):
                    run.retry.append(item)
                    run.halt.wait(0.05)
                else:
                    self._fail_item(run, item, "no brain will judge dis one", "brain_fail")
                continue
            with self._lock:
                self._judging += 1
            if not run.over():
                self.step("judging", item["meta"]["title"])
            try:
                try:
                    v = brain.rate(item["meta"], item["pics"], item["transcript"], sheet=item["sheet"])
                finally:
                    with self._lock:
                        self._judging -= 1
            except (BrainStopped, Stopped):
                return
            except Busy as e:
                if run.over():
                    return
                if len(team.alive()) > 1:     # tag team: Ollama takes over for a bit
                    if time.time() >= team.rest_until:
                        self._rlog(run, "gemini_rest", "warn", s=int(e.delay))
                    team.rest_until = time.time() + e.delay
                else:
                    self._rlog(run, "gemini_slow", "warn", s=int(e.delay))
                    run.halt.wait(e.delay)
                run.retry.append(item)
                continue
            except Tired as e:
                if run.over():
                    return
                team.out.add(brain.kind)
                run.retry.append(item)
                if team.alive():
                    self._rlog(run, "gemini_tired", "warn")
                else:
                    self._give_up(run, "brain_fail_many", str(e))
                return
            except Refused as e:
                if run.over():
                    return
                item["avoid"].add(brain.kind)
                if any(b.kind not in item["avoid"] for b in team.alive()):
                    run.retry.append(item)
                else:
                    self._fail_item(run, item, str(e), "brain_fail")
                continue
            except Exception as e:
                if run.over():
                    return
                fails += 1
                others = [b for b in team.alive() if b is not brain]
                if others and fails >= 3:     # this brain is broken: the other one carries on
                    team.out.add(brain.kind)
                    run.retry.append(item)
                    self._rlog(run, "brain_out", "warn", brain=brain.kind, err=str(e)[:160])
                    return
                if others:
                    run.retry.append(item)    # let the other brain try this one
                else:
                    self._fail_item(run, item, e, "brain_fail")
                continue
            fails = 0
            self._finish(run, item, v, brain, o)

    def _finish(self, run, item, v, brain, o):
        cand, meta, path = item["cand"], item["meta"], item["path"]
        try:
            with run.lock:
                if run.over():
                    return
                v = localize_verdict(v, self.cfg["lang"])
                self.progress["checked"] += 1
                self._ok(run, cand)
                if v.get("ai", 0) >= AI_LIMIT:
                    self._ai(run, meta, v["why"] or "AI", strikes=1, score_ai=v["ai"],
                             hashes=item["hashes"])
                    return
                self.tally["best"] = max(self.tally["best"], v["score"])
                keep = v["score"] >= o["threshold"]
                dur = item["dur"]
                thumb = thumbs_dir() / (hashlib.sha1(cand["key"].encode()).hexdigest()[:16] + ".jpg")
                dest = None
                cave = o["cave"]
                if keep:
                    self.tally["site_" + cand["src"]] = self.tally.get("site_" + cand["src"], 0) + 1
                    self.tally["kept"] += 1
                    dest = cave / (f"{v['score']:02d}_{_safe(meta['title'])}_{_safe(cand['id'], 20)}"
                                   f"{path.suffix}")
                    shutil.move(str(path), dest)
                    media.thumb(dest, thumb, dur)
                    self.progress["kept"] += 1
                    self.log("keep", "good", score=v["score"], why=v["why"])
                else:
                    self.tally["nope"] += 1
                    if self.cfg["keep_rejects"]:
                        nope = cave / "_nope"
                        nope.mkdir(exist_ok=True)
                        dest = nope / (f"{v['score']:02d}_{_safe(meta['title'])}_"
                                       f"{_safe(cand['id'], 20)}{path.suffix}")
                        shutil.move(str(path), dest)
                    self.log("nope", score=v["score"], why=v["why"])
                vid = self.db.add(key=cand["key"], url=cand["url"], title=meta["title"],
                                  uploader=meta["uploader"], duration=dur,
                                  status="kept" if keep else "nope", score=v["score"],
                                  vibe=v["vibe"], why=v["why"], path=str(dest) if dest else None,
                                  thumb=str(thumb) if keep and thumb.exists() else None,
                                  query=cand["query"], brain=brain.label)
                self.db.add_hashes(vid, item["hashes"])
                if self.progress["kept"] >= run.count:
                    run.enough = True
                    run.halt.set()
        finally:
            run.done_one()
            shutil.rmtree(item["work"], ignore_errors=True)

    # ----------------------------------------------------------- results --
    def _ok(self, run, cand):
        with run.lock:
            self.fails_in_row = 0
            self.src_fails[cand["src"]] = 0

    def _fail_item(self, run, item, err, kind):
        try:
            self._fail(run, item["cand"], err, kind)
        finally:
            run.done_one()
            shutil.rmtree(item["work"], ignore_errors=True)

    def _fail(self, run, cand, err, kind):
        with run.lock:
            if run.over():
                return
            err = net.nice(err) if "curl" in str(err) else str(err)
            self.tally["fail"] += 1
            self.last_err = err
            self.log(kind, "bad", err=err[:220])
            self.db.add(key=cand["key"], url=cand["url"], title=cand["title"], status="fail",
                        query=cand["query"])
            src = cand["src"]
            self.src_fails[src] = self.src_fails.get(src, 0) + 1
            if self.src_fails[src] >= 4 and src != "youtube" and \
                    len(set(self.sources) - self.src_off) > 1 and src not in self.src_off:
                # one site keeps breaking (e.g. Instagram wants login): skip it, keep the rest
                self.src_off.add(src)
                self.log("src_off", "warn", site={"tiktok": "TikTok", "instagram": "Instagram"}.get(
                    src, src.capitalize()), err=err[:140])
                self.fails_in_row = 0
                return
            self.fails_in_row += 1
            if self.fails_in_row >= 8:
                self._give_up(run, kind + "_many", err)

    def _give_up(self, run, key, err):
        with run.lock:
            if run.over():
                return
            self.log(key, "bad", err=str(err)[:200])
            run.end = key
            run.halt.set()

    def _summary(self, run):
        """Say what happened, and the most likely fix when not enough rot was found."""
        t = self.tally
        threshold = self.cfg["threshold"]
        self.log("summary", n=t["found"], kept=t["kept"], nope=t["nope"], dupe=t["dupe"],
                 long=t["long"], seen=t["seen"], fail=t["fail"], ai=t["ai"])
        if t["kept"]:
            self.log("sites_got", tt=t.get("site_tiktok", 0), ig=t.get("site_instagram", 0),
                     yt=t.get("site_youtube", 0))
        if self.progress["kept"] >= self.progress["target"] or self.stop.is_set() or run.end:
            return                           # (gave up: the reason was already said)
        tt_ig = t.get("site_tiktok", 0) + t.get("site_instagram", 0)
        if self.cfg["source_mode"] == "only" and tt_ig == 0 and not t["ai"]:
            self.log("hint_ttig", "warn")
        elif t["found"] == 0:
            self.log("no_results", "warn")
        elif t["ai"] >= max(t["found"] // 3, 1):
            self.log("hint_ai", "warn", n=t["ai"])
        elif t["nope"] and t["best"] < threshold:
            self.log("hint_low", "warn", best=max(t["best"], 0), th=threshold)
        elif t["seen"] >= max(t["found"] // 2, 1):
            self.log("hint_seen", "warn")
        elif t["long"] >= max(t["found"] // 3, 1):
            self.log("hint_long", "warn")
        elif t["fail"] >= max(t["found"] // 3, 1):
            self.log("hint_fail", "warn", err=self.last_err[:160])
