import json
from pathlib import Path
from typing import Callable

from langchain_core.tools import tool

from app.tools._query import bm25_rank, tokenize

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"


def _document_text(m: dict) -> str:
    return " ".join(
        [
            m.get("subject", ""),
            m.get("body", ""),
            m.get("from", ""),
            m.get("snippet", ""),
        ]
    )


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

        Ranking is BM25 over subject + body + sender. Whole-word matching
        is enforced as a sanity gate, so short noisy tokens like `dr` or
        `or` won't substring-match inside `address` / `or` etc. Gmail-style
        operators (`from:`, `OR`) are stripped, so writing `'Nilesh'` and
        `'from:nilesh@patelassociates.com'` give the same result. Prefer
        focused tokens; avoid stuffing many unrelated keywords.

        Args:
            query: Free-text search. Tokenised, BM25-ranked, word-bounded.
            start_date: Optional earliest date (YYYY-MM-DD).
            end_date: Optional latest date (YYYY-MM-DD).
            max_results: Cap on returned messages (default 20).

        Returns:
            JSON-encoded list of matching messages, most-relevant first.
            Empty query → newest-first by date.
        """
        path = DATA_DIR / persona_slug / "mailbox.json"
        if not path.exists():
            return json.dumps([])

        mailbox = json.loads(path.read_text())
        messages = mailbox.get("messages", [])
        if not messages:
            return json.dumps([])

        # Date-filter first so BM25 only ranks the relevant window.
        candidates = []
        for m in messages:
            received = m.get("received_at", "")[:10]
            if start_date and received < start_date:
                continue
            if end_date and received > end_date:
                continue
            candidates.append(m)
        if not candidates:
            return json.dumps([])

        tokens = tokenize(query)
        if not tokens:
            # No query → return newest-first.
            candidates.sort(key=lambda m: m.get("received_at", ""), reverse=True)
            return json.dumps(candidates[:max_results])

        docs = [_document_text(m) for m in candidates]
        ranked = bm25_rank(docs, query)
        out = [candidates[i] for i, _score in ranked]
        return json.dumps(out[:max_results])

    return gmail_search