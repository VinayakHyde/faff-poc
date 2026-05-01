"""Run all 8 sub-agents on each persona, rubric-score every candidate
task, and write a readable markdown report to PIPELINE_TEST.md.

This is a manual end-to-end test of step 1.3 + step 2 + step 4 wired
together. The orchestrator (step 3) hasn't been written yet — this
script just calls .run() on every registered agent in parallel,
collects all the SubAgentResults, and pipes their tasks through the
rubric.
"""

import asyncio
from pathlib import Path

from app.agents import ALL_AGENTS
from app.loaders import load_fixture, load_profile
from app.models import PreferencesProfile, ScoredTask, SubAgentResult
from app.rubric import score_task


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "PIPELINE_TEST.md"


async def _safe_run(agent, di, profile) -> SubAgentResult | Exception:
    try:
        return await agent.run(di, profile)
    except Exception as e:
        return e


async def _safe_score(task, profile) -> ScoredTask | Exception:
    try:
        return await score_task(task, profile)
    except Exception as e:
        return e


async def run_persona(slug: str, date: str = "2026-05-01"):
    profile = load_profile(slug)
    di = load_fixture(slug, date)
    mode = "BACKFILL" if di.date == profile.meta.onboarded_at else "STEADY-STATE"

    print(f"  [{slug}] running 8 agents in parallel...", flush=True)
    raw_results = await asyncio.gather(
        *(_safe_run(a, di, profile) for a in ALL_AGENTS)
    )

    # Collect (agent, result-or-exception) pairs
    agent_results = list(zip(ALL_AGENTS, raw_results))

    # Score every task across all successful agents in parallel
    all_tasks: list = []
    for _agent, r in agent_results:
        if isinstance(r, SubAgentResult):
            all_tasks.extend(r.tasks)

    print(f"  [{slug}] scoring {len(all_tasks)} candidate tasks...", flush=True)
    scored_list = await asyncio.gather(
        *(_safe_score(t, profile) for t in all_tasks)
    )
    score_by_id = {id(t): s for t, s in zip(all_tasks, scored_list)}

    return profile, di, mode, agent_results, score_by_id


def _render_task(scored_or_task, score_by_id) -> str:
    """Render one task with its rubric breakdown (if scored)."""
    if isinstance(scored_or_task, ScoredTask):
        scored = scored_or_task
    else:
        # Look up via id() — same object identity
        scored = score_by_id.get(id(scored_or_task))

    if scored is None or isinstance(scored, Exception):
        # No score available
        t = scored_or_task if not isinstance(scored_or_task, ScoredTask) else scored_or_task.task
        return (
            f"- **[?/7] {t.title}**\n"
            f"  - Action: {t.action}\n"
            f"  - Rationale: {t.rationale}\n"
            f"  - Surface time: `{t.suggested_surface_time}`\n"
            f"  - _Rubric scoring failed or skipped._\n"
        )

    t = scored.task
    out = [
        f"- **[{scored.total_score}/7] {t.title}**\n",
        f"  - Action: {t.action}\n",
        f"  - Rationale: {t.rationale}\n",
        f"  - Surface time: `{t.suggested_surface_time}`\n",
        f"  - Rubric:\n",
    ]
    for c in scored.criteria:
        mark = "✓" if c.matches else "✗"
        out.append(f"    - {mark} `{c.name}` — {c.reasoning}\n")
    return "".join(out)


def render_persona(profile, di, mode, agent_results, score_by_id) -> str:
    out: list[str] = []
    out.append(f"\n---\n\n## `{profile.meta.slug}` — {profile.meta.name}\n\n")
    out.append(
        f"- **Mode:** {mode}\n"
        f"- **Onboarded:** {profile.meta.onboarded_at}\n"
        f"- **Today's slice:** {len(di.gmail)} emails / {len(di.calendar)} events\n"
    )

    # Aggregate
    total_tasks = sum(len(r.tasks) for _a, r in agent_results if isinstance(r, SubAgentResult))
    total_prefs = sum(len(r.preference_updates) for _a, r in agent_results if isinstance(r, SubAgentResult))
    out.append(f"- **Surfaced:** {total_tasks} candidate tasks, {total_prefs} preference updates\n\n")

    # Ranked summary table
    all_scored = []
    for _agent, r in agent_results:
        if isinstance(r, SubAgentResult):
            for t in r.tasks:
                s = score_by_id.get(id(t))
                if isinstance(s, ScoredTask):
                    all_scored.append(s)

    if all_scored:
        all_scored.sort(key=lambda s: s.total_score, reverse=True)
        out.append("### Ranked tasks\n\n| Score | Agent | Title |\n| ---: | --- | --- |\n")
        for s in all_scored:
            out.append(f"| {s.total_score}/7 | `{s.task.sub_agent}` | {s.task.title} |\n")
        out.append("\n")

    # Per-agent breakdown
    out.append("### Per-agent results\n")
    for agent, r in agent_results:
        name = agent.NAME
        if isinstance(r, Exception):
            out.append(f"\n#### `{name}` — **errored**\n\n```\n{type(r).__name__}: {r}\n```\n")
            continue
        out.append(f"\n#### `{name}` — {len(r.tasks)} task(s), {len(r.preference_updates)} pref update(s)\n\n")
        if not r.tasks and not r.preference_updates:
            out.append("_(silence — nothing surfaced)_\n")
            continue
        for t in r.tasks:
            out.append(_render_task(t, score_by_id))
        for p in r.preference_updates:
            out.append(
                f"- **Preference update** → `{p.section}`\n"
                f"  - Content: {p.content}\n"
                f"  - Reason: {p.reason}\n"
            )

    return "".join(out)


async def main() -> None:
    parts: list[str] = []
    parts.append("# Pipeline Test — 8 sub-agents + rubric scoring\n\n")
    parts.append(
        "Auto-generated by `backend/scripts/pipeline_test.py`. Each persona is run "
        "through every sub-agent in parallel; every surfaced candidate task is "
        "scored against the 7-criterion rubric (additive +1, max 7).\n"
    )

    for slug in ["aditi", "arjun", "devendra", "meera"]:
        print(f"\n=== {slug} ===", flush=True)
        result = await run_persona(slug)
        parts.append(render_persona(*result))

    OUTPUT_PATH.write_text("".join(parts))
    print(f"\nwrote {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
