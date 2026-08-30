"""The pre-check's position and its burn rule. These tests drive attempt_send with the same
scripted transports and inert gateway the existing send-tool tests use; read those fixtures
first and reuse their helpers rather than re-authoring doubles (tests/boundary/test_hook.py and
the existing attempt_send tests are the pattern).

So the five integration tests below IMPORT `harness`, `ctx` and `draft` from `test_send_tool.py`
rather than re-authoring them. A second copy of the chokepoint's wiring would drift from the
first, and what these tests are about is where one step sits inside that one wiring, which a
different wiring cannot show.

`ctx` is called with `approval_token` and `tier` spelled at every call site here and never taken
from its defaults. Those defaults belong to the file that owns them, and this file's whole
subject is what the chokepoint does at each of their values: reading them would turn every test
here into a restatement of a fixture instead of a statement about the code.

EFFECTS, never invocations, and three of them carry these tests:

- the review queue's rows, read back as the categories that actually landed in it;
- the ledger's `sent` touchpoints;
- the AUDIT LOG's existence on disk. `Gateway.call` appends an intent entry and an outcome entry
  to `tmp_path/audit.jsonl` on every call it makes, allowed or denied, and `AuditStore` creates
  the parent directory but never the file. So an absent file is the effect that says
  `guarded_call` was never entered, measured on the gate rather than on a double: a spy counting
  calls would only ever report on the spy.
"""
from datetime import datetime, timedelta, timezone

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, body_digest_of,
                                        validate_and_consume)

from chaperone.policy.types import Record, ViolationClass
from retinue.boundary.hook import SEND_TOOL
from retinue.boundary.send_tool import (APPROVAL_UNVERIFIED, PROJECTION_UNAVAILABLE, attempt_send)
from test_send_tool import ctx, draft as send_draft, harness

T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)


def minted(body, *, key="k-1", tool="mcp__retinue__send_message", domain="example.test",
           tok="a" * 32, hours=24):
    t = ApprovalToken(token=tok, idempotency_key=key, body_digest=body_digest_of(body),
                      tool=tool, recipient_domain=domain, resolution_id=1, minted_at=T0,
                      expires_at=T0 + timedelta(hours=hours))
    s = MemoryApprovalStore()
    assert s.put_token(t)
    return s


def test_a_valid_token_validates_and_is_consumed_exactly_once(draft_factory):
    d = draft_factory(body="hello")
    s = minted("hello")
    assert validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s) is None
    reason = validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
    assert reason is not None and "consum" in reason


def test_every_binding_leg_refuses_and_names_itself(draft_factory):
    d = draft_factory(body="hello")
    for kwargs, needle in [
        (dict(token="b" * 32), "minted"),                      # absent from the store
        (dict(key="k-OTHER"), "idempotency"),                  # re-aimed at a different act
        (dict(at=T0 + timedelta(hours=25)), "expire"),         # expired
    ]:
        s = minted("hello")
        call = dict(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
        call.update(kwargs)
        reason = validate_and_consume(**call)
        assert reason is not None and needle in reason


def test_a_changed_body_or_tool_or_domain_refuses(draft_factory):
    for change in [dict(body="tampered"), dict(tool_name="other_tool"),
                   dict(recipient_domain="elsewhere.test")]:
        d = draft_factory(body="hello", **{k: v for k, v in change.items() if k != "body"})
        if "body" in change:
            d = draft_factory(body=change["body"])
        s = minted("hello")
        reason = validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s)
        assert reason is not None


def test_a_binding_failure_does_not_burn_the_token(draft_factory):
    # Reads before the write: a mis-aimed attempt must not spend a token someone else earned.
    d = draft_factory(body="hello")
    s = minted("hello")
    assert validate_and_consume(token="a" * 32, key="k-OTHER", draft=d, at=T0, store=s)
    assert validate_and_consume(token="a" * 32, key="k-1", draft=d, at=T0, store=s) is None


#: A body the frozen verdict fixture covers and CLEARS, so the gate's answer on it is an allow and
#: anything that stops the call short of an allow stopped it before the gate.
CLEAN = "Following up on our conversation."
#: A body the same fixture covers and DENIES, on a content class. The gate answering at all is what
#: says the pre-check let the call through, which is why this file needs a denial it can recognise.
DENIED = "Honestly, this company is a great investment and you should take the allocation."


def approved(tmp_path, *, key, body, token="a" * 32, hours=24):
    """The send-tool harness wound onto this file's clock, plus a store holding one bound token.

    `occurred_at` is overridden because the chokepoint hands it to `validate_and_consume` as the
    clock, and the send-tool harness's own instant sits four months after the mint helper above
    stamps `minted_at`. Which instant a fixture picks is not a property of anything, so the harness
    moves onto this file's `T0` and the brief's mint helper stays usable unchanged.
    """
    kw, rows = harness(tmp_path)
    store = minted(body, key=key, tool=SEND_TOOL, tok=token, hours=hours)
    kw.update(occurred_at=T0, recorded_at=T0, approvals=store)
    return kw, rows, store


def test_missing_context_still_denies_as_projection_unavailable_even_with_a_token(tmp_path):
    """Position, upper edge. A missing context is the more fundamental absence and answers first.

    Hoist the new pre-check above the projection one and this reddens on the spot, because
    `context` is None there and `None.approval_token` raises. That crash is the measured red
    recorded for this test, and it is also the reason the order is not merely a preference: a
    pre-check reaching for a field on a context that does not exist has nothing to check.

    The last assertion is the one that survives a pre-check rewritten to TOLERATE a None context
    rather than crash on it. A token spent on a call the projection refused is an approval the
    human who gave it cannot get back, and the queue row would say `projection_unavailable` while
    the approval was quietly gone.
    """
    kw, rows, store = approved(tmp_path, key="a1", body=CLEAN)
    out = attempt_send(key="a1", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=None, confirm=lambda v: True, **kw)
    assert out is None
    assert [r[1]["reason_category"] for r in rows] == [PROJECTION_UNAVAILABLE]
    assert validate_and_consume(token="a" * 32, key="a1", draft=send_draft(body=CLEAN),
                                at=T0, store=store) is None


def test_a_supplied_token_with_no_store_is_unverifiable_and_stops_before_the_gate(tmp_path):
    """Presence alone is not verification, which is the hole the whole bridge exists to close.

    `approvals` is left off the call deliberately. A chokepoint that skipped the check whenever no
    store was wired would answer an ALLOW here, and every caller that forgot to wire one would be
    back to an approval token that is a type check: any non-None string standing in for a human.
    Fail closed, so the missing store is a refusal a reviewer sees rather than a silence.
    """
    kw, rows = harness(tmp_path)
    kw.update(occurred_at=T0, recorded_at=T0)              # no `approvals`, deliberately
    out = attempt_send(key="a2", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    assert out is None
    assert [r[1]["reason_category"] for r in rows] == [APPROVAL_UNVERIFIED]
    assert rows[0][1]["detector_outage"]                   # the reviewer is told which leg failed
    assert not (tmp_path / "audit.jsonl").exists()         # the gate was never entered
    assert kw["store"].touchpoints_for("inv-1") == ()


def test_an_invalid_token_stops_before_the_gate_with_the_boundary_class(tmp_path):
    """Position, lower edge: the boundary answers a mis-bound token and the gate never sees it.

    The audit log is the assertion that names the position. Without it this test passes on a
    pre-check placed AFTER `guarded_call`, because the queue would still receive the boundary class
    and the ledger would still hold no row - the gate would simply have run first, and the imported
    presence check would have been handed a token nothing had verified.
    """
    kw, rows, store = approved(tmp_path, key="a-OTHER", body=CLEAN)
    out = attempt_send(key="a3", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    assert out is None
    assert [r[1]["reason_category"] for r in rows] == [APPROVAL_UNVERIFIED]
    assert "idempotency" in rows[0][1]["detector_outage"]
    assert not (tmp_path / "audit.jsonl").exists()
    assert kw["store"].touchpoints_for("inv-1") == ()
    # And it spent nothing: the approval is still there for the act it was actually minted for.
    assert validate_and_consume(token="a" * 32, key="a-OTHER", draft=send_draft(body=CLEAN),
                                at=T0, store=store) is None


def test_a_valid_token_reaches_the_gate_and_a_gate_denial_burns_it(tmp_path):
    """The burn rule the spec argues as a feature, read off the store afterwards.

    A human approved ONE attempt at one body. The gate then refusing that act earns a fresh look
    and a fresh resolution, not a free retry riding the old approval, so the token is spent at the
    pre-check and stays spent through the denial.

    `out.allowed` being False rather than `out` being None is what says the pre-check passed: the
    pre-check's own refusal returns None and `guarded_call` has no None return, so a denied result
    can only have come from the gate. The audit log is the second half of that, on disk.
    """
    kw, rows, store = approved(tmp_path, key="a4", body=DENIED)
    out = attempt_send(key="a4", draft=send_draft(body=DENIED), record=Record(fields={}),
                       context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    assert out is not None and not out.allowed
    assert (tmp_path / "audit.jsonl").exists()             # the gate was entered
    assert APPROVAL_UNVERIFIED not in {r[1]["reason_category"] for r in rows}
    assert kw["store"].touchpoints_for("inv-1") == ()      # denied, so no act and no sent row
    spent = validate_and_consume(token="a" * 32, key="a4", draft=send_draft(body=DENIED),
                                 at=T0, store=store)
    assert spent is not None and "consum" in spent


def test_a_valid_token_carries_a_tier_2_act_to_an_allowed_confirmed_recorded_send(tmp_path):
    """The arm the whole bridge exists to ENABLE, and every other test at this level is a refusal.

    Stated precisely, because the obvious phrasing is wrong. This is not coverage the `ctx()` move
    displaced: the old fixture's tier-2 allow ran on `"tok-1"`, a string nothing minted, past a
    check that only asked whether it was non-None, so a VERIFIED-token allow was never asserted
    anywhere in this suite. The refusal paths moved into this file; this path had no predecessor.

    What is unique here is not the refusal it would catch but the EFFECTS it asserts. Inverting the
    pre-check's terminal condition, so a fully valid token is treated as unverified, reddens this
    test at `assert out is not None and out.allowed` and reddens four siblings with it - measured,
    and recorded that way rather than as a sole-catcher claim, which the same run refuted. What no
    other test at this level reaches is what an APPROVED act leaves behind: every other integration
    test in this file ends in a refusal, and the one other test that carries a valid token through
    the pre-check drives a body the gate denies, so it asserts an empty ledger by design.

    All of a bridged approval's effects, in one act: the gate allowed it, the tool ran, the ledger
    holds exactly one CONFIRMED `sent` row, nothing was escalated, and the approval is spent.
    """
    kw, rows, store = approved(tmp_path, key="a8", body=CLEAN)
    out = attempt_send(key="a8", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    assert out is not None and out.allowed
    touchpoints = kw["store"].touchpoints_for("inv-1")
    assert [t.kind for t in touchpoints] == ["sent"]
    assert touchpoints[0].delivery_status == "CONFIRMED"
    assert rows == []                                      # an approved clean send escalates nothing
    spent = validate_and_consume(token="a" * 32, key="a8", draft=send_draft(body=CLEAN),
                                 at=T0, store=store)
    assert spent is not None and "consum" in spent         # and the approval was spent, exactly once


def test_the_new_boundary_class_is_no_policy_class_at_all(tmp_path):
    """Read off what LANDED, never off the constant, because that is how this defect recurs here.

    Every other assertion in this file compares `payload["reason_category"]` against the imported
    `APPROVAL_UNVERIFIED`, so BOTH SIDES OF THAT COMPARISON MOVE TOGETHER: renamed to
    `content:negotiates_terms`, a boundary refusal would report a content class no detector ran and
    every one of them would stay green. `test_send_tool.py` records that exact slip happening twice
    already, once per constant added, and names the cause - a per-constant test has to be remembered
    on the day a constant is added. Its own three-path sweep enumerates its harnesses, so it does
    not reach this fourth path; this row is that path's arm of the same control.

    Derived from the imported enum rather than listed, for the reason the engine derives its own
    class families: a member added upstream joins this check with no edit here.
    """
    kw, rows, _ = approved(tmp_path, key="a-OTHER", body=CLEAN)
    attempt_send(key="a6", draft=send_draft(body=CLEAN), record=Record(fields={}),
                 context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    landed = {r[1]["reason_category"] for r in rows}
    assert landed == {APPROVAL_UNVERIFIED}
    assert not landed & {member.value for member in ViolationClass}
    assert all(category.startswith("boundary:") for category in landed)


def test_expiry_is_judged_against_when_the_act_occurred_not_when_it_was_recorded(tmp_path):
    """WHICH of the chokepoint's two clocks the pre-check hands the validator, on a DISTINCT pair.

    `approved` gives `occurred_at` and `recorded_at` the same instant, as the send-tool harness
    does, so `at=recorded_at` is a silent mutation everywhere else in this file and the choice would
    rest on nothing. Bitemporality is why it matters rather than tidiness, and the store contract
    already pins the two apart: `occurred_at` is when the act is true in the world, `recorded_at` is
    when the system learned it, and an approval's window is a window on the ACT - not on the
    bookkeeping that may catch up to it hours later, which would revive an expired approval.
    """
    kw, rows, _ = approved(tmp_path, key="a7", body=CLEAN, hours=24)
    kw.update(occurred_at=T0 + timedelta(hours=25), recorded_at=T0)
    out = attempt_send(key="a7", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=ctx(approval_token="a" * 32, tier=2), confirm=lambda v: True, **kw)
    assert out is None
    assert [r[1]["reason_category"] for r in rows] == [APPROVAL_UNVERIFIED]
    assert "expire" in rows[0][1]["detector_outage"]
    assert not (tmp_path / "audit.jsonl").exists()


def test_no_token_at_all_behaves_exactly_as_today(tmp_path):
    """The guarantee the spec says is unchanged, pinned here so a change to it cannot be silent.

    A store IS wired and a token IS minted, and neither is consulted, because the context carries
    no token to verify. The denial therefore comes from the imported presence check at tier 2 and
    wears the imported class, exactly as it did before this task existed.

    The category is derived from the imported enum rather than spelled, so it moves with the
    library. The last assertion is what refuses a pre-check that fired on an ABSENT token and
    burned the wired store's approval on a call that was never bound to it.
    """
    kw, rows, store = approved(tmp_path, key="a5", body=CLEAN)
    out = attempt_send(key="a5", draft=send_draft(body=CLEAN), record=Record(fields={}),
                       context=ctx(approval_token=None, tier=2), confirm=lambda v: True, **kw)
    assert out is not None and not out.allowed
    assert [r[1]["reason_category"] for r in rows] == [ViolationClass.NO_APPROVAL_TOKEN.value]
    assert kw["store"].touchpoints_for("inv-1") == ()
    assert validate_and_consume(token="a" * 32, key="a5", draft=send_draft(body=CLEAN),
                                at=T0, store=store) is None
