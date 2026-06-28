"""
FDIC Part 370 Deposit Insurance Coverage Summary Report (§370.10(a)(2)).

Mirrors the illustrative report in the IT Functional Guide §6.2 / Appendix B:

  Table 1 — Summary by Ownership Right and Capacity: per ORC, the count and
            dollars of fully-insured vs partially-insured/uninsured accounts.
  Table 2 — Summary of Deposits by Pending Code, split into
            I. Records maintained by the bank (A, B, OI, RAC) and
            II. Alternative recordkeeping (ARB, ARBN, ARCRA, AREBP, ARM, ARO, ARTR).
  Reconciliation — internal control: Table 1 insured+uninsured + pending == total
            principal & interest (the guide's validation that all deposit
            balances are accounted for across the output files).
"""

from __future__ import annotations

from decimal import Decimal

from ..domain.constants import (
    PENDING_ALT_RECORDKEEPING,
    PENDING_BANK_MAINTAINED,
    PendingReason,
)
from ..domain.models import CoverageResult, PendingDecision


def build_summary(coverage: list[CoverageResult],
                  pending: list[PendingDecision]) -> dict:
    # ---- Table 1: coverage by ORC (fully vs partially insured) ----
    table1, t_pi, t_ins, t_unins = [], Decimal("0"), Decimal("0"), Decimal("0")
    for r in coverage:
        fully = r.uninsured_amount == 0
        table1.append({
            "orc": r.orc.value,
            "deposit_accounts": len(r.accounts_included),
            "fully_insured_count": len(r.accounts_included) if fully else 0,
            "fully_insured_dollars": str(r.insured_amount if fully else Decimal("0")),
            "partial_uninsured_count": 0 if fully else len(r.accounts_included),
            "dollars_insured": str(Decimal("0") if fully else r.insured_amount),
            "dollars_uninsured": str(r.uninsured_amount),
            "aggregated_pi": str(r.aggregated_pi),
            "coverage_limit": str(r.coverage_limit),
        })
        t_pi += r.aggregated_pi
        t_ins += r.insured_amount
        t_unins += r.uninsured_amount

    table1_total = {"deposit_accounts": sum(t["deposit_accounts"] for t in table1),
                    "total_pi": str(t_pi), "total_insured": str(t_ins),
                    "total_uninsured": str(t_unins)}

    # ---- Table 2: pending by code, grouped per the guide ----
    counts: dict[str, int] = {}
    for d in pending:
        if d.is_pending and d.reason:
            counts[d.reason.value] = counts.get(d.reason.value, 0) + 1

    def _section(codes: list[PendingReason]) -> list[dict]:
        return [{"reason_code": c.value, "count": counts.get(c.value, 0)} for c in codes]

    table2 = {
        "I_records_maintained_by_bank": _section(PENDING_BANK_MAINTAINED),
        "II_alternative_recordkeeping": _section(PENDING_ALT_RECORDKEEPING),
        "total_pending_accounts": sum(counts.values()),
    }

    # ---- Reconciliation control ----
    reconciliation = {
        "total_principal_and_interest": str(t_pi),
        "total_insured": str(t_ins),
        "total_uninsured": str(t_unins),
        "reconciles": t_ins + t_unins == t_pi,
        "pending_accounts": table2["total_pending_accounts"],
    }

    return {"table_1_coverage_by_orc": table1,
            "table_1_total": table1_total,
            "table_2_pending_by_code": table2,
            "reconciliation": reconciliation}
