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
- `expected_tasks`: list of `{id, summary, evidence_email_ids?, category?, notes?}`
- `expected_skips`: list of same shape
- `expected_preference_topics`: list of short strings

Each `id` must be unique within the file. The `summary` is what the LLM judge will semantically compare against the agent's output, so write it as a description of the task (not the exact wording).

Hard rule: don't include items that aren't truly your agent's domain. The golden is *your* call about correctness — be willing to defend each entry.

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

### 6. Iterate the prompt

After each run, open `backend/eval/results/<agent_name>_latest.json` and look at:

- `expected_skip_violations` — agent surfaced something out of scope. Add the offending task wording to the `# Negative examples` section of the agent prompt with a one-line "why this is wrong" explanation. Look for the *root pattern* (verb rewording? task source mining the wrong place?) and add a binding rule that prevents it.

- `expected_task_misses` — agent missed something it should have surfaced. Add a clearer IN-scope example to the relevant `## N. <category>` section, OR add a new sub-category if the missed item reveals a gap in the scope.

- `task_alignments` with `kind: "unexpected"` — agent produced a task that matches neither expected_task nor expected_skip. Decide: (a) is this actually a valid surface that you missed in the golden? then add it to `expected_tasks`. (b) is this noise? then add it as a negative example AND optionally as an `expected_skip` so future runs catch the regression.

- `preference_topic_misses` — for BACKFILL personas, agent didn't detect a pattern. Strengthen the BACKFILL section of the prompt with concrete examples of what to mine.

After 3 iterations without F1 improvement, stop and write a summary of the remaining failures — likely indicates the scope or the golden need rethinking.

---

## Acceptance criteria

- Macro F1 ≥ 0.85.
- Macro specificity = 1.00 (no skip violations on any persona).
- Macro precision ≥ 0.80.
- Vacuous-perfect personas (e.g. Meera if mailbox/calendar empty) score 1.00 on every metric — the agent must stay silent when there's no source data.
- Each iteration's prompt change is justified by a specific failure in the previous run's alignments.

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
