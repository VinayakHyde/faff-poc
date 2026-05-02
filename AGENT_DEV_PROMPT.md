# Agent Development Prompt

Use this brief once per sub-agent. The first sub-agent (`email_triage`) is already done — use it as the working example. Your job: deliver a tightened prompt + golden set + judge prompt + verified eval metrics for ONE additional agent.

---

## Mission (per agent)

For the agent assigned to you (e.g. `calendar`, `food`, `travel`, `finance`, `dates`, `shopping`, `todos`):

1. **Tighten the agent prompt** — make it hyper-specific, with two binding constraints (action shape + task source), explicit positive scope categories with IN/OUT examples, and a "negative examples (observed failures)" section.
2. **Deep-examine each persona** — read every persona's `profile.md`, `mailbox.json`, `calendar.json`, and `fixtures/2026-05-01.json`. Decide what this agent *should* surface for each persona on 2026-05-01.
3. **Write the golden set** at `backend/eval/golden/<agent_name>.json` per the schema in `backend/eval/golden/SCHEMA.md`.
4. **Write the per-agent judge prompt** at `backend/eval/judge_prompts/<agent_name>.md`. The shared base prompt at `_base.md` already covers JSON output shape and matching rules — your file only adds the agent-specific scope and common failure modes.
5. **Run the eval**: `cd backend && source venv/bin/activate && python -m eval.run <agent_name>`.
6. **Iterate the prompt** based on the alignments in `backend/eval/results/<agent_name>_latest.json` until macro F1 ≥ 0.85 and macro specificity = 1.00. Re-run after each change.

Stop when the metrics meet the bar OR when you've made 3 prompt iterations without improvement (in which case escalate with a written summary of the remaining failures).

---

## Working example: `email_triage`

Read these four files end-to-end before you start. They define the pattern.

- `backend/app/agents/email_triage.py` — the agent prompt structure.
- `backend/eval/golden/email_triage.json` — the golden set structure.
- `backend/eval/judge_prompts/email_triage.md` — the per-agent judge prompt.
- `backend/eval/results/email_triage_latest.json` — what one eval run looks like.

Match the structure and tone exactly. Same headings, same level of specificity, same "binding constraints" framing.

---

## Step-by-step

### 1. Tighten the agent prompt

The prompt lives at `backend/app/agents/<agent_name>.py`. Rewrite the `SYSTEM_PROMPT` constant. Keep the surrounding code (NAME, run() function) unchanged.

Required sections, in this order:

- **`# Role`** — one sentence saying exactly what kind of worker this is. No mention of "sub-agent", "personal assistant system", "other agents", or any sibling. The agent should think of itself as a standalone specialist.

- **`# Two binding constraints (read first, every time)`**
  - **Constraint 1 — Action shape.** What verbs are allowed at the start of the `action` field. E.g. for `food`: `Order`, `Restock`. Anything else → STOP.
  - **Constraint 2 — Task source.** What input must the task be derived from. E.g. for `calendar`: a specific calendar event in today's slice or via `calendar_search`. Profile-only tasks are not allowed.

- **`# Your scope — exactly N categories`** (positive scope only — never list other agents' domains)
  - Each category gets its own `## N. <name>` section.
  - Each category has IN scope examples and OUT scope examples (within-category — e.g. "form-letter recruiter blast is OUT of recruiter scope").
  - The OUT examples should NOT name other agents. Just say "ignore" or "out of scope here".

- **`# Examples of correct silence`** — 2–3 fixture-shaped scenarios where the right answer is empty arrays.

- **`# Negative examples (DO NOT produce these — observed failures)`** — start empty; populate from real eval failures as you iterate.

- **`# Outputs`** — 2–3 bullets describing tasks + preference_updates fields.

- **`# Tools`** — list the 3 tools (`gmail_search`, `calendar_search`, `web_search`) with one-line guidance per tool.

- **`# Run modes`** — BACKFILL vs STEADY-STATE behaviour.

- **`# Rules`** — silence is valid, concrete actions, ISO 8601 surface times, profile-aware, one source = one task.

### 2. Deep-examine each persona

Run `backend/scripts/dump_email_landscape.py` (already exists) to see the full email + sender layout per persona. For calendar-relevant agents, also read `backend/data/users/<slug>/calendar.json` carefully.

For each of the 4 personas:

- Identify the emails / events / profile entries this agent SHOULD act on.
- Identify the items that LOOK relevant but should NOT be surfaced (these become `expected_skips`).
- For BACKFILL personas (everyone except aditi), identify durable patterns the agent should detect across the full mailbox / calendar history (these become `expected_preference_topics`).

Be strict. The bar is "what would a careful human assistant for this user actually do today." Empty output is correct on many days.

### 3. Write the golden set

Save as `backend/eval/golden/<agent_name>.json`. Follow the v2 schema in `backend/eval/golden/SCHEMA.md`. Required fields per persona:

- `slug`, `mode`
- `expected_tasks`: list of ExpectedItem (see below)
- `expected_skips`: list of ExpectedItem
- `expected_preference_topics`: list of short strings

**ExpectedItem fields** (the schema is shared across `expected_tasks` and `expected_skips`):

- `id` (required) — unique within the file. The judge alignment maps actual-task → this id.
- `summary` (required) — semantic description; the LLM judge compares actual `title + action + rationale` against this.
- `evidence_email_ids` (optional) — fixture email / mailbox message ids that ground the expectation.
- `category` (optional) — per-agent scope label.
- `as_of` (optional) — ISO date when the underlying real-world fact was sourced. Required when the entry is grounded in live web data (deep-research run output).
- `valid_until` (optional) — ISO date past which this expectation should NOT be evaluated. The harness filters entries with `valid_until < evaluation_date` and treats them as N/A. Use for any item grounded in time-bound external state (current sale prices, ticket sale windows, festival prep windows). Set to `null` for profile-driven items that don't decay (most items in the email_triage / calendar / dates / finance / todos golden sets).
- `source_url` (optional) — source link for items grounded in external research; strongly recommended whenever `valid_until` is set.
- `notes` (optional) — free-text for human reviewers.

**The standard convention:** every entry in every golden file MUST include `valid_until`. Use `null` when the entry doesn't decay; use an ISO date (`"2026-08-02"`) when it does.

Hard rule: don't include items that aren't truly your agent's domain. The golden is *your* call about correctness — be willing to defend each entry.

**For agents that depend on the live web** (currently `events`, `travel`, `shopping`): use the deep-research prompts in `backend/eval/deep_research_prompts.md` to ground `expected_tasks` in real, currently-announced facts. Always include `as_of`, `valid_until`, and `source_url` for those entries. For agents that work entirely off the user's own data (`calendar`, `email_triage`, `finance`, `dates`, `todos`, `food`), most entries will have `valid_until: null`.

### 4. Write the judge prompt

Save as `backend/eval/judge_prompts/<agent_name>.md`. The shared base prompt at `_base.md` covers input/output mechanics — your file only adds:

- A 1-paragraph description of the agent's stated scope.
- A `## Common failure modes — flag these strictly` section listing what would count as a skip violation. Use bullet points with concrete bad output examples.
- A `## Borderline calls — use these heuristics` section for ambiguous cases.

Mirror the style of `backend/eval/judge_prompts/email_triage.md`.

### 5. Run the eval

```bash
cd backend
source venv/bin/activate
python -m eval.run <agent_name>
```

Output: a metrics table per persona + macro-averaged P / R / F1 / Specificity / Pref Coverage. Full alignments dumped to `backend/eval/results/<agent_name>_latest.json`.

The harness filters out any `expected_tasks` / `expected_skips` whose `valid_until` is strictly before `evaluation_date`, and prints a one-line summary per persona when entries are dropped (e.g. `[devendra] filtered expired golden: -2 tasks / -0 skips (valid_until < 2026-09-01)`). When you bump `evaluation_date` forward, expired entries are silently skipped — refresh them by re-running the relevant deep-research prompt and updating `as_of` / `valid_until` / `source_url`.

### 6. Iterate the prompt

After each run, open `backend/eval/results/<agent_name>_latest.json` and look at:

- `expected_skip_violations` — agent surfaced something out of scope. Add the offending task wording to the `# Negative examples` section of the agent prompt with a one-line "why this is wrong" explanation. Look for the *root pattern* (verb rewording? task source mining the wrong place?) and add a binding rule that prevents it.

- `expected_task_misses` — agent missed something it should have surfaced. Add a clearer IN-scope example to the relevant `## N. <category>` section, OR add a new sub-category if the missed item reveals a gap in the scope.

- `task_alignments` with `kind: "unexpected"` — agent produced a task that matches neither expected_task nor expected_skip. Decide: (a) is this actually a valid surface that you missed in the golden? then add it to `expected_tasks`. (b) is this noise? then add it as a negative example AND optionally as an `expected_skip` so future runs catch the regression.

- `preference_topic_misses` — for BACKFILL personas, agent didn't detect a pattern. Strengthen the BACKFILL section of the prompt with concrete examples of what to mine.

#### 6a. Web-dependent agents — `web_search` tool usage is usually the bottleneck

For `events`, `travel`, and `shopping` (the agents whose `expected_tasks` come from `deep_research_prompts.md`-style web research), the dominant failure mode after 1–2 iterations is rarely "the prompt's scope is wrong" — it's that the agent **isn't using `web_search` correctly**. Three concrete patterns to check before iterating on scope/verbs:

1. **Agent never calls `web_search`.** Symptom: `actual_tasks=[]` even when the deep-research-grounded `expected_tasks` are well-formed. Cause: the agent prompt's "use web_search sparingly" guardrail is too tight, so the model defaults to not searching at all. Fix: rewrite the tools section to say `web_search is REQUIRED for every profile-named artist / wishlist item / festival the user cares about — call it before deciding silence is correct` with an explicit example query (e.g. `web_search("Anuv Jain Mumbai 2026 tour dates site:district.in OR site:bookmyshow.com")`).
2. **Agent calls `web_search` but on the wrong query.** Symptom: tool calls in the trace, but they're vague (`"upcoming concerts in Bangalore"`) instead of profile-anchored. Fix: in the prompt, give 2–3 example queries that combine profile-named artist + city + ticket platform, and require the agent to formulate queries the same way.
3. **Agent calls `web_search`, gets results, but ignores them.** Symptom: tool result shows ticket-platform URLs in the trace, but the structured response still emits `tasks: []`. Cause: the structured-output step is dropping signal. Fix: make the prompt require the agent to cite `source_url` from web_search results in the task's `notes` field — if it can't cite, the task didn't survive parsing and you have a downstream bug (likely needing the same `response_format=(prompt, schema)` fix that `base.py` already carries).

These three checks usually move web-dependent agents from F1 0.20–0.40 (silence) to F1 0.80+ (correct discovery) in one iteration.

#### 6b. Escape hatch — split the prompt by mode

If you've made 3 iterations and metrics haven't improved AND the failures cluster differently for BACKFILL vs STEADY-STATE personas (e.g. BACKFILL is firing too many tasks while STEADY-STATE is silent, or vice versa), the single prompt is probably trying to serve two genuinely different jobs. Split it.

Pattern (already shipped in `dates`): replace the single `SYSTEM_PROMPT` constant with two — `BACKFILL_PROMPT` and `STEADY_STATE_PROMPT` — and pick at runtime in the agent's `run()`:

```python
async def run(daily_input, profile):
    is_backfill = daily_input.date == profile.meta.onboarded_at
    prompt = BACKFILL_PROMPT if is_backfill else STEADY_STATE_PROMPT
    return await run_subagent(NAME, prompt, daily_input, profile)
```

When to do this:
- BACKFILL needs to mine 6 months of history aggressively for `preference_updates`; STEADY-STATE needs to mine yesterday's slice and stay quiet.
- The two modes have different "silence is valid" thresholds (BACKFILL is rarely silent on prefs; STEADY-STATE often is).
- A single prompt that tries to serve both ends up over-firing on one mode and under-firing on the other.

When NOT to do this:
- Iteration is moving metrics — keep iterating the single prompt.
- The two modes' failure modes are similar (verb-prefix discipline, lane leak) — those are scope problems, not mode problems.

After splitting, re-run the eval. Each prompt is now smaller and specialised; iteration should converge faster. See commit `7ef50ff dates: split into STEADY-STATE + BACKFILL prompts → 1.00 across all metrics` for a worked example.

After 3 iterations without F1 improvement AND after trying the split-by-mode escape hatch, stop and write a summary of the remaining failures — likely indicates the scope or the golden need rethinking.

### 7. Line-number provenance (LAST step — only after metrics are at ceiling)

This step is for **human-reviewer auditability**, not the eval harness. The reviewer should be able to open the golden file, pick any expected entry, and immediately know **which lines in which source file** support it — so a future inspector can trace exactly what's contributing to the agent's good (or bad) behaviour.

For every entry in `expected_tasks` and `expected_skips` of the agent's golden file, fill in the three provenance line-number fields:

- **`profile_md_lines`** — line numbers (1-indexed) in `backend/data/users/{slug}/profile.md` that ground this expectation. Empty list if the entry isn't profile-driven.
- **`mailbox_json_lines`** — line numbers in `backend/data/users/{slug}/mailbox.json` that anchor the email(s) triggering the entry. Empty if no mailbox provenance.
- **`calendar_json_lines`** — line numbers in `backend/data/users/{slug}/calendar.json` that anchor the event(s) triggering the entry. Empty if no calendar provenance.

Workflow:

1. Open the persona's `profile.md`, `mailbox.json`, `calendar.json` side by side with the golden file.
2. For each expected entry, identify the **minimum-sufficient** lines in each source file that justify the expectation (typically 1–4 lines per source). Don't dump whole sections — pick the load-bearing lines.
3. Update the three `*_lines` fields. Empty list (`[]`) is the correct value when a source doesn't apply.
4. Re-run the eval to confirm the metrics haven't regressed (they shouldn't — these fields are metadata, not eval inputs).

Example after population:

```json
{
  "id": "aditi_mom_reply",
  "summary": "Reply to mom (Sunita) about her relational check-in.",
  "evidence_email_ids": ["msg_mom_1"],
  "category": "personal_social_emotional",
  "profile_md_lines": [121, 195],
  "mailbox_json_lines": [4, 17],
  "calendar_json_lines": [],
  "valid_until": null
}
```

This step happens **only after** Step 6 has converged (Macro F1 ≥ 0.85 and Macro Specificity = 1.00). Skipping it leaves the golden harder to audit, but doesn't block eval correctness.

---

## Acceptance criteria

- Macro F1 ≥ 0.85.
- Macro specificity = 1.00 (no skip violations on any persona).
- Macro precision ≥ 0.80.
- Vacuous-perfect personas (e.g. Meera if mailbox/calendar empty) score 1.00 on every metric — the agent must stay silent when there's no source data.
- Each iteration's prompt change is justified by a specific failure in the previous run's alignments.
- After metrics meet the bar, **Step 7 (line-number provenance) is fully populated** — every entry in `expected_tasks` and `expected_skips` has its `profile_md_lines`, `mailbox_json_lines`, `calendar_json_lines` filled in (empty lists where a source doesn't apply, real line numbers where it does).

---

## Files you produce per agent

1. `backend/app/agents/<agent_name>.py` (modified — only the `SYSTEM_PROMPT` string)
2. `backend/eval/golden/<agent_name>.json` (new)
3. `backend/eval/judge_prompts/<agent_name>.md` (new)
4. (auto-generated by harness) `backend/eval/results/<agent_name>_latest.json`

Do NOT modify any of the following:
- `backend/app/agents/base.py` (shared runtime — touch only if there's a real bug)
- `backend/app/agents/__init__.py` (already registers all 8 agents)
- Any other agent's files.
- Any persona data file (`backend/data/users/...`).
- `backend/eval/run.py` or `backend/eval/judge_prompts/_base.md`.

---

## Per-agent guidance (for assignment)

These are the 7 remaining agents. Each gets the same treatment. Notes below are starter context — you must verify against the actual personas before committing the prompt.

- **`calendar`** — prep nudges, leave-now alerts, conflicts, RSVPs, post-event follow-ups. Action shape: "Prep ...", "Leave by ...", "RSVP to ...". Task source: a specific calendar event. Only Aditi has a calendar — Arjun, Devendra, Meera have empty calendars (correct silence expected).

- **`food`** — recurring food orders, restock nudges, mealtime-gap prompts, new-restaurant nudges. Action shape: "Order ...", "Restock ...". Task source: profile-stated food patterns + email order history + calendar gaps + web_search verification. The profile food section drives most of this.

- **`travel`** — web check-in 24h before flights, cab booking ahead of departure, day-of itinerary, status alerts. Action shape: "Web check-in for ...", "Book cab for ...", "Itinerary recap ...". Task source: flight / hotel / cab emails. Many days will have nothing.

- **`finance`** — bill due nudges, subscription renewals, trial expiries, refund follow-ups, reimbursement filing. Action shape: "Pay ...", "Cancel ... trial", "Follow up on refund for ...". Task source: bill / subscription / refund emails. The personas have monthly bill cycles.

- **`dates`** — birthday/anniversary reminders with concrete gift suggestions, reach-out prompts for relationships gone cold, festival reminders. Action shape: "Wish ... happy birthday", "Reach out to ...", "Order gift for ...". Task source: profile-stated important dates + recurring all-day calendar events + relationship-history emails.

- **`shopping`** — wishlist price drops, restock alerts on stated-interest items, gift purchase actions handed off from `dates`. Action shape: "Buy ...", "Add ... to cart". Task source: profile wishlist + sale-alert emails + price-tracking via web_search. The bar is high — don't surface generic sales.

- **`todos`** — deadline-approaching reminders for self-made commitments, action items from meeting recaps. Action shape: "Send X to Y", "Deliver X by Z". Task source: emails containing the user's stated commitments ("I'll send you X by Friday") + meeting-recap emails with action-item lists.

---

## Tone for the agent prompt itself

Read `backend/app/agents/email_triage.py` once more. Match its tone exactly — direct, declarative, written like instructions to a competent worker who needs zero hand-holding but also zero ambiguity. Markdown headings, concrete examples, no apologetic language. Length: 100–200 lines is normal.

You are not writing for a paper. You are writing for a model that will follow this prompt thousands of times.
