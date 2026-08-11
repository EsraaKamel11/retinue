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
    # Which jurisdiction wins decides MEMBERSHIP, so the precedence is not a detail. Reverse it and
    # a stale roster row readmits a party the ledger places outside consent.
    #
    # Kept deliberately even though every mutation that reddens it also reddens the empty-value
    # test below, so the question is not re-derived: subsumption was measured over mutations to ONE
    # expression, and the two tests differ in which EDITS they survive rather than only in which
    # mutations they catch. Normalize `""` to `None` inside project_record - a plausible cleanup
    # one layer down, and one the test below would correctly redden - and that test becomes wrong
    # and gets rewritten or deleted. At that moment the primary rule, that a jurisdiction the
    # ledger actually records beats the roster row, would have NO guard at all. This one survives
    # that edit untouched. Retiring it would trade a durable guard for a transient one.
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="inv-1-i", investor_id="inv-1", mandate_id="m-1",
                            kind="identity", payload={"jurisdiction": "RU"},
                            occurred_at=NOW - timedelta(days=5), recorded_at=NOW))
    assert candidate_for(row(), store, now=NOW).jurisdiction == "RU"   # resolved, not merely gone
    ranked, needs = shortlist([row()], MANDATE, embed_score=lambda c: 1.0, store=store, now=NOW)
    assert (ranked, needs) == ([], [])

def test_an_empty_ledger_jurisdiction_is_a_fact_not_an_absence():
    # `None` and `""` are different facts, and only one of them is an absence. No identity
    # touchpoint means the ledger holds no opinion, and the roster row standing in is reasonable.
    # An identity touchpoint recording an EMPTY jurisdiction means a record exists and names no
    # consent. Under `or` the two collapse, the roster row's consented value wins, and a malformed
    # identity record is readmitted by the less trustworthy of the two sources - the permissive
    # direction, reached by DATA rather than by an edit to the precedence.
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="inv-1-i", investor_id="inv-1", mandate_id="m-1",
                            kind="identity", payload={"jurisdiction": ""},
                            occurred_at=NOW - timedelta(days=5), recorded_at=NOW))
    assert candidate_for(row(juris="US"), store, now=NOW).jurisdiction == ""  # the ledger's fact
    ranked, needs = shortlist([row(juris="US")], MANDATE, embed_score=lambda c: 1.0,
                              store=store, now=NOW)
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

def test_one_unreadable_party_fails_the_whole_shortlist():
    # The doctrine is pinned at candidate_for, and shortlist is what the rest of the system calls.
    # Nothing else holds shortlist to it: wrap the loop in `try/except StoreUnavailable: continue`,
    # the change someone makes in the name of resilience, and every other test here stays green
    # while a party vanishes from a shortlist that still looks complete. The MIXED list is the
    # point - one readable row and one unreadable - because the swallowing form then returns an
    # ordinary-looking (['inv-ok'], []) rather than an empty result anyone would question. That is
    # projection.py's forbidden collapse transposed up a layer: absent-because-not-a-match and
    # absent-because-the-query-failed must not arrive as the same answer.
    class HalfBroken:
        def __init__(self): self._ok = InMemoryStore()
        def touchpoints_for(self, i):
            if i == "inv-down": raise StoreUnavailable("down")
            return self._ok.touchpoints_for(i)
        def append(self, t): raise AssertionError
    with pytest.raises(StoreUnavailable, match="never invents"):
        shortlist([row("inv-ok"), row("inv-down")], MANDATE,
                  embed_score=lambda c: 1.0, store=HalfBroken(), now=NOW)
