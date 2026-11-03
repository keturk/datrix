"""Which of a package's fixture files its tests still read: what ``repoint -Prune`` keeps.

A package's fixture files are the files of the fixture budget gate's kinds under its ``tests/``
(``fixture_budget_gate.fixture_files``). One is kept when anything reads it, found statically and never by
running a test:

``named``
    needs discovery (``needs.package_inputs``) resolves an input of a module under ``tests/`` to it. A name
    two or more files answer equally near keeps every file ending with it; a conftest pair fixture whose file
    name is computed keeps every fixture of the package, since any could be the one.
``tree``
    it lies under a directory a module reads whole. A path expression is evaluated statically:
    ``Path(__file__)`` and ``__file__`` with ``.parent``, ``.parents[n]``, ``.resolve()`` and ``.absolute()``,
    ``/`` joins, ``Path(...)`` and ``os.path.join`` of string constants and of path constants (bound in the
    module, or imported from a module of the package or of an installed ``datrix_*`` package); a base it
    cannot evaluate stands for every directory whose path ends with the parts joined to it. An expression
    naming a directory under ``tests/`` reads it whole unless it is joined with a constant (the join is
    judged instead) or bound to a name (each use of the name is judged instead): a walk, a call argument, a
    join with a computed or wildcard part, a return, an f-string all read it whole. An expression handed to a
    tree reader's entry (``package_contracts``, ``SemanticBaselineCorpus``, ``CaseSuite``), or written inside a
    tree reader of ``TREE_READERS``, is that reader's: the prune applies the reader's own rule to it.
``harness``
    it lies under ``tests/fixtures/diagnostics/`` (``DIAGNOSTIC_FIXTURES``): the case runner reads that tree
    off the diagnostic catalog, and ``fixture-author.ps1 diagnostics`` authors it.
``reached``
    a kept file reaches it: a ``.dtrx``'s project as parsed (``datrix_testing.corpus.project_reached_files``),
    a ``.dcfg``'s imports (resolved in its own directory and each one above it up to ``tests/``). A kept
    ``.dtrx`` or ``.dcfg`` that does not parse keeps every fixture under its directory: what it reaches is
    unknown.
"""

from __future__ import annotations

import ast
import importlib
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePath, PurePosixPath
from typing import Final

from datrix_common.errors.base import DatrixError
from datrix_common.source_syntax import SourceParseError
from datrix_testing.cases.annotations import DIAGNOSTIC_FIXTURES
from datrix_testing.cases.runner import CaseSuite
from datrix_testing.config_documents import disk_config_documents
from datrix_testing.corpus import project_reached_files
from datrix_testing.model_contracts.runner import package_contracts
from datrix_testing.parsing import register_installed_parsers
from datrix_testing.semantic_baseline import SemanticBaselineCorpus

from datrix_scripts.dev.fixture_author.needs import TREE_READERS, ModuleInput, Unresolved, package_inputs
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    DCFG_KIND,
    PYTHON_SUFFIX,
    SKIPPED_DIRS,
    fixture_files,
    fixture_kind,
    parse_module,
    walk_files,
)

logger = logging.getLogger(__name__)

#: The calls through which a test hands its whole ``tests/`` to a reader with a rule of its own: the model contract
#: capture (a model keeps a sample), the semantic baseline (its manifest drifts legally only), and the case suite
#: (it reads the diagnostics tree, the harness rule, and the projects its case inputs name, the named rule).
TREE_READER_ENTRIES: Final[frozenset[str]] = frozenset(
    {package_contracts.__name__, SemanticBaselineCorpus.__name__, CaseSuite.__name__}
)
#: The fixture kind a kept file's project is parsed for.
PROJECT_KIND: Final = ".dtrx"
#: The attributes of a path that name another path, evaluated as steps of the expression.
_PATH_STEPS: Final[frozenset[str]] = frozenset({"parent", "parents", "resolve", "absolute"})
#: The calls building a path from their arguments: the expression is the call.
_PATH_BUILDERS: Final[frozenset[str]] = frozenset({"Path", "PurePath", "PosixPath", "WindowsPath", "join", "str",
                                                   "fspath"})
_MODULE_FILE: Final = "__file__"
_INSTALLED_PREFIX: Final = "datrix_"
_WILDCARDS: Final = frozenset("*?[")
_PARENT_PART: Final = ".."
_CURRENT_PART: Final = "."
_PACKAGE_INIT: Final = "__init__"
#: What a kept file that does not parse is read with: its reach is unknown.
_PARSE_ERRORS: Final = (DatrixError, SourceParseError, ValueError, OSError, UnicodeDecodeError)

_Binding = ast.Assign | ast.AnnAssign | ast.Import | ast.ImportFrom


class KeepReason(StrEnum):
    """Why a fixture file is kept."""

    NAMED = "named"
    TREE = "tree"
    HARNESS = "harness"
    REACHED = "reached"


@dataclass(frozen=True)
class Kept:
    """Why one fixture file is kept, and where: the module and line, or the file reaching it."""

    reason: KeepReason
    where: str


@dataclass(frozen=True)
class KeptFiles:
    """Every fixture file of one package, the ones kept with why, and the modules handing its ``tests/`` to the
    model contract capture (``package_contracts``)."""

    files: tuple[Path, ...]
    kept: Mapping[Path, Kept]
    contract_readers: tuple[Path, ...]

    def unread(self) -> tuple[Path, ...]:
        """files − kept: the fixture files nothing reads."""
        return tuple(path for path in self.files if path not in self.kept)


# --------------------------------------------------------------------------- path values


@dataclass(frozen=True)
class PathValue:
    """A path known statically: *base* (absolute) with *parts* joined, or, with no base, every path ending with
    *parts*."""

    base: Path | None
    parts: tuple[str, ...]

    def joined(self, parts: Sequence[str]) -> PathValue | None:
        if self.base is not None:
            return PathValue(Path(os.path.normpath(Path(self.base, *self.parts, *parts))), ())
        if _PARENT_PART in parts:
            return None
        return PathValue(None, (*self.parts, *parts))

    def up(self, levels: int) -> PathValue | None:
        if self.base is not None:
            path = Path(self.base, *self.parts)
            return PathValue(path.parents[levels], ()) if levels < len(path.parents) else None
        kept = len(self.parts) - levels - 1
        return PathValue(None, self.parts[:kept]) if kept > 0 else None


#: A call's result the evaluation cannot follow: some path, known only by the parts joined to it.
UNKNOWN_BASE: Final = PathValue(None, ())


def text_parts(text: str) -> tuple[str, ...] | None:
    """The path parts of a constant *text*, ``None`` when it holds a wildcard (a walk, not a name)."""
    if _WILDCARDS & set(text):
        return None
    return tuple(part for part in PurePosixPath(text.replace("\\", "/")).parts if part != _CURRENT_PART)


def _constant_value(value: object) -> tuple[PathValue, ...]:
    """The path a constant of an installed module stands for: a relative path or text is a suffix."""
    if isinstance(value, str):
        parts = text_parts(value)
        return () if not parts else (PathValue(None, parts),)
    if isinstance(value, PurePath):
        if value.is_absolute():
            return (PathValue(Path(value), ()),)
        return (PathValue(None, value.parts),) if value.parts else ()
    return ()


def _call_name(function: ast.expr) -> str | None:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _dotted_tail(module: Path, package_dir: Path) -> tuple[str, ...]:
    relative = module.relative_to(package_dir).with_suffix("").parts
    return relative[:-1] if relative[-1] == _PACKAGE_INIT else relative


# --------------------------------------------------------------------------- module scopes


class _Resolver:
    """The path constants of every module of one package, evaluated once, and of installed ``datrix_*``
    modules."""

    def __init__(self, package_dir: Path) -> None:
        self.package_dir = package_dir
        self.modules = [path for path in walk_files(package_dir / PackageMarker.TESTS.value)
                        if path.suffix == PYTHON_SUFFIX]
        self.scopes: dict[Path, _Scope | None] = {}

    def scope(self, module: Path) -> _Scope:
        if module not in self.scopes:
            self.scopes[module] = None
            self.scopes[module] = _Scope(module, parse_module(module), self)
        found = self.scopes[module]
        return found if found is not None else _Scope.empty(module, self)

    def local_module(self, dotted: str, level: int, importer: Path) -> list[Path]:
        """The package modules an import names: relative to *importer*, or by the tail of its dotted path."""
        parts = tuple(dotted.split(".")) if dotted else ()
        if level:
            base = importer.parents[level - 1].joinpath(*parts)
            return [path for path in (base.with_suffix(PYTHON_SUFFIX), base / f"{_PACKAGE_INIT}{PYTHON_SUFFIX}")
                    if path.is_file()]
        if not parts:
            return []
        return [module for module in self.modules if _dotted_tail(module, self.package_dir)[-len(parts):] == parts]

    def imported(self, dotted: str, level: int, name: str, importer: Path) -> tuple[PathValue, ...]:
        """What *name* imported from module *dotted* stands for as a path, if anything."""
        local = self.local_module(dotted, level, importer)
        if local:
            return tuple(value for module in local for value in self.scope(module).values(name))
        if level or not dotted.startswith(_INSTALLED_PREFIX):
            return ()
        try:
            module = importlib.import_module(dotted)
        except ImportError:
            return ()
        return _constant_value(vars(module)[name]) if name in vars(module) else ()


@dataclass
class _Scope:
    """One module: the path values of the names it binds, in line order, and the modules it imports by alias."""

    module: Path
    tree: ast.Module
    resolver: _Resolver
    env: dict[str, tuple[PathValue, ...]] = field(default_factory=dict)
    module_aliases: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        bindings = sorted((node for node in ast.walk(self.tree) if isinstance(node, _Binding)),
                          key=lambda node: (node.lineno, node.col_offset))
        for node in bindings:
            self._bind(node)

    @classmethod
    def empty(cls, module: Path, resolver: _Resolver) -> _Scope:
        return cls(module, ast.Module(body=[], type_ignores=[]), resolver)

    def values(self, name: str) -> tuple[PathValue, ...]:
        return self.env[name] if name in self.env else ()

    def _set(self, name: str, found: tuple[PathValue, ...]) -> None:
        if found:
            self.env[name] = found

    def _bind(self, node: _Binding) -> None:
        if isinstance(node, ast.Import):
            self.module_aliases.update({alias.asname or alias.name: alias.name for alias in node.names})
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                self._set(alias.asname or alias.name,
                          self.resolver.imported(node.module or "", node.level, alias.name, self.module))
        else:
            target = _single_name(node)
            if target is not None and node.value is not None:
                self._set(target, self._bound_value(node.value))

    def _bound_value(self, value: ast.expr) -> tuple[PathValue, ...]:
        """What a name bound to *value* stands for: a path, or a string constant joined as path parts."""
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return _constant_value(value.value)
        return self.evaluate(value)

    def evaluate(self, node: ast.expr) -> tuple[PathValue, ...]:
        """Every path *node* stands for statically; empty when it stands for none known."""
        if isinstance(node, ast.Name):
            return (PathValue(self.module, ()),) if node.id == _MODULE_FILE else self.values(node.id)
        if isinstance(node, ast.Attribute):
            return self._attribute(node)
        if isinstance(node, ast.Subscript):
            return self._parents(node)
        if isinstance(node, ast.Call):
            return self._call(node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self._joined(self.evaluate(node.left), [node.right])
        return ()

    def part_texts(self, node: ast.expr) -> tuple[str, ...] | None:
        """The parts a joined operand adds: a string constant or a relative path constant; ``None`` when it is
        computed or a wildcard."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return text_parts(node.value)
        relative = [value.parts for value in self.evaluate(node) if value.base is None and value.parts]
        return relative[0] if len(relative) == 1 else None

    def _joined(self, bases: Sequence[PathValue], operands: Sequence[ast.expr]) -> tuple[PathValue, ...]:
        added: list[str] = []
        for operand in operands:
            parts = self.part_texts(operand)
            if parts is None:
                return ()
            added.extend(parts)
        return tuple(joined for base in bases if (joined := base.joined(added)) is not None)

    def _attribute(self, node: ast.Attribute) -> tuple[PathValue, ...]:
        if node.attr == "parent":
            return tuple(up for value in self.evaluate(node.value) if (up := value.up(0)) is not None)
        if isinstance(node.value, ast.Name) and node.value.id in self.module_aliases:
            return self.resolver.imported(self.module_aliases[node.value.id], 0, node.attr, self.module)
        return ()

    def _parents(self, node: ast.Subscript) -> tuple[PathValue, ...]:
        value, index = node.value, node.slice
        if not (isinstance(value, ast.Attribute) and value.attr == "parents"
                and isinstance(index, ast.Constant) and isinstance(index.value, int)):
            return ()
        return tuple(up for each in self.evaluate(value.value) if (up := each.up(index.value)) is not None)

    def _call(self, node: ast.Call) -> tuple[PathValue, ...]:
        name = _call_name(node.func)
        if isinstance(node.func, ast.Attribute) and name in _PATH_STEPS and not node.args:
            return self.evaluate(node.func.value)
        if name not in _PATH_BUILDERS:
            return (UNKNOWN_BASE,)
        if not node.args or node.keywords:
            return ()
        first, rest = node.args[0], node.args[1:]
        if isinstance(first, ast.Constant):
            return self._joined((UNKNOWN_BASE,), node.args)
        return self._joined(self.evaluate(first), rest)


def _single_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    """The one name *node* binds, ``None`` when it binds a tuple, an attribute or several names."""
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return targets[0].id if len(targets) == 1 and isinstance(targets[0], ast.Name) else None


# --------------------------------------------------------------------------- whole-tree reads


def _parents_of(tree: ast.Module) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _continues(scope: _Scope, node: ast.expr, parent: ast.AST) -> bool:
    """Whether *parent* carries *node* on as a longer path expression (judged in its place) or binds it to a
    name (whose uses are judged)."""
    if isinstance(parent, ast.Assign | ast.AnnAssign):
        return parent.value is node and _single_name(parent) is not None
    if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
        return parent.left is node and scope.part_texts(parent.right) is not None
    if isinstance(parent, ast.Attribute):
        return parent.attr in _PATH_STEPS
    if isinstance(parent, ast.Call) and _call_name(parent.func) not in _PATH_BUILDERS:
        return False
    if isinstance(parent, ast.Subscript | ast.Call):
        return any(value != UNKNOWN_BASE for value in scope.evaluate(parent))
    return False


def _handed_to_tree_reader(node: ast.expr, parent: ast.AST, parents: Mapping[int, ast.AST]) -> bool:
    call = parents[id(parent)] if isinstance(parent, ast.keyword) and id(parent) in parents else parent
    return isinstance(call, ast.Call) and call.func is not node and _call_name(call.func) in TREE_READER_ENTRIES


def _reader_spans(module: Path, workspace: Path, tree: ast.Module) -> list[tuple[int, int]]:
    """The line spans of the tree readers of ``TREE_READERS`` *module* defines."""
    symbols = {reader.symbol for reader in TREE_READERS if workspace / reader.module == module}
    return [(node.lineno, node.end_lineno or node.lineno) for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in symbols]


@dataclass(frozen=True)
class TreeRead:
    """A directory a module reads whole, at a line."""

    module: Path
    line: int
    directory: Path


class _DirectoryIndex:
    """Every directory under one package's ``tests/``, to match a path value against."""

    def __init__(self, tests_dir: Path) -> None:
        self.tests_dir = tests_dir.resolve()
        self.directories = [self.tests_dir]
        for current, names, _ in os.walk(self.tests_dir):
            names[:] = sorted(name for name in names if name not in SKIPPED_DIRS)
            self.directories.extend(Path(current, name) for name in names)

    def named(self, value: PathValue) -> list[Path]:
        if value.base is not None:
            path = Path(value.base, *value.parts).resolve()
            return [path] if path.is_dir() and path.is_relative_to(self.tests_dir) else []
        size = len(value.parts)
        if not size:
            return []
        return [directory for directory in self.directories if directory.parts[-size:] == value.parts]


def _is_path_node(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Load)
    return isinstance(node, ast.Attribute | ast.Subscript | ast.Call | ast.BinOp)


def tree_reads(scope: _Scope, index: _DirectoryIndex, workspace: Path) -> Iterator[TreeRead]:
    """Every directory under ``tests/`` the module of *scope* reads whole, with the line reading it."""
    parents = _parents_of(scope.tree)
    spans = _reader_spans(scope.module, workspace, scope.tree)
    for node in ast.walk(scope.tree):
        if not _is_path_node(node) or id(node) not in parents:
            continue
        directories = [directory for value in scope.evaluate(node) for directory in index.named(value)]
        parent = parents[id(node)]
        if not directories or _continues(scope, node, parent) or _handed_to_tree_reader(node, parent, parents):
            continue
        if not any(start <= node.lineno <= end for start, end in spans):
            yield from (TreeRead(scope.module, node.lineno, directory) for directory in directories)


# --------------------------------------------------------------------------- the kept set


@dataclass
class _Keeping:
    files: set[Path]
    tests_dir: Path
    workspace: Path
    kept: dict[Path, Kept] = field(default_factory=dict)

    def keep(self, path: Path, reason: KeepReason, where: str) -> bool:
        if path not in self.files or path in self.kept:
            return False
        self.kept[path] = Kept(reason, where)
        return True

    def keep_under(self, directory: Path, reason: KeepReason, where: str) -> list[Path]:
        """Keep every fixture under *directory*; the ones newly kept."""
        return [path for path in sorted(self.files) if path.is_relative_to(directory) and self.keep(path, reason, where)]

    def label(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix() if path.is_relative_to(self.workspace) else str(path)


def _keep_input(keeping: _Keeping, each: ModuleInput, where: str) -> None:
    if each.path is not None:
        keeping.keep(each.path.resolve(), KeepReason.NAMED, where)
    elif each.unresolved is Unresolved.AMBIGUOUS:
        for path in sorted(keeping.files):
            if path.as_posix().endswith(f"/{each.name}"):
                keeping.keep(path, KeepReason.NAMED, where)
    elif each.unresolved is Unresolved.COMPUTED:
        keeping.keep_under(keeping.tests_dir, KeepReason.NAMED, f"{where} (a pair fixture's computed file)")


def _keep_named(keeping: _Keeping, package_dir: Path) -> None:
    for module in package_inputs(package_dir, keeping.workspace):
        for each in module.inputs:
            _keep_input(keeping, each, f"{keeping.label(module.module)}:{each.lines[0]}")


def _keep_trees(keeping: _Keeping, resolver: _Resolver) -> list[Path]:
    """Keep what the modules read whole; the modules handing ``tests/`` to the model contract capture."""
    index = _DirectoryIndex(keeping.tests_dir)
    contract_readers: list[Path] = []
    for module in resolver.modules:
        scope = resolver.scope(module)
        for read in tree_reads(scope, index, keeping.workspace):
            keeping.keep_under(read.directory, KeepReason.TREE, f"{keeping.label(read.module)}:{read.line}")
        if any(isinstance(node, ast.Call) and _call_name(node.func) == package_contracts.__name__
               for node in ast.walk(scope.tree)):
            contract_readers.append(module)
    return contract_readers


def _config_imports(path: Path, tests_dir: Path) -> Iterator[Path]:
    """Every file an import of the ``.dcfg`` at *path* can name: resolved in its directory and each above it."""
    document = disk_config_documents().config_document(path)
    roots = [path.parent, *(parent for parent in path.parent.parents if parent.is_relative_to(tests_dir))]
    for imported in document.imports:
        yield from ((root / imported.path).resolve() for root in roots)


def _reached_from(path: Path, tests_dir: Path) -> Iterator[Path]:
    if fixture_kind(path.name) == PROJECT_KIND:
        yield from project_reached_files(path)
    elif fixture_kind(path.name) == DCFG_KIND:
        yield from _config_imports(path, tests_dir)


def _keep_reached(keeping: _Keeping) -> None:
    """Keep what every kept file reaches. A file a parsed project reaches is in that project's reach already;
    a kept file that does not parse keeps its directory, and each file so kept is read in turn."""
    pending = sorted(keeping.kept, reverse=True)
    while pending:
        root = pending.pop()
        where = keeping.label(root)
        try:
            reached = list(_reached_from(root, keeping.tests_dir))
        except _PARSE_ERRORS as error:
            logger.debug("prune reach unreadable file=%s error=%s", where, error)
            pending.extend(keeping.keep_under(root.parent, KeepReason.REACHED,
                                              f"{where} does not parse ({type(error).__name__})"))
            continue
        for path in reached:
            keeping.keep(path.resolve(), KeepReason.REACHED, where)


def kept_fixture_files(package_dir: Path, workspace: Path) -> KeptFiles:
    """The fixture files of the package at *package_dir* and which of them its tests read (module docstring).

    Raises:
        NeedsScanError: the shared fixture directory is missing or an input cannot be read.
        FixtureScanError: a module under ``tests/`` cannot be parsed.
    """
    register_installed_parsers()
    tests_dir = (package_dir / PackageMarker.TESTS.value).resolve()
    files = {each.path.resolve() for each in fixture_files(tests_dir, package_dir.name)}
    keeping = _Keeping(files, tests_dir, workspace)
    _keep_named(keeping, package_dir)
    contract_readers = _keep_trees(keeping, _Resolver(package_dir))
    harness = tests_dir / DIAGNOSTIC_FIXTURES
    keeping.keep_under(harness, KeepReason.HARNESS, keeping.label(harness))
    _keep_reached(keeping)
    logger.debug("prune kept package=%s files=%d kept=%d", package_dir.name, len(files), len(keeping.kept))
    return KeptFiles(tuple(sorted(files)), dict(keeping.kept), tuple(contract_readers))


__all__ = [
    "PROJECT_KIND",
    "TREE_READER_ENTRIES",
    "UNKNOWN_BASE",
    "KeepReason",
    "Kept",
    "KeptFiles",
    "PathValue",
    "TreeRead",
    "kept_fixture_files",
    "text_parts",
    "tree_reads",
]
