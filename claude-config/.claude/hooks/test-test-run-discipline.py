"""Self-test for guard-test-run-discipline.py, record-fixture-edits.py and guard-rewrite-size.py.

Run: D:\\datrix\\.venv\\Scripts\\python.exe .claude/hooks/test-test-run-discipline.py

Both directions are asserted. A test run chained with other work, or following an unprobed fixture
edit, must be refused; a lone run, a run after a leading `cd`, a run filtered by a pipe, a run
that only names the runner, and a run after a probe must pass. The size guard refuses only the
edit that takes a session past the cap of distinct test files with no advisor dispatched.

State written by the test (a session record, a probe stamp, a scratch fixture tree) is removed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _fixture_probe as probe  # noqa: E402

_HOOKS = Path(__file__).resolve().parent
_DISCIPLINE = _HOOKS / "guard-test-run-discipline.py"
_RECORDER = _HOOKS / "record-fixture-edits.py"
_SIZE = _HOOKS / "guard-rewrite-size.py"
_BLOCK_EXIT = 2

_TEST = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1"'
_SPECIFIC = f'{_TEST} datrix-common -Specific "tests/unit/a.py"'
_SESSION = "self-test-run-discipline"

_COMPOUND_CASES: tuple[tuple[str, bool, str], ...] = (
    (_SPECIFIC, False, "a lone targeted run"),
    (f"cd d:/datrix && {_SPECIFIC}", False, "a leading cd is not other work"),
    (f"{_SPECIFIC} 2>&1 | Select-Object -Last 30", False, "an output filter on the run's pipeline"),
    (f"{_SPECIFIC} 2>&1 | tail -8", False, "tail on the run's pipeline"),
    (f"{_TEST} datrix-common -ListTags", False, "-ListTags runs no test"),
    ("grep -n Unit datrix/scripts/test/test.ps1; echo done", False, "reading the runner runs no test"),
    ('git -C d:/datrix/datrix-common status; echo ok', False, "no test run at all"),
    (f"sed -i s/a/b/ x.py; {_SPECIFIC}", True, "an edit chained before the run"),
    (f"{_SPECIFIC}; python pins.py", True, "a script chained after the run"),
    (f"{_SPECIFIC} > /dev/null 2>&1; python pins.py datrix-common", True, "the run, then a check, in one call"),
    (f"python probe.py && {_SPECIFIC}", True, "a probe chained before the run"),
    (f"cd d:/datrix && python probe.py && {_SPECIFIC}", True, "a cd does not excuse the probe"),
    (f'{_SPECIFIC}\npython pins.py', True, "a newline-separated second command"),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py;tests/unit/b.py"',
        False,
        "a semicolon inside a quoted argument is not a separator",
    ),
    ('bash d:/datrix/datrix/scripts/test/test.sh datrix-common --tag gateway', False, "test.sh lone run"),
    ('bash d:/datrix/datrix/scripts/test/test-single.sh tests/a.py; ls', True, "test-single chained"),
)


def _hook(path: Path, payload: dict[str, object], env_extra: dict[str, str] | None = None) -> int:
    result = subprocess.run(
        [sys.executable, str(path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode


def _command_payload(command: str) -> dict[str, object]:
    return {
        "tool_name": "PowerShell",
        "session_id": _SESSION,
        "tool_input": {"command": command},
    }


def _write(tool: str, path: str, session: str = _SESSION) -> int:
    return _hook(
        _RECORDER,
        {"tool_name": tool, "session_id": session, "tool_input": {"file_path": path}},
    )


def _check_compound(failures: list[str]) -> int:
    probe.write_edits(_SESSION, {"projects": [], "tests": []})
    for command, must_block, why in _COMPOUND_CASES:
        blocked = _hook(_DISCIPLINE, _command_payload(command)) == _BLOCK_EXIT
        ok = blocked == must_block
        print(f"  [{'OK  ' if ok else 'FAIL'}] {'BLOCK' if blocked else 'allow'}  {why}")
        if not ok:
            failures.append(f"expected {'block' if must_block else 'allow'}: {command}")
    return len(_COMPOUND_CASES)


def _make_project(root: Path) -> Path:
    project = root / "pkg" / "tests" / "fixtures" / "projects" / "probe-me"
    (project / "config").mkdir(parents=True)
    (project / "system.dtrx").write_text("system a.B('config/system.dcfg') {}\n", encoding="utf-8")
    (project / "config" / "system.dcfg").write_text("config system a.B { base {} }\n", encoding="utf-8")
    return project


def _check_probe_gate(failures: list[str], root: Path) -> int:
    project = _make_project(root)
    directory = probe.normalise(str(project))
    edited = str(project / "config" / "system.dcfg")
    stamp = Path(probe.stamp_path(directory))
    steps: list[tuple[str, bool]] = []

    probe.write_edits(_SESSION, {"projects": [], "tests": []})
    _write("Write", edited)
    steps.append(("an edited fixture project is recorded", probe.read_edits(_SESSION)["projects"] == [directory]))
    steps.append(
        ("a run after the edit with no probe is refused", _hook(_DISCIPLINE, _command_payload(_SPECIFIC)) == _BLOCK_EXIT)
    )
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(json.dumps({"dir": directory, "ts": time.time() + 5}), encoding="utf-8")
    try:
        steps.append(("a run after a probe is allowed", _hook(_DISCIPLINE, _command_payload(_SPECIFIC)) == 0))
        (project / "system.dtrx").write_text("system a.B('config/system.dcfg') { }\n", encoding="utf-8")
        newest = Path(project / "system.dtrx")
        stamp.write_text(json.dumps({"dir": directory, "ts": newest.stat().st_mtime - 5}), encoding="utf-8")
        steps.append(
            ("an edit after the probe makes it stale again", _hook(_DISCIPLINE, _command_payload(_SPECIFIC)) == _BLOCK_EXIT)
        )
    finally:
        stamp.unlink(missing_ok=True)
    flat = str(root / "pkg" / "tests" / "fixtures" / "flat.dtrx")
    probe.write_edits(_SESSION, {"projects": [], "tests": []})
    _write("Write", flat)
    steps.append(("a flat fixture file is no project", probe.read_edits(_SESSION)["projects"] == []))
    for label, ok in steps:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)
    return len(steps)


def _transcript(root: Path, *, advisor: bool) -> str:
    entries: list[dict[str, object]] = [
        {"type": "user", "message": {"content": [{"type": "text", "text": "fix them"}]}},
    ]
    if advisor:
        entries.append(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Agent",
                            "input": {"subagent_type": "decision-advisor"},
                        }
                    ]
                },
            }
        )
    path = root / ("advised.jsonl" if advisor else "plain.jsonl")
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    return str(path)


def _check_size_guard(failures: list[str], root: Path) -> int:
    session = f"{_SESSION}-size"
    cap = 25
    many = [f"d:/x/pkg/tests/unit/test_{index}.py" for index in range(cap)]
    probe.write_edits(session, {"projects": [], "tests": many})
    new_file = "d:/x/pkg/tests/unit/test_new.py"

    def edit(path: str, transcript: str) -> int:
        return _hook(
            _SIZE,
            {
                "tool_name": "Edit",
                "session_id": session,
                "transcript_path": transcript,
                "tool_input": {"file_path": path},
            },
        )

    plain, advised = _transcript(root, advisor=False), _transcript(root, advisor=True)
    probe.write_edits(f"{session}-few", {"projects": [], "tests": many[:3]})
    steps = [
        ("a new test file past the cap with no advisor is refused", edit(new_file, plain) == _BLOCK_EXIT),
        ("a file already edited is never refused", edit(many[0], plain) == 0),
        ("a non-test file is never refused", edit("d:/x/pkg/src/mod.py", plain) == 0),
        ("an advisor dispatch lifts the refusal", edit(new_file, advised) == 0),
    ]
    few = _hook(
        _SIZE,
        {
            "tool_name": "Edit",
            "session_id": f"{session}-few",
            "transcript_path": plain,
            "tool_input": {"file_path": new_file},
        },
    )
    steps.append(("below the cap nothing is refused", few == 0))
    for name in (session, f"{session}-few"):
        Path(probe.edits_path(name)).unlink(missing_ok=True)
    for label, ok in steps:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)
    return len(steps)


def _check_stamp_parity(failures: list[str]) -> int:
    """The hook and `dev/probe-fixture` agree on a project's directory and its stamp file."""
    sys.path.insert(0, str(Path(probe.REPO_ROOT) / "datrix" / "scripts" / "common" / "lib"))
    from datrix_scripts.dev import probe_fixture as script  # noqa: PLC0415 - needs the path above

    cases = (
        "d:/datrix/datrix-codegen-azure/tests/fixtures/projects/pooled-queue-consumers/system.dtrx",
        "d:/datrix/datrix-codegen-azure/tests/fixtures/projects/pooled-queue-consumers/config/system.dcfg",
    )
    steps: list[tuple[str, bool]] = []
    for case in cases:
        hook_dir = probe.project_dir(case)
        script_dir = script.project_directory(Path(case))
        steps.append((f"stamp parity: directory of {case.rsplit('tests/fixtures/', 1)[-1]}", (hook_dir or "").lower() == script_dir.lower()))
        if hook_dir is not None:
            same = Path(probe.stamp_path(hook_dir)).as_posix().lower() == script.stamp_path(script_dir).as_posix().lower()
            steps.append((f"stamp parity: stamp file of {hook_dir.rsplit('/', 1)[-1]}", same))
    for label, ok in steps:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)
    return len(steps)


def main() -> int:
    failures: list[str] = []
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            checked += _check_compound(failures)
            checked += _check_probe_gate(failures, root)
            checked += _check_size_guard(failures, root)
            checked += _check_stamp_parity(failures)
        finally:
            Path(probe.edits_path(_SESSION)).unlink(missing_ok=True)
    print()
    if failures:
        print(f"[FAIL] {len(failures)} of {checked} cases wrong:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"[OK] all {checked} cases correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
