"""The approval bridge, driven end to end by the captured ask payload: a human resolution, the
mint, the boundary's validate-and-consume, the gate, the act, the ledger row.

THE FIRST CALLER OF THE CHOKEPOINT THAT IS NOT A TEST. Every other caller of `attempt_send` in
this repository lives under `tests/`, so until this file existed the bridge's end-to-end path was
asserted only by things written to assert it. This script runs offline, keylessly and with no
network, which is why it can be the default lane's own evidence rather than a manual errand.

**The tool body performs no outward act, and that decision is preserved here with its reason.**
`scripts/demo.py` states it for the capture lane: wiring a real transport into a script means the
first execution of the whole assembly is a run nobody has done, and a body that claimed to send
would be a claim about an unexecuted path. The same holds here one layer down. The registry entry
below returns a handle and transmits nothing, and `confirm` reports on THAT inert transport rather
than on any delivery: `CONFIRMED` in this run means the local handle came back, never that a
message reached a person. What the bridge demonstrates is the PATH - which approvals are minted,
which are refused, what is spent, what is gated and what is recorded - and that path is real.

**Nothing is enqueued to stand in for the ask, deliberately.** The plan's sketch has this script
enqueue the held draft, and the review queue holds `Handoff` rows, every one of which carries a
`reason_category` naming what the gate or the boundary concluded. An ask is neither: the hook
answers "ask" and no predicate has refused anything, so a row here would need a category invented
for a demo, in a file that is not the boundary and may not name one. The queue IS wired, and the
one arm that fills it is driven by a test rather than described here. Review row 1 below is the
identity a durable `review_queue` row would carry, and the memory resolution log keys on it exactly
as `PgResolutionLog` keys on a real row id.

**Three spellings of one tool, and they are not interchangeable.** The captured payload names
`mcp__retinue__send_message`, the wire spelling the hook gates. `attempt_send` hands `SEND_TOOL`,
the bare name, to `guarded_call`, and `_decide_for` denies outright when the draft names anything
else. So the DRAFT, the GRANT and the TOKEN'S `tool` binding all carry the bare name, and the
payload's own spelling is read to confirm it is a gated send and then not used as a binding. Minted
against the payload's spelling instead, the token binds a tool the draft does not name and the
boundary refuses it as `approval_unverified` before the gate is ever reached.

Flags: --approve-as NAME / --reject-as NAME resolve without a prompt (tests, CI); with neither, the
held draft prints and the operator answers y/n interactively.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chaperone.audit.gateway import Gateway, GatewayResult
from chaperone.audit.store import AuditStore
from chaperone.policy.types import Draft, Message

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, MemoryResolutionLog,
                                        resolve)
from retinue.boundary.checker_lane import build_checker, scripted_transport
from retinue.boundary.hook import SEND_TOOL, SEND_TOOLS
from retinue.boundary.review_queue import DurableQueues, memory_sink
from retinue.boundary.send_tool import attempt_send
from retinue.ledger.models import Touchpoint
from retinue.ledger.projection import as_policy_record, build_act_context, project_record
from retinue.ledger.store import InMemoryStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "payloads" / "captured_ask.json"
VERDICTS = ROOT / "fixtures" / "verdicts" / "checker_scripted.json"

#: The clock is an argument everywhere below, never a call to now(): the mint, the window, the act
#: and the ledger row all read this one instant, so two runs of this script leave identical rows.
T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)
WINDOW = timedelta(hours=24)
INVESTOR = "inv-demo"          # the counterparty the captured session's own prompt names
MANDATE = "m-demo"
KEY = "bridge-1"               # the act's idempotency key, which no review row can supply
DOMAIN = "example.test"
JURISDICTION = "US"
ROW_ID = 1


@dataclass(frozen=True)
class BridgeOutcome:
    """What the run LEFT BEHIND, so a caller can assert effects rather than read printed words.

    `touchpoints` and `escalations` are read back out of the store and the sink the run actually
    used, never accumulated as the run goes: a counter incremented beside a write says the code
    reached the line, and the ledger row says the ledger holds it.
    """
    row_id: int
    key: str
    draft: Draft
    approvals: MemoryApprovalStore
    resolutions: MemoryResolutionLog
    token: ApprovalToken | None = None
    result: GatewayResult | None = None
    touchpoints: tuple[Touchpoint, ...] = ()
    escalations: list = field(default_factory=list)
    audit_entries: int = 0


def captured() -> tuple[str, str]:
    """The model-authored body and the tool spelling the capture recorded, from the frozen fixture.

    Read rather than retyped, and the whole file is the reason: the body carries a character no
    authored file in this tree may hold, the digest the mint binds is taken over its exact bytes,
    and the frozen verdict row is keyed by the same string. A copy typed here would drift from all
    three at once, and the checker would fail closed on a body nobody could see was different.
    """
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["payload"]
    return payload["tool_input"]["body"], payload["tool_name"]


def seeded_store() -> InMemoryStore:
    """The ledger the projection reads. The identity row is what makes a CONTEXT possible at all.

    `build_act_context` takes the consented jurisdiction from the last `identity` touchpoint, so an
    unseeded store yields an empty consent set and the engine denies every draft on
    `act:jurisdiction_not_consented` - a refusal about missing history rather than about the
    approval this script exists to demonstrate.
    """
    store = InMemoryStore()
    store.append(Touchpoint(idempotency_key="seed-identity", investor_id=INVESTOR,
                            mandate_id=MANDATE, kind="identity",
                            payload={"jurisdiction": JURISDICTION, "domain": DOMAIN},
                            occurred_at=T0, recorded_at=T0))
    return store


def ledger_line(row: Touchpoint) -> str:
    """One recorded touchpoint as the line the demo prints for it.

    A function, and not an f-string inline in `main`, for a reason a mutant measured: on this
    script's own happy path the row's kind is `sent` and its status is `CONFIRMED`, so a line
    built from three literals prints exactly what a line built from the row prints, and no
    assertion over this script's output can tell them apart. Lifted out, it can be handed a row
    that says something else - which is the only way to show the line reports the ledger.
    """
    return (f"ledger row: kind={row.kind} delivery={row.delivery_status} "
            f"body_bytes={row.payload['body_bytes']}")


def bridge_run(*, verdict: str, by: str, body: str | None = None) -> BridgeOutcome:
    """One resolution carried to whatever it earns, with every store returned for inspection.

    Split out of `main` for the reason `outcome_after_read` is split out of the resolve CLI's
    `main`: the printing and the exit code are one concern and the effects are another, and only
    the second can be asserted as a property. `main` below adds nothing but words and a number.
    """
    captured_body, payload_tool = captured()
    body = captured_body if body is None else body
    draft = Draft(thread=(Message(role="investor", body="hello"),), body=body, cited_fields=(),
                  recipient_jurisdiction=JURISDICTION, recipient_domain=DOMAIN,
                  tool_name=SEND_TOOL)
    approvals, resolutions = MemoryApprovalStore(), MemoryResolutionLog()
    base = BridgeOutcome(row_id=ROW_ID, key=KEY, draft=draft, approvals=approvals,
                         resolutions=resolutions)

    # The payload's own spelling is checked and then deliberately not bound; see the module
    # docstring. A capture naming something the hook never gated would make this whole run a
    # demonstration of an act nobody holds, so it is an assertion rather than a comment.
    assert payload_tool in SEND_TOOLS, f"the captured payload names {payload_tool!r}, which is no gated send"

    token = resolve(row_id=ROW_ID, verdict=verdict, at=T0, approved_by=by, window=WINDOW,
                    resolutions=resolutions, approvals=approvals, key=KEY, body=body,
                    tool=SEND_TOOL, recipient_domain=DOMAIN)
    store = seeded_store()
    if token is None:
        return BridgeOutcome(**{**base.__dict__, "touchpoints": store.touchpoints_for(INVESTOR)})

    sink, rows = memory_sink()
    context = build_act_context(store, INVESTOR, granted_tools=frozenset({SEND_TOOL}), tier=2,
                                send_cap=5, approval_token=token.token)
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "audit.jsonl"
        result = attempt_send(
            key=KEY, draft=draft, record=as_policy_record(project_record(store, INVESTOR)),
            context=context, checker=build_checker(scripted_transport(VERDICTS)),
            gateway=Gateway(AuditStore(log), principal="retinue", tier=2),
            # The inert act, and the module docstring carries its reason: a handle, and no
            # transport behind it.
            registry={SEND_TOOL: lambda **a: "handle-1"},
            queues=DurableQueues(sink, now=lambda: T0), store=store, approvals=approvals,
            investor_id=INVESTOR, mandate_id=MANDATE, occurred_at=T0, recorded_at=T0,
            confirm=lambda handle: True)
        entries = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0

    return BridgeOutcome(**{**base.__dict__, "token": token, "result": result,
                            "touchpoints": store.touchpoints_for(INVESTOR), "escalations": rows,
                            "audit_entries": entries})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python scripts/bridge.py")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--approve-as", metavar="NAME")
    group.add_argument("--reject-as", metavar="NAME")
    args = ap.parse_args(argv)

    body, payload_tool = captured()
    print("bridge: the captured ask, carried through the chokepoint by one human resolution")
    print(f"  payload tool    : {payload_tool}")
    print(f"  chokepoint tool : {SEND_TOOL}")
    # The body prints as its JSON literal, the form the fixture itself ships. A raw print of the
    # true character raises UnicodeEncodeError on a console using a legacy code page, which would
    # end the demo on the one line whose whole point is that the bytes are carried faithfully.
    print(f"  body            : {json.dumps(body)}")
    print(f"  held for a human as review row {ROW_ID}")

    if args.approve_as or args.reject_as:
        by = args.approve_as or args.reject_as
        verdict = "approve" if args.approve_as else "reject"
    else:
        try:
            answer = input("approve this draft? [y/N] ").strip().lower()
        except EOFError:
            print("no verdict: this run has no operator and neither flag was given")
            return 2
        by, verdict = "operator", ("approve" if answer in ("y", "yes") else "reject")

    out = bridge_run(verdict=verdict, by=by)
    if out.token is None:
        print(f"{verdict}ed by {by}: no token was minted, and the chokepoint is never reached")
        return 1

    print(f"resolved by {by}; token {out.token.token} expires {out.token.expires_at.isoformat()}")
    print(f"decision: {'allowed' if out.result is not None and out.result.allowed else 'denied'}")
    # Read back FROM THE STORE, never from the local draft: a byte count printed from the variable
    # the act was built out of says what this script meant to record, and the ledger is what it did.
    for row in out.touchpoints:
        if row.kind == "sent":
            print(ledger_line(row))
    print(f"review queue: {len(out.escalations)} escalation(s); audit log: {out.audit_entries} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
