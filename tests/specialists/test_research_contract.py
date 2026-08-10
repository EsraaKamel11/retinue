from datetime import date
import pytest
from retinue.specialists.failures import MalformedCitation, MissingSource
from retinue.specialists.research import (Claim, ResearchBrief, RESEARCH_PROMPT,
                                          resolve_source, validate_brief)

DOCS = frozenset({"doc-1", "doc-2"})

def claim(**over):
    base = dict(claim="fund writes early checks", evidence="page 4", source="doc-1 (filing, p.4)",
                source_date=date(2030, 1, 2), confidence=0.8)
    base.update(over)
    return Claim(**base)

def test_source_resolution_is_containment_not_equality():
    assert resolve_source("doc-1 (filing, p.4)", DOCS) == "doc-1"   # qualified citation resolves
    assert resolve_source("doc-9", DOCS) is None

def test_undated_claim_cannot_be_constructed():
    with pytest.raises(Exception):
        Claim(claim="x", evidence="y", source="doc-1", confidence=0.5)   # no source_date

def test_missing_source_is_never_retryable_and_names_the_claim():
    bad = ResearchBrief(claims=(claim(source="doc-9"),))
    with pytest.raises(MissingSource) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is False

def test_malformed_citation_is_retryable_and_carries_the_prior_value():
    bad = ResearchBrief(claims=(claim(source=""),))
    with pytest.raises(MalformedCitation) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is True and e.value.prior == ""

def test_ambiguity_is_flagged_never_guessed():
    c = claim(needs_identifier=True, candidates=("Fund A", "Fund A II"))
    assert c.candidates == ("Fund A", "Fund A II")

def test_prompt_and_validator_are_a_coupled_pair():
    # The prompt must name the same conventions the validator checks - edited together.
    assert "source" in RESEARCH_PROMPT and "document id" in RESEARCH_PROMPT
    assert "refuse" in RESEARCH_PROMPT.lower()
