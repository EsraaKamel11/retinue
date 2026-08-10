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
