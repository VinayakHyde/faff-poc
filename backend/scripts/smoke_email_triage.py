"""Smoke test the email triage sub-agent against two personas.

Aditi (steady-state, onboarded 2026-02-15) — focused on yesterday's slice.
Meera (first-run, onboarded 2026-05-01) — exercises BACKFILL mode.
"""

import asyncio
import json

from app.agents import email_triage
from app.loaders import load_fixture, load_profile


async def run_one(slug: str) -> None:
    profile = load_profile(slug)
    daily_input = load_fixture(slug, "2026-05-01")
    mode = "BACKFILL" if daily_input.date == profile.meta.onboarded_at else "STEADY-STATE"

    print(f"\n{'=' * 70}")
    print(f"  {slug}  ·  {profile.meta.name}  ·  mode={mode}")
    print(f"  fixture: {len(daily_input.gmail)} mail / {len(daily_input.calendar)} events")
    print(f"{'=' * 70}\n")

    result = await email_triage.run(daily_input, profile)
    print(json.dumps(result.model_dump(), indent=2, default=str))


async def main() -> None:
    for slug in ["aditi", "meera"]:
        await run_one(slug)


if __name__ == "__main__":
    asyncio.run(main())
