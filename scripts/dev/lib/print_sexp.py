#!/usr/bin/env python3
"""Print the tree-sitter parse tree of Datrix source as a corpus-style S-expression.

Parses with the built Datrix grammar (``TreeSitterParser.parse_tree``, the same compiled parser
the language package and its tests load -- the native ``tree-sitter`` CLI cannot load that
self-built library on every host) and prints the tree in the layout of a tree-sitter corpus
test: two-space indentation, closing parentheses on the last child's line, so the output can
be pasted into a corpus file as the expected tree.

Named nodes only by default; ``--all`` also prints anonymous nodes (keywords, punctuation) as
their quoted text. ``MISSING`` nodes print as ``(MISSING <type>)``.

Exit codes: 0 = the tree has no error, 1 = it contains ERROR or MISSING nodes (the tree is still
printed), 2 = the input could not be read.

Usage:
    python print_sexp.py FILE.dtrx [--all]
    python print_sexp.py --text "service s { }" [--all]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
from tree_sitter import Node

EXIT_CLEAN: Final[int] = 0
EXIT_HAS_ERROR: Final[int] = 1
EXIT_USAGE: Final[int] = 2
INDENT: Final[str] = "  "
SOURCE_ENCODING: Final[str] = "utf-8-sig"


def _label(node: Node) -> str:
    if node.is_missing:
        return f"(MISSING {node.type}"
    if node.is_named:
        return f"({node.type}"
    return f'"{node.type}"'


def render(node: Node, include_anonymous: bool, depth: int = 0) -> list[str]:
    """Corpus-style lines for *node* and its subtree."""
    indent = INDENT * depth
    if not node.is_named and not node.is_missing:
        return [f"{indent}{_label(node)}"]
    children = [child for child in node.children if include_anonymous or child.is_named or child.is_missing]
    if not children:
        return [f"{indent}{_label(node)})"]
    lines = [f"{indent}{_label(node)}"]
    for child in children:
        lines.extend(render(child, include_anonymous, depth + 1))
    lines[-1] += ")"
    return lines


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("file", nargs="?", type=Path, help="A .dtrx file.")
    source.add_argument("--text", help="Datrix source given inline.")
    parser.add_argument("--all", action="store_true", help="Also print anonymous nodes.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    if args.text is not None:
        source, origin = args.text, None
    else:
        if not args.file.is_file():
            print(f"No such file: {args.file}. Pass a .dtrx file or --text.", file=sys.stderr)
            return EXIT_USAGE
        source, origin = args.file.read_text(encoding=SOURCE_ENCODING), args.file
    tree = TreeSitterParser().parse_tree(source, origin)
    print("\n".join(render(tree.root_node, args.all)))
    if tree.root_node.has_error:
        print("has_error: the tree contains ERROR or MISSING nodes", file=sys.stderr)
        return EXIT_HAS_ERROR
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
