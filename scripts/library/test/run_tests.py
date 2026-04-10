#!/usr/bin/env python3
"""
Orchestrate full-package tests, batch generation, and complete workflow per language.

Runs, in order:
1. test.ps1 -All
2. For each target language: generate.ps1 -All -L <lang>
3. For each language whose generate succeeded: run-complete.ps1 -All -Skip1 -Skip2 -L <lang>

If -L/--language is omitted, languages are python then typescript. If test.ps1 fails,
no later steps run. If generate fails for a language, run-complete is skipped for that
language only; other languages still run.

Exit code: first non-zero child exit code in execution order, or 0 if all succeeded.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

# Ensure stdout/stderr handle Unicode (child scripts may emit rich output)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

LANGUAGE_PYTHON = "python"
LANGUAGE_TYPESCRIPT = "typescript"
ALL_LANGUAGES: tuple[str, ...] = (LANGUAGE_PYTHON, LANGUAGE_TYPESCRIPT)


def _resolve_script_paths() -> tuple[Path, Path, Path]:
    """Return absolute paths to test.ps1, generate.ps1, and run-complete.ps1."""
    scripts_dir = Path(__file__).resolve().parent.parent.parent
    test_ps1 = scripts_dir / "test" / "test.ps1"
    generate_ps1 = scripts_dir / "dev" / "generate.ps1"
    run_complete_ps1 = scripts_dir / "test" / "run-complete.ps1"
    return test_ps1, generate_ps1, run_complete_ps1


def _require_existing_scripts(
    test_ps1: Path, generate_ps1: Path, run_complete_ps1: Path
) -> None:
    """Raise FileNotFoundError if any orchestration script is missing."""
    missing = [p for p in (test_ps1, generate_ps1, run_complete_ps1) if not p.is_file()]
    if missing:
        names = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(f"Required script(s) not found: {names}")


def _resolve_powershell_executable() -> str:
    """Return 'pwsh' or 'powershell' on PATH; raise if neither is available."""
    pwsh = shutil.which("pwsh")
    if pwsh:
        return pwsh
    powershell = shutil.which("powershell")
    if powershell:
        return powershell
    raise EnvironmentError(
        "Neither 'pwsh' nor 'powershell' was found on PATH. "
        "Install PowerShell Core (pwsh) or Windows PowerShell to run Datrix .ps1 scripts."
    )


def _run_ps1(
    powershell_exe: str,
    script_path: Path,
    cwd: Path,
    ps_args: Sequence[str],
) -> int:
    """Execute a .ps1 via PowerShell with -NoProfile -File; return process exit code."""
    cmd: list[str] = [
        powershell_exe,
        "-NoProfile",
        "-File",
        str(script_path.resolve()),
        *ps_args,
    ]
    result = subprocess.run(cmd, cwd=cwd, check=False)
    return int(result.returncode)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse CLI arguments for language selection."""
    parser = argparse.ArgumentParser(
        description=(
            "Run test.ps1 -All, then per-language generate.ps1 and run-complete.ps1 "
            "(with -Skip1 -Skip2)."
        )
    )
    parser.add_argument(
        "-L",
        "--language",
        choices=list(ALL_LANGUAGES),
        dest="language",
        default=None,
        help="Run generate and run-complete for this language only (default: python then typescript)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: run orchestrated steps; return exit code for the shell."""
    args = _parse_args(argv)
    languages: tuple[str, ...] = (
        (args.language,) if args.language is not None else ALL_LANGUAGES
    )

    test_ps1, generate_ps1, run_complete_ps1 = _resolve_script_paths()
    _require_existing_scripts(test_ps1, generate_ps1, run_complete_ps1)

    cwd = get_datrix_root()
    powershell_exe = _resolve_powershell_executable()

    test_code = _run_ps1(powershell_exe, test_ps1, cwd, ("-All",))
    if test_code != 0:
        return test_code

    first_nonzero: int | None = None

    def record(code: int) -> None:
        nonlocal first_nonzero
        if code != 0 and first_nonzero is None:
            first_nonzero = code

    for lang in languages:
        gen_code = _run_ps1(
            powershell_exe,
            generate_ps1,
            cwd,
            ("-All", "-L", lang),
        )
        record(gen_code)
        if gen_code != 0:
            continue

        rc_code = _run_ps1(
            powershell_exe,
            run_complete_ps1,
            cwd,
            ("-All", "-Skip1", "-Skip2", "-L", lang),
        )
        record(rc_code)

    return first_nonzero if first_nonzero is not None else 0


if __name__ == "__main__":
    sys.exit(main())
