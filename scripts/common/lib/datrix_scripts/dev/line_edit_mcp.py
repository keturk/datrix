#!/usr/bin/env python3
"""Line-addressed reading and editing as an MCP server over standard input/output, for Claude Code.

Registered per machine with ``line-edit.ps1 -Setup``; Claude Code then starts it for each session
(with ``PYTHONPATH`` set to ``scripts/common/lib``). ``read_lines`` shows a file's lines numbered
and hashed; ``edit_lines`` replaces or inserts line ranges, many at once across files, naming the
old lines by number and hash instead of re-sending their text (``datrix_scripts.line_edits``).
The Write/Edit guards run over every ``edit_lines`` call through the ``route-line-edits.py`` hook.

Only existing UTF-8 text files under the workspace root are read or written. Nothing is sent off
this machine; standard input/output is the only channel to Claude Code.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from datrix_scripts.line_edits import MAX_EDITS_PER_CALL, MAX_READ_LINES, LineEditError, apply_edits, read_lines
from datrix_scripts.mcp_stdio import (
    JsonObject,
    McpServer,
    ServerInfo,
    Tool,
    ToolInputError,
    bounded_int,
    bounded_int_property,
    required_text,
    serve,
)
from datrix_scripts.paths import WORKSPACE_DIR

LOG = logging.getLogger(__name__)

SERVER_NAME = "datrix-edit"
SERVER_VERSION = "1"
DEFAULT_OFFSET = 1
MAX_OFFSET = 10_000_000

SERVER_INSTRUCTIONS = (
    "Line-addressed editing that does not re-send the old text. read_lines shows each line as "
    "'<number>:<hash>|<text>'; edit_lines then replaces lines by number plus the hash of every replaced line, "
    "or inserts after a line by its number and hash, so the old text never enters the conversation again. "
    "Prefer them over Edit when you change several places, or when Edit's old_string would be long or need "
    "padding to be unique: put every edit of a step in ONE edit_lines call, across files, with line numbers "
    "from the file as you read it (edits apply bottom-up). The reply lists each changed range's new numbers "
    "and hashes, so a follow-up edit needs no re-read. A mismatched hash is refused with the lines now there "
    "and nothing is written. After edit_lines changes a file, keep editing that file with edit_lines: the "
    "built-in Edit refuses a file changed outside it until you Read it again. New files are still written "
    "with Write. The Write/Edit guards apply to edit_lines exactly as to Edit."
)

_EDIT_ITEM_SCHEMA: JsonObject = {
    "type": "object",
    "description": ("Replace: {file_path, start, end, hashes, text} -- lines start..end (inclusive), hashes = the "
                    "2-character hash of every one of them in order (e.g. 'a3f0' for two lines), text = the new "
                    "lines ('' deletes them). Insert: {file_path, after, hash, text} -- after = the line to insert "
                    "below (0 = top of file), hash = that line's hash ('' for 0)."),
    "properties": {
        "file_path": {"type": "string"},
        "start": {"type": "integer", "minimum": 1},
        "end": {"type": "integer", "minimum": 1},
        "hashes": {"type": "string"},
        "after": {"type": "integer", "minimum": 0},
        "hash": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["file_path", "text"],
    "additionalProperties": False,
}


def _offset(args: JsonObject) -> int:
    return bounded_int(args, "offset", DEFAULT_OFFSET, MAX_OFFSET)


def _read_lines(root: Path, args: JsonObject) -> str:
    return read_lines(root, required_text(args, "file_path"), _offset(args),
                      bounded_int(args, "limit", MAX_READ_LINES, MAX_READ_LINES))


def _edit_lines(root: Path, args: JsonObject) -> str:
    if "edits" not in args:
        raise ToolInputError(f"'edits' is required: a list of 1 to {MAX_EDITS_PER_CALL} edit objects.")
    return apply_edits(root, args["edits"])


TOOLS: tuple[Tool[Path], ...] = (
    Tool(
        "read_lines",
        "Read a workspace text file with every line shown as '<number>:<hash>|<text>', for editing with "
        "edit_lines. Same paging as Read: 'offset' (first line, default 1) and 'limit' (default and maximum "
        f"{MAX_READ_LINES}). Read only the lines you will change or need to see.",
        {"file_path": {"type": "string"},
         "offset": bounded_int_property(DEFAULT_OFFSET, MAX_OFFSET),
         "limit": bounded_int_property(MAX_READ_LINES, MAX_READ_LINES)},
        ("file_path",),
        _read_lines,
    ),
    Tool(
        "edit_lines",
        "Replace or insert line ranges in existing workspace text files, many at once across files, naming the "
        "old lines by number and hash (from read_lines or an earlier edit_lines reply) instead of re-sending "
        "their text. Every line number refers to the files as they were before this call. Every edit is checked "
        "before any file is written; a hash that does not match the line now there refuses the whole call and "
        "shows those lines. Line endings, a byte-order mark and a missing final newline are kept.",
        {"edits": {"type": "array", "items": _EDIT_ITEM_SCHEMA, "minItems": 1, "maxItems": MAX_EDITS_PER_CALL}},
        ("edits",),
        _edit_lines,
        read_only=False,
    ),
)


class LineEditServer(McpServer[Path]):
    """Answers MCP requests by reading and editing files under one workspace root."""

    def __init__(self, root: Path) -> None:
        super().__init__(ServerInfo(SERVER_NAME, SERVER_VERSION, SERVER_INSTRUCTIONS), TOOLS, (LineEditError,))
        self._root = root

    def run_tool(self, tool: Tool[Path], arguments: JsonObject) -> str:
        return tool.handler(self._root, arguments)


def main() -> int:
    # Standard output is the protocol channel; every log line goes to standard error.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve(LineEditServer(WORKSPACE_DIR), sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
