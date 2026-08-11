"""The record is a pure projection of the touchpoint stream. There is no record write.

`None` from either function means THE STORE COULD NOT BE READ - a different fact from an empty
stream, and the boundary treats it as fail-closed (spec 5.2). Zero-because-new and
zero-because-the-query-failed must never reach the guard as the same value.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Record
from retinue.ledger.models import StoreUnavailable, Touchpoint
from retinue.ledger.store import TouchpointStore

@dataclass(frozen=True)
class RelationshipRecord:
    investor_id: str
    stated_check_size: Decimal | None
    pass_reason: str | None
    last_contact: datetime | None
    jurisdiction: str | None
    domain: str | None

def _rows(store: TouchpointStore, investor_id: str) -> tuple[Touchpoint, ...] | None:
    try:
        return store.touchpoints_for(investor_id)
    except StoreUnavailable:
        return None

def _last(rows, kind: str) -> Touchpoint | None:
    hits = [t for t in rows if t.kind == kind]
    return max(hits, key=lambda t: t.occurred_at) if hits else None

def project_record(store: TouchpointStore, investor_id: str) -> RelationshipRecord | None:
    rows = _rows(store, investor_id)
    if rows is None:
        return None
    check = _last(rows, "stated_check_size")
    passed = _last(rows, "pass_reason")
    ident = _last(rows, "identity")
    contacts = [t for t in rows if t.kind in ("contact", "sent")]
    return RelationshipRecord(
        investor_id=investor_id,
        stated_check_size=Decimal(check.payload["amount"]) if check else None,
        pass_reason=passed.payload.get("reason") if passed else None,
        last_contact=max(t.occurred_at for t in contacts) if contacts else None,
        jurisdiction=ident.payload.get("jurisdiction") if ident else None,
        domain=ident.payload.get("domain") if ident else None,
    )

def build_act_context(store: TouchpointStore, investor_id: str, *,
                      granted_tools: frozenset[str], tier: int, send_cap: int,
                      approval_token: str | None = None) -> ActContext | None:
    rows = _rows(store, investor_id)
    if rows is None:
        return None
    ident = _last(rows, "identity")
    juris = frozenset({ident.payload["jurisdiction"]}) if ident and "jurisdiction" in ident.payload else frozenset()
    return ActContext(
        approval_token=approval_token, tier=tier,
        consented_jurisdictions=juris, granted_tools=granted_tools,
        sent_count=sum(1 for t in rows if t.kind == "sent"), send_cap=send_cap,
    )

def as_policy_record(record: RelationshipRecord) -> Record:
    """The ledger record in the imported policy vocabulary. Money leaves in PLAIN notation, which
    is NOT `str(Decimal)`.

    `str(Decimal("2.5E+5"))` is `"2.5E+5"`, `normalize_money` fullmatches a decimal-digits pattern
    which that fails, `evaluate_act_classes` catches the CanonicalizationError and CONTINUES, and
    the field is dropped from `record_values` altogether. A draft stating a figure the record
    actually holds then collects `act:figure_not_in_record`. The value is reachable from an
    ordinary payload: the write barrier refuses floats and unparseable strings, and `"2.5E+5"` is
    neither. Canonicalising the money upstream detonates this rather than fixing it, since
    `Decimal("250000").normalize()` IS `Decimal("2.5E+5")`.

    No sentence here says the engine canonicalises on its side. It does so only for values its
    pattern accepts, and that sentence is what invited the rewrite that breaks this.
    """
    fields = {"investor_id": record.investor_id}
    if record.stated_check_size is not None:      # `is not None`, never falsiness: a zero check
        fields["stated_check_size"] = f"{record.stated_check_size:f}"      # size is a FACT
    if record.pass_reason:                        # falsiness, matching render_block: an empty
        fields["pass_reason"] = record.pass_reason                         # reason is an ABSENCE
    return Record(fields=fields)
