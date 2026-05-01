"""Registry of all sub-agents.

The orchestrator (step 3) iterates ALL_AGENTS and dispatches in parallel.
"""

from app.agents import email_triage

ALL_AGENTS = [email_triage]


__all__ = ["ALL_AGENTS", "email_triage"]
