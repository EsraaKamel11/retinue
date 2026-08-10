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
        """
        if self.kind in MONEY_KINDS:
            raw = self.payload.get("amount")
            if raw is None:
                raise ValueError(f"a {self.kind} touchpoint must carry an 'amount' in its payload")
            if isinstance(raw, float):
                raise ValueError(f"amount {raw!r} is a float; money is Decimal, carried as a string")
            try:
                Decimal(str(raw))
            except InvalidOperation as exc:
                raise ValueError(f"amount {raw!r} is not a usable decimal") from exc
        return self
