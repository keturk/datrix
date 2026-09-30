"""Load the validated Application a documentation script renders from.

Every docs script (diagrams, OpenAPI/AsyncAPI specs) reads the same AST the
generation pipeline builds for the same source and profile: config
resolution, system-entity injection, then semantic analysis with
infrastructure config resolution run as a pre-seal hook. Re-deriving that
sequence per script is how one of them came to resolve infrastructure configs
after analysis sealed the tree, failing every real application with
``Cannot mutate System.config -- this node is sealed``. The sequence lives
once, in ``datrix-cli``, and this module is the scripts' only way to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

__all__ = ["SYSTEM_DTRX", "load_application", "resolve_system_source"]

SYSTEM_DTRX = "system.dtrx"

_PURPOSE = "documentation generation"


def resolve_system_source(source_path: Path) -> Path:
    """The ``.dtrx`` entry point for *source_path*: the file itself, or the
    ``system.dtrx`` inside a directory.

    Raises:
        FileNotFoundError: *source_path* does not exist, or is a directory
            holding no ``system.dtrx``.
    """
    if source_path.is_dir():
        system_dtrx = source_path / SYSTEM_DTRX
        if not system_dtrx.is_file():
            raise FileNotFoundError(
                f"No {SYSTEM_DTRX} found in {source_path}. Pass the application's "
                f"{SYSTEM_DTRX}, or the directory that holds it."
            )
        return system_dtrx
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Source file not found: {source_path}. Pass an existing .dtrx file or "
            f"a directory holding {SYSTEM_DTRX}."
        )
    return source_path


def load_application(source_path: Path, profile: str) -> Application:
    """Parse, config-resolve and analyze *source_path* under *profile*.

    Args:
        source_path: A ``.dtrx`` file, or a directory holding ``system.dtrx``.
            Its directory is the ConfigDSL resolution root.
        profile: ConfigDSL profile to resolve (e.g. ``test``, ``staging``).

    Returns:
        The validated, sealed Application.

    Raises:
        FileNotFoundError: No ``.dtrx`` entry point at *source_path*.
        ValueError: Parsing or semantic analysis failed; the message lists
            every analysis error with its location.
        ConfigResolutionError: A named config file is missing, unparsable, or
            invalid for *profile*.
    """
    from datrix_cli.commands._app_spec import resolve_application
    from datrix_language.registration import register_all

    register_all()
    entry = resolve_system_source(source_path)
    return resolve_application(entry.parent, entry, profile, purpose=_PURPOSE)
