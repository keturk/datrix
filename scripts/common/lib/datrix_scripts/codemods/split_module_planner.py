"""Choose where to cut a module for ``split_module``, so a list of files needs no hand-written plans.

Top-level definitions are grouped by strongly connected component (a pytest fixture and the tests
that take it count as one, because a parameter is not an import), walked in dependency order and
filled into chunks. What must stay is the original's tail, so no chunk imports from the original:
``pytestmark``, ``__all__``, a group too big for one module, a definition that rebinds a ``global``, a
conftest fixture, and whatever depends on those.
"""

from __future__ import annotations

import ast
import heapq
import io
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

TARGET_LINES: Final[int] = 430
ONE_MODULE_MAX: Final[int] = 540
MIN_CHUNK_LINES: Final[int] = 40
BLANK_LINES_BETWEEN: Final[int] = 2
SAFE_FILE_LINES: Final[int] = 585
MAX_HEADER_ALLOWANCE: Final[int] = 120
MAX_SLUG_LENGTH: Final[int] = 34
MAX_BASE_LENGTH: Final[int] = 26
ALWAYS_STAYS: Final[frozenset[str]] = frozenset({"pytestmark", "__all__"})
INLINED_MARKS: Final[tuple[str, ...]] = ("inlined into", "inlined wherever", "is inlined")
OPENING_LINES: Final[int] = 40

_COUNTED_LINE: Final = re.compile(r"^\s*(\d+)\s+(\S+\.py)\s*$")
_PROJECT_LINE: Final = re.compile(r"^\[\d+/\d+\]\s+(\S+)")


class ReadModule(Protocol):
    """What the planner reads of a parsed module."""

    lines: list[str]
    header_end: int
    blocks: dict[str, str]
    owner: dict[str, list[str]]
    order: list[str]


@dataclass(frozen=True)
class Chunk:
    """One new module: its stem, docstring and definitions."""

    stem: str
    doc: str
    names: tuple[str, ...]


@dataclass(frozen=True)
class _Graph:
    """The module's definition groups and what each needs."""

    groups: list[list[str]]
    lines: list[int]
    needs: dict[int, set[int]]
    dependents: dict[int, set[int]]
    first_line: list[int]


def cannot_be_cut(path: Path, module: ReadModule) -> bool:
    """Whether generated projects carry this module's source verbatim, or the model generator writes it."""
    opening = "".join(module.lines[:OPENING_LINES]).lower()
    if path.parent.name == "datrix_model" and module.lines[0].startswith("from __future__"):
        return True
    return path.stem.endswith("_runtime") or path.parent.name == "runtime" or any(mark in opening for mark in INLINED_MARKS)


def _line_count(text: str) -> int:
    return text.count("\n") + 1


def _is_fixture(node: ast.stmt) -> bool:
    return any("fixture" in ast.unparse(decorator) for decorator in getattr(node, "decorator_list", []))


def _names_taken(tree: ast.Module) -> set[str]:
    """Every parameter a block's functions take and every name its ``usefixtures`` marks ask for."""
    taken: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            taken.update(arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
        elif isinstance(node, ast.Call) and "usefixtures" in ast.unparse(node.func):
            taken.update(str(arg.value) for arg in node.args if isinstance(arg, ast.Constant))
    return taken


def _fixture_ties(blocks: Mapping[str, str]) -> dict[str, set[str]]:
    """{fixture block: the blocks that take it as a parameter}."""
    trees = {key: ast.parse(block) for key, block in blocks.items()}
    fixtures = [key for key, tree in trees.items() if any(_is_fixture(node) for node in tree.body)]
    taken = {key: _names_taken(tree) for key, tree in trees.items()}
    return {fixture: {key for key in trees if key != fixture and fixture in taken[key]} for fixture in fixtures}


def _reachable(start: str, uses: Mapping[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    pending = list(uses[start])
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(uses[node])
    return seen


def _components(keys: Sequence[str], uses: Mapping[str, set[str]]) -> list[list[str]]:
    """The strongly connected components: a key and everything that both reaches it and is reached."""
    reach = {key: _reachable(key, uses) for key in keys}
    placed: set[str] = set()
    groups: list[list[str]] = []
    for key in keys:
        if key not in placed:
            group = [other for other in keys if other == key or (other in reach[key] and key in reach[other])]
            placed.update(group)
            groups.append(group)
    return groups


def _graph(module: ReadModule, uses: Mapping[str, set[str]]) -> _Graph:
    groups = _components(module.order, uses)
    group_of = {key: number for number, group in enumerate(groups) for key in group}
    needs: dict[int, set[int]] = {number: set() for number in range(len(groups))}
    dependents: dict[int, set[int]] = {number: set() for number in range(len(groups))}
    for key, others in uses.items():
        for other in others:
            if group_of[key] != group_of[other]:
                needs[group_of[key]].add(group_of[other])
                dependents[group_of[other]].add(group_of[key])
    position = {key: number for number, key in enumerate(module.order)}
    return _Graph(
        groups=groups,
        lines=[sum(_line_count(module.blocks[key]) + BLANK_LINES_BETWEEN for key in group) for group in groups],
        needs=needs,
        dependents=dependents,
        first_line=[min(position[key] for key in group) for group in groups],
    )


def _rebinding_blocks(module: ReadModule) -> set[str]:
    """Every block that rebinds a ``global``, and the block that defines each such name."""
    owner = {name: key for key, names in module.owner.items() for name in names}
    keys: set[str] = set()
    for key, block in module.blocks.items():
        for node in ast.walk(ast.parse(block)):
            if isinstance(node, ast.Global):
                keys.add(key)
                keys.update(owner[name] for name in node.names if name in owner)
    return keys


def _pinned(path: Path, module: ReadModule, fixtures: Mapping[str, set[str]], graph: _Graph) -> set[int]:
    """The groups that stay in the original, closed over what depends on them."""
    stays = {key for key in module.order if key in ALWAYS_STAYS} | _rebinding_blocks(module)
    if path.name == "conftest.py":
        stays |= set(fixtures)
    pinned = {number for number, group in enumerate(graph.groups) if stays & set(group)}
    pinned |= {number for number, size in enumerate(graph.lines) if size > ONE_MODULE_MAX}
    frontier = list(pinned)
    while frontier:
        fresh = graph.dependents[frontier.pop()] - pinned
        pinned |= fresh
        frontier.extend(fresh)
    return pinned


def _dependency_order(graph: _Graph, pinned: set[int]) -> list[int]:
    """Every group after what it needs, the pinned ones last, source order as the tiebreak."""
    waiting = {number: len(needs) for number, needs in graph.needs.items()}
    heap = [(number in pinned, graph.first_line[number], number) for number, count in waiting.items() if count == 0]
    heapq.heapify(heap)
    walk: list[int] = []
    while heap:
        group = heapq.heappop(heap)[2]
        walk.append(group)
        for dependent in graph.dependents[group]:
            waiting[dependent] -= 1
            if waiting[dependent] == 0:
                heapq.heappush(heap, (dependent in pinned, graph.first_line[dependent], dependent))
    return walk


def _fill(walk: Sequence[int], pinned: set[int], lines: Sequence[int], stay_limit: int) -> list[list[int]]:
    """Fill chunks in walk order until what is left fits the original."""
    remaining = sum(lines)
    picked: list[list[int]] = [[]]
    filled = 0
    for group in walk:
        if group in pinned or (remaining <= stay_limit and (not picked[-1] or filled >= MIN_CHUNK_LINES)):
            break
        if filled >= TARGET_LINES or (picked[-1] and filled + lines[group] > ONE_MODULE_MAX):
            picked.append([])
            filled = 0
        picked[-1].append(group)
        filled += lines[group]
        remaining -= lines[group]
    return [chunk for chunk in picked if sum(lines[group] for group in chunk) >= MIN_CHUNK_LINES]


def _slug(names: Sequence[str], blocks: Mapping[str, str]) -> str:
    largest = max(names, key=lambda name: _line_count(blocks[name]))
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", re.sub(r"\W", "", largest)).lower().strip("_")
    return re.sub(r"^(test_|build_|get_|make_)", "", snake)[:MAX_SLUG_LENGTH].strip("_")


def _chunk_of(path: Path, names: tuple[str, ...], blocks: Mapping[str, str], taken: set[str]) -> Chunk:
    base = path.stem.removeprefix("test_").strip("_")[:MAX_BASE_LENGTH].strip("_")
    slug = _slug(names, blocks)
    holds_tests = any(name.startswith(("Test", "test_")) for name in names)
    stem = f"test_{base}_{slug}" if holds_tests else f"{base}_{slug}_support" if "tests" in path.parts else f"_{base}_{slug}"
    suffix = 2
    candidate = stem
    while candidate in taken or path.with_name(f"{candidate}.py").exists():
        candidate = f"{stem}_{suffix}"
        suffix += 1
    taken.add(candidate)
    words = slug.replace("_", " ")
    return Chunk(candidate, f"Tests for {words}." if holds_tests else f"The {words} part of ``{path.stem}``.", names)


def plan_cut(path: Path, module: ReadModule, names_used: Callable[[str], set[str]]) -> list[Chunk]:
    """The chunks that take *module* under the limit, or as far under it as what must stay allows."""
    owner = {name: key for key, names in module.owner.items() for name in names}
    uses = {key: {owner[name] for name in names_used(module.blocks[key]) if name in owner} - {key} for key in module.order}
    fixtures = _fixture_ties(module.blocks)
    for fixture, takers in fixtures.items():
        uses[fixture] |= takers
        for taker in takers:
            uses[taker].add(fixture)
    graph = _graph(module, uses)
    pinned = _pinned(path, module, fixtures, graph)
    stay_limit = SAFE_FILE_LINES - min(module.header_end, MAX_HEADER_ALLOWANCE)
    picked = _fill(_dependency_order(graph, pinned), pinned, graph.lines, stay_limit)
    if sum(len(numbers) for numbers in picked) == len(graph.groups):
        picked = picked[:-1]
    position ={key: number for number, key in enumerate(module.order)}
    taken: set[str] = set()
    return [
        _chunk_of(
            path,
            tuple(sorted((key for number in numbers for key in graph.groups[number]), key=position.__getitem__)),
            module.blocks,
            taken,
        )
        for numbers in picked
    ]


def _tied_to_self(member: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A helper, or a test that reaches one through ``self``: these stay together in the first class."""
    used = (node for statement in member.body for node in ast.walk(statement))
    return not member.name.startswith("test_") or any(isinstance(node, ast.Name) and node.id == "self" for node in used)


def _class_parts(node: ast.ClassDef, lines: Sequence[str]) -> list[str] | None:
    """*node* as classes of about ``TARGET_LINES`` each, or None when it holds more than methods."""
    has_doc = ast.get_docstring(node) is not None
    members = node.body[1:] if has_doc else node.body
    if not all(isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) for member in members):
        return None
    head_end = node.body[0].end_lineno if has_doc else node.lineno
    starts = [head_end, *(member.end_lineno for member in members[:-1])]
    blocks = [(_tied_to_self(member), "".join(lines[start : member.end_lineno]).lstrip("\r\n")) for start, member in zip(starts, members)]
    parts: list[list[str]] = [[]]
    filled = 0
    for _tied, block in sorted(blocks, key=lambda item: not item[0]):
        size = _line_count(block) + 1
        if parts[-1] and filled + size > TARGET_LINES:
            parts.append([])
            filled = 0
        parts[-1].append(block)
        filled += size
    first_line = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
    decorators = "".join(lines[first_line - 1 : node.lineno - 1])
    rendered: list[str] = []
    for number, part in enumerate(parts, start=1):
        name = node.name if number == 1 else f"{node.name}Part{number}"
        doc = "".join(lines[node.lineno : head_end]) if number == 1 else f'    """``{node.name}``, continued."""\n'
        rendered.append(f"{decorators}{lines[node.lineno - 1].replace(node.name, name, 1)}{doc}\n" + "\n".join(part))
    return rendered


def cut_test_classes(text: str) -> str:
    """Cut every ``Test*`` class too big for one module at its method boundaries, so the cut can move the parts."""
    lines = io.StringIO(text, newline="").readlines()
    for node in reversed(ast.parse(text).body):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test") and node.end_lineno - node.lineno + 1 > ONE_MODULE_MAX:
            parts = _class_parts(node, lines)
            first_line = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            if parts:
                lines[first_line - 1 : node.end_lineno] = ["\n\n".join(parts)]
    return "".join(lines)


def listed_files(text: str, limit: int, workspace: Path) -> list[Path]:
    """The files at *limit* lines or more in ``large-files.ps1`` output, in the order listed."""
    project = ""
    found: list[Path] = []
    for line in text.splitlines():
        header = _PROJECT_LINE.match(line)
        counted = _COUNTED_LINE.match(line)
        if header:
            project = header.group(1)
        elif counted and project and int(counted.group(1)) >= limit:
            found.append(workspace / project / counted.group(2))
    return found
