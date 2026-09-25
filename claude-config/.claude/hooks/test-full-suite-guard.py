"""Self-test for guard-full-suite-runs.py.

Run: D:\\datrix\\.venv\\Scripts\\python.exe .claude/hooks/test-full-suite-guard.py

The guard enforces that no agent -- subagent or main session -- ever runs a whole
test suite. Agents run the tests related to the code they changed: named files
(`-Specific`), a keyword (`-Keyword`), or feature tags (`-Tag`).

Both directions matter and both are asserted here. A guard scoped too broadly
would block the targeted runs every change depends on, a tag listing, or
`test-single.ps1`; one scoped too narrowly would miss `-All`, a tier sweep, an
`affected-gate.ps1` sweep, or a second bare invocation chained after a targeted one.

The audit log is truncated back to its starting length, so running this test
leaves no trace.
"""

import json
import subprocess
import sys
from pathlib import Path

_HOOK = Path(__file__).resolve().parent / "guard-full-suite-runs.py"
_BLOCK_EXIT = 2

_AUDIT = Path("D:/datrix/.tmp/full-suite-audit.jsonl")

_TEST = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1"'
_SINGLE = 'powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1"'
_AFFECTED_GATE = 'powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1"'

_AGENT = "a188ff1324c21f55e"
_MAIN = ""

#: (command, must_block, why) -- each case runs as a subagent AND as the main
#: session: the rule is identical for both.
_CASES: tuple[tuple[str, bool, str], ...] = (
    # ---- whole-suite forms: blocked for everyone ----
    (f"{_TEST} datrix-codegen-docker", True, "bare full suite"),
    (f"{_TEST} datrix-common datrix-codegen-aws", True, "several bare packages"),
    (f"{_TEST} -All", True, "-All"),
    (f"{_TEST} datrix-common -Unit", True, "tier sweep is not a targeted run"),
    (f"{_TEST} datrix-common -Fast", True, "-Fast still sweeps the package"),
    (f"{_TEST} -Rerun", True, "-Rerun re-runs whole package suites"),
    (f"{_TEST} .\\datrix-common\\", True, "folder-path form names a package"),
    (f"{_TEST} -All -Tag gateway", True, "-All widens a tag run back to every package"),
    (f'{_TEST} -Rerun -Specific "tests/unit/a.py"', True, "-Rerun widens a -Specific run"),
    (
        f'{_TEST} datrix-common; {_TEST} datrix-language -Specific "tests/unit/a.py"',
        True,
        "a targeted second invocation must not vouch for a bare first one",
    ),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py"; {_TEST} datrix-language',
        True,
        "a targeted first invocation must not vouch for a bare second one",
    ),
    (
        f"{_TEST} datrix-codegen-docker 2>&1 | Select-Object -Last 30",
        True,
        "pipeline suffix does not disguise a bare full suite",
    ),
    (f"{_AFFECTED_GATE} -Projects datrix-common", True, "affected-gate.ps1 sweep"),
    (f"{_AFFECTED_GATE} -All", True, "affected-gate.ps1 -All"),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py"; {_AFFECTED_GATE} -Projects datrix-language',
        True,
        "a targeted run must not vouch for an affected-gate.ps1 sweep chained after it",
    ),
    (
        f"grep -n Unit datrix/scripts/test/test.ps1; {_TEST} datrix-common",
        True,
        "read chained BEFORE a real bare full-suite run still blocks",
    ),
    (
        f"{_TEST} datrix-common; grep -n Unit datrix/scripts/test/test.ps1",
        True,
        "read chained AFTER a real bare full-suite run still blocks",
    ),
    # ---- targeted forms: allowed for everyone ----
    (
        f'{_TEST} datrix-codegen-docker -Specific "tests/unit/infra/test_jaeger.py"',
        False,
        "targeted -Specific",
    ),
    (f'{_TEST} datrix-codegen-python -Keyword "export_level"', False, "-Keyword narrows"),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py,tests/unit/b.py"',
        False,
        "batched comma-separated targeted set",
    ),
    (f"{_TEST} datrix-codegen-python -Tag gateway", False, "-Tag narrows to tagged tests"),
    (
        f"{_TEST} datrix-codegen-python datrix-codegen-java -Tag gateway,identity",
        False,
        "-Tag across several packages",
    ),
    # ---- shapes that start no test: allowed for everyone ----
    (f"{_TEST} datrix-codegen-python -ListTags", False, "-ListTags runs no test"),
    (f"{_TEST} -All -ListTags", False, "-All -ListTags runs no test"),
    (f"{_AFFECTED_GATE} -SelfTest", False, "affected-gate.ps1 -SelfTest runs no suite child"),
    (
        f"{_AFFECTED_GATE} -Projects datrix-common,datrix-codegen-aws -SelfTest",
        False,
        "-Projects alongside -SelfTest keeps the self-test exemption",
    ),
    # ---- must never over-block ----
    (
        f'{_SINGLE} "tests/unit/test_entity.py" -Project datrix-codegen-python',
        False,
        "test-single.ps1 is inherently single",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/test-specific-selection-gate.ps1"',
        False,
        "a repo gate whose name merely contains 'test'",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/gate-verdict.ps1" -All',
        False,
        "gate-verdict.ps1 reads results, it does not run suites",
    ),
    ('git -C d:\\datrix\\datrix-codegen-docker diff --stat', False, "not a test invocation"),
    # ---- reading the runner is not running it ----
    ('grep -nE "Unit|marker|-m " datrix/scripts/test/test.ps1', False, "grep over test.ps1"),
    ('rg -n "\\-Unit" d:/datrix/datrix/scripts/test/test.ps1', False, "ripgrep over the runner"),
    (
        'Select-String -Path "d:/datrix/datrix/scripts/test/test.ps1" -Pattern "Unit"',
        False,
        "Select-String over the runner",
    ),
    (
        "Get-Content d:/datrix/datrix/scripts/test/test.ps1 | Select-Object -First 40",
        False,
        "Get-Content over the runner",
    ),
    ("cat datrix/scripts/test/test.ps1 | grep -n Unit", False, "cat piped to grep"),
    ("head -50 datrix/scripts/test/test.ps1", False, "head over the runner"),
    (
        'grep -n "affected-gate.ps1" d:/datrix/datrix/scripts/test/quick-reference.md',
        False,
        "grep over affected-gate.ps1 is a read",
    ),
)


def _run(command: str, agent_id: str) -> int:
    payload = json.dumps(
        {
            "tool_name": "PowerShell",
            "session_id": "self-test",
            "agent_id": agent_id,
            "tool_input": {"command": command},
        }
    )
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode


def main() -> int:
    audit_size = _AUDIT.stat().st_size if _AUDIT.exists() else 0

    failures: list[str] = []
    checked = 0
    try:
        for command, must_block, why in _CASES:
            for role, agent_id in (("subagent", _AGENT), ("main", _MAIN)):
                checked += 1
                blocked = _run(command, agent_id) == _BLOCK_EXIT
                ok = blocked == must_block
                verdict = "BLOCK" if blocked else "allow"
                print(f"  [{'OK  ' if ok else 'FAIL'}] {verdict:5s}  {role:8s} {why}")
                if not ok:
                    expected = "block" if must_block else "allow"
                    failures.append(f"{role}: expected {expected}, got {verdict}: {command}")
    finally:
        if _AUDIT.exists():
            with open(_AUDIT, "r+b") as handle:
                handle.truncate(audit_size)

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
