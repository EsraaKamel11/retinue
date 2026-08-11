"""Ledger primitives. Every fact arrives as a touchpoint; the record is a projection."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DeliveryStatus = Literal["CONFIRMED", "FAILED", "UNVERIFIABLE"]
KINDS = frozenset({"contact", "stated_check_size", "pass_reason", "identity", "sent"})
#: Kinds whose payload carries money. Money rules bind at the write barrier, not at read.
MONEY_KINDS = frozenset({"stated_check_size"})

#: `render_block`'s DEFAULT byte budget, restated here rather than imported. `models.py ->
#: block.py -> projection.py -> models.py` is an import cycle, so the number is written in two
#: files and `test_the_write_barriers_bound_is_the_blocks_own_default_budget` holds the two
#: spellings equal. Double entry, the same control this repository already uses for the session
#: roster: the fact is stated twice and a test refuses to let one move alone.
BLOCK_DEFAULT_BUDGET = 1024

def plain_width(value: Decimal) -> int:
    """The length of `format(value, "f")`, computed WITHOUT building that string.

    This exists because plain notation costs O(10^|exponent|) where `str(Decimal)` cost nothing.
    Measuring the width by formatting would give the guard exactly the cost it exists to prevent,
    so the width is arithmetic on the three small integers `as_tuple` returns.

    Callers must establish finiteness first: `Decimal("NaN").as_tuple()` carries the string `'n'`
    as its exponent and the arithmetic below would raise a TypeError on it.

    Four cases, and the first is the one pure digit-counting gets wrong. A zero coefficient with a
    non-negative exponent formats as `"0"` rather than as padded zeros, so `Decimal("0E+2")` is one
    character and not three; an implementation without that branch over-refuses a stored zero.
    Pinned against the formatter across the grid in `test_models.py` rather than argued here, which
    is what makes the 10^9 case an extrapolation from a measurement.
    """
    sign, digits, exponent = value.as_tuple()
    if digits == (0,) and exponent >= 0:
        width = 1                                  # every zero formats as "0", never padded
    elif exponent >= 0:
        width = len(digits) + exponent             # an integer, then that many trailing zeros
    elif len(digits) > -exponent:
        width = len(digits) + 1                    # the digits, with a point somewhere inside them
    else:
        width = -exponent + 2                      # "0.", then leading zeros, then the digits
    return width + (1 if sign else 0)

class StoreUnavailable(Exception):
    """The store could not be read. Distinct from empty; the projection returns None on this."""

class Touchpoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    idempotency_key: str
    investor_id: str
    mandate_id: str | None
    kind: str
    payload: dict
    occurred_at: datetime      # when true in the world
    recorded_at: datetime      # when the system learned it
    delivery_status: DeliveryStatus | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in KINDS:
            raise ValueError(f"unknown touchpoint kind {v!r}; known: {sorted(KINDS)}")
        return v

    @model_validator(mode="after")
    def _money_payload_is_usable(self) -> "Touchpoint":
        """A money touchpoint must carry a usable amount, refused at construction.

        Degrading at read would let the rendered block print "not stated" for a statement
        that exists and cannot be read, which is a false fact arriving through the most
        trusted component. Raising at read would add a fourth state to a tri-state contract.
        Floats are refused rather than coerced: money is Decimal, carried as a string.

        The last two clauses are about what money COSTS downstream, and both close a route the
        budget structurally cannot. `render_block` measures its output after building it, so a
        value whose plain rendering is a billion characters has already been allocated by the time
        the budget looks, and `as_policy_record` has no budget at all. A guard that measures after
        the cost it guards against is not a guard, so the bound binds here, where the value enters.
        """
        if self.kind in MONEY_KINDS:
            raw = self.payload.get("amount")
            if raw is None:
                raise ValueError(f"a {self.kind} touchpoint must carry an 'amount' in its payload")
            if isinstance(raw, float):
                raise ValueError(f"amount {raw!r} is a float; money is Decimal, carried as a string")
            try:
                amount = Decimal(str(raw))
            except InvalidOperation as exc:
                raise ValueError(f"amount {raw!r} is not a usable decimal") from exc
            # NaN, sNaN and Infinity all parse. They render into the block as `stated_check_size:
            # NaN` and are then dropped from the engine's record values in silence, which is a fact
            # the model was shown and the boundary never saw. `is_finite` and not a comparison: a
            # signalling NaN raises the moment anything compares it.
            if not amount.is_finite():
                raise ValueError(f"amount {raw!r} is not a finite decimal")
            # STRUCTURAL, not a business limit on cheque sizes: a value whose plain rendering alone
            # does not fit the block's default budget leaves no room for the header, the other five
            # fields, or its own label, so it can never be rendered at any budget the block ships
            # with. Refusing it once here beats raising on every render forever.
            width = plain_width(amount)
            if width > BLOCK_DEFAULT_BUDGET:
                raise ValueError(
                    f"amount {raw!r} is {width} characters in plain notation, past the "
                    f"{BLOCK_DEFAULT_BUDGET}-byte block budget, so it could never be rendered"
                )
        return self
