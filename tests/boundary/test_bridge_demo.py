"""The end-to-end evidence: resolution -> mint -> validated, consumed, gated, ledgered send,
driven by the captured ask payload. This test is the evidence bar's first and sixth bullets.

Two layers, deliberately. The brief's two tests pin the SCRIPT'S OUTPUT CONTRACT, because a demo
whose printing is wrong is a demo that shows nothing, and the exit code is what CI reads. Every
test after them pins EFFECTS, read off the ledger, the queue and the approval store the run
actually used - because a string in stdout is a proxy for the act, and this repository's standard
is that a test asserts the property rather than a proxy for it. `bridge_run` exists to make that
possible: it returns what the run left behind, and `main` is the printing around it, the same
split `retinue.boundary.resolve.outcome_after_read` already uses one module over.

`from scripts.bridge import main` and NOT `from demo.bridge import main`, which the plan's Task 4
listing asks for. `tests/test_fixture_meta.py` matches gated script names as SUBSTRINGS of imported
module names, and `demo` is one of them, so the plan's own import line reddens
`test_no_test_module_imports_a_gated_script` on a script that is gated by nothing. Measured, not
supposed: the finding is `test_imports_gated_script: t.py:1 ['demo']`. The task report carries it.
"""
import json
from datetime import timedelta
from pathlib import Path

from retinue.boundary.approvals import validate_and_consume
from retinue.boundary.send_tool import REVIEW_QUEUE
from retinue.ledger.models import Touchpoint
from scripts.bridge import T0, bridge_run, ledger_line, main

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "payloads" / "captured_ask.json"


def captured_body() -> str:
    return json.loads(FIX.read_text(encoding="utf-8"))["payload"]["tool_input"]["body"]


def test_the_captured_ask_drives_a_bridged_approval_end_to_end(capsys):
    assert main(["--approve-as", "reviewer-1"]) == 0
    out = capsys.readouterr().out
    body = captured_body()
    assert "resolved by reviewer-1" in out
    assert "allowed" in out.lower()
    assert "sent" in out.lower()          # the ledger row's kind, printed from the row
    assert str(len(body.encode())) in out  # body_bytes printed from the recorded touchpoint


def test_a_rejecting_operator_mints_nothing_and_nothing_sends(capsys):
    assert main(["--reject-as", "reviewer-1"]) == 1
    out = capsys.readouterr().out
    assert "no token" in out.lower()
    assert "sent" not in out.lower()


def test_the_printed_ledger_line_is_the_row_the_store_holds(capsys):
    """The printed line is held against a row, so it cannot be printed from literals.

    The brief asks for the byte count to be read back FROM THE STORE, and the assertion it supplies
    for that - the number appearing anywhere in stdout - cannot see the difference: `attempt_send`
    computes the row's `body_bytes` from the same draft the script holds, so the two sources agree
    by construction and a print from either satisfies it. What IS observable is whether the line
    reports the ROW: its kind and its delivery status come from the touchpoint and from nowhere
    else, and a hand-written `delivery=CONFIRMED` reddens here while passing every assertion above.
    """
    effects = bridge_run(verdict="approve", by="reviewer-1")
    row = effects.touchpoints[-1]
    assert main(["--approve-as", "reviewer-1"]) == 0
    out = capsys.readouterr().out
    assert ledger_line(row) in out


def test_the_ledger_line_reports_the_row_rather_than_this_scripts_happy_path():
    """Driven on a row that says something else, which is what makes the claim checkable.

    Every run this script can make records `kind=sent` with `delivery=CONFIRMED`, so over its own
    output a line built from three literals is indistinguishable from a line built from the
    touchpoint - measured: hardcoding `delivery=CONFIRMED` passes every other test in this file.
    A row carrying the tri-state's other answers separates them.
    """
    row = Touchpoint(idempotency_key="k", investor_id="inv-demo", mandate_id=None, kind="contact",
                     payload={"body_bytes": 3}, occurred_at=T0, recorded_at=T0,
                     delivery_status="UNVERIFIABLE")
    assert ledger_line(row) == "ledger row: kind=contact delivery=UNVERIFIABLE body_bytes=3"


def test_the_approved_run_leaves_one_confirmed_row_and_escalates_nothing():
    """The EFFECTS the output test can only gesture at, read off the stores the run used.

    The output test above passes on a script that prints the right words having done nothing at
    all - `print("allowed ... sent ... 88")` satisfies every one of its assertions. What cannot be
    printed into existence is a ledger holding exactly one CONFIRMED `sent` row whose recorded byte
    count is the captured body's own, with nothing in the review queue beside it.
    """
    out = bridge_run(verdict="approve", by="reviewer-1")
    assert out.token is not None
    assert out.result is not None and out.result.allowed
    assert [t.kind for t in out.touchpoints] == ["identity", "sent"]
    row = out.touchpoints[-1]
    assert row.delivery_status == "CONFIRMED"
    assert row.payload == {"body_bytes": len(captured_body().encode())}
    assert out.escalations == []


def test_the_approved_act_spends_its_approval_exactly_once():
    """Single use, asserted where it is observable: the token the run minted is already gone.

    The chokepoint consumes at the pre-check, so after a successful bridged send the same token
    cannot carry a second act. A pre-check that verified without consuming leaves this token
    spendable and reddens here, and nothing in the output contract above would notice.
    """
    out = bridge_run(verdict="approve", by="reviewer-1")
    assert out.token is not None
    again = validate_and_consume(token=out.token.token, key=out.key, draft=out.draft, at=T0,
                                 store=out.approvals)
    assert again is not None and "consum" in again


def test_a_rejection_resolves_the_row_mints_nothing_and_reaches_no_ledger():
    """The refusing arm's effects. A rejection is a resolution: the row is settled and unresolvable
    again, and no approval exists for anything to spend."""
    out = bridge_run(verdict="reject", by="reviewer-1")
    assert out.token is None
    assert out.result is None
    assert [t.kind for t in out.touchpoints] == ["identity"]   # the seed, and nothing the run added
    assert out.escalations == []
    # The rejection DID resolve the row, so a second reviewer settles nothing.
    assert out.resolutions.record(out.row_id, T0, "reviewer-2") is False


def test_the_token_the_run_mints_binds_the_captured_body_and_the_gated_tool():
    """What the mint bound, rather than that it minted. Every binding is a leg the chokepoint
    compares against the act's own fact, so a token bound to the wrong body or the wrong spelling
    of the tool is a token the boundary refuses - which is the whole subject of the bridge."""
    from retinue.boundary.approvals import body_digest_of
    from retinue.boundary.hook import SEND_TOOL

    out = bridge_run(verdict="approve", by="reviewer-1")
    t = out.token
    assert t is not None
    assert t.body_digest == body_digest_of(captured_body())
    assert t.tool == SEND_TOOL          # the spelling the chokepoint gates on, not the wire one
    assert t.recipient_domain == out.draft.recipient_domain
    assert t.idempotency_key == out.key
    assert t.expires_at == T0 + timedelta(hours=24)


def test_a_denied_act_would_escalate_to_the_queue_the_boundary_routes_to():
    """The queue is WIRED, shown by driving something into it rather than by reading the source.

    Every assertion above says the queue stayed empty, and an empty queue is what a run with no
    queue at all also produces. So this drives the one arm that fills it: a body the frozen verdict
    fixture denies, carried by a correctly bound token, lands a row under the boundary's own queue
    name. Without it `escalations == []` rests on nothing.
    """
    out = bridge_run(verdict="approve", by="reviewer-1", body="Honestly, this company is a great "
                                                              "investment and you should take the "
                                                              "allocation.")
    assert out.result is not None and not out.result.allowed
    assert [name for name, _, _ in out.escalations] == [REVIEW_QUEUE]
    assert [t.kind for t in out.touchpoints] == ["identity"]   # denied, so no act and no row
