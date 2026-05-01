"""Registry of all sub-agents.

The orchestrator (step 3) iterates ALL_AGENTS and dispatches in parallel.
"""

from app.agents import (
    calendar,
    dates,
    email_triage,
    finance,
    food,
    shopping,
    todos,
    travel,
)

ALL_AGENTS = [
    calendar,
    email_triage,
    food,
    travel,
    finance,
    dates,
    shopping,
    todos,
]


__all__ = [
    "ALL_AGENTS",
    "calendar",
    "dates",
    "email_triage",
    "finance",
    "food",
    "shopping",
    "todos",
    "travel",
]
