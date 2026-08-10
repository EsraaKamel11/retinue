"""The P1 live capture smoke (spec 2.3). RETINUE_LIVE=1 gated; never imported by tests; run
manually, once; its outputs are the canonical captured fixtures the default lane replays.

Session shape: orchestrator + research subagent ONLY - no send tool exists anywhere in the
session, so this run cannot ask and does not try to. It captures the real PreToolUse payloads:
whether `agent_type` reaches a hook at all and, more to the point, HOW the CLI spells it, since
the router matches that string exactly; and the spawn tool's real naming.

Two things spec 2.3 also attributes to this smoke are NOT produced by this script, and are left
visibly unproduced rather than quietly approximated. The background evidence PAIR needs two runs
whose `background` settings differ, and this is one run against one topology. The "ask" surfacing
fixture belongs to the first session that owns a send tool, which this one deliberately does not.
"""
from __future__ import annotations
import asyncio, json, os, platform, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "payloads"

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

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: capture smoke is manual and keyed; not running.")
        return 0
    import claude_agent_sdk
    from claude_agent_sdk import ClaudeSDKClient
    from retinue.boundary.hook import pre_tool_use
    from retinue.orchestration.topology import build_options

    stamp = {"sdk": claude_agent_sdk.__version__, "cli": _cli_version()}
    captured: list[dict] = []

    async def recording_hook(input_data, tool_use_id, context):
        captured.append({"meta": {"captured": stamp}, "payload": input_data})
        return await pre_tool_use(input_data, tool_use_id, context)

    options = build_options(recording_hook)
    _refuse_if_a_send_tool_exists(options)
    OUT.mkdir(parents=True, exist_ok=True)
    # The subagent reads through the CLI's working directory, and the frozen fixtures record
    # repo-relative paths. Both follow from running the session from the repository root rather
    # than from wherever the script was invoked; an absolute path in the prompt would write this
    # machine's home directory into a tracked fixture instead.
    os.chdir(ROOT)
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Use the research agent to summarise fixtures/docs/doc-1.md")
            async for _ in client.receive_response():
                pass
    finally:
        # Written in `finally`: a live capture is not repeatable for free, and payloads held only
        # in a local list are lost with the process on an interrupt, a timeout or a transport
        # error - which are exactly the runs whose payloads are worth having.
        for i, item in enumerate(captured):
            (OUT / f"captured_{i:02d}.json").write_text(json.dumps(item, indent=1), encoding="utf-8")
        print(f"captured {len(captured)} payloads into {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
