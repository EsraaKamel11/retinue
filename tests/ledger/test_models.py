from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.models import Touchpoint

T = datetime(2030, 1, 5, tzinfo=timezone.utc)

def money(**payload):
    return Touchpoint(idempotency_key="m1", investor_id="inv-1", mandate_id="m-1",
                      kind="stated_check_size", payload=payload, occurred_at=T, recorded_at=T)

def test_a_money_touchpoint_without_an_amount_is_refused_at_construction():
    with pytest.raises(Exception, match="amount"):
        money()

def test_a_float_amount_is_refused_rather_than_coerced():
    with pytest.raises(Exception, match="float"):
        money(amount=250000.0)

def test_an_unparseable_amount_is_refused():
    with pytest.raises(Exception, match="usable decimal"):
        money(amount="two hundred fifty thousand")

def test_a_string_amount_is_accepted_and_survives_as_an_exact_decimal():
    t = money(amount="250000.01")
    assert Decimal(t.payload["amount"]) == Decimal("250000.01")

def test_kinds_that_carry_no_money_are_unaffected_by_the_amount_rule():
    Touchpoint(idempotency_key="c1", investor_id="inv-1", mandate_id="m-1", kind="contact",
               payload={}, occurred_at=T, recorded_at=T)
