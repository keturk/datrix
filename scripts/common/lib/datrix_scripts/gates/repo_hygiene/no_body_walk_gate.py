"""No-body-walk gate: a generator function walks a model body only where the allowlist says so.

Analysis records what a body reads, calls, writes and resolves (``datrix_common.datrix_model``
``effects`` / ``usage`` / ``reads`` / ``resolution``); a generator reads those facts instead of
walking the body again. The few functions that still walk one -- a renderer emitting each child, a
local syntax question, a transpiler decision, a literal search, code analysis records no facts on --
are named in ``scripts/config/no_body_walk_allowlist.json`` with a category and a reason.

WHAT IS FLAGGED (syntactic, by ``ast``; receiver types are never inferred). In every ``*.py`` under
``datrix-codegen-*/src/`` (globbed from the workspace root, so a new target repository is covered
the moment it exists), a call of:

  * a walk function, by bare name or as an attribute: ``iter_tree``, ``iter_expressions``,
    ``walk_expression``, ``expression_children``, ``find_call_nodes``, ``iter_ast_walk_edges``,
    ``iter_body_nodes``;
  * a walk method ``.walk()``, ``.child_nodes()``, ``.children()``, ``.child_expressions()`` or
    ``.child_statements()``, unless its receiver is the bare name ``ast`` or ``os`` (a walk of
    generated Python source or of a directory tree, not of the model);
  * ``getattr(<x>, "<method>")`` naming one of those five methods.

A function that recurses over expression fields by ``isinstance`` dispatch, without any of those
calls, is not flagged. The unit is the innermost enclosing ``def``: ``<path>::<function>``, with
``<path>`` relative to the workspace root and ``<module>`` for module level.

PASSES when flagged - allowlist and allowlist - flagged are both empty: a stale entry fails too, so
the list only shrinks when the code it names is removed. ``guard-code-standards.py`` imports
:func:`function_walks` and :func:`load_allowlist` to refuse an edit that adds a flagged call to a
function the list does not name.

Built-in non-vacuity self-test, every invocation: an embedded source holding one call of every
flagged form, plus an ``ast.walk`` and an ``os.walk``, must flag exactly the former.

Run it through ``gates/repo-hygiene/no-body-walk-gate.ps1`` or its ``.sh`` twin; it runs in gate mode
(``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] no-body-walk PASSED|FAILED exit=<n> log=<path>`` verdict last.

Exit codes: 0 = pass, 1 = a difference, 2 = the gate cannot judge (self-test failed, malformed
allowlist, a source file that does not parse or cannot be read).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, print_command
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import CONFIG_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "no-body-walk"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.no_body_walk_gate"
WRAPPER: Final = "no-body-walk-gate"

WALK_FUNCTIONS: Final[frozenset[str]] = frozenset({
    "iter_tree", "iter_expressions", "walk_expression", "expression_children", "find_call_nodes",
    "iter_ast_walk_edges", "iter_body_nodes",
})
WALK_METHODS: Final[frozenset[str]] = frozenset({
    "walk", "child_nodes", "children", "child_expressions", "child_statements",
})
# Receivers whose walk method reads generated Python source or a directory tree, not the model.
EXCLUDED_RECEIVERS: Final[frozenset[str]] = frozenset({"ast", "os"})
CATEGORIES: Final[frozenset[str]] = frozenset({
    "render-traversal", "emission-syntax", "emission-decision", "literal-content", "no-facts-boundary",
})
MODULE_UNIT: Final[str] = "<module>"
SITE_SEPARATOR: Final[str] = "::"
SOURCE_ROOT_GLOB: Final[str] = "datrix-codegen-*/src"
ALLOWLIST_PATH: Final[Path] = CONFIG_DIR / "no_body_walk_allowlist.json"
_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"site", "category", "reason"})

_EXIT_OK: Final[int] = 0
_EXIT_DIFFERENCE: Final[int] = 1
_EXIT_GATE_BROKEN: Final[int] = 2


@dataclass(frozen=True)
class WalkCall:
    """One flagged call: its line and the form that flagged it."""

    line: int
    form: str

    def __str__(self) -> str:
        return f"{self.form}@{self.line}"


@dataclass(frozen=True)
class AllowEntry:
    """One allowlisted site and why it may walk a body."""

    site: str
    category: str
    reason: str


class AllowlistError(ValueError):
    """The allowlist file is not the documented array of entries."""


def _excluded_receiver(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Name) and receiver.id in EXCLUDED_RECEIVERS


def _getattr_form(node: ast.Call) -> str | None:
    if len(node.args) < 2:
        return None
    name = node.args[1]
    if isinstance(name, ast.Constant) and isinstance(name.value, str) and name.value in WALK_METHODS:
        return f'getattr(_, "{name.value}")'
    return None


def call_form(node: ast.Call) -> str | None:
    """The flagged form of ``node`` (``iter_tree()``, ``.walk()``, ``getattr(_, "children")``), or None."""
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in WALK_FUNCTIONS:
            return f"{func.id}()"
        return _getattr_form(node) if func.id == "getattr" else None
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr in WALK_FUNCTIONS:
        return f".{func.attr}()"
    if func.attr in WALK_METHODS and not _excluded_receiver(func.value):
        return f".{func.attr}()"
    return None


class _UnitVisitor(ast.NodeVisitor):
    """Collects the flagged calls of a module by innermost enclosing ``def``."""

    def __init__(self) -> None:
        self._stack: list[str] = []
        self.calls: dict[str, list[WalkCall]] = {}

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Call(self, node: ast.Call) -> None:
        form = call_form(node)
        if form is not None:
            unit = self._stack[-1] if self._stack else MODULE_UNIT
            self.calls.setdefault(unit, []).append(WalkCall(node.lineno, form))
        self.generic_visit(node)


def function_walks(source: str) -> dict[str, list[WalkCall]]:
    """The flagged calls of ``source`` by unit name; raises ``SyntaxError`` when it does not parse."""
    visitor = _UnitVisitor()
    visitor.visit(ast.parse(source))
    return visitor.calls


def site(relative_path: str, unit: str) -> str:
    """The allowlist key of ``unit`` in the workspace-relative posix ``relative_path``."""
    return f"{relative_path}{SITE_SEPARATOR}{unit}"


def _entry(item: object, index: int, path: Path) -> AllowEntry:
    if not isinstance(item, dict) or set(item) != _ENTRY_KEYS:
        raise AllowlistError(
            f"{path}: entry {index} must be an object with exactly the keys {sorted(_ENTRY_KEYS)}; "
            f"found {item!r}. Fix the entry."
        )
    values = [item[key] for key in ("site", "category", "reason")]
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise AllowlistError(f"{path}: entry {index} needs non-empty string site, category and reason; found {item!r}.")
    entry_site, category, reason = values
    if SITE_SEPARATOR not in entry_site:
        raise AllowlistError(f"{path}: entry {index} site {entry_site!r} must read '<path>::<function>'.")
    if category not in CATEGORIES:
        raise AllowlistError(
            f"{path}: entry {index} ({entry_site}) has category {category!r}; expected one of "
            f"{sorted(CATEGORIES)}. A new category is a design change that needs Jon's approval."
        )
    return AllowEntry(entry_site, category, reason)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, AllowEntry]:
    """The allowlist by site; raises ``AllowlistError`` (or ``OSError``) when it cannot be read as documented."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AllowlistError(f"{path}: not valid JSON ({error}). Expected an array of entries.") from error
    if not isinstance(raw, list):
        raise AllowlistError(f"{path}: expected a JSON array of entries, found {type(raw).__name__}.")
    entries: dict[str, AllowEntry] = {}
    for index, item in enumerate(raw):
        entry = _entry(item, index, path)
        if entry.site in entries:
            raise AllowlistError(f"{path}: site {entry.site} is listed twice; keep one entry.")
        entries[entry.site] = entry
    return entries


def source_files(workspace: Path) -> list[Path]:
    """Every ``*.py`` under every ``datrix-codegen-*/src`` of ``workspace``, sorted."""
    roots = [root for root in sorted(workspace.glob(SOURCE_ROOT_GLOB)) if root.is_dir()]
    return [path for root in roots for path in sorted(root.rglob("*.py"))]


def scan(workspace: Path) -> tuple[dict[str, list[WalkCall]], list[str]]:
    """The flagged calls by site, and one message per source file that could not be judged."""
    flagged: dict[str, list[WalkCall]] = {}
    broken: list[str] = []
    for path in source_files(workspace):
        relative = path.relative_to(workspace).as_posix()
        try:
            walks = function_walks(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as error:
            broken.append(f"{relative}: cannot be parsed ({error}); the gate cannot judge it")
            continue
        for unit, calls in walks.items():
            flagged[site(relative, unit)] = calls
    return flagged, broken


@dataclass(frozen=True)
class Difference:
    """Flagged sites the allowlist does not name, and entries that name no flagged site."""

    unlisted: dict[str, list[WalkCall]]
    stale: list[AllowEntry]

    def __bool__(self) -> bool:
        return bool(self.unlisted or self.stale)


def compare(flagged: dict[str, list[WalkCall]], allowlist: dict[str, AllowEntry]) -> Difference:
    """flagged - allowlist and allowlist - flagged."""
    unlisted = {key: calls for key, calls in sorted(flagged.items()) if key not in allowlist}
    stale = [entry for key, entry in sorted(allowlist.items()) if key not in flagged]
    return Difference(unlisted, stale)


# One call of every flagged form, each in its own function, plus the two excluded receivers.
_SELF_TEST_SOURCE: Final[str] = '''\
import ast
import os

iter_tree(ROOT)


def f_iter_tree(node):
    return iter_tree(node)


def f_iter_expressions(node):
    return iter_expressions(node)


def f_walk_expression(node):
    return walk_expression(node)


def f_expression_children(node):
    return expression_children(node)


def f_find_call_nodes(node):
    return find_call_nodes(node)


def f_iter_ast_walk_edges(node):
    return iter_ast_walk_edges(node)


def f_iter_body_nodes(node):
    return model.iter_body_nodes(node)


def m_walk(node):
    return node.walk()


def m_child_nodes(node):
    return node.child_nodes()


def m_children(context, element):
    return context.children(element.children)


def m_child_expressions(node):
    return node.child_expressions()


def m_child_statements(node):
    return self.node.child_statements()


def g_child_nodes(node):
    return getattr(node, "child_nodes", None)


def outer(node):
    def inner(child):
        return child.walk()
    return inner(node)


def x_ast(tree):
    return list(ast.walk(tree))


def x_os(root):
    return list(os.walk(root))


def x_isinstance_recursion(expr):
    return [x_isinstance_recursion(arg) for arg in expr.arguments] if hasattr(expr, "arguments") else []


def x_getattr_other(node):
    return getattr(node, "name")
'''

_SELF_TEST_EXPECTED: Final[dict[str, list[str]]] = {
    MODULE_UNIT: ["iter_tree()"],
    "f_iter_tree": ["iter_tree()"],
    "f_iter_expressions": ["iter_expressions()"],
    "f_walk_expression": ["walk_expression()"],
    "f_expression_children": ["expression_children()"],
    "f_find_call_nodes": ["find_call_nodes()"],
    "f_iter_ast_walk_edges": ["iter_ast_walk_edges()"],
    "f_iter_body_nodes": [".iter_body_nodes()"],
    "m_walk": [".walk()"],
    "m_child_nodes": [".child_nodes()"],
    "m_children": [".children()"],
    "m_child_expressions": [".child_expressions()"],
    "m_child_statements": [".child_statements()"],
    "g_child_nodes": ['getattr(_, "child_nodes")'],
    "inner": [".walk()"],
}


def self_test() -> list[str]:
    """Problems with the matcher and the comparison; empty when both work."""
    walks = function_walks(_SELF_TEST_SOURCE)
    found = {unit: [call.form for call in calls] for unit, calls in walks.items()}
    problems = [f"{unit}: expected {forms}, flagged {found[unit] if unit in found else 'nothing'}"
                for unit, forms in _SELF_TEST_EXPECTED.items() if unit not in found or found[unit] != forms]
    problems += [f"{unit}: flagged {forms}, expected nothing" for unit, forms in found.items()
                 if unit not in _SELF_TEST_EXPECTED]
    flagged = {site("pkg/mod.py", unit): calls for unit, calls in walks.items()}
    kept = site("pkg/mod.py", "m_walk")
    allowlist = {kept: AllowEntry(kept, "render-traversal", "self-test"),
                 "pkg/mod.py::gone": AllowEntry("pkg/mod.py::gone", "render-traversal", "self-test")}
    difference = compare(flagged, allowlist)
    if kept in difference.unlisted or len(difference.unlisted) != len(flagged) - 1:
        problems.append(f"compare: unlisted sites wrong: {sorted(difference.unlisted)}")
    if [entry.site for entry in difference.stale] != ["pkg/mod.py::gone"]:
        problems.append(f"compare: stale entries wrong: {[entry.site for entry in difference.stale]}")
    return problems


def _print_difference(difference: Difference, allowlist_path: Path) -> None:
    for key, calls in difference.unlisted.items():
        print(f"UNLISTED {key}  {', '.join(str(call) for call in calls)}")
    for entry in difference.stale:
        print(f"STALE    {entry.site}  ({entry.category}) no flagged call remains there")
    if difference.unlisted:
        print("\nAn unlisted function walks a model body. Read the facts analysis records instead "
              "(datrix_common.datrix_model effects / usage / reads / resolution). A walk that is "
              f"genuinely one of the categories {sorted(CATEGORIES)} is added to {allowlist_path} "
              "with Jon's approval; a new category is a design change.")
    if difference.stale:
        print(f"\nRemove each stale entry from {allowlist_path}: the code it named is gone.")


def run_gate(workspace: Path, allowlist_path: Path) -> int:
    """Compare the flagged sites of ``workspace`` with the allowlist; print every difference."""
    try:
        allowlist = load_allowlist(allowlist_path)
    except (AllowlistError, OSError) as error:
        print(f"BROKEN {error}")
        return _EXIT_GATE_BROKEN
    flagged, broken = scan(workspace)
    for message in broken:
        print(f"BROKEN {message}")
    if broken:
        return _EXIT_GATE_BROKEN
    difference = compare(flagged, allowlist)
    _print_difference(difference, allowlist_path)
    print(f"{len(flagged)} flagged function(s), {len(allowlist)} allowlisted, "
          f"{len(difference.unlisted)} unlisted, {len(difference.stale)} stale")
    return _EXIT_DIFFERENCE if difference else _EXIT_OK


def _check_matcher_and_comparison() -> None:
    problems = self_test()
    assert not problems, "\n".join(problems)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/no-body-walk-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="A generator function walks a model body only where the allowlist says so.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam checks."
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.debug:
        print_command()
    if args.self_test:
        return wrappers.run_self_test(
            [_check_matcher_and_comparison],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    problems = self_test()
    for problem in problems:
        print(f"SELF-TEST FAIL {problem}")
    if problems:
        print("No-body-walk gate self-test failed: the matcher cannot tell a body walk from other code.")
        return _EXIT_GATE_BROKEN
    print("self-test passed: every flagged form fires; ast.walk, os.walk and isinstance recursion do not")
    return run_gate(WORKSPACE_DIR, ALLOWLIST_PATH)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
