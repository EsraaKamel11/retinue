from datetime import datetime, timezone
from decimal import Decimal
from inspect import signature
from itertools import product
import tracemalloc
import pytest
from retinue.ledger.models import BLOCK_DEFAULT_BUDGET, Touchpoint, plain_width

T = datetime(2030, 1, 5, tzinfo=timezone.utc)

def money(**payload):
    return Touchpoint(idempotency_key="m1", investor_id="inv-1", mandate_id="m-1",
                      kind="stated_check_size", payload=payload, occurred_at=T, recorded_at=T)

def test_a_money_touchpoint_without_an_amount_is_refused_at_construction():
    with pytest.raises(Exception, match="amount"):
        money()

def test_a_float_amount_is_refused_rather_than_coerced():
    with pytest.raises(Exception, match="float"):
        money(amount=250000.0)

def test_an_unparseable_amount_is_refused():
    with pytest.raises(Exception, match="usable decimal"):
        money(amount="two hundred fifty thousand")

def test_a_string_amount_is_accepted_and_survives_as_an_exact_decimal():
    t = money(amount="250000.01")
    assert Decimal(t.payload["amount"]) == Decimal("250000.01")

def test_a_non_finite_amount_is_refused():
    """`Decimal` parses these; only an explicit check refuses them.

    `NaN`, `Infinity` and `sNaN` all survive `Decimal(str(raw))`, render into the block as
    `stated_check_size: NaN`, and are then refused by the engine's canonicaliser, which drops the
    field from `record_values` in silence. That is the same silent-drop family this task closed for
    exponent notation, reached from a different input. `is_finite` rather than a comparison, because
    a signalling NaN raises InvalidOperation the moment anything compares it.
    """
    for raw in ("NaN", "-NaN", "sNaN", "Infinity", "-Infinity", "inf"):
        with pytest.raises(Exception, match="finite"):
            money(amount=raw)

def test_an_amount_too_wide_to_ever_render_is_refused_at_write():
    """The bound is STRUCTURAL, not a business limit on cheque sizes.

    Plain notation costs O(10^|exponent|) where `str(Decimal)` cost nothing, and `Decimal`'s default
    Emax is 999999999, so `"1E+999999999"` parses here and then attempts a roughly 1 GB string. The
    block's budget cannot catch it: `render_block` measures the string AFTER building it, so the
    allocation has already happened and the budget only reports on a string that exists. A guard
    that measures after the cost it guards against is not a guard.

    What is refused is exactly what could never render: a money value whose plain rendering alone
    does not fit the block's DEFAULT budget leaves no room for the header, the other five fields, or
    its own label, at any budget the block ships with. Refusing it once at write beats raising on
    every render forever. Nothing narrower is claimed, and the accepting arm below is what keeps
    this from quietly becoming a limit on what a ledger may record.
    """
    for raw in ("1E+999999999", "1E-999999999", "1E+1030", "-1E-1030"):
        with pytest.raises(Exception, match="plain notation"):
            money(amount=raw)

def test_the_width_bound_refuses_without_materialising_the_string():
    """The guard must not have the cost it exists to prevent, and ALLOCATION is what witnesses that.

    Written as a wall-clock bound first, and that version is the reason this docstring exists.
    Formatting `Decimal("1E+999999999")` is mostly a memset, so it costs about 2.3 seconds under a
    full-suite run and under 1.0 second when the same test runs alone: a one-second threshold went
    RED in the suite and GREEN in isolation off the same mutated code. A threshold the machine's
    mood can move is not a measurement, and it would have recorded this row as passing on a quiet
    run.

    Peak allocation separates the two arms by a factor no machine state can close. The arithmetic
    path costs a few KILOBYTES; formatting the same value peaks at 2,000,000,259 bytes, which is
    two GIGABYTES and was measured directly. The bound below sits far above the first and three
    orders of magnitude below the second.

    Stated as an order of magnitude on purpose, and this docstring carried four-significant-figure
    numbers for the real path until a review could not reproduce them. They were not wrong so much
    as unrepeatable: the construction's peak moves with what the interpreter has already allocated,
    measuring between roughly 2.9 KB in a bare script and 5.1 KB under pytest, so no single figure
    is a measurement of it. The byte boundaries in `test_block.py` were promoted from prose into
    assertions when they went stale; this number cannot be, because it legitimately moves, and a
    figure that cannot be asserted should not be written as though it had been. The margin holds
    at every one of those readings: 1 MB against 5.1 KB is still nearly 200x.

    (A formatting implementation may raise MemoryError on a smaller machine instead of allocating.
    That is red here too, which is the point.)

    KNOWN FRAGILITY, recorded rather than defended against: this assumes it is the only user of
    `tracemalloc`. Calling `start()` while tracing is already on does NOT reset the peak, and the
    `stop()` below would switch tracing off under whoever else had it on. Nothing else in the repo
    touches it and no ini or environment setting enables it, so it holds today; a second consumer,
    or `PYTHONTRACEMALLOC` set in some environment, would redden this for a reason having nothing
    to do with the guard. A test that fails for the wrong reason is worth naming before it does.
    """
    tracemalloc.start()
    try:
        with pytest.raises(Exception, match="plain notation"):
            money(amount="1E+999999999")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1_000_000, f"peak {peak} bytes: the guard materialised what it exists to refuse"

def test_a_wide_but_renderable_amount_is_still_accepted():
    # The accepting arm. `1E-900` is 902 characters in plain notation, inside the write barrier's
    # structural bound and outside the block's real budget once the other fields are counted, so it
    # is accepted here and raises at render. That split is deliberate: the write barrier refuses
    # only what can NEVER render, and the block keeps enforcing the budget it actually has.
    assert Decimal(money(amount="1E-900").payload["amount"]) == Decimal("1E-900")

def test_the_plain_width_arithmetic_agrees_with_the_formatter_it_predicts():
    """The arithmetic is trusted at 10^9 only because it is checked where the string can be built.

    `plain_width` exists to answer a question about a string nobody may allocate, so nothing about
    its result can be verified at the sizes that matter. It is pinned here against
    `len(format(value, "f"))` across every combination this grid reaches, which is what makes the
    unverifiable case an extrapolation from a measurement rather than an assertion.

    The zero-coefficient case is named separately because it is the one branch pure digit-counting
    gets wrong: `format(Decimal("0E+2"), "f")` is `"0"`, not `"0.00"` and not three characters, so
    an implementation that adds the exponent to the digit count over-refuses on a stored zero.
    """
    for coeff, exp, sign in product(("0", "1", "7", "10", "105", "9999", "100000", "123456789"),
                                    range(-25, 26), ("", "-")):
        value = Decimal(f"{sign}{coeff}E{exp:+d}")
        assert plain_width(value) == len(format(value, "f")), f"{value} disagrees"
    for spelling in ("0E+2", "0E+9", "-0E+3", "0", "-0", "0.00"):
        value = Decimal(spelling)
        assert plain_width(value) == len(format(value, "f")), f"{spelling} disagrees"

def test_the_write_barriers_bound_is_the_blocks_own_default_budget():
    """Double entry, because the constant cannot be imported from where it belongs.

    `models.py -> block.py -> projection.py -> models.py` is an import cycle, so the budget is
    written in two files and this test holds the two spellings equal. Read off `render_block`'s
    signature rather than a second literal: the default is what the block actually applies when no
    caller passes one, and that is the number the write barrier's bound is derived from. The import
    is local so that this coupling is the only place the cycle's far side is touched.
    """
    from retinue.ledger.block import render_block
    assert BLOCK_DEFAULT_BUDGET == signature(render_block).parameters["budget"].default

def test_kinds_that_carry_no_money_are_unaffected_by_the_amount_rule():
    Touchpoint(idempotency_key="c1", investor_id="inv-1", mandate_id="m-1", kind="contact",
               payload={}, occurred_at=T, recorded_at=T)
