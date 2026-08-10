import asyncio, json
from pathlib import Path
import pytest
from retinue.boundary.hook import SEND_TOOL, decide, pre_tool_use

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads"

def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))["payload"]

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
    assert asyncio.run(pre_tool_use(load("provisional_research.json"), None, None)) == {}

def test_a_malformed_payload_asks_rather_than_raising():
    # A hook that raises fails OPEN - the platform contract is that an exception propagating
    # out of a hook does not block the tool call. These are the two shapes that would raise
    # ahead of the imported lane's own BaseException net, making its guard unreachable.
    for payload in (None, {"tool_name": ["not", "a", "string"]}):
        out = asyncio.run(pre_tool_use(payload, None, None))
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"

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
