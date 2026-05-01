import json
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from app.tools._query import bm25_rank, tokenize

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def _document_text(e: dict) -> str:
    return " ".join(
        [
            e.get("summary", ""),
            e.get("location", ""),
            e.get("description", ""),
            " ".join(e.get("attendees", [])),
        ]
    )


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

        Ranking is BM25 over summary + location + description + attendees,
        with whole-word matching as a sanity gate. Empty query = no text
        filter (date filter only, sorted soonest-first).

        Args:
            query: Free-text search. Tokenised, BM25-ranked, word-bounded.
            start_date: Optional earliest date (YYYY-MM-DD).
            end_date: Optional latest date (YYYY-MM-DD).
            max_results: Cap on returned events (default 30).

        Returns:
            JSON-encoded list of matching events. Empty query → soonest first.
        """
        path = DATA_DIR / persona_slug / "calendar.json"
        if not path.exists():
            return json.dumps([])

        calendar = json.loads(path.read_text())
        events = calendar.get("events", [])
        if not events:
            return json.dumps([])

        candidates = []
        for e in events:
            event_date = str(e.get("start", ""))[:10]
            if start_date and event_date < start_date:
                continue
            if end_date and event_date > end_date:
                continue
            candidates.append(e)
        if not candidates:
            return json.dumps([])

        tokens = tokenize(query)
        if not tokens:
            candidates.sort(key=lambda e: str(e.get("start", "")))
            return json.dumps(candidates[:max_results])

        docs = [_document_text(e) for e in candidates]
        ranked = bm25_rank(docs, query)
        out = [candidates[i] for i, _ in ranked]
        return json.dumps(out[:max_results])

    return calendar_search