"""The approval store contract, both halves. The Postgres tests skip without a DSN and FAIL
under RETINUE_PG_REQUIRED=1, the same posture test_review_queue.py:136-140 establishes."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from retinue.boundary.approvals import (ApprovalToken, MemoryApprovalStore, body_digest_of)

T0 = datetime(2030, 1, 2, tzinfo=timezone.utc)


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
