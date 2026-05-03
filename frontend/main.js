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
  running: false,
  activeTab: "profile",
  // Per-persona caches so switching tabs doesn't refetch.
  emailCache: new Map(),    // slug → messages[]
  calendarCache: new Map(), // slug → events[]
  goldenCache: new Map(),   // slug → { items, agents }
};

// ---- sidebar resize constants (must be declared before init() IIFE) ----

const SIDEBAR_KEY = "sidebarWidthPx";
const COMPACT_THRESHOLD = 140; // px below which we collapse to icon-only

// ---- bootstrap ----

let jsonEditor = null;

(async function init() {
  initSidebarResize();
  initJsonEditor();
  buildFilterBar();
  initTabs();
  initStickyActionBar();
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
  if (state.running) return;
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

  await Promise.all([loadProfile(slug), loadFixtureIntoInput(slug)]);
  $("#run-btn").disabled = false;
}

// ---- profile panel ----

async function loadProfile(slug) {
  try {
    const [profile, golden] = await Promise.all([
      fetchJSON(`/api/personas/${slug}`),
      ensureGoldenMap(slug),
    ]);
    $("#profile-empty").hidden = true;
    $("#profile-content-wrapper").hidden = false;

    const firstName = profile.meta.name.split(" ")[0];
    $("#profile-avatar").src = `/assets/avatars/${firstName}_arch.png`;
    $("#profile-avatar").onerror = function () { this.style.visibility = "hidden"; };
    $("#profile-name").textContent = profile.meta.name;
    $("#profile-meta").textContent =
      `${profile.meta.neighbourhood}, ${profile.meta.city}  ·  onboarded ${profile.meta.onboarded_at}`;

    renderProfileLineByLine(profile.markdown);
    // Overlay per-item absolute-positioned frames over the exact source
    // lines each golden item anchors to (via profile_md_lines).
    applyLineFrames(golden.allItems);
  } catch (err) {
    $("#profile-empty").hidden = false;
    $("#profile-content-wrapper").hidden = true;
    $("#profile-empty").textContent = `failed: ${err.message}`;
  }
}

// Walk every h2 section in the rendered profile markdown. For each, gather
// the section's text (heading + following siblings until the next h2) and
// run the heuristic match. If any agent's expected_task summary shares a
// 4+ char token with the section text, wrap the section in a `golden-shim`
// div with the agent labels as a tag.
// Per-line frame approach for the profile shim.
//
//   1. Render profile.md line-by-line, each line as its own DOM node with
//      `data-line="N"`. Inline markdown (bold, italic, links) is preserved
//      via marked.parseInline; multi-line constructs (lists, headings) are
//      handled per-line so each list bullet / heading line is its own node.
//
//   2. For each golden item with profile_md_lines, compute a bounding
//      rectangle from the min/max line's offsetTop/offsetHeight and overlay
//      an absolute-positioned frame on the profile container. Frames don't
//      nest in the DOM, so multiple items with overlapping line ranges
//      render as separate, visually-overlapping rectangles — exactly the
//      "different line styles for overlap" the spec asks for.
//
//   3. Buckets merge only when (sorted line set, summary) are EXACTLY
//      identical — those collapse into a single frame whose tag lists all
//      contributing agents. Otherwise each bucket gets its own frame.
//
//   4. Border style cycles solid → dashed → dotted → double per stacking
//      order. Frame tags stagger horizontally so multiple stacks per region
//      are all readable.

function renderProfileLineByLine(rawMarkdown) {
  const root = $("#tab-profile");
  if (!root) return;
  root.classList.add("profile-line-view");
  root.innerHTML = "";

  const lines = rawMarkdown.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const div = document.createElement("div");
    div.className = "profile-line";
    div.dataset.line = String(i + 1);

    if (raw.trim() === "") {
      div.classList.add("empty");
      div.innerHTML = "&nbsp;";
    } else if (/^#\s+/.test(raw)) {
      div.classList.add("h1");
      div.innerHTML = `<h1>${marked.parseInline(raw.replace(/^#\s+/, ""))}</h1>`;
    } else if (/^##\s+/.test(raw)) {
      div.classList.add("h2");
      div.innerHTML = `<h2>${marked.parseInline(raw.replace(/^##\s+/, ""))}</h2>`;
    } else if (/^###\s+/.test(raw)) {
      div.classList.add("h3");
      div.innerHTML = `<h3>${marked.parseInline(raw.replace(/^###\s+/, ""))}</h3>`;
    } else if (/^\s*[-*]\s+/.test(raw)) {
      const text = raw.replace(/^\s*[-*]\s+/, "");
      div.classList.add("bullet");
      div.innerHTML = `<span class="bullet-marker">•</span><span class="bullet-text">${marked.parseInline(text)}</span>`;
    } else if (/^\s*\d+\.\s+/.test(raw)) {
      const m = raw.match(/^(\s*)(\d+)\.\s+(.*)$/);
      div.classList.add("ordered");
      div.innerHTML = `<span class="bullet-marker">${m[2]}.</span><span class="bullet-text">${marked.parseInline(m[3])}</span>`;
    } else if (/^\|/.test(raw)) {
      // Render table rows as monospace pre-formatted (preserves columns).
      div.classList.add("table-row");
      div.innerHTML = `<code>${escapeHtml(raw)}</code>`;
    } else {
      div.innerHTML = marked.parseInline(raw);
    }
    root.appendChild(div);
  }
}

// Split a list of line numbers into contiguous runs (gap of ≥1 splits).
function splitIntoContiguousRuns(lines) {
  const sorted = [...new Set(lines.filter((n) => Number.isInteger(n)))].sort((a, b) => a - b);
  const runs = [];
  let cur = null;
  for (const n of sorted) {
    if (cur && n === cur[cur.length - 1] + 1) {
      cur.push(n);
    } else {
      cur = [n];
      runs.push(cur);
    }
  }
  return runs;
}

function applyLineFrames(items) {
  const root = $("#tab-profile");
  if (!root || !items.length) return;

  root.querySelectorAll(".shim-frame").forEach((n) => n.remove());
  root.querySelectorAll(".profile-line.has-frame").forEach((n) =>
    n.classList.remove("has-frame"),
  );
  if (getComputedStyle(root).position === "static") {
    root.style.position = "relative";
  }

  // The H1 title line is exempt from framing — it's a header, not content.
  const isH1Line = (n) => {
    const el = root.querySelector(`.profile-line[data-line="${n}"]`);
    return !!(el && el.classList.contains("h1"));
  };

  // Each item splits into contiguous runs; each run produces a record.
  // Frames are bucketed strictly by (startLine, endLine).
  const bucketMap = new Map();
  for (const item of items) {
    const filtered = (item.profile_md_lines || []).filter(
      (n) => Number.isInteger(n) && !isH1Line(n),
    );
    const runs = splitIntoContiguousRuns(filtered);
    const summary = (item.summary || "").trim();
    for (const run of runs) {
      const startLine = run[0];
      const endLine = run[run.length - 1];
      const key = `${startLine}-${endLine}`;
      let bucket = bucketMap.get(key);
      if (!bucket) {
        bucket = { startLine, endLine, key, tags: [] };
        bucketMap.set(key, bucket);
      }
      // Only collapse identical (agent, summary) duplicates.
      const dupe = bucket.tags.some((t) => t.agent === item.agent && t.summary === summary);
      if (!dupe) bucket.tags.push({ agent: item.agent, summary });
    }
  }
  const buckets = [...bucketMap.values()];
  if (!buckets.length) return;

  // Tag every profile-line covered by a frame so CSS can give it extra
  // breathing room (only framed lines, not the whole profile).
  for (const bucket of buckets) {
    for (let ln = bucket.startLine; ln <= bucket.endLine; ln++) {
      const el = root.querySelector(`.profile-line[data-line="${ln}"]`);
      if (el) el.classList.add("has-frame");
    }
  }

  requestAnimationFrame(() => paintFrames(root, buckets));
}

// For each bucket, return the buckets that strictly contain it (cross-agent),
// sorted biggest → smallest. Used to render ancestor pills on the smaller
// frame so the bigger frame's agents don't get hidden behind it.
function computeBucketParents(buckets) {
  const result = new Map();
  for (const b of buckets) {
    const parents = [];
    for (const c of buckets) {
      if (c === b) continue;
      const strictlyContains =
        c.startLine <= b.startLine &&
        c.endLine >= b.endLine &&
        (c.startLine !== b.startLine || c.endLine !== b.endLine);
      if (strictlyContains) parents.push(c);
    }
    parents.sort(
      (x, y) =>
        y.endLine - y.startLine - (x.endLine - x.startLine) ||
        x.startLine - y.startLine,
    );
    result.set(b.key, parents);
  }
  return result;
}

// Build a single tag pill bound to a target frame. Hovering it traces that
// frame; the tooltip (anchored under the pill) lists the agent's summaries.
function buildTagPill({ agent, summaries, targetFrame, isAncestor }) {
  const tag = document.createElement("span");
  tag.className = "golden-shim-tag" + (isAncestor ? " is-ancestor" : "");
  tag.appendChild(document.createTextNode(agentLabel(agent)));

  const tip = document.createElement("div");
  tip.className = "shim-frame-tip";
  if (summaries.length === 1) {
    const body = document.createElement("div");
    body.className = "shim-frame-tip-single";
    body.textContent = summaries[0];
    tip.appendChild(body);
  } else {
    const list = document.createElement("ul");
    list.className = "shim-frame-tip-list";
    for (const s of summaries) {
      const li = document.createElement("li");
      li.textContent = s;
      list.appendChild(li);
    }
    tip.appendChild(list);
  }
  tag.appendChild(tip);

  tag.addEventListener("mouseenter", () => {
    targetFrame.classList.add("is-tracing");
    const panel = document.querySelector(".profile-panel");
    const tagRect = tag.getBoundingClientRect();
    const panelRect = panel
      ? panel.getBoundingClientRect()
      : { top: 0, bottom: window.innerHeight };
    const spaceBelow = panelRect.bottom - tagRect.bottom;
    const spaceAbove = tagRect.top - panelRect.top;
    const needed = 220;
    tip.classList.toggle("flip-up", spaceBelow < needed && spaceAbove > spaceBelow);
  });
  tag.addEventListener("mouseleave", () => {
    targetFrame.classList.remove("is-tracing");
    tip.classList.remove("flip-up");
  });

  return tag;
}

// Group a bucket's tag list into agent → unique-summaries[].
function groupTagsByAgent(tags) {
  const byAgent = new Map();
  for (const t of tags) {
    const list = byAgent.get(t.agent) || [];
    const s = t.summary || "(no summary)";
    if (!list.includes(s)) list.push(s);
    byAgent.set(t.agent, list);
  }
  return byAgent;
}

function paintFrames(root, buckets) {
  // Stable ordering: top-to-bottom, longer spans first so shorter overlapping
  // frames render in front.
  buckets.sort((a, b) => {
    if (a.startLine !== b.startLine) return a.startLine - b.startLine;
    return (b.endLine - b.startLine) - (a.endLine - a.startLine);
  });

  // Pass 1: create + append every frame element so cross-frame references
  // (ancestor pills, etc.) can resolve via the dom map below.
  const frameMap = new Map(); // bucket.key → { bucket, frameEl, tagRow }
  for (const bucket of buckets) {
    const firstLine = root.querySelector(`.profile-line[data-line="${bucket.startLine}"]`);
    const lastLine = root.querySelector(`.profile-line[data-line="${bucket.endLine}"]`);
    if (!firstLine || !lastLine) continue;

    const top = firstLine.offsetTop;
    const bottom = lastLine.offsetTop + lastLine.offsetHeight;

    const frame = document.createElement("div");
    frame.className = "shim-frame";
    frame.dataset.frameId = bucket.key;
    frame.style.top = `${top - 1}px`;
    frame.style.height = `${bottom - top + 2}px`;
    frame.style.left = "0";
    frame.style.right = "0";

    const tagRow = document.createElement("div");
    tagRow.className = "shim-frame-tags";
    frame.appendChild(tagRow);
    root.appendChild(frame);

    frameMap.set(bucket.key, { bucket, frameEl: frame, tagRow });
  }

  // Pass 2: populate each frame's tag-row with its own pills, then with
  // ancestor pills for any covering frame (cross-agent). Hovering an
  // ancestor pill traces the bigger frame even though its native tag-row
  // is hidden behind smaller frames.
  const parentsMap = computeBucketParents(buckets);
  for (const { bucket, frameEl, tagRow } of frameMap.values()) {
    const ownByAgent = groupTagsByAgent(bucket.tags);
    for (const [agent, summaries] of ownByAgent) {
      tagRow.appendChild(
        buildTagPill({ agent, summaries, targetFrame: frameEl, isAncestor: false }),
      );
    }

    const parents = parentsMap.get(bucket.key) || [];
    for (const parent of parents) {
      const parentEntry = frameMap.get(parent.key);
      if (!parentEntry) continue;
      const parentByAgent = groupTagsByAgent(parent.tags);
      for (const [agent, summaries] of parentByAgent) {
        tagRow.appendChild(
          buildTagPill({
            agent,
            summaries,
            targetFrame: parentEntry.frameEl,
            isAncestor: true,
          }),
        );
      }
    }
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
    const golden = await ensureGoldenMap(slug);
    renderEmailTab(state.emailCache.get(slug), golden.emailMap);
    return;
  }
  wrap.innerHTML = `<div class="email-empty">loading…</div>`;
  try {
    const [r, golden] = await Promise.all([
      fetch(`/api/personas/${slug}/mailbox`),
      ensureGoldenMap(slug),
    ]);
    if (!r.ok) {
      wrap.innerHTML = `<div class="email-empty">No mailbox for this persona — they haven't granted Gmail access.</div>`;
      state.emailCache.set(slug, []);
      return;
    }
    const data = await r.json();
    const messages = data.messages || [];
    state.emailCache.set(slug, messages);
    renderEmailTab(messages, golden.emailMap);
  } catch (err) {
    wrap.innerHTML = `<div class="email-empty">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

// Pull the persona's golden set (cached). Returns:
//   items     — expected_task only, used for the email/calendar tab shims
//                (skips would be noise there — we want "agents that ACT
//                on this thing", not "agents that decided to ignore it")
//   allItems  — tasks + skips, used for the profile shim where line-number
//                provenance keeps things scoped tightly enough that skips
//                are meaningful signal too
//   emailMap  — email_id → Set<agent>, computed from items.evidence_email_ids
async function ensureGoldenMap(slug) {
  if (!state.goldenCache.has(slug)) {
    try {
      const r = await fetch(`/api/personas/${slug}/golden`);
      if (r.ok) state.goldenCache.set(slug, await r.json());
      else state.goldenCache.set(slug, { items: [], agents: [] });
    } catch {
      state.goldenCache.set(slug, { items: [], agents: [] });
    }
  }
  const allItems = state.goldenCache.get(slug).items || [];
  const items = allItems.filter((i) => i.kind === "expected_task");
  const emailMap = new Map();
  for (const item of items) {
    for (const eid of item.evidence_email_ids || []) {
      if (!emailMap.has(eid)) emailMap.set(eid, new Set());
      emailMap.get(eid).add(item.agent);
    }
  }
  return { items, allItems, emailMap };
}

// Heuristic word-overlap match: does any expected_task summary share a
// meaningful word (≥4 chars) with the given haystack text? Used for
// calendar events + profile sections where the schema doesn't yet carry
// explicit evidence ids.
function matchAgentsByText(haystack, items) {
  const norm = (s) => (s || "").toLowerCase();
  const tokens = (s) =>
    norm(s).split(/[^\w]+/).filter((w) => w.length >= 4);
  const haystackTokens = new Set(tokens(haystack));
  if (!haystackTokens.size) return new Set();
  const agents = new Set();
  for (const item of items) {
    const itemTokens = tokens(`${item.summary} ${item.category || ""}`);
    if (itemTokens.some((t) => haystackTokens.has(t))) agents.add(item.agent);
  }
  return agents;
}

// Apply the shim class + tag to a card-shaped element.
function applyShim(el, agents) {
  if (!agents || !agents.size) return;
  el.classList.add("golden-shim");
  const tag = document.createElement("span");
  tag.className = "golden-shim-tag";
  const labels = [...agents].map(agentLabel);
  tag.textContent = labels.join(" · ");
  tag.title = `In golden set of: ${labels.join(", ")}`;
  el.appendChild(tag);
}

function renderEmailTab(messages, goldenMap = new Map()) {
  const wrap = $("#tab-email");
  if (!messages.length) {
    wrap.innerHTML = `<div class="email-empty">No emails yet — this persona is profile-only (no Gmail connected).</div>`;
    return;
  }
  // Sort: golden-shimmed ones first (so the shimmer is visible without scrolling),
  // then newest-first within each group.
  const sorted = [...messages].sort((a, b) => {
    const aGolden = goldenMap.has(a.id) ? 0 : 1;
    const bGolden = goldenMap.has(b.id) ? 0 : 1;
    if (aGolden !== bGolden) return aGolden - bGolden;
    return (b.received_at || "").localeCompare(a.received_at || "");
  });

  wrap.innerHTML = "";
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = `Search ${sorted.length} emails…`;
  search.className = "email-search";
  wrap.appendChild(search);

  const list = document.createElement("div");
  wrap.appendChild(list);

  const cards = sorted.map((m) => buildEmailCard(m, goldenMap.get(m.id)));
  cards.forEach((c) => list.appendChild(c));

  search.addEventListener("input", () => {
    const q = search.value.toLowerCase().trim();
    cards.forEach((c) => {
      c.style.display = !q || c.dataset.haystack.includes(q) ? "" : "none";
    });
  });
}

function buildEmailCard(m, goldenAgents) {
  const card = document.createElement("div");
  card.className = "email-card";
  applyShim(card, goldenAgents);
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
    const golden = await ensureGoldenMap(slug);
    renderCalendarTab(state.calendarCache.get(slug), golden.items);
    return;
  }
  wrap.innerHTML = `<div class="calendar-empty">loading…</div>`;
  try {
    const [r, golden] = await Promise.all([
      fetch(`/api/personas/${slug}/calendar`),
      ensureGoldenMap(slug),
    ]);
    if (!r.ok) {
      wrap.innerHTML = `<div class="calendar-empty">No calendar for this persona — they haven't granted Calendar access.</div>`;
      state.calendarCache.set(slug, []);
      return;
    }
    const data = await r.json();
    const events = data.events || [];
    state.calendarCache.set(slug, events);
    renderCalendarTab(events, golden.items);
  } catch (err) {
    wrap.innerHTML = `<div class="calendar-empty">failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

function renderCalendarTab(events, goldenItems = []) {
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
      // Heuristic: any expected_task whose summary shares a 4+ char word
      // with this event's summary or description.
      const haystack = `${e.summary || ""} ${e.description || ""}`;
      applyShim(ev, matchAgentsByText(haystack, goldenItems));
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
      $$(`.trace-node[data-agent="${slug}"]`).forEach((n) => n.classList.toggle("hidden", !on));
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
// The backend emits in chronological order; the frontend only routes by
// type so each stage card stays semantically pure (rubric stuff in rubric,
// messenger stuff in messenger, etc.).
const STAGE_BY_TYPE = {
  orchestrator_started: 1,
  subagent_started: 1,
  tool_call: 1,
  tool_result: 1,
  llm_call: 1,
  subagent_returned: 1,
  dedup_decision: 1,
  task_scored: 2,
  task_emitted: 2,
  task_filtered: 2,
  message_drafted: 3,
  preference_merged: 4,
  // orchestrator_finished — intentionally unrouted; nothing to render
};

const STAGE_DEFS = [
  { no: 1, title: "Agent execution", subtitle: "9 sub-agents fan out in parallel" },
  { no: 2, title: "Rubric scoring & filter", subtitle: "score 0–7, cutoff ≥4, per-agent cap of 2" },
  { no: 3, title: "LLM reframing", subtitle: "messenger turns each kept task into user-facing copy" },
  { no: 4, title: "Preference updates", subtitle: "merged into the persona profile for future runs" },
  { no: 5, title: "Surfaced for the user", subtitle: "" },
];

async function runStream() {
  if (state.running || !state.selected) return;
  state.running = true;
  $("#run-btn").disabled = true;

  const slug = state.selected;
  const inputRaw = getDailyInputRaw().trim();

  // Reset all stage cards for a fresh run.
  initStages();
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
    finalizeStages();
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
    routeTraceEvent(data, startedAt);
  } else if (eventName === "result") {
    renderFinalStage(data);
  } else if (eventName === "error") {
    appendTraceError(data.error || "unknown error");
  }
}

// ---- staged trace renderer ----

function initStages() {
  const host = $("#trace-stages");
  host.hidden = false;
  host.innerHTML = "";
  for (const def of STAGE_DEFS) {
    const stage = document.createElement("section");
    stage.className = "stage";
    stage.id = `stage-${def.no}`;
    stage.innerHTML = `
      <div class="stage-head">
        <span class="step-no">Step ${def.no}</span>
        <h3>${def.title}</h3>
        ${def.subtitle ? `<span class="stage-sub">${def.subtitle}</span>` : ""}
      </div>
      <div class="stage-body" id="stage-${def.no}-body"></div>
    `;
    host.appendChild(stage);
  }
}

function finalizeStages() {
  // Any stage that didn't receive an event gets a "no events" placeholder
  // — clearer than an empty card with just a header.
  for (const def of STAGE_DEFS) {
    const body = document.getElementById(`stage-${def.no}-body`);
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

function routeTraceEvent(traceEvent, startedAt) {
  const stageNo = STAGE_BY_TYPE[traceEvent.type];
  if (!stageNo) return; // orchestrator_finished etc. — not displayed
  const body = document.getElementById(`stage-${stageNo}-body`);
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
  if (node) body.appendChild(node);
  autoScrollRunPanel();
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

  const cb = document.querySelector(`#filter-toggles input[data-agent="${sa}"]`);
  if (cb && !cb.checked) node.classList.add("hidden");

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

function renderFinalStage(result) {
  const body = document.getElementById("stage-5-body");
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

function appendTraceError(msg) {
  // Errors land in stage 1 since they're typically subagent failures.
  const body = document.getElementById("stage-1-body");
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

// Smart autoscroll: only follow new traces if the user is already near the
// bottom. If they've scrolled up to inspect, leave them alone.
function autoScrollRunPanel() {
  const panel = document.querySelector(".run-panel");
  if (!panel) return;
  const distanceFromBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight;
  if (distanceFromBottom < 80) {
    panel.scrollTop = panel.scrollHeight;
  }
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
