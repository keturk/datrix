"""Generation-pipeline determinism gate: the module behind ``gates/realization/generation-determinism-gate.ps1``.

The SAME source tree, generated N times in a row for one registered language through the single-project
generation, must never produce two different outcomes. A corpus generation sweep once found the identical
command against an unchanged tree producing three different outcomes (once failing inside the language's own
``generate:<lang>`` stage, twice at the generated project's compile step with different errors): no conclusion
drawn from one generation is trustworthy until this class of regression is caught automatically.

Each run is its own generation process (a fresh interpreter), so this also exercises hash-seed-driven ordering
bugs a single long-lived process never surfaces: a ``set`` iterated without a deterministic sort orders
differently across processes but always the same within one. No before/after comparison of two code states
catches this class of bug, because it never runs the same code twice; this gate runs the same code N times.

1. The reference example is generated ``--runs`` times (default 5) for ``--language`` into
   ``<output root>/run1`` .. ``runN``.
2. Each run is SUCCESS (the generation exited 0) or FAILED, with a fingerprint:
   SUCCESS -- the SHA-256 of the per-relative-path SHA-256 manifest of the generated tree, ``.datrix`` excluded
   (its audit log, snapshot and manifest ``generated_at`` record when generation ran, not what it produced);
   FAILED -- the SHA-256 of the run's own generation log with its timestamp and log-path lines dropped and the
   run's output directory replaced by a placeholder, so two runs failing for one reason in different output
   directories fingerprint alike.
3. Every run must have run 1's classification and fingerprint; each that differs is reported by name.

A consistent, reproducible FAILURE is a passing outcome: the property is determinism, not the correctness of the
generated code.

Exit codes: 0 = all runs identical (or the self-test passed); 1 = a run differs, ``--runs`` is below 2, the
reference example is missing, a generated tree is missing, or a self-test check failed; 2 = usage error
(no ``--language`` without ``--self-test``).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.dev.generate import LOG_PREFIX, RESULTS_DIR
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, UsageError, expect_usage_error, write_files
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.realization.generating_gates import (
    TEST_OUTPUT_DIR,
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

GATE: Final = "generation-determinism"
MODULE: Final = "datrix_scripts.gates.realization.generation_determinism_gate"
WRAPPER: Final = "generation-determinism-gate"

DEFAULT_RUNS: Final = 5
MINIMUM_RUNS: Final = 2
#: The example this class of non-determinism was originally found against.
REFERENCE_EXAMPLE: Final = "02-features/03-infrastructure-blocks/nosql"
DEFAULT_OUTPUT_FOLDER: Final = "generation-determinism-gate"
#: The run's own metadata, expected to differ every run by design.
EXCLUDED_DIR_NAMES: Final = frozenset({".datrix"})
RESULTS_LOG_GLOB: Final = f"{LOG_PREFIX}-*.log"
#: Preamble lines of a generation log that carry the run's own time or path.
RUN_SPECIFIC_LOG_LINE: Final = re.compile(r"^(?:Timestamp:|Log file:|Log saved to:)", re.IGNORECASE)
OUTPUT_DIR_PLACEHOLDER: Final = "<OUTPUT_DIR>"
NO_LOG_FINGERPRINT: Final = "NO_LOG_FOUND"
MISSING_LOG_PREFIX: Final = "MISSING_LOG:"
_LINE_BREAK: Final = re.compile(r"\r?\n")
_SUCCESS: Final = "SUCCESS"
_FAILED: Final = "FAILED"


@dataclass(frozen=True)
class RunOutcome:
    """One run's classification, fingerprint and the line describing it."""

    run: int
    success: bool
    fingerprint: str
    detail: str = ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def success_manifest_hash(root: Path) -> str:
    """The SHA-256 of ``<relative key>:<file SHA-256>`` lines, in key order, for the tree at *root*."""
    files = sorted(generated_files(root, EXCLUDED_DIR_NAMES), key=lambda item: item.rel_key)
    return _sha256_text("\n".join(f"{item.rel_key}:{item.digest()}" for item in files))


def failure_fingerprint(log: Path, output_dir: Path) -> str:
    """The SHA-256 of *log* with its run-specific lines dropped and *output_dir* (either separator) replaced."""
    if not log.is_file():
        return f"{MISSING_LOG_PREFIX}{log}"
    text = log.read_text(encoding="utf-8", errors="replace")
    output = os.path.abspath(output_dir)
    text = text.replace(output, OUTPUT_DIR_PLACEHOLDER).replace(output.replace("\\", "/"), OUTPUT_DIR_PLACEHOLDER)
    kept = [line for line in _LINE_BREAK.split(text) if not RUN_SPECIFIC_LOG_LINE.match(line)]
    return _sha256_text("\n".join(kept))


def _classification(success: bool) -> str:
    return _SUCCESS if success else _FAILED


def determinism_failures(outcomes: Sequence[RunOutcome]) -> list[str]:
    """Every outcome whose classification or fingerprint differs from the first."""
    reference = outcomes[0]
    failures: list[str] = []
    for outcome in outcomes[1:]:
        if outcome.success != reference.success:
            failures.append(
                f"run{outcome.run} classification ({_classification(outcome.success)}) differs from run1 "
                f"({_classification(reference.success)})"
            )
        elif outcome.fingerprint != reference.fingerprint:
            failures.append(
                f"run{outcome.run} fingerprint ({outcome.fingerprint}) differs from run1 ({reference.fingerprint})"
            )
    return failures


def results_logs(results_dir: Path) -> frozenset[Path]:
    """The generation logs in *results_dir* now."""
    if not results_dir.is_dir():
        return frozenset()
    return frozenset(path for path in results_dir.glob(RESULTS_LOG_GLOB) if path.is_file())


def new_results_logs(before: frozenset[Path], after: frozenset[Path]) -> list[Path]:
    """The logs in *after* that *before* lacks, newest first: a run's own log leads."""
    return sorted(after - before, key=lambda path: path.stat().st_mtime, reverse=True)


@dataclass(frozen=True)
class DeterminismRequest:
    """What one gate run generates and compares."""

    language: str
    root: Path
    runs: int
    debug: bool


def request_from_args(args: argparse.Namespace) -> DeterminismRequest:
    """The request *args* name; a missing ``--language`` is a usage error."""
    if not args.language.strip():
        raise UsageError(
            "--language is required unless --self-test. Expected a registered datrix.languages name "
            "(e.g. --language=python). Fix: pass the language to generate for."
        )
    default_root = TEST_OUTPUT_DIR / DEFAULT_OUTPUT_FOLDER / args.language
    return DeterminismRequest(args.language, output_root(args.output_root, default_root), args.runs, args.debug)


def generate_outcome(request: DeterminismRequest, number: int, source: Path) -> RunOutcome:
    """Generate run *number* and classify it."""
    output = run_dir(request.root, number)
    print(f"Generating run{number}...", flush=True)
    before = results_logs(RESULTS_DIR)
    exit_code = run_generation(source, output, request.language, debug=request.debug, quiet=True)
    if exit_code == 0:
        manifest = success_manifest_hash(output)
        return RunOutcome(number, True, manifest, f"SUCCESS manifest sha256={manifest}")
    logs = new_results_logs(before, results_logs(RESULTS_DIR))
    if not logs:
        return RunOutcome(
            number, False, NO_LOG_FINGERPRINT,
            f"FAILED (exit {exit_code}) -- no new {RESULTS_LOG_GLOB} was found in {RESULTS_DIR}",
        )
    fingerprint = failure_fingerprint(logs[0], output)
    return RunOutcome(number, False, fingerprint, f"FAILED (exit {exit_code}) fingerprint={fingerprint} log={logs[0]}")


def run_gate(request: DeterminismRequest) -> int:
    """Generate the reference example ``request.runs`` times and compare the outcomes."""
    if request.runs < MINIMUM_RUNS:
        print(
            f"Runs must be >= {MINIMUM_RUNS} (need at least two outcomes to compare); got {request.runs}. "
            f"Fix: pass -Runs {MINIMUM_RUNS} or more."
        )
        return EXIT_VIOLATION
    source = example_source(REFERENCE_EXAMPLE)
    if not source.is_file():
        print(f"Reference example not found at: {source}. Fix: restore it.")
        return EXIT_VIOLATION
    print(f"=== Generation determinism gate: {request.language} ({request.runs} runs) ===")
    print(f"Example : {source}")
    outcomes: list[RunOutcome] = []
    for number in range(1, request.runs + 1):
        outcomes.append(generate_outcome(request, number, source))
        print(f"  run{number}: {outcomes[-1].detail}", flush=True)
    failures = determinism_failures(outcomes)
    if failures:
        print("GATE FAILED (non-deterministic generation detected):")
        for failure in failures:
            print(f"  - {failure}")
        return EXIT_VIOLATION
    kind = "byte-identical SUCCESS" if outcomes[0].success else "identical FAILURE"
    print(f"GATE PASSED: all {request.runs} runs produced {kind} (fingerprint {outcomes[0].fingerprint}).")
    return EXIT_PASS


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_AGREEING: Final = (RunOutcome(1, True, "f"), RunOutcome(2, True, "f"))


def _planted_trees(root: Path) -> None:
    for tree in ("a", "b", "c"):
        write_files(root / tree, {"src/app.py": "x = 1", ".datrix/manifest.json": f'{{"generated_at": "{tree}"}}'})
    write_files(root / "c", {"src/app.py": "x = 2"})


def _check_manifest_identical_trees_agree_despite_datrix_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _planted_trees(root)
        assert success_manifest_hash(root / "a") == success_manifest_hash(root / "b")


def _check_manifest_one_changed_byte_differs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _planted_trees(root)
        assert success_manifest_hash(root / "a") != success_manifest_hash(root / "c")


def _planted_logs(root: Path) -> tuple[Path, Path, Path, Path]:
    """Run directories a and b and three logs: a's and b's one failure, and b's other failure."""
    run_a, run_b = root / "run-a", root / "run-b"
    run_a.mkdir()
    run_b.mkdir()
    write_files(
        root,
        {
            "a.log": f"Timestamp: 1\nerror in {run_a / 'src' / 'app.ts'}: TS2304\n",
            "b.log": f"Timestamp: 2\nLog file: {root / 'b.log'}\nerror in {run_b / 'src' / 'app.ts'}: TS2304\n",
            "c.log": f"Timestamp: 3\nerror in {run_b / 'src' / 'app.ts'}: TS2551\n",
        },
    )
    return run_a, run_b, root / "a.log", root / "b.log"


def _check_fingerprint_same_failure_in_another_output_dir_agrees() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_a, run_b, log_a, log_b = _planted_logs(Path(tmp))
        assert failure_fingerprint(log_a, run_a) == failure_fingerprint(log_b, run_b)


def _check_fingerprint_different_error_differs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, run_b, _, log_b = _planted_logs(root)
        assert failure_fingerprint(log_b, run_b) != failure_fingerprint(root / "c.log", run_b)
        assert failure_fingerprint(root / "absent.log", run_b).startswith(MISSING_LOG_PREFIX)


def _check_comparison_agreeing_runs_pass() -> None:
    assert determinism_failures(_AGREEING) == []


def _check_comparison_changed_classification_fails() -> None:
    failures = determinism_failures((_AGREEING[0], RunOutcome(2, False, "f")))
    assert failures == ["run2 classification (FAILED) differs from run1 (SUCCESS)"], failures


def _check_comparison_changed_fingerprint_fails() -> None:
    failures = determinism_failures((_AGREEING[0], RunOutcome(2, True, "g")))
    assert failures == ["run2 fingerprint (g) differs from run1 (f)"], failures


def _check_a_run_reads_the_log_it_wrote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        results = Path(tmp)
        old = write_files(results, {f"{LOG_PREFIX}-20260101-000000-a.log": "old", "other.log": "x"})[0]
        before = results_logs(results)
        new = write_files(results, {f"{LOG_PREFIX}-20260102-000000-a.log": "new"})[0]
        assert before == frozenset({old}), before
        assert new_results_logs(before, results_logs(results)) == [new]
        assert new_results_logs(before, before) == []
        assert results_logs(results / "absent") == frozenset()


def _check_language_is_required_and_runs_default_to_five() -> None:
    parser = build_parser()
    expect_usage_error(lambda: request_from_args(parser.parse_args([])), "--language is required")
    request = request_from_args(parser.parse_args(["--language=lang-a"]))
    assert request.runs == DEFAULT_RUNS, request
    assert request.root == TEST_OUTPUT_DIR / DEFAULT_OUTPUT_FOLDER / "lang-a", request
    refusal = io.StringIO()
    with contextlib.redirect_stdout(refusal):  # The refusal a run below two prints, read below.
        exit_code = run_gate(DeterminismRequest("lang-a", request.root, MINIMUM_RUNS - 1, False))
    assert exit_code == EXIT_VIOLATION, exit_code
    assert f"Runs must be >= {MINIMUM_RUNS}" in refusal.getvalue(), refusal.getvalue()


_SELF_TEST_CHECKS: Final = (
    _check_manifest_identical_trees_agree_despite_datrix_metadata,
    _check_manifest_one_changed_byte_differs,
    _check_fingerprint_same_failure_in_another_output_dir_agrees,
    _check_fingerprint_different_error_differs,
    _check_comparison_agreeing_runs_pass,
    _check_comparison_changed_classification_fails,
    _check_comparison_changed_fingerprint_fails,
    _check_a_run_reads_the_log_it_wrote,
    _check_language_is_required_and_runs_default_to_five,
    check_walk_skips_excluded_directories_and_links,
    check_generation_command_is_an_argument_vector,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/realization/generation-determinism-gate.ps1``, each parameter spelled ``--kebab``."""
    parser = gate_parser(WRAPPER, "Generate one example N times for one language and require one outcome.")
    parser.add_argument("--language", default="", help="A registered datrix.languages name (required).")
    parser.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS, help=f"Generations to compare (default {DEFAULT_RUNS}, >= 2)."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return gate_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser())
    try:
        return run_gate(request_from_args(args))
    except (GeneratedTreeError, OSError) as error:
        print(f"GATE FAILED: {error}")
        return EXIT_VIOLATION


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
