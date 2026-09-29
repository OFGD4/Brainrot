"""ffmpeg helpers: duration, frames for the AI, perceptual hashes, audio for whisper."""
import os
import re
import subprocess
from pathlib import Path

import numpy as np

from .paths import ffmpeg_exe

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0
CHILL = True   # "go easy on me pc": set by the engine from the config


def flags():
    """Windows process flags: no console window, and low priority in chill mode."""
    return NO_WINDOW | (BELOW_NORMAL if CHILL else 0)


def _ff(args, timeout=120, capture=True, hw=False):
    """Run ffmpeg. Chill mode: max 2 threads; hw=True lets the GPU decode video if it can."""
    pre = []
    if CHILL:
        pre += ["-threads", "2", "-filter_threads", "1"]
        if hw:
            pre += ["-hwaccel", "auto"]
    if pre and "-i" in args:
        i = args.index("-i")
        args = args[:i] + pre + args[i:]
    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                          capture_output=capture, timeout=timeout, creationflags=flags())


def _ff_video(args, timeout=120, ok=lambda r: r.returncode == 0):
    """Video decode: try GPU decoding first (chill mode), fall back to plain CPU if it fails."""
    r = _ff(args, timeout, hw=True)
    if CHILL and not ok(r):
        r = _ff(args, timeout, hw=False)
    return r


def duration(path) -> float:
    r = _ff(["-i", str(path)], timeout=30)
    m = re.search(rb"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def has_audio(path) -> bool:
    r = _ff(["-i", str(path)], timeout=30)
    return b"Audio:" in r.stderr


def grab_frames(path, out_dir, n=4, width=512, dur=None) -> list[Path]:
    """n JPEG frames spread across the clip, for the vision model."""
    dur = dur or duration(path) or 10.0
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        out = out_dir / f"f{i}.jpg"
        _ff_video(["-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-q:v", "4", str(out)], timeout=60)
        if out.exists() and out.stat().st_size > 0:
            frames.append(out)
    return frames


def frame_sheet(frames, out) -> Path | None:
    """Glue the frames into ONE 2x2 picture. The AI reads 1 picture much faster than 4
    (about half the pixels, a quarter of the Gemini image cost), and still sees the whole clip."""
    frames = [Path(f) for f in frames if Path(f).exists()]
    if len(frames) < 2:
        return frames[0] if frames else None
    frames = frames[:4]
    args = ["-y"]
    for f in frames:
        args += ["-i", str(f)]
    if len(frames) == 4:
        vf = "xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0"
    else:
        vf = f"hstack=inputs={len(frames)}"
    r = _ff(args + ["-filter_complex", vf, "-frames:v", "1", "-q:v", "4", str(out)], timeout=60)
    if r.returncode == 0 and Path(out).exists() and Path(out).stat().st_size > 0:
        return Path(out)
    return None


def frame_hashes(path, every=1.0, max_frames=180) -> np.ndarray:
    """64-bit dHash per sampled frame. ffmpeg does the resize, numpy does the bits."""
    r = _ff_video(["-i", str(path), "-an", "-vf", f"fps=1/{every},scale=9:8:flags=area,format=gray",
             "-frames:v", str(max_frames), "-f", "rawvideo", "-pix_fmt", "gray", "-"], timeout=180,
                  ok=lambda r: r.returncode == 0 and len(r.stdout) >= 72)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(buf) // 72
    if n == 0:
        return np.zeros(0, dtype=np.uint64)
    px = buf[: n * 72].reshape(n, 8, 9).astype(np.int16)
    bits = (px[:, :, 1:] > px[:, :, :-1]).reshape(n, 64)
    # drop near-flat frames (black/white fades) — they match everything
    flat = px.std(axis=(1, 2)) < 3
    bits = bits[~flat]
    if len(bits) == 0:
        return np.zeros(0, dtype=np.uint64)
    weights = (np.uint64(1) << np.arange(64, dtype=np.uint64))
    return (bits.astype(np.uint64) * weights).sum(axis=1, dtype=np.uint64)


def audio_wav(path, out, max_secs=120) -> bool:
    """16 kHz mono wav for whisper.cpp. Returns False if there is no real sound."""
    Path(out).unlink(missing_ok=True)
    r = _ff(["-y", "-i", str(path), "-t", str(max_secs), "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(out)], timeout=120)
    if r.returncode != 0:
        return False
    try:
        pcm = np.frombuffer(Path(out).read_bytes()[44:], dtype=np.int16)
    except OSError:
        return False
    return len(pcm) > 8000 and int(np.abs(pcm).max()) > 60


def thumb(path, out, dur=None):
    dur = dur or duration(path) or 2.0
    _ff_video(["-y", "-ss", f"{min(dur * 0.3, 3.0):.2f}", "-i", str(path), "-frames:v", "1",
         "-vf", "scale=360:-2", "-q:v", "5", str(out)], timeout=60)
    return Path(out).exists()
