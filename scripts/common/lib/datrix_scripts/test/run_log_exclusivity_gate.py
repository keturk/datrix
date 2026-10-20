"""Prove two concurrent runs can never be handed the same run-log file (the behaviour of
``test/run-log-exclusivity-gate.ps1``).

A run log named from a second-granularity timestamp plus a few labels is one name for every run that agrees on
those labels. That was a real, observed defect: two ``generate.ps1`` runs started together for two different
config profiles computed the identical ``generate-results-<timestamp>-<language>.log``, the second run's header
write truncated the first run's log, and both then appended into one file -- so each run pointed its caller at a
log describing the other run's generation. Adding another label does not fix that; it moves it. Uniqueness has to
come from claiming the name: ``common/DatrixRunLog.psm1``'s ``New-DatrixRunLogFile`` (FileMode.CreateNew) and its
Python twin ``datrix_scripts.run_log.claim_run_log_file`` (O_CREAT | O_EXCL), both atomic create-or-fail.

The gate holds both claimers to that, the PowerShell one driven through PowerShell children:

1. NON-VACUITY -- the distinct-count comparator is fed names composed the way the defect composed them (same
   timestamp, same labels) and MUST see one name, and genuinely distinct names and must see all of them; and the
   two composers produce the same name for every label set, hostile labels included.
2. SEQUENTIAL EXCLUSIVITY -- N claims on a PINNED base name (a guaranteed collision) yield N distinct files that
   all exist, from each claimer.
3. CONCURRENT EXCLUSIVITY -- the same N claims made simultaneously (N PowerShell processes released together; N
   threads behind a barrier) yield N distinct files.
4. LABEL CONTAINMENT -- a label carrying separators, "..", or a drive letter cannot steer the log out of its
   results directory.
5. WIRING -- the syntax tree of ``datrix_scripts.dev.generate`` (the module behind generate.ps1) calls
   ``claim_run_log_file`` and builds no ``generate-results-<...>`` name inline; the matcher is first proven on a
   planted module that does both.

``--self-test`` runs step 1 and the wrapper seam checks, and claims no file. Exit 0 every run gets a log file of
its own and the check is non-vacuous, 1 a check failed, 2 usage error (DatrixRunLog.psm1 or the generate module
not found, or --racers outside 2..64).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Sequence
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    NamedCheck,
    UsageError,
    report_step,
    run_checks,
    run_main,
)
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.paths import PACKAGE_DIR, SCRIPTS_DIR
from datrix_scripts.powershell_ast import POWERSHELL_EXE
from datrix_scripts.run_log import claim_run_log_file, run_log_base_name
from datrix_scripts.test.wrappers import seam_checks

MODULE: Final = "datrix_scripts.test.run_log_exclusivity_gate"
WRAPPER: Final = "run-log-exclusivity-gate"
GATE: Final = "run-log-exclusivity"

RUN_LOG_MODULE: Final = SCRIPTS_DIR / "common" / "DatrixRunLog.psm1"
#: The module behind dev/generate.ps1: it claims the generate-results log.
GENERATE_MODULE: Final = PACKAGE_DIR / "dev" / "generate.py"

DEFAULT_RACERS: Final = 8
MIN_RACERS: Final = 2
MAX_RACERS: Final = 64

#: A fixed moment, so every composed base name in this gate is identical by construction: the collision these
#: checks survive is guaranteed, not scheduled.
PINNED_TIMESTAMP: Final = datetime(2026, 1, 2, 3, 4, 5)
_TIMESTAMP_WIRE_FORMAT: Final = "%Y-%m-%dT%H:%M:%S"
PREFIX: Final = "generate-results"
LABELS: Final = ("python", "pilot")
HOSTILE_LABELS: Final = (
    "../../escaped",
    "..\\..\\escaped",
    "C:\\Windows\\System32\\log",
    "nested/deep/name",
    "with spaces and *wildcards?",
)
#: A character that would let a composed name name a path or a wildcard.
_NAME_UNSAFE: Final = re.compile(r'[\\/:*?"<>|]')
CLAIM_FUNCTION: Final = claim_run_log_file.__name__
BASE_NAME_FUNCTION: Final = run_log_base_name.__name__
_COMPOSED_NAME: Final = "generate-results-"
_READY: Final = "READY"
_GO: Final = "go\n"
_CHILD_TIMEOUT_SECONDS: Final = 120
_SCRATCH_PREFIX: Final = "datrix-run-log-gate-"

#: The PowerShell side: one request (a JSON file) per child. ``names`` composes a base name per label set,
#: ``claim`` claims each base name in turn, ``race`` prints READY, waits for one stdin line, then claims once.
_PROGRAM: Final = r"""
param([Parameter(Mandatory)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
Import-Module $request.module -Force
$timestamp = [datetime]::ParseExact($request.timestamp, 'yyyy-MM-ddTHH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
switch ($request.mode) {
    'names' {
        $names = @(foreach ($labels in $request.label_sets) {
            Get-DatrixRunLogBaseName -Prefix $request.prefix -Segment ([string[]]@($labels)) -Timestamp $timestamp
        })
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject $names -Compress))
    }
    'claim' {
        $paths = @(foreach ($base in $request.base_names) { New-DatrixRunLogFile -Directory $request.directory -BaseName $base })
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject $paths -Compress))
    }
    'race' {
        [Console]::Out.WriteLine('READY')
        [Console]::Out.Flush()
        $null = [Console]::In.ReadLine()
        $path = New-DatrixRunLogFile -Directory $request.directory -BaseName @($request.base_names)[0]
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject @($path) -Compress))
    }
    default { throw "unknown mode '$($request.mode)'; expected names, claim or race" }
}
"""

#: A module that claims and composes, to prove the wiring matcher sees both (and that a docstring naming the
#: log pattern is no composition).
_PLANTED_CALLER: Final = (
    '"""Writes generate-results-<timestamp>-<language>.log."""\n'
    "from datrix_scripts import run_log\n"
    'base = run_log.run_log_base_name("generate-results", [language])\n'
    "log = run_log.claim_run_log_file(directory, base)\n"
    'composed = f"generate-results-{stamp}-{language}.log"\n'
)


class ClaimerError(Exception):
    """A PowerShell claimer child failed or printed something other than its JSON answer (a gate failure)."""


class PowerShellClaimer:
    """``DatrixRunLog.psm1``'s functions, run in PowerShell children from a program written under *work_dir*."""

    def __init__(self, work_dir: Path, module: Path) -> None:
        self._work_dir = work_dir
        self._module = module
        self._program = work_dir / "run-log-claimer.ps1"
        self._program.write_text(_PROGRAM, encoding="utf-8-sig")
        self._requests = 0

    def _request(self, mode: str, **fields: object) -> Path:
        self._requests += 1
        path = self._work_dir / f"request-{self._requests}.json"
        payload = {"mode": mode, "module": str(self._module), "prefix": PREFIX,
                   "timestamp": PINNED_TIMESTAMP.strftime(_TIMESTAMP_WIRE_FORMAT), **fields}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _command(self, request: Path) -> list[str]:
        return [POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(self._program), "-RequestPath", str(request)]

    @staticmethod
    def _answer(stdout: str, returncode: int, stderr: str, what: str) -> list[str]:
        if returncode != 0:
            raise ClaimerError(f"the PowerShell claimer exited {returncode} on {what}: {stderr.strip()[:2000]}")
        lines = [line for line in stdout.splitlines() if line.strip()]
        try:
            answer = json.loads(lines[-1]) if lines else None
        except json.JSONDecodeError as exc:
            raise ClaimerError(f"the PowerShell claimer printed no JSON answer on {what}: {lines[-1][:300]!r}") from exc
        if not isinstance(answer, list):
            raise ClaimerError(f"the PowerShell claimer's answer on {what} is not a list: {stdout[:300]!r}")
        return [str(item) for item in answer]

    def _run(self, request: Path, what: str) -> list[str]:
        try:
            completed = subprocess.run(self._command(request), capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", timeout=_CHILD_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClaimerError(f"could not run {POWERSHELL_EXE} for {what}: {exc}. Expected Windows PowerShell "
                               "on PATH.") from exc
        return self._answer(completed.stdout, completed.returncode, completed.stderr, what)

    def names(self, label_sets: Sequence[Sequence[str]]) -> list[str]:
        """``Get-DatrixRunLogBaseName`` of each label set, at the pinned timestamp."""
        return self._run(self._request("names", label_sets=[list(labels) for labels in label_sets]),
                         f"composing {len(label_sets)} names")

    def claim(self, directory: Path, base_names: Sequence[str]) -> list[str]:
        """``New-DatrixRunLogFile`` of each base name in turn, in one child."""
        return self._run(self._request("claim", directory=str(directory), base_names=list(base_names)),
                         f"{len(base_names)} sequential claims")

    def race(self, directory: Path, base_name: str, racers: int) -> list[str]:
        """One claim of *base_name* from each of *racers* children, all released together once every one is up."""
        request = self._request("race", directory=str(directory), base_names=[base_name])
        processes: list[subprocess.Popen[str]] = []
        try:
            for _ in range(racers):
                processes.append(subprocess.Popen(self._command(request), stdin=subprocess.PIPE,
                                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                                  encoding="utf-8", errors="replace"))
            for process in processes:
                _await_ready(process)
            for process in processes:
                _release(process)
            return [path for process in processes for path in self._collect(process)]
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def _collect(self, process: subprocess.Popen[str]) -> list[str]:
        try:
            stdout, stderr = process.communicate(timeout=_CHILD_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise ClaimerError(f"a racing claimer did not finish within {_CHILD_TIMEOUT_SECONDS}s") from exc
        return self._answer(stdout, process.returncode, stderr, "a racing claim")


def _await_ready(process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        raise ClaimerError("a racing claimer was started without a stdout pipe")
    line = process.stdout.readline().strip()
    if line != _READY:
        _, stderr = process.communicate(timeout=_CHILD_TIMEOUT_SECONDS)
        raise ClaimerError(f"a racing claimer printed {line!r} instead of {_READY}: {stderr.strip()[:2000]}")


def _release(process: subprocess.Popen[str]) -> None:
    if process.stdin is None:
        raise ClaimerError("a racing claimer was started without a stdin pipe")
    process.stdin.write(_GO)
    process.stdin.close()


def _python_names(label_sets: Sequence[Sequence[str]]) -> list[str]:
    return [run_log_base_name(PREFIX, labels, timestamp=PINNED_TIMESTAMP) for labels in label_sets]


def _python_race(directory: Path, base_name: str, racers: int) -> list[str]:
    """One claim of *base_name* from each of *racers* threads released together by a barrier."""
    barrier = threading.Barrier(racers)
    claimed: list[str] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def racer() -> None:
        barrier.wait()
        try:
            path = claim_run_log_file(directory, base_name)
        except (OSError, RuntimeError) as exc:
            with lock:
                failures.append(exc)
            return
        with lock:
            claimed.append(str(path))

    threads = [threading.Thread(target=racer) for _ in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if failures:
        raise AssertionError(f"{len(failures)} concurrent Python claim(s) raised: {failures[0]}")
    return claimed


# ---------------------------------------------------------------------------
# The five steps (each a check: AssertionError or ClaimerError is its failure)
# ---------------------------------------------------------------------------


def _assert_one_name_per_composition(names: Sequence[str], racers: int, who: str) -> None:
    colliding, varied = names[:racers], names[racers:2 * racers]
    assert len(set(colliding)) == 1, (
        f"{who}: {racers} names composed from one timestamp and one label set produced {len(set(colliding))} "
        "distinct names, expected 1. The gate cannot force the collision it exists to survive, so its later "
        "steps prove nothing."
    )
    assert len(set(varied)) == racers, (
        f"{who}: {racers} names composed from {racers} different label sets produced {len(set(varied))} distinct "
        f"names, expected {racers}. The comparator reports sameness that is not there, so a passing exclusivity "
        "step would be meaningless."
    )


def check_non_vacuity(claimer: PowerShellClaimer, racers: int) -> None:
    """Step 1: the comparator sees a forced collision and no false one, and both composers agree name for name."""
    label_sets = [
        *([LABELS] * racers),
        *[(LABELS[0], f"profile{number}") for number in range(1, racers + 1)],
        *[(LABELS[0], label) for label in HOSTILE_LABELS],
    ]
    powershell_names = claimer.names(label_sets)
    python_names = _python_names(label_sets)
    _assert_one_name_per_composition(powershell_names, racers, "DatrixRunLog.psm1")
    _assert_one_name_per_composition(python_names, racers, "datrix_scripts.run_log")
    mismatched = [(ps, py) for ps, py in zip(powershell_names, python_names, strict=True) if ps != py]
    assert len(powershell_names) == len(label_sets) and not mismatched, (
        f"the PowerShell and Python composers disagree on {len(mismatched)} of {len(label_sets)} names "
        f"(first: {mismatched[:1]}); expected one name per label set from both, since both claim in one directory"
    )


def _assert_distinct_and_created(claimed: Sequence[str], racers: int, who: str, how: str) -> None:
    assert len(set(claimed)) == racers, (
        f"{who}: {racers} {how} runs wanting the same log name got {len(set(claimed))} distinct files, expected "
        f"{racers}. A shared log file means one run truncates the other's log and both append into one file."
    )
    missing = [path for path in claimed if not Path(path).is_file()]
    assert not missing, (
        f"{who}: {len(missing)} claimed path(s) do not exist: {missing[:3]}; a claim that does not create the "
        "file reserves nothing"
    )


def check_sequential_exclusivity(claimer: PowerShellClaimer, racers: int, root: Path) -> None:
    """Step 2: N claims on one pinned base name, one after another, yield N distinct created files."""
    base = run_log_base_name(PREFIX, LABELS, timestamp=PINNED_TIMESTAMP)
    _assert_distinct_and_created(claimer.claim(root / "sequential-ps", [base] * racers), racers,
                                 "DatrixRunLog.psm1", "sequential")
    python_claimed = [str(claim_run_log_file(root / "sequential-py", base)) for _ in range(racers)]
    _assert_distinct_and_created(python_claimed, racers, "datrix_scripts.run_log", "sequential")


def check_concurrent_exclusivity(claimer: PowerShellClaimer, racers: int, root: Path) -> None:
    """Step 3: the same N claims made simultaneously yield N distinct files: the claim is atomic."""
    base = run_log_base_name(PREFIX, LABELS, timestamp=PINNED_TIMESTAMP)
    ps_dir = root / "concurrent-ps"
    ps_dir.mkdir()
    _assert_distinct_and_created(claimer.race(ps_dir, base, racers), racers, "DatrixRunLog.psm1", "CONCURRENT")
    _assert_distinct_and_created(_python_race(root / "concurrent-py", base, racers), racers,
                                 "datrix_scripts.run_log", "CONCURRENT")


def _assert_contained(claimed: Sequence[str], directory: Path, who: str) -> None:
    resolved = directory.resolve()
    escaped = [path for path in claimed if Path(path).resolve().parent != resolved]
    assert not escaped, f"{who}: hostile labels produced logs outside {resolved}: {escaped[:3]}"


def check_label_containment(claimer: PowerShellClaimer, root: Path) -> None:
    """Step 4: a hostile label composes no path or wildcard character and claims inside the results directory."""
    bases = claimer.names([(LABELS[0], label) for label in HOSTILE_LABELS])
    unsafe = [(label, base) for label, base in zip(HOSTILE_LABELS, bases, strict=True) if _NAME_UNSAFE.search(base)]
    assert not unsafe, f"composed base names still carry a path or wildcard character: {unsafe}"
    ps_dir = root / "containment-ps"
    ps_dir.mkdir()
    _assert_contained(claimer.claim(ps_dir, bases), ps_dir, "DatrixRunLog.psm1")
    py_dir = root / "containment-py"
    _assert_contained([str(claim_run_log_file(py_dir, base)) for base in _python_names(
        [(LABELS[0], label) for label in HOSTILE_LABELS])], py_dir, "datrix_scripts.run_log")


def _wiring_problems(claim_calls: int, composed: Sequence[str], module: str) -> list[str]:
    problems: list[str] = []
    if claim_calls < 1:
        problems.append(
            f"{module} never calls {CLAIM_FUNCTION}, so its log path is not claimed and two concurrent runs can "
            f"still share one file. Fix: build the name with {BASE_NAME_FUNCTION} and claim it with "
            f"{CLAIM_FUNCTION} (datrix_scripts.run_log)."
        )
    if composed:
        problems.append(
            f"{module} still composes a log name inline: {composed[0]}. A name built from a timestamp is one name "
            "for every run that shares that second."
        )
    return problems


def _called_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else ""


def _composed_names(tree: ast.Module) -> list[str]:
    """Every string literal or f-string of *tree* holding ``generate-results-``, docstrings excepted."""
    docstrings = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)}
    f_string_parts = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    composed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and any(
                isinstance(part, ast.Constant) and _COMPOSED_NAME in str(part.value) for part in node.values):
            composed.append(ast.unparse(node))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str) and _COMPOSED_NAME in node.value
              and id(node) not in docstrings | f_string_parts):
            composed.append(repr(node.value))
    return composed


def _module_wiring_problems(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"{path} does not parse: {exc}") from exc
    claim_calls = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call) and _called_name(node) == CLAIM_FUNCTION)
    return _wiring_problems(claim_calls, _composed_names(tree), path.name)


def check_caller_wiring(root: Path, generate_module: Path = GENERATE_MODULE) -> None:
    """Step 5: the generate module claims its log and composes none inline; the matcher is proven on a planted
    caller."""
    planted = root / "planted_caller.py"
    planted.write_text(_PLANTED_CALLER, encoding="utf-8")
    planted_problems = _module_wiring_problems(planted)
    assert len(planted_problems) == 1 and "composes a log name inline" in planted_problems[0], (
        f"the wiring matcher misread a planted caller that claims once and composes one name inline: "
        f"{planted_problems}; expected exactly the inline-composition problem, or the real check proves nothing"
    )
    problems = _module_wiring_problems(generate_module)
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options of ``test/run-log-exclusivity-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Prove two concurrent runs can never be handed the same run-log file.", allow_abbrev=False)
    parser.add_argument("--racers", type=int, default=DEFAULT_RACERS,
                        help=f"How many runs to force onto one name ({MIN_RACERS}..{MAX_RACERS}, default "
                        f"{DEFAULT_RACERS})")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only step 1, the non-vacuity and composer-parity check, and claim no file")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging")
    return parser


def _require_inputs(args: argparse.Namespace) -> None:
    if not MIN_RACERS <= args.racers <= MAX_RACERS:
        raise UsageError(f"--racers {args.racers} is outside {MIN_RACERS}..{MAX_RACERS}. Pass a number of runs "
                         f"in that range, or omit it for {DEFAULT_RACERS}.")
    for path in (RUN_LOG_MODULE, GENERATE_MODULE):
        if not path.is_file():
            raise UsageError(f"{path.name} not found at: {path}. Expected the datrix scripts tree this module is in.")


def _gate_checks(args: argparse.Namespace, claimer: PowerShellClaimer, root: Path) -> list[NamedCheck]:
    checks = [NamedCheck("non_vacuity", partial(check_non_vacuity, claimer, args.racers))]
    if args.self_test:
        return [*checks, *seam_checks(wrapper=WRAPPER, module=MODULE, parser=build_parser())]
    return [
        *checks,
        NamedCheck("sequential_exclusivity", partial(check_sequential_exclusivity, claimer, args.racers, root)),
        NamedCheck("concurrent_exclusivity", partial(check_concurrent_exclusivity, claimer, args.racers, root)),
        NamedCheck("label_containment", partial(check_label_containment, claimer, root)),
        NamedCheck("caller_wiring", partial(check_caller_wiring, root)),
    ]


def _run(args: argparse.Namespace) -> int:
    _require_inputs(args)
    scope = "step 1 and the wrapper seam" if args.self_test else "all five steps"
    report_step(f"run-log exclusivity: {scope}, {args.racers} racers")
    with tempfile.TemporaryDirectory(prefix=_SCRATCH_PREFIX) as tmp:
        root = Path(tmp)
        work = root / "claimer"
        work.mkdir()
        claimer = PowerShellClaimer(work, RUN_LOG_MODULE)
        passed = run_checks(_gate_checks(args, claimer, root), also_failing=(ClaimerError,))
    print()
    if not passed:
        print("GATE FAILED: see the violations above.")
        return EXIT_VIOLATION
    if args.self_test:
        print("GATE PASSED: the comparator detects a forced collision and both composers agree.")
    else:
        print("GATE PASSED: every run gets a log file of its own, and the check is non-vacuous.")
    return EXIT_PASS


def _gate(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    return run_main(lambda: parser.parse_args(argv), _run)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
