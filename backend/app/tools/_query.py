"""Shared query tokenizer for gmail_search and calendar_search.

The LLM tends to issue Gmail-style queries with operators (`from:foo`,
`OR`, multi-word phrases). Real Gmail parses these; our local JSON store
doesn't. We strip the operators, split on whitespace, and OR-match the
remaining tokens — so a query like
    'from:nilesh@patelassociates.com OR audit review FY25'
becomes the token set
    {'nilesh@patelassociates.com', 'audit', 'review', 'fy25'}
and a message matches if ANY token appears anywhere in the haystack.
"""

import re

_OPERATOR_PREFIXES = re.compile(
    r"\b(from|to|cc|bcc|subject|label|has|filename|in|is|after|before|older|newer):",
    flags=re.IGNORECASE,
)
_BOOLEAN_TOKENS = re.compile(r"\b(or|and|not)\b", flags=re.IGNORECASE)
_NON_TOKEN_CHARS = re.compile(r"[^\w@.\-+]")


def tokenize(query: str) -> list[str]:
    """Lowercased token list with Gmail operators + boolean keywords stripped.

    Tokens shorter than 2 chars are dropped. Empty input returns []
    (callers treat empty-token-list as 'no filter — return everything').
    """
    if not query:
        return []
    cleaned = _OPERATOR_PREFIXES.sub("", query.lower())
    cleaned = _BOOLEAN_TOKENS.sub(" ", cleaned)
    cleaned = _NON_TOKEN_CHARS.sub(" ", cleaned)
    return [t for t in cleaned.split() if len(t) >= 2]


def matches_any(haystack: str, tokens: list[str]) -> bool:
    """True if any token appears as a substring of the lowercased haystack."""
    if not tokens:
        return True
    h = haystack.lower()
    return any(t in h for t in tokens)
