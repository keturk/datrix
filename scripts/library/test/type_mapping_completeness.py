#!/usr/bin/env python3
"""Type mapping completeness validator for Datrix language generators.

Validates that all canonical types in the TypeRegistry have mappings in
the specified language generators. Exits nonzero if any gaps are found.

Usage:
    python type_mapping_completeness.py --languages python,typescript
    python type_mapping_completeness.py --languages python --debug
"""

import argparse
import logging
import sys
from typing import Any


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def import_language_mappings(language: str) -> Any:
    """Import type mapping module for a language.

    Args:
        language: Language name (python, typescript, etc.)

    Returns:
        The imported type mappings module

    Raises:
        ImportError: If the language package is not installed
    """
    logger = logging.getLogger(__name__)

    if language == "python":
        try:
            from datrix_codegen_python import type_mappings

            logger.debug("Imported Python type mappings")
            return type_mappings
        except ImportError as e:
            raise ImportError(
                f"Failed to import Python type mappings. "
                f"Is datrix-codegen-python installed? Error: {e}"
            ) from e

    elif language == "typescript":
        try:
            from datrix_codegen_typescript import type_mappings

            logger.debug("Imported TypeScript type mappings")
            return type_mappings
        except ImportError as e:
            raise ImportError(
                f"Failed to import TypeScript type mappings. "
                f"Is datrix-codegen-typescript installed? Error: {e}"
            ) from e

    else:
        raise ValueError(
            f"Unknown language: {language}. " f"Supported languages: python, typescript"
        )


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
        required=True,
        help="Comma-separated list of languages (e.g., python,typescript)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    configure_logging(debug=args.debug)

    # Parse language list
    languages = [lang.strip().lower() for lang in args.languages.split(",")]
    if not languages:
        logging.error("No languages specified")
        return 2

    return validate_completeness(languages)


if __name__ == "__main__":
    sys.exit(main())
