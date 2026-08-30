"""The approval bridge's stores and verbs (spec: 2026-08-30-approval-bridge-design.md).

A token is a row binding one act, one body, one tool and one destination to the human
resolution that minted it. The TOKEN stores are append-only throughout: mint rows and
consumption rows are only ever inserted, and consumption is the house append-that-wins
primitive - INSERT ... ON CONFLICT DO NOTHING in Postgres, first-insert set membership in
memory - so single use survives a race by construction. The one update in the whole design is
the resolution test-and-set in `resolve`, named in the spec as such.

No policy is decided here. Validation legs compare recorded facts against the actual call's
facts; the class their refusal carries lives in send_tool.py beside its boundary siblings,
because no policy predicate ran.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from chaperone.policy.types import Draft


def body_digest_of(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalToken:
    token: str
    idempotency_key: str
    body_digest: str
    tool: str
    recipient_domain: str
    resolution_id: int
    minted_at: datetime
    expires_at: datetime


class ApprovalStore(Protocol):
    def put_token(self, t: ApprovalToken) -> bool: ...
    def get_token(self, token: str) -> ApprovalToken | None: ...
    def consume(self, token: str, at: datetime) -> bool: ...


class MemoryApprovalStore:
    def __init__(self) -> None:
        self._tokens: dict[str, ApprovalToken] = {}
        self._consumed: dict[str, datetime] = {}

    def put_token(self, t: ApprovalToken) -> bool:
        if t.token in self._tokens:
            return False
        self._tokens[t.token] = t
        return True

    def get_token(self, token: str) -> ApprovalToken | None:
        return self._tokens.get(token)

    def consume(self, token: str, at: datetime) -> bool:
        if token in self._consumed:
            return False
        self._consumed[token] = at
        return True


#: Hoisted for the reason INSERT_REVIEW_ROW is hoisted in review_queue.py: the tests that need a
#: database read the exact text the adapter issues. A KEYLESS double-entry gate in
#: tests/boundary/test_approvals.py holds all three against schema.sql, because every one of these
#: statements is executable only in the DSN lane.
#:
#: The conflict target is SPELLED, the way PostgresStore.append spells it, rather than left bare.
#: A bare `ON CONFLICT DO NOTHING` fires on whatever unique constraint the table happens to carry,
#: so a UNIQUE added later on `idempotency_key` would make put_token answer False for a DIFFERENT
#: token colliding on that key while MemoryApprovalStore answered True. Two halves whose whole
#: purpose is identical semantics would split, in the lane the default suite never runs. Naming
#: the target closes that off before it can open.
#:
#: SELECT_TOKEN's column ORDER is load-bearing rather than incidental: get_token splats the row
#: positionally into ApprovalToken, so this order IS the dataclass's field order, and the gate
#: asserts them equal as sequences.
INSERT_TOKEN = ("INSERT INTO approvals (token, idempotency_key, body_digest, tool, "
                "recipient_domain, resolution_id, minted_at, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (token) DO NOTHING")
SELECT_TOKEN = ("SELECT token, idempotency_key, body_digest, tool, recipient_domain, "
                "resolution_id, minted_at, expires_at FROM approvals WHERE token = %s")
INSERT_CONSUMPTION = ("INSERT INTO approval_consumptions (token, consumed_at) "
                      "VALUES (%s,%s) ON CONFLICT (token) DO NOTHING")


class PgApprovalStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conn(self):
        import psycopg
        return psycopg.connect(self._dsn)

    def put_token(self, t: ApprovalToken) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(INSERT_TOKEN, (t.token, t.idempotency_key, t.body_digest, t.tool,
                                       t.recipient_domain, t.resolution_id, t.minted_at,
                                       t.expires_at))
            return cur.rowcount == 1

    def get_token(self, token: str) -> ApprovalToken | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(SELECT_TOKEN, (token,))
            row = cur.fetchone()
        return None if row is None else ApprovalToken(*row)

    def consume(self, token: str, at: datetime) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(INSERT_CONSUMPTION, (token, at))
            return cur.rowcount == 1
