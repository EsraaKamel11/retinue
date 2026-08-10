import os, uuid
import pytest
from retinue.ledger.store import InMemoryStore

def _pg_store():
    dsn = os.environ.get("RETINUE_PG_DSN")
    if not dsn:
        if os.environ.get("RETINUE_PG_REQUIRED") == "1":
            pytest.fail("RETINUE_PG_REQUIRED=1 but RETINUE_PG_DSN is unset - the lane may not silently skip")
        pytest.skip("RETINUE_PG_DSN unset: Postgres lane skipped. Run `docker compose up -d --wait` "
                    "(--wait consumes the healthcheck) and export the DSN in docker-compose.yml's "
                    "trailing comment, or point at any Postgres 16.")
    from retinue.ledger.postgres import PostgresStore, bootstrap
    bootstrap(dsn)
    return PostgresStore(dsn)

@pytest.fixture(params=["memory", "postgres"])
def store(request):
    return InMemoryStore() if request.param == "memory" else _pg_store()

@pytest.fixture()
def ns():
    """Per-test namespace. The Postgres table is append-only BY TRIGGER - it can never be
    truncated between runs, so isolation comes from unique keys and investor ids, not cleanup."""
    return uuid.uuid4().hex[:12]
