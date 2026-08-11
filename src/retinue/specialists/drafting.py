"""Drafting: from the record only; output goes to review, never directly out. One module, both
artifacts, shared constants (the spec's parity rule - topology imports THIS prompt object)."""
from __future__ import annotations
from pydantic_ai import Agent
from chaperone.policy.types import Draft, Message
from retinue.boundary.hook import SEND_TOOL
from retinue.ledger.projection import RelationshipRecord

DRAFTING_PROMPT = (
    "Draft outbound text from the relationship record only. Cite the record fields you used. "
    "Never state a figure the record does not hold. Your output goes to review, never directly out."
)

def build_draft(record: RelationshipRecord, thread: tuple[Message, ...], body: str,
                cited_fields: tuple[str, ...]) -> Draft:
    if not record.jurisdiction or not record.domain:
        raise ValueError("drafting requires the identity record: jurisdiction and domain (spec 4.2)")
    return Draft(thread=thread, body=body, cited_fields=cited_fields,
                 recipient_jurisdiction=record.jurisdiction, recipient_domain=record.domain,
                 tool_name=SEND_TOOL)

def build_drafting_agent(model) -> Agent:
    return Agent(model, output_type=str, instructions=DRAFTING_PROMPT)
