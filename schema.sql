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
--
-- ONE function, serving every append-only table here, so the message names the table it fired for
-- rather than the table it was first written for. It said 'touchpoints is append-only' on all six
-- triggers until the approval tables arrived and an operator tripping the guard on `approvals` was
-- handed the name of a table they had not touched. TG_TABLE_NAME is the trigger's own view of what
-- it is protecting, so this stays one function and gains no per-table copy. The function's NAME
-- still says touchpoints and a PL/pgSQL context line still shows it; renaming it would need
-- DROP ... CASCADE and six trigger recreations in a file that advertises exactly one destructive
-- statement, which is a worse trade than the residual it would buy.
CREATE OR REPLACE FUNCTION touchpoints_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END;
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
-- Explicitly not a graph-checkpointer. `resolved_at` was declared here before anything wrote it:
-- the enqueue was what that task made durable, and a column added later would need its own ALTER
-- (see this file's opening note), so declaring it nullable up front was cheaper than migrating.
-- Corrected 2026-08-30, the day it gained its writer: `RESOLVE_ROW` in boundary/approvals.py sets
-- it, and that statement is a test-and-set matching only a row still holding NULL here, so the
-- second reviewer of one row writes nothing. The reviewer identity the note below describes is set
-- in the same statement, and it is the later column this note argued about, arriving by exactly the
-- route prescribed: the ALTER immediately after this table. The column is deliberately not spelled
-- in this comment - the ALTER-guard in tests/boundary/test_approvals.py deletes the ALTER and its
-- plant check sweeps the whole schema text, comments included, so a comment carrying the name
-- reddens that check loudly (measured); the declared-column parser itself reads only the CREATE
-- block and the ALTER, so the guard's real assertion is untouched either way.
CREATE TABLE IF NOT EXISTS review_queue (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_name  TEXT NOT NULL,
    handoff     JSONB NOT NULL,
    enqueued_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);
-- The reviewer's identity on the resolution, which is the provenance a token's `resolution_id`
-- reaches for (spec section 1, amended 2026-08-30). Added by ALTER because CREATE TABLE IF NOT
-- EXISTS no-ops on the existing table above and would report success while the column never
-- appeared, which is the route this file's opening note prescribes.
ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS approved_by TEXT;
-- The approval bridge's own two tables (spec: 2026-08-30-approval-bridge-design.md). Both are
-- append-only with the same trigger pair the touchpoints table carries: a mint row and a
-- consumption row are only ever inserted, and single use is the primary key refusing a second
-- consumption.
CREATE TABLE IF NOT EXISTS approvals (
    token            TEXT PRIMARY KEY,
    idempotency_key  TEXT NOT NULL,
    body_digest      TEXT NOT NULL,
    tool             TEXT NOT NULL,
    recipient_domain TEXT NOT NULL,
    resolution_id    BIGINT NOT NULL,
    minted_at        TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL
);
DROP TRIGGER IF EXISTS trg_approvals_append_only ON approvals;
CREATE TRIGGER trg_approvals_append_only
    BEFORE UPDATE OR DELETE ON approvals
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
DROP TRIGGER IF EXISTS trg_approvals_no_truncate ON approvals;
CREATE TRIGGER trg_approvals_no_truncate
    BEFORE TRUNCATE ON approvals
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
CREATE TABLE IF NOT EXISTS approval_consumptions (
    token       TEXT PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL
);
DROP TRIGGER IF EXISTS trg_approval_consumptions_append_only ON approval_consumptions;
CREATE TRIGGER trg_approval_consumptions_append_only
    BEFORE UPDATE OR DELETE ON approval_consumptions
    FOR EACH ROW EXECUTE FUNCTION touchpoints_append_only();
DROP TRIGGER IF EXISTS trg_approval_consumptions_no_truncate ON approval_consumptions;
CREATE TRIGGER trg_approval_consumptions_no_truncate
    BEFORE TRUNCATE ON approval_consumptions
    FOR EACH STATEMENT EXECUTE FUNCTION touchpoints_append_only();
