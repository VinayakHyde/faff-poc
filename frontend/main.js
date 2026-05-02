// Faff POC frontend.
//
// Wires up: persona sidebar (GET /api/personas) → profile renderer
// (GET /api/personas/{slug}, marked.parse) → daily-input fixture preload
// (GET /api/personas/{slug}/fixtures/{date}) → SSE-streamed run
// (POST /api/personas/{slug}/run/stream) → trace nodes with per-agent
// filter toggles → final user-facing task cards.

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
  running: false,
  activeTab: "profile",
  // Per-persona caches so switching tabs doesn't refetch.
  emailCache: new Map(),    // slug → messages[]
  calendarCache: new Map(), // slug → events[]
};

// ---- sidebar resize constants (must be declared before init() IIFE) ----

const SIDEBAR_KEY = "sidebarWidthPx";
const COMPACT_THRESHOLD = 140; // px below which we collapse to icon-only

// ---- bootstrap ----

(async function init() {
  initSidebarResize();
  buildFilterBar();
  initTabs();
  await loadPersonas();
  $("#run-btn").addEventListener("click", runStream);
})();

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
  if (state.running) return;
  state.selected = slug;
  $$(".persona-list li").forEach((li) => {
    li.classList.toggle("active", li.dataset.slug === slug);
  });

  // Reset to Profile tab + clear other tab views (they'll lazy-load when clicked).
  selectTab("profile");
  $("#tab-email").innerHTML = "";
  $("#tab-calendar").innerHTML = "";

  await Promise.all([loadProfile(slug), loadFixtureIntoInput(slug)]);
  $("#run-btn").disabled = false;
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
        $("#daily-input-json").value = "";
        return;
      }
      fixture = await fetchJSON(`/api/personas/${slug}/fixtures/${dates[dates.length - 1]}`);
    }
    $("#daily-input-json").value = JSON.stringify(fixture, null, 2);
  } catch (err) {
    $("#daily-input-json").value = "";
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
  // Newest first.
  const sorted = [...messages].sort((a, b) =>
    (b.received_at || "").localeCompare(a.received_at || "")
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

// ---- filter bar ----

function buildFilterBar() {
  const host = $("#filter-toggles");
  host.innerHTML = "";
  for (const a of AGENTS) {
    const lbl = document.createElement("label");
    lbl.dataset.agent = a.slug;
    lbl.innerHTML = `<input type="checkbox" data-agent="${a.slug}" checked /> ${a.label}`;
    lbl.querySelector("input").addEventListener("change", (e) => {
      const slug = e.target.dataset.agent;
      const on = e.target.checked;
      lbl.classList.toggle("off", !on);
      $$(`.trace-node[data-agent="${slug}"]`).forEach((n) => n.classList.toggle("hidden", !on));
    });
    host.appendChild(lbl);
  }
}

// ---- run + SSE consumer ----

async function runStream() {
  if (state.running || !state.selected) return;
  state.running = true;
  $("#run-btn").disabled = true;

  const slug = state.selected;
  const inputRaw = $("#daily-input-json").value.trim();

  // Reset trace + final tasks for a fresh run.
  $("#filter-bar").hidden = false;
  $("#trace-stream").hidden = false;
  $("#trace-list").innerHTML = "";
  $("#final-tasks").hidden = true;
  $("#final-tasks-list").innerHTML = "";
  $("#run-status").textContent = "running…";

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

    await consumeSSE(response, (event, data) => handleSSEFrame(event, data, startedAt));
    $("#run-status").textContent = `done — ${((performance.now() - startedAt) / 1000).toFixed(1)}s`;
  } catch (err) {
    appendTraceError(err.message);
    $("#run-status").textContent = `error`;
  } finally {
    state.running = false;
    $("#run-btn").disabled = false;
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

function handleSSEFrame(eventName, data, startedAt) {
  if (eventName === "trace") {
    appendTraceNode(data, startedAt);
  } else if (eventName === "result") {
    renderFinalResult(data);
  } else if (eventName === "error") {
    appendTraceError(data.error || "unknown error");
  }
}

// ---- trace nodes ----

function appendTraceNode(traceEvent, startedAt) {
  const elapsed = ((performance.now() - startedAt) / 1000).toFixed(1) + "s";
  const node = document.createElement("div");
  const sa = traceEvent.sub_agent || "orchestrator";
  node.className = "trace-node";
  node.dataset.agent = sa;

  // honour current filter checkbox state for this agent
  const cb = document.querySelector(`#filter-toggles input[data-agent="${sa}"]`);
  if (cb && !cb.checked) node.classList.add("hidden");

  const time = document.createElement("div");
  time.className = "trace-time";
  time.textContent = `+${elapsed}`;

  const body = document.createElement("div");
  body.className = "trace-body";

  const header = document.createElement("div");
  header.className = "trace-header-line";
  const tag = document.createElement("span");
  tag.className = `agent-tag ${sa}`;
  tag.textContent = sa;
  const type = document.createElement("span");
  type.className = "event-type";
  type.textContent = traceEvent.type;
  header.appendChild(tag);
  header.appendChild(type);

  const payloadDiv = document.createElement("div");
  payloadDiv.className = "trace-payload";
  payloadDiv.textContent = formatPayload(traceEvent.payload);

  body.appendChild(header);
  if (payloadDiv.textContent) body.appendChild(payloadDiv);
  node.appendChild(time);
  node.appendChild(body);
  $("#trace-list").appendChild(node);

  // auto-scroll the stream
  const stream = $("#trace-stream");
  stream.scrollTop = stream.scrollHeight;
}

function appendTraceError(msg) {
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
  $("#trace-list").appendChild(node);
}

function formatPayload(payload) {
  if (!payload || typeof payload !== "object" || Object.keys(payload).length === 0) return "";
  // Compact one-liner for short payloads, multi-line JSON for bigger ones.
  const json = JSON.stringify(payload);
  if (json.length <= 120) return json;
  return JSON.stringify(payload, null, 2);
}

// ---- final result ----

function renderFinalResult(result) {
  const list = $("#final-tasks-list");
  list.innerHTML = "";
  const messages = result.final_messages || [];
  if (messages.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.style.fontSize = "12px";
    empty.style.margin = "0";
    empty.textContent = "no tasks cleared the cutoff today — silence is correct output.";
    list.appendChild(empty);
  } else {
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
      list.appendChild(card);
    }
  }
  $("#final-tasks").hidden = false;
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
