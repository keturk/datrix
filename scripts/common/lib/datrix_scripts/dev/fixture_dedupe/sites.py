"""The test-module sites that read a copy a plan takes out of its tree, and the text each becomes.

Once the copies move, a test that read a moved or deleted copy reads its group's shared copy through the
one accessor, ``datrix_testing.corpus.shared_fixture("<path under shared/>")``:

* a path expression (``/`` joins, ``joinpath``/``with_*``, ``Path(...)``) the static evaluator
  (``static_paths``) evaluates to such a copy -- a root joined with string literals and constants,
  ``fixture_names`` ones included -- becomes ``shared_fixture("<package>/<path in the package>")``;
* a ``FixturePairSpec`` registered (``register_fixture_pairs``) or built (``build_spec_app``) with a
  fixtures directory the evaluator follows, whose file is such a copy, has its ``dtrx_filename`` operand
  replaced by that call: ``fixtures_dir / dtrx_filename`` yields an absolute path unchanged;
* a literal of a moving literal group becomes ``shared_fixture("inline/...").read_text(encoding="utf-8")``.

A module gaining a call imports the accessor after its last top-level import. The evaluator never
builds an installed class here: no constructor of a test module's expression runs.

A site is refused, listed and left for a hand edit when:

* a path expression evaluates to such a copy, but the site reads where the copy lies (``.parent``,
  ``.name``, ...) rather than its bytes: the shared copy lies elsewhere, possibly under another name;
* a path expression naming a leaving copy -- by a literal, or a constant holding one -- cannot be
  evaluated, or evaluates to something other than an absolute path;
* a pair spec naming a leaving copy is registered with no fixtures directory the evaluator follows;
* a literal or constant naming a leaving copy lies in no path expression at all (a helper's argument, a
  parametrize value, an assertion), unless it is the whole value of a name bound once: that name's uses
  are the sites;
* the module binds ``shared_fixture`` to something else.

A text names a copy when its last segment is the copy's base name and, unless it holds a ``..``, its
segments end the copy's path; a path expression's text is the trailing segments its text fixes (its last
literals and text constants, joined). A text is matched against the copies leaving the module's own package (a
test reads its own ``tests/`` tree); an evaluated path is matched against every leaving copy.
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields
from itertools import pairwise
from pathlib import Path, PurePath
from typing import Final

from datrix_testing.conftest_plugin import FixturePairSpec, build_spec_app, register_fixture_pairs
from datrix_testing.corpus import shared_fixture

from datrix_scripts.dev.fixture_dedupe.groups import LiteralSite
from datrix_scripts.dev.fixture_dedupe.layout import shared_root
from datrix_scripts.dev.fixture_dedupe.static_paths import (
    PATH_JOIN_METHODS,
    PATH_TYPES,
    ModuleScope,
    StaticEvaluator,
    UnevaluableError,
    callee_name,
    enclosing_bindings,
    single_bindings,
)
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError, literal_modules, parse_module

ACCESSOR: Final = shared_fixture.__name__
ACCESSOR_MODULE: Final = shared_fixture.__module__
ACCESSOR_IMPORT: Final = f"from {ACCESSOR_MODULE} import {ACCESSOR}"
PATH_SITE: Final = "path"
PAIR_SITE: Final = "pair"
LITERAL_SITE: Final = "literal"
_PAIR_SPEC: Final = FixturePairSpec.__name__
_PAIR_FIELDS: Final = tuple(field.name for field in fields(FixturePairSpec))
_PAIR_FILE: Final = "dtrx_filename"
_PAIR_FILE_INDEX: Final = _PAIR_FIELDS.index(_PAIR_FILE)
# Each pair-spec reader, with the positions of its fixtures directory and its spec (or specs) operand.
_PAIR_READERS: Final[Mapping[str, tuple[int, int]]] = {register_fixture_pairs.__name__: (0, 1), build_spec_app.__name__: (0, 1)}
_SHAPE_READS: Final = frozenset(
    {
        "parent", "parents", "name", "stem", "suffix", "suffixes", "parts", "anchor", "drive", "root",
        "with_name", "with_stem", "with_suffix", "relative_to", "is_relative_to", "joinpath", "match",
        "glob", "rglob", "iterdir", "walk",
    }
)
# How many names, lists and sums a reader's specs operand is followed through to its pair specs.
_MAX_SPEC_DEPTH: Final = 16
_SEPARATORS: Final = re.compile(r"[\\/]")
_HERE: Final = "."
_UP: Final = ".."
_TEXT_ENCODING: Final = "utf-8"
_NEWLINE: Final = b"\n"
_CRLF: Final = b"\r\n"


@dataclass(frozen=True)
class SiteRewrite:
    """One test-module expression rewritten to read a shared copy.

    Attributes:
        module: The module.
        line: The expression's first line.
        column: Its first column (UTF-8 bytes, as ``ast`` gives it).
        end_line: Its last line.
        end_column: The column just past it on that line.
        written: The expression as written.
        replacement: What it becomes.
        kind: ``path``, ``pair`` or ``literal``.
        read: The copy it read; ``None`` for a literal, which held its text.
        shared: The shared file it reads once rewritten.
    """

    module: Path
    line: int
    column: int
    end_line: int
    end_column: int
    written: str
    replacement: str
    kind: str
    read: Path | None
    shared: Path


@dataclass(frozen=True)
class RefusedSite:
    """A test-module site that reads, or names, a leaving copy and is not rewritten: it is edited by hand."""

    module: Path
    line: int
    written: str
    reason: str


@dataclass(frozen=True)
class ModuleEdit:
    """The rewrites of one module, and where the accessor import goes.

    Attributes:
        module: The module.
        rewrites: Its rewrites, in text order.
        import_after: The line after which the accessor import is inserted (0: before the first line);
            ``None`` when the module imports it already.
    """

    module: Path
    rewrites: tuple[SiteRewrite, ...]
    import_after: int | None


@dataclass(frozen=True)
class SitePlan:
    """Every test-module site of a plan: the module edits, the refused sites, and how many modules were read."""

    edits: tuple[ModuleEdit, ...]
    refused: tuple[RefusedSite, ...]
    read: int

    @property
    def rewrites(self) -> tuple[SiteRewrite, ...]:
        """Every rewrite, in module and text order."""
        return tuple(rewrite for edit in self.edits for rewrite in edit.rewrites)


class LeavingNames:
    """The copies leaving one package, looked up by a text that names one."""

    def __init__(self, copies: Iterable[Path]) -> None:
        self._by_base: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for copy in copies:
            self._by_base[copy.name].append(copy.parts)

    def named_by(self, text: str) -> bool:
        """Whether *text* names one of the copies: its last segment is the copy's base name and, unless it
        holds a ``..``, its segments end the copy's path."""
        if "\n" in text:
            return False
        segments = tuple(segment for segment in _SEPARATORS.split(text) if segment not in ("", _HERE))
        if not segments or segments[-1] not in self._by_base:
            return False
        if _UP in segments:
            return True
        return any(parts[-len(segments) :] == segments for parts in self._by_base[segments[-1]])


def shared_argument(base_dir: Path, shared: Path) -> str:
    """The accessor's argument naming *shared*: its path under the corpus's shared directory."""
    return shared.relative_to(shared_root(base_dir)).as_posix()


def accessor_call(argument: str) -> str:
    """The call reading the shared file *argument* names."""
    return f"{ACCESSOR}({json.dumps(argument, ensure_ascii=False)})"


def accessor_argument(replacement: str) -> str:
    """The path *replacement* passes the accessor, read from the parsed expression.

    Raises:
        FixtureScanError: *replacement* holds no one accessor call with one string literal argument.
    """
    calls = [
        node
        for node in ast.walk(ast.parse(replacement, mode="eval"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == ACCESSOR
    ]
    if len(calls) != 1 or len(calls[0].args) != 1 or calls[0].keywords:
        raise FixtureScanError(f"{replacement!r} holds no one {ACCESSOR}(...) call with one argument")
    argument = calls[0].args[0]
    if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
        raise FixtureScanError(f"{replacement!r} passes {ACCESSOR} no string literal")
    return argument.value


def literal_read(argument: str) -> str:
    """The expression reading the text of the shared file *argument* names."""
    return f'{accessor_call(argument)}.read_text(encoding="{_TEXT_ENCODING}")'


def _is_path_node(node: ast.AST) -> bool:
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, ast.Div)
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_JOIN_METHODS:
        return True
    return callee_name(node.func) in PATH_TYPES and bool(node.args)


def _operands(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp):
        return [node.left, node.right]
    assert isinstance(node, ast.Call)
    receiver = [node.func.value] if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_JOIN_METHODS else []
    return [*receiver, *node.args]


def _formatted_tail(node: ast.JoinedStr) -> str:
    """The segments a formatted string's last constant part writes whole: the text after its first separator."""
    last = node.values[-1] if node.values else None
    if not (isinstance(last, ast.Constant) and isinstance(last.value, str)):
        return ""
    pieces = _SEPARATORS.split(last.value, maxsplit=1)
    return pieces[1] if len(pieces) == 2 else ""


def _import_after(tree: ast.Module) -> int:
    """The line after which an import is added: the module's last top-level import before its first
    definition, else its docstring, else 0."""
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node.end_lineno or node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
    if last:
        return last
    first = tree.body[0] if tree.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.end_lineno or first.lineno
    return 0


def _binds_accessor(tree: ast.Module) -> bool:
    """Whether *tree* binds the accessor's name itself (an assignment, a definition or a parameter)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == ACCESSOR:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == ACCESSOR:
            return True
        if isinstance(node, ast.arg) and node.arg == ACCESSOR:
            return True
    return False


def _whole_values(tree: ast.Module) -> set[int]:
    """``id`` of each expression that is the whole value of a name bound once, at module level or in a function."""
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    values = set(map(id, single_bindings([node for node in tree.body if not isinstance(node, definitions)]).values()))
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            values.update(map(id, single_bindings(function.body).values()))
    return values


class _ModuleSites:
    """The sites of one test module."""

    def __init__(self, finder: _SiteFinder, module: Path, tests_root: Path, names: LeavingNames) -> None:
        self._finder = finder
        self._module = module
        self._names = names
        # Decoded as written, line endings kept: a rewrite's text must match the module's bytes.
        self._source = module.read_bytes().decode(_TEXT_ENCODING, errors="surrogateescape")
        self._tree = parse_module(module)
        self._scope: ModuleScope = finder.evaluator.scope(module, tests_root, self._tree)
        self._locals = enclosing_bindings(self._tree)
        self._parents = {id(child): node for node in ast.walk(self._tree) for child in ast.iter_child_nodes(node)}
        self._whole = _whole_values(self._tree)
        self._statements = {
            id(node.value) for node in ast.walk(self._tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        self._covered: set[int] = set()
        self.rewrites: list[SiteRewrite] = []
        self.refused: list[RefusedSite] = []

    def find(self, literals: Sequence[tuple[LiteralSite, Path]]) -> ModuleEdit | None:
        """Find the module's sites; its edit, or ``None`` when nothing in it is rewritten."""
        self._literal_sites(literals)
        self._pair_sites()
        self._path_sites()
        self._loose_names()
        if not self.rewrites:
            return None
        rewrites = sorted(self.rewrites, key=lambda rewrite: (rewrite.line, rewrite.column))
        if self._scope.imports.get(ACCESSOR) == (ACCESSOR_MODULE, 0, ACCESSOR):
            return ModuleEdit(self._module, tuple(rewrites), None)
        if ACCESSOR in self._scope.imports or _binds_accessor(self._tree):
            reason = f"the module binds {ACCESSOR} to something else, so the rewrite would not read the shared copy"
            self.refused.extend(RefusedSite(self._module, r.line, r.written, reason) for r in rewrites)
            self.rewrites.clear()
            return None
        return ModuleEdit(self._module, tuple(rewrites), _import_after(self._tree))

    def _literal_sites(self, literals: Sequence[tuple[LiteralSite, Path]]) -> None:
        constants = {
            (node.lineno, node.col_offset): node
            for node in ast.walk(self._tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for site, target in literals:
            node = constants.get((site.line, site.column))
            if node is None or node.value != site.text:
                raise FixtureScanError(
                    f"{self._module}:{site.line}: the literal {site.name} is no longer written there. "
                    "Fix: rebuild the plan from the files as they are now."
                )
            self._cover(node)
            self._rewrite(node, literal_read(shared_argument(self._finder.base_dir, target)), LITERAL_SITE, None, target)

    def _pair_sites(self) -> None:
        reached = self._reached_specs()
        for call in ast.walk(self._tree):
            if not (isinstance(call, ast.Call) and callee_name(call.func) == _PAIR_SPEC):
                continue
            operand = self._pair_file(call)
            if operand is None:
                continue
            self._cover(operand)
            directory = reached.get(id(call))
            if directory is None:
                self._refuse_named(operand, "its pair spec is registered with no fixtures directory the text shows")
                continue
            try:
                root = self._finder.evaluator.path(directory[0], self._scope, directory[1])
                name = self._finder.evaluator.evaluate(operand, self._scope, self._locals.get(id(operand), {}))
            except UnevaluableError as exc:
                self._refuse_named(operand, str(exc))
                continue
            if isinstance(name, (str, PurePath)):
                self._read_site(operand, root / name, PAIR_SITE)
            else:
                self._refuse_named(operand, f"its pair spec's file evaluates to {name!r}, not a path")

    def _pair_file(self, call: ast.Call) -> ast.expr | None:
        for keyword in call.keywords:
            if keyword.arg == _PAIR_FILE:
                return keyword.value
        return call.args[_PAIR_FILE_INDEX] if len(call.args) > _PAIR_FILE_INDEX else None

    def _reached_specs(self) -> dict[int, tuple[ast.expr, Mapping[str, ast.expr]]]:
        """``id`` of each pair spec a reader of this module reaches, with that reader's fixtures directory
        and the bindings around it."""
        reached: dict[int, tuple[ast.expr, Mapping[str, ast.expr]]] = {}
        for call in ast.walk(self._tree):
            if not isinstance(call, ast.Call) or callee_name(call.func) not in _PAIR_READERS:
                continue
            directory_at, specs_at = _PAIR_READERS[callee_name(call.func)]
            if len(call.args) <= max(directory_at, specs_at):
                continue
            local = self._locals.get(id(call), {})
            for spec in self._spec_calls(call.args[specs_at], local, 0):
                reached[id(spec)] = (call.args[directory_at], local)
        return reached

    def _spec_calls(self, node: ast.expr, local: Mapping[str, ast.expr], depth: int) -> Iterator[ast.Call]:
        if depth > _MAX_SPEC_DEPTH:
            return
        if isinstance(node, ast.Call) and callee_name(node.func) == _PAIR_SPEC:
            yield node
        elif isinstance(node, (ast.List, ast.Tuple)):
            for element in node.elts:
                yield from self._spec_calls(element, local, depth + 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            yield from self._spec_calls(node.left, local, depth + 1)
            yield from self._spec_calls(node.right, local, depth + 1)
        elif isinstance(node, ast.Name):
            bound = local.get(node.id, self._scope.bindings.get(node.id))
            if bound is not None:
                yield from self._spec_calls(bound, {}, depth + 1)

    def _path_sites(self) -> None:
        for node in ast.walk(self._tree):
            if id(node) in self._covered or not _is_path_node(node) or not self._maximal(node):
                continue
            assert isinstance(node, ast.expr)
            self._cover(node)
            try:
                value = self._finder.evaluator.evaluate(node, self._scope, self._locals.get(id(node), {}))
            except UnevaluableError as exc:
                self._refuse_named(node, str(exc))
                continue
            if isinstance(value, PurePath):
                self._read_site(node, Path(value), PATH_SITE)
            else:
                self._refuse_named(node, f"it evaluates to {value!r}, not a path")

    def _maximal(self, node: ast.AST) -> bool:
        parent = self._parents.get(id(node))
        return parent is None or not _is_path_node(parent) or not any(node is operand for operand in _operands(parent))

    def _read_site(self, node: ast.expr, path: Path, kind: str) -> None:
        """Rewrite *node*, which reads *path*, when *path* is a leaving copy; refuse what cannot be rewritten."""
        if not path.is_absolute():
            self._refuse_named(node, f"it evaluates to the relative path {path.as_posix()}, read from the working directory")
            return
        found = self._finder.leaving.get(path.resolve())
        if found is None:
            return
        read, shared = found
        parent = self._parents.get(id(node))
        if kind == PATH_SITE and isinstance(parent, ast.Attribute) and parent.attr in _SHAPE_READS:
            self._refuse(
                node,
                f"it reads .{parent.attr} of {self._finder.shown(read)}, where the copy lies rather than its bytes, "
                f"and its shared copy is {self._finder.shown(shared)}",
            )
            return
        self._rewrite(node, accessor_call(shared_argument(self._finder.base_dir, shared)), kind, read, shared)

    def _loose_names(self) -> None:
        for node in self._uncovered(self._tree):
            if id(node) in self._whole or id(node) in self._statements or not self._names_leaving(node):
                continue
            self._refuse(node, "it names a copy that leaves in an expression the script cannot evaluate to a path")

    def _uncovered(self, node: ast.AST) -> Iterator[ast.AST]:
        """Every node under *node* outside the sites already judged, not entering an import or a formatted
        string (a formatted string is judged whole)."""
        for child in ast.iter_child_nodes(node):
            if id(child) in self._covered or isinstance(child, (ast.Import, ast.ImportFrom)):
                continue
            yield child
            if not isinstance(child, ast.JoinedStr):
                yield from self._uncovered(child)

    def _names_leaving(self, node: ast.AST) -> bool:
        """Whether *node* names a copy leaving the module's package: a literal, or a constant holding one."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and self._names.named_by(node.value)
        if isinstance(node, ast.JoinedStr):
            value = self._looked_at(node)
            return self._names.named_by(value if isinstance(value, str) else _formatted_tail(node))
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            value = self._looked_at(node)
            return isinstance(value, str) and self._names.named_by(value)
        return False

    def _looked_at(self, node: ast.expr) -> object:
        try:
            return self._finder.evaluator.evaluate(node, self._scope, self._locals.get(id(node), {}))
        except UnevaluableError:
            return None

    def _refuse_named(self, node: ast.expr, reason: str) -> None:
        """Refuse *node* when the path it builds names a copy that leaves: a site reading another file stays."""
        tail = self._known_tail(node)
        if tail and self._names.named_by(tail):
            self._refuse(node, f"it names a copy that leaves, and {reason}")

    def _known_tail(self, node: ast.expr) -> str:
        """The trailing segments of the path *node* builds that its text fixes (empty when its last one is not):
        each joined operand that is a literal, or a constant holding one, from the end back to the first that
        is not."""
        whole = self._whole_text(node)
        if whole is not None:
            return whole
        if isinstance(node, ast.JoinedStr):
            return _formatted_tail(node)
        if not _is_path_node(node):
            return ""
        texts: list[str] = []
        for operand in reversed([operand for operand in _operands(node) if isinstance(operand, ast.expr)]):
            whole = self._whole_text(operand)
            if whole is None:
                texts.append(self._known_tail(operand))
                break
            texts.append(whole)
        return "/".join(text for text in reversed(texts) if text)

    def _whole_text(self, node: ast.expr) -> str | None:
        """The whole text *node* holds: a literal, or a formatted string or name evaluating to a text."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, (ast.JoinedStr, ast.Name, ast.Attribute)):
            value = self._looked_at(node)
            return value if isinstance(value, str) else None
        return None

    def _cover(self, node: ast.AST) -> None:
        self._covered.update(id(inner) for inner in ast.walk(node))

    def _refuse(self, node: ast.AST, reason: str) -> None:
        written = ast.get_source_segment(self._source, node) or ast.unparse(node)
        self.refused.append(RefusedSite(self._module, getattr(node, "lineno", 0), written, reason))

    def _rewrite(self, node: ast.expr, replacement: str, kind: str, read: Path | None, shared: Path) -> None:
        written = ast.get_source_segment(self._source, node)
        if written is None or node.end_lineno is None or node.end_col_offset is None:
            raise FixtureScanError(f"{self._module}:{node.lineno}: the expression's text cannot be read back from the module")
        self.rewrites.append(
            SiteRewrite(
                self._module, node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                written, replacement, kind, read, shared,
            )
        )


class _SiteFinder:
    """What every module's site search shares: the workspace, the leaving copies and the evaluator."""

    def __init__(self, base_dir: Path, moves: Mapping[Path, Path]) -> None:
        self.base_dir = base_dir
        self.leaving = {old.resolve(): (old, new) for old, new in moves.items()}
        self.evaluator = StaticEvaluator(constructs=False)

    def shown(self, path: Path) -> str:
        return path.relative_to(self.base_dir).as_posix()


def find_sites(
    base_dir: Path,
    packages: Sequence[Path],
    moves: Mapping[Path, Path],
    literals: Sequence[tuple[LiteralSite, Path]],
) -> SitePlan:
    """Every site of the test modules of *packages* (the modules whose literals the budget gate counts:
    ``tests/``, ``src/**/testkit/``, ``src/datrix_testing/``) that reads a copy *moves* takes out of its tree (each
    mapped to the copy replacing it), and every literal of *literals* (each with its shared file), as
    rewrites and refusals.

    Raises:
        FixtureScanError: A module cannot be read or parsed, or a literal is no longer where the plan found it.
    """
    finder = _SiteFinder(base_dir, moves)
    by_module: dict[Path, list[tuple[LiteralSite, Path]]] = defaultdict(list)
    for site, target in literals:
        by_module[site.module].append((site, target))
    edits: list[ModuleEdit] = []
    refused: list[RefusedSite] = []
    read = 0
    for package in packages:
        tests_root = package / PackageMarker.TESTS.value
        own = package.resolve()
        names = LeavingNames(old for old in moves if old.resolve().is_relative_to(own))
        for module in literal_modules(package):
            read += 1
            root = tests_root if module.is_relative_to(tests_root) else package / PackageMarker.SRC.value
            sites = _ModuleSites(finder, module, root, names)
            edit = sites.find(by_module.pop(module, []))
            if edit is not None:
                edits.append(edit)
            refused.extend(sites.refused)
    if by_module:
        raise FixtureScanError(
            f"literals of {', '.join(sorted(str(module) for module in by_module))} lie in no test module read. "
            "Fix: rebuild the plan from the files as they are now."
        )
    return SitePlan(tuple(edits), tuple(sorted(refused, key=lambda site: (site.module, site.line))), read)


def _line_starts(source: bytes) -> list[int]:
    return [0, *(match.end() for match in re.finditer(re.escape(_NEWLINE), source))]


def edit_spans(edit: ModuleEdit, source: bytes) -> list[tuple[int, int, bytes]]:
    """Each byte span of *source*, the module's bytes before *edit*, that *edit* replaces, with the bytes
    replacing it, in text order: each rewrite's expression and, when the accessor is imported, the empty
    span the import goes in.

    Raises:
        FixtureScanError: A rewrite's expression is not written where the plan found it, or two overlap.
    """
    starts = _line_starts(source)
    newline = _CRLF if _CRLF in source else _NEWLINE
    spans: list[tuple[int, int, bytes]] = []
    for rewrite in edit.rewrites:
        start = starts[rewrite.line - 1] + rewrite.column
        end = starts[rewrite.end_line - 1] + rewrite.end_column
        if source[start:end] != rewrite.written.encode(_TEXT_ENCODING, errors="surrogateescape"):
            raise FixtureScanError(
                f"{edit.module}:{rewrite.line}: {rewrite.written!r} is not written there, so its rewrite would "
                "change other text. Fix: rebuild the plan from the files as they are now."
            )
        spans.append((start, end, rewrite.replacement.encode(_TEXT_ENCODING)))
    if edit.import_after is not None:
        at = starts[edit.import_after] if edit.import_after < len(starts) else len(source)
        lead = newline if at == len(source) and source and not source.endswith(_NEWLINE) else b""
        spans.append((at, at, lead + ACCESSOR_IMPORT.encode(_TEXT_ENCODING) + newline))
    ordered = sorted(spans, key=lambda span: (span[0], span[1]))
    for before, after in pairwise(ordered):
        if after[0] < before[1]:
            raise FixtureScanError(f"{edit.module}: two rewrites overlap at byte {after[0]}. Fix: report the module's sites.")
    return ordered


def rewritten_source(edit: ModuleEdit) -> bytes:
    """The bytes of *edit*'s module once its rewrites are applied and the accessor imported.

    Raises:
        FixtureScanError: A rewrite's expression is not written where the plan found it, or two overlap.
    """
    source = edit.module.read_bytes()
    result = source
    for start, end, text in reversed(edit_spans(edit, source)):
        result = result[:start] + text + result[end:]
    return result
