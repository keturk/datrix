"""Self-test for guard-full-suite-runs.py.

Run: D:\\datrix\\.venv\\Scripts\\python.exe .claude/hooks/test-full-suite-guard.py

The guard enforces the verification-strategy rule that full package suites run
ONCE at a phase boundary, never inside a task. It is a hard block because the
rule was written down, repeated in every dispatch prompt, and violated anyway --
aws (1844), azure (3294), docker (1880) and component (427) all ran bare full
suites inside a single phase.

Both directions matter and both are asserted here. A guard scoped too broadly
would block the targeted `-Specific` runs every task depends on, or catch
`test-single.ps1`; one scoped too narrowly would miss `-All`, a tier sweep, or a
second bare invocation chained after a targeted one.

The ticket file is the real one: it is saved and restored around the run, and
the audit log is truncated back to its starting length, so running this test
leaves no trace.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_HOOK = Path(__file__).resolve().parent / "guard-full-suite-runs.py"
_BLOCK_EXIT = 2

_TICKET = Path("D:/datrix/.tmp/full-suite-ticket.json")
_AUDIT = Path("D:/datrix/.tmp/full-suite-audit.jsonl")

_TEST = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1"'
_SINGLE = 'powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1"'

_AGENT = "a188ff1324c21f55e"


def _ticket(packages: list[str], *, ttl_seconds: int = 3600, reason: str | None = None) -> dict:
    return {
        "packages": packages,
        "reason": "phase-45 boundary gate over the affected closure" if reason is None else reason,
        "granted_by": "orchestrator",
        "expires_epoch": int(time.time()) + ttl_seconds,
    }


#: (command, agent_id, ticket-or-None, must_block, why)
_CASES: tuple[tuple[str, str, dict | None, bool, str], ...] = (
    # ---- subagents: unconditional, no ticket can help ----
    (f"{_TEST} datrix-codegen-docker", _AGENT, None, True, "subagent, bare full suite"),
    (
        f"{_TEST} datrix-codegen-docker",
        _AGENT,
        _ticket(["*"]),
        True,
        "subagent, bare full suite, even under a wildcard ticket",
    ),
    (f"{_TEST} -All", _AGENT, _ticket(["*"]), True, "subagent, -All"),
    (
        f'{_TEST} datrix-codegen-docker -Specific "tests/unit/infra/test_jaeger.py"',
        _AGENT,
        None,
        False,
        "subagent, targeted -Specific is the sanctioned form",
    ),
    (
        f'{_TEST} datrix-codegen-python -Keyword "export_level"',
        _AGENT,
        None,
        False,
        "subagent, -Keyword narrows to named tests",
    ),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py,tests/unit/b.py"',
        _AGENT,
        None,
        False,
        "subagent, batched comma-separated targeted set",
    ),
    # ---- main session: ticket-gated ----
    (f"{_TEST} datrix-codegen-azure", "", None, True, "main session, no ticket"),
    (
        f"{_TEST} datrix-codegen-azure",
        "",
        _ticket(["datrix-codegen-azure"]),
        False,
        "main session, ticket covers the package",
    ),
    (
        f"{_TEST} datrix-codegen-azure",
        "",
        _ticket(["datrix-codegen-aws"]),
        True,
        "main session, ticket names a different package",
    ),
    (
        f"{_TEST} datrix-common datrix-codegen-aws",
        "",
        _ticket(["datrix-common"]),
        True,
        "main session, ticket covers only one of two packages",
    ),
    (
        f"{_TEST} datrix-common datrix-codegen-aws",
        "",
        _ticket(["datrix-common", "datrix-codegen-aws"]),
        False,
        "main session, ticket covers both packages",
    ),
    (f"{_TEST} -All", "", _ticket(["datrix-common"]), True, "-All needs a wildcard ticket"),
    (f"{_TEST} -All", "", _ticket(["*"]), False, "-All under a wildcard ticket"),
    (
        f"{_TEST} datrix-codegen-azure",
        "",
        _ticket(["*"], ttl_seconds=-60),
        True,
        "expired ticket",
    ),
    (
        f"{_TEST} datrix-codegen-azure",
        "",
        _ticket(["*"], ttl_seconds=48 * 3600),
        True,
        "ticket lifetime beyond the 6h cap",
    ),
    (
        f"{_TEST} datrix-codegen-azure",
        "",
        _ticket(["*"], reason="gate"),
        True,
        "ticket with no written reason",
    ),
    # ---- shapes that are still whole-suite runs ----
    (f"{_TEST} datrix-common -Unit", "", None, True, "tier sweep is not a targeted run"),
    (f"{_TEST} datrix-common -Fast", "", None, True, "-Fast still sweeps the package"),
    (f"{_TEST} -Rerun", "", None, True, "-Rerun re-runs whole package suites"),
    (f"{_TEST} .\\datrix-common\\", "", None, True, "folder-path form names a package"),
    (
        f'{_TEST} datrix-common; {_TEST} datrix-language -Specific "tests/unit/a.py"',
        "",
        None,
        True,
        "a targeted second invocation must not vouch for a bare first one",
    ),
    (
        f'{_TEST} datrix-common -Specific "tests/unit/a.py"; {_TEST} datrix-language',
        "",
        None,
        True,
        "a targeted first invocation must not vouch for a bare second one",
    ),
    (
        f"{_TEST} datrix-codegen-docker 2>&1 | Select-Object -Last 30",
        _AGENT,
        None,
        True,
        "pipeline suffix does not disguise a bare full suite",
    ),
    # ---- must never over-block ----
    (
        f'{_SINGLE} "tests/unit/test_entity.py" -Project datrix-codegen-python',
        _AGENT,
        None,
        False,
        "test-single.ps1 is inherently single",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/test-specific-selection-gate.ps1"',
        _AGENT,
        None,
        False,
        "a repo gate whose name merely contains 'test'",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/gate-verdict.ps1" -All',
        _AGENT,
        None,
        False,
        "gate-verdict.ps1 reads results, it does not run suites",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/tasks/phase-status.ps1" 45',
        _AGENT,
        None,
        False,
        "unrelated script",
    ),
    (
        'git -C d:\\datrix\\datrix-codegen-docker diff --stat',
        _AGENT,
        None,
        False,
        "not a test invocation at all",
    ),
    # ---- reading the runner is not running it ----
    #
    # This family shipped as a live over-block: `grep -nE "Unit|-m " .../test.ps1`
    # names the script and a tier flag, and was refused as a whole-suite run --
    # with a package list of `<unnamed>, <unnamed>`, the parse reporting that it
    # had matched nothing. A guard that stops an agent reading the source of the
    # thing it guards is worse than the sweep it prevents.
    (
        'grep -nE "Unit|marker|-m " datrix/scripts/test/test.ps1',
        _AGENT,
        None,
        False,
        "grep OVER test.ps1 is a read, not a run",
    ),
    (
        'rg -n "\\-Unit" d:/datrix/datrix/scripts/test/test.ps1',
        "",
        None,
        False,
        "ripgrep over the runner",
    ),
    (
        'Select-String -Path "d:/datrix/datrix/scripts/test/test.ps1" -Pattern "Unit"',
        _AGENT,
        None,
        False,
        "Select-String over the runner",
    ),
    (
        'Get-Content d:/datrix/datrix/scripts/test/test.ps1 | Select-Object -First 40',
        "",
        None,
        False,
        "Get-Content over the runner",
    ),
    (
        "cat datrix/scripts/test/test.ps1 | grep -n Unit",
        _AGENT,
        None,
        False,
        "cat piped to grep",
    ),
    (
        "head -50 datrix/scripts/test/test.ps1",
        "",
        None,
        False,
        "head over the runner",
    ),
    # ...but a read in one segment must not launder a real run in another.
    (
        f"grep -n Unit datrix/scripts/test/test.ps1; {_TEST} datrix-common",
        _AGENT,
        None,
        True,
        "read chained BEFORE a real bare full-suite run still blocks",
    ),
    (
        f"{_TEST} datrix-common; grep -n Unit datrix/scripts/test/test.ps1",
        _AGENT,
        None,
        True,
        "read chained AFTER a real bare full-suite run still blocks",
    ),
    (
        f'{_TEST} datrix-common 2>&1 | Select-Object -Last 30',
        _AGENT,
        None,
        True,
        "piping a real run's output to a read tool still blocks",
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


def _write_ticket(ticket: dict | None, *, bom: bool = False) -> None:
    if ticket is None:
        if _TICKET.exists():
            _TICKET.unlink()
        return
    _TICKET.parent.mkdir(parents=True, exist_ok=True)
    # PowerShell 5.1 writes a BOM by default, so a real ticket authored on this
    # platform is BOM-prefixed; `bom=True` reproduces that exactly.
    _TICKET.write_text(json.dumps(ticket), encoding="utf-8-sig" if bom else "utf-8")


def _bom_case_passes() -> bool:
    """A BOM-prefixed ticket must still authorize.

    Regression: the guard originally opened the ticket as plain utf-8, so the
    BOM that PowerShell 5.1 prepends made `json.load` raise and the guard
    (correctly, but unhelpfully) failed closed on every ticket written the
    obvious way on Windows.
    """
    _write_ticket(_ticket(["datrix-codegen-azure"]), bom=True)
    return _run(f"{_TEST} datrix-codegen-azure", "") != _BLOCK_EXIT


def main() -> int:
    saved_ticket = _TICKET.read_bytes() if _TICKET.exists() else None
    audit_size = _AUDIT.stat().st_size if _AUDIT.exists() else 0

    failures: list[str] = []
    try:
        for command, agent_id, ticket, must_block, why in _CASES:
            _write_ticket(ticket)
            blocked = _run(command, agent_id) == _BLOCK_EXIT
            ok = blocked == must_block
            verdict = "BLOCK" if blocked else "allow"
            print(f"  [{'OK  ' if ok else 'FAIL'}] {verdict:5s}  {why}")
            if not ok:
                expected = "block" if must_block else "allow"
                failures.append(f"expected {expected}, got {verdict}: {command}")

        bom_ok = _bom_case_passes()
        print(f"  [{'OK  ' if bom_ok else 'FAIL'}] {'allow' if bom_ok else 'BLOCK':5s}  "
              "BOM-prefixed ticket (as PowerShell writes it) still authorizes")
        if not bom_ok:
            failures.append("expected allow, got block: BOM-prefixed ticket")
    finally:
        if saved_ticket is None:
            if _TICKET.exists():
                _TICKET.unlink()
        else:
            _TICKET.write_bytes(saved_ticket)
        if _AUDIT.exists():
            with open(_AUDIT, "r+b") as handle:
                handle.truncate(audit_size)

    print()
    if failures:
        print(f"[FAIL] {len(failures)} of {len(_CASES)} cases wrong:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"[OK] all {len(_CASES)} cases correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
