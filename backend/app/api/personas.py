"""Persona-keyed REST endpoints.

The frontend uses these to:
- list personas for the sidebar selector
- load one persona's standing context (meta + profile markdown)
- pull a default fixture for the daily-input box
- POST a daily input to run the orchestrator end-to-end (sync or SSE)
"""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import orchestrator
from app.loaders import (
    DATA_DIR,
    list_personas,
    load_fixture,
    load_meta,
    load_profile,
)
from app.models import (
    DailyInput,
    Meta,
    OrchestratorResult,
    PreferencesProfile,
    TraceEvent,
)


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


def _resolve_fixture_date(slug: str, requested_date: str | None) -> str:
    """Pick a fixture date. Order:
      1. If the caller passed `?date=YYYY-MM-DD`, use that.
      2. Else today's date (matches "cron-triggered today" semantic).
      3. Else fall back to the most recent fixture on disk for the persona.
    """
    if requested_date is not None:
        try:
            date.fromisoformat(requested_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="`date` must be YYYY-MM-DD") from e
        return requested_date

    today = date.today().isoformat()
    if (DATA_DIR / slug / "fixtures" / f"{today}.json").exists():
        return today

    fix_dir = DATA_DIR / slug / "fixtures"
    if fix_dir.is_dir():
        candidates = sorted(p.stem for p in fix_dir.glob("*.json"))
        if candidates:
            return candidates[-1]

    return today  # caller will 400 cleanly when load_fixture fails


def _resolve_run_inputs(
    slug: str,
    daily_input: DailyInput | None,
    fixture_date: str | None = None,
) -> tuple[PreferencesProfile, DailyInput]:
    """Shared by the sync and streaming run endpoints. Loads profile,
    falls back to a sensible fixture if no body is posted, and enforces
    URL `slug` over any `user_slug` in the body."""
    try:
        profile = load_profile(slug)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"persona not found: {slug}") from e

    if daily_input is None:
        chosen = _resolve_fixture_date(slug, fixture_date)
        try:
            daily_input = load_fixture(slug, chosen)
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"no fixture for {slug} on {chosen} — POST a DailyInput body or pass ?date=YYYY-MM-DD"
                ),
            ) from e

    if daily_input.user_slug != slug:
        daily_input = daily_input.model_copy(update={"user_slug": slug})
    return profile, daily_input


@router.post("/{slug}/run", response_model=OrchestratorResult)
async def run_for_persona(
    slug: str,
    daily_input: DailyInput | None = None,
    date: str | None = None,
) -> OrchestratorResult:
    """Run the full orchestrator pipeline for a persona (synchronous JSON).

    Body is optional. If omitted, loads a fixture: `?date=YYYY-MM-DD` if
    given, else today's date, else the latest fixture on disk. The URL
    `slug` is authoritative; if a body is provided with a different
    `user_slug`, it gets overwritten.

    For the right-panel "watch it think" UX, prefer `/run/stream`.
    """
    profile, daily_input = _resolve_run_inputs(slug, daily_input, fixture_date=date)
    return await orchestrator.run(daily_input, profile)


@router.post("/{slug}/run/stream")
async def run_for_persona_streaming(
    slug: str,
    daily_input: DailyInput | None = None,
    date: str | None = None,
) -> StreamingResponse:
    """Same as /run, but returns Server-Sent Events.

    Stream format (named events so JS can subscribe per-type):

        event: trace
        data: {<TraceEvent JSON>}

        event: trace
        data: {...}

        event: result
        data: {<OrchestratorResult JSON>}     ← terminal frame; stream ends after this

    On error, a single `event: error` frame is emitted before the stream closes.
    """
    profile, daily_input = _resolve_run_inputs(slug, daily_input, fixture_date=date)
    return StreamingResponse(
        _stream_events(profile, daily_input),
        media_type="text/event-stream",
        # Disable buffering at any reverse proxy in front (nginx etc.).
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event_name: str, data: str) -> str:
    """Format one SSE frame. Trailing `\\n\\n` terminates the message."""
    return f"event: {event_name}\ndata: {data}\n\n"


async def _stream_events(
    profile: PreferencesProfile,
    daily_input: DailyInput,
) -> AsyncIterator[str]:
    """Run the orchestrator concurrently with this generator. Yield SSE
    frames as TraceEvents land in the queue; emit one final `result`
    (or `error`) frame after the orchestrator returns."""
    queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
    run_task: asyncio.Task[OrchestratorResult] = asyncio.create_task(
        orchestrator.run(daily_input, profile, event_queue=queue)
    )

    try:
        # Stream events while the run is in flight.
        while not run_task.done():
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {get_task, run_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                event = get_task.result()
                yield _sse("trace", event.model_dump_json())
            else:
                get_task.cancel()
                try:
                    await get_task
                except (asyncio.CancelledError, Exception):
                    pass

        # Drain any TraceEvents the orchestrator pushed after the last `wait` race.
        while not queue.empty():
            event = queue.get_nowait()
            yield _sse("trace", event.model_dump_json())

        # Terminal frame: result or error.
        if run_task.exception():
            err = run_task.exception()
            yield _sse(
                "error",
                json.dumps({"error": f"{type(err).__name__}: {err}"}),
            )
        else:
            result = run_task.result()
            yield _sse("result", result.model_dump_json())
    finally:
        # Client disconnect: cancel the orchestrator so we don't leak the task.
        if not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
