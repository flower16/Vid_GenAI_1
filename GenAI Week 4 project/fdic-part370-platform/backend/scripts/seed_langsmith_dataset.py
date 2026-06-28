"""
Seed a LangSmith dataset with one labeled example per ORC, then (optionally) run
the eval experiment — so a full ORC regression is one command.

Usage (from backend/):
    python scripts/seed_langsmith_dataset.py            # local mode if no LS key
    python scripts/seed_langsmith_dataset.py --local    # force in-process eval
    python scripts/seed_langsmith_dataset.py --upload    # create/replace LS dataset
    python scripts/seed_langsmith_dataset.py --run       # upload + run experiment

Requires LANGSMITH_API_KEY in the environment/.env for --upload / --run.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from decimal import Decimal as D

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.domain.constants import ORC, CustomerType  # noqa: E402
from app.domain.models import (  # noqa: E402
    Account, Beneficiary, Customer, DeterminationRequest, Owner, Participant,
)

DATASET_NAME = "fdic-part370-orc-suite"
SMDIA = 250000


def _cust() -> Customer:
    return Customer(customer_id="C1", first_name="Test", last_name="Depositor",
                    ssn_tin="123-45-6789", customer_type=CustomerType.INDIVIDUAL)


def _acct(orc: ORC, balance: str, **kw) -> Account:
    return Account(account_number="A1", customer_id="C1", orc=orc,
                   product_type=kw.pop("product_type", "SAV"), balance=D(balance), **kw)


def _owner(i: int, name: str) -> Owner:
    return Owner(party_id=f"O{i}", name=name)


def _bene(i: int, name: str) -> Beneficiary:
    return Beneficiary(party_id=f"B{i}", name=name)


def _part(i: int, name: str, amt: str) -> Participant:
    return Participant(party_id=f"P{i}", name=name, vested_interest=D(amt))


def _example(name: str, orc: ORC, account: Account, expected_insured: int,
             **labels) -> dict:
    req = DeterminationRequest(customer=_cust(), accounts=[account])
    return {
        "name": name,
        "inputs": req.model_dump(mode="json"),
        "expected_insured": expected_insured,
        "expect_input_fail": False,
        "expect_ssn_issue": False,
        **labels,
    }


def build_examples() -> list[dict]:
    """One labeled example per ORC (plus a 2nd BUS branch), each with a known
    expected insured amount."""
    return [
        _example("SGL_over_limit", ORC.SGL,
                 _acct(ORC.SGL, "350000", product_type="DDA"), SMDIA),
        _example("JNT_two_owners", ORC.JNT,
                 _acct(ORC.JNT, "500000",
                       owners=[_owner(1, "Alice"), _owner(2, "Bob")]), 500000),
        _example("TST_grantor_two_benes", ORC.TST,
                 _acct(ORC.TST, "450000",
                       owners=[_owner(1, "Grantor One")],
                       beneficiaries=[_bene(1, "Bene A"), _bene(2, "Bene B")]), 450000),
        _example("CRA_retiree", ORC.CRA,
                 _acct(ORC.CRA, "300000", product_type="CDS",
                       owners=[_owner(1, "Jane Retiree")]), SMDIA),
        _example("EBP_two_participants", ORC.EBP,
                 _acct(ORC.EBP, "500000",
                       participants=[_part(1, "Alice", "200000"),
                                     _part(2, "Bob", "300000")]), 450000),
        _example("BUS_entity", ORC.BUS,
                 _acct(ORC.BUS, "400000", product_type="DDA"), SMDIA,
                 expected_bus_treatment="per_entity_independent"),
        _example("BUS_non_independent_members", ORC.BUS,
                 _acct(ORC.BUS, "400000", product_type="DDA",
                       independent_activity=False,
                       owners=[_owner(1, "Partner Alice"), _owner(2, "Partner Bob")]),
                 400000, expected_bus_treatment="pass_through_members"),
        _example("GOV1_custodian", ORC.GOV1,
                 _acct(ORC.GOV1, "400000",
                       owners=[_owner(1, "City Treasurer")],
                       beneficiaries=[_bene(1, "City of Springfield")]), SMDIA),
        _example("GOV2_custodian", ORC.GOV2,
                 _acct(ORC.GOV2, "300000", product_type="DDA",
                       owners=[_owner(1, "County Clerk")]), SMDIA),
        _example("GOV3_out_of_state", ORC.GOV3,
                 _acct(ORC.GOV3, "300000",
                       owners=[_owner(1, "State Agency")]), SMDIA),
        _example("MSA_two_mortgagors", ORC.MSA,
                 _acct(ORC.MSA, "350000", product_type="DDA",
                       owners=[_owner(1, "BigBank Servicing")],
                       participants=[_part(1, "Alice", "250000"),
                                     _part(2, "Bob", "100000")]), 350000),
        _example("PBA_two_bondholders", ORC.PBA,
                 _acct(ORC.PBA, "350000",
                       participants=[_part(1, "Holder A", "250000"),
                                     _part(2, "Holder B", "100000")]), 350000),
        _example("DIT_one_beneficiary", ORC.DIT,
                 _acct(ORC.DIT, "260000",
                       beneficiaries=[_bene(1, "Trust Bene")]), SMDIA),
        _example("ANC_two_annuitants", ORC.ANC,
                 _acct(ORC.ANC, "600000", product_type="MMA",
                       owners=[_owner(1, "Acme Life")],
                       beneficiaries=[_bene(1, "Annuitant One"),
                                      _bene(2, "Annuitant Two")]), 500000),
        _example("BIA_native_american", ORC.BIA,
                 _acct(ORC.BIA, "150000",
                       beneficiaries=[_bene(1, "Beneficiary One")]), 150000),
        _example("DOE_idi_program", ORC.DOE,
                 _acct(ORC.DOE, "275000"), SMDIA),
    ]


def run_local(examples: list[dict]) -> int:
    from app.evals.langsmith_evals import evaluate_local
    report = evaluate_local(examples)
    print(f"\nLocal eval: {report['passed']}/{report['total']} examples passed\n")
    for row in report["rows"]:
        flag = "PASS" if row["passed"] else "FAIL"
        print(f"  [{flag}] {row['example']}")
        if not row["passed"]:
            for s in row["scores"]:
                if not s["score"]:
                    print(f"        ✗ {s['key']}: {s.get('comment', '')}")
    return 0 if report["passed"] == report["total"] else 1


def upload(examples: list[dict]):  # pragma: no cover - external
    from langsmith import Client
    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        client.delete_dataset(dataset_name=DATASET_NAME)
    ds = client.create_dataset(DATASET_NAME,
                               description="FDIC Part 370 — one labeled example per ORC")
    client.create_examples(
        inputs=[ex["inputs"] for ex in examples],
        metadata=[{k: ex.get(k) for k in
                   ("name", "expected_insured", "expect_input_fail", "expect_ssn_issue",
                    "expected_bus_treatment")}
                  for ex in examples],
        dataset_id=ds.id,
    )
    print(f"Uploaded {len(examples)} examples to LangSmith dataset '{DATASET_NAME}'.")
    return ds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="run in-process eval only")
    parser.add_argument("--upload", action="store_true", help="create/replace LangSmith dataset")
    parser.add_argument("--run", action="store_true", help="upload + run the experiment")
    args = parser.parse_args()

    examples = build_examples()
    print(f"Built {len(examples)} labeled examples (one per ORC + a 2nd BUS branch).")

    has_ls = bool(settings.langsmith_api_key)
    if args.local or not (args.upload or args.run) and not has_ls:
        return run_local(examples)

    if args.upload or args.run:
        if not has_ls:
            print("LANGSMITH_API_KEY not set — running local eval instead.")
            return run_local(examples)
        upload(examples)  # pragma: no cover
        if args.run:  # pragma: no cover
            from app.evals.langsmith_evals import evaluate_langsmith
            print("Running LangSmith experiment 'fdic-part370'...")
            evaluate_langsmith(DATASET_NAME)
            print("Experiment complete — see results in the LangSmith UI.")
        return 0

    # default when a key IS present: upload + run
    upload(examples)  # pragma: no cover
    from app.evals.langsmith_evals import evaluate_langsmith  # pragma: no cover
    evaluate_langsmith(DATASET_NAME)  # pragma: no cover
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
