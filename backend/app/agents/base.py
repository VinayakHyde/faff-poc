"""Shared sub-agent runtime.

Every agent module exports `NAME` + `SYSTEM_PROMPT` + a thin `run()` that
delegates to `run_subagent` here. Keeps each agent file ~5 lines of code
plus the prompt. The orchestrator (step 3) iterates `ALL_AGENTS`.
"""

from typing import Protocol

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import (
    CandidateTask,
    DailyInput,
    PreferenceUpdate,
    PreferencesProfile,
    SubAgentResult,
)
from app.tools import make_tools_for_persona


class SubAgentModule(Protocol):
    NAME: str

    async def run(
        self,
        daily_input: DailyInput,
        profile: PreferencesProfile,
    ) -> SubAgentResult: ...


class _Output(BaseModel):
    """Structured output every sub-agent produces."""

    tasks: list[CandidateTask] = Field(default_factory=list)
    preference_updates: list[PreferenceUpdate] = Field(default_factory=list)


def _format_emails(daily_input: DailyInput) -> str:
    if not daily_input.gmail:
        return "_(no emails in today's slice)_"
    parts = []
    for m in daily_input.gmail:
        parts.append(
            f"[id: {m.id}]\n"
            f"FROM: {m.from_}\n"
            f"TO: {m.to}\n"
            f"SUBJECT: {m.subject}\n"
            f"RECEIVED: {m.received_at.isoformat()}\n"
            f"LABELS: {', '.join(m.labels) or '—'}\n"
            f"\n{m.body}"
        )
    return "\n\n---\n\n".join(parts)


def _format_calendar(daily_input: DailyInput) -> str:
    if not daily_input.calendar:
        return "_(no events on calendar)_"
    return "\n".join(
        f"- {e.start} → {e.end} | {e.summary} ({e.location or 'no location'})"
        for e in daily_input.calendar
    )


def build_user_message(daily_input: DailyInput, profile: PreferencesProfile) -> str:
    is_backfill = daily_input.date == profile.meta.onboarded_at
    mode = (
        "BACKFILL — user onboarded today; mine inbox/calendar via tools and emit preference_updates aggressively."
        if is_backfill
        else "STEADY-STATE — focus on the slice below; use tools only for narrow context lookups."
    )
    return f"""## Run context
- Today: {daily_input.date}
- User's onboarded_at: {profile.meta.onboarded_at}
- Mode: {mode}

## User's profile (preferences.md)
{profile.markdown}

## Calendar (today + upcoming, for context only)
{_format_calendar(daily_input)}

## Emails (yesterday's window)
{_format_emails(daily_input)}

Now run your domain. Return only what passes the bar."""


async def run_subagent(
    name: str,
    system_prompt: str,
    daily_input: DailyInput,
    profile: PreferencesProfile,
) -> SubAgentResult:
    """Build a react agent with the persona's tools, run it once, parse output."""
    settings = get_settings()
    agent = create_react_agent(
        model=ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        ),
        tools=make_tools_for_persona(profile.meta.slug),
        prompt=system_prompt,
        response_format=_Output,
        name=name,
    )

    result = await agent.ainvoke(
        {"messages": [("user", build_user_message(daily_input, profile))]}
    )

    out: _Output | None = result.get("structured_response")
    if out is None:
        return SubAgentResult(sub_agent=name)

    for t in out.tasks:
        t.sub_agent = name
    return SubAgentResult(
        sub_agent=name,
        tasks=out.tasks,
        preference_updates=out.preference_updates,
    )
