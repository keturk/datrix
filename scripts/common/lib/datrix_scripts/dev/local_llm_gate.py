#!/usr/bin/env python3
"""Repo-level gate for the local-model reading tools (datrix_scripts.local_reading, datrix_scripts.dev.local_llm_mcp).

Every check builds a real workspace in a temporary directory -- framework repositories, a
customer-style repository beside them, .tmp and .test-output -- and talks to a real
Ollama-shaped HTTP server on loopback (datrix_scripts.local_llm_loopback) whose answers
depend on the prompt it receives.
Nothing here contacts the network's model servers, and every request is recorded in a
temporary usage log, never the machine's own.

Run through dev/local-llm-gate.ps1.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from datrix_scripts.customer_domain_isolation import hash_term
from datrix_scripts.detached_run import LockBusy, held_lock
from datrix_scripts.dev.local_llm import MCP_SERVER_MODULE
from datrix_scripts.dev.local_llm_mcp import LocalLlmServer, LocalReader
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, CheckFunc, check_list_main, check_list_parser, write_file
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.local_llm import (
    DEFAULT_LOCAL_MACHINES,
    LOAD_MISSING_LOCK_NAME,
    LOAD_MISSING_LOG_NAME,
    LOAD_MISSING_MODULE,
    MISSING_LOAD_LOCK_STALE_SECONDS,
    OLLAMA_KEEP_ALIVE_INDEFINITE,
    OLLAMA_KEEP_ALIVE_UNLOAD,
    OLLAMA_LOAD_PREFERENCE,
    OLLAMA_PORT,
    ChatRequest,
    LocalCandidate,
    LocalHost,
    LocalLlmPool,
    LocalLlmReply,
    LocalLlmSettings,
    LocalLlmUnavailable,
    load_missing_models,
    ollama_base_url,
    pin_models,
    start_missing_loads,
    survey_ollama,
    unpin_models,
    unpinned_machine_lines,
)
from datrix_scripts.local_llm_loopback import (
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_SERVER_ERROR,
    LOOPBACK,
    Chat,
    ChatAnswer,
    JsonResponder,
    LoopbackJsonServer,
    LoopbackOllama,
    answering,
    closed_port,
    held_for,
    held_for_thirty_minutes,
)
from datrix_scripts.local_llm_usage import GATE_USAGE_LOG, USAGE_LOG_VARIABLE
from datrix_scripts.local_reading import (
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
from datrix_scripts.mcp_exchange import exchange, tool_call, tool_result
from datrix_scripts.paths import script_env
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, seam_checks

MODULE = "datrix_scripts.dev.local_llm_gate"
WRAPPER = "local-llm-gate"
GATE = "local-llm"

_A_PY = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
# A registered customer term for the fixture workspace: a made-up word no real stack uses.
_GATE_TERM = "zzgateterm"


# ===========================================================================
# fixtures: a workspace, and a model server on loopback
# ===========================================================================


@contextmanager
def _workspace() -> Iterator[Path]:
    """Two framework repos, a customer-style repo, .tmp and .test-output."""
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        root = Path(temp)
        for repo in ("datrix", "datrix-alpha", "acme-shop"):
            (root / repo / ".git").mkdir(parents=True)
        write_file(root / "datrix-alpha" / ".git" / "config", "[core]\n")
        write_file(root / "datrix-alpha" / "src" / "a.py", _A_PY)
        write_file(root / "datrix-alpha" / "src" / "b.py", "X = 1\n")
        write_file(root / "acme-shop" / "x.py", "SECRET_DOMAIN = 1\n")
        write_file(root / ".tmp" / "generated" / "app.py", "GENERATED = 1\n")
        write_file(root / ".test-output" / "run.log", "collected 3 items\nE   AssertionError: boom\n1 failed\n")
        write_file(root / "datrix" / "scripts" / "config" / "customer-term-hashes.json", json.dumps({
            "algorithm": "sha256", "min_token_length": 5,
            "terms": [{"hash": hash_term(_GATE_TERM), "hint": "gate fixture"}]}))
        yield root


def _settings(ollama_port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=ollama_port, usage_log=usage_log, caller="gate")


def _pool(server: LoopbackOllama, usage_log: Path) -> LocalLlmPool:
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


def check_scope_reads_generation_logs_and_extra_roots_only_when_given() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="local-llm-gate-extra-") as extra_temp, \
            LoopbackOllama(answering("ok")) as server:
        write_file(root / ".generated" / ".results" / "the-tour-card" / "generate-results-1.log", "Failed: 1\n")
        write_file(root / ".generated" / "python" / "app.py", "GENERATED = 1\n")
        extra = Path(extra_temp)
        write_file(extra / "service.dtrx", f"service Shop {{}}\n// {_GATE_TERM}\n")
        assert ReadScope(root).files([".generated/.results/the-tour-card/generate-results-1.log"]), (
            "generation logs are in scope")
        assert "outside what local-model tools may read" in _refused(ReadScope(root), ".generated/python/app.py"), \
            "a generated tree is not a log and stays out of scope"
        outside = str(extra / "service.dtrx")
        assert "outside what local-model tools may read" in _refused(ReadScope(root), outside), \
            "a directory is read only when the caller names it as an extra root"
        scope = ReadScope(root, extra_roots=(extra,))
        assert scope.files([outside]) == [(extra / "service.dtrx").resolve()]
        ask_files(scope, _pool(server, root / "usage.jsonl"), [outside], "q")
        sent = server.chats[-1].user
        assert _GATE_TERM not in sent.lower() and "<line withheld" in sent, \
            "a line from an extra root is checked against the customer-term corpus like any other"


def check_scope_caps_the_files_per_call() -> None:
    with _workspace() as root:
        for n in range(MAX_FILES + 1):
            write_file(root / "datrix-alpha" / "many" / f"m{n}.py", "X = 1\n")
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
    with _workspace() as root, LoopbackOllama(answering(answer)) as server:
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"],
                           "Where is alpha defined?")
        assert len(server.chats) == 1, f"one chunk must be one request, got {len(server.chats)}"
        user = server.chats[0].user
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
    with _workspace() as root, LoopbackOllama(answering(answer)) as server:
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        notes = " ".join(result.notes)
        assert "1 quoted code snippet(s) do not appear" in notes and "re.search" in notes, result.notes
        assert "def alpha" not in notes and "return 1" not in notes, "code that really is in the file is not flagged"
        assert "to_words" not in notes, "a short span is a name, not a quotation, and is not checked"
    honest = ("It is:\n```python\ndef beta():\n    return 2\n```\ndefined in `datrix-alpha/src/a.py:5` and used by "
              "`EventGenerator._render_event_handlers_for_every_service`.")
    with _workspace() as root, LoopbackOllama(answering(honest)) as server:
        quiet = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        assert not quiet.notes, f"a faithful quotation (whitespace aside) must not be flagged: {quiet.notes}"


def check_ask_over_many_chunks_maps_then_merges() -> None:
    body = "".join(f"value_{n} = {n}  # padding to make the file long enough\n" for n in range(2000))

    def respond(chat: Chat) -> str:
        if chat.system == REDUCE_SYSTEM:
            return "merged: datrix-alpha/src/long.py:3 and datrix-alpha/src/long.py:1999"
        if chat.system == MAP_SYSTEM:
            if "3| value_2 = 2" in chat.user:
                return "datrix-alpha/src/long.py:3"
            if "1999| value_1998" in chat.user:
                return "datrix-alpha/src/long.py:1999"
            return NOTHING_RELEVANT
        raise AssertionError(f"unexpected system prompt: {chat.system[:60]}")

    with _workspace() as root, LoopbackOllama(respond) as server:
        write_file(root / "datrix-alpha" / "src" / "long.py", body)
        result = ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/long.py"],
                           "Where are value_2 and value_1998?")
        systems = [chat.system for chat in server.chats]
        assert systems.count(REDUCE_SYSTEM) == 1 and systems.count(MAP_SYSTEM) == result.chunks > 1, systems
        assert result.text.startswith("merged:") and not result.notes, (result.text, result.notes)


def check_a_line_with_a_registered_customer_term_is_never_sent() -> None:
    log = ("collected 3 items\nERROR port conflict: container zzgateterm-db is already bound\n"
           "E   AssertionError: boom\n1 failed\n")
    with _workspace() as root, LoopbackOllama(answering("ok")) as server:
        write_file(root / ".test-output" / "other-stack.log", log)
        result = digest_log(ReadScope(root), _pool(server, root / "usage.jsonl"), ".test-output/other-stack.log", "")
        sent = server.chats[0].user
        assert _GATE_TERM not in sent.lower(), "a registered customer term reached the model server"
        assert "2| <line withheld" in sent and "3| E   AssertionError: boom" in sent, sent
        assert any("1 line(s) withheld" in note for note in result.notes), result.notes
        write_file(root / "datrix-alpha" / "src" / "c.py", f"# {_GATE_TERM}\nX = 1\n")
        ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/c.py"], "q")
        assert _GATE_TERM not in server.chats[-1].user.lower(), "the filter covers source files as well as logs"


def check_no_term_corpus_means_nothing_is_read() -> None:
    with _workspace() as root, LoopbackOllama(answering("ok")) as server:
        (root / "datrix" / "scripts" / "config" / "customer-term-hashes.json").unlink()
        message = ""
        try:
            ask_files(ReadScope(root), _pool(server, root / "usage.jsonl"), ["datrix-alpha/src/a.py"], "q")
        except ReadScopeError as exc:
            message = str(exc)
        assert "without the customer-term corpus" in message, message
        assert not server.requests, "an unfiltered read must not reach the model server at all"


def check_digest_log_checks_only_its_own_line_citations() -> None:
    answer = "AssertionError: boom, 1 time, first at .test-output/run.log:2, raised from src/app.py:41; " \
             "also .test-output/run.log:77."
    with _workspace() as root, LoopbackOllama(answering(answer)) as server:
        result = digest_log(ReadScope(root), _pool(server, root / "usage.jsonl"), ".test-output/run.log",
                            "only assertions")
        assert "Focus: only assertions" in server.chats[0].user
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


def check_mcp_server_answers_and_refuses_out_of_scope() -> None:
    with _workspace() as root, LoopbackOllama(answering("alpha: datrix-alpha/src/a.py:1")) as server:
        log = root / "usage.jsonl"
        responses = exchange(LocalLlmServer(lambda: LocalReader(ReadScope(root), _settings(server.port, log))), [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            tool_call(3, "ask_files", {"paths": ["datrix-alpha/src/a.py"], "question": "Where is alpha?"}),
            tool_call(4, "ask_files", {"paths": ["acme-shop/x.py"], "question": "What is this?"}),
            tool_call(5, "ask_files", {"paths": [], "question": "q"}),
            tool_call(6, "local_models", {}),
        ])
        assert responses[0]["result"]["serverInfo"]["name"] == "datrix-local-llm", responses[0]
        tools = responses[1]["result"]["tools"]
        assert [(t["name"], t["annotations"]["openWorldHint"]) for t in tools] == [
            ("ask_files", True), ("digest_log", True), ("local_models", True)], tools
        assert tool_result(responses[2]) == (False, tool_result(responses[2])[1]) and \
            "alpha: datrix-alpha/src/a.py:1" in tool_result(responses[2])[1]
        is_error, text = tool_result(responses[3])
        assert is_error and "outside what local-model tools may read" in text, text
        is_error, text = tool_result(responses[4])
        assert is_error and "'paths' is required" in text, text
        is_error, text = tool_result(responses[5])
        assert not is_error and "gate-model" in text and "mcp:ask_files: 1 requests" in text, text
        callers = [json.loads(line)["caller"] for line in log.read_text(encoding="utf-8").splitlines()]
        assert callers == ["mcp:ask_files"], f"a tool call must be logged under its tool's name: {callers}"


def check_mcp_server_reports_no_model_server_as_a_tool_error() -> None:
    with _workspace() as root:
        settings = _settings(closed_port(), root / "usage.jsonl")
        responses = exchange(LocalLlmServer(lambda: LocalReader(ReadScope(root), settings)), [
            tool_call(1, "ask_files", {"paths": ["datrix-alpha/src/a.py"], "question": "q"})])
        is_error, text = tool_result(responses[0])
        assert is_error and "No local Ollama server could answer" in text, text


def check_mcp_server_stdout_carries_only_protocol() -> None:
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        env = {**script_env(), USAGE_LOG_VARIABLE: str(Path(temp) / "usage.jsonl")}
        result = subprocess.run([sys.executable, "-m", MCP_SERVER_MODULE], capture_output=True, timeout=60, check=False,
                                input=b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages), env=env)
    lines = result.stdout.decode("utf-8").splitlines()
    assert result.returncode == 0 and len(lines) == 2, (result.returncode, lines, result.stderr[-500:])
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in lines), lines


# ===========================================================================
# model residency: -Pin, -Unpin and the -Status line
# ===========================================================================

_PREFERRED = OLLAMA_LOAD_PREFERENCE[0]
_INDEFINITELY = timedelta(days=200 * 365)


def _residency_settings(port: int) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, load_timeout_ms=5000,
                            ollama_port=port, usage_log=Path("unused"), caller="gate")


def check_pin_loads_the_preferred_model_with_an_indefinite_keep_alive() -> None:
    with LoopbackOllama(answering("ok"), ("other:7b", _PREFERRED)) as server:
        lines = pin_models(_residency_settings(server.port))
        assert lines == [f"{LOOPBACK}: pinned {_PREFERRED}"], lines
        assert server.generate_bodies == [{"model": _PREFERRED, "keep_alive": OLLAMA_KEEP_ALIVE_INDEFINITE}], \
            ("an already-loaded model is pinned too: its finite residency is not carried over", server.generate_bodies)
    with LoopbackOllama(answering("ok"), ("other:7b",)) as server:
        [line] = pin_models(_residency_settings(server.port))
        assert "not pinned: none of" in line and not server.generate_bodies, line
    [line] = pin_models(_residency_settings(closed_port()))
    assert "not pinned: no Ollama server answers" in line, line


def check_unpin_releases_only_indefinitely_resident_models() -> None:
    now = datetime.now(UTC)
    with LoopbackOllama(answering("ok"), (_PREFERRED,), expires_at=held_for(_INDEFINITELY)) as server:
        assert unpin_models(_residency_settings(server.port), now) == [f"{LOOPBACK}: released {_PREFERRED}"]
        assert server.generate_bodies == [{"model": _PREFERRED, "keep_alive": OLLAMA_KEEP_ALIVE_UNLOAD}], \
            server.generate_bodies
    with LoopbackOllama(answering("ok"), (_PREFERRED,), expires_at=held_for(timedelta(minutes=30))) as server:
        assert unpin_models(_residency_settings(server.port), now) == [f"{LOOPBACK}: nothing pinned"]
        assert not server.generate_bodies, "a model held for a while is not someone's pin"


def check_status_names_each_machine_with_no_pinned_model() -> None:
    now = datetime.now(UTC)
    settings = _residency_settings(1)
    host = LocalHost(ollama_base_url(LOOPBACK, settings), _PREFERRED)
    pinned = LocalCandidate(host, thinking=False, resident=True, resident_until=now + _INDEFINITELY)
    held = LocalCandidate(host, thinking=False, resident=True, resident_until=now + timedelta(minutes=30))
    assert unpinned_machine_lines(settings, [pinned], now) == []
    assert unpinned_machine_lines(settings, [held], now) == [
        f"{LOOPBACK}: no model pinned (local-llm.ps1 -Pin keeps one resident)"]
    assert len(unpinned_machine_lines(settings, [], now)) == 1, "a machine that did not answer holds no pin either"


# ===========================================================================
# a machine that holds no model is loaded
# ===========================================================================


def _installed_not_loaded(generated: list[dict[str, object]]) -> JsonResponder:
    """A model server with the preferred model installed and nothing in memory; it records each /api/generate body."""

    def respond(method: str, path: str, body: dict[str, object] | None) -> tuple[int, object]:
        if method == "GET" and path == "/api/tags":
            return HTTP_OK, {"models": [{"name": _PREFERRED, "capabilities": ["completion"]}]}
        if method == "GET" and path == "/api/ps":
            return HTTP_OK, {"models": []}
        if method == "POST" and path == "/api/generate" and body is not None:
            generated.append(body)
            return HTTP_OK, {"model": _PREFERRED, "done": True}
        return HTTP_NOT_FOUND, {"error": f"{method} {path}"}

    return respond


def _load_settings(port: int, temp: str) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, load_timeout_ms=5000, ollama_port=port,
                            usage_log=Path(temp) / "usage.jsonl", caller="gate")


def check_a_machine_holding_nothing_is_loaded_for_the_usual_window_and_not_pinned() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        generated: list[dict[str, object]] = []
        with LoopbackJsonServer(_installed_not_loaded(generated)) as server:
            settings = _load_settings(server.port, temp)
            lines = load_missing_models(settings)
        assert lines == [f"{LOOPBACK}: loaded {_PREFERRED} for 30 min"], lines
        assert generated == [{"model": _PREFERRED, "keep_alive": settings.keep_alive_seconds}], \
            ("the load carries the pool's window, never an indefinite keep-alive", generated)
        assert not (Path(temp) / LOAD_MISSING_LOCK_NAME).exists(), "the run's lock is released when it ends"


def _first_model_does_not_fit(generated: list[str]) -> JsonResponder:
    """A model server with both preferred models installed and nothing in memory, whose GPU fits only the second."""
    first, second = OLLAMA_LOAD_PREFERENCE[:2]

    def respond(method: str, path: str, body: dict[str, object] | None) -> tuple[int, object]:
        if method == "GET" and path == "/api/tags":
            return HTTP_OK, {"models": [{"name": m, "capabilities": ["completion"]} for m in (first, second)]}
        if method == "GET" and path == "/api/ps":
            return HTTP_OK, {"models": []}
        if method == "POST" and path == "/api/generate" and body is not None:
            generated.append(str(body["model"]))
            if body["model"] == first:
                return HTTP_SERVER_ERROR, {"error": "cudaMalloc failed: out of memory"}
            return HTTP_OK, {"model": second, "done": True}
        return HTTP_NOT_FOUND, {"error": f"{method} {path}"}

    return respond


def check_a_model_that_does_not_fit_falls_through_to_the_next_preferred() -> None:
    first, second = OLLAMA_LOAD_PREFERENCE[:2]
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        asked: list[str] = []
        with LoopbackJsonServer(_first_model_does_not_fit(asked)) as server:
            [line] = load_missing_models(_load_settings(server.port, temp))
        assert line == f"{LOOPBACK}: loaded {second} for 30 min", line
        assert asked == [first, second], ("the model that failed is tried first, then the next", asked)
        asked.clear()
        with LoopbackJsonServer(_first_model_does_not_fit(asked)) as server:
            settings = replace(_load_settings(server.port, temp), keep_alive_seconds=60)
            [line] = load_missing_models(settings)
        assert line.endswith("for 1 min"), ("the window is the settings', not a constant", line)


def check_a_machine_where_no_preferred_model_fits_reports_every_failure() -> None:
    first, _ = OLLAMA_LOAD_PREFERENCE[:2]
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        generated: list[str] = []

        def refuse_everything(method: str, path: str, body: dict[str, object] | None) -> tuple[int, object]:
            status, answer = _first_model_does_not_fit(generated)(method, path, body)
            if method == "POST":
                return HTTP_SERVER_ERROR, {"error": "cudaMalloc failed: out of memory"}
            return status, answer

        with LoopbackJsonServer(refuse_everything) as server:
            [line] = load_missing_models(_load_settings(server.port, temp))
        assert line.startswith(f"{LOOPBACK}: nothing loaded: loading {first} failed") and "out of memory" in line, line
        assert generated == list(OLLAMA_LOAD_PREFERENCE[:2]), generated


def check_a_machine_holding_any_model_is_left_alone() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp, LoopbackOllama(answering("ok"), ("other:7b",)) as server:
        [line] = load_missing_models(_load_settings(server.port, temp))
        assert line == f"{LOOPBACK}: nothing loaded: it already holds a model", line
        assert not server.generate_bodies, ("a model the caller never asks for still counts as held", server.generate_bodies)


def check_a_second_load_run_exits_while_one_holds_the_lock() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        generated: list[dict[str, object]] = []
        with LoopbackJsonServer(_installed_not_loaded(generated)) as server:
            settings = _load_settings(server.port, temp)
            with held_lock(Path(temp) / LOAD_MISSING_LOCK_NAME, MISSING_LOAD_LOCK_STALE_SECONDS):
                try:
                    load_missing_models(settings)
                except LockBusy as busy:
                    assert "already holds" in str(busy), busy
                else:
                    raise AssertionError("a second load run worked while the first held the lock")
        assert not generated, generated


class _RecordingLauncher:
    """Collects the commands a load run would be started with, and leaves the log a started run leaves."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.logs: list[Path] = []

    def __call__(self, command: list[str], log: Path) -> None:
        self.commands.append(command)
        self.logs.append(log)
        log.write_text("", encoding="utf-8")


def check_discovery_starts_one_detached_load_for_a_machine_holding_nothing() -> None:
    standard = DEFAULT_LOCAL_MACHINES[0]
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        settings = LocalLlmSettings(usage_log=Path(temp) / "usage.jsonl", caller="gate")
        launcher = _RecordingLauncher()
        assert not start_missing_loads(settings, [], launcher), "every machine holds a model: nothing to start"
        assert not start_missing_loads(settings, ["192.0.2.1"], launcher), "a machine the run does not serve"
        assert not start_missing_loads(replace(settings, ollama_port=OLLAMA_PORT + 1), [standard], launcher), \
            "the run reaches the standard port only"
        assert not launcher.commands
        assert start_missing_loads(settings, [standard], launcher), "an empty machine starts a run"
        assert launcher.commands == [[sys.executable, "-m", LOAD_MISSING_MODULE, "--load-missing"]], launcher.commands
        assert launcher.logs == [Path(temp) / LOAD_MISSING_LOG_NAME], launcher.logs
        assert not start_missing_loads(settings, [standard], launcher), \
            "a run that just ran (or is failing to load) is not started again at once"
        (Path(temp) / LOAD_MISSING_LOG_NAME).unlink()
        with held_lock(Path(temp) / LOAD_MISSING_LOCK_NAME, MISSING_LOAD_LOCK_STALE_SECONDS):
            assert not start_missing_loads(settings, [standard], launcher), "no second run while one holds the lock"
        assert start_missing_loads(settings, [standard], launcher), "once the run is over and quiet, the next starts"


def check_a_survey_says_whether_the_server_holds_any_model() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp:
        with LoopbackJsonServer(_installed_not_loaded([])) as server:
            settings = _load_settings(server.port, temp)
            empty = survey_ollama(ollama_base_url(LOOPBACK, settings), settings)
        assert not empty.holds_a_model, empty
        with LoopbackOllama(answering("ok"), ("other:7b",)) as server:
            settings = _load_settings(server.port, temp)
            held = survey_ollama(ollama_base_url(LOOPBACK, settings), settings)
        assert held.holds_a_model, held


# ===========================================================================
# readiness at the run's context window
# ===========================================================================

_RUN_WINDOW = 45056
_OTHER_WINDOW = 32768


def _readied(server: LoopbackOllama, context_window: int | None) -> list[dict[str, object]]:
    """The /api/generate bodies the server received while a pool readied its model for a run."""
    LocalLlmPool(_residency_settings(server.port), report=lambda _line: None).activate(context_window)
    return server.generate_bodies


def check_a_pool_readies_the_model_at_the_runs_window() -> None:
    with LoopbackOllama(answering("ok"), (_PREFERRED,), context_length=_OTHER_WINDOW) as server:
        unload, load = _readied(server, _RUN_WINDOW)
        assert unload == {"model": _PREFERRED, "keep_alive": OLLAMA_KEEP_ALIVE_UNLOAD}, \
            ("a model held at another window is unloaded before the load", unload)
        assert load["options"] == {"num_ctx": _RUN_WINDOW}, ("the load carries the run's window", load)
        assert server.context_length == _RUN_WINDOW, "the server now holds the run's window"
    with LoopbackOllama(answering("ok"), (_PREFERRED,), context_length=_RUN_WINDOW) as server:
        [load] = _readied(server, _RUN_WINDOW)
        assert load["options"] == {"num_ctx": _RUN_WINDOW}, ("a model held at the window is not unloaded", load)
    with LoopbackOllama(answering("ok"), (_PREFERRED,)) as server:
        [load] = _readied(server, _RUN_WINDOW)
        assert load["options"] == {"num_ctx": _RUN_WINDOW}, ("a window the server does not state is loaded", load)


def check_a_pool_readied_without_a_window_neither_unloads_nor_names_one() -> None:
    with LoopbackOllama(answering("ok"), (_PREFERRED,), context_length=_OTHER_WINDOW) as server:
        [load] = _readied(server, None)
        assert "options" not in load and server.context_length == _OTHER_WINDOW, (load, server.context_length)


# ===========================================================================
# a request that times out, and a readiness step that hangs
# ===========================================================================

# The pool waits _ASK_SECONDS for an answer (the shortest wait a request is given is one second);
# a stalled chat is silent for _STALL_SECONDS, longer.
_ASK_SECONDS = 1.0
_STALL_SECONDS = 1.6
_STALLED = "stall"
_TIMEOUT_WAIT_SECONDS = 5.0


def _stalls(times: int) -> ChatAnswer:
    """An answer that stays silent past the pool's timeout for the first *times* chats asking ``_STALLED``."""
    lock = threading.Lock()
    asked = [0]

    def answer(chat: Chat) -> str:
        if chat.user == _STALLED:
            with lock:
                asked[0] += 1
                stalled = asked[0] <= times
            if stalled:
                time.sleep(_STALL_SECONDS)
        return "ok"

    return answer


def _timing_out_pool(server: LoopbackOllama, temp: str) -> LocalLlmPool:
    settings = LocalLlmSettings(
        machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=int(_ASK_SECONDS * 1000),
        allow_load=False, ollama_port=server.port, usage_log=Path(temp) / "usage.jsonl", caller="gate")
    return LocalLlmPool(settings, report=lambda _line: None)


def _ask(user: str) -> ChatRequest:
    return ChatRequest(system="s", user=user, temperature=0.0)


def _asked_in_background(pool: LocalLlmPool, user: str) -> tuple[threading.Thread, list[LocalLlmReply | Exception]]:
    """Start ``pool.chat`` for *user* on a thread; the list receives its reply, or the exception it raised."""
    outcome: list[LocalLlmReply | Exception] = []

    def run() -> None:
        try:
            outcome.append(pool.chat(_ask(user)))
        except LocalLlmUnavailable as exc:
            outcome.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _wait_until_asked(server: LoopbackOllama, user: str) -> None:
    deadline = time.monotonic() + _TIMEOUT_WAIT_SECONDS
    while not any(chat.user == user for chat in server.chats):
        assert time.monotonic() < deadline, f"the server was never asked '{user}'"
        time.sleep(0.01)


def check_a_timeout_on_a_server_that_answered_others_is_asked_again_not_dropped() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp, LoopbackOllama(_stalls(1)) as server:
        pool = _timing_out_pool(server, temp)
        thread, outcome = _asked_in_background(pool, _STALLED)
        _wait_until_asked(server, _STALLED)
        assert pool.chat(_ask("quick")).text == "ok", "the server answers while the stalled request waits"
        thread.join()
        [reply] = outcome
        assert isinstance(reply, LocalLlmReply) and reply.text == "ok", \
            ("the timed-out request is asked again and answered", reply)
        assert not pool.is_exhausted(), "a server that answered others is not dropped for one timeout"
        assert [chat.user for chat in server.chats].count(_STALLED) == 2, [chat.user for chat in server.chats]


def check_a_timeout_drops_a_server_that_answered_nothing_or_timed_out_twice() -> None:
    with TemporaryDirectory(prefix="local-llm-gate-") as temp, LoopbackOllama(_stalls(9)) as server:
        thread, outcome = _asked_in_background(_timing_out_pool(server, temp), _STALLED)
        thread.join()
        [failure] = outcome
        assert isinstance(failure, LocalLlmUnavailable), ("a silent server is dropped at its first timeout", failure)
        assert [chat.user for chat in server.chats] == [_STALLED], "and the request is not asked of it again"
    with TemporaryDirectory(prefix="local-llm-gate-") as temp, LoopbackOllama(_stalls(2)) as server:
        pool = _timing_out_pool(server, temp)
        thread, outcome = _asked_in_background(pool, _STALLED)
        _wait_until_asked(server, _STALLED)
        pool.chat(_ask("quick"))
        thread.join()
        [failure] = outcome
        assert isinstance(failure, LocalLlmUnavailable), ("a second timeout of one request drops the server", failure)
        assert [chat.user for chat in server.chats].count(_STALLED) == 2, [chat.user for chat in server.chats]


_RENEW_SECONDS = 1.0
_HANG_SECONDS = 1.6
_READINESS_LOAD_SECONDS = 5.0


def _hanging_generate(held: bool) -> JsonResponder:
    """A model server whose every /api/generate stays silent for ``_HANG_SECONDS``; the model is held or not."""

    def respond(method: str, path: str, body: dict[str, object] | None) -> tuple[int, object]:
        if method == "GET" and path == "/api/tags":
            return HTTP_OK, {"models": [{"name": _PREFERRED, "capabilities": ["completion"]}]}
        if method == "GET" and path == "/api/ps":
            entries = [{"name": _PREFERRED, "expires_at": held_for_thirty_minutes(), "context_length": _RUN_WINDOW}]
            return HTTP_OK, {"models": entries if held else []}
        if method == "POST" and path == "/api/generate":
            time.sleep(_HANG_SECONDS)
            return HTTP_OK, {"model": _PREFERRED, "done": True}
        return HTTP_NOT_FOUND, {"error": f"{method} {path}"}

    return respond


def _readiness_settings(port: int, *, allow_load: bool) -> LocalLlmSettings:
    return LocalLlmSettings(
        machines=(LOOPBACK,), models=(_PREFERRED,), reachable_timeout_ms=2000, ollama_port=port, allow_load=allow_load,
        renew_timeout_ms=int(_RENEW_SECONDS * 1000), load_timeout_ms=int(_READINESS_LOAD_SECONDS * 1000),
        usage_log=Path("unused"), caller="gate")


def check_a_hung_renewal_fails_at_the_renew_timeout_and_a_cold_load_does_not() -> None:
    with LoopbackJsonServer(_hanging_generate(held=True)) as server:
        pool = LocalLlmPool(_readiness_settings(server.port, allow_load=False), report=lambda _line: None)
        started = time.monotonic()
        try:
            pool.activate(_RUN_WINDOW)
        except LocalLlmUnavailable as exc:
            assert "got no answer within 1 s" in str(exc), ("the failure names the limit it hit", str(exc))
        else:
            raise AssertionError("a held model whose renewal hangs was reported ready")
        assert time.monotonic() - started < _HANG_SECONDS, "the renewal was cut at the renew timeout"
    with LoopbackJsonServer(_hanging_generate(held=False)) as server:
        pool = LocalLlmPool(_readiness_settings(server.port, allow_load=True), report=lambda _line: None)
        assert pool.activate(_RUN_WINDOW).model == _PREFERRED, \
            "a cold load slower than the renew timeout is still waited for"


# ===========================================================================
# harness
# ===========================================================================


_ALL_CHECKS: list[CheckFunc] = [
    check_scope_reads_framework_repos_and_test_output_only,
    check_scope_reads_generation_logs_and_extra_roots_only_when_given,
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
    check_pin_loads_the_preferred_model_with_an_indefinite_keep_alive,
    check_unpin_releases_only_indefinitely_resident_models,
    check_status_names_each_machine_with_no_pinned_model,
    check_a_machine_holding_nothing_is_loaded_for_the_usual_window_and_not_pinned,
    check_a_model_that_does_not_fit_falls_through_to_the_next_preferred,
    check_a_machine_where_no_preferred_model_fits_reports_every_failure,
    check_a_machine_holding_any_model_is_left_alone,
    check_a_second_load_run_exits_while_one_holds_the_lock,
    check_discovery_starts_one_detached_load_for_a_machine_holding_nothing,
    check_a_survey_says_whether_the_server_holds_any_model,
    check_a_pool_readies_the_model_at_the_runs_window,
    check_a_pool_readied_without_a_window_neither_unloads_nor_names_one,
    check_a_timeout_on_a_server_that_answered_others_is_asked_again_not_dropped,
    check_a_timeout_drops_a_server_that_answered_nothing_or_timed_out_twice,
    check_a_hung_renewal_fails_at_the_renew_timeout_and_a_cold_load_does_not,
]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/local-llm-gate.ps1``: one per wrapper parameter, spelled exactly."""
    return check_list_parser(
        "Behaviour checks for the local-model reading tools.",
        debug_flag=WRAPPER_DEBUG_FLAG,
        allow_abbrev=False,
    )


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the harness reports a deliberate failure, and the wrapper is the template rendered
    # with this parser's options. Every model request of the checks is recorded in a temporary usage log.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        "local-model reading",
        _ALL_CHECKS,
        self_test=seam_checks(wrapper=WRAPPER, module=MODULE, parser=parser, folder=DEV_SCRIPTS_DIR),
        temp_file_variable=GATE_USAGE_LOG,
        argv=argv,
        parser=parser,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
