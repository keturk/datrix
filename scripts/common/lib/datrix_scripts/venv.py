"""The shared Datrix virtual environment, as Python scripts see it.

Every wrapper activates the venv before it runs Python (``common/DatrixPythonScript.psm1``), so
a script only ever needs to locate the venv and its interpreter, or ask whether one is active.
"""

import os
import sys
from pathlib import Path

from datrix_scripts.paths import WORKSPACE_DIR


def get_venv_path() -> Path:
 """Get the path to the Datrix virtual environment.

 Returns:
 Path to the venv directory (e.g., D:\\datrix\\.venv)
 """
 return WORKSPACE_DIR / ".venv"


def is_venv_active() -> bool:
 """Check if a virtual environment is currently active.

 Returns:
 True if a venv is active (either via VIRTUAL_ENV or sys.prefix check)
 """
 if os.environ.get("VIRTUAL_ENV"):
  return True
 return sys.prefix != sys.base_prefix


def get_venv_python() -> Path:
 """Get the path to the Python executable in the Datrix venv.

 If a venv is already active, returns the active venv's Python.
 Otherwise, returns the Datrix venv's Python.

 Returns:
 Path to the Python executable
 """
 active_venv = os.environ.get("VIRTUAL_ENV")
 if active_venv:
  if os.name == "nt":
   return Path(active_venv) / "Scripts" / "python.exe"
  return Path(active_venv) / "bin" / "python"

 if sys.prefix != sys.base_prefix:
  return Path(sys.executable)

 venv_path = get_venv_path()
 if os.name == "nt":
  return venv_path / "Scripts" / "python.exe"
 return venv_path / "bin" / "python"
