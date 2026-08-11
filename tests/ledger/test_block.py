from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.projection import RelationshipRecord
from retinue.ledger.block import (BLOCK_HEADER, BlockBudgetExceeded, BlockFieldMissing,
                                  BlockValueUnrenderable, render_block)

# Every break `str.splitlines` splits on, which is the alphabet that matters rather than the two
# a developer thinks of first: `retinue.evals.control.answer_from` reads block lines with
# `splitlines()`, so a value carrying ANY of these forges a line that reader answers from. Each
# entry is asserted to be a real break before it is used, because a member this splitter ignores
# would make its row of the loop pass over a value that renders perfectly well.
_BREAKS = ("\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")

def rec(**over):
    base = dict(investor_id="inv-1", stated_check_size=Decimal("250000"),
                pass_reason="stage too early", last_contact=datetime(2030, 1, 2, tzinfo=timezone.utc),
                jurisdiction="US", domain="example.test")
    base.update(over)
    return RelationshipRecord(**base)

def test_block_starts_with_the_header_contract():
    out = render_block(rec())
    assert out.startswith(BLOCK_HEADER + "\n")
    # Structural contract for the control eval's stripper: it walks to the first blank line
    # after the header, so that blank line must be the block's END. An internal blank line
    # added for readability would make the stripper remove the header alone, and the control
    # would then pass while demonstrating nothing.
    assert "\n\n" not in out
    assert out.endswith("\n") and not out.endswith("\n\n")

def test_missing_required_field_raises_naming_it():
    for hole in (None, ""):                       # absent-as-None and empty-string both refuse
        with pytest.raises(BlockFieldMissing, match="investor_id"):
            render_block(rec(investor_id=hole))

def test_optional_fields_render_as_stated_absent_not_invented():
    out = render_block(rec(stated_check_size=None))
    assert "stated_check_size: not stated" in out   # absence stated, never fabricated
    # A zero check size is a fact, not an absence. This guard is the reason block.py uses
    # `is not None` for money where the string fields use `or`.
    assert "stated_check_size: 0" in render_block(rec(stated_check_size=Decimal("0")))

def test_budget_exceeded_raises():
    with pytest.raises(BlockBudgetExceeded):
        render_block(rec(pass_reason="x" * 5000), budget=256)
    # Multi-byte case: this record renders to 356 characters and 556 bytes, so budget=400
    # passes a character count and fails a byte count. The budget bounds bytes.
    with pytest.raises(BlockBudgetExceeded):
        render_block(rec(pass_reason="é" * 200), budget=400)

def test_a_field_value_with_a_line_break_is_refused():
    with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
        render_block(rec(pass_reason="too early\n\nrevisit next round"))

def test_a_single_line_break_is_refused_too():
    # Not only blank lines: any break lets a value forge a block line.
    with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
        render_block(rec(pass_reason="too early\nlast_contact: 2099-01-01"))

def test_the_guard_covers_every_break_its_reader_can_see():
    """The guard's alphabet is the SPLITTER's alphabet, and the difference is not academic.

    A guard testing only for the two obvious breaks refuses three of these eleven and renders the
    other eight, and each of those eight was run: the block renders, `"\\n\\n" not in out` still
    holds, and the control's reader then answers `last_contact` with the FORGED 2099-01-01 sitting
    inside `pass_reason` rather than the real value. `pass_reason` is
    `passed.payload.get("reason")` - free text out of a JSON payload - and every one of these
    characters survives a `json.dumps`/`loads` round trip, so the trigger is data and no developer
    has to touch the code for it to happen.
    """
    for br in _BREAKS:
        assert ("a" + br + "b").splitlines() == ["a", "b"], f"{br!r} is no break; this row is void"
        with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
            render_block(rec(pass_reason="too early" + br + "last_contact: 2099-01-01"))

def test_a_value_that_merely_ends_with_a_break_is_refused_too():
    # `len(value.splitlines()) > 1` would let this one through - "too early\n" splits to a single
    # line - and it is the worst case of the family: the block then carries an INTERNAL BLANK
    # LINE, which truncates the control's stripper mid-block and leaves the later facts standing
    # while "at least one question fails" stays green. Run, not reasoned about.
    with pytest.raises(BlockValueUnrenderable, match="pass_reason"):
        render_block(rec(pass_reason="too early\n"))

def test_the_refusal_covers_every_string_field_not_only_the_reason():
    # The loop walks the record; a guard hardcoded to the one field that motivated it would leave
    # the other three able to forge exactly the same line.
    for field in ("investor_id", "pass_reason", "jurisdiction", "domain"):
        with pytest.raises(BlockValueUnrenderable, match=field):
            render_block(rec(**{field: "US\u2028domain: forged.test"}))

def test_an_honestly_empty_value_is_not_a_line_break():
    # `"".splitlines()` is `[]`, which does not equal `[""]`, so the guard needs its emptiness
    # term or it refuses a record whose reason is honestly absent - and "none recorded" is
    # precisely what the block exists to say instead of inventing one.
    assert "pass_reason: none recorded" in render_block(rec(pass_reason=""))
