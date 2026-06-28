"""
Initialize the Snowflake schema from db/snowflake_ddl.sql using the .env
credentials (SNOWFLAKE_* in backend/.env).

Usage (from backend/):
    python scripts/init_snowflake.py            # run the DDL
    python scripts/init_snowflake.py --dry-run  # print statements, connect nothing

Executes each statement independently and continues on error, so unsupported
DDL on standard tables (e.g. CREATE INDEX, which Snowflake only supports on
Unistore/hybrid tables) is reported as a warning rather than aborting the run.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

# The summary prints ✓/✗ markers; force UTF-8 so it never crashes on consoles
# that default to a legacy code page (e.g. Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover - older/odd streams
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

DDL_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "snowflake_ddl.sql"


def split_statements(sql: str) -> list[str]:
    """Split on ';' and drop chunks that are only comments/whitespace."""
    statements = []
    for chunk in sql.split(";"):
        # strip full-line comments so comment-only chunks are skipped
        body = "\n".join(
            ln for ln in chunk.splitlines() if not ln.strip().startswith("--")
        ).strip()
        if body:
            statements.append(body)
    return statements


def _first_line(stmt: str) -> str:
    return " ".join(stmt.splitlines()[0].split())[:70]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print the statements without connecting")
    args = parser.parse_args()

    if not DDL_PATH.exists():
        print(f"DDL file not found: {DDL_PATH}")
        return 1
    statements = split_statements(DDL_PATH.read_text(encoding="utf-8"))
    print(f"Parsed {len(statements)} SQL statements from {DDL_PATH.name}.")

    if args.dry_run:
        for i, s in enumerate(statements, 1):
            print(f"  [{i:02d}] {_first_line(s)}")
        return 0

    if not settings.snowflake_account:
        print("\nSNOWFLAKE_ACCOUNT is not set in backend/.env — nothing to run.")
        print("Fill in SNOWFLAKE_ACCOUNT / USER / PASSWORD / WAREHOUSE (+ ROLE) "
              "and re-run, or use --dry-run to preview the DDL.")
        return 1

    try:
        import snowflake.connector
    except ImportError:
        print("snowflake-connector-python is not installed "
              "(pip install -r requirements.txt).")
        return 1

    conn = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        warehouse=settings.snowflake_warehouse,
        role=settings.snowflake_role,
        # database/schema are created by the DDL itself, so don't require them here
    )
    print(f"Connected to Snowflake account '{settings.snowflake_account}' "
          f"as '{settings.snowflake_user}'.\n")

    ok, failed = 0, 0
    try:
        cur = conn.cursor()
        for i, stmt in enumerate(statements, 1):
            label = _first_line(stmt)
            try:
                cur.execute(stmt)
                ok += 1
                print(f"  ✓ [{i:02d}] {label}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                failed += 1
                print(f"  ✗ [{i:02d}] {label}\n        {exc}")
    finally:
        conn.close()

    print(f"\nDone: {ok} succeeded, {failed} failed/skipped "
          f"(index DDL on standard tables is expected to be skipped).")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
