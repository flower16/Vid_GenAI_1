"""
Sample-calculation tests for every supported ORC.

Each test encodes a worked FDIC example and asserts insured/uninsured. These
double as the documented "Sample calculations" for each ORC.
"""

from decimal import Decimal

import pytest

from app.domain.constants import ORC
from app.domain.models import Account, Beneficiary, Owner, Participant
from app.domain.orc.engine import calculate

D = Decimal


def acct(orc, bal, interest="0", **kw):
    return Account(account_number=kw.pop("num", "A1"), customer_id=kw.pop("cust", "C1"),
                   orc=orc, balance=D(bal), accrued_interest=D(interest), **kw)


def test_sgl_single_owner_over_limit():
    # $350,000 single account → insured $250k, uninsured $100k
    r = calculate(ORC.SGL, [acct(ORC.SGL, "350000")])
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("100000.00")
    assert r.insured_amount + r.uninsured_amount == r.aggregated_pi


def test_sgl_aggregates_multiple_accounts():
    accts = [acct(ORC.SGL, "200000", num="A1"), acct(ORC.SGL, "150000", num="A2")]
    r = calculate(ORC.SGL, accts)
    assert r.aggregated_pi == D("350000.00")
    assert r.insured_amount == D("250000.00")


def test_jnt_two_owners_fully_insured():
    # $500,000 joint, 2 owners → 2 × $250k = $500k limit, fully insured
    o1, o2 = Owner(party_id="P1", name="A"), Owner(party_id="P2", name="B")
    r = calculate(ORC.JNT, [acct(ORC.JNT, "500000", owners=[o1, o2])])
    assert r.coverage_limit == D("500000.00")
    assert r.insured_amount == D("500000.00")
    assert r.uninsured_amount == D("0.00")


def test_jnt_per_owner_cap():
    # $700,000 joint, 2 owners → each share $350k capped at $250k → $500k insured
    o1, o2 = Owner(party_id="P1", name="A"), Owner(party_id="P2", name="B")
    r = calculate(ORC.JNT, [acct(ORC.JNT, "700000", owners=[o1, o2])])
    assert r.insured_amount == D("500000.00")
    assert r.uninsured_amount == D("200000.00")


def test_tst_revocable_two_beneficiaries():
    # 1 owner × 2 beneficiaries × $250k = $500k limit
    b = [Beneficiary(party_id="B1", name="X"), Beneficiary(party_id="B2", name="Y")]
    r = calculate(ORC.TST, [acct(ORC.TST, "450000", beneficiaries=b)])
    assert r.coverage_limit == D("500000.00")
    assert r.insured_amount == D("450000.00")


def test_tst_capped_at_five_beneficiaries():
    # 7 beneficiaries → capped at 5 → $1.25M limit
    b = [Beneficiary(party_id=f"B{i}", name=str(i)) for i in range(7)]
    r = calculate(ORC.TST, [acct(ORC.TST, "2000000", beneficiaries=b)])
    assert r.coverage_limit == D("1250000.00")
    assert r.insured_amount == D("1250000.00")
    assert r.uninsured_amount == D("750000.00")


def test_cra_single_owner():
    r = calculate(ORC.CRA, [acct(ORC.CRA, "300000")])
    assert r.insured_amount == D("250000.00")


def test_ebp_passthrough_participants():
    p = [Participant(party_id="P1", name="A", vested_interest=D("200000")),
         Participant(party_id="P2", name="B", vested_interest=D("300000"))]
    r = calculate(ORC.EBP, [acct(ORC.EBP, "500000", participants=p)])
    # P1 fully insured (200k), P2 capped at 250k → 450k insured
    assert r.insured_amount == D("450000.00")
    assert r.uninsured_amount == D("50000.00")


def test_bus_single_entity():
    # Default: independent activity assumed → one SMDIA for the entity.
    r = calculate(ORC.BUS, [acct(ORC.BUS, "400000")])
    assert r.coverage_limit == D("250000.00")
    assert r.insured_amount == D("250000.00")
    assert r.evidence["treatment"] == "per_entity_independent"
    assert r.evidence["independent_activity"] == "assumed"


def test_bus_independent_confirmed_separate_from_owners():
    # Engaged in independent activity (confirmed) → $250k, separate depositor.
    r = calculate(ORC.BUS, [acct(ORC.BUS, "400000", independent_activity=True)])
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("150000.00")
    assert r.evidence["independent_activity"] is True


def test_bus_non_independent_passes_through_to_members():
    # NOT independent → allocate equally among members, each capped at SMDIA.
    # $400k / 2 members = $200k each, both fully insured → $400k insured.
    o1, o2 = Owner(party_id="M1", name="Alice"), Owner(party_id="M2", name="Bob")
    r = calculate(ORC.BUS, [acct(ORC.BUS, "400000", independent_activity=False,
                                 owners=[o1, o2])])
    assert r.coverage_limit == D("500000.00")
    assert r.insured_amount == D("400000.00")
    assert r.uninsured_amount == D("0.00")
    assert r.evidence["treatment"] == "pass_through_members"
    # owner_shares drives the per-owner allocation table in the UI
    assert set(r.evidence["owner_shares"]) == {"M1", "M2"}
    assert r.evidence["owner_shares"]["M1"] == "200000.00"


def test_bus_non_independent_member_share_capped():
    # 1 member with $400k → capped at SMDIA → $250k insured, $150k uninsured.
    o1 = Owner(party_id="M1", name="Solo")
    r = calculate(ORC.BUS, [acct(ORC.BUS, "400000", independent_activity=False,
                                 owners=[o1])])
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("150000.00")


def test_gov1_in_state_time_savings_single_smdia():
    # GOV1 (in-state, time & savings): one SMDIA per custodian — NO 2x multiplier.
    # The demand-deposit portion would be a separate GOV2 group/coverage.
    r = calculate(ORC.GOV1, [acct(ORC.GOV1, "450000")])
    assert r.coverage_limit == D("250000.00")
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("200000.00")


def test_gov1_and_gov2_are_separate_coverages():
    # Same custodian, time/savings (GOV1) + demand (GOV2) each get their own SMDIA.
    g1 = calculate(ORC.GOV1, [acct(ORC.GOV1, "250000", cust="PU1")])
    g2 = calculate(ORC.GOV2, [acct(ORC.GOV2, "250000", cust="PU1")])
    assert g1.insured_amount == D("250000.00")
    assert g2.insured_amount == D("250000.00")
    assert g1.insured_amount + g2.insured_amount == D("500000.00")


def test_gov2_in_state_demand_single():
    r = calculate(ORC.GOV2, [acct(ORC.GOV2, "400000")])
    assert r.coverage_limit == D("250000.00")
    assert r.insured_amount == D("250000.00")


def test_gov3_out_of_state_single():
    r = calculate(ORC.GOV3, [acct(ORC.GOV3, "300000")])
    assert r.coverage_limit == D("250000.00")
    assert r.insured_amount == D("250000.00")


def test_msa_passthrough_mortgagors():
    p = [Participant(party_id="M1", name="A", vested_interest=D("250000")),
         Participant(party_id="M2", name="B", vested_interest=D("100000"))]
    r = calculate(ORC.MSA, [acct(ORC.MSA, "350000", participants=p)])
    assert r.insured_amount == D("350000.00")


def test_pba_per_bondholder():
    # PBA is pass-through per bondholder; two bondholders → 2 × SMDIA.
    p = [Participant(party_id="BH1", name="A", vested_interest=D("250000")),
         Participant(party_id="BH2", name="B", vested_interest=D("100000"))]
    r = calculate(ORC.PBA, [acct(ORC.PBA, "350000", participants=p)])
    assert r.insured_amount == D("350000.00")
    assert r.uninsured_amount == D("0.00")


def test_dit_per_trust_beneficiary():
    # DIT (IDI as trustee of irrevocable trust): per trust fund owner/beneficiary.
    # Coverage is driven by the beneficiaries list (equal split, no amount given).
    b = [Beneficiary(party_id="BEN1", name="A")]
    r = calculate(ORC.DIT, [acct(ORC.DIT, "260000", beneficiaries=b)])
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("10000.00")


def test_anc_annuitants():
    # ANC: pass-through to each annuitant (beneficiaries list).
    b = [Beneficiary(party_id="A1", name="A")]
    r = calculate(ORC.ANC, [acct(ORC.ANC, "260000", beneficiaries=b)])
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("10000.00")


def test_bia_native_americans():
    # BIA: per Native American (beneficiaries list).
    b = [Beneficiary(party_id="X1", name="A")]
    r = calculate(ORC.BIA, [acct(ORC.BIA, "150000", beneficiaries=b)])
    assert r.insured_amount == D("150000.00")


def test_doe_idi_program_per_entity():
    # DOE = accounts of an IDI under the DOE Bank Deposit Financial Assistance
    # Program; each IDI insured to one SMDIA for combined DOE deposits.
    r = calculate(ORC.DOE, [acct(ORC.DOE, "275000")])
    assert r.coverage_limit == D("250000.00")
    assert r.insured_amount == D("250000.00")
    assert r.uninsured_amount == D("25000.00")


def test_accrued_interest_included_in_pi():
    r = calculate(ORC.SGL, [acct(ORC.SGL, "249000", interest="2000")])
    assert r.aggregated_pi == D("251000.00")
    assert r.insured_amount == D("250000.00")


@pytest.mark.parametrize("orc", list(ORC))
def test_every_orc_reconciles(orc):
    """Invariant: insured + uninsured == aggregated PI for every ORC."""
    extra = {}
    if orc == ORC.JNT:
        extra["owners"] = [Owner(party_id="P1", name="A"), Owner(party_id="P2", name="B")]
    if orc in (ORC.TST, ORC.ANC, ORC.DIT, ORC.BIA):
        extra["beneficiaries"] = [Beneficiary(party_id="B1", name="X")]
    if orc in (ORC.EBP, ORC.MSA, ORC.PBA):
        extra["participants"] = [Participant(party_id="P1", name="A", vested_interest=D("100000"))]
    r = calculate(orc, [acct(orc, "300000", **extra)])
    assert r.insured_amount + r.uninsured_amount == r.aggregated_pi
