"""Exercise digest-red-test-run.py: a local model's digest of a red test, gate or generation run's log.

``context_for`` is driven in-process against a temp workspace (a framework repository and a
customer-style one) and a real Ollama-shaped server on loopback; the hook's entry point
is driven as a subprocess for the cases that must never touch a model. Both directions, on
purpose:

  DIGEST -- a package block whose status is not PASSED, a gate's FAILED verdict line, a
            generation summary with a failed project -- each with a log in scope.
  SILENT -- a green run, a command that runs no script, a script only named, a log outside the
            read scope, a missing log, no model server, more red runs than the cap,
            unparseable input.

The gate verdict line is read from the real ``Write-DatrixGateVerdict`` (PowerShell), so the
hook's parser and the runner's printer cannot drift apart.

A hook that digests green runs, or fails a tool call because a model server is down, would
cost more than it saves.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

HOOKS = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = Path(HOOKS).parents[2] / "scripts" / "common"
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
TEST_SCRIPTS = [PurePosixPath("d:/datrix/datrix/scripts/test/test.ps1")]
GATE_SCRIPTS = [PurePosixPath("d:/datrix/datrix/scripts/gates/repo-hygiene/script-catalogue-gate.ps1")]
GENERATE_SCRIPTS = [PurePosixPath("d:/datrix/datrix/scripts/dev/generate.ps1")]


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


def make_log(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / name
    log.write_text("step 1\nERROR: gate check failed: boom\nERROR: gate check failed: boom\n", encoding="utf-8")
    return log


def console(*blocks: tuple[str, str, Path]) -> str:
    return "Running tests...\n" + "".join(
        f"\n[{status}] {package}\n  fail: 2\n  Details: {run / 'index.json'}\n" for status, package, run in blocks)


def generation_console(failed: int, log: Path) -> str:
    rule = "=" * 40
    return (f"[1/2] alpha: Success\n[2/2] beta: {'Failed' if failed else 'Success'}\n\n{rule}\n"
            f"Generation Summary\n{rule}\n  Total projects: 2\n  Successful:     {2 - failed}\n"
            f"  Failed:         {failed}\n{rule}\n\nLog saved to: {log}\n")


def gate_verdict_line(gate: str, exit_code: int, log: Path) -> str:
    """The verdict line the real Write-DatrixGateVerdict prints."""
    script = (f"Import-Module '{COMMON_DIR / 'DatrixPythonScript.psm1'}' -Force; "
              f"Write-DatrixGateVerdict -Gate '{gate}' -ExitCode {exit_code} -LogPath '{log}'")
    process = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=120)
    return process.stdout.strip()


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

    def test_context(text: str, with_settings: LocalLlmSettings = settings) -> str:
        return hook.context_for(hook.red_logs(TEST_SCRIPTS, text), workspace, with_settings)

    print("== parsing the console summary ==")
    parsed = hook.red_runs(console(("PASSED", "pkg-a", green), ("FAILED", "pkg-b", red), ("ERROR", "pkg-c", customer)))
    check("only non-PASSED blocks, with their run folders", parsed, [("pkg-b", red), ("pkg-c", customer)])
    check("a Details line that is not an index.json is ignored",
          hook.red_runs("[FAILED] pkg-d\n  Details: D:\\somewhere\\summary.txt\n"), [])
    check("a nested response is flattened to its strings",
          hook.response_text({"stdout": "a", "meta": {"stderr": ["b", "c"]}, "code": 1}), "a\nb\nc")
    check("a called test script is a test run", [p.name for p in hook.ran_scripts("& test.ps1 datrix-common")],
          ["test.ps1"])
    check("a test script only named is not a run", hook.ran_scripts("grep -n Tag test.ps1"), [])

    print("== DIGEST: a red test run in scope ==")
    context = test_context(console(("FAILED", "datrix-alpha", red)))
    check("the digest is in the context", ANSWER in context, True)
    check("it names the package and the log", "datrix-alpha" in context and "full.log" in context, True)
    check("it points at the structured data the run saved", str(red / "failure-data.json") in context, True)
    check("it tells the agent not to read the log whole", "Do not read full.log whole" in context, True)
    check("the model was sent the numbered log lines", "3| E   AssertionError: boom" in server.chats[-1].user, True)
    unstructured = make_run(workspace, "datrix-alpha", "4", structured=False)
    context = test_context(console(("FAILED", "datrix-alpha", unstructured)))
    check("with no failure-data.json it names the collector", "collect-failure-data.ps1" in context, True)
    callers = [json.loads(line)["caller"] for line in usage.read_text(encoding="utf-8").splitlines()]
    check("every request is in the usage log under the hook's name", set(callers), {"hook:red-test-digest"})

    print("== DIGEST: a failed gate run ==")
    gate_log = make_log(workspace / ".test-output" / "gates" / "x", "x-1.log")
    failed_line = gate_verdict_line("x", 1, gate_log)
    check("Write-DatrixGateVerdict prints the line the hook parses",
          [red_log.log for red_log in hook.failed_gate_logs(failed_line)], [gate_log])
    passed_line = gate_verdict_line("x", 0, gate_log)
    check("a PASSED verdict line is not a failed gate", hook.failed_gate_logs(passed_line), [])
    context = hook.context_for(hook.red_logs(GATE_SCRIPTS, f"checks...\n{failed_line}\n"), workspace, settings)
    check("the gate log's digest is in the context", ANSWER in context and "x gate run (exit 1)" in context, True)
    check("a verdict line in the output of a command that ran no script is ignored",
          hook.red_logs([], failed_line), [])

    print("== DIGEST: a failed generation run ==")
    generation_log = make_log(workspace / ".generated" / ".results" / "the-tour-card", "generate-results-1.log")
    context = hook.context_for(hook.red_logs(GENERATE_SCRIPTS, generation_console(1, generation_log)),
                               workspace, settings)
    check("the generation log's digest is in the context",
          ANSWER in context and "1 failed project(s)" in context, True)
    check("a generation summary with no failed project", hook.red_logs(GENERATE_SCRIPTS,
                                                                       generation_console(0, generation_log)), [])
    check("a generation summary from a command that did not run generate.ps1",
          hook.red_logs(GATE_SCRIPTS, generation_console(1, generation_log)), [])
    check("a summary with no saved log", hook.red_logs(GENERATE_SCRIPTS, "Generation Summary\n  Failed:  1\n"), [])

    print("== SILENT: every way the hook must add nothing ==")
    check("the hook's digest file name is the one test.ps1's digest writes", hook.RUN_DIGEST_NAME, DIGEST_FILENAME)
    digested = make_run(workspace, "datrix-alpha", "5")
    (digested / DIGEST_FILENAME).write_text("Failure digest: datrix-alpha FAILED\n", encoding="utf-8")
    before = len(server.chats)
    check("a red run test.ps1 already digested", test_context(console(("FAILED", "datrix-alpha", digested))), "")
    check("which reached no model", len(server.chats), before)
    mixed = test_context(console(("FAILED", "datrix-alpha", digested), ("FAILED", "datrix-alpha", red)))
    check("a digested run does not use up the cap: the undigested one is still digested",
          (mixed.count("Local-model digest of"), str(red / "full.log") in mixed), (1, True))
    before = len(server.chats)
    check("a green run", test_context(console(("PASSED", "datrix-alpha", green))), "")
    check("a red run whose log is outside the read scope",
          test_context(console(("FAILED", "acme-shop", customer))), "")
    missing = workspace / "datrix-alpha" / ".test_results" / "test-results-9"
    check("a red run with no log", test_context(console(("FAILED", "datrix-alpha", missing))), "")
    check("none of those reached a model", len(server.chats), before)
    dead = settings_for(closed_port(), usage)
    check("no model server answers: the result is untouched",
          test_context(console(("FAILED", "datrix-alpha", red)), dead), "")
    runs = [make_run(workspace, "datrix-alpha", f"cap{n}") for n in range(4)]
    before = len(server.chats)
    capped = test_context(console(*(("FAILED", "datrix-alpha", r) for r in runs)))
    check("at most MAX_RUNS runs are digested", (capped.count("Local-model digest of"), len(server.chats) - before),
          (hook.MAX_RUNS, hook.MAX_RUNS))
    both = hook.red_logs(TEST_SCRIPTS + GATE_SCRIPTS, console(*(("FAILED", "datrix-alpha", r) for r in runs))
                         + f"\n{failed_line}\n")
    before = len(server.chats)
    capped = hook.context_for(both, workspace, settings)
    check("MAX_RUNS caps every shape together", len(server.chats) - before, hook.MAX_RUNS)

    print("== the entry point ==")
    check("not a test command", run_hook("git status", "[FAILED] pkg\n  Details: x\\index.json"), (0, ""))
    check("a test script only named", run_hook("cat test.ps1", console(("FAILED", "datrix-alpha", red))), (0, ""))
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
