"""Load a module of the harness hooks directory by path.

A repo gate that audits what a hook enforces, or enforces the same ceiling, shares the hook's
one definition instead of keeping a copy: the hooks run under the system interpreter from
``claude-config/.claude/hooks`` and are no installed distribution, so the module is loaded by
path. A hooks module may import its siblings (``from _command_shape import ...``), so the hooks
directory goes on ``sys.path`` (once) before the module executes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.paths import SHOWCASE_DIR

#: The harness hooks directory.
HOOKS_DIR: Final[Path] = SHOWCASE_DIR / "claude-config" / ".claude" / "hooks"
#: The whole-suite classifier ``guard-full-suite-runs.py`` imports, and the module it imports.
SUITE_INVOCATION_MODULE: Final[str] = "_suite_invocation"
COMMAND_SHAPE_MODULE: Final[str] = "_command_shape"


class HookModuleError(RuntimeError):
    """A hooks module is missing or cannot be loaded."""


def load_hook_module(name: str, hooks_dir: Path = HOOKS_DIR) -> ModuleType:
    """Load the hooks module *name* (``_suite_invocation``) from *hooks_dir*.

    Raises:
        HookModuleError: The module file is missing, or no import spec can be built for it.
    """
    path = hooks_dir / f"{name}.py"
    if not path.is_file():
        raise HookModuleError(
            f"{path} not found. A script that shares a hook's definition cannot fall back to a "
            f"private copy; restore {name}.py in the hooks directory."
        )
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HookModuleError(f"Could not build an import spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_suite_invocation(hooks_dir: Path = HOOKS_DIR) -> ModuleType:
    """Load ``_suite_invocation.py``, the classifier and ceilings ``guard-full-suite-runs.py`` uses,
    after proving its sibling ``_command_shape.py`` is there.

    Raises:
        HookModuleError: Either module is missing or cannot be loaded.
    """
    if not (hooks_dir / f"{COMMAND_SHAPE_MODULE}.py").is_file():
        raise HookModuleError(
            f"{hooks_dir / f'{COMMAND_SHAPE_MODULE}.py'} not found; {SUITE_INVOCATION_MODULE}.py imports it. "
            f"Restore it in the hooks directory."
        )
    return load_hook_module(SUITE_INVOCATION_MODULE, hooks_dir)


__all__ = [
    "COMMAND_SHAPE_MODULE",
    "HOOKS_DIR",
    "SUITE_INVOCATION_MODULE",
    "HookModuleError",
    "load_hook_module",
    "load_suite_invocation",
]
