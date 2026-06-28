"""
Audit/persistence layer.

Writes the determination, coverage results, and eval results to Snowflake via
SQLAlchemy. When Snowflake is not configured (local/dev), it appends to a local
JSONL audit log so the full audit trail is always captured.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import settings
from ..domain.models import DeterminationRequest

logger = logging.getLogger(__name__)
_LOCAL_AUDIT = Path(__file__).resolve().parents[3] / "audit_log.jsonl"


def _snowflake_engine():  # pragma: no cover - external dep
    from sqlalchemy import create_engine
    url = (
        f"snowflake://{settings.snowflake_user}:{settings.snowflake_password}"
        f"@{settings.snowflake_account}/{settings.snowflake_database}/"
        f"{settings.snowflake_schema}?warehouse={settings.snowflake_warehouse}"
    )
    if settings.snowflake_role:
        url += f"&role={settings.snowflake_role}"
    return create_engine(url)


def _log_evals_to_langsmith(determination_id: str, eval_results) -> str | None:  # pragma: no cover
    """Auto-sync: log the in-workflow evals to LangSmith as a run with one
    feedback score per eval. Returns the LangSmith run id (stored back in
    Snowflake) or None. Never raises — eval logging must not break a determination.
    """
    if not settings.langsmith_api_key or not eval_results:
        return None
    try:
        import uuid
        from langsmith import Client
        client = Client()
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        client.create_run(
            id=run_id, name=f"determination-{determination_id[:8]}", run_type="chain",
            inputs={"determination_id": determination_id},
            outputs={"evals": {e.get("name"): e.get("status") for e in eval_results}},
            project_name=settings.langsmith_project, start_time=now, end_time=now,
        )
        score = {"PASS": 1.0, "WARNING": 0.5, "FAIL": 0.0}
        for e in eval_results:
            client.create_feedback(run_id, key=e.get("name", "unnamed"),
                                   score=score.get(e.get("status"), 0.0),
                                   comment=f"{e.get('status')}: {e.get('detail', '')}"[:250])
        return run_id
    except Exception as exc:
        logger.warning("LangSmith auto-sync failed (rows still in Snowflake): %s", exc)
        return None


def persist_determination(determination_id: str, req: DeterminationRequest,
                          response: dict, is_recalc: bool = False) -> None:
    # Auto-sync evals to LangSmith first so the run id can be stored in Snowflake.
    ls_run_id = _log_evals_to_langsmith(determination_id, response.get("eval_results"))
    record = {
        "determination_id": determination_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "is_recalc": is_recalc,
        "customer_id": req.customer.customer_id,
        "summary_report": response.get("summary_report"),
        "eval_results": response.get("eval_results"),
        "langsmith_run_id": ls_run_id,
    }
    if settings.snowflake_account:
        try:
            _persist_snowflake(determination_id, req, response, is_recalc, ls_run_id)
            return
        except Exception as exc:  # pragma: no cover - external dep
            logger.error("Snowflake persist failed, falling back to local: %s", exc)
    with _LOCAL_AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _persist_snowflake(determination_id, req, response, is_recalc, ls_run_id=None):  # pragma: no cover
    from sqlalchemy import text
    engine = _snowflake_engine()
    summary = json.dumps(response.get("summary_report"))
    # INSURANCE_RESULT is keyed by (DETERMINATION_ID, ORC) with per-ORC coverage
    # columns, so write one row per coverage result. ORC is part of the primary
    # key and therefore NOT NULL in Snowflake.
    coverage_results = response.get("coverage_results") or []
    rows = [{
        "id": determination_id,
        "cust": req.customer.customer_id,
        "orc": cr.get("orc"),
        "pi": cr.get("aggregated_pi"),
        "limit": cr.get("coverage_limit"),
        "insured": cr.get("insured_amount"),
        "uninsured": cr.get("uninsured_amount"),
        "recalc": is_recalc,
        "summary": summary,
    } for cr in coverage_results if cr.get("orc")]
    # No coverage result (e.g. everything pending) — still record the determination.
    if not rows:
        rows = [{"id": determination_id, "cust": req.customer.customer_id,
                 "orc": "NONE", "pi": None, "limit": None, "insured": None,
                 "uninsured": None, "recalc": is_recalc, "summary": summary}]
    with engine.begin() as conn:
        for row in rows:
            conn.execute(text(
                "INSERT INTO INSURANCE_RESULT "
                "(DETERMINATION_ID, CUSTOMER_ID, ORC, AGGREGATED_PI, COVERAGE_LIMIT, "
                "INSURED_AMOUNT, UNINSURED_AMOUNT, IS_RECALC, SUMMARY_REPORT, CREATED_AT) "
                "SELECT :id, :cust, :orc, :pi, :limit, :insured, :uninsured, :recalc, "
                "PARSE_JSON(:summary), CURRENT_TIMESTAMP()"
            ), row)
        conn.execute(text(
            "INSERT INTO CALCULATION_AUDIT (DETERMINATION_ID, PAYLOAD, CREATED_AT) "
            "SELECT :id, PARSE_JSON(:payload), CURRENT_TIMESTAMP()"
        ), {"id": determination_id, "payload": json.dumps(response, default=str)})

        # One row per in-workflow eval (evals_agent output) so the eval outcomes
        # are queryable alongside the determination in LANGSMITH_EVAL_RESULTS.
        for ev in response.get("eval_results") or []:
            conn.execute(text(
                "INSERT INTO LANGSMITH_EVAL_RESULTS "
                "(DETERMINATION_ID, EVAL_NAME, STATUS, DETAIL, LANGSMITH_RUN_ID, CREATED_AT) "
                "VALUES (:id, :name, :status, :detail, :run_id, CURRENT_TIMESTAMP())"
            ), {"id": determination_id, "name": ev.get("name", "unnamed"),
                "status": ev.get("status", "UNKNOWN"), "detail": ev.get("detail", ""),
                "run_id": ls_run_id})
