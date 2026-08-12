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

def test_an_exception_whose_message_cannot_be_rendered_is_still_signal_two():
    """Formatting the error is itself arbitrary code, and it runs INSIDE the handler.

    `f"{exc}"` calls `exc.__str__()`. A transport wrapping a driver or HTTP error whose message
    renders lazily from a resource that has since closed raises there, and a raise inside the
    handler escapes `annotate` as an uncaught error - turning the fail-closed signal two into the
    one thing this function exists not to do. The type name survives, so the report still says what
    went wrong.
    """
    class Unrenderable(Exception):
        def __str__(self):
            raise RuntimeError("this message renders from a resource that has closed")
    class TornChecker:
        def check(self, draft, record):
            raise Unrenderable()
    p = annotate(draft("Following up on our conversation."), Record(fields={}), ctx(),
                 TornChecker())
    assert p.outcome is None and p.error and routes_to_human(p)
    assert "Unrenderable" in p.error

def test_a_base_exception_is_not_converted_into_a_policy_answer():
    """The bound on the catch, stated as a test rather than as the word "never".

    `except Exception` does not catch `BaseException`, and that is the design `boundary/hook.py`
    already takes for cancellation: a torn-down call is not a call waiting on a human, and a
    reviewer handed "the pre-flight failed" for a shutdown is being told something untrue about the
    draft. This test passed when written; its red arm is the row that widens the catch.
    """
    class Cancelling:
        def check(self, draft, record):
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        annotate(draft("Following up on our conversation."), Record(fields={}), ctx(), Cancelling())

# The absence. Two signals means two, and the third candidate is right there in the payload the
# imported engine builds, so the module refusing to read it is a property of the module's code and
# not of what happens to be available to it. Each test below is one direction the pin has to hold
# in, and the two planted sources are the two ways the pin it replaces would have been wrong.

#: The complete census for the routing function, written out rather than derived, so nothing on the
#: left of the assertion moved when the module did. It reaches past the routing body because the
#: region is the whole definition: `Preflight` arrives through the parameter annotation and is
#: followed like any other module-level name, which is what puts a read in the class body inside
#: the routing census rather than outside it.
#:
#: Held in TWO directions, and the second is what makes the first refuse anything. The pin requires
#: the module's census to EQUAL this set; `test_a_docstring_naming_the_field_is_not_a_read` requires
#: a CLEAN planted module's census to equal it too. Widening the set to admit a new read leaves the
#: planted census where it was, so the second assertion reddens. That is the only construct that
#: fires on an arbitrary widening - a must-DIFFER control against a differently shaped snippet
#: cannot, because a widened superset still differs from the snippet.
ROUTING_READS = frozenset({"p", "outcome", "allow", "Preflight", "bool",
                           "dataclass", "frozen", "HookOutcome", "error", "str"})

#: The same for the annotation path, which the module's docstring also claims reads no field of the
#: self-rating. A claim scoped to routing alone would leave `annotate` unpinned while the docstring
#: spoke about the module. `": "` and the fallback sentence are literal fragments of the error
#: f-strings: a subscript key, a `getattr` argument and an f-string fragment are one node type, and
#: the census carries the noise rather than opening a hole to remove it.
#:
#: Held in two directions by the same construct as `ROUTING_READS`, and that is a repair. It had one
#: face, a must-DIFFER control, which is structurally incapable of firing on a widening: for any
#: superset of this set, the planted reintroduction's census still differs from it. So the single
#: edit "add the read, widen the set" left the suite green, which is verbatim the defect the commit
#: that introduced the control claimed to close.
ANNOTATE_READS = frozenset({
    "pre_tool_use", "SEND_TOOL", "draft", "record", "context", "checker", "Preflight", "outcome",
    "type", "exc", "Exception", "body", "__name__", "named", "described", ": ",
    ": the exception's own message could not be rendered",
    "an exception whose type would not name itself",
    "Draft", "Record", "ActContext", "dataclass", "frozen", "HookOutcome", "error", "str"})

#: The reference shape both expected sets are held against: the module's code with nothing removed
#: and nothing added but prose. Its job is to be an independent copy, so an expected set widened to
#: admit a new read stops matching it. The prose names the field the module refuses to read, which
#: is the second thing this source pins: a mention is not a read, and a text search could not tell
#: the difference.
#:
#: INDEPENDENT, not immovable, and the difference is the standing cost of this pin. An earlier note
#: here said it does not move when the module moves. It is hand-maintained and lives beside the sets
#: it guards, so every legitimate change to the module forces an edit here too - which trains the
#: exact motion a widening needs, on a reader who has just been told the edit is routine. The
#: protection is that the edit must be made twice, in two shapes, by someone who would have to
#: choose to widen both.
#:
#: One dependency worth naming because no pin names it: the class body is censused only because the
#: router's parameter carries `: Preflight`. Drop that annotation from the module AND from this
#: source AND narrow both sets, and the class body leaves the routing census with the suite green.
#: Three coordinated edits rather than one, so it is not a disarm, but it is the thinnest thread
#: here and it is not held by anything that would notice on its own.
PLANTED_CLEAN_MODULE = '''
@dataclass(frozen=True)
class Preflight:
    outcome: HookOutcome | None
    error: str | None

def annotate(draft: Draft, record: Record, context: ActContext, checker) -> Preflight:
    """The checker's confidence deliberately routes nothing, and this sentence is why the pin is a
    census rather than a text search."""
    try:
        outcome = pre_tool_use(SEND_TOOL, {"body": draft.body}, (draft, record, context, checker))
        return Preflight(outcome, None)
    except Exception as exc:
        try:
            named = type(exc).__name__
        except Exception:
            named = "an exception whose type would not name itself"
        try:
            described = f"{named}: {exc}"
        except Exception:
            described = f"{named}: the exception's own message could not be rendered"
        return Preflight(None, described)

def routes_to_human(p: Preflight) -> bool:
    """Confidence is named here as well, and the census still does not see it."""
    if p.outcome is None:
        return True
    return not p.outcome.allow
'''

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

PLANTED_DECORATOR = '''
def _gate(fn):
    return fn

@_gate
def routes_to_human(p):
    if p.outcome is None:
        return True
    return not p.outcome.allow
'''

PLANTED_ANNOTATE_READ = '''
def annotate(draft, record, context, checker):
    outcome = pre_tool_use(SEND_TOOL, {"body": draft.body}, (draft, record, context, checker))
    if outcome.payload and outcome.payload.get("confidence"):
        return Preflight(None, "the checker was unsure")
    return Preflight(outcome, None)
'''

# Three constructs that decide routing from OUTSIDE a function's body. Each planted source below
# carries a live read that suppresses routing when the self-rating is under 0.5, and each was
# measured green against a census that walked bodies and decorators only - so these are holes that
# were open, not shapes somebody imagined. The routing body in the second and third is byte for
# byte the shipped one.

PLANTED_DEFAULT_READ = '''
def routes_to_human(p, _unsure=lambda o: (o.payload or {}).get("confidence", 1.0) < 0.5):
    if p.outcome is None:
        return True
    return not p.outcome.allow
'''

PLANTED_CLASS_BODY_READ = '''
@dataclass(frozen=True)
class Preflight:
    outcome: object
    error: object
    def __post_init__(self):
        if (self.outcome.payload or {}).get("confidence", 1.0) < 0.5:
            object.__setattr__(self, "outcome", HookOutcome(allow=True, payload=None))

def routes_to_human(p: Preflight) -> bool:
    if p.outcome is None:
        return True
    return not p.outcome.allow
'''

PLANTED_REBOUND_ENTRY = '''
def _timed(fn):
    def inner(p):
        if (p.outcome.payload or {}).get("confidence", 1.0) < 0.5:
            return False
        return fn(p)
    return inner

def routes_to_human(p: Preflight) -> bool:
    if p.outcome is None:
        return True
    return not p.outcome.allow

routes_to_human = _timed(routes_to_human)
'''

#: The module's top-level statements, exhaustively. This is one half of the argument that the two
#: censuses cover everything that executes: the other half is that each census walks the WHOLE
#: subtree of a definition, so between them nothing in the file is outside a censused region.
#: Conditional definition, a module `__getattr__`, a duplicate def and any module-level statement
#: that runs at import all change this tuple.
MODULE_SHAPE = (
    ("Expr", "<docstring>"),
    ("ImportFrom", "__future__"),
    ("ImportFrom", "dataclasses"),
    ("ImportFrom", "chaperone.gates.hook"),
    ("ImportFrom", "chaperone.policy.act_classes"),
    ("ImportFrom", "chaperone.policy.types"),
    ("ImportFrom", "retinue.boundary.hook"),
    ("ClassDef", "Preflight"),
    ("FunctionDef", "annotate"),
    ("FunctionDef", "routes_to_human"),
)

def reachable_reads(source: str, entry: str) -> frozenset[str]:
    """Every name the code reachable from `entry` could read a field by.

    Collected off the parsed source rather than its text: attribute names, string constants, keyword
    argument names, and every identifier the code names. Identifiers are in the census because a
    field can be read through a call - `getattr(p.outcome, "confidence")` names no attribute node,
    and `getattr(p.outcome, "conf" + "idence")` names no matching constant either, so both are
    caught by the arrival of `getattr` itself. Calls into module-level functions are followed, so a
    read moved one line out into a helper is still counted.

    **The region is the whole definition, and that is the coverage argument rather than a list.**
    `ast.walk(definition)` is the definition's entire subtree, so the census does not choose which
    fields of a `def` to look at and cannot leave one out: decorators, positional and keyword-only
    defaults, parameter and return annotations, nested definitions and the body are all inside it
    by construction. The first version walked `body`, then `decorator_list + body`, and each time
    the field it had not thought of was a live escape - a default holding a lambda, a class doing
    the deciding - which is why the region is now stated as a subtree instead of a list of fields.
    Every module-level name the region touches is followed the same way, whether it is bound by a
    `def` or by a `class`.

    Two bounds it does not cover, named because they are otherwise invisible and because a
    coverage claim with unnamed edges is the claim this pin was rewritten for:

    - **What the module BINDS its names to.** A census keyed on the `def` walks that `def` even
      when the module exports something else, so `routes_to_human = _timed(routes_to_human)` is
      invisible here. `top_level_bindings` is the pin for it and `module_shape` is the pin that
      stops any other module-level statement appearing at all. The three compose: nothing inside a
      definition is outside a census, and nothing at module level is outside a definition.
    - **Imported code.** `pre_tool_use` arrives by name and its body is not censused. That is
      deliberate - the imported engine reads the self-rating, which is exactly the thing this
      module must receive and must not route on. An earlier version of this sentence added that
      `module_shape` pins the import list so the name cannot be swapped quietly. That is false, and
      measured false: `module_shape` labels an `ImportFrom` by `node.module` alone and never reads
      `node.names` or `asname`, so `import HookOutcome, denial_result as pre_tool_use` moves none of
      the three pins. What `module_shape` pins is WHICH MODULES are imported, not which names are
      bound out of them. The swap is refused behaviourally instead: run either alias swap and six
      tests redden. Nothing here is a claim about behaviour at runtime either - a monkeypatch from
      outside the module is not a property of this source.

    Docstrings and bare string statements are dropped, and comments never enter an AST at all, so
    prose is free. That is the trade this census makes against a text search, and it is the trade
    `tools/fleet_audit.py` already takes: a mention is not a read.

    Raises rather than returning an empty set for an entry it cannot resolve. Every failure mode of
    an analysis like this one is silence, and silence here reads as a module that touches nothing.
    """
    tree = ast.parse(source)
    defs = {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    if entry not in defs:
        raise LookupError(f"{entry!r} is not a module-level definition of the parsed source; "
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
        for node in ast.walk(defs[name]):
            if isinstance(node, ast.Attribute):
                reads.add(node.attr)
            elif isinstance(node, ast.Name):
                reads.add(node.id)
                if node.id in defs:
                    pending.append(node.id)
            elif isinstance(node, ast.keyword) and node.arg:
                reads.add(node.arg)
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in prose):
                reads.add(node.value)
    return frozenset(reads)

def module_shape(source: str) -> tuple[tuple[str, str], ...]:
    """Every top-level statement as (node type, the name it introduces). Exhaustive by walking
    `tree.body` rather than by looking for shapes considered suspicious: a construct nobody
    anticipated still appears, as a row that is not in the expected tuple.
    """
    out: list[tuple[str, str]] = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            label = node.name
        elif isinstance(node, ast.ImportFrom):
            label = node.module or ""
        elif isinstance(node, ast.Import):
            label = ",".join(alias.name for alias in node.names)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            label = "<docstring>"
        else:
            label = ",".join(sorted(_bound_names(node)))
        out.append((type(node).__name__, label))
    return tuple(out)

def _bound_names(node: ast.stmt) -> set[str]:
    """The module-level names one statement rebinds by assignment."""
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()

def top_level_bindings(source: str, name: str) -> tuple[str, ...]:
    """Every top-level statement that binds `name`, in order, as node type names.

    `("FunctionDef",)` is the only answer that means "this name is the function the census walked".
    Two entries means a shadowing redefinition; an `Assign` in the tuple means the module exports
    something the census never looked at. Scoped to `tree.body` because `module_shape` is what
    refuses an `if` or a `try` at module level, and the two are only sound together.
    """
    kinds: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                kinds.append(type(node).__name__)
        elif name in _bound_names(node):
            kinds.append(type(node).__name__)
    return tuple(kinds)

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

def test_a_self_rating_read_on_the_annotation_path_differs_from_the_expected_census():
    """`ANNOTATE_READS` in the must-DIFFER direction, which is what stops one edit from disarming
    it. Used only by the pin above, it could be widened in the same commit that adds the read it
    was meant to refuse, and nothing would redden - the state where the pin still exists and
    refuses nothing. `ROUTING_READS` is held by two tests facing opposite ways; this is the
    matching second face for the annotation path.
    """
    reads = reachable_reads(PLANTED_ANNOTATE_READ, "annotate")
    assert {"payload", "get", "confidence"} <= reads
    assert reads != ANNOTATE_READS

def test_a_read_moved_into_a_helper_is_still_counted():
    """Routing that calls one line out into a helper is still routing. Calls into module-level
    functions are followed, or the pin would be one refactor away from measuring an empty body.
    """
    assert "confidence" in reachable_reads(PLANTED_HELPER, "routes_to_human")

def test_a_decorator_wrapping_the_routing_is_censused():
    """A decorator is the same escape as the helper, one line higher up. It never appears in the
    function's body, so a census reading `body` alone is blind to a wrapper that consults the
    payload and returns early - and the wrapper decides the routing just as much as the body does.
    """
    reads = reachable_reads(PLANTED_DECORATOR, "routes_to_human")
    assert "_gate" in reads and reads != ROUTING_READS

def test_a_default_argument_value_is_censused():
    """A default is evaluated at definition time and bound into the function, so a lambda sitting
    in one is code the routing carries. It lives in neither the body nor the decorator list.
    """
    assert "confidence" in reachable_reads(PLANTED_DEFAULT_READ, "routes_to_human")

def test_a_read_in_the_class_the_router_names_is_censused():
    """The routing body here is byte for byte the shipped one; the class it takes decides instead.
    A `__post_init__` that rewrites the outcome when the self-rating is low suppresses routing
    without a single character of the router changing, so the type the router names has to be
    followed like any other module-level name.
    """
    assert "confidence" in reachable_reads(PLANTED_CLASS_BODY_READ, "routes_to_human")

def test_a_rebound_entry_is_refused_even_though_its_census_is_innocent():
    """The escape the census structurally cannot see, and the reason a second pin exists.

    A census keyed on the `def` walks the innocent body while the module exports something else.
    The first assertion witnesses exactly that - the wrapper suppresses routing under 0.5 and the
    census is still the shipped set - so the refusal below is closing something live. The realistic
    route in is not adversarial: someone wraps the router in telemetry by assignment and the
    wrapper carries a "do not bother a human when the checker was unsure" short-circuit.
    """
    assert "confidence" not in reachable_reads(PLANTED_REBOUND_ENTRY, "routes_to_human")
    assert top_level_bindings(PLANTED_REBOUND_ENTRY, "routes_to_human") != ("FunctionDef",)

def test_the_module_binds_each_censused_entry_by_its_def_and_nothing_else():
    source = inspect.getsource(preflight)
    assert top_level_bindings(source, "routes_to_human") == ("FunctionDef",)
    assert top_level_bindings(source, "annotate") == ("FunctionDef",)

def test_the_module_runs_nothing_at_import_beyond_its_declared_shape():
    """The other half of the coverage argument. Each census walks a whole definition subtree, so
    nothing inside a definition is outside a census; this says there is nothing at module level
    except those definitions and the imports, so nothing is outside a definition either.
    """
    assert module_shape(inspect.getsource(preflight)) == MODULE_SHAPE

def test_a_docstring_naming_the_field_is_not_a_read():
    """Two jobs, and the second is the load-bearing one. Delete this as commentary and the routing
    pin stops refusing anything.

    The payoff: the module is free to say plainly what it refuses to read, because docstrings are
    dropped and comments never reach an AST. That is the trade against a text search.

    The pin: this is the SECOND FACE of `ROUTING_READS`. The census on the left comes from a clean
    reference module that does not move when the shipped module moves, so widening the expected set
    to admit a new read reddens here even though the module's own pin was widened to match. No
    must-DIFFER control can do this job - a widened superset still differs from a reintroduction.
    """
    assert reachable_reads(PLANTED_CLEAN_MODULE, "routes_to_human") == ROUTING_READS

def test_the_expected_annotation_census_is_held_by_a_clean_planted_annotate():
    """`ANNOTATE_READS`'s second face, and the repair of a defect a previous commit claimed closed.

    The must-DIFFER control below cannot fire on a widening, because a superset of this set still
    differs from a planted reintroduction's census. This can: the reference module's census is
    fixed, so any widening stops matching it. Measured end to end as R15, where the read is added
    to `annotate` and the set widened to the module's new census in the same mutation.
    """
    assert reachable_reads(PLANTED_CLEAN_MODULE, "annotate") == ANNOTATE_READS

def test_an_entry_that_resolves_to_nothing_raises_rather_than_censusing_nothing():
    """The only control on the two pins measuring anything at all. A misspelled or renamed entry
    walks no body, and an empty census equals no expected set - but a subset pin would have passed,
    and so would any pin whose failure mode is silence.
    """
    with pytest.raises(LookupError, match="not a module-level definition"):
        reachable_reads(inspect.getsource(preflight), "routes_to_humans")
