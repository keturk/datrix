#!/usr/bin/env python3
"""DAL generator corpus reference-resolution gate.

Eager builder/call-expression reference resolution runs when a target's
``.dal`` resource compiles (``generator_definition_file``,
``datrix_codegen_kernel.dgen.resolver``). This is the cross-package proof
that the real, shipped corpus of builder/call/context/appends references
across every consumer package is genuinely resolvable: compiling each
target's DAL generator definitions through ``target_definitions(<target>)``
IS the assertion. If any reference in any package fails to resolve, the
compile raises ``DalReferenceError``.

The proof is inherently repo-level -- it spans every generator package, which
``datrix_codegen_common`` may not import and which no package's own test
suite may span (a cross-package test is prohibited everywhere) -- so it
belongs as a script under ``datrix/scripts/gates/``, the same home as the
other repo-level corpus gates (``artifact-role-parity-gate.ps1``,
``type-mapping-completeness.ps1``).

**Each target compiles in its own dedicated subprocess -- never in this
process.** Reference resolution imports every module a reference names. If two
targets compiled in one process, a reference in target B whose module only
imports because target A's compile loaded a dependency first would pass here
and fail in a real run that generates B alone. Compiling each target in a
fresh child guarantees its corpus is proven to resolve entirely on its own.
The target set itself is derived from ``datrix.dgen_generator_targets`` +
``datrix.platforms`` entry-point discovery (see
:func:`discover_dgen_definition_targets`), never a hardcoded package count or
list.

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

#: Generous ceiling for compiling a single target's DAL generator definitions.
#: Eager reference resolution walks one target's compiled IR tree in memory; a
#: real run finishes in well under a second per target, so this only exists to
#: fail loud (instead of hanging the gate forever) if a subprocess never
#: returns.
SUBPROCESS_TIMEOUT_SECONDS: int = 120

#: The child program compiling one registered target's definitions through the
#: one by-name resolution every tool shares.
TARGET_COMPILE_PROGRAM = (
    "import sys\n"
    "from datrix_codegen_kernel.dgen.compiler import target_definitions\n"
    "target_definitions(sys.argv[1])\n"
)

#: The child program compiling a planted definitions module's
#: ``generator_definitions()`` (the self-test's packages are not registered
#: targets, so they are reached by module name).
MODULE_COMPILE_PROGRAM = (
    "import importlib, sys\n"
    "from datrix_codegen_kernel.dgen.compiler import DEFINITIONS_FUNCTION\n"
    "getattr(importlib.import_module(sys.argv[1]), DEFINITIONS_FUNCTION)()\n"
)

#: The self-test plants definitions for this registered target, whose DAL
#: namespace resolves to its own dgen package; the resolved twin names a builder
#: that namespace really carries, the other a builder it does not.
SELF_TEST_TARGET = "sql"
SELF_TEST_NAMESPACE = "sql.ddl"
SELF_TEST_RESOLVED_BUILDER = "build_entity_ddl"
SELF_TEST_MISSING_BUILDER = "dgen_corpus_selftest_missing_builder"


@dataclass(frozen=True)
class CompileResult:
    """Outcome of compiling one target's (or planted module's) definitions in isolation."""

    subject: str
    succeeded: bool
    error_output: str


def discover_dgen_definition_targets() -> tuple[str, ...]:
    """Derive every discovered dgen target that declares definition modules.

    EVERY target -- language, platform, artifact or component alike --
    contributes its own ``DgenTargetContribution.definition_modules``, resolved
    uniformly through ``target_registry.definition_modules_for()``. A target
    that declares no DAL generator definition module of its own (as ``local``
    does -- its artifacts are declared by the docker package that owns it) has
    no corpus to compile and is not swept; a future ``datrix-codegen-<x>`` is
    swept with no edit to this gate.

    Calling ``target_registry.target_kind_map()``/``definition_modules_for()``
    here, in this script's own single process, is safe: both only import the
    dependency-light registration modules and compile nothing -- the
    one-subprocess-per-target isolation this gate enforces applies to the
    compile, not to this discovery step.

    Returns:
        The sorted tuple of every discovered target declaring at least one
        definitions module.

    Raises:
        PluginError: Propagated from target_registry discovery/loading
            failures -- a bad entry-point registration must fail this
            gate loud, never silently shrink the corpus it proves.
    """
    return tuple(
        sorted(target for target in target_registry.target_kind_map() if target_registry.definition_modules_for(target))
    )


def compile_in_subprocess(
    python_executable: str, program: str, subject: str, cwd: Path | None = None
) -> CompileResult:
    """Run *program* with *subject* as its argument in its own dedicated subprocess.

    Eager reference resolution (``datrix_codegen_kernel.dgen.resolver``) runs
    inside the child's compile; any unresolved reference raises
    ``DalReferenceError`` there, which prints its traceback to stderr and exits
    non-zero -- the child's combined stdout/stderr is returned verbatim for the
    caller to surface.

    Args:
        python_executable: Path to the Python interpreter to run the compile
            under (the shared venv interpreter, so the target package is
            importable).
        program: The child program (:data:`TARGET_COMPILE_PROGRAM` or
            :data:`MODULE_COMPILE_PROGRAM`).
        subject: The target name or module name the program compiles.
        cwd: The child's working directory, which ``-c`` puts first on its
            ``sys.path`` (the self-test's planted packages live there); the
            inherited one when omitted.

    Returns:
        The compile result: whether it succeeded, and (on failure) the child
        process's verbatim combined output.
    """
    try:
        completed = subprocess.run(
            [python_executable, "-c", program, subject],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_output = f"Subprocess compiling {subject} did not finish within {SUBPROCESS_TIMEOUT_SECONDS}s: {exc}"
        return CompileResult(subject, False, timeout_output)

    if completed.returncode == 0:
        return CompileResult(subject, True, "")

    combined_output = (completed.stdout + completed.stderr).strip()
    return CompileResult(subject, False, combined_output)


def check_corpus_resolution(
    python_executable: str, program: str, subjects: tuple[str, ...], cwd: Path | None = None
) -> int:
    """Compile every subject's definitions in isolation and report failures.

    Args:
        python_executable: Path to the Python interpreter each subprocess is
            run under.
        program: The child program each subject is compiled with.
        subjects: Target names (or planted module names), one subprocess each.
        cwd: Each child's working directory (see :func:`compile_in_subprocess`).

    Returns:
        Exit code (0 = every subject's corpus resolved, 1 = at least one
        failed to compile).
    """
    logger = logging.getLogger(__name__)

    failures: dict[str, str] = {}
    for subject in subjects:
        logger.info("Resolving DAL generator corpus (isolated subprocess): %s", subject)
        result = compile_in_subprocess(python_executable, program, subject, cwd)
        if not result.succeeded:
            failures[subject] = result.error_output
            logger.error("%s: subprocess compile failed:\n%s", subject, result.error_output)

    if failures:
        logger.error(
            "DAL generator corpus resolution failed for %d of %d target(s): %s",
            len(failures),
            len(subjects),
            ", ".join(sorted(failures)),
        )
        return 1

    logger.info("DAL generator corpus resolution passed for all %d target(s)", len(subjects))
    return 0


def _plant_definitions_package(root: Path, package: str, builder_function: str) -> str:
    """Write a definitions package under *root* whose one builder names *builder_function*.

    The package's ``generator_definitions()`` compiles a ``.dal`` resource
    through the real ``generator_definition_file``, so calling it runs the
    shipped eager reference resolution exactly as a target's own definitions
    module does.

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
        "from datrix_codegen_kernel.dgen.compiler import generator_definition_file\n\n\n"
        "def generator_definitions():\n"
        f'    return (generator_definition_file("{SELF_TEST_TARGET}", __package__, "generator.dal"),)\n',
        encoding="utf-8",
    )
    return f"{package}.definitions"


def _check_planted_corpus() -> None:
    with tempfile.TemporaryDirectory(prefix="dgen-corpus-selftest-") as tmp:
        root = Path(tmp)
        resolved = _plant_definitions_package(root, "dgen_selftest_resolved", SELF_TEST_RESOLVED_BUILDER)
        unresolved = _plant_definitions_package(root, "dgen_selftest_unresolved", SELF_TEST_MISSING_BUILDER)
        resolved_result = compile_in_subprocess(sys.executable, MODULE_COMPILE_PROGRAM, resolved, root)
        if not resolved_result.succeeded:
            raise AssertionError(
                f"the planted corpus naming {SELF_TEST_NAMESPACE}.{SELF_TEST_RESOLVED_BUILDER} "
                f"failed to resolve:\n{resolved_result.error_output}"
            )
        unresolved_result = compile_in_subprocess(sys.executable, MODULE_COMPILE_PROGRAM, unresolved, root)
        if unresolved_result.succeeded or "DalReferenceError" not in unresolved_result.error_output:
            raise AssertionError(
                f"the planted corpus naming {SELF_TEST_NAMESPACE}.{SELF_TEST_MISSING_BUILDER} was "
                f"not reported as an unresolved reference (succeeded={unresolved_result.succeeded}):\n"
                f"{unresolved_result.error_output}"
            )
        if check_corpus_resolution(sys.executable, MODULE_COMPILE_PROGRAM, (resolved, unresolved), root) != 1:
            raise AssertionError("a corpus holding one unresolved module did not fail the gate")


def _check_target_compile_reaches_the_corpus() -> None:
    """The gate's real child program compiles the self-test target's shipped corpus, and refuses an unknown one."""
    if SELF_TEST_TARGET not in discover_dgen_definition_targets():
        raise AssertionError(f"target {SELF_TEST_TARGET!r} declares no definitions module; the sweep is vacuous")
    shipped = compile_in_subprocess(sys.executable, TARGET_COMPILE_PROGRAM, SELF_TEST_TARGET)
    if not shipped.succeeded:
        raise AssertionError(f"compiling target {SELF_TEST_TARGET!r} failed:\n{shipped.error_output}")
    unknown = compile_in_subprocess(sys.executable, TARGET_COMPILE_PROGRAM, "dgen_corpus_selftest_unknown_target")
    if unknown.succeeded:
        raise AssertionError("compiling an unregistered target succeeded; the child program resolves nothing")


def self_test_checks() -> list[NamedCheck]:
    """The gate's non-vacuity checks."""
    return [
        NamedCheck("planted_unresolved_reference_is_reported_and_its_twin_passes", _check_planted_corpus),
        NamedCheck("target_compile_reaches_the_shipped_corpus", _check_target_compile_reaches_the_corpus),
    ]


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = corpus resolved for every target, 1 = failure).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every discovered dgen target's builder/call/context/"
            "appends reference corpus resolves when it compiles, one "
            "subprocess per target so each corpus resolves on its own. "
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
        "reported, its resolved twin passes, and the real per-target compile reaches a shipped corpus.",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    if args.self_test:
        return EXIT_PASS if run_checks(self_test_checks()) else EXIT_USAGE

    targets = discover_dgen_definition_targets()
    logging.getLogger(__name__).info(
        "Discovered %d DAL generator target(s) declaring definition modules: %s", len(targets), targets
    )
    return check_corpus_resolution(sys.executable, TARGET_COMPILE_PROGRAM, targets)


if __name__ == "__main__":
    sys.exit(main())
