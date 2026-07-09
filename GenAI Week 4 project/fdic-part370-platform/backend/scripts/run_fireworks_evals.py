"""
Run the Fireworks LLM-as-judge evals over the per-ORC suite.

These are the *qualitative* evals (rationale grounding, evidence support, plain
language) that complement the deterministic math evals in LangSmith. They run
free by default (heuristic fallback); set FIREWORKS_API_KEY in backend/.env to
score with a Fireworks-served model instead.

Usage (from backend/):
    python scripts/run_fireworks_evals.py              # score the ORC suite
    python scripts/run_fireworks_evals.py --json       # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.evals.fireworks_evals import evaluate_determination, fireworks_available  # noqa: E402
from app.agents.graph import run_determination  # noqa: E402
from app.domain.models import DeterminationRequest  # noqa: E402
from scripts.seed_langsmith_dataset import build_examples  # noqa: E402


def _coverage_for(example: dict) -> list[dict]:
    req = DeterminationRequest(**example["inputs"])
    state = run_determination(req)
    return [r.model_dump(mode="json") for r in state.get("coverage_results", [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    grader = "Fireworks model" if fireworks_available() else "heuristic (no FIREWORKS_API_KEY — $0)"
    examples = build_examples()

    reports = []
    for ex in examples:
        cov = _coverage_for(ex)
        report = evaluate_determination(cov)
        reports.append({"name": ex["name"], **report})

    if args.json:
        print(json.dumps(reports, indent=2, default=str))
        return 0

    print(f"Fireworks LLM-as-judge evals — grader: {grader}\n")
    passed = sum(1 for r in reports if r["passed"])
    for r in reports:
        flag = "PASS" if r["passed"] else "WARN"
        judges = "  ".join(f"{k}={v['mean']}" for k, v in r["by_judge"].items())
        print(f"  [{flag}] {r['name']:<28} mean={r['mean_score']:<5}  {judges}")
    print(f"\n{passed}/{len(reports)} determinations >= {reports[0]['pass_threshold']} on every judge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
