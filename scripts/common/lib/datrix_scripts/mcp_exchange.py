"""Talking to a Datrix MCP server in process, for the gates that check one.

A gate hands ``exchange`` the server object and the JSON-RPC messages a client would send; the
server answers through the real ``mcp_stdio.serve`` loop over in-memory streams, so a check sees
exactly the lines Claude Code would read.
"""

from __future__ import annotations

import io
import json

from datrix_scripts.mcp_stdio import Context, McpServer, serve


def exchange(server: McpServer[Context], messages: list[object]) -> list[dict[str, object]]:
    """The server's response lines to ``messages``, one JSON-RPC message per line, in order."""
    stdin = io.BytesIO(b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages))
    stdout = io.BytesIO()
    serve(server, stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def tool_call(request_id: int, name: str, arguments: dict[str, object]) -> dict[str, object]:
    """A ``tools/call`` request for ``name`` with ``arguments``."""
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def tool_result(response: dict[str, object]) -> tuple[bool, str]:
    """(is error, text) of a ``tools/call`` response."""
    result = response["result"]
    assert isinstance(result, dict), response
    content = result["content"]
    assert isinstance(content, list)
    return bool(result["isError"]), str(content[0]["text"])
