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
    agent_type = input_data.get("agent_type")
    tool_name = input_data.get("tool_name", "")
    verdict = decide(agent_type, tool_name)
    if verdict == "ask":
        return _ask(f"outward action by {agent_type or 'unknown'} requires a human")
    if tool_name in SEND_TOOLS:
        return await pre_tool_use_deny(input_data, tool_use_id, context)
    return {}
