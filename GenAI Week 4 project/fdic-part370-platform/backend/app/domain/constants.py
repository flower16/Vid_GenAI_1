"""
FDIC Part 370 regulatory constants and code tables.

SOURCE OF TRUTH NOTE
--------------------
The values below encode 12 CFR Part 370 and the FDIC IT Functional / Data
Submission Guide. They are intentionally centralized so that when the official
FDIC guide is provided, an analyst can reconcile every number in ONE place
without touching calculation logic. Anything marked `# CONFIRM` should be
validated against the authoritative guide before a production filing.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

# ---------------------------------------------------------------------------
# Core coverage constant
# ---------------------------------------------------------------------------
# Standard Maximum Deposit Insurance Amount (SMDIA). $250,000 since 2008.
SMDIA: Decimal = Decimal("250000.00")


class ORC(str, Enum):
    """Ownership Right and Capacity codes supported by the platform."""

    # Definitions per FDIC IT Functional Guide v3.0 (June 2023), §4.1 & App. A.
    SGL = "SGL"     # Single accounts
    JNT = "JNT"     # Joint accounts
    TST = "TST"     # Trust accounts (combined REV+IRR per §330.10, eff. 2024-04-01)
    CRA = "CRA"     # Certain retirement accounts (IRA, self-directed)
    EBP = "EBP"     # Employee benefit plan accounts (pass-through)
    BUS = "BUS"     # Business / organization (corp / partnership / unincorporated)
    GOV1 = "GOV1"   # Public unit — in-state, time & savings deposits
    GOV2 = "GOV2"   # Public unit — in-state, demand deposits
    GOV3 = "GOV3"   # Public unit — IDI located outside the public unit's state
    MSA = "MSA"     # Mortgage servicing accounts (principal & interest)
    PBA = "PBA"     # Public bond accounts
    DIT = "DIT"     # Accounts held by an IDI as trustee of an irrevocable trust
    ANC = "ANC"     # Annuity contract accounts
    BIA = "BIA"     # Custodian accounts for American Indians (Bureau of Indian Affairs)
    DOE = "DOE"     # Accounts of an IDI under the DOE Bank Deposit Financial Assistance Program


# ---------------------------------------------------------------------------
# Coverage-limit "shape" per ORC. Drives the calculation engine.
#   PER_OWNER            : limit = unique_owners * SMDIA, each owner capped
#   PER_OWNER_PER_BENE   : trust math (owners * beneficiaries * SMDIA, capped)
#   PER_PARTICIPANT      : pass-through to each participant's vested interest
#   PER_ENTITY           : one SMDIA for the legal entity
#   PER_CUSTODIAN        : public unit, one SMDIA per official custodian/category
#   PER_PRINCIPAL        : MSA pass-through to each mortgagor (P&I)
# ---------------------------------------------------------------------------
class CoverageShape(str, Enum):
    PER_OWNER = "PER_OWNER"
    PER_OWNER_PER_BENE = "PER_OWNER_PER_BENE"
    PER_PARTICIPANT = "PER_PARTICIPANT"
    PER_ENTITY = "PER_ENTITY"
    PER_CUSTODIAN = "PER_CUSTODIAN"
    PER_PRINCIPAL = "PER_PRINCIPAL"


# Per-ORC configuration table. Reconciled to FDIC IT Functional Guide v3.0 §4.1.
# `max_beneficiaries` reflects the §330.10 trust rule effective 2024-04-01
# (≤5 beneficiaries → $1.25M cap per grantor; §4.1.4.4).
#
# GOV1/GOV2/GOV3 each carry one SMDIA per unique (official custodian, public
# unit) combination — the time/savings vs demand split is expressed as separate
# codes (GOV1 vs GOV2), NOT as a 2× multiplier within a single code (§4.1.9).
ORC_CONFIG: dict[ORC, dict] = {
    ORC.SGL:  {"shape": CoverageShape.PER_OWNER, "aggregates_with": [ORC.SGL]},
    ORC.JNT:  {"shape": CoverageShape.PER_OWNER, "aggregates_with": [ORC.JNT]},
    ORC.TST:  {"shape": CoverageShape.PER_OWNER_PER_BENE, "max_beneficiaries": 5,
               "aggregates_with": [ORC.TST]},
    ORC.CRA:  {"shape": CoverageShape.PER_OWNER, "aggregates_with": [ORC.CRA]},
    ORC.EBP:  {"shape": CoverageShape.PER_PARTICIPANT, "aggregates_with": [ORC.EBP],
               "pass_through_source": "participants"},  # plan participants
    ORC.BUS:  {"shape": CoverageShape.PER_ENTITY, "aggregates_with": [ORC.BUS]},
    ORC.GOV1: {"shape": CoverageShape.PER_CUSTODIAN, "aggregates_with": [ORC.GOV1]},
    ORC.GOV2: {"shape": CoverageShape.PER_CUSTODIAN, "aggregates_with": [ORC.GOV2]},
    ORC.GOV3: {"shape": CoverageShape.PER_CUSTODIAN, "aggregates_with": [ORC.GOV3]},
    ORC.MSA:  {"shape": CoverageShape.PER_PRINCIPAL, "aggregates_with": [ORC.MSA],
               "pass_through_source": "participants"},  # mortgagors
    ORC.PBA:  {"shape": CoverageShape.PER_PARTICIPANT, "aggregates_with": [ORC.PBA],
               "pass_through_source": "participants"},  # bondholders
    ORC.DIT:  {"shape": CoverageShape.PER_PARTICIPANT, "aggregates_with": [ORC.DIT],
               "pass_through_source": "beneficiaries"},  # trust fund owners/beneficiaries
    ORC.ANC:  {"shape": CoverageShape.PER_PARTICIPANT, "aggregates_with": [ORC.ANC],
               "pass_through_source": "beneficiaries"},  # annuitants
    ORC.BIA:  {"shape": CoverageShape.PER_PRINCIPAL, "aggregates_with": [ORC.BIA],
               "pass_through_source": "beneficiaries"},  # Native Americans
    ORC.DOE:  {"shape": CoverageShape.PER_ENTITY, "aggregates_with": [ORC.DOE]},
}


class PendingReason(str, Enum):
    """Part 370 Pending File reason codes (IT Functional Guide v3.0, Pending
    File field #2 / Summary Report Table 2)."""

    # I. Records maintained by the bank
    A = "A"          # Agency or custodian
    B = "B"          # Beneficiary
    OI = "OI"        # Official item
    RAC = "RAC"      # Right and capacity code (e.g. joint acct w/o signature card)
    # II. Alternative recordkeeping (§370.4(b))
    ARB = "ARB"      # Direct-obligation (depository org.) brokered deposits
    ARBN = "ARBN"    # Non-direct-obligation (non-depository org.) brokered deposits
    ARCRA = "ARCRA"  # Certain retirement accounts
    AREBP = "AREBP"  # Employee benefit plan accounts
    ARM = "ARM"      # Mortgage servicing for principal & interest payments
    ARO = "ARO"      # Other deposits
    ARTR = "ARTR"    # Trust accounts


# Pending reason groupings for the Summary Report Table 2.
PENDING_BANK_MAINTAINED = [PendingReason.A, PendingReason.B,
                           PendingReason.OI, PendingReason.RAC]
PENDING_ALT_RECORDKEEPING = [PendingReason.ARB, PendingReason.ARBN,
                             PendingReason.ARCRA, PendingReason.AREBP,
                             PendingReason.ARM, PendingReason.ARO, PendingReason.ARTR]


# Customer types recognized for validation
class CustomerType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    JOINT = "JOINT"
    TRUST = "TRUST"
    BUSINESS = "BUSINESS"
    GOVERNMENT = "GOVERNMENT"
    PLAN = "PLAN"            # employee benefit / retirement plan
    FIDUCIARY = "FIDUCIARY"  # bank/broker acting as fiduciary
    ESTATE = "ESTATE"
