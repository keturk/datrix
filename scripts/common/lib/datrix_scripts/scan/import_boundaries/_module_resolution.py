"""Resolve a scanned file or dotted import to the Datrix module (src or test tree) that defines it."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_scripts.scan.import_boundaries._ast_common import PackageInfo


@dataclass(frozen=True)
class _ResolvedDatrixModule:
    """A policed dotted module path resolved to the real file that defines
    it -- either an ordinary module (``foo/bar.py``) or a package
    (``foo/bar/__init__.py``, ``is_package=True``). A test-tree directory
    with no ``__init__.py`` is a namespace package (``is_namespace=True``):
    ``file_path`` is then the directory itself and it defines no names."""

    file_path: Path
    is_package: bool
    is_namespace: bool = False


_DATRIX_MODULE_ROOT_PREFIX = "datrix"
_TEST_TREE_ROOT = "tests"


def _is_datrix_module_path(dotted_module: str) -> bool:
    """True when *dotted_module*'s root segment looks like a Datrix package
    import root (``datrix_common``, ``datrix_codegen_kernel``, ...) --
    scopes the re-export-facade scan to Datrix's own module graph, excluding
    every third-party and standard-library import."""
    return dotted_module.split(".", 1)[0].startswith(_DATRIX_MODULE_ROOT_PREFIX)


def _resolve_datrix_module(
    dotted_module: str, packages: dict[str, PackageInfo]
) -> _ResolvedDatrixModule | None:
    """Resolve *dotted_module* to the real file that defines it, or
    ``None`` if its root package is not discovered or the path does not
    exist on disk under that package's ``src/`` tree."""
    segments = dotted_module.split(".")
    package_info = packages.get(segments[0])
    if package_info is None:
        return None
    remainder = segments[1:]
    target_dir = package_info.src_dir.joinpath(*remainder)
    if remainder:
        module_file = target_dir.with_suffix(".py")
        if module_file.is_file():
            return _ResolvedDatrixModule(file_path=module_file, is_package=False)
    package_init = target_dir / "__init__.py"
    if package_init.is_file():
        return _ResolvedDatrixModule(file_path=package_init, is_package=True)
    return None


def _is_policed_module_path(dotted_module: str) -> bool:
    """True when *dotted_module* is a Datrix module or a test-tree module
    (``tests.<module>``) -- every module a facade can hide a name behind."""
    return (
        _is_datrix_module_path(dotted_module)
        or dotted_module.split(".", 1)[0] == _TEST_TREE_ROOT
    )


def _owning_package(
    file_path: Path, packages: dict[str, PackageInfo]
) -> PackageInfo | None:
    """The discovered package whose repository directory contains *file_path*."""
    for package_info in packages.values():
        try:
            file_path.relative_to(package_info.root)
        except ValueError:
            continue
        return package_info
    return None


def _resolve_test_tree_module(
    dotted_module: str, owner: PackageInfo
) -> _ResolvedDatrixModule | None:
    """Resolve ``tests.<module>`` against *owner*'s own ``tests/`` tree -- the
    pytest rootdir anchors ``tests`` per package, so the same dotted name
    names a different file in every package."""
    remainder = dotted_module.split(".")[1:]
    target = (owner.root / _TEST_TREE_ROOT).joinpath(*remainder)
    if remainder:
        module_file = target.with_suffix(".py")
        if module_file.is_file():
            return _ResolvedDatrixModule(file_path=module_file, is_package=False)
    package_init = target / "__init__.py"
    if package_init.is_file():
        return _ResolvedDatrixModule(file_path=package_init, is_package=True)
    if target.is_dir():
        return _ResolvedDatrixModule(
            file_path=target, is_package=True, is_namespace=True
        )
    return None


def _resolve_policed_module(
    dotted_module: str, packages: dict[str, PackageInfo], context_file: Path
) -> _ResolvedDatrixModule | None:
    """Resolve a Datrix or test-tree module path. A test-tree path is
    anchored at the package that owns *context_file* (the importing file);
    a file outside every package has no ``tests`` root to resolve against."""
    if dotted_module.split(".", 1)[0] != _TEST_TREE_ROOT:
        return _resolve_datrix_module(dotted_module, packages)
    owner = _owning_package(context_file, packages)
    if owner is None:
        return None
    return _resolve_test_tree_module(dotted_module, owner)


def _is_submodule_member(resolved: _ResolvedDatrixModule, name: str) -> bool:
    """True when *name* is itself an importable submodule/subpackage of the
    resolved package -- a plain package traversal (`from pkg import
    submodule`), never a facade hit."""
    if not resolved.is_package:
        return False
    package_dir = (
        resolved.file_path if resolved.is_namespace else resolved.file_path.parent
    )
    # Python module names are case-sensitive but a Windows/macOS filesystem
    # is not, so `Crypto` would otherwise "exist" as `crypto.py`. Match the
    # directory listing's own spelling instead of probing the path.
    entries = {entry.name for entry in package_dir.iterdir()}
    if f"{name}.py" in entries:
        return True
    return name in entries and (package_dir / name / "__init__.py").is_file()


def _dotted_module_name_for_file(
    file_path: Path, packages: dict[str, PackageInfo]
) -> str | None:
    """The dotted module path a ``src/`` or ``tests/`` file corresponds to,
    for the provider-side shape's ``-FacadeModule`` filter/display name and
    for resolving the file's own relative imports -- ``datrix_x.mod`` for a
    ``src/`` file, ``tests.mod`` for a file in a package's ``tests/`` tree,
    ``None`` for any other file (a ``datrix/scripts/*.py`` utility or a
    package root-level ``conftest.py`` has no importable module identity of
    its own, so it is filtered by its relative file path only)."""
    for package_name, package_info in packages.items():
        try:
            relative = file_path.relative_to(package_info.src_dir)
        except ValueError:
            continue
        parts = list(relative.parts)
        if parts and parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][: -len(".py")]
        return ".".join([package_name, *parts]) if parts else package_name
    return _test_tree_module_name(file_path, packages)


def _test_tree_module_name(
    file_path: Path, packages: dict[str, PackageInfo]
) -> str | None:
    """``tests.<module>`` for a file under a discovered package's ``tests/``
    tree, ``None`` for every other file."""
    owner = _owning_package(file_path, packages)
    if owner is None:
        return None
    try:
        relative = file_path.relative_to(owner.root / _TEST_TREE_ROOT)
    except ValueError:
        return None
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join([_TEST_TREE_ROOT, *parts])


def _absolute_import_module(
    stmt: ast.ImportFrom, file_path: Path, own_dotted: str | None
) -> str | None:
    """The absolute dotted module a ``from ... import`` statement names.

    An absolute import returns its own ``module``. A relative import
    (``level > 0``) is resolved against the scanned file's own dotted name
    *own_dotted* (``from . import sub`` names the file's package itself,
    ``from .a import X`` names ``<package>.a``). Returns ``None`` when the
    statement has no module to resolve to (``from . import x`` in a file
    with no dotted name -- a file outside every package's ``src/`` tree can
    only name its own siblings, never a Datrix module).

    Raises:
        ValueError: A relative import climbs above the file's top-level
            package, which Python itself rejects at import time.
    """
    if stmt.level == 0:
        return stmt.module
    if own_dotted is None:
        return None
    own_parts = own_dotted.split(".")
    package_parts = own_parts if file_path.name == "__init__.py" else own_parts[:-1]
    ascend = stmt.level - 1
    if ascend >= len(package_parts):
        raise ValueError(
            f"{file_path}:{stmt.lineno}: relative import with level {stmt.level} climbs "
            f"above the top-level package of {own_dotted!r}; use an import that stays "
            f"inside the package, or the absolute module path."
        )
    base_parts = package_parts[: len(package_parts) - ascend]
    module_parts = stmt.module.split(".") if stmt.module else []
    return ".".join([*base_parts, *module_parts])
