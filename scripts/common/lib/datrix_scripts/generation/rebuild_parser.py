"""Rebuild the Datrix Tree-sitter parser through the package's own build.

The module behind ``generation/rebuild-parser.ps1`` (and its ``.sh`` twin). A thin command over
``datrix_language.parser.tree_sitter_datrix.build``. The grammar directory and its ``build/`` child
come from the installed package; everything about building -- staleness, the per-platform library and
record names, pinning the compiler to the interpreter's architecture, and the post-build load check --
is that module's alone, shared with the package build backend and the test session.

Without ``--force`` the parser is built only when stale (``build_if_stale``); with it, always
(``ensure_grammar_compiled(force=True)``). Prints the library path and whether a build ran, and exits
0 on success, 1 with the ``ParseError`` text on failure.

Usage:
    python -m datrix_scripts.generation.rebuild_parser [--force] [--self-test]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

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

from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.generation.rebuild_parser"
WRAPPER: Final = "rebuild-parser"
_BUILD_DIR_NAME: Final = "build"
_EXIT_SUCCESS: Final = 0
_EXIT_FAILURE: Final = 1
_FAILURE_LINE: Final = "Parser build failed:"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/rebuild-parser.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--force", action="store_true", help="Rebuild even if the parser is fresh.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a grammar directory without grammar.js fails the build.")
    parser.set_defaults(debug=False)
    return parser


def _build(grammar_dir: Path, build_dir: Path, force: bool) -> tuple[Path, bool]:
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


def rebuild_parser(grammar_dir: Path, force: bool) -> int:
    """Rebuild the parser of *grammar_dir* into its ``build/``; return the process exit code."""
    build_dir = grammar_dir / _BUILD_DIR_NAME
    print(f"Grammar: {grammar_dir / GRAMMAR_FILENAME}")
    print(f"Platform: {interpreter_platform_tag()}")
    try:
        library, built = _build(grammar_dir, build_dir, force)
    except ParseError as error:
        print(f"{_FAILURE_LINE}\n{error}", file=sys.stderr)
        return _EXIT_FAILURE
    print(f"Library: {library}")
    if built:
        print("Built: the parser was compiled and its staleness record written.")
    else:
        print("Already fresh: no build was needed (pass -Force to rebuild anyway).")
    return _EXIT_SUCCESS


def _check_a_missing_grammar_fails_the_build() -> None:
    for force in (False, True):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                code = rebuild_parser(Path(tmp), force)
        assert code == _EXIT_FAILURE, f"force={force}: a grammar directory without grammar.js exited {code}, expected 1"
        assert _FAILURE_LINE in errors.getvalue(), (
            f"force={force}: the failure did not print {_FAILURE_LINE!r}: {errors.getvalue()!r}"
        )


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test([_check_a_missing_grammar_fails_the_build], wrapper=WRAPPER, module=MODULE,
                             parser=build_parser(), folder=GENERATION_SCRIPTS_DIR)
    return rebuild_parser(Path(tree_sitter_datrix.__file__).parent, args.force)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
