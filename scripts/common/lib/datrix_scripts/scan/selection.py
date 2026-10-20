"""What a scan was asked to scan: the paths or projects named, or every Datrix repository with ``--all``.

Every scanner behind a ``scan/`` wrapper selects its targets the same way: one or more paths (or
project names), or ``--all``, never both and never neither. Neither prints the wrapper's usage;
both is refused. Each exits with the code its wrapper always used.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_VIOLATION

BOTH_SELECTED: Final = "Specify either -All or one or more paths, not both."


class SelectionRefused(Exception):
    """The arguments select nothing to scan, or contradict each other: the text to print and the exit code."""

    def __init__(self, text: str, exit_code: int, *, to_stderr: bool) -> None:
        super().__init__(text)
        self.text = text
        self.exit_code = exit_code
        self.to_stderr = to_stderr

    def report(self) -> int:
        """Print the text (the usage to stdout, an error to stderr); the exit code."""
        print(self.text, file=sys.stderr if self.to_stderr else sys.stdout)
        return self.exit_code


def wrapper_usage(wrapper: str, forms: Sequence[str], *, get_help: bool = True) -> str:
    """The usage a wrapper prints when nothing is selected: each invocation form of ``.\\<wrapper>.ps1``,
    then (with *get_help*) the pointer to its full help."""
    lines = ["Usage:", *(f"  .\\{wrapper}.ps1 {form}" for form in forms)]
    if get_help:
        lines.extend(["", f"Use Get-Help .\\{wrapper}.ps1 -Full for detailed help."])
    return "\n".join(lines)


def require_selection(
    targets: Sequence[str],
    all_repos: bool,
    usage: str,
    *,
    exit_code: int = EXIT_VIOLATION,
    refuse_both: bool = True,
) -> None:
    """Refuse a run that names no target and no ``--all`` (the usage), or (with *refuse_both*) both.

    Raises:
        SelectionRefused: carrying the text to print and *exit_code*.
    """
    if all_repos and targets and refuse_both:
        raise SelectionRefused(f"ERROR: {BOTH_SELECTED}", exit_code, to_stderr=True)
    if not all_repos and not targets:
        raise SelectionRefused(usage, exit_code, to_stderr=False)


def every_repository(workspace: Path) -> list[Path]:
    """Every Datrix repository under *workspace* (the showcase repo, then each ``datrix-*``), as ``-All`` scans them."""
    return [path for path in workspace_package_dirs(workspace, include_showcase=True) if path.exists()]


def expect_refusal(call: Callable[[], object], exit_code: int, fragment: str) -> None:
    """Assert *call* raises ``SelectionRefused`` with *exit_code* and text holding *fragment* (a self-test
    helper)."""
    try:
        call()
    except SelectionRefused as refused:
        assert refused.exit_code == exit_code, f"refused with exit {refused.exit_code}, expected {exit_code}"
        assert fragment in refused.text, f"refusal must mention {fragment!r}; got {refused.text!r}"
    else:
        raise AssertionError(f"expected a refusal mentioning {fragment!r} (exit {exit_code})")
