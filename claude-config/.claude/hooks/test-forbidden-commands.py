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
      cmd("cd /d/datrix/datrix-codegen-python && /d/datrix/.venv/Scripts/mypy.exe src/datrix_codegen_python"),
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
check("the wrapper's Python entry point",
      cmd("D:/datrix/.venv/Scripts/python.exe d:/datrix/datrix/scripts/test/lib/mypy_check.py datrix-cli"),
      BLOCK)
check("affected-gate with the opt-in switch",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1" -Projects datrix-common -Mypy'),
      BLOCK)

print("== type-checkers: reading, cleaning up and neighbours stay allowed ==")
check("reading the wrapper",
      cmd('grep -n "cache-dir" d:/datrix/datrix/scripts/test/mypy.ps1'), ALLOW)
check("paging the wrapper's Python entry point",
      cmd("sed -n '1,80p' /d/datrix/datrix/scripts/test/lib/mypy_check.py"), ALLOW)
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
      cmd("python -m py_compile d:/datrix/datrix/scripts/test/lib/mypy_check.py"), ALLOW)
check("compiling the wrapper's directory",
      cmd("python -m compileall d:/datrix/datrix/scripts/test/lib"), ALLOW)

print("== /resolve-conflicts: the window opens only on Jon's own invocation ==")
TRANSCRIPT_DIR = r"D:\datrix\.tmp"
INVOKED = ("<command-message>resolve-conflicts</command-message>\n"
           "<command-name>/resolve-conflicts</command-name>\n"
           "<command-args>datrix-common</command-args>")


def transcript(name, entries):
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    path = os.path.join(TRANSCRIPT_DIR, f"forbidden-commands-test-{name}.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return path


def user(content, **extra):
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def tool_result(text):
    return user([{"type": "tool_result", "tool_use_id": "t1", "content": text}])


OPEN = transcript("open", [
    user(INVOKED),
    user([{"type": "text", "text": "Base directory for this skill: ..."}], isMeta=True),
    tool_result("error: Your local changes would be overwritten by merge"),
])
FOLLOW_UP = transcript("follow-up", [user(INVOKED), user("now fix the other thing")])
QUOTED = transcript("quoted", [
    user("why did <command-name>/resolve-conflicts</command-name> fail?")])
MODEL_INVOKED = transcript("model-invoked", [
    user("pull everything"),
    user([{"type": "text", "text": INVOKED}], isMeta=True),
])


def in_window(command, path=OPEN, tool="Bash"):
    return run({"tool_name": tool, "transcript_path": path,
                "tool_input": {"command": command}})


STASH_PATHS = "git stash push -m pull -- docs/a.md docs/b.md"
check("window: path-limited stash push", in_window(STASH_PATHS), ALLOW)
check("window: stash pop", in_window("git -C d:/datrix/datrix-common stash pop"), ALLOW)
check("window: stash drop", in_window("git stash drop stash@{0}"), ALLOW)
check("window: unstage paths", in_window("git reset -q -- docs/a.md"), ALLOW)
check("window: unstage all, HEAD", in_window("git reset HEAD"), ALLOW)
check("window: restore --staged", in_window("git restore --staged docs/a.md"), ALLOW)
check("window: take theirs", in_window("git checkout --theirs -- docs/a.md"), ALLOW)
check("window: full stash-pull-pop chain",
      in_window(f"cd /d/datrix/datrix-common && {STASH_PATHS} && git pull --ff-only "
                "&& git stash pop"), ALLOW)
check("window, PowerShell: stash push",
      in_window(f"git -C D:\\datrix\\datrix-common {STASH_PATHS}", tool="PowerShell"), ALLOW)

check("window still blocks: bare stash (everything)", in_window("git stash"), BLOCK)
check("window still blocks: stash push without paths", in_window("git stash push -m x"), BLOCK)
check("window still blocks: stash clear", in_window("git stash clear"), BLOCK)
check("window still blocks: reset --hard", in_window("git reset --hard origin/main"), BLOCK)
check("window still blocks: reset to another commit", in_window("git reset HEAD~1"), BLOCK)
check("window still blocks: reset --soft", in_window("git reset --soft HEAD"), BLOCK)
check("window still blocks: restore the working tree", in_window("git restore docs/a.md"), BLOCK)
check("window still blocks: restore --staged --worktree",
      in_window("git restore --staged --worktree docs/a.md"), BLOCK)
check("window still blocks: restore --staged --source",
      in_window("git restore --staged --source=HEAD~2 docs/a.md"), BLOCK)
check("window still blocks: checkout -- path", in_window("git checkout -- docs/a.md"), BLOCK)
check("window still blocks: checkout a ref", in_window("git checkout origin/main"), BLOCK)
check("window still blocks: revert", in_window("git revert HEAD"), BLOCK)
check("window still blocks: clean -fd", in_window("git clean -fd"), BLOCK)
check("window still blocks: an allowed call chained to reset --hard",
      in_window(f"{STASH_PATHS} && git reset --hard"), BLOCK)

check("closed: no transcript", cmd(STASH_PATHS), BLOCK)
check("closed: unreadable transcript",
      in_window(STASH_PATHS, path=r"D:\datrix\.tmp\no-such-transcript.jsonl"), BLOCK)
check("closed: a follow-up prompt ends the window", in_window(STASH_PATHS, FOLLOW_UP), BLOCK)
check("closed: the tag quoted mid-prompt", in_window(STASH_PATHS, QUOTED), BLOCK)
check("closed: meta text is not Jon's prompt", in_window(STASH_PATHS, MODEL_INVOKED), BLOCK)

print("== pytest invoked directly (test.ps1 owns the interpreter and the guards) ==")
check("bare pytest", cmd("pytest tests/unit/test_a.py"), BLOCK)
check("pytest -x", cmd("pytest -x -q"), BLOCK)
check("venv pytest.exe, absolute", cmd(r"D:\datrix\.venv\Scripts\pytest.exe datrix-common/tests"), BLOCK)
check("python -m pytest", cmd("python -m pytest tests/unit"), BLOCK)
check("venv python -m pytest", cmd("D:/datrix/.venv/Scripts/python.exe -m pytest -k foo"), BLOCK)
check("uv run pytest", cmd("uv run pytest tests"), BLOCK)
check("poetry run pytest", cmd("poetry run pytest"), BLOCK)
check("chained after cd", cmd("cd datrix-common && pytest tests/unit"), BLOCK)
check("PowerShell tool", cmd("pytest tests/unit", tool="PowerShell"), BLOCK)
check("test.ps1 -Specific stays allowed",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/test_a.py"'),
      ALLOW)
check("test.ps1 -Tag stays allowed",
      cmd('powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common datrix-cli -Tag config-resolution'),
      ALLOW)
check("a one-off script stays allowed", cmd("D:/datrix/.venv/Scripts/python.exe .scripts/probe.py"), ALLOW)
check("grep for pytest is a read", cmd("grep -rn pytest datrix-common/pyproject.toml"), ALLOW)
check("cat a pytest config is a read", cmd("cat datrix-common/pytest.ini"), ALLOW)
check("pip show pytest is not a run", cmd("D:/datrix/.venv/Scripts/python.exe -m pip show pytest"), ALLOW)
check("quoted mention in a commit message", cmd('git commit -m "stop calling pytest directly"'), ALLOW)

print("== polling loops inside one tool call ==")
check("until ... sleep", cmd("until test -f out.log; do sleep 5; done"), BLOCK)
check("while ... sleep", cmd("while ! curl -s localhost:8000; do sleep 2; done"), BLOCK)
check("multi-line until", cmd("until [ -f done ]\ndo\n  sleep 10\ndone"), BLOCK)
check("PowerShell while / Start-Sleep",
      cmd("while (-not (Test-Path out.log)) { Start-Sleep -Seconds 5 }", tool="PowerShell"), BLOCK)
check("PowerShell do/while Start-Sleep",
      cmd("do { Start-Sleep 3 } while (-not (Test-Path x))", tool="PowerShell"), BLOCK)
check("a for loop without sleep stays allowed", cmd("for f in a b c; do echo $f; done"), ALLOW)
check("a while-read loop stays allowed", cmd("while read -r l; do echo $l; done < list.txt"), ALLOW)
check("a plain command stays allowed", cmd("ls -la"), ALLOW)
check("grep for the loop text is a read", cmd('grep -n "until .*; do sleep" CLAUDE.md'), ALLOW)
check("echoing the rule in quotes is not a loop",
      cmd('echo "never write until x; do sleep 5; done"'), ALLOW)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
