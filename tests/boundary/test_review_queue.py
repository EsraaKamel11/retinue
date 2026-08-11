"""The DURABLE half of escalation, and the ORDER the two halves are written in.

The imported queues state their own limit in their own module docstring: a `ReviewQueues` that
goes out of scope takes its escalations with it, and a fresh one starts empty. That limit is why
this module exists, and the ordering test below is the whole of what "durable" buys - a crash
between the two writes must lose the rebuildable copy and never the work item.

The Postgres test skips without a DSN and FAILS under `RETINUE_PG_REQUIRED=1`, which is the same
negative control tests/ledger/conftest.py already carries: a lane that can skip forever is a
vacuous gate, so the environment that runs it for real makes vacuity a red build.
"""
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import pytest
from chaperone.gates.handoff import Handoff
from retinue.boundary.review_queue import DurableQueues, memory_sink

NOW = lambda: datetime(2030, 4, 1, tzinfo=timezone.utc)
SCHEMA = Path(__file__).resolve().parents[2] / "schema.sql"

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

def test_the_row_is_stamped_from_the_injected_clock_never_from_wall_time():
    """Without this, `datetime.now(timezone.utc)` in place of the injected clock passes every
    other test in this file, and the repository's one rule about time has no arm anywhere."""
    sink, rows = memory_sink()
    DurableQueues(sink, now=NOW).put("human-review", handoff())
    assert rows[0][2] == datetime(2030, 4, 1, tzinfo=timezone.utc)

def test_the_row_carries_the_handoff_as_json_encodable_data():
    """The sink is handed `model_dump()` and not the model, and the column it lands in is JSONB.

    Handing the `Handoff` across instead passes every other test in this file and fails only
    inside `Jsonb(...)`, in the lane that has never run. So the encodability is asserted here,
    where it costs nothing, rather than discovered there.
    """
    sink, rows = memory_sink()
    DurableQueues(sink, now=NOW).put("human-review", handoff())
    payload = rows[0][1]
    assert isinstance(payload, dict)
    assert json.loads(json.dumps(payload)) == payload
    assert payload["blocked_body"] == "The round is $9M."     # the reviewer's whole work item

def test_the_insert_columns_and_the_schema_are_one_fact_in_two_spellings():
    """Double entry, the same shape the outcome signals already use against this file.

    The only test that runs the INSERT needs a database, so a column renamed on one side of the
    pair would otherwise surface first in a lane that has never executed. Both directions are
    held: a name the INSERT writes and the table does not declare, and a NOT NULL column the
    table declares and the INSERT never fills. `id` is GENERATED ALWAYS, which REJECTS an
    explicit value, so it is excluded here rather than merely absent by luck.

    Two CONTAINMENTS and not an equality, which is a correction rather than a preference: see the
    comment at the assertions themselves.
    """
    from retinue.boundary.review_queue import INSERT_REVIEW_ROW
    written = re.search(r"INSERT INTO review_queue \(([^)]*)\) VALUES \(([^)]*)\)",
                        INSERT_REVIEW_ROW)
    assert written, f"the INSERT no longer parses, so this gate reads nothing:\n{INSERT_REVIEW_ROW}"
    columns = [c.strip() for c in written.group(1).split(",")]
    assert columns, "no columns parsed out of the INSERT"
    assert len(written.group(2).split(",")) == len(columns), "placeholders do not match columns"

    block = re.search(r"CREATE TABLE IF NOT EXISTS review_queue \((.*?)\n\);",
                      SCHEMA.read_text(encoding="utf-8"), re.DOTALL)
    assert block, "no review_queue table in schema.sql, so this gate reads nothing"
    declared = {m.group(1): m.group(0)
                for m in re.finditer(r"^\s*(\w+)\s+[A-Z].*$", block.group(1), re.MULTILINE)}
    assert declared, "no columns parsed out of the table"
    required = {n for n, line in declared.items()
                if "NOT NULL" in line and "GENERATED" not in line}
    generated = {n for n, line in declared.items() if "GENERATED" in line}
    assert required and generated, "the two column classes this gate reads are both empty"
    # An equality here would be STRICTER THAN CORRECTNESS: it forbids the INSERT from ever naming
    # a nullable column, and `resolved_at` is declared in this same table precisely so that a
    # later task can write it. The first task to do that correctly would redden this test on
    # correct SQL, and the repair in that moment is to weaken an assertion, which is exactly the
    # moment a weakened check gets waved through. So the two containments that are actually true.
    assert set(columns) >= required, (
        f"INSERT writes {sorted(columns)} and the table requires {sorted(required)}")
    assert set(columns) <= set(declared) - generated, (
        f"INSERT writes {sorted(columns)}; the table declares {sorted(declared)} "
        f"of which {sorted(generated)} REJECT an explicit value")

MINE = ("FROM review_queue WHERE queue_name='human-review' AND enqueued_at = %s")

def test_postgres_sink_persists_a_row():
    """Reads back the row it wrote, rather than counting rows anyone wrote.

    A bare `count(*) >= 1` over the queue name is satisfied by a row an EARLIER run left behind,
    and that matters more here than it would anywhere else in this repository: this is the only
    test in the tree that can ever execute `postgres_sink`'s body, so against a reused database it
    would pass with that body emptied or its parameters mis-bound. The injected clock is what
    makes the narrower question askable, since a fixed `NOW` gives the row a signature.

    The before-and-after count is the half that a signature alone does not buy. An earlier run of
    THIS test wrote a row with THIS timestamp, so identifying by signature still finds one when
    the current run wrote nothing. A strict increase is the structural witness that this run's own
    call reached the database, and it holds on a fresh database and a reused one alike. Nothing
    here is timed: the witness is a count, not a duration.

    Re-running is safe. A second run writes a second identical row, so the count still increases
    by one and the read-back still matches, and the table is never cleaned up by this test.
    """
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped")
    import psycopg
    from retinue.ledger.postgres import bootstrap
    from retinue.boundary.review_queue import postgres_sink
    bootstrap(dsn)
    with psycopg.connect(dsn) as c:
        before = c.execute("SELECT count(*) " + MINE, (NOW(),)).fetchone()[0]
    q = DurableQueues(postgres_sink(dsn), now=NOW)
    q.put("human-review", handoff())
    with psycopg.connect(dsn) as c:
        after = c.execute("SELECT count(*) " + MINE, (NOW(),)).fetchone()[0]
        row = c.execute("SELECT handoff, enqueued_at " + MINE, (NOW(),)).fetchone()
    assert after == before + 1, f"this run's own write did not reach the table ({before} -> {after})"
    assert row is not None, "the sink wrote no row this test can identify as its own"
    stored, at = row
    # JSONB comes back through psycopg's `JsonbLoader`, which is `json.loads`, so `stored` is a
    # parsed dict and not text. Dict equality ignores key order, which JSONB does not preserve.
    assert stored == handoff().model_dump()
    # Aware datetimes compare as instants, so a session timezone other than UTC still matches.
    assert at == NOW()
