"""
LangSmith evaluation framework.

Defines Input, Output, and System evaluators and a runner that evaluates the
determination workflow against a labeled dataset. When LangSmith isn't
configured, `evaluate_local` runs the same evaluators in-process (used by CI).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from ..agents.graph import run_determination
from ..domain.models import DeterminationRequest

# ---------------------------------------------------------------------------
# Evaluators: (name, fn(run_output, example) -> {"score": 0|1, "comment": str})
# ---------------------------------------------------------------------------

# ---- Input evals ----
def eval_required_data(output: dict, example: dict) -> dict:
    fails = [f for f in output.get("customer_findings", []) + output.get("account_findings", [])
             if f.get("severity") == "FAIL"]
    expect_fail = example.get("expect_input_fail", False)
    ok = bool(fails) == expect_fail
    return {"key": "input_completeness", "score": int(ok),
            "comment": f"{len(fails)} blocking findings, expected_fail={expect_fail}"}


def eval_valid_ssn(output: dict, example: dict) -> dict:
    codes = {f["code"] for f in output.get("customer_findings", [])}
    flagged = "SSN_INVALID" in codes or "SSN_MISSING" in codes
    ok = flagged == example.get("expect_ssn_issue", False)
    return {"key": "ssn_validation", "score": int(ok), "comment": str(sorted(codes))}


# ---- Output evals ----
def eval_pi_reconciles(output: dict, example: dict) -> dict:
    ok = all(Decimal(r["insured_amount"]) + Decimal(r["uninsured_amount"])
             == Decimal(r["aggregated_pi"]) for r in output.get("coverage_results", []))
    return {"key": "pi_reconciliation", "score": int(ok),
            "comment": "insured + uninsured == total PI"}


def eval_limits_respected(output: dict, example: dict) -> dict:
    ok = all(Decimal(r["insured_amount"]) <= Decimal(r["coverage_limit"]) + Decimal("0.01")
             for r in output.get("coverage_results", []))
    return {"key": "coverage_limits", "score": int(ok)}


def eval_expected_insured(output: dict, example: dict) -> dict:
    expected = example.get("expected_insured")
    if expected is None:
        return {"key": "expected_insured", "score": 1, "comment": "no label"}
    total = sum(Decimal(r["insured_amount"]) for r in output.get("coverage_results", []))
    ok = abs(total - Decimal(str(expected))) <= Decimal("0.01")
    return {"key": "expected_insured", "score": int(ok),
            "comment": f"got {total}, expected {expected}"}


def eval_pending_routing(output: dict, example: dict) -> dict:
    expected = example.get("expected_pending_reason")
    if expected is None:
        return {"key": "pending_routing", "score": 1, "comment": "no label"}
    reasons = {d.get("reason") for d in output.get("pending_decisions", []) if d.get("is_pending")}
    return {"key": "pending_routing", "score": int(expected in reasons),
            "comment": f"got {sorted(r for r in reasons if r)}, expected {expected}"}


def eval_bus_treatment(output: dict, example: dict) -> dict:
    """BUS (12 CFR 330.11): the coverage must use the eligibility treatment the
    example labels (per_entity_independent | pass_through_members)."""
    expected = example.get("expected_bus_treatment")
    if expected is None:
        return {"key": "bus_treatment", "score": 1, "comment": "no label"}
    treatments = [r.get("evidence", {}).get("treatment")
                  for r in output.get("coverage_results", []) if r.get("orc") == "BUS"]
    return {"key": "bus_treatment", "score": int(expected in treatments),
            "comment": f"got {treatments}, expected {expected}"}


INPUT_EVALS: list[Callable] = [eval_required_data, eval_valid_ssn]
OUTPUT_EVALS: list[Callable] = [eval_pi_reconciles, eval_limits_respected,
                                eval_expected_insured, eval_pending_routing,
                                eval_bus_treatment]
ALL_EVALS = INPUT_EVALS + OUTPUT_EVALS


# ---- Fireworks LLM-as-judge evaluators (qualitative), wrapped for LangSmith ----
def fireworks_evaluators() -> list[Callable]:
    """The Fireworks judges ([fireworks_evals.py](fireworks_evals.py)) exposed with
    the `(output, example)` signature so they attach to the LangSmith runner
    alongside the deterministic math evals. They average each judge over every
    coverage result and return a continuous 0..1 score. Free by default (the
    judges fall back to a heuristic until FIREWORKS_API_KEY is set)."""
    from .fireworks_evals import JUDGES

    def _wrap(judge: Callable) -> Callable:
        def _ev(output: dict, example: dict) -> dict:
            results = output.get("coverage_results", [])
            if not results:
                return {"key": judge(dict())["key"], "score": 1, "comment": "no coverage"}
            scored = [judge(r) for r in results]
            mean = sum(s["score"] for s in scored) / len(scored)
            return {"key": scored[0]["key"], "score": round(mean, 3),
                    "comment": f"{scored[0]['grader']} judge, mean over {len(scored)} ORC(s)"}
        _ev.__name__ = judge.__name__
        return _ev

    return [_wrap(j) for j in JUDGES]


def _target(example: dict) -> dict:
    req = DeterminationRequest(**example["inputs"])
    state = run_determination(req)
    return {
        "customer_findings": [f.model_dump() for f in state.get("customer_findings", [])],
        "account_findings": [f.model_dump() for f in state.get("account_findings", [])],
        "coverage_results": [r.model_dump(mode="json") for r in state.get("coverage_results", [])],
        "pending_decisions": [d.model_dump() for d in state.get("pending_decisions", [])],
    }


def evaluate_local(dataset: list[dict]) -> dict:
    """Run evaluators in-process. dataset = [{inputs, expected_*...}, ...]."""
    rows = []
    for ex in dataset:
        out = _target(ex)
        scores = [e(out, ex) for e in ALL_EVALS]
        rows.append({"example": ex.get("name", ex["inputs"]["customer"]["customer_id"]),
                     "scores": scores,
                     "passed": all(s["score"] for s in scores)})
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows), "rows": rows}


def evaluate_langsmith(dataset_name: str) -> Any:  # pragma: no cover - external
    """Run evaluation against a LangSmith dataset and log results."""
    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()

    def target(inputs: dict) -> dict:
        return _target({"inputs": inputs})

    def _make_evaluator(fn: Callable) -> Callable:
        # Wrap each evaluator so it has the (run, example) signature LangSmith
        # introspects, and bind `fn` per-iteration (avoids late-binding closure).
        def _evaluator(run, example):
            return fn(run.outputs, example.metadata or {})
        _evaluator.__name__ = fn.__name__
        return _evaluator

    # Deterministic math evals + the Fireworks LLM-as-judge evals, both attached
    # to the same LangSmith experiment.
    evaluators = ALL_EVALS + fireworks_evaluators()
    return evaluate(
        target,
        data=dataset_name,
        evaluators=[_make_evaluator(e) for e in evaluators],
        experiment_prefix="fdic-part370",
        client=client,
    )
