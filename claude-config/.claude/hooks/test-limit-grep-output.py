"""Exercise limit-grep-output.py: a content search with no head_limit gets the smaller default.

Both directions, on purpose:

  REWRITE -- a content-mode Grep inside the workspace with no head_limit: the input comes back
             with head_limit set and every other field unchanged, answered as `allow`.
  PASS AS SENT -- an explicit head_limit (0 included), another output mode, a search rooted
             outside the workspace (the rewrite's `allow` must never grant a read the permission
             system would ask about), another tool, unparseable input.
"""
import importlib.util
import json
import os
import subprocess
import sys

HOOKS = os.path.dirname(os.path.abspath(__file__))
fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


spec = importlib.util.spec_from_file_location("limit_grep_output", os.path.join(HOOKS, "limit-grep-output.py"))
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

INSIDE = os.path.join(hook.WORKSPACE, "datrix")
OUTSIDE = os.path.dirname(os.path.realpath(hook.WORKSPACE)) or "/"


def grep(cwd: str = INSIDE, **tool_input: object) -> dict[str, object]:
    return {"tool_name": "Grep", "tool_input": {"pattern": "x", **tool_input}, "cwd": cwd}


def run_hook(payload: object, raw: str | None = None) -> tuple[int, str]:
    process = subprocess.run([sys.executable, os.path.join(HOOKS, "limit-grep-output.py")],
                             input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True,
                             timeout=30)
    return process.returncode, process.stdout


print("== REWRITE: a content search with no head_limit ==")
check("the default limit is added, the rest unchanged",
      hook.rewritten_input(grep(output_mode="content", glob="*.md")),
      {"pattern": "x", "output_mode": "content", "glob": "*.md", "head_limit": hook.DEFAULT_HEAD_LIMIT})
check("an explicit path inside the workspace is rewritten too",
      hook.rewritten_input(grep(cwd=OUTSIDE, output_mode="content", path=INSIDE)).get("head_limit"),
      hook.DEFAULT_HEAD_LIMIT)
code, out = run_hook(grep(output_mode="content"))
answer = json.loads(out)["hookSpecificOutput"] if out else {}
check("the entry point answers allow with the updated input",
      (code, answer.get("permissionDecision"), answer.get("updatedInput", {}).get("head_limit")),
      (0, "allow", hook.DEFAULT_HEAD_LIMIT))

print("== PASS AS SENT ==")
check("an explicit head_limit", hook.rewritten_input(grep(output_mode="content", head_limit=500)), {})
check("head_limit 0 (unlimited, asked for)", hook.rewritten_input(grep(output_mode="content", head_limit=0)), {})
check("files_with_matches mode", hook.rewritten_input(grep(output_mode="files_with_matches")), {})
check("the default mode (no output_mode)", hook.rewritten_input(grep()), {})
check("a search rooted outside the workspace", hook.rewritten_input(grep(cwd=OUTSIDE, output_mode="content")), {})
check("a relative path that climbs out of the workspace",
      hook.rewritten_input(grep(output_mode="content", path="../../..")), {})
check("another tool", hook.rewritten_input({"tool_name": "Read", "tool_input": {"file_path": "a"}}), {})
check("unparseable input", run_hook(None, raw="{not json"), (0, ""))
check("input that is not an object", run_hook(None, raw="[1, 2]"), (0, ""))

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
