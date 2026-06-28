"""Agents 1 & 4: FDIC Rules retrieval + ORC Classification."""

from __future__ import annotations

from collections import defaultdict

from ...domain.constants import ORC, ORC_CONFIG
from ...rag.retriever import retriever
from ..state import DeterminationState


def fdic_rules_agent(state: DeterminationState) -> dict:
    """Retrieve Part 370 rules for every ORC present in the request (RAG)."""
    orcs = {_effective_orc(a) for a in state["accounts"]}
    rules = {orc.value: retriever.applicable_rules(orc) for orc in orcs}
    return {"applicable_rules": rules,
            "trace": [{"agent": "fdic_rules", "orcs": [o.value for o in orcs]}]}


def _effective_orc(a) -> ORC:
    """Resolve the ORC actually used for coverage.

    A BUS sole proprietorship is not a separate entity under 12 CFR 330.11; its
    funds are insured as the owner's single-ownership (SGL) deposits, so it is
    reclassified to SGL and aggregates with the owner's other single accounts.
    """
    if a.orc == ORC.BUS and a.sole_proprietorship:
        return ORC.SGL
    return a.orc


def orc_classification_agent(state: DeterminationState) -> dict:
    """Assign ORC + build aggregation groups.

    Accounts are grouped by (ORC family, depositor) so the engine receives the
    correct aggregation set. The depositor key is the customer_id, but ORCs that
    aggregate per owner/custodian use the owner set as the secondary key.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    evidence: dict[str, dict] = {}
    for a in state["accounts"]:
        effective = _effective_orc(a)
        family = ORC_CONFIG[effective]["aggregates_with"][0].value
        key = f"{family}:{a.customer_id}"
        groups[key].append(a.account_number)
        reclassified = effective is not a.orc
        reason = (f"Account product/ownership matches {a.orc.value} criteria; "
                  f"aggregates with other {family} deposits of {a.customer_id}.")
        if reclassified:
            reason = (f"BUS sole proprietorship reclassified to {effective.value}: "
                      f"insured as the owner's single-ownership funds and aggregated "
                      f"with their other {family} deposits (12 CFR 330.11).")
        evidence[a.account_number] = {
            "assigned_orc": effective.value,
            "declared_orc": a.orc.value,
            "aggregation_group": key,
            "shape": ORC_CONFIG[effective]["shape"].value,
            "reason": reason,
        }
    return {"orc_classification": {"groups": dict(groups), "evidence": evidence},
            "trace": [{"agent": "orc_classification", "groups": len(groups)}]}
