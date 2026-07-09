"""
Customer / account directory — read side over Snowflake.

Powers the UI's "load from Snowflake" search: find customers and accounts that
already exist in FDIC_PART370.CORE and return them shaped like the domain models
so the frontend can auto-populate the determination forms.

Graceful degradation (consistent with the rest of the platform): when Snowflake
is not configured, the same queries run against an in-code sample directory
(`SAMPLE_*` below) — the canonical seed data that `scripts/seed_snowflake_inputs.py`
also loads into Snowflake — so the feature works end-to-end in local/demo mode.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Canonical sample directory (one worked example per ORC). Single source of
# truth shared with scripts/seed_snowflake_inputs.py so the local fallback and
# the seeded Snowflake rows are identical.
# --------------------------------------------------------------------------- #
SAMPLE_CUSTOMERS: list[dict] = [
    {"customer_id": "SF-SGL", "first_name": "Jane", "last_name": "Doe", "ssn_tin": "123-45-6789", "customer_type": "INDIVIDUAL"},
    {"customer_id": "SF-JNT", "first_name": "John", "last_name": "Smith", "ssn_tin": "234-56-7890", "customer_type": "JOINT"},
    {"customer_id": "SF-TST", "first_name": "Mary", "last_name": "Grantor", "ssn_tin": "345-67-8901", "customer_type": "TRUST"},
    {"customer_id": "SF-CRA", "first_name": "Robert", "last_name": "Retiree", "ssn_tin": "456-78-9012", "customer_type": "INDIVIDUAL"},
    {"customer_id": "SF-EBP", "first_name": "Acme", "last_name": "Plan", "ssn_tin": "12-3456701", "customer_type": "PLAN"},
    {"customer_id": "SF-BUS", "first_name": "Acme", "last_name": "Corp", "ssn_tin": "12-3456702", "customer_type": "BUSINESS"},
    {"customer_id": "SF-GOV1", "first_name": "City", "last_name": "Treasury", "ssn_tin": "12-3456703", "customer_type": "GOVERNMENT"},
    {"customer_id": "SF-GOV2", "first_name": "City", "last_name": "Treasury", "ssn_tin": "12-3456704", "customer_type": "GOVERNMENT"},
    {"customer_id": "SF-GOV3", "first_name": "State", "last_name": "Treasury", "ssn_tin": "12-3456705", "customer_type": "GOVERNMENT"},
    {"customer_id": "SF-MSA", "first_name": "Home", "last_name": "Servicer", "ssn_tin": "12-3456706", "customer_type": "FIDUCIARY"},
    {"customer_id": "SF-PBA", "first_name": "Muni", "last_name": "Issuer", "ssn_tin": "12-3456707", "customer_type": "GOVERNMENT"},
    {"customer_id": "SF-DIT", "first_name": "Trust", "last_name": "IDI", "ssn_tin": "12-3456708", "customer_type": "FIDUCIARY"},
    {"customer_id": "SF-ANC", "first_name": "Life", "last_name": "Insurer", "ssn_tin": "12-3456709", "customer_type": "BUSINESS"},
    {"customer_id": "SF-BIA", "first_name": "BIA", "last_name": "Custodian", "ssn_tin": "12-3456710", "customer_type": "FIDUCIARY"},
    {"customer_id": "SF-DOE", "first_name": "DOE", "last_name": "Program", "ssn_tin": "12-3456711", "customer_type": "BUSINESS"},
]

# account_number, customer_id, product_type, balance, accrued_interest, orc
SAMPLE_ACCOUNTS: list[dict] = [
    {"account_number": "SF-SGL-A1", "customer_id": "SF-SGL", "product_type": "DDA", "balance": 350000, "accrued_interest": 0, "orc": "SGL"},
    {"account_number": "SF-JNT-A1", "customer_id": "SF-JNT", "product_type": "SAV", "balance": 500000, "accrued_interest": 0, "orc": "JNT"},
    {"account_number": "SF-TST-A1", "customer_id": "SF-TST", "product_type": "MMA", "balance": 600000, "accrued_interest": 0, "orc": "TST"},
    {"account_number": "SF-CRA-A1", "customer_id": "SF-CRA", "product_type": "CDS", "balance": 300000, "accrued_interest": 0, "orc": "CRA"},
    {"account_number": "SF-EBP-A1", "customer_id": "SF-EBP", "product_type": "DDA", "balance": 500000, "accrued_interest": 0, "orc": "EBP"},
    {"account_number": "SF-BUS-A1", "customer_id": "SF-BUS", "product_type": "DDA", "balance": 400000, "accrued_interest": 0, "orc": "BUS"},
    {"account_number": "SF-GOV1-A1", "customer_id": "SF-GOV1", "product_type": "SAV", "balance": 450000, "accrued_interest": 0, "orc": "GOV1"},
    {"account_number": "SF-GOV2-A1", "customer_id": "SF-GOV2", "product_type": "DDA", "balance": 400000, "accrued_interest": 0, "orc": "GOV2"},
    {"account_number": "SF-GOV3-A1", "customer_id": "SF-GOV3", "product_type": "DDA", "balance": 300000, "accrued_interest": 0, "orc": "GOV3"},
    {"account_number": "SF-MSA-A1", "customer_id": "SF-MSA", "product_type": "DDA", "balance": 350000, "accrued_interest": 0, "orc": "MSA"},
    {"account_number": "SF-PBA-A1", "customer_id": "SF-PBA", "product_type": "DDA", "balance": 350000, "accrued_interest": 0, "orc": "PBA"},
    {"account_number": "SF-DIT-A1", "customer_id": "SF-DIT", "product_type": "MMA", "balance": 260000, "accrued_interest": 0, "orc": "DIT"},
    {"account_number": "SF-ANC-A1", "customer_id": "SF-ANC", "product_type": "MMA", "balance": 600000, "accrued_interest": 0, "orc": "ANC"},
    {"account_number": "SF-BIA-A1", "customer_id": "SF-BIA", "product_type": "SAV", "balance": 150000, "accrued_interest": 0, "orc": "BIA"},
    {"account_number": "SF-DOE-A1", "customer_id": "SF-DOE", "product_type": "DDA", "balance": 275000, "accrued_interest": 0, "orc": "DOE"},
]

# account_number, party_id, role (OWNER|BENEFICIARY|PARTICIPANT), name, interest_pct, vested_interest
SAMPLE_PARTICIPANTS: list[dict] = [
    {"account_number": "SF-JNT-A1", "party_id": "P1", "role": "OWNER", "name": "John Smith", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-JNT-A1", "party_id": "P2", "role": "OWNER", "name": "Jane Smith", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-TST-A1", "party_id": "G1", "role": "OWNER", "name": "Mary Grantor", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-TST-A1", "party_id": "B1", "role": "BENEFICIARY", "name": "Child A", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-TST-A1", "party_id": "B2", "role": "BENEFICIARY", "name": "Child B", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-EBP-A1", "party_id": "E1", "role": "PARTICIPANT", "name": "Employee A", "interest_pct": 0, "vested_interest": 300000},
    {"account_number": "SF-EBP-A1", "party_id": "E2", "role": "PARTICIPANT", "name": "Employee B", "interest_pct": 0, "vested_interest": 200000},
    {"account_number": "SF-BUS-A1", "party_id": "M1", "role": "OWNER", "name": "Partner Alice", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-BUS-A1", "party_id": "M2", "role": "OWNER", "name": "Partner Bob", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-MSA-A1", "party_id": "R1", "role": "PARTICIPANT", "name": "Mortgagor A", "interest_pct": 0, "vested_interest": 250000},
    {"account_number": "SF-MSA-A1", "party_id": "R2", "role": "PARTICIPANT", "name": "Mortgagor B", "interest_pct": 0, "vested_interest": 100000},
    {"account_number": "SF-PBA-A1", "party_id": "H1", "role": "PARTICIPANT", "name": "Bondholder A", "interest_pct": 0, "vested_interest": 250000},
    {"account_number": "SF-PBA-A1", "party_id": "H2", "role": "PARTICIPANT", "name": "Bondholder B", "interest_pct": 0, "vested_interest": 100000},
    {"account_number": "SF-DIT-A1", "party_id": "D1", "role": "BENEFICIARY", "name": "Trust Bene", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-ANC-A1", "party_id": "N1", "role": "BENEFICIARY", "name": "Annuitant A", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-ANC-A1", "party_id": "N2", "role": "BENEFICIARY", "name": "Annuitant B", "interest_pct": 0, "vested_interest": 0},
    {"account_number": "SF-BIA-A1", "party_id": "I1", "role": "BENEFICIARY", "name": "Tribe Member", "interest_pct": 0, "vested_interest": 0},
]


# --------------------------------------------------------------------------- #
# Shaping helpers
# --------------------------------------------------------------------------- #
def _shape_account(acct: dict, participants: list[dict]) -> dict:
    """Return an Account-shaped dict (owners/beneficiaries/participants split)."""
    owners, benes, parts = [], [], []
    for p in participants:
        if p["account_number"] != acct["account_number"]:
            continue
        role = (p.get("role") or "").upper()
        if role == "OWNER":
            owners.append({"party_id": p["party_id"], "name": p.get("name", ""),
                           "ownership_pct": float(p.get("interest_pct") or 0)})
        elif role == "BENEFICIARY":
            benes.append({"party_id": p["party_id"], "name": p.get("name", ""),
                          "interest_pct": float(p.get("interest_pct") or 0)})
        elif role == "PARTICIPANT":
            parts.append({"party_id": p["party_id"], "name": p.get("name", ""),
                          "vested_interest": float(p.get("vested_interest") or 0)})
    return {
        "account_number": acct["account_number"], "customer_id": acct["customer_id"],
        "product_type": acct.get("product_type") or "DDA",
        "balance": float(acct.get("balance") or 0),
        "accrued_interest": float(acct.get("accrued_interest") or 0),
        "hold_amount": float(acct.get("hold_amount") or 0),
        "orc": acct.get("orc") or "SGL",
        "owners": owners, "beneficiaries": benes, "participants": parts,
        # Model-only BUS flags aren't stored in Snowflake; default them.
        "independent_activity": None, "sole_proprietorship": False,
    }


def _use_snowflake() -> bool:
    return bool(settings.snowflake_account and settings.snowflake_user
               and settings.snowflake_password)


# --------------------------------------------------------------------------- #
# Public API — Snowflake-first, local fallback
# --------------------------------------------------------------------------- #
def search_customers(q: str, limit: int = 10) -> list[dict]:
    if _use_snowflake():
        try:
            return _sf_search_customers(q, limit)
        except Exception as exc:  # pragma: no cover - external
            logger.warning("Snowflake customer search failed, using local: %s", exc)
    return _local_search_customers(q, limit)


def search_accounts(q: str, limit: int = 10) -> list[dict]:
    if _use_snowflake():
        try:
            return _sf_search_accounts(q, limit)
        except Exception as exc:  # pragma: no cover - external
            logger.warning("Snowflake account search failed, using local: %s", exc)
    return _local_search_accounts(q, limit)


def get_customer_detail(customer_id: str) -> Optional[dict]:
    """{'customer': {...}, 'accounts': [Account-shaped, ...]} or None."""
    if _use_snowflake():
        try:
            return _sf_customer_detail(customer_id)
        except Exception as exc:  # pragma: no cover - external
            logger.warning("Snowflake customer detail failed, using local: %s", exc)
    return _local_customer_detail(customer_id)


# ---- Local (in-code) implementation ---------------------------------------- #
def _match(text: str, q: str) -> bool:
    return q.lower() in (text or "").lower()


def _local_search_customers(q: str, limit: int) -> list[dict]:
    out = []
    for c in SAMPLE_CUSTOMERS:
        hay = f"{c['customer_id']} {c['first_name']} {c['last_name']} {c['customer_type']}"
        if not q or _match(hay, q):
            n = sum(1 for a in SAMPLE_ACCOUNTS if a["customer_id"] == c["customer_id"])
            out.append({"customer_id": c["customer_id"], "first_name": c["first_name"],
                        "last_name": c["last_name"], "customer_type": c["customer_type"],
                        "account_count": n})
        if len(out) >= limit:
            break
    return out


def _local_search_accounts(q: str, limit: int) -> list[dict]:
    out = []
    for a in SAMPLE_ACCOUNTS:
        hay = f"{a['account_number']} {a['customer_id']} {a['orc']} {a['product_type']}"
        if not q or _match(hay, q):
            out.append({"account_number": a["account_number"], "customer_id": a["customer_id"],
                        "orc": a["orc"], "product_type": a["product_type"],
                        "balance": float(a["balance"])})
        if len(out) >= limit:
            break
    return out


def _local_customer_detail(customer_id: str) -> Optional[dict]:
    cust = next((c for c in SAMPLE_CUSTOMERS if c["customer_id"] == customer_id), None)
    if not cust:
        return None
    accts = [_shape_account(a, SAMPLE_PARTICIPANTS)
             for a in SAMPLE_ACCOUNTS if a["customer_id"] == customer_id]
    customer = {"customer_id": cust["customer_id"], "first_name": cust["first_name"],
                "last_name": cust["last_name"], "ssn_tin": cust["ssn_tin"],
                "customer_type": cust["customer_type"], "address": "", "email": "", "phone": ""}
    return {"customer": customer, "accounts": accts}


# ---- Snowflake implementation ---------------------------------------------- #
def _connect():  # pragma: no cover - external
    import snowflake.connector
    return snowflake.connector.connect(
        account=settings.snowflake_account, user=settings.snowflake_user,
        password=settings.snowflake_password, warehouse=settings.snowflake_warehouse or None,
        role=settings.snowflake_role or None, database=settings.snowflake_database,
        schema=settings.snowflake_schema, login_timeout=8)


def _sf_search_customers(q: str, limit: int) -> list[dict]:  # pragma: no cover - external
    like = f"%{q}%"
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT c.CUSTOMER_ID, c.FIRST_NAME, c.LAST_NAME, c.CUSTOMER_TYPE, "
            "  (SELECT COUNT(*) FROM ACCOUNT a WHERE a.CUSTOMER_ID = c.CUSTOMER_ID) "
            "FROM CUSTOMER c "
            "WHERE c.CUSTOMER_ID ILIKE %s OR c.FIRST_NAME ILIKE %s OR c.LAST_NAME ILIKE %s "
            "ORDER BY c.CUSTOMER_ID LIMIT %s",
            (like, like, like, limit))
        return [{"customer_id": r[0], "first_name": r[1], "last_name": r[2],
                 "customer_type": r[3], "account_count": int(r[4] or 0)} for r in cur.fetchall()]
    finally:
        conn.close()


def _sf_search_accounts(q: str, limit: int) -> list[dict]:  # pragma: no cover - external
    like = f"%{q}%"
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ACCOUNT_NUMBER, CUSTOMER_ID, ORC, PRODUCT_TYPE, BALANCE FROM ACCOUNT "
            "WHERE ACCOUNT_NUMBER ILIKE %s OR CUSTOMER_ID ILIKE %s OR ORC ILIKE %s "
            "ORDER BY ACCOUNT_NUMBER LIMIT %s", (like, like, like, limit))
        return [{"account_number": r[0], "customer_id": r[1], "orc": r[2],
                 "product_type": r[3], "balance": float(r[4] or 0)} for r in cur.fetchall()]
    finally:
        conn.close()


def _sf_customer_detail(customer_id: str) -> Optional[dict]:  # pragma: no cover - external
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT CUSTOMER_ID, FIRST_NAME, LAST_NAME, SSN_TIN, CUSTOMER_TYPE, "
                    "ADDRESS, EMAIL, PHONE FROM CUSTOMER WHERE CUSTOMER_ID = %s", (customer_id,))
        row = cur.fetchone()
        if not row:
            return None
        customer = {"customer_id": row[0], "first_name": row[1], "last_name": row[2],
                    "ssn_tin": row[3], "customer_type": row[4], "address": row[5] or "",
                    "email": row[6] or "", "phone": row[7] or ""}
        cur.execute("SELECT ACCOUNT_NUMBER, CUSTOMER_ID, PRODUCT_TYPE, BALANCE, "
                    "ACCRUED_INTEREST, HOLD_AMOUNT, ORC FROM ACCOUNT WHERE CUSTOMER_ID = %s "
                    "ORDER BY ACCOUNT_NUMBER", (customer_id,))
        acct_rows = [{"account_number": r[0], "customer_id": r[1], "product_type": r[2],
                      "balance": r[3], "accrued_interest": r[4], "hold_amount": r[5],
                      "orc": r[6]} for r in cur.fetchall()]
        parts: list[dict] = []
        if acct_rows:
            nums = [a["account_number"] for a in acct_rows]
            placeholders = ",".join(["%s"] * len(nums))
            cur.execute(f"SELECT ACCOUNT_NUMBER, PARTY_ID, PARTY_ROLE, NAME, INTEREST_PCT, "
                        f"VESTED_INTEREST FROM ACCOUNT_PARTICIPANT "
                        f"WHERE ACCOUNT_NUMBER IN ({placeholders})", nums)
            parts = [{"account_number": r[0], "party_id": r[1], "role": r[2], "name": r[3],
                      "interest_pct": r[4], "vested_interest": r[5]} for r in cur.fetchall()]
        accounts = [_shape_account(a, parts) for a in acct_rows]
        return {"customer": customer, "accounts": accounts}
    finally:
        conn.close()
