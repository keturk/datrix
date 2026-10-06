"""Exercise redirect-large-read.py: the first whole read of a large file gets an outline or a digest.

``decide`` is driven in-process against a temp workspace (framework repositories, a
customer-style repository, test output) with the real code index over it and a real
OpenAI-compatible server on loopback; the entry point is driven as a subprocess for the cases
that must never reach the index or a model. Both directions, on purpose:

  REDIRECT -- the first whole read, by one agent, of a large Python file or test log in scope.
  ALLOW -- the repeat of that read, a ranged read, a small file, a file outside the framework
           repositories, a file the index cannot outline, a log with no model server, any other
           tool, unparseable input.

A hook that refuses a read it should not have, or twice, wedges an agent; one that never
refuses saves nothing.
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
SESSION = "TEST-redirect-large-read"
fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


spec = importlib.util.spec_from_file_location("redirect_large_read", os.path.join(HOOKS, "redirect-large-read.py"))
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook.add_scripts_lib_to_path()
from datrix_scripts.customer_domain_isolation import corpus_path  # noqa: E402
from datrix_scripts.local_llm import LocalLlmSettings  # noqa: E402

ANSWER = "1. AssertionError: boom, 3 times, first at .test-output/run/big.log:4"


class ModelServer:
    """OpenAI-compatible server on loopback answering every chat with ANSWER."""

    def __init__(self) -> None:
        self.chats = 0
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


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def many_small_functions(count: int) -> str:
    return '"""Many small functions."""\n\n' + "".join(
        f'def fn_{n}(x: int) -> int:\n    """Add {n}."""\n    return x + {n}\n\n\n' for n in range(count))


def few_fat_functions(count: int) -> str:
    """Few definitions, many bytes: the outline is short, the file is large (docstring bodies)."""
    body = "".join(f"    Line {line} of a long docstring body that makes the file large.\n" for line in range(8))
    return '"""A few fat functions."""\n\n' + "".join(
        f'def fat_{n}(x: int) -> int:\n    """Fat {n}.\n\n{body}    """\n    return x * {n}\n\n\n'
        for n in range(count))


def read(path: Path, agent: str = "", **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"tool_name": "Read", "tool_input": {"file_path": str(path), **extra},
                                  "session_id": SESSION, "cwd": str(path.parent)}
    if agent:
        payload["agent_id"] = agent
    return payload


def run_hook(payload: object, raw: str | None = None) -> tuple[int, str]:
    process = subprocess.run([sys.executable, os.path.join(HOOKS, "redirect-large-read.py")],
                             input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True,
                             timeout=60)
    return process.returncode, process.stderr


def cleanup_state() -> None:
    state = Path(hook._STATE_DIR)
    for item in state.glob(f"read-redirect-{SESSION}*.json"):
        item.unlink(missing_ok=True)


cleanup_state()
try:
    with tempfile.TemporaryDirectory(prefix="redirect-hook-") as temp:
        workspace = Path(temp)
        for repo in ("datrix", "datrix-alpha", "acme-shop"):
            (workspace / repo).mkdir()
            subprocess.run(["git", "-C", str(workspace / repo), "init", "-q"], check=True, capture_output=True)
        big = write(workspace / "datrix-alpha/src/alpha_pkg/big.py", many_small_functions(200))
        fat = write(workspace / "datrix-alpha/src/alpha_pkg/fat.py", few_fat_functions(40))
        small = write(workspace / "datrix-alpha/src/alpha_pkg/small.py", many_small_functions(5))
        customer = write(workspace / "acme-shop/big.py", many_small_functions(200))
        excluded = write(workspace / "datrix/examples/big.py", many_small_functions(200))
        notes = write(workspace / "datrix-alpha/docs/notes.md", "A long note. " * 2000)
        log_text = "".join(f"step {n} ok\n" for n in range(3000)) + "E   AssertionError: boom\n" * 3
        big_log = write(workspace / ".test-output/run/big.log", log_text)
        small_log = write(workspace / ".test-output/run/small.log", "all fine\n")
        # Nothing reaches a local model without the customer-term corpus; an empty one filters nothing.
        write(corpus_path(workspace / "datrix"), json.dumps({"algorithm": "sha256", "terms": []}))
        server = ModelServer()
        settings = settings_for(server.port, workspace / "usage.jsonl")

        repeats: list[str] = []

        def decide(payload: dict[str, object], with_settings: LocalLlmSettings = settings) -> str:
            return hook.decide(payload, workspace, with_settings, on_repeat=lambda: repeats.append("repeat"))

        print("== REDIRECT: the first whole read of a large Python file ==")
        message = decide(read(big))
        check("it is refused with the outline", "READ REDIRECTED" in message and "datrix-alpha/src/alpha_pkg/big.py" in message, True)
        check("the outline lists definitions with line ranges", "L3-5 def fn_0(x: int) -> int" in message, True)
        check("a long outline is clipped, saying so", "more outline lines" in message, True)
        check("it says how to proceed and how to get the whole file",
              "offset and limit" in message and "repeat the same Read" in message, True)
        fat_message = decide(read(fat))
        check("a short outline is given whole",
              "READ REDIRECTED" in fat_message and "def fat_39" in fat_message and "more outline lines" not in fat_message,
              True)

        print("== ALLOW: every way a read must go through ==")
        check("nothing was a repeat yet", repeats, [])
        check("the repeat of the same read", decide(read(big)), "")
        check("and it is reported as a repeat, so the usage report can count it", repeats, ["repeat"])
        check("a different agent has its own context, so it is told too",
              "READ REDIRECTED" in decide(read(big, agent="a1")), True)
        check("a ranged read (offset)", decide(read(fat, offset=10)), "")
        check("a ranged read (limit)", decide(read(excluded, limit=50)), "")
        check("a small file", decide(read(small)), "")
        check("a file in another repository", decide(read(customer)), "")
        check("a large file that is not Python or a log", decide(read(notes)), "")
        check("a file the index does not cover (excluded by configuration)", decide(read(excluded)), "")
        check("a small log", decide(read(small_log)), "")
        check("a path that does not exist", decide(read(workspace / "datrix-alpha/src/nope.py")), "")
        check("another tool", decide({"tool_name": "Edit", "tool_input": {"file_path": str(big)}}), "")
        check("an excluded file was not marked as told, so nothing is held against the agent",
              str(excluded) in hook._told(hook._state_path(SESSION, "main")), False)

        print("== a large test log: the digest ==")
        before = server.chats
        dead = settings_for(closed_port(), workspace / "usage.jsonl")
        check("no model server answers: the read goes through", decide(read(big_log), dead), "")
        check("and the agent is not marked as told, so the next read still gets a digest",
              str(big_log) in hook._told(hook._state_path(SESSION, "main")), False)
        log_message = decide(read(big_log))
        check("the first whole read is refused with the model's digest",
              "READ REDIRECTED" in log_message and ANSWER in log_message, True)
        check("the model was asked once or in chunks, never for nothing", server.chats > before, True)
        check("the repeat goes through", decide(read(big_log)), "")

        print("== the entry point ==")
        check("a ranged read", run_hook(read(big, offset=1, limit=20)), (0, ""))
        check("another tool", run_hook({"tool_name": "Grep", "tool_input": {"pattern": "x"}}), (0, ""))
        check("unparseable input", run_hook(None, raw="{not json"), (0, ""))
        check("input that is not an object", run_hook(None, raw="[1, 2]"), (0, ""))
        check("a file that is not in the real workspace's framework repositories",
              run_hook(read(customer)), (0, ""))
        server.httpd.shutdown()
finally:
    cleanup_state()

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
