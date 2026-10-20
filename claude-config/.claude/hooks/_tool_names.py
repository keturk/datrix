"""Tool names the hooks treat alike: a read through the line-edit MCP server is a Read.

The ``datrix-edit`` MCP server (``datrix_scripts.dev.line_edit_mcp``) reads files with
``read_lines`` and edits them with ``edit_lines``. A hook that looks at what a session read
counts ``read_lines`` exactly as ``Read`` (both take ``file_path``, ``offset`` and ``limit``);
``route-line-edits.py`` runs the Write/Edit guards over every ``edit_lines`` call.
"""

from __future__ import annotations

from typing import Final

LINE_READ_TOOL: Final = "mcp__datrix-edit__read_lines"
LINE_EDIT_TOOL: Final = "mcp__datrix-edit__edit_lines"
READ_TOOLS: Final = frozenset({"Read", LINE_READ_TOOL})
