"""Pytest configuration for scripts tests.

Adds the scripts/library directory to sys.path so that test files can
import script modules using the same paths as the scripts themselves
(e.g., ``from dev.generate_doc_fragments import ...``).

Also pre-imports script modules that replace sys.stdout/sys.stderr at
module level (for UTF-8 on Windows), protecting pytest's capture
mechanism by temporarily hiding the win32 platform check.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# scripts/library/ is the root for script module imports
_library_dir = Path(__file__).resolve().parent.parent / "library"
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

# Pre-import modules that wrap sys.stdout/stderr at module level on
# Windows. We temporarily set sys.platform to a non-win32 value so
# the module-level guard ``if sys.platform == "win32"`` is skipped.
# This prevents the TextIOWrapper replacement from breaking pytest's
# capture mechanism.
_real_platform = sys.platform
sys.platform = "testing"  # type: ignore[assignment]
try:
    importlib.import_module("dev.generate_doc_fragments")
finally:
    sys.platform = _real_platform
