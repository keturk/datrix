"""Exercise digest-red-test-run.py: a local model's digest of a red test run's log.

``context_for`` is driven in-process against a temp workspace (a framework repository and a
customer-style one) and a real Ollama-shaped server on loopback; the hook's entry point
is driven as a subprocess for the cases that must never touch a model. Both directions, on
purpose:

  DIGEST -- a package block whose status is not PASSED, with a log in scope.
  SILENT -- a green run, a command that is not a test run, a log outside the read scope, a
            missing log, no model server, more red runs than the cap, unparseable input.

A hook that digests green runs, or fails a tool call because a model server is down, would
cost more than it saves.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = os.path.dirname(os.path.abspath(__file__))
fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


spec = importlib.util.spec_from_file_location("digest_red_test_run", os.path.join(HOOKS, "digest-red-test-run.py"))
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook.add_scripts_lib_to_path()
from datrix_scripts.customer_domain_isolation import corpus_path  # noqa: E402
from datrix_scripts.local_llm import LocalLlmSettings  # noqa: E402
from datrix_scripts.local_llm_loopback import LOOPBACK, LoopbackOllama, answering, closed_port  # noqa: E402
from datrix_scripts.run_digest import DIGEST_FILENAME  # noqa: E402

ANSWER = "1. AssertionError: boom, 2 times, first at datrix-alpha/.test_results/test-results-1/full.log:4"


def settings_for(port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=port, usage_log=usage_log, caller=hook.CALLER)


def make_run(workspace: Path, repo: str, stamp: str, structured: bool = True) -> Path:
    run = workspace / repo / ".test_results" / f"test-results-{stamp}"
    run.mkdir(parents=True)
    (run / "full.log").write_text(
        "collected 3 items\nrunning\nE   AssertionError: boom\nE   AssertionError: boom\n2 failed, 1 passed\n",
        encoding="utf-8")
    (run / "index.json").write_text("{}", encoding="utf-8")
    if structured:
        (run / "failure-data.json").write_text("{}", encoding="utf-8")
    return run


def console(*blocks: tuple[str, str, Path]) -> str:
    return "Running tests...\n" + "".join(
        f"\n[{status}] {package}\n  fail: 2\n  Details: {run / 'index.json'}\n" for status, package, run in blocks)


def run_hook(command: str, response: object, raw: str | None = None) -> tuple[int, str]:
    payload = raw if raw is not None else json.dumps(
        {"tool_name": "PowerShell", "tool_input": {"command": command}, "tool_response": response})
    process = subprocess.run([sys.executable, os.path.join(HOOKS, "digest-red-test-run.py")], input=payload,
                             capture_output=True, text=True, timeout=60)
    return process.returncode, process.stdout


with tempfile.TemporaryDirectory(prefix="digest-hook-") as temp, \
        LoopbackOllama(answering(ANSWER), ("digest-model",)) as server:
    workspace = Path(temp)
    for repo in ("datrix", "datrix-alpha", "acme-shop"):
        (workspace / repo / ".git").mkdir(parents=True)
    # Nothing reaches a local model without the customer-term corpus; an empty one is a legitimate checkout.
    corpus = corpus_path(workspace / "datrix")
    corpus.parent.mkdir(parents=True)
    corpus.write_text(json.dumps({"algorithm": "sha256", "min_token_length": 5, "terms": []}), encoding="utf-8")
    usage = workspace / "usage.jsonl"
    settings = settings_for(server.port, usage)
    red = make_run(workspace, "datrix-alpha", "1")
    green = make_run(workspace, "datrix-alpha", "2")
    customer = make_run(workspace, "acme-shop", "3")

    print("== parsing the console summary ==")
    parsed = hook.red_runs(console(("PASSED", "pkg-a", green), ("FAILED", "pkg-b", red), ("ERROR", "pkg-c", customer)))
    check("only non-PASSED blocks, with their run folders", parsed, [("pkg-b", red), ("pkg-c", customer)])
    check("a Details line that is not an index.json is ignored",
          hook.red_runs("[FAILED] pkg-d\n  Details: D:\\somewhere\\summary.txt\n"), [])
    check("a nested response is flattened to its strings",
          hook.response_text({"stdout": "a", "meta": {"stderr": ["b", "c"]}, "code": 1}), "a\nb\nc")

    print("== DIGEST: a red run in scope ==")
    context = hook.context_for(console(("FAILED", "datrix-alpha", red)), workspace, settings)
    check("the digest is in the context", ANSWER in context, True)
    check("it names the package and the log", "datrix-alpha" in context and "full.log" in context, True)
    check("it points at the structured data the run saved", str(red / "failure-data.json") in context, True)
    check("it tells the agent not to read the log whole", "Do not read full.log whole" in context, True)
    check("the model was sent the numbered log lines", "3| E   AssertionError: boom" in server.chats[-1].user, True)
    unstructured = make_run(workspace, "datrix-alpha", "4", structured=False)
    context = hook.context_for(console(("FAILED", "datrix-alpha", unstructured)), workspace, settings)
    check("with no failure-data.json it names the collector", "collect-failure-data.ps1" in context, True)
    callers = [json.loads(line)["caller"] for line in usage.read_text(encoding="utf-8").splitlines()]
    check("every request is in the usage log under the hook's name", set(callers), {"hook:red-test-digest"})

    print("== SILENT: every way the hook must add nothing ==")
    check("the hook's digest file name is the one test.ps1's digest writes", hook.RUN_DIGEST_NAME, DIGEST_FILENAME)
    digested = make_run(workspace, "datrix-alpha", "5")
    (digested / DIGEST_FILENAME).write_text("Failure digest: datrix-alpha FAILED\n", encoding="utf-8")
    before = len(server.chats)
    check("a red run test.ps1 already digested",
          hook.context_for(console(("FAILED", "datrix-alpha", digested)), workspace, settings), "")
    check("which reached no model", len(server.chats), before)
    mixed = hook.context_for(console(("FAILED", "datrix-alpha", digested), ("FAILED", "datrix-alpha", red)),
                             workspace, settings)
    check("a digested run does not use up the cap: the undigested one is still digested",
          (mixed.count("Local-model digest of"), str(red / "full.log") in mixed), (1, True))
    before = len(server.chats)
    check("a green run", hook.context_for(console(("PASSED", "datrix-alpha", green)), workspace, settings), "")
    check("a red run whose log is outside the read scope",
          hook.context_for(console(("FAILED", "acme-shop", customer)), workspace, settings), "")
    missing = workspace / "datrix-alpha" / ".test_results" / "test-results-9"
    check("a red run with no log",
          hook.context_for(console(("FAILED", "datrix-alpha", missing)), workspace, settings), "")
    check("none of those reached a model", len(server.chats), before)
    dead = settings_for(closed_port(), usage)
    check("no model server answers: the result is untouched",
          hook.context_for(console(("FAILED", "datrix-alpha", red)), workspace, dead), "")
    runs = [make_run(workspace, "datrix-alpha", f"cap{n}") for n in range(4)]
    before = len(server.chats)
    capped = hook.context_for(console(*(("FAILED", "datrix-alpha", r) for r in runs)), workspace, settings)
    check("at most MAX_RUNS runs are digested", (capped.count("Local-model digest of"), len(server.chats) - before),
          (hook.MAX_RUNS, hook.MAX_RUNS))

    print("== the entry point ==")
    check("not a test command", run_hook("git status", "[FAILED] pkg\n  Details: x\\index.json"), (0, ""))
    check("a test command with a green result",
          run_hook("& test.ps1 datrix-common -Specific a.py", console(("PASSED", "datrix-alpha", green))), (0, ""))
    check("a red result whose log does not exist",
          run_hook("& test.ps1 datrix-common -Tag x", {"stdout": console(("FAILED", "datrix-alpha", missing))}),
          (0, ""))
    check("unparseable input", run_hook("", None, raw="{not json"), (0, ""))
    check("a non-shell tool", run_hook("", None, raw=json.dumps({"tool_name": "Read", "tool_input": {}})), (0, ""))

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
