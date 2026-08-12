import asyncio, json
from pathlib import Path
import pytest
from retinue.boundary.hook import SEND_TOOL, SEND_TOOLS, decide, pre_tool_use

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads"

def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))["payload"]

def load_captured_research():
    """The research arm replays a CAPTURED payload (spec 2.1), chosen by content and not by
    filename. The smoke's payload ORDER is a property of one run - which tool the orchestrator
    reached for first, and how often - so pinning `captured_02.json` would make an equally valid
    future capture look like a regression. Absent is an error rather than a skip: this arm exists
    to replay a real subagent call, and having none to replay is the failure, not a reason to
    pass quietly."""
    for p in sorted(FIX.glob("captured_*.json")):
        payload = json.loads(p.read_text(encoding="utf-8"))["payload"]
        if payload.get("agent_type") == "research" and payload.get("tool_name") == "Read":
            return payload
    raise AssertionError(f"no captured research Read payload under {FIX}")

def test_decision_table_is_total():
    assert decide(None, "anything") == "allow"                 # main thread
    assert decide("research", "Read") == "allow"
    assert decide("drafting", "Read") == "allow"
    # The send tool's name is imported, never respelled: it has one home. The wire spelling is
    # still pinned, because the two fixture-driven tests below carry the literal in JSON and go
    # red the moment the constant stops matching it.
    assert decide("conversation", SEND_TOOL) == "ask"
    assert decide("conversation", "Read") == "allow"           # non-send conversation tool
    assert decide("mystery", "Read") == "ask"                  # unknown fails toward the human

def test_conversation_is_asked_on_every_spelling_of_the_send_tool():
    """Both members of `SEND_TOOLS`, because Task 22 is what made the second one reachable.

    Until the conversation roster and the session ceiling gained these names, no send tool of any
    spelling resolved into any session, so `decide`'s conversation arm was pinned on the bare name
    alone and the `mcp__` spelling was carried as data nothing exercised. Narrowing that arm to
    `tool_name == SEND_TOOL` - which reads like a tidy-up, since the constant is right there -
    would leave the offered tool ungated and every other test in this file green.

    The shape is pinned before the loop runs, because a loop over a set is greenest when the set is
    empty: `SEND_TOOLS` emptied or collapsed to one name makes the assertions below vacuous, which
    is the failure mode of a test that reads the same constant the code under test reads.
    """
    assert len(SEND_TOOLS) == 2 and any(t.startswith("mcp__") for t in SEND_TOOLS)
    p = load("provisional_send.json")
    for name in sorted(SEND_TOOLS):
        assert decide("conversation", name) == "ask", name
        out = asyncio.run(pre_tool_use({**p, "tool_name": name}, None, None))
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask", name

def test_the_main_thread_reaches_the_deny_lane_on_every_spelling():
    """The reach Task 22 widened, gated by the other door.

    The session ceiling is the orchestrator's bound too, so putting the send names there let the
    MAIN THREAD reach a send tool where before it none existed anywhere in the session. That is a
    real widening and it is stated rather than waved at: `decide` answers "allow" for a main-thread
    call, and the allow arm puts every send payload INTO the imported deterministic lane rather
    than past it. Ask for the subagent, the lane for the main thread, and neither is a send.

    THIS PAYLOAD, not every payload, and the distinction is the test's whole scope. The imported
    lane answers `{}` to allow and a deny dict to refuse, so a denial is a property of what was
    submitted; what generalises is that the main thread cannot skip the lane, and a payload the
    lane allowed would still meet the chokepoint inside the send tool body. The fixture used here
    is the one the showcase test at the foot of this file already relies on for a refusal.

    The REASON is deliberately not asserted, unlike that showcase test. The two spellings refuse on
    two different primary findings, because the fixture's grant names one of them - which is a
    property of that fixture rather than of the router.
    """
    p = load("provisional_send.json")
    p.pop("agent_type")
    for name in sorted(SEND_TOOLS):
        out = asyncio.run(pre_tool_use({**p, "tool_name": name}, None, None))
        assert out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", name

def test_outward_send_returns_ask_shape():
    out = asyncio.run(pre_tool_use(load("provisional_send.json"), None, None))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "ask"

def test_research_read_passes_untouched():
    # Was `provisional_research.json`, a hand-authored double of exactly this call whose own note
    # said the P1 capture smoke would replace it. The smoke has run, so it did: this replays the
    # real payload, with the real `agent_type` spelling the CLI actually sends.
    assert asyncio.run(pre_tool_use(load_captured_research(), None, None)) == {}

def test_a_malformed_payload_asks_rather_than_raising():
    # A hook that raises fails OPEN - the platform contract is that an exception propagating
    # out of a hook does not block the tool call. These are the two shapes that would raise
    # ahead of the imported lane's own BaseException net, making its guard unreachable.
    for payload in (None, {"tool_name": ["not", "a", "string"]}):
        out = asyncio.run(pre_tool_use(payload, None, None))
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"

class _CancelOnRead(dict):
    def get(self, *args, **kwargs):
        raise asyncio.CancelledError()

def test_cancellation_propagates_rather_than_becoming_an_ask():
    # The imported lane's BaseException net is safe only because its body has no await; this
    # one awaits that lane, so a cancellation caught here would make the router un-cancellable.
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pre_tool_use(_CancelOnRead(), None, None))

def test_main_thread_send_still_runs_the_deterministic_lane():
    p = load("provisional_send.json"); p.pop("agent_type")
    out = asyncio.run(pre_tool_use(p, None, None))
    spec = out.get("hookSpecificOutput", {})
    assert spec.get("permissionDecision") == "deny"
    # figure-not-in-record IS the primary finding: the fixture supplies the approval token and a
    # consented jurisdiction precisely so the 9M-vs-8M mismatch is findings[0] - a token-less
    # fixture would deny on no_approval_token and this comment would be the masquerade 5.2 warns
    # about, documented into the showcase test.
    assert "figure_not_in_record" in spec.get("permissionDecisionReason", "")
