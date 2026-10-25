#!/usr/bin/env python3
"""Split a large module into sibling modules, and point every importer at the new homes.

Top-level definitions move VERBATIM (source lines, comments above them included, never
regenerated code), so a split cannot change behaviour by re-rendering an expression. A JSON
plan names, for each new sibling module, the definitions it receives and its docstring::

    {
      "_plan_sizing":  {"doc": "App Service Plan SKU policy.", "range": ["SKU_MAP", "derive_size"]},
      "_plan_checks":  {"doc": "SKU validation.", "names": ["validate_sku", "_tier_of"]}
    }

``range`` claims a contiguous run in source order; ``names`` claims an explicit list. Whatever
no entry claims stays in the original module.

Each new module gets the original's import header with its own docstring, the imports of
the names it uses from its siblings and from the original, the original's module-level ``pytestmark`` (a test
module's marks do not survive a split by themselves), and its definitions. The original keeps
its header, the unclaimed definitions and imports of the moved names it still uses.

The original module does NOT re-export what moved: every symbol keeps one import path. Every
``from <original> import <moved name>`` in the workspace (``datrix_scripts.import_sites``) is
rewritten to the new home instead. The split refuses -- writing nothing -- when it would be
wrong or incomplete:

- a definition claimed twice, an unknown name, a reversed range, a claimed ``pytestmark``;
- an import cycle among the new modules and the original: moved code imports the names left
  behind from the original, and the original imports the moved names it still uses, so moved code
  may use what stays only when nothing that stays uses it back;
- an ``__all__`` in the original naming a moved name;
- an importer the rewrite cannot reach: ``alias.<moved name>`` on the module object, an import
  statement sharing its line with other code, or the dotted path ``<original>.<moved name>``
  (or ``<original>:<moved name>``) written as text in a source or ``pyproject.toml`` file.

``ruff check --select F401,I001 --fix`` then prunes and sorts the imports of the new modules and
the original. ``--dry-run`` prints everything the split would do and writes nothing.

The module behind ``codemods/split-module.ps1`` (and its ``.sh`` twin).

Exit codes: 0 = split done (or a clean dry run), 1 = refused (every reason printed), 2 = usage.

Usage:
    python -m datrix_scripts.codemods.split_module --module=FILE --plan=PLAN.json [--package-module=DOTTED] [--dry-run]
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.import_sites import (
    PACKAGE_DIR_PREFIX,
    SOURCE_ENCODING,
    SRC_DIR_NAME,
    ModuleBindings,
    parse_source,
    scanned_files,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import CODEMODS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.codemods.split_module"
WRAPPER: Final = "split-module"

EXIT_OK: Final[int] = 0
EXIT_REFUSED: Final[int] = 1
MARKER_NAME: Final[str] = "pytestmark"
ALL_NAME: Final[str] = "__all__"
INIT_FILE_NAME: Final[str] = "__init__.py"
PYPROJECT_NAME: Final[str] = "pyproject.toml"
PLAN_DOC_KEY: Final[str] = "doc"
PLAN_RANGE_KEY: Final[str] = "range"
PLAN_NAMES_KEY: Final[str] = "names"
MAX_SINGLE_LINE_IMPORT: Final[int] = 100
RUFF_RULES: Final[str] = "F401,I001"
WRITE_ENCODING: Final[str] = "utf-8"
BLANK_LINES_BEFORE_DEFINITIONS: Final[str] = "\n\n"


class SplitRefused(Exception):
    """The split would be wrong or incomplete; nothing has been written."""


@dataclass(frozen=True)
class PlanEntry:
    """One new sibling module: its stem, docstring and the definitions it receives."""

    stem: str
    doc: str
    keys: tuple[str, ...]


@dataclass
class SourceModule:
    """The module being split, cut into its header and one block per top-level definition."""

    lines: list[str]
    header_end: int
    docstring: ast.Expr | None
    blocks: dict[str, str] = field(default_factory=dict)
    owner: dict[str, list[str]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    @property
    def header(self) -> str:
        return "".join(self.lines[: self.header_end])


@dataclass(frozen=True)
class ImporterEdit:
    """One import statement to replace in an importer file."""

    path: Path
    first_line: int
    last_line: int
    replacement: str


# ---------------------------------------------------------------------------
# Reading the module
# ---------------------------------------------------------------------------


def defined_names(node: ast.stmt) -> list[str]:
    """The names a top-level statement defines (empty for imports and expressions)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    return []


def _start_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)])


def _end_line(node: ast.stmt) -> int:
    if node.end_lineno is None:
        raise SplitRefused(f"Statement at line {node.lineno} carries no end position; run under Python >= 3.8.")
    return node.end_lineno


def free_names(source: str) -> set[str]:
    """Every name in *source* that could refer to something defined elsewhere.

    Parameter names are subtracted: a helper taking a ``deploy`` argument would otherwise read
    as a reference to a module-level ``deploy``, inventing an edge that can fabricate a cycle.
    """
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            spec = node.args
            arguments = [*spec.posonlyargs, *spec.args, *spec.kwonlyargs]
            arguments += [arg for arg in (spec.vararg, spec.kwarg) if arg is not None]
            bound.update(arg.arg for arg in arguments)
    return names - bound


def _header_end(body: list[ast.stmt]) -> int:
    """The last line of the docstring and import block above the first definition."""
    first_named = next((index for index, node in enumerate(body) if defined_names(node)), len(body))
    header_nodes = [
        node for node in body[:first_named] if isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.If))
    ]
    if not header_nodes:
        raise SplitRefused("The module has no docstring or import block above its first definition to copy.")
    return max(_end_line(node) for node in header_nodes)


def source_lines(path: Path) -> list[str]:
    """The lines of *path* as Python numbers them. ``str.splitlines`` also breaks at form feeds and
    other separators the parser does not count, which shifts every later line number."""
    return io.StringIO(path.read_text(encoding=SOURCE_ENCODING), newline="").readlines()


def read_module(path: Path) -> SourceModule:
    """Cut *path* into its header and one block per top-level definition. Each block owns the
    lines above it (its leading comments) through its own last line."""
    lines = source_lines(path)
    tree = ast.parse("".join(lines), filename=str(path))
    body = list(tree.body)
    first = body[0] if body else None
    is_docstring = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
    module = SourceModule(lines=lines, header_end=_header_end(body), docstring=first if is_docstring else None)
    previous_end = module.header_end
    for node in body:
        names = defined_names(node)
        if not names:
            continue
        end = _end_line(node)
        if _start_line(node) <= module.header_end:
            previous_end = end
            continue
        key = names[0]
        module.blocks[key] = "".join(lines[previous_end:end])
        module.owner[key] = names
        module.order.append(key)
        previous_end = end
    if module.order and previous_end < len(lines):
        module.blocks[module.order[-1]] += "".join(lines[previous_end:])
    return module


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def _claimed(stem: str, spec: Mapping[str, object], order: Sequence[str]) -> tuple[str, ...]:
    if PLAN_NAMES_KEY in spec:
        names = spec[PLAN_NAMES_KEY]
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise SplitRefused(f"{stem}: '{PLAN_NAMES_KEY}' must be a list of definition names.")
        unknown = [name for name in names if name not in order]
        if unknown:
            raise SplitRefused(f"{stem}: no top-level definition named {unknown}. Defined: {list(order)}.")
        return tuple(names)
    span = spec.get(PLAN_RANGE_KEY)
    if not isinstance(span, list) or len(span) != 2 or not all(name in order for name in span):
        raise SplitRefused(
            f"{stem}: expected '{PLAN_RANGE_KEY}': [first, last] naming two top-level definitions, "
            f"or '{PLAN_NAMES_KEY}': [...]. Got {spec!r}. Defined: {list(order)}."
        )
    low, high = order.index(span[0]), order.index(span[1])
    if low > high:
        raise SplitRefused(f"{stem}: {span[0]!r} comes after {span[1]!r} in the module.")
    return tuple(order[low : high + 1])


def load_plan(path: Path, module: SourceModule) -> list[PlanEntry]:
    """Parse and validate the plan file against *module*."""
    raw = json.loads(path.read_text(encoding=SOURCE_ENCODING))
    if not isinstance(raw, dict) or not raw:
        raise SplitRefused(f"{path}: expected a non-empty JSON object {{module_stem: {{doc, range|names}}}}.")
    entries: list[PlanEntry] = []
    for stem, spec in raw.items():
        if not isinstance(spec, dict) or not isinstance(spec.get(PLAN_DOC_KEY), str) or not spec[PLAN_DOC_KEY].strip():
            raise SplitRefused(f"{stem}: every plan entry needs a non-empty '{PLAN_DOC_KEY}' (the new module's docstring).")
        if not stem.isidentifier():
            raise SplitRefused(f"{stem!r} is not a valid module name.")
        entries.append(PlanEntry(stem=stem, doc=spec[PLAN_DOC_KEY].strip(), keys=_claimed(stem, spec, module.order)))
    return entries


def assign(entries: Sequence[PlanEntry]) -> dict[str, str]:
    """Definition key -> the new module that receives it."""
    assignment: dict[str, str] = {}
    for entry in entries:
        for key in entry.keys:
            if key == MARKER_NAME:
                raise SplitRefused(f"{entry.stem}: {MARKER_NAME} is copied into every new module; never claim it.")
            if key in assignment:
                raise SplitRefused(f"{key!r} is claimed by both {assignment[key]} and {entry.stem}.")
            assignment[key] = entry.stem
    return assignment


def _assert_acyclic(graph: Mapping[str, set[str]], edge_names: Mapping[tuple[str, str], set[str]]) -> None:
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = [*path[path.index(node):], node]
            uses = "; ".join(f"{a} uses {sorted(edge_names[(a, b)])} from {b}" for a, b in zip(cycle, cycle[1:]))
            raise SplitRefused(
                f"The cut creates an import cycle: {' -> '.join(cycle)} ({uses}). Fix: claim the names that "
                "close the cycle into the same module."
            )
        state[node] = 1
        for successor in sorted(graph.get(node, set())):
            visit(successor, [*path, node])
        state[node] = 2

    for node in sorted(graph):
        visit(node, [])


def homes_of(module: SourceModule, provides: Mapping[str, str], original_stem: str) -> dict[str, str]:
    """Every top-level name -> the module that defines it after the split: its new module, or the original."""
    kept = {name: original_stem for key in module.order if key not in provides for name in module.owner[key]}
    kept.pop(MARKER_NAME, None)
    return {**kept, **provides}


def validate_cut(module: SourceModule, entries: Sequence[PlanEntry], homes: Mapping[str, str], original_stem: str) -> None:
    """Refuse an import cycle among the new modules and the original.

    Moved code imports the names left behind from the original, and the original imports the moved
    names it still uses, so the cut is sound exactly when those imports form no cycle.
    """
    blocks = {original_stem: [module.blocks[key] for key in module.order if homes.get(key) == original_stem]}
    blocks.update({entry.stem: [module.blocks[key] for key in entry.keys] for entry in entries})
    edge_names: dict[tuple[str, str], set[str]] = {}
    for stem, sources in blocks.items():
        for name in set().union(*(free_names(source) for source in sources)):
            home = homes.get(name)
            if home and home != stem:
                edge_names.setdefault((stem, home), set()).add(name)
    graph: dict[str, set[str]] = {stem: set() for stem in blocks}
    for source, home in edge_names:
        graph[source].add(home)
    _assert_acyclic(graph, edge_names)


def _check_all(module: SourceModule, moved: frozenset[str]) -> None:
    block = module.blocks.get(ALL_NAME)
    if block is None:
        return
    listed = {node.value for node in ast.walk(ast.parse(block)) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    if listed & moved:
        raise SplitRefused(
            f"{ALL_NAME} in the original names moved definitions {sorted(listed & moved)}. Fix: remove them "
            f"from {ALL_NAME} first (each symbol keeps one import path), then split."
        )


# ---------------------------------------------------------------------------
# Rendering the new modules and the remainder
# ---------------------------------------------------------------------------


def _import_statement(module: str, names: Sequence[str], indent: str = "", level: int = 0) -> str:
    dots = "." * level
    single = f"{indent}from {dots}{module} import {', '.join(names)}\n"
    if len(single) <= MAX_SINGLE_LINE_IMPORT:
        return single
    inner = "".join(f"{indent}    {name},\n" for name in names)
    return f"{indent}from {dots}{module} import (\n{inner}{indent})\n"


def _header_with_doc(module: SourceModule, doc: str) -> str:
    if module.docstring is None:
        return f'"""{doc}"""\n\n' + module.header
    doc_end = _end_line(module.docstring)
    return f'"""{doc}"""\n' + "".join(module.lines[doc_end : module.header_end])


def _imports_from_siblings(sources: Sequence[str], own_stem: str, homes: Mapping[str, str], package: str) -> str:
    needed: dict[str, set[str]] = {}
    for source in sources:
        for name in free_names(source):
            home = homes.get(name)
            if home is not None and home != own_stem:
                needed.setdefault(home, set()).add(name)
    return "".join(_import_statement(f"{package}.{home}", sorted(names)) for home, names in sorted(needed.items()))


def _definitions(sources: Sequence[str]) -> str:
    """The moved blocks, two blank lines below whatever precedes them (PEP 8)."""
    return BLANK_LINES_BEFORE_DEFINITIONS + "".join(sources).lstrip("\n")


def render_new_module(module: SourceModule, entry: PlanEntry, homes: Mapping[str, str], package: str) -> str:
    sources = [module.blocks[key] for key in entry.keys]
    marker = module.blocks.get(MARKER_NAME, "").strip("\n")
    return (
        _header_with_doc(module, entry.doc)
        + _imports_from_siblings(sources, entry.stem, homes, package)
        + (f"\n{marker}\n" if marker else "")
        + _definitions(sources)
    )


def render_remainder(module: SourceModule, homes: Mapping[str, str], package: str, original_stem: str) -> str:
    kept = [module.blocks[key] for key in module.order if homes.get(key, original_stem) == original_stem]
    return module.header + _imports_from_siblings(kept, original_stem, homes, package) + _definitions(kept)


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------


def _statement_owns_its_lines(lines: Sequence[str], node: ast.ImportFrom) -> bool:
    end_line = _end_line(node)
    before = lines[node.lineno - 1][: node.col_offset]
    after = lines[end_line - 1][node.end_col_offset or 0 :].strip()
    return not before.strip() and (not after or after.startswith("#"))


def _rewrite(node: ast.ImportFrom, moved: Mapping[str, str], indent: str) -> str:
    """The statements replacing *node*: kept names from the original, moved names from their homes."""
    if node.module is None:
        raise SplitRefused(f"Line {node.lineno}: 'from {'.' * node.level} import ...' cannot name the split module.")
    parent = node.module.rpartition(".")[0]
    kept = [alias for alias in node.names if alias.name not in moved]
    by_home: dict[str, list[ast.alias]] = {}
    for alias in node.names:
        if alias.name in moved:
            by_home.setdefault(moved[alias.name], []).append(alias)
    pieces: list[str] = []
    if kept:
        pieces.append(_import_statement(node.module, [ast.unparse(alias) for alias in kept], indent, node.level))
    for home, aliases in sorted(by_home.items()):
        target = f"{parent}.{home}" if parent else home
        pieces.append(_import_statement(target, [ast.unparse(alias) for alias in aliases], indent, node.level))
    return "".join(pieces)


def display_path(path: Path, workspace: Path) -> str:
    """*path* relative to *workspace* when it lies inside it, else absolute."""
    resolved = path.resolve()
    return resolved.relative_to(workspace).as_posix() if resolved.is_relative_to(workspace) else resolved.as_posix()


def _text_references(path: Path, original: str, moved: Mapping[str, str], workspace: Path) -> list[str]:
    try:
        text = path.read_text(encoding=SOURCE_ENCODING)
    except UnicodeDecodeError:
        # A binary asset (image, font, compiled grammar) cannot spell a dotted Python path.
        return []
    return [
        f"{display_path(path, workspace)}: text reference {needle!r}"
        for name in sorted(moved)
        for needle in (f"{original}.{name}", f"{original}:{name}")
        if needle in text
    ]


def _importer_edits(
    path: Path, original: str, moved: Mapping[str, str], workspace: Path
) -> tuple[list[ImporterEdit], list[str]]:
    tree = parse_source(path)
    lines = source_lines(path)
    bindings = ModuleBindings(path, tree, frozenset({original}))
    relative = display_path(path, workspace)
    blockers = [
        f"{relative}:{node.lineno}: {ast.unparse(node)} reads a moved name off the module object"
        for node in bindings.attribute_reads(tree, frozenset(moved))
    ]
    edits: list[ImporterEdit] = []
    for node, _ in bindings.from_imports:
        if not any(alias.name in moved for alias in node.names):
            continue
        if not _statement_owns_its_lines(lines, node):
            blockers.append(f"{relative}:{node.lineno}: the import shares its line with other code")
            continue
        comment = lines[_end_line(node) - 1][node.end_col_offset or 0 :].strip()
        replacement = _rewrite(node, moved, " " * node.col_offset)
        if comment:
            first, _, rest = replacement.partition("\n")
            replacement = f"{first}  {comment}\n{rest}"
        edits.append(ImporterEdit(path, node.lineno, _end_line(node), replacement))
    return edits, blockers


def _text_reference_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for repo in sorted(workspace.glob(f"{PACKAGE_DIR_PREFIX}*")):
        if (repo / PYPROJECT_NAME).is_file():
            files.append(repo / PYPROJECT_NAME)
        src = repo / SRC_DIR_NAME
        if src.is_dir():
            files.extend(path for path in sorted(src.rglob("*")) if path.is_file() and path.suffix != ".pyc")
    return files


def plan_importers(
    original: str, moved: Mapping[str, str], skip: frozenset[Path], workspace: Path
) -> tuple[list[ImporterEdit], list[str]]:
    """Every importer edit the split needs, and every reason it cannot be completed."""
    edits: list[ImporterEdit] = []
    blockers: list[str] = []
    for path in scanned_files(workspace):
        if path.resolve() in skip:
            continue
        try:
            file_edits, file_blockers = _importer_edits(path, original, moved, workspace)
        except (SyntaxError, UnicodeDecodeError) as exc:
            blockers.append(f"{display_path(path, workspace)}: cannot be parsed to check its imports ({exc})")
            continue
        edits.extend(file_edits)
        blockers.extend(file_blockers)
    for path in _text_reference_files(workspace):
        if path.resolve() not in skip:
            blockers.extend(_text_references(path, original, moved, workspace))
    return edits, blockers


def apply_edits(edits: Sequence[ImporterEdit]) -> None:
    by_path: dict[Path, list[ImporterEdit]] = {}
    for edit in edits:
        by_path.setdefault(edit.path, []).append(edit)
    for path, file_edits in by_path.items():
        lines = source_lines(path)
        for edit in sorted(file_edits, key=lambda item: item.first_line, reverse=True):
            lines[edit.first_line - 1 : edit.last_line] = [edit.replacement]
        path.write_text("".join(lines), encoding=WRITE_ENCODING)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def package_module_for(path: Path, override: str | None) -> str:
    """The dotted package the split module lives in."""
    if override:
        return override
    parts = path.resolve().parts
    if SRC_DIR_NAME not in parts:
        raise SplitRefused(
            f"{path} is not under a src/ tree, so its package cannot be derived. Fix: pass -PackageModule "
            "(--package-module) with the dotted package the module is imported from (e.g. tests.unit.generators)."
        )
    index = len(parts) - parts[::-1].index(SRC_DIR_NAME)
    return ".".join(parts[index:-1])


def find_ruff() -> str:
    """The venv's ruff executable.

    Raises:
        SplitRefused: ruff is not installed beside the running interpreter.
    """
    ruff = shutil.which("ruff", path=str(Path(sys.executable).parent))
    if ruff is None:
        raise SplitRefused(f"ruff is not installed next to {sys.executable}. Fix: install the venv's dev tools.")
    return ruff


def run_ruff(ruff: str, paths: Sequence[Path]) -> None:
    command = [ruff, "check", "--select", RUFF_RULES, "--fix", "--quiet", *map(str, paths)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = result.stdout.strip() or result.stderr.strip()
    if output:
        print(f"ruff (exit {result.returncode}): {output}")


@dataclass(frozen=True)
class SplitPlan:
    """Everything the split will write, computed before anything is written."""

    target: Path
    outputs: dict[Path, str]
    remainder: str
    kept_count: int
    edits: list[ImporterEdit]
    blockers: list[str]


def prepare(args: argparse.Namespace, workspace: Path) -> SplitPlan:
    """Validate the plan and compute every file the split writes, the importers read from *workspace*.

    Raises:
        SplitRefused: The plan or the cut is invalid.
    """
    target: Path = args.module.resolve()
    if target.name == INIT_FILE_NAME:
        raise SplitRefused("Splitting a package __init__.py is not supported; move the definitions into a module first.")
    package = package_module_for(target, args.package_module)
    module = read_module(target)
    entries = load_plan(args.plan, module)
    assignment = assign(entries)
    provides = {name: stem for key, stem in assignment.items() for name in module.owner[key]}
    if target.stem in provides.values():
        raise SplitRefused(f"A new module may not take the original's name {target.stem!r}. Pick another stem.")
    homes = homes_of(module, provides, target.stem)
    _check_all(module, frozenset(provides))
    validate_cut(module, entries, homes, target.stem)
    clashes = [entry.stem for entry in entries if (target.parent / f"{entry.stem}.py").exists()]
    if clashes:
        raise SplitRefused(f"Module file(s) already exist: {clashes}. Pick new stems.")
    outputs = {target.parent / f"{entry.stem}.py": render_new_module(module, entry, homes, package) for entry in entries}
    skip = frozenset({target, *(path.resolve() for path in outputs)})
    edits, blockers = plan_importers(f"{package}.{target.stem}", provides, skip, workspace.resolve())
    return SplitPlan(
        target=target,
        outputs=outputs,
        remainder=render_remainder(module, homes, package, target.stem),
        kept_count=len(module.order) - len(assignment),
        edits=edits,
        blockers=blockers,
    )


def split(args: argparse.Namespace, workspace: Path) -> int:
    """Split ``args.module`` by ``args.plan``, rewriting the importers under *workspace*; returns the exit code."""
    plan = prepare(args, workspace)
    ruff = find_ruff()
    workspace = workspace.resolve()
    for path, content in plan.outputs.items():
        print(f"new module {path.name}: {len(content.splitlines())} lines")
    print(f"remainder {plan.target.name}: {plan.kept_count} definition(s) kept")
    for edit in plan.edits:
        print(f"rewrite {display_path(edit.path, workspace)}:{edit.first_line}")
    if plan.blockers:
        for blocker in plan.blockers:
            print(f"BLOCKED {blocker}")
        print(f"Refused: {len(plan.blockers)} reference(s) the rewrite cannot reach. Nothing was written.")
        return EXIT_REFUSED
    if args.dry_run:
        print("Dry run: nothing was written.")
        return EXIT_OK
    for path, content in plan.outputs.items():
        path.write_text(content, encoding=WRITE_ENCODING)
    plan.target.write_text(plan.remainder, encoding=WRITE_ENCODING)
    apply_edits(plan.edits)
    run_ruff(ruff, [plan.target, *plan.outputs])
    print(f"Split {plan.target.name} into {len(plan.outputs)} new module(s); rewrote {len(plan.edits)} import statement(s).")
    return EXIT_OK


def run_split(args: argparse.Namespace, workspace: Path) -> int:
    """The split, its refusal printed; returns the exit code."""
    if args.module is None or args.plan is None or not args.module.is_file() or not args.plan.is_file():
        raise UsageError(
            f"Expected an existing -Module file and -Plan file; got {args.module} and {args.plan}. "
            "Pass the .py file to split and the JSON plan naming its new modules."
        )
    try:
        return split(args, workspace)
    except SplitRefused as exc:
        print(f"Refused: {exc} Nothing was written.")
        return EXIT_REFUSED


def build_parser() -> argparse.ArgumentParser:
    """The options of ``codemods/split-module.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--module", type=Path, help="The .py file to split.")
    parser.add_argument("--plan", type=Path, help="The JSON plan (see the module docstring).")
    parser.add_argument("--package-module", help="Dotted package of the module when it is not under a src/ tree.")
    parser.add_argument("--dry-run", action="store_true", help="Print what the split would do; write nothing.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted module is split (dry run, then for real), and a bad plan "
                             "is refused.")
    parser.set_defaults(debug=False)
    return parser


_PLANTED_MODULE: Final = '"""Big."""\n\n\ndef alpha() -> int:\n    return 1\n\n\ndef beta() -> int:\n    return alpha() + 1\n'
_PLANTED_IMPORTER: Final = "from planted_pkg.big import alpha\n\nVALUE = alpha()\n"
_PLANTED_MUTUAL: Final = (
    '"""Big."""\n\n\ndef alpha(n: int) -> int:\n    return 0 if n == 0 else beta(n - 1)\n\n\n'
    "def beta(n: int) -> int:\n    return alpha(n)\n"
)


def _planted_workspace(root: Path, plan: Mapping[str, object], source: str = _PLANTED_MODULE) -> tuple[Path, Path, Path]:
    """A workspace holding one framework repo: the module to split, an importer of it, and the plan."""
    package = root / f"{PACKAGE_DIR_PREFIX}planted" / SRC_DIR_NAME / "planted_pkg"
    package.mkdir(parents=True)
    (package / INIT_FILE_NAME).write_text("", encoding=WRITE_ENCODING)
    module = package / "big.py"
    module.write_text(source, encoding=WRITE_ENCODING)
    (package / "user.py").write_text(_PLANTED_IMPORTER, encoding=WRITE_ENCODING)
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding=WRITE_ENCODING)
    return module, plan_path, package / "user.py"


def _quiet_split(argv: Sequence[str], workspace: Path) -> tuple[int, str]:
    with contextlib.redirect_stdout(io.StringIO()) as printed:
        code = run_split(build_parser().parse_args(argv), workspace)
    return code, printed.getvalue()


def _check_a_planted_module_is_split_and_its_importer_rewritten() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        module, plan, importer = _planted_workspace(root, {"_alpha": {PLAN_DOC_KEY: "Alpha.", PLAN_NAMES_KEY: ["alpha"]}})
        argv = [f"--module={module}", f"--plan={plan}"]
        code, text = _quiet_split([*argv, "--dry-run"], root)
        assert code == EXIT_OK and "Dry run: nothing was written." in text, text
        assert not (module.parent / "_alpha.py").exists() and importer.read_text(encoding=WRITE_ENCODING) == _PLANTED_IMPORTER
        code, text = _quiet_split(argv, root)
        assert code == EXIT_OK, text
        assert "def alpha" in (module.parent / "_alpha.py").read_text(encoding=WRITE_ENCODING)
        assert "from planted_pkg._alpha import alpha" in importer.read_text(encoding=WRITE_ENCODING), text
        assert "def alpha" not in module.read_text(encoding=WRITE_ENCODING)


def _check_moved_code_imports_what_stays_from_the_original() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        module, plan, importer = _planted_workspace(root, {"_beta": {PLAN_DOC_KEY: "Beta.", PLAN_NAMES_KEY: ["beta"]}})
        code, text = _quiet_split([f"--module={module}", f"--plan={plan}"], root)
        assert code == EXIT_OK, text
        moved = (module.parent / "_beta.py").read_text(encoding=WRITE_ENCODING)
        assert "from planted_pkg.big import alpha" in moved and "def beta" in moved, moved
        remainder = module.read_text(encoding=WRITE_ENCODING)
        assert "def alpha" in remainder and "_beta" not in remainder, remainder
        assert importer.read_text(encoding=WRITE_ENCODING) == _PLANTED_IMPORTER
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_spec = {"_beta": {PLAN_DOC_KEY: "Beta.", PLAN_NAMES_KEY: ["beta"]}}
        module, plan, _importer = _planted_workspace(root, plan_spec, _PLANTED_MUTUAL)
        code, text = _quiet_split([f"--module={module}", f"--plan={plan}"], root)
        assert code == EXIT_REFUSED and "import cycle" in text, text
        assert module.read_text(encoding=WRITE_ENCODING) == _PLANTED_MUTUAL and not (module.parent / "_beta.py").exists()


def _check_an_importer_with_a_form_feed_is_rewritten() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        module, plan, importer = _planted_workspace(root, {"_alpha": {PLAN_DOC_KEY: "Alpha.", PLAN_NAMES_KEY: ["alpha"]}})
        importer.write_text('"""Page one.\x0cPage two."""\n\n' + _PLANTED_IMPORTER, encoding=WRITE_ENCODING)
        code, text = _quiet_split([f"--module={module}", f"--plan={plan}"], root)
        assert code == EXIT_OK, text
        assert "from planted_pkg._alpha import alpha" in importer.read_text(encoding=WRITE_ENCODING), text


def _check_a_bad_plan_is_refused_and_nothing_written() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        module, plan, _importer = _planted_workspace(root, {"_gamma": {PLAN_DOC_KEY: "Gamma.", PLAN_NAMES_KEY: ["gamma"]}})
        code, text = _quiet_split([f"--module={module}", f"--plan={plan}"], root)
        assert code == EXIT_REFUSED and "Nothing was written." in text, text
        assert module.read_text(encoding=WRITE_ENCODING) == _PLANTED_MODULE and not (module.parent / "_gamma.py").exists()
    expect_usage_error(lambda: run_split(build_parser().parse_args([]), WORKSPACE_DIR), "-Module")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_module_is_split_and_its_importer_rewritten,
                  _check_moved_code_imports_what_stays_from_the_original,
                  _check_an_importer_with_a_form_feed_is_rewritten,
                  _check_a_bad_plan_is_refused_and_nothing_written]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=CODEMODS_SCRIPTS_DIR)
    return run_split(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
