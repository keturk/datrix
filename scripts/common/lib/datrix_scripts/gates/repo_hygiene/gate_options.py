"""The options several repo-hygiene gates' wrappers declare alike, built once.

The source-tree scanners (``check-handler-name-dedup``, ``check-enum-value-literals``,
``check-cross-package-fixture-reads``, ``app-probe-path-literal-gate``, ...) take a monorepo root
(``-BaseDir``), a self-test switch, and some of ``-ShowFiles`` (print each file as it is scanned) and
``-Dbg`` (print the interpreter and arguments first). ``base_dir_gate_parser`` is that parser, spelled
exactly as the wrapper's parameters (``--base-dir``, ``--self-test``, ``--show-files``, ``--dbg``),
abbreviations refused; ``requested_base_dir`` is the root a ``--base-dir`` value names.

The reference scanners (``design-task-reference-gate``, ``import-name-existence-gate``) take a
comma-separated ``-Roots`` and ``-SelfTest``: ``roots_gate_parser`` and ``requested_roots``.

The example and source-comment gates take only ``-Dbg`` and ``-SelfTest``: ``self_test_gate_parser``.
A gate that imports the datrix packages first proves their installs current: ``packages_current``.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, print_command
from datrix_scripts.paths import WORKSPACE_DIR

_ROOT_SEPARATOR: Final = ","


def base_dir_gate_parser(
    wrapper: str, description: str, *, show_files: bool = True, debug: bool = True
) -> argparse.ArgumentParser:
    """The parser of a scanner whose wrapper declares ``-BaseDir`` and ``-SelfTest``, plus ``-ShowFiles``
    when *show_files* and ``-Dbg`` when *debug* (``args.show_files`` / ``args.debug`` are False when the
    wrapper does not declare them)."""
    parser = argparse.ArgumentParser(prog=wrapper, description=description, allow_abbrev=False)
    parser.add_argument("--base-dir", default="", help="Monorepo root directory (default: the workspace).")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the scanner self-test and the wrapper seam check."
    )
    if show_files:
        parser.add_argument("--show-files", action="store_true", help="Print each file as it is scanned.")
    else:
        parser.set_defaults(show_files=False)
    if debug:
        parser.add_argument(
            WRAPPER_DEBUG_FLAG,
            dest="debug",
            action="store_true",
            help="Print the interpreter and arguments first, and log at DEBUG level.",
        )
    else:
        parser.set_defaults(debug=False)
    return parser


def report_by_printing(debug: bool) -> None:
    """Start a gate that reports by printing: under ``--dbg`` print the interpreter and arguments (and gate
    mode logs at DEBUG); otherwise hold the root logger at WARNING, so the INFO records the datrix packages
    it imports emit (plugin discovery, builtin and type-map registration, config loads) stay out of the
    report."""
    if debug:
        print_command()
    else:
        logging.getLogger().setLevel(logging.WARNING)


def requested_base_dir(value: str) -> Path:
    """The absolute monorepo root *value* names: the workspace when *value* is empty."""
    return (Path(value) if value else WORKSPACE_DIR).resolve()


def roots_gate_parser(wrapper: str, description: str) -> argparse.ArgumentParser:
    """The parser of a scanner whose wrapper declares only ``-Roots`` (comma-separated directories) and
    ``-SelfTest``; ``args.debug`` is False, since such a wrapper declares no ``-Dbg``."""
    parser = argparse.ArgumentParser(prog=wrapper, description=description, allow_abbrev=False)
    parser.add_argument(
        "--roots",
        default="",
        help="Comma-separated directories to scan. Default: every tree the gate derives from disk.",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam check."
    )
    parser.set_defaults(debug=False)
    return parser


def requested_roots(value: str) -> list[str]:
    """The directories a ``--roots`` *value* names, split on commas and trimmed; empty when it names none."""
    return [root.strip() for root in value.split(_ROOT_SEPARATOR) if root.strip()]


def self_test_gate_parser(wrapper: str, description: str) -> argparse.ArgumentParser:
    """The parser of a gate whose wrapper declares only ``-Dbg`` (DEBUG logging) and ``-SelfTest``."""
    parser = argparse.ArgumentParser(prog=wrapper, description=description, allow_abbrev=False)
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and the wrapper seam check, and skip the real check.",
    )
    return parser


def packages_current() -> bool:
    """True when every datrix package is installed in the shared venv as its source declares; otherwise
    reinstall what is stale and answer whether that succeeded (the check a gate that imports the datrix
    packages runs first, so it never judges the tree with code older than the tree)."""
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    return ensure_packages(os.environ, require_packages)


def check_requested_roots_split_on_commas() -> None:
    """Self-test check: ``requested_roots`` splits as the wrapper's ``-Roots`` help describes."""
    cases: tuple[tuple[str, list[str]], ...] = (
        ("", []),
        ("D:/datrix/datrix/scripts/config", ["D:/datrix/datrix/scripts/config"]),
        ("a, b ,c", ["a", "b", "c"]),
        (" , ", []),
    )
    for value, expected in cases:
        got = requested_roots(value)
        assert got == expected, f"requested_roots({value!r}) is {got!r}, expected {expected!r}"
