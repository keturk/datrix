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

**Each module is imported in its own dedicated subprocess -- never in this
process.** All seven packages register their genDSL definitions into the
SAME global ``@generator_definition`` registry within whichever process
imports them. If two packages' modules were both imported into this one
process (as a single ``importlib.import_module`` loop would do), a reference
in package B that would fail to resolve on its own could be silently
satisfied by a registration that package A's earlier import happened to
make -- reintroducing, inside this script, the exact cross-package coupling
the pytest test was removed for. Running each package's import in its own
subprocess guarantees no single process ever holds more than one generator
package's genDSL modules loaded at once, so each package's corpus is proven
to resolve entirely on its own.

Usage:
    python gendsl_corpus_resolution.py
    python gendsl_corpus_resolution.py --debug
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass

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

#: Generous ceiling for a single package's genDSL-definitions import. Eager
#: reference resolution walks one package's compiled IR tree in memory; a
#: real run finishes in well under a second per package, so this only exists
#: to fail loud (instead of hanging the gate forever) if a subprocess never
#: returns.
SUBPROCESS_TIMEOUT_SECONDS: int = 120


@dataclass(frozen=True)
class ModuleResolutionResult:
    """Outcome of importing one genDSL definitions module in isolation."""

    module_name: str
    succeeded: bool
    error_output: str


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def resolve_module_in_subprocess(
    python_executable: str, module_name: str
) -> ModuleResolutionResult:
    """Import *module_name* in its own dedicated subprocess.

    Runs ``python -c "import <module_name>"`` as a fresh child process so
    that this module's process never holds more than one generator
    package's genDSL modules loaded at once. Eager reference resolution
    (``datrix_codegen_common.gendsl.resolver``) runs as a side effect of the
    import; any unresolved reference raises
    ``GenDSLReferenceResolutionError`` inside the child process, which
    prints its traceback to stderr and exits non-zero -- the child's
    combined stdout/stderr is returned verbatim for the caller to surface.

    Args:
        python_executable: Path to the Python interpreter to run the import
            under (the shared venv interpreter, so the target package is
            importable).
        module_name: Fully qualified genDSL definitions module to import.

    Returns:
        The resolution result: whether the import succeeded, and (on
        failure) the child process's verbatim combined output.
    """
    try:
        completed = subprocess.run(
            [python_executable, "-c", f"import {module_name}"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_output = (
            f"Subprocess importing {module_name} did not finish within "
            f"{SUBPROCESS_TIMEOUT_SECONDS}s: {exc}"
        )
        return ModuleResolutionResult(module_name, False, timeout_output)

    if completed.returncode == 0:
        return ModuleResolutionResult(module_name, True, "")

    combined_output = (completed.stdout + completed.stderr).strip()
    return ModuleResolutionResult(module_name, False, combined_output)


def check_corpus_resolution(python_executable: str, modules: tuple[str, ...]) -> int:
    """Import every genDSL definitions module in isolation and report failures.

    Args:
        python_executable: Path to the Python interpreter each per-package
            subprocess is run under.
        modules: Fully qualified module names to import, one subprocess per
            module.

    Returns:
        Exit code (0 = every module's corpus resolved, 1 = at least one
        module failed to resolve or import).
    """
    logger = logging.getLogger(__name__)

    failures: dict[str, str] = {}
    for module_name in modules:
        logger.info(
            "Resolving genDSL corpus (isolated subprocess): %s", module_name
        )
        result = resolve_module_in_subprocess(python_executable, module_name)
        if not result.succeeded:
            failures[module_name] = result.error_output
            logger.error(
                "%s: subprocess import failed:\n%s",
                module_name,
                result.error_output,
            )

    if failures:
        logger.error(
            "GenDSL corpus resolution failed for %d of %d package(s): %s",
            len(failures),
            len(modules),
            ", ".join(sorted(failures)),
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
            "appends reference corpus resolves at import time, one "
            "subprocess per package so no single process ever holds more "
            "than one generator package's genDSL modules loaded at once."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    return check_corpus_resolution(sys.executable, GENDSL_DEFINITION_MODULES)


if __name__ == "__main__":
    sys.exit(main())
