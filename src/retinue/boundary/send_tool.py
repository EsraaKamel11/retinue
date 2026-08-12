"""The chokepoint wiring. The checker runs HERE, inside the send-tool body, never in the hook.

The order inside attempt_send is load-bearing (spec 6):
1. TERMINAL guard, BEFORE input validation - validation-first returns a readable error the model
   can correct and resubmit, a real second act; this ordering catches the duplicate act, the
   ledger's idempotency key merely catches the duplicate row.
2. Input validation.
3. Boundary pre-check - a None context denies with the boundary-level class
   `projection_unavailable` and `guarded_call` is never reached: no context is fabricated, the
   policy engine never runs on invented values, and the denial never masquerades as a policy
   judgment (spec 5.2). The class is deliberately NOT a policy ViolationClass: this repo adds no
   policy code.
4. The imported `guarded_call` - engine + checker at the chokepoint; denials terminal via the
   imported Handoff; no resume round-trip.
5. The sent touchpoint, tri-state - an unconfirmable send is UNVERIFIABLE and escalates; never
   guessed CONFIRMED. The payload carries byte counts, not text: message bodies live in the
   review queue's Handoff, never in the ledger.
6. The record-keeping check, on the same call that made the act. `store.append` is declared
   `-> bool` and the store contract already pins False as "dropped" for both implementations, so
   this reads an answer the ledger was already giving.

**Reading that boolean closes THREE paths at once, and it closes them BECAUSE IT DOES NOT CARE WHY
the row was dropped.** Narrowing it back to any one of them reopens the other two:
- a key already held by a touchpoint of another KIND, which the step 1 guard lets past because it
  matches `key AND kind == "sent"` while both stores dedupe on the key alone;
- a key already held by another INVESTOR, which needs no cross-kind key at all: the guard is
  investor-scoped and the key namespace is global (`idempotency_key TEXT PRIMARY KEY`, and
  `test_idempotency_keys_are_globally_unique_not_per_investor` pins exactly that);
- a store that RAISES instead of answering, the Postgres lane's shape, which used to leave by a
  different door entirely, propagating out after the act with nothing escalated.

**Prevention is available and is refused, and the reason is not that the store lacks an API.** An
earlier revision argued that, and it is defeasible in one step: `append`'s boolean is ALREADY a
key-global test-and-set, so claiming the key before the act needs no new store method at all, and
claiming first would refuse the cross-kind and cross-investor paths before the message leaves.

The reason is that a claim row could never be resolved. The store is append-only with no update
(`INSERT ... ON CONFLICT DO NOTHING` and nothing else), the key is globally unique, and
`DeliveryStatus` has no pending member. Measured: append a claim row, then append the same key
carrying `CONFIRMED`, and the second call returns False with the stored row still at
`delivery_status=None`. Claim-first would therefore trade the tri-state away for prevention on two
of four paths, and the tri-state is the thing that keeps an unconfirmable send from being guessed
CONFIRMED. It is also TOCTOU-racy, and it cannot reach the raising-store path at all.

So detection, and the guarantee is that an unrecorded act is NEVER REPORTED AS A CLEAN ALLOW AND
NEVER SILENT. Left unread, the failure was unbounded rather than off by one: no row is written, so
the guard finds none on the next attempt either, and the key becomes a reusable, unmetered send
licence. Two acts, no meter, measured.

**Why an unrecorded act comes back as a distinct TYPE and not as a raise.** A raise after an
irreversible act is design spec 3.4's named trap aimed at the worst possible target: a
defensively-written executor wraps handler invocation in a catch-all, the exception reaches the
agent relabelled "transient, please retry", and the retry re-enters this function, where the guard
finds no `sent` row FOR EXACTLY THE REASON WE ARE HERE and the message goes out a second time. The
cost of a raise is therefore a duplicate message to an investor, where the cost of a silent allow
is only a miscounted cap. `UnrecordedSend` is neither. It carries no `allowed` attribute, and that
is deliberate: `True` is the state being distinguished from, `False` would say nothing was sent and
invite the same re-send, and neither is honest about a call the gate allowed and the ledger lost.
`None` was not available for it either: that already means denied at the pre-check with the engine
never run.

**What the type buys is that every duplicate is escalated, and it does NOT buy "never sent
twice".** `out.allowed` raises loudly, as designed. The defensive idiom `getattr(out, "allowed",
False)` does not: it answers False, which reads as a denial and drives a retry loop. Measured, a
caller retrying on that falsy answer makes three tool calls, writes zero rows, and files THREE
escalations. Nothing here runs a type checker either, so the return union is enforced by no tool.
The guarantee that survives all of that is the one worth stating: no duplicate is silent, and a
human holds one work item per act. That is what this type earns.

**No "already escalated" marker on the type, deliberately.** Every `UnrecordedSend` is constructed
one line after the `put` that files its escalation, and there is no path that builds one without
filing, so such a field would be a constant True, and a field that is always True is a field a
later reader eventually sets to False. A conscientious caller filing a second escalation costs a
duplicate work item carrying the same class and the same body, which a human resolves; the failure
this module is built against is the missing one, which nobody can.

**`Gateway.log_torn` is read here by nobody, and that is a decision rather than an oversight.**
The imported gateway surfaces it and says why: the send cap counts intents, a tear may have taken
one, and a cap check reading the count alone would then permit one send too many. That warning is
addressed to a caller whose cap reads the AUDIT LOG, and this repository has no such caller.
`build_act_context` in ledger/projection.py fills `ActContext.sent_count` from the ledger's own
`sent` touchpoints, and `Gateway.sent_count` is called nowhere here. So the input the gateway
declines to hide is an input this chokepoint's cap does not consume, and a refusal keyed on it
here would be a policy decision taken at the wrong layer over a count nothing reads. The right
home, on the day anything in this tree counts intents off the log, is `build_act_context`, beside
the count itself, where a torn log and a short count arrive together.

The step 6 check above is the LEDGER's instance of the same hazard, and it is this chokepoint's
because this chokepoint is what creates it. An earlier revision of this file deferred it as a
store-contract change; that was wrong twice over. The store had already contracted the answer and
already tested it, and the chokepoint is the only place the answer can be read.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from chaperone.audit.gateway import Gateway, GatewayResult
from chaperone.gates.handoff import Handoff
from chaperone.gates.hook import guarded_call
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Record
from retinue.boundary.hook import SEND_TOOL
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import TouchpointStore

PROJECTION_UNAVAILABLE = "boundary:projection_unavailable"
DELIVERY_UNVERIFIABLE = "boundary:delivery_unverifiable"
#: The act happened and the ledger has no record of it. Boundary-level like the two above and for
#: the same reason: no policy predicate ran and none failed, so this may not wear a ViolationClass.
SEND_UNRECORDED = "boundary:send_unrecorded"
REVIEW_QUEUE = "human-review"   # the imported destination_for's one queue name (gates/engine.py);
                                # spelled here because engine sits outside the 6.1 import surface.
                                # Double entry:
                                # test_the_boundary_queue_is_the_imported_engines_own_destination
                                # holds this against destination_for's own answer, because nothing
                                # else in the suite reads the name a routed row landed under.

class TerminalSend(Exception):
    """This idempotency key already produced an act. Refused before validation, by design."""

class InvalidSend(Exception): ...

@dataclass(frozen=True)
class UnrecordedSend:
    """The message left and the ledger has no record of it. Deliberately NOT a `GatewayResult`.

    The module docstring carries the reasoning; the shape is the point. `result` is the real
    gateway answer, so a caller that needs the handle or the audit sequence still has both, and
    `reason` is why the row was dropped, in the store's own terms rather than this module's guess.

    No `allowed` attribute. See the docstring: a caller duck-typing it gets an AttributeError at
    its own call site, which is the loud failure, and every boolean that could sit there is a lie
    in one direction or the other.
    """
    result: GatewayResult
    reason: str

def _boundary_handoff(draft: Draft, category: str, outage: str | None) -> Handoff:
    return Handoff(reason_category=category, detector_outage=outage,
                   violating_span="", blocked_body=draft.body,
                   recipient_domain=draft.recipient_domain,
                   recipient_jurisdiction=draft.recipient_jurisdiction,
                   cited_field_values={}, thread_excerpt="", proposed_alternative=None,
                   refinement_rounds=0)

def attempt_send(*, key: str, draft: Draft, record: Record, context: ActContext | None,
                 checker, gateway: Gateway, registry: Mapping[str, object], queues,
                 store: TouchpointStore, investor_id: str, mandate_id: str | None,
                 occurred_at: datetime, recorded_at: datetime,
                 confirm: Callable[[object], bool | None],
                 ) -> GatewayResult | UnrecordedSend | None:
    if any(t.idempotency_key == key and t.kind == "sent"
           for t in store.touchpoints_for(investor_id)):
        raise TerminalSend(f"idempotency key {key!r} already produced an act")
    if not draft.body.strip():
        raise InvalidSend("empty draft body")
    if context is None:
        queues.put(REVIEW_QUEUE, _boundary_handoff(
            draft, PROJECTION_UNAVAILABLE,
            "the relationship projection could not be read; no context was fabricated and the "
            "policy engine never ran"))
        return None
    result = guarded_call(gateway, SEND_TOOL, {"body": draft.body}, draft, record,
                          context, checker, registry, queues=queues)
    if result.allowed:
        # Bound BEFORE the guarded region, to the state that is true when nothing has answered.
        # This is the answer and not a placeholder: `confirm` is a transport round-trip and one
        # that raises IS the definition of an unconfirmable send, so the delivery state it leaves
        # behind is exactly the one the tri-state already has a name for.
        status = "UNVERIFIABLE"
        # `confirm` is INSIDE, and it is here rather than one line above because it was one line
        # above: a raising `confirm` left the act done, no row written, nothing escalated and
        # nothing queued, which is path three's shape sitting immediately in front of path three's
        # repair. The guarded region is drawn around every step between the act and the recorded
        # row, so no step can be added between them that is outside it.
        #
        # `Exception` and not `BaseException`, matching boundary/hook.py: a cancellation or a
        # SystemExit must still propagate. Anything narrower would enumerate the ways recording can
        # fail, and the whole point of this branch is that it does not care which one. The row is
        # BUILT inside as well, so a payload pydantic refuses is the same event as a store that
        # will not take it: either way the act happened and the ledger has no row.
        try:
            confirmed = confirm(result.value)
            status = ("CONFIRMED" if confirmed is True
                      else "FAILED" if confirmed is False else "UNVERIFIABLE")
            recorded = store.append(Touchpoint(
                idempotency_key=key, investor_id=investor_id, mandate_id=mandate_id, kind="sent",
                payload={"body_bytes": len(draft.body.encode())},
                occurred_at=occurred_at, recorded_at=recorded_at, delivery_status=status))
            dropped = None if recorded else f"the ledger already holds the key {key!r}"
        except Exception as exc:
            # Names the STAGE, not an actor. "the store raised" was wrong for two of the three
            # things this catches: a confirmation round-trip and a row pydantic refuses both reach
            # a human reviewer before the store is touched at all.
            dropped = f"recording the act for key {key!r} raised {type(exc).__name__}: {exc}"
        if status == "UNVERIFIABLE":
            queues.put(REVIEW_QUEUE, _boundary_handoff(draft, DELIVERY_UNVERIFIABLE, None))
        if dropped is not None:
            # Both escalations fire when both are true; they are different facts about one send.
            # `detector_outage` carries the reason for the same purpose the pre-check above uses it
            # for: at a boundary class it is this module's slot for why the normal path did not
            # complete, and the imported consumers only ever read it against a policy `other`.
            queues.put(REVIEW_QUEUE, _boundary_handoff(
                draft, SEND_UNRECORDED,
                f"the message left and the ledger has no record of it; {dropped}"))
            return UnrecordedSend(result=result, reason=dropped)
    return result
