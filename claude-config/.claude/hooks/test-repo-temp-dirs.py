"""Exercise guard-repo-temp-dirs.py with synthetic payloads.

Blocking is worthless if it fires on real source paths, and worse than worthless
if it misses the shape that actually caused the incident. Both directions are
asserted below.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-repo-temp-dirs.py")
fails = []


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode


def write(path):
    return run({"tool_name": "Write", "tool_input": {"file_path": path}})


def cmd(command):
    return run({"tool_name": "PowerShell", "tool_input": {"command": command}})


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


BLOCK, ALLOW = 2, 0

print("== Write/Edit: temp directory inside a package repo ==")
check("the incident: datrix/.test-output", write(r"d:\datrix\datrix\.test-output\x.json"), BLOCK)
check("nested .tmp", write("D:/datrix/datrix-common/.tmp/run.log"), BLOCK)
check("tmp under tests/", write(r"d:\datrix\datrix-codegen-aws\tests\tmp\out.json"), BLOCK)
check("suffixed test-output", write(r"d:\datrix\datrix-cli\.test-output-foundation-check\a.txt"), BLOCK)
check("scratch dir", write("d:/datrix/datrix-language/scratch/notes.md"), BLOCK)
check(".scripts inside a repo", write("d:/datrix/datrix-extensions/.scripts/run.ps1"), BLOCK)

print("== Write/Edit: legitimate paths stay writable ==")
check("workspace .tmp (sanctioned)", write(r"d:\datrix\.tmp\ratchet.txt"), ALLOW)
check("workspace .test-output (sanctioned)", write(r"d:\datrix\.test-output\run.log"), ALLOW)
check("workspace .scripts (sanctioned)", write(r"d:\datrix\.scripts\measure.py"), ALLOW)
check("real source", write(r"d:\datrix\datrix-common\src\datrix_common\config\loader.py"), ALLOW)
check("scripts/ is not .scripts", write(r"d:\datrix\datrix\scripts\test\test.ps1"), ALLOW)
check(".test_results (test.ps1 writes it by design)",
      write(r"d:\datrix\datrix-codegen-python\.test_results\latest.json"), ALLOW)
check("vendored tmp", write(r"d:\datrix\datrix-codegen-typescript\node_modules\tmp\index.js"), ALLOW)
check("session scratchpad", write(r"C:\Users\x\AppData\Local\Temp\claude\s\scratchpad\a.py"), ALLOW)
check("a file merely named temp_utils.py", write(r"d:\datrix\datrix-common\src\temp_utils.py"), ALLOW)

print("== Commands: creating or writing a temp dir in a repo ==")
check("mkdir", cmd(r"mkdir d:\datrix\datrix\.test-output"), BLOCK)
check("New-Item", cmd('New-Item -ItemType Directory -Path "D:\\datrix\\datrix-common\\.tmp"'), BLOCK)
check("redirect, workspace-relative", cmd("python foo.py > datrix-codegen-python/.tmp/out.log"), BLOCK)
check("-OutputDir argument", cmd(r"powershell -File gen.ps1 -OutputDir d:\datrix\datrix-cli\tmp"), BLOCK)
check("copy into a repo temp dir", cmd(r"Copy-Item a.json d:\datrix\datrix-codegen-sql\temp\a.json"), BLOCK)

print("== Commands: inspection, cleanup, and sanctioned targets stay allowed ==")
check("listing a stray dir", cmd(r"Get-ChildItem d:\datrix\datrix\.test-output"), ALLOW)
check("deleting a stray dir", cmd(r"Remove-Item d:\datrix\datrix\.test-output -Recurse -Force"), ALLOW)
check("redirect to workspace .tmp", cmd(r"python foo.py > d:\datrix\.tmp\out.log"), ALLOW)
check("redirect to workspace .test-output",
      cmd(r'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-cli > d:\datrix\.test-output\cli.log'),
      ALLOW)
check("git untracking the stray dir", cmd("git -C d:/datrix/datrix rm -r --cached .test-output"), ALLOW)
check("writing real source in a repo", cmd(r'Set-Content d:\datrix\datrix-common\src\a.py "x"'), ALLOW)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
