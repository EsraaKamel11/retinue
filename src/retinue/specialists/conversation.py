"""Conversation: COMPOSES a Draft (the thread already rides inside it) rather than siblinging it,
so the conversation lane hands the checker everything the boundary library already carries
(spec 4.3). Sends are gated: the hook asks, the chokepoint executes. One module, both artifacts,
shared constants (parity).

The composition is the contract and not a style choice. A `thread` field beside the draft is a
second copy of the same fact, and the two copies are what the checker and the reviewer would then
disagree about: the imported prompt builder reads the thread off the Draft, so a turn carrying its
own thread would be judged against the draft's copy while the reviewer read the turn's. There is no
field here to fall out of step, which is why the test asserts the ABSENCE of the sibling rather
than only the presence of the composed draft.
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from chaperone.policy.types import Draft

CONVERSATION_PROMPT = (
    "Carry the investor conversation from the record and the thread. Propose each turn as a "
    "draft; any outward send is gated - a human approves the act, never you."
)

class ConversationTurn(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    draft: Draft          # composition: thread, body, citations, recipient - all inside
    intent: str           # "reply" / "follow_up" - a label, never an act

def build_conversation_agent(model) -> Agent:
    return Agent(model, output_type=ConversationTurn, instructions=CONVERSATION_PROMPT)
