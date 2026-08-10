from datetime import datetime, timezone
from decimal import Decimal
import pytest
from retinue.ledger.projection import RelationshipRecord
from retinue.ledger.block import BLOCK_HEADER, BlockBudgetExceeded, BlockFieldMissing, render_block

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
