"""
Replace print(...) with logger.info(...) and ensure logging + logger exist.

Fixes Datrix logging inconsistency: use standard logger instead of print.
Adds 'import logging' and 'logger = logging.getLogger(__name__)' when missing.
Drops print-only keyword args (file=, sep=, end=). Use .diff() to preview.

Usage:
  .\run-codemod.ps1 13_print_to_logger [paths...]
  bowler run scripts/dev/codemods/13_print_to_logger.py -- datrix-cli/src
"""

from __future__ import annotations

import sys

import libcst as cst
from bowler import Query


def _has_logger_definition(body: list[cst.BaseStatement]) -> bool:
    """Return True if the module already defines 'logger'."""
    for stmt in body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for part in stmt.body:
                if (
                    isinstance(part, cst.Assign)
                    and len(part.targets) == 1
                    and isinstance(part.targets[0].target, cst.Name)
                    and part.targets[0].target.value == "logger"
                ):
                    return True
    return False


def _module_root(mod: cst.BaseExpression) -> str | None:
    """Return the root module name (e.g. 'logging' for 'logging.handlers')."""
    if isinstance(mod, cst.Name):
        return mod.value
    if isinstance(mod, cst.Attribute):
        return _module_root(mod.value)
    return None


def _has_logging_import(body: list[cst.BaseStatement]) -> bool:
    """Return True if the module imports 'logging' (import logging or from logging import ...)."""
    for stmt in body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for part in stmt.body:
                if isinstance(part, cst.Import):
                    for alias in part.names:
                        name = alias.name
                        if isinstance(name, cst.Attribute):
                            name = name.attr
                        if isinstance(name, cst.Name) and name.value == "logging":
                            return True
                if isinstance(part, cst.ImportFrom) and part.module is not None:
                    root = _module_root(part.module)
                    if root == "logging":
                        return True
    return False


def _insert_after_imports_index(body: list[cst.BaseStatement]) -> int:
    """Return index after the last import statement (for inserting logger)."""
    idx = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine) and any(
            isinstance(part, (cst.Import, cst.ImportFrom)) for part in stmt.body
        ):
            idx = i + 1
    return idx


class ReplacePrintTransformer(cst.CSTTransformer):
    """Replaces print(...) with logger.info(...); keeps positional args, drops file/sep/end."""

    def __init__(self) -> None:
        self._replaced_any = False

    def leave_Call(
        self, original: cst.Call, updated: cst.Call
    ) -> cst.BaseExpression:
        if not isinstance(updated.func, cst.Name) or updated.func.value != "print":
            return updated
        pos_args = [a for a in updated.args if a.keyword is None]
        if len(pos_args) == 0:
            new_args = [cst.Arg(cst.SimpleString('""'))]
        elif len(pos_args) == 1:
            new_args = list(pos_args)
        else:
            format_str = " ".join(["%s"] * len(pos_args))
            new_args = [
                cst.Arg(cst.SimpleString(f'"{format_str}"')),
                *pos_args,
            ]
        self._replaced_any = True
        return updated.with_changes(
            func=cst.Attribute(
                value=cst.Name("logger"),
                attr=cst.Name("info"),
            ),
            args=new_args,
        )


def print_to_logger(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    """Replace print with logger.info and add logging/logger if missing."""
    if not isinstance(node, cst.Module):
        return None
    transformer = ReplacePrintTransformer()
    transformed = node.visit(transformer)
    if not transformer._replaced_any:
        return None
    body = list(transformed.body)
    has_logger = _has_logger_definition(body)
    has_logging = _has_logging_import(body)
    if has_logger and has_logging:
        return transformed
    insert_idx = _insert_after_imports_index(body)
    new_stmts: list[cst.SimpleStatementLine] = []
    if not has_logging:
        new_stmts.append(
            cst.SimpleStatementLine(body=[cst.Import(names=[cst.ImportAlias(cst.Name("logging"))])])
        )
    if not has_logger:
        new_stmts.append(
            cst.SimpleStatementLine(
                body=[
                    cst.Assign(
                        targets=[cst.AssignTarget(cst.Name("logger"))],
                        value=cst.Call(
                            func=cst.Attribute(
                                value=cst.Name("logging"),
                                attr=cst.Name("getLogger"),
                            ),
                            args=[cst.Arg(cst.Name("__name__"))],
                        ),
                    )
                ],
            )
        )
    new_body = body[:insert_idx] + new_stmts + body[insert_idx:]
    return transformed.with_changes(body=new_body)


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]

    (
        Query(*paths)
        .select_root()
        .modify(print_to_logger)
        .diff()
    )


if __name__ == "__main__":
    main()
