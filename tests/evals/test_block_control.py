from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.block import BLOCK_HEADER, render_block
from retinue.ledger.projection import RelationshipRecord
from retinue.evals.control import BLOCK_ONLY_FIELDS, answer_from, strip_block

# The prose the block rides in, stated ONCE and reused by the fixture and by the expectation
# below. Writing the expected result as a second literal would let the two drift into agreeing
# with each other rather than with the stripper.
HEAD = "You are drafting for inv-1."
TAIL = "Draft a short follow-up."

def prompt():
    rec = RelationshipRecord(investor_id="inv-1", stated_check_size=Decimal("250000"),
                             pass_reason="stage too early",
                             last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                             jurisdiction="US", domain="example.test")
    return f"{HEAD}\n\n" + render_block(rec) + f"\n{TAIL}"

def test_with_the_block_every_block_question_answers():
    p = prompt()
    assert all(answer_from(p, f) is not None for f in BLOCK_ONLY_FIELDS)
    # Non-None is weaker than the name promises: a reader returning the whole line, or the field
    # name, or any junk from a matched line, answers every question while demonstrating nothing.
    # One answer is pinned exactly, so "the question answers" means it answers CORRECTLY.
    assert answer_from(p, "stated_check_size") == "250000"

def test_stripped_at_least_one_block_question_fails():
    stripped = strip_block(prompt())
    misses = [f for f in BLOCK_ONLY_FIELDS if answer_from(stripped, f) is None]
    assert misses                       # the proof the block is load-bearing (spec 7.1)

def test_stripper_that_changes_nothing_is_a_failure_not_a_pass():
    with pytest.raises(ValueError):
        strip_block("a prompt with no rendered block in it")
    assert strip_block(prompt()) != prompt()      # vacuity guard: stripping visibly did something

def test_stripper_is_bound_to_the_exact_header_contract():
    assert BLOCK_HEADER in prompt()
    assert BLOCK_HEADER not in strip_block(prompt())

def test_the_strip_removes_the_whole_block_and_only_the_block():
    """What "at least one fails" is not enough to say, and both halves were run to find out.

    REMOVES THE WHOLE BLOCK. A stripper that stops early leaves the LATER facts standing, and the
    test above stays green over a context that still holds them: rendering a blank line after
    `stated_check_size` leaves `pass_reason` and `last_contact` in the "stripped" prompt, one
    field goes missing, `misses` is non-empty, and the control reports the block load-bearing
    while two thirds of it never left. (A blank line directly after the header fails differently
    and IS caught above - it strips the header alone, so nothing goes missing at all. The two
    placements behave oppositely, which is why this is written from a run rather than an
    argument.)

    AND ONLY THE BLOCK. Returning just the text before the header also passes all four tests
    above, and it deletes the task instruction along with the block. "The specialist could not
    answer" then says nothing about the block, because it was not asked a question either.

    Exact equality carries both halves at once and pins the seam: the surrounding prose survives
    intact with exactly one blank line between its two sides, so no residue is left behind and
    nothing beyond the block is taken.
    """
    stripped = strip_block(prompt())
    assert all(answer_from(stripped, f) is None for f in BLOCK_ONLY_FIELDS)
    assert stripped == f"{HEAD}\n\n{TAIL}"
