"""Smoke test the rubric on a spread of candidate tasks.

Uses Aditi's profile. Includes:
- A high-quality task that should score 6-7/7.
- A medium task (some criteria met).
- A low-quality task that should score 1-2/7.
- The actual task email_triage produced for Aditi (mom-reply).
"""

import asyncio

from app.loaders import load_profile
from app.models import CandidateTask
from app.rubric import score_task


GOLD_TASKS: list[CandidateTask] = [
    CandidateTask(
        sub_agent="food",
        title="Order Meghana's chicken biryani at 1:50pm",
        action="Place a Swiggy order for 1x Chicken Biryani (Regular) from Meghana's Foods (Indiranagar). Deliver by ~2:15pm to fit your usual lunch slot.",
        rationale="It's Wednesday — your established weekly biryani slot. Calendar shows a 1:30–3pm gap.",
        suggested_surface_time="2026-05-06T13:35:00+05:30",
    ),
    CandidateTask(
        sub_agent="finance",
        title="Pay BESCOM bill ₹1,193 by May 8",
        action="Pay BESCOM electricity bill (Account 4521, ₹1,193) via HDFC Diners — due May 8.",
        rationale="Bill arrived 2026-04-30; profile says nudge 3 days before due.",
        suggested_surface_time="2026-05-05T09:00:00+05:30",
    ),
    CandidateTask(
        sub_agent="email_triage",
        title="Maybe respond to LinkedIn DM",
        action="Consider replying to the LinkedIn DM from a recruiter you don't recognise.",
        rationale="It's been sitting in your inbox.",
        suggested_surface_time="morning",
    ),
    CandidateTask(
        sub_agent="email_triage",
        title="Reply to Mom and suggest a Sunday call",
        action="Send a short reply to Sunita saying you're doing fine, ask how she's doing, and suggest a quick call Sunday after yoga/brunch.",
        rationale="Personal relationship-maintenance nudge from your mom; the kind of low-effort personal mail you tend to leave hanging.",
        suggested_surface_time="2026-05-03T09:15:00+05:30",
    ),
]


def _render(scored) -> None:
    t = scored.task
    print(f"\n[{scored.total_score}/7]  ({t.sub_agent})  {t.title}")
    for c in scored.criteria:
        mark = "✓" if c.matches else "✗"
        print(f"   {mark} {c.name:30s}  {c.reasoning}")


async def main():
    profile = load_profile("aditi")
    results = await asyncio.gather(
        *(score_task(t, profile) for t in GOLD_TASKS)
    )
    print(f"=== Rubric smoke ({len(results)} tasks, persona=aditi) ===")
    for r in results:
        _render(r)

    print()
    print("Sorted by score:")
    for r in sorted(results, key=lambda r: r.total_score, reverse=True):
        print(f"  {r.total_score}/7  {r.task.title}")


if __name__ == "__main__":
    asyncio.run(main())
