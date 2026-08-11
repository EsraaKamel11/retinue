import hashlib
import json
from retinue.synth.rosters import generate_rosters

#: sha256 of `json.dumps(generate_rosters(7, 8), sort_keys=True)`. Regenerate deliberately, never
#: to make a red test green: the tasks whose golds are keyed to this substrate choose their rows
#: out of it by hand.
FROZEN_7_8 = "c23a8ecc760659bbe87c391003bbb240fdd102e3f9db411830f5174db8cfa656"

# The axes chaperone's `classify` reads off a Candidate, spelled as the roster row spells them.
# Task 13 builds a Candidate from a row: a name dropped here arrives there as None, which
# `classify` reports as a distinct missing state, so every generated row would route to
# needs-verification with nothing in the generator looking wrong.
AXES = {"investor_id", "jurisdiction", "check_ceiling", "stage", "sector", "geography"}

def test_same_seed_same_rosters():
    assert generate_rosters(7, 5) == generate_rosters(7, 5)

def test_different_seed_differs():
    assert generate_rosters(7, 5) != generate_rosters(8, 5)

def test_n_rows_each_carrying_the_axes_the_matcher_filters_on():
    # The two tests above are satisfied by a generator that ignores `n` and returns the seed in a
    # one-element tuple: (7,) == (7,) and (7,) != (8,). They pin determinism, not rosters. This is
    # the assertion that makes them about rosters.
    rows = generate_rosters(7, 5)
    assert len(rows) == 5
    for row in rows:
        assert AXES <= set(row), f"row is missing {sorted(AXES - set(row))}"

def test_the_generated_substrate_is_frozen_to_a_digest():
    """The two tests above compare the generator against ITSELF, so both stay green through a
    change of values: reordering `_SECTORS` shifts every downstream `rng.choice`, and neither test
    can object. It would surface later, as a confusing failure in the task whose hand-chosen golds
    are keyed to this substrate. This pins the values themselves.

    `sort_keys=True` so that reordering the keys in the row literal - cosmetic, no value moves -
    does not redden, while renaming or dropping one still does. The first row is asserted beside
    the digest because a bare digest mismatch says only that something moved.
    """
    rows = generate_rosters(7, 8)
    assert rows[0] == {"investor_id": "synth-000", "sector": "climate", "stage": "pre-seed",
                       "geography": "eu-west", "jurisdiction": "DE",
                       "check_floor": 100_000, "check_ceiling": 1_500_000}
    assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == FROZEN_7_8
