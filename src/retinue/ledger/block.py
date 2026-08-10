"""The record rendered into the prompt-riding block.

Two raises, never warnings: a partial block is the fabrication vector arriving through the
most-trusted component, and an over-budget block silently truncated is the same defect. The header
is a contract: the control eval's stripper matches it byte-for-byte (spec 7.1).
"""
from __future__ import annotations
from retinue.ledger.projection import RelationshipRecord

BLOCK_HEADER = "# Relationship Record"

class BlockFieldMissing(Exception): ...
class BlockBudgetExceeded(Exception): ...

_REQUIRED = ("investor_id",)          # identity is required; facts may honestly be absent

def render_block(record: RelationshipRecord, *, budget: int = 1024) -> str:
    for name in _REQUIRED:
        v = getattr(record, name)
        if v is None or v == "":
            raise BlockFieldMissing(f"required field {name} is absent, null, or empty")
    lines = [BLOCK_HEADER,
             f"investor: {record.investor_id}",
             f"stated_check_size: {record.stated_check_size if record.stated_check_size is not None else 'not stated'}",
             f"pass_reason: {record.pass_reason or 'none recorded'}",
             f"last_contact: {record.last_contact.isoformat() if record.last_contact else 'never'}",
             f"jurisdiction: {record.jurisdiction or 'unknown'}",
             f"domain: {record.domain or 'unknown'}"]
    out = "\n".join(lines) + "\n"
    if len(out.encode()) > budget:
        raise BlockBudgetExceeded(f"{len(out.encode())} bytes exceeds the {budget}-byte budget")
    return out
