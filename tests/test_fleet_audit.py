from pathlib import Path
import shutil, subprocess, sys
from tools.fleet_audit import audit

ROOT = Path(__file__).resolve().parents[1]

def test_the_real_tree_is_clean():
    assert audit(ROOT / "src" / "retinue") == []

def test_gates_import_outside_boundary_is_caught(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "specialists"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("from chaperone.gates.hook import guarded_call\n")
    findings = audit(tmp_path / "src" / "retinue")
    assert any("specialists_import_no_gates" in f for f in findings)

def test_a_plain_import_of_audit_outside_boundary_is_caught(tmp_path):
    # The gate rule's OTHER label, and three paths the test above never walks: the
    # `only_boundary_imports_gates` name (chosen for any non-boundary directory that is not
    # specialists/), the `ast.Import` node type (the test above plants an `ImportFrom`), and the
    # `chaperone.audit` prefix. A label no test has seen fire could be misspelled, or its branch
    # unreachable, with every other test in this file still green.
    pkg = tmp_path / "src" / "retinue" / "orchestration"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("import chaperone.audit.record\n")
    findings = audit(tmp_path / "src" / "retinue")
    assert any("only_boundary_imports_gates" in f for f in findings)

def test_a_mention_in_a_docstring_is_not_an_import(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "specialists"; pkg.mkdir(parents=True)
    (pkg / "ok.py").write_text('"""chaperone.gates.hook is discussed here, not imported."""\n')
    assert audit(tmp_path / "src" / "retinue") == []          # grep would flag this; AST must not

def test_send_tool_literal_outside_boundary_is_caught(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "orchestration"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("TOOL = 'send_message'\n")      # single quotes: grep-proof, AST-caught
    findings = audit(tmp_path / "src" / "retinue")
    assert any("send_tool_single_home" in f for f in findings)

def test_a_send_tool_mention_in_a_docstring_is_not_a_definition(tmp_path):
    pkg = tmp_path / "src" / "retinue" / "orchestration"; pkg.mkdir(parents=True)
    (pkg / "ok.py").write_text('"""The send_message tool is discussed here, not defined."""\n')
    assert audit(tmp_path / "src" / "retinue") == []              # equality, not substring

def test_cli_exit_codes(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "fleet_audit.py")], capture_output=True)
    assert r.returncode == 0
    # The other arm. `sys.exit(1 if found else 0)` has two branches and the clean tree only ever
    # walks one of them, so the exit-1 path is asserted here against a COPY of the script over a
    # planted tree - the copy resolves its own root, which leaves the real tree untouched. The rule
    # name is read out of stderr as well as the code, because an unhandled exception in the copy
    # would exit 1 too and a returncode-only assertion would accept that as a pass.
    tools = tmp_path / "tools"; tools.mkdir()
    shutil.copy(ROOT / "tools" / "fleet_audit.py", tools / "fleet_audit.py")
    pkg = tmp_path / "src" / "retinue" / "specialists"; pkg.mkdir(parents=True)
    (pkg / "evil.py").write_text("from chaperone.gates.hook import guarded_call\n")
    r = subprocess.run([sys.executable, str(tools / "fleet_audit.py")], capture_output=True)
    assert r.returncode == 1
    assert b"specialists_import_no_gates" in r.stderr
