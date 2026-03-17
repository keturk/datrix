"""
Example custom modifier using libCST with Bowler: on each module (select_root),
optionally add `logger = logging.getLogger(__name__)` after imports.

Bowler passes libCST nodes to modifiers; select_root() matches the file root.
Adjust the condition and inserted node for your use case. Run with .diff() first.

Usage:
  .\run-codemod.ps1 05_custom_modifier [paths...]
  bowler run scripts/dev/codemods/05_custom_modifier.py -- [paths...]
"""

from __future__ import annotations

import sys

import libcst as cst
from bowler import Query


def add_logger_if_missing(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    """If this is a module with no 'logger' assignment, add one after imports."""
    if not isinstance(node, cst.Module):
        return None
    body = list(node.body)
    has_logger = any(
        isinstance(stmt, cst.SimpleStatementLine)
        and any(
            isinstance(part, cst.Assign)
            and len(part.targets) == 1
            and isinstance(part.targets[0].target, cst.Name)
            and part.targets[0].target.value == "logger"
            for part in stmt.body
        )
        for stmt in body
    )
    if has_logger:
        return None
    insert_idx = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine) and any(
            isinstance(part, (cst.Import, cst.ImportFrom)) for part in stmt.body
        ):
            insert_idx = i + 1
    logger_line = cst.SimpleStatementLine(
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
    new_body = body[:insert_idx] + [logger_line] + body[insert_idx:]
    return node.with_changes(body=new_body)


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]

    (
        Query(*paths)
        .select_root()
        .modify(add_logger_if_missing)
        .diff()
    )


if __name__ == "__main__":
    main()
