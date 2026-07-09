"""Customer/account directory — search + auto-populate detail.

Forces the local (in-code sample) path so the test is deterministic regardless
of whether Snowflake is configured in the environment.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import directory
from app.main import app


@pytest.fixture(autouse=True)
def _force_local(monkeypatch):
    monkeypatch.setattr(directory, "_use_snowflake", lambda: False)


def test_search_customers_matches_id_and_name():
    assert directory.search_customers("SF-JNT")[0]["customer_id"] == "SF-JNT"
    names = {c["customer_id"] for c in directory.search_customers("treasury")}
    assert {"SF-GOV1", "SF-GOV2", "SF-GOV3"} <= names
    # Empty query returns the full (capped) list.
    assert len(directory.search_customers("", limit=100)) == len(directory.SAMPLE_CUSTOMERS)


def test_search_customers_by_ssn_tin():
    # SF-SGL has SSN 123-45-6789.
    assert directory.search_customers("123-45-6789")[0]["customer_id"] == "SF-SGL"


def test_search_accounts_matches_orc():
    accts = directory.search_accounts("TST")
    assert accts and accts[0]["account_number"] == "SF-TST-A1"
    assert accts[0]["balance"] > 2_000_000  # seeded > $2M for a real insured/uninsured split


def test_customer_detail_includes_demographics():
    cust = directory.get_customer_detail("SF-SGL")["customer"]
    assert cust["address"] and cust["email"] and cust["phone"]


def test_customer_detail_shapes_parties():
    detail = directory.get_customer_detail("SF-TST")
    assert detail["customer"]["customer_type"] == "TRUST"
    acct = detail["accounts"][0]
    assert acct["orc"] == "TST"
    assert {b["name"] for b in acct["beneficiaries"]} == {"Child A", "Child B"}
    assert [o["name"] for o in acct["owners"]] == ["Mary Grantor"]


def test_customer_detail_missing_returns_none():
    assert directory.get_customer_detail("DOES-NOT-EXIST") is None


def test_endpoints(monkeypatch):
    monkeypatch.setattr(directory, "_use_snowflake", lambda: False)
    c = TestClient(app)
    assert c.get("/api/v1/customers/search", params={"q": "jane"}).json()[0]["customer_id"] == "SF-SGL"
    d = c.get("/api/v1/customers/SF-JNT").json()
    assert [o["name"] for o in d["accounts"][0]["owners"]] == ["John Smith", "Jane Smith"]
    assert c.get("/api/v1/accounts/search", params={"q": "GOV1"}).json()[0]["orc"] == "GOV1"
    assert c.get("/api/v1/customers/NOPE").status_code == 404
