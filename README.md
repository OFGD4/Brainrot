# BRAINROT GOON MACHINE 9000

helo me cum brain rot vidas me give here.

Finds short videos → downloads → AI looks + listens → keeps the rot in da goon cave, yeets the rest. Free: no paid APIs.

## Build the .exe (Windows)
1. Install **Python 3.12** from python.org → tick **"Add python.exe to PATH"**.
2. Double-click **`build.bat`**. First time ~5–10 min.
3. Exe: `dist\BrainrotGoonMachine\BrainrotGoonMachine.exe`
   Share: `dist\BrainrotGoonMachine.zip` (whole folder, not just the exe).

Dev run without building: `run.bat`.
Got [Inno Setup](https://jrsoftware.org/isdl.php)? `build.bat` also makes `dist\BrainrotGoonMachine-Setup.exe`.

## Small app, tools download once
The app is ~35MB to download (~105MB installed). On first launch it downloads its tools (~75MB, once):
ffmpeg, deno and yt-dlp from PyPI, checked against PyPI's sha256. After that:
- **yt-dlp** checks for a new version every day, so broken downloads fix themselves without a new release.
  If a new yt-dlp is broken, the app falls back to its built-in copy and skips that version.
- **deno** re-checks weekly, **ffmpeg** monthly.
- **Ear mode** stuff downloads only when you use it.

## Updates (users never go to GitHub)
First time only:
1. Make a GitHub repo, push this folder (the `.github` folder too).
2. `git tag v1.0.0` → `git push origin v1.0.0`
3. GitHub Actions builds `BrainrotGoonMachine-Setup.exe` → Releases. Users install it once.

Every update after that:
```
git tag v1.0.1
git push origin v1.0.1
```
Every installed copy then shows **UPDATE ME** → downloads Setup → installs silently → reopens as v1.0.1.
Version + repo name come from the tag automatically (`app_info.py` stays `0.0.0` in git).
Downloads are checked against GitHub's sha256. Turn on 2FA on GitHub: whoever controls the repo controls updates.

## Languages (top right button)
- **Niba**: da original caveman-style talk
- **Illsonois**: every word ends with s. Started in Illisnois (see lore in the app)
- 📜 **Ye Olde**: Shakespeare talk

The UI, the log, and the AI's reasons all switch. Edit or add text in `goon/lang.py`.

Each language has a champion (pictures in `web/champs/`): **Niba**, **HelosFromsIllsnois** (Mayor of Illsonois), **Sir Tawawawa Goonsperm the Third**. Champions are shown only as their pictures (no emojis for them).
HelosFromsIllsnois' signature move fires in every war he's in: "Hellos hows ares yous mes gonnas sfucks yous".
Illsonois rule breakers: "as" stays "as", Illinois is written **Illisnois** (no extra s), fuck becomes **sfucks**.
Switching language = the current champion guilt-trips you, then they fight. The new language always wins.

## Searching (YouTube + TikTok + Instagram)
Type anything. A broad word like **brainrot** mixes lots of kinds of weird vids (skibidi, sigma edits, cursed videos,
Ohio memes, 67, split-screen, weird TikToks, Italian brainrot, ...) and digs deeper until it has enough.
- **YouTube**: real search, short videos only (under 4 min). No login needed.
- **TikTok**: yt-dlp has no TikTok search, so the app uses **tikwm.com** (free public TikTok search, no login).
  If tikwm is down: web search (DuckDuckGo, Bing backup) for TikTok videos + creators. If yt-dlp can't download a
  TikTok, it uses tikwm's direct video link instead.
- **Instagram**: with your **cookies.txt**, it uses Instagram's own search as you (keyword search + hashtag page,
  videos only). Without cookies it can only web-search for reels, which rarely finds much.
- When a site finds nothing, ME THOUGHTS says why (e.g. "tikwm said 503", "instagram says log in again").
- ME BRAIN > **where me search**: **TikTok + Insta only** (never YouTube) / **TikTok + Insta first**, YouTube only if
  they run out (default) / **mix all**. Every kept video shows its site, and each run ends with "me got: X from TikTok...".
- No guarantee TikTok/Insta always deliver: search engines can block for a while, and Insta needs a login.
- A site that keeps failing gets skipped for that run (with a hint).

### Login for TikTok / Instagram (cookies.txt)
Chrome locks its cookies on Windows, so use a file instead:
1. Install the free browser extension **"Get cookies.txt LOCALLY"**.
2. Log in to tiktok.com and instagram.com in that browser.
3. Click the extension, export cookies (all sites or those two) -> `cookies.txt`.
4. ME BRAIN > more brain stuff > **or give me cookies.txt** -> pick the file. It shows which sites it found.
Cookies are only sent to TikTok/Instagram, never YouTube. Treat the file like a password (it logs in as you).

## Brain (pick one, both free)
- **Local** → install [Ollama](https://ollama.com/download). App picks the model by VRAM and downloads it on first START:

| VRAM | model | size |
|---|---|---|
| 10GB+ | qwen3-vl:8b-instruct | 6.1GB |
| 5–10GB | qwen3-vl:4b-instruct | 3.3GB |
| 2.5–5GB | qwen3-vl:2b-instruct | 1.9GB |
| no GPU | qwen3-vl:2b on CPU (slow) → use Gemini |

- **Google** → free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no card). ~10 vids/min, daily cap. Paste it in ME BRAIN (top right button).

Ear mode = whisper.cpp on CPU. Downloads on first use: 8MB program + model (tiny 75MB / base 142MB / small 466MB, picked by CPU cores).

## Go easy on me pc (on by default)
ME BRAIN > **go easy on me pc**: everything runs at low priority (PC stays smooth), ffmpeg max 2 threads + GPU video
decoding when possible, ear mode uses fast decoding / half the cores / first 60s only, and a local AI on CPU gets half
the cores. Turn it off for max speed. Ear model auto-pick never uses the heavy "small" (pick it by hand if you want).

## Where stuff goes
- Kept vids: `Videos\GoonCave` (change in ME BRAIN)
- DB/config/logs: `%LOCALAPPDATA%\BrainrotGoonMachine`
- Downloaded tools (ffmpeg, deno, yt-dlp, whisper): `%LOCALAPPDATA%\BrainrotGoonMachine\tools`

## When it breaks
- **Downloads fail** → the app updates yt-dlp by itself once a day. Restart the app to pull it sooner.
- **TikTok / Insta fail** → give it a **cookies.txt** (see above), or cookies from browser → **firefox**. Chrome cookies are locked on Windows.
- **Not enough rot found** → read the last 2 lines in ME THOUGHTS: it says how many were too normal / too long / seen before / broke, and what to change.
- **Need help** → click **copy thoughts** and paste it (also saved in `%LOCALAPPDATA%\BrainrotGoonMachine\thoughts.txt`).
- **Check all parts** → `BrainrotGoonMachine.exe --selftest`
- **Update failed** → message shows in the app. Or grab the Setup from GitHub Releases once.
- AMD GPU: Ollama supports RX 6000/7000+. Older → CPU.

Personal use. Reposting other people's clips = copyright problem.
