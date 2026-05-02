# Personal Assistant Agent — POC Spec

## What we are building

A daily-running personal assistant agent that, for a given user, looks at their data for the day, figures out what tasks it can suggest or execute on the user's behalf, prioritises them, and surfaces the highest-value ones at the right time of day.

This is a POC intended to showcase the agent's technical ability and traceability — not a production system.

## Data sources

**Primary (per user)**

- Manual preferences profile — a markdown document capturing the user's preferences, interests, recurring patterns, important dates, etc. (e.g. "likes hip-hop", "orders from Meghana's Biryani regularly", "mom's birthday on X date"). Generated and stored per user.
- Gmail inbox
- Google Calendar

These three are what the agent has access to per user.

## POC interface

A web interface split into stable context (left) vs. live daily input + agent output (right).

**Left sidebar — profile selector**

- A list of demo user profiles. Selecting one loads that user's stable context into the left main panel.

**Left main panel — stable / persistent data**

- The user's preferences markdown profile — the long-lived view of who the user is, what they like, recurring patterns, important dates, etc.
- This side does not change when a new day's input is entered; it represents the agent's standing knowledge of the user.

**Right main panel — daily input + chat-style agent output**

- An input box at the top where I manually paste the day's JSON payload — i.e. what the cron job would have fetched from the Gmail + Calendar APIs for that day.
- Below it, a chat-style stream of the agent's response: the automations it identified, the steps it took, and what it's doing under the hood, rendered as HTML trace components (Andrew Ng AI-agents-course / ag-ui style).
- Each new JSON input produces a fresh agent run rendered in the same panel.
- **Sub-agent filter** — a single run produces a lot of trace nodes (orchestrator + 9 sub-agents, each with their own tool calls, candidate tasks, and preference updates), so the panel includes a filter dropdown at the top of the trace stream. The dropdown lists every sub-agent (Calendar, Email, Food, Travel, Bills, Dates, Shopping, To-dos, Events, plus Orchestrator and Rubric) with a toggle next to each — all enabled by default. Untoggling an agent hides its trace nodes so the user can isolate one agent's trace end-to-end. Pure client-side hide/show on already-rendered nodes (each node carries a `data-agent` attribute) — no re-running, no backend round-trip.

## Daily flow (cron-triggered)

A cron job triggers the agent once per day per user. The agent receives the day's input (calendar + Gmail for that day) plus the existing preferences profile.

### Step 1 — Run sub-agents in parallel

Sub-agents fan out from the orchestrator and run concurrently. Each one returns both candidate tasks (with suggested surface-time) and preference updates. Preference updates are merged and applied to the profile as part of this same step — there is no separate "update preferences first, then generate tasks" pass.

#### Sub-agent design

Task generation is hierarchical, not a single monolithic call.

- A **top-level orchestrator agent** holds the full context (preferences + today's input).
- It routes the relevant slices of context to a set of **specialised sub-agents**, each responsible for surfacing candidate tasks within their domain.
- Sub-agents are **fired in parallel**, not sequentially.

Every sub-agent has **two responsibilities** on each run:

1. Return **candidate tasks** for the day — each task includes its own **suggested time-to-surface** (e.g. "30 min before 2pm"), since the sub-agent is the one with domain context to know when its task is best delivered.
2. Return **preference updates** — any new high-signal info from today's input that should be written back to the preferences profile (new restaurant tried, flight booked, recurring meeting detected, etc.).

Both outputs flow back to the orchestrator. Preference updates from all sub-agents are merged and applied to the profile.

**Sub-agent inputs and tools:**
- **Inputs (always):** today's data slice + the user's preferences profile.
- **Tools available:**
  1. `gmail_search` — query the inbox beyond today (used for backfill on first run, and for context lookups any day).
  2. `calendar_search` — query past/future calendar beyond today's window.
  3. `web_search` — for going above-and-beyond personalisation (e.g. user loves Kanye → events agent searches for Kanye shows in their city; user loves a restaurant → food agent checks if it has a new outlet nearby).

The mental model for what these sub-agents (and the agent overall) should and shouldn't do: **think of it as a human personal assistant.** Anything a competent human assistant could plausibly do for you is in scope; anything they couldn't is out of scope.

#### Sub-agent set (v1)

Grounded in what Poke and similar proactive assistants actually ship as hero use cases (their public recipe categories are Calendar, Email, Finance, Health, Home, Productivity, Scheduling, Shopping, To-dos, Travel, plus Developer/Students). For our POC we collapse these into the smallest set that covers the recurring high-value cases an Indian user would expect:

1. **Calendar / Scheduling agent**
   - Looks at today's calendar events.
   - Surfaces: prep nudges before meetings, "leave now" alerts based on event location + travel time, conflict/double-booking flags, follow-ups for events that just ended, RSVP-needed invites.

2. **Email triage agent**
   - Looks at today's Gmail input.
   - Surfaces: emails needing a reply, threads where the user committed to something, ignored/decayed threads, unsubscribe candidates, things to read later. Drafts responses where appropriate so the user just confirms.

3. **Food & order-history agent**
   - Looks at preferences + email-derived food order history (Swiggy/Zomato confirmations, etc.).
   - Surfaces: recurring order suggestions at the right time of day ("you usually order Meghana's at 2pm Wednesdays"), restock nudges (Instamart staples), "you haven't eaten yet today" prompts when calendar gaps line up.
   - **Edge case handled here:** if no food preferences exist in the profile yet, this agent's first job is to mine email order history → infer preferences → write them back to the preferences profile (so future runs have it).

4. **Travel agent**
   - Looks at preferences + email for flights, hotels, cab/train bookings.
   - Surfaces: web check-in 24h before flights, cab booking ahead of departure, itinerary reminders, status changes from airline emails, hotel/restaurant prep for destination.

5. **Bills, subscriptions & finance agent**
   - Looks at email for bill due notices, subscription renewals, trial expiries, refunds-in-progress.
   - Surfaces: "BESCOM bill due in 3 days, pay now?", "trial ending tomorrow, cancel?", "refund hasn't landed in 7 days, follow up?".

6. **Dates, occasions & relationships agent**
   - Looks at preferences (birthdays, anniversaries, important relationships) + calendar.
   - Surfaces: birthday/anniversary reminders ahead of time with a suggested action (gift, message, call), follow-ups with people the user hasn't been in touch with for a while.

7. **Shopping & wishlist agent**
   - Looks at preferences + email for price drops, restock notifications, sale alerts on items the user has expressed interest in.
   - Surfaces: actionable buy nudges only when the item matches stated interests.

8. **To-dos & commitments agent**
   - Looks at preferences + email + calendar for things the user said they'd do ("I'll send you X by Friday", action items from meeting notes).
   - Surfaces: deadline-approaching reminders for self-made commitments.

9. **Events & discovery agent**
   - Looks at preferences (favourite artists, genres, music/cinema/theatre hobbies, bucket-list artists, alma-mater fests) + email (ticket-platform mailers and confirmations from BookMyShow / District / Paytm Insider, artist newsletters, venue announcements) + calendar (free-time windows and stated routine blocks to surface only conflict-free options).
   - Surfaces: concert / show announcements by favourite artists in the user's city, sale-window nudges the moment a high-signal date drops (e.g. user follows Anuv Jain → Aria Tour Mumbai date drops → ticket-buy nudge before tickets sell out), recurring festival reminders the user actually attends (Mood Indigo, Bacardi NH7 Weekender, Dover Lane Music Conference, Magnetic Fields, college alma-mater fests), and "saved you the FOMO" flags when a candidate event clashes with stated routines or existing calendar blocks.
   - **Edge case handled here:** if no event-attendance history exists in the profile, this agent's first job is to mine 6 months of email for ticket confirmations and platform receipts → infer attended artists / venues / genres / city circuits → write back to preferences (so future runs have it).

All sub-agents are invoked on every run — there is no orchestrator-level pruning. Each sub-agent decides for itself whether it has anything to surface; if its slice of today's input is empty, it returns no candidate tasks. Always-on fan-out keeps the orchestrator simple and ensures we never miss a category by mis-routing. (See the stretch section for the latency optimisation of pruning idle sub-agents — explicitly out of scope for the POC.) New sub-agents can be added later — Health, Home automation, Developer/PR — but v1 sticks to this set since it covers the bulk of what a human assistant would handle.

#### Preference-update edge cases at the sub-agent layer

Some sub-agents double as **preference enrichment agents** when the relevant preference slice is empty or stale. Examples:

- Food agent → no food preferences → mine 6 months of order emails → write preferences.
- Travel agent → no travel patterns → mine flight/hotel emails → infer home airport, frequent destinations, preferred airlines.
- Dates agent → birthdays missing → mine email greetings/calendar recurring events.
- Events agent → no event-attendance history → mine BookMyShow / District / Paytm Insider ticket confirmations → infer attended artists, venues, genres, festival circuits.

All sub-agents share the same write path into the preferences profile — preference updates are simply one of two outputs each sub-agent produces.

### Step 2 — Score tasks via a rubric

Each candidate task (with its proposed surface-time) goes through the rubric. Locked design principles:

- **Additive +1 scoring**, not a 1–5 scale. Each criterion the task satisfies adds +1.
- Criteria must be things an **LLM-as-judge can quantitatively grade** — clear, checkable conditions, not vibes.
- The scoring optimises for two axes: (a) how **critical** the task is, and (b) how **likely** it is the user would actually want the agent to handle it on their behalf.

Candidate criteria (each worth +1, to be finalised):

- Time-sensitive — has a hard deadline within 24h.
- Recurring pattern match — the task lines up with an established preference/history pattern.
- Has a concrete executable action (not just an FYI).
- High stakes if missed — ignoring this would have real consequences (late fee, missed flight, forgotten birthday, dropped commitment). FYIs and "try this new thing" suggestions score False here.
- **Avoids redundancy — category-aware**. Whether a task counts as "already nudged" is **not** a one-size rule; the prompt to the LLM-judge must spell out the per-category logic. Examples that need to be in the prompt:
  - **Food ordering**: weekly recurrence is fine. Re-suggesting next week even if the user ignored last week is correct.
  - **Travel (e.g. cab to airport, web check-in)**: one-shot. If suggested once and the user didn't take it up, do **not** suggest again for the same trip.
  - **Bills / subscriptions**: re-nudge as the deadline approaches (e.g. day -3, day -1) even if previously nudged, because the criticality rises.
  - **Birthdays / occasions**: one nudge ahead of time is enough; don't re-spam.
  - **Events / concerts**: one-shot per specific show. If the user ignored the Anuv Jain Mumbai sale-window nudge, do **not** re-nudge for that same show. A new show by the same artist (different city or different tour) IS a fresh nudge. Festival lineups are an exception — if a high-signal artist is added to a festival the user is already considering, re-nudge once with the lineup change.
    The subjectiveness here is real, so the rubric prompt must enumerate these category rules explicitly rather than relying on the judge to infer them.
- Matches user-stated preference category (vs. inferred / weak).
- The proposed surface-time is well-justified (not just "9am default").

Tasks above a score threshold pass through to output.

#### Output cap and cutoff (important — to be finalised)

The rubric isn't only about ranking — it also gates how many tasks make it to the user. The defaults below are starting points, calibrated against market research on notification fatigue and how real human assistants operate; they should be tuned once we see real outputs.

- **Minimum tasks per day:** `0`. It's better to surface nothing than to surface filler. If no candidate clears the score cutoff, the agent stays quiet that day. Silence is a _feature_, not a fallback.
- **Maximum tasks per day:** `N = 5` (default). Framing: 1 slot reserved for a morning briefing (consolidated calendar overview + day's high-value emails), and up to 4 in-the-moment proactive nudges through the day. Real human EAs interrupt 2–5 times a day; productivity-assistant research lands tolerable proactive frequency around 3–7/day. Above that it tips into spam.
- **Score cutoff:** `X = 4/7` (default). With ~7 additive criteria in the rubric, a task must clear a clear majority to be shown — in practice that means it must be at least time-sensitive _or_ a strong recurring pattern, plus have a concrete action and a justified surface-time. Below 4 is where weak "want to order food?" suggestions land and get dropped.
- **Per-sub-agent sub-cap:** each sub-agent capped at **2 tasks/day** to force category diversity. Without this, the top-3 tasks one day could all come from Email triage and crowd out everything else.

These four numbers (`min=0`, `max=5`, `cutoff=4/7`, `per-sub-agent=2`) are the final filter between candidate tasks and what the user actually sees. They must be called out explicitly on the architecture page, because they're as important to product feel as the rubric itself.

### Step 3 — Output

The high-priority tasks (with their suggested timing already attached from Step 1) are rendered into the trace UI on the right panel. Each step (sub-agent fan-out, candidate tasks per agent, preference updates, rubric scoring) is visible as its own HTML component so the full agent reasoning is traceable.

## Edge case — new user (first-time onboarding)

A new user is **not** missing preferences — onboarding includes a human interview that collects baseline preferences, so the preferences profile exists from day one just like for an existing user. The only thing missing is the historical signal from their Gmail + Calendar.

To bootstrap that, on first run the agent searches the past ~6 months of Gmail across important categories (food order history, flight tickets, car service, recurring services, etc.) and uses what it finds to enrich the preferences profile. (Superhuman's email assistant is a reference for the kind of category extraction we want here.)

After this backfill, the user is on the normal daily flow.

**Persona schema implication:** each persona stores an `onboarded_at` date. If `today == onboarded_at`, sub-agents run broader Gmail queries across the inbox (not just yesterday's window) to do the backfill themselves. Normal days = yesterday's slice only.

## Technical stack & engineering principles

**Stack**

- **Frontend:** HTML, CSS, JavaScript (no framework — keep it light, this is a POC).
- **Backend:** Python with FastAPI.

**Engineering principles**

- **Single Responsibility Principle (SRP)** — every module/class/function does one thing. Sub-agents in particular must each own exactly one domain; the orchestrator owns routing and merging only.
- **KISS (Keep It Simple, Stupid)** — prefer the smallest, most boring solution that works. No premature abstractions, no clever indirection, no frameworks where a function will do.
- These principles apply to both frontend and backend, and explicitly to the agent code (orchestrator, sub-agents, rubric, output formatter should each be cleanly separable).

## Extra pages (if time permits — for the presentation)

Two additional pages to support the demo. **No buttons or nav on the main page** — these are reachable only by modifying the URL, so the main interface stays clean and the extra pages are pulled up on demand during the walkthrough.

**`/drawbacks` — Drawbacks page**

- Plain list of known limitations of the current POC (false positives, missing categories, latency, eval gaps, etc.).
- Useful for pre-empting reviewer questions during the presentation.

**`/architecture` — Architecture & design rationale page**

- Mermaid diagram of the agent topology: cron trigger → orchestrator → parallel sub-agents → rubric → output.
- Notes on **how we designed the rubric** (why additive +1, why those specific criteria, what we deliberately left out, how an LLM-as-judge grades each criterion). The rubric is the most defensible/important design choice in the system, so it gets the most explanation here.
- Notes on the **output cap and score cutoff** — `min=0`, `max=5` (1 briefing + 4 proactive), `cutoff=4/7`, per-sub-agent cap of 2 — and the reasoning behind each, calibrated against notification-fatigue research and how real human assistants behave.
- **Defence points** (these are the design decisions most likely to be questioned in the presentation, so they get explicit defence here):
  - **Why `min=0` is a feature, not a bug.** Silence is correct output when nothing clears the bar. Most assistant products fail by feeling obligated to ping; we deliberately reject that. Research backs this up — excessive notifications are the dominant uninstall reason for assistant-class apps.
  - **Why `max=5` and not higher or lower.** Tied to the 3–7/day tolerable range from notification research and the 2–5/day interruption rate of real human EAs. The 1+4 split (briefing + proactive) is what makes it feel like an assistant rather than a notification feed.
  - **Why redundancy is category-aware, not global.** Re-nudging is correct for food (weekly) and bills (escalating); re-nudging is wrong for travel (one-shot) and occasions. The rubric prompt encodes these per-category rules explicitly so the LLM-judge isn't guessing.
  - **Why the rubric is additive +1 instead of a 1–5 scale.** Each +1 criterion is independently checkable by an LLM-judge; 1–5 scales drift and become vibes-based across runs.
- **Why we deliberately did NOT add quiet hours in the POC.** Quiet hours (don't ping at 11pm or 7am) is a real concern for production but explicitly out of scope for the POC. Reasoning: (a) it's a thin wrapper around the surface-time decision sub-agents already make, (b) it introduces a separate config layer that distracts from the core agentic logic the POC is trying to demonstrate, (c) edge cases like flight check-ins would need overrides anyway. **Future work**: add a configurable quiet-hours window (e.g. 8am–10pm by default) with category-level overrides for genuinely time-locked tasks. Logged here so reviewers know it was a deliberate omission, not an oversight.
- Any other design rationale that doesn't fit on the main page.

## Build plan

0. Sample personas + fake daily JSON fixtures.
1. First sub-agent + pydantic contracts (shape gets pinned here, carried forward).
2. Remaining 8 sub-agents.
3. Orchestrator (routing + parallel fan-out + preference merge).
4. Rubric scorer + filter (min/max/cutoff/per-agent cap).
5. Final LLM pass — reframes filtered tasks into user-facing copy. Trace UI itself is dumb rendering, no LLM there.
6. FastAPI endpoints, keyed by persona slug. Profile at `data/users/{slug}/profile.md`.
7. Main page (left: profile, right: input + trace stream).
8. `/architecture` page.
9. `/drawbacks` page.

## Sample personas — how to build them

Treat persona creation as a 30–40 min onboarding interview with an imagined real person. Be greedy with detail — extensive > sparse. Cover at least:

- **Identity & location:** name, age, city, neighbourhood, work.
- **Schedule:** typical weekday/weekend, work hours, recurring meetings, gym/run timings.
- **Food:** go-to restaurants, cuisines they love/hate, recurring orders (Swiggy/Zomato), Instamart staples, dietary stuff.
- **Music & hobbies:** favourite artists (so events agent can web-search shows in their city), genres, hobbies, things they're learning.
- **Travel:** home airport, frequent destinations, preferred airlines, upcoming trips.
- **Important dates (≥10):** birthdays, anniversaries, parents' anniversary, work milestones, festivals they actually celebrate.
- **Relationships:** partner/spouse name + their preferences (their favourite flowers, food, artists), close family, close friends, their birthdays and what they like.
- **Bills & subscriptions:** which providers (BESCOM, BSNL, Netflix, etc.), rough due windows.
- **Shopping & wishlist:** brands they like, items they're tracking, sale categories they care about.
- **Commitments style:** how they track to-dos, what they tend to drop, what nudges actually work on them.

Each persona also stores `onboarded_at` (see new-user edge case) so we can simulate first-run vs steady-state behaviour.

## Stretch (if time permits)

### Where do we go from here

If time allows during the POC — or as the natural next steps post-POC — these are the directions that turn this from a demo into something productionable:

- **Evals** — build an eval harness over the agent's task selection and prioritisation. Golden-set of (input → expected high-priority tasks) pairs to regression-test changes to sub-agents and rubric. LLM-as-judge for the subjective parts (was the suggested time appropriate, was the task framed well).
- **Error detection** — log every sub-agent run, every rubric score, every accept/reject decision. Surface failure modes: sub-agents returning empty when they shouldn't, rubric scoring drifting, preference updates writing junk. Tie failures back to specific inputs for replay.
- **Component-wise error analysis & improvement** — go a level deeper than overall eval. For each component independently — orchestrator routing, each sub-agent, preference-update writes, rubric scoring, surface-time decisions — define its own failure taxonomy, eval set, and improvement loop. This way a regression in (say) the Food agent doesn't get masked by the Travel agent doing well, and improvements can be made surgically rather than globally re-prompting the system.
- **Sub-agent expansion** — add the categories we deliberately skipped in v1 (Health, Home, Developer/PR, Community) once the v1 set is solid.
- **Cost & latency optimisation** — POC defaults to a strong general model for everything. In production, route by task: cheap/small models for sub-agents that do narrow extraction (email triage, bills parsing), stronger models reserved for the orchestrator and rubric. Cache repeated reads of the preferences profile and recent input. Parallelisation is already in place at the sub-agent layer, but further wins come from pruning sub-agents that have nothing to do for a given day's input before invoking them, and from streaming partial results back to the trace UI rather than waiting for the full run.
