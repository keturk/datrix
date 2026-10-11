#!/usr/bin/env python
"""Repo-level gate: no retired internal-DSL name appears in a Datrix framework repo.

When an internal language is renamed or replaced, every identifier, module, package,
entry-point group, feature tag, script, resource file and document carrying its old name
is renamed with it. This gate holds that end state: it scans every PUBLISHABLE file of
every framework repo -- tracked files plus untracked-but-not-ignored ones, because a new
file is untracked right up until the ``git add`` that commits it -- and fails on any
retired spelling in file content, in a file name, or in a directory name.

The spellings are data, not code: ``retired_dsl_names.json`` beside this module holds one
entry per retired family (a name, the replacement to use, case-insensitive patterns, and
concrete samples the self-test plants). That file is the only path the scan skips, so this
module and its wrapper are themselves scanned and must never spell a retired name.

Repo-level validation script, per the datrix showcase boundary: the showcase repo hosts no
pytest suite, so the self-test below is the gate's coverage. It runs before every scan.

Exit codes:
  0 = no retired spelling found (or the self-test passed, with --self-test)
  1 = at least one retired spelling, or the self-test failed
  2 = usage error, a malformed spellings file, a repo git cannot list, or a file that
      cannot be read
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.customer_domain_isolation import CorpusError, publishable_files
from datrix_scripts.framework_repos import select_framework_repos
from datrix_scripts.paths import WORKSPACE_DIR

SPELLINGS_FILE = Path(__file__).resolve().with_name("retired_dsl_names.json")
SCRATCH_ROOT = WORKSPACE_DIR / ".tmp"
SELF_TEST_PREFIX = "retired-dsl-names-selftest-"
MAX_EXCERPT_CHARS = 160
NAME_HIT_LINE = 0
PATH_SEPARATOR = "/"
REQUIRED_FAMILY_KEYS = ("name", "replacement", "patterns", "samples")
CLEAN_SAMPLE = "The order service reads a generator document and publishes an OrderPlaced event.\n"


class SpellingsError(RuntimeError):
    """The spellings file is missing, unreadable or malformed."""


class UnreadableFileError(RuntimeError):
    """A publishable file exists but cannot be read, so its content cannot be scanned."""


@dataclass(frozen=True)
class Family:
    """One retired name family: its patterns and the samples that prove them."""

    name: str
    replacement: str
    patterns: tuple[re.Pattern[str], ...]
    samples: tuple[str, ...]

    def matches(self, text: str) -> bool:
        """Return whether any of this family's patterns occurs in *text*."""
        return any(pattern.search(text) for pattern in self.patterns)


@dataclass(frozen=True)
class Hit:
    """One retired spelling found in a repo.

    ``line`` is the 1-based content line, or ``NAME_HIT_LINE`` when the spelling is in the
    path itself; then ``path`` is the offending file or directory and ``excerpt`` the
    offending name segment.
    """

    repo: str
    path: str
    line: int
    family: str
    excerpt: str

    def render(self) -> str:
        """Format the hit as one report line."""
        if self.line == NAME_HIT_LINE:
            return f"{self.path}: [{self.family}] name segment '{self.excerpt}'"
        return f"{self.path}:{self.line}: [{self.family}] {self.excerpt}"


def _string_list(entry: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    """Return ``entry[key]`` as a non-empty tuple of non-empty strings."""
    value = entry[key]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise SpellingsError(
            f"{label}: '{key}' must be a non-empty list of non-empty strings, got {value!r}. "
            f"Fix the entry in {SPELLINGS_FILE}."
        )
    return tuple(value)


def _compile_patterns(raw: tuple[str, ...], label: str) -> tuple[re.Pattern[str], ...]:
    """Compile each pattern case-insensitively, naming the one that does not compile."""
    compiled: list[re.Pattern[str]] = []
    for pattern in raw:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise SpellingsError(
                f"{label}: pattern {pattern!r} is not a valid regular expression ({exc}). "
                f"Fix it in {SPELLINGS_FILE}."
            ) from exc
    return tuple(compiled)


def _parse_family(entry: object, index: int) -> Family:
    """Validate one ``families`` entry and build its ``Family``."""
    label = f"families[{index}]"
    if not isinstance(entry, dict):
        raise SpellingsError(f"{label} must be an object with keys {REQUIRED_FAMILY_KEYS}, got {entry!r}.")
    missing = [key for key in REQUIRED_FAMILY_KEYS if key not in entry]
    if missing:
        raise SpellingsError(
            f"{label} is missing {missing}. Every family needs {REQUIRED_FAMILY_KEYS}; add them in {SPELLINGS_FILE}."
        )
    name, replacement = entry["name"], entry["replacement"]
    if not isinstance(name, str) or not name or not isinstance(replacement, str) or not replacement:
        raise SpellingsError(f"{label}: 'name' and 'replacement' must be non-empty strings.")
    family = Family(
        name=name,
        replacement=replacement,
        patterns=_compile_patterns(_string_list(entry, "patterns", label), label),
        samples=_string_list(entry, "samples", label),
    )
    unmatched = [sample for sample in family.samples if not family.matches(sample)]
    if unmatched:
        raise SpellingsError(
            f"{label} ({name}): samples {unmatched} match none of its patterns, so the self-test "
            f"could not prove them. Correct the sample or the pattern in {SPELLINGS_FILE}."
        )
    return family


def load_families(path: Path) -> tuple[Family, ...]:
    """Load and validate every retired family from the spellings file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpellingsError(f"Cannot read the spellings file {path}: {exc}") from exc
    families = data.get("families") if isinstance(data, dict) else None
    if not isinstance(families, list) or not families:
        raise SpellingsError(
            f"{path} must hold a non-empty 'families' list; an empty list would make the gate vacuous."
        )
    return tuple(_parse_family(entry, index) for index, entry in enumerate(families))


def read_text(path: Path) -> str | None:
    """Return a file's text, or None when it is not a regular file or holds binary data.

    Raises:
        UnreadableFileError: If the file exists but cannot be read. Skipping it would leave
            its content unscanned and report a clean tree.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UnreadableFileError(
            f"Cannot read {path} ({exc}); an unread file would pass unscanned. "
            "Close whatever holds it open or fix its permissions, then re-run the gate."
        ) from exc
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def _excerpt(line: str) -> str:
    """Trim a matching line to a bounded, single-line excerpt."""
    stripped = line.strip()
    if len(stripped) <= MAX_EXCERPT_CHARS:
        return stripped
    return stripped[:MAX_EXCERPT_CHARS] + "..."


def scan_content(text: str, families: tuple[Family, ...]) -> list[tuple[int, str, str]]:
    """Return ``(line, family name, excerpt)`` for every line carrying a retired spelling."""
    found: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for family in families:
            if family.matches(line):
                found.append((line_number, family.name, _excerpt(line)))
    return found


def _name_hits(repo: Path, rel_path: str, families: tuple[Family, ...], seen_dirs: set[str]) -> list[Hit]:
    """Hits for retired spellings in the directory and file names of *rel_path*.

    A directory is reported once however many files sit under it.
    """
    hits: list[Hit] = []
    segments = rel_path.split(PATH_SEPARATOR)
    for depth, segment in enumerate(segments):
        location = PATH_SEPARATOR.join(segments[: depth + 1])
        is_directory = depth < len(segments) - 1
        if is_directory and location in seen_dirs:
            continue
        for family in families:
            if family.matches(segment):
                hits.append(Hit(repo.name, location, NAME_HIT_LINE, family.name, segment))
        if is_directory:
            seen_dirs.add(location)
    return hits


def scan_repo(
    repo: Path, rel_paths: list[str], families: tuple[Family, ...], exempt: frozenset[Path]
) -> list[Hit]:
    """Scan the given repo-relative paths' names and content; skip the *exempt* files."""
    hits: list[Hit] = []
    seen_dirs: set[str] = set()
    for rel_path in rel_paths:
        absolute = (repo / rel_path).resolve()
        if absolute in exempt:
            continue
        hits.extend(_name_hits(repo, rel_path, families, seen_dirs))
        text = read_text(absolute)
        if text is None:
            continue
        for line_number, family_name, excerpt in scan_content(text, families):
            hits.append(Hit(repo.name, rel_path, line_number, family_name, excerpt))
    return hits


def _plant(repo: Path, rel_path: str, text: str) -> None:
    """Write *text* to *rel_path* under the scratch repo, creating parent directories."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _plant_fixtures(repo: Path, families: tuple[Family, ...]) -> dict[str, int]:
    """Plant every sample three ways and return ``{expected hit path: expected line}``."""
    expected: dict[str, int] = {}
    for family_index, family in enumerate(families):
        for sample_index, sample in enumerate(family.samples):
            tag = f"{family_index}-{sample_index}"
            content_path = f"content/sample-{tag}.txt"
            _plant(repo, content_path, f"first line\nthis line uses {sample} here\n")
            expected[content_path] = 2
            file_path = f"names/file-{tag}-{sample}.txt"
            _plant(repo, file_path, CLEAN_SAMPLE)
            expected[file_path] = NAME_HIT_LINE
            directory = f"dirs/{sample}-{tag}"
            _plant(repo, f"{directory}/inner.txt", CLEAN_SAMPLE)
            expected[directory] = NAME_HIT_LINE
            _plant(repo, f"ignored/sample-{tag}.txt", f"{sample}\n")
    return expected


def _check_hits(hits: list[Hit], expected: dict[str, int]) -> list[str]:
    """Compare the scan's hits with the planted expectations."""
    failures: list[str] = []
    reported = {(hit.path, hit.line) for hit in hits}
    for path, line in sorted(expected.items()):
        if (path, line) not in reported:
            failures.append(f"self-test: planted spelling at {path}:{line} was NOT reported")
    for hit in hits:
        if hit.path.startswith("ignored/"):
            failures.append(f"self-test: a git-ignored file was scanned ({hit.path})")
        if hit.path.startswith(("lib/", "docs/")) or hit.path.endswith("inner.txt"):
            failures.append(f"self-test: a clean or exempt file was reported ({hit.render()})")
    return failures


def self_test(families: tuple[Family, ...]) -> list[str]:
    """Prove the scan is not vacuous on a real scratch git repo. Returns failure descriptions.

    Every sample of every family is planted in file content, in a file name and in a
    directory name of an untracked file; a git-ignored copy, a clean file, and an exempt
    spellings file must not be reported. The listing is the same ``publishable_files`` the
    real scan uses, so a lister that stopped reaching new files fails here too.
    """
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH_ROOT, prefix=SELF_TEST_PREFIX, ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp)
        init = subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, text=True, check=False)
        if init.returncode != 0:
            return [f"self-test: could not create a scratch git repo: {init.stderr.strip()}"]
        _plant(repo, ".gitignore", "ignored/\n")
        _plant(repo, "docs/clean.md", CLEAN_SAMPLE)
        all_samples = [sample for family in families for sample in family.samples]
        _plant(repo, "lib/spellings.json", json.dumps(all_samples) + "\n")
        expected = _plant_fixtures(repo, families)
        exempt = frozenset({(repo / "lib/spellings.json").resolve()})
        hits = scan_repo(repo, publishable_files(repo), families, exempt)
        return _check_hits(hits, expected)


def report(hits: list[Hit]) -> None:
    """Print every hit, grouped by repo."""
    by_repo: dict[str, list[Hit]] = {}
    for hit in hits:
        by_repo.setdefault(hit.repo, []).append(hit)
    for repo in sorted(by_repo):
        print(f"\n  {repo}:")
        for hit in by_repo[repo]:
            print(f"    {hit.render()}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="No retired internal-DSL name in a framework repo.")
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable). Default: every framework repo.",
    )
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test; skip the real scan.")
    return parser.parse_args(argv)


def scan_workspace(repos: list[Path], families: tuple[Family, ...]) -> list[Hit]:
    """Scan every publishable file of every repo, skipping only the spellings file."""
    exempt = frozenset({SPELLINGS_FILE})
    hits: list[Hit] = []
    for repo in repos:
        rel_paths = publishable_files(repo)
        found = scan_repo(repo, rel_paths, families, exempt)
        print(f"  {repo.name}: {len(rel_paths)} file(s) scanned, {len(found)} hit(s)")
        hits.extend(found)
    return hits


def main(argv: list[str]) -> int:
    # Reported excerpts are arbitrary repo text; a console codepage that cannot encode one
    # character must not abort the report half-way.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        families = load_families(SPELLINGS_FILE)
    except SpellingsError as exc:
        print(f"RETIRED-DSL-NAMES GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    failures = self_test(families)
    if failures:
        print("RETIRED-DSL-NAMES GATE CANNOT BE TRUSTED: self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return 1
    if args.self_test:
        print(f"RETIRED-DSL-NAMES SELF-TEST PASSED: {len(families)} family(ies), every sample detected.")
        return 0

    try:
        repos = select_framework_repos(WORKSPACE_DIR, args.repo)
        print(f"Scanning publishable files in {len(repos)} repo(s) for {len(families)} retired family(ies)")
        hits = scan_workspace(repos, families)
    except (ValueError, CorpusError, UnreadableFileError) as exc:
        print(f"RETIRED-DSL-NAMES GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    if hits:
        replacements = "; ".join(f"{family.name} -> {family.replacement}" for family in families)
        print(
            f"\nRETIRED-DSL-NAMES GATE FAILED: {len(hits)} occurrence(s) of a retired name. "
            f"Rename each at its source ({replacements})."
        )
        report(hits)
        return 1

    print("\nRETIRED-DSL-NAMES GATE PASSED: no retired name found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
