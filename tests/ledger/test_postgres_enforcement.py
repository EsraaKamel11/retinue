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
        plan = "\n".join(r[0] for r in cur.fetchall())   # rows come off the cursor: a Connection has no fetchall
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
