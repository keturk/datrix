"""Exercise redirect-identifier-grep.py: the first grep for one identifier gets the index's answer.

``decide`` is driven in-process against a temp workspace (framework repositories and a
customer-style repository) with the real code index over it; the entry point is driven as a
subprocess for the cases that must never reach the index. Both directions, on purpose:

  REDIRECT -- the first grep, by one agent, for one identifier the index defines, fenced to
              Python or to nothing, over a framework repository or the workspace.
  ALLOW -- the repeat of that grep, a regex, a case-insensitive or multiline search, a grep
           fenced to another language, a search outside the framework repositories, a name the
           index defines nowhere, any other tool, unparseable input.

A hook that refuses a grep it should not have, or twice, wedges an agent; one that never
refuses saves nothing.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = os.path.dirname(os.path.abspath(__file__))
SESSION = "TEST-redirect-identifier-grep"
fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


spec = importlib.util.spec_from_file_location("redirect_identifier_grep",
                                              os.path.join(HOOKS, "redirect-identifier-grep.py"))
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def grep(pattern: str, path: Path | str, agent: str = "", cwd: Path | None = None, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"tool_name": "Grep", "tool_input": {"pattern": pattern, "path": str(path), **extra},
                                  "session_id": SESSION, "cwd": str(cwd if cwd is not None else path)}
    if agent:
        payload["agent_id"] = agent
    return payload


def run_hook(payload: object, raw: str | None = None) -> tuple[int, str]:
    process = subprocess.run([sys.executable, os.path.join(HOOKS, "redirect-identifier-grep.py")],
                             input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True,
                             timeout=60)
    return process.returncode, process.stderr


def cleanup_state() -> None:
    for item in Path(hook._STATE_DIR).glob(f"grep-redirect-{SESSION}*.json"):
        item.unlink(missing_ok=True)


print("== the name a pattern asks for ==")
for pattern, name in (("\\bto_words\\b", "to_words"), ("def to_words", "to_words"), ("class Splitter", "Splitter"),
                      ("to_words\\(", "to_words"), ("alpha_pkg\\.text\\.to_words", "alpha_pkg.text.to_words")):
    check(f"{pattern!r} asks for {name!r}", hook.bare_name(pattern), name)

cleanup_state()
try:
    with tempfile.TemporaryDirectory(prefix="grep-redirect-hook-") as temp:
        workspace = Path(temp)
        for repo in ("datrix", "datrix-alpha", "acme-shop"):
            (workspace / repo).mkdir()
            subprocess.run(["git", "-C", str(workspace / repo), "init", "-q"], check=True, capture_output=True)
        alpha = workspace / "datrix-alpha"
        write(alpha / "src/alpha_pkg/__init__.py", "")
        write(alpha / "src/alpha_pkg/text.py",
              '"""Text helpers."""\n\n\ndef to_words(name: str) -> list[str]:\n    """Split a name into words."""\n'
              '    return name.split("_")\n')
        write(alpha / "src/alpha_pkg/use.py",
              '"""Uses of the helper."""\nfrom alpha_pkg.text import to_words\n\n\n'
              'def split(name: str) -> list[str]:\n    return to_words(name)\n')
        customer = write(workspace / "acme-shop/src/shop.py", "def to_words(x: str) -> str:\n    return x\n").parent

        repeats: list[str] = []

        def decide(payload: dict[str, object]) -> str:
            return hook.decide(payload, workspace, on_repeat=lambda: repeats.append("repeat"))

        print("== REDIRECT: the first grep for an identifier the index defines ==")
        message = decide(grep("\\bto_words\\b", alpha))
        check("it is refused with the index's answer", message.startswith("GREP REDIRECTED") and "'to_words'" in message,
              True)
        check("the answer names the definition", "datrix-alpha/src/alpha_pkg/text.py:4" in message, True)
        check("a bare name also gets its uses, through the import",
              "Uses:" in message and "datrix-alpha/src/alpha_pkg/use.py" in message, True)
        check("it says how to get the grep anyway", "repeat the same Grep" in message, True)
        definition = decide(grep("def to_words", alpha, agent="a1"))
        check("'def X' asks for the definition only",
              "text.py:4" in definition and "Uses:" not in definition, True)
        check("the whole workspace is a search the index covers",
              "GREP REDIRECTED" in decide(grep("to_words", workspace, agent="a2")), True)
        check("a relative path is taken from the agent's directory",
              "GREP REDIRECTED" in decide(grep("to_words", "src", agent="a3", cwd=alpha)), True)
        check("a grep fenced to Python", "GREP REDIRECTED" in decide(grep("to_words", alpha, agent="a4", type="py")),
              True)

        print("== ALLOW: every way a grep must go through ==")
        check("nothing was a repeat yet", repeats, [])
        check("the repeat of the same name", decide(grep("to_words\\(", alpha)), "")
        check("and it is reported as a repeat, so the usage report can count it", repeats, ["repeat"])
        for label, payload in (
            ("a regex that is not one identifier", grep("to_.*words", alpha, agent="b1")),
            ("a case-insensitive search", grep("to_words", alpha, agent="b2", **{"-i": True})),
            ("a multiline search", grep("to_words", alpha, agent="b3", multiline=True)),
            ("a grep fenced to another language by type", grep("to_words", alpha, agent="b4", type="js")),
            ("a grep fenced to another language by glob", grep("to_words", alpha, agent="b5", glob="*.ts")),
            ("a grep of one non-Python file", grep("to_words", alpha / "README.md", agent="b6", cwd=alpha)),
            ("a search in a repository the index does not cover", grep("to_words", customer, agent="b7")),
            ("a name the index defines nowhere", grep("never_defined_here", alpha, agent="b8")),
            ("another tool", {"tool_name": "Glob", "tool_input": {"pattern": "to_words"}, "session_id": SESSION}),
        ):
            check(label, decide(payload), "")
        check("an allowed grep was not marked as told, so nothing is held against the agent",
              hook._told(hook._state_path(SESSION, "b8")), [])

        print("== the entry point ==")
        check("a regex", run_hook(grep("to_.*words", alpha)), (0, ""))
        check("another tool", run_hook({"tool_name": "Read", "tool_input": {"file_path": "x.py"}}), (0, ""))
        check("unparseable input", run_hook(None, raw="{not json"), (0, ""))
        check("input that is not an object", run_hook(None, raw="[1, 2]"), (0, ""))
        check("a search outside the real workspace's framework repositories", run_hook(grep("to_words", customer)),
              (0, ""))
finally:
    cleanup_state()

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
