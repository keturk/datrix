#!/usr/bin/env python
"""D14 gate: no package's tests resolve a path inside another package's
``tests/`` directory.

A test file that hardcodes ``Path(__file__).resolve().parents[N] /
"datrix-other-package" / "tests" / "fixtures"`` (or imports such a constant
from a sibling module in the same package) makes its own suite depend on
another package's test tree staying exactly as it is. That tree is free to
delete, move or rename anything the reader never declared -- which is exactly
how datrix-common commit ``0badd1c`` turned a routine fixture cleanup into a
red ``datrix-codegen-typescript`` suite: ``COMMON_FIXTURES_DIR /
"system-with-jobs.dtrx"`` pointed at a file datrix-common's own tests no
longer read, so nothing there knew to keep it.

This AST-scans every ``.py`` file under every discovered package's ``tests/``
tree (never regex -- a commented-out or docstring-quoted path must not count)
and evaluates a small, real subset of ``pathlib`` expressions statically:
``Path(__file__)``, ``.resolve()``, ``.parent``/``.parents[N]``, and ``/``
joins against string literals or previously-resolved names (including names
imported with ``from tests.<module> import NAME`` -- always the SAME
package's own ``tests/`` namespace, so it resolves within that package).

Two things are reported, both from the same evaluation:

  (a) NEGATIVE -- a resolved directory whose path contains another
      discovered package's own directory name followed by a ``tests``
      segment. Reported regardless of whether the fixture file it is later
      joined against exists; the cross-package DIRECTORY reference is
      already the D14 violation.
  (b) POSITIVE (non-vacuity) -- of the fixture PATHS this scan can resolve to
      a full file (a directory constant joined with a literal or a
      previously-resolved name ending in ``.dtrx``/``.dcfg``/``.json``),
      any that do not exist on disk.

Exit codes: 0 = clean (or a successful ``--self-test``), 1 = a violation was
found, 2 = usage error, no packages discovered, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: Extensions that mark a resolved join as "a fixture file", for the
#: existence (positive) check. Anything else resolved is a directory, only
#: ever checked for the cross-package (negative) violation.
_FIXTURE_SUFFIXES: frozenset[str] = frozenset({".dtrx", ".dcfg", ".json"})

_SKIP_DIR_NAMES: frozenset[str] = frozenset({"__pycache__", "node_modules"})


@dataclass(frozen=True)
class CrossPackageViolation:
    """A directory constant that resolves into another package's tests/ tree."""

    path: Path
    line: int
    name: str
    resolved_dir: Path
    other_package: str

    def render(self, base_dir: Path) -> str:
        shown = _relative(self.path, base_dir)
        return (
            f"  {shown}:{self.line}  {self.name} resolves to "
            f"{_relative(self.resolved_dir, base_dir)} -- inside "
            f"{self.other_package}'s own tests/ tree (D14)"
        )


@dataclass(frozen=True)
class MissingFixture:
    """A statically-resolved fixture path that does not exist on disk."""

    path: Path
    line: int
    expr: str
    resolved_file: Path

    def render(self, base_dir: Path) -> str:
        shown = _relative(self.path, base_dir)
        return (
            f"  {shown}:{self.line}  {self.expr} resolves to "
            f"{_relative(self.resolved_file, base_dir)}, which does not exist"
        )


def _relative(path: Path, base_dir: Path) -> Path:
    try:
        return path.relative_to(base_dir)
    except ValueError:
        return path


# ---------------------------------------------------------------------------
# Package discovery -- from disk, never a hardcoded list.
# ---------------------------------------------------------------------------


def discover_packages(base_dir: Path) -> dict[str, Path]:
    """Every ``datrix*`` directory at *base_dir* carrying a ``tests/`` tree.

    Returns:
        ``{package name: tests/ directory}``, sorted by name.
    """
    packages: dict[str, Path] = {}
    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("datrix"):
            continue
        tests_dir = entry / "tests"
        if tests_dir.is_dir():
            packages[entry.name] = tests_dir
    return packages


def _discover_python_files(tests_dir: Path) -> list[Path]:
    return sorted(
        p for p in tests_dir.rglob("*.py") if not any(part in _SKIP_DIR_NAMES for part in p.parts)
    )


# ---------------------------------------------------------------------------
# A tiny static evaluator for the pathlib expressions these fixtures use.
# ---------------------------------------------------------------------------

#: A resolved value: either a concrete Path, or a string segment (from a
#: literal, an f-string of only literal parts, or a resolved string constant).
_Resolved = Path | str


class _Scope:
    """Name -> resolved value, for one module (plus its "from tests.X import
    NAME" cross-references within the same package)."""

    def __init__(self, package_root: Path, package_tests_root: Path) -> None:
        self.package_root = package_root
        self.package_tests_root = package_tests_root
        self.values: dict[str, _Resolved] = {}
        #: module dotted path ("tests.conftest") -> resolved values, filled
        #: lazily as sibling modules are visited.
        self._module_cache: dict[str, dict[str, _Resolved]] = {}

    def module_values(self, dotted: str) -> dict[str, _Resolved]:
        """Resolve every top-level constant of ``tests.<sub>`` within this
        same package (imports of this shape are always intra-package)."""
        if dotted in self._module_cache:
            return self._module_cache[dotted]
        parts = dotted.split(".")
        if parts[0] != "tests":
            self._module_cache[dotted] = {}
            return {}
        rel = parts[1:]
        candidate = self.package_tests_root.joinpath(*rel[:-1], f"{rel[-1]}.py") if rel else None
        if candidate is None or not candidate.is_file():
            candidate = self.package_tests_root.joinpath(*rel, "__init__.py") if rel else None
        if candidate is None or not candidate.is_file():
            self._module_cache[dotted] = {}
            return {}
        tree = _parse(candidate)
        if tree is None:
            self._module_cache[dotted] = {}
            return {}
        sub_scope = _Scope(self.package_root, self.package_tests_root)
        collect_module_assignments(tree, candidate, sub_scope)
        self._module_cache[dotted] = sub_scope.values
        return sub_scope.values


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def _eval_path_expr(node: ast.expr, file_path: Path, scope: _Scope) -> _Resolved | None:
    """Evaluate a restricted grammar of pathlib expressions to a concrete
    value. Returns None when the expression is not one of the recognized
    shapes (dynamic input, an unresolvable name, ...)."""
    if isinstance(node, ast.Call):
        return _eval_call(node, file_path, scope)
    if isinstance(node, ast.Attribute):
        return _eval_attribute(node, file_path, scope)
    if isinstance(node, ast.Subscript):
        return _eval_subscript(node, file_path, scope)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _eval_path_expr(node.left, file_path, scope)
        right = _eval_segment(node.right, file_path, scope)
        if isinstance(left, Path) and right is not None:
            return left / right
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return scope.values.get(node.id)
    if isinstance(node, ast.JoinedStr):
        return _eval_fstring(node, file_path, scope)
    return None


def _eval_segment(node: ast.expr, file_path: Path, scope: _Scope) -> str | None:
    """A path segment on the right of a ``/`` -- a string literal, a resolved
    name, or a purely-literal f-string. A dynamic segment (a parameter, a
    function call) yields None, so the join is abandoned rather than guessed."""
    value = _eval_path_expr(node, file_path, scope)
    return value if isinstance(value, str) else None


def _eval_fstring(node: ast.JoinedStr, file_path: Path, scope: _Scope) -> str | None:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
            continue
        if isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
            resolved = scope.values.get(value.value.id)
            if isinstance(resolved, str):
                parts.append(resolved)
                continue
        return None
    return "".join(parts)


def _eval_call(node: ast.Call, file_path: Path, scope: _Scope) -> _Resolved | None:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == "__file__":
            return file_path
        return None
    if isinstance(func, ast.Attribute) and func.attr == "resolve":
        return _eval_path_expr(func.value, file_path, scope)
    return None


def _eval_attribute(node: ast.Attribute, file_path: Path, scope: _Scope) -> _Resolved | None:
    if node.attr == "resolve":
        return _eval_path_expr(node.value, file_path, scope)
    if node.attr == "parent":
        base = _eval_path_expr(node.value, file_path, scope)
        return base.parent if isinstance(base, Path) else None
    return None


def _eval_subscript(node: ast.Subscript, file_path: Path, scope: _Scope) -> _Resolved | None:
    value = node.value
    if not (isinstance(value, ast.Attribute) and value.attr == "parents"):
        return None
    index = node.slice
    if not (isinstance(index, ast.Constant) and isinstance(index.value, int)):
        return None
    base = _eval_path_expr(value.value, file_path, scope)
    if not isinstance(base, Path):
        return None
    parents = list(base.parents)
    n = index.value
    return parents[n] if 0 <= n < len(parents) else None


# ---------------------------------------------------------------------------
# Per-file collection
# ---------------------------------------------------------------------------


def collect_module_assignments(tree: ast.Module, file_path: Path, scope: _Scope) -> None:
    """Fill *scope* with every ``NAME = <path-expr>`` this module defines
    (module-level and nested -- some packages define the constant inside a
    fixture function), in source order, plus the values these constants
    resolve to."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        resolved = _eval_path_expr(node.value, file_path, scope)
        if resolved is not None:
            scope.values[target.id] = resolved


def _import_aliases(tree: ast.Module) -> list[tuple[str, str, str]]:
    """Every ``from tests.<sub> import NAME [as ALIAS]`` -- (module, name, local)."""
    aliases: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module != "tests" and not node.module.startswith("tests."):
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            aliases.append((node.module, alias.name, local))
    return aliases


def scan_file(
    file_path: Path, package_root: Path, package_tests_root: Path,
) -> tuple[list[CrossPackageViolation], list[MissingFixture]]:
    """Every cross-package directory constant and unresolved fixture path in
    one test module."""
    tree = _parse(file_path)
    if tree is None:
        return [], []
    scope = _Scope(package_root, package_tests_root)
    collect_module_assignments(tree, file_path, scope)
    for module, name, local in _import_aliases(tree):
        values = scope.module_values(module)
        if name in values:
            scope.values[local] = values[name]

    violations: list[CrossPackageViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        resolved = scope.values.get(target.id)
        if not isinstance(resolved, Path):
            continue
        other = _other_package_tests_hit(resolved, package_root)
        if other is not None:
            violations.append(
                CrossPackageViolation(file_path, node.lineno, target.id, resolved, other)
            )

    missing: list[MissingFixture] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        resolved = _eval_path_expr(node, file_path, scope)
        if not isinstance(resolved, Path) or resolved.suffix not in _FIXTURE_SUFFIXES:
            continue
        if resolved.exists():
            continue
        missing.append(MissingFixture(file_path, node.lineno, ast.unparse(node), resolved))
    return violations, missing


def _other_package_tests_hit(resolved_dir: Path, own_package_root: Path) -> str | None:
    """The OTHER package's name, if *resolved_dir* sits inside some
    ``datrix*`` package's own ``tests/`` tree that is not *own_package_root*."""
    parts = resolved_dir.parts
    for index, part in enumerate(parts):
        if not part.startswith("datrix"):
            continue
        candidate_root = Path(*parts[: index + 1])
        if candidate_root == own_package_root:
            continue
        if index + 1 < len(parts) and parts[index + 1] == "tests":
            return part
    return None


# ---------------------------------------------------------------------------
# Workspace scan
# ---------------------------------------------------------------------------


def scan_workspace(base_dir: Path, *, verbose: bool = False) -> tuple[
    list[CrossPackageViolation], list[MissingFixture], int
]:
    packages = discover_packages(base_dir)
    violations: list[CrossPackageViolation] = []
    missing: list[MissingFixture] = []
    file_count = 0
    for package_name, tests_dir in packages.items():
        package_root = tests_dir.parent
        for file_path in _discover_python_files(tests_dir):
            file_count += 1
            if verbose:
                print(f"  scanning {package_name}: {file_path}")
            file_violations, file_missing = scan_file(file_path, package_root, tests_dir)
            violations.extend(file_violations)
            missing.extend(file_missing)
    return violations, missing, file_count


# ---------------------------------------------------------------------------
# Self-test -- plants both defect shapes and one clean case, in a temp tree.
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_self_test() -> bool:
    ok = True
    with tempfile.TemporaryDirectory(prefix="cross-pkg-fixture-gate-") as tmp:
        root = Path(tmp)
        pkg_a = root / "datrix-pkg-a"
        pkg_b = root / "datrix-pkg-b"
        _write(pkg_b / "tests" / "fixtures" / "real.dtrx", "// real\n")

        # (a) cross-package directory constant -- must be caught.
        _write(
            pkg_a / "tests" / "conftest.py",
            'from pathlib import Path\n'
            'OTHER_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "datrix-pkg-b" / "tests" / "fixtures"\n'
            'LOCAL_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"\n',
        )
        # (b) missing fixture via a LOCAL (own-package) constant -- must be caught.
        _write(
            pkg_a / "tests" / "test_missing.py",
            'from tests.conftest import LOCAL_FIXTURES_DIR\n'
            'PATH = LOCAL_FIXTURES_DIR / "does-not-exist.dtrx"\n',
        )
        # (c) clean: local constant, existing file -- must NOT be caught.
        _write(pkg_a / "tests" / "fixtures" / "own.dtrx", "// own\n")
        _write(
            pkg_a / "tests" / "test_clean.py",
            'from tests.conftest import LOCAL_FIXTURES_DIR\n'
            'PATH = LOCAL_FIXTURES_DIR / "own.dtrx"\n',
        )

        violations, missing, files = scan_workspace(root)

        ok &= _assert(files == 3, f"scans exactly the 3 planted files (got {files})")
        cross_names = {v.name for v in violations}
        ok &= _assert(
            "OTHER_FIXTURES_DIR" in cross_names and len(violations) == 1,
            f"the cross-package directory constant is the one violation found (got {cross_names})",
        )
        if violations:
            ok &= _assert(
                violations[0].other_package == "datrix-pkg-b",
                f"names the other package correctly (got {violations[0].other_package})",
            )
        missing_files = {m.resolved_file.name for m in missing}
        ok &= _assert(
            "does-not-exist.dtrx" in missing_files and "own.dtrx" not in missing_files,
            f"reports the missing fixture and not the existing one (got {missing_files})",
        )

    # Non-vacuity against the EXACT shape of the real incident: datrix-common
    # commit 0badd1c deleted tests/fixtures/system-with-jobs.dtrx while
    # datrix-codegen-typescript/tests/conftest.py still resolved it through a
    # two-step chain -- an intermediate _MONOREPO_ROOT constant, then
    # COMMON_FIXTURES_DIR = _MONOREPO_ROOT / "datrix-common" / "tests" / "fixtures"
    # -- read from a SIBLING module via "from tests.conftest import ...", and
    # joined against the literal filename at the call site. This plants that
    # precise chain (two-variable resolution, cross-module import, real
    # missing-file literal) rather than asserting against the live workspace,
    # so the self-test does not go vacuous once the incident itself is fixed.
    with tempfile.TemporaryDirectory(prefix="cross-pkg-fixture-gate-incident-") as tmp:
        root = Path(tmp)
        pkg = root / "datrix-codegen-typescript"
        other = root / "datrix-common"
        _write(other / "tests" / "fixtures" / "system-basic.dtrx", "// unrelated, still present\n")
        _write(
            pkg / "tests" / "conftest.py",
            'from pathlib import Path\n'
            '_MONOREPO_ROOT = Path(__file__).resolve().parents[2]\n'
            'COMMON_FIXTURES_DIR = _MONOREPO_ROOT / "datrix-common" / "tests" / "fixtures"\n',
        )
        _write(
            pkg / "tests" / "test_jobs_generator.py",
            'from tests.conftest import COMMON_FIXTURES_DIR\n'
            'path = COMMON_FIXTURES_DIR / "system-with-jobs.dtrx"\n',
        )
        incident_violations, incident_missing, _ = scan_workspace(root)
        ok &= _assert(
            any(v.name == "COMMON_FIXTURES_DIR" and v.other_package == "datrix-common"
                for v in incident_violations),
            "the incident's two-step, cross-module COMMON_FIXTURES_DIR chain "
            f"is caught as a datrix-common cross-package read (got {incident_violations})",
        )
        ok &= _assert(
            any(m.resolved_file.name == "system-with-jobs.dtrx" for m in incident_missing),
            f"the incident's own missing fixture (system-with-jobs.dtrx) is caught (got {incident_missing})",
        )
    return ok


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", default="", help="Monorepo root")
    parser.add_argument("--self-test", action="store_true", help="Self-test only")
    parser.add_argument("--verbose", action="store_true", help="Print scanned files")
    args = parser.parse_args(argv)

    print("Non-vacuity self-test:")
    if not run_self_test():
        print("Error: self-test FAILED; the real scan cannot be trusted.", file=sys.stderr)
        return 2
    if args.self_test:
        return 0

    base_dir = Path(args.base_dir).resolve() if args.base_dir else Path(__file__).resolve().parents[3]
    if not base_dir.is_dir():
        print(f"Base directory not found: {base_dir}", file=sys.stderr)
        return 2

    violations, missing, file_count = scan_workspace(base_dir, verbose=args.verbose)
    packages = discover_packages(base_dir)
    if not packages:
        print(f"No datrix* package with a tests/ tree found under {base_dir}", file=sys.stderr)
        return 2

    print(
        f"\nScanned {file_count} test file(s) across {len(packages)} package(s): "
        f"{', '.join(sorted(packages))}"
    )
    if violations or missing:
        print(
            f"\nCROSS-PACKAGE FIXTURE READ GATE FAILED: "
            f"{len(violations)} cross-package reference(s), {len(missing)} missing fixture(s)\n",
        )
        for violation in violations:
            print(violation.render(base_dir))
        for entry in missing:
            print(entry.render(base_dir))
        print(
            "\nA fixture read by one package lives in that package's own tests/fixtures/. "
            "A fixture read by several packages lives in datrix-testing as shared package "
            "data, reached through a datrix_testing function or constant -- never a "
            "relative path into another package's tests/ tree."
        )
        return 1
    print("\n[OK] no package's tests resolve a path inside another package's tests/ directory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
