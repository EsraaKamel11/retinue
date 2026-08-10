from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from retinue.orchestration.topology import AGENTS, SPAWN_TOOLS, TIERS, build_options

async def _noop_hook(input_data, tool_use_id, context):
    return {}

def test_every_agent_is_foreground():
    for name, d in AGENTS.items():
        assert getattr(d, "background", None) is False, f"{name} must set background=False"

def test_research_has_no_outbound_tool_at_all():
    # The roster is pinned as PRESENT before it is inspected. `or []` below collapses an unset
    # roster to an empty one, and both checks then hold vacuously - yet unset is the dangerous
    # value, not the safe one: the SDK serialises an AgentDefinition by dropping every None field,
    # so tools=None sends no roster at all and the subagent inherits the CLI default, outbound
    # tools included. Without this line the test is greenest on the exact config it forbids.
    assert AGENTS["research"].tools is not None
    tools = AGENTS["research"].tools or []
    assert all("send" not in t.lower() for t in tools)
    assert "WebFetch" not in tools and "WebSearch" not in tools

def test_orchestrator_holds_only_the_spawn_tool():
    opts = build_options(_noop_hook)
    assert set(opts.allowed_tools) == set(SPAWN_TOOLS)   # both names as data; runtime binds one

def test_tiers_use_the_imported_vocabulary_exactly():
    from chaperone.gates.checker import MODEL_STRENGTH
    assert set(TIERS.values()) <= set(MODEL_STRENGTH)   # single-sourced; topology itself never imports gates

def test_research_parity_prompt_is_the_same_object():
    from retinue.specialists.research import RESEARCH_PROMPT, build_research_agent
    assert AGENTS["research"].prompt is RESEARCH_PROMPT   # the spec's parity rule: same object, not equal strings

    # The pydantic-ai half of the same rule, unpinned until now: FunctionModel never reads the
    # agent's instructions, so every test of the research agent stays green with the
    # instructions=RESEARCH_PROMPT argument deleted. Parity means BOTH artifacts, and a rule pinned
    # on one side is half a rule. Read it off ModelRequest.instructions - the public field carrying
    # what the model is actually handed - rather than Agent._instructions, which is private. That
    # field is a join of the agent's literal instructions, so it can only be asked whether it
    # CARRIES the constant; identity survives the join today by a CPython single-element
    # optimisation, which is not a property to assert on.
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={
            "claims": [{"claim": "writes early checks", "evidence": "p4", "source": "doc-1",
                        "source_date": "2030-01-02", "confidence": 0.8}]})])
    build_research_agent(FunctionModel(fn), doc_ids=frozenset({"doc-1"})).run_sync("investor brief")
    assert RESEARCH_PROMPT in (seen[0][0].instructions or "")

def test_hook_is_registered_once_on_pre_tool_use():
    opts = build_options(_noop_hook)
    matchers = opts.hooks["PreToolUse"]
    assert len(matchers) == 1 and _noop_hook in matchers[0].hooks
