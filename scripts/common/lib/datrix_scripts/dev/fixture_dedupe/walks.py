"""The fixture directories a test reads whole: deleting a copy inside one changes what that read sees.

Two sources:

* a test-module site calling ``glob``, ``rglob``, ``iterdir`` or ``walk`` on a fixture-path name (the
  receiver's text, as written up to the ``.``, ends in ``FIXTURE_DIR``/``FIXTURES_DIR``, ``_FIXTURE``/
  ``_FIXTURES`` or ``fixtures_dir``, optionally followed by more name characters and a ``)``), or ``os.walk``
  of one. Its receiver is evaluated statically (``static_paths``); one that cannot be is refused;
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

from datrix_scripts.dev.fixture_dedupe.static_paths import StaticEvaluator, UnevaluableError, single_bindings
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import PYTHON_SUFFIX, parse_module, walk_files

WALK_METHODS: Final = frozenset({"glob", "rglob", "iterdir", "walk"})
_OS_WALK: Final = "walk"
_FIXTURE_ROOT_NAME: Final = re.compile(r"(FIXTURES?_DIR|_FIXTURES?|fixtures_dir)[A-Za-z_]*\)?$")
DIAGNOSTICS_COLLECTOR: Final = "the diagnostics collector (datrix_testing.cases.annotations) reads it whole"
LSP_COLLECTOR: Final = "the language-server inputs (datrix_testing.cases.annotation_migrate) live only here"


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
    """A directory read whole, and why: the site reading it or the collector."""

    path: Path
    reason: str


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


def _walk_receiver(call: ast.Call, lines: list[str]) -> ast.expr | None:
    """The receiver of *call* when it walks a fixture-path name, else ``None``."""
    function = call.func
    if isinstance(function, ast.Attribute) and function.attr in WALK_METHODS and function.end_lineno is not None:
        column = (function.end_col_offset or 0) - len(function.attr) - 1
        if _FIXTURE_ROOT_NAME.search(_text_before(lines, function.end_lineno, column)) is not None:
            return function.value
    is_os_walk = isinstance(function, ast.Attribute) and function.attr == _OS_WALK
    if is_os_walk and call.args and call.args[0].end_lineno is not None:
        argument = call.args[0]
        if _FIXTURE_ROOT_NAME.search(_text_before(lines, argument.end_lineno or 0, argument.end_col_offset or 0)):
            return argument
    return None


def _calls_with_locals(tree: ast.Module) -> Iterator[tuple[ast.Call, Mapping[str, ast.expr]]]:
    """Every call of *tree*, with the single bindings of the function enclosing it (none at module level)."""
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    enclosing: dict[int, Mapping[str, ast.expr]] = {}
    for function in functions:
        bindings = single_bindings(function.body)
        for node in ast.walk(function):
            enclosing[id(node)] = bindings
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
        receiver = _walk_receiver(call, lines)
        if receiver is None:
            continue
        site = WalkSite(module, call.lineno, ast.unparse(call))
        try:
            directory = evaluator.path(receiver, scope, local)
        except UnevaluableError as exc:
            refused.append(RefusedWalk(site, str(exc)))
            continue
        walked.append(WalkedDirectory(directory, f"{module.as_posix()}:{call.lineno} reads it whole"))
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
