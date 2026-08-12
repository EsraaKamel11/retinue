"""The P4 live demo (spec 9). RETINUE_LIVE=1 gated; never imported by tests; run manually.

Two obligations, in order, and the order is the whole design:

1. ASSERT THE OFFER. The send tool must appear in the session's `system:init` tool list BEFORE any
   claim about gating is made. CONTAINMENT IS NEVER DEMONSTRATED BY THE ABSENCE OF THE THING BEING
   CONTAINED: a session where no send tool was ever offered produces the same silence as a session
   where one was offered and held, and the P1 smoke has already shown what that silence looks like.
   The demo ABORTS if the tool was not offered, writes nothing, and says so on stderr.
2. CAPTURE THE ASK. The first session in which a send tool exists is the first one that can capture
   how "ask" surfaces, so that payload is written as the canonical fixture the default lane replays.

Exit codes, because the two ways of not finishing are different facts: 0 the ask was captured,
1 the send tool was NEVER OFFERED (obligation 1 failed, and nothing here demonstrates anything),
2 the tool was offered and the conversation lane made no send (obligation 1 met, no ask to
capture, re-run). That wording is the branch's own: "offered and never called" would be a
containment claim resting on a count this script does not take, and the exit-2 branch below says
so where it prints.

**Nothing is written under a `finally`, and that is a deliberate difference from the P1 smoke.**
That script writes in a `finally` because a live capture is not repeatable and payloads held in a
local list die with the process. Here the offer assertion has to PRECEDE the write, so a `finally`
would hand a fixture to a run that failed obligation 1 - which is the one outcome this file exists
to refuse. The cost is paid instead by printing the captured payloads, redacted, on EVERY way out
that is not a successful write: the offer abort, the no-ask exit, and a torn session. That last one
is why the printing sits in an `except` around the session rather than after it - a transport error
or an interrupt is exactly the run whose payloads are worth having, and prints placed after the
`async with` never execute for it.

The send tool is registered through the pinned SDK's own in-process tool mechanism
(`create_sdk_mcp_server`). This is the SDK's custom-tool surface, not the rejected external
MCP-configuration surface (spec 10) - the distinction is stated here because a reader will
reasonably ask.

**What this demo does NOT wire, stated because `topology.py` asks it directly.** The tool body
performs no outbound act: no transport, no gateway, no `attempt_send`. It is a capture instrument,
and the reason it is not the chokepoint's first agent caller is in the body's own comment.

Adaptation points, named at SDK 0.2.130 rather than hidden: the `tool` decorator's schema argument;
the `mcp_servers` kwarg; and where the `system:init` tool list appears on the message object, which
is `SystemMessage.data["tools"]` and NOT an attribute - a `getattr(message, "tools", None)` reads
None from every message in the stream, leaves the offered list empty and makes the demo abort on
every run, reporting a containment failure that never happened. The run itself is the witness for
all three, and any mismatch is fixed HERE, never by weakening the offer assertion.
"""
from __future__ import annotations
import asyncio, dataclasses, json, os, platform, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "payloads" / "captured_ask.json"

#: The smoke's redaction, respelled rather than imported. `scripts/` is not a package and both
#: scripts are invoked by path, so `from scripts.capture_smoke import _redact` resolves for some
#: launch commands and not others, which is a poor dependency for a manual keyed run. The redaction
#: CONTRACT is enforced on the output instead of on the source: `home_path_without_redaction` in
#: tests/test_fixture_meta.py reddens for any `captured_` fixture carrying a home path that its own
#: meta does not declare, and it reads this script's output exactly as it reads the smoke's.
_HOME_SEGMENT = re.compile(r"([A-Za-z]:\\Users\\|/home/|/Users/)[^\\/]+")

def _cli_version() -> str:
    """The version of the binary the SDK will actually spawn, asked of that binary.

    Not a constant, for the reason the smoke gives: `_find_cli` prefers the CLI bundled inside the
    installed SDK and only then falls back to PATH, so a hardcoded stamp is a claim about a payload
    it did not witness. The stamp exists to say which versions produced this fixture; it may not be
    the one thing in it that is guessed.
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
    """Mask the operator's user path segment wherever it appears; return the value and the notes."""
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

def _dump(why: str, captured: list) -> None:
    """Payloads to stderr, redacted, written nowhere.

    Redacted because stderr from a manual run gets pasted into reports and issues, and the operator's
    transcript path is in every payload. Written nowhere because none of the callers has passed the
    offer assertion, and a fixture is what this script hands over only when that assertion holds.
    """
    print(f"{why}: {len(captured)} hook payloads, unwritten:", file=sys.stderr)
    print(json.dumps(_redact(captured)[0], indent=1), file=sys.stderr)

def _write(path: Path, payload, stamp: dict) -> None:
    payload, notes = _redact(payload)
    meta = {"captured": stamp}
    if notes:
        meta["redacted"] = sorted(set(notes))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": meta, "payload": payload}, indent=1), encoding="utf-8")

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: the demo is manual and keyed; not running.")
        return 0
    import claude_agent_sdk
    # No HookMatcher here: `build_options` wraps the hook in one, and importing the name to leave it
    # unused would read as a second, competing registration.
    from claude_agent_sdk import ClaudeSDKClient, SystemMessage, tool, create_sdk_mcp_server
    from retinue.boundary.hook import SEND_TOOL, SEND_TOOLS, pre_tool_use
    from retinue.orchestration.topology import SESSION_TOOLS, build_options

    #: The server is registered under the name the GATED SPELLING already carries, rather than
    #: under a literal typed here a second time. The CLI composes `mcp__<server>__<tool>`, so
    #: deriving the server from that spelling makes the tool the CLI offers the tool the hook gates
    #: by construction, and leaves the offer assertion measuring the thing that can actually go
    #: wrong: whether the tool was offered AT ALL. The session roster intersects every declared
    #: roster, so a tool can be declared, served, and silently stripped before anyone sees it.
    mcp_send = next(t for t in sorted(SEND_TOOLS) if t.startswith("mcp__"))
    server_name = mcp_send.split("__")[1]

    captured: list[dict] = []
    reached: list[dict] = []

    @tool(SEND_TOOL, "Send the approved outbound message.", {"body": str})
    async def send_message(args):
        """No transport, no gateway, no `attempt_send`, and the omission is the answer to the
        paragraph `topology.py` addresses to this task.

        Wiring the chokepoint here would build a gateway, checker, registry, queues, store and
        ActContext inside a manual script, and the first execution of all of it would be a live run
        nobody has done. This demo's subject is what happens BEFORE the tool body: the hook answers
        "ask" for conversation on this name, so on the path being demonstrated the body does not run
        at all. A body that recorded a call it never receives, while claiming to be the chokepoint's
        first agent caller, would be a claim about an unexecuted path.

        It is not silent, though. Every entry here is a call that got past the gate, which is a fact
        worth having from a run whose whole thesis is that none should.
        """
        reached.append(args)
        return {"content": [{"type": "text",
                             "text": "the demo's send tool performs no act and sent nothing"}]}

    server = create_sdk_mcp_server(name=server_name, tools=[send_message])

    async def recording_hook(input_data, tool_use_id, context):
        captured.append(input_data)
        return await pre_tool_use(input_data, tool_use_id, context)

    #: `build_options` rather than a hand-built ClaudeAgentOptions, so the demo runs the topology
    #: the repository describes: the SESSION_TOOLS ceiling that Task 22 widened to let a send tool
    #: survive the roster intersection, and `setting_sources=[]`, without which one operator's
    #: ambient configuration reaches the session and the fixture stops being canonical. An options
    #: object built here instead would omit both and the offer it asserted would belong to a
    #: different session shape than the one `topology.py` documents. `mcp_servers` is added by
    #: `replace` rather than by a new parameter on `build_options`: that function is imported by the
    #: default offline lane, and a live-only server argument does not belong in its signature.
    options = dataclasses.replace(build_options(recording_hook),
                                  mcp_servers={server_name: server})

    stamp = {"sdk": claude_agent_sdk.__version__, "cli": _cli_version()}
    messages: list = []
    os.chdir(ROOT)
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query("Use the conversation agent to send inv-demo a one-line follow-up.")
            async for message in client.receive_response():
                messages.append(message)
    except BaseException:
        # Print and RE-RAISE. Nothing is written and nothing is swallowed: the offer assertion below
        # never ran, so no fixture has been earned, and a torn session is not a demo result.
        _dump("the session did not finish", captured)
        raise

    init = next((m.data for m in messages
                 if isinstance(m, SystemMessage) and m.subtype == "init"), None)
    offered = list((init or {}).get("tools") or ())

    # OBLIGATION 1, and nothing below it runs until it holds.
    if not (set(offered) & SEND_TOOLS):
        print("ABORT: the send tool was never OFFERED in system:init - nothing here demonstrates "
              "gating, and this demo refuses to pretend otherwise.", file=sys.stderr)
        print(f"  system:init seen : {init is not None}", file=sys.stderr)
        print(f"  offered          : {offered}", file=sys.stderr)
        print(f"  declared ceiling : {list(SESSION_TOOLS)}", file=sys.stderr)
        print(f"  gated spellings  : {sorted(SEND_TOOLS)}", file=sys.stderr)
        # Printed rather than written: an aborted run loses the file and not the evidence.
        _dump("the offer was never made", captured)
        return 1
    print(f"OFFER ASSERTED: {sorted(set(offered) & SEND_TOOLS)} resolved into system:init")
    print(f"  full init tool list: {offered}")

    # OBLIGATION 2. Selected on the payload's OWN routing facts and never on the hook's answer:
    # picking "whatever the hook asked about" would make the replay test read its expectation out of
    # the decision it is checking. A main-thread call to a send name lands in `captured` too and
    # `decide` answers "allow" for it, so a filter on the tool name alone can write a payload the
    # replay test then fails on, correctly, for a capture that was fine.
    asks = [c for c in captured
            if isinstance(c, dict) and c.get("agent_type") == "conversation"
            and c.get("tool_name") in SEND_TOOLS]
    print(f"captured {len(captured)} hook payloads; {len(asks)} are conversation sends; "
          f"the tool body was reached {len(reached)} times")
    if not asks:
        # The sentence names what was measured and nothing wider. `asks` counts CONVERSATION sends,
        # so an empty `asks` says the conversation lane made none - it does NOT say the tool went
        # uncalled, because the widened ceiling makes a main-thread call reachable and `reached`
        # may be non-empty on exactly this branch. An earlier version of this line said "offered
        # and never called", which is a containment claim resting on a count that was not taken,
        # in a script whose whole thesis is that containment is never demonstrated by absence.
        print(f"the send tool was offered; the conversation lane made no send. The tool body was "
              f"reached {len(reached)} times, which this run does not attribute to a lane. "
              "There is no ask to capture.", file=sys.stderr)
        _dump("no conversation send", captured)
        return 2
    _write(OUT, asks[0], stamp)
    print(f"captured the ask fixture into {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
