"""The store contract and its in-memory reference. The Postgres adapter must pass the SAME tests."""
from __future__ import annotations
from typing import Protocol
from retinue.ledger.models import Touchpoint

class TouchpointStore(Protocol):
    def append(self, tp: Touchpoint) -> bool: ...
    def touchpoints_for(self, investor_id: str) -> tuple[Touchpoint, ...]: ...

class InMemoryStore:
    def __init__(self) -> None:
        self._rows: list[Touchpoint] = []
        self._keys: set[str] = set()

    def append(self, tp: Touchpoint) -> bool:
        if tp.idempotency_key in self._keys:
            return False
        self._keys.add(tp.idempotency_key)
        self._rows.append(tp)
        return True

    def touchpoints_for(self, investor_id: str) -> tuple[Touchpoint, ...]:
        return tuple(t for t in self._rows if t.investor_id == investor_id)
