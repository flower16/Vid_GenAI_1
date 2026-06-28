"""Shared LangGraph state passed between the 9 agents."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
import operator

from ..domain.models import (
    Account,
    CoverageResult,
    Customer,
    PendingDecision,
    ValidationFinding,
)


def _merge_dict(a: dict, b: dict) -> dict:
    return {**a, **b}


class DeterminationState(TypedDict, total=False):
    """Flows through the graph. Reducer-annotated fields merge across nodes."""

    # Inputs
    customer: Customer
    accounts: list[Account]
    alt_recordkeeping_received: bool

    # Agent outputs (accumulated)
    applicable_rules: Annotated[dict, _merge_dict]
    customer_findings: Annotated[list[ValidationFinding], operator.add]
    account_findings: Annotated[list[ValidationFinding], operator.add]
    orc_classification: Annotated[dict, _merge_dict]
    coverage_results: Annotated[list[CoverageResult], operator.add]
    pending_decisions: Annotated[list[PendingDecision], operator.add]
    output_files: Annotated[dict, _merge_dict]
    summary_report: dict
    eval_results: Annotated[list, operator.add]

    # Control
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict[str, Any]], operator.add]
