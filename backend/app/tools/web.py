import json

from langchain_core.tools import tool

from app.config import get_settings  # noqa: F401  (ensures .env is loaded)

_tavily = None


def _get_tavily():
    global _tavily
    if _tavily is None:
        from langchain_tavily import TavilySearch

        _tavily = TavilySearch(max_results=5)
    return _tavily


@tool
def web_search(query: str) -> str:
    """Search the public web for current information.

    Use this to enrich personalisation — concert dates for an artist the
    user loves in their city, restaurant openings, event details mentioned
    in email, sale dates, news on a person they follow.

    Args:
        query: Free-text search query.

    Returns:
        JSON-encoded search results.
    """
    result = _get_tavily().invoke({"query": query})
    return json.dumps(result, default=str)
