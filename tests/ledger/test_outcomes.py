from datetime import datetime, timezone
import pytest
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import InMemoryStore
from retinue.ledger.outcomes import (OUTCOME_SIGNALS, OutcomeConfig, OutcomeRecord,
                                     last_touch_attribution, resolved_for)

T = [datetime(2030, 2, d, tzinfo=timezone.utc) for d in (1, 5, 9, 20)]

def outcome(signal="replied", occurred=T[2], observed=T[3], key="o1"):
    return OutcomeRecord(outcome_key=key, investor_id="inv-1", mandate_id="m-1",
                         signal=signal, occurred_at=occurred, observed_at=observed)

def test_unknown_signal_raises():
    with pytest.raises(Exception):
        outcome(signal="ghosted")

def test_occurred_and_observed_are_both_required_and_distinct():
    o = outcome()
    assert o.occurred_at != o.observed_at        # weeks apart in the world; both carried

def test_active_signal_is_configuration_not_code():
    rows = (outcome("replied", key="o1"), outcome("meeting_booked", key="o2"))
    assert [o.outcome_key for o in resolved_for(OutcomeConfig(), rows)] == ["o1"]
    toggled = OutcomeConfig(active_signal="meeting_booked")
    assert [o.outcome_key for o in resolved_for(toggled, rows)] == ["o2"]

def test_config_rejects_a_signal_outside_the_enum():
    with pytest.raises(Exception):
        OutcomeConfig(active_signal="vibes")

def test_last_touch_attribution_picks_latest_at_or_before_occurred():
    s = InMemoryStore()
    for key, occ in (("c1", T[0]), ("c2", T[1]), ("late", T[3])):
        s.append(Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                            kind="contact", payload={}, occurred_at=occ, recorded_at=T[3]))
    hit = last_touch_attribution(s, outcome(occurred=T[2]))
    assert hit.idempotency_key == "c2"           # latest <= occurred; never the later one

def test_attribution_on_a_new_investor_is_none_not_invented():
    assert last_touch_attribution(InMemoryStore(), outcome()) is None
