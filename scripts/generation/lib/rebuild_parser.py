#!/usr/bin/env python3
"""Rebuild the Datrix Tree-sitter parser through the package's own build.

A thin command over ``datrix_language.parser.tree_sitter_datrix.build``. The grammar
directory and its ``build/`` child come from the installed package; everything about
building -- staleness, the per-platform library and record names, pinning the compiler
to the interpreter's architecture, and the post-build load check -- is that module's
alone, shared with the package build backend and the test session.

Without ``--force`` the parser is built only when stale (``build_if_stale``); with it,
always (``ensure_grammar_compiled(force=True)``). Prints the library path and whether a
build ran, and exits 0 on success, 1 with the ``ParseError`` text on failure.
"""

import argparse
import logging
import sys
from pathlib import Path

import datrix_language.parser.tree_sitter_datrix as tree_sitter_datrix
from datrix_common.errors.parse import ParseError
from datrix_language.parser.tree_sitter_datrix.build import (
    GRAMMAR_FILENAME,
    build_if_stale,
    compiled_library_path,
    ensure_grammar_compiled,
    grammar_hash_path,
    interpreter_platform_tag,
    should_rebuild_grammar,
)

_BUILD_DIR_NAME = "build"
_EXIT_SUCCESS = 0
_EXIT_FAILURE = 1


def _build_parser(grammar_dir: Path, build_dir: Path, force: bool) -> tuple[Path, bool]:
    """Build through the package; return the library path and whether a build ran.

    Raises:
        ParseError: The grammar is missing, the toolchain cannot build it, or the built
            library does not load into this interpreter.
    """
    if force:
        return ensure_grammar_compiled(grammar_dir, build_dir, force=True), True
    stale = should_rebuild_grammar(
        grammar_dir / GRAMMAR_FILENAME,
        compiled_library_path(build_dir),
        grammar_hash_path(build_dir),
    )
    return build_if_stale(grammar_dir, build_dir), stale


def rebuild_parser(force: bool) -> int:
    """Rebuild the package's parser; return the process exit code."""
    grammar_dir = Path(tree_sitter_datrix.__file__).parent
    build_dir = grammar_dir / _BUILD_DIR_NAME
    print(f"Grammar: {grammar_dir / GRAMMAR_FILENAME}")
    print(f"Platform: {interpreter_platform_tag()}")
    try:
        library, built = _build_parser(grammar_dir, build_dir, force)
    except ParseError as error:
        print(f"Parser build failed:\n{error}", file=sys.stderr)
        return _EXIT_FAILURE
    print(f"Library: {library}")
    if built:
        print("Built: the parser was compiled and its staleness record written.")
    else:
        print("Already fresh: no build was needed (pass -Force to rebuild anyway).")
    return _EXIT_SUCCESS


def main() -> None:
    """Parse the command line and run the rebuild."""
    parser = argparse.ArgumentParser(description="Rebuild the Datrix Tree-sitter parser")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Rebuild even if the parser is fresh",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    sys.exit(rebuild_parser(force=args.force))


if __name__ == "__main__":
    main()
