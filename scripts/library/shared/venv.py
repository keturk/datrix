"""Virtual environment management utilities for Datrix scripts.

This module provides functions to:
- Find the Datrix root directory
- Check if a virtual environment exists
- Check if a virtual environment is active
- Create a virtual environment if needed
- Get the path to the venv Python executable

Usage:
 from shared.venv import ensure_datrix_venv, get_venv_python

 # Ensure venv exists (creates if needed)
 if ensure_datrix_venv():
 python_exe = get_venv_python()
 # Use python_exe...
"""

import os
import subprocess
import sys
from pathlib import Path


def get_datrix_root() -> Path:
 """Find the Datrix root directory.

 The Datrix root is the directory containing all datrix* project folders.
 This function traverses up from the script location to find it.

 Returns:
 Path to the Datrix root directory (e.g., D:\\datrix)

 Raises:
 FileNotFoundError: If the Datrix root cannot be found
 """
 # Start from this file's location
 # Path: library/shared/venv.py -> library/shared -> library -> scripts -> datrix -> datrix-root
 script_dir = Path(__file__).resolve().parent
 current = script_dir

 # Traverse up to find datrix root
 while current != current.parent:
  # Check if this directory contains datrix* projects
  datrix_projects = [d for d in current.iterdir() if d.is_dir() and d.name.startswith("datrix")]
  if len(datrix_projects) >= 2:
   return current

  # Also check if we're in the 'datrix' common folder
  if current.name == "datrix" and (current.parent / "datrix-common").exists():
   return current.parent

  current = current.parent

 # Fallback: check common locations
 common_locations = [
  Path("D:/datrix"),
  Path("d:/datrix"),
  Path("C:/datrix"),
  Path("c:/datrix"),
  Path.home() / "datrix",
 ]

 for location in common_locations:
  if location.exists() and location.is_dir():
   datrix_projects = [d for d in location.iterdir() if d.is_dir() and d.name.startswith("datrix-")]
   if datrix_projects:
    return location

 raise FileNotFoundError("Could not find Datrix root directory")


def get_venv_path() -> Path:
 """Get the path to the Datrix virtual environment.

 Returns:
 Path to the venv directory (e.g., D:\\datrix\\.venv)
 """
 return get_datrix_root() / ".venv"


def is_venv_exists() -> bool:
 """Check if the Datrix virtual environment exists.

 Returns:
 True if the venv exists and has a valid Python executable
 """
 venv_path = get_venv_path()
 if os.name == "nt":
  python_exe = venv_path / "Scripts" / "python.exe"
 else:
  python_exe = venv_path / "bin" / "python"
 return python_exe.exists()


def is_venv_active() -> bool:
 """Check if a virtual environment is currently active.

 Returns:
 True if a venv is active (either via VIRTUAL_ENV or sys.prefix check)
 """
 # Check for VIRTUAL_ENV environment variable
 if os.environ.get("VIRTUAL_ENV"):
  return True

 # Check if sys.prefix differs from sys.base_prefix
 if sys.prefix != sys.base_prefix:
  return True

 return False


def is_datrix_venv_active() -> bool:
 """Check if the Datrix virtual environment is specifically active.

 Returns:
 True if the active venv is the Datrix venv
 """
 if not is_venv_active():
  return False

 active_venv = os.environ.get("VIRTUAL_ENV", "")
 datrix_venv = str(get_venv_path())

 # Normalize paths for comparison
 return os.path.normpath(active_venv).lower() == os.path.normpath(datrix_venv).lower()


def get_venv_python() -> Path:
 """Get the path to the Python executable in the Datrix venv.

 If a venv is already active, returns the active venv's Python.
 Otherwise, returns the Datrix venv's Python.

 Returns:
 Path to the Python executable
 """
 # Check if a virtual environment is already active
 active_venv = os.environ.get("VIRTUAL_ENV")
 if active_venv:
  if os.name == "nt":
   return Path(active_venv) / "Scripts" / "python.exe"
  else:
   return Path(active_venv) / "bin" / "python"

 # Check if sys.prefix indicates we're in a venv
 if sys.prefix != sys.base_prefix:
  return Path(sys.executable)

 # Return the Datrix venv Python
 venv_path = get_venv_path()
 if os.name == "nt":
  return venv_path / "Scripts" / "python.exe"
 else:
  return venv_path / "bin" / "python"


def create_venv(force: bool = False) -> bool:
 """Create the Datrix virtual environment.

 Args:
 force: If True, recreate the venv even if it exists

 Returns:
 True if venv was created successfully
 """
 venv_path = get_venv_path()

 if is_venv_exists() and not force:
  print(f"Virtual environment already exists at: {venv_path}")
  return True

 if force and venv_path.exists():
  print(f"Removing existing virtual environment...")
  import shutil
  shutil.rmtree(venv_path)

 print(f"Creating virtual environment at: {venv_path}")
 print("")

 result = subprocess.run(
 [sys.executable, "-m", "venv", str(venv_path)],
 check=False,
 )

 if result.returncode != 0:
  print(f"ERROR: Failed to create virtual environment", file=sys.stderr)
  return False

 print(f"Virtual environment created successfully")
 return True


def install_package(package_name: str, dev: bool = True) -> bool:
 """Install a Datrix package in editable mode.

 Args:
 package_name: Name of the package (e.g., "datrix-common")
 dev: If True, install with dev dependencies

 Returns:
 True if installation was successful
 """
 datrix_root = get_datrix_root()
 package_path = datrix_root / package_name

 if not package_path.exists():
  print(f"ERROR: Package not found: {package_path}", file=sys.stderr)
  return False

 pyproject_toml = package_path / "pyproject.toml"
 if not pyproject_toml.exists():
  print(f"ERROR: pyproject.toml not found in: {package_path}", file=sys.stderr)
  return False

 python_exe = get_venv_python()
 print(f"Installing {package_name} in editable mode...")

 if dev:
  install_path = f"{package_path}[dev]"
 else:
  install_path = str(package_path)

 result = subprocess.run(
 [str(python_exe), "-m", "pip", "install", "-e", install_path],
 check=False,
 )

 if result.returncode == 0:
  print(f"{package_name} installed successfully")
  return True
 else:
  print(f"ERROR: Failed to install {package_name}", file=sys.stderr)
  return False


def ensure_datrix_venv(install_core: bool = False, quiet: bool = False) -> bool:
 """Ensure the Datrix virtual environment exists and is usable.

 Creates the venv if it doesn't exist. Optionally installs datrix-common.

 Args:
 install_core: If True, also install datrix-common in editable mode
 quiet: If True, suppress informational output

 Returns:
 True if venv is ready to use
 """
 venv_path = get_venv_path()

 # Check if venv exists, create if not
 if not is_venv_exists():
  if not quiet:
   print(f"Virtual environment not found at: {venv_path}")
   print("Creating virtual environment...")
   print("")

  if not create_venv():
   return False

  if not quiet:
   print("")

 # Check if active venv is the Datrix venv
 if is_venv_active():
  active_venv = os.environ.get("VIRTUAL_ENV", "")
  if os.path.normpath(active_venv).lower() != os.path.normpath(str(venv_path)).lower():
   if not quiet:
    print(f"Note: Different virtual environment is active: {active_venv}")
    print(f" Datrix venv is at: {venv_path}")
  else:
   if not quiet:
    print(f"Virtual environment ready at: {venv_path}")
    print(f"To activate: {venv_path}\\Scripts\\Activate.ps1")

 # Optionally install datrix-common
 if install_core:
  datrix_root = get_datrix_root()
  core_path = datrix_root / "datrix-common"
  if core_path.exists():
   # Check if already installed
   python_exe = get_venv_python()
   result = subprocess.run(
    [str(python_exe), "-m", "pip", "show", "datrix-common"],
    capture_output=True,
    check=False,
   )
   if result.returncode != 0:
    if not quiet:
     print("")
    install_package("datrix-common", dev=True)

 return True


def run_in_venv(args: list[str], cwd: Path | str | None = None) -> int:
 """Run a command using the Datrix venv Python.

 Args:
 args: Command arguments (first arg is script/module)
 cwd: Working directory for the command

 Returns:
 Exit code from the command
 """
 python_exe = get_venv_python()

 # Ensure venv exists
 if not is_venv_exists():
  if not ensure_datrix_venv():
   return 1

 result = subprocess.run(
 [str(python_exe)] + args,
 cwd=cwd,
 check=False,
 )
 return result.returncode
