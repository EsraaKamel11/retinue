"""Operator CLI for the DSN lane: python -m retinue.boundary.resolve <row-id> --approve ...

Reads the review row for the binding material that row actually carries, refuses an approval it
could not bind, and otherwise resolves through `approvals.resolve` - the same verb with the same
arguments the memory lane calls in-process. The memory lane never uses this module.

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
neither: an operator rejecting a draft should not need the act's idempotency key.

**Two connections today, not one transaction, said plainly rather than claimed away.** Spec
section 2 asks the mint to be atomic with the resolution, one transaction in Postgres.
`PgResolutionLog.record` and `PgApprovalStore.put_token` each open their own connection and each
commit on their own, so a crash between them leaves a resolved row with no token - the same
unresolvable row named above. The plan's Task 4 step 5 owns the one-transaction wrapper and the
contract test that pins it. Until that lands this module calls the two stores as they stand, and
says so here rather than describing an atomicity it has not got.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from retinue.boundary.approvals import PgApprovalStore, PgResolutionLog, resolve

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

    import psycopg
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute(SELECT_HANDOFF, (args.row_id,))
        row = cur.fetchone()
    if row is None:
        print(f"no review row {args.row_id}", file=sys.stderr)
        return 2
    handoff = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    binding, missing = binding_material(handoff, key=args.key, tool=args.tool)
    if args.approve and missing:
        print(f"review row {args.row_id} supplies no {', '.join(missing)}, so approving it could "
              "mint only a token bound to nothing; the row is left unresolved", file=sys.stderr)
        return 2

    token = resolve(row_id=args.row_id, verdict="approve" if args.approve else "reject",
                    at=datetime.fromisoformat(args.at), approved_by=args.by,
                    window=timedelta(hours=args.window_hours),
                    resolutions=PgResolutionLog(args.dsn), approvals=PgApprovalStore(args.dsn),
                    key=binding["key"], body=binding["body"], tool=binding["tool"],
                    recipient_domain=binding["recipient_domain"])
    if token is None:
        print("resolved: no token minted (rejection, or the row was already resolved)")
        return 0 if args.reject else 1
    print(f"resolved by {args.by}; token {token.token} expires {token.expires_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
