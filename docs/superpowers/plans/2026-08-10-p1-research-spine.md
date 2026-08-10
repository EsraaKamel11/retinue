# P1 Research Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** The research spine end-to-end through the default lane: ledger (touchpoints, projection,
`ActContext` feed, rendered block), the research agent with its contract and failure taxonomy, the
topology as data, the hook, the AST audit, fixtures, and the live capture smoke.

**Architecture:** Everything deterministic by default; the SDK is constructed as data and never
spawned in tests; chaperone is imported from the vendored wheel and never modified. The ledger is an
append-only touchpoint stream with the record as a pure projection. Spec:
`docs/superpowers/specs/2026-08-10-retinue-design.md` - it governs; where this plan and the spec
disagree, the spec wins.

**Tech Stack:** Python >=3.11 · pydantic >=2.7 · pydantic-ai / pydantic-evals 2.23 (offline doubles:
`TestModel`, `FunctionModel`) · claude-agent-sdk 0.2.130 (options as data only) · psycopg[binary]
>=3.1 · pytest.

## Global Constraints (verbatim from the spec; every task inherits them)

- Default lane: `pytest -q` green on a fresh clone - **no daemon, no network, no key**.
- Postgres lane: keyed on `RETINUE_PG_DSN`; unset = skip with printed reason; CI negative control
  turns skip into fail via `RETINUE_PG_REQUIRED=1`.
- **Never `pip install chaperone`** - the wheel at `vendor/chaperone-0.1.0-py3-none-any.whl` only.
- Org-name-free and client-token-free repo. The battery greps: em dashes · the two banned
  certainty adjectives (word-bounded; never spelled in any tracked file, this one included) ·
  client and organisation tokens from the untracked local list · stale model ids · the removed
  pydantic-ai 2.x result kwarg. Run before every commit that touches docs.
- Money is `Decimal`, never float; money comparisons use a tolerance, never `==`.
- **Test-inertness rule:** every constraint test is demonstrated red-with-constraint-removed at
  introduction, and the red run is recorded in the introducing commit's message.
- Timestamps injectable; `now()` only at the Postgres adapter edge.
- No policy code in this repo, ever. The fleet audit enforces import discipline instead.
- Commit messages: conventional prefixes, no trailers, no organisation names.

## File Structure

| Path | Responsibility |
|---|---|
| `src/retinue/ledger/models.py` | `Touchpoint`, `RelationshipRecord`, `DeliveryStatus`, `StoreUnavailable` |
| `src/retinue/ledger/store.py` | `TouchpointStore` protocol + `InMemoryStore` (the contract reference) |
| `src/retinue/ledger/postgres.py` | `PostgresStore` + `bootstrap(dsn)` applying `schema.sql` |
| `schema.sql` | The one idempotent schema (touchpoints, named index, append-only trigger) |
| `src/retinue/ledger/projection.py` | `project_record`, `build_act_context` (the six-field feed, tri-state) |
| `src/retinue/ledger/block.py` | `render_block` - budget raise + completeness raise + header contract |
| `src/retinue/specialists/research.py` | `Claim`, `ResearchBrief`, `resolve_source`, validator, agent factory, `RESEARCH_PROMPT` |
| `src/retinue/specialists/failures.py` | `MissingSource`, `MalformedCitation` - the retryable split |
| `src/retinue/orchestration/topology.py` | `AGENTS`, `TIERS`, `SPAWN_TOOLS`, `build_options(hook)` |
| `src/retinue/boundary/hook.py` | `decide(agent_type, tool_name)` + `pre_tool_use` composing chaperone's deterministic lane |
| `tools/fleet_audit.py` | AST import-discipline audit, one named rule per function |
| `fixtures/` | Frozen JSON, each with a `meta` block; `fixtures/payloads/` hook payloads (provisional until the smoke replaces them) |
| `src/retinue/synth/rosters.py` | Seeded deterministic roster generator (unjudged volume only) |
| `scripts/capture_smoke.py` | The live capture run, `RETINUE_LIVE=1`-gated; never imported by tests |
| `tests/…` | Mirrors `src/` per task below |

Tasks in dependency order; each independently reviewable.

---

### Task 1: Ledger models and the in-memory reference store

**Files:**
- Create: `src/retinue/ledger/__init__.py` (empty), `src/retinue/ledger/models.py`,
  `src/retinue/ledger/store.py`
- Test: `tests/ledger/test_store_contract.py`

**Interfaces:**
- Produces: `Touchpoint(idempotency_key: str, investor_id: str, mandate_id: str | None, kind: str,
  payload: dict, occurred_at: datetime, recorded_at: datetime, delivery_status: DeliveryStatus |
  None = None)` (frozen pydantic model); `DeliveryStatus = Literal["CONFIRMED", "FAILED",
  "UNVERIFIABLE"]`; `KINDS = frozenset({"contact", "stated_check_size", "pass_reason", "identity",
  "sent"})`; `StoreUnavailable(Exception)`; `TouchpointStore` protocol with
  `append(tp: Touchpoint) -> bool` (False = duplicate key, nothing written) and
  `touchpoints_for(investor_id: str) -> tuple[Touchpoint, ...]` (insertion order);
  `InMemoryStore()` implementing it.

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/ledger/test_store_contract.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.models import Touchpoint, KINDS
from retinue.ledger.store import InMemoryStore

T0 = datetime(2030, 1, 5, tzinfo=timezone.utc)
T1 = datetime(2030, 1, 6, tzinfo=timezone.utc)

def tp(key="k1", kind="contact", investor="inv-1", occurred=T0, **payload):
    return Touchpoint(idempotency_key=key, investor_id=investor, mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T1)

def test_append_then_read_in_insertion_order():
    s = InMemoryStore()
    assert s.append(tp("a")) is True
    assert s.append(tp("b", occurred=T1)) is True
    keys = [t.idempotency_key for t in s.touchpoints_for("inv-1")]
    assert keys == ["a", "b"]

def test_duplicate_idempotency_key_is_refused_without_error():
    s = InMemoryStore()
    assert s.append(tp("a")) is True
    assert s.append(tp("a")) is False          # same key: refused, not raised
    assert len(s.touchpoints_for("inv-1")) == 1

def test_touchpoints_are_frozen():
    t = tp("a")
    with pytest.raises(Exception):
        t.kind = "sent"

def test_unknown_kind_is_rejected_at_construction():
    with pytest.raises(Exception):
        tp("a", kind="mutation")

def test_bitemporal_fields_are_distinct_and_required():
    t = tp("a")
    assert t.occurred_at != t.recorded_at      # world-time vs system-time both carried
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/ledger/test_store_contract.py -q`
Expected: FAIL - `ModuleNotFoundError: retinue.ledger`.

- [ ] **Step 3: Implement models and store**

```python
# src/retinue/ledger/models.py
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
```

```python
# src/retinue/ledger/store.py
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/ledger/test_store_contract.py -q`
Expected: 5 passed.

- [ ] **Step 5: Inertness proof, then commit**

Temporarily comment the `_known_kind` validator body (`return v` only) and run: the unknown-kind
test must go RED. Restore, re-run green. Commit with the red run named:

```bash
git add src/retinue/ledger tests/ledger
git commit -m "feat: touchpoint models and the in-memory store contract (inertness: unknown-kind test shown red with the validator stubbed, then restored)"
```

---

### Task 2: The projection - record and the six-field ActContext feed

**Files:**
- Create: `src/retinue/ledger/projection.py`
- Test: `tests/ledger/test_projection.py`

**Interfaces:**
- Consumes: Task 1's store protocol and models; chaperone's `ActContext` from
  `chaperone.policy.act_classes` (six fields: `approval_token`, `tier`, `consented_jurisdictions`,
  `granted_tools`, `sent_count`, `send_cap`).
- Produces: `RelationshipRecord(investor_id, stated_check_size: Decimal | None, pass_reason:
  str | None, last_contact: datetime | None, jurisdiction: str | None, domain: str | None)`;
  `project_record(store, investor_id) -> RelationshipRecord | None` (None = store unavailable,
  never "empty"); `build_act_context(store, investor_id, *, granted_tools, tier, send_cap,
  approval_token=None) -> ActContext | None` (None = unavailable; the boundary pre-check consumes
  it in P3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/ledger/test_projection.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.models import Touchpoint, StoreUnavailable
from retinue.ledger.store import InMemoryStore
from retinue.ledger.projection import project_record, build_act_context

T = [datetime(2030, 1, d, tzinfo=timezone.utc) for d in (1, 2, 3, 4)]

def tp(key, kind, occurred, **payload):
    return Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T[3])

def seeded():
    s = InMemoryStore()
    s.append(tp("i", "identity", T[0], jurisdiction="US", domain="example.test"))
    s.append(tp("c1", "contact", T[1]))
    s.append(tp("k", "stated_check_size", T[2], amount="250000"))
    s.append(tp("c2", "contact", T[2]))
    return s

def test_record_fields_are_all_derived():
    r = project_record(seeded(), "inv-1")
    assert r.stated_check_size == Decimal("250000")
    assert r.last_contact == T[2]                       # max occurred_at of contact kinds
    assert (r.jurisdiction, r.domain) == ("US", "example.test")

def test_check_size_is_decimal_never_float():
    r = project_record(seeded(), "inv-1")
    assert isinstance(r.stated_check_size, Decimal)

def test_new_investor_is_a_true_zero_not_unavailable():
    ctx = build_act_context(InMemoryStore(), "inv-9", granted_tools=frozenset({"send_message"}),
                            tier=2, send_cap=5)
    assert ctx is not None and ctx.sent_count == 0      # zero-because-new is a real fact

class BrokenStore:
    def append(self, tp): raise AssertionError
    def touchpoints_for(self, investor_id): raise StoreUnavailable("connection refused")

def test_unavailable_store_is_none_never_zero():
    assert build_act_context(BrokenStore(), "inv-1", granted_tools=frozenset(),
                             tier=2, send_cap=5) is None
    assert project_record(BrokenStore(), "inv-1") is None

def test_sent_count_counts_only_sends():
    s = seeded()
    s.append(tp("s1", "sent", T[3]))
    ctx = build_act_context(s, "inv-1", granted_tools=frozenset(), tier=2, send_cap=5)
    assert ctx.sent_count == 1

def test_six_actcontext_fields_are_populated():
    ctx = build_act_context(seeded(), "inv-1", granted_tools=frozenset({"send_message"}),
                            tier=2, send_cap=5, approval_token=None)
    assert ctx.consented_jurisdictions == frozenset({"US"})
    assert ctx.granted_tools == frozenset({"send_message"})
    assert (ctx.tier, ctx.send_cap, ctx.approval_token) == (2, 5, None)
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError` on `projection`.

- [ ] **Step 3: Implement**

```python
# src/retinue/ledger/projection.py
"""The record is a pure projection of the touchpoint stream. There is no record write.

`None` from either function means THE STORE COULD NOT BE READ - a different fact from an empty
stream, and the boundary treats it as fail-closed (spec 5.2). Zero-because-new and
zero-because-the-query-failed must never reach the guard as the same value.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from chaperone.policy.act_classes import ActContext
from retinue.ledger.models import StoreUnavailable, Touchpoint
from retinue.ledger.store import TouchpointStore

@dataclass(frozen=True)
class RelationshipRecord:
    investor_id: str
    stated_check_size: Decimal | None
    pass_reason: str | None
    last_contact: datetime | None
    jurisdiction: str | None
    domain: str | None

def _rows(store: TouchpointStore, investor_id: str) -> tuple[Touchpoint, ...] | None:
    try:
        return store.touchpoints_for(investor_id)
    except StoreUnavailable:
        return None

def _last(rows, kind: str) -> Touchpoint | None:
    hits = [t for t in rows if t.kind == kind]
    return max(hits, key=lambda t: t.occurred_at) if hits else None

def project_record(store: TouchpointStore, investor_id: str) -> RelationshipRecord | None:
    rows = _rows(store, investor_id)
    if rows is None:
        return None
    check = _last(rows, "stated_check_size")
    passed = _last(rows, "pass_reason")
    ident = _last(rows, "identity")
    contacts = [t for t in rows if t.kind in ("contact", "sent")]
    return RelationshipRecord(
        investor_id=investor_id,
        stated_check_size=Decimal(check.payload["amount"]) if check else None,
        pass_reason=passed.payload.get("reason") if passed else None,
        last_contact=max(t.occurred_at for t in contacts) if contacts else None,
        jurisdiction=ident.payload.get("jurisdiction") if ident else None,
        domain=ident.payload.get("domain") if ident else None,
    )

def build_act_context(store: TouchpointStore, investor_id: str, *,
                      granted_tools: frozenset[str], tier: int, send_cap: int,
                      approval_token: str | None = None) -> ActContext | None:
    rows = _rows(store, investor_id)
    if rows is None:
        return None
    ident = _last(rows, "identity")
    juris = frozenset({ident.payload["jurisdiction"]}) if ident and "jurisdiction" in ident.payload else frozenset()
    return ActContext(
        approval_token=approval_token, tier=tier,
        consented_jurisdictions=juris, granted_tools=granted_tools,
        sent_count=sum(1 for t in rows if t.kind == "sent"), send_cap=send_cap,
    )
```

(If `ActContext`'s constructor differs on the installed wheel, the RED run names it; fix the call,
never the design.)

- [ ] **Step 4: Run to verify pass** - Expected: 7 passed.
- [ ] **Step 5: Commit**

```bash
git add src/retinue/ledger/projection.py tests/ledger/test_projection.py
git commit -m "feat: record-as-projection and the six-field ActContext feed with the unavailable-vs-empty tri-state"
```

---

### Task 3: The rendered block - budget, completeness, header contract

**Files:**
- Create: `src/retinue/ledger/block.py`
- Test: `tests/ledger/test_block.py`

**Interfaces:**
- Consumes: `RelationshipRecord` (Task 2).
- Produces: `BLOCK_HEADER = "# Relationship Record"` (a machine-checked contract - the P2 control
  eval's stripper matches it); `render_block(record, *, budget: int = 1024) -> str`;
  `BlockFieldMissing(Exception)` (names the field); `BlockBudgetExceeded(Exception)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ledger/test_block.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.projection import RelationshipRecord
from retinue.ledger.block import BLOCK_HEADER, BlockBudgetExceeded, BlockFieldMissing, render_block

def rec(**over):
    base = dict(investor_id="inv-1", stated_check_size=Decimal("250000"),
                pass_reason="stage too early", last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                jurisdiction="US", domain="example.test")
    base.update(over)
    return RelationshipRecord(**base)

def test_block_starts_with_the_header_contract():
    assert render_block(rec()).startswith(BLOCK_HEADER + "\n")

def test_missing_required_field_raises_naming_it():
    for hole in (None, ""):                       # absent-as-None and empty-string both refuse
        with pytest.raises(BlockFieldMissing, match="investor_id"):
            render_block(rec(investor_id=hole))

def test_optional_fields_render_as_stated_absent_not_invented():
    out = render_block(rec(stated_check_size=None))
    assert "stated_check_size: not stated" in out   # absence stated, never fabricated

def test_budget_exceeded_raises():
    with pytest.raises(BlockBudgetExceeded):
        render_block(rec(pass_reason="x" * 5000), budget=256)
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError` on `block`.
- [ ] **Step 3: Implement**

```python
# src/retinue/ledger/block.py
"""The record rendered into the prompt-riding block.

Two raises, never warnings: a partial block is the fabrication vector arriving through the
most-trusted component, and an over-budget block silently truncated is the same defect. The header
is a contract: the control eval's stripper matches it byte-for-byte (spec 7.1).
"""
from __future__ import annotations
from retinue.ledger.projection import RelationshipRecord

BLOCK_HEADER = "# Relationship Record"

class BlockFieldMissing(Exception): ...
class BlockBudgetExceeded(Exception): ...

_REQUIRED = ("investor_id",)          # identity is required; facts may honestly be absent

def render_block(record: RelationshipRecord, *, budget: int = 1024) -> str:
    for name in _REQUIRED:
        v = getattr(record, name)
        if v is None or v == "":
            raise BlockFieldMissing(f"required field {name} is absent, null, or empty")
    lines = [BLOCK_HEADER,
             f"investor: {record.investor_id}",
             f"stated_check_size: {record.stated_check_size if record.stated_check_size is not None else 'not stated'}",
             f"pass_reason: {record.pass_reason or 'none recorded'}",
             f"last_contact: {record.last_contact.isoformat() if record.last_contact else 'never'}",
             f"jurisdiction: {record.jurisdiction or 'unknown'}",
             f"domain: {record.domain or 'unknown'}"]
    out = "\n".join(lines) + "\n"
    if len(out.encode()) > budget:
        raise BlockBudgetExceeded(f"{len(out.encode())} bytes exceeds the {budget}-byte budget")
    return out
```

- [ ] **Step 4: Run to verify pass** - Expected: 4 passed.
- [ ] **Step 5: Inertness proof, then commit**

Stub the budget check (`if False:`), watch the budget test go RED; restore, green.

```bash
git add src/retinue/ledger/block.py tests/ledger/test_block.py
git commit -m "feat: the rendered block with budget and completeness raises (inertness: budget test shown red with the check stubbed)"
```

---

### Task 4: schema.sql and the Postgres adapter (DSN lane)

**Files:**
- Create: `schema.sql`, `src/retinue/ledger/postgres.py`, `tests/ledger/conftest.py`
- Modify: `tests/ledger/test_store_contract.py` (parametrize over both stores)
- Test: `tests/ledger/test_postgres_enforcement.py`

**Interfaces:**
- Consumes: Task 1's protocol and tests.
- Produces: `PostgresStore(dsn: str)` implementing `TouchpointStore`; `bootstrap(dsn: str) -> None`
  applying `schema.sql` idempotently; conftest fixture `store` parametrized
  `["memory", "postgres"]` where postgres skips without `RETINUE_PG_DSN` and **fails** under
  `RETINUE_PG_REQUIRED=1`.

- [ ] **Step 1: Write `schema.sql`**

```sql
-- schema.sql: idempotent; the whole migration story. Applies unchanged on the managed target.
CREATE TABLE IF NOT EXISTS touchpoints (
    idempotency_key TEXT PRIMARY KEY,
    investor_id     TEXT NOT NULL,
    mandate_id      TEXT,
    kind            TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    delivery_status TEXT CHECK (delivery_status IN ('CONFIRMED','FAILED','UNVERIFIABLE')),
    seq             BIGINT GENERATED ALWAYS AS IDENTITY
);
-- Named so a plan test can match it (spec 2.2): the projection's hot query.
CREATE INDEX IF NOT EXISTS idx_touchpoints_investor_ts
    ON touchpoints (investor_id, occurred_at);
-- Append-only: no UPDATE, no DELETE, enforced in the database not in prose.
CREATE OR REPLACE FUNCTION touchpoints_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'touchpoints is append-only'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touchpoints_append_only ON touchpoints;
CREATE TRIGGER trg_touchpoints_append_only
    BEFORE UPDATE OR DELETE ON touchpoints
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
```

- [ ] **Step 2: Write the conftest and the failing enforcement tests**

```python
# tests/ledger/conftest.py
import os, uuid
import pytest
from retinue.ledger.store import InMemoryStore

def _pg_store():
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset - the lane may not silently skip")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped (set it to run; docker-compose.yml is one way)")
    from retinue.ledger.postgres import PostgresStore, bootstrap
    bootstrap(dsn)
    return PostgresStore(dsn)

@pytest.fixture(params=["memory", "postgres"])
def store(request):
    return InMemoryStore() if request.param == "memory" else _pg_store()

@pytest.fixture()
def ns():
    """Per-test namespace. The Postgres table is append-only BY TRIGGER - it can never be
    truncated between runs, so isolation comes from unique keys and investor ids, not cleanup."""
    return uuid.uuid4().hex[:12]
```

```python
# tests/ledger/test_postgres_enforcement.py
"""Behaviours only a real database earns. Every test here skips without RETINUE_PG_DSN."""
import os
import pytest
psycopg = pytest.importorskip("psycopg")

DSN = os.environ.get("RETINUE_PG_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and os.environ.get("RETINUE_PG_REQUIRED") != "1",
    reason="RETINUE_PG_DSN unset: Postgres lane skipped")

def _conn():
    if not DSN:
        pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
    from retinue.ledger.postgres import bootstrap
    bootstrap(DSN)
    return psycopg.connect(DSN)

def test_update_and_delete_are_refused_by_trigger():
    with _conn() as c:
        c.execute("INSERT INTO touchpoints (idempotency_key, investor_id, kind, payload, occurred_at, recorded_at)"
                  " VALUES ('t-ap1','inv-1','contact','{}', now(), now()) ON CONFLICT DO NOTHING")
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("UPDATE touchpoints SET kind='sent' WHERE idempotency_key='t-ap1'")
        c.rollback()
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("DELETE FROM touchpoints WHERE idempotency_key='t-ap1'")
        c.rollback()

def test_projection_query_uses_the_named_index_not_a_seq_scan():
    with _conn() as c:
        # Sized so the planner would actually choose the index: ten rows seq-scan regardless.
        c.execute("""INSERT INTO touchpoints (idempotency_key, investor_id, kind, payload, occurred_at, recorded_at)
                     SELECT 'seed-'||g, 'inv-'||(g % 200), 'contact', '{}', now() - (g||' hours')::interval, now()
                     FROM generate_series(1, 5000) g ON CONFLICT DO NOTHING""")
        c.commit()
        c.execute("ANALYZE touchpoints")
        c.execute("EXPLAIN (FORMAT TEXT) SELECT * FROM touchpoints WHERE investor_id='inv-7' ORDER BY occurred_at")
        plan = "\n".join(r[0] for r in c.fetchall())
        assert "idx_touchpoints_investor_ts" in plan, f"planner chose a different path:\n{plan}"
        assert "Seq Scan" not in plan, f"seq scan accepted would make this gate vacuous:\n{plan}"
```

- [ ] **Step 3: Run without a DSN** - Expected: enforcement tests SKIP with the printed reason;
  contract tests run on memory only. Then run once with
  `RETINUE_PG_REQUIRED=1` and no DSN - Expected: FAIL (the negative control works).

- [ ] **Step 4: Implement the adapter**

```python
# src/retinue/ledger/postgres.py
"""Postgres adapter. now() never appears here for row data - timestamps arrive on the model."""
from __future__ import annotations
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from retinue.ledger.models import StoreUnavailable, Touchpoint

_SCHEMA = Path(__file__).resolve().parents[3] / "schema.sql"

def bootstrap(dsn: str) -> None:
    with psycopg.connect(dsn) as c:
        c.execute(_SCHEMA.read_text(encoding="utf-8"))

class PostgresStore:
    def __init__(self, dsn: str, table_suffix: str = "") -> None:
        self._dsn = dsn        # suffix reserved for test isolation; single table in P1

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
                rows = c.execute(
                    "SELECT idempotency_key, investor_id, mandate_id, kind, payload,"
                    " occurred_at, recorded_at, delivery_status FROM touchpoints"
                    " WHERE investor_id=%s ORDER BY seq", (investor_id,)).fetchall()
        except psycopg.OperationalError as exc:
            raise StoreUnavailable(str(exc)) from exc
        return tuple(Touchpoint(idempotency_key=r[0], investor_id=r[1], mandate_id=r[2],
                                kind=r[3], payload=r[4], occurred_at=r[5], recorded_at=r[6],
                                delivery_status=r[7]) for r in rows)
```

Rewrite `tests/ledger/test_store_contract.py` to consume the parametrized `store` fixture AND the
`ns` namespace - fixed keys like `"a"` would collide with prior runs' rows in the never-truncatable
Postgres table, and a fixed investor id would read them back. The rewritten tests:

```python
# tests/ledger/test_store_contract.py (Task 4 rewrite: fixture-driven, namespaced)
from datetime import datetime, timezone
import pytest
from retinue.ledger.models import Touchpoint

T0 = datetime(2030, 1, 5, tzinfo=timezone.utc)
T1 = datetime(2030, 1, 6, tzinfo=timezone.utc)

def tp(ns, key="k1", kind="contact", occurred=T0, **payload):
    return Touchpoint(idempotency_key=f"{ns}-{key}", investor_id=f"inv-{ns}", mandate_id="m-1",
                      kind=kind, payload=payload, occurred_at=occurred, recorded_at=T1)

def test_append_then_read_in_insertion_order(store, ns):
    assert store.append(tp(ns, "a")) is True
    assert store.append(tp(ns, "b", occurred=T1)) is True
    keys = [t.idempotency_key for t in store.touchpoints_for(f"inv-{ns}")]
    assert keys == [f"{ns}-a", f"{ns}-b"]

def test_duplicate_idempotency_key_is_refused_without_error(store, ns):
    assert store.append(tp(ns, "a")) is True
    assert store.append(tp(ns, "a")) is False
    assert len(store.touchpoints_for(f"inv-{ns}")) == 1

def test_touchpoints_are_frozen(ns):
    t = tp(ns, "a")
    with pytest.raises(Exception):
        t.kind = "sent"

def test_unknown_kind_is_rejected_at_construction(ns):
    with pytest.raises(Exception):
        tp(ns, "a", kind="mutation")

def test_bitemporal_fields_are_distinct_and_required(ns):
    t = tp(ns, "a")
    assert t.occurred_at != t.recorded_at
```

- [ ] **Step 5: Run both lanes** - default: contract green on memory + postgres skipped; with a DSN
  (docker-compose or local): everything green. Then commit:

```bash
git add schema.sql src/retinue/ledger/postgres.py tests/ledger
git commit -m "feat: postgres adapter, append-only trigger, named-index plan test, and the required-lane negative control"
```

---

### Task 5: Research contract, source resolution, failure taxonomy

**Files:**
- Create: `src/retinue/specialists/__init__.py`, `src/retinue/specialists/failures.py`,
  `src/retinue/specialists/research.py`
- Test: `tests/specialists/test_research_contract.py`

**Interfaces:**
- Produces: `Claim(claim: str, evidence: str, source: str, source_date: date, confidence: float,
  needs_identifier: bool = False, candidates: tuple[str, ...] = (), quantity_key: str | None =
  None)` (frozen; `source_date` mandatory - no default); `ResearchBrief(claims:
  tuple[Claim, ...])`; `resolve_source(source: str, doc_ids: frozenset[str]) -> str | None`
  (containment, not equality); `validate_brief(brief, doc_ids) -> None` raising
  `MissingSource(claim=...)` or `MalformedCitation(claim=..., prior=...)`;
  `RESEARCH_PROMPT: str` (the coupled pair).

- [ ] **Step 1: Write the failing tests**

```python
# tests/specialists/test_research_contract.py
from datetime import date
import pytest
from retinue.specialists.failures import MalformedCitation, MissingSource
from retinue.specialists.research import (Claim, ResearchBrief, RESEARCH_PROMPT,
                                          resolve_source, validate_brief)

DOCS = frozenset({"doc-1", "doc-2"})

def claim(**over):
    base = dict(claim="fund writes early checks", evidence="page 4", source="doc-1 (filing, p.4)",
                source_date=date(2030, 1, 2), confidence=0.8)
    base.update(over)
    return Claim(**base)

def test_source_resolution_is_containment_not_equality():
    assert resolve_source("doc-1 (filing, p.4)", DOCS) == "doc-1"   # qualified citation resolves
    assert resolve_source("doc-9", DOCS) is None

def test_undated_claim_cannot_be_constructed():
    with pytest.raises(Exception):
        Claim(claim="x", evidence="y", source="doc-1", confidence=0.5)   # no source_date

def test_missing_source_is_never_retryable_and_names_the_claim():
    bad = ResearchBrief(claims=(claim(source="doc-9"),))
    with pytest.raises(MissingSource) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is False

def test_malformed_citation_is_retryable_and_carries_the_prior_value():
    bad = ResearchBrief(claims=(claim(source=""),))
    with pytest.raises(MalformedCitation) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is True and e.value.prior == ""

def test_ambiguity_is_flagged_never_guessed():
    c = claim(needs_identifier=True, candidates=("Fund A", "Fund A II"))
    assert c.candidates == ("Fund A", "Fund A II")

def test_prompt_and_validator_are_a_coupled_pair():
    # The prompt must name the same conventions the validator checks - edited together.
    assert "source" in RESEARCH_PROMPT and "document id" in RESEARCH_PROMPT
    assert "refuse" in RESEARCH_PROMPT.lower()
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError`.
- [ ] **Step 3: Implement**

```python
# src/retinue/specialists/failures.py
"""The retryable split. A format failure can be fixed by the model; a missing source cannot -
'a document that does not mention the schedule is not going to start mentioning it after a
retry', and retrying it is an invitation to fabricate."""
class ResearchValidationError(Exception):
    retryable: bool = False

class MalformedCitation(ResearchValidationError):
    retryable = True
    def __init__(self, claim: str, prior: str) -> None:
        super().__init__(f"malformed citation on {claim!r}: {prior!r}")
        self.claim, self.prior = claim, prior

class MissingSource(ResearchValidationError):
    retryable = False
    def __init__(self, claim: str, source: str) -> None:
        super().__init__(f"no fixture document supports {claim!r} (cited {source!r}); escalating, not retrying")
        self.claim, self.source = claim, source
```

```python
# src/retinue/specialists/research.py
"""The research specialist's contract. The prompt and validate_brief are a COUPLED PAIR:
the prompt names the document-id convention the validator checks. Edit them together."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from retinue.specialists.failures import MalformedCitation, MissingSource

class Claim(BaseModel):
    model_config = ConfigDict(frozen=True)
    claim: str
    evidence: str
    source: str
    source_date: date                       # mandatory, no default: an undated claim raises
    confidence: float = Field(ge=0.0, le=1.0)   # recorded; routes nothing
    needs_identifier: bool = False
    candidates: tuple[str, ...] = ()
    quantity_key: str | None = None         # same-quantity claims group; conflicts are kept, not averaged

class ResearchBrief(BaseModel):
    model_config = ConfigDict(frozen=True)
    claims: tuple[Claim, ...]

def resolve_source(source: str, doc_ids: frozenset[str]) -> str | None:
    """Containment, not equality: live models emit qualified citations ('doc-3 (filing, p.4)')."""
    hits = [d for d in doc_ids if d in source]
    return max(hits, key=len) if hits else None

def validate_brief(brief: ResearchBrief, doc_ids: frozenset[str]) -> None:
    for c in brief.claims:
        if not c.source.strip():
            raise MalformedCitation(c.claim, c.source)
        if resolve_source(c.source, doc_ids) is None:
            raise MissingSource(c.claim, c.source)

RESEARCH_PROMPT = (
    "You research investors from the provided fixture documents only.\n"
    "Every claim MUST cite its source containing the exact document id (e.g. 'doc-3 (filing, p.4)')\n"
    "and carry the document's date. If no document supports a fact, refuse that claim entirely -\n"
    "never guess, never write a claim without a resolvable document id. If an entity is ambiguous,\n"
    "set needs_identifier and list the candidates instead of choosing."
)
```

- [ ] **Step 4: Run to verify pass** - Expected: 6 passed.
- [ ] **Step 5: Inertness proof, then commit** - stub `resolve_source` to return `"doc-1"`
  unconditionally; the missing-source test goes RED; restore.

```bash
git add src/retinue/specialists tests/specialists
git commit -m "feat: research contract with containment resolution and the retryable split (inertness: missing-source shown red with resolution stubbed)"
```

---

### Task 6: The research agent under offline doubles

**Files:**
- Modify: `src/retinue/specialists/research.py` (append the agent factory)
- Test: `tests/specialists/test_research_agent.py`

**Interfaces:**
- Consumes: Task 5's contract; pydantic-ai `Agent`, `FunctionModel`.
- Produces: `build_research_agent(model, *, doc_ids: frozenset[str]) -> Agent` with
  `output_type=ResearchBrief`,
  `retries=1`, and an output validator that re-raises `MissingSource` as terminal (wrapped so
  pydantic-ai does NOT retry it) while `MalformedCitation` raises `ModelRetry` carrying the prior
  value verbatim.

- [ ] **Step 1: Write the failing tests**

```python
# tests/specialists/test_research_agent.py
from datetime import date
import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart
from retinue.specialists.failures import MissingSource
from retinue.specialists.research import build_research_agent

DOCS = frozenset({"doc-1"})

def _brief_call(source: str):
    return ToolCallPart(tool_name="final_result", args={
        "claims": [{"claim": "writes early checks", "evidence": "p4", "source": source,
                    "source_date": "2030-01-02", "confidence": 0.8}]})

def test_valid_brief_passes_through():
    def fn(messages, info: AgentInfo):
        return ModelResponse(parts=[_brief_call("doc-1 (filing)")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    out = agent.run_sync("investor brief").output
    assert out.claims[0].source_date == date(2030, 1, 2)

def test_missing_source_escalates_with_zero_retries():
    calls = []
    def fn(messages, info: AgentInfo):
        calls.append(1)
        return ModelResponse(parts=[_brief_call("doc-9")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    with pytest.raises(Exception) as e:
        agent.run_sync("investor brief")
    assert len(calls) == 1                     # never retried: one call, then escalate
    assert "doc-9" in str(e.value)

def test_malformed_citation_is_retried_with_prior_value_in_the_retry_prompt():
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[_brief_call("" if len(seen) == 1 else "doc-1")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    out = agent.run_sync("investor brief").output
    assert out.claims[0].source == "doc-1"
    assert "''" in str(seen[1]) or '""' in str(seen[1])   # the prior offending value, verbatim
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError: build_research_agent`.
- [ ] **Step 3: Implement (append to research.py)**

```python
# append to src/retinue/specialists/research.py
from pydantic_ai import Agent, ModelRetry

class ResearchEscalation(Exception):
    """Terminal: wraps MissingSource so the agent loop cannot convert it into a retry."""

def build_research_agent(model, *, doc_ids: frozenset[str]) -> Agent:
    agent: Agent = Agent(model, output_type=ResearchBrief, retries=1,
                         instructions=RESEARCH_PROMPT)

    @agent.output_validator
    def _validate(output: ResearchBrief) -> ResearchBrief:
        try:
            validate_brief(output, doc_ids)
        except MalformedCitation as exc:
            raise ModelRetry(f"citation was {exc.prior!r} - malformed; cite a document id") from exc
        except MissingSource as exc:
            raise ResearchEscalation(str(exc)) from exc     # terminal, not a retry
        return output
    return agent
```

- [ ] **Step 4: Run to verify pass** - Expected: 3 passed. (If pydantic-ai 2.23 wraps the terminal
  exception, assert on the wrapper's chained cause; the RED run tells you the real surface.)
- [ ] **Step 5: Commit**

```bash
git add src/retinue/specialists/research.py tests/specialists/test_research_agent.py
git commit -m "feat: the research agent under FunctionModel - retry carries the prior value, missing-source escalates in one call"
```

---

### Task 7: Topology as data

**Files:**
- Create: `src/retinue/orchestration/__init__.py`, `src/retinue/orchestration/topology.py`
- Test: `tests/orchestration/test_topology.py`

**Interfaces:**
- Consumes: `claude_agent_sdk.types.AgentDefinition`, `ClaudeAgentOptions`; Task 8's hook (by
  import; registered as callback).
- Produces: `SPAWN_TOOLS = ("Agent", "Task")`; `TIERS = {"orchestrator": "sonnet-tier",
  "research": "haiku-tier", "drafting": "haiku-tier", "conversation": "sonnet-tier"}`;
  `AGENTS: dict[str, AgentDefinition]` (P1 defines all four; only research is exercised);
  `build_options(hook) -> ClaudeAgentOptions`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/orchestration/test_topology.py
from retinue.orchestration.topology import AGENTS, SPAWN_TOOLS, TIERS, build_options

async def _noop_hook(input_data, tool_use_id, context):
    return {}

def test_every_agent_is_foreground():
    for name, d in AGENTS.items():
        assert getattr(d, "background", None) is False, f"{name} must set background=False"

def test_research_has_no_outbound_tool_at_all():
    tools = AGENTS["research"].tools or []
    assert all("send" not in t.lower() for t in tools)
    assert "WebFetch" not in tools and "WebSearch" not in tools

def test_orchestrator_holds_only_the_spawn_tool():
    opts = build_options(_noop_hook)
    assert set(opts.allowed_tools) == set(SPAWN_TOOLS)   # both names as data; runtime binds one

def test_tiers_use_the_imported_vocabulary_exactly():
    assert set(TIERS.values()) <= {"haiku-tier", "sonnet-tier", "opus-tier"}

def test_hook_is_registered_once_on_pre_tool_use():
    opts = build_options(_noop_hook)
    matchers = opts.hooks["PreToolUse"]
    assert len(matchers) == 1 and _noop_hook in matchers[0].hooks
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError`.
- [ ] **Step 3: Implement**

```python
# src/retinue/orchestration/topology.py
"""The topology as inspectable data. These objects are asserted by tests and rendered by docs;
nothing here spawns anything. Model tiers use the imported MODEL_STRENGTH vocabulary so the
checker-ordering guarantee reads straight off this table."""
from __future__ import annotations
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import AgentDefinition

SPAWN_TOOLS = ("Agent", "Task")   # renamed at CLI 2.1.63; both listed, runtime binds one

TIERS = {"orchestrator": "sonnet-tier", "research": "haiku-tier",
         "drafting": "haiku-tier", "conversation": "sonnet-tier"}

AGENTS: dict[str, AgentDefinition] = {
    "research": AgentDefinition(
        description="Researches investors from fixture documents; cites or refuses.",
        prompt="Use only the provided fixture documents. Cite document ids. Refuse unsupported claims.",
        tools=["Read", "Grep", "Glob"], background=False),
    "drafting": AgentDefinition(
        description="Drafts outreach from the relationship record. Output goes to review.",
        prompt="Draft from the record only.", tools=["Read"], background=False),
    "conversation": AgentDefinition(
        description="Carries investor conversation; sends are gated.",
        prompt="Converse; sending is gated.", tools=["Read"], background=False),
}

def build_options(hook) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        agents=AGENTS,
        allowed_tools=list(SPAWN_TOOLS),
        permission_mode="default",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook])]},
    )
```

(Exact `AgentDefinition`/`HookMatcher` kwargs are camelCase in places; the RED run against the
installed 0.2.130 names any mismatch - fix the call, never the table's content.)

- [ ] **Step 4: Run to verify pass** - Expected: 5 passed.
- [ ] **Step 5: Inertness proof, then commit** - set research `background=None`, foreground test
  RED; restore.

```bash
git add src/retinue/orchestration tests/orchestration
git commit -m "feat: topology as data - foreground everywhere, spawn-only orchestrator, tier vocabulary exact (inertness: background test shown red)"
```

---

### Task 8: The hook

**Files:**
- Create: `src/retinue/boundary/__init__.py`, `src/retinue/boundary/hook.py`
- Create: `fixtures/payloads/provisional_send.json`, `fixtures/payloads/provisional_research.json`
- Test: `tests/boundary/test_hook.py`

**Interfaces:**
- Consumes: `chaperone.gates.sdk_callback.pre_tool_use_deny` (async: payload in, deny-dict or `{}`).
- Produces: `SEND_TOOLS = frozenset({"send_message"})`; `decide(agent_type: str | None,
  tool_name: str) -> Literal["allow", "ask"]`; `async pre_tool_use(input_data, tool_use_id,
  context) -> dict` - the ONE parent-registered hook: routing first, then chaperone's
  deterministic lane for send payloads.

- [ ] **Step 1: Write the provisional payload fixtures** (replaced by the smoke's captures;
  marked). JSON permits no comments - the blocks below are the COMPLETE file contents.

File `fixtures/payloads/provisional_send.json`:

```json
{"meta": {"provisional": true, "note": "hand-authored; replaced by the P1 capture smoke"},
 "payload": {"tool_name": "send_message", "agent_type": "conversation",
             "tool_input": {"body": "The round is $9M.", "record": {"round_size": "8000000"},
                            "cited_fields": ["round_size"]}}}
```

File `fixtures/payloads/provisional_research.json`:

```json
{"meta": {"provisional": true, "note": "hand-authored; replaced by the P1 capture smoke"},
 "payload": {"tool_name": "Read", "agent_type": "research",
             "tool_input": {"file_path": "fixtures/docs/doc-1.md"}}}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/boundary/test_hook.py
import asyncio, json
from pathlib import Path
import pytest
from retinue.boundary.hook import decide, pre_tool_use

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads"

def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))["payload"]

def test_decision_table_is_total():
    assert decide(None, "anything") == "allow"                 # main thread
    assert decide("research", "Read") == "allow"
    assert decide("drafting", "Read") == "allow"
    assert decide("conversation", "send_message") == "ask"
    assert decide("conversation", "Read") == "allow"           # non-send conversation tool
    assert decide("mystery", "Read") == "ask"                  # unknown fails toward the human

def test_outward_send_returns_ask_shape():
    out = asyncio.run(pre_tool_use(load("provisional_send.json"), None, None))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "ask"

def test_research_read_passes_untouched():
    assert asyncio.run(pre_tool_use(load("provisional_research.json"), None, None)) == {}

def test_main_thread_send_still_runs_the_deterministic_lane():
    p = load("provisional_send.json"); p.pop("agent_type")
    out = asyncio.run(pre_tool_use(p, None, None))
    spec = out.get("hookSpecificOutput", {})
    assert spec.get("permissionDecision") == "deny"            # figure-not-in-record denies
    assert "act:" in spec.get("permissionDecisionReason", "")
```

- [ ] **Step 3: Run to verify failure** - Expected: `ImportError`.
- [ ] **Step 4: Implement**

```python
# src/retinue/boundary/hook.py
"""The one parent-registered PreToolUse hook. Routing first (a table, total by test), then the
imported deterministic lane on send payloads. The checker never runs here - it runs at the
chokepoint inside the send tool body (P3). Unknown agent_type fails toward the human."""
from __future__ import annotations
from chaperone.gates.sdk_callback import pre_tool_use_deny

SEND_TOOLS = frozenset({"send_message"})

def decide(agent_type: str | None, tool_name: str) -> str:
    if agent_type is None:
        return "allow"
    if agent_type in ("research", "drafting"):
        return "allow"
    if agent_type == "conversation":
        return "ask" if tool_name in SEND_TOOLS else "allow"
    return "ask"

def _ask(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "ask",
                                   "permissionDecisionReason": reason}}

async def pre_tool_use(input_data: dict, tool_use_id, context) -> dict:
    agent_type = input_data.get("agent_type")
    tool_name = input_data.get("tool_name", "")
    verdict = decide(agent_type, tool_name)
    if verdict == "ask":
        return _ask(f"outward action by {agent_type or 'unknown'} requires a human")
    if tool_name in SEND_TOOLS:
        return await pre_tool_use_deny(input_data, tool_use_id, context)
    return {}
```

- [ ] **Step 5: Run to verify pass** - Expected: 4 passed. (Payload key for agent identity may be
  `agent_type` nested differently in real captures; the smoke's fixtures arbitrate in Task 10 and
  this module adapts THEN, never speculatively.)
- [ ] **Step 6: Commit**

```bash
git add src/retinue/boundary fixtures/payloads tests/boundary
git commit -m "feat: the one hook - total decision table, ask on outward sends, imported deterministic lane on send payloads"
```

---

### Task 9: The AST audit

**Files:**
- Create: `tools/fleet_audit.py`
- Test: `tests/test_fleet_audit.py`

**Interfaces:**
- Produces: `audit(root: Path) -> list[str]` (empty = clean; each entry names the broken rule);
  rules: `only_boundary_imports_gates` (only `boundary/` imports `chaperone.gates.hook` /
  `chaperone.gates.sdk_callback` / `chaperone.audit`), `specialists_import_no_gates`,
  `send_tool_single_home` (the literal `send_message` tool name defined in at most one module
  under `src/retinue/`). CLI: `python tools/fleet_audit.py` exits 1 on findings.

- [ ] **Step 1: Write the failing tests (with planted violations - the negative controls)**

```python
# tests/test_fleet_audit.py
from pathlib import Path
import subprocess, sys, textwrap
from tools.fleet_audit import audit

ROOT = Path(__file__).resolve().parents[1]

def test_the_real_tree_is_clean():
    assert audit(ROOT / "src" / "retinue") == []

def test_gates_import_outside_boundary_is_caught(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "specialists"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("from chaperone.gates.hook import guarded_call\n")
    findings = audit(tmp_path / "src" / "retinue")
    assert any("specialists_import_no_gates" in f for f in findings)

def test_a_mention_in_a_docstring_is_not_an_import(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "specialists"; pkg.mkdir(parents=True)
    (pkg / "ok.py").write_text('"""chaperone.gates.hook is discussed here, not imported."""\n')
    assert audit(tmp_path / "src" / "retinue") == []          # grep would flag this; AST must not

def test_cli_exit_codes():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "fleet_audit.py")], capture_output=True)
    assert r.returncode == 0
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError: tools.fleet_audit`.
- [ ] **Step 3: Implement**

```python
# tools/fleet_audit.py
"""Import discipline as AST rules - one named rule per function, each with a planted-violation
test proving it fires. Grep is defeated by a docstring, a comment, or a string literal, and
cannot tell an import from a mention; ast.walk over Import/ImportFrom can."""
from __future__ import annotations
import ast, sys
from pathlib import Path

GATE_MODULES = ("chaperone.gates.hook", "chaperone.gates.sdk_callback", "chaperone.audit")

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out

def audit(root: Path) -> list[str]:
    findings: list[str] = []
    send_homes: list[Path] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        mods = _imports(py)
        gate_hits = [m for m in mods if any(m.startswith(g) for g in GATE_MODULES)]
        if gate_hits and rel.parts[0] != "boundary":
            rule = ("specialists_import_no_gates" if rel.parts[0] == "specialists"
                    else "only_boundary_imports_gates")
            findings.append(f"{rule}: {rel} imports {sorted(gate_hits)}")
        if '"send_message"' in py.read_text(encoding="utf-8") and rel.parts[0] != "boundary":
            send_homes.append(rel)
    if send_homes:
        findings.append(f"send_tool_single_home: send tool named outside boundary/: {send_homes}")
    return findings

if __name__ == "__main__":
    found = audit(Path(__file__).resolve().parents[1] / "src" / "retinue")
    for f in found:
        print(f, file=sys.stderr)
    sys.exit(1 if found else 0)
```

- [ ] **Step 4: Run to verify pass** - Expected: 4 passed (the planted violations ARE the
  negative controls - each rule demonstrated firing).
- [ ] **Step 5: Commit**

```bash
git add tools/fleet_audit.py tests/test_fleet_audit.py
git commit -m "feat: AST import audit with planted-violation negative controls per named rule"
```

---

### Task 10: Fixtures, the roster generator, and the capture smoke

**Files:**
- Create: `fixtures/docs/doc-1.md`, `fixtures/docs/doc-2.md` (short synthetic investor documents;
  invented names and figures only), `src/retinue/synth/__init__.py`,
  `src/retinue/synth/rosters.py`, `scripts/capture_smoke.py`
- Test: `tests/synth/test_rosters.py`, `tests/test_fixture_meta.py`

**Interfaces:**
- Produces: `generate_rosters(seed: int, n: int) -> tuple[dict, ...]` (deterministic; invented
  figures); the smoke script (RETINUE_LIVE=1-gated, never imported by tests) writing
  `fixtures/payloads/captured_*.json` with `meta.captured = {"sdk": "0.2.130", "cli": "2.1.222"}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/synth/test_rosters.py
from retinue.synth.rosters import generate_rosters

def test_same_seed_same_rosters():
    assert generate_rosters(7, 5) == generate_rosters(7, 5)

def test_different_seed_differs():
    assert generate_rosters(7, 5) != generate_rosters(8, 5)
```

```python
# tests/test_fixture_meta.py
"""Every frozen fixture carries a meta block; captured ones carry the version stamp."""
import json
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures"

def test_every_fixture_json_has_meta():
    for p in FIX.rglob("*.json"):
        meta = json.loads(p.read_text(encoding="utf-8")).get("meta")
        assert meta, f"{p} has no meta block"
        assert meta.get("provisional") or meta.get("captured"), f"{p}: neither provisional nor captured"
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/synth/rosters.py
"""Seeded generator for UNJUDGED volume only (spec 7.2): rosters the matcher filters.
Judged content is hand-authored and frozen - never generated. All figures invented."""
from __future__ import annotations
import random

_SECTORS = ("logistics", "devtools", "climate", "health-admin")
_JURIS = ("US", "UK", "DE")

def generate_rosters(seed: int, n: int) -> tuple[dict, ...]:
    rng = random.Random(seed)
    return tuple(
        {"investor_id": f"synth-{i:03d}",
         "sector": rng.choice(_SECTORS),
         "jurisdiction": rng.choice(_JURIS),
         "check_floor": rng.choice((100_000, 300_000, 700_000)),
         "check_ceiling": rng.choice((1_500_000, 4_000_000, 9_000_000))}
        for i in range(n))
```

```python
# scripts/capture_smoke.py
"""The P1 live capture smoke (spec 2.3). RETINUE_LIVE=1 gated; never imported by tests; run
manually, once; its outputs are the canonical captured fixtures the default lane replays.

Session shape: orchestrator + research subagent ONLY - no send tool exists anywhere, so this run
cannot ask and does not try to. It captures: hook payloads with agent_type populated, the spawn
tool's real naming, and the background evidence pair (one run background-unset, one
background=False)."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: capture smoke is manual and keyed; not running.")
        return 0
    from claude_agent_sdk import ClaudeSDKClient
    from retinue.orchestration.topology import build_options
    captured: list[dict] = []

    async def recording_hook(input_data, tool_use_id, context):
        captured.append({"meta": {"captured": {"sdk": "0.2.130", "cli": "2.1.222"}},
                         "payload": input_data})
        from retinue.boundary.hook import pre_tool_use
        return await pre_tool_use(input_data, tool_use_id, context)

    async with ClaudeSDKClient(options=build_options(recording_hook)) as client:
        await client.query("Use the research agent to summarise fixtures/docs/doc-1.md")
        async for _ in client.receive_response():
            pass
    out = Path("fixtures/payloads")
    for i, item in enumerate(captured):
        (out / f"captured_{i:02d}.json").write_text(json.dumps(item, indent=1), encoding="utf-8")
    print(f"captured {len(captured)} payloads")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

Write `fixtures/docs/doc-1.md` / `doc-2.md` as ~10-line synthetic investor notes (invented fund
names, invented figures; no real firm's published ranges).

- [ ] **Step 3: Run the default suite** - Expected: all green; the smoke never runs in tests
  (verify: `grep -r "capture_smoke" tests/` is empty).
- [ ] **Step 4: Commit**

```bash
git add fixtures src/retinue/synth scripts tests/synth tests/test_fixture_meta.py
git commit -m "feat: synthetic fixtures, seeded roster generator, and the RETINUE_LIVE-gated capture smoke"
```

---

### Task 11: README seed and the battery

**Files:**
- Create: `README.md`, `tools/battery.sh`
- Test: (the battery is the test; run it)

- [ ] **Step 1: Write `tools/battery.sh`**

```bash
#!/usr/bin/env bash
# The repo battery (spec section 11). Zero hits expected on every grep.
set -u
fail=0
say() { printf "%-40s %s\n" "$1" "$2"; }
docs=$(git ls-files '*.md')
# Patterns are CONSTRUCTED, never spelled: every tracked file, this script and the plan that
# embeds it included, must pass the battery it defines.
EMD=$(printf 'â')
n=$(grep -c "$EMD" $docs 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
[ "$n" -eq 0 ] && say "em dashes" "ok" || { say "em dashes" "$n FAIL"; fail=1; }
for t in prov{able,en}; do
  n=$(grep -cwi "$t" $docs 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
  [ "$n" -eq 0 ] && say "adjective $t" "ok" || { say "adjective $t" "$n FAIL"; fail=1; }
done
# Client/organisation tokens: list maintained OUTSIDE this script (a battery that names its own
# banned tokens fails on its own specification). Reads one token per line, comments allowed.
if [ -f tools/banned_tokens.txt ]; then
  while read -r tok; do
    case "$tok" in ''|'#'*) continue;; esac
    n=$(grep -rci "$tok" $docs src tests 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
    [ "$n" -eq 0 ] && say "token" "ok" || { say "token [redacted]" "$n FAIL"; fail=1; }
  done < tools/banned_tokens.txt
fi
python tools/fleet_audit.py || fail=1
python -m pytest -q || fail=1
exit $fail
```

Create `tools/banned_tokens.txt` locally with one token per line, copied from the governing plan's
list (maintained outside this repo). **The file is NEVER committed** - add `tools/banned_tokens.txt`
to `.gitignore` in this task. A tracked list would ship the very tokens it bans into the repo a
reviewer receives; that is why the battery treats the file as optional (a fresh clone runs the
battery without the token pass - those greps belong to the author's pipeline, not the reviewer's)
and prints `[redacted]` on a hit rather than the token.

- [ ] **Step 2: Write `README.md`** - short: what retinue is (three sentences from the spec's
  header), install (`pip install -r requirements.txt`), the three lanes with their env vars, and
  the Designed-vs-Built table copied from spec section 12 with P1 rows flipped to **Built** as
  they land (each flip in the same commit as its feature - never before).

- [ ] **Step 3: Run the battery** - Expected: exit 0, every line ok.
- [ ] **Step 4: Commit**

```bash
git add README.md tools/battery.sh .gitignore
git commit -m "docs: README seed with the Designed-vs-Built table, and the battery with an untracked local token list"
```

---

## Self-Review (performed at write time)

**Spec coverage:** 2.1 default lane → Tasks 1-3, 5-9; 2.2 Postgres lane incl. named-index plan
test and negative control → Task 4; 2.3 capture smoke → Task 10; 3 topology + decision table →
Tasks 7-8; 4.1/4.4 contract + taxonomy → Tasks 5-6; 5.1-5.3 ledger/projection/block → Tasks 1-3;
6 AST audit → Task 9; 7.2 fixture provenance meta → Task 10; 11 battery → Task 11. Not in P1 by
spec: the boundary pre-check consumer (P3), matching (P2), the block-stripped control (P2), judge
capture (P2), `pre_tool_use` pre-flight (P3).
**Placeholders:** none - every step carries real code or an exact command.
**Type consistency:** `Touchpoint`/`TouchpointStore` (T1) consumed by T2/T4 under the same names;
`RelationshipRecord` (T2) consumed by T3; `build_research_agent(model, *, doc_ids)` consistent
between T5's exports and T6's tests; `build_options(hook)` consistent between T7 and T10's smoke;
`pre_tool_use(input_data, tool_use_id, context)` matches chaperone's callback arity everywhere.
**Known adaptation points, named not hidden:** chaperone `ActContext` constructor kwargs (T2),
pydantic-ai terminal-exception wrapping (T6), SDK camelCase kwargs (T7), the captured payload's
real agent-identity key (T8/T10) - each marked "the RED run names it; fix the call, never the
design."
