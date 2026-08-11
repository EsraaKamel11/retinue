"""The block-stripped control (spec 7.1). The most-trusted component gets the containment
treatment: re-ask ONLY the questions whose answers depend on block-only fields, against a context
with the block stripped. At least one must fail - and a control that passes proves the stripper
silently did nothing, which is why an absent header RAISES instead of no-op'ing. The stripper
matches the exact header, which is why the header is a machine-checked contract.

"At least one must fail" is the spec's sentence, kept verbatim in the test that carries it, and it
is not on its own a sufficient check of itself: a strip that stopped part way leaves the later
facts standing and still makes one question fail, and a strip that deleted the rest of the prompt
makes all three fail for a reason having nothing to do with the block. Both were run;
`test_the_strip_removes_the_whole_block_and_only_the_block` is what closes them. Neither test
subsumes the other, and that was run too rather than assumed: emptying `BLOCK_ONLY_FIELDS` reddens
the spec's test alone, because asking no questions makes the stronger one vacuously true.
"""
from __future__ import annotations
from retinue.ledger.block import BLOCK_HEADER

BLOCK_ONLY_FIELDS = ("stated_check_size", "pass_reason", "last_contact")

def strip_block(prompt: str) -> str:
    """Remove the block, or raise if there is none to remove.

    COUPLING, load-bearing: this terminates at the block's end only because `render_block` emits
    no internal blank line and exactly one trailing newline, so the first blank line after the
    header IS the block's boundary. A blank line inside the rendering breaks that, and it breaks
    it two DIFFERENT ways depending on where it falls - both run rather than argued:

    - directly after the header, this strips the header alone and every field line survives, so
      no block question goes unanswered and the control reddens. Caught, loudly.
    - anywhere further down, this truncates there and the fields BELOW it survive. One question
      still goes unanswered, so "at least one fails" stays green over a context that still holds
      the rest of the block. Not caught by that assertion, which is why the exact-equality test
      exists alongside it.

    The same truncation is reachable from the data side without anyone editing this code, since a
    field value ending in or containing a newline renders a blank line inside the block. That is
    shut at the producer: `render_block` raises `BlockValueUnrenderable` rather than rendering
    such a value, so the shape this function depends on cannot be broken by a stored string.
    """
    if BLOCK_HEADER not in prompt:
        raise ValueError("no rendered block in this prompt; the control has nothing to strip")
    head, _, rest = prompt.partition(BLOCK_HEADER)
    _, sep, tail = rest.partition("\n\n")
    return head + tail if sep else head

def answer_from(prompt: str, field: str) -> str | None:
    """The deterministic specialist stand-in: answers a block question only if the block line is
    present. A FunctionModel reading its messages does the same thing with more moving parts; the
    protocol being demonstrated (7.2) is identical.

    The FIRST matching line wins, so a forged earlier line would be read back INSTEAD of the real
    value - a fabricated answer rather than a missing one, which is the worse of the two failures
    and the one a control looking for absences would never notice. Nothing here defends against
    that, on purpose: the defence belongs at the producer, and `render_block` refuses any value
    carrying a break that `splitlines` recognises. That guard is written as the same `splitlines`
    this reader uses, and deliberately not as a search for the two breaks a developer thinks of
    first: narrowing it to those two renders eight characters that forge a line here, each of
    which reaches a stored reason through an ordinary JSON round trip. Recorded as a mutation row
    rather than left as a warning.
    """
    for line in prompt.splitlines():
        if line.startswith(f"{field}: "):
            return line.split(": ", 1)[1]
    return None
