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
    assert render_block(rec()).startswith(BLOCK_HEADER + "\n")

def test_missing_required_field_raises_naming_it():
    for hole in (None, ""):                       # absent-as-None and empty-string both refuse
        with pytest.raises(BlockFieldMissing, match="investor_id"):
            render_block(rec(investor_id=hole))

def test_optional_fields_render_as_stated_absent_not_invented():
    out = render_block(rec(stated_check_size=None))
    assert "stated_check_size: not stated" in out   # absence stated, never fabricated

def test_budget_exceeded_raises():
    with pytest.raises(BlockBudgetExceeded):
        render_block(rec(pass_reason="x" * 5000), budget=256)
