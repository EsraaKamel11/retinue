"""The capture lane's contracts: what a fixture must declare about where it came from, and the
one thing no test module may do.

`meta.provisional` had no expiry, and nothing else in this repository reads it, so a fixture could
be replaced by a real capture and go on claiming to be a placeholder for it forever. The marking
is made self-clearing here instead, in BOTH directions - a `captured_*` fixture that still says
`provisional` is a finding, and so is a `provisional_*` fixture whose note names a capture that
has since run.

A capture also records the operator's own transcript path, and this repository is read by people
who are not the operator. An edited capture is a weaker artifact than a raw one, so the rule below
does not forbid the edit - it forbids making it silently: a captured fixture carrying a home
directory path must say in its own meta that it was redacted.
"""
import ast
import fnmatch
import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
TESTS = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
#: What the two P1-capture helpers below say when their fixture is missing. Until Task 24 this
#: constant held `RETINUE_LIVE=1 python scripts/capture_smoke.py` and was emitted into two SKIP
#: reasons as "produce it with:" - an instruction that had exited with `not a send-free session` on
#: every invocation since Task 22 put the send names into the session roster. A false reason is
#: worse than no reason, so the P1 capture is declared FROZEN at the payloads already in
#: `fixtures/payloads/` and this says so.
#:
#: The skips became FAILURES in the same change, and the freeze is the whole argument for it. A skip
#: says a lane legitimately did not run, which was true while the capture was still to be taken;
#: once the fixtures are tracked and the command that made them refuses to run, their absence is a
#: broken checkout and not a lane awaiting its turn. `tests/boundary/test_ask_replay.py` was the
#: control for this reasoning while the P4 demo had not run: its skip said the lane was awaiting
#: its turn, which was true and could not be faked, since that fixture cannot be hand-authored into
#: existence. The demo ran on 2026-08-12 and its capture is tracked, so that file crossed to this
#: side of the line by the argument above: absence there now FAILS too. The contrast this comment
#: used to draw ended the day both captures existed; what remains is the doctrine itself, which is
#: that a skip's printed reason has to be true.
#:
#: The path `scripts/capture_smoke.py` is still spelled here deliberately.
#: `_gated_script_import_findings` parses rather than greps precisely so that a MENTION of a gated
#: script is told apart from an import of one, and this is the mention it is told apart from.
FROZEN = ("the P1 capture is frozen at the payloads under fixtures/payloads/, which are tracked; "
          "scripts/capture_smoke.py refuses today's send-bearing session and cannot retake them, "
          "so a missing one is a broken checkout rather than a lane that has not run yet")

#: Exactly one of these, never two. "At least one" would let a fixture declare itself both
#: captured and hand-authored, which is not a provenance but a pair of incompatible claims.
_PROVENANCE = ("provisional", "captured", "hand_authored")

#: A provisional fixture's note names the capture that will retire it; this pairs that claim with
#: where that capture's outputs land. The direction is the point: `captured_still_provisional`
#: keys on the `captured_` prefix and so catches a capture calling itself a placeholder, while the
#: staleness that actually occurred wears the `provisional_` prefix - a placeholder outliving the
#: capture meant to replace it. A note reworded past this phrase goes silent, which is why the arm
#: carries a planted control.
#:
#: THE P4 DEMO EARNS NO ROW HERE, and the reason is a measurement rather than a deferral. That
#: capture's output name is now defined - `captured_ask.json`, written by `scripts/demo.py` - so the
#: condition this comment used to wait on has been met and the answer is still no. `guarded_call`
#: passes `{"body": draft.body}` as the send tool's WHOLE `tool_input`, and the demo's tool declares
#: that same one-key schema, so no capture taken from the current send-tool argument shape can carry
#: the record, cited fields, approval token and jurisdiction that `provisional_send.json` supplies.
#: The demo capture therefore retires that fixture's ASK arm and cannot retire its DENY-LANE arm,
#: where `test_main_thread_send_still_runs_the_deterministic_lane` reads a constructed 9M-vs-8M
#: mismatch back as `figure_not_in_record`. A row added anyway would redden the suite on the first
#: real capture, demanding the retirement of a fixture that has to survive it. Scoped to the current
#: argument shape on purpose: a later task that widens the schema may change this, and would then
#: own the row.
_SUPERSEDED_BY = (("P1 capture smoke", "captured_*.json"),)

#: Each capture SCRIPT's outputs, as a FAMILY. `captured_sessions_mixed` below asks that a family
#: hold one session, and the reason it is per-family rather than per-tree is the P4 demo: it is a
#: second, later, deliberately separate run, so its fixture carries a different `session_id` by
#: construction and a tree-wide rule would report a correct capture as a mixed corpus. The hazard
#: the rule was built for is untouched and is internal to one family - a smoke re-run writing fewer
#: payloads leaves the previous run's higher-numbered files beside the new ones.
#:
#: The membership rule is what stops this being a weakening. Every `captured_*.json` must match
#: EXACTLY ONE family: matching none is a finding, so a future capture cannot escape the
#: single-session check by landing under an unlisted name, and matching two is a finding, so a
#: family pattern widened to `captured_*.json` cannot swallow its neighbours and make the check
#: vacuous by putting every file in one bucket that is then allowed one session per bucket.
#:
#: `captured_[0-9]*.json` rather than a two-digit form: the smoke writes `captured_{i:02d}.json`, and
#: a run long enough to reach three digits would otherwise leave every file past the ninety-ninth
#: unfamilied.
_CAPTURE_FAMILIES = (
    ("P1 capture smoke", ("captured_[0-9]*.json", "captured_init.json")),
    ("P4 demo", ("captured_ask.json",)),
)

def _families_of(name: str, families=_CAPTURE_FAMILIES) -> list[str]:
    """Every family this filename matches. A list rather than a first hit, because "matches two"
    is a finding and a `next(...)` would silently report the first."""
    return [label for label, patterns in families
            if any(fnmatch.fnmatch(name, pat) for pat in patterns)]

#: Matched against the RAW file text, not the decoded values: a Windows path inside JSON is
#: always backslash-escaped, so `C:\\Users\\` is what is actually on disk. A redacted fixture
#: still matches this pattern, because the placeholder keeps the path's shape - which is the
#: point. Only the pairing of a home path with no declared redaction is a finding.
_HOME_PATH = re.compile(r"[A-Za-z]:\\\\Users\\\\|/home/|/Users/")

def _provenance_findings(root: Path, families=_CAPTURE_FAMILIES) -> list[str]:
    """One named rule per finding, over ANY fixture tree - so each rule can be shown firing on a
    planted one. Silence over the real tree is what a correct rule and an unreachable rule look
    like alike.

    `families` is a parameter for the same reason `root` is: the family-overlap rule cannot be shown
    firing by planting files, only by planting a bad tuple, and patching the module-level one would
    leave the shipped tuple untested in the same run.
    """
    findings: list[str] = []
    sessions: dict[str, dict[str, list[str]]] = {}
    for p in sorted(root.rglob("*.json")):
        text = p.read_text(encoding="utf-8")
        doc = json.loads(text)
        meta = doc.get("meta") or {}
        if not meta:
            findings.append(f"no_meta_block: {p.name}")
            continue
        declared = [k for k in _PROVENANCE if meta.get(k)]
        if not declared:
            findings.append(f"no_provenance: {p.name}")
        elif len(declared) > 1:
            findings.append(f"ambiguous_provenance: {p.name} declares {declared}")
        if p.name.startswith("captured_"):
            if meta.get("provisional"):
                findings.append(f"captured_still_provisional: {p.name}")
            stamp = meta.get("captured")
            values = list(stamp.values()) if isinstance(stamp, dict) else [stamp]
            if not stamp:
                findings.append(f"captured_without_version_stamp: {p.name}")
            elif any((not v) or v == "unknown" for v in values):
                # `_cli_version()` returns the literal "unknown" when it cannot resolve the binary
                # it is stamping, so a stamp can be present and still say nothing.
                findings.append(f"captured_stamp_unresolved: {p.name}: {stamp}")
            if _HOME_PATH.search(text) and not meta.get("redacted"):
                findings.append(f"home_path_without_redaction: {p.name}")
            family = _families_of(p.name, families)
            if not family:
                findings.append(f"captured_family_unnamed: {p.name}")
            elif len(family) > 1:
                findings.append(f"captured_family_ambiguous: {p.name} matches {family}")
            session = (doc.get("payload") or {}).get("session_id")
            if session:
                # Keyed by the file's own name when the family is not exactly one, so an unfamilied
                # or double-claimed capture is never quietly pooled with a real family - it is
                # already a finding above, and pooling it could turn a second finding on or off.
                key = family[0] if len(family) == 1 else f"<{p.name}>"
                sessions.setdefault(key, {}).setdefault(session, []).append(p.name)
        if p.name.startswith("provisional_"):
            note = meta.get("note") or ""
            for phrase, pattern in _SUPERSEDED_BY:
                if phrase in note and any(root.rglob(pattern)):
                    findings.append(f"provisional_superseded_by_capture: {p.name}")
    for label, by_session in sorted(sessions.items()):
        if len(by_session) > 1:
            # A later run writing fewer payloads leaves the previous run's higher-numbered files in
            # place. The write happens in a `finally` precisely because a live capture is not
            # repeatable, so the guard against mixing two corpora belongs here rather than in a
            # destructive pre-clear inside the script. Per FAMILY, because two capture scripts are
            # two corpora and always were - see `_CAPTURE_FAMILIES`.
            findings.append(f"captured_sessions_mixed: {label}: {sorted(by_session.values())}")
    return findings

#: Every RETINUE_LIVE-gated script. Each one is manual, keyed and not repeatable for free, so a test
#: module importing one could spend a key or overwrite a captured fixture as a side effect of mere
#: collection. A tuple rather than the single literal this began as: every such script's docstring
#: claims "never imported by tests", and a rule naming only the first of them left that claim
#: asserted and unenforced for the rest - which is the shape of gap this file exists to close. That
#: gap reopens by ADDITION rather than by edit, so `test_every_live_gated_script_is_named_in_the_rule`
#: reads `scripts/` off disk and holds it against this tuple; `demo` arrived through that line going
#: red rather than through anyone remembering.
#:
#: `demo` is a SHORT entry where the other two are distinctive, and the matcher below is a substring
#: test over imported module names. No import under `tests/` contains it today, checked rather than
#: assumed, but `from x import demo_helpers` would be reported as importing a gated script. The cost
#: of that false positive is a loud test naming the wrong file, which is the safe direction here;
#: the note exists so the next reader diagnoses it in one step instead of suspecting the rule.
_GATED_SCRIPTS = ("capture_smoke", "demo", "judge_capture")

def _gated_script_import_findings(root: Path) -> list[str]:
    """An import STATEMENT naming a gated script, told apart from a mention of one.

    The failure reason above names `scripts/capture_smoke.py` in a string, and a grep cannot tell
    that from an import - which is why the brief's `grep -r capture_smoke tests/` check broke on
    a correct change. Parsing is the same answer the fleet audit reaches for the same reason.
    """
    findings: list[str] = []
    for py in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            else:
                continue
            hit = [g for g in _GATED_SCRIPTS if any(g in n for n in names)]
            if hit:
                findings.append(f"test_imports_gated_script: {py.name}:{node.lineno} {hit}")
    return findings

#: The CLI's own built-in agents at 2.1.222, read off a captured `system:init`. Not configuration:
#: they ship with the product, and `setting_sources=[]` does not remove them. Pinned as data so
#: anything ELSE appearing beside the topology's own names is a finding - which is exactly what a
#: capture taken on a machine whose settings leaked into the session looks like.
_BUILTIN_AGENTS = frozenset({"claude", "Explore", "general-purpose", "Plan", "statusline-setup"})

def _init_findings(init: dict) -> list[str]:
    """What a canonical `system:init` may contain. These fixtures are replayed forever, so a
    session that one operator's ambient configuration helped shape must not become the canon."""
    from retinue.orchestration.topology import AGENTS
    findings: list[str] = []
    ambient = sorted(set(init.get("agents") or ()) - _BUILTIN_AGENTS - set(AGENTS))
    if ambient:
        findings.append(f"init_declares_ambient_agents: {ambient}")
    # `setting_sources=[]` does NOT clear `mcp_servers`, so those servers are listed in a
    # canonical capture too. Being listed is harmless; a tool of theirs resolving into the session
    # is not, and that is the property the send-free claim actually rests on.
    #
    # TASK 22 LEFT THIS RULE'S FATE TO TASK 23, AND TASK 23 LEAVES IT EXACTLY AS IT IS. The concern
    # was that a P4 capture, taken with the widened ceiling and the retinue server connected, would
    # resolve `mcp__retinue__send_message` into the session and be reported here for a name this
    # repository puts there deliberately. The premise is right and the conclusion does not follow,
    # because of WHICH FILE this rule reads. `_captured_init` opens `captured_init.json` and nothing
    # else, and that file is the P1 smoke's output; `_refuse_if_a_send_tool_exists` makes the smoke
    # exit before constructing a client if any send tool is named in any roster OR if `mcp_servers`
    # is set at all. So for the one payload this rule judges, a resolved `mcp__` send tool would mean
    # that guard was bypassed, which is a real finding and not a false one.
    #
    # THAT GUARD IS NOW UNCONDITIONAL, and this comment described it in the present tense as
    # conditional. Task 22 put the send names in `SESSION_TOOLS`, so `build_options` always names
    # them and the smoke SystemExits on every invocation: `not a send-free session`. The rule above
    # is still sound - it reads a file that already exists and was captured before that change - but
    # a reader taking the conditional phrasing at face value would believe a fresh P1 capture is one
    # command away. It is not, until someone decides how a send-free capture is taken from a session
    # whose ceiling now offers the tool. Booked into Task 24 with the three tracked strings that
    # still point a reader at that command.
    #
    # What keeps it that way is that `scripts/demo.py` writes ONE path, `captured_ask.json`, and
    # never `captured_init.json` - it does not overwrite the send-free capture with a send-bearing
    # one. Excepting `SEND_TOOLS` here would have bought nothing and cost the rule its edge on the
    # only file it looks at: the send-free session is the claim, and a rule that waves through the
    # send tool cannot check it.
    #
    # The demo's own offer evidence needs no fixture. The ask capture IS the evidence, because the
    # hook is only ever handed a call to a tool the session resolved, so a `captured_ask.json`
    # naming a send tool is a session in which that tool was offered.
    mcp = sorted(t for t in (init.get("tools") or ()) if t.startswith("mcp__"))
    if mcp:
        findings.append(f"init_session_holds_an_mcp_tool: {mcp}")
    return findings

def _captured_init() -> dict:
    p = FIX / "payloads" / "captured_init.json"
    if not p.is_file():
        pytest.fail(f"no captured system:init at {p}: {FROZEN}")
    return json.loads(p.read_text(encoding="utf-8"))["payload"]

def _captured_payloads() -> list[dict]:
    paths = sorted(FIX.glob("payloads/captured_*.json"))
    if not paths:
        pytest.fail(f"no captured payloads in {FIX / 'payloads'}: {FROZEN}")
    return [json.loads(p.read_text(encoding="utf-8")).get("payload") or {} for p in paths]

def test_every_fixture_json_carries_provenance():
    # rglob over an emptied or moved tree yields nothing and every rule below holds vacuously,
    # so the sweep is pinned as non-empty before it is trusted. Absence of files is not evidence.
    assert sorted(FIX.rglob("*.json")), f"no fixture JSON found under {FIX}"
    assert _provenance_findings(FIX) == []

def test_each_provenance_rule_fires_on_a_planted_tree(tmp_path):
    (tmp_path / "headless.json").write_text('{"payload": {}}', encoding="utf-8")
    (tmp_path / "unmarked.json").write_text('{"meta": {"note": "x"}}', encoding="utf-8")
    # Two provenances at once is a pair of incompatible claims, not a richer declaration.
    (tmp_path / "both.json").write_text(
        '{"meta": {"captured": {"sdk": "a", "cli": "b"}, "hand_authored": true}}', encoding="utf-8")
    # One planted file for both stamp-absent rules: marked provisional AND carrying no stamp.
    (tmp_path / "captured_99.json").write_text('{"meta": {"provisional": true}}', encoding="utf-8")
    # Stamped, not provisional, carrying a home path it does not declare.
    (tmp_path / "captured_98.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}},'
        ' "payload": {"transcript_path": "C:\\\\Users\\\\someone\\\\s.jsonl"}}', encoding="utf-8")
    # A stamp that is present and says nothing.
    (tmp_path / "captured_97.json").write_text(
        '{"meta": {"captured": {"sdk": "0.2.130", "cli": "unknown"}}}', encoding="utf-8")
    # Two captures from two different runs of the SAME script, which is the mixed-corpus hazard.
    (tmp_path / "captured_70.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}}, "payload": {"session_id": "run-a"}}',
        encoding="utf-8")
    (tmp_path / "captured_71.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}}, "payload": {"session_id": "run-b"}}',
        encoding="utf-8")
    # A capture landing under a name no family claims, which is how a later output would otherwise
    # escape the single-session check entirely.
    (tmp_path / "captured_elsewhere.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}}}', encoding="utf-8")
    # A placeholder naming a capture that the same tree shows has since run.
    (tmp_path / "provisional_stale.json").write_text(
        '{"meta": {"provisional": true, "note": "hand-authored; replaced by the P1 capture smoke"}}',
        encoding="utf-8")
    found = " ".join(_provenance_findings(tmp_path))
    for rule in ("no_meta_block", "no_provenance", "ambiguous_provenance",
                 "captured_still_provisional", "captured_without_version_stamp",
                 "captured_stamp_unresolved", "home_path_without_redaction",
                 "captured_sessions_mixed", "captured_family_unnamed",
                 "provisional_superseded_by_capture"):
        assert rule in found, f"rule never fired: {rule}"

def test_a_lone_hand_authored_marking_is_the_accepted_third_provenance(tmp_path):
    # Written when `hand_authored` was a disjunct no fixture used, so deleting it from the accepted
    # set left the whole suite green. `provisional_send.json` declares it since Task 23 measured
    # that no capture can produce that payload, so the real tree now exercises the branch too and
    # this row has become the planted control beside it rather than its only cover.
    (tmp_path / "hand.json").write_text('{"meta": {"hand_authored": true}}', encoding="utf-8")
    assert _provenance_findings(tmp_path) == []

def _capture(session: str | None = None) -> str:
    body = '{"meta": {"captured": {"sdk": "x", "cli": "y"}}'
    return body + (f', "payload": {{"session_id": "{session}"}}}}' if session else "}")

def test_two_capture_families_are_two_corpora_rather_than_one_mixed_one(tmp_path):
    """Two live runs are two corpora, held over planted payloads in their RAW shape.

    The demo is a second live run, so as captured its `captured_ask.json` carried a `session_id`
    the smoke's payloads did not. Read tree-wide that is two sessions, and the mixed-corpus rule
    would report a correct capture; read per family it is two corpora, which is what it is.

    The planted payloads below keep that raw shape on purpose, and the shipped tree no longer has
    it: every captured payload was redacted to the same literal `<session-id>` placeholder, so over
    `fixtures/` the two families now agree by construction rather than by rule. Planting is what
    keeps this test measuring the rule instead of the redaction. It is the one that fails if the
    rule is ever put back the way it was.
    """
    (tmp_path / "captured_00.json").write_text(_capture("smoke-run"), encoding="utf-8")
    (tmp_path / "captured_init.json").write_text(_capture("smoke-run"), encoding="utf-8")
    (tmp_path / "captured_ask.json").write_text(_capture("demo-run"), encoding="utf-8")
    assert _provenance_findings(tmp_path) == []

def test_one_family_still_may_not_hold_two_sessions(tmp_path):
    """The other direction, on the family the P4 fixture joins rather than on the smoke's.

    Without this the per-family rule could be shown working only where it already worked. Two demo
    runs cannot both land in `captured_ask.json`, so the specimen is the smoke's own family, and the
    row above plus this one together say the rule moved from tree-wide to per-family and did not
    simply switch off.
    """
    (tmp_path / "captured_00.json").write_text(_capture("run-a"), encoding="utf-8")
    (tmp_path / "captured_init.json").write_text(_capture("run-b"), encoding="utf-8")
    found = _provenance_findings(tmp_path)
    assert any("captured_sessions_mixed" in f for f in found), found
    assert any("P1 capture smoke" in f for f in found), found

def test_a_family_pattern_that_swallows_another_is_a_finding(tmp_path):
    """The membership rule's second half, which is what keeps the first half from being a hole.

    A future capture script given the pattern `captured_*.json` would put every fixture in the tree
    into one family, and a family is allowed one session - so every other family's files would be
    read as that family's and the single-session check would go quiet over exactly the mixing it
    exists to find. The families are passed in rather than patched onto the module, so this row does
    not disturb the real tuple, and the second assertion is the control: the shipped families are
    not ambiguous, so a green first assertion cannot be coming from a rule that fires on everything.
    """
    (tmp_path / "captured_ask.json").write_text(_capture("demo-run"), encoding="utf-8")
    greedy = (("greedy", ("captured_*.json",)), ("P4 demo", ("captured_ask.json",)))
    assert any("captured_family_ambiguous" in f
               for f in _provenance_findings(tmp_path, greedy))
    assert not any("captured_family_" in f for f in _provenance_findings(tmp_path))

def test_every_shipped_capture_fixture_belongs_to_exactly_one_family():
    """Over the REAL tree, and separate from the sweep above because it says something narrower.

    `test_every_fixture_json_carries_provenance` would also catch an unfamilied fixture, mixed in
    with every other rule. This one names the property, and it is the line a future capture script
    trips on when it writes a name nobody added to `_CAPTURE_FAMILIES`.
    """
    captures = sorted(p.name for p in FIX.rglob("captured_*.json"))
    assert captures, f"no captured fixtures under {FIX}"
    for name in captures:
        assert len(_families_of(name)) == 1, f"{name}: {_families_of(name)}"

def test_no_test_module_imports_a_gated_script():
    """Named for the whole tuple, because it now guards the whole tuple.

    It read `..._the_capture_smoke` while checking every entry in `_GATED_SCRIPTS`: a name promising
    something narrower than its body holds, which is the same defect one file over as the docstring
    absolute this round's review was convened to remove.
    """
    assert _gated_script_import_findings(TESTS) == []

def test_the_gated_script_rule_tells_an_import_from_a_mention(tmp_path):
    (tmp_path / "mentions.py").write_text('SMOKE = "scripts/capture_smoke.py"\n', encoding="utf-8")
    assert _gated_script_import_findings(tmp_path) == []      # a grep flags this; the parse must not
    (tmp_path / "imports.py").write_text("from scripts.capture_smoke import main\n",
                                         encoding="utf-8")
    assert any("imports.py" in f for f in _gated_script_import_findings(tmp_path))

def test_every_live_gated_script_is_named_in_the_rule():
    """The tuple above is a hand-maintained list, and the gap it closed can reopen by addition.

    Its own comment says a rule naming only the first script left the "never imported by tests"
    claim asserted and unenforced for the rest. Adding a third gated script and forgetting the entry
    reopens exactly that, silently: `test_the_gated_script_rule_fires_on_every_script_it_names`
    plants one import per NAMED entry, so it goes on passing over a script nobody named.

    The two sides are independent on purpose. This reads `scripts/` off disk and greps each file for
    the environment key that gates it; the tuple is a literal. Deriving either from the other is the
    defect this repository has hit four times, and it would make the check agree with itself.
    """
    key = "RETINUE_LIVE"
    gated = sorted(p.stem for p in SCRIPTS.glob("*.py")
                   if key in p.read_text(encoding="utf-8"))
    assert gated, f"no {key}-gated script under {SCRIPTS}"
    assert gated == sorted(_GATED_SCRIPTS)

def test_the_gated_script_rule_fires_on_every_script_it_names(tmp_path):
    """One specimen per branch, which is the standard `tools/battery.sh` holds itself to.

    A tuple whose later entries never appear in a planted tree is a rule that reads broader than it
    is: retarget the second name at a script that exists nowhere and a one-specimen test still
    reports a clean pass with half the rule dead. Each name gets its own planted import, and the
    count is compared to the tuple's length so an entry that stops matching is a finding rather
    than a silence.
    """
    for i, script in enumerate(_GATED_SCRIPTS):
        (tmp_path / f"imports_{i}.py").write_text(f"from scripts.{script} import main\n",
                                                  encoding="utf-8")
    found = _gated_script_import_findings(tmp_path)
    assert len(found) == len(_GATED_SCRIPTS), found
    for script in _GATED_SCRIPTS:
        assert any(script in f for f in found), f"rule never fired for {script}"

def test_a_captured_payload_carries_the_agent_type_key():
    """The hook routes on `agent_type`, and the documented hook input does not list it.

    If no real payload ever carries the key, `decide` collapses to its main-thread arm, the ask
    branch is unreachable, and the module still fails closed - so the loss would be silent. ANY
    rather than ALL: the orchestrator's own spawn call is a main-thread call and legitimately
    carries no `agent_type`, which is the arm that returns "allow".
    """
    payloads = _captured_payloads()
    assert any("agent_type" in p for p in payloads), (
        f"none of {len(payloads)} captured payloads carries `agent_type`: the routing table has "
        "no subagent arm to route on and the ask branch is dead code")

def test_the_captured_session_is_the_topology_plus_nothing_ambient():
    """A capture taken on a machine whose settings reach the session is not canonical, whatever
    it happens to show - and it would otherwise become the canon quietly, since every fixture
    here is replayed forever.

    BOTH KEYS ARE PINNED NON-EMPTY BEFORE THE FINDINGS ARE TRUSTED, and that is not defensive
    padding. `_init_findings` reads `init.get(...) or ()` on each, so every rule below fires when
    its key is present and goes silent when it is absent or empty: measured, deleting either
    `payload.tools` or `payload.agents` from the fixture leaves the whole suite green, while
    appending an `mcp__` name to the tool list correctly reddens this row. `README.md` leaves
    `strict_mcp_config` unset BECAUSE the tool rule holds over this file, so a payload with no tool
    list would carry that reasoning on a check that read nothing. Truthiness rather than `in`,
    because an empty list is the same vacuity one step further down.

    This is `test_every_fixture_json_carries_provenance`'s own reasoning one level up, in the same
    words: absence of files is not evidence, and neither is absence of a key.
    """
    init = _captured_init()
    assert init.get("agents"), "the captured init lists no agents; the ambient-agent rule reads nothing"
    assert init.get("tools"), "the captured init lists no tools; the mcp-tool rule reads nothing"
    assert _init_findings(init) == []

def test_the_init_rules_fire_on_a_planted_session():
    assert any("init_declares_ambient_agents" in f
               for f in _init_findings({"agents": ["research", "someones-own-agent"]}))
    assert any("init_session_holds_an_mcp_tool" in f
               for f in _init_findings({"tools": ["Read", "mcp__mail__deliver"]}))
