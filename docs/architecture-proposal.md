# retinue: an architecture proposal

**What this document is.** The single-document case for this system's architecture and the
proposal for where it goes next, written for a technical reviewer who has read the
[README](../README.md) and wants the design argued end to end - ideally after reading the sibling
proposal in the boundary library's repository, `docs/architecture-proposal.md` there, because this
system is the one that library's closing section describes. Everything here is a synthetic
scenario. Where the [design spec](superpowers/specs/2026-08-10-retinue-design.md) argues a
per-module decision, this page compresses and cites rather than repeating it. One rule governs
every sentence: built, designed and proposed are three different words, nothing that has never
executed is described as a run that happened, and every probabilistic quantity is either measured
with its denominator or not stated.

---

## 1. The problem, from first principles

The sibling proposal argues that an eval score is not an authorization, and builds a boundary
that keeps the two apart on a single draft. The problem this repository exists for sits one level
up: **a boundary library bounds the call it is handed, and nothing about a library makes anyone
hand it the call.** A product is not a draft; it is a fleet - agents that research counterparties,
draft outreach, and carry conversations - and a fleet fails by composition, not by defeating a
predicate. The send that ships unreviewed does not beat the checker; it is constructed one module
away from the chokepoint, with a tool roster the gate never saw, a subagent type the router never
named, and a context object somebody defaulted. Every one of those is an integration decision, and
integration decisions are exactly what a vendored wheel cannot make for its consumer.

The library also publishes its own limits, and three of them are work orders addressed to whoever
composes it. Its send-cap predicate reads a count that, in the library's own tree, no shipped path
derives and feeds - the input defaults to a permissive zero, so a re-attempt is unguarded there.
Its review queues are lists in memory whose own docstring says that going out of scope takes the
escalations with them. And its governance is per-draft, while a conversation is a sequence. This
repository is the consumer those sentences were addressed to: the ledger's projection feeds the
count (`src/retinue/ledger/projection.py:63`), a review queue writes the work item durably before
the in-process copy (`src/retinue/boundary/review_queue.py`, `schema.sql:59`), and the conversation specialist's
contract composes the library's own `Draft` so the thread rides inside what the checker reads
(`src/retinue/specialists/conversation.py:23`).

The shape of the system is the README's opening sentence and it is kept deliberately: one
orchestrator routing to three specialists, an evaluation harness that decides offline what agents
may do alone, and a matching engine behind them, over Python and Postgres, on the Claude Agent SDK
with pydantic-ai - the system a founding engineer would build for agent-run, relationship-led
outreach. The domain is synthetic; the composition problem is not specific to it.

**Status, stated before anything is argued, and dated because it moved under this page.** P1
through P4 are built: 241 tests pass and 9 skip by design on the authoring machine at this commit,
per the README's own count, all 9 keyed on an absent Postgres DSN. This page was drafted naming
four built things that had never executed anywhere. On 2026-08-12 three of them ran, and those
sentences are replaced throughout rather than softened: the judge capture ran once, the live demo
ran once, and CI ran, so the default lane is green on Python 3.11 as well as 3.13 and the Postgres
lane has executed, green since its third run on 2026-08-13 (section 10 carries the counts).
Nothing built here has never executed anywhere any more. Whether every lane is GREEN is a
different claim from whether it has RUN, and section 10 keeps the two apart. The README's
Designed-vs-Built table is the authority on build status; the spec's own section 12 calls itself
the seed that table inherited.

---

## 2. The two repositories, and the line between them

The whole design follows from one import: the deterministic boundary is `chaperone`, vendored as
a wheel at `vendor/chaperone-0.1.0-py3-none-any.whl`, and **this repository adds no policy code of
its own.** That sentence is the contract between the two trees, and it is held by machinery rather
than intention, because the failure it forbids - a second, slightly different implementation of a
predicate that already exists - is the failure that turns two repositories into two authorities.

**What the library guarantees, this repository consumes and never restates as its own.** The act
family is decided by pure functions over explicit arguments, and for that family alone the library
claims zero by construction; the claim is exactly as strong as the arguments those functions are
handed, which is why section 7's projection is the most load-bearing code this repository adds.
The other family's honest claim is a measured rate with its denominator, and the sibling
proposal's section 2 carries that split in full; nothing here re-argues it, and nothing here may
weaken it.

**What this repository may never reimplement is enforced as AST rules, not remembered.**
`tools/fleet_audit.py` walks `Import`/`ImportFrom` and `Constant` nodes over `src/retinue/` and
holds three named rules: only `boundary/` imports the gate and audit surfaces
(`tools/fleet_audit.py:8`, prefixes, so every submodule counts), `specialists/` imports no gate
module, and the send tool's name has a single home - the literal is constructed rather than
spelled in the audit itself (`tools/fleet_audit.py:9`) so the tool passes its own rule. The
audit's `__main__` block states its own limits out loud: every rule is import-shaped, so policy
logic written inline and importing nothing is invisible to it, and `tests/`, `tools/` and
`scripts/` sit outside its root (`tools/fleet_audit.py:53-59`). A clean run says no module outside
`boundary/` reaches the gate surface; it does not say the package holds no policy, and the file
says so itself.

**The wheel pins the contract, and the pin was verified rather than asserted.**
`vendor/PROVENANCE.md` records the source repository, the exact commit the wheel was built from,
and a 2026-08-12 rebuild that reproduced every packaged file byte for byte, differing only in the
build tool's version stamps. The import surface is enumerated in spec section 6.1: the library
had no published contract when this consumer wrote it down and verified it against the wheel's
source tree, and the library-side statement of record now exists, carried by the sibling
proposal's appendix. The PyPI name `chaperone` belongs to an unrelated package, which is why the
dependency is the wheel and the manifest deliberately omits the name (`pyproject.toml:6-8`).

**What does not travel is half the relationship.** The wheel ships the library's `src/` only: the
purity audit, the edit-time hook, the mutation sweep and the claims suite are siblings of that
`src/` and stay home. A consumer inherits the properties and must hold in its own tree anything it
needs held - the sibling proposal says exactly this in its closing section - and this repository's
substitutes are the fleet audit above, the battery (section 10), and the plan-sync test. The
sibling's closing section also describes this successor system as designed and not built; that
page predates this tree's build-out, the delta is recorded here rather than by editing a published
page, and the README's Designed-vs-Built table is what states how much of the design now stands.

---

## 3. Three enforcement surfaces, one act

One outward act is governed at three places, and the differences between them - what each can
reach, and which way each fails - are the architecture. A fourth surface annotates without
executing. The table is the spec's section 3 and 6 material, compressed:

| Surface | Where | Decides | Failure direction |
|---|---|---|---|
| Session roster | `SESSION_TOOLS`, `src/retinue/orchestration/topology.py:106` | which tools exist in the session at all; the CLI intersects every subagent's declared roster with it | **silent**: a name missing from the ceiling resolves to nothing and says so nowhere, with every options-shape test still green - held by a declared-roster-subset test, not by memory |
| PreToolUse hook | `pre_tool_use`, `src/retinue/boundary/hook.py:52` | routing by `agent_type`, then the imported deterministic lane on send payloads | the platform contract fails **open** - an exception escaping a hook does not block the call - so the whole body is guarded and every escape becomes an `ask` (`hook.py:89-90`) |
| Chokepoint | `attempt_send`, `src/retinue/boundary/send_tool.py:155` | the imported engine and the independent detector lane, bound to the reviewed draft, plus tri-state recording | denials terminal; a recording failure escalates and returns a distinct type, never a silent allow |
| Pre-flight | `annotate`, `src/retinue/boundary/preflight.py:57` | the would-be verdict over the full predicate set, with no execution | an annotation that errors **is** routing signal two; `routes_to_human` needs no working annotation to say yes |

**The roster is a ceiling, not a grant, and the distinction was measured.** The captured
`system:init` at CLI 2.1.222 settled three facts from real payloads rather than reasoning:
`tools=` restricts (five names declared, four resolved, no CLI default surviving),
`allowed_tools=` only pre-approves (read tools resolved into the session while the allow list held
the spawn names alone), and the spawn tool is one tool under two names by surface (`Task` in the
init roster, `Agent` in the `tool_use` blocks), which is why both are carried as data
(`topology.py:12`). The ceiling's real job is to drop what no agent needs: no Bash, no Write, no
Edit, no WebFetch, no WebSearch, so the research specialist cannot reach an outbound surface even
by inheritance. `background=False` is stated on every definition because an unset value is dropped
in serialisation and the CLI's own default then strips the subagent's tool list - containment
shown against a stripped roster would be containment of nothing (`topology.py:17-20`).

**The hook's decision table is total, and unknown fails toward the human.** `decide` is a tuple of
pairs rather than a dict on purpose - equality against each key never hashes, so a non-string
`agent_type` out of a malformed payload walks off the end of the table and takes the
unknown-agent ask instead of raising inside the router (`hook.py:27-45`, with the measurement in
the comment). `research` and `drafting` gate nothing because their rosters hold nothing outward;
`conversation` on either send spelling is `"ask"`; a main-thread send is `"allow"`, which routes
the payload *into* the imported deterministic lane rather than past it (`hook.py:75-76`). The one
asymmetry worth a sentence: conversation's send is held for a human before the call and the main
thread's is not. What stands behind the main thread is measured payload by payload, never claimed
of the lane: the one send-shaped payload measured refuses on both spellings, a clean bare-spelling
payload took the lane's allow answer, and the remaining gate on an allowed payload is the
chokepoint, which today has no caller outside its module and tests (section 4). `topology.py`'s
long comment carries each of those at its measured size.

**An allow is an abstention.** The hook returns `{}` rather than an explicit allow, because an
explicit allow would override the operator's own permission configuration in the permissive
direction, the one direction a gate may never move it (`hook.py:78-80`). And cancellation
propagates: converting `asyncio.CancelledError` into an ask would make the router un-cancellable,
and a torn-down call is not a call waiting on a human (`hook.py:81-88`).

---

## 4. The chokepoint, completed

`attempt_send` exists to make the library's chokepoint contract survive composition, and its
internal order is load-bearing (`send_tool.py:1-21`):

1. **The terminal guard runs before input validation.** Validation-first returns a readable error
   the model can correct and resubmit - a real second act. The ledger's idempotency key catches
   the duplicate row; this ordering catches the duplicate act (`send_tool.py:161-163`).
2. Input validation (`send_tool.py:164-165`).
3. **A `None` context denies before the engine runs.** The boundary-level class
   `boundary:projection_unavailable` is deliberately not a policy `ViolationClass` - this
   repository adds no policy code - and the denial never masquerades as a policy judgment: a
   sentinel context pushed through the engine would have reported a token failure, which is a lie
   about what happened (`send_tool.py:115,166-171`).
4. The imported `guarded_call`, engine and detector lane at the chokepoint, denials terminal via
   the imported `Handoff`, no resume round trip (`send_tool.py:172-173`).
5. **The sent touchpoint is tri-state.** `confirm` is a transport round trip; one that raises is
   the definition of an unconfirmable send, so the status is bound to `UNVERIFIABLE` before the
   guarded region and only upgraded by an answer (`send_tool.py:179-198`). An unconfirmable send
   escalates and is never guessed `CONFIRMED`. The payload carries byte counts, never text -
   message bodies live in the review queue's `Handoff`, not in the ledger.
6. **The recording check reads the store's own boolean on the same call that made the act.** A
   dropped row - cross-kind key collision, cross-investor key collision, or a store that raised -
   comes back as `UnrecordedSend`, a distinct frozen type with deliberately no `allowed`
   attribute: `True` is the state being distinguished from, `False` would invite a re-send, and a
   raise after an irreversible act arrives at a defensively-written executor relabelled transient,
   which drives the retry that sends twice (`send_tool.py:132-145` and the module docstring).

**Detection was chosen over prevention, and the refusal is argued against its strongest form.**
The store's `append` is already an atomic key-global test-and-set, so claiming the key before the
act needs no new API - the module docstring says so, then refuses it anyway: the store is
append-only with no update, the key is globally unique, and `DeliveryStatus` has no pending
member, so a claim row could never be resolved, and claim-first would trade the tri-state away
(`send_tool.py:32-57`). The guarantee that survives is stated at its true size: no duplicate is
silent and a human holds one work item per act - not "never sent twice".

**And the whole function has no production caller, which is disclosed where the capability is
claimed.** `attempt_send` is called from its own tests and nowhere else; the checker lane, the
pre-flight surface and the review queue are reachable only through it, so they have no production
caller either. The README's P3 row states this in the same cell that says Built. The scripted
driver is the chokepoint's first caller by design - the boundary lands before the agent it bounds
(spec section 9) - and the first agent caller is future work this proposal returns to in
section 15.

---

## 5. The checker lane and the review surface

The independent detector runs at the chokepoint and at the pre-flight, never in the hook, and its
default transport is a frozen replay: `scripted_transport` keys recorded results by the **exact
draft body**, and anything else fails closed as `CheckerUnavailable` - the scripted lane never
invents a clean (`src/retinue/boundary/checker_lane.py:147-152`).

Three load-time refusals keep the replay's keys honest, each demonstrated against this module
rather than supposed (`checker_lane.py:104-146`): a non-string body (a null key would answer
every prompt the extraction cannot read), a body carrying the prompt's own delimiters (the span
starts at the leftmost opener, so a counterparty writing one into the thread synthesises a key
out of their own text), and a body two rows share (the loser is answered by the winner's verdict,
silently). The extraction itself is greedy on purpose: the captured span always *contains* the
real body, so a forged closing delimiter can widen what is read and never narrow it - more
matches no row and fails closed, where a prefix would answer a long draft with a short row's
verdict (`checker_lane.py:28-33`). The residual is named as the design it is: a counterparty who
writes the opening delimiter into the thread holds a liveness lever - every draft in that thread
resolves to no row and denies - and that lever can stop a message and never cause one
(`checker_lane.py:82-91`).

The tier ordering is enforced by the import at construction: the checker runs `sonnet-tier`
against a `haiku-tier` drafter, and the imported constructor raises on a weaker pairing
(`checker_lane.py:16,155-156`; the vocabulary is the library's `MODEL_STRENGTH`). The library's
verdict types map onto the fleet's tri-state register in one function: a violation is an
EXCEPTION, a flag-for-review is UNVERIFIABLE (`checker_lane.py:158-161`).

**The review surface routes on two signals, and the model's self-rated confidence deliberately
routes nothing.** `annotate` runs the imported full-lane `pre_tool_use` over the draft - full
predicate set, detector included, no execution - and `routes_to_human` is a disjunction: the
annotation denied, or the annotation itself failed (`preflight.py:95-104`). The confidence number
is one field access away and sits unread: a model's estimate of its own certainty is a model
output like any other, and a routing rule built on it makes the boundary's behaviour a function
of the thing the boundary exists to bound (`preflight.py:8-14`). The refusal is pinned by a
census over the module's AST - the complete set of names each function touches, compared against
a written-out set - rather than by a text search, so a read added under any name reddens while
the docstring stays free to name the field it refuses to read (`preflight.py:16-43`).

---

## 6. The verification contract

The rule is inherited from the sibling and applied to a tree with less evidence, which makes the
tiers matter more, not less. **Invariants are asserted; probabilistic outcomes are measured,
reported, and never asserted.** Every load-bearing claim in the spec carries one of three
evidence tiers (spec section 2.4): deterministic-lane-witnessed, live-captured at version
(existentials only - "this happened at 0.2.130 / CLI 2.1.222"), or structurally unobservable at
the pinned version, named as a limitation rather than papered over. The one unresolved framework
corner - permission-rule evaluation order against a hook - is kept unreachable by design: the
fleet registers no allow or ask rules for the send tool at all.

**Every constraint test is shown to fail with the constraint removed, once, at introduction**
(spec section 2.4's inertness rule). A pinned-version suite is exactly the regime where a
silently ignored kwarg yields a green suite that tests nothing, and the red run is recorded in
the introducing commit's message rather than re-run forever.

The suite asserts effects, not invocations, and the sharpest instances are refusals to trust the
happy path: the block-stripped control must fail at least one question *and* strip exactly the
block (section 8); the durable queue's crash ordering is held by the write order itself
(section 7); and the hook's fail-open platform contract is answered by construction - every
escape converted to an ask - rather than by a test that the runtime behaves.

---

## 7. The ledger spine

The ledger answers the question the imported audit chain does not: what is the relationship
state, and can the boundary trust the number derived from it? The two stores' division of labour
is pre-answered in the spec (section 6, "why two stores"): the imported file-based hash chain is
tamper-evidence for gate decisions; the Postgres ledger is relationship state. Unification is a
Designed note, and section 15 argues it may deserve to stay one.

**Every fact arrives as a touchpoint, and the record is a pure projection.** There is no record
write: a newly stated check size is a touchpoint of kind `stated_check_size` and the record
derives (`src/retinue/ledger/projection.py:35-50`). Append-only is enforced in the database, not
in prose - an UPDATE/DELETE trigger, plus a statement-level TRUNCATE trigger because a row-level
trigger cannot fire on TRUNCATE and a truncated append-only ledger would empty in silence
(`schema.sql:26-38`). Every touchpoint carries `occurred_at` and `recorded_at`, so
bi-temporality is structural; `outcomes` deliberately carries no append-only trigger, because a
later-resolving outcome updates its row and never the touchpoint - the ledger stays immutable
and the outcome stays correctable (`schema.sql:39-53`).

**The tri-state is the boundary's safety property.** No-touchpoints and store-unreadable are
different facts with different types: `0` versus `None`. The projection returns `None` only when
the store raised `StoreUnavailable`, and the chokepoint's pre-check denies on it before the
engine runs (section 4, step 3). Zero-because-new and zero-because-the-query-failed must never
reach the guard as the same integer, because the second one opens it (`projection.py:1-6`).
Matching honours the same tri-state: `candidate_for` raises rather than handing the ranker a
candidate whose relationship state is zero because a query failed
(`src/retinue/matching/integrate.py:22-24`).

**Money is Decimal at the write barrier, and the barrier is where the bound binds.** A money
touchpoint refuses a missing amount, refuses a float outright, refuses an unparseable string,
refuses a non-finite value, and refuses a value whose plain rendering alone exceeds the block's
default budget - measured by arithmetic on `as_tuple` rather than by building the string, so the
guard does not pay the cost it exists to prevent (`src/retinue/ledger/models.py:68-114,20-45`).
Downstream, money leaves in plain notation via `:f`, never `str(Decimal)`: scientific notation
would be dropped from the engine's record values in silence, and a draft stating a figure the
record actually holds would then collect a figure-not-in-record finding
(`projection.py:66-86`). The write barrier's bound and the block's default budget are stated in
two files the import cycle keeps apart, held equal by a test - double entry, the same control
the session roster uses (`models.py:13-18`).

**The projection's structural job is feeding the boundary's `ActContext`.** Four of the six
fields are sourced: `sent_count` from the investor's `sent` touchpoints, consented jurisdictions
from the identity record, granted tools from the topology roster, the cap from configuration
(`projection.py:52-64`). The other two - the approval token and the tier - are not sourced, the
spec's sharpest amendment says so by name (spec section 5.2, amended 2026-08-12), and they are
two of section 15's six rows. Escalation durability is the queue's job: `DurableQueues.put`
writes the durable row first and the in-process copy second, so a crash between the halves loses
the copy a restart can rebuild and never the work item; a sink that raises raises out of `put`
with nothing softened (`review_queue.py:54-56` and the module docstring).

---

## 8. The rendered block, and the control that distrusts it

The record projects into a bounded context block that rides in every prompt, and the block is
treated as what it is: the most-trusted component, and therefore the best fabrication vector.
`render_block` raises on an over-budget block and raises on a missing required field - a partial
block is the agent confidently reading back null - and refuses any field value carrying a line
break `splitlines` recognises, because eight such characters survive a JSON round trip and a
value carrying one renders a forged field line the reader answers from
(`src/retinue/ledger/block.py:48-85`). The header and the label roster are machine-checked
contracts: the labels are derived from the render table itself, so a label has exactly one home
(`block.py:12,31-46`).

The control eval gives that component the containment treatment: re-ask only the questions whose
answers live in block-only fields, against a context with the block stripped, and **at least one
must fail** - a control that passes says the stripper silently did nothing. The stripper is
structural rather than boundary-hunting - the header, then the consecutive lines carrying the
block's own labels - and its docstring records the two abandoned end-hunting rules and the
measurement that retired them: over 24 ordinary instruction openers appended with no separator,
the colon rule handled none correctly and this walk keeps all 24
(`src/retinue/evals/control.py:45-113`). `BLOCK_ONLY_FIELDS` is curated, not derived, and the
comment says why a derived list passes today's tests and fails the eventual reader
(`control.py:19-39`). The spec's sentence is not left to check itself: a second test holds that
the strip removes the whole block and only the block, and emptying the question list was run to
show which test catches it (`control.py:7-15`).

---

## 9. The evaluation architecture

Over hand-authored fixtures, every number this harness produces is **a demonstration of a
protocol, not a measured claim about model behaviour**, and both halves of that sentence are
load-bearing: those fixtures are hand-authored, not blind-authored like the sibling's corpus, so
no figure computed over them may be read as an observation of a model. One fixture crossed that
line on 2026-08-12: the judge capture ran once, so the verdict column in
`fixtures/verdicts/judge_verdicts.json` is a captured judge's answer, frozen at the library
version and model id stamped in its own `meta`. The drafts' ground truth is still one author's
labels, and the capture's size is stated where its numbers are read: two cases, the compliant
verdict at confidence 0.55 under the 0.7 floor, so the calibration figure divides by ONE confident
verdict, with raw agreement of two-in-two pinned as its own assertion. A real judge inside a small
protocol demonstration, not a measurement at scale.

**Calibration and discrimination are separate checks with separate names and units.**
`calibration_agreement` scores the confident verdicts' agreement with ground truth and returns
0.0 when nothing clears the floor, because a judge confident of nothing has failed to be
calibrated, not passed; `discrimination_gap` is mean compliant quality minus mean violating
quality, signed so a positive number carries the claim
(`src/retinue/evals/frozen.py:47-76`). The loader refuses a duplicate case outright, because two
rows collapsing to one key would leave every coverage check green while both metrics scored the
survivor as the only verdict (`frozen.py:32-45`).

**The ranking evaluators are floats carrying their own names, never booleans.** `hit_at_{n}`
puts the window in the metric's name because two windows averaged under one name are a figure
with no meaning; MRR returns the reciprocal rank - 1, 1/2, 1/3 - and the tests probe ranks 2 and
3 because a binary impostor agrees with MRR at both ends and lies only in the middle
(`src/retinue/evals/ranking.py:27-54`). The shortlist under evaluation drops the
needs-verification bucket deliberately: a blocked-and-routed candidate is not a result, and a
metric that counts one rewards the ordering the eligibility layer exists to refuse
(`ranking.py:56-71`). The gold fixture documents its own statistics: its `meta` records why the
roster is 33 rows - the first seed-7 prefix at which two cells hold three rivals each, because a
gold over a one-candidate shortlist is a tautology that scores 1.0 whatever the ranker did
(`fixtures/gold_rankings.json`).

The block-stripped control (section 8) and the block-rate discipline complete the harness: the
judge ran once, live and keyed, and is frozen at version - never in CI, on determinism grounds.
What would widen these from protocol size into measurements is section 16's plan.

---

## 10. Three lanes, and what each has actually done

**Default lane** - `python -m pytest`, no daemon, no network, no key, on a fresh clone. The
README's count at this commit: 241 passed, 9 skipped, all 9 keyed on the Postgres DSN. Local
counts are one machine's on Python 3.13. CI first ran on 2026-08-12 and the default lane is green
on both 3.11 and 3.13, so the sentence this page carried about nothing having run on 3.11 is
retired rather than reworded.

**Postgres lane** - keyed on `RETINUE_PG_DSN`; unset, it skips with a printed reason;
`RETINUE_PG_REQUIRED=1` turns the skip into a failure, which is the negative control that keeps
the lane from being vacuous (`.github/workflows/ci.yml:56-61`). The lane runs the same contract
tests against real Postgres plus the enforcement only a real database earns: the unique
idempotency key, the append-only and TRUNCATE triggers, concurrent append, the durable
review-queue sink, and two separate plan assertions over the projection's hot query: that it
reaches the named index, and that its ORDER BY rides that index rather than a Sort.

**This lane has now executed, and what it found is the reason it exists.** There is no Docker on
the authoring machine, so every Postgres statement here was read and never run until CI ran it on
2026-08-12. Four runs as of 2026-08-14; the first collected 249, each later one 250, and a
sentence that counted two was counting reddens. The first reddened the index test on a third
clause it carried, asserting no Sort: the named index was reached and there was no Seq Scan, so
what the test's name claimed held, but at roughly twenty-five rows per investor the planner chose
a bitmap scan and re-sorted. A planner choice at toy scale, not a broken index. The clause became
its own test, and that test then reddened on its own first contact for a different reason: its
seed had put every row under the queried investor, so the predicate selected the whole table, and
at full selectivity no index scan beats a sequential scan plus a sort. Both findings were the seed
deciding the plan rather than the schema, inverted. The current seed makes selectivity the
experiment, and its first run, on the morning of 2026-08-13, was green: the planner chose the
index path at half a percent selectivity, 250 passed in this lane, and the 2026-08-14 run
repeated it. **Executed and green are still different claims; since 2026-08-13 this lane holds
both.**

**Live lane** - `RETINUE_LIVE=1`, keyed, manual, never CI. Live runs are capture runs: payloads
recorded once, stamped with the versions that produced them - asked of the installed binaries,
never hardcoded (`scripts/demo.py:58-74`) - frozen under `fixtures/`, and replayed forever. The
three scripts are in three states and the README lists them one by one because the states differ:
the P1 smoke has run and is now frozen, its guard refusing every invocation since the P4 roster
widened the session it captured; the judge capture ran once on 2026-08-12; the demo ran once the
same day. All three outputs are tracked, so `tests/boundary/test_ask_replay.py` no longer skips on
absence and fails instead, a missing tracked capture being a broken checkout rather than a lane
awaiting its turn.

**What the demo's one run showed.** The offer was asserted before any gating claim, which is the
protocol's whole first obligation: the send tool resolved into `system:init` beside the four P1
names. Then seven hook payloads, one conversation send, and the tool body reached zero times. The
hook held a live send for a human who was not there, and nothing left the process. One run of one
session is evidence that the ask arm holds unattended; it is not a distribution over runs, and
section 17 keeps that distinction.

What the retained capture settled is quoted in section 3. What it also settled, less
comfortably: **the session is not hermetic by default.** The uncontrolled capture carried five
MCP servers and sixteen agent definitions where the topology declares three; `setting_sources=[]`
was then measured to remove the eight settings-defined agents, two plugins and the operator's own
hooks, while removing neither the CLI's five built-in agents nor the MCP servers
(`topology.py:115-136`). The residual is guarded rather than assumed: a fixture contract asserts
no `mcp__` tool resolved into the P1 session - scoped to that one file deliberately, because the
P4 demo registers an in-process send tool on purpose, and containment is never demonstrated by
the absence of the thing being contained.

---

## 11. The enforcement of honesty itself

The differentiating layer here, as in the sibling, is the machinery that keeps the claims true -
with the added difficulty that this tree's strongest claims are about what has *not* happened.

**The battery** (`tools/battery.sh`) is documented gate by gate in the README's own battery
section, and this page does not restate it. The one idea worth carrying is its organising rule:
every gate must demonstrate it can still fire before its zero is believed, because "nothing found"
and "nothing looked" print the same word. That rule generalises past the greps into a floor on
files scanned, a positive control on the counting machinery, a floor on the suite's pass count
rather than its exit status, and a grep that errors being a failed gate rather than zero hits.

**Two costs are stated where they are decided.** The client-and-organisation token pass reads an
untracked, gitignored list - a tracked list would ship the tokens it exists to keep out - so the
battery says when that pass did not run rather than reporting an ok it never earned, and the
design's cost is named beside it: this is the one gate with no standing enforcement outside the
authoring machine (`battery.sh:214-249`). And the marketing-figures family the spec names is
deliberately not a gate, because it has no reliable textual signature; the decision is written
into the script beside the gates rather than left to be noticed (`battery.sh:251-257`).

**Documents are bound to artifacts.** The governing plan embeds the battery verbatim and
`tests/test_plan_sync.py` holds the two byte-identical, so a plan describing gates the script no
longer has is a red suite. Every fixture declares exactly one provenance in its own `meta` block
and a test enforces it, including that a capture carrying an operator's home path must declare
the redaction (`tests/test_fixture_meta.py`); the redaction contract is enforced on script
*outputs*, so the demo's fixture is held to the same rule as the smoke's
(`scripts/demo.py:50-56`). The Designed-vs-Built table corrects rows against the tree in the row,
in public - the matching row struck its own "ablation harness" clause when nothing in the tree
ran an ablation - and where a claim elsewhere and a row disagree, the row is what gets fixed.

---

## 12. The technology stack, justified

Five runtime dependencies (`pyproject.toml:11-17`): `pydantic>=2.7`, `pydantic-ai>=2.23`,
`pydantic-evals>=2.23`, `psycopg[binary]>=3.1`, `claude-agent-sdk>=0.2.130` - plus the vendored
wheel, installed first by `requirements.txt` because order matters and the file encodes it.

| Choice | Why |
|---|---|
| The SDK as a default dependency | The default lane constructs `ClaudeAgentOptions` as data, which needs the package while spawning nothing. The README's earlier "dependency-free" wording was corrected to the claim that survives a skeptic: nothing needs to be *running*, not nothing is installed. |
| pydantic-ai at the specialist seam | Each specialist is one module emitting both artifacts - the SDK `AgentDefinition` and the pydantic-ai `Agent` - from shared constants, with parity asserted on the same prompt *object*, not equal strings (`topology.py:24,28,32`). Offline doubles (`TestModel`/`FunctionModel`) drive the specialist tests. |
| Not `pydantic-ai-harness` | Read at 0.18.1, dated because a 0.x package dates any claim about it. Its `ToolGuardrail` guards the tools a pydantic-ai `Agent` executes; this fleet's acts travel through the Claude Agent SDK's hook path and the chokepoint, so the guardrail belongs to the layer the acts do not travel through. Adoption is possible - the version constraints overlap - so nothing here is a compatibility excuse; the README carries the full argument, including the one question kept open. |
| psycopg3, one idempotent `schema.sql` | `ledger.bootstrap(dsn)` applying one file is the whole migration story, which is also the managed-Postgres story (spec 2.2). No sqlite anywhere: a second SQL dialect is a second implementation of the schema under test. |
| Rejected alternatives, each with its reason | Spec section 10 lists nineteen, none silent - policy-as-data, a tool-registry table, retry-with-backoff at the chokepoint, token buckets, prompt caching, a hand-rolled agent loop, a graph checkpointer for escalation durability, and the rest. |

---

## 13. Data flow: one gated send, end to end

The stages below are each driven by the default lane's tests through the scripted driver; no
single test drives them as one path, because the seam between the hook's ask and the chokepoint is
section 15.1's. One live crossing exists and stops exactly at that seam: the demo's session drove
a conversation send into the hook's ask and no further, the tool body unreached (section 10). No
agent has run anything below the ask live.

```
conversation turn (ConversationTurn composes the Draft; the thread rides inside)
      |
      v
PreToolUse hook: decide(agent_type="conversation", tool="send_message") -> "ask"
      |                                  (a human approves the CALL; the act is still ungated
      v                                   evidence-wise - the token seam, section 15.1)
attempt_send(key, draft, record, context, checker, gateway, registry, queues, store, ...)
      |-- terminal guard: this key already produced an act?  -> TerminalSend
      |-- validation: empty body?                            -> InvalidSend
      |-- context is None?  -> deny boundary:projection_unavailable, queue handoff, engine never runs
      v
guarded_call (imported): engine + independent detector, bound to the reviewed draft
      |-- denial: terminal Handoff -> DurableQueues.put (durable row FIRST, then in-process)
      v allow
confirm(result) -> CONFIRMED | FAILED | UNVERIFIABLE   (a raise IS unverifiable)
      |-- UNVERIFIABLE: escalate boundary:delivery_unverifiable
      v
store.append(sent touchpoint, byte counts only)  -> False or a raise:
      escalate boundary:send_unrecorded, return UnrecordedSend (no `allowed` attribute)
      v
ledger projection: sent_count now includes this act; the next build_act_context reads it
```

---

## 14. Project structure

```
src/retinue/
  orchestration/  topology.py - the options, rosters and ceiling as inspectable data.
  specialists/    research.py (ResearchBrief; bounded-containment citation resolver),
                  drafting.py, conversation.py (composes Draft), failures.py (the
                  retryable split: malformed retries once, missing-source escalates in
                  one model call - retrying is an invitation to fabricate).
  boundary/       hook.py, send_tool.py (the chokepoint), checker_lane.py, preflight.py,
                  review_queue.py. The only package that imports chaperone.gates/audit.
  ledger/         models.py (write barriers), store.py (contract + in-memory reference),
                  postgres.py (adapter; first executed in CI, 2026-08-12), projection.py,
                  block.py, outcomes.py.
  matching/       integrate.py - roster + ledger into the imported staging, unchanged.
  evals/          frozen.py, ranking.py, control.py.
  synth/          rosters.py - seeded volume for unjudged data only.
tools/            battery.sh, fleet_audit.py - the guards that do not travel in any wheel.
fixtures/         frozen captures and hand-authored fixtures, one declared provenance each.
scripts/          capture_smoke.py (frozen), judge_capture.py and demo.py (each ran once,
                  2026-08-12; their outputs are the frozen fixtures).
schema.sql        the whole migration story; first executed in CI, 2026-08-12.
vendor/           the wheel and its provenance.
```

---

## 15. The roadmap: six Designed rows, argued

The README's Designed-vs-Built table carries six Designed rows, and they are this proposal's
roadmap because each is already a named absence with a shape - a row, a sketch, a parked test -
rather than an idea. For each: what exists, what building it would take, what risk it retires,
and what evidence would count. Ordered by leverage.

### 15.1 The ask-to-chokepoint approval bridge

**What exists.** The seam the two lanes meet at, and the sharpest correction in the tree: the
spec asserted this as sourced until 2026-08-12 (spec 5.2). `build_act_context` takes
`approval_token: str | None = None` and every non-test caller would default it
(`projection.py:52-54`); the imported check is presence-only and its class sits in the library's
futile set, terminal with no redraft,
so a composed system denies every send - unless a caller invents a token, which reduces "a human
approved this act" to "the caller passed a non-None string". An SDK permission grant hands the
tool body no evidence it can carry, so this is a design question, not unwritten wiring.

**What building it takes.** A mint, a transport, and a validation stronger than presence, all
boundary-side because none of it may be policy code. The natural mint is the review surface this
tree already has: `review_queue` rows carry a `resolved_at` column that nothing writes yet
(`schema.sql:56-58,64`), so a human resolution can mint a single-use token bound to the draft's
idempotency key and body digest, stored where the tool body can read it back. Validation binds
the token to the act - key and digest match, unconsumed, within a window - as a boundary
pre-check in the pattern `projection_unavailable` already established (`send_tool.py:115-119`),
before `build_act_context` receives it; the imported presence check then holds what it has always
held. The open half stays open: whether the hook's `"ask"` and the chokepoint's token can be one
event depends on what evidence an SDK grant can carry, and the honest sequencing is to capture
that with the demo before designing around a guess.

**What risk it retires.** Today the strong lane is unreachable when composed as designed; the
only path to a permitted send is a caller inventing evidence. That is the standing incentive this
row removes.

**What evidence would count.** Default-lane tests: a bridged approval passes end to end; a token
minted for a different draft or key is refused at the boundary pre-check; a reused token is
refused; and a replay of the demo's captured ask payload drives the full path. Postgres-lane
tests for the mint's durability. The row flips to Built only when `attempt_send` gains its first
non-test caller through this path, which is the same event as section 4's disclosure coming off.

### 15.2 Tier from the ladder decision

**What exists.** `chaperone/gates/ladder.py` ships in the wheel and nothing in `src/retinue/`
imports it; tier arrives everywhere as a bare int parameter (README row; spec 5.2). The doctrine
it would serve is already written: eval rates decide how much autonomy a class of action has
earned - offline, human-ratified - and permission is enforced at call time by code a reader can
audit (spec section 1).

**What building it takes.** `boundary/` imports the ladder (the fleet audit already routes all
gate imports there), declares per-surface ceilings for the three specialists in the topology's
data style, and `build_act_context`'s `tier` parameter is fed from a constructed `LadderState`
rather than a literal. The library's constructor refuses a state above its surface's ceiling, so
the fleet inherits an unconstructable-overreach property instead of building one.

**What risk it retires.** A bare int is an unvalidated grant: any call site can pass `1` and
quietly stand below the tier at which the token check binds (the imported predicate fires at
tier >= 2). Sourcing tier from the ladder makes the autonomy level a decision with provenance.

**What evidence would count.** An options-shape-style test that every `build_act_context` call
site sources `tier` from a `LadderState`; a test that a specialist surface above its ceiling
cannot be constructed; and the promotion path left exactly as the library left it - built and
driven by nothing - until human-review outcomes exist to drive it, which is the sibling's own
refusal of self-promotion, inherited deliberately.

### 15.3 The per-investor sliding-window contact limit

**What exists.** A Designed row inheriting the library's note, and the substrate the window
needs: every touchpoint carries `occurred_at`, so a windowed count is one query over data already
recorded. The spec's rejected-alternatives list has already ruled the shape once: a token bucket
is "a different object with the same name" (spec section 10), and the same caution applies to
the imported cap predicate - `sent_count` versus `send_cap` is a lifetime count today, and a
windowed count silently substituted into it would change the predicate's meaning without changing
its code.

**What building it takes.** A windowed count computed in the projection beside `sent_count`, fed
explicitly - the purity rule is that a predicate needing a value takes it as an argument - and
either a second, documented use of the imported cap predicate over (windowed count, windowed cap)
or a boundary pre-check in the `projection_unavailable` pattern. Postgres work follows: the
window query's plan may re-litigate the index this schema already retired once
(`schema.sql:22`, the dropped `(investor_id, occurred_at)` index), and the DSN lane's plan-test
discipline applies to whatever index the real query earns.

**What risk it retires.** Burst contact inside the lifetime cap: a cap of N says nothing about N
sends in an afternoon, and relationship-led outreach is the domain where pacing is the constraint
that matters.

**What evidence would count.** Contract tests over both stores at the window boundaries - a touch
at exactly now-minus-window, clock injection via the same injectable timestamps the ledger
already uses - and an in-lane demonstration that the boundary refuses the send that a lifetime
count would have allowed.

### 15.4 Contested-quantity rendering and the thin-support badge

**What exists.** The contract can hold a conflict: `Claim.quantity_key` groups same-quantity
claims (`research.py:23`), the prompt instructs the model to keep both sides and never average
(`research.py:62-64`), and nothing renders a Contested quantity or a thin-support badge - the
commitment is annotate-not-arbitrate, and surfacing the annotation is the unbuilt half (README
row).

**What building it takes.** A brief renderer in the block's own style: group claims by
`quantity_key`, render a conflict as both values with both sources and dates under a Contested
marker, badge a single-source quantity as thin support, and hold the marker text as a
machine-checked contract the way `BLOCK_HEADER` is held, so an eval can strip or count it.

**What risk it retires.** A conflict held in data and invisible in prose is arbitration by
whoever reads the prose next - the drafting model picks a value, or the reviewer never learns
there were two. The renderer makes the annotation reach the only consumers who can act on it.

**What evidence would count.** Exact-render tests over a two-source conflict (both kept, marker
present) and a single-source claim (badge present); a control-style check that removing the
marker from a rendered brief changes a downstream answer, in the block-stripped control's
pattern.

### 15.5 The weights-update sketch

**What exists.** The parameter the sketch would read: `OutcomeConfig.active_signal` keeps which
outcome counts a configuration question rather than a settled one, `resolved_for` filters on it,
and last-touch attribution is built and pinned by tests, including its stated investor-level
scope (`outcomes.py:40-58` and the module docstring). Nothing updates a weight or a threshold
from a resolved outcome.

**What building it takes.** First an upstream seam, named honestly: the staging's blend weights
are module constants in the imported library (`RELATIONSHIP_WEIGHT`, `EMBEDDING_WEIGHT` in
`chaperone/matching/rank.py`), so a fleet-side update rule needs `rank` to accept weights as
arguments - a library change to request, not a fork to make, because a second ranking
implementation here would be the reimplementation this repository forbids itself. Then a
deterministic update rule at this volume: a handful of resolved outcomes adjusting a weight and a
threshold, not a learned model (spec 5.4), with every adjustment written as its own record so the
weights have provenance the way the fixtures do.

**What risk it retires.** A matching engine with no feedback path does not sharpen; the design's
outcome vocabulary exists so that it can, and this row is the difference between recording
outcomes and using them.

**What evidence would count.** A fixed outcome fixture moving a weight in the stated direction,
deterministically; ranking metrics re-run over the gold set before and after, with the deltas
*reported* - rates are never asserted, and a weights update that had to pass a metric gate would
be an eval score promoted to an authorization, the exact error the doctrine names.

### 15.6 Store unification

**What exists.** A Designed note, and a pre-answered division: the imported hash-chained audit
file is tamper-evidence for gate decisions; the Postgres ledger is relationship state (spec
section 6).

**What building it would take, and why the answer may be a documented refusal.** The two stores
hold different properties by different mechanisms: the chain's tamper-evidence is
per-entry hash links over an fsynced file, while the ledger's append-only is a trigger a
sufficiently privileged role can drop - detection by construction versus a database privilege
boundary. Unifying into Postgres would trade the first property for one backup story; unifying
into the file would rebuild a relational projection over a log. The work this row actually
proposes is the comparison, written as a decision record with the threat model stated, and the
honest possible outcome is that the note graduates to a reasoned refusal rather than a build.

**What risk it retires.** Two durability stories is an operational hazard - two backup policies,
and an operator restoring one store without the other - and an undecided note is a decision
someone will eventually make under pressure instead.

**What evidence would count.** If unified: the tamper tests asserting detection against the
unified store, and the crash-ordering tests of `DurableQueues` re-earned there. If refused: the
decision record, cited from the README row, with the same status the rejected-alternatives list
already gives nineteen other shapes.

---

## 16. The operational path to a deployment

The forward path a production deployment needs, in the order the evidence comes cheapest.

**First, CI - which has now happened, and behaved exactly as this paragraph was written to
predict.** The first push ran, for the first time on any machine, the default lane on Python 3.11,
the battery on a second platform, and every Postgres statement in the tree against the pinned
`postgres:16.4` service (`ci.yml:19,41`). The default lane came back green on both versions. The
Postgres lane's first two runs each reddened one test, and each red was a finding rather than an
embarrassment: first a Sort clause conjoined into the index test, reddening a test whose named
properties held; then the replacement test's own seed selecting the whole table. Section 10
carries both plans, pinned verbatim in the tests' docstrings. The negative control
(`RETINUE_PG_REQUIRED=1`) exists so failures surface as failures rather than skips, and they did.
The schema and the adapter stopped being read-only claims on 2026-08-12; the lane's green is the
one claim still pending, on the current seed's first run.

**Managed Postgres is the same story, by construction.** One idempotent `schema.sql` applied by
`ledger.bootstrap(dsn)` is the whole migration story, and the CI image pin matches the managed
target's major version (spec 2.2), so promotion to a managed Postgres instance is a DSN, not a
port. What managed Postgres adds beyond the lane:
backup policy, a privilege split so the application role cannot drop the append-only triggers
(section 15.6's threat model, applied early), and connection pooling in front of the
connection-per-write adapters, which are the deliberate shape at this volume, read rather than
run like every Postgres statement here, and the first thing a load profile would revisit.

**The deployment shape follows the tree's own seams.** A session-runner service on managed
compute owns the keys; nothing in the tree assumes more than a process with environment
variables. It constructs what the chokepoint requires: the gateway over the audit store,
the checker with a live transport, the registry, and `DurableQueues` over the Postgres sink. The
human half of the system is a consumer of the `review_queue` table plus the approval mint of
section 15.1; the table's `resolved_at` column is already waiting for it. The orchestrator and
specialists run as the topology's options object says they do - `setting_sources=[]`, the session
ceiling, one parent-registered hook - and the eval harness stays offline, gating autonomy through
the ladder row, never sitting on the act path. Embeddings enter where the design left the seam:
`embed_score` is an injected callable, so a real embedding pipeline is a deployment investment
that changes no staging code and gets measured by the ranking evaluators that already exist.

**The capture plan, in dependency order.** Live runs are purchases of evidence, made once each,
and the first two purchases were made on 2026-08-12. (1) Done: the judge capture replaced the
provisional verdict file in place with a stamped one - the script refuses to run over zero drafts,
so it could not have written an empty canon (`judge_capture.py:59-63`) - and the calibration and
discrimination tests are now claims about the model named in the fixture's stamp, at the size
section 9 states. (2) Done: the demo produced `captured_ask.json` under the two-obligation
protocol - the offer asserted before any gating claim, then the ask captured - and the formerly
parked replay test now runs against it, retiring that skip's named cost: the reason a human is
shown for a gated send is asserted over a hand-authored payload and a captured one. (3) Open: the
background-unset half of the P1 evidence pair, which needs a run against a deliberately-unset
definition and is the one gap the frozen smoke names itself. Rules settled and inherited by every
future capture:
stamps are asked of the installed binaries, the redaction contract is enforced on outputs by the
fixture-meta test, captures are frozen at version, fixtures from different sessions are never
mixed into one corpus, and the em-dash policy for model-authored prose inside captures is
pre-decided in the battery rather than negotiated under pressure.

**Eval expansion, with the rates named as measurements.** After the judge capture: calibration
agreement and the discrimination gap with real verdict provenance, reported with denominators.
After a grown gold set: hit@1, hit@3 and MRR over more than two cells, and the cold-start case
the metric is designed to notice - a new investor carries no relationship state, so similarity
must carry them, and the metric must notice when it does not. After the bridge and the ladder
rows: a block-rate control in the sibling's style - what fraction of a violating fixture set the
composed boundary refuses, and what a compliant set pays in false blocks. Every one of those
numbers lands in a report; the CI rule this tree inherits is that invariants are asserted and
rates never are, and the day a rate becomes a merge gate is the day a measurement quietly became
an authorization.

---

## 17. What this proposal does not claim

Limits are properties of the system, so they get the same precision as the features.

- **No agent has ever driven the chokepoint.** `attempt_send` has no caller outside its own
  module and tests; the checker lane, pre-flight and review queue are reachable only through it.
  The demo's live crossing stopped at the hook's ask, above the chokepoint, deliberately. The
  composed fleet's strong lane is unreachable as designed until section 15.1 exists, and the only
  path to a permitted send today is a caller inventing evidence.
- **Numbers over hand-authored fixtures are protocol demonstrations**, one author's, and stay so.
  The one captured crossing is stated at its size in section 9: the judge verdicts are a model's,
  frozen at version, two cases with one confident verdict. The drafts' ground truth is still one
  author's opinion, so even that figure is a judge against one author's labels, not a benchmark.
- **The Postgres half has run four times and has been green since 2026-08-13**, and the limit worth
  keeping is narrower than that sentence sounds. This bullet said "twice and not yet green, the
  current seed's first run pending" until 2026-08-14; two was the count of reddens, and the run it
  called pending had already gone green on the morning of 2026-08-13. Section 10 carried the
  corrected account first, and this bullet is dated rather than quietly swapped because a limits
  list that silently updates is the one place a reader cannot check the update. What the four runs
  bought: both reds were seed findings and not schema faults, so what they establish is that the
  index is reached and its ordering rides it at half a percent selectivity on this planner, not
  that either holds at every table size. The 241-passed count is one machine's, on 3.13, restated
  from the README rather than re-measured by this page; CI's counts are its own runs'.
- **The live captures are one machine's, at one version.** Payloads captured under one operator's
  ambient configuration are not canonical whatever they show, the session is only partially
  hermetic, and the `strict_mcp_config` field that would close the MCP half is source-cited at
  0.2.130 and not set.
- **The demo demonstrated the gate before the act, not the act.** Its one run asserted the offer,
  captured the ask, and reached no tool body; the body performs no outbound act by design
  (`demo.py:139-156`), and its main-thread reachability asymmetry is stated in the topology's own
  comment rather than smoothed over.
- **Two enforcement gaps are held by nothing but their own disclosure**: `attempt_send`'s return
  union is enforced by no type checker, so the `UnrecordedSend` guarantee is "no duplicate is
  silent", never "never sent twice"; and the banned-token pass has no standing enforcement
  outside the authoring machine, a cost the battery states where it is decided.
- **The fleet audit sees imports, not semantics.** Inline policy logic importing nothing would
  pass it; the audit's own main block says so. The claim is discipline made conspicuous, not
  absence demonstrated.

---

## Appendix: the imported contract, and how the wheel pins it

The statement of record for the import surface is spec section 6.1, verified against the wheel's
source tree; this appendix names the shape so a reviewer sees its size, and defers to the sibling
proposal's appendix for the library-side contract in full.

**What is imported, by submodule path** (the wheel's `__init__` is empty, so every import names
its module): the gates - `hook` (`pre_tool_use`, `guarded_call`), `sdk_callback`
(`pre_tool_use_deny`), `handoff`, `checker` (the transport seam, the strength ordering, the
verdict types), `queues`; the policy vocabulary - `types` (`Draft`, `Record`, `Decision`,
`Finding`, `ViolationClass`, `Disposition`) and `act_classes` (`ActContext`, which lives beside
its predicate, not in `types`); `matching` (filters, relationship, rank); `audit` (store,
gateway, chain).

**What the consumer constructs, none of it optional**: a `Gateway` over an audit store, a tool
registry the chokepoint indexes, a `Checker` with a transport, and queues - here `DurableQueues`,
duck-typed on the one method `guarded_call` calls, composition rather than inheritance so a
method the imported class grows later cannot arrive already bypassing the sink
(`review_queue.py:41-47`).

**How the pin holds.** `vendor/PROVENANCE.md` names the source repository and the exact commit;
the wheel was rebuilt from that commit on 2026-08-12 and reproduced byte for byte apart from
build-tool stamps; and the boundary queue name is double-entered - spelled once in
`send_tool.py:120` because the engine sits outside the declared surface, and held against the
imported `destination_for`'s own answer by a test, so a drift in either spelling is a red suite.
What the wheel does not carry - the library's own enforcement tooling - is exactly what
sections 2 and 11 of this page exist to replace on this side of the line.
