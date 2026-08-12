"""Replays the captured ask fixture through the hook.

This file SKIPPED while the P4 demo had not run, and that was the honest state: the fixture cannot
be hand-authored into existence - its provenance is the point (spec 2.3) - and the P1 smoke
deliberately owned no send tool, so no session before the demo could produce an "ask" at all. The
demo ran on 2026-08-12 and its capture is tracked, so the skip's reason ("not yet run") stopped
being true, and a missing fixture is now a broken checkout rather than a lane awaiting its turn.
Absence FAILS, on the same doctrine as the frozen P1 payloads in `tests/test_fixture_meta.py`: a
skip whose printed reason is false is worse than no skip at all.

`scripts/demo.py` is NAMED in the failure message and imported nowhere. `tests/test_fixture_meta.py`
carries the rule that enforces the difference, and it parses rather than greps for exactly this
case: the brief's `grep -r demo tests/` check reports this docstring and the string below.
"""
import asyncio, json
from pathlib import Path
from retinue.boundary.hook import SEND_TOOLS, pre_tool_use

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads" / "captured_ask.json"

def test_captured_ask_payload_replays_to_ask():
    """The ask, and the ask FOR THE RIGHT REASON.

    `pre_tool_use` answers "ask" down two arms, and only one of them is this fixture's subject: a
    send by a gated specialist, and an agent_type the routing table does not recognise. A test
    asserting the decision alone passes on a capture whose `agent_type` arrived misspelled, which is
    the failure it would most want to report - the send arm would then be dead and the suite would
    say the containment replays. So the payload's own routing facts are pinned first, and the reason
    string is read for the send arm's wording rather than for the word "human", which both arms use.
    """
    assert FIX.exists(), (
        "fixtures/payloads/captured_ask.json is tracked (captured by scripts/demo.py on "
        "2026-08-12), so a missing one is a broken checkout; re-capturing with RETINUE_LIVE=1 "
        "overwrites the canon and is a deliberate act")
    row = json.loads(FIX.read_text(encoding="utf-8"))
    assert row["meta"]["captured"]                       # provenance stamp required
    payload = row["payload"]
    assert payload["agent_type"] == "conversation"
    assert payload["tool_name"] in SEND_TOOLS
    out = asyncio.run(pre_tool_use(payload, None, None))
    spec = out["hookSpecificOutput"]
    assert spec["permissionDecision"] == "ask"
    assert "outward send by" in spec["permissionDecisionReason"]
