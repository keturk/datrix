"""
Add a decorator to all functions (or classes) with a given name. Structural/pattern change.

Edit DECORATOR_MODULE and DECORATOR_NAME below to add e.g. @deprecated or a custom decorator.
Use .diff() to preview.

Usage:
  .\run-codemod.ps1 07_add_decorator FUNC_OR_CLASS_NAME [paths...]
  bowler run scripts/dev/codemods/07_add_decorator.py -- my_func datrix-language/src

To add to classes instead, change .select_function to .select_class in main().
"""

from __future__ import annotations

import sys

import libcst as cst
from bowler import Query

# Configure: decorator to add (module.name or bare name)
DECORATOR_MODULE: str | None = None  # e.g. "functools"
DECORATOR_NAME: str = "wraps"  # e.g. "wraps" or "deprecated"


def _make_decorator() -> cst.BaseExpression:
    if DECORATOR_MODULE:
        return cst.Attribute(
            value=cst.Name(DECORATOR_MODULE),
            attr=cst.Name(DECORATOR_NAME),
        )
    return cst.Name(DECORATOR_NAME)


def add_decorator(
    node: cst.CSTNode,
    capture: dict,
    filename: str,
) -> cst.CSTNode | None:
    """Prepend one decorator to the node's decorator list."""
    if isinstance(node, cst.FunctionDef):
        new_dec = cst.Decorator(decorator=_make_decorator())
        existing = list(node.decorators)
        return node.with_changes(decorators=[new_dec] + existing)
    if isinstance(node, cst.ClassDef):
        new_dec = cst.Decorator(decorator=_make_decorator())
        existing = list(node.decorators)
        return node.with_changes(decorators=[new_dec] + existing)
    return None


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 2:
        name = sys.argv[1]
        if len(sys.argv) > 2:
            paths = sys.argv[2:]
    else:
        name = "my_func"

    (
        Query(*paths)
        .select_function(name)
        .modify(add_decorator)
        .diff()
    )


if __name__ == "__main__":
    main()
