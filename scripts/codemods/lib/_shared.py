"""Helpers shared by the codemods in this folder."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import libcst as cst
from bowler import Query

# Set to "1" by ``run-codemod.ps1 -Write`` (``datrix_scripts.codemods.run_codemod.WRITE_ENV``).
WRITE_ENV: Final = "DATRIX_CODEMOD_WRITE"


def finish(query: Query) -> Query:
    """Run *query*: write the rewrite when ``run-codemod -Write`` asked for it, else print its diff.

    Bowler writes a file through text mode, which respells every line ending as the platform's, so each
    written file gets its own back.
    """
    if os.environ.get(WRITE_ENV) != "1":
        return query.diff()
    newlines: dict[str, bytes] = {}

    def note_newline(filename: str, hunk: list[str]) -> bool:
        newlines[filename] = b"\r\n" if b"\r\n" in Path(filename).read_bytes() else b"\n"
        return True

    written = query.process(note_newline).write()
    for filename, newline in newlines.items():
        path = Path(filename)
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline))
    return written


def _module_expression(dotted: str) -> cst.BaseExpression:
    """``a`` or ``a.b`` as a libcst expression (the two shapes the codemods configure)."""
    parts = dotted.split(".")
    if len(parts) == 1:
        return cst.Name(parts[0])
    return cst.Attribute(value=cst.Name(parts[0]), attr=cst.Name(parts[1]))


def add_from_import(module: cst.Module, from_module: str, name: str) -> cst.Module:
    """``module`` with ``from <from_module> import <name>`` after its last top-level import."""
    import_stmt = cst.SimpleStatementLine(
        body=[
            cst.ImportFrom(
                module=_module_expression(from_module),
                names=[cst.ImportAlias(cst.Name(name))],
            )
        ],
    )
    body = list(module.body)
    insert_at = 0
    for index, statement in enumerate(body):
        if isinstance(statement, cst.SimpleStatementLine) and any(
            isinstance(part, (cst.Import, cst.ImportFrom)) for part in statement.body
        ):
            insert_at = index + 1
    return module.with_changes(body=body[:insert_at] + [import_stmt] + body[insert_at:])
