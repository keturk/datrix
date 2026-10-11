"""Load every installed Datrix plugin once, and say which group failed and why.

``datrix --version`` proves the CLI entry point but loads no plugin. A package whose plugin
fails to register (a missing builtin mapping, a broken import after a refactor) makes every
generation and every test that discovers plugins fail at the same place, far from the cause.
This loads the ``datrix.languages``, ``datrix.generators``, ``datrix.platforms`` and
``datrix.extensions`` groups in turn and prints one line per group: ``OK`` with what loaded, or
``FAILED`` with the registry's own error.

Run by ``Test-DatrixPluginDiscovery`` in ``common/venv.ps1``:
``python -m datrix_scripts.plugin_discovery``.

Exit codes: 0 = every group loaded, 1 = at least one group failed.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

from datrix_common.errors.plugin import PluginError
from datrix_common.plugin.registry import (
    EXTENSION_GROUP,
    GENERATOR_GROUP,
    LANGUAGES_GROUP,
    PLATFORM_GROUP,
    PluginRegistry,
)

EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1


def _languages(registry: PluginRegistry) -> list[str]:
    return registry.language_plugin_names()


def _generators(registry: PluginRegistry) -> list[str]:
    registry.discover_generators()
    return sorted(registry.list_generator_classes())


def _platforms(registry: PluginRegistry) -> list[str]:
    registry.discover_platforms()
    return sorted(registry.list_platform_classes())


def _extensions(registry: PluginRegistry) -> list[str]:
    registry.discover_extensions()
    return sorted(registry.list_extension_classes())


GROUP_LOADERS: Final[tuple[tuple[str, Callable[[PluginRegistry], list[str]]], ...]] = (
    (LANGUAGES_GROUP, _languages),
    (GENERATOR_GROUP, _generators),
    (PLATFORM_GROUP, _platforms),
    (EXTENSION_GROUP, _extensions),
)


def check_plugins() -> list[str]:
    """Load every group; return one failure line per group that did not load."""
    failures: list[str] = []
    for group, load in GROUP_LOADERS:
        try:
            names = load(PluginRegistry())
        except PluginError as exc:
            failures.append(f"FAILED {group}: {exc}")
            print(failures[-1])
            continue
        print(f"OK {group}: {len(names)} plugin(s): {', '.join(names)}")
    return failures


def main() -> int:
    return EXIT_FAILED if check_plugins() else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
