#!/usr/bin/env python3
"""List every place that imports names from given modules: the worklist before a move or rename.

Reads every file ``datrix_scripts.import_sites`` scans (each ``datrix-*`` repository's
``src/`` and ``tests/`` trees and root ``*.py`` files, the scripts tree, the hooks) and reports:

- ``from M import N`` where M is a target module (relative imports inside a ``src/`` package
  are resolved to their absolute module first);
- without ``--name``: ``import M`` / ``import M as alias`` / ``from P import M`` of a target;
- with ``--name``: ``alias.N`` attribute reads on a name bound to a target module.

A file that does not parse is listed as UNPARSEABLE and counted -- never skipped silently --
and the exit code is still 0: this is a report, not a gate.

Usage:
    python find_imports.py --module M [--module M ...] [--name N ...] [--debug]
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.import_sites import scanned_files, sites_in
from datrix_scripts.paths import WORKSPACE_DIR

EXIT_OK: Final[int] = 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--module", action="append", required=True, help="Dotted target module. Repeatable.")
    parser.add_argument("--name", action="append", default=[], help="Narrow to this imported name. Repeatable.")
    parser.add_argument("--debug", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")
    modules = frozenset(args.module)
    names = frozenset(args.name)
    total = 0
    unparseable = 0
    files = scanned_files(WORKSPACE_DIR)
    for path in files:
        try:
            sites = sites_in(path, modules, names)
        except (SyntaxError, UnicodeDecodeError) as exc:
            unparseable += 1
            print(f"UNPARSEABLE {path.relative_to(WORKSPACE_DIR).as_posix()}: {exc}")
            continue
        for site in sites:
            print(f"{site.path.relative_to(WORKSPACE_DIR).as_posix()}:{site.line}: [{site.kind}] {site.text}")
        total += len(sites)
    print(f"{total} site(s) in {len(files)} file(s); {unparseable} unparseable file(s).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
