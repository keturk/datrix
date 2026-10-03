#!/usr/bin/env python3
"""Ask the knowledge base what you need to know (wrapped by dev/ineedtoknow.ps1).

Usage:
    ineedtoknow_cli.py QUESTION...        answer from the knowledge base; if it holds no answer, have a
                                          local model read the closest docs and keep a grounded answer
    ineedtoknow_cli.py --status           what the knowledge base holds
    ineedtoknow_cli.py --rebuild          drop the database and rebuild it from the docs and learned files
    ineedtoknow_cli.py --prune            delete learned files whose sources changed on this machine

Exit codes: 0 answered; 1 the request could not be carried out (the message says why); 2 no answer
(not in the knowledge base, and no local model could add one).
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from dataclasses import replace
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from knowledge.gather import Gathered, gather, leads_for  # noqa: E402
from knowledge.learned_files import (  # noqa: E402
    LEARNED_DIR_RELATIVE,
    learned_dir,
    prune_stale,
    read_entries,
    stale_sources,
    sync_learned,
)
from knowledge.lookup import DEFAULT_ANSWERS, lookup, render  # noqa: E402
from knowledge.seed import sync_curated  # noqa: E402
from knowledge.store import KIND_CURATED, KIND_LEARNED, KnowledgeBase, KnowledgeError, knowledge_db_path  # noqa: E402
from shared.local_llm import (  # noqa: E402
    LocalLlmPool,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from shared.local_reading import ReadScope, ReadScopeError  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402

EXIT_ANSWERED = 0
EXIT_USAGE = 1
EXIT_NO_ANSWER = 2

# A gather reads a few chunks, so a short answer should take seconds; a model that is not already in
# memory is reported as unavailable rather than waited for (local-llm.ps1 -Status shows what is resident).
GATHER_TIMEOUT_MS = 120_000

LOG = logging.getLogger("ineedtoknow")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask the knowledge base what you need to know.")
    parser.add_argument("question", nargs="*", help="What you need to know, in your own words.")
    parser.add_argument("--in", dest="in_specs", action="append", default=[], metavar="PATH_OR_GLOB",
                        help="Also read these files (workspace-relative path or glob) to answer; implies a "
                             "local-model read instead of a lookup. Repeatable.")
    parser.add_argument("--refresh", action="store_true",
                        help="Skip the lookup and have a local model read the closest docs again.")
    parser.add_argument("--no-learn", action="store_true",
                        help="Look up only; never contact a local model.")
    parser.add_argument("--limit", type=int, default=DEFAULT_ANSWERS, help="Answers to show (default: %(default)s).")
    parser.add_argument("--status", action="store_true", help="Show what the knowledge base holds.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop the database and rebuild it from the docs and the committed learned files.")
    parser.add_argument("--prune", action="store_true",
                        help="Delete learned files whose sources changed on this machine.")
    add_local_llm_arguments(parser, generate_timeout_ms=GATHER_TIMEOUT_MS)
    return parser


def _status(kb: KnowledgeBase, scope: ReadScope) -> str:
    counts = kb.counts()
    files = read_entries(scope)
    stale = sum(1 for entry in files.values() if stale_sources(scope, entry))
    return "\n".join([
        f"database:      {kb.path}",
        f"docs:          {counts['docs']} ({counts[KIND_CURATED]} chunks)",
        f"learned (db):  {counts[KIND_LEARNED]}",
        f"learned files: {len(files)} in {LEARNED_DIR_RELATIVE} ({stale} stale on this machine)",
        f"text copy:     {learned_dir(scope)}",
    ])


def _show_gathered(gathered: Gathered) -> int:
    if gathered.stored:
        print(gathered.text)
        print(f"\n---\nLearned by a local model ({', '.join(gathered.models)}), citations checked against what it "
              f"was shown, and kept for the next question. A lead, not a finding: open the cited lines before "
              f"acting on it.")
        return EXIT_ANSWERED
    print(gathered.text)
    for problem in gathered.problems:
        print(f"- {problem}")
    _print_leads(gathered.leads)
    return EXIT_NO_ANSWER


def _print_leads(leads: tuple[str, ...]) -> None:
    if not leads:
        return
    print("\nClosest places to read yourself:")
    for lead in leads:
        print(f"  {lead}")


def _answer(args: argparse.Namespace, kb: KnowledgeBase, scope: ReadScope, question: str) -> int:
    if not (args.refresh or args.in_specs):
        answers = lookup(kb, scope, question, args.limit)
        if answers:
            print(render(answers))
            print("\n---\nFrom the knowledge base. Wrong or too thin? Ask with more specific words, or add "
                  "--refresh to have a local model read the closest docs.")
            return EXIT_ANSWERED
    if args.no_learn:
        print("The knowledge base holds no answer to that.")
        _print_leads(leads_for(kb, question))
        return EXIT_NO_ANSWER
    pool = LocalLlmPool(replace(local_llm_settings(args), allow_load=False),
                        report=lambda line: LOG.info("%s", line))
    try:
        gathered = gather(kb, scope, pool, question, args.in_specs)
    except LocalLlmUnavailable as exc:
        print(f"The knowledge base holds no answer to that, and no local model could add one: {exc}")
        _print_leads(leads_for(kb, question))
        return EXIT_NO_ANSWER
    return _show_gathered(gathered)


def main(argv: list[str]) -> int:
    # Docs carry dashes and ellipses; a Windows console codepage must not turn an answer into '?'.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    parser = _parser()
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()
    actions = [flag for flag in ("status", "rebuild", "prune") if getattr(args, flag)]
    if len(actions) + bool(question) != 1:
        parser.error("pass a question, or exactly one of --status, --rebuild, --prune")
    if args.limit < 1:
        parser.error(f"--limit must be at least 1; got {args.limit}.")
    scope = ReadScope(get_datrix_root())
    try:
        kb = KnowledgeBase(knowledge_db_path())
        if args.rebuild:
            kb.clear()
        if args.prune:
            for removed in prune_stale(scope):
                print(f"deleted {removed}")
        sync_curated(kb, scope)
        sync_learned(kb, scope)
        if args.rebuild or args.prune:
            print(_status(kb, scope))
            return EXIT_ANSWERED
        if args.status:
            print(_status(kb, scope))
            return EXIT_ANSWERED
        return _answer(args, kb, scope, question)
    except (KnowledgeError, ReadScopeError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
