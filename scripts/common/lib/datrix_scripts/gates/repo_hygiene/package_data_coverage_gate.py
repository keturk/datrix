"""Package-data coverage gate: every runtime resource a package loads ships in its wheel.

A generator package loads its Jinja2 templates (``*.j2``) and its DAL generator
definitions (``*.dal``) from its installed package directory at run time.
Neither is Python, so a built wheel carries them only when a
``[tool.setuptools.package-data]`` glob of the package's ``pyproject.toml``
matches them. An editable install reads the source tree directly, so a
missing glob is invisible locally -- every test passes and every generation
works -- and the loss only appears after ``pip install`` of the built wheel,
as a package that cannot render a single file.

That is exactly how the python and typescript backends came to ship two of
their three hundred templates: their glob, ``**/templates/*.j2``, matches only
files DIRECTLY inside a ``templates/`` directory, while nearly every template
sits one level deeper (``templates/messaging/...``).

SETUPTOOLS IS THE ORACLE FOR MATCHING: setuptools expands each package-data
pattern with ``glob.glob(<package dir>/<pattern>, recursive=True)``; this gate
expands them the same way (a dotted key names a sub-package directory), never
with ``fnmatch``, whose ``*`` crosses directory separators and so reports a
confident "shipped" for a file setuptools leaves out.

Every ``datrix-*`` package in the workspace with a package-data table is
scanned. A built-in non-vacuity self-test runs first: a planted package whose
glob misses one nested template must be reported, and a recursive glob over
the same tree must report nothing.

This module is what ``gates/repo-hygiene/package-data-coverage-gate.ps1`` (and its ``.sh`` twin)
runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] package-data-coverage PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = every resource ships (or ``--self-test`` passed), 1 = a resource no glob ships or a
failed self-test, 2 = a ``--package`` that names no workspace package.
"""

from __future__ import annotations

import argparse
import glob
import logging
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "package-data-coverage"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.package_data_coverage_gate"
WRAPPER: Final = "package-data-coverage-gate"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

#: The suffixes of the non-Python resources a generator package loads at run time.
RUNTIME_RESOURCE_SUFFIXES: tuple[str, ...] = (".j2", ".dal")
_PACKAGE_GLOB = "datrix-*"
_SOURCE_DIR = "src"


@dataclass(frozen=True)
class Uncovered:
    """One runtime resource no package-data glob ships."""

    package: str
    resource: Path


def shipped_files(source_dir: Path, package_data: Mapping[str, Sequence[str]]) -> set[Path]:
    """Every file the package-data table ships, expanded as setuptools expands it.

    Args:
        source_dir: The ``src/`` directory holding the top-level packages.
        package_data: The ``[tool.setuptools.package-data]`` table: a dotted
            package name mapped to its glob patterns.

    Returns:
        The resolved paths of every matched file.
    """
    shipped: set[Path] = set()
    for package, patterns in package_data.items():
        package_dir = source_dir.joinpath(*package.split("."))
        for pattern in patterns:
            shipped.update(
                Path(match).resolve()
                for match in glob.glob(str(package_dir / pattern), recursive=True)
                if Path(match).is_file()
            )
    return shipped


def uncovered_resources(
    source_dir: Path, package_data: Mapping[str, Sequence[str]], label: str
) -> list[Uncovered]:
    """Every runtime resource under the table's top-level packages that no glob ships."""
    shipped = shipped_files(source_dir, package_data)
    top_packages = {package.split(".")[0] for package in package_data}
    uncovered: list[Uncovered] = []
    for top_package in sorted(top_packages):
        package_dir = source_dir / top_package
        for suffix in RUNTIME_RESOURCE_SUFFIXES:
            uncovered.extend(
                Uncovered(package=label, resource=resource)
                for resource in sorted(package_dir.rglob(f"*{suffix}"))
                if resource.resolve() not in shipped
            )
    return uncovered


def _scan_package(repo_dir: Path) -> list[Uncovered]:
    pyproject = repo_dir / "pyproject.toml"
    if not pyproject.is_file():
        return []
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    package_data = data.get("tool", {}).get("setuptools", {}).get("package-data")
    if not package_data:
        return []
    return uncovered_resources(repo_dir / _SOURCE_DIR, package_data, repo_dir.name)


def run_self_test() -> bool:
    """Non-vacuity: a missed nested template is reported; a recursive glob reports nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        source_dir = Path(tmp) / _SOURCE_DIR
        nested = source_dir / "pkg" / "templates" / "messaging"
        nested.mkdir(parents=True)
        (nested / "consumer.py.j2").write_text("{{ x }}", encoding="utf-8")
        (source_dir / "pkg" / "templates" / "top.py.j2").write_text("{{ y }}", encoding="utf-8")
        missed = uncovered_resources(source_dir, {"pkg": ["**/templates/*.j2"]}, "self-test")
        if [item.resource.name for item in missed] != ["consumer.py.j2"]:
            logger.error("self_test_failed detector_missed_nested_template found=%s", missed)
            return False
        clean = uncovered_resources(source_dir, {"pkg": ["templates/**/*.j2"]}, "self-test")
        if clean:
            logger.error("self_test_failed recursive_glob_reported found=%s", clean)
            return False
    return True


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/package-data-coverage-gate.ps1``: one per wrapper parameter,
    spelled exactly."""
    parser = argparse.ArgumentParser(prog=WRAPPER, description=__doc__.split("\n", 1)[0], allow_abbrev=False)
    parser.add_argument("--package", action="append", default=[], help="Limit to these repos.")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the self-test and the wrapper seam check."
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging.")
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, then check every selected package's wheel coverage (exit codes in the module
    docstring)."""
    if not run_self_test():
        print("FAIL: package-data coverage self-test failed; the scan cannot be trusted.")
        return EXIT_FAIL
    if args.self_test:
        print("OK: package-data coverage self-test passed.")
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )

    repos = sorted(path for path in WORKSPACE_DIR.glob(_PACKAGE_GLOB) if path.is_dir())
    if args.package:
        unknown = sorted(set(args.package) - {repo.name for repo in repos})
        if unknown:
            print(f"Unknown package(s) {unknown}; workspace packages: {[r.name for r in repos]}")
            return EXIT_USAGE
        repos = [repo for repo in repos if repo.name in args.package]

    uncovered = [item for repo in repos for item in _scan_package(repo)]
    if uncovered:
        for item in uncovered:
            print(f"{item.package}: {item.resource} is shipped by no package-data glob")
        print(
            f"FAIL: {len(uncovered)} runtime resource(s) would be missing from the built wheels. "
            "Fix: add a recursive glob (e.g. 'templates/**/*.j2') to the package's "
            "[tool.setuptools.package-data] table."
        )
        return EXIT_FAIL
    print(f"OK: every runtime resource of {len(repos)} package(s) ships in its wheel.")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
