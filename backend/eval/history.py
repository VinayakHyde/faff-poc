"""Show the score history for one or all agents.

Reads `eval/results/<agent>_history.jsonl` (one JSON object per line,
appended by `eval.run`) and prints a timeline.

Usage:
    python -m eval.history <agent>                # one agent — full timeline
    python -m eval.history <agent> --last N       # last N rows
    python -m eval.history <agent> --insights     # last run's failure detail (for prompt iteration)
    python -m eval.history --all                  # latest row per agent
"""

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"


def _load_history(agent_name: str) -> list[dict]:
    path = RESULTS_DIR / f"{agent_name}_history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _short_ts(iso: str) -> str:
    return iso[5:10] + " " + iso[11:16]


def _delta_str(curr: float, prev: float | None) -> str:
    if prev is None:
        return "  ·"
    d = curr - prev
    if d > 0.005:
        return f"+{d:>4.2f}"
    if d < -0.005:
        return f"{d:>5.2f}"
    return "  ·"


def show_one(agent_name: str, last_n: int | None = None) -> int:
    rows = _load_history(agent_name)
    if not rows:
        print(f"no history for {agent_name} (run `python -m eval.run {agent_name}` first)")
        return 1
    if last_n:
        rows = rows[-last_n:]

    print(f"=== {agent_name} — {len(rows)} run(s) ===\n")
    header = (
        f"{'when':12s}  {'hash':>12s}  {'model':>8s}  "
        f"{'F1':>5s} {'ΔF1':>5s}  "
        f"{'P':>5s} {'ΔP':>5s}  "
        f"{'R':>5s} {'ΔR':>5s}  "
        f"{'Spec':>5s} {'ΔSp':>5s}  "
        f"{'Pref':>5s} {'ΔPr':>5s}"
    )
    print(header)
    print("-" * len(header))

    prev = None
    for r in rows:
        m = r["macro"]
        when = _short_ts(r["timestamp"])
        h = r["agent_source_hash"]
        model = r.get("model", "?")[-8:]
        f1d = _delta_str(m["f1"], prev["f1"] if prev else None)
        pd = _delta_str(m["precision"], prev["precision"] if prev else None)
        rd = _delta_str(m["recall"], prev["recall"] if prev else None)
        sd = _delta_str(m["specificity"], prev["specificity"] if prev else None)
        prd = _delta_str(m["pref_coverage"], prev["pref_coverage"] if prev else None)
        print(
            f"{when:12s}  {h:>12s}  {model:>8s}  "
            f"{m['f1']:>5.2f} {f1d:>5s}  "
            f"{m['precision']:>5.2f} {pd:>5s}  "
            f"{m['recall']:>5.2f} {rd:>5s}  "
            f"{m['specificity']:>5.2f} {sd:>5s}  "
            f"{m['pref_coverage']:>5.2f} {prd:>5s}"
        )
        prev = m
    return 0


def show_insights(agent_name: str) -> int:
    """Print the LAST run's per-persona failure detail. Suitable for piping
    into a prompt to ask the LLM 'fix these failures'."""
    rows = _load_history(agent_name)
    if not rows:
        print(f"no history for {agent_name}")
        return 1
    last = rows[-1]
    print(f"=== {agent_name} — failure insights from {_short_ts(last['timestamp'])} ===\n")
    for p in last["personas"]:
        f = p.get("failures", {})
        misses = f.get("task_misses", [])
        violations = f.get("skip_violations", [])
        unexpected = f.get("unexpected_tasks", [])
        pref_misses = f.get("pref_topic_misses", [])
        if not (misses or violations or unexpected or pref_misses):
            continue
        print(f"--- {p['slug']} ({p['mode']}) ---")
        if misses:
            print(f"  TASK MISSES (recall {p['recall']:.2f}):")
            for m in misses:
                print(f"    [{m['id']}] {m['summary']}")
                print(f"      judge: {m['judge_reasoning']}")
        if violations:
            print(f"  SKIP VIOLATIONS (specificity {p['specificity']:.2f}):")
            for v in violations:
                a = v.get("actual", {})
                print(f"    [{v['id']}] expected_skip: {v['summary']}")
                print(f"      agent surfaced: \"{a.get('title', '')}\" → {a.get('action', '')}")
                print(f"      judge: {v['judge_reasoning']}")
        if unexpected:
            print(f"  UNEXPECTED TASKS (precision drag):")
            for u in unexpected:
                a = u.get("actual", {})
                print(f"    \"{a.get('title', '')}\" → {a.get('action', '')}")
                print(f"      judge: {u['judge_reasoning']}")
        if pref_misses:
            print(f"  PREF TOPIC MISSES (coverage {p['pref_coverage']:.2f}):")
            for pm in pref_misses:
                print(f"    - {pm['topic']}")
        print()
    return 0


def show_all() -> int:
    files = sorted(RESULTS_DIR.glob("*_history.jsonl"))
    if not files:
        print("no history files yet")
        return 1
    print(f"=== latest run per agent ({len(files)} agent(s)) ===\n")
    header = (
        f"{'agent':14s}  {'when':12s}  {'runs':>4s}  "
        f"{'F1':>5s}  {'P':>5s}  {'R':>5s}  {'Spec':>5s}  {'Pref':>5s}"
    )
    print(header)
    print("-" * len(header))
    for f in files:
        agent_name = f.name.replace("_history.jsonl", "")
        rows = _load_history(agent_name)
        if not rows:
            continue
        last = rows[-1]
        m = last["macro"]
        print(
            f"{agent_name:14s}  {_short_ts(last['timestamp']):12s}  {len(rows):>4d}  "
            f"{m['f1']:>5.2f}  {m['precision']:>5.2f}  {m['recall']:>5.2f}  "
            f"{m['specificity']:>5.2f}  {m['pref_coverage']:>5.2f}"
        )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 1:
        print(__doc__)
        return 1
    if argv[0] == "--all":
        return show_all()
    agent = argv[0]
    if "--insights" in argv:
        return show_insights(agent)
    last_n = None
    if "--last" in argv:
        i = argv.index("--last")
        last_n = int(argv[i + 1])
    return show_one(agent, last_n)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
