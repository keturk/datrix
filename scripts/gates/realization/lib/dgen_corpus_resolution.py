#!/usr/bin/env python3
"""DAL generator corpus reference-resolution gate.

Eager builder/call-expression reference resolution runs when each target's
``.dal`` resource is registered (``generator_definition_file``,
``datrix_codegen_kernel.dgen.resolver``). This is the cross-package proof
that the real, shipped corpus of builder/call/context/appends references
across every consumer package is genuinely resolvable: importing each
package's DAL generator definitions module IS the assertion. If any reference in
any package failed to resolve, the import itself raises
``DalReferenceError``.

This check previously lived as a pytest test
(``datrix-codegen-common/tests/integration/dgen/test_resolution_corpus.py``)
that imported all seven concrete target packages directly from
``datrix-codegen-common``'s own test suite -- a cross-package import boundary
violation (``datrix_codegen_common`` must not import concrete target
packages) and a cross-package test (prohibited everywhere in the repo, not
just in the showcase package). The proof is inherently repo-level -- it
spans every generator package -- so it belongs as a script under
``datrix/scripts/gates/``, the same home as the other repo-level corpus gates
(``artifact-role-parity-gate.ps1``, ``type-mapping-completeness.ps1``),
not inside any single package's own test suite.

**Each module is imported in its own dedicated subprocess -- never in this
process.** Every discovered target registers its DAL generator definitions into
the SAME global DAL generator definition registry within whichever process
imports them. If two targets' modules were both imported into this one
process (as a single ``importlib.import_module`` loop would do), a reference
in target B that would fail to resolve on its own could be silently
satisfied by a registration that target A's earlier import happened to
make -- reintroducing, inside this script, the exact cross-package coupling
the pytest test was removed for. Running each target's import in its own
subprocess guarantees no single process ever holds more than one generator
package's DAL generator modules loaded at once, so each target's corpus is proven
to resolve entirely on its own. The target set itself is derived from
``datrix.dgen_generator_targets`` + ``datrix.platforms`` entry-point
discovery (see :func:`discover_dgen_definition_modules`), never a
hardcoded package count or list.

Usage:
    python dgen_corpus_resolution.py
    python dgen_corpus_resolution.py --debug
    python dgen_corpus_resolution.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from datrix_codegen_kernel.dgen import target_registry
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, NamedCheck, configure_logging, run_checks

#: Generous ceiling for a single package's DAL generator-definitions import. Eager
#: reference resolution walks one package's compiled IR tree in memory; a
#: real run finishes in well under a second per package, so this only exists
#: to fail loud (instead of hanging the gate forever) if a subprocess never
#: returns.
SUBPROCESS_TIMEOUT_SECONDS: int = 120

#: The self-test plants definitions for this registered target, whose DAL
#: namespace resolves to its own dgen package; the resolved twin names a builder
#: that namespace really carries, the other a builder it does not.
SELF_TEST_TARGET = "sql"
SELF_TEST_NAMESPACE = "sql.ddl"
SELF_TEST_RESOLVED_BUILDER = "build_entity_ddl"
SELF_TEST_MISSING_BUILDER = "dgen_corpus_selftest_missing_builder"


@dataclass(frozen=True)
class ModuleResolutionResult:
    """Outcome of importing one DAL generator definitions module in isolation."""

    module_name: str
    succeeded: bool
    error_output: str


def discover_dgen_definition_modules() -> tuple[str, ...]:
    """Derive every discovered dgen target's definition modules.

    Replaces the former 7-entry hand-authored tuple. EVERY target --
    language, platform, artifact or component alike -- contributes its own
    `DgenTargetContribution.definition_modules`, resolved uniformly
    through `target_registry.definition_modules_for()`. There is no
    separate platform path: the transitional platform-definition-module map
    that once carried aws/azure/docker has been retired, and platform
    definition modules are now a first-class `DgenTargetContribution`
    fact like any other target's.

    Consequence: the target set is never a literal here. A target that
    declares no DAL generator definition modules of its own correctly resolves to
    an empty tuple (as `local` does -- its artifacts are declared by the
    docker package that owns it), and a future `datrix-codegen-<x>` is
    swept with no edit to this gate.

    Calling `target_registry.target_kind_map()`/`definition_modules_for()`
    here, in this script's own single process, is safe: both only ever
    import the dependency-light `*_dgen_registration`-shaped modules
    (never the heavier `dgen.definitions` modules whose import registers
    the `.dal` resource as a side effect) -- the
    one-subprocess-per-package isolation this gate enforces below applies
    to THOSE modules, not to this discovery step.

    Returns:
        The sorted, deduplicated tuple of every discovered target's
        definition-module dotted paths.

    Raises:
        PluginError: Propagated from target_registry discovery/loading
            failures -- a bad entry-point registration must fail this
            gate loud, never silently shrink the corpus it proves.
    """
    modules: set[str] = set()
    for target in target_registry.target_kind_map():
        modules.update(target_registry.definition_modules_for(target))
    return tuple(sorted(modules))


def resolve_module_in_subprocess(
    python_executable: str, module_name: str, cwd: Path | None = None
) -> ModuleResolutionResult:
    """Import *module_name* in its own dedicated subprocess.

    Runs ``python -c "import <module_name>"`` as a fresh child process so
    that this module's process never holds more than one generator
    package's DAL generator modules loaded at once. Eager reference resolution
    (``datrix_codegen_kernel.dgen.resolver``) runs as a side effect of the
    import; any unresolved reference raises
    ``DalReferenceError`` inside the child process, which
    prints its traceback to stderr and exits non-zero -- the child's
    combined stdout/stderr is returned verbatim for the caller to surface.

    Args:
        python_executable: Path to the Python interpreter to run the import
            under (the shared venv interpreter, so the target package is
            importable).
        module_name: Fully qualified DAL generator definitions module to import.
        cwd: The child's working directory, which ``-c`` puts first on its
            ``sys.path`` (the self-test's planted packages live there); the
            inherited one when omitted.

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
            cwd=cwd,
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


def check_corpus_resolution(
    python_executable: str, modules: tuple[str, ...], cwd: Path | None = None
) -> int:
    """Import every DAL generator definitions module in isolation and report failures.

    Args:
        python_executable: Path to the Python interpreter each per-package
            subprocess is run under.
        modules: Fully qualified module names to import, one subprocess per
            module.
        cwd: Each child's working directory (see :func:`resolve_module_in_subprocess`).

    Returns:
        Exit code (0 = every module's corpus resolved, 1 = at least one
        module failed to resolve or import).
    """
    logger = logging.getLogger(__name__)

    failures: dict[str, str] = {}
    for module_name in modules:
        logger.info(
            "Resolving DAL generator corpus (isolated subprocess): %s", module_name
        )
        result = resolve_module_in_subprocess(python_executable, module_name, cwd)
        if not result.succeeded:
            failures[module_name] = result.error_output
            logger.error(
                "%s: subprocess import failed:\n%s",
                module_name,
                result.error_output,
            )

    if failures:
        logger.error(
            "DAL generator corpus resolution failed for %d of %d package(s): %s",
            len(failures),
            len(modules),
            ", ".join(sorted(failures)),
        )
        return 1

    logger.info(
        "DAL generator corpus resolution passed for all %d package(s)", len(modules)
    )
    return 0


def _plant_definitions_package(root: Path, package: str, builder_function: str) -> str:
    """Write a definitions package under *root* whose one builder names *builder_function*.

    The package registers a ``.dal`` resource through the real
    ``generator_definition_file``, so importing it runs the shipped eager
    reference resolution exactly as a target's own definitions module does.

    Returns:
        The dotted name of the planted definitions module.
    """
    package_dir = root / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "generator.dal").write_text(
        f"generator {package} : {SELF_TEST_TARGET} {{\n"
        "  consumes application;\n"
        "  domain entity_ddl {\n"
        "    each service {\n"
        "      each rdbms_block {\n"
        "        each entity where concrete {\n"
        "          sql entity_table {\n"
        f'            builder {SELF_TEST_NAMESPACE}.{builder_function} => "{{service.dir}}/x.sql";\n'
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (package_dir / "definitions.py").write_text(
        "from datrix_codegen_kernel.dgen.compiler import generator_definition_file\n\n"
        f'generator_definition_file("{SELF_TEST_TARGET}", __package__, "generator.dal")\n',
        encoding="utf-8",
    )
    return f"{package}.definitions"


def _check_planted_corpus() -> None:
    with tempfile.TemporaryDirectory(prefix="dgen-corpus-selftest-") as tmp:
        root = Path(tmp)
        resolved = _plant_definitions_package(root, "dgen_selftest_resolved", SELF_TEST_RESOLVED_BUILDER)
        unresolved = _plant_definitions_package(root, "dgen_selftest_unresolved", SELF_TEST_MISSING_BUILDER)
        resolved_result = resolve_module_in_subprocess(sys.executable, resolved, root)
        if not resolved_result.succeeded:
            raise AssertionError(
                f"the planted corpus naming {SELF_TEST_NAMESPACE}.{SELF_TEST_RESOLVED_BUILDER} "
                f"failed to resolve:\n{resolved_result.error_output}"
            )
        unresolved_result = resolve_module_in_subprocess(sys.executable, unresolved, root)
        if unresolved_result.succeeded or "DalReferenceError" not in unresolved_result.error_output:
            raise AssertionError(
                f"the planted corpus naming {SELF_TEST_NAMESPACE}.{SELF_TEST_MISSING_BUILDER} was "
                f"not reported as an unresolved reference (succeeded={unresolved_result.succeeded}):\n"
                f"{unresolved_result.error_output}"
            )
        if check_corpus_resolution(sys.executable, (resolved, unresolved), root) != 1:
            raise AssertionError("a corpus holding one unresolved module did not fail the gate")


def self_test_checks() -> list[NamedCheck]:
    """The gate's non-vacuity checks."""
    return [NamedCheck("planted_unresolved_reference_is_reported_and_its_twin_passes", _check_planted_corpus)]


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = corpus resolved for every package, 1 = failure).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every discovered dgen target's builder/call/context/"
            "appends reference corpus resolves at import time, one "
            "subprocess per target so no single process ever holds more "
            "than one generator package's DAL generator modules loaded at once. "
            "The target set is derived from datrix.dgen_generator_targets "
            "+ datrix.platforms entry-point discovery -- never hardcoded."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: a planted corpus with one unresolved reference is "
        "reported, and its resolved twin passes.",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    if args.self_test:
        return EXIT_PASS if run_checks(self_test_checks()) else EXIT_USAGE

    modules = discover_dgen_definition_modules()
    logging.getLogger(__name__).info(
        "Discovered %d DAL generator definition module(s) across every registered "
        "target: %s", len(modules), modules,
    )
    return check_corpus_resolution(sys.executable, modules)


if __name__ == "__main__":
    sys.exit(main())
