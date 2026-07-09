# FDIC Part 370 — Agentic AI Insurance Determination Platform

A production-shaped, multi-agent platform that calculates FDIC deposit insurance
coverage under **12 CFR Part 370** for all Ownership Right & Capacity (ORC)
categories, validates FDIC-required data elements, generates the four required
deposit files + the 3-table Summary Report, and produces a full audit/evidence
trail with iterative recalculation support.

> ✅ **Source of truth.** Reconciled to the **FDIC IT Functional Guide for Part
> 370, Version 3.0 (June 2023)**. Regulatory rules are config-driven
> (`domain/constants.py`, `domain/orc/rules.py`). Post-reconciliation corrections
> (see [docs/orc-reference.md](docs/orc-reference.md)): GOV1/2/3 redefined as
> in-state-time/savings / in-state-demand / out-of-state with one SMDIA each
> (removed an erroneous 2× on GOV1); DIT = IDI-as-trustee-of-irrevocable-trust;
> BIA = custodian accounts for American Indians; DOE = IDI deposits under the DOE
> program; pending codes relabeled (A=agency/custodian, B=beneficiary,
> OI=official item, RAC=right-and-capacity); output files use Appendix A field
> names. Trust math follows the §330.10 rule effective 2024-04-01 ($1.25M/grantor,
> ≤5 beneficiaries). BUS (§330.11) implements all three eligibility branches —
> independent activity (one SMDIA, separate depositor), sole proprietorship
> (reclassified to the owner's SGL), and non-independent (equal pass-through to
> members). Remaining refinements (EBP contingent-interest + overfunding
> sub-coverages, MSA T&I-vs-P&I split, six-month death rule, full Appendix A
> null-field layouts) are noted as extension points.

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | React, TypeScript, Material UI, AG Grid, MSAL (Azure AD) |
| Backend | FastAPI, Python 3.12 |
| AI | LangGraph, LangChain, LangSmith (model: `claude-opus-4-8`) |
| Data | Snowflake, SQLAlchemy, Snowpark |
| Vector store | Pinecone |
| Integration | MCP server, REST |
| Auth | Login screen: Azure AD SSO **or** demo role login + RBAC |
| Evals | LangSmith (deterministic) + Fireworks AI (LLM-as-judge) |
| Learning | Zero-cost RL ORC policy (pure Python) + Fireworks fine-tune export |
| Deploy | Replit (single process), Docker, Kubernetes, Azure AKS |
| Observability | LangSmith, OpenTelemetry, `/health/integrations` |

## Supported ORCs

`SGL JNT TST CRA EBP BUS GOV1 GOV2 GOV3 MSA PBA DIT ANC BIA DOE`
— see [docs/orc-reference.md](docs/orc-reference.md) for rules, limits, edge
cases, validation, pending rules, and worked sample calculations.

## The 9 agents (LangGraph)

1. **FDIC Rules** — RAG retrieval of Part 370 rules per ORC
2. **Customer Validation** — demographics, SSN/TIN, type, ownership
3. **Account Validation** — ownership, product, interest, joint/trust rules
4. **ORC Classification** — assignment + aggregation grouping
5. **Insurance Calculation** — aggregated PI, limit, insured/uninsured + evidence
6. **Pending Determination** — pending routing with reason codes (A…ARTR)
7. **Output File** — Customer / Account / Participant / Pending files
8. **Summary Report** — Tables 1, 2, 3
9. **Evals** — completeness, reconciliation, limits, accuracy

Diagrams: [docs/architecture.md](docs/architecture.md). Full session walkthrough
(setup, BUS branching, integrations, troubleshooting): [WALKTHROUGH.md](WALKTHROUGH.md).
Eval framework (LangSmith deterministic + Fireworks LLM-as-judge) + Snowflake↔LangSmith
bridge: [docs/evals.md](docs/evals.md). Fine-tuning vs the zero-cost RL policy:
[docs/fine-tuning-and-rl.md](docs/fine-tuning-and-rl.md).

## Login

The frontend opens on a **login screen** ([frontend/src/components/Login.tsx](frontend/src/components/Login.tsx)):

- **Azure AD SSO** — enabled when `VITE_AZURE_CLIENT_ID` is set (MSAL popup,
  acquires the API bearer token).
- **Demo access** — pick a display name + RBAC role (Analyst / Reviewer / Admin)
  and enter. Works with no Azure tenant (the backend's `local` env grants an
  Admin principal); the session persists in `sessionStorage`. Sign-out clears it.

Auth wiring: [frontend/src/auth/AuthContext.tsx](frontend/src/auth/AuthContext.tsx),
`frontend/.env.example`.

## Quickstart (local, no external services required)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
pytest -q                                               # 48 tests pass (ORC calcs + BUS branches + workflow + evals + RL policy + Fireworks judges)
uvicorn app.main:app --reload                           # http://localhost:8000/docs

# MCP server (separate shell)
python -m app.mcp.server

# Frontend
cd ../frontend
npm install && npm run dev                              # http://localhost:5173
```

In `ENVIRONMENT=local`, Azure AD auth is bypassed (synthetic Admin), RAG uses the
in-code rule corpus, and persistence writes to `audit_log.jsonl`. Wire `.env`
(see `.env.example`) to enable Pinecone, Snowflake, LangSmith, Fireworks, and
Azure AD.

### Integrations & deploy

Check which external services are wired and reachable at any time:

```bash
cd backend
python scripts/check_integrations.py --live   # LangSmith / Fireworks / Snowflake / Azure AD / Pinecone
# or GET /api/v1/health/integrations?live=true  (also shown as the AppBar "Integrations N/5" chip)
```

**One-click Replit hosting** runs the whole stack as a single web process
(`start.sh` builds the UI and FastAPI serves it same-origin). Setup + the health
layer: [docs/integrations.md](docs/integrations.md).

## Folder structure

```
fdic-part370-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app (CORS, OTel, LangSmith)
│   │   ├── api/routes.py           # REST endpoints
│   │   ├── core/                   # config, Azure AD auth + RBAC
│   │   ├── domain/
│   │   │   ├── constants.py        # SMDIA, ORC codes, pending codes (config)
│   │   │   ├── models.py           # Pydantic domain models
│   │   │   └── orc/
│   │   │       ├── engine.py       # ★ pure coverage math (all 15 ORCs)
│   │   │       └── rules.py        # structured Part 370 rule corpus
│   │   ├── agents/
│   │   │   ├── graph.py            # LangGraph workflow assembly
│   │   │   ├── state.py            # shared reducer-annotated state
│   │   │   └── nodes/              # the 9 agents
│   │   ├── rag/retriever.py        # Pinecone RAG + deterministic fallback
│   │   ├── files/generators.py     # FDIC output files (pipe-delimited)
│   │   ├── reports/summary.py      # Summary Report Tables 1-3
│   │   ├── evals/
│   │   │   ├── langsmith_evals.py   # deterministic Input/Output/System evals
│   │   │   └── fireworks_evals.py   # LLM-as-judge evals (free heuristic fallback)
│   │   ├── ml/orc_policy.py         # zero-cost RL ORC classifier (pure Python)
│   │   ├── db/persistence.py       # Snowflake (SQLAlchemy) + local fallback
│   │   └── mcp/server.py           # MCP server (10 tools)
│   ├── scripts/                    # init_snowflake, seed_pinecone, seed_langsmith_dataset,
│   │                               #   seed_snowflake_inputs, sync_evals_to_langsmith,
│   │                               #   run_fireworks_evals, train_orc_policy, export_finetune_dataset
│   ├── tests/                      # per-ORC sample calcs + BUS branches + workflow + evals
│   └── requirements.txt
├── frontend/                       # React + MUI + AG Grid + MSAL
│   └── src/{components,api,types,auth}
├── db/snowflake_ddl.sql            # 7 tables: PK/FK/index/clustering
├── deploy/{docker,k8s}             # Dockerfiles, AKS manifests, HPA, Ingress
├── .github/workflows/ci-cd.yaml    # test → eval gate → ACR build → AKS deploy
├── docs/                           # architecture, ORC reference, API examples, evals
├── WALKTHROUGH.md                  # full setup/run/troubleshooting walkthrough
└── docker-compose.yml
```

## Key design decisions

- **Pure calculation core.** `domain/orc/engine.py` has zero I/O — every ORC maps
  to a `CoverageShape`; the math is fully unit-tested and pins regulatory
  behavior independent of agents/LLM.
- **Config-driven regulation.** Coverage constants, ORC shapes, and rule text are
  centralized for one-place reconciliation to the official guide.
- **Evidence everywhere.** Each `CoverageResult` carries `rationale` + structured
  `evidence`; the Evidence Panel and `CALCULATION_AUDIT` table reproduce it.
- **Iterative recalculation.** `alt_recordkeeping_received` toggles AR* pending
  routing; `/recalculate` reruns the graph and clears pending when data arrives.
- **Graceful degradation.** Pinecone/Snowflake/Azure AD optional in dev.

## Verification status

- ✅ **48 tests pass** (`pytest`): per-ORC sample calcs, the three BUS §330.11
  branches, full workflow, the eval framework, the RL ORC policy (converges to
  100% train/hold-out), and the Fireworks judges (heuristic-fallback path).
- ✅ LangSmith evals: 7 evaluators over a 16-example dataset (one per ORC + a 2nd
  BUS branch); per-determination evals persist to Snowflake and sync to LangSmith
  via `scripts/sync_evals_to_langsmith.py`. See [docs/evals.md](docs/evals.md).
- ⚙️ External integrations (Pinecone/Snowflake/Azure AD/LangSmith) are wired
  behind config and fall back cleanly when unconfigured.
```
