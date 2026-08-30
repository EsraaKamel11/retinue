"""Shared doubles for the boundary tests.

`draft_factory` builds a `Draft` whose body, tool name and recipient domain are each overridable,
which is what the approval bridge's validation legs need: every leg is a comparison between a
binding the mint recorded and the actual call's own fact, so a test for one leg has to move
exactly one of them and leave the rest alone.

The default tool name is DERIVED from the imported `SEND_TOOLS` roster rather than spelled. The
send tool has one home, and a second file carrying its wire spelling is a second thing to update.
The `mcp__` member is the one taken here because `tests/boundary/test_send_tool.py` already drives
the bare name through its own `draft` helper, so between the two files both members are exercised.
"""
from __future__ import annotations

import pytest

from chaperone.policy.types import Draft, Message
from retinue.boundary.hook import SEND_TOOLS

#: Picked out of the imported roster rather than typed. The roster's SHAPE - two members, one of
#: them prefixed - is pinned by `test_conversation_is_asked_on_every_spelling_of_the_send_tool`,
#: so a roster that collapsed reddens there with its own name on it rather than raising here in a
#: way that reads as an unrelated collection error.
MCP_SEND_TOOL = next(t for t in sorted(SEND_TOOLS) if t.startswith("mcp__"))


@pytest.fixture
def draft_factory():
    """Keyword-only, so a caller that means to move the recipient domain cannot move the body."""

    def make(*, body="hello", tool_name=MCP_SEND_TOOL, recipient_domain="example.test",
             recipient_jurisdiction="US", thread=None):
        # `is None` and never falsiness, for the reason `test_send_tool.py`'s own helper gives:
        # `thread or default` turns an EXPLICITLY empty thread back into the default one, and a
        # test written for a draft with no conversation would silently have been handed one.
        default = (Message(role="investor", body="hello"),)
        return Draft(thread=default if thread is None else thread, body=body, cited_fields=(),
                     recipient_jurisdiction=recipient_jurisdiction,
                     recipient_domain=recipient_domain, tool_name=tool_name)

    return make
