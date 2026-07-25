#!/usr/bin/env python3
"""Canonical enumeration of Datrix's registered generation targets.

Datrix is a multi-language, multi-platform generator. The set of target
*languages* (python, typescript, dotnet, java, ...) and *platforms*
(aws, azure, docker, local, ...) is defined by which ``datrix-codegen-<x>``
packages are installed, and is discovered at runtime from their entry-point
groups -- never a hardcoded literal. Installing a new codegen package makes its
target selectable everywhere with no edit here (design DI-6 / D4 open identity).

Every script that needs "which languages/platforms exist" -- argparse ``choices``,
default sweep sets, gate target lists -- MUST source it here (Python) or via the
sibling PowerShell ``Get-DatrixInstalledLanguages`` / ``Get-DatrixInstalledPlatforms``
helpers, so the answer stays derived from the registered set.

Run directly to print the set for shell consumption::

    python registered_targets.py languages   # one name per line, sorted
    python registered_targets.py platforms
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points

# The entry-point group names are owned by datrix-common's plugin registry;
# import them so this module tracks the single source of truth rather than
# re-spelling the group strings.
from datrix_common.plugin.registry import LANGUAGES_GROUP, PLATFORM_GROUP


def _registered_names(group: str) -> frozenset[str]:
    """Return every entry-point name registered under *group*.

    Name-only enumeration: the plugins are NOT loaded (no leaf codegen package
    is imported), which is exactly what a target-selection/validation list
    needs and keeps this cheap.

    Args:
        group: Entry-point group name (e.g. ``datrix.languages``).

    Returns:
        The frozenset of installed entry-point names in *group*.

    Raises:
        RuntimeError: If entry-point discovery itself fails (a queryable
            ``importlib.metadata`` failure, distinct from a plugin-load error).
    """
    try:
        eps = list(entry_points(group=group))
    except Exception as exc:  # noqa: BLE001 -- re-raised with actionable context
        raise RuntimeError(
            f"Failed to discover '{group}' entry points: {exc}. Expected the "
            f"group to be queryable via importlib.metadata.entry_points(). Fix: "
            f"verify the datrix-codegen-<x> packages are installed into the "
            f"active environment (D:\\datrix\\.venv)."
        ) from exc
    return frozenset(ep.name for ep in eps)


def registered_language_names() -> frozenset[str]:
    """Return every language registered under the ``datrix.languages`` group.

    Derived from installed entry points -- never a hardcoded literal -- so a
    future language package is picked up automatically with no edit here.
    """
    return _registered_names(LANGUAGES_GROUP)


def registered_platform_names() -> frozenset[str]:
    """Return every platform registered under the ``datrix.platforms`` group.

    Derived from installed entry points -- never a hardcoded literal -- so a
    future provider package is picked up automatically with no edit here.
    """
    return _registered_names(PLATFORM_GROUP)


_KIND_TO_ENUMERATOR = {
    "languages": registered_language_names,
    "platforms": registered_platform_names,
}


def main(argv: list[str] | None = None) -> int:
    """Print the requested registered target set, one name per line, sorted.

    Args:
        argv: CLI args; ``argv[0]`` selects ``languages`` or ``platforms``.

    Returns:
        Process exit code (0 on success, 2 on a usage error).
    """
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in _KIND_TO_ENUMERATOR:
        kinds = ", ".join(sorted(_KIND_TO_ENUMERATOR))
        print(f"usage: registered_targets.py <{kinds}>", file=sys.stderr)
        return 2
    for name in sorted(_KIND_TO_ENUMERATOR[args[0]]()):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
