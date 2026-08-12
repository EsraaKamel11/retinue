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
#: Drift is loud rather than silent, and how loud is the part a triager actually gets. Break the
#: agreement between this pattern and the tags the import emits and this matches nothing, every
#: draft fails closed, and the SUITE goes 20 red. Only 2 of those name the cause: they assert on
#: `candidate_draft_body` and report `assert None == <the body>`. NONE of the other 18 names it.
#: They report the checker down - `no frozen verdict for this draft`, which says that and not why -
#: or they fail on a consequence of it: an allow that came back False, an empty ledger tuple, a
#: routing category set, a violation class that arrived as `other`. Those two groups are
#: deliberately not split into integers, because where one ends and the other begins depends on how
#: far pytest elided a repr in the run being read, and a number that moves with the eliding is not
#: a measurement. The 2 and the 18 do not move with it.
#:
#: An earlier version of this row counted `tests/boundary/test_checker_lane.py` ALONE, where the
#: split is 5 red, 3 and 2, and offered that 3:2 as the ratio a triager gets. True of that one
#: file, and not what the run reports: the fifteen further tests that read this extraction were
#: added after that sentence and every one of them landed on the silent side. Measured suite-wide
#: over 249 collected, and the integers move with the suite while the shape does not - two rows
#: name the extraction because two rows assert on it, and every other red is a consequence. There
#: is DELIBERATELY no standing promise here to re-measure on each added test. That promise is
#: exactly what rotted, and re-arming it would buy the same rot a second time.
#:
#: What M8 renames is the tag HERE, which is one side of that agreement. An earlier version of this
#: sentence said "rename either tag upstream", naming the side the row does NOT touch. Both sides
#: land on the same five tests, because the tests read the import's real output rather than a copy
#: of it, so the count is right either way. The measured direction is this one, and a sentence that
#: names the unmeasured direction is a claim standing on a row that did not test it.
_CANDIDATE_DRAFT = re.compile(r"<candidate_draft>\n(.*)\n</candidate_draft>", re.DOTALL)

#: Every structural delimiter `build_checker_messages` emits. A frozen row whose body carries any
#: of them is refused at load, because the span starts at the LEFTMOST opener: a counterparty who
#: writes an opener into the thread makes the span begin there and run through the real block, so a
#: row body shaped like that span is a key they can synthesise from their own text.
_PROMPT_TAGS = ("<transmitted_thread>", "</transmitted_thread>", "<candidate_draft>",
                "</candidate_draft>", "<cited_records>", "</cited_records>")

def candidate_draft_body(messages: list[dict]) -> str | None:
    """The draft body read back out of the checker prompt, or None when the prompt carries no
    candidate-draft block in the shape this module was written against.

    None keys no row and the caller fails closed, and that holds BECAUSE `scripted_transport`
    refuses a non-string body at load, not because None is unusual. Without that refusal a row with
    a null body keys `table[None]` and becomes a catch-all answering every prompt this function
    cannot read, which composed with a renamed delimiter upstream is every draft there is.

    Named and public because it IS the coupling: a test can pin it against the import that emits
    the prompt, and a reader looking for what ties this module to the checker's wording finds one
    function rather than a regular expression buried in a closure.

    A LIVENESS LEVER THE COUNTERPARTY HOLDS, named because it is real and left open on purpose. A
    thread carrying the literal opening delimiter and a newline moves the leftmost opener into the
    thread and widens the span on EVERY draft, so a covered and entirely clean draft resolves to no
    row and comes back `CheckerUnavailable`. That is the fail-closed direction: the lever can stop
    a message being sent and can never cause one to be sent. Closing it would mean anchoring on the
    LAST opener instead of the first, and that trade is refused - the draft body is the drafting
    model's own text, so an opener inside the body would then NARROW the span to a suffix of what
    was written, and narrowing is the direction that answers a long draft with a short row's
    verdict. An availability lever held by the counterparty is the better of the two, and it is the
    one this module takes.
    """
    found = _CANDIDATE_DRAFT.search(messages[0]["content"])
    return found.group(1) if found else None

def _result_for(row: dict) -> CheckerResult:
    """One frozen row as the result it replays. Called at LOAD, never at the call."""
    if "flag" in row:
        return FlagForReview(reason=row["flag"])
    vc = ViolationClass(row["violation_class"]) if row.get("violation_class") else None
    return Verdict(violates=row["violates"], violation_class=vc,
                   confidence=row["confidence"], span=row.get("span"))

def scripted_transport(path: Path) -> Callable[[list[dict]], CheckerResult]:
    """Replay frozen verdicts keyed by the EXACT draft body; anything else fails closed.

    A dict rather than a scan, which is what removes the first-match-wins hazard structurally
    rather than detecting it: there is no ordering for a shorter row to win by. What a dict cannot
    remove is what goes INTO its keys, so the loop below refuses three shapes, each demonstrated
    against this module rather than supposed:

    - **A non-string body.** `candidate_draft_body` returns None for a prompt it cannot read, so a
      null body keys `table[None]` and answers every one of those clean.
    - **A body carrying the prompt's own delimiters.** The span starts at the leftmost opener, so a
      counterparty writing one into the thread synthesises exactly such a key out of their own text.
    - **A body a previous row already claimed**, for the reason the imported replay gives in its own
      words at `chaperone.testing.recorded.replay_over_corpus`: a key two rows share silently drops
      one, and the row that lost is answered by the verdict recorded for the row that won.

    Every row is turned into its `CheckerResult` HERE rather than at the call, so a fixture built
    wrong reddens on construction instead of on whichever draft happens to reach the bad row. Left
    to the call, a missing key or an out-of-range confidence raises inside the imported retry loop,
    which spends the whole budget and arrives as `CheckerUnavailable` naming a JSON key: fail
    closed, so the cost is diagnosis rather than safety, and still this module's own stated standard
    unmet. The refusals are all one exception type, so a fixture built wrong reads as one thing.
    """
    table: dict[str, CheckerResult] = {}
    for row in json.loads(Path(path).read_text(encoding="utf-8"))["verdicts"]:
        body = row.get("body")
        if not isinstance(body, str):
            raise ValueError(f"a frozen row's body must be a string, not "
                             f"{type(body).__name__}; a null body would key every prompt the "
                             "extraction cannot read")
        carried = [t for t in _PROMPT_TAGS if t in body]
        if carried:
            raise ValueError(f"the frozen row for {body!r} carries the prompt's own delimiter "
                             f"{carried[0]!r}; a forged opener in the thread would synthesise "
                             "its key out of counterparty text")
        if body in table:
            raise ValueError(f"two frozen verdicts share the body {body!r}; one would "
                             "silently answer for the other")
        try:
            table[body] = _result_for(row)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"the frozen row for {body!r} is not a usable verdict: "
                             f"{exc!r}") from exc
    def transport(messages: list[dict]) -> CheckerResult:
        result = table.get(candidate_draft_body(messages))
        if result is None:
            raise CheckerUnavailable(
                "no frozen verdict for this draft; the scripted lane never invents a clean")
        return result
    return transport

def build_checker(transport: Callable[[list[dict]], CheckerResult]) -> Checker:
    return Checker(CHECKER_TIER, TIERS["drafting"], transport)

def register_of(result: CheckerResult) -> Register:
    if isinstance(result, FlagForReview):
        return "UNVERIFIABLE"
    return "EXCEPTION" if result.violates else "CLEAN"
