"""Pydantic contracts shared across orchestrator, sub-agents, rubric, output.

Pinned in step 1.2 and carried through the rest of the build. Only the
fields actually used today are non-default — speculative fields stay out.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Persona data shapes — mirror the JSON files on disk
# ---------------------------------------------------------------------------


class EmailMessage(BaseModel):
    """One Gmail message. Used both in mailbox.json and in DailyInput.gmail."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    thread_id: str
    from_: str = Field(alias="from")
    to: str
    subject: str
    snippet: str = ""
    body: str = ""
    labels: list[str] = []
    received_at: datetime


class CalendarEvent(BaseModel):
    """One calendar event. Used both in calendar.json and in DailyInput.calendar."""

    id: str
    summary: str
    start: str
    end: str
    location: str = ""
    attendees: list[str] = []
    description: str = ""
    all_day: bool = False


class Meta(BaseModel):
    """Per-persona identity fields from meta.json."""

    slug: str
    name: str
    email: str
    city: str
    neighbourhood: str
    timezone: str
    onboarded_at: str  # YYYY-MM-DD


class PreferencesProfile(BaseModel):
    """A persona's standing context: their meta + the markdown profile."""

    meta: Meta
    markdown: str


class DailyInput(BaseModel):
    """Cron payload for one day — the JSON pasted into the right panel."""

    date: str  # YYYY-MM-DD
    user_slug: str
    gmail: list[EmailMessage] = []
    calendar: list[CalendarEvent] = []


# ---------------------------------------------------------------------------
# Sub-agent I/O — every sub-agent returns a SubAgentResult
# ---------------------------------------------------------------------------


class CandidateTask(BaseModel):
    """A single proposed action a sub-agent wants to surface for the user."""

    title: str
    action: str
    rationale: str
    suggested_surface_time: str
    sub_agent: str = ""  # stamped by the producing sub-agent


class PreferenceUpdate(BaseModel):
    """A new fact the agent learned today, to merge into the profile."""

    section: str
    content: str
    reason: str


class SubAgentResult(BaseModel):
    sub_agent: str
    tasks: list[CandidateTask] = []
    preference_updates: list[PreferenceUpdate] = []


# ---------------------------------------------------------------------------
# Rubric — pinned shape, fleshed out in step 4
# ---------------------------------------------------------------------------


class RubricCriterion(BaseModel):
    name: str
    matches: bool
    reasoning: str


class ScoredTask(BaseModel):
    task: CandidateTask
    criteria: list[RubricCriterion] = []
    total_score: int = 0


# ---------------------------------------------------------------------------
# Final messenger — Step 5 in the build plan
# ---------------------------------------------------------------------------


class DeliverableMessage(BaseModel):
    """Final user-facing copy for one filtered task, plus the time we'd surface it."""

    scored_task: ScoredTask
    message: str
    surface_time: str  # ISO 8601 — carried forward from the sub-agent's suggestion


# ---------------------------------------------------------------------------
# Trace events — pinned shape, used in step 5/6 by the streaming UI
# ---------------------------------------------------------------------------


TraceEventType = Literal[
    "orchestrator_started",
    "subagent_started",
    "tool_call",
    "tool_result",
    "llm_call",
    "subagent_returned",
    "dedup_decision",
    "preference_merged",
    "task_scored",
    "task_filtered",
    "task_emitted",
    "message_drafted",
    "orchestrator_finished",
]


class TraceEvent(BaseModel):
    type: TraceEventType
    sub_agent: str | None = None
    payload: dict[str, Any] = {}
    at: datetime = Field(default_factory=datetime.now)


class OrchestratorResult(BaseModel):
    """Full output of one daily run."""

    persona_slug: str
    daily_input_date: str
    sub_agent_results: list[SubAgentResult] = []
    merged_preference_updates: list[PreferenceUpdate] = []
    scored_tasks: list[ScoredTask] = []
    final_tasks: list[ScoredTask] = []
    final_messages: list[DeliverableMessage] = []
    trace_events: list[TraceEvent] = []
