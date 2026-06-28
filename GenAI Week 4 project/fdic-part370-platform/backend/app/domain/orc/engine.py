"""
FDIC Part 370 ORC calculation engine.

Design: each ORC maps to a `CoverageShape` (see constants.ORC_CONFIG). One
calculator function per shape keeps the regulatory math auditable and testable.
Every result carries a human-readable rationale + structured evidence so the
Insurance Calculation Agent can surface a full evidence chain in the UI.

The engine is intentionally PURE (no I/O). Agents call it; tests pin it.
"""

from __future__ import annotations

from decimal import Decimal

from ..constants import ORC, ORC_CONFIG, SMDIA, CoverageShape
from ..models import Account, CoverageResult


def _q(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


def _unique_owners(accounts: list[Account]) -> set[str]:
    ids: set[str] = set()
    for a in accounts:
        for o in a.owners:
            ids.add(o.party_id)
        if not a.owners:  # single account w/o explicit owner list → the customer
            ids.add(a.customer_id)
    return ids


def _unique_beneficiaries(accounts: list[Account]) -> set[str]:
    ids: set[str] = set()
    for a in accounts:
        for b in a.beneficiaries:
            ids.add(b.party_id)
    return ids


def _aggregate_pi(accounts: list[Account]) -> Decimal:
    return sum((a.principal_and_interest for a in accounts), Decimal("0"))


def _pt_parties(orc: ORC, a: Account) -> list[tuple[str, str, Decimal]]:
    """Pass-through parties (party_id, name, amount) for one account, read from
    the ORC's configured source list (`pass_through_source` in ORC_CONFIG):
    participants for EBP/MSA/PBA (mortgagors, bondholders) or beneficiaries for
    ANC/DIT/BIA (annuitants, trust beneficiaries, Native Americans).
    Beneficiary-sourced parties carry no dollar amount (0 → equal split)."""
    src = ORC_CONFIG[orc].get("pass_through_source", "participants")
    if src == "beneficiaries":
        return [(b.party_id, b.name, Decimal("0")) for b in a.beneficiaries]
    return [(p.party_id, p.name, Decimal(p.vested_interest)) for p in a.participants]


# ---------------------------------------------------------------------------
# Shape calculators
# ---------------------------------------------------------------------------
def _per_owner(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """SGL/JNT/CRA: limit = unique_owners * SMDIA; each owner capped at SMDIA.

    For JNT we also enforce the per-owner cap across all joint accounts: a
    single person's combined share in all joint accounts cannot exceed SMDIA.
    """
    pi = _aggregate_pi(accounts)
    owners = _unique_owners(accounts)
    n = max(len(owners), 1)
    limit = SMDIA * n

    # Per-owner cap: sum of min(owner_share, SMDIA). Also capture display names
    # (party_id -> name) so consumers can show who is insured, not just the ID.
    owner_share: dict[str, Decimal] = {oid: Decimal("0") for oid in owners}
    owner_names: dict[str, str] = {}
    for a in accounts:
        for o in a.owners:
            owner_names.setdefault(o.party_id, o.name)
        share_owners = [o.party_id for o in a.owners] or [a.customer_id]
        per = a.principal_and_interest / Decimal(len(share_owners))
        for oid in share_owners:
            owner_share[oid] += per
    insured = sum((min(s, SMDIA) for s in owner_share.values()), Decimal("0"))
    insured = min(insured, pi)

    return CoverageResult(
        orc=orc,
        aggregated_pi=_q(pi),
        coverage_limit=_q(limit),
        insured_amount=_q(insured),
        uninsured_amount=_q(pi - insured),
        rationale=(
            f"{orc.value}: {n} unique owner(s) × SMDIA ${SMDIA:,.0f} = "
            f"${limit:,.0f} aggregate limit. Each owner's combined share is "
            f"capped at SMDIA before summing insured amount."
        ),
        accounts_included=[a.account_number for a in accounts],
        evidence={"owner_shares": {k: str(_q(v)) for k, v in owner_share.items()},
                  "owner_names": owner_names,
                  "unique_owners": sorted(owners)},
    )


def _per_owner_per_bene(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """TST (revocable trust, 2024 simplified rule).

    Coverage = owners × min(beneficiaries, max_beneficiaries) × SMDIA.
    With the 2024 rule, max 5 beneficiaries → $1.25M cap per grantor.
    """
    cfg = ORC_CONFIG[orc]
    max_b = cfg.get("max_beneficiaries", 5)
    pi = _aggregate_pi(accounts)
    owners = _unique_owners(accounts)
    benes = _unique_beneficiaries(accounts)
    n_owner = max(len(owners), 1)
    n_bene = min(max(len(benes), 1), max_b)
    limit = SMDIA * n_owner * n_bene
    insured = min(pi, limit)

    # Capture display names so consumers can show WHO the grantors and
    # beneficiaries are (party_id -> name), not just the IDs.
    owner_names: dict[str, str] = {}
    bene_names: dict[str, str] = {}
    for a in accounts:
        for o in a.owners:
            owner_names.setdefault(o.party_id, o.name)
        for b in a.beneficiaries:
            bene_names.setdefault(b.party_id, b.name)

    # ---- Per-grantor and per (grantor × beneficiary) allocation ----
    # Contributions are presumed equal across grantors (guide §4.1.5 / §4.1.4.4),
    # so each grantor's trust interest = PI / #grantors. Each grantor is insured
    # to min(#eligible beneficiaries, 5) × SMDIA, and each grantor-beneficiary
    # pair is entitled to up to SMDIA. These breakdowns sum to the totals above.
    grantor_ids = sorted(owners)
    bene_ids = sorted(benes)
    g_share = pi / Decimal(n_owner)
    g_limit = SMDIA * n_bene
    n_b_actual = max(len(bene_ids), 1)

    grantor_coverage: list[dict] = []
    pair_coverage: list[dict] = []
    for gid in grantor_ids:
        gname = owner_names.get(gid, gid)
        g_ins = min(g_share, g_limit)
        grantor_coverage.append({
            "grantor": gname,
            "trust_interest": str(_q(g_share)),
            "coverage_limit": str(_q(g_limit)),
            "insured": str(_q(g_ins)),
            "uninsured": str(_q(g_share - g_ins)),
        })
        # §330.10 (eff. 2024-04-01): only up to `max_b` (5) beneficiaries are
        # insured. The grantor's interest is divided across the ELIGIBLE
        # beneficiaries (first min(#benes, 5)); each such pair is insured up to
        # SMDIA. Beneficiaries beyond the 5th are not counted and get $0.
        n_eligible = min(n_b_actual, max_b)
        per_bene = g_share / Decimal(n_eligible)
        for idx, bid in enumerate(bene_ids):
            counted = idx < max_b
            alloc = per_bene if counted else Decimal("0")
            p_ins = min(alloc, SMDIA)
            pair_coverage.append({
                "grantor": gname,
                "beneficiary": bene_names.get(bid, bid),
                "allocated": str(_q(alloc)),
                "insured": str(_q(p_ins)),
                "uninsured": str(_q(alloc - p_ins)),
                "counted": counted,
            })

    return CoverageResult(
        orc=orc,
        aggregated_pi=_q(pi),
        coverage_limit=_q(limit),
        insured_amount=_q(insured),
        uninsured_amount=_q(pi - insured),
        rationale=(
            f"TST (2024 trust rule): {n_owner} grantor(s) × {n_bene} eligible "
            f"beneficiary(ies) (capped at {max_b}) × SMDIA ${SMDIA:,.0f} = "
            f"${limit:,.0f}. Beneficiaries counted: {len(benes)}."
        ),
        accounts_included=[a.account_number for a in accounts],
        evidence={"owners": sorted(owners), "beneficiaries": sorted(benes),
                  "owner_names": owner_names, "beneficiary_names": bene_names,
                  "beneficiaries_counted": min(len(benes), max_b),
                  "grantors_count": n_owner, "eligible_beneficiaries": n_bene,
                  "grantor_coverage": grantor_coverage,
                  "pair_coverage": pair_coverage},
    )


def _per_participant(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """EBP / ANC / DIT / PBA pass-through: each participant's non-contingent
    (vested) interest is insured to SMDIA.

    The plan/account owner (employer for EBP, insurer for ANC, etc.) is the
    account holder (customer). If participant interests aren't supplied, the
    account PI is split equally among the named participants so coverage can be
    demonstrated — flagged via `equal_split` in the evidence.
    """
    pi = _aggregate_pi(accounts)
    vested: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for a in accounts:
        for pid, pname, amt in _pt_parties(orc, a):
            vested[pid] = vested.get(pid, Decimal("0")) + amt
            names.setdefault(pid, pname)

    n = len(vested)
    equal_split = False
    if n and all(v == 0 for v in vested.values()):
        share = pi / Decimal(n)
        vested = {k: share for k in vested}
        equal_split = True

    if vested:
        insured = sum((min(v, SMDIA) for v in vested.values()), Decimal("0"))
        limit = SMDIA * n
        detail = (f"{n} participant(s); pass-through to "
                  + ("equally-split interest." if equal_split else "vested interest."))
    else:
        # No participant detail → cannot pass through; falls to pending (AREBP/ARO).
        insured = Decimal("0")
        limit = SMDIA
        detail = "No participant detail; pass-through cannot be computed (pending)."
    insured = min(insured, pi)

    participant_coverage = [
        {"participant": names.get(pid, pid),
         "allocated": str(_q(v)),
         "insured": str(_q(min(v, SMDIA))),
         "uninsured": str(_q(v - min(v, SMDIA)))}
        for pid, v in vested.items()
    ]
    plan_owner = accounts[0].customer_id if accounts else None

    return CoverageResult(
        orc=orc, aggregated_pi=_q(pi), coverage_limit=_q(limit),
        insured_amount=_q(insured), uninsured_amount=_q(pi - insured),
        rationale=f"{orc.value} pass-through. {detail}",
        accounts_included=[a.account_number for a in accounts],
        evidence={"vested_interests": {k: str(_q(v)) for k, v in vested.items()},
                  "participant_names": names,
                  "participant_coverage": participant_coverage,
                  "plan_owner": plan_owner,
                  "equal_split": equal_split},
    )


def _per_entity(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """BUS / DIT / DOE: one SMDIA for the legal entity, separate from owners."""
    pi = _aggregate_pi(accounts)
    limit = SMDIA
    insured = min(pi, limit)
    return CoverageResult(
        orc=orc, aggregated_pi=_q(pi), coverage_limit=_q(limit),
        insured_amount=_q(insured), uninsured_amount=_q(pi - insured),
        rationale=(
            f"{orc.value}: the legal entity is a single depositor insured to "
            f"SMDIA ${SMDIA:,.0f}, separate from the personal accounts of any "
            f"owner, member, or partner."
        ),
        accounts_included=[a.account_number for a in accounts],
        evidence={"entity": accounts[0].customer_id if accounts else None},
    )


def _business(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """BUS — corporation / partnership / unincorporated association (12 CFR 330.11).

    Eligibility branches (sole proprietorships are reclassified to SGL upstream
    in the ORC Classification Agent and never reach this function):

      * Engaged in an INDEPENDENT ACTIVITY (default / assumed): the entity is a
        single, separate depositor insured to one SMDIA, distinct from the
        personal accounts of its owners, members, or partners — §330.11(a).
      * NOT engaged in an independent activity: the deposit is owned by the
        members; it is allocated equally among them and each member is insured
        to SMDIA as single-ownership funds (pass-through) — §330.11(c).
    """
    pi = _aggregate_pi(accounts)
    entity = accounts[0].customer_id if accounts else None
    per_account = {a.account_number: str(_q(a.principal_and_interest)) for a in accounts}

    # Non-independent only when explicitly flagged False on any account; None is
    # treated as "assumed independent" but recorded as unconfirmed for review.
    independent = not any(a.independent_activity is False for a in accounts)
    confirmed = all(a.independent_activity is not None for a in accounts)

    if independent:
        limit = SMDIA
        insured = min(pi, limit)
        return CoverageResult(
            orc=orc, aggregated_pi=_q(pi), coverage_limit=_q(limit),
            insured_amount=_q(insured), uninsured_amount=_q(pi - insured),
            rationale=(
                f"BUS: the legal entity is engaged in an independent activity and "
                f"is insured as a single depositor to one SMDIA ${SMDIA:,.0f}, "
                f"separate from the personal accounts of any owner, member, or "
                f"partner (12 CFR 330.11(a))."
                + ("" if confirmed else " Independent activity assumed — confirm.")
            ),
            accounts_included=[a.account_number for a in accounts],
            evidence={"entity": entity, "treatment": "per_entity_independent",
                      "independent_activity": True if confirmed else "assumed",
                      "per_account_pi": per_account, "citation": "12 CFR 330.11(a)"},
        )

    # Non-independent association → pass-through to members (equal allocation).
    members: list[str] = []
    member_names: dict[str, str] = {}
    for a in accounts:
        for o in a.owners:
            if o.party_id not in member_names:
                members.append(o.party_id)
                member_names[o.party_id] = o.name
    if not members:  # roster not provided — conservative single-member fallback
        members = [entity or "MEMBER_1"]
        member_names[members[0]] = "(member roster pending)"
    n = len(members)
    share = pi / Decimal(n)
    member_share = {m: share for m in members}
    insured = min(sum((min(s, SMDIA) for s in member_share.values()), Decimal("0")), pi)
    return CoverageResult(
        orc=orc, aggregated_pi=_q(pi), coverage_limit=_q(SMDIA * n),
        insured_amount=_q(insured), uninsured_amount=_q(pi - insured),
        rationale=(
            f"BUS: entity is NOT engaged in an independent activity, so funds are "
            f"allocated equally among {n} member(s) and each is insured to SMDIA "
            f"${SMDIA:,.0f} as single-ownership funds (12 CFR 330.11(c))."
        ),
        accounts_included=[a.account_number for a in accounts],
        evidence={"entity": entity, "treatment": "pass_through_members",
                  "independent_activity": False,
                  # owner_shares/owner_names mirror the per-owner allocation shape
                  # (SGL/JNT) so the UI renders each member's insured/uninsured split.
                  "owner_shares": {m: str(_q(s)) for m, s in member_share.items()},
                  "owner_names": member_names,
                  "member_shares": {m: str(_q(s)) for m, s in member_share.items()},
                  "member_names": member_names, "per_account_pi": per_account,
                  "citation": "12 CFR 330.11(c)"},
    )


def _per_custodian(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """GOV1/GOV2/GOV3: one SMDIA per unique (official custodian, public unit).

    Per FDIC IT Functional Guide §4.1.9, each unique combination of official
    custodian, public unit, and GOV code is insured up to SMDIA. The time/savings
    vs demand-deposit split is captured by the *code itself* (GOV1 = in-state
    time & savings, GOV2 = in-state demand, GOV3 = out-of-state) — there is NO
    intra-code multiplier. A custodian holding both deposit types is therefore
    covered separately under GOV1 and GOV2, each evaluated in its own group.
    """
    pi = _aggregate_pi(accounts)
    custodians = _unique_owners(accounts)
    n = max(len(custodians), 1)
    limit = SMDIA * n
    insured = min(pi, limit)
    return CoverageResult(
        orc=orc, aggregated_pi=_q(pi), coverage_limit=_q(limit),
        insured_amount=_q(insured), uninsured_amount=_q(pi - insured),
        rationale=(
            f"{orc.value}: {n} unique official custodian/public-unit combination(s) "
            f"× SMDIA ${SMDIA:,.0f} = ${limit:,.0f}."
        ),
        accounts_included=[a.account_number for a in accounts],
        evidence={"official_custodians": sorted(custodians)},
    )


_DISPATCH = {
    CoverageShape.PER_OWNER: _per_owner,
    CoverageShape.PER_OWNER_PER_BENE: _per_owner_per_bene,
    CoverageShape.PER_PARTICIPANT: _per_participant,
    CoverageShape.PER_PRINCIPAL: _per_participant,  # MSA/BIA: same pass-through engine
    CoverageShape.PER_ENTITY: _per_entity,
    CoverageShape.PER_CUSTODIAN: _per_custodian,
}


def calculate(orc: ORC, accounts: list[Account]) -> CoverageResult:
    """Calculate FDIC coverage for one ORC aggregation group.

    `accounts` MUST already be the set of accounts that aggregate together for
    this ORC + depositor (see ORC_CONFIG['aggregates_with']). Grouping is the
    caller's (ORC Classification Agent) responsibility.
    """
    # BUS has eligibility branching (independent activity / pass-through to
    # members) beyond the plain PER_ENTITY cap shared by DIT/DOE.
    if orc == ORC.BUS:
        return _business(orc, accounts)
    shape = ORC_CONFIG[orc]["shape"]
    return _DISPATCH[shape](orc, accounts)
