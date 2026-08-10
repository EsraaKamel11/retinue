"""Postgres adapter. now() never appears here for row data - timestamps arrive on the model."""
from __future__ import annotations
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from retinue.ledger.models import StoreUnavailable, Touchpoint

#: Resolves from a source checkout only - the wheel ships `src/` and not this file. Bootstrapping
#: is a test-and-CI operation, both of which run from a checkout, so that is the whole story.
_SCHEMA = Path(__file__).resolve().parents[3] / "schema.sql"

def bootstrap(dsn: str) -> None:
    if not _SCHEMA.is_file():
        raise FileNotFoundError(
            f"{_SCHEMA} is missing: bootstrap runs from a source checkout, not an installed wheel")
    try:
        with psycopg.connect(dsn) as c:
            c.execute(_SCHEMA.read_text(encoding="utf-8"))
    except psycopg.OperationalError as exc:
        raise StoreUnavailable(str(exc)) from exc   # same translation as append/touchpoints_for

#: The one read query, hoisted so the index plan test EXPLAINs exactly what the adapter runs.
SELECT_FOR_INVESTOR = (
    "SELECT idempotency_key, investor_id, mandate_id, kind, payload,"
    " occurred_at, recorded_at, delivery_status FROM touchpoints"
    " WHERE investor_id=%s ORDER BY seq")

class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def append(self, tp: Touchpoint) -> bool:
        try:
            with psycopg.connect(self._dsn) as c:
                cur = c.execute(
                    "INSERT INTO touchpoints (idempotency_key, investor_id, mandate_id, kind,"
                    " payload, occurred_at, recorded_at, delivery_status)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING",
                    (tp.idempotency_key, tp.investor_id, tp.mandate_id, tp.kind,
                     Jsonb(tp.payload), tp.occurred_at, tp.recorded_at, tp.delivery_status))
                return cur.rowcount == 1
        except psycopg.OperationalError as exc:
            raise StoreUnavailable(str(exc)) from exc

    def touchpoints_for(self, investor_id: str) -> tuple[Touchpoint, ...]:
        try:
            with psycopg.connect(self._dsn) as c:
                rows = c.execute(SELECT_FOR_INVESTOR, (investor_id,)).fetchall()
        except psycopg.OperationalError as exc:
            raise StoreUnavailable(str(exc)) from exc
        return tuple(Touchpoint(idempotency_key=r[0], investor_id=r[1], mandate_id=r[2],
                                kind=r[3], payload=r[4], occurred_at=r[5], recorded_at=r[6],
                                delivery_status=r[7]) for r in rows)
