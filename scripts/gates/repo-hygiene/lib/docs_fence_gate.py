"""Docs fence gate: every ``datrix`` fence under ``datrix/docs`` states a fact that holds.

The showcase repo hosts no test suite, so its docs tree is checked here, through the same
collector, stages and comparison a package's case runner applies to its own ``docs/``
(:func:`datrix_testing.cases.runner.fence_failures`): an example parses, a fragment parses in the
construct its ``context=`` names, a whole application analyzes clean or to exactly the codes its
``expect=`` names, and ``rejected`` syntax stays rejected.

Built-in non-vacuity self-test, every invocation: a planted docs tree whose fence does not parse
must be reported, and the same tree with the fence fixed must pass.

Usage:
    python docs_fence_gate.py
    python docs_fence_gate.py --debug
    python docs_fence_gate.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path
from typing import Final

from datrix_testing.cases.fences import FenceError
from datrix_testing.cases.runner import fence_failures
from datrix_testing.parsing import register_installed_parsers

from datrix_scripts.paths import SHOWCASE_DIR

logger = logging.getLogger(__name__)

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    args = parser.parse_args()
    # The analysis the fences run logs per stage; only --debug shows it.
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING, format="%(levelname)s %(message)s")
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
    register_installed_parsers()

    if not self_test():
        print("Docs fence gate self-test failed: the gate cannot tell a broken fence from a good one.")
        return _EXIT_GATE_BROKEN
    if args.self_test:
        return _EXIT_OK
    return run_gate(DOCS_ROOT)


if __name__ == "__main__":
    sys.exit(main())
