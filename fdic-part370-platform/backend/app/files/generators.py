"""
FDIC Part 370 output-file generators.

Field names and ordering follow the IT Functional Guide v3.0 Appendix A record
layouts (pipe-delimited). The four files are linked by CS_Unique_ID, and the
Account Participant / Account files additionally by DP_Acct_Identifier (+
DP_Right_Capacity for the participant file). Per §5.3, an Account Participant
File is NOT produced for SGL, JNT, CRA, BUS, BIA, or DOE accounts.
"""

from __future__ import annotations

from ..domain.constants import ORC
from ..domain.models import Account, Customer, PendingDecision

# Authoritative field orders (subset of the most calculation-relevant fields;
# full layouts in Appendix A — null-allowed fields emitted as empty between pipes).
FILE_LAYOUTS = {
    "customer": ["CS_Unique_ID", "CS_Govt_ID", "CS_Govt_ID_Type", "CS_Type",
                 "CS_First_Name", "CS_Last_Name", "CS_Entity_Name",
                 "CS_Street_Add_Ln1", "CS_City", "CS_State", "CS_ZIP",
                 "CS_Telephone", "CS_Email"],
    "account": ["CS_Unique_ID", "DP_Acct_Identifier", "DP_Right_Capacity",
                "DP_Prod_Cat", "DP_Allocated_Amt", "DP_Acc_Int", "DP_Total_PI",
                "DP_Hold_Amount", "DP_Insured_Amount", "DP_Uninsured_Amount",
                "DP_Prepaid_Account_Flag", "DP_PT_Account_Flag", "DP_PT_Trans_Flag"],
    "participant": ["CS_Unique_ID", "DP_Acct_Identifier", "DP_Right_Capacity",
                    "AP_Allocated_Amount", "AP_Participant_ID", "AP_Govt_ID",
                    "AP_First_Name", "AP_Last_Name", "AP_Entity_Name",
                    "AP_Participant_Type"],
    "pending": ["CS_Unique_ID", "Pending_Reason", "DP_Acct_Identifier",
                "DP_Right_Capacity", "DP_Prod_Category", "DP_Cur_Bal",
                "DP_Acc_Int", "DP_Total_PI", "DP_Hold_Amount", "CS_Govt_ID"],
}

# §5.3 — ORCs that do NOT generate an Account Participant File record.
_NO_PARTICIPANT_FILE = {ORC.SGL, ORC.JNT, ORC.CRA, ORC.BUS, ORC.BIA, ORC.DOE}

# AP_Participant_Type codes (Appendix A, field 13)
_ROLE_OWNER = "OC"          # official custodian (GOV) — owners surfaced as custodians
_ROLE_BENEFICIARY = "BEN"
_ROLE_BONDHOLDER = "BHR"
_ROLE_MORTGAGOR = "MOR"
_ROLE_PARTICIPANT = "EPP"   # employee benefit plan participant


def _row(values: list) -> str:
    return "|".join("" if v is None else str(v) for v in values)


def customer_file(customers: list[Customer]) -> dict:
    rows = [_row([c.customer_id, c.ssn_tin, _govt_id_type(c.ssn_tin),
                  c.customer_type.value if c.customer_type else "",
                  c.first_name, c.last_name, "", c.address, "", "", "",
                  c.phone, c.email]) for c in customers]
    return {"layout": FILE_LAYOUTS["customer"], "header": _row(FILE_LAYOUTS["customer"]),
            "rows": rows, "record_count": len(rows)}


def account_file(accounts: list[Account]) -> dict:
    rows = [_row([a.customer_id, a.account_number, a.orc.value, a.product_type,
                  a.balance, a.accrued_interest, a.principal_and_interest,
                  a.hold_amount, "", "", "N", "N", "N"]) for a in accounts]
    return {"layout": FILE_LAYOUTS["account"], "header": _row(FILE_LAYOUTS["account"]),
            "rows": rows, "record_count": len(rows)}


def participant_file(accounts: list[Account]) -> dict:
    """Per §5.3, only TST/EBP/ANC/DIT/GOV*/MSA/PBA accounts populate this file."""
    rows: list[str] = []
    for a in accounts:
        if a.orc in _NO_PARTICIPANT_FILE:
            continue
        for b in a.beneficiaries:
            rows.append(_row([a.customer_id, a.account_number, a.orc.value,
                              b.interest_pct, b.party_id, b.party_id, b.name, "", "",
                              _ROLE_BONDHOLDER if a.orc == ORC.PBA else _ROLE_BENEFICIARY]))
        for p in a.participants:
            role = {ORC.MSA: _ROLE_MORTGAGOR, ORC.EBP: _ROLE_PARTICIPANT}.get(
                a.orc, _ROLE_PARTICIPANT)
            rows.append(_row([a.customer_id, a.account_number, a.orc.value,
                              p.vested_interest, p.party_id, p.party_id, p.name, "", "", role]))
        if a.orc in (ORC.GOV1, ORC.GOV2, ORC.GOV3):
            for o in a.owners:
                rows.append(_row([a.customer_id, a.account_number, a.orc.value,
                                  o.ownership_pct, o.party_id, o.party_id, o.name, "", "",
                                  _ROLE_OWNER]))
    return {"layout": FILE_LAYOUTS["participant"], "header": _row(FILE_LAYOUTS["participant"]),
            "rows": rows, "record_count": len(rows)}


def pending_file(decisions: list[PendingDecision], customer_id: str,
                 govt_id: str = "") -> dict:
    rows = [_row([customer_id, d.reason.value if d.reason else "",
                  d.account_number or "", "", "", "", "", "", "", govt_id])
            for d in decisions if d.is_pending]
    return {"layout": FILE_LAYOUTS["pending"], "header": _row(FILE_LAYOUTS["pending"]),
            "rows": rows, "record_count": len(rows)}


def _govt_id_type(ssn_tin: str | None) -> str:
    """Infer CS_Govt_ID_Type (SSN vs TIN) from format (NNN-NN-NNNN vs NN-NNNNNNN)."""
    if not ssn_tin:
        return ""
    digits = ssn_tin.replace("-", "")
    if len(digits) == 9 and ssn_tin[:3].isdigit() and "-" in ssn_tin and ssn_tin.index("-") == 3:
        return "SSN"
    return "TIN" if len(digits) == 9 else "OTH"
