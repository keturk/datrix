#!/usr/bin/env python
"""Repo-level gate: no registered customer term appears in a Datrix framework repo.

Scans every PUBLISHABLE file of every framework repo in the workspace -- tracked
files plus untracked-but-not-ignored ones, because a new file carrying a term is
untracked right up until the `git add` that commits it -- against the hashed
customer-term corpus at
``scripts/config/customer-term-hashes.json``. See
``scripts/library/dev/customer_domain_isolation.py`` for why the corpus is
hashed and what shapes of occurrence it matches.

Repo-level validation script, per the datrix showcase boundary: the showcase
repo hosts no pytest suite, so cross-repo checks live here and are invoked by
the runner.

Exit codes:
  0 = no violations (or the corpus is registered-empty, reported as NOT ENFORCED)
  1 = at least one violation, or the scanner self-test failed
  2 = usage error, or the corpus is missing/malformed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATRIX_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(DATRIX_ROOT / "scripts" / "library"))

from dev.customer_domain_isolation import (  # noqa: E402
    CorpusError,
    Violation,
    corpus_path,
    framework_repos,
    hash_term,
    load_term_corpus,
    pending_files,
    publishable_files,
    scan_paths,
    self_test,
)


def add_term(path: Path, term: str, hint: str) -> int:
    """Register one term by digest. The plaintext term is never written."""
    if not term.strip():
        print("ERROR: --add-term requires a non-empty term.", file=sys.stderr)
        return 2
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {
            "algorithm": "sha256",
            "min_token_length": 5,
            "terms": [],
        }
    digest = hash_term(term)
    existing = {entry.get("hash") for entry in data.get("terms", [])}
    if digest in existing:
        print(f"Term already registered (digest {digest[:12]}...); corpus unchanged.")
        return 0
    if len(term.strip()) < int(data.get("min_token_length", 5)):
        print(
            f"ERROR: term is shorter than the corpus min_token_length "
            f"({data.get('min_token_length', 5)}); it could never be matched.",
            file=sys.stderr,
        )
        return 2
    data.setdefault("terms", []).append({"hash": digest, "hint": hint})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Registered term digest {digest[:12]}... (hint: {hint}) in {path}")
    return 0


def report(violations: list[Violation]) -> None:
    """Print every violation, grouped by repo, with the term redacted."""
    by_repo: dict[str, list[Violation]] = {}
    for violation in violations:
        by_repo.setdefault(violation.repo, []).append(violation)
    for repo in sorted(by_repo):
        print(f"\n  {repo}:")
        for violation in by_repo[repo]:
            print(f"    {violation.path}:{violation.line}: {violation.excerpt}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        "--add-term",
        metavar="TERM",
        default=None,
        help="Register a customer term by SHA-256 digest and exit. The term itself is never stored.",
    )
    parser.add_argument(
        "--hint",
        default="customer project",
        help="Non-identifying note stored alongside a registered digest.",
    )
    return parser.parse_args(argv)


def resolve_repos(workspace_root: Path, wanted: list[str] | None) -> list[Path] | None:
    """Return the repos to scan, or None when a requested name does not exist."""
    repos = framework_repos(workspace_root)
    if wanted is None:
        return repos
    selected = [repo for repo in repos if repo.name in set(wanted)]
    missing = sorted(set(wanted) - {repo.name for repo in selected})
    if missing:
        print(
            f"ERROR: no framework repo named {', '.join(missing)} under {workspace_root}. "
            f"Known: {', '.join(repo.name for repo in repos)}",
            file=sys.stderr,
        )
        return None
    return selected


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    workspace_root = DATRIX_ROOT.parent
    path = corpus_path(DATRIX_ROOT)

    if args.add_term is not None:
        return add_term(path, args.add_term, args.hint)

    failures = self_test()
    if failures:
        print("CUSTOMER-DOMAIN ISOLATION GATE CANNOT BE TRUSTED: scanner self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return 1

    try:
        corpus = load_term_corpus(path)
    except CorpusError as exc:
        print(f"CUSTOMER-DOMAIN ISOLATION GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    if corpus.is_empty:
        print(
            f"CUSTOMER-DOMAIN ISOLATION NOT ENFORCED: zero terms registered in {path}. "
            f"Register one with -AddTerm before relying on this gate."
        )
        return 0

    repos = resolve_repos(workspace_root, args.repo)
    if repos is None:
        return 2

    scope = "pending changes" if args.pending_only else "publishable files"
    print(f"Scanning {scope} in {len(repos)} repo(s) against {len(corpus.hashes)} registered term(s)")

    violations: list[Violation] = []
    for repo in repos:
        rel_paths = pending_files(repo) if args.pending_only else publishable_files(repo)
        found = scan_paths(repo, rel_paths, corpus)
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
        return 1

    print("\nCUSTOMER-DOMAIN ISOLATION GATE PASSED: no registered customer term found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
