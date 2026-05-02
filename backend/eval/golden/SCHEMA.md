# Golden-set schema (all sub-agents)

One golden JSON file per agent, all using the schema below. The eval
harness loads `<agent_name>.json`, runs the agent on each persona, asks
an LLM judge to align actual output to expected output, then computes
P/R/F1/specificity from the alignment.

## File shape

```json
{
  "agent": "<agent_name>",
  "schema_version": 2,
  "evaluation_date": "2026-05-02",
  "personas": [
    {
      "slug": "aditi",
      "mode": "STEADY-STATE",
      "expected_tasks":              [ <ExpectedItem>, ... ],
      "expected_skips":              [ <ExpectedItem>, ... ],
      "expected_preference_topics":  [ "<short topic>", ... ]
    },
    ...
  ]
}
```

## `ExpectedItem`

```json
{
  "id": "devendra_buy_golf_set_wilson",
  "summary": "Buy the Wilson Profile XD Men's Graphite Complete Set from Golf Mart India at ₹49,490 — best current price for a beginner-suitable all-graphite configuration.",
  "evidence_email_ids": [],
  "category": "wishlist_buy_now",
  "profile_md_lines": [],
  "mailbox_json_lines": [],
  "calendar_json_lines": [],
  "as_of": "2026-05-02",
  "valid_until": "2026-08-02",
  "source_url": "https://golfmartindia.com/product/wilson-profile-xd-mens-graphite-complete-golf-set/",
  "notes": "Profile lists 'considering taking up golf' — beginner full-set match. Sourced from Gemini Deep Research run on 2026-05-02."
}
```

| Field | Required | Purpose |
| --- | --- | --- |
| `id` | yes | Unique within the file. The judge alignment maps actual-task → this id. |
| `summary` | yes | Semantic description. The LLM judge compares actual `title + action + rationale` against this. |
| `evidence_email_ids` | optional | Concrete provenance — which fixture emails / mailbox messages support this expectation by message id. Useful for debugging false negatives. Complements `mailbox_json_lines` (line-number-based). |
| `category` | optional | Per-agent scope label (e.g. `personal_social_emotional`, `recurring_food_order`, `bill_due_nudge`). Used for domain-purity stats. |
| `profile_md_lines` | yes (default `[]`) | List of line numbers (1-indexed) in `data/users/{slug}/profile.md` that ground this expectation. Empty list = either the entry is not profile-driven, or the human reviewer has not yet mapped it. Populated as the **last step** after the agent's metrics are at ceiling — see `AGENT_DEV_PROMPT.md` Step 7. |
| `mailbox_json_lines` | yes (default `[]`) | List of line numbers in `data/users/{slug}/mailbox.json` that anchor this expectation (the message block that triggers it). Empty list = no mailbox provenance / not yet mapped. |
| `calendar_json_lines` | yes (default `[]`) | List of line numbers in `data/users/{slug}/calendar.json` that anchor this expectation (the event block that triggers it). Empty list = no calendar provenance / not yet mapped. |
| `as_of` | optional | ISO date (`YYYY-MM-DD`) when the underlying real-world fact was sourced (e.g. when the deep-research dump was pulled). Required for items grounded in live web data; omit / null for profile-driven items that don't decay. |
| `valid_until` | yes (default `null`) | ISO date (`YYYY-MM-DD`) past which this expectation should NOT be evaluated. The harness filters out entries where `valid_until < evaluation_date` and treats them as N/A (no penalty for missing, no credit for hitting). Use for any item grounded in time-bound external state — current sale prices, ticket sale windows, festival-prep windows, current launch status of a product. Set to `null` for profile-driven items (`Reply to mom`, `RSVP to invite ev_xxx`) that don't decay. |
| `source_url` | optional | The external source URL the fact was lifted from (deep-research result, ticket platform, retailer page). Strongly recommended whenever `valid_until` is set — gives a future maintainer a way to re-verify. |
| `notes` | optional | Free-text. Not used by the judge, just for human reviewers. |

### The line-number provenance fields (`*_lines`)

These three fields exist so a human reviewer can audit exactly **what in the user's data** supports each expected entry — and therefore what's contributing to a good (or bad) system. They are populated **after** the agent has hit its metrics bar; before that they stay `[]` as placeholders. See `AGENT_DEV_PROMPT.md` Step 7 for the workflow.

Conventions:

- Line numbers are 1-indexed (matches what editors / `cat -n` show).
- Multiple line numbers are allowed when an expectation spans several lines or several blocks (e.g. mom's identity row + the gifting cue line).
- `[]` always means "no provenance for this source" — it is the default and the placeholder. Never use `null` for these fields.
- Pick the **minimum-sufficient** lines that justify the expectation. Don't dump a whole section; pick the 1–4 lines that are load-bearing.

### When to set `valid_until`

| Item type | `valid_until` |
| --- | --- |
| `Reply to friend X about their check-in` (profile-driven) | omit / null |
| `Pay BESCOM bill due 2026-05-10` (date-stamped from email fixture) | the due date |
| `Buy iPhone 17 256GB at ₹82,900` (current price from web) | ~3 months from `as_of`, OR the next launch event ETA |
| `Tickets open for X concert on 2026-05-15` (sale-window) | the sale-open date + 7 days, OR concert date |
| `Wait for Manyavar pre-Diwali sale` (deferred) | the expected sale-open date |
| `Attend IJS Ahmedabad jewellery exhibition Jun 26-28` (event window) | the event end date |
| `Skip — admin email reframed as calendar reminder` (lane-discipline skip) | omit / null |
| `Skip — speculative bucket-list task with no live signal` (anti-speculation skip) | omit / null |

`expected_tasks` are positives — the agent **should** produce a task that matches each one.

`expected_skips` are negatives — the agent **must not** surface a task for the underlying signal. Used to measure specificity.

`expected_preference_topics` are short string topics, e.g. `"Mitali emails personally about plans"`. The judge checks if **any** of the agent's `preference_updates` semantically covers each topic.

## Metrics produced

For each persona:

```
TP = expected_tasks the agent matched
FP = actual_tasks that don't match any expected_task (or that match an expected_skip — counts double-bad)
FN = expected_tasks the agent missed
TN_proxy = expected_skips the agent correctly didn't surface

task_recall      = TP / (TP + FN)
task_precision   = TP / (TP + FP)
task_f1          = 2 * P * R / (P + R)
specificity      = TN_proxy / (TN_proxy + skips_violated)
pref_coverage    = topics_with_a_match / total_expected_topics
```

Aggregate (across all personas) reports the macro-average of each.

## LLM judge contract

One call per persona. Inputs:

- `expected_tasks` (list of {id, summary, …})
- `expected_skips` (list of {id, summary, …})
- `actual_tasks` (the agent's output)

Output:

```json
{
  "task_alignments": [
    { "actual_task_index": 0, "matched_id": "aditi_mom_reply", "kind": "expected_task" }
  ],
  "expected_task_misses": [],
  "expected_skip_violations": [],
  "preference_topic_hits": ["Mitali emails personally"]
}
```

`kind` is one of: `expected_task` (true positive), `expected_skip` (skip violation — agent surfaced something it shouldn't have), `unexpected` (matches neither — counts as a false positive).

## Writing a new golden file

1. Pick an agent.
2. Read each persona's profile + fixture + mailbox carefully.
3. For each persona:
   - List `expected_tasks` — what the agent should surface, with one entry per distinct task.
   - List `expected_skips` — items in the slice that look tempting but should NOT be surfaced (off-domain content from in-domain-looking senders, FYIs, etc.).
   - List `expected_preference_topics` — for BACKFILL personas, the high-level patterns the agent should detect in history.
4. Save as `eval/golden/<agent_name>.json`.

Each agent is self-contained; the harness handles the rest uniformly.
