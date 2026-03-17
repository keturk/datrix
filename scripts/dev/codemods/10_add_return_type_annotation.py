"""
Add "-> None" (or another type) to functions that have no return annotation.

Configure RETURN_ANNOTATION (default "None"). Use .diff() to preview.

Usage:
  .\run-codemod.ps1 10_add_return_type_annotation [paths...]
  bowler run scripts/dev/codemods/10_add_return_type_annotation.py -- datrix-language/src
"""

from __future__ import annotations

import sys

import libcst as cst
from bowler import Query

RETURN_ANNOTATION = "None"  # e.g. "None", "bool", "str"


class AddReturnAnnotationTransformer(cst.CSTTransformer):
    """Adds return annotation to function defs that lack one."""

    def __init__(self, annotation: str) -> None:
        self.annotation = annotation

    def leave_FunctionDef(
        self, original: cst.FunctionDef, updated: cst.FunctionDef
    ) -> cst.FunctionDef:
        if updated.returns is not None:
            return updated
        return updated.with_changes(
            returns=cst.Annotation(annotation=cst.Name(self.annotation))
        )


def add_return_annotation(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    if not isinstance(node, cst.Module):
        return None
    transformer = AddReturnAnnotationTransformer(RETURN_ANNOTATION)
    return node.visit(transformer)


def main() -> None:
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["."]

    (
        Query(*paths)
        .select_root()
        .modify(add_return_annotation)
        .diff()
    )


if __name__ == "__main__":
    main()
