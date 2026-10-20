#!/usr/bin/env python3
"""Query the code index from a shell: definitions, references, outlines, search, markers.

The module behind ``dev/code-index.ps1`` (and its ``.sh`` twin): exactly one action per run.
Every query refreshes the index first (only changed files are parsed), then answers. The same
queries are served to agents by ``datrix_scripts.dev.code_index_mcp``, which ``--setup``
registers in the workspace's ``.mcp.json``.

Exit codes: 0 answered, 1 the query or the index could not be answered as asked,
2 no local model server could summarize.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

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
from datrix_scripts.dev.mcp_setup import run_setup
from datrix_scripts.gate_harness import install_sigint_handler
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.code_index"
WRAPPER: Final = "code-index"
MCP_SERVER_NAME: Final = "datrix-code-index"
MCP_SERVER_MODULE: Final = "datrix_scripts.dev.code_index_mcp"
SETUP_COMMAND: Final = "code-index.ps1 -Setup"

EXIT_OK = 0
EXIT_QUERY_ERROR = 1
EXIT_NO_MODEL = 2

# A summary request carries up to ~30k characters of module source and outline.
SUMMARY_TIMEOUT_SECONDS: Final = 300
DEFAULT_USAGE_DAYS = 7
#: -Limit's "not given": each query keeps its own default.
LIMIT_NOT_GIVEN: Final = -1

#: The actions, in the order the usage message names them: (wrapper parameter, option dest).
ACTIONS: Final = (
    ("-Symbol", "symbol"),
    ("-References", "references"),
    ("-Outline", "outline"),
    ("-Search", "search"),
    ("-Canonical", "canonical"),
    ("-Status", "status"),
    ("-Refresh", "refresh"),
    ("-Usage", "usage"),
    ("-Summarize", "summarize"),
    ("-Setup", "setup"),
)
#: The default -Limit of each action that takes one.
DEFAULT_LIMITS: Final = {
    "symbol": DEFAULT_SYMBOL_LIMIT,
    "references": DEFAULT_REFERENCE_FILE_LIMIT,
    "search": DEFAULT_SEARCH_LIMIT,
    "canonical": DEFAULT_CANONICAL_LIMIT,
    "summarize": DEFAULT_SUMMARY_LIMIT,
}
# Actions that answer a question. After their refresh, changed modules are summarized in the
# background (code_index.background); maintenance actions start nothing.
_QUERY_ACTIONS = frozenset({"symbol", "references", "outline", "search", "canonical"})


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/code-index.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="", help="Definitions of a name, glob (*Resolver), Class.method or dotted path.")
    parser.add_argument("--kind", default="", choices=("", *SYMBOL_KINDS), help="With --symbol: only this kind.")
    parser.add_argument("--references", default="", help="Where a definition is used, resolved through imports.")
    parser.add_argument("--outline", default="",
                        help="A file's definitions with signatures: workspace-relative path, unique suffix or dotted module.")
    parser.add_argument("--search", default="", help="Ranked search over names, docstrings, summaries and markers.")
    parser.add_argument("--canonical", default="", help="Logic-map markers (@canonical, @pattern, ...) for a topic.")
    parser.add_argument("--include-test-rules", action="store_true", help="With --canonical: include @test-rule markers.")
    parser.add_argument("--status", action="store_true",
                        help="What the index holds: files, definitions, markers, summaries, syntax errors.")
    parser.add_argument("--refresh", action="store_true", help="Bring the index up to date and report what changed.")
    parser.add_argument("--usage", action="store_true",
                        help="Index tool calls against the greps and file reads the index could have answered.")
    parser.add_argument("--days", type=int, default=DEFAULT_USAGE_DAYS, help="With --usage: days to cover; 0 = all logged.")
    parser.add_argument("--summarize", action="store_true",
                        help="Ask a local model to summarize modules that have no summary for their current content.")
    parser.add_argument("--workers", type=int, default=DEFAULT_SUMMARY_WORKERS, help="With --summarize: parallel requests.")
    parser.add_argument("--limit", type=int, default=LIMIT_NOT_GIVEN,
                        help="Results, files or modules (--summarize: 0 = all). Default: each query's own default.")
    add_wrapper_llm_arguments(parser, timeout_seconds=SUMMARY_TIMEOUT_SECONDS)
    parser.add_argument("--setup", action="store_true",
                        help="Build the index, then register its MCP server for this machine in .mcp.json.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: exactly one action is required, and each query keeps its limit.")
    parser.set_defaults(debug=False)
    return parser


def chosen_actions(args: argparse.Namespace) -> list[str]:
    """The actions *args* asks for (an empty query string is no action), in usage order."""
    return [dest for _, dest in ACTIONS if getattr(args, dest)]


def action_usage_message(chosen: Sequence[str]) -> str:
    """The message for a run that names no action or several."""
    names = dict((dest, flag) for flag, dest in ACTIONS)
    given = ", ".join(names[dest] for dest in chosen) or "none"
    listed = ", ".join(flag for flag, _ in ACTIONS[:-1])
    return (f"Pass exactly one action: {listed} or {ACTIONS[-1][0]} (given: {given}). "
            "Get-Help .\\code-index.ps1 -Full lists them.")


def action_limit(action: str, limit: int) -> int:
    """The limit *action* runs with: -Limit when given, else the action's own default."""
    return limit if limit != LIMIT_NOT_GIVEN else DEFAULT_LIMITS[action]


def _report(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _answer(session: IndexSession, action: str, args: argparse.Namespace) -> str:
    conn = session.conn
    if action == "symbol":
        return find_symbol(conn, args.symbol, args.kind or None, action_limit(action, args.limit)).render()
    if action == "references":
        return find_references(conn, args.references, action_limit(action, args.limit)).render()
    if action == "outline":
        return outline(conn, args.outline).render()
    if action == "search":
        return search(conn, args.search, action_limit(action, args.limit)).render()
    if action == "canonical":
        return find_canonical(conn, args.canonical, args.include_test_rules, action_limit(action, args.limit)).render()
    if action == "status":
        paths = {candidate.path for candidate in summarizable(conn, session.config)}
        return status(conn, paths).render()
    if action == "usage":
        return usage_report(session.workspace, args.days).render()
    if action == "summarize":
        return _summarize(session, args)
    return ""


def _summarize(session: IndexSession, args: argparse.Namespace) -> str:
    try:
        with summarize_lock(session.workspace) as keep_lock_fresh:
            def report_progress(line: str) -> None:
                _report(line)
                keep_lock_fresh()

            pool = LocalLlmPool(wrapper_llm_settings(args), report=report_progress)
            run = summarize(session.conn, session.workspace, session.config, pool,
                            limit=action_limit("summarize", args.limit), workers=args.workers, report=report_progress)
    except SummarizeBusy as exc:
        return str(exc)
    return run.line()


def _query(action: str, args: argparse.Namespace) -> int:
    """Refresh the index, then answer *action*."""
    try:
        session = open_session()
    except CodeIndexError as exc:
        _report(f"Error: {exc}")
        return EXIT_QUERY_ERROR
    try:
        refreshed = session.refresh()
        _report(refreshed.line())
        if action in _QUERY_ACTIONS and (refreshed.parsed or refreshed.removed) and \
                start_background_summaries(session):
            _report(f"Summarizing changed modules in the background (log: {index_dir(session.workspace) / LOG_NAME}).")
        output = _answer(session, action, args)
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


def _setup(args: argparse.Namespace) -> int:
    """Build (or bring up to date) the index, then register its MCP server for this machine."""
    refreshed = _query("refresh", args)
    if refreshed != EXIT_OK:
        print("Building the index failed (see above); the MCP server was not set up.")
        return refreshed
    return run_setup(name=MCP_SERVER_NAME, module=MCP_SERVER_MODULE, workspace=WORKSPACE_DIR,
                     setup_command=SETUP_COMMAND)


def _check_exactly_one_action_is_required() -> None:
    parser = build_parser()
    assert chosen_actions(parser.parse_args([])) == []
    assert chosen_actions(parser.parse_args(["--symbol="])) == [], "an empty query string is no action"
    assert chosen_actions(parser.parse_args(["--refresh", "--status"])) == ["status", "refresh"]
    assert action_usage_message(["status", "refresh"]) == (
        "Pass exactly one action: -Symbol, -References, -Outline, -Search, -Canonical, -Status, -Refresh, "
        "-Usage, -Summarize or -Setup (given: -Status, -Refresh). Get-Help .\\code-index.ps1 -Full lists them."
    ), action_usage_message(["status", "refresh"])
    assert "(given: none)" in action_usage_message([])


def _check_each_query_keeps_its_limit() -> None:
    assert [action_limit(action, LIMIT_NOT_GIVEN) for action in DEFAULT_LIMITS] == list(DEFAULT_LIMITS.values())
    assert action_limit("summarize", 0) == 0, "-Summarize -Limit 0 summarizes every module"
    assert action_limit("symbol", 3) == 3


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_exactly_one_action_is_required, _check_each_query_keeps_its_limit]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    chosen = chosen_actions(args)
    if len(chosen) != 1:
        print(action_usage_message(chosen))
        return EXIT_QUERY_ERROR
    if chosen[0] == "setup":
        return _setup(args)
    return _query(chosen[0], args)


if __name__ == "__main__":
    sys.exit(main())
