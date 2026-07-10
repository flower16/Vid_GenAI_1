# FDIC Part 370 Insurance Determination Platform — Walkthrough

A practical guide to what this platform is, how it's built, how to run it, and
everything that was set up/fixed in this session. Read top-to-bottom, or jump to
a section.

- [1. What it does](#1-what-it-does)
- [2. Architecture at a glance](#2-architecture-at-a-glance)
- [3. How to run it](#3-how-to-run-it)
- [4. The determination workflow (9 agents)](#4-the-determination-workflow-9-agents)
- [5. ORC coverage logic](#5-orc-coverage-logic)
- [6. BUS — full eligibility branching (§330.11)](#6-bus--full-eligibility-branching-33011)
- [7. Integrations: Pinecone, LangSmith, Snowflake, Fireworks + Replit deploy](#7-integrations-pinecone-langsmith-snowflake-fireworks--replit-deploy)
- [8. Data model](#8-data-model)
- [9. API surface](#9-api-surface)
- [10. Testing & evals](#10-testing--evals)
- [11. Session changelog (what we changed)](#11-session-changelog-what-we-changed)
- [12. Troubleshooting / gotchas](#12-troubleshooting--gotchas)

---

## 1. What it does

The platform determines **FDIC deposit-insurance coverage** for a customer's
accounts under **12 CFR Part 370**. Given a customer and their deposit accounts,
it:

1. Validates the input data (customer + accounts).
2. Classifies each account into an **ORC** (Ownership Right and Capacity).
3. Calculates insured vs. uninsured amounts per the Part 370 rules.
4. Routes incomplete records to a **Pending File** with a reason code.
5. Produces output files, a summary report, and self-evaluations.
6. Persists the full audit trail.

It runs fully **locally** without any external service (RAG falls back to
in-code rules; persistence falls back to a local JSONL log; the LLM-as-judge
evals fall back to a free heuristic). External integrations (Pinecone, LangSmith,
Snowflake, Fireworks, Azure AD) light up when their keys are set, and Replit
hosts the whole stack as one web process. Check status any time with
`python scripts/check_integrations.py --live`.

---

## 2. Architecture at a glance

```
frontend/ (React + Vite + MUI + AG Grid)   ── http ──►   backend/ (FastAPI)
   AccountForm, CustomerForm, EvidencePanel                 │
                                                            ▼
                                          LangGraph workflow (9 agents)
                                                            │
                                   pure ORC calculation engine (domain/orc)
                                                            │
                       ┌────────────────────┬───────────────┴───────────────┐
                       ▼                    ▼                                ▼
                  Pinecone RAG         Snowflake persistence          LangSmith evals
                 (rule retrieval)     (results + audit trail)        (experiment tracking)
```

- **Backend:** Python 3.12, FastAPI + LangGraph. The calculation engine is
  **pure** (no I/O) so it's fully unit-testable.
- **Frontend:** React + Vite on port **5173**, Material UI + AG Grid.
- **Auth:** Azure AD SSO + RBAC, **bypassed in `local`** with a synthetic Admin
  so you can run without a tenant.

Key backend folders (`backend/app/`):
| Path | Role |
|---|---|
| `agents/graph.py` | LangGraph wiring (nodes + edges) |
| `agents/nodes/` | the 9 agent functions |
| `agents/state.py` | shared graph state (TypedDict) |
| `domain/constants.py` | ORC codes, coverage shapes, SMDIA, pending reasons |
| `domain/orc/engine.py` | the calculation engine (one function per shape) |
| `domain/orc/rules.py` | per-ORC rule text + citations |
| `domain/models.py` | Pydantic models (Customer, Account, CoverageResult, …) |
| `rag/retriever.py` | Pinecone RAG + in-code fallback |
| `db/persistence.py` | Snowflake persistence + local JSONL fallback |
| `evals/langsmith_evals.py` | evaluators + LangSmith runner |
| `api/routes.py` | REST endpoints |

---

## 3. How to run it

**Prerequisites:** Python 3.12 (miniconda), Node/npm. Both already verified.

**One-time setup** (Windows PowerShell, from the project root):
```powershell
.\setup.ps1            # installs deps, runs tests + local evals, seeds (guarded)
.\setup.ps1 -SkipDeps  # faster re-run, skips pip/npm install
```

**Start the platform** — two terminals:
```powershell
# Terminal 1 — backend
cd "F:\GenAI Week 4 project\fdic-part370-platform\backend"
python -m uvicorn app.main:app --port 8000 --reload   # http://127.0.0.1:8000/docs

# Terminal 2 — frontend
cd "F:\GenAI Week 4 project\fdic-part370-platform\frontend"
npm run dev                                            # http://localhost:5173/
```

Open **http://localhost:5173/**, fill in a customer + accounts, and run a
determination. Keys auto-load from `backend/.env` (see §7).

---

## 4. The determination workflow (9 agents)

Defined in `agents/graph.py`. Validation + rules run in parallel, then converge:

```
rules ─┐
       ├─► classify ─► insurance_calculation ─► pending ─► output_file ─► summary ─► evals ─► END
customer ┤
account ─┘
```

| # | Agent (node) | What it does |
|---|---|---|
| 1 | `fdic_rules` | Retrieve Part 370 rules per ORC (Pinecone RAG, or in-code fallback) |
| 2 | `customer_validation` | Validate demographics, SSN/TIN format, customer type |
| 3 | `account_validation` | Validate balances, ownership structure, ORC-specific roster requirements |
| 4 | `classify` | Assign ORC + build aggregation groups by `(family, depositor)` |
| 5 | `insurance_calculation` | Run the ORC engine over each group → coverage results |
| 6 | `pending_determination` | Route incomplete records to the Pending File with a reason code |
| 7 | `output_file` | Generate customer / account / participant / pending files |
| 8 | `summary` | Build the summary report (Table 1 coverage, reconciliation) |
| 9 | `evals` | Self-checks (reconciliation, limits, completeness) |

> Supports **iterative recalculation**: call again with
> `alt_recordkeeping_received=True` to clear "Alternative Recordkeeping" pending
> reasons and recompute.

---

## 5. ORC coverage logic

There are **15 ORCs**. Each maps to a **CoverageShape** that drives the math
(`domain/constants.py` → `ORC_CONFIG`):

| Shape | ORCs | Rule |
|---|---|---|
| `PER_OWNER` | SGL, JNT, CRA | `unique_owners × SMDIA`; each owner capped at SMDIA |
| `PER_OWNER_PER_BENE` | TST | `owners × min(benes,5) × SMDIA` (2024 trust rule) |
| `PER_PARTICIPANT` | EBP, PBA, DIT, ANC | pass-through to each participant's vested interest |
| `PER_PRINCIPAL` | MSA, BIA | pass-through to each mortgagor/principal |
| `PER_ENTITY` | BUS, DIT*, DOE | one SMDIA for the legal entity |
| `PER_CUSTODIAN` | GOV1, GOV2, GOV3 | one SMDIA per official custodian/public unit |

`SMDIA` = **$250,000** (the Standard Maximum Deposit Insurance Amount).

**PI (Principal & Interest)** = `balance + accrued_interest` — the insured base.

The engine (`domain/orc/engine.py`) has one pure function per shape; `calculate(orc, accounts)`
dispatches to it. BUS is special-cased (see next section).

---

## 6. BUS — full eligibility branching (§330.11)

BUS (corporation / partnership / unincorporated association) was extended this
session to follow the functional guide's **three eligibility branches**. Two new
model fields drive it: `Account.independent_activity` and `Account.sole_proprietorship`.

| Branch | Condition | Treatment | Where it shows in the UI |
|---|---|---|---|
| **Independent activity** | default / `independent_activity` True or unset | One SMDIA for the entity, separate from owners — §330.11(a). Unset → flagged `BUS_ACTIVITY_UNCONFIRMED` (assumed) | Aggregation & Coverage grid + Calculation Formula |
| **Not independent** | `independent_activity = False` | Funds split **equally among members**, each insured to SMDIA (pass-through) — §330.11(c) | Per-Owner (member) Allocation table |
| **Sole proprietorship** | `sole_proprietorship = True` | Reclassified to **SGL**; insured as the owner's single-ownership funds and **aggregated with their other SGL deposits** — §330.11 | Folds into the SGL row |

**Worked examples** (from the test suite):
- Independent, $400k → **$250k insured**, $150k uninsured.
- Not independent, 2 members, $400k → split $200k each, both fully insured → **$400k insured** ($500k limit).
- Sole prop $150k + SGL $150k → aggregated to $300k under SGL → **$250k insured**.

Implementation lives in:
`engine.py` (`_business`), `agents/nodes/rules_and_classify.py` (`_effective_orc`
sole-prop→SGL), `agents/nodes/validation.py` (BUS findings), `rules.py` (docs),
and the frontend `AccountForm.tsx` (the two BUS controls, shown only for ORC=BUS).

---

## 7. Integrations: Pinecone, LangSmith, Snowflake, Fireworks + Replit deploy

All keys live in `backend/.env`. They are **auto-exported to the OS environment**
at startup (`core/config.py` → `_export_to_env`) so libraries that read env vars
directly (langchain-pinecone, OpenAI, LangSmith) work without manual setup.

> **Every integration is optional and currently unconfigured** (no `backend/.env`
> in the repo). Each degrades cleanly, so the platform is fully usable with zero
> keys. See exactly what's wired and reachable any time:
> ```bash
> cd backend
> python scripts/check_integrations.py --live   # Snowflake / LangSmith / Fireworks / Azure AD / Pinecone
> ```
> The same data is served at `GET /api/v1/health/integrations?live=true` and shown
> as the AppBar **"Integrations N/5"** chip.
>
> | Integration | Role | Fallback when unconfigured |
> |---|---|---|
> | Pinecone | RAG over rule corpus | in-code rules (`domain/orc/rules.py`) |
> | LangSmith | tracing + experiment + eval sync | in-process `evaluate_local` |
> | Snowflake | persistence + audit + input lookups | `audit_log.jsonl` + sample rows |
> | Fireworks | LLM-as-judge evals; fine-tune target | free deterministic heuristic |
> | Azure AD | SSO + RBAC | synthetic Admin in `local` |

### Pinecone (RAG over the rule corpus)
- Index `fdic-part370` (dim 3072, cosine). Seeded with 15 ORC rule docs.
- Seed: `python scripts/seed_pinecone.py`
- Needs `PINECONE_API_KEY` + `OPENAI_API_KEY`. If absent, the FDIC Rules Agent
  falls back to the in-code corpus (`domain/orc/rules.py`).

### LangSmith (evaluation tracking)
Two distinct eval surfaces (don't confuse them):

**1. Offline experiment** — a labeled dataset scored by 7 named evaluators:
- Dataset `fdic-part370-orc-suite` (one labeled example per ORC + a 2nd BUS branch = 16).
- `python scripts/seed_langsmith_dataset.py --local`  → in-process eval (no key)
- `python scripts/seed_langsmith_dataset.py --run`    → upload + run experiment
- **7 evaluators** logged to LangSmith: `input_completeness`, `ssn_validation`,
  `pi_reconciliation`, `coverage_limits`, `expected_insured`, `pending_routing`,
  `bus_treatment` (checks the §330.11 BUS branch via `expected_bus_treatment`).
- **Adding an evaluator:** write a `fn(output, example) -> {key, score, comment}`
  in `langsmith_evals.py`, append it to `OUTPUT_EVALS`, and (if it reads a label)
  add that label to the dataset rows + the `upload()` metadata.

**2. Per-determination in-workflow evals** — agent #9 runs 7 self-checks on
*every* determination (`input_completeness`, `deposit_balance_reconciliation`,
`coverage_limit_respected`, `summary_report_reconciliation`,
`accounts_fully_accounted`, `ssn_validation`, `bus_treatment`). These persist to
the Snowflake `LANGSMITH_EVAL_RESULTS` table and sync to LangSmith.

**Bridging Snowflake → LangSmith (automatic).** On every determination,
`persist_determination` logs the evals to LangSmith as a **run with one feedback
score per eval** (PASS=1, WARNING=0.5, FAIL=0) and stores the **`LANGSMITH_RUN_ID`**
directly in the Snowflake rows — so evals show in **both** places with no manual
step. Runs land in the LangSmith project `fdic-part370` (filter by run name
`determination-…`). The sync script is now only a **backfill** for rows whose
`LANGSMITH_RUN_ID` is NULL (e.g. persisted while LangSmith was down):
```bash
python scripts/sync_evals_to_langsmith.py             # backfill unlinked rows
python scripts/sync_evals_to_langsmith.py --all       # re-sync everything
```

### Snowflake (persistence + audit)
- Database/schema: **`FDIC_PART370.CORE`**, 7 tables.
- Account identifier format that works here: **`UVAMSIL-EL81904`** (org-account).
- Create schema: `python scripts/init_snowflake.py`
- Seed sample input data: `python scripts/seed_snowflake_inputs.py` (rows prefixed `SF-`)

| Table | Filled by | Holds |
|---|---|---|
| `CUSTOMER`, `ACCOUNT`, `ACCOUNT_PARTICIPANT` | seed script (inputs) | sample inputs for inspection |
| `INSURANCE_RESULT` | each determination | one row per ORC: PI / limit / insured / uninsured |
| `CALCULATION_AUDIT` | each determination | full agent state / evidence (JSON) |
| `LANGSMITH_EVAL_RESULTS` | each determination; `LANGSMITH_RUN_ID` by the sync script | one row per in-workflow eval (name/status/detail), linked to a LangSmith run |
| `PENDING` | (schema present) | pending-file rows |

> The engine reads inputs from the **API request**, not from Snowflake. Snowflake
> stores **outputs**. The seeded input tables are for inspection / manual SQL.

### Fireworks (LLM-as-judge evals)
The deterministic evals prove the *math* reconciles; three **Fireworks judges**
score the qualitative parts the math can't — `rationale_grounding`,
`evidence_support`, `plain_language` ([evals/fireworks_evals.py](backend/app/evals/fireworks_evals.py)).
- Model: `accounts/fireworks/models/llama-v3p1-8b-instruct` over the OpenAI-compatible
  `/chat/completions` API (stdlib `urllib`, no extra dependency).
- **Free by default:** with no `FIREWORKS_API_KEY` each judge falls back to a
  deterministic heuristic (`grader="heuristic"`), so the suite runs at **$0**. Set
  the key to switch the same judges to the model (`grader="fireworks"`).
- Run standalone: `python scripts/run_fireworks_evals.py` (add `--json`).
- With `FIREWORKS_EVALS_IN_WORKFLOW=true` (default) the judges also run on every
  determination as `fw_*` scores → persisted to `LANGSMITH_EVAL_RESULTS` and synced
  to LangSmith alongside the deterministic checks.
- **There is no "app" in the Fireworks console** — it's a model API. Confirm calls
  landed via the Fireworks **Usage/Billing** dashboard; the only artifact you can
  create there is an optional fine-tuned model (below).

### Replit (one-process hosting)
`start.sh` runs the whole stack as a **single web process**: it installs backend
deps, builds the Vite frontend, and starts FastAPI, which serves both the API and
the built UI same-origin. That's exactly what `.replit` invokes
(`run = "bash start.sh"`, `deploymentTarget = "cloudrun"`, `replit.nix` pins
python-3.12 + nodejs-20). Secrets go in the Replit **Secrets** pane and arrive as
env vars read by `core/config.py`. The same `start.sh` also backs Docker/AKS.

### Learning: RL policy (shipped, free) vs. fine-tune (enabled, not run)
The coverage math is deterministic and never learned. The one learnable task —
**ORC classification** (customer + account → ORC code) — is addressed two ways over
the *same* synthetic labeled set ([docs/fine-tuning-and-rl.md](docs/fine-tuning-and-rl.md)):

- **RL policy — the learning that was actually done ($0).**
  [app/ml/orc_policy.py](backend/app/ml/orc_policy.py) is a 15-class linear softmax
  trained by the **expected (all-action) policy gradient**, pure Python, converging
  to 100% train/hold-out in <1s. Train it: `python scripts/train_orc_policy.py`
  (add `--save models/orc_policy.json`). No artifact is checked in; it trains
  in-process.
- **Fine-tune — enabled but not executed (paid).** No hosted fine-tune was run.
  `python scripts/export_finetune_dataset.py` only writes a Fireworks/OpenAI-ready
  chat JSONL (`data/orc_finetune.jsonl`); launching the job is the paid `firectl`
  step and is intentionally left out, so no fine-tuned model exists in the repo.

---

## 8. Data model

`domain/models.py` (Pydantic):
- **Customer**: `customer_id, first/last_name, ssn_tin, customer_type, address, …`
- **Account**: `account_number, customer_id, product_type, balance, accrued_interest,
  hold_amount, orc, owners[], beneficiaries[], participants[]`,
  plus BUS: `independent_activity`, `sole_proprietorship`.
  Property `principal_and_interest = balance + accrued_interest`.
- **Owner / Beneficiary / Participant**: party rosters that drive aggregation.
- **CoverageResult**: `orc, aggregated_pi, coverage_limit, insured_amount,
  uninsured_amount, rationale, accounts_included, evidence{}`.
- **PendingDecision / EvalResult / ValidationFinding**.

---

## 9. API surface

`api/routes.py`, prefix `/api/v1`:
| Method | Path | Purpose |
|---|---|---|
| GET | `/orcs` | ORC catalog for the UI dropdown |
| GET | `/orcs/{orc}/rules` | Rule detail for one ORC |
| POST | `/determinations` | Run the workflow + persist the audit trail |
| POST | `/determinations/{id}/recalculate` | Iterative recalculation (AR data arrived) |

Interactive docs: **http://127.0.0.1:8000/docs**. In `local`, auth is bypassed
with a synthetic Admin (no token needed).

---

## 10. Testing & evals

```powershell
cd backend
python -m pytest -q                                   # 43 tests
python scripts\seed_langsmith_dataset.py --local      # 16/16 examples (one per ORC + 2nd BUS branch)
```
- `tests/test_orc_calculations.py` — one worked calculation per ORC (+ BUS branches).
- `tests/test_workflow.py` — end-to-end workflow + sole-prop reclassification.

---

## 11. Session changelog (what we changed)

| Area | Change | Why |
|---|---|---|
| `setup.ps1` | Re-saved UTF-8 **with BOM** | PowerShell 5.1 mis-parsed Unicode → false "missing `}`" |
| `requirements.txt` | `snowflake-snowpark-python` → 1.27.0; `pinecone-client` → `pinecone==9.1.0` | Python 3.12 compat; removed duplicate pinecone package |
| `agents/graph.py` | Renamed colliding nodes → `classify`, `summary` | langgraph 0.2.60 forbids node name == state key |
| `core/config.py` | Auto-export `.env` keys to `os.environ` | langchain-pinecone/OpenAI read env vars directly |
| `db/persistence.py` | Fixed Snowflake INSERT (per-ORC rows w/ all columns); **added `LANGSMITH_EVAL_RESULTS` write** | INSERT was silently failing on NOT NULL `ORC`; eval table was empty |
| `scripts/init_snowflake.py` | UTF-8 console output | crashed on ✓/✗ on cp1252 consoles |
| **BUS feature** | `models.py`, `engine.py`, `rules_and_classify.py`, `validation.py`, `rules.py`, frontend `types` + `AccountForm.tsx`, tests | full §330.11 eligibility branching |
| `evals/langsmith_evals.py` | Factory-wrapped evaluators | fixed late-binding closure + bad param name; all 6 evaluators now log |
| `scripts/seed_snowflake_inputs.py` | **New** | seed one sample input per ORC into Snowflake |
| `scripts/sync_evals_to_langsmith.py` | **New** | push Snowflake eval rows to LangSmith as runs + feedback; fill `LANGSMITH_RUN_ID` |

---

## 12. Troubleshooting / gotchas

- **PowerShell "missing `}`" on a valid script** → the file is UTF-8 *without* a
  BOM. Re-save with a BOM (PS 5.1 otherwise reads it as cp1252).
- **`[Errno 10048]` on backend start** → port 8000 already in use:
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess
  Stop-Process -Id <PID> -Force
  ```
- **Frontend on 5174 instead of 5173** → 5173 was already taken; check the Vite
  output for the actual URL.
- **Snowflake "Incorrect username or password" right after it worked** → usually a
  **temporary lockout** (~15 min) from repeated failed logins, *not* a bad
  password. Stop retrying — every attempt resets the 15-minute timer. Confirm via
  the Snowsight browser login; wait, then retry once.
- **Snowflake account identifier** → use the **`ORG-ACCOUNT`** form
  (`UVAMSIL-EL81904`), not the locator-only `EL81904.region` form.
- **`uvicorn` not reflecting code changes** → start it with `--reload`.
- **BUS "didn't get insured" / "didn't show"** → customer *type* BUSINESS is not
  the same as an account *ORC* of BUS. Set the **account ORC dropdown** to BUS.
  Amounts above $250k show as *uninsured* (over the per-entity cap), not rejected.
  There is **no reject file** — incomplete records go to the **Pending File**.

---

---

## Appendix A — Per-ORC worked calculations

Every example below is pinned by a unit test in
`tests/test_orc_calculations.py`. `SMDIA = $250,000`. `PI = balance + accrued_interest`.

### SGL — Single ownership
- **Formula:** `unique_owners × SMDIA`; each owner capped at SMDIA. A single
  account with no explicit owner list → the customer is the one owner.
- **Example:** $350,000 single account → **insured $250,000 / uninsured $100,000**.
- **Aggregation:** $200k + $150k in two SGL accounts of the same owner →
  PI $350k → **insured $250,000** (one $250k limit across both).

### JNT — Joint ownership
- **Formula:** `unique_owners × SMDIA`; each person's combined share across all
  joint accounts capped at SMDIA.
- **Fully insured:** $500,000, 2 owners → limit 2 × $250k = $500k → **insured $500,000**.
- **Per-owner cap:** $700,000, 2 owners → each share $350k capped at $250k →
  **insured $500,000 / uninsured $200,000**.

### TST — Revocable/irrevocable trust (2024 rule)
- **Formula:** `owners × min(beneficiaries, 5) × SMDIA`.
- **Two beneficiaries:** 1 grantor × 2 benes → limit $500k; PI $450k → **insured $450,000**.
- **Five-beneficiary cap:** 7 benes → capped at 5 → limit $1,250,000; PI $2,000,000
  → **insured $1,250,000 / uninsured $750,000**.

### CRA — Certain retirement accounts
- **Formula:** `unique_owners × SMDIA` (like SGL).
- **Example:** $300,000 IRA → **insured $250,000**.

### EBP — Employee benefit plan (pass-through)
- **Formula:** pass-through to each participant's vested interest, each capped at SMDIA.
- **Example:** P1 $200k + P2 $300k → P1 fully insured, P2 capped at $250k →
  **insured $450,000 / uninsured $50,000**.

### BUS — Business / corporation / partnership  *(see §6)*
- **Independent (default):** $400,000 → **insured $250,000 / uninsured $150,000**.
- **Not independent, 2 members:** $400k split $200k each → **insured $400,000** ($500k limit).
- **Sole proprietorship:** folds into the owner's SGL (e.g. $150k BUS + $150k SGL
  → $300k SGL → **insured $250,000**).

### GOV1 / GOV2 / GOV3 — Public unit
- **Formula:** one SMDIA per unique (official custodian, public unit) — **no**
  2× multiplier inside a code.
- **GOV1:** $450,000 → **insured $250,000 / uninsured $200,000**.
- **GOV1 + GOV2, same custodian:** time/savings (GOV1) and demand (GOV2) are
  **separate** codes → each gets its own $250k → **$500,000 combined**.

### MSA — Mortgage servicing (pass-through to mortgagors, P&I)
- **Example:** M1 $250k + M2 $100k → **insured $350,000**.

### PBA — Public bond accounts (pass-through to bondholders)
- **Example:** BH1 $250k + BH2 $100k → **insured $350,000 / uninsured $0**.

### DIT — IDI as trustee of irrevocable trust (pass-through to beneficiaries)
- **Example:** 1 beneficiary (equal split, no amount) → PI $260k → **insured $250,000 / uninsured $10,000**.

### ANC — Annuity contract accounts (pass-through to annuitants)
- **Example:** 1 annuitant → PI $260k → **insured $250,000 / uninsured $10,000**.

### BIA — Custodian accounts for American Indians
- **Example:** 1 beneficiary → PI $150k → **insured $150,000** (fully insured).

### DOE — IDI under DOE Bank Deposit Financial Assistance Program
- **Formula:** one SMDIA per entity (like BUS independent).
- **Example:** $275,000 → **insured $250,000 / uninsured $25,000**.

### Invariants enforced by tests
- `insured + uninsured == aggregated_pi` for **every** ORC.
- Accrued interest is part of PI: $249,000 balance + $2,000 interest = $251,000 PI
  → **insured $250,000**.

---

## Appendix B — Step-by-step UI walkthrough

1. **Start both servers** (§3) and open **http://localhost:5173/**.
2. **Customer section:** enter `Customer ID`, name, `SSN/TIN`
   (format `123-45-6789` or `12-3456789`), and pick a **Customer Type**.
   - Missing/invalid SSN/TIN → the determination still runs but routes to the
     **Pending File** (reason A = missing, B = invalid).
3. **Add an account:** set `Account Number`, `Product Type`, `Balance`,
   `Accrued Interest`, and the **ORC** dropdown.
   - The **ORC dropdown is what classifies the account** — not the customer type.
     To test a business, set **ORC = BUS** (see step 5).
   - Party fields appear based on ORC (e.g. Co-Owners for JNT, Beneficiaries for
     TST, Plan Participants for EBP). Enter comma-separated names; for
     participants use `Name:Amount` (amount optional → equal split).
4. **Run** the determination. The **Evidence Panel** shows:
   - **Aggregation & Coverage** grid — ORC / PI / limit / insured / uninsured (every ORC).
   - **Per-Owner Allocation** — for SGL/JNT/CRA and **BUS non-independent** (per member).
   - **Trust** / **Pass-Through Participants** sections where relevant.
   - **Calculation Formula & AI Reasoning** — the rationale per ORC.
   - **Pending File** — any held records with reason codes.
   - **Evals** — the in-workflow self-checks (PASS/WARNING).
5. **BUS specifics (ORC = BUS):** two extra controls appear —
   - **Independent Activity:** *Assumed*/Yes → one $250k entity limit;
     *No* → pass-through to members (add 2+ Business Owners to see the split).
   - **Sole proprietorship** checkbox → the account folds into the customer's SGL.
6. **Recalculation:** re-submit with Alternative Recordkeeping data to clear
   AR* pending reasons (via the recalculate endpoint).

---

*Generated during the setup/working session. Keep alongside the code; update the
changelog as the platform evolves.*
