#!/usr/bin/env python3
"""On-demand code-health scan: one ranked report instead of four scanners' raw output.

Scans the packages whose content changed since the last scan (``--package`` or ``--all``
override that) with the existing scanners, and writes one report:

  - dead code: two-pass Vulture (``metrics.dead_code_report``), every finding checked
    against the code index, which sees the whole workspace. Vulture run over one
    package reports a symbol only other packages use as unused; the index refutes it.
    What survives is "never used anywhere" or "used only by tests".
  - complexity: functions over the cyclomatic or cognitive limit (``metrics.complexity``).
  - duplicates: Pylint R0801 groups (``metrics.duplicate``), largest first.
  - docs drift: the docs lint checks (``dev.check_docs``) over each package's docs/.

Everything runs on this machine; nothing is changed but the report and the scan state.
The report -- every finding, by section, then by package, in rank order -- goes to
``<workspace>/reports/code-scan/``, headed by a per-package count table; standard output
gets one line -- the totals and the report's path -- so a reader opens just the sections it
needs. "Changed since the last scan"
compares each package's file hashes from the code index with the fingerprint recorded
in ``<workspace>/.code-index/scan-state.json`` when that package was last scanned.

Exit codes: 0 digest written (or nothing changed), 1 the scan could not run.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from code_index.queries import find_references  # noqa: E402
from code_index.session import IndexSession, open_session  # noqa: E402
from code_index.sources import CodeIndexError, discover_repos, index_dir  # noqa: E402
from metrics.complexity import (  # noqa: E402
    DEFAULT_IGNORE_DIRS,
    DEFAULT_MAX_COMPLEXITY,
    get_cognitive_complexity,
    run_check,
    run_check_cognitive,
)
from metrics.dead_code_report import DeadCodeError, Finding, collect_dead_code  # noqa: E402
from metrics.duplicate import DuplicateScanError, parse_duplicate_groups, run_pylint_duplicates  # noqa: E402

from dev.check_docs import DOCS_DIR_CHECKS, LintResult  # noqa: E402

EXIT_OK = 0
EXIT_CANNOT_RUN = 1

STATE_NAME = "scan-state.json"
REPORT_DIR = Path("reports") / "code-scan"
DEFAULT_MIN_CONFIDENCE = 60
DEFAULT_DUPLICATE_MIN_LINES = 6

VERDICT_DEAD = "never used"
VERDICT_TEST_ONLY = "used only by tests"
# The index found a use outside tests: Vulture was wrong (typically a use in another package).
VERDICT_REFUTED = "refuted"
# Test-support code (a test harness or testkit module) used by tests: that is what it is for.
VERDICT_TEST_SUPPORT = "test support used by tests"
# The index has no definition at Vulture's file:line; Vulture's own classification stands.
VERDICT_UNMATCHED = "unmatched"
COGNITIVE_MISSING_NOTE = "cognitive_complexity is not installed, so only cyclomatic complexity was checked."
# Names used through strings, where neither Vulture nor the index looks: Jinja files,
# genDSL/Jinja source kept in Python string literals, getattr names and dotted resolver
# paths, and manifest entry points. A finding named in any of them is dropped.
TEMPLATE_SUFFIXES = ("*.j2", "*.jinja", "*.jinja2")
_TEMPLATE_MARKERS = ("{{", "{%", "#{")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAME_OR_DOTTED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
# genDSL text names its context builders (`context Ctx from ns.module.builder;`) and its
# predicates (`where call ns.module.predicate(x)`) by a namespace-aliased dotted path, and
# carries no template marker when the definition interpolates nothing. The last segment is
# the function the executor resolves.
_GENDSL_RESOLVER_RE = re.compile(
    r"\bcontext\s+[A-Za-z_][A-Za-z0-9_]*\s+from\s+((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)"
    r"|\bcall\s+((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)\s*\(")
# Definitions first, data last: an unused class or function is the finding worth reading.
_KIND_RANK = {"class": 0, "function": 1, "method": 2, "property": 3, "attribute": 4, "variable": 5}
GIT_TIMEOUT_SECONDS = 60
# How far below Vulture's reported line (a first decorator) a definition's own line may sit.
DECORATOR_SPAN_LINES = 20
# Unused imports are ruff's F401; they would only crowd the digest.
_SKIPPED_KINDS = frozenset({"import"})
# Test code: a tests/, testing/ or testkit/ folder, a package named for testing (datrix_testing/),
# a test_*.py module, or a conftest.py. A use from here is a use by tests.
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|testing|testkit|[A-Za-z0-9]+_testing)/|(^|/)test_[^/]*\.py$|(^|/)conftest\.py$")


class CodeScanError(RuntimeError):
    """The scan cannot run as asked; the message says what to pass instead."""


@dataclass(frozen=True)
class DeadItem:
    path: str
    line: int
    symbol: str
    kind: str
    confidence: int
    verdict: str
    confirmed: bool  # False: the index could not match the finding to a definition

    @property
    def package(self) -> str:
        return _package_of(self.path)

    def render(self) -> str:
        unconfirmed = "" if self.confirmed else " (not matched in the index; Vulture's word only)"
        return f"- `{self.path}:{self.line}` {self.kind} `{self.symbol}` ({self.confidence}%){unconfirmed}"


@dataclass(frozen=True)
class ComplexItem:
    path: str
    name: str
    line: int
    value: int
    measure: str

    @property
    def package(self) -> str:
        return _package_of(self.path)

    def render(self) -> str:
        return f"- `{self.path}:{self.line}` `{self.name}` {self.measure} {self.value} (limit {DEFAULT_MAX_COMPLEXITY})"


@dataclass(frozen=True)
class DuplicateItem:
    package: str
    lines: int
    locations: tuple[str, ...]

    def render(self) -> str:
        return f"- {self.lines} similar lines in {len(self.locations)} places: " + ", ".join(
            f"`{location}`" for location in self.locations)


@dataclass(frozen=True)
class DocsItem:
    path: str
    line: int
    check: str
    suggestion: str

    @property
    def package(self) -> str:
        return _package_of(self.path)

    def render(self) -> str:
        return f"- `{self.path}:{self.line}` {self.check}: {self.suggestion}"


ScanItem = DeadItem | ComplexItem | DuplicateItem | DocsItem


def _package_of(workspace_relative_path: str) -> str:
    """The repository a workspace-relative path lies in: its first segment."""
    return workspace_relative_path.split("/", 1)[0]


@dataclass
class ScanDigest:
    packages: list[str]
    dead: list[DeadItem] = field(default_factory=list)
    test_only: list[DeadItem] = field(default_factory=list)
    refuted: int = 0
    test_support: int = 0
    named_in_strings: int = 0
    complexity: list[ComplexItem] = field(default_factory=list)
    duplicates: list[DuplicateItem] = field(default_factory=list)
    docs: list[DocsItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def sections(self) -> list[tuple[str, list[ScanItem]]]:
        return [
            ("Dead code: never used anywhere in the workspace", list(self.dead)),
            ("Dead code: used only by tests", list(self.test_only)),
            ("Too complex", list(self.complexity)),
            ("Duplicated blocks", list(self.duplicates)),
            ("Docs drift", list(self.docs)),
        ]

    def _footer(self) -> list[str]:
        lines = [
            f"Vulture findings the index refuted (used elsewhere in the workspace): {self.refuted}",
            f"Vulture findings in test-support code that tests use (its purpose): {self.test_support}",
            f"Vulture findings dropped because a template, string or manifest names them: {self.named_in_strings}",
        ]
        lines.extend(f"Note: {note}" for note in self.notes)
        return lines

    def _package_table(self) -> list[str]:
        counts = [(title, Counter(item.package for item in items)) for title, items in self.sections()]
        lines = ["| Package | Never used | Test-only | Too complex | Duplicated | Docs drift |",
                 "|---|---|---|---|---|---|"]
        for package in self.packages:
            lines.append(f"| {package} | " + " | ".join(str(per[package]) for _, per in counts) + " |")
        lines.append("| **Total** | " + " | ".join(str(sum(per.values())) for _, per in counts) + " |")
        return lines

    def render_report(self) -> str:
        """The whole report: the per-package counts, then every finding by section and package, in rank order."""
        lines = [f"# Code scan {datetime.now():%Y-%m-%d %H:%M}", "", *self._package_table(), "", *self._footer(), ""]
        for title, items in self.sections():
            lines.append(f"## {title} ({len(items)})")
            lines.append("")
            for package in sorted({item.package for item in items}):
                in_package = [item for item in items if item.package == package]
                lines.append(f"### {package} ({len(in_package)})")
                lines.extend(item.render() for item in in_package)
                lines.append("")
        return "\n".join(lines)

    def render_summary(self, report_path: Path) -> str:
        """One line for the console: the totals and where the report is."""
        dead, test_only, complex_, duplicated, docs = (len(items) for _, items in self.sections())
        return (f"Code scan of {len(self.packages)} package(s): {dead} never used, {test_only} test-only, "
                f"{complex_} too complex, {duplicated} duplicated, {docs} docs drift. Report: {report_path}")


def _relative(path: str, workspace: Path) -> str:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = workspace / resolved
    try:
        return resolved.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def scannable_packages(workspace: Path) -> list[str]:
    """Every Python package in the workspace (a pyproject.toml and a src/ tree): what the scanners read.

    A repository with a src/ tree but no pyproject.toml (datrix-vscode, TypeScript) is not one.
    """
    return [repo.name for repo in discover_repos(workspace)
            if (repo / "src").is_dir() and (repo / "pyproject.toml").is_file()]


def fingerprint(conn: sqlite3.Connection, package: str) -> str:
    """A hash of every indexed file of ``package`` and its content hash."""
    digest = hashlib.sha256()
    for path, sha in conn.execute("SELECT path, sha256 FROM files WHERE repo = ? ORDER BY path", (package,)):
        digest.update(f"{path}\0{sha}\n".encode())
    return digest.hexdigest()


def _state_path(workspace: Path) -> Path:
    return index_dir(workspace) / STATE_NAME


def read_state(workspace: Path) -> dict[str, str]:
    path = _state_path(workspace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CodeScanError(f"The scan state {path} is unreadable ({exc}); delete it to rescan everything.") from exc
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise CodeScanError(f"The scan state {path} is not a package-to-fingerprint map; delete it to rescan.")
    return {str(k): v for k, v in data.items()}


def write_state(workspace: Path, state: dict[str, str]) -> None:
    _state_path(workspace).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def package_name(spec: str, workspace: Path) -> str:
    """The package a ``--package`` value names: a name, or a folder path in or under a package.

    ``datrix-cli``, ``.\\datrix-cli\\``, ``D:\\datrix\\datrix-cli`` and ``datrix-cli/src`` all name
    datrix-cli. A relative path is read against the current directory, as a shell user means it.
    """
    text = spec.strip().rstrip("/\\")
    path = Path(text)
    located = path if path.is_absolute() else Path.cwd() / path
    if located.is_dir():
        try:
            parts = located.resolve().relative_to(workspace.resolve()).parts
        except ValueError:
            parts = ()
        if parts:
            return parts[0]
    return path.name


def select_packages(conn: sqlite3.Connection, workspace: Path, requested: list[str], scan_all: bool) -> list[str]:
    available = scannable_packages(workspace)
    if requested:
        names = {package_name(spec, workspace): spec for spec in requested}
        unknown = sorted(spec for name, spec in names.items() if name not in available)
        if unknown:
            raise CodeScanError(f"Unknown package(s) {unknown}. Pass a package name or its folder; scannable "
                                f"packages: {', '.join(available)}.")
        return sorted(names)
    if scan_all:
        return available
    state = read_state(workspace)
    return [package for package in available if state.get(package) != fingerprint(conn, package)]


def index_verdict(conn: sqlite3.Connection, workspace: Path, finding: Finding) -> str:
    """The index's reading of a Vulture finding, across the whole workspace.

    VERDICT_REFUTED when something outside tests uses it, VERDICT_TEST_ONLY when only
    tests do, VERDICT_DEAD when nothing does, VERDICT_UNMATCHED when the index has no
    definition at that file and line. A method matches every ``.name`` access, so a
    common method name is refuted rather than wrongly confirmed dead.

    Vulture reports a decorated definition at its first decorator, the index at its
    ``def``/``class`` line, so the nearest same-named definition at or just below the
    reported line is the match.
    """
    row = conn.execute(
        "SELECT f.module, s.qualname FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.path = ? AND s.name = ? AND s.line BETWEEN ? AND ? ORDER BY s.line LIMIT 1",
        (_relative(finding.file, workspace), finding.symbol, finding.line,
         finding.line + DECORATOR_SPAN_LINES),
    ).fetchone()
    if row is None:
        return VERDICT_UNMATCHED
    sites = find_references(conn, f"{row[0]}.{row[1]}").sites
    if any(not _TEST_PATH_RE.search(path) for path in sites):
        return VERDICT_REFUTED
    if not sites:
        return VERDICT_DEAD
    # Test-support code (a harness package, a testkit) exists to be used by tests: that is its use.
    return VERDICT_TEST_SUPPORT if _TEST_PATH_RE.search(_relative(finding.file, workspace)) else VERDICT_TEST_ONLY


def _template_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for repo in discover_repos(workspace):
        result = subprocess.run(["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard",
                                 "-z", "--", *TEMPLATE_SUFFIXES], capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
                                check=False)
        if result.returncode != 0:
            raise CodeScanError(f"Listing templates in {repo} failed: "
                                f"{result.stderr.decode('utf-8', errors='replace').strip()}")
        files.extend(repo / p for p in result.stdout.decode("utf-8", errors="replace").split("\0") if p)
    return [path for path in files if path.is_file()]


def _string_names(source: str) -> set[str]:
    """Names a module mentions inside string literals: in template text, or as a whole
    identifier or dotted path (``getattr(x, "name")``, ``resolver_ref="pkg.mod.func"``)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if _NAME_OR_DOTTED_RE.fullmatch(text):
            names.update(text.split("."))
        elif any(marker in text for marker in _TEMPLATE_MARKERS):
            names.update(_WORD_RE.findall(text))
        else:
            names.update((context_ref or call_ref).rsplit(".", 1)[-1]
                         for context_ref, call_ref in _GENDSL_RESOLVER_RE.findall(text))
    return names


def named_in_strings(conn: sqlite3.Connection, workspace: Path) -> set[str]:
    """Every name used through a string -- where neither Vulture nor the index can see a use.

    Jinja files, template text in Python strings, strings that are exactly a name or a
    dotted path, and package manifests (entry points name ``module:function``).
    """
    words: set[str] = set()
    for path in _template_files(workspace):
        words.update(_WORD_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
    for repo in discover_repos(workspace):
        manifest = repo / "pyproject.toml"
        if manifest.is_file():
            words.update(_WORD_RE.findall(manifest.read_text(encoding="utf-8", errors="replace")))
    for (rel_path,) in conn.execute("SELECT path FROM files WHERE parse_error = ''"):
        words.update(_string_names((workspace / rel_path).read_text(encoding="utf-8", errors="replace")))
    return words


def classify_dead_code(conn: sqlite3.Connection, workspace: Path, digest: ScanDigest,
                       by_project: dict[str, dict[str, list[Finding]]]) -> None:
    """Check every Vulture finding against the whole-workspace index and string uses; file it by verdict."""
    buckets = {"never_referenced": VERDICT_DEAD, "only_referenced_by_tests": VERDICT_TEST_ONLY}
    by_name = named_in_strings(conn, workspace)
    for groups in by_project.values():
        for bucket, vulture_verdict in buckets.items():
            for finding in groups[bucket]:
                if finding.kind in _SKIPPED_KINDS:
                    continue
                if finding.symbol in by_name:
                    digest.named_in_strings += 1
                    continue
                verdict = index_verdict(conn, workspace, finding)
                if verdict == VERDICT_REFUTED:
                    digest.refuted += 1
                    continue
                if verdict == VERDICT_TEST_SUPPORT:
                    digest.test_support += 1
                    continue
                matched = verdict != VERDICT_UNMATCHED
                item = DeadItem(_relative(finding.file, workspace), finding.line, finding.symbol, finding.kind,
                                finding.confidence, verdict if matched else vulture_verdict, matched)
                (digest.dead if item.verdict == VERDICT_DEAD else digest.test_only).append(item)
    for items in (digest.dead, digest.test_only):
        items.sort(key=lambda i: (not i.confirmed, _KIND_RANK.get(i.kind, len(_KIND_RANK)), -i.confidence,
                                  i.path, i.line))


def scan_complexity(workspace: Path, digest: ScanDigest, package: str) -> None:
    root = workspace / package
    found = [(p, n, ln, v, "cyclomatic") for p, n, ln, v in run_check(root, DEFAULT_MAX_COMPLEXITY,
                                                                       DEFAULT_IGNORE_DIRS, False)]
    if get_cognitive_complexity is None:
        if COGNITIVE_MISSING_NOTE not in digest.notes:
            digest.notes.append(COGNITIVE_MISSING_NOTE)
    else:
        found += [(p, n, ln, v, "cognitive") for p, n, ln, v in run_check_cognitive(
            root, DEFAULT_MAX_COMPLEXITY, DEFAULT_IGNORE_DIRS, False)]
    seen: set[tuple[str, str, int]] = set()
    for path, name, line, value, measure in sorted(found, key=lambda v: -v[3]):
        if (path, name, line) not in seen:
            seen.add((path, name, line))
            digest.complexity.append(ComplexItem(_relative(path, workspace), name, line, value, measure))


def scan_duplicates(workspace: Path, digest: ScanDigest, package: str, min_lines: int) -> None:
    root = workspace / package
    result = run_pylint_duplicates([root / "src"], min_lines, root)
    for group in parse_duplicate_groups(result.stdout or ""):
        locations = group.get("locations")
        if not isinstance(locations, list) or not locations:
            continue
        spans = [(str(loc["file"]), int(loc["start_line"]), int(loc["end_line"])) for loc in locations
                 if isinstance(loc, dict)]
        size = max(end - start + 1 for _, start, end in spans)
        digest.duplicates.append(DuplicateItem(package, size, tuple(f"{f}:{s}-{e}" for f, s, e in spans)))


def scan_docs(workspace: Path, digest: ScanDigest, package: str) -> None:
    docs_dir = workspace / package / "docs"
    if not docs_dir.is_dir():
        return
    result = LintResult()
    for check in DOCS_DIR_CHECKS.values():
        check([docs_dir], result)
    digest.docs.extend(DocsItem(_relative(str(f.file_path), workspace), f.line_number, f.check_name, f.suggestion)
                       for f in result.findings)


def run_scan(session: IndexSession, packages: list[str], min_confidence: int, min_lines: int,
             progress: Callable[[str], None]) -> ScanDigest:
    workspace = session.workspace
    digest = ScanDigest(packages)
    progress(f"Dead code: Vulture over {len(packages)} package(s), checked against the index...")
    try:
        dead = collect_dead_code(workspace, packages, min_confidence)
    except DeadCodeError as exc:
        raise CodeScanError(f"The dead-code scan could not run: {exc}") from exc
    classify_dead_code(session.conn, workspace, digest, dead.by_project)
    for number, package in enumerate(packages, start=1):
        progress(f"[{number}/{len(packages)}] {package}: complexity, duplicates, docs...")
        scan_complexity(workspace, digest, package)
        try:
            scan_duplicates(workspace, digest, package, min_lines)
        except DuplicateScanError as exc:
            raise CodeScanError(f"The duplicate scan could not run: {exc}") from exc
        scan_docs(workspace, digest, package)
    digest.complexity.sort(key=lambda i: -i.value)
    digest.duplicates.sort(key=lambda i: (-i.lines * len(i.locations), i.package))
    return digest


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", action="append", default=[],
                        help="Scan this package: its name or its folder (repeatable).")
    parser.add_argument("--all", action="store_true", dest="scan_all", help="Scan every package.")
    parser.add_argument("--min-confidence", type=int, default=DEFAULT_MIN_CONFIDENCE,
                        help="Vulture's minimum confidence for a dead-code finding.")
    parser.add_argument("--duplicate-min-lines", type=int, default=DEFAULT_DUPLICATE_MIN_LINES,
                        help="Smallest duplicated block Pylint reports.")
    args = parser.parse_args(argv)

    def progress(line: str) -> None:
        # Standard error, one line per stage: a scan of every package takes minutes, and a
        # silent console reads as a hung one. The result itself is the one stdout line.
        print(line, file=sys.stderr, flush=True)

    try:
        session = open_session()
        try:
            progress("Refreshing the code index...")
            session.refresh()
            packages = select_packages(session.conn, session.workspace, args.package, args.scan_all)
            if not packages:
                print("No package changed since its last scan. Pass --package NAME or --all to scan anyway.")
                return EXIT_OK
            digest = run_scan(session, packages, args.min_confidence, args.duplicate_min_lines, progress)
            state = read_state(session.workspace)
            state.update({package: fingerprint(session.conn, package) for package in packages})
            write_state(session.workspace, state)
        finally:
            session.close()
    except (CodeScanError, CodeIndexError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    out_dir = session.workspace / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"code-scan-{datetime.now():%Y%m%d-%H%M%S}.md"
    out_path.write_text(digest.render_report() + "\n", encoding="utf-8")
    print(digest.render_summary(out_path))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
