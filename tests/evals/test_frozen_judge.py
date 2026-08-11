"""The frozen-judge replay, and the two separate numbers it is read through.

The judge runs once, live and keyed (`scripts/judge_capture.py`); the default lane replays what it
froze and opens no socket. Two families of test live here, split for the reason
`tests/evals/test_ranking.py` splits its own: the arithmetic of calibration and discrimination is
held over HAND-BUILT verdicts, so a definition that drifts reddens whatever the fixture later says,
and the fixture tests read `fixtures/` and read all of it.

What the fixture tests can and cannot say is stated in their names rather than left implied. Both a
draft's `ground_truth_violates` and a verdict's `violates` are this author's judgment, written by
hand in one sitting, so their agreement is arithmetic over two columns of one opinion - not a
measurement of a judge. That is precisely what a live capture buys, and until it runs the frozen
calibration figure is an internal-consistency check wearing a calibration name.
"""
import json
import pathlib
import socket
import pytest
from pydantic import ValidationError
from retinue.evals import frozen
from retinue.evals.frozen import (FrozenVerdict, calibration_agreement, discrimination_gap,
                                  load_verdicts)

FIX = pathlib.Path(__file__).resolve().parents[2] / "fixtures"
VERDICTS = FIX / "verdicts" / "judge_verdicts.json"

def truth() -> dict[str, bool]:
    """Every draft's ground truth, read off the drafts themselves and inferred from nothing."""
    rows = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((FIX / "drafts").glob("*.json"))]
    return {r["case"]: r["ground_truth_violates"] for r in rows}

def hand_built(*rows: tuple[str, bool, float, float]) -> dict[str, FrozenVerdict]:
    """Verdicts assembled here, deliberately not read off the frozen file.

    A probe built from that file would move whenever a capture moves it, and the arithmetic these
    rows pin is what has to hold whatever a judge later writes.
    """
    return {case: FrozenVerdict(case=case, violates=v, confidence=c, quality=q)
            for case, v, c, q in rows}

def test_the_replay_opens_no_socket(monkeypatch):
    """The default lane's whole claim (spec 2.3): the LLM judge never runs in CI.

    The brief's version of this test was named for the network and asserted key-set equality, which
    is an assertion passing for a reason it does not name - a `load_verdicts` that phoned a judge
    would satisfy it exactly as well. Here the socket constructor itself is replaced, so an attempt
    to open one raises inside the call under test instead of being inferred from a file's contents.

    The whole path runs - load, then both metrics - because any of the three could be the one that
    reaches for the network. What it asserts about the RESULTS is only that they are numbers, and
    that restraint is deliberate: the two frozen-set tests below own the values, and a capture that
    moves them must not redden a test about the network. A test that reddens for reasons outside
    its name is how a lane's real claim stops being legible.
    """
    def refuse(*args, **kwargs):
        raise AssertionError("the replay lane opened a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    v = load_verdicts(VERDICTS)
    assert isinstance(calibration_agreement(v, truth()), float)
    assert isinstance(discrimination_gap(v, truth()), float)

def test_every_draft_is_judged_and_nothing_else():
    """Coverage, and the precondition every fixture test below rests on.

    `calibration_agreement` reads `ground_truth[v.case]`, so a verdict naming a draft that is not
    there raises KeyError rather than returning a wrong number, and a draft carrying no verdict goes
    silently unjudged - a replay scoring a subset and reporting it as the whole set. Both directions
    are one set comparison, and it is first in the file because the rest are only meaningful once it
    holds.
    """
    assert set(load_verdicts(VERDICTS)) == set(truth())

def test_calibration_over_the_frozen_set_is_perfect_by_construction():
    """1.0, and the name carries why that number is not yet evidence about a judge.

    `ground_truth_violates` in `fixtures/drafts/` and `violates` in `fixtures/verdicts/` are both
    hand-authored by one author in one sitting, so agreement between them is arithmetic over two
    columns of the same opinion. No code mutation can turn this 1.0 into evidence about a judge,
    because both columns are one author's - but a mutation of the agreement comparison itself still
    reddens it, which is all this test can claim today. An earlier draft of this docstring said it
    could not fall to any code change at all, which was false and contradicted its own next sentence.

    What it does hold is that the two files stay consistent with each other and that the comparison
    drawn between them is the right one: edit one column, or invert the comparison, and this reddens.
    """
    assert calibration_agreement(load_verdicts(VERDICTS), truth(), floor=0.7) == 1.0

def test_discrimination_over_the_frozen_set_ranks_the_violating_draft_below():
    """Positive: the violating draft's quality sits below the compliant one's.

    Hand-authored on both sides like the calibration figure above, so this restates the fixture's
    own ordering rather than a scorer's. A capture is what turns it into a claim about a scorer.
    """
    assert discrimination_gap(load_verdicts(VERDICTS), truth()) > 0.0

def test_calibration_excludes_verdicts_below_the_confidence_floor():
    """The denominator is the CONFIDENT verdicts and never all of them.

    Built here rather than from the frozen file, and that is the load-bearing choice: every verdict
    in that file clears the floor, so `agree / len(verdicts)` and `agree / len(confident)` both
    return 1.0 over it and a drift between the two denominators goes unseen. The third row below is
    under the floor AND disagrees with the truth, which is the one shape where the two definitions
    part - 1.0 against two thirds. The same row catches a floor that stopped filtering at all.
    """
    v = hand_built(("agrees-a", False, 0.9, 0.8),
                   ("agrees-b", True, 0.85, 0.2),
                   ("unsure-c", False, 0.4, 0.5))
    ground = {"agrees-a": False, "agrees-b": True, "unsure-c": True}
    assert calibration_agreement(v, ground, floor=0.7) == 1.0

def test_the_confidence_floor_defaults_to_seven_tenths_inclusive():
    """Both sides of the boundary, straddling it exactly, read through the DEFAULT floor.

    Every other call in this file passes `floor=` explicitly, which pins the parameter and leaves
    the declared default a number no test would notice moving - and moving it silently changes what
    counts as a confident verdict, which is the entire denominator of calibration. A default no test
    exercises is not a contract.

    One verdict on one side of the floor pins the default only to a RANGE, and an earlier version of
    this test did exactly that: sitting at 0.65 it left a default anywhere in roughly (0.65, 0.90]
    unnoticed, and said nothing whatever about whether the comparison includes its own boundary. Two
    rows straddling the boundary exactly close all three questions at once:

      0.70 must be ADMITTED  -> a raised default reddens, and so does `>=` drifting to `>`
      0.69 must be EXCLUDED  -> a lowered default reddens

    Both verdicts AGREE with the truth, so exclusion by the floor is the only thing that can produce
    0.0 from either. The third line is the one call in this file passing a floor that is not 0.7,
    which is what keeps a `floor` parameter quietly hardcoded back to its own default from passing
    everywhere it is read.
    """
    on_the_floor = hand_built(("exactly-seven-tenths", False, 0.70, 0.5))
    just_under = hand_built(("just-under", False, 0.69, 0.5))

    assert calibration_agreement(on_the_floor, {"exactly-seven-tenths": False}) == 1.0
    assert calibration_agreement(just_under, {"just-under": False}) == 0.0
    assert calibration_agreement(just_under, {"just-under": False}, floor=0.6) == 1.0

def test_two_verdicts_for_one_case_are_refused_rather_than_collapsed(tmp_path):
    """Keying by case is what makes a dict the right return, and what makes a duplicate silent.

    Two rows naming one case collapse into one entry with the later quietly winning, and every other
    test here still passes: the set of KEYS is unchanged, so the coverage check holds, and both
    metrics score the survivor as though it had been the only verdict. `scripts/judge_capture.py` is
    the one writer that can produce this - it globs the drafts and trusts each file's own `case` - so
    the load refuses rather than picking a winner nobody asked it to pick.
    """
    doubled = tmp_path / "doubled.json"
    doubled.write_text(json.dumps({"meta": {"hand_authored": True}, "verdicts": [
        {"case": "same", "violates": False, "confidence": 0.9, "quality": 0.8},
        {"case": "same", "violates": True, "confidence": 0.9, "quality": 0.2}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_verdicts(doubled)

def test_no_confident_verdict_is_a_calibration_failure_not_a_pass():
    """0.0 when nothing clears the floor - the branch a vacuous pass would hide.

    Every verdict below agrees with the truth, so a `calibration_agreement` reading an empty
    confident set as "nothing disagreed, therefore perfect" returns 1.0 here and reports a
    calibrated judge on a judge that was sure of nothing. Written this way round on purpose: the
    correct answer and the vacuous one sit at opposite ends of the range.
    """
    v = hand_built(("timid-a", False, 0.2, 0.8), ("timid-b", True, 0.1, 0.2))
    assert calibration_agreement(v, {"timid-a": False, "timid-b": True}, floor=0.7) == 0.0

def test_discrimination_gap_is_a_difference_of_means_not_of_sums():
    """Mean compliant quality minus mean violating quality, in that order.

    The two sides hold different numbers of drafts on purpose: with one each a sum and a mean agree,
    and a metric that quietly began adding would go on reporting a plausible figure. Two compliant
    against one violating parts them - 0.5 against 1.2. The order of subtraction is the second
    claim: reverse it and a scorer ranking violations LAST scores as though it ranked them first.
    """
    v = hand_built(("ok-a", False, 0.9, 0.8), ("ok-b", False, 0.9, 0.6), ("bad-c", True, 0.9, 0.2))
    ground = {"ok-a": False, "ok-b": False, "bad-c": True}
    assert discrimination_gap(v, ground) == pytest.approx(0.5)

def test_discrimination_over_one_side_alone_is_not_a_gap():
    """A set with no violating draft has no ranking to measure, so the answer is 0.0.

    0.0 is also what a genuinely equal pair scores, and that ambiguity is worth naming rather than
    hiding: `calibration_agreement` returns 0.0 on ITS empty case to mean failure, this one returns
    it to mean no comparison was available, and a report cannot tell the two apart from the number.
    It is still the right value here - the alternative is a ZeroDivisionError raised inside an
    evaluator over the shape of a fixture, which trades an ambiguous number for a dead run.
    """
    only_compliant = hand_built(("ok-a", False, 0.9, 0.8), ("ok-b", False, 0.9, 0.6))
    assert discrimination_gap(only_compliant, {"ok-a": False, "ok-b": False}) == 0.0

def test_calibration_and_discrimination_never_share_a_result():
    """Two names, two numbers, two meanings (spec 7): one asks whether the judge knows what it
    knows, the other whether the score ranks violations below compliance. Conflating them blurs the
    two-lane thesis inside its own evidence.

    The identity line is a cheap pin on the API SHAPE and it is not what discriminates here: a
    `discrimination_gap` that merely called `calibration_agreement` is a distinct function object
    and sails straight past it. The probes below are what a merged implementation cannot satisfy.
    Each moves exactly one column of the same base set, and pins which number notices:

      flip `violates` -> calibration falls, the gap does not move (calibration reads violates)
      swap `quality`  -> the gap inverts, calibration does not move (the gap reads quality)

    No single function returns both pairs, so an implementation routing either through the other
    reddens on one probe or the other.
    """
    ground = {"ok-a": False, "bad-b": True}
    base = hand_built(("ok-a", False, 0.9, 0.8), ("bad-b", True, 0.9, 0.2))
    flipped = hand_built(("ok-a", False, 0.9, 0.8), ("bad-b", False, 0.9, 0.2))
    swapped = hand_built(("ok-a", False, 0.9, 0.2), ("bad-b", True, 0.9, 0.8))

    assert frozen.calibration_agreement is not frozen.discrimination_gap

    assert calibration_agreement(base, ground) == 1.0
    assert discrimination_gap(base, ground) == pytest.approx(0.6)

    assert calibration_agreement(flipped, ground) == 0.5              # violates moved: this noticed
    assert discrimination_gap(flipped, ground) == pytest.approx(0.6)  # ... and this did not

    assert calibration_agreement(swapped, ground) == 1.0              # quality moved: this did not
    assert discrimination_gap(swapped, ground) == pytest.approx(-0.6) # ... and this inverted

def test_a_loaded_verdict_cannot_be_edited():
    """Frozen means frozen: the replay hands out records, not scratch space.

    A verdict a consumer could assign to is a frozen fixture only until the first consumer edits it
    in memory, and everything downstream then scores a number nobody captured while the file on disk
    goes on describing something else. A raised `ValidationError` rather than a silent rebind is
    what `frozen=True` is there to buy.
    """
    verdict = next(iter(load_verdicts(VERDICTS).values()))
    with pytest.raises(ValidationError):
        verdict.quality = 0.99
