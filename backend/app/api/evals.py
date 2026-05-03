"""Eval history endpoint.

Surfaces what's already on disk under `backend/eval/results/`:
- `<agent>_history.jsonl` — append-only, one row per eval run, with macro
  metrics and per-persona breakdowns (incl. failures).
- `<agent>_latest.json`   — most recent run, used as a fallback for agents
  that haven't been run twice yet (so we still have something to graph).

The frontend's Evals view consumes `/api/evals` directly to render the
combined F1 timeline + per-agent line charts + latest-run tables.
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/evals", tags=["evals"])

EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "eval"
RESULTS_DIR = EVAL_DIR / "results"


def _load_history(agent: str) -> list[dict]:
    """Return chronologically-ordered eval runs for one agent.

    Prefers `<agent>_history.jsonl` (full timeline). Falls back to
    `<agent>_latest.json` wrapped in a single-element list when no history
    file exists, so first-run agents still show up.
    """
    history_path = RESULTS_DIR / f"{agent}_history.jsonl"
    if history_path.exists():
        rows: list[dict] = []
        for line in history_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        rows.sort(key=lambda r: r.get("timestamp", ""))
        return rows

    latest_path = RESULTS_DIR / f"{agent}_latest.json"
    if latest_path.exists():
        try:
            return [json.loads(latest_path.read_text())]
        except json.JSONDecodeError:
            return []
    return []


def _discover_agents() -> list[str]:
    """Every agent that has either a history or a latest result on disk."""
    if not RESULTS_DIR.is_dir():
        return []
    seen: set[str] = set()
    for p in RESULTS_DIR.iterdir():
        name = p.name
        if name.endswith("_history.jsonl"):
            seen.add(name[: -len("_history.jsonl")])
        elif name.endswith("_latest.json"):
            seen.add(name[: -len("_latest.json")])
    return sorted(seen)


@router.get("")
def get_all_evals() -> dict:
    """Full eval history for every agent, plus the combined leaderboard.

    Shape:
        {
          "agents": [
            {
              "agent": "shopping",
              "runs": [ { timestamp, model, macro: {...}, personas: [...] }, ... ],
              "latest": { ...same shape as one run... } | null
            },
            ...
          ]
        }
    """
    out: list[dict] = []
    for agent in _discover_agents():
        runs = _load_history(agent)
        latest = runs[-1] if runs else None
        out.append({"agent": agent, "runs": runs, "latest": latest})
    return {"agents": out}
