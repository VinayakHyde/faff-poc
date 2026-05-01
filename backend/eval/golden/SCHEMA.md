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
  "evaluation_date": "2026-05-01",
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
  "id": "aditi_mom_reply",
  "summary": "Reply to mom (Sunita) about her relational check-in.",
  "evidence_email_ids": ["msg_mom_1"],
  "category": "personal_social_emotional",
  "notes": "Profile says Aditi tends to drop personal emails — nudge fits."
}
```

| Field | Required | Purpose |
| --- | --- | --- |
| `id` | yes | Unique within the file. The judge alignment maps actual-task → this id. |
| `summary` | yes | Semantic description. The LLM judge compares actual `title + action + rationale` against this. |
| `evidence_email_ids` | optional | Concrete provenance — which fixture emails / mailbox messages support this expectation. Useful for debugging false negatives. |
| `category` | optional | Per-agent scope label (e.g. `personal_social_emotional`, `recurring_food_order`, `bill_due_nudge`). Used for domain-purity stats. |
| `notes` | optional | Free-text. Not used by the judge, just for human reviewers. |

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
