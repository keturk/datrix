"""Exercise guard-untargeted-scans.py with synthetic payloads.

The incident shape (a three-package semgrep run with no rule and no question) must
block; a targeted rule, a stated question, reading the script, and unrelated
commands must stay allowed; `-All` and subagent runs block regardless of markers.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-untargeted-scans.py")
fails = []


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode


def cmd(command, description="", agent_id=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": command, "description": description}}
    if agent_id:
        payload["agent_id"] = agent_id
    return run(payload)


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


BLOCK, ALLOW = 2, 0
INCIDENT = ('cd /d/datrix; powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" '
            "datrix-codegen-python datrix-common datrix-codegen-common 2>&1 | tail -15")

print("== the incident and its relatives block ==")
check("incident: three-package semgrep, no rule, no question",
      cmd(INCIDENT, "Run semgrep anti-pattern scan on the three touched packages"), BLOCK)
check("libcst one package, bare", cmd('powershell -File "d:/datrix/datrix/scripts/dev/libcst.ps1" datrix-common'), BLOCK)
check("ast-grep direct .ps1 form", cmd(r".\scripts\dev\ast-grep.ps1 datrix-cli"), BLOCK)
check("empty question marker does not lift it",
      cmd(INCIDENT, "SCAN_QUESTION:   "), BLOCK)
check("-All blocks even with a question",
      cmd('powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" -All',
          "SCAN_QUESTION: any missing-encoding-read after the template change"), BLOCK)
check("-All blocks even with a rule",
      cmd('powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" -All -Rule missing-encoding-read'), BLOCK)
check("subagent blocks even with a rule",
      cmd('powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" datrix-common -Rule missing-encoding-read',
          "", agent_id="agent-1"), BLOCK)
check("subagent blocks even with a question",
      cmd(INCIDENT, "SCAN_QUESTION: silent fallbacks in the new helper", agent_id="agent-1"), BLOCK)

print("== targeted or justified scans stay allowed ==")
check("named rule", cmd('powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" datrix-common -Rule missing-encoding-read'), ALLOW)
check("stated question",
      cmd(INCIDENT, "SCAN_QUESTION: does the new sqlite3 helper read a file without an encoding"), ALLOW)
check("-ListRules is a read of the rule set",
      cmd('powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" -ListRules',
          "SCAN_QUESTION: which rules exist"), ALLOW)

print("== reading the scripts and unrelated commands stay allowed ==")
check("grep the wrapper", cmd("grep -n Rule d:/datrix/datrix/scripts/dev/semgrep.ps1"), ALLOW)
check("cat the wrapper", cmd("cat d:/datrix/datrix/scripts/dev/libcst.ps1"), ALLOW)
check("test.ps1 is another guard's business",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/a.py"'), ALLOW)
check("git status", cmd("git -C d:/datrix/datrix-common status --porcelain"), ALLOW)
check("PowerShell tool payload", run({"tool_name": "PowerShell", "tool_input": {"command": "Get-ChildItem"}}), ALLOW)

print()
if fails:
    print("FAILURES:")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("all checks passed")
