"""Where a module, or names from it, are imported across the Datrix workspace.

Shared by ``dev\\find-imports.ps1`` (the report) and ``codemods\\split-module.ps1`` (which
rewrites every importer of a moved name), so both read the same files and resolve relative
imports the same way.

The scanned set is every ``.py`` file under each ``datrix-*`` repository's ``src/`` and
``tests/`` trees, its root-level ``*.py`` files (``conftest.py`` and the like), the scripts
tree and the Claude Code hooks -- discovered from disk, never listed.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.paths import SCRIPTS_DIR, SHOWCASE_DIR

PACKAGE_DIR_PREFIX: Final[str] = "datrix-"
SCANNED_SUBTREES: Final[tuple[str, ...]] = ("src", "tests")
HOOKS_DIR: Final[Path] = SHOWCASE_DIR / "claude-config" / ".claude" / "hooks"
SKIPPED_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {"build", ".venv", "node_modules", "__pycache__", ".generated", ".git", ".test_results"}
)
SRC_DIR_NAME: Final[str] = "src"
SOURCE_ENCODING: Final[str] = "utf-8-sig"


@dataclass(frozen=True)
class ImportSite:
    """One reference to a target module or one of its names."""

    path: Path
    line: int
    kind: str
    text: str


def _python_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.py")):
        if not SKIPPED_DIR_NAMES & set(path.relative_to(root).parts):
            yield path


def scanned_files(workspace: Path) -> list[Path]:
    """Every file the scanners read, discovered from disk."""
    files: list[Path] = []
    for repo in sorted(workspace.glob(f"{PACKAGE_DIR_PREFIX}*")):
        if not repo.is_dir():
            continue
        for subtree in SCANNED_SUBTREES:
            files.extend(_python_files(repo / subtree))
        files.extend(sorted(repo.glob("*.py")))
    files.extend(_python_files(SCRIPTS_DIR))
    files.extend(_python_files(HOOKS_DIR))
    return files


def current_package(path: Path) -> str | None:
    """The dotted package of a file under a ``src/`` tree, for resolving relative imports.

    ``pkg/sub/mod.py`` and ``pkg/sub/__init__.py`` alike live in ``pkg.sub``. ``None`` for a
    file outside any ``src/`` tree, whose relative imports are then left unresolved.
    """
    parts = path.parts
    if SRC_DIR_NAME not in parts:
        return None
    relative = parts[len(parts) - parts[::-1].index(SRC_DIR_NAME) :]
    return ".".join(relative[:-1]) or None


def resolve_from_module(node: ast.ImportFrom, package: str | None) -> str | None:
    """The absolute module an ``ImportFrom`` names, or ``None`` when it cannot be resolved."""
    if node.level == 0:
        return node.module
    if package is None:
        return None
    base = package.split(".")
    if node.level - 1 > len(base):
        return None
    anchor = base[: len(base) - (node.level - 1)]
    return ".".join([*anchor, node.module]) if node.module else ".".join(anchor)


class ModuleBindings:
    """The import statements of one file that bind a target module or names from it.

    ``from_imports`` holds every ``from M import ...`` whose absolute M is a target;
    ``module_aliases`` every local name bound to a target module (``import M``,
    ``import M as m``, ``from P import M``) with the statement that binds it.
    """

    def __init__(self, path: Path, tree: ast.Module, modules: frozenset[str]) -> None:
        self.from_imports: list[tuple[ast.ImportFrom, str]] = []
        self.module_aliases: dict[str, ast.Import | ast.ImportFrom] = {}
        package = current_package(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self._import(node, modules)
            elif isinstance(node, ast.ImportFrom):
                self._import_from(node, modules, package)

    def _import(self, node: ast.Import, modules: frozenset[str]) -> None:
        for alias in node.names:
            if alias.name in modules:
                self.module_aliases[alias.asname or alias.name] = node

    def _import_from(self, node: ast.ImportFrom, modules: frozenset[str], package: str | None) -> None:
        module = resolve_from_module(node, package)
        if module is None:
            return
        if module in modules:
            self.from_imports.append((node, module))
        for alias in node.names:
            if f"{module}.{alias.name}" in modules:
                self.module_aliases[alias.asname or alias.name] = node

    def attribute_reads(self, tree: ast.Module, names: frozenset[str]) -> list[ast.Attribute]:
        """Every ``alias.N`` read with N in *names* on a bound module alias."""
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in names
            and isinstance(node.value, ast.Name)
            and node.value.id in self.module_aliases
        ]


def parse_source(path: Path) -> ast.Module:
    """Parse *path*.

    Raises:
        SyntaxError, UnicodeDecodeError: The file cannot be parsed; the caller reports it.
    """
    return ast.parse(path.read_text(encoding=SOURCE_ENCODING), filename=str(path))


def sites_in(path: Path, modules: frozenset[str], names: frozenset[str]) -> list[ImportSite]:
    """Every import site in *path*: from-imports of a target module (narrowed to *names* when
    given), and -- without *names* -- the statements binding a target module, or -- with
    *names* -- the attribute reads of those names on a bound module.

    Raises:
        SyntaxError, UnicodeDecodeError: The file cannot be parsed; the caller reports it.
    """
    tree = parse_source(path)
    bindings = ModuleBindings(path, tree, modules)
    sites = [
        ImportSite(path, node.lineno, "from-import", ast.unparse(node))
        for node, _ in bindings.from_imports
        if not names or any(alias.name in names for alias in node.names)
    ]
    if names:
        sites.extend(
            ImportSite(path, node.lineno, "attribute", ast.unparse(node))
            for node in bindings.attribute_reads(tree, names)
        )
    else:
        bound = {id(node): node for node in bindings.module_aliases.values()}
        sites.extend(
            ImportSite(path, node.lineno, "import" if isinstance(node, ast.Import) else "module-import", ast.unparse(node))
            for node in bound.values()
        )
    return sorted(sites, key=lambda site: site.line)
