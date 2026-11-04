"""The fixture directories a test reads whole: deleting a copy inside one changes what that read sees.

Two sources:

* a test-module site calling ``glob``, ``rglob``, ``iterdir`` or ``walk`` on a fixture-path name (the
  receiver's text, as written up to the ``.``, ends in ``FIXTURE_DIR``/``FIXTURES_DIR``, ``_FIXTURE``/
  ``_FIXTURES`` or ``fixtures_dir``, optionally followed by more name characters and a ``)``), or ``os.walk``
  of one, or a ``datrix_testing.tenant_fixtures`` helper given one (each globs the directory it is handed).
  Its receiver is evaluated statically (``static_paths``); one that cannot be is refused;
* a ``shutil.copytree`` of a directory of the package's ``tests/`` that the module names statically: a path in
  that copy leading out of the directory resolves to nothing;
* the case collectors: every package's diagnostics fixtures (``datrix_testing.cases.annotations``) and its
  language-server inputs (``datrix_testing.cases.annotation_migrate``), each read whole.

A walked directory covers its whole subtree.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_testing.cases.annotation_migrate import LSP_FIXTURE_PREFIX, LSP_FIXTURES
from datrix_testing.cases.annotations import DIAGNOSTIC_FIXTURES
from datrix_testing.tenant_fixtures import fixture_set_mismatch, negative_tenant_fixtures

from datrix_scripts.dev.fixture_dedupe.static_paths import (
    ModuleScope,
    StaticEvaluator,
    UnevaluableError,
    enclosing_bindings,
)
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import PYTHON_SUFFIX, parse_module, walk_files

WALK_METHODS: Final = frozenset({"glob", "rglob", "iterdir", "walk"})
_OS_WALK: Final = "walk"
_COPY_TREE: Final = "copytree"
_DIRECTORY_HELPERS: Final = frozenset({fixture_set_mismatch.__name__, negative_tenant_fixtures.__name__})
_FIXTURE_ROOT_NAME: Final = re.compile(r"(FIXTURES?_DIR|_FIXTURES?|fixtures_dir)[A-Za-z_]*\)?$")
DIAGNOSTICS_COLLECTOR: Final = "the diagnostics collector (datrix_testing.cases.annotations) reads it whole"
SITE_READ: Final = "reads it whole"
LSP_COLLECTOR: Final ="the language-server inputs (datrix_testing.cases.annotation_migrate) live only here"


@dataclass(frozen=True)
class WalkSite:
    """One test-module call reading a fixture directory whole.

    Attributes:
        module: The test module.
        line: The call's line.
        text: The call as written.
    """

    module: Path
    line: int
    text: str


@dataclass(frozen=True)
class WalkedDirectory:
    """A directory read whole, and why: the site reading it, or the collector's reason."""

    path: Path
    reason: str
    site: WalkSite | None = None

    def describe(self, base_dir: Path) -> str:
        """Why the directory is read whole, its paths relative to *base_dir*."""
        if self.site is None:
            return self.reason
        return f"{self.site.module.relative_to(base_dir).as_posix()}:{self.site.line} {self.reason}"


@dataclass(frozen=True)
class RefusedWalk:
    """A walk site whose directory cannot be evaluated statically, and why."""

    site: WalkSite
    reason: str


@dataclass(frozen=True)
class Walks:
    """Every directory read whole, and every walk site that could not be evaluated."""

    directories: tuple[WalkedDirectory, ...]
    refused: tuple[RefusedWalk, ...]

    def reader_of(self, path: Path) -> WalkedDirectory | None:
        """The walked directory holding *path*, if one does."""
        resolved = path.resolve()
        return next((walked for walked in self.directories if resolved.is_relative_to(walked.path.resolve())), None)


def _text_before(lines: list[str], line: int, column: int) -> str:
    return lines[line - 1][:column] if 0 < line <= len(lines) else ""


def _reads_first_argument_whole(function: ast.expr) -> bool:
    """Whether a call of *function* reads the directory its first argument names whole."""
    if isinstance(function, ast.Attribute):
        return function.attr == _OS_WALK or function.attr in _DIRECTORY_HELPERS
    return isinstance(function, ast.Name) and function.id in _DIRECTORY_HELPERS


def _is_copy(function: ast.expr) -> bool:
    """Whether a call of *function* copies the directory its first argument names to somewhere else."""
    return isinstance(function, ast.Attribute) and function.attr == _COPY_TREE


def _walk_receiver(call: ast.Call, lines: list[str]) -> ast.expr | None:
    """The receiver of *call* when it walks a fixture-path name, else ``None``."""
    function = call.func
    if isinstance(function, ast.Attribute) and function.attr in WALK_METHODS and function.end_lineno is not None:
        column = (function.end_col_offset or 0) - len(function.attr) - 1
        if _FIXTURE_ROOT_NAME.search(_text_before(lines, function.end_lineno, column)) is not None:
            return function.value
    if _reads_first_argument_whole(function) and call.args and call.args[0].end_lineno is not None:
        argument = call.args[0]
        if _FIXTURE_ROOT_NAME.search(_text_before(lines, argument.end_lineno or 0, argument.end_col_offset or 0)):
            return argument
    return None


def _copied_directory(
    evaluator: StaticEvaluator, call: ast.Call, scope: ModuleScope, local: Mapping[str, ast.expr], tests_root: Path
) -> Path | None:
    """The directory of *tests_root* that *call* copies whole, else ``None``: a copy of a path the module does
    not name statically (a parameter, a scratch directory) reads no fixture this plan can move."""
    if not _is_copy(call.func) or not call.args:
        return None
    try:
        directory = evaluator.path(call.args[0], scope, local)
    except UnevaluableError:
        return None
    return directory if directory.resolve().is_relative_to(tests_root.resolve()) else None


def _calls_with_locals(tree: ast.Module) -> Iterator[tuple[ast.Call, Mapping[str, ast.expr]]]:
    """Every call of *tree*, with the single bindings of the function enclosing it (none at module level)."""
    enclosing = enclosing_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, enclosing.get(id(node), {})


def module_walks(
    evaluator: StaticEvaluator, module: Path, tests_root: Path
) -> tuple[list[WalkedDirectory], list[RefusedWalk]]:
    """The directories the test module at *module* reads whole, and its sites that cannot be evaluated.

    Raises:
        FixtureScanError: The module cannot be read or parsed.
    """
    tree = parse_module(module)
    scope = evaluator.scope(module, tests_root, tree)
    lines = module.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
    walked: list[WalkedDirectory] = []
    refused: list[RefusedWalk] = []
    for call, local in _calls_with_locals(tree):
        copied = _copied_directory(evaluator, call, scope, local, tests_root)
        if copied is not None:
            walked.append(WalkedDirectory(copied, SITE_READ, WalkSite(module, call.lineno, ast.unparse(call))))
            continue
        receiver = _walk_receiver(call, lines)
        if receiver is None:
            continue
        site = WalkSite(module, call.lineno, ast.unparse(call))
        try:
            directory = evaluator.path(receiver, scope, local)
        except UnevaluableError as exc:
            refused.append(RefusedWalk(site, str(exc)))
            continue
        walked.append(WalkedDirectory(directory, SITE_READ, site))
    return walked, refused


def collector_directories(tests_root: Path) -> list[WalkedDirectory]:
    """The directories of *tests_root* the case collectors read whole."""
    found = [WalkedDirectory(tests_root / DIAGNOSTIC_FIXTURES, DIAGNOSTICS_COLLECTOR)]
    lsp_root = tests_root / LSP_FIXTURES
    if lsp_root.is_dir():
        found.extend(
            WalkedDirectory(child, LSP_COLLECTOR)
            for child in sorted(lsp_root.iterdir())
            if child.is_dir() and child.name.startswith(LSP_FIXTURE_PREFIX)
        )
    return found


def find_walks(packages: list[Path]) -> Walks:
    """Every directory the tests of *packages* read whole, and every walk site that cannot be evaluated."""
    evaluator = StaticEvaluator()
    directories: list[WalkedDirectory] = []
    refused: list[RefusedWalk] = []
    for package in packages:
        tests_root = package / PackageMarker.TESTS.value
        directories.extend(collector_directories(tests_root))
        for module in walk_files(tests_root):
            if module.suffix != PYTHON_SUFFIX:
                continue
            walked, unevaluated = module_walks(evaluator, module, tests_root)
            directories.extend(walked)
            refused.extend(unevaluated)
    return Walks(tuple(directories), tuple(refused))
