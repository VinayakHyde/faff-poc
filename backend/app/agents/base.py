"""Convention every sub-agent module implements.

Modules in `app/agents/` expose:
    NAME: str                                          # canonical agent name
    SYSTEM_PROMPT: str                                 # role + rules
    async def run(daily_input, profile) -> SubAgentResult

The orchestrator (step 3) iterates `app.agents.ALL_AGENTS` and dispatches.
"""

from typing import Protocol

from app.models import DailyInput, PreferencesProfile, SubAgentResult


class SubAgentModule(Protocol):
    NAME: str

    async def run(
        self,
        daily_input: DailyInput,
        profile: PreferencesProfile,
    ) -> SubAgentResult: ...
