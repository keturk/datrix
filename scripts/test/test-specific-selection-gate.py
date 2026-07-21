#!/usr/bin/env python3
"""Gate: `test.ps1 <package> -Specific <file>` must run ONLY that file's tests.

Why this gate exists
--------------------
`-Specific` is the fast-iteration verification path every agent uses, and a run
that reports PASSED while its own artifacts describe a *different* file's tests
is a silent false green: the caller "proves" a fix that never ran.

That was a real defect. `TeeLogger` named its run directory
``test-results-<YYYYMMDD-HHMMSS>`` (second granularity) and created it with
``mkdir(exist_ok=True)``, so two `test.ps1` invocations against one package that
started in the same second silently SHARED one run directory, overwriting each
other's ``junit-*.xml`` and ``index.json``. Each process still reported its own
correct exit code, so both printed PASSED -- while one of them pointed the caller
at the other's results.

What this gate proves, on every run
-----------------------------------
1. NON-VACUITY (self-test, runs first). The comparator is fed a deliberately
   WRONG-file run directory -- a synthetic JUnit XML naming another file's tests
   -- and MUST report a violation. It is also fed a correct one and must accept
   it. A comparator that cannot detect the forced mismatch fails the gate
   outright, before any real result is trusted.
2. POSITIVE. A real `test.ps1 <pkg> -Specific <fileA>` run's OWN artifacts
   (the run directory it printed) name tests from fileA and nothing else.
3. MULTI-FILE POSITIVE. A real `test.ps1 <pkg> -Specific "<fileA>,<fileB>"` run
   (comma-separated batch, ONE pytest session) names tests from BOTH files --
   each contributes at least one testcase -- and from nothing else. This is the
   batched form the orchestrator wave gates use instead of one runner startup
   per file; a batch that silently drops or adds a file is a false green.
4. RUN-DIRECTORY EXCLUSIVITY (deterministic). TeeLogger's timestamp format is
   pinned to a literal so every racer computes the SAME preferred directory name
   -- a guaranteed collision, not a hoped-for one. Sequential racers prove the
   name is never reused; concurrent racers prove the claim is atomic. This is the
   root-cause invariant, and it fails 8/8 against the old `mkdir(exist_ok=True)`.
5. CONCURRENCY REGRESSION (end-to-end). Two `test.ps1 -Specific` runs against the
   SAME package but DIFFERENT files, launched concurrently, must land in distinct
   run directories and each must name only its own file. Whether these two
   processes actually collide on one second is up to the scheduler, so step 4 --
   not this step -- is what makes the invariant reliably enforced.

Exit codes: 0 = all checks pass, 1 = a check failed, 2 = usage/config error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.logging_utils import LogConfig, TeeLogger  # noqa: E402
from shared.structured_log_writer import StructuredLogWriter  # noqa: E402

# The pair from the original report: two files in one package that a
# `-Specific` run was observed to confuse. Both are small, so the gate stays fast.
_DEFAULT_PACKAGE = "datrix-codegen-python"
_DEFAULT_FILE_A = "tests/generators/cross_cutting/test_integration_test_generator.py"
_DEFAULT_FILE_B = "tests/generators/cross_cutting/test_resilience_test_generator.py"

_TEST_PS1 = _SCRIPT_DIR / "test.ps1"
_RUN_DIR_MARKERS = ("Details:", "Structured test results:")

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


def _normalize(path_text: str) -> str:
    """Normalize a test path for comparison (slashes, node id, casing of separators)."""
    cleaned = path_text.strip().replace("\\", "/")
    # A pytest node id ("tests/x.py::TestC::test_f") selects a file too.
    return cleaned.split("::", 1)[0].lstrip("./")


# The gate must judge a run by the very classname->file translation that produced
# the artifacts an agent reads, so it reuses StructuredLogWriter's own mapper
# rather than reimplementing it.
_MAPPER = StructuredLogWriter(project_name="specific-selection-gate", run_dir=_SCRIPT_DIR)


def _classname_to_file(classname: str) -> str:
    """Map a JUnit classname to its source file, using the SAME mapping index.json uses."""
    return _MAPPER._classname_to_filepath(classname)  # noqa: SLF001


def _junit_files(run_dir: Path) -> list[Path]:
    return sorted(p for p in run_dir.glob("junit*.xml") if p.stat().st_size > 0)


def _files_named_by_junit(run_dir: Path) -> tuple[set[str], int]:
    """Return (set of source files named by JUnit testcases, total testcase count)."""
    named: set[str] = set()
    total = 0
    for xml_path in _junit_files(run_dir):
        root = ET.parse(xml_path).getroot()  # noqa: S314
        for testcase in root.iter("testcase"):
            total += 1
            named.add(_normalize(_classname_to_file(testcase.get("classname", ""))))
    return named, total


def _files_named_by_index(run_dir: Path) -> set[str]:
    """Files named by index.json's failure/error entries (index.json lists no passes)."""
    index_path = run_dir / "index.json"
    if not index_path.exists():
        return set()
    data = json.loads(index_path.read_text(encoding="utf-8"))
    named: set[str] = set()
    for key in ("failures", "errors"):
        for entry in data.get(key) or []:
            file_text = entry.get("file")
            if file_text:
                named.add(_normalize(str(file_text)))
    return named


def check_selection(run_dir: Path, requested_file: str) -> list[str]:
    """Judge one run directory against the file its invocation asked for.

    Returns a list of violations; an empty list means the run's own artifacts name
    ONLY the requested file. This is the single comparator used by every step of
    the gate -- including the non-vacuity self-test, which is what makes that
    self-test meaningful.
    """
    violations: list[str] = []
    want = _normalize(requested_file)

    if not run_dir.is_dir():
        return [f"run directory does not exist: {run_dir}"]

    xml_paths = _junit_files(run_dir)
    if not xml_paths:
        return [f"no non-empty JUnit XML in {run_dir}: the run proves nothing"]

    named, total = _files_named_by_junit(run_dir)
    if total == 0:
        violations.append(
            f"{run_dir}: JUnit XML contains zero testcases -- a run that executed no "
            f"test cannot be evidence for {want}"
        )

    for found in sorted(named):
        if found != want:
            violations.append(
                f"{run_dir}: JUnit names tests from '{found}' but the run requested "
                f"'{want}'. The results in this directory describe a different file."
            )

    for found in sorted(_files_named_by_index(run_dir)):
        if found != want:
            violations.append(
                f"{run_dir}: index.json names tests from '{found}' but the run "
                f"requested '{want}'."
            )

    return violations


def check_selection_multi(run_dir: Path, requested_files: list[str]) -> list[str]:
    """Judge one run directory against a comma-batched multi-file selection.

    Violations when: the run's artifacts name a file OUTSIDE the requested set
    (wrong selection), or any requested file contributed ZERO testcases (silently
    dropped from the batch). Empty list = the batch ran exactly the requested set.
    """
    violations: list[str] = []
    wanted = {_normalize(f) for f in requested_files}

    if not run_dir.is_dir():
        return [f"run directory does not exist: {run_dir}"]

    xml_paths = _junit_files(run_dir)
    if not xml_paths:
        return [f"no non-empty JUnit XML in {run_dir}: the run proves nothing"]

    named, total = _files_named_by_junit(run_dir)
    if total == 0:
        violations.append(
            f"{run_dir}: JUnit XML contains zero testcases -- a run that executed no "
            f"test cannot be evidence for {sorted(wanted)}"
        )

    for found in sorted(named - wanted):
        violations.append(
            f"{run_dir}: JUnit names tests from '{found}' but the batch requested "
            f"only {sorted(wanted)}."
        )
    for missing in sorted(wanted - named):
        violations.append(
            f"{run_dir}: requested file '{missing}' contributed ZERO testcases -- "
            f"the batch silently dropped it."
        )

    for found in sorted(_files_named_by_index(run_dir) - wanted):
        violations.append(
            f"{run_dir}: index.json names tests from '{found}' but the batch "
            f"requested only {sorted(wanted)}."
        )

    return violations


def _write_synthetic_run(run_dir: Path, classname: str, function: str) -> None:
    """Write a minimal, valid one-testcase run directory (JUnit XML + index.json)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "junit-parallel.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" '
        'tests="1" time="0.01">'
        f'<testcase classname="{classname}" name="{function}" time="0.01" />'
        "</testsuite></testsuites>\n",
        encoding="utf-8",
    )
    (run_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": "synthetic",
                "result": "PASSED",
                "counts": {"passed": 1, "failed": 0, "error": 0, "skipped": 0},
                "failures": [],
                "errors": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def self_test(scratch_root: Path) -> bool:
    """Prove the comparator can actually DETECT a wrong-file selection.

    A gate that cannot fail is not a gate. This forces the exact defect the gate
    exists to catch -- a run directory whose JUnit names a file OTHER than the one
    requested -- and requires check_selection() to reject it. It also requires the
    comparator to ACCEPT a correct run, so it cannot pass by rejecting everything.
    """
    _step("Step 1/5: non-vacuity self-test (the comparator must reject a forced wrong-file run)")
    scratch = scratch_root / "selftest"

    correct_dir = scratch / "correct"
    _write_synthetic_run(
        correct_dir,
        "tests.generators.cross_cutting.test_integration_test_generator.TestIntegrationTestGenerator",
        "test_generates_integration_tests",
    )
    correct_violations = check_selection(correct_dir, _DEFAULT_FILE_A)
    if correct_violations:
        _fail(
            "comparator REJECTED a correct run -- it would fail every real run and "
            "prove nothing. Violations: " + "; ".join(correct_violations)
        )
        return False
    _ok("comparator accepts a correct run (requested file == the file JUnit names)")

    wrong_dir = scratch / "forced-wrong-file"
    _write_synthetic_run(
        wrong_dir,
        "tests.generators.cross_cutting.test_resilience_test_generator.TestResilienceTestGenerator",
        "test_generates_resilience_tests",
    )
    wrong_violations = check_selection(wrong_dir, _DEFAULT_FILE_A)
    if not wrong_violations:
        _fail(
            "comparator ACCEPTED a run whose JUnit names "
            f"'{_DEFAULT_FILE_B}' while '{_DEFAULT_FILE_A}' was requested. The gate is "
            "vacuous: it cannot detect the very defect it exists to catch."
        )
        return False
    _ok("comparator rejects a forced wrong-file run:")
    for violation in wrong_violations:
        print(f"     -> {violation}")

    empty_dir = scratch / "forced-empty"
    _write_synthetic_run(
        empty_dir,
        "tests.generators.cross_cutting.test_integration_test_generator.TestIntegrationTestGenerator",
        "test_x",
    )
    (empty_dir / "junit-parallel.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest" '
        'tests="0" /></testsuites>\n',
        encoding="utf-8",
    )
    if not check_selection(empty_dir, _DEFAULT_FILE_A):
        _fail("comparator ACCEPTED a run that executed zero testcases -- a false green.")
        return False
    _ok("comparator rejects a run that executed zero testcases")
    return True


def run_dir_exclusivity_check(scratch_root: Path) -> bool:
    """Deterministically prove TeeLogger never hands two runs the same run directory.

    This is the root-cause invariant of that defect, checked without relying on a
    race actually landing. `LogConfig.timestamp_format` is pinned to a literal, so
    every TeeLogger here computes the SAME preferred directory name -- a guaranteed
    collision. Each must still end up with a directory of its own.

    Sequential racers prove the name is never REUSED; threaded racers prove the
    claim is ATOMIC (mkdir-without-exist_ok), so two simultaneous claimants cannot
    both believe they own one directory.

    With the old `mkdir(exist_ok=True)`, every racer returns the same directory and
    both halves of this check fail -- which is exactly why it belongs in the gate.
    """
    _step("Step 4/5: run-directory exclusivity (forced same-name collision, deterministic)")
    racers = 8
    ok = True

    def claim(root: Path, index: int) -> Path:
        config = LogConfig(
            log_dir=".test_results",
            prefix="test-results",
            # No % directives -> strftime returns this literal, so every racer wants
            # the identical directory name. This is the collision, made certain.
            timestamp_format="pinned-collision",
            project_name=f"racer-{index}",
            quiet_mode=True,
        )
        with TeeLogger(config, project_root=root) as logger:
            logger.write(f"racer {index}")
            run_dir = logger.get_run_dir()
        if run_dir is None:
            raise RuntimeError("TeeLogger produced no run directory")
        return run_dir

    sequential_root = scratch_root / "exclusivity-sequential"
    sequential_root.mkdir(parents=True, exist_ok=True)
    sequential = [claim(sequential_root, i) for i in range(racers)]
    if len(set(sequential)) != racers:
        _fail(
            f"{racers} sequential runs that computed the same preferred directory name "
            f"got only {len(set(sequential))} distinct run directories. A reused run "
            f"directory means a later run overwrites an earlier run's junit-*.xml and "
            f"index.json, so its results are reported as the earlier run's."
        )
        ok = False
    else:
        _ok(f"{racers} sequential same-name runs -> {racers} distinct run directories")

    concurrent_root = scratch_root / "exclusivity-concurrent"
    concurrent_root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=racers) as pool:
        concurrent = list(pool.map(lambda i: claim(concurrent_root, i), range(racers)))
    if len(set(concurrent)) != racers:
        _fail(
            f"{racers} CONCURRENT runs that computed the same preferred directory name "
            f"got only {len(set(concurrent))} distinct run directories -- the directory "
            f"claim is not atomic. This is the 17-14 defect."
        )
        ok = False
    else:
        _ok(f"{racers} concurrent same-name runs -> {racers} distinct run directories")

    return ok


def _run_specific(package: str, test_file: str) -> tuple[int, Optional[Path], str]:
    """Invoke `test.ps1 <package> -Specific <file>` and return its OWN run directory.

    The run directory is taken from the path the runner itself printed -- never by
    scanning .test_results for the newest directory, which is precisely the guess
    that misattributes a concurrent run's results.
    """
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(_TEST_PS1),
            package,
            "-Specific",
            test_file,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    run_dir: Optional[Path] = None
    for line in output.splitlines():
        stripped = line.strip()
        for marker in _RUN_DIR_MARKERS:
            if stripped.startswith(marker):
                candidate = stripped[len(marker) :].strip()
                if candidate.endswith("index.json"):
                    run_dir = Path(candidate).parent
    return proc.returncode, run_dir, output


def positive_check(package: str, file_a: str) -> bool:
    _step(f"Step 2/5: real run -- test.ps1 {package} -Specific {file_a}")
    code, run_dir, output = _run_specific(package, file_a)
    if run_dir is None:
        _fail("the run did not report a run directory. Output:\n" + output)
        return False
    print(f"     run directory: {run_dir}  (exit {code})")
    violations = check_selection(run_dir, file_a)
    if violations:
        _fail("the run's own artifacts do not match the requested file:")
        for violation in violations:
            print(f"     -> {violation}")
        return False
    _ok(f"the run's own index.json/JUnit name ONLY {file_a}")
    return True


def multi_positive_check(package: str, file_a: str, file_b: str) -> bool:
    """One batched run must execute BOTH files -- and nothing else."""
    batch = f"{file_a},{file_b}"
    _step(f'Step 3/5: batched run -- test.ps1 {package} -Specific "{batch}"')
    code, run_dir, output = _run_specific(package, batch)
    if run_dir is None:
        _fail("the batched run did not report a run directory. Output:\n" + output)
        return False
    print(f"     run directory: {run_dir}  (exit {code})")
    violations = check_selection_multi(run_dir, [file_a, file_b])
    if violations:
        _fail("the batched run's own artifacts do not match the requested set:")
        for violation in violations:
            print(f"     -> {violation}")
        return False
    _ok(f"one pytest session ran BOTH {file_a} and {file_b}, and nothing else")
    return True


def concurrency_check(package: str, file_a: str, file_b: str) -> bool:
    """Reproduce the original defect on purpose: two concurrent -Specific runs.

    Before the fix, these two invocations shared one run directory (same-second
    timestamp + mkdir(exist_ok=True)) and clobbered each other's artifacts, so the
    run that asked for file B reported PASSED over file A's tests.
    """
    _step(f"Step 5/5: concurrency -- two real -Specific runs against {package} at once")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_run_specific, package, file_a)
        future_b = pool.submit(_run_specific, package, file_b)
        code_a, dir_a, out_a = future_a.result()
        code_b, dir_b, out_b = future_b.result()

    ok = True
    if dir_a is None or dir_b is None:
        _fail(
            "a concurrent run did not report a run directory.\n"
            f"--- run A ---\n{out_a}\n--- run B ---\n{out_b}"
        )
        return False

    print(f"     run A ({file_a}) -> {dir_a}  (exit {code_a})")
    print(f"     run B ({file_b}) -> {dir_b}  (exit {code_b})")

    if dir_a == dir_b:
        _fail(
            f"both concurrent runs claimed the SAME run directory ({dir_a}). They "
            "overwrite each other's junit-*.xml and index.json, so at least one run's "
            "reported results belong to the other run. This is the 17-14 defect."
        )
        ok = False

    for run_dir, requested in ((dir_a, file_a), (dir_b, file_b)):
        violations = check_selection(run_dir, requested)
        if violations:
            _fail(f"concurrent run for '{requested}' reported another file's tests:")
            for violation in violations:
                print(f"     -> {violation}")
            ok = False

    if ok:
        _ok("both concurrent runs got private run directories naming only their own file")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prove that a `test.ps1 -Specific <file>` run's own index.json/JUnit "
            "output names only tests from the requested file."
        )
    )
    parser.add_argument("--package", default=_DEFAULT_PACKAGE, help="Package to exercise")
    parser.add_argument("--file-a", default=_DEFAULT_FILE_A, help="First test file (package-relative)")
    parser.add_argument("--file-b", default=_DEFAULT_FILE_B, help="Second test file (package-relative)")
    args = parser.parse_args()

    if not _TEST_PS1.exists():
        print(f"ERROR: test.ps1 not found at {_TEST_PS1}", file=sys.stderr)
        return 2

    for test_file in (args.file_a, args.file_b):
        resolved = _SCRIPT_DIR.parents[2] / args.package / test_file
        if not resolved.is_file():
            print(
                f"ERROR: test file not found: {resolved}\n"
                f"Expected a path relative to the '{args.package}' package root "
                f"(e.g. tests/unit/test_foo.py). Fix: pass an existing file via "
                f"--file-a/--file-b.",
                file=sys.stderr,
            )
            return 2

    with tempfile.TemporaryDirectory(prefix="specific-selection-gate-") as tmp:
        results = [
            self_test(Path(tmp)),
            positive_check(args.package, args.file_a),
            multi_positive_check(args.package, args.file_a, args.file_b),
            run_dir_exclusivity_check(Path(tmp)),
            concurrency_check(args.package, args.file_a, args.file_b),
        ]

    print()
    if all(results):
        print(f"{_GREEN}GATE PASSED{_RESET}: -Specific selects only the requested file, "
              f"and the check is non-vacuous.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the violations above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
