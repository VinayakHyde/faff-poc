// Faff POC frontend.
//
// Wires up: persona sidebar (GET /api/personas) → profile renderer
// (GET /api/personas/{slug}, marked.parse) → daily-input fixture preload
// (GET /api/personas/{slug}/fixtures/{date}) → SSE-streamed run
// (POST /api/personas/{slug}/run/stream) → trace nodes with per-agent
// filter toggles → final user-facing task cards.

import { CodeJar } from "https://cdn.jsdelivr.net/npm/codejar@3.7.0/codejar.min.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Per spec: filter dropdown lists every sub-agent + Orchestrator + Rubric.
// Plus messenger since it produces trace events too.
const AGENTS = [
  { slug: "calendar",     label: "Calendar"     },
  { slug: "email_triage", label: "Email"        },
  { slug: "food",         label: "Food"         },
  { slug: "travel",       label: "Travel"       },
  { slug: "finance",      label: "Bills"        },
  { slug: "dates",        label: "Dates"        },
  { slug: "shopping",     label: "Shopping"     },
  { slug: "todos",        label: "To-dos"       },
  { slug: "events",       label: "Events"       },
  { slug: "orchestrator", label: "Orchestrator" },
  { slug: "rubric",       label: "Rubric"       },
  { slug: "messenger",    label: "Messenger"    },
];

const state = {
  selected: null,
  activeTab: "profile",
  // Per-persona caches so switching tabs doesn't refetch.
  emailCache: new Map(),    // slug → messages[]
  calendarCache: new Map(), // slug → events[]
  goldenCache: new Map(),   // slug → { items, agents }
  // Per-persona run-panel "chat" state. Each entry owns its own stages
  // DOM subtree so SSE events keep streaming into a chat even while the
  // user is viewing a different persona; switching back just toggles
  // visibility on the existing DOM.
  runChats: new Map(),      // slug → { stagesEl, dailyInputText, runStatus, hasRun, running }
};

// ---- per-persona run-panel chat ----

// Lazy-create or return the chat container for this persona. The stages
// subtree stays attached even while the user views a different persona —
// a running SSE keeps writing to it; switching back just unhides it.
function ensureChat(slug) {
  let chat = state.runChats.get(slug);
  if (chat) return chat;
  const stagesEl = document.createElement("div");
  stagesEl.className = "trace-stages";
  stagesEl.dataset.slug = slug;
  stagesEl.hidden = true;
  document.getElementById("run-output").appendChild(stagesEl);
  chat = { slug, stagesEl, dailyInputText: "", runStatus: "", hasRun: false, running: false };
  state.runChats.set(slug, chat);
  return chat;
}

function setActiveChat(slug) {
  for (const chat of state.runChats.values()) {
    chat.stagesEl.hidden = chat.slug !== slug || !chat.hasRun;
  }
}

// Returns the body of stage `no` within `chat`'s stages subtree.
function chatStageBody(chat, no) {
  return chat.stagesEl.querySelector(`.stage-body[data-stage-no="${no}"]`);
}

// Update the action-bar chrome (Simulate button + status text) to reflect
// whichever persona is currently visible.
function syncRunPanelChrome() {
  const chat = state.selected ? state.runChats.get(state.selected) : null;
  const btn = document.getElementById("run-btn");
  const status = document.getElementById("run-status");
  if (!btn || !status) return;
  if (!chat) {
    btn.disabled = true;
    status.textContent = "";
    return;
  }
  btn.disabled = chat.running;
  status.textContent = chat.runStatus;
}

// ---- sidebar resize constants (must be declared before init() IIFE) ----

const SIDEBAR_KEY = "sidebarWidthPx";
const COMPACT_THRESHOLD = 140; // px below which we collapse to icon-only

// ---- bootstrap ----

let jsonEditor = null;

(async function init() {
  // Preview pages (e.g. trace-preview.html) import this module purely
  // to get the trace renderers — they don't have the full app shell.
  // Detect that and skip the bootstrap so the import side-effect is safe.
  if (!document.getElementById("run-btn")) return;
  initSidebarResize();
  initJsonEditor();
  buildFilterBar();
  initTabs();
  initStickyActionBar();
  initEvalsToggle();
  await loadPersonas();
  $("#run-btn").addEventListener("click", runStream);
})();

// Toggle .is-stuck on the action-bar when it pins to the top of the run-panel
// scroll. Uses the classic IntersectionObserver "shrink root by 1px" trick.
function initStickyActionBar() {
  const bar = document.getElementById("action-bar");
  const panel = document.querySelector(".run-panel");
  if (!bar || !panel || !("IntersectionObserver" in window)) return;
  const obs = new IntersectionObserver(
    ([entry]) => bar.classList.toggle("is-stuck", entry.intersectionRatio < 1),
    { root: panel, threshold: [1], rootMargin: "-1px 0px 0px 0px" }
  );
  obs.observe(bar);
}

// ---- JSON editor (CodeJar + Prism) ----

function initJsonEditor() {
  const el = document.getElementById("daily-input-editor");
  if (!el || !window.Prism) {
    console.warn("Prism not loaded; daily-input editor will be plain text.");
    return;
  }
  jsonEditor = CodeJar(
    el,
    (editor) => Prism.highlightElement(editor),
    { tab: "  ", indentOn: /[\[{]$/ }
  );
}

function getDailyInputRaw() {
  if (jsonEditor) return jsonEditor.toString();
  const el = document.getElementById("daily-input-editor");
  return el ? el.textContent : "";
}

function setDailyInput(text) {
  if (jsonEditor) {
    jsonEditor.updateCode(text);
  } else {
    const el = document.getElementById("daily-input-editor");
    if (el) el.textContent = text;
  }
}

function initSidebarResize() {
  // Restore saved width.
  const saved = parseInt(localStorage.getItem(SIDEBAR_KEY) || "");
  if (saved && saved > 40) setSidebarWidth(saved);
  else setSidebarWidth(240);

  const handle = $("#resize-sidebar");
  if (!handle) return;

  let dragging = false;
  let startX = 0;
  let startW = 0;

  const onMove = (e) => {
    if (!dragging) return;
    const delta = e.clientX - startX;
    setSidebarWidth(startW + delta);
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("dragging");
    document.body.classList.remove("resizing");
    const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w-resolved")) || 240;
    localStorage.setItem(SIDEBAR_KEY, String(cur));
  };

  handle.addEventListener("mousedown", (e) => {
    dragging = true;
    startX = e.clientX;
    startW = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-w-resolved")) || 240;
    handle.classList.add("dragging");
    document.body.classList.add("resizing");
    e.preventDefault();
  });
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

function setSidebarWidth(px) {
  const layout = document.querySelector(".layout");
  const min = parseInt(getComputedStyle(layout).getPropertyValue("--sidebar-min")) || 60;
  const max = parseInt(getComputedStyle(layout).getPropertyValue("--sidebar-max")) || 480;
  const clamped = Math.max(min, Math.min(max, px));
  layout.style.setProperty("--sidebar-w", clamped + "px");
  // Track resolved value so getComputedStyle.getPropertyValue picks it up cleanly.
  document.documentElement.style.setProperty("--sidebar-w-resolved", clamped + "px");
  // Toggle compact mode.
  $("#sidebar").classList.toggle("compact", clamped < COMPACT_THRESHOLD);
}

// ---- tabs ----

function initTabs() {
  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => selectTab(btn.dataset.tab));
  });
}

function selectTab(name) {
  state.activeTab = name;
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab-view").forEach((v) => { v.hidden = v.dataset.tab !== name; });
  if (!state.selected) return;
  if (name === "email") loadEmailTab(state.selected);
  if (name === "calendar") loadCalendarTab(state.selected);
  if (name === "golden") loadGoldenTab(state.selected);
}

// ---- persona sidebar ----

async function loadPersonas() {
  try {
    const personas = await fetchJSON("/api/personas");
    renderPersonaList(personas);
  } catch (err) {
    $("#persona-list").innerHTML = `<li class="persona-loading">failed to load: ${err.message}</li>`;
  }
}

function renderPersonaList(personas) {
  const list = $("#persona-list");
  list.innerHTML = "";
  for (const p of personas) {
    const li = document.createElement("li");
    li.dataset.slug = p.slug;

    const avatar = document.createElement("img");
    avatar.className = "avatar";
    // /assets/avatars/{Firstname}_arch.png — frontend-served
    const firstName = p.name.split(" ")[0];
    avatar.src = `/assets/avatars/${firstName}_arch.png`;
    avatar.onerror = () => { avatar.style.visibility = "hidden"; };
    avatar.alt = "";

    const text = document.createElement("div");
    text.innerHTML = `${p.name}<span class="meta-line">${p.neighbourhood}, ${p.city}</span>`;

    li.appendChild(avatar);
    li.appendChild(text);
    li.addEventListener("click", () => selectPersona(p.slug));
    list.appendChild(li);
  }
}

async function selectPersona(slug) {
  if (state.selected === slug) return;

  // Snapshot the outgoing persona's editor text so it survives the switch.
  if (state.selected) {
    const out = state.runChats.get(state.selected);
    if (out) out.dailyInputText = getDailyInputRaw();
  }

  state.selected = slug;
  document.body.classList.add("has-persona");
  $$(".persona-list li").forEach((li) => {
    li.classList.toggle("active", li.dataset.slug === slug);
  });

  // Reset to Profile tab + clear other tab views (they'll lazy-load when clicked).
  selectTab("profile");
  $("#tab-email").innerHTML = "";
  $("#tab-calendar").innerHTML = "";
  $("#tab-golden").innerHTML = "";

  // Create or surface this persona's chat (stages + running run, if any).
  const chat = ensureChat(slug);
  setActiveChat(slug);

  // Restore the persona's editor text, or load the fixture if none yet.
  await loadProfile(slug);
  if (chat.dailyInputText) {
    setDailyInput(chat.dailyInputText);
  } else {
    await loadFixtureIntoInput(slug);
    chat.dailyInputText = getDailyInputRaw();
  }

  syncRunPanelChrome();
}

// ---- profile panel ----

async function loadProfile(slug) {
  try {
    const profile = await fetchJSON(`/api/personas/${slug}`);
    $("#profile-empty").hidden = true;
    $("#profile-content-wrapper").hidden = false;

    const firstName = profile.meta.name.split(" ")[0];
    $("#profile-avatar").src = `/assets/avatars/${firstName}_arch.png`;
    $("#profile-avatar").onerror = function () { this.style.visibility = "hidden"; };
    $("#profile-name").textContent = profile.meta.name;
    $("#profile-meta").textContent =
      `${profile.meta.neighbourhood}, ${profile.meta.city}  ·  onboarded ${profile.meta.onboarded_at}`;

    $("#tab-profile").innerHTML = marked.parse(profile.markdown);
  } catch (err) {
    $("#profile-empty").hidden = false;
    $("#profile-content-wrapper").hidden = true;
    $("#profile-empty").textContent = `failed: ${err.message}`;
  }
}

async function loadFixtureIntoInput(slug) {
  try {
    const today = new Date().toISOString().slice(0, 10);
    let fixture;
    try {
      fixture = await fetchJSON(`/api/personas/${slug}/fixtures/${today}`);
    } catch {
      // fall back to listing available dates and grabbing the most recent.
      const idx = await fetchJSON(`/api/personas/${slug}/fixtures`);
      const dates = idx.available_dates || [];
      if (dates.length === 0) {
        setDailyInput("");
        return;
      }
      fixture = await fetchJSON(`/api/personas/${slug}/fixtures/${dates[dates.length - 1]}`);
    }
    setDailyInput(JSON.stringify(fixture, null, 2));
  } catch (err) {
    setDailyInput("");
  }
}

// ---- email tab ----

async function loadEmailTab(slug) {
  const wrap = $("#tab-email");
  if (state.emailCache.has(slug)) {
    renderEmailTab(state.emailCache.get(slug));
    return;
  }
  wrap.innerHTML = `<div class="email-empty">loading…</div>`;
  try {
    const r = await fetch(`/api/personas/${slug}/mailbox`);
    if (!r.ok) {
      wrap.innerHTML = `<div class="email-empty">No mailbox for this persona — they haven't granted Gmail access.</div>`;
      state.emailCache.set(slug, []);
      return;
    }
    const data = await r.json();
    const messages = data.messages || [];
    state.emailCache.set(slug, messages);
    renderEmailTab(messages);
  } catch (err) {
    wrap.innerHTML = `<div class="email-empty">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

function renderEmailTab(messages) {
  const wrap = $("#tab-email");
  if (!messages.length) {
    wrap.innerHTML = `<div class="email-empty">No emails yet — this persona is profile-only (no Gmail connected).</div>`;
    return;
  }
  const sorted = [...messages].sort((a, b) =>
    (b.received_at || "").localeCompare(a.received_at || ""),
  );

  wrap.innerHTML = "";
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = `Search ${sorted.length} emails…`;
  search.className = "email-search";
  wrap.appendChild(search);

  const list = document.createElement("div");
  wrap.appendChild(list);

  const cards = sorted.map((m) => buildEmailCard(m));
  cards.forEach((c) => list.appendChild(c));

  search.addEventListener("input", () => {
    const q = search.value.toLowerCase().trim();
    cards.forEach((c) => {
      c.style.display = !q || c.dataset.haystack.includes(q) ? "" : "none";
    });
  });
}

function buildEmailCard(m) {
  const card = document.createElement("div");
  card.className = "email-card";
  const haystack =
    `${m.from || ""} ${m.subject || ""} ${m.snippet || ""} ${m.body || ""}`.toLowerCase();
  card.dataset.haystack = haystack;

  const row = document.createElement("div");
  row.className = "email-row";

  const fromSubj = document.createElement("div");
  fromSubj.className = "email-from-subj";
  fromSubj.innerHTML = `
    <div class="email-from">${escapeHtml(m.from || "")}</div>
    <div class="email-subject">${escapeHtml(m.subject || "")}</div>
  `;

  const date = document.createElement("div");
  date.className = "email-date";
  date.textContent = (m.received_at || "").slice(0, 10);

  row.appendChild(fromSubj);
  row.appendChild(date);
  card.appendChild(row);

  const body = document.createElement("div");
  body.className = "email-body";
  body.textContent = m.body || m.snippet || "";
  card.appendChild(body);

  card.addEventListener("click", () => card.classList.toggle("expanded"));
  return card;
}

// ---- calendar tab ----

async function loadCalendarTab(slug) {
  const wrap = $("#tab-calendar");
  if (state.calendarCache.has(slug)) {
    renderCalendarTab(state.calendarCache.get(slug));
    return;
  }
  wrap.innerHTML = `<div class="calendar-empty">loading…</div>`;
  try {
    const r = await fetch(`/api/personas/${slug}/calendar`);
    if (!r.ok) {
      wrap.innerHTML = `<div class="calendar-empty">No calendar for this persona — they haven't granted Calendar access.</div>`;
      state.calendarCache.set(slug, []);
      return;
    }
    const data = await r.json();
    const events = data.events || [];
    state.calendarCache.set(slug, events);
    renderCalendarTab(events);
  } catch (err) {
    wrap.innerHTML = `<div class="calendar-empty">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

function renderCalendarTab(events) {
  const wrap = $("#tab-calendar");
  if (!events.length) {
    wrap.innerHTML = `<div class="calendar-empty">No calendar events yet — this persona is profile-only.</div>`;
    return;
  }
  wrap.innerHTML = "";

  // Group by date (YYYY-MM-DD).
  const byDay = new Map();
  const sorted = [...events].sort((a, b) =>
    String(a.start || "").localeCompare(String(b.start || ""))
  );
  for (const e of sorted) {
    const day = String(e.start || "").slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(e);
  }

  for (const [day, list] of byDay) {
    const dayEl = document.createElement("div");
    dayEl.className = "calendar-day";
    const header = document.createElement("div");
    header.className = "calendar-day-header";
    header.textContent = day || "(undated)";
    dayEl.appendChild(header);
    for (const e of list) {
      const ev = document.createElement("div");
      ev.className = "calendar-event" + (e.all_day ? " all-day" : "");
      const time = document.createElement("div");
      time.className = "calendar-time";
      const start = String(e.start || "");
      time.textContent = e.all_day || start.length <= 10 ? "all day" : start.slice(11, 16);
      const summary = document.createElement("div");
      summary.innerHTML = `<div class="calendar-summary">${escapeHtml(e.summary || "")}</div>`;
      if (e.location) {
        const loc = document.createElement("div");
        loc.className = "calendar-loc";
        loc.textContent = e.location;
        summary.appendChild(loc);
      }
      ev.appendChild(time);
      ev.appendChild(summary);
      dayEl.appendChild(ev);
    }
    wrap.appendChild(dayEl);
  }
}

// ---- golden tab ----

async function loadGoldenTab(slug) {
  const wrap = $("#tab-golden");
  if (state.goldenCache.has(slug)) {
    renderGoldenTab(state.goldenCache.get(slug));
    return;
  }
  wrap.innerHTML = `<div class="email-empty">loading golden set…</div>`;
  try {
    const r = await fetch(`/api/personas/${slug}/golden`);
    if (!r.ok) {
      wrap.innerHTML = `<div class="email-empty">no golden set found.</div>`;
      state.goldenCache.set(slug, { items: [], agents: [] });
      return;
    }
    const data = await r.json();
    state.goldenCache.set(slug, data);
    renderGoldenTab(data);
  } catch (err) {
    wrap.innerHTML = `<div class="email-empty">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

// Stable order for agent rows (mirrors the AGENTS list above + alphabetises anything else).
const AGENT_ORDER = AGENTS.map((a) => a.slug);

function renderGoldenTab(data) {
  const wrap = $("#tab-golden");
  const items = data.items || [];
  if (!items.length) {
    wrap.innerHTML = `<div class="email-empty">no golden set entries for this persona.</div>`;
    return;
  }

  // Sort: by agent (per AGENT_ORDER), then by kind (task → skip → pref_topic),
  // then by category, then by id. Stable order means consecutive same-agent
  // items naturally cluster into one merged block.
  const kindRank = { expected_task: 0, expected_skip: 1, expected_pref_topic: 2 };
  const agentRank = (a) => {
    const i = AGENT_ORDER.indexOf(a);
    return i === -1 ? 1000 : i;
  };
  const sorted = [...items].sort((a, b) => {
    if (agentRank(a.agent) !== agentRank(b.agent)) return agentRank(a.agent) - agentRank(b.agent);
    if ((kindRank[a.kind] ?? 99) !== (kindRank[b.kind] ?? 99)) return (kindRank[a.kind] ?? 99) - (kindRank[b.kind] ?? 99);
    return String(a.id || "").localeCompare(String(b.id || ""));
  });

  // Group consecutive same-agent items into one block.
  const blocks = [];
  for (const item of sorted) {
    const last = blocks[blocks.length - 1];
    if (last && last.agent === item.agent) {
      last.items.push(item);
      for (const eid of item.evidence_email_ids || []) last.evidenceSet.add(eid);
    } else {
      blocks.push({
        agent: item.agent,
        items: [item],
        evidenceSet: new Set(item.evidence_email_ids || []),
      });
    }
  }

  // Programmatic border-style cycling: when block N's evidence overlaps block
  // N-1's evidence, bump the style to the next in [solid, dashed, dotted].
  // Otherwise reset to solid.
  const STYLES = ["solid", "dashed", "dotted"];
  let styleIdx = 0;
  for (let i = 0; i < blocks.length; i++) {
    const prev = blocks[i - 1];
    if (prev && setsOverlap(prev.evidenceSet, blocks[i].evidenceSet)) {
      styleIdx = (styleIdx + 1) % STYLES.length;
    } else {
      styleIdx = 0;
    }
    blocks[i].borderStyle = STYLES[styleIdx];
  }

  // Detect identical-summary items between consecutive different-agent blocks
  // (covers "if multiple agent boxes are the exact same, space the text and
  // list the agents") — collapse them by tagging items with `mergedAgents`.
  const mergedKey = (it) => `${it.kind}|${(it.summary || "").trim()}`;
  for (let i = 1; i < blocks.length; i++) {
    const prev = blocks[i - 1];
    const cur = blocks[i];
    for (const item of [...cur.items]) {
      const key = mergedKey(item);
      const twin = prev.items.find((p) => mergedKey(p) === key && !p.mergedAgents);
      if (twin) {
        twin.mergedAgents = twin.mergedAgents || [twin._origAgent || prev.agent];
        twin.mergedAgents.push(cur.agent);
        cur.items = cur.items.filter((x) => x !== item);
      }
    }
  }

  // Render.
  wrap.innerHTML = `
    <div class="golden-summary">
      <span class="golden-stat"><b>${items.length}</b> total entries</span>
      <span class="golden-stat"><b>${data.agents.length}</b> agents</span>
      <span class="golden-stat"><b>${blocks.length}</b> blocks</span>
    </div>
    <div class="golden-blocks" id="golden-blocks"></div>
  `;
  const host = $("#golden-blocks");
  for (const block of blocks) {
    if (!block.items.length) continue; // entirely merged into a previous block
    host.appendChild(renderGoldenBlock(block));
  }
}

function renderGoldenBlock(block) {
  const el = document.createElement("div");
  el.className = `golden-block border-${block.borderStyle}`;
  el.dataset.agent = block.agent;
  el.style.setProperty("--block-color", `var(--c-${block.agent}, var(--accent))`);

  const head = document.createElement("div");
  head.className = "golden-block-head";
  head.innerHTML = `
    <span class="agent-tag ${block.agent}">${agentLabel(block.agent)}</span>
    <span class="golden-block-meta">${block.items.length} ${block.items.length === 1 ? "entry" : "entries"}</span>
  `;
  el.appendChild(head);

  const body = document.createElement("div");
  body.className = "golden-block-body";
  for (const item of block.items) {
    body.appendChild(renderGoldenItem(item, block.agent));
  }
  el.appendChild(body);
  return el;
}

function renderGoldenItem(item, primaryAgent) {
  const row = document.createElement("div");
  row.className = `golden-item kind-${item.kind}`;
  const kindLabels = {
    expected_task: "task",
    expected_skip: "skip",
    expected_pref_topic: "pref",
  };
  const agents = item.mergedAgents && item.mergedAgents.length > 1
    ? item.mergedAgents
    : null;

  let evidenceHtml = "";
  if (item.evidence_email_ids && item.evidence_email_ids.length) {
    evidenceHtml = `<div class="golden-evidence">${
      item.evidence_email_ids.map((id) => `<code>${escapeHtml(id)}</code>`).join(" ")
    }</div>`;
  }

  let chips = "";
  if (item.category) chips += `<span class="golden-chip">${escapeHtml(item.category)}</span>`;
  if (item.valid_until) chips += `<span class="golden-chip golden-chip-time">until ${escapeHtml(item.valid_until)}</span>`;

  let agentLabels = "";
  if (agents) {
    agentLabels = `<div class="golden-merged-agents">${
      agents.map((a) => `<span class="agent-tag ${a}" style="--block-color: var(--c-${a}, var(--accent))">${agentLabel(a)}</span>`).join("")
    }<span class="golden-merged-note">same expectation across these agents</span></div>`;
  }

  row.innerHTML = `
    <div class="golden-item-head">
      <span class="golden-kind kind-${item.kind}">${kindLabels[item.kind] || item.kind}</span>
      ${item.id ? `<code class="golden-id">${escapeHtml(item.id)}</code>` : ""}
      ${chips}
    </div>
    <div class="golden-summary-text">${escapeHtml(item.summary || "")}</div>
    ${evidenceHtml}
    ${agentLabels}
  `;
  return row;
}

function setsOverlap(a, b) {
  for (const x of a) if (b.has(x)) return true;
  return false;
}

function agentLabel(slug) {
  const a = AGENTS.find((x) => x.slug === slug);
  return a ? a.label : slug;
}

// ---- filter bar ----

function buildFilterBar() {
  const host = $("#filter-toggles");
  host.innerHTML = "";
  for (const a of AGENTS) {
    const row = document.createElement("label");
    row.className = "filter-row";
    row.dataset.agent = a.slug;
    row.innerHTML = `
      <input type="checkbox" data-agent="${a.slug}" checked />
      <span class="filter-swatch" style="background: var(--c-${a.slug});"></span>
      <span class="filter-row-label">${a.label}</span>
    `;
    row.querySelector("input").addEventListener("change", (e) => {
      const slug = e.target.dataset.agent;
      const on = e.target.checked;
      row.classList.toggle("off", !on);
      // Match both the primary agent (stage-1 nodes) AND the origin agent
      // (rubric/messenger nodes that surface a task originally produced
      // by this agent). Otherwise filtering Shopping would still show
      // shopping's rubric scores and shopping's drafted messages.
      $$(`.trace-node[data-agent="${slug}"], .trace-node[data-origin-agent="${slug}"]`)
        .forEach((n) => n.classList.toggle("hidden", !on));
      updateFilterCount();
    });
    host.appendChild(row);
  }

  const trigger = $("#filter-trigger");
  const popover = $("#filter-popover");
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    setFilterOpen(popover.hidden);
  });
  popover.addEventListener("click", (e) => e.stopPropagation());
  document.addEventListener("click", () => setFilterOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setFilterOpen(false);
  });

  $("#filter-all").addEventListener("click", () => bulkSetFilter(true));
  $("#filter-none").addEventListener("click", () => bulkSetFilter(false));

  updateFilterCount();
}

function setFilterOpen(open) {
  const popover = $("#filter-popover");
  const trigger = $("#filter-trigger");
  popover.hidden = !open;
  trigger.setAttribute("aria-expanded", String(open));
  trigger.classList.toggle("open", open);
  if (open) flipPopoverIfNeeded(trigger, popover);
}

// Flip the popover above the trigger when there isn't enough room below.
// We measure after un-hiding so getBoundingClientRect / scrollHeight are valid.
function flipPopoverIfNeeded(trigger, popover) {
  popover.classList.remove("open-up");
  const triggerRect = trigger.getBoundingClientRect();
  const spaceBelow = window.innerHeight - triggerRect.bottom;
  const spaceAbove = triggerRect.top;
  const popoverHeight = popover.scrollHeight;
  if (spaceBelow < popoverHeight + 12 && spaceAbove > spaceBelow) {
    popover.classList.add("open-up");
  }
}

function bulkSetFilter(on) {
  $$('#filter-toggles input[type="checkbox"]').forEach((cb) => {
    if (cb.checked === on) return;
    cb.checked = on;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function updateFilterCount() {
  const total = AGENTS.length;
  const active = $$('#filter-toggles input[type="checkbox"]:checked').length;
  const el = $("#filter-count");
  if (!el) return;
  el.textContent = active === total ? `${total}` : `${active}/${total}`;
  $("#filter-trigger").classList.toggle("filtered", active !== total);
}

// ---- run + SSE consumer ----

// The 7 rubric criteria (in canonical order) — mirrors backend/app/rubric.py
// so the frontend can render a hit/miss pill row even before the live event
// arrives carrying the criterion list.
const RUBRIC_CRITERIA = [
  "time_sensitive",
  "recurring_pattern_match",
  "concrete_action",
  "high_stakes_if_missed",
  "non_redundant",
  "matches_stated_preference",
  "well_justified_surface_time",
];

// Map every backend trace event type to the visual stage it belongs in.
// Stages are rendered in this fixed order regardless of backend emission
// order — preferences arrive mid-run from the orchestrator but read more
// naturally as a "post-agent, pre-rubric" step.
const STAGE_BY_TYPE = {
  orchestrator_started: 1,
  subagent_started: 1,
  tool_call: 1,
  tool_result: 1,
  llm_call: 1,
  subagent_returned: 1,
  dedup_decision: 1,
  preference_merged: 2,
  task_scored: 3,
  task_emitted: 3,
  task_filtered: 3,
  message_drafted: 4,
  // orchestrator_finished — intentionally unrouted; nothing to render
};

const STAGE_DEFS = [
  { no: 1, title: "Agent execution", subtitle: "9 sub-agents fan out in parallel" },
  { no: 2, title: "Preference updates", subtitle: "merged into the persona profile for future runs" },
  { no: 3, title: "Rubric scoring & filter", subtitle: "score 0–7, cutoff ≥4, per-agent cap of 2" },
  { no: 4, title: "LLM reframing", subtitle: "messenger turns each kept task into user-facing copy" },
  { no: 5, title: "Surfaced for the user", subtitle: "" },
];

async function runStream() {
  if (!state.selected) return;
  const slug = state.selected;
  const chat = ensureChat(slug);
  if (chat.running) return;

  // Snapshot the editor text into chat state and use it for the run.
  chat.dailyInputText = getDailyInputRaw();
  const inputRaw = chat.dailyInputText.trim();

  // Replace any prior run for this persona — single thread per chat.
  chat.running = true;
  chat.hasRun = true;
  chat.runStatus = "running…";
  initStages(chat);
  if (state.selected === slug) setActiveChat(slug);
  syncRunPanelChrome();

  const startedAt = performance.now();

  try {
    const body = inputRaw ? inputRaw : "null";
    const response = await fetch(`/api/personas/${slug}/run/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    await consumeSSE(response, (event, data) => handleSSEFrame(chat, event, data, startedAt));
    finalizeStages(chat);
    chat.runStatus = `done — ${((performance.now() - startedAt) / 1000).toFixed(1)}s`;
  } catch (err) {
    appendTraceError(chat, err.message);
    chat.runStatus = "error";
  } finally {
    chat.running = false;
    if (state.selected === slug) syncRunPanelChrome();
  }
}

async function consumeSSE(response, onFrame) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line ("\n\n").
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const lines = frame.split("\n");
      let eventName = "message";
      let dataParts = [];
      for (const line of lines) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataParts.push(line.slice(5).trim());
      }
      if (dataParts.length === 0) continue;
      try {
        onFrame(eventName, JSON.parse(dataParts.join("\n")));
      } catch (err) {
        console.warn("SSE parse error", err, frame);
      }
    }
  }
}

function handleSSEFrame(chat, eventName, data, startedAt) {
  if (eventName === "trace") {
    routeTraceEvent(chat, data, startedAt);
  } else if (eventName === "result") {
    renderFinalStage(chat, data);
  } else if (eventName === "error") {
    appendTraceError(chat, data.error || "unknown error");
  }
}

// ---- staged trace renderer ----

function initStages(chat) {
  chat.stagesEl.hidden = state.selected !== chat.slug;
  chat.stagesEl.innerHTML = "";
  for (const def of STAGE_DEFS) {
    const stage = document.createElement("section");
    stage.className = "stage";
    stage.dataset.stageNo = String(def.no);
    stage.innerHTML = `
      <div class="stage-head">
        <span class="step-no">Step ${def.no}</span>
        <h3>${def.title}</h3>
        ${def.subtitle ? `<span class="stage-sub">${def.subtitle}</span>` : ""}
      </div>
      <div class="stage-body" data-stage-no="${def.no}"></div>
    `;
    chat.stagesEl.appendChild(stage);
  }
}

function finalizeStages(chat) {
  // Any stage that didn't receive an event gets a "no events" placeholder
  // — clearer than an empty card with just a header.
  for (const def of STAGE_DEFS) {
    const body = chatStageBody(chat, def.no);
    if (body && !body.children.length) {
      const empty = document.createElement("div");
      empty.className = "stage-empty";
      empty.textContent = def.no === 5
        ? "no tasks cleared the cutoff today — silence is correct output."
        : "no events";
      body.appendChild(empty);
    }
  }
}

function routeTraceEvent(chat, traceEvent, startedAt) {
  const stageNo = STAGE_BY_TYPE[traceEvent.type];
  if (!stageNo) return; // orchestrator_finished etc. — not displayed
  const body = chatStageBody(chat, stageNo);
  if (!body) return;
  const elapsed = `+${((performance.now() - startedAt) / 1000).toFixed(1)}s`;

  let node;
  switch (traceEvent.type) {
    case "task_scored":
    case "task_emitted":
    case "task_filtered":
      node = renderRubricNode(traceEvent, elapsed);
      break;
    case "message_drafted":
      node = renderReframeNode(traceEvent, elapsed);
      break;
    case "preference_merged":
      node = renderPrefNode(traceEvent, elapsed);
      break;
    default:
      // Stage 1 events: agent execution + tool calls + llm calls.
      node = renderGenericTraceNode(traceEvent, elapsed);
  }
  if (!node) return;

  // Streaming follow-tail: scroll the new node into view IF this chat is
  // the visible one AND the user was already at the bottom of the run-panel.
  // For background chats we just append silently — when the user switches
  // back, the freshest activity is already at the end of the chat.
  const isVisible = state.selected === chat.slug;
  const wasAtBottom = isVisible && isPanelAtBottom();
  body.appendChild(node);
  if (wasAtBottom) {
    node.scrollIntoView({ block: "end", behavior: "instant" });
  }
}

function isPanelAtBottom() {
  const panel = document.querySelector(".run-panel");
  if (!panel) return false;
  const distanceFromBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight;
  return distanceFromBottom < 80;
}

// ── generic trace node (stage 1 events) ──

function renderGenericTraceNode(traceEvent, elapsed) {
  const sa = traceEvent.sub_agent || "orchestrator";
  const isTool = traceEvent.type === "tool_call"
    || traceEvent.type === "tool_result"
    || traceEvent.type === "llm_call";

  const node = document.createElement("div");
  node.className = "trace-node" + (isTool ? " tool" : "");
  node.dataset.agent = sa;
  applyFilterVisibility(node);

  node.appendChild(buildTime(elapsed));
  const body = document.createElement("div");
  body.className = "trace-body";
  body.appendChild(buildHeader(sa, traceEvent.type));
  const payload = buildPayloadBlock(traceEvent.payload);
  if (payload) body.appendChild(payload);
  node.appendChild(body);
  return node;
}

// ── stage 2 — rubric scoring + filter ──

function renderRubricNode(traceEvent, elapsed) {
  const p = traceEvent.payload || {};
  const originAgent = p.agent || traceEvent.sub_agent || "orchestrator";
  // task_emitted / task_filtered tell us pass/fail; task_scored is a
  // pre-filter scoring tick.
  const passed = traceEvent.type === "task_emitted";
  const dropped = traceEvent.type === "task_filtered";

  const node = document.createElement("div");
  node.className = "trace-node" + (dropped ? " dropped" : "");
  node.dataset.agent = "rubric";
  // Tag the originating agent too so the filter can hide this row when
  // that agent is unchecked (otherwise filtering Shopping would still
  // leave shopping's rubric scores visible).
  node.dataset.originAgent = originAgent;
  applyFilterVisibility(node);

  const time = document.createElement("div");
  time.className = "trace-time";
  if (passed) time.textContent = "kept";
  else if (dropped) time.textContent = "drop";
  else time.textContent = elapsed;
  node.appendChild(time);

  const body = document.createElement("div");
  body.className = "trace-body";

  const header = document.createElement("div");
  header.className = "trace-header-line";
  header.appendChild(buildAgentTag("rubric"));
  const originTag = buildAgentTag(originAgent);
  originTag.style.opacity = "0.7";
  header.appendChild(originTag);
  const typeEl = document.createElement("span");
  typeEl.className = "event-type";
  if (passed) typeEl.textContent = `task_emitted · ${p.score ?? "?"}/7`;
  else if (dropped) typeEl.textContent = `task_filtered · ${p.score ?? "?"}/7 — ${p.reason || ""}`;
  else typeEl.textContent = `task_scored · ${p.score ?? "?"}/7`;
  header.appendChild(typeEl);
  body.appendChild(header);

  if (p.title) {
    const titleLine = document.createElement("div");
    titleLine.className = "trace-payload";
    titleLine.style.whiteSpace = "normal";
    titleLine.textContent = p.title;
    body.appendChild(titleLine);
  }
  if (Array.isArray(p.criteria) && p.criteria.length) {
    body.appendChild(buildCriteriaPills(p.criteria));
  }
  node.appendChild(body);
  return node;
}

function buildCriteriaPills(criteria) {
  const wrap = document.createElement("div");
  wrap.className = "rubric-criteria";
  // Render in canonical order so all rubric rows align visually.
  const byName = new Map(criteria.map((c) => [c.name, c]));
  for (const name of RUBRIC_CRITERIA) {
    const c = byName.get(name);
    const hit = c ? !!c.matches : false;
    const pill = document.createElement("span");
    pill.className = "rubric-pill " + (hit ? "hit" : "miss");
    pill.textContent = (hit ? "✓ " : "✗ ") + name;
    if (c?.reasoning) pill.title = c.reasoning;
    wrap.appendChild(pill);
  }
  return wrap;
}

// ── stage 3 — messenger reframing ──

function renderReframeNode(traceEvent, elapsed) {
  const p = traceEvent.payload || {};
  const originAgent = p.agent || "orchestrator";

  const node = document.createElement("div");
  node.className = "trace-node";
  node.dataset.agent = "messenger";
  node.dataset.originAgent = originAgent;
  applyFilterVisibility(node);

  const time = document.createElement("div");
  time.className = "trace-time";
  time.textContent = (p.surface_time || elapsed).slice(11, 16) || elapsed;
  node.appendChild(time);

  const body = document.createElement("div");
  body.className = "trace-body";

  const header = document.createElement("div");
  header.className = "trace-header-line";
  header.appendChild(buildAgentTag("messenger"));
  const originTag = buildAgentTag(originAgent);
  originTag.style.opacity = "0.7";
  header.appendChild(originTag);
  const typeEl = document.createElement("span");
  typeEl.className = "event-type";
  typeEl.textContent = `message_drafted · surface @ ${p.surface_time || "?"}`;
  header.appendChild(typeEl);
  body.appendChild(header);

  const grid = document.createElement("div");
  grid.className = "reframe-grid";
  grid.innerHTML = `
    <div class="reframe-cell">
      <div class="reframe-label">original task</div>
      <div><b>${escapeHtml(p.title || "")}</b></div>
      ${p.action ? `<div style="color: var(--muted); margin-top: 4px;">${escapeHtml(p.action)}</div>` : ""}
    </div>
    <div class="reframe-cell after">
      <div class="reframe-label">user-facing message</div>
      <div>${escapeHtml(p.message || "")}</div>
    </div>
  `;
  body.appendChild(grid);
  node.appendChild(body);
  return node;
}

// ── stage 4 — preference updates ──

function renderPrefNode(traceEvent, elapsed) {
  // Prefs are orchestrator-emitted; tag color stays neutral.
  const node = document.createElement("div");
  node.className = "trace-node";
  node.dataset.agent = "orchestrator";
  node.appendChild(buildTime("merge"));
  const body = document.createElement("div");
  body.className = "trace-body";
  body.appendChild(buildHeader("orchestrator", "preference_merged"));
  const payload = buildPayloadBlock(traceEvent.payload);
  if (payload) body.appendChild(payload);
  node.appendChild(body);
  return node;
}

// ── stage 5 — final surfaced messages (from `result` SSE frame) ──

function renderFinalStage(chat, result) {
  const body = chatStageBody(chat, 5);
  if (!body) return;
  body.innerHTML = "";
  const messages = result.final_messages || [];
  if (messages.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.style.fontSize = "12px";
    empty.style.margin = "0";
    empty.textContent = "no tasks cleared the cutoff today — silence is correct output.";
    body.appendChild(empty);
    return;
  }
  for (const m of messages) {
    const t = m.scored_task.task;
    const card = document.createElement("div");
    card.className = "final-task-card";
    card.style.borderLeftColor = `var(--c-${t.sub_agent}, var(--accent))`;
    const msg = document.createElement("p");
    msg.className = "final-task-message";
    msg.textContent = m.message;
    const meta = document.createElement("div");
    meta.className = "final-task-meta";
    meta.innerHTML =
      `<span class="agent-tag ${t.sub_agent}">${t.sub_agent}</span>` +
      `<span>score ${m.scored_task.total_score}/7</span>` +
      `<span>surface @ <code>${m.surface_time}</code></span>`;
    card.appendChild(msg);
    card.appendChild(meta);
    body.appendChild(card);
  }
}

// ── shared builders ──

function buildTime(label) {
  const el = document.createElement("div");
  el.className = "trace-time";
  el.textContent = label;
  return el;
}

// Hide a freshly-built node when the filter for its agent (or origin
// agent, for rubric/messenger cards) is currently off. Mirrors the
// filter handler's selector so a node arriving mid-stream while a
// filter is unchecked doesn't visibly flicker into view.
function applyFilterVisibility(node) {
  const slugs = [node.dataset.agent, node.dataset.originAgent].filter(Boolean);
  for (const slug of slugs) {
    const cb = document.querySelector(`#filter-toggles input[data-agent="${slug}"]`);
    if (cb && !cb.checked) {
      node.classList.add("hidden");
      return;
    }
  }
}

function buildAgentTag(agent) {
  const tag = document.createElement("span");
  tag.className = `agent-tag ${agent}`;
  tag.textContent = agent;
  return tag;
}

function buildHeader(agent, type) {
  const header = document.createElement("div");
  header.className = "trace-header-line";
  header.appendChild(buildAgentTag(agent));
  const t = document.createElement("span");
  t.className = "event-type";
  t.textContent = type;
  header.appendChild(t);
  return header;
}

function buildPayloadBlock(payload) {
  if (!payload || typeof payload !== "object" || Object.keys(payload).length === 0) return null;
  const wrap = document.createElement("div");
  wrap.className = "trace-payload";
  const pre = document.createElement("pre");
  pre.className = "payload-pre";
  const code = document.createElement("code");
  code.className = "language-json";
  code.textContent = JSON.stringify(payload, null, 2);
  pre.appendChild(code);
  wrap.appendChild(pre);
  if (window.Prism) Prism.highlightElement(code);
  return wrap;
}

function appendTraceError(chat, msg) {
  // Errors land in stage 1 since they're typically subagent failures.
  const body = chatStageBody(chat, 1);
  if (!body) return;
  const node = document.createElement("div");
  node.className = "trace-node error";
  node.dataset.agent = "orchestrator";
  node.innerHTML = `<div class="trace-time">err</div>
    <div class="trace-body">
      <div class="trace-header-line">
        <span class="agent-tag orchestrator">error</span>
      </div>
      <div class="trace-payload">${escapeHtml(msg)}</div>
    </div>`;
  body.appendChild(node);
}

// ---- utils ----

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ─────────────────────────────────────────────────────────────────────────
// Evals view — toggled by the header button. When open, hides <main>
// and renders historical eval data as charts + tables.
// ─────────────────────────────────────────────────────────────────────────

const evalsState = {
  open: false,
  loaded: false,
  data: null,
  charts: [],   // active Chart.js instances; destroyed on view close
};

// Per-agent colour anchors (hex). Mirror the CSS --c-<agent> values so the
// chart line colours match the agent tags shown elsewhere in the UI.
const AGENT_COLOR = {
  calendar:     "#2563eb",
  email_triage: "#9333ea",
  food:         "#ea580c",
  travel:       "#0d9488",
  finance:      "#16a34a",
  dates:        "#db2777",
  shopping:     "#dc2626",
  todos:        "#4f46e5",
  events:       "#ca8a04",
};

function initEvalsToggle() {
  const btn = $("#evals-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    evalsState.open ? closeEvalsView() : openEvalsView();
  });
}

async function openEvalsView() {
  evalsState.open = true;
  $("#evals-toggle").classList.add("active");
  $("main.layout").style.display = "none";
  $("#evals-view").hidden = false;
  if (!evalsState.loaded) {
    await loadEvalsData();
  } else {
    renderEvalsView();
  }
}

function closeEvalsView() {
  evalsState.open = false;
  $("#evals-toggle").classList.remove("active");
  $("main.layout").style.display = "";
  $("#evals-view").hidden = true;
  // Charts hold canvas refs; destroy them so a re-open re-creates fresh
  // instances (otherwise the second open can leak resize observers).
  for (const c of evalsState.charts) {
    try { c.destroy(); } catch (_e) { /* noop */ }
  }
  evalsState.charts = [];
}

async function loadEvalsData() {
  const view = $("#evals-view");
  view.innerHTML = `<div class="evals-loading">loading eval history…</div>`;
  try {
    evalsState.data = await fetchJSON("/api/evals");
    evalsState.loaded = true;
    renderEvalsView();
  } catch (err) {
    view.innerHTML = `<div class="evals-loading">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

function renderEvalsView() {
  const view = $("#evals-view");
  view.innerHTML = "";
  // Destroy any charts left over from a prior render.
  for (const c of evalsState.charts) { try { c.destroy(); } catch (_e) {} }
  evalsState.charts = [];

  const agents = (evalsState.data?.agents || []).filter((a) => a.runs.length);
  if (!agents.length) {
    view.innerHTML = `<div class="evals-loading">no eval history found.</div>`;
    return;
  }

  view.appendChild(renderLeaderboard(agents));
  view.appendChild(renderCombinedTimeline(agents));
  view.appendChild(renderPerAgentSection(agents));
}

// ── leaderboard (top section) ──

function renderLeaderboard(agents) {
  const wrap = document.createElement("section");
  wrap.className = "evals-section";
  wrap.innerHTML = `<h2 class="evals-section-title">Latest run — leaderboard</h2>`;

  const table = document.createElement("table");
  table.className = "evals-leaderboard";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Rank</th>
        <th>Agent</th><th>Date</th><th>Model</th>
        <th>F1</th><th>Precision</th><th>Recall</th>
        <th>Specificity</th><th>Pref&nbsp;coverage</th>
        <th>Runs</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector("tbody");

  // Sort by latest F1 desc so the strongest agents bubble to the top.
  const rows = [...agents].sort((a, b) => {
    const af = a.latest?.macro?.f1 ?? -1;
    const bf = b.latest?.macro?.f1 ?? -1;
    return bf - af;
  });

  // Standard competition ranking — ties share the same rank, next rank
  // skips accordingly (1, 2, 2, 4, …). Rounding to 4 dp avoids float
  // noise classifying mathematically equal F1s as different.
  const keyFor = (a) => Math.round((a.latest?.macro?.f1 ?? -1) * 1e4);
  let lastKey = null;
  let lastRank = 0;
  for (let i = 0; i < rows.length; i++) {
    const a = rows[i];
    const k = keyFor(a);
    const rank = k === lastKey ? lastRank : i + 1;
    lastKey = k; lastRank = rank;
    const m = a.latest?.macro || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="metric"><b>${rank}</b></td>
      <td><span class="agent-tag ${a.agent}">${a.agent}</span></td>
      <td>${a.latest?.evaluation_date || "—"}</td>
      <td>${a.latest?.model || "—"}</td>
      <td class="metric ${f1Class(m.f1)}">${fmt(m.f1)}</td>
      <td class="metric">${fmt(m.precision)}</td>
      <td class="metric">${fmt(m.recall)}</td>
      <td class="metric">${fmt(m.specificity)}</td>
      <td class="metric">${fmt(m.pref_coverage)}</td>
      <td class="metric">${a.runs.length}</td>
    `;
    tbody.appendChild(tr);
  }
  wrap.appendChild(table);
  return wrap;
}

// ── combined F1 timeline (one chart, all agents) ──

function renderCombinedTimeline(agents) {
  const wrap = document.createElement("section");
  wrap.className = "evals-section";
  wrap.innerHTML = `<h2 class="evals-section-title">Combined — F1 trajectory across agents</h2>`;

  const card = document.createElement("div");
  card.className = "eval-card";
  card.innerHTML = `
    <div class="eval-card-head">
      <h3>F1 over iterations</h3>
      <span class="eval-card-meta">${agents.length} agents</span>
    </div>
    <div class="eval-chart-wrap large"><canvas></canvas></div>
  `;
  wrap.appendChild(card);

  const canvas = card.querySelector("canvas");
  const datasets = agents
    .filter((a) => a.runs.length >= 1)
    .map((a) => ({
      label: a.agent,
      data: a.runs.map((r, i) => ({
        x: i + 1,
        y: r.macro?.f1 ?? null,
      })),
      borderColor: AGENT_COLOR[a.agent] || "#525252",
      backgroundColor: AGENT_COLOR[a.agent] || "#525252",
      tension: 0.25,
      pointRadius: 3,
      borderWidth: 2,
      spanGaps: true,
    }));

  evalsState.charts.push(new Chart(canvas, {
    type: "line",
    data: { datasets },
    options: lineChartOptions({ yMax: 1, yLabel: "F1" }),
  }));

  return wrap;
}

// ── per-agent grid: chart + macro pills + persona table + failures ──

function renderPerAgentSection(agents) {
  const wrap = document.createElement("section");
  wrap.className = "evals-section";
  wrap.innerHTML = `<h2 class="evals-section-title">Per-agent detail</h2>`;
  const grid = document.createElement("div");
  grid.className = "evals-grid";
  // Sort by number of runs desc — agents with more history go on top so
  // their richer trend lines are visible without scrolling. Tiebreak by
  // latest F1 desc, then alphabetically for stability.
  const ordered = [...agents].sort((a, b) => {
    if (b.runs.length !== a.runs.length) return b.runs.length - a.runs.length;
    const af = a.latest?.macro?.f1 ?? -1;
    const bf = b.latest?.macro?.f1 ?? -1;
    if (bf !== af) return bf - af;
    return a.agent.localeCompare(b.agent);
  });
  for (const a of ordered) grid.appendChild(renderAgentCard(a));
  wrap.appendChild(grid);
  return wrap;
}

function renderAgentCard(agent) {
  const card = document.createElement("div");
  card.className = "eval-card";

  const m = agent.latest?.macro || {};
  card.innerHTML = `
    <div class="eval-card-head">
      <span class="agent-tag ${agent.agent}">${agent.agent}</span>
      <h3 style="margin-left: 4px;">${agent.runs.length} run${agent.runs.length === 1 ? "" : "s"}</h3>
      <span class="eval-card-meta">latest: ${agent.latest?.evaluation_date || "—"}</span>
    </div>
    <div class="eval-chart-wrap"><canvas></canvas></div>
    <div class="eval-macro-row">
      <span class="eval-macro-pill">F1 <b>${fmt(m.f1)}</b></span>
      <span class="eval-macro-pill">P <b>${fmt(m.precision)}</b></span>
      <span class="eval-macro-pill">R <b>${fmt(m.recall)}</b></span>
      <span class="eval-macro-pill">Spec <b>${fmt(m.specificity)}</b></span>
      <span class="eval-macro-pill">Pref <b>${fmt(m.pref_coverage)}</b></span>
    </div>
  `;

  // Per-agent line chart: 3 series (precision, recall, F1).
  const canvas = card.querySelector("canvas");
  const color = AGENT_COLOR[agent.agent] || "#525252";
  evalsState.charts.push(new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        {
          label: "F1",
          data: agent.runs.map((r, i) => ({ x: i + 1, y: r.macro?.f1 ?? null })),
          borderColor: color,
          backgroundColor: color,
          borderWidth: 2.5,
          tension: 0.25,
          pointRadius: 3,
          spanGaps: true,
        },
        {
          label: "Precision",
          data: agent.runs.map((r, i) => ({ x: i + 1, y: r.macro?.precision ?? null })),
          borderColor: color,
          backgroundColor: "transparent",
          borderWidth: 1.4,
          borderDash: [4, 4],
          tension: 0.25,
          pointRadius: 2,
          spanGaps: true,
        },
        {
          label: "Recall",
          data: agent.runs.map((r, i) => ({ x: i + 1, y: r.macro?.recall ?? null })),
          borderColor: color,
          backgroundColor: "transparent",
          borderWidth: 1.4,
          borderDash: [2, 3],
          tension: 0.25,
          pointRadius: 2,
          spanGaps: true,
        },
      ],
    },
    options: lineChartOptions({ yMax: 1, yLabel: "" }),
  }));

  // Per-persona table (latest run).
  if (agent.latest?.personas?.length) {
    card.appendChild(renderPersonaTable(agent.latest.personas));
  }

  // Failures (latest run, aggregated across personas).
  const failures = collectFailures(agent.latest?.personas || []);
  if (failures.length) {
    card.appendChild(renderFailures(failures));
  }

  return card;
}

function renderPersonaTable(personas) {
  const t = document.createElement("table");
  t.className = "eval-persona-table";
  t.innerHTML = `
    <thead>
      <tr>
        <th>Persona</th><th>Mode</th>
        <th>F1</th><th>P</th><th>R</th>
        <th>TP</th><th>FP</th><th>FN</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tb = t.querySelector("tbody");
  for (const p of personas) {
    const tr = document.createElement("tr");
    const fp = (p.fp_unexpected ?? 0) + (p.fp_skip_violations ?? 0);
    tr.innerHTML = `
      <td>${escapeHtml(p.slug || "")}</td>
      <td>${escapeHtml(p.mode || "")}</td>
      <td class="metric ${f1Class(p.f1)}">${fmt(p.f1)}</td>
      <td class="metric">${fmt(p.precision)}</td>
      <td class="metric">${fmt(p.recall)}</td>
      <td class="metric">${p.tp ?? 0}</td>
      <td class="metric">${fp}</td>
      <td class="metric">${p.fn ?? 0}</td>
    `;
    tb.appendChild(tr);
  }
  return t;
}

function collectFailures(personas) {
  const out = [];
  for (const p of personas) {
    const f = p.failures || {};
    for (const m of f.task_misses || [])      out.push({ persona: p.slug, kind: "miss",   ...m });
    for (const v of f.skip_violations || [])  out.push({ persona: p.slug, kind: "skipv",  ...v });
    for (const u of f.unexpected_tasks || []) out.push({ persona: p.slug, kind: "unexp",  ...u });
    for (const t of f.pref_topic_misses || [])out.push({ persona: p.slug, kind: "preft",  ...t });
  }
  return out;
}

function renderFailures(failures) {
  const det = document.createElement("details");
  det.className = "eval-failures";
  const sum = document.createElement("summary");
  sum.textContent = `${failures.length} failure${failures.length === 1 ? "" : "s"} — click to expand`;
  det.appendChild(sum);

  const KIND_LABEL = { miss: "miss", skipv: "skip violation", unexp: "unexpected", preft: "pref topic miss" };
  for (const f of failures) {
    const item = document.createElement("div");
    item.className = "eval-failure-item";
    const summary = f.summary || f.title || "(no summary)";
    item.innerHTML = `
      <span class="eval-failure-kind ${f.kind}">${KIND_LABEL[f.kind] || f.kind}</span>
      <span class="muted">${escapeHtml(f.persona || "")}</span>
      <div class="eval-failure-summary">${escapeHtml(summary)}</div>
      ${f.judge_reasoning ? `<div class="eval-failure-reason">${escapeHtml(f.judge_reasoning)}</div>` : ""}
    `;
    det.appendChild(item);
  }
  return det;
}

// ── chart helpers ──

function lineChartOptions({ yMax = 1, yLabel = "" } = {}) {
  // Detect dark mode so axis labels stay readable in both themes.
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const tickColor = dark ? "#a1a1aa" : "#71717a";
  const gridColor = dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
  // Sliver of headroom so series sitting exactly on yMax (e.g. F1=1.0 or
  // perfect precision) don't have their points clipped against the top
  // edge of the chart area. Tick labels are still capped at the round
  // 0.0 → 1.0 grid via the callback below.
  const headroom = yMax * 0.06;
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    layout: { padding: { top: 8 } },
    scales: {
      x: {
        type: "linear",
        title: { display: true, text: "Iteration", color: tickColor, font: { size: 10 } },
        ticks: {
          color: tickColor,
          font: { size: 10 },
          stepSize: 1,
          precision: 0,
          callback: (v) => (Number.isInteger(v) ? v : ""),
        },
        grid: { color: gridColor },
      },
      y: {
        min: 0,
        max: yMax + headroom,
        title: yLabel ? { display: true, text: yLabel, color: tickColor, font: { size: 10 } } : undefined,
        ticks: {
          color: tickColor,
          font: { size: 10 },
          stepSize: yMax / 5,
          // Suppress any tick auto-generated above yMax so the axis
          // doesn't show an awkward "1.06" label up top.
          callback: (v) => (v <= yMax + 1e-9 ? Number(v).toFixed(1) : ""),
        },
        grid: { color: gridColor },
      },
    },
    plugins: {
      legend: { labels: { color: tickColor, font: { size: 11 }, boxWidth: 12 } },
      tooltip: {
        backgroundColor: "rgba(0,0,0,0.85)",
        titleFont: { size: 11 },
        bodyFont: { size: 11 },
        callbacks: {
          title: (items) => `Iteration ${items[0].parsed.x}`,
        },
      },
    },
  };
}

function fmt(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(2);
}

function f1Class(n) {
  if (n == null) return "";
  if (n >= 0.75) return "f1-good";
  if (n >= 0.5)  return "f1-mid";
  return "f1-bad";
}

// Exports for preview pages (trace-preview.html). These are the exact
// renderers main.js uses for live SSE events — preview drives them with
// synthetic events so a full agent run isn't needed to verify UI changes.
export {
  AGENTS,
  STAGE_DEFS,
  initStages,
  finalizeStages,
  routeTraceEvent,
  renderFinalStage,
  buildFilterBar,
};
