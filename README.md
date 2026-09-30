# BRAINROT GOON MACHINE 9000

helo me cum brain rot vidas me give here.

Finds short videos → downloads → AI looks + listens → keeps the rot in da goon cave, yeets the rest. Free: no paid APIs.
**No AI slop**: AI-made videos and AI accounts never make it into the cave (see below).

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
Each line of the fight stays ~5 seconds, weapons fly slowly so you can see them. Buttons: **skip talk ▶** (skip only the
current line, one at a time; also Enter / → key) and **skip fight ⏭** (skip the whole fight; also Esc).

## No AI slop 🚫🤖
Memes, brainrot and weird edits made by people only. Every video goes through 4 checks:
1. **Before download** (instant): AI hashtags/words (#ai #aigenerated "made with ai"...), AI tools (Sora, Veo, Kling,
   Hailuo, Runway, Pika, Midjourney, Grok Imagine...), AI trends (AI babies, fruit soap operas, bigfoot vlogs...),
   all **Italian brainrot** characters (Tralalero, Tung Tung Sahur, Ballerina Cappuccina... they are AI-made),
   AI-sounding accounts (`brainrot.ai`, `ai_memes`, `aivideos`...) and TikTok's / Instagram's own "AI-generated" label.
2. **Ear mode**: if the video *says* AI stuff (e.g. "tung tung tung sahur"), it's out.
3. **The AI judge** looks at the frames and gives an "ai" score (plastic skin, morphing, warped hands, AI watermarks).
   ai 5/10 or more = score 0 = yeeted.
4. **AI accounts get blocked forever**: 2 AI videos from one account (or 1 with the site's AI label, or an AI name)
   and nothing from it is ever opened again. Re-uploads of a rejected AI video are caught by the copy check.
- YouTube searches leave out AI videos too (`-ai -sora -veo -kling`).
- The search mix for "brainrot" has no AI topics. The top bar shows **🚫🤖 AI yeeted: N**.
- Typing an AI topic (e.g. "italian brainrot") works, but almost everything gets yeeted, so the app says so.

## Searching (YouTube + TikTok + Instagram)
Type anything. A broad word like **brainrot** mixes lots of kinds of weird vids (skibidi, sigma edits, cursed videos,
Ohio memes, 67, split-screen, goofy ahh, meme edits, shitposts, ...) and digs deeper until it has enough.
All searches run side by side: a slow site never holds up the others.
- **YouTube**: real search, short videos only (under 4 min). No login needed.
- **TikTok search**, in this order (the next one only runs if the one before found nothing / is blocked):
  1. **tikwm.com** (free public TikTok search, no login). Its free limit is per internet connection: too many
     searches close together and it answers **403** for a while. So the app calls it once every 2.5s for everything,
     never retries a 403 right away, and lets it rest (20s → 45s → 90s → 180s).
  2. **TikTok's own search** (the call tiktok.com makes). Works best with your TikTok login in cookies.txt.
  3. Web search (DuckDuckGo, Bing backup) for TikTok videos + creators.
- **TikTok downloads**: yt-dlp (as Chrome) first, so tikwm is only used for searching. tikwm's video link is the backup.
- **TikTok 403 fix**: TikTok, tikwm (Cloudflare) and Instagram block plain Python with "403 Forbidden" by checking
  *how* it connects. The app connects exactly like Chrome (curl_cffi), for its own requests and for yt-dlp.
  If a download fails every way, ME THOUGHTS says which one said what.
- **Instagram**: with your **cookies.txt**, it uses Instagram's own search as you (keyword search + hashtag page,
  videos only). Without cookies it can only web-search for reels, which rarely finds much.
- When a site finds nothing, ME THOUGHTS says why (e.g. "tikwm said 503", "instagram says log in again").
- ME BRAIN > **where me search**: **TikTok + Insta only** (never YouTube) / **TikTok + Insta first**, YouTube only if
  they run out (default) / **mix all**. Every kept video shows its site, and each run ends with "me got: X from TikTok...".
- No guarantee TikTok/Insta always deliver: search engines can block for a while, and Insta needs a login.
- A site that keeps failing gets skipped for that run (with a hint).
- **Why one site works and the other doesn't** — every run ends with a 📊 line per site, e.g.
  `📊 TikTok: 40 found → 10 judged, 20 seen before, 8 AI, 1 copycat, 1 broke → 5 kept` or
  `📊 Instagram: found NOTHING. why: instagram says log in again`. Usual reasons:
  - **TikTok down, Insta fine**: tikwm said 403 (too many searches from your internet, it rests a bit) and TikTok's
    own search needs your TikTok login in cookies.txt; or TikTok downloads kept failing, so TikTok got skipped for that run.
  - **Insta down, TikTok fine**: no cookies.txt (Insta search needs a login), the login expired ("log in again":
    export a fresh cookies.txt), Instagram said "slow down" (429: wait ~10 min), or reel downloads need the login.
  - **Works once, then "nothing new"**: everything it found was "seen before". Instagram search now also pages through
    more results + the hashtag's RECENT reels, so each run gets fresh videos.
  - Instagram calls are spaced 3s apart so your account doesn't get flagged for clicking too fast.

### 💎 Hidden gems (videos with NO caption)
Search only finds videos whose caption / hashtags match your words, so caption-less rot never shows up in a search.
With **💎 hidden gems** on (under the START button, on by default), every time a video is kept the app also digs:
- that **creator's other videos** (TikTok, YouTube channel Shorts, Instagram with cookies.txt)
- other **TikTok videos with the same sound**
The AI judges those by picture + sound only ("no caption" never lowers the score). Kept videos with no real caption get a
**💎 GEM** badge in the cave and `GEM_` in the file name. AI accounts / AI sounds are never dug. Digging is limited per
run (about 2x the number of videos you asked for) so it doesn't go down the rabbit hole forever.

### 📌 Saved captions
Under the START button: **saved captions**, one per line. Every caption there is searched on EVERY run, on top of
whatever you type (you can even leave the words empty). Paste the caption of a video you liked to find its reposts +
similar videos. Comes with one example caption; delete it if you don't want it.

### Login for TikTok / Instagram (cookies.txt)
Chrome locks its cookies on Windows, so use a file instead:
1. Install the free browser extension **"Get cookies.txt LOCALLY"**.
2. Log in to tiktok.com and instagram.com in that browser.
3. Click the extension, export cookies (all sites or those two) -> `cookies.txt`.
4. ME BRAIN > more brain stuff > **or give me cookies.txt** -> pick the file. Got one file per site (e.g.
   `www.tiktok.com_cookies.txt` + `www.instagram.com_cookies.txt`)? Pick both (or one after the other): they get
   **merged**. It shows each site with ✓ = logged in, or "(not logged in)" = visitor cookies only (won't help).
Cookies are only sent to TikTok/Instagram, never YouTube. Treat the file like a password (it logs in as you).

## Brain (all free)
- **Local** → install [Ollama](https://ollama.com/download). App picks the model by VRAM and downloads it on first START:

| VRAM | model | size |
|---|---|---|
| 10GB+ | qwen3-vl:8b-instruct | 6.1GB |
| 5–10GB | qwen3-vl:4b-instruct | 3.3GB |
| 2.5–5GB | qwen3-vl:2b-instruct | 1.9GB |
| no GPU | qwen3-vl:2b on CPU (slow) → use Gemini |

- **Google** → free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (no card). ~10 vids/min, daily cap. Paste it in ME BRAIN (top right button).
- **Tag team (fastest + reliable)** → Google key AND Ollama. **auto** picks this when you have both.
  - Good GPU (or "go easy on me pc" off): both brains judge at the same time.
  - Weak PC: Google judges; the local brain only jumps in when Google says "slow down" or runs out of free
    tries for the day, so the CPU stays calm. Google refuses to look at a video? The local brain takes it.
  - A brain that keeps breaking gets benched; the other one carries on.

### Why it's faster now
- **Pipeline**: while the brain judges video 1, video 2 is already downloading + being checked.
- **1 picture instead of 4**: the 4 frames are glued into one 2x2 grid (~half the pixels for Ollama, ~4x less for Gemini).
- The local brain is loaded while the first videos download (no wait on the first video).
- AI videos are thrown out before downloading, so no time is wasted on them.
- Google pacing adapts: starts fast, slows down by itself if Google complains.

### STOP is instant
Every slow step (searching, downloading, AI thinking, waiting for Google) can be walked away from. STOP ends the
run in well under a second; the local AI is told to stop thinking too. Leftovers finish quietly and never touch the cave.

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
- **"tikwm said 403"** → tikwm's free limit (too many searches from your internet). The app lets it rest and uses
  TikTok's own search meanwhile. Add your **TikTok login to cookies.txt** (log in to tiktok.com before exporting) so
  TikTok's own search works well. Wait a few minutes between big runs.
- **"chrome disguise missing"** → curl_cffi isn't installed: run `build.bat` again (dev: delete `.venv`, run `run.bat`;
  `run.bat` now reinstalls packages by itself whenever requirements.txt changes).
- **Too few videos / lots of AI** → the last ME THOUGHTS line says how many were AI. Use non-AI words (skibidi, sigma edit, cursed memes, goofy ahh).
- **TikTok / Insta fail** → give it a **cookies.txt** (see above), or cookies from browser → **firefox**. Chrome cookies are locked on Windows.
- **Not enough rot found** → read the last 2 lines in ME THOUGHTS: it says how many were too normal / too long / seen before / broke, and what to change.
- **Need help** → click **copy thoughts** and paste it (also saved in `%LOCALAPPDATA%\BrainrotGoonMachine\thoughts.txt`).
- **Check all parts** → `BrainrotGoonMachine.exe --selftest`
- **Update failed** → message shows in the app. Or grab the Setup from GitHub Releases once.
- AMD GPU: Ollama supports RX 6000/7000+. Older → CPU.

Personal use. Reposting other people's clips = copyright problem.
