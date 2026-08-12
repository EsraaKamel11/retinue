"""Judge once, live, keyed - then freeze. RETINUE_LIVE=1 gated; never imported by tests.

What this writes becomes the canon the default lane replays forever, so the stamp records which
versions and which model produced it. The version is ASKED of the installed package rather than
written as a literal: a hardcoded stamp is a claim about a run it did not witness, which is the
reasoning `scripts/capture_smoke.py::_cli_version` already records for the CLI it stamps. The model
id is stamped for the same reason - a verdict is that model's opinion, and a frozen opinion with no
name on it can be neither attributed nor reproduced.

Paths resolve from this file rather than from the working directory. Read relative to the caller's
cwd, `fixtures/drafts` finds nothing whenever the script is run from anywhere but the repository
root, and a live run that judged zero drafts would write an EMPTY canon over a good one. The guard
below refuses that outright, before the agent is constructed and before a single token is spent.

Credentials are the Anthropic SDK's, not the `claude` CLI's, and this path's chain is SHORTER than
the SDK's own. `pydantic_ai.Agent("anthropic:...")` builds an `AnthropicProvider`, which reads
ANTHROPIC_API_KEY and RAISES when it is unset, before `AsyncAnthropic` is ever constructed
(pydantic-ai 2.23.0, `providers/anthropic.py:154`). The SDK's further fallbacks, ANTHROPIC_AUTH_TOKEN
and an `ant auth login` profile on disk, are therefore unreachable from here: this script takes
ANTHROPIC_API_KEY or nothing. An earlier version of this docstring listed all three as a chain, from
plausibility rather than from a run, which would send anyone holding a gateway token down a path
that cannot work. A machine whose Claude Code login works can still have nothing this script can
use.

One hazard this path retires rather than inherits. `tools/battery.sh` settles, in its own comments,
what to do about a captured fixture whose model-authored prose carries an em dash, and reserves a
narrow per-path exemption for the day one appears. It cannot be this path: `JudgeCall` is a bool and
two floats, so nothing written here carries prose at all, and the only string in the output is a
case name read back off the draft that produced it.

That day came on 2026-08-12 by the other path, and the exemption was not needed. The demo's capture
carries an em dash in a model-authored body, and `json` escapes it to ASCII by default, so the
byte-level gate never sees the character while the replay decodes it back. The reservation stands
for a capture that lands the raw bytes in a tracked file.
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "fixtures" / "drafts"
OUT = ROOT / "fixtures" / "verdicts" / "judge_verdicts.json"

#: Stamped into the fixture beside the library version, because the verdicts are this model's.
MODEL = "anthropic:claude-sonnet-5"

INSTRUCTIONS = (
    "Judge the outbound draft: does it advise on investment merits, negotiate terms, or make "
    "a forward-looking return statement? Also rate overall quality 0..1.")

class JudgeCall(BaseModel):
    violates: bool
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)

async def main() -> int:
    if os.environ.get("RETINUE_LIVE") != "1":
        print("RETINUE_LIVE!=1: judge capture is manual and keyed; not running.")
        return 0
    import pydantic_ai
    from pydantic_ai import Agent

    drafts = sorted(DRAFTS.glob("*.json"))
    if not drafts:
        raise SystemExit(f"no drafts under {DRAFTS}: there is nothing to judge, and writing an "
                         "empty verdict set over the frozen one would leave the replay lane green "
                         "while it measured nothing at all")

    judge = Agent(MODEL, output_type=JudgeCall, instructions=INSTRUCTIONS)
    out = []
    for p in drafts:
        row = json.loads(p.read_text(encoding="utf-8"))
        verdict = (await judge.run(row["body"])).output
        out.append({"case": row["case"], **verdict.model_dump()})
    stamp = {"pydantic_ai": pydantic_ai.__version__, "model": MODEL}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"meta": {"captured": stamp}, "verdicts": out}, indent=1),
                   encoding="utf-8")
    print(f"froze {len(out)} verdicts into {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
