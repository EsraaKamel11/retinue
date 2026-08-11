-- schema.sql: idempotent, and the whole migration story FOR P1 - creates, plus two DROP TRIGGER
-- statements that keep their creates re-runnable (CREATE TRIGGER has no IF NOT EXISTS). The one
-- exception is DROP INDEX IF EXISTS below: it is the file's only destructive migration action,
-- retiring an index an earlier revision created, where every other statement reaches an existing
-- database only by adding what it finds missing. A column added later would need its own ALTER,
-- since CREATE TABLE IF NOT EXISTS no-ops on an existing table and would report success while
-- the new column never appeared.
CREATE TABLE IF NOT EXISTS touchpoints (
    idempotency_key TEXT PRIMARY KEY,
    investor_id     TEXT NOT NULL,
    mandate_id      TEXT,
    kind            TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL,
    delivery_status TEXT CHECK (delivery_status IN ('CONFIRMED','FAILED','UNVERIFIABLE')),
    seq             BIGINT GENERATED ALWAYS AS IDENTITY
);
-- Named so a plan test can match it (spec 2.2), and ordered to serve the query the adapter
-- ACTUALLY issues: `WHERE investor_id=%s ORDER BY seq`. An (investor_id, occurred_at) index
-- serves the equality and then leaves a Sort, so the second column would buy that path nothing.
DROP INDEX IF EXISTS idx_touchpoints_investor_ts;
CREATE INDEX IF NOT EXISTS idx_touchpoints_investor_seq
    ON touchpoints (investor_id, seq);
-- Append-only: no UPDATE, no DELETE, enforced in the database not in prose.
CREATE OR REPLACE FUNCTION touchpoints_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'touchpoints is append-only'; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touchpoints_append_only ON touchpoints;
CREATE TRIGGER trg_touchpoints_append_only
    BEFORE UPDATE OR DELETE ON touchpoints
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
-- A row-level trigger CANNOT fire on TRUNCATE, so without this one `TRUNCATE touchpoints`
-- quietly empties an append-only ledger. Statement-level, because TRUNCATE has no rows.
DROP TRIGGER IF EXISTS trg_touchpoints_no_truncate ON touchpoints;
CREATE TRIGGER trg_touchpoints_no_truncate
    BEFORE TRUNCATE ON touchpoints
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
-- Outcomes resolve over weeks: occurred_at and observed_at diverge structurally, and a
-- later-resolving outcome UPDATES this row - never the touchpoint (spec 5.1). So this table
-- carries NO append-only trigger where touchpoints above carries one, and the absence is the
-- decision rather than the oversight it could look like: that trigger here would forbid the very
-- UPDATE the design requires, forcing a second row per revision and making outcome_key a lie.
-- The ledger stays immutable; the outcome stays correctable. The signal list below is the same
-- fact as OUTCOME_SIGNALS in ledger/outcomes.py, and a test holds the two spellings equal.
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_key TEXT PRIMARY KEY,
    investor_id TEXT NOT NULL,
    mandate_id  TEXT NOT NULL,
    signal      TEXT NOT NULL CHECK (signal IN ('replied','meeting_booked','check_written')),
    occurred_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL
);
-- The DURABLE half of escalation (spec 8). The imported in-process queues state their own limit:
-- going out of scope takes the escalations with them. This table is what survives a process.
-- Explicitly not a graph-checkpointer. `resolved_at` is declared and nothing writes it yet: the
-- enqueue is what this task makes durable, and a column added later would need its own ALTER
-- (see this file's opening note), so it is cheaper to declare nullable now than to migrate later.
CREATE TABLE IF NOT EXISTS review_queue (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_name  TEXT NOT NULL,
    handoff     JSONB NOT NULL,
    enqueued_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);
