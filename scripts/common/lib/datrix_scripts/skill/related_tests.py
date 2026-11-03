"""The related-tests half of /implement-finding: which tests a fix must leave green, and running them.

A fix session proves its own change; this module also proves the tests that name what it changed. It derives,
from the files a session wrote and from nothing a model reports, the targeted ``test.ps1 -Specific`` runs that must
pass before ``implement-finding.ps1`` deletes a finding, and runs them. Never a whole suite, never a feature-tag
sweep: a finding is one defect, so what it costs to prove stays in proportion to it.

THE SELECTIONS
    Edited tests
        Each test file the session wrote or changed, in its own package.
    Tests that name the change
        Every other test file, in any package, that mentions a code name the session put into or took out of its
        source and test files (``related_references``): ``app_user`` and ``appUser`` are one name, a name that many
        test files mention selects none, and the rarest names are taken first up to a total limit. One run per
        package.

RUNNING THEM
    Packages run side by side and one package's runs run in order (``related_parallel``), after one package
    install check for all of them.

Exit semantics live in the caller (``implement_finding``); this module only plans, runs and reports.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.affected_set import discover_packages
from datrix_scripts.logging_utils import say
from datrix_scripts.skill.chain import event_blocks
from datrix_scripts.skill.common import AssistError, read_text
from datrix_scripts.skill.finding_inbox import summaries_passed
from datrix_scripts.skill.related_parallel import logical_cores, run_units, worker_allotment
from datrix_scripts.skill.related_references import code_names, describe_names, referencing_tests
from datrix_scripts.test.affected_gate import InstallCheckError, ensure_packages_installed_once, install_check_command

LOG = logging.getLogger(__name__)

TEST_SCRIPT_PARTS: Final = ("datrix", "scripts", "test", "test.ps1")
SOURCE_DIRNAME: Final = "src"
TESTS_DIRNAME: Final = "tests"
EDIT_TOOLS: Final = frozenset({"Edit", "Write"})
EDIT_LINES_SUFFIX: Final = "edit_lines"
RUN_TIMEOUT_SECONDS: Final = 3600
MODULE: Final = "datrix_scripts.skill.related_tests"
LIB_DIR: Final = Path(__file__).resolve().parents[2]
VERDICT_FILE: Final = "verdict.json"
LOCK_MESSAGE: Final = "Could not acquire package lock"
LOCK_RETRIES: Final = 5
TAIL_LINES: Final = 40


@dataclass(frozen=True)
class Selection:
    """One targeted ``test.ps1`` run: the package and the test files (relative to it) to run."""

    package: str
    specific: tuple[str, ...]
    reason: str

    def arguments(self) -> list[str]:
        """The ``test.ps1`` arguments after the script path."""
        return [self.package, "-Specific", ",".join(self.specific)]

    def describe(self) -> str:
        return "test.ps1 " + " ".join(self.arguments())


@dataclass(frozen=True)
class SelectionResult:
    selection: Selection
    passed: bool
    tail: str


@dataclass(frozen=True)
class RelatedVerdict:
    """What the related runs proved: the selections planned and those that did not pass."""

    selections: tuple[Selection, ...]
    failures: tuple[SelectionResult, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def _edit_calls(session_log: Path) -> Iterable[tuple[str, dict[str, object]]]:
    """The tool name and input of every ``Edit``, ``Write`` and ``edit_lines`` call of the session, in order."""
    if not session_log.is_file():
        raise AssistError(f"Session log '{session_log}' does not exist. Pass the step's .stream.jsonl.")
    for event in _events(session_log):
        for block in event_blocks(event, "tool_use"):
            name = str(block.get("name", ""))
            tool_input = block.get("input")
            if isinstance(tool_input, dict) and (name in EDIT_TOOLS or name.endswith(EDIT_LINES_SUFFIX)):
                yield name, tool_input


def written_paths(session_log: Path) -> list[Path]:
    """Every file the session wrote with ``Edit``, ``Write`` or ``edit_lines``, in order, from its stream log."""
    return [path for _, tool_input in _edit_calls(session_log) for path in _input_paths(tool_input)]


def _written_texts(name: str, tool_input: dict[str, object]) -> list[tuple[object, object]]:
    """The (file, text) pairs of one edit call; the text is ``None`` for a ``Write`` of the whole file."""
    if name == "Write":
        return [(tool_input.get("file_path"), None)]
    if name == "Edit":
        return [(tool_input.get("file_path"), tool_input.get("old_string")),
                (tool_input.get("file_path"), tool_input.get("new_string"))]
    edits = tool_input.get("edits")
    if not isinstance(edits, list):
        return []
    return [(edit.get("file_path"), edit.get("text")) for edit in edits if isinstance(edit, dict)]


def written_changes(session_log: Path) -> dict[Path, list[str | None]]:
    """The text the session put into or took out of each file: per file, an ``Edit``'s ``old_string`` and
    ``new_string``, an ``edit_lines`` edit's ``text``, and ``None`` for a ``Write`` of the whole file."""
    changes: dict[Path, list[str | None]] = {}
    for name, tool_input in _edit_calls(session_log):
        for raw, text in _written_texts(name, tool_input):
            if isinstance(raw, str) and raw:
                changes.setdefault(Path(raw).resolve(), []).append(text if isinstance(text, str) else None)
    return changes


def _events(session_log: Path) -> Iterable[dict[str, object]]:
    for line in read_text(session_log).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _input_paths(tool_input: dict[str, object]) -> list[Path]:
    raw = [tool_input.get("file_path")]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        raw.extend(edit.get("file_path") for edit in edits if isinstance(edit, dict))
    return [Path(item) for item in raw if isinstance(item, str) and item]


@dataclass(frozen=True)
class _Edits:
    """The session's written files, by package: source files and test files (relative to the package)."""

    sources: dict[str, list[str]]
    tests: dict[str, list[str]]


def classify_edits(root: Path, packages: dict[str, Path], written: Sequence[Path]) -> _Edits:
    """Split *written* into source and test files of the packages; docs, manifests and other trees are ignored,
    and so is a test file the session later removed (there is nothing left to run)."""
    sources: dict[str, list[str]] = {}
    tests: dict[str, list[str]] = {}
    for path in written:
        try:
            parts = path.resolve().relative_to(root.resolve()).parts
        except ValueError:
            continue
        if len(parts) < 3 or parts[0] not in packages:
            continue
        package, tree, relative = parts[0], parts[1], "/".join(parts[1:])
        if tree == SOURCE_DIRNAME:
            bucket = sources
        elif tree == TESTS_DIRNAME and path.name.startswith("test_") and path.suffix == ".py" and path.is_file():
            bucket = tests
        else:
            continue
        if relative not in bucket.setdefault(package, []):
            bucket[package].append(relative)
    return _Edits(sources, tests)


def plan_related(root: Path, written: Sequence[Path],
                 changes: Mapping[Path, Sequence[str | None]] | None = None) -> tuple[Selection, ...]:
    """The targeted runs the files in *written* require; empty when no package source or test was written.

    The runs are the test files the session wrote, and the other test files that name a code name found in
    *changes*, the text it put into or took out of each file (``related_references``).
    """
    packages = discover_packages(root)
    edits = classify_edits(root, packages, written)
    if not edits.sources and not edits.tests:
        return ()
    selections = [Selection(package, tuple(files), "tests the session wrote or changed")
                  for package, files in sorted(edits.tests.items())]
    own = frozenset((packages[package] / relative).resolve()
                    for package, files in edits.tests.items() for relative in files)
    names = code_names(_changed_texts(_edited_paths(packages, edits), changes or {}))
    for package, (files, picked) in sorted(referencing_tests(packages, names, own).items()):
        selections.append(Selection(package, tuple(files), f"tests that name {describe_names(picked)}"))
    return tuple(selections)


def _edited_paths(packages: Mapping[str, Path], edits: _Edits) -> Iterator[Path]:
    for bucket in (edits.sources, edits.tests):
        for package, files in bucket.items():
            yield from (packages[package] / relative for relative in files)


def _changed_texts(paths: Iterable[Path], changes: Mapping[Path, Sequence[str | None]]) -> list[str]:
    """The text put into or taken out of *paths*; the whole file when the session wrote it with ``Write``."""
    texts: list[str] = []
    for path in paths:
        for text in changes.get(path.resolve(), ()):
            if text is not None:
                texts.append(text)
            elif path.is_file():
                texts.append(read_text(path))
    return texts


def _run_harness(root: Path, arguments: Sequence[str],
                 environment: Mapping[str, str] | None = None) -> tuple[int, str]:
    """Run ``test.ps1`` with *arguments* in the foreground (in *environment* when given, else this process's),
    repeating a run that lost the package lock; its exit code and output. The output of the last try still names
    the lock when every try lost it.

    Raises:
        subprocess.TimeoutExpired: when a try ran past ``RUN_TIMEOUT_SECONDS``.
    """
    script = root.joinpath(*TEST_SCRIPT_PARTS)
    returncode, output = 0, ""
    for _ in range(LOCK_RETRIES):
        done = subprocess.run(["powershell", "-NoProfile", "-File", str(script), *arguments],
                              cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=RUN_TIMEOUT_SECONDS, check=False,
                              env=None if environment is None else dict(environment))
        returncode, output = done.returncode, done.stdout + done.stderr
        if LOCK_MESSAGE not in output:
            break
    return returncode, output


def _lost_lock(description: str) -> AssistError:
    return AssistError(f"{description} could not take the package lock in {LOCK_RETRIES} tries: another test run "
                       "holds it. Run the finding again when no other test run is active.")


def run_selection(root: Path, selection: Selection, log: Path,
                  environment: Mapping[str, str] | None = None) -> SelectionResult:
    """Run one selection in the foreground, keep its full output in *log*, and judge it by test.ps1's own
    exit code and closing summary line. A run that lost the package lock to another run is repeated.

    Raises:
        AssistError: when every try lost the lock -- no test ran, so there is nothing for a session to repair.
    """
    try:
        returncode, output = _run_harness(root, selection.arguments(), environment)
    except subprocess.TimeoutExpired:
        log.write_text(f"{selection.describe()}\ntimed out after {RUN_TIMEOUT_SECONDS} seconds\n", encoding="utf-8")
        return SelectionResult(selection, False, f"timed out after {RUN_TIMEOUT_SECONDS} seconds")
    log.write_text(f"{selection.describe()}\n{output}", encoding="utf-8")
    if LOCK_MESSAGE in output:
        raise _lost_lock(selection.describe())
    passed = returncode == 0 and summaries_passed(output)
    tail = "\n".join(output.splitlines()[-TAIL_LINES:])
    return SelectionResult(selection, passed, tail)


def verify_related(root: Path, session_logs: Sequence[Path], log_dir: Path) -> RelatedVerdict:
    """Plan the related selections from every file the session wrote and run them all, keeping each run's
    output under *log_dir*."""
    written = [path for log in session_logs for path in written_paths(log)]
    changes: dict[Path, list[str | None]] = {}
    for log in session_logs:
        for path, texts in written_changes(log).items():
            changes.setdefault(path, []).extend(texts)
    selections = plan_related(root, written, changes)
    log_dir.mkdir(parents=True, exist_ok=True)
    if not selections:
        say("  related runs: none planned (the session wrote no package source or test)")
        return RelatedVerdict(selections, ())
    say(f"  related runs planned: {len(selections)}")
    for number, selection in enumerate(selections, start=1):
        say(f"    {number}. {selection.describe()}  ({selection.reason})")
    results = _run_planned(root, selections, log_dir)
    return RelatedVerdict(selections, tuple(result for result in results if not result.passed))


def _install_check_once(root: Path) -> None:
    """Verify the shared venv's package installs once, so no run repeats it (and none contends for the install lock)."""
    try:
        ensure_packages_installed_once(install_check_command())
    except InstallCheckError as exc:
        raise AssistError(str(exc)) from exc


def _run_planned(root: Path, selections: Sequence[Selection], log_dir: Path) -> list[SelectionResult]:
    """Run *selections*: packages side by side, one package's runs in order; the results in selection order."""
    _install_check_once(root)
    cores = logical_cores()
    package_dirs = discover_packages(root)
    allotment = worker_allotment(package_dirs, sorted({selection.package for selection in selections}), cores)
    total = len(selections)

    def run_one(number: int, environment: dict[str, str]) -> SelectionResult:
        selection = selections[number - 1]
        say(f"  related run {number} of {total} started: {selection.describe()}")
        result = run_selection(root, selection, log_dir / f"related-{number:02d}.log", environment)
        say(f"  related run {number} of {total} {'passed' if result.passed else 'NOT PASSING'}: {selection.describe()}")
        return result

    units = [(selection.package, number) for number, selection in enumerate(selections, start=1)]
    results = run_units(units, run_one, allotment, cores)
    return [results[number] for number in range(1, total + 1)]


def _selection_data(selection: Selection) -> dict[str, object]:
    return {"package": selection.package, "specific": list(selection.specific), "reason": selection.reason}


def _selection_from(data: dict[str, object]) -> Selection:
    return Selection(str(data["package"]), tuple(data["specific"]), str(data["reason"]))


def _verdict_data(verdict: RelatedVerdict) -> dict[str, object]:
    return {"selections": [_selection_data(selection) for selection in verdict.selections],
            "failures": [{"selection": _selection_data(result.selection), "tail": result.tail}
                         for result in verdict.failures]}


def _verdict_from(data: dict[str, object]) -> RelatedVerdict:
    return RelatedVerdict(tuple(_selection_from(item) for item in data["selections"]),
                          tuple(SelectionResult(_selection_from(item["selection"]), False, str(item["tail"]))
                                for item in data["failures"]))


def verify_related_fresh(root: Path, session_logs: Sequence[Path], log_dir: Path) -> RelatedVerdict:
    """``verify_related`` in a new Python process, its output relayed line by line as it prints. A repair session
    may rewrite this very module (the planner); only a new process plans and judges with the code now on disk,
    so the repair that fixes the planner is the one the next round is judged by.

    Raises:
        AssistError: when the run could not be planned or took no package lock, or the process left no verdict.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    verdict_file = log_dir / VERDICT_FILE
    verdict_file.unlink(missing_ok=True)
    command = [sys.executable, "-m", MODULE, "--root", str(root), "--log-dir", str(log_dir),
               "--verdict-file", str(verdict_file)]
    for log in session_logs:
        command += ["--stream", str(log)]
    paths = [str(LIB_DIR), *filter(None, [os.environ.get("PYTHONPATH")])]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONUTF8": "1"}
    with subprocess.Popen(command, cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace") as process:
        if process.stdout is None:
            raise AssistError(f"{MODULE} was started without the stdout pipe this run reads.")
        for line in process.stdout:
            say(line.rstrip())
    if not verdict_file.is_file():
        raise AssistError(f"The related-run process exited {process.returncode} without a verdict ({verdict_file}); "
                          "its output is above.")
    data = json.loads(verdict_file.read_text(encoding="utf-8"))
    if "error" in data:
        raise AssistError(str(data["error"]))
    return _verdict_from(data)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the new process ``verify_related_fresh`` starts: plan and run, write the verdict as JSON."""
    parser = argparse.ArgumentParser(description="Run the tests related to the files fix sessions wrote.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--verdict-file", type=Path, required=True)
    parser.add_argument("--stream", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        data = _verdict_data(verify_related(args.root, args.stream, args.log_dir))
    except AssistError as exc:
        data = {"error": str(exc)}
    args.verdict_file.write_text(json.dumps(data), encoding="utf-8")
    return 0


def repair_prompt(verdict: RelatedVerdict) -> str:
    """What the fix session is told when related runs fail: the runs, their output, and that closing needs them green."""
    lines = ["After your fix, the script ran the tests related to the files you wrote, and these did not pass. "
             "The script keeps resuming this session until they all pass; only a B1-B4 blocker you prove ends it.",
             "The finding is deleted only when every one of them passes, so make them pass: find each root cause "
             "(a failing test may assert the behaviour you changed, or fail on output your change now produces) "
             "and fix it there, in the package that owns it. Run only the failing selections again, in the "
             "foreground, and end with the usual 'Finding fix:' line. Work only the failures your change can "
             "have caused: a failing test whose traceback frames and named symbols never reach a file you wrote "
             "belongs to another agent's work in that suite. Do not investigate, fix or loosen it; write a "
             "findings file for it and reply 'Finding fix: BLOCKED B4' naming the failing ids and the frames that "
             "show your change is not in them.", ""]
    for result in verdict.failures:
        lines += [f"## {result.selection.describe()}", f"({result.selection.reason})", result.tail, ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
