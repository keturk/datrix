"""
Replace "raise Exception(...)" with "raise SpecificError(...)" and add import.

Bulk validation/fix: use a specific exception type instead of generic Exception.
Configure ERROR_MODULE and ERROR_CLASS below. Use .diff() to preview.

Usage:
  .\run-codemod.ps1 12_replace_raise_exception [paths...]
  bowler run scripts/dev/codemods/12_replace_raise_exception.py -- datrix-language/src
"""

from __future__ import annotations

import sys

import libcst as cst
from bowler import Query

ERROR_MODULE = "datrix_common.errors"
ERROR_CLASS = "TransformError"  # or ValueError, EntityNotFoundError, etc.


class ReplaceExceptionTransformer(cst.CSTTransformer):
    """Replaces raise Exception(...) with raise ERROR_CLASS(...) and adds import."""

    def __init__(self, error_module: str, error_class: str) -> None:
        self.error_module = error_module
        self.error_class = error_class
        self._needs_import = False

    def leave_Raise(
        self, original: cst.Raise, updated: cst.Raise
    ) -> cst.Raise | cst.BaseStatement:
        if updated.exc is None:
            return updated
        if not isinstance(updated.exc, cst.Call):
            return updated
        if not isinstance(updated.exc.func, cst.Name):
            return updated
        if updated.exc.func.value != "Exception":
            return updated
        self._needs_import = True
        return updated.with_changes(
            exc=updated.exc.with_changes(func=cst.Name(self.error_class))
        )

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


def replace_exception(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    if not isinstance(node, cst.Module):
        return None
    transformer = ReplaceExceptionTransformer(ERROR_MODULE, ERROR_CLASS)
    return node.visit(transformer)


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]

    (
        Query(*paths)
        .select_root()
        .modify(replace_exception)
        .diff()
    )


if __name__ == "__main__":
    main()
