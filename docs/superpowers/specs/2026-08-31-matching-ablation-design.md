# The matching ablation: what the eligibility filter refuses that similarity would admit

A measurement, pre-registered here before anything runs, of how much shortlist contamination a
similarity-driven search admits when the imported eligibility filter is taken out of the staging
this repository ships. The README's own build-status table already carries the correction: the matching row
"said staging + ablation harness; nothing here runs an ablation". This spec is that
ablation, built to the repository's standing rule that rates are measured and reported with their
denominators and never asserted, and to the capture discipline that a frozen artifact is canon.

Everything below the line "What is pre-registered" was fixed before the first measured
contamination number existed. The one number computed before this spec was written is the
eligibility rate of the synthetic rosters under three mandates - a sizing fact about the generator,
recorded in section 3, and not a result.

## 1. The question, and what each answer would mean

The shipped staging (`retinue.matching.integrate.shortlist` over the imported
`chaperone.matching.rank`) filters first and ranks inside the eligible set. A candidate the
mandate excludes - wrong jurisdiction, cheque ceiling under the floor, wrong stage, sector or
geography - never reaches the scorer. The ablation asks: if the filter were removed and the
shortlist were the top of the score alone, how many excluded candidates would sit in it?

The readings are fixed in advance so the report cannot be steered after the fact:

- High contamination in the ablated arms and zero in the shipped arm: the filter is load-bearing,
  and the report says so, bounded to these mandates and this synthetic score.
- Low contamination in the ablated arms: the mandates admit too much of the roster, or the score
  is too weakly correlated with the excluded axes, for the filter to matter at this K. The report
  says THAT. It never says "the filter helps little", because that reading is not what the
  measurement supports.
- Any non-zero contamination in the shipped arm is a defect in the harness or the import, not a
  finding: the shipped staging cannot rank an excluded candidate by construction
  (`test_violation_costs_membership_not_score` already holds this), and the ablation asserts it as
  an invariant.

What the study does not claim, stated once: nothing here is evidence that matches get "sharper
over time". That is the weights-update row (proposal section 15.5), unbuilt behind an upstream
seam, and this measurement is not dressed as it. Nothing here is evidence about real embeddings or
real investors; the score and the roster are synthetic and named as such wherever a number
appears.

## 2. The arms

Three arms over identical inputs - the same roster, the same mandate, the same score function,
the same K:

- **Shipped (S).** `rank(candidates, mandate, embed_score)` as imported: `classify` first, then the
  0.6 relationship / 0.4 embedding blend inside the eligible bucket. Top K of the ranked list.
- **Ablated, blend without filter (A2).** Every candidate sorted by the identical blend,
  `0.6 * relationship_score + 0.4 * embed_score`, with no `classify` call. Top K. This arm
  isolates exactly what the filter buys, holding the ranking function fixed.
- **Ablated, similarity only (A1).** Every candidate sorted by `embed_score` alone. Top K. This is
  the literal "pure weighted-vector search" of the external review's framing.

All three arms consume the same candidates, built by the shipped
`retinue.matching.integrate.candidate_for(row, store, now=NOW)` over one empty in-memory store,
with `NOW = datetime(2030, 3, 1, tzinfo=timezone.utc)` pre-registered here (the constant the
integration tests already use). On an empty store every candidate carries no touchpoint history,
which is the collapse this section already discloses. Verified before this spec was fixed: this
mapping reproduces section 3's pool counts exactly, per regime and per seed. Since the imported
`rank` takes `embed_score: Callable[[Candidate], float]`, the mandate is bound into the score by
partial application where the arms are driven.

A1 and A2 are computed in the ablation module by reading the imported weights
(`RELATIONSHIP_WEIGHT`, `EMBEDDING_WEIGHT`) and calling the imported `relationship_score` and
`classify`; no ranking or eligibility logic is written in this repository, which keeps
`tools/fleet_audit.py`'s rule intact and keeps the arms comparable by construction. A test holds
that, over an all-eligible candidate list, A2's ordering equals the imported `rank`'s actual
output ordering: an effect, not a recomputation of the key, because a key recomputed from the
same imported weights and score compares the imports to themselves and cannot redden for the
drift it exists to catch (respelled 2026-09-01 at the advisor round's one new finding).

In the synthetic rosters no candidate has a touchpoint history, so `relationship_score` is 0.0
for every candidate and A2 collapses onto A1 up to scale. The study says so in its artifact and
still runs both arms, because the harness is the deliverable and the collapse is the measured
state of THIS substrate, not a property of the design; a roster with ledger history - a later
run over captured relationship state - separates them without a code change.

## 3. The substrate, sized from the generator and not from folklore

`retinue.synth.rosters.generate_rosters(seed, n)` draws every field uniformly from three or four
values, so a mandate's eligibility rate is fixed by the geometry of the mandate rather than by
anything the ablation can tune. Measured before this spec was fixed, over seeds 1 to 10 (counts of
`Eligibility.ELIGIBLE` per roster, no scores involved):

| mandate regime | n = 10000: eligible per roster, min / mean / max | rate |
| --- | --- | --- |
| permissive: three consented jurisdictions, floor 100k | 259 / 284.5 / 309 | 0.0284 |
| jurisdiction-restricted: one consented jurisdiction, floor 100k | 80 / 92.4 / 107 | 0.0092 |
| jurisdiction and cheque restricted: one jurisdiction, floor 2M | 47 / 63.9 / 78 | 0.0064 |

The stage, sector and geography axes each exclude by uniform draw regardless of regime, which is
why even the permissive mandate admits under three percent. The K sweep must sit well inside the
smallest eligible pool or the shipped arm's shortlist is truncated by pool size rather than by K,
and the comparison stops meaning what it says.

**Fixed:** `n = 10000`; **seeds 1 through 10** inclusive; the three mandates above, spelled in
full in the ablation module as frozen dataclass literals with `stage="seed"`, `sector="devtools"`,
`geography="eu-west"` and the jurisdiction and floor values of the table; **K in {5, 10, 20}**.
The smallest eligible pool measured in the tightest regime (47) exceeds the largest K (20) on
every seed with room to spare (n = 5000 gave 21, one above K and too thin to rest on), so no
shipped shortlist is pool-truncated; the artifact records the eligible pool per (seed, mandate)
beside every rate so a reader can check that claim against the run rather than this sentence.

## 4. The score, designed to be able to fail

An uncorrelated pseudo-random score would produce contamination equal to the ineligible rate -
the base rate restated, a tautology wearing a measurement's clothes. Real embeddings fail in a
specific way: a strong textual match on what the fund invests in, blind to where it may invest
and how much it may write. The synthetic score is built to fail the same way, and is named
`designed_similarity` so nobody reads it as a model.

`designed_similarity(candidate, mandate) -> float` in [0, 1], deterministic, reading only
`sector` and `stage`: 0.5 for a sector match plus 0.3 for a stage match, plus a deterministic
jitter in [0, 0.2) derived from `sha256(candidate.id)`, with the candidate id as the final sort key, so the order
is total and reproducible.
It reads neither `jurisdiction`, `check_size_max` nor `geography`, so a candidate in a
non-consented jurisdiction with a cheque under the floor and the wrong geography can top the
ablated arms on a perfect sector-and-stage match. That is the failure mode the filter exists for,
and the artifact states this construction beside every number that depends on it.

The geography axis is left inside the filter's remit and outside the score's on purpose:
geography is a mandate preference the score could plausibly have learned, and leaving it out
keeps the score's blindness legible as two hard axes (jurisdiction, cheque) plus one soft one,
which the per-axis breakdown in section 5 then reports separately.

## 5. The metric

For each (seed, mandate, K) cell and each ablated arm:

- `contamination = |{c in topK(arm) : classify(c, mandate)[0] is Eligibility.INELIGIBLE}| / K`,
  reported as the count and the K, never as a bare rate. (Amended 2026-08-31, before any run.
  The first spelling read "is not ELIGIBLE", which folded NEEDS_VERIFICATION into contamination
  in direct contradiction of the bullet below, and compared classify's tuple against an enum
  member; contamination counts hard exclusions only. Provenance, corrected 2026-09-01: this
  respelling, the clock-as-argument clause in section 7 and the candidate-mapping clause in
  section 2 were all the author's own pre-run review. Two earlier versions of this note, and the
  commit messages that landed them, attributed them to an advisor round dated 2026-08-31 that
  never ran; both attributions were false. The first genuine advisor round ran on 2026-09-01,
  after all of those edits, and returned three things: the respelling confirmed, the clock and
  mapping clauses confirmed as the author's own, and one new finding, the effect-level respelling
  of section 2's A2 test.)
- The per-axis breakdown: of the contaminated entries, how many fail on each of jurisdiction,
  cheque size, stage, sector, geography (an entry may fail several; counts are per axis, and the
  artifact says an entry can be counted under more than one). Method, pinned 2026-09-01 because
  the imported `classify` returns the failing axes for INELIGIBLE as an empty tuple: each axis is
  probed by calling the imported `classify` again against a copy of the mandate widened along
  that one axis (the candidate's own value substituted for stage, sector or geography; the
  candidate's jurisdiction added to the consented set; the floor lowered to the candidate's
  ceiling), and the axis counts as failed if the widened call still returns INELIGIBLE with all
  other axes widened, or, more simply, if widening that axis alone changes the verdict. The
  probe calls the import and decides nothing itself; a test holds that on a candidate failing
  exactly one axis the probe names that axis and no other.
- `needs_verification` entries in an ablated top K are reported as their own count, never folded
  into contamination: the imported vocabulary distinguishes a missing field from an exclusion,
  and this report keeps the distinction. (The synthetic generator emits no missing fields, so the
  count is expected to be zero on this substrate and is reported anyway.)
- Overlap with the shipped arm: the size of the intersection of topK(S) and topK(arm), over
  the size of topK(S), so the filter's effect on
  the eligible ordering is visible and not only its effect on admission.

Aggregates over seeds are reported as pooled counts over pooled denominators per (mandate, K),
with the per-seed minimum and maximum beside them. No aggregate is a mean of rates.

## 6. What is pre-registered

Fixed by this spec before the first contamination number was computed: the three arms and their
definitions; `n = 10000`; seeds 1 to 10; the three mandates; K in {5, 10, 20}; the score's exact
construction; the metric and its breakdowns; the readings in section 1. The artifact is produced
by one run of one command and frozen. A change to any pre-registered value after the run is a new
study with a new dated spec, never an edit to this one; a rerun after a technical defect in the
harness is permitted and the artifact's meta names the defect.

## 7. The artifact, the tests, the documents

`fixtures/ablation/matching_contamination.json`. Its provenance under `tests/test_fixture_meta.py`
is `hand_authored: true` with a note stating what that means here: the file is generated by one
run of a named deterministic command over synthetic inputs and no model, frozen; the `captured`
provenance is reserved by that test for model and session captures (a `captured_` filename
enters a family registry and a session-id check the ablation has no business in), and the
gold-rankings fixture, also a generated-then-frozen artifact over the same generator, already
sets this precedent. `meta` carries the `command` (`scripts/matching_ablation.py` with its
exact arguments), the spec path, the generator's pinned digest
`FROZEN_7_8` from `tests/synth/test_rosters.py` as its identity anchor, the imported library version from the wheel and the wheel's
sha256 beside it (two builds have shared one version in this portfolio before; the hash names
the build), the score's name, run date, command), the pre-registered parameters restated, then per-cell counts with
denominators and per-axis breakdowns, then the pooled aggregates. sha256-pinned by a test in the
gold-rankings pattern; the README section renders from it and never types a number.

CI asserts invariants only: the shipped arm's contamination is zero in every cell; every
denominator equals K; every eligible pool exceeds K_max on every recorded seed; the run is
deterministic (regenerating under the pinned parameters reproduces the artifact byte for byte;
the run date in meta is an argument to the generator, never a clock read, and the regeneration
check passes the frozen meta's own date back in, so determinism and the dated meta coexist);
A2's key equals the imported ranker's key. CI never asserts a contamination rate.

Documents that move, in the same commit as the frozen artifact and never before: the README's
matching row (its self-correction becomes a dated statement that the ablation ran), a short
Results section rendered from the artifact with the readings of section 1 applied to what was
measured, and the proposal's section 15 preamble if it counts this among the Designed absences.
The battery's rules bind every sentence: denominators beside rates, no em dashes, no claim past
what ran.

## 8. Constraints carried whole

No policy or ranking code in this repository - the arms call the imported `classify`,
`relationship_score` and the imported weights; the ablation module is measurement wiring and must
read as such under `tools/fleet_audit.py`. Determinism: no network, no key, no clock read; the run
is a function of the pinned parameters. Watched-red TDD with the repository's measured-red
practice. Gates before every commit, exit codes unpiped. Subjects under 72 chars, narrative
bodies, no trailers. All figures synthetic and invented, stated wherever they appear.
