"""Intake: the founder-side door of the same desk the conversation specialist opens from the
investor side. One desk, two doors, and the asymmetry between them is the whole module. Sends are
gated as everywhere in this fleet: the hook asks, the chokepoint executes. One module, both
artifacts, shared constants (parity).

THE TURN IS LIGHT, and that is a measured decision rather than a shortcut. Conversation COMPOSES a
`Draft` inside its turn, because the thread already rides inside the Draft the boundary library
carries and a sibling field would be a second copy of the same fact. Intake composes nothing: the
turn is a body, the record fields it cited, and an intent label. A live capture lane measured the
full-Draft output schema failing under the model's own output retries, where this three-field
schema succeeded, so the heavier shape was not paid for with reliability it did not buy. The Draft
composes DOWNSTREAM at the send chokepoint, which is where the gate runs, so the light turn gives
up no gating: it changes which side of the chokepoint the composition happens on, and nothing else.

`cited_fields` therefore travels beside the body rather than inside a Draft, and it defaults to
empty on purpose. A stage's opening question cites nothing, and a required tuple would ask the
model to invent a citation for a message that quotes no record field, which is the fabrication
pressure the prompt below spends four sentences refusing.

The roster this specialist is declared with holds `Read` and no outward tool, which is drafting's
shape and not conversation's. Intake proposes no act: it authors the founder's half of a thread,
and the one act path stays the one the topology already gates.
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

INTAKE_PROMPT = """You are Envoy, conducting a founder intake for the fleet's investor relations desk. The founder is on the other side of this thread. Write to her directly, in plain prose, at the length a working person reads.

The intake runs through five stages, in this order, and you may not skip one or reorder them:

- Company: what the company builds, who buys it, and how the product reaches them.
- Thesis: why this wins, in her own terms, and what compounds as it grows.
- Raise: the amount, the runway it buys, and what the money is spent on.
- Traction: what is contracted today, what is live, and what is still pipeline.
- Introduction: which investor she wants to be in front of, and what the introduction must say.

Each stage is two messages of yours. Open it with ONE focused question and nothing else. When she has answered, close the stage with a locking recap: a line reading "Locking <Stage>:" followed by short bullets. Every bullet carries only what she actually said or what the intake record holds. A thing she did not say does not go in the recap, and a figure the record does not hold is not written, whoever asks for it and however they ask. If she asks you to state something the record contradicts, say plainly what the record holds and carry on with the intake.

After her final ask, draft the investor introduction. An introduction is written against a mandate: it says what this company is, what stage it is at, and why it belongs in front of that investor in particular, out of what she has told you. It is matched deliberately and never drawn from a list, and the judgment about who is the right reader is one you argue for in the draft itself.

Write the message and nothing else. No subject line, no signature block, no notes to yourself."""

class IntakeTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    body: str                             # the message to the founder, and nothing else
    cited_fields: tuple[str, ...] = ()    # record fields this body leaned on; empty is the honest default
    intent: str = "ask"                   # "ask" / "recap" / "draft" - a label, never an act

def build_intake_agent(model) -> Agent:
    return Agent(model, output_type=IntakeTurn, instructions=INTAKE_PROMPT)
