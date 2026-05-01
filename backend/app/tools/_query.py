"""Search primitives shared by gmail_search and calendar_search.

Two layers, used together by the tools:

1. `tokenize(query)` and `tokenize_document(text)` — same algorithm:
   strip operators, split on every non-word char (so emails/domains
   become multiple tokens — `nilesh@patelassociates.com` →
   `['nilesh', 'patelassociates']`, with the `com` suffix dropped as
   a stopword), keep tokens of length ≥ 3, lowercase.

2. `bm25_rank(documents, query)` — BM25 relevance ranking, with a
   word-boundary sanity gate so short tokens like `dr` don't substring
   into `address`. `dr shah` → only `shah` survives min-length, then
   word-bounded → 0 spurious hits.

The BM25 index is rebuilt per call (cheap at POC scale, ≤100 docs/persona).
"""

from __future__ import annotations

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

# Strip Gmail-style operator prefixes like `from:foo@bar` -> `foo@bar`
_OPERATOR_PREFIXES = re.compile(
    r"\b(from|to|cc|bcc|subject|label|has|filename|in|is|after|before|older|newer):",
    flags=re.IGNORECASE,
)
_BOOLEAN_TOKENS = re.compile(r"\b(or|and|not)\b", flags=re.IGNORECASE)

# Both query and document tokens are pure alphanumerics — no @, no dots.
# Splitting on these means emails and domains become multiple tokens, so
# the indexed and query vocabularies line up.
_WORD_RE = re.compile(r"[a-z0-9]+")

MIN_TOKEN_LEN = 3

# Tiny stopword set — email/URL suffixes and the most common short fillers.
# Keeps the search lean without depending on nltk or similar.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "com", "org", "net", "edu", "gov", "pvt", "inc", "ltd", "llc",
        "the", "and", "for", "are", "has", "had", "you", "your", "from",
        "this", "that", "with", "have", "will", "but", "not", "all",
    }
)


def _split_lower(text: str) -> list[str]:
    """Lowercase + split on every non-alphanumeric char. Drops short tokens and stopwords."""
    if not text:
        return []
    return [
        t for t in _WORD_RE.findall(text.lower())
        if len(t) >= MIN_TOKEN_LEN and t not in _STOPWORDS
    ]


def tokenize(query: str) -> list[str]:
    """Lowercased token list for a user query (operators stripped first)."""
    if not query:
        return []
    cleaned = _OPERATOR_PREFIXES.sub("", query)
    cleaned = _BOOLEAN_TOKENS.sub(" ", cleaned)
    return _split_lower(cleaned)


def tokenize_document(text: str) -> list[str]:
    """Tokens for a corpus document (BM25 indexing). Same algo as queries."""
    return _split_lower(text)


@lru_cache(maxsize=1024)
def _word_pattern(token: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(token) + r"\b")


def has_word_match(haystack: str, tokens: list[str]) -> bool:
    """True if any token appears as a whole word in the haystack.

    Word-boundary matching prevents `dr` from matching `address` /
    `draft` / `drive`. A second-line defence after stopword + min-length
    drops most of the noise.
    """
    if not tokens:
        return True
    h = haystack.lower()
    return any(_word_pattern(t).search(h) for t in tokens)


def bm25_rank(
    documents: list[str],
    query: str,
) -> list[tuple[int, float]]:
    """Rank documents by BM25 relevance to query.

    Returns (document_index, score) pairs, score-descending, only
    including docs that BM25 scored > 0 AND contain at least one query
    token as a whole word. Empty/no-token query returns all docs at
    score 0; callers fall back to date sort.
    """
    tokens = tokenize(query)
    if not tokens or not documents:
        return [(i, 0.0) for i in range(len(documents))]

    corpus = [tokenize_document(d) for d in documents]
    bm25 = BM25Okapi(corpus)
    raw = bm25.get_scores(tokens)

    scored = [
        (i, float(s))
        for i, s in enumerate(raw)
        if s > 0 and has_word_match(documents[i], tokens)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
