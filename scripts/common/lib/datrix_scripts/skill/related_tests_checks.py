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
from datrix_scripts.skill.related_tests import (
    LOCK_MESSAGE,
    RelatedVerdict,
    Selection,
    SelectionResult,
    file_tags,
    plan_related,
    repair_prompt,
    run_selection,
    written_paths,
)

_ALPHA_TEST = 'import pytest\n\npytestmark = pytest.mark.tag("alpha")\n\n\ndef test_ok() -> None:\n    assert True\n'


def write_workspace(root: Path) -> None:
    """lib <- plug (a plugin: declares a datrix.* entry point); host owns GenerationPipeline and runs plugins only
    through entry points; other is unrelated. Every package has an alpha-tagged unit test."""
    manifest = '[project]\nname = "{name}"\ndependencies = [{deps}]\n{extra}'
    plugin = '\n[project.entry-points."datrix.platforms"]\nplug = "datrix_plug:Plug"\n'
    files = {
        "datrix-lib/pyproject.toml": manifest.format(name="datrix-lib", deps="", extra=""),
        "datrix-lib/src/datrix_lib/__init__.py": "VALUE = 1\n",
        "datrix-plug/pyproject.toml": manifest.format(name="datrix-plug", deps='"datrix-lib"', extra=plugin),
        "datrix-plug/src/datrix_plug/__init__.py": "import datrix_lib\n\n\nclass Plug:\n    pass\n",
        "datrix-host/pyproject.toml": manifest.format(name="datrix-host", deps="", extra=""),
        "datrix-host/src/datrix_host/__init__.py": "class GenerationPipeline:\n    pass\n",
        "datrix-host/tests/e2e/test_host.py": _ALPHA_TEST,
        "datrix-other/pyproject.toml": manifest.format(name="datrix-other", deps="", extra=""),
        "datrix-other/src/datrix_other/__init__.py": "VALUE = 2\n",
    }
    for name in ("lib", "plug", "host", "other"):
        files[f"datrix-{name}/tests/unit/test_{name}.py"] = _ALPHA_TEST
    write_files(root, files)
    config = cross_ecosystem_config_path(root)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"dependencies": {}}), encoding="utf-8")


def tool_use_line(name: str, tool_input: dict[str, object]) -> str:
    """One stream-log line: an assistant message holding a single tool call."""
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name,
                                                                       "input": tool_input}]}})


def check_written_paths_come_from_every_editing_tool() -> None:
    with TemporaryDirectory() as raw:
        log = Path(raw) / "step.stream.jsonl"
        log.write_text("\n".join([
            tool_use_line("Edit", {"file_path": "a.py"}),
            tool_use_line("Write", {"file_path": "b.py"}),
            tool_use_line("mcp__datrix-edit__edit_lines", {"edits": [{"file_path": "c.py"}, {"file_path": "d.py"}]}),
            tool_use_line("Read", {"file_path": "never.py"}),
            "not json",
        ]), encoding="utf-8")
        assert written_paths(log) == [Path("a.py"), Path("b.py"), Path("c.py"), Path("d.py")]
        try:
            written_paths(Path(raw) / "absent.jsonl")
        except AssistError:
            return
    raise AssertionError("a missing session log must be refused")


def check_tags_are_read_at_every_marker_level() -> None:
    source = (
        "import pytest\n\n"
        'pytestmark = [pytest.mark.unit, pytest.mark.tag("alpha")]\n\n\n'
        '@pytest.mark.tag("beta")\nclass TestX:\n'
        '    @pytest.mark.parametrize("v", [pytest.param(1, marks=pytest.mark.tag("gamma"))])\n'
        "    def test_row(self, v: int) -> None:\n        assert v\n"
    )
    with TemporaryDirectory() as raw:
        path = Path(raw) / "test_x.py"
        path.write_text(source, encoding="utf-8")
        assert file_tags(path) == {"alpha", "beta", "gamma"}


def check_the_plan_follows_the_closure_the_tags_and_the_plugins() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        lib_source = root / "datrix-lib" / "src" / "datrix_lib" / "__init__.py"
        lib_test = root / "datrix-lib" / "tests" / "unit" / "test_lib.py"
        plan = plan_related(root, [lib_source, lib_test])
        assert [(s.packages, s.specific, s.tags) for s in plan] == [
            (("datrix-lib",), ("tests/unit/test_lib.py",), ()),
            (("datrix-lib", "datrix-plug"), (), ("alpha",)),
            (("datrix-host",), ("tests/e2e",), ()),
        ], plan
        other = root / "datrix-other" / "src" / "datrix_other" / "__init__.py"
        assert plan_related(root, [other, root / "datrix-other" / "README.md", root / "elsewhere.py"]) == ()


def write_stub_harness(root: Path, body: str) -> None:
    """Replace the workspace's ``test.ps1`` with a small real PowerShell script."""
    script = root / "datrix" / "scripts" / "test" / "test.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")


def check_a_run_passes_only_on_exit_code_and_summary_and_a_lost_lock_is_refused() -> None:
    selection = Selection(("datrix-lib",), ("tests/unit/test_lib.py",), (), "check")
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
    failing = SelectionResult(Selection(("datrix-cli",), ("tests/e2e",), (), "end-to-end tier"), False, "E   A002 found")
    prompt = repair_prompt(RelatedVerdict((failing.selection,), (failing,)))
    assert "test.ps1 datrix-cli -Specific tests/e2e" in prompt and "E   A002 found" in prompt, prompt


CHECKS = (
    check_written_paths_come_from_every_editing_tool,
    check_tags_are_read_at_every_marker_level,
    check_the_plan_follows_the_closure_the_tags_and_the_plugins,
    check_a_run_passes_only_on_exit_code_and_summary_and_a_lost_lock_is_refused,
    check_the_repair_prompt_names_each_failing_run_and_its_output,
)
