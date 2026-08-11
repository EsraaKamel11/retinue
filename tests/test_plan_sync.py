"""Double entry between the plan and the artifact it embeds.

The plan's Task 11 section carries `tools/battery.sh` verbatim in a fenced block, and the two were
kept in step by hand and then by a one-off script. Neither is a control: editing the plan instead
of the script, or the script instead of the plan, leaves a document describing an artifact that no
longer exists, and nothing says so. The topology's roster is held by the same mechanism for the
same reason - the fact is stated twice and a test holds the two spellings equal, so changing one
alone is a red suite rather than a quiet lie.

The battery is exactly the artifact this matters for: it is the document a reader consults to learn
what the repository checks, and a plan that describes gates the script no longer has is worse than
no plan at all.
"""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-08-10-retinue-implementation.md"
SCRIPT = ROOT / "tools" / "battery.sh"

HEADING = "### Task 11: README seed and the battery"
OPEN_FENCE = "```bash\n"
CLOSE_FENCE = "\n```\n"


def embedded_battery(plan_text: str) -> str:
    """The fenced bash block inside Task 11, or a raised failure naming what went missing.

    Every way of not finding the block RAISES rather than returning an empty string. An empty
    return would still compare unequal and still fail the test below, but it would fail saying the
    script had changed, which sends the next reader to the wrong file with the wrong question.
    """
    try:
        start = plan_text.index(HEADING)
    except ValueError:
        raise AssertionError(f"the plan no longer carries the section {HEADING!r}")
    try:
        body = plan_text.index(OPEN_FENCE, start) + len(OPEN_FENCE)
        end = plan_text.index(CLOSE_FENCE, body)
    except ValueError:
        raise AssertionError("the plan's Task 11 no longer embeds a fenced bash block")
    return plan_text[body:end]


def test_the_plan_embeds_the_battery_verbatim():
    """The claim "the plan matches what shipped" is worth exactly what enforces it."""
    # read_text uses universal newlines, which is what makes this robust rather than lucky: the
    # repository is authored on Windows with core.autocrlf=true and .gitattributes pins only *.sh,
    # so a fresh checkout materialises the plan with CRLF and the script with LF. The comparison is
    # about content; line-ending policy belongs to .gitattributes and is not relitigated here.
    block = embedded_battery(PLAN.read_text(encoding="utf-8"))
    # The fence consumes the block's final newline, so it is added back rather than stripped off
    # the script - stripping would let a stray trailing blank line in one file go unnoticed.
    assert block + "\n" == SCRIPT.read_text(encoding="utf-8"), (
        "the plan's embedded battery block and tools/battery.sh have drifted apart; "
        "re-copy the script into the plan's Task 11 block, or fix the script"
    )


def test_the_comparison_notices_a_one_character_mutation():
    """Without this, the rule above could be a helper agreeing with itself.

    A test that derived both sides from the same source, or an extractor that returned a constant,
    would pass over a drifted plan just as quietly as no test at all.
    """
    script = "#!/usr/bin/env bash\nset -u\nexit 0\n"
    plan = f"{HEADING}\n\nprose\n\n{OPEN_FENCE}{script[:-1]}{CLOSE_FENCE}more prose\n"
    assert embedded_battery(plan) + "\n" == script          # the honest copy passes
    drifted = plan.replace("set -u", "set -x")              # one character
    assert embedded_battery(drifted) + "\n" != script


def test_a_missing_section_or_fence_raises_rather_than_matching_nothing():
    """Absence of a block is not evidence the block agrees."""
    with pytest.raises(AssertionError, match="no longer carries the section"):
        embedded_battery("a plan without that heading\n")
    with pytest.raises(AssertionError, match="no longer embeds a fenced bash block"):
        embedded_battery(f"{HEADING}\n\nprose but no code block at all\n")
