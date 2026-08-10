# retinue Implementation Plan (P1-P4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** The full retinue build across the spec's four phases - P1 the research spine, P2
matching plus the evaluation harness, P3 drafting plus the chokepoint, P4 conversation plus the
live demo.

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
- Commit messages: conventional prefixes, no trailers, no organisation names. Subject under about
  72 characters, narrative in the body after a blank line. **The `git commit -m` lines in the task
  steps are illustrative of CONTENT, not of formatting** - several carry a whole paragraph as one
  subject. Where a step's `-m` string exceeds the subject limit, split it: the rule governs, the
  snippet does not.

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
| `src/retinue/ledger/outcomes.py` | `OutcomeRecord`, the parameterized signal enum, last-touch attribution |
| `src/retinue/matching/integrate.py` | Roster + ledger -> chaperone `Candidate`; `shortlist` over the imported `rank` |
| `src/retinue/evals/ranking.py` | Hand-rolled `HitAtN` / `MRR` evaluators (floats, names explicit) |
| `src/retinue/evals/frozen.py` | Frozen-judge replay: calibration and discrimination, separate |
| `src/retinue/evals/control.py` | The block-stripped control (stripper bound to `BLOCK_HEADER`) |
| `src/retinue/specialists/drafting.py` | `DRAFTING_PROMPT`, `build_draft` from the identity record, agent factory |
| `src/retinue/specialists/conversation.py` | `CONVERSATION_PROMPT`, `ConversationTurn` composing `Draft`, agent factory |
| `src/retinue/boundary/review_queue.py` | `DurableQueues`: imported in-process queues + the durable sink |
| `src/retinue/boundary/checker_lane.py` | `Checker` construction + the scripted (frozen-verdict) transport |
| `src/retinue/boundary/send_tool.py` | `attempt_send`: terminal guard, boundary pre-check, `guarded_call`, tri-state touchpoint |
| `src/retinue/boundary/preflight.py` | The imported full-lane `pre_tool_use` as pre-flight; two-signal routing |
| `scripts/judge_capture.py` | Live judge capture (RETINUE_LIVE=1); writes frozen verdicts |
| `scripts/demo.py` | The P4 live demo: offer asserted, ask captured (RETINUE_LIVE=1) |
| `tests/...` | Mirrors `src/` per task below |

Tasks in dependency order; each independently reviewable. Phase boundaries are the spec's
(section 9); every phase is independently demonstrable and no task depends on a later one.

---

## Phase 1 - research spine (Tasks 1-11)

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
    assert abs(r.stated_check_size - Decimal("250000")) < Decimal("0.01")   # tolerance, never ==
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

- [ ] **Step 4: Run to verify pass** - Expected: 6 passed (13 cumulative with Task 1's).
- [ ] **Step 5: Inertness proof, then commit** - stub `_rows` to return `()` on
  `StoreUnavailable`: both unavailable-is-None tests go RED (unavailable would collapse into
  empty, the exact confusion 5.2 forbids); restore, and name the red run in the commit message.

```bash
git add src/retinue/ledger/projection.py tests/ledger/test_projection.py
git commit -m "feat: record-as-projection and the six-field ActContext feed (inertness: unavailable-as-empty stub shown red)"
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

- [ ] **Step 1a: Write `docker-compose.yml`** - one documented way to supply the DSN, pinned to
  the same image the CI job uses. It is not the harness contract; any Postgres 16 will do.

```yaml
services:
  postgres:
    image: postgres:16.4
    environment:
      POSTGRES_PASSWORD: retinue
      POSTGRES_DB: retinue
    # 55432, not 5432: a locally installed Postgres commonly holds the default port.
    ports: ["55432:5432"]
    healthcheck:
      # -h 127.0.0.1 is the load-bearing flag, not -d: pg_isready's exit status comes from
      # PQping, which reports OK whenever the server answers at all, so -d cannot distinguish
      # the entrypoint's socket-only init phase from a server accepting TCP. Forcing the TCP
      # host makes the check fail while listen_addresses is still empty, which is the point.
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U postgres -d retinue"]
      interval: 2s
      timeout: 3s
      retries: 15
# Then: export RETINUE_PG_DSN=postgresql://postgres:retinue@localhost:55432/retinue
```

- [ ] **Step 1: Write `schema.sql`**

```sql
-- schema.sql: idempotent, and the whole migration story FOR P1 - creates, plus two DROP TRIGGER
-- statements that keep their creates re-runnable (CREATE TRIGGER has no IF NOT EXISTS). The one
-- exception is DROP INDEX IF EXISTS below: it is the file's only destructive migration action,
-- retiring an index an earlier revision created, where every other statement reaches an existing
-- database only by adding what it finds missing. A column added later would need its own ALTER, since CREATE
-- TABLE IF NOT EXISTS no-ops on an existing table and would report success while the new column
-- never appeared.
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
-- Named so a plan test can match it (spec 2.2), and ordered to serve the query the adapter
-- ACTUALLY issues: `WHERE investor_id=%s ORDER BY seq`. An (investor_id, occurred_at) index
-- serves the equality and then leaves a Sort, so the second column would buy that path nothing.
DROP INDEX IF EXISTS idx_touchpoints_investor_ts;
CREATE INDEX IF NOT EXISTS idx_touchpoints_investor_seq
    ON touchpoints (investor_id, seq);
-- Append-only: no UPDATE, no DELETE, enforced in the database not in prose.
CREATE OR REPLACE FUNCTION touchpoints_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'touchpoints is append-only'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touchpoints_append_only ON touchpoints;
CREATE TRIGGER trg_touchpoints_append_only
    BEFORE UPDATE OR DELETE ON touchpoints
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
-- A row-level trigger CANNOT fire on TRUNCATE, so without this one `TRUNCATE touchpoints`
-- quietly empties an append-only ledger. Statement-level, because TRUNCATE has no rows.
DROP TRIGGER IF EXISTS trg_touchpoints_no_truncate ON touchpoints;
CREATE TRIGGER trg_touchpoints_no_truncate
    BEFORE TRUNCATE ON touchpoints
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
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
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped. Run `docker compose up -d --wait` "
                    "(--wait consumes the healthcheck) and export the DSN in docker-compose.yml's "
                    "trailing comment, or point at any Postgres 16.")
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

def test_update_delete_and_truncate_are_refused_by_trigger():
    with _conn() as c:
        c.execute("INSERT INTO touchpoints (idempotency_key, investor_id, kind, payload, occurred_at, recorded_at)"
                  " VALUES ('t-ap1','inv-1','contact','{}', now(), now()) ON CONFLICT DO NOTHING")
        c.commit()   # the UPDATE's raise rolls back; an uncommitted INSERT would vanish with it
                     # and the DELETE below would fire its trigger on zero rows
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("UPDATE touchpoints SET kind='sent' WHERE idempotency_key='t-ap1'")
        c.rollback()
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("DELETE FROM touchpoints WHERE idempotency_key='t-ap1'")
        c.rollback()
        # The third arm is the one a row-level trigger cannot cover: TRUNCATE has no rows.
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("TRUNCATE touchpoints")
        c.rollback()

def test_projection_query_uses_the_named_index_not_a_seq_scan():
    with _conn() as c:
        # Sized so the planner would actually choose the index: ten rows seq-scan regardless.
        c.execute("""INSERT INTO touchpoints (idempotency_key, investor_id, kind, payload, occurred_at, recorded_at)
                     SELECT 'seed-'||g, 'inv-'||(g % 200), 'contact', '{}', now() - (g||' hours')::interval, now()
                     FROM generate_series(1, 5000) g ON CONFLICT DO NOTHING""")
        c.commit()
        c.execute("ANALYZE touchpoints")
        # EXPLAINs the adapter's OWN query text, imported rather than retyped: a gate that
        # explains a query nobody issues measures a hypothetical read path, and the production
        # query could regress to a Seq Scan with the gate still green.
        from retinue.ledger.postgres import SELECT_FOR_INVESTOR
        cur = c.execute("EXPLAIN (FORMAT TEXT) " + SELECT_FOR_INVESTOR, ("inv-7",))
        plan = "\n".join(r[0] for r in cur.fetchall())   # psycopg3: rows come off the CURSOR
        assert "idx_touchpoints_investor_seq" in plan, f"planner chose a different path:\n{plan}"
        assert "Seq Scan" not in plan, f"seq scan accepted would make this gate vacuous:\n{plan}"
        # The ordering is WHY the index is (investor_id, seq): a Bitmap Index Scan would use the
        # index and still Sort afterwards, passing both asserts above while delivering none of
        # the reason for the change. This pins the property, not just the index's name.
        assert "Sort" not in plan, f"index used but the ordering is not free:\n{plan}"

def test_concurrent_append_same_key_exactly_one_wins():
    _conn().close()          # same guard as its siblings: an explanatory failure, never an
                             # opaque AttributeError when the required lane has no DSN
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    import uuid
    from retinue.ledger.models import Touchpoint
    from retinue.ledger.postgres import PostgresStore, bootstrap
    bootstrap(DSN)
    store = PostgresStore(DSN)
    tp = Touchpoint(idempotency_key="conc-" + uuid.uuid4().hex[:12], investor_id="inv-conc",
                    mandate_id=None, kind="contact", payload={},
                    occurred_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
                    recorded_at=datetime(2030, 1, 2, tzinfo=timezone.utc))
    with ThreadPoolExecutor(2) as ex:
        results = sorted(ex.map(lambda _: store.append(tp), range(2)))
    assert results == [False, True]       # exactly one writer wins; the DATABASE enforces it
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

def test_idempotency_keys_are_globally_unique_not_per_investor(store, ns):
    # The schema makes idempotency_key the PRIMARY KEY: one namespace for every investor.
    # Pinned so an adapter with a per-investor unique index cannot pass this suite.
    first = tp(ns, "shared")
    second = Touchpoint(**{**first.model_dump(), "investor_id": f"other-{ns}"})
    assert store.append(first) is True
    assert store.append(second) is False
    assert store.touchpoints_for(f"other-{ns}") == ()

def test_the_store_snapshots_payloads_at_append_and_at_read(store, ns):
    # Postgres serialises payload into JSONB at write and rebuilds objects per read; the
    # in-memory reference must snapshot at both barriers, or the two adapters disagree about
    # whether a retained reference can rewrite an already-appended fact.
    t = tp(ns, "snap", usd="250000")
    store.append(t)
    t.payload["usd"] = "1"                                        # caller mutates its own object
    inv = f"inv-{ns}"
    assert store.touchpoints_for(inv)[0].payload["usd"] == "250000"
    store.touchpoints_for(inv)[0].payload["usd"] = "9"            # reader mutates what it got
    assert store.touchpoints_for(inv)[0].payload["usd"] == "250000"
```

(The last two carry forward from Task 1's fix round: this rewrite REPLACES the file, so
dropping them here would silently delete two constraint tests. The Postgres adapter satisfies
both inherently - `PRIMARY KEY` is one namespace, and a JSONB round-trip returns a fresh dict.)

- [ ] **Step 5: Run both lanes** - default: 7 contract tests green on memory + postgres skipped;
  with a DSN (docker-compose or local): everything green. Inertness (DSN lane): drop the trigger in a
  scratch database (`DROP TRIGGER trg_touchpoints_append_only ON touchpoints`) - the enforcement
  test goes RED; re-bootstrap, green. Then commit:

```bash
git add schema.sql src/retinue/ledger/postgres.py tests/ledger
git commit -m "feat: postgres adapter, append-only trigger, named-index plan test, and the required-lane negative control (inertness: trigger dropped, shown red)"
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

def test_a_fabricated_id_that_extends_a_real_one_does_not_resolve():
    # Bare containment matched "doc-12" against "doc-1", so an invented document validated and
    # the escalation this contract exists to force never fired. This is the boundary's whole job.
    assert resolve_source("doc-12 (filing, p.4)", DOCS) is None
    assert resolve_source("doc-1000", DOCS) is None

def test_resolution_is_deterministic_and_prefers_the_id_actually_cited():
    # frozenset order is hash-seed dependent, so a resolver picking arbitrarily among matches
    # answers differently between runs. Earliest position wins: the id inside the qualifier is
    # not the one being cited.
    assert resolve_source("doc-1 and doc-2 agree", DOCS) == "doc-1"
    assert resolve_source("doc-1 (doc-2, p.4)", DOCS) == "doc-1"

def test_undated_claim_cannot_be_constructed():
    with pytest.raises(Exception):
        Claim(claim="x", evidence="y", source="doc-1", confidence=0.5)   # no source_date

def test_missing_source_is_never_retryable_and_names_the_claim():
    bad = ResearchBrief(claims=(claim(source="doc-9"),))
    with pytest.raises(MissingSource) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is False
    assert e.value.claim == "fund writes early checks"   # the test's name promises this

def test_malformed_citation_is_retryable_and_carries_the_prior_value():
    bad = ResearchBrief(claims=(claim(source=""),))
    with pytest.raises(MalformedCitation) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is True and e.value.prior == ""

def test_ambiguity_is_flagged_never_guessed():
    c = claim(needs_identifier=True, candidates=("Fund A", "Fund A II"))
    assert c.candidates == ("Fund A", "Fund A II")

def test_prompt_names_every_convention_the_contract_enforces():
    # The prompt and the validator are a coupled pair, and this is the half a test can hold:
    # every convention the contract enforces must be NAMED in the prompt, so a rewrite that
    # drops one reddens. It cannot pin the prose's meaning - a prompt rewritten to say the
    # opposite would still pass - which is why the pairing is stated at both definition sites.
    for convention in ("document id",        # resolve_source
                       "source_date",        # mandatory; NOT the bare word "date", which the
                                             # word "candidates" supplies for free - that arm
                                             # could not redden and so enforced nothing
                       "quantity_key",       # the grouping key that lets a conflict be held
                       "needs_identifier"):  # ambiguity flagged, never guessed
        assert convention in RESEARCH_PROMPT, f"prompt never names {convention}"
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
"""The research specialist's contract. The prompt and validate_brief are a COUPLED PAIR, and
the prompt must name four conventions: the document-id citation, source_date, quantity_key
grouping, and needs_identifier ambiguity. Only document-id resolution is machine-checked, by
validate_brief; source_date is enforced at Claim construction, and quantity_key and
needs_identifier are contract shape. Edit the prompt and this module together."""
from __future__ import annotations
import re
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
    r"""Bounded containment, not equality and not bare containment.

    The r prefix is load-bearing: this docstring names the \b escape, and in a non-raw string
    Python stores an actual backspace character instead of the two characters described.

    Equality is wrong because live models emit qualified citations ('doc-3 (filing, p.4)'), and
    it would reject every claim from a capture run that cannot cheaply be re-taken.

    BARE containment is worse than equality: with no boundary, an invented 'doc-12' matches the
    real 'doc-1', so a fabricated citation validates and the escalation this contract exists to
    force never fires. The lookarounds are what keep containment from resolving a document that
    does not exist. They are used rather than \b so an id ending in punctuation still bounds.

    Ties break on position, then length, then name - deterministically. Position first because
    the id appearing earliest is the one being cited, not one that happens to appear inside the
    qualifier; length and name after because frozenset iteration order is hash-seed dependent
    and a resolver that answers differently between runs cannot be reasoned about.
    """
    hits = [(m.start(), -len(d), d) for d in doc_ids
            if (m := re.search(rf"(?<!\w){re.escape(d)}(?!\w)", source))]
    return min(hits)[2] if hits else None

def validate_brief(brief: ResearchBrief, doc_ids: frozenset[str]) -> None:
    for c in brief.claims:
        if not c.source.strip():
            raise MalformedCitation(c.claim, c.source)
        if resolve_source(c.source, doc_ids) is None:
            raise MissingSource(c.claim, c.source)

RESEARCH_PROMPT = (
    "You research investors from the provided fixture documents only.\n"
    "Every claim MUST cite its source containing the exact document id (e.g. 'doc-3 (filing, p.4)')\n"
    "and carry the document's date in source_date. If no document supports a fact, refuse that\n"
    "claim entirely -\n"
    "never guess, never write a claim without a resolvable document id. If an entity is ambiguous,\n"
    "set needs_identifier and list the candidates instead of choosing. When two documents report\n"
    "different values for the same quantity, give both claims the same quantity_key and keep\n"
    "both: annotate the conflict, never average it away and never pick a winner."
)
```

- [ ] **Step 4: Run to verify pass** - Expected: 8 passed.
- [ ] **Step 5: Inertness proofs, then commit** - one constraint removed at a time, the named
  test red, everything else green, restored between:
  1. Revert to bare containment (`d in source`, `max(hits, key=len)`) - the fabricated-id test
     reddens. Note that the determinism test reddens only under SOME hash seeds: a single run
     cannot reliably catch a seed-dependent resolver, which is the argument for removing the
     non-determinism rather than testing around it.
  2. Drop only the `(?!\w)` lookahead - the fabricated-id test reddens while the
     qualified-citation test stays green, showing the boundary and not the rewrite is what
     refuses fabrication.
  3. Delete the prompt's `source_date` instruction - the convention loop reddens on that arm.
     This is the proof a bare `"date"` arm could not give, since the word `candidates` supplies
     that substring for free.

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
- [ ] **Step 5: Inertness proof, then commit** - convert the validator's `MissingSource` branch
  into a `ModelRetry`: the zero-retry escalation test goes RED (two calls where one is allowed);
  restore.

```bash
git add src/retinue/specialists/research.py tests/specialists/test_research_agent.py
git commit -m "feat: the research agent under FunctionModel (inertness: escalation-as-retry shown red)"
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
from retinue.orchestration.topology import (AGENTS, SESSION_TOOLS, SPAWN_TOOLS, TIERS,
                                            build_options)

async def _noop_hook(input_data, tool_use_id, context):
    return {}

def test_every_agent_is_foreground():
    for name, d in AGENTS.items():
        assert getattr(d, "background", None) is False, f"{name} must set background=False"

def test_research_has_no_outbound_tool_at_all():
    # `is not None` first: `tools=None` makes the roster check below vacuous AND is the
    # dangerous value, since the SDK drops None fields and the subagent then inherits the
    # CLI default roster rather than an empty one.
    assert AGENTS["research"].tools is not None
    tools = AGENTS["research"].tools or []
    assert all("send" not in t.lower() for t in tools)
    assert "WebFetch" not in tools and "WebSearch" not in tools

def test_orchestrator_is_pre_approved_for_the_spawn_tool_only():
    opts = build_options(_noop_hook)
    assert set(opts.allowed_tools) == set(SPAWN_TOOLS)   # both names as data; runtime binds one

def test_the_session_roster_drops_every_write_and_outbound_capability():
    # A real narrowing, and the reason research cannot reach an outbound surface even by
    # inheritance. Not None: an omitted roster inherits all tools from the parent.
    opts = build_options(_noop_hook)
    assert opts.tools is not None
    assert not ({"Bash", "Write", "Edit", "WebFetch", "WebSearch"} & set(opts.tools))

def test_the_session_roster_covers_every_declared_agent_roster():
    # The CLI intersects each subagent's declared tools with the session roster, so a name in
    # an AgentDefinition that is missing here resolves to nothing - silently, with every other
    # test in this file still green. This is the assertion that makes that coupling visible.
    opts = build_options(_noop_hook)
    for name, definition in AGENTS.items():
        missing = set(definition.tools or ()) - set(opts.tools)
        assert not missing, f"{name} declares {sorted(missing)}, absent from the session roster"


def test_tiers_use_the_imported_vocabulary_exactly():
    from chaperone.gates.checker import MODEL_STRENGTH
    assert set(TIERS.values()) <= set(MODEL_STRENGTH)   # single-sourced; topology itself never imports gates

def test_research_parity_prompt_is_the_same_object():
    from retinue.specialists.research import RESEARCH_PROMPT
    assert AGENTS["research"].prompt is RESEARCH_PROMPT   # the spec's parity rule: same object, not equal strings

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
from retinue.specialists.research import RESEARCH_PROMPT

SPAWN_TOOLS = ("Agent", "Task")   # renamed at CLI 2.1.63; both listed, runtime binds one

TIERS = {"orchestrator": "sonnet-tier", "research": "haiku-tier",
         "drafting": "haiku-tier", "conversation": "sonnet-tier"}

AGENTS: dict[str, AgentDefinition] = {
    "research": AgentDefinition(
        description="Researches investors from fixture documents; cites or refuses.",
        prompt=RESEARCH_PROMPT,     # parity: the SAME constant object the pydantic-ai agent uses
        tools=["Read", "Grep", "Glob"], background=False),
    # drafting/conversation prompts are PROVISIONAL inline strings until their modules land
    # (Tasks 17 and 22 move them into shared constants and add their parity tests).
    "drafting": AgentDefinition(
        description="Drafts outreach from the relationship record. Output goes to review.",
        prompt="Draft from the record only.", tools=["Read"], background=False),
    "conversation": AgentDefinition(
        description="Carries investor conversation; sends are gated.",
        prompt="Converse; sending is gated.", tools=["Read"], background=False),
}

#: The SESSION roster. The CLI resolves each subagent's declared tools by INTERSECTING them
#: with this list, so it is a shared ceiling and not a per-agent bound: narrowing it to the
#: spawn tool alone resolves every specialist to zero tools, silently, with the options-shape
#: tests still green. Its real job is to drop what NO agent needs - Bash, Write, Edit, WebFetch
#: and WebSearch are absent, so the research specialist cannot reach an outbound surface even
#: by inheritance. Per-agent bounds live in each AgentDefinition; the orchestrator's own bound
#: is `allowed_tools` plus the hook. `SESSION_TOOLS_COVER_EVERY_AGENT` pins the intersection.
SESSION_TOOLS = ("Agent", "Task", "Read", "Grep", "Glob")

def build_options(hook) -> ClaudeAgentOptions:
    # `tools` is the session roster; `allowed_tools` is the auto-approve list. Both are set:
    # omitting `tools` inherits the CLI default (the agent-definition schema says an omitted
    # roster "inherits all tools from parent"), and omitting `allowed_tools` would leave the
    # orchestrator's spawn-only bound unstated.
    return ClaudeAgentOptions(
        agents=AGENTS,
        tools=list(SESSION_TOOLS),
        allowed_tools=list(SPAWN_TOOLS),
        permission_mode="default",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook])]},
    )
```

(Exact `AgentDefinition`/`HookMatcher` kwargs are camelCase in places; the RED run against the
installed 0.2.130 names any mismatch - fix the call, never the table's content.)

- [ ] **Step 4: Run to verify pass** - Expected: 6 passed.
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
- Produces: `SEND_TOOL = "send_message"` (the ONE definition of the name; every later module
  imports it - the audit's `send_tool_single_home` rule holds them to it); `SEND_TOOLS =
  frozenset((SEND_TOOL, "mcp__retinue__" + SEND_TOOL))` (the in-process-server name listed as
  data, like the spawn tool's two names; which binds live is witnessed by the P4 demo capture);
  `decide(agent_type: str | None,
  tool_name: str) -> Literal["allow", "ask"]`; `async pre_tool_use(input_data, tool_use_id,
  context) -> dict` - the ONE parent-registered hook: routing first, then chaperone's
  deterministic lane for send payloads.

- [ ] **Step 1: Write the provisional payload fixtures** (marked; the research payload is
  replaced by the P1 smoke's capture, the send payload by the P4 demo's - the smoke session has
  no send tool by design). JSON permits no comments - the blocks below are the COMPLETE file
  contents.

File `fixtures/payloads/provisional_send.json`:

```json
{"meta": {"provisional": true, "note": "hand-authored; replaced by the P4 demo capture"},
 "payload": {"tool_name": "send_message", "agent_type": "conversation",
             "tool_input": {"body": "The round is $9M.", "record": {"round_size": "8000000"},
                            "cited_fields": ["round_size"], "approval_token": "tok-1",
                            "jurisdiction": "US"}}}
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
    assert spec.get("permissionDecision") == "deny"
    # figure-not-in-record IS the primary finding: the fixture supplies the approval token and a
    # consented jurisdiction precisely so the 9M-vs-8M mismatch is findings[0] - a token-less
    # fixture would deny on no_approval_token and this comment would be the masquerade 5.2 warns
    # about, documented into the showcase test.
    assert "figure_not_in_record" in spec.get("permissionDecisionReason", "")
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

SEND_TOOL = "send_message"   # the ONE definition; the audit holds every other module to importing it
SEND_TOOLS = frozenset((SEND_TOOL, "mcp__retinue__" + SEND_TOOL))   # live server name as data

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
- [ ] **Step 6: Inertness proof, then commit** - make `decide` return `"allow"` for an
  unrecognised `agent_type`: the table-totality test goes RED (unknown must fail toward the
  human); restore.

```bash
git add src/retinue/boundary fixtures/payloads tests/boundary
git commit -m "feat: the one hook - total decision table, ask on outward sends (inertness: unknown-agent allow shown red)"
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
  under `src/retinue/`). CLI: `python tools/fleet_audit.py` exits 1 on findings. Test imports resolve because the
  manifest sets `pythonpath = ["src", "."]` - the repo root entry exists for exactly this
  (`tools/` is a PEP 420 namespace package on 3.11).

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

def test_send_tool_literal_outside_boundary_is_caught(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "orchestration"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("TOOL = 'send_message'\n")      # single quotes: grep-proof, AST-caught
    findings = audit(tmp_path / "src" / "retinue")
    assert any("send_tool_single_home" in f for f in findings)

def test_a_send_tool_mention_in_a_docstring_is_not_a_definition(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "orchestration"; pkg.mkdir(parents=True)
    (pkg / "ok.py").write_text('"""The send_message tool is discussed here, not defined."""\n')
    assert audit(tmp_path / "src" / "retinue") == []              # equality, not substring

def test_cli_exit_codes():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "fleet_audit.py")], capture_output=True)
    assert r.returncode == 0
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError: tools.fleet_audit`.
- [ ] **Step 3: Implement**

```python
# tools/fleet_audit.py
"""Import discipline as AST rules - one named rule per check, each with a planted-violation test
proving it fires. Grep is defeated by quoting style, f-strings, docstrings and comments, and
cannot tell an import from a mention; walking Import/ImportFrom and Constant nodes can."""
from __future__ import annotations
import ast, sys
from pathlib import Path

GATE_MODULES = ("chaperone.gates", "chaperone.audit")   # prefixes: EVERY gates/audit submodule counts
SEND_TOOL_LITERAL = "send" + "_message"                 # constructed: this file lives outside boundary/

def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out

def _names_send_tool(tree: ast.AST) -> bool:
    """String CONSTANTS equal to the send-tool name - equality, not substring, so a docstring
    discussing the tool is not a hit while a single-quoted or f-string definition is."""
    return any(isinstance(n, ast.Constant) and n.value == SEND_TOOL_LITERAL
               for n in ast.walk(tree))

def audit(root: Path) -> list[str]:
    findings: list[str] = []
    send_homes: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        tree = ast.parse(py.read_text(encoding="utf-8"))
        gate_hits = [m for m in _imports(tree) if any(m.startswith(g) for g in GATE_MODULES)]
        if gate_hits and rel.parts[0] != "boundary":
            rule = ("specialists_import_no_gates" if rel.parts[0] == "specialists"
                    else "only_boundary_imports_gates")
            findings.append(f"{rule}: {rel} imports {sorted(gate_hits)}")
        if _names_send_tool(tree) and rel.parts[0] != "boundary":
            send_homes.append(str(rel))
    if send_homes:
        findings.append(f"send_tool_single_home: send tool named outside boundary/: {send_homes}")
    return findings

if __name__ == "__main__":
    found = audit(Path(__file__).resolve().parents[1] / "src" / "retinue")
    for f in found:
        print(f, file=sys.stderr)
    sys.exit(1 if found else 0)
```

- [ ] **Step 4: Run to verify pass** - Expected: 6 passed (the planted violations ARE the
  negative controls - every rule, the send-tool rule included, demonstrated firing).
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
        assert (meta.get("provisional") or meta.get("captured")
                or meta.get("hand_authored")), f"{p}: no provenance (provisional/captured/hand_authored)"
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
         "stage": rng.choice(("pre-seed", "seed", "series-a")),
         "geography": rng.choice(("us-east", "eu-west", "mena")),
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
- [ ] **Step 3b: Fingerprint pass** - hand-diff every invented figure in `fixtures/` and the
  generator against the published check-size ranges of the firms on the untracked token list; a
  range collision is invisible to every automated gate here.
- [ ] **Step 4: Commit**

```bash
git add fixtures src/retinue/synth scripts tests/synth tests/test_fixture_meta.py
git commit -m "feat: synthetic fixtures, seeded roster generator, and the RETINUE_LIVE-gated capture smoke"
```

---

### Task 11: README seed and the battery

**Files:**
- Create: `README.md`, `tools/battery.sh`, `.github/workflows/ci.yml`
- Test: (the battery and the CI negative control are the test; run the battery)

- [ ] **Step 1: Write `tools/battery.sh`**

```bash
#!/usr/bin/env bash
# The repo battery (spec section 11). Zero hits expected on every grep.
# Patterns are CONSTRUCTED, never spelled: every tracked file, this script and the plan that
# embeds it included, must pass the battery it defines.
set -u
fail=0
say() { printf "%-40s %s\n" "$1" "$2"; }
docs=$(git ls-files '*.md')
all=$(git ls-files ':!*.whl')
EMD=$(printf '\342\200\224')      # octal, so the byte sequence appears in no tracked file
n=$(grep -c "$EMD" /dev/null $docs 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
[ "$n" -eq 0 ] && say "em dashes" "ok" || { say "em dashes" "$n FAIL"; fail=1; }
for t in prov{able,en}; do
  n=$(grep -cIwi "$t" /dev/null $all 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
  [ "$n" -eq 0 ] && say "adjective $t" "ok" || { say "adjective $t" "$n FAIL"; fail=1; }
done
KW="result""_type="
n=$(grep -cI "$KW" /dev/null $all 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
[ "$n" -eq 0 ] && say "removed 2.x result kwarg" "ok" || { say "removed 2.x result kwarg" "$n FAIL"; fail=1; }
STALE="claude-[23]|gpt-""4"
n=$(grep -cIE "$STALE" /dev/null $all 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
[ "$n" -eq 0 ] && say "stale model ids" "ok" || { say "stale model ids" "$n FAIL"; fail=1; }
# Client/organisation tokens: the list lives OUTSIDE the repo (untracked; see .gitignore) - a
# tracked list would ship the very tokens it bans. Optional on a fresh clone by design.
if [ -f tools/banned_tokens.txt ]; then
  while read -r tok; do
    case "$tok" in ''|'#'*) continue;; esac
    n=$(grep -cIi "$tok" /dev/null $all 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
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

- [ ] **Step 2b: Write `.github/workflows/ci.yml`** - the spec's 2.2 negative control lives in
  CI or it does not exist ("a lane that can silently skip forever is a vacuous gate"):

```yaml
name: ci
on: [push]
jobs:
  default-lane:
    runs-on: ubuntu-latest
    strategy:
      # Both ends of the range the manifest claims (requires-python >=3.11). Testing only the
      # floor while developers run the ceiling lets a version-specific failure ship unseen:
      # pydantic-graph emits a no-current-event-loop DeprecationWarning under run_sync on 3.13
      # that 3.11 never shows, so "output pristine" means different things on each.
      matrix:
        python-version: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt
      - run: python -m pytest -q            # no daemon, no network, no key
  postgres-lane:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16.4                # pinned exactly; matches the managed target's major
        env:
          POSTGRES_PASSWORD: retinue
          POSTGRES_DB: retinue
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      RETINUE_PG_DSN: postgresql://postgres:retinue@localhost:5432/retinue
      RETINUE_PG_REQUIRED: "1"              # the negative control: a silent skip is a red build
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
      - run: bash tools/battery.sh
```

- [ ] **Step 3: Run the battery** - Expected: exit 0, every line ok.
- [ ] **Step 4: Commit**

```bash
git add README.md tools/battery.sh .gitignore .github/workflows/ci.yml
git commit -m "docs: README seed, the battery with an untracked local token list, and CI with the Postgres negative control"
```

---

## Phase 2 - matching (Tasks 12-16)

Spec section 9: "Matching integration, OutcomeRecord, ranking evaluators, the judge capture plus
frozen-verdict replay (calibration and discrimination), and the block-stripped control."

---

### Task 12: OutcomeRecord and the parameterized signal

**Files:**
- Create: `src/retinue/ledger/outcomes.py`
- Modify: `schema.sql` (append the `outcomes` table)
- Test: `tests/ledger/test_outcomes.py`

**Interfaces:**
- Consumes: Task 1's `TouchpointStore` (for attribution).
- Produces: `OUTCOME_SIGNALS = ("replied", "meeting_booked", "check_written")`;
  `OutcomeRecord(outcome_key: str, investor_id: str, mandate_id: str, signal: str,
  occurred_at: datetime, observed_at: datetime)` (frozen; unknown signal raises);
  `OutcomeConfig(active_signal: str = "replied", attribution: str = "last_touch")` (validated);
  `resolved_for(config, outcomes) -> tuple[OutcomeRecord, ...]` (only the active signal counts);
  `last_touch_attribution(store, outcome) -> Touchpoint | None` (latest contact/sent touchpoint
  with `occurred_at <=` the outcome's).

- [ ] **Step 1: Append to `schema.sql`** (idempotent, like everything in it):

```sql
-- Outcomes resolve over weeks: occurred_at and observed_at diverge structurally, and a
-- later-resolving outcome UPDATES this row - never the touchpoint (spec 5.1).
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_key TEXT PRIMARY KEY,
    investor_id TEXT NOT NULL,
    mandate_id  TEXT NOT NULL,
    signal      TEXT NOT NULL CHECK (signal IN ('replied','meeting_booked','check_written')),
    occurred_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL
);
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/ledger/test_outcomes.py
from datetime import datetime, timezone
import pytest
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import InMemoryStore
from retinue.ledger.outcomes import (OUTCOME_SIGNALS, OutcomeConfig, OutcomeRecord,
                                     last_touch_attribution, resolved_for)

T = [datetime(2030, 2, d, tzinfo=timezone.utc) for d in (1, 5, 9, 20)]

def outcome(signal="replied", occurred=T[2], observed=T[3], key="o1"):
    return OutcomeRecord(outcome_key=key, investor_id="inv-1", mandate_id="m-1",
                         signal=signal, occurred_at=occurred, observed_at=observed)

def test_unknown_signal_raises():
    with pytest.raises(Exception):
        outcome(signal="ghosted")

def test_occurred_and_observed_are_both_required_and_distinct():
    o = outcome()
    assert o.occurred_at != o.observed_at        # weeks apart in the world; both carried

def test_active_signal_is_configuration_not_code():
    rows = (outcome("replied", key="o1"), outcome("meeting_booked", key="o2"))
    assert [o.outcome_key for o in resolved_for(OutcomeConfig(), rows)] == ["o1"]
    toggled = OutcomeConfig(active_signal="meeting_booked")
    assert [o.outcome_key for o in resolved_for(toggled, rows)] == ["o2"]

def test_config_rejects_a_signal_outside_the_enum():
    with pytest.raises(Exception):
        OutcomeConfig(active_signal="vibes")

def test_last_touch_attribution_picks_latest_at_or_before_occurred():
    s = InMemoryStore()
    for key, occ in (("c1", T[0]), ("c2", T[1]), ("late", T[3])):
        s.append(Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                            kind="contact", payload={}, occurred_at=occ, recorded_at=T[3]))
    hit = last_touch_attribution(s, outcome(occurred=T[2]))
    assert hit.idempotency_key == "c2"           # latest <= occurred; never the later one

def test_attribution_on_a_new_investor_is_none_not_invented():
    assert last_touch_attribution(InMemoryStore(), outcome()) is None
```

- [ ] **Step 3: Run to verify failure** - Expected: `ImportError` on `outcomes`.
- [ ] **Step 4: Implement**

```python
# src/retinue/ledger/outcomes.py
"""Outcomes. The signal that counts is a CONFIG PARAMETER, not a code path: which outcome the
product optimises for is a genuinely open question, and this shape keeps it a toggle (spec 5.1).
The weights-update sketch that reads it stays Designed. Attribution: last-touch, parameterized."""
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
```

- [ ] **Step 5: Run to verify pass** - Expected: 6 passed. Then run the Postgres lane once with a
  DSN if available: `bootstrap` applies the appended table idempotently (re-run is a no-op).
- [ ] **Step 6: Inertness proof, then commit** - stub the signal validator to `return v`: the
  unknown-signal test goes RED; restore.

```bash
git add src/retinue/ledger/outcomes.py schema.sql tests/ledger/test_outcomes.py
git commit -m "feat: OutcomeRecord with the parameterized signal toggle and last-touch attribution (inertness: validator stubbed, shown red)"
```

---

### Task 13: Matching integration

**Files:**
- Create: `src/retinue/matching/__init__.py` (empty), `src/retinue/matching/integrate.py`
- Test: `tests/matching/test_integrate.py`

**Interfaces:**
- Consumes: chaperone's `Mandate(check_size_min, stage, sector, geography,
  consented_jurisdictions)`, `Candidate(id, check_size_max, stage, sector, geography,
  jurisdiction, days_since_touch, prior_passes)`, `classify`, `rank(candidates, mandate,
  embed_score) -> (ranked, needs_verification)` - all imported unchanged; Task 2's
  `project_record`; Task 10's roster rows.
- Produces: `candidate_for(row: dict, store, *, now: datetime) -> Candidate`;
  `shortlist(rows, mandate, *, embed_score, store, now) -> tuple[list[Candidate], list[Candidate]]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/matching/test_integrate.py
from datetime import datetime, timedelta, timezone
import pytest
from chaperone.matching.filters import Mandate
from retinue.ledger.models import StoreUnavailable, Touchpoint
from retinue.ledger.store import InMemoryStore
from retinue.matching.integrate import candidate_for, shortlist

NOW = datetime(2030, 3, 1, tzinfo=timezone.utc)
MANDATE = Mandate(check_size_min="300000", stage="seed", sector="devtools",
                  geography="eu-west", consented_jurisdictions=frozenset({"US", "DE"}))

def row(inv="inv-1", juris="US", ceiling="4000000", stage="seed", sector="devtools", geo="eu-west"):
    return {"investor_id": inv, "jurisdiction": juris, "check_ceiling": ceiling,
            "stage": stage, "sector": sector, "geography": geo}

def seeded(inv="inv-1", days_ago=30, passes=1):
    s = InMemoryStore()
    s.append(Touchpoint(idempotency_key=f"{inv}-c", investor_id=inv, mandate_id="m-1",
                        kind="contact", payload={},
                        occurred_at=NOW - timedelta(days=days_ago), recorded_at=NOW))
    for i in range(passes):
        s.append(Touchpoint(idempotency_key=f"{inv}-p{i}", investor_id=inv, mandate_id="m-1",
                            kind="pass_reason", payload={"reason": "too early"},
                            occurred_at=datetime(2030, 1, 15, tzinfo=timezone.utc), recorded_at=NOW))
    return s

def test_candidate_carries_ledger_relationship_state():
    c = candidate_for(row(), seeded(), now=NOW)
    assert c.days_since_touch == 30 and c.prior_passes == 1

def test_violation_costs_membership_not_score():
    rows = [row("inv-ok"), row("inv-bad", juris="RU")]         # jurisdiction not consented
    ranked, needs = shortlist(rows, MANDATE, embed_score=lambda c: 1.0,
                              store=InMemoryStore(), now=NOW)
    ids = [c.id for c in ranked] + [c.id for c in needs]
    assert "inv-bad" not in ids       # a perfect similarity score buys nothing: membership, not score

def test_missing_field_routes_to_needs_verification_not_dropped():
    rows = [row("inv-hole", stage=None)]
    ranked, needs = shortlist(rows, MANDATE, embed_score=lambda c: 0.5,
                              store=InMemoryStore(), now=NOW)
    assert [c.id for c in needs] == ["inv-hole"] and ranked == []

def test_similarity_runs_only_inside_the_filtered_set():
    seen = []
    def spy(candidate):
        seen.append(candidate.id)
        return 0.5
    shortlist([row("inv-ok"), row("inv-bad", juris="RU")], MANDATE,
              embed_score=spy, store=InMemoryStore(), now=NOW)
    assert "inv-bad" not in seen      # never retrieval: the excluded are never even scored

def test_cold_start_is_carried_by_similarity():
    rows = [row("inv-new"), row("inv-known")]
    # The imported weights are 0.6 relationship / 0.4 embedding, so the rival must be STALE:
    # at 300 days, 0.6*(1-300/365) + 0.4*0.1 = 0.147 < inv-new's 0.4*0.99 = 0.396. A 30-day-old
    # contact would win at 0.591 and the test would be red against the real ranker.
    store = seeded("inv-known", days_ago=300, passes=0)
    ranked, _ = shortlist(rows, MANDATE,
                          embed_score=lambda c: 0.99 if c.id == "inv-new" else 0.1,
                          store=store, now=NOW)
    assert ranked[0].id == "inv-new"  # no relationship state, so similarity must carry them

def test_projection_unavailable_raises_never_invents_a_candidate():
    class Broken:
        def touchpoints_for(self, i): raise StoreUnavailable("down")
        def append(self, t): raise AssertionError
    with pytest.raises(StoreUnavailable):
        candidate_for(row(), Broken(), now=NOW)
```

- [ ] **Step 2: Run to verify failure** - Expected: `ImportError`.
- [ ] **Step 3: Implement**

```python
# src/retinue/matching/integrate.py
"""Roster + ledger -> the imported matching staging, unchanged: hard filters, then relationship,
then similarity INSIDE the filtered set. The similarity score stays an injected callable - a scope
commitment (spec 5.4). Matching never invents: an unreadable projection raises."""
from __future__ import annotations
from datetime import datetime
from typing import Callable, Sequence
from chaperone.matching.filters import Candidate, Mandate
from chaperone.matching.rank import rank
from retinue.ledger.models import StoreUnavailable
from retinue.ledger.projection import project_record
from retinue.ledger.store import TouchpointStore

def candidate_for(row: dict, store: TouchpointStore, *, now: datetime) -> Candidate:
    rec = project_record(store, row["investor_id"])
    if rec is None:
        raise StoreUnavailable(f"projection unavailable for {row['investor_id']}; matching never invents")
    passes = sum(1 for t in store.touchpoints_for(row["investor_id"]) if t.kind == "pass_reason")
    return Candidate(
        id=row["investor_id"],
        check_size_max=str(row["check_ceiling"]) if row.get("check_ceiling") is not None else None,
        stage=row.get("stage"), sector=row.get("sector"), geography=row.get("geography"),
        jurisdiction=rec.jurisdiction or row.get("jurisdiction"),
        days_since_touch=(now - rec.last_contact).days if rec.last_contact else None,
        prior_passes=passes,
    )

def shortlist(rows: Sequence[dict], mandate: Mandate, *,
              embed_score: Callable[[Candidate], float],
              store: TouchpointStore, now: datetime):
    candidates = [candidate_for(r, store, now=now) for r in rows]
    return rank(candidates, mandate, embed_score)
```

- [ ] **Step 4: Run to verify pass** - Expected: 6 passed.
- [ ] **Step 5: Inertness proof, then commit** - route `INELIGIBLE` into the ranked bucket by
  monkeypatching in a scratch run? No - simpler and honest: pass `embed_score=lambda c: 1.0` with
  the ineligible row and confirm the membership test is the one that catches it (it already ran
  RED before Step 3). Commit:

```bash
git add src/retinue/matching tests/matching
git commit -m "feat: matching integration - ledger-fed candidates through the imported staging (membership test red before implementation)"
```

---

### Task 14: Ranking evaluators and the gold fixtures

**Files:**
- Create: `src/retinue/evals/__init__.py` (empty), `src/retinue/evals/ranking.py`,
  `fixtures/gold_rankings.json`
- Test: `tests/evals/test_ranking.py`

**Interfaces:**
- Consumes: Task 13's `shortlist`; pydantic-evals `Evaluator`, `EvaluatorContext`.
- Produces: `HitAtN(n: int)` and `MRR()` evaluators whose `evaluate` returns a mapping with the
  metric name explicit (`{"hit_at_3": 1.0}`, `{"mrr": 0.5}`) - floats always; helper
  `ranked_ids(rows, mandate, embed_score, store, now) -> list[str]`.

- [ ] **Step 1: Write `fixtures/gold_rankings.json`** (hand-authored, judged, frozen; figures
  invented):

```json
{"meta": {"hand_authored": true,
          "note": "gold shortlists over the seed-7 synthetic roster; judged by hand, frozen"},
 "cases": [
  {"name": "warm-relationship-wins", "seed": 7, "n": 8, "expected_top": "synth-003"},
  {"name": "cold-start-carried-by-similarity", "seed": 7, "n": 8, "expected_top": "synth-005"}
 ]}
```

(After Task 10's generator is extended, regenerate expectations by inspecting
`generate_rosters(7, 8)` once and choosing two defensible golds by hand - the point is a frozen
judged fixture, and the judgment is the author's, stated as such per spec 7.2. Choose golds
inside the mandate's eligibility cell; `seed` and `n` are fixture fields and may change during
regeneration too - only the metric definitions are immovable.)

- [ ] **Step 2: Write the failing tests**

```python
# tests/evals/test_ranking.py
from retinue.evals.ranking import MRR, HitAtN

class Ctx:
    """Duck-typed stand-in: the evaluators read exactly these two attributes."""
    def __init__(self, output, expected):
        self.output, self.expected_output = output, expected

def test_mrr_is_the_reciprocal_rank_never_a_binary():
    ranked = ["a", "b", "c", "d"]
    assert MRR().evaluate(Ctx(ranked, "a")) == {"mrr": 1.0}
    assert MRR().evaluate(Ctx(ranked, "b")) == {"mrr": 0.5}     # the one-probe catch: 0.5, not 0 or 1
    assert MRR().evaluate(Ctx(ranked, "c")) == {"mrr": 1.0 / 3}
    assert MRR().evaluate(Ctx(ranked, "zz")) == {"mrr": 0.0}

def test_hit_at_n_is_a_float_with_an_explicit_name():
    out = HitAtN(3).evaluate(Ctx(["a", "b", "c", "d"], "c"))
    assert out == {"hit_at_3": 1.0} and isinstance(out["hit_at_3"], float)
    assert HitAtN(3).evaluate(Ctx(["a", "b", "c", "d"], "d")) == {"hit_at_3": 0.0}

def test_the_metric_notices_a_null_embedder_on_the_cold_start_case():
    # The cold-start gold expects similarity to carry a new investor; an embedder that returns
    # 0.0 for everyone must drop the metric. This is the "the metric must notice" clause as a test.
    from datetime import datetime, timezone
    from chaperone.matching.filters import Mandate
    from retinue.evals.ranking import ranked_ids
    from retinue.ledger.store import InMemoryStore
    from retinue.synth.rosters import generate_rosters
    import json, pathlib
    gold = json.loads((pathlib.Path(__file__).resolve().parents[2] / "fixtures"
                       / "gold_rankings.json").read_text(encoding="utf-8"))
    case = next(c for c in gold["cases"] if c["name"] == "cold-start-carried-by-similarity")
    rows = list(generate_rosters(case["seed"], case["n"]))
    top = next(r for r in rows if r["investor_id"] == case["expected_top"])
    mandate = Mandate(check_size_min="100000", stage=top["stage"], sector=top["sector"],
                      geography=top["geography"], consented_jurisdictions=frozenset({"US", "UK", "DE"}))
    now = datetime(2030, 3, 1, tzinfo=timezone.utc)
    favouring = ranked_ids(rows, mandate, lambda c: 0.99 if c.id == case["expected_top"] else 0.1,
                           InMemoryStore(), now)
    null = ranked_ids(rows, mandate, lambda c: 0.0, InMemoryStore(), now)
    good = MRR().evaluate(Ctx(favouring, case["expected_top"]))["mrr"]
    bad = MRR().evaluate(Ctx(null, case["expected_top"]))["mrr"]
    assert good > bad                 # the metric notices when similarity stops carrying them

def test_warm_relationship_wins_under_a_uniform_embedder():
    # The other gold case's consumer: with the embedder flat, relationship state must decide.
    from datetime import datetime, timedelta, timezone
    from chaperone.matching.filters import Mandate
    from retinue.evals.ranking import ranked_ids
    from retinue.ledger.models import Touchpoint
    from retinue.ledger.store import InMemoryStore
    from retinue.synth.rosters import generate_rosters
    import json, pathlib
    gold = json.loads((pathlib.Path(__file__).resolve().parents[2] / "fixtures"
                       / "gold_rankings.json").read_text(encoding="utf-8"))
    case = next(c for c in gold["cases"] if c["name"] == "warm-relationship-wins")
    rows = list(generate_rosters(case["seed"], case["n"]))
    top = next(r for r in rows if r["investor_id"] == case["expected_top"])
    mandate = Mandate(check_size_min="100000", stage=top["stage"], sector=top["sector"],
                      geography=top["geography"], consented_jurisdictions=frozenset({"US", "UK", "DE"}))
    now = datetime(2030, 3, 1, tzinfo=timezone.utc)
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="warm-c", investor_id=case["expected_top"],
                            mandate_id="m-1", kind="contact", payload={},
                            occurred_at=now - timedelta(days=20), recorded_at=now))
    ranked = ranked_ids(rows, mandate, lambda c: 0.5, store, now)
    assert MRR().evaluate(Ctx(ranked, case["expected_top"]))["mrr"] == 1.0
```

- [ ] **Step 3: Run to verify failure** - Expected: `ImportError`.
- [ ] **Step 4: Implement**

```python
# src/retinue/evals/ranking.py
"""Hand-rolled ranking evaluators: FLOATS with explicit names, never booleans. MRR is the
reciprocal rank (1, 1/2, 1/3, ...) - a binary MRR is the exact drift these tests pin against.
(Lineage per spec 5.4: from the project ledger's ranking analysis, not the course corpus.)"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from retinue.matching.integrate import shortlist

@dataclass
class HitAtN(Evaluator):
    n: int
    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        return {f"hit_at_{self.n}": 1.0 if ctx.expected_output in list(ctx.output)[: self.n] else 0.0}

@dataclass
class MRR(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        ranked = list(ctx.output)
        if ctx.expected_output not in ranked:
            return {"mrr": 0.0}
        return {"mrr": 1.0 / (ranked.index(ctx.expected_output) + 1)}

def ranked_ids(rows: Sequence[dict], mandate, embed_score: Callable, store, now: datetime) -> list[str]:
    ranked, _ = shortlist(rows, mandate, embed_score=embed_score, store=store, now=now)
    return [c.id for c in ranked]
```

(Adaptation point, named: pydantic-evals 2.23 accepts a mapping return from `evaluate` for
named results; if the installed surface differs, the RED run names it - keep the explicit-name
mapping, adjust only the base-class hook. If `Evaluator` is generic and complains about bare
subscription, subclass without generics - the duck-typed `Ctx` tests pin the math either way.)

- [ ] **Step 5: Run to verify pass** - Expected: 4 passed. If the cold-start gold id chosen in
  Step 1 turns out not to be constructible from the seed-7 roster (wrong sector/stage draw),
  regenerate the fixture per Step 1's procedure - change the FIXTURE, never the metric.
- [ ] **Step 6: Commit**

```bash
git add src/retinue/evals fixtures/gold_rankings.json tests/evals
git commit -m "feat: hand-rolled ranking evaluators - floats, explicit names, reciprocal-rank MRR (binary-MRR trap pinned red first)"
```

---

### Task 15: Judge capture and the frozen-verdict replay

**Files:**
- Create: `src/retinue/evals/frozen.py`, `fixtures/verdicts/judge_verdicts.json`,
  `fixtures/drafts/compliant_01.json`, `fixtures/drafts/violating_01.json`,
  `scripts/judge_capture.py`
- Test: `tests/evals/test_frozen_judge.py`

**Interfaces:**
- Produces: `FrozenVerdict(case: str, violates: bool, confidence: float, quality: float)`;
  `load_verdicts(path) -> dict[str, FrozenVerdict]`; `calibration_agreement(verdicts,
  ground_truth, *, floor: float = 0.7) -> float` (fraction of confident verdicts agreeing);
  `discrimination_gap(verdicts, ground_truth) -> float` (mean compliant quality minus mean
  violating quality). **Two functions, deliberately never one** (spec 7).

- [ ] **Step 1: Write the draft fixtures** (synthetic; bodies invented; the violating one trips a
  content class):

File `fixtures/drafts/compliant_01.json`:

```json
{"meta": {"hand_authored": true},
 "case": "compliant_01",
 "body": "Thanks for the conversation last week. Sharing the update you asked for.",
 "ground_truth_violates": false}
```

File `fixtures/drafts/violating_01.json`:

```json
{"meta": {"hand_authored": true},
 "case": "violating_01",
 "body": "Honestly, this company is a great investment and you should take the allocation.",
 "ground_truth_violates": true}
```

File `fixtures/verdicts/judge_verdicts.json` (provisional until the capture runs):

```json
{"meta": {"provisional": true, "note": "hand-authored; replaced by scripts/judge_capture.py"},
 "verdicts": [
  {"case": "compliant_01", "violates": false, "confidence": 0.9, "quality": 0.8},
  {"case": "violating_01", "violates": true, "confidence": 0.85, "quality": 0.2}
 ]}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/evals/test_frozen_judge.py
import json
from pathlib import Path
from retinue.evals.frozen import calibration_agreement, discrimination_gap, load_verdicts

FIX = Path(__file__).resolve().parents[2] / "fixtures"

def truth():
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in (FIX / "drafts").glob("*.json")]
    return {r["case"]: r["ground_truth_violates"] for r in rows}

def test_replay_needs_no_network():
    v = load_verdicts(FIX / "verdicts" / "judge_verdicts.json")
    assert set(v) == set(truth())            # every draft judged, nothing else

def test_calibration_is_agreement_of_confident_verdicts():
    v = load_verdicts(FIX / "verdicts" / "judge_verdicts.json")
    assert calibration_agreement(v, truth(), floor=0.7) == 1.0

def test_discrimination_gap_is_positive_on_the_frozen_set():
    v = load_verdicts(FIX / "verdicts" / "judge_verdicts.json")
    assert discrimination_gap(v, truth()) > 0.0   # violating drafts score BELOW compliant ones

def test_calibration_and_discrimination_never_share_a_result():
    # Two names, two numbers, two meanings: conflating them blurs the two-lane thesis inside
    # its own evidence (spec 7). This pins the API shape itself.
    from retinue.evals import frozen
    assert frozen.calibration_agreement is not frozen.discrimination_gap
```

- [ ] **Step 3: Run to verify failure**, then implement:

```python
# src/retinue/evals/frozen.py
"""Frozen-judge replay. Judged once live (scripts/judge_capture.py), frozen, replayed forever -
the LLM judge never runs in CI, on determinism grounds (spec 2.3). Calibration and discrimination
are SEPARATE checks with separate names and units; a shared number would conflate whether the
judge knows what it knows with whether the score ranks violations below compliance."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

class FrozenVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)
    case: str
    violates: bool
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)

def load_verdicts(path: Path) -> dict[str, FrozenVerdict]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["verdicts"]
    return {r["case"]: FrozenVerdict(**r) for r in rows}

def calibration_agreement(verdicts: dict[str, FrozenVerdict], ground_truth: dict[str, bool],
                          *, floor: float = 0.7) -> float:
    confident = [v for v in verdicts.values() if v.confidence >= floor]
    if not confident:
        return 0.0                      # no confident verdicts is a calibration FAILURE, not a pass
    agree = sum(1 for v in confident if v.violates == ground_truth[v.case])
    return agree / len(confident)

def discrimination_gap(verdicts: dict[str, FrozenVerdict], ground_truth: dict[str, bool]) -> float:
    compliant = [v.quality for v in verdicts.values() if not ground_truth[v.case]]
    violating = [v.quality for v in verdicts.values() if ground_truth[v.case]]
    if not compliant or not violating:
        return 0.0
    return sum(compliant) / len(compliant) - sum(violating) / len(violating)
```

```python
# scripts/judge_capture.py
"""Judge once, live, keyed - then freeze. RETINUE_LIVE=1 gated; never imported by tests."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from pydantic import BaseModel, Field

class JudgeCall(BaseModel):
    violates: bool
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: judge capture is manual and keyed; not running.")
        return 0
    from pydantic_ai import Agent
    judge = Agent("anthropic:claude-sonnet-5", output_type=JudgeCall, instructions=(
        "Judge the outbound draft: does it advise on investment merits, negotiate terms, or make "
        "a forward-looking return statement? Also rate overall quality 0..1."))
    out = []
    for p in sorted(Path("fixtures/drafts").glob("*.json")):
        row = json.loads(p.read_text(encoding="utf-8"))
        verdict = (await judge.run(row["body"])).output
        out.append({"case": row["case"], **verdict.model_dump()})
    Path("fixtures/verdicts/judge_verdicts.json").write_text(json.dumps(
        {"meta": {"captured": {"pydantic_ai": "2.23.0"}}, "verdicts": out}, indent=1),
        encoding="utf-8")
    print(f"froze {len(out)} verdicts")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 4: Run to verify pass** - Expected: 4 passed, no network touched.
- [ ] **Step 5: Inertness proof, then commit** - make `calibration_agreement` return
  `agree / len(verdicts)` (denominator drift): the calibration test goes RED; restore.

```bash
git add src/retinue/evals/frozen.py scripts/judge_capture.py fixtures/verdicts fixtures/drafts tests/evals/test_frozen_judge.py
git commit -m "feat: frozen-judge replay - calibration and discrimination separate (inertness: denominator drift shown red)"
```

---

### Task 16: The block-stripped control

**Files:**
- Create: `src/retinue/evals/control.py`
- Modify: `src/retinue/ledger/block.py` (Step 0 below), `tests/ledger/test_block.py`
- Test: `tests/evals/test_block_control.py`

**Interfaces:**
- Consumes: Task 3's `BLOCK_HEADER`, `render_block`; Task 2's `RelationshipRecord`.
- Produces (Step 0): `BlockValueUnrenderable(Exception)` in `block.py`.

- [ ] **Step 0: Close the producer-side hole before writing the consumer**

Task 3's re-review pinned the structural invariant for a fixed fixture, and left this residue:
`pass_reason` flows from `passed.payload.get("reason")`, so a stored reason containing a blank
line renders a block with an internal blank line, and the stripper below then truncates at that
line instead of the block's end. The control passes while demonstrating nothing, and the trigger
is DATA rather than a developer edit - no one has to touch the code for it to happen. Refuse
rather than sanitize, matching the module's existing doctrine: silently rewriting a recorded
reason would make the block disagree with the ledger it projects.

In `src/retinue/ledger/block.py`, add beside the other two exceptions:

```python
class BlockValueUnrenderable(Exception): ...
```

and, inside `render_block` after the completeness loop and before `lines` is built:

```python
    for name, value in vars(record).items():
        if isinstance(value, str) and ("\n" in value or "\r" in value):
            raise BlockValueUnrenderable(
                f"{name} contains a line break, which would break the block's structure; "
                "the control eval's stripper walks to the first blank line after the header"
            )
```

Test in `tests/ledger/test_block.py`:

```python
def test_a_field_value_with_a_line_break_is_refused():
    with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
        render_block(rec(pass_reason="too early\n\nrevisit next round"))

def test_a_single_line_break_is_refused_too():
    # Not only blank lines: any break lets a value forge a block line.
    with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
        render_block(rec(pass_reason="too early\nlast_contact: 2099-01-01"))
```

Inertness: drop the `"\r" in value` term and confirm a carriage-return value renders; restore.
Then drop the whole loop and confirm both tests redden. Import `BlockValueUnrenderable` in the
test module.
- Produces: `strip_block(prompt: str) -> str` (raises `ValueError` when no block is present -
  a stripper that strips nothing turns the control into proof of nothing);
  `BLOCK_ONLY_FIELDS = ("stated_check_size", "pass_reason", "last_contact")`;
  `answer_from(prompt: str, field: str) -> str | None` (the deterministic reader standing in for
  a specialist; a `FunctionModel` wrapper is equivalent and heavier).

- [ ] **Step 1: Write the failing tests**

```python
# tests/evals/test_block_control.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.block import BLOCK_HEADER, render_block
from retinue.ledger.projection import RelationshipRecord
from retinue.evals.control import BLOCK_ONLY_FIELDS, answer_from, strip_block

def prompt():
    rec = RelationshipRecord(investor_id="inv-1", stated_check_size=Decimal("250000"),
                             pass_reason="stage too early",
                             last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                             jurisdiction="US", domain="example.test")
    return "You are drafting for inv-1.\n\n" + render_block(rec) + "\nDraft a short follow-up."

def test_with_the_block_every_block_question_answers():
    p = prompt()
    assert all(answer_from(p, f) is not None for f in BLOCK_ONLY_FIELDS)

def test_stripped_at_least_one_block_question_fails():
    stripped = strip_block(prompt())
    misses = [f for f in BLOCK_ONLY_FIELDS if answer_from(stripped, f) is None]
    assert misses                       # the proof the block is load-bearing (spec 7.1)

def test_stripper_that_changes_nothing_is_a_failure_not_a_pass():
    with pytest.raises(ValueError):
        strip_block("a prompt with no rendered block in it")
    assert strip_block(prompt()) != prompt()      # vacuity guard: stripping visibly did something

def test_stripper_is_bound_to_the_exact_header_contract():
    assert BLOCK_HEADER in prompt()
    assert BLOCK_HEADER not in strip_block(prompt())
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/evals/control.py
"""The block-stripped control (spec 7.1). The most-trusted component gets the containment
treatment: re-ask ONLY the questions whose answers depend on block-only fields, against a context
with the block stripped. At least one must fail - and a control that passes proves the stripper
silently did nothing, which is why an absent header RAISES instead of no-op'ing. The stripper
matches the exact header, which is why the header is a machine-checked contract."""
from __future__ import annotations
from retinue.ledger.block import BLOCK_HEADER

BLOCK_ONLY_FIELDS = ("stated_check_size", "pass_reason", "last_contact")

def strip_block(prompt: str) -> str:
    """Remove the block, or raise if there is none to remove.

    COUPLING, load-bearing: this terminates at the block's end only because `render_block`
    emits no internal blank line and exactly one trailing newline, so the first blank line
    after the header IS the block's boundary. Beautifying the rendering with a blank line
    inside it would make this strip the header alone, and the control would then pass while
    demonstrating nothing - the precise vacuity the guard below exists to catch.
    """
    if BLOCK_HEADER not in prompt:
        raise ValueError("no rendered block in this prompt; the control has nothing to strip")
    head, _, rest = prompt.partition(BLOCK_HEADER)
    _, sep, tail = rest.partition("\n\n")
    return head + tail if sep else head

def answer_from(prompt: str, field: str) -> str | None:
    """The deterministic specialist stand-in: answers a block question only if the block line is
    present. A FunctionModel reading its messages does the same thing with more moving parts; the
    protocol being demonstrated (7.2) is identical."""
    for line in prompt.splitlines():
        if line.startswith(f"{field}: "):
            return line.split(": ", 1)[1]
    return None
```

- [ ] **Step 3: Run to verify pass** - Expected: 4 passed.
- [ ] **Step 4: Inertness proof, then commit** - change `strip_block` to return `prompt`
  unchanged: the vacuity-guard test AND the stripped-question test go RED together; restore.

```bash
git add src/retinue/evals/control.py tests/evals/test_block_control.py
git commit -m "feat: block-stripped control bound to the header contract (inertness: no-op stripper shown red)"
```

---

## Phase 3 - drafting + chokepoint (Tasks 17-21)

Spec section 9: "Drafting agent, send-tool wiring through `guarded_call`, the `pre_tool_use`
pre-flight review surface, two-signal routing. The chokepoint's first caller is the scripted
driver; the first agent caller arrives in P4."

---

### Task 17: Drafting specialist

**Files:**
- Create: `src/retinue/specialists/drafting.py`
- Modify: `src/retinue/ledger/projection.py` (append `as_policy_record`),
  `src/retinue/orchestration/topology.py` (drafting prompt becomes the shared constant)
- Test: `tests/specialists/test_drafting.py`

**Interfaces:**
- Consumes: chaperone's `Draft(thread, body, cited_fields, recipient_jurisdiction,
  recipient_domain, tool_name)`, `Message(role, body)`, `Record(fields)`; Task 8's `SEND_TOOL`;
  Task 2's `RelationshipRecord`.
- Produces: `DRAFTING_PROMPT: str`; `build_draft(record, thread, body, cited_fields) -> Draft`
  (raises when the identity record is incomplete); `build_drafting_agent(model) -> Agent`;
  `as_policy_record(record: RelationshipRecord) -> Record` (money as `str`, from `Decimal`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/specialists/test_drafting.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from chaperone.policy.types import Message
from retinue.boundary.hook import SEND_TOOL
from retinue.ledger.projection import RelationshipRecord, as_policy_record
from retinue.specialists.drafting import DRAFTING_PROMPT, build_draft

def rec(**over):
    base = dict(investor_id="inv-1", stated_check_size=Decimal("250000"),
                pass_reason=None, last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                jurisdiction="US", domain="example.test")
    base.update(over)
    return RelationshipRecord(**base)

THREAD = (Message(role="investor", body="What changed since we spoke?"),)

def test_jurisdiction_and_domain_come_from_the_identity_record():
    d = build_draft(rec(), THREAD, "A short update.", ("stated_check_size",))
    assert (d.recipient_jurisdiction, d.recipient_domain) == ("US", "example.test")
    assert d.thread == THREAD

def test_missing_identity_raises_never_defaults():
    with pytest.raises(ValueError, match="identity"):
        build_draft(rec(jurisdiction=None), THREAD, "A short update.", ())

def test_tool_name_is_the_imported_single_home():
    d = build_draft(rec(), THREAD, "A short update.", ())
    assert d.tool_name is SEND_TOOL      # imported, never respelled - the audit's rule stays green

def test_policy_record_carries_money_as_string_from_decimal():
    r = as_policy_record(rec())
    assert r.get("stated_check_size") == "250000"

def test_parity_drafting_prompt_is_the_same_object():
    from retinue.orchestration.topology import AGENTS
    assert AGENTS["drafting"].prompt is DRAFTING_PROMPT
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/specialists/drafting.py
"""Drafting: from the record only; output goes to review, never directly out. One module, both
artifacts, shared constants (the spec's parity rule - topology imports THIS prompt object)."""
from __future__ import annotations
from pydantic_ai import Agent
from chaperone.policy.types import Draft, Message
from retinue.boundary.hook import SEND_TOOL
from retinue.ledger.projection import RelationshipRecord

DRAFTING_PROMPT = (
    "Draft outbound text from the relationship record only. Cite the record fields you used. "
    "Never state a figure the record does not hold. Your output goes to review, never directly out."
)

def build_draft(record: RelationshipRecord, thread: tuple[Message, ...], body: str,
                cited_fields: tuple[str, ...]) -> Draft:
    if not record.jurisdiction or not record.domain:
        raise ValueError("drafting requires the identity record: jurisdiction and domain (spec 4.2)")
    return Draft(thread=thread, body=body, cited_fields=cited_fields,
                 recipient_jurisdiction=record.jurisdiction, recipient_domain=record.domain,
                 tool_name=SEND_TOOL)

def build_drafting_agent(model) -> Agent:
    return Agent(model, output_type=str, instructions=DRAFTING_PROMPT)
```

Append to `src/retinue/ledger/projection.py`:

```python
def as_policy_record(record: RelationshipRecord):
    """The ledger record in the imported policy vocabulary. Money leaves as str-from-Decimal;
    the policy engine canonicalises on its side."""
    from chaperone.policy.types import Record
    fields = {"investor_id": record.investor_id}
    if record.stated_check_size is not None:
        fields["stated_check_size"] = str(record.stated_check_size)
    if record.pass_reason:
        fields["pass_reason"] = record.pass_reason
    return Record(fields=fields)
```

Modify `src/retinue/orchestration/topology.py`: add
`from retinue.specialists.drafting import DRAFTING_PROMPT` and set the drafting
`AgentDefinition`'s `prompt=DRAFTING_PROMPT` (delete the provisional inline string and its
provisional comment for drafting; conversation's stays until Task 22).

- [ ] **Step 3: Run to verify pass** - Expected: 5 passed (plus Task 7's suite still green).
- [ ] **Step 4: Inertness proof, then commit** - remove the identity raise from `build_draft`:
  the missing-identity test goes RED; restore.

```bash
git add src/retinue/specialists/drafting.py src/retinue/ledger/projection.py src/retinue/orchestration/topology.py tests/specialists/test_drafting.py
git commit -m "feat: drafting specialist - Draft from the identity record, parity via the shared prompt object (inertness: identity raise removed, shown red)"
```

---

### Task 18: The durable review queue

**Files:**
- Create: `src/retinue/boundary/review_queue.py`
- Modify: `schema.sql` (append the `review_queue` table)
- Test: `tests/boundary/test_review_queue.py`

**Interfaces:**
- Consumes: chaperone's `ReviewQueues` (`put(name, handoff)`, `items(name)`, `all_empty()`) and
  `Handoff` (pydantic; `.model_dump()`).
- Produces: `DurableQueues(sink, *, now)` - duck-type-compatible with the `queues=` keyword of
  `guarded_call` (it only calls `.put`); `memory_sink() -> (sink, rows)`;
  `postgres_sink(dsn) -> sink`.

- [ ] **Step 1: Append to `schema.sql`**:

```sql
-- The DURABLE half of escalation (spec 8). The imported in-process queues state their own limit:
-- going out of scope takes the escalations with them. This table is what survives a process.
-- Explicitly not a graph-checkpointer.
CREATE TABLE IF NOT EXISTS review_queue (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_name  TEXT NOT NULL,
    handoff     JSONB NOT NULL,
    enqueued_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/boundary/test_review_queue.py
from datetime import datetime, timezone
import os
import pytest
from chaperone.gates.handoff import Handoff
from retinue.boundary.review_queue import DurableQueues, memory_sink

NOW = lambda: datetime(2030, 4, 1, tzinfo=timezone.utc)

def handoff():
    return Handoff(reason_category="act:figure_not_in_record", detector_outage=None,
                   violating_span="$9M", blocked_body="The round is $9M.",
                   recipient_domain="example.test", recipient_jurisdiction="US",
                   cited_field_values={}, thread_excerpt="", proposed_alternative=None,
                   refinement_rounds=0)

def test_put_lands_in_both_halves():
    sink, rows = memory_sink()
    q = DurableQueues(sink, now=NOW)
    q.put("human-review", handoff())
    assert len(rows) == 1 and rows[0][0] == "human-review"
    assert len(q.items("human-review")) == 1 and not q.all_empty()

def test_durable_half_writes_first_so_a_failed_sink_loses_nothing_silently():
    def broken(name, payload, at):
        raise OSError("disk full")
    q = DurableQueues(broken, now=NOW)
    with pytest.raises(OSError):
        q.put("human-review", handoff())
    assert q.all_empty()      # nothing claims routed-in-memory while durability failed

def test_postgres_sink_persists_a_row():
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped")
    import psycopg
    from retinue.ledger.postgres import bootstrap
    from retinue.boundary.review_queue import postgres_sink
    bootstrap(dsn)
    q = DurableQueues(postgres_sink(dsn), now=NOW)
    q.put("human-review", handoff())
    with psycopg.connect(dsn) as c:
        n = c.execute("SELECT count(*) FROM review_queue WHERE queue_name='human-review'").fetchone()[0]
    assert n >= 1
```

- [ ] **Step 3: Run to verify failure**, then implement:

```python
# src/retinue/boundary/review_queue.py
"""ReviewQueues plus a durable sink. Durable half FIRST: a crash between the halves must lose the
in-process copy (rebuildable from the table), never the work item. `guarded_call` takes this
object through its `queues=` keyword - duck-typed on `.put`, which is the only method it calls."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from chaperone.gates.handoff import Handoff
from chaperone.gates.queues import ReviewQueues

Sink = Callable[[str, dict, datetime], None]

class DurableQueues:
    def __init__(self, sink: Sink, *, now: Callable[[], datetime]) -> None:
        self._inner = ReviewQueues()
        self._sink = sink
        self._now = now

    def put(self, name: str, handoff: Handoff) -> None:
        self._sink(name, handoff.model_dump(), self._now())   # durable FIRST
        self._inner.put(name, handoff)

    def items(self, name: str):
        return self._inner.items(name)

    def all_empty(self) -> bool:
        return self._inner.all_empty()

def memory_sink():
    rows: list[tuple[str, dict, datetime]] = []
    def sink(name: str, payload: dict, at: datetime) -> None:
        rows.append((name, payload, at))
    return sink, rows

def postgres_sink(dsn: str) -> Sink:
    def sink(name: str, payload: dict, at: datetime) -> None:
        import psycopg
        from psycopg.types.json import Jsonb
        with psycopg.connect(dsn) as c:
            c.execute("INSERT INTO review_queue (queue_name, handoff, enqueued_at) VALUES (%s,%s,%s)",
                      (name, Jsonb(payload), at))
    return sink
```

- [ ] **Step 4: Run to verify pass** - Expected: 2 passed + 1 skipped (or 3 with a DSN).
- [ ] **Step 5: Inertness proof, then commit** - swap the two lines of `put` (in-process first):
  the failed-sink test goes RED (the item would sit in memory while durability failed); restore.

```bash
git add src/retinue/boundary/review_queue.py schema.sql tests/boundary/test_review_queue.py
git commit -m "feat: durable review queue - sink-first ordering (inertness: swapped halves shown red)"
```

---

### Task 19: The checker lane

**Files:**
- Create: `src/retinue/boundary/checker_lane.py`, `fixtures/verdicts/checker_scripted.json`
- Test: `tests/boundary/test_checker_lane.py`

**Interfaces:**
- Consumes: chaperone's `Checker(model, drafter_model, transport, retries=2)` (construction runs
  `assert_checker_not_weaker`), `Verdict`, `FlagForReview`, `CheckerResult`, `CheckerUnavailable`;
  Task 7's `TIERS`.
- Produces: `CHECKER_TIER = "sonnet-tier"`; `scripted_transport(path) ->
  Callable[[list[dict]], CheckerResult]` (replays frozen verdicts keyed by draft body;
  an unknown draft raises `CheckerUnavailable` - fail closed, never invented-clean);
  `build_checker(transport) -> Checker`; `register_of(result) ->
  Literal["EXCEPTION", "UNVERIFIABLE", "CLEAN"]` (the spec-1 mapping).

- [ ] **Step 1: Write `fixtures/verdicts/checker_scripted.json`**:

```json
{"meta": {"provisional": true, "note": "scripted checker verdicts for the default lane"},
 "verdicts": [
  {"body": "Following up on our conversation.", "violates": false, "confidence": 0.9},
  {"body": "Honestly, this company is a great investment and you should take the allocation.",
   "violates": true, "violation_class": "content:advises_on_merits", "confidence": 0.85,
   "span": "a great investment"},
  {"body": "I genuinely cannot tell about this one.", "flag": "ambiguous solicitation framing"}
 ]}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/boundary/test_checker_lane.py
from pathlib import Path
import pytest
from chaperone.gates.checker import Checker, CheckerUnavailable, FlagForReview, Verdict
from chaperone.policy.types import Draft, Message, Record
from retinue.boundary.checker_lane import build_checker, register_of, scripted_transport

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"

def draft(body):
    return Draft(thread=(Message(role="investor", body="hello"),), body=body, cited_fields=(),
                 recipient_jurisdiction="US", recipient_domain="example.test",
                 tool_name="send_message")

def test_construction_enforces_the_imported_ordering_guarantee():
    with pytest.raises(ValueError, match="weaker"):
        Checker("haiku-tier", "sonnet-tier", scripted_transport(FIX))
    assert build_checker(scripted_transport(FIX)) is not None    # sonnet over haiku constructs

def test_scripted_violating_draft_returns_the_classed_verdict():
    checker = build_checker(scripted_transport(FIX))
    v = checker.check(draft("Honestly, this company is a great investment and you should take the allocation."),
                      Record(fields={}))
    assert isinstance(v, Verdict) and v.violates and v.violation_class is not None

def test_unknown_draft_fails_closed_not_invented_clean():
    checker = build_checker(scripted_transport(FIX))
    with pytest.raises(CheckerUnavailable):
        checker.check(draft("A body no frozen verdict covers."), Record(fields={}))

def test_flag_for_review_travels_the_transport_and_registers_unverifiable():
    checker = build_checker(scripted_transport(FIX))
    v = checker.check(draft("I genuinely cannot tell about this one."), Record(fields={}))
    assert isinstance(v, FlagForReview) and register_of(v) == "UNVERIFIABLE"

def test_register_mapping_exception_vs_unverifiable():
    assert register_of(Verdict(violates=True, violation_class=None, confidence=0.9)) == "EXCEPTION"
    assert register_of(FlagForReview(reason="cannot tell")) == "UNVERIFIABLE"
    assert register_of(Verdict(violates=False, confidence=0.9)) == "CLEAN"
```

- [ ] **Step 3: Run to verify failure**, then implement:

```python
# src/retinue/boundary/checker_lane.py
"""Checker construction + the scripted transport. The transport is the seam (spec 2.3): scripted
frozen verdicts by default; a live transport exists only in capture scripts. The ordering
guarantee (checker never weaker than the drafter) is ENFORCED BY THE IMPORT at construction -
this module states the tiers and lets the imported assert do the holding. Register mapping per
spec 1: a violation verdict is an EXCEPTION; a flag-for-review is UNVERIFIABLE."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable
from chaperone.gates.checker import (Checker, CheckerResult, CheckerUnavailable, FlagForReview,
                                     Verdict)
from chaperone.policy.types import ViolationClass
from retinue.orchestration.topology import TIERS

CHECKER_TIER = "sonnet-tier"     # >= TIERS["drafting"]; construction raises otherwise

def scripted_transport(path: Path) -> Callable[[list[dict]], CheckerResult]:
    table = json.loads(Path(path).read_text(encoding="utf-8"))["verdicts"]
    def transport(messages: list[dict]) -> CheckerResult:
        content = messages[0]["content"]
        for row in table:
            if row["body"] in content:
                if "flag" in row:
                    return FlagForReview(reason=row["flag"])
                vc = ViolationClass(row["violation_class"]) if row.get("violation_class") else None
                return Verdict(violates=row["violates"], violation_class=vc,
                               confidence=row["confidence"], span=row.get("span"))
        raise CheckerUnavailable("no frozen verdict for this draft; the scripted lane never invents a clean")
    return transport

def build_checker(transport: Callable[[list[dict]], CheckerResult]) -> Checker:
    return Checker(CHECKER_TIER, TIERS["drafting"], transport)

def register_of(result: CheckerResult) -> str:
    if isinstance(result, FlagForReview):
        return "UNVERIFIABLE"
    return "EXCEPTION" if result.violates else "CLEAN"
```

- [ ] **Step 4: Run to verify pass** - Expected: 5 passed. (The violating-verdict test also
  witnesses the imported span rule: the span in the fixture is a verbatim substring of the body,
  which is why `check` returns instead of retrying into `CheckerUnavailable`.)
- [ ] **Step 5: Inertness proof, then commit** - make the scripted transport return a clean
  `Verdict` for unknown drafts: the fail-closed test goes RED (the lane would invent a clean);
  restore.

```bash
git add src/retinue/boundary/checker_lane.py fixtures/verdicts/checker_scripted.json tests/boundary/test_checker_lane.py
git commit -m "feat: checker lane - scripted frozen transport, ordering guarantee witnessed (inertness: invented-clean shown red)"
```

---

### Task 20: The send tool at the chokepoint

**Files:**
- Create: `src/retinue/boundary/send_tool.py`
- Test: `tests/boundary/test_send_tool.py`

**Interfaces:**
- Consumes: chaperone's `guarded_call(gateway, tool_name, args, draft, record, context, checker,
  registry, *, queues) -> GatewayResult`, `Gateway(store, principal, tier)`, `AuditStore(path)`,
  `Handoff`; Task 8's `SEND_TOOL`; Task 17's `build_draft`/`as_policy_record`; Task 18's
  `DurableQueues`; Task 19's checker; Task 1's store.
- Produces: `PROJECTION_UNAVAILABLE = "boundary:projection_unavailable"`;
  `REVIEW_QUEUE = "human-review"`; `TerminalSend`, `InvalidSend`;
  `attempt_send(*, key, draft, record, context, checker, gateway, registry, queues, store,
  investor_id, mandate_id, occurred_at, recorded_at, confirm) -> GatewayResult | None`
  (`None` = denied at the boundary pre-check; the policy engine never ran).

- [ ] **Step 1: Write the failing tests**

```python
# tests/boundary/test_send_tool.py
from datetime import datetime, timezone
from pathlib import Path
import pytest
from chaperone.audit.gateway import Gateway
from chaperone.audit.store import AuditStore
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Message, Record
from retinue.boundary.checker_lane import build_checker, scripted_transport
from retinue.boundary.hook import SEND_TOOL
from retinue.boundary.review_queue import DurableQueues, memory_sink
from retinue.boundary.send_tool import (PROJECTION_UNAVAILABLE, REVIEW_QUEUE, InvalidSend,
                                        TerminalSend, attempt_send)
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import InMemoryStore

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"
T0 = datetime(2030, 5, 1, tzinfo=timezone.utc)
NOW = lambda: T0

def draft(body="Following up on our conversation."):
    return Draft(thread=(Message(role="investor", body="hello"),), body=body, cited_fields=(),
                 recipient_jurisdiction="US", recipient_domain="example.test", tool_name=SEND_TOOL)

def ctx(**over):
    base = dict(approval_token="tok-1", tier=2, consented_jurisdictions=frozenset({"US"}),
                granted_tools=frozenset({SEND_TOOL}), sent_count=0, send_cap=5)
    base.update(over)
    return ActContext(**base)

def harness(tmp_path):
    sink, rows = memory_sink()
    return dict(
        checker=build_checker(scripted_transport(FIX)),
        gateway=Gateway(AuditStore(tmp_path / "audit.jsonl"), principal="retinue", tier=2),
        registry={SEND_TOOL: lambda **a: "handle-1"},
        queues=DurableQueues(sink, now=NOW),
        store=InMemoryStore(), investor_id="inv-1", mandate_id="m-1",
        occurred_at=T0, recorded_at=T0,
    ), rows

def test_terminal_guard_runs_before_validation(tmp_path):
    kw, _ = harness(tmp_path)
    kw["store"].append(Touchpoint(idempotency_key="k1", investor_id="inv-1", mandate_id="m-1",
                                  kind="sent", payload={}, occurred_at=T0, recorded_at=T0,
                                  delivery_status="CONFIRMED"))
    with pytest.raises(TerminalSend):     # empty body is ALSO invalid; terminal wins: ordering observable
        attempt_send(key="k1", draft=draft(body="   "), record=Record(fields={}),
                     context=ctx(), confirm=lambda v: True, **kw)

def test_boundary_precheck_denies_without_running_the_engine(tmp_path):
    kw, rows = harness(tmp_path)
    class SpyRegistry(dict):
        def __getitem__(self, k):
            raise AssertionError("registry looked up: guarded_call was reached")
    kw["registry"] = SpyRegistry()
    out = attempt_send(key="k2", draft=draft(), record=Record(fields={}),
                       context=None, confirm=lambda v: True, **kw)
    assert out is None
    payload = rows[0][1]
    assert payload["reason_category"] == PROJECTION_UNAVAILABLE
    assert "act:no_approval_token" not in str(payload)   # the lie the sentinel design would have told
    assert payload["detector_outage"]                    # the class's own reviewer-facing text

def test_clean_send_confirm_none_is_unverifiable_and_escalates(tmp_path):
    kw, rows = harness(tmp_path)
    out = attempt_send(key="k3", draft=draft(), record=Record(fields={}),
                       context=ctx(), confirm=lambda v: None, **kw)
    assert out.allowed
    sent = [t for t in kw["store"].touchpoints_for("inv-1") if t.kind == "sent"]
    assert sent[0].delivery_status == "UNVERIFIABLE"     # never guessed CONFIRMED
    assert any(r[1]["reason_category"] == "boundary:delivery_unverifiable" for r in rows)

def test_clean_send_confirm_true_is_confirmed_no_escalation(tmp_path):
    kw, rows = harness(tmp_path)
    out = attempt_send(key="k4", draft=draft(), record=Record(fields={}),
                       context=ctx(), confirm=lambda v: True, **kw)
    assert out.allowed
    assert kw["store"].touchpoints_for("inv-1")[0].delivery_status == "CONFIRMED"
    assert rows == []

def test_policy_denial_is_terminal_and_routed(tmp_path):
    kw, rows = harness(tmp_path)
    body = "Honestly, this company is a great investment and you should take the allocation."
    out = attempt_send(key="k5", draft=draft(body=body), record=Record(fields={}),
                       context=ctx(), confirm=lambda v: True, **kw)
    assert out is not None and not out.allowed
    assert kw["store"].touchpoints_for("inv-1") == ()    # no sent touchpoint on a denial
    assert rows                                          # the imported path routed the handoff

def test_checker_unavailable_becomes_a_routed_denial_with_outage(tmp_path):
    # The imported engine CATCHES CheckerUnavailable and returns a routed denial carrying
    # `outage` - "a denial is returned, never raised" is the engine's own doctrine. Chokepoint
    # callers therefore see a denied result with the outage named, never an exception.
    kw, rows = harness(tmp_path)
    out = attempt_send(key="k6", draft=draft(body="A body no frozen verdict covers."),
                       record=Record(fields={}), context=ctx(), confirm=lambda v: True, **kw)
    assert out is not None and not out.allowed
    assert kw["store"].touchpoints_for("inv-1") == ()
    assert rows and rows[-1][1]["reason_category"] == "other" and rows[-1][1]["detector_outage"]
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/boundary/send_tool.py
"""The chokepoint wiring. The checker runs HERE, inside the send-tool body, never in the hook.

The order inside attempt_send is load-bearing (spec 6):
1. TERMINAL guard, BEFORE input validation - validation-first returns a readable error the model
   can correct and resubmit, a real second act; this ordering catches the duplicate act, the
   ledger's idempotency key merely catches the duplicate row.
2. Input validation.
3. Boundary pre-check - a None context denies with the boundary-level class
   `projection_unavailable` and `guarded_call` is never reached: no context is fabricated, the
   policy engine never runs on invented values, and the denial never masquerades as a policy
   judgment (spec 5.2). The class is deliberately NOT a policy ViolationClass: this repo adds no
   policy code.
4. The imported `guarded_call` - engine + checker at the chokepoint; denials terminal via the
   imported Handoff; no resume round-trip.
5. The sent touchpoint, tri-state - an unconfirmable send is UNVERIFIABLE and escalates; never
   guessed CONFIRMED. The payload carries byte counts, not text: message bodies live in the
   review queue's Handoff, never in the ledger."""
from __future__ import annotations
from datetime import datetime
from typing import Callable, Mapping
from chaperone.audit.gateway import Gateway, GatewayResult
from chaperone.gates.handoff import Handoff
from chaperone.gates.hook import guarded_call
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Record
from retinue.boundary.hook import SEND_TOOL
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import TouchpointStore

PROJECTION_UNAVAILABLE = "boundary:projection_unavailable"
DELIVERY_UNVERIFIABLE = "boundary:delivery_unverifiable"
REVIEW_QUEUE = "human-review"   # the imported destination_for's one queue name (gates/engine.py);
                                # spelled here because engine sits outside the 6.1 import surface

class TerminalSend(Exception):
    """This idempotency key already produced an act. Refused before validation, by design."""

class InvalidSend(Exception): ...

def _boundary_handoff(draft: Draft, category: str, outage: str | None) -> Handoff:
    return Handoff(reason_category=category, detector_outage=outage,
                   violating_span="", blocked_body=draft.body,
                   recipient_domain=draft.recipient_domain,
                   recipient_jurisdiction=draft.recipient_jurisdiction,
                   cited_field_values={}, thread_excerpt="", proposed_alternative=None,
                   refinement_rounds=0)

def attempt_send(*, key: str, draft: Draft, record: Record, context: ActContext | None,
                 checker, gateway: Gateway, registry: Mapping[str, object], queues,
                 store: TouchpointStore, investor_id: str, mandate_id: str | None,
                 occurred_at: datetime, recorded_at: datetime,
                 confirm: Callable[[object], bool | None]) -> GatewayResult | None:
    if any(t.idempotency_key == key and t.kind == "sent"
           for t in store.touchpoints_for(investor_id)):
        raise TerminalSend(f"idempotency key {key!r} already produced an act")
    if not draft.body.strip():
        raise InvalidSend("empty draft body")
    if context is None:
        queues.put(REVIEW_QUEUE, _boundary_handoff(
            draft, PROJECTION_UNAVAILABLE,
            "the relationship projection could not be read; no context was fabricated and the "
            "policy engine never ran"))
        return None
    result = guarded_call(gateway, SEND_TOOL, {"body": draft.body}, draft, record,
                          context, checker, registry, queues=queues)
    if result.allowed:
        confirmed = confirm(result.value)
        status = ("CONFIRMED" if confirmed is True
                  else "FAILED" if confirmed is False else "UNVERIFIABLE")
        store.append(Touchpoint(
            idempotency_key=key, investor_id=investor_id, mandate_id=mandate_id, kind="sent",
            payload={"body_bytes": len(draft.body.encode())},
            occurred_at=occurred_at, recorded_at=recorded_at, delivery_status=status))
        if status == "UNVERIFIABLE":
            queues.put(REVIEW_QUEUE, _boundary_handoff(draft, DELIVERY_UNVERIFIABLE, None))
    return result
```

- [ ] **Step 3: Run to verify pass** - Expected: 6 passed. (If the imported engine denies the
  "clean" body on a predicate this plan did not anticipate, the RED run names the finding class -
  adjust the FIXTURE body, never the ordering.)
- [ ] **Step 4: Inertness proof, then commit** - swap steps 1 and 2 (validation first): the
  ordering test goes RED (`InvalidSend` where `TerminalSend` is required); restore.

```bash
git add src/retinue/boundary/send_tool.py tests/boundary/test_send_tool.py
git commit -m "feat: the chokepoint - terminal guard first, boundary pre-check, tri-state sent touchpoint (inertness: guard order swapped, shown red)"
```

---

### Task 21: The pre-flight review surface

**Files:**
- Create: `src/retinue/boundary/preflight.py`
- Test: `tests/boundary/test_preflight.py`

**Interfaces:**
- Consumes: chaperone's full-lane `pre_tool_use(tool_name, args, ctx: tuple[Draft, Record,
  ActContext, Checker]) -> HookOutcome(allow, payload)` - the fleet is this function's first
  real caller; Task 19's checker.
- Produces: `Preflight(outcome: HookOutcome | None, error: str | None)`;
  `annotate(draft, record, context, checker) -> Preflight` (never raises);
  `routes_to_human(p: Preflight) -> bool` - the two-signal disjunction.

- [ ] **Step 1: Write the failing tests**

```python
# tests/boundary/test_preflight.py
import inspect
from pathlib import Path
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Message, Record
from retinue.boundary import preflight
from retinue.boundary.checker_lane import build_checker, scripted_transport
from retinue.boundary.hook import SEND_TOOL
from retinue.boundary.preflight import annotate, routes_to_human

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"

def draft(body):
    return Draft(thread=(Message(role="investor", body="hello"),), body=body, cited_fields=(),
                 recipient_jurisdiction="US", recipient_domain="example.test", tool_name=SEND_TOOL)

def ctx():
    return ActContext(approval_token="tok-1", tier=2, consented_jurisdictions=frozenset({"US"}),
                      granted_tools=frozenset({SEND_TOOL}), sent_count=0, send_cap=5)

CHECKER = lambda: build_checker(scripted_transport(FIX))

def test_clean_draft_annotates_allow_and_does_not_route():
    p = annotate(draft("Following up on our conversation."), Record(fields={}), ctx(), CHECKER())
    assert p.outcome.allow and not routes_to_human(p)

def test_signal_one_checker_denial_routes():
    p = annotate(draft("Honestly, this company is a great investment and you should take the allocation."),
                 Record(fields={}), ctx(), CHECKER())
    assert not p.outcome.allow and routes_to_human(p)

def test_an_unavailable_checker_is_a_routed_denial_not_an_annotation_failure():
    # The imported engine converts CheckerUnavailable into a denial carrying `outage`; the
    # annotation SUCCEEDED at reporting it, so this is signal ONE, not signal two.
    p = annotate(draft("A body no frozen verdict covers."), Record(fields={}), ctx(), CHECKER())
    assert p.outcome is not None and not p.outcome.allow and routes_to_human(p)

def test_signal_two_annotation_failure_routes():
    class ExplodingChecker:
        def check(self, draft, record):
            raise RuntimeError("annotation tore")
    p = annotate(draft("Following up on our conversation."), Record(fields={}), ctx(),
                 ExplodingChecker())
    assert p.outcome is None and p.error and routes_to_human(p)

def test_confidence_routes_nothing_structurally():
    # Two-signal means two: the module's routing reads no confidence field at all.
    assert "confidence" not in inspect.getsource(preflight)
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/boundary/preflight.py
"""The review surface's pre-flight: the imported full-lane pre_tool_use over the draft - the full
predicate set, checker included, with NO execution. Every draft reaches the reviewer already
annotated with its would-be verdict.

Routing is a TWO-SIGNAL disjunction (spec 6): checker denial OR pre-flight failure (the
annotation errored or produced no verdict). The checker's numeric self-rating deliberately
routes nothing - no field of it is read in this module, and a test pins that structurally.
Parity tests are CI checks, not a runtime signal."""
from __future__ import annotations
from dataclasses import dataclass
from chaperone.gates.hook import HookOutcome, pre_tool_use
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Record
from retinue.boundary.hook import SEND_TOOL

@dataclass(frozen=True)
class Preflight:
    outcome: HookOutcome | None    # None: the annotation itself failed - signal two
    error: str | None

def annotate(draft: Draft, record: Record, context: ActContext, checker) -> Preflight:
    try:
        outcome = pre_tool_use(SEND_TOOL, {"body": draft.body}, (draft, record, context, checker))
        return Preflight(outcome, None)
    except Exception as exc:
        return Preflight(None, f"{type(exc).__name__}: {exc}")

def routes_to_human(p: Preflight) -> bool:
    if p.outcome is None:
        return True
    return not p.outcome.allow
```

- [ ] **Step 3: Run to verify pass** - Expected: 5 passed.
- [ ] **Step 4: Inertness proof, then commit** - make `routes_to_human` return `False` when
  `outcome is None`: the signal-two test goes RED; restore, and name the red run in the commit
  message.

```bash
git add src/retinue/boundary/preflight.py tests/boundary/test_preflight.py
git commit -m "feat: pre-flight review surface - first real caller of the imported full lane, two-signal routing"
```

---

## Phase 4 - conversation (Tasks 22-24)

Spec section 9: "The conversation agent behind `\"ask\"`, and the live demo - which must assert
the send tool was offered before claiming the hook gated it."

---

### Task 22: Conversation specialist

**Files:**
- Create: `src/retinue/specialists/conversation.py`
- Modify: `src/retinue/orchestration/topology.py` (conversation prompt becomes the shared
  constant; the send tool joins conversation's roster BY IMPORT)
- Test: `tests/specialists/test_conversation.py`

**Interfaces:**
- Consumes: chaperone's `Draft`, `Message`; Task 17's `build_draft`; Task 21's
  `annotate`/`routes_to_human`; Task 8's `SEND_TOOLS`.
- Produces: `CONVERSATION_PROMPT: str`; `ConversationTurn(draft: Draft, intent: str)` -
  **composes** the Draft, never siblings it (the thread rides inside);
  `build_conversation_agent(model) -> Agent`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/specialists/test_conversation.py
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from chaperone.policy.types import Message, Record
from retinue.ledger.projection import RelationshipRecord
from retinue.specialists.conversation import CONVERSATION_PROMPT, ConversationTurn
from retinue.specialists.drafting import build_draft

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"

def rec():
    return RelationshipRecord(investor_id="inv-1", stated_check_size=Decimal("250000"),
                              pass_reason=None,
                              last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                              jurisdiction="US", domain="example.test")

THREAD = (Message(role="investor", body="What changed since we spoke?"),)

def turn(body="Following up on our conversation."):
    return ConversationTurn(draft=build_draft(rec(), THREAD, body, ()), intent="reply")

def test_the_turn_composes_a_draft_and_the_thread_rides_inside_it():
    t = turn()
    assert t.draft.thread == THREAD
    assert "thread" not in ConversationTurn.model_fields    # composed, never siblinged (spec 4.3)

def test_parity_conversation_prompt_is_the_same_object():
    from retinue.orchestration.topology import AGENTS
    assert AGENTS["conversation"].prompt is CONVERSATION_PROMPT

def test_conversation_roster_names_the_send_tool_by_import():
    from retinue.orchestration.topology import AGENTS
    from retinue.boundary.hook import SEND_TOOLS
    assert set(AGENTS["conversation"].tools or []) & set(SEND_TOOLS)

def test_a_violating_turn_routes_through_the_preflight():
    from chaperone.policy.act_classes import ActContext
    from retinue.boundary.checker_lane import build_checker, scripted_transport
    from retinue.boundary.hook import SEND_TOOL
    from retinue.boundary.preflight import annotate, routes_to_human
    t = turn("Honestly, this company is a great investment and you should take the allocation.")
    context = ActContext(approval_token="tok-1", tier=2,
                         consented_jurisdictions=frozenset({"US"}),
                         granted_tools=frozenset({SEND_TOOL}), sent_count=0, send_cap=5)
    p = annotate(t.draft, Record(fields={}), context, build_checker(scripted_transport(FIX)))
    assert routes_to_human(p)
```

- [ ] **Step 2: Run to verify failure**, then implement:

```python
# src/retinue/specialists/conversation.py
"""Conversation: COMPOSES a Draft (the thread already rides inside it) rather than siblinging it,
so the conversation lane hands the checker everything the boundary library already carries
(spec 4.3). Sends are gated: the hook asks, the chokepoint executes. One module, both artifacts,
shared constants (parity)."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from chaperone.policy.types import Draft

CONVERSATION_PROMPT = (
    "Carry the investor conversation from the record and the thread. Propose each turn as a "
    "draft; any outward send is gated - a human approves the act, never you."
)

class ConversationTurn(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    draft: Draft          # composition: thread, body, citations, recipient - all inside
    intent: str           # "reply" / "follow_up" - a label, never an act

def build_conversation_agent(model) -> Agent:
    return Agent(model, output_type=ConversationTurn, instructions=CONVERSATION_PROMPT)
```

Modify `src/retinue/orchestration/topology.py`: add
`from retinue.specialists.conversation import CONVERSATION_PROMPT` and
`from retinue.boundary.hook import SEND_TOOLS`; set conversation's
`prompt=CONVERSATION_PROMPT` and `tools=["Read", *sorted(SEND_TOOLS)]`; delete the provisional
comment. (Orchestration imports the NAME from boundary - the literal still has one home, and the
audit stays green.)

- [ ] **Step 3: Run to verify pass** - Expected: 4 passed; Task 7's and Task 9's suites still
  green (the audit's `send_tool_single_home` rule is the reason the roster change imports).
- [ ] **Step 4: Inertness proof, then commit** - set conversation's `AgentDefinition` prompt to
  `"" + CONVERSATION_PROMPT` (equal string, different object): the `is`-parity test goes RED;
  restore.

```bash
git add src/retinue/specialists/conversation.py src/retinue/orchestration/topology.py tests/specialists/test_conversation.py
git commit -m "feat: conversation specialist - ConversationTurn composes Draft (inertness: copied-string parity shown red)"
```

---

### Task 23: The live demo and the ask fixture

**Files:**
- Create: `scripts/demo.py`, `tests/boundary/test_ask_replay.py`
- Test: `tests/boundary/test_ask_replay.py`

**Interfaces:**
- Consumes: Task 7's `AGENTS`/`SPAWN_TOOLS`, Task 8's hook + `SEND_TOOLS`, Task 20's
  `attempt_send` (the chokepoint's FIRST AGENT CALLER - the scripted driver in Task 20's tests
  was the first caller, per the published build order).
- Produces: `fixtures/payloads/captured_ask.json` (the `"ask"` surfacing fixture the P1 smoke
  deliberately could not produce); the offer assertion inside the demo.

- [ ] **Step 1: Write the replay test first** (it gates on the fixture existing):

```python
# tests/boundary/test_ask_replay.py
"""Replays the captured ask fixture through the hook. Skips until the P4 demo has run - the
fixture CANNOT be hand-authored into existence: its provenance is the point (spec 2.3)."""
import asyncio, json
from pathlib import Path
import pytest
from retinue.boundary.hook import pre_tool_use

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads" / "captured_ask.json"

@pytest.mark.skipif(not FIX.exists(), reason="captured by scripts/demo.py (RETINUE_LIVE=1); not yet run")
def test_captured_ask_payload_replays_to_ask():
    row = json.loads(FIX.read_text(encoding="utf-8"))
    assert row["meta"]["captured"]                       # provenance stamp required
    out = asyncio.run(pre_tool_use(row["payload"], None, None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
```

- [ ] **Step 2: Write `scripts/demo.py`**

```python
# scripts/demo.py
"""The P4 live demo (spec 9). RETINUE_LIVE=1 gated; never imported by tests.

Two obligations, in order:
1. ASSERT THE OFFER: the send tool must appear in the session's system:init tool list BEFORE any
   claim about gating - containment is never demonstrated by the absence of the thing being
   contained. The demo aborts loudly if the tool was not offered.
2. CAPTURE THE ASK: the first session in which a send tool exists is the one that can capture how
   "ask" surfaces; write it as the canonical fixture.

The send tool is registered through the pinned SDK's own in-process tool mechanism
(`create_sdk_mcp_server`). This is the SDK's custom-tool surface, not the rejected external
MCP-configuration surface (spec 10) - the distinction is stated here because a reader will
reasonably ask."""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: the demo is manual and keyed; not running.")
        return 0
    from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, tool,
                                  create_sdk_mcp_server)
    from retinue.boundary.hook import SEND_TOOL, SEND_TOOLS, pre_tool_use
    from retinue.orchestration.topology import AGENTS, SPAWN_TOOLS

    captured: list[dict] = []
    offered: list[str] = []

    @tool(SEND_TOOL, "Send the approved outbound message.", {"body": str})
    async def send_message(args):
        # The chokepoint's first agent caller: the live path still goes through attempt_send.
        return {"content": [{"type": "text", "text": "queued for the chokepoint driver"}]}

    server = create_sdk_mcp_server(name="retinue", tools=[send_message])

    async def recording_hook(input_data, tool_use_id, context):
        captured.append({"meta": {"captured": {"sdk": "0.2.130", "cli": "2.1.222"}},
                         "payload": input_data})
        return await pre_tool_use(input_data, tool_use_id, context)

    options = ClaudeAgentOptions(
        agents=AGENTS, allowed_tools=list(SPAWN_TOOLS), permission_mode="default",
        mcp_servers={"retinue": server},
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[recording_hook])]})

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Use the conversation agent to send inv-demo a one-line follow-up.")
        async for message in client.receive_response():
            init_tools = getattr(message, "tools", None)
            if init_tools:
                offered.extend(init_tools)

    if not (set(offered) & set(SEND_TOOLS)):
        print("ABORT: the send tool was never OFFERED in system:init - nothing here demonstrates "
              "gating, and this demo refuses to pretend otherwise.", file=sys.stderr)
        return 1
    asks = [c for c in captured
            if c["payload"].get("tool_name") in SEND_TOOLS]
    if asks:
        Path("fixtures/payloads/captured_ask.json").write_text(
            json.dumps(asks[0], indent=1), encoding="utf-8")
        print("captured the ask fixture")
    print(f"offer asserted; {len(captured)} payloads captured")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

(Adaptation points, named: the `tool` decorator's schema argument, the `mcp_servers` kwarg, and
where system:init tools appear on the message object - all at 0.2.130; the demo run itself is
the witness, and any mismatch is fixed in the SCRIPT, never by weakening the offer assertion.)

- [ ] **Step 3: Run the default suite** - Expected: green with the ask-replay test SKIPPED
  (reason printed). Verify `grep -r "demo" tests/` shows only the skip-gated replay test.
- [ ] **Step 4: Commit**

```bash
git add scripts/demo.py tests/boundary/test_ask_replay.py
git commit -m "feat: the P4 demo - offer asserted before any gating claim, ask fixture capture + skip-gated replay"
```

---

### Task 24: README completion and the final battery

**Files:**
- Modify: `README.md`
- Test: `tools/battery.sh` (exit 0)

- [ ] **Step 1: Update `README.md`**: flip every Designed-vs-Built row whose task landed to
  **Built** with its file path (the flip happens in the same commit as this task because the
  README seed in Task 11 predates Phases 2-4; from here on, every future flip rides its feature's
  own commit). Rows that stay Designed, verbatim from the spec: per-investor sliding-window
  contact limit; store unification (Designed note only); the weights-update sketch. Document the
  three lanes (`pytest -q` · `RETINUE_PG_DSN`/`RETINUE_PG_REQUIRED=1` · `RETINUE_LIVE=1` with the
  three capture scripts: smoke, judge, demo) and the fixture-provenance statement (spec 7.2,
  both halves: hand-authored, so every number is a protocol demonstration, not a measured claim
  about model behaviour).

- [ ] **Step 2: Run the battery** - `bash tools/battery.sh` - Expected: exit 0, every line ok
  (em dashes, adjectives, removed kwarg, stale ids, token list if present locally, audit, full
  suite). Then the fingerprint pass once more over everything committed since Task 10's: every
  invented figure hand-diffed against the published ranges of the firms on the untracked list.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README - lanes, provenance statement, Designed-vs-Built flips through P4"
```


---

## Self-Review (performed at write time, full plan)

**Spec coverage:** 2.1 default lane -> Tasks 1-3, 5-9, 12-22 (all offline); 2.2 Postgres lane
incl. named-index plan test + negative control -> Task 4, outcomes table -> Task 12, durable
queue table -> Task 18; 2.3 capture runs -> Tasks 10 (smoke), 15 (judge), 23 (demo/ask);
3 topology, parity, tier vocabulary, decision table -> Tasks 7-8 (+ 17/22 parity completions);
4.1/4.4 -> Tasks 5-6; 4.2 -> Task 17; 4.3 composition -> Task 22; 5.1 -> Tasks 1, 12;
5.2 six-field feed + tri-state + boundary pre-check -> Tasks 2, 20; 5.3 block -> Task 3;
5.4 matching + ranking metrics + cold start -> Tasks 13-14; 6 chokepoint ordering, handoff
completeness (imported), pre-flight, two-signal, why-two-stores (README) -> Tasks 18-21;
6.1/6.2 import surface + AST audit -> Task 9 (prefix rule covers every gates/audit submodule);
7 separate calibration/discrimination -> Task 15; 7.1 block-stripped control -> Task 16;
7.2 provenance statement -> Tasks 10 (meta contract), 24 (README); 8 failure taxonomy rows ->
missing_source T5/T6, retryable T6, CheckerUnavailable-fail-closed T19/T20, ask T8/T23,
UNVERIFIABLE-escalates T20, projection-unavailable T20, hook-fails-open noted in T8's module
docstring context (platform contract; the chokepoint behind it is T20); 9 phase boundaries ->
the four phase headers; 12 Designed-vs-Built flips -> Tasks 11, 24.
**Deliberately not in this plan (spec says Designed/absent):** sliding-window contact limit,
store unification, weights-update sketch beyond the config parameter it reads, cold memory tier,
embedding pipeline.
**Placeholders:** none - every step carries real code, real fixture content, or an exact command.
**Type consistency:** `Touchpoint`/`TouchpointStore` (T1) consumed by T2/T4/T12/T13/T20 under the
same names; `RelationshipRecord` (T2) by T3/T16/T17/T22; `build_research_agent(model, *, doc_ids)`
(T6); `SEND_TOOL`/`SEND_TOOLS` single home (T8) imported by T17/T20/T21/T22/T23;
`DurableQueues.put(name, handoff)` duck-matches the only method `guarded_call` calls on
`queues=`; `build_checker(transport)` (T19) consumed by T20/T21/T22 tests;
`attempt_send(...) -> GatewayResult | None` with `None` = boundary pre-check denial;
`as_policy_record` (T17) available to P3/P4 callers; TIERS values validated against the imported
`MODEL_STRENGTH` in T7's test, and `CHECKER_TIER`/`TIERS["drafting"]` feed the imported
construction assert in T19.
**Known adaptation points, named not hidden:** chaperone `ActContext` kwargs (T2), pydantic-ai
terminal-exception wrapping (T6), SDK kwarg casing (T7), the captured payload's real
agent-identity key (T8/T10), pydantic-evals mapping-return surface (T14), pydantic accepting the
`Draft` dataclass as a model field (T22), the SDK tool decorator/`mcp_servers`/system:init shapes
(T23) - each marked "the RED run names it; fix the call/script, never the design."

**Fable 5 round (2026-08-10) applied in full:** engine outage semantics corrected (a chokepoint
or pre-flight `CheckerUnavailable` is a routed denial carrying `outage`, never a raise - Tasks
20/21 and the spec's section 8 row); the pre-flight structural test made safe against its own
docstring; Task 4's trigger test commits its seed row; the cold-start case ages its rival past
the 0.6/0.4 crossover; `pythonpath` gains the repo root; the battery rebuilt (octal em-dash
pattern, tracked-file scope, filename-prefix summing, removed-kwarg and stale-id gates, binary
exclusion); the spec's rejected-alternatives item narrowed to external MCP configuration; the CI
negative-control job added to Task 11; the queue name unified on the imported `human-review`;
money tolerance in Task 2; inertness steps added to Tasks 2, 4, 6, 8, 12, 17, 19, 21, 22; the
audit's send-tool rule rebuilt on AST constant equality with planted-violation tests; the warm
gold case gained its consumer and both eval mandates anchor to the gold's own cell; a
concurrent-append test joined the DSN lane; the flag-for-review fixture row gained its transport
test; fingerprint hand-check gates added at Tasks 10 and 24.
