"""The customer-domain isolation gate: no registered customer term appears in a Datrix framework repo.

Scans every PUBLISHABLE file of every framework repo in the workspace -- tracked files plus
untracked-but-not-ignored ones, because a new file carrying a term is untracked right up until the
``git add`` that commits it -- against the hashed customer-term corpus at
``scripts/config/customer-term-hashes.json``. See ``datrix_scripts.customer_domain_isolation`` for why
the corpus is hashed and what shapes of occurrence it matches. One hit fails the gate.

``--add-term`` registers one term by its SHA-256 digest and exits; the term itself is never written --
not to the corpus, not to the hint stored beside its digest, and not to the ``--dbg`` command echo, which
gate mode copies into a log file on disk.

This module is what ``gates/repo-hygiene/customer-domain-isolation-gate.ps1`` (and its ``.sh`` twin)
runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] customer-domain-isolation PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes:
  0 = no violations (or the corpus is registered-empty, reported as NOT ENFORCED; or a term registered)
  1 = at least one violation, or the self-test failed
  2 = usage error, the corpus is missing/malformed, git cannot list a repo's files, or a file to scan
      cannot be read (the scan stops rather than skip it)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.customer_domain_isolation import (
    DEFAULT_MIN_TOKEN_LENGTH,
    REDACTION,
    SELF_TEST_TERM,
    TOKEN_PATTERN,
    CorpusError,
    TermCorpus,
    Violation,
    corpus_path,
    hash_term,
    load_term_corpus,
    pending_files,
    publishable_files,
    scan_paths,
    self_test,
)
from datrix_scripts.framework_repos import select_framework_repos
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "customer-domain-isolation"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.customer_domain_isolation_gate"
WRAPPER: Final = "customer-domain-isolation-gate"
DATRIX_ROOT: Final = SHOWCASE_DIR
ADD_TERM_FLAG: Final = "--add-term"
DEFAULT_HINT: Final = "customer project"
_CORPUS_ALGORITHM: Final = "sha256"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/customer-domain-isolation-gate.ps1``: one per wrapper
    parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Fail if a registered customer term appears in any publishable file of a framework repo.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable). Default: every framework repo.",
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Scan only what a 'git add -A' would stage, instead of every publishable file.",
    )
    parser.add_argument(
        ADD_TERM_FLAG,
        metavar="TERM",
        default=None,
        help="Register a customer term by SHA-256 digest and exit. The term itself is never stored.",
    )
    parser.add_argument(
        "--hint",
        default=DEFAULT_HINT,
        help="Non-identifying note stored alongside a registered digest (never the term itself).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the scanner self-test (planted terms found, clean text not) and the wrapper seam check.",
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Print the command (term redacted) first."
    )
    return parser


def redacted_argv(argv: Sequence[str]) -> list[str]:
    """*argv* with the value of every ``--add-term`` (``--add-term=TERM`` or ``--add-term TERM``) masked."""
    redacted: list[str] = []
    value_follows = False
    for argument in argv:
        if value_follows:
            redacted.append(REDACTION)
        elif argument.startswith(f"{ADD_TERM_FLAG}="):
            redacted.append(f"{ADD_TERM_FLAG}={REDACTION}")
        else:
            redacted.append(argument)
        value_follows = not value_follows and argument == ADD_TERM_FLAG
    return redacted


def _print_redacted_command() -> None:
    """The ``-Dbg`` echo of ``gate_harness.print_command``, with the registered term masked: gate mode
    writes every printed line to a log file on disk."""
    print(f"Python executable: {sys.executable}")
    print(f"Arguments: {' '.join(redacted_argv(sys.argv))}", flush=True)


def _registrable_corpus(path: Path) -> tuple[dict[str, object], list[object], TermCorpus]:
    """The corpus document at *path* (its raw form, its ``terms`` list and its validated form), or a new
    empty sha256 corpus when no file exists yet. Raises ``CorpusError`` when the file is malformed."""
    if not path.is_file():
        terms: list[object] = []
        document: dict[str, object] = {
            "algorithm": _CORPUS_ALGORITHM,
            "min_token_length": DEFAULT_MIN_TOKEN_LENGTH,
            "terms": terms,
        }
        return document, terms, TermCorpus(hashes=frozenset(), min_token_length=DEFAULT_MIN_TOKEN_LENGTH)
    corpus = load_term_corpus(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    existing = document["terms"]
    if not isinstance(existing, list):
        raise CorpusError(f"Customer-term corpus at {path} has no 'terms' list.")
    return document, existing, corpus


def add_term(path: Path, term: str, hint: str) -> int:
    """Register one term by digest in the corpus at *path*. The plaintext term is never written."""
    candidate = term.strip()
    if not TOKEN_PATTERN.fullmatch(candidate):
        print(
            "ERROR: --add-term takes exactly one token: a letter followed by letters or digits (e.g. "
            "acmecorp). The scanner matches only such tokens and their camelCase parts, so a term that is "
            "empty or holds a space, hyphen or other separator could never be matched. Register each "
            "token separately.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if candidate.lower() in hint.lower():
        print(
            "ERROR: --hint contains the term itself, and the hint is stored in clear text. Expected a "
            f"non-identifying note such as '{DEFAULT_HINT}'.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        document, terms, corpus = _registrable_corpus(path)
    except CorpusError as exc:
        print(f"CUSTOMER-DOMAIN ISOLATION GATE CANNOT REGISTER: {exc}", file=sys.stderr)
        return EXIT_USAGE
    digest = hash_term(candidate)
    if digest in corpus.hashes:
        print(f"Term already registered (digest {digest[:12]}...); corpus unchanged.")
        return EXIT_PASS
    if len(candidate) < corpus.min_token_length:
        print(
            f"ERROR: term is shorter than the corpus min_token_length ({corpus.min_token_length}); it could "
            "never be matched.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    terms.append({"hash": digest, "hint": hint})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Registered term digest {digest[:12]}... (hint: {hint}) in {path}")
    return EXIT_PASS


def report(violations: list[Violation]) -> None:
    """Print every violation, grouped by repo, with the term redacted."""
    by_repo: dict[str, list[Violation]] = {}
    for violation in violations:
        by_repo.setdefault(violation.repo, []).append(violation)
    for repo in sorted(by_repo):
        print(f"\n  {repo}:")
        for violation in by_repo[repo]:
            print(f"    {violation.path}:{violation.line}: {violation.excerpt}")


def resolve_repos(workspace_root: Path, wanted: list[str] | None) -> list[Path] | None:
    """Return the repos to scan, or None when a requested name does not exist."""
    try:
        return select_framework_repos(workspace_root, wanted)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


def _scan(args: argparse.Namespace, path: Path) -> int:
    """Scan the requested repos against the corpus at *path*; the gate's exit code."""
    try:
        corpus = load_term_corpus(path)
    except CorpusError as exc:
        print(f"CUSTOMER-DOMAIN ISOLATION GATE CANNOT RUN: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if corpus.is_empty:
        print(
            f"CUSTOMER-DOMAIN ISOLATION NOT ENFORCED: zero terms registered in {path}. "
            f"Register one with -AddTerm before relying on this gate."
        )
        return EXIT_PASS

    repos = resolve_repos(DATRIX_ROOT.parent, args.repo)
    if repos is None:
        return EXIT_USAGE

    scope = "pending changes" if args.pending_only else "publishable files"
    print(f"Scanning {scope} in {len(repos)} repo(s) against {len(corpus.hashes)} registered term(s)")

    violations: list[Violation] = []
    for repo in repos:
        try:
            rel_paths = pending_files(repo) if args.pending_only else publishable_files(repo)
            found = scan_paths(repo, rel_paths, corpus)
        except CorpusError as exc:
            print(f"CUSTOMER-DOMAIN ISOLATION GATE CANNOT RUN in {repo.name}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        print(f"  {repo.name}: {len(rel_paths)} file(s) scanned, {len(found)} violation(s)")
        violations.extend(found)

    if violations:
        print(
            f"\nCUSTOMER-DOMAIN ISOLATION GATE FAILED: {len(violations)} occurrence(s) of a "
            f"registered customer term. Customer domain language must not exist in a "
            f"framework repo -- remove it at the source (the matched token is redacted below; "
            f"open the file:line to see it)."
        )
        report(violations)
        return EXIT_VIOLATION

    print("\nCUSTOMER-DOMAIN ISOLATION GATE PASSED: no registered customer term found.")
    return EXIT_PASS


def _run(args: argparse.Namespace) -> int:
    """Run the gate: register a term, or self-test then scan (exit codes in the module docstring)."""
    if args.debug:
        _print_redacted_command()
    path = corpus_path(DATRIX_ROOT)
    if args.add_term is not None:
        return add_term(path, args.add_term, args.hint)

    failures = self_test()
    if failures:
        print("CUSTOMER-DOMAIN ISOLATION GATE CANNOT BE TRUSTED: scanner self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return EXIT_VIOLATION
    if args.self_test:
        print("CUSTOMER-DOMAIN ISOLATION SELF-TEST PASSED: the scanner finds every planted term.")
        return wrappers.run_self_test(
            [_check_add_term_stores_only_a_digest, _check_add_term_refuses_what_could_never_match_or_leaks,
             _check_dbg_echo_redacts_the_term],
            wrapper=WRAPPER,
            module=MODULE,
            parser=build_parser(),
            folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    return _scan(args, path)


def _quiet_add_term(path: Path, term: str, hint: str) -> int:
    """``add_term`` with its console lines swallowed (a self-test case refused or accepted on purpose)."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return add_term(path, term, hint)


def _check_add_term_stores_only_a_digest() -> None:
    with tempfile.TemporaryDirectory(prefix="customer-term-") as tmp:
        path = Path(tmp, "config", "customer-term-hashes.json")
        assert _quiet_add_term(path, f"  {SELF_TEST_TERM.capitalize()} ", DEFAULT_HINT) == EXIT_PASS, (
            "add_term did not register a valid single-token term into a new corpus"
        )
        written = path.read_text(encoding="utf-8")
        assert SELF_TEST_TERM not in written.lower(), "the corpus holds the registered term in clear text"
        assert hash_term(SELF_TEST_TERM) in load_term_corpus(path).hashes, (
            "the corpus add_term wrote does not load with the term's digest"
        )
        assert _quiet_add_term(path, SELF_TEST_TERM, DEFAULT_HINT) == EXIT_PASS, "re-registering a term failed"
        assert path.read_text(encoding="utf-8") == written, "re-registering a term changed the corpus"


def _check_add_term_refuses_what_could_never_match_or_leaks() -> None:
    with tempfile.TemporaryDirectory(prefix="customer-term-") as tmp:
        fresh = Path(tmp, "fresh.json")
        refused = ("", "   ", "two words", f"{SELF_TEST_TERM}-corp", "9lives", "abc")
        for term in refused:
            assert _quiet_add_term(fresh, term, DEFAULT_HINT) == EXIT_USAGE, (
                f"add_term accepted {term!r}, a term the scanner could never match"
            )
        assert _quiet_add_term(fresh, SELF_TEST_TERM, f"the {SELF_TEST_TERM.upper()} project") == EXIT_USAGE, (
            "add_term accepted a hint holding the term, which would store the term in clear text"
        )
        assert not fresh.exists(), "a refused registration wrote a corpus file"

        malformed = Path(tmp, "malformed.json")
        malformed_text = json.dumps({"algorithm": "md5", "min_token_length": 5, "terms": []})
        malformed.write_text(malformed_text, encoding="utf-8")
        assert _quiet_add_term(malformed, SELF_TEST_TERM, DEFAULT_HINT) == EXIT_USAGE, (
            "add_term registered into a corpus load_term_corpus refuses"
        )
        assert malformed.read_text(encoding="utf-8") == malformed_text, "add_term rewrote a malformed corpus"


def _check_dbg_echo_redacts_the_term() -> None:
    cases: tuple[tuple[list[str], list[str]], ...] = (
        (
            [f"{ADD_TERM_FLAG}={SELF_TEST_TERM}", "--hint=x", "--dbg"],
            [f"{ADD_TERM_FLAG}={REDACTION}", "--hint=x", "--dbg"],
        ),
        ([ADD_TERM_FLAG, SELF_TEST_TERM, "--dbg"], [ADD_TERM_FLAG, REDACTION, "--dbg"]),
        (["--repo=datrix", "--dbg"], ["--repo=datrix", "--dbg"]),
    )
    for argv, expected in cases:
        got = redacted_argv(argv)
        assert got == expected, f"redacted_argv({argv!r}) is {got!r}, expected {expected!r}"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
