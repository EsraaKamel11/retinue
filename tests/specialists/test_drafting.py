from datetime import datetime, timezone
from decimal import Decimal
import pytest
from chaperone.policy.types import Message
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from retinue.boundary.hook import SEND_TOOL
from retinue.evals.control import BLOCK_ONLY_FIELDS, answer_from, strip_block
from retinue.ledger.block import render_block
from retinue.ledger.projection import RelationshipRecord, as_policy_record
from retinue.specialists.drafting import DRAFTING_PROMPT, build_draft, build_drafting_agent

def rec(**over):
    base = dict(investor_id="inv-1", stated_check_size=Decimal("250000"),
                pass_reason=None, last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                jurisdiction="US", domain="example.test")
    base.update(over)
    return RelationshipRecord(**base)

THREAD = (Message(role="investor", body="What changed since we spoke?"),)

def test_jurisdiction_and_domain_come_from_the_identity_record():
    d = build_draft(rec(), THREAD, "A short update.", ("stated_check_size",))
    assert (d.recipient_jurisdiction, d.recipient_domain) == ("US", "example.test")
    assert d.thread == THREAD

def test_missing_identity_raises_never_defaults():
    with pytest.raises(ValueError, match="identity"):
        build_draft(rec(jurisdiction=None), THREAD, "A short update.", ())

def test_the_identity_guard_covers_domain_not_only_jurisdiction():
    """Half a guard is the half that never runs.

    The test above removes `jurisdiction` and never touches `domain`, so a guard narrowed to
    `not record.jurisdiction` alone reddens nothing anywhere: the raise still fires on the one
    shape any test hands it, and drafting for a party whose domain is unknown proceeds to build a
    Draft carrying `recipient_domain=None` into the imported policy engine. Both terms are
    exercised here for the same reason the guard has both.

    `""` as well as `None`, because the guard is written on FALSINESS and the projection can
    produce either: `ident.payload.get("domain")` returns None when the identity touchpoint never
    recorded one and returns the empty string when it recorded one empty. A guard rewritten as
    `is None` for apparent precision would pass an empty recipient domain straight through, and
    that rewrite is invisible to a test that only ever passes None.
    """
    for absent in (None, ""):
        with pytest.raises(ValueError, match="identity"):
            build_draft(rec(domain=absent), THREAD, "A short update.", ())

def test_tool_name_is_the_imported_single_home():
    d = build_draft(rec(), THREAD, "A short update.", ())
    assert d.tool_name is SEND_TOOL      # imported, never respelled - the audit's rule stays green

def test_policy_record_carries_money_as_string_from_decimal():
    r = as_policy_record(rec())
    assert r.get("stated_check_size") == "250000"

def test_parity_drafting_prompt_is_the_same_object():
    from retinue.orchestration.topology import AGENTS
    assert AGENTS["drafting"].prompt is DRAFTING_PROMPT

def test_the_pydantic_ai_agent_is_handed_the_same_prompt_constant():
    """The other half of the parity rule, which the identity check above cannot reach.

    FunctionModel never reads the agent's instructions, so every other test of this module stays
    green with `instructions=DRAFTING_PROMPT` deleted from `build_drafting_agent`. Parity means
    BOTH artifacts - the SDK AgentDefinition and the pydantic-ai Agent - and a rule pinned on one
    side is half a rule. This mirrors the research specialist's own parity test rather than
    inventing a second convention.

    Read off `ModelRequest.instructions`, the public field carrying what the model is actually
    handed, and not `Agent._instructions`. That field is a join of the agent's literal
    instructions, so it can only be asked whether it CARRIES the constant; the constant is
    stripped before the comparison because the render is `'\\n'.join(parts).strip()`.
    """
    seen = []
    def fn(messages, info: AgentInfo):
        seen.append(messages)
        return ModelResponse(parts=[TextPart("A short update.")])
    build_drafting_agent(FunctionModel(fn)).run_sync("draft a short update")
    assert DRAFTING_PROMPT.strip() in (seen[0][0].instructions or "")

def test_the_block_is_load_bearing_for_the_real_drafting_prompt():
    """The block-stripped control (spec 7.1) run over the prompt this specialist actually carries.

    Until now the control had only its own fixture prose to strip, so "the block is load-bearing"
    was a statement about HEAD and TAIL strings written inside the control's test file. Here the
    instruction is the shipped `DRAFTING_PROMPT` object, which is what makes this a measurement of
    the drafting specialist rather than of the eval's own scaffolding.

    ASSEMBLY, stated because it is the one thing this caller must get right. `render_block` ends in
    exactly one newline, so the instruction appends straight onto its output and the block's last
    field line stays a line of its own. `render_block(...).rstrip() + " " + DRAFTING_PROMPT` puts
    the instruction INSIDE a line the block rendered; the walk then takes the instruction along
    with that line and hands back a "stripped" prompt that asks nothing at all. All three questions
    miss, the control reports the block load-bearing, and it demonstrated nothing. No stripper can
    close that route, which is why the middle assertion here is the one that matters: the
    instruction has to come back WHOLE, or the two questions either side of it are vacuous.
    """
    prompt = render_block(rec()) + DRAFTING_PROMPT      # one newline is the seam; never rstripped
    assert all(answer_from(prompt, f) is not None for f in BLOCK_ONLY_FIELDS)
    stripped = strip_block(prompt)
    assert stripped == DRAFTING_PROMPT                  # the ask survived; this control is not hollow
    assert all(answer_from(stripped, f) is None for f in BLOCK_ONLY_FIELDS)
