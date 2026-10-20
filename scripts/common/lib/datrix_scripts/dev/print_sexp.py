"""Print the tree-sitter parse tree of Datrix source as a corpus-style S-expression.

The module behind ``dev/print-sexp.ps1`` (and its ``.sh`` twin). Parses with the built Datrix
grammar (``TreeSitterParser.parse_tree``, the same compiled parser the language package and its
tests load -- the native ``tree-sitter`` CLI cannot load that self-built library on every host) and
prints the tree in the layout of a tree-sitter corpus test: two-space indentation, closing
parentheses on the last child's line, so the output can be pasted into a corpus file as the
expected tree. The editable installs are checked first.

Named nodes only by default; ``--all`` also prints anonymous nodes (keywords, punctuation) as
their quoted text. ``MISSING`` nodes print as ``(MISSING <type>)``.

Exit codes: 0 = the tree has no error, 1 = it contains ERROR or MISSING nodes (the tree is still
printed) or the package install check failed, 2 = the input could not be read.

Usage:
    python -m datrix_scripts.dev.print_sexp --path FILE.dtrx [--all]
    python -m datrix_scripts.dev.print_sexp --text "service s { }" [--all]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

if TYPE_CHECKING:
    from tree_sitter import Node

MODULE: Final = "datrix_scripts.dev.print_sexp"
WRAPPER: Final = "print-sexp"
EXIT_CLEAN: Final[int] = 0
EXIT_HAS_ERROR: Final[int] = 1
EXIT_USAGE: Final[int] = 2
INDENT: Final[str] = "  "
SOURCE_ENCODING: Final[str] = "utf-8-sig"
_PLANTED_ERROR_SOURCE: Final = "enum Status { Active, Inactive }"
_MISSING_FILE: Final = Path("no-such-print-sexp-input.dtrx")


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


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/print-sexp.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("positional_path", nargs="?", type=Path, metavar="PATH",
                        help="as --path, for a caller of the .sh twin")
    parser.add_argument("--path", type=Path, help="A .dtrx file.")
    parser.add_argument("--text", help="Datrix source given inline instead of a file.")
    parser.add_argument("--all", action="store_true", help="Also print anonymous nodes.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a parse error exits 1 with the tree, an unreadable file exits 2.")
    parser.set_defaults(debug=False)
    return parser


def _source(args: argparse.Namespace) -> tuple[str, Path | None] | None:
    """The source text and its file (None for --text); None when the file cannot be read (reported)."""
    given = [value for value in (args.path, args.positional_path, args.text) if value is not None]
    if len(given) != 1:
        raise UsageError("Pass exactly one input: -Path <file.dtrx> or -Text '<source>'.")
    if args.text is not None:
        return args.text, None
    path: Path = args.path if args.path is not None else args.positional_path
    if not path.is_file():
        print(f"No such file: {path}. Pass a .dtrx file or --text.", file=sys.stderr)
        return None
    return path.read_text(encoding=SOURCE_ENCODING), path


def print_tree(args: argparse.Namespace) -> int:
    """Parse the input *args* name and print its tree; the exit code."""
    from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser

    source = _source(args)
    if source is None:
        return EXIT_USAGE
    tree = TreeSitterParser().parse_tree(*source)
    print("\n".join(render(tree.root_node, args.all)))
    if tree.root_node.has_error:
        print("has_error: the tree contains ERROR or MISSING nodes", file=sys.stderr)
        return EXIT_HAS_ERROR
    return EXIT_CLEAN


def _check_a_parse_error_prints_the_tree_and_exits_1() -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = print_tree(build_parser().parse_args([f"--text={_PLANTED_ERROR_SOURCE}", "--all"]))
    assert code == EXIT_HAS_ERROR, f"source with a parse error must exit {EXIT_HAS_ERROR}; got {code}"
    lines = out.getvalue().splitlines()
    assert lines[0] == "(source_file" and "(ERROR" in lines[1], f"expected the corpus tree with its ERROR node; got {lines}"
    assert '"{"' in out.getvalue(), "--all must print the anonymous nodes"
    assert out.getvalue().count("(") == out.getvalue().count(")"), "every node the tree opens must be closed"


def _check_an_unreadable_file_exits_2() -> None:
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = print_tree(build_parser().parse_args([f"--path={_MISSING_FILE}"]))
    assert code == EXIT_USAGE and "No such file" in err.getvalue(), (code, err.getvalue())
    expect_usage_error(lambda: _source(build_parser().parse_args([])), "exactly one input")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_parse_error_prints_the_tree_and_exits_1, _check_an_unreadable_file_exits_2]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_HAS_ERROR
    return print_tree(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
