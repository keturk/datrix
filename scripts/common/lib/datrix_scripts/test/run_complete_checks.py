"""Shared-library gate checks for ``run_complete`` (``test\\run-complete.ps1``).

Run by ``shared_library_gate.py``. Each check drives the real functions over planted inputs: the
test-summary parser over every summary format a runner prints, the step summary log, a real child
process through ``run_command`` in each of its output modes, the structured index a run's reports
produce, steps 3 and 4 over planted generated projects whose stub runners write real reports, and
the workflow's argument handling. Nothing here starts a container: the deploy checks stop below
step 4's pre-flight teardown of every datrix compose project, and a planted project carries no
compose file, so its own teardown has nothing to tear down.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Final

from datrix_codegen_kernel.generation.test_runner_entry_point import (
    TEST_RUNNER_ENTRY_POINT,
    ProjectTestRunner,
    build_test_runner_entry_point,
)

from datrix_scripts.gate_harness import CheckFunc, write_file, write_files
from datrix_scripts.registered_targets import registered_language_names
from datrix_scripts.test.run_complete import (
    _produce_structured_output,
    _run_deployment_tests,
    get_paths,
    main,
    parse_test_statistics,
    run_command,
    save_test_summary_log,
    step3_run_unit_tests,
)

_LANGUAGE: Final = "lang-x"
_PLATFORM: Final = "docker"
_TARGET: Final = ("lang-x", "docker", "local")
_TIMESTAMP: Final = "20000101-000000"
_UNIT_STUB: Final = ProjectTestRunner("python", PurePosixPath("tests/unit_report_stub.py"))
_DEPLOY_STUB: Final = ProjectTestRunner("python", PurePosixPath("tests/deploy_report_stub.py"))
_EXIT_SUFFIX: Final = ".exit"
_JUNIT_PASSED: Final = (
    '<testsuite name="api" tests="1" failures="0">'
    '<testcase classname="tests.test_api" name="test_ok" time="0.1"/></testsuite>'
)
_JUNIT_FAILED: Final = (
    '<testsuite name="api" tests="1" failures="1">'
    '<testcase classname="tests.test_api" name="test_ok" time="0.1">'
    '<failure message="boom">AssertionError: boom</failure></testcase></testsuite>'
)
# The unit stub writes its report the way a generated unit runner does: a fresh
# ``.test_results/unit-tests-*`` run directory under the project root, one JUnit report per
# service, and the summary lines the console parser reads.
_UNIT_REPORT_STUB: Final = (
    "import sys, time\n"
    "from pathlib import Path\n"
    f"code = int(Path(sys.argv[0] + {_EXIT_SUFFIX!r}).read_text(encoding='utf-8'))\n"
    "run = Path('.test_results') / ('unit-tests-' + str(time.time_ns())) / 'services' / 'api'\n"
    "run.mkdir(parents=True)\n"
    f"report = {_JUNIT_PASSED!r} if code == 0 else {_JUNIT_FAILED!r}\n"
    "(run / 'junit.xml').write_text(report, encoding='utf-8')\n"
    "print('Total Passed: ' + str(1 - min(code, 1)))\n"
    "print('Total Failed: ' + str(min(code, 1)))\n"
    "sys.exit(code)\n"
)
_DEPLOY_REPORT_STUB: Final = (
    "import sys\n"
    "from pathlib import Path\n"
    f"code = int(Path(sys.argv[0] + {_EXIT_SUFFIX!r}).read_text(encoding='utf-8'))\n"
    "print('Total Passed: 2')\n"
    "print('Total Failed: ' + str(min(code, 1)))\n"
    "sys.exit(code)\n"
)
_ANSI_RED: Final = "\x1b[31m"
_ANSI_RESET: Final = "\x1b[0m"
_PROBE_VARIABLE: Final = "RUN_COMPLETE_CHECK_PROBE"
_RULE: Final = "=" * 60


def _real_example() -> str:
    """An example under ``datrix/examples`` (its path there), so a planted project's metadata resolves."""
    examples = get_paths()["datrix_root"] / "datrix" / "examples"
    sources = sorted(examples.rglob("system.dtrx"))
    assert sources, f"no example system.dtrx under {examples}: the structured-output checks need one"
    return sources[0].parent.relative_to(examples).as_posix()


def _plant_project(project: Path, *, exit_code: int, with_deploy: bool) -> Path:
    """A generated project whose entry point runs the report-writing stubs, exiting ``exit_code``."""
    entry_point = build_test_runner_entry_point(unit=_UNIT_STUB, deploy=_DEPLOY_STUB if with_deploy else None)
    files = {str(TEST_RUNNER_ENTRY_POINT): entry_point.content}
    for stub, program in ((_UNIT_STUB, _UNIT_REPORT_STUB), (_DEPLOY_STUB, _DEPLOY_REPORT_STUB)):
        files[str(stub.script)] = program
        files[f"{stub.script}{_EXIT_SUFFIX}"] = str(exit_code)
    write_files(project, files)
    return project


def _paths_under(root: Path) -> dict[str, Path]:
    """``get_paths()`` re-rooted at ``root``: steps 3 and 4 read and write only beneath it."""
    return {**get_paths(), "datrix_root": root, "datrix_dir": root / "datrix"}


def check_run_complete_reads_every_test_summary_format() -> None:
    """The console parser reads a summary-block run, pytest summary lines (summed, only on lines
    opening with ``=``), and Jest's ``Tests:``/``Test Suites:`` lines, where a suite that failed
    before any test ran is an error and its count stays apart in ``suiteFailures``."""
    cases = {
        "": (0, 0, 0, 0, 0),
        "Total Passed: 35\nTotal Failed: 2\nTotal Errors: 1\nTotal Skipped: 4": (35, 2, 1, 4, 0),
        "===== 3 passed, 1 failed, 2 skipped, 1 error in 8.48s =====\n== 2 passed in 1.0s ==": (5, 1, 1, 2, 0),
        "Total Passed: 0\n=== 5 passed in 1.2s ===": (5, 0, 0, 0, 0),
        "3 passed in 1.0s": (0, 0, 0, 0, 0),
        "Test Suites: 1 failed, 2 passed, 3 total\nTests:       4 failed, 10 passed, 1 skipped, 15 total": (
            10, 4, 0, 1, 1,
        ),
        "Test Suites: 2 failed, 2 total\nTests:       0 total": (0, 0, 2, 0, 2),
        "Test Suites: 1 failed, 1 total": (0, 0, 1, 0, 1),
    }
    for output, expected in cases.items():
        stats = parse_test_statistics(output)
        got = (stats["passed"], stats["failed"], stats["errors"], stats["skipped"], stats["suiteFailures"])
        assert got == expected, f"parse_test_statistics({output!r}) read {got}, expected {expected}"


def check_run_complete_summary_log_lists_each_project_under_its_outcome() -> None:
    """The step summary log carries the totals, each project under its outcome with only its non-zero
    counts, and -- for a deploy run -- the failure index of the run's ``failures.json``; a unit step's
    log is named for the step under ``.generated/.test_results``."""
    results = [
        {"name": "alpha", "success": True, "passed": 3, "failed": 0, "errors": 0, "skipped": 1},
        {"name": "beta", "success": True, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
        {"name": "gamma", "success": False, "passed": 0, "failed": 2, "errors": 1, "skipped": 0},
    ]
    failure = {"service": "api", "fullName": "Suite > case", "testFilePath": "tests/a.spec.ts", "line": 12,
               "message": "boom\nsecond line"}
    with TemporaryDirectory(prefix="run-complete-summary-") as tmp:
        root = Path(tmp)
        deploy_dir = root / "deploy-run"
        write_file(deploy_dir / "failures.json", json.dumps({"failures": [failure]}))
        log = save_test_summary_log(5, "Deploy Tests", _paths_under(root), results, 3, 2, 1, 3, 2, 1, 1,
                                    step5_output_dir=deploy_dir)
        assert log == deploy_dir / "deploy-test-summary.log", f"a deploy run's summary went to {log}"
        lines = log.read_text(encoding="utf-8").splitlines()
        assert lines[3].startswith("Timestamp: "), f"line 4 is not the timestamp: {lines[3]!r}"
        expected = [
            _RULE, "STEP 5 SUMMARY: Deploy Tests", _RULE, "",
            "Total Projects Tested: 3", " Successful Projects: 2", " Failed Projects: 1", "",
            "Total Tests:", " Passed: 3", " Failed: 2", " Errors: 1", " Skipped: 1", "",
            "Per-Project Breakdown:", "-" * 60, "",
            "Successful Projects (2):", " ✓ alpha", "   Tests: passed: 3, skipped: 1", " ✓ beta", "",
            "Failed Projects (1):", " ✗ gamma", "   Tests: failed: 2, errors: 1", "",
            _RULE, "", _RULE, "Failure index (from failures.json)", _RULE,
            "- [api] Suite > case", "    file: tests/a.spec.ts:12", "    message: boom",
        ]
        assert lines[:3] + lines[4:] == expected, "the summary log differs:\n" + "\n".join(lines)

        unit_log = save_test_summary_log(3, "Unit Tests", _paths_under(root), [], 0, 0, 0, 0, 0, 0, 0)
        assert unit_log.parent == root / ".generated" / ".test_results", f"a unit step's log went to {unit_log}"
        assert unit_log.name.startswith("step3-unit-tests-") and unit_log.suffix == ".log", unit_log.name
        unit_text = unit_log.read_text(encoding="utf-8")
        assert "Projects (" not in unit_text, f"an empty step listed a project group:\n{unit_text}"


def check_run_complete_run_command_reports_the_child_exit_and_output() -> None:
    """``run_command`` reports the child's exit as success or failure in every mode: capturing, it
    returns the child's lines (its environment carrying ``env_overrides``); teeing to a log, it
    appends the output with ANSI colour stripped and returns no output; otherwise it returns none."""
    python = sys.executable
    show = f"import os; print('one'); print(os.environ.get({_PROBE_VARIABLE!r}, 'unset'))"
    captured = run_command([python, "-c", show], capture_output=True, env_overrides={_PROBE_VARIABLE: "seen"})
    assert captured == (True, "one\nseen"), f"a captured passing child returned {captured}"
    failed = run_command([python, "-c", "import sys; print('x'); sys.exit(3)"], capture_output=True)
    assert failed == (False, "x"), f"a captured failing child returned {failed}"
    with TemporaryDirectory(prefix="run-complete-tee-") as tmp:
        log = write_file(Path(tmp) / "run.log", "before\n")
        colour = f"print({_ANSI_RED + 'red' + _ANSI_RESET!r}); print('plain')"
        teed = run_command([python, "-c", colour], log_file=log)
        assert teed == (True, None), f"a teed passing child returned {teed}"
        assert log.read_text(encoding="utf-8") == "before\nred\nplain\n", repr(log.read_text(encoding="utf-8"))
        teed_failure = run_command([python, "-c", "import sys; sys.exit(4)"], log_file=log)
        assert teed_failure == (False, None), f"a teed failing child returned {teed_failure}"
    assert run_command([python, "-c", "pass"]) == (True, None), "a plain passing child must succeed"
    assert run_command([python, "-c", "import sys; sys.exit(2)"]) == (False, None), "a plain failing child"


def _index(path: Path | None) -> dict[str, object]:
    assert path is not None, "no index.json was written"
    return json.loads(path.read_text(encoding="utf-8"))


def _service_results(index: dict[str, object]) -> dict[str, str]:
    services = index["services"]
    assert isinstance(services, list), f"index services is not a list: {services!r}"
    return {str(service["name"]): str(service["result"]) for service in services}


def check_run_complete_indexes_every_service_a_run_reported() -> None:
    """The structured index covers every service of a run: a ``services/<name>/`` report is read, a
    service with no report or an unreadable one is recorded FAILED, the top-level ``<name>/`` layout
    counts a directory only beside its ``<name>-unit-tests.log``, and a run with nothing yields none."""
    with TemporaryDirectory(prefix="run-complete-index-") as tmp:
        project = Path(tmp).joinpath(*_TARGET, _real_example())
        empty = project / ".test_results" / "unit-tests-empty"
        empty.mkdir(parents=True)
        assert _produce_structured_output(project, Path(tmp), _LANGUAGE, _PLATFORM, empty, 0.0) is None, (
            "a run directory holding no service must yield no index"
        )

        nested = project / ".test_results" / "unit-tests-nested"
        write_files(nested / "services", {
            "api/junit.xml": _JUNIT_PASSED,
            "broken/junit.xml": "not xml",
            "web/service.log": "tsc failed\n",
        })
        index = _index(_produce_structured_output(project, Path(tmp), _LANGUAGE, _PLATFORM, nested, 1.5))
        assert _service_results(index) == {"api": "PASSED", "broken": "FAILED", "web": "FAILED"}, index["services"]
        assert index["result"] == "FAILED" and index["language"] == _LANGUAGE, (index["result"], index["language"])

        flat = project / ".test_results" / "unit-tests-flat"
        write_files(flat, {
            "catalog/console.txt": "tsc failed\n",
            "catalog-unit-tests.log": "build failed\n",
            "stray/notes.txt": "not a service\n",
        })
        flat_index = _index(_produce_structured_output(project, Path(tmp), _LANGUAGE, _PLATFORM, flat, 0.0))
        assert _service_results(flat_index) == {"catalog": "FAILED"}, flat_index["services"]


def _summary_logs(root: Path, step: int) -> list[Path]:
    return sorted((root / ".generated" / ".test_results").glob(f"step{step}-*.log"))


def check_run_complete_step3_runs_every_project_and_indexes_their_reports() -> None:
    """Step 3 over a whole generated tree runs each project, logs the step summary, writes an
    aggregate over the projects' indexes and fails when any project failed; for one project it
    reports that project's verdict, and a missing or unnamed project fails the step."""
    example = _real_example()
    with TemporaryDirectory(prefix="run-complete-step3-") as tmp:
        root = Path(tmp)
        generated = root / ".generated"
        passing = _plant_project(generated.joinpath(*_TARGET, example), exit_code=0, with_deploy=False)
        paths = _paths_under(root)
        assert step3_run_unit_tests(True, paths, language=_LANGUAGE) is True, "a passing tree must pass step 3"
        assert len(_summary_logs(root, 3)) == 1, f"step 3 wrote {_summary_logs(root, 3)}"
        aggregates = sorted((generated / ".test_results").glob("unit-tests-*"))
        assert len(aggregates) == 1 and any(aggregates[0].iterdir()), f"no aggregate output: {aggregates}"

        failing = _plant_project(generated.joinpath("lang-y", "docker", "local", example), exit_code=1,
                                 with_deploy=False)
        assert step3_run_unit_tests(True, paths, language=_LANGUAGE) is False, "a failing project must fail step 3"

        assert step3_run_unit_tests(False, paths, output_path=str(passing), language=_LANGUAGE) is True
        assert step3_run_unit_tests(False, paths, output_path=str(failing), language=_LANGUAGE) is False
        assert step3_run_unit_tests(False, paths, output_path=str(root / "absent")) is False
        assert step3_run_unit_tests(False, paths) is False, "single-project mode without a project must fail"

    with TemporaryDirectory(prefix="run-complete-step3-empty-") as tmp:
        assert step3_run_unit_tests(True, _paths_under(Path(tmp))) is True, "an empty tree has nothing to fail"


def check_run_complete_step4_runs_each_deploy_project_once() -> None:
    """Step 4 (below its pre-flight teardown) over a whole tree runs only the projects whose entry
    point declares ``-Deploy`` and fails when any failed; for one project it reports that project's
    verdict, passes a project with no deploy tests, and fails a missing or unnamed project."""
    example = _real_example()
    with TemporaryDirectory(prefix="run-complete-step4-") as tmp:
        root = Path(tmp)
        generated = root / ".generated"
        passing = _plant_project(generated.joinpath(*_TARGET, example), exit_code=0, with_deploy=True)
        unit_only = _plant_project(generated.joinpath("lang-y", "docker", "local", example), exit_code=1,
                                   with_deploy=False)
        paths = _paths_under(root)
        assert _run_deployment_tests(True, paths, None, None, _LANGUAGE, _PLATFORM, False, _TIMESTAMP) is True
        assert len(_summary_logs(root, 4)) == 1, f"step 4 wrote {_summary_logs(root, 4)}"
        assert (passing / ".test_results" / f"deploy-test-{_TIMESTAMP}" / "deploy-test-summary.log").is_file()
        assert not (unit_only / ".test_results").exists(), "a project without -Deploy was run by step 4"

        failing = _plant_project(generated.joinpath("lang-z", "docker", "local", example), exit_code=1,
                                 with_deploy=True)
        assert _run_deployment_tests(True, paths, None, None, _LANGUAGE, _PLATFORM, False, _TIMESTAMP) is False

        def single(project: Path | None) -> bool:
            output_path = None if project is None else str(project)
            return _run_deployment_tests(False, paths, output_path, None, _LANGUAGE, _PLATFORM, False, _TIMESTAMP)

        assert single(passing) is True and single(failing) is False, "one project's verdict is the step's"
        assert single(unit_only) is True, "a project with no deploy tests has nothing to fail"
        assert single(root / "absent") is False and single(None) is False, "a missing project must fail"


def check_run_complete_workflow_skips_each_requested_step() -> None:
    """The workflow runs no step it was told to skip and then succeeds; it refuses a request with no
    language, or a single-example request with no example (exit 1), and an example whose output path
    cannot be derived is a usage error (exit 2)."""
    language = f"--language={sorted(registered_language_names())[0]}"
    skipped = ["--all", language, "--skip1", "--skip2", "--skip3", "--skip4", "--skip5"]
    assert main(skipped) == 0, "a workflow with every step skipped must succeed"
    assert main([]) == 1, "a request without --language must be refused with exit 1"
    assert main([language]) == 1, "a single-example request without an example must be refused with exit 1"
    with TemporaryDirectory() as raw:
        outside_examples = str(Path(raw) / "system.dtrx")
        assert main([outside_examples, language]) == 2, "an example outside examples/ must be a usage error"


def checks() -> list[CheckFunc]:
    """Every check of this module, in run order."""
    return [
        check_run_complete_reads_every_test_summary_format,
        check_run_complete_summary_log_lists_each_project_under_its_outcome,
        check_run_complete_run_command_reports_the_child_exit_and_output,
        check_run_complete_indexes_every_service_a_run_reported,
        check_run_complete_step3_runs_every_project_and_indexes_their_reports,
        check_run_complete_step4_runs_each_deploy_project_once,
        check_run_complete_workflow_skips_each_requested_step,
    ]
