const $ = (id) => document.getElementById(id);
const api = async (path, body) => {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(r.status + " " + path);
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const linkHtml = (url, text) => `<a href="#" data-link="${esc(url)}">${esc(text)}</a>`;

let L = { code: "caveman", ui: {}, lore: {}, langs: [] };
let lastLog = 0, running = false, vids = [], hw = null, cfg = null, stats = {}, brainSt = null;
let logBig = false, sleeping = true;
let appVersion = "0.0.0", upd = null, updLater = false;

// ------------------------------------------------------------------ i18n --
function t(key, vars = {}) {
  const s = L.ui[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}
async function loadLang(code) {
  L = await api("/api/lang" + (code ? "?code=" + code : ""));
  document.body.className = "lang-" + L.code;
  document.documentElement.lang = L.code === "illsonois" ? "en-x-ils" : "en";
  document.title = t("doc_title");
  document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll("[data-th]").forEach((el) => {
    el.innerHTML = t(el.dataset.th, { link: linkHtml("https://aistudio.google.com/apikey", "aistudio.google.com") });
  });
  document.querySelectorAll("[data-tp]").forEach((el) => { el.placeholder = t(el.dataset.tp); });
  document.querySelectorAll("[data-tt]").forEach((el) => { el.title = t(el.dataset.tt); });
  const me = L.langs.find((x) => x.code === L.code) || {};
  $("langBtnTxt").textContent = (me.emoji ? me.emoji + " " : "") + (me.name || L.code);
  $("hello").textContent = t("hello");
  $("verTxt").textContent = t("version", { v: "v" + appVersion });
  if (upd) showUpdate(upd);
  $("logToggle").textContent = t(logBig ? "log_less" : "log_more");
  renderLangs();
  if (sleeping) $("log").innerHTML = `<li class="k-info">${esc(t("step_idle"))}</li>`;
  if (cfg) fillConfig(cfg);
  if (hw) showHw(hw);
  showStats(stats);
  if (brainSt) showBrain(brainSt);
  if (typeof loadCookies === "function") loadCookies();
  setRunning(running);
  renderVids();
}

function renderLangs() {
  $("langs").innerHTML = L.langs.map((l) => `
    <button class="langcard ${l.code === L.code ? "on" : ""}" type="button" data-lang="${l.code}">
      <span class="em">${face(L.chars[l.code])}</span>
      <span><b>${l.emoji ? l.emoji + " " : ""}${esc(l.name)}</b><span class="s">"${esc(l.sample)}"</span>
        <span class="champ">⚔ ${esc(t("lang_champion", { name: (L.chars[l.code] || {}).name || "?" }))}</span></span>
    </button>`).join("");
  const champ = L.chars[L.code] || {};
  $("lorePic").hidden = !champ.full;
  if (champ.full) { $("lorePic").src = champ.full; $("lorePic").alt = champ.name; }
  $("loreTitle").textContent = L.lore.title;
  $("loreIntro").textContent = L.lore.intro;
  $("loreFacts").innerHTML = L.lore.facts.map((f) => `<li>${esc(f)}</li>`).join("");
  $("loreFoot").textContent = "✦ " + L.lore.footer;
}

$("langs").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-lang]");
  if (!b || b.dataset.lang === L.code) return;
  closeDrawers();
  await languageWar(L.code, b.dataset.lang);
});

async function switchLang(code, extraLine) {
  cfg = await api("/api/config", { lang: code });
  await loadLang(code);
  const me = L.langs.find((x) => x.code === L.code);
  addLocal(t("lang_switched", { lang: me ? me.name : L.code }), "good");
  if (extraLine) addLocal(extraLine, "good");
}

// ------------------------------------------------------------ lang war --
// No bullet emoji exists, so Tawawawa's bullet is drawn.
const BULLET = `<svg class="bullet" viewBox="0 0 64 24" width="60" height="22" aria-label="bullet">
  <rect x="2" y="4" width="34" height="16" rx="2" fill="#d4ad45" stroke="#6b4f12" stroke-width="2"/>
  <rect x="3" y="5" width="6" height="14" fill="#a8841f"/>
  <path d="M36 4 H44 C56 4 62 10 62 12 C62 14 56 20 44 20 H36 Z" fill="#c07a3c" stroke="#5a3210" stroke-width="2"/>
  <path d="M40 7 H46 C52 7 56 10 57 11" fill="none" stroke="#f1c28e" stroke-width="2" stroke-linecap="round"/></svg>`;
const face = (c) => c && c.img ? `<img src="${esc(c.img)}" alt="${esc(c.name)}">` : "";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let warSkip = false, warNext = null;

function waitOrClick(ms) {           // click on the arena = next line faster
  return new Promise((res) => {
    const done = () => { clearTimeout(tm); warNext = null; res(); };
    const tm = setTimeout(done, ms);
    warNext = done;
  });
}

function askLeave(d) {
  return new Promise((res) => {
    $("lvAv").innerHTML = face(d);
    $("lvName").textContent = d.name;
    $("lvTitle").textContent = d.title + (d.motto ? ` · "${d.motto}"` : "");
    $("lvText").textContent = `"${d.prompt}"`;
    $("lvYes").textContent = d.yes;
    $("lvNo").textContent = d.no;
    $("leave").hidden = false;
    $("lvYes").onclick = () => { $("leave").hidden = true; res(true); };
    $("lvNo").onclick = () => { $("leave").hidden = true; res(false); };
  });
}

function setHp(side, hp) {
  const bar = $("hp" + side);
  bar.style.width = Math.max(0, hp) + "%";
  bar.className = hp <= 25 ? "crit" : hp <= 55 ? "low" : "";
}

async function languageWar(from, to) {
  let w;
  try { w = await api(`/api/war?from=${from}&to=${to}`); } catch (e) { return switchLang(to); }
  if (!w || !w.lines) return switchLang(to);

  const stay = await askLeave(w.def);
  if (!stay) { addLocal(`${w.def.name}: "${w.def.stay}"`, "good"); return; }

  // set up arena: current language (defender) left, challenger right
  const side = { def: "L", atk: "R" };
  const hp = { def: 100, atk: 100 };
  for (const [who, s] of Object.entries(side)) {
    const c = w[who];
    $("av" + s).innerHTML = face(c);
    $("nm" + s).textContent = c.name;
    $("tl" + s).textContent = c.title;
    $("ko" + s).hidden = true;
    $("f" + s).className = "fighter";
    setHp(s, 100);
  }
  $("warTitle").textContent = "⚔️ " + w.title + " ⚔️";
  $("warVs").textContent = w.vs;
  $("warSkip").textContent = w.skip;
  $("warOk").textContent = w.ok;
  $("warOk").hidden = true; $("warSkip").hidden = false;
  $("warResult").hidden = true;
  $("spWho").textContent = ""; $("spText").textContent = "";
  $("speech").hidden = false;
  $("war").hidden = false;
  warSkip = false;
  const wIdx = { atk: 0, def: 0 };
  await sleep(500);

  for (const line of w.lines) {
    if (warSkip) break;
    const me = side[line.who], them = line.who === "atk" ? "def" : "atk", themS = side[them];
    $("f" + me).classList.add("talk");
    $("spWho").innerHTML = face(w[line.who]) + esc(w[line.who].name) + ":";
    const txt = line.text; $("spText").textContent = "";
    for (let i = 0; i < txt.length && !warSkip; i += 2) {   // typewriter
      $("spText").textContent = txt.slice(0, i + 2);
      await sleep(16);
    }
    $("spText").textContent = txt;
    if (line.sig && !warSkip) {
      const fl = $("sigFlash");
      fl.textContent = "💥 " + w.sig + " 💥";
      fl.hidden = false; fl.classList.remove("go"); void fl.offsetWidth; fl.classList.add("go");
      $("warBox").classList.remove("quake"); void $("warBox").offsetWidth; $("warBox").classList.add("quake");
      await sleep(700);
    }
    if (line.dmg && !warSkip) {
      const p = $("proj");
      const ws = w[line.who].weapons || [w[line.who].weapon];
      const wp = ws[wIdx[line.who]++ % ws.length];
      if (wp === "bullet") p.innerHTML = line.sig ? BULLET.repeat(3) : BULLET;
      else p.textContent = line.sig ? wp.repeat(3) : wp;
      p.className = "projectile" + (line.sig ? " big" : "") + (wp === "bullet" ? " straight" : "");
      p.hidden = false; void p.offsetWidth;
      p.classList.add(me === "L" ? "fly-r" : "fly-l");
      await sleep(430);
      p.hidden = true;
      hp[them] -= line.dmg;
      setHp(themS, hp[them]);
      const f = $("f" + themS); f.classList.remove("hit"); void f.offsetWidth; f.classList.add("hit");
      const pop = $("dp" + themS); pop.textContent = "-" + line.dmg; pop.classList.remove("go"); void pop.offsetWidth; pop.classList.add("go");
    }
    await waitOrClick(Math.min(2600, 900 + txt.length * 22) + (line.sig ? 900 : 0));
    $("f" + me).classList.remove("talk");
    $("sigFlash").hidden = true;
  }

  // finish: challenger always wins
  setHp("L", 0);
  $("fL").classList.add("dead");
  $("koL").textContent = w.ko; $("koL").hidden = false;
  $("speech").hidden = true;
  $("warResult").innerHTML =
    `<span class="wins">🏆 ${esc(w.wins)}</span>` +
    `<div class="said">${face(w.atk)}<span>"${esc(w.atk.win)}"</span></div>` +
    `<div class="said lose">${face(w.def)}<span>"${esc(w.def.lose)}"</span></div>`;
  $("warResult").hidden = false;
  $("warSkip").hidden = true; $("warOk").hidden = false;
  await new Promise((res) => { $("warOk").onclick = res; });
  $("war").hidden = true;
  await switchLang(to, `${w.atk.name}: "${w.atk.win}"`);
}
$("warSkip").onclick = () => { warSkip = true; if (warNext) warNext(); };
$("arena").onclick = () => { if (warNext) warNext(); };
$("speech").onclick = () => { if (warNext) warNext(); };

// ----------------------------------------------------------------- boot --
async function boot() {
  const h = await api("/api/hello");
  hw = h.hw; cfg = h.config; stats = h.stats; appVersion = h.version; upd = h.update;
  await loadLang(h.lang);
  try { const q = localStorage.getItem("goon.query"); if (q) $("query").value = q; } catch (e) {}
  try { const n = localStorage.getItem("goon.count"); if (n) $("count").value = n; } catch (e) {}
  checkBrain();
  loadVids();
  pollLoop();
}

function showStats(s) {
  const kept = s.kept || 0;
  const seen = Object.values(s).reduce((a, b) => a + b, 0);
  $("chipCave").textContent = t("chip_cave", { n: kept });
  $("chipSeen").textContent = t("chip_seen", { n: seen });
}

function showHw(h) {
  const gpu = h.gpu ? `${esc(h.gpu)} <b>${h.vram_gb}GB</b>` : `<b>${esc(t("hw_nogpu"))}</b>`;
  $("ollama_model").placeholder = h.model;
  $("hwLine").innerHTML =
    t("hw_line_html", { gpu, ram: h.ram_gb, cores: h.cores }) + "<br>" +
    t("hw_pick_html", { model: esc(h.model), tier: esc(t("tier_" + h.tier)), speed: esc(t("speed_" + h.speed)) }) +
    (h.recommend === "gemini" ? "<br>" + esc(t("hw_tip")) : "");
}

// --------------------------------------------------------------- config --
const FIELDS = ["ollama_model", "gemini_model", "threshold", "max_secs", "cookies_browser",
  "whisper_size", "taste", "cave_dir"];
const CHECKS = ["ear_mode", "keep_rejects", "chill_cpu"];

function fillConfig(c) {
  FIELDS.forEach((k) => { if ($(k)) $(k).value = c[k] ?? ""; });
  CHECKS.forEach((k) => { $(k).checked = !!c[k]; });
  document.querySelectorAll("input[name=backend]").forEach((r) => { r.checked = r.value === c.backend; });
  document.querySelectorAll("input[name=source_mode]").forEach((r) => { r.checked = r.value === (c.source_mode || "first"); });
  $("gemini_key").value = "";
  $("gemini_key").placeholder = c.gemini_key_set ? t("key_saved_ph", { hint: c.gemini_key_hint }) : t("key_ph");
  showThreshold(c.threshold);
  showPlaceGroups();
}
function showThreshold(v) { $("thLabel").innerHTML = t("th_label_html", { v: esc(v) }); }

function showPlaceGroups() {
  const b = (document.querySelector("input[name=backend]:checked") || {}).value || "auto";
  document.querySelectorAll(".group[data-for]").forEach((g) => {
    g.hidden = !g.dataset.for.split(" ").includes(b);
  });
}

function readConfig() {
  const c = {};
  FIELDS.forEach((k) => { c[k] = $(k).value; });
  CHECKS.forEach((k) => { c[k] = $(k).checked; });
  const b = document.querySelector("input[name=backend]:checked");
  if (b) c.backend = b.value;
  const sm = document.querySelector("input[name=source_mode]:checked");
  if (sm) c.source_mode = sm.value;
  const key = $("gemini_key").value.trim();
  if (key) c.gemini_key = key;
  return c;
}

async function saveConfig() {
  cfg = await api("/api/config", readConfig());
  fillConfig(cfg);
  addLocal(t("msg_saved"), "good");
  checkBrain();
}

// ---------------------------------------------------------------- brain --
async function checkBrain() {
  const pill = $("brainPill");
  pill.className = "pill"; pill.textContent = t("pill_checking");
  let st;
  try { st = await api("/api/brain"); } catch (e) { st = { state: "error", error: String(e) }; }
  brainSt = st;
  showBrain(st);
}

function showBrain(st) {
  const pill = $("brainPill"), dot = $("brainDot"), alert = $("brainAlert"), banner = $("banner");
  $("chipBrain").textContent = t("chip_brain", { b: st.label || "???" });
  let cls = "bad", pillKey = "pill_confused", msg = esc(st.error || st.state);
  const ai = linkHtml("https://aistudio.google.com/apikey", "aistudio.google.com/apikey");
  switch (st.state) {
    case "ready": cls = "ready"; pillKey = "pill_ready"; msg = ""; break;
    case "no_model":
      cls = "warn"; pillKey = "pill_no_model";
      msg = t("alert_no_model_html", { model: esc(st.model) }); break;
    case "no_ollama":
      pillKey = "pill_no_ollama";
      msg = st.installed ? esc(t("alert_ollama_sleep"))
        : t("alert_no_ollama_html", { link: linkHtml("https://ollama.com/download", "ollama.com/download") });
      if (st.installed) cls = "warn";
      break;
    case "no_key": pillKey = "pill_no_key"; msg = t("alert_no_key_html", { link: ai }); break;
    case "bad_key": pillKey = "pill_bad_key"; msg = esc(t("alert_bad_key", { err: st.error || "" })); break;
    case "bad_model": pillKey = "pill_bad_model"; msg = t("alert_bad_model_html", { model: esc(st.model) }); break;
  }
  pill.className = "pill " + cls; pill.textContent = t(pillKey);
  dot.className = "dot " + cls;
  alert.hidden = !msg; alert.innerHTML = msg;
  $("pullBtn").hidden = st.state !== "no_model";
  // banner on main page so nobody has to dig for it
  banner.hidden = !msg;
  banner.className = "banner " + (cls === "warn" ? "warn" : "");
  $("bannerTxt").innerHTML = `<b>${esc(t(pillKey))}.</b> ${msg}`;
}

// -------------------------------------------------------------- update --
function showUpdate(u) {
  const ban = $("updBanner");
  const busy = u.phase === "downloading" || u.phase === "installing";
  const show = busy || (u.phase === "error" && u.available) || (u.available && !u.skipped && !updLater);
  ban.hidden = !show;
  if (!show) return;
  ban.className = "banner upd" + (u.phase === "error" ? " err" : "");
  $("updBtns").hidden = busy;
  $("updBarWrap").hidden = u.phase !== "downloading";
  $("updBar").style.width = (u.pct || 0) + "%";
  if (u.phase === "downloading") $("updTxt").textContent = t("upd_downloading", { pct: u.pct || 0 });
  else if (u.phase === "installing") {
    $("updTxt").textContent = t("upd_installing");
    setTimeout(() => { try { window.close(); } catch (e) {} }, 5000);
  } else if (u.phase === "error") $("updTxt").textContent = t("upd_failed", { err: u.error });
  else $("updTxt").innerHTML = t("upd_banner_html", { latest: esc(u.latest), current: esc("v" + u.current) });
}
$("updNow").onclick = async () => {
  if (upd && !upd.can_install) { $("updMsg").textContent = t("upd_source"); return; }
  upd = await api("/api/update/install", {});
  showUpdate(upd);
};
$("updLater").onclick = () => { updLater = true; $("updBanner").hidden = true; };
$("updSkip").onclick = async () => { upd = await api("/api/update/skip", {}); showUpdate(upd); };
$("updCheck").onclick = async () => {
  $("updMsg").textContent = t("upd_checking");
  try { upd = await api("/api/update/check", {}); } catch (e) { upd = { phase: "error", error: String(e) }; }
  updLater = false;
  if (upd.phase === "none") $("updMsg").textContent = t("upd_none");
  else if (upd.phase === "error") $("updMsg").textContent = t("upd_error", { err: upd.error });
  else if (upd.available) {
    $("updMsg").textContent = upd.can_install ? "" : t("upd_source");
    if (upd.skipped) upd.skipped = false;   // manual check shows it again
  }
  showUpdate(upd);
};

// ------------------------------------------------------------- drawers --
function openDrawer(id) {
  closeDrawers();
  $(id).hidden = false; $("scrim").hidden = false;
}
function closeDrawers() {
  ["brainDrawer", "langDrawer"].forEach((d) => { $(d).hidden = true; });
  $("scrim").hidden = true;
}
$("brainBtn").onclick = () => openDrawer("brainDrawer");
$("bannerFix").onclick = () => openDrawer("brainDrawer");
$("langBtn").onclick = () => openDrawer("langDrawer");
$("scrim").onclick = closeDrawers;
document.querySelectorAll("[data-close]").forEach((b) => { b.onclick = closeDrawers; });

// ------------------------------------------------------------------ run --
async function go() {
  if (running) {
    if (stopping) return;                      // already asked; don't spam
    stopping = true;
    $("goBtn").textContent = t("stopping_btn"); $("goBtn").disabled = true;
    await api("/api/stop", {}); addLocal(t("msg_stopping"), "warn"); return;
  }
  const query = $("query").value.trim();
  const links = $("links").value.trim();
  const count = parseInt($("count").value, 10) || 10;
  if (!query && !links) { addLocal(t("msg_no_input"), "bad"); $("query").focus(); return; }
  try { localStorage.setItem("goon.query", query); localStorage.setItem("goon.count", count); } catch (e) {}
  await api("/api/config", readConfig());
  const r = await api("/api/start", { query, links, count });
  if (!r.ok) addLocal(t("msg_already"), "warn");
}

let stopping = false;
function setRunning(on) {
  running = on;
  if (!on) { stopping = false; $("goBtn").disabled = false; }
  if (on && stopping) return;                 // keep showing "stopping..." until it really stops
  const b = $("goBtn");
  b.textContent = t(on ? "stop" : "go");
  b.classList.toggle("stop", on);
  $("pullBtn").disabled = on;
}

const STEP_KEYS = {
  "": "step_idle", searching: "step_searching", downloading: "step_downloading",
  "checking dupes": "step_dupes", looking: "step_looking", listening: "step_listening",
  judging: "step_judging", "downloading brain": "step_pull", "waking brain": "step_wake",
  tools: "step_tools",
};

// ---------------------------------------------------------------- tools --
let toolsSt = null;
function showTools(ts) {
  toolsSt = ts;
  const ban = $("toolsBanner");
  const names = ["ffmpeg", "deno", "yt-dlp", "whisper", "model"];
  const busy = names.filter((n) => ts[n] && ts[n].state === "downloading");
  const errs = names.filter((n) => ts[n] && ts[n].state === "error");
  const missing = !ts.core_ready;
  ban.hidden = !(busy.length || errs.length || missing);
  if (ban.hidden) return;
  ban.classList.toggle("err", !!errs.length && !busy.length);
  $("toolsTxt").textContent = errs.length && !busy.length
    ? t("tools_error", { err: errs.map((n) => `${n}: ${ts[n].error}`).join("; ") })
    : t("tools_setup");
  $("toolsRetry").hidden = !(errs.length && !busy.length);
  $("toolBars").innerHTML = names.filter((n) => ts[n] && (ts[n].state === "downloading" || (missing && n !== "whisper" && n !== "model")))
    .map((n) => `<div class="toolbar"><span>${esc(n)} ${ts[n].state === "downloading" ? ts[n].pct + "%" : ts[n].state === "ok" ? "✓" : "…"}</span>
      <div class="bar"><i style="width:${ts[n].state === "ok" ? 100 : ts[n].pct || 0}%"></i></div></div>`).join("");
}
$("toolsRetry").onclick = async () => showTools(await api("/api/tools/retry", {}));

async function pollLoop() {
  await poll();
  const busy = running || (upd && (upd.phase === "downloading" || upd.phase === "installing")) ||
    (toolsSt && toolsSt.busy);
  setTimeout(pollLoop, busy ? 1000 : 3000);
}

async function poll() {
  let s;
  try { s = await api("/api/status?since=" + lastLog); } catch (e) { return; }
  const was = running;
  setRunning(s.running);
  const p = s.progress;
  $("prog").hidden = !s.running && !p.kept;
  $("progStep").textContent = t(STEP_KEYS[p.step] || "step_idle");
  $("progCount").textContent = t("prog_count", { k: p.kept, n: p.target });
  const pct = p.step === "downloading brain" && p.pct != null ? p.pct : (p.target ? (100 * p.kept) / p.target : 0);
  $("progBar").style.width = Math.min(100, pct) + "%";
  $("progTitle").textContent = p.title || "";
  if (s.brain) $("chipBrain").textContent = t("chip_brain", { b: s.brain });
  if (s.update) { upd = s.update; showUpdate(upd); }
  if (s.tools) showTools(s.tools);

  let newRot = false;
  for (const l of s.log) {
    lastLog = Math.max(lastLog, l.i);
    addLine(l.text, l.kind, l.t);
    if (l.key === "keep") newRot = true;
  }
  if (newRot) loadVids();
  if (was && !s.running) { loadVids(); checkBrain(); }
}

function addLine(text, kind, tm) {
  const log = $("log");
  if (sleeping) { log.innerHTML = ""; sleeping = false; }
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  const li = document.createElement("li");
  li.className = "k-" + (kind || "info");
  const d = tm ? new Date(tm * 1000) : new Date();
  li.innerHTML = `<time>${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>${esc(text)}`;
  log.appendChild(li);
  while (log.children.length > 400) log.removeChild(log.firstChild);
  if (nearBottom) log.scrollTop = log.scrollHeight;
}
const addLocal = (text, kind) => addLine(text, kind);

// ----------------------------------------------------------------- cave --
async function loadVids() {
  try { vids = await api("/api/vids?sort=" + $("sort").value); } catch (e) { return; }
  renderVids();
  try { const h = await api("/api/hello"); stats = h.stats; showStats(stats); } catch (e) {}
}

function renderVids() {
  const cave = $("cave");
  if (!vids.length) { cave.innerHTML = `<p class="empty">${esc(t("empty"))}</p>`; return; }
  cave.innerHTML = vids.map((v, i) => `
    <article class="vcard" data-i="${i}">
      <div class="thumb" data-act="doom">
        ${v.has_thumb ? `<img loading="lazy" src="/vid/${v.id}/thumb" alt="">` : `<div class="noimg">🧠</div>`}
        <span class="lvl l${v.score}">${esc(t("lvl", { s: v.score }))}</span>
        <span class="site site-${esc(v.site)}">${esc({ tiktok: "TikTok", instagram: "Insta", youtube: "YouTube" }[v.site] || v.site)}</span>
        <span class="play">▶</span>
      </div>
      <div class="vbody">
        <div class="vtitle" title="${esc(v.title)}">${esc(v.title || t("untitled"))}</div>
        <div class="vvibe">${esc(v.vibe)}</div>
        <div class="vwhy">"${esc(v.why)}"</div>
        <div class="vbtns">
          <button type="button" data-act="show" title="${esc(t("show_title"))}">📂</button>
          <button type="button" data-act="src" title="${esc(t("src_title"))}">🔗</button>
          <button type="button" data-act="yeet" class="yeet">${esc(t("yeet"))}</button>
        </div>
      </div>
    </article>`).join("");
}

$("cave").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  const card = e.target.closest(".vcard");
  if (!btn || !card) return;
  const v = vids[+card.dataset.i];
  const act = btn.dataset.act;
  if (act === "doom") openDoom(+card.dataset.i);
  else if (act === "show") api(`/vid/${v.id}/show`, {});
  else if (act === "src") api("/api/open_link", { url: v.url });
  else if (act === "yeet") {
    card.style.opacity = ".3";
    await api(`/vid/${v.id}/yeet`, {});
    addLocal(t("msg_yeeted", { title: v.title }), "warn");
    loadVids();
  }
});

// ----------------------------------------------------------- doomscroll --
let doomI = 0;
function openDoom(i = 0) {
  if (!vids.length) { addLocal(t("msg_no_doom"), "warn"); return; }
  doomI = Math.max(0, Math.min(i, vids.length - 1));
  $("doom").hidden = false;
  showDoom();
}
function showDoom() {
  const v = vids[doomI];
  const vid = $("doomVid");
  vid.src = `/vid/${v.id}/file`;
  vid.play().catch(() => {});
  const lvl = $("doomLvl");
  lvl.textContent = t("lvl", { s: v.score });
  lvl.className = `lvl l${v.score}`;
  $("doomTitle").textContent = v.title || t("untitled");
  $("doomWhy").textContent = `"${v.why}"`;
}
function doomMove(d) {
  if (!vids.length) return;
  doomI = (doomI + d + vids.length) % vids.length;
  showDoom();
}
function closeDoom() {
  const vid = $("doomVid");
  vid.pause(); vid.removeAttribute("src"); vid.load();
  $("doom").hidden = true;
}
let wheelLock = 0;
$("doom").addEventListener("wheel", (e) => {
  e.preventDefault();
  const now = Date.now();
  if (now - wheelLock < 450 || Math.abs(e.deltaY) < 10) return;
  wheelLock = now;
  doomMove(e.deltaY > 0 ? 1 : -1);
}, { passive: false });
document.addEventListener("keydown", (e) => {
  if (!$("war").hidden) { if (e.key === "Escape") $("warSkip").click(); else if (warNext) warNext(); return; }
  if (e.key === "Escape" && !$("doom").hidden) return closeDoom();
  if (e.key === "Escape") return closeDrawers();
  if ($("doom").hidden) return;
  if (e.key === "ArrowDown" || e.key === "j") doomMove(1);
  else if (e.key === "ArrowUp" || e.key === "k") doomMove(-1);
  else if (e.key === " ") { e.preventDefault(); const v = $("doomVid"); v.paused ? v.play() : v.pause(); }
});
$("doomX").onclick = closeDoom;
$("doomUp").onclick = () => doomMove(-1);
$("doomDown").onclick = () => doomMove(1);
$("doomVid").onclick = (e) => { const v = e.target; v.paused ? v.play() : v.pause(); };

// ---------------------------------------------------------------- wires --
$("goBtn").onclick = go;
$("query").addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
$("linksToggle").onclick = () => {
  const box = $("linksBox");
  box.hidden = !box.hidden;
  $("linksPlus").textContent = box.hidden ? "+" : "−";
  $("linksToggle").setAttribute("aria-expanded", String(!box.hidden));
  if (!box.hidden) $("links").focus();
};
$("saveBtn").onclick = () => saveConfig();
$("clearKey").onclick = async () => {
  cfg = await api("/api/config", { gemini_key_clear: true });
  fillConfig(cfg); addLocal(t("msg_key_forgot"), "warn"); checkBrain();
};
$("pullBtn").onclick = async () => { await api("/api/config", readConfig()); await api("/api/brain/pull", {}); };
$("threshold").oninput = (e) => showThreshold(e.target.value);
document.querySelectorAll("input[name=backend]").forEach((r) => { r.onchange = showPlaceGroups; });
$("sort").onchange = loadVids;
$("caveBtn").onclick = () => api("/api/open_cave", {});
$("doomBtn").onclick = () => openDoom(0);
$("clearLog").onclick = () => { $("log").innerHTML = ""; };

// ---- cookies.txt (login for tiktok / insta)
function showCookies(st) {
  const el = $("cookieStatus");
  el.textContent = st.bad ? t("cookies_bad") : st.loaded ? t("cookies_loaded", { sites: st.sites.join(", ") || "?" }) : t("cookies_empty");
  el.className = "cookie-status " + (st.bad ? "bad" : st.loaded ? "good" : "");
}
async function loadCookies() { try { showCookies(await api("/api/cookies")); } catch (e) {} }
$("cookieFile").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const r = await fetch("/api/cookies", { method: "POST", body: await f.text(), headers: { "Content-Type": "text/plain" } });
  showCookies(await r.json()); e.target.value = "";
};
$("cookieClear").onclick = async () => showCookies(await api("/api/cookies/clear", {}));
loadCookies();
$("copyLog").onclick = async () => {
  const text = [...$("log").querySelectorAll("li")].map((li) => li.textContent).join("\n");
  try { await navigator.clipboard.writeText(text); }
  catch (e) {   // older webviews: fall back to a hidden textarea
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
    ta.select(); document.execCommand("copy"); ta.remove();
  }
  addLocal(t("msg_copied"), "good");
};
$("logToggle").onclick = () => {
  logBig = !logBig;
  $("log").classList.toggle("small", !logBig);
  $("logToggle").textContent = t(logBig ? "log_less" : "log_more");
  $("log").scrollTop = $("log").scrollHeight;
};
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (a) { e.preventDefault(); api("/api/open_link", { url: a.dataset.link }); }
});

boot().catch((e) => addLocal(t("msg_boot_crash", { err: String(e) }), "bad"));
