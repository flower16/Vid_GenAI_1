"""REST API surface for the determination platform."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ..agents.graph import run_determination
from ..core.auth import Principal, require
from ..domain.constants import ORC
from ..domain.models import CoverageResult, DeterminationRequest
from ..domain.orc.rules import ORC_RULES
from ..db.persistence import persist_determination

router = APIRouter(prefix="/api/v1", tags=["determination"])


@router.get("/orcs")
def list_orcs() -> list[dict]:
    """ORC catalog for the UI dropdown."""
    return [{"code": o.value, "name": ORC_RULES[o]["name"],
             "smdia": ORC_RULES[o]["smdia"]} for o in ORC]


@router.get("/orcs/{orc}/rules")
def orc_rules(orc: ORC) -> dict:
    return ORC_RULES[orc]


@router.post("/determinations")
def create_determination(
    req: DeterminationRequest,
    principal: Principal = Depends(require("run_determination")),
) -> dict:
    """Run the LangGraph workflow and persist the audit trail."""
    determination_id = str(uuid.uuid4())
    state = run_determination(req)

    coverage = [r.model_dump(mode="json") if isinstance(r, CoverageResult) else r
                for r in state.get("coverage_results", [])]
    response = {
        "determination_id": determination_id,
        "run_by": principal.name,
        "customer_findings": [f.model_dump() for f in state.get("customer_findings", [])],
        "account_findings": [f.model_dump() for f in state.get("account_findings", [])],
        "applicable_rules": state.get("applicable_rules", {}),
        "orc_classification": state.get("orc_classification", {}),
        "coverage_results": coverage,
        "pending_decisions": [d.model_dump() for d in state.get("pending_decisions", [])],
        "output_files": state.get("output_files", {}),
        "summary_report": state.get("summary_report", {}),
        "eval_results": state.get("eval_results", []),
        "trace": state.get("trace", []),
    }
    persist_determination(determination_id, req, response)
    return response


@router.post("/determinations/{determination_id}/recalculate")
def recalculate(
    determination_id: str,
    req: DeterminationRequest,
    principal: Principal = Depends(require("run_determination")),
) -> dict:
    """Iterative recalculation when Alternative Recordkeeping data arrives."""
    req.alt_recordkeeping_received = True
    state = run_determination(req)
    response = {"determination_id": determination_id, "recalculated": True,
                "coverage_results": [r.model_dump(mode="json") for r in state.get("coverage_results", [])],
                "pending_decisions": [d.model_dump() for d in state.get("pending_decisions", [])],
                "summary_report": state.get("summary_report", {}),
                "eval_results": state.get("eval_results", [])}
    persist_determination(determination_id, req, response, is_recalc=True)
    return response
