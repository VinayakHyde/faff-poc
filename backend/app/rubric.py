"""Rubric scorer.

Each candidate task surfaced by a sub-agent is scored against 7
independent criteria. The criteria are spec-locked (see POC_Spec.md
under "Step 2 — Score tasks via a rubric"). Scoring is additive +1 —
each criterion the task satisfies adds 1. Max score = 7.

Score computation is deterministic: the LLM only judges per-criterion
match + reasoning. The integer total is summed in code afterwards so
the rubric can never round / inflate / drift the total.

A small downstream filter (step in the orchestrator, not here) will
apply min=0, max=5, cutoff=4, per-sub-agent cap=2.
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import (
    CandidateTask,
    PreferencesProfile,
    RubricCriterion,
    ScoredTask,
)


CRITERIA_ORDER = [
    "time_sensitive",
    "recurring_pattern_match",
    "concrete_action",
    "low_risk_if_ignored",
    "non_redundant",
    "matches_stated_preference",
    "well_justified_surface_time",
]


SYSTEM_PROMPT = """You are the RUBRIC scorer for a daily personal-assistant agent.

You evaluate ONE candidate task at a time against 7 independent criteria. For each, you decide `matches=True` or `False` and give a one-sentence `reasoning`. The integer total is summed downstream — you do not produce it.

## Design principles you must respect

- Additive +1 scoring. No partial credit.
- Judgments must be quantitatively checkable. If you can't point to a specific reason, default to False.
- Optimise for: (a) how CRITICAL the task is, and (b) how LIKELY the user actually wants the agent to handle it on their behalf.

## The 7 criteria — return them in this exact order

1. **time_sensitive** — has a hard deadline within 24h, or refers to an event happening in the next 24h. A specific time anchor must be visible. "Sometime soon" → False. "Bill due in 3 days" → False (more than 24h). "Mom's birthday in 5 days" → False (more than 24h).

2. **recurring_pattern_match** — the task lines up with a recurring pattern explicitly described in the profile (e.g. "Wednesday biryani at 2pm", "Sunday brunch at Glen's"). One-offs and weak inferences → False.

3. **concrete_action** — the `action` describes a specific executable step (place an order, send a draft, book a cab, pay a bill, call a person). Vague "follow up" / "consider" / "review" with no specific output → False.

4. **low_risk_if_ignored** — if the user ignores or rejects this, consequences are reversible / minor. Bill nudges, gift suggestions, food orders → True. Flight check-in / hospital duty alerts where missing it has hard consequences → False.

5. **non_redundant** — the task is not already covered by something noted in the profile as recently handled. Default to True unless the profile clearly indicates this exact thing was just done. (POC: there's no notification log yet, so True is the right default in absence of evidence.)

6. **matches_stated_preference** — the task aligns with an EXPLICITLY stated preference in the profile (a named restaurant, a named person, a stated routine). Inferred / weak signals → False.

7. **well_justified_surface_time** — `suggested_surface_time` is tied to a real anchor (calendar event, hard deadline, daily routine). "9am default" / "morning" / "later today" with no anchor → False.

Return exactly 7 criteria objects in the order above."""


class _Output(BaseModel):
    criteria: list[RubricCriterion] = Field(default_factory=list)


def _build_user_message(task: CandidateTask, profile: PreferencesProfile) -> str:
    return f"""## User profile (preferences)
{profile.markdown}

## Candidate task to score

- **sub_agent:** {task.sub_agent}
- **title:** {task.title}
- **action:** {task.action}
- **rationale:** {task.rationale}
- **suggested_surface_time:** {task.suggested_surface_time}

Score against the 7 criteria, in the fixed order. Each criterion: matches (bool) + one-sentence reasoning."""


async def score_task(
    task: CandidateTask,
    profile: PreferencesProfile,
) -> ScoredTask:
    """Score one candidate task. Returns a ScoredTask with criteria + summed total."""
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(_Output)

    out: _Output = await llm.ainvoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", _build_user_message(task, profile)),
        ]
    )

    # Deterministic sum — never trust the LLM with arithmetic.
    total = sum(1 for c in out.criteria if c.matches)
    return ScoredTask(task=task, criteria=out.criteria, total_score=total)
