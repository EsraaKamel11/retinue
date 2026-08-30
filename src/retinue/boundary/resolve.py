"""Operator CLI for the DSN lane: python -m retinue.boundary.resolve <row-id> --approve ...

Reads the review row for the binding material that row actually carries, refuses an approval it
could not bind, and otherwise resolves through `resolve_pg` below - the same verb with the same
arguments the memory lane calls in-process, wrapped in one transaction. The memory lane never uses
this module.

**What a review row can and cannot supply, because it decided this file's shape.** The durable
row stores a `Handoff` dump. That model carries `blocked_body` and `recipient_domain`, and it
carries neither an idempotency key nor a tool name: the key is an argument the caller hands
`attempt_send`, and the tool name is the gate's rather than the handoff's. So two of the token's
four bindings come from the row and two are the operator's to supply, `--key` and `--tool`.
Reading `body` and `tool` off the dump instead would return "" from every row ever written and
mint a token bound to nothing.

**The refusal precedes the resolution, and that order is the point.** `record` is
first-writer-wins, so an approve that resolved the row and only then discovered it could not bind
would leave a row nobody can ever resolve again and a token nobody can ever spend, recoverable
only by a fresh draft. Both binding checks therefore run before `resolve` is called, and the
first of them runs before the connection is opened. A rejection binds nothing and is held to
neither: an operator rejecting a draft should not need the act's idempotency key. That order is
now held by tests rather than by this paragraph: everything after the read lives in
`outcome_after_read`, a function of the row and a resolve callable, which the keyless lane drives
end to end.

**One transaction, and the paragraph that stood here said otherwise.** Spec section 2 asks the
mint to be atomic with the resolution, and until Task 4 this module called `PgResolutionLog.record`
and `PgApprovalStore.put_token`, which open a connection each and commit separately: a crash
between them left a resolved row with no token, the same unresolvable row named above. `resolve_pg`
below is that wrapper - one connection, one transaction over the resolution and the insert, so
neither survives without the other - and `main` calls it. The claim is a measured one rather than a
described one: `test_a_mint_that_cannot_be_written_leaves_the_resolution_unwritten_too` forces the
insert to fail after the update has succeeded and reads both tables back, and it was watched red
against an implementation that committed between the two.

**The read is still its own connection, and that is not the atomicity being claimed.** `main`
fetches the review row on one connection and resolves on another. What section 2 requires is that
the MINT be atomic with the RESOLUTION, which are the two writes; a stale read costs the operator a
refusal or a first-writer-wins None, and never a half-written pair.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta

from retinue.boundary.approvals import (INSERT_TOKEN, RESOLVE_ROW, ApprovalToken, body_digest_of)

#: Hoisted for the reason every statement in approvals.py is hoisted: it runs in the DSN lane and
#: nowhere else, so the keyless double-entry gate in tests/boundary/test_approvals.py reads the
#: exact text this module issues rather than a retyped copy that could agree with schema.sql while
#: this file does not.
SELECT_HANDOFF = "SELECT handoff FROM review_queue WHERE id = %s"

#: Where each of the token's four bindings comes from, in words an operator can act on. A refusal
#: builds its message from these, so nothing has to guess which half of the binding is missing.
BINDING_SOURCES = {"key": "--key", "tool": "--tool", "body": "the handoff's blocked_body",
                   "recipient_domain": "the handoff's recipient_domain"}


def binding_material(handoff: dict, *, key: str | None, tool: str | None,
                     ) -> tuple[dict[str, str], list[str]]:
    """The token's four bindings, and the names of the sources that supplied nothing.

    `blocked_body`, never `body`: see the module docstring for why that is the whole difference
    between a token bound to the approved draft and a token bound to the empty string.
    """
    binding = {"key": key or "", "body": handoff.get("blocked_body") or "", "tool": tool or "",
               "recipient_domain": handoff.get("recipient_domain") or ""}
    missing = [BINDING_SOURCES[n] for n in BINDING_SOURCES if not binding[n]]
    return binding, missing


def outcome_after_read(row, *, row_id: int, approve: bool, by: str, at: datetime,
                       window: timedelta, key: str | None, tool: str | None,
                       resolve_fn) -> tuple[int, str]:
    """Everything the CLI decides once the row is in hand: an exit code and the line to print.

    A function of the ROW rather than of a connection, so the keyless lane drives all of it - the
    missing row, the parse of a text-typed column, the refusal that must precede the resolution,
    and both post-resolve exit codes. `main` keeps the fetch and nothing else. It is a function
    because the ordering below was held by inspection alone: a mutant moving the refusal BELOW
    `resolve_fn`, which is the row-destroying order this module exists to prevent, passed the
    entire suite.

    `resolve_fn` is the resolving verb with its destination already bound - `resolve_pg` with the
    DSN closed over, in `main` below, and a plain function in the keyless tests that drive this.
    Exit 2 is the refusal family, which is how the caller knows to print to stderr; exit 1 is an
    approval that minted nothing, which for an approving operator is a failure to get what they
    asked for.
    """
    if row is None:
        return 2, f"no review row {row_id}"
    # psycopg answers a dict for a JSONB column and a string for a text one. Both are rows this
    # command can be pointed at, so both parse here rather than in whichever lane finds out.
    handoff = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    binding, missing = binding_material(handoff, key=key, tool=tool)
    if approve and missing:
        return 2, (f"review row {row_id} supplies no {', '.join(missing)}, so approving it could "
                   "mint only a token bound to nothing; the row is left unresolved")
    token = resolve_fn(row_id=row_id, verdict="approve" if approve else "reject", at=at,
                       approved_by=by, window=window, key=binding["key"], body=binding["body"],
                       tool=binding["tool"], recipient_domain=binding["recipient_domain"])
    if token is None:
        return (1 if approve else 0,
                "resolved: no token minted (rejection, or the row was already resolved)")
    return 0, f"resolved by {by}; token {token.token} expires {token.expires_at.isoformat()}"


def resolve_pg(dsn: str, *, row_id: int, verdict: str, at: datetime, approved_by: str,
               window: timedelta, key: str, body: str, tool: str, recipient_domain: str,
               token_id: str | None = None) -> ApprovalToken | None:
    """`resolve` for the DSN lane: the resolution and its mint in ONE transaction (spec section 2).

    Same answers as the memory verb - a token, or None for a rejection and for the loser of a
    double resolution - and one difference in HOW the collision is refused, which is the whole
    reason this function exists rather than calling `resolve` with the two Pg stores.

    **The order is inverted on purpose, and the transaction is what permits it.** `resolve` checks
    for a colliding token id BEFORE it records the resolution, because it holds two connections
    that commit separately: discovering the collision afterwards would leave a row resolved,
    tokenless and unresolvable for good. Here the resolution and the insert are one atomic unit, so
    the check can come from `INSERT_TOKEN`'s own rowcount - which is the authoritative answer rather
    than a read that another writer can invalidate a moment later - and the raise takes the
    resolution back out with it. A pre-read here would be a second, weaker copy of a guarantee the
    database is already giving.

    **What the caller sees is therefore unchanged: a colliding id raises and writes nothing.** One
    contract difference is real and is named rather than left to be found. `resolve` runs its
    collision guard above the verdict check, so a REJECTION carrying an already-minted token id
    raises there; here a rejection never reaches the insert, so it resolves the row and answers
    None. No caller reaches it - `main` below supplies no token id, and a rejection has no token to
    collide - and the two verbs are held to the same bindings by
    `test_the_two_verbs_mint_the_same_bindings_from_the_same_material`.

    The two statements are the module-level constants `approvals.py` hoists, never respelled here:
    the keyless double-entry gate holds those against schema.sql, and a copy typed into this
    function would run SQL that gate has never read.
    """
    import psycopg
    # One connection, one transaction. psycopg's connection context manager commits on a clean
    # exit and ROLLS BACK on an exception, so every `raise` below un-writes the update above it.
    with psycopg.connect(dsn) as conn:
        if conn.execute(RESOLVE_ROW, (at, approved_by, row_id)).rowcount != 1:
            return None                      # somebody resolved this row first; nothing to mint
        if verdict != "approve":
            return None
        token = ApprovalToken(token=token_id or secrets.token_hex(16), idempotency_key=key,
                              body_digest=body_digest_of(body), tool=tool,
                              recipient_domain=recipient_domain, resolution_id=row_id,
                              minted_at=at, expires_at=at + window)
        minted = conn.execute(INSERT_TOKEN, (token.token, token.idempotency_key,
                                             token.body_digest, token.tool,
                                             token.recipient_domain, token.resolution_id,
                                             token.minted_at, token.expires_at)).rowcount
        if minted != 1:
            # `ON CONFLICT (token) DO NOTHING` makes this a rowcount rather than an error, so the
            # transaction is still usable and the rollback below is ours to trigger deliberately.
            raise ValueError(f"token id {token.token!r} is already minted, so nothing was "
                             f"resolved: review row {row_id} is untouched and can still be "
                             "resolved")
        return token


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m retinue.boundary.resolve")
    ap.add_argument("row_id", type=int)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true")
    group.add_argument("--reject", action="store_true")
    ap.add_argument("--by", required=True, help="the reviewer's identity, recorded on the row")
    ap.add_argument("--at", required=True, help="ISO timestamp; the clock is an argument")
    ap.add_argument("--key", help="the act's idempotency key; an approval needs it and the "
                                  "review row does not carry it")
    ap.add_argument("--tool", help="the tool the approval is for; an approval needs it and the "
                                   "review row does not carry it")
    ap.add_argument("--window-hours", type=float, default=24.0)
    ap.add_argument("--dsn", required=True)
    args = ap.parse_args(argv)

    # Before the connection, so an approval that cannot bind costs the row nothing at all.
    if args.approve and not (args.key and args.tool):
        print("--approve needs --key and --tool: the review row carries a handoff, which holds "
              "neither the act's idempotency key nor the tool name", file=sys.stderr)
        return 2

    # The connection seam, and all of it: one read, handed to the function above. Everything the
    # command decides is decided there, where no database is needed to drive it.
    import psycopg
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute(SELECT_HANDOFF, (args.row_id,))
        row = cur.fetchone()

    def resolve_fn(**kwargs):
        return resolve_pg(args.dsn, **kwargs)

    code, message = outcome_after_read(row, row_id=args.row_id, approve=args.approve,
                                       by=args.by, at=datetime.fromisoformat(args.at),
                                       window=timedelta(hours=args.window_hours),
                                       key=args.key, tool=args.tool, resolve_fn=resolve_fn)
    print(message, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
