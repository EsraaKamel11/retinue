"""ReviewQueues plus a durable sink. Durable half FIRST: a crash between the halves must lose the
in-process copy (rebuildable from the table), never the work item. `guarded_call` takes this object
through its `queues=` keyword, duck-typed on `.put`, which is the only method it calls.

**Why this module exists at all.** The imported `gates/queues.py` states its own limit in its own
docstring: a queue is a list in memory living as long as the object its caller holds, durable
delivery is out of scope, and a `ReviewQueues` that goes out of scope takes its escalations with
it. That module also says why losing one costs more than a copy: the audit log records THAT a
draft was redirected and carries no text, while the queue holds the blocked body, the offending
span and the cited record values. Somebody holding the log and not the queue knows a redirect
happened and cannot read what was redirected. So this is the half that survives a process, and it
is deliberately NOT a graph checkpointer: it persists the work item, not the run that produced it.

**The ordering is the whole design, and it is the cheap direction of a real trade.** Writing the
durable row first means a crash between the two writes leaves a row nobody has routed in memory,
which a restart rebuilds by reading the table. Writing the in-process copy first means a crash
leaves an escalation that one live object believes it routed and no restart can find, and the
process that would have reported the loss is the one that died. A sink that raises therefore
raises out of `put` with nothing added to the inner queue, and no `try` here softens that: an
escalation reported as routed while durability failed is the exact silence this file is against.

**No policy is decided here.** The queue name arrives from `destination_for`, in the imported
engine, and nothing in this file names one.
"""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from chaperone.gates.handoff import Handoff
from chaperone.gates.queues import ReviewQueues

Sink = Callable[[str, dict, datetime], None]

#: Hoisted for the same reason `SELECT_FOR_INVESTOR` is hoisted in ledger/postgres.py: the only
#: test that RUNS this statement needs a database, so the double-entry test reads the exact text
#: the sink issues rather than a retyped copy that could agree with schema.sql while the adapter
#: does not. `id` is omitted deliberately, not by oversight: GENERATED ALWAYS AS IDENTITY REJECTS
#: an explicit value. `resolved_at` is omitted because an enqueue is not a resolution.
INSERT_REVIEW_ROW = (
    "INSERT INTO review_queue (queue_name, handoff, enqueued_at) VALUES (%s,%s,%s)")

class DurableQueues:
    """Duck-type-compatible with `ReviewQueues` across the three methods this repository uses.

    Composition rather than inheritance, so that a method the imported class grows later cannot
    arrive here already bypassing the sink. An unwritten method is an AttributeError at the call
    site; an inherited one would be a silent hole in exactly the guarantee this class is for.
    """

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
    """A sink and the rows it wrote. The default lane's durable half, and a test's whole window
    onto what `put` handed across: the name, the encodable payload and the stamped time."""
    rows: list[tuple[str, dict, datetime]] = []
    def sink(name: str, payload: dict, at: datetime) -> None:
        rows.append((name, payload, at))
    return sink, rows

def postgres_sink(dsn: str) -> Sink:
    """Connection per write, the same shape `PostgresStore.append` already uses against this DSN.

    psycopg's connection context manager COMMITS on a clean exit and rolls back on an exception,
    so a raise here leaves no half-written row for `put` to have routed against.
    """
    def sink(name: str, payload: dict, at: datetime) -> None:
        import psycopg
        from psycopg.types.json import Jsonb
        with psycopg.connect(dsn) as c:
            c.execute(INSERT_REVIEW_ROW, (name, Jsonb(payload), at))
    return sink
