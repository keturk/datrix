"""Exercise digest-red-test-run.py: a local model's digest of a red test run's log.

``context_for`` is driven in-process against a temp workspace (a framework repository and a
customer-style one) and a real OpenAI-compatible server on loopback; the hook's entry point
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
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOOKS = os.path.dirname(os.path.abspath(__file__))
LOOPBACK = "127.0.0.1"
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
sys.path.insert(0, hook.LIBRARY_DIR)
from shared.local_llm import LocalLlmSettings  # noqa: E402

ANSWER = "1. AssertionError: boom, 2 times, first at datrix-alpha/.test_results/test-results-1/full.log:4"


class ModelServer:
    """OpenAI-compatible server on loopback answering every chat with ANSWER."""

    def __init__(self) -> None:
        self.chats = 0
        self.prompts: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self._send({"data": [{"id": "digest-model"}]})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if body.get("max_tokens") != 1:
                    server.chats += 1
                    server.prompts.append(str(body["messages"][-1]["content"]))
                self._send({"choices": [{"message": {"content": ANSWER}, "finish_reason": "stop"}]})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self.httpd = ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.port = int(self.httpd.server_address[1])
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK, 0))
        return int(sock.getsockname()[1])


def settings_for(port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=closed_port(), openai_ports=(port,),
                            usage_log=usage_log, caller=hook.CALLER)


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


with tempfile.TemporaryDirectory(prefix="digest-hook-") as temp:
    workspace = Path(temp)
    for repo in ("datrix", "datrix-alpha", "acme-shop"):
        (workspace / repo / ".git").mkdir(parents=True)
    usage = workspace / "usage.jsonl"
    server = ModelServer()
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
    check("the model was sent the numbered log lines", "3| E   AssertionError: boom" in server.prompts[-1], True)
    unstructured = make_run(workspace, "datrix-alpha", "4", structured=False)
    context = hook.context_for(console(("FAILED", "datrix-alpha", unstructured)), workspace, settings)
    check("with no failure-data.json it names the collector", "collect-failure-data.ps1" in context, True)
    callers = [json.loads(line)["caller"] for line in usage.read_text(encoding="utf-8").splitlines()]
    check("every request is in the usage log under the hook's name", set(callers), {"hook:red-test-digest"})

    print("== SILENT: every way the hook must add nothing ==")
    before = server.chats
    check("a green run", hook.context_for(console(("PASSED", "datrix-alpha", green)), workspace, settings), "")
    check("a red run whose log is outside the read scope",
          hook.context_for(console(("FAILED", "acme-shop", customer)), workspace, settings), "")
    missing = workspace / "datrix-alpha" / ".test_results" / "test-results-9"
    check("a red run with no log",
          hook.context_for(console(("FAILED", "datrix-alpha", missing)), workspace, settings), "")
    check("none of those reached a model", server.chats, before)
    dead = settings_for(closed_port(), usage)
    check("no model server answers: the result is untouched",
          hook.context_for(console(("FAILED", "datrix-alpha", red)), workspace, dead), "")
    runs = [make_run(workspace, "datrix-alpha", f"cap{n}") for n in range(4)]
    before = server.chats
    capped = hook.context_for(console(*(("FAILED", "datrix-alpha", r) for r in runs)), workspace, settings)
    check("at most MAX_RUNS runs are digested", (capped.count("Local-model digest of"), server.chats - before),
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
    server.httpd.shutdown()

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
