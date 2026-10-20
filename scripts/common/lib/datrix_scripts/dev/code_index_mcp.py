#!/usr/bin/env python3
"""The code index as an MCP server over standard input/output, for Claude Code.

Registered per machine with ``code-index.ps1 -Setup``; Claude Code then starts it
for each session. It speaks newline-delimited JSON-RPC 2.0 on stdin/stdout
(``datrix_scripts.mcp_stdio``) and opens no socket, so it has no network surface. Every tool
call refreshes the index first (only changed files are parsed) and never contacts another
machine itself; when the refresh changed files, it starts a detached background run that
summarizes the changed modules on the local model servers (``datrix_scripts.code_index.background``).
The registration sets ``PYTHONPATH`` to ``scripts/common/lib`` so the shared package resolves.

Standard library only, on purpose: it must start on every development machine from the
shared venv without an extra dependency to install and keep in step.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from datrix_scripts.code_index.background import Launcher, launch_detached, start_background_summaries
from datrix_scripts.code_index.queries import (
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
from datrix_scripts.code_index.session import IndexSession, open_session
from datrix_scripts.code_index.sources import CodeIndexError
from datrix_scripts.code_index.summaries import summarizable
from datrix_scripts.mcp_stdio import (
    JsonObject,
    McpServer,
    ServerInfo,
    Tool,
    ToolInputError,
    bounded_int,
    bounded_int_property,
    flag,
    required_text,
    serve,
)

SERVER_NAME = "datrix-code-index"
SERVER_VERSION = "1"

MAX_LIMIT = 500

SERVER_INSTRUCTIONS = (
    "Index of every Python file in the Datrix workspace repositories on this machine, refreshed "
    "before each answer. Prefer these tools to grep-and-read when looking for a definition "
    "(find_symbol), its uses (find_references), the shape of a file (outline), code by what it "
    "does (search), or the declared canonical implementation of a concept (find_canonical)."
)


def _limit(args: JsonObject, default: int) -> int:
    return bounded_int(args, "limit", default, MAX_LIMIT)


def _kind(args: JsonObject) -> str | None:
    value = args.get("kind")
    if value is None:
        return None
    if value not in SYMBOL_KINDS:
        raise ToolInputError(f"'kind' must be one of {', '.join(SYMBOL_KINDS)}; got {value!r}.")
    return str(value)


def _limit_property(default: int) -> JsonObject:
    return bounded_int_property(default, MAX_LIMIT)


def _status(session: IndexSession, _args: JsonObject) -> str:
    paths = {candidate.path for candidate in summarizable(session.conn, session.config)}
    return status(session.conn, paths).render()


TOOLS: tuple[Tool[IndexSession], ...] = (
    Tool(
        "find_symbol",
        "Find where a Python name is defined anywhere in the Datrix workspace (every repository's src, "
        "tests and scripts). Accepts a bare name (to_snake_case), a glob (*Resolver), Class.method, or a "
        "dotted path. Returns file:line, the signature, the dotted path and the first docstring line -- "
        "cheaper than grepping and opening files. Offers similar names when nothing matches.",
        {"name": {"type": "string"}, "kind": {"type": "string", "enum": list(SYMBOL_KINDS)},
         "limit": _limit_property(DEFAULT_SYMBOL_LIMIT)},
        ("name",),
        lambda s, a: find_symbol(s.conn, required_text(a, "name"), _kind(a),
                                 _limit(a, DEFAULT_SYMBOL_LIMIT)).render(),
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
        lambda s, a: find_references(s.conn, required_text(a, "target"),
                                     _limit(a, DEFAULT_REFERENCE_FILE_LIMIT)).render(),
    ),
    Tool(
        "outline",
        "List a Python file's classes, functions, methods and constants in source order, with line "
        "ranges, signatures and first docstring lines, plus the module docstring and summary. Read this "
        "before opening a large file, then read only the lines you need. Accepts a workspace-relative "
        "path, a unique path suffix, or a dotted module name.",
        {"path": {"type": "string"}},
        ("path",),
        lambda s, a: outline(s.conn, required_text(a, "path")).render(),
    ),
    Tool(
        "search",
        "Ranked full-text search over definition names (identifiers split into words), signatures, "
        "docstrings, module summaries and logic-map markers. Use when you know what code does but not "
        "what it is called. Matching is by stemmed words, not meaning: try the words the code would use.",
        {"query": {"type": "string"}, "limit": _limit_property(DEFAULT_SEARCH_LIMIT)},
        ("query",),
        lambda s, a: search(s.conn, required_text(a, "query"), _limit(a, DEFAULT_SEARCH_LIMIT)).render(),
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
        lambda s, a: find_canonical(s.conn, required_text(a, "query"), flag(a, "include_test_rules"),
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


class CodeIndexServer(McpServer[IndexSession]):
    """Answers MCP requests; opens the index on the first tool call, not at startup.

    With a ``summary_launcher``, a call whose refresh changed files -- and the first call,
    which may find modules left unsummarized since the last session -- starts a background
    summarize run of the modules awaiting a summary (``code_index.background``).
    """

    def __init__(self, session_factory: Callable[[], IndexSession] = open_session,
                 summary_launcher: Launcher | None = None) -> None:
        super().__init__(ServerInfo(SERVER_NAME, SERVER_VERSION, SERVER_INSTRUCTIONS), TOOLS,
                         (QueryError, CodeIndexError))
        self._session_factory = session_factory
        self._session: IndexSession | None = None
        self._summary_launcher = summary_launcher
        self._summaries_checked = False

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def run_tool(self, tool: Tool[IndexSession], arguments: JsonObject) -> str:
        if self._session is None:
            self._session = self._session_factory()
        report = self._session.refresh()
        changed = bool(report.parsed or report.removed)
        if self._summary_launcher is not None and (changed or not self._summaries_checked):
            self._summaries_checked = True
            start_background_summaries(self._session, self._summary_launcher)
        text = tool.handler(self._session, arguments)
        if report.parsed or report.removed:
            text = f"{text}\n({report.line()})"
        return text


def main() -> int:
    # Standard output is the protocol channel; every log line goes to standard error.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve(CodeIndexServer(summary_launcher=launch_detached), sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
