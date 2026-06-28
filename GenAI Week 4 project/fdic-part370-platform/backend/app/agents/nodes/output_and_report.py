"""Agents 7, 8 & 9: Output File generation, Summary Report, Evals."""

from __future__ import annotations

from decimal import Decimal

from ...domain.constants import ORC
from ...domain.models import EvalResult
from ...files import generators as gen
from ...reports.summary import build_summary
from ..state import DeterminationState


def output_file_agent(state: DeterminationState) -> dict:
    """Generate Customer, Account, Account Participant, and Pending files."""
    accounts = state["accounts"]
    files = {
        "customer_file": gen.customer_file([state["customer"]]),
        "account_file": gen.account_file(accounts),
        "participant_file": gen.participant_file(accounts),
        "pending_file": gen.pending_file(state.get("pending_decisions", []),
                                         state["customer"].customer_id),
    }
    return {"output_files": files,
            "trace": [{"agent": "output_file", "files": list(files)}]}


def summary_report_agent(state: DeterminationState) -> dict:
    """Build the Part 370 Summary Report (Tables 1-3)."""
    report = build_summary(state.get("coverage_results", []),
                           state.get("pending_decisions", []))
    return {"summary_report": report,
            "trace": [{"agent": "summary_report", "tables": 3}]}


def evals_agent(state: DeterminationState) -> dict:
    """In-line correctness evals (mirrors the LangSmith eval suite)."""
    results: list[EvalResult] = []

    # 1. Input completeness
    fails = [f for f in state.get("customer_findings", []) + state.get("account_findings", [])
             if f.severity == "FAIL"]
    results.append(EvalResult(name="input_completeness",
                              status="FAIL" if fails else "PASS",
                              detail=f"{len(fails)} blocking finding(s)"))

    # 2. Insured + Uninsured = Total PI (per ORC)
    recon_ok = all(r.insured_amount + r.uninsured_amount == r.aggregated_pi
                   for r in state.get("coverage_results", []))
    results.append(EvalResult(name="deposit_balance_reconciliation",
                              status="PASS" if recon_ok else "FAIL",
                              detail="insured + uninsured == PI for all ORCs"))

    # 3. Coverage limits respected
    limit_ok = all(r.insured_amount <= r.coverage_limit + Decimal("0.01")
                   for r in state.get("coverage_results", []))
    results.append(EvalResult(name="coverage_limit_respected",
                              status="PASS" if limit_ok else "FAIL"))

    # 4. Summary report reconciliation (Table 1 + pending == total PI)
    recon = state.get("summary_report", {}).get("reconciliation", {})
    results.append(EvalResult(name="summary_report_reconciliation",
                              status="PASS" if recon.get("reconciles") else "WARNING",
                              detail=str(recon)))

    # 5. Every input account is accounted for (covered or routed to pending)
    input_accts = {a.account_number for a in state.get("accounts", [])}
    covered = {n for r in state.get("coverage_results", []) for n in r.accounts_included}
    pending_accts = {d.account_number for d in state.get("pending_decisions", [])
                     if d.account_number}
    unaccounted = input_accts - covered - pending_accts
    results.append(EvalResult(name="accounts_fully_accounted",
                              status="PASS" if not unaccounted else "FAIL",
                              detail=("all accounts covered or pending"
                                      if not unaccounted
                                      else f"{len(unaccounted)} unaccounted: {sorted(unaccounted)}")))

    # 6. SSN/TIN validity (mirrors the LangSmith ssn_validation evaluator)
    ssn_codes = {f.code for f in state.get("customer_findings", [])}
    ssn_issue = "SSN_INVALID" in ssn_codes or "SSN_MISSING" in ssn_codes
    results.append(EvalResult(name="ssn_validation",
                              status="WARNING" if ssn_issue else "PASS",
                              detail="SSN/TIN issue flagged" if ssn_issue else "SSN/TIN valid"))

    # 7. BUS eligibility treatment assigned (mirrors the bus_treatment evaluator)
    bus_results = [r for r in state.get("coverage_results", []) if r.orc == ORC.BUS]
    valid_treatments = {"per_entity_independent", "pass_through_members"}
    bus_ok = all(r.evidence.get("treatment") in valid_treatments for r in bus_results)
    results.append(EvalResult(name="bus_treatment",
                              status="PASS" if bus_ok else "WARNING",
                              detail=("no BUS accounts" if not bus_results
                                      else f"treatments: {[r.evidence.get('treatment') for r in bus_results]}")))

    return {"eval_results": [r.model_dump() for r in results],
            "trace": [{"agent": "evals", "checks": len(results)}]}
