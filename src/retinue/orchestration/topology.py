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

#: The SESSION roster. The CLI resolves each subagent's declared tools by INTERSECTING them
#: with this list, so it is a shared ceiling and not a per-agent bound: narrowing it to the
#: spawn tool alone resolves every specialist to zero tools, silently, with the options-shape
#: tests still green. Its real job is to drop what NO agent needs - Bash, Write, Edit, WebFetch
#: and WebSearch are absent, so the research specialist cannot reach an outbound surface even
#: by inheritance. Per-agent bounds live in each AgentDefinition; the orchestrator's own bound
#: is `allowed_tools` plus the hook.
SESSION_TOOLS = ("Agent", "Task", "Read", "Grep", "Glob")

def build_options(hook) -> ClaudeAgentOptions:
    # `tools` is the session roster; `allowed_tools` is the auto-approve list. Both are set:
    # omitting `tools` inherits the CLI default, and omitting `allowed_tools` would leave the
    # orchestrator's spawn-only bound unstated.
    #
    # `setting_sources=[]` is the third, and what it does here is measured, not assumed. Left
    # unset it defaults to None, which loads every filesystem settings source - and `agents`
    # MERGES with what those sources declare rather than replacing it. A live capture taken
    # without it resolved SIXTEEN agent definitions where this table declares three, plus two
    # plugins and the operator's own hooks, all read off one machine. A second capture with it
    # set resolved eight: the eight settings-defined agents, both plugins and those ambient hooks
    # were gone, and the resolved tool list was identical either way.
    #
    # What it does NOT remove, stated because the paragraph above would otherwise overclaim: the
    # CLI's own built-in agents (`claude`, `Explore`, `general-purpose`, `Plan`,
    # `statusline-setup`), which are the product rather than anyone's configuration; and the MCP
    # servers, which reach the session from a source this option does not govern - both captures
    # listed the same five. That residual is why the fixture contract asserts that no `mcp__`
    # tool resolves INTO the session, which is the property those servers would have to breach
    # to matter.
    #
    # The reason to care is the fixtures. The design survives an inherited agent (the session
    # ceiling intersects it down to the same four tools, and an unrecognised `agent_type` routes
    # to the human), but a payload captured from a session one machine's configuration helped
    # shape is not the canonical artifact the default lane replays forever.
    return ClaudeAgentOptions(
        agents=AGENTS,
        tools=list(SESSION_TOOLS),
        allowed_tools=list(SPAWN_TOOLS),
        permission_mode="default",
        setting_sources=[],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook])]},
    )
