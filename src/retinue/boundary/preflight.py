"""The review surface's pre-flight: the imported full-lane `pre_tool_use` over the draft - the full
predicate set, checker included, with NO execution. Every draft reaches the reviewer already
annotated with its would-be verdict.

Routing is a TWO-SIGNAL disjunction (spec 6): checker denial OR pre-flight failure (the annotation
errored or produced no verdict). Parity tests are CI checks, not a runtime signal.

**The checker's confidence score deliberately routes nothing, and no field of it is read anywhere
in this module.** The refusal is not for want of the number: the imported engine writes it into the
denial payload as `f"checker confidence {result.confidence}"`, so a third signal is one field
access away, and `test_the_self_rating_is_really_in_the_payload_to_be_routed_on` witnesses it
sitting there. A model's own estimate of how sure it is, is a model output like any other, and a
routing rule built on it would make the boundary's behaviour a function of the thing the boundary
exists to bound.

**Pinned by a census, not by a text search, and this paragraph is the reason.** The tests parse this
module and compare the complete set of names each function touches against a written-out set, so a
read added under ANY name - `certainty`, `score`, a `getattr` through a call, a line moved out into
a helper - changes the census and reddens. A search for the word would have been silent on every
one of those, and would have forbidden this module from naming the thing it refuses to read, which
is the paragraph a later reader most needs. The trade is the one `tools/fleet_audit.py` already
takes for the import rules: a mention is not a read.

**What the census covers is a region, and the region is stated rather than enumerated.** Three
pins compose, and the composition is the claim:

1. the census walks a definition's ENTIRE subtree, so no field of a `def` is outside it - not the
   decorators, not the positional or keyword-only defaults, not the annotations, not a nested
   definition - and every module-level name that subtree touches is followed the same way, whether
   it is bound by a `def` or a `class`;
2. `top_level_bindings` requires each censused name to be bound by its own `def` and by nothing
   else, so the module cannot export a wrapper the census never walked;
3. `module_shape` pins the module's top-level statements exhaustively, so there is no module-level
   statement outside those definitions and their imports.

Together: nothing inside a definition is outside a census, and nothing at module level is outside a
definition. **That claim is the third version of this paragraph.** The first said a census of the
body; a default argument holding a lambda escaped it. The second added decorators and called the
decorator "the" escape found; a default, a read in the class body, and a module-level rebinding all
escaped that, each measured live. Naming the member rather than the region is what made both
versions wrong, so this one names the region and the two edges it does not reach: imported code is
not censused, which is deliberate because the imported engine is exactly what reads the score, and
nothing here is a claim about runtime, where a monkeypatch is not a property of this source.
"""
from __future__ import annotations
from dataclasses import dataclass
from chaperone.gates.hook import HookOutcome, pre_tool_use
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Record
from retinue.boundary.hook import SEND_TOOL

@dataclass(frozen=True)
class Preflight:
    outcome: HookOutcome | None    # None: the annotation itself failed - signal two
    error: str | None

def annotate(draft: Draft, record: Record, context: ActContext, checker) -> Preflight:
    """The would-be verdict, or the report that there is none.

    **Returns rather than raises for every `Exception`, and that is the bound, not "never".**
    `BaseException` is deliberately not caught, for the reason `boundary/hook.py` gives about
    cancellation: a shutdown or an interrupt is not a policy answer, and a reviewer handed
    "the pre-flight failed" for a torn-down process is being told something untrue about the draft.

    **The error text is formatted under its own guard, because formatting is arbitrary code.**
    `f"{exc}"` calls the exception's own `__str__` inside the handler, and a transport wrapping a
    driver or HTTP error whose message renders lazily from a resource that has since closed raises
    there. A raise inside the handler escapes this function, turning the fail-closed signal two
    into exactly the failure this surface exists to prevent. The type name is read first and kept,
    so the fallback still names what went wrong.

    `{"body": draft.body}` is what makes the annotation assess the same object the draft names:
    the imported `_decide_for` refuses any argument outside the reviewed draft's outbound surface,
    so a pre-flight run over some other argument shape would be a denial about the pre-flight
    rather than about the draft.
    """
    try:
        outcome = pre_tool_use(SEND_TOOL, {"body": draft.body}, (draft, record, context, checker))
        return Preflight(outcome, None)
    except Exception as exc:
        named = type(exc).__name__
        try:
            described = f"{named}: {exc}"
        except Exception:
            described = f"{named}: the exception's own message could not be rendered"
        return Preflight(None, described)

def routes_to_human(p: Preflight) -> bool:
    """The two-signal disjunction, and nothing else decides it - not the checker's confidence.

    This sentence is inside the pinned function on purpose. The census drops docstrings, so a
    module that named the field it refuses to read would still have failed a text search, and the
    fact that this one names it here and stays green is what shows the two are different pins.
    """
    if p.outcome is None:
        return True
    return not p.outcome.allow
