"""
MCP server exposing FDIC Part 370 determination tools.

Run:  python -m app.mcp.server   (stdio transport)

Tools map 1:1 to the agent capabilities so an MCP client (Claude Desktop, an
orchestrator, or another agent) can drive the determination pipeline tool-by-tool
or end-to-end via `run_evals` / the REST API.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..agents.graph import run_determination
from ..agents.nodes.calculation import (
    insurance_calculation_agent,
    pending_determination_agent,
)
from ..agents.nodes.rules_and_classify import orc_classification_agent
from ..agents.nodes.validation import account_validation_agent, customer_validation_agent
from ..domain.constants import ORC
from ..domain.models import Account, Customer, DeterminationRequest
from ..files import generators as gen

mcp = FastMCP("fdic-part370")


@mcp.tool()
def validate_customer(customer: dict) -> dict:
    """Validate customer demographics, SSN/TIN, type, ownership structure."""
    state = {"customer": Customer(**customer), "accounts": []}
    return customer_validation_agent(state)


@mcp.tool()
def validate_account(accounts: list[dict]) -> dict:
    """Validate account ownership, product, interest, joint/trust requirements."""
    state = {"accounts": [Account(**a) for a in accounts]}
    return account_validation_agent(state)


@mcp.tool()
def classify_orc(customer: dict, accounts: list[dict]) -> dict:
    """Assign ORC and build aggregation groups."""
    state = {"customer": Customer(**customer),
             "accounts": [Account(**a) for a in accounts]}
    return orc_classification_agent(state)


@mcp.tool()
def calculate_insurance(customer: dict, accounts: list[dict]) -> dict:
    """Calculate aggregated balance, coverage limit, insured & uninsured."""
    acc = [Account(**a) for a in accounts]
    state = {"customer": Customer(**customer), "accounts": acc,
             "applicable_rules": {}}
    state.update(orc_classification_agent(state))
    res = insurance_calculation_agent(state)
    return {"coverage_results": [r.model_dump(mode="json") for r in res["coverage_results"]]}


@mcp.tool()
def generate_customer_file(customer: dict) -> dict:
    """Generate FDIC Customer File."""
    return gen.customer_file([Customer(**customer)])


@mcp.tool()
def generate_account_file(accounts: list[dict]) -> dict:
    """Generate FDIC Account File."""
    return gen.account_file([Account(**a) for a in accounts])


@mcp.tool()
def generate_participant_file(accounts: list[dict]) -> dict:
    """Generate FDIC Account Participant File."""
    return gen.participant_file([Account(**a) for a in accounts])


@mcp.tool()
def generate_pending_file(customer: dict, accounts: list[dict],
                          alt_recordkeeping_received: bool = True) -> dict:
    """Generate FDIC Pending File with reason codes."""
    acc = [Account(**a) for a in accounts]
    state: dict[str, Any] = {"customer": Customer(**customer), "accounts": acc,
                             "alt_recordkeeping_received": alt_recordkeeping_received}
    state.update(customer_validation_agent(state))
    state.update(account_validation_agent(state))
    pend = pending_determination_agent(state)
    return gen.pending_file(pend["pending_decisions"], state["customer"].customer_id)


@mcp.tool()
def generate_summary_report(customer: dict, accounts: list[dict]) -> dict:
    """Run the full workflow and return the Summary Report (Tables 1-3)."""
    req = DeterminationRequest(customer=Customer(**customer),
                               accounts=[Account(**a) for a in accounts])
    state = run_determination(req)
    return state.get("summary_report", {})


@mcp.tool()
def run_evals(customer: dict, accounts: list[dict]) -> dict:
    """Run the full workflow and return eval results (PASS/FAIL/WARNING)."""
    req = DeterminationRequest(customer=Customer(**customer),
                               accounts=[Account(**a) for a in accounts])
    state = run_determination(req)
    return {"eval_results": state.get("eval_results", [])}


if __name__ == "__main__":
    mcp.run()
