"""
Export a supervised fine-tuning dataset for the ORC-classification task, in the
chat JSONL format Fireworks (and OpenAI) fine-tuning accept.

This is the *paid* path's data-prep step — and generating the file is itself
free. Each line is one chat example teaching a model to output the ORC code for
a (customer, account) description; a fine-tuned small model can then replace or
check the classification agent at low latency/cost. The training run itself is
what costs money on Fireworks, so this script only writes the file — it never
uploads or launches a job.

Usage (from backend/):
    python scripts/export_finetune_dataset.py                    # -> data/orc_finetune.jsonl
    python scripts/export_finetune_dataset.py --out data/x.jsonl --per-class 12
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.train_orc_policy import build_training_data, _PROFILES  # noqa: E402
from app.domain.orc.rules import ORC_RULES  # noqa: E402

_SYSTEM = ("You are an FDIC Part 370 deposit-insurance classifier. Given a customer "
           "and account, respond with ONLY the Ownership Right & Capacity (ORC) code "
           "from this set: " + ", ".join(o.value for o in ORC_RULES) + ".")


def _describe(orc: str) -> str:
    """Natural-language account description from the ORC's profile."""
    p = _PROFILES[orc]
    parts = [f"Customer type: {p['ctype'].title()}.",
             f"Account product: {p['product']}."]
    if p.get("owners"):
        parts.append(f"{p['owners']} account owner(s).")
    if p.get("benes"):
        parts.append(f"{p['benes']} named beneficiary(ies).")
    if p.get("participants"):
        parts.append(f"{p['participants']} plan participant(s)/mortgagor(s).")
    return " ".join(parts)


def build_chat_examples(per_class: int) -> list[dict]:
    """One chat example per synthetic account; label = the ORC code."""
    examples: list[dict] = []
    # Reuse the same synthetic generator the RL policy trains on, so the two
    # learning paths (RL / fine-tune) see the same task.
    for _feats, orc in build_training_data(per_class=per_class):
        examples.append({"messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _describe(orc)},
            {"role": "assistant", "content": orc},
        ]})
    return examples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/orc_finetune.jsonl")
    ap.add_argument("--per-class", type=int, default=10)
    args = ap.parse_args()

    examples = build_chat_examples(args.per_class)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"Wrote {len(examples)} chat examples -> {out}")
    print("\nThis file is Fireworks/OpenAI fine-tune ready. To train on Fireworks "
          "(this step costs money — the export above did not):")
    print("  firectl create dataset orc-classify " + str(out))
    print("  firectl create fine-tuning-job --dataset orc-classify \\")
    print("      --base-model accounts/fireworks/models/llama-v3p1-8b-instruct")
    print("\nThe zero-cost alternative is the RL policy: scripts/train_orc_policy.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
