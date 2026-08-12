# retinue

An orchestrated fleet of three specialist agents - research, drafting, conversation - around an
imported deterministic boundary, with a Postgres relationship ledger, a matching integration, and
an evaluation harness. It is the system a founding engineer would build for agent-run,
relationship-led outreach: the agent layer, the gate that decides what agents may do alone and the
evals behind it, and the matching engine beneath them. Determinism is the doctrine and keys are
incidental, so the default lane needs no running service, live runs exist only to capture evidence
once, and no test contacts a model or a network. Clone it, `pip install -r requirements.txt`,
`python -m pytest`: that is the whole default lane.

Both halves of that sentence were looser before, in the two places a skeptic would press first. It
said the default lane is "dependency-free", against five declared runtime dependencies including
`psycopg[binary]`; the claim is that nothing needs to be RUNNING, not that nothing is installed. And
it said "nothing in CI contacts a model or a network", while `.github/workflows/ci.yml` runs
`pip install -r requirements.txt` on every job. The job reaches PyPI. No test reaches anything.

The design spec is `docs/superpowers/specs/2026-08-10-retinue-design.md` and it governs design
intent: where this file and the spec disagree about what the system is meant to be, the spec wins.
Build status runs the other way. The spec's section 12 table is the seed this file's
Designed-vs-Built table replaced, and it still reads as it did the day the spec was written, so on
what is actually built the table at the bottom of this file is the authority.

**Status: P1 through P4 are built. Six rows in the table stay Designed.** P1 is the research
spine; P2 the matching integration, the ranking evaluators, the frozen-verdict replay and the
block-stripped control; P3 the drafting specialist, the chokepoint, the pre-flight review surface
and the durable review queue; P4 the conversation specialist and the live demo. The
Designed-vs-Built table at the bottom is the authority on which capability is which, and it is not
a summary of this sentence: a status claim and a row that disagree is the defect the table exists
to catch, and the row is what gets fixed. The six Designed rows say so there, by name, with the
reason: four capabilities this design added (the approval bridge, the ladder tier,
contested-quantity rendering, the weights-update sketch) and two notes inherited from the library
(the sliding-window contact limit, store unification). An earlier version of this sentence counted
four, written before the approval bridge and the ladder tier joined the table, which is the
count-versus-row disagreement the previous sentence describes.

Two things below are built and have never executed anywhere: the Postgres lane and CI itself. Each
says so where it is documented, and neither is described here as a run that happened. The judge
capture and the live demo both left this list on 2026-08-12: each ran once, and their outputs are
the frozen fixtures the default lane replays.

CI is the one that was nearly missed, and naming it is the point of the list. An earlier version
left CI off it, which invited the reading that everything else had run. This repository has no remote and has never been
pushed, so `.github/workflows/ci.yml` has never executed; the local interpreter is 3.13, so nothing
has been run on 3.11 by anyone. Every count below is from this machine, on this version.

## What retinue imports

The boundary library `chaperone`, as a vendored wheel at `vendor/chaperone-0.1.0-py3-none-any.whl`
whose origin is recorded in `vendor/PROVENANCE.md`. Its source is
`https://github.com/EsraaKamel11/chaperone`, so the claim below that this repository adds no policy
code of its own is one a reader can check against the library rather than take on trust. Never `pip install chaperone`: that PyPI name
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
commit: 241 passed, 9 skipped, all 9 for the Postgres lane below. No second `-q`: `pyproject.toml`'s
`addopts` already carries one, and `-qq` deletes the summary line that both CI and the battery
read. The lane holds the options-shape tests, the hook callback replayed against captured payloads,
the specialist tests under pydantic-ai's own offline doubles, the ledger contract tests against an
in-memory reference store, the matching integration against the imported staging, the ranking
evaluators over a hand-judged gold shortlist across the seeded synthetic roster, the frozen judge
replay, the block-stripped control, the chokepoint's ordering and denial tests, the pre-flight
two-signal routing, the review queue's in-memory half, and the audit's own planted-violation tests.
`.github/workflows/ci.yml` is written to run it on 3.11 and 3.13, then the battery. It has never
run: there is no remote and nothing has been pushed, so the 3.11 half of that matrix is a claim
about a version no one has executed this suite on.

**Postgres lane** - keyed on `RETINUE_PG_DSN`. Unset, it skips with a printed reason. Set, the same
contract tests run against real Postgres alongside the enforcement tests only a real database can
earn, five tests: the append-only trigger, the plan assertion that the projection's hot query
reaches the named index, a separate one that its ORDER BY rides that index rather than a Sort, the
durable review-queue sink, and one test holding the unique idempotency key and concurrent append
together, because exactly-one-wins under concurrency is the uniqueness claim under load.

Those two plan assertions were one test until this lane's first execution, which is the whole
argument for running a lane rather than reading it. It reddened on the Sort clause while its own
name's properties held: the named index was reached and there was no Seq Scan, but at roughly
twenty-five rows per investor the planner chose a bitmap scan and re-sorted. A planner choice at
toy scale, not a broken index. The ordering claim now has its own test at its own size, and the
first run's plan is pinned in the docstring as the finding it was.
`RETINUE_PG_REQUIRED=1` turns a skip into a failure, which is the negative control that keeps the
lane from being vacuous.

> **This lane has never executed, anywhere.** There is no Docker on the machine this was built on
> and an ephemeral cluster would not start there, so every Postgres statement in this repository is
> code that has been read and never run. `.github/workflows/ci.yml` is its first execution. Treat
> the schema, the adapter and the enforcement tests accordingly until that run is green.
>
> Locally: `docker compose up -d --wait`, then export the DSN from the trailing comment in
> `docker-compose.yml` (port 55432, because a locally installed Postgres commonly holds 5432).

**Live lane** - `RETINUE_LIVE=1`, keyed, manual, flag-gated, and never in CI. Live runs are capture
runs: payloads are recorded once, stamped with the versions that produced them, frozen under
`fixtures/`, and replayed by the default lane forever. There are three capture scripts and they are
in three different states, which is the whole reason they are listed one by one:

| Script | Command | State |
|---|---|---|
| `scripts/capture_smoke.py` (P1) | none, see below | Has run. Its payloads are frozen under `fixtures/payloads/` and the script now refuses every invocation. |
| `scripts/judge_capture.py` (P2) | `RETINUE_LIVE=1 python scripts/judge_capture.py` | Has run once (2026-08-12). Its verdicts are frozen and replayed; running it again overwrites that canon, which is a deliberate act and not a refresh. |
| `scripts/demo.py` (P4) | `RETINUE_LIVE=1 python scripts/demo.py` | Has run once (2026-08-12). The send tool's offer was asserted in the live session before any gating claim, the conversation send fired the hook's ask, and the tool body was reached zero times. Its capture is frozen and replayed; running it again overwrites that canon. |

**The P1 capture is frozen, and there is no command that retakes it.** `scripts/capture_smoke.py`
refuses to construct a session in which any send tool exists, which was the point of the run: its
payloads are the evidence that nothing in that session could ask. P4 then widened the session
roster so that the demo could show a send being gated in a session that offers one, so the smoke's
guard now fires on every invocation and prints `not a send-free session`. The guard is right and
the roster is right. What that leaves is a script whose session no longer exists, and the choice
was between giving it a capture-only send-free options shape and declaring the capture frozen. It
is frozen, because `fixtures/payloads/` records the P1 topology as it stood, a retake under today's
ceiling could not reproduce it, and a capture taken from an options shape nothing else in the tree
constructs would be evidence about a session the fleet does not run. The script stays as the record
of how those payloads were taken. A missing payload is therefore a broken checkout, not a lane
awaiting its turn, and the tests that read them fail rather than skip.

Both live captures have now run, once each, on the same day. The demo's output,
`fixtures/payloads/captured_ask.json`, is the one fixture that could never have been hand-authored
into existence, because its provenance is the point: it is a real hook payload from a real session
in which a send tool was offered, a gated specialist tried to use it, and the hook held it for a
human while the tool body went unreached. `tests/boundary/test_ask_replay.py` replays it and now
fails rather than skips on absence, since a tracked capture that is missing is a broken checkout.
The judge capture's output, `fixtures/verdicts/judge_verdicts.json`, stopped being hand-authored
the same way; what its two verdicts do and do not establish is owned by the fixture-provenance
section below.

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

- each gate first runs its own invocation, flags and all, against one specimen per branch of its
  pattern, all of which have to hit, and reddens as INERT otherwise - a single specimen would only
  show a pattern is not totally dead, and half a dead gate reports ok just as convincingly;
- the scan is held to a floor on tracked files rather than to "more than zero", and a positive
  control asserts the counting machinery returns hits at all;
- the suite gate is held to a floor on the pass count, parsed from pytest's own summary, because
  pytest exits 0 for a run in which every test skipped;
- a grep that exits with an error status is a failed gate, never zero hits.

That last guard earned its place by being caught rather than foreseen: a grep build that aborts on
one flag combination printed nothing, and the gate scored the silence as a clean pass.

Both floors are re-baselined to the finished tree at this commit and stay floors rather than
equalities: a floor raised to equality reddens on the first added test and gets exempted, which is
how a gate stops measuring.

**It also says what it did not read.** Every gate scans `git ls-files`, so an untracked file is
invisible to all of them while each still prints ok - measured, by dropping an untracked file
holding a stale model id into the tree and watching the script exit 0. Scanning what ships is the
right scope and has not changed; the silence was the defect. The run now counts untracked
non-ignored files, names them, and does not fail on them, because a work in progress is not a
violation and a gate that reddens on ordinary work gets disabled.

The plan's Task 11 section embeds this script verbatim, and a test in the default lane holds the
two byte-identical, so a plan describing gates the script no longer has is a red suite.

The client-and-organisation token pass reads `tools/banned_tokens.txt`, which is **untracked and
gitignored on purpose**: a tracked list would ship into a reader's clone the very tokens it
exists to keep out. The battery therefore runs without it and says the pass did not run, rather
than reporting an "ok" it did not earn, and a hit prints `[redacted]` rather than the token. A list
that exists but holds no entries reddens, since an empty list is a mistake and not a policy. The
cost of the design is worth naming: an untracked file can never reach CI, so this is the one gate
here with no standing enforcement outside the author's own machine.

Spec section 11 names one more grep family, marketing figures, which is deliberately not a gate:
it has no reliable textual signature, so a pattern loose enough to catch one reddens on correct
text. That intent is served by a hand-diff pass over invented figures instead, and the omission is
written into `tools/battery.sh` beside the gates rather than left to be noticed.

## Why not `pydantic-ai-harness`

`pydantic-ai-harness` (PyPI; `github.com/pydantic/pydantic-ai-harness`) is the official capability
library for pydantic-ai. This repository is built on pydantic-ai and does not use it, and the
reason is design rather than compatibility. Version 0.18.1, read on 2026-08-11, and the date is
stated because a 0.x package that ships breaking changes between minor releases dates any claim
made about it: at that version the harness wants `pydantic-ai-slim>=2.23.0` on Python >=3.10, while
this repository pins `pydantic-ai>=2.23` on Python >=3.11, so adoption is possible and nothing
below is a compatibility excuse.

`ToolGuardrail` guards the tools a **pydantic-ai Agent** executes. This fleet's act boundary sits at
the Claude Agent SDK's `PreToolUse` hook, because the SDK is the runtime executing the fleet's
tools, and the chokepoint is `attempt_send` wrapping the imported `guarded_call`. Three execution
layers, and the guardrail belongs to the one the acts do not travel through. `ToolGuardrail` is a
wiring point rather than a policy in any case, since the caller supplies the callable: adopting it
would add a place to call the imported engine from, and would not replace the engine.

Two convergences are worth more than the code. The harness **deliberately declines** to ship a
prompt-injection detector, on the reasoning that injection is ordinary language, so a pattern list
catches the examples and misses the attack, and a check that reads as protection without being it
is worse than none at all. That is this repository's own doctrine, reached independently. And the
harness's `hidden=`, which drops a tool from the definitions the model sees, against a visible
refusal, is the same distinction as the session-roster ceiling here: the research specialist has no
outbound tool at all rather than a refused one.

One question is carried open rather than answered. Policy denials here are terminal because
chaperone's own README documents the `requires_approval` resume round trip as unsafe, since
`override_args` substitutes before re-validation. The harness documents that same round trip and
states that on the resumed run the guard is re-evaluated and every verdict except `approve` still
applies. Whether that closes the hole is unverified in either direction; no run here has settled
it, and it is a named gap rather than a resolved one.

## What the live captures settled

Three live capture runs of the P1 smoke, at claude-agent-sdk 0.2.130 with bundled CLI 2.1.222. The
fixtures kept are all from one session, under `fixtures/payloads/`, and they are the frozen capture
described above. What they settled, from real payloads rather than by reasoning:

- **`agent_type` exists, and is spelled `research`.** The hook routes on that exact string, and
  the documented hook input does not list the key at all. If no real payload carried it, `decide`
  would collapse to its main-thread arm and the ask branch would be dead code, silently. A default
  lane test asserts a captured payload carries it.
- **`tools=` restricts; `allowed_tools=` only pre-approves.** Five names were declared and the
  session resolved four (`Task, Glob, Grep, Read`), with no CLI default surviving beside them. That
  session's options held the spawn names alone in the allow list (the allow list is options-side,
  so it is not a field of the captured payload), and the captured `system:init` shows `Glob`,
  `Grep` and `Read` resolved into the session anyway. So the honest bound is the session ceiling,
  not the allow list.
  (Spec section 3 also records the orchestrator actually calling `Glob` under that allow list. That
  payload came from an earlier run in the series and is deliberately not in the tree: the fixtures
  were reduced to a single session so two capture runs could not be mixed into one corpus. The
  roster evidence above stands on the retained capture alone.)
- **The spawn tool is one tool under two names, by surface.** `system:init` reports `Task`; the
  `tool_use` blocks and the hook payloads report `Agent`. Carrying both as data was necessary
  rather than defensive.

Read that roster as the P1 session's, because it is. The session roster is wider today: P4 added
the two send spellings to it, so the ceiling now offers a send tool the P1 session had no way to
reach. The capture is evidence about what the SDK does with `tools=`, and it is not a picture of
the fleet's current session.

## The session is not hermetic by default

The captured `system:init` for the P1 session carried five MCP servers and sixteen agent definitions
where the topology declares three. (`fixtures/payloads/captured_init.json` is that capture and holds
eight definitions, because the sixteen and the eight are TWO CAPTURES rather than two stages of one:
sixteen with `setting_sources` unset, eight with it set, which is what the paragraph below measured.
Read the fixture as the second of those.) A session inherits the operator's ambient configuration,
because `agents=` merges rather than replaces.

`setting_sources=[]` is set, and what it buys was measured rather than assumed: sixteen agent
definitions fell to eight, two plugins and the operator's own hooks stopped running inside the
capture, and the resolved tool list was identical either way. What it does **not** remove: the
CLI's five built-in agents, which are the product rather than anyone's configuration, and the five
MCP servers, which reach the session from a source that option does not govern.

The field that would close the MCP half is `ClaudeAgentOptions.strict_mcp_config` (SDK 0.2.130,
default `False`, mapping to the CLI's `--strict-mcp-config`, documented as ignoring every MCP
configuration the CLI would otherwise load). The fleet does not set it today, and that sentence is
source-cited at 0.2.130 rather than captured, so the residual is guarded instead of assumed: a
fixture contract asserts that no `mcp__` tool resolved into the P1 session, which is the property
those servers would have to breach before their presence mattered.

That contract is scoped to `captured_init.json` and to nothing else, deliberately, and the scope is
the load-bearing part rather than a caveat. P4 registers an in-process SDK MCP server inside
`scripts/demo.py`, so an `mcp__` send tool does resolve into that session on purpose: containment
is never demonstrated by the absence of the thing being contained. The rule keeps its edge over the
one file whose claim is a send-free session, and it makes no claim about the demo's.

Partial hermeticity is worth stating as partial. A capture taken under one machine's ambient
configuration is not canonical whatever it happens to show.

## Fixture provenance limit

Fixtures here are hand-authored unless their own `meta` says `captured`, and the captured list is
short: the P1 session payloads, and since 2026-08-12 the judge verdicts. **Over hand-authored
fixtures, every number this repository produces is a demonstration of a protocol, not a measured
claim about model behaviour.** Both halves of that sentence are load-bearing: the first says how
those fixtures were made, and the second says what follows, which is that no figure computed over
them may be read as an observation of a model. The gold rankings and the drafts' ground truth are
in that class.

The judge verdicts are the one crossing of that line, and the crossing is dated:
`scripts/judge_capture.py` ran once on 2026-08-12, so the verdict column is a captured judge's
answer, frozen at the library version and model id stamped in the fixture's own `meta`. The drafts
and their ground truth are still one author's judgment. What the capture bought is stated at its
exact size: calibration and discrimination are now a captured judge read against one author's
labels over two cases, and the judge marked the compliant draft at confidence 0.55, under the 0.7
floor, so the calibration figure divides by a single confident verdict. Raw agreement is two of
two, pinned separately in the test that reads the file. A real judge inside a small protocol
demonstration, not a measurement at scale; re-running the capture overwrites the canon, which is
why it is manual and flag-gated.

Synthetic mandate and check-size figures are invented and resemble no real firm's published ranges.
Each fixture declares exactly one provenance in its own `meta` block, and a test enforces that,
including that a capture carrying an operator's home directory path has to declare the redaction.

## Designed vs Built

Rows land as Built only when they are built. This table is the authority: where a claim elsewhere
in this file and a row here disagree, the row is the thing that gets corrected.

| Capability | Status |
|---|---|
| Deterministic act boundary, checker, handoff, queues, audit chain | **Built (imported: `chaperone.gates`, `chaperone.policy`, `chaperone.audit`)** |
| Matching staging | **Built (imported: `chaperone.matching`)** - `src/retinue/matching/integrate.py` imports `filters` and `rank`. The row said "staging + ablation harness"; nothing here runs an ablation. The phrase survives in the spec's section 12 seed table and inside the vendored wheel, which packages the library's own copy; it is corrected here because on build status this table is the authority. |
| The library's own purity audit | **Not imported.** The wheel ships `src/chaperone` only; the source repository's `tools/` and `tests/` do not travel. |
| Orchestration options + hook + routing | **Built (P1)** - `src/retinue/orchestration/topology.py`, `src/retinue/boundary/hook.py` |
| Research agent + ResearchBrief contract | **Built (P1)** - `src/retinue/specialists/research.py`, `src/retinue/specialists/failures.py` |
| Ledger schema, projection, `ActContext` feed | **Built (P1)** - `schema.sql`, `src/retinue/ledger/`. The in-memory contract lane is green; the Postgres half has never executed anywhere (see Lanes). |
| Rendered block renderer (budget + completeness raises) | **Built (P1)** - `src/retinue/ledger/block.py` |
| Live capture smoke + payload fixtures | **Built (P1)** - `scripts/capture_smoke.py`, `fixtures/payloads/`, plus the seeded roster generator at `src/retinue/synth/rosters.py`. The capture is frozen and the script refuses every invocation (see Lanes). One gap it names itself stays unproduced: the `background`-unset half of the background evidence pair, which needs a run against a deliberately-unset definition. The "ask" fixture moved to the P4 demo, which owns it. |
| Matching integration + ranking evaluators + OutcomeRecord | **Built (P2)** - `src/retinue/matching/integrate.py`, `src/retinue/evals/ranking.py`, `src/retinue/ledger/outcomes.py` |
| Block-stripped control | **Built (P2)** - `src/retinue/evals/control.py` |
| Judge capture + frozen-verdict replay | **Built (P2)** - `scripts/judge_capture.py`, `src/retinue/evals/frozen.py`. The capture ran once (2026-08-12); the verdict set is captured, stamped in its own meta, and replayed by the default lane. Two cases with one under the confidence floor: real-judge evidence at protocol size, not a measurement at scale. |
| Drafting agent + chokepoint wiring + pre-flight review | **Built (P3)** - `src/retinue/specialists/drafting.py`, `src/retinue/boundary/send_tool.py`, `src/retinue/boundary/checker_lane.py`, `src/retinue/boundary/preflight.py`. `attempt_send` has no caller outside its own module and its tests, which is stated rather than left to be found. The checker lane, the pre-flight surface and the review queue are reachable only through it, so they have no production caller either. |
| Durable review-queue table (escalation persistence) | **Built (P3)** - `src/retinue/boundary/review_queue.py`, `schema.sql`. The in-memory half is green; the durable half is Postgres and has never executed anywhere. |
| Conversation agent + live demo | **Built (P4)** - `src/retinue/specialists/conversation.py`, `scripts/demo.py`. The demo ran once (2026-08-12): the send tool's offer was asserted in the live session, the conversation send fired the hook's ask, the tool body was reached zero times, and the captured ask is tracked and replayed by `tests/boundary/test_ask_replay.py`. The reason a human is shown for a gated send is now asserted over a hand-authored payload and a captured one. |
| **Ask-to-chokepoint approval bridge** | **Designed only, and it is the seam the two lanes meet at.** Nothing mints, transports or validates an approval token. `build_act_context` defaults it, the imported check is presence-only, and its violation class is terminal, so a composed system denies every send unless a caller invents a token - which would reduce "a human approved this act" to "the caller passed a non-None string". An SDK permission grant hands the tool body no evidence it can carry, so this is an unanswered design question rather than unwritten wiring. The spec asserted this as sourced until 2026-08-12. |
| **Tier from the ladder decision** | Designed only - `chaperone/gates/ladder.py` ships in the wheel and nothing here imports it. Tier arrives as a bare int parameter. |
| Contested-quantity rendering + thin-support badge | Designed only - the contract carries `quantity_key` so a conflict can be held, and the prompt instructs the model to group by it, but nothing renders a Contested quantity or a thin-support badge. Annotate-not-arbitrate is the commitment; surfacing the annotation is unbuilt. |
| Weights-update sketch | Designed - `src/retinue/ledger/outcomes.py` carries the outcome-signal config parameter the sketch would read, and nothing updates a weight or a threshold from a resolved outcome. |
| Per-investor sliding-window contact limit | Designed (inherits the library's note) |
| Store unification (audit chain + ledger) | Designed note only |
