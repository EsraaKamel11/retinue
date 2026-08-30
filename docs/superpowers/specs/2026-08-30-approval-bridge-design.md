# The approval bridge: mint, validation, consumption

Design for the Designed row this repository's README carries first (proposal section 15.1). The
bridge closes the seam where the two lanes meet: today the imported presence check refuses every
composed send on `act:no_approval_token` because nothing mints one, and the standing perverse
incentive is that any caller could pass a non-None string and reduce "a human approved this act"
to a type check. After this build, a token exists only as the trace of a human resolution, binds
the exact act and the exact bytes that resolution approved, is spent by an append that can be
won exactly once, and is verified at the boundary before the imported gate ever sees it.

Scope, settled at brainstorm and confirmed by an advisor round on 2026-08-30 (the round ran
after this spec's first commit; this amendment re-anchors the attribution to the call that
actually happened): the mint-validate-consume path
with a human resolution as its trigger. The SDK-hook linkage - whether the hook's "ask" and the
chokepoint's token can be one event - has never been observed in a run and is NAMED, NOT BUILT:
no part of this design may depend on it, and no elegance argument mid-build reopens it. Its
entry condition is an observation capture, a separate spend, another day.

## 1. The token

A row, never a bare string:

- `token` - opaque random identifier (32 hex chars from a CSPRNG).
- `idempotency_key` - the act it approves; the same key `attempt_send` is called with.
- `body_digest` - sha256 over the draft body's UTF-8 bytes; the content it approves.
- `resolution_id` - the review-queue row whose resolution minted it; provenance, so every token
  answers "which human act created you".
- `minted_at`, `expires_at` - both datetimes arrive as arguments; the window is the resolver's
  parameter and nothing here reads a clock.

A token is evidence that one human resolution approved one body for one act. Anything weaker -
presence, format, freshness alone - does not validate.

## 2. The mint

`review_queue.resolved_at` gains its first writer. A boundary function
`resolve(row_id, verdict, at, *, window, store)` writes the resolution; an approving verdict
mints the token in the same call, because the mint IS the resolution event - there is no second
human act to attest. Rejecting verdicts write `resolved_at` and mint nothing.

Tokens live in their own table, `approval_tokens`, not as columns on the review row: a
resolution mints zero or one token, and the token's lifecycle is the new store's own contract.
The `resolved_at` write is this design's SINGLE deliberate update, named as such: the queue's
enqueue stays insert-only, and the resolution is a test-and-set
(`UPDATE ... SET resolved_at = %s ... WHERE id = %s AND resolved_at IS NULL`, `rowcount == 1`),
so a double resolution is first-writer-wins by construction and the loser mints nothing. The
mint is atomic with the resolution: one transaction in Postgres, one operation in memory, so no
crash can leave a resolution without its token or a token without its resolution. Two halves, one contract test suite, the
`DurableQueues` pattern: an in-memory store the default lane drives keyless and offline, a
Postgres store the DSN lane drives, identical semantics pinned by shared tests.

## 3. Consumption: an append that wins or loses

Not an UPDATE, and not a flag on the token row. Consumption is the house primitive reused:
`INSERT INTO approval_consumptions (token, consumed_at) ... ON CONFLICT DO NOTHING`, and the
boolean the store answers with is the atomic, token-global test-and-set - `rowcount == 1` in
Postgres, first-insert set membership in memory. Validity is the conjunction: the mint row
exists, it binds this idempotency key AND this body digest, `at < expires_at`, and the consume
append won. Two callers racing the same token: one wins the insert and proceeds, one reads
False and is refused. The TOKEN stores are append-only throughout - mint rows and consumption
rows are only ever inserted; the one update in this design is the resolution test-and-set named
in section 2, and nothing else updates anything.

## 4. Validation: site, class, and the burn rule

A boundary pre-check inside `attempt_send`, refusing with the boundary-level class
`boundary:approval_unverified` - a sibling of `projection_unavailable`,
`delivery_unverifiable` and `send_unrecorded`, and deliberately never a policy
`ViolationClass`: no policy predicate ran, so the refusal may not masquerade as a policy
judgment.

Position in the module's load-bearing order: between the projection pre-check and
`guarded_call`. After the projection pre-check, because a missing context is the more
fundamental absence and must keep denying as `projection_unavailable`, never masked by a token
refusal. Before `guarded_call`, because the boundary verifies binding, expiry and consumption
BEFORE the imported gate sees the token, so the imported presence check keeps holding exactly
what it has always held and nothing upstream weakens it.

Consumption happens at this same site, before the gate decides. Consequence, argued as a
feature: if the imported gate then denies the act, the token is spent. A human approved one
attempt of one body; an act the gate refused earns a fresh look and a fresh resolution, not a
free retry riding an old approval. The same rule covers the crash path: a token consumed by a
process that died before its act is a spent token, visible as a consumption row with no sent
touchpoint, and recovery is a fresh resolution over the same draft, never a resurrection. A send without a token, or with a token that fails any leg
of validity, denies exactly as today - the existing guarantee is unchanged and a test pins it.

## 5. The first caller that is not a test

A script in the P5 shape. It enqueues the captured ask payload's handoff
(`fixtures/payloads/captured_ask.json`) into the durable review queue; the operator resolves it
through a small CLI (`python -m retinue.boundary.resolve <row> --approve`, timestamps and
window as arguments); the script then drives `attempt_send` with the minted token through the
real path - terminal guard, validation, projection pre-check, token validation and consumption,
`guarded_call`, the sent touchpoint, the record check. The P4 demo's decision that the tool
body performs no outward act is preserved with its reason: the demo lane's transport is inert
by design, and what the bridge proves is the path, not a network send. This script is the
caller that flips the row.

## 6. Evidence bar

Adopted from the Phase 0 brief verbatim; the row flips on these and never on effort:

- a bridged approval passes end to end, from resolution through mint to an allowed send;
- a token minted for a different draft, or a different idempotency key, is refused at the
  boundary pre-check;
- a reused token is refused, and the refusal survives two callers racing for it;
- an expired token is refused;
- an absent token still denies exactly as today;
- a double resolution mints exactly one token, the second resolver reading first-writer-wins;
- the captured ask payload drives the full path;
- Postgres-lane tests for the mint's durability, in the durable queue's pattern.

Documents that move only when those are green with the real caller: the README's
Designed-vs-Built row, the "no agent has ever driven the chokepoint" limit and the P3 clause
that states it, the roadmap's first entry, and proposal sections 15.1 and 17, each dated in the
house style - what the sentence said, what ran, and when. Nothing moves on code existing.

## 7. Constraints carried whole

No policy code: every deciding predicate stays imported, `tools/fleet_audit.py` holds that as
AST rules, and the validator is boundary wiring that must read as such. Determinism: the
default lane needs no service, no network, no key. The clock is an argument everywhere.
Failure past an irreversible act follows the module's own reasoning - a denial, never an
exception that abandons the record. Watched-red TDD with the repository's measured-red
practice where a natural red is impossible. Gates before every commit, exit codes unpiped.

## 8. Named absences, so they are not scope

The SDK-hook linkage (above; observation capture first, ever). The sibling console's approve
action becoming a live `resolve()` caller - the operator seat gaining the real mint - which is
that repository's phase 3 and gets its own spec against this contract when its time comes.
