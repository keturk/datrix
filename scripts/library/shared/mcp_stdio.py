"""The MCP protocol over standard input/output, shared by every Datrix MCP server.

Each server (the code index, the local-model reader) supplies its tools and how to run one;
this module answers the protocol around them: ``initialize``, ``ping``, ``tools/list`` and
``tools/call`` as newline-delimited JSON-RPC 2.0 on stdin/stdout. It opens no socket.

Standard library only, on purpose: the servers must start on every development machine from
the shared venv without an extra dependency to install and keep in step.
"""

from __future__ import annotations

import json
import logging
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO, Generic, TypeVar

LOG = logging.getLogger(__name__)

# Newest first; a client asking for one of these gets it, any other gets the newest.
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

JSONRPC_VERSION = "2.0"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

JsonObject = dict[str, object]
Context = TypeVar("Context")


class ToolInputError(ValueError):
    """A tool was called with arguments it cannot use; the message says what to pass."""


@dataclass(frozen=True)
class Tool(Generic[Context]):
    """One tool: what the client is told about it, and the handler that answers it."""

    name: str
    description: str
    properties: JsonObject
    required: tuple[str, ...]
    handler: Callable[[Context, JsonObject], str]
    # True when answering contacts anything beyond this machine's files.
    open_world: bool = False

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
            "annotations": {"readOnlyHint": True, "openWorldHint": self.open_world},
        }


@dataclass(frozen=True)
class ServerInfo:
    name: str
    version: str
    instructions: str


def required_text(args: JsonObject, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"'{key}' is required and must be a non-empty string.")
    return value


def optional_text(args: JsonObject, key: str) -> str:
    """The value of an optional string argument; an absent one is the empty string."""
    if key not in args:
        return ""
    value = args[key]
    if not isinstance(value, str):
        raise ToolInputError(f"'{key}' must be a string; got {value!r}.")
    return value


def text_list(args: JsonObject, key: str, max_items: int) -> list[str]:
    value = args.get(key)
    if not isinstance(value, list) or not value or len(value) > max_items:
        raise ToolInputError(f"'{key}' is required: a list of 1 to {max_items} strings; got {value!r}.")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ToolInputError(f"Every entry of '{key}' must be a non-empty string; got {value!r}.")
    return [str(item) for item in value]


def bounded_int(args: JsonObject, key: str, default: int, maximum: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ToolInputError(f"'{key}' must be an integer from 1 to {maximum}; got {value!r}.")
    return value


def flag(args: JsonObject, key: str) -> bool:
    value = args.get(key, False)
    if not isinstance(value, bool):
        raise ToolInputError(f"'{key}' must be true or false; got {value!r}.")
    return value


def bounded_int_property(default: int, maximum: int) -> JsonObject:
    return {"type": "integer", "minimum": 1, "maximum": maximum, "default": default}


class McpServer(ABC, Generic[Context]):
    """Answers MCP requests for a fixed set of tools; subclasses say how one call runs."""

    def __init__(self, info: ServerInfo, tools: tuple[Tool[Context], ...],
                 expected_errors: tuple[type[Exception], ...]) -> None:
        self._info = info
        self._tools = {tool.name: tool for tool in tools}
        # Errors whose message is the answer (bad input, nothing found): returned as tool text,
        # never logged as a failure of the server.
        self._expected_errors = (ToolInputError, *expected_errors)

    @abstractmethod
    def run_tool(self, tool: Tool[Context], arguments: JsonObject) -> str:
        """Answer one call of ``tool``; raise one of the expected errors to answer with its message."""

    def close(self) -> None:
        """Release what the server opened; nothing by default."""
        return

    def handle(self, message: object) -> JsonObject | None:
        """The response to one JSON-RPC message, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != JSONRPC_VERSION:
            return error_response(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 object.")
        method = message.get("method")
        request_id = message.get("id")
        if "id" not in message:
            return None
        params = message.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            return error_response(request_id, INVALID_REQUEST,
                                  "A request needs a string 'method' and object 'params'.")
        if method == "initialize":
            return result_response(request_id, self._initialize(params))
        if method == "ping":
            return result_response(request_id, {})
        if method == "tools/list":
            return result_response(request_id, {"tools": [tool.listing() for tool in self._tools.values()]})
        if method == "tools/call":
            return self._call(request_id, params)
        return error_response(request_id, METHOD_NOT_FOUND, f"Unknown method '{method}'.")

    def _initialize(self, params: JsonObject) -> JsonObject:
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self._info.name, "version": self._info.version},
            "instructions": self._info.instructions,
        }

    def _call(self, request_id: object, params: JsonObject) -> JsonObject:
        name = params.get("name")
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return error_response(request_id, INVALID_PARAMS,
                                  f"Unknown tool {name!r}. Tools: {', '.join(self._tools)}.")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return error_response(request_id, INVALID_PARAMS, "'arguments' must be an object.")
        try:
            text = self.run_tool(tool, arguments)
        except self._expected_errors as exc:
            return result_response(request_id, tool_text(str(exc), is_error=True))
        except Exception as exc:  # the server must answer and keep serving; the trace goes to stderr
            LOG.error("Tool %s failed:\n%s", tool.name, traceback.format_exc())
            return result_response(request_id,
                                   tool_text(f"{tool.name} failed: {type(exc).__name__}: {exc}", is_error=True))
        return result_response(request_id, tool_text(text, is_error=False))


def tool_text(text: str, *, is_error: bool) -> JsonObject:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def result_response(request_id: object, result: JsonObject) -> JsonObject:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: object, code: int, message: str) -> JsonObject:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}


def _respond(server: McpServer[Context], line: bytes) -> object | None:
    try:
        message = json.loads(line)
    except ValueError as exc:
        return error_response(None, PARSE_ERROR, f"Not JSON: {exc}")
    if isinstance(message, list):
        responses = [response for item in message if (response := server.handle(item)) is not None]
        return responses or None
    return server.handle(message)


def serve(server: McpServer[Context], stdin: BinaryIO, stdout: BinaryIO) -> None:
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
