"""Collect the module-level functions and class methods of a package source tree.

One walker, shared by every script that compares function bodies across packages: the
behaviour-parity gate, the shared-home body gate and the duplicate-body report all enumerate
the same declarations, so they agree on what a "function" is. Nested functions are closures,
not declarations, and are never collected.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from datrix_scripts.behaviour_skeleton import (
    FunctionSource,
    SkeletonError,
    build_import_table,
    build_local_class_table,
    parse_module_or_raise,
)

#: The stem of a package's own module file -- the file that IS its package.
PACKAGE_INIT_STEM: Final[str] = "__init__"

#: ``ast.stmt`` attribute names whose value is a statement list the walker descends into to
#: find a def nested inside a non-function, non-class container (If/While/For/With/Try main
#: body + else + finally).
CONTAINER_BODY_ATTRS: Final[tuple[str, ...]] = ("body", "orelse", "finalbody")

FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef


def iter_source_files(
    src_dir: Path, suffixes: frozenset[str], skip_dir_names: frozenset[str]
) -> list[Path]:
    """Every file under ``src_dir`` with one of ``suffixes``, outside any ``skip_dir_names`` folder, sorted."""
    files: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in skip_dir_names for part in path.relative_to(src_dir).parts):
            continue
        files.append(path)
    return files


def terminal_name(node: ast.expr) -> str | None:
    """The last identifier of a name or attribute expression (``x`` -> ``x``, ``a.b.x`` -> ``x``).

    ``None`` when the expression is neither (a call, a subscript, a literal): it has no name.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def collect_module_and_method_defs(
    body: list[ast.stmt], enclosing_class: str | None
) -> list[tuple[FunctionDefNode, str | None]]:
    """Recursively collect every module-level or class-method function def
    reachable through non-function statement containers (If/While/For/With/
    Try), pairing each with its nearest enclosing class name.

    Never descends into a function's own body -- a nested function is a
    closure, not a declaration this walker tracks. A class nested inside
    another class resets ``enclosing_class`` to its own name (single-level
    qualification, ``ClassName.method_name``).

    Args:
        body: A statement list (a module body or a class body).
        enclosing_class: The nearest enclosing class's name, or ``None``.

    Returns:
        ``(node, enclosing_class)`` pairs, in source order.
    """
    found: list[tuple[FunctionDefNode, str | None]] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            found.extend(collect_module_and_method_defs(stmt.body, stmt.name))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((stmt, enclosing_class))
            continue
        for attr in CONTAINER_BODY_ATTRS:
            nested_body = getattr(stmt, attr, None)
            if nested_body:
                found.extend(collect_module_and_method_defs(nested_body, enclosing_class))
        for handler in getattr(stmt, "handlers", ()):
            found.extend(collect_module_and_method_defs(handler.body, enclosing_class))
    return found


def decorated_source_segment(source_lines: list[str], node: FunctionDefNode) -> str:
    """Verbatim source text of *node*, decorators included: whole source
    lines from the first decorator's line (or the ``def`` line) through the
    function's last line.

    Args:
        source_lines: The file's source, ``splitlines(keepends=True)``.
        node: The function/method AST node.

    Returns:
        The decorator(s) + def + body, as literal source text.

    Raises:
        SkeletonError: If ``node.end_lineno`` is unavailable.
    """
    if node.end_lineno is None:
        raise SkeletonError(
            f"AST node for {node.name!r} at line {node.lineno} has no end_lineno -- "
            f"expected ast.parse() to populate it (requires Python >= 3.8)."
        )
    start_line = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    return "".join(source_lines[start_line - 1 : node.end_lineno])


def dotted_package_for_file(src_dir: Path, file_path: Path) -> str:
    """The dotted package *file_path* lives in, for resolving its relative
    imports: ``pkg/sub/mod.py`` and ``pkg/sub/__init__.py`` alike live in
    ``pkg.sub`` (a package's ``__init__`` IS its package).

    Args:
        src_dir: The package's src root (e.g. ``.../src/datrix_codegen_python``).
        file_path: A ``.py`` file under *src_dir*.

    Returns:
        The dotted package path.
    """
    relative = file_path.relative_to(src_dir)
    return ".".join([src_dir.name, *relative.parts[:-1]])


def dotted_module_for_file(src_dir: Path, file_path: Path) -> str:
    """The dotted name of the module *file_path* is: ``pkg.sub.mod`` for
    ``pkg/sub/mod.py``, and ``pkg.sub`` for ``pkg/sub/__init__.py``.

    Args:
        src_dir: The package's src root (e.g. ``.../src/datrix_codegen_python``).
        file_path: A ``.py`` file under *src_dir*.

    Returns:
        The dotted module path.
    """
    package = dotted_package_for_file(src_dir, file_path)
    return package if file_path.stem == PACKAGE_INIT_STEM else f"{package}.{file_path.stem}"


def qualified_def_name(node: FunctionDefNode, enclosing_class: str | None) -> str:
    """``Class.method`` for a method, the bare name for a module-level function."""
    return f"{enclosing_class}.{node.name}" if enclosing_class else node.name


def collect_function_sources(src_dir: Path, package: str) -> list[FunctionSource]:
    """AST-walk every ``.py`` file under *src_dir* for module-level and
    class-method function/method definitions, building one ``FunctionSource``
    per declaration with its decorated source text and its own file's import
    table.

    Args:
        src_dir: A package's source root (e.g. a language's
            ``src/datrix_codegen_python`` directory).
        package: The label recorded on every returned ``FunctionSource`` (a
            registered language/platform name, or a folded label).

    Returns:
        Every declaration found, in file-then-source order. Empty if
        *src_dir* does not exist.

    Raises:
        SkeletonError: If a ``.py`` file under *src_dir* cannot be parsed --
            propagates unmodified, never caught here.
    """
    sources: list[FunctionSource] = []
    if not src_dir.is_dir():
        return sources
    for py_file in sorted(src_dir.rglob("*.py")):
        module = parse_module_or_raise(py_file)
        import_table = build_import_table(module, dotted_package_for_file(src_dir, py_file))
        local_classes = build_local_class_table(module, dotted_module_for_file(src_dir, py_file))
        source_lines = py_file.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        for node, enclosing_class in collect_module_and_method_defs(module.body, None):
            sources.append(
                FunctionSource(
                    package=package,
                    file_path=py_file,
                    line_number=node.lineno,
                    qualified_name=qualified_def_name(node, enclosing_class),
                    node=node,
                    source_text=decorated_source_segment(source_lines, node),
                    import_table=import_table,
                    local_classes=local_classes,
                )
            )
    return sources
