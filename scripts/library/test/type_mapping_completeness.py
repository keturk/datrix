#!/usr/bin/env python3
"""Type mapping completeness validator for Datrix language generators.

Validates that all canonical types in the TypeRegistry have mappings in
the specified language generators. Exits nonzero if any gaps are found.

The language set is discovered from the ``datrix.languages`` entry-point group
at runtime -- never a hardcoded literal -- so a new datrix-codegen-<lang>
package is validated automatically with no edit here.

Usage:
    python type_mapping_completeness.py                       # every registered language
    python type_mapping_completeness.py --languages python,typescript
    python type_mapping_completeness.py --languages python --debug
"""

import argparse
import importlib
import logging
import sys
from collections.abc import Mapping
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType
from typing import Final

# The `shared` package (registered-target discovery) lives one directory up.
_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_common.generation.discovery import list_available_generators  # noqa: E402
from datrix_common.plugin.registry import EXTENSION_GROUP  # noqa: E402

#: Every language's type_mappings module exposes exactly one module-level
#: dict whose name ends with this suffix (PYTHON_EXTENSION_MAPS,
#: JAVA_EXTENSION_MAPS, SQL_EXTENSION_MAPS, TS_EXTENSION_MAPS,
#: DOTNET_EXTENSION_MAPS -- verified by reading all five; the language-name
#: PREFIX is not uniform, e.g. "TS" not "TYPESCRIPT", so this check locates
#: the dict by suffix, never by guessing a per-language constant name).
_EXTENSION_MAPS_SUFFIX: Final[str] = "_EXTENSION_MAPS"

#: SQL registers under `datrix.generators`, not `datrix.languages` -- it is a
#: singular, named non-language type-mapping surface the design requires
#: alongside the (fully-derived) language axis. Naming this one literal does
#: NOT truncate the language axis: registered_language_names() below still
#: derives that axis at runtime with no per-language literal anywhere.
_SQL_SURFACE_NAME: Final[str] = "sql"

#: Self-test-only synthetic names (neutral, never collide with a real
#: language or a real installed extensions pack).
_SELF_TEST_PACK: Final[str] = "self_test_pack"
_SELF_TEST_SURFACE_COMPLETE: Final[str] = "self_test_surface_with_key"
_SELF_TEST_SURFACE_MISSING: Final[str] = "self_test_surface_missing_key"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def import_language_mappings(language: str) -> ModuleType:
    """Import a language's ``type_mappings`` module (registering its mappings).

    The language's package root is resolved from its registered
    ``datrix.languages`` plugin, so this works for every installed language
    with no per-language branch. Importing ``<package>.type_mappings`` triggers
    that language's registration into the global type-mapping registry.

    Args:
        language: A registered ``datrix.languages`` entry-point name.

    Returns:
        The imported ``type_mappings`` module.

    Raises:
        ValueError: If *language* is not a registered ``datrix.languages`` target.
        ImportError: If the language's ``type_mappings`` module cannot be imported.
    """
    logger = logging.getLogger(__name__)

    registered = registered_language_names()
    if language not in registered:
        raise ValueError(
            f"Unknown language: {language}. "
            f"Registered languages: {', '.join(sorted(registered))}."
        )

    from datrix_common.generation.discovery import get_language_plugin

    plugin = get_language_plugin(language)
    package_root = type(plugin).__module__.split(".")[0]
    module_name = f"{package_root}.type_mappings"
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(
            f"Failed to import {language} type mappings ({module_name}). "
            f"Is datrix-codegen-{language} installed and does it ship a "
            f"type_mappings module? Error: {e}"
        ) from e
    logger.debug("Imported %s type mappings from %s", language, module_name)
    return module


def validate_completeness(languages: list[str]) -> int:
    """Validate type mapping completeness for specified languages.

    Args:
        languages: List of language names to check

    Returns:
        Exit code (0 = complete, 1 = gaps found, 2 = error)
    """
    logger = logging.getLogger(__name__)

    try:
        from datrix_common.generation.type_mapping_registry import global_registry
    except ImportError as e:
        logger.error("Failed to import global_registry: %s", e)
        logger.error("Is datrix-common installed?")
        return 2

    # Import all requested language mappings
    for language in languages:
        try:
            import_language_mappings(language)
        except (ImportError, ValueError) as e:
            logger.error(str(e))
            return 2

    # Run completeness validation for each language
    all_complete = True
    for language in languages:
        logger.info("Checking type mapping completeness for %s...", language)

        try:
            missing = global_registry.unmapped_types(language)
        except Exception as e:
            logger.error("Validation failed for %s: %s", language, e)
            return 2

        if missing:
            all_complete = False
            logger.error("%s type mappings are incomplete:", language.capitalize())
            logger.error("Missing mappings for %d types:", len(missing))
            for type_name in sorted(missing):
                logger.error("  - %s", type_name)
        else:
            logger.info("%s type mappings are complete", language.capitalize())

    if all_complete:
        logger.info("All type mappings are complete")
        return 0
    else:
        logger.error("Type mapping completeness check failed")
        return 1


def registered_extension_pack_names() -> frozenset[str]:
    """Return every installed ``datrix.extensions`` pack name.

    Derived from entry points -- never a hardcoded literal -- so a future
    ``datrix-extensions``-shipped pack (a third, fourth, ... extension) is
    covered automatically with no edit here.

    Returns:
        The frozenset of installed ``datrix.extensions`` entry-point names.

    Raises:
        RuntimeError: If entry-point discovery itself fails.
    """
    try:
        eps = list(entry_points(group=EXTENSION_GROUP))
    except Exception as exc:  # noqa: BLE001 -- re-raised with actionable context
        raise RuntimeError(
            f"Failed to discover '{EXTENSION_GROUP}' entry points: {exc}. Fix: "
            f"verify datrix-extensions is installed into the active environment "
            f"(D:\\datrix\\.venv)."
        ) from exc
    return frozenset(ep.name for ep in eps)


def _sql_type_mappings_module() -> ModuleType:
    """Resolve datrix-codegen-sql's ``type_mappings`` module.

    SQL is not a ``datrix.languages`` plugin, so it cannot go through
    :func:`import_language_mappings`. Its package root is still resolved via
    the sanctioned :func:`list_available_generators` API (never a hardcoded
    ``datrix_codegen_sql`` package-path literal).

    Returns:
        The imported ``datrix_codegen_sql.type_mappings`` module.

    Raises:
        ValueError: If no ``"sql"`` entry is registered under ``datrix.generators``.
        ImportError: If the resolved module cannot be imported.
    """
    available = list_available_generators()
    if _SQL_SURFACE_NAME not in available:
        raise ValueError(
            f"No {_SQL_SURFACE_NAME!r} generator registered under 'datrix.generators'. "
            f"Installed: {sorted(available)}. Fix: install datrix-codegen-sql into "
            f"D:\\datrix\\.venv (editable install)."
        )
    class_path = available[_SQL_SURFACE_NAME]  # e.g. "datrix_codegen_sql.plugin:SQLGenerator"
    module_path = class_path.split(":", 1)[0]
    package_root = module_path.split(".")[0]
    module_name = f"{package_root}.type_mappings"
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        raise ImportError(
            f"Failed to import SQL type mappings ({module_name}). Is "
            f"datrix-codegen-sql installed and does it ship a type_mappings "
            f"module? Error: {e}"
        ) from e


def extension_map_completeness_surfaces() -> dict[str, ModuleType]:
    """Return ``{surface_name: type_mappings module}`` for every checked surface.

    Every registered ``datrix.languages`` target PLUS the singular ``"sql"``
    surface (see :data:`_SQL_SURFACE_NAME`).

    Returns:
        One entry per surface, keyed by surface name.
    """
    surfaces: dict[str, ModuleType] = {
        language: import_language_mappings(language)
        for language in sorted(registered_language_names())
    }
    surfaces[_SQL_SURFACE_NAME] = _sql_type_mappings_module()
    return surfaces


def _extension_maps_dict(surface: str, module: ModuleType) -> Mapping[str, object]:
    """Locate the single module-level dict whose name ends with the
    ``*_EXTENSION_MAPS`` suffix.

    Args:
        surface: The surface name (for error messages).
        module: The surface's imported ``type_mappings`` module.

    Returns:
        The extension-name-keyed mapping dict.

    Raises:
        ValueError: If the module exposes zero or more than one such dict --
            the established convention (verified across all five current
            surfaces) requires exactly one.
    """
    candidates = {
        name: value
        for name, value in vars(module).items()
        if name.endswith(_EXTENSION_MAPS_SUFFIX) and isinstance(value, dict)
    }
    if len(candidates) != 1:
        raise ValueError(
            f"{surface} ({module.__name__}) must expose EXACTLY ONE module-level "
            f"dict named '*{_EXTENSION_MAPS_SUFFIX}' (found {sorted(candidates)}). "
            f"Expected a single '{{PREFIX}}{_EXTENSION_MAPS_SUFFIX}: "
            f"dict[str, dict[str, ...]]' constant keyed by extension-pack name, "
            f"following the convention every other surface already uses (see "
            f"PYTHON_EXTENSION_MAPS, TS_EXTENSION_MAPS, ...)."
        )
    return next(iter(candidates.values()))


def compare_extension_map_completeness(
    installed_packs: frozenset[str],
    per_surface_maps: Mapping[str, Mapping[str, object]],
) -> dict[str, frozenset[str]]:
    """Compare every surface's extension-map keys against the installed pack set.

    Args:
        installed_packs: Every installed ``datrix.extensions`` pack name.
        per_surface_maps: ``{surface_name: extension_maps_dict}``.

    Returns:
        ``{surface_name: missing_pack_names}`` -- packs installed but absent
        as a key in that surface's map. Every value is empty iff extension-map
        completeness holds for every surface (D3's acceptance property).

    Raises:
        ValueError: If either argument is empty -- a completeness comparison
            with nothing installed to require, or nothing to check, is
            vacuous and must never be silently reported as "holds".
    """
    if not installed_packs:
        raise ValueError(
            "compare_extension_map_completeness requires at least one installed "
            "datrix.extensions pack -- comparing against an empty required set is "
            "vacuously 'complete' and must never be silently reported as passing."
        )
    if not per_surface_maps:
        raise ValueError(
            "compare_extension_map_completeness requires at least one surface "
            "(language or sql) to check -- comparing zero surfaces is vacuous."
        )
    return {
        surface: installed_packs - frozenset(ext_map.keys())
        for surface, ext_map in per_surface_maps.items()
    }


def run_extension_map_self_test() -> None:
    """Prove the comparator detects a forced missing-key mismatch before any
    real comparison is trusted (non-vacuity requirement).

    Feeds :func:`compare_extension_map_completeness` a synthetic MATCHING
    surface (the pack's key present, empty dict value -- must report zero
    missing) and a synthetic surface MISSING the key entirely (must report
    exactly that pack as missing).

    Raises:
        AssertionError: If either synthetic case does not produce the
            expected result.
    """
    matching: dict[str, Mapping[str, object]] = {
        _SELF_TEST_SURFACE_COMPLETE: {_SELF_TEST_PACK: {}}
    }
    matching_result = compare_extension_map_completeness(
        frozenset({_SELF_TEST_PACK}), matching
    )
    if matching_result[_SELF_TEST_SURFACE_COMPLETE]:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_extension_map_completeness "
            f"reported a hole for a synthetic surface that DOES carry the pack's "
            f"key ({matching_result}) -- the comparator is over-triggering."
        )

    missing: dict[str, Mapping[str, object]] = {_SELF_TEST_SURFACE_MISSING: {}}
    missing_result = compare_extension_map_completeness(
        frozenset({_SELF_TEST_PACK}), missing
    )
    if _SELF_TEST_PACK not in missing_result[_SELF_TEST_SURFACE_MISSING]:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_extension_map_completeness "
            f"did not detect the forced missing key (expected {_SELF_TEST_PACK!r} "
            f"reported missing for {_SELF_TEST_SURFACE_MISSING!r}, got "
            f"{missing_result}) -- a check that cannot detect a real hole is "
            f"worthless."
        )


def check_extension_map_completeness() -> int:
    """Real-tree extension-map completeness check (D3).

    Returns:
        Exit code (0 = every installed pack has a key on every surface,
        1 = at least one hole found, 2 = discovery/import error).
    """
    logger = logging.getLogger(__name__)
    try:
        installed_packs = registered_extension_pack_names()
        surfaces = extension_map_completeness_surfaces()
        per_surface_maps = {
            name: _extension_maps_dict(name, module) for name, module in surfaces.items()
        }
        missing_by_surface = compare_extension_map_completeness(
            installed_packs, per_surface_maps
        )
    except (ValueError, ImportError, RuntimeError) as e:
        logger.error("Extension-map completeness check could not run: %s", e)
        return 2

    ok = True
    for surface in sorted(missing_by_surface):
        missing = missing_by_surface[surface]
        if missing:
            ok = False
            logger.error(
                "EXTENSION-MAP HOLE: surface=%s missing_pack(s)=%s",
                surface, sorted(missing),
            )
    if ok:
        logger.info(
            "Extension-map completeness holds: %d installed pack(s) across %d "
            "surface(s) (%s)",
            len(installed_packs), len(missing_by_surface), sorted(missing_by_surface),
        )
    else:
        logger.error("Extension-map completeness check FAILED.")
    return 0 if ok else 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = both checks pass or --self-test passed, 1 = either
        check found gaps, 2 = the self-test failed, an error occurred, or no
        languages are registered).
    """
    parser = argparse.ArgumentParser(
        description="Validate type mapping completeness for language generators",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--languages",
        default=None,
        help="Comma-separated list of languages to check for the canonical-type "
        "check (e.g., python,typescript). Default: every registered "
        "datrix.languages target. Does NOT restrict the extension-map "
        "completeness check below, which always covers every registered "
        "language plus sql.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real checks",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    try:
        run_extension_map_self_test()
    except AssertionError as e:
        logger.error(
            "Non-vacuity self-test FAILED -- aborting before any real check is "
            "trusted: %s", e,
        )
        return 2
    logger.info(
        "Non-vacuity self-test passed: the extension-map comparator detects a "
        "forced missing-key hole and reports zero for a satisfied surface."
    )

    if args.self_test:
        return 0

    if args.languages is None:
        languages = sorted(registered_language_names())
    else:
        languages = [lang.strip().lower() for lang in args.languages.split(",")]
    if not languages:
        logging.error("No languages specified and none are registered")
        return 2

    canonical_result = validate_completeness(languages)
    extension_result = check_extension_map_completeness()

    if canonical_result == 2 or extension_result == 2:
        return 2
    if canonical_result == 1 or extension_result == 1:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
