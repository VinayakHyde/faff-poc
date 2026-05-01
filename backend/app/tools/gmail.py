import json
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def make_gmail_search(persona_slug: str) -> Callable:
    """Build a `gmail_search` tool bound to one persona's mailbox."""

    @tool
    def gmail_search(
        query: str,
        start_date: str | None = None,
        end_date: str | None = None,
        max_results: int = 20,
    ) -> str:
        """Search the user's Gmail inbox for messages matching the query.

        Use this to look beyond today's slice — historical order
        confirmations, prior threads with a contact, past bill cycles, etc.

        Args:
            query: Free-text search. Matched against subject, body, sender, snippet.
            start_date: Optional earliest date (YYYY-MM-DD).
            end_date: Optional latest date (YYYY-MM-DD).
            max_results: Cap on returned messages (default 20).

        Returns:
            JSON-encoded list of matching messages, newest first.
        """
        path = DATA_DIR / persona_slug / "mailbox.json"
        if not path.exists():
            return json.dumps([])

        mailbox = json.loads(path.read_text())
        messages = mailbox.get("messages", [])
        q = query.lower().strip()

        out = []
        for m in messages:
            haystack = " ".join(
                [
                    m.get("subject", ""),
                    m.get("body", ""),
                    m.get("from", ""),
                    m.get("snippet", ""),
                ]
            ).lower()
            if q and q not in haystack:
                continue
            received = m.get("received_at", "")[:10]
            if start_date and received < start_date:
                continue
            if end_date and received > end_date:
                continue
            out.append(m)

        out.sort(key=lambda m: m.get("received_at", ""), reverse=True)
        return json.dumps(out[:max_results])

    return gmail_search
