#!/usr/bin/env python3
"""The code index as an MCP server over standard input/output, for Claude Code.

Registered per machine with ``code-index.ps1 -Setup``; Claude Code then starts it
for each session. It speaks newline-delimited JSON-RPC 2.0 on stdin/stdout and opens no
socket, so it has no network surface. Every tool call refreshes the index first (only
changed files are parsed) and never contacts another machine.

Standard library only, on purpose: it must start on every development machine from the
shared venv without an extra dependency to install and keep in step.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from code_index.queries import (  # noqa: E402
    DEFAULT_CANONICAL_LIMIT,
    DEFAULT_REFERENCE_FILE_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SYMBOL_LIMIT,
    SYMBOL_KINDS,
    QueryError,
    find_canonical,
    find_references,
    find_symbol,
    outline,
    search,
    status,
)
from code_index.session import IndexSession, open_session  # noqa: E402
from code_index.sources import CodeIndexError  # noqa: E402
from code_index.summaries import summarizable  # noqa: E402

LOG = logging.getLogger(__name__)

SERVER_NAME = "datrix-code-index"
SERVER_VERSION = "1"
# Newest first; a client asking for one of these gets it, any other gets the newest.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

JSONRPC_VERSION = "2.0"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

MAX_LIMIT = 500

SERVER_INSTRUCTIONS = (
    "Index of every Python file in the Datrix workspace repositories on this machine, refreshed "
    "before each answer. Prefer these tools to grep-and-read when looking for a definition "
    "(find_symbol), its uses (find_references), the shape of a file (outline), code by what it "
    "does (search), or the declared canonical implementation of a concept (find_canonical)."
)

JsonObject = dict[str, object]


class ToolInputError(ValueError):
    """A tool was called with arguments it cannot use; the message says what to pass."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: JsonObject
    required: tuple[str, ...]
    handler: Callable[[IndexSession, JsonObject], str]

    def listing(self) -> JsonObject:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
        }


def _text(args: JsonObject, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"'{key}' is required and must be a non-empty string.")
    return value


def _limit(args: JsonObject, default: int) -> int:
    value = args.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise ToolInputError(f"'limit' must be an integer from 1 to {MAX_LIMIT}; got {value!r}.")
    return value


def _flag(args: JsonObject, key: str) -> bool:
    value = args.get(key, False)
    if not isinstance(value, bool):
        raise ToolInputError(f"'{key}' must be true or false; got {value!r}.")
    return value


def _kind(args: JsonObject) -> str | None:
    value = args.get("kind")
    if value is None:
        return None
    if value not in SYMBOL_KINDS:
        raise ToolInputError(f"'kind' must be one of {', '.join(SYMBOL_KINDS)}; got {value!r}.")
    return str(value)


def _limit_property(default: int) -> JsonObject:
    return {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": default}


def _status(session: IndexSession, _args: JsonObject) -> str:
    paths = {candidate.path for candidate in summarizable(session.conn, session.config)}
    return status(session.conn, paths).render()


TOOLS: tuple[Tool, ...] = (
    Tool(
        "find_symbol",
        "Find where a Python name is defined anywhere in the Datrix workspace (every repository's src, "
        "tests and scripts). Accepts a bare name (to_snake_case), a glob (*Resolver), Class.method, or a "
        "dotted path. Returns file:line, the signature, the dotted path and the first docstring line -- "
        "cheaper than grepping and opening files. Offers similar names when nothing matches.",
        {"name": {"type": "string"}, "kind": {"type": "string", "enum": list(SYMBOL_KINDS)},
         "limit": _limit_property(DEFAULT_SYMBOL_LIMIT)},
        ("name",),
        lambda s, a: find_symbol(s.conn, _text(a, "name"), _kind(a), _limit(a, DEFAULT_SYMBOL_LIMIT)).render(),
    ),
    Tool(
        "find_references",
        "Find every use of a definition. Module-level functions, classes and constants are resolved "
        "through imports, following aliases and re-exports. Methods and attributes match every '.name' "
        "access; receiver types are not checked, and the answer says so. Strings, comments and docstrings "
        "are not uses. Lists 'file: line kind' (import, call, name, attr, attr_call), production code "
        "before tests. Pass a dotted path (from find_symbol) when a bare name has several definitions.",
        {"target": {"type": "string"}, "limit": _limit_property(DEFAULT_REFERENCE_FILE_LIMIT)},
        ("target",),
        lambda s, a: find_references(s.conn, _text(a, "target"), _limit(a, DEFAULT_REFERENCE_FILE_LIMIT)).render(),
    ),
    Tool(
        "outline",
        "List a Python file's classes, functions, methods and constants in source order, with line "
        "ranges, signatures and first docstring lines, plus the module docstring and summary. Read this "
        "before opening a large file, then read only the lines you need. Accepts a workspace-relative "
        "path, a unique path suffix, or a dotted module name.",
        {"path": {"type": "string"}},
        ("path",),
        lambda s, a: outline(s.conn, _text(a, "path")).render(),
    ),
    Tool(
        "search",
        "Ranked full-text search over definition names (identifiers split into words), signatures, "
        "docstrings, module summaries and logic-map markers. Use when you know what code does but not "
        "what it is called. Matching is by stemmed words, not meaning: try the words the code would use.",
        {"query": {"type": "string"}, "limit": _limit_property(DEFAULT_SEARCH_LIMIT)},
        ("query",),
        lambda s, a: search(s.conn, _text(a, "query"), _limit(a, DEFAULT_SEARCH_LIMIT)).render(),
    ),
    Tool(
        "find_canonical",
        "Look up the logic map: the @canonical, @pattern, @boundary and @invariant markers that declare "
        "the one correct implementation of a concept, with their rules, anti-patterns and see-also "
        "topics. Query by topic path (text/to-snake), a topic segment (snake), or words. Check before "
        "implementing significant new logic, and reuse what it names instead of writing a variant. "
        "include_test_rules adds @test-rule markers.",
        {"query": {"type": "string"}, "include_test_rules": {"type": "boolean", "default": False},
         "limit": _limit_property(DEFAULT_CANONICAL_LIMIT)},
        ("query",),
        lambda s, a: find_canonical(s.conn, _text(a, "query"), _flag(a, "include_test_rules"),
                                    _limit(a, DEFAULT_CANONICAL_LIMIT)).render(),
    ),
    Tool(
        "index_status",
        "Report what the code index holds: when it last refreshed, file and definition counts, "
        "logic-map marker counts, module-summary coverage, and files with syntax errors.",
        {},
        (),
        _status,
    ),
)

_TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


class CodeIndexServer:
    """Answers MCP requests; opens the index on the first tool call, not at startup."""

    def __init__(self, session_factory: Callable[[], IndexSession] = open_session) -> None:
        self._session_factory = session_factory
        self._session: IndexSession | None = None

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def handle(self, message: object) -> JsonObject | None:
        """The response to one JSON-RPC message, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != JSONRPC_VERSION:
            return _error(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 object.")
        method = message.get("method")
        request_id = message.get("id")
        if "id" not in message:
            return None
        params = message.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            return _error(request_id, INVALID_REQUEST, "A request needs a string 'method' and object 'params'.")
        if method == "initialize":
            return _result(request_id, self._initialize(params))
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": [tool.listing() for tool in TOOLS]})
        if method == "tools/call":
            return self._call(request_id, params)
        return _error(request_id, METHOD_NOT_FOUND, f"Unknown method '{method}'.")

    def _initialize(self, params: JsonObject) -> JsonObject:
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": SERVER_INSTRUCTIONS,
        }

    def _call(self, request_id: object, params: JsonObject) -> JsonObject:
        name = params.get("name")
        tool = _TOOLS_BY_NAME.get(name) if isinstance(name, str) else None
        if tool is None:
            return _error(request_id, INVALID_PARAMS,
                          f"Unknown tool {name!r}. Tools: {', '.join(_TOOLS_BY_NAME)}.")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, INVALID_PARAMS, "'arguments' must be an object.")
        try:
            if self._session is None:
                self._session = self._session_factory()
            report = self._session.refresh()
            text = tool.handler(self._session, arguments)
        except (ToolInputError, QueryError, CodeIndexError) as exc:
            return _result(request_id, _tool_text(str(exc), is_error=True))
        except Exception as exc:  # the server must answer and keep serving; the trace goes to stderr
            LOG.error("Tool %s failed:\n%s", tool.name, traceback.format_exc())
            return _result(request_id, _tool_text(f"{tool.name} failed: {type(exc).__name__}: {exc}", is_error=True))
        if report.parsed or report.removed:
            text = f"{text}\n({report.line()})"
        return _result(request_id, _tool_text(text, is_error=False))


def _tool_text(text: str, *, is_error: bool) -> JsonObject:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _result(request_id: object, result: JsonObject) -> JsonObject:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> JsonObject:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}


def _respond(server: CodeIndexServer, line: bytes) -> object | None:
    try:
        message = json.loads(line)
    except ValueError as exc:
        return _error(None, PARSE_ERROR, f"Not JSON: {exc}")
    if isinstance(message, list):
        responses = [response for item in message if (response := server.handle(item)) is not None]
        return responses or None
    return server.handle(message)


def serve(server: CodeIndexServer, stdin: BinaryIO, stdout: BinaryIO) -> None:
    """Answer one JSON-RPC message per input line until the input closes."""
    try:
        for line in stdin:
            if not line.strip():
                continue
            response = _respond(server, line)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
                stdout.flush()
    finally:
        server.close()


def main() -> int:
    # Standard output is the protocol channel; every log line goes to standard error.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve(CodeIndexServer(), sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
