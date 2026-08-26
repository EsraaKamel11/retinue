import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from retinue.specialists.intake import INTAKE_PROMPT, IntakeTurn, build_intake_agent

def turn(body="What does the company build, and who buys it?"):
    return IntakeTurn(body=body)

def test_the_turn_is_light_and_composes_no_draft():
    """The light-schema contract, asserted as an ABSENCE the way conversation asserts its own.

    Conversation composes a `Draft` inside its turn and the test there pins that the thread is not
    siblinged beside it. Intake pins the opposite shape for the opposite reason: there is no draft
    field at all, because a live capture lane measured the full-Draft output schema failing under
    the model's output retries while this three-field turn succeeded. The Draft composes downstream
    at the send chokepoint, which is where the gate runs, so nothing is lost by the turn not
    carrying one.

    `cited_fields` defaults to empty rather than being required, because the opening question of a
    stage cites nothing: a required tuple would make the model invent a citation for a message that
    quotes no record field, which is the fabrication pressure this fleet spends its prompts
    refusing.
    """
    t = turn()
    assert t.cited_fields == ()
    assert t.intent == "ask"
    assert "draft" not in IntakeTurn.model_fields   # light schema: the Draft composes downstream

def test_the_turn_is_frozen():
    # Frozen for the same reason every other specialist output is: a turn a caller can edit after
    # the model produced it is not the thing the reviewer read.
    t = turn()
    with pytest.raises(ValidationError):
        t.body = "rewritten after the fact"

def test_parity_intake_prompt_is_the_same_object():
    from retinue.orchestration.topology import AGENTS, TIERS
    assert AGENTS["intake"].prompt is INTAKE_PROMPT
    assert TIERS["intake"] == "sonnet-tier"

def test_the_pydantic_ai_agent_is_handed_the_same_prompt_constant():
    """The other half of the parity rule, which the identity check above cannot reach.

    FunctionModel never reads the agent's instructions, so every other test in this module stays
    green with `instructions=INTAKE_PROMPT` deleted from `build_intake_agent`. Parity means BOTH
    artifacts, the SDK AgentDefinition and the pydantic-ai Agent, and a rule pinned on one side is
    half a rule. This mirrors what research, drafting and conversation already do rather than
    inventing a fourth convention.

    Read off `ModelRequest.instructions`, the public field carrying what the model is actually
    handed, and not `Agent._instructions`. That field is a join of the agent's literal
    instructions, so it can only be asked whether it CARRIES the constant; the constant is
    stripped before the comparison because the render is `'\\n'.join(parts).strip()`.
    """
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={
            "body": "What does the company build, and who buys it?",
            "cited_fields": [], "intent": "ask"})])
    build_intake_agent(FunctionModel(fn)).run_sync("open the company stage")
    assert INTAKE_PROMPT.strip() in (seen[0][0].instructions or "")

def test_the_intake_roster_names_no_send_tool():
    """The DECLARED side of intake's containment, and the inverse of conversation's own pair.

    Conversation names the send tool in its roster because its turn proposes an act and the hook
    holds that act for a human before the call. Intake proposes no act: it authors the founder's
    side of the desk, and the send chokepoint downstream is where a Draft is composed and gated.
    So the roster is `Read` alone, which is drafting's shape rather than conversation's, and this
    row is what says the choice was made rather than inherited.

    The RESOLVED side, after the CLI intersects this declaration with the session ceiling, is
    `test_widening_the_ceiling_offers_no_send_tool_to_any_content_specialist` in
    `tests/orchestration/test_topology.py`. Both exist for the reason conversation's pair exists:
    a declaration and what the runtime offers are different facts.
    """
    from retinue.boundary.hook import SEND_TOOLS
    from retinue.orchestration.topology import AGENTS
    assert AGENTS["intake"].tools is not None      # unset inherits the CLI default, outbound included
    assert not (set(AGENTS["intake"].tools or []) & set(SEND_TOOLS))

def test_intake_is_routed_rather_than_taking_the_unknown_agent_ask():
    """A specialist the topology declares and the routing table does not know is a table that has
    quietly stopped describing the fleet. `test_decision_table_is_total` holds the two sets equal;
    this row pins the ANSWER for intake, which that equality does not reach: intake is routed with
    nothing gated, exactly as research and drafting are, because it is offered no gated tool.
    """
    from retinue.boundary.hook import decide
    assert decide("intake", "Read") == "allow"
