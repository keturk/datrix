#!/usr/bin/env python
"""PolyString case round-trip gate: a name never goes str() -> to_*_case().

WHY THIS EXISTS
---------------
Every identifier the generator re-cases -- an entity, service, block, field,
queue or shared-container name, ``QualifiedNode.name`` and ``qualified_name``
-- is a ``PolyString``: a ``str`` subclass that split its words ONCE at
construction and exposes ``.snake``, ``.camel``, ``.pascal``, ``.kebab``,
``.screaming_snake`` and ``.simple`` as read-only properties. The case
functions in ``datrix_common.utils.text`` (``to_snake_case`` and friends)
exist for text that is NOT already a name object.

The recurring defect is the round trip::

    block_name = str(block.name)          # throws the variants away
    block_snake = to_snake_case(block_name)  # recomputes the word split

or, in one expression, ``to_snake_case(str(block.name))``. It is not merely
wasteful: it hides that the value was a name, so the next reader also treats
it as text, and the pattern spread to several hundred sites across the
language and platform packages before anything refused it. A Semgrep rule
named the shape but ran only on demand, as a WARNING -- an advisory nobody
has to read is the same as no rule.

WHAT THIS COMPUTES
------------------
For every publishable ``.py`` file in every framework repo (discovered at
runtime, never listed), the ``ast`` of the file is walked and each call to a
case function -- by its canonical name, an import alias, or a module
attribute -- is classified:

``str-wrapped``
    ``to_X_case(str(E))``. Read ``E.X`` when ``E`` is a name object; when it is
    genuinely plain text, drop the ``str()`` -- every case function already
    accepts any ``str``, PolyString included.

``str-bound``
    ``to_X_case(NAME)`` where ``NAME = str(E)`` is bound in the same function
    (or module) scope. The two-step spelling of the same round trip.

``nested``
    ``to_X_case(to_Y_case(E))``. Both split the same words; the outer form
    alone is equivalent, and ``PolyString.compose`` exists for derived names.

``simple-name``
    ``to_X_case(extract_simple_name(E))``. ``PolyString.simple`` is the last
    segment of a dotted name, as a PolyString: ``E.simple.X``.

Every hit is a defect and the count is held at a HARD ZERO. There is no
exemption file, because no shape above has a legitimate instance: a case
function never needs a ``str()`` around its argument, and a nested call
never needs its inner one.

WHAT THIS CANNOT SEE
--------------------
``to_snake_case(node.name)`` -- a PolyString passed straight to a case
function -- is the same waste without the ``str()``, but whether ``.name``
is a PolyString or an ``Enum`` member's plain-``str`` ``.name`` is a type
fact, and no type checker runs in this repo. That shape is left to review.

THE COMMIT PATH IS THE ENFORCEMENT POINT
----------------------------------------
``git/commit-and-push.ps1`` runs this scan over the pending files of every
dirty repo before it stages anything, exactly as the customer-domain and
ignored-source gates run: a hit in the last repo must not leave the first
four already pushed. The standalone ``test/polystring-case-roundtrip-gate.ps1``
runs the full census on demand.

Repo-level validation script, per the datrix showcase boundary: the showcase
repo hosts no pytest suite, so cross-repo checks live here as scripts and the
gate's own self-test is its coverage.

Exit codes:
  0 = zero round trips in every scanned file
  1 = at least one round trip, or the self-test failed
  2 = usage error, or a scanned file could not be parsed
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = SCRIPT_DIR.parent
DATRIX_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(LIBRARY_DIR))

from dev.customer_domain_isolation import (  # noqa: E402
    framework_repos,
    pending_files,
    publishable_files,
)

logger = logging.getLogger(__name__)

# The case functions in datrix_common.utils.text and the PolyString property
# each one duplicates. The mapping is the fix suggestion: a hit on
# ``to_kebab_case`` tells the reader to read ``.kebab``.
CASE_FUNCTION_VARIANTS: dict[str, str] = {
    "to_snake_case": "snake",
    "to_camel_case": "camel",
    "to_pascal_case": "pascal",
    "to_kebab_case": "kebab",
    "to_screaming_snake_case": "screaming_snake",
}

# The dotted-name helper PolyString.simple replaces.
SIMPLE_NAME_FUNCTION = "extract_simple_name"

# The builtin whose call inside a case function is the round trip.
STR_BUILTIN = "str"

# Only Python source is parsed; templates and docs are outside this gate.
PYTHON_SUFFIX = ".py"

KIND_STR_WRAPPED = "str-wrapped"
KIND_STR_BOUND = "str-bound"
KIND_NESTED = "nested"
KIND_SIMPLE_NAME = "simple-name"


class PolyStringGateError(RuntimeError):
    """The gate cannot run: a file could not be read or parsed."""


@dataclass(frozen=True)
class Hit:
    """One case-function call that round-trips a name through plain text."""

    repo: str
    rel_path: str
    line: int
    col: int
    kind: str
    case_function: str
    fix: str

    def render(self) -> str:
        """``repo/path:line:col  kind  to_x_case(...)  -- fix``."""
        return (
            f"{self.repo}/{self.rel_path}:{self.line}:{self.col}  "
            f"{self.kind}  {self.case_function}(...)  -- {self.fix}"
        )


@dataclass(frozen=True)
class RepoResult:
    """Census for one repo."""

    repo: str
    files_scanned: int
    hits: tuple[Hit, ...]


# --------------------------------------------------------------------------
# Callee resolution: canonical name, import alias, or module attribute.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Aliases:
    """The local names a file binds to the case functions and to the simple-name helper."""

    case_functions: dict[str, str]  # local name -> canonical case function
    simple_name: frozenset[str]  # local names bound to extract_simple_name


def _collect_aliases(tree: ast.Module) -> _Aliases:
    """Resolve every ``from ... import X [as Y]`` of a case function, at any depth.

    Collected over the whole file rather than per scope: a function-level
    import is the common spelling for these helpers, and an alias bound in
    one function is never legitimately a *different* function elsewhere.
    """
    case_functions = {canonical: canonical for canonical in CASE_FUNCTION_VARIANTS}
    simple_name = {SIMPLE_NAME_FUNCTION}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            if alias.name in CASE_FUNCTION_VARIANTS:
                case_functions[local] = alias.name
            elif alias.name == SIMPLE_NAME_FUNCTION:
                simple_name.add(local)
    return _Aliases(case_functions=case_functions, simple_name=frozenset(simple_name))


def _callee_name(call: ast.Call) -> str | None:
    """The bare or attribute name a call is made through, or None."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _case_function_of(call: ast.Call, aliases: _Aliases) -> str | None:
    """The canonical case function this call invokes, or None."""
    name = _callee_name(call)
    if name is None:
        return None
    return aliases.case_functions.get(name)


def _is_str_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == STR_BUILTIN
    )


def _is_simple_name_call(node: ast.AST, aliases: _Aliases) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = _callee_name(node)
    return name is not None and name in aliases.simple_name


# --------------------------------------------------------------------------
# Scope walk: a function's own statements, never a nested def's.
# --------------------------------------------------------------------------

_SCOPE_ROOTS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_BARRIERS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _iter_scope_nodes(root: ast.AST) -> Iterator[ast.AST]:
    """Every node inside ``root`` that belongs to ``root``'s own scope.

    Descends into statements, expressions, comprehensions and lambdas, but
    stops at a nested function or class: those are their own scopes and are
    visited when the outer walk reaches them as roots.
    """
    stack = list(ast.iter_child_nodes(root))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _SCOPE_BARRIERS):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _str_bound_names(scope: ast.AST) -> set[str]:
    """Names this scope binds to a ``str(...)`` call: ``NAME = str(E)`` / ``NAME: T = str(E)``."""
    bound: set[str] = set()
    for node in _iter_scope_nodes(scope):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if value is None or not _is_str_call(value):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bound.add(target.id)
    return bound


# --------------------------------------------------------------------------
# Classification.
# --------------------------------------------------------------------------


def _fix_for(kind: str, variant: str) -> str:
    if kind == KIND_STR_WRAPPED:
        return (
            f"read `.{variant}` off the name object; if the value is genuinely plain "
            f"text, drop the str() -- case functions accept any str, PolyString included"
        )
    if kind == KIND_STR_BOUND:
        return (
            f"the argument was bound by `= str(...)` in this scope: read `.{variant}` off "
            f"the original name object instead of re-casing its text"
        )
    if kind == KIND_NESTED:
        return (
            f"the outer call alone is equivalent; for a derived name use "
            f"PolyString.compose(...).{variant}"
        )
    return f"read `.simple.{variant}` off the qualified name"


def _classify(
    call: ast.Call, canonical: str, aliases: _Aliases, str_bound: set[str]
) -> str | None:
    """The hit kind for a case-function call, or None when the call is clean."""
    if len(call.args) != 1 or call.keywords:
        return None
    arg = call.args[0]
    if _is_str_call(arg):
        return KIND_STR_WRAPPED
    if isinstance(arg, ast.Name) and arg.id in str_bound:
        return KIND_STR_BOUND
    if isinstance(arg, ast.Call) and _case_function_of(arg, aliases) is not None:
        return KIND_NESTED
    if _is_simple_name_call(arg, aliases):
        return KIND_SIMPLE_NAME
    return None


def scan_source(source: str, repo: str, rel_path: str) -> list[Hit]:
    """Every round trip in one Python source text."""
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        raise PolyStringGateError(
            f"{repo}/{rel_path}: cannot parse as Python ({exc.msg} at line {exc.lineno}). "
            f"Expected: a syntactically valid module. Fix the file, then re-run."
        ) from exc
    aliases = _collect_aliases(tree)
    hits: list[Hit] = []
    for scope in ast.walk(tree):
        if not isinstance(scope, _SCOPE_ROOTS):
            continue
        str_bound = _str_bound_names(scope)
        for node in _iter_scope_nodes(scope):
            if not isinstance(node, ast.Call):
                continue
            canonical = _case_function_of(node, aliases)
            if canonical is None:
                continue
            kind = _classify(node, canonical, aliases, str_bound)
            if kind is None:
                continue
            hits.append(
                Hit(
                    repo=repo,
                    rel_path=rel_path,
                    line=node.lineno,
                    col=node.col_offset + 1,
                    kind=kind,
                    case_function=canonical,
                    fix=_fix_for(kind, CASE_FUNCTION_VARIANTS[canonical]),
                )
            )
    hits.sort(key=lambda hit: (hit.rel_path, hit.line, hit.col))
    return hits


def scan_paths(repo_path: Path, rel_paths: list[str]) -> RepoResult:
    """Scan the given repo-relative paths; non-Python paths are skipped."""
    hits: list[Hit] = []
    scanned = 0
    for rel_path in rel_paths:
        if not rel_path.endswith(PYTHON_SUFFIX):
            continue
        full = repo_path / rel_path
        if not full.is_file():
            continue
        try:
            source = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PolyStringGateError(
                f"{repo_path.name}/{rel_path}: cannot read as UTF-8 text ({exc}). "
                f"Expected: a readable UTF-8 Python source file."
            ) from exc
        scanned += 1
        hits.extend(scan_source(source, repo_path.name, rel_path.replace("\\", "/")))
    return RepoResult(repo=repo_path.name, files_scanned=scanned, hits=tuple(hits))


def scan_repo(repo_path: Path) -> RepoResult:
    """Scan every publishable Python file in one repo."""
    return scan_paths(repo_path, publishable_files(repo_path))


def scan_for_commit(repo_path: Path) -> RepoResult:
    """Scan only what a ``git add -A`` in ``repo_path`` would stage."""
    return scan_paths(repo_path, pending_files(repo_path))


def resolve_repos(workspace_root: Path, wanted: list[str] | None) -> list[Path]:
    """Return the repos to scan, raising when a requested name does not exist."""
    repos = framework_repos(workspace_root)
    if not repos:
        raise PolyStringGateError(
            f"No framework repo found under {workspace_root}. Expected the datrix showcase "
            f"repo and its datrix-* siblings, each a git checkout."
        )
    if wanted is None:
        return repos
    selected = [repo for repo in repos if repo.name in set(wanted)]
    missing = sorted(set(wanted) - {repo.name for repo in selected})
    if missing:
        raise PolyStringGateError(
            f"No framework repo named {', '.join(missing)} under {workspace_root}. "
            f"Known: {', '.join(repo.name for repo in repos)}"
        )
    return selected


# --------------------------------------------------------------------------
# Self-test: the gate proves it can still see every planted shape before it is
# believed about anything. A scan that can only return zero is not evidence.
# --------------------------------------------------------------------------

SELF_TEST_REPO = "self-test"
SELF_TEST_PATH = "src/pkg/planted.py"

# One instance of every kind, plus every callee spelling (canonical, aliased,
# module attribute, function-level import), plus a nested-function scope so the
# scope barrier is exercised. Expected (line, kind) pairs are listed beside it.
SELF_TEST_PLANTED_SOURCE = '''\
from datrix_common.utils import text
from datrix_common.utils.text import extract_simple_name, to_pascal_case
from datrix_common.utils.text import to_kebab_case as _kebab


def direct(node):
    return to_pascal_case(str(node.name))


def bound(node):
    shared_name = str(node.name)
    other = str(node.other)
    return _kebab(shared_name), other


def bound_annotated(node):
    label: str = str(node.name)
    return text.to_snake_case(label)


def nested(node):
    return to_pascal_case(_kebab(node.name))


def simple(node):
    return to_pascal_case(extract_simple_name(node.qualified_name))


def function_level_import(node):
    from datrix_common.utils.text import to_camel_case as camel
    return camel(str(node.name))


def outer(node):
    stack_name = str(node.name)

    def inner(other):
        return to_pascal_case(other)

    return inner(stack_name)
'''

SELF_TEST_EXPECTED: tuple[tuple[int, str, str], ...] = (
    (7, KIND_STR_WRAPPED, "to_pascal_case"),
    (13, KIND_STR_BOUND, "to_kebab_case"),
    (18, KIND_STR_BOUND, "to_snake_case"),
    (22, KIND_NESTED, "to_pascal_case"),
    (26, KIND_SIMPLE_NAME, "to_pascal_case"),
    (31, KIND_STR_WRAPPED, "to_camel_case"),
)

# The clean spellings: reading variants off the name, a case function over a
# value that was never str()-wrapped, and str() applied AFTER the case call.
SELF_TEST_CLEAN_SOURCE = '''\
from datrix_common.utils.text import PolyString, to_snake_case


def clean(node, raw: str):
    a = node.name.snake
    b = to_snake_case(raw)
    c = str(to_snake_case(raw))
    d = PolyString.compose(node.name, "handler").pascal
    e = str(node.name)
    return a, b, c, d, e, str(e)
'''


def self_test() -> list[str]:
    """Prove the gate is non-vacuous. Returns a list of failure descriptions."""
    failures: list[str] = []
    hits = scan_source(SELF_TEST_PLANTED_SOURCE, SELF_TEST_REPO, SELF_TEST_PATH)
    observed = tuple((hit.line, hit.kind, hit.case_function) for hit in hits)
    if observed != SELF_TEST_EXPECTED:
        failures.append(
            f"planted source: expected hits {SELF_TEST_EXPECTED}, observed {observed}"
        )
    clean_hits = scan_source(SELF_TEST_CLEAN_SOURCE, SELF_TEST_REPO, SELF_TEST_PATH)
    if clean_hits:
        failures.append(
            "clean source: expected zero hits, observed "
            + "; ".join(hit.render() for hit in clean_hits)
        )
    try:
        scan_source("def broken(:\n", SELF_TEST_REPO, SELF_TEST_PATH)
    except PolyStringGateError:
        pass
    else:
        failures.append("unparseable source: expected PolyStringGateError, observed a verdict")
    return failures


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable). Default: every framework repo.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real scan.",
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Scan only the files a `git add -A` would stage in each repo (the commit-path form).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser.parse_args(argv)


def run_scan(repos: list[Path], pending_only: bool) -> int:
    """Scan every repo, print the census, and return the process exit code."""
    mode = "pending" if pending_only else "publishable"
    print(f"Scanning {mode} Python files in {len(repos)} repo(s) for PolyString case round trips")
    results = [scan_for_commit(repo) if pending_only else scan_repo(repo) for repo in repos]
    for result in results:
        print(f"  {result.repo}: {result.files_scanned} file(s) scanned, {len(result.hits)} hit(s)")

    violating = [result for result in results if result.hits]
    if not violating:
        print(
            "\nPOLYSTRING CASE ROUND-TRIP GATE PASSED: no case function is called on a "
            "str()-converted, str()-bound, nested-cased or simple-name-extracted argument."
        )
        return 0

    total = sum(len(result.hits) for result in violating)
    print(
        f"\nPOLYSTRING CASE ROUND-TRIP GATE FAILED: {total} hit(s) in {len(violating)} "
        f"repo(s). A name that is already a PolyString carries .snake/.camel/.pascal/"
        f".kebab/.screaming_snake/.simple -- read the variant; never str() it and re-case "
        f"the text. Held at a hard zero; there is no exemption file."
    )
    for result in violating:
        print(f"\n  {result.repo}: {len(result.hits)} hit(s)")
        for hit in result.hits:
            print(f"    {hit.render()}")
    return 1


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    workspace_root = DATRIX_ROOT.parent

    failures = self_test()
    if failures:
        print("POLYSTRING CASE ROUND-TRIP GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("Self-test passed: the scanner still detects every planted round-trip shape.")

    if args.self_test:
        return 0

    try:
        repos = resolve_repos(workspace_root, args.repo)
        return run_scan(repos, args.pending_only)
    except PolyStringGateError as exc:
        print(f"POLYSTRING CASE ROUND-TRIP GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
