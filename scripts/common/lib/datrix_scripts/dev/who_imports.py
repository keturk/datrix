"""Show which runtime import chain first loads a module.

The module behind ``dev/who-imports.ps1`` (and its ``.sh`` twin). Imports each root module in this
interpreter with a ``sys.meta_path`` observer installed. The first time a target module (or any
submodule of a target package) is looked up, the observer records the Python call stack below the
root's import, keeping only frames in workspace files, so the chain ``root -> ... -> the import
statement that pulled the target in`` is printed. The observer never resolves anything itself, so
imports behave exactly as without it; ``importlib``-driven imports are seen as well as ``import``
statements.

The static import-boundary scanner (``scan\\check-import-boundaries.ps1``) reports *that* a
forbidden edge exists; this reports *which* chain realizes it at runtime, function-level
imports included.

Exit codes: 0 = every root imported (targets that never loaded are listed as such),
1 = the package install check failed, 2 = a root failed to import (its error is printed).

Usage:
    python -m datrix_scripts.dev.who_imports --root MODULE [--root MODULE ...] --target MODULE [--target MODULE ...]
"""

from __future__ import annotations

import argparse
import importlib
import importlib.abc
import importlib.machinery
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import EXIT_VIOLATION, UsageError, expect_usage_error
from datrix_scripts.paths import WORKSPACE_DIR, script_env
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.who_imports"
WRAPPER: Final = "who-imports"
EXIT_OK: Final[int] = 0
EXIT_ROOT_FAILED: Final[int] = 2
#: The self-test's child: ``trace`` of the comma-joined roots (argv 2) for one target (argv 3), with the
#: planted modules' directory (argv 1) as the workspace whose frames are kept.
_PLANTED_TRACE: Final[str] = (
    "import sys\n"
    "from pathlib import Path\n"
    f"from {MODULE} import trace\n"
    "sys.exit(trace(sys.argv[2].split(','), [sys.argv[3]], Path(sys.argv[1])))\n"
)
_CHILD_TIMEOUT_SECONDS: Final[int] = 60
_IMPORTLIB_FRAME_MARKER: Final[str] = "<frozen importlib"
#: The frames ``find_spec`` itself adds to the stack it records.
_OBSERVER_FRAMES: Final[int] = 2


@dataclass
class _FirstLoadObserver(importlib.abc.MetaPathFinder):
    """Records the stack at the first lookup of each target; resolves nothing."""

    targets: frozenset[str]
    workspace: Path
    tracer_file: Path
    chains: dict[str, list[str]] = field(default_factory=dict)
    #: How deep the stack was where the current root's import started; frames above it are the caller's.
    base_depth: int = 0

    def _matched_target(self, fullname: str) -> str | None:
        for target in self.targets:
            if fullname == target or fullname.startswith(f"{target}."):
                return target
        return None

    def _workspace_frames(self) -> list[str]:
        frames: list[str] = []
        for frame in traceback.extract_stack()[self.base_depth:-_OBSERVER_FRAMES]:
            if frame.filename.startswith(_IMPORTLIB_FRAME_MARKER):
                continue
            path = Path(frame.filename)
            if path == self.tracer_file or not path.is_relative_to(self.workspace):
                continue
            frames.append(f"{path.relative_to(self.workspace).as_posix()}:{frame.lineno}  {(frame.line or '').strip()}")
        return frames

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        matched = self._matched_target(fullname)
        if matched is not None and matched not in self.chains:
            self.chains[matched] = [f"first lookup: {fullname}", *self._workspace_frames()]
        return None


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/who-imports.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--root", action="append", default=[],
                        help="Module to import (required). Repeatable or comma-separated.")
    parser.add_argument("--target", action="append", default=[],
                        help="Module or package to watch (required). Repeatable or comma-separated.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted chain is traced, and a missing --root is refused.")
    parser.set_defaults(debug=False)
    return parser


def trace(roots: Sequence[str], targets: Sequence[str], workspace: Path) -> int:
    """Import each of *roots* and print the chain that first loaded each of *targets*; the exit code."""
    already = sorted(target for target in targets if target in sys.modules)
    observer = _FirstLoadObserver(
        targets=frozenset(targets), workspace=workspace.resolve(), tracer_file=Path(__file__).resolve()
    )
    sys.meta_path.insert(0, observer)
    failed = False
    try:
        for root in roots:
            observer.base_depth = len(traceback.extract_stack())
            try:
                importlib.import_module(root)
            except Exception as exc:  # noqa: BLE001 -- the root's own failure is the answer; print it
                failed = True
                print(f"ROOT FAILED {root}: {type(exc).__name__}: {exc}")
    finally:
        sys.meta_path.remove(observer)

    for target in sorted(targets):
        if target in already:
            print(f"=== {target}: already loaded before any root was imported (interpreter startup)")
        elif target in observer.chains:
            first, *frames = observer.chains[target]
            print(f"=== {target}: {first}")
            for frame in frames:
                print(f"    {frame}")
        else:
            print(f"=== {target}: never loaded by {', '.join(roots)}")
    return EXIT_ROOT_FAILED if failed else EXIT_OK


def _required(values: Sequence[str], parameter: str) -> list[str]:
    items = comma_values(values)
    if not items:
        raise UsageError(f"-{parameter} is required: pass one or more dotted module names (comma-separate several).")
    return items


def _trace_in_child(directory: Path, roots: Sequence[str], target: str) -> subprocess.CompletedProcess[str]:
    """``trace`` in a fresh interpreter whose import path starts at *directory*, as a real run's does."""
    env = script_env()
    env["PYTHONPATH"] = os.pathsep.join([str(directory), env["PYTHONPATH"]])
    return subprocess.run(
        [sys.executable, "-c", _PLANTED_TRACE, str(directory), ",".join(roots), target],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=_CHILD_TIMEOUT_SECONDS, check=False,
    )


def _check_a_planted_chain_is_traced() -> None:
    planted_root, planted_middle, planted_target = "who_imports_planted_root", "who_imports_planted_mid", "who_imports_planted_leaf"
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / f"{planted_root}.py").write_text(f"import {planted_middle}\n", encoding="utf-8")
        (directory / f"{planted_middle}.py").write_text(f"def load():\n    import {planted_target}\nload()\n", encoding="utf-8")
        (directory / f"{planted_target}.py").write_text("VALUE = 1\n", encoding="utf-8")
        result = _trace_in_child(directory, [planted_root, "who_imports_no_such_root"], planted_target)
    exit_code, lines = result.returncode, result.stdout.splitlines()
    assert exit_code == EXIT_ROOT_FAILED, (
        f"a root that fails to import must exit {EXIT_ROOT_FAILED}; got {exit_code}: {result.stdout}{result.stderr}"
    )
    assert lines[0].startswith("ROOT FAILED who_imports_no_such_root"), lines
    assert lines[1] == f"=== {planted_target}: first lookup: {planted_target}", lines
    chain = [line.strip().split("  ", 1)[0] for line in lines[2:]]
    assert chain == [f"{planted_root}.py:1", f"{planted_middle}.py:3", f"{planted_middle}.py:2"], (
        f"the chain must start at the root's import and hold no caller frame; got {lines[2:]}"
    )


def _check_missing_root_is_refused() -> None:
    expect_usage_error(lambda: _required([], "Root"), "-Root is required")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_chain_is_traced, _check_missing_root_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    roots, targets = _required(args.root, "Root"), _required(args.target, "Target")
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    return trace(roots, targets, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
