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

# (account_number, orc, product, balance, accrued_interest) — expected coverage noted.
ACCOUNTS = [
    # account,      orc,    product, balance,  interest, note
    ("SF-SGL-A1",  "SGL",  "DDA",  "350000", "0",   "single owner, $250k insured / $100k uninsured"),
    ("SF-JNT-A1",  "JNT",  "SAV",  "500000", "0",   "2 owners -> $500k limit, fully insured"),
    ("SF-TST-A1",  "TST",  "MMA",  "600000", "0",   "1 grantor x 2 benes -> $500k limit"),
    ("SF-CRA-A1",  "CRA",  "CDS",  "300000", "0",   "retiree IRA, $250k insured"),
    ("SF-EBP-A1",  "EBP",  "DDA",  "500000", "0",   "2 plan participants pass-through"),
    ("SF-BUS-A1",  "BUS",  "DDA",  "400000", "0",   "separate entity, $250k insured / $150k uninsured"),
    ("SF-GOV1-A1", "GOV1", "SAV",  "450000", "0",   "in-state time & savings, one SMDIA"),
    ("SF-GOV2-A1", "GOV2", "DDA",  "400000", "0",   "in-state demand, one SMDIA"),
    ("SF-GOV3-A1", "GOV3", "DDA",  "300000", "0",   "out-of-state public unit, one SMDIA"),
    ("SF-MSA-A1",  "MSA",  "DDA",  "350000", "0",   "2 mortgagors pass-through (P&I)"),
    ("SF-PBA-A1",  "PBA",  "DDA",  "350000", "0",   "2 bondholders pass-through"),
    ("SF-DIT-A1",  "DIT",  "MMA",  "260000", "0",   "1 trust beneficiary"),
    ("SF-ANC-A1",  "ANC",  "MMA",  "600000", "0",   "2 annuitants pass-through"),
    ("SF-BIA-A1",  "BIA",  "SAV",  "150000", "0",   "1 Native American beneficiary"),
    ("SF-DOE-A1",  "DOE",  "DDA",  "275000", "0",   "IDI DOE program, one SMDIA"),
]

# customer_id == account's ORC sample customer (1:1 here for clarity).
CUSTOMERS = [
    # customer_id, first, last, ssn_tin, type
    ("SF-SGL",  "Jane",  "Doe",      "123-45-6789", "INDIVIDUAL"),
    ("SF-JNT",  "John",  "Smith",    "234-56-7890", "JOINT"),
    ("SF-TST",  "Mary",  "Grantor",  "345-67-8901", "TRUST"),
    ("SF-CRA",  "Robert","Retiree",  "456-78-9012", "INDIVIDUAL"),
    ("SF-EBP",  "Acme",  "Plan",     "12-3456701",  "PLAN"),
    ("SF-BUS",  "Acme",  "Corp",     "12-3456702",  "BUSINESS"),
    ("SF-GOV1", "City",  "Treasury", "12-3456703",  "GOVERNMENT"),
    ("SF-GOV2", "City",  "Treasury", "12-3456704",  "GOVERNMENT"),
    ("SF-GOV3", "State", "Treasury", "12-3456705",  "GOVERNMENT"),
    ("SF-MSA",  "Home",  "Servicer", "12-3456706",  "FIDUCIARY"),
    ("SF-PBA",  "Muni",  "Issuer",   "12-3456707",  "GOVERNMENT"),
    ("SF-DIT",  "Trust", "IDI",      "12-3456708",  "FIDUCIARY"),
    ("SF-ANC",  "Life",  "Insurer",  "12-3456709",  "BUSINESS"),
    ("SF-BIA",  "BIA",   "Custodian","12-3456710",  "FIDUCIARY"),
    ("SF-DOE",  "DOE",   "Program",  "12-3456711",  "BUSINESS"),
]

# (account_number, party_id, role, name, vested_interest)
PARTICIPANTS = [
    ("SF-JNT-A1",  "P1", "OWNER",        "John Smith",   "0"),
    ("SF-JNT-A1",  "P2", "OWNER",        "Jane Smith",   "0"),
    ("SF-TST-A1",  "G1", "OWNER",        "Mary Grantor", "0"),
    ("SF-TST-A1",  "B1", "BENEFICIARY",  "Child A",      "0"),
    ("SF-TST-A1",  "B2", "BENEFICIARY",  "Child B",      "0"),
    ("SF-EBP-A1",  "E1", "PARTICIPANT",  "Employee A",   "300000"),
    ("SF-EBP-A1",  "E2", "PARTICIPANT",  "Employee B",   "200000"),
    # BUS member roster (relevant to the non-independent / pass-through branch)
    ("SF-BUS-A1",  "M1", "OWNER",        "Partner Alice","0"),
    ("SF-BUS-A1",  "M2", "OWNER",        "Partner Bob",  "0"),
    ("SF-MSA-A1",  "R1", "PARTICIPANT",  "Mortgagor A",  "250000"),
    ("SF-MSA-A1",  "R2", "PARTICIPANT",  "Mortgagor B",  "100000"),
    ("SF-PBA-A1",  "H1", "PARTICIPANT",  "Bondholder A", "250000"),
    ("SF-PBA-A1",  "H2", "PARTICIPANT",  "Bondholder B", "100000"),
    ("SF-DIT-A1",  "D1", "BENEFICIARY",  "Trust Bene",   "0"),
    ("SF-ANC-A1",  "N1", "BENEFICIARY",  "Annuitant A",  "0"),
    ("SF-ANC-A1",  "N2", "BENEFICIARY",  "Annuitant B",  "0"),
    ("SF-BIA-A1",  "I1", "BENEFICIARY",  "Tribe Member", "0"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print plan, no connection")
    args = ap.parse_args()

    print(f"Plan: {len(CUSTOMERS)} customers, {len(ACCOUNTS)} accounts, "
          f"{len(PARTICIPANTS)} participants (one worked example per ORC).")
    if args.dry_run:
        for a in ACCOUNTS:
            print(f"  {a[0]:12s} {a[1]:4s} ${a[3]:>9s}  — {a[5]}")
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
            "INSERT INTO CUSTOMER (CUSTOMER_ID, FIRST_NAME, LAST_NAME, SSN_TIN, CUSTOMER_TYPE) "
            "VALUES (%s, %s, %s, %s, %s)", CUSTOMERS)
        # account_number -> customer_id by stripping the trailing "-A1"
        acct_rows = [(num, num.rsplit("-", 1)[0], prod, bal, intr, orc)
                     for (num, orc, prod, bal, intr, _note) in ACCOUNTS]
        cur.executemany(
            "INSERT INTO ACCOUNT (ACCOUNT_NUMBER, CUSTOMER_ID, PRODUCT_TYPE, BALANCE, "
            "ACCRUED_INTEREST, ORC) VALUES (%s, %s, %s, %s, %s, %s)", acct_rows)
        cur.executemany(
            "INSERT INTO ACCOUNT_PARTICIPANT (ACCOUNT_NUMBER, PARTY_ID, PARTY_ROLE, NAME, "
            "VESTED_INTEREST) VALUES (%s, %s, %s, %s, %s)", PARTICIPANTS)

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
