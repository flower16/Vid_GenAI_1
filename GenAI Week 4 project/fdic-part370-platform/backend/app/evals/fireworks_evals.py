"""
Fireworks AI evaluations — the LLM-as-judge layer.

The deterministic LangSmith evaluators ([langsmith_evals.py](langsmith_evals.py))
prove the *math* reconciles: insured + uninsured == P&I, insured <= limit, the
expected number came out. They cannot judge whether the natural-language
*rationale* the platform emits is actually grounded in the right Part 370 rule,
whether the structured evidence supports the number, or whether a human reviewer
could read it. Those are qualitative — so we score them with an LLM judge.

The judge calls a Fireworks-served open model over its OpenAI-compatible chat
API (`/chat/completions`). We use the stdlib `urllib` (no extra dependency) and
ask the model for strict JSON `{"score": 0..1, "reason": "..."}`.

Cost note: when `FIREWORKS_API_KEY` is unset — CI, offline dev, and this repo by
default — every judge falls back to a deterministic heuristic, so the suite
still runs and costs **$0**. Set the key to switch the same judges to the real
model. See [docs/evals.md](../../../docs/evals.md).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Callable

from ..core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fireworks chat call (OpenAI-compatible), stdlib only
# ---------------------------------------------------------------------------

_TIMEOUT_S = 30


def fireworks_available() -> bool:
    return bool(settings.fireworks_api_key)


def _chat(system: str, user: str) -> str:  # pragma: no cover - external network
    """One chat completion against Fireworks; returns the assistant text."""
    body = json.dumps({
        "model": settings.fireworks_judge_model,
        "temperature": 0.0,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.fireworks_base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.fireworks_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def _judge(system: str, user: str, heuristic: Callable[[], dict]) -> dict:
    """Run the LLM judge, or the deterministic heuristic when no key / on error.

    Always returns {"score": float 0..1, "reason": str, "grader": "fireworks"|"heuristic"}.
    Never raises: a judge that blows up must not fail a determination.
    """
    if not fireworks_available():
        h = heuristic()
        return {**h, "grader": "heuristic"}
    try:  # pragma: no cover - external network
        raw = _chat(system, user)
        data = json.loads(raw)
        score = float(data.get("score", 0.0))
        return {"score": max(0.0, min(1.0, score)),
                "reason": str(data.get("reason", ""))[:400],
                "grader": "fireworks"}
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:  # pragma: no cover
        # Configured but the call failed (bad/retired model id, quota, network).
        # We still fall back so a determination never breaks — but log it, so a
        # misconfigured key/model can't silently masquerade as heuristic scores.
        logger.warning("Fireworks judge call failed (model=%s); falling back to "
                       "heuristic: %s", settings.fireworks_judge_model, e)
        h = heuristic()
        return {**h, "grader": "heuristic", "reason": f"fireworks unavailable ({e}); {h['reason']}"}


# ---------------------------------------------------------------------------
# The judges. Each: fn(result: dict) -> {"key","score","comment","grader"}
# `result` is a CoverageResult.model_dump(mode="json").
# ---------------------------------------------------------------------------

_RULE_HINT = {
    "TST": "§330.10", "DIT": "§330.10", "BUS": "§330.11", "JNT": "§330.9",
    "SGL": "§330.6", "CRA": "§330.14", "EBP": "§330.14", "MSA": "§330.7",
    "GOV1": "§330.15", "GOV2": "§330.15", "GOV3": "§330.15",
}

# Human-readable capacity keywords a rationale uses instead of the ORC code
# ("Trust account…" rather than "TST"), so the heuristic can credit grounding.
_ORC_KEYWORDS = {
    "SGL": ("single", "individual"), "JNT": ("joint", "co-owner"),
    "TST": ("trust", "beneficiar", "grantor"), "CRA": ("retirement", "ira"),
    "EBP": ("employee benefit", "plan", "participant"), "BUS": ("business", "entity", "corp"),
    "GOV1": ("public unit", "government"), "GOV2": ("public unit", "government", "demand"),
    "GOV3": ("public unit", "government", "out-of-state"), "MSA": ("mortgage servic",),
    "PBA": ("bond", "bondholder"), "DIT": ("trust", "irrevocable", "trustee"),
    "ANC": ("annuit",), "BIA": ("american indian", "custodian"), "DOE": ("doe", "financial assistance"),
}

_SYS = ("You are a meticulous FDIC deposit-insurance reviewer scoring one field "
        "of an automated coverage determination under 12 CFR Part 370. Reply with "
        'ONLY a JSON object: {"score": <0..1>, "reason": "<one sentence>"}. '
        "1.0 = fully correct/grounded, 0.0 = wrong or unsupported.")


def judge_rationale_grounding(result: dict) -> dict:
    """Is the rationale grounded in the correct ORC and a Part 370 citation?"""
    orc = result.get("orc", "")
    rationale = result.get("rationale", "") or ""

    def heuristic() -> dict:
        low = rationale.lower()
        mentions_orc = orc.lower() in low or any(k in low for k in _ORC_KEYWORDS.get(orc, ()))
        cites_reg = bool(re.search(r"330\.\d+|part\s*370|smdia|\$?250", rationale, re.I))
        score = 0.5 * mentions_orc + 0.5 * cites_reg
        return {"score": score,
                "reason": f"mentions_capacity={mentions_orc}, cites_regulation={cites_reg}"}

    user = (f"ORC category: {orc} (expected citation near {_RULE_HINT.get(orc, 'Part 370')}).\n"
            f"Rationale to score:\n\"\"\"{rationale}\"\"\"\n"
            "Score 1.0 only if it names the correct capacity AND cites the coverage rule.")
    r = _judge(_SYS, user, heuristic)
    return {"key": "rationale_grounding", "score": r["score"],
            "comment": r["reason"], "grader": r["grader"]}


def judge_evidence_support(result: dict) -> dict:
    """Does the structured evidence actually support the insured number?"""
    evidence = result.get("evidence", {}) or {}
    insured = result.get("insured_amount")
    limit = result.get("coverage_limit")

    def heuristic() -> dict:
        has_evidence = isinstance(evidence, dict) and len(evidence) > 0
        # Reproducible = the evidence exposes how the limit was built: the party
        # breakdown the shape aggregates over, plus the rule it applied. These
        # are the keys the engine actually emits (see domain/orc/engine.py).
        breakdown = any(k in evidence for k in (
            "owner_shares", "owner_names", "unique_owners",
            "vested_interests", "participant_coverage", "participant_names",
            "official_custodians", "beneficiaries", "treatment", "smdia"))
        cited = "rule_citation" in evidence
        score = 0.5 * (has_evidence and breakdown) + 0.5 * cited
        return {"score": score,
                "reason": f"evidence_keys={list(evidence)[:6]}, breakdown={breakdown}, cited={cited}"}

    user = (f"Insured amount: {insured}; coverage limit: {limit}.\n"
            f"Structured evidence emitted by the engine:\n{json.dumps(evidence, default=str)[:1200]}\n"
            "Score 1.0 only if this evidence is enough to reproduce the insured amount.")
    r = _judge(_SYS, user, heuristic)
    return {"key": "evidence_support", "score": r["score"],
            "comment": r["reason"], "grader": r["grader"]}


def judge_plain_language(result: dict) -> dict:
    """Could a non-specialist reviewer understand the rationale?"""
    rationale = result.get("rationale", "") or ""

    def heuristic() -> dict:
        words = len(rationale.split())
        has_amount = bool(re.search(r"\$?\d[\d,]{2,}", rationale))
        # Readable = says something (>= 8 words), not a wall of text, cites a number.
        score = 1.0 if (8 <= words <= 80 and has_amount) else (0.5 if words >= 8 else 0.0)
        return {"score": score, "reason": f"words={words}, has_amount={has_amount}"}

    user = ("Rationale to score for clarity to a trained-but-non-lawyer reviewer:\n"
            f"\"\"\"{rationale}\"\"\"\n"
            "Score 1.0 if it is a clear, self-contained explanation of the coverage.")
    r = _judge(_SYS, user, heuristic)
    return {"key": "plain_language", "score": r["score"],
            "comment": r["reason"], "grader": r["grader"]}


JUDGES: list[Callable[[dict], dict]] = [
    judge_rationale_grounding, judge_evidence_support, judge_plain_language,
]


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def evaluate_coverage_result(result: dict) -> list[dict]:
    """All judges over one coverage result."""
    return [j(result) for j in JUDGES]


def evaluate_determination(coverage_results: list[dict], *, pass_threshold: float = 0.75) -> dict:
    """Aggregate the judges across every coverage result of a determination.

    Returns {"grader", "pass_threshold", "mean_score", "passed", "by_judge",
    "rows"} where each judge's mean score is compared to `pass_threshold`.
    """
    rows: list[dict] = []
    per_key: dict[str, list[float]] = {}
    grader = "heuristic"
    for result in coverage_results:
        for ev in evaluate_coverage_result(result):
            rows.append({"orc": result.get("orc"), **ev})
            per_key.setdefault(ev["key"], []).append(ev["score"])
            if ev["grader"] == "fireworks":
                grader = "fireworks"

    by_judge = {k: {"mean": round(sum(v) / len(v), 3),
                    "passed": (sum(v) / len(v)) >= pass_threshold}
                for k, v in per_key.items()}
    all_scores = [s for v in per_key.values() for s in v]
    mean = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0
    return {"grader": grader, "pass_threshold": pass_threshold, "mean_score": mean,
            "passed": all(j["passed"] for j in by_judge.values()) if by_judge else True,
            "by_judge": by_judge, "rows": rows}
