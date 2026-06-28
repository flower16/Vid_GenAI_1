# Evals — How Quality Is Measured (LangSmith)

The platform evaluates determinations at **two layers**:

1. **In-workflow Evals Agent** — runs on *every* determination as the last node
   of the LangGraph workflow ([nodes/output_and_report.py](../backend/app/agents/nodes/output_and_report.py),
   `evals_agent`). Returns PASS / FAIL / WARNING inline with the result, and is
   surfaced as chips in the UI Evidence Panel.
2. **LangSmith offline eval framework** — runs a labeled dataset through the
   workflow and scores it with named evaluators
   ([evals/langsmith_evals.py](../backend/app/evals/langsmith_evals.py)). Used in
   CI and for regression tracking. When LangSmith isn't configured it runs the
   same evaluators in-process (`evaluate_local`).

## The evaluators

Each evaluator is a pure function `fn(output, example) -> {key, score (0|1), comment}`.

### Input evals (data quality)
| Evaluator | Key | Checks |
|-----------|-----|--------|
| `eval_required_data` | `input_completeness` | # of blocking (FAIL) findings matches the example's `expect_input_fail` |
| `eval_valid_ssn` | `ssn_validation` | SSN_MISSING / SSN_INVALID flagged iff `expect_ssn_issue` |

### Output evals (calculation correctness)
| Evaluator | Key | Checks |
|-----------|-----|--------|
| `eval_pi_reconciles` | `pi_reconciliation` | insured + uninsured == aggregated P&I for every ORC |
| `eval_limits_respected` | `coverage_limits` | insured ≤ coverage limit for every ORC |
| `eval_expected_insured` | `expected_insured` | total insured == labeled `expected_insured` |
| `eval_pending_routing` | `pending_routing` | the labeled `expected_pending_reason` appears |
| `eval_bus_treatment` | `bus_treatment` | BUS coverage uses the labeled §330.11 `expected_bus_treatment` (`per_entity_independent` / `pass_through_members`) |

> **Adding an evaluator** (the `bus_treatment` pattern): (1) write a pure
> `fn(output, example) -> {key, score, comment}` in `langsmith_evals.py`,
> (2) append it to `OUTPUT_EVALS` (it auto-attaches via the `_make_evaluator`
> factory), (3) if it reads a new label, add that label to the dataset rows and
> to the `upload()` metadata list in `seed_langsmith_dataset.py`.

### System evals (reconciliation)
The in-workflow Evals Agent additionally checks **deposit-balance reconciliation**
and **summary-report reconciliation** (Table 1 insured + uninsured + pending ==
total deposits), mirroring the Compliance Review Manual checks (Guide §2.4).

## How LangSmith is wired

**Tracing.** [main.py](../backend/app/main.py) enables LangSmith tracing when
configured, so every agent/node run is captured as a trace:
```python
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project   # "fdic-part370"
```
Set `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` in `.env`.

**Offline evaluation.** `evaluate_langsmith(dataset_name)` runs a LangSmith
dataset through the workflow and attaches every evaluator:
```python
from langsmith.evaluation import evaluate
evaluate(
    target,                          # inputs -> determination output
    data=dataset_name,               # a LangSmith dataset of labeled examples
    evaluators=[... ALL_EVALS ...],  # input + output evaluators
    experiment_prefix="fdic-part370",
)
```
Results appear in the LangSmith UI as an **experiment** (one row per example,
one column per evaluator score).

## Snowflake ↔ LangSmith bridge

The Snowflake `LANGSMITH_EVAL_RESULTS` table ([db/snowflake_ddl.sql](../../db/snowflake_ddl.sql),
keyed by `DETERMINATION_ID` + `EVAL_NAME`, with a nullable `LANGSMITH_RUN_ID`) is
populated by the **in-workflow Evals Agent** every time a determination is
persisted ([db/persistence.py](../backend/app/db/persistence.py)). So the table
fills up from real determinations, not from the offline experiment.

To make those per-determination evals visible **in LangSmith**, run the sync:

```bash
cd backend
python scripts/sync_evals_to_langsmith.py --dry-run   # preview
python scripts/sync_evals_to_langsmith.py             # sync unlinked rows
python scripts/sync_evals_to_langsmith.py --all       # re-sync everything
```

[scripts/sync_evals_to_langsmith.py](../backend/scripts/sync_evals_to_langsmith.py)
reads the Snowflake rows, logs **one LangSmith run per determination** with one
**feedback** score per eval (`PASS=1`, `WARNING=0.5`, `FAIL=0`), then writes the
new `LANGSMITH_RUN_ID` back into Snowflake so each row links to its LangSmith run.
The runs land in the `fdic-part370` project (filter by run name `determination-…`).

Example run:
```
8 eval rows across 2 determination(s) to sync.
  b035f8bd…  -> LangSmith run 644be1c0  (4 feedback)
  de3d6acd…  -> LangSmith run a7694bca  (4 feedback)
Synced 2 determination(s) to LangSmith project 'fdic-part370'.
```
After syncing, `SELECT ... LANGSMITH_RUN_ID FROM LANGSMITH_EVAL_RESULTS` shows the
linked run id on every row (0 unlinked).

A dataset example looks like:
```json
{
  "inputs": { "customer": {...}, "accounts": [...] },
  "expected_insured": 250000,
  "expect_input_fail": false,
  "expect_ssn_issue": false,
  "expected_pending_reason": null
}
```

## Local run (no LangSmith required)

`evaluate_local(dataset)` runs the identical evaluators in-process — this is what
CI executes:

```python
from app.evals.langsmith_evals import evaluate_local
report = evaluate_local(dataset)   # {"total": N, "passed": M, "rows": [...]}
```

### Actual output

Dataset: a single SGL account at $350K (expect $250K insured, no input failure)
and a customer with a missing SSN (expect input failure + SSN issue):

```
passed 2 of 2
 example: sgl_over_limit -> PASS
     input_completeness = 1 | 0 blocking findings, expected_fail=False
     ssn_validation     = 1 | ['ADDR_MISSING']
     pi_reconciliation  = 1 | insured + uninsured == total PI
     coverage_limits    = 1 |
     expected_insured   = 1 | got 250000.00, expected 250000
     pending_routing    = 1 | no label
 example: missing_ssn -> PASS
     input_completeness = 1 | 2 blocking findings, expected_fail=True
     ssn_validation     = 1 | ['ADDR_MISSING', 'CUST_NAME_MISSING', 'SSN_MISSING']
     pi_reconciliation  = 1 | insured + uninsured == total PI
     coverage_limits    = 1 |
     expected_insured   = 1 | no label
     pending_routing    = 1 | no label
```

The `missing_ssn` example correctly produces 2 blocking findings and the
SSN_MISSING flag — and the Pending Agent routes that account to the Pending File
with reason code **A** (missing required data element).

## Seed dataset + run the experiment (one command)

[scripts/seed_langsmith_dataset.py](../backend/scripts/seed_langsmith_dataset.py)
builds **one labeled example per ORC plus a 2nd BUS branch** (16 total, each with
a known `expected_insured`) and can upload it to LangSmith and run the experiment:

```bash
cd backend
python scripts/seed_langsmith_dataset.py            # local eval (no key needed)
python scripts/seed_langsmith_dataset.py --upload   # create/replace LS dataset
python scripts/seed_langsmith_dataset.py --run      # upload + run the experiment
```

With `LANGSMITH_API_KEY` set, `--run` creates the `fdic-part370-orc-suite`
dataset, runs every evaluator against each example, and posts an experiment to
the LangSmith UI. Without a key it falls back to the in-process runner.

Local run output (all ORCs):
```
Built 16 labeled examples (one per ORC + a 2nd BUS branch).
Local eval: 16/16 examples passed
  [PASS] SGL_over_limit   [PASS] JNT_two_owners   [PASS] TST_grantor_two_benes
  [PASS] CRA_retiree      [PASS] EBP_two_participants  [PASS] BUS_entity
  [PASS] BUS_non_independent_members
  [PASS] GOV1_custodian   [PASS] GOV2_custodian   [PASS] GOV3_out_of_state
  [PASS] MSA_two_mortgagors  [PASS] PBA_two_bondholders  [PASS] DIT_one_beneficiary
  [PASS] ANC_two_annuitants  [PASS] BIA_native_american  [PASS] DOE_idi_program
```

## CI gate

[.github/workflows/ci-cd.yaml](../../.github/workflows/ci-cd.yaml) runs `pytest`
(35 ORC sample-calculation tests + workflow + eval tests) and imports the eval
framework on every push; deployment is blocked unless they pass.
