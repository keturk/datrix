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
INCIDENT = ('cd /d/datrix; powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" '
            "datrix-codegen-python datrix-common datrix-codegen-common 2>&1 | tail -15")

print("== the incident and its relatives block ==")
check("incident: three-package semgrep, no rule, no question",
      cmd(INCIDENT, "Run semgrep anti-pattern scan on the three touched packages"), BLOCK)
check("libcst one package, bare", cmd('powershell -File "d:/datrix/datrix/scripts/scan/libcst.ps1" datrix-common'), BLOCK)
check("ast-grep direct .ps1 form", cmd(r".\scripts\scan\ast-grep.ps1 datrix-cli"), BLOCK)
check("empty question marker does not lift it",
      cmd(INCIDENT, "SCAN_QUESTION:   "), BLOCK)
check("-All blocks even with a question",
      cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" -All',
          "SCAN_QUESTION: any missing-encoding-read after the template change"), BLOCK)
check("-All blocks even with a rule",
      cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" -All -Rule missing-encoding-read'), BLOCK)
check("subagent blocks even with a rule",
      cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" datrix-common -Rule missing-encoding-read',
          "", agent_id="agent-1"), BLOCK)
check("subagent blocks even with a question",
      cmd(INCIDENT, "SCAN_QUESTION: silent fallbacks in the new helper", agent_id="agent-1"), BLOCK)

print("== targeted or justified scans stay allowed ==")
check("named rule", cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" datrix-common -Rule missing-encoding-read'), ALLOW)
check("stated question",
      cmd(INCIDENT, "SCAN_QUESTION: does the new sqlite3 helper read a file without an encoding"), ALLOW)
check("-ListRules is a read of the rule set",
      cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" -ListRules',
          "SCAN_QUESTION: which rules exist"), ALLOW)

print("== a scanner's POSIX twin and its module are the same scan ==")
SEMGREP_TWIN = "d:/datrix/datrix/scripts/scan/semgrep.sh"
LIBCST_TWIN = "d:/datrix/datrix/scripts/scan/libcst.sh"
AST_GREP_TWIN = "d:/datrix/datrix/scripts/scan/ast-grep.sh"
VENV_PYTHON = r"D:\datrix\.venv\Scripts\python.exe"
check("twin --all blocks", cmd(f"bash {SEMGREP_TWIN} --all"), BLOCK)
check("twin --all blocks even with a rule", cmd(f"bash {AST_GREP_TWIN} --all --rule=empty-except-pass"), BLOCK)
check("twin run directly, bare package", cmd(f"{LIBCST_TWIN} --projects=datrix-common"), BLOCK)
check("twin one package, no rule", cmd(f"bash {SEMGREP_TWIN} --projects=datrix-common"), BLOCK)
check("twin in a subagent blocks even with a rule",
      cmd(f"bash {SEMGREP_TWIN} --projects=datrix-common --rule=missing-encoding-read", agent_id="agent-1"), BLOCK)
check("module --all blocks", cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.semgrep --all"), BLOCK)
check("module under -I, bare package", cmd(f"{VENV_PYTHON} -Im datrix_scripts.scan.ast_grep --projects=datrix-cli"), BLOCK)
check("module libcst, bare package", cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.libcst --projects=datrix-cli"), BLOCK)
check("twin with a named rule", cmd(f"bash {SEMGREP_TWIN} --projects=datrix-common --rule=missing-encoding-read"), ALLOW)
check("twin with a rule, space form", cmd(f"bash {AST_GREP_TWIN} --projects=datrix-cli --rule empty-except-pass"), ALLOW)
check("twin with a one-off pattern", cmd(f"bash {AST_GREP_TWIN} --projects=datrix-cli --pattern='raise Exception($M)'"), ALLOW)
check("module with a named rule",
      cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.semgrep --projects=datrix-common --rule=empty-except-pass"), ALLOW)
check("twin with a stated question",
      cmd(f"bash {LIBCST_TWIN} --projects=datrix-common", "SCAN_QUESTION: silent fallbacks in the new loader"), ALLOW)
check("twin self-test reads planted inputs only", cmd(f"bash {LIBCST_TWIN} --self-test"), ALLOW)
check("module self-test", cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.semgrep --self-test"), ALLOW)
check("wrapper self-test", cmd('powershell -File "d:/datrix/datrix/scripts/scan/ast-grep.ps1" -SelfTest'), ALLOW)
check("-All -SelfTest still sweeps", cmd('powershell -File "d:/datrix/datrix/scripts/scan/semgrep.ps1" -All -SelfTest'), BLOCK)
check("reading a twin", cmd(f"cat {SEMGREP_TWIN}"), ALLOW)
check("another scan module is not a scanner",
      cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.syntax_checker --path=datrix-common"), ALLOW)
check("a module whose name merely starts with a scanner's",
      cmd(f"{VENV_PYTHON} -m datrix_scripts.scan.semgrep_rules --all"), ALLOW)

print("== the parity cases gate runs tagged or as its self-test ==")
PARITY = '"d:/datrix/datrix/scripts/gates/parity/parity-cases-gate.ps1"'
check("untagged parity cases run blocks", cmd(f"powershell -File {PARITY}"), BLOCK)
check("untagged with -Dbg still blocks", cmd(f"powershell -File {PARITY} -Dbg"), BLOCK)
check("a question marker does not lift it", cmd(f"powershell -File {PARITY}", "SCAN_QUESTION: all rows"), BLOCK)
check("direct .ps1 form blocks", cmd(r".\scripts\gates\parity\parity-cases-gate.ps1"), BLOCK)
check("tagged run", cmd(f"powershell -File {PARITY} -Tag rest-api"), ALLOW)
check("self-test", cmd(f"powershell -File {PARITY} -SelfTest"), ALLOW)
check("the authoring tool is not the gate", cmd('powershell -File "d:/datrix/datrix/scripts/gates/parity/parity-cases.ps1" check'), ALLOW)
check("reading the gate", cmd("cat d:/datrix/datrix/scripts/gates/parity/parity-cases-gate.ps1"), ALLOW)
PARITY_TWIN = "d:/datrix/datrix/scripts/gates/parity/parity-cases-gate.sh"
PARITY_MODULE = r"D:\datrix\.venv\Scripts\python.exe -m datrix_scripts.gates.parity.parity_cases_gate"
check("untagged POSIX twin blocks", cmd(f"bash {PARITY_TWIN}"), BLOCK)
check("untagged POSIX twin run directly blocks", cmd(f"{PARITY_TWIN} --dbg"), BLOCK)
check("untagged module run blocks", cmd(PARITY_MODULE), BLOCK)
check("untagged module run under -I blocks", cmd(PARITY_MODULE.replace(" -m ", " -Im ")), BLOCK)
check("tagged POSIX twin", cmd(f"bash {PARITY_TWIN} --tag rest-api"), ALLOW)
check("tagged POSIX twin, = form", cmd(f"bash {PARITY_TWIN} --tag=rest-api"), ALLOW)
check("POSIX twin self-test", cmd(f"bash {PARITY_TWIN} --self-test"), ALLOW)
check("tagged module run", cmd(f"{PARITY_MODULE} --tag=rest-api"), ALLOW)
check("one untagged run among tagged ones blocks",
      cmd(f"bash {PARITY_TWIN} --tag rest-api; bash {PARITY_TWIN}"), BLOCK)
check("reading the twin", cmd(f"cat {PARITY_TWIN}"), ALLOW)
check("the authoring tool's module is not the gate",
      cmd(r"D:\datrix\.venv\Scripts\python.exe -m datrix_scripts.gates.parity.parity_cases check"), ALLOW)

print("== reading the scripts and unrelated commands stay allowed ==")
check("grep the wrapper", cmd("grep -n Rule d:/datrix/datrix/scripts/scan/semgrep.ps1"), ALLOW)
check("cat the wrapper", cmd("cat d:/datrix/datrix/scripts/scan/libcst.ps1"), ALLOW)
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
