#!/usr/bin/env python
"""Hard-zero gate: no ``datrix-codegen-*`` package may de-duplicate a handler name.

Every REST handler / controller method name is derived ONCE, in the shared
API-level derivation (``datrix_common.generation.api_helpers``:
``compute_rest_api_handler_names`` / ``rest_api_handler_names_by_endpoint``).
That derivation REFUSES to hand two endpoints of one ``rest_api`` a single
name: it raises, naming both routes, so the author disambiguates the ``@path``.

A package-local de-duplicator does the opposite. It renames one side of the
collision -- ``getOrders`` / ``getOrders2``, ``GetOrders`` / ``GetOrders2`` --
and every OTHER consumer of that route (the browser client, the API test
generator, the other language targets) keeps calling it by the un-numbered
name. The collision is hidden, not resolved, and the sides silently drift.
This shipped in three packages before it was retired.

The detected shape, matched by AST rather than text, has three parts and needs
all three:

1. **A numeric-suffix allocation loop.** A ``while <expr> in <container>``
   whose body increments an integer counter, where that counter is
   interpolated into a string-building expression that is either the loop
   test's left operand or the value of an assignment inside the loop.
2. **An accumulating container.** The container is named like a claim
   accumulator (``used``, ``seen``, ``taken``, ``claimed``, ``existing``, ...)
   or the enclosing function mutates it (``.add``/``.append``/``.update``/
   ``|=``/item assignment). This is what makes the rename order-dependent and
   invisible to every other consumer of the name.
3. **A handler-shaped subject.** A handler token (``handler``, ``controller``,
   ``endpoint``, ``route``, ``action``) appears in the module path, the
   enclosing function's name, or one of the identifiers the loop touches.

Part 2 is what separates this from legitimate shadow-avoidance -- a serverless
handler ``def`` renamed away from a SERVICE FUNCTION's name is deterministic in
its inputs, mutates no accumulator, and every consumer recomputes the same
answer. Part 3 is what separates it from local-variable, test-method, and
temp-file name allocation, which no second emitter consumes.

The baseline is a hard zero. There is no exemption file, on purpose: a REST
handler name that needs local de-duplication is a name that should have been
taken from the shared table.

Self-test runs first on every invocation. It plants each retired form and
requires detection, and plants the legitimate near-misses and requires them to
be reported clean -- so neither a scanner that can only return zero nor one
that flags everything is believed.

Exit codes: 0 = clean (or a successful --self-test), 1 = a violation was found,
2 = usage error, too few packages discovered, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

#: Packages whose source may not de-duplicate a handler name. Every one of
#: them emits handler/controller members for the same routes, so any of them
#: renaming a collision locally puts it out of step with all the others.
_SCANNED_PREFIX = "datrix-codegen-"

#: Refuse to pass on a discovery that found almost nothing: the monorepo ships
#: many generator packages, and a run that sees one is looking at the wrong
#: tree rather than at a clean one.
_MIN_PACKAGES = 2

#: Identifiers a claim accumulator is bound to in this codebase. A name tested
#: against one of these is being allocated against names already handed out.
_ACCUMULATOR_NAMES: frozenset[str] = frozenset({
    "used",
    "used_names",
    "seen",
    "seen_names",
    "taken",
    "taken_names",
    "claimed",
    "claimed_names",
    "existing",
    "existing_names",
    "allocated",
    "assigned_names",
})

#: Methods/operators that add a name to a container, making it an accumulator.
_MUTATING_METHODS: frozenset[str] = frozenset({"add", "append", "update", "extend"})

#: Tokens that mark a name as a REST handler / controller member name. The
#: subject has to be one of these for the loop to be this gate's business.
_HANDLER_TOKENS: tuple[str, ...] = ("handler", "controller", "endpoint", "route", "action")


@dataclass(frozen=True)
class Violation:
    """One package-local handler-name de-duplication loop."""

    path: Path
    line: int
    function: str
    container: str

    def render(self, base_dir: Path) -> str:
        """One reviewer-facing line naming the file, line and offending loop."""
        try:
            shown = self.path.relative_to(base_dir)
        except ValueError:
            shown = self.path
        return (
            f"  {shown}:{self.line}  in {self.function}() -- numeric-suffix loop "
            f"over the claimed-name set {self.container!r}"
        )


def _container_identifier(node: ast.expr) -> str | None:
    """Name a membership test's right-hand container, when it has one."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _referenced_names(node: ast.AST) -> set[str]:
    """Every bare identifier read anywhere inside *node*."""
    return {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)}


def _incremented_counters(body: list[ast.stmt]) -> set[str]:
    """Names incremented by an integer literal anywhere inside *body*."""
    counters: set[str] = set()
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.AugAssign) or not isinstance(node.op, ast.Add):
                continue
            value = node.value
            if not (isinstance(value, ast.Constant) and isinstance(value.value, int)):
                continue
            if isinstance(node.target, ast.Name):
                counters.add(node.target.id)
    return counters


def _builds_string_from(node: ast.expr, counters: set[str]) -> bool:
    """True when *node* composes a string that interpolates one of *counters*."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr) and _referenced_names(sub) & counters:
            return True
        if (
            isinstance(sub, ast.BinOp)
            and isinstance(sub.op, ast.Add)
            and _referenced_names(sub) & counters
        ):
            return True
        if isinstance(sub, ast.Call) and _referenced_names(sub) & counters:
            return True
    return False


def _suffix_renamed_subjects(body: list[ast.stmt], counters: set[str]) -> set[str]:
    """Names assigned a counter-interpolated string inside *body*."""
    subjects: set[str] = set()
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Assign) or not _builds_string_from(node.value, counters):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    subjects.add(target.id)
    return subjects


def _is_numeric_suffix_loop(node: ast.While) -> tuple[str, set[str]] | None:
    """Classify *node* as a numeric-suffix allocation loop, or reject it.

    Returns:
        ``(container identifier, identifiers the loop touches)`` when the loop
        allocates a name by appending an incrementing number until it is free,
        else ``None``.
    """
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.In):
        return None
    container = _container_identifier(test.comparators[0])
    if container is None:
        return None
    counters = _incremented_counters(node.body)
    if not counters:
        return None
    left_names = _referenced_names(test.left)
    renamed = _suffix_renamed_subjects(node.body, counters)
    test_builds_candidate = _builds_string_from(test.left, counters)
    if not (renamed & left_names or test_builds_candidate):
        return None
    touched = left_names | renamed | counters | {container}
    return container, touched


def _mutates(function: ast.FunctionDef | ast.AsyncFunctionDef, container: str) -> bool:
    """True when *function* adds to *container*, making it a claim accumulator."""
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and _container_identifier(node.func.value) == container
        ):
            return True
        if (
            isinstance(node, ast.AugAssign)
            and _container_identifier(node.target) == container
        ):
            return True
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Subscript) and _container_identifier(t.value) == container
            for t in node.targets
        ):
            return True
    return False


def _has_handler_token(*subjects: str) -> bool:
    """True when any handler token appears in any of *subjects* (case-folded)."""
    haystack = " ".join(subjects).lower()
    return any(token in haystack for token in _HANDLER_TOKENS)


def _scan_function(
    function: ast.FunctionDef | ast.AsyncFunctionDef, path: Path
) -> list[Violation]:
    """Every handler-name de-duplication loop directly inside *function*."""
    found: list[Violation] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.While):
            continue
        classified = _is_numeric_suffix_loop(node)
        if classified is None:
            continue
        container, touched = classified
        accumulates = container in _ACCUMULATOR_NAMES or _mutates(function, container)
        if not accumulates:
            continue
        if not _has_handler_token(path.as_posix(), function.name, *sorted(touched)):
            continue
        found.append(
            Violation(
                path=path, line=node.lineno, function=function.name, container=container
            )
        )
    return found


def scan_source(source: str, path: Path) -> list[Violation]:
    """Return every violation in one module's source text.

    Args:
        source: Python source text.
        path: Path reported in violations, and scanned for a handler token
            (never read from disk here).

    Returns:
        Violations in file order. A file that does not parse yields none --
        a syntax error is another gate's failure, not this one's.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    by_line: dict[int, Violation] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # A nested `def` is reached both through its own visit and through its
        # enclosing function's, so the innermost attribution -- the one seen
        # last, whose `function` name is the loop's real owner -- wins.
        for violation in _scan_function(node, path):
            by_line[violation.line] = violation
    return sorted(by_line.values(), key=lambda v: (v.line, v.function))


def discover_packages(base_dir: Path) -> list[Path]:
    """Every ``datrix-codegen-*`` package directory carrying a ``src/`` tree."""
    return [
        package
        for package in sorted(base_dir.iterdir())
        if package.is_dir()
        and package.name.startswith(_SCANNED_PREFIX)
        and (package / "src").is_dir()
    ]


def discover_source_files(packages: list[Path]) -> list[Path]:
    """Every ``src/`` Python file of every discovered package, sorted."""
    files: list[Path] = []
    for package in packages:
        files.extend(
            sorted(
                p
                for p in (package / "src").rglob("*.py")
                if "__pycache__" not in p.parts
            )
        )
    return files


#: The retired java form: derive from the raw path, then number the collision.
_SELF_TEST_JAVA = '''
def _handler_name(endpoint, used):
    base = to_camel_case(f"{endpoint.method}_{endpoint.path}")
    name = base
    suffix = 2
    while name in used:
        name = f"{base}{suffix}"
        suffix += 1
    used.add(name)
    return name
'''

#: The retired java nested form: the same loop applied to a name already built.
_SELF_TEST_JAVA_NESTED = '''
def _handler_name_from_string(base, used):
    name = base
    suffix = 2
    while name in used:
        name = f"{base}{suffix}"
        suffix += 1
    used.add(name)
    return name
'''

#: The retired .NET form, whose function name says "method" rather than
#: "handler" -- caught by the module path instead.
_SELF_TEST_DOTNET_NESTED = '''
def _deduplicate_nested_method_name(base_name, claimed):
    name = base_name
    suffix = 2
    while name in claimed:
        name = f"{base_name}{suffix}"
        suffix += 1
    claimed.add(name)
    return name
'''

#: Legitimate: a serverless handler def renamed away from a SERVICE FUNCTION
#: name. Deterministic in its inputs, accumulates nothing, and every consumer
#: recomputes the same answer -- not a collision hidden from anybody.
_SELF_TEST_SERVERLESS = '''
def resolve_handler_fn_name(service, handler_name):
    function_names = {to_snake_case(str(fn.name)) for fn in service.functions.values()}
    if handler_name not in function_names:
        return handler_name
    candidate = f"{handler_name}_handler"
    suffix = 2
    while candidate in function_names:
        candidate = f"{handler_name}_handler_{suffix}"
        suffix += 1
    return candidate
'''

#: Legitimate: a generated TEST method name disambiguated from other test
#: method names. No second emitter consumes it, so it carries no handler token.
_SELF_TEST_FACT_METHOD = '''
def _unique_fact_method_name(description, seen):
    base = _slug_from_description(description)
    name = base
    suffix = 2
    while name in seen:
        name = f"{base}{suffix}"
        suffix += 1
    seen.add(name)
    return name
'''

#: Legitimate: a local C# variable renamed away from an endpoint's own
#: parameter names. The container IS accumulator-named (``taken``), so only
#: the handler-token test clears it -- which is the point of pinning it here:
#: the same loop moved onto a handler-name subject must be reported.
_SELF_TEST_LOCAL_NAME = '''
def _unique_local_name(preferred, taken):
    if preferred not in taken:
        return preferred
    suffix = 2
    while f"{preferred}{suffix}" in taken:
        suffix += 1
    return f"{preferred}{suffix}"
'''

#: (source, path, must be detected) for every self-test case.
_SELF_TEST_CASES: tuple[tuple[str, str, str, bool], ...] = (
    ("retired java derivation", _SELF_TEST_JAVA, "api/_endpoint_session_context.py", True),
    ("retired java nested dedup", _SELF_TEST_JAVA_NESTED, "api/_session_context.py", True),
    ("retired .NET nested dedup", _SELF_TEST_DOTNET_NESTED, "api/_endpoint_nested.py", True),
    ("serverless shadow avoidance", _SELF_TEST_SERVERLESS, "serverless/_handler_naming.py", False),
    ("test-method disambiguation", _SELF_TEST_FACT_METHOD, "testing/test_spec_generator.py", False),
    ("local-variable allocation", _SELF_TEST_LOCAL_NAME, "extern/extern_client_generator.py", False),
)


def run_self_test() -> bool:
    """Plant every retired form and every legitimate near-miss; check both ways.

    Returns:
        True when the scanner detects each retired form and reports each
        legitimate near-miss clean.
    """
    ok = True
    for label, source, path, expected in _SELF_TEST_CASES:
        found = scan_source(source, Path(path))
        if bool(found) is not expected:
            verdict = "was not detected" if expected else f"was flagged ({len(found)} hit(s))"
            print(f"[FAIL] self-test: planted {label} ({path}) {verdict}")
            ok = False
    if ok:
        detected = sum(1 for case in _SELF_TEST_CASES if case[3])
        cleared = len(_SELF_TEST_CASES) - detected
        print(
            f"[OK] self-test: {detected} retired form(s) detected, "
            f"{cleared} legitimate near-miss(es) reported clean"
        )
    return ok


def main(argv: list[str] | None = None) -> int:
    """Run the self-test, then scan every ``datrix-codegen-*`` ``src/`` tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", default="", help="Monorepo root")
    parser.add_argument("--self-test", action="store_true", help="Self-test only")
    parser.add_argument("--verbose", action="store_true", help="Print scanned files")
    args = parser.parse_args(argv)

    if not run_self_test():
        return 2
    if args.self_test:
        return 0

    base_dir = (
        Path(args.base_dir).resolve()
        if args.base_dir
        else Path(__file__).resolve().parents[3]
    )
    if not base_dir.is_dir():
        print(f"Base directory not found: {base_dir}")
        return 2

    packages = discover_packages(base_dir)
    if len(packages) < _MIN_PACKAGES:
        print(
            f"Discovered {len(packages)} '{_SCANNED_PREFIX}*' package(s) with a src/ "
            f"tree under {base_dir}; at least {_MIN_PACKAGES} are expected -- "
            "refusing to pass vacuously"
        )
        return 2
    files = discover_source_files(packages)
    if not files:
        print(
            f"No Python source found in {len(packages)} discovered package(s) -- "
            "refusing to pass vacuously"
        )
        return 2

    violations: list[Violation] = []
    for path in files:
        if args.verbose:
            print(f"  scanning {path}")
        violations.extend(scan_source(path.read_text(encoding="utf-8", errors="replace"), path))

    print(f"Scanned {len(files)} file(s) across {len(packages)} {_SCANNED_PREFIX}* package(s)")
    if violations:
        print(f"\nHANDLER-NAME DEDUP GATE FAILED: {len(violations)} violation(s)\n")
        for violation in violations:
            print(violation.render(base_dir))
        print(
            "\nA REST handler/controller method name is derived once, in "
            "datrix_common.generation.api_helpers "
            "(compute_rest_api_handler_names / rest_api_handler_names_by_endpoint), "
            "which RAISES on a collision naming both routes. Take the name from "
            "that table and re-case it with this package's own caser; pass any "
            "non-endpoint member of the same emitted namespace as reserved_names."
        )
        return 1
    print("[OK] no datrix-codegen-* package de-duplicates a handler name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
