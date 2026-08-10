"""The topology as inspectable data. These objects are asserted by tests and rendered by docs;
nothing here spawns anything. Model tiers use the imported MODEL_STRENGTH vocabulary so the
checker-ordering guarantee reads straight off this table."""
from __future__ import annotations
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import AgentDefinition
from retinue.specialists.research import RESEARCH_PROMPT

SPAWN_TOOLS = ("Agent", "Task")   # renamed at CLI 2.1.63; both listed, runtime binds one

TIERS = {"orchestrator": "sonnet-tier", "research": "haiku-tier",
         "drafting": "haiku-tier", "conversation": "sonnet-tier"}

# background=False is stated on every definition, never left unset. The SDK serialises a
# definition by dropping its None fields, so an unset background sends nothing and the CLI's own
# default applies - background since 2.1.198 - and a background subagent has its tool list
# stripped. Containment shown against a stripped roster would be containment of nothing.
AGENTS: dict[str, AgentDefinition] = {
    "research": AgentDefinition(
        description="Researches investors from fixture documents; cites or refuses.",
        prompt=RESEARCH_PROMPT,     # parity: the SAME constant object the pydantic-ai agent uses
        tools=["Read", "Grep", "Glob"], background=False),
    # drafting/conversation prompts are PROVISIONAL inline strings until their modules land
    # (Tasks 17 and 22 move them into shared constants and add their parity tests).
    "drafting": AgentDefinition(
        description="Drafts outreach from the relationship record. Output goes to review.",
        prompt="Draft from the record only.", tools=["Read"], background=False),
    "conversation": AgentDefinition(
        description="Carries investor conversation; sends are gated.",
        prompt="Converse; sending is gated.", tools=["Read"], background=False),
}

def build_options(hook) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        agents=AGENTS,
        allowed_tools=list(SPAWN_TOOLS),
        permission_mode="default",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook])]},
    )
