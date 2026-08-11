"""The ranking metrics, and the two judged cases they are pointed at.

The first three tests are the definitions themselves, held over a hand-written list rather than a
shortlist: a metric's arithmetic should not move when a fixture does, and these keep discriminating
whatever `fixtures/gold_rankings.json` later says. The rest read that fixture, and read all of it -
the mandate, the roster it is judged over and the judged top are fixture fields, so no test here
builds the question out of the answer it expects.
"""
import json
import pathlib
from datetime import datetime, timedelta, timezone
import pytest
from chaperone.matching.filters import Mandate
from pydantic_evals.evaluators import EvaluatorContext
from retinue.evals.ranking import MRR, HitAtN, ranked_ids
from retinue.ledger.models import StoreUnavailable, Touchpoint
from retinue.ledger.store import InMemoryStore
from retinue.matching.integrate import shortlist
from retinue.synth.rosters import generate_rosters

GOLD = json.loads((pathlib.Path(__file__).resolve().parents[2] / "fixtures"
                   / "gold_rankings.json").read_text(encoding="utf-8"))
NOW = datetime(2030, 3, 1, tzinfo=timezone.utc)

class Ctx:
    """Duck-typed stand-in: the evaluators read exactly these two attributes."""
    def __init__(self, output, expected):
        self.output, self.expected_output = output, expected

def gold_case(name: str) -> dict:
    return next(c for c in GOLD["cases"] if c["name"] == name)

def case_inputs(case: dict) -> tuple[list[dict], Mandate]:
    """A judged case's roster and its mandate, both read off the fixture and neither inferred."""
    m = case["mandate"]
    return (list(generate_rosters(case["seed"], case["n"])),
            Mandate(check_size_min=m["check_size_min"], stage=m["stage"], sector=m["sector"],
                    geography=m["geography"],
                    consented_jurisdictions=frozenset(m["consented_jurisdictions"])))

def test_mrr_is_the_reciprocal_rank_never_a_binary():
    """The drift this module exists to prevent: an MRR that answers "did it appear at all".

    Rank 1 and absent are the two places the correct definition and the broken one AGREE - 1.0 and
    0.0 under both - so a test built from those two alone goes green over a binary. The middle is
    where they part, which is what the second and third probes are for.
    """
    ranked = ["a", "b", "c", "d"]
    assert MRR().evaluate(Ctx(ranked, "a")) == {"mrr": 1.0}
    assert MRR().evaluate(Ctx(ranked, "b")) == {"mrr": 0.5}       # neither 0.0 nor 1.0
    assert MRR().evaluate(Ctx(ranked, "c")) == {"mrr": 1.0 / 3}
    assert MRR().evaluate(Ctx(ranked, "zz")) == {"mrr": 0.0}

def test_hit_at_n_is_a_float_with_an_explicit_name():
    """1.0 and 0.0, never True and False, under a name that says which N was measured.

    The `isinstance` calls are the assertions doing the work, not decoration: `1.0 == True` and
    `0.0 == False` in Python, so the dict comparisons alone are satisfied by an evaluator returning
    booleans, and a report cannot average an assertion. The window boundary is probed from both
    sides - "c" is the third result and inside it, "d" is the fourth and outside.
    """
    hit = HitAtN(3).evaluate(Ctx(["a", "b", "c", "d"], "c"))
    assert hit == {"hit_at_3": 1.0} and isinstance(hit["hit_at_3"], float)
    miss = HitAtN(3).evaluate(Ctx(["a", "b", "c", "d"], "d"))
    assert miss == {"hit_at_3": 0.0} and isinstance(miss["hit_at_3"], float)

def test_the_evaluators_run_against_the_real_evaluator_context():
    """`Ctx` above is a stand-in, and a stand-in that agrees with nothing is how a green suite comes
    to sit on evaluators the real harness cannot drive: rename either attribute in pydantic-evals
    and every duck-typed test here stays green while both evaluators raise on the first real
    context. So the pinned harness type is built once, here, and driven through both metrics - a
    renamed field lands as a TypeError in this constructor instead of in production.

    Rank 2 again, and deliberately: the one probe that tells a reciprocal rank from a binary is
    worth having on the real type as well as the stand-in. `_span_tree` is required by the
    dataclass and read by neither evaluator, which is what `None` says here.
    """
    ctx = EvaluatorContext(name="rank-2", inputs=None, metadata=None, expected_output="b",
                           output=["a", "b", "c"], duration=0.0, _span_tree=None,
                           attributes={}, metrics={})
    assert MRR().evaluate(ctx) == {"mrr": 0.5}
    assert HitAtN(3).evaluate(ctx) == {"hit_at_3": 1.0}
    assert HitAtN(1).evaluate(ctx) == {"hit_at_1": 0.0}

def test_each_gold_case_names_a_cell_the_ranking_can_actually_reorder():
    """A gold over a one-candidate shortlist is a tautology, and this fixture began as one.

    On `generate_rosters(7, 8)` every (sector, stage, geography) cell holds a single row, so any
    mandate admits exactly one candidate: both cases below would have reported a perfect metric
    against a ranker that did nothing whatever, and the cold-start case could not have fallen at
    all. This pins what regenerating the fixture bought - a cell with rivals in it, and a judged top
    that does not already start at the head of it.

    Membership is compared as a SET: with the embedder null and the ledger empty every eligible
    candidate scores exactly 0.0, so the order here is Python's stable sort preserving roster order
    rather than anything the ranker decided, and freezing it as order would pin the wrong fact.

    The one ordering claim is the last line, and it reads `cell[-1] ==` rather than `cell[0] !=`.
    Both cases' judgments say in prose that the gold is LAST of its cell, and not-first is a weaker
    claim that a middle member also satisfies: park a three-member cell's gold in the middle and the
    warm case below still passes, but on a rank-2 recovery rather than the rank-3 one the fixture
    claims, and the cold-start case's bound loosens from a third to a half. Asserted as the claim
    the fixture already owns, so the prose and the test cannot drift apart.
    """
    for case in GOLD["cases"]:
        rows, mandate = case_inputs(case)
        cell = ranked_ids(rows, mandate, lambda c: 0.0, InMemoryStore(), NOW)
        assert set(cell) == set(case["eligible_cell"]), case["name"]
        assert len(cell) >= 2, f"{case['name']}: a one-candidate shortlist judges nothing"
        assert cell[-1] == case["expected_top"], f"{case['name']}: the gold is not last in its cell"

def test_the_metric_notices_a_null_embedder_on_the_cold_start_case():
    """The cold-start gold expects similarity to carry a party with no history; an embedder that
    returns 0.0 for everyone must drop the metric. This is the "the metric must notice" clause.

    `bad > 0.0` and `bad < 1.0` are separate claims and both are load-bearing. The lower bound says
    the candidate is still THERE - withdrawing similarity costs them the top of the shortlist, not
    their membership of it, which is the eligibility doctrine one layer down. The upper bound is
    what a binary MRR fails: under "did it appear at all" both runs return 1.0, `good > bad` reads
    1.0 > 1.0, and this is the case that catches it on real data.

    hit@N gets its one run over real rows here, at N=2, which is the only window this cell can say
    anything with: hit@3 over three candidates is 1.0 for any gold and any ranker, and hit@1 would
    restate the two MRR lines above. It is also SHARPER than the bound above rather than a duplicate
    of it - `0.0 < bad < 1.0` admits rank 2 or rank 3, while `hit_at_2 == 0.0` pins rank 3 exactly,
    which is where the fixture's judgment puts this gold. Float-ness is not re-pinned here; the
    dedicated hit@N test owns that claim.
    """
    case = gold_case("cold-start-carried-by-similarity")
    rows, mandate = case_inputs(case)
    top = case["expected_top"]
    favouring = ranked_ids(rows, mandate, lambda c: 0.99 if c.id == top else 0.1,
                           InMemoryStore(), NOW)
    null = ranked_ids(rows, mandate, lambda c: 0.0, InMemoryStore(), NOW)
    good = MRR().evaluate(Ctx(favouring, top))["mrr"]
    bad = MRR().evaluate(Ctx(null, top))["mrr"]
    assert good == 1.0                # similarity alone puts the cold-start party at the front
    assert 0.0 < bad < 1.0            # and withdrawing it costs them order, not membership
    assert good > bad                 # the metric notices when similarity stops carrying them
    assert HitAtN(2).evaluate(Ctx(favouring, top)) == {"hit_at_2": 1.0}
    assert HitAtN(2).evaluate(Ctx(null, top)) == {"hit_at_2": 0.0}     # rank 3 exactly, not 2

def test_warm_relationship_wins_under_a_uniform_embedder():
    """The other gold's consumer: with the embedder flat, relationship state must decide.

    The judged top is last of the three in roster order, so a flat embedder over an empty ledger
    leaves it third. That counterfactual is RUN rather than asserted in prose: `cold` is the same
    call with the ledger emptied, and the pair says what one number cannot - the top spot was bought
    by the relationship term and by nothing else. Its own weights live in the imported ranker and
    are not this repository's to mutate, so the control is the second call.
    """
    case = gold_case("warm-relationship-wins")
    rows, mandate = case_inputs(case)
    top = case["expected_top"]
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="warm-c", investor_id=top, mandate_id="m-1",
                            kind="contact", payload={},
                            occurred_at=NOW - timedelta(days=20), recorded_at=NOW))
    warm = MRR().evaluate(Ctx(ranked_ids(rows, mandate, lambda c: 0.5, store, NOW), top))["mrr"]
    cold = MRR().evaluate(Ctx(ranked_ids(rows, mandate, lambda c: 0.5, InMemoryStore(), NOW),
                              top))["mrr"]
    assert warm == 1.0
    assert cold < warm      # the ledger emptied, the same flat embedder: the relationship decided

def test_ranked_ids_carries_the_ranked_bucket_and_not_the_blocked_one():
    """A needs-verification candidate is blocked and routed, never ranked low, so no metric may see
    them. Every row in both gold cases carries every axis, so that bucket is empty throughout this
    file: append it to the first and each test above stays green while the metric quietly begins
    scoring parties the eligibility layer refused to surface. This is the row that would notice.

    The blocked bucket is asserted NON-EMPTY first, and that line is the difference between a test
    and a test-shaped thing. It rests on a premise this repository does not own - that the imported
    `classify` routes a missing `stage` to needs-verification rather than to ineligible - and if
    that ever changed, the bucket would be empty, `ranked_ids` would have nothing to drop, the
    assertion below would still pass and the guard would be green and vacuous. Stating the premise
    as its own assertion means the day it stops holding is the day this reddens, rather than the day
    it silently stops measuring.
    """
    mandate = Mandate(check_size_min="100000", stage="seed", sector="devtools",
                      geography="eu-west", consented_jurisdictions=frozenset({"US"}))
    def row(inv, **overrides):
        return {"investor_id": inv, "jurisdiction": "US", "check_ceiling": 4_000_000,
                "stage": "seed", "sector": "devtools", "geography": "eu-west"} | overrides
    rows = [row("inv-ok"), row("inv-hole", stage=None)]
    _ranked, blocked = shortlist(rows, mandate, embed_score=lambda c: 0.5,
                                 store=InMemoryStore(), now=NOW)
    assert [c.id for c in blocked] == ["inv-hole"]        # the premise: there IS something to drop
    assert ranked_ids(rows, mandate, lambda c: 0.5, InMemoryStore(), NOW) == ["inv-ok"]

def test_ranked_ids_lets_an_unreadable_ledger_raise():
    """Matching never invents, and a metric laid over it inherits that. A `ranked_ids` that caught
    this would hand the evaluator an empty shortlist, which scores 0.0 - a number reported where
    there is no answer, and indistinguishable in a report from a ranker that ordered the cell badly.
    """
    class Unreadable(InMemoryStore):
        def touchpoints_for(self, investor_id):
            raise StoreUnavailable(investor_id)
    rows, mandate = case_inputs(gold_case("warm-relationship-wins"))
    with pytest.raises(StoreUnavailable):
        ranked_ids(rows, mandate, lambda c: 0.5, Unreadable(), NOW)
