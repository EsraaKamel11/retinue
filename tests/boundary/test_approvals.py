"""The approval store contract, both halves. The Postgres tests skip without a DSN and FAIL
under RETINUE_PG_REQUIRED=1, the same posture test_review_queue.py:136-140 establishes."""
import dataclasses
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, body_digest_of)

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
        findings.append(f"select_order: the SELECT reads {columns} and ApprovalToken(*row) "
                        f"binds them to {list(fields)}")
    block = _table_block(schema_text, table)
    if block is None:
        return findings + [f"table_undeclared: schema.sql declares no table named {table!r}"]
    undeclared = sorted(set(columns) - set(_declared(block)))
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


def _pg_store():
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped")
    # `bootstrap` first, the same order tests/ledger/conftest.py and test_review_queue.py:144
    # already use. This file collects BEFORE both of them, so on a database that has never seen
    # the two new tables the PG test below would red on an undefined relation rather than on the
    # contract it is written to check, and it would do so on correct adapter code. Running the
    # idempotent schema here is what makes "runs green with a DSN" true rather than aspirational.
    from retinue.ledger.postgres import bootstrap
    from retinue.boundary.approvals import PgApprovalStore
    bootstrap(dsn)
    return PgApprovalStore(dsn)


def test_pg_half_honours_the_same_contract():
    s = _pg_store()
    tok = os.urandom(16).hex()
    t = token(tok=tok, key=f"k-{tok[:8]}")
    assert s.put_token(t) is True
    assert s.put_token(t) is False
    got = s.get_token(tok)
    assert got is not None and got.idempotency_key == t.idempotency_key
    assert s.consume(tok, T0) is True
    assert s.consume(tok, T0) is False
