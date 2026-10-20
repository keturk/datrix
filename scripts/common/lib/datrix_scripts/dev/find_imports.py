"""List every place that imports names from given modules: the worklist before a move or rename.

The module behind ``dev/find-imports.ps1`` (and its ``.sh`` twin). Reads every file
``datrix_scripts.import_sites`` scans (each ``datrix-*`` repository's ``src/`` and ``tests/`` trees
and root ``*.py`` files, the scripts tree, the hooks) and reports:

- ``from M import N`` where M is a target module (relative imports inside a ``src/`` package
  are resolved to their absolute module first);
- without ``--name``: ``import M`` / ``import M as alias`` / ``from P import M`` of a target;
- with ``--name``: ``alias.N`` attribute reads on a name bound to a target module.

A file that does not parse is listed as UNPARSEABLE and counted -- never skipped silently --
and the exit code is still 0: this is a report, not a gate.

Usage:
    python -m datrix_scripts.dev.find_imports --module M [--module M ...] [--name N ...] [--dbg]
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

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, expect_usage_error
from datrix_scripts.import_sites import scanned_files, sites_in
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.find_imports"
WRAPPER: Final = "find-imports"
EXIT_OK: Final[int] = 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/find-imports.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--module", action="append", default=[],
                        help="Dotted target module (required). Repeatable or comma-separated.")
    parser.add_argument("--name", action="append", default=[],
                        help="Narrow to this imported name. Repeatable or comma-separated.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted import is found, and no --module is refused.")
    return parser


def report(modules: frozenset[str], names: frozenset[str], workspace: Path, files: Sequence[Path]) -> int:
    """Print every import site of *modules* (narrowed to *names*) in *files*; the number of sites."""
    total = 0
    unparseable = 0
    for path in files:
        try:
            sites = sites_in(path, modules, names)
        except (SyntaxError, UnicodeDecodeError) as exc:
            unparseable += 1
            print(f"UNPARSEABLE {path.relative_to(workspace).as_posix()}: {exc}")
            continue
        for site in sites:
            print(f"{site.path.relative_to(workspace).as_posix()}:{site.line}: [{site.kind}] {site.text}")
        total += len(sites)
    print(f"{total} site(s) in {len(files)} file(s); {unparseable} unparseable file(s).")
    return total


def _modules(args: argparse.Namespace) -> frozenset[str]:
    modules = frozenset(comma_values(args.module))
    if not modules:
        raise UsageError("-Module is required: pass the dotted module(s) whose imports to list, e.g. "
                         "-Module datrix_common.errors.plugin (comma-separate several).")
    return modules


def _check_a_planted_import_is_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        planted = workspace / "planted.py"
        planted.write_text("from datrix_common.errors.plugin import PluginError\nimport os\n", encoding="utf-8")
        args = build_parser().parse_args(["--module=datrix_common.errors.plugin,os", "--name=PluginError"])
        with contextlib.redirect_stdout(io.StringIO()):  # The report lines, for a real run.
            total = report(_modules(args), frozenset(comma_values(args.name)), workspace, [planted])
        assert total == 1, f"expected the one from-import of PluginError, found {total} site(s)"


def _check_no_module_is_refused() -> None:
    expect_usage_error(lambda: _modules(build_parser().parse_args([])), "-Module is required")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_import_is_found, _check_no_module_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    report(_modules(args), frozenset(comma_values(args.name)), WORKSPACE_DIR, scanned_files(WORKSPACE_DIR))
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
