#!/usr/bin/env python3
"""
Run a Bowler codemod script from scripts/dev/codemods.

Resolves the codemods directory, finds the requested script, and invokes
`python -m bowler run <script> -- <args>`. Requires the Datrix venv (with
bowler installed) to be active or on PATH.

Usage:
  python scripts/library/dev/run_codemod.py CODEMOD_NAME [args ...]
  python scripts/library/dev/run_codemod.py 01_rename_function old_name new_name datrix-language/src

  Or use the PowerShell wrapper:
    .\\scripts\\dev\\run-codemod.ps1 01_rename_function old_name new_name datrix-language/src
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Add library directory to sys.path for shared
_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_venv_python

# scripts/library/dev -> scripts
_scripts_dir = Path(__file__).resolve().parent.parent.parent
CODEMODS_DIR = _scripts_dir / "dev" / "codemods"


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
            f"{', '.join(p.name for p in sorted(CODEMODS_DIR.glob('*.py')))}"
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
