"""Shared sub-agent runtime.

Every agent module exports `NAME` + `SYSTEM_PROMPT` + a thin `run()` that
delegates to `run_subagent` here. Keeps each agent file ~5 lines of code
plus the prompt. The orchestrator (step 3) iterates `ALL_AGENTS`.
"""

import json
from typing import Any, Callable, Protocol
from uuid import UUID

import openai._compat as _openai_compat
import openai.lib._parsing._completions as _openai_parse_completions
from langchain_core.callbacks import AsyncCallbackHandler
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


# Type of the per-agent emit callable wired in by the orchestrator. It takes
# (event_type, payload) and stamps sub_agent itself.
EmitFn = Callable[[str, dict[str, Any]], None]


def _truncate(s: str, n: int = 600) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


class _TraceCallbackHandler(AsyncCallbackHandler):
    """Bridge LangChain/LangGraph callbacks into orchestrator trace events.

    Emits one `tool_call` per `on_tool_start` and one `tool_result` per
    `on_tool_end` (paired by run_id so the result knows which tool it
    belonged to). Emits one `llm_call` per `on_chat_model_end` carrying
    model name + token usage when the model exposes it.
    """

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit
        self._tool_names: dict[UUID, str] = {}

    async def on_tool_start(  # type: ignore[override]
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "tool"
        self._tool_names[run_id] = name
        # input_str is langchain's stringified arg blob. Try to parse it as
        # JSON for nicer pretty-printing in the trace UI; fall back to raw.
        parsed: Any
        try:
            parsed = json.loads(input_str)
        except Exception:
            parsed = input_str
        self._emit("tool_call", {"tool": name, "input": parsed})

    async def on_tool_end(  # type: ignore[override]
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        name = self._tool_names.pop(run_id, "tool")
        # Tool outputs are often huge JSON blobs (web_search returns full
        # Tavily response). Summarize when possible: count list-shaped
        # results, truncate long strings.
        text = str(output) if not isinstance(output, str) else output
        summary: dict[str, Any] = {"tool": name}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                summary["result_count"] = len(parsed)
                summary["preview"] = parsed[:3]
            elif isinstance(parsed, dict):
                # Tavily returns {"results": [...], "query": ...}
                if "results" in parsed and isinstance(parsed["results"], list):
                    summary["result_count"] = len(parsed["results"])
                    summary["preview"] = [
                        {k: r.get(k) for k in ("title", "url") if k in r}
                        for r in parsed["results"][:3]
                    ]
                else:
                    summary["output"] = _truncate(text)
            else:
                summary["output"] = _truncate(text)
        except Exception:
            summary["output"] = _truncate(text)
        self._emit("tool_result", summary)

    async def on_chat_model_end(  # type: ignore[override]
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        usage: dict[str, Any] = {}
        model_name: str | None = None
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            if msg is not None and getattr(msg, "usage_metadata", None):
                usage = dict(msg.usage_metadata)
            if msg is not None and getattr(msg, "response_metadata", None):
                model_name = msg.response_metadata.get("model_name") or msg.response_metadata.get("model")
        except Exception:
            pass
        if not model_name:
            model_name = (response.llm_output or {}).get("model_name") if hasattr(response, "llm_output") else None
        payload: dict[str, Any] = {"model": model_name or "unknown"}
        if usage:
            payload["tokens"] = usage
        self._emit("llm_call", payload)


# Some chat models occasionally emit a valid JSON object followed by trailing
# prose / a stray newline, which Pydantic's strict `model_validate_json`
# rejects. The OpenAI structured-output path goes through
# `_openai_compat.model_parse_json`, so we monkey-patch it to fall back to
# parsing just the first JSON object via `JSONDecoder.raw_decode` when strict
# parsing fails. Strict parsing remains the default; this only kicks in on
# malformed-trailing-content errors.
_orig_model_parse_json = _openai_compat.model_parse_json


def _lenient_model_parse_json(model, data):  # type: ignore[no-untyped-def]
    try:
        return _orig_model_parse_json(model, data)
    except Exception:
        text = data.decode() if isinstance(data, (bytes, bytearray)) else str(data)
        obj, _idx = json.JSONDecoder().raw_decode(text.lstrip())
        return model.model_validate(obj)


_openai_compat.model_parse_json = _lenient_model_parse_json
_openai_parse_completions.model_parse_json = _lenient_model_parse_json


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
    lines = []
    for e in daily_input.calendar:
        attendees = f" | attendees: {', '.join(e.attendees)}" if e.attendees else ""
        lines.append(
            f"- [id: {e.id}] {e.start} → {e.end} | {e.summary} "
            f"({e.location or 'no location'}){attendees}"
        )
    return "\n".join(lines)


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
    *,
    emit: EmitFn | None = None,
) -> SubAgentResult:
    """Build a react agent with the persona's tools, run it once, parse output.

    If `emit` is provided, every tool invocation and LLM call inside the
    react loop is forwarded as a TraceEvent (`tool_call`, `tool_result`,
    `llm_call`) so the streaming UI can show what the agent actually did.
    """
    settings = get_settings()
    agent = create_react_agent(
        model=ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        ),
        tools=make_tools_for_persona(profile.meta.slug),
        prompt=system_prompt,
        # langgraph's structured-response node makes a SEPARATE LLM call that
        # only receives `state["messages"]` — the agent's system prompt is
        # NOT prepended to that call by default. Passing response_format as
        # a (system_prompt, schema) tuple makes langgraph prepend our prompt
        # to that call too, which is critical for prompt-driven discipline
        # (lane rules, silence, etc.) on the final output.
        response_format=(system_prompt, _Output),
        name=name,
    )

    config: dict[str, Any] = {}
    if emit is not None:
        config["callbacks"] = [_TraceCallbackHandler(emit)]

    # Retry once on transient structured-output parse errors (some models
    # occasionally emit a valid JSON object followed by trailing whitespace
    # or a stray line, which the strict OpenAI parser rejects).
    last_err: Exception | None = None
    for _ in range(2):
        try:
            result = await agent.ainvoke(
                {"messages": [("user", build_user_message(daily_input, profile))]},
                config=config,
            )
            break
        except Exception as e:
            last_err = e
    else:
        raise last_err  # type: ignore[misc]

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
