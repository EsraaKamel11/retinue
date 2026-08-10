"""Ledger primitives. Every fact arrives as a touchpoint; the record is a projection."""
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator

DeliveryStatus = Literal["CONFIRMED", "FAILED", "UNVERIFIABLE"]
KINDS = frozenset({"contact", "stated_check_size", "pass_reason", "identity", "sent"})

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
