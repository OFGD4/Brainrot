import sqlite3
import threading
import time

import numpy as np

from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS vids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,            -- extractor:id
    url TEXT, title TEXT, uploader TEXT, duration REAL,
    status TEXT,                -- kept | nope | dupe | fail | ai | yeeted
    score INTEGER, vibe TEXT, why TEXT,
    path TEXT, thumb TEXT, dupe_of INTEGER,
    query TEXT, brain TEXT,
    created REAL
);
CREATE TABLE IF NOT EXISTS hashes (
    vid INTEGER, h INTEGER
);
CREATE INDEX IF NOT EXISTS hashes_vid ON hashes(vid);
CREATE TABLE IF NOT EXISTS ai_users (   -- accounts caught posting AI stuff
    who TEXT PRIMARY KEY,       -- site:name (lowercase)
    strikes INTEGER, why TEXT, created REAL
);
"""
AI_BLOCK_AT = 2   # strikes: sure-thing AI (tags/labels/names) = 2 at once, AI judge "maybe" = 1


class DB:
    def __init__(self):
        self.path = data_dir() / "goon.db"
        self.lock = threading.Lock()
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()
        self._hash_cache = None  # (vid ids array, hashes array)
        self._blocked = {r[0] for r in self.con.execute(
            "SELECT who FROM ai_users WHERE strikes >= ?", (AI_BLOCK_AT,))}

    # ------------------------------------------------------ AI accounts --
    @staticmethod
    def _who(site, user):
        return f"{(site or '').lower()}:{(user or '').strip().lstrip('@').lower()}"

    def ai_blocked(self, site, user) -> bool:
        return bool(user) and self._who(site, user) in self._blocked

    def ai_strike(self, site, user, n=1, why="") -> bool:
        """Count AI videos per account. Returns True when the account just got blocked."""
        if not user:
            return False
        who = self._who(site, user)
        with self.lock:
            r = self.con.execute("SELECT strikes FROM ai_users WHERE who=?", (who,)).fetchone()
            strikes = (r[0] if r else 0) + n
            self.con.execute("INSERT OR REPLACE INTO ai_users (who, strikes, why, created) "
                             "VALUES (?, ?, ?, ?)", (who, strikes, why[:120], time.time()))
            self.con.commit()
        if strikes >= AI_BLOCK_AT and who not in self._blocked:
            self._blocked.add(who)
            return True
        return False

    def ai_blocked_count(self) -> int:
        return len(self._blocked)

    def seen(self, key: str) -> bool:
        with self.lock:
            r = self.con.execute("SELECT status FROM vids WHERE key=?", (key,)).fetchone()
        # failed downloads may be retried later
        return bool(r) and r["status"] != "fail"

    def add(self, **row) -> int:
        row.setdefault("created", time.time())
        cols = ",".join(row)
        qs = ",".join("?" * len(row))
        with self.lock:
            cur = self.con.execute(
                f"INSERT OR REPLACE INTO vids ({cols}) VALUES ({qs})", tuple(row.values()))
            self.con.commit()
            return cur.lastrowid

    def add_hashes(self, vid: int, hashes: np.ndarray):
        with self.lock:
            self.con.executemany("INSERT INTO hashes (vid, h) VALUES (?, ?)",
                                 [(vid, int(h)) for h in hashes.astype(np.uint64).view(np.int64)])
            self.con.commit()
            self._hash_cache = None

    def _all_hashes(self):
        if self._hash_cache is None:
            with self.lock:
                rows = self.con.execute(
                    "SELECT h.vid, h.h FROM hashes h JOIN vids v ON v.id=h.vid "
                    "WHERE v.status IN ('kept','nope','yeeted')").fetchall()
            vids = np.array([r[0] for r in rows], dtype=np.int64)
            hs = np.array([r[1] for r in rows], dtype=np.int64).view(np.uint64)
            self._hash_cache = (vids, hs)
        return self._hash_cache

    def find_dupe(self, hashes: np.ndarray, max_bits=10, min_frac=0.6):
        """Return id of an earlier video that shares most frames with this one."""
        vids, hs = self._all_hashes()
        if len(hs) == 0 or len(hashes) == 0:
            return None
        x = np.bitwise_xor(hashes.astype(np.uint64)[:, None], hs[None, :])
        bits = np.unpackbits(x.view(np.uint8).reshape(x.shape + (8,)), axis=-1).sum(-1)
        close = bits <= max_bits  # [new_frames, all_frames]
        best, best_frac = None, 0.0
        for v in np.unique(vids):
            frac = close[:, vids == v].any(axis=1).mean()
            if frac > best_frac:
                best, best_frac = int(v), frac
        return best if best_frac >= min_frac else None

    def kept(self, sort="new", limit=500):
        order = "score DESC, id DESC" if sort == "score" else "id DESC"
        with self.lock:
            rows = self.con.execute(
                f"SELECT * FROM vids WHERE status='kept' ORDER BY {order} LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get(self, vid: int):
        with self.lock:
            r = self.con.execute("SELECT * FROM vids WHERE id=?", (vid,)).fetchone()
        return dict(r) if r else None

    def set_status(self, vid: int, status: str):
        with self.lock:
            self.con.execute("UPDATE vids SET status=?, path=NULL WHERE id=?", (status, vid))
            self.con.commit()
            self._hash_cache = None

    def stats(self):
        with self.lock:
            rows = self.con.execute("SELECT status, COUNT(*) c FROM vids GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}
