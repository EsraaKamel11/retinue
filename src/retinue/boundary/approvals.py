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


class MemoryResolutionLog:
    """First-writer-wins over review rows: the memory half of the design's one named update."""

    def __init__(self) -> None:
        self._resolved: dict[int, tuple[datetime, str]] = {}

    def record(self, row_id: int, at: datetime, approved_by: str) -> bool:
        if row_id in self._resolved:
            return False
        self._resolved[row_id] = (at, approved_by)
        return True


#: The design's SINGLE named update (spec section 2), hoisted for the reason the three statements
#: above are hoisted, and held against schema.sql by the same keyless gate. Three clauses in it
#: carry weight that no keyless run can otherwise reach:
#:
#: `AND resolved_at IS NULL` IS the test-and-set. Drop it and the UPDATE succeeds against a row
#: already resolved, so `rowcount == 1` comes back for the second resolver too and a double
#: resolution mints a second token over one human act - the exact property `resolve` rests on.
#: `approved_by` is written in the same statement rather than a second one, because which human
#: approved is the provenance the token's `resolution_id` reaches for. And the WHERE keys on the
#: primary key, so `rowcount == 1` names one identified row rather than one of several.
RESOLVE_ROW = ("UPDATE review_queue SET resolved_at = %s, approved_by = %s "
               "WHERE id = %s AND resolved_at IS NULL")


class PgResolutionLog:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def record(self, row_id: int, at: datetime, approved_by: str) -> bool:
        import psycopg
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(RESOLVE_ROW, (at, approved_by, row_id))
            return cur.rowcount == 1


def resolve(*, row_id: int, verdict: str, at: datetime, approved_by: str,
            window: timedelta, resolutions, approvals: ApprovalStore, key: str, body: str,
            tool: str, recipient_domain: str, token_id: str | None = None,
            ) -> ApprovalToken | None:
    """The mint IS the resolution event. The resolution is the test-and-set; its loser mints
    nothing, so a double resolution yields exactly one token. A rejecting verdict resolves the
    row and mints nothing. The caller supplies the binding material and the clock.

    A caller-supplied token id that is already minted RAISES, and raises BEFORE the resolution is
    written. Discovering the collision afterwards left the row resolved, tokenless and
    unresolvable for good, while answering the same None a race loser gets - reached with no crash
    and no concurrency. Generate-and-retry is not the repair: a supplied id is the caller's own
    evidence, and quietly substituting another hands back a token the caller cannot recognise. So
    the collision costs the row nothing and a corrected call still resolves it.
    """
    if token_id is not None and approvals.get_token(token_id) is not None:
        raise ValueError(f"token id {token_id!r} is already minted, so nothing was resolved: "
                         f"review row {row_id} is untouched and can still be resolved")
    if not resolutions.record(row_id, at, approved_by):
        return None
    if verdict != "approve":
        return None
    token = ApprovalToken(token=token_id or secrets.token_hex(16), idempotency_key=key,
                          body_digest=body_digest_of(body), tool=tool,
                          recipient_domain=recipient_domain, resolution_id=row_id,
                          minted_at=at, expires_at=at + window)
    if not approvals.put_token(token):
        # Reachable now only by a genuine race - another caller minting this id between the check
        # above and this insert - which a single-threaded caller cannot reach and CSPRNG ids do
        # not reach in practice. It still leaves the resolved row tokenless, which no check here
        # can close and one transaction can: the plan's Task 4 step 5, for the DSN lane.
        return None
    return token


def validate_and_consume(*, token: str, key: str, draft: Draft, at: datetime,
                         store: ApprovalStore) -> str | None:
    """None on success. Otherwise a reason naming the failed leg, for the boundary handoff.

    Reads run before the one write: a mis-bound attempt refuses WITHOUT spending the token,
    so nobody can burn an approval they could not use. The consume append is last and its
    boolean is the race decision; the gate-denial burn the spec argues lives downstream of
    this function, which only ever spends a token it fully validated."""
    t = store.get_token(token)
    if t is None:
        return f"no approval was ever minted under this token"
    if t.idempotency_key != key:
        return "the approval binds a different idempotency key"
    if t.body_digest != body_digest_of(draft.body):
        return "the approval binds a different body"
    if t.tool != (draft.tool_name or ""):
        return "the approval binds a different tool"
    if t.recipient_domain != draft.recipient_domain:
        return "the approval binds a different recipient domain"
    if not at < t.expires_at:
        return "the approval expired before the act"
    if not store.consume(token, at):
        return "the approval was already consumed"
    return None
