"""The research specialist's contract. The prompt and validate_brief are a COUPLED PAIR:
the prompt names the document-id convention the validator checks. Edit them together."""
from __future__ import annotations
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
    """Containment, not equality: live models emit qualified citations ('doc-3 (filing, p.4)')."""
    hits = [d for d in doc_ids if d in source]
    return max(hits, key=len) if hits else None

def validate_brief(brief: ResearchBrief, doc_ids: frozenset[str]) -> None:
    for c in brief.claims:
        if not c.source.strip():
            raise MalformedCitation(c.claim, c.source)
        if resolve_source(c.source, doc_ids) is None:
            raise MissingSource(c.claim, c.source)

RESEARCH_PROMPT = (
    "You research investors from the provided fixture documents only.\n"
    "Every claim MUST cite its source containing the exact document id (e.g. 'doc-3 (filing, p.4)')\n"
    "and carry the document's date. If no document supports a fact, refuse that claim entirely -\n"
    "never guess, never write a claim without a resolvable document id. If an entity is ambiguous,\n"
    "set needs_identifier and list the candidates instead of choosing. When two documents report\n"
    "different values for the same quantity, give both claims the same quantity_key and keep\n"
    "both: annotate the conflict, never average it away and never pick a winner."
)
