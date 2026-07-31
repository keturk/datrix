#!/usr/bin/env python3
"""Reverse-dependency closure derivation for Datrix packages.

Discovers every datrix-* package carrying a pyproject.toml under the
monorepo root (never a hardcoded package list) and classifies every import
edge by WHERE the importing file lives and, for src/ imports, WHERE in the
file the import statement sits:

- SOURCE edge -- an import statement at MODULE SCOPE (the top level of a
  file under the package's src/, including inside a module-scope
  `if TYPE_CHECKING:` block), or a target declared in
  `[project.dependencies]`. The package's runtime behavior depends on the
  target unconditionally, so source edges propagate transitively: if A's
  src imports B, and C's src imports A, a change to B affects C too.
- DEFERRED edge -- an import statement under the package's src/ that is
  nested inside a `def`/`async def` body (e.g. a lazy import used to avoid
  a module-scope import cycle). The package's own suite genuinely exercises
  that function, so a change to the target can break the importer's suite
  -- but the dependency is conditional at import time, not part of the
  package's module-scope surface. DEFERRED edges are therefore terminal,
  exactly like TEST edges (see below): one hop, never traversed further.
- TEST edge -- the importing file is under the package's tests/ or is its
  root-level conftest.py (or the target is declared only under some
  `[project.optional-dependencies]` group). Only the package's own SUITE
  depends on the target, so test edges are terminal: they add the
  declaring package to the target's closure, but do not propagate onward
  to the declaring package's own consumers.

When the same (importer, target) pair matches more than one signal, the
strongest wins: SOURCE beats DEFERRED beats TEST.

For package X, the closure is: X itself, plus every package reachable from
X by following source edges in reverse (transitively), plus every package
with a direct DEFERRED or TEST edge into that set (one hop, not traversed
further).

Usage:
  python scripts/library/test/affected_set.py --projects datrix-language
  python scripts/library/test/affected_set.py --all
  .\\scripts\\test\\affected-set.ps1 -Projects datrix-language
  .\\scripts\\test\\affected-set.ps1 -All

Exit codes: 0 = done, 1 = non-vacuity self-check failed (or --self-test
failed), 2 = usage error / unreadable input.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import logging
import re
import sys
import tempfile
import tomllib
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared and sibling modules
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.venv import get_datrix_root  # noqa: E402

logger = logging.getLogger(__name__)

_PACKAGE_PREFIX = "datrix-"
_PYPROJECT_NAME = "pyproject.toml"
_CONFTEST_NAME = "conftest.py"
_SRC_DIRNAME = "src"
_TESTS_DIRNAME = "tests"
_OUTPUT_FILENAME = "affected-set.json"
_OUTPUT_SUBDIRS = ("test",)
_EXIT_OK = 0
_EXIT_SELFCHECK_FAILED = 1
_EXIT_USAGE = 2

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(datrix_[a-zA-Z0-9_]*)", re.MULTILINE)
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")


class UsageError(Exception):
    """Invalid usage or unreadable input; the script exits with code 2."""


def discover_packages(root: Path) -> dict[str, Path]:
    """Discover datrix-* packages carrying a pyproject.toml under root.

    Args:
        root: The Datrix monorepo root (contains one directory per package).

    Returns:
        Mapping of package directory name -> absolute package directory
        path. Never a hardcoded list; recomputed from disk every call.

    Raises:
        UsageError: if no datrix-* packages with a pyproject.toml are found
            under root (an empty or wrong root).
    """
    packages: dict[str, Path] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not entry.name.startswith(_PACKAGE_PREFIX):
            continue
        if (entry / _PYPROJECT_NAME).is_file():
            packages[entry.name] = entry
    if not packages:
        raise UsageError(
            f"No {_PACKAGE_PREFIX}* packages with a {_PYPROJECT_NAME} found under "
            f"{root}. Expected the Datrix monorepo layout with each package at "
            f"{root}\\datrix-<name>\\pyproject.toml. Fix by pointing at the "
            f"correct monorepo root."
        )
    return packages


def discover_import_name(package_dir: Path) -> str | None:
    """The single top-level Python import name a package's src/ exposes.

    Args:
        package_dir: Absolute path to one discovered package directory.

    Returns:
        The import name (e.g. "datrix_common"), or None when the package has
        no src/ layout (e.g. a docs/scripts-only package).

    Raises:
        UsageError: if src/ contains more than one candidate top-level
            package and none matches the directory name's underscore form --
            an ambiguous layout this scanner refuses to guess at.
    """
    src_dir = package_dir / _SRC_DIRNAME
    if not src_dir.is_dir():
        return None
    candidates = [
        child.name
        for child in src_dir.iterdir()
        if child.is_dir() and (child / "__init__.py").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    underscored = package_dir.name.replace("-", "_")
    if underscored in candidates:
        return underscored
    raise UsageError(
        f"Package {package_dir.name} exposes multiple ambiguous top-level "
        f"import packages under {src_dir}: {sorted(candidates)}. Expected "
        f"exactly one, or one matching '{underscored}'. Fix by removing the "
        f"stray package directory or renaming it to match the package name."
    )


def _read_text_bom_safe(path: Path) -> str:
    """Read a source file, tolerating a leading UTF-8 BOM.

    A BOM-prefixed file read with plain "utf-8" leaves a stray U+FEFF on the
    first line, silently breaking a ``^\\s*(from|import)`` regex anchored at
    line start -- the file is scanned but its first import is invisibly
    dropped. "utf-8-sig" strips the BOM when present and is identical to
    "utf-8" otherwise.

    Raises:
        UsageError: if the file cannot be decoded even as utf-8-sig, or
            cannot be read at all -- never silently treated as empty.
    """
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(
            f"Cannot read {path} as UTF-8 (with or without BOM): {exc}. Fix "
            f"the file's encoding, or exclude it, before re-running."
        ) from exc


def _imported_names(source: str) -> set[str]:
    """Every datrix_* top-level import name referenced by a `from X import
    ...` or `import X` statement in source."""
    return {m.group(1) for m in _IMPORT_RE.finditer(source)}


def _import_top_level_names(node: ast.AST) -> set[str]:
    """Top-level dotted-name root(s) referenced by one Import/ImportFrom
    node.

    E.g. {"datrix_common"} for both `import datrix_common.foo` and
    `from datrix_common.foo import bar`. Empty set for any other node type.
    """
    if isinstance(node, ast.Import):
        return {alias.name.split(".", maxsplit=1)[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.split(".", maxsplit=1)[0]}
    return set()


def _classify_src_imports(source: str, file_path: Path) -> tuple[set[str], set[str]]:
    """Split every import statement in `source` by WHERE it sits: module
    scope (the top level of the file, including inside a module-scope
    `if TYPE_CHECKING:` block) versus nested inside a `def`/`async def` body.

    Args:
        source: The file's full text (already BOM-stripped).
        file_path: Only used to identify the file in a parse-error message.

    Returns:
        (module_scope_names, function_scope_names) -- the sets of top-level
        import-name roots found at each scope. A name may appear in both if
        the file imports it in both places.

    Raises:
        UsageError: if `source` fails to parse as Python -- never silently
            skipped, since a src/ file that can't be parsed can't be
            trusted to have zero import edges either.
    """
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        raise UsageError(
            f"Cannot parse {file_path} as Python: {exc}. Fix the file's "
            f"syntax before re-running."
        ) from exc

    module_scope_names: set[str] = set()
    function_scope_names: set[str] = set()
    stack: list[tuple[ast.AST, bool]] = [(tree, False)]
    while stack:
        node, in_function = stack.pop()
        for child in ast.iter_child_nodes(node):
            names = _import_top_level_names(child)
            if names:
                target = function_scope_names if in_function else module_scope_names
                target |= names
                continue
            child_in_function = in_function or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)
            )
            stack.append((child, child_in_function))
    return module_scope_names, function_scope_names


def _iter_src_files(package_dir: Path) -> Iterator[Path]:
    """Yield every .py file under this package's src/ -- these imports are
    SOURCE or DEFERRED edges depending on scope (see _classify_src_imports;
    the package's runtime behavior depends on the target either way)."""
    src_dir = package_dir / _SRC_DIRNAME
    if src_dir.is_dir():
        yield from src_dir.rglob("*.py")


def _iter_test_files(package_dir: Path, *, include_root_conftest: bool) -> Iterator[Path]:
    """Yield every .py file under this package's tests/, plus -- unless
    disabled -- its package-root conftest.py. These imports are TEST edges
    (only the package's own SUITE depends on the target).

    The root conftest.py lives beside pyproject.toml, outside both src/ and
    tests/. include_root_conftest exists ONLY so the self-test can prove the
    conftest scan is load-bearing (see
    check_restricted_scan_loses_conftest_edge); production callers always
    leave it at the default True.
    """
    tests_dir = package_dir / _TESTS_DIRNAME
    if tests_dir.is_dir():
        yield from tests_dir.rglob("*.py")
    if include_root_conftest:
        root_conftest = package_dir / _CONFTEST_NAME
        if root_conftest.is_file():
            yield root_conftest


def _dep_name(dep_spec: str) -> str:
    """Bare package name from a PEP 508 dependency spec.

    E.g. "datrix-language>=1.0" -> "datrix-language".
    """
    match = _DEP_NAME_RE.match(dep_spec.strip())
    return match.group(0) if match else dep_spec.strip()


def _declared_pyproject_deps_split(
    package_dir: Path, packages: dict[str, Path]
) -> tuple[set[str], set[str]]:
    """Discovered datrix-* dependencies declared in this package's
    pyproject.toml, split by declaration site.

    A `[project.dependencies]` entry is a SOURCE edge (the package's runtime
    behavior requires it unconditionally). An entry that appears ONLY under
    some `[project.optional-dependencies.*]` group (a dev/test extra) is a
    TEST edge (only the package's own suite requires it) -- unless the same
    package is also declared under `[project.dependencies]`, in which case
    the source classification wins for that pair.

    Returns:
        (source_deps, test_deps) -- both filtered to known packages, and
        never including the declaring package itself.

    Raises:
        UsageError: if pyproject.toml cannot be read or parsed as TOML --
            never silently treated as declaring zero dependencies.
    """
    pyproject_path = package_dir / _PYPROJECT_NAME
    try:
        raw_bytes = pyproject_path.read_bytes()
    except OSError as exc:
        raise UsageError(f"Cannot read {pyproject_path}: {exc}.") from exc
    try:
        data = tomllib.loads(raw_bytes.decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise UsageError(
            f"Cannot parse {pyproject_path} as TOML: {exc}. Fix the file's "
            f"syntax or encoding before re-running."
        ) from exc

    project = data.get("project", {})
    self_name = package_dir.name

    def _known_names(dep_specs: list[str]) -> set[str]:
        names = {_dep_name(dep) for dep in dep_specs}
        return {name for name in names if name in packages and name != self_name}

    source_deps = _known_names(project.get("dependencies", []))
    optional = project.get("optional-dependencies", {})
    all_optional_deps: set[str] = set()
    for group_deps in optional.values():
        all_optional_deps |= _known_names(group_deps)
    test_deps = all_optional_deps - source_deps
    return source_deps, test_deps


def _scanned_import_deps(pkg_name: str, files: Iterator[Path], import_to_package: dict[str, str]) -> set[str]:
    """Datrix-* packages imported by any of `files`, excluding `pkg_name`
    itself, resolved through `import_to_package`."""
    deps: set[str] = set()
    for source_file in files:
        text = _read_text_bom_safe(source_file)
        for imported in _imported_names(text):
            dep_pkg = import_to_package.get(imported)
            if dep_pkg is not None and dep_pkg != pkg_name:
                deps.add(dep_pkg)
    return deps


def _scanned_src_imports_by_scope(
    pkg_name: str, files: Iterator[Path], import_to_package: dict[str, str]
) -> tuple[set[str], set[str]]:
    """Datrix-* packages imported by any of `files` (a package's src/ tree),
    split by scope and resolved through `import_to_package`, excluding
    `pkg_name` itself.

    Returns:
        (module_scope_deps, function_scope_deps) -- see _classify_src_imports.
    """
    module_scope_deps: set[str] = set()
    function_scope_deps: set[str] = set()
    for source_file in files:
        text = _read_text_bom_safe(source_file)
        module_names, function_names = _classify_src_imports(text, source_file)
        for imported in module_names:
            dep_pkg = import_to_package.get(imported)
            if dep_pkg is not None and dep_pkg != pkg_name:
                module_scope_deps.add(dep_pkg)
        for imported in function_names:
            dep_pkg = import_to_package.get(imported)
            if dep_pkg is not None and dep_pkg != pkg_name:
                function_scope_deps.add(dep_pkg)
    return module_scope_deps, function_scope_deps


def build_source_test_and_deferred_graphs(
    packages: dict[str, Path],
    import_names: dict[str, str | None],
    *,
    include_root_conftest: bool = True,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """Three forward dependency graphs: SOURCE edges (propagate
    transitively), TEST edges, and DEFERRED edges (both terminal -- only the
    declaring package's own suite depends on the target).

    Args:
        packages: Discovered package name -> directory path.
        import_names: Package name -> its top-level import name (or None).
        include_root_conftest: Whether the root-level conftest.py is
            included in the TEST-edge scan. Defaults to True (production
            behavior); set False ONLY to prove the conftest edge is
            load-bearing (see the self-test).

    Returns:
        (source_graph, test_graph, deferred_graph): each maps package name
        -> the set of package names it depends on at that edge tier. When
        the same (importer, target) pair matches more than one signal, the
        strongest wins: a SOURCE finding removes that target from the same
        package's DEFERRED and TEST sets; a DEFERRED finding removes it
        from that package's TEST set.
    """
    import_to_package = {v: k for k, v in import_names.items() if v is not None}
    source_graph: dict[str, set[str]] = {}
    test_graph: dict[str, set[str]] = {}
    deferred_graph: dict[str, set[str]] = {}

    for pkg_name, pkg_dir in packages.items():
        module_scope_deps, function_scope_deps = _scanned_src_imports_by_scope(
            pkg_name, _iter_src_files(pkg_dir), import_to_package
        )
        test_deps = _scanned_import_deps(
            pkg_name,
            _iter_test_files(pkg_dir, include_root_conftest=include_root_conftest),
            import_to_package,
        )
        declared_source, declared_test = _declared_pyproject_deps_split(pkg_dir, packages)
        source_deps = module_scope_deps | declared_source
        deferred_deps = function_scope_deps - source_deps
        test_deps |= declared_test
        test_deps -= source_deps
        test_deps -= deferred_deps
        source_graph[pkg_name] = source_deps
        test_graph[pkg_name] = test_deps
        deferred_graph[pkg_name] = deferred_deps
    return source_graph, test_graph, deferred_graph


def build_declared_source_only_graph(packages: dict[str, Path]) -> dict[str, set[str]]:
    """Forward SOURCE graph derived purely from declared
    `[project.dependencies]` (no import scan, no optional-dependencies) --
    the non-vacuity floor for check_closure_not_smaller_than_declared.
    """
    return {
        name: _declared_pyproject_deps_split(pkg_dir, packages)[0] for name, pkg_dir in packages.items()
    }


def transitive_reverse_closure(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """For each package, the set of OTHER packages that (transitively)
    depend on it in `graph` -- i.e. must also be tested when it changes,
    considering only the edges present in this graph.

    Cycle-safe: a self-referential or mutually-referential edge set never
    causes non-termination, because visited-set membership -- not edge
    presence -- ends each package's traversal.

    Args:
        graph: A forward dependency graph (package -> set of packages it
            depends on). Used both as a generic utility and as the SOURCE
            half of the two-tier model (see compute_affected_closures).

    Returns:
        Mapping of package name -> its transitive reverse closure in this
        graph (never including packages absent from `graph`; includes the
        package itself only if a cycle in `graph` loops back to it).
    """
    reverse_graph: dict[str, set[str]] = {name: set() for name in graph}
    for consumer, deps in graph.items():
        for dep in deps:
            if dep in reverse_graph:
                reverse_graph[dep].add(consumer)

    closures: dict[str, set[str]] = {}
    for target in graph:
        visited: set[str] = set()
        frontier = list(reverse_graph.get(target, set()))
        while frontier:
            node = frontier.pop()
            if node in visited:
                continue
            visited.add(node)
            frontier.extend(reverse_graph.get(node, set()) - visited)
        closures[target] = visited
    return closures


def compute_affected_closures(
    source_graph: dict[str, set[str]],
    test_graph: dict[str, set[str]],
    deferred_graph: dict[str, set[str]],
) -> dict[str, set[str]]:
    """For each package P, the full set of packages that must be tested
    when P changes.

    Algorithm: (1) start with {P}; (2) add every package reachable from P by
    following SOURCE edges in reverse, transitively; (3) add every package
    with a direct TEST or DEFERRED edge into the set built by (1)-(2) --
    one hop only, never traversed further, so a test-only or deferred-only
    consumer's OWN consumers are never pulled in by this step.

    Args:
        source_graph: Forward SOURCE graph (propagates transitively).
        test_graph: Forward TEST graph (terminal -- one hop only).
        deferred_graph: Forward DEFERRED graph (terminal -- one hop only,
            same treatment as test_graph; see the module docstring for why
            a function-body-only src/ import is terminal rather than
            transitively propagating like a SOURCE edge).

    Returns:
        Mapping of package name -> its full closure. Always includes the
        package itself, even when nothing depends on it.
    """
    source_reverse_closures = transitive_reverse_closure(source_graph)
    terminal_reverse_direct: dict[str, set[str]] = {name: set() for name in source_graph}
    for terminal_graph in (test_graph, deferred_graph):
        for consumer, deps in terminal_graph.items():
            for dep in deps:
                if dep in terminal_reverse_direct:
                    terminal_reverse_direct[dep].add(consumer)

    closures: dict[str, set[str]] = {}
    for target in source_graph:
        source_reachable = {target} | source_reverse_closures.get(target, set())
        terminal_additions: set[str] = set()
        for member in source_reachable:
            terminal_additions |= terminal_reverse_direct.get(member, set())
        closures[target] = source_reachable | terminal_additions
    return closures


def check_closure_not_smaller_than_declared(
    declared_only_graph: dict[str, set[str]],
    full_closures: dict[str, set[str]],
) -> list[str]:
    """Non-vacuity guard: the full closure must never be a STRICT SUBSET of
    the declared-source-dependency-only closure for any package.

    A violation means the src/ import scan produced FEWER source edges than
    `[project.dependencies]` alone guarantees -- the signature of scan
    breakage (e.g. an unreadable src/ tree silently treated as empty).

    Args:
        declared_only_graph: Forward SOURCE graph derived from
            `[project.dependencies]` alone (see
            build_declared_source_only_graph).
        full_closures: The real closures (see compute_affected_closures).

    Returns:
        Names of packages that fail the check (empty when all pass).
    """
    declared_closures = transitive_reverse_closure(declared_only_graph)
    violations = []
    for pkg, declared_closure in declared_closures.items():
        if not declared_closure <= full_closures.get(pkg, set()):
            violations.append(pkg)
    return violations


def _resolve_report_targets(
    all_packages: list[str], raw_projects: list[str] | None, use_all: bool
) -> list[str]:
    """Validate and return the packages to report closures for."""
    if use_all:
        if raw_projects:
            raise UsageError("Use either --projects or --all, not both.")
        return sorted(all_packages)
    if not raw_projects:
        raise UsageError("No projects specified. Pass --projects <a,b,c> or --all.")
    names: list[str] = []
    for chunk in raw_projects:
        names.extend(name.strip() for name in chunk.split(",") if name.strip())
    names = list(dict.fromkeys(names))
    unknown = [name for name in names if name not in all_packages]
    if unknown:
        raise UsageError(
            f"Unknown package(s): {', '.join(unknown)}. "
            f"Discovered packages: {', '.join(sorted(all_packages))}."
        )
    return names


def _resolve_output_path(raw_output: str | None, workspace: Path) -> Path:
    """Default to <workspace>/.tmp/test/affected-set.json unless overridden."""
    if raw_output:
        output_path = Path(raw_output).resolve()
    else:
        output_path = workspace.joinpath(".tmp", *_OUTPUT_SUBDIRS, _OUTPUT_FILENAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


# ---------------------------------------------------------------------------
# Self-test harness -- mirrors the repo's established _ok/_fail/_step +
# run_self_test_checks pattern. Runs automatically as step 1 of every
# invocation (see main()); --self-test runs it in isolation.
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


def run_self_test_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check.

    Args:
        checks: Named zero-argument callables; each raises AssertionError on
            failure and returns normally on success.

    Returns:
        True iff every check passed.
    """
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except AssertionError as e:
            _fail(f"{name}: {e}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


def _make_pkg(
    root: Path,
    name: str,
    *,
    imports: list[str] | None = None,
    deferred_imports: list[str] | None = None,
    type_checking_imports: list[str] | None = None,
    test_imports: list[str] | None = None,
    conftest_imports: list[str] | None = None,
    deps: list[str] | None = None,
    dev_only_deps: list[str] | None = None,
    bom: bool = False,
    unparseable_src: bool = False,
) -> Path:
    """Build one synthetic package directory under root: pyproject.toml,
    src/<import_name>/__init__.py (optionally importing `imports` at module
    scope -- SOURCE edges; `deferred_imports` inside a function body --
    DEFERRED edges; `type_checking_imports` inside a module-scope
    `if typing.TYPE_CHECKING:` block -- also SOURCE edges), a tests/
    directory (optionally importing `test_imports` -- TEST edges), an
    optional package-root conftest.py (optionally importing
    `conftest_imports` -- also TEST edges), and optional dev-extra-only
    declared dependencies (`dev_only_deps`, added under
    `[project.optional-dependencies].dev` and never under
    `[project.dependencies]`, i.e. TEST edges by declaration). When
    `unparseable_src` is True, __init__.py is given invalid Python syntax
    instead (all other body arguments are ignored in that case)."""
    import_name = name.replace("-", "_")
    pkg_dir = root / name
    src_pkg = pkg_dir / "src" / import_name
    src_pkg.mkdir(parents=True)
    if unparseable_src:
        body_text = "def broken(:\n    pass\n"
    else:
        body_lines = [f"import {mod}\n" for mod in (imports or [])]
        body_lines.append("VALUE = 1\n")
        if type_checking_imports:
            tc_lines = "".join(f"    import {mod}\n" for mod in type_checking_imports)
            body_lines.append(f"import typing\nif typing.TYPE_CHECKING:\n{tc_lines}")
        if deferred_imports:
            deferred_lines = "".join(f"    import {mod}\n" for mod in deferred_imports)
            body_lines.append(f"def _deferred_loader() -> None:\n{deferred_lines}    return None\n")
        body_text = "".join(body_lines)
    init_path = src_pkg / "__init__.py"
    if bom:
        init_path.write_bytes(b"\xef\xbb\xbf" + body_text.encode("utf-8"))
    else:
        init_path.write_text(body_text, encoding="utf-8")
    (pkg_dir / "tests").mkdir()
    test_body_lines = [f"import {mod}\n" for mod in (test_imports or [])]
    test_body_lines.append("def test_ok():\n    assert True\n")
    (pkg_dir / "tests" / "test_placeholder.py").write_text("".join(test_body_lines), encoding="utf-8")
    dep_lines = "".join(f'    "{dep}",\n' for dep in (deps or []))
    pyproject_parts = [f'[project]\nname = "{name}"\ndependencies = [\n{dep_lines}]\n']
    if dev_only_deps:
        dev_lines = "".join(f'    "{dep}",\n' for dep in dev_only_deps)
        pyproject_parts.append(f'\n[project.optional-dependencies]\ndev = [\n{dev_lines}]\n')
    (pkg_dir / "pyproject.toml").write_text("".join(pyproject_parts), encoding="utf-8")
    if conftest_imports:
        conftest_text = "".join(f"import {mod}\n" for mod in conftest_imports)
        (pkg_dir / "conftest.py").write_text(conftest_text, encoding="utf-8")
    return pkg_dir


def _check_discover_packages_finds_synthetic_tree() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-alpha")
        _make_pkg(root, "datrix-beta")
        (root / "datrix-not-a-package").mkdir()  # no pyproject.toml -- must be excluded
        packages = discover_packages(root)
        assert set(packages) == {"datrix-alpha", "datrix-beta"}, packages


def _check_root_conftest_edge_is_detected() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-common", conftest_imports=["datrix_language"])
        _make_pkg(root, "datrix-language")
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names, include_root_conftest=True
        )
        assert "datrix-language" in test_graph["datrix-common"], (
            f"root conftest.py import of datrix_language must produce a "
            f"datrix-common -> datrix-language TEST edge; got {test_graph['datrix-common']}"
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-common" in closures["datrix-language"], (
            f"datrix-language's closure must include datrix-common (the "
            f"conftest-only consumer); got {closures['datrix-language']}"
        )


def _check_restricted_scan_loses_conftest_edge() -> None:
    """Adversarial: the SAME tree as above, scanned with the root
    conftest.py excluded, must NOT find the edge -- proving the conftest
    scan is load-bearing rather than decorative."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-common", conftest_imports=["datrix_language"])
        _make_pkg(root, "datrix-language")
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names, include_root_conftest=False
        )
        assert "datrix-language" not in test_graph["datrix-common"], (
            f"restricting the scan to src/+tests/ must lose the "
            f"conftest-only edge; got {test_graph['datrix-common']}"
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-common" not in closures["datrix-language"], (
            f"with the conftest edge lost, datrix-language's closure must "
            f"NOT include datrix-common; got {closures['datrix-language']}"
        )


def _check_bom_prefixed_file_is_read() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-gamma", imports=["datrix_alpha"], bom=True)
        _make_pkg(root, "datrix-alpha")
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, _test_graph, _deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        assert "datrix-alpha" in source_graph["datrix-gamma"], (
            f"a BOM-prefixed __init__.py's SOURCE import must still be "
            f"detected; got {source_graph['datrix-gamma']}"
        )


def _check_test_edge_does_not_propagate_to_consumers() -> None:
    """BUG 1 regression check: datrix-a's TESTS import datrix-b (a TEST
    edge); datrix-c's SRC imports datrix-a (a SOURCE edge). datrix-b's
    closure must contain datrix-a (its suite must run when datrix-b
    changes) but must NOT contain datrix-c -- a test edge is terminal, it
    must not make datrix-a's own consumers reachable from datrix-b. This
    check fails against the old model that treats every edge as
    transitively propagating (verified against the pre-fix
    build_import_graph + transitive_reverse_closure pairing)."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-a", test_imports=["datrix_b"])
        _make_pkg(root, "datrix-b")
        _make_pkg(root, "datrix-c", imports=["datrix_a"])
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-a" in closures["datrix-b"], (
            f"datrix-a's TESTS import datrix-b -- datrix-a must be in "
            f"datrix-b's closure; got {closures['datrix-b']}"
        )
        assert "datrix-c" not in closures["datrix-b"], (
            f"datrix-c depends (source) on datrix-a, NOT on datrix-b -- the "
            f"test edge datrix-a -> datrix-b must be terminal and must not "
            f"propagate onward to datrix-a's own consumer datrix-c; "
            f"got {closures['datrix-b']}"
        )


def _check_source_edge_propagates_to_consumers() -> None:
    """Same shape as the previous check, but datrix-a's SRC (not tests)
    imports datrix-b -- a genuine SOURCE edge -- so datrix-b's closure MUST
    include datrix-c: datrix-c depends on datrix-a, which depends on
    datrix-b, so datrix-c transitively depends on datrix-b."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-a", imports=["datrix_b"])
        _make_pkg(root, "datrix-b")
        _make_pkg(root, "datrix-c", imports=["datrix_a"])
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-c" in closures["datrix-b"], (
            f"datrix-a's SRC imports datrix-b and datrix-c's SRC imports "
            f"datrix-a -- source edges must propagate transitively, so "
            f"datrix-b's closure must include datrix-c; got {closures['datrix-b']}"
        )


def _check_package_with_no_consumers_closure_is_self_only() -> None:
    """BUG 2 regression check: a package nobody depends on must still yield
    a closure of exactly itself, never `(none)` -- its own suite always
    runs when it changes."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-lonely")
        _make_pkg(root, "datrix-other")
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert closures["datrix-lonely"] == {"datrix-lonely"}, closures["datrix-lonely"]


def _check_dev_extra_is_test_edge_only() -> None:
    """A package declaring a dependency ONLY under
    `[project.optional-dependencies]` (a dev extra) must produce a TEST
    edge, not a SOURCE edge -- terminal, one hop, no further propagation to
    the declaring package's own consumers."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-a", dev_only_deps=["datrix-b"])
        _make_pkg(root, "datrix-b")
        _make_pkg(root, "datrix-c", imports=["datrix_a"])
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        assert "datrix-b" in test_graph["datrix-a"], (
            f"a dev-extra-only dependency must produce a TEST edge; "
            f"got {test_graph['datrix-a']}"
        )
        assert "datrix-b" not in source_graph["datrix-a"], (
            f"a dev-extra-only dependency must NOT be classified as a "
            f"SOURCE edge; got {source_graph['datrix-a']}"
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-a" in closures["datrix-b"], (
            f"datrix-a's dev extra declares datrix-b -- datrix-a must be in "
            f"datrix-b's closure; got {closures['datrix-b']}"
        )
        assert "datrix-c" not in closures["datrix-b"], (
            f"the dev-extra test edge datrix-a -> datrix-b must be "
            f"terminal -- it must not propagate onward to datrix-a's own "
            f"consumer datrix-c; got {closures['datrix-b']}"
        )


def _check_function_scope_src_import_is_deferred_and_terminal() -> None:
    """THE FIX regression check: datrix-a's src/ imports datrix-b only
    INSIDE a function body (a DEFERRED edge, e.g. an import-cycle-avoidance
    lazy import) instead of at module scope; datrix-c's src/ imports
    datrix-a at module scope (a genuine SOURCE edge). datrix-b's closure
    must contain datrix-a (datrix-a's own suite genuinely exercises the
    deferred import, so it must run when datrix-b changes) but must NOT
    contain datrix-c -- a DEFERRED edge is terminal exactly like a TEST
    edge, and must not propagate onward to datrix-a's own consumer
    datrix-c. This is the shape that previously made a function-body-only
    import count as a full SOURCE edge and balloon a downstream package's
    reverse closure far beyond its real consumers."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-a", deferred_imports=["datrix_b"])
        _make_pkg(root, "datrix-b")
        _make_pkg(root, "datrix-c", imports=["datrix_a"])
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        assert "datrix-b" in deferred_graph["datrix-a"], (
            f"a function-body-only src/ import must produce a DEFERRED "
            f"edge; got {deferred_graph['datrix-a']}"
        )
        assert "datrix-b" not in source_graph["datrix-a"], (
            f"a function-body-only src/ import must NOT be classified as a "
            f"SOURCE edge; got {source_graph['datrix-a']}"
        )
        closures = compute_affected_closures(source_graph, test_graph, deferred_graph)
        assert "datrix-a" in closures["datrix-b"], (
            f"datrix-a's src/ deferred-imports datrix-b -- datrix-a must "
            f"be in datrix-b's closure; got {closures['datrix-b']}"
        )
        assert "datrix-c" not in closures["datrix-b"], (
            f"the deferred edge datrix-a -> datrix-b must be terminal -- "
            f"it must not propagate onward to datrix-a's own consumer "
            f"datrix-c; got {closures['datrix-b']}"
        )


def _check_module_scope_type_checking_import_is_source() -> None:
    """A module-scope `if typing.TYPE_CHECKING:` block is still module
    scope, not a function body -- an import inside it must be classified
    SOURCE (and propagate transitively), not DEFERRED."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-a", type_checking_imports=["datrix_b"])
        _make_pkg(root, "datrix-b")
        _make_pkg(root, "datrix-c", imports=["datrix_a"])
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        source_graph, _test_graph, deferred_graph = build_source_test_and_deferred_graphs(
            packages, import_names
        )
        assert "datrix-b" in source_graph["datrix-a"], (
            f"an import inside a module-scope `if TYPE_CHECKING:` block "
            f"must be classified SOURCE; got {source_graph['datrix-a']}"
        )
        assert "datrix-b" not in deferred_graph["datrix-a"], (
            f"an import inside a module-scope `if TYPE_CHECKING:` block "
            f"must NOT be classified DEFERRED; got {deferred_graph['datrix-a']}"
        )


def _check_unparseable_src_file_raises_usage_error() -> None:
    """A src/ file that fails to parse as Python must raise UsageError from
    the scanner -- never be silently treated as having zero import edges."""
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        _make_pkg(root, "datrix-broken", unparseable_src=True)
        packages = discover_packages(root)
        import_names = {name: discover_import_name(d) for name, d in packages.items()}
        try:
            build_source_test_and_deferred_graphs(packages, import_names)
        except UsageError:
            pass
        else:
            raise AssertionError(
                "an unparseable src/ file must raise UsageError, not be "
                "silently scanned as having zero imports"
            )


def _check_cyclic_edge_does_not_hang() -> None:
    # Direct unit test against a hand-built mutually-cyclic graph -- proves
    # termination and asserts the (correct) resulting closure, rather than
    # relying on a wall-clock timeout to detect a hang.
    graph = {"datrix-a": {"datrix-b"}, "datrix-b": {"datrix-a"}}
    closures = transitive_reverse_closure(graph)
    assert closures["datrix-a"] == {"datrix-a", "datrix-b"}, closures["datrix-a"]
    assert closures["datrix-b"] == {"datrix-a", "datrix-b"}, closures["datrix-b"]

    self_graph = {"datrix-a": {"datrix-a"}}
    self_closures = transitive_reverse_closure(self_graph)
    assert self_closures["datrix-a"] == {"datrix-a"}, self_closures["datrix-a"]


def _check_non_vacuity_guard_detects_shrunk_closure() -> None:
    """The self-check must fail loud when the import-derived closure is a
    STRICT SUBSET of the declared-deps-only closure for some package -- the
    signature of a scan that silently produced fewer edges than
    pyproject.toml alone guarantees."""
    declared_only_graph = {"datrix-a": {"datrix-b"}, "datrix-b": set()}
    broken_full_graph: dict[str, set[str]] = {"datrix-a": set(), "datrix-b": set()}  # scan lost the edge
    full_closures = transitive_reverse_closure(broken_full_graph)
    violations = check_closure_not_smaller_than_declared(declared_only_graph, full_closures)
    assert violations == ["datrix-b"], violations

    intact_full_graph = {"datrix-a": {"datrix-b"}, "datrix-b": set()}
    intact_full_closures = transitive_reverse_closure(intact_full_graph)
    no_violations = check_closure_not_smaller_than_declared(declared_only_graph, intact_full_closures)
    assert no_violations == [], no_violations


def _check_unreadable_pyproject_raises_usage_error() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-set-selftest-") as tmp:
        root = Path(tmp)
        pkg_dir = root / "datrix-broken"
        pkg_dir.mkdir()
        (pkg_dir / "pyproject.toml").write_text("this is not [ valid toml", encoding="utf-8")
        try:
            _declared_pyproject_deps_split(pkg_dir, {"datrix-broken": pkg_dir})
        except UsageError:
            pass
        else:
            raise AssertionError(
                "corrupt pyproject.toml must raise UsageError, not return silently"
            )


_SELF_TEST_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("discover_packages_finds_synthetic_tree", _check_discover_packages_finds_synthetic_tree),
    ("root_conftest_edge_is_detected", _check_root_conftest_edge_is_detected),
    ("restricted_scan_loses_conftest_edge", _check_restricted_scan_loses_conftest_edge),
    ("bom_prefixed_file_is_read", _check_bom_prefixed_file_is_read),
    ("cyclic_edge_does_not_hang", _check_cyclic_edge_does_not_hang),
    ("non_vacuity_guard_detects_shrunk_closure", _check_non_vacuity_guard_detects_shrunk_closure),
    ("unreadable_pyproject_raises_usage_error", _check_unreadable_pyproject_raises_usage_error),
    ("test_edge_does_not_propagate_to_consumers", _check_test_edge_does_not_propagate_to_consumers),
    ("source_edge_propagates_to_consumers", _check_source_edge_propagates_to_consumers),
    (
        "package_with_no_consumers_closure_is_self_only",
        _check_package_with_no_consumers_closure_is_self_only,
    ),
    ("dev_extra_is_test_edge_only", _check_dev_extra_is_test_edge_only),
    (
        "function_scope_src_import_is_deferred_and_terminal",
        _check_function_scope_src_import_is_deferred_and_terminal,
    ),
    (
        "module_scope_type_checking_import_is_source",
        _check_module_scope_type_checking_import_is_source,
    ),
    ("unparseable_src_file_raises_usage_error", _check_unparseable_src_file_raises_usage_error),
]


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive the reverse-dependency closure of every datrix-* package from actual imports."
    )
    parser.add_argument(
        "--projects",
        action="append",
        help="Package name(s) to report closures for; repeatable and/or comma-separated",
    )
    parser.add_argument("--all", action="store_true", help="Report every discovered package's closure")
    parser.add_argument(
        "--output", help="Output JSON path (default <workspace>/.tmp/test/affected-set.json)"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run only the self-test suite and exit -- skips the real "
            "derivation. The same checks also run automatically, "
            "unconditionally, as step 1 of every normal invocation."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _run(args: argparse.Namespace) -> int:
    workspace = get_datrix_root()
    packages = discover_packages(workspace)
    import_names = {name: discover_import_name(d) for name, d in packages.items()}
    source_graph, test_graph, deferred_graph = build_source_test_and_deferred_graphs(
        packages, import_names, include_root_conftest=True
    )
    closures = compute_affected_closures(source_graph, test_graph, deferred_graph)

    declared_source_only_graph = build_declared_source_only_graph(packages)
    violations = check_closure_not_smaller_than_declared(declared_source_only_graph, closures)
    if violations:
        print(
            "ERROR: non-vacuity guard failed -- the closure is SMALLER than "
            f"the declared-[project.dependencies]-only closure for: "
            f"{', '.join(violations)}. This indicates the src/ import scan "
            "silently produced fewer source edges than pyproject.toml alone "
            "guarantees (e.g. an unreadable src/ tree treated as empty). Fix "
            "the scan before trusting this closure.",
            file=sys.stderr,
        )
        return _EXIT_SELFCHECK_FAILED

    targets = _resolve_report_targets(sorted(packages), args.projects, args.all)
    output_path = _resolve_output_path(args.output, workspace)
    payload: dict[str, object] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "packages": {name: sorted(closures[name]) for name in targets},
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for name in targets:
        members = ", ".join(sorted(closures[name])) or "(none)"
        print(f"{name}: {members}")
    print(f"Details: {output_path}")
    return _EXIT_OK


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)

    _step("Self-test: reverse-dependency closure derivation edge cases")
    self_test_passed = run_self_test_checks(_SELF_TEST_CHECKS)
    if args.self_test:
        return _EXIT_OK if self_test_passed else _EXIT_SELFCHECK_FAILED
    if not self_test_passed:
        print(
            "\nError: self-test failed -- refusing to trust the closure "
            "derivation for a real run. Fix the scanner before re-running.",
            file=sys.stderr,
        )
        return _EXIT_SELFCHECK_FAILED

    try:
        return _run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
