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

def test_a_fabricated_id_that_extends_a_real_one_does_not_resolve():
    # Bare containment matched "doc-12" against "doc-1", so an invented document validated and
    # the escalation this contract exists to force never fired. This is the boundary's whole job.
    assert resolve_source("doc-12 (filing, p.4)", DOCS) is None
    assert resolve_source("doc-1000", DOCS) is None

def test_resolution_is_deterministic_and_prefers_the_id_actually_cited():
    # frozenset order is hash-seed dependent, so a resolver picking arbitrarily among matches
    # answers differently between runs. Earliest position wins: the id inside the qualifier is
    # not the one being cited.
    assert resolve_source("doc-1 and doc-2 agree", DOCS) == "doc-1"
    assert resolve_source("doc-1 (doc-2, p.4)", DOCS) == "doc-1"

def test_undated_claim_cannot_be_constructed():
    with pytest.raises(Exception):
        Claim(claim="x", evidence="y", source="doc-1", confidence=0.5)   # no source_date

def test_missing_source_is_never_retryable_and_names_the_claim():
    bad = ResearchBrief(claims=(claim(source="doc-9"),))
    with pytest.raises(MissingSource) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is False
    assert e.value.claim == "fund writes early checks"   # the test's name promises this

def test_malformed_citation_is_retryable_and_carries_the_prior_value():
    bad = ResearchBrief(claims=(claim(source=""),))
    with pytest.raises(MalformedCitation) as e:
        validate_brief(bad, DOCS)
    assert e.value.retryable is True and e.value.prior == ""

def test_ambiguity_is_flagged_never_guessed():
    c = claim(needs_identifier=True, candidates=("Fund A", "Fund A II"))
    assert c.candidates == ("Fund A", "Fund A II")

def test_prompt_names_every_convention_the_contract_enforces():
    # The prompt and the validator are a coupled pair, and this is the half a test can hold:
    # every convention the contract enforces must be NAMED in the prompt, so a rewrite that
    # drops one reddens. It cannot pin the prose's meaning - a prompt rewritten to say the
    # opposite would still pass - which is why the pairing is stated at both definition sites.
    for convention in ("document id",        # resolve_source
                       "source_date",        # mandatory; NOT the bare word "date", which the
                                             # word "candidates" supplies for free - that arm
                                             # could not redden and so enforced nothing
                       "quantity_key",       # the grouping key that lets a conflict be held
                       "needs_identifier"):  # ambiguity flagged, never guessed
        assert convention in RESEARCH_PROMPT, f"prompt never names {convention}"
    assert "refuse" in RESEARCH_PROMPT.lower()
