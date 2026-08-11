import asyncio, json
from pathlib import Path
import pytest
from retinue.boundary.hook import SEND_TOOL, decide, pre_tool_use

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
