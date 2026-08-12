"""The topology as inspectable data. These objects are asserted by tests and rendered by docs;
nothing here spawns anything. Model tiers use the imported MODEL_STRENGTH vocabulary so the
checker-ordering guarantee reads straight off this table."""
from __future__ import annotations
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import AgentDefinition
from retinue.boundary.hook import SEND_TOOLS
from retinue.specialists.conversation import CONVERSATION_PROMPT
from retinue.specialists.drafting import DRAFTING_PROMPT
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
    "drafting": AgentDefinition(
        description="Drafts outreach from the relationship record. Output goes to review.",
        prompt=DRAFTING_PROMPT,     # parity: the SAME constant object the pydantic-ai agent uses
        tools=["Read"], background=False),
    "conversation": AgentDefinition(
        description="Carries investor conversation; sends are gated.",
        prompt=CONVERSATION_PROMPT,  # parity: the SAME constant object the pydantic-ai agent uses
        # The one roster that names the send tool, and it names it by IMPORT: the literal has a
        # single home in boundary/, which is the audit's `send_tool_single_home` rule. Both
        # spellings, because which one the runtime binds is a property of how the tool is served
        # and not of this table. Declaring it is only half of offering it - see SESSION_TOOLS.
        tools=["Read", *sorted(SEND_TOOLS)], background=False),
}

#: The SESSION roster. The CLI resolves each subagent's declared tools by INTERSECTING them
#: with this list, so it is a shared ceiling and not a per-agent bound: narrowing it to the
#: spawn tool alone resolves every specialist to zero tools, silently, with the options-shape
#: tests still green. Its real job is to drop what NO agent needs - Bash, Write, Edit, WebFetch
#: and WebSearch are absent, so the research specialist cannot reach an outbound surface even
#: by inheritance. WITNESSED at CLI 2.1.222: a captured `system:init` resolved four tools, all of
#: them named here, with no CLI default surviving beside them - `tools=` restricts rather than
#: proposes. Per-agent bounds live in each AgentDefinition. This ceiling is the ORCHESTRATOR's
#: bound too, because `allowed_tools` pre-approves and restricts nothing: the same payload shows
#: Glob, Grep and Read resolved into the session while the allow-list held only the spawn names.
#:
#: THE SEND NAMES ARE HERE BECAUSE DECLARING A TOOL IS NOT OFFERING IT. The intersection above is
#: the whole reason: a send tool named in conversation's roster and absent from this tuple resolves
#: to `["Read"]` and is stripped, while every options-shape assertion stays green. Imported for the
#: same reason the roster is, so the literal keeps its single home.
#:
#: What this widening does NOT do, stated as three separate claims because they are checked
#: separately. Per-agent bounds still apply, so research and drafting declare no send tool and are
#: offered none: the ceiling is a maximum and never a grant. The hook still answers `"ask"` for
#: conversation on exactly these names, both spellings. And what it DOES do, which the paragraph
#: above this one already says and which a comment claiming "nothing changes" would bury: this
#: tuple is the ORCHESTRATOR's bound too, so the main thread can now reach a send tool where before
#: this line no send tool existed anywhere in the session.
#:
#: That reach is ROUTED rather than waved through, and the verb is narrow on purpose. `decide`
#: answers "allow" for a main-thread call, which puts the payload INTO the imported deterministic
#: lane rather than past it. That lane answers `{}` to allow and a deny dict to refuse, so "the
#: lane denies" is a property of a payload and never of the lane: the one payload measured here
#: refuses on both spellings, and an earlier version of this comment stated the general form of
#: that measurement, which is the overclaim this repository keeps having to walk back. A payload
#: the lane allowed would still meet the chokepoint inside the send tool body, which is where the
#: checker runs and where the act is executed or not.
#:
#: THE ASYMMETRY, which that paragraph stops one step short of and which is the sentence that
#: matters here: `decide` answers `"ask"` for CONVERSATION on these names and `"allow"` for the
#: MAIN THREAD. So conversation's send is held for a human BEFORE the call and the main thread's is
#: not. Measured: a clean bare-spelling payload from the main thread gets `{}` from the lane, which
#: is the allow answer. The widened main-thread path is therefore no human ask, no lane refusal,
#: and the chokepoint as the only remaining gate.
#:
#: TASK 23 WIRED THE SERVER, so half of the bound that used to sit here is gone and the answer
#: replaces it rather than sitting in a report. `scripts/demo.py` registers an in-process SDK MCP
#: server that serves the `mcp__` spelling, so in THAT session the main thread can reach a send tool
#: that exists. The ceiling above is why: it is shared, so conversation cannot be offered the tool
#: unless the main thread can reach it too, and the demo cannot narrow one without losing the other.
#:
#: WHAT HOLDS IT, in the order the claims are worth. First, the demo's tool body performs no act:
#: no transport, no gateway, no `attempt_send`, nothing that leaves the process. It is a capture
#: instrument, so reaching it sends nothing. Second, MEASURED on 2026-08-12, where an earlier
#: revision of this sentence was labelled inferred: the demo ran, the conversation agent's send
#: fired the hook's ask, and the tool body was reached ZERO times in a session that captured seven
#: hook payloads. One run of one session, so it is evidence the ask arm holds unattended, not a
#: distribution over runs; the claim still rests first on the body performing no act. Third, and
#: scoped to a payload SHAPE rather
#: than offered as a property of the lane: the demo's tool declares `{"body": str}`, which is the
#: chokepoint's own whole `tool_input`, and a main-thread call carrying only a body is refused by the
#: imported lane on `act:no_approval_token`. That last one is a measurement over the shape the schema
#: permits and not a general claim, which is the distinction the paragraph above had to walk back.
#:
#: The other half of the bound stands, and it is stated rather than quietly dropped: `attempt_send`
#: still has NO caller outside its own module and tests. The demo did not become one, deliberately.
#: Building a gateway, checker, registry, queues, store and ActContext inside a manual keyed script
#: would put the chokepoint's first agent call on a path whose first execution is a live run nobody
#: has done, and "would still meet the chokepoint" would go on being present tense about something
#: nothing calls. A demo that captures what the gate does before the call is the thing this fleet can
#: show; a chokepoint caller it cannot run is not.
SESSION_TOOLS = ("Agent", "Task", "Read", "Grep", "Glob", *sorted(SEND_TOOLS))

def build_options(hook) -> ClaudeAgentOptions:
    # `tools` is the session roster; `allowed_tools` is the auto-approve list. Both are set:
    # omitting `tools` inherits the CLI default, and omitting `allowed_tools` would leave the
    # spawn call needing an approval that nobody in an unattended run is there to give. It states
    # no bound - it pre-approves, and the bound is `tools` above.
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
    # The reason to care is the fixtures. The design should survive an inherited agent - the
    # ceiling would intersect its roster down to the same four tools, and an unrecognised
    # `agent_type` routes to the human by `decide`'s own table - but both are INFERRED for that
    # case, since no inherited agent was spawned in any of the three captures. Labelled rather
    # than dropped, because a block that advertises measurement may not smuggle in an inference.
    # A payload captured from a session one machine's configuration helped shape is not the
    # canonical artifact the default lane replays forever.
    return ClaudeAgentOptions(
        agents=AGENTS,
        tools=list(SESSION_TOOLS),
        allowed_tools=list(SPAWN_TOOLS),
        permission_mode="default",
        setting_sources=[],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[hook])]},
    )
