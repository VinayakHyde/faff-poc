"""Orchestrator — fan-out, dedup, merge, score, filter.

Per spec: "the orchestrator owns routing and merging only" (line 179).
All 8 sub-agents always run (no orchestrator-level pruning, line 108).
The orchestrator collects their outputs, dedupes near-duplicate tasks
across agents, merges preference updates, pipes the survivors through
the rubric, applies the filter (min/max/cutoff/per-agent cap), and
emits a stream of TraceEvents for the streaming UI.
"""

import asyncio

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents import ALL_AGENTS
from app.config import get_settings
from app.models import (
    CandidateTask,
    DailyInput,
    OrchestratorResult,
    PreferencesProfile,
    ScoredTask,
    SubAgentResult,
    TraceEvent,
)
from app.rubric import score_task


# ---- Filter knobs (spec-locked) ----
MIN_TASKS = 0
MAX_TASKS = 5
CUTOFF_SCORE = 4
PER_AGENT_CAP = 2


# ---- Dedup judge ----

DEDUP_SYSTEM_PROMPT = """You are the DEDUPLICATION judge for a multi-agent personal-assistant system.

8 sub-agents fan out daily; sometimes 2+ agents surface the same underlying task in different framings (e.g. "Pay Airtel bill" / "Set reminder for Airtel bill" / "Airtel postpaid due soon"). Your job: identify groups of near-duplicates, and pick the task whose `sub_agent` actually owns the underlying domain.

## Domain ownership map (use this to break ties)

- `calendar`: prep nudges, leave-now alerts, conflicts, RSVPs.
- `email_triage`: replies to personal mail, recruiter outreach, drafts.
- `food`: recurring food orders, restock nudges.
- `travel`: flight check-ins, cab booking, itineraries.
- `finance`: bill payments, subscription renewals, refunds — anything money-related.
- `dates`: birthdays, anniversaries, reach-out reminders for relationships.
- `shopping`: wishlist price drops, restock, gift purchases.
- `todos`: self-made commitments with stated deadlines.

When 2+ tasks share the same underlying intent, pick the one whose `sub_agent` is the rightful owner per the map. Examples:
- "Pay X bill" / "Reminder for X bill" / "Reply to dad about X bill" → finance owns.
- "Reply to mom" / "Reach out to mom" → email_triage owns (unless the trigger is mom's birthday, then dates).
- "Order Meghana's at 2pm" / "Lunch suggestion" → food owns.
- "Buy mom flowers for birthday" → shopping owns the purchase action; dates owns the reminder.

## Output format

Return:
- `groups`: each {keep_index, drop_indices, why_kept}
- `standalone_indices`: indices of tasks with no near-duplicates

Every input index MUST appear exactly once across (group keep_indices ∪ group drop_indices ∪ standalone_indices).

If two tasks LOOK similar but are actually distinct (e.g. "Pay Airtel bill" vs "Pay BESCOM bill"), they go in standalone_indices — they're not duplicates."""


class _DedupGroup(BaseModel):
    keep_index: int
    drop_indices: list[int] = Field(default_factory=list)
    why_kept: str


class _DedupOutput(BaseModel):
    groups: list[_DedupGroup] = Field(default_factory=list)
    standalone_indices: list[int] = Field(default_factory=list)


def _format_tasks_for_dedup(tasks: list[CandidateTask]) -> str:
    return "\n".join(
        f"[{i}] sub_agent={t.sub_agent} | title={t.title} | action={t.action[:140]}"
        for i, t in enumerate(tasks)
    )


async def _dedup_tasks(
    tasks: list[CandidateTask],
) -> tuple[list[CandidateTask], list[_DedupGroup]]:
    """Return (kept_tasks, dedup_groups). On any failure, fall back to keeping all."""
    if len(tasks) <= 1:
        return tasks, []

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(_DedupOutput)

    try:
        out: _DedupOutput = await llm.ainvoke(
            [
                ("system", DEDUP_SYSTEM_PROMPT),
                ("user", f"Tasks to dedupe:\n\n{_format_tasks_for_dedup(tasks)}"),
            ]
        )
    except Exception:
        return tasks, []  # fail-open: keep everything

    # Validate: every index appears exactly once.
    n = len(tasks)
    seen: set[int] = set()
    valid = True
    for g in out.groups:
        if not (0 <= g.keep_index < n) or g.keep_index in seen:
            valid = False
            break
        seen.add(g.keep_index)
        for d in g.drop_indices:
            if not (0 <= d < n) or d in seen:
                valid = False
                break
            seen.add(d)
    for s in out.standalone_indices:
        if not (0 <= s < n) or s in seen:
            valid = False
            break
        seen.add(s)
    if not valid or len(seen) != n:
        return tasks, []  # fail-open

    kept_indices = {g.keep_index for g in out.groups} | set(out.standalone_indices)
    kept = [t for i, t in enumerate(tasks) if i in kept_indices]
    return kept, out.groups


# ---- Filter ----

def _apply_filter(scored: list[ScoredTask]) -> list[ScoredTask]:
    """min=0, max=5, cutoff=4, per-agent cap=2.

    Order: (a) drop below cutoff, (b) sort by score desc, (c) per-agent cap, (d) global max.
    """
    above = [s for s in scored if s.total_score >= CUTOFF_SCORE]
    above.sort(key=lambda s: s.total_score, reverse=True)

    per_agent: dict[str, int] = {}
    capped: list[ScoredTask] = []
    for s in above:
        agent = s.task.sub_agent or "unknown"
        if per_agent.get(agent, 0) >= PER_AGENT_CAP:
            continue
        capped.append(s)
        per_agent[agent] = per_agent.get(agent, 0) + 1

    return capped[:MAX_TASKS]


# ---- Main entry ----

async def run(
    daily_input: DailyInput,
    profile: PreferencesProfile,
) -> OrchestratorResult:
    trace: list[TraceEvent] = []

    trace.append(
        TraceEvent(
            type="orchestrator_started",
            sub_agent="orchestrator",
            payload={"persona": profile.meta.slug, "date": daily_input.date},
        )
    )

    # ---- 1. Fan-out ----
    async def _run_one(agent) -> SubAgentResult:
        trace.append(TraceEvent(type="subagent_started", sub_agent=agent.NAME))
        try:
            r = await agent.run(daily_input, profile)
            trace.append(
                TraceEvent(
                    type="subagent_returned",
                    sub_agent=agent.NAME,
                    payload={
                        "task_count": len(r.tasks),
                        "preference_update_count": len(r.preference_updates),
                    },
                )
            )
            return r
        except Exception as e:
            trace.append(
                TraceEvent(
                    type="subagent_returned",
                    sub_agent=agent.NAME,
                    payload={"error": f"{type(e).__name__}: {e}"},
                )
            )
            return SubAgentResult(sub_agent=agent.NAME)

    sub_agent_results = await asyncio.gather(
        *(_run_one(a) for a in ALL_AGENTS)
    )

    # ---- 2. Collect ----
    all_tasks: list[CandidateTask] = []
    for r in sub_agent_results:
        all_tasks.extend(r.tasks)

    all_prefs = []
    for r in sub_agent_results:
        all_prefs.extend(r.preference_updates)

    # ---- 3. Dedup ----
    deduped, groups = await _dedup_tasks(all_tasks)
    for g in groups:
        kept = all_tasks[g.keep_index]
        dropped = [
            {"sub_agent": all_tasks[i].sub_agent, "title": all_tasks[i].title}
            for i in g.drop_indices
        ]
        trace.append(
            TraceEvent(
                type="dedup_decision",
                sub_agent="orchestrator",
                payload={
                    "kept": {"sub_agent": kept.sub_agent, "title": kept.title},
                    "dropped": dropped,
                    "why": g.why_kept,
                },
            )
        )

    # ---- 4. Merge prefs (POC: just collect; LLM-based pref dedup is later work) ----
    for p in all_prefs:
        trace.append(
            TraceEvent(
                type="preference_merged",
                sub_agent="orchestrator",
                payload={"section": p.section, "content": p.content[:120]},
            )
        )

    # ---- 5. Score ----
    scored = await asyncio.gather(*(score_task(t, profile) for t in deduped))
    for s in scored:
        trace.append(
            TraceEvent(
                type="task_scored",
                sub_agent="rubric",
                payload={
                    "title": s.task.title,
                    "score": s.total_score,
                    "agent": s.task.sub_agent,
                },
            )
        )

    # ---- 6. Filter ----
    final = _apply_filter(scored)
    final_titles = {(s.task.title, s.task.sub_agent) for s in final}
    for s in scored:
        key = (s.task.title, s.task.sub_agent)
        if key in final_titles:
            trace.append(
                TraceEvent(
                    type="task_emitted",
                    sub_agent=s.task.sub_agent,
                    payload={"title": s.task.title, "score": s.total_score},
                )
            )
        else:
            trace.append(
                TraceEvent(
                    type="task_filtered",
                    sub_agent="orchestrator",
                    payload={
                        "title": s.task.title,
                        "score": s.total_score,
                        "agent": s.task.sub_agent,
                        "reason": "below cutoff" if s.total_score < CUTOFF_SCORE else "capped",
                    },
                )
            )

    trace.append(
        TraceEvent(
            type="orchestrator_finished",
            sub_agent="orchestrator",
            payload={
                "tasks_emitted": len(final),
                "preference_updates": len(all_prefs),
                "duration_event_count": len(trace) + 1,
            },
        )
    )

    return OrchestratorResult(
        persona_slug=profile.meta.slug,
        daily_input_date=daily_input.date,
        sub_agent_results=sub_agent_results,
        merged_preference_updates=all_prefs,
        scored_tasks=scored,
        final_tasks=final,
        trace_events=trace,
    )
