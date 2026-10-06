"""Fixed locations in the scripts tree, the showcase repository and the workspace.

Every script locates these through this module rather than counting ``.parent`` steps up from
its own file: a script's depth changes whenever it moves between folders, and a stale count
silently resolves to the wrong directory. This module's own position is fixed --
``scripts/common/lib/datrix_scripts/paths.py`` -- so the anchors below are derived once, here.

Python run by a wrapper lives in the ``lib/`` folder beside that wrapper
(``scripts/<folder>/lib/`` or ``scripts/gates/<family>/lib/``); code imported from more than
one folder lives in this package, which wrappers put on ``PYTHONPATH``
(``Set-DatrixPythonPath`` in ``common/DatrixScriptCommon.psm1``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
PYTHONPATH_ROOT: Final[Path] = PACKAGE_DIR.parent
SCRIPTS_DIR: Final[Path] = PYTHONPATH_ROOT.parents[1]
CONFIG_DIR: Final[Path] = SCRIPTS_DIR / "config"
SHOWCASE_DIR: Final[Path] = SCRIPTS_DIR.parent
WORKSPACE_DIR: Final[Path] = SHOWCASE_DIR.parent

LIB_DIR_NAME: Final[str] = "lib"


def lib_script(folder: str, file_name: str) -> Path:
    """Return the path of a Python file in a scripts folder's ``lib/``.

    Args:
        folder: The folder relative to ``scripts/`` that owns the wrapper, e.g. ``"dev"`` or
            ``"gates/parity"``.
        file_name: The file name inside that folder's ``lib/``, e.g. ``"generate.py"``.

    Raises:
        FileNotFoundError: If no such file exists, naming the path that was expected.
    """
    path = SCRIPTS_DIR / folder / LIB_DIR_NAME / file_name
    if not path.is_file():
        raise FileNotFoundError(
            f"Expected script {file_name!r} in {folder}/{LIB_DIR_NAME}/ under {SCRIPTS_DIR}, "
            f"but {path} does not exist. Check the folder name against the scripts tree "
            "(scripts/README.md lists every folder)."
        )
    return path


def script_env() -> dict[str, str]:
    """Return this process's environment with the shared package root first on ``PYTHONPATH``.

    Pass it as ``env=`` to every subprocess that runs a scripts ``.py`` file: a process started
    by a Claude Code hook or MCP server did not come through a wrapper, so it may not carry
    ``PYTHONPATH`` for its children to inherit.
    """
    env = dict(os.environ)
    root = str(PYTHONPATH_ROOT)
    existing = [entry for entry in env.get("PYTHONPATH", "").split(os.pathsep) if entry and entry != root]
    env["PYTHONPATH"] = os.pathsep.join([root, *existing])
    return env
