#!/usr/bin/env python3
"""The local model servers as an MCP server over standard input/output, for Claude Code.

Registered per machine with ``local-llm.ps1 -Setup``; Claude Code then starts it for each
session. Its tools hand reading work to the local model servers (``shared.local_llm``): an
agent names files or a log and gets back a short answer citing ``path:line``, instead of
reading the text into its own context. What may be sent is fenced by
``shared.local_reading.ReadScope`` (framework repositories and test output only).

Unlike the code index, these tools DO contact other machines: the model servers on the local
network. Standard input/output stays the only channel to Claude Code; no socket is opened.
Every request is recorded in the local-model usage log under ``mcp:<tool>``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.local_llm import (  # noqa: E402
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    discover_candidates,
)
from shared.local_llm_usage import usage_report  # noqa: E402
from shared.local_reading import ReadScope, ReadScopeError, ask_files, digest_log  # noqa: E402
from shared.mcp_stdio import (  # noqa: E402
    JsonObject,
    McpServer,
    ServerInfo,
    Tool,
    bounded_int,
    bounded_int_property,
    optional_text,
    required_text,
    serve,
    text_list,
)
from shared.venv import get_datrix_root  # noqa: E402

LOG = logging.getLogger(__name__)

SERVER_NAME = "datrix-local-llm"
SERVER_VERSION = "1"
MAX_PATH_SPECS = 20
DEFAULT_USAGE_DAYS = 1
MAX_USAGE_DAYS = 90

SERVER_INSTRUCTIONS = (
    "Local model servers on this network, for reading you would otherwise do yourself. ask_files answers a "
    "question about files you name (paths or globs) -- what code does, how something is validated -- and "
    "digest_log lists the distinct failures in a test, generation or deploy log. Both return a short answer "
    "citing path:line, so the text never enters your context. Use them before reading a large file whole or "
    "reading a log into context. They are NOT for definitions or call sites (use the code-index tools, which "
    "are exact: a model asked 'where is X defined' invents answers). An answer is a lead: confirm the cited "
    "lines with a ranged Read before acting on it. Only framework repositories and .test-output can be read."
)


@dataclass(frozen=True)
class LocalReader:
    """What every tool call needs: the read scope, and settings for a pool labelled by caller."""

    scope: ReadScope
    settings: LocalLlmSettings

    def pool(self, tool: str) -> LocalLlmPool:
        # A fresh pool per call: a pool drops a failed server for its lifetime, and a long-lived
        # server process must not stay blind to a model server that has since come back.
        return LocalLlmPool(replace(self.settings, caller=f"mcp:{tool}"), report=lambda line: LOG.info("%s", line))


def _ask_files(reader: LocalReader, args: JsonObject) -> str:
    specs = text_list(args, "paths", MAX_PATH_SPECS)
    return ask_files(reader.scope, reader.pool("ask_files"), specs, required_text(args, "question")).render()


def _digest_log(reader: LocalReader, args: JsonObject) -> str:
    return digest_log(reader.scope, reader.pool("digest_log"), required_text(args, "path"),
                      optional_text(args, "focus")).render()


def models_status(settings: LocalLlmSettings, days: int) -> str:
    """Which servers answer and what they hold in memory, then the usage report for ``days``."""
    lines: list[str] = []
    candidates = discover_candidates(settings, lines.append)
    usable = ", ".join(candidate.host.label() for candidate in candidates) or "none"
    return "\n".join([*lines, f"Usable now (resident): {usable}", "",
                      usage_report(settings.usage_log, days).render()])


def _local_models(reader: LocalReader, args: JsonObject) -> str:
    return models_status(reader.settings, bounded_int(args, "days", DEFAULT_USAGE_DAYS, MAX_USAGE_DAYS))


TOOLS: tuple[Tool[LocalReader], ...] = (
    Tool(
        "ask_files",
        "Ask a local model a question about files, instead of reading them yourself. Name up to 40 files by "
        "workspace-relative path or glob (datrix-common/src/datrix_common/config/*.py); they are read on this "
        "machine and you get back a short answer citing path:line. Use it for 'what does this module do', "
        "'how is X validated', 'which of these files handle Y', or any question whose answer is a few lines "
        "out of a lot of text. NOT for 'where is X defined' or 'who calls X': a model asked that invents "
        "definitions and callers in files it was never given (observed), so use the code-index tools "
        "find_symbol / find_references, which are exact. Large inputs are split and answered part by part. "
        "Citations of files or lines it was not sent, and quoted code that is not in those files, are called "
        "out under the answer; a claim in plain prose is not checked. Not for editing, and not a substitute "
        "for reading the exact lines you will change: confirm cited lines with a ranged Read.",
        {"paths": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": MAX_PATH_SPECS},
         "question": {"type": "string"}},
        ("paths", "question"),
        _ask_files,
        open_world=True,
    ),
    Tool(
        "digest_log",
        "List the distinct failures in a test, generation or deploy log, instead of reading the log into your "
        "context: one entry per cause with its message, count, first log line and the source file:line it "
        "names. A log too large to read whole is cut to the lines around error markers (or its end when it "
        "has none), keeping original line numbers. Pass a workspace-relative path under .test-output or a "
        "package's .test_results; 'focus' narrows it (e.g. 'only the import errors').",
        {"path": {"type": "string"}, "focus": {"type": "string"}},
        ("path",),
        _digest_log,
        open_world=True,
    ),
    Tool(
        "local_models",
        "Show which local model servers answer right now and which models they hold in memory, and how much "
        "the local models were used over the last 'days' days (default 1), by caller and by server.",
        {"days": bounded_int_property(DEFAULT_USAGE_DAYS, MAX_USAGE_DAYS)},
        (),
        _local_models,
        open_world=True,
    ),
)


def mcp_settings() -> LocalLlmSettings:
    """Settings for a tool call: models already in memory only -- a call must answer in seconds, so it
    never waits out a multi-minute model load."""
    return LocalLlmSettings(allow_load=False)


class LocalLlmServer(McpServer[LocalReader]):
    """Answers MCP requests by reading through the local model servers."""

    def __init__(self, reader_factory: Callable[[], LocalReader]) -> None:
        super().__init__(ServerInfo(SERVER_NAME, SERVER_VERSION, SERVER_INSTRUCTIONS), TOOLS,
                         (ReadScopeError, LocalLlmUnavailable))
        self._reader_factory = reader_factory
        self._reader: LocalReader | None = None

    def run_tool(self, tool: Tool[LocalReader], arguments: JsonObject) -> str:
        if self._reader is None:
            self._reader = self._reader_factory()
        return tool.handler(self._reader, arguments)


def _workspace_reader() -> LocalReader:
    return LocalReader(ReadScope(get_datrix_root()), mcp_settings())


def main() -> int:
    # Standard output is the protocol channel; every log line goes to standard error.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve(LocalLlmServer(_workspace_reader), sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
