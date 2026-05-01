"""Data quality audit for persona fixtures.

Prints aggregate distributions only — no email/event content. Helps spot
unrealistic patterns: too-uniform recurring subjects, single-sender
dominance, monthly bursts, weekday skew, mismatched email addresses.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"


def _hist(counter: Counter, *, sort_key=None) -> None:
    keys = sorted(counter, key=sort_key) if sort_key else sorted(counter)
    if not keys:
        return
    max_n = max(counter.values())
    width = 30
    for k in keys:
        n = counter[k]
        bar = "#" * max(1, int(n / max_n * width)) if n else ""
        print(f"    {k}: {n:3d}  {bar}")


def audit(slug: str) -> None:
    print(f"\n{'=' * 70}\n  {slug.upper()}\n{'=' * 70}")
    meta = json.loads((DATA_DIR / slug / "meta.json").read_text())
    print(f"  meta.email: {meta.get('email', '<missing>')}")
    print(f"  onboarded_at: {meta.get('onboarded_at', '<missing>')}")

    # ---- mailbox ----
    mailbox_path = DATA_DIR / slug / "mailbox.json"
    if mailbox_path.exists():
        msgs = json.loads(mailbox_path.read_text()).get("messages", [])
        print(f"\n  GMAIL — {len(msgs)} messages")

        if msgs:
            dates = sorted(m.get("received_at", "")[:10] for m in msgs)
            print(f"    date range: {dates[0]} → {dates[-1]}")

            to_counter = Counter(m.get("to", "") for m in msgs)
            print(f"    'to' addresses ({len(to_counter)} unique):")
            for to, n in to_counter.most_common():
                print(f"      {n:3d} | {to}")

            print(f"\n    top 10 subjects (recurrence check):")
            subj_counter = Counter(m.get("subject", "") for m in msgs)
            for s, n in subj_counter.most_common(10):
                print(f"      {n:3d} | {s[:62]}")

            print(f"\n    top 10 sender domains:")
            domain_counter: Counter = Counter()
            for m in msgs:
                sender = m.get("from", "")
                if "@" in sender:
                    d = sender.split("@")[-1].rstrip(">").strip()
                    domain_counter[d] += 1
            for d, n in domain_counter.most_common(10):
                print(f"      {n:3d} | {d}")

            print(f"\n    monthly distribution:")
            month_counter = Counter(m.get("received_at", "")[:7] for m in msgs)
            _hist(month_counter)

            print(f"\n    weekday distribution:")
            wd_counter: Counter = Counter()
            for m in msgs:
                try:
                    iso = m["received_at"].replace("Z", "+00:00")
                    wd = datetime.fromisoformat(iso).strftime("%a")
                    wd_counter[wd] += 1
                except Exception:
                    pass
            for wd in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                n = wd_counter.get(wd, 0)
                bar = "#" * n
                print(f"      {wd}: {n:3d}  {bar}")

    # ---- calendar ----
    cal_path = DATA_DIR / slug / "calendar.json"
    if cal_path.exists():
        evts = json.loads(cal_path.read_text()).get("events", [])
        print(f"\n  CALENDAR — {len(evts)} events")
        if evts:
            starts = sorted(str(e.get("start", ""))[:10] for e in evts if e.get("start"))
            if starts:
                print(f"    date range: {starts[0]} → {starts[-1]}")

            print(f"\n    top 10 summaries (recurrence check):")
            summ_counter = Counter(e.get("summary", "") for e in evts)
            for s, n in summ_counter.most_common(10):
                print(f"      {n:3d} | {s[:62]}")

            print(f"\n    monthly distribution:")
            mc = Counter(str(e.get("start", ""))[:7] for e in evts)
            _hist(mc)

    # ---- fixture sanity ----
    fix_path = DATA_DIR / slug / "fixtures" / "2026-05-01.json"
    if fix_path.exists():
        f = json.loads(fix_path.read_text())
        print(f"\n  FIXTURE 2026-05-01: {len(f.get('gmail', []))} emails, {len(f.get('calendar', []))} events")
    else:
        print(f"\n  FIXTURE 2026-05-01: <missing>")


if __name__ == "__main__":
    for slug in ["aditi", "arjun", "devendra", "meera"]:
        audit(slug)
