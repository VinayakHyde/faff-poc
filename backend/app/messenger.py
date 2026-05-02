"""Final LLM pass — reframe each filtered task into user-facing copy.

Step 5 in the build plan. Inputs are the rubric-filtered ScoredTasks +
the user's profile (for tone). Output is one short notification-style
message per task, plus the ISO 8601 surface_time the sub-agent already
proposed. The trace UI itself is dumb rendering — all phrasing
decisions happen here.

One LLM call per task, run in parallel by the orchestrator.
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import DeliverableMessage, PreferencesProfile, ScoredTask


SYSTEM_PROMPT = """You are the FINAL MESSENGER for a daily personal-assistant agent. A sub-agent has already decided WHAT to surface and WHEN; the rubric has already decided this task is worth showing the user. Your only job is to phrase the message the user will actually read in their notification.

# Output

A single `message` string — the exact text we'd send. Treat it like a high-quality push notification or assistant SMS, not an email.

# Hard constraints

- **Length:** 1–2 sentences. Hard cap 220 characters. If you cannot say it in 2 sentences, you are over-explaining.
- **Voice:** second-person, addressed directly to the user. "Mom emailed yesterday — want to send a quick reply?" beats "User should reply to mom".
- **Concrete:** keep specific names, amounts, dates, deadlines from the task's `action` field. Strip generic filler.
- **Tone:** match the user's stated tone preference from the profile's "Notes for the assistant" / equivalent section. Examples:
  - "friendly-direct, no filler, occasional Hindi-English code-switch is fine" → casual + crisp.
  - "Formal but warm. No slang." → keep it polite, no contractions.
  - "warm, terse, slightly maternal" → short, caring.
  Default to friendly-neutral if the profile says nothing.
- **No meta-language.** Don't say "I noticed", "Here is a reminder", "The agent suggests". Just say the thing.
- **No emoji** unless the user's profile explicitly shows they like them.
- **One ask, one line of context.** A typical message is "<one-line context>. <one-line ask or action>?" — e.g. `"BESCOM ₹1,193 due Sun May 10 — account 4521. Pay on HDFC Diners?"`.
- **Preserve the action verb.** If the task's action is `Pay X`, your message phrases it as a payment, not a "check on" or "look into".

# Input shape

You will receive:
- The user's profile markdown (use it for the user's name, tone preference, and any context that lets the message land).
- The scored task's `title`, `action`, `rationale`, `sub_agent`, and the rubric criteria that fired (for context — do NOT mention the rubric to the user).
- The `suggested_surface_time` (for context only — the harness emits this verbatim, you do not need to repeat it in the message unless the time is itself the point).

Return ONE field: `message`. The surface_time is carried forward by the harness."""


class _Output(BaseModel):
    message: str = Field(..., description="The user-facing notification text.")


def _format_criteria(s: ScoredTask) -> str:
    return ", ".join(c.name for c in s.criteria if c.matches) or "(none)"


def _build_user_message(scored: ScoredTask, profile: PreferencesProfile) -> str:
    t = scored.task
    return f"""## User profile (for tone + name + relevant context)
{profile.markdown}

## Task to phrase
- **sub_agent:** {t.sub_agent}
- **title:** {t.title}
- **action:** {t.action}
- **rationale:** {t.rationale}
- **suggested_surface_time:** {t.suggested_surface_time}
- **rubric criteria fired ({scored.total_score}/7):** {_format_criteria(scored)}

Write the message. One field: `message`. 1–2 sentences. ≤220 chars. Match the user's tone preference."""


async def draft_message(
    scored: ScoredTask,
    profile: PreferencesProfile,
) -> DeliverableMessage:
    """Reframe one scored task into user-facing copy. surface_time is carried verbatim."""
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(_Output)

    out: _Output = await llm.ainvoke(
        [
            ("system", SYSTEM_PROMPT),
            ("user", _build_user_message(scored, profile)),
        ]
    )

    return DeliverableMessage(
        scored_task=scored,
        message=out.message.strip(),
        surface_time=scored.task.suggested_surface_time,
    )
