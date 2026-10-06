#!/usr/bin/env python3
"""Repo-level gate absorbing the pytest coverage of ``datrix_scripts.runner_plugin``.

Run through ``test/runner-plugin-gate.ps1``. ``runner_plugin.py`` lives in the shared scripts
package (``scripts/common/lib/datrix_scripts/``) because the module's only consumer is the
shared test runner, which lives in this repo;
it is not part of any installable package's test support. Its original
unit test (``datrix-common/tests/unit/testing/test_runner_plugin.py``) used
pytest's own ``pytester`` fixture to run real, separately-collected pytest
sessions in-process -- a technique that only exists inside a pytest
collection run. The datrix showcase repo hosts no test suite of any kind
(``repo-boundaries.md``), so that file cannot simply move here as a
``test_*.py`` pytest module; it is re-expressed as a plain-Python gate,
following the same shape ``shared_library_gate.py`` uses for the same
boundary. Every behavior check below spawns a REAL, separate pytest process
(``python -m pytest -p datrix_scripts.runner_plugin ...``) against a temporary fixture
suite and inspects the record files it writes -- the out-of-process
equivalent of ``pytester.runpytest_inprocess``.

Behavior classes covered (see the deleted pytest file for the exhaustive
parametrization this narrows from):

- records never leak file contents, environment values, or CLI arguments;
- records hold exactly the observed/deselected/timings facts a session
  produced, with paths confined to the workspace and transient paths excluded;
- a missing or malformed required environment variable is a usage error that
  names it, and leaves no record;
- records are named for the worker (``main``, or the real ``PYTEST_XDIST_WORKER``
  id under a genuine distributed ``-n`` run), and a distributed controller
  leaves ``observed-controller.json`` / ``workers-controller.json`` naming
  every worker it ran;
- an existing record file is never overwritten;
- ``transient_roots`` / ``_PathScope`` (pure functions, called directly).

Intentionally NOT ported: the two overhead-ratio performance benchmarks
(``test_the_plugin_changes_no_outcome`` /
``test_the_plugin_costs_at_most_five_percent``, a 4000-test-suite timing
comparison) and the internal ``_dispatch``-with-a-malformed-payload edge case
(``test_an_operation_the_recorder_cannot_interpret_...``), which drove the
recorder's hooks directly through ``pytester.parseconfigure`` -- a technique
with no out-of-process equivalent and no real caller ever supplies a payload
shaped that way. Both are correctness-adjacent but not required to prove the
plugin's observable contract; a performance regression is a design-sized
follow-up, not this gate's job.

Harness convention: same as ``shared_library_gate.py`` -- each ``check_*``
takes no arguments, does its own setup, and raises ``AssertionError`` on
failure. ``run_checks`` catches only ``AssertionError``.

Exit codes: 0 = every check passed, 1 = at least one check failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from datrix_scripts import runner_plugin
from datrix_scripts.paths import script_env
from datrix_scripts.venv import get_venv_python

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"

_PLUGIN = runner_plugin.__name__
_RUN_DIR = "DATRIX_RUN_DIR"
_SUITE_CONE = "DATRIX_SUITE_CONE"
_WORKSPACE_ROOT = "DATRIX_WORKSPACE_ROOT"
_XDIST_WORKER = "PYTEST_XDIST_WORKER"
_RECORD_KINDS = ("observed", "deselected", "timings")

_SENTINEL_FILE_CONTENT = "runner-plugin-sentinel-file-content-must-never-leak"
_SENTINEL_ENV_VALUE = "runner-plugin-sentinel-env-value-must-never-leak"
_SENTINEL_ARGUMENT = "runner-plugin-sentinel-argument-must-never-leak"

_INI = """
[pytest]
markers =
    excluded: deselected by -m for the deselected-count check
"""

_FACTS_SUITE = f"""
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


def test_reads_a_file():
    assert (DATA / "read.txt").read_text(encoding="utf-8") == {_SENTINEL_FILE_CONTENT!r}
    os.environ["RUNNER_PLUGIN_SENTINEL"] = {_SENTINEL_ENV_VALUE!r}


def test_lists_and_globs():
    assert [p.name for p in (DATA / "listed").iterdir()] == ["member.txt"]
    assert glob.glob("*.txt", root_dir=DATA / "globbed") == ["member.txt"]


def test_copies_a_file(tmp_path):
    shutil.copy2(DATA / "copied.txt", tmp_path / "copy.txt")


def test_spawns_a_subprocess():
    environment = dict(os.environ, RUNNER_PLUGIN_CHILD_SENTINEL={_SENTINEL_ENV_VALUE!r})
    subprocess.run(
        [sys.executable, "-c", "pass", {_SENTINEL_ARGUMENT!r}], check=True, env=environment
    )


@pytest.mark.excluded
def test_deselected_one():
    assert True


@pytest.mark.excluded
def test_deselected_two():
    assert True
"""

_FACTS_SUITE_EXECUTED = 4
_FACTS_SUITE_DESELECTED = 2

_TRIVIAL_SUITE = "def test_ok():\n    assert True\n"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    """Run every check, catching only AssertionError. Returns True iff all passed."""
    all_passed = True
    for check in checks:
        name = check.__name__
        try:
            check()
        except AssertionError as exc:
            _fail(f"{name}: {exc}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


# ===========================================================================
# Fixture-workspace plumbing (out-of-process equivalent of pytester)
# ===========================================================================


class _Workspace:
    """A temporary pytest workspace with the recorder's environment set."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="runner-plugin-gate-")
        self.root = Path(os.path.realpath(self._tmp.name))
        self.data = self.root / "data"
        self.data.mkdir()
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()

    def close(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def env(self, **overrides: str) -> dict[str, str]:
        environment = script_env()
        environment[_RUN_DIR] = str(self.run_dir)
        environment[_WORKSPACE_ROOT] = str(self.root)
        environment[_SUITE_CONE] = str(self.root)
        environment.pop(_XDIST_WORKER, None)
        environment.update(overrides)
        return environment

    def record_names(self) -> list[str]:
        return sorted(path.name for path in self.run_dir.iterdir())

    def read_record(self, name: str) -> dict[str, object]:
        return json.loads((self.run_dir / name).read_text(encoding="utf-8"))


def _run_pytest(
    workspace: _Workspace, *args: str, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    python_exe = str(get_venv_python())
    command = [python_exe, "-m", "pytest", *args]
    return subprocess.run(
        command,
        cwd=workspace.root,
        env=workspace.env(**(env_overrides or {})),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _write_facts_workspace(workspace: _Workspace) -> None:
    workspace.write("pytest.ini", _INI)
    workspace.write("test_suite.py", _FACTS_SUITE)
    (workspace.data / "read.txt").write_text(_SENTINEL_FILE_CONTENT, encoding="utf-8")
    (workspace.data / "copied.txt").write_text("copied", encoding="utf-8")
    for name in ("listed", "globbed"):
        (workspace.data / name).mkdir()
        (workspace.data / name / "member.txt").write_text(name, encoding="utf-8")


def _run_facts_suite(workspace: _Workspace) -> subprocess.CompletedProcess[str]:
    _write_facts_workspace(workspace)
    result = _run_pytest(workspace, "-p", _PLUGIN, "-m", "not excluded", "test_suite.py")
    assert result.returncode == 0, (
        f"facts suite did not pass: rc={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    return result


# ===========================================================================
# Behavior checks
# ===========================================================================


def check_records_never_leak_sentinels() -> None:
    workspace = _Workspace()
    try:
        _run_facts_suite(workspace)
        for kind in _RECORD_KINDS:
            text = (workspace.run_dir / f"{kind}-main.json").read_text(encoding="utf-8")
            assert _SENTINEL_FILE_CONTENT not in text, f"{kind} record leaked file content"
            assert _SENTINEL_ENV_VALUE not in text, f"{kind} record leaked an env value"
            assert _SENTINEL_ARGUMENT not in text, f"{kind} record leaked a CLI argument"
    finally:
        workspace.close()


def check_records_hold_exact_facts() -> None:
    workspace = _Workspace()
    try:
        _run_facts_suite(workspace)
        assert workspace.record_names() == [
            "deselected-main.json",
            "observed-main.json",
            "timings-main.json",
        ], workspace.record_names()

        observed = workspace.read_record("observed-main.json")
        assert observed["schema"] == 1
        assert observed["worker"] == "main"
        opened = set(observed["opened"])
        listed = set(observed["listed"])
        data = workspace.data
        assert {str(data / "read.txt"), str(data / "copied.txt")} <= opened, opened
        assert {str(data / "listed"), str(data / "globbed")} <= listed, listed
        assert str(workspace.root / "test_suite.py") in opened

        deselected = workspace.read_record("deselected-main.json")
        assert deselected["deselected"] == _FACTS_SUITE_DESELECTED, deselected
        assert deselected["deselected_files"] == {"test_suite.py": _FACTS_SUITE_DESELECTED}, deselected

        timings = workspace.read_record("timings-main.json")
        calls = {call["nodeid"] for call in timings["calls"]}
        assert len(calls) == _FACTS_SUITE_EXECUTED, calls
    finally:
        workspace.close()


def check_missing_environment_variable_is_usage_error() -> None:
    for missing in (_RUN_DIR, _SUITE_CONE, _WORKSPACE_ROOT):
        workspace = _Workspace()
        try:
            workspace.write("test_suite.py", _TRIVIAL_SUITE)
            env = workspace.env()
            del env[missing]
            result = subprocess.run(
                [str(get_venv_python()), "-m", "pytest", "-p", _PLUGIN, "test_suite.py"],
                cwd=workspace.root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            assert result.returncode == 4, (  # pytest.ExitCode.USAGE_ERROR
                f"missing {missing}: expected exit 4, got {result.returncode}\n{result.stderr}"
            )
            assert f"{missing} is not set" in result.stderr, result.stderr
            assert workspace.record_names() == []
        finally:
            workspace.close()


def check_malformed_environment_variable_is_usage_error() -> None:
    workspace = _Workspace()
    try:
        workspace.write("test_suite.py", _TRIVIAL_SUITE)
        result = _run_pytest(
            workspace, "-p", _PLUGIN, "test_suite.py", env_overrides={_RUN_DIR: "relative-dir"}
        )
        assert result.returncode == 4, result.stderr
        assert "is not an absolute path" in result.stderr, result.stderr
        assert workspace.record_names() == []
    finally:
        workspace.close()


def check_worker_id_that_cannot_name_a_file_is_usage_error() -> None:
    workspace = _Workspace()
    try:
        workspace.write("test_suite.py", _TRIVIAL_SUITE)
        result = _run_pytest(
            workspace, "-p", _PLUGIN, "test_suite.py", env_overrides={_XDIST_WORKER: "../escaped"}
        )
        assert result.returncode == 4, result.stderr
        assert "cannot name a record file" in result.stderr, result.stderr
        assert workspace.record_names() == []
    finally:
        workspace.close()


def check_records_are_named_for_the_worker() -> None:
    for worker, expected in ((None, "main"), ("gw7", "gw7")):
        workspace = _Workspace()
        try:
            workspace.write("test_suite.py", _TRIVIAL_SUITE)
            overrides = {_XDIST_WORKER: worker} if worker is not None else {}
            result = _run_pytest(
                workspace, "-p", _PLUGIN, "test_suite.py", env_overrides=overrides
            )
            assert result.returncode == 0, result.stderr
            assert workspace.record_names() == sorted(
                f"{kind}-{expected}.json" for kind in _RECORD_KINDS
            ), workspace.record_names()
        finally:
            workspace.close()


def check_distributed_session_records_every_worker() -> None:
    worker_count = 2
    workspace = _Workspace()
    try:
        suite = "\n".join(
            f"def test_distributed_{i}():\n    assert True\n" for i in range(worker_count * 2)
        )
        workspace.write("test_suite.py", suite)
        result = _run_pytest(
            workspace, "-p", _PLUGIN, "-n", str(worker_count), "test_suite.py"
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        workers_record = workspace.read_record("workers-controller.json")
        expected_workers = [f"gw{i}" for i in range(worker_count)]
        assert workers_record["workers"] == expected_workers, workers_record
        expected_names = sorted(
            [
                "observed-controller.json",
                "workers-controller.json",
                *(
                    f"{kind}-{worker}.json"
                    for worker in expected_workers
                    for kind in _RECORD_KINDS
                ),
            ]
        )
        assert workspace.record_names() == expected_names, workspace.record_names()
    finally:
        workspace.close()


def check_existing_record_is_never_overwritten() -> None:
    workspace = _Workspace()
    try:
        existing = workspace.run_dir / "observed-main.json"
        existing.write_text("an earlier session's record", encoding="utf-8")
        workspace.write("test_suite.py", _TRIVIAL_SUITE)
        result = _run_pytest(workspace, "-p", _PLUGIN, "test_suite.py")
        assert result.returncode == 3, (  # pytest.ExitCode.INTERNAL_ERROR
            f"expected exit 3 (INTERNAL_ERROR), got {result.returncode}\n{result.stderr}"
        )
        assert "already exists" in result.stderr and "never overwritten" in result.stderr, (
            result.stderr
        )
        assert existing.read_text(encoding="utf-8") == "an earlier session's record"
        assert workspace.record_names() == ["observed-main.json"]
    finally:
        workspace.close()


def check_transient_roots_names_the_resolved_os_temp_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="runner-plugin-gate-transient-") as tmp:
        workspace_root = Path(tmp)
        expected = Path(os.path.realpath(tempfile.gettempdir()))
        assert expected in runner_plugin.transient_roots(workspace_root)


def check_path_scope_excludes_workspace_scratch_directories() -> None:
    with tempfile.TemporaryDirectory(prefix="runner-plugin-gate-scope-") as tmp:
        root = Path(tmp)
        scope = runner_plugin._PathScope.for_workspace(root)
        roots = runner_plugin.transient_roots(root)
        root_key = os.path.normcase(str(root.resolve()))
        excluded_zones = [
            r for r in roots if os.path.normcase(str(r)).startswith(root_key)
        ]
        assert excluded_zones, "precondition: at least one transient root nests inside the workspace"
        for zone in excluded_zones:
            marker = str(zone / "generated.exe")
            assert not scope.admits(marker), f"{marker} must be excluded via {zone}"
        assert scope.admits(str(root / "src" / "kept.py"))


def harness_self_test() -> bool:
    """A dummy check that always fails, used only by --harness-self-test."""

    def _always_fails() -> None:
        assert False, "deliberately failing check for --harness-self-test"

    return run_checks([_always_fails])


_ALL_CHECKS: list[CheckFunc] = [
    check_records_never_leak_sentinels,
    check_records_hold_exact_facts,
    check_missing_environment_variable_is_usage_error,
    check_malformed_environment_variable_is_usage_error,
    check_worker_id_that_cannot_name_a_file_is_usage_error,
    check_records_are_named_for_the_worker,
    check_distributed_session_records_every_worker,
    check_existing_record_is_never_overwritten,
    check_transient_roots_names_the_resolved_os_temp_directory,
    check_path_scope_excludes_workspace_scratch_directories,
]


def main() -> int:
    if "--harness-self-test" in sys.argv:
        return 0 if harness_self_test() else 1

    print(f"Running {len(_ALL_CHECKS)} {_PLUGIN} behavior checks...\n")
    passed = run_checks(_ALL_CHECKS)

    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(_ALL_CHECKS)} runner-plugin behavior checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
