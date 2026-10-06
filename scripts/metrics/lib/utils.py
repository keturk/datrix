"""Utility functions for metrics scripts."""

import os
import sys
from pathlib import Path


def get_venv_python(project_root: Path) -> Path:
    """Get path to Python in virtual environment.

    First checks if a virtual environment is already active (via VIRTUAL_ENV env var).
    If active, uses that Python. Otherwise, falls back to project-local .venv.
    """
    # Check if a virtual environment is already active
    active_venv = os.environ.get("VIRTUAL_ENV")
    if active_venv:
        # Use the active virtual environment's Python
        if os.name == "nt":
            return Path(active_venv) / "Scripts" / "python.exe"
        else:
            return Path(active_venv) / "bin" / "python"

    # Check if sys.prefix indicates we're in a venv
    if sys.prefix != sys.base_prefix:
        # We're in a venv, use sys.executable
        return Path(sys.executable)

    # Fallback to project-local .venv
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    else:
        return project_root / ".venv" / "bin" / "python"
