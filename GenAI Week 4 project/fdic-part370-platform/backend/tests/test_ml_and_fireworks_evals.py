"""Tests for the zero-cost RL ORC policy and the Fireworks LLM-as-judge evals.

Both run fully offline: the RL policy is pure Python, and the Fireworks judges
fall back to their deterministic heuristic when no FIREWORKS_API_KEY is set (as
in CI). No network, no cost.
"""

from app.evals.fireworks_evals import (
    evaluate_determination, judge_rationale_grounding, judge_evidence_support,
    judge_plain_language,
)
from app.ml.orc_policy import CLASSES, accuracy, featurize, train, ORCPolicy
from scripts.train_orc_policy import build_training_data


# --------------------------------------------------------------------------- #
# RL ORC-classification policy
# --------------------------------------------------------------------------- #
def test_policy_learns_separable_orc_mapping():
    data = build_training_data(per_class=8)
    policy, hist = train(data, epochs=500, lr=0.5)
    # Expected policy gradient converges to the separable optimum.
    assert hist["greedy_accuracy"] == 1.0
    # Generalizes to unseen (differently-seeded) variants of each profile.
    holdout = build_training_data(per_class=1, seed=123)
    assert accuracy(policy, holdout) >= 0.9


def test_policy_probs_are_a_distribution():
    x = featurize({"product_type": "DDA", "owners": [{"party_id": "O1", "name": "a"}]},
                  {"customer_type": "INDIVIDUAL"})
    p = ORCPolicy().probs(x)
    assert set(p) == set(CLASSES)
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_policy_round_trips_through_disk(tmp_path):
    data = build_training_data(per_class=4)
    policy, _ = train(data, epochs=200)
    path = tmp_path / "policy.json"
    policy.save(path)
    reloaded = ORCPolicy.load(path)
    x = data[0][0]
    assert reloaded.predict(x) == policy.predict(x)


# --------------------------------------------------------------------------- #
# Fireworks LLM-as-judge evals (heuristic fallback path)
# --------------------------------------------------------------------------- #
_GOOD = {
    "orc": "TST",
    "insured_amount": "450000.00", "coverage_limit": "1250000.00",
    "aggregated_pi": "450000.00",
    "rationale": "Trust account under §330.10: $250,000 SMDIA per beneficiary "
                 "(2 beneficiaries) yields $450,000 insured of the total P&I.",
    "evidence": {"beneficiaries": 2, "smdia": "250000", "rule_citation": "12 CFR 330.10"},
}
_BAD = {"orc": "TST", "insured_amount": "0", "coverage_limit": "0",
        "aggregated_pi": "0", "rationale": "", "evidence": {}}


def test_judges_score_grounded_result_high_and_empty_low():
    for judge in (judge_rationale_grounding, judge_evidence_support, judge_plain_language):
        good = judge(_GOOD)
        bad = judge(_BAD)
        assert good["grader"] == "heuristic"  # no API key in CI
        assert 0.0 <= good["score"] <= 1.0 and 0.0 <= bad["score"] <= 1.0
        assert good["score"] > bad["score"], f"{judge.__name__} did not separate good/bad"


def test_evaluate_determination_aggregates():
    report = evaluate_determination([_GOOD])
    assert set(report["by_judge"]) == {"rationale_grounding", "evidence_support", "plain_language"}
    assert report["passed"] is True
    assert 0.0 <= report["mean_score"] <= 1.0
