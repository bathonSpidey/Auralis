"use strict";

/* ── tiny helpers ─────────────────────────────────────────────────────── */
const $ = (selector, root = document) => root.querySelector(selector);

// Builds DOM without innerHTML, so playlist names and prompts can never inject markup.
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  const add = (kid) => {
    if (kid == null || kid === false) return;
    if (Array.isArray(kid)) kid.forEach(add);
    else el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  };
  kids.forEach(add);
  return el;
}

function icon(name) {
  const paths = {
    up: "M7 10v10H3V10h4zm2 10V10l4-7a2 2 0 0 1 2 2v4h5a2 2 0 0 1 2 2.3l-1.3 7A2 2 0 0 1 18.7 20H9z",
    down: "M7 14V4H3v10h4zm2-10v10l4 7a2 2 0 0 0 2-2v-4h5a2 2 0 0 0 2-2.3l-1.3-7A2 2 0 0 0 18.7 4H9z",
    check: "M5 12.5l4.5 4.5L19 7.5",
    open: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
    x: "M6 6l12 12M18 6L6 18",
    swap: "M7 7h11l-3-3M17 17H6l3 3",
  };
  const stroked = ["check", "open", "x", "swap"].includes(name);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", paths[name]);
  if (stroked) {
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
  } else {
    path.setAttribute("fill", "currentColor");
  }
  svg.append(path);
  return svg;
}

async function api(path, { method = "GET", json } = {}) {
  const response = await fetch(path, {
    method,
    headers: json ? { "Content-Type": "application/json" } : {},
    body: json ? JSON.stringify(json) : undefined,
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || message;
    } catch (_) { /* keep the status text */ }
    throw new Error(message.replace(/^Value error, /, ""));
  }
  return response.status === 204 ? null : response.json();
}

const store = {
  get(key, fallback) {
    try { const raw = localStorage.getItem("auralis." + key); return raw == null ? fallback : JSON.parse(raw); }
    catch (_) { return fallback; }
  },
  set(key, value) { try { localStorage.setItem("auralis." + key, JSON.stringify(value)); } catch (_) { /* private mode */ } },
};

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ── content ──────────────────────────────────────────────────────────── */
const EXAMPLES = [
  "A one-hour focus session, instrumental but not boring",
  "80s Japanese city pop and its modern revival, 45 minutes",
  "Rainy Sunday cooking, something warm",
  "Road trip through the Alps, three hours",
];
const DEPTHS = {
  quick: { label: "Quick", level: 1, hint: "Uses your taste only. Fastest." },
  auto: { label: "Auto", level: 2, hint: "Searches the web only when the request needs it." },
  deep: { label: "Deep", level: 3, hint: "Thorough web research. Takes longer and finds more." },
};
const STEPS = {
  playlist: (depth) => [
    ["taste", "Reading your listening"],
    ["scout", "Scouting tracks" + (depth === "deep" ? " and researching the web" : depth === "auto" ? ", searching the web if needed" : "")],
    ["curate", "Curating and ordering"],
    ["finish", "Finishing up"],
  ],
  song: () => [["taste", "Reading your listening"], ["pick", "Choosing a song"], ["finish", "Finishing up"]],
  commit: () => [["create", "Creating it on Spotify"]],
};

/* ── state ────────────────────────────────────────────────────────────── */
const settings = Object.assign({ preview: true, device: "", depth: "auto", songWeb: false }, store.get("settings", {}));
const state = { tab: "create", jobId: store.get("job", null), job: null, poll: null, clock: null, historyOffset: 0 };
const saveSettings = () => store.set("settings", settings);

/* ── theme: the glow turns violet at night, as in the original app ────── */
function applyHour() {
  const hour = new Date().getHours();
  document.documentElement.dataset.hour = hour >= 6 && hour < 18 ? "day" : "night";
}

/* ── tabs ─────────────────────────────────────────────────────────────── */
function showTab(name) {
  if (!["create", "history", "taste"].includes(name)) name = "create";
  state.tab = name;
  for (const tab of document.querySelectorAll(".tab")) tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  for (const view of ["create", "history", "taste"]) $("#view-" + view).hidden = view !== name;
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  if (name === "history") loadHistory(true);
  if (name === "taste") loadTaste();
}

/* ── status + devices ─────────────────────────────────────────────────── */
async function refreshStatus() {
  const status = $("#status");
  try {
    const health = await api("/api/health");
    status.replaceChildren(
      ...[
        health.spotify === "ok"
          ? h("span", { class: "pill" }, h("span", { class: "dot ok" }), "Spotify connected")
          : h("span", { class: "pill" }, h("span", { class: "dot bad" }), "Spotify needs login"),
        health.queued > 0 && h("span", { class: "pill" }, `${health.queued} waiting`),
      ].filter(Boolean),
    );
  } catch (_) {
    status.replaceChildren(h("span", { class: "pill" }, h("span", { class: "dot bad" }), "Can't reach Auralis"));
  }
}

async function loadDevices() {
  const select = $("#device");
  try {
    const { devices } = await api("/api/devices");
    select.replaceChildren(
      h("option", { value: "" }, "Don't play, just create"),
      // Spotify only lists devices that are online; this one also covers the
      // device it remembers as the last one used.
      h("option", { value: "current" }, "Where I'm listening (playing now, or last used)"),
      ...devices.map((d) => h("option", { value: d.id }, d.name + (d.is_active ? " (active now)" : ""))),
    );
    const known = settings.device === "current" || devices.some((d) => d.id === settings.device);
    select.value = known ? settings.device : "";
  } catch (_) { /* the list is optional */ }
}

/* ── composer ─────────────────────────────────────────────────────────── */
function renderDepth() {
  const group = $("#depth");
  group.replaceChildren(
    ...Object.entries(DEPTHS).map(([key, d]) =>
      h(
        "button",
        {
          type: "button", role: "radio", "aria-checked": String(settings.depth === key),
          onclick: () => { settings.depth = key; saveSettings(); renderDepth(); },
        },
        h("span", { class: "bars", "aria-hidden": "true" }, [1, 2, 3].map((n) => h("i", { class: n <= d.level ? "on" : "" }))),
        d.label,
      ),
    ),
  );
  $("#depth-hint").textContent = DEPTHS[settings.depth].hint;
}

function buildComposer() {
  $("#examples").replaceChildren(
    ...EXAMPLES.map((text) => h("button", { type: "button", class: "chip", onclick: () => { $("#prompt").value = text; $("#prompt").focus(); } }, text)),
  );
  renderDepth();
  $("#preview").checked = settings.preview;
  $("#preview").addEventListener("change", (e) => { settings.preview = e.target.checked; saveSettings(); });
  $("#device").addEventListener("change", (e) => { settings.device = e.target.value; saveSettings(); });
  $("#song-web").checked = settings.songWeb;
  $("#song-web").addEventListener("change", (e) => { settings.songWeb = e.target.checked; saveSettings(); });
  $("#playlist-form").addEventListener("submit", (e) => { e.preventDefault(); submitPlaylist(); });
  $("#prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submitPlaylist(); } });
  $("#go-song").addEventListener("click", submitSong);
}

function common() {
  return { preview: settings.preview, device_id: settings.device || null };
}

async function submitPlaylist() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) { toast("Describe the playlist you want first."); $("#prompt").focus(); return; }
  await startJob({ kind: "playlist", prompt, depth: settings.depth, ...common() });
}

async function submitSong() {
  await startJob({ kind: "song", depth: settings.songWeb ? "auto" : "quick", ...common() });
}

async function startJob(payload) {
  try {
    const job = await api("/api/jobs", { method: "POST", json: payload });
    watch(job.id);
  } catch (error) { toast(error.message); }
}

/* ── watching a job ───────────────────────────────────────────────────── */
function watch(id) {
  state.jobId = id;
  store.set("job", id);
  clearTimeout(state.poll);
  poll();
}

async function poll() {
  let job;
  try { job = await api("/api/jobs/" + state.jobId); }
  catch (_) { forget(); return; }
  state.job = job;
  renderWork(job);
  const active = job.status === "queued" || job.status === "running";
  document.body.classList.toggle("busy", active);
  if (active) state.poll = setTimeout(poll, 1500);
  else { refreshStatus(); loadRecent(); }
}

function forget() {
  clearTimeout(state.poll);
  clearInterval(state.clock);
  state.jobId = null;
  state.job = null;
  store.set("job", null);
  document.body.classList.remove("busy");
  $("#work").hidden = true;
  $("#composer").hidden = false;
}

function elapsed(job) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - job.created_at));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function renderWork(job) {
  $("#composer").hidden = true;
  $("#work").hidden = false;
  clearInterval(state.clock);
  if (job.status === "failed") return $("#work").replaceChildren(errorPanel(job));
  if (job.status === "done") return $("#work").replaceChildren(resultPanel(job));
  const panel = progressPanel(job);
  $("#work").replaceChildren(panel);
  state.clock = setInterval(() => { const t = $(".timer"); if (t) t.textContent = elapsed(job); }, 1000);
}

function progressPanel(job) {
  const steps = STEPS[job.kind](job.depth);
  const activeIndex = steps.findIndex(([key]) => key === job.stage);
  const waiting = job.status === "queued";
  const title = job.kind === "playlist" ? job.prompt : job.kind === "song" ? "Song of the moment" : "Creating your playlist";
  return h(
    "div",
    { class: "card working" },
    h("div", { class: "working-head" },
      h("div", {}, h("div", { class: "eyebrow" }, waiting ? "Waiting in line" : "Working"), h("h2", { style: "margin-top:.5rem" }, title)),
      h("div", { class: "timer", "aria-label": "Time elapsed" }, elapsed(job)),
    ),
    h("ul", { class: "steps" },
      steps.map(([key, label], index) => {
        const done = !waiting && index < activeIndex;
        const active = !waiting && index === activeIndex;
        return h("li", { class: "step" + (done ? " done" : active ? " active" : ""), "aria-current": active ? "step" : null },
          h("span", { class: "mark" },
            done ? h("span", { class: "tick" }, icon("check")) : active ? h("span", { class: "eq", "aria-hidden": "true" }, h("i"), h("i"), h("i"), h("i")) : h("span", { class: "idle" })),
          label);
      }),
    ),
    h("p", { class: "note" }, waiting
      ? "Another run is in progress. Yours starts as soon as it finishes."
      : "This usually takes one to three minutes. It runs on the Pi, so you can close this page and come back."),
  );
}

function errorPanel(job) {
  return h("div", { class: "card error working" },
    h("div", {}, h("div", { class: "eyebrow" }, "That didn't work"), h("h2", { style: "margin-top:.5rem" }, "Something went wrong")),
    h("p", { class: "reason", style: "margin:0" }, job.error || "Unknown error."),
    h("div", { class: "actions", style: "margin-top:0" }, h("button", { class: "btn", type: "button", onclick: forget }, "Back")),
  );
}

/* ── results ──────────────────────────────────────────────────────────── */
function spotifyTrackUrl(uri) { return "https://open.spotify.com/track/" + uri.split(":").pop(); }

function playbackLabel(outcome) {
  if (outcome.dry_run) return "Not created yet";
  return { playing: "Playing now", queued: "Added to your queue", none: "Created, not played" }[outcome.playback];
}

function trackList(tracks, { suggestionId = null, ratings = {} } = {}) {
  return h("ol", { class: "tracks" },
    tracks.map((track, index) => {
      const rating = ratings[track.uri] ?? track.rating ?? null;
      const canRate = suggestionId != null;
      const row = h("li", { class: "track-row" },
        h("span", { class: "n" }, String(index + 1).padStart(2, "0")),
        h("div", { class: "t" },
          h("a", { href: spotifyTrackUrl(track.uri), target: "_blank", rel: "noopener" }, track.title),
          h("span", { class: "by" }, [track.artist, track.album].filter(Boolean).join(" · ")),
        ),
        h("span", { class: "yr" }, track.year || ""),
        rateButtons(track.uri, rating, canRate, suggestionId),
      );
      return row;
    }),
  );
}

function rateButtons(uri, current, enabled, suggestionId) {
  const make = (kind, label) =>
    h("button", {
      type: "button", class: kind, "aria-pressed": String(current === kind), disabled: !enabled,
      title: enabled ? label : "You can rate songs once the playlist is created",
      "aria-label": label,
    }, icon(kind === "like" ? "up" : "down"));
  const like = make("like", "Like this song"), dislike = make("dislike", "Dislike this song");
  const apply = (value) => {
    like.setAttribute("aria-pressed", String(value === "like"));
    dislike.setAttribute("aria-pressed", String(value === "dislike"));
  };
  for (const [button, kind] of [[like, "like"], [dislike, "dislike"]]) {
    button.addEventListener("click", async () => {
      const next = button.getAttribute("aria-pressed") === "true" ? null : kind;
      try {
        await api("/api/ratings", { method: "PUT", json: { suggestion_id: suggestionId, uri, rating: next } });
        apply(next);
        toast(next === "like" ? "Liked. Future picks will lean this way." : next === "dislike" ? "Disliked. Future picks will steer away." : "Back to neutral.");
      } catch (error) { toast(error.message); }
    });
  }
  return h("span", { class: "rate" }, like, dislike);
}

function resultPanel(job) {
  const { kind, outcome } = job.result;
  const isSong = kind === "song";
  const tracks = isSong ? [outcome.track] : outcome.tracks;
  const title = isSong ? outcome.track.title : outcome.name;
  const preview = outcome.dry_run;
  const parentJob = job;
  return h("div", { class: "card sleeve" },
    preview && h("div", { class: "banner" },
      h("span", {}, h("strong", {}, "Preview. "), isSong ? "Nothing has been played or saved yet." : "Nothing has been created in Spotify yet."),
      h("span", { class: "actions", style: "margin:0" },
        h("button", { class: "btn primary small", type: "button", onclick: () => createFromPreview(parentJob) }, isSong ? "Play it and save it" : "Create this playlist"),
        h("button", { class: "btn quiet small", type: "button", onclick: () => discard(parentJob) }, "Discard"),
      ),
    ),
    h("div", {},
      h("div", { class: "eyebrow" }, isSong ? "Song of the moment" : "Playlist"),
      h("h2", { class: "title", style: "margin-top:.6rem" }, title),
      isSong && h("p", { class: "reason", style: "margin-top:.3rem;font-weight:500;color:var(--fg)" }, outcome.track.artist),
      h("p", { class: "reason" }, outcome.reason),
    ),
    h("div", { class: "meta" },
      h("span", { class: "pill" }, `${tracks.length} ${tracks.length === 1 ? "track" : "tracks"}`),
      h("span", { class: "pill" }, `${job.depth} research`),
      h("span", { class: "pill" }, playbackLabel(outcome)),
      outcome.playlist_url && h("a", { class: "link", href: outcome.playlist_url, target: "_blank", rel: "noopener" }, "Open in Spotify"),
    ),
    outcome.research && h("details", { class: "how" }, h("summary", {}, "How Auralis looked"), h("p", {}, outcome.research)),
    trackList(tracks, { suggestionId: preview ? null : outcome.id }),
    h("div", { class: "actions", style: "margin:0" }, h("button", { class: "btn", type: "button", onclick: forget }, "Make another")),
  );
}

async function createFromPreview(job) {
  try {
    const next = await api(`/api/jobs/${job.id}/create` + (settings.device ? `?device_id=${encodeURIComponent(settings.device)}` : ""), { method: "POST" });
    watch(next.id);
  } catch (error) { toast(error.message); }
}

async function discard(job) {
  try { await api("/api/jobs/" + job.id, { method: "DELETE" }); } catch (_) { /* already gone */ }
  forget();
}

/* ── history ──────────────────────────────────────────────────────────── */
const PAGE = 15;

function when(epoch) {
  const date = new Date(epoch * 1000), now = new Date();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const days = Math.round((new Date(now.toDateString()) - new Date(date.toDateString())) / 86400000);
  if (days === 0) return "Today " + time;
  if (days === 1) return "Yesterday " + time;
  return date.toLocaleDateString([], { day: "numeric", month: "short", year: date.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

function entryCard(entry) {
  const isSong = entry.kind === "song";
  return h("details", { class: "entry" },
    h("summary", {},
      h("span", { class: "name" }, entry.name || "Untitled"),
      h("span", { class: "when" },
        h("span", { class: "pill" }, isSong ? "song" : `${entry.tracks.length} tracks`),
        h("span", { class: "pill" }, entry.depth),
        h("span", { class: "pill" }, entry.source),
        h("span", { class: "mono muted", style: "font-size:.78rem" }, when(entry.created_at)),
      ),
      h("span", { class: "prompt" }, entry.prompt || "Song of the moment"),
    ),
    h("div", { class: "body" },
      h("p", { class: "reason", style: "margin:0" }, entry.reason),
      entry.playlist_url && h("a", { class: "link", href: entry.playlist_url, target: "_blank", rel: "noopener" }, "Open in Spotify"),
      trackList(entry.tracks, { suggestionId: entry.id }),
    ),
  );
}

async function loadHistory(reset) {
  if (reset) state.historyOffset = 0;
  const list = $("#entries");
  try {
    const { items } = await api(`/api/history?limit=${PAGE}&offset=${state.historyOffset}`);
    if (reset) list.replaceChildren();
    if (reset && !items.length) {
      list.replaceChildren(h("div", { class: "empty-big" }, h("h2", {}, "Nothing here yet"), h("p", {}, "Playlists and songs you create will show up here, with their reasons and ratings.")));
    }
    items.forEach((entry) => list.append(entryCard(entry)));
    state.historyOffset += items.length;
    $("#more").hidden = items.length < PAGE;
  } catch (error) { toast(error.message); }
}

async function loadRecent() {
  try {
    const { items } = await api("/api/history?limit=3");
    const box = $("#recent");
    box.replaceChildren(
      ...(items.length
        ? [
            h("div", { class: "eyebrow" }, "Recently made"),
            ...items.map((entry) =>
              h("a", { class: "recent-row", href: "#history" },
                h("span", { class: "name" }, entry.name || "Untitled"),
                h("span", { class: "mono muted" }, when(entry.created_at)))),
          ]
        : []),
    );
  } catch (_) { /* optional */ }
}

/* ── likes & dislikes ─────────────────────────────────────────────────── */
async function loadTaste() {
  try {
    const data = await api("/api/ratings");
    $("#taste").replaceChildren(
      tasteColumn("likes", "Leaning toward", "up", data.like, "dislike", "Rate songs with the thumbs in History or after creating a playlist. Liked songs tell Auralis which sound to lean toward."),
      tasteColumn("dislikes", "Steering away", "down", data.dislike, "like", "Nothing disliked. A dislike tells Auralis to steer away from songs like it, never to ban them."),
    );
  } catch (error) { toast(error.message); }
}

function tasteColumn(cls, title, iconName, rows, flipTo, emptyText) {
  const change = async (row, rating, message) => {
    try { await api("/api/ratings", { method: "PUT", json: { song_key: row.song_key, rating } }); toast(message); loadTaste(); }
    catch (error) { toast(error.message); }
  };
  return h("div", { class: `card taste-col ${cls}` },
    h("h2", {}, icon(iconName), title, h("span", { class: "count" }, rows.length)),
    rows.length
      ? h("ul", { class: "rows" }, rows.map((row) =>
          h("li", { class: "row" },
            h("div", { style: "min-width:0" }, h("div", { class: "name" }, row.title), h("div", { class: "by" }, row.artist)),
            h("div", { class: "row-actions" },
              h("button", { class: "btn quiet small", type: "button", title: flipTo === "like" ? "Move to likes" : "Move to dislikes", "aria-label": flipTo === "like" ? "Move to likes" : "Move to dislikes",
                onclick: () => change(row, flipTo, flipTo === "like" ? "Moved to likes." : "Moved to dislikes.") }, icon("swap")),
              h("button", { class: "btn quiet small", type: "button", title: "Back to neutral", "aria-label": "Back to neutral",
                onclick: () => change(row, null, "Back to neutral.") }, icon("x")),
            ),
          )))
      : h("p", { class: "empty" }, emptyText),
  );
}

/* ── boot ─────────────────────────────────────────────────────────────── */
async function boot() {
  applyHour();
  buildComposer();
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));
  $("#more").addEventListener("click", () => loadHistory(false));
  window.addEventListener("focus", () => { loadDevices(); refreshStatus(); });
  showTab(location.hash.slice(1) || "create");
  refreshStatus();
  loadDevices();
  loadRecent();
  setInterval(refreshStatus, 20000);

  // Resume a run that is still going (or the one we were looking at).
  try {
    const { jobs } = await api("/api/jobs");
    const active = jobs.find((j) => j.status === "queued" || j.status === "running");
    if (active) return watch(active.id);
    if (state.jobId && jobs.some((j) => j.id === state.jobId)) return watch(state.jobId);
  } catch (_) { /* start fresh */ }
  state.jobId = null;
  store.set("job", null);
}

boot();
