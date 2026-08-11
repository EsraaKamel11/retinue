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

#: The questions whose answers live ONLY in the block. Curated, and deliberately not derived from
#: the rendered labels: `investor`, `jurisdiction` and `domain` are excluded because the
#: specialist this control stands in for can answer them from the surrounding prompt and from what
#: it already knows about the party, so asking them would be asking questions the block is not the
#: only source for, and a control that scored those would report the block load-bearing for facts
#: it does not carry alone.
#:
#: That reasoning is about the specialist, NOT about `answer_from`, and the difference was run: a
#: list derived from all six rendered labels passes both control tests today, because this reader
#: only ever matches `label: ` lines and the surrounding prose is not one. So the curation buys
#: nothing against the current reader and everything against the eventual one - which is exactly
#: the kind of distinction that disappears if it is not written down, leaving the next reader to
#: "simplify" a hand-written list into a derived one. `BLOCK_ONLY_FIELDS` is curated on purpose.
#: Adding a field to the block is caught by the roster test, which requires every rendered label
#: to be classified here or explicitly excluded.
BLOCK_ONLY_FIELDS = ("stated_check_size", "pass_reason", "last_contact")

def strip_block(prompt: str) -> str:
    """Remove the block, or raise when there is no block, or no locatable end to one.

    COUPLING, load-bearing: this terminates at the block's end only because `render_block` emits
    no internal blank line and exactly one trailing newline, so the first blank line after the
    header IS the block's boundary. Three ways that boundary fails, all three run rather than
    argued, and they do not fail alike:

    - a blank line rendered directly AFTER the header strips the header alone and every field
      line survives, so no block question goes unanswered and the control reddens. Caught, loudly.
    - a blank line rendered anywhere FURTHER DOWN truncates there and the fields BELOW it survive.
      One question still goes unanswered, so "at least one fails" stays green over a context that
      still holds the rest of the block. That is what the exact-equality test is for.
    - NO blank line after the block at all, which is what ordinary prompt assembly produces:
      `render_block` already ends in one newline, so concatenating the next instruction straight
      onto it adds no separator. The end is then unlocatable, and taking everything from the
      header onward deletes the instruction along with the block. All three questions then fail
      because NOTHING WAS ASKED OF ANYONE, which is the hollow control this module exists to
      refuse. It raises, on the same doctrine as the absent-header raise: a boundary that cannot
      be found is not a boundary at the end of the string.

    The one shape where no blank line is legitimate is the block ENDING the prompt, and there
    returning everything before the header is right. The two are told apart by the block's own
    line shape - every line after the header reading `label: value`. Prose whose every line
    carried ": " would still be taken for block; that is a far narrower hole than the one it
    replaces, and it is stated here rather than papered over.

    The mid-block truncation is also reachable from the data side without anyone editing this
    code, since a field value containing or ending in a newline renders a blank line inside the
    block. That is shut at the producer: `render_block` raises `BlockValueUnrenderable` rather
    than rendering such a value, so the shape this function depends on cannot be broken by a
    stored string.
    """
    if BLOCK_HEADER not in prompt:
        raise ValueError("no rendered block in this prompt; the control has nothing to strip")
    head, _, rest = prompt.partition(BLOCK_HEADER)
    _, sep, tail = rest.partition("\n\n")
    if sep:
        return head + tail
    if all(": " in line for line in rest.splitlines() if line):
        return head                       # the block ends the prompt; nothing follows to keep
    raise ValueError(
        "the block is followed by text with no blank line between them, so the block's end "
        "cannot be located; stripping to the end of the prompt would take the instruction with "
        "it and leave every question unanswered because none of them was asked"
    )

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
