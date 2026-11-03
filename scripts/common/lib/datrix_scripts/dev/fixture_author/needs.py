"""What the packages' tests read from their fixtures: the inputs behind ``fixture-author.ps1 needs``.

Discovery is static and executes nothing. Every ``tests/**/*.py`` module of every workspace package is
parsed once, and the inputs it reads are found with the literal walk of the fixture budget gate
(``datrix_scripts.gates.ratchet.fixture_budget_gate``), imported, never copied. A module reads an input
in one of four forms (``InputForm``):

``file``
    a string literal naming a fixture file (one of the gate's fixture kinds). A path joined with ``/``
    from string parts (``FIXTURES / "orders" / "system.dtrx"``) is read as the whole joined name.
``inline``
    a string literal holding ``.dtrx``/``.dcfg`` text, exactly the literals the gate counts.
``shared-name``
    a use of a ``FIXTURE_SYSTEM*`` constant of ``datrix_testing.fixture_names``, imported or by attribute.
``pair``
    a fixture a ``conftest.py`` on the module's path registers with ``FixturePairSpec``
    (``datrix_testing.conftest_plugin``), requested as a parameter or by its name in a string; the
    nearer conftest wins, as pytest resolves it.

A named file resolves to the fixture file under the package's ``tests/`` whose path ends with the name
and lies nearest the module (fewest directories up to a common ancestor, then fewest down), else to one
under the shared fixtures of ``datrix-testing``. A name matching no file (one the test writes itself), two
files equally near, or a name computed at run time is kept with the reason (``Unresolved``), never
dropped: whoever reads the module decides whether that input can be shared.

Three readers read whole trees instead of naming files (``TREE_READERS``); ``tree_reader_failures``
proves each still exists where the inventory says.
"""

from __future__ import annotations

import ast
import dataclasses
import logging
import os
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from datrix_testing import fixture_names
from datrix_testing.conftest_plugin import FixturePairSpec, pair_fixture_names

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    PYTHON_SUFFIX,
    SHARED_FIXTURES_RELATIVE,
    SHARED_PACKAGE,
    holds_fixture_text,
    is_fixture,
    parse_module,
    string_literals,
    walk_files,
)

logger = logging.getLogger(__name__)

#: The prefix of the ``datrix_testing.fixture_names`` constants that name a shared fixture file.
SHARED_NAME_PREFIX: Final = "FIXTURE_SYSTEM"
CONFTEST_FILE: Final = "conftest.py"
#: The ``FixturePairSpec`` fields that carry the fixture suffix and the file name, in declaration order.
_SPEC_NAME_FIELD, _SPEC_FILE_FIELD = (spec_field.name for spec_field in dataclasses.fields(FixturePairSpec)[:2])
_PATH_SEPARATOR: Final = "/"
_INLINE_NAME: Final = "line {line}"


class NeedsScanError(Exception):
    """A tree the inventory must read is missing, or a file it must read cannot be read (exit 2)."""


class InputForm(StrEnum):
    """How a test module reads one input."""

    FILE = "file"
    INLINE = "inline"
    SHARED_NAME = "shared-name"
    PAIR = "pair"


class Unresolved(StrEnum):
    """Why a named input resolves to no one file."""

    NOT_FOUND = "no fixture file under the package's tests/ or the shared fixtures ends with this name"
    AMBIGUOUS = "two or more fixture files ending with this name are equally near the module"
    COMPUTED = "the file name is computed at run time"


@dataclass(frozen=True)
class Resolution:
    """Where a named input resolves: *path*, or *unresolved* saying why there is none."""

    path: Path | None
    unresolved: Unresolved | None


@dataclass(frozen=True)
class ModuleInput:
    """One input a test module reads.

    *name* is the file name as written (``file``), the constant (``shared-name``), the fixture
    (``pair``) or ``line <n>`` (``inline``); *lines* are where the module reads it. *path* is the file
    read, ``None`` for an inline literal or an unresolved name (*unresolved* says why); *text* is the
    text the input carries, empty when it resolves to no file.
    """

    form: InputForm
    name: str
    lines: tuple[int, ...]
    path: Path | None
    unresolved: Unresolved | None
    text: str


@dataclass(frozen=True)
class ModuleInputs:
    """The inputs one test module reads; only a module reading at least one is listed."""

    package: str
    module: Path
    inputs: tuple[ModuleInput, ...]


@dataclass(frozen=True)
class TreeReader:
    """A reader that reads every fixture file under a root instead of naming files.

    *module* is workspace-relative; *symbol* is the top-level function that enumerates the files.
    """

    module: str
    symbol: str
    reads: str


TREE_READERS: Final[tuple[TreeReader, ...]] = (
    TreeReader(
        "datrix-language/tests/integration/formatting/test_format_corpus.py",
        "_corpus",
        "every .dtrx under the showcase examples, under the shared fixture corpus (CORPUS_ROOT) and under "
        "tests/ of the packages the test lists",
    ),
    TreeReader(
        "datrix-testing/src/datrix_testing/semantic_baseline.py",
        "enumerate_fixture_corpus",
        "every .dtrx under a package's tests/, the diagnostics and project trees excluded, and every entry of "
        "the shared fixture corpus (CORPUS_ROOT)",
    ),
    TreeReader(
        "datrix-testing/src/datrix_testing/model_contracts/capture.py",
        "collect_samples",
        "every committed .dcfg under a package's tests/, then every .dcfg under the shared fixture corpus "
        "(CORPUS_ROOT)",
    ),
)


def tree_reader_failures(workspace: Path, readers: Sequence[TreeReader] = TREE_READERS) -> list[str]:
    """One message per tree reader of *readers* whose module is missing or no longer defines its function."""
    failures: list[str] = []
    for reader in readers:
        path = workspace / reader.module
        if not path.is_file():
            failures.append(
                f"tree reader {reader.module} does not exist. Fix: point TREE_READERS at the module that now "
                f"reads {reader.reads}."
            )
            continue
        defined = {node.name for node in parse_module(path).body if isinstance(node, ast.FunctionDef)}
        if reader.symbol not in defined:
            failures.append(
                f"tree reader {reader.module} defines no top-level function {reader.symbol!r} (it defines "
                f"{sorted(defined)}). Fix: name the function that now reads {reader.reads}."
            )
    return failures


def shared_fixture_names() -> dict[str, str]:
    """Each ``FIXTURE_SYSTEM*`` constant of ``datrix_testing.fixture_names`` with the file name it holds."""
    return {
        name: value
        for name, value in sorted(vars(fixture_names).items())
        if name.startswith(SHARED_NAME_PREFIX) and isinstance(value, str)
    }


@dataclass(frozen=True)
class _RegisteredPair:
    """A ``FixturePairSpec`` a conftest declares: the conftest, the line and where its file resolves."""

    conftest: Path
    line: int
    resolution: Resolution


@dataclass
class _PackageScan:
    """One package's discovery: its fixture index, and every tree, text and conftest read once."""

    workspace: Path
    package_dir: Path
    shared_names: Mapping[str, str]
    local_index: dict[str, list[Path]]
    shared_index: dict[str, list[Path]]
    trees: dict[Path, ast.Module] = field(default_factory=dict)
    texts: dict[Path, str] = field(default_factory=dict)
    conftest_pairs: dict[Path, dict[str, _RegisteredPair]] = field(default_factory=dict)

    def tree(self, module: Path) -> ast.Module:
        if module not in self.trees:
            self.trees[module] = parse_module(module)
        return self.trees[module]

    def text(self, path: Path) -> str:
        if path not in self.texts:
            try:
                self.texts[path] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise NeedsScanError(
                    f"cannot read fixture {path}: {exc}. A test's input that cannot be read cannot be "
                    "inventoried. Fix: resolve the read error or the file's encoding (UTF-8)."
                ) from exc
        return self.texts[path]


def _fixture_index(root: Path) -> dict[str, list[Path]]:
    """The fixture files under *root*, by base name, in walk order."""
    found: dict[str, list[Path]] = defaultdict(list)
    for path in walk_files(root):
        if is_fixture(path.name):
            found[path.name].append(path)
    return found


def _nearness(anchor_dir: Path, candidate: Path) -> tuple[int, int]:
    common = Path(os.path.commonpath([anchor_dir, candidate.parent]))
    return len(anchor_dir.parts) - len(common.parts), len(candidate.parent.parts) - len(common.parts)


def _nearest(name: str, anchor: Path, index: Mapping[str, list[Path]]) -> Resolution:
    """The one file of *index* ending with *name* nearest *anchor*, or why there is none."""
    base_name = name.rsplit(_PATH_SEPARATOR, 1)[-1]
    if base_name not in index:
        return Resolution(None, Unresolved.NOT_FOUND)
    candidates = [path for path in index[base_name] if path.as_posix().endswith(_PATH_SEPARATOR + name)]
    if not candidates:
        return Resolution(None, Unresolved.NOT_FOUND)
    keyed = sorted((_nearness(anchor.parent, path), path.as_posix(), path) for path in candidates)
    nearest = [path for key, _, path in keyed if key == keyed[0][0]]
    if len(nearest) > 1:
        return Resolution(None, Unresolved.AMBIGUOUS)
    return Resolution(nearest[0], None)


def resolve_name(name: str, anchor: Path, scan: _PackageScan) -> Resolution:
    """Where the file *name*, written in *anchor*, resolves: the package's ``tests/`` first, then the shared
    fixtures."""
    local = _nearest(name, anchor, scan.local_index)
    if local.unresolved is not Unresolved.NOT_FOUND:
        return local
    return _nearest(name, anchor, scan.shared_index)


def _shared_aliases(tree: ast.Module, shared: Mapping[str, str]) -> dict[str, str]:
    """Each local name *tree* binds to a ``FIXTURE_SYSTEM*`` constant, with the constant's name."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == fixture_names.__name__:
            aliases.update({alias.asname or alias.name: alias.name for alias in node.names if alias.name in shared})
    return aliases


def _shared_name_uses(tree: ast.Module, shared: Mapping[str, str]) -> Iterator[tuple[str, int]]:
    """``(constant, line)`` of every use of a ``FIXTURE_SYSTEM*`` constant in *tree*."""
    aliases = _shared_aliases(tree, shared)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in aliases:
            yield aliases[node.id], node.lineno
        elif isinstance(node, ast.Attribute) and node.attr in shared:
            yield node.attr, node.lineno


def _joined_paths(tree: ast.Module) -> dict[tuple[int, str], str]:
    """For each string constant ending a ``/`` join of string parts, the joined name, keyed as the walk keys it."""
    joined: dict[tuple[int, str], str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)) or _text(node.right) is None:
            continue
        parts: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
            part = _text(current.right)
            if part is None:
                break
            parts.insert(0, part)
            current = current.left
        joined[(node.right.lineno, parts[-1])] = _PATH_SEPARATOR.join(parts)
    return joined


def _text(node: ast.expr | None) -> str | None:
    """The text of *node* when it is a string constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _spec_argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for argument in call.keywords:
        if argument.arg == keyword:
            return argument.value
    return call.args[position] if len(call.args) > position else None


def _constant_text(node: ast.expr | None, aliases: Mapping[str, str], shared: Mapping[str, str]) -> str | None:
    """The text *node* stands for statically: a string constant or a ``FIXTURE_SYSTEM*`` constant."""
    text = _text(node)
    if text is not None:
        return text
    if isinstance(node, ast.Name) and node.id in aliases:
        return shared[aliases[node.id]]
    if isinstance(node, ast.Attribute) and node.attr in shared:
        return shared[node.attr]
    return None


def _calls_spec(function: ast.expr) -> bool:
    if isinstance(function, ast.Name):
        return function.id == FixturePairSpec.__name__
    return isinstance(function, ast.Attribute) and function.attr == FixturePairSpec.__name__


def _pairs_declared(conftest: Path, scan: _PackageScan) -> dict[str, _RegisteredPair]:
    """Every fixture name the ``FixturePairSpec`` calls of *conftest* register, with its file's resolution.

    A spec whose suffix is computed registers no name a module could be matched to, so it is not listed.
    """
    if conftest in scan.conftest_pairs:
        return scan.conftest_pairs[conftest]
    tree = scan.tree(conftest)
    aliases = _shared_aliases(tree, scan.shared_names)
    pairs: dict[str, _RegisteredPair] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _calls_spec(node.func)):
            continue
        suffix = _constant_text(_spec_argument(node, 0, _SPEC_NAME_FIELD), aliases, scan.shared_names)
        if suffix is None:
            continue
        file_name = _constant_text(_spec_argument(node, 1, _SPEC_FILE_FIELD), aliases, scan.shared_names)
        resolution = (
            Resolution(None, Unresolved.COMPUTED) if file_name is None else resolve_name(file_name, conftest, scan)
        )
        for fixture in pair_fixture_names(suffix):
            pairs[fixture] = _RegisteredPair(conftest, node.lineno, resolution)
    scan.conftest_pairs[conftest] = pairs
    return pairs


def _pairs_in_reach(module: Path, scan: _PackageScan) -> dict[str, _RegisteredPair]:
    """The pair fixtures the conftests from the package root down to *module*'s directory register; the
    nearer conftest wins."""
    reach: dict[str, _RegisteredPair] = {}
    relative = module.parent.relative_to(scan.package_dir).parts
    for depth in range(len(relative) + 1):
        conftest = scan.package_dir.joinpath(*relative[:depth], CONFTEST_FILE)
        if conftest.is_file():
            reach.update(_pairs_declared(conftest, scan))
    return reach


def _parameter_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
                yield argument.arg, argument.lineno


@dataclass
class _Collected:
    """The named inputs of one module as they are found: ``(form, name)`` -> lines and resolution."""

    lines: dict[tuple[InputForm, str], list[int]] = field(default_factory=lambda: defaultdict(list))
    resolutions: dict[tuple[InputForm, str], Resolution] = field(default_factory=dict)

    def add(self, form: InputForm, name: str, line: int, resolution: Resolution) -> None:
        self.lines[(form, name)].append(line)
        self.resolutions.setdefault((form, name), resolution)


def _named_inputs(module: Path, tree: ast.Module, literals: Sequence[tuple[int, str]], scan: _PackageScan) -> _Collected:
    collected = _Collected()
    joined = _joined_paths(tree)
    for line, text in literals:
        if is_fixture(text):
            name = joined[(line, text)] if (line, text) in joined else text
            collected.add(InputForm.FILE, name, line, resolve_name(name, module, scan))
    for constant, line in _shared_name_uses(tree, scan.shared_names):
        collected.add(InputForm.SHARED_NAME, constant, line, resolve_name(scan.shared_names[constant], module, scan))
    pairs = _pairs_in_reach(module, scan)
    requested = [*_parameter_names(tree), *((text, line) for line, text in literals)]
    for fixture, line in requested:
        if fixture in pairs:
            collected.add(InputForm.PAIR, fixture, line, pairs[fixture].resolution)
    return collected


def _module_input(form: InputForm, name: str, lines: Sequence[int], resolution: Resolution, scan: _PackageScan) -> ModuleInput:
    text = "" if resolution.path is None else scan.text(resolution.path)
    return ModuleInput(form, name, tuple(sorted(set(lines))), resolution.path, resolution.unresolved, text)


def module_inputs(module: Path, scan: _PackageScan) -> tuple[ModuleInput, ...]:
    """Every input *module* reads: its named inputs sorted by form and name, then its inline literals by line."""
    tree = scan.tree(module)
    literals = string_literals(tree)
    collected = _named_inputs(module, tree, literals, scan)
    named = [
        _module_input(form, name, collected.lines[(form, name)], resolution, scan)
        for (form, name), resolution in sorted(collected.resolutions.items())
    ]
    inline = [
        ModuleInput(InputForm.INLINE, _INLINE_NAME.format(line=line), (line,), None, None, text)
        for line, text in literals
        if holds_fixture_text(text)
    ]
    return (*named, *inline)


def _shared_root(workspace: Path) -> Path:
    root = workspace / SHARED_PACKAGE / SHARED_FIXTURES_RELATIVE
    if not root.is_dir():
        raise NeedsScanError(
            f"the shared fixture directory {root} does not exist. A test's file name resolves there when its "
            f"package holds no such file. Fix: run from a workspace holding {SHARED_PACKAGE}."
        )
    return root


def _package_scan(package_dir: Path, workspace: Path) -> _PackageScan:
    return _PackageScan(
        workspace=workspace,
        package_dir=package_dir,
        shared_names=shared_fixture_names(),
        local_index=_fixture_index(package_dir / PackageMarker.TESTS.value),
        shared_index=_fixture_index(_shared_root(workspace)),
    )


def current_inputs(module: Path, package_dir: Path, workspace: Path) -> tuple[ModuleInput, ...]:
    """Every input *module*, a test module of *package_dir*, reads as the tree stands now.

    Raises:
        NeedsScanError: the shared fixture directory is missing or an input cannot be read.
        FixtureScanError: *module* cannot be parsed.
    """
    return module_inputs(module, _package_scan(package_dir, workspace))


def package_inputs(package_dir: Path, workspace: Path) -> list[ModuleInputs]:
    """The modules under *package_dir*'s ``tests/`` that read at least one input, by path.

    Raises:
        NeedsScanError: the shared fixture directory is missing or an input cannot be read.
        FixtureScanError: a test module cannot be parsed (it would escape the inventory).
    """
    tests_dir = package_dir / PackageMarker.TESTS.value
    scan = _package_scan(package_dir, workspace)
    found: list[ModuleInputs] = []
    for module in walk_files(tests_dir):
        if module.suffix != PYTHON_SUFFIX:
            continue
        inputs = module_inputs(module, scan)
        if inputs:
            found.append(ModuleInputs(package_dir.name, module, inputs))
    logger.debug("needs discovery package=%s modules=%d reading=%d", package_dir.name, len(scan.trees), len(found))
    return sorted(found, key=lambda each: each.module.as_posix())


def needs_packages(workspace: Path) -> list[Path]:
    """The workspace packages holding a ``tests/`` tree, by name."""
    return workspace_package_dirs(workspace, any_of=frozenset({PackageMarker.TESTS}))


def workspace_inputs(workspace: Path, packages: Sequence[Path]) -> list[ModuleInputs]:
    """The modules of *packages* that read at least one input, by path."""
    found = [each for package_dir in packages for each in package_inputs(package_dir, workspace)]
    return sorted(found, key=lambda each: each.module.as_posix())


__all__ = [
    "CONFTEST_FILE",
    "SHARED_NAME_PREFIX",
    "TREE_READERS",
    "InputForm",
    "ModuleInput",
    "ModuleInputs",
    "NeedsScanError",
    "Resolution",
    "TreeReader",
    "Unresolved",
    "current_inputs",
    "module_inputs",
    "needs_packages",
    "package_inputs",
    "resolve_name",
    "shared_fixture_names",
    "tree_reader_failures",
    "workspace_inputs",
]
