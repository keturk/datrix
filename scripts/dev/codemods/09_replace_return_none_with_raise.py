"""
Replace "return None" with "raise SomeError(...)" in functions (fail-fast style).

Configure ERROR_MODULE, ERROR_CLASS, and optionally restrict to function names
matching FUNC_NAME_PATTERN (None = all functions). Adds import for the exception
if missing. Use .diff() to preview.

Usage:
  .\run-codemod.ps1 09_replace_return_none_with_raise [paths...]
  bowler run scripts/dev/codemods/09_replace_return_none_with_raise.py -- datrix-language/src

Edit the constants below for your exception type and optional function filter.
"""

from __future__ import annotations

import re
import sys

import libcst as cst
from bowler import Query

ERROR_MODULE = "datrix_common.errors"
ERROR_CLASS = "EntityNotFoundError"
# Only in functions whose name matches this regex; None = all functions.
FUNC_NAME_PATTERN: re.Pattern[str] | None = None  # e.g. re.compile(r"^get_|^find_")


class ReturnNoneToRaiseTransformer(cst.CSTTransformer):
    """Replaces return None with raise ERROR_CLASS(...) and ensures import."""

    def __init__(
        self,
        error_module: str,
        error_class: str,
        func_name_pattern: re.Pattern[str] | None,
    ) -> None:
        self.error_module = error_module
        self.error_class = error_class
        self.func_name_pattern = func_name_pattern
        self._current_func: str | None = None
        self._needs_import = False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self._current_func = node.name.value
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> cst.FunctionDef:
        self._current_func = None
        return node

    def leave_Return(
        self, original: cst.Return, updated: cst.Return
    ) -> cst.BaseStatement | cst.RemovalSentinel:
        if not isinstance(updated.value, cst.Name) or updated.value.value != "None":
            return updated
        if self.func_name_pattern is not None and self._current_func is not None:
            if not self.func_name_pattern.search(self._current_func):
                return updated
        self._needs_import = True
        raise_expr = cst.Call(
            func=cst.Name(self.error_class),
            args=[cst.Arg(cst.SimpleString('"Not found."'))],
        )
        return cst.Raise(exc=raise_expr)

    def leave_Module(
        self, original: cst.Module, updated: cst.Module
    ) -> cst.Module:
        if not self._needs_import:
            return updated
        parts = self.error_module.split(".")
        if len(parts) == 1:
            module_node: cst.BaseExpression = cst.Name(parts[0])
        else:
            module_node = cst.Attribute(
                value=cst.Name(parts[0]),
                attr=cst.Name(parts[1]),
            )
        import_stmt = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=module_node,
                    names=[cst.ImportAlias(cst.Name(self.error_class))],
                )
            ],
        )
        body = list(updated.body)
        insert_at = 0
        for i, stmt in enumerate(body):
            if isinstance(stmt, cst.SimpleStatementLine) and any(
                isinstance(part, (cst.Import, cst.ImportFrom)) for part in stmt.body
            ):
                insert_at = i + 1
        new_body = body[:insert_at] + [import_stmt] + body[insert_at:]
        return updated.with_changes(body=new_body)


def _transform_module(
    node: cst.CSTNode,
    error_module: str,
    error_class: str,
    func_name_pattern: re.Pattern[str] | None,
) -> cst.CSTNode | None:
    if not isinstance(node, cst.Module):
        return None
    transformer = ReturnNoneToRaiseTransformer(
        error_module, error_class, func_name_pattern
    )
    try:
        return node.visit(transformer)
    except Exception:
        return None


def replace_return_none(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    result = _transform_module(
        node, ERROR_MODULE, ERROR_CLASS, FUNC_NAME_PATTERN
    )
    return result


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]

    (
        Query(*paths)
        .select_root()
        .modify(replace_return_none)
        .diff()
    )


if __name__ == "__main__":
    main()
