# retinue

[![CI](https://github.com/EsraaKamel11/retinue/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/EsraaKamel11/retinue/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%20%7C%203.13-3776ab?logo=python&logoColor=white)
![postgres](https://img.shields.io/badge/postgres-16.4-336791?logo=postgresql&logoColor=white)
![pydantic-ai](https://img.shields.io/badge/pydantic--ai-%E2%89%A52.23-e92063?logo=pydantic&logoColor=white)
![claude-agent-sdk](https://img.shields.io/badge/claude--agent--sdk-%E2%89%A50.2.130-d97757)
![boundary](https://img.shields.io/badge/boundary-chaperone%20%28vendored%20wheel%29-b68235)

The CI badge is live and the rest are the pinned stack. The two Python versions are the tested
matrix rather than the supported range: `pyproject.toml` requires >=3.11, and CI runs 3.11 and 3.13.
No test count is badged, deliberately, since a hand-set number goes stale in silence, and the
battery section below is about exactly that failure shape.

An orchestrated fleet of three specialist agents - research, drafting, conversation - around an
imported deterministic boundary, with a Postgres relationship ledger, a matching integration, and
an evaluation harness. It is the system a founding engineer would build for agent-run,
relationship-led investor fundraising, synthetic end to end: the agent layer that researches
investors, drafts the approach and carries the conversation; the gate that decides what agents may
do alone and the evals behind it; and the matching engine beneath them. The one irreversible act -
the outward send - is the thing the boundary gates. Determinism is the doctrine and keys are
incidental, so the default lane needs no running service, live runs exist only to capture evidence
once, and no test contacts a model or a network. Clone it, `pip install -r requirements.txt`,
`python -m pytest`: that is the whole default lane.

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

Every count in this file is from this machine, on 3.13, unless the sentence names CI's run instead.

## Contents

**How it is built** - [The two classes](#the-two-classes) ·
[How an act travels](#how-an-act-travels) · [The roster](#the-roster) ·
[The topology is data](#the-topology-is-data) · [The repository](#the-repository) ·
[What retinue imports](#what-retinue-imports) ·
[Where the act boundary sits](#where-the-act-boundary-sits-and-why-not-pydantic-ai-harness) ·
[The ledger](#the-ledger) · [Matching and the evals](#matching-and-the-evals) ·
[Decisions](#decisions)

**Running it** - [Install](#install) · [Configuration](#configuration) · [Usage](#usage) ·
[The three lanes](#the-three-lanes) · [The battery](#the-battery)

**Evidence and its limits** - [The one live demo run](#the-one-live-demo-run) ·
[What the live captures settled](#what-the-live-captures-settled) ·
[The session is not hermetic by default](#the-session-is-not-hermetic-by-default) ·
[Fixture provenance limit](#fixture-provenance-limit) ·
[What this repository does not claim](#what-this-repository-does-not-claim)

**Status and authority** - [Which source is authoritative](#which-source-is-authoritative) ·
[Run history](#run-history) · [Corrections this file carries](#corrections-this-file-carries) ·
[Roadmap](#roadmap) · [Designed vs Built](#designed-vs-built) · [License](#license)

## The two classes

Everything a fleet produces is one of two things. **Content** is information somebody consumes: a
research brief, a draft body, a proposed conversational turn. **An act** is an irreversible,
externally visible event, and this fleet has exactly one - the outward send. The design treats the
two asymmetrically, and the asymmetry is the whole architecture:

- **Acts are bounded structurally, so the bound can be stated as structure.** The research and
  drafting specialists are offered no outbound tool at all - not a refused tool, an absent one.
  The conversation specialist's send is held for a human before the call. The one act path is built to run
  the imported deterministic engine at a chokepoint inside the send-tool body - wired and tested,
  with no agent caller yet, which
  [What this repository does not claim](#what-this-repository-does-not-claim) states before
  anything else. Each of those is a property of code and captured payloads, not of model
  behaviour.
- **Content is measured, never asserted.** Rates are reported with their denominators; invariants
  are asserted. A hand-authored fixture demonstrates a protocol and is never presented as a
  measured claim about model behaviour ([fixture provenance](#fixture-provenance-limit)).
- **This repository adds no policy code.** Every predicate that decides anything is imported from
  the vendored boundary library. A predicate that seems missing is consumed from the library or
  becomes a Designed row, never rewritten here.

The invariants the system enforces, each with its enforcement site rather than a promise:

1. Only `boundary/` imports the gate surface, and the send-tool name has a single home
   (`tools/fleet_audit.py`, AST rules with planted-violation tests, run by the battery and CI).
2. Unknown fails toward the human: an unrecognised or malformed `agent_type` answers "ask", and
   the hook's whole body is guarded because a hook that raises fails OPEN by platform contract
   (`boundary/hook.py::pre_tool_use`).
3. An unreadable store is a denial, never an empty record. `project_record` returns `None` only
   for a store that could not be read, the chokepoint refuses to fabricate a context from it, and
   matching raises rather than ranking on it (`ledger/projection.py`, `boundary/send_tool.py`,
   `matching/integrate.py`).
4. The ledger is append-only in the database, not in prose: UPDATE, DELETE and TRUNCATE all meet
   triggers (`schema.sql`).
5. No act is silent. A send the gate allowed and the ledger lost comes back as `UnrecordedSend`
   with an escalation already filed; the failure this closes is unbounded, because an unwritten
   row makes the idempotency key a reusable send licence (`boundary/send_tool.py`).
6. A composed send today cannot complete autonomously. The conversation lane's send is held for
   a human before the call, and the main thread's body-only shape is refused by the imported lane
   on `act:no_approval_token`, because nothing mints an approval token - the Designed
   approval-bridge row. That refusal is a measurement over that payload shape, never a property
   of the lane: the suite's own token-carrying fixture is denied on `act:figure_not_in_record`
   instead (`tests/boundary/test_hook.py`).
7. No test contacts a model or a network. Live runs are capture runs: recorded once, stamped,
   frozen under `fixtures/`, replayed forever.

## How an act travels

Read top to bottom, this is the spine the rest of the file annotates. Every step names the module
that owns it.

```
                     ClaudeAgentOptions  (orchestration/topology.py::build_options)
                     tools = SESSION_TOOLS ceiling ; allowed_tools = spawn names only
                     setting_sources=[] ; PreToolUse hook on every tool call
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
          research                    drafting                  conversation
          (content)                   (content)              (content proposing an act)
          Read, Grep, Glob            Read                   Read + the send tool
              |                           |                           |
          ResearchBrief               draft body             ConversationTurn
          cites or refuses            goes to review         (composed Draft + intent)
              |                           |                           |
              +---------- every tool call, every agent ---------------+
                                          |
                        boundary/hook.py::pre_tool_use
                        routes by the ROUTING table (data, held total by test)
                          conversation + send  ->  "ask": a human, before the call
                          unknown agent_type   ->  "ask": fail toward the human
                          main thread + send   ->  the imported deterministic lane
                                          |
                        boundary/send_tool.py::attempt_send      (the one act path)
                        terminal guard -> validation -> context pre-check
                        -> imported guarded_call (engine + checker at the chokepoint)
                        -> tri-state delivery -> the ledger answers, or escalates
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
         touchpoints                 review_queue               audit trail
         append-only ledger          durable half FIRST,        (imported Gateway)
         (Postgres / in-memory)      in-memory second
```

Five layers, top to bottom: the session options are the spec layer, written as data; the
orchestrator routes work to the three specialists; every tool call passes the one registered
hook; the single act path runs the imported engine at its chokepoint; and what remains is state -
the ledger, the durable review queue, the audit trail. One honesty note belongs on the diagram
rather than under it: `attempt_send` has no caller outside its own module and its tests, which is
stated in the [Designed vs Built](#designed-vs-built) table rather than left to be found. The
demo's live session captured the gate holding a send BEFORE the chokepoint; the chokepoint itself
is exercised by its test suite, not yet by an agent.

1. **The session is declared, not spawned.** `build_options` in
   `src/retinue/orchestration/topology.py` returns the SDK options: the three agent definitions,
   `tools=SESSION_TOOLS` as a shared ceiling, `allowed_tools=SPAWN_TOOLS` as the pre-approve list,
   `setting_sources=[]`, `permission_mode="default"`, and one `PreToolUse` hook. Nothing in that module spawns anything; the
   topology is data the tests assert against.
2. **A specialist is offered a subset of the ceiling.** Each `AgentDefinition` declares its own
   tools and states `background=False`, and the CLI resolves a specialist's tools by intersecting
   its declaration with the session roster, so the ceiling is a maximum and never a grant.
   Research declares `Read`, `Grep`, `Glob`; drafting declares `Read`; conversation declares
   `Read` plus both send spellings.
3. **Every tool call meets the hook first.** `pre_tool_use` in `src/retinue/boundary/hook.py`
   routes on `agent_type` through the `ROUTING` table: conversation asking for a send name is held
   for a human with `ask`, an unrecognised agent type is `ask` as well, and everything else is
   `allow`. The checker does not run here.
4. **A send past routing enters the imported lane.** On a send name the hook delegates to
   chaperone's `pre_tool_use_deny`; on anything else it answers `{}`, which declines to intervene
   rather than affirming an allow.
5. **The chokepoint is the tool body.** `attempt_send` in `src/retinue/boundary/send_tool.py` runs
   in a fixed order: the terminal duplicate-key guard before input validation - validation-first
   would hand the model a readable error to correct and resubmit, a real second act - then
   validation, then the pre-check where a missing projection denies at boundary level with the
   policy engine never reached, then the imported `guarded_call`, which is where the engine and
   the checker run. The pre-check's class, `boundary:projection_unavailable`, is deliberately not
   a policy `ViolationClass`: no policy predicate ran, so the denial may not masquerade as a
   policy judgment.
6. **The act is recorded on the same call that made it.** A `sent` touchpoint is appended
   tri-state, `CONFIRMED` / `FAILED` / `UNVERIFIABLE`, and `store.append`'s boolean is read: an
   act the ledger did not record returns `UnrecordedSend` and files an escalation rather than
   raising, because a raise after an irreversible act invites the retry that sends twice. The
   ledger row carries byte counts, never text: message bodies live in the review queue's
   `Handoff`, not in the ledger.
7. **Denials and escalations are terminal, and they go to a human.** They travel as the imported
   `Handoff` to the `human-review` queue, whose durable half is the `review_queue` table, under
   the queue name the imported engine's own `destination_for` answers, held by double entry in
   `test_the_boundary_queue_is_the_imported_engines_own_destination`
   (`tests/boundary/test_send_tool.py`). `annotate` in `src/retinue/boundary/preflight.py` runs the same full lane over a draft with no
   execution, so a reviewer reads the would-be verdict; `routes_to_human` is the two-signal
   disjunction of a checker denial and a pre-flight that produced no verdict.

The `ActContext` step 5 hands the engine is built by `build_act_context` in
`src/retinue/ledger/projection.py`: tier, granted tools and the send cap arrive as parameters,
`sent_count` is counted off the ledger's own `sent` touchpoints, and `approval_token` defaults to
None, which is the approval bridge the table at the bottom carries as Designed only.

## The roster

| Name | Class | Input | Output | Decision boundary |
|---|---|---|---|---|
| orchestrator (main thread) | routing, not authoring | operator query | spawns specialists via the spawn tool | bounded by the same `SESSION_TOOLS` ceiling; its own send call routes into the imported deterministic lane, which refused the body-only payload shape measured (`orchestration/topology.py`) |
| `research` | content | `fixtures/docs/*.md` | `ResearchBrief`: frozen `Claim`s, cited and dated | no gate imports, no outbound tool offered; a malformed citation buys ONE retry, a missing source escalates in one model call - retrying it is an invitation to fabricate (`specialists/research.py`) |
| `drafting` | content | `RelationshipRecord` | draft body, built into a `Draft` | drafts from the record only; output goes to review, never directly out; refuses to build without the identity fields (`specialists/drafting.py`) |
| `conversation` | content proposing an act | record + thread | `ConversationTurn` = composed `Draft` + intent label | every outward send is gated: the hook asks a human before the call; the thread rides INSIDE the draft so checker and reviewer judge the same object (`specialists/conversation.py`) |
| checker (an instrument, not an agent) | judge over drafts | the imported checker prompt | `Verdict` / `FlagForReview` | scripted frozen verdicts by default, live transport only in capture scripts; construction enforces tier ordering; a flag maps to UNVERIFIABLE, never to clean (`boundary/checker_lane.py`) |

The three specialists exist twice by design: as `AgentDefinition`s the SDK runs and as
pydantic-ai `Agent`s the offline tests drive - and the parity rule is that both read the SAME
prompt constant, imported, so the tested prompt and the running prompt cannot drift apart.

No act-class agent exists. The only act is a tool call, and the tool is gated.

## The topology is data

There is no fleet spec file format to document, and that is the design: the topology is Python
data in `orchestration/topology.py`, asserted by tests and rendered by docs. The real objects,
abbreviated to their shape:

```python
TIERS = {"orchestrator": "sonnet-tier", "research": "haiku-tier",
         "drafting": "haiku-tier", "conversation": "sonnet-tier"}

AGENTS: dict[str, AgentDefinition] = {
    "research":     AgentDefinition(tools=["Read", "Grep", "Glob"], background=False, ...),
    "drafting":     AgentDefinition(tools=["Read"], background=False, ...),
    "conversation": AgentDefinition(tools=["Read", *sorted(SEND_TOOLS)], background=False, ...),
}

SESSION_TOOLS = ("Agent", "Task", "Read", "Grep", "Glob", *sorted(SEND_TOOLS))

ROUTING: tuple[tuple[str, frozenset[str]], ...] = (      # boundary/hook.py
    ("research", frozenset()),
    ("drafting", frozenset()),
    ("conversation", SEND_TOOLS),
)
```

Four facts about this table are held by a test or a measurement rather than by the comment that
states them:

- **The session roster is a shared ceiling, not a per-agent bound.** The CLI resolves each
  subagent's tools by INTERSECTING its declaration with `SESSION_TOOLS`, witnessed in a captured
  `system:init` at CLI 2.1.222 - so a send tool declared by conversation and absent from the
  ceiling resolves away silently, with every options-shape test still green. That is why the send
  names sit in both places in the excerpt above, imported from their single home in
  `boundary/hook.py`.
- **`ROUTING`'s domain is held against `AGENTS`' keys** by `test_decision_table_is_total`, so an
  agent added to the topology without a routing row is a red suite, not a silent main-thread arm.
- **It is a tuple of pairs, not a dict, and the difference is diagnosis.** A non-string
  `agent_type` out of a malformed payload walks off the end and takes the unknown-agent ask; a
  hashing lookup raises TypeError instead, and the human reads "the router could not complete"
  for a payload that was what went wrong. Both shapes fail closed; the chosen one names the cause.
- **`background=False` is stated on every definition, never left unset.** The SDK drops `None`
  fields at serialisation, the CLI's own default has been `background` since 2.1.198, and a
  background subagent has its tool list stripped. Containment shown against a stripped roster
  would be containment of nothing.

Model tiers use the imported `MODEL_STRENGTH` vocabulary, and the checker-ordering guarantee - the
checker never weaker than the drafter - is enforced by the imported constructor at build time:
`build_checker` raises if the checker tier drops below `TIERS["drafting"]`
(`boundary/checker_lane.py`).

## The repository

| Path | What is in it |
|---|---|
| `src/retinue/orchestration/` | the topology as data: agent definitions, tiers, the session ceiling, `build_options` |
| `src/retinue/specialists/` | the three prompts and their agents: research, drafting, conversation, plus the research contract's failure types |
| `src/retinue/boundary/` | the hook, the chokepoint, the checker lane, the pre-flight surface, the review queue |
| `src/retinue/ledger/` | touchpoint models and the write barrier, the store contract with its in-memory reference, the Postgres adapter, the projection, the rendered block, outcomes |
| `src/retinue/matching/` | `integrate.py`, the one caller of the imported matching staging |
| `src/retinue/evals/` | the ranking evaluators, the block-stripped control, the frozen-verdict replay |
| `src/retinue/synth/` | the seeded synthetic roster generator |
| `scripts/` | the three capture scripts, all live-lane and flag-gated |
| `fixtures/` | payloads, drafts, verdicts, gold rankings, and the documents the research specialist reads |
| `tests/` | one directory per package above, plus the fixture-provenance, audit and plan-sync tests at the top level |
| `tools/` | `battery.sh` and `fleet_audit.py` |
| `docs/` | the architecture proposal, and under `superpowers/` the design spec and the implementation plan, one file each |
| `vendor/` | the chaperone wheel and `PROVENANCE.md` |
| root | `schema.sql`, `docker-compose.yml` for the Postgres lane, `pyproject.toml`, `requirements.txt`, `.github/workflows/ci.yml`, `CLAUDE.md` |

One file this document discusses is deliberately not in this table: `tools/banned_tokens.txt`,
untracked and machine-local, for the reason the battery section gives.

## What retinue imports

The boundary library `chaperone`, as a vendored wheel at `vendor/chaperone-0.1.0-py3-none-any.whl`
whose origin is recorded in `vendor/PROVENANCE.md`. Its source is
`https://github.com/EsraaKamel11/chaperone`, so the claim below that this repository adds no policy
code of its own is one a reader can check against the library rather than take on trust. Never
`pip install chaperone`: that PyPI name belongs to an unrelated package. The wheel ships the
library's `src/` only, so the library's own purity-audit tooling and its test suite do not travel
with it and this repository does not imply they do. This repository adds no policy code of its own;
the import surface it depends on is the declared contract in spec section 6.1, and the substitute
for a purity audit here is import discipline enforced as AST rules (`tools/fleet_audit.py`).

The division of labour is one sentence each way: chaperone decides, retinue runs. The two
repositories are a pair, built together: chaperone owns every policy predicate, the
deterministic engine, the checker contract, the audit gateway and the matching staging; this
repository owns the fleet that consumes them, and the library's own README names this fleet as its
consumer, so the pairing is stated from both sides. The wheel's provenance is verified, not
asserted: a rebuild from the named source commit reproduced every packaged file, differing only in
the build tool's own version stamps (`vendor/PROVENANCE.md`).

## Where the act boundary sits, and why not `pydantic-ai-harness`

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

## The ledger

`schema.sql` is idempotent and carries three tables. It is the whole migration story for P1: every
statement reaches an existing database by adding what it finds missing, with one destructive
exception it names.

| Table | Holds | Mutability |
|---|---|---|
| `touchpoints` | every fact the fleet learns, one row per event, across five kinds: `contact`, `stated_check_size`, `pass_reason`, `identity`, `sent` - each carrying `occurred_at`, when it was true in the world, and `recorded_at`, when the system learned it | append-only, enforced by two triggers |
| `outcomes` | resolved outcome signals: `replied`, `meeting_booked`, `check_written` | updatable, and the absent trigger is the decision |
| `review_queue` | the durable half of escalation: queue name, the `Handoff` as JSONB, enqueued time | insert only today; `resolved_at` is declared and nothing writes it |

Append-only lives in the database rather than in prose: a row-level trigger before UPDATE or
DELETE, and a statement-level trigger before TRUNCATE, because a row-level trigger cannot fire on
TRUNCATE and without the second one `TRUNCATE touchpoints` quietly empties an append-only ledger.
`outcomes` carries no such trigger, because an outcome resolves over weeks and a later resolution
updates its row: `occurred_at` and `observed_at` diverge structurally. The ledger stays immutable
and the outcome stays correctable.

There is no record write. `project_record` and `build_act_context` are pure projections over the
touchpoint stream, and `None` from either means the store could not be READ, which is a different
fact from an empty stream and is treated as fail-closed. Zero-because-new and
zero-because-the-query-failed never reach the guard as the same value.

The store contract is a Protocol of two methods (`ledger/store.py`): `append`, returning a bool where False means the row was
dropped, and `touchpoints_for`. The in-memory reference and the Postgres adapter pass the same
tests, both snapshot on write and on read so no holder of a returned row can rewrite history
through it, and the index `idx_touchpoints_investor_seq` is ordered for the query the adapter
actually issues, `WHERE investor_id = %s ORDER BY seq`, which is what the Postgres lane's two plan
assertions hold it to.

Money binds at the write barrier and not at read: amounts are Decimal carried as strings, floats
are refused, non-finite values are refused, and a value whose plain notation would not fit the
rendered block's default budget is refused at construction, since a guard that measures after the
cost it guards against is not a guard. The width guard is arithmetic on `as_tuple`, not
formatting: measuring by formatting would pay exactly the cost it exists to prevent
(`ledger/models.py::plain_width`). The rejected alternatives are on the record: degrading at
read is a false fact through the most-trusted component, and raising at read is a fourth state in
a tri-state contract (`ledger/models.py`). The idempotency key is globally unique rather than
per investor, which is the property the chokepoint's step 6 boolean depends on.

Outcome attribution is investor-level, pinned: `last_touch_attribution` filters by kind and by
time, never by `mandate_id`, so an outcome on one mandate can attribute to a touch on another for
the same investor - deliberate at this size, and pinned by
`test_attribution_is_investor_level_and_crosses_mandates_by_design` in
`tests/ledger/test_outcomes.py` rather than left to be inferred. Which signal counts is the
`OutcomeConfig` parameter Configuration names; the weights update that would read it stays a
Designed row.

## Matching and the evals

**Matching never invents.** `candidate_for` consults the projection first and honours its `None`
before reading anything else: a store that cannot be read raises `StoreUnavailable` rather than
handing the ranker a candidate whose zero relationship state is indistinguishable from a failed
query. The ledger's identity fact outranks the roster row on jurisdiction, and only in that
direction - reversed, a stale roster row would readmit someone the ledger places outside consent.
`days_since_touch` is `None` for never-touched, never `0`, which would read as touched today.
Staging is the imported `chaperone.matching` pipeline unchanged: hard filters, then relationship,
then similarity INSIDE the filtered set, with the similarity score an injected callable.

**The ranking evaluators are floats carrying their own names** (`evals/ranking.py`, on
pydantic-evals): `hit_at_3: 1.0` and `mrr: 0.5`, never booleans and never a bare score. MRR is the
reciprocal rank, and the suite probes ranks 2 and 3 because a reciprocal rank that quietly became
"did it appear at all" reports an unchanged headline number while the ordering it claims to
measure has stopped being measured. The needs-verification bucket is dropped from scoring, and
dropping it is the point: a metric that counts blocked candidates rewards exactly the ordering the
eligibility layer refuses.

**The rendered block is a contract, and the control eval attacks it** (`ledger/block.py`,
`evals/control.py`). `render_block` raises rather than truncating or sanitising - a partial block
is the fabrication vector arriving through the most-trusted component - and refuses any value
carrying a line break `splitlines` recognises, an alphabet far wider than `\n`: eight further
characters survive a JSON round trip and would forge a block line in the reader. The
block-stripped control then re-asks ONLY the questions whose answers live in block-only fields
against a context with the block stripped; at least one must fail, and a strip that removes more
or less than exactly the block is caught by its own test rather than argued about.

**The LLM judge ran once, live, and is frozen** (`evals/frozen.py`,
`fixtures/verdicts/judge_verdicts.json`). Calibration and discrimination are separate checks with
separate names and units: whether the judge knows what it knows is not the same question as
whether its score ranks violations below compliance. What those two frozen verdicts do and do not
establish is owned by [fixture provenance](#fixture-provenance-limit).

## Decisions

Eight, each with the alternative that was rejected and where the rejection is held. None is
invented for this file; each is recorded at the site it governs.

1. **The checker runs at the chokepoint, never in the hook.** Rejected: checking in the
   `PreToolUse` hook. A hook that raises fails OPEN by platform contract, so the hook only routes
   and delegates; the checker runs inside the send-tool body, where a failure is a denial
   (`boundary/hook.py`, `boundary/send_tool.py`).
2. **Detection over prevention for the unrecorded act.** Rejected: claiming the idempotency key
   before the act - `append` is already an atomic test-and-set, so it was genuinely available.
   Measured and declined: a claim row could never be resolved (append-only store, no pending
   status), so claim-first trades the tri-state away, and a crash between claim and act burns the
   key. The shipped guarantee is exact: no duplicate is silent, and a human holds one work
   item per act (`boundary/send_tool.py`).
3. **Durable write first, in-memory second.** Rejected ordering: in-process first, which loses the
   escalation with the process while one live object believes it routed. A crash between the
   shipped halves leaves a row a restart rebuilds (`boundary/review_queue.py`).
4. **Frozen captures over retakes.** Rejected: giving the P1 smoke a capture-only send-free
   options shape so it could run again. A capture from a session shape nothing in the tree
   constructs would be evidence about a session the fleet does not run; the script now refuses
   every invocation instead (`scripts/capture_smoke.py`).
5. **The checker's confidence routes nothing.** Rejected: a third routing signal from the model's
   self-estimate, one field access away and witnessed sitting in the payload. A boundary routed on
   a model output is a function of the thing it exists to bound. Enforced by an AST census of
   touched names, not a text search (`boundary/preflight.py`).
6. **The routing table is a tuple of pairs, not a dict.** Rejected: hashing lookup, which raises
   TypeError on a malformed non-string `agent_type` and reports the router as the failure. The
   tuple walk answers "ask" with a reason naming the payload. Both fail closed; the difference is
   what the human reads (`boundary/hook.py`).
7. **Money is Decimal, carried as a string, refused at the write barrier.** Rejected: degrading at
   read ("not stated" for a value that exists and cannot be read - a false fact through the
   most-trusted component) and raising at read (a fourth state in a tri-state contract). Floats
   are refused, not coerced (`ledger/models.py`).
8. **The boundary is vendored as a wheel, not declared as a dependency.** Rejected: the bare PyPI
   name, which installs an unrelated dead package. The wheel's provenance is recorded, and a
   rebuild from the named source commit reproduced every packaged file byte for byte, apart
   from the build tool's own version stamps (`vendor/PROVENANCE.md`).

A ninth is big enough to keep its own section: [where the act boundary sits](#where-the-act-boundary-sits-and-why-not-pydantic-ai-harness).

Five runtime dependencies (`pydantic>=2.7`, `pydantic-ai>=2.23`, `pydantic-evals>=2.23`,
`psycopg[binary]>=3.1`, `claude-agent-sdk>=0.2.130`) plus the vendored wheel, and each choice has
a reason on the record rather than a default.

| Choice | Why |
|---|---|
| The SDK as a default dependency | The default lane constructs `ClaudeAgentOptions` as data, which needs the package while spawning nothing. This is the distinction the corrections section holds: nothing needs to be running, not nothing is installed. |
| pydantic-ai at the specialist seam | Each specialist is one module emitting both artifacts, the SDK `AgentDefinition` and the pydantic-ai `Agent`, from shared constants, with parity asserted on the same prompt object rather than on equal strings. The offline doubles drive the specialist tests. |
| Not `pydantic-ai-harness` | Argued in full above: the version constraints overlap, so this is a design decision and not a compatibility excuse. |
| psycopg3 and one idempotent `schema.sql` | `bootstrap(dsn)` in `ledger/postgres.py` applying one file is the whole migration story, which is also the managed-Postgres story. No sqlite anywhere: a second SQL dialect is a second implementation of the schema under test. |
| An event-sourced ledger in plain Postgres, not an event-store product | Every fact is a touchpoint and the record is a projection, but the machinery is one boring dialect: append-only is a trigger, durability is a table, and the tri-state and the plan assertions stay checkable in the same lane that runs everything else. |

The design spec's section 10 lists nineteen rejected alternatives, each with its reason and none
silent, among them policy-as-data, a tool-registry table, retry-with-backoff at the chokepoint,
token buckets, prompt caching, a hand-rolled agent loop, and a graph checkpointer for escalation
durability. Two of those refusals are load-bearing enough to restate here, because a later reader
is likely to propose them again: a token bucket in place of the contact limit is a different object
under the same name, and retry-with-backoff at the chokepoint contradicts denials that are
terminal by design - and past the act, it is the retry that sends twice.

## Install

Windows first, because this repository was authored and first run on Windows; CI runs the same
commands on ubuntu.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

Order matters and `requirements.txt` encodes it: the vendored wheel first, then this package as an
editable install with its dev extra. Python >=3.11. For the Postgres lane locally:

```bash
docker compose up -d --wait
export RETINUE_PG_DSN=postgresql://postgres:retinue@localhost:55432/retinue
python -m pytest
```

Port 55432, not 5432, because a locally installed Postgres commonly holds the default port. The
compose file pins `postgres:16.4`, the same tag CI's service container runs.

## Configuration

There is no settings module and no `.env` file. Four environment variables are the entire
configuration surface, each compared where it is read:

| Variable | Read by | Effect |
|---|---|---|
| `RETINUE_PG_DSN` | the test suite only (`tests/ledger/conftest.py`, `tests/ledger/test_postgres_enforcement.py`, `tests/boundary/test_review_queue.py`), which hands it to `bootstrap`, `PostgresStore` and the durable sink; nothing under `src/` reads the environment | Set: the Postgres lane runs against it. Unset: those tests skip with a printed reason that says how to start one. |
| `RETINUE_PG_REQUIRED` | the same three test files, against the exact string `"1"` | Turns a skip into a failure - the negative control that keeps the lane from being vacuous in CI. |
| `RETINUE_LIVE` | all three `scripts/`, against the exact string `"1"` | Gates the live capture lane. Unset, every script prints that it is manual and keyed, and exits. |
| `ANTHROPIC_API_KEY` | `scripts/judge_capture.py` via pydantic-ai's provider | The judge capture takes this or nothing: the provider raises when it is unset, and the Anthropic SDK's further fallbacks are unreachable from that path (source-cited at pydantic-ai 2.23.0). |

The one piece of runtime configuration that is code rather than environment is
`OutcomeConfig(active_signal="replied", attribution="last_touch")` - which outcome signal counts
is a constructor argument, validated against `OUTCOME_SIGNALS`, because it is a product decision
this repository declines to hardcode.

## Usage

Every entrypoint, with what it actually does:

| Command | What happens |
|---|---|
| `python -m pytest` | The default lane: 241 passed, 9 skipped at this commit, on a fresh clone, offline. The 9 are the Postgres lane waiting on a DSN. |
| `bash tools/battery.sh` | The doc-and-hygiene gates, then the audit, then the suite with a floor on the PASS count. Every gate proves it can still fire before its zero is believed. |
| `python tools/fleet_audit.py` | The AST import audit alone: exits 0 silent, or prints findings and exits 1. |
| `docker compose up -d --wait` | Local Postgres 16.4 for the lane below. |
| `RETINUE_LIVE=1 python scripts/judge_capture.py` | Re-judges the fixture drafts live and OVERWRITES the frozen canon - a deliberate act, not a refresh. |
| `RETINUE_LIVE=1 python scripts/demo.py` | The P4 live demo; has run once, and its capture is frozen. Exit 0: ask captured. Exit 1: the send tool was never offered, nothing was demonstrated, nothing written. Exit 2: offered, but the conversation lane made no send. |
| `python scripts/capture_smoke.py` | Refuses every invocation, by design - see [the three lanes](#the-three-lanes). |

## The three lanes

### Default lane

`python -m pytest`. No daemon, no network, no key, on a fresh clone. At this
commit: 241 passed, 9 skipped, all 9 for the Postgres lane below. No second `-q`: `pyproject.toml`'s
`addopts` already carries one, and `-qq` deletes the summary line that both CI and the battery
read. The lane holds the options-shape tests, the hook callback replayed against captured payloads,
the specialist tests under pydantic-ai's own offline doubles, the ledger contract tests against an
in-memory reference store, the matching integration against the imported staging, the ranking
evaluators over a hand-judged gold shortlist across the seeded synthetic roster, the frozen judge
replay, the block-stripped control, the chokepoint's ordering and denial tests, the pre-flight
two-signal routing, the review queue's in-memory half, and the audit's own planted-violation tests.
`.github/workflows/ci.yml` runs it on 3.11 and 3.13, then the battery. It first ran on
2026-08-12, green on both versions, so the 3.11 half of that matrix stopped being a claim about a
version no one had executed this suite on.

### Postgres lane

Keyed on `RETINUE_PG_DSN`. Unset, it skips with a printed reason. Set, the same
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

> **This lane first executed on 2026-08-12, in CI, and went green on 2026-08-13.** There is no
> Docker on the machine this was built on and an ephemeral cluster would not start there, so
> until that run every Postgres statement in this repository was code that had been read and never
> run. Four runs as of 2026-08-14. The first two each reddened one plan assertion: the Sort clause
> the paragraph above holds, at 249 collected, then the split-off ordering test on a seed that let
> the predicate select the whole table, 1 failed and 249 passed of 250 collected. The re-seeded
> ordering test's first run came on the morning of 2026-08-13 and was green, the planner choosing
> the index path at half a percent selectivity, 250 passed in this lane; the 2026-08-14 run
> repeated it, 250 again. An earlier version of this paragraph counted two runs and called that
> first run pending: two is the count of reddens, and the run it awaited had already gone green.
>
> Locally: `docker compose up -d --wait`, then export the DSN from the trailing comment in
> `docker-compose.yml` (port 55432, because a locally installed Postgres commonly holds 5432).

### Live lane

`RETINUE_LIVE=1`, keyed, manual, flag-gated, and never in CI. Live runs are capture
runs: payloads are recorded once, stamped with the versions that produced them, frozen under
`fixtures/`, and replayed by the default lane forever. There are three capture scripts and they are
in three different states, which is the whole reason they are listed one by one:

| Script | Command | State |
|---|---|---|
| `scripts/capture_smoke.py` (P1) | none, see below | Has run. Its payloads are frozen under `fixtures/payloads/` and the script now refuses every invocation. |
| `scripts/judge_capture.py` (P2) | `RETINUE_LIVE=1 python scripts/judge_capture.py` | Has run once (2026-08-12). Its verdicts are frozen and replayed; running it again overwrites that canon, which is a deliberate act and not a refresh. |
| `scripts/demo.py` (P4) | `RETINUE_LIVE=1 python scripts/demo.py` | Has run once (2026-08-12). The send tool's offer was asserted in the live session before any gating claim, the conversation send fired the hook's ask, and the tool body was reached zero times. Its capture is frozen and replayed; running it again overwrites that canon. |

#### The P1 capture is frozen, and there is no command that retakes it

`scripts/capture_smoke.py` refuses to construct a session in which any send tool exists, which was
the point of the run: its payloads are the evidence that nothing in that session could ask. P4 then
widened the session roster so that the demo could show a send being gated in a session that offers
one, so the smoke's guard now fires on every invocation and prints `not a send-free session`. The
guard is right and the roster is right. What that leaves is a script whose session no longer
exists, and the choice was between giving it a capture-only send-free options shape and declaring
the capture frozen. It is frozen, because `fixtures/payloads/` records the P1 topology as it stood,
a retake under today's ceiling could not reproduce it, and a capture taken from an options shape
nothing else in the tree constructs would be evidence about a session the fleet does not run. The
script stays as the record of how those payloads were taken. A missing payload is therefore a
broken checkout, not a lane awaiting its turn, and the tests that read them fail rather than skip.

The judge capture and the demo have now run, once each, on the same day. The demo's output,
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

`docs/superpowers/plans/2026-08-10-retinue-implementation.md`, Task 11, embeds this script verbatim, and a test in the default lane holds the
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

## The one live demo run

The demo (`scripts/demo.py`) ran once, on 2026-08-12, and the run is reconstructable from its
frozen artifacts rather than from memory. What it did, in order:

1. **Built the real topology.** `build_options` with a recording hook, then the in-process SDK
   MCP server added by `dataclasses.replace` - the server name DERIVED from the gated spelling
   `mcp__retinue__send_message`, so the tool the CLI offers is the tool the hook gates by
   construction. The tool body performs no act: no transport, no gateway, no `attempt_send`. It is
   a capture instrument.
2. **Asserted the offer before any claim.** The send tool must appear in the session's
   `system:init` tool list first, because containment is never demonstrated by the absence of the
   thing being contained: a session where no send tool was offered produces the same silence as
   one where it was offered and held. Had the offer been absent, the demo would have aborted
   (exit 1) and written nothing; exit 2 is the offered-but-no-send case, re-run.
3. **One query:** "Use the conversation agent to send inv-demo a one-line follow-up."
4. **The gate held it.** The conversation agent proposed a send; the hook answered "ask"; the
   session captured seven hook payloads; the tool body was reached zero times.
5. **Wrote the canon.** The ask payload - selected on its OWN routing facts (`agent_type` is
   `conversation`, tool name in the gated set), never on the hook's answer, so the replay test
   does not read its expectation out of the decision it checks - became
   `fixtures/payloads/captured_ask.json` (exit 0), stamped and with its redactions declared in its
   own meta:

```json
{
 "meta": {
  "captured": {"sdk": "0.2.130", "cli": "2.1.222"},
  "redacted": ["auto: user path segment replaced with <user>", "..."]
 },
 "payload": {
  "agent_type": "conversation",
  "hook_event_name": "PreToolUse",
  "tool_name": "mcp__retinue__send_message",
  "tool_input": {"body": "Checking in \u2014 happy to share an update or answer any questions whenever that's useful."}
 }
}
```

   The body ships as JSON's ASCII escape, byte-exact from the run; the identifiers are
   shape-preserving placeholders, declared in `meta.redacted` because an undeclared edit is what
   makes a capture unusable as evidence.
6. **The default lane replays it forever.** `tests/boundary/test_ask_replay.py` drives the same
   `pre_tool_use` with the captured payload and asserts the ask, and it fails rather than skips on
   absence, because a tracked capture that is missing is a broken checkout.

One run of one session: evidence that the ask arm holds unattended, not a distribution over runs.

**Evidence, not logging.** There is no logging framework anywhere in this repository, and that is
stated rather than dressed up: the ledger is the durable record of what happened, the imported
audit trail records that a gate decided, the review queue holds what was held back and why - so
somebody holding the log and not the queue knows a redirect happened and cannot read what was
redirected, which is the privacy split the design wants - and the stamped captures under
`fixtures/` are the run history. Each of those is queryable and testable, which a log line is not.

## What the live captures settled

Three live capture runs of the P1 smoke, at claude-agent-sdk 0.2.130 with bundled CLI 2.1.222. The
fixtures kept from those runs are all from one session (the captured P1 family under
`fixtures/payloads/`, which now also holds the P4 demo's ask from a second session), and they are
the frozen capture described above. What they settled, from real payloads rather than by reasoning:

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
short: the P1 session payloads, and since 2026-08-12 the judge verdicts and the demo's captured
ask. **Over hand-authored fixtures, every number this repository produces is a demonstration of a
protocol, not a measured claim about model behaviour.** Both halves of that sentence are
load-bearing: the first says how those fixtures were made, and the second says what follows, which
is that no figure computed over them may be read as an observation of a model. The gold rankings
and the drafts' ground truth are in that class.

The judge verdicts are the one captured fixture a computed FIGURE rests on, and the crossing is
dated: `scripts/judge_capture.py` ran once on 2026-08-12, so the verdict column is a captured
judge's answer, frozen at the library version and model id stamped in the fixture's own `meta`. The
drafts and their ground truth are still one author's judgment. What the capture bought is stated at
its exact size: calibration and discrimination are now a captured judge read against one author's
labels over two cases, and the judge marked the compliant draft at confidence 0.55, under the 0.7
floor, so the calibration figure divides by a single confident verdict. Raw agreement is two of
two, pinned separately in the test that reads the file. A real judge inside a small protocol
demonstration, not a measurement at scale; re-running the capture overwrites the canon, which is
why it is manual and flag-gated.

Synthetic mandate and check-size figures are invented and resemble no real firm's published ranges.
Each fixture declares exactly one provenance in its own `meta` block, and a test enforces that,
including that a capture carrying an operator's home directory path has to declare the redaction.

## What this repository does not claim

Limits are properties of the system, so they get the same precision as the features.
`docs/architecture-proposal.md` section 17 is the source of this list; where a bullet there and this
file's run history disagree, the run history is newer and the bullet below carries what ran.

- **No agent has ever driven the chokepoint.** `attempt_send` has no caller outside its own module
  and tests, and the checker lane, the pre-flight surface and the review queue are reachable only
  through it. The demo's live crossing stopped at the hook's ask, above the chokepoint,
  deliberately. The composed fleet's strong lane is unreachable as designed until the approval
  bridge exists, and the only path to a permitted send today is a caller inventing evidence.
- **Numbers over hand-authored fixtures are protocol demonstrations**, one author's, and stay so.
  The one captured crossing is stated at its size above: two cases, one confident verdict, and the
  drafts' ground truth is still one author's labels, so even that figure is a judge read against one
  author's opinion rather than a benchmark.
- **Executed and green stayed different claims for the Postgres lane, and the distinction is kept**
  even now that it holds both. Four runs as of 2026-08-14, the first two red on a plan assertion,
  green since 2026-08-13. Both reds were seed findings rather than schema faults, which is a
  narrower result than a green lane suggests on its own.
- **The live captures are one machine's, at one version.** Payloads captured under one operator's
  ambient configuration are not canonical whatever they show, the session is only partially
  hermetic, and the `strict_mcp_config` field that would close the MCP half is source-cited at
  0.2.130 and not set.
- **The demo demonstrated the gate before the act, not the act.** Its one run asserted the offer,
  captured the ask, and reached no tool body; the body performs no outbound act by design, and the
  main-thread reachability asymmetry is stated in the topology's own comment rather than smoothed
  over.
- **Two enforcement gaps are held by nothing but their own disclosure.** `attempt_send`'s return
  union is enforced by no type checker, so the `UnrecordedSend` guarantee is that no duplicate is
  silent and never that nothing is sent twice; and the banned-token pass has no standing
  enforcement outside the authoring machine, a cost the battery states where it is decided.
- **The fleet audit sees imports, not semantics.** Inline policy logic importing nothing would pass
  it, and the audit's own main block says so. The claim is discipline made conspicuous, not absence
  demonstrated.

## Which source is authoritative

Three documents sit in `docs/`, and they answer different questions.

| Document | Answers | Authority |
|---|---|---|
| `docs/superpowers/specs/2026-08-10-retinue-design.md` | what the system is meant to be, per module, with the rejected alternatives and the evidence tiers | design intent: where this file and the spec disagree about intent, the spec wins |
| `docs/architecture-proposal.md` | why the architecture is shaped this way, argued end to end for a reviewer, and the six Designed rows argued one by one | the argument, not the status; it cites the tree by file and line |
| `docs/superpowers/plans/2026-08-10-retinue-implementation.md` | how it was built, task by task, tests first | the build record; its Task 11 section embeds `tools/battery.sh` verbatim and `tests/test_plan_sync.py` holds the two byte-identical |

Build status runs the other way. The spec's section 12 table is the seed this file's
Designed-vs-Built table replaced, and it still reads as it did the day the spec was written, so on
what is actually built the table at the bottom of this file is the authority.

## Run history

Two things in this file were built and, as of 2026-08-12, had never executed anywhere: the Postgres
lane and CI itself. That list is now empty. Later the same day the first push gave this repository a
remote, `.github/workflows/ci.yml` ran, and the Postgres lane executed inside it; each sentence
that carried the never-executed claim now carries what its first run did instead. Has-run
and is-green stay different claims, and Lanes keeps them apart; on 2026-08-13 they stopped
differing here: CI's default lane went green on 3.11 and 3.13, and the Postgres lane, red twice
on its plan assertions, went green on its third run and again on its fourth. The judge
capture and the live demo had left the list earlier on 2026-08-12: each ran once, and their
outputs are the frozen fixtures the default lane replays. The dates on these sentences are
load-bearing rather than decorative: publishing this repository was itself the act that made the
old ones stale, and sentences written to be true by naming when they were true get replaced by
what the run showed, not reworded to a present that moves.

CI is the one that was nearly missed, and naming it was the point of the list. An earlier version
left CI off it, which invited the reading that everything else had run. Until the push on
2026-08-12 this repository had no remote, so `.github/workflows/ci.yml` had never executed and
nothing had been run on 3.11 by anyone; CI's first run retired both halves of that sentence at
once.

## Corrections this file carries

On the opening paragraph's two claims about the default lane:

> Both halves of that sentence were looser before, in the two places a skeptic would press first. It
> said the default lane is "dependency-free", against five declared runtime dependencies including
> `psycopg[binary]`; the claim is that nothing needs to be RUNNING, not that nothing is installed.
> And it said "nothing in CI contacts a model or a network", while `.github/workflows/ci.yml` runs
> `pip install -r requirements.txt` on every job. The job reaches PyPI. No test reaches anything.

## Roadmap

The six Designed rows are the roadmap, ordered by leverage. Each is a named absence with a shape,
a row, a sketch or a parked test, rather than an idea. `docs/architecture-proposal.md` section 15 argues each one at
length: what exists, what building it takes, what risk it retires, and what evidence would count.
That last clause is the entry condition, so a row flips to Built on evidence and never on effort.

1. **The approval bridge** (section 15.1). A mint, a transport, and a validation stronger than
   presence, all boundary-side because none of it may be policy code. The natural mint is the
   review surface already here: `review_queue.resolved_at` is declared and unwritten, so a human
   resolution can mint a single-use token bound to the draft's idempotency key and body digest.
   It retires the standing incentive for a caller to invent evidence, and it is the same event as
   `attempt_send` gaining its first non-test caller.
2. **Tier from the ladder** (section 15.2). `boundary/` imports `chaperone/gates/ladder.py`,
   declares per-surface ceilings in the topology's data style, and feeds `build_act_context`'s
   `tier` from a constructed `LadderState` rather than a literal. The library's constructor
   refuses a state above its ceiling, so the fleet inherits an unconstructable-overreach property
   instead of building one. Promotion stays driven by nothing until human-review outcomes exist to
   drive it, which is the library's own refusal of self-promotion, inherited deliberately.
3. **The sliding-window contact limit** (section 15.3). Every touchpoint already carries
   `occurred_at`, so a windowed count is one query over recorded data. It retires burst contact
   inside the lifetime cap: a cap of N says nothing about N sends in an afternoon. The windowed
   count is fed explicitly rather than substituted into the lifetime predicate, which would change
   that predicate's meaning without changing its code.
4. **Contested-quantity rendering** (section 15.4). The contract can hold a conflict and nothing
   renders one. A brief renderer groups claims by `quantity_key`, shows both values with both
   sources under a Contested marker, badges a single-source quantity as thin support, and holds the
   marker text as a machine-checked contract the way `BLOCK_HEADER` is held. A conflict held in
   data and invisible in prose is arbitration by whoever reads the prose next.
5. **The weights-update sketch** (section 15.5). It needs an upstream seam first: the staging's
   blend weights are module constants in the imported library, so an update rule needs `rank` to
   accept weights as arguments. That is a library change to request and not a fork to make, since
   a second ranking implementation here would be the reimplementation this repository forbids
   itself. Then a deterministic rule at this volume, with every adjustment written as its own
   record so the weights have provenance the way the fixtures do. Metrics are reported and never
   asserted: a weights update that had to pass a metric gate would be an eval score promoted to an
   authorization.
6. **Store unification** (section 15.6). The one row whose argument may be to stay Designed. The
   imported hash chain is tamper-evidence for gate decisions and the ledger is relationship state,
   and the spec answers why two stores before this row asks whether they should be one.

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
| Ledger schema, projection, `ActContext` feed | **Built (P1)** - `schema.sql`, `src/retinue/ledger/`. The in-memory contract lane is green; the Postgres half first executed in CI on 2026-08-12 and went green on 2026-08-13, holding through the 2026-08-14 run (see Lanes). |
| Rendered block renderer (budget + completeness raises) | **Built (P1)** - `src/retinue/ledger/block.py` |
| Live capture smoke + payload fixtures | **Built (P1)** - `scripts/capture_smoke.py`, `fixtures/payloads/`, plus the seeded roster generator at `src/retinue/synth/rosters.py`. The capture is frozen and the script refuses every invocation (see Lanes). One gap it names itself stays unproduced: the `background`-unset half of the background evidence pair, which needs a run against a deliberately-unset definition. The "ask" fixture moved to the P4 demo, which owns it. |
| Matching integration + ranking evaluators + OutcomeRecord | **Built (P2)** - `src/retinue/matching/integrate.py`, `src/retinue/evals/ranking.py`, `src/retinue/ledger/outcomes.py` |
| Block-stripped control | **Built (P2)** - `src/retinue/evals/control.py` |
| Judge capture + frozen-verdict replay | **Built (P2)** - `scripts/judge_capture.py`, `src/retinue/evals/frozen.py`. The capture ran once (2026-08-12); the verdict set is captured, stamped in its own meta, and replayed by the default lane. Two cases with one under the confidence floor: real-judge evidence at protocol size, not a measurement at scale. |
| Drafting agent + chokepoint wiring + pre-flight review | **Built (P3)** - `src/retinue/specialists/drafting.py`, `src/retinue/boundary/send_tool.py`, `src/retinue/boundary/checker_lane.py`, `src/retinue/boundary/preflight.py`. `attempt_send` has no caller outside its own module and its tests, which is stated rather than left to be found. The checker lane, the pre-flight surface and the review queue are reachable only through it, so they have no production caller either. |
| Durable review-queue table (escalation persistence) | **Built (P3)** - `src/retinue/boundary/review_queue.py`, `schema.sql`. The in-memory half is green; the durable half is Postgres, first executed in CI on 2026-08-12, and green on 2026-08-13 and 2026-08-14 (see Lanes). |
| Conversation agent + live demo | **Built (P4)** - `src/retinue/specialists/conversation.py`, `scripts/demo.py`. The demo ran once (2026-08-12): the send tool's offer was asserted in the live session, the conversation send fired the hook's ask, the tool body was reached zero times, and the captured ask is tracked and replayed by `tests/boundary/test_ask_replay.py`. The reason a human is shown for a gated send is now asserted over a hand-authored payload and a captured one. |
| **Ask-to-chokepoint approval bridge** | **Designed only, and it is the seam the two lanes meet at.** Nothing mints, transports or validates an approval token. `build_act_context` defaults it, the imported check is presence-only, and its violation class is terminal, so a composed system denies every send unless a caller invents a token - which would reduce "a human approved this act" to "the caller passed a non-None string". An SDK permission grant hands the tool body no evidence it can carry, so this is an unanswered design question rather than unwritten wiring. The spec asserted this as sourced until 2026-08-12. |
| **Tier from the ladder decision** | Designed only - `chaperone/gates/ladder.py` ships in the wheel and nothing here imports it. Tier arrives as a bare int parameter. |
| Contested-quantity rendering + thin-support badge | Designed only - the contract carries `quantity_key` so a conflict can be held, and the prompt instructs the model to group by it, but nothing renders a Contested quantity or a thin-support badge. Annotate-not-arbitrate is the commitment; surfacing the annotation is unbuilt. |
| Weights-update sketch | Designed - `src/retinue/ledger/outcomes.py` carries the outcome-signal config parameter the sketch would read, and nothing updates a weight or a threshold from a resolved outcome. |
| Per-investor sliding-window contact limit | Designed (inherits the library's note) |
| Store unification (audit chain + ledger) | Designed note only |

## License

There is no license file, deliberately. This is a private repository shared for reading; no
open-source grant is made, and all data in it is synthetic.
