"""Exercise guard-forbidden-commands.py with synthetic payloads.

Two directions matter equally. A guard that misses the shape that caused the
incident is decoration; a guard that fires on reading or cleaning up after that
shape blocks the fix. Both are asserted below.

The type-checker cases are drawn from the real incident: 33 Bash calls running
`.venv/Scripts/mypy.exe` from inside each package root, which left ~51,400
`.mypy_cache` files across 15 git repositories.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-forbidden-commands.py")
fails = []


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode


def cmd(command, tool="Bash"):
    return run({"tool_name": tool, "tool_input": {"command": command}})


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


BLOCK, ALLOW = 2, 0

print("== git: reverting or discarding working-tree changes ==")
check("git restore", cmd("git restore src/a.py"), BLOCK)
check("git reset --hard", cmd("git reset --hard origin/main"), BLOCK)
check("git revert", cmd("git revert HEAD"), BLOCK)
check("git stash", cmd("git stash"), BLOCK)
check("git checkout a path", cmd("git checkout -- src/a.py"), BLOCK)
check("git clean -fd", cmd("git clean -fd"), BLOCK)
check("git -C <dir> reset", cmd("git -C d:/datrix/datrix-cli reset --hard"), BLOCK)

print("== git: creating and inspecting stay allowed ==")
check("git checkout -b", cmd("git checkout -b feature/x"), ALLOW)
check("git stash list", cmd("git stash list"), ALLOW)
check("git status", cmd("git -C d:/datrix/datrix-common status --porcelain"), ALLOW)

print("== type-checkers: the incident shape and its relatives ==")
check("the incident: venv mypy.exe from a package root",
      cmd("cd /d/datrix/datrix-codegen-java && /d/datrix/.venv/Scripts/mypy.exe src/datrix_codegen_java"),
      BLOCK)
check("bare mypy", cmd("mypy src"), BLOCK)
check("python -m mypy", cmd("python -m mypy src/datrix_common"), BLOCK)
check("venv python -m mypy", cmd(r"D:\datrix\.venv\Scripts\python.exe -m mypy src"), BLOCK)
check("dmypy daemon", cmd("dmypy run -- src"), BLOCK)
check("pyright", cmd("pyright src"), BLOCK)
check("mypy piped into a filter",
      cmd("/d/datrix/.venv/Scripts/mypy.exe src 2>&1 | tail -20"), BLOCK)
check("the wrapper, bash form",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/mypy.ps1" -All'), BLOCK)
check("the wrapper, call operator",
      cmd(r'& "d:\datrix\datrix\scripts\test\mypy.ps1" datrix-common', tool="PowerShell"),
      BLOCK)
check("the library entry point",
      cmd("D:/datrix/.venv/Scripts/python.exe d:/datrix/datrix/scripts/library/mypy.py datrix-cli"),
      BLOCK)
check("affected-gate with the opt-in switch",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1" -Projects datrix-common -Mypy'),
      BLOCK)

print("== type-checkers: reading, cleaning up and neighbours stay allowed ==")
check("reading the wrapper",
      cmd('grep -n "cache-dir" d:/datrix/datrix/scripts/test/mypy.ps1'), ALLOW)
check("paging the library script",
      cmd("sed -n '1,80p' /d/datrix/datrix/scripts/library/mypy.py"), ALLOW)
check("deleting a stray cache",
      cmd(r"Remove-Item -Recurse -Force d:\datrix\datrix-cli\.mypy_cache", tool="PowerShell"),
      ALLOW)
check("listing the relocated cache root",
      cmd(r"Get-ChildItem d:\datrix\.tmp\mypy-cache", tool="PowerShell"), ALLOW)
check("finding stray caches", cmd("find /d/datrix -maxdepth 2 -name .mypy_cache"), ALLOW)
check("affected-gate WITHOUT the switch",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1" -Projects datrix-common'),
      ALLOW)
check("a package suite run",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/test_a.py"'),
      ALLOW)
check("a file merely named check_mypy.py",
      cmd("python d:/datrix/.scripts/check_mypy.py"), ALLOW)
check("installing is not running", cmd("pip show mypy"), ALLOW)
check("syntax-checking the guarded script (-m consumes the module)",
      cmd("python -m py_compile d:/datrix/datrix/scripts/library/mypy.py"), ALLOW)
check("compiling the wrapper's directory",
      cmd("python -m compileall d:/datrix/datrix/scripts/library"), ALLOW)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
