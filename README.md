# retinue

An orchestrated fleet of three specialist agents - research, drafting, conversation - around an
imported deterministic boundary, with a Postgres relationship ledger, a matching integration, and
an evaluation harness. It is the system a founding engineer would build for agent-run,
relationship-led outreach: the agent layer, the eval gate that decides what agents may do alone,
and the matching engine behind them. Determinism is the doctrine and keys are incidental, so the
default lane is dependency-free, live runs exist only to capture evidence once, and nothing in CI
contacts a model or a network.

The design spec is `docs/superpowers/specs/2026-08-10-retinue-design.md` and it governs. Where this
file and the spec disagree, the spec wins.

**Status: Phase 1, the research spine, is what exists. Phases 2, 3 and 4 are not built.** The
Designed-vs-Built table at the bottom is the authority on which is which, and nothing above it
describes unbuilt work as built.

## What retinue imports

The boundary library `chaperone`, as a vendored wheel at `vendor/chaperone-0.1.0-py3-none-any.whl`
whose origin is recorded in `vendor/PROVENANCE.md`. Never `pip install chaperone`: that PyPI name
belongs to an unrelated package. The wheel ships the library's `src/` only, so the library's own
purity-audit tooling and its test suite do not travel with it and this repository does not imply
they do. This repository adds no policy code of its own; the import surface it depends on is the
declared contract in spec section 6.1, and the substitute for a purity audit here is import
discipline enforced as AST rules (`tools/fleet_audit.py`).

## Install

```
pip install -r requirements.txt
```

Order matters and the file encodes it: the vendored wheel first, then this package as an editable
install with its dev extra. Python >=3.11.

## The three lanes

**Default lane** - `python -m pytest`. No daemon, no network, no key, on a fresh clone. At this
commit: 72 passed, 7 skipped, the 7 being the Postgres lane below. It holds the options-shape
tests, the hook callback replayed against captured payloads, the specialist tests under
pydantic-ai's own offline doubles, and the ledger contract tests against an in-memory reference
store.

**Postgres lane** - keyed on `RETINUE_PG_DSN`. Unset, it skips with a printed reason. Set, the same
contract tests run against real Postgres alongside the enforcement tests only a real database can
earn: the unique idempotency key, the append-only trigger, concurrent append, and the plan
assertion that the projection's hot query uses the named index. `RETINUE_PG_REQUIRED=1` turns a
skip into a failure, which is the negative control that keeps the lane from being vacuous.

> **This lane has never executed, anywhere.** There is no Docker on the machine this was built on
> and an ephemeral cluster would not start there, so every Postgres statement in this repository is
> code that has been read and never run. `.github/workflows/ci.yml` is its first execution. Treat
> the schema, the adapter and the enforcement tests accordingly until that run is green.
>
> Locally: `docker compose up -d --wait`, then export the DSN from the trailing comment in
> `docker-compose.yml` (port 55432, because a locally installed Postgres commonly holds 5432).

**Live lane** - `RETINUE_LIVE=1 python scripts/capture_smoke.py`. Keyed, manual, flag-gated, and
never in CI. Live runs are capture runs: payloads are recorded once, stamped with the SDK and CLI
versions that produced them, frozen under `fixtures/`, and replayed by the default lane forever.

## The battery

```
bash tools/battery.sh                        # PYTHON=/path/to/python ... to pick an interpreter
```

It scans every tracked file except the wheel and expects zero hits on: em dashes, the two banned
certainty adjectives (word-bounded, so "provenance" is not a hit), the removed pydantic-ai 2.x
result kwarg, and stale model ids. Then it runs the AST import audit and the full suite.

Its patterns are constructed rather than spelled, so the script passes the battery it defines
instead of exempting itself. Every gate asserts a magnitude and not merely a non-zero, because
"nothing found" and "nothing looked" print the same word:

- each gate first runs its own invocation, flags and all, against a specimen built to violate it,
  and reddens as INERT if it finds nothing there, so a pattern that has quietly stopped matching
  cannot go on reporting ok;
- the scan is held to a floor on tracked files rather than to "more than zero", and a positive
  control asserts the counting machinery returns hits at all;
- the suite gate is held to a floor on the pass count, parsed from pytest's own summary, because
  pytest exits 0 for a run in which every test skipped;
- a grep that exits with an error status is a failed gate, never zero hits.

That last guard earned its place by being caught rather than foreseen: a grep build that aborts on
one flag combination printed nothing, and the gate scored the silence as a clean pass.

The client-and-organisation token pass reads `tools/banned_tokens.txt`, which is **untracked and
gitignored on purpose**: a tracked list would ship into a reviewer's clone the very tokens it
exists to keep out. The battery therefore runs without it and says the pass did not run, rather
than reporting an "ok" it did not earn, and a hit prints `[redacted]` rather than the token. A list
that exists but holds no entries reddens, since an empty list is a mistake and not a policy. The
cost of the design is worth naming: an untracked file can never reach CI, so this is the one gate
here with no standing enforcement outside the author's own machine.

Spec section 11 names one more grep family, marketing figures, which is deliberately not a gate:
it has no reliable textual signature, so a pattern loose enough to catch one reddens on correct
text. That intent is served by a hand-diff pass over invented figures instead, and the omission is
written into `tools/battery.sh` beside the gates rather than left to be noticed.

## What the live captures settled

Three live capture runs, at claude-agent-sdk 0.2.130 with bundled CLI 2.1.222. The fixtures kept
are all from one session, under `fixtures/payloads/`. What they settled, from real payloads rather
than by reasoning:

- **`agent_type` exists, and is spelled `research`.** The hook routes on that exact string, and
  the documented hook input does not list the key at all. If no real payload carried it, `decide`
  would collapse to its main-thread arm and the ask branch would be dead code, silently. A default
  lane test asserts a captured payload carries it.
- **`tools=` restricts; `allowed_tools=` only pre-approves.** Five names were declared and the
  session resolved four (`Task, Glob, Grep, Read`), with no CLI default surviving beside them. In
  the same `system:init`, the allow list held the spawn names alone while `Glob`, `Grep` and `Read`
  resolved into the session anyway. So the honest bound is the session ceiling, not the allow list.
  (Spec section 3 also records the orchestrator actually calling `Glob` under that allow list. That
  payload came from an earlier run in the series and is deliberately not in the tree: the fixtures
  were reduced to a single session so two capture runs could not be mixed into one corpus. The
  roster evidence above stands on the retained capture alone.)
- **The spawn tool is one tool under two names, by surface.** `system:init` reports `Task`; the
  `tool_use` blocks and the hook payloads report `Agent`. Carrying both as data was necessary
  rather than defensive.

## The session is not hermetic by default

The captured `system:init` carried five MCP servers and sixteen agent definitions where the
topology declares three. A session inherits the operator's ambient configuration, because `agents=`
merges rather than replaces.

`setting_sources=[]` is set, and what it buys was measured rather than assumed: sixteen agent
definitions fell to eight, two plugins and the operator's own hooks stopped running inside the
capture, and the resolved tool list was identical either way. What it does **not** remove: the
CLI's five built-in agents, which are the product rather than anyone's configuration, and the five
MCP servers, which reach the session from a source that option does not govern.

The field that would close the MCP half is `ClaudeAgentOptions.strict_mcp_config` (SDK 0.2.130,
default `False`, mapping to the CLI's `--strict-mcp-config`, documented as ignoring every MCP
configuration the CLI would otherwise load). The fleet does not set it today, and that sentence is
source-cited at 0.2.130 rather than captured, so the residual is guarded instead of assumed: a
fixture contract asserts no `mcp__` tool resolves **into** the session, which is the property those
servers would have to breach before their presence mattered.

Partial hermeticity is worth stating as partial. A capture taken under one machine's ambient
configuration is not canonical whatever it happens to show.

## Fixture provenance limit

Fixtures here are hand-authored, not blind-authored. **Every number this repository produces is a
demonstration of a protocol, not a measured claim about model behaviour.** Judge verdicts, when
they exist, are frozen at version. Synthetic mandate and check-size figures are invented and
resemble no real firm's published ranges. Each fixture declares exactly one provenance in its own
`meta` block, and a test enforces that, including that a capture carrying an operator's home
directory path has to declare the redaction.

## Designed vs Built

Rows land as Built only when they are built.

| Capability | Status |
|---|---|
| Deterministic act boundary, checker, handoff, queues, audit chain | **Built (imported: `chaperone.gates`, `chaperone.policy`, `chaperone.audit`)** |
| Matching staging + ablation harness | **Built (imported: `chaperone.matching`)** |
| The library's own purity audit | **Not imported.** The wheel ships `src/chaperone` only; the source repository's `tools/` and `tests/` do not travel. |
| Orchestration options + hook + routing | **Built (P1)** - `src/retinue/orchestration/topology.py`, `src/retinue/boundary/hook.py` |
| Research agent + ResearchBrief contract | **Built (P1)** - `src/retinue/specialists/research.py`, `src/retinue/specialists/failures.py` |
| Ledger schema, projection, `ActContext` feed | **Built (P1)** - `schema.sql`, `src/retinue/ledger/`. The in-memory contract lane is green; the Postgres half has never executed anywhere (see Lanes). |
| Rendered block renderer (budget + completeness raises) | **Built (P1)** - `src/retinue/ledger/block.py` |
| Live capture smoke + payload fixtures | **Built (P1)** - `scripts/capture_smoke.py`, `fixtures/`, plus the seeded roster generator at `src/retinue/synth/rosters.py`. Two gaps the script names itself: the `background`-unset half of the background evidence pair is unproduced, and the "ask" fixture belongs to the first session that owns a send tool, which is P4. |
| Contested-quantity rendering + thin-support badge | Designed only - the contract carries `quantity_key` so a conflict can be held, and the prompt instructs the model to group by it, but nothing renders a Contested quantity or a thin-support badge. Annotate-not-arbitrate is the commitment; surfacing the annotation is unbuilt. |
| Matching integration + ranking evaluators + OutcomeRecord | Designed (P2) |
| Block-stripped control | Designed (P2) |
| Judge capture + frozen-verdict replay | Designed (P2) |
| Drafting agent + chokepoint wiring + pre-flight review | Designed (P3) |
| Durable review-queue table (escalation persistence) | Designed (P3) |
| Conversation agent + live demo | Designed (P4) |
| Per-investor sliding-window contact limit | Designed (inherits the library's note) |
| Store unification (audit chain + ledger) | Designed note only |
