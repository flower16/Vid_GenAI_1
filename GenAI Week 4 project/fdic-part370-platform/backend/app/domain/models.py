"""Pydantic domain models shared across agents, API, MCP and file generators."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from .constants import ORC, CustomerType, PendingReason


class Owner(BaseModel):
    """An owner / co-owner of an account (drives PER_OWNER aggregation)."""

    party_id: str
    name: str
    ssn_tin: Optional[str] = None
    ownership_pct: Decimal = Field(default=Decimal("0"))


class Beneficiary(BaseModel):
    party_id: str
    name: str
    interest_pct: Decimal = Field(default=Decimal("0"))


class Participant(BaseModel):
    """EBP / annuity participant or MSA mortgagor (pass-through interest)."""

    party_id: str
    name: str
    vested_interest: Decimal = Field(default=Decimal("0"))


class Customer(BaseModel):
    customer_id: str
    first_name: str = ""
    last_name: str = ""
    ssn_tin: Optional[str] = None
    customer_type: Optional[CustomerType] = None
    address: str = ""
    email: str = ""
    phone: str = ""


class Account(BaseModel):
    account_number: str
    customer_id: str
    product_type: str = "DDA"
    balance: Decimal = Field(default=Decimal("0"))
    accrued_interest: Decimal = Field(default=Decimal("0"))
    hold_amount: Decimal = Field(default=Decimal("0"))
    orc: ORC
    owners: list[Owner] = Field(default_factory=list)
    beneficiaries: list[Beneficiary] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)

    # BUS (12 CFR 330.11) eligibility. `independent_activity` None = unconfirmed
    # (assumed engaged, flagged for review); False = funds pass through to the
    # members. `sole_proprietorship` True = insured as the owner's single
    # ownership (SGL) funds rather than as a separate entity.
    independent_activity: Optional[bool] = None
    sole_proprietorship: bool = False

    @property
    def principal_and_interest(self) -> Decimal:
        """PI = principal balance + accrued interest (the insured amount base)."""
        return Decimal(self.balance) + Decimal(self.accrued_interest)


class DeterminationRequest(BaseModel):
    """Top-level input to the LangGraph workflow."""

    customer: Customer
    accounts: list[Account]
    # Alternative-recordkeeping data may arrive late; recompute when set.
    alt_recordkeeping_received: bool = True


class ValidationFinding(BaseModel):
    code: str
    severity: str  # PASS | WARNING | FAIL
    message: str
    field: Optional[str] = None


class CoverageResult(BaseModel):
    orc: ORC
    aggregated_pi: Decimal
    coverage_limit: Decimal
    insured_amount: Decimal
    uninsured_amount: Decimal
    rationale: str
    accounts_included: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)


class PendingDecision(BaseModel):
    is_pending: bool
    reason: Optional[PendingReason] = None
    account_number: Optional[str] = None
    detail: str = ""


class EvalResult(BaseModel):
    name: str
    status: str  # PASS | FAIL | WARNING
    detail: str = ""
