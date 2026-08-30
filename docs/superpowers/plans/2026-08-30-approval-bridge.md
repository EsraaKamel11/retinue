# Approval Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mint-validate-consume approval path so a human resolution mints a single-use
token bound to one act, one body, one tool and one destination, verified and spent at the
boundary before the imported gate sees it, driven end to end by a first caller that is not a
test.

**Architecture:** One new boundary module (`approvals.py`) holds the token model, the dual store
halves and the validity conjunction; `resolve` writes `resolved_at` as the design's single named
update and mints atomically; `attempt_send` gains one pre-check between the projection check and
`guarded_call`; a P5-shape script drives the captured ask payload through the whole path. No
policy code anywhere; every deciding predicate stays imported.

**Tech Stack:** Python (existing repo toolchain), psycopg for the DSN lane, stdlib `hashlib`,
`secrets`, `argparse`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-approval-bridge-design.md` (at 9e30ade or later; the
binding authority - every conflict in this plan resolves against it).

## Global Constraints

- No policy code in this repository; `tools/fleet_audit.py` holds that as AST rules; only
  `boundary/` imports the gate surface.
- The default lane runs keyless, offline, no service; Postgres halves live behind
  `RETINUE_PG_DSN` with the existing skip-or-required pattern.
- The clock is an argument everywhere; nothing reads `now()` inside an adapter or a predicate.
- TDD: failing test watched red first, then minimal implementation, then green. Where a natural
  red is impossible, the repository's measured-red practice applies, naming the assertion.
- Gates before EVERY commit, exit codes read unpiped: `python -m pytest` AND
  `bash tools/battery.sh`. Stage by name. Subjects under 72 chars, narrative bodies, no trailers.
- No em dashes in authored files (spaced hyphens " - "); "judgment" without an e after the g; no
  word-bounded claim adjectives built on prov-; no organisation or person names.
- The README's Designed-vs-Built row, the chokepoint limit line, the P3 clause, and proposal
  sections 15.1 and 17 move ONLY in Task 5, dated, after Tasks 1-4 are green with the real
  caller. Nothing moves on code existing (spec section 6).

## File Structure

- `src/retinue/boundary/approvals.py` - token model, digest helper, `ApprovalStore` protocol,
  `MemoryApprovalStore`, `PgApprovalStore`, `MemoryResolutionLog`, `PgResolutionLog`,
  `resolve()`, `validate_and_consume()`.
- `src/retinue/boundary/resolve.py` - the operator CLI (`python -m retinue.boundary.resolve`),
  DSN lane only; the memory lane resolves in-process through `resolve()`.
- `src/retinue/boundary/send_tool.py` - one new class constant beside its siblings, one keyword
  parameter, one pre-check block.
- `schema.sql` - `approvals` and `approval_consumptions` tables with append-only triggers, one
  `ALTER` for `review_queue.approved_by`.
- `demo/bridge.py` - the first caller that is not a test.
- Tests: `tests/boundary/test_approvals.py`, `tests/boundary/test_send_tool_approval.py`,
  `tests/boundary/test_bridge_demo.py`.

---

### Task 1: The token, the digest, and the dual approval stores

**Files:**
- Create: `src/retinue/boundary/approvals.py`
- Modify: `schema.sql` (append after the `review_queue` table)
- Test: `tests/boundary/test_approvals.py`

**Interfaces:**
- Consumes: `chaperone.policy.types.Draft` (fields `body`, `tool_name`, `recipient_domain`);
  the DSN skip pattern from `tests/boundary/test_review_queue.py:136-140`.
- Produces: `ApprovalToken` (frozen dataclass: `token: str`, `idempotency_key: str`,
  `body_digest: str`, `tool: str`, `recipient_domain: str`, `resolution_id: int`,
  `minted_at: datetime`, `expires_at: datetime`); `body_digest_of(body: str) -> str`;
  `ApprovalStore` protocol with `put_token(t: ApprovalToken) -> bool`,
  `get_token(token: str) -> ApprovalToken | None`, `consume(token: str, at: datetime) -> bool`;
  `MemoryApprovalStore()` and `PgApprovalStore(dsn: str)` implementing it.

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/boundary/test_approvals.py
"""The approval store contract, both halves. The Postgres tests skip without a DSN and FAIL
under RETINUE_PG_REQUIRED=1, the same posture test_review_queue.py:136-140 establishes."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, body_digest_of)

T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)


def token(tok="a" * 32, key="k-1", body="hello", tool="mcp__retinue__send_message",
          domain="example.test", res=1):
    return ApprovalToken(token=tok, idempotency_key=key, body_digest=body_digest_of(body),
                         tool=tool, recipient_domain=domain, resolution_id=res,
                         minted_at=T0, expires_at=T0 + timedelta(hours=24))


def test_the_digest_is_sha256_over_utf8_bytes():
    import hashlib
    assert body_digest_of("café") == hashlib.sha256("café".encode()).hexdigest()


def test_put_token_is_first_writer_wins_on_the_token_id():
    s = MemoryApprovalStore()
    assert s.put_token(token()) is True
    assert s.put_token(token(body="different")) is False
    assert s.get_token("a" * 32).body_digest == body_digest_of("hello")


def test_get_token_answers_none_for_a_token_never_minted():
    assert MemoryApprovalStore().get_token("b" * 32) is None


def test_consume_is_an_append_that_wins_exactly_once():
    s = MemoryApprovalStore()
    s.put_token(token())
    assert s.consume("a" * 32, T0) is True
    assert s.consume("a" * 32, T0) is False


def test_consume_of_a_never_minted_token_still_wins_only_once():
    # The consumption table is its own append; validity conjunction is the caller's job. A
    # consume row without a mint row is refusable garbage, never a crash.
    s = MemoryApprovalStore()
    assert s.consume("c" * 32, T0) is True
    assert s.consume("c" * 32, T0) is False


def _pg_store():
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped")
    from retinue.boundary.approvals import PgApprovalStore
    return PgApprovalStore(dsn)


def test_pg_half_honours_the_same_contract():
    s = _pg_store()
    tok = os.urandom(16).hex()
    t = token(tok=tok, key=f"k-{tok[:8]}")
    assert s.put_token(t) is True
    assert s.put_token(t) is False
    got = s.get_token(tok)
    assert got is not None and got.idempotency_key == t.idempotency_key
    assert s.consume(tok, T0) is True
    assert s.consume(tok, T0) is False
```

- [ ] **Step 2: Run to watch them fail**

Run: `python -m pytest tests/boundary/test_approvals.py -x`
Expected: FAIL at import (`No module named 'retinue.boundary.approvals'`)

- [ ] **Step 3: Write the module**

```python
# src/retinue/boundary/approvals.py
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
#: database read the exact text the adapter issues.
INSERT_TOKEN = ("INSERT INTO approvals (token, idempotency_key, body_digest, tool, "
                "recipient_domain, resolution_id, minted_at, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING")
SELECT_TOKEN = ("SELECT token, idempotency_key, body_digest, tool, recipient_domain, "
                "resolution_id, minted_at, expires_at FROM approvals WHERE token = %s")
INSERT_CONSUMPTION = ("INSERT INTO approval_consumptions (token, consumed_at) "
                      "VALUES (%s,%s) ON CONFLICT DO NOTHING")


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
```

- [ ] **Step 4: Append the DDL to schema.sql**

```sql
-- The approval bridge (spec: 2026-08-30-approval-bridge-design.md). Both tables are append-only
-- with the same trigger pair the touchpoints table carries: a mint row and a consumption row
-- are only ever inserted, and single use is the primary key refusing a second consumption.
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS approved_by TEXT;
CREATE TABLE IF NOT EXISTS approvals (
    token            TEXT PRIMARY KEY,
    idempotency_key  TEXT NOT NULL,
    body_digest      TEXT NOT NULL,
    tool             TEXT NOT NULL,
    recipient_domain TEXT NOT NULL,
    resolution_id    BIGINT NOT NULL,
    minted_at        TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL
);
DROP TRIGGER IF EXISTS trg_approvals_append_only ON approvals;
CREATE TRIGGER trg_approvals_append_only
    BEFORE UPDATE OR DELETE ON approvals
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
DROP TRIGGER IF EXISTS trg_approvals_no_truncate ON approvals;
CREATE TRIGGER trg_approvals_no_truncate
    BEFORE TRUNCATE ON approvals
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
CREATE TABLE IF NOT EXISTS approval_consumptions (
    token       TEXT PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL
);
DROP TRIGGER IF EXISTS trg_approval_consumptions_append_only ON approval_consumptions;
CREATE TRIGGER trg_approval_consumptions_append_only
    BEFORE UPDATE OR DELETE ON approval_consumptions
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
DROP TRIGGER IF EXISTS trg_approval_consumptions_no_truncate ON approval_consumptions;
CREATE TRIGGER trg_approval_consumptions_no_truncate
    BEFORE TRUNCATE ON approval_consumptions
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `python -m pytest tests/boundary/test_approvals.py -v`
Expected: memory tests PASS; the PG test SKIPS without a DSN (runs green with one).

- [ ] **Step 6: Gates, then commit**

```bash
python -m pytest
bash tools/battery.sh
git add src/retinue/boundary/approvals.py schema.sql tests/boundary/test_approvals.py
git commit -m "feat: a token is a row, and spending it is an append that wins once"
```

---

### Task 2: The resolution, its single update, and the atomic mint

**Files:**
- Modify: `src/retinue/boundary/approvals.py` (append)
- Create: `src/retinue/boundary/resolve.py`
- Test: `tests/boundary/test_approvals.py` (append)

**Interfaces:**
- Consumes: Task 1's `ApprovalToken`, `ApprovalStore`, `body_digest_of`.
- Produces: `MemoryResolutionLog()` and `PgResolutionLog(dsn)` with
  `record(row_id: int, at: datetime, approved_by: str) -> bool` (first-writer-wins);
  `resolve(*, row_id, verdict, at, approved_by, window, resolutions, approvals, key, body,
  tool, recipient_domain, token_id=None) -> ApprovalToken | None`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/boundary/test_approvals.py
from retinue.boundary.approvals import (MemoryResolutionLog, resolve)


def test_an_approving_resolution_writes_once_and_mints_a_bound_token():
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    t = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-1",
                window=timedelta(hours=24), resolutions=res, approvals=appr,
                key="k-7", body="hello", tool="mcp__retinue__send_message",
                recipient_domain="example.test", token_id="d" * 32)
    assert t is not None and t.resolution_id == 7
    assert t.body_digest == body_digest_of("hello")
    assert t.expires_at == T0 + timedelta(hours=24)
    assert appr.get_token("d" * 32) == t


def test_a_double_resolution_is_first_writer_wins_and_the_loser_mints_nothing():
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    first = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-1",
                    window=timedelta(hours=24), resolutions=res, approvals=appr,
                    key="k-7", body="hello", tool="t", recipient_domain="d",
                    token_id="e" * 32)
    second = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-2",
                     window=timedelta(hours=24), resolutions=res, approvals=appr,
                     key="k-7", body="hello", tool="t", recipient_domain="d",
                     token_id="f" * 32)
    assert first is not None and second is None
    assert appr.get_token("f" * 32) is None


def test_a_rejecting_resolution_writes_resolved_and_mints_nothing():
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    out = resolve(row_id=9, verdict="reject", at=T0, approved_by="reviewer-1",
                  window=timedelta(hours=24), resolutions=res, approvals=appr,
                  key="k-9", body="no", tool="t", recipient_domain="d")
    assert out is None
    assert res.record(9, T0, "reviewer-2") is False   # the row is already resolved
```

- [ ] **Step 2: Run to watch them fail**

Run: `python -m pytest tests/boundary/test_approvals.py -k resolution -v`
Expected: FAIL at import (`cannot import name 'MemoryResolutionLog'`)

- [ ] **Step 3: Implement**

```python
# append to src/retinue/boundary/approvals.py

class MemoryResolutionLog:
    """First-writer-wins over review rows: the memory half of the design's one named update."""

    def __init__(self) -> None:
        self._resolved: dict[int, tuple[datetime, str]] = {}

    def record(self, row_id: int, at: datetime, approved_by: str) -> bool:
        if row_id in self._resolved:
            return False
        self._resolved[row_id] = (at, approved_by)
        return True


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
    row and mints nothing. The caller supplies the binding material and the clock."""
    if not resolutions.record(row_id, at, approved_by):
        return None
    if verdict != "approve":
        return None
    token = ApprovalToken(token=token_id or secrets.token_hex(16), idempotency_key=key,
                          body_digest=body_digest_of(body), tool=tool,
                          recipient_domain=recipient_domain, resolution_id=row_id,
                          minted_at=at, expires_at=at + window)
    if not approvals.put_token(token):
        # A colliding token id under a caller-supplied id; CSPRNG ids do not collide in practice.
        return None
    return token
```

Note on atomicity: in the memory half the two writes are one single-threaded function; the PG
lane's CLI (below) wraps `record` and `put_token` in one connection transaction. A contract test
for the PG transaction rides in Task 4's durability step.

- [ ] **Step 4: The CLI for the DSN lane**

```python
# src/retinue/boundary/resolve.py
"""Operator CLI for the DSN lane: python -m retinue.boundary.resolve <row-id> --approve ...

Reads the review row's handoff for the binding material, resolves with the test-and-set, and
mints in the same transaction. The memory lane never uses this module; it resolves in-process
through `approvals.resolve`, which is the same verb with the same arguments.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from retinue.boundary.approvals import PgApprovalStore, PgResolutionLog, resolve


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m retinue.boundary.resolve")
    ap.add_argument("row_id", type=int)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true")
    group.add_argument("--reject", action="store_true")
    ap.add_argument("--by", required=True, help="the reviewer's identity, recorded on the row")
    ap.add_argument("--at", required=True, help="ISO timestamp; the clock is an argument")
    ap.add_argument("--window-hours", type=float, default=24.0)
    ap.add_argument("--dsn", required=True)
    args = ap.parse_args(argv)

    import psycopg
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT handoff FROM review_queue WHERE id = %s", (args.row_id,))
        row = cur.fetchone()
    if row is None:
        print(f"no review row {args.row_id}", file=sys.stderr)
        return 2
    handoff = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    token = resolve(row_id=args.row_id, verdict="approve" if args.approve else "reject",
                    at=datetime.fromisoformat(args.at), approved_by=args.by,
                    window=timedelta(hours=args.window_hours),
                    resolutions=PgResolutionLog(args.dsn), approvals=PgApprovalStore(args.dsn),
                    key=handoff.get("idempotency_key", ""), body=handoff.get("body", ""),
                    tool=handoff.get("tool", ""),
                    recipient_domain=handoff.get("recipient_domain", ""))
    if token is None:
        print("resolved: no token minted (rejection, or the row was already resolved)")
        return 0 if args.reject else 1
    print(f"resolved by {args.by}; token {token.token} expires {token.expires_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run all the new tests to watch them pass**

Run: `python -m pytest tests/boundary/test_approvals.py -v`
Expected: PASS (PG entries skip without a DSN)

- [ ] **Step 6: Gates, then commit**

```bash
python -m pytest
bash tools/battery.sh
git add src/retinue/boundary/approvals.py src/retinue/boundary/resolve.py tests/boundary/test_approvals.py
git commit -m "feat: the resolution is the mint, and its loser mints nothing"
```

---

### Task 3: The boundary pre-check inside attempt_send

**Files:**
- Modify: `src/retinue/boundary/send_tool.py` (the class-constant block at lines 115-119 and the
  body of `attempt_send` between the projection pre-check and `guarded_call`)
- Test: `tests/boundary/test_send_tool_approval.py`

**Interfaces:**
- Consumes: Task 1's `ApprovalStore`, `body_digest_of`; the existing `attempt_send` signature
  and `_boundary_handoff` helper; `ActContext.approval_token` (imported type, field at
  `chaperone/policy/act_classes.py:12`).
- Produces: `APPROVAL_UNVERIFIED = "boundary:approval_unverified"`;
  `validate_and_consume(*, token: str, key: str, draft, at: datetime, store: ApprovalStore)
  -> str | None` in `approvals.py` (None on success; a reason naming the failed leg otherwise);
  `attempt_send` gains keyword `approvals: ApprovalStore | None = None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/boundary/test_send_tool_approval.py
"""The pre-check's position and its burn rule. These tests drive attempt_send with the same
scripted transports and inert gateway the existing send-tool tests use; read those fixtures
first and reuse their helpers rather than re-authoring doubles (tests/boundary/test_hook.py and
the existing attempt_send tests are the pattern)."""
from datetime import datetime, timedelta, timezone

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, body_digest_of,
                                        validate_and_consume)

T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)


def minted(body, *, key="k-1", tool="mcp__retinue__send_message", domain="example.test",
           tok="a" * 32, hours=24):
    t = ApprovalToken(token=tok, idempotency_key=key, body_digest=body_digest_of(body),
                      tool=tool, recipient_domain=domain, resolution_id=1, minted_at=T0,
                      expires_at=T0 + timedelta(hours=hours))
    s = MemoryApprovalStore()
    assert s.put_token(t)
    return s


def test_a_valid_token_validates_and_is_consumed_exactly_once(draft_factory):
    d = draft_factory(body="hello")
    s = minted("hello")
    assert validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s) is None
    reason = validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
    assert reason is not None and "consum" in reason


def test_every_binding_leg_refuses_and_names_itself(draft_factory):
    d = draft_factory(body="hello")
    for kwargs, needle in [
        (dict(token="b" * 32), "minted"),                      # absent from the store
        (dict(key="k-OTHER"), "idempotency"),                  # re-aimed at a different act
        (dict(at=T0 + timedelta(hours=25)), "expire"),         # expired
    ]:
        s = minted("hello")
        call = dict(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
        call.update(kwargs)
        reason = validate_and_consume(**call)
        assert reason is not None and needle in reason


def test_a_changed_body_or_tool_or_domain_refuses(draft_factory):
    for change in [dict(body="tampered"), dict(tool_name="other_tool"),
                   dict(recipient_domain="elsewhere.test")]:
        d = draft_factory(body="hello", **{k: v for k, v in change.items() if k != "body"})
        if "body" in change:
            d = draft_factory(body=change["body"])
        s = minted("hello")
        reason = validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
        assert reason is not None


def test_a_binding_failure_does_not_burn_the_token(draft_factory):
    # Reads before the write: a mis-aimed attempt must not spend a token someone else earned.
    d = draft_factory(body="hello")
    s = minted("hello")
    assert validate_and_consume(token="a" * 32, key="k-OTHER", draft=d, at=T0, store=s)
    assert validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s) is None


# The attempt_send integration tests follow the existing send-tool test file's fixture pattern:
# build the draft, record, context (with context.approval_token set), scripted checker, inert
# gateway, memory queues and store, and call attempt_send with approvals=the memory store.
# Assert EFFECTS: the review queue's handoff class, the ledger's rows, the gateway's call count.

def test_missing_context_still_denies_as_projection_unavailable_even_with_a_token():
    ...  # context=None, approvals set: the queue receives PROJECTION_UNAVAILABLE, not the new class


def test_a_supplied_token_with_no_store_is_unverifiable_and_stops_before_the_gate():
    ...  # context.approval_token set, approvals=None: queue receives APPROVAL_UNVERIFIED,
    ...  # gateway never called


def test_an_invalid_token_stops_before_the_gate_with_the_boundary_class():
    ...  # bound to a different key: APPROVAL_UNVERIFIED handoff, gateway.calls == 0


def test_a_valid_token_reaches_the_gate_and_a_gate_denial_burns_it():
    ...  # scripted checker denies: the token is consumed (second validate refuses), no send row


def test_no_token_at_all_behaves_exactly_as_today():
    ...  # context.approval_token None, approvals provided: the imported presence check denies
    ...  # at tier 2 exactly as the existing tests pin; no APPROVAL_UNVERIFIED handoff appears
```

The five `...` bodies are written by the implementer against the existing send-tool test
fixtures; each must assert effects (queue class, ledger rows, gateway call count), never
invocations, and each is watched red first. `draft_factory` is a small conftest helper building
a `Draft` with overridable `body`, `tool_name`, `recipient_domain`; add it to
`tests/boundary/conftest.py` if no equivalent exists.

- [ ] **Step 2: Run to watch them fail**

Run: `python -m pytest tests/boundary/test_send_tool_approval.py -v`
Expected: FAIL at import (`cannot import name 'validate_and_consume'`)

- [ ] **Step 3: Implement validate_and_consume, then the pre-check**

```python
# append to src/retinue/boundary/approvals.py

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
```

```python
# send_tool.py: add beside the siblings at lines 115-119
APPROVAL_UNVERIFIED = "boundary:approval_unverified"

# attempt_send signature gains one keyword (after `store`):
#     approvals: "ApprovalStore | None" = None,
# and between the projection pre-check and guarded_call:
    if context.approval_token is not None:
        if approvals is None:
            reason = ("an approval token was supplied but no approval store was provided; "
                      "presence alone is not verification")
        else:
            from retinue.boundary.approvals import validate_and_consume
            reason = validate_and_consume(token=context.approval_token, key=key, draft=draft,
                                          at=occurred_at, store=approvals)
        if reason is not None:
            queues.put(REVIEW_QUEUE, _boundary_handoff(draft, APPROVAL_UNVERIFIED, reason))
            return None
```

Position argument, restated from the spec for the module docstring's order list: AFTER the
projection pre-check because a missing context is the more fundamental absence and must keep
denying as `projection_unavailable`; BEFORE `guarded_call` because the boundary verifies
binding, expiry and consumption before the imported gate sees the token, and the imported
presence check keeps holding exactly what it has always held. Update the module docstring's
numbered order to include the new step between its 3 and 4.

- [ ] **Step 4: Run all tests to watch them pass**

Run: `python -m pytest tests/boundary/ -v`
Expected: PASS, including every pre-existing send-tool test unmodified

- [ ] **Step 5: Gates, then commit**

```bash
python -m pytest
bash tools/battery.sh
git add src/retinue/boundary/approvals.py src/retinue/boundary/send_tool.py tests/boundary/test_send_tool_approval.py tests/boundary/conftest.py
git commit -m "feat: the boundary verifies an approval before the gate sees it"
```

---

### Task 4: The first caller that is not a test

**Files:**
- Create: `demo/bridge.py`
- Test: `tests/boundary/test_bridge_demo.py`

**Interfaces:**
- Consumes: everything above; `fixtures/payloads/captured_ask.json` (the body lives at
  `payload.tool_input.body`, the tool name at `payload.tool_name`); the inert gateway, scripted
  checker transport, cast and record construction from `demo/day2.py` (read it first and reuse
  its helpers or mirror its construction - the demo lane's transport performs no outward act,
  and that decision is preserved with its reason).
- Produces: `demo/bridge.py` with `main(argv: list[str] | None = None) -> int` supporting
  `--approve-as <name>` (scripted resolution for tests and CI) and an interactive y/n prompt
  without it.

- [ ] **Step 1: Write the failing test**

```python
# tests/boundary/test_bridge_demo.py
"""The end-to-end evidence: resolution -> mint -> validated, consumed, gated, ledgered send,
driven by the captured ask payload. This test is the evidence bar's first and sixth bullets."""
import json
from pathlib import Path

from demo.bridge import main

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads" / "captured_ask.json"


def test_the_captured_ask_drives_a_bridged_approval_end_to_end(capsys):
    assert main(["--approve-as", "reviewer-1"]) == 0
    out = capsys.readouterr().out
    body = json.loads(FIX.read_text(encoding="utf-8"))["payload"]["tool_input"]["body"]
    assert "resolved by reviewer-1" in out
    assert "allowed" in out.lower()
    assert "sent" in out.lower()          # the ledger row's kind, printed from the row
    assert str(len(body.encode())) in out  # body_bytes printed from the recorded touchpoint


def test_a_rejecting_operator_mints_nothing_and_nothing_sends(capsys):
    assert main(["--reject-as", "reviewer-1"]) == 1
    out = capsys.readouterr().out
    assert "no token" in out.lower()
    assert "sent" not in out.lower()
```

- [ ] **Step 2: Run to watch it fail**

Run: `python -m pytest tests/boundary/test_bridge_demo.py -v`
Expected: FAIL at import (`No module named 'demo.bridge'`)

- [ ] **Step 3: Write the script**

`demo/bridge.py` structure (the implementer reads `demo/day2.py` first and mirrors its
construction of record, cast, registry, scripted checker transport, inert gateway and confirm;
the fixture-loading and printing below are the contract):

```python
# demo/bridge.py
"""The approval bridge, driven end to end by the captured ask payload: enqueue, human
resolution, mint, validate, consume, gate, send, ledger. The tool body performs no outward act,
the decision demo/day2.py made and this script preserves with its reason: the demo lane's
transport is inert by design, and what the bridge proves is the path.

Flags: --approve-as NAME / --reject-as NAME resolve without a prompt (tests, CI); with neither,
the held draft prints and the operator answers y/n interactively.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from retinue.boundary.approvals import (MemoryApprovalStore, MemoryResolutionLog, resolve)
from retinue.boundary.send_tool import attempt_send

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "payloads" / "captured_ask.json"
T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m demo.bridge")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--approve-as")
    group.add_argument("--reject-as")
    args = ap.parse_args(argv)

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["payload"]
    body, tool = payload["tool_input"]["body"], payload["tool_name"]

    # ... build draft (thread, body, cited_fields=(), jurisdiction, domain, tool_name=tool),
    # record, cast, registry, queues (DurableQueues over a memory sink), ledger store, scripted
    # checker and inert gateway - mirroring demo/day2.py. Then:

    # 1. Enqueue the held draft, print it, and obtain the verdict.
    # 2. resolve(row_id=1, verdict=..., at=T0, approved_by=..., window=timedelta(hours=24),
    #            resolutions=MemoryResolutionLog(), approvals=approvals, key=KEY, body=body,
    #            tool=tool, recipient_domain=DOMAIN) -> token (print, or exit 1 on rejection)
    # 3. Build the ActContext through build_act_context with approval_token=token.token.
    # 4. attempt_send(..., approvals=approvals, ...) and print the decision, the ledger row's
    #    kind, delivery status and payload byte count, read back FROM THE STORE.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to watch them pass**

Run: `python -m pytest tests/boundary/test_bridge_demo.py -v`
Expected: PASS

- [ ] **Step 5: The Postgres durability leg (evidence bar, last bullet)**

Append to `tests/boundary/test_approvals.py`, in the DSN-skip pattern: a resolve-and-mint
through `PgResolutionLog` + `PgApprovalStore` wrapped in one connection where the UPDATE
succeeds and the INSERT is then forced to fail (a duplicate caller-supplied token id), asserting
the transaction leaves NEITHER write behind; and a plain durability round-trip (mint, reconnect,
get_token, consume once). If the one-transaction wrapper needs a small
`resolve_pg(dsn, ...)` helper in `resolve.py` to be testable, write it there and have `main`
call it.

Run: `python -m pytest tests/boundary/test_approvals.py -v` (skips keyless; green under a DSN)

- [ ] **Step 6: Gates, then commit**

```bash
python -m pytest
bash tools/battery.sh
git add demo/bridge.py tests/boundary/test_bridge_demo.py tests/boundary/test_approvals.py src/retinue/boundary/resolve.py
git commit -m "feat: a human resolution drives the chokepoint for the first time"
```

---

### Task 5: The documents move, dated, because the evidence exists

**Files:**
- Modify: `README.md` (the Designed-vs-Built row for the approval bridge; the limits bullet
  "No agent has ever driven the chokepoint"; the P3 clause "no caller outside its own module and
  its tests"; the Roadmap's first entry)
- Modify: `docs/architecture-proposal.md` (sections 15.1 and 17, dated amendments in the house
  style: what the sentence said, what ran, and when)

**Interfaces:**
- Consumes: green Tasks 1-4 and the demo script as the real caller. This task runs ONLY after
  `python -m pytest` is green including `test_bridge_demo.py`.

- [ ] **Step 1: Re-run the full suite and record the counts**

Run: `python -m pytest` then `bash tools/battery.sh` (both must be green before any doc moves;
paste the pass count into the commit body).

- [ ] **Step 2: Flip the row and amend the prose, dated**

Every touched sentence follows the house pattern: the old claim stays quoted or summarized, the
date and the evidence land beside it. The row flips Built with the date and the caller named
(`demo/bridge.py`). The limits bullet and the P3 clause are corrected as one fact with the row.
Sections 15.1 and 17 gain dated amendments citing the evidence bar's tests by name. The battery
runs over every touched file; watch for em dashes and the README table-consistency guards
(`test_plan_sync.py`, `test_fleet_audit.py` roster pins) and update any pinned count
deliberately, never by loosening.

- [ ] **Step 3: Gates, then commit**

```bash
python -m pytest
bash tools/battery.sh
git add README.md docs/architecture-proposal.md
git commit -m "docs: the bridge row flips on its evidence, and the limit comes off"
```

---

## Self-review notes

- Spec coverage: section 1 (Task 1), section 2 (Tasks 1-2), section 3 (Task 1), section 4
  (Task 3), section 5 (Task 4), section 6 (Tasks 4-5), section 7 (global constraints), section 8
  (out of scope, untouched). The re-aimed-send refusal (spec's amended bar) is Task 3's
  binding-leg tests; the double-resolution race is Task 2; PG durability is Task 4 step 5.
- The five `...` test bodies in Task 3 are deliberate implementer-authored steps against
  existing fixtures the plan cannot restate without staleness; their properties and red-first
  obligation are stated inline, which is this repository's measured practice for such cases.
- Type consistency checked: `ApprovalToken`, `ApprovalStore`, `body_digest_of`,
  `validate_and_consume`, `MemoryResolutionLog.record`, `resolve` signatures match across tasks.
