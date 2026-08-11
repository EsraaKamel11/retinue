"""The P1 live capture smoke (spec 2.3). RETINUE_LIVE=1 gated; never imported by tests; run
manually, once; its outputs are the canonical captured fixtures the default lane replays.

Session shape: orchestrator + research subagent ONLY - no send tool exists anywhere in the
session, so this run cannot ask and does not try to. It captures the real PreToolUse payloads:
whether `agent_type` reaches a hook at all and, more to the point, HOW the CLI spells it, since
the router matches that string exactly; the spawn tool's real naming; and the `system:init`
payload, whose own tool list is the only artifact that says whether `tools=` restricts the
session or merely proposes a set.

The message stream is recorded rather than discarded. An earlier version of this script iterated
`receive_response()` into `_`, which threw away the init payload spec 2.3 names as a capture
source and left half the session unobserved.

The one thing spec 2.3 attributes to this smoke that it does NOT produce: the background evidence
PAIR needs two runs whose `background` settings differ, and this is one run against one topology,
where every AgentDefinition sets `background=False`. This run produces that half. The other half -
`background` unset, the field dropped on serialisation, the subagent's tool list silently stripped
- needs a run against a deliberately-unset definition and is left visibly unproduced. The "ask"
surfacing fixture likewise belongs to the first session that owns a send tool, which this one
deliberately does not.
"""
from __future__ import annotations
import asyncio, json, os, platform, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "payloads"

#: The one path segment that names a person. Not anchored: a home path can sit inside a longer
#: string as easily as at its start.
_HOME_SEGMENT = re.compile(r"([A-Za-z]:\\Users\\|/home/|/Users/)[^\\/]+")

def _cli_version() -> str:
    """The version of the binary the SDK will actually spawn, asked of that binary.

    Not a constant. `_find_cli` prefers the CLI bundled inside the installed SDK and only then
    falls back to PATH, and on a machine with its own install those are two different versions -
    so a hardcoded stamp is a claim about a payload it did not witness. The stamp exists to say
    which versions produced these fixtures; it may not be the one thing in them that is guessed.
    """
    import claude_agent_sdk
    name = "claude.exe" if platform.system() == "Windows" else "claude"
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    exe = str(bundled) if bundled.is_file() else shutil.which("claude")
    if not exe:
        return "unknown"
    done = subprocess.run([exe, "--version"], capture_output=True, text=True)
    head = done.stdout.split() if done.returncode == 0 else []
    return head[0] if head else "unknown"

def _redact(node, key: str = ""):
    """Mask the operator's user path segment wherever it appears; return the value and the notes.

    Done at write time rather than by hand afterwards. A capture is written once, under a
    `finally`, because a live run is not repeatable - and a manual cleanup step after an
    unrepeatable run is a step that can be forgotten. The edit is narrow on purpose, and it is
    declared in the fixture's own meta, because an undeclared edit is what makes a capture
    unusable as evidence.
    """
    if isinstance(node, str):
        masked = _HOME_SEGMENT.sub(lambda m: m.group(1) + "<user>", node)
        note = [f"{key}: user path segment replaced with <user>"] if masked != node else []
        return masked, note
    if isinstance(node, dict):
        out, notes = {}, []
        for k, v in node.items():
            value, found = _redact(v, k)
            out[k] = value
            notes += found
        return out, notes
    if isinstance(node, list):
        out, notes = [], []
        for v in node:
            value, found = _redact(v, key)
            out.append(value)
            notes += found
        return out, notes
    return node, []

def _write(path: Path, payload, stamp: dict) -> None:
    payload, notes = _redact(payload)
    meta = {"captured": stamp}
    if notes:
        meta["redacted"] = sorted(set(notes))
    path.write_text(json.dumps({"meta": meta, "payload": payload}, indent=1), encoding="utf-8")

def _refuse_if_a_send_tool_exists(options) -> None:
    """This smoke's whole claim is that nothing in its session CAN ask.

    Checked here, before the client is constructed, so a mistake in the check itself costs no
    tokens. The tool name is imported from its one home rather than respelled. `mcp_servers` is
    read too: the session roster is not the only door a send tool could come through.
    """
    from retinue.boundary.hook import SEND_TOOLS
    rosters = [options.tools or [], options.allowed_tools or []]
    rosters += [d.tools or [] for d in (options.agents or {}).values()]
    named = sorted({t for roster in rosters for t in roster} & SEND_TOOLS)
    if named or options.mcp_servers:
        raise SystemExit(f"not a send-free session: tools={named}, "
                         f"mcp_servers={options.mcp_servers}")

def _summarise(messages) -> None:
    """The stream, as shapes. The bodies live in the session transcript on disk; what this run
    needs from them is which messages arrived and what the tool calls were."""
    for m in messages:
        line = type(m).__name__
        subtype = getattr(m, "subtype", None)
        if subtype:
            line += f" subtype={subtype}"
        blocks = getattr(m, "content", None)
        if isinstance(blocks, list):
            kinds = [f"{type(b).__name__}({getattr(b, 'name', '')})".replace("()", "")
                     for b in blocks]
            line += f" blocks={kinds}"
        print(f"  {line}")

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: capture smoke is manual and keyed; not running.")
        return 0
    import claude_agent_sdk
    from claude_agent_sdk import ClaudeSDKClient, SystemMessage
    from retinue.boundary.hook import pre_tool_use
    from retinue.orchestration.topology import SESSION_TOOLS, build_options

    stamp = {"sdk": claude_agent_sdk.__version__, "cli": _cli_version()}
    captured: list[dict] = []
    messages: list = []

    async def recording_hook(input_data, tool_use_id, context):
        captured.append(input_data)
        return await pre_tool_use(input_data, tool_use_id, context)

    options = build_options(recording_hook)
    _refuse_if_a_send_tool_exists(options)
    OUT.mkdir(parents=True, exist_ok=True)
    # The subagent reads through the CLI's working directory, and the frozen fixtures record
    # repo-relative paths. Both follow from running the session from the repository root rather
    # than from wherever the script was invoked.
    os.chdir(ROOT)
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Use the research agent to summarise fixtures/docs/doc-1.md")
            async for message in client.receive_response():
                messages.append(message)
    finally:
        # Written in `finally`: a live capture is not repeatable for free, and payloads held only
        # in a local list are lost with the process on an interrupt, a timeout or a transport
        # error - which are exactly the runs whose payloads are worth having.
        for i, payload in enumerate(captured):
            _write(OUT / f"captured_{i:02d}.json", payload, stamp)
        init = next((m.data for m in messages
                     if isinstance(m, SystemMessage) and m.subtype == "init"), None)
        if init is not None:
            _write(OUT / "captured_init.json", init, stamp)
        print(f"captured {len(captured)} hook payloads and {len(messages)} messages into {OUT}")
        _summarise(messages)
        print("\ndeclared SESSION_TOOLS:", list(SESSION_TOOLS))
        print("init tool list        :", json.dumps((init or {}).get("tools")))
        print("init keys             :", sorted(init or {}))
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
