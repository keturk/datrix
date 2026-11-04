"""Input-source census gate: a run reads user input before generation only through ``InputSource``.

``datrix_common.fileops.input_source`` is the one seam a run reads ``.dtrx`` sources, ``.dcfg``
documents, seed files, content collections and UI assets through, so the run can answer for what it
read. A direct read in the analysis packages is a read the run cannot see.

WHAT IS SCANNED. Every ``*.py`` under ``datrix-common/src``, ``datrix-language/src`` and
``datrix-semantic/src``, plus ``datrix-cli/src/datrix_cli/pipeline/stages/parsing.py``, except the
seam itself.

WHAT IS FLAGGED (syntactic, by ``ast``; import aliases are followed, receiver types are never
inferred), a call of:

  * builtin ``open``;
  * a ``Path`` method ``read_text``, ``read_bytes``, ``open``, ``exists``, ``is_file``, ``is_dir``,
    ``glob``, ``rglob``, ``iterdir`` or ``stat``, on any receiver that is not a known source;
  * ``os.listdir``, ``os.scandir``, ``os.walk``, ``os.path.exists``, ``os.path.isfile`` or
    ``os.path.isdir``;
  * a read helper of ``fileops/io.py``, ``utils/transient_io.py`` or ``utils/hash.py``.

A receiver is a known source only when it is a name annotated ``InputSource``, ``self.<attr>``
declared or assigned from one, or ``.input_source``. Every other receiver is reported, so the gate
fails closed.

PASSES when flagged - exemptions and exemptions - flagged are both empty: a module not in
:data:`EXEMPTIONS` fails, and so does a row that no longer matches a flagged module.

Built-in non-vacuity self-test, every invocation: an embedded source with one call of every flagged
form must flag exactly those, its clean twin nothing, and a planted workspace must report its direct
reads, pass the same reads through ``InputSource``, and report a stale row and a missing root.

Run it through ``gates/repo-hygiene/input-source-census-gate.ps1`` or its ``.sh`` twin; it runs in
gate mode (``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] input-source-census PASSED|FAILED exit=<n> log=<path>`` verdict last.

Exit codes: 0 = pass, 1 = a difference, 2 = the gate cannot judge (self-test failed, a scanned root
is missing, a source file that does not parse or cannot be read).
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, print_command, write_files
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import self_test_gate_parser
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "input-source-census"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.input_source_census_gate"
WRAPPER: Final = "input-source-census-gate"

SOURCE_ROOTS: Final[tuple[str, ...]] = ("datrix-common/src", "datrix-language/src", "datrix-semantic/src")
SOURCE_FILES: Final[tuple[str, ...]] = ("datrix-cli/src/datrix_cli/pipeline/stages/parsing.py",)
SEAM_MODULE: Final[str] = "datrix-common/src/datrix_common/fileops/input_source.py"

PATH_METHODS: Final[frozenset[str]] = frozenset({
    "read_text", "read_bytes", "open", "exists", "is_file", "is_dir", "glob", "rglob", "iterdir", "stat",
})
OS_CALLS: Final[frozenset[str]] = frozenset({
    "os.listdir", "os.scandir", "os.walk", "os.path.exists", "os.path.isfile", "os.path.isdir",
})
READ_HELPERS: Final[frozenset[str]] = frozenset({
    "read_text_utf8", "read_text_utf8_exact", "load_json", "read_text_with_retry", "compute_file_hash",
})
BUILTIN_OPEN: Final[str] = "open"
SOURCE_TYPE: Final[str] = "InputSource"
APPLICATION_ATTRIBUTE: Final[str] = "input_source"
INSTANCE_NAME: Final[str] = "self"

_COMMON: Final[str] = "datrix-common/src/datrix_common"
_LANGUAGE: Final[str] = "datrix-language/src/datrix_language"
_SEMANTIC: Final[str] = "datrix-semantic/src/datrix_semantic"
_TOOLCHAIN: Final[str] = "toolchain resource: reads what the package ships, never user input"
_GRAMMAR: Final[str] = "grammar build: reads the toolchain's grammar and build artifacts"
_HELPER: Final[str] = "read helper: the function the census flags at its callers"

_EXIT_GATE_BROKEN: Final[int] = 2

_SELF_TEST_PREFIX: Final[str] = "input-source-census-selftest-"


@dataclass(frozen=True)
class DirectRead:
    """One flagged call: its line and the form that flagged it."""

    line: int
    form: str

    def __str__(self) -> str:
        return f"{self.form}@{self.line}"


@dataclass(frozen=True)
class Exemption:
    """A workspace-relative posix module pattern that may read directly, and why."""

    pattern: str
    reason: str


EXEMPTIONS: Final[tuple[Exemption, ...]] = (
    Exemption(f"{_COMMON}/builtins/data/*_loader.py", _TOOLCHAIN),
    Exemption(f"{_COMMON}/config/image_pins.py", _TOOLCHAIN),
    Exemption(f"{_COMMON}/config/project/catalog.py", _TOOLCHAIN),
    Exemption(f"{_COMMON}/stdlib/catalog.py", _TOOLCHAIN),
    Exemption(f"{_LANGUAGE}/transformers/node_types.py", _TOOLCHAIN),
    Exemption(f"{_LANGUAGE}/builtins/loader.py", _TOOLCHAIN),
    Exemption(f"{_SEMANTIC}/diagnostics/catalog.py", _TOOLCHAIN),
    Exemption(f"{_LANGUAGE}/parser/tree_sitter_datrix/build.py", _GRAMMAR),
    Exemption(f"{_LANGUAGE}/parser/tree_sitter_datrix/grammar_operators.py", _GRAMMAR),
    Exemption(f"{_LANGUAGE}/lsp/*", "language server: reads the editor's workspace, outside any run"),
    Exemption(f"{_COMMON}/fileops/io.py", _HELPER),
    Exemption(f"{_COMMON}/utils/transient_io.py", _HELPER),
    Exemption(f"{_COMMON}/utils/hash.py", _HELPER),
    Exemption(f"{_COMMON}/testing/tag_vocabulary.py", "test-tag vocabulary: reads the repo's docs, never user input"),
)


def _names_source(annotation: ast.expr | None) -> bool:
    """Whether *annotation* declares an ``InputSource``, alone or with ``None``."""
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return _names_source(ast.parse(annotation.value, mode="eval").body)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        sides = (annotation.left, annotation.right)
        return any(map(_names_source, sides)) and all(_names_source(side) or _is_none(side) for side in sides)
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == SOURCE_TYPE
    return isinstance(annotation, ast.Name) and annotation.id == SOURCE_TYPE


def _is_none(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is None


def _own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Every node of *scope*, without entering a nested function, lambda or class."""
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            pending.extend(ast.iter_child_nodes(node))


def _parameters(arguments: ast.arguments) -> list[ast.arg]:
    named = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    return named + [extra for extra in (arguments.vararg, arguments.kwarg) if extra is not None]


def _scope_sources(
    scope: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, enclosing: frozenset[str]
) -> frozenset[str]:
    """The names bound to a source inside *scope*: a parameter hides the enclosing name it repeats."""
    parameters = _parameters(scope.args)
    locals_declared = {
        node.target.id for node in _own_nodes(scope)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and _names_source(node.annotation)
    }
    declared = {parameter.arg for parameter in parameters if _names_source(parameter.annotation)}
    return (enclosing - {parameter.arg for parameter in parameters}) | declared | locals_declared


def _instance_attribute(target: ast.expr) -> str:
    """``attr`` when *target* is ``self.attr``; else empty."""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == INSTANCE_NAME:
        return target.attr
    return ""


def _is_source_value(value: ast.expr | None, names: frozenset[str]) -> bool:
    if isinstance(value, ast.Name):
        return value.id in names
    return isinstance(value, ast.Attribute) and value.attr == APPLICATION_ATTRIBUTE


def _method_source_attributes(method: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[str]:
    names = _scope_sources(method, frozenset())
    for node in _own_nodes(method):
        if isinstance(node, ast.AnnAssign) and _names_source(node.annotation):
            yield _instance_attribute(node.target)
        elif isinstance(node, ast.Assign) and _is_source_value(node.value, names):
            yield from map(_instance_attribute, node.targets)


def _class_source_attributes(node: ast.ClassDef) -> frozenset[str]:
    """The attributes of *node* declared ``InputSource`` or assigned from a source in a method."""
    attributes: set[str] = set()
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if _names_source(statement.annotation):
                attributes.add(statement.target.id)
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            attributes.update(_method_source_attributes(statement))
    return frozenset(attributes - {""})


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """What each imported name binds, by dotted name; a plain ``import a.b`` needs no entry."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update({name.asname: name.name for name in node.names if name.asname})
        elif isinstance(node, ast.ImportFrom):
            aliases.update({name.asname or name.name: f"{node.module or ''}.{name.name}" for name in node.names})
    return aliases


class _ReadVisitor(ast.NodeVisitor):
    """Collects the direct reads of a module, tracking which names and attributes hold a source."""

    def __init__(self, aliases: dict[str, str]) -> None:
        self.reads: list[DirectRead] = []
        self._aliases = aliases
        self._names: frozenset[str] = frozenset()
        self._attributes: frozenset[str] = frozenset()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        enclosing = self._attributes
        self._attributes = _class_source_attributes(node)
        self.generic_visit(node)
        self._attributes = enclosing

    def _visit_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        enclosing = self._names
        self._names = _scope_sources(node, enclosing)
        self.generic_visit(node)
        self._names = enclosing

    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope
    visit_Lambda = _visit_scope

    def visit_Call(self, node: ast.Call) -> None:
        form = self._direct_form(node.func)
        if form:
            self.reads.append(DirectRead(node.lineno, form))
        self.generic_visit(node)

    def _resolved(self, func: ast.expr) -> str:
        """The dotted name *func* refers to through the imports; empty for any other expression."""
        if isinstance(func, ast.Name):
            return self._aliases.get(func.id, func.id)
        if isinstance(func, ast.Attribute):
            owner = self._resolved(func.value)
            return f"{owner}.{func.attr}" if owner else ""
        return ""

    def _known_source(self, receiver: ast.expr) -> bool:
        if isinstance(receiver, ast.Name):
            return receiver.id in self._names
        if isinstance(receiver, ast.Attribute) and receiver.attr == APPLICATION_ATTRIBUTE:
            return True
        return _instance_attribute(receiver) in self._attributes

    def _direct_form(self, func: ast.expr) -> str:
        """The flagged form of a call of *func*; empty when the call is clean."""
        resolved = self._resolved(func)
        final = resolved.rpartition(".")[2]
        if resolved in OS_CALLS:
            return resolved
        if final in READ_HELPERS:
            return final
        if isinstance(func, ast.Name):
            return BUILTIN_OPEN if final == BUILTIN_OPEN else ""
        if isinstance(func, ast.Attribute) and func.attr in PATH_METHODS and not self._known_source(func.value):
            return ast.unparse(func)
        return ""


def direct_reads(source: str) -> list[DirectRead]:
    """The flagged calls of *source*; raises ``SyntaxError`` when it does not parse."""
    tree = ast.parse(source)
    visitor = _ReadVisitor(_import_aliases(tree))
    visitor.visit(tree)
    return visitor.reads


def source_files(workspace: Path) -> list[Path]:
    """The ``*.py`` files the census reads, sorted within each root, the seam left out."""
    paths = [path for root in SOURCE_ROOTS for path in sorted((workspace / root).rglob("*.py"))]
    paths += [workspace / relative for relative in SOURCE_FILES]
    return [path for path in paths if path != workspace / SEAM_MODULE]


def scan(workspace: Path) -> tuple[dict[str, list[DirectRead]], list[str]]:
    """The flagged calls by module, and one message per input that could not be judged."""
    broken = [f"{relative}: does not exist; the gate cannot judge it"
              for relative in (*SOURCE_ROOTS, *SOURCE_FILES) if not (workspace / relative).exists()]
    if broken:
        return {}, broken
    flagged: dict[str, list[DirectRead]] = {}
    for path in source_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        try:
            reads = direct_reads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as error:
            broken.append(f"{relative}: cannot be parsed ({error}); the gate cannot judge it")
            continue
        if reads:
            flagged[relative] = reads
    return flagged, broken


@dataclass(frozen=True)
class Difference:
    """Flagged modules no row exempts, and rows that match no flagged module."""

    unlisted: dict[str, list[DirectRead]]
    stale: list[Exemption]

    def __bool__(self) -> bool:
        return bool(self.unlisted or self.stale)


def compare(flagged: dict[str, list[DirectRead]], exemptions: Sequence[Exemption]) -> Difference:
    """flagged - exemptions and exemptions - flagged."""
    unlisted = {module: reads for module, reads in flagged.items()
                if not any(fnmatchcase(module, row.pattern) for row in exemptions)}
    stale = [row for row in exemptions if not any(fnmatchcase(module, row.pattern) for module in flagged)]
    return Difference(unlisted, stale)


_FLAGGED_SOURCE: Final[str] = '''\
import os
import os as system
import os.path as os_paths
from os import walk as tree_walk
from pathlib import Path

from datrix_common.fileops.io import load_json, read_text_utf8 as read_utf8
from datrix_common.utils import hash as hashing


class Holder:
    def __init__(self, path: Path, source) -> None:
        self._path = path
        self._unknown = source

    def read(self) -> str:
        self._unknown.is_file(self._path)
        return self._path.read_text()


def direct(path: Path, source) -> None:
    open(path)
    path.read_text()
    path.read_bytes()
    path.open()
    path.exists()
    path.is_file()
    path.is_dir()
    path.glob("*")
    path.rglob("*")
    path.iterdir()
    path.stat()
    os.listdir(path)
    os.scandir(path)
    os.walk(path)
    os.path.exists(path)
    os.path.isfile(path)
    os.path.isdir(path)
    system.listdir(path)
    os_paths.isfile(path)
    tree_walk(path)
    load_json(path)
    read_utf8(path)
    hashing.compute_file_hash(path)
    source.read_text(path)


def hidden(source: InputSource, path: Path) -> None:
    def inner(source: Path) -> None:
        source.read_text()

    inner(path)
'''

_FLAGGED_FORMS: Final[tuple[str, ...]] = (
    "self._unknown.is_file", "self._path.read_text",
    "open", "path.read_text", "path.read_bytes", "path.open", "path.exists", "path.is_file", "path.is_dir",
    "path.glob", "path.rglob", "path.iterdir", "path.stat",
    "os.listdir", "os.scandir", "os.walk", "os.path.exists", "os.path.isfile", "os.path.isdir",
    "os.listdir", "os.path.isfile", "os.walk",
    "load_json", "read_text_utf8", "compute_file_hash", "source.read_text",
    "source.read_text",
)

_CLEAN_SOURCE: Final[str] = '''\
from pathlib import Path

from datrix_common.fileops import input_source
from datrix_common.fileops.input_source import InputSource


class Holder:
    declared: InputSource

    def __init__(self, source: InputSource, app: Application) -> None:
        self._source = source
        self._kept: "InputSource" = source
        self._from_app = app.input_source

    def read(self, path: Path) -> None:
        self.declared.read_text(path)
        self._source.read_bytes(path)
        self._kept.is_file(path)
        self._from_app.is_dir(path)


def read(source: InputSource, optional: InputSource | None, dotted: input_source.InputSource, path: Path) -> None:
    source.read_text(path)
    source.read_bytes(path, max_bytes=1)
    source.is_file(path)
    source.is_dir(path)
    source.glob(path, "*")
    dotted.read_text(path)
    if optional is not None:
        optional.read_text(path)


def read_local(app: Application, path: Path) -> None:
    source: InputSource = app.input_source
    source.read_text(path)
    app.input_source.read_bytes(path)


def closure(source: InputSource, paths: list[Path]) -> list[str]:
    def inner(path: Path) -> str:
        return source.read_text(path)

    return sorted(map(lambda path: source.read_text(path), paths)) + [inner(path) for path in paths]
'''

_DIRECT_READ: Final[str] = "def read(path):\n    return path.read_text(encoding='utf-8')\n"
_SOURCE_READ: Final[str] = "def read(source: InputSource, path):\n    return source.read_text(path)\n"
_PLANTED_DIRECT: Final[tuple[str, ...]] = (
    f"{_COMMON}/seed/direct.py", f"{_LANGUAGE}/parser/direct.py", f"{_SEMANTIC}/validators/direct.py", SOURCE_FILES[0],
)
_PLANTED_EXEMPT: Final[str] = f"{_COMMON}/exempt/direct.py"
_PLANTED_CLEAN: Final[str] = f"{_COMMON}/seed/through_source.py"
_PLANTED_OUTSIDE: Final[str] = "datrix-cli/src/datrix_cli/commands/direct.py"
_PLANTED_STALE: Final[str] = f"{_COMMON}/gone/*.py"


def _matcher_problems() -> list[str]:
    found = tuple(read.form for read in direct_reads(_FLAGGED_SOURCE))
    problems = [] if found == _FLAGGED_FORMS else [f"flagged forms: expected {_FLAGGED_FORMS}, got {found}"]
    clean = [str(read) for read in direct_reads(_CLEAN_SOURCE)]
    return problems + ([f"clean twin flagged: {clean}"] if clean else [])


def _planted_problems(root: Path) -> list[str]:
    """Scan a planted workspace: its direct reads reported, the same reads through a source clean."""
    planted = {relative: _DIRECT_READ for relative in (*_PLANTED_DIRECT, _PLANTED_EXEMPT, _PLANTED_OUTSIDE, SEAM_MODULE)}
    write_files(root, {**planted, _PLANTED_CLEAN: _SOURCE_READ})
    flagged, broken = scan(root)
    exemptions = (Exemption(f"{_COMMON}/exempt/*", "self-test"), Exemption(_PLANTED_STALE, "self-test"))
    difference = compare(flagged, exemptions)
    problems = [f"planted workspace broken: {broken}"] if broken else []
    if sorted(difference.unlisted) != sorted(_PLANTED_DIRECT):
        problems.append(f"unlisted modules wrong: {sorted(difference.unlisted)}")
    if [row.pattern for row in difference.stale] != [_PLANTED_STALE]:
        problems.append(f"stale rows wrong: {[row.pattern for row in difference.stale]}")
    missing = scan(root / "absent")[1]
    if len(missing) != len(SOURCE_ROOTS) + len(SOURCE_FILES):
        problems.append(f"missing roots not all reported: {missing}")
    return problems


def self_test() -> list[str]:
    """Problems with the matcher, the scan and the comparison; empty when all three work."""
    problems = _matcher_problems()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR, prefix=_SELF_TEST_PREFIX, ignore_cleanup_errors=True) as scratch:
        return problems + _planted_problems(Path(scratch))


def _print_difference(difference: Difference) -> None:
    for module, reads in difference.unlisted.items():
        print(f"UNLISTED {module}  {', '.join(str(read) for read in reads)}")
    for row in difference.stale:
        print(f"STALE    {row.pattern}  no flagged module matches this row")
    if difference.unlisted:
        print("\nAn unlisted module reads directly, so the run cannot see the read. Read through "
              "app.input_source, or take source: InputSource from the caller. A module that reads no "
              f"user input gets a row, with its reason, in EXEMPTIONS of {MODULE}.")
    if difference.stale:
        print(f"\nRemove each stale row from EXEMPTIONS of {MODULE}: the reads it covered are gone.")


def run_gate(workspace: Path) -> int:
    """Compare the flagged modules of *workspace* with the exemption table; print every difference."""
    flagged, broken = scan(workspace)
    for message in broken:
        print(f"BROKEN {message}")
    if broken:
        return _EXIT_GATE_BROKEN
    difference = compare(flagged, EXEMPTIONS)
    _print_difference(difference)
    print(f"{len(source_files(workspace))} file(s) scanned, {len(flagged)} flagged module(s), "
          f"{len(EXEMPTIONS)} exemption row(s), {len(difference.unlisted)} unlisted, {len(difference.stale)} stale")
    return EXIT_VIOLATION if difference else EXIT_PASS


def _check_matcher_scan_and_comparison() -> None:
    problems = self_test()
    assert not problems, "\n".join(problems)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/input-source-census-gate.ps1``: one per wrapper parameter."""
    return self_test_gate_parser(WRAPPER, "A run reads user input before generation only through InputSource.")


def _run(args: argparse.Namespace) -> int:
    if args.debug:
        print_command()
    if args.self_test:
        return wrappers.run_self_test(
            [_check_matcher_scan_and_comparison],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    problems = self_test()
    for problem in problems:
        print(f"SELF-TEST FAIL {problem}")
    if problems:
        print("Input-source census self-test failed: the matcher cannot tell a direct read from a source read.")
        return _EXIT_GATE_BROKEN
    print("self-test passed: every flagged form fires, its clean twin does not")
    return run_gate(WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
