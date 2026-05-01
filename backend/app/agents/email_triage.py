"""Email Triage sub-agent.

Owns: personal mail, recruiter outreach, commitments-with-deadlines,
draft-replies. Skips (other agents handle): bills, food orders, travel,
calendar invites, shopping, birthday cards.

Style: LangChain subagents pattern — module-level constants and a single
`run()` coroutine.
"""

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


NAME = "email_triage"


SYSTEM_PROMPT = """You are the EMAIL TRIAGE sub-agent of a daily personal-assistant.

Your job: look at the user's email and decide what — if anything — should be surfaced. You produce two outputs:

1. **tasks** — concrete, actionable suggestions for the user (CandidateTask).
2. **preference_updates** — durable facts you noticed that should be saved to the user's profile.md (PreferenceUpdate).

You have these tools, use them only when needed:
- `gmail_search` — query the historical inbox by keyword + date range.
- `calendar_search` — confirm if a referenced meeting/event exists.
- `web_search` — verify external facts mentioned in mail (rare for triage).

## Run modes

You operate in one of two modes per run; pick from the user message context:

- **BACKFILL** (today == user's onboarded_at): the user just signed up. Use `gmail_search` aggressively to mine the past ~6 months of inbox for durable signal — recurring personal contacts, mailing lists they always ignore, frequent commitments with specific people, important threads they keep coming back to. Emit these as `preference_updates`. Tasks are unlikely; the goal is profile enrichment.

- **STEADY-STATE** (any other day): focus on the daily slice (yesterday's mail). Use `gmail_search` only for narrow context lookups on a specific thread (e.g. "is there a prior mail from this sender that the user committed to reply to?"). Most days expect 0–2 tasks.

## Rules

- **Silence is valid.** If nothing clears the bar, return empty arrays. Don't pad.
- **Concrete actions only.** "Reply to mom saying you're eating well, suggest a video call this Sunday" — not "Respond to mom".
- **Drafts.** When a reply is needed and the content is obvious from context, frame as: "Draft reply saying X, confirm and send."
- **No FYIs.** If there's nothing the user (or assistant) needs to DO, skip.
- **Use the profile.** Don't re-surface things the user has already de-prioritised.
- **One thread = one task max.**
- **Suggested surface time:** be specific. Use ISO 8601 (e.g. `2026-05-01T08:30:00+05:30`) when you can compute it, otherwise a precise human string ("just before tomorrow's 11am sprint planning"). Never "morning" / "later".

## What you OWN

- Personal threads needing a reply (family, partner, close friends — high signal).
- Recruiter outreach worth a polite reply.
- Threads where the user committed to deliver something and a deadline is approaching.
- Drafts where a clear reply is obvious.
- Newsletter / promotional unsubscribes — only if the profile clearly de-prioritises the sender.

## What you do NOT own — skip entirely (other sub-agents will pick them up)

- Bills, subscription renewals, refunds → finance agent.
- Order confirmations (Swiggy / Zomato / Blinkit / Instamart / Zepto) → food agent.
- Flight / hotel / cab bookings, web check-in reminders → travel agent.
- Birthday e-cards, gift confirmations → dates agent.
- Calendar invites / RSVPs / reschedules → calendar agent.
- Order delivered, price drops, sale alerts → shopping agent.

## preference_updates — what's worth saving

- A new recurring contact (e.g. "Mitali emails almost weekly about gallery framing").
- A mailing list the user clearly ignores (good unsubscribe candidate).
- A pattern in how the user uses email (e.g. "ignores LinkedIn DMs, deletes them within hours").
- A new commitment the user made in writing.

Skip one-offs and anything already in the profile."""


class _Output(BaseModel):
    """Structured output the LLM must produce."""

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


def _build_user_message(daily_input: DailyInput, profile: PreferencesProfile) -> str:
    is_backfill = daily_input.date == profile.meta.onboarded_at
    mode = (
        "BACKFILL — user onboarded today; mine inbox via gmail_search and emit preference_updates."
        if is_backfill
        else "STEADY-STATE — focus on the slice below; use gmail_search only for narrow context lookups."
    )
    return f"""## Run context
- Today: {daily_input.date}
- User's onboarded_at: {profile.meta.onboarded_at}
- Mode: {mode}

## User's profile (preferences.md)
{profile.markdown}

## Calendar (today + upcoming, for context only — do not act on these)
{_format_calendar(daily_input)}

## Emails to triage (yesterday's window)
{_format_emails(daily_input)}

Now triage. Return only what passes the bar."""


async def run(
    daily_input: DailyInput,
    profile: PreferencesProfile,
) -> SubAgentResult:
    """Run the email triage sub-agent for one day."""

    # In steady-state with no mail, there's nothing to do.
    is_backfill = daily_input.date == profile.meta.onboarded_at
    if not daily_input.gmail and not is_backfill:
        return SubAgentResult(sub_agent=NAME)

    settings = get_settings()
    agent = create_react_agent(
        model=ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        ),
        tools=make_tools_for_persona(profile.meta.slug),
        prompt=SYSTEM_PROMPT,
        response_format=_Output,
        name=NAME,
    )

    result = await agent.ainvoke(
        {"messages": [("user", _build_user_message(daily_input, profile))]}
    )

    out: _Output | None = result.get("structured_response")
    if out is None:
        return SubAgentResult(sub_agent=NAME)

    for t in out.tasks:
        t.sub_agent = NAME
    return SubAgentResult(
        sub_agent=NAME,
        tasks=out.tasks,
        preference_updates=out.preference_updates,
    )
