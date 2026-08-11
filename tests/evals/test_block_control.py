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

def test_a_block_with_no_blank_line_after_it_keeps_the_instruction():
    """The hollow control arrives through prompt ASSEMBLY, not through the rendering.

    `render_block` already ends in one newline, so the natural concatenation adds no separator,
    and then there is no blank line after the block at all. A stripper that took everything from
    the header onward would remove the instruction along with the block; all three questions then
    fail because NOTHING WAS ASKED OF ANYONE, and the control reports the block load-bearing on
    the strength of a prompt that no longer asks anything.

    The block's end is not a blank line. It is the last line carrying one of the block's own
    labels, so the tail needs no separator to survive.
    """
    p = f"{HEAD}\n\n" + render_block(record()) + TAIL          # no separating newline
    assert strip_block(p) == f"{HEAD}\n\n{TAIL}"

def test_an_instruction_carrying_a_colon_is_not_read_as_a_block_line():
    """The measured shape that made the raise above the wrong answer, and the round-2 defect.

    A stripper that told block from tail by asking whether every remaining line held ": " read
    `Task: draft a short follow-up.` as block, because for a ONE-LINE instruction "every line" is
    one line and a single colon anywhere in it suffices. The strip then returned the head alone
    and the control went green over a prompt that asked nothing. An ordinary instruction carrying
    an ordinary colon is not a rare shape, so this is pinned separately from the plain tail above:
    that one reddens if the walk stops consuming block lines, this one reddens if the walk ever
    starts guessing from punctuation again.
    """
    tail = "Task: draft a short follow-up."
    stripped = strip_block(f"{HEAD}\n\n" + render_block(record()) + tail)
    assert stripped == f"{HEAD}\n\n{tail}"
    assert all(answer_from(stripped, f) is None for f in BLOCK_ONLY_FIELDS)

def test_a_multi_paragraph_tail_survives_whole_including_its_first_paragraph():
    """Partitioning on the first blank line ate the first paragraph of a two-paragraph tail.

    That blank line is inside the TAIL, not after the block, and nothing about "first blank line
    after the header" can tell the two apart. Walking the block's own lines does not have to: the
    walk has already stopped by the time the tail's blank line is reached.
    """
    tail = "Draft a short follow-up.\n\nBe brief."
    assert strip_block(f"{HEAD}\n\n" + render_block(record()) + tail) == f"{HEAD}\n\n{tail}"

def test_the_prose_the_strip_did_not_take_comes_back_byte_for_byte():
    r"""The splitter the walk uses has to be the one that rejoins without rewriting.

    `split("\n")` and `"\n".join` are exact inverses. `splitlines` and `"\n".join` are not: eight
    further characters begin a line for `splitlines`, so a tail carrying one of them comes back
    with that character silently rewritten to a newline. `render_block` refuses those characters
    in a RECORD, and the prose around the block is not a record - it is whatever the prompt
    assembler wrote. A stripper that edited the text it kept would hand the specialist a prompt
    nobody wrote, which is the fabrication this whole eval is pointed at.
    """
    tail = "Draft a short follow-up.\u2028Then stop."   # an escape: this file is ASCII
    assert tail.splitlines() != [tail] and "\n" not in tail, "no break; this test is void"
    assert strip_block(f"{HEAD}\n\n" + render_block(record()) + tail) == f"{HEAD}\n\n{tail}"

def test_a_block_that_ends_the_prompt_is_still_stripped():
    # A block sitting at the very END of the prompt has no tail at all, and there the head is the
    # whole answer. Same walk, no special case: it runs out of lines and there is nothing to keep.
    assert strip_block(f"{HEAD}\n\n" + render_block(record())) == f"{HEAD}\n\n"

def test_trailing_whitespace_after_a_terminal_block_is_not_a_tail():
    # Blank is `line.strip()`, not `line`. A prompt builder that joined its pieces with spaces
    # leaves `"   "` where the terminal block's separator would be; testing the raw line would
    # read that as the tail and hand back a prompt whose whole remaining instruction is padding.
    assert strip_block(f"{HEAD}\n\n" + render_block(record()) + "   ") == f"{HEAD}\n\n"

def test_only_the_blocks_own_separator_blank_line_is_consumed():
    # AT MOST ONE, and the ordinary fixture cannot show it: the block renders one trailing newline
    # and the assembler adds one, so the usual seam is a single blank line and a greedy consume
    # looks identical there. A tail that deliberately opens on its own blank line is where the two
    # part, and vertical space someone wrote into the prompt is not the stripper's to take.
    tail = "\nDraft a short follow-up."
    assert strip_block(f"{HEAD}\n\n" + render_block(record()) + f"\n{tail}") == f"{HEAD}\n\n{tail}"

def test_a_blank_line_after_the_header_strips_the_header_alone_and_reddens_loudly():
    """The first of the two ways a beautified rendering breaks the block's shape.

    A blank line directly after the header stops the walk before it consumes anything, so the
    header goes and every field line stays. That is the LOUD failure: no block question goes
    unanswered, so the control itself reddens and says the block was not stripped. It must not
    raise, because a raise here would be a stripper refusing to run instead of a control
    reporting that it demonstrated nothing.
    """
    beautified = render_block(record()).replace(f"{BLOCK_HEADER}\n", f"{BLOCK_HEADER}\n\n", 1)
    stripped = strip_block(f"{HEAD}\n\n" + beautified + f"\n{TAIL}")
    assert BLOCK_HEADER not in stripped and TAIL in stripped
    assert all(answer_from(stripped, f) is not None for f in BLOCK_ONLY_FIELDS)

def test_a_blank_line_mid_block_truncates_there_and_leaves_the_fields_below():
    """The second way, and the quiet one, which is why exact equality is the test that catches it.

    A blank line further down stops the walk there, so the fields BELOW it survive into the
    "stripped" context. One field going missing is enough to keep "at least one question fails"
    green over a prompt that still holds two thirds of the block, and that is asserted here rather
    than argued: the spec's sentence is not on its own a check of itself.
    """
    beautified = render_block(record()).replace("pass_reason:", "\npass_reason:", 1)
    stripped = strip_block(f"{HEAD}\n\n" + beautified + f"\n{TAIL}")
    assert answer_from(stripped, "stated_check_size") is None      # above the break, consumed
    assert answer_from(stripped, "pass_reason") == "stage too early"    # below it, still standing
    assert answer_from(stripped, "last_contact") is not None
    assert [f for f in BLOCK_ONLY_FIELDS if answer_from(stripped, f) is None]
    assert stripped != f"{HEAD}\n\n{TAIL}"

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
