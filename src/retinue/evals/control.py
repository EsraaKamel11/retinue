"""The block-stripped control (spec 7.1). The most-trusted component gets the containment
treatment: re-ask ONLY the questions whose answers depend on block-only fields, against a context
with the block stripped. At least one must fail - and a control that passes says the stripper
silently did nothing, which is why an absent header RAISES instead of no-op'ing. The stripper
matches the exact header and then the block's own labels, which is why both are machine-checked
contracts imported from `block.py` rather than copies kept in step by hand.

"At least one must fail" is the spec's sentence, kept verbatim in the test that carries it, and it
is not on its own a sufficient check of itself: a strip that stopped part way leaves the later
facts standing and still makes one question fail, and a strip that deleted the rest of the prompt
makes all three fail for a reason having nothing to do with the block. Both were run;
`test_the_strip_removes_the_whole_block_and_only_the_block` is what closes them. Neither test
subsumes the other, and that was run too rather than assumed: emptying `BLOCK_ONLY_FIELDS` reddens
the spec's test alone, because asking no questions makes the stronger one vacuously true.
"""
from __future__ import annotations
from retinue.ledger.block import BLOCK_HEADER, BLOCK_LABELS

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
#:
#: This is NOT the roster `strip_block` walks by, and the two must not be merged. `BLOCK_LABELS`
#: is every label the block renders and is what says where the block ENDS; this is the subset the
#: control asks ABOUT. Walking by this one instead stops at `investor: `, which is the block's
#: first field line, and hands back a "stripped" prompt still holding the entire block.
BLOCK_ONLY_FIELDS = ("stated_check_size", "pass_reason", "last_contact")

def _is_block_line(line: str) -> bool:
    """A line the block itself rendered: one of ITS labels, then the separator it renders."""
    return any(line.startswith(f"{label}: ") for label in BLOCK_LABELS)

def strip_block(prompt: str) -> str:
    """Remove the block, or raise when there is no block to remove.

    STRUCTURAL, not boundary-hunting. The block is its header plus the CONSECUTIVE lines carrying
    its own labels, so the walk stops at the first line that is not the block's and the tail
    cannot be eaten. The hollow control - a strip that returns a prompt asking nothing, so all
    three questions fail for a reason having nothing to do with the block - is impossible here by
    construction rather than defended against, because whatever the walk stops at survives.

    Every earlier version of this looked for the block's END instead, and each way of looking
    failed on a shape ordinary assembly produces, which is why the approach was abandoned rather
    than patched again:

    - "the first blank line after the header" ate the first paragraph of any two-paragraph tail.
      That blank line sits INSIDE the tail, and nothing about the rule can tell the two apart.
    - "no blank line at all means the block ends the prompt, unless the remaining lines do not
      all carry ': '" read `Task: draft a short follow-up.` as block, because for a one-line
      instruction "every line" is one line and one colon anywhere in it suffices. It returned the
      head alone and the control passed over a prompt that asked nothing.

    Two shapes the walk must handle differently, and both are pinned by tests rather than argued,
    because they fail in opposite directions:

    - a blank line rendered directly AFTER the header stops the walk before it consumes anything,
      so the header goes and every field line stays. No block question goes unanswered and the
      control itself reddens. That is the loud failure, and this does NOT raise on it: a raise
      would be the stripper refusing to run in place of the control reporting what it found.
    - a blank line rendered FURTHER DOWN stops the walk there, and the fields below it survive.
      One field going missing keeps "at least one question fails" green over a context still
      holding two thirds of the block, so the exact-equality test is what catches that one.

    Neither is reachable from the data side: a stored value carrying any break `splitlines`
    recognises would render one, and `render_block` refuses such a value rather than rendering it.

    RESIDUAL, checked rather than asserted. A tail whose leading lines begin with one of the
    block's own six labels followed by ": " is still consumed. That set is a strict SUBSET of what
    the colon rule consumed - `line.startswith(f"{label}: ")` implies `": " in line` and never the
    reverse - so the hole is narrower by construction rather than by impression, and the six
    label openers were run to confirm both rules lose them.

    The size of the difference was measured, not estimated. Over 24 ordinary instruction openers
    written for a drafting prompt and appended with no separator, the colon rule LOST 13 in
    silence and RAISED on the other 11: it handled none of the 24 correctly. This walk keeps all
    24. "Far narrower" is a claim about that measurement and not about how the rule reads.
    """
    if BLOCK_HEADER not in prompt:
        raise ValueError("no rendered block in this prompt; the control has nothing to strip")
    head, _, rest = prompt.partition(BLOCK_HEADER)
    # `split("\n")` and `"\n".join` are exact inverses. `splitlines` is not: it also breaks on the
    # eight further characters `render_block` refuses, so rejoining its output would silently
    # rewrite any of those that reached the surrounding prose.
    lines = rest.split("\n")
    i = 1                                 # index 0 is the remainder of the header's own line
    while i < len(lines) and _is_block_line(lines[i]):
        i += 1
    if i < len(lines) and not lines[i].strip():
        i += 1                            # at most one blank line, the block's own separator
    return head + "\n".join(lines[i:])

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
