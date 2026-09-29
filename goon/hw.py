"""Look at the user's PC and pick a brain that fits."""
import os
import subprocess

import psutil

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# (min VRAM GB, ollama model tag, label)
TIERS = [
    (10.0, "qwen3-vl:8b-instruct", "big brain"),
    (5.0, "qwen3-vl:4b-instruct", "medium brain"),
    (2.5, "qwen3-vl:2b-instruct", "smol brain"),
]
CPU_MODEL = "qwen3-vl:2b-instruct"


def _run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _nvidia():
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        try:
            name, mem = [x.strip() for x in line.rsplit(",", 1)]
            gpus.append({"name": name, "vram_gb": round(float(mem) / 1024, 1), "vendor": "nvidia"})
        except ValueError:
            pass
    return gpus


def _windows_registry():
    """Works for AMD/Intel/NVIDIA. Win32_VideoController caps at 4GB, registry doesn't."""
    ps = (
        "$k='HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\0*';"
        "Get-ItemProperty -Path $k -ErrorAction SilentlyContinue | ForEach-Object {"
        "  $m=$_.'HardwareInformation.qwMemorySize'; if(-not $m){$m=$_.'HardwareInformation.MemorySize'};"
        "  if($_.DriverDesc){ \"$($_.DriverDesc)|$m\" } }"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=12)
    gpus = []
    for line in out.strip().splitlines():
        if "|" not in line:
            continue
        name, mem = line.rsplit("|", 1)
        try:
            gb = round(int(mem) / 1024**3, 1)
        except ValueError:
            gb = 0.0
        low = name.lower()
        vendor = "nvidia" if "nvidia" in low else "amd" if ("amd" in low or "radeon" in low) else \
            "intel" if "intel" in low else "other"
        gpus.append({"name": name.strip(), "vram_gb": gb, "vendor": vendor})
    return gpus


def detect() -> dict:
    gpus = _nvidia()
    if os.name == "nt":
        seen = {g["name"] for g in gpus}
        gpus += [g for g in _windows_registry() if g["name"] not in seen]
    # Ignore tiny iGPU carve-outs and virtual adapters
    real = [g for g in gpus if g["vram_gb"] >= 2.0 and g["vendor"] in ("nvidia", "amd", "intel")]
    best = max(real, key=lambda g: g["vram_gb"], default=None)
    ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)
    cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1

    info = {
        "gpu": best["name"] if best else None,
        "vendor": best["vendor"] if best else None,
        "vram_gb": best["vram_gb"] if best else 0.0,
        "ram_gb": ram_gb,
        "cores": cores,
        "all_gpus": gpus,
    }
    info.update(pick(info))
    return info


def pick(info: dict) -> dict:
    vram = info["vram_gb"]
    vendor = info.get("vendor")
    # Intel Arc isn't accelerated by stock Ollama; treat as CPU
    usable_vram = vram if vendor in ("nvidia", "amd") else 0.0
    cores = info.get("cores") or 1
    ear = "base" if cores >= 6 else "tiny"   # whisper.cpp runs on CPU; "small" only if picked by hand
    for need, model, label in TIERS:
        if usable_vram >= need:
            return {"model": model, "tier": label, "speed": "fast",
                    "recommend": "ollama", "whisper": ear}
    if info["ram_gb"] >= 12:
        return {"model": CPU_MODEL, "tier": "cpu brain", "speed": "slow",
                "recommend": "gemini", "whisper": ear}
    return {"model": CPU_MODEL, "tier": "potato", "speed": "very slow",
            "recommend": "gemini", "whisper": "tiny"}


if __name__ == "__main__":
    import json
    print(json.dumps(detect(), indent=2))
