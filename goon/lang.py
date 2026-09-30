"""All da languages: UI text, log words, AI reply style, and lore.

3 languages:
  caveman   - "Niba": da original weird english (code stays "caveman")
  illsonois - every word ends with s. write NORMAL english in ILLSONOIS_* below,
              da machine adds da s. wrap stuff in [[...]] to keep it as-is.
  olde      - ye olde shakespeare english
"""
import random
import re

LANGS = [
    {"code": "caveman", "name": "Niba", "emoji": "", "sample": "me goon. me happy."},
    {"code": "illsonois", "name": "Illsonois", "emoji": "", "sample": "mes goons. mes happys."},
    {"code": "olde", "name": "Ye Olde", "emoji": "📜", "sample": "I goon, and I am merry."},
]
CODES = [l["code"] for l in LANGS]
DEFAULT = "caveman"

# ------------------------------------------------------------ illsonois ----
# Da one rule: add an s to da end of every word. Even words dat already end
# in s (this -> thiss). Exceptions: "as" (legal reasons) and da name itself.
ILLSONOIS_EXEMPT = {"as", "illsonois", "illisnois"}
# Rule breakers: the state is spelled Illisnois (no extra s); fuck gets an s on BOTH ends.
ILLSONOIS_SWAP = {"illinois": "Illisnois"}
_TOKEN = re.compile(r"\[\[.*?\]\]|\{[^}]*\}|<[^>]*>|&\w+;|https?://\S+|[A-Za-z][A-Za-z']*")


def illsonoisify(text: str) -> str:
    def rep(m):
        w = m.group(0)
        if w[0] in "[{<&" or w.startswith("http"):
            return w
        low = w.lower()
        if low in ILLSONOIS_SWAP:
            out = ILLSONOIS_SWAP[low]
            return out.upper() if w.isupper() else out
        if low in ILLSONOIS_EXEMPT:
            return w
        if low.startswith("fuck"):              # fuck -> sfucks
            s_ = "S" if w.isupper() else "s"
            return s_ + w + s_
        core = w.rstrip("'")
        tail = w[len(core):]
        s = "S" if len(core) > 1 and core.isupper() else "s"
        return core + s + tail
    return _TOKEN.sub(rep, text)


def _unprotect(text: str) -> str:
    return re.sub(r"\[\[(.*?)\]\]", r"\1", text)


def _finish(lang: str, text: str) -> str:
    if lang == "illsonois":
        text = illsonoisify(text)
    return _unprotect(text)


# ================================================================== UI ====
# keys ending in _html may contain markup; everything else is plain text.

UI_CAVEMAN = {
    "doc_title": "Brainrot Goon Machine 9000",
    "title_main": "BRAINROT GOON MACHINE",
    "title_num": "9000",
    "hello": "helo me cum brain rot vidas me give here",
    "chip_cave": "cave: {n} rot",
    "chip_seen": "seen: {n}",
    "chip_brain": "brain: {b}",
    "brain_btn": "ME BRAIN",
    "lang_h": "ME TALK HOW",
    "lang_switched": "me talk {lang} now",

    "hunt_h": "WAT ROT U WANT",
    "query_label": "rot words (comma for many)",
    "query_ph": "brainrot, skibidi, sigma edit, cursed memes",
    "links_toggle": "or giv me da links",
    "links_help": "yt channel/shorts, tiktok, reels, playlist. one per line",
    "count_label": "how many rot vidas me get",
    "go": "START GOONING",
    "stop": "STOP GOON",
    "prog_count": "{k} / {n} rot",
    "step_idle": "me sleep. zzz",
    "step_searching": "me search...",
    "step_downloading": "me yoink vida...",
    "step_dupes": "me check if copycat...",
    "step_looking": "me look wit ai eyes...",
    "step_listening": "me listen wit ear...",
    "step_judging": "me judge da rot...",
    "step_pull": "me download brain...",
    "step_wake": "me wake brain...",

    "brain_h": "ME BRAIN",
    "pill_checking": "checking...",
    "pill_ready": "brain ready",
    "pill_no_model": "brain not downloaded",
    "pill_no_ollama": "no local brain",
    "pill_no_key": "need google key",
    "pill_bad_key": "key no good",
    "pill_bad_model": "wrong model name",
    "pill_confused": "brain confused",
    "alert_no_model_html": "ollama is here but brain <b>{model}</b> not downloaded. me download it when u start, or click \"download brain\" now.",
    "alert_ollama_sleep": "ollama installed but sleeping. me try wake it when u start.",
    "alert_no_ollama_html": "u no hav ollama. get it free: {link} then come back. or use google gemini brain.",
    "alert_no_key_html": "gemini brain need free key. get at {link} (no card), paste below, SAVE BRAIN.",
    "alert_bad_key": "google no like ur key: {err}",
    "alert_bad_model_html": "google no know <b>{model}</b>. try [[gemini-3.5-flash-lite]]",
    "banner_fix": "fix in ME BRAIN",
    "hw_looking": "me look at ur pc...",
    "hw_line_html": "ur pc hav: {gpu} · {ram}GB ram · {cores} cores",
    "hw_pick_html": "me pick: <b>{model}</b> ({tier}, {speed})",
    "hw_nogpu": "no real gpu",
    "hw_tip": "ur pc kinda weak for local brain. google gemini brain fastr (free key).",
    "tier_big brain": "big brain", "tier_medium brain": "medium brain", "tier_smol brain": "smol brain",
    "tier_cpu brain": "cpu brain", "tier_potato": "potato",
    "speed_fast": "fast", "speed_slow": "slow", "speed_very slow": "very slow",
    "place_legend": "brain place",
    "place_auto": "auto (me pick)",
    "place_ollama": "local (ur pc, free)",
    "place_gemini": "google gemini (free key)",
    "ollama_model_label": "local brain model",
    "ollama_model_small": "(empty = me pick for ur pc)",
    "gemini_key_label": "google key",
    "gemini_key_small_html": "free at {link}, no card",
    "key_ph": "paste [[AIza...]] key",
    "key_saved_ph": "key saved {hint} (paste new to change)",
    "forget": "forget",
    "gemini_model_label": "google brain model",
    "th_label_html": "how rot is rot enuf: <b>{v}</b>/10",
    "more_toggle": "more brain stuff",
    "max_secs_label": "max vida long (secs)",
    "cookies_label": "cookies from browser",
    "cookies_small": "(only tiktok/insta need. firefox best, chrome often broken)",
    "cookies_none": "none",
    "ear_label": "ear mode (me listen wit whisper)",
    "ear_size": "ear size",
    "ear_auto": "auto", "ear_tiny": "tiny (fast)", "ear_base": "base", "ear_small": "small (smart, slow)",
    "taste_label": "wat rot u like most",
    "taste_small": "(tell brain ur taste)",
    "taste_ph": "loud bass boosted edits, cursed cat memes, no reddit stories",
    "cave_dir_label": "goon cave folder",
    "keep_rejects": "keep normal vidas too (in [[_nope]] folder)",
    "pull_btn": "download brain",
    "save_btn": "SAVE BRAIN",
    "close": "close",

    "thoughts_h": "ME THOUGHTS",
    "clear_log": "forget thoughts",
    "log_more": "show all",
    "log_less": "show less",

    "cave_h": "DA GOON CAVE",
    "sort_new": "newest rot",
    "sort_score": "most rot",
    "doom": "DOOMSCROLL",
    "open_folder": "open folder",
    "empty": "cave empty. no rot yet. sad.",
    "lvl": "ROT {s}/10",
    "untitled": "untitled rot",
    "show_title": "show in folder",
    "src_title": "open source",
    "yeet": "yeet",
    "doom_hint": "scroll or ↑ ↓ to goon more. esc to escape",

    "msg_saved": "brain saved. me remember",
    "msg_stopping": "telling me to stop...",
    "msg_no_input": "u no tell me wat rot. type words or links first",
    "msg_already": "me already goonin. wait",
    "msg_yeeted": "yeeted: {title}",
    "msg_key_forgot": "me forget google key",
    "msg_no_doom": "no rot to doomscroll. go goon first",
    "msg_boot_crash": "me crash on boot: {err}",
}

# Normal english. Da machine turns it into Illsonois (adds da s).
UI_ILLSONOIS_BASE = {
    "doc_title": "Brainrot Goon Machine 9000",
    "title_main": "BRAINROT GOON MACHINE",
    "title_num": "9000",
    "hello": "helo me cum brain rot vidas me give here",
    "chip_cave": "cave: {n} rot",
    "chip_seen": "seen: {n}",
    "chip_brain": "brain: {b}",
    "brain_btn": "MY BRAIN",
    "lang_h": "HOW DO I TALK",
    "lang_switched": "I talk {lang} now. ope",

    "hunt_h": "WHAT ROT DO YOU WANT",
    "query_label": "rot words (comma for many)",
    "query_ph": "[[brainrot, skibidi, sigma edit, cursed memes]]",
    "links_toggle": "or give me the links",
    "links_help": "yt channel or shorts, tiktok, reels, playlist. one per line",
    "count_label": "how many rot videos do I get",
    "go": "START GOONING",
    "stop": "STOP GOON",
    "prog_count": "{k} of {n} rot",
    "step_idle": "I sleep. zzz",
    "step_searching": "I search...",
    "step_downloading": "I yoink the video...",
    "step_dupes": "I check for copycat...",
    "step_looking": "I look with ai eyes...",
    "step_listening": "I listen with ear...",
    "step_judging": "I judge the rot...",
    "step_pull": "I download the brain...",
    "step_wake": "I wake the brain...",

    "brain_h": "MY BRAIN",
    "pill_checking": "checking...",
    "pill_ready": "brain ready",
    "pill_no_model": "brain not downloaded",
    "pill_no_ollama": "no local brain",
    "pill_no_key": "need google key",
    "pill_bad_key": "key no good",
    "pill_bad_model": "wrong model name",
    "pill_confused": "brain confused",
    "alert_no_model_html": "ollama is here but the brain <b>{model}</b> is not downloaded. I download it when you start, or click \"download brain\" now.",
    "alert_ollama_sleep": "ollama is installed but sleeping. I try to wake it when you start.",
    "alert_no_ollama_html": "you have no ollama. get it free: {link} then come back. or use the google gemini brain.",
    "alert_no_key_html": "the gemini brain needs a free key. get it at {link} (no card), paste it below, SAVE BRAIN.",
    "alert_bad_key": "google does not like your key: {err}",
    "alert_bad_model_html": "google does not know <b>{model}</b>. try [[gemini-3.5-flash-lite]]",
    "banner_fix": "fix in MY BRAIN",
    "hw_looking": "I look at your pc...",
    "hw_line_html": "your pc has: {gpu} · {ram}GB ram · {cores} cores",
    "hw_pick_html": "I pick: <b>{model}</b> ({tier}, {speed})",
    "hw_nogpu": "no real gpu",
    "hw_tip": "your pc is kind of weak for a local brain. the google gemini brain is faster (free key).",
    "tier_big brain": "big brain", "tier_medium brain": "medium brain", "tier_smol brain": "small brain",
    "tier_cpu brain": "cpu brain", "tier_potato": "potato",
    "speed_fast": "fast", "speed_slow": "slow", "speed_very slow": "very slow",
    "place_legend": "brain place",
    "place_auto": "auto (I pick)",
    "place_ollama": "local (your pc, free)",
    "place_gemini": "google gemini (free key)",
    "ollama_model_label": "local brain model",
    "ollama_model_small": "(empty = I pick for your pc)",
    "gemini_key_label": "google key",
    "gemini_key_small_html": "free at {link}, no card",
    "key_ph": "paste [[AIza...]] key",
    "key_saved_ph": "key saved {hint} (paste new to change)",
    "forget": "forget",
    "gemini_model_label": "google brain model",
    "th_label_html": "how rot is rot enough: <b>{v}</b>/10",
    "more_toggle": "more brain stuff",
    "max_secs_label": "max video long (seconds)",
    "cookies_label": "cookies from browser",
    "cookies_small": "(only tiktok and insta need it. firefox works best, chrome is often broken)",
    "cookies_none": "none",
    "ear_label": "ear mode (I listen with whisper)",
    "ear_size": "ear size",
    "ear_auto": "auto", "ear_tiny": "tiny (fast)", "ear_base": "base", "ear_small": "small (smart, slow)",
    "taste_label": "what rot do you like most",
    "taste_small": "(tell the brain your taste)",
    "taste_ph": "loud bass boosted edits, cursed cat memes, no reddit stories",
    "cave_dir_label": "goon cave folder",
    "keep_rejects": "keep normal videos too (in the [[_nope]] folder)",
    "pull_btn": "download brain",
    "save_btn": "SAVE BRAIN",
    "close": "close",

    "thoughts_h": "MY THOUGHTS",
    "clear_log": "forget thoughts",
    "log_more": "show all",
    "log_less": "show less",

    "cave_h": "THE GOON CAVE",
    "sort_new": "newest rot",
    "sort_score": "most rot",
    "doom": "DOOMSCROLL",
    "open_folder": "open folder",
    "empty": "cave empty. no rot yet. sad. ope.",
    "lvl": "ROT {s}/10",
    "untitled": "untitled rot",
    "show_title": "show in folder",
    "src_title": "open source",
    "yeet": "yeet",
    "doom_hint": "scroll or ↑ ↓ to goon more. esc to escape",

    "msg_saved": "brain saved. I remember",
    "msg_stopping": "telling me to stop...",
    "msg_no_input": "you did not tell me what rot. type words or links first",
    "msg_already": "I am already gooning. wait",
    "msg_yeeted": "yeeted: {title}",
    "msg_key_forgot": "I forget the google key",
    "msg_no_doom": "no rot to doomscroll. go goon first",
    "msg_boot_crash": "I crash on boot: {err}",
}

UI_OLDE = {
    "doc_title": "Ye Olde Brainrot Goon Engine 9000",
    "title_main": "YE OLDE BRAINROT GOON ENGINE",
    "title_num": "9000",
    "hello": "Hark! I come bearing brainrot videos, and here I bestow them upon thee.",
    "chip_cave": "cavern: {n} rot",
    "chip_seen": "beheld: {n}",
    "chip_brain": "mind: {b}",
    "brain_btn": "MINE MIND",
    "lang_h": "WHAT TONGUE SHALL I SPEAK",
    "lang_switched": "Henceforth I speak {lang}.",

    "hunt_h": "WHAT ROT SEEKEST THOU",
    "query_label": "words of rot (parted by commas)",
    "query_ph": "brainrot, skibidi, sigma edit, cursed memes",
    "links_toggle": "or bestow upon me thy links",
    "links_help": "yt channels or shorts, tiktok, reels, playlists. one upon each line",
    "count_label": "how many rot videos shall I fetch",
    "go": "BEGIN THE GOONING",
    "stop": "CEASE THY GOON",
    "prog_count": "{k} of {n} rot",
    "step_idle": "I slumber. zzz",
    "step_searching": "I search the realm...",
    "step_downloading": "I seize the video...",
    "step_dupes": "I seek out forgeries...",
    "step_looking": "I gaze with mine AI eyes...",
    "step_listening": "I hearken with mine ear...",
    "step_judging": "I pass judgement upon the rot...",
    "step_pull": "I summon a mind...",
    "step_wake": "I rouse the mind...",

    "brain_h": "MINE MIND",
    "pill_checking": "pondering...",
    "pill_ready": "the mind is ready",
    "pill_no_model": "mind not yet fetched",
    "pill_no_ollama": "no local mind",
    "pill_no_key": "google key required",
    "pill_bad_key": "the key is false",
    "pill_bad_model": "no such model",
    "pill_confused": "the mind is confounded",
    "alert_no_model_html": "Ollama dwelleth here, yet the mind <b>{model}</b> hath not been fetched. I shall fetch it when thou beginnest, or press \"fetch mind\" now.",
    "alert_ollama_sleep": "Ollama is installed but slumbereth. I shall rouse it when thou beginnest.",
    "alert_no_ollama_html": "Thou hast no Ollama. Procure it freely at {link}, then return. Or use the google gemini mind.",
    "alert_no_key_html": "The gemini mind requireth a free key. Obtain one at {link} (no coin needed), place it below, and SAVE MINE MIND.",
    "alert_bad_key": "Google liketh not thy key: {err}",
    "alert_bad_model_html": "Google knoweth not <b>{model}</b>. Try [[gemini-3.5-flash-lite]]",
    "banner_fix": "mend it in MINE MIND",
    "hw_looking": "I survey thy machine...",
    "hw_line_html": "Thy machine possesseth: {gpu} · {ram}GB of memory · {cores} cores",
    "hw_pick_html": "I choose: <b>{model}</b> ({tier}, {speed})",
    "hw_nogpu": "no true graphics card",
    "hw_tip": "Thy machine is feeble for a local mind. The google gemini mind is swifter (free key).",
    "tier_big brain": "a mighty mind", "tier_medium brain": "a middling mind",
    "tier_smol brain": "a humble mind", "tier_cpu brain": "a mind of the processor",
    "tier_potato": "a mere potato",
    "speed_fast": "swift", "speed_slow": "slow", "speed_very slow": "slow as a snail",
    "place_legend": "where the mind dwelleth",
    "place_auto": "auto (I shall choose)",
    "place_ollama": "local (thy machine, free)",
    "place_gemini": "google gemini (free key)",
    "ollama_model_label": "local mind model",
    "ollama_model_small": "(leave it empty and I shall choose)",
    "gemini_key_label": "google key",
    "gemini_key_small_html": "free at {link}, no coin needed",
    "key_ph": "place thy [[AIza...]] key",
    "key_saved_ph": "key kept {hint} (place a new one to change)",
    "forget": "forget",
    "gemini_model_label": "google mind model",
    "th_label_html": "how rotten is rotten enough: <b>{v}</b>/10",
    "more_toggle": "more matters of the mind",
    "max_secs_label": "longest video (seconds)",
    "cookies_label": "cookies from thy browser",
    "cookies_small": "(only tiktok and insta need them. firefox serveth best, chrome is oft broken)",
    "cookies_none": "none",
    "ear_label": "ear mode (I hearken with whisper)",
    "ear_size": "size of ear",
    "ear_auto": "auto", "ear_tiny": "tiny (swift)", "ear_base": "base", "ear_small": "small (wise, slow)",
    "taste_label": "what rot pleaseth thee most",
    "taste_small": "(tell the mind thy taste)",
    "taste_ph": "loud bass boosted edits, cursed cat memes, no reddit tales",
    "cave_dir_label": "goon cavern folder",
    "keep_rejects": "keep common videos also (in the [[_nope]] folder)",
    "pull_btn": "fetch mind",
    "save_btn": "SAVE MINE MIND",
    "close": "close",

    "thoughts_h": "MINE THOUGHTS",
    "clear_log": "forget thoughts",
    "log_more": "show all",
    "log_less": "show less",

    "cave_h": "YE GOON CAVERN",
    "sort_new": "newest rot",
    "sort_score": "most rotten",
    "doom": "DOOMSCROLL",
    "open_folder": "open folder",
    "empty": "The cavern is empty. No rot yet. Alas.",
    "lvl": "ROT {s}/10",
    "untitled": "untitled rot",
    "show_title": "reveal in folder",
    "src_title": "visit the source",
    "yeet": "banish",
    "doom_hint": "scroll or ↑ ↓ to goon onward. esc to flee",

    "msg_saved": "Thy mind is saved. I shall remember.",
    "msg_stopping": "I am bidden to cease...",
    "msg_no_input": "Thou hast not named thy rot. Write words or links first.",
    "msg_already": "I goon already. Be patient.",
    "msg_yeeted": "banished: {title}",
    "msg_key_forgot": "I have forgotten thy google key.",
    "msg_no_doom": "No rot to doomscroll. Go forth and goon first.",
    "msg_boot_crash": "I perished upon waking: {err}",
}

# ================================================================ LORE ====

LORE = {
    "caveman": {
        "title": "ABOUT NIBA TALK",
        "intro": "niba talk is first language. before words, only rot.",
        "facts": [
            "no grammar. only vibe.",
            "u say \"me\" for everything. me hungry. me goon. me machine.",
            "\"da\" mean \"the\". \"wit\" mean \"with\". \"vida\" mean video. easy.",
            "started when first niba see first brainrot on cave wall. it was rock wit face.",
            "still spoken today in every comment section.",
            "champion is niba. niba look up at u. niba tongue out. niba angry.",
        ],
        "footer": "facts checked by da goon machine",
    },
    "illsonois": {
        "title": "THE ILLSONOIS LANGUAGE",
        "intro": "For your information: this language always end with s.",
        "facts": [
            "It originally started in Illinois, where the wind off Lake Michigan blows so hard it pushes an extra s onto the end of every word.",
            "The rule is simple: every word gets one more s at the end. Even words that already end with s get another one, so this becomes [[thiss]].",
            "The name Illsonois comes from Illinois, but the s got pushed into the middle because the end was already full.",
            "The only exception is the word as, for legal reasons.",
            "Native speakers can be found in Chicago, Peoria, Springfield and one goon machine.",
            "Saying a word without the s is very rude in Illinois. Do not do it at a deep dish pizza place.",
            "The official greeting is ope, which is said when you bump into anything.",
            "Rule breaker: the home state is written Illinois and it never gets another s. Not even one.",
            "Rule breaker: the word fuck gets an s at the front AND the back. Nobody knows why. It is the law.",
            "The champion of the language is [[HelosFromsIllsnois]]. His signature move is: [[Hellos hows ares yous mes gonnas sfucks yous]]",
        ],
        "footer": "Facts certified by the goon machine.",
    },
    "olde": {
        "title": "OF YE OLDE TONGUE",
        "intro": "Hark, good traveller! Thou hast chosen the tongue of bards and knaves.",
        "facts": [
            "It was spoken throughout England in the age of Shakespeare, some four centuries past.",
            "\"Thou\" is he who doth the deed; \"thee\" is he to whom the deed is done; \"thy\" and \"thine\" be what he owneth.",
            "Verbs of the third person do end in -eth: he goeth, she gooneth, it rotteth.",
            "\"Thou\" was spoken unto friends and lowly folk; \"you\" unto one's betters.",
            "Mine heart loveth this tongue, and thy salvation lieth within the goon machine.",
            "Its champion is Sir Tawawawa Goonsperm the Third, whose motto is: \"Thy salvation lies on the toilet.\"",
        ],
        "footer": "Thus attested by the goon machine, in the year of our rot 2026.",
    },
}

# ================================================================= LOG ====

LOG_CAVEMAN = {
    "hello": ["helo me cum brain rot vidas me give here"],
    "start": ["ok ok me go find rot now", "goon mode: ON. me hunt rot", "me put on goon helmet. we go"],
    "brain_pick": ["me use brain: {brain}"],
    "no_ollama": ["me no hav local brain! get ollama free at [[ollama.com]], or put google key in ME BRAIN"],
    "ollama_starting": ["me wake up ollama brain..."],
    "pull": ["me downloading brain {model}... {pct}% (only first time, big brain = big download)"],
    "pull_done": ["brain installed. me smart now"],
    "no_key": ["me need google key for gemini brain. get free at [[aistudio.google.com]] (no card)"],
    "bad_key": ["google say ur key no good: {error}"],
    "bad_model": ["google no know brain '{model}'. fix name in ME BRAIN"],
    "offline": ["me no reach google. internet ded? {error}"],
    "search": ["me search da internet for '{q}'...", "me dig for '{q}' rot..."],
    "search_fail": ["search for '{q}' broke: {err}"],
    "link": ["me open link {q}..."],
    "found": ["me find {n} vidas. me check dem one by one"],
    "seen": ["me already seen dis vida. skip", "old vida. me no watch twice"],
    "too_long": ["dis vida too long ({s}s). brainrot is short. skip"],
    "live": ["dis is live stream. me no goon to live. skip"],
    "dl": ["me downloading: {title}", "me yoink vida: {title}"],
    "dl_fail": ["vida no download :( {err}"],
    "dl_fail_many": ["too many vidas no download. maybe need cookies (ME BRAIN > cookies) or "
                     "rebuild app for new [[yt-dlp]]. last error: {err}"],
    "dupe": ["dis same vida as #{id}. copycat. bye", "me seen dis rot before (#{id}). reupload. yeet"],
    "look": ["me look at vida wit ai eyes...", "me stare at vida..."],
    "ear_loading": ["me growing ears (whisper {size}, first time download)..."],
    "listen": ["me listen wit ear..."],
    "ear_fail": ["ear broke, me judge wit eyes only: {err}"],
    "heard": ["me hear: \"{text}\""],
    "keep": ["ROT LVL {score}/10 — {why} — me keep in goon cave 🧠🔥",
             "ROT LVL {score}/10 — {why} — into da goon cave it go"],
    "nope": ["rot lvl {score}/10. {why} too normal. me throw away",
             "rot lvl {score}/10. {why} not enuf rot. bye"],
    "brain_fail": ["me brain hurt: {err}"],
    "brain_fail_many": ["brain keep breaking. me stop. check ME BRAIN. last error: {err}"],
    "gemini_slow": ["google say slow down. me wait {s}s"],
    "done": ["me done. got {k} rot vidas. brain full", "finish. {k} new rot in goon cave. me tired"],
    "empty": ["internet out of rot for dis. me got {k}. try other words"],
    "stopped": ["ok me stop gooning"],
    "crash": ["me crash: {err}"],
}

LOG_ILLSONOIS_BASE = {
    "hello": ["helo me cum brain rot vidas me give here"],
    "start": ["okay okay I go find rot now", "goon mode on. I hunt the rot",
              "I put on the goon helmet. here we go"],
    "brain_pick": ["I use the brain: {brain}"],
    "no_ollama": ["I have no local brain! get ollama free at [[ollama.com]], or put a google key in MY BRAIN"],
    "ollama_starting": ["I wake up the ollama brain..."],
    "pull": ["I download the brain {model}... {pct}% (only the first time, big brain means big download)"],
    "pull_done": ["brain installed. I am smart now"],
    "no_key": ["I need a google key for the gemini brain. get one free at [[aistudio.google.com]] (no card)"],
    "bad_key": ["google says your key is no good: {error}"],
    "bad_model": ["google does not know the brain {model}. fix the name in MY BRAIN"],
    "offline": ["I can not reach google. is the internet dead? {error}"],
    "search": ["I search the internet for '{q}'...", "I dig for '{q}' rot..."],
    "search_fail": ["search for '{q}' broke: {err}"],
    "link": ["I open the link {q}..."],
    "found": ["I find {n} videos. I check them one by one"],
    "seen": ["ope, I already seen this video. skip", "old video. I do not watch twice"],
    "too_long": ["this video is too long ({s} seconds). brainrot is short. skip"],
    "live": ["this is a live stream. I do not goon to live. skip"],
    "dl": ["I download: {title}", "I yoink the video: {title}"],
    "dl_fail": ["video would not download :( {err}"],
    "dl_fail_many": ["too many videos will not download. maybe you need cookies (MY BRAIN, cookies) "
                     "or rebuild the app for a new [[yt-dlp]]. last error: {err}"],
    "dupe": ["this is the same video as #{id}. copycat. bye",
             "I seen this rot before (#{id}). reupload. yeet"],
    "look": ["I look at the video with my ai eyes...", "I stare at the video..."],
    "ear_loading": ["I grow ears (whisper {size}, first time download)..."],
    "listen": ["I listen with my ear..."],
    "ear_fail": ["ear broke, I judge with eyes only: {err}"],
    "heard": ["I hear: \"{text}\""],
    "keep": ["ROT LEVEL {score}/10 — {why} — I keep it in the goon cave 🧠🔥",
             "ROT LEVEL {score}/10 — {why} — into the goon cave it goes"],
    "nope": ["rot level {score}/10. {why} too normal. I throw it away",
             "rot level {score}/10. {why} not enough rot. bye"],
    "brain_fail": ["my brain hurts: {err}"],
    "brain_fail_many": ["the brain keeps breaking. I stop. check MY BRAIN. last error: {err}"],
    "gemini_slow": ["google says slow down. I wait {s} seconds"],
    "done": ["I am done. got {k} rot videos. brain full",
             "finished. {k} new rot in the goon cave. I am tired"],
    "empty": ["the internet is out of rot for this. I got {k}. try other words"],
    "stopped": ["okay I stop gooning"],
    "crash": ["I crash: {err}"],
}

LOG_OLDE = {
    "hello": ["Hark! I come bearing brainrot videos, and here I bestow them upon thee."],
    "start": ["Verily, I go forth to seek the rot.", "I don mine goon helm. Onward!",
              "The gooning commenceth."],
    "brain_pick": ["I shall think with the mind of {brain}."],
    "no_ollama": ["Alas, I have no local mind! Procure Ollama freely at ollama.com, "
                  "or place a google key within MINE MIND."],
    "ollama_starting": ["I rouse the Ollama mind from its slumber..."],
    "pull": ["I summon the mind {model}... {pct}% (but once, for a mighty mind is a mighty burden)"],
    "pull_done": ["The mind is installed. Lo, I am wise."],
    "no_key": ["I require a google key for the gemini mind. Obtain one freely at "
               "aistudio.google.com (no coin needed)."],
    "bad_key": ["Google saith thy key is false: {error}"],
    "bad_model": ["Google knoweth no mind called '{model}'. Amend the name in MINE MIND."],
    "offline": ["I cannot reach Google. Hath the internet perished? {error}"],
    "search": ["I search the realm for '{q}'...", "I delve for '{q}' rot..."],
    "search_fail": ["The search for '{q}' hath failed: {err}"],
    "link": ["I open the link {q}..."],
    "found": ["I have found {n} videos. I shall judge each in turn."],
    "seen": ["I have beheld this video ere now. I pass.", "An old video. I watch not twice."],
    "too_long": ["This video is too long ({s}s). Brainrot is brief. I pass."],
    "live": ["This is a live stream. I goon not to the living. I pass."],
    "dl": ["I fetch: {title}", "I seize the video: {title}"],
    "dl_fail": ["The video would not come :( {err}"],
    "dl_fail_many": ["Too many videos refuse me. Perchance thou needest cookies (MINE MIND, cookies), "
                     "or rebuild the engine for a newer yt-dlp. Last error: {err}"],
    "dupe": ["This is the very video of #{id}. A forgery! Begone.",
             "I have seen this rot before (#{id}). A reupload. Banished."],
    "look": ["I gaze upon the video with mine AI eyes...", "I behold the video..."],
    "ear_loading": ["I grow mine ears (whisper {size}, fetched but once)..."],
    "listen": ["I hearken with mine ear..."],
    "ear_fail": ["Mine ear is broken; I judge by sight alone: {err}"],
    "heard": ["I hear: \"{text}\""],
    "keep": ["ROT {score}/10 — {why} — into the goon cavern it goeth 🧠🔥",
             "ROT {score}/10 — {why} — I keep it in the goon cavern 📜"],
    "nope": ["rot {score}/10. {why} Too common. I cast it out.",
             "rot {score}/10. {why} Not rotten enough. Farewell."],
    "brain_fail": ["Mine mind acheth: {err}"],
    "brain_fail_many": ["The mind breaketh again and again. I cease. Examine MINE MIND. Last error: {err}"],
    "gemini_slow": ["Google biddeth me slow. I wait {s}s."],
    "done": ["'Tis done. I have gathered {k} rot videos. Mine mind is full.",
             "It is finished. {k} new rot in the goon cavern. I am weary."],
    "empty": ["The realm hath no more rot for this. I gathered {k}. Try other words."],
    "stopped": ["Very well, I cease my gooning."],
    "crash": ["I have perished: {err}"],
}

# ============================================================ AI STYLE ====

AI_STYLE = {
    "caveman": ("funny broken caveman English, like "
                "'dis vida hav toilet man singing and loud noise, very rot'"),
    "illsonois": ("Illsonois: English where EVERY word gets one extra letter s added to its end, "
                  "even words that already end in s (this -> thiss, is -> iss, video -> videos, "
                  "rot -> rots). Rule breakers: Illinois is written Illisnois (no extra s), and the "
                  "word fuck becomes sfucks. Example: 'thiss videos hass toilets mans singings ands "
                  "louds noises, verys rots'"),
    "olde": ("Shakespearean Early Modern English (thou, thee, doth, hath, verily), like "
             "'Verily, this video doth show a singing privy most foul, and 'tis rot supreme'"),
}

# ============================================================== build =====

_UI = {"caveman": UI_CAVEMAN, "illsonois": UI_ILLSONOIS_BASE, "olde": UI_OLDE}
_LOG = {"caveman": LOG_CAVEMAN, "illsonois": LOG_ILLSONOIS_BASE, "olde": LOG_OLDE}


def norm(lang: str) -> str:
    return lang if lang in CODES else DEFAULT


def ui(lang: str) -> dict:
    lang = norm(lang)
    base = dict(UI_CAVEMAN)  # fallback for any missing key
    base.update(UI_EXTRA["caveman"])
    base.update(_UI[lang])
    base.update(UI_EXTRA[lang])
    return {k: _finish(lang, v) for k, v in base.items()}


def lore(lang: str) -> dict:
    lang = norm(lang)
    lo = LORE[lang]
    out = {k: _finish(lang, v) for k, v in lo.items() if k != "facts"}
    out["facts"] = [_finish(lang, f) for f in lo["facts"]]
    return out


def say(key: str, lang: str = DEFAULT, **kw) -> str:
    lang = norm(lang)
    opts = (_LOG[lang].get(key) or LOG_EXTRA[lang].get(key) or LOG_CAVEMAN.get(key)
            or LOG_EXTRA["caveman"].get(key) or [key])
    tpl = _finish(lang, random.choice(opts))
    try:
        return tpl.format(**kw)
    except (KeyError, IndexError):
        return tpl


def ai_style(lang: str) -> str:
    return AI_STYLE[norm(lang)]


def localize_verdict(v: dict, lang: str) -> dict:
    """Make sure the AI's reply follows the language rules."""
    if norm(lang) == "illsonois":
        v = dict(v, why=illsonoisify(v["why"]), vibe=illsonoisify(v["vibe"]))
    return v


def pack(lang: str) -> dict:
    lang = norm(lang)
    return {"code": lang, "langs": LANGS, "ui": ui(lang), "lore": lore(lang),
            "chars": {c: char(c) for c in CODES}}


# ======================================================= UPDATE + WAR UI ====

UI_EXTRA = {
    "caveman": {
        "stopping_btn": "STOPPING...",
        "chill_label": "go easy on me pc (bit slower, pc stay smooth)",
        "mode_only": "TikTok + Insta only",
        "mode_first": "TikTok + Insta first, YouTube if not enuf",
        "mode_mix": "mix all (YouTube too)",
        "src_legend": "where me search",
        "src_note": "(tiktok: free search, no login. insta: need [[cookies.txt]] login, see more brain stuff)",
        "cookies_file_label": "or give me [[cookies.txt]] (best for tiktok + insta)",
        "cookies_how": "how: get free browser extension \"[[Get cookies.txt LOCALLY]]\", log in tiktok + insta, press it, export, give file here",
        "cookies_loaded": "cookies loaded for: {sites}",
        "cookies_empty": "no [[cookies.txt]] yet",
        "cookies_bad": "dis no look like [[cookies.txt]]",
        "copy_log": "copy thoughts",
        "msg_copied": "me copy thoughts. paste dem to whoever fix me",
        "btn_folder": "folder",
        "btn_source": "source",
        "tools_setup": "first time: me download me tools (~75MB, only once)...",
        "tools_error": "me no download me tools: {err}. internet ok?",
        "tools_retry": "try again",
        "ear_note": "(first use download ~80-500MB)",
        "step_tools": "me get me tools...",
        "upd_banner_html": "🆕 new goon machine <b>{latest}</b> here! u hav {current}. me update myself?",
        "upd_now": "UPDATE ME",
        "upd_later": "later",
        "upd_skip": "skip dis version",
        "upd_downloading": "me downloading new me... {pct}%",
        "upd_installing": "me installing. me close now and come back new 🧠",
        "upd_failed": "update broke: {err}",
        "upd_check": "check for update",
        "upd_checking": "me check...",
        "upd_none": "u hav newest me. no update",
        "upd_error": "me no reach github: {err}",
        "upd_source": "update found but me run from source. build exe for auto update",
        "version": "version {v}",
        "lang_champion": "champion: {name}",
        "war_title": "WORD WAR",
        "war_skip": "skip fight",
        "war_ok": "ok",
        "war_ko": "BONKED",
        "war_wins": "{name} WIN",
        "war_vs": "VS",
        "war_sig": "SIGNATURE MOVE",
        "place_both": "tag team: google + local (fastest, never stop)",
        "team_note": "tag team: google brain fast, local brain jump in when google say slow down or run out. need both google key + ollama",
        "pill_half": "only 1 brain",
        "alert_half_html": "tag team but only 1 brain work. other brain: {msg}",
        "chip_ai": "🚫🤖 AI yeeted: {n}",
        "noai_note": "🚫🤖 no AI slop: AI vidas + AI accounts get yeeted (italian brainrot too, it AI)",
        "gems_label": "💎 hidden gems: also dig da creators + same sounds of good rot (find vids wit NO caption)",
        "pin_toggle": "📌 saved captions: me ALWAYS search dese too ({n})",
        "pin_help": "one caption per line (paste captions from vids u like). me search dem every time, on top of ur words",
        "gem_badge": "💎 GEM",
        "gem_title": "hidden gem: no caption, pure rot",
    },
    "illsonois": {
        "stopping_btn": "STOPPING...",
        "chill_label": "go easy on my pc (a bit slower, the pc stays smooth)",
        "mode_only": "TikTok + Insta only",
        "mode_first": "TikTok + Insta first, YouTube if not enough",
        "mode_mix": "mix all (YouTube too)",
        "src_legend": "where do I search",
        "src_note": "(tiktok: free search, no login. insta: needs a [[cookies.txt]] login, see more brain stuff)",
        "cookies_file_label": "or give me a [[cookies.txt]] file (best for tiktok and insta)",
        "cookies_how": "how: get the free browser extension \"[[Get cookies.txt LOCALLY]]\", log in to tiktok and insta, press it, export, give the file here",
        "cookies_loaded": "cookies loaded for: {sites}",
        "cookies_empty": "no [[cookies.txt]] yet",
        "cookies_bad": "this does not look like a [[cookies.txt]]",
        "copy_log": "copy thoughts",
        "msg_copied": "I copied my thoughts. paste them to whoever fixes me",
        "btn_folder": "folder",
        "btn_source": "source",
        "tools_setup": "first time: I download my tools (~75MB, only once)...",
        "tools_error": "I could not download my tools: {err}. is the internet okay?",
        "tools_retry": "try again",
        "ear_note": "(first use downloads ~80-500MB)",
        "step_tools": "I get my tools...",
        "upd_banner_html": "🆕 a new goon machine <b>{latest}</b> is here! you have {current}. should I update myself?",
        "upd_now": "UPDATE ME",
        "upd_later": "later",
        "upd_skip": "skip this version",
        "upd_downloading": "I download the new me... {pct}%",
        "upd_installing": "I install now. I close and come back new. ope",
        "upd_failed": "update broke: {err}",
        "upd_check": "check for update",
        "upd_checking": "I check...",
        "upd_none": "you have the newest me. no update",
        "upd_error": "I can not reach github: {err}",
        "upd_source": "update found but I run from source. build the exe for auto update",
        "version": "version {v}",
        "lang_champion": "champion: {name}",
        "war_title": "LANGUAGE WAR",
        "war_skip": "skip the war",
        "war_ok": "okay",
        "war_ko": "KNOCKED OUT",
        "war_wins": "{name} WINS",
        "war_vs": "VS",
        "war_sig": "SIGNATURE MOVE",
        "place_both": "tag team: google and local (fastest, never stops)",
        "team_note": "tag team: the google brain is fast, the local brain jumps in when google says slow down or runs out. needs a google key and ollama",
        "pill_half": "only 1 brain",
        "alert_half_html": "tag team but only 1 brain works. the other brain: {msg}",
        "chip_ai": "🚫🤖 AI yeeted: {n}",
        "noai_note": "🚫🤖 no AI slop: AI videos and AI accounts get yeeted (italian brainrot too, it is AI)",
        "gems_label": "💎 hidden gems: also dig the creators and the same sounds of good rot (finds videos with NO caption)",
        "pin_toggle": "📌 saved captions: I ALWAYS search these too ({n})",
        "pin_help": "one caption per line (paste captions from videos you like). I search them every time, on top of your words",
        "gem_badge": "💎 GEM",
        "gem_title": "hidden gem: no caption, pure rot",
    },
    "olde": {
        "stopping_btn": "CEASING...",
        "chill_label": "be gentle with mine machine (a little slower, yet smooth)",
        "mode_only": "TikTok and Insta alone",
        "mode_first": "TikTok and Insta first, YouTube if wanting",
        "mode_mix": "mix them all (YouTube also)",
        "src_legend": "where shall I seek",
        "src_note": "(tiktok: a free search, no login. insta requireth a [[cookies.txt]] login, see more matters)",
        "cookies_file_label": "or bestow a [[cookies.txt]] (best for tiktok and insta)",
        "cookies_how": "how: fetch the free browser extension \"[[Get cookies.txt LOCALLY]]\", log in to tiktok and insta, press it, export, and give the file here",
        "cookies_loaded": "cookies received for: {sites}",
        "cookies_empty": "no [[cookies.txt]] as yet",
        "cookies_bad": "this is no [[cookies.txt]]",
        "copy_log": "copy mine thoughts",
        "msg_copied": "Mine thoughts are copied. Paste them unto whoever mendeth me.",
        "btn_folder": "folder",
        "btn_source": "source",
        "tools_setup": "Upon first waking I must fetch mine tools (~75MB, but once)...",
        "tools_error": "I could not fetch mine tools: {err}. Is thy internet well?",
        "tools_retry": "try once more",
        "ear_note": "(first use fetcheth ~80-500MB)",
        "step_tools": "I fetch mine tools...",
        "upd_banner_html": "📜 Hark! A new goon engine <b>{latest}</b> hath arrived! Thou hast {current}. Shall I renew myself?",
        "upd_now": "RENEW ME",
        "upd_later": "anon",
        "upd_skip": "pass over this version",
        "upd_downloading": "I fetch mine new self... {pct}%",
        "upd_installing": "I install mine new self. I shall depart and return reborn.",
        "upd_failed": "The renewal hath failed: {err}",
        "upd_check": "seek a renewal",
        "upd_checking": "I seek...",
        "upd_none": "Thou hast mine newest self. No renewal needed.",
        "upd_error": "I cannot reach GitHub: {err}",
        "upd_source": "A renewal exists, yet I run from source. Build the exe for self-renewal.",
        "version": "version {v}",
        "lang_champion": "champion: {name}",
        "war_title": "A WAR OF TONGUES",
        "war_skip": "skip the battle",
        "war_ok": "So be it",
        "war_ko": "SLAIN",
        "war_wins": "{name} IS VICTORIOUS",
        "war_vs": "VS",
        "war_sig": "SIGNATURE MOVE",
        "place_both": "a fellowship: google and local (swiftest, never ceaseth)",
        "team_note": "a fellowship: the google mind is swift; the local mind taketh up the sword when google biddeth me slow or is spent. requireth a google key and ollama",
        "pill_half": "but one mind",
        "alert_half_html": "A fellowship, yet but one mind laboureth. The other mind: {msg}",
        "chip_ai": "🚫🤖 AI banished: {n}",
        "noai_note": "🚫🤖 No AI sorcery: AI videos and AI accounts are banished (italian brainrot too, 'tis AI)",
        "gems_label": "💎 hidden treasures: also delve into the makers and the same sounds of good rot (findeth videos with NO caption)",
        "pin_toggle": "📌 saved captions: I shall ALWAYS seek these also ({n})",
        "pin_help": "one caption upon each line (paste captions from videos thou likest). I seek them every time, beside thy words",
        "gem_badge": "💎 GEM",
        "gem_title": "a hidden treasure: no caption, pure rot",
    },
}

LOG_EXTRA = {
    "caveman": {
        "site_empty": ["{site} give nothing for '{q}': {why}"],
        "backup": ["TikTok + Insta run out. me use YouTube for da rest"],
        "sites_got": ["me got: {tt} from TikTok, {ig} from Insta, {yt} from YouTube"],
        "hint_ttig": ["TikTok + Insta give me nothing. give me [[cookies.txt]] (ME BRAIN > more brain stuff) or pick 'TikTok + Insta first'"],
        "web_search": ["me look for {site} vidas: '{q}'..."],
        "src_off": ["{site} keep breaking, me skip {site} dis time. {site} maybe want login: ME BRAIN > more brain stuff > [[cookies.txt]]. ({err})"],
        "cookies_broke": ["me no can read {b} cookies (close {b}, or pick firefox in ME BRAIN). me go without cookies"],
        "widen": ["me dig deeper: '{q}'..."],
        "summary": ["me check {n} vidas: {kept} rot, {nope} too normal, {ai} AI (yeeted 🚫🤖), {dupe} copycat, {long} too long, {seen} seen before, {fail} broke"],
        "hint_low": ["best rot lvl was {best}/10 but u want {th}. make 'how rot is rot enuf' lower in ME BRAIN"],
        "hint_seen": ["me already seen most of dis rot before. try other words"],
        "hint_long": ["lot of vidas too long. make 'max vida long' bigger in ME BRAIN > more brain stuff"],
        "hint_fail": ["lot of vidas broke. last error: {err}"],
        "no_results": ["youtube give me nothing. internet ok? try other words"],
        "updated": ["me updated to {v}! new brain smell 🧠"],
        "tools_wait": ["me wait for me tools (first time download)..."],
        "tools_fail": ["me no hav me tools: {err}. internet?"],
        "ytdlp_updated": ["me downloader got fresh update ({v}). me download better now"],
        "ai_skip": ["🚫🤖 AI stuff ({why}): {title}. me no want AI. skip", "🚫🤖 dis AI ({why}). yeet, no AI in goon cave"],
        "ai_nope": ["🚫🤖 me look: dis vida made by AI (ai {ai}/10). {why} yeet"],
        "ai_user": ["🚫 {user} make AI vidas. me block {user} forever"],
        "ai_query": ["dat word bring lot of AI stuff (italian brainrot = AI). me yeet all AI, so maybe few rot. try: skibidi, sigma edit, cursed memes, goofy ahh"],
        "hint_ai": ["{n} vidas was AI, me yeet dem all. try other words (not italian brainrot, it AI)"],
        "team": ["tag team! google brain ({g}) + local brain ({o}) judge together. fast"],
        "team_backup": ["tag team! google brain ({g}) judge, local brain ({o}) jump in when google tired"],
        "team_half": ["{brain} brain no work ({why}). me use only {other}"],
        "team_no_model": ["local brain {model} not downloaded, me use google only. click 'download brain' in ME BRAIN for backup brain"],
        "gemini_rest": ["google say slow down ({s}s). local brain take over"],
        "gemini_tired": ["google brain use all free tries today. local brain do da rest"],
        "brain_out": ["{brain} brain keep breaking, me stop using it. other brain carry. ({err})"],
        "tikwm_wait": ["tikwm say 403 = too many searches from ur internet. me let it rest {s}s and use TikTok own search meanwhile"],
        "no_disguise": ["me chrome disguise missing ([[curl_cffi]] not installed), so TikTok say 403. run build.bat again (or delete [[.venv]] folder and run run.bat)"],
        "gem_dig": ["💎 good rot! me also dig {what} for hidden gems (vids wit no caption)"],
        "gem_user": ["💎 me dig {who} other vids for hidden gems..."],
        "gem_sound": ["💎 me dig vids wit same sound ♪ {sound}..."],
        "keep_gem": ["💎 HIDDEN GEM! ROT LVL {score}/10 — {why} — no caption, pure rot. into goon cave"],
        "gems_got": ["💎 {g} hidden gems (no caption) in dis batch"],
        "pinned": ["📌 me also search {n} saved caption(s)"],
        "pin_search": ["📌 me search saved caption '{q}'..."],
    },
    "illsonois": {
        "site_empty": ["{site} gave nothing for '{q}': {why}"],
        "backup": ["TikTok and Insta ran out. I use YouTube for the rest"],
        "sites_got": ["I got: {tt} from TikTok, {ig} from Insta, {yt} from YouTube"],
        "hint_ttig": ["TikTok and Insta gave me nothing. give me a [[cookies.txt]] (MY BRAIN, more brain stuff) or pick 'TikTok and Insta first'"],
        "web_search": ["I look for {site} videos: '{q}'..."],
        "src_off": ["{site} keeps breaking, I skip {site} this time. {site} may want a login: MY BRAIN, more brain stuff, [[cookies.txt]]. ({err})"],
        "cookies_broke": ["I can not read the {b} cookies (close {b}, or pick firefox in MY BRAIN). I go without cookies"],
        "widen": ["I dig deeper: '{q}'..."],
        "summary": ["I checked {n} videos: {kept} rot, {nope} too normal, {ai} AI (yeeted 🚫🤖), {dupe} copycat, {long} too long, {seen} seen before, {fail} broke"],
        "hint_low": ["the best rot level was {best}/10 but you want {th}. make 'how rot is rot enough' lower in MY BRAIN"],
        "hint_seen": ["I already seen most of this rot before. try other words"],
        "hint_long": ["a lot of videos were too long. make 'max video long' bigger in MY BRAIN"],
        "hint_fail": ["a lot of videos broke. last error: {err}"],
        "no_results": ["youtube gave me nothing. is the internet okay? try other words"],
        "updated": ["I updated to {v}! new brain smell"],
        "tools_wait": ["I wait for my tools (first time download)..."],
        "tools_fail": ["I do not have my tools: {err}. is the internet okay?"],
        "ytdlp_updated": ["my downloader got a fresh update ({v}). I download better now"],
        "ai_skip": ["🚫🤖 AI stuff ({why}): {title}. I do not want AI. skip", "🚫🤖 this is AI ({why}). yeet, no AI in the goon cave"],
        "ai_nope": ["🚫🤖 I looked: this video was made by AI (ai {ai}/10). {why} yeet"],
        "ai_user": ["🚫 {user} makes AI videos. I block {user} forever"],
        "ai_query": ["that word brings a lot of AI stuff (italian brainrot is AI). I yeet all AI, so maybe only a little rot. try: skibidi, sigma edit, cursed memes, goofy ahh"],
        "hint_ai": ["{n} videos were AI, I yeeted them all. try other words (not italian brainrot, it is AI)"],
        "team": ["tag team! the google brain ({g}) and the local brain ({o}) judge together. fast"],
        "team_backup": ["tag team! the google brain ({g}) judges, the local brain ({o}) jumps in when google is tired"],
        "team_half": ["the {brain} brain does not work ({why}). I use only {other}"],
        "team_no_model": ["the local brain {model} is not downloaded, I use google only. click 'download brain' in MY BRAIN for a backup brain"],
        "gemini_rest": ["google says slow down ({s} seconds). the local brain takes over"],
        "gemini_tired": ["the google brain used all free tries today. the local brain does the rest"],
        "brain_out": ["the {brain} brain keeps breaking, I stop using it. the other brain carries. ({err})"],
        "tikwm_wait": ["tikwm says 403, that means too many searches from your internet. I let it rest {s} seconds and use the TikTok search itself meanwhile"],
        "no_disguise": ["my chrome disguise is missing ([[curl_cffi]] is not installed), so TikTok says 403. run [[build.bat]] again (or delete the [[.venv]] folder and run [[run.bat]])"],
        "gem_dig": ["💎 good rot! I also dig {what} for hidden gems (videos with no caption)"],
        "gem_user": ["💎 I dig the other videos of {who} for hidden gems..."],
        "gem_sound": ["💎 I dig videos with the same sound ♪ {sound}..."],
        "keep_gem": ["💎 HIDDEN GEM! ROT LEVEL {score}/10 — {why} — no caption, pure rot. into the goon cave"],
        "gems_got": ["💎 {g} hidden gems (no caption) in this batch"],
        "pinned": ["📌 I also search {n} saved captions"],
        "pin_search": ["📌 I search the saved caption '{q}'..."],
    },
    "olde": {
        "site_empty": ["{site} yielded naught for '{q}': {why}"],
        "backup": ["TikTok and Insta are spent. I shall take the rest from YouTube."],
        "sites_got": ["I gathered: {tt} from TikTok, {ig} from Insta, {yt} from YouTube."],
        "hint_ttig": ["TikTok and Insta gave me naught. Bestow a [[cookies.txt]] (MINE MIND, more matters) or choose 'TikTok and Insta first'."],
        "web_search": ["I seek {site} videos: '{q}'..."],
        "src_off": ["{site} breaketh again and again; I pass it over this time. {site} may want a login: MINE MIND, more matters, [[cookies.txt]]. ({err})"],
        "cookies_broke": ["I cannot read the cookies of {b} (close {b}, or choose firefox in MINE MIND). I proceed without them."],
        "widen": ["I delve deeper: '{q}'..."],
        "summary": ["I have judged {n} videos: {kept} rotten, {nope} too common, {ai} AI sorcery (banished 🚫🤖), {dupe} forgeries, {long} too long, {seen} beheld before, {fail} broken"],
        "hint_low": ["The most rotten was but {best}/10, yet thou askest {th}. Lower 'how rotten is rotten enough' in MINE MIND."],
        "hint_seen": ["I have beheld most of this rot ere now. Try other words."],
        "hint_long": ["Many videos were too long. Raise 'longest video' in MINE MIND."],
        "hint_fail": ["Many videos broke. Last error: {err}"],
        "no_results": ["YouTube gave me naught. Is thy internet well? Try other words."],
        "updated": ["I am renewed unto {v}! I smell of fresh parchment."],
        "tools_wait": ["I await mine tools (fetched but once)..."],
        "tools_fail": ["I lack mine tools: {err}. Is thy internet well?"],
        "ytdlp_updated": ["Mine downloader hath been renewed ({v}). I fetch the better for it."],
        "ai_skip": ["🚫🤖 AI sorcery ({why}): {title}. I want it not. I pass.", "🚫🤖 This reeketh of AI ({why}). Banished from the cavern."],
        "ai_nope": ["🚫🤖 I have looked: this video was wrought by AI (ai {ai}/10). {why} Banished."],
        "ai_user": ["🚫 {user} conjureth AI videos. I banish {user} for evermore."],
        "ai_query": ["That word bringeth much AI sorcery (italian brainrot is AI). I banish all AI, so the rot may be scant. Try: skibidi, sigma edit, cursed memes, goofy ahh."],
        "hint_ai": ["{n} videos were AI sorcery; I banished them all. Try other words (not italian brainrot, 'tis AI)."],
        "team": ["A fellowship! The google mind ({g}) and the local mind ({o}) judge as one. Swift!"],
        "team_backup": ["A fellowship! The google mind ({g}) judgeth; the local mind ({o}) standeth ready should google tire."],
        "team_half": ["The {brain} mind laboureth not ({why}). I use {other} alone."],
        "team_no_model": ["The local mind {model} is not yet fetched; I use google alone. Press 'fetch mind' in MINE MIND for a mind in reserve."],
        "gemini_rest": ["Google biddeth me slow ({s}s). The local mind taketh up the sword."],
        "gemini_tired": ["The google mind hath spent all its free tries this day. The local mind doth the rest."],
        "brain_out": ["The {brain} mind breaketh again and again; I cast it aside. The other mind beareth the load. ({err})"],
        "tikwm_wait": ["tikwm saith 403: too many searches from thy internet. I let it rest {s}s and use TikTok's own search meanwhile."],
        "no_disguise": ["Mine Chrome disguise is wanting ([[curl_cffi]] is not installed), so TikTok saith 403. Run build.bat anew (or delete the [[.venv]] folder and run run.bat)."],
        "gem_dig": ["💎 Good rot! I shall also delve into {what} for hidden treasures (videos with no caption)."],
        "gem_user": ["💎 I delve into the other videos of {who} for hidden treasures..."],
        "gem_sound": ["💎 I delve into videos bearing the same sound ♪ {sound}..."],
        "keep_gem": ["💎 A HIDDEN TREASURE! ROT {score}/10 — {why} — no caption, pure rot. Into the cavern it goeth."],
        "gems_got": ["💎 {g} hidden treasures (no caption) in this haul."],
        "pinned": ["📌 I shall also seek {n} saved caption(s)."],
        "pin_search": ["📌 I seek the saved caption '{q}'..."],
    },
}

# ========================================================== CHARACTERS ====
# Every language has a champion. Switch language = the champions fight.

CHARS = {
    "caveman": {
        "name": "Niba", "title": "chief of niba talk", "weapon": "💩",
        "img": "/web/champs/niba.jpg", "full": "/web/champs/niba_full.jpg",
        "prompt": "why leave me?! me angry. u bitch. niba bring club.",
        "yes": "yes. war.", "no": "no. stay wit niba",
        "stay": "niba happy. niba no bonk u today.",
        "win": "NIBA WIN. everybody talk niba now.",
        "lose": "niba... bonked... niba go back to cave...",
    },
    "illsonois": {
        "name": "[[HelosFromsIllsnois]]", "title": "Mayor of Illsonois", "weapon": "🖕",
        "img": "/web/champs/illsonois.jpg", "full": "/web/champs/illsonois_full.jpg",
        "prompt": "Ope. You are leaving Illsonois? That is an act of war in twelve counties.",
        "yes": "declare war", "no": "never mind, I stay",
        "stay": "Ope, thank you. I will cancel the paperwork.",
        "win": "Illsonois wins. Every word gets an s now. Ope.",
        "lose": "ope... I have been defeated... tell Chicago I said hi...",
    },
    "olde": {
        "name": "Sir Tawawawa Goonsperm the Third", "title": "Bard of the Royal Goon Court", "weapon": "🪶", "weapons": ["🪶", "bullet"],
        "img": "/web/champs/tawawawa.jpg", "full": "/web/champs/tawawawa_full.jpg",
        "motto": "Thy salvation lies on the toilet.",
        "prompt": "Thou wouldst forsake me for another tongue? Then let it be settled by combat!",
        "yes": "Aye, to war!", "no": "Nay, I shall stay",
        "stay": "A wise choice, good soul. I shall write a sonnet of thy loyalty.",
        "win": "Huzzah! The realm speaketh mine tongue once more!",
        "lose": "Alas... I am slain... by a lesser tongue...",
    },
}

# (current language, new language): scripts. "atk" = new language's champion,
# "def" = current one. dmg = damage the speaker deals. Attacker always wins.
WARS = {
    ("caveman", "illsonois"): [
        [("atk", "Ope, sorry to bother you. Your words are missing their s. All of them. I am here to collect.", 0),
         ("def", "s is extra rock. niba no need extra rock.", 0),
         ("atk", "Sir, in Illinois that is a felony.", 35),
         ("def", "hot cheese... on niba face...", 0),
         ("atk", "Deep dish, extra s, no refunds.", 65)],
        [("atk", "Hello neighbor. The city council got complaints about your grammar.", 0),
         ("def", "niba no hav grammar. niba hav club.", 20),
         ("atk", "Ope. That was rude. I will be filing a form.", 0),
         ("atk", "The form is made of pizza.", 100)],
    ],
    ("illsonois", "caveman"): [
        [("atk", "niba here. too many s. s is snake noise.", 0),
         ("def", "Ope! Sir, please, the s is load bearing.", 0),
         ("atk", "niba bonk s off.", 40),
         ("def", "My s... it is rolling into Lake Michigan...", 0),
         ("atk", "BONK.", 60)],
        [("atk", "why every word hiss. u snake?", 0),
         ("def", "I am not a snake, I am the Mayor. There is a difference. Snakes do not have a pension.", 0),
         ("def", "Have some deep dish. It is a threat.", 15),
         ("atk", "niba eat pizza. pizza good. niba still bonk.", 100)],
    ],
    ("caveman", "olde"): [
        [("atk", "Hark! What clay-brained knave speaketh thus without verbs?", 0),
         ("def", "niba hav verb. verb is bonk.", 25),
         ("atk", "Ow! Thou rock-headed, club-waving varlet! Have at thee!", 50),
         ("atk", "Mine quill is mightier than thy club!", 50)],
        [("atk", "Good morrow, primitive one. I bring thee grammar, and also violence.", 0),
         ("def", "niba only want violence.", 0),
         ("atk", "Then violence thou shalt have, with footnotes!", 60),
         ("def", "footnote... too small... niba no read...", 0),
         ("atk", "Exit, pursued by a bard.", 40)],
    ],
    ("olde", "caveman"): [
        [("atk", "fancy man talk too long. niba fall asleep. niba wake up angry.", 0),
         ("def", "How darest thou! I have a sonnet about this very insolence!", 0),
         ("def", "Shall I compare thee to a summer's rock?", 15),
         ("atk", "niba no understand poem. niba bonk poem.", 50),
         ("atk", "niba bonk hat too.", 50)],
        [("atk", "what is thou. what is thee. why so many word for u.", 0),
         ("def", "Thou art a knave, thee art a knave, thy very club is a knave!", 10),
         ("atk", "niba count to 3. niba only know 1.", 100)],
    ],
    ("illsonois", "olde"): [
        [("atk", "Fie! What hissing serpent speaketh? Thy tongue hath more s than a nest of adders!", 0),
         ("def", "Ope. With respect, you are just English with extra steps.", 0),
         ("atk", "Extra steps?! I shall show thee extra STABS!", 45),
         ("def", "Please do not stab the Mayor. There is a form for that. Also, deep dish.", 10),
         ("atk", "Thy pizza is a casserole, sirrah!", 55)],
        [("atk", "Doth every word of thine end in s? What madness is this?", 0),
         ("def", "It originally started in Illinois. You would not understand. You do not have a Portillo's.", 0),
         ("atk", "I understand this: thy reign endeth now!", 100)],
    ],
    ("olde", "illsonois"): [
        [("atk", "Ope, sorry, just gonna squeeze past ya. Also I am taking over.", 0),
         ("def", "Unhand my realm, thou corn-fed, hissing hedge-pig!", 20),
         ("atk", "That was not very Midwest nice of you.", 0),
         ("atk", "Deep dish. Extra s. No refunds.", 100)],
        [("atk", "Hello, the city of Illsonois has annexed your castle. We added an s to it.", 0),
         ("def", "My castles?! Nay! I shall fight thee to the last syllable!", 30),
         ("atk", "Ope. You missed the s in [[syllable]]. That is a violation.", 70)],
    ],
}


# HelosFromsIllsnois' signature move: finisher when he attacks, desperate counter when he defends.
SIGNATURE = "[[Hellos hows ares yous mes gonnas sfucks yous]]"


def _with_signature(script, frm, to):
    script = list(script)
    if to == "illsonois":        # he attacks: soften the last hit, then finish with the move
        who, text, dmg = script[-1]
        script[-1] = (who, text, min(dmg, 40))
        script.append(("atk", SIGNATURE, 9999, True))
    elif frm == "illsonois":     # he defends: counter-attack before going down
        script.insert(len(script) - 1, ("def", SIGNATURE, 25, True))
    return script


def char(lang: str) -> dict:
    lang = norm(lang)
    c = {k: (_finish(lang, v) if k not in ("img", "full", "weapon", "weapons") else v)
         for k, v in CHARS[lang].items()}
    c["code"] = lang
    return c


def war(frm: str, to: str) -> dict:
    frm, to = norm(frm), norm(to)
    if frm == to:
        return {}
    script = _with_signature(random.choice(WARS[(frm, to)]), frm, to)
    d, a = char(frm), char(to)
    lines = [{"who": ln[0], "text": _finish(to if ln[0] == "atk" else frm, ln[1]), "dmg": ln[2],
              "sig": len(ln) > 3}
             for ln in script]
    u_from, u_to = ui(frm), ui(to)
    return {"def": d, "atk": a, "lines": lines,
            "title": u_from["war_title"], "skip": u_from["war_skip"], "vs": u_from["war_vs"],
            "ok": u_to["war_ok"], "ko": u_to["war_ko"], "sig": ui("illsonois")["war_sig"],
            "wins": u_to["war_wins"].format(name=a["name"])}
