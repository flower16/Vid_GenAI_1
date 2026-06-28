"""
LangGraph multi-agent workflow for FDIC Part 370 determination.

Flow:
    rules ─┐
           ├─► classify ─► calculate ─► pending ─► output ─► summary ─► evals ─► END
  customer ┤
  account ─┘
(validation + rules run in parallel, then converge at classify)

Supports iterative recalculation: invoke again with
`alt_recordkeeping_received=True` and updated accounts; the Pending Agent will
clear AR* reasons and the engine recomputes coverage.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..domain.models import DeterminationRequest
from .nodes.calculation import insurance_calculation_agent, pending_determination_agent
from .nodes.output_and_report import (
    evals_agent,
    output_file_agent,
    summary_report_agent,
)
from .nodes.rules_and_classify import fdic_rules_agent, orc_classification_agent
from .nodes.validation import account_validation_agent, customer_validation_agent
from .state import DeterminationState


def build_graph():
    g = StateGraph(DeterminationState)

    g.add_node("fdic_rules", fdic_rules_agent)
    g.add_node("customer_validation", customer_validation_agent)
    g.add_node("account_validation", account_validation_agent)
    g.add_node("classify", orc_classification_agent)
    g.add_node("insurance_calculation", insurance_calculation_agent)
    g.add_node("pending_determination", pending_determination_agent)
    g.add_node("output_file", output_file_agent)
    g.add_node("summary", summary_report_agent)
    g.add_node("evals", evals_agent)

    # Fan-out: rules + validations run from START in parallel
    g.add_edge(START, "fdic_rules")
    g.add_edge(START, "customer_validation")
    g.add_edge(START, "account_validation")

    # Converge at classification (LangGraph waits for all three)
    g.add_edge("fdic_rules", "classify")
    g.add_edge("customer_validation", "classify")
    g.add_edge("account_validation", "classify")

    # Linear determination pipeline
    g.add_edge("classify", "insurance_calculation")
    g.add_edge("insurance_calculation", "pending_determination")
    g.add_edge("pending_determination", "output_file")
    g.add_edge("output_file", "summary")
    g.add_edge("summary", "evals")
    g.add_edge("evals", END)

    return g.compile()


WORKFLOW = build_graph()


def run_determination(request: DeterminationRequest) -> dict:
    """Execute the full workflow and return the final state."""
    initial: DeterminationState = {
        "customer": request.customer,
        "accounts": request.accounts,
        "alt_recordkeeping_received": request.alt_recordkeeping_received,
    }
    return WORKFLOW.invoke(initial)
