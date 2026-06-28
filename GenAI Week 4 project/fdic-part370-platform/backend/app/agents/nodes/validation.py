"""Agents 2 & 3: Customer Validation + Account Validation."""

from __future__ import annotations

import re
from decimal import Decimal

from ...domain.constants import ORC
from ...domain.models import ValidationFinding
from ..state import DeterminationState

_SSN_RE = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")
_TIN_RE = re.compile(r"^\d{2}-?\d{7}$")


def _finding(code, sev, msg, field=None) -> ValidationFinding:
    return ValidationFinding(code=code, severity=sev, message=msg, field=field)


def customer_validation_agent(state: DeterminationState) -> dict:
    """Validate demographics, SSN/TIN, customer type, ownership structure."""
    c = state["customer"]
    findings: list[ValidationFinding] = []

    if not c.customer_id:
        findings.append(_finding("CUST_ID_MISSING", "FAIL", "Customer ID is required", "customer_id"))
    if not (c.first_name or c.last_name):
        findings.append(_finding("CUST_NAME_MISSING", "FAIL", "Customer name is required", "name"))
    if not c.ssn_tin:
        findings.append(_finding("SSN_MISSING", "FAIL", "SSN/TIN is required (Part 370 data element)", "ssn_tin"))
    elif not (_SSN_RE.match(c.ssn_tin) or _TIN_RE.match(c.ssn_tin)):
        findings.append(_finding("SSN_INVALID", "FAIL", f"SSN/TIN '{c.ssn_tin}' is not a valid format", "ssn_tin"))
    if not c.customer_type:
        findings.append(_finding("CUST_TYPE_MISSING", "WARNING", "Customer type not provided", "customer_type"))
    if not c.address:
        findings.append(_finding("ADDR_MISSING", "WARNING", "Address recommended for Part 370", "address"))

    if not findings:
        findings.append(_finding("CUST_OK", "PASS", "Customer demographics valid"))
    return {"customer_findings": findings,
            "trace": [{"agent": "customer_validation", "findings": len(findings)}]}


def account_validation_agent(state: DeterminationState) -> dict:
    """Validate ownership, product, accrued interest, joint & trust requirements."""
    findings: list[ValidationFinding] = []
    for a in state["accounts"]:
        if a.balance < Decimal("0"):
            findings.append(_finding("BAL_NEGATIVE", "FAIL", f"{a.account_number}: negative balance", "balance"))
        if a.accrued_interest < Decimal("0"):
            findings.append(_finding("INT_NEGATIVE", "WARNING", f"{a.account_number}: negative accrued interest", "accrued_interest"))
        if a.hold_amount > a.principal_and_interest:
            findings.append(_finding("HOLD_EXCEEDS", "WARNING", f"{a.account_number}: hold exceeds PI", "hold_amount"))

        # ORC-specific structural validation
        if a.orc == ORC.JNT and len(a.owners) < 2:
            findings.append(_finding("JNT_OWNERS", "FAIL", f"{a.account_number}: joint account needs ≥2 owners", "owners"))
        if a.orc == ORC.TST and not a.beneficiaries:
            findings.append(_finding("TST_BENE", "FAIL", f"{a.account_number}: trust account needs beneficiaries", "beneficiaries"))
        if a.orc in (ORC.EBP, ORC.ANC, ORC.MSA, ORC.BIA) and not a.participants:
            findings.append(_finding("PARTICIPANTS_MISSING", "WARNING",
                                     f"{a.account_number}: {a.orc.value} requires participant/principal roster", "participants"))

        # BUS (12 CFR 330.11) eligibility checks
        if a.orc == ORC.BUS and not a.sole_proprietorship:
            if a.independent_activity is None:
                findings.append(_finding("BUS_ACTIVITY_UNCONFIRMED", "WARNING",
                                         f"{a.account_number}: independent business activity not confirmed; "
                                         f"assumed engaged (separate-entity coverage)", "independent_activity"))
            elif a.independent_activity is False and not a.owners:
                findings.append(_finding("BUS_MEMBERS_MISSING", "WARNING",
                                         f"{a.account_number}: non-independent entity needs a member roster "
                                         f"to allocate pass-through coverage", "owners"))

    if not findings:
        findings.append(_finding("ACCT_OK", "PASS", "Accounts valid"))
    return {"account_findings": findings,
            "trace": [{"agent": "account_validation", "findings": len(findings)}]}
