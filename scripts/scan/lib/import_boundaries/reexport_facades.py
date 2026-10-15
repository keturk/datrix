"""Re-export facade scanner (hard zero, no baseline)."""

from __future__ import annotations

import ast
import functools
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.paths import PACKAGE_DIR as SCRIPTS_PACKAGE_DIR
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_SCRIPT,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    self_test_check,
)
from import_boundaries._module_resolution import (
    _TEST_TREE_ROOT,
    _absolute_import_module,
    _dotted_module_name_for_file,
    _is_datrix_module_path,
    _is_policed_module_path,
    _is_submodule_member,
    _owning_package,
    _resolve_datrix_module,
    _resolve_policed_module,
    _ResolvedDatrixModule,
)
from import_boundaries.taxonomy import LANGUAGES_ENTRY_POINT_GROUP

# ---------------------------------------------------------------------------
# Re-export facade ratchet: a name has exactly one import path.
#
# Opt-in via --check-reexport-facades, it AST-scans every discovered
# package's src/ and tests/ trees (discover_packages() -- the same set every
# other whole-workspace ratchet in this file uses), every .py file under this
# repo's own datrix/scripts/ tree, and every .py file under
# datrix/claude-config/.claude/hooks/ (if any), for the shapes of re-export
# facade -- a name with a second, redundant import path on top of its real,
# single home -- all attributed to the PROVIDING module (the module through
# which the second path runs), never to the file where a consumer statement
# happens to appear. A providing module is a Datrix module or a test-tree
# module (``tests.<module>``, anchored at the importing file's own package).
# Shapes 1 and 2 follow; the module-object, entry-point and unresolved shapes
# are described below them:
#
# 1. Provider side. A module whose top-level `from <datrix module> import N`
#    binds a name N that is listed in the module's own __all__, or imported
#    as `N as N`, while the module does not itself define N ("defines" means
#    a top-level def/class/assignment target, including under a top-level
#    if/try -- an if is walked on both branches unconditionally, so a name
#    defined only under `if TYPE_CHECKING: ... else: ...` still counts as
#    defined).
# 2. Consumer side. Any `from M import N` anywhere in a scanned file (not
#    only at module top) where M is a Datrix module that does not define N,
#    and N does not itself resolve to a submodule of M (`from pkg import
#    submodule` is a normal package traversal, never a facade hit).
#
# Module-object shape. A module held as an object (`import a.b as m`,
# `from a import b`) whose attribute is read as `m.attr` or `getattr(m,
# "attr")` while the module does not define `attr` -- a module passed whole as
# a delegation table binds its names at run time, so emptying it by rewriting
# `from M import N` statements alone breaks there, not at import. Not a hit: a
# submodule, a module dunder, a name the module imports from a non-Datrix
# module, `hasattr` / `getattr` with a default (existence probes), and a read
# inside `pytest.raises(AttributeError)`. Tracked per scope.
#
# DAL generator-bound names. The kernel resolver looks a `<namespace>.<module>.<name>`
# DAL generator reference up as an attribute of the module the namespace reaches, so a
# name imported there only to be bound for DAL generator is not a provider-side hit;
# the allowlist is read from the definitions text and fails closed.
#
# Every `[project.entry-points.*]` value shaped "module.path:attr" in a
# discovered package's pyproject.toml is a site too: an attr the module does
# not define is a hit attributed to module.path.
#
# A `from M import N` where M is a dotted path under a Datrix import root
# that resolves to no module on disk at all is ALSO a hit -- once a facade's
# __all__ is emptied and its consumers are rewritten one at a time, this is
# what proves every rewritten import lands on something that actually
# exists, rather than silently accepting any string.
#
# Relative imports (`from .a import X`, `from . import sub`) are resolved to
# their absolute dotted module from the scanned file's own dotted name, on
# both the provider and the consumer side; a file outside every package's
# src/ tree has no dotted name, so its relative imports (which can only
# name sibling files of that tree, never a Datrix module) are not followed.
#
# This is a HARD ZERO with no baseline: any hit fails. Hits are grouped by
# the PROVIDING module -- its own relative file path when it resolves to a
# real file, or (only for the unresolved-import shape, where by definition
# no such file exists) the dotted module path itself.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReexportFacadeHit:
    """One occurrence of a re-export facade, attributed to the PROVIDING
    module.

    ``providing_module`` is the grouping key: the module's own
    relative file path when it resolves to a real file on disk, or -- only
    for an "unresolved" hit, where by definition no such file exists -- the
    dotted module path that failed to resolve. ``providing_module_dotted``
    is the same module's dotted import path when known (always known for
    consumer/entry-point/unresolved hits; known for a provider hit only when
    the scanned file is itself part of a discovered package's ``src/``
    tree), used solely to let ``-FacadeModule`` filter by dotted name.
    """

    providing_module: str
    kind: Literal[
        "provider", "consumer", "module_attribute", "entry_point", "unresolved"
    ]
    name: str
    site_file: Path
    site_line: int
    defining_module: str | None = None
    providing_module_dotted: str | None = None


def _assignment_target_names(target: ast.expr) -> set[str]:
    """Every ``Name`` id bound by an assignment target, including nested
    tuple/list/starred unpacking."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_assignment_target_names(elt))
        return names
    if isinstance(target, ast.Starred):
        return _assignment_target_names(target.value)
    return set()


def _collect_top_level_defined_names(body: list[ast.stmt]) -> set[str]:
    """Every name *body* DEFINES at its own top level: a ``def``/``class``,
    or an assignment target -- including under an ``if``/``try`` (both
    branches of every ``if`` are walked unconditionally, which is what makes
    a name defined only under ``if TYPE_CHECKING: ... else: ...`` still
    count as defined, with no special-casing of that one condition)."""
    names: set[str] = set()
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                names.update(_assignment_target_names(target))
        elif isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
            names.update(_assignment_target_names(stmt.target))
        elif isinstance(stmt, ast.AugAssign):
            names.update(_assignment_target_names(stmt.target))
        elif isinstance(stmt, ast.If):
            names.update(_collect_top_level_defined_names(stmt.body))
            names.update(_collect_top_level_defined_names(stmt.orelse))
        elif isinstance(stmt, ast.Try):
            names.update(_collect_top_level_defined_names(stmt.body))
            for handler in stmt.handlers:
                names.update(_collect_top_level_defined_names(handler.body))
            names.update(_collect_top_level_defined_names(stmt.orelse))
            names.update(_collect_top_level_defined_names(stmt.finalbody))
    return names


@dataclass(frozen=True)
class _ModuleFacadeInfo:
    """Everything the re-export-facade scan needs about one already-parsed
    module: the names it defines at its own top level, the names listed in
    its own ``__all__``, and every top-level ``from <datrix module> import
    N`` it declares (bound name -> (source module, source name, is a self
    alias), plus the reporting line for each bound name)."""

    defined_names: frozenset[str]
    all_names: frozenset[str]
    datrix_imports: dict[str, tuple[str, str, bool]]
    import_lines: dict[str, int]
    foreign_import_names: frozenset[str] = frozenset()


@functools.lru_cache(maxsize=None)
def _parse_module_source(file_path: Path) -> ast.Module:
    """Parse *file_path* once; every re-export-facade helper below shares
    this single cached parse instead of re-reading the file."""
    source = file_path.read_text(encoding="utf-8-sig")
    return ast.parse(source, filename=str(file_path))


@functools.lru_cache(maxsize=None)
def _analyze_module_file(file_path: Path, own_dotted: str | None) -> _ModuleFacadeInfo:
    """Compute *file_path*'s ``_ModuleFacadeInfo`` from its top-level
    statements only -- "defines" and "declares __all__" are both top-level
    facts by the check's own definition. *own_dotted* is the file's own
    dotted module name (``None`` outside every package's ``src/`` tree); it
    resolves the file's relative imports to absolute modules."""
    tree = _parse_module_source(file_path)
    defined_names = frozenset(_collect_top_level_defined_names(tree.body))
    all_names: set[str] = set()
    datrix_imports: dict[str, tuple[str, str, bool]] = {}
    import_lines: dict[str, int] = {}
    foreign_import_names: set[str] = set()
    for stmt in tree.body:
        source_module = (
            _absolute_import_module(stmt, file_path, own_dotted)
            if isinstance(stmt, ast.ImportFrom)
            else None
        )
        if (
            isinstance(stmt, ast.ImportFrom)
            and source_module is not None
            and _is_policed_module_path(source_module)
        ):
            for alias in stmt.names:
                bound = alias.asname or alias.name
                datrix_imports[bound] = (
                    source_module,
                    alias.name,
                    alias.asname == alias.name,
                )
                import_lines[bound] = alias.lineno
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            foreign_import_names.update(
                alias.asname or alias.name.split(".", 1)[0] for alias in stmt.names
            )
        elif isinstance(stmt, (ast.Assign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            targets_all = any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in targets
            )
            if targets_all and isinstance(stmt.value, (ast.List, ast.Tuple)):
                for elt in stmt.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        all_names.add(elt.value)
    return _ModuleFacadeInfo(
        defined_names=defined_names,
        all_names=frozenset(all_names),
        datrix_imports=datrix_imports,
        import_lines=import_lines,
        foreign_import_names=frozenset(foreign_import_names),
    )


def _resolve_defining_module(
    module_dotted: str,
    name: str,
    packages: dict[str, PackageInfo],
    context_file: Path,
    _seen: frozenset[Path] = frozenset(),
) -> str | None:
    """Follow *module_dotted*'s own re-export chain for *name* to the module
    that actually defines it, for the ``-ShowFiles`` worklist report only --
    never used for baseline attribution. *context_file* is the file whose
    import named *module_dotted* (it anchors a ``tests.<module>`` path).
    Returns ``None`` on a cycle, an unresolved link in the chain, or a dead
    end (the module neither defines the name nor re-exports it further)."""
    resolved = _resolve_policed_module(module_dotted, packages, context_file)
    if resolved is None or resolved.is_namespace or resolved.file_path in _seen:
        return None
    info = _analyze_module_file(resolved.file_path, module_dotted)
    if name in info.defined_names:
        return module_dotted
    next_hop = info.datrix_imports.get(name)
    if next_hop is None:
        return None
    next_module, next_name, _self_aliased = next_hop
    return _resolve_defining_module(
        next_module,
        next_name,
        packages,
        resolved.file_path,
        _seen | {resolved.file_path},
    )


def _analyze_scanned_file(
    file_path: Path, packages: dict[str, PackageInfo]
) -> _ModuleFacadeInfo:
    """``_analyze_module_file`` for a file of the scan scope, with the file's
    own dotted module name supplied so its relative imports resolve."""
    return _analyze_module_file(
        file_path, _dotted_module_name_for_file(file_path, packages)
    )


def _reexport_facade_scan_files(
    packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[Path]:
    """Every ``.py`` file the re-export-facade check scans: every discovered
    package's ``src/`` and ``tests/`` trees plus its root-level ``*.py``
    files (``conftest.py`` and the like), this repo's own
    ``datrix/scripts/`` tree, and ``datrix/claude-config/.claude/hooks/`` (a
    facade emptied later would otherwise break a script or a hook silently,
    with no static warning from this check). Prints an informational note
    when the hooks tree exists but nothing under it imports a Datrix
    module -- confirmed by scanning it, never assumed."""
    files: list[Path] = []
    for package_info in packages.values():
        files.extend(sorted(package_info.src_dir.rglob("*.py")))
        files.extend(sorted(package_info.root.glob("*.py")))
        tests_dir = package_info.root / "tests"
        if tests_dir.is_dir():
            files.extend(sorted(tests_dir.rglob("*.py")))
    scripts_dir = monorepo_root / "datrix" / "scripts"
    if scripts_dir.is_dir():
        files.extend(sorted(scripts_dir.rglob("*.py")))
    hooks_dir = monorepo_root / "datrix" / "claude-config" / ".claude" / "hooks"
    if hooks_dir.is_dir():
        hook_files = sorted(hooks_dir.rglob("*.py"))
        files.extend(hook_files)
        hooks_import_datrix = any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.level == 0
            and _is_datrix_module_path(node.module)
            for hook_file in hook_files
            for node in ast.walk(_parse_module_source(hook_file))
        )
        if hook_files and not hooks_import_datrix:
            print(
                f"Note: {len(hook_files)} file(s) under "
                f"{hooks_dir.relative_to(monorepo_root)} were scanned for "
                f"re-export facades; none imports a Datrix module.",
                file=sys.stderr,
            )
    return files


def _with_scripts_package(
    packages: dict[str, PackageInfo], monorepo_root: Path
) -> dict[str, PackageInfo]:
    """*packages* plus the shared scripts package (``datrix_scripts``), so
    the scripts and hooks the facade check scans resolve their imports of it
    instead of reporting every one as unresolved. Its location is the one
    ``datrix_scripts.paths`` declares, re-anchored at *monorepo_root*; a
    monorepo without that directory gets *packages* unchanged. Used for
    import resolution only -- the package's files are already in the scan
    scope through the ``datrix/scripts/`` tree."""
    scripts_src = monorepo_root / SCRIPTS_PACKAGE_DIR.relative_to(WORKSPACE_DIR)
    if not (scripts_src / "__init__.py").is_file():
        return packages
    name = SCRIPTS_PACKAGE_DIR.name
    return {
        **packages,
        name: PackageInfo(
            name=name,
            root=monorepo_root / SHOWCASE_DIR.relative_to(WORKSPACE_DIR),
            src_dir=scripts_src,
        ),
    }


def _reexport_facade_provider_hits(
    py_file: Path,
    info: _ModuleFacadeInfo,
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    dgen_bound: frozenset[tuple[Path, str]] = frozenset(),
) -> list[ReexportFacadeHit]:
    """The provider-side shape for one already-analyzed file: every bound
    name it imports from a Datrix or test-tree module and passes through --
    via a self-aliased import or its own ``__all__`` -- without defining it.
    A bound name that is itself a submodule of the module it is imported from
    (``from . import sub``) is a package traversal, never a facade, and a
    name in *dgen_bound* (see ``_dgen_bound_names``) is bound for a
    DAL generator ``<namespace>.<module>.<name>`` reference, not re-exported."""
    hits: list[ReexportFacadeHit] = []
    providing_module = str(py_file.relative_to(monorepo_root)).replace("\\", "/")
    providing_module_dotted = _dotted_module_name_for_file(py_file, packages)
    for bound_name, (source_module, source_name, self_aliased) in sorted(
        info.datrix_imports.items()
    ):
        if bound_name in info.defined_names:
            continue
        if not (self_aliased or bound_name in info.all_names):
            continue
        if (py_file, bound_name) in dgen_bound:
            continue
        resolved_source = _resolve_policed_module(source_module, packages, py_file)
        if resolved_source is not None and _is_submodule_member(
            resolved_source, source_name
        ):
            continue
        hits.append(
            ReexportFacadeHit(
                providing_module=providing_module,
                kind="provider",
                name=bound_name,
                site_file=py_file,
                site_line=info.import_lines[bound_name],
                providing_module_dotted=providing_module_dotted,
            )
        )
    return hits


def _reexport_facade_consumer_hits(
    py_file: Path, packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[ReexportFacadeHit]:
    """The consumer-side and unresolved-import shapes for one file: every
    ``from M import N`` ANYWHERE in the file (module top or nested -- unlike
    the provider-side shape, this one is not limited to module top), for
    every M that is a Datrix module or a test-tree module (``tests.<m>``,
    resolved against the importing file's own package). A relative import is
    resolved to its absolute M from the file's own dotted name first."""
    hits: list[ReexportFacadeHit] = []
    tree = _parse_module_source(py_file)
    own_dotted = _dotted_module_name_for_file(py_file, packages)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        node_module = _absolute_import_module(node, py_file, own_dotted)
        if node_module is None or not _is_policed_module_path(node_module):
            continue
        if (
            node_module.split(".", 1)[0] == _TEST_TREE_ROOT
            and _owning_package(py_file, packages) is None
        ):
            continue
        resolved = _resolve_policed_module(node_module, packages, py_file)
        for alias in node.names:
            if alias.name == "*":
                continue
            site_line = alias.lineno
            if resolved is None or (
                resolved.is_namespace
                and not _is_submodule_member(resolved, alias.name)
            ):
                hits.append(
                    ReexportFacadeHit(
                        providing_module=node_module,
                        kind="unresolved",
                        name=alias.name,
                        site_file=py_file,
                        site_line=site_line,
                        providing_module_dotted=node_module,
                    )
                )
                continue
            if resolved.is_namespace:
                continue
            info = _analyze_module_file(resolved.file_path, node_module)
            if alias.name in info.defined_names:
                continue
            if _is_submodule_member(resolved, alias.name):
                continue
            providing_module = str(
                resolved.file_path.relative_to(monorepo_root)
            ).replace("\\", "/")
            defining_module = _resolve_defining_module(
                node_module, alias.name, packages, py_file
            )
            hits.append(
                ReexportFacadeHit(
                    providing_module=providing_module,
                    kind="consumer",
                    name=alias.name,
                    site_file=py_file,
                    site_line=site_line,
                    defining_module=defining_module,
                    providing_module_dotted=node_module,
                )
            )
    return hits


#: ``getattr(m, "name")`` with no default raises when ``name`` is gone, so it
#: is a hard dependency on the attribute. ``hasattr`` and ``getattr`` with a
#: default are existence probes -- the tests that assert a name was REMOVED are
#: written with them -- and are not read as a use.
_MODULE_ATTRIBUTE_GETTER = "getattr"


def _dotted_chain(node: ast.expr) -> str | None:
    """``a.b.c`` for a ``Name``/``Attribute`` chain, ``None`` for any other
    expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_chain(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


_COMPREHENSION_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED_SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    *_COMPREHENSION_NODES,
)


def _scope_roots(scope: ast.AST) -> list[ast.AST]:
    """The child nodes a scope's own code is made of."""
    if isinstance(scope, ast.Lambda):
        return [scope.body]
    if isinstance(scope, ast.DictComp):
        return [scope.key, scope.value, *scope.generators]
    if isinstance(scope, _COMPREHENSION_NODES):
        return [scope.elt, *scope.generators]
    return list(getattr(scope, "body"))


def _own_scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """Every node that belongs to *scope* itself: its own code, and each
    nested scope's node (where that scope's name is bound) but not that
    scope's interior. A comprehension's first iterable is evaluated in the
    enclosing scope, so it belongs to the enclosing scope."""
    nodes: list[ast.AST] = []
    stack = list(reversed(_scope_roots(scope)))
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(node, _COMPREHENSION_NODES):
            stack.append(node.generators[0].iter)
        if isinstance(node, _NESTED_SCOPE_NODES):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return nodes


def _scope_rebound_names(scope: ast.AST, own_nodes: list[ast.AST]) -> set[str]:
    """Every name *scope* binds by something other than an import: a
    parameter, an assignment/``for``/``with``/comprehension target, a
    ``def``/``class`` or an ``except ... as`` name."""
    names: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = scope.args
        for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
            names.add(arg.arg)
        for special in (arguments.vararg, arguments.kwarg):
            if special is not None:
                names.add(special.arg)
    for node in own_nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            names.add(node.name)
    return names


def _scope_import_aliases(
    own_nodes: list[ast.AST],
    py_file: Path,
    own_dotted: str | None,
    packages: dict[str, PackageInfo],
) -> tuple[dict[str, str], set[str]]:
    """The module objects one scope's imports bind, and every name those
    imports bind at all. The mapping holds each expression a scope uses to
    hold a policed MODULE OBJECT -> that module's absolute dotted path:
    ``import a.b as m`` (``m``), ``import a.b.c`` (``a``, ``a.b`` and
    ``a.b.c``, each a real module) and ``from a import b`` where ``b`` is a
    submodule of ``a`` (``b``)."""
    aliases: dict[str, str] = {}
    bound: set[str] = set()
    for node in own_nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".", 1)[0])
                if not _is_policed_module_path(alias.name):
                    continue
                if alias.asname:
                    aliases[alias.asname] = alias.name
                    continue
                segments = alias.name.split(".")
                for depth in range(1, len(segments) + 1):
                    prefix = ".".join(segments[:depth])
                    aliases[prefix] = prefix
        elif isinstance(node, ast.ImportFrom):
            bound.update(
                alias.asname or alias.name for alias in node.names if alias.name != "*"
            )
            node_module = _absolute_import_module(node, py_file, own_dotted)
            if node_module is None or not _is_policed_module_path(node_module):
                continue
            resolved = _resolve_policed_module(node_module, packages, py_file)
            if resolved is None:
                continue
            for alias in node.names:
                if alias.name != "*" and _is_submodule_member(resolved, alias.name):
                    aliases[alias.asname or alias.name] = f"{node_module}.{alias.name}"
    return aliases, bound


def _is_attribute_error_raises(item: ast.withitem) -> bool:
    """True for a ``with pytest.raises(AttributeError, ...)`` item."""
    call = item.context_expr
    if not isinstance(call, ast.Call) or not call.args:
        return False
    if _dotted_chain(call.func) not in ("raises", "pytest.raises"):
        return False
    expected = call.args[0]
    candidates = expected.elts if isinstance(expected, ast.Tuple) else [expected]
    return any(_dotted_chain(c) == "AttributeError" for c in candidates)


def _absence_asserted_node_ids(tree: ast.Module) -> frozenset[int]:
    """The ids of every node inside a ``with pytest.raises(AttributeError)``
    body: a read there asserts that the attribute is GONE, which is the
    opposite of depending on it."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            _is_attribute_error_raises(item) for item in node.items
        ):
            for stmt in node.body:
                ids.update(id(inner) for inner in ast.walk(stmt))
    return frozenset(ids)


def _scope_attribute_uses(
    own_nodes: list[ast.AST], aliases: dict[str, str], absence_asserted: frozenset[int]
) -> set[tuple[str, str, int]]:
    """Every ``(module dotted path, attribute, line)`` the scope reads off a
    module object in *aliases*: ``m.attr`` in load position, and
    ``getattr(m, "attr")`` with a literal name and no default. A read inside
    a ``pytest.raises(AttributeError)`` body (*absence_asserted*) is skipped."""
    uses: set[tuple[str, str, int]] = set()
    for node in own_nodes:
        if id(node) in absence_asserted:
            continue
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            chain = _dotted_chain(node.value)
            if chain in aliases:
                uses.add((aliases[chain], node.attr, node.lineno))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == _MODULE_ATTRIBUTE_GETTER
            and len(node.args) == 2
            and not node.keywords
        ):
            chain = _dotted_chain(node.args[0])
            attr_arg = node.args[1]
            if (
                chain in aliases
                and isinstance(attr_arg, ast.Constant)
                and isinstance(attr_arg.value, str)
            ):
                uses.add((aliases[chain], attr_arg.value, node.lineno))
    return uses


def _module_attribute_uses(
    tree: ast.Module,
    py_file: Path,
    own_dotted: str | None,
    packages: dict[str, PackageInfo],
) -> list[tuple[str, str, int]]:
    """Every attribute use of a policed module object in the file, resolved
    scope by scope: a name is a module object only where an import in that
    scope (or an enclosing one) binds it and nothing in the scope rebinds it
    some other way. A name a scope both imports and rebinds, or rebinds
    where an enclosing scope imports it, is not tracked there -- which
    binding a use reads is flow-dependent, and guessing would report code
    that never touches the module."""
    uses: set[tuple[str, str, int]] = set()
    absence_asserted = _absence_asserted_node_ids(tree)
    pending: list[tuple[ast.AST, dict[str, str]]] = [(tree, {})]
    while pending:
        scope, inherited = pending.pop()
        own_nodes = _own_scope_nodes(scope)
        import_aliases, import_bound = _scope_import_aliases(
            own_nodes, py_file, own_dotted, packages
        )
        rebound = _scope_rebound_names(scope, own_nodes)
        shadowed = rebound | import_bound
        aliases = {
            key: module
            for key, module in inherited.items()
            if key.split(".", 1)[0] not in shadowed
        }
        aliases.update(
            (key, module)
            for key, module in import_aliases.items()
            if key.split(".", 1)[0] not in rebound
        )
        if aliases:
            uses.update(_scope_attribute_uses(own_nodes, aliases, absence_asserted))
        pending.extend(
            (node, aliases) for node in own_nodes if isinstance(node, _NESTED_SCOPE_NODES)
        )
    return sorted(uses)


def _reexport_facade_module_attribute_hits(
    py_file: Path, packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[ReexportFacadeHit]:
    """The module-object shape for one file: a policed module held as an
    object (``import a.b as m``, ``from a import b``) whose attribute is read
    with ``m.attr`` or ``getattr(m, "attr")`` while the module
    does not itself define ``attr`` (and ``attr`` is not one of its
    submodules or a module dunder). A module passed whole as a delegation
    table, or probed by ``getattr``, binds its attributes at run time, so
    emptying it by rewriting ``from M import N`` statements alone breaks at
    run time, not at import."""
    tree = _parse_module_source(py_file)
    own_dotted = _dotted_module_name_for_file(py_file, packages)
    hits: list[ReexportFacadeHit] = []
    for module_dotted, attr, line in _module_attribute_uses(
        tree, py_file, own_dotted, packages
    ):
        if attr.startswith("__") and attr.endswith("__"):
            continue
        resolved = _resolve_policed_module(module_dotted, packages, py_file)
        if resolved is None or resolved.is_namespace:
            continue
        info = _analyze_module_file(resolved.file_path, module_dotted)
        if (
            attr in info.defined_names
            or attr in info.foreign_import_names
            or _is_submodule_member(resolved, attr)
        ):
            continue
        hits.append(
            ReexportFacadeHit(
                providing_module=str(
                    resolved.file_path.relative_to(monorepo_root)
                ).replace("\\", "/"),
                kind="module_attribute",
                name=attr,
                site_file=py_file,
                site_line=line,
                defining_module=_resolve_defining_module(
                    module_dotted, attr, packages, py_file
                ),
                providing_module_dotted=module_dotted,
            )
        )
    return hits


#: A DAL generator function reference as the definitions text spells it: ``builder
#: <ref>``, ``call <ref>(...)`` or ``from <ref>`` (the ``context T from`` /
#: ``appends X from`` forms), where ``<ref>`` is ``<namespace>.<module>.<name>``.
_DGEN_REFERENCE_PATTERN = re.compile(
    r"(?<![\w.])(?:builder|call|from)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)"
)

ContextModuleResolver = Callable[[str], str | None]


def _registry_context_module_resolver() -> ContextModuleResolver:
    """Resolve a DAL generator ``<namespace>.<module>`` path to its real module path
    through the kernel's own registry -- the single resolver the DAL generator
    executor uses -- or ``None`` when no registered namespace prefixes it."""
    from datrix_codegen_kernel.dgen import target_registry
    from datrix_common.errors.generation import GenerationError

    def resolve(module_path: str) -> str | None:
        try:
            return target_registry.resolve_dgen_context_module(module_path)
        except GenerationError:
            return None

    return resolve


def _dgen_bound_names(
    files: list[Path],
    packages: dict[str, PackageInfo],
    resolve_context_module: ContextModuleResolver,
) -> frozenset[tuple[Path, str]]:
    """Every ``(module file, name)`` a DAL generator reference in the scanned
    packages' ``src/`` trees resolves to. The kernel DAL generator resolver looks a
    ``<namespace>.<module>.<name>`` reference up as an ATTRIBUTE of the
    module the namespace reaches, so a name imported into that module only
    to be bound for DAL generator is not a re-export for Python callers.

    The allowlist is read from the definitions text itself (string constants,
    f-string literal parts included). A reference the text spells in a way
    this pattern does not match is simply not exempted, so the scan fails
    closed: an under-read allowlist reports a hit, never hides one."""
    src_dirs = [info.src_dir for info in packages.values()]
    resolved_modules: dict[str, _ResolvedDatrixModule | None] = {}
    bound: set[tuple[Path, str]] = set()
    for py_file in files:
        if not any(src_dir in py_file.parents for src_dir in src_dirs):
            continue
        try:
            tree = _parse_module_source(py_file)
        except (SyntaxError, OSError, UnicodeDecodeError):
            # Not skipped for good: ``scan_reexport_facades`` parses every
            # scanned file next and aborts the run, naming the file.
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for match in _DGEN_REFERENCE_PATTERN.finditer(node.value):
                module_path, _, name = match.group(1).rpartition(".")
                if not module_path:
                    continue
                if module_path not in resolved_modules:
                    actual = resolve_context_module(module_path)
                    resolved_modules[module_path] = (
                        None if actual is None else _resolve_datrix_module(actual, packages)
                    )
                target = resolved_modules[module_path]
                if target is not None and not target.is_namespace:
                    bound.add((target.file_path, name))
    return frozenset(bound)


def _reexport_facade_entry_point_targets(manifest: Path) -> list[tuple[str, str, str]]:
    """Every ``(group, entry name, "module.path:attr")`` triple a package's
    ``pyproject.toml`` declares under ``[project.entry-points.*]``."""
    with manifest.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project")
    groups = project.get("entry-points", {}) if isinstance(project, dict) else {}
    if not isinstance(groups, dict):
        return []
    targets: list[tuple[str, str, str]] = []
    for group, entries in groups.items():
        if not isinstance(entries, dict):
            continue
        for entry_name, reference in entries.items():
            if isinstance(reference, str) and ":" in reference:
                targets.append((group, entry_name, reference))
    return targets


def _reexport_facade_entry_point_line(manifest_lines: list[str], reference: str) -> int:
    """The 1-based line in *manifest_lines* naming *reference* verbatim, or
    line 1 if the exact string cannot be found (never fails the scan over a
    reporting nicety)."""
    for line_number, line in enumerate(manifest_lines, start=1):
        if reference in line:
            return line_number
    return 1


def scan_reexport_facades(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    context_module_resolver: ContextModuleResolver | None = None,
) -> dict[str, list[ReexportFacadeHit]]:
    """Scan every re-export-facade shape -- provider side, consumer side,
    module-object attribute use, pyproject.toml entry points, and unresolved
    imports -- across the whole scan scope, and group every hit by its
    PROVIDING module.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        context_module_resolver: Resolves a DAL generator ``<namespace>.<module>``
            path to its real module path, or ``None`` for an unregistered
            namespace; defaults to the kernel registry's resolver.

    Returns:
        Mapping of providing-module key (see ``ReexportFacadeHit``) -> hits
        attributed to it (keys with zero hits omitted).
    """
    results: dict[str, list[ReexportFacadeHit]] = {}

    def _add(hit: ReexportFacadeHit) -> None:
        results.setdefault(hit.providing_module, []).append(hit)

    scan_files = _reexport_facade_scan_files(packages, monorepo_root)
    resolution_packages = _with_scripts_package(packages, monorepo_root)
    dgen_bound = _dgen_bound_names(
        scan_files,
        resolution_packages,
        context_module_resolver or _registry_context_module_resolver(),
    )
    for py_file in scan_files:
        try:
            info = _analyze_scanned_file(py_file, resolution_packages)
        except SyntaxError as e:
            rel_path = py_file.relative_to(monorepo_root)
            print(
                f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                f"A policed file that cannot be parsed would escape this scan "
                f"(a silent blind spot); fix its syntax or encoding.",
                file=sys.stderr,
            )
            sys.exit(2)
        except (OSError, UnicodeDecodeError) as e:
            rel_path = py_file.relative_to(monorepo_root)
            print(
                f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                f"cannot be read would escape this scan; resolve the read error.",
                file=sys.stderr,
            )
            sys.exit(2)

        for hit in _reexport_facade_provider_hits(
            py_file, info, resolution_packages, monorepo_root, dgen_bound
        ):
            _add(hit)
        for hit in _reexport_facade_consumer_hits(
            py_file, resolution_packages, monorepo_root
        ):
            _add(hit)
        for hit in _reexport_facade_module_attribute_hits(
            py_file, resolution_packages, monorepo_root
        ):
            _add(hit)

    for package_name, package_info in sorted(packages.items()):
        manifest = package_info.root / "pyproject.toml"
        if not manifest.is_file():
            continue
        targets = _reexport_facade_entry_point_targets(manifest)
        if not targets:
            continue
        try:
            manifest_lines = manifest.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            rel_path = manifest.relative_to(monorepo_root)
            print(
                f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                f"cannot be read would escape this scan; resolve the read error.",
                file=sys.stderr,
            )
            sys.exit(2)
        for _group, _entry_name, reference in targets:
            module_path, _, attr = reference.partition(":")
            module_path = module_path.strip()
            attr = attr.strip()
            if not module_path or not attr or not _is_datrix_module_path(module_path):
                continue
            site_line = _reexport_facade_entry_point_line(manifest_lines, reference)
            resolved = _resolve_datrix_module(module_path, packages)
            if resolved is not None:
                defined = _analyze_module_file(
                    resolved.file_path, module_path
                ).defined_names
                if attr in defined:
                    continue
                providing_module = str(
                    resolved.file_path.relative_to(monorepo_root)
                ).replace("\\", "/")
            else:
                providing_module = module_path
            _add(
                ReexportFacadeHit(
                    providing_module=providing_module,
                    kind="entry_point",
                    name=attr,
                    site_file=manifest,
                    site_line=site_line,
                    providing_module_dotted=module_path,
                )
            )

    return results


def check_reexport_facades(
    hits_by_module: dict[str, list[ReexportFacadeHit]], monorepo_root: Path
) -> list[str]:
    """Return one message per re-export-facade hit -- ANY hit fails.

    No baseline: a name with a second import path is removed, never
    grandfathered, so a new facade fails outright. Returns an empty list only
    when ``hits_by_module`` holds no hit at all.

    Args:
        hits_by_module: Output of ``scan_reexport_facades``.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        One failure message per hit, sorted by providing module, then site
        file, then line.
    """
    return format_reexport_facade_worklist(hits_by_module, monorepo_root)


def format_reexport_facade_worklist(
    hits_by_module: dict[str, list[ReexportFacadeHit]],
    monorepo_root: Path,
    *,
    facade_modules: frozenset[str] = frozenset(),
    consumer_packages: frozenset[str] = frozenset(),
) -> list[str]:
    """The per-site worklist report for ``-ShowFiles``: one line per hit,
    filtered by ``-FacadeModule``/``-ConsumerPackage`` when given.

    Args:
        hits_by_module: The scan result, as returned by
            ``scan_reexport_facades``.
        monorepo_root: Monorepo root, for the site file's relative path.
        facade_modules: If non-empty, keep only hits whose providing module
            matches one of these -- either the grouping-key form (a relative
            file path, or a dotted path for an unresolved entry) or the
            dotted form (``providing_module_dotted``).
        consumer_packages: If non-empty, keep only hits whose site file
            lives under one of these repo directory names.

    Returns:
        One formatted line per surviving hit, sorted by providing module
        then site file then line.
    """
    lines: list[str] = []
    for providing_module in sorted(hits_by_module):
        for hit in sorted(
            hits_by_module[providing_module], key=lambda h: (str(h.site_file), h.site_line)
        ):
            if facade_modules and not (
                providing_module in facade_modules
                or (
                    hit.providing_module_dotted is not None
                    and hit.providing_module_dotted in facade_modules
                )
            ):
                continue
            site_rel = str(hit.site_file.relative_to(monorepo_root)).replace("\\", "/")
            if consumer_packages and site_rel.split("/", 1)[0] not in consumer_packages:
                continue
            defining_suffix = (
                f" (defined by {hit.defining_module})"
                if hit.kind == "consumer" and hit.defining_module
                else ""
            )
            lines.append(
                f"{providing_module} [{hit.kind}] {site_rel}:{hit.site_line} "
                f"{hit.name}{defining_suffix}"
            )
    return lines


def _self_test_reexport_facade_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one fixture package
    (``datrix-codegen-fixture``) with a clean ``__init__.py`` (defines
    nothing, re-exports nothing) and a ``sub.py`` defining ``VALUE``. The
    fixture carries NO re-export-facade baseline file: the check is a hard
    zero and never reads one. Registers a ``datrix.languages`` entry point so
    the scanner classifies it (a discovered package with no rule at all stops
    the scan by design). Returns the ``__init__.py`` path."""
    _self_test_write_manifest(
        tmp_root,
        "datrix-codegen-fixture",
        "datrix_codegen_fixture",
        entry_point_groups={
            LANGUAGES_ENTRY_POINT_GROUP: {"fixture": "FixtureLanguagePlugin"}
        },
    )
    fixture_src = tmp_root / "datrix-codegen-fixture" / "src" / "datrix_codegen_fixture"
    fixture_src.mkdir(parents=True, exist_ok=True)
    init_path = fixture_src / "__init__.py"
    init_path.write_text('"""Fixture package."""\n', encoding="utf-8")
    (fixture_src / "sub.py").write_text("VALUE = 1\n", encoding="utf-8")
    # The manifest's own entry point (module=<import_package>.plugin) must
    # resolve to a real module defining the referenced attribute, or the
    # entry-point shape would itself flag a hit and break the "clean"
    # baseline this fixture is meant to establish.
    (fixture_src / "plugin.py").write_text(
        "class FixtureLanguagePlugin:\n    pass\n", encoding="utf-8"
    )
    return init_path


def _self_test_reexport_facade_run_cli(
    tmp_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--base-dir",
            str(tmp_root),
            "--check-reexport-facades",
            "--skip-auto-self-test",
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_reexport_facade_extended_shapes(
    scratch_dir: Path, fixture_src: Path, packages: dict[str, PackageInfo]
) -> bool:
    """Scanner assertions for the three shapes a plain ``from <datrix module>
    import N`` scan cannot see: test-tree modules (``tests.<module>``) as
    providers, module objects read by attribute or ``getattr``, and names
    bound for a DAL generator ``<namespace>.<module>.<name>`` reference. Every case
    runs the real scanner functions over real fixture files, the negative
    (zero-hit) case beside the positive one."""
    ok = True

    def _write(relative: str, source: str) -> Path:
        file_path = scratch_dir / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source, encoding="utf-8")
        _analyze_module_file.cache_clear()
        _parse_module_source.cache_clear()
        return file_path

    def _consumer(file_path: Path, known: dict[str, PackageInfo]) -> list[ReexportFacadeHit]:
        return _reexport_facade_consumer_hits(file_path, known, scratch_dir)

    def _attribute(file_path: Path) -> list[ReexportFacadeHit]:
        return sorted(
            _reexport_facade_module_attribute_hits(file_path, packages, scratch_dir),
            key=lambda hit: hit.site_line,
        )

    (fixture_src / "pkg" / "sub.py").write_text("X = 1\nY = 2\n", encoding="utf-8")

    # Test-tree modules are providers: ``tests.<module>`` resolves against the
    # importing file's own package.
    _write("tests/__init__.py", "")
    helpers = _write(
        "tests/helpers.py", "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n"
    )
    _write("tests/clean_helpers.py", "X = 1\n")
    provider_hits = _reexport_facade_provider_hits(
        helpers, _analyze_scanned_file(helpers, packages), packages, scratch_dir
    )
    ok &= _check(
        "a tests/ module re-exporting a Datrix name is exactly one provider hit "
        "named by its dotted tests.<module> path",
        len(provider_hits) == 1
        and provider_hits[0].kind == "provider"
        and provider_hits[0].providing_module_dotted == "tests.helpers",
    )
    test_use = _write("tests/test_use.py", "from tests.helpers import X\n")
    test_hits = _consumer(test_use, packages)
    ok &= _check(
        "from tests.helpers import X is exactly one consumer hit, attributed to "
        "tests/helpers.py and resolved to the module that defines X",
        len(test_hits) == 1
        and test_hits[0].kind == "consumer"
        and test_hits[0].providing_module == "tests/helpers.py"
        and test_hits[0].defining_module == "datrix_fixture.pkg.sub",
    )
    ok &= _check(
        "from tests.clean_helpers import X is zero hits when that module defines X",
        _consumer(_write("tests/test_clean.py", "from tests.clean_helpers import X\n"), packages)
        == [],
    )
    missing_hits = _consumer(
        _write("tests/test_missing.py", "from tests.nope import X\n"), packages
    )
    ok &= _check(
        "from tests.nope import X is one unresolved hit",
        len(missing_hits) == 1
        and missing_hits[0].kind == "unresolved"
        and missing_hits[0].providing_module == "tests.nope",
    )
    relative_init = _write(
        "tests/relpkg/__init__.py", "from .a import X\n\n__all__ = ['X']\n"
    )
    _write("tests/relpkg/a.py", "X = 1\n")
    relative_provider_hits = _reexport_facade_provider_hits(
        relative_init, _analyze_scanned_file(relative_init, packages), packages, scratch_dir
    )
    ok &= _check(
        "a relative import inside the tests/ tree resolves: from .a import X + "
        "__all__ is one provider hit and zero consumer hits",
        len(relative_provider_hits) == 1 and _consumer(relative_init, packages) == [],
    )
    _write("tests/ns/mod.py", "VALUE = 1\n")
    ok &= _check(
        "a tests/ directory without __init__.py is a namespace package: importing "
        "its submodule is zero hits",
        _consumer(_write("tests/test_ns.py", "from tests.ns import mod\n"), packages) == [],
    )
    namespace_hits = _consumer(
        _write("tests/test_ns_absent.py", "from tests.ns import absent\n"), packages
    )
    ok &= _check(
        "importing a name that is not a submodule of a namespace package is one "
        "unresolved hit",
        len(namespace_hits) == 1 and namespace_hits[0].kind == "unresolved",
    )
    ok &= _check(
        "a file outside every package has no tests/ root to resolve against: zero hits",
        _consumer(test_use, {}) == [],
    )

    # Module objects: ``m.attr`` and ``getattr(m, "attr")`` read the attribute at
    # run time, so a facade emptied by rewriting its imports breaks there.
    module_use = _write(
        "datrix_fixture/module_use.py",
        "import datrix_fixture.pkg as m\n"
        "import datrix_fixture.pkg.sub as s\n"
        "from datrix_fixture.pkg import sub\n\n"
        "A = m.X\n"
        "B = m.sub\n"
        "C = m.__name__\n"
        "D = s.X\n"
        "E = sub.Y\n"
        "F = sub.Missing\n"
        "G = getattr(m, 'X')\n"
        "H = getattr(m, 'X', None)\n"
        "I = hasattr(m, 'X')\n",
    )
    attribute_hits = _attribute(module_use)
    ok &= _check(
        "m.attr and getattr(m, 'attr') on a name the module only re-exports, and "
        "an undefined attribute, are exactly three module_attribute hits",
        [(hit.name, hit.site_line) for hit in attribute_hits]
        == [("X", 5), ("Missing", 10), ("X", 11)]
        and all(hit.kind == "module_attribute" for hit in attribute_hits),
    )
    ok &= _check(
        "a module-attribute hit is attributed to the re-exporting module and "
        "resolved to the module that defines the name",
        attribute_hits[0].providing_module == "datrix_fixture/pkg/__init__.py"
        and attribute_hits[0].defining_module == "datrix_fixture.pkg.sub",
    )
    ok &= _check(
        "a defined name, a submodule, a module dunder, getattr with a default and "
        "hasattr are all zero module_attribute hits",
        {hit.site_line for hit in attribute_hits}.isdisjoint({6, 7, 8, 9, 12, 13}),
    )
    scoped = _write(
        "datrix_fixture/module_scope.py",
        "import datrix_fixture.pkg as m\n\n"
        "def uses_module():\n"
        "    return m.X\n\n"
        "def shadowed(m):\n"
        "    return m.X\n\n"
        "def reimported():\n"
        "    import datrix_fixture.pkg.sub as m\n"
        "    return m.X\n",
    )
    ok &= _check(
        "module-object tracking is scope-aware: a parameter or a function-local "
        "import of another module rebinding the name is not a use of the facade",
        [hit.site_line for hit in _attribute(scoped)] == [4],
    )
    absent = _write(
        "datrix_fixture/module_absent.py",
        "import pytest\n"
        "import datrix_fixture.pkg as m\n\n"
        "def test_gone() -> None:\n"
        "    with pytest.raises(AttributeError):\n"
        "        m.X\n"
        "    with pytest.raises(AttributeError):\n"
        "        getattr(m, 'X')\n",
    )
    ok &= _check(
        "a read inside pytest.raises(AttributeError) asserts the name is gone: zero hits",
        _attribute(absent) == [],
    )
    _write("datrix_fixture/foreign.py", "import shutil\nVALUE = 1\n")
    foreign = _write(
        "datrix_fixture/foreign_use.py",
        "import datrix_fixture.foreign as f\nA = f.shutil\nB = f.nope\nC = f.VALUE\n",
    )
    ok &= _check(
        "a stdlib module the target imports is not a re-exported Datrix name, while "
        "an attribute it neither defines nor imports is one hit",
        [hit.name for hit in _attribute(foreign)] == ["nope"],
    )
    tests_module_use = _write(
        "tests/test_module_use.py",
        "from tests import helpers\n\nA = helpers.X\nB = getattr(helpers, 'X')\n",
    )
    ok &= _check(
        "a tests/ module held as an object is tracked like a Datrix module: "
        "helpers.X and getattr(helpers, 'X') are two hits",
        [hit.site_line for hit in _attribute(tests_module_use)] == [3, 4],
    )

    # DAL generator-bound names: the kernel resolver looks ``<namespace>.<module>.<name>``
    # up as an attribute of the module the namespace reaches.
    bound_module = _write(
        "datrix_fixture/dgen_mod.py",
        "from datrix_fixture.pkg.sub import X as X\nfrom datrix_fixture.pkg.sub import Y as Y\n",
    )
    definitions = _write(
        "datrix_fixture/defs.py",
        "TEXT = 'builder fx.builders.X => call fx.builders.X(item); "
        "when call other.thing.f(item);'\n",
    )

    def _resolve_fixture_namespace(module_path: str) -> str | None:
        return {"fx.builders": "datrix_fixture.dgen_mod"}.get(module_path)

    bound = _dgen_bound_names([definitions], packages, _resolve_fixture_namespace)
    ok &= _check(
        "the DAL generator allowlist holds exactly the (module, name) pairs the definitions "
        "text references through a registered namespace",
        bound == frozenset({(bound_module, "X")}),
    )
    bound_info = _analyze_scanned_file(bound_module, packages)
    ok &= _check(
        "a name bound for a DAL generator reference is not a provider hit; an unreferenced "
        "import in the same module still is",
        [
            hit.name
            for hit in _reexport_facade_provider_hits(
                bound_module, bound_info, packages, scratch_dir, bound
            )
        ]
        == ["Y"]
        and [
            hit.name
            for hit in _reexport_facade_provider_hits(
                bound_module, bound_info, packages, scratch_dir
            )
        ]
        == ["X", "Y"],
    )
    ok &= _check(
        "a Python caller importing a DAL generator-bound name through that module is still "
        "a consumer hit",
        len(
            _consumer(
                _write("datrix_fixture/dgen_caller.py", "from datrix_fixture.dgen_mod import X\n"),
                packages,
            )
        )
        == 1,
    )
    return ok


def _self_test_reexport_facade_scanner() -> bool:
    """Direct scanner assertions for the re-export-facade check's exactly-
    one-hit and zero-hit cases, PLUS a real CLI mutation proof (plant a
    provider-side facade in a fixture package, prove the ratchet fires and
    names the exact delta, prove it clears on revert), PLUS a
    ``-FacadeModule``/``-ConsumerPackage``-filtered ``-ShowFiles`` run
    proving the worklist prints the planted sites with the consumer hit's
    resolved defining module."""
    report_step(
        "Self-test 23/24: re-export-facade scanner (provider/consumer/"
        "entry-point/unresolved shapes, TYPE_CHECKING definition, submodule "
        "exemption) + CLI mutation non-vacuity + filtered worklist"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"reexport-facade-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        fixture_src = scratch_dir / "datrix_fixture"
        pkg_dir = fixture_src / "pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text(
            "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n", encoding="utf-8"
        )
        (pkg_dir / "sub.py").write_text("X = 1\n", encoding="utf-8")
        packages = {
            "datrix_fixture": PackageInfo(
                name="datrix_fixture", root=scratch_dir, src_dir=fixture_src
            )
        }

        def _provider_hits(relative_name: str, source: str) -> list[ReexportFacadeHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            _analyze_module_file.cache_clear()
            _parse_module_source.cache_clear()
            info = _analyze_scanned_file(file_path, packages)
            return _reexport_facade_provider_hits(file_path, info, packages, scratch_dir)

        # One-hit case: __all__ = ["X"] + from a.b import X.
        all_hits = _provider_hits(
            "one_all.py", "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n"
        )
        ok &= _check(
            "__all__ = ['X'] + from ...sub import X is exactly one provider hit",
            len(all_hits) == 1 and all_hits[0].kind == "provider" and all_hits[0].name == "X",
        )

        # One-hit case: from a.b import X as X.
        self_alias_hits = _provider_hits(
            "one_self_alias.py", "from datrix_fixture.pkg.sub import X as X\n"
        )
        ok &= _check(
            "from ...sub import X as X is exactly one provider hit",
            len(self_alias_hits) == 1 and self_alias_hits[0].kind == "provider",
        )

        # Zero-hit case: imports X and uses it without listing it in __all__.
        unlisted_hits = _provider_hits(
            "zero_unlisted.py", "from datrix_fixture.pkg.sub import X\n\nprint(X)\n"
        )
        ok &= _check(
            "importing X and using it without __all__/self-alias is zero provider hits",
            unlisted_hits == [],
        )

        # Zero-hit case: a name defined under if TYPE_CHECKING: ... else: ...
        # despite also being self-aliased from an external module.
        type_checking_hits = _provider_hits(
            "zero_type_checking.py",
            "from typing import TYPE_CHECKING\n"
            "from datrix_fixture.pkg.sub import X as X\n\n"
            "if TYPE_CHECKING:\n"
            "    class X:\n"
            "        pass\n"
            "else:\n"
            "    class X:\n"
            "        pass\n",
        )
        ok &= _check(
            "a name defined under if TYPE_CHECKING: ... else: ... is zero "
            "provider hits even when self-aliased",
            type_checking_hits == [],
        )

        # One-hit case (consumer side): from pkg import X where pkg/__init__
        # only imports X (never defines it) -- resolves the defining module
        # through the re-export chain to pkg.sub.
        consumer_file = scratch_dir / "consumer.py"
        consumer_file.write_text("from datrix_fixture.pkg import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        consumer_hits = _reexport_facade_consumer_hits(consumer_file, packages, scratch_dir)
        ok &= _check(
            "from pkg import X where pkg/__init__ only imports X is exactly "
            "one consumer hit, resolved to the module that actually defines it",
            len(consumer_hits) == 1
            and consumer_hits[0].kind == "consumer"
            and consumer_hits[0].providing_module
            == "datrix_fixture/pkg/__init__.py"
            and consumer_hits[0].defining_module == "datrix_fixture.pkg.sub",
        )

        # Zero-hit case: from pkg import submodule is a normal traversal.
        submodule_file = scratch_dir / "submodule_consumer.py"
        submodule_file.write_text("from datrix_fixture.pkg import sub\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        submodule_hits = _reexport_facade_consumer_hits(
            submodule_file, packages, scratch_dir
        )
        ok &= _check(
            "from pkg import submodule is zero consumer hits (submodule exemption)",
            submodule_hits == [],
        )

        # One-hit case: a facade name that differs from a submodule's file
        # stem only by case is NOT that submodule -- a case-insensitive
        # filesystem must not exempt it.
        case_pkg_dir = fixture_src / "pkg_case"
        case_pkg_dir.mkdir(parents=True, exist_ok=True)
        (case_pkg_dir / "__init__.py").write_text(
            "from datrix_fixture.pkg_case.sub import Sub\n\n__all__ = ['Sub']\n",
            encoding="utf-8",
        )
        (case_pkg_dir / "sub.py").write_text("Sub = 1\n", encoding="utf-8")
        case_file = scratch_dir / "case_consumer.py"
        case_file.write_text("from datrix_fixture.pkg_case import Sub\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        case_hits = _reexport_facade_consumer_hits(case_file, packages, scratch_dir)
        ok &= _check(
            "from pkg import Sub where pkg also has sub.py is one consumer hit "
            "(the submodule exemption is case-exact)",
            len(case_hits) == 1
            and case_hits[0].kind == "consumer"
            and case_hits[0].defining_module == "datrix_fixture.pkg_case.sub",
        )

        # Unresolved-import case: the module segment does not exist on disk.
        unresolved_file = scratch_dir / "unresolved_consumer.py"
        unresolved_file.write_text(
            "from datrix_fixture.no_such_module import X\n", encoding="utf-8"
        )
        _parse_module_source.cache_clear()
        unresolved_hits = _reexport_facade_consumer_hits(
            unresolved_file, packages, scratch_dir
        )
        ok &= _check(
            "an import of a module that resolves to nothing on disk is one "
            "unresolved hit",
            len(unresolved_hits) == 1
            and unresolved_hits[0].kind == "unresolved"
            and unresolved_hits[0].providing_module == "datrix_fixture.no_such_module",
        )

        # Entry-point case: a pyproject.toml `module:attr` value is a site. An
        # attr the module defines is zero hits; an attr it does not define is
        # one entry_point hit attributed to the module's file; a module that
        # resolves to nothing on disk is one entry_point hit attributed to the
        # dotted path.
        ep_repo = scratch_dir / "ep_repo"
        ep_root = ep_repo / "datrix-fixture-ep"
        ep_src = ep_root / "src" / "datrix_fixture_ep"
        ep_src.mkdir(parents=True, exist_ok=True)
        (ep_src / "__init__.py").write_text('"""Fixture."""\n', encoding="utf-8")
        (ep_src / "plugin.py").write_text(
            "class DefinedPlugin:\n    pass\n", encoding="utf-8"
        )
        ep_packages = {
            "datrix_fixture_ep": PackageInfo(
                name="datrix_fixture_ep", root=ep_root, src_dir=ep_src
            )
        }

        def _entry_point_hits(
            import_package: str, attribute: str
        ) -> list[ReexportFacadeHit]:
            _self_test_write_manifest(
                ep_repo,
                "datrix-fixture-ep",
                import_package,
                entry_point_groups={"datrix.languages": {"fixture": attribute}},
            )
            _analyze_module_file.cache_clear()
            _parse_module_source.cache_clear()
            scanned = scan_reexport_facades(ep_packages, ep_repo)
            return [
                hit
                for hits in scanned.values()
                for hit in hits
                if hit.kind == "entry_point"
            ]

        ok &= _check(
            "an entry point naming an attr its module defines is zero entry_point hits",
            _entry_point_hits("datrix_fixture_ep", "DefinedPlugin") == [],
        )
        undefined_attr_hits = _entry_point_hits("datrix_fixture_ep", "MissingPlugin")
        ok &= _check(
            "an entry point naming an attr its module does not define is exactly "
            "one entry_point hit attributed to that module's file",
            len(undefined_attr_hits) == 1
            and undefined_attr_hits[0].name == "MissingPlugin"
            and undefined_attr_hits[0].providing_module.endswith(
                "src/datrix_fixture_ep/plugin.py"
            ),
        )
        unresolved_ep_hits = _entry_point_hits("datrix_fixture_ep.nowhere", "DefinedPlugin")
        ok &= _check(
            "an entry point naming a module that resolves to nothing on disk is "
            "exactly one entry_point hit attributed to the dotted path",
            len(unresolved_ep_hits) == 1
            and unresolved_ep_hits[0].providing_module
            == "datrix_fixture_ep.nowhere.plugin",
        )

        # Relative imports resolve to their absolute module from the file's
        # own dotted name, on both the provider and the consumer side.
        rel_pkg_dir = fixture_src / "relpkg"
        rel_pkg_dir.mkdir(parents=True, exist_ok=True)
        (rel_pkg_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        relative_all_hits = _provider_hits(
            "datrix_fixture/relpkg/__init__.py",
            "from .a import X\n\n__all__ = ['X']\n",
        )
        ok &= _check(
            "from .a import X + __all__ = ['X'] is exactly one provider hit",
            len(relative_all_hits) == 1
            and relative_all_hits[0].kind == "provider"
            and relative_all_hits[0].name == "X",
        )

        relative_own_consumer_hits = _reexport_facade_consumer_hits(
            rel_pkg_dir / "__init__.py", packages, scratch_dir
        )
        ok &= _check(
            "from .a import X is zero consumer hits when a.py defines X",
            relative_own_consumer_hits == [],
        )

        rel_sub_dir = fixture_src / "relsub"
        rel_sub_dir.mkdir(parents=True, exist_ok=True)
        (rel_sub_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        relative_submodule_hits = _provider_hits(
            "datrix_fixture/relsub/__init__.py",
            "from . import a\n\n__all__ = ['a']\n",
        )
        relative_submodule_consumer_hits = _reexport_facade_consumer_hits(
            rel_sub_dir / "__init__.py", packages, scratch_dir
        )
        ok &= _check(
            "from . import submodule is zero provider and zero consumer hits",
            relative_submodule_hits == [] and relative_submodule_consumer_hits == [],
        )

        relative_consumer_file = rel_pkg_dir / "relative_consumer.py"
        relative_consumer_file.write_text("from . import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        relative_consumer_hits = _reexport_facade_consumer_hits(
            relative_consumer_file, packages, scratch_dir
        )
        ok &= _check(
            "a relative consumer importing a re-exported name through a facade "
            "is exactly one consumer hit, resolved to the defining module",
            len(relative_consumer_hits) == 1
            and relative_consumer_hits[0].kind == "consumer"
            and relative_consumer_hits[0].providing_module
            == "datrix_fixture/relpkg/__init__.py"
            and relative_consumer_hits[0].defining_module == "datrix_fixture.relpkg.a",
        )

        relative_unresolved_file = rel_pkg_dir / "relative_unresolved.py"
        relative_unresolved_file.write_text("from .no_such import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        relative_unresolved_hits = _reexport_facade_consumer_hits(
            relative_unresolved_file, packages, scratch_dir
        )
        ok &= _check(
            "a relative import of a module that resolves to nothing on disk is "
            "one unresolved hit",
            len(relative_unresolved_hits) == 1
            and relative_unresolved_hits[0].kind == "unresolved"
            and relative_unresolved_hits[0].providing_module
            == "datrix_fixture.relpkg.no_such",
        )

        # A package's root-level modules (conftest.py) are in the scan scope.
        conftest_package_root = scratch_dir / "datrix-root-scan"
        (conftest_package_root / "src" / "datrix_root_scan").mkdir(parents=True)
        (conftest_package_root / "conftest.py").write_text("\n", encoding="utf-8")
        scoped_files = _reexport_facade_scan_files(
            {
                "datrix_root_scan": PackageInfo(
                    name="datrix_root_scan",
                    root=conftest_package_root,
                    src_dir=conftest_package_root / "src" / "datrix_root_scan",
                )
            },
            scratch_dir,
        )
        ok &= _check(
            "a package's root-level conftest.py is in the re-export-facade scan scope",
            conftest_package_root / "conftest.py" in scoped_files,
        )

        # The shared scripts package resolves at the location datrix_scripts.paths
        # declares, so a script importing it is not an unresolved hit.
        scripts_package_dir = scratch_dir / SCRIPTS_PACKAGE_DIR.relative_to(WORKSPACE_DIR)
        scripts_package_dir.mkdir(parents=True)
        (scripts_package_dir / "__init__.py").write_text("\n", encoding="utf-8")
        (scripts_package_dir / "leaf.py").write_text("X = 1\n", encoding="utf-8")
        script_file = scratch_dir / "datrix" / "scripts" / "dev" / "lib" / "uses_leaf.py"
        script_file.parent.mkdir(parents=True)
        script_file.write_text(
            f"from {SCRIPTS_PACKAGE_DIR.name}.leaf import X\n"
            f"from {SCRIPTS_PACKAGE_DIR.name}.no_such import Y\n",
            encoding="utf-8",
        )
        _parse_module_source.cache_clear()
        script_hits = _reexport_facade_consumer_hits(
            script_file, _with_scripts_package(packages, scratch_dir), scratch_dir
        )
        ok &= _check(
            "an import of the shared scripts package resolves at its declared home: "
            "a name its module defines is zero hits, a missing module is one unresolved hit",
            [(hit.kind, hit.name) for hit in script_hits] == [("unresolved", "Y")],
        )
        unregistered_hits = _reexport_facade_consumer_hits(script_file, packages, scratch_dir)
        ok &= _check(
            "without the scripts package registered both imports are unresolved "
            "(the resolution above is what clears the defined name)",
            sorted(hit.name for hit in unregistered_hits) == ["X", "Y"],
        )

        ok &= _self_test_reexport_facade_extended_shapes(scratch_dir, fixture_src, packages)
    finally:
        _analyze_module_file.cache_clear()
        _parse_module_source.cache_clear()
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"reexport-facade-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        init_path = _self_test_reexport_facade_build_fixture_monorepo(tmp_root)
        clean_source = init_path.read_text(encoding="utf-8")

        baseline_path = (
            tmp_root / "datrix" / "scripts" / "config" / "reexport-facade-baseline.toml"
        )
        ok &= _check(
            "the fixture carries no re-export-facade baseline file",
            not baseline_path.exists(),
        )

        clean_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture package exits 0 with the baseline file absent, "
            f"got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        init_path.write_text(
            "from datrix_codegen_fixture.sub import VALUE\n\n__all__ = ['VALUE']\n",
            encoding="utf-8",
        )
        failing_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"planted provider-side facade exits 1 with the baseline file absent, "
            f"got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file, line and name",
            "__init__.py:1 VALUE" in failing_result.stdout,
        )

        # A hand-authored baseline at the old path must not suppress the
        # planted facade, and the check must not resurrect or rewrite it.
        stray_baseline = (
            "[[baseline]]\n"
            'file = "datrix-codegen-fixture/src/datrix_codegen_fixture/__init__.py"\n'
            "count = 5\n"
        )
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(stray_baseline, encoding="utf-8")
        stray_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"a stray hand-authored baseline does not suppress a planted facade, "
            f"got exit {stray_result.returncode}",
            stray_result.returncode == 1,
        )
        ok &= _check(
            "the check leaves a stray baseline file untouched",
            baseline_path.read_text(encoding="utf-8") == stray_baseline,
        )
        baseline_path.unlink()

        update_result = _self_test_reexport_facade_run_cli(tmp_root, "--update-baseline")
        ok &= _check(
            f"--update-baseline cannot make a planted facade pass, "
            f"got exit {update_result.returncode}",
            update_result.returncode == 1,
        )
        ok &= _check(
            "--update-baseline writes no re-export-facade baseline file",
            not baseline_path.exists(),
        )

        init_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        # Filtered worklist: plant the same provider-side facade AND a
        # consumer that imports through it, then prove -ShowFiles
        # -FacadeModule prints both sites, the consumer line naming the
        # module that actually defines the name.
        init_path.write_text(
            "from datrix_codegen_fixture.sub import VALUE\n\n__all__ = ['VALUE']\n",
            encoding="utf-8",
        )
        fixture_src_dir = tmp_root / "datrix-codegen-fixture" / "src" / "datrix_codegen_fixture"
        consumer_path = fixture_src_dir / "consumer.py"
        consumer_path.write_text(
            "from datrix_codegen_fixture import VALUE\n", encoding="utf-8"
        )
        worklist_result = _self_test_reexport_facade_run_cli(
            tmp_root,
            "--verbose",
            "--facade-module",
            "datrix_codegen_fixture",
        )
        ok &= _check(
            "the filtered worklist prints the planted provider hit",
            "[provider]" in worklist_result.stdout and "VALUE" in worklist_result.stdout,
        )
        ok &= _check(
            "the filtered worklist prints the consumer hit with its "
            "resolved defining module",
            "[consumer]" in worklist_result.stdout
            and "(defined by datrix_codegen_fixture.sub)" in worklist_result.stdout,
        )

        consumer_package_result = _self_test_reexport_facade_run_cli(
            tmp_root,
            "--verbose",
            "--consumer-package",
            "datrix-codegen-fixture",
        )
        ok &= _check(
            "-ConsumerPackage matching the site's own repo keeps its line",
            "consumer.py" in consumer_package_result.stdout,
        )

        consumer_path.unlink()
        init_path.write_text(clean_source, encoding="utf-8")
        final_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"removing both mutations clears the failure, got exit {final_result.returncode}",
            final_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def self_test_checks() -> list[NamedCheck]:
    """The re-export facade scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [self_test_check(_self_test_reexport_facade_scanner)]
