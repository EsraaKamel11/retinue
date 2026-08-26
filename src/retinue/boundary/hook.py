"""The one parent-registered PreToolUse hook. Routing first (a table, held against the topology by
test), then the imported deterministic lane on send payloads. The checker never runs here - it runs
at the chokepoint inside the send tool body (P3). Unknown agent_type fails toward the human."""
from __future__ import annotations
import asyncio
from chaperone.gates.sdk_callback import pre_tool_use_deny

SEND_TOOL = "send_message"   # the ONE definition; the audit holds every other module to importing it
SEND_TOOLS = frozenset((SEND_TOOL, "mcp__retinue__" + SEND_TOOL))   # live server name as data

#: The routing table as DATA: each agent type this fleet declares, paired with the tool names it is
#: asked about. A table rather than a chain of `if`s so that `decide`'s DOMAIN can be read and held
#: against something - `test_decision_table_is_total` compares these keys with
#: `orchestration.topology.AGENTS`, and a spot check over a handful of arms cannot make that
#: comparison. The dependency runs one way (topology imports SEND_TOOLS from here), so the two are
#: held equal from a test rather than derived one from the other.
#:
#: A tuple of pairs, not a dict, and the difference is load-bearing in a narrow way worth stating
#: exactly. `==` against each key in turn never hashes, so a non-string agent_type out of a
#: malformed payload walks off the end of the table and takes the unknown-agent ask. A dict lookup
#: or a set membership test raises TypeError on that value instead. MEASURED, both shapes still
#: fail closed: the one non-test caller runs inside `pre_tool_use`'s guarded body, which answers
#: ask either way. What differs is the reason the human reads - `unrecognised agent type [...]`
#: here, against `the router could not complete: TypeError` from a hashing form, which names the
#: router for a payload that was what went wrong. A diagnosis property, then, and not a containment
#: one, and it is stated as the smaller thing it is.
ROUTING: tuple[tuple[str, frozenset[str]], ...] = (
    ("research", frozenset()),
    ("drafting", frozenset()),
    ("conversation", SEND_TOOLS),
    # Intake is the desk's founder-side door and is offered no send tool, so it routes with an
    # empty gated set exactly as the other two content specialists do. The empty set is the honest
    # entry rather than a defensive `SEND_TOOLS`: a gated name for a tool the roster never declares
    # is an arm nothing can reach, and this table's whole job is to be readable as the fleet.
    ("intake", frozenset()),
)
ROUTED_AGENTS = frozenset(name for name, _ in ROUTING)

def decide(agent_type: str | None, tool_name: str) -> str:
    if agent_type is None:
        return "allow"
    for known, gated in ROUTING:
        if agent_type == known:
            # `gated and` short-circuits, so an agent with nothing gated never touches tool_name.
            # MEASURED rather than reasoned from CPython's set internals: `decide("research",
            # ["Read"])` answers "allow" as written here and raises TypeError with the short circuit
            # removed, because membership hashes its key before it looks, empty set or not. That
            # "allow" is the answer the if-chain this table replaced gave, preserved exactly.
            return "ask" if gated and tool_name in gated else "allow"
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
    except asyncio.CancelledError:
        # Cooperative cancellation must propagate. The imported lane can swallow BaseException
        # safely because its body contains NO `await`, so the loop has no suspension point to
        # throw into - its own docstring says in as many words that adding one changes that
        # claim. This body awaits the lane, so the claim does not transfer: converting a
        # cancellation into an ask would make the router un-cancellable and could stall a
        # shutdown, and a torn-down call is not a call waiting on a human.
        raise
    except BaseException as exc:
        return _ask(f"the router could not complete: {type(exc).__name__}")
