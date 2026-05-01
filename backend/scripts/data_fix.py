"""Apply quality fixes to persona fixtures based on the audit findings.

Operations:
1. Normalize `to` on every mailbox message to match meta.email.
2. Devendra: drop placeholder `example.com` sender emails.
3. Trim over-recurring delivery/food subjects on Arjun, Devendra, Meera
   (Aditi's Meghana's pattern stays — matches her profile).
4. Empty calendars for everyone except Aditi.
5. Regenerate fixtures/2026-05-01.json as a derived slice of mailbox+calendar.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def normalize_to(slug: str) -> str:
    meta = _load(DATA_DIR / slug / "meta.json")
    email = meta["email"]
    mb_path = DATA_DIR / slug / "mailbox.json"
    mb = _load(mb_path)
    for m in mb.get("messages", []):
        m["to"] = email
    _save(mb_path, mb)
    return email


def remove_messages(slug: str, predicate) -> int:
    mb_path = DATA_DIR / slug / "mailbox.json"
    mb = _load(mb_path)
    before = len(mb.get("messages", []))
    mb["messages"] = [m for m in mb.get("messages", []) if not predicate(m)]
    _save(mb_path, mb)
    return before - len(mb["messages"])


def trim_by(slug: str, predicate, keep: int) -> int:
    """Trim messages matching `predicate` down to `keep` count, evenly spaced by date."""
    mb_path = DATA_DIR / slug / "mailbox.json"
    mb = _load(mb_path)
    msgs = mb.get("messages", [])
    matching = [m for m in msgs if predicate(m)]
    others = [m for m in msgs if not predicate(m)]
    if len(matching) <= keep:
        return 0
    matching.sort(key=lambda m: m.get("received_at", ""))
    step = len(matching) / keep
    kept = [matching[int(i * step)] for i in range(keep)]
    new_msgs = others + kept
    new_msgs.sort(key=lambda m: m.get("received_at", ""))
    mb["messages"] = new_msgs
    _save(mb_path, mb)
    return len(matching) - len(kept)


def empty_calendar(slug: str) -> None:
    path = DATA_DIR / slug / "calendar.json"
    if path.exists():
        _save(path, {"events": []})


def regen_fixture(slug: str, date: str = "2026-05-01") -> tuple[int, int]:
    mb = _load(DATA_DIR / slug / "mailbox.json")
    cal_path = DATA_DIR / slug / "calendar.json"
    cal = _load(cal_path) if cal_path.exists() else {"events": []}

    yesterday = "2026-04-30"
    week_end = "2026-05-07"

    gmail_slice = [
        m for m in mb.get("messages", [])
        if m.get("received_at", "")[:10] == yesterday
    ]
    cal_slice = [
        e for e in cal.get("events", [])
        if date <= str(e.get("start", ""))[:10] <= week_end
    ]

    fixture = {
        "date": date,
        "user_slug": slug,
        "gmail": gmail_slice,
        "calendar": cal_slice,
    }
    out_path = DATA_DIR / slug / "fixtures" / f"{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _save(out_path, fixture)
    return len(gmail_slice), len(cal_slice)


def main() -> None:
    print("== 1. normalize `to` addresses ==")
    for slug in ["aditi", "arjun", "devendra", "meera"]:
        print(f"   {slug}: {normalize_to(slug)}")

    print("\n== 2. devendra: drop example.com placeholders ==")
    n = remove_messages("devendra", lambda m: "example.com" in m.get("from", "").lower())
    print(f"   removed {n} placeholder emails")

    print("\n== 3. trim over-recurring delivery/food (keep Aditi as-is) ==")

    # Arjun: 24 food orders → 10
    a1 = trim_by("arjun", lambda m: "Flurys" in m.get("subject", ""), keep=4)
    a2 = trim_by("arjun", lambda m: "Amber" in m.get("subject", ""), keep=4)
    a3 = trim_by("arjun", lambda m: "Kareem" in m.get("subject", ""), keep=2)
    print(f"   arjun: trimmed Flurys -{a1}, Amber -{a2}, Kareem -{a3}")

    # Devendra: 24 food orders → 8
    d1 = trim_by("devendra", lambda m: "Swati Snacks" in m.get("subject", ""), keep=4)
    d2 = trim_by("devendra", lambda m: "Iscon Gathiya" in m.get("subject", ""), keep=4)
    print(f"   devendra: trimmed Swati Snacks -{d1}, Iscon Gathiya -{d2}")

    # Meera: Zepto 20 → 8, Blinkit 6 → 4
    m1 = trim_by("meera", lambda m: "zeptonow.com" in m.get("from", "").lower(), keep=8)
    m2 = trim_by("meera", lambda m: "blinkit.com" in m.get("from", "").lower(), keep=4)
    print(f"   meera: trimmed Zepto -{m1}, Blinkit -{m2}")

    print("\n== 4. empty calendars (keep Aditi only) ==")
    for slug in ["arjun", "devendra", "meera"]:
        empty_calendar(slug)
        print(f"   {slug}: calendar emptied")

    print("\n== 5. regenerate fixtures/2026-05-01.json ==")
    for slug in ["aditi", "arjun", "devendra", "meera"]:
        g, c = regen_fixture(slug)
        print(f"   {slug}: {g} emails, {c} events")


if __name__ == "__main__":
    main()
