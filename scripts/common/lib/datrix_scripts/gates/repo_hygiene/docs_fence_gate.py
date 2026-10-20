"""Docs fence gate: every ``datrix`` fence under ``datrix/docs`` states a fact that holds.

The showcase repo hosts no test suite, so its docs tree is checked here, through the same
collector, stages and comparison a package's case runner applies to its own ``docs/``
(:func:`datrix_testing.cases.runner.fence_failures`): an example parses, a fragment parses in the
construct its ``context=`` names, a whole application analyzes clean or to exactly the codes its
``expect=`` names, and ``rejected`` syntax stays rejected.

Built-in non-vacuity self-test, every invocation: a planted docs tree whose fence does not parse
must be reported, and the same tree with the fence fixed must pass.

Run it through ``gates/repo-hygiene/docs-fence-gate.ps1`` or its ``.sh`` twin; it runs in gate mode
(``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] docs-fence PASSED|FAILED exit=<n> log=<path>`` verdict last.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_testing.cases.fences import FenceError
from datrix_testing.cases.runner import fence_failures
from datrix_testing.parsing import register_installed_parsers

from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import packages_current, self_test_gate_parser
from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "docs-fence"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.docs_fence_gate"
WRAPPER: Final = "docs-fence-gate"

DOCS_ROOT: Final[Path] = SHOWCASE_DIR / "docs"

_EXIT_OK: Final[int] = 0
_EXIT_FAILURES: Final[int] = 1
_EXIT_GATE_BROKEN: Final[int] = 2

_PLANTED_BROKEN: Final[str] = """\
```datrix
module pricing {
    fn double(Int amount) -> Int {
        return amount * ;
    }
}
```
"""

_PLANTED_FIXED: Final[str] = _PLANTED_BROKEN.replace("amount * ;", "amount * 2;")


def _planted_failures(page_text: str) -> list[str]:
    with tempfile.TemporaryDirectory() as scratch:
        docs = Path(scratch) / "docs"
        docs.mkdir()
        (docs / "page.md").write_text(page_text, encoding="utf-8")
        return fence_failures(docs)[1]


def self_test() -> bool:
    """The gate reports a fence that does not parse and passes the same fence fixed."""
    broken = _planted_failures(_PLANTED_BROKEN)
    fixed = _planted_failures(_PLANTED_FIXED)
    if len(broken) != 1 or "page.md:1" not in broken[0]:
        logger.error("self_test_failed planted_broken_fence_not_reported failures=%s", broken)
        return False
    if fixed:
        logger.error("self_test_failed planted_fixed_fence_reported failures=%s", fixed)
        return False
    logger.info("self_test_passed")
    return True


def run_gate(docs_root: Path) -> int:
    """Run every fence of *docs_root*; print each failure and a count."""
    try:
        count, failures = fence_failures(docs_root)
    except FenceError as error:
        print(f"FAIL {error}")
        return _EXIT_FAILURES
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"{count} fence case(s) under {docs_root}, {len(failures)} failing")
    return _EXIT_FAILURES if failures else _EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/docs-fence-gate.ps1``: one per wrapper parameter, spelled
    exactly."""
    return self_test_gate_parser(WRAPPER, __doc__.splitlines()[0])


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (every fence holds / self-test passed), 1 (a failing fence, a failed wrapper
    seam check, or package installs that are not current), 2 (a failed self-test)."""
    if not packages_current():
        return _EXIT_FAILURES
    if not args.debug:
        # The analysis the fences run logs per stage; only --dbg shows it.
        logging.getLogger().setLevel(logging.WARNING)
        logger.setLevel(logging.INFO)
    register_installed_parsers()

    if not self_test():
        print("Docs fence gate self-test failed: the gate cannot tell a broken fence from a good one.")
        return _EXIT_GATE_BROKEN
    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )
    return run_gate(DOCS_ROOT)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
