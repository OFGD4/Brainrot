"""Ear mode: whisper.cpp (whisper-cli) on the CPU. Tiny download, works on every PC.
The program and the model are downloaded the first time ear mode is used (goon/tools.py)."""
import os
import subprocess
import time
from pathlib import Path

from . import media, tools

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def ready(size) -> bool:
    return bool(tools.path("whisper")) and tools.model_path(size).exists()


def prepare(size, log=None):
    """Download whisper-cli + model if needed (logs 'growing ears' the first time)."""
    if not ready(size) and log:
        log("ear_loading", size=size)
    cli = tools.ensure("whisper")
    model = tools.ensure_model(size)
    return cli, model


def listen(video, work: Path, size="base", log=None, stop=None) -> str:
    cli, model = prepare(size, log)
    wav = Path(work) / "ear.wav"
    if not media.audio_wav(video, wav, max_secs=60 if media.CHILL else 120):
        return ""
    out = Path(work) / "ear"
    out.with_suffix(".txt").unlink(missing_ok=True)
    cores = os.cpu_count() or 2
    threads = max(1, min(4, cores // 2)) if media.CHILL else max(1, min(8, cores - 1))
    cmd = [cli, "-m", model, "-f", str(wav), "-l", "auto", "-t", str(threads),
           "-nt", "-np", "-otxt", "-of", str(out)]
    if media.CHILL:
        cmd += ["-bs", "1", "-bo", "1"]   # greedy decoding: ~3-5x less work than beam search
    # Popen + poll so STOP can kill it (a long clip on a slow CPU can take a while)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         creationflags=media.flags(), cwd=str(Path(cli).parent))
    t0 = time.time()
    while p.poll() is None:
        if (stop is not None and stop.is_set()) or time.time() - t0 > 600:
            p.kill()
            p.wait()
            return ""
        time.sleep(0.2)
    out_s, err_s = p.communicate()
    r = subprocess.CompletedProcess(cmd, p.returncode, out_s, err_s)
    txt = out.with_suffix(".txt")
    if txt.exists():
        text = txt.read_text("utf-8", errors="ignore")
    else:
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "whisper-cli failed").strip()[-200:])
        text = r.stdout
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return text[:1500]
