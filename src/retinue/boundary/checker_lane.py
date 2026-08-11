"""Checker construction + the scripted transport. The transport is the seam (spec 2.3): scripted
frozen verdicts by default; a live transport exists only in capture scripts. The ordering
guarantee (checker never weaker than the drafter) is ENFORCED BY THE IMPORT at construction -
this module states the tiers and lets the imported assert do the holding. Register mapping per
spec 1: a violation verdict is an EXCEPTION; a flag-for-review is UNVERIFIABLE."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Callable, Literal
from chaperone.gates.checker import (Checker, CheckerResult, CheckerUnavailable, FlagForReview,
                                     Verdict)
from chaperone.policy.types import ViolationClass
from retinue.orchestration.topology import TIERS

CHECKER_TIER = "sonnet-tier"     # >= TIERS["drafting"]; construction raises otherwise

Register = Literal["EXCEPTION", "UNVERIFIABLE", "CLEAN"]

#: The delimiters `build_checker_messages` wraps the draft body in, and the ONE place this module
#: couples to that prompt's shape. The replay is keyed by draft body, so the body has to be read
#: back out of a prompt that also carries the checker instructions, the transmitted thread and the
#: cited records - and the import interpolates all of them unescaped, which it says so in its own
#: docstring. Matching a row against the whole prompt instead is answered by any of those four:
#: a body the counterparty quoted into the thread resolves an unknown draft to a frozen verdict,
#: which is the fail-closed guarantee breaking on text nobody here wrote.
#:
#: GREEDY, and that is the safety property rather than a default. `search` takes the LEFTMOST
#: opening delimiter and `.*` runs to the RIGHTMOST closing one, so the captured span always
#: CONTAINS the real body: a forged delimiter in the draft can only make this read more than was
#: written, never a prefix of it. More matches no row and fails closed. A prefix would answer a
#: long draft with a short row's verdict, which is the direction that must not exist. Made
#: non-greedy, `test_a_draft_forging_the_closing_delimiter_answers_for_no_frozen_row` reddens.
#:
#: Drift is loud rather than silent: rename either tag upstream and this matches nothing, every
#: draft fails closed, and four tests go red - three of them reporting a checker that is down, and
#: `test_the_extraction_reads_the_body_the_import_actually_emits` naming the actual cause.
_CANDIDATE_DRAFT = re.compile(r"<candidate_draft>\n(.*)\n</candidate_draft>", re.DOTALL)

def candidate_draft_body(messages: list[dict]) -> str | None:
    """The draft body read back out of the checker prompt, or None when the prompt does not carry
    one in the shape this module was written against. None keys no row, so the caller fails closed.

    Named and public because it IS the coupling: a test can pin it against the import that emits
    the prompt, and a reader looking for what ties this module to the checker's wording finds one
    function rather than a regular expression buried in a closure.
    """
    found = _CANDIDATE_DRAFT.search(messages[0]["content"])
    return found.group(1) if found else None

def scripted_transport(path: Path) -> Callable[[list[dict]], CheckerResult]:
    """Replay frozen verdicts keyed by the EXACT draft body; anything else fails closed.

    A dict rather than a scan, which is what removes the first-match-wins hazard structurally
    rather than detecting it: there is no ordering for a shorter row to win by. What a dict cannot
    remove is two rows spelling the same body, so that is refused where the table is built. The
    imported replay refuses it for the same reason and in its own words at
    `chaperone.testing.recorded.replay_over_corpus` - a key two rows share silently drops one, and
    the row that lost is answered by the verdict recorded for the row that won. At load rather
    than at the call, so a fixture built wrong reddens on construction instead of on whichever
    draft happens to reach the duplicate.
    """
    table: dict[str, dict] = {}
    for row in json.loads(Path(path).read_text(encoding="utf-8"))["verdicts"]:
        if row["body"] in table:
            raise ValueError(f"two frozen verdicts share the body {row['body']!r}; one would "
                             "silently answer for the other")
        table[row["body"]] = row
    def transport(messages: list[dict]) -> CheckerResult:
        row = table.get(candidate_draft_body(messages))
        if row is None:
            raise CheckerUnavailable(
                "no frozen verdict for this draft; the scripted lane never invents a clean")
        if "flag" in row:
            return FlagForReview(reason=row["flag"])
        vc = ViolationClass(row["violation_class"]) if row.get("violation_class") else None
        return Verdict(violates=row["violates"], violation_class=vc,
                       confidence=row["confidence"], span=row.get("span"))
    return transport

def build_checker(transport: Callable[[list[dict]], CheckerResult]) -> Checker:
    return Checker(CHECKER_TIER, TIERS["drafting"], transport)

def register_of(result: CheckerResult) -> Register:
    if isinstance(result, FlagForReview):
        return "UNVERIFIABLE"
    return "EXCEPTION" if result.violates else "CLEAN"
