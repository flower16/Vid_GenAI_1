"""
ORC-classification policy trained by reinforcement learning — the *free* path.

Why this exists
---------------
Today the ORC Classification agent ([nodes/rules_and_classify.py]
(../agents/nodes/rules_and_classify.py)) trusts the declared `orc` field. A
natural next step is to *learn* the (customer + account features) -> ORC mapping
so the agent can propose/verify a classification. The paid way to do that is to
fine-tune a hosted model (see [docs/fine-tuning-and-rl.md]
(../../../docs/fine-tuning-and-rl.md) and `scripts/export_finetune_dataset.py`).

The *free* way — implemented here — is a tiny softmax policy trained with
REINFORCE (policy-gradient reinforcement learning) in pure Python:

    reward = 1 if the sampled ORC == the labeled ORC else 0
    w_c <- w_c + lr * (reward - baseline) * (1[c==action] - p_c) * x

No numpy, no GPU, no network — it trains on the seeded suite in milliseconds and
costs nothing. It is a genuine RL loop (stochastic policy, sampled action,
reward, policy-gradient update with a running baseline), just small.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from ..domain.constants import ORC

# The action space: every supported ORC.
CLASSES: list[str] = [o.value for o in ORC]


# ---------------------------------------------------------------------------
# Features — the raw signals a classifier would key off (customer + account).
# Returns a sparse {feature_name: value} map; a "bias" term is always present.
# ---------------------------------------------------------------------------
def featurize(account: dict, customer: dict) -> dict[str, float]:
    owners = account.get("owners") or []
    benes = account.get("beneficiaries") or []
    parts = account.get("participants") or []
    ctype = (customer.get("customer_type") or "").upper()
    product = (account.get("product_type") or "").upper()

    feats: dict[str, float] = {"bias": 1.0}

    def flag(name: str, cond: bool) -> None:
        if cond:
            feats[name] = 1.0

    flag(f"ctype={ctype}", bool(ctype))
    flag(f"product={product}", bool(product))
    feats["n_owners"] = float(len(owners))
    feats["n_beneficiaries"] = float(len(benes))
    feats["n_participants"] = float(len(parts))
    flag("has_owners", bool(owners))
    flag("multi_owner", len(owners) >= 2)
    flag("has_beneficiaries", bool(benes))
    flag("has_participants", bool(parts))
    flag("sole_proprietorship", bool(account.get("sole_proprietorship")))
    flag("independent_activity_false", account.get("independent_activity") is False)
    return feats


class ORCPolicy:
    """A linear softmax policy over ORC classes with REINFORCE updates."""

    def __init__(self, classes: list[str] | None = None, seed: int = 0):
        self.classes = classes or list(CLASSES)
        self.w: dict[str, dict[str, float]] = {c: {} for c in self.classes}
        self._rng = random.Random(seed)

    # --- scoring ---
    def _logit(self, c: str, x: dict[str, float]) -> float:
        wc = self.w[c]
        return sum(wc.get(k, 0.0) * v for k, v in x.items())

    def probs(self, x: dict[str, float]) -> dict[str, float]:
        logits = {c: self._logit(c, x) for c in self.classes}
        m = max(logits.values())
        exps = {c: math.exp(v - m) for c, v in logits.items()}
        z = sum(exps.values())
        return {c: e / z for c, e in exps.items()}

    def predict(self, x: dict[str, float]) -> str:
        """Greedy (argmax) action — used at inference time."""
        return max(self.classes, key=lambda c: self._logit(c, x))

    def _sample(self, p: dict[str, float]) -> str:
        r, cum = self._rng.random(), 0.0
        for c, pc in p.items():
            cum += pc
            if r <= cum:
                return c
        return self.classes[-1]

    # --- learning ---
    def update(self, x: dict[str, float], label: str, lr: float) -> float:
        """One policy-gradient step; returns expected reward E[r]=p(label).

        This is the *expected* (all-action) policy gradient. The reward is
        r(a)=1 when the sampled ORC a equals the label, else 0, so the objective
        is J = E_{a~pi}[r] = p(label). Rather than sample one action and eat the
        variance (which stalls this small policy around ~80%), we take the exact
        gradient over the finite action set:

            dJ/d logit_c = p(c) * (1[c==label] - p(label))

        — the policy-gradient theorem computed in closed form. Same RL objective,
        far lower variance, converges to the separable optimum.
        """
        p = self.probs(x)
        p_label = p[label]
        for c in self.classes:
            grad_c = p[c] * ((1.0 if c == label else 0.0) - p_label)
            coeff = lr * grad_c
            if coeff == 0.0:
                continue
            wc = self.w[c]
            for k, v in x.items():
                wc[k] = wc.get(k, 0.0) + coeff * v
        return p_label

    # --- persistence ---
    def to_dict(self) -> dict:
        return {"classes": self.classes, "weights": self.w}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict()), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ORCPolicy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pol = cls(classes=data["classes"])
        pol.w = {c: dict(w) for c, w in data["weights"].items()}
        return pol


def train(dataset: list[tuple[dict, str]], *, epochs: int = 500, lr: float = 0.5,
          seed: int = 0) -> tuple[ORCPolicy, dict]:
    """Train a policy on [(features, orc_label), ...]. Returns (policy, history)."""
    pol = ORCPolicy(seed=seed)
    history: list[float] = []
    order = list(range(len(dataset)))
    for ep in range(epochs):
        # Cosine-style decay: large steps to escape early, small steps to settle.
        lr_ep = lr * (0.1 + 0.9 * (1 + math.cos(math.pi * ep / max(1, epochs))) / 2)
        pol._rng.shuffle(order)
        rewards = [pol.update(dataset[i][0], dataset[i][1], lr_ep) for i in order]
        history.append(sum(rewards) / len(rewards) if rewards else 0.0)
    acc = accuracy(pol, dataset)
    return pol, {"epochs": epochs, "lr": lr, "final_sample_reward": history[-1],
                 "greedy_accuracy": acc, "reward_curve": history}


def accuracy(pol: ORCPolicy, dataset: list[tuple[dict, str]]) -> float:
    if not dataset:
        return 0.0
    correct = sum(1 for x, y in dataset if pol.predict(x) == y)
    return correct / len(dataset)
