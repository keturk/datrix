#!/usr/bin/env python3
"""GenDSL corpus reference-resolution gate (design 025 D1/I1, task 13-04).

Eager builder/call-expression reference resolution runs at
``@generator_definition`` registration time
(``datrix_codegen_common.gendsl.resolver``). This is the cross-package proof
that the real, shipped corpus of builder/call/context/appends references
across every consumer package is genuinely resolvable: importing each
package's genDSL definitions module IS the assertion. If any reference in
any package failed to resolve, the import itself raises
``GenDSLReferenceResolutionError``.

This check previously lived as a pytest test
(``datrix-codegen-common/tests/integration/gendsl/test_resolution_corpus.py``)
that imported all seven concrete target packages directly from
``datrix-codegen-common``'s own test suite -- a cross-package import boundary
violation (``datrix_codegen_common`` must not import concrete target
packages) and a cross-package test (prohibited everywhere in the repo, not
just in the showcase package). The proof is inherently repo-level -- it
spans every generator package -- so it belongs as a script under
``datrix/scripts/test/``, the same home as the other repo-level corpus gates
(``reference-example-parity-gate.ps1``, ``type-mapping-completeness.ps1``),
not inside any single package's own test suite.

Usage:
    python gendsl_corpus_resolution.py
    python gendsl_corpus_resolution.py --debug
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys

#: Every consumer package's genDSL definitions module. Importing each module
#: triggers eager reference resolution for its full corpus of builder/call/
#: context/appends references.
GENDSL_DEFINITION_MODULES: tuple[str, ...] = (
    "datrix_codegen_python.gendsl.definitions",
    "datrix_codegen_typescript.gendsl_definitions",
    "datrix_codegen_sql.gendsl.sql_definitions",
    "datrix_codegen_docker.gendsl_definitions",
    "datrix_codegen_aws.gendsl.aws_definitions",
    "datrix_codegen_azure.gendsl.azure_definitions",
    "datrix_codegen_component.gendsl_definitions",
)


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def check_corpus_resolution(modules: tuple[str, ...]) -> int:
    """Import every genDSL definitions module and report resolution failures.

    Args:
        modules: Fully qualified module names to import.

    Returns:
        Exit code (0 = every module's corpus resolved, 1 = at least one
        module failed to resolve or import).
    """
    logger = logging.getLogger(__name__)

    # Import lazily so a missing GenDSLReferenceResolutionError type (an
    # unexpected packaging problem, distinct from a corpus resolution
    # failure) fails loud with its own traceback rather than being folded
    # into the per-module except clause below.
    from datrix_codegen_common.gendsl.resolver import GenDSLReferenceResolutionError

    failures: dict[str, str] = {}
    for module_name in modules:
        logger.info("Resolving genDSL corpus: %s", module_name)
        try:
            importlib.import_module(module_name)
        except GenDSLReferenceResolutionError as exc:
            failures[module_name] = str(exc)
            logger.error("%s: unresolved reference(s): %s", module_name, exc)
        except ImportError as exc:
            failures[module_name] = str(exc)
            logger.error(
                "%s: import failed (is the package installed in the shared "
                "venv?): %s",
                module_name,
                exc,
            )

    if failures:
        logger.error(
            "GenDSL corpus resolution failed for %d of %d package(s)",
            len(failures),
            len(modules),
        )
        return 1

    logger.info(
        "GenDSL corpus resolution passed for all %d package(s)", len(modules)
    )
    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = corpus resolved for every package, 1 = failure).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every consumer package's genDSL builder/call/context/"
            "appends reference corpus resolves at import time."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    return check_corpus_resolution(GENDSL_DEFINITION_MODULES)


if __name__ == "__main__":
    sys.exit(main())
