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

**`Gateway.log_torn` is read here by nobody, and that is a decision rather than an oversight.**
The imported gateway surfaces it and says why: the send cap counts intents, a tear may have taken
one, and a cap check reading the count alone would then permit one send too many. That warning is
addressed to a caller whose cap reads the AUDIT LOG, and this repository has no such caller.
`build_act_context` in ledger/projection.py fills `ActContext.sent_count` from the ledger's own
`sent` touchpoints, and `Gateway.sent_count` is called nowhere here. So the input the gateway
declines to hide is an input this chokepoint's cap does not consume, and a refusal keyed on it
here would be a policy decision taken at the wrong layer over a count nothing reads. The right
home, on the day anything in this tree counts intents off the log, is `build_act_context`, beside
the count itself, where a torn log and a short count arrive together. The related defect this
chokepoint DOES sit on is recorded in the task report rather than repaired here: the terminal
guard matches on `key AND kind == "sent"` while both stores dedupe on the key alone, so a key
already held by a touchpoint of another kind passes the guard and then loses its `sent` row to
`append` returning False, which under-counts the ledger cap in exactly the shape the gateway
describes. Widening the guard trades that for spurious refusals and is a store-contract change,
not a chokepoint one.
"""
from __future__ import annotations
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
REVIEW_QUEUE = "human-review"   # the imported destination_for's one queue name (gates/engine.py);
                                # spelled here because engine sits outside the 6.1 import surface.
                                # Double entry:
                                # test_the_boundary_queue_is_the_imported_engines_own_destination
                                # holds this against destination_for's own answer, because nothing
                                # else in the suite reads the name a routed row landed under.

class TerminalSend(Exception):
    """This idempotency key already produced an act. Refused before validation, by design."""

class InvalidSend(Exception): ...

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
                 confirm: Callable[[object], bool | None]) -> GatewayResult | None:
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
        confirmed = confirm(result.value)
        status = ("CONFIRMED" if confirmed is True
                  else "FAILED" if confirmed is False else "UNVERIFIABLE")
        store.append(Touchpoint(
            idempotency_key=key, investor_id=investor_id, mandate_id=mandate_id, kind="sent",
            payload={"body_bytes": len(draft.body.encode())},
            occurred_at=occurred_at, recorded_at=recorded_at, delivery_status=status))
        if status == "UNVERIFIABLE":
            queues.put(REVIEW_QUEUE, _boundary_handoff(draft, DELIVERY_UNVERIFIABLE, None))
    return result
