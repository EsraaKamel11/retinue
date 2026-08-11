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
class BlockValueUnrenderable(Exception): ...

_REQUIRED = ("investor_id",)          # identity is required; facts may honestly be absent

def render_block(record: RelationshipRecord, *, budget: int = 1024) -> str:
    for name in _REQUIRED:
        v = getattr(record, name)
        if v is None or v == "":
            raise BlockFieldMissing(f"required field {name} is absent, null, or empty")
    # Refused, never sanitized: silently rewriting a recorded value would make the block disagree
    # with the ledger it projects, and this module's doctrine is that a block which cannot be
    # rendered honestly is not rendered at all.
    #
    # The test is `splitlines`, not a search for the two breaks a developer thinks of first, and
    # the difference is the whole guard. `splitlines` is the SAME splitter the control eval's
    # reader uses, and its alphabet is far wider: \v, \f, \x1c, \x1d, \x1e, \x85, \u2028 and
    # \u2029 all begin a line for it. A value carrying one of those renders a block that looks
    # perfect - no blank line, one trailing newline - while the reader sees a forged field line
    # inside the value and answers from it. `pass_reason` is `passed.payload.get("reason")`, free
    # text out of a JSON payload, and all eight survive a JSON round trip, so the trigger is DATA
    # and no one has to touch this code for it to happen.
    #
    # Comparing against `[value]` rather than counting lines also catches a value that merely ENDS
    # with a break, which is the one case that produces an internal blank line - and that is the
    # case the control's stripper truncates on. `value and` keeps an honestly empty value
    # renderable, since "".splitlines() is [] and would otherwise be refused.
    for name, value in vars(record).items():
        if isinstance(value, str) and value and value.splitlines() != [value]:
            raise BlockValueUnrenderable(
                f"{name} contains a line break, so rendering it would forge a block line or an "
                "early block boundary; the record is refused rather than rewritten"
            )
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
