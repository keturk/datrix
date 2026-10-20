#!/usr/bin/env python3
"""Ask the knowledge base what you need to know.

The module behind ``dev/ineedtoknow.ps1`` (and its ``.sh`` twin), one request per run:

    a question (--question, repeatable; the words are joined)
                       answer from the knowledge base; if it holds no answer, have a local model
                       read the closest docs and keep a grounded answer
    --status           what the knowledge base holds
    --rebuild          drop the database and rebuild it from the docs and learned files
    --prune            delete learned files whose sources changed on this machine

Exit codes: 0 answered; 1 the request could not be carried out (the message says why); 2 no answer
(not in the knowledge base, and no local model could add one).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from datrix_scripts.knowledge.gather import Gathered, gather, leads_for
from datrix_scripts.knowledge.learned_files import (
    LEARNED_DIR_RELATIVE,
    learned_dir,
    prune_stale,
    read_entries,
    stale_sources,
    sync_learned,
)
from datrix_scripts.knowledge.lookup import DEFAULT_ANSWERS, lookup, render
from datrix_scripts.knowledge.seed import sync_curated
from datrix_scripts.knowledge.store import (
    KIND_CURATED,
    KIND_LEARNED,
    KnowledgeBase,
    KnowledgeError,
    knowledge_db_path,
)
from datrix_scripts.gate_harness import install_sigint_handler
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.local_reading import ReadScope, ReadScopeError
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.ineedtoknow"
WRAPPER: Final = "ineedtoknow"

EXIT_ANSWERED = 0
EXIT_USAGE = 1
EXIT_NO_ANSWER = 2

# A gather reads a few chunks, so a short answer should take seconds; a model that is not already in
# memory is reported as unavailable rather than waited for (local-llm.ps1 -Status shows what is resident).
GATHER_TIMEOUT_SECONDS: Final = 120
#: -Limit's "not given" (and any value below 1): the lookup's own number of answers.
LIMIT_NOT_GIVEN: Final = 0
#: The maintenance requests, in the order the usage message names them: (wrapper parameter, option dest).
MAINTENANCE: Final = (("-Status", "status"), ("-Rebuild", "rebuild"), ("-Prune", "prune"))

LOG = logging.getLogger("ineedtoknow")


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/ineedtoknow.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("positional_question", nargs="*", metavar="WORD", help="The question (as --question).")
    parser.add_argument("--question", action="append", default=[],
                        help="What you need to know, in your own words (repeatable; the words are joined).")
    parser.add_argument("--in", dest="in_specs", action="append", default=[], metavar="PATH_OR_GLOB",
                        help="Also read these files (workspace-relative path or glob) to answer; implies a "
                             "local-model read instead of a lookup. Repeatable.")
    parser.add_argument("--refresh", action="store_true",
                        help="Skip the lookup and have a local model read the closest docs again.")
    parser.add_argument("--no-learn", action="store_true",
                        help="Look up only; never contact a local model.")
    parser.add_argument("--limit", type=int, default=LIMIT_NOT_GIVEN,
                        help=f"Answers to show (default: {DEFAULT_ANSWERS}).")
    parser.add_argument("--status", action="store_true", help="Show what the knowledge base holds.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop the database and rebuild it from the docs and the committed learned files.")
    parser.add_argument("--prune", action="store_true",
                        help="Delete learned files whose sources changed on this machine.")
    add_wrapper_llm_arguments(parser, timeout_seconds=GATHER_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: exactly one request is required, and the question's "
                             "words are joined.")
    parser.set_defaults(debug=False)
    return parser


def question_text(args: argparse.Namespace) -> str:
    """The question *args* asks: its words joined with spaces, ends trimmed."""
    return " ".join([*args.positional_question, *args.question]).strip()


def answer_limit(args: argparse.Namespace) -> int:
    """The number of answers to show: --limit when at least 1, else the lookup's default."""
    return int(args.limit) if args.limit >= 1 else DEFAULT_ANSWERS


def refusal(args: argparse.Namespace) -> str:
    """Why *args* cannot run (no request, or several), or ``""``."""
    chosen = (["a question"] if question_text(args) else []) + [flag for flag, dest in MAINTENANCE if getattr(args, dest)]
    if len(chosen) == 1:
        return ""
    given = ", ".join(chosen) or "none"
    return (f"Pass exactly one of: a question, -Status, -Rebuild or -Prune (given: {given}). "
            "Get-Help .\\ineedtoknow.ps1 -Full lists them.")


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
        answers = lookup(kb, scope, question, answer_limit(args))
        if answers:
            print(render(answers))
            print("\n---\nFrom the knowledge base. Wrong or too thin? Ask with more specific words, or add "
                  "--refresh to have a local model read the closest docs.")
            return EXIT_ANSWERED
    if args.no_learn:
        print("The knowledge base holds no answer to that.")
        _print_leads(leads_for(kb, question))
        return EXIT_NO_ANSWER
    pool = LocalLlmPool(replace(wrapper_llm_settings(args), allow_load=False),
                        report=lambda line: LOG.info("%s", line))
    try:
        gathered = gather(kb, scope, pool, question, args.in_specs)
    except LocalLlmUnavailable as exc:
        print(f"The knowledge base holds no answer to that, and no local model could add one: {exc}")
        _print_leads(leads_for(kb, question))
        return EXIT_NO_ANSWER
    return _show_gathered(gathered)


def _check_exactly_one_request_is_required() -> None:
    parser = build_parser()
    assert refusal(parser.parse_args([])) == (
        "Pass exactly one of: a question, -Status, -Rebuild or -Prune (given: none). "
        "Get-Help .\\ineedtoknow.ps1 -Full lists them."
    ), refusal(parser.parse_args([]))
    assert "(given: a question, -Status)" in refusal(parser.parse_args(["--question=why", "--status"]))
    assert "(given: none)" in refusal(parser.parse_args(["--question=  "])), "a blank question is no request"
    assert refusal(parser.parse_args(["--prune"])) == ""


def _check_question_words_are_joined() -> None:
    parser = build_parser()
    args = parser.parse_args(["which", "--question=package owns", "--question", "routes "])
    assert question_text(args) == "which package owns routes", question_text(args)
    assert answer_limit(parser.parse_args([])) == DEFAULT_ANSWERS
    assert answer_limit(parser.parse_args(["--limit=5"])) == 5


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_exactly_one_request_is_required, _check_question_words_are_joined]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    problem = refusal(args)
    if problem:
        print(problem)
        return EXIT_USAGE
    # Progress lines (which model server answers) go to standard error, bare.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s", force=True)
    return _request(args, question_text(args))


def _request(args: argparse.Namespace, question: str) -> int:
    """Bring the knowledge base up to date, then carry out the one request *args* makes."""
    scope = ReadScope(WORKSPACE_DIR)
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
    sys.exit(main())
