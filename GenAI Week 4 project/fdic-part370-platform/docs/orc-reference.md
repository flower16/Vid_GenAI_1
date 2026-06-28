# ORC Reference — FDIC Part 370 Coverage Categories

> Reconciled to the **FDIC IT Functional Guide for Part 370, Version 3.0 (June
> 2023)** — §4.1 (coverage), §5 + Appendix A (output files), §6.2 + Appendix B
> (Summary Report). Coverage math lives in
> `backend/app/domain/orc/engine.py`; rule text in `.../orc/rules.py`.

SMDIA = **$250,000** per depositor, per insured bank, per ownership right and
capacity (ORC). All deposits in one ORC are aggregated and insured to SMDIA.

| ORC | Category (per Guide App. A) | Coverage Shape | Per-unit limit |
|-----|------------------------------|----------------|----------------|
| SGL | Single accounts | per owner | owners × SMDIA |
| JNT | Joint accounts | per owner (capped) | co-owners × SMDIA |
| TST | Trust accounts (§330.10, eff. 2024-04-01) | per owner × beneficiary | owners × min(benes,5) × SMDIA → $1.25M/grantor |
| CRA | Certain retirement accounts | per owner | SMDIA per owner |
| EBP | Employee benefit plan accounts | per participant | SMDIA per participant (non-contingent) |
| BUS | Business / organization (§330.11) | per entity (branches ↓) | SMDIA |
| GOV1| Public unit — in-state, **time & savings** | per custodian/public unit | SMDIA |
| GOV2| Public unit — in-state, **demand** | per custodian/public unit | SMDIA |
| GOV3| Public unit — **out-of-state** | per custodian/public unit | SMDIA |
| MSA | Mortgage servicing (P&I) | per mortgagor | SMDIA per mortgagor |
| PBA | Public bond accounts | per bondholder/issuer | SMDIA |
| DIT | IDI as trustee of an **irrevocable trust** | per trust fund owner/beneficiary | SMDIA per beneficiary/trust |
| ANC | Annuity contract accounts | per annuitant | SMDIA per (insurer, annuitant) |
| BIA | Custodian accounts for **American Indians** (BIA) | per Native American | SMDIA |
| DOE | Accounts of an IDI under the **DOE** program | per IDI | SMDIA |

### Corrections applied after reconciling to the official guide
- **GOV1/GOV2/GOV3 redefined.** GOV1 = in-state *time & savings*, GOV2 = in-state
  *demand*, GOV3 = *out-of-state* (the earlier build had GOV1=in-state,
  GOV2=out-of-state, GOV3=federal). Each code gives **one** SMDIA per
  (custodian, public unit) — the prior erroneous 2× multiplier on GOV1 was removed
  (§4.1.9).
- **DIT** = accounts held by an IDI as **trustee of an irrevocable trust**, per
  trust fund owner/beneficiary (§4.1.11) — not "deposit of an IDI."
- **BIA** = **Custodian Accounts for American Indians** (Bureau of Indian
  Affairs), per Native American (§4.1.14) — not "bank investment/broker."
- **DOE** = accounts of an IDI under the **Department of Energy** Bank Deposit
  Financial Assistance Program, per IDI (§4.1.15) — not "decedent's estate."
- **Pending reason codes** relabeled to the guide meanings (A=agency/custodian,
  B=beneficiary, OI=official item, RAC=right-and-capacity).

### BUS eligibility branches (§330.11)

A BUS account resolves to one of three treatments (engine: `_business` in
`engine.py`; sole-prop reclassification in `agents/nodes/rules_and_classify.py`).
Driven by two `Account` fields: `independent_activity` and `sole_proprietorship`.

| Branch | Condition | Treatment | Citation |
|--------|-----------|-----------|----------|
| Independent activity | default (unset → assumed, flagged `BUS_ACTIVITY_UNCONFIRMED`) or `independent_activity=True` | One SMDIA for the entity, separate from owners | §330.11(a) |
| Not independent | `independent_activity=False` | Funds split **equally among members**; each member insured to SMDIA (pass-through) | §330.11(c) |
| Sole proprietorship | `sole_proprietorship=True` | Reclassified to **SGL** — owner's single-ownership funds, aggregated with their other SGL deposits | §330.11 |

## Worked sample calculations

Mirror the assertions in `tests/test_orc_calculations.py`.

| ORC | Scenario | PI | Limit | Insured | Uninsured |
|-----|----------|----|-------|---------|-----------|
| SGL | 1 owner | $350,000 | $250,000 | $250,000 | $100,000 |
| JNT | 2 owners, even | $500,000 | $500,000 | $500,000 | $0 |
| JNT | 2 owners, per-owner cap | $700,000 | $500,000 | $500,000 | $200,000 |
| TST | 1 grantor, 2 benes | $450,000 | $500,000 | $450,000 | $0 |
| TST | 1 grantor, 7 benes (cap 5) | $2,000,000 | $1,250,000 | $1,250,000 | $750,000 |
| EBP | 2 participants 200k/300k | $500,000 | $500,000 | $450,000 | $50,000 |
| BUS | independent entity | $400,000 | $250,000 | $250,000 | $150,000 |
| BUS | not independent, 2 members | $400,000 | $500,000 | $400,000 | $0 |
| GOV1| in-state time/savings, 1 custodian | $450,000 | $250,000 | $250,000 | $200,000 |
| GOV1+GOV2 | same custodian, $250k each | $500,000 | $500,000 | $500,000 | $0 |
| PBA | 2 bondholders 250k/100k | $350,000 | $500,000 | $350,000 | $0 |
| DIT | 1 beneficiary | $260,000 | $250,000 | $250,000 | $10,000 |
| DOE | 1 IDI | $275,000 | $250,000 | $250,000 | $25,000 |

## Pending reason codes (Pending File field #2 / Summary Report Table 2)

**I. Records maintained by the bank**

| Code | Meaning |
|------|---------|
| A | Agency or custodian |
| B | Beneficiary |
| OI | Official item |
| RAC | Right and capacity (e.g. joint account without signature card) |

**II. Alternative recordkeeping (§370.4(b))**

| Code | Meaning |
|------|---------|
| ARB | Direct-obligation (depository org.) brokered deposits |
| ARBN | Non-direct-obligation (non-depository org.) brokered deposits |
| ARCRA | Certain retirement accounts |
| AREBP | Employee benefit plan accounts |
| ARM | Mortgage servicing for principal & interest |
| ARO | Other deposits |
| ARTR | Trust accounts |

## Output files (Appendix A) — key facts encoded

- Four pipe-delimited files: **Customer, Account, Account Participant, Pending**,
  linked by `CS_Unique_ID` (+ `DP_Acct_Identifier`, `DP_Right_Capacity`).
- An **Account Participant File is NOT produced** for SGL, JNT, CRA, BUS, BIA,
  DOE (§5.3); it is produced for TST, EBP, ANC, DIT, GOV*, MSA, PBA.
- Participant types: `OC` (official custodian), `BEN` (beneficiary), `BHR`
  (bondholder), `MOR` (mortgagor), `EPP` (EBP participant).
- A pending account does not also appear on the Account File, except pass-through
  accounts; iterative recalculation moves balances from Pending → Account as
  alternative-recordkeeping data arrives (§3.3, Appendix E).

## Worked end-to-end example (multi-account, multi-ORC)

One depositor, three accounts spanning two ownership categories. This is a live
run of `POST /api/v1/determinations`.

**Request**

| Account | ORC | Product | Balance | Owners |
|---------|-----|---------|--------:|--------|
| ACCT-1 | SGL | DDA | $200,000 | Jane Doe (customer) |
| ACCT-2 | SGL | SAV | $100,000 | Jane Doe (customer) |
| JNT-1 | JNT | MMA | $400,000 | Jane Doe, John Doe |

**Step 1 — ORC classification / aggregation groups**
- `SGL:C1001` → {ACCT-1, ACCT-2}
- `JNT:C1001` → {JNT-1}

**Step 2 — coverage per group**

| ORC | Accounts | Aggregated P&I | Coverage Limit | Insured | Uninsured |
|-----|----------|---------------:|---------------:|--------:|----------:|
| SGL | ACCT-1, ACCT-2 | $300,000 | $250,000 (1 owner × SMDIA) | $250,000 | $50,000 |
| JNT | JNT-1 | $400,000 | $500,000 (2 owners × SMDIA) | $400,000 | $0 |

The two SGL accounts aggregate to one SMDIA → $50K uninsured. The joint account's
two co-owners give a $500K limit, so all $400K is insured.

**Step 3 — Account File (Appendix A layout)**
```
C1001|ACCT-1|SGL|DDA|200000|0|200000|0|||N|N|N
C1001|ACCT-2|SGL|SAV|100000|0|100000|0|||N|N|N
C1001|JNT-1|JNT|MMA|400000|0|400000|0|||N|N|N
```

**Step 4 — Summary Report (Table 1 totals) + reconciliation**

| Total accounts | Total P&I | Total insured | Total uninsured | Pending |
|---------------:|----------:|--------------:|----------------:|--------:|
| 3 | $700,000 | $650,000 | $50,000 | 0 |

`reconciles: true` — insured + uninsured ($650K + $50K) = total P&I ($700K).

**Step 5 — Evals** — `input_completeness`, `deposit_balance_reconciliation`,
`coverage_limit_respected`, `summary_report_reconciliation` → all **PASS**.

See [evals.md](evals.md) for how the eval framework works.
