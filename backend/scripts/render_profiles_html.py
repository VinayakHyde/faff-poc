"""Render every user profile (meta + profile.md + mailbox + calendar) into one
self-contained HTML page for visual inspection.

Usage:
    python backend/scripts/render_profiles_html.py
    # writes profiles/profiles_overview.html and opens it in your browser

The generated page is a single file: profile data is embedded as JSON in a
<script> tag, the markdown profile is rendered client-side via marked.js
(loaded from a CDN), and tabs/filters are implemented with a small vanilla-JS
controller. No build step.
"""

from __future__ import annotations

import base64
import json
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_DIR = REPO_ROOT / "backend" / "data" / "users"
PROFILES_DIR = REPO_ROOT / "profiles"
AVATARS_DIR = REPO_ROOT / "frontend" / "assets" / "avatars"
GOLDEN_DIR = REPO_ROOT / "backend" / "eval" / "golden"
OUTPUT_PATH = PROFILES_DIR / "profiles_overview.html"

USER_ORDER = ["aditi", "arjun", "devendra", "meera"]

# Which profile-markdown H2 sections each agent's golden set semantically
# depends on. Used to drive the "this section is part of <agent>'s golden"
# shimmer overlay. Only applied for a given persona if that persona has at
# least one expected_task / expected_skip / preference_topic for the agent.
AGENT_TO_PROFILE_SECTIONS: dict[str, list[str]] = {
    "calendar":     ["Schedule"],
    "dates":        ["Important Dates", "Relationships"],
    "email_triage": ["Relationships"],
    "events":       ["Schedule", "Relationships"],
    "finance":      ["Bills & Subscriptions"],
    "food":         ["Food"],
    "shopping":     ["Shopping & Wishlist"],
    "todos":        ["Commitments style"],
    "travel":       ["Travel"],
}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _image_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _golden_files() -> list[Path]:
    if not GOLDEN_DIR.exists():
        return []
    return sorted(p for p in GOLDEN_DIR.glob("*.json") if p.is_file())


def build_evidence_map() -> dict[str, dict]:
    """Build per-persona evidence: which agents' goldens reference each
    email id, calendar event id, and profile section heading.

    Returns: { slug: { "emails": {id: [agent...]},
                        "events": {id: [agent...]},
                        "profile_sections": {heading: [agent...]} } }
    """
    out: dict[str, dict] = {}
    for path in _golden_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        agent = data.get("agent")
        if not agent:
            continue
        for persona in data.get("personas", []) or []:
            slug = persona.get("slug")
            if not slug:
                continue
            bucket = out.setdefault(slug, {"emails": {}, "events": {}, "profile_sections": {}})

            items = list(persona.get("expected_tasks", []) or []) + \
                    list(persona.get("expected_skips", []) or [])
            for item in items:
                for eid in (item.get("evidence_email_ids") or []):
                    bucket["emails"].setdefault(eid, [])
                    if agent not in bucket["emails"][eid]:
                        bucket["emails"][eid].append(agent)
                for evid in (item.get("evidence_event_ids") or []):
                    bucket["events"].setdefault(evid, [])
                    if agent not in bucket["events"][evid]:
                        bucket["events"][evid].append(agent)

            has_any = bool(items) or bool(persona.get("expected_preference_topics") or [])
            if has_any:
                for section in AGENT_TO_PROFILE_SECTIONS.get(agent, []):
                    bucket["profile_sections"].setdefault(section, [])
                    if agent not in bucket["profile_sections"][section]:
                        bucket["profile_sections"][section].append(agent)

    for slug_bucket in out.values():
        for key in ("emails", "events", "profile_sections"):
            for k in slug_bucket[key]:
                slug_bucket[key][k].sort()
    return out


def collect_user(slug: str) -> dict:
    user_dir = USERS_DIR / slug
    meta = _read_json(user_dir / "meta.json")
    profile_md = _read_text(user_dir / "profile.md")
    mailbox = _read_json(user_dir / "mailbox.json").get("messages", [])
    calendar = _read_json(user_dir / "calendar.json").get("events", [])

    # Merge in fixture-only gmail/calendar items (e.g. SENT messages held only
    # in the daily fixture) so golden-set evidence ids resolve to a visible row.
    fixtures_dir = user_dir / "fixtures"
    if fixtures_dir.exists():
        seen_msg = {m.get("id") for m in mailbox if m.get("id")}
        seen_evt = {e.get("id") for e in calendar if e.get("id")}
        for fx_path in sorted(fixtures_dir.glob("*.json")):
            fx = _read_json(fx_path)
            for m in fx.get("gmail", []) or []:
                mid = m.get("id")
                if mid and mid not in seen_msg:
                    mailbox.append(m)
                    seen_msg.add(mid)
            for e in fx.get("calendar", []) or []:
                eid = e.get("id")
                if eid and eid not in seen_evt:
                    calendar.append(e)
                    seen_evt.add(eid)

    first_name = (meta.get("name") or slug).split(" ")[0]
    portrait_candidates = [
        AVATARS_DIR / f"{first_name}_arch.png",
        AVATARS_DIR / f"{slug.capitalize()}_arch.png",
        AVATARS_DIR / f"{first_name}_Profile.png",
        AVATARS_DIR / f"{slug.capitalize()}_Profile.png",
        PROFILES_DIR / f"{first_name}_Profile.png",
        PROFILES_DIR / f"{slug.capitalize()}_Profile.png",
    ]
    portrait = next((_image_data_uri(p) for p in portrait_candidates if p.exists()), None)
    arch = None

    # Sort mailbox: newest first.
    mailbox_sorted = sorted(
        mailbox, key=lambda m: m.get("received_at", ""), reverse=True
    )
    # Sort calendar: chronological.
    calendar_sorted = sorted(calendar, key=lambda e: e.get("start", ""))

    return {
        "slug": slug,
        "meta": meta,
        "profile_md": profile_md,
        "mailbox": mailbox_sorted,
        "calendar": calendar_sorted,
        "portrait": portrait,
        "arch": arch,
        "evidence": {"emails": {}, "events": {}, "profile_sections": {}},
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Profiles overview</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --bg: #0f1115;
  --panel: #161922;
  --panel-2: #1d2230;
  --border: #262c3a;
  --text: #e7eaf0;
  --muted: #8a93a6;
  --accent: #7aa2f7;
  --accent-2: #9ece6a;
  --warn: #e0af68;
  --pill: #2a3142;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
a { color: var(--accent); text-decoration: none; }
.app { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
aside.sidebar {
  border-right: 1px solid var(--border);
  background: var(--panel);
  padding: 20px 14px;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
.brand { font-weight: 700; font-size: 16px; letter-spacing: .3px; margin-bottom: 18px; color: var(--text); }
.brand small { color: var(--muted); font-weight: 400; display: block; font-size: 12px; margin-top: 4px; }
.nav-user {
  display: flex; align-items: center; gap: 10px;
  padding: 10px; border-radius: 8px; cursor: pointer; margin-bottom: 6px;
  border: 1px solid transparent;
}
.nav-user:hover { background: var(--panel-2); }
.nav-user.active { background: var(--panel-2); border-color: var(--border); }
.nav-user .avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--pill); object-fit: cover; flex-shrink: 0; }
.nav-user .name { font-weight: 600; }
.nav-user .sub { color: var(--muted); font-size: 12px; }
main { padding: 28px 36px; max-width: 1200px; }
.profile-header { display: flex; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
.profile-header img.portrait { width: 160px; height: 160px; border-radius: 14px; object-fit: cover; border: 1px solid var(--border); }
.profile-header h1 { margin: 0 0 6px; font-size: 28px; }
.profile-header .meta-grid { display: grid; grid-template-columns: repeat(2, minmax(180px, auto)); gap: 6px 24px; margin-top: 10px; color: var(--muted); font-size: 13px; }
.profile-header .meta-grid b { color: var(--text); font-weight: 500; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 18px; }
.tab { padding: 10px 16px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; font-weight: 500; }
.tab.active { color: var(--text); border-bottom-color: var(--accent); }
.tab .count { color: var(--muted); font-size: 11px; margin-left: 6px; padding: 2px 6px; background: var(--pill); border-radius: 10px; }
.tab.active .count { color: var(--text); }
.panel { display: none; }
.panel.active { display: block; }

/* Profile markdown */
.markdown {
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 22px 28px; line-height: 1.65;
}
.markdown h1 { font-size: 22px; margin-top: 0; }
.markdown h2 { font-size: 18px; margin-top: 28px; padding-bottom: 6px; border-bottom: 1px solid var(--border); color: var(--accent); }
.markdown h3 { font-size: 15px; margin-top: 18px; color: var(--accent-2); }
.markdown ul { padding-left: 22px; }
.markdown li { margin: 3px 0; }
.markdown code { background: var(--panel-2); padding: 1px 6px; border-radius: 4px; font-size: 13px; }
.markdown blockquote { border-left: 3px solid var(--accent); margin: 10px 0; padding: 4px 14px; color: var(--muted); }
.markdown em { color: var(--muted); }
.markdown strong { color: var(--text); }
.markdown table { border-collapse: collapse; margin: 10px 0; }
.markdown th, .markdown td { border: 1px solid var(--border); padding: 6px 10px; }

/* Inbox */
.toolbar { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
.toolbar input, .toolbar select {
  background: var(--panel); color: var(--text); border: 1px solid var(--border);
  padding: 8px 12px; border-radius: 8px; font-size: 13px; min-width: 180px;
}
.toolbar input:focus, .toolbar select:focus { outline: none; border-color: var(--accent); }
.toolbar .stat { color: var(--muted); font-size: 12px; margin-left: auto; }
.mail {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 16px; margin-bottom: 8px;
}
.mail summary {
  list-style: none; cursor: pointer; display: grid;
  grid-template-columns: 200px 1fr 130px; gap: 12px; align-items: baseline;
}
.mail summary::-webkit-details-marker { display: none; }
.mail .from { color: var(--text); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mail .subject { color: var(--text); }
.mail .subject .snippet { color: var(--muted); margin-left: 8px; }
.mail .date { color: var(--muted); font-size: 12px; text-align: right; }
.mail[open] { background: var(--panel-2); }
.mail .body { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); white-space: pre-wrap; color: #c7ccd8; font-size: 13px; }
.mail .labels { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.label-pill { background: var(--pill); color: var(--muted); padding: 2px 8px; border-radius: 10px; font-size: 11px; }

/* Calendar */
.month-group { margin-bottom: 24px; }
.month-group h2 { font-size: 16px; color: var(--accent); margin: 0 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.event {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 16px; margin-bottom: 8px; display: grid;
  grid-template-columns: 90px 1fr; gap: 14px; align-items: start;
}
.event.all-day { border-left: 3px solid var(--warn); }
.event .when { color: var(--muted); font-size: 12px; line-height: 1.4; }
.event .when .day { color: var(--text); font-weight: 600; font-size: 18px; display: block; }
.event .when .month { text-transform: uppercase; font-size: 11px; letter-spacing: .5px; }
.event .summary { font-weight: 500; }
.event .desc { color: var(--muted); font-size: 13px; margin-top: 4px; }
.event .extra { color: var(--muted); font-size: 12px; margin-top: 6px; display: flex; gap: 14px; flex-wrap: wrap; }
.event .extra span::before { margin-right: 5px; color: var(--accent); }
.event .extra .loc::before { content: "📍"; }
.event .extra .att::before { content: "👥"; }

.empty { color: var(--muted); padding: 30px; text-align: center; border: 1px dashed var(--border); border-radius: 10px; }

/* Golden shimmer overlay — marks elements that appear in an agent's golden set */
@keyframes golden-shim-pulse {
  0%, 100% { box-shadow: 0 0 0 1px rgba(255,196,77,0.55), 0 0 10px rgba(255,196,77,0.18); }
  50%      { box-shadow: 0 0 0 1px rgba(255,224,138,0.85), 0 0 22px rgba(255,196,77,0.45); }
}
@keyframes golden-shim-sheen {
  0%   { background-position: -180% 0; }
  100% { background-position:  280% 0; }
}
.golden-shim {
  position: relative;
  overflow: visible;
  border-color: rgba(255,196,77,0.55) !important;
  margin-top: 28px !important;
  animation: golden-shim-pulse 6s ease-in-out infinite;
}
.golden-shim::after {
  content: "";
  pointer-events: none;
  position: absolute; inset: 0;
  border-radius: inherit;
  background: linear-gradient(110deg,
    transparent 35%,
    rgba(255,232,170,0.10) 48%,
    rgba(255,232,170,0.22) 50%,
    rgba(255,232,170,0.10) 52%,
    transparent 65%);
  background-size: 220% 100%;
  animation: golden-shim-sheen 8s linear infinite;
  mix-blend-mode: screen;
}
.golden-shim .golden-shim-tag {
  position: absolute;
  top: -11px;
  right: 6px;
  max-width: calc(100% - 12px);
  background: linear-gradient(90deg, #c9892b, #f3c456 55%, #fde79a);
  color: #1a1306;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid rgba(255,232,170,0.7);
  box-shadow: 0 1px 3px rgba(0,0,0,0.35), 0 0 8px rgba(255,196,77,0.35);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  z-index: 2;
}
.markdown .golden-shim {
  border: 1px solid rgba(255,196,77,0.55);
  border-radius: 10px;
  padding: 4px 16px 14px;
  margin: 32px 0 18px;
  background: rgba(255,196,77,0.035);
}
.markdown .golden-shim > h2 {
  border-bottom: 1px solid rgba(255,196,77,0.25);
  margin-top: 8px;
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">Profiles overview<small>__GENERATED_AT__</small></div>
    <div id="nav"></div>
  </aside>
  <main id="main"></main>
</div>

<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const today = new Date();
  const sameYear = d.getFullYear() === today.getFullYear();
  const opts = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
  if (!sameYear) opts.year = 'numeric';
  return d.toLocaleString(undefined, opts);
}

function monthKey(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return 'Unknown';
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

function monthLabel(key) {
  const [y, m] = key.split('-');
  return MONTHS[Number(m) - 1] + ' ' + y;
}

function renderNav() {
  const nav = document.getElementById('nav');
  nav.innerHTML = DATA.users.map((u, i) => `
    <div class="nav-user" data-slug="${u.slug}">
      ${u.portrait ? `<img class="avatar" src="${u.portrait}" alt="">` : `<div class="avatar"></div>`}
      <div>
        <div class="name">${escapeHtml(u.meta.name || u.slug)}</div>
        <div class="sub">${escapeHtml(u.meta.city || '')}</div>
      </div>
    </div>
  `).join('');
  nav.querySelectorAll('.nav-user').forEach(el => {
    el.addEventListener('click', () => selectUser(el.dataset.slug));
  });
}

function renderProfile(u) {
  const m = u.meta;
  const profileHtml = u.profile_md ? marked.parse(u.profile_md) : '<div class="empty">No profile.md</div>';
  return `
    <div class="profile-header">
      ${u.portrait ? `<img class="portrait" src="${u.portrait}" alt="">` : ''}
      <div>
        <h1>${escapeHtml(m.name || u.slug)}</h1>
        <div class="meta-grid">
          <div><b>Email</b> <span>${escapeHtml(m.email || '—')}</span></div>
          <div><b>City</b> <span>${escapeHtml(m.city || '—')}</span></div>
          <div><b>Neighbourhood</b> <span>${escapeHtml(m.neighbourhood || '—')}</span></div>
          <div><b>Timezone</b> <span>${escapeHtml(m.timezone || '—')}</span></div>
          <div><b>Onboarded</b> <span>${escapeHtml(m.onboarded_at || '—')}</span></div>
          <div><b>Slug</b> <span>${escapeHtml(u.slug)}</span></div>
        </div>
      </div>
    </div>
    <div class="tabs">
      <div class="tab active" data-tab="profile">Profile</div>
      <div class="tab" data-tab="inbox">Inbox <span class="count">${u.mailbox.length}</span></div>
      <div class="tab" data-tab="calendar">Calendar <span class="count">${u.calendar.length}</span></div>
      ${u.arch ? '<div class="tab" data-tab="arch">Architecture</div>' : ''}
    </div>
    <div class="panel active" data-panel="profile"><div class="markdown">${profileHtml}</div></div>
    <div class="panel" data-panel="inbox">${renderInbox(u)}</div>
    <div class="panel" data-panel="calendar">${renderCalendar(u)}</div>
    ${u.arch ? `<div class="panel" data-panel="arch"><img src="${u.arch}" style="width:100%;border:1px solid var(--border);border-radius:12px"></div>` : ''}
  `;
}

function renderInbox(u) {
  if (!u.mailbox.length) return '<div class="empty">Empty mailbox</div>';
  const labels = new Set();
  const senders = new Set();
  u.mailbox.forEach(msg => {
    (msg.labels || []).forEach(l => labels.add(l));
    if (msg.from) senders.add(msg.from);
  });
  const labelOpts = ['<option value="">All labels</option>']
    .concat([...labels].sort().map(l => `<option value="${escapeHtml(l)}">${escapeHtml(l)}</option>`)).join('');
  const senderOpts = ['<option value="">All senders</option>']
    .concat([...senders].sort().map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`)).join('');

  const evMap = (u.evidence && u.evidence.emails) || {};
  const rows = u.mailbox.map((msg, idx) => {
    const agents = evMap[msg.id] || [];
    const shim = agents.length ? ' golden-shim' : '';
    const tag = agents.length
      ? `<span class="golden-shim-tag" title="In golden set of: ${escapeHtml(agents.join(', '))}">${escapeHtml(agents.join(' · '))}</span>`
      : '';
    return `
    <details class="mail${shim}" data-idx="${idx}"
      data-labels="${escapeHtml((msg.labels || []).join('|'))}"
      data-from="${escapeHtml(msg.from || '')}"
      data-search="${escapeHtml(((msg.subject||'') + ' ' + (msg.from||'') + ' ' + (msg.snippet||'') + ' ' + (msg.body||'')).toLowerCase())}">
      <summary>
        ${tag}
        <span class="from">${escapeHtml(msg.from || '—')}</span>
        <span class="subject"><b>${escapeHtml(msg.subject || '(no subject)')}</b><span class="snippet"> — ${escapeHtml(msg.snippet || '')}</span></span>
        <span class="date">${escapeHtml(fmtDate(msg.received_at))}</span>
      </summary>
      <div class="body">${escapeHtml(msg.body || '(no body)')}</div>
      <div class="labels">${(msg.labels || []).map(l => `<span class="label-pill">${escapeHtml(l)}</span>`).join('')}</div>
    </details>
  `;
  }).join('');

  return `
    <div class="toolbar">
      <input type="search" placeholder="Search subject, sender, body…" data-mail-search>
      <select data-mail-label>${labelOpts}</select>
      <select data-mail-sender>${senderOpts}</select>
      <span class="stat" data-mail-stat>${u.mailbox.length} messages</span>
    </div>
    <div data-mail-list>${rows}</div>
  `;
}

function renderCalendar(u) {
  if (!u.calendar.length) return '<div class="empty">No calendar events</div>';
  const evMap = (u.evidence && u.evidence.events) || {};
  const groups = {};
  u.calendar.forEach(ev => {
    const key = monthKey(ev.start);
    (groups[key] = groups[key] || []).push(ev);
  });
  const keys = Object.keys(groups).sort();
  return keys.map(key => `
    <div class="month-group">
      <h2>${monthLabel(key)}</h2>
      ${groups[key].map(ev => {
        const d = new Date(ev.start);
        const day = isNaN(d) ? '?' : d.getDate();
        const mon = isNaN(d) ? '' : MONTHS[d.getMonth()];
        const time = ev.all_day
          ? 'all day'
          : (isNaN(d) ? '' : d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}));
        const endTime = ev.all_day || !ev.end ? '' : (() => {
          const e = new Date(ev.end);
          return isNaN(e) ? '' : ' – ' + e.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        })();
        const agents = evMap[ev.id] || [];
        const shim = agents.length ? ' golden-shim' : '';
        const tag = agents.length
          ? `<span class="golden-shim-tag" title="In golden set of: ${escapeHtml(agents.join(', '))}">${escapeHtml(agents.join(' · '))}</span>`
          : '';
        return `
          <div class="event ${ev.all_day ? 'all-day' : ''}${shim}">
            ${tag}
            <div class="when">
              <span class="day">${day}</span>
              <span class="month">${mon}</span>
              <div>${escapeHtml(time + endTime)}</div>
            </div>
            <div>
              <div class="summary">${escapeHtml(ev.summary || '(untitled)')}</div>
              ${ev.description ? `<div class="desc">${escapeHtml(ev.description)}</div>` : ''}
              <div class="extra">
                ${ev.location ? `<span class="loc">${escapeHtml(ev.location)}</span>` : ''}
                ${(ev.attendees && ev.attendees.length) ? `<span class="att">${escapeHtml(ev.attendees.join(', '))}</span>` : ''}
              </div>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `).join('');
}

function bindTabs(root) {
  const tabs = root.querySelectorAll('.tab');
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    root.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.dataset.panel === t.dataset.tab));
  }));
}

function bindMailFilter(root) {
  const search = root.querySelector('[data-mail-search]');
  const labelSel = root.querySelector('[data-mail-label]');
  const senderSel = root.querySelector('[data-mail-sender]');
  const stat = root.querySelector('[data-mail-stat]');
  const list = root.querySelector('[data-mail-list]');
  if (!list) return;
  const items = [...list.querySelectorAll('.mail')];
  function apply() {
    const q = (search.value || '').toLowerCase().trim();
    const lab = labelSel.value;
    const snd = senderSel.value;
    let visible = 0;
    items.forEach(it => {
      const labels = it.dataset.labels.split('|');
      const matches = (!q || it.dataset.search.includes(q))
        && (!lab || labels.includes(lab))
        && (!snd || it.dataset.from === snd);
      it.style.display = matches ? '' : 'none';
      if (matches) visible++;
    });
    stat.textContent = visible + ' of ' + items.length + ' messages';
  }
  [search, labelSel, senderSel].forEach(el => el && el.addEventListener('input', apply));
}

function decorateProfileSections(root, u) {
  const sectionMap = (u.evidence && u.evidence.profile_sections) || {};
  if (!Object.keys(sectionMap).length) return;
  const md = root.querySelector('.panel[data-panel="profile"] .markdown');
  if (!md) return;
  const headings = [...md.querySelectorAll('h2')];
  headings.forEach(h2 => {
    const text = (h2.textContent || '').trim();
    const agents = sectionMap[text];
    if (!agents || !agents.length) return;
    const wrap = document.createElement('div');
    wrap.className = 'golden-shim';
    wrap.setAttribute('data-section', text);
    const tag = document.createElement('span');
    tag.className = 'golden-shim-tag';
    tag.title = 'In golden set of: ' + agents.join(', ');
    tag.textContent = agents.join(' · ');
    h2.parentNode.insertBefore(wrap, h2);
    wrap.appendChild(tag);
    let node = h2;
    while (node) {
      const next = node.nextSibling;
      wrap.appendChild(node);
      if (next && next.nodeType === 1 && next.tagName === 'H2') break;
      node = next;
    }
  });
}

function selectUser(slug) {
  const u = DATA.users.find(x => x.slug === slug) || DATA.users[0];
  document.querySelectorAll('.nav-user').forEach(el => el.classList.toggle('active', el.dataset.slug === u.slug));
  const main = document.getElementById('main');
  main.innerHTML = renderProfile(u);
  bindTabs(main);
  bindMailFilter(main);
  decorateProfileSections(main, u);
  history.replaceState(null, '', '#' + u.slug);
}

renderNav();
const initial = location.hash.slice(1) || DATA.users[0]?.slug;
if (initial) selectUser(initial);
</script>
</body>
</html>
"""


def main() -> int:
    if not USERS_DIR.exists():
        print(f"error: users directory not found at {USERS_DIR}", file=sys.stderr)
        return 1

    users = [collect_user(slug) for slug in USER_ORDER if (USERS_DIR / slug).exists()]
    if not users:
        print("error: no user data found", file=sys.stderr)
        return 1

    evidence_map = build_evidence_map()
    for u in users:
        u["evidence"] = evidence_map.get(u["slug"], {"emails": {}, "events": {}, "profile_sections": {}})

    from datetime import datetime
    payload = {"users": users}
    html = (
        HTML_TEMPLATE
        .replace("__DATA_JSON__", json.dumps(payload).replace("</", "<\\/"))
        .replace("__GENERATED_AT__", "Generated " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    )

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)")
    print(f"users: {', '.join(u['slug'] for u in users)}")

    if "--no-open" not in sys.argv:
        webbrowser.open(OUTPUT_PATH.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
