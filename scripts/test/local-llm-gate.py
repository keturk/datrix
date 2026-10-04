#!/usr/bin/env python3
"""Repo-level gate for the local-model reading tools (shared/local_reading.py, dev/local_llm_mcp.py).

Every check builds a real workspace in a temporary directory -- framework repositories, a
customer-style repository beside them, .tmp and .test-output -- and talks to a real
OpenAI-compatible HTTP server on loopback whose answers depend on the prompt it receives.
Nothing here contacts the network's model servers, and every request is recorded in a
temporary usage log, never the machine's own.

Run through test/local-llm-gate.ps1.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from dev.local_llm_mcp import LocalLlmServer, LocalReader  # noqa: E402
from dev.customer_domain_isolation import hash_term  # noqa: E402
from shared.local_llm import LocalLlmPool, LocalLlmSettings  # noqa: E402
from shared.local_llm_usage import USAGE_LOG_VARIABLE  # noqa: E402
from shared.local_reading import (  # noqa: E402
    MAP_SYSTEM,
    MAX_FILES,
    NOTHING_RELEVANT,
    REDUCE_SYSTEM,
    ReadScope,
    ReadScopeError,
    Section,
    ask_files,
    chunk_sections,
    digest_log,
    reduce_log,
)
from shared.mcp_stdio import serve  # noqa: E402

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"

_LOOPBACK = "127.0.0.1"
_MCP_SCRIPT = _LIBRARY_DIR / "dev" / "local_llm_mcp.py"

_A_PY = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
# A registered customer term for the fixture workspace: a made-up word no real stack uses.
_GATE_TERM = "zzgateterm"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    """Run every check, catching only AssertionError. Returns True iff all passed."""
    all_passed = True
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            _fail(f"{check.__name__}: {exc}")
            all_passed = False
        else:
            _ok(check.__name__)
    return all_passed


# ===========================================================================
# fixtures: a workspace, and a model server on loopback
# ===========================================================================


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@contextmanager
def _workspace() -> Iterator[Path]:
    """Two framework repos, a customer-style repo, .tmp and .test-output."""
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        root = Path(temp)
        for repo in ("datrix", "datrix-alpha", "acme-shop"):
            (root / repo / ".git").mkdir(parents=True)
        _write(root / "datrix-alpha" / ".git" / "config", "[core]\n")
        _write(root / "datrix-alpha" / "src" / "a.py", _A_PY)
        _write(root / "datrix-alpha" / "src" / "b.py", "X = 1\n")
        _write(root / "acme-shop" / "x.py", "SECRET_DOMAIN = 1\n")
        _write(root / ".tmp" / "generated" / "app.py", "GENERATED = 1\n")
        _write(root / ".test-output" / "run.log", "collected 3 items\nE   AssertionError: boom\n1 failed\n")
        _write(root / "datrix" / "scripts" / "config" / "customer-term-hashes.json", json.dumps({
            "algorithm": "sha256", "min_token_length": 5,
            "terms": [{"hash": hash_term(_GATE_TERM), "hint": "gate fixture"}]}))
        yield root


Responder = Callable[[str, str], str]


class _ModelServer:
    """An OpenAI-compatible server on loopback: ``respond(system, user)`` writes every answer."""

    def __init__(self, model: str, respond: Responder) -> None:
        self.requests: list[tuple[str, str]] = []
        requests = self.requests

        class _Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._send({"data": [{"id": model}]})

            def do_POST(self) -> None:  # noqa: N802 -- http.server's dispatch name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if body.get("max_tokens") == 1:
                    self._send({"choices": [{"message": {"content": "pong"}}]})
                    return
                system, user = (str(m["content"]) for m in body["messages"])
                requests.append((system, user))
                self._send({"choices": [{"message": {"content": respond(system, user)}, "finish_reason": "stop"}]})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._httpd = ThreadingHTTPServer((_LOOPBACK, 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> _ModelServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


def _settings(openai_port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=_closed_port(), openai_ports=(openai_port,),
                            usage_log=usage_log, caller="gate")


def _pool(server: _ModelServer, usage_log: Path) -> LocalLlmPool:
    return LocalLlmPool(_settings(server.port, usage_log), report=lambda _line: None)


def _refused(scope: ReadScope, spec: str) -> str:
    try:
        scope.files([spec])
    except ReadScopeError as exc:
        return str(exc)
    raise AssertionError(f"'{spec}' was accepted but is out of scope")


# ===========================================================================
# scope
# ===========================================================================


def check_scope_reads_framework_repos_and_test_output_only() -> None:
    with _workspace() as root:
        scope = ReadScope(root)
        accepted = [scope.label(p) for p in scope.files(
            ["datrix-alpha/src/a.py", ".test-output/run.log", "datrix-alpha/src/*.py"])]
        assert accepted == ["datrix-alpha/src/a.py", ".test-output/run.log", "datrix-alpha/src/b.py"], accepted
        assert scope.label(scope.files([str(root / "datrix-alpha" / "src" / "a.py")])[0]) == "datrix-alpha/src/a.py"
        for spec in ("acme-shop/x.py", ".tmp/generated/app.py", "datrix-alpha/../acme-shop/x.py",
                     "datrix-alpha/.git/config", "*/x.py", str(Path(__file__).resolve())):
            message = _refused(scope, spec)
            assert "outside what local-model tools may read" in message and "datrix-alpha" in message, message
        assert "is not a file" in _refused(scope, "datrix-alpha/src"), "a directory must be refused, naming the fix"
        assert "matches no file" in _refused(scope, "datrix-alpha/**/*.rs")


def check_scope_caps_the_files_per_call() -> None:
    with _workspace() as root:
        for n in range(MAX_FILES + 1):
            _write(root / "datrix-alpha" / "many" / f"m{n}.py", "X = 1\n")
        message = _refused(ReadScope(root), "datrix-alpha/many/*.py")
        assert f"at most {MAX_FILES}" in message, message


# ===========================================================================
# chunking and log reduction
# ===========================================================================


def check_chunks_carry_headers_and_original_line_numbers() -> None:
    section = Section("datrix-alpha/src/long.py", tuple(f"{n}| value_{n} = {n}" for n in range(1, 201)))
    chunks = chunk_sections([section, Section("datrix-alpha/src/b.py", ("1| X = 1",))], max_chars=1500)
    assert len(chunks) > 2, f"expected the long file to be split, got {len(chunks)} chunk(s)"
    assert all(len(chunk) <= 1500 for chunk in chunks), [len(c) for c in chunks]
    assert all(chunk.startswith("=== ") for chunk in chunks), "every chunk must open with the header of its file"
    numbered: dict[str, list[int]] = {}
    for chunk in chunks:
        label = ""
        for line in chunk.splitlines():
            if line.startswith("=== "):
                label = line.strip("= ")
            else:
                numbered.setdefault(label, []).append(int(line.split("|")[0]))
    assert numbered == {"datrix-alpha/src/long.py": list(range(1, 201)), "datrix-alpha/src/b.py": [1]}, \
        "a split file must keep every line, in order, with its own number, under its own header"
    assert chunks[-1].endswith("=== datrix-alpha/src/b.py ===\n1| X = 1"), chunks[-1][-80:]


def check_reduce_log_keeps_error_context_or_the_tail() -> None:
    lines = tuple(f"{n}| ok step {n}" for n in range(1, 2001))
    marked = lines[:999] + ("1000| E   AssertionError: boom",) + lines[1000:]
    reduced = reduce_log(Section("run.log", marked), budget_chars=5000)
    numbers = [int(line.split("|")[0]) for line in reduced.lines]
    assert numbers == list(range(997, 1013)), f"expected the marker with 3 before and 12 after, got {numbers}"
    assert "around error markers" in reduced.note, reduced.note
    tail = reduce_log(Section("quiet.log", lines), budget_chars=200)
    assert tail.lines[-1] == "2000| ok step 2000" and "last" in tail.note, (tail.lines, tail.note)
    whole = Section("small.log", lines[:5])
    assert reduce_log(whole, budget_chars=5000) is whole, "a log that fits is read whole"


# ===========================================================================
# asking
# ===========================================================================


def check_ask_files_sends_numbered_lines_and_checks_citations() -> None:
    answer = ("alpha is defined at datrix-alpha/src/a.py:1-2; beta at datrix-alpha/src/a.py:999; "
              "see also other/z.py:1.")
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: answer) as server:
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"],
                           "Where is alpha defined?")
        assert len(server.requests) == 1, f"one chunk must be one request, got {len(server.requests)}"
        user = server.requests[0][1]
        assert user.startswith("Question: Where is alpha defined?") and "=== datrix-alpha/src/a.py ===" in user
        assert "1| def alpha():" in user and "5| def beta():" in user, user
        rendered = result.render()
        assert answer in rendered and "A lead, not a finding" in rendered, rendered
        assert "datrix-alpha/src/a.py:999" in rendered.split("---", 1)[1] and "other/z.py:1" in rendered.split(
            "---", 1)[1], "citations of an unsent line or file must be called out"
        assert "datrix-alpha/src/a.py:1-2," not in rendered.split("---", 1)[1], "a valid citation is not flagged"
        entries = [json.loads(line) for line in (root / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [(e["caller"], e["outcome"]) for e in entries] == [("gate", "ok")], entries


def check_ask_files_flags_quoted_code_the_model_was_not_sent() -> None:
    answer = ("The helper is `def alpha():` at datrix-alpha/src/a.py:1, returning `return 1`.\n"
              "It also checks:\n```python\nreturn {e for e in enums if re.search(rf\"\\b{e}\\b\", body)}\n```\n"
              "and defers to `to_words`.")
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: answer) as server:
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        notes = " ".join(result.notes)
        assert "1 quoted code snippet(s) do not appear" in notes and "re.search" in notes, result.notes
        assert "def alpha" not in notes and "return 1" not in notes, "code that really is in the file is not flagged"
        assert "to_words" not in notes, "a short span is a name, not a quotation, and is not checked"
    honest = ("It is:\n```python\ndef beta():\n    return 2\n```\ndefined in `datrix-alpha/src/a.py:5` and used by "
              "`EventGenerator._render_event_handlers_for_every_service`.")
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: honest) as server:
        quiet = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        assert not quiet.notes, f"a faithful quotation (whitespace aside) must not be flagged: {quiet.notes}"


def check_ask_over_many_chunks_maps_then_merges() -> None:
    body = "".join(f"value_{n} = {n}  # padding to make the file long enough\n" for n in range(2000))

    def respond(system: str, user: str) -> str:
        if system == REDUCE_SYSTEM:
            return "merged: datrix-alpha/src/long.py:3 and datrix-alpha/src/long.py:1999"
        if system == MAP_SYSTEM:
            if "3| value_2 = 2" in user:
                return "datrix-alpha/src/long.py:3"
            if "1999| value_1998" in user:
                return "datrix-alpha/src/long.py:1999"
            return NOTHING_RELEVANT
        raise AssertionError(f"unexpected system prompt: {system[:60]}")

    with _workspace() as root, _ModelServer("gate-model", respond) as server:
        _write(root / "datrix-alpha" / "src" / "long.py", body)
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/long.py"],
                           "Where are value_2 and value_1998?")
        systems = [system for system, _ in server.requests]
        assert systems.count(REDUCE_SYSTEM) == 1 and systems.count(MAP_SYSTEM) == result.chunks > 1, systems
        assert result.text.startswith("merged:") and not result.notes, (result.text, result.notes)


def check_a_line_with_a_registered_customer_term_is_never_sent() -> None:
    log = ("collected 3 items\nERROR port conflict: container zzgateterm-db is already bound\n"
           "E   AssertionError: boom\n1 failed\n")
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: "ok") as server:
        _write(root / ".test-output" / "other-stack.log", log)
        result = digest_log(ReadScope(root), _pool(server, root / "usage.jsonl"), ".test-output/other-stack.log", "")
        sent = server.requests[0][1]
        assert _GATE_TERM not in sent.lower(), "a registered customer term reached the model server"
        assert "2| <line withheld" in sent and "3| E   AssertionError: boom" in sent, sent
        assert any("1 line(s) withheld" in note for note in result.notes), result.notes
        _write(root / "datrix-alpha" / "src" / "c.py", f"# {_GATE_TERM}\nX = 1\n")
        ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/c.py"], "q")
        assert _GATE_TERM not in server.requests[-1][1].lower(), "the filter covers source files as well as logs"


def check_no_term_corpus_means_nothing_is_read() -> None:
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: "ok") as server:
        (root / "datrix" / "scripts" / "config" / "customer-term-hashes.json").unlink()
        message = ""
        try:
            ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        except ReadScopeError as exc:
            message = str(exc)
        assert "without the customer-term corpus" in message, message
        assert not server.requests, "an unfiltered read must not reach the model server"


def check_digest_log_checks_only_its_own_line_citations() -> None:
    answer = "AssertionError: boom, 1 time, first at .test-output/run.log:2, raised from src/app.py:41; " \
             "also .test-output/run.log:77."
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: answer) as server:
        result = digest_log(ReadScope(root), _pool(server, root / "usage.jsonl"), ".test-output/run.log",
                            "only assertions")
        assert "Focus: only assertions" in server.requests[0][1]
        notes = " ".join(result.notes)
        assert ".test-output/run.log:77" in notes, "a log line that does not exist must be called out"
        assert "src/app.py:41" not in notes, "a source location the log itself names is not a wrong citation"
        message = ""
        try:
            digest_log(ReadScope(root), _pool(server, root / "usage.jsonl"), "datrix-alpha/src/*.py", "")
        except ReadScopeError as exc:
            message = str(exc)
        assert "reads one log" in message, message


# ===========================================================================
# MCP server
# ===========================================================================


def _exchange(server: LocalLlmServer, messages: list[object]) -> list[dict[str, object]]:
    stdin = io.BytesIO(b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages))
    stdout = io.BytesIO()
    serve(server, stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def _call(request_id: int, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def _content(response: dict[str, object]) -> tuple[bool, str]:
    result = response["result"]
    assert isinstance(result, dict), response
    content = result["content"]
    assert isinstance(content, list)
    return bool(result["isError"]), str(content[0]["text"])


def check_mcp_server_answers_and_refuses_out_of_scope() -> None:
    with _workspace() as root, _ModelServer("gate-model", lambda _s, _u: "alpha: datrix-alpha/src/a.py:1") as server:
        log = root / "usage.jsonl"
        responses = _exchange(LocalLlmServer(lambda: LocalReader(ReadScope(root), _settings(server.port, log))), [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            _call(3, "ask_files", {"paths": ["datrix-alpha/src/a.py"], "question": "Where is alpha?"}),
            _call(4, "ask_files", {"paths": ["acme-shop/x.py"], "question": "What is this?"}),
            _call(5, "ask_files", {"paths": [], "question": "q"}),
            _call(6, "local_models", {}),
        ])
        assert responses[0]["result"]["serverInfo"]["name"] == "datrix-local-llm", responses[0]
        tools = responses[1]["result"]["tools"]
        assert [(t["name"], t["annotations"]["openWorldHint"]) for t in tools] == [
            ("ask_files", True), ("digest_log", True), ("local_models", True)], tools
        assert _content(responses[2]) == (False, _content(responses[2])[1]) and "alpha: datrix-alpha/src/a.py:1" in \
            _content(responses[2])[1]
        is_error, text = _content(responses[3])
        assert is_error and "outside what local-model tools may read" in text, text
        is_error, text = _content(responses[4])
        assert is_error and "'paths' is required" in text, text
        is_error, text = _content(responses[5])
        assert not is_error and "gate-model" in text and "mcp:ask_files: 1 requests" in text, text
        callers = [json.loads(line)["caller"] for line in log.read_text(encoding="utf-8").splitlines()]
        assert callers == ["mcp:ask_files"], f"a tool call must be logged under its tool's name: {callers}"


def check_mcp_server_reports_no_model_server_as_a_tool_error() -> None:
    with _workspace() as root:
        settings = _settings(_closed_port(), root / "usage.jsonl")
        responses = _exchange(LocalLlmServer(lambda: LocalReader(ReadScope(root), settings)), [
            _call(1, "ask_files", {"paths": ["datrix-alpha/src/a.py"], "question": "q"})])
        is_error, text = _content(responses[0])
        assert is_error and "No local model server could answer" in text, text


def check_mcp_server_stdout_carries_only_protocol() -> None:
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        env = {**os.environ, USAGE_LOG_VARIABLE: str(Path(temp) / "usage.jsonl")}
        result = subprocess.run([sys.executable, str(_MCP_SCRIPT)], capture_output=True, timeout=60, check=False,
                                input=b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages), env=env)
    lines = result.stdout.decode("utf-8").splitlines()
    assert result.returncode == 0 and len(lines) == 2, (result.returncode, lines, result.stderr[-500:])
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in lines), lines


# ===========================================================================
# harness
# ===========================================================================


def _deliberately_failing_check() -> None:
    assert False, "deliberately failing check for --harness-self-test"


def harness_self_test() -> bool:
    print("=== Harness self-test: a deliberately-failing check must be reported FAILED ===")
    if run_checks([_deliberately_failing_check]):
        _fail("harness self-test: the deliberately-failing check was NOT reported as failed")
        return False
    _ok("harness self-test: the deliberately-failing check was correctly reported FAILED")
    return True


_ALL_CHECKS: list[CheckFunc] = [
    check_scope_reads_framework_repos_and_test_output_only,
    check_scope_caps_the_files_per_call,
    check_chunks_carry_headers_and_original_line_numbers,
    check_reduce_log_keeps_error_context_or_the_tail,
    check_ask_files_sends_numbered_lines_and_checks_citations,
    check_ask_files_flags_quoted_code_the_model_was_not_sent,
    check_ask_over_many_chunks_maps_then_merges,
    check_a_line_with_a_registered_customer_term_is_never_sent,
    check_no_term_corpus_means_nothing_is_read,
    check_digest_log_checks_only_its_own_line_citations,
    check_mcp_server_answers_and_refuses_out_of_scope,
    check_mcp_server_reports_no_model_server_as_a_tool_error,
    check_mcp_server_stdout_carries_only_protocol,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for the local-model reading tools.")
    parser.add_argument("--harness-self-test", action="store_true",
                        help="Run only the harness self-test (a deliberately-failing dummy check).")
    parser.add_argument("--only", metavar="PREFIX", help="Run only the checks whose name starts with PREFIX.")
    args = parser.parse_args()
    if args.harness_self_test:
        return 0 if harness_self_test() else 1
    checks = _ALL_CHECKS
    if args.only:
        checks = [check for check in _ALL_CHECKS if check.__name__.startswith(args.only)]
        if not checks:
            print(f"Error: no check name starts with {args.only!r}. Checks: "
                  f"{', '.join(c.__name__ for c in _ALL_CHECKS)}.", file=sys.stderr)
            return 2
    print(f"Running {len(checks)} local-model reading checks...\n")
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        os.environ[USAGE_LOG_VARIABLE] = str(Path(temp) / "usage.jsonl")
        passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} local-model reading checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
