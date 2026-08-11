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

# The rendered labels this control deliberately does NOT ask about. Held here rather than left
# implicit so that the roster test below can require every rendered label to be in one list or the
# other, which is what turns "a field was added to the block" into a decision instead of silence.
NOT_BLOCK_ONLY_LABELS = frozenset({"investor", "jurisdiction", "domain"})

def record():
    return RelationshipRecord(investor_id="inv-1", stated_check_size=Decimal("250000"),
                              pass_reason="stage too early",
                              last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                              jurisdiction="US", domain="example.test")

def prompt():
    return f"{HEAD}\n\n" + render_block(record()) + f"\n{TAIL}"

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

def test_a_block_with_no_boundary_after_it_raises_rather_than_eating_the_prompt():
    """The hollow control arrives through prompt ASSEMBLY, not through the rendering.

    `render_block` already ends in one newline, so the natural concatenation adds no separator -
    and then there is no blank line after the block at all. Taking everything from the header
    onward removes the instruction along with the block, all three questions fail because NOTHING
    WAS ASKED OF ANYONE, and the control reports the block load-bearing on the strength of a
    prompt that no longer asks anything. That is M8 arriving as a prompt shape rather than as an
    edit, and the fixture with its explicit separator never builds it.

    Unlocatable is not the same as absent, and both raise, on one doctrine.
    """
    p = f"{HEAD}\n\n" + render_block(record()) + TAIL          # no separating newline
    with pytest.raises(ValueError, match="cannot be located"):
        strip_block(p)

def test_a_block_that_ends_the_prompt_is_still_stripped():
    # The other side of that raise, and the reason it cannot simply refuse whenever no blank line
    # follows: a block sitting at the very END of the prompt has no blank line after it either,
    # and there taking everything from the header onward is exactly right.
    assert strip_block(f"{HEAD}\n\n" + render_block(record())) == f"{HEAD}\n\n"

def test_every_rendered_label_is_classified_block_only_or_deliberately_not():
    """Rename and removal are loud; ADDITION is the direction that drifts in silence.

    A seventh field added to `render_block` and not to `BLOCK_ONLY_FIELDS` reddens nothing
    anywhere: the control simply stops covering it, every test stays green, and the eval quietly
    measures less than it claims. Requiring every rendered label to be classified one way or the
    other makes that addition a decision someone has to make, rather than a default.
    """
    labels = [line.split(":", 1)[0] for line in render_block(record()).splitlines()[1:]]
    assert len(labels) == len(set(labels)), "two rendered lines share a label"
    assert not (set(BLOCK_ONLY_FIELDS) & NOT_BLOCK_ONLY_LABELS), "a label classified both ways"
    assert set(labels) == set(BLOCK_ONLY_FIELDS) | NOT_BLOCK_ONLY_LABELS
