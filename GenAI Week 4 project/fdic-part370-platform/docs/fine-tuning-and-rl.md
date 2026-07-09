# Fine-tuning & Reinforcement Learning — where they fit, and the free path

The platform is deliberately **rules-first**: the coverage math lives in
`domain/orc/engine.py` and is unit-tested against the FDIC guide, so we never
want an LLM *doing arithmetic*. That leaves two places where a *learned* model
genuinely helps, and this doc recommends one of each and ships a **zero-cost**
implementation.

## Where learning helps (and where it must not)

| Task | Learnable? | Verdict |
|------|-----------|---------|
| Coverage arithmetic (insured/uninsured) | No — must stay deterministic & auditable | Keep in `engine.py` |
| **ORC classification** (customer+account → ORC code) | Yes — pattern from structured features | ✅ good fine-tune / RL target |
| Rationale wording quality | Yes — but judged, not trained here | Scored by the [Fireworks judges](evals.md) |
| Pending-routing policy (which reason code) | Yes — sequential decision w/ reward | 🔶 good RL target (future) |

## Recommended use case #1 — Fine-tune a small model for ORC classification

**Why.** Today the ORC Classification agent trusts the declared `orc` field. A
small fine-tuned model can *propose* and *cross-check* the ORC from the raw
customer/account features, catching mis-declared capacities before they reach
the (correct-but-blind) engine. A fine-tuned 8B model is cheap and low-latency
versus prompting a frontier model per account.

**How (paid — data prep is free).**
[`scripts/export_finetune_dataset.py`](../backend/scripts/export_finetune_dataset.py)
writes a chat-format JSONL that Fireworks/OpenAI fine-tuning accept:

```bash
cd backend
python scripts/export_finetune_dataset.py          # -> data/orc_finetune.jsonl (free)
# The training run below costs money; the export above does not:
firectl create dataset orc-classify data/orc_finetune.jsonl
firectl create fine-tuning-job --dataset orc-classify \
    --base-model accounts/fireworks/models/llama-v3p1-8b-instruct
```

Each line teaches: *system* = "classify into one ORC code", *user* = a
natural-language account description, *assistant* = the ORC code.

## Recommended use case #2 (implemented, **$0**) — RL policy for ORC classification

Instead of paying to fine-tune a hosted model, we learn the same mapping locally
with **reinforcement learning**:
[`app/ml/orc_policy.py`](../backend/app/ml/orc_policy.py) is a linear softmax
policy over the 15 ORC classes, trained with the **policy-gradient theorem**:

```
reward  r(a) = 1 if the chosen ORC a == the true ORC, else 0
objective    J = E_{a~π(·|x)}[ r(a) ] = π(label | x)
update       w_c ← w_c + lr · π(c|x)·(1[c==label] − π(label|x)) · x
```

We use the **expected (all-action) policy gradient** — the exact gradient over
the finite ORC action set rather than a single sampled action. It's the same RL
objective with far lower variance, so the tiny policy converges instead of
stalling. Pure Python, no numpy/GPU/network → **trains in <1s for $0**:

```bash
cd backend
python scripts/train_orc_policy.py                 # train + report
python scripts/train_orc_policy.py --save models/orc_policy.json
```

```
Reinforcement training on 120 labeled examples (15 ORC classes) — pure Python, $0.
epochs=500  lr=0.5
final expected reward E[r]  : 1.000
greedy training accuracy    : 100.0%
Hold-out accuracy           : 100.0%
```

Tests in [`tests/test_ml_and_fireworks_evals.py`](../backend/tests/test_ml_and_fireworks_evals.py)
assert convergence, that `probs()` is a valid distribution, and disk round-trip.

### Fine-tuning vs RL here — same task, two costs

| | Fine-tune (paid) | RL policy (this repo, free) |
|--|------------------|------------------------------|
| Model | hosted 8B, updated by Fireworks | 15-class linear softmax, on-device |
| Signal | supervised next-token | reward (1 = correct ORC) |
| Cost | GPU training + hosting | **$0** (pure Python) |
| Artifact | fine-tuned model id | `models/orc_policy.json` |
| Use | drop-in classifier via API | in-process check in the agent |

Both consume the **same** synthetic labeled set, so you can start free with the
RL policy and graduate to a fine-tune when the labeled data grows.

## Next RL target (not yet implemented)

Pending-routing is a natural **sequential** RL problem: state = the finding set,
action = pending reason code (A/B/OI/RAC/AR*), reward = the in-workflow eval
verdict (`pending_routing` PASS = +1). The same expected-policy-gradient trainer
generalizes to it once we log routed determinations as episodes.
