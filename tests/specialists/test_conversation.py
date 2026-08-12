import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from chaperone.policy.types import Message, Record
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from retinue.ledger.projection import RelationshipRecord
from retinue.specialists.conversation import (CONVERSATION_PROMPT, ConversationTurn,
                                              build_conversation_agent)
from retinue.specialists.drafting import build_draft

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"

VIOLATING = "Honestly, this company is a great investment and you should take the allocation."

def frozen_row(body):
    """The scripted row this body keys, read from the same fixture the transport loads.

    A `next` over a generator with no default, so a body the fixture no longer carries raises
    StopIteration here and names the fixture, rather than resolving to None and comparing a
    category against nothing.
    """
    rows = json.loads(FIX.read_text(encoding="utf-8"))["verdicts"]
    return next(r for r in rows if r["body"] == body)

def rec():
    return RelationshipRecord(investor_id="inv-1", stated_check_size=Decimal("250000"),
                              pass_reason=None,
                              last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                              jurisdiction="US", domain="example.test")

THREAD = (Message(role="investor", body="What changed since we spoke?"),)

def turn(body="Following up on our conversation."):
    return ConversationTurn(draft=build_draft(rec(), THREAD, body, ()), intent="reply")

def test_the_turn_composes_a_draft_and_the_thread_rides_inside_it():
    t = turn()
    assert t.draft.thread == THREAD
    assert "thread" not in ConversationTurn.model_fields    # composed, never siblinged (spec 4.3)

def test_parity_conversation_prompt_is_the_same_object():
    from retinue.orchestration.topology import AGENTS
    assert AGENTS["conversation"].prompt is CONVERSATION_PROMPT

def test_the_pydantic_ai_agent_is_handed_the_same_prompt_constant():
    """The other half of the parity rule, which the identity check above cannot reach.

    FunctionModel never reads the agent's instructions, so every other test in this module stays
    green with `instructions=CONVERSATION_PROMPT` deleted from `build_conversation_agent`. Parity
    means BOTH artifacts, the SDK AgentDefinition and the pydantic-ai Agent, and a rule pinned on
    one side is half a rule. This mirrors what the research and drafting specialists already do
    rather than inventing a third convention.

    Read off `ModelRequest.instructions`, the public field carrying what the model is actually
    handed, and not `Agent._instructions`. That field is a join of the agent's literal
    instructions, so it can only be asked whether it CARRIES the constant; the constant is
    stripped before the comparison because the render is `'\\n'.join(parts).strip()`.
    """
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args={
            "draft": asdict(build_draft(rec(), THREAD, "Following up on our conversation.", ())),
            "intent": "reply"})])
    build_conversation_agent(FunctionModel(fn)).run_sync("carry the conversation")
    assert CONVERSATION_PROMPT.strip() in (seen[0][0].instructions or "")

def test_conversation_roster_names_the_send_tool_by_import():
    from retinue.orchestration.topology import AGENTS
    from retinue.boundary.hook import SEND_TOOLS
    assert set(AGENTS["conversation"].tools or []) & set(SEND_TOOLS)

def test_the_send_tool_survives_the_session_intersection():
    """The DECLARED roster is not the RESOLVED one. The CLI intersects each subagent's tools with
    the session roster, so a send tool named here and absent from SESSION_TOOLS is stripped at
    runtime while every options-shape assertion stays green.

    The test above cannot be this test, and the difference is the whole reason both exist. It reads
    the declaration, which is the side that stays true while the runtime is starved.

    What this repository already held is worth stating precisely, because the plan's amendment says
    nothing would have caught the stripping and that is true of the PLAN rather than of the tree:
    `test_the_session_roster_covers_every_declared_agent_roster` reddens on a conversation roster
    naming a tool the ceiling does not carry. That test forces A fix and is equally satisfied by
    deleting the send tool from conversation's roster, which is the fix that ships a conversation
    specialist unable to do the one thing its gating story is about. This one pins the DIRECTION.
    """
    from retinue.orchestration.topology import AGENTS, SESSION_TOOLS
    from retinue.boundary.hook import SEND_TOOLS
    resolved = [t for t in (AGENTS["conversation"].tools or []) if t in SESSION_TOOLS]
    assert set(resolved) & set(SEND_TOOLS)

def test_a_violating_turn_routes_through_the_preflight():
    """The composed draft reaches the checker intact, and the frozen verdict FOR THIS BODY answers.

    `routes_to_human` is True for a draft the checker denied and equally for a draft never judged
    at all, so on its own it cannot tell the two apart. THREE answers collapse into that one True,
    and the third is the one worth naming because it is not obvious: the scripted transport raises
    `CheckerUnavailable` for a body no frozen row carries, and the imported gate turns that into a
    denial of its OWN rather than letting it reach `annotate`'s handler. So `p.error` stays None
    and `p.outcome.allow` stays False for a draft the checker never saw. Measured, and measured
    after asserting the opposite: an earlier version of this docstring said the annotation errored,
    which is what the two-signal design reads like from the outside and is not what happens.

    The CATEGORY is therefore the assertion that makes this a test of the composition. An
    unrecognised body comes back `other` with a `checker unavailable` detail; this one comes back
    carrying the frozen row's own violation class, which it can only do if the body the turn
    composed arrived at the transport as the key that row is stored under. The expected class is
    read out of the same fixture the transport loads, so a fixture whose row moved reddens here
    rather than being quietly agreed with.
    """
    from chaperone.policy.act_classes import ActContext
    from retinue.boundary.checker_lane import build_checker, scripted_transport
    from retinue.boundary.hook import SEND_TOOL
    from retinue.boundary.preflight import annotate, routes_to_human
    t = turn(VIOLATING)
    context = ActContext(approval_token="tok-1", tier=2,
                         consented_jurisdictions=frozenset({"US"}),
                         granted_tools=frozenset({SEND_TOOL}), sent_count=0, send_cap=5)
    p = annotate(t.draft, Record(fields={}), context, build_checker(scripted_transport(FIX)))
    assert routes_to_human(p)
    assert p.error is None and p.outcome is not None and not p.outcome.allow
    assert p.outcome.payload["category"] == frozen_row(VIOLATING)["violation_class"]
