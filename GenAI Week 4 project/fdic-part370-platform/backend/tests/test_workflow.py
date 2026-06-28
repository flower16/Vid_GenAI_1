"""End-to-end workflow + LangSmith-style eval dataset tests."""

from decimal import Decimal

from app.agents.graph import run_determination
from app.domain.constants import ORC, CustomerType
from app.domain.models import Account, Customer, DeterminationRequest, Owner
from app.evals.langsmith_evals import evaluate_local


def _req(**overrides):
    customer = Customer(customer_id="C1", first_name="Jane", last_name="Doe",
                        ssn_tin="123-45-6789", customer_type=CustomerType.INDIVIDUAL,
                        address="1 Main St", email="j@x.com", phone="555-1234")
    accounts = [Account(account_number="A1", customer_id="C1", orc=ORC.SGL,
                        balance=Decimal("350000"))]
    return DeterminationRequest(customer=customer, accounts=accounts, **overrides)


def test_full_workflow_produces_all_artifacts():
    state = run_determination(_req())
    assert state["coverage_results"][0].insured_amount == Decimal("250000.00")
    assert "customer_file" in state["output_files"]
    assert "account_file" in state["output_files"]
    assert "participant_file" in state["output_files"]
    assert "pending_file" in state["output_files"]
    assert state["summary_report"]["reconciliation"]["reconciles"]
    assert all(e["status"] in ("PASS", "WARNING") for e in state["eval_results"])


def test_missing_ssn_routes_to_pending_reason_a():
    req = _req()
    req.customer.ssn_tin = None
    state = run_determination(req)
    reasons = {d.reason.value for d in state["pending_decisions"] if d.is_pending}
    assert "A" in reasons


def test_iterative_recalculation_clears_pending():
    # First pass: AR data not received → pending; second pass clears it.
    req = _req(alt_recordkeeping_received=False)
    s1 = run_determination(req)
    assert any(d.is_pending for d in s1["pending_decisions"])
    req.alt_recordkeeping_received = True
    s2 = run_determination(req)
    ar_reasons = {d.reason.value for d in s2["pending_decisions"]
                  if d.is_pending and d.reason and d.reason.value.startswith("AR")}
    assert not ar_reasons


def test_bus_sole_proprietorship_reclassified_to_sgl():
    # A BUS sole proprietorship is not a separate entity: it is insured as the
    # owner's single-ownership (SGL) funds and aggregates with their SGL deposits.
    customer = Customer(customer_id="C1", first_name="Jane", last_name="Doe",
                        ssn_tin="123-45-6789", customer_type=CustomerType.BUSINESS,
                        address="1 Main St", email="j@x.com", phone="555-1234")
    accounts = [
        Account(account_number="SP1", customer_id="C1", orc=ORC.BUS,
                balance=Decimal("150000"), sole_proprietorship=True),
        Account(account_number="SGL1", customer_id="C1", orc=ORC.SGL,
                balance=Decimal("150000")),
    ]
    state = run_determination(DeterminationRequest(customer=customer, accounts=accounts))
    # Both accounts aggregate under SGL ($300k) → one $250k cap, no separate BUS row.
    orcs = {r.orc for r in state["coverage_results"]}
    assert orcs == {ORC.SGL}
    sgl = next(r for r in state["coverage_results"] if r.orc == ORC.SGL)
    assert sgl.aggregated_pi == Decimal("300000.00")
    assert sgl.insured_amount == Decimal("250000.00")


def test_local_eval_suite():
    dataset = [
        {"name": "sgl_over_limit",
         "inputs": _req().model_dump(mode="json"),
         "expected_insured": 250000, "expect_input_fail": False},
        {"name": "joint_full",
         "inputs": DeterminationRequest(
             customer=_req().customer,
             accounts=[Account(account_number="J1", customer_id="C1", orc=ORC.JNT,
                               balance=Decimal("500000"),
                               owners=[Owner(party_id="P1", name="A"),
                                       Owner(party_id="P2", name="B")])],
         ).model_dump(mode="json"),
         "expected_insured": 500000, "expect_input_fail": False},
    ]
    report = evaluate_local(dataset)
    assert report["passed"] == report["total"]
