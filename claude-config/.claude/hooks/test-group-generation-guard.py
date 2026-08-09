"""Self-test for validate-script-invocation.py's group-generation guard.

Run: D:\\datrix\\.venv\\Scripts\\python.exe .claude/hooks/test-group-generation-guard.py

The guard enforces CLAUDE.md's "Generation granularity" rule: verification
regenerates the ONE affected project, never a group sweep. An agent swept all 13
domain examples via `generate.ps1 -Domains` despite the rule being written down,
which is why this is a hard block rather than an instruction.

Non-vacuity matters here: a guard scoped too broadly would block `-All` on
test.ps1/compile.ps1 (legitimate and common), and one scoped too narrowly would
miss `-Domains`. Both directions are asserted below.
"""

import json
import subprocess
import sys
from pathlib import Path

_HOOK = Path(__file__).resolve().parent / "validate-script-invocation.py"
_BLOCK_EXIT = 2
_VERIFIED = "VERIFIED_AGAINST_QUICK_REFERENCE"

_GEN = 'powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1"'
_EXAMPLE = '"d:/datrix/datrix/examples/03-domains/finance/system.dtrx"'

#: (command, must_block, why)
_CASES: tuple[tuple[str, bool, str], ...] = (
    # ---- reading a script is not invoking it ----
    #
    # This hook decided "does the command invoke script X" by testing whether X's
    # name appeared anywhere in the text, so `grep -n "Unit" .../test.ps1` was
    # refused for lacking a quick-reference marker — blocking an agent from
    # reading the source of the very script the hook guards. The quoted pipe in a
    # grep pattern is load-bearing here: a non-quote-aware split cuts the segment
    # at it and loses the leading `grep`.
    (
        'grep -nE "Unit|marker|-m " datrix/scripts/test/test.ps1',
        False,
        "grep over test.ps1 is a read, not a run",
    ),
    (
        'Select-String -Path "d:/datrix/datrix/scripts/dev/generate.ps1" -Pattern "Domains"',
        False,
        "Select-String over generate.ps1",
    ),
    (
        "cat datrix/scripts/dev/generate.ps1 | head -40",
        False,
        "cat piped to head",
    ),
    (
        f'grep -n Domains datrix/scripts/dev/generate.ps1; {_GEN} -Domains -L python',
        True,
        "a read chained before a real group generation still blocks",
    ),
    (f"{_GEN} -Domains -L typescript", True, "sweeps every domain example"),
    (f"{_GEN} -All -L python", True, "sweeps the whole corpus"),
    (f"{_GEN} -TestSet foundation -L java", True, "sweeps a named test set"),
    (f"{_GEN} -All -L java -OutputBase .tmp/x", True, "group flag anywhere in the command"),
    (f"{_GEN} {_EXAMPLE} -L java", False, "single project is the sanctioned form"),
    (f"{_GEN} {_EXAMPLE} -L typescript -ConfigProfile production", False, "single project + profile"),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -All',
        False,
        "-All is legitimate on test.ps1",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/dev/compile.ps1" -All',
        False,
        "-All is legitimate on compile.ps1",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/dev/libcst.ps1" -All',
        False,
        "-All is legitimate on libcst.ps1",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/dev/generate-test-rules.ps1" -All',
        False,
        "different script whose name merely starts with 'generate'",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/dev/generate-doc-fragments.ps1" -Check',
        False,
        "generate-doc-fragments.ps1 is not generate.ps1",
    ),
)


def _run(command: str) -> int:
    payload = json.dumps({"tool_input": {"command": command, "description": _VERIFIED}})
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
    failures: list[str] = []
    for command, must_block, why in _CASES:
        blocked = _run(command) == _BLOCK_EXIT
        ok = blocked == must_block
        verdict = "BLOCK" if blocked else "allow"
        print(f"  [{'OK  ' if ok else 'FAIL'}] {verdict:5s}  {why}")
        if not ok:
            expected = "block" if must_block else "allow"
            failures.append(f"expected {expected}, got {verdict}: {command}")

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
