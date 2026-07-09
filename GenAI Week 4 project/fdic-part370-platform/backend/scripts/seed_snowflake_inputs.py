"""
Seed representative INPUT data into Snowflake for inspection / manual testing.

Inserts one worked example per ORC into CUSTOMER, ACCOUNT and ACCOUNT_PARTICIPANT
(FDIC_PART370.CORE), so the calculation inputs can be browsed in Snowsight. The
balances mirror the labeled eval-suite examples, so the expected coverage is
easy to reason about.

Idempotent: every seeded row uses a customer_id / account prefix of "SF-" and is
deleted before re-insertion, so the script can be re-run safely.

Usage (from backend/):
    python scripts/seed_snowflake_inputs.py
    python scripts/seed_snowflake_inputs.py --dry-run   # print plan, no connection

Note: the BUS eligibility flags (independent_activity, sole_proprietorship) are
model-level fields and are NOT columns on the Snowflake ACCOUNT table, so the BUS
sole-prop / non-independent branches are represented here only by their member
roster in ACCOUNT_PARTICIPANT. The standard separate-entity BUS case is seeded.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.directory import (  # noqa: E402
    SAMPLE_ACCOUNTS, SAMPLE_CUSTOMERS, SAMPLE_PARTICIPANTS,
)

# Build Snowflake INSERT tuples from the canonical sample directory (single
# source of truth shared with app/db/directory.py's local fallback).
CUSTOMERS = [(c["customer_id"], c["first_name"], c["last_name"], c["ssn_tin"],
              c["customer_type"], c.get("address", ""), c.get("email", ""),
              c.get("phone", "")) for c in SAMPLE_CUSTOMERS]

ACCOUNTS = [(a["account_number"], a["customer_id"], a["orc"], a["product_type"],
             str(a["balance"]), str(a["accrued_interest"])) for a in SAMPLE_ACCOUNTS]

PARTICIPANTS = [(p["account_number"], p["party_id"], p["role"], p["name"],
                 str(p.get("interest_pct", 0)), str(p["vested_interest"]))
                for p in SAMPLE_PARTICIPANTS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print plan, no connection")
    args = ap.parse_args()

    print(f"Plan: {len(CUSTOMERS)} customers, {len(ACCOUNTS)} accounts, "
          f"{len(PARTICIPANTS)} participants (one worked example per ORC).")
    if args.dry_run:
        for (num, cust, orc, prod, bal, _intr) in ACCOUNTS:
            print(f"  {num:12s} {orc:4s} {prod:4s} ${bal:>9s}  (customer {cust})")
        return 0

    if not settings.snowflake_account:
        print("SNOWFLAKE_ACCOUNT not set in backend/.env — nothing to seed.")
        return 1

    import snowflake.connector
    conn = snowflake.connector.connect(
        account=settings.snowflake_account, user=settings.snowflake_user,
        password=settings.snowflake_password, warehouse=settings.snowflake_warehouse or None,
        role=settings.snowflake_role or None, database=settings.snowflake_database,
        schema=settings.snowflake_schema,
    )
    cur = conn.cursor()
    try:
        # Idempotent: clear prior SF- sample rows (children first for clarity).
        cur.execute("DELETE FROM ACCOUNT_PARTICIPANT WHERE ACCOUNT_NUMBER LIKE 'SF-%'")
        cur.execute("DELETE FROM ACCOUNT WHERE ACCOUNT_NUMBER LIKE 'SF-%'")
        cur.execute("DELETE FROM CUSTOMER WHERE CUSTOMER_ID LIKE 'SF-%'")

        cur.executemany(
            "INSERT INTO CUSTOMER (CUSTOMER_ID, FIRST_NAME, LAST_NAME, SSN_TIN, "
            "CUSTOMER_TYPE, ADDRESS, EMAIL, PHONE) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", CUSTOMERS)
        acct_rows = [(num, cust, prod, bal, intr, orc)
                     for (num, cust, orc, prod, bal, intr) in ACCOUNTS]
        cur.executemany(
            "INSERT INTO ACCOUNT (ACCOUNT_NUMBER, CUSTOMER_ID, PRODUCT_TYPE, BALANCE, "
            "ACCRUED_INTEREST, ORC) VALUES (%s, %s, %s, %s, %s, %s)", acct_rows)
        cur.executemany(
            "INSERT INTO ACCOUNT_PARTICIPANT (ACCOUNT_NUMBER, PARTY_ID, PARTY_ROLE, NAME, "
            "INTEREST_PCT, VESTED_INTEREST) VALUES (%s, %s, %s, %s, %s, %s)", PARTICIPANTS)

        for t in ("CUSTOMER", "ACCOUNT", "ACCOUNT_PARTICIPANT"):
            cur.execute(f"SELECT COUNT(*) FROM {t} WHERE "
                        + ("ACCOUNT_NUMBER" if t != "CUSTOMER" else "CUSTOMER_ID") + " LIKE 'SF-%'")
            print(f"  {t:20s} SF- rows = {cur.fetchone()[0]}")
        print("\nSeeded sample input data into FDIC_PART370.CORE (prefix 'SF-').")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
