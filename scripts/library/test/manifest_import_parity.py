#!/usr/bin/env python3
"""Manifest / import parity gate -- the declared Datrix dependency set of every
package equals the Datrix packages its ``src/`` tree actually imports.

Datrix is a family of separately installable packages that are always developed
inside one shared editable venv. That venv makes every package importable from
every other, so a package can import a sibling it never declared, or declare a
sibling it never imports, and nothing fails: the resolver is never consulted.
Both shapes shipped and both lied about the architecture -- a package whose
adopted decisions said it was fenced out of the shared codegen layer imported
that layer from a dozen production modules, a platform package ran on an
undeclared dependency, three language packages carried a dead dependency, and
one package pulled a test-only extra (and with it a parser package and a test
framework) into production.

This gate is the set comparison that seam lacked. For every ``datrix-*``
directory at the workspace root carrying a ``pyproject.toml``:

* **declared** = the ``datrix-*`` distributions named in ``[project]
  dependencies`` (extras and markers stripped; a test-only extra such as
  ``[testkit]`` on a runtime requirement is its own violation);
* **imported** = the ``datrix_*`` import roots any ``.py`` under ``src/``
  imports (absolute ``import``/``from ... import``; relative imports are
  intra-package by construction and ignored), mapped to distribution names by
  the ``_`` -> ``-`` spelling every Datrix package uses.

``imported - declared`` must be empty (an undeclared dependency), and
``declared - imported`` must be empty (a dead declaration). Both are hard
zeros -- there is no baseline, because there is no legitimate steady state in
which a manifest disagrees with the import set. Imports made only under
``if TYPE_CHECKING:`` still count: a type-checking install needs the package
too, and a type-only edge to an undeclared package is the same manifest lie
in a quieter form.

The package set is discovered from disk, never a hardcoded list, so a new
``datrix-codegen-<x>`` package is covered the moment its directory exists.

Runs a built-in non-vacuity self-test on every invocation (a synthetic
package tree with one planted undeclared import, one planted dead
declaration, one planted test-only extra and one clean package), plus a
live-tree proof that the scanner sees a known real edge.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

Usage:
    python manifest_import_parity.py
    python manifest_import_parity.py --debug
    python manifest_import_parity.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import logging
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from packaging.requirements import InvalidRequirement, Requirement

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
#: The monorepo root containing every ``datrix-*`` checkout (this file lives at
#: ``datrix/scripts/library/test/``).
WORKSPACE_ROOT: Final[Path] = _HERE.parents[4]

#: Directory-name prefix identifying a Datrix package at the workspace root.
#: The ``datrix`` showcase repo has no trailing hyphen and is never matched.
_PACKAGE_DIR_PREFIX: Final[str] = "datrix-"
_SRC_SUBDIR_NAME: Final[str] = "src"
_PYPROJECT_NAME: Final[str] = "pyproject.toml"
#: Import-root prefix every Datrix package's importable module uses.
_IMPORT_ROOT_PREFIX: Final[str] = "datrix_"
#: Directories under ``src/`` that hold no scannable source.
_SKIPPED_DIR_SUFFIXES: Final[tuple[str, ...]] = ("__pycache__", ".egg-info")

#: Extras that exist to install a TEST surface (the conformance kit, the dev
#: toolchain, a property-testing library). A CONSUMER's runtime requirement
#: carrying one of these drags that surface into every production install of
#: the consumer.
_TEST_ONLY_EXTRAS: Final[frozenset[str]] = frozenset({"testkit", "dev", "testing"})

#: A PROVIDER's own extras that never satisfy a ``src/`` import: they install
#: the toolchain that runs the provider's tests, not anything its shipped
#: modules may import. Every other extra (``testkit``, ``lsp``, ...) is an
#: optional feature surface: a ``src/`` subtree that imports a sibling only
#: reachable through such an extra is a declared optional dependency, and the
#: gate reports it as satisfied-by-extra rather than as undeclared.
_DEV_EXTRAS: Final[frozenset[str]] = frozenset({"dev", "testing"})

#: A currently-real edge the live-tree proof must see: every language package
#: imports the shared codegen layer. Expressed as (import root, distribution)
#: rather than a package literal, so the proof reads the registered language set
#: from disk and never names one language.
_KNOWN_LIVE_IMPORTED_DIST: Final[str] = "datrix-codegen-common"

_MIN_PACKAGES_FOR_COMPARISON: Final[int] = 2

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: Self-test-only synthetic names, unmistakably not real packages.
_SELF_TEST_PKG_DIRTY: Final[str] = "datrix-selftest-dirty"
_SELF_TEST_PKG_CLEAN: Final[str] = "datrix-selftest-clean"
_SELF_TEST_DIST_UNDECLARED: Final[str] = "datrix-selftest-undeclared"
_SELF_TEST_DIST_DEAD: Final[str] = "datrix-selftest-dead"
_SELF_TEST_DIST_TYPE_ONLY: Final[str] = "datrix-selftest-typeonly"
_SELF_TEST_DIST_OPTIONAL: Final[str] = "datrix-selftest-optional"
_SELF_TEST_DIST_DEV_ONLY: Final[str] = "datrix-selftest-devonly"


def import_root_to_distribution(import_root: str) -> str:
    """``datrix_codegen_common`` -> ``datrix-codegen-common``."""
    return import_root.replace("_", "-")


def distribution_to_import_root(distribution: str) -> str:
    """``datrix-codegen-common`` -> ``datrix_codegen_common``."""
    return distribution.replace("-", "_")


@dataclass(frozen=True)
class PackageManifest:
    """What one package's ``pyproject.toml`` declares about Datrix siblings.

    ``declared`` is the runtime set (``[project] dependencies``);
    ``declared_optional`` maps each sibling reachable only through one of the
    package's own non-dev extras to the extra names that declare it.
    """

    distribution: str
    package_dir: Path
    declared: frozenset[str]
    declared_optional: Mapping[str, tuple[str, ...]]
    test_only_extra_requirements: tuple[str, ...]


@dataclass(frozen=True)
class PackageImports:
    """What one package's ``src/`` tree imports from Datrix siblings."""

    distribution: str
    own_import_roots: frozenset[str]
    imported: frozenset[str]


@dataclass(frozen=True)
class ParityViolation:
    """One manifest/import disagreement for one package.

    ``subject`` is the sibling distribution (or the raw requirement string for
    a test-only-extra violation) the disagreement is about, so a consumer can
    compare violations without parsing ``detail``.
    """

    distribution: str
    kind: str
    subject: str
    detail: str


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_packages(workspace_root: Path) -> dict[str, Path]:
    """Every ``datrix-*`` directory carrying a ``pyproject.toml``, keyed by the
    distribution name its manifest declares.

    Raises:
        ValueError: If a manifest declares no ``[project] name``.
    """
    packages: dict[str, Path] = {}
    for candidate in sorted(workspace_root.iterdir()):
        if not candidate.is_dir() or not candidate.name.startswith(_PACKAGE_DIR_PREFIX):
            continue
        pyproject = candidate / _PYPROJECT_NAME
        if not pyproject.is_file():
            continue
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name = data.get("project", {}).get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{pyproject} declares no [project] name. Every Datrix package "
                f"manifest must name its distribution. Fix: add `name = \"...\"` "
                f"under [project]."
            )
        packages[name] = candidate
    return packages


def read_manifest(distribution: str, package_dir: Path) -> PackageManifest:
    """Parse ``[project] dependencies`` into the declared Datrix sibling set.

    Raises:
        ValueError: If a requirement string is not PEP 508.
    """
    pyproject = package_dir / _PYPROJECT_NAME
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    declared: set[str] = set()
    flagged: list[str] = []
    for raw in project.get("dependencies", []):
        requirement = _parse_requirement(pyproject, raw)
        if not requirement.name.startswith(_PACKAGE_DIR_PREFIX):
            continue
        declared.add(requirement.name)
        if requirement.extras & _TEST_ONLY_EXTRAS:
            flagged.append(raw)
    declared_optional: dict[str, list[str]] = {}
    for extra, raw_requirements in project.get("optional-dependencies", {}).items():
        if extra in _DEV_EXTRAS:
            continue
        for raw in raw_requirements:
            requirement = _parse_requirement(pyproject, raw)
            if requirement.name.startswith(_PACKAGE_DIR_PREFIX):
                declared_optional.setdefault(requirement.name, []).append(extra)
    return PackageManifest(
        distribution=distribution,
        package_dir=package_dir,
        declared=frozenset(declared),
        declared_optional={name: tuple(extras) for name, extras in declared_optional.items()},
        test_only_extra_requirements=tuple(flagged),
    )


def _parse_requirement(pyproject: Path, raw: str) -> Requirement:
    try:
        return Requirement(raw)
    except InvalidRequirement as exc:
        raise ValueError(
            f"{pyproject}: dependency {raw!r} is not a valid PEP 508 "
            f"requirement ({exc}). Fix: correct the requirement string."
        ) from exc


def _own_import_roots(src_dir: Path) -> frozenset[str]:
    """The import roots this package itself provides: every top-level
    ``datrix_*`` directory directly under ``src/``."""
    return frozenset(
        child.name
        for child in src_dir.iterdir()
        if child.is_dir()
        and child.name.startswith(_IMPORT_ROOT_PREFIX)
        and not child.name.endswith(_SKIPPED_DIR_SUFFIXES)
    )


def _is_skipped_dir(path: Path) -> bool:
    return any(part.endswith(_SKIPPED_DIR_SUFFIXES) for part in path.parts)


def _datrix_import_roots_in_module(module_path: Path) -> frozenset[str]:
    """Every absolute ``datrix_*`` import root one module imports.

    Raises:
        SyntaxError: If the module does not parse -- a scan error, never a skip.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8-sig"), filename=str(module_path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root.startswith(_IMPORT_ROOT_PREFIX):
                    roots.add(root)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".", 1)[0]
            if root.startswith(_IMPORT_ROOT_PREFIX):
                roots.add(root)
    return frozenset(roots)


def scan_package_imports(distribution: str, package_dir: Path) -> PackageImports:
    """Every Datrix sibling distribution the package's ``src/`` tree imports.

    Raises:
        ValueError: If the package has no ``src/`` directory.
    """
    src_dir = package_dir / _SRC_SUBDIR_NAME
    if not src_dir.is_dir():
        raise ValueError(
            f"{package_dir} has a {_PYPROJECT_NAME} but no {_SRC_SUBDIR_NAME}/ "
            f"directory. Every Datrix package keeps its importable code under "
            f"src/. Fix: add the src/ layout or remove the manifest."
        )
    own_roots = _own_import_roots(src_dir)
    imported_roots: set[str] = set()
    for module_path in sorted(src_dir.rglob("*.py")):
        if _is_skipped_dir(module_path.relative_to(src_dir)):
            continue
        imported_roots |= _datrix_import_roots_in_module(module_path)
    imported = frozenset(
        import_root_to_distribution(root) for root in imported_roots if root not in own_roots
    )
    return PackageImports(distribution=distribution, own_import_roots=own_roots, imported=imported)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare(manifest: PackageManifest, imports: PackageImports) -> list[ParityViolation]:
    """``imported - declared`` and ``declared - imported`` must both be empty,
    and no runtime requirement may carry a test-only extra.

    An import satisfied only by one of the package's own non-dev extras is a
    declared optional dependency: logged, never a violation.
    """
    violations: list[ParityViolation] = []
    for dist in sorted(imports.imported - manifest.declared):
        extras = manifest.declared_optional.get(dist)
        if extras:
            logger.info(
                "%s imports %s, declared only by optional extra(s) %s",
                manifest.distribution,
                distribution_to_import_root(dist),
                ", ".join(f"[{extra}]" for extra in extras),
            )
            continue
        violations.append(
            ParityViolation(
                manifest.distribution,
                "undeclared-import",
                dist,
                f"src/ imports {distribution_to_import_root(dist)} but [project] "
                f"dependencies does not declare {dist}. Fix: add {dist!r} to "
                f"dependencies in {manifest.package_dir / _PYPROJECT_NAME}.",
            )
        )
    for dist in sorted(manifest.declared - imports.imported):
        violations.append(
            ParityViolation(
                manifest.distribution,
                "dead-declaration",
                dist,
                f"[project] dependencies declares {dist} but nothing under src/ "
                f"imports {distribution_to_import_root(dist)}. Fix: remove {dist!r} "
                f"from dependencies in {manifest.package_dir / _PYPROJECT_NAME}.",
            )
        )
    for raw in manifest.test_only_extra_requirements:
        violations.append(
            ParityViolation(
                manifest.distribution,
                "test-only-extra-at-runtime",
                raw,
                f"[project] dependencies carries {raw!r}, whose extra installs a "
                f"test surface into production. Fix: declare the bare "
                f"distribution at runtime and move the extra to the dev list.",
            )
        )
    return violations


def scan_workspace(workspace_root: Path) -> dict[str, list[ParityViolation]]:
    """Run the comparison over every discovered package.

    Raises:
        SystemExit: ``EXIT_USAGE`` if fewer than two packages are found -- a
            parity check over one package is vacuous.
    """
    packages = discover_packages(workspace_root)
    if len(packages) < _MIN_PACKAGES_FOR_COMPARISON:
        logger.error(
            "Manifest/import parity requires at least %d datrix-* packages under %s; "
            "found %d (%s).",
            _MIN_PACKAGES_FOR_COMPARISON,
            workspace_root,
            len(packages),
            sorted(packages),
        )
        raise SystemExit(EXIT_USAGE)
    report: dict[str, list[ParityViolation]] = {}
    for distribution, package_dir in sorted(packages.items()):
        manifest = read_manifest(distribution, package_dir)
        imports = scan_package_imports(distribution, package_dir)
        logger.debug(
            "package=%s declared=%s imported=%s",
            distribution,
            sorted(manifest.declared),
            sorted(imports.imported),
        )
        report[distribution] = compare(manifest, imports)
    return report


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    print(f"[{'OK' if condition else 'FAIL'}] {label}")
    return condition


def _write_synthetic_package(
    root: Path,
    distribution: str,
    dependencies: tuple[str, ...],
    module_source: str,
    optional_dependencies: Mapping[str, tuple[str, ...]] | None = None,
) -> None:
    """Plant one synthetic package: a manifest and one src module."""
    import_root = distribution_to_import_root(distribution)
    package_dir = root / distribution
    src_pkg = package_dir / _SRC_SUBDIR_NAME / import_root
    src_pkg.mkdir(parents=True)
    deps = ", ".join(f'"{dep}"' for dep in dependencies)
    manifest = (
        f'[project]\nname = "{distribution}"\nversion = "0.0.0"\n'
        f"dependencies = [{deps}]\n"
    )
    if optional_dependencies:
        manifest += "\n[project.optional-dependencies]\n"
        for extra, extra_deps in optional_dependencies.items():
            joined = ", ".join(f'"{dep}"' for dep in extra_deps)
            manifest += f"{extra} = [{joined}]\n"
    (package_dir / _PYPROJECT_NAME).write_text(manifest, encoding="utf-8")
    (src_pkg / "__init__.py").write_text("", encoding="utf-8")
    (src_pkg / "module.py").write_text(module_source, encoding="utf-8")


def _self_test_synthetic_tree(tmp_root: Path) -> bool:
    """A dirty package must yield exactly its three planted violations; a
    clean one must yield none; a type-only import still counts."""
    dirty_source = (
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        f"import {distribution_to_import_root(_SELF_TEST_DIST_UNDECLARED)}\n"
        f"from {distribution_to_import_root(_SELF_TEST_PKG_CLEAN)}.module import thing\n"
        f"import {distribution_to_import_root(_SELF_TEST_DIST_OPTIONAL)}\n"
        f"import {distribution_to_import_root(_SELF_TEST_DIST_DEV_ONLY)}\n"
        "if TYPE_CHECKING:\n"
        f"    from {distribution_to_import_root(_SELF_TEST_DIST_TYPE_ONLY)} import T\n"
        "from . import sibling\n"
    )
    _write_synthetic_package(
        tmp_root,
        _SELF_TEST_PKG_DIRTY,
        (
            f"{_SELF_TEST_PKG_CLEAN}[testkit]",
            _SELF_TEST_DIST_DEAD,
            "pydantic>=2.0",
        ),
        dirty_source,
        optional_dependencies={
            "kit": (_SELF_TEST_DIST_OPTIONAL,),
            "dev": (_SELF_TEST_DIST_DEV_ONLY,),
        },
    )
    _write_synthetic_package(tmp_root, _SELF_TEST_PKG_CLEAN, (), "thing = 1\n")

    report = scan_workspace(tmp_root)
    dirty = report[_SELF_TEST_PKG_DIRTY]
    clean = report[_SELF_TEST_PKG_CLEAN]
    kinds = sorted((v.kind, v.subject) for v in dirty)
    found_undeclared = {v.subject for v in dirty if v.kind == "undeclared-import"}
    found_dead = {v.subject for v in dirty if v.kind == "dead-declaration"}
    found_extras = [v.subject for v in dirty if v.kind == "test-only-extra-at-runtime"]
    ok = True
    ok &= _assert(
        found_undeclared
        == {_SELF_TEST_DIST_UNDECLARED, _SELF_TEST_DIST_TYPE_ONLY, _SELF_TEST_DIST_DEV_ONLY},
        "planted undeclared imports (plain, TYPE_CHECKING-only, and dev-extra-only) are all reported",
    )
    ok &= _assert(
        _SELF_TEST_DIST_OPTIONAL not in found_undeclared,
        "an import declared by the package's own non-dev extra is satisfied, not undeclared",
    )
    ok &= _assert(
        found_dead == {_SELF_TEST_DIST_DEAD},
        "planted dead declaration is reported and the used declaration is not",
    )
    ok &= _assert(
        found_extras == [f"{_SELF_TEST_PKG_CLEAN}[testkit]"],
        "planted test-only extra on a runtime requirement is reported",
    )
    ok &= _assert(len(dirty) == 5, f"dirty package yields exactly five violations (got {kinds})")
    ok &= _assert(clean == [], "clean package yields zero violations")
    return ok


def _self_test_live_edge() -> bool:
    """The live scan must see every registered language package importing the
    shared codegen layer -- a real, load-bearing edge; a scanner that only
    works on synthetic trees proves nothing about the tree it guards."""
    packages = discover_packages(WORKSPACE_ROOT)
    language_packages = [
        dist
        for dist, package_dir in packages.items()
        if _declares_entry_point_group(package_dir, "datrix.languages")
    ]
    if not language_packages:
        return _assert(False, "live tree registers at least one datrix.languages package")
    ok = True
    for dist in sorted(language_packages):
        imports = scan_package_imports(dist, packages[dist])
        ok &= _assert(
            _KNOWN_LIVE_IMPORTED_DIST in imports.imported,
            f"live scan sees {dist} import {_KNOWN_LIVE_IMPORTED_DIST}",
        )
    return ok


def _declares_entry_point_group(package_dir: Path, group: str) -> bool:
    data = tomllib.loads((package_dir / _PYPROJECT_NAME).read_text(encoding="utf-8"))
    return group in data.get("project", {}).get("entry-points", {})


def self_test() -> bool:
    """Non-vacuity self-test, run as step 1 of every invocation."""
    ok = True
    tmp_root = Path(tempfile.mkdtemp(prefix="manifest-import-parity-selftest-"))
    try:
        ok &= _self_test_synthetic_tree(tmp_root)
        try:
            scan_workspace(tmp_root / "nowhere-empty")
            refused = False
        except FileNotFoundError:
            refused = True
        except SystemExit as exc:
            refused = exc.code == EXIT_USAGE
        ok &= _assert(refused, "a workspace with fewer than two packages is refused, never a silent pass")
        ok &= _self_test_live_edge()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _log_report(report: dict[str, list[ParityViolation]]) -> int:
    total = 0
    for distribution in sorted(report):
        violations = report[distribution]
        total += len(violations)
        for violation in violations:
            logger.error("%s [%s]: %s", distribution, violation.kind, violation.detail)
        logger.info("package=%s violations=%d", distribution, len(violations))
    logger.info(
        "MANIFEST/IMPORT PARITY REPORT: %d package(s) scanned, %d violation(s).",
        len(report),
        total,
    )
    return total


def main(argv: list[str] | None = None) -> int:
    """Entry point: self-test, then (unless --self-test) the real comparison."""
    parser = argparse.ArgumentParser(
        description=(
            "Manifest/import parity: every datrix-* package's declared Datrix "
            "dependency set must equal the Datrix packages its src/ imports, and "
            "no runtime requirement may carry a test-only extra. Hard zero."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real scan is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")
    if args.self_test:
        return EXIT_OK

    try:
        report = scan_workspace(WORKSPACE_ROOT)
    except (ValueError, SyntaxError) as exc:
        logger.error("Manifest/import scan failed: %s", exc)
        return EXIT_USAGE
    total = _log_report(report)
    return EXIT_FAIL if total else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
