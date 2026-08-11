"""Hand-rolled ranking evaluators: FLOATS carrying explicit names, never booleans.

MRR here is the RECIPROCAL RANK - 1, 1/2, 1/3 - and never a binary. The two definitions agree at
both ends: a judged top at rank 1 scores 1.0 either way, and one that is absent scores 0.0 either
way. They part only in the middle, so an MRR that quietly became "did it appear at all" survives
every probe except a rank-2 one, and reports an unchanged headline number while the ordering it
claims to measure has stopped being measured. `tests/evals/test_ranking.py` probes rank 2 and 3 for
that reason, and the gold case whose judged top trails its cell catches the same drift on real
rows.

Both evaluators name their own metric rather than returning a bare score. Two hit@N evaluators
differ in nothing but that name once their results are in a report, and a scalar with no name is a
number a reader cannot attribute.

Lineage (spec 5.4): both metrics come from this project's own ranking analysis. They are not the
course corpus's metric family, which is a Brier score sliced by cell.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Sequence
from chaperone.matching.filters import Candidate, Mandate
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from retinue.ledger.store import TouchpointStore
from retinue.matching.integrate import shortlist

@dataclass
class HitAtN(Evaluator):
    """Whether the judged top is among the first `n` results: 1.0 or 0.0, never True or False.

    `n` is in the metric's name and not only in the evaluator's arguments. A report row reading
    `hit: 0.5` says nothing about the window it was measured over, and two windows averaged under
    one name are a figure with no meaning at all.
    """
    n: int

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        window = list(ctx.output)[: self.n]
        return {f"hit_at_{self.n}": 1.0 if ctx.expected_output in window else 0.0}

@dataclass
class MRR(Evaluator):
    """The reciprocal rank of the judged top: 1.0 at rank 1, 0.5 at rank 2, one third at rank 3.

    Absent scores 0.0, which is the one value it shares with a binary and the reason the membership
    check is written as its own early return: a shortlist the candidate never reached is a distinct
    outcome from one they reached late, and `index` would raise rather than say so.
    """

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, float]:
        ranked = list(ctx.output)
        if ctx.expected_output not in ranked:
            return {"mrr": 0.0}
        return {"mrr": 1.0 / (ranked.index(ctx.expected_output) + 1)}

def ranked_ids(rows: Sequence[dict], mandate: Mandate, embed_score: Callable[[Candidate], float],
               store: TouchpointStore, now: datetime) -> list[str]:
    """The shortlist's ids, in the order the imported ranker put them.

    The second bucket is dropped, and dropping it is the point rather than a convenience. A
    needs-verification candidate is blocked and routed - not ranked low, not a result - so appending
    that bucket would score parties the system has refused to surface, and a metric that counts them
    rewards exactly the ordering the eligibility layer exists to refuse.

    Nothing is caught here either. `shortlist` raises `StoreUnavailable` when a projection cannot be
    read, and an evaluator that swallowed it would score a shortlist built from a ledger nobody
    could query, reporting a number where there is no answer.
    """
    ranked, _needs_verification = shortlist(rows, mandate, embed_score=embed_score,
                                            store=store, now=now)
    return [c.id for c in ranked]
