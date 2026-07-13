#!/usr/bin/env python3
"""
Run mypy for a specific Datrix project.

This script is intended to be called from scripts/test/mypy.ps1, which handles
virtual environment activation and package installation checks.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
 import tomllib
except ImportError:
 tomllib = None  # type: ignore[assignment]

library_dir = Path(__file__).parent
if library_dir.exists() and str(library_dir) not in sys.path:
 sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root, get_venv_python, is_venv_active


def find_project_root(project_name: str, datrix_root: Path) -> Path:
 project_path = datrix_root / project_name
 if not project_path.exists():
  available = sorted([
   d.name
   for d in datrix_root.iterdir()
   if d.is_dir() and d.name.startswith("datrix")
  ])
  raise FileNotFoundError(
   f"Project '{project_name}' not found at {project_path}\n"
   f"Available projects: {', '.join(available)}"
  )
 return project_path


def has_mypy_config(project_root: Path) -> bool:
 pyproject_path = project_root / "pyproject.toml"
 if not pyproject_path.exists():
  return False
 if tomllib is not None:
  try:
   with pyproject_path.open("rb") as f:
    data = tomllib.load(f)
   tool = data.get("tool", {})
   return isinstance(tool, dict) and isinstance(tool.get("mypy"), dict)
  except (OSError, ValueError):
   return False
 try:
  return "[tool.mypy]" in pyproject_path.read_text(encoding="utf-8")
 except OSError:
  return False


def resolve_specific_targets(project_root: Path, specific: str | None) -> list[str]:
 if not specific:
  return ["src"]

 targets: list[str] = []
 for raw_target in specific.split(","):
  target = raw_target.strip()
  if not target:
   continue
  target_path = Path(target)
  if not target_path.is_absolute():
   target_path = project_root / target_path
  targets.append(str(target_path))
 return targets


def write_log(project_root: Path, output: str) -> Path:
 results_dir = project_root / ".test_results"
 results_dir.mkdir(exist_ok=True)
 timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
 log_path = results_dir / f"mypy-results-{timestamp}.log"
 log_path.write_text(output, encoding="utf-8")
 return log_path


def resolve_extra_mypy_env(project_root: Path) -> tuple[list[str], dict[str, str]]:
 """Extra mypy CLI args + environment overrides for showcase-repo scripts.

 The `datrix` showcase repo has no `src/` package layout: its own
 `scripts/test/*.py` and `scripts/dev/*.py` gate scripts import shared helpers
 from `scripts/library/` (e.g. `review`, `test`, `shared`) via a runtime
 `sys.path.insert(...)`, which mypy cannot see unless told where to look. Set
 `MYPYPATH` to `scripts/library` so those imports resolve, and pass
 `--follow-imports=silent` so pre-existing issues *inside* those shared
 library modules (which get no dedicated mypy --strict run of their own --
 there is no separate "scripts/library" project) don't block the target
 script's own strict check with unrelated errors.

 Returns:
  (extra_cli_args, env_overrides) -- both empty for every other project,
  which keeps this a no-op for the normal datrix-* package sweep.
 """
 library_dir = project_root / "scripts" / "library"
 if project_root.name != "datrix" or not library_dir.exists():
  return [], {}
 return ["--follow-imports=silent"], {"MYPYPATH": str(library_dir)}


def run_mypy(
 python_exe: str,
 project_root: Path,
 targets: list[str],
 verbose: bool,
 save_log: bool,
) -> int:
 extra_args, extra_env = resolve_extra_mypy_env(project_root)
 cmd = [python_exe, "-m", "mypy", *extra_args, *targets]
 if verbose:
  cmd.append("--show-error-context")

 print(f"Running: {' '.join(cmd)}")
 print(f"Working directory: {project_root}")
 print("")

 process = subprocess.Popen(
  cmd,
  cwd=project_root,
  stdout=subprocess.PIPE,
  stderr=subprocess.STDOUT,
  text=True,
  bufsize=1,
  env={**os.environ, **extra_env} if extra_env else None,
 )

 output_lines: list[str] = []
 assert process.stdout is not None
 for line in process.stdout:
  print(line, end="")
  output_lines.append(line)

 exit_code = process.wait()

 if save_log:
  log_path = write_log(project_root, "".join(output_lines))
  print("")
  print(f"Log file: {log_path}")

 return exit_code


def main() -> int:
 parser = argparse.ArgumentParser(
  description="Run mypy for a Datrix project",
  formatter_class=argparse.RawDescriptionHelpFormatter,
  epilog="""
Examples:
 python scripts/library/mypy.py datrix-common
 python scripts/library/mypy.py datrix-codegen-python --specific src

Note: This script should be called from mypy.ps1, which handles virtual environment activation.
""",
 )
 parser.add_argument("project_name", help="Name of the project to type-check")
 parser.add_argument("--coverage", "-c", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose mypy context")
 parser.add_argument("--no-save", action="store_true", help="Don't save mypy output to log files")
 parser.add_argument("--no-auto-install", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--unit", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--integration", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--e2e", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--fast", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--slow", action="store_true", help=argparse.SUPPRESS)
 parser.add_argument("--specific", type=str, help="Run mypy against a specific file, directory, or comma-separated targets")
 parser.add_argument("-k", "--keyword", type=str, help=argparse.SUPPRESS)
 parser.add_argument("--debug", action="store_true", help="Enable debug logging")
 args = parser.parse_args()

 if not is_venv_active():
  print("ERROR: No virtual environment is currently active.", file=sys.stderr)
  print("", file=sys.stderr)
  print("This script should be called from mypy.ps1, which handles virtual environment activation.", file=sys.stderr)
  return 1

 ignored_options = []
 for name in ["coverage", "no_auto_install", "unit", "integration", "e2e", "fast", "slow", "keyword"]:
  value = getattr(args, name)
  if value:
   ignored_options.append(name.replace("_", "-"))
 if ignored_options:
  print(f"Note: mypy does not use these test runner options: {', '.join(ignored_options)}")
  print("")

 try:
  datrix_root = get_datrix_root()
  project_root = find_project_root(args.project_name, datrix_root)
 except FileNotFoundError as e:
  print(f"ERROR: {e}", file=sys.stderr)
  return 1

 print(f"Found project '{args.project_name}' at: {project_root}")

 if not has_mypy_config(project_root):
  print(f"SKIP: {args.project_name} has no [tool.mypy] config in pyproject.toml.")
  return 0

 python_path = get_venv_python()
 python_exe = str(python_path if python_path.exists() else Path(sys.executable))
 print(f"Using Python: {python_exe}")

 targets = resolve_specific_targets(project_root, args.specific)
 return run_mypy(
  python_exe=python_exe,
  project_root=project_root,
  targets=targets,
  verbose=args.verbose or args.debug,
  save_log=not args.no_save,
 )


if __name__ == "__main__":
 sys.exit(main())
