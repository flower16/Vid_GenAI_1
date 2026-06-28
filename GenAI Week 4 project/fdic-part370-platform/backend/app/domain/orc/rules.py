"""
Structured FDIC Part 370 rule knowledge per ORC.

Used by (a) the RAG retriever to seed the Pinecone index and (b) the FDIC Rules
Agent as a deterministic fallback when vector retrieval is unavailable. Each
entry is a compact, citable summary — replace `citation` values with exact
guide references once the official FDIC IT Functional Guide is supplied.
"""

from __future__ import annotations

from ..constants import ORC

ORC_RULES: dict[ORC, dict] = {
    ORC.SGL: {
        "name": "Single Ownership",
        "summary": "Deposits owned by one natural person, not held jointly, in trust, "
                   "or as a business. All single accounts of the same owner at the same "
                   "IDI aggregate and are insured to $250,000.",
        "aggregation": "Sum PI across all SGL accounts for the owner.",
        "smdia": "$250,000 per owner.",
        "validation": ["Owner SSN/TIN present", "Single natural-person owner",
                        "No POD/beneficiary designation (else TST)"],
        "edge_cases": ["Sole proprietorship treated as single ownership of the owner.",
                       "Decedent accounts move to DOE after grace period."],
        "pending": ["A — missing owner SSN/TIN", "ARO — ownership detail pending"],
        "citation": "12 CFR 330.6 / Part 370 App.",
    },
    ORC.JNT: {
        "name": "Joint Ownership",
        "summary": "Accounts owned by two or more natural persons with equal withdrawal "
                   "rights. Each co-owner's combined interest in all joint accounts at "
                   "the IDI is insured to $250,000.",
        "aggregation": "Each owner's pro-rata share summed across all JNT accounts, capped at SMDIA.",
        "smdia": "$250,000 per co-owner.",
        "validation": ["≥2 natural-person owners", "Equal withdrawal rights",
                       "Each owner has signature/SSN"],
        "edge_cases": ["Unequal ownership defaults to equal shares.",
                       "Same combination of owners cannot multiply coverage."],
        "pending": ["ARO — ownership detail pending", "A — missing co-owner SSN"],
        "citation": "12 CFR 330.9 / Part 370 App.",
    },
    ORC.TST: {
        "name": "Revocable Trust / POD",
        "summary": "Revocable trust, POD, or informal trust accounts. Under the 2024 "
                   "simplified rule, insured to $250,000 per beneficiary, up to 5 "
                   "beneficiaries ($1.25M max per owner).",
        "aggregation": "owners × min(beneficiaries,5) × SMDIA.",
        "smdia": "$250,000 per owner per beneficiary (≤5).",
        "validation": ["Valid beneficiary list", "Beneficiary relationship eligible",
                       "Trust revocable / POD designation present"],
        "edge_cases": [">5 beneficiaries still capped at 5 under 2024 rule.",
                       "Irrevocable trust may route to DIT/fiduciary handling."],
        "pending": ["ARTR — trust beneficiary detail pending", "ARBN — beneficiary data pending"],
        "citation": "12 CFR 330.10 (2024 amendment) / Part 370 App.",
    },
    ORC.CRA: {
        "name": "Certain Retirement Accounts",
        "summary": "IRAs and certain self-directed retirement accounts. All CRA deposits "
                   "of the same owner aggregate and are insured to $250,000.",
        "aggregation": "Sum PI across all CRA accounts per owner.",
        "smdia": "$250,000 per owner (separate from SGL).",
        "validation": ["Account is a qualifying retirement vehicle", "Owner SSN present"],
        "edge_cases": ["Self-directed plan deposits qualify; non-self-directed may be EBP."],
        "pending": ["ARCRA — CRA detail pending"],
        "citation": "12 CFR 330.14 / Part 370 App.",
    },
    ORC.EBP: {
        "name": "Employee Benefit Plan",
        "summary": "Plan deposits insured on a pass-through basis to each participant's "
                   "non-contingent vested interest, up to $250,000 each.",
        "aggregation": "Per participant vested interest, capped at SMDIA.",
        "smdia": "$250,000 per participant.",
        "validation": ["Participant roster + vested interests present", "Plan TIN present"],
        "edge_cases": ["Contingent interests not separately insured.",
                       "Defined-benefit plans use different allocation."],
        "pending": ["AREBP — EBP participant detail pending"],
        "citation": "12 CFR 330.14 / Part 370 App.",
    },
    ORC.BUS: {
        "name": "Business / Corporation / Partnership / Unincorporated",
        "summary": "Deposits of a corporation, partnership, or unincorporated association "
                   "engaged in an independent activity, insured to $250,000 as a separate "
                   "depositor.",
        "aggregation": "Sum PI across all BUS accounts of the entity.",
        "smdia": "$250,000 per legal entity engaged in independent activity.",
        "validation": ["Entity TIN present", "Independent business activity",
                       "Not a sole prop (→ SGL)"],
        "branches": [
            "Independent activity → one SMDIA for the entity, separate from owners (§330.11(a)).",
            "Sole proprietorship → owner's single-ownership (SGL) funds (§330.11).",
            "Not independent activity → split equally among members, each insured "
            "to SMDIA as single-ownership funds (§330.11(c)).",
        ],
        "edge_cases": ["Multiple entities with same owner each get separate coverage.",
                       "Sole proprietorship aggregates with the owner's other SGL deposits."],
        "pending": ["A — missing entity TIN"],
        "citation": "12 CFR 330.11 / Part 370 App.",
    },
    ORC.GOV1: {
        "name": "Public Unit — In-State, Time & Savings",
        "summary": "Time and savings deposits (NOW, Savings, CD, MMDA) of an official "
                   "custodian of a public unit held at an IDI located in the same state "
                   "as the public unit. Insured to $250,000 per custodian/public unit.",
        "aggregation": "Per unique (official custodian, public unit) under GOV1.",
        "smdia": "$250,000 per official custodian/public unit (GOV1).",
        "validation": ["Official custodian (plenary authority) confirmed",
                       "Same-state location", "Product is time/savings (not demand)"],
        "edge_cases": ["Demand deposits of the same custodian are GOV2 (separate SMDIA).",
                       "One official custodian for two public units → two coverages."],
        "pending": ["A — agency/custodian; RAC — custodian status unverified"],
        "citation": "12 CFR 330.15 / Guide §4.1.9",
    },
    ORC.GOV2: {
        "name": "Public Unit — In-State, Demand Deposits",
        "summary": "Demand deposit accounts of an official custodian of a public unit "
                   "held at an IDI located in the same state. Insured to $250,000 per "
                   "custodian/public unit, separately from the custodian's GOV1 deposits.",
        "aggregation": "Per unique (official custodian, public unit) under GOV2.",
        "smdia": "$250,000 per official custodian/public unit (GOV2).",
        "validation": ["Official custodian confirmed", "Same-state location",
                       "Product is a demand deposit"],
        "edge_cases": ["Time/savings of the same custodian are GOV1 (separate SMDIA)."],
        "pending": ["A — agency/custodian", "RAC — custodian status unverified"],
        "citation": "12 CFR 330.15 / Guide §4.1.9",
    },
    ORC.GOV3: {
        "name": "Public Unit — Out-of-State",
        "summary": "Deposits of an official custodian held at an IDI located OUTSIDE the "
                   "state in which the public unit is located. All such deposits of the "
                   "custodian aggregate to a single $250,000 (no demand/time split).",
        "aggregation": "Per unique (official custodian, public unit) under GOV3.",
        "smdia": "$250,000 per official custodian/public unit (GOV3).",
        "validation": ["Official custodian confirmed", "Out-of-state location confirmed"],
        "edge_cases": ["Demand vs time/savings split does NOT apply out of state."],
        "pending": ["A — agency/custodian"], "citation": "12 CFR 330.15 / Guide §4.1.9",
    },
    ORC.MSA: {
        "name": "Mortgage Servicing Account",
        "summary": "Principal & interest payments collected by a servicer are insured on "
                   "a pass-through basis to each mortgagor up to $250,000; servicer escrow "
                   "(tax/insurance) covered separately.",
        "aggregation": "Per mortgagor P&I, capped at SMDIA.",
        "smdia": "$250,000 per mortgagor (P&I).",
        "validation": ["Mortgagor roster present", "Servicer fiduciary capacity"],
        "edge_cases": ["Cushion/escrow funds use a different category."],
        "pending": ["ARM — MSA mortgagor detail pending"],
        "citation": "12 CFR 330.7 / Part 370 App.",
    },
    ORC.PBA: {
        "name": "Public Bond Account",
        "summary": "Deposits held for a public-bond issuance. Each unique (bondholder, "
                   "bond issuer) beneficial interest is insured to $250,000 on a "
                   "pass-through basis.",
        "aggregation": "Per unique (bondholder, bond issuer).",
        "smdia": "$250,000 per bondholder/bond issuer.",
        "validation": ["Bondholders + beneficial interests identified"],
        "edge_cases": ["Pending if bondholder interests incomplete."],
        "pending": ["ARO — bondholder detail pending"], "citation": "Guide §4.1.13",
    },
    ORC.DIT: {
        "name": "Accounts Held by an IDI as Trustee of an Irrevocable Trust",
        "summary": "Accounts where a depository institution acts as trustee of an "
                   "irrevocable trust. Each trust fund owner or beneficiary is insured to "
                   "$250,000 for combined interests in all accounts under each separate "
                   "trust at the IDI.",
        "aggregation": "Per (trust fund owner/beneficiary, separate trust).",
        "smdia": "$250,000 per trust fund owner/beneficiary, per trust.",
        "validation": ["Trust fund owner/beneficiary identified",
                       "Irrevocable trust + IDI trustee relationship confirmed"],
        "edge_cases": ["Grantor retained interest insured to the grantor."],
        "pending": ["ARO — beneficiary detail pending"], "citation": "Guide §4.1.11",
    },
    ORC.ANC: {
        "name": "Annuity Contract Account",
        "summary": "Deposits of an annuity issuer/insurance company for annuitants. "
                   "Insured to $250,000 per unique (insurance company, annuitant) pair, "
                   "or per annuitant where state law makes the annuitant the owner.",
        "aggregation": "Per (insurance company, annuitant) pair, or per annuitant.",
        "smdia": "$250,000 per annuitant relationship.",
        "validation": ["Annuitants identified", "Account insulated from issuer's "
                       "other-business liabilities and creditors (§4.1.12)"],
        "edge_cases": ["State-law ownership determines aggregation across issuers."],
        "pending": ["ARO — annuitant detail pending"], "citation": "Guide §4.1.12",
    },
    ORC.BIA: {
        "name": "Custodian Accounts for American Indians",
        "summary": "Deposits held by the Bureau of Indian Affairs (or other disbursing "
                   "agent under 25 U.S.C. 162a) for Native Americans. Insured to $250,000 "
                   "for each Native American for whom the BIA acts.",
        "aggregation": "Per Native American beneficial owner (BIA accounts only; no "
                       "aggregation with the owner's SGL/JNT/other ORCs).",
        "smdia": "$250,000 per Native American beneficial owner.",
        "validation": ["Funds held by disbursing agent in agency capacity",
                       "Native American has an ascertainable interest"],
        "edge_cases": ["Personal (non-BIA) deposits revert to SGL/JNT.",
                       "Tribal official-custodian funds use GOV (§4.1.9)."],
        "pending": ["A — agency/custodian detail pending"], "citation": "Guide §4.1.14",
    },
    ORC.DOE: {
        "name": "Accounts of an IDI under the DOE Program",
        "summary": "Deposits of an insured depository institution placed pursuant to the "
                   "Bank Deposit Financial Assistance Program of the U.S. Department of "
                   "Energy. Each IDI is insured to $250,000 for combined DOE-program "
                   "deposits at the CI.",
        "aggregation": "Per IDI (DOE-program deposits).",
        "smdia": "$250,000 per IDI.",
        "validation": ["IDI + DOE program participation confirmed"],
        "edge_cases": ["Non-DOE IDI deposits are treated as Business (BUS)."],
        "pending": ["A — program documentation pending"], "citation": "Guide §4.1.15",
    },
}


def rule_text(orc: ORC) -> str:
    """Flatten a rule entry into RAG-friendly text."""
    r = ORC_RULES[orc]
    return (
        f"ORC {orc.value} — {r['name']}\n"
        f"Summary: {r['summary']}\n"
        f"Aggregation: {r['aggregation']}\n"
        f"Coverage/SMDIA: {r['smdia']}\n"
        f"Validation: {'; '.join(r['validation'])}\n"
        f"Edge cases: {'; '.join(r['edge_cases']) or 'none'}\n"
        f"Pending: {'; '.join(r['pending'])}\n"
        f"Citation: {r['citation']}"
    )
