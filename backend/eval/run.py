"""Eval harness — runs an agent against its golden set, judges the
output via LLM-as-judge, prints precision / recall / F1 / specificity /
preference coverage per persona + macro-averaged.

Usage:
    python -m eval.run <agent_name>
    python -m eval.run email_triage
"""

import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents import ALL_AGENTS
from app.config import get_settings
from app.loaders import load_fixture, load_profile


EVAL_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = EVAL_DIR / "golden"
PROMPTS_DIR = EVAL_DIR / "judge_prompts"
RESULTS_DIR = EVAL_DIR / "results"


# ---------------- Judge output schema ----------------


AlignmentKind = Literal["expected_task", "expected_skip", "unexpected"]


class _TaskAlignment(BaseModel):
    actual_task_index: int
    matched_id: str | None = None
    kind: AlignmentKind
    reasoning: str


class _Miss(BaseModel):
    id: str
    reasoning: str


class _SkipViolation(BaseModel):
    id: str
    actual_task_index: int
    reasoning: str


class _PrefHit(BaseModel):
    topic: str
    actual_pref_index: int
    reasoning: str


class _PrefMiss(BaseModel):
    topic: str
    reasoning: str


class JudgeOutput(BaseModel):
    task_alignments: list[_TaskAlignment] = Field(default_factory=list)
    expected_task_misses: list[_Miss] = Field(default_factory=list)
    expected_skip_violations: list[_SkipViolation] = Field(default_factory=list)
    preference_topic_hits: list[_PrefHit] = Field(default_factory=list)
    preference_topic_misses: list[_PrefMiss] = Field(default_factory=list)


# ---------------- Helpers ----------------


def load_judge_prompt(agent_name: str) -> str:
    base = (PROMPTS_DIR / "_base.md").read_text()
    specific_path = PROMPTS_DIR / f"{agent_name}.md"
    if not specific_path.exists():
        raise SystemExit(f"missing per-agent judge prompt: {specific_path}")
    return f"{base}\n\n---\n\n{specific_path.read_text()}"


def agent_module(name: str):
    for a in ALL_AGENTS:
        if a.NAME == name:
            return a
    available = ", ".join(sorted(a.NAME for a in ALL_AGENTS))
    raise SystemExit(f"unknown agent {name!r}. available: {available}")


# ---------------- LLM judge ----------------


async def judge_run(
    agent_name: str,
    persona_slug: str,
    mode: str,
    expected_tasks: list[dict],
    expected_skips: list[dict],
    expected_preference_topics: list[str],
    actual_tasks: list[dict],
    actual_prefs: list[dict],
) -> JudgeOutput:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(JudgeOutput)

    system = load_judge_prompt(agent_name)
    user = f"""## Run context
- Agent: {agent_name}
- Persona: {persona_slug}
- Mode: {mode}

## expected_tasks
{json.dumps(expected_tasks, indent=2, ensure_ascii=False)}

## expected_skips
{json.dumps(expected_skips, indent=2, ensure_ascii=False)}

## expected_preference_topics
{json.dumps(expected_preference_topics, indent=2, ensure_ascii=False)}

## actual_tasks
{json.dumps(actual_tasks, indent=2, ensure_ascii=False, default=str)}

## actual_preference_updates
{json.dumps(actual_prefs, indent=2, ensure_ascii=False)}

Return the alignment object exactly per the schema."""
    return await llm.ainvoke([("system", system), ("user", user)])


# ---------------- Metric computation ----------------


def _f1(p: float, r: float) -> float:
    return 0.0 if (p + r) == 0 else 2 * p * r / (p + r)


def compute_metrics(
    judge: JudgeOutput,
    expected_tasks: list[dict],
    expected_skips: list[dict],
    expected_topics: list[str],
    actual_tasks_count: int,
) -> dict:
    tp = sum(1 for a in judge.task_alignments if a.kind == "expected_task")
    fp_unexpected = sum(1 for a in judge.task_alignments if a.kind == "unexpected")
    fp_skip = len(judge.expected_skip_violations)
    fp = fp_unexpected + fp_skip
    fn = len(judge.expected_task_misses)

    expected_count = len(expected_tasks)
    skip_count = len(expected_skips)
    topic_count = len(expected_topics)

    # Vacuous-perfect rules:
    #  - 0 expected tasks AND 0 actual → recall=1, precision=1, f1=1.
    #  - 0 expected tasks AND >0 actual → precision=0, recall=1 (vacuous), f1=0.
    if expected_count == 0 and actual_tasks_count == 0:
        recall, precision = 1.0, 1.0
    elif expected_count == 0:
        recall = 1.0
        precision = 0.0
    elif actual_tasks_count == 0:
        recall = 0.0
        precision = 1.0  # vacuous
    else:
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

    f1 = _f1(precision, recall)

    correctly_skipped = skip_count - fp_skip
    specificity = correctly_skipped / skip_count if skip_count > 0 else 1.0

    topic_hits = len(judge.preference_topic_hits)
    pref_coverage = topic_hits / topic_count if topic_count > 0 else 1.0

    return {
        "tp": tp,
        "fp_unexpected": fp_unexpected,
        "fp_skip_violations": fp_skip,
        "fn": fn,
        "expected_tasks": expected_count,
        "actual_tasks": actual_tasks_count,
        "expected_skips": skip_count,
        "expected_topics": topic_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "pref_coverage": pref_coverage,
    }


# ---------------- Runner ----------------


def _filter_expired(items: list[dict], evaluation_date: str) -> tuple[list[dict], int]:
    """Drop entries whose valid_until is strictly before evaluation_date.

    Items without `valid_until` (or null) never expire and are always kept.
    Returns (kept_items, dropped_count).
    """
    kept: list[dict] = []
    dropped = 0
    for it in items:
        vu = it.get("valid_until")
        if vu and vu < evaluation_date:
            dropped += 1
            continue
        kept.append(it)
    return kept, dropped


async def run_eval(agent_name: str) -> int:
    golden_path = GOLDEN_DIR / f"{agent_name}.json"
    if not golden_path.exists():
        raise SystemExit(f"missing golden file: {golden_path}")
    golden = json.loads(golden_path.read_text())
    agent = agent_module(agent_name)
    eval_date: str = golden["evaluation_date"]

    print(f"=== Eval: {agent_name} (schema v{golden['schema_version']}, "
          f"{len(golden['personas'])} personas, evaluation_date={eval_date}) ===\n")

    rows: list[dict] = []
    for p in golden["personas"]:
        slug = p["slug"]
        mode = p["mode"]

        # Filter out expired golden entries before judging.
        live_tasks, dropped_tasks = _filter_expired(p["expected_tasks"], eval_date)
        live_skips, dropped_skips = _filter_expired(p["expected_skips"], eval_date)
        if dropped_tasks or dropped_skips:
            print(
                f"  [{slug}] filtered expired golden: "
                f"-{dropped_tasks} tasks / -{dropped_skips} skips "
                f"(valid_until < {eval_date})",
                flush=True,
            )

        print(f"  [{slug}] running agent...", flush=True)
        profile = load_profile(slug)
        di = load_fixture(slug, eval_date)
        result = await agent.run(di, profile)

        actual_tasks = [t.model_dump() for t in result.tasks]
        actual_prefs = [pr.model_dump() for pr in result.preference_updates]

        print(f"  [{slug}] judging "
              f"({len(actual_tasks)} actual tasks vs "
              f"{len(live_tasks)} expected)...", flush=True)
        judge = await judge_run(
            agent_name=agent_name,
            persona_slug=slug,
            mode=mode,
            expected_tasks=live_tasks,
            expected_skips=live_skips,
            expected_preference_topics=p["expected_preference_topics"],
            actual_tasks=actual_tasks,
            actual_prefs=actual_prefs,
        )
        m = compute_metrics(
            judge,
            live_tasks,
            live_skips,
            p["expected_preference_topics"],
            len(actual_tasks),
        )
        m["expired_tasks_filtered"] = dropped_tasks
        m["expired_skips_filtered"] = dropped_skips
        rows.append(
            {
                "slug": slug,
                "mode": mode,
                "metrics": m,
                "judge": judge.model_dump(),
                "actual_tasks": actual_tasks,
                "actual_prefs": actual_prefs,
            }
        )

    # ---------------- Print metrics table ----------------
    print()
    header = f"{'persona':10s}  {'mode':14s}  {'P':>5s}  {'R':>5s}  {'F1':>5s}  {'Spec':>5s}  {'Pref':>5s}  {'TP/FP/FN':>10s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        m = r["metrics"]
        print(
            f"{r['slug']:10s}  {r['mode']:14s}  "
            f"{m['precision']:>5.2f}  {m['recall']:>5.2f}  {m['f1']:>5.2f}  "
            f"{m['specificity']:>5.2f}  {m['pref_coverage']:>5.2f}  "
            f"{m['tp']:>2d}/{m['fp_unexpected']+m['fp_skip_violations']:>2d}/{m['fn']:>2d}"
        )
    print("-" * len(header))
    n = len(rows)
    avg = lambda key: sum(r["metrics"][key] for r in rows) / n
    print(
        f"{'MACRO AVG':10s}  {'':14s}  "
        f"{avg('precision'):>5.2f}  {avg('recall'):>5.2f}  {avg('f1'):>5.2f}  "
        f"{avg('specificity'):>5.2f}  {avg('pref_coverage'):>5.2f}"
    )

    macro = {
        "precision": avg("precision"),
        "recall": avg("recall"),
        "f1": avg("f1"),
        "specificity": avg("specificity"),
        "pref_coverage": avg("pref_coverage"),
    }

    # ---------------- Persist full alignments (overwrites every run) ----------------
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"{agent_name}_latest.json"
    out_path.write_text(
        json.dumps(
            {
                "agent": agent_name,
                "macro_avg": macro,
                "personas": rows,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    # ---------------- Append history row (one-line JSONL per run) ----------------
    settings = get_settings()
    history_path = RESULTS_DIR / f"{agent_name}_history.jsonl"
    history_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent_name,
        "agent_source_hash": _agent_source_hash(agent_name),
        "model": settings.openai_model,
        "evaluation_date": eval_date,
        "macro": macro,
        "personas": [
            _build_persona_history_entry(r, golden_personas_by_slug=_golden_by_slug(golden))
            for r in rows
        ],
    }
    prev_macro = _read_previous_macro(history_path)
    with history_path.open("a") as f:
        f.write(json.dumps(history_row, ensure_ascii=False) + "\n")

    # Trend line — show delta from the previous run on the same agent.
    if prev_macro is not None:
        deltas = " ".join(
            f"{k[:4]}{_fmt_delta(macro[k] - prev_macro[k])}"
            for k in ("f1", "precision", "recall", "specificity", "pref_coverage")
        )
        print(f"\ntrend vs prev run: {deltas}")
    else:
        print("\ntrend: first run for this agent")

    print(f"full alignments → {out_path.relative_to(EVAL_DIR.parent)}")
    print(f"history row     → {history_path.relative_to(EVAL_DIR.parent)}")
    return 0


def _golden_by_slug(golden: dict) -> dict:
    return {p["slug"]: p for p in golden["personas"]}


def _build_persona_history_entry(row: dict, *, golden_personas_by_slug: dict) -> dict:
    """Build a single persona history entry — metrics + failure insights.

    Insights are programmatic so the row can be fed back into a prompt-iteration
    loop. Each failure includes enough context to act on (the offending task's
    title/action, the expected item's summary, the judge's one-line reasoning).
    """
    m = row["metrics"]
    j = row["judge"]
    actual_tasks = row["actual_tasks"]
    slug = row["slug"]
    g = golden_personas_by_slug.get(slug, {})
    expected_by_id: dict[str, dict] = {t["id"]: t for t in g.get("expected_tasks", [])}
    skip_by_id: dict[str, dict] = {s["id"]: s for s in g.get("expected_skips", [])}

    def _actual(idx: int) -> dict:
        if 0 <= idx < len(actual_tasks):
            t = actual_tasks[idx]
            return {
                "title": t.get("title", ""),
                "action": t.get("action", ""),
                "rationale": t.get("rationale", ""),
            }
        return {}

    task_misses = [
        {
            "id": miss["id"],
            "summary": expected_by_id.get(miss["id"], {}).get("summary", ""),
            "evidence_email_ids": expected_by_id.get(miss["id"], {}).get("evidence_email_ids", []),
            "category": expected_by_id.get(miss["id"], {}).get("category"),
            "judge_reasoning": miss["reasoning"],
        }
        for miss in j["expected_task_misses"]
    ]

    skip_violations = [
        {
            "id": v["id"],
            "summary": skip_by_id.get(v["id"], {}).get("summary", ""),
            "actual": _actual(v["actual_task_index"]),
            "judge_reasoning": v["reasoning"],
        }
        for v in j["expected_skip_violations"]
    ]

    unexpected_tasks = [
        {
            "actual": _actual(a["actual_task_index"]),
            "judge_reasoning": a["reasoning"],
        }
        for a in j["task_alignments"]
        if a["kind"] == "unexpected"
    ]

    pref_topic_misses = [
        {"topic": miss["topic"], "judge_reasoning": miss["reasoning"]}
        for miss in j["preference_topic_misses"]
    ]

    return {
        "slug": slug,
        "mode": row["mode"],
        # ---- metrics ----
        "precision": m["precision"],
        "recall": m["recall"],
        "f1": m["f1"],
        "specificity": m["specificity"],
        "pref_coverage": m["pref_coverage"],
        # ---- counts ----
        "tp": m["tp"],
        "fp_unexpected": m["fp_unexpected"],
        "fp_skip_violations": m["fp_skip_violations"],
        "fn": m["fn"],
        "expected_tasks": m["expected_tasks"],
        "actual_tasks": m["actual_tasks"],
        "expected_skips": m["expected_skips"],
        "expected_topics": m["expected_topics"],
        # ---- programmatic insights (use as input for prompt iteration) ----
        "failures": {
            "task_misses": task_misses,
            "skip_violations": skip_violations,
            "unexpected_tasks": unexpected_tasks,
            "pref_topic_misses": pref_topic_misses,
        },
    }


def _agent_source_hash(agent_name: str) -> str:
    """SHA-256 of the agent module's source file (truncated). Lets us tie a
    score row to a specific prompt+code snapshot, so two runs with the same
    hash represent pure LLM nondeterminism vs prompt iteration."""
    src_path = Path(__file__).resolve().parent.parent / "app" / "agents" / f"{agent_name}.py"
    return hashlib.sha256(src_path.read_bytes()).hexdigest()[:12]


def _read_previous_macro(history_path: Path) -> dict | None:
    """Return the macro dict from the last row of the history file, or None
    if no history exists yet."""
    if not history_path.exists():
        return None
    last = None
    with history_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    return json.loads(last).get("macro")


def _fmt_delta(d: float) -> str:
    """+0.07 / -0.12 / =0.00 format."""
    if d > 0.005:
        return f"+{d:.2f}"
    if d < -0.005:
        return f"{d:.2f}"
    return "=0.00"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m eval.run <agent_name>")
        sys.exit(1)
    sys.exit(asyncio.run(run_eval(sys.argv[1])))
