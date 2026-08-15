"""Exercise guard-shell-file-writes.py with synthetic payloads.

Both directions are asserted. A guard that blocks the incident shape but also
blocks ordinary shell work gets routed around within a turn, which is worse than
no guard: it teaches the agent that the block is noise.

The BLOCK cases are the exact commands from the session that motivated this hook.
The ALLOW cases are commands issued in that same session that must keep working.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-shell-file-writes.py")
fails = []


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode, p.stderr


def cmd(command, tool="Bash"):
    return run({"tool_name": tool, "tool_input": {"command": command}})


def check(label, command, want, tool="Bash"):
    got, stderr = cmd(command, tool)
    if got != want:
        verb = "block" if want == 2 else "allow"
        fails.append(f"[{label}] expected {verb} ({want}), got {got}\n    {command}")
    elif want == 2 and "Write" not in stderr:
        fails.append(f"[{label}] blocked without naming the right tool to use instead")


# ---------------------------------------------------------------------------
# MUST BLOCK -- the shapes that caused this hook to exist.
# ---------------------------------------------------------------------------
check("heredoc append to a test file",
      "cat >> tests/generators/cross_cutting/test_log_categories.py <<'APPEND'\nfoo\nAPPEND", 2)
check("heredoc overwrite",
      "cat > src/datrix_common/thing.py <<'EOF'\nx = 1\nEOF", 2)
check("inline python writing a source file",
      "python - <<'PY'\nimport pathlib\npathlib.Path('a.py').write_text('x')\nPY", 2)
check("python -c writing a source file",
      "python -c \"open('src/x.py','w').write('hi')\"", 2)
check("echo into a source file",
      "echo 'x = 1' > src/datrix_common/x.py", 2)
check("printf append into a source file",
      "printf 'x\\n' >> docs/notes.md", 2)
check("node -e writing a file",
      "node -e \"require('fs').writeFileSync('a.ts','x')\"", 2)
check("PowerShell Set-Content",
      "Set-Content -Path src\\x.py -Value 'x = 1'", 2, tool="PowerShell")
check("PowerShell Out-File",
      "'x' | Out-File -FilePath src\\x.py", 2, tool="PowerShell")
check("New-Item with content",
      "New-Item -Path src\\x.py -ItemType File -Value 'x'", 2, tool="PowerShell")

# ---------------------------------------------------------------------------
# MUST ALLOW -- ordinary work from the same session.
# ---------------------------------------------------------------------------
check("reading a file", "cat src/datrix_common/config/observability/models.py", 0)
check("grep with a redirect-looking pattern", "grep -n 'a > b' src/x.py", 0)
check("stderr plumbing", "some-tool 2>&1 | tail -5", 0)
check("discard stdout", "noisy-command > /dev/null", 0)
check("PowerShell null discard", "Get-Thing 2>$null", 0, tool="PowerShell")
check("redirect into workspace scratch",
      "powershell -File d:/x/test.ps1 > d:/datrix/.test-output/run.log", 0)
check("redirect into the session scratchpad",
      "python census.py > /c/Users/x/Temp/claude/d--datrix/abc/scratchpad/out.txt", 0)
check("running a test suite", 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common', 0)
check("running a generator", 'powershell -File "d:/g/storefront/scripts/dev/generate.ps1"', 0)
check("git operations", "git -C datrix-common status --porcelain", 0)
check("mkdir", "New-Item -ItemType Directory -Force d:/datrix/.tmp", 0, tool="PowerShell")
check("inline python that only READS and prints",
      "python -c \"import pathlib; print(pathlib.Path('a.py').read_text())\"", 0)
check("inline python running a real check",
      "python -c \"from datrix_common.config.observability.models import LogCategoryLevels; print(LogCategoryLevels())\"", 0)
check("a real script writing files as its job",
      "d:/datrix/.venv/Scripts/python.exe scripts/build_thing.py --out d:/datrix/.tmp", 0)

# ---------------------------------------------------------------------------
# MUST FAIL OPEN.
# ---------------------------------------------------------------------------
rc, _ = run({"tool_name": "Bash", "tool_input": {}})
if rc != 0:
    fails.append(f"[empty command] expected allow (0), got {rc}")
rc, _ = run({"tool_name": "Write", "tool_input": {"file_path": "x.py"}})
if rc != 0:
    fails.append(f"[non-shell tool] expected allow (0), got {rc}")
p = subprocess.run([sys.executable, HOOK], input="not json",
                   capture_output=True, text=True)
if p.returncode != 0:
    fails.append(f"[malformed payload] expected allow (0), got {p.returncode}")

if fails:
    print("FAILURES:")
    for line in fails:
        print("  -", line)
    sys.exit(1)
print("guard-shell-file-writes.py: all cases pass")
