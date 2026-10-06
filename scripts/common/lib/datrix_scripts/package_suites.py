"""Which Datrix packages carry a test suite, and which runner executes it.

One home for a fact several tools need: *is this package testable, and by what?*
``test.ps1 -All``, ``status-tests.ps1``, ``test_project.py`` and the affected-set
machinery all have to agree on the answer, and they used to agree only by each
re-implementing "has a ``tests/`` directory" and hoping.

The predicate is **derived from what is on disk**, never from a package list. A
package joins the test system by carrying a suite, not by being named here:

===========  ==========================================================
Suite kind   Marker on disk
===========  ==========================================================
``PYTEST``   a ``tests/`` directory
``NODE``     a ``package.json`` declaring ``scripts.test``
===========  ==========================================================

Datrix is a multi-language toolchain and its own repo tooling has to be one too:
``datrix-vscode`` is a TypeScript package whose suite runs under Node, and a
future package may arrive with a third runner. Adding one is a row in
:data:`_SUITE_MARKERS` plus a runner module — never an edit to every consumer.

The ``datrix`` showcase repo is deliberately unmatched: it holds docs, examples
and scripts and hosts no test suite of any kind, so only ``datrix-*`` package
directories are considered even if a stray ``tests/`` appears at its root.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

#: Directory-name prefix every toolchain package shares. The showcase repo
#: ("datrix", no hyphen) is excluded by construction.
PACKAGE_PREFIX = "datrix-"

#: Names merged into datrix-common. A stale checkout can still have these
#: directories on disk; they are not part of the test system.
RETIRED_PACKAGE_NAMES = frozenset({"datrix-core", "datrix-codegen"})

#: Node manifest filename, and the script key whose presence means "this
#: package declares a test suite".
NODE_MANIFEST_NAME = "package.json"
NODE_TEST_SCRIPT_KEY = "test"

#: Key of the Datrix declaration block inside a Node manifest, holding what the
#: repo tooling needs to RUN the package's suite -- which files hold its tests,
#: which npm script builds them.
#:
#: Only facts that are safe to publish live here. A Node package may package
#: itself into a distributable artifact that includes its own manifest, so a
#: fact naming a framework package (which packages it is built against) is
#: declared in the monorepo instead -- see
#: ``datrix/scripts/config/cross-ecosystem-dependencies.json``.
NODE_DATRIX_BLOCK_KEY = "datrix"


class SuiteKind(Enum):
    """The runner that executes a package's test suite."""

    PYTEST = "pytest"
    NODE = "node"


@dataclass(frozen=True)
class PackageSuite:
    """A discovered package together with the runner its suite needs."""

    name: str
    path: Path
    kind: SuiteKind


def _has_pytest_suite(package_dir: Path) -> bool:
    """True when the package carries a ``tests/`` directory."""
    return (package_dir / "tests").is_dir()


def _has_node_suite(package_dir: Path) -> bool:
    """True when the package's ``package.json`` declares a ``test`` script.

    A manifest that cannot be read or parsed is reported and treated as *not*
    declaring a suite: silently guessing "testable" would put a package into
    ``test.ps1 -All`` that no runner can execute.
    """
    manifest_path = package_dir / NODE_MANIFEST_NAME
    if not manifest_path.is_file():
        return False
    manifest = read_json_object(manifest_path)
    if manifest is None:
        return False
    scripts = manifest.get("scripts")
    if not isinstance(scripts, dict):
        return False
    return isinstance(scripts.get(NODE_TEST_SCRIPT_KEY), str)


#: Ordered suite-kind detection table. Ordered because a package could in
#: principle carry both markers; the first match wins and the order is the
#: documented precedence rather than dict iteration luck.
_SUITE_MARKERS: tuple[tuple[SuiteKind, Callable[[Path], bool]], ...] = (
    (SuiteKind.PYTEST, _has_pytest_suite),
    (SuiteKind.NODE, _has_node_suite),
)


def read_json_object(path: Path) -> dict[str, object] | None:
    """Parse a JSON object file, or return ``None`` when it is unusable.

    Args:
        path: Path to the JSON file to read.

    Returns:
        The parsed object, or ``None`` if the file cannot be read, is not valid
        JSON, or does not parse to a JSON object.
    """
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        logger.warning("json_file_unreadable path=%s error=%s", path, exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("json_file_unparsable path=%s error=%s", path, exc)
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            "json_file_not_an_object path=%s type=%s", path, type(parsed).__name__
        )
        return None
    return parsed


def detect_suite_kind(package_dir: Path) -> SuiteKind | None:
    """Return the suite kind a package carries, or ``None`` when it carries none.

    Args:
        package_dir: Directory of a single package.

    Returns:
        The matching :class:`SuiteKind`, or ``None`` for a package with no
        recognizable test suite.
    """
    for kind, has_marker in _SUITE_MARKERS:
        if has_marker(package_dir):
            return kind
    return None


def discover_package_suites(workspace_root: Path) -> dict[str, PackageSuite]:
    """Discover every testable package under *workspace_root*.

    Args:
        workspace_root: Monorepo root holding the ``datrix-*`` package
            directories.

    Returns:
        Mapping of package name to :class:`PackageSuite`, in sorted name order.
        Empty when *workspace_root* does not exist, so a caller pointed at the
        wrong directory gets an empty report rather than a traceback.
    """
    if not workspace_root.is_dir():
        logger.warning("workspace_root_missing path=%s", workspace_root)
        return {}

    suites: dict[str, PackageSuite] = {}
    for child in sorted(workspace_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if not child.name.startswith(PACKAGE_PREFIX):
            continue
        if child.name in RETIRED_PACKAGE_NAMES:
            continue
        kind = detect_suite_kind(child)
        if kind is None:
            continue
        suites[child.name] = PackageSuite(name=child.name, path=child, kind=kind)
    return suites


def testable_package_names(workspace_root: Path) -> list[str]:
    """Sorted names of every package carrying a test suite.

    Args:
        workspace_root: Monorepo root holding the package directories.

    Returns:
        Sorted list of package directory names.
    """
    return sorted(discover_package_suites(workspace_root))
