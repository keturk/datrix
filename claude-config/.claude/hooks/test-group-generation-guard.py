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
_TWIN = 'bash "d:/datrix/datrix/scripts/dev/generate.sh"'
_PY = "D:/datrix/.venv/Scripts/python.exe"
_MODULE = f"{_PY} -m datrix_scripts.dev.generate"

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
    (f"{_GEN} -TestSet foundation -L typescript", True, "sweeps a named test set"),
    (f"{_GEN} -All -L python -OutputBase .tmp/x", True, "group flag anywhere in the command"),
    (f"{_GEN} {_EXAMPLE} -L python", False, "single project is the sanctioned form"),
    (f"{_GEN} {_EXAMPLE} -L typescript -ConfigProfile production", False, "single project + profile"),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -All',
        False,
        "-All is legitimate on test.ps1",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/scan/compile.ps1" -All',
        False,
        "-All is legitimate on compile.ps1",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/scan/libcst.ps1" -All',
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
    (
        f"{_GEN} {_EXAMPLE} -L python; "
        'powershell -File "d:/datrix/datrix/scripts/scan/compile.ps1" -All',
        False,
        "-All on a different statement than generate.ps1",
    ),
    (
        f"& 'd:/datrix/datrix/scripts/dev/generate.ps1' {_EXAMPLE} -All",
        True,
        "the call operator runs generate.ps1",
    ),
    (
        f'bash -c "{_GEN.replace(chr(34), chr(39))} -Domains -L python"',
        True,
        "generate.ps1 run through a shell wrapper",
    ),
    # ---- the POSIX twin and the module take the module's own flags ----
    (f"{_TWIN} --all --language=python", True, "generate.sh --all sweeps the whole corpus"),
    (f"{_TWIN} --domains --language=python", True, "generate.sh --domains sweeps every domain example"),
    (f"{_TWIN} --test-set=foundation --language=python", True, "generate.sh --test-set=<set> sweeps a set"),
    (f"{_TWIN} --test-set foundation --language=python", True, "generate.sh --test-set <set> sweeps a set"),
    ("/d/datrix/datrix/scripts/dev/generate.sh --all", True, "the twin run directly"),
    (f"{_TWIN} {_EXAMPLE} --language=python", False, "single project through the twin"),
    (f"{_MODULE} --all --language=python", True, "the module run directly with --all"),
    (f"{_MODULE} --domains", True, "the module run directly with --domains"),
    (f"{_MODULE} --source={_EXAMPLE} --language=python", False, "single project through the module"),
    (f"{_PY} -mdatrix_scripts.dev.generate --all", True, "the module named with no space after -m"),
    (f"{_PY} -Im datrix_scripts.dev.generate --domains", True, "-m grouped with other interpreter flags"),
    (f"{_PY} -I -m datrix_scripts.dev.generate --all", True, "-m after a separate interpreter flag"),
    (
        f"{_PY} -Im datrix_scripts.dev.generate --source={_EXAMPLE} --language=python",
        False,
        "single project through the module with grouped interpreter flags",
    ),
    (
        f"{_PY} -m datrix_scripts.dev.generate_doc_fragments --all",
        False,
        "a module whose name merely starts with datrix_scripts.dev.generate",
    ),
    (
        'bash "d:/datrix/datrix/scripts/dev/generate-test-rules.sh" --all',
        False,
        "generate-test-rules.sh is not generate.sh",
    ),
    (f"{_TWIN} {_EXAMPLE} --language=python -All", False, "the PowerShell spelling is no flag of the twin"),
)

#: (command, must_block, why) — run WITHOUT the quick-reference marker: only a
#: command that executes a script under datrix/scripts/ needs it.
_MARKER_CASES: tuple[tuple[str, bool, str], ...] = (
    (
        "S=d:/datrix/datrix/scripts/common/lib/datrix_scripts/scan/config_linter.py; grep -n foo $S",
        False,
        "a scripts path in a variable assignment is named, not run",
    ),
    (
        "cat <<EOF\n  python d:/datrix/datrix/scripts/common/lib/datrix_scripts/scan/config_linter.py\nEOF",
        False,
        "a heredoc body line naming a scripts .py is data",
    ),
    (
        'for f in d:/datrix/datrix/scripts/test/status-deploy-tests.ps1; do sed -n 1,5p "$f"; done',
        False,
        "a for list naming a script runs nothing",
    ),
    (
        'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific a.py',
        True,
        "powershell -File runs the script",
    ),
    (
        "& 'd:/datrix/datrix/scripts/scan/compile.ps1' -ProjectDir x",
        True,
        "the call operator runs the script",
    ),
    (
        r"D:\datrix\.venv\Scripts\python.exe d:\datrix\datrix\scripts\common\lib\datrix_scripts\scan\config_linter.py",
        True,
        "a Python interpreter runs the scripts .py",
    ),
    (
        "S=x; powershell -Command \"& 'd:/datrix/datrix/scripts/dev/generate.ps1' a.dtrx\"",
        True,
        "-Command text is read for the script it runs",
    ),
)


def _run(command: str, description: str = _VERIFIED) -> int:
    payload = json.dumps({"tool_input": {"command": command, "description": description}})
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
    runs = [(case, _VERIFIED) for case in _CASES] + [(case, "") for case in _MARKER_CASES]
    for (command, must_block, why), description in runs:
        blocked = _run(command, description) == _BLOCK_EXIT
        ok = blocked == must_block
        verdict = "BLOCK" if blocked else "allow"
        print(f"  [{'OK  ' if ok else 'FAIL'}] {verdict:5s}  {why}")
        if not ok:
            expected = "block" if must_block else "allow"
            failures.append(f"expected {expected}, got {verdict}: {command}")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} of {len(runs)} cases wrong:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"[OK] all {len(runs)} cases correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
