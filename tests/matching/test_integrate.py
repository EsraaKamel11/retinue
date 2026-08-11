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
    # Equality, not `"inv-bad" not in seen`. The weaker form is satisfied by an implementation that
    # never scores ANYBODY, so it would go green over a similarity step that had stopped running -
    # the vacuity shape this repo's gates exist to hunt. The equality says both halves at once: the
    # eligible candidate was scored, and the excluded one never even reached the scorer.
    assert seen == ["inv-ok"]         # never retrieval: the excluded are never even scored

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

def test_never_touched_is_absent_not_a_touch_today():
    # The other half of cold start, and the half the ranking test cannot see: `days_since_touch=0`
    # would ALSO sort inv-new first, at 0.996, so the test above stays green over a candidate_for
    # that reports a brand new investor as touched this morning. Absent is not zero - the same
    # distinction test_new_investor_projects_a_record_not_none holds one layer down.
    c = candidate_for(row("inv-new"), InMemoryStore(), now=NOW)
    assert c.days_since_touch is None

def test_ledger_identity_outranks_the_roster_row_on_jurisdiction():
    # Which jurisdiction wins decides MEMBERSHIP, so the precedence is not a detail. No other test
    # here seeds an identity touchpoint, which leaves the ledger arm of that choice unexercised:
    # reverse it and a stale roster row readmits a party the ledger places outside consent.
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="inv-1-i", investor_id="inv-1", mandate_id="m-1",
                            kind="identity", payload={"jurisdiction": "RU"},
                            occurred_at=NOW - timedelta(days=5), recorded_at=NOW))
    ranked, needs = shortlist([row()], MANDATE, embed_score=lambda c: 1.0, store=store, now=NOW)
    assert (ranked, needs) == ([], [])

def test_projection_unavailable_raises_never_invents_a_candidate():
    class Broken:
        def touchpoints_for(self, i): raise StoreUnavailable("down")
        def append(self, t): raise AssertionError
    # `match` pins WHICH mechanism refused, and it is not decoration. `candidate_for` reads the
    # store twice, so a bare `raises(StoreUnavailable)` is satisfied by the second read even when
    # the guard honouring the projection's `None` has been deleted outright - measured, not
    # supposed: replacing that guard with an invented blank record left all eight tests green.
    # The message is the doctrine the guard carries, so matching it is what tells the two apart.
    with pytest.raises(StoreUnavailable, match="never invents"):
        candidate_for(row(), Broken(), now=NOW)
