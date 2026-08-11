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
import json
import re
from pathlib import Path
import pytest

FIX = Path(__file__).resolve().parents[1] / "fixtures"
TESTS = Path(__file__).resolve().parent
SMOKE = "RETINUE_LIVE=1 python scripts/capture_smoke.py"

#: Exactly one of these, never two. "At least one" would let a fixture declare itself both
#: captured and hand-authored, which is not a provenance but a pair of incompatible claims.
_PROVENANCE = ("provisional", "captured", "hand_authored")

#: A provisional fixture's note names the capture that will retire it; this pairs that claim with
#: where that capture's outputs land. The direction is the point: `captured_still_provisional`
#: keys on the `captured_` prefix and so catches a capture calling itself a placeholder, while the
#: staleness that actually occurred wears the `provisional_` prefix - a placeholder outliving the
#: capture meant to replace it. A note reworded past this phrase goes silent, which is why the arm
#: carries a planted control. The P4 demo capture earns a row here when it defines its output
#: names; until it runs, `provisional_send.json`'s note is still true.
_SUPERSEDED_BY = (("P1 capture smoke", "captured_*.json"),)

#: Matched against the RAW file text, not the decoded values: a Windows path inside JSON is
#: always backslash-escaped, so `C:\\Users\\` is what is actually on disk. A redacted fixture
#: still matches this pattern, because the placeholder keeps the path's shape - which is the
#: point. Only the pairing of a home path with no declared redaction is a finding.
_HOME_PATH = re.compile(r"[A-Za-z]:\\\\Users\\\\|/home/|/Users/")

def _provenance_findings(root: Path) -> list[str]:
    """One named rule per finding, over ANY fixture tree - so each rule can be shown firing on a
    planted one. Silence over the real tree is what a correct rule and an unreachable rule look
    like alike."""
    findings: list[str] = []
    sessions: dict[str, list[str]] = {}
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
            session = (doc.get("payload") or {}).get("session_id")
            if session:
                sessions.setdefault(session, []).append(p.name)
        if p.name.startswith("provisional_"):
            note = meta.get("note") or ""
            for phrase, pattern in _SUPERSEDED_BY:
                if phrase in note and any(root.rglob(pattern)):
                    findings.append(f"provisional_superseded_by_capture: {p.name}")
    if len(sessions) > 1:
        # A later run writing fewer payloads leaves the previous run's higher-numbered files in
        # place. The write happens in a `finally` precisely because a live capture is not
        # repeatable, so the guard against mixing two corpora belongs here rather than in a
        # destructive pre-clear inside the script.
        findings.append(f"captured_sessions_mixed: {sorted(sessions.values())}")
    return findings

def _smoke_import_findings(root: Path) -> list[str]:
    """An import STATEMENT naming the capture smoke, told apart from a mention of one.

    The skip reason below names `scripts/capture_smoke.py` in a string, and a grep cannot tell
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
            if any("capture_smoke" in n for n in names):
                findings.append(f"test_imports_capture_smoke: {py.name}:{node.lineno}")
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
    mcp = sorted(t for t in (init.get("tools") or ()) if t.startswith("mcp__"))
    if mcp:
        findings.append(f"init_session_holds_an_mcp_tool: {mcp}")
    return findings

def _captured_init() -> dict:
    p = FIX / "payloads" / "captured_init.json"
    if not p.is_file():
        pytest.skip(f"no captured system:init at {p}; produce it with: {SMOKE}")
    return json.loads(p.read_text(encoding="utf-8"))["payload"]

def _captured_payloads() -> list[dict]:
    paths = sorted(FIX.glob("payloads/captured_*.json"))
    if not paths:
        pytest.skip(f"no captured payloads in {FIX / 'payloads'}; produce them with: {SMOKE}")
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
    # Two captures from two different runs, which is the mixed-corpus hazard.
    (tmp_path / "captured_70.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}}, "payload": {"session_id": "run-a"}}',
        encoding="utf-8")
    (tmp_path / "captured_71.json").write_text(
        '{"meta": {"captured": {"sdk": "x", "cli": "y"}}, "payload": {"session_id": "run-b"}}',
        encoding="utf-8")
    # A placeholder naming a capture that the same tree shows has since run.
    (tmp_path / "provisional_stale.json").write_text(
        '{"meta": {"provisional": true, "note": "hand-authored; replaced by the P1 capture smoke"}}',
        encoding="utf-8")
    found = " ".join(_provenance_findings(tmp_path))
    for rule in ("no_meta_block", "no_provenance", "ambiguous_provenance",
                 "captured_still_provisional", "captured_without_version_stamp",
                 "captured_stamp_unresolved", "home_path_without_redaction",
                 "captured_sessions_mixed", "provisional_superseded_by_capture"):
        assert rule in found, f"rule never fired: {rule}"

def test_a_lone_hand_authored_marking_is_the_accepted_third_provenance(tmp_path):
    # Without this, `hand_authored` can be deleted from the accepted set and the whole suite still
    # passes: no fixture declares it and no planted tree plants it. A disjunct no test exercises
    # is not a contract, and this file's entire job is provenance.
    (tmp_path / "hand.json").write_text('{"meta": {"hand_authored": true}}', encoding="utf-8")
    assert _provenance_findings(tmp_path) == []

def test_no_test_module_imports_the_capture_smoke():
    assert _smoke_import_findings(TESTS) == []

def test_the_smoke_import_rule_tells_an_import_from_a_mention(tmp_path):
    (tmp_path / "mentions.py").write_text('SMOKE = "scripts/capture_smoke.py"\n', encoding="utf-8")
    assert _smoke_import_findings(tmp_path) == []      # a grep flags this; the parse must not
    (tmp_path / "imports.py").write_text("from scripts.capture_smoke import main\n",
                                         encoding="utf-8")
    assert any("imports.py" in f for f in _smoke_import_findings(tmp_path))

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
    here is replayed forever."""
    assert _init_findings(_captured_init()) == []

def test_the_init_rules_fire_on_a_planted_session():
    assert any("init_declares_ambient_agents" in f
               for f in _init_findings({"agents": ["research", "someones-own-agent"]}))
    assert any("init_session_holds_an_mcp_tool" in f
               for f in _init_findings({"tools": ["Read", "mcp__mail__deliver"]}))
