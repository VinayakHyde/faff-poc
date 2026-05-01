"""Run a single sub-agent against a single persona — for prompt iteration.

Usage:
    python -m scripts.test_agent <persona_slug> <agent_name>

Example:
    python -m scripts.test_agent aditi email_triage
    python -m scripts.test_agent meera dates
"""

import asyncio
import json
import sys

from app.agents import ALL_AGENTS
from app.loaders import load_fixture, load_profile


def _by_name(name: str):
    for a in ALL_AGENTS:
        if a.NAME == name:
            return a
    available = ", ".join(sorted(a.NAME for a in ALL_AGENTS))
    raise SystemExit(f"unknown agent '{name}'. available: {available}")


async def main(slug: str, agent_name: str) -> None:
    profile = load_profile(slug)
    di = load_fixture(slug, "2026-05-01")
    mode = "BACKFILL" if di.date == profile.meta.onboarded_at else "STEADY-STATE"

    print(f"=== {agent_name} on {slug} ({mode}) ===")
    print(f"fixture: {len(di.gmail)} mail / {len(di.calendar)} events")
    print(f"profile: {len(profile.markdown):,} chars")
    print()

    agent = _by_name(agent_name)
    result = await agent.run(di, profile)

    print(f"--- TASKS ({len(result.tasks)}) ---")
    if not result.tasks:
        print("  (none — silent)")
    for t in result.tasks:
        print(f"\n  • {t.title}")
        print(f"    sub_agent       = {t.sub_agent}")
        print(f"    action          = {t.action}")
        print(f"    rationale       = {t.rationale}")
        print(f"    surface_time    = {t.suggested_surface_time}")

    print(f"\n--- PREFERENCE UPDATES ({len(result.preference_updates)}) ---")
    if not result.preference_updates:
        print("  (none)")
    for p in result.preference_updates:
        print(f"\n  • [{p.section}]")
        print(f"    content = {p.content}")
        print(f"    reason  = {p.reason}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
