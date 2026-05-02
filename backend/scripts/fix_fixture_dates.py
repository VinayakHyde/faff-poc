"""Re-date the fixture so received_at lands on today.

Reads backend/data/users/<slug>/fixtures/<today>.json, rewrites every
gmail entry's received_at YYYY-MM-DD prefix to today's date (preserving
the original time-of-day + timezone), and writes back. Calendar events
are left as-is — they already span past + today + upcoming.
"""

import json
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "users"
TODAY = date.today().isoformat()


def fix_one(slug: str) -> None:
    fix = DATA / slug / "fixtures" / f"{TODAY}.json"
    if not fix.exists():
        # try the most recent fixture file for this persona
        fix_dir = DATA / slug / "fixtures"
        candidates = sorted(p for p in fix_dir.glob("*.json"))
        if not candidates:
            print(f"  {slug}: no fixture")
            return
        fix = candidates[-1]
    data = json.loads(fix.read_text())
    n = 0
    for m in data.get("gmail", []):
        cur = m.get("received_at", "")
        if len(cur) >= 10:
            m["received_at"] = TODAY + cur[10:]
            n += 1
    # Make sure the fixture's `date` field also says today.
    data["date"] = TODAY
    fix.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"  {slug}: rewrote {n} received_at  →  {TODAY}")


def main() -> None:
    print(f"shifting received_at to today = {TODAY}")
    for slug in ["aditi", "arjun", "devendra", "meera"]:
        fix_one(slug)


if __name__ == "__main__":
    main()
