"""Disk loaders for personas and daily fixtures.

Files live at `backend/data/users/<slug>/`:
  meta.json
  profile.md
  mailbox.json
  calendar.json
  fixtures/YYYY-MM-DD.json

The loaders return validated pydantic models so the rest of the pipeline
never touches raw dicts.
"""

from pathlib import Path

from app.models import DailyInput, Meta, PreferencesProfile

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"


def load_meta(slug: str) -> Meta:
    return Meta.model_validate_json((DATA_DIR / slug / "meta.json").read_text())


def load_profile(slug: str) -> PreferencesProfile:
    meta = load_meta(slug)
    markdown = (DATA_DIR / slug / "profile.md").read_text()
    return PreferencesProfile(meta=meta, markdown=markdown)


def load_fixture(slug: str, date: str) -> DailyInput:
    return DailyInput.model_validate_json(
        (DATA_DIR / slug / "fixtures" / f"{date}.json").read_text()
    )


def list_personas() -> list[str]:
    return sorted(p.name for p in DATA_DIR.iterdir() if p.is_dir())
