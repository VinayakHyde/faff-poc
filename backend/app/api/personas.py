"""Persona-keyed REST endpoints.

The frontend uses these to:
- list personas for the sidebar selector
- load one persona's standing context (meta + profile markdown)
- pull a default fixture for the daily-input box
- POST a daily input to run the orchestrator end-to-end
"""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app import orchestrator
from app.loaders import (
    DATA_DIR,
    list_personas,
    load_fixture,
    load_meta,
    load_profile,
)
from app.models import DailyInput, Meta, OrchestratorResult, PreferencesProfile


router = APIRouter(prefix="/api/personas", tags=["personas"])


# ---------------- response models ----------------


class PersonaListing(Meta):
    """Persona summary for the sidebar — Meta + a derived avatar_url."""

    avatar_url: str | None = None


class PersonaDetail(PreferencesProfile):
    """Full standing context — meta + profile markdown."""


class FixtureIndex(dict):
    """Wrapper for `{slug, available_dates}` (avoids hand-rolling a model)."""


# ---------------- helpers ----------------


def _avatar_url(slug: str) -> str | None:
    """Return /avatars/<slug>.png if the file exists at backend/data/users/<slug>/avatar.png, else None."""
    p = DATA_DIR / slug / "avatar.png"
    return f"/api/personas/{slug}/avatar" if p.exists() else None


def _fixture_dates(slug: str) -> list[str]:
    fix_dir = DATA_DIR / slug / "fixtures"
    if not fix_dir.is_dir():
        return []
    return sorted(p.stem for p in fix_dir.glob("*.json"))


# ---------------- endpoints ----------------


@router.get("", response_model=list[PersonaListing])
async def list_all() -> list[PersonaListing]:
    """List every available persona (sidebar selector)."""
    out: list[PersonaListing] = []
    for slug in list_personas():
        try:
            meta = load_meta(slug)
        except FileNotFoundError:
            continue
        out.append(PersonaListing(**meta.model_dump(), avatar_url=_avatar_url(slug)))
    return out


@router.get("/{slug}", response_model=PersonaDetail)
async def get_persona(slug: str) -> PersonaDetail:
    """Return one persona's standing context — meta + profile markdown."""
    try:
        profile = load_profile(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"persona not found: {slug}") from e
    return PersonaDetail(**profile.model_dump())


@router.get("/{slug}/avatar")
async def get_avatar(slug: str):
    """Serve the persona's avatar.png if present (404 otherwise)."""
    from fastapi.responses import FileResponse

    p = DATA_DIR / slug / "avatar.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"no avatar for {slug}")
    return FileResponse(p, media_type="image/png")


@router.get("/{slug}/fixtures")
async def list_fixtures(slug: str) -> dict:
    """List available fixture dates for a persona."""
    if not (DATA_DIR / slug).is_dir():
        raise HTTPException(status_code=404, detail=f"persona not found: {slug}")
    return {"slug": slug, "available_dates": _fixture_dates(slug)}


@router.get("/{slug}/fixtures/{fixture_date}", response_model=DailyInput)
async def get_fixture(slug: str, fixture_date: str) -> DailyInput:
    """Return one fixture's DailyInput payload. `fixture_date` is YYYY-MM-DD."""
    try:
        # Validate date shape (FastAPI's date type would do it, but we want
        # to accept the raw string and 404 cleanly).
        date.fromisoformat(fixture_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="fixture_date must be YYYY-MM-DD") from e
    try:
        return load_fixture(slug, fixture_date)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"no fixture for {slug} on {fixture_date}",
        ) from e


@router.post("/{slug}/run", response_model=OrchestratorResult)
async def run_for_persona(
    slug: str,
    daily_input: DailyInput | None = None,
) -> OrchestratorResult:
    """Run the full orchestrator pipeline for a persona.

    Body is optional. If omitted, defaults to the persona's fixture for
    the canonical demo date (2026-05-01). The URL `slug` is authoritative;
    if a body is provided with a different `user_slug`, it gets overwritten.
    """
    try:
        profile = load_profile(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"persona not found: {slug}") from e

    if daily_input is None:
        try:
            daily_input = load_fixture(slug, "2026-05-01")
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"no fixture for {slug} on 2026-05-01 — POST a DailyInput body explicitly"
                ),
            ) from e

    # URL slug wins over any value in the body.
    if daily_input.user_slug != slug:
        daily_input = daily_input.model_copy(update={"user_slug": slug})

    return await orchestrator.run(daily_input, profile)
