from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.models import Touchpoint, KINDS
from retinue.ledger.store import InMemoryStore

T0 = datetime(2030, 1, 5, tzinfo=timezone.utc)
T1 = datetime(2030, 1, 6, tzinfo=timezone.utc)

def tp(key="k1", kind="contact", investor="inv-1", occurred=T0, **payload):
    return Touchpoint(idempotency_key=key, investor_id=investor, mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T1)

def test_append_then_read_in_insertion_order():
    s = InMemoryStore()
    assert s.append(tp("a")) is True
    assert s.append(tp("b", occurred=T1)) is True
    keys = [t.idempotency_key for t in s.touchpoints_for("inv-1")]
    assert keys == ["a", "b"]

def test_duplicate_idempotency_key_is_refused_without_error():
    s = InMemoryStore()
    assert s.append(tp("a")) is True
    assert s.append(tp("a")) is False          # same key: refused, not raised
    assert len(s.touchpoints_for("inv-1")) == 1

def test_touchpoints_are_frozen():
    t = tp("a")
    with pytest.raises(Exception):
        t.kind = "sent"

def test_unknown_kind_is_rejected_at_construction():
    with pytest.raises(Exception):
        tp("a", kind="mutation")

def test_bitemporal_fields_are_distinct_and_required():
    t = tp("a")
    assert t.occurred_at != t.recorded_at      # world-time vs system-time both carried

def test_the_store_snapshots_payloads_at_append_and_at_read():
    s = InMemoryStore()
    t = tp("snap", usd="250000")
    s.append(t)
    t.payload["usd"] = "1"                                  # caller mutates its own object
    assert s.touchpoints_for("inv-1")[0].payload["usd"] == "250000"
    s.touchpoints_for("inv-1")[0].payload["usd"] = "9"      # reader mutates what it was handed
    assert s.touchpoints_for("inv-1")[0].payload["usd"] == "250000"

def test_idempotency_keys_are_globally_unique_not_per_investor():
    # The schema makes idempotency_key the PRIMARY KEY: one namespace for every investor.
    # Pinned here so an adapter with a per-investor unique index cannot pass this suite.
    s = InMemoryStore()
    assert s.append(tp("shared")) is True
    assert s.append(tp("shared", investor="inv-2")) is False
    assert s.touchpoints_for("inv-2") == ()
