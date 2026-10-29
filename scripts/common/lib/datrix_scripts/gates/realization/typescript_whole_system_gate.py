"""Whole-system TypeScript generation gate: the module behind ``gates/realization/typescript-whole-system-gate.ps1``.

The whole-system generate path was once hollow for TypeScript: the pipeline never attached the codegen context to
the language generator (Python received one only by a bootstrap side effect), so the TypeScript generator raised
before writing anything. This gate proves a real end-to-end TypeScript whole-system run:

1. A language-neutral example is generated twice with ``--language=typescript`` into ``<output root>/run1`` and
   ``run2`` through the single-project generation. The target language comes solely from that flag: no example
   pins a language, and a ``language`` key in a system ``.dcfg`` is refused when it loads.
2. REALNESS: run 1 holds generated ``*.ts`` files, and no ``*.py`` file is the service implementation.
3. BYTE-STABILITY: run 1 and run 2 hold the same files with the same bytes.

A blanket "no ``*.py``" would fail correct output: every target language's project carries the
language-agnostic HTTP-contract integration tests under ``tests/`` (black-box tests against the running
service). Any ``*.py`` under a ``src`` segment, or outside ``tests/``, is a language leak.

Post-generation build and install artifacts (``.datrix``, ``.ruff_cache``, ``.tsc_cache``, ``node_modules``) embed
absolute paths or install state, and are excluded from both checks.

Exit codes: 0 = real and byte-stable output (or the self-test passed); 1 = a generation failed, a check failed, the
example is missing, or a self-test check failed; 2 = usage error.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, NamedCheck, write_files
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.realization.generating_gates import (
    TEST_OUTPUT_DIR,
    GeneratedFile,
    GeneratedTreeError,
    check_generation_command_is_an_argument_vector,
    check_walk_skips_excluded_directories_and_links,
    example_source,
    gate_parser,
    gate_self_test,
    generated_files,
    output_root,
    run_dir,
    run_generation,
)

GATE: Final = "typescript-whole-system"
MODULE: Final = "datrix_scripts.gates.realization.typescript_whole_system_gate"
WRAPPER: Final = "typescript-whole-system-gate"

#: The language this gate proves; the gate exists for its whole-system path.
LANGUAGE: Final = "typescript"
#: Language-neutral, and the one example known to generate cleanly in every registered language.
EXAMPLE: Final = "01-foundation"
DEFAULT_OUTPUT_FOLDER: Final = "ts-gate"
RUN_COUNT: Final = 2
#: Post-generation build and install artifacts, never deterministic generated source.
EXCLUDED_DIR_NAMES: Final = (".datrix", ".ruff_cache", ".tsc_cache", "node_modules")
#: Where every target language's project carries Python by design.
LANGUAGE_AGNOSTIC_PYTHON_DIRS: Final = ("tests",)
SOURCE_SEGMENT: Final = "src"
TYPESCRIPT_SUFFIX: Final = ".ts"
PYTHON_SUFFIX: Final = ".py"
#: Byte differences listed before the rest are summarized.
BYTE_DIFF_LIST_LIMIT: Final = 40
REALNESS: Final = "REALNESS"
BYTE_STABILITY: Final = "BYTE-STABILITY"


@dataclass(frozen=True)
class GenerationVerdict:
    """The classifier's failures over a run pair, and the summary counts."""

    failures: list[str]
    ts_count: int
    py_count: int
    compared_count: int
    byte_diff_count: int


def path_segments(rel_path: str) -> list[str]:
    """The non-empty ``/``-separated parts of *rel_path*."""
    return [part for part in rel_path.split("/") if part]


def language_leaks(py_files: Sequence[GeneratedFile]) -> list[str]:
    """The ``*.py`` files that are a language leak: under a ``src`` segment, or outside every allowed directory."""
    leaked: list[str] = []
    for item in py_files:
        segments = path_segments(item.rel_key)
        allowed = any(segment in LANGUAGE_AGNOSTIC_PYTHON_DIRS for segment in segments)
        if SOURCE_SEGMENT in segments or not allowed:
            leaked.append(item.rel_path)
    return leaked


def byte_differences(run1_files: Sequence[GeneratedFile], run2_files: Sequence[GeneratedFile]) -> list[str]:
    """Each file only one run has, and each file whose bytes differ, by comparison key."""
    run1 = {item.rel_key: item for item in run1_files}
    run2 = {item.rel_key: item for item in run2_files}
    differences: list[str] = []
    for key in sorted(run1):
        if key not in run2:
            differences.append(f"only in run1: {key}")
        elif run1[key].digest() != run2[key].digest():
            differences.append(f"content differs: {key}")
    differences.extend(f"only in run2: {key}" for key in sorted(run2) if key not in run1)
    return differences


def _realness_failures(ts_count: int, py_files: Sequence[GeneratedFile]) -> list[str]:
    failures: list[str] = []
    if ts_count <= 0:
        failures.append(
            f"{REALNESS}: expected generated *{TYPESCRIPT_SUFFIX} files > 0, found {ts_count} "
            "(hollow TypeScript output)."
        )
    leaked = language_leaks(py_files)
    if leaked:
        allowed = "/ + ".join(LANGUAGE_AGNOSTIC_PYTHON_DIRS)
        failures.append(
            f"{REALNESS}: {len(leaked)} Python file(s) leaked into the TypeScript service "
            f"(expected only {allowed}/): {', '.join(leaked)}"
        )
    return failures


def generation_verdict(run1: Path, run2: Path) -> GenerationVerdict:
    """Realness over *run1*, byte-stability of *run1* against *run2*."""
    excluded = frozenset(EXCLUDED_DIR_NAMES)
    run1_files = generated_files(run1, excluded)
    ts_count = sum(1 for item in run1_files if item.rel_key.endswith(TYPESCRIPT_SUFFIX))
    py_files = [item for item in run1_files if item.rel_key.endswith(PYTHON_SUFFIX)]
    failures = _realness_failures(ts_count, py_files)
    differences = byte_differences(run1_files, generated_files(run2, excluded))
    failures.extend(f"{BYTE_STABILITY}: {difference}" for difference in differences[:BYTE_DIFF_LIST_LIMIT])
    if len(differences) > BYTE_DIFF_LIST_LIMIT:
        failures.append(f"{BYTE_STABILITY}: ... and {len(differences) - BYTE_DIFF_LIST_LIMIT} more differences")
    return GenerationVerdict(failures, ts_count, len(py_files), len(run1_files), len(differences))


def _print_failures(header: str, failures: Sequence[str]) -> None:
    print(header)
    for failure in failures:
        print(f"  - {failure}")


def _print_summary(verdict: GenerationVerdict) -> None:
    print("=== Summary ===")
    print(f"Generated TypeScript source files (*.ts, excl. build artifacts): {verdict.ts_count}")
    print(f"Language-agnostic Python artifacts (tests/):                     {verdict.py_count}")
    print(f"Compared source files run1 vs run2:                              {verdict.compared_count}")
    print(f"Byte differences (excl. {'/'.join(EXCLUDED_DIR_NAMES)}): {verdict.byte_diff_count}")


def run_gate(root: Path, *, debug: bool) -> int:
    """Generate the example twice under *root* and judge realness and byte-stability."""
    source = example_source(EXAMPLE)
    if not source.is_file():
        print(f"Gate example not found at: {source}. Expected the {EXAMPLE} example. Fix: restore it.")
        return EXIT_VIOLATION
    runs = [run_dir(root, number) for number in range(1, RUN_COUNT + 1)]
    print("=== TypeScript whole-system gate ===")
    print(f"Example : {source}")
    for run in runs:
        print(f"{run.name}    : {run}")
    generation_failures: list[str] = []
    for run in runs:
        print(f"Generating {run.name}...", flush=True)
        exit_code = run_generation(source, run, LANGUAGE, debug=debug, quiet=False)
        if exit_code != 0:
            generation_failures.append(f"{run.name} generation exited with code {exit_code}")
    if generation_failures:
        _print_failures("GATE FAILED (generation did not complete):", generation_failures)
        return EXIT_VIOLATION
    verdict = generation_verdict(runs[0], runs[1])
    _print_summary(verdict)
    if verdict.failures:
        _print_failures("GATE FAILED:", verdict.failures)
        return EXIT_VIOLATION
    print("GATE PASSED: real TypeScript whole-system output, byte-stable across two runs.")
    return EXIT_PASS


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

#: Breaks a planted run pair (run1, run2).
Plant = Callable[[Path, Path], None]


def _planted_pair(root: Path) -> tuple[Path, Path]:
    """A clean run pair under *root*: identical source, allowed Python, a differing excluded directory."""
    run1, run2 = run_dir(root, 1), run_dir(root, 2)
    for run in (run1, run2):
        write_files(
            run,
            {
                "service/src/app.ts": "export const app = 1;",
                "service/tests/test_contract.py": "def test_contract(): ...",
                "service/node_modules/pkg/index.js": run.name,
            },
        )
    return run1, run2


def _no_change(run1: Path, run2: Path) -> None:
    del run1, run2  # The clean pair stays as planted.


def _python_under_src(run1: Path, run2: Path) -> None:
    for run in (run1, run2):
        write_files(run, {"service/src/handler.py": "x = 1"})


def _no_typescript(run1: Path, run2: Path) -> None:
    for run in (run1, run2):
        (run / "service" / "src" / "app.ts").unlink()


def _changed_byte(run1: Path, run2: Path) -> None:
    del run1  # Only run 2 changes.
    write_files(run2, {"service/src/app.ts": "export const app = 2;"})


def _file_in_one_run(run1: Path, run2: Path) -> None:
    del run1  # Only run 2 gains the file.
    write_files(run2, {"service/src/extra.ts": "export {};"})


def _verdict_case(name: str, plant: Plant, expected_prefix: str) -> NamedCheck:
    """Plant a pair, let *plant* break it, and expect exactly one failure starting *expected_prefix* ("" = none)."""

    def check() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run1, run2 = _planted_pair(Path(tmp))
            plant(run1, run2)
            failures = generation_verdict(run1, run2).failures
        if expected_prefix:
            assert len(failures) == 1 and failures[0].startswith(expected_prefix), failures
        else:
            assert failures == [], failures

    return NamedCheck(name, check)


_VERDICT_CASES: Final = (
    _verdict_case("clean_pair_passes", _no_change, ""),
    _verdict_case("python_under_src_is_a_leak", _python_under_src, f"{REALNESS}: 1 Python file(s) leaked"),
    _verdict_case("no_typescript_is_hollow", _no_typescript, f"{REALNESS}: expected generated *{TYPESCRIPT_SUFFIX}"),
    _verdict_case("changed_byte_is_unstable", _changed_byte, f"{BYTE_STABILITY}: content differs"),
    _verdict_case("file_in_one_run_is_unstable", _file_in_one_run, f"{BYTE_STABILITY}: only in run2"),
)


def _check_path_segments_drop_empty_parts() -> None:
    assert path_segments("service//src/app.ts") == ["service", "src", "app.ts"]


def _check_default_output_root() -> None:
    args = build_parser().parse_args([])
    assert output_root(args.output_root, TEST_OUTPUT_DIR / DEFAULT_OUTPUT_FOLDER) == (
        TEST_OUTPUT_DIR / DEFAULT_OUTPUT_FOLDER
    )


_SELF_TEST_CHECKS: Final = (
    *_VERDICT_CASES,
    _check_path_segments_drop_empty_parts,
    _check_default_output_root,
    check_walk_skips_excluded_directories_and_links,
    check_generation_command_is_an_argument_vector,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/realization/typescript-whole-system-gate.ps1``, each parameter spelled ``--kebab``."""
    return gate_parser(WRAPPER, "Generate one example twice for TypeScript; require real and byte-stable output.")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return gate_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser())
    try:
        return run_gate(output_root(args.output_root, TEST_OUTPUT_DIR / DEFAULT_OUTPUT_FOLDER), debug=args.debug)
    except (GeneratedTreeError, OSError) as error:
        print(f"GATE FAILED: {error}")
        return EXIT_VIOLATION


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
