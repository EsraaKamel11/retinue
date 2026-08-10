# retinue - design spec

**Date 2026-08-10. Status: written, pending review round and user review.**
Produced via brainstorming: three open decisions user-resolved, an architecture shape carried through
two adversarial review passes, a full concept audit against the competency register and a
line-complete sweep of three course corpora (15,412 lines), all deltas folded before this document
was written.

**What retinue is.** An orchestrated fleet of three specialist agents - research, drafting,
conversation - around an imported deterministic boundary, with a Postgres relationship ledger, a
matching integration, and an evaluation harness. It is the system a founding engineer would build
for agent-run, relationship-led outreach: the agent layer, the eval gate that decides what agents
may do alone, and the matching engine behind them.

**What retinue imports.** The boundary library (`chaperone`, vendored wheel - see
`vendor/PROVENANCE.md`). The wheel ships the library's `src/` only: its purity-audit tooling and its
test suite do not travel, and this repository never implies they do. The import is a declared API
contract enumerated in section 6.

**Version pins.** `claude-agent-sdk 0.2.130` (bundled CLI 2.1.222) · `pydantic-ai` /
`pydantic-evals` `2.23.0` · `psycopg[binary] >=3.1` · Python >=3.11. Framework claims in this spec
carry these versions; a claim without its version is undated and invalid here. Floors live in the
manifest; capture stamps record exact resolved versions.

---

## 1. Doctrine

**Determinism is the doctrine; keys are incidental.** The default lane is deterministic and
dependency-free. Live runs exist to *capture* evidence once, which is then frozen and replayed
forever. Nothing in CI contacts a model or a network.

**The runtime loop is Perception-Act-Verify.** Perceive = research plus ledger context assembly.
Act = draft and send through the chokepoint. Verify = the independent checker (clean-room by
construction), post-send verification, and the evaluation lane. The two-lane split (deterministic
act boundary; probabilistic content checking) is Verify's implementation, not a rival frame.

**A measurement is never an authorization.** Eval rates decide how much autonomy a class of action
has earned - offline, human-ratified. Permission is enforced at call time by code a reader can
audit. The two never share a mechanism. No judge verdict ever sits on the act path.

**Tri-state honesty.** Post-send verification returns CONFIRMED / FAILED / UNVERIFIABLE, and the
system never guesses a pass: anything not literally decidable is UNVERIFIABLE and escalates to the
durable human-review queue. The imported checker's abstention type maps onto the same register:
a verdict that establishes a violation is an EXCEPTION; a flag-for-review is UNVERIFIABLE.

---

## 2. Lanes and evidence tiers

### 2.1 Default lane (all CI, fresh clone)

`pytest -q` passes on a fresh clone: **no daemon, no network, no key** - deterministic and
dependency-free. (Constructing SDK options offline requires the SDK *package*, which is therefore a
default dependency; it spawns nothing at import or construction time.) It contains:

- **Options-shape tests**: the orchestrator topology asserted AS DATA - the agents dict, each
  specialist's tool roster, `permissionMode`, `background=False` on every `AgentDefinition`, the
  hook registration, and the orchestrator's own tool list being exactly the spawn tool and nothing
  else (a config-sourced bound asserted where it lives).
- **Hook-callback tests over captured payloads** (see 2.3): the deterministic lane's decisions
  replayed against recorded subagent tool-call payloads.
- **Specialist tests** under `TestModel` / `FunctionModel` (pydantic-ai's own offline doubles).
- **Ledger contract tests** against an in-memory reference store - a Python structure, not sqlite:
  a second SQL dialect would be a second implementation of the schema under test.

### 2.2 Postgres lane (DSN-keyed; not "offline", and not default because of environmental nondeterminism)

Docker in the default path would make the suite's failure surface include registry outages, image
pulls, wait-for-ready races, and port collisions - none deterministic. So:

- `RETINUE_PG_DSN` set: the **same contract tests** run against real Postgres, plus DB-enforcement
  tests that only a real database earns - unique/idempotency constraints, the append-only trigger,
  concurrent append, and the query-plan assertions: the projection's hot query runs over an
explicitly named index (`idx_touchpoints_investor_ts` - named so a test can match it), and a plan
test asserts that name appears in the `EXPLAIN` output, over a fixture sized so the planner
actually chooses it (a ten-row table seq-scans regardless, and the assert must fail on a seq
scan, never accept one).
- `RETINUE_PG_DSN` unset: skip, with a printed reason.
- **CI negative control:** one ubuntu job runs `services: postgres` with `RETINUE_PG_REQUIRED=1`,
  which turns skip into FAIL. A lane that can silently skip forever is a vacuous gate; this makes
  vacuity a red build.
- The Postgres image tag is pinned exactly, matching the managed-Postgres target's major version. One idempotent
  `schema.sql` applied by `ledger.bootstrap(dsn)` is the whole migration story - which is also the
  managed-Postgres story, since the one schema file applies unchanged on the managed target.
- Rejected: testcontainers (adds a Docker-API dependency and still requires a daemon),
  pytest-postgresql (host `initdb`/`pg_ctl` binaries; poor Windows story). `docker-compose.yml` is
  one documented way to provide the DSN, not the harness contract.

### 2.3 Live lane (keyed, manual, flag-gated, never CI)

Live runs are **capture runs**: transcripts and payloads recorded once, stamped
`captured@0.2.130 / CLI 2.1.222`, frozen, and replayed by the default lane forever.

The **P1 capture smoke** is the first: orchestrator plus the research subagent, with no send tool
existing anywhere in the session. It produces the canonical fixtures for: real hook payloads from
subagent tool calls (`agent_type` populated); the spawn tool's
naming as it actually appears in `system:init` and `tool_use` blocks; and the background-stripping
evidence pair - one run with `background` unset (tool list silently stripped), one with
`background: False` (tool offered). The `"ask"` surfacing fixture is deliberately NOT this smoke's
to produce - no send tool exists in its session, so nothing asks; it is captured by the first
session where one does (the P4 demo, or the flag-gated headless variant).

**Judge protocol:** judge once live (keyed, manual), freeze the verdicts, replay forever. The LLM
judge never runs *in* CI, on determinism grounds.

### 2.4 Evidence tiers (every load-bearing claim in this spec carries one)

1. **Deterministic-lane-witnessed** - contract, shape, and replay tests.
2. **Live-captured at version** - existentials only: "this happened, at 0.2.130 / CLI 2.1.222."
3. **Structurally unobservable at 0.2.130** - named as pure limitations, never papered over:
   universally quantified runtime claims (transcripts sample; they never prove "in every mode");
   permission-evaluation internals (no event stream distinguishes an ask rule skipped from one
   never consulted - so the fleet registers **no allow/ask rules** for the send tool, keeping the
   one unresolved framework corner unreachable by design); and counterfactuals, which stay
   source-cited at version.

**Test-inertness rule (suite-wide):** every constraint test is shown to fail with the constraint
removed, once, at introduction. A pinned-version suite is exactly the regime where a silently
ignored kwarg yields a green suite that tests nothing.

---

## 3. Topology

| Agent | mode | tools | background | model tier | never |
|---|---|---|---|---|---|
| orchestrator | `default` | spawn tool only (both current and legacy names listed as data; which binds is runtime-only) | - | `sonnet-tier` | calls no external surface; drafts nothing; **holds no specialist tool** |
| research | inherit | fixture-read tools only | **False** | `haiku-tier` | **no outbound tool exists in its session** |
| drafting | inherit | ledger-read only | **False** | `haiku-tier` | no send tool; output goes to review |
| conversation | inherit | send tool (gated) | **False** | `sonnet-tier` | send never executes without hook + chokepoint |

- Tier names are the imported `MODEL_STRENGTH` vocabulary (`haiku-tier` / `sonnet-tier` /
  `opus-tier` - anything else raises). "The drafter", for the checker-ordering guarantee, is the
  drafting specialist's tier.
- The checker runs a tier at least as strong as the drafter; the imported
  `assert_checker_not_weaker` enforces the ordering at construction, and the table above makes the
  imported guarantee visible as data.
- **One** parent-registered `PreToolUse` hook, keyed on `agent_type`, treating `None` as
  main-thread. It carries the imported deterministic lane plus routing: `"ask"` on outward sends.
  `"defer"` appears only in a flag-gated headless variant and stays source-cited at 0.2.130 until
that variant captures it.
- The orchestrator's mode is `default` - of the six permission modes, three are sticky (a
  subagent's own `permissionMode` is ignored under them, not narrowed), so a permissive orchestrator
  would erase permission mode as a per-specialist lever. Source-cited at 0.2.130.
- The hook's decision table, complete: `agent_type` absent -> main thread, allow · `research` /
  `drafting` -> allow (their rosters contain no outward tool to gate) · `conversation` + send tool
  -> `"ask"` · `conversation` + any other tool -> allow (nothing outward) · any unrecognised
  `agent_type` -> `"ask"` (unknown fails toward the human). The hook decides on payloads, not
  rosters, which is why the non-send conversation row exists.
- Routing helpers are plain Python scoped strictly to that table.
  Task routing belongs to the live-lane model via `AgentDefinition.description`; the default lane
  drives specialists directly and needs no router.
- Each specialist is **one module emitting both artifacts** - the SDK `AgentDefinition` and the
  pydantic-ai `Agent` - from shared constants, with a **parity test** on tool rosters and prompt
  source - asserting both artifacts reference the same prompt constant object, not equal strings. Nothing enforces a specialist's output schema at live runtime; the act boundary holds at
  the chokepoint, and the content contract is an offline eval. This spec says so rather than letting
  a reader discover it.

---

## 4. Specialist contracts

All contracts are pydantic models with `output_type` binding in the offline lane.

### 4.1 ResearchBrief

A list of **claims**, each carrying:

- `claim: str` and `evidence: str`
- `source: str` - **must resolve to a fixture document id. Resolution is containment, not
  equality**: live models emit qualified citations ("doc-3 (filing, p.4)"), never bare tokens, and
  an equality check would fail every claim on the one capture run that cannot be cheaply re-taken.
  Resolution checks existence; **support** - whether the source actually establishes the claim - is
  a judged question that lives in the eval lane, and the spec states that split.
- `source_date: date` - **mandatory, no default**. Constructing an undated claim raises.
- `confidence: float` - recorded, **routes nothing**.
- `needs_identifier: bool` + `candidates: tuple[str, ...]` - ambiguity is flagged, never guessed.
- A grouping key per quantity, so two sources reporting different values for the same fact are
  **both kept** (Contested), never averaged; a single-source fact carries a thin-support badge.
  Annotate, don't arbitrate - with a contract shape that can actually hold a conflict.

**The prompt and the validator are a coupled pair**: the prompt names the same source-id and
grouping conventions the validator checks, and the coupling is stated at both definition sites so
they are edited together.

### 4.2 Draft

The imported boundary library's own `Draft` contract, unchanged - six fields: thread, body,
cited fields, recipient jurisdiction, recipient domain, tool name. Jurisdiction and domain are
populated from the ledger's identity record (5.1); the thread field is why 4.3 composes rather
than siblings.

### 4.3 ConversationTurn

**Composes a `Draft`** (the thread already rides inside it) rather than siblinging it, so the
conversation lane hands the checker everything the boundary library already carries.

### 4.4 Validation failure taxonomy (per contract)

Failures are categorised at the validator, and the category decides the response:

- **Retryable** (malformed citation, format, internal inconsistency): retried with the prior
  offending value quoted verbatim in the retry prompt, under the standard retry budget.
- **Never-retryable** (`missing_source`: no fixture supports the claim): **escalates immediately,
  zero further model calls.** A corpus that does not contain the answer will not start containing
  it on retry; retrying is an invitation to fabricate, which is the failure this design exists to
  make structural rather than behavioural.

---

## 5. The ledger (Postgres)

### 5.1 The record is a projection

**Every fact arrives as a touchpoint.** The relationship record - identity, stated check size,
pass reason, last contact - is a pure projection of the append-only touchpoint stream. There is no
direct record write: a newly stated check size is a touchpoint of type `stated_check_size`, and the
record derives. This makes the safe-write gate structural, keeps append-only honest, and yields
bi-temporality for free: every touchpoint carries `occurred_at` (when true in the world) and
`recorded_at` (when the system learned it).

- Touchpoints: append-only, `idempotency_key UNIQUE` + `ON CONFLICT DO NOTHING` - a behaviour a
  real database earns, tested in the DSN lane. An append-only trigger enforces no UPDATE/DELETE.
- `stated_check_size` is `NUMERIC` -> `Decimal`, never float; every money comparison uses a
  tolerance, never `==`.
- Send touchpoints carry the tri-state `delivery_status`: CONFIRMED / FAILED / UNVERIFIABLE, with
  UNVERIFIABLE a designed value (sent-but-unconfirmed is a state, not an error). A later-resolving
  outcome updates the OutcomeRecord, never the touchpoint.
- **OutcomeRecord**: investor and mandate keys; `occurred_at` vs `observed_at` (outcomes resolve
  over weeks, so the two diverge structurally); a **parameterized signal enum**
  (`replied` / `meeting_booked` / `check_written`) whose *active* member is configuration - the
  outcome signal is a genuinely open product question, and this shape keeps it a toggle rather than
  silently settling it; attribution rule named: last-touch as the parameterized default.
- Timestamps are injectable for tests; database `now()` only at the adapter edge.

### 5.2 The projection into the boundary

**The ledger's structural job is feeding the boundary's `ActContext` at the chokepoint** (all six
fields sourced below). The imported library documents its own
sharpest limit here: with nothing feeding it, `sent_count` defaults to a permissive zero and a
re-attempt is unguarded. This projection closes that published limit - the fleet does not merely
import the boundary, it completes it.

All six `ActContext` fields are sourced: `sent_count` from the touchpoints table per investor,
`consented_jurisdictions` from the identity record, the approval token from the ask flow,
`granted_tools` from the topology roster, `tier` from the ladder decision (defaulting to the most
restrictive), `send_cap` from configuration.

**Projection tri-state:** no-touchpoints (a true zero for a new investor) and
projection-unavailable (the store could not be read) are different facts and carry different types
(`0` vs `None`). **Unavailable fails closed at the chokepoint**, by a named mechanism: the projection returns
`None`, and the boundary intercepts **before** `guarded_call` is ever reached - it denies with the
boundary-level class `projection_unavailable` (a boundary denial class, deliberately NOT a policy
`ViolationClass`: the fleet adds no policy code) and writes the handoff with that class's own
reviewer-facing text. No context is fabricated, the policy engine never runs on invented values,
and the denial never masquerades as a policy judgment - a sentinel context pushed through the
engine would have reported `no_approval_token`, which is a lie about what happened. Zero-because-new and zero-because-the-query-failed must never reach the
guard as the same integer, because the second one opens it.

### 5.3 The rendered block

The record projects into a bounded context block that rides in every prompt:

- **Byte budget enforced with a raise**, not a warning.
- **Completeness enforced with a raise**: a required field that is absent, null, or empty-string
  (all three checked) raises naming the missing field. A partial block is the fabrication vector
  arriving through the most-trusted component; the silent alternative is the agent confidently
  reading back null.
- The block's **section header text is a machine-checked contract** - the control eval's stripper
  matches on it (7.1).
- Conversation summarization never touches the record or the block; the compaction boundary is
  structural, not prompt-level.

Tiering: this is **two of the three memory tiers** - the rendered block (hot) and the Postgres
ledger (warm). A cold tier of periodic re-derivable rollups is **deliberately absent**: there is no
lookback volume to serve. The pattern is named at two-of-three, not claimed in full.

### 5.4 Matching integration

Imports the boundary library's matching modules unchanged: hard filters, then relationship state,
then similarity **inside the filtered set**; a mandate violation costs **membership, not score**;
the similarity score remains an **injected callable** - a scope commitment, not a key artifact. A
live demo may inject a real embedder over synthetic rosters; building an embedding pipeline is out
of scope and would contradict the stated commitment.

Additions: gold-ranking frozen fixtures; hand-rolled ranking evaluators as floats with
`evaluation_name` set explicitly - **hit@N returns 1.0/0.0; MRR returns the reciprocal rank (1,
1/2, 1/3, ...), never a binary**. (Lineage note: these metrics come from the ranking-evaluation
analysis in the project ledger, not from the course corpus, whose metric family is Brier score
sliced by cell.) The weights-update sketch is **Designed**, reads the outcome-signal parameter, and
at this volume updates weights and thresholds from a handful of resolved outcomes - not a learned
model. Cold start is noticed by the metric: a new investor carries no relationship state, so
similarity must carry them, and the metric must notice when it does not.

---

## 6. The boundary (`boundary/`)

Named `boundary/`, not `gates/`: two packages called `gates` collide in prose and in a reader's
head, even though imports would resolve.

- Owns constructing what the imported `guarded_call` requires: the `Gateway` over the audit
  store, the tool registry, and the keyword-only review queues.
- **The send tool's body calls the imported `guarded_call`** - the checker runs at the chokepoint,
  never in the hook. Denials are terminal via the imported `Handoff`; there is no resume round-trip
  (the library documents the framework's approval-resume path substituting arguments before
  re-validation, which is exactly the failure the chokepoint refuses).
- **The terminal-send guard runs first, before input validation.** Validation-first returns a
  readable error the model can correct and resubmit - a real second send. The ledger's idempotency
  key catches the duplicate row; this ordering catches the duplicate act.
- **The handoff refuses to escalate incomplete**: all summary fields required, so an empty
  escalation is unrepresentable rather than discouraged.
- **P3's review surface calls the imported full-lane `pre_tool_use` as a pre-flight**, annotating
  every draft with its would-be verdict before the reviewer sees it - the full predicate set,
  checker included, with no execution. The fleet is that function's first real caller.
- **Review routing is a two-signal disjunction**: checker denial OR pre-flight failure (the
  annotation errored or produced no verdict) routes to human. Parity tests are CI checks, not a
  runtime signal. Model confidence deliberately routes nothing - following the corpus's own
  escalation design whose trigger list excludes the model's self-rated confidence. (Named as
  two-signal; a third signal would be reviewer disagreement, which exists only when a second
  reviewer does.)
- **"Why two stores"**, pre-answered: the imported file-based hash-chained audit is tamper-evidence
  for gate decisions; the Postgres ledger is relationship state. Unification is a Designed note.
- The fleet adds **no policy code**. Its audit is therefore import discipline, and it is
  **AST-based**: `ast.walk` over `Import`/`ImportFrom` nodes, one named test per rule - only
  `boundary/` imports the gate and audit modules; `specialists/` imports no gate module; the send
  tool is defined in exactly one module. Grep is defeated by a docstring, a comment, or a string
  literal, and cannot tell an import from a mention; the AST walk can, and its failure message
  names the rule that broke.

### 6.1 Declared import surface

The wheel's `__init__` is empty; every import is a submodule path, and this list is the API
contract the fleet depends on (the library never published one):

`chaperone.gates.hook` (`pre_tool_use`, `guarded_call`) · `chaperone.gates.sdk_callback`
(`pre_tool_use_deny`) · `chaperone.gates.handoff` · `chaperone.gates.checker` (transport seam,
`assert_checker_not_weaker`, and the verdict types: `Verdict`, `FlagForReview`, `CheckerResult`,
`CheckerUnavailable`) · `chaperone.gates.queues` · `chaperone.policy.types` (`Draft`, `Record`,
`Decision`, `Finding`, `ViolationClass`, `Disposition`) · `chaperone.policy.act_classes`
(`ActContext`) · `chaperone.matching.*` (filters, relationship, rank) · `chaperone.audit.*`
(store, gateway, chain). Verified against the wheel's source tree; `ActContext` lives in
`act_classes`, not `types`, and the library's own hook imports it from there.

### 6.2 Repo layout

`src/retinue/{orchestration,specialists,ledger,matching,boundary,evals}` · `fixtures/` (frozen,
each carrying a `meta.captured` stamp) · `synth/` · `vendor/` (the wheel + provenance) ·
`schema.sql` · `tests/`. **The hook module lives at `boundary/hook.py`** - boundary owns every
`chaperone.gates` import, and orchestration registers the hook by importing it *from boundary* -
which is what keeps the AST audit's rules single-sourced and greppable.

---

## 7. Evaluation harness

- pydantic-evals `Dataset`s over frozen hand-authored fixtures (judged content); a seeded
  deterministic generator for unjudged volume (investor rosters) only.
- **Calibration and discrimination are separate checks** - one asks whether the checker's
  confidence is calibrated, the other whether the quality score ranks a violating draft above a
  compliant one. Conflating them blurs the two-lane thesis inside its own evidence.
- Judge protocol per 2.3: judge once live, freeze, replay. Calibration then carries real verdict
  provenance, frozen at version.

### 7.1 The block-stripped control

The most-trusted component gets the containment treatment: a control eval re-asks **only the
questions whose answers depend on block-only fields**, against a context with the block stripped
(the stripper matches the block's exact section header - which is why the header is a contract).
**At least one must fail.** That failure is the proof the block is load-bearing; a control that
passes proves the stripper silently did nothing. Judged once live, frozen, replayed.

### 7.2 Provenance limits (stated, both halves)

Fixtures are hand-authored, not blind-authored like the imported library's corpus - so every number
this harness produces is a **protocol demonstration**, not a measured claim about model behaviour.
Verdicts are frozen at version. Synthetic mandate and check-size figures are invented and resemble
no real firm's published ranges.

---

## 8. Failure taxonomy

Register discipline: every failure classified to a named mode with a **pre-decided recovery path**,
terminating in durable human review. Escalation durability is a Postgres review-queue table -
the imported in-memory queues are the in-process half only (their own docstring: going out of
scope takes the escalations with them), so the durable half is fleet-designed. Explicitly not a
graph-checkpointer.

| Surface | Mode | Response |
|---|---|---|
| research | `missing_source` | never-retryable; escalate immediately (4.4) |
| research | malformed citation / format | retry with prior value verbatim, budgeted |
| drafting | checker unusable after budget | fail closed: a direct `Checker.check` raises `CheckerUnavailable`; at the chokepoint and pre-flight the imported engine converts it into a routed denial carrying `outage` - either way, never an allow |
| drafting | checker denial | terminal handoff; redraft proposes to a human, never auto-retries |
| conversation | outward send attempt | hook `"ask"` -> human; chokepoint at execution |
| conversation | send executed, unconfirmed | touchpoint `delivery_status=UNVERIFIABLE`; escalate to queue; never guessed CONFIRMED |
| ledger | projection unavailable | **fail closed** at chokepoint, highest-restriction tier (5.2) |
| any | hook crash (SDK contract) | fails **open** per the platform contract - which is why every escape in the callback is forced to a decision, and why the chokepoint exists behind it |
| any | guard exception (pydantic-ai contract) | fails **closed** - propagates |

The last two rows name which contract each sentence means; the two frameworks fail in opposite
directions and no sentence in this repository leaves that ambiguous.

---

## 9. Phases

- **P1 - research spine.** Orchestration options + the hook (act-lane infrastructure - the boundary
  itself is imported, not built here), the research agent end-to-end through the default lane, the
  ledger (touchpoints, projection, `ActContext` feed - the projection is why the DB harness is
  justified in P1), **the rendered block** (5.3 - it rides in every prompt, so the research agent
  needs it), fixtures, the AST audit, and the **live capture smoke** (2.3).
- **P2 - matching.** Matching integration, OutcomeRecord, ranking evaluators, the judge capture
  plus frozen-verdict replay (calibration and discrimination), and the block-stripped control.
- **P3 - drafting + chokepoint.** Drafting agent, send-tool wiring through `guarded_call`, the
  `pre_tool_use` pre-flight review surface, two-signal routing. **The chokepoint's first caller is
  the scripted driver; the first agent caller arrives in P4** - the boundary lands before the agent
  it bounds, which is the published build order, stated rather than accidental.
- **P4 - conversation.** The conversation agent behind `"ask"`, and the live demo - which must
  assert the send tool was **offered** before claiming the hook gated it. Containment is never
  demonstrated by the absence of the thing being contained.

Each phase is independently demonstrable; no phase depends on a later one.

---

## 10. Rejected alternatives (each with its reason, none silent)

Policy stored in the database (policy-as-data contradicts auditable-by-reading; policy stays code) ·
a tool-registry table (right at production platform scale, wrong at three specialists) · retry with
backoff at the chokepoint (contradicts non-retryable denials) · token-bucket rate limiting (the
per-investor contact limit over touchpoints is a different object with the same name; Designed) ·
batch APIs and SLA math (no batch workload; replay removes the cost argument) · prompt caching (the
live lane runs once) · a token counter in the default lane (imports model-dependence; the byte
budget is lane-independent) · vector-store claim grouping (requires a real embedder in the default
lane) · external MCP server configuration (unused; the SDK's in-process `create_sdk_mcp_server` tool surface is used exactly once, in the P4 demo, because a send tool must exist in a session before its gating can be demonstrated) · the CLI-product configuration surface (this
is an SDK application) · settings allow/ask rules for the send tool (the unresolved evaluation-order corner is
hook-allow versus ask-rule; registering none keeps it unreachable) · settings deny lists
(redundant with tool absence plus the hook) · a hand-rolled agent loop (the SDK owns it) · an agentic
refinement loop at the review surface (a second live call per draft, against a deliberately human
surface; the cap principle transfers, the loop does not) · competing-agents (nothing to arbitrate
among fixed contracts) · async fan-out mechanics (the SDK spawns; the default lane drives directly)
· a cold memory tier (no lookback volume; named absent) · sqlite anywhere (a second SQL dialect) ·
a graph-checkpointer for escalation durability (the queue plus Postgres is the durable path).

---

## 11. Verification battery (run before the review round, and again before any send)

1. Suite: default lane green on a fresh clone; DSN lane green under `RETINUE_PG_REQUIRED=1`.
2. Greps, expect zero: em dashes · the two banned certainty adjectives (word-bounded; "provenance" is not a hit) · marketing figures · stale
   model ids and removed API kwargs · every entry on the governing plan's client-and-organisation
   token list. **The list is referenced, never enumerated here**: a battery that names its own
   banned tokens fails on its own specification.
3. The consistency table from the governing plan, run row by row against this spec.
4. The register below/above check: nothing here sits below a registered competency or implies an
   unregistered one.
5. Designed-vs-Built: every imported capability marked **Built (imported: `src/chaperone/<path>`)**;
   the purity audit explicitly **not** imported; everything fleet-new marked Designed until built.
6. Test-inertness: every constraint test demonstrated red-with-constraint-removed at
   introduction, with the red run recorded in the introducing commit's message.

---

## 12. Designed-vs-Built (seed - the README inherits this table)

| Capability | Status |
|---|---|
| Deterministic act boundary, checker, handoff, queues, audit chain | **Built (imported: `src/chaperone/gates/`, `src/chaperone/policy/`, `src/chaperone/audit/`)** |
| Matching staging + ablation harness | **Built (imported: `src/chaperone/matching/`)** |
| Orchestration options + hook + routing | Designed (P1) |
| Research agent + ResearchBrief contract | Designed (P1) |
| Ledger schema, projection, `ActContext` feed | Designed (P1) |
| Live capture smoke + payload fixtures | Designed (P1) |
| Matching integration + ranking evaluators + OutcomeRecord | Designed (P2) |
| Block-stripped control | Designed (P2) |
| Drafting agent + chokepoint wiring + pre-flight review | Designed (P3) |
| Conversation agent + live demo | Designed (P4) |
| Per-investor sliding-window contact limit | Designed (inherits the library's note) |
| Rendered block renderer (budget + completeness raises) | Designed (P1) |
| Judge capture + frozen-verdict replay | Designed (P2) |
| Durable review-queue table (escalation persistence) | Designed (P3) |
| Store unification (audit chain + ledger) | Designed note only |
