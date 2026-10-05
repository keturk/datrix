"""Exercise guard-committed-content.py with real files in a real repository-shaped tree.

Every case applies a real Write or Edit payload and asserts both directions: a design/task reference
or a registered customer term ADDED to committed content blocks; the same content already there,
content in an ignored or unscanned place, and files outside the framework repositories never do.
The term corpus is a temporary one registering a made-up word (DATRIX_TERM_CORPUS), so no real
customer term is needed or printed.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-committed-content.py")
TERM = "zzgatecustomer"
BLOCK, ALLOW = 2, 0
fails: list[str] = []


def run(payload: dict[str, object], env: dict[str, str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def put(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def remove_tree(root: str) -> None:
    for base, dirs, files in os.walk(root, topdown=False):
        for name in files:
            path = os.path.join(base, name)
            os.chmod(path, 0o666)
            os.remove(path)
        for name in dirs:
            os.rmdir(os.path.join(base, name))
    os.rmdir(root)


with tempfile.TemporaryDirectory(prefix="committed-content-corpus-") as corpus_dir:
    corpus = put(os.path.join(corpus_dir, "terms.json"), json.dumps({
        "algorithm": "sha256", "min_token_length": 5,
        "terms": [{"hash": hashlib.sha256(TERM.encode("utf-8")).hexdigest(), "hint": "gate fixture"}]}))
    env = {**os.environ, "DATRIX_TERM_CORPUS": corpus}
    root = os.path.join(r"d:\datrix", f"datrix-ccgate-{os.getpid()}")
    os.makedirs(root)
    try:
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, capture_output=True)
        put(os.path.join(root, ".gitignore"), "ignored/\n")
        src = put(os.path.join(root, "src", "pkg", "mod.py"), '"""A module."""\n\nX = 1\n')

        def edit(path: str, old: str, new: str) -> int:
            return run({"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}},
                       env)[0]

        def write(path: str, content: str) -> int:
            return run({"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}, env)[0]

        print("== design and task references ==")
        check("a task-file id in a source comment", edit(src, "X = 1", "# see task-41-07\nX = 1"), BLOCK)
        check("a design path in a docstring", edit(src, '"""A module."""', '"""Implements design/044-x.md."""'), BLOCK)
        check("'design doc 044' in docs", write(os.path.join(root, "docs", "a.md"), "Per design doc 044, do it.\n"),
              BLOCK)
        check("a reference outside the scanned subtrees (repo root README)",
              write(os.path.join(root, "README.md"), "Per design doc 044.\n"), ALLOW)
        check("a plain number stays allowed", edit(src, "X = 1", "X = 44  # forty-four widgets"), ALLOW)

        print("== customer terms ==")
        check("a registered term added to source", edit(src, "X = 1", f"X = '{TERM}'"), BLOCK)
        check("a registered term in a new file anywhere in the repo",
              write(os.path.join(root, "config", "x.yaml"), f"name: {TERM}\n"), BLOCK)
        check("a term in a git-ignored path", write(os.path.join(root, "ignored", "x.txt"), f"{TERM}\n"), ALLOW)
        code, err = run({"tool_name": "Edit", "tool_input": {"file_path": src, "old_string": "X = 1",
                                                              "new_string": f"X = '{TERM}'"}}, env)
        check("the message never prints the term itself", TERM not in err and "customer term" in err, True)

        print("== only the delta is judged ==")
        legacy = put(os.path.join(root, "src", "pkg", "legacy.py"), f"# see task-41-07\nNAME = '{TERM}'\nY = 1\n")
        check("an unrelated edit to a file that already carries both", edit(legacy, "Y = 1", "Y = 2"), ALLOW)
        check("removing them", edit(legacy, f"# see task-41-07\nNAME = '{TERM}'\n", ""), ALLOW)

        print("== out of scope / fails open ==")
        check("a file outside the framework repos", write(r"d:\datrix\acme-shop\notes.md", f"{TERM} task-41-07\n"), ALLOW)
        check("an Edit whose old_string is not in the file", edit(src, "no such text", "task-41-07"), ALLOW)
        check("a design doc itself (outside every repo)",
              write(r"d:\datrix\design\999-gate-fixture.md", "Depends on task-41-07.\n"), ALLOW)
        check("NotebookEdit is ignored", run({"tool_name": "NotebookEdit", "tool_input": {"file_path": src}}, env)[0],
              ALLOW)
        broken_env = {**env, "DATRIX_TERM_CORPUS": os.path.join(corpus_dir, "missing.json")}
        check("an unreadable corpus fails open",
              run({"tool_name": "Edit", "tool_input": {"file_path": src, "old_string": "X = 1",
                                                       "new_string": f"X = '{TERM}'"}}, broken_env)[0], ALLOW)
    finally:
        remove_tree(root)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
