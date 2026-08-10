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
