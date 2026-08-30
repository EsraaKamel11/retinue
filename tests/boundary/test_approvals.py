"""The approval store contract, both halves. The Postgres tests skip without a DSN and FAIL
under RETINUE_PG_REQUIRED=1, the same posture test_review_queue.py:136-140 establishes."""
import dataclasses
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, MemoryResolutionLog,
                                        body_digest_of, resolve)

T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)
SCHEMA = Path(__file__).resolve().parents[2] / "schema.sql"


def token(tok="a" * 32, key="k-1", body="hello", tool="mcp__retinue__send_message",
          domain="example.test", res=1):
    return ApprovalToken(token=tok, idempotency_key=key, body_digest=body_digest_of(body),
                         tool=tool, recipient_domain=domain, resolution_id=res,
                         minted_at=T0, expires_at=T0 + timedelta(hours=24))


def test_the_digest_is_sha256_over_utf8_bytes():
    import hashlib
    assert body_digest_of("café") == hashlib.sha256("café".encode()).hexdigest()


def test_put_token_is_first_writer_wins_on_the_token_id():
    s = MemoryApprovalStore()
    assert s.put_token(token()) is True
    assert s.put_token(token(body="different")) is False
    assert s.get_token("a" * 32).body_digest == body_digest_of("hello")


def test_get_token_answers_none_for_a_token_never_minted():
    assert MemoryApprovalStore().get_token("b" * 32) is None


def test_consume_is_an_append_that_wins_exactly_once():
    s = MemoryApprovalStore()
    s.put_token(token())
    assert s.consume("a" * 32, T0) is True
    assert s.consume("a" * 32, T0) is False


def test_consume_of_a_never_minted_token_still_wins_only_once():
    # The consumption table is its own append; validity conjunction is the caller's job. A
    # consume row without a mint row is refusable garbage, never a crash.
    s = MemoryApprovalStore()
    assert s.consume("c" * 32, T0) is True
    assert s.consume("c" * 32, T0) is False


# --- The resolution: the design's single named update, and the mint that IS the resolution. --


def test_an_approving_resolution_writes_once_and_mints_a_bound_token():
    """EVERY field against the ARGUMENT it came from, never against the token itself.

    The review's I1, and the reason it was the top finding: this test used to assert three fields
    and then `appr.get_token("d" * 32) == t`, which compares the stored row to the same object the
    call returned. That line says the store holds the token and says nothing whatever about what
    the token is bound to, so `idempotency_key=""`, `tool` and `recipient_domain` swapped, and
    `minted_at` corrupted all survived the whole suite at 279 green.

    `tool` and `recipient_domain` are exactly the pair the spec's 2026-08-30 amendment added to
    close an authorization hole, and this is the site where their binding is DECIDED. The
    identical hazard was already named one layer down, in the docstring of
    `test_the_select_reads_the_field_order_the_adapter_splats_the_row_into`; the mint reproduced
    it and shipped no test. Each line below spells its expected value independently, from the
    call's own arguments, so a swap has nothing to hide behind.
    """
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    t = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-1",
                window=timedelta(hours=24), resolutions=res, approvals=appr,
                key="k-7", body="hello", tool="mcp__retinue__send_message",
                recipient_domain="example.test", token_id="d" * 32)
    assert t is not None
    assert t.token == "d" * 32
    assert t.idempotency_key == "k-7"
    assert t.body_digest == body_digest_of("hello")
    assert t.tool == "mcp__retinue__send_message"
    assert t.recipient_domain == "example.test"
    assert t.resolution_id == 7
    assert t.minted_at == T0
    assert t.expires_at == T0 + timedelta(hours=24)
    # Now that the object above is pinned field by field, this one says the store holds THAT row.
    assert appr.get_token("d" * 32) == t


def test_a_double_resolution_is_first_writer_wins_and_the_loser_mints_nothing():
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    first = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-1",
                    window=timedelta(hours=24), resolutions=res, approvals=appr,
                    key="k-7", body="hello", tool="t", recipient_domain="d",
                    token_id="e" * 32)
    second = resolve(row_id=7, verdict="approve", at=T0, approved_by="reviewer-2",
                     window=timedelta(hours=24), resolutions=res, approvals=appr,
                     key="k-7", body="hello", tool="t", recipient_domain="d",
                     token_id="f" * 32)
    assert first is not None and second is None
    assert appr.get_token("f" * 32) is None


def test_a_rejecting_resolution_writes_resolved_and_mints_nothing():
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    out = resolve(row_id=9, verdict="reject", at=T0, approved_by="reviewer-1",
                  window=timedelta(hours=24), resolutions=res, approvals=appr,
                  key="k-9", body="no", tool="t", recipient_domain="d")
    assert out is None
    assert res.record(9, T0, "reviewer-2") is False   # the row is already resolved


def test_first_writer_wins_is_per_row_and_never_a_single_global_latch():
    """A `record` that latched on the FIRST call of any kind passes both tests above.

    It would refuse every resolution after the first one the process ever made, which is a queue
    that resolves exactly one row per restart, and neither test here would notice.
    """
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    for row, tok in ((7, "1" * 32), (8, "2" * 32)):
        t = resolve(row_id=row, verdict="approve", at=T0, approved_by="reviewer-1",
                    window=timedelta(hours=24), resolutions=res, approvals=appr,
                    key=f"k-{row}", body="hello", tool="t", recipient_domain="d", token_id=tok)
        assert t is not None and t.resolution_id == row


def test_an_unnamed_token_is_minted_with_a_32_hex_id_and_two_mints_differ():
    """Spec section 1: an opaque random identifier, 32 hex chars from a CSPRNG.

    Every other test in this file hands `token_id` in, so the default id - the one every real
    resolution uses, since only the tests and the doubled-mint case ever name a token - is
    asserted by nothing without this. A default of `"token"`, or of the row id, would sail
    through the whole file and collide on the second mint in production.
    """
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    minted = [resolve(row_id=row, verdict="approve", at=T0, approved_by="reviewer-1",
                      window=timedelta(hours=24), resolutions=res, approvals=appr,
                      key=f"k-{row}", body="hello", tool="t", recipient_domain="d")
              for row in (11, 12)]
    assert all(re.fullmatch(r"[0-9a-f]{32}", t.token) for t in minted)
    assert minted[0].token != minted[1].token


def test_a_mixed_second_verdict_settles_nothing_the_first_resolution_already_settled():
    """Both mixed orders, which the brief's checklist names and no test covered.

    They hold because the `record` gate is verdict-independent and sits ABOVE the verdict check,
    so approve-then-reject and reject-then-approve walk one line: the second reviewer resolves
    nothing and mints nothing, and a late approval cannot mint over a rejected row. Hoist the
    verdict check above `record` and the second half of this test goes red.
    """
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    common = dict(at=T0, approved_by="reviewer-1", window=timedelta(hours=24), resolutions=res,
                  approvals=appr, key="k", body="hello", tool="t", recipient_domain="d")
    first = resolve(row_id=7, verdict="approve", token_id="3" * 32, **common)
    assert resolve(row_id=7, verdict="reject", **common) is None
    assert appr.get_token("3" * 32) == first        # the late rejection did not unmint anything

    assert resolve(row_id=8, verdict="reject", **common) is None
    assert resolve(row_id=8, verdict="approve", token_id="4" * 32, **common) is None
    assert appr.get_token("4" * 32) is None         # the late approval minted nothing


def test_a_colliding_caller_supplied_token_id_refuses_before_it_spends_the_row():
    """The review's I3, ruled: that state may not be reached silently.

    The collision used to be discovered AFTER the resolution was recorded, so `resolve` answered
    None over a row left resolved, tokenless and unresolvable for good - the state spec section 2
    writes its atomicity sentence to prevent, reached with no crash and no race, and
    indistinguishable to the caller from losing one. Generate-and-retry is not the answer, since a
    caller-supplied id is the caller's own evidence. So the collision is refused BEFORE the
    resolution write: it raises, the row survives, and a correct retry still resolves it.
    """
    res, appr = MemoryResolutionLog(), MemoryApprovalStore()
    common = dict(verdict="approve", at=T0, approved_by="reviewer-1", window=timedelta(hours=24),
                  resolutions=res, approvals=appr, key="k", body="hello", tool="t",
                  recipient_domain="d")
    taken = resolve(row_id=7, token_id="5" * 32, **common)
    assert taken is not None
    with pytest.raises(ValueError):
        resolve(row_id=8, token_id="5" * 32, **common)
    assert appr.get_token("5" * 32) == taken        # row 7's token is untouched by the refusal
    # The row survived, which is the whole finding: a correct retry still resolves row 8.
    again = resolve(row_id=8, token_id="6" * 32, **common)
    assert again is not None and again.resolution_id == 8


# --- Double entry between the three SQL constants and schema.sql, read KEYLESSLY. ------------
#
# The gate a review mutant proved missing: all three statements below were pointed at tables that
# do not exist and the whole suite stayed green, because every line of SQL in this module is
# executable only in the DSN lane. That is the hazard `test_review_queue.py:67-106` already exists
# for, in its own words - a name renamed on one side of the pair surfaces first in a lane that has
# never run - and the constants were hoisted to module level citing that precedent, which supplied
# the mechanism for a gate that was then not written.
#
# Two legs here that the review_queue gate does not need. `PgApprovalStore.get_token` builds its
# result with `ApprovalToken(*row)`, so `SELECT_TOKEN`'s column ORDER is load-bearing and not only
# its column set. And the conflict TARGET is pinned, so `rowcount == 1` cannot come to mean
# something different in one half than in the other.
#
# Findings are NAMED and returned rather than asserted in place, the shape `tools/fleet_audit.py`
# uses, so that every branch can be driven by a planted violation below. A gate whose firing path
# no test has walked is a gate that reports ok for a scan that never happened.

_INSERT = re.compile(r"INSERT INTO (\w+) \(([^)]*)\) VALUES \(([^)]*)\)"
                     r"\s*ON CONFLICT \((\w+)\) DO NOTHING")
_SELECT = re.compile(r"SELECT (.*?) FROM (\w+) WHERE")
_COLUMN = re.compile(r"^\s*(\w+)\s+[A-Z].*$", re.MULTILINE)


def _table_block(schema_text: str, table: str) -> str | None:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {re.escape(table)} \((.*?)\n\);",
                  schema_text, re.DOTALL)
    return None if m is None else m.group(1)


def _declared(block: str) -> dict[str, str]:
    return {m.group(1): m.group(0) for m in _COLUMN.finditer(block)}


def insert_findings(sql: str, schema_text: str) -> list[str]:
    """What schema.sql disagrees with in one INSERT. Empty means the two spellings are one fact."""
    m = _INSERT.match(sql.strip())
    if not m:
        return ["insert_unparsed: not a targeted "
                f"INSERT INTO t (cols) VALUES (...) ON CONFLICT (col) DO NOTHING:\n{sql}"]
    table, cols, placeholders, target = m.groups()
    columns = [c.strip() for c in cols.split(",")]
    findings: list[str] = []
    if len(placeholders.split(",")) != len(columns):
        findings.append(f"placeholder_arity: {len(columns)} columns against "
                        f"{len(placeholders.split(','))} placeholders")
    block = _table_block(schema_text, table)
    if block is None:
        # Returned rather than appended: with no table there is nothing further to read, and
        # every check below would hold vacuously against an empty column set.
        return findings + [f"table_undeclared: schema.sql declares no table named {table!r}"]
    declared = _declared(block)
    # PRIMARY KEY joins NOT NULL as a required column, which is stricter than the review_queue
    # gate and correct: a primary key is implicitly NOT NULL, so a gate reading only the literal
    # words would let an INSERT drop the one column that identifies the row. GENERATED columns are
    # excluded from both sides because they REJECT an explicit value.
    required = {n for n, line in declared.items()
                if ("NOT NULL" in line or "PRIMARY KEY" in line) and "GENERATED" not in line}
    generated = {n for n, line in declared.items() if "GENERATED" in line}
    if not required:
        return findings + [f"no_required_columns: nothing parsed out of {table!r}, "
                           "so the containments below would hold vacuously"]
    missing = sorted(required - set(columns))
    if missing:
        findings.append(f"insert_misses_required: {table} demands {missing} and the INSERT "
                        f"writes {sorted(columns)}")
    undeclared = sorted(set(columns) - (set(declared) - generated))
    if undeclared:
        findings.append(f"insert_writes_undeclared: {undeclared} against a table declaring "
                        f"{sorted(declared)}, of which {sorted(generated)} reject a value")
    if target not in declared:
        findings.append(f"conflict_target_undeclared: {target!r} is not a column of {table}")
    elif "PRIMARY KEY" not in declared[target]:
        findings.append(f"conflict_target_not_the_primary_key: {target!r}, so `rowcount == 1` "
                        "would stop meaning first-writer-wins on the row identity")
    return findings


def select_findings(sql: str, schema_text: str, fields: tuple[str, ...]) -> list[str]:
    """What disagrees in the SELECT. Column ORDER is checked, not merely the set."""
    m = _SELECT.search(sql)
    if not m:
        return [f"select_unparsed: no SELECT ... FROM t WHERE in:\n{sql}"]
    cols_text, table = m.groups()
    columns = [c.strip() for c in cols_text.split(",")]
    findings: list[str] = []
    if tuple(columns) != tuple(fields):
        findings.append(f"select_order: the SELECT reads {columns} and the caller binds them "
                        f"positionally to {list(fields)}")
    block = _table_block(schema_text, table)
    if block is None:
        return findings + [f"table_undeclared: schema.sql declares no table named {table!r}"]
    # `_declared_all`, defined below with the UPDATE leg, so a column arriving by ALTER is
    # declared to THIS leg too. The review's M6: reading only the block would redden this gate on
    # correct SQL the first time a hoisted SELECT names `approved_by`.
    undeclared = sorted(set(columns) - set(_declared_all(schema_text, table)))
    if undeclared:
        findings.append(f"select_reads_undeclared: {undeclared} not declared by {table}")
    return findings


def _schema() -> str:
    text = SCHEMA.read_text(encoding="utf-8")
    assert "CREATE TABLE" in text, f"nothing readable at {SCHEMA}, so every gate below is vacuous"
    return text


def _fields() -> tuple[str, ...]:
    return tuple(f.name for f in dataclasses.fields(ApprovalToken))


def test_the_token_insert_and_the_approvals_table_are_one_fact_in_two_spellings():
    from retinue.boundary.approvals import INSERT_TOKEN
    assert insert_findings(INSERT_TOKEN, _schema()) == []


def test_the_consumption_insert_and_its_table_are_one_fact_in_two_spellings():
    from retinue.boundary.approvals import INSERT_CONSUMPTION
    assert insert_findings(INSERT_CONSUMPTION, _schema()) == []


def test_the_select_reads_the_field_order_the_adapter_splats_the_row_into():
    """`ApprovalToken(*row)` binds by POSITION, so the column order is part of the contract.

    A set comparison passes over a swap. This is the leg the review named: `tool` and
    `recipient_domain` are the two fields the spec's 2026-08-30 amendment added to close an
    authorization hole, and swapping them in the SELECT would bind each to the other's meaning
    while every other test in this file stayed green.
    """
    from retinue.boundary.approvals import SELECT_TOKEN
    assert select_findings(SELECT_TOKEN, _schema(), _fields()) == []


def test_the_gate_catches_a_table_the_schema_never_declares():
    """The review's surviving mutant, planted here so it can never survive again.

    All three constants were pointed at nonexistent tables and the full suite stayed 252 green.
    """
    from retinue.boundary.approvals import (INSERT_CONSUMPTION, INSERT_TOKEN, SELECT_TOKEN)
    schema = _schema()
    assert any("table_undeclared" in f for f in
               insert_findings(INSERT_TOKEN.replace("approvals", "no_such_table"), schema))
    assert any("table_undeclared" in f for f in insert_findings(
        INSERT_CONSUMPTION.replace("approval_consumptions", "no_such_table"), schema))
    assert any("table_undeclared" in f for f in select_findings(
        SELECT_TOKEN.replace("approvals", "no_such_table"), schema, _fields()))


def test_the_gate_catches_a_column_the_table_never_declares():
    from retinue.boundary.approvals import INSERT_TOKEN
    assert any("insert_writes_undeclared" in f for f in
               insert_findings(INSERT_TOKEN.replace("body_digest", "body_hash"), _schema()))


def test_the_gate_catches_a_required_column_the_insert_never_fills():
    from retinue.boundary.approvals import INSERT_TOKEN
    mutant = (INSERT_TOKEN.replace("recipient_domain, ", "")
                          .replace("%s,%s,%s,%s,%s,%s,%s,%s", "%s,%s,%s,%s,%s,%s,%s"))
    assert any("insert_misses_required" in f for f in insert_findings(mutant, _schema()))


def test_the_gate_catches_a_reordered_select():
    from retinue.boundary.approvals import SELECT_TOKEN
    swapped = SELECT_TOKEN.replace("tool, recipient_domain", "recipient_domain, tool")
    assert any("select_order" in f for f in select_findings(swapped, _schema(), _fields()))


def test_the_gate_catches_an_untargeted_conflict_clause():
    """A bare `ON CONFLICT DO NOTHING` fires on ANY unique constraint the table carries.

    Correct today, because `token` is the only unique index on either table. It is a latent
    divergence rather than a present defect, and this gate is what keeps it from opening: a
    UNIQUE added later on `idempotency_key` would make `put_token` answer False for a DIFFERENT
    token colliding on that key, where `MemoryApprovalStore` answers True. Two halves whose whole
    purpose is identical semantics would split, and only in the lane the default suite never runs.
    """
    from retinue.boundary.approvals import INSERT_TOKEN
    untargeted = INSERT_TOKEN.replace("ON CONFLICT (token) DO NOTHING", "ON CONFLICT DO NOTHING")
    assert untargeted != INSERT_TOKEN, "the constant is already untargeted, so this plants nothing"
    assert any("insert_unparsed" in f for f in insert_findings(untargeted, _schema()))


def test_the_gate_catches_a_conflict_target_that_is_not_the_primary_key():
    from retinue.boundary.approvals import INSERT_TOKEN
    mutant = INSERT_TOKEN.replace("ON CONFLICT (token)", "ON CONFLICT (idempotency_key)")
    assert any("conflict_target_not_the_primary_key" in f
               for f in insert_findings(mutant, _schema()))


# --- The SAME double entry over the design's ONE named update, and over the CLI's read. ------
#
# `RESOLVE_ROW` is the only UPDATE this design contains (spec section 2, named there as such) and
# `SELECT_HANDOFF` is the operator CLI's only read. Both execute in the DSN lane and nowhere else,
# so every word of the section above applies to them unchanged. Three legs the INSERT gate above
# has no need of:
#
#   * the SET list is pinned to the resolution's two columns. An update that stopped writing
#     `approved_by` would resolve rows carrying no reviewer, and `approved_by` is precisely the
#     provenance the spec's 2026-08-30 amendment added - which human approved this.
#   * `AND resolved_at IS NULL` is pinned, because that clause IS the test-and-set. Without it the
#     UPDATE succeeds against an already-resolved row, `rowcount == 1` comes back for the second
#     resolver too, and first-writer-wins - the whole reason a double resolution mints exactly one
#     token - stops holding in the lane the default suite never runs.
#   * the WHERE keys on the PRIMARY KEY, so `rowcount == 1` means one row rather than one of many.
#
# `approved_by` reaches `review_queue` by ALTER and is absent from the `CREATE TABLE` block, so the
# declared set is read from BOTH statements. A gate reading only the block would redden on correct
# SQL, which is the trap Task 1's review named as its M4 before this gate existed.

_UPDATE = re.compile(r"UPDATE (\w+) SET (.+?) WHERE (.+)$")
_ALTER = re.compile(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)([^;]*);")


def _declared_all(schema_text: str, table: str) -> dict[str, str]:
    """Every column the schema declares for `table`, from its CREATE TABLE and its ALTERs."""
    block = _table_block(schema_text, table)
    declared = {} if block is None else _declared(block)
    for m in _ALTER.finditer(schema_text):
        if m.group(1) == table:
            declared[m.group(2)] = m.group(0)
    return declared


def update_findings(sql: str, schema_text: str,
                    expected: tuple[str, ...] = ("resolved_at", "approved_by")) -> list[str]:
    """What schema.sql disagrees with in the resolution UPDATE. Empty means one fact, two
    spellings. The guard clause and the keyed column are read as well as the column names,
    because they are what make `rowcount == 1` mean first-writer-wins on one row."""
    m = _UPDATE.match(sql.strip())
    if not m:
        return [f"update_unparsed: not an UPDATE t SET ... WHERE ...:\n{sql}"]
    table, sets, where = m.groups()
    assignments = [a.strip() for a in sets.split(",")]
    columns = [a.split("=")[0].strip() for a in assignments]
    findings: list[str] = []
    if tuple(columns) != tuple(expected):
        findings.append(f"update_sets: the resolution writes {columns} where the design's one "
                        f"named update writes {list(expected)}")
    if sets.count("%s") != len(assignments):
        findings.append(f"placeholder_arity: {len(assignments)} assignments against "
                        f"{sets.count('%s')} placeholders")
    if not re.search(r"\bAND\s+resolved_at IS NULL\b", where):
        findings.append("guard_dropped: the WHERE carries no `AND resolved_at IS NULL`, so the "
                        "update stops being a test-and-set and the second resolver wins too")
    declared = _declared_all(schema_text, table)
    if not declared:
        # Returned rather than appended, for the reason insert_findings returns here: with no
        # table there is nothing to read and every check below would hold vacuously.
        return findings + [f"table_undeclared: schema.sql declares no table named {table!r}"]
    undeclared = sorted(set(columns) - set(declared))
    if undeclared:
        findings.append(f"update_sets_undeclared: {undeclared} against a table declaring "
                        f"{sorted(declared)}")
    key = re.match(r"(\w+) = %s\b", where)
    if key is None or "PRIMARY KEY" not in declared.get(key.group(1), ""):
        named = "nothing" if key is None else repr(key.group(1))
        findings.append(f"update_not_keyed_on_the_primary_key: the WHERE keys on {named}, so "
                        "`rowcount == 1` would stop meaning one identified row")
    return findings


def test_the_resolution_update_and_the_review_queue_table_are_one_fact_in_two_spellings():
    from retinue.boundary.approvals import RESOLVE_ROW
    assert update_findings(RESOLVE_ROW, _schema()) == []


def test_the_clis_read_of_the_review_row_is_held_against_the_same_schema():
    """The CLI's SELECT is a fourth statement that only the DSN lane executes, so it is pinned
    the way the other three are rather than left to be discovered by an operator."""
    from retinue.boundary.resolve import SELECT_HANDOFF
    assert select_findings(SELECT_HANDOFF, _schema(), ("handoff",)) == []


def test_the_gate_reads_the_column_that_arrives_by_alter_and_not_only_the_create_block():
    """`approved_by` is added by `ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS`.

    A gate parsing only the `CREATE TABLE` block would call the correct UPDATE undeclared, which
    is the failure Task 1's review predicted as its M4. Driven both ways: the real schema is
    clean above, and a schema with the ALTER line deleted reddens on that exact column.
    """
    from retinue.boundary.approvals import RESOLVE_ROW
    without = re.sub(r"ALTER TABLE review_queue[^;]*;", "", _schema())
    assert "approved_by" not in without, "the ALTER is still there, so this plants nothing"
    assert any("update_sets_undeclared" in f for f in update_findings(RESOLVE_ROW, without))


def test_the_select_leg_of_the_gate_reads_that_column_too():
    """The review's M6: the UPDATE leg learned to read the ALTER and the SELECT leg did not.

    Latent rather than present, because the only hoisted SELECT over `review_queue` reads
    `handoff`, which is in the CREATE TABLE block. It becomes a false red the first time the
    operator path wants `SELECT resolved_at, approved_by ...` to show who resolved a row, and a
    gate that reddens on correct SQL is the shape that gets exempted. Driven both ways, like the
    UPDATE leg above.
    """
    sql = "SELECT approved_by FROM review_queue WHERE id = %s"
    assert select_findings(sql, _schema(), ("approved_by",)) == []
    without = re.sub(r"ALTER TABLE review_queue[^;]*;", "", _schema())
    assert any("select_reads_undeclared" in f
               for f in select_findings(sql, without, ("approved_by",)))


def test_the_gate_catches_a_resolution_pointed_at_a_table_the_schema_never_declares():
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace("review_queue", "no_such_table")
    assert mutant != RESOLVE_ROW, "the constant names another table, so this plants nothing"
    assert any("table_undeclared" in f for f in update_findings(mutant, _schema()))


def test_the_gate_catches_a_resolution_that_stops_recording_the_reviewer():
    """The provenance leg: which human approved this act (spec section 1, amended 2026-08-30)."""
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace(", approved_by = %s", "")
    assert mutant != RESOLVE_ROW, "nothing writes approved_by, so this plants nothing"
    assert any("update_sets" in f for f in update_findings(mutant, _schema()))


def test_the_gate_catches_a_set_column_the_table_never_declares():
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace("approved_by =", "approved_by_whom =")
    assert any("update_sets_undeclared" in f for f in update_findings(
        mutant, _schema(), expected=("resolved_at", "approved_by_whom")))


def test_the_gate_catches_a_resolution_that_drops_its_first_writer_wins_guard():
    """The mutant that matters most: without the guard the second resolver also reads
    `rowcount == 1`, and a double resolution mints two tokens over one human act."""
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace(" AND resolved_at IS NULL", "")
    assert mutant != RESOLVE_ROW, "the guard is already absent, so this plants nothing"
    assert any("guard_dropped" in f for f in update_findings(mutant, _schema()))


def test_the_gate_catches_a_resolution_keyed_on_something_other_than_the_row_identity():
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace("WHERE id = %s", "WHERE queue_name = %s")
    assert mutant != RESOLVE_ROW, "the update is not keyed on id, so this plants nothing"
    assert any("update_not_keyed_on_the_primary_key" in f
               for f in update_findings(mutant, _schema()))


def test_the_gate_catches_an_update_whose_placeholders_do_not_match_its_assignments():
    from retinue.boundary.approvals import RESOLVE_ROW
    mutant = RESOLVE_ROW.replace("approved_by = %s", "approved_by = 'nobody'")
    assert any("placeholder_arity" in f for f in update_findings(mutant, _schema()))


def test_the_gate_catches_a_statement_that_is_not_an_update_at_all():
    from retinue.boundary.approvals import RESOLVE_ROW
    assert any("update_unparsed" in f
               for f in update_findings(RESOLVE_ROW.split(" WHERE ")[0], _schema()))


# --- The operator CLI's binding material, read KEYLESSLY. -------------------------------------
#
# The CLI itself needs a DSN. What it BINDS a token to does not, and that is where the hazard is:
# the durable review row stores a `Handoff` dump, which carries `blocked_body` and
# `recipient_domain` and carries neither an idempotency key nor a tool name. A CLI reading `body`
# or `tool` off that dump would bind every token it ever minted to the empty string, and because
# the resolution is first-writer-wins the row would be spent for good on a token no send could
# ever validate against. So the derivation is a function, and the function is pinned here.


def _handoff_dump() -> dict:
    """A REAL `Handoff`, dumped the way `DurableQueues.put` dumps it into the row.

    Built from the imported model rather than typed as a literal, so a field renamed in the
    vendored wheel reddens here instead of in an operator's terminal.
    """
    from chaperone.gates.handoff import Handoff
    return Handoff(reason_category="act:figure_not_in_record", detector_outage=None,
                   violating_span="$9M", blocked_body="The round is $9M.",
                   recipient_domain="example.test", recipient_jurisdiction="US",
                   cited_field_values={}, thread_excerpt="", proposed_alternative=None,
                   refinement_rounds=0).model_dump()


def test_the_binding_is_read_from_the_fields_the_stored_row_actually_carries():
    from retinue.boundary.resolve import binding_material
    binding, missing = binding_material(_handoff_dump(), key="k-7",
                                        tool="mcp__retinue__send_message")
    assert missing == []
    assert binding == {"key": "k-7", "body": "The round is $9M.",
                       "tool": "mcp__retinue__send_message",
                       "recipient_domain": "example.test"}


def test_every_source_that_supplied_nothing_is_named_rather_than_bound_to_the_empty_string():
    from retinue.boundary.resolve import binding_material
    binding, missing = binding_material({}, key=None, tool=None)
    assert missing == ["--key", "--tool", "the handoff's blocked_body",
                       "the handoff's recipient_domain"]
    assert binding == {"key": "", "body": "", "tool": "", "recipient_domain": ""}


def test_an_approval_that_cannot_bind_refuses_before_it_ever_opens_a_connection(capsys):
    """The order is the property: the refusal precedes the resolution, never follows it.

    `record` is first-writer-wins, so an approve that resolved the row and only then found it
    could not bind would leave a row nobody can resolve again and a token nobody can spend, with
    no way back but a fresh draft. The DSN here is deliberately unusable and psycopg rejects the
    string before any network, so a guard that moved below the read raises instead of returning 2.
    """
    from retinue.boundary.resolve import main
    code = main(["7", "--approve", "--by=reviewer-1", "--at=2030-01-02T00:00:00+00:00",
                 "--dsn=not a dsn at all"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--key" in err and "--tool" in err


# --- Everything the CLI does AFTER the read, driven keylessly through the seam. ----------------
#
# The review's I2: the second refusal ran before `resolve` by inspection and by nothing else, and
# a mutant moving it BELOW the resolution - the row-destroying order the whole D1 argument is
# against - survived the entire suite at 279 green. Everything under `psycopg.connect` was
# undriven: that refusal, the missing-row exit, the text-column parse branch, and both post-resolve
# exit codes.
#
# So the decision is a function of the ROW rather than of a connection, and `main` is the thin
# wiring that fetches the row and hands it over. No connection double is installed and no database
# is reached; the seam is the row value and the resolve callable.
#
# The injected callable is the REAL `resolve` over the REAL memory halves, which is what lets every
# assertion below be an effect on actual state rather than a count of calls. "The refusal ran
# before the resolution" is asserted as `res.record(row, ...) is True` afterwards: the row is still
# resolvable, which is only true if nothing resolved it.


def _seam(res, appr, minted: list):
    """The CLI's resolve seam, wired to the memory stores. Returns what `resolve` returns."""
    def resolve_fn(**kwargs):
        token = resolve(resolutions=res, approvals=appr, **kwargs)
        minted.append(token)
        return token
    return resolve_fn


def _call(row, res, appr, minted, **overrides):
    from retinue.boundary.resolve import outcome_after_read
    call = dict(row_id=7, approve=True, by="reviewer-1", at=T0, window=timedelta(hours=24),
                key="k-7", tool="mcp__retinue__send_message", resolve_fn=_seam(res, appr, minted))
    call.update(overrides)
    return outcome_after_read(row, **call)


def test_a_review_row_that_is_not_there_exits_two_and_resolves_nothing():
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    code, message = _call(None, res, appr, minted)
    assert code == 2 and "no review row 7" in message
    assert res.record(7, T0, "reviewer-2") is True    # nothing was resolved on the way out
    assert minted == []


def test_an_approval_whose_row_cannot_bind_refuses_before_the_resolution_ever_runs():
    """The mutant the review planted: move this refusal below the resolve call and the row is
    spent for good on a token bound to nothing. The row staying resolvable is that mutant's red."""
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    code, message = _call(({"recipient_domain": "example.test"},), res, appr, minted)
    assert code == 2 and "blocked_body" in message
    # The row is still resolvable, which is only true if nothing resolved it. That state is the
    # property; the empty mint list below is corroboration, not the assertion doing the work.
    assert res.record(7, T0, "reviewer-2") is True
    assert minted == []


def test_a_handoff_stored_as_text_binds_exactly_as_one_stored_as_jsonb():
    """psycopg hands back a dict for JSONB and a string for a text column, and the CLI's parse
    branch is the difference. Both paths are driven, and both must bind the same body."""
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    dump = _handoff_dump()
    for row_id, row in ((1, (dump,)), (2, (json.dumps(dump),))):
        code, _ = _call(row, res, appr, minted, row_id=row_id)
        assert code == 0
    assert [t.body_digest for t in minted] == [body_digest_of("The round is $9M.")] * 2
    assert [t.recipient_domain for t in minted] == ["example.test"] * 2


def test_an_approving_row_resolves_mints_and_hands_the_operator_the_token():
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    code, message = _call((_handoff_dump(),), res, appr, minted)
    assert code == 0
    t = minted[0]
    assert t is not None and t.token in message and "reviewer-1" in message
    assert appr.get_token(t.token) == t
    assert (t.idempotency_key, t.tool) == ("k-7", "mcp__retinue__send_message")
    assert t.body_digest == body_digest_of("The round is $9M.")
    assert t.recipient_domain == "example.test"
    assert res.record(7, T0, "reviewer-2") is False   # and the row is now resolved


def test_a_rejection_needs_no_binding_flags_resolves_the_row_and_mints_nothing():
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    code, message = _call((_handoff_dump(),), res, appr, minted, row_id=9, approve=False,
                          key=None, tool=None)
    assert code == 0 and "no token minted" in message
    assert minted == [None]
    assert res.record(9, T0, "reviewer-2") is False   # the rejection did resolve the row


def test_an_approval_of_a_row_someone_else_resolved_first_exits_one():
    res, appr, minted = MemoryResolutionLog(), MemoryApprovalStore(), []
    assert res.record(7, T0, "reviewer-2") is True    # somebody got there first
    code, message = _call((_handoff_dump(),), res, appr, minted)
    assert code == 1 and "no token minted" in message
    assert minted == [None]


def _dsn_or_skip() -> str:
    """The DSN, or the skip-and-fail posture this module opens by declaring.

    One copy, called by everything below. It was written out twice, and a third caller arrived with
    the transaction tests: a posture stated in the module docstring and re-implemented per helper is
    one edit away from a lane that quietly stops failing under RETINUE_PG_REQUIRED=1.
    """
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped")
    return dsn


def _pg_store():
    dsn = _dsn_or_skip()
    # `bootstrap` first, the same order tests/ledger/conftest.py and test_review_queue.py:144
    # already use. This file collects BEFORE both of them, so on a database that has never seen
    # the two new tables the PG test below would red on an undefined relation rather than on the
    # contract it is written to check, and it would do so on correct adapter code. Running the
    # idempotent schema here is what makes "runs green with a DSN" true rather than aspirational.
    from retinue.ledger.postgres import bootstrap
    from retinue.boundary.approvals import PgApprovalStore
    bootstrap(dsn)
    return PgApprovalStore(dsn)


def _pg_conn():
    """A raw connection, carrying the same skip, fail and bootstrap sequence as `_pg_store`.

    psycopg is imported inside, not at module scope, for the reason the module under test imports
    it inside `_conn`: the keyless lane never pays for the DSN lane's dependency.
    """
    dsn = _dsn_or_skip()
    import psycopg
    from retinue.ledger.postgres import bootstrap
    bootstrap(dsn)
    return psycopg.connect(dsn)


def test_pg_half_honours_the_same_contract():
    s = _pg_store()
    tok = os.urandom(16).hex()
    t = token(tok=tok, key=f"k-{tok[:8]}")
    assert s.put_token(t) is True
    assert s.put_token(t) is False
    got = s.get_token(tok)
    assert got is not None, "the mint row did not read back at all"
    # ALL EIGHT FIELDS, not one. `ApprovalToken(*row)` binds by POSITION, so a swap of `tool` and
    # `recipient_domain` in SELECT_TOKEN round-trips through a single-field check in silence, and
    # those two are exactly the fields the spec's 2026-08-30 amendment added to close an
    # authorization hole. Frozen dataclass equality compares the whole row in one assertion.
    # Aware datetimes compare as INSTANTS, so a session timezone other than UTC still matches,
    # which is the same reasoning test_review_queue.py:162 already rests on.
    assert got == t
    assert s.consume(tok, T0) is True
    assert s.consume(tok, T0) is False


def test_the_approvals_table_refuses_update_delete_and_truncate():
    """The append-only claim, asserted where a future edit can redden it.

    The DDL's four triggers were probed by hand once and the transcript lived in a report, so a
    dropped `CREATE TRIGGER` line reddened nothing in the tree. This is that probe as a test,
    mirroring `tests/ledger/test_postgres_enforcement.py:18-32` for the two tables this module
    owns. It lives here rather than beside that file because the tables belong to the boundary,
    the same way `test_review_queue.py` keeps the durable queue's own DSN test in this directory.

    The seed is committed by its own connection before the probes open theirs, which answers the
    hazard the mirrored test answers with an explicit commit: the UPDATE's raise rolls its
    transaction back, an uncommitted seed would vanish with it, and the DELETE below would then
    fire a row-level trigger on zero rows and raise nothing at all.

    THE MESSAGE IS ASSERTED, not only the exception class. Both tables lean on one shared trigger
    function, so a trigger wired to the wrong table would still raise and still pass a
    class-only check. Naming the table is what makes this test about THIS table.
    """
    import psycopg
    s = _pg_store()
    tok = os.urandom(16).hex()
    assert s.put_token(token(tok=tok, key=f"k-{tok[:8]}")) is True
    with _pg_conn() as c:
        with pytest.raises(psycopg.errors.RaiseException, match="approvals is append-only"):
            c.execute("UPDATE approvals SET tool='x' WHERE token=%s", (tok,))
        c.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="approvals is append-only"):
            c.execute("DELETE FROM approvals WHERE token=%s", (tok,))
        c.rollback()
        # Statement-level, and the reason it is a separate trigger: a row-level trigger CANNOT
        # fire on TRUNCATE, so without this one the table is emptied in silence.
        with pytest.raises(psycopg.errors.RaiseException, match="approvals is append-only"):
            c.execute("TRUNCATE approvals")
        c.rollback()


def test_the_consumption_table_refuses_update_delete_and_truncate():
    """The other half of the same claim. Single use rests on this row being unrewritable."""
    import psycopg
    s = _pg_store()
    tok = os.urandom(16).hex()
    assert s.consume(tok, T0) is True
    with _pg_conn() as c:
        with pytest.raises(psycopg.errors.RaiseException,
                           match="approval_consumptions is append-only"):
            c.execute("UPDATE approval_consumptions SET consumed_at=%s WHERE token=%s", (T0, tok))
        c.rollback()
        with pytest.raises(psycopg.errors.RaiseException,
                           match="approval_consumptions is append-only"):
            c.execute("DELETE FROM approval_consumptions WHERE token=%s", (tok,))
        c.rollback()
        with pytest.raises(psycopg.errors.RaiseException,
                           match="approval_consumptions is append-only"):
            c.execute("TRUNCATE approval_consumptions")
        c.rollback()


# --- The one transaction: the mint is atomic with the resolution (spec section 2). -------------
#
# These run only under a DSN, and that is the point rather than a limitation. What they assert is a
# ROLLBACK, and a rollback is a property of a database session: the memory lane has no transaction
# to leave half-finished, so there is nothing here a keyless run could stand in for. The SQL they
# exercise is `RESOLVE_ROW` and `INSERT_TOKEN`, held against schema.sql by the keyless double-entry
# gate above, so the two halves cover the statements' text and their behaviour separately.


def _seed_review_row(conn, *, body="The round is $9M.") -> int:
    """One unresolved review row, committed, with its generated id.

    Committed by its own connection before a probe opens one, the reasoning
    `test_the_approvals_table_refuses_update_delete_and_truncate` already carries: a rollback under
    test would otherwise take the seed with it, and the assertions would then read an ABSENT row
    where they mean to read an UNRESOLVED one - which is a different fact and a passing test.
    """
    from psycopg.types.json import Jsonb
    handoff = {"reason_category": "boundary:approval_unverified", "detector_outage": "held",
               "violating_span": "", "blocked_body": body, "recipient_domain": "example.test",
               "recipient_jurisdiction": "US", "cited_field_values": {}, "thread_excerpt": "",
               "proposed_alternative": None, "refinement_rounds": 0}
    row = conn.execute("INSERT INTO review_queue (queue_name, handoff, enqueued_at) "
                       "VALUES (%s,%s,%s) RETURNING id",
                       ("human-review", Jsonb(handoff), T0)).fetchone()[0]
    conn.commit()
    return row


def _row_state(conn, row_id: int):
    return conn.execute("SELECT resolved_at, approved_by FROM review_queue WHERE id = %s",
                        (row_id,)).fetchone()


def _tokens_for(conn, tok: str):
    return conn.execute("SELECT token, resolution_id FROM approvals WHERE token = %s",
                        (tok,)).fetchall()


def test_the_resolution_and_its_mint_survive_a_reconnect_as_one_durable_fact():
    """The plain round-trip: resolve through one transaction, then read both halves back cold.

    Read back through a SEPARATE connection, and through `PgApprovalStore` rather than through the
    connection that wrote it, because what is asserted is that the transaction COMMITTED rather
    than that a cursor remembers what it did.
    """
    from retinue.boundary.approvals import PgApprovalStore
    from retinue.boundary.resolve import resolve_pg

    dsn = _dsn_or_skip()
    with _pg_conn() as seed:
        row_id = _seed_review_row(seed)
    tok = os.urandom(16).hex()
    minted = resolve_pg(dsn, row_id=row_id, verdict="approve", at=T0, approved_by="reviewer-1",
                        window=timedelta(hours=24), key=f"k-{tok[:8]}", body="The round is $9M.",
                        tool="mcp__retinue__send_message", recipient_domain="example.test",
                        token_id=tok)
    assert minted is not None

    store = PgApprovalStore(dsn)
    assert store.get_token(tok) == minted        # all eight fields, by frozen-dataclass equality
    assert store.consume(tok, T0) is True
    assert store.consume(tok, T0) is False       # single use, across connections
    with _pg_conn() as check:
        resolved_at, approved_by = _row_state(check, row_id)
        assert resolved_at is not None and approved_by == "reviewer-1"


def test_a_mint_that_cannot_be_written_leaves_the_resolution_unwritten_too():
    """THE ATOMICITY PROPERTY, and the whole reason step 5 exists: neither write, or both.

    The forced failure is a caller-supplied token id that is already minted. In the shared
    `resolve` that collision is refused by a read BEFORE the resolution, because that verb holds
    two connections and cannot take the row back once it is written. `resolve_pg` inverts the order
    deliberately: it writes the resolution, discovers the collision from `INSERT_TOKEN`'s own
    rowcount, and RAISES - and the transaction takes the resolution back out with it. Same
    observable contract, reached by the transaction rather than by the pre-read, which is what
    makes this test an exercise of the transaction instead of an exercise of the guard.

    Measured red before it was believed: an implementation committing between the UPDATE and the
    INSERT leaves the second row resolved and tokenless, which is exactly the unresolvable row spec
    section 2 forbids, and this test reddens on the `_row_state` assertion below.
    """
    from retinue.boundary.resolve import resolve_pg

    dsn = _dsn_or_skip()
    with _pg_conn() as seed:
        first, second = _seed_review_row(seed), _seed_review_row(seed)
    tok = os.urandom(16).hex()
    common = dict(verdict="approve", at=T0, window=timedelta(hours=24), key=f"k-{tok[:8]}",
                  body="The round is $9M.", tool="mcp__retinue__send_message",
                  recipient_domain="example.test")
    taken = resolve_pg(dsn, row_id=first, approved_by="reviewer-1", token_id=tok, **common)
    assert taken is not None

    with pytest.raises(ValueError):
        resolve_pg(dsn, row_id=second, approved_by="reviewer-2", token_id=tok, **common)

    with _pg_conn() as check:
        # NEITHER write survived. The row is the half a committing implementation would leave.
        assert _row_state(check, second) == (None, None)
        # And the token still belongs to the row that legitimately minted it, unrewritten.
        assert _tokens_for(check, tok) == [(tok, first)]
    # The row survived the refusal, which is the finding: a corrected retry still resolves it.
    again = resolve_pg(dsn, row_id=second, approved_by="reviewer-2",
                       token_id=os.urandom(16).hex(), **common)
    assert again is not None and again.resolution_id == second


def test_the_two_verbs_mint_the_same_bindings_from_the_same_material():
    """Double entry between the memory verb and the transactional one, which are two spellings of
    one mint and can drift apart in silence.

    `resolve_pg` builds its `ApprovalToken` itself rather than calling `resolve`, because the ORDER
    of its steps is the property it exists for. That leaves two constructions of one record, and a
    field dropped or crossed in either is invisible to every test driving only one of them. The
    token id and the resolution id are held equal by construction here, since those are the two
    fields that legitimately differ between any two mints.
    """
    from retinue.boundary.resolve import resolve_pg

    dsn = _dsn_or_skip()
    with _pg_conn() as seed:
        row_id = _seed_review_row(seed)
    tok = os.urandom(16).hex()
    material = dict(verdict="approve", at=T0, approved_by="reviewer-1",
                    window=timedelta(hours=24), key=f"k-{tok[:8]}", body="The round is $9M.",
                    tool="mcp__retinue__send_message", recipient_domain="example.test")
    durable = resolve_pg(dsn, row_id=row_id, token_id=tok, **material)
    in_memory = resolve(row_id=row_id, token_id=tok, resolutions=MemoryResolutionLog(),
                        approvals=MemoryApprovalStore(), **material)
    assert durable is not None and in_memory is not None
    assert durable == in_memory


def test_a_rejection_through_the_transaction_resolves_the_row_and_mints_nothing():
    """The verdict arm, in the lane where a resolution is a committed row rather than a dict entry.

    Without it `resolve_pg` could answer None for a rejection having written nothing at all, and
    every assertion above would still hold - while a row it left unresolved could be approved
    afterwards by somebody else, which is the whole point of recording a rejection.
    """
    from retinue.boundary.resolve import resolve_pg

    dsn = _dsn_or_skip()
    with _pg_conn() as seed:
        row_id = _seed_review_row(seed)
    assert resolve_pg(dsn, row_id=row_id, verdict="reject", at=T0, approved_by="reviewer-1",
                      window=timedelta(hours=24), key="", body="", tool="",
                      recipient_domain="") is None
    with _pg_conn() as check:
        resolved_at, approved_by = _row_state(check, row_id)
        assert resolved_at is not None and approved_by == "reviewer-1"


def test_the_loser_of_a_double_resolution_mints_nothing_in_the_durable_lane():
    """First-writer-wins, held where it is a real UPDATE against a real row.

    `RESOLVE_ROW` carries `AND resolved_at IS NULL`, and the keyless gate pins that TEXT. What no
    keyless run can show is the clause doing anything, because nothing keyless executes it. This is
    the arm where a second resolver meets a row already resolved and comes away with nothing.
    """
    from retinue.boundary.resolve import resolve_pg

    dsn = _dsn_or_skip()
    with _pg_conn() as seed:
        row_id = _seed_review_row(seed)
    common = dict(row_id=row_id, verdict="approve", at=T0, window=timedelta(hours=24),
                  key="k-double", body="The round is $9M.", tool="mcp__retinue__send_message",
                  recipient_domain="example.test")
    assert resolve_pg(dsn, approved_by="reviewer-1", token_id=os.urandom(16).hex(),
                      **common) is not None
    loser = os.urandom(16).hex()
    assert resolve_pg(dsn, approved_by="reviewer-2", token_id=loser, **common) is None
    with _pg_conn() as check:
        assert _tokens_for(check, loser) == []            # the loser minted nothing at all
        assert _row_state(check, row_id)[1] == "reviewer-1"
