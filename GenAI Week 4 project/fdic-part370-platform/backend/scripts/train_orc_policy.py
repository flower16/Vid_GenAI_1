"""
Train the ORC-classification policy with reinforcement learning — costs $0.

Generates a labeled set of (customer, account) -> ORC examples with the
characteristic signals each capacity carries (a BUSINESS entity account -> BUS,
a GOVERNMENT demand account -> GOV2, a plan account with participants -> EBP,
...), then trains the pure-Python REINFORCE policy in `app/ml/orc_policy.py`.

No API key, no GPU, no network — trains in well under a second.

Usage (from backend/):
    python scripts/train_orc_policy.py                       # train + report
    python scripts/train_orc_policy.py --save models/orc_policy.json
"""

from __future__ import annotations

import argparse
import pathlib
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ml.orc_policy import CLASSES, featurize, train, accuracy  # noqa: E402

# Characteristic profile per ORC. Each carries a distinct signature over the
# featurized signals (customer type, product, party counts) so the policy has a
# separable target to learn.
_PROFILES: dict[str, dict] = {
    "SGL":  {"ctype": "INDIVIDUAL", "product": "DDA", "owners": 1},
    "JNT":  {"ctype": "JOINT",      "product": "SAV", "owners": 2},
    "TST":  {"ctype": "TRUST",      "product": "SAV", "owners": 1, "benes": 2},
    "CRA":  {"ctype": "INDIVIDUAL", "product": "CDS", "owners": 1},
    "EBP":  {"ctype": "PLAN",       "product": "MMA", "participants": 3},
    "BUS":  {"ctype": "BUSINESS",   "product": "DDA", "owners": 1},
    "GOV1": {"ctype": "GOVERNMENT", "product": "SAV", "owners": 1, "benes": 1},
    "GOV2": {"ctype": "GOVERNMENT", "product": "DDA", "owners": 1},
    "GOV3": {"ctype": "GOVERNMENT", "product": "CDS", "owners": 1},
    "MSA":  {"ctype": "BUSINESS",   "product": "DDA", "owners": 1, "participants": 2},
    "PBA":  {"ctype": "GOVERNMENT", "product": "MMA", "participants": 2},
    "DIT":  {"ctype": "FIDUCIARY",  "product": "SAV", "benes": 1},
    "ANC":  {"ctype": "BUSINESS",   "product": "MMA", "owners": 1, "benes": 2},
    "BIA":  {"ctype": "FIDUCIARY",  "product": "CDS", "benes": 1},
    "DOE":  {"ctype": "BUSINESS",   "product": "CDS", "owners": 1},
}


def _parties(n: int) -> list[dict]:
    return [{"party_id": f"P{i}", "name": f"Party {i}"} for i in range(n)]


def build_training_data(per_class: int = 8, seed: int = 0) -> list[tuple[dict, str]]:
    """Synthesize `per_class` noisy variants of each ORC profile."""
    rng = random.Random(seed)
    data: list[tuple[dict, str]] = []
    for orc in CLASSES:
        p = _PROFILES[orc]
        for _ in range(per_class):
            # Add mild noise so the policy generalizes rather than memorizing.
            owners = max(0, p.get("owners", 0) + rng.choice([0, 0, 1] if p.get("owners") else [0]))
            account = {
                "product_type": p["product"],
                "owners": _parties(owners),
                "beneficiaries": _parties(p.get("benes", 0)),
                "participants": _parties(p.get("participants", 0)),
                "sole_proprietorship": False,
                "independent_activity": None,
            }
            customer = {"customer_type": p["ctype"]}
            data.append((featurize(account, customer), orc))
    rng.shuffle(data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", metavar="PATH", help="write trained policy weights (JSON)")
    ap.add_argument("--epochs", type=int, default=500)
    ap.add_argument("--per-class", type=int, default=8)
    args = ap.parse_args()

    data = build_training_data(per_class=args.per_class)
    print(f"Reinforcement training on {len(data)} labeled examples "
          f"({len(CLASSES)} ORC classes) — pure Python, $0.\n")

    policy, hist = train(data, epochs=args.epochs)
    print(f"epochs={hist['epochs']}  lr={hist['lr']}")
    print(f"final expected reward E[r]  : {hist['final_sample_reward']:.3f}")
    print(f"greedy training accuracy    : {hist['greedy_accuracy']:.1%}")

    # Show the learned mapping on one fresh example per class.
    holdout = build_training_data(per_class=1, seed=999)
    print(f"\nHold-out accuracy           : {accuracy(policy, holdout):.1%}")

    if args.save:
        path = pathlib.Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        policy.save(path)
        print(f"\nSaved policy weights -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
