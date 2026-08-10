from retinue.synth.rosters import generate_rosters

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
