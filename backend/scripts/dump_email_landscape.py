"""Print every email each persona has, plus the relationship/email
sections of their profile. Used to construct the email_triage golden set.

No filtering — full bodies for the fixture, full sender distribution +
sample subjects for the historical mailbox.
"""

import json
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "users"


def dump_persona(slug: str) -> None:
    print(f"\n{'='*78}\n  {slug.upper()}\n{'='*78}")
    meta = json.loads((DATA / slug / "meta.json").read_text())
    print(f"  email: {meta['email']}")
    print(f"  onboarded: {meta['onboarded_at']} (mode = "
          f"{'BACKFILL' if meta['onboarded_at'] == '2026-05-01' else 'STEADY-STATE'})")

    # Fixture in full
    fix = json.loads((DATA / slug / "fixtures" / "2026-05-01.json").read_text())
    print(f"\n  -- FIXTURE: {len(fix['gmail'])} emails (yesterday's slice) --")
    for m in fix["gmail"]:
        print(f"\n    [{m['id']}]")
        print(f"      FROM:    {m['from']}")
        print(f"      SUBJECT: {m['subject']}")
        print(f"      LABELS:  {', '.join(m.get('labels', []))}")
        print(f"      BODY:    {m['body']}")

    # Mailbox grouped by sender
    mb = json.loads((DATA / slug / "mailbox.json").read_text())
    msgs = mb.get("messages", [])
    if not msgs:
        print("\n  -- MAILBOX: empty --")
        return

    by_sender = defaultdict(list)
    for m in msgs:
        by_sender[m.get("from", "")].append(m)

    print(f"\n  -- MAILBOX: {len(msgs)} historical emails, "
          f"{len(by_sender)} unique senders --")
    for sender, ms in sorted(by_sender.items(), key=lambda x: -len(x[1])):
        ms.sort(key=lambda m: m.get("received_at", ""), reverse=True)
        print(f"\n    [{len(ms):>3d}x] {sender}")
        for m in ms[:3]:
            print(f"          {m['received_at'][:10]} | {m['subject'][:64]}")
            body = (m.get("body", "") or "").replace("\n", " ")
            print(f"                {body[:120]}")
        if len(ms) > 3:
            print(f"          ... +{len(ms)-3} more")


if __name__ == "__main__":
    for s in ["aditi", "arjun", "devendra", "meera"]:
        dump_persona(s)
