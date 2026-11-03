"""Self-test checks of ``datrix_scripts.skill.related_tests``, run by ``implement-finding.ps1 -SelfTest``.

Each check builds a real (synthetic) workspace on disk and runs the module's own functions over it; the one
``test.ps1`` that runs is a small real PowerShell script standing in for the harness's, printing the closing
summary line the real one prints.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from datrix_scripts.affected_set import cross_ecosystem_config_path
from datrix_scripts.gate_harness import write_files
from datrix_scripts.skill.common import AssistError
from datrix_scripts.skill.related_parallel import XDIST_WORKERS_ENV, run_units
from datrix_scripts.skill.related_references import MAX_TESTS_PER_NAME, code_names
from datrix_scripts.skill.related_tests import (
    LOCK_MESSAGE,
    RelatedVerdict,
    Selection,
    SelectionResult,
    plan_related,
    repair_prompt,
    run_selection,
    written_changes,
    written_paths,
)

_PASSING_TEST = 'def test_ok() -> None:\n    assert True\n'


def write_workspace(root: Path) -> None:
    """Four packages (lib, plug, host, other), each with a unit test, and the stub venv script the install check runs."""
    manifest = '[project]\nname = "{name}"\ndependencies = []\n'
    files = {}
    for name in ("lib", "plug", "host", "other"):
        files[f"datrix-{name}/pyproject.toml"] = manifest.format(name=f"datrix-{name}")
        files[f"datrix-{name}/src/datrix_{name}/__init__.py"] = "VALUE = 1\n"
        files[f"datrix-{name}/tests/unit/test_{name}.py"] = _PASSING_TEST
    write_files(root, files)
    config = cross_ecosystem_config_path(root)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"dependencies": {}}), encoding="utf-8")
    write_files(root, {"datrix/scripts/common/venv.ps1": "exit 0\n"})


def tool_use_line(name: str, tool_input: dict[str, object]) -> str:
    """One stream-log line: an assistant message holding a single tool call."""
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name,
                                                                       "input": tool_input}]}})


def write_stub_harness(root: Path, body: str) -> None:
    """Replace the workspace's ``test.ps1`` with a small real PowerShell script."""
    script = root / "datrix" / "scripts" / "test" / "test.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")


def check_written_paths_come_from_every_editing_tool() -> None:
    with TemporaryDirectory() as raw:
        log = Path(raw) / "step.stream.jsonl"
        log.write_text("\n".join([
            tool_use_line("Edit", {"file_path": "a.py", "old_string": "gone_name", "new_string": "kept_name"}),
            tool_use_line("Write", {"file_path": "b.py"}),
            tool_use_line("mcp__datrix-edit__edit_lines", {"edits": [{"file_path": "c.py", "text": "typed_name"},
                                                                     {"file_path": "d.py"}]}),
            tool_use_line("Read", {"file_path": "never.py"}),
            "not json",
        ]), encoding="utf-8")
        assert written_paths(log) == [Path("a.py"), Path("b.py"), Path("c.py"), Path("d.py")]
        changes = written_changes(log)
        assert changes[Path("a.py").resolve()] == ["gone_name", "kept_name"], changes
        assert changes[Path("b.py").resolve()] == [None] and changes[Path("c.py").resolve()] == ["typed_name"], changes
        try:
            written_paths(Path(raw) / "absent.jsonl")
        except AssistError:
            return
    raise AssertionError("a missing session log must be refused")


def check_a_name_is_code_shaped_and_one_name_in_both_spellings() -> None:
    names = code_names(["app_user = AppUser(appUser)\nplain words and a_b and Duration and thing"])
    assert set(names) == {"appuser"}, names
    assert set(code_names(["RdbmsConfig and dbConfig"])) == {"rdbmsconfig", "dbconfig"}


def _named_by(root: Path, files: dict[str, str], edited_text: str) -> list[tuple[str, tuple[str, ...]]]:
    """The plan for a session that edited datrix-lib's source and its test and typed *edited_text* into the source."""
    write_files(root, files)
    source = root / "datrix-lib" / "src" / "datrix_lib" / "__init__.py"
    lib_test = root / "datrix-lib" / "tests" / "unit" / "test_lib.py"
    plan = plan_related(root, [source, lib_test], {source.resolve(): [edited_text]})
    return [(s.package, s.specific) for s in plan]


def check_the_plan_is_the_written_tests_and_the_tests_that_name_the_change() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        plan = _named_by(root, {
            "datrix-plug/tests/unit/test_names_it.py": "def test_x() -> None:\n    assert 'app_user'\n",
            "datrix-host/tests/unit/test_camel.py": "def test_y() -> None:\n    assert 'appUser'\n",
            "datrix-other/tests/unit/test_other.py": _PASSING_TEST,
        }, "removed the app_user field")
        assert plan == [
            ("datrix-lib", ("tests/unit/test_lib.py",)),
            ("datrix-host", ("tests/unit/test_camel.py",)),
            ("datrix-plug", ("tests/unit/test_names_it.py",)),
        ], plan
        other = root / "datrix-other" / "src" / "datrix_other" / "__init__.py"
        assert plan_related(root, [other, root / "datrix-other" / "README.md", root / "elsewhere.py"]) == ()


def check_a_name_many_tests_mention_selects_none_and_written_tests_are_not_repeated() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        crowd = {f"datrix-plug/tests/unit/test_crowd_{n}.py": "NAME = 'common_name'\n" for n in range(MAX_TESTS_PER_NAME + 1)}
        crowd["datrix-lib/tests/unit/test_lib.py"] = "NAME = 'app_user'\n"
        plan = _named_by(root, crowd, "common_name and app_user")
        assert plan == [("datrix-lib", ("tests/unit/test_lib.py",))], plan


def check_a_run_passes_only_on_exit_code_and_summary_and_a_lost_lock_is_refused() -> None:
    selection = Selection("datrix-lib", ("tests/unit/test_lib.py",), "check")
    with TemporaryDirectory() as raw:
        root = Path(raw)
        log = root / "run.log"
        write_stub_harness(root, "Write-Output 'Total: 1 | Passed: 1 | Failed: 0'\nexit 0\n")
        assert run_selection(root, selection, log).passed
        write_stub_harness(root, "Write-Output 'Total: 1 | Passed: 0 | Failed: 1'\nexit 1\n")
        assert not run_selection(root, selection, log).passed
        write_stub_harness(root, "Write-Output 'collected nothing'\nexit 0\n")
        assert not run_selection(root, selection, log).passed, "no closing summary line is no proof"
        write_stub_harness(root, f"Write-Output '{LOCK_MESSAGE}'\nexit 1\n")
        try:
            run_selection(root, selection, log)
        except AssistError:
            return
    raise AssertionError("a run that never took the package lock must be refused, not reported as failing tests")


def check_the_repair_prompt_names_each_failing_run_and_its_output() -> None:
    failing = SelectionResult(Selection("datrix-cli", ("tests/unit/test_a.py",), "tests that name 'x_y'"), False,
                              "E   A002 found")
    prompt = repair_prompt(RelatedVerdict((failing.selection,), (failing,)))
    assert "test.ps1 datrix-cli -Specific tests/unit/test_a.py" in prompt and "E   A002 found" in prompt, prompt


def _span_of_unit(directory: Path, package: str) -> list[tuple[int, int]]:
    """The (start, end) ticks each stub run of *package* recorded, earliest first."""
    spans = []
    for record in directory.glob(f"span-{package}-*.txt"):
        start, end = record.read_text(encoding="utf-8").split()
        spans.append((int(start), int(end)))
    return sorted(spans)


def check_packages_run_side_by_side_and_one_packages_runs_never_overlap() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_stub_harness(root, "$start = (Get-Date).Ticks\nStart-Sleep -Milliseconds 1500\n"
                                 "$end = (Get-Date).Ticks\n"
                                 "Set-Content -Path \"$PSScriptRoot/span-$($args[0])-$([guid]::NewGuid()).txt\" "
                                 "-Value \"$start $end\"\n"
                                 "Write-Output 'Total: 1 | Passed: 1 | Failed: 0'\nexit 0\n")
        selections = [Selection("alpha", ("tests/a.py",), "check"), Selection("beta", ("tests/b.py",), "check"),
                      Selection("alpha", ("tests/c.py",), "check")]
        logs = root / "logs"
        logs.mkdir()

        def run_one(number: int, environment: dict[str, str]) -> SelectionResult:
            assert environment[XDIST_WORKERS_ENV] == "2", environment
            return run_selection(root, selections[number - 1], logs / f"{number}.log", environment)

        results = run_units([(s.package, n) for n, s in enumerate(selections, start=1)], run_one,
                            {"alpha": 2, "beta": 2}, 4)
        assert [results[n].passed for n in (1, 2, 3)] == [True, True, True], results
        directory = root / "datrix" / "scripts" / "test"
        alpha, beta = _span_of_unit(directory, "alpha"), _span_of_unit(directory, "beta")
        assert len(alpha) == 2 and len(beta) == 1, (alpha, beta)
        assert alpha[0][1] <= alpha[1][0], f"one package's runs must not overlap: {alpha}"
        assert min(alpha[0][1], beta[0][1]) > max(alpha[0][0], beta[0][0]), f"packages must overlap: {alpha} {beta}"
        # Workers beyond the cores are never admitted together: allotments 3 + 3 > 4 cores run one package at a time.
        serial = run_units([("alpha", 1), ("beta", 2)], lambda number, _: number, {"alpha": 3, "beta": 3}, 4)
        assert serial == {1: 1, 2: 2}, serial


CHECKS = (
    check_packages_run_side_by_side_and_one_packages_runs_never_overlap,
    check_written_paths_come_from_every_editing_tool,
    check_a_name_is_code_shaped_and_one_name_in_both_spellings,
    check_the_plan_is_the_written_tests_and_the_tests_that_name_the_change,
    check_a_name_many_tests_mention_selects_none_and_written_tests_are_not_repeated,
    check_a_run_passes_only_on_exit_code_and_summary_and_a_lost_lock_is_refused,
    check_the_repair_prompt_names_each_failing_run_and_its_output,
)
