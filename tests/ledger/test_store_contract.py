from datetime import datetime, timezone
import pytest
from retinue.ledger.models import Touchpoint

T0 = datetime(2030, 1, 5, tzinfo=timezone.utc)
T1 = datetime(2030, 1, 6, tzinfo=timezone.utc)

def tp(ns, key="k1", kind="contact", occurred=T0, **payload):
    return Touchpoint(idempotency_key=f"{ns}-{key}", investor_id=f"inv-{ns}", mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T1)

def test_append_then_read_in_insertion_order(store, ns):
    assert store.append(tp(ns, "a")) is True
    assert store.append(tp(ns, "b", occurred=T1)) is True
    keys = [t.idempotency_key for t in store.touchpoints_for(f"inv-{ns}")]
    assert keys == [f"{ns}-a", f"{ns}-b"]

def test_duplicate_idempotency_key_is_refused_without_error(store, ns):
    assert store.append(tp(ns, "a")) is True
    assert store.append(tp(ns, "a")) is False
    assert len(store.touchpoints_for(f"inv-{ns}")) == 1

def test_touchpoints_are_frozen(ns):
    t = tp(ns, "a")
    with pytest.raises(Exception):
        t.kind = "sent"

def test_unknown_kind_is_rejected_at_construction(ns):
    with pytest.raises(Exception):
        tp(ns, "a", kind="mutation")

def test_bitemporal_fields_are_distinct_and_required(ns):
    t = tp(ns, "a")
    assert t.occurred_at != t.recorded_at

def test_idempotency_keys_are_globally_unique_not_per_investor(store, ns):
    # The schema makes idempotency_key the PRIMARY KEY: one namespace for every investor.
    # Pinned so an adapter with a per-investor unique index cannot pass this suite.
    first = tp(ns, "shared")
    second = Touchpoint(**{**first.model_dump(), "investor_id": f"other-{ns}"})
    assert store.append(first) is True
    assert store.append(second) is False
    assert store.touchpoints_for(f"other-{ns}") == ()

def test_the_store_snapshots_payloads_at_append_and_at_read(store, ns):
    # Postgres serialises payload into JSONB at write and rebuilds objects per read; the
    # in-memory reference must snapshot at both barriers, or the two adapters disagree about
    # whether a retained reference can rewrite an already-appended fact.
    t = tp(ns, "snap", usd="250000")
    store.append(t)
    t.payload["usd"] = "1"                                        # caller mutates its own object
    inv = f"inv-{ns}"
    assert store.touchpoints_for(inv)[0].payload["usd"] == "250000"
    store.touchpoints_for(inv)[0].payload["usd"] = "9"            # reader mutates what it got
    assert store.touchpoints_for(inv)[0].payload["usd"] == "250000"
