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
    """One roster row plus the ledger's answer about that investor, as a `Candidate`.

    The projection is consulted FIRST and its `None` is honoured before anything else is read.
    That ordering is the whole tri-state: `project_record` returns `None` only for a store that
    could not be read, and collapsing that into "no relationship" would hand the ranker a
    candidate whose relationship state is zero because a query failed, indistinguishable from one
    whose relationship state is zero because nobody has spoken to them yet.
    """
    rec = project_record(store, row["investor_id"])
    if rec is None:
        raise StoreUnavailable(f"projection unavailable for {row['investor_id']}; matching never invents")
    # A second read, deliberately. `RelationshipRecord` carries the LAST pass reason, not a count,
    # and `prior_passes` is a depth signal the ranker's penalty term needs. The alternatives are
    # worse: re-deriving the record's fields here would put a second copy of the projection inside
    # matching, which is the layer drift Task 12 closed. This read raises rather than degrades, so
    # a store that fails between the two calls still fails closed.
    passes = sum(1 for t in store.touchpoints_for(row["investor_id"]) if t.kind == "pass_reason")
    return Candidate(
        id=row["investor_id"],
        check_size_max=str(row["check_ceiling"]) if row.get("check_ceiling") is not None else None,
        stage=row.get("stage"), sector=row.get("sector"), geography=row.get("geography"),
        # The ledger's identity fact outranks the roster row, and only in that direction. The row
        # is roster input; the record is what this system has actually recorded about the party,
        # and jurisdiction decides membership. Reversed, a stale row would readmit someone the
        # ledger places outside consent - a hard exclusion lost to input that was never checked.
        jurisdiction=rec.jurisdiction or row.get("jurisdiction"),
        # `None`, never `0`. Zero days means touched today; absent means never touched, which is
        # the state the cold-start commitment turns on - `relationship_score` reads `None` as 0.0
        # and lets similarity carry the candidate, where a 0 would read as maximum recency.
        days_since_touch=(now - rec.last_contact).days if rec.last_contact else None,
        prior_passes=passes,
    )

def shortlist(rows: Sequence[dict], mandate: Mandate, *,
              embed_score: Callable[[Candidate], float],
              store: TouchpointStore, now: datetime):
    """Rows to `(ranked, needs_verification)`, staged by the imported ranker and nothing else.

    No ordering, no filtering and no scoring happens here: `rank` runs `classify` first and calls
    `embed_score` only from the sort key over the eligible bucket, so an excluded candidate is
    never scored at all. Reordering that here - even to "pre-score for speed" - would spend the
    similarity call on parties who are not results, and would make the exclusion a ranking penalty
    in everything but name.
    """
    candidates = [candidate_for(r, store, now=now) for r in rows]
    return rank(candidates, mandate, embed_score)
