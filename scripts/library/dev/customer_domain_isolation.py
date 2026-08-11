#!/usr/bin/env python
"""Customer-domain isolation for the Datrix framework repos.

WHY THIS EXISTS
---------------
The framework repos (``datrix``, ``datrix-cli``, ``datrix-codegen-*``,
``datrix-common``, ``datrix-extensions``, ``datrix-language``) are shared,
publishable artifacts. Customer and project domain language -- a customer name,
their service names, their cloud resource names, paths into their checkout --
must never appear in any of them. That rule was prose only, and nothing checked
it: customer cloud-resource names and checkout paths reached a committed
settings file through Claude Code permission entries, and a customer deployment
target reached a hook's docstring example.

WHY THE DENYLIST IS HASHED
--------------------------
A plaintext denylist naming the customer would BE the violation it polices --
the banned term would sit, in the clear, in the very repo it is banned from.
The corpus therefore stores only SHA-256 digests of lowercased terms. Scanning
hashes each candidate token and compares digests, so no term is ever present in
the repo, yet the check travels with the checkout and enforces on every machine
(an out-of-repo term file would silently not exist on the second machine, which
is exactly the failure mode a guard must not have).

WHAT IT MATCHES
---------------
Identifier-shaped occurrences. Content is split into alphanumeric tokens, each
token is additionally camel-split, and every piece of at least
``min_token_length`` characters is lowercased and hashed. That covers
hyphenated cloud-resource names (``<term>-system-kv-dev``), paths
(``//d/g/<Term>/generated/**``), snake/kebab identifiers, and camelCase
(``<term>Backend``).

It does NOT match a term glued to another word with neither a separator nor a
case boundary (``<term>dev``): a hash denylist cannot do substring search
without the plaintext it deliberately does not hold. If such a variant ever
appears, register it as its own term.

REDACTION
---------
Reported excerpts have the matched token replaced with ``<customer-term>``.
The file and line are what a fix needs; echoing the term back invites an agent
to copy it into a summary, a task file, or a commit message -- re-committing
the leak while reporting it.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

# A token starts with a letter so pure numbers and hex blobs never enter the
# hash loop; digits inside a name (``acme2``) are kept.
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*")

# camelCase / PascalCase splitter: ``acmecorpBackend`` -> acmecorp + Backend,
# ``ACMEStore`` -> ACME + Store. Emitted IN ADDITION TO the whole token, so a
# PascalCase term (``AcmeCorp``) still matches on the whole-token pass.
CAMEL_SPLIT_PATTERN = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")

# Files above this size are generated blobs or binaries, never hand-written
# prose; scanning them costs more than the class of defect they could hold.
MAX_SCAN_BYTES = 2_000_000

DEFAULT_MIN_TOKEN_LENGTH = 5

REDACTION = "<customer-term>"
MAX_EXCERPT_CHARS = 160


class CorpusError(RuntimeError):
    """The term corpus is missing or malformed."""


@dataclass(frozen=True)
class TermCorpus:
    """Registered customer terms, as SHA-256 digests of their lowercased form."""

    hashes: frozenset[str]
    min_token_length: int

    @property
    def is_empty(self) -> bool:
        return not self.hashes


@dataclass(frozen=True)
class Violation:
    """One registered term found at one line of one file."""

    repo: str
    path: str
    line: int
    excerpt: str

    def render(self) -> str:
        return f"{self.repo}/{self.path}:{self.line}: {self.excerpt}"


def hash_term(term: str) -> str:
    """Digest one term the same way scanning digests a candidate token."""
    return hashlib.sha256(term.strip().lower().encode("utf-8")).hexdigest()


def corpus_path(workspace_datrix_root: Path) -> Path:
    """Canonical location of the hashed denylist inside the showcase repo."""
    return workspace_datrix_root / "scripts" / "config" / "customer-term-hashes.json"


def load_term_corpus(path: Path) -> TermCorpus:
    """Load the hashed denylist.

    A missing or malformed corpus is an error, not an empty corpus: silently
    scanning against zero terms would make every caller vacuously green. An
    explicitly empty ``terms`` list is legitimate (a checkout with no customer
    projects) and callers report it as NOT ENFORCED rather than as a pass.
    """
    if not path.is_file():
        raise CorpusError(
            f"Customer-term corpus not found at {path}. Expected a JSON file with "
            f'{{"algorithm": "sha256", "min_token_length": <int>, "terms": [...]}}. '
            f"Create it with: customer-domain-isolation-gate.ps1 -AddTerm <term>"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"Customer-term corpus at {path} is unreadable: {exc}") from exc

    algorithm = data.get("algorithm")
    if algorithm != "sha256":
        raise CorpusError(
            f"Customer-term corpus at {path} declares algorithm '{algorithm}'. "
            f"Only 'sha256' is supported; re-register the terms with -AddTerm."
        )

    raw_terms = data.get("terms")
    if not isinstance(raw_terms, list):
        raise CorpusError(f"Customer-term corpus at {path} has no 'terms' list.")

    hashes: set[str] = set()
    for entry in raw_terms:
        if not isinstance(entry, dict) or not isinstance(entry.get("hash"), str):
            raise CorpusError(
                f"Customer-term corpus at {path} has a term entry without a string "
                f"'hash' field: {entry!r}. Each entry is {{'hash': ..., 'hint': ...}}."
            )
        hashes.add(entry["hash"].strip().lower())

    min_length = data.get("min_token_length", DEFAULT_MIN_TOKEN_LENGTH)
    if not isinstance(min_length, int) or min_length < 3:
        raise CorpusError(
            f"Customer-term corpus at {path} has min_token_length={min_length!r}. "
            f"Expected an integer >= 3 (short tokens collide with ordinary words)."
        )
    return TermCorpus(hashes=frozenset(hashes), min_token_length=min_length)


def iter_candidate_tokens(text: str, min_length: int) -> Iterator[str]:
    """Yield every token of `text` long enough to be a customer term.

    Both the whole alphanumeric token and its camel-split parts are yielded, so
    ``AcmeCorp`` matches on the whole token while ``acmecorpBackend`` matches on
    a part. Duplicates are yielded; callers memoize.
    """
    for match in TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if len(token) >= min_length:
            yield token
        for part in CAMEL_SPLIT_PATTERN.findall(token):
            if len(part) >= min_length and part != token:
                yield part


def redact_excerpt(line: str, token: str) -> str:
    """Return `line` with `token` masked and the whole thing length-capped."""
    masked = re.sub(re.escape(token), REDACTION, line, flags=re.IGNORECASE).strip()
    if len(masked) <= MAX_EXCERPT_CHARS:
        return masked
    return masked[:MAX_EXCERPT_CHARS] + " [...]"


def scan_text(text: str, corpus: TermCorpus, seen: dict[str, bool] | None = None) -> list[tuple[int, str]]:
    """Return `(line_number, redacted_excerpt)` for every line carrying a term."""
    if corpus.is_empty:
        return []
    memo: dict[str, bool] = {} if seen is None else seen
    hits: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for token in iter_candidate_tokens(line, corpus.min_token_length):
            lowered = token.lower()
            is_term = memo.get(lowered)
            if is_term is None:
                is_term = hash_term(lowered) in corpus.hashes
                memo[lowered] = is_term
            if is_term:
                hits.append((line_number, redact_excerpt(line, token)))
                break
    return hits


def read_scannable_text(path: Path) -> str | None:
    """Return a file's text, or None when it is binary, huge, or unreadable."""
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def run_git(repo_path: Path, args: list[str]) -> str:
    """Run a read-only git command in `repo_path` and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise CorpusError(
            f"git {' '.join(args)} failed in {repo_path.name} "
            f"({result.returncode}): {(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def publishable_files(repo_path: Path) -> list[str]:
    """Every path in `repo_path` that a commit could publish.

    Tracked files UNION untracked-but-not-ignored files. Scanning only tracked
    files leaves a real hole: a new file carrying a customer term is untracked
    right up until the `git add` that commits it, so a tracked-only gate reports
    green on precisely the file about to leak (this was observed -- this
    module's own first draft carried a term and a tracked-only scan missed it).
    Ignored paths are excluded: they are never published.
    """
    listing = run_git(repo_path, ["ls-files", "--cached", "--others", "--exclude-standard"])
    seen: list[str] = []
    for line in listing.splitlines():
        path = line.strip()
        if path and path not in seen:
            seen.append(path)
    return seen


def pending_files(repo_path: Path) -> list[str]:
    """Every path a `git add -A` in `repo_path` would stage.

    Modified, added, renamed and untracked-but-not-ignored paths; deletions are
    excluded because there is no content left to scan. `-uall` lists untracked
    files individually rather than collapsing them into a directory entry, so a
    new folder's files are each scanned.
    """
    paths: list[str] = []
    for raw in run_git(repo_path, ["status", "--porcelain", "-uall"]).splitlines():
        if len(raw) < 4:
            continue
        status, path = raw[:2], raw[3:].strip()
        if "D" in status and "?" not in status:
            continue
        if " -> " in path:  # rename: only the destination still has content
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if path and path not in paths:
            paths.append(path)
    return paths


def scan_paths(repo_path: Path, rel_paths: list[str], corpus: TermCorpus) -> list[Violation]:
    """Scan the given repo-relative paths and return every violation found."""
    if corpus.is_empty:
        return []
    memo: dict[str, bool] = {}
    violations: list[Violation] = []
    for rel_path in rel_paths:
        text = read_scannable_text(repo_path / rel_path)
        if text is None:
            continue
        for line_number, excerpt in scan_text(text, corpus, memo):
            violations.append(
                Violation(repo=repo_path.name, path=rel_path, line=line_number, excerpt=excerpt)
            )
    return violations


def framework_repos(workspace_root: Path) -> list[Path]:
    """Discover the framework git repos in the workspace.

    Discovered, not hardcoded: a newly cloned ``datrix-codegen-<lang>`` must be
    policed the day it appears, and Datrix is a multi-language, multi-platform
    generator whose repo set is open-ended. The showcase repo anchors the list.
    """
    repos: list[Path] = []
    showcase = workspace_root / "datrix"
    if (showcase / ".git").exists():
        repos.append(showcase)
    for child in sorted(workspace_root.iterdir()):
        if child.name.startswith("datrix-") and (child / ".git").exists():
            repos.append(child)
    return repos


SELF_TEST_TERM = "zephyrantha"

PLANTED_RELPATH = "config/settings.json"


def _self_test_git_listing() -> list[str]:
    """Prove the git-listing legs actually reach a new file, on a real repo.

    String matching being correct is worth nothing if the file never reaches the
    scanner. A real ``git init`` in a temp directory, a planted UNTRACKED file
    (the state every new file is in right up until the ``git add`` that commits
    it), and a planted IGNORED file (which must be skipped, since it is never
    published) exercise exactly what the callers call.
    """
    failures: list[str] = []
    corpus = TermCorpus(hashes=frozenset({hash_term(SELF_TEST_TERM)}), min_token_length=5)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        init = subprocess.run(
            ["git", "init", "-q", str(repo)], capture_output=True, text=True, check=False
        )
        if init.returncode != 0:
            return [f"self-test: could not create a temp git repo: {init.stderr.strip()}"]

        planted = repo / PLANTED_RELPATH
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(f'"vault": "{SELF_TEST_TERM}-system-kv-dev"\n', encoding="utf-8")

        (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        ignored = repo / "ignored" / "leak.txt"
        ignored.parent.mkdir(parents=True, exist_ok=True)
        ignored.write_text(f"{SELF_TEST_TERM}-development-rg\n", encoding="utf-8")

        listers: tuple[tuple[str, Callable[[Path], list[str]]], ...] = (
            ("pending_files", pending_files),
            ("publishable_files", publishable_files),
        )
        for label, lister in listers:
            paths = lister(repo)
            if PLANTED_RELPATH not in paths:
                failures.append(f"self-test: {label} did not list a new untracked file")
            found = scan_paths(repo, paths, corpus)
            if not any(violation.path == PLANTED_RELPATH for violation in found):
                failures.append(
                    f"self-test: {label} + scan missed a planted term in an untracked file"
                )
            if any(violation.path.startswith("ignored/") for violation in found):
                failures.append(f"self-test: {label} scanned a git-ignored path")
    return failures


def self_test() -> list[str]:
    """Prove the scanner is not vacuous. Returns a list of failure descriptions.

    Runs before every real scan: a detector that silently stopped detecting
    reports a clean tree, which is indistinguishable from a clean tree.
    """
    failures: list[str] = []
    corpus = TermCorpus(hashes=frozenset({hash_term(SELF_TEST_TERM)}), min_token_length=5)

    positives = {
        "hyphenated resource name": f"vault: {SELF_TEST_TERM}-system-kv-dev",
        "path segment": f"Read(//d/g/{SELF_TEST_TERM.capitalize()}/generated/**)",
        "camelCase identifier": f"const client = new {SELF_TEST_TERM}Backend();",
        "upper case": f"RESOURCE_GROUP = {SELF_TEST_TERM.upper()}_RG",
    }
    for label, sample in positives.items():
        if not scan_text(sample, corpus):
            failures.append(f"self-test: {label} was NOT detected")

    negatives = {
        "unrelated prose": "The order service publishes an OrderPlaced event.",
        "similar prefix": "zephyr and anthanasia are unrelated tokens",
    }
    for label, sample in negatives.items():
        if scan_text(sample, corpus):
            failures.append(f"self-test: {label} was falsely flagged")

    redacted = scan_text(f"vault: {SELF_TEST_TERM}-kv-dev", corpus)
    if redacted and SELF_TEST_TERM in redacted[0][1].lower():
        failures.append("self-test: the reported excerpt leaked the matched term")

    empty = TermCorpus(hashes=frozenset(), min_token_length=5)
    if scan_text(f"{SELF_TEST_TERM}-system", empty):
        failures.append("self-test: an empty corpus reported a match")

    failures.extend(_self_test_git_listing())
    return failures
