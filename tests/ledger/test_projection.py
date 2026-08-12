from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.models import Touchpoint, StoreUnavailable
from retinue.ledger.store import InMemoryStore
from retinue.ledger.projection import project_record, build_act_context

T = [datetime(2030, 1, d, tzinfo=timezone.utc) for d in (1, 2, 3, 4)]

def tp(key, kind, occurred, **payload):
    return Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T[3])

PASS_REASON = "fund is fully allocated for this vintage"

def seeded():
    s = InMemoryStore()
    s.append(tp("i", "identity", T[0], jurisdiction="US", domain="example.test"))
    s.append(tp("c1", "contact", T[1]))
    s.append(tp("k", "stated_check_size", T[2], amount="250000"))
    s.append(tp("c2", "contact", T[2]))
    # The one kind the seed never held, which left `pass_reason` the single record field with no
    # positive assertion anywhere: measured, change the projection's payload key from "reason" to
    # anything else and the whole suite stays green, because the only row touching that field
    # asserts None over a store that never carried one.
    s.append(tp("p", "pass_reason", T[2], reason=PASS_REASON))
    return s

def test_record_fields_are_all_derived():
    """All SIX, which is what the name says and what four of them used to hold.

    `pass_reason` is the field this row exists for now. `block.py` rests its whole
    line-break-forgery guard on that expression being free text out of a JSON payload, and
    `as_policy_record` carries it into the policy vocabulary, so a projection reading the wrong
    payload key drops it silently everywhere downstream and reports an absence as a fact.
    """
    r = project_record(seeded(), "inv-1")
    assert r.investor_id == "inv-1"
    assert r.stated_check_size == Decimal("250000")
    assert r.pass_reason == PASS_REASON
    assert r.last_contact == T[2]                       # max occurred_at of contact kinds
    assert (r.jurisdiction, r.domain) == ("US", "example.test")

def test_check_size_is_decimal_never_float():
    r = project_record(seeded(), "inv-1")
    assert isinstance(r.stated_check_size, Decimal)

def test_new_investor_is_a_true_zero_not_unavailable():
    ctx = build_act_context(InMemoryStore(), "inv-9", granted_tools=frozenset({"send_message"}),
                            tier=2, send_cap=5)
    assert ctx is not None and ctx.sent_count == 0      # zero-because-new is a real fact

def test_new_investor_projects_a_record_not_none():
    # The mirror of test_new_investor_is_a_true_zero_not_unavailable, for the other function:
    # a new investor is a record whose facts are absent, never the absence of a record.
    rec = project_record(InMemoryStore(), "inv-9")
    assert rec is not None
    assert (rec.stated_check_size, rec.pass_reason, rec.last_contact) == (None, None, None)

class BrokenStore:
    def append(self, tp): raise AssertionError
    def touchpoints_for(self, investor_id): raise StoreUnavailable("connection refused")

def test_unavailable_store_gives_no_act_context():
    assert build_act_context(BrokenStore(), "inv-1", granted_tools=frozenset(),
                             tier=2, send_cap=5) is None

def test_unavailable_store_gives_no_record():
    assert project_record(BrokenStore(), "inv-1") is None

def test_sent_count_counts_only_sends():
    s = seeded()
    s.append(tp("s1", "sent", T[3]))
    ctx = build_act_context(s, "inv-1", granted_tools=frozenset(), tier=2, send_cap=5)
    assert ctx.sent_count == 1

def test_six_actcontext_fields_are_populated():
    ctx = build_act_context(seeded(), "inv-1", granted_tools=frozenset({"send_message"}),
                            tier=2, send_cap=5, approval_token=None)
    assert ctx.consented_jurisdictions == frozenset({"US"})
    assert ctx.granted_tools == frozenset({"send_message"})
    assert (ctx.tier, ctx.send_cap, ctx.approval_token) == (2, 5, None)
