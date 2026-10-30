"""The related-suites half of /implement-finding: which tests a fix must leave green, and running them.

A fix session proves its own change; it does not prove the packages that depend on it. This module
derives, from the files a session wrote and from nothing a model reports, the targeted test
selections that must pass before ``implement-finding.ps1`` deletes a finding, and runs them. Never a
whole suite: every selection is a ``test.ps1`` targeted form (``-Specific`` files or directories, or
``-Tag``), the forms the rest of the harness already allows.

THE SELECTIONS
    Edited tests
        Each test file the session wrote or changed, in its own package.
    Feature tags
        The tags those tests carry (read from their ``pytest.mark.tag(...)`` calls), run in every
        package of the edited packages' affected closure (``datrix_scripts.affected_set``) that has a
        test carrying one -- the way ``feature-tags.md`` says a change is verified across the
        packages it reaches. Three tags per run.
    End-to-end tier
        A package that declares a ``datrix.*`` entry point is a plugin: the generation pipeline runs
        it without importing it, so no import closure reaches the tests that run it. When an edit
        lands in a plugin package, or in a package a plugin package depends on, the ``tests/e2e``
        tier of the package that owns ``GenerationPipeline`` and of each edited package is selected.

Exit semantics live in the caller (``implement_finding``); this module only plans, runs and reports.
"""

from __future__ import annotations

import ast
import json
import logging
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.affected_set import build_workspace_graphs, compute_affected_closures, discover_packages
from datrix_scripts.skill.chain import event_blocks
from datrix_scripts.skill.common import AssistError, read_text
from datrix_scripts.skill.finding_inbox import summaries_passed

LOG = logging.getLogger(__name__)

TEST_SCRIPT_PARTS: Final = ("datrix", "scripts", "test", "test.ps1")
SOURCE_DIRNAME: Final = "src"
TESTS_DIRNAME: Final = "tests"
E2E_RELPATH: Final = "tests/e2e"
ENTRY_POINT_GROUP_PREFIX: Final = "datrix."
PIPELINE_CLASS: Final = "GenerationPipeline"
EDIT_TOOLS: Final = frozenset({"Edit", "Write"})
EDIT_LINES_SUFFIX: Final = "edit_lines"
TAGS_PER_RUN: Final = 3
RUN_TIMEOUT_SECONDS: Final = 3600
LOCK_MESSAGE: Final = "Could not acquire package lock"
LOCK_RETRIES: Final = 5
TAIL_LINES: Final = 40


@dataclass(frozen=True)
class Selection:
    """One targeted ``test.ps1`` run: the packages, and either ``specific`` paths (one package) or ``tags``."""

    packages: tuple[str, ...]
    specific: tuple[str, ...]
    tags: tuple[str, ...]
    reason: str

    def arguments(self) -> list[str]:
        """The ``test.ps1`` arguments after the script path."""
        if self.specific:
            return [*self.packages, "-Specific", ",".join(self.specific)]
        return [*self.packages, "-Tag", ",".join(self.tags)]

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


def written_paths(session_log: Path) -> list[Path]:
    """Every file the session wrote with ``Edit``, ``Write`` or ``edit_lines``, in order, from its stream log."""
    if not session_log.is_file():
        raise AssistError(f"Session log '{session_log}' does not exist. Pass the step's .stream.jsonl.")
    paths: list[Path] = []
    for event in _events(session_log):
        for block in event_blocks(event, "tool_use"):
            name = str(block.get("name", ""))
            tool_input = block.get("input")
            if not isinstance(tool_input, dict) or not (name in EDIT_TOOLS or name.endswith(EDIT_LINES_SUFFIX)):
                continue
            paths.extend(_input_paths(tool_input))
    return paths


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


def _is_tag_marker(function: ast.expr) -> bool:
    """``pytest.mark.tag`` or ``mark.tag``."""
    if not isinstance(function, ast.Attribute) or function.attr != "tag":
        return False
    owner = function.value
    return (isinstance(owner, ast.Attribute) and owner.attr == "mark") or (isinstance(owner, ast.Name) and owner.id == "mark")


def file_tags(path: Path) -> frozenset[str]:
    """The tags named by every ``tag`` marker in a Python test file (module, class, function and row level)."""
    tags: set[str] = set()
    for node in ast.walk(ast.parse(read_text(path), filename=str(path))):
        if isinstance(node, ast.Call) and _is_tag_marker(node.func):
            tags.update(arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return frozenset(tags)


def package_tags(package_dir: Path) -> frozenset[str]:
    """Every tag any test file of the package carries."""
    tags: set[str] = set()
    for path in sorted((package_dir / TESTS_DIRNAME).rglob("test_*.py")):
        tags |= file_tags(path)
    return frozenset(tags)


def plugin_packages(packages: dict[str, Path]) -> frozenset[str]:
    """Packages whose manifest declares an entry point in a ``datrix.*`` group."""
    plugins: set[str] = set()
    for name, directory in packages.items():
        manifest = directory / "pyproject.toml"
        if not manifest.is_file():
            continue
        groups = tomllib.loads(read_text(manifest)).get("project", {}).get("entry-points", {})
        if any(group.startswith(ENTRY_POINT_GROUP_PREFIX) for group in groups):
            plugins.add(name)
    return frozenset(plugins)


def pipeline_owner(packages: dict[str, Path]) -> str:
    """The one package whose ``src`` defines ``GenerationPipeline``."""
    owners = []
    for name, directory in packages.items():
        for path in (directory / SOURCE_DIRNAME).rglob("*.py"):
            text = read_text(path)
            if f"class {PIPELINE_CLASS}" in text and any(
                isinstance(node, ast.ClassDef) and node.name == PIPELINE_CLASS for node in ast.parse(text).body
            ):
                owners.append(name)
                break
    if len(owners) != 1:
        raise AssistError(f"Expected exactly one package defining {PIPELINE_CLASS}, found {sorted(owners)}. "
                          "The end-to-end tier cannot be selected without its owner.")
    return owners[0]


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


def plan_related(root: Path, written: Sequence[Path]) -> tuple[Selection, ...]:
    """The targeted runs the files in *written* require; empty when no package source or test was written."""
    packages = discover_packages(root)
    edits = classify_edits(root, packages, written)
    changed = sorted(set(edits.sources) | set(edits.tests))
    if not changed:
        return ()
    graphs = build_workspace_graphs(root)
    closures = compute_affected_closures(graphs.source_graph, graphs.test_graph, graphs.deferred_graph)
    scope = sorted({member for package in changed for member in closures[package]})
    selections = [Selection((package,), tuple(files), (), "tests the session wrote or changed")
                  for package, files in sorted(edits.tests.items())]
    tags = sorted({tag for package, files in edits.tests.items() for relative in files
                   for tag in file_tags(packages[package] / relative)})
    selections += _tag_selections(packages, scope, tags)
    selections += _e2e_selections(packages, scope, sorted(edits.sources))
    return tuple(selections)


def _tag_selections(packages: dict[str, Path], scope: Sequence[str], tags: Sequence[str]) -> list[Selection]:
    carried = {name: package_tags(packages[name]) for name in scope if (packages[name] / TESTS_DIRNAME).is_dir()}
    selections = []
    for start in range(0, len(tags), TAGS_PER_RUN):
        chunk = tuple(tags[start:start + TAGS_PER_RUN])
        reached = tuple(name for name, held in sorted(carried.items()) if held.intersection(chunk))
        if reached:
            selections.append(Selection(reached, (), chunk, "feature tags of the session's tests"))
    return selections


def _e2e_selections(packages: dict[str, Path], scope: Sequence[str], edited_sources: Sequence[str]) -> list[Selection]:
    if not set(scope) & plugin_packages(packages):
        return []
    owners = {pipeline_owner(packages), *edited_sources}
    return [Selection((name,), (E2E_RELPATH,), (), "end-to-end tier: the generation pipeline runs every plugin")
            for name in sorted(owners) if (packages[name] / E2E_RELPATH).is_dir()]


def run_selection(root: Path, selection: Selection, log: Path) -> SelectionResult:
    """Run one selection in the foreground, keep its full output in *log*, and judge it by test.ps1's own
    exit code and closing summary line. A run that lost the package lock to another run is repeated.

    Raises:
        AssistError: when every try lost the lock -- no test ran, so there is nothing for a session to repair.
    """
    script = root.joinpath(*TEST_SCRIPT_PARTS)
    output = ""
    for _ in range(LOCK_RETRIES):
        try:
            done = subprocess.run(["powershell", "-NoProfile", "-File", str(script), *selection.arguments()],
                                  cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=RUN_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            log.write_text(f"{selection.describe()}\ntimed out after {RUN_TIMEOUT_SECONDS} seconds\n", encoding="utf-8")
            return SelectionResult(selection, False, f"timed out after {RUN_TIMEOUT_SECONDS} seconds")
        output = done.stdout + done.stderr
        if LOCK_MESSAGE not in output:
            break
    log.write_text(f"{selection.describe()}\n{output}", encoding="utf-8")
    if LOCK_MESSAGE in output:
        raise AssistError(f"{selection.describe()} could not take the package lock in {LOCK_RETRIES} tries: another "
                          "test run holds it. Run the finding again when no other test run is active.")
    passed = done.returncode == 0 and summaries_passed(output)
    tail = "\n".join(output.splitlines()[-TAIL_LINES:])
    return SelectionResult(selection, passed, tail)


def verify_related(root: Path, session_logs: Sequence[Path], log_dir: Path) -> RelatedVerdict:
    """Plan the related selections from every file the session wrote and run them all, keeping each run's
    output under *log_dir*."""
    written = [path for log in session_logs for path in written_paths(log)]
    selections = plan_related(root, written)
    log_dir.mkdir(parents=True, exist_ok=True)
    results = [run_selection(root, selection, log_dir / f"related-{number:02d}.log")
               for number, selection in enumerate(selections, start=1)]
    return RelatedVerdict(selections, tuple(result for result in results if not result.passed))


def repair_prompt(verdict: RelatedVerdict) -> str:
    """What the fix session is told when related runs fail: the runs, their output, and that closing needs them green."""
    lines = ["After your fix, the script ran the tests related to the files you wrote, and these did not pass.",
             "The finding is deleted only when every one of them passes, so make them pass: find each root cause "
             "(a failing test may assert the behaviour you changed, or fail on output your change now produces) "
             "and fix it there, in the package that owns it. Run only the failing selections again, in the "
             "foreground, and end with the usual 'Finding fix:' line.", ""]
    for result in verdict.failures:
        lines += [f"## {result.selection.describe()}", f"({result.selection.reason})", result.tail, ""]
    return "\n".join(lines)
