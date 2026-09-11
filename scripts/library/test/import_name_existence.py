"""Fail if a `from <datrix module> import <name>` names something that does not exist.

Three half-completed renames landed in one phase -- an import line rewritten
while its call site was not, a definition left under its old name while both
call sites moved, and a mechanical replacement that produced
``arcgis_feature_layer_client_`` + ``arcgis_client_class_name`` instead of the
real symbol. All three were found by accident, while an unrelated task happened
to run a suite that exercised the path. Nothing in this repository looks for
them on purpose.

This gate is that missing check. It resolves every ``from <module> import
<name>`` whose module belongs to a Datrix package against whether the name
actually exists in that module, and fails on any that does not.

**The `TYPE_CHECKING` case is the one this exists for.** A broken RUNTIME
import announces itself: the first test that imports the module raises
``ImportError`` and the suite goes red. A broken import inside ``if
TYPE_CHECKING:`` announces nothing, ever -- the block never executes, so every
package still imports cleanly, and this repository runs no standalone
type-checker by policy (``CLAUDE.md``, "Running Python"). Two such imports
survived indefinitely that way (``ViewField``, and ``PubsubBlock`` imported from
the wrong module), and every annotation written against either named a class
that did not exist. Runtime imports are checked too, because doing so costs
nothing once the resolver exists -- but they are not the reason it exists.

Resolution, in order, for ``from M import N``:

1. **Module-level binding in M's own source**, by AST -- a ``def``, ``class``,
   assignment, annotated assignment, or import alias at module level, including
   inside a top-level ``if`` / ``try`` / ``with`` (so a name M itself re-exports
   only under ``TYPE_CHECKING`` resolves: a type checker sees it, and this gate
   is not stricter than a type checker).
2. **A submodule of M** -- ``from datrix_cli.commands import lsp`` imports a
   MODULE, not an attribute. **This step is not optional and it is not an
   optimization.** A first pass written without it reported 102 undefined names,
   of which essentially all were submodule imports; the correction is the
   difference between 102 findings and 2. A gate that cries wolf a hundred times
   is worse than no gate, because the next person switches it off.
3. **A runtime attribute of M**, by importing M -- the last resort, reached only
   for names steps 1 and 2 miss. It covers what an AST walk cannot see: a name
   re-exported through ``from x import *``, or synthesized by a module-level
   ``__getattr__``. An import that raises is reported with the exception text,
   never silently treated as resolved.

Steps 1 and 2 read the workspace's own source tree, so the common case costs no
imports and no side effects at all.

The terminal state is zero. There is no baseline and no ratchet, because the
findings this gate was written against were fixed rather than pinned. A name
that genuinely cannot be resolved by any of the three routes is a defect in the
importing module, not an entry to record here.

Run with ``--self-test`` to verify the resolver is non-vacuous. The self-test
runs before every real scan, so a green result can never mean "the resolver was
broken".
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import os
import sys
import tempfile
from dataclasses import dataclass

#: Directories never walked -- caches, build output, virtualenvs, and the
#: gitignored orchestration trees.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tsc_cache",
        ".test_results",
        ".generated",
        ".tmp",
        ".scripts",
        ".test-output",
        ".tasks",
        "design",
        "build",
        "dist",
    }
)

#: Import targets this gate resolves. A module outside these prefixes belongs to
#: the standard library or a third party and is none of this gate's business.
DEFAULT_MODULE_PREFIXES: tuple[str, ...] = ("datrix",)

#: Consumer subtrees scanned inside each package repo. `src` carries production
#: code; `tests` carries suites, and a dead annotation in a test is exactly as
#: invisible as one in `src`.
PACKAGE_SUBTREES: tuple[str, ...] = ("src", "tests")

#: The showcase repo is not an installable package -- its Python lives under
#: `scripts`, and those modules import framework packages like any consumer.
SHOWCASE_SUBTREES: tuple[str, ...] = ("scripts",)


@dataclass(frozen=True)
class ImportSite:
    """One `from module import name` binding, with where it was written."""

    path: str
    lineno: int
    module: str
    name: str
    type_checking_only: bool


@dataclass(frozen=True)
class Finding:
    """An import site whose name resolved by none of the three routes."""

    site: ImportSite
    detail: str


@dataclass(frozen=True)
class ScanReport:
    """What a scan looked at, so a zero can be read as coverage, not silence."""

    findings: tuple[Finding, ...]
    checked: int
    type_checking_checked: int
    unresolvable_relative: int
    expected_to_fail: int


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def workspace_root() -> str:
    """The directory holding every `datrix*` package repo."""
    here = os.path.dirname(os.path.abspath(__file__))
    return _norm(os.path.abspath(os.path.join(here, "..", "..", "..", "..")))


def _package_subtrees(package_name: str) -> tuple[str, ...]:
    return SHOWCASE_SUBTREES if package_name == "datrix" else PACKAGE_SUBTREES


def default_roots(workspace: str) -> list[str]:
    """Every scannable subtree of every `datrix*` repo on disk.

    Derived from what is present rather than a hand-authored list, so a new
    package repo is covered the day it appears.
    """
    roots: list[str] = []
    for name in sorted(os.listdir(workspace)):
        package_dir = os.path.join(workspace, name)
        if not name.startswith("datrix") or not os.path.isdir(package_dir):
            continue
        for subtree in _package_subtrees(name):
            candidate = os.path.join(package_dir, subtree)
            if os.path.isdir(candidate):
                roots.append(_norm(candidate))
    return roots


def build_source_index(workspace: str) -> dict[str, str]:
    """Map every importable dotted module name to its file, from `src/` trees.

    A package's `__init__.py` is indexed under the package's own dotted name,
    so `from datrix_cli.commands import lsp` can be answered by an index lookup
    rather than an import.
    """
    index: dict[str, str] = {}
    for name in sorted(os.listdir(workspace)):
        src_root = os.path.join(workspace, name, "src")
        if not name.startswith("datrix") or not os.path.isdir(src_root):
            continue
        _index_src_tree(_norm(src_root), index)
    return index


def _index_src_tree(src_root: str, index: dict[str, str]) -> None:
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = _norm(os.path.join(dirpath, filename))
            relative = path[len(src_root) + 1 :]
            parts = relative[: -len(".py")].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts:
                index[".".join(parts)] = path


def _statement_bindings(node: ast.stmt) -> set[str]:
    """Names *node* binds at the scope it appears in."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    return set()


def _child_bodies(node: ast.stmt) -> list[list[ast.stmt]]:
    """Statement lists a module-level construct can still bind module names in."""
    if isinstance(node, ast.If):
        return [node.body, node.orelse]
    if isinstance(node, ast.Try):
        bodies = [node.body, node.orelse, node.finalbody]
        bodies.extend(handler.body for handler in node.handlers)
        return bodies
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [node.body]
    return []


def _collect_bindings(body: list[ast.stmt], names: set[str]) -> None:
    for node in body:
        names.update(_statement_bindings(node))
        for child in _child_bodies(node):
            _collect_bindings(child, names)


def _has_star_import(body: list[ast.stmt]) -> bool:
    for node in body:
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                return True
        for child in _child_bodies(node):
            if _has_star_import(child):
                return True
    return False


@dataclass(frozen=True)
class ModuleFacts:
    """What a target module's own source says it binds."""

    bindings: frozenset[str]
    has_star_import: bool


def parse_module_facts(path: str) -> ModuleFacts:
    with open(path, encoding="utf-8", errors="replace") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names: set[str] = set()
    _collect_bindings(tree.body, names)
    return ModuleFacts(bindings=frozenset(names), has_star_import=_has_star_import(tree.body))


class NameResolver:
    """Answers 'does `name` exist in `module`?' by the three documented routes."""

    def __init__(self, source_index: dict[str, str], module_prefixes: tuple[str, ...]) -> None:
        self._source_index = source_index
        self._module_prefixes = module_prefixes
        self._facts: dict[str, ModuleFacts] = {}
        self._runtime: dict[tuple[str, str], str] = {}

    def is_in_scope(self, module: str) -> bool:
        head = module.split(".")[0]
        return any(head == prefix or head.startswith(prefix) for prefix in self._module_prefixes)

    def resolve(self, module: str, name: str) -> str:
        """Return an empty string when *name* resolves, else why it did not."""
        if f"{module}.{name}" in self._source_index:
            return ""
        facts = self._module_facts(module)
        if facts is None:
            return self._runtime_failure(module, name, f"module {module!r} has no source in the workspace")
        if name in facts.bindings:
            return ""
        if not facts.has_star_import:
            return self._runtime_failure(
                module, name, f"module {module!r} binds no name {name!r} and declares no submodule {name!r}"
            )
        return self._runtime_failure(
            module, name, f"module {module!r} star-imports, and {name!r} is not re-exported"
        )

    def _module_facts(self, module: str) -> ModuleFacts | None:
        if module in self._facts:
            return self._facts[module]
        path = self._source_index.get(module)
        if path is None:
            return None
        facts = parse_module_facts(path)
        self._facts[module] = facts
        return facts

    def _runtime_failure(self, module: str, name: str, static_detail: str) -> str:
        """Last route: import *module* and look. Empty string means resolved."""
        key = (module, name)
        if key in self._runtime:
            return self._runtime[key]
        try:
            imported = importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            detail = f"{static_detail}; importing it to check raised {type(exc).__name__}: {exc}"
            self._runtime[key] = detail
            return detail
        detail = "" if hasattr(imported, name) else static_detail
        self._runtime[key] = detail
        return detail


#: Exceptions whose presence in an `except` clause or a `pytest.raises(...)`
#: means the author WANTS this import to fail. A test asserting that a deleted
#: symbol is gone writes exactly this shape, and it is the third
#: false-positive family: eight of the first ten findings this gate produced
#: were such assertions, and reporting them would have made the real two
#: invisible in the noise.
EXPECTED_IMPORT_FAILURES: frozenset[str] = frozenset(
    {"ImportError", "ModuleNotFoundError", "AttributeError"}
)


@dataclass(frozen=True)
class WalkContext:
    """What the enclosing statements say about an import found beneath them."""

    type_checking: bool
    expected_to_fail: bool


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _exception_names(expr: ast.expr | None) -> set[str]:
    if expr is None:
        return set(EXPECTED_IMPORT_FAILURES)  # bare `except:` tolerates anything
    if isinstance(expr, ast.Name):
        return {expr.id}
    if isinstance(expr, ast.Attribute):
        return {expr.attr}
    if isinstance(expr, ast.Tuple):
        return {name for element in expr.elts for name in _exception_names(element)}
    return set()


def _try_tolerates_import_failure(node: ast.Try) -> bool:
    return any(
        _exception_names(handler.type) & EXPECTED_IMPORT_FAILURES for handler in node.handlers
    )


def _is_expected_failure_raises(item: ast.expr) -> bool:
    """True for `pytest.raises(ImportError)` and its bare-`raises` spelling."""
    if not isinstance(item, ast.Call):
        return False
    func = item.func
    if isinstance(func, ast.Attribute):
        called = func.attr
    elif isinstance(func, ast.Name):
        called = func.id
    else:
        return False
    if called != "raises":
        return False
    return any(_exception_names(arg) & EXPECTED_IMPORT_FAILURES for arg in item.args)


def _with_tolerates_import_failure(node: ast.With | ast.AsyncWith) -> bool:
    return any(_is_expected_failure_raises(item.context_expr) for item in node.items)


def _child_contexts(node: ast.stmt, ctx: WalkContext) -> list[tuple[list[ast.stmt], WalkContext]]:
    """Each statement list under *node*, paired with the context it imposes."""
    if isinstance(node, ast.If) and _is_type_checking_guard(node):
        guarded = WalkContext(type_checking=True, expected_to_fail=ctx.expected_to_fail)
        return [(node.body, guarded), (node.orelse, ctx)]
    if isinstance(node, ast.Try) and _try_tolerates_import_failure(node):
        tolerated = WalkContext(type_checking=ctx.type_checking, expected_to_fail=True)
        rest: list[tuple[list[ast.stmt], WalkContext]] = [(node.body, tolerated)]
        rest.extend((body, ctx) for body in _nested_bodies(node)[1:])
        return rest
    if isinstance(node, (ast.With, ast.AsyncWith)) and _with_tolerates_import_failure(node):
        tolerated = WalkContext(type_checking=ctx.type_checking, expected_to_fail=True)
        return [(node.body, tolerated)]
    return [(body, ctx) for body in _nested_bodies(node)]


def _walk_imports(
    body: list[ast.stmt], ctx: WalkContext
) -> list[tuple[ast.ImportFrom, WalkContext]]:
    found: list[tuple[ast.ImportFrom, WalkContext]] = []
    for node in body:
        if isinstance(node, ast.ImportFrom):
            found.append((node, ctx))
            continue
        for child_body, child_ctx in _child_contexts(node, ctx):
            found.extend(_walk_imports(child_body, child_ctx))
    return found


def _nested_bodies(node: ast.stmt) -> list[list[ast.stmt]]:
    """Every statement list under *node*, including function and class bodies."""
    bodies = _child_bodies(node)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        bodies = [node.body]
    elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        bodies = [node.body, node.orelse]
    return bodies


def _dotted_name_for_src_file(path: str, src_root: str) -> str:
    relative = _norm(path)[len(_norm(src_root)) + 1 :]
    parts = relative[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _absolute_module(node: ast.ImportFrom, containing_module: str, is_package: bool) -> str:
    """Resolve *node*'s target module, following a relative import when possible.

    A package's ``__init__.py`` IS its package, so one leading dot there means
    the package itself, not its parent -- `from .api import X` inside
    ``transformers/registry/__init__.py`` targets
    ``…transformers.registry.api``, while the same statement in a sibling
    module targets ``…transformers.api``. Getting that wrong reports every
    intra-package re-export in every ``__init__.py`` as a dead name, which is
    exactly the kind of confident wrongness that makes a gate unusable.

    Returns an empty string when the import is relative and the importing
    file's own dotted name is unknown -- counted and reported, never silently
    dropped.
    """
    if node.level == 0:
        return node.module or ""
    if not containing_module:
        return ""
    parts = containing_module.split(".")
    strip = node.level - 1 if is_package else node.level
    package_parts = parts[: len(parts) - strip] if strip else parts
    if not package_parts:
        return ""
    if node.module:
        package_parts = [*package_parts, *node.module.split(".")]
    return ".".join(package_parts)


@dataclass(frozen=True)
class FileHarvest:
    """Import sites from one file, plus what was deliberately not collected."""

    sites: tuple[ImportSite, ...]
    unresolvable_relative: int
    expected_to_fail: int


def collect_import_sites(root: str, src_root: str) -> tuple[list[ImportSite], int, int]:
    """Every in-file `from module import name` under *root*, plus two counts.

    *src_root* is the `src/` directory the files live under, or an empty string
    for a tree (`tests/`, `scripts/`) whose files have no unambiguous dotted
    name. Relative imports in such a tree cannot be resolved and are counted.
    """
    sites: list[ImportSite] = []
    unresolvable_relative = 0
    expected_to_fail = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            harvest = _collect_file_sites(_norm(os.path.join(dirpath, filename)), src_root)
            sites.extend(harvest.sites)
            unresolvable_relative += harvest.unresolvable_relative
            expected_to_fail += harvest.expected_to_fail
    return sites, unresolvable_relative, expected_to_fail


def _collect_file_sites(path: str, src_root: str) -> FileHarvest:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read(), filename=path)
    except SyntaxError:
        return FileHarvest(sites=(), unresolvable_relative=0, expected_to_fail=0)
    containing = _dotted_name_for_src_file(path, src_root) if src_root else ""
    is_package = os.path.basename(path) == "__init__.py"
    sites: list[ImportSite] = []
    unresolvable_relative = 0
    expected_to_fail = 0
    root_ctx = WalkContext(type_checking=False, expected_to_fail=False)
    for node, ctx in _walk_imports(tree.body, root_ctx):
        names = [alias.name for alias in node.names if alias.name != "*"]
        if ctx.expected_to_fail:
            expected_to_fail += len(names)
            continue
        module = _absolute_module(node, containing, is_package)
        if not module:
            unresolvable_relative += len(names)
            continue
        sites.extend(
            ImportSite(
                path=path,
                lineno=node.lineno,
                module=module,
                name=name,
                type_checking_only=ctx.type_checking,
            )
            for name in names
        )
    return FileHarvest(
        sites=tuple(sites),
        unresolvable_relative=unresolvable_relative,
        expected_to_fail=expected_to_fail,
    )


def scan(roots: list[str], resolver: NameResolver) -> ScanReport:
    findings: list[Finding] = []
    checked = 0
    type_checking_checked = 0
    unresolvable_relative = 0
    expected_to_fail = 0
    for root in roots:
        src_root = root if os.path.basename(root) == "src" else ""
        sites, skipped, tolerated = collect_import_sites(root, src_root)
        unresolvable_relative += skipped
        expected_to_fail += tolerated
        for site in sites:
            if not resolver.is_in_scope(site.module):
                continue
            checked += 1
            if site.type_checking_only:
                type_checking_checked += 1
            detail = resolver.resolve(site.module, site.name)
            if detail:
                findings.append(Finding(site=site, detail=detail))
    return ScanReport(
        findings=tuple(findings),
        checked=checked,
        type_checking_checked=type_checking_checked,
        unresolvable_relative=unresolvable_relative,
        expected_to_fail=expected_to_fail,
    )


def _write(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


_SELF_TEST_TARGET = """\
from __future__ import annotations

from typing import TYPE_CHECKING

REAL_CONSTANT = 1


class RealClass:
    pass


def real_function() -> int:
    return REAL_CONSTANT


if TYPE_CHECKING:
    from probe_pkg.leaf import LeafOnlyUnderTypeChecking
"""

_SELF_TEST_LEAF = """\
from __future__ import annotations


class LeafOnlyUnderTypeChecking:
    pass
"""

_SELF_TEST_CONSUMER = """\
from __future__ import annotations

from typing import TYPE_CHECKING

from probe_pkg.target import RealClass, real_function
from probe_pkg import leaf

if TYPE_CHECKING:
    from probe_pkg.target import LeafOnlyUnderTypeChecking
    from probe_pkg.target import NameThatExistsNowhere
    from probe_pkg.leaf import AlsoMissing
"""

#: A suite asserting a deleted symbol is really gone. Both spellings appear in
#: this repository, and both import a name that provably does not exist -- on
#: purpose. Reporting these is how a real finding gets buried.
_SELF_TEST_NEGATIVE_SUITE = """\
from __future__ import annotations

import pytest


def test_symbol_is_gone() -> None:
    with pytest.raises(ImportError):
        from probe_pkg.target import DeletedByDesign  # noqa: F401


def test_other_symbol_is_gone() -> None:
    try:
        from probe_pkg.target import AlsoDeletedByDesign  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.fail("AlsoDeletedByDesign should not exist")


def test_a_raises_that_is_not_about_imports_still_counts() -> None:
    with pytest.raises(ValueError):
        from probe_pkg.target import StillCheckedBecauseNotAnImportError  # noqa: F401
"""


_SELF_TEST_INNER = """\
from __future__ import annotations


class InnerName:
    pass
"""

#: A package `__init__.py`: one leading dot means THIS package, two means its
#: parent. Resolving those the way a plain module resolves them reports every
#: intra-package re-export in the workspace as dead.
_SELF_TEST_SUB_INIT = """\
from __future__ import annotations

from .inner import InnerName
from .inner import MissingInner
from ..target import RealClass
"""

#: The same two statements in a plain module of the same package, where one
#: leading dot means the PARENT package -- the other half of the pair.
_SELF_TEST_SIBLING = """\
from __future__ import annotations

from .inner import InnerName
from ..target import real_function
"""


def _build_self_test_tree(tmp: str) -> tuple[list[str], dict[str, str]]:
    src_root = _norm(os.path.join(tmp, "src"))
    _write(os.path.join(src_root, "probe_pkg", "__init__.py"), "")
    _write(os.path.join(src_root, "probe_pkg", "target.py"), _SELF_TEST_TARGET)
    _write(os.path.join(src_root, "probe_pkg", "leaf.py"), _SELF_TEST_LEAF)
    _write(os.path.join(src_root, "probe_pkg", "consumer.py"), _SELF_TEST_CONSUMER)
    _write(os.path.join(src_root, "probe_pkg", "sub", "inner.py"), _SELF_TEST_INNER)
    _write(os.path.join(src_root, "probe_pkg", "sub", "__init__.py"), _SELF_TEST_SUB_INIT)
    _write(os.path.join(src_root, "probe_pkg", "sub", "sibling.py"), _SELF_TEST_SIBLING)
    index: dict[str, str] = {}
    _index_src_tree(src_root, index)
    tests_root = _norm(os.path.join(tmp, "tests"))
    _write(os.path.join(tests_root, "test_negative_existence.py"), _SELF_TEST_NEGATIVE_SUITE)
    return [src_root, tests_root], index


def self_test() -> int:
    """Prove the resolver reports the dead names and only the dead names.

    Non-vacuity here means enumerating the shapes that must NOT be reported as
    well as the ones that must: a submodule import and a `TYPE_CHECKING`-only
    re-export are exactly the two false-positive families that made a first
    attempt at this check report a hundred non-defects.
    """
    with tempfile.TemporaryDirectory() as tmp:
        roots, index = _build_self_test_tree(tmp)
        resolver = NameResolver(index, module_prefixes=("probe_pkg",))
        report = scan(roots, resolver)
        reported = {(f.site.name, f.site.type_checking_only) for f in report.findings}
        expected = {
            ("NameThatExistsNowhere", True),
            ("AlsoMissing", True),
            ("MissingInner", False),
            # A `raises` that is not about import failure tolerates nothing:
            # the import inside it is still checked, and this name is dead.
            ("StillCheckedBecauseNotAnImportError", False),
        }
        if reported != expected:
            print(f"SELF-TEST FAILED: expected {sorted(expected)}, got {sorted(reported)}")
            return 1
        # consumer.py contributes six in-scope names (two runtime, one
        # submodule, three under TYPE_CHECKING); target.py contributes its own
        # TYPE_CHECKING re-export; the sub-package contributes five relative
        # imports across a package `__init__.py` and a plain sibling module. A
        # count that drifts means the walker stopped seeing a shape, which a
        # findings-only comparison would not notice.
        if report.type_checking_checked != 4:
            print(
                "SELF-TEST FAILED: expected 4 TYPE_CHECKING imports checked, "
                f"got {report.type_checking_checked}"
            )
            return 1
        if report.checked != 13:
            print(f"SELF-TEST FAILED: expected 13 in-scope imports checked, got {report.checked}")
            return 1
        if report.expected_to_fail != 2:
            print(
                "SELF-TEST FAILED: expected 2 deliberate negative-existence imports "
                f"excluded, got {report.expected_to_fail}"
            )
            return 1

    print(
        "INFO: Non-vacuity self-test passed: the resolver reports all four "
        "planted dead names (two inside `if TYPE_CHECKING:`, one behind a "
        "package-relative import, one inside a `raises` that is not about "
        "imports), and reports NONE of the five false-positive families -- a "
        "submodule import, a name re-exported only inside the target module's "
        "own `TYPE_CHECKING` block, a single-dot import inside a package "
        "`__init__.py` (which means THIS package), the same statement in a "
        "sibling module (which means the PARENT package), and an import "
        "written to fail under `pytest.raises(ImportError)` or "
        "`try/except ImportError`."
    )
    return 0


def _print_findings(report: ScanReport) -> None:
    print(f"ERROR: {len(report.findings)} import(s) name something that does not exist:")
    for finding in report.findings:
        channel = "TYPE_CHECKING" if finding.site.type_checking_only else "runtime"
        print(
            f"  [{channel}] {finding.site.path}:{finding.site.lineno}: "
            f"from {finding.site.module} import {finding.site.name}"
        )
        print(f"      {finding.detail}")
    print(
        "\nA name imported from a module that does not define it is a half-completed "
        "rename. Under `if TYPE_CHECKING:` nothing will ever tell you: the block never "
        "executes, so the package still imports, and every annotation written against "
        "that name is meaningless. Fix the import or the definition -- there is no "
        "baseline to add it to."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots", nargs="*", help="directories to scan (default: every datrix package subtree)"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run only the non-vacuity self-test"
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    workspace = workspace_root()
    index = build_source_index(workspace)
    if not index:
        print(f"ERROR: no datrix `src/` tree found under {workspace} -- nothing to resolve against.")
        return 2
    resolver = NameResolver(index, module_prefixes=DEFAULT_MODULE_PREFIXES)
    roots = [_norm(os.path.abspath(r)) for r in args.roots] or default_roots(workspace)
    report = scan(roots, resolver)

    print(
        f"INFO: {report.checked} datrix import name(s) checked across {len(roots)} tree(s) "
        f"against {len(index)} indexed module(s); {report.type_checking_checked} of them "
        f"inside `if TYPE_CHECKING:`."
    )
    if report.expected_to_fail:
        print(
            f"INFO: {report.expected_to_fail} import(s) written to FAIL (inside "
            "`pytest.raises(ImportError)` or `try/except ImportError`) were excluded -- "
            "those are negative-existence assertions, not defects."
        )
    if report.unresolvable_relative:
        print(
            f"INFO: {report.unresolvable_relative} relative import(s) in trees with no "
            "unambiguous dotted module name (tests/, scripts/) were not resolved."
        )
    if not report.findings:
        print("Import-name existence check passed")
        return 0
    _print_findings(report)
    return 1


if __name__ == "__main__":
    sys.exit(main())
