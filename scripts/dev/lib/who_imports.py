#!/usr/bin/env python3
"""Show which runtime import chain first loads a module.

Imports each root module in this fresh interpreter with a ``sys.meta_path`` observer installed.
The first time a target module (or any submodule of a target package) is looked up, the
observer records the Python call stack, keeping only frames in workspace files, so the chain
``root -> ... -> the import statement that pulled the target in`` is printed. The observer
never resolves anything itself, so imports behave exactly as without it; ``importlib``-driven
imports are seen as well as ``import`` statements.

The static import-boundary scanner (``scan\\check-import-boundaries.ps1``) reports *that* a
forbidden edge exists; this reports *which* chain realizes it at runtime, function-level
imports included.

Exit codes: 0 = every root imported (targets that never loaded are listed as such),
2 = a root failed to import (its error is printed).

Usage:
    python who_imports.py --root MODULE [--root MODULE ...] --target MODULE [--target MODULE ...]
"""

from __future__ import annotations

import argparse
import importlib
import importlib.abc
import importlib.machinery
import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.paths import WORKSPACE_DIR

EXIT_OK: Final[int] = 0
EXIT_ROOT_FAILED: Final[int] = 2
_IMPORTLIB_FRAME_MARKER: Final[str] = "<frozen importlib"


@dataclass
class _FirstLoadObserver(importlib.abc.MetaPathFinder):
    """Records the stack at the first lookup of each target; resolves nothing."""

    targets: frozenset[str]
    workspace: Path
    tracer_file: Path
    chains: dict[str, list[str]] = field(default_factory=dict)

    def _matched_target(self, fullname: str) -> str | None:
        for target in self.targets:
            if fullname == target or fullname.startswith(f"{target}."):
                return target
        return None

    def _workspace_frames(self) -> list[str]:
        frames: list[str] = []
        for frame in traceback.extract_stack()[:-2]:
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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", action="append", required=True, help="Module to import. Repeatable.")
    parser.add_argument("--target", action="append", required=True, help="Module or package to watch. Repeatable.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    already = sorted(target for target in args.target if target in sys.modules)
    observer = _FirstLoadObserver(
        targets=frozenset(args.target), workspace=WORKSPACE_DIR.resolve(), tracer_file=Path(__file__).resolve()
    )
    sys.meta_path.insert(0, observer)
    failed = False
    for root in args.root:
        try:
            importlib.import_module(root)
        except Exception as exc:  # noqa: BLE001 -- the root's own failure is the answer; print it
            failed = True
            print(f"ROOT FAILED {root}: {type(exc).__name__}: {exc}")
    sys.meta_path.remove(observer)

    for target in sorted(args.target):
        if target in already:
            print(f"=== {target}: already loaded before any root was imported (interpreter startup)")
        elif target in observer.chains:
            first, *frames = observer.chains[target]
            print(f"=== {target}: {first}")
            for frame in frames:
                print(f"    {frame}")
        else:
            print(f"=== {target}: never loaded by {', '.join(args.root)}")
    return EXIT_ROOT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
