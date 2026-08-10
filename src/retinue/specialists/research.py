"""The research specialist's contract. The prompt and this module are a COUPLED PAIR, stated at
both definition sites because a test can hold only half of it: the prompt must NAME every
convention the contract enforces - document id, source_date, quantity_key, needs_identifier -
and dropping one reddens. Only document-id resolution is machine-checked, by validate_brief;
source_date is enforced at Claim construction, and quantity_key and needs_identifier are
contract shape that nothing but the prompt asks the model to fill. Edit them together."""
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
