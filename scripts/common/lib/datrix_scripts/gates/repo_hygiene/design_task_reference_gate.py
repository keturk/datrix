"""The design/task reference gate: no committed artifact cites a design document or a task file.

The detector, the committed-tree derivation and the non-vacuity self-test are
``datrix_scripts.design_task_references``'s (shared with ``git/commit-and-push.ps1``, which scans the
pending files of every dirty repo, and with the committed-content hook, which judges an edit before it is
written; see that module for the reference shapes and item labels it refuses). This module is what
``gates/repo-hygiene/design-task-reference-gate.ps1`` (and its ``.sh`` twin) runs, in gate mode
(``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] design-task-reference PASSED|FAILED exit=<n> log=<path>`` verdict.

The self-test runs before every scan, so a green result never means the detector was broken.

Exit codes: 0 = no reference found (or the self-test passed), 1 = at least one reference, a scanned file
that could not be read, the self-test failed, or the package installs are not current.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.design_task_references import ReferenceScanError, default_roots, scan, self_test
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import (
    check_requested_roots_split_on_commas,
    packages_current,
    requested_roots,
    roots_gate_parser,
)
from datrix_scripts.test import wrappers

GATE: Final = "design-task-reference"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.design_task_reference_gate"
WRAPPER: Final = "design-task-reference-gate"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/design-task-reference-gate.ps1``: one per wrapper parameter,
    spelled exactly. The wrapper declares no ``-Dbg``, so ``args.debug`` is always False."""
    return roots_gate_parser(WRAPPER, "Fail if a committed artifact cites a design document or a task file.")


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (no reference / self-test passed), 1 (a reference, an unreadable file, a
    failed self-test, or package installs that are not current)."""
    if not packages_current():
        return EXIT_VIOLATION
    if self_test() != EXIT_PASS:
        return EXIT_VIOLATION
    if args.self_test:
        return wrappers.run_self_test(
            [check_requested_roots_split_on_commas],
            wrapper=WRAPPER,
            module=MODULE,
            parser=build_parser(),
            folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )

    roots = requested_roots(args.roots) or default_roots()
    try:
        hits = scan(roots)
    except ReferenceScanError as exc:
        print(f"ERROR: {exc}")
        return EXIT_VIOLATION
    if not hits:
        print(f"INFO: No design-doc or task-file references in {len(roots)} committed tree(s).")
        print("Design/task reference check passed")
        return EXIT_PASS

    print(f"ERROR: {len(hits)} design-doc/task-file reference(s) in committed artifacts:")
    for rel, lineno, label, line in hits:
        print(f"  [{label}] {rel}:{lineno}: {line}")
    print(
        "\nDesign docs and task files are gitignored and numbered per-machine, so these are "
        "dangling pointers. Describe the WORK, not the ticket."
    )
    return EXIT_VIOLATION


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
