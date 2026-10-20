"""The git forms no git script may run: stash, reset, checkout, revert and restore.

Each of them discards or rewrites local work that no script can tell is safe to lose (another task's
uncommitted edits, a merge in progress), so the git scripts report a blocked pull or a dirty tree and
leave the decision to a person (``/resolve-conflicts``). Every git call a git script makes is an argument
vector, so a forbidden form would appear as a string literal equal to its verb (``["git", "stash",
"push"]``); ``forbidden_git_calls`` finds every such literal by reading a module's syntax tree. A git
script runs its own module and every ``datrix_scripts`` module it imports (the isolation, ignored-source
and lint scans of commit-and-push run git themselves), so ``package_git_calls`` reads the
``datrix_scripts.git`` modules and every ``datrix_scripts`` module they import, directly or through
another, at module scope or inside a function. Each git module's ``--self-test`` runs
``check_no_git_script_runs_a_forbidden_form`` over that set.
"""

from __future__ import annotations

import ast
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Final

FORBIDDEN_GIT_VERBS: Final = frozenset({"stash", "reset", "checkout", "revert", "restore"})
#: A verb every git script that pushes carries; the census finds it when asked to, so a clean verdict
#: is not a matcher that reads nothing.
_KNOWN_VERB: Final = "push"
_PACKAGE_DIR: Final = Path(__file__).resolve().parent
_ROOT_PACKAGE: Final = "datrix_scripts"
_INIT: Final = "__init__.py"
_PLANTED_CALL: Final = 'import subprocess\nsubprocess.run(["git", "-C", "repo", "stash", "push"], check=True)\n'
_PLANTED_PROSE: Final = '"""A blocked pull is reported; nothing runs git stash or git checkout."""\n'
#: A git module whose forbidden call sits in a helper it imports inside a function, two packages away.
_PLANTED_IMPORTER: Final = 'def run() -> None:\n    from datrix_scripts.shared import helper\n    helper.run()\n'
_PLANTED_HELPER_PATH: Final = "datrix_scripts/shared/helper.py"


def forbidden_git_calls(source: str, filename: str, verbs: Iterable[str] = FORBIDDEN_GIT_VERBS) -> list[str]:
    """``<file>:<line>: "<verb>"`` for every string literal in *source* equal to one of *verbs*.

    Raises:
        SyntaxError: *source* does not parse (the census fails closed).
    """
    wanted = frozenset(verbs)
    return [
        f"{filename}:{node.lineno}: {node.value!r}"
        for node in ast.walk(ast.parse(source, filename=filename))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in wanted
    ]


def _module_file(lib_root: Path, dotted: str) -> Path | None:
    """The file of *dotted* under *lib_root* (a module, or a package's ``__init__.py``); None when neither exists,
    as for a name imported from a module rather than a submodule."""
    base = lib_root.joinpath(*dotted.split("."))
    for candidate in (base.with_suffix(".py"), base / _INIT):
        if candidate.is_file():
            return candidate
    return None


def _module_name(lib_root: Path, module_file: Path) -> str:
    parts = module_file.relative_to(lib_root).with_suffix("").parts
    return ".".join(parts[:-1] if module_file.name == _INIT else parts)


def _imported_names(tree: ast.Module, module: str, is_package: bool) -> Iterator[str]:
    """Every dotted name an import in *tree* (of *module*) may load: each module, and each ``from`` name as a
    possible submodule; a relative import resolved against *module*'s package."""
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ".".join(package.split(".")[: len(package.split(".")) - node.level + 1]) if node.level else ""
            source = ".".join(part for part in (base, node.module or "") if part)
            yield source
            yield from (f"{source}.{alias.name}" for alias in node.names)


def _reached_modules(package_dir: Path) -> list[Path]:
    """The modules of *package_dir* and every ``datrix_scripts`` module they import, transitively."""
    lib_root = package_dir.parent.parent
    pending = sorted(package_dir.glob("*.py"))
    reached: dict[Path, None] = {}
    while pending:
        module_file = pending.pop().resolve()
        if module_file in reached:
            continue
        reached[module_file] = None
        tree = ast.parse(module_file.read_text(encoding="utf-8"), filename=str(module_file))
        names = _imported_names(tree, _module_name(lib_root, module_file), module_file.name == _INIT)
        pending.extend(
            found for name in names
            if name.split(".")[0] == _ROOT_PACKAGE and (found := _module_file(lib_root, name)) is not None
        )
    return sorted(reached)


def package_git_calls(verbs: Iterable[str] = FORBIDDEN_GIT_VERBS, package_dir: Path = _PACKAGE_DIR) -> list[str]:
    """``forbidden_git_calls`` over every module a git script runs: the modules of *package_dir* and every
    ``datrix_scripts`` module they import, this census excluded. Each hit is named by its path under the
    ``lib`` folder that holds ``datrix_scripts``."""
    lib_root = package_dir.resolve().parent.parent
    census = Path(__file__).resolve()
    found: list[str] = []
    for module_file in _reached_modules(package_dir.resolve()):
        if module_file != census:
            name = module_file.relative_to(lib_root).as_posix()
            found.extend(forbidden_git_calls(module_file.read_text(encoding="utf-8"), name, verbs))
    return found


def _planted_import_is_followed() -> list[str]:
    """The census over a planted package whose git module imports, inside a function, a helper that runs stash."""
    with tempfile.TemporaryDirectory() as raw:
        lib_root = Path(raw)
        files = {
            f"{_ROOT_PACKAGE}/{_INIT}": "",
            f"{_ROOT_PACKAGE}/git/{_INIT}": "",
            f"{_ROOT_PACKAGE}/git/planted.py": _PLANTED_IMPORTER,
            f"{_ROOT_PACKAGE}/shared/{_INIT}": "",
            _PLANTED_HELPER_PATH: _PLANTED_CALL,
        }
        for relative, text in files.items():
            path = lib_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return package_git_calls(package_dir=lib_root / _ROOT_PACKAGE / "git")


def check_no_git_script_runs_a_forbidden_form() -> None:
    """No module a git script runs holds a forbidden form; the census finds a planted one, follows an import to
    a planted helper, finds a verb the package does use, and does not read prose that names a forbidden form."""
    planted = forbidden_git_calls(_PLANTED_CALL, "planted.py")
    assert planted == ["planted.py:2: 'stash'"], planted
    assert forbidden_git_calls(_PLANTED_PROSE, "prose.py") == [], "the census read a docstring as a git call"
    followed = _planted_import_is_followed()
    assert followed == [f"{_PLANTED_HELPER_PATH}:2: 'stash'"], (
        f"the census did not follow a git module's import to the helper that runs stash: {followed}"
    )
    assert package_git_calls({_KNOWN_VERB}), (
        f"the census found no {_KNOWN_VERB!r} literal in the modules {_PACKAGE_DIR} runs, where commit_and_push "
        "pushes: it reads nothing, so its clean verdict proves nothing"
    )
    violations = package_git_calls()
    assert not violations, (
        "a git script runs a form that discards or rewrites local work (stash, reset, checkout, revert, restore): "
        + "; ".join(violations)
        + ". Expected none: report the blocked state and leave the decision to /resolve-conflicts."
    )
