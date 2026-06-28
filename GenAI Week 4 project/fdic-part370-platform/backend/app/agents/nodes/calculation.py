"""Agents 5 & 6: Insurance Calculation + Pending Determination."""

from __future__ import annotations

from ...domain.constants import ORC, PendingReason
from ...domain.models import PendingDecision
from ...domain.orc.engine import calculate
from ..state import DeterminationState


def insurance_calculation_agent(state: DeterminationState) -> dict:
    """Run the ORC engine over each aggregation group; emit coverage + evidence."""
    by_number = {a.account_number: a for a in state["accounts"]}
    groups = state["orc_classification"]["groups"]
    results = []
    for key, account_numbers in groups.items():
        family = key.split(":", 1)[0]
        orc = ORC(family)
        accounts = [by_number[n] for n in account_numbers]
        res = calculate(orc, accounts)
        # Attach the applicable rule snippet to the evidence chain
        rule = state.get("applicable_rules", {}).get(orc.value, {})
        res.evidence = {**res.evidence, "rule_citation": rule.get("citation"),
                        "aggregation_group": key}
        results.append(res)
    return {"coverage_results": results,
            "trace": [{"agent": "insurance_calculation", "groups": len(results)}]}


# Map structural gaps → Alternative Recordkeeping pending reasons
_AR_REASON = {
    ORC.TST: PendingReason.ARTR,
    ORC.EBP: PendingReason.AREBP,
    ORC.CRA: PendingReason.ARCRA,
    ORC.MSA: PendingReason.ARM,
}


def pending_determination_agent(state: DeterminationState) -> dict:
    """Route accounts to the Pending File with a Part 370 reason code."""
    decisions: list[PendingDecision] = []
    fail_codes = {f.code for f in state.get("customer_findings", []) if f.severity == "FAIL"}
    fail_codes |= {f.code for f in state.get("account_findings", []) if f.severity == "FAIL"}

    # Customer-level data failures → reason A (missing) or B (failed validation)
    if "SSN_MISSING" in fail_codes or "CUST_ID_MISSING" in fail_codes:
        decisions.append(PendingDecision(is_pending=True, reason=PendingReason.A,
                                         detail="Required customer data element missing"))
    elif "SSN_INVALID" in fail_codes:
        decisions.append(PendingDecision(is_pending=True, reason=PendingReason.B,
                                         detail="Customer data failed validation"))

    for a in state["accounts"]:
        reason = None
        detail = ""
        if not state.get("alt_recordkeeping_received", True):
            reason = _AR_REASON.get(a.orc, PendingReason.RAC)
            detail = "Alternative Recordkeeping data not yet received"
        elif a.orc == ORC.JNT and len(a.owners) < 2:
            reason, detail = PendingReason.ARO, "Joint ownership detail incomplete"
        elif a.orc == ORC.TST and not a.beneficiaries:
            reason, detail = PendingReason.ARTR, "Trust beneficiary detail pending"
        elif a.orc in (ORC.EBP, ORC.ANC, ORC.MSA, ORC.BIA) and not a.participants:
            reason = _AR_REASON.get(a.orc, PendingReason.ARO)
            detail = "Pass-through participant detail pending"
        if reason:
            decisions.append(PendingDecision(is_pending=True, reason=reason,
                                             account_number=a.account_number, detail=detail))

    if not decisions:
        decisions.append(PendingDecision(is_pending=False, detail="No pending conditions"))
    return {"pending_decisions": decisions,
            "trace": [{"agent": "pending_determination", "pending": sum(d.is_pending for d in decisions)}]}
