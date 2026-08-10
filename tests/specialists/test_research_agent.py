from datetime import date
import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from retinue.specialists.failures import MissingSource
from retinue.specialists.research import ResearchEscalation, build_research_agent

DOCS = frozenset({"doc-1"})

def _brief_call(source: str):
    return ToolCallPart(tool_name="final_result", args={
        "claims": [{"claim": "writes early checks", "evidence": "p4", "source": source,
                    "source_date": "2030-01-02", "confidence": 0.8}]})

def test_valid_brief_passes_through():
    def fn(messages, info: AgentInfo):
        return ModelResponse(parts=[_brief_call("doc-1 (filing)")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    out = agent.run_sync("investor brief").output
    assert out.claims[0].source_date == date(2030, 1, 2)

def test_missing_source_escalates_with_zero_retries():
    # The whole point of the retryable split, as behaviour. A document that does not mention a
    # fact will not start mentioning it on a second attempt, so retrying only invites fabrication.
    calls = []
    def fn(messages, info: AgentInfo):
        calls.append(1)
        return ModelResponse(parts=[_brief_call("doc-9")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    with pytest.raises(Exception) as e:
        agent.run_sync("investor brief")
    # The count is asserted FIRST, and the type is caught loosely, so that this test reddens on the
    # property it names. retries=1 DOES permit a second model call on this path - the malformed
    # citation test below only goes green because it does - so one call is a fact about the
    # escalation, not about a budget of zero. A validator that turned MissingSource into a
    # ModelRetry spends that budget and arrives here at two, which is the line that then fails.
    assert len(calls) == 1
    assert isinstance(e.value, ResearchEscalation)        # terminal, not retry exhaustion
    assert isinstance(e.value.__cause__, MissingSource)   # escalated from the contract failure
    assert "doc-9" in str(e.value)                        # naming the citation that did not resolve

def test_malformed_citation_is_retried_with_prior_value_in_the_retry_prompt():
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[_brief_call("" if len(seen) == 1 else "doc-1")])
    agent = build_research_agent(FunctionModel(fn), doc_ids=DOCS)
    out = agent.run_sync("investor brief").output
    assert out.claims[0].source == "doc-1"
    # Assert on the RETRY PROMPT, not on str(seen[1]). The second call's message history already
    # carries the model's own offending response, whose args repr as "'source': ''" - so a check
    # for "''" anywhere in that history passes even when the retry prompt quotes nothing at all,
    # and enforces nothing. Only the prompt the model is handed can carry the prior value back.
    prompts = [p for m in seen[1] for p in getattr(m, "parts", ()) if isinstance(p, RetryPromptPart)]
    assert prompts, "the second call carried no retry prompt"
    assert "''" in str(prompts[0].content)   # the prior offending value, verbatim
