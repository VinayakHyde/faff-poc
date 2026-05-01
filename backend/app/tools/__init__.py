from app.tools.calendar import make_calendar_search
from app.tools.gmail import make_gmail_search
from app.tools.web import web_search


def make_tools_for_persona(persona_slug: str) -> list:
    """Return the full tool set bound to a specific persona.

    gmail_search and calendar_search are bound to the persona's data files
    via closure. web_search is persona-agnostic.
    """
    return [
        make_gmail_search(persona_slug),
        make_calendar_search(persona_slug),
        web_search,
    ]


__all__ = [
    "make_tools_for_persona",
    "make_gmail_search",
    "make_calendar_search",
    "web_search",
]
