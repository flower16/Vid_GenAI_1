"""
Sync per-determination eval results from Snowflake -> LangSmith.

Reads LANGSMITH_EVAL_RESULTS (populated by the in-workflow evals agent on every
determination), logs each determination as a run in the LangSmith project with
one feedback score per eval (PASS=1, WARNING=0.5, FAIL=0), then writes the
LangSmith run id back into the Snowflake row so the two systems are linked.

Usage (from backend/):
    python scripts/sync_evals_to_langsmith.py            # sync unlinked rows
    python scripts/sync_evals_to_langsmith.py --all      # re-sync every row
    python scripts/sync_evals_to_langsmith.py --dry-run  # show plan, no writes

Requires SNOWFLAKE_* and LANGSMITH_API_KEY in backend/.env.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

_SCORE = {"PASS": 1.0, "WARNING": 0.5, "FAIL": 0.0}


def _snowflake():
    import snowflake.connector
    return snowflake.connector.connect(
        account=settings.snowflake_account, user=settings.snowflake_user,
        password=settings.snowflake_password, warehouse=settings.snowflake_warehouse or None,
        role=settings.snowflake_role or None, database=settings.snowflake_database,
        schema=settings.snowflake_schema)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-sync rows even if already linked")
    ap.add_argument("--dry-run", action="store_true", help="print plan, write nothing")
    args = ap.parse_args()

    if not (settings.snowflake_account and settings.langsmith_api_key):
        print("Need SNOWFLAKE_* and LANGSMITH_API_KEY in backend/.env.")
        return 1

    conn = _snowflake()
    cur = conn.cursor()
    where = "" if args.all else "WHERE LANGSMITH_RUN_ID IS NULL"
    cur.execute(f"SELECT DETERMINATION_ID, EVAL_NAME, STATUS, DETAIL "
                f"FROM LANGSMITH_EVAL_RESULTS {where} ORDER BY DETERMINATION_ID")
    rows = cur.fetchall()
    if not rows:
        print("No eval rows to sync (all already linked — use --all to re-sync).")
        conn.close()
        return 0

    by_det: dict[str, list[tuple]] = defaultdict(list)
    for det_id, name, status, detail in rows:
        by_det[det_id].append((name, status, detail))
    print(f"{len(rows)} eval rows across {len(by_det)} determination(s) to sync.")

    if args.dry_run:
        for det_id, evals in by_det.items():
            passed = sum(1 for _, s, _ in evals if s == "PASS")
            print(f"  {det_id[:8]}…  {passed}/{len(evals)} PASS  -> 1 LangSmith run + {len(evals)} feedback")
        conn.close()
        return 0

    from langsmith import Client
    client = Client()
    project = settings.langsmith_project
    now = datetime.now(timezone.utc)
    linked = 0

    for det_id, evals in by_det.items():
        run_id = str(uuid.uuid4())
        statuses = {name: status for name, status, _ in evals}
        client.create_run(
            id=run_id,
            name=f"determination-{det_id[:8]}",
            run_type="chain",
            inputs={"determination_id": det_id},
            outputs={"evals": statuses,
                     "passed": sum(1 for v in statuses.values() if v == "PASS"),
                     "total": len(statuses)},
            project_name=project,
            start_time=now, end_time=now,
        )
        for name, status, detail in evals:
            client.create_feedback(run_id, key=name,
                                   score=_SCORE.get(status, 0.0),
                                   comment=f"{status}: {detail}"[:250])
        cur.execute("UPDATE LANGSMITH_EVAL_RESULTS SET LANGSMITH_RUN_ID = %s "
                    "WHERE DETERMINATION_ID = %s", (run_id, det_id))
        linked += 1
        print(f"  {det_id[:8]}…  -> LangSmith run {run_id[:8]}  ({len(evals)} feedback)")

    conn.commit()
    conn.close()
    print(f"\nSynced {linked} determination(s) to LangSmith project '{project}'.")
    print("View them in the LangSmith UI under that project (filter by run name 'determination-').")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
