"""Outcomes. The signal that counts is a CONFIG PARAMETER, not a code path: which outcome the
product optimises for is a genuinely open question, and this shape keeps it a toggle (spec 5.1).
The weights-update sketch that reads it stays Designed. Attribution: last-touch, parameterized.

OutcomeRecord is frozen here while its row in `outcomes` is deliberately mutable, and the two are
not in contradiction: frozen stops a value being rewritten under the holder it was handed to,
while a later-resolving outcome rewrites the ROW under the same outcome_key. That is why
`outcomes` carries no append-only trigger where `touchpoints` does. The ledger stays immutable and
the outcome stays correctable, and schema.sql states the same reason beside the table.

Attribution is INVESTOR-level: last_touch_attribution filters by kind and by time, never by
mandate_id, so an outcome on one mandate can attribute to a touch on another for the same
investor. That is deliberate at this size - the store offers no mandate-scoped query, and an
investor's history reads as one conversation - but the record requires a mandate_id that
attribution never reads, so the semantics are pinned by a test rather than left to be inferred."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import TouchpointStore

OUTCOME_SIGNALS = ("replied", "meeting_booked", "check_written")

class OutcomeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    outcome_key: str
    investor_id: str
    mandate_id: str
    signal: str
    occurred_at: datetime      # when it happened in the world
    observed_at: datetime      # when the system learned it - weeks later, structurally

    @field_validator("signal")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in OUTCOME_SIGNALS:
            raise ValueError(f"unknown outcome signal {v!r}; known: {OUTCOME_SIGNALS}")
        return v

class OutcomeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    active_signal: str = "replied"
    attribution: str = "last_touch"

    @field_validator("active_signal")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in OUTCOME_SIGNALS:
            raise ValueError(f"active_signal {v!r} is not in {OUTCOME_SIGNALS}")
        return v

def resolved_for(config: OutcomeConfig, outcomes) -> tuple[OutcomeRecord, ...]:
    return tuple(o for o in outcomes if o.signal == config.active_signal)

def last_touch_attribution(store: TouchpointStore, outcome: OutcomeRecord) -> Touchpoint | None:
    touches = [t for t in store.touchpoints_for(outcome.investor_id)
               if t.kind in ("contact", "sent") and t.occurred_at <= outcome.occurred_at]
    return max(touches, key=lambda t: t.occurred_at) if touches else None
