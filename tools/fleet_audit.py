"""Import discipline as AST rules - one named rule per check, each with a planted-violation test
proving it fires. Grep is defeated by quoting style, f-strings, docstrings and comments, and
cannot tell an import from a mention; walking Import/ImportFrom and Constant nodes can."""
from __future__ import annotations
import ast, sys
from pathlib import Path

GATE_MODULES = ("chaperone.gates", "chaperone.audit")   # prefixes: EVERY gates/audit submodule counts
SEND_TOOL_LITERAL = "send" + "_message"                 # constructed: this file lives outside boundary/

def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            # `from chaperone import gates` names the gate surface in node.names, never in
            # node.module, so a rule reading only the module stays silent on the most ordinary
            # spelling of the import it exists to forbid.
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out

def _names_send_tool(tree: ast.AST) -> bool:
    """String CONSTANTS equal to the send-tool name - equality, not substring, so a docstring
    discussing the tool is not a hit while a single-quoted or f-string definition is."""
    return any(isinstance(n, ast.Constant) and n.value == SEND_TOOL_LITERAL
               for n in ast.walk(tree))

def audit(root: Path) -> list[str]:
    # A missing root makes rglob yield nothing, so every rule passes, the CLI exits 0 and the
    # battery never reddens again - the guardrail failing silent exactly when the package it
    # guards has been moved or renamed. Absence of files is not evidence of discipline.
    if not root.is_dir():
        return [f"audit_root_missing: {root}"]
    findings: list[str] = []
    send_homes: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        tree = ast.parse(py.read_text(encoding="utf-8"))
        gate_hits = [m for m in _imports(tree) if any(m.startswith(g) for g in GATE_MODULES)]
        if gate_hits and rel.parts[0] != "boundary":
            rule = ("specialists_import_no_gates" if rel.parts[0] == "specialists"
                    else "only_boundary_imports_gates")
            findings.append(f"{rule}: {rel} imports {sorted(gate_hits)}")
        if _names_send_tool(tree) and rel.parts[0] != "boundary":
            send_homes.append(str(rel))
    if send_homes:
        findings.append(f"send_tool_single_home: send tool named outside boundary/: {send_homes}")
    return findings

if __name__ == "__main__":
    # THE ROOT IS `src/retinue` AND NOTHING ELSE, which bounds what these rules may be offered as.
    # `README.md` calls them the substitute for a purity audit the vendored wheel does not ship, and
    # the substitution is partial in one direction worth naming: every rule here is import-shaped, so
    # what it can see is what a module IMPORTS. Policy logic written inline, importing nothing, is
    # invisible to all of them, and so is everything under `tests/`, `tools/` and `scripts/`, which
    # this root does not reach. A clean run says no module outside boundary/ reaches the gate surface
    # or names the send tool; it does not say this package holds no policy of its own.
    found = audit(Path(__file__).resolve().parents[1] / "src" / "retinue")
    for f in found:
        print(f, file=sys.stderr)
    sys.exit(1 if found else 0)
