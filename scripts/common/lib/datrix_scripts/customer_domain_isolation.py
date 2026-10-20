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

DEFAULT_MIN_TOKEN_LENGTH = 5

#: ``git status --porcelain`` entries: two status letters, a space, then the path.
PORCELAIN_PATH_OFFSET = 3
RENAMED = "R"
COPIED = "C"
DELETED = "D"
UNTRACKED = "?"

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
    if not isinstance(data, dict):
        raise CorpusError(
            f"Customer-term corpus at {path} is a JSON {type(data).__name__}, not an object. Expected "
            f'{{"algorithm": "sha256", "min_token_length": <int>, "terms": [...]}}.'
        )

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


def read_scan_text(path: Path) -> str:
    """The text the scanner reads from the file at *path*: every byte the file holds, never a skip.

    A term is ASCII (``TOKEN_PATTERN``), so the scan needs the ASCII letters and digits a file holds
    whatever its encoding. NUL bytes are dropped, so UTF-16 text reads as its ASCII characters; a byte
    that is not UTF-8 decodes to U+FFFD, which ends a token as a separator does. There is no size cap
    and no binary skip: any file a commit can publish is a file a term can leak through.

    Raises:
        CorpusError: when the file cannot be read; skipping it would report its content as clean.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CorpusError(
            f"{path.name} could not be read ({exc.strerror or exc}). The scan reads every publishable "
            "file and stops rather than skip one. Close the program holding the file, then re-run."
        ) from exc
    return raw.replace(b"\x00", b"").decode("utf-8", errors="replace")


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
    return list(dict.fromkeys(path for path in (line.strip() for line in listing.splitlines()) if path))


def pending_files(repo_path: Path) -> list[str]:
    """Every path a `git add -A` in `repo_path` would stage.

    Modified, added, renamed and untracked-but-not-ignored paths; deletions are
    excluded because there is no content left to scan. `-uall` lists untracked
    files individually rather than collapsing them into a directory entry, so a
    new folder's files are each scanned. `-z` gives every path verbatim: without
    it git C-quotes a path holding a space or a non-ASCII character, and the
    quoted form names no file.
    """
    fields = run_git(repo_path, ["status", "--porcelain", "-z", "-uall"]).split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < PORCELAIN_PATH_OFFSET + 1:
            continue
        status, path = entry[:2], entry[PORCELAIN_PATH_OFFSET:]
        if RENAMED in status or COPIED in status:
            index += 1  # the source path follows as its own field; only the destination has content
        if DELETED in status and UNTRACKED not in status:
            continue
        if path not in paths:
            paths.append(path)
    return paths


def scan_paths(repo_path: Path, rel_paths: list[str], corpus: TermCorpus) -> list[Violation]:
    """Scan the given repo-relative paths and return every violation found."""
    if corpus.is_empty:
        return []
    memo: dict[str, bool] = {}
    violations: list[Violation] = []
    for rel_path in rel_paths:
        path = repo_path / rel_path
        if not path.exists():  # tracked but deleted from the working tree: nothing left to publish
            continue
        for line_number, excerpt in scan_text(read_scan_text(path), corpus, memo):
            violations.append(
                Violation(repo=repo_path.name, path=rel_path, line=line_number, excerpt=excerpt)
            )
    return violations


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


SPACED_RELPATH = "notes/café list.txt"
RENAME_SOURCE_RELPATH = "docs/before.md"
RENAME_DESTINATION_RELPATH = "docs/after.md"
#: Identity for the throwaway commit the rename check makes; ``.invalid`` is a reserved domain.
SELF_TEST_GIT_IDENTITY = ("-c", "user.name=self-test", "-c", "user.email=self-test@example.invalid")


def _git_in(repo: Path, *args: str) -> str:
    """Run git in the self-test repo; returns the error text, or "" when it succeeded."""
    result = subprocess.run(
        ["git", *SELF_TEST_GIT_IDENTITY, "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return "" if result.returncode == 0 else f"git {' '.join(args)}: {result.stderr.strip()}"


def _self_test_pending_paths_verbatim() -> list[str]:
    """Prove `pending_files` names each path as it is on disk, on a real repo.

    An untracked path holding a space and a non-ASCII character (which git C-quotes unless asked for
    ``-z`` output) and a committed file renamed with ``git mv`` (whose entry carries the source path too):
    the first must be listed as its file and scanned, the second listed under its new name only.
    """
    failures: list[str] = []
    corpus = TermCorpus(hashes=frozenset({hash_term(SELF_TEST_TERM)}), min_token_length=5)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        renamed = repo / RENAME_SOURCE_RELPATH
        renamed.parent.mkdir(parents=True, exist_ok=True)
        renamed.write_text(f"{SELF_TEST_TERM}-system-kv-dev\n", encoding="utf-8")
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "seed"),
                     ("mv", RENAME_SOURCE_RELPATH, RENAME_DESTINATION_RELPATH)):
            error = _git_in(repo, *args)
            if error:
                return [f"self-test: could not build the rename repo: {error}"]
        spaced = repo / SPACED_RELPATH
        spaced.parent.mkdir(parents=True, exist_ok=True)
        spaced.write_text(f"{SELF_TEST_TERM}-system-kv-dev\n", encoding="utf-8")

        paths = pending_files(repo)
        if SPACED_RELPATH not in paths:
            failures.append(f"self-test: pending_files did not name a spaced, non-ASCII path verbatim: {paths}")
        if RENAME_DESTINATION_RELPATH not in paths or RENAME_SOURCE_RELPATH in paths:
            failures.append(f"self-test: pending_files did not list a rename under its new name only: {paths}")
        found = {violation.path for violation in scan_paths(repo, paths, corpus)}
        if SPACED_RELPATH not in found:
            failures.append("self-test: scan missed a planted term in a spaced, non-ASCII path")
    return failures


#: The size the scanner once stopped reading at; a term past it must still be found.
FORMER_SIZE_CAP_BYTES = 2_000_000


def _raises_corpus_error(action: Callable[[], object]) -> bool:
    """True when *action* raises `CorpusError`."""
    try:
        action()
    except CorpusError:
        return True
    return False


def _self_test_file_reads() -> list[str]:
    """Prove the scan reads every file it is handed, whatever its encoding or size, and stops on one it
    cannot read."""
    failures: list[str] = []
    corpus = TermCorpus(hashes=frozenset({hash_term(SELF_TEST_TERM)}), min_token_length=5)
    line = f"vault: {SELF_TEST_TERM}-system-kv-dev\n"
    planted = {
        "utf16.txt": line.encode("utf-16"),
        "latin1.txt": f"café {line}".encode("latin-1"),
        "large.txt": b"x" * FORMER_SIZE_CAP_BYTES + b"\n" + line.encode("utf-8"),
        "binary.dat": b"\x89PNG\r\n\x1a\n\x00\x00" + line.encode("utf-8"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        for name, content in planted.items():
            (repo / name).write_bytes(content)
        found = {violation.path for violation in scan_paths(repo, [*planted, "deleted.txt"], corpus)}
        for name in planted:
            if name not in found:
                failures.append(f"self-test: scan missed a planted term in {name}")
        (repo / "a-directory").mkdir()
        if not _raises_corpus_error(lambda: scan_paths(repo, ["a-directory"], corpus)):
            failures.append("self-test: a path that cannot be read as a file did not stop the scan")
        array_corpus = repo / "corpus.json"
        array_corpus.write_text("[]", encoding="utf-8")
        if not _raises_corpus_error(lambda: load_term_corpus(array_corpus)):
            failures.append("self-test: a corpus that is a JSON array was accepted")
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
    failures.extend(_self_test_pending_paths_verbatim())
    failures.extend(_self_test_file_reads())
    return failures
