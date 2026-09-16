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
from datrix_common.plugin.registry import LANGUAGES_GROUP, PLATFORM_GROUP, entry_points

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
#: consumes this module (the decision-parity gate, and any future
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
