import json
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def make_calendar_search(persona_slug: str) -> Callable:
    """Build a `calendar_search` tool bound to one persona's calendar."""

    @tool
    def calendar_search(
        query: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        max_results: int = 30,
    ) -> str:
        """Search the user's calendar for events matching the query and date window.

        Use this to look beyond the current week — past events for follow-ups,
        upcoming travel blocks, recurring patterns, birthdays already on the
        calendar.

        Args:
            query: Free-text search against event summary, location, description, attendees. Empty = no text filter.
            start_date: Optional earliest date (YYYY-MM-DD).
            end_date: Optional latest date (YYYY-MM-DD).
            max_results: Cap on returned events (default 30).

        Returns:
            JSON-encoded list of matching events, soonest first.
        """
        path = DATA_DIR / persona_slug / "calendar.json"
        if not path.exists():
            return json.dumps([])

        calendar = json.loads(path.read_text())
        events = calendar.get("events", [])
        q = query.lower().strip()

        out = []
        for e in events:
            haystack = " ".join(
                [
                    e.get("summary", ""),
                    e.get("location", ""),
                    e.get("description", ""),
                    " ".join(e.get("attendees", [])),
                ]
            ).lower()
            if q and q not in haystack:
                continue
            event_date = str(e.get("start", ""))[:10]
            if start_date and event_date < start_date:
                continue
            if end_date and event_date > end_date:
                continue
            out.append(e)

        out.sort(key=lambda e: str(e.get("start", "")))
        return json.dumps(out[:max_results])

    return calendar_search
