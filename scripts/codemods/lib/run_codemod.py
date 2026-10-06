#!/usr/bin/env python3
"""
Run a Bowler codemod script from scripts/codemods/lib.

Resolves the codemods directory, finds the requested script, and invokes
`python -m bowler run <script> -- <args>`. Requires the Datrix venv (with
bowler installed) to be active or on PATH.

Usage:
  python scripts/codemods/lib/run_codemod.py CODEMOD_NAME [args ...]   (PYTHONPATH=scripts/common/lib)
  python scripts/codemods/lib/run_codemod.py 01_rename_function old_name new_name datrix-language/src

  Or use the PowerShell wrapper:
    .\\scripts\\codemods\\run-codemod.ps1 01_rename_function old_name new_name datrix-language/src
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from datrix_scripts.venv import get_venv_python

# The numbered codemod recipes live beside this runner.
CODEMODS_DIR = Path(__file__).resolve().parent
CODEMOD_GLOB = "[0-9][0-9]_*.py"


def find_codemod_script(name: str) -> Path:
    """Return path to the codemod script; add .py if missing."""
    base = CODEMODS_DIR / name
    if base.suffix == ".py":
        path = base
    else:
        path = Path(str(base) + ".py")
    if not path.is_file():
        raise FileNotFoundError(
            f"Codemod script not found: {path}. "
            f"Available in {CODEMODS_DIR}: "
            f"{', '.join(p.name for p in sorted(CODEMODS_DIR.glob(CODEMOD_GLOB)))}"
        )
    return path


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: run_codemod.py CODEMOD_NAME [args ...]",
            file=sys.stderr,
        )
        print(
            f"  Codemods directory: {CODEMODS_DIR}",
            file=sys.stderr,
        )
        return 1
    codemod_name = sys.argv[1]
    codemod_args = sys.argv[2:]
    try:
        script_path = find_codemod_script(codemod_name)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    python_exe = get_venv_python()
    cmd = [
        str(python_exe),
        "-m",
        "bowler",
        "run",
        str(script_path),
        "--",
        *codemod_args,
    ]
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
