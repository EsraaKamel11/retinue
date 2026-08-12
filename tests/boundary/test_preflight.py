"""The pre-flight review surface: the would-be verdict, and the two signals that route on it.

Every draft reaches the human reviewer already annotated with the verdict it would have received,
so the full predicate set runs here with the checker included and nothing executed. What is
asserted is the annotation and the routing disjunction - never whether a verdict is correct, which
is a measured question and not a structural one.

The third thing asserted is an absence. Two signals means two, so the checker's confidence score
routes nothing, and an absence has to be pinned structurally or it is not pinned at all. The pin
is a census of every name the module's code touches, parsed rather than searched, for the reason
`tools/fleet_audit.py` gives for its own import rules: a text search cannot tell a read from a
mention, so it would have caught a docstring explaining the refusal while missing the same read
under a renamed field. Both directions are planted below.
"""
import ast
import inspect
from pathlib import Path
import pytest
from chaperone.policy.act_classes import ActContext
from chaperone.policy.types import Draft, Message, Record
from retinue.boundary import preflight
from retinue.boundary.checker_lane import build_checker, scripted_transport
from retinue.boundary.hook import SEND_TOOL
from retinue.boundary.preflight import annotate, routes_to_human

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "verdicts" / "checker_scripted.json"

VIOLATING = "Honestly, this company is a great investment and you should take the allocation."

def draft(body):
    return Draft(thread=(Message(role="investor", body="hello"),), body=body, cited_fields=(),
                 recipient_jurisdiction="US", recipient_domain="example.test", tool_name=SEND_TOOL)

def ctx():
    return ActContext(approval_token="tok-1", tier=2, consented_jurisdictions=frozenset({"US"}),
                      granted_tools=frozenset({SEND_TOOL}), sent_count=0, send_cap=5)

def checker():
    return build_checker(scripted_transport(FIX))

def test_clean_draft_annotates_allow_and_does_not_route():
    p = annotate(draft("Following up on our conversation."), Record(fields={}), ctx(), checker())
    assert p.outcome.allow and not routes_to_human(p)

def test_signal_one_checker_denial_routes():
    p = annotate(draft(VIOLATING), Record(fields={}), ctx(), checker())
    assert not p.outcome.allow and routes_to_human(p)

def test_an_unavailable_checker_is_a_routed_denial_not_an_annotation_failure():
    """The imported engine converts CheckerUnavailable into a denial carrying `outage`; the
    annotation SUCCEEDED at reporting it, so this is signal ONE, not signal two.

    The payload is read as well as the flag, because every assertion above it holds for a denial
    of any kind: a test named for the outage that would pass on an act-class refusal is not
    measuring the distinction it is named for. `detail` is the imported engine's own wording and
    pinning it is deliberate - if the wording moves, a reader learns the outage now arrives
    somewhere else, which is worth a red.
    """
    p = annotate(draft("A body no frozen verdict covers."), Record(fields={}), ctx(), checker())
    assert p.outcome is not None and not p.outcome.allow and routes_to_human(p)
    assert "unavailable" in p.outcome.payload["detail"]

def test_signal_two_annotation_failure_routes():
    class ExplodingChecker:
        def check(self, draft, record):
            raise RuntimeError("annotation tore")
    p = annotate(draft("Following up on our conversation."), Record(fields={}), ctx(),
                 ExplodingChecker())
    assert p.outcome is None and p.error and routes_to_human(p)

# The absence. Two signals means two, and the third candidate is right there in the payload the
# imported engine builds, so the module refusing to read it is a property of the module's code and
# not of what happens to be available to it. Each test below is one direction the pin has to hold
# in, and the two planted sources are the two ways the pin it replaces would have been wrong.

#: The complete census for the routing function, written out rather than derived, so nothing on the
#: left of the assertion moved when the module did. Used in two directions: the pin below requires
#: the module's census to EQUAL it, and the renamed-field control requires a reintroduction's census
#: to DIFFER from it. Widening this set to admit a new read therefore reddens the control, which is
#: the state where the pin still exists but no longer refuses anything.
ROUTING_READS = frozenset({"p", "outcome", "allow"})

#: The same for the annotation path, which the module's docstring also claims reads no field of the
#: self-rating. A claim scoped to routing alone would leave `annotate` unpinned while the docstring
#: spoke about the module. `": "` is a literal fragment of the error f-string: a subscript key, a
#: `getattr` argument and an f-string fragment are one node type, and the census carries the noise
#: rather than opening a hole to remove it.
ANNOTATE_READS = frozenset({"pre_tool_use", "SEND_TOOL", "draft", "record", "context", "checker",
                            "Preflight", "outcome", "type", "exc", "Exception", "body",
                            "__name__", ": "})

PLANTED_RENAME = '''
def routes_to_human(p):
    if p.outcome.payload["certainty"] < 0.5:
        return False
    return not p.outcome.allow
'''

PLANTED_HELPER = '''
def _low(p):
    return p.outcome.payload["confidence"] < 0.5

def routes_to_human(p):
    return _low(p) or not p.outcome.allow
'''

PLANTED_PROSE = '''
def routes_to_human(p):
    """The checker's confidence deliberately routes nothing, and this sentence is why the pin is a
    census rather than a text search."""
    if p.outcome is None:
        return True
    return not p.outcome.allow
'''

def reachable_reads(source: str, entry: str) -> frozenset[str]:
    """Every name the code reachable from `entry` could read a field by.

    Collected off the parsed source rather than its text: attribute names, string constants, keyword
    argument names, and every identifier the code names. Identifiers are in the census because a
    field can be read through a call - `getattr(p.outcome, "confidence")` names no attribute node,
    and `getattr(p.outcome, "conf" + "idence")` names no matching constant either, so both are
    caught by the arrival of `getattr` itself. Calls into module-level functions are followed, so a
    read moved one line out into a helper is still counted.

    Docstrings and bare string statements are dropped, and comments never enter an AST at all, so
    prose is free. That is the trade this census makes against a text search, and it is the trade
    `tools/fleet_audit.py` already takes: a mention is not a read.

    Raises rather than returning an empty set for an entry it cannot resolve. Every failure mode of
    an analysis like this one is silence, and silence here reads as a module that touches nothing.
    """
    tree = ast.parse(source)
    funcs = {n.name: n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if entry not in funcs:
        raise LookupError(f"{entry!r} is not a module-level function of the parsed source; "
                          "an entry that resolves to nothing walks no body and censuses nothing")
    prose = {id(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str)}
    reads: set[str] = set()
    pending, visited = [entry], set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for statement in funcs[name].body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Attribute):
                    reads.add(node.attr)
                elif isinstance(node, ast.Name):
                    reads.add(node.id)
                    if node.id in funcs:
                        pending.append(node.id)
                elif isinstance(node, ast.keyword) and node.arg:
                    reads.add(node.arg)
                elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and id(node) not in prose):
                    reads.add(node.value)
    return frozenset(reads)

def test_confidence_routes_nothing_structurally():
    """Equality, not containment. A subset assertion is satisfied by an empty census, so an
    analysis that found nothing would score as a module that read nothing - the shape where a test
    gets greener as it measures less. Equality also refuses a read being REMOVED, which is the
    mutation that makes the disjunction answer on one signal.
    """
    assert reachable_reads(inspect.getsource(preflight), "routes_to_human") == ROUTING_READS

def test_the_annotation_path_reads_no_self_rating_either():
    assert reachable_reads(inspect.getsource(preflight), "annotate") == ANNOTATE_READS

def test_the_self_rating_is_really_in_the_payload_to_be_routed_on():
    """The pin guards something live. The imported engine writes the checker's own numeric score
    into the denial payload, so routing on it is one field access away rather than a shape somebody
    imagined - and this test is the only reason the two pins above measure a refusal at all.
    """
    p = annotate(draft(VIOLATING), Record(fields={}), ctx(), checker())
    assert "confidence" in p.outcome.payload["detail"]

def test_a_renamed_self_rating_is_caught_where_a_text_search_would_miss_it():
    """The row that earns the census. The planted routing reads the same number under another
    name: a search for the word is silent on it, and the census names it.
    """
    assert "confidence" not in PLANTED_RENAME              # the text search stays quiet
    reads = reachable_reads(PLANTED_RENAME, "routes_to_human")
    assert {"payload", "certainty"} <= reads               # the census does not
    assert reads != ROUTING_READS                          # so the pin reddens

def test_a_read_moved_into_a_helper_is_still_counted():
    """Routing that calls one line out into a helper is still routing. Calls into module-level
    functions are followed, or the pin would be one refactor away from measuring an empty body.
    """
    assert "confidence" in reachable_reads(PLANTED_HELPER, "routes_to_human")

def test_a_docstring_naming_the_field_is_not_a_read():
    """The payoff, and the whole reason the pin is not a text search: the module is free to say
    plainly what it refuses to read. Comments never reach an AST; docstrings are dropped here.
    """
    assert reachable_reads(PLANTED_PROSE, "routes_to_human") == ROUTING_READS

def test_an_entry_that_resolves_to_nothing_raises_rather_than_censusing_nothing():
    """The only control on the two pins measuring anything at all. A misspelled or renamed entry
    walks no body, and an empty census equals no expected set - but a subset pin would have passed,
    and so would any pin whose failure mode is silence.
    """
    with pytest.raises(LookupError, match="not a module-level function"):
        reachable_reads(inspect.getsource(preflight), "routes_to_humans")
