#!/usr/bin/env python3
"""Query the code index from a shell: definitions, references, outlines, search, markers.

Every command refreshes the index first (only changed files are parsed), then answers.
The same queries are served to agents by ``code_index_mcp.py``.

Usage:
    python code_index_cli.py symbol to_snake_case
    python code_index_cli.py refs datrix_common.utils.text.to_snake_case
    python code_index_cli.py outline datrix-common/src/datrix_common/utils/text.py
    python code_index_cli.py search "tenant isolation header"
    python code_index_cli.py canonical text/to-snake
    python code_index_cli.py status
    python code_index_cli.py summarize --limit 100

Exit codes: 0 answered, 1 the query or the index could not be answered as asked,
2 no local model server could summarize.
"""

from __future__ import annotations

import argparse
import sys

from datrix_scripts.code_index.background import (
    LOG_NAME,
    SummarizeBusy,
    start_background_summaries,
    summarize_lock,
)
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
from datrix_scripts.code_index.sources import CodeIndexError, index_dir
from datrix_scripts.code_index.summaries import (
    DEFAULT_SUMMARY_LIMIT,
    DEFAULT_SUMMARY_WORKERS,
    summarizable,
    summarize,
)
from datrix_scripts.code_index.usage import usage_report
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)

EXIT_OK = 0
EXIT_QUERY_ERROR = 1
EXIT_NO_MODEL = 2

# A summary request carries up to ~30k characters of module source and outline.
SUMMARY_TIMEOUT_MS = 300000
DEFAULT_USAGE_DAYS = 7


def _report(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _run(session: IndexSession, args: argparse.Namespace) -> str:
    conn = session.conn
    command = args.command
    if command == "symbol":
        return find_symbol(conn, args.name, args.kind, args.limit).render()
    if command == "refs":
        return find_references(conn, args.target, args.limit).render()
    if command == "outline":
        return outline(conn, args.path).render()
    if command == "search":
        return search(conn, " ".join(args.text), args.limit).render()
    if command == "canonical":
        return find_canonical(conn, " ".join(args.text), args.test_rules, args.limit).render()
    if command == "status":
        paths = {candidate.path for candidate in summarizable(conn, session.config)}
        return status(conn, paths).render()
    if command == "usage":
        return usage_report(session.workspace, args.days).render()
    if command == "summarize":
        try:
            with summarize_lock(session.workspace) as keep_lock_fresh:
                def report_progress(line: str) -> None:
                    _report(line)
                    keep_lock_fresh()

                pool = LocalLlmPool(local_llm_settings(args), report=report_progress)
                run = summarize(conn, session.workspace, session.config, pool, limit=args.limit,
                                workers=args.workers, report=report_progress)
        except SummarizeBusy as exc:
            return str(exc)
        return run.line()
    return ""


# Commands that answer a question. After their refresh, changed modules are summarized in the
# background (code_index.background); maintenance commands start nothing.
_QUERY_COMMANDS = frozenset({"symbol", "refs", "outline", "search", "canonical"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("refresh", help="Bring the index up to date and report what changed.")
    commands.add_parser("status", help="What the index holds: files, definitions, markers, summaries, syntax errors.")
    symbol = commands.add_parser("symbol", help="Definitions of a name, glob (*Resolver), Class.method or dotted path.")
    symbol.add_argument("name")
    symbol.add_argument("--kind", choices=SYMBOL_KINDS)
    symbol.add_argument("--limit", type=int, default=DEFAULT_SYMBOL_LIMIT)
    refs = commands.add_parser("refs", help="Where a definition is used, resolved through imports.")
    refs.add_argument("target")
    refs.add_argument("--limit", type=int, default=DEFAULT_REFERENCE_FILE_LIMIT, help="Files to list.")
    outline_cmd = commands.add_parser("outline", help="A file's definitions with signatures, in source order.")
    outline_cmd.add_argument("path", help="Workspace-relative path, unique path suffix, or dotted module name.")
    search_cmd = commands.add_parser("search", help="Ranked search over names, docstrings, summaries and markers.")
    search_cmd.add_argument("text", nargs="+")
    search_cmd.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    canonical = commands.add_parser("canonical", help="Logic-map markers (@canonical, @pattern, ...) for a topic.")
    canonical.add_argument("text", nargs="+")
    canonical.add_argument("--test-rules", action="store_true", help="Include @test-rule markers.")
    canonical.add_argument("--limit", type=int, default=DEFAULT_CANONICAL_LIMIT)
    usage_cmd = commands.add_parser(
        "usage", help="Index tool calls against the greps and file reads the index could have answered.")
    usage_cmd.add_argument("--days", type=int, default=DEFAULT_USAGE_DAYS, help="Days to cover; 0 = all logged.")
    summarize_cmd = commands.add_parser(
        "summarize", help="Ask a local model to summarize modules that have no summary for their current content.")
    summarize_cmd.add_argument("--limit", type=int, default=DEFAULT_SUMMARY_LIMIT, help="Modules to summarize; 0 = all.")
    summarize_cmd.add_argument("--workers", type=int, default=DEFAULT_SUMMARY_WORKERS, help="Parallel requests.")
    add_local_llm_arguments(summarize_cmd, generate_timeout_ms=SUMMARY_TIMEOUT_MS)
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    args = _parser().parse_args()
    try:
        session = open_session()
    except CodeIndexError as exc:
        _report(f"Error: {exc}")
        return EXIT_QUERY_ERROR
    try:
        refreshed = session.refresh()
        _report(refreshed.line())
        if args.command in _QUERY_COMMANDS and (refreshed.parsed or refreshed.removed) and \
                start_background_summaries(session):
            _report(f"Summarizing changed modules in the background (log: {index_dir(session.workspace) / LOG_NAME}).")
        output = _run(session, args)
    except (QueryError, CodeIndexError) as exc:
        _report(f"Error: {exc}")
        return EXIT_QUERY_ERROR
    except LocalLlmUnavailable as exc:
        _report(f"Error: {exc}")
        return EXIT_NO_MODEL
    finally:
        session.close()
    if output:
        print(output)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
