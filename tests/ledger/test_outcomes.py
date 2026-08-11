import re
from datetime import datetime, timezone
from pathlib import Path
import pytest
from retinue.ledger.models import Touchpoint
from retinue.ledger.store import InMemoryStore
from retinue.ledger.outcomes import (OUTCOME_SIGNALS, OutcomeConfig, OutcomeRecord,
                                     last_touch_attribution, resolved_for)

T = [datetime(2030, 2, d, tzinfo=timezone.utc) for d in (1, 5, 9, 20)]

SCHEMA = Path(__file__).resolve().parents[2] / "schema.sql"
CREATE = "CREATE TABLE IF NOT EXISTS outcomes"

def outcome(signal="replied", occurred=T[2], observed=T[3], key="o1"):
    return OutcomeRecord(outcome_key=key, investor_id="inv-1", mandate_id="m-1",
                         signal=signal, occurred_at=occurred, observed_at=observed)

def test_unknown_signal_raises():
    with pytest.raises(Exception):
        outcome(signal="ghosted")

def test_occurred_and_observed_are_both_required_and_distinct():
    o = outcome()
    assert o.occurred_at != o.observed_at        # weeks apart in the world; both carried
    # Requiredness, not merely distinctness, because the two are separable: a default added to
    # either field later would keep every other test here green while writing a confident wrong
    # timestamp, and NOT NULL in schema.sql cannot catch that - a default writes a non-null.
    for missing in ("occurred_at", "observed_at"):
        fields = {"outcome_key": "o1", "investor_id": "inv-1", "mandate_id": "m-1",
                  "signal": "replied", "occurred_at": T[2], "observed_at": T[3]}
        del fields[missing]
        with pytest.raises(Exception):
            OutcomeRecord(**fields)

def test_active_signal_is_configuration_not_code():
    rows = (outcome("replied", key="o1"), outcome("meeting_booked", key="o2"))
    assert [o.outcome_key for o in resolved_for(OutcomeConfig(), rows)] == ["o1"]
    toggled = OutcomeConfig(active_signal="meeting_booked")
    assert [o.outcome_key for o in resolved_for(toggled, rows)] == ["o2"]

def test_the_third_signal_toggles_like_the_other_two():
    """check_written is the member the other tests never construct, so without this the enum
    exports a signal that is asserted nowhere on the Python side while the CHECK admits it."""
    rows = (outcome("replied", key="o1"), outcome("check_written", key="o3"))
    toggled = OutcomeConfig(active_signal="check_written")
    assert [o.outcome_key for o in resolved_for(toggled, rows)] == ["o3"]

def test_config_rejects_a_signal_outside_the_enum():
    with pytest.raises(Exception):
        OutcomeConfig(active_signal="vibes")

def test_last_touch_attribution_picks_latest_at_or_before_occurred():
    s = InMemoryStore()
    for key, occ in (("c1", T[0]), ("c2", T[1]), ("late", T[3])):
        s.append(Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                            kind="contact", payload={}, occurred_at=occ, recorded_at=T[3]))
    hit = last_touch_attribution(s, outcome(occurred=T[2]))
    assert hit.idempotency_key == "c2"           # latest <= occurred; never the later one

def test_a_touch_exactly_at_the_outcome_is_the_at_in_at_or_before():
    """The test above cannot tell `<` from `<=`: with no touch ON the boundary the two select the
    identical set. This is the other half of the rule the docstring and the schema both assert."""
    s = InMemoryStore()
    for key, occ in (("earlier", T[1]), ("exactly", T[2]), ("later", T[3])):
        s.append(Touchpoint(idempotency_key=key, investor_id="inv-1", mandate_id="m-1",
                            kind="contact", payload={}, occurred_at=occ, recorded_at=T[3]))
    hit = last_touch_attribution(s, outcome(occurred=T[2]))
    assert hit.idempotency_key == "exactly"      # simultaneous counts; strictly-before would not

def test_attribution_is_investor_level_and_crosses_mandates_by_design():
    """Pinned rather than left to be inferred: the record REQUIRES a mandate_id and attribution
    never reads it, so an outcome on one mandate attributes to the investor's latest touch on any
    mandate. Defensible at this size, and if it ever stops being so this test is where the
    decision surfaces instead of a silent change of meaning."""
    s = InMemoryStore()
    s.append(Touchpoint(idempotency_key="other-mandate", investor_id="inv-1", mandate_id="m-2",
                        kind="contact", payload={}, occurred_at=T[1], recorded_at=T[3]))
    hit = last_touch_attribution(s, outcome())   # the outcome is on m-1
    assert hit.idempotency_key == "other-mandate"

def test_attribution_on_a_new_investor_is_none_not_invented():
    assert last_touch_attribution(InMemoryStore(), outcome()) is None


# --- The CHECK constraint and the enum are one fact stated twice ------------------------------
#
# They fail in different lanes, which is the whole reason this needs holding: OUTCOME_SIGNALS is
# exercised on every run, and the CHECK first executes in CI. Add a member to the enum and every
# behavioural test above stays green, then an INSERT is refused in the lane nobody is watching.
# Same mechanism as tests/test_plan_sync.py, for the same reason.

def sql_check_list(sql_text: str) -> tuple[str, ...]:
    """The signals the outcomes CHECK admits, or a raised failure naming what went missing.

    Every way of not finding the constraint RAISES rather than returning an empty tuple. An empty
    return would still compare unequal and still redden the test below, but it would redden saying
    the enum had drifted, which sends the next reader to the wrong file with the wrong question.
    """
    try:
        start = sql_text.index(CREATE)
    except ValueError:
        raise AssertionError(f"schema.sql no longer carries {CREATE!r}")
    try:
        body = sql_text[start:sql_text.index(";", start)]
    except ValueError:
        raise AssertionError("the outcomes table statement is unterminated in schema.sql")
    match = re.search(r"CHECK \(signal IN \(([^)]*)\)\)", body)
    if match is None:
        raise AssertionError("the outcomes table no longer CHECKs signal against a list")
    return tuple(re.findall(r"'([^']*)'", match.group(1)))

def test_the_sql_check_list_matches_the_python_enum():
    """The claim "the database admits exactly what the enum declares" is worth what enforces it."""
    assert sql_check_list(SCHEMA.read_text(encoding="utf-8")) == OUTCOME_SIGNALS, (
        "schema.sql's CHECK on outcomes.signal and OUTCOME_SIGNALS have drifted apart; "
        "a value one side admits and the other refuses is an INSERT that fails first in CI")

def test_the_comparison_notices_a_drifted_check_list():
    """Without this, the rule above could be a helper agreeing with itself - an extractor that
    returned the enum, or a parser that found nothing, would pass over a drifted schema.

    The fixture is synthetic rather than built from OUTCOME_SIGNALS on purpose: a control that
    referenced the real enum would redden ALONGSIDE the rule above every time the enum changed,
    which measures the same fact twice instead of holding the comparison itself to account.
    """
    signals = ("alpha", "beta")
    honest = f"{CREATE} (\n    signal TEXT NOT NULL CHECK (signal IN ('alpha','beta'))\n);\n"
    assert sql_check_list(honest) == signals                              # a faithful copy passes
    assert sql_check_list(honest.replace(",'beta'", "")) != signals        # a dropped member
    assert sql_check_list(honest.replace("'alpha'", "'alpha','gamma'")) != signals   # an added one

def test_a_missing_table_or_check_raises_rather_than_matching_nothing():
    """Absence of a constraint is not evidence the constraint agrees."""
    with pytest.raises(AssertionError, match="no longer carries"):
        sql_check_list("a schema without that table\n")
    with pytest.raises(AssertionError, match="unterminated"):
        sql_check_list(f"{CREATE} (\n    signal TEXT NOT NULL")
    with pytest.raises(AssertionError, match="no longer CHECKs"):
        sql_check_list(f"{CREATE} (\n    signal TEXT NOT NULL\n);\n")
