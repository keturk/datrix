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
from pathlib import Path
from types import ModuleType

# The `shared` package (registered-target discovery) lives one directory up.
_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.registered_targets import registered_language_names  # noqa: E402


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


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = complete, 1 = gaps found, 2 = error)
    """
    parser = argparse.ArgumentParser(
        description="Validate type mapping completeness for language generators",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--languages",
        default=None,
        help="Comma-separated list of languages to check (e.g., python,typescript). "
        "Default: every registered datrix.languages target.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    configure_logging(debug=args.debug)

    # Parse language list; default to every registered language when omitted.
    if args.languages is None:
        languages = sorted(registered_language_names())
    else:
        languages = [lang.strip().lower() for lang in args.languages.split(",")]
    if not languages:
        logging.error("No languages specified and none are registered")
        return 2

    return validate_completeness(languages)


if __name__ == "__main__":
    sys.exit(main())
