"""Frozen-judge replay. Judged once live (scripts/judge_capture.py), frozen, replayed forever -
the LLM judge never runs in CI, on determinism grounds (spec 2.3). Calibration and discrimination
are SEPARATE checks with separate names and units; a shared number would conflate whether the
judge knows what it knows with whether the score ranks violations below compliance.

The two functions disagree about what an empty input means, and the disagreement is deliberate
rather than an oversight left lying about. `calibration_agreement` returns 0.0 when nothing clears
the floor because a judge confident of nothing has FAILED to be calibrated, not passed.
`discrimination_gap` returns 0.0 when a side is missing because no comparison was available - a
value it shares with a genuinely equal pair, which a reader of a report cannot tell apart from the
number alone. It is still the right value there: the alternative is a ZeroDivisionError raised
inside an evaluator over the shape of a fixture, trading an ambiguous number for a dead run.
"""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

class FrozenVerdict(BaseModel):
    """One judged draft, immutable from the moment it is loaded.

    Frozen because a replay hands the same records to every consumer in a run: a verdict an
    evaluator could assign to lets one consumer's edit silently become what the next one scores,
    and the file on disk then describes something other than the numbers in the report.
    """
    model_config = ConfigDict(frozen=True)
    case: str
    violates: bool
    confidence: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)

def load_verdicts(path: Path) -> dict[str, FrozenVerdict]:
    """The frozen verdicts, keyed by case. Reads one file and opens nothing else.

    Two rows naming one case would collapse into one entry with the later silently winning, and
    nothing downstream could tell: the set of keys is unchanged, so a coverage check still passes,
    and both metrics score the survivor as though it had been the only verdict. A capture is the one
    writer that can produce it, so the refusal belongs here at the load rather than in a reader.
    """
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["verdicts"]
    verdicts = {r["case"]: FrozenVerdict(**r) for r in rows}
    if len(verdicts) != len(rows):
        raise ValueError(f"{path}: {len(rows)} verdicts over {len(verdicts)} cases, so keying by "
                         "case would drop one of them without saying so")
    return verdicts

def calibration_agreement(verdicts: dict[str, FrozenVerdict], ground_truth: dict[str, bool],
                          *, floor: float = 0.7) -> float:
    """The fraction of CONFIDENT verdicts agreeing with the truth: does the judge know what it knows?

    The denominator is the confident verdicts and not all of them. Over a set where every verdict
    clears the floor the two denominators are the same number and a drift between them is invisible,
    which is why the test for this is written over a hand-built set holding a verdict below it.

    `ground_truth[v.case]` is left to raise. A verdict naming a draft that is not there is a
    corrupted replay, and a default would score it as agreement or disagreement by accident.
    """
    confident = [v for v in verdicts.values() if v.confidence >= floor]
    if not confident:
        return 0.0                      # no confident verdicts is a calibration FAILURE, not a pass
    agree = sum(1 for v in confident if v.violates == ground_truth[v.case])
    return agree / len(confident)

def discrimination_gap(verdicts: dict[str, FrozenVerdict], ground_truth: dict[str, bool]) -> float:
    """Mean compliant quality minus mean violating quality: does the score RANK violations below
    compliance?

    Means rather than sums, so the figure does not move with how many drafts of each kind the set
    happens to hold; compliant minus violating, so a positive number means the ranking is the right
    way round and the sign carries that claim rather than a convention.
    """
    compliant = [v.quality for v in verdicts.values() if not ground_truth[v.case]]
    violating = [v.quality for v in verdicts.values() if ground_truth[v.case]]
    if not compliant or not violating:
        return 0.0
    return sum(compliant) / len(compliant) - sum(violating) / len(violating)
