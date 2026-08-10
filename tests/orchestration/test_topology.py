from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from retinue.orchestration.topology import AGENTS, SESSION_TOOLS, SPAWN_TOOLS, TIERS, build_options

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

def test_orchestrator_is_pre_approved_for_the_spawn_tool_only():
    opts = build_options(_noop_hook)
    assert set(opts.allowed_tools) == set(SPAWN_TOOLS)   # both names as data; runtime binds one

def test_the_session_roster_drops_every_write_and_outbound_capability():
    # A real narrowing, and the reason research cannot reach an outbound surface even by
    # inheritance. Not None: an omitted roster inherits all tools from the parent.
    opts = build_options(_noop_hook)
    assert opts.tools is not None
    # Three axes, and the ceiling is bracketed only by all three together:
    #   ORIGIN - build_options must publish the constant and not a list of its own, so the call
    #     site cannot widen past it: tools=list(SESSION_TOOLS) + ["NotebookEdit"] reddens here.
    #   THE CONSTANT - restated literally below, so a widening from any source must be authored
    #     twice, in two files. Double entry, the ordinary control for a declaration like this one;
    #     an equality against SESSION_TOOLS alone cannot object, since both sides move together.
    #   CONTENT - the denylist catches the dangerous names from either source, including one a
    #     widener went to the trouble of restating in both places.
    # The cost is a second line to edit whenever the ceiling legitimately changes, at Task 22 among
    # others. That is the control working, not friction to design away.
    assert opts.tools == list(SESSION_TOOLS)
    assert list(SESSION_TOOLS) == ["Agent", "Task", "Read", "Grep", "Glob"]
    assert not ({"Bash", "Write", "Edit", "WebFetch", "WebSearch"} & set(opts.tools))

def test_the_session_roster_covers_every_declared_agent_roster():
    # The CLI intersects each subagent's declared tools with the session roster, so a name in
    # an AgentDefinition that is missing here resolves to nothing - silently, with every other
    # test in this file still green. This is the assertion that makes that coupling visible.
    opts = build_options(_noop_hook)
    # `or ()` is deliberately fail-open here, the inverse of the research guard above: an agent
    # with tools=None inherits the session roster and so cannot be starved by it. Tightening this
    # to `is not None` would redden on a config this test does not speak to.
    starved = {name: sorted(set(d.tools or ()) - set(opts.tools)) for name, d in AGENTS.items()}
    starved = {name: missing for name, missing in starved.items() if missing}
    assert not starved, f"declared but absent from the session roster: {starved}"

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
    # optimisation, which is not a property to assert on. The constant is stripped before the
    # comparison because that render is `'\n'.join(parts).strip()`: without it, rewriting this
    # prompt as a triple-quoted string with a leading newline - the obvious refactor, and the one
    # Tasks 17 and 22 will reach for - reddens a test with nothing wrong behind it.
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={
            "claims": [{"claim": "writes early checks", "evidence": "p4", "source": "doc-1",
                        "source_date": "2030-01-02", "confidence": 0.8}]})])
    build_research_agent(FunctionModel(fn), doc_ids=frozenset({"doc-1"})).run_sync("investor brief")
    assert RESEARCH_PROMPT.strip() in (seen[0][0].instructions or "")

def test_hook_is_registered_once_on_pre_tool_use():
    opts = build_options(_noop_hook)
    matchers = opts.hooks["PreToolUse"]
    assert len(matchers) == 1 and _noop_hook in matchers[0].hooks
