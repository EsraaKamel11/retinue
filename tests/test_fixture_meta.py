"""Every frozen fixture carries a meta block; captured ones carry the version stamp.

`meta.provisional` had no expiry, and nothing else in this repository reads it, so a fixture
could be replaced by a real capture and go on claiming to be a placeholder for it forever. The
marking is made self-clearing here instead: a `captured_*` fixture that still says `provisional`
is a finding, and so is one carrying no version stamp.

A capture also records the operator's own transcript path, and this repository is read by people
who are not the operator. An edited capture is a weaker artifact than a raw one, so the rule below
does not forbid the edit - it forbids making it silently: a captured fixture carrying a home
directory path must say in its own meta that it was redacted.
"""
import json
import re
from pathlib import Path
import pytest

FIX = Path(__file__).resolve().parents[1] / "fixtures"
SMOKE = "RETINUE_LIVE=1 python scripts/capture_smoke.py"

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
    for p in sorted(root.rglob("*.json")):
        text = p.read_text(encoding="utf-8")
        meta = json.loads(text).get("meta") or {}
        if not meta:
            findings.append(f"no_meta_block: {p.name}")
            continue
        if not (meta.get("provisional") or meta.get("captured") or meta.get("hand_authored")):
            findings.append(f"no_provenance: {p.name}")
        if p.name.startswith("captured_"):
            if meta.get("provisional"):
                findings.append(f"captured_still_provisional: {p.name}")
            if not meta.get("captured"):
                findings.append(f"captured_without_version_stamp: {p.name}")
            if _HOME_PATH.search(text) and not meta.get("redacted"):
                findings.append(f"home_path_without_redaction: {p.name}")
    return findings

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
    # One planted file for both captured rules: marked provisional AND carrying no stamp.
    (tmp_path / "captured_99.json").write_text('{"meta": {"provisional": true}}', encoding="utf-8")
    # Stamped, not provisional, and carrying a home path it does not declare: this one isolates
    # the redaction rule, so its firing cannot be borrowed from any of the rules above.
    (tmp_path / "captured_98.json").write_text(
        '{"meta": {"captured": {"sdk": "x"}},'
        ' "payload": {"transcript_path": "C:\\\\Users\\\\someone\\\\s.jsonl"}}', encoding="utf-8")
    found = " ".join(_provenance_findings(tmp_path))
    for rule in ("no_meta_block", "no_provenance", "captured_still_provisional",
                 "captured_without_version_stamp", "home_path_without_redaction"):
        assert rule in found, f"rule never fired: {rule}"

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
