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
        with pytest.raises(psycopg.errors.RaiseException):
            c.execute("TRUNCATE touchpoints")
        c.rollback()

def _seed_and_explain(c, investor: str, per_investor: int, spread: int, *, no_bitmap: bool = False):
    """Seed, ANALYZE, and EXPLAIN the adapter's OWN query text for one investor.

    Imported rather than retyped: a gate that explains a query nobody issues measures a
    hypothetical read path, and the production query could regress to a Seq Scan with the gate
    still green.

    ANALYZE before EXPLAIN, always, and AFTER the seed rather than before it. Without it the
    planner reads stale statistics and the plan under test is a plan for a table that no longer
    exists. It is also what carries SELECTIVITY into the estimate, which is the property both tests
    below actually turn on: `spread` is not a detail of the fixture, it is the experiment.

    The tag carries both numbers because both callers vary them. Keying on `spread` alone collided:
    two callers at the same spread wrote overlapping keys, `ON CONFLICT DO NOTHING` swallowed the
    overlap, and the second seed would have been quietly partial.
    """
    c.execute("""INSERT INTO touchpoints (idempotency_key, investor_id, kind, payload, occurred_at, recorded_at)
                 SELECT %(tag)s||g, 'inv-'||(g %% %(spread)s), 'contact', '{}',
                        now() - (g||' hours')::interval, now()
                 FROM generate_series(1, %(rows)s) g ON CONFLICT DO NOTHING""",
              {"tag": f"seed-{spread}x{per_investor}-", "spread": spread,
               "rows": per_investor * spread})
    c.commit()
    c.execute("ANALYZE touchpoints")
    from retinue.ledger.postgres import SELECT_FOR_INVESTOR
    if no_bitmap:
        c.execute("SET LOCAL enable_bitmapscan = off")
    cur = c.execute("EXPLAIN (FORMAT TEXT) " + SELECT_FOR_INVESTOR, (investor,))
    return "\n".join(r[0] for r in cur.fetchall())   # rows come off the cursor: a Connection has no fetchall

def test_projection_query_uses_the_named_index_not_a_seq_scan():
    """The index is reached. Two assertions, and deliberately not a third.

    This test carried a third clause, `"Sort" not in plan`, until the lane's FIRST EVER execution
    (CI run 31615144104, postgres:16.4) reddened it while both assertions above passed. The plan
    was:

        Sort (Sort Key: seq)
          -> Bitmap Heap Scan on touchpoints
             -> Bitmap Index Scan on idx_touchpoints_investor_seq (Index Cond: investor_id = ...)

    The named index was used and there was no Seq Scan, so what this test's NAME claims held. The
    seeding spread 5000 rows over 200 investors, about 25 each, and at that size the planner
    prefers a bitmap scan and re-sorts. That is a planner choice at toy scale, not a broken index.

    The third clause is now its own test below, at its own size, because a test that reddens for a
    reason outside its name is the defect this repository is about. Splitting is not weakening: the
    free-ordering property is asserted more strictly there than it was here.
    """
    with _conn() as c:
        plan = _seed_and_explain(c, "inv-7", per_investor=25, spread=200)
        assert "idx_touchpoints_investor_seq" in plan, f"planner chose a different path:\n{plan}"
        assert "Seq Scan" not in plan, f"seq scan accepted would make this gate vacuous:\n{plan}"

def test_the_projection_ordering_rides_the_index_rather_than_a_sort():
    """WHY the index is `(investor_id, seq)` and not `(investor_id)`: the ORDER BY is free.

    A Bitmap Index Scan uses the index and then re-sorts, which satisfies the test above while
    delivering none of the reason for the composite. So this asserts the absence of a Sort, and it
    has to make the planner's choice deterministic before it can.

    SECOND DATED FINDING, CI run 31668067816 at a065dac, and it is the more instructive of the two.
    The split shipped and the renamed test above passed against the very plan it had failed on, but
    this test failed its own first contact:

        Sort (Sort Key: seq)
          -> Seq Scan on touchpoints (Filter: investor_id = 'inv-0', rows=2025)

    The seed had put all 2000 rows under ONE investor and then queried that investor, so the filter
    selected the entire table. At 100 percent selectivity no index scan can beat a sequential scan
    plus a sort, and `enable_bitmapscan = off` does not forbid a Seq Scan, so the pin could not save
    it either. The seed had defeated the test's own thesis: the composite index's order-for-free
    story EXISTS ONLY UNDER A SELECTIVE PREDICATE, and a predicate matching everything is not one.

    That is the same error as the first finding, inverted. The original test grew the table without
    growing the rows per investor; this one grew the rows per investor until they were the whole
    table. Both times the seed, not the schema, decided the plan.

    So selectivity is now the experiment rather than a side effect: 200 investors at 50 rows each,
    one of them queried, which is half a percent of the table. `enable_bitmapscan = off` stays,
    SET LOCAL and scoped to this transaction, as a disclosed belt-and-braces pin against a planner
    version that would otherwise prefer a bitmap path and re-sort. `enable_seqscan` is deliberately
    NOT pinned: turning every alternative off would measure the pins rather than the index, and a
    Seq Scan appearing here again is information this test should be able to report.

    What this cannot claim: that the ordered scan wins at every table size or every selectivity. It
    wins here, at this size, at this selectivity, on this planner. That is the honest scope of an
    EXPLAIN assertion, and both findings above are what taught it.
    """
    with _conn() as c:
        plan = _seed_and_explain(c, "inv-0", per_investor=50, spread=200, no_bitmap=True)
        assert "idx_touchpoints_investor_seq" in plan, f"planner chose a different path:\n{plan}"
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
