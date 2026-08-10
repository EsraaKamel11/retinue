"""The one parent-registered PreToolUse hook. Routing first (a table, total by test), then the
imported deterministic lane on send payloads. The checker never runs here - it runs at the
chokepoint inside the send tool body (P3). Unknown agent_type fails toward the human."""
from __future__ import annotations
from chaperone.gates.sdk_callback import pre_tool_use_deny

SEND_TOOL = "send_message"   # the ONE definition; the audit holds every other module to importing it
SEND_TOOLS = frozenset((SEND_TOOL, "mcp__retinue__" + SEND_TOOL))   # live server name as data

def decide(agent_type: str | None, tool_name: str) -> str:
    if agent_type is None:
        return "allow"
    # A tuple, not a frozenset, and the difference is load-bearing: `in` on a tuple compares with
    # `==` and never hashes, so a non-string agent_type from a malformed payload reaches the ask
    # below instead of raising TypeError. That keeps `decide` total for every caller, and leaves
    # the router's own guard a second line of defence rather than the only one. Tidying this into
    # a frozenset for symmetry with SEND_TOOLS trades a fail-closed path for a raise.
    if agent_type in ("research", "drafting"):
        return "allow"
    if agent_type == "conversation":
        return "ask" if tool_name in SEND_TOOLS else "allow"
    return "ask"

def _ask(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "ask",
                                   "permissionDecisionReason": reason}}

async def pre_tool_use(input_data: dict, tool_use_id, context) -> dict:
    """Route first, then delegate send payloads to the imported deterministic lane.

    The whole body is guarded because a hook that raises fails OPEN: the platform contract is
    that an exception propagating out of a hook does not block the tool call. The imported
    `pre_tool_use_deny` spends a `BaseException` catch on exactly that, and two unguarded lines
    in front of it - a `.get` on a payload that may not be a dict, and a hashable-membership
    test on a tool name that may not be a string - would put a fail-open window ahead of that
    net and make its own malformed-payload guard unreachable.

    It ASKS rather than denies, because the router failing is not a policy finding, and a
    denial that reports a policy class it never evaluated is the masquerade this design refuses
    everywhere else. Nothing executes without a human either way.
    """
    try:
        agent_type = input_data.get("agent_type")
        tool_name = input_data.get("tool_name") or ""
        verdict = decide(agent_type, tool_name)
        if verdict == "ask":
            if tool_name in SEND_TOOLS:
                return _ask(f"outward send by {agent_type!r} requires a human")
            # agent_type is untrusted payload text rendered into a permission prompt: quote it.
            return _ask(f"unrecognised agent type {agent_type!r}; unknown fails toward the human")
        if tool_name in SEND_TOOLS:
            return await pre_tool_use_deny(input_data, tool_use_id, context)
        # `{}` declines to intervene rather than affirming an allow. An explicit allow would
        # override the user's own permission configuration in the permissive direction, which is
        # the one direction a gate may never move it.
        return {}
    except BaseException as exc:
        return _ask(f"the router could not complete: {type(exc).__name__}")
