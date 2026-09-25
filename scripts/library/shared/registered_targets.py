#!/usr/bin/env python3
"""Canonical enumeration of Datrix's registered generation targets.

Datrix is a multi-language, multi-platform generator. The set of target
*languages* (python, typescript, dotnet, java, ...) and *platforms*
(aws, azure, docker, local, ...) is defined by which ``datrix-codegen-<x>``
packages are installed, and is discovered at runtime from their entry-point
groups -- never a hardcoded literal. Installing a new codegen package makes its
target selectable everywhere with no edit here (open-world target identity).

Every script that needs "which languages/platforms exist" -- argparse ``choices``,
default sweep sets, gate target lists -- MUST source it here (Python) or via the
sibling PowerShell ``Get-DatrixInstalledLanguages`` / ``Get-DatrixInstalledPlatforms``
helpers, so the answer stays derived from the registered set.

Run directly to print the set for shell consumption::

    python registered_targets.py languages   # one name per line, sorted
    python registered_targets.py platforms

Every script that also needs "which on-disk ``src/`` directory backs this
registered target" sources it here too, via
``discover_target_package_src_dirs``/``discover_all_other_package_src_dirs`` --
never a hardcoded ``datrix-codegen-{name}`` string-format assumption.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

# The entry-point group names are owned by datrix-common's plugin registry;
# import them so this module tracks the single source of truth rather than
# re-spelling the group strings.
from datrix_common.plugin.registry import (
    GENERATOR_GROUP,
    LANGUAGES_GROUP,
    PLATFORM_GROUP,
    PluginRegistry,
    entry_points,
)

logger = logging.getLogger(__name__)


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


# This file: datrix/scripts/library/shared/registered_targets.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root -- shared/ and
# test/ are sibling directories under library/, so a module living at either
# depth resolves the same WORKSPACE_ROOT.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]
WORKSPACE_ROOT: Path = _HERE.parents[4]

#: The two comparison axes used by every discovery/comparison scanner that
#: consumes this module (the behaviour-parity gate, and any future
#: cross-target scanner).
AXIS_LANGUAGES: Final[str] = "languages"
AXIS_PLATFORMS: Final[str] = "platforms"
_AXIS_ENTRY_POINT_GROUPS: Final[dict[str, str]] = {
    AXIS_LANGUAGES: LANGUAGES_GROUP,
    AXIS_PLATFORMS: PLATFORM_GROUP,
}

#: Separator joining registered names that share ONE package into a single
#: comparison entry (e.g. "azure+azure-vm" -- see fold_names_by_src_dir).
_SHARED_PACKAGE_LABEL_SEPARATOR: Final[str] = "+"

#: Directory-name prefix identifying a Datrix package at the workspace root.
_PACKAGE_DIR_PREFIX: Final[str] = "datrix-"
#: Source subdirectory name every scanned package's importable code lives under.
_SRC_SUBDIR_NAME: Final[str] = "src"


def discover_all_package_locations(monorepo_root: Path) -> dict[str, Path]:
    """Every `datrix-*` package directory with a `src/<import_name>/` tree,
    mapped `import_name -> src_dir`.

    Pure filesystem discovery -- mirrors `dev/check-import-boundaries.py`'s
    own `discover_packages`. No `datrix-codegen-{lang}` naming-convention
    assumption anywhere: the import name is read off whichever directory
    actually exists under `src/`, never synthesized from a language name.
    Public: also the resolver a scanner reaches for when it needs "which file
    backs this dotted module name" for a package outside the axis it is
    comparing (e.g. resolving a shared-layer re-export back to its defining
    module), not just the axis's own target set.

    Args:
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        `{import_name: src_dir}` for every package with a resolvable src tree.
    """
    locations: dict[str, Path] = {}
    for candidate in sorted(monorepo_root.iterdir()):
        if not candidate.is_dir() or not candidate.name.startswith(_PACKAGE_DIR_PREFIX):
            continue
        src_dir = candidate / _SRC_SUBDIR_NAME
        if not src_dir.is_dir():
            continue
        package_dirs = sorted(d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix"))
        if not package_dirs:
            continue
        locations[package_dirs[0].name] = package_dirs[0]
    return locations


def fold_names_by_src_dir(names_by_src_dir: dict[Path, list[str]]) -> dict[str, Path]:
    """Fold registered names sharing ONE package into a single labelled entry.

    Pure and dependency-injected so the self-test can exercise the many-to-one
    case directly, without a live registry that happens to contain one.

    Args:
        names_by_src_dir: `{src_dir: [registered names backed by it]}`.

    Returns:
        `{joined label: src_dir}`, one entry per distinct package.
    """
    return {_SHARED_PACKAGE_LABEL_SEPARATOR.join(sorted(names)): src_dir for src_dir, names in names_by_src_dir.items()}


def entry_point_module_roots(axis: str) -> dict[str, str]:
    """Map each registered target name on *axis* to its entry point's module root.

    Read from the entry point's DECLARED module rather than by importing and
    instantiating the plugin: a platform plugin needs generation context to
    construct, and this report only needs to know which package the code lives
    in. For the language axis this is provably the same answer the plugin-class
    route gives -- asserted every run by the self-test's
    `_language_entry_point_roots_match_plugin_roots` check, so the two can
    never silently diverge.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.

    Returns:
        `{registered name: top-level module name}`.
    """
    group = _AXIS_ENTRY_POINT_GROUPS[axis]
    return {ep.name: ep.module.split(".")[0] for ep in entry_points(group=group)}


def discover_target_package_src_dirs(axis: str, target_names: frozenset[str], monorepo_root: Path) -> dict[str, Path]:
    """Resolve the registered target names on *axis* to their packages'
    `src/<import_name>` directories, matched against the filesystem package map
    -- never a hardcoded `datrix-codegen-{name}` string-format assumption.

    **Names sharing one package are folded into a single entry** whose label
    joins them (e.g. `azure+azure-vm`), because the comparison unit is the
    package: two registered names backed by the same src tree are not parallel
    implementations of each other. On the 1:1 language axis every group has
    exactly one member, so each label is just the language name and the report
    is unchanged.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.
        target_names: Registered names on that axis to resolve.
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        `{label: absolute src package directory}`, one entry per distinct
        package.

    Raises:
        ValueError: If a registered name resolves to an import root with no
            matching on-disk package, or has no entry point at all -- a real
            configuration error, never silently skipped (shrinking the target
            set quietly would hide the exact drift this report exists to
            surface).
    """
    all_locations = discover_all_package_locations(monorepo_root)
    module_roots = entry_point_module_roots(axis)

    names_by_src_dir: dict[Path, list[str]] = {}
    for name in sorted(target_names):
        import_name = module_roots.get(name)
        if import_name is None:
            raise ValueError(
                f"Registered {axis} target {name!r} has no entry point in group "
                f"{_AXIS_ENTRY_POINT_GROUPS[axis]!r}. Registered entry points: "
                f"{sorted(module_roots)}."
            )
        src_dir = all_locations.get(import_name)
        if src_dir is None:
            raise ValueError(
                f"Could not resolve an on-disk src/ directory for {axis} target "
                f"{name!r} (its registered plugin lives in module root "
                f"{import_name!r}). Expected a 'datrix-*' directory under "
                f"{monorepo_root} whose src/ tree contains a {import_name!r} "
                f"package directory. Discovered package roots: "
                f"{sorted(all_locations)}."
            )
        names_by_src_dir.setdefault(src_dir, []).append(name)

    folded = fold_names_by_src_dir(names_by_src_dir)
    if len(folded) < len(target_names):
        logger.info(
            "axis=%s folded %d registered name(s) into %d distinct package(s): %s",
            axis,
            len(target_names),
            len(folded),
            sorted(folded),
        )
    return folded


#: Process-wide registry used to resolve which `datrix.generators` native
#: classes declare a `transpiler_profile`, when a caller supplies none.
#: Discovery is idempotent and cached on the instance. This is discovery
#: infrastructure, not a `(target -> policy)` table: it enumerates nothing
#: and hardcodes no generator name.
_GENERATOR_REGISTRY: Final[PluginRegistry] = PluginRegistry()


def _native_generator_classes_with_transpiler_profile(
    registry: PluginRegistry | None = None,
) -> dict[str, type]:
    """The ONE construction-free "native `datrix.generators` classes
    declaring a `transpiler_profile`" scan both
    `registered_client_target_generator_names` and
    `client_target_generator_module_roots` call, so the two enumerations can
    never silently diverge.

    Reads `PluginRegistry.list_native_generator_classes()` -- excludes the
    language generators folded in from `datrix.languages` (a folded
    `LanguageGenerator` carries no `descriptor` and is never a client
    target) -- and inspects each remaining class's `descriptor` attribute
    directly. No plugin is instantiated: the same construction-free
    discipline `datrix_common.plugin.capability_resolution.declaration_for_provider`
    already uses for platform plugins, for the identical reason (aws/azure/
    docker-shaped generators need constructor arguments that do not exist
    yet at discovery time).

    Args:
        registry: Registry to resolve against; defaults to the module-level
            shared registry. Tests pass a registry seeded with fixture
            generator plugins.

    Returns:
        `{registered name: native generator class}`, restricted to classes
        whose `descriptor.transpiler_profile` is not `None`.

    Raises:
        RuntimeError: If `datrix.generators` discovery itself fails (an
            entry-point scan or a plugin-class import failure).
    """
    reg = registry if registry is not None else _GENERATOR_REGISTRY
    try:
        classes = reg.list_native_generator_classes()
    except Exception as exc:  # noqa: BLE001 -- re-raised with actionable context
        raise RuntimeError(
            f"Failed to discover native '{GENERATOR_GROUP}' generator classes: {exc}. "
            f"Expected every '{GENERATOR_GROUP}' entry point to be queryable via "
            f"importlib.metadata.entry_points() and loadable. Fix: verify the "
            f"datrix-codegen-<x> packages are installed into the active environment "
            f"(D:\\datrix\\.venv)."
        ) from exc
    return {
        name: cls
        for name, cls in classes.items()
        if getattr(cls, "descriptor", None) is not None and cls.descriptor.transpiler_profile is not None
    }


def registered_client_target_generator_names(registry: PluginRegistry | None = None) -> frozenset[str]:
    """Every ``datrix.generators`` entry point whose NATIVE generator class
    declares a non-``None`` ``transpiler_profile`` on its ``PluginDescriptor``.

    Construction-free: reads ``PluginRegistry.list_native_generator_classes()``
    (excludes the language generators folded in from ``datrix.languages`` --
    those carry no ``descriptor`` and are never client targets) and inspects
    each class's ``descriptor`` attribute directly, without instantiating a
    plugin that needs generation-context constructor arguments that do not
    exist yet at discovery time (the same construction-free discipline
    ``declaration_for_provider`` already uses for platforms).

    Args:
        registry: Registry to resolve against; defaults to the module-level
            shared registry. Tests pass a registry seeded with fixture
            generator plugins.

    Returns:
        The frozenset of registered `datrix.generators` names whose descriptor
        carries a `transpiler_profile` -- the frontend-client renderer set
        the behaviour-parity language axis must include beside every
        `datrix.languages` package.

    Raises:
        RuntimeError: If `datrix.generators` discovery itself fails.
    """
    return frozenset(_native_generator_classes_with_transpiler_profile(registry))


def client_target_generator_module_roots(
    names: frozenset[str], registry: PluginRegistry | None = None
) -> dict[str, str]:
    """The ``datrix.generators``-group sibling of ``entry_point_module_roots``,
    restricted to *names* (normally
    ``registered_client_target_generator_names()``'s result).

    A separate function, never a branch inside ``entry_point_module_roots``:
    that function's ``_AXIS_ENTRY_POINT_GROUPS`` lookup is keyed by
    ``AXIS_LANGUAGES``/``AXIS_PLATFORMS`` only, and a client-target generator's
    entry point lives under ``GENERATOR_GROUP``, a third group neither axis
    constant names. Reads each class's own ``__module__`` -- the class is
    already in hand from the same construction-free scan
    ``registered_client_target_generator_names`` runs, so it is never
    imported a second time here.

    Args:
        names: Registered `datrix.generators` names to resolve.
        registry: Registry to resolve against; defaults to the module-level
            shared registry. Tests pass a registry seeded with fixture
            generator plugins.

    Returns:
        `{registered name: top-level module name}`, restricted to *names*.

    Raises:
        RuntimeError: If `datrix.generators` discovery itself fails.
    """
    classes = _native_generator_classes_with_transpiler_profile(registry)
    return {name: cls.__module__.split(".")[0] for name, cls in classes.items() if name in names}


def discover_client_target_generator_src_dirs(
    names: frozenset[str], monorepo_root: Path, registry: PluginRegistry | None = None
) -> dict[str, Path]:
    """The ``datrix.generators``-group sibling of ``discover_target_package_src_dirs``,
    for the client-target names *names* resolves.

    Reuses ``discover_all_package_locations``/``fold_names_by_src_dir`` -- the
    same on-disk resolution and same-package folding -- seeded from
    ``client_target_generator_module_roots(names, registry)`` instead of
    ``entry_point_module_roots(axis)``.

    Args:
        names: Registered `datrix.generators` names to resolve (normally
            `registered_client_target_generator_names()`'s result).
        monorepo_root: The workspace root containing every `datrix-*` checkout.
        registry: Registry to resolve against; defaults to the module-level
            shared registry. Tests pass a registry seeded with fixture
            generator plugins.

    Returns:
        `{label: absolute src package directory}`.

    Raises:
        ValueError: A name resolves to no on-disk package (same failure shape
            as `discover_target_package_src_dirs`).
        RuntimeError: If `datrix.generators` discovery itself fails
            (propagates from `client_target_generator_module_roots`).
    """
    all_locations = discover_all_package_locations(monorepo_root)
    module_roots = client_target_generator_module_roots(names, registry)

    names_by_src_dir: dict[Path, list[str]] = {}
    for name in sorted(names):
        import_name = module_roots.get(name)
        if import_name is None:
            raise ValueError(
                f"Registered client-target generator {name!r} has no native "
                f"'{GENERATOR_GROUP}' class declaring a 'transpiler_profile'. "
                f"Client-target generators with a transpiler_profile: {sorted(module_roots)}."
            )
        src_dir = all_locations.get(import_name)
        if src_dir is None:
            raise ValueError(
                f"Could not resolve an on-disk src/ directory for client-target "
                f"generator {name!r} (its registered plugin class lives in module "
                f"root {import_name!r}). Expected a 'datrix-*' directory under "
                f"{monorepo_root} whose src/ tree contains a {import_name!r} "
                f"package directory. Discovered package roots: {sorted(all_locations)}."
            )
        names_by_src_dir.setdefault(src_dir, []).append(name)

    return fold_names_by_src_dir(names_by_src_dir)


def discover_all_other_package_src_dirs(monorepo_root: Path, exclude_dirs: frozenset[Path]) -> list[Path]:
    """Every OTHER datrix-* package's src/ tree -- literally every discovered
    package directory not already covered by the caller's own target set
    (datrix-common, datrix-codegen-common, datrix-cli, every non-language
    datrix-codegen-* package, datrix-extensions, datrix-language, and any
    future package). Never a hardcoded package list: a new `datrix-*` package
    appearing on disk is picked up automatically.

    Args:
        monorepo_root: The workspace root containing every `datrix-*` checkout.
        exclude_dirs: Src dirs already covered by the caller's own target set.

    Returns:
        Sorted list of every other discovered package's src directory.
    """
    all_locations = discover_all_package_locations(monorepo_root)
    return sorted(src_dir for src_dir in all_locations.values() if src_dir not in exclude_dirs)


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
