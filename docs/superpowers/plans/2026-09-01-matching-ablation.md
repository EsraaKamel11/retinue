# Matching Ablation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure, once, over the pre-registered synthetic substrate, how many hard-excluded
candidates a similarity-driven shortlist admits when the imported eligibility filter is removed,
freeze the measurement as a sha-pinned artifact, and render it into the README without typing a
number.

**Architecture:** One measurement module (`src/retinue/matching/ablation.py`) holds the
pre-registered constants, the designed score, the three arms, the per-axis probe and the cell
metric, all calling the imported `classify`, `rank`, `relationship_score` and weights and deciding
nothing themselves. One script (`scripts/matching_ablation.py`) runs the study end to end into
`fixtures/ablation/matching_contamination.json` with a run date passed as an argument. Tests pin
the artifact's sha256, assert the spec's CI invariants, and re-run the generator against the
frozen artifact byte for byte. Documents move in the artifact's own commit and never before.

**Tech Stack:** Python 3.11+, the vendored `chaperone` wheel (`chaperone.matching.*`), stdlib
`hashlib` / `json` / `dataclasses` / `argparse`; pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-31-matching-ablation-design.md` (at 518e487 or later;
the binding authority - every conflict in this plan resolves against it, and section 6's
pre-registered values may not change after the run without a new dated spec).

## Global Constraints

- No policy or ranking logic in this repository: every eligibility verdict, every relationship
  score and every weight comes from the imported `chaperone.matching` modules; the ablation module
  is measurement wiring under `tools/fleet_audit.py` (which forbids only `chaperone.gates` and
  `chaperone.audit` imports outside `boundary/`; `chaperone.matching` is importable anywhere, and
  `src/retinue/matching/integrate.py` already does).
- Pre-registered, verbatim from the spec: `n = 10000`; seeds `1` through `10` inclusive; `K` in
  `{5, 10, 20}`; `NOW = datetime(2030, 3, 1, tzinfo=timezone.utc)`; the three mandates with
  `stage="seed"`, `sector="devtools"`, `geography="eu-west"` and (permissive: consented
  `{"US", "UK", "DE"}`, floor `"100000"`; jurisdiction-restricted: consented `{"US"}`, floor
  `"100000"`; jurisdiction-and-cheque-restricted: consented `{"US"}`, floor `"2000000"`); the
  score `designed_similarity` = 0.5 on sector match + 0.3 on stage match + jitter in [0, 0.2)
  from `sha256(candidate.id)`, candidate id as the final sort key; contamination counts
  `Eligibility.INELIGIBLE` only.
- Determinism: no network, no key, no clock read anywhere in the module or the script; the run
  date is an argument.
- The artifact's provenance is `hand_authored: true` with the spec's stated note; never
  `captured` (that word enters the fixture-meta family registry).
- Script filename contains none of the substrings `demo`, `capture_smoke`, `judge_capture`
  (the gated-script rule matches substrings of imported module names).
- Watched-red TDD: failing test first, run and record the failure line, implement, green. A mutant
  per new property, each watched red. Tests assert effects and properties, never proxies.
- Gates before EVERY commit, exit codes read unpiped, with the venv interpreter:
  `.venv/Scripts/python.exe -m pytest` AND `PYTHON=.venv/Scripts/python.exe bash tools/battery.sh`.
  Stage by name, never `add -A`. Subjects under 72 chars, narrative bodies, no trailers.
- No em dashes in authored files (spaced hyphens " - "); "judgment" without an e after the g; no
  word-bounded claim adjectives built on prov-; every rate beside its denominator; all figures
  synthetic and said so wherever they appear.
- Documents (README row, Results section, proposal section 15 preamble) move ONLY in Task 4, in
  the same commit as the frozen artifact.

## File Structure

- `src/retinue/matching/ablation.py` - pre-registered constants (`N`, `SEEDS`, `KS`, `NOW`,
  `MANDATES`), `designed_similarity`, `arm_shipped`, `arm_blend_no_filter`,
  `arm_similarity_only`, `failing_axes` (the per-axis probe), `cell_metrics`, `run_study`,
  `STUDY_META_SKELETON`. Measurement wiring only.
- `scripts/matching_ablation.py` - argparse wrapper: `--run-date YYYY-MM-DD` required,
  `--out PATH` defaulting to the fixture path; writes the artifact via `run_study`.
- `fixtures/ablation/matching_contamination.json` - the frozen artifact (Task 4).
- `tests/matching/test_ablation.py` - Tasks 1-3: score, arms, probe, metric, determinism.
- `tests/matching/test_ablation_artifact.py` - Task 4: sha pin, invariants, regeneration.
- `README.md`, `docs/architecture-proposal.md` - Task 4 only.

---

### Task 1: The pre-registered constants and the designed score

**Files:**
- Create: `src/retinue/matching/ablation.py`
- Test: `tests/matching/test_ablation.py`

**Interfaces:**
- Consumes: `chaperone.matching.filters.Candidate`, `Mandate`.
- Produces: `N: int = 10000`; `SEEDS: tuple[int, ...] = tuple(range(1, 11))`;
  `KS: tuple[int, ...] = (5, 10, 20)`; `NOW: datetime`; `MANDATES: dict[str, Mandate]` keyed
  `"permissive"`, `"jurisdiction_restricted"`, `"jurisdiction_and_cheque_restricted"`;
  `designed_similarity(candidate: Candidate, mandate: Mandate) -> float`;
  `jitter(candidate_id: str) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/matching/test_ablation.py
"""The matching ablation's measurement wiring (spec: 2026-08-31-matching-ablation-design.md).

Every test here holds a pre-registered value or a property of the wiring. None reads a
contamination number: those live in the frozen artifact and are asserted nowhere."""
import hashlib
from datetime import datetime, timezone

from chaperone.matching.filters import Candidate, Mandate

from retinue.matching.ablation import (KS, MANDATES, N, NOW, SEEDS, designed_similarity, jitter)


def cand(cid="c-1", sector="devtools", stage="seed", geography="eu-west", jurisdiction="US",
         ceiling="4000000"):
    return Candidate(id=cid, check_size_max=ceiling, stage=stage, sector=sector,
                     geography=geography, jurisdiction=jurisdiction, days_since_touch=None,
                     prior_passes=0)


def test_the_pre_registered_values_are_the_spec_section_6_values():
    assert N == 10000
    assert SEEDS == tuple(range(1, 11))
    assert KS == (5, 10, 20)
    assert NOW == datetime(2030, 3, 1, tzinfo=timezone.utc)
    assert set(MANDATES) == {"permissive", "jurisdiction_restricted",
                             "jurisdiction_and_cheque_restricted"}
    for m in MANDATES.values():
        assert (m.stage, m.sector, m.geography) == ("seed", "devtools", "eu-west")
    assert MANDATES["permissive"].consented_jurisdictions == frozenset({"US", "UK", "DE"})
    assert MANDATES["permissive"].check_size_min == "100000"
    assert MANDATES["jurisdiction_restricted"].consented_jurisdictions == frozenset({"US"})
    assert MANDATES["jurisdiction_restricted"].check_size_min == "100000"
    assert MANDATES["jurisdiction_and_cheque_restricted"].consented_jurisdictions == frozenset({"US"})
    assert MANDATES["jurisdiction_and_cheque_restricted"].check_size_min == "2000000"


def test_the_jitter_is_sha256_of_the_id_scaled_into_the_open_fifth():
    expected = int(hashlib.sha256(b"c-1").hexdigest()[:8], 16) / 0x100000000 * 0.2
    assert jitter("c-1") == expected
    assert 0.0 <= jitter("c-1") < 0.2
    assert jitter("c-1") == jitter("c-1")           # deterministic
    assert jitter("c-1") != jitter("c-2")           # id-dependent


def test_the_score_reads_sector_and_stage_and_nothing_else():
    m = MANDATES["permissive"]
    full = designed_similarity(cand(), m)
    assert 0.8 <= full < 1.0                          # 0.5 + 0.3 + jitter
    sector_only = designed_similarity(cand(stage="series-a"), m)
    assert 0.5 <= sector_only < 0.7
    none = designed_similarity(cand(sector="climate", stage="series-a"), m)
    assert 0.0 <= none < 0.2
    # Blind to the hard axes: an ineligible candidate can score identically to an eligible one.
    eligible = cand(cid="same")
    wrong_everything_else = cand(cid="same", jurisdiction="RU", ceiling="1000", geography="mena")
    assert designed_similarity(eligible, m) == designed_similarity(wrong_everything_else, m)


def test_the_score_is_bounded_in_the_unit_interval():
    for c in (cand(), cand(sector="x", stage="y"), cand(cid="z" * 50)):
        s = designed_similarity(c, MANDATES["permissive"])
        assert 0.0 <= s <= 1.0
```

- [ ] **Step 2: Run to watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: FAIL at import: `No module named 'retinue.matching.ablation'`

- [ ] **Step 3: Write the module's first half**

```python
# src/retinue/matching/ablation.py
"""The matching ablation: measurement wiring, no policy and no ranking of its own.

Pre-registered in docs/superpowers/specs/2026-08-31-matching-ablation-design.md before any
contamination number existed. Everything that decides eligibility, relationship or ordering is
imported from the vendored library and called; this module composes the arms, probes the axes,
counts, and writes what it counted. The score below is synthetic and designed, and every artifact
this module writes says so beside every number that depends on it.
"""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timezone

from chaperone.matching.filters import Candidate, Eligibility, Mandate, classify
from chaperone.matching.rank import EMBEDDING_WEIGHT, RELATIONSHIP_WEIGHT, rank
from chaperone.matching.relationship import relationship_score

#: Section 6 of the spec. A change here after the run is a new study with a new dated spec.
N = 10000
SEEDS = tuple(range(1, 11))
KS = (5, 10, 20)
NOW = datetime(2030, 3, 1, tzinfo=timezone.utc)
MANDATES: dict[str, Mandate] = {
    "permissive": Mandate(check_size_min="100000", stage="seed", sector="devtools",
                          geography="eu-west", consented_jurisdictions=frozenset({"US", "UK", "DE"})),
    "jurisdiction_restricted": Mandate(check_size_min="100000", stage="seed", sector="devtools",
                                       geography="eu-west", consented_jurisdictions=frozenset({"US"})),
    "jurisdiction_and_cheque_restricted": Mandate(check_size_min="2000000", stage="seed",
                                                  sector="devtools", geography="eu-west",
                                                  consented_jurisdictions=frozenset({"US"})),
}
SCORE_NAME = "designed_similarity"


def jitter(candidate_id: str) -> float:
    """[0, 0.2) from the id's sha256: stable tie-breaking texture, never a signal."""
    return int(hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:8], 16) / 0x100000000 * 0.2


def designed_similarity(candidate: Candidate, mandate: Mandate) -> float:
    """Synthetic. Reads sector and stage only, blind to jurisdiction, cheque size and geography by
    design (spec section 4): a candidate the mandate must exclude can top this score."""
    score = 0.0
    if candidate.sector == mandate.sector:
        score += 0.5
    if candidate.stage == mandate.stage:
        score += 0.3
    return score + jitter(candidate.id)
```

- [ ] **Step 4: Run the tests to watch them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: 4 passed

- [ ] **Step 5: Mutants, each watched red**

Apply one at a time, run the file, confirm red on the named test, restore: change `0.5` to `0.4`
(sector test reds); change the jitter divisor to `0xFFFFFFFF` (jitter test reds); make the score
read `candidate.jurisdiction` (blindness assertion reds); change a mandate floor (values test
reds). Record each in the report.

- [ ] **Step 6: Gates, then commit**

```bash
.venv/Scripts/python.exe -m pytest
PYTHON=.venv/Scripts/python.exe bash tools/battery.sh
git add src/retinue/matching/ablation.py tests/matching/test_ablation.py
git commit -m "feat: the ablation's constants and its designed score, pre-registered"
```

---

### Task 2: The three arms, the candidates, and the per-axis probe

**Files:**
- Modify: `src/retinue/matching/ablation.py` (append)
- Test: `tests/matching/test_ablation.py` (append)

**Interfaces:**
- Consumes: Task 1's constants and `designed_similarity`; the imported `rank`, `classify`,
  `relationship_score`, `RELATIONSHIP_WEIGHT`, `EMBEDDING_WEIGHT`;
  `retinue.matching.integrate.candidate_for`; `retinue.ledger.store.InMemoryStore`;
  `retinue.synth.rosters.generate_rosters`.
- Produces: `candidates_for_seed(seed: int) -> list[Candidate]`;
  `arm_shipped(candidates, mandate, k) -> list[Candidate]`;
  `arm_blend_no_filter(candidates, mandate, k) -> list[Candidate]`;
  `arm_similarity_only(candidates, mandate, k) -> list[Candidate]`;
  `AXES = ("jurisdiction", "check_size_max", "stage", "sector", "geography")`;
  `failing_axes(candidate: Candidate, mandate: Mandate) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/matching/test_ablation.py
from chaperone.matching.filters import Eligibility, classify
from chaperone.matching.rank import rank

from retinue.matching.ablation import (AXES, arm_blend_no_filter, arm_shipped,
                                       arm_similarity_only, candidates_for_seed, failing_axes)


def test_candidates_for_a_seed_are_the_shipped_mapping_over_an_empty_store():
    cs = candidates_for_seed(1)
    assert len(cs) == N
    assert all(c.days_since_touch is None and c.prior_passes == 0 for c in cs)
    assert cs[0].id == "synth-000"


def test_the_shipped_arm_never_contains_an_ineligible_candidate():
    cs = candidates_for_seed(1)
    for name, m in MANDATES.items():
        top = arm_shipped(cs, m, 20)
        assert len(top) == 20
        assert all(classify(c, m)[0] is Eligibility.ELIGIBLE for c in top), name


def test_the_ablated_arms_never_call_the_filter_and_admit_anyone():
    # An effect, not a spy: a mandate NOBODY is eligible for still yields a full top K.
    cs = candidates_for_seed(1)
    impossible = Mandate(check_size_min="999999999999", stage="seed", sector="devtools",
                         geography="eu-west", consented_jurisdictions=frozenset())
    assert arm_shipped(cs, impossible, 5) == []
    assert len(arm_similarity_only(cs, impossible, 5)) == 5
    assert len(arm_blend_no_filter(cs, impossible, 5)) == 5


def test_a2_ordering_equals_the_imported_rankers_ordering_over_an_all_eligible_list():
    # The spec's effect-level test: not a recomputed key, the import's own output order.
    m = MANDATES["permissive"]
    eligible = [c for c in candidates_for_seed(2) if classify(c, m)[0] is Eligibility.ELIGIBLE]
    ranked, _ = rank(eligible, m, lambda c: designed_similarity(c, m))
    assert [c.id for c in arm_blend_no_filter(eligible, m, len(eligible))] == [c.id for c in ranked]


def test_a1_orders_by_the_score_alone_with_the_id_as_the_final_key():
    m = MANDATES["permissive"]
    cs = candidates_for_seed(3)
    top = arm_similarity_only(cs, m, 50)
    keys = [(-designed_similarity(c, m), c.id) for c in top]
    assert keys == sorted(keys)


def test_the_probe_names_exactly_the_one_axis_a_candidate_fails():
    m = MANDATES["jurisdiction_restricted"]      # consented {"US"}, floor 100k
    base = dict(sector="devtools", stage="seed", geography="eu-west", jurisdiction="US",
                ceiling="4000000")
    assert failing_axes(cand(**base), m) == ()
    one_off = {
        "jurisdiction": dict(base, jurisdiction="DE"),
        "check_size_max": dict(base, ceiling="50000"),
        "stage": dict(base, stage="series-a"),
        "sector": dict(base, sector="climate"),
        "geography": dict(base, geography="mena"),
    }
    for axis, kwargs in one_off.items():
        assert failing_axes(cand(**kwargs), m) == (axis,), axis


def test_the_probe_reports_every_failing_axis_of_a_candidate_failing_several():
    m = MANDATES["jurisdiction_and_cheque_restricted"]
    c = cand(jurisdiction="DE", ceiling="1500000", sector="climate")
    assert set(failing_axes(c, m)) == {"jurisdiction", "check_size_max", "sector"}
    assert tuple(a for a in AXES if a in failing_axes(c, m)) == failing_axes(c, m)  # AXES order
```

- [ ] **Step 2: Run to watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: FAIL at import: `cannot import name 'AXES'`

- [ ] **Step 3: Implement**

```python
# append to src/retinue/matching/ablation.py
from retinue.ledger.store import InMemoryStore
from retinue.matching.integrate import candidate_for
from retinue.synth.rosters import generate_rosters

AXES = ("jurisdiction", "check_size_max", "stage", "sector", "geography")


def candidates_for_seed(seed: int) -> list[Candidate]:
    """The shipped row-to-Candidate mapping over one empty store at the pre-registered NOW."""
    store = InMemoryStore()
    return [candidate_for(row, store, now=NOW) for row in generate_rosters(seed, N)]


def arm_shipped(candidates, mandate: Mandate, k: int) -> list[Candidate]:
    ranked, _needs = rank(candidates, mandate, lambda c: designed_similarity(c, mandate))
    return ranked[:k]


def _blend(candidate: Candidate, mandate: Mandate) -> float:
    return (RELATIONSHIP_WEIGHT * relationship_score(candidate)
            + EMBEDDING_WEIGHT * designed_similarity(candidate, mandate))


def arm_blend_no_filter(candidates, mandate: Mandate, k: int) -> list[Candidate]:
    """The imported blend over EVERY candidate, no classify call: what the filter buys."""
    return sorted(candidates, key=lambda c: (-_blend(c, mandate), c.id))[:k]


def arm_similarity_only(candidates, mandate: Mandate, k: int) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (-designed_similarity(c, mandate), c.id))[:k]


def _widened(mandate: Mandate, axis: str, candidate: Candidate) -> Mandate:
    """A copy of the mandate that cannot exclude this candidate on the given axis."""
    if axis == "jurisdiction":
        return dataclasses.replace(
            mandate, consented_jurisdictions=mandate.consented_jurisdictions | {candidate.jurisdiction})
    if axis == "check_size_max":
        return dataclasses.replace(mandate, check_size_min="0")
    return dataclasses.replace(mandate, **{axis: getattr(candidate, axis)})


def failing_axes(candidate: Candidate, mandate: Mandate) -> tuple[str, ...]:
    """Which axes exclude this candidate, by re-running the imported classify against a mandate
    widened on every OTHER axis: the axis fails if the verdict is still INELIGIBLE when only it
    remains strict. The import decides; this function only asks it five questions."""
    if classify(candidate, mandate)[0] is not Eligibility.INELIGIBLE:
        return ()
    failing = []
    for axis in AXES:
        others_widened = mandate
        for other in AXES:
            if other != axis:
                others_widened = _widened(others_widened, other, candidate)
        if classify(candidate, others_widened)[0] is Eligibility.INELIGIBLE:
            failing.append(axis)
    return tuple(failing)
```

Note on the widening for `check_size_max`: the spec says "the floor lowered to the candidate's
ceiling"; `"0"` is the same operation in effect (no candidate ceiling is below zero) and is what
the spec's own "cannot exclude on this axis" intent requires. State this in the report.

- [ ] **Step 4: Run the tests to watch them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: 11 passed

- [ ] **Step 5: Mutants, each watched red**

Apply one at a time, run, confirm red on the named test, restore: make `arm_shipped` drop the
`classify` (the shipped-arm test reds); make `arm_blend_no_filter` sort by `_blend` without the
id tiebreak on a list with equal blends, or reverse the sort (the A2 ordering test reds); make
`failing_axes` skip widening one axis (the several-axes test reds); make `_widened` for
jurisdiction return the mandate unchanged (the one-axis test reds on `"jurisdiction"`).

- [ ] **Step 6: Gates, then commit**

```bash
.venv/Scripts/python.exe -m pytest
PYTHON=.venv/Scripts/python.exe bash tools/battery.sh
git add src/retinue/matching/ablation.py tests/matching/test_ablation.py
git commit -m "feat: three arms over one substrate, and a probe that asks the import"
```

---

### Task 3: The cell metric, the study runner, and the script

**Files:**
- Modify: `src/retinue/matching/ablation.py` (append)
- Create: `scripts/matching_ablation.py`
- Test: `tests/matching/test_ablation.py` (append)

**Interfaces:**
- Consumes: everything above.
- Produces: `cell_metrics(candidates, mandate, k) -> dict` with keys `k`, `eligible_pool`,
  `arms` (a dict keyed `"S"`, `"A1"`, `"A2"`, each `{"contaminated": int, "denominator": k,
  "needs_verification": int, "per_axis": {axis: int}, "overlap_with_shipped": int,
  "shipped_size": int, "ids": [...]}`);
  `run_study(*, run_date: str, wheel_sha256: str, library_version: str) -> dict` returning
  the whole artifact document; `WHEEL_PATH` and `wheel_identity() -> tuple[str, str]` (sha256
  hex, version) reading `vendor/chaperone-0.1.0-py3-none-any.whl` and
  `importlib.metadata.version("chaperone")`; `write_study(doc, path)` writing UTF-8, LF,
  `json.dumps(doc, indent=1, sort_keys=True) + "\n"`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/matching/test_ablation.py
import json

from retinue.matching.ablation import cell_metrics, run_study, wheel_identity, write_study


def test_cell_metrics_counts_ineligible_only_and_keeps_needs_verification_apart():
    m = MANDATES["permissive"]
    cs = candidates_for_seed(4)
    cell = cell_metrics(cs, m, 10)
    assert cell["k"] == 10
    assert cell["eligible_pool"] == sum(1 for c in cs if classify(c, m)[0] is Eligibility.ELIGIBLE)
    for arm in ("S", "A1", "A2"):
        a = cell["arms"][arm]
        assert a["denominator"] == 10 and len(a["ids"]) == 10
        assert a["contaminated"] + a["needs_verification"] <= 10
        assert set(a["per_axis"]) == set(AXES)
        assert 0 <= a["overlap_with_shipped"] <= a["shipped_size"] == 10
    assert cell["arms"]["S"]["contaminated"] == 0
    assert cell["arms"]["S"]["overlap_with_shipped"] == 10


def test_cell_metrics_counts_are_recomputable_from_the_ids_it_reports():
    m = MANDATES["jurisdiction_restricted"]
    cs = candidates_for_seed(5)
    by_id = {c.id: c for c in cs}
    cell = cell_metrics(cs, m, 20)
    for arm in ("A1", "A2"):
        a = cell["arms"][arm]
        picked = [by_id[i] for i in a["ids"]]
        assert a["contaminated"] == sum(
            1 for c in picked if classify(c, m)[0] is Eligibility.INELIGIBLE)
        assert a["needs_verification"] == sum(
            1 for c in picked if classify(c, m)[0] is Eligibility.NEEDS_VERIFICATION)
        for axis in AXES:
            assert a["per_axis"][axis] == sum(1 for c in picked if axis in failing_axes(c, m))
        assert a["overlap_with_shipped"] == len(set(a["ids"]) & set(cell["arms"]["S"]["ids"]))


def test_the_study_document_carries_its_pre_registration_and_its_stamp():
    doc = run_study(run_date="2030-01-01", wheel_sha256="0" * 64, library_version="0.1.0")
    meta = doc["meta"]
    assert meta["hand_authored"] is True
    assert "no model" in meta["note"] and "synthetic" in meta["note"]
    assert meta["spec"] == "docs/superpowers/specs/2026-08-31-matching-ablation-design.md"
    assert meta["run_date"] == "2030-01-01"
    assert meta["wheel_sha256"] == "0" * 64 and meta["library_version"] == "0.1.0"
    assert meta["score"] == "designed_similarity"
    assert meta["command"].startswith("scripts/matching_ablation.py")
    pre = doc["pre_registered"]
    assert pre["n"] == N and pre["seeds"] == list(SEEDS) and pre["ks"] == list(KS)
    assert set(pre["mandates"]) == set(MANDATES)
    assert doc["generator_digest"] == (
        "c23a8ecc760659bbe87c391003bbb240fdd102e3f9db411830f5174db8cfa656")
    assert len(doc["cells"]) == len(SEEDS) * len(MANDATES) * len(KS)
    agg = doc["aggregates"]
    for mandate in MANDATES:
        for k in KS:
            cellagg = agg[mandate][str(k)]
            for arm in ("A1", "A2"):
                a = cellagg[arm]
                assert a["denominator"] == k * len(SEEDS)
                assert a["per_seed_min"] <= a["per_seed_max"] <= k
                assert 0 <= a["contaminated"] <= a["denominator"]


def test_the_study_is_a_pure_function_of_its_arguments():
    a = run_study(run_date="2030-01-01", wheel_sha256="0" * 64, library_version="0.1.0")
    b = run_study(run_date="2030-01-01", wheel_sha256="0" * 64, library_version="0.1.0")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_wheel_identity_reads_the_vendored_wheel_and_the_installed_version():
    sha, version = wheel_identity()
    assert len(sha) == 64 and int(sha, 16) >= 0
    assert version == "0.1.0"


def test_write_study_is_lf_utf8_sorted_and_terminated(tmp_path):
    out = tmp_path / "a.json"
    write_study({"b": 1, "a": {"z": [1]}}, out)
    raw = out.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert raw.decode("utf-8") == json.dumps({"b": 1, "a": {"z": [1]}}, indent=1, sort_keys=True) + "\n"
```

- [ ] **Step 2: Run to watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: FAIL at import: `cannot import name 'cell_metrics'`

- [ ] **Step 3: Implement the runner**

```python
# append to src/retinue/matching/ablation.py
import hashlib as _hashlib
import importlib.metadata
import json
from pathlib import Path

SPEC_PATH = "docs/superpowers/specs/2026-08-31-matching-ablation-design.md"
WHEEL_PATH = Path(__file__).resolve().parents[3] / "vendor" / "chaperone-0.1.0-py3-none-any.whl"
GENERATOR_DIGEST = "c23a8ecc760659bbe87c391003bbb240fdd102e3f9db411830f5174db8cfa656"
ARMS = ("S", "A1", "A2")
NOTE = ("Generated by one deterministic run of scripts/matching_ablation.py over synthetic rosters "
        "from retinue.synth.rosters and a synthetic designed score; no model, no network, no "
        "clock. hand_authored here means authored by this repository's own code over invented "
        "inputs, the gold-rankings precedent. All figures are synthetic. Every rate carries its "
        "denominator; CI asserts invariants over this file and never a rate.")


def _arm_entry(picked, mandate, shipped_ids):
    verdicts = [classify(c, mandate)[0] for c in picked]
    return {
        "ids": [c.id for c in picked],
        "denominator": len(picked),
        "contaminated": sum(1 for v in verdicts if v is Eligibility.INELIGIBLE),
        "needs_verification": sum(1 for v in verdicts if v is Eligibility.NEEDS_VERIFICATION),
        "per_axis": {axis: sum(1 for c in picked if axis in failing_axes(c, mandate))
                     for axis in AXES},
        "overlap_with_shipped": len({c.id for c in picked} & shipped_ids),
        "shipped_size": len(shipped_ids),
    }


def cell_metrics(candidates, mandate: Mandate, k: int) -> dict:
    shipped = arm_shipped(candidates, mandate, k)
    shipped_ids = {c.id for c in shipped}
    picks = {"S": shipped, "A1": arm_similarity_only(candidates, mandate, k),
             "A2": arm_blend_no_filter(candidates, mandate, k)}
    return {
        "k": k,
        "eligible_pool": sum(1 for c in candidates
                             if classify(c, mandate)[0] is Eligibility.ELIGIBLE),
        "arms": {arm: _arm_entry(picks[arm], mandate, shipped_ids) for arm in ARMS},
    }


def wheel_identity() -> tuple[str, str]:
    return (_hashlib.sha256(WHEEL_PATH.read_bytes()).hexdigest(),
            importlib.metadata.version("chaperone"))


def run_study(*, run_date: str, wheel_sha256: str, library_version: str) -> dict:
    """The whole artifact as a document. Pure in its arguments: the date is passed in."""
    cells = []
    for seed in SEEDS:
        candidates = candidates_for_seed(seed)
        for mandate_name, mandate in MANDATES.items():
            for k in KS:
                cell = cell_metrics(candidates, mandate, k)
                cells.append({"seed": seed, "mandate": mandate_name, **cell})
    aggregates: dict = {}
    for mandate_name in MANDATES:
        aggregates[mandate_name] = {}
        for k in KS:
            group = [c for c in cells if c["mandate"] == mandate_name and c["k"] == k]
            aggregates[mandate_name][str(k)] = {
                "eligible_pool_min": min(c["eligible_pool"] for c in group),
                "eligible_pool_max": max(c["eligible_pool"] for c in group),
                **{arm: {
                    "contaminated": sum(c["arms"][arm]["contaminated"] for c in group),
                    "denominator": sum(c["arms"][arm]["denominator"] for c in group),
                    "needs_verification": sum(c["arms"][arm]["needs_verification"] for c in group),
                    "per_axis": {axis: sum(c["arms"][arm]["per_axis"][axis] for c in group)
                                 for axis in AXES},
                    "overlap_with_shipped": sum(c["arms"][arm]["overlap_with_shipped"] for c in group),
                    "shipped_size": sum(c["arms"][arm]["shipped_size"] for c in group),
                    "per_seed_min": min(c["arms"][arm]["contaminated"] for c in group),
                    "per_seed_max": max(c["arms"][arm]["contaminated"] for c in group),
                } for arm in ARMS},
            }
    return {
        "meta": {
            "hand_authored": True,
            "note": NOTE,
            "spec": SPEC_PATH,
            "command": f"scripts/matching_ablation.py --run-date {run_date}",
            "run_date": run_date,
            "library_version": library_version,
            "wheel_sha256": wheel_sha256,
            "score": SCORE_NAME,
            "relationship_collapse": (
                "every candidate is built over an empty store, so relationship_score is 0.0 for "
                "all of them and A2 orders as A1 up to scale on this substrate; both arms ran"),
        },
        "pre_registered": {
            "n": N, "seeds": list(SEEDS), "ks": list(KS), "now": NOW.isoformat(),
            "mandates": {name: {"check_size_min": m.check_size_min, "stage": m.stage,
                                "sector": m.sector, "geography": m.geography,
                                "consented_jurisdictions": sorted(m.consented_jurisdictions)}
                         for name, m in MANDATES.items()},
            "score": {"name": SCORE_NAME, "sector_match": 0.5, "stage_match": 0.3,
                      "jitter": "sha256(id)[:8] / 2^32 * 0.2", "final_key": "candidate id"},
        },
        "generator_digest": GENERATOR_DIGEST,
        "cells": cells,
        "aggregates": aggregates,
    }


def write_study(doc: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
```

- [ ] **Step 4: The script**

```python
# scripts/matching_ablation.py
"""Runs the pre-registered matching ablation once and writes the frozen artifact.

    python scripts/matching_ablation.py --run-date 2026-09-01

The run date is an ARGUMENT, never a clock read, so the regeneration check in
tests/matching/test_ablation_artifact.py can pass the frozen meta's own date back in and compare
byte for byte. Nothing here touches a network, a key or a model; the whole study is a function of
the values pre-registered in docs/superpowers/specs/2026-08-31-matching-ablation-design.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from retinue.matching.ablation import run_study, wheel_identity, write_study

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "fixtures" / "ablation" / "matching_contamination.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python scripts/matching_ablation.py")
    ap.add_argument("--run-date", required=True, help="ISO date stamped into meta; an argument, never now()")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    sha, version = wheel_identity()
    doc = run_study(run_date=args.run_date, wheel_sha256=sha, library_version=version)
    write_study(doc, args.out)
    print(f"wrote {args.out} ({len(doc['cells'])} cells)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/test_ablation.py -v`
Expected: 17 passed (the study tests take roughly ten seconds each; that is the substrate's size)

- [ ] **Step 6: Mutants, each watched red**

One at a time, run the file, confirm red on the named test, restore: count `NEEDS_VERIFICATION`
into `contaminated` (recomputability test reds); drop `per_seed_min` (document test reds); read
`datetime.now()` for `run_date` inside `run_study` ignoring the argument (purity test reds only
if the date differs, so instead: make the meta `run_date` the literal `"x"`; the document test
reds); write with `newline=None` on Windows (the LF test reds).

- [ ] **Step 7: Gates, then commit**

```bash
.venv/Scripts/python.exe -m pytest
PYTHON=.venv/Scripts/python.exe bash tools/battery.sh
git add src/retinue/matching/ablation.py scripts/matching_ablation.py tests/matching/test_ablation.py
git commit -m "feat: the study runs as a function of its pre-registered arguments"
```

---

### Task 4: The run, the frozen artifact, its tests, and the documents

**Files:**
- Create: `fixtures/ablation/matching_contamination.json` (by running the script, once)
- Create: `tests/matching/test_ablation_artifact.py`
- Modify: `README.md` (the Matching staging row in Designed vs Built; a Results subsection under
  "Matching and the evals"; the Run history paragraph gains one dated sentence)
- Modify: `docs/architecture-proposal.md` (section 15 preamble: one dated sentence noting the
  ablation ran and where its artifact lives; it was never a Designed row, so no row moves)

**Interfaces:**
- Consumes: everything above; `tests/test_fixture_meta.py`'s provenance rules
  (`hand_authored: true` accepted alone; the fixture must live under `fixtures/` to be scanned).

- [ ] **Step 1: Run the study once, with today's date as the argument**

```bash
.venv/Scripts/python.exe scripts/matching_ablation.py --run-date 2026-09-01
```
Expected: `wrote .../fixtures/ablation/matching_contamination.json (90 cells)`. Do not open the
file to read its numbers before the tests below exist; the artifact is canon on the first run
(spec section 6). A rerun is permitted only after a technical defect in the harness, and the
artifact's meta then names the defect.

- [ ] **Step 2: Write the failing artifact tests**

```python
# tests/matching/test_ablation_artifact.py
"""The frozen ablation artifact: its pin, the spec's CI invariants, and its regeneration.

Nothing here asserts a contamination rate. The rates are reported in the README from this file's
bytes; these tests hold that the bytes are the pre-registered run and that the invariants the spec
names in section 7 hold over it."""
import hashlib
import json
from pathlib import Path

from chaperone.matching.filters import Eligibility, classify

from retinue.matching.ablation import (ARMS, AXES, KS, MANDATES, N, SEEDS, candidates_for_seed,
                                       run_study, write_study)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "fixtures" / "ablation" / "matching_contamination.json"
#: The artifact's sha256 the day it was frozen. Regenerate deliberately, never to green a test:
#: a changed pre-registered value is a new study with a new dated spec (spec section 6).
FROZEN_SHA256 = "REPLACE-WITH-THE-HASH-PRINTED-BY-STEP-3"

DOC = json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_the_artifact_is_pinned_to_the_frozen_run():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == FROZEN_SHA256


def test_the_artifact_restates_the_pre_registration_exactly():
    pre = DOC["pre_registered"]
    assert pre["n"] == N and pre["seeds"] == list(SEEDS) and pre["ks"] == list(KS)
    for name, m in MANDATES.items():
        assert pre["mandates"][name]["consented_jurisdictions"] == sorted(m.consented_jurisdictions)
        assert pre["mandates"][name]["check_size_min"] == m.check_size_min


def test_the_shipped_arm_is_uncontaminated_in_every_cell():
    for cell in DOC["cells"]:
        assert cell["arms"]["S"]["contaminated"] == 0, (cell["seed"], cell["mandate"], cell["k"])


def test_every_denominator_equals_k_and_every_pool_exceeds_the_largest_k():
    for cell in DOC["cells"]:
        for arm in ARMS:
            assert cell["arms"][arm]["denominator"] == cell["k"]
        assert cell["eligible_pool"] > max(KS), (cell["seed"], cell["mandate"])


def test_the_aggregates_are_pooled_counts_over_pooled_denominators():
    for mandate in MANDATES:
        for k in KS:
            group = [c for c in DOC["cells"] if c["mandate"] == mandate and c["k"] == k]
            agg = DOC["aggregates"][mandate][str(k)]
            for arm in ARMS:
                assert agg[arm]["contaminated"] == sum(c["arms"][arm]["contaminated"] for c in group)
                assert agg[arm]["denominator"] == k * len(SEEDS)
                assert agg[arm]["per_seed_min"] == min(c["arms"][arm]["contaminated"] for c in group)
                assert agg[arm]["per_seed_max"] == max(c["arms"][arm]["contaminated"] for c in group)


def test_one_recorded_cell_recomputes_from_the_substrate():
    # The artifact's numbers are what the wiring produces over the pinned seed, not typed.
    cell = next(c for c in DOC["cells"] if c["seed"] == 1 and c["mandate"] == "permissive" and c["k"] == 5)
    cs = candidates_for_seed(1)
    by_id = {c.id: c for c in cs}
    m = MANDATES["permissive"]
    picked = [by_id[i] for i in cell["arms"]["A1"]["ids"]]
    assert cell["arms"]["A1"]["contaminated"] == sum(
        1 for c in picked if classify(c, m)[0] is Eligibility.INELIGIBLE)
    assert cell["eligible_pool"] == sum(1 for c in cs if classify(c, m)[0] is Eligibility.ELIGIBLE)


def test_regenerating_under_the_frozen_meta_reproduces_the_bytes(tmp_path):
    meta = DOC["meta"]
    doc = run_study(run_date=meta["run_date"], wheel_sha256=meta["wheel_sha256"],
                    library_version=meta["library_version"])
    out = tmp_path / "regen.json"
    write_study(doc, out)
    assert out.read_bytes() == ARTIFACT.read_bytes()


def test_the_provenance_is_hand_authored_with_the_stated_note():
    meta = DOC["meta"]
    assert meta["hand_authored"] is True and "captured" not in meta
    assert "no model" in meta["note"]
```

- [ ] **Step 3: Compute the pin and fill it in**

```bash
.venv/Scripts/python.exe -c "import hashlib;print(hashlib.sha256(open('fixtures/ablation/matching_contamination.json','rb').read()).hexdigest())"
```
Paste the printed hash into `FROZEN_SHA256`. Run the file: the pin test must pass; before pasting,
run it once with the placeholder to watch it red (`assert ... == 'REPLACE-...'` fails).

- [ ] **Step 4: Run all the tests, then the fixture-meta and battery gates**

Run: `.venv/Scripts/python.exe -m pytest tests/matching/ tests/test_fixture_meta.py -v`
Expected: all green, including `test_every_fixture_json_carries_provenance` over the new file.
If the em-dash gate or any battery gate reddens over the artifact (it should not: every string in
it is authored ASCII), the fix is in the generator's text, followed by a rerun whose meta names
the defect.

- [ ] **Step 5: The documents, from the artifact**

Read the frozen artifact's `aggregates` and write the prose from those numbers with denominators
beside every rate and no mean of rates, in these three places:

1. README `## Designed vs Built`, the Matching staging row: append after the existing text:
   `The ablation this row said did not exist ran on 2026-09-01: scripts/matching_ablation.py,
   frozen at fixtures/ablation/matching_contamination.json and pinned by
   tests/matching/test_ablation_artifact.py; its readings are under Matching and the evals.`
2. README `## Matching and the evals`, a new final paragraph headed **The ablation ran once and
   is frozen**: state the three arms in one sentence each, the substrate (n, seeds, three
   mandates, K), the score's blindness in one sentence with its name, then per mandate the pooled
   contaminated count over the pooled denominator for A1 and A2 at each K with the per-seed range,
   the shipped arm's zero, and ONE reading chosen from spec section 1 by which of its conditions
   the numbers meet - quoted, not paraphrased. End with the disclosure that A2 collapsed onto A1
   on this substrate and why, and the sentence "Nothing here is evidence that matches sharpen over
   time; that is the weights-update row, unbuilt."
3. README `## Run history`: one sentence dated 2026-09-01 that the ablation ran once, keyless and
   offline, and is frozen.
4. `docs/architecture-proposal.md` section 15 preamble: one dated sentence after the existing
   amendment noting the ablation ran (it was never a Designed row) with the artifact path.

Run the battery over the edited files; check every counting sentence still agrees with the
table (five Designed rows unchanged: the ablation flips no row).

- [ ] **Step 6: Gates, then the one commit**

```bash
.venv/Scripts/python.exe -m pytest
PYTHON=.venv/Scripts/python.exe bash tools/battery.sh
git add fixtures/ablation/matching_contamination.json tests/matching/test_ablation_artifact.py README.md docs/architecture-proposal.md
git commit -m "feat: the ablation ran once and is frozen, rates beside denominators"
```
The commit body carries the pooled counts per mandate at K=10 for A1, each over its denominator,
and the sentence that the shipped arm was zero in all 90 cells.

---

## Self-review notes

- Spec coverage: section 1 readings (Task 4 step 5, quoted); section 2 arms and the A2
  effect-level test (Task 2); section 3 substrate and pools (Task 1 constants, Task 4 pool
  invariant); section 4 score (Task 1); section 5 metric, probe, needs-verification, overlap,
  pooled aggregates (Tasks 2-3, Task 4 aggregate test); section 6 pre-registration (constants
  pinned by test, pin test forbids silent regeneration); section 7 artifact, provenance, CI
  invariants, regeneration with the date as argument, documents (Task 4); section 8 constraints
  (global block).
- Placeholder scan: the one intentional placeholder is `FROZEN_SHA256`'s value, filled in Task 4
  step 3 from the run and watched red first; no other TBDs.
- Type consistency: `cell_metrics` returns `arms` keyed by `ARMS`; `run_study` and the artifact
  tests read the same keys; `write_study` is the single serializer used by both the script and
  the regeneration test, which is what makes byte-for-byte meaningful.
- Runtime: the full study is roughly ten seconds; the regeneration test costs the same once per
  suite run, accepted.
