#!/usr/bin/env python3
"""Fixture budget ratchet: the ``.dtrx``/``.dcfg`` test fixtures of every package, counted and capped.

Packages are the ``datrix-*`` directories holding a ``tests/`` tree, discovered from disk. Per package
the gate counts:

``fixture_files``
    ``*.dtrx``, ``*.dtrx.false``, ``*.dcfg`` and ``*.dseed`` files under ``tests/`` (``.git``,
    ``node_modules``, ``__pycache__``, ``.test-output``, ``.test_results`` and ``build`` pruned, no
    directory link entered).
``inline_literals``
    string constants, and the joined constant parts of f-strings, docstrings excluded, in
    ``tests/**/*.py``, ``src/**/testkit/**/*.py`` and ``src/datrix_testing/**/*.py`` that hold a
    ``.dtrx`` declaration line together with a ``{``, or a ``.dcfg`` ``config`` header.

Across every counted file it counts:

``duplicate_copies``
    files whose normalized content (comments outside string literals removed, ``#`` comments in
    ``.dcfg`` only, whitespace collapsed) equals another file's of the same kind, minus one per group.
``cross_package_names``
    fixture base names present under ``tests/`` of two or more packages, ``system.dtrx`` excluded.
``shared_files``
    the same file kinds under ``datrix-testing/src/datrix_testing/fixtures_data/``. Printed, not pinned:
    the shared set grows as copies move into it from the packages.
``total_fixtures``
    every package's ``fixture_files`` and ``inline_literals`` plus ``shared_files``. Moving a fixture
    into the shared set leaves it unchanged; deleting a copy lowers it.

Every count but ``shared_files`` is pinned by ``scripts/config/fixture-budget-baseline.json`` and may
only fall. A missing baseline is refused, never read as empty; ``--update-baseline`` freezes the first
baseline and afterwards writes only when no count rises.

Every entry of the fixture corpus (``fixtures_data/corpus/``, its scenarios listed by
``datrix_testing.corpus.corpus_scenarios``) must be read: some module under a package's ``tests/`` passes
the scenario's name as a string literal to ``corpus_project(...)``, positionally or by keyword. An entry
no test names fails the gate; a missing corpus root, or a scenario written in both entry forms, is refused.

Exit codes:
    0: every pinned count at or below its baseline and every corpus entry read (or a successful
       ``--update-baseline`` or ``--self-test``).
    1: a pinned count above its baseline, or a corpus entry no test reads.
    2: usage error, missing or malformed baseline, an attempted baseline increase, a file that cannot be
       read or parsed, a missing shared fixture directory or corpus root, an ambiguous corpus entry, or a
       failed self-test.

Run through ``gates/ratchet/fixture-budget-gate.ps1`` (or its ``.sh`` twin) in gate mode
(``datrix_scripts.gate_log.run_as_gate``): the last line is
``[GATE] fixture-budget PASSED|FAILED exit=<n> log=<path>``.

Usage:
    fixture-budget-gate.ps1
    fixture-budget-gate.ps1 -ShowFiles
    fixture-budget-gate.ps1 -UpdateBaseline
    fixture-budget-gate.ps1 -SelfTest
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import inspect
import io
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_testing.corpus import CORPUS_ROOT, corpus_project, corpus_scenarios
from datrix_testing.shared_fixtures import SHARED_FIXTURES_DIR

from datrix_scripts.cleanup_utils import is_link, plant_directory_link
from datrix_scripts.count_ratchet import RatchetMode, compare, load_counts_json, write_counts_json
from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    NamedCheck,
    UsageError,
    harness_self_test,
    named_checks,
    print_command,
    report_step,
    run_checks,
    write_files,
)
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import CONFIG_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "fixture-budget"
MODULE: Final = "datrix_scripts.gates.ratchet.fixture_budget_gate"
WRAPPER: Final = "fixture-budget-gate"

BASELINE_TABLE: Final = "baseline"
BASELINE_RELATIVE: Final = CONFIG_DIR.relative_to(WORKSPACE_DIR) / "fixture-budget-baseline.json"

SHARED_PACKAGE: Final = "datrix-testing"
SHARED_FIXTURES_RELATIVE: Final = Path("src", "datrix_testing", "fixtures_data")
CORPUS_RELATIVE: Final = SHARED_FIXTURES_RELATIVE / CORPUS_ROOT.relative_to(SHARED_FIXTURES_DIR)
# The accessor a test reads a corpus entry through, and the name of its scenario parameter.
CORPUS_READER: Final = corpus_project.__name__
CORPUS_SCENARIO_PARAMETER: Final = next(iter(inspect.signature(corpus_project).parameters))
TESTKIT_DIR: Final = "testkit"
TESTING_SOURCE_DIR: Final = "datrix_testing"
PYTHON_SUFFIX: Final = ".py"

# Longest suffix first, so ``x.dtrx.false`` is a ``.dtrx.false`` and never a ``.dtrx``.
FIXTURE_KINDS: Final = (".dtrx.false", ".dtrx", ".dcfg", ".dseed")
DCFG_KIND: Final = ".dcfg"
DTRX_KIND: Final = ".dtrx"
SKIPPED_DIRS: Final = frozenset({".git", "node_modules", "__pycache__", ".test-output", ".test_results", "build"})
CROSS_NAME_EXEMPT: Final = frozenset({"system.dtrx"})

FIXTURE_FILES: Final = "fixture_files"
INLINE_LITERALS: Final = "inline_literals"
DUPLICATE_COPIES: Final = "duplicate_copies"
CROSS_PACKAGE_NAMES: Final = "cross_package_names"
SHARED_FILES: Final = "shared_files"
TOTAL_FIXTURES: Final = "total_fixtures"
PACKAGE_KEY_SEPARATOR: Final = ":"

_DTRX_DECLARATION: Final = re.compile(
    r"^\s*(abstract\s+)?(service|system|module|shared|app|extern\s+service)\s+[A-Za-z_][\w.]*\s*[({:]",
    re.MULTILINE,
)
_DCFG_HEADER: Final = re.compile(r"^\s*config\s+(service|system|shared|app)\s+[A-Za-z_][\w.]*\s*\{", re.MULTILINE)
# One lexeme at a time, a string literal (double- or single-quoted) first, so a ``//`` or ``#`` inside a
# string is never a comment.
_STRING_LEXEME: Final = r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\''
_STRING_QUOTES: Final = ('"', "'")
_DTRX_LEXEMES: Final = re.compile(rf"{_STRING_LEXEME}|//[^\n]*|/\*.*?\*/", re.DOTALL)
_DCFG_LEXEMES: Final = re.compile(rf"{_STRING_LEXEME}|//[^\n]*|/\*.*?\*/|#[^\n]*", re.DOTALL)
_WHITESPACE: Final = re.compile(r"\s+")
_BYTE_ORDER_MARK: Final = "﻿"

_FIXES: Final[Mapping[str, str]] = {
    FIXTURE_FILES: "read an existing fixture (a datrix-testing fixtures_data file or one of the package's own) "
    "instead of adding a file",
    INLINE_LITERALS: "read an existing fixture file instead of writing the .dtrx/.dcfg text into the test module",
    DUPLICATE_COPIES: "delete the copy and read the file it duplicates (-ShowFiles lists each group)",
    CROSS_PACKAGE_NAMES: "read the shared datrix-testing fixture, or give the package's own fixture a name of its "
    "own (-ShowFiles lists each name and its packages)",
    TOTAL_FIXTURES: "move the fixture into the shared datrix-testing set or read one already there, instead of "
    "adding a fixture file or inline fixture text anywhere",
}

_BASELINE_COMMENT: Final = (
    "Fixture budget baseline. Per package: fixture_files (.dtrx, .dtrx.false, .dcfg, .dseed files under "
    "tests/) and inline_literals (.dtrx/.dcfg string literals in test modules); globally: duplicate_copies, "
    "cross_package_names and total_fixtures (every package's fixture_files and inline_literals plus the "
    "shared datrix-testing fixture files). Every count may only fall: "
    "datrix/scripts/gates/ratchet/fixture-budget-gate.ps1 fails a rise, and its -UpdateBaseline writes only "
    "when no count rises. shared_files is printed by the gate and is not pinned here."
)


class FixtureScanError(Exception):
    """A file the census must read cannot be read or parsed, or a counted tree is missing (exit 2)."""


@dataclass(frozen=True)
class FixtureFile:
    """One counted fixture file: its path, its kind (the matched suffix) and the package holding it."""

    path: Path
    kind: str
    package: str


@dataclass(frozen=True)
class LiteralSite:
    """One string literal holding inline ``.dtrx``/``.dcfg`` text: the module and the literal's line."""

    path: Path
    line: int


@dataclass(frozen=True)
class Census:
    """Everything one scan counted, keyed by package directory name."""

    package_files: dict[str, list[FixtureFile]]
    literal_sites: dict[str, list[LiteralSite]]
    shared_files: list[FixtureFile]
    duplicate_groups: list[list[FixtureFile]]
    cross_package_names: dict[str, list[str]]
    scenarios: tuple[str, ...]
    scenario_readers: dict[str, list[Path]]

    def counts(self) -> dict[str, int]:
        """The ratcheted counts as baseline keys: ``<package>:<count>`` per package, then the globals."""
        result: dict[str, int] = {}
        for package, files in self.package_files.items():
            result[package_key(package, FIXTURE_FILES)] = len(files)
            result[package_key(package, INLINE_LITERALS)] = len(self.literal_sites[package])
        result[DUPLICATE_COPIES] = sum(len(group) - 1 for group in self.duplicate_groups)
        result[CROSS_PACKAGE_NAMES] = len(self.cross_package_names)
        result[TOTAL_FIXTURES] = (
            sum(len(files) for files in self.package_files.values())
            + sum(len(sites) for sites in self.literal_sites.values())
            + len(self.shared_files)
        )
        return result


def package_key(package: str, count: str) -> str:
    """The baseline key of one per-package count."""
    return f"{package}{PACKAGE_KEY_SEPARATOR}{count}"


def walk_files(root: Path) -> Iterator[Path]:
    """Every file under *root* in name order, pruning ``SKIPPED_DIRS`` and never entering a directory link."""
    for current, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name for name in dir_names if name not in SKIPPED_DIRS and not is_link(Path(current, name))
        )
        for name in sorted(file_names):
            yield Path(current, name)


def is_fixture(name: str) -> bool:
    """Whether a file name carries one of the counted fixture kinds."""
    return name.endswith(FIXTURE_KINDS)


def fixture_kind(name: str) -> str:
    """The kind (matched suffix) of a fixture file name; ``is_fixture(name)`` must hold."""
    return next(kind for kind in FIXTURE_KINDS if name.endswith(kind))


def fixture_files(root: Path, package: str) -> list[FixtureFile]:
    """The fixture files under *root*, owned by *package*."""
    return [
        FixtureFile(path=path, kind=fixture_kind(path.name), package=package)
        for path in walk_files(root)
        if is_fixture(path.name)
    ]


def normalized(text: str, kind: str) -> str:
    """*text* with its comments removed (``#`` ones too in ``.dcfg``) and whitespace collapsed.

    String literals are kept whole, so a ``//`` inside one (``"http://host"``) is content, not a comment.
    """
    lexemes = _DCFG_LEXEMES if kind == DCFG_KIND else _DTRX_LEXEMES
    without_comments = lexemes.sub(_keep_string_literal, text.removeprefix(_BYTE_ORDER_MARK))
    return _WHITESPACE.sub(" ", without_comments).strip()


def _keep_string_literal(match: re.Match[str]) -> str:
    lexeme = match.group(0)
    return lexeme if lexeme.startswith(_STRING_QUOTES) else " "


def string_lexemes(text: str, kind: str) -> list[tuple[int, str]]:
    """``(offset, value)`` of every string literal of fixture *text* outside a comment, by the lexing
    ``normalized`` uses: *offset* is where the value starts in *text* (after the opening quote), *value* the
    characters between the quotes as written."""
    lexemes = _DCFG_LEXEMES if kind == DCFG_KIND else _DTRX_LEXEMES
    return [
        (match.start() + 1, match.group(0)[1:-1])
        for match in lexemes.finditer(text)
        if match.group(0).startswith(_STRING_QUOTES)
    ]


def read_fixture(path: Path) -> str:
    """The fixture's text; undecodable bytes are kept (escaped), so equal bytes always compare equal."""
    try:
        return path.read_bytes().decode("utf-8", errors="surrogateescape")
    except OSError as exc:
        raise FixtureScanError(
            f"cannot read fixture {path}: {exc}. A counted file that cannot be read would escape the "
            "duplicate count. Fix: resolve the read error."
        ) from exc


def duplicate_groups(files: Sequence[FixtureFile]) -> list[list[FixtureFile]]:
    """The groups of two or more files of one kind whose normalized content is equal, in path order."""
    groups: dict[tuple[str, str], list[FixtureFile]] = defaultdict(list)
    for fixture in files:
        groups[(fixture.kind, normalized(read_fixture(fixture.path), fixture.kind))].append(fixture)
    found = [sorted(group, key=lambda fixture: fixture.path.as_posix()) for group in groups.values() if len(group) > 1]
    return sorted(found, key=lambda group: group[0].path.as_posix())


def cross_package_names(package_files: Mapping[str, Sequence[FixtureFile]]) -> dict[str, list[str]]:
    """Each fixture base name found under ``tests/`` of two or more packages, with those packages."""
    owners: dict[str, set[str]] = defaultdict(set)
    for package, files in package_files.items():
        for fixture in files:
            if fixture.path.name not in CROSS_NAME_EXEMPT:
                owners[fixture.path.name].add(package)
    return {name: sorted(packages) for name, packages in sorted(owners.items()) if len(packages) > 1}


def fixture_text_kind(text: str) -> str | None:
    """The fixture kind a string literal's text is written in: ``.dcfg`` for a ``.dcfg`` header, ``.dtrx`` for
    a ``.dtrx`` declaration line with a ``{``, else ``None`` (no fixture text)."""
    if _DCFG_HEADER.search(text) is not None:
        return DCFG_KIND
    if "{" in text and _DTRX_DECLARATION.search(text) is not None:
        return DTRX_KIND
    return None


def holds_fixture_text(text: str) -> bool:
    """Whether a string literal holds a ``.dtrx`` declaration line with a ``{``, or a ``.dcfg`` header."""
    return fixture_text_kind(text) is not None


def _docstring_ids(tree: ast.Module) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, owners) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def string_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """``(line, text)`` of every string literal in *tree*: an f-string once, as its constant parts joined;
    docstrings excluded."""
    skipped = _docstring_ids(tree)
    literals: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = [part for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)]
            skipped.update(id(part) for part in parts)
            literals.append((node.lineno, "".join(str(part.value) for part in parts)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped:
            literals.append((node.lineno, node.value))
    return sorted(literals)


def parse_module(module: Path) -> ast.Module:
    """*module* parsed.

    Raises:
        FixtureScanError: the module cannot be read or parsed.
    """
    try:
        return ast.parse(module.read_bytes(), filename=str(module))
    except (OSError, SyntaxError, ValueError) as exc:
        raise FixtureScanError(
            f"cannot parse {module}: {exc}. A test module that cannot be parsed would escape the inline "
            "literal count and the corpus reads. Fix: correct the file's syntax or encoding."
        ) from exc


def literal_sites(module: Path, tree: ast.Module) -> list[LiteralSite]:
    """The string literals of *module* (parsed as *tree*) holding inline ``.dtrx``/``.dcfg`` text."""
    return [LiteralSite(path=module, line=line) for line, text in string_literals(tree) if holds_fixture_text(text)]


def _calls_corpus_reader(function: ast.expr) -> bool:
    if isinstance(function, ast.Name):
        return function.id == CORPUS_READER
    return isinstance(function, ast.Attribute) and function.attr == CORPUS_READER


def corpus_reads(tree: ast.Module) -> set[str]:
    """The scenario names *tree* passes as a string literal to ``corpus_project(...)``, positionally or by
    keyword. A name computed at run time is not a read the gate can see, so it never counts."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _calls_corpus_reader(node.func):
            continue
        keyword_values = [keyword.value for keyword in node.keywords if keyword.arg == CORPUS_SCENARIO_PARAMETER]
        for argument in [*node.args[:1], *keyword_values]:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                names.add(argument.value)
    return names


def literal_modules(package_dir: Path) -> list[Path]:
    """The Python modules whose literals count for *package_dir*: ``tests/``, ``src/**/testkit/`` and
    ``src/datrix_testing/``."""
    modules = [path for path in walk_files(package_dir / PackageMarker.TESTS.value) if path.suffix == PYTHON_SUFFIX]
    source = package_dir / PackageMarker.SRC.value
    for path in walk_files(source):
        directories = path.relative_to(source).parts[:-1]
        test_support = TESTKIT_DIR in directories or directories[:1] == (TESTING_SOURCE_DIR,)
        if path.suffix == PYTHON_SUFFIX and test_support:
            modules.append(path)
    return modules


def scan_package_modules(package_dir: Path) -> tuple[list[LiteralSite], dict[str, list[Path]]]:
    """The inline literal sites of *package_dir*'s ``literal_modules``, and the corpus scenarios its
    ``tests/`` modules read, each with the modules reading it. Every module is parsed once."""
    tests_dir = package_dir / PackageMarker.TESTS.value
    sites: list[LiteralSite] = []
    readers: dict[str, list[Path]] = defaultdict(list)
    for module in literal_modules(package_dir):
        tree = parse_module(module)
        sites.extend(literal_sites(module, tree))
        if module.is_relative_to(tests_dir):
            for scenario in corpus_reads(tree):
                readers[scenario].append(module)
    return sites, readers


def corpus_entries(base_dir: Path) -> tuple[str, ...]:
    """The scenarios of the corpus under *base_dir*, by the corpus's own entry rule.

    Raises:
        FixtureScanError: the corpus root is missing, or a scenario is written in both entry forms.
    """
    try:
        return corpus_scenarios(base_dir / SHARED_PACKAGE / CORPUS_RELATIVE)
    except (FileNotFoundError, ValueError) as exc:
        raise FixtureScanError(
            f"{exc} Without the corpus's entries the gate cannot prove every entry is read by a test."
        ) from exc


def take_census(base_dir: Path) -> Census:
    """Count every package's fixtures and inline literals, the shared fixtures, duplicates and shared names,
    and find which corpus entries the packages' tests read.

    Raises:
        FixtureScanError: no package has a ``tests/`` tree, the shared fixture directory or the corpus root
            is missing, a corpus entry is ambiguous, or a counted file cannot be read or parsed.
    """
    packages = workspace_package_dirs(base_dir, any_of=frozenset({PackageMarker.TESTS}))
    if not packages:
        raise FixtureScanError(
            f"no datrix-* directory under {base_dir} holds a tests/ tree, so there is nothing to count. "
            "Fix: point -BaseDir at the workspace root."
        )
    shared_dir = base_dir / SHARED_PACKAGE / SHARED_FIXTURES_RELATIVE
    if not shared_dir.is_dir():
        raise FixtureScanError(
            f"shared fixture directory {shared_dir} does not exist; shared_files would read 0 forever. "
            "Fix: point -BaseDir at the workspace root, or restore the directory."
        )
    package_files = {
        package.name: fixture_files(package / PackageMarker.TESTS.value, package.name) for package in packages
    }
    scenarios = corpus_entries(base_dir)
    sites: dict[str, list[LiteralSite]] = {}
    readers: dict[str, list[Path]] = defaultdict(list)
    for package in packages:
        sites[package.name], package_readers = scan_package_modules(package)
        for scenario, modules in package_readers.items():
            readers[scenario].extend(modules)
    shared = fixture_files(shared_dir, SHARED_PACKAGE)
    every_file = [fixture for files in package_files.values() for fixture in files] + shared
    return Census(
        package_files=package_files,
        literal_sites=sites,
        shared_files=shared,
        duplicate_groups=duplicate_groups(every_file),
        cross_package_names=cross_package_names(package_files),
        scenarios=scenarios,
        scenario_readers={scenario: readers[scenario] for scenario in sorted(readers)},
    )


def _relative(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).as_posix()


def _print_files(census: Census, base_dir: Path) -> None:
    report_step("Counted files")
    for package, files in census.package_files.items():
        for fixture in files:
            print(f"  {package} fixture {_relative(fixture.path, base_dir)}")
        for site in census.literal_sites[package]:
            print(f"  {package} inline {_relative(site.path, base_dir)}:{site.line}")
    for fixture in census.shared_files:
        print(f"  shared {_relative(fixture.path, base_dir)}")
    for group in census.duplicate_groups:
        print(f"  duplicate group: {', '.join(_relative(fixture.path, base_dir) for fixture in group)}")
    for name, owners in census.cross_package_names.items():
        print(f"  cross-package name {name}: {', '.join(owners)}")
    for scenario in census.scenarios:
        modules = census.scenario_readers.get(scenario, [])
        read_by = ", ".join(_relative(module, base_dir) for module in modules) or "no test"
        print(f"  corpus entry {scenario}: read by {read_by}")


def _count_text(label: str, key: str, current: Mapping[str, int], baseline: Mapping[str, int] | None) -> str:
    live = current[key]
    if baseline is None:
        return f"{label} {live} (no baseline)"
    # A key the baseline does not name is pinned at zero (the tighten-only semantics of count_ratchet).
    frozen = baseline.get(key, 0)
    return f"{label} {live} (baseline {frozen}, {live - frozen:+d})"


def _print_counts(census: Census, current: Mapping[str, int], baseline: Mapping[str, int] | None) -> None:
    report_step(f"Fixture budget: {len(census.package_files)} package(s)")
    for package in census.package_files:
        files = _count_text(FIXTURE_FILES, package_key(package, FIXTURE_FILES), current, baseline)
        literals = _count_text(INLINE_LITERALS, package_key(package, INLINE_LITERALS), current, baseline)
        print(f"  {package}: {files}, {literals}")
    for key in (DUPLICATE_COPIES, CROSS_PACKAGE_NAMES, TOTAL_FIXTURES):
        print(f"  {_count_text(key, key, current, baseline)}")
    print(f"  {SHARED_FILES} {len(census.shared_files)} (not pinned)")
    print(f"  corpus entries {len(census.scenarios)} ({len(unread_scenarios(census))} read by no test)")


def ratchet_failures(current: Mapping[str, int], baseline: Mapping[str, int]) -> list[str]:
    """One message per count above its baseline, naming the package (when per-package) and both counts."""
    messages: list[str] = []
    for delta in compare(current, baseline, RatchetMode.TIGHTEN_ONLY):
        count = delta.key.rpartition(PACKAGE_KEY_SEPARATOR)[2]
        messages.append(
            f"{delta.key.replace(PACKAGE_KEY_SEPARATOR, ' ')} rose from baseline {delta.frozen} to "
            f"{delta.current}. Fix: {_FIXES[count]}. A fall is banked with -UpdateBaseline; a rise is never "
            "accepted."
        )
    return messages


def unread_scenarios(census: Census) -> list[str]:
    """The corpus entries no package's ``tests/`` names in a ``corpus_project(...)`` call: entries − reads."""
    return [scenario for scenario in census.scenarios if scenario not in census.scenario_readers]


def unread_corpus_failures(census: Census) -> list[str]:
    """One message per corpus entry no test reads, naming it."""
    corpus = f"{SHARED_PACKAGE}/{CORPUS_RELATIVE.as_posix()}"
    return [
        f"corpus entry {scenario!r} ({corpus}) is read by no package's tests/: no module there calls "
        f"{CORPUS_READER}({scenario!r}). Fix: read it from the tests that need the scenario, or delete the "
        "entry together with the corpus files only it reaches."
        for scenario in unread_scenarios(census)
    ]


def _print_failures(failures: Sequence[str]) -> None:
    print()
    for message in failures:
        print(f"FAIL {message}")


def _update_baseline(census: Census, current: Mapping[str, int], baseline_path: Path) -> int:
    """Freeze the first baseline, or tighten an existing one; never write a rise, or while a corpus entry is
    read by no test."""
    existing: dict[str, int] | None = None
    if baseline_path.exists():
        existing = load_counts_json(baseline_path, table_key=BASELINE_TABLE)
    _print_counts(census, current, existing)
    if existing is not None:
        rises = ratchet_failures(current, existing)
        if rises:
            _print_failures(rises)
            print("\n-UpdateBaseline only writes when no count rises; the baseline is unchanged.")
            return EXIT_USAGE
    unread = unread_corpus_failures(census)
    if unread:
        _print_failures(unread)
        return EXIT_VIOLATION
    write_counts_json(baseline_path, current, comment=_BASELINE_COMMENT, table_key=BASELINE_TABLE)
    action = "Froze the first" if existing is None else "Tightened the"
    print(f"\n{action} fixture budget baseline: {len(current)} count(s) at {baseline_path}")
    return EXIT_PASS


def run_budget(base_dir: Path, *, update_baseline: bool, show_files: bool) -> int:
    """Count the fixtures under *base_dir* and compare them with its baseline (or write it).

    Raises:
        FixtureScanError: from ``take_census``.
        ValueError: the baseline exists but is malformed (``count_ratchet``).
    """
    census = take_census(base_dir)
    if show_files:
        _print_files(census, base_dir)
    current = census.counts()
    baseline_path = base_dir / BASELINE_RELATIVE
    if update_baseline:
        return _update_baseline(census, current, baseline_path)
    if not baseline_path.is_file():
        _print_counts(census, current, None)
        print(
            f"\nERROR: fixture budget baseline {baseline_path} does not exist. A missing baseline is not an "
            "empty one. Fix: restore it, or freeze it from the live tree with -UpdateBaseline."
        )
        return EXIT_USAGE
    baseline = load_counts_json(baseline_path, table_key=BASELINE_TABLE)
    _print_counts(census, current, baseline)
    failures = [*ratchet_failures(current, baseline), *unread_corpus_failures(census)]
    if failures:
        _print_failures(failures)
        return EXIT_VIOLATION
    return EXIT_PASS


# --------------------------------------------------------------------------- self-test
# Each check plants a workspace in a temporary directory and runs the real scan on it: no real tree is read.

_ALPHA_INLINE_MODULE: Final = '''"""Module docstring: service Doc {
} is prose here."""

DTRX = "service Inline {\\n}\\n"
DCFG = "config system Shop {\\n}\\n"
PROSE = "a service is not a declaration"


def make(name: str) -> str:
    """service FunctionDoc {
    }"""
    return f"system Shop {{\\n  service Orders {{ }}\\n}} // {name}"
'''

_PLANTED: Final[Mapping[str, str]] = {
    "datrix-alpha/tests/fixtures/orders.dtrx": "// alpha copy\nservice Orders {\n}\n",
    "datrix-alpha/tests/fixtures/system.dtrx": "system Shop {\n}\n",
    "datrix-alpha/tests/fixtures/config/orders.dcfg": "config service Orders {\n  port = 8080 # alpha\n}\n",
    "datrix-alpha/tests/fixtures/broken.dtrx.false": "service {\n",
    "datrix-alpha/tests/fixtures/seed/orders.dseed": "seed Orders { }\n",
    "datrix-alpha/tests/fixtures/tag-red.dtrx": "service Tag {\n  color = 1 # red\n}\n",
    "datrix-alpha/tests/fixtures/tag-blue.dtrx": "service Tag {\n  color = 1 # blue\n}\n",
    "datrix-alpha/tests/fixtures/node_modules/skipped.dtrx": "service Skipped {\n}\n",
    "datrix-alpha/tests/fixtures/notes.txt": "service NotAFixture {\n}\n",
    "datrix-alpha/tests/test_inline.py": _ALPHA_INLINE_MODULE,
    "datrix-alpha/src/datrix_alpha/testkit/builders.py": 'APP = "app Portal {\\n}\\n"\n',
    "datrix-alpha/src/datrix_alpha/runtime.py": 'NOT_TEST_SUPPORT = "service Runtime {\\n}\\n"\n',
    "datrix-beta/tests/fixtures/orders.dtrx": "service   Orders {\n}  /* beta copy */\n",
    "datrix-beta/tests/fixtures/system.dtrx": "system Other {\n}\n",
    "datrix-beta/tests/fixtures/url.dtrx": 'service Links {\n  base = "http://alpha"\n}\n',
    "datrix-beta/tests/fixtures/url-copy.dtrx": 'service Links {\n  base = "http://beta"\n}\n',
    "datrix-beta/tests/fixtures/config/orders.dcfg": "config service Orders {\n  port = 8080 # beta\n}\n",
    "datrix-testing/tests/test_nothing.py": "VALUE = 1\n",
    "datrix-testing/src/datrix_testing/fixtures_data/shared.dtrx": "service Orders {\n}\n",
    "datrix-testing/src/datrix_testing/helpers.py": 'SHARED = "extern service Pay {\\n}\\n"\n',
    "datrix-testing/src/datrix_testing/fixtures_data/corpus/shop.dtrx": "system Store {\n}\n",
    "datrix-testing/src/datrix_testing/fixtures_data/corpus/seeded/system.dtrx": "system Seeded {\n}\n",
    "datrix-alpha/tests/test_shop.py": 'from datrix_testing.corpus import corpus_project\n\nENTRY = corpus_project("shop")\n',
    "datrix-beta/tests/test_seeded.py": (
        'from datrix_testing import corpus\n\nENTRY = corpus.corpus_project(scenario="seeded")\n'
    ),
    "outside/linked-only.dtrx": "service OnlyThroughALink {\n}\n",
}
_ALPHA: Final = "datrix-alpha"
_BETA: Final = "datrix-beta"
_CORPUS: Final = f"{SHARED_PACKAGE}/{CORPUS_RELATIVE.as_posix()}"
# The planted shared fixtures, in walk order (a directory's files before its subdirectories).
_SHARED_PLANTED: Final = [
    "datrix-testing/src/datrix_testing/fixtures_data/shared.dtrx",
    f"{_CORPUS}/shop.dtrx",
    f"{_CORPUS}/seeded/system.dtrx",
]
# An entry no test names: read only from src/ and through a computed name in tests/, neither a read.
_UNREAD_ENTRY: Final[Mapping[str, str]] = {
    f"{_CORPUS}/unread.dtrx": "system Unread {\n}\n",
    "datrix-alpha/src/datrix_alpha/testkit/corpus_reader.py": 'ENTRY = corpus_project("unread")\n',
    "datrix-beta/tests/test_computed.py": 'NAME = "unread"\nENTRY = corpus_project(NAME)\n',
}
_LINK: Final = "datrix-alpha/tests/fixtures/linked"
_LINK_TARGET: Final = "outside"
# The planted inline literals of test_inline.py (DTRX, DCFG and the f-string) and its docstring lines.
_ALPHA_INLINE_LINES: Final = [4, 5, 12]
_ALPHA_DOCSTRING_LINES: Final = frozenset({1, 10})
# The planted total: 12 package fixture files, 5 inline literals (4 in datrix-alpha, 1 in datrix-testing), 3 shared.
_PLANTED_TOTAL: Final = 20
_MOVED_TO_SHARED: Final = 125


@contextlib.contextmanager
def _planted_workspace() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="fixture-budget-selftest-") as tmp:
        root = Path(tmp)
        write_files(root, _PLANTED)
        plant_directory_link(root / _LINK, root / _LINK_TARGET)
        yield root


def _quiet_budget(root: Path, *, update_baseline: bool) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = run_budget(root, update_baseline=update_baseline, show_files=False)
    return code, output.getvalue()


def _check_fixture_files_counted_per_package() -> None:
    with _planted_workspace() as root:
        counts = take_census(root).counts()
    expected = {_ALPHA: 7, _BETA: 5, SHARED_PACKAGE: 0}
    actual = {package: counts[package_key(package, FIXTURE_FILES)] for package in expected}
    assert actual == expected, f"fixture_files per package: expected {expected}, got {actual}"


def _check_skipped_directory_and_link_not_entered() -> None:
    with _planted_workspace() as root:
        census = take_census(root)
        assert (root / _LINK / "linked-only.dtrx").is_file(), "the planted link must reach its target"
        names = {fixture.path.name for files in census.package_files.values() for fixture in files}
    assert "skipped.dtrx" not in names, "a fixture under node_modules/ was counted"
    assert "linked-only.dtrx" not in names, "a fixture reached only through a directory link was counted"
    assert "notes.txt" not in names, "a file of no fixture kind was counted"


def _check_inline_literals_counted() -> None:
    with _planted_workspace() as root:
        census = take_census(root)
        alpha = [(_relative(site.path, root), site.line) for site in census.literal_sites[_ALPHA]]
        testing = [_relative(site.path, root) for site in census.literal_sites[SHARED_PACKAGE]]
    expected_alpha = [("datrix-alpha/tests/test_inline.py", line) for line in _ALPHA_INLINE_LINES]
    expected_alpha.append(("datrix-alpha/src/datrix_alpha/testkit/builders.py", 1))
    assert alpha == expected_alpha, f"alpha inline literals: expected {expected_alpha}, got {alpha}"
    assert testing == ["datrix-testing/src/datrix_testing/helpers.py"], f"datrix_testing literals: {testing}"
    assert census.literal_sites[_BETA] == [], f"beta has no inline literal: {census.literal_sites[_BETA]}"


def _check_docstring_not_counted() -> None:
    tree = ast.parse(_ALPHA_INLINE_MODULE)
    docstrings = [line for line, text in string_literals(tree) if line in _ALPHA_DOCSTRING_LINES]
    assert docstrings == [], f"a docstring was read as a literal at line(s) {docstrings}"
    assert holds_fixture_text("service Doc {\n} is prose"), "the docstring text itself must be fixture text"


def _check_duplicate_copies_counted() -> None:
    with _planted_workspace() as root:
        census = take_census(root)
        groups = [[_relative(fixture.path, root) for fixture in group] for group in census.duplicate_groups]
    expected = [
        ["datrix-alpha/tests/fixtures/config/orders.dcfg", "datrix-beta/tests/fixtures/config/orders.dcfg"],
        [
            "datrix-alpha/tests/fixtures/orders.dtrx",
            "datrix-beta/tests/fixtures/orders.dtrx",
            "datrix-testing/src/datrix_testing/fixtures_data/shared.dtrx",
        ],
    ]
    assert groups == expected, f"duplicate groups: expected {expected}, got {groups}"
    assert census.counts()[DUPLICATE_COPIES] == 3, f"duplicate_copies: {census.counts()[DUPLICATE_COPIES]}"


def _check_comment_markers_inside_strings_and_dtrx_hash_kept() -> None:
    urls = [normalized(f'service Links {{ base = "http://{host}" }}', ".dtrx") for host in ("alpha", "beta")]
    assert urls[0] != urls[1], f"a // inside a string literal was stripped as a comment: {urls}"
    routes = [normalized(f"service Hooks {{ path = '/hooks//{name}' }}", ".dtrx") for name in ("stripe", "paypal")]
    assert routes[0] != routes[1], f"a // inside a single-quoted string literal was stripped as a comment: {routes}"
    tags = [normalized(f"service Tag {{ color = 1 # {name} }}", ".dtrx") for name in ("red", "blue")]
    assert tags[0] != tags[1], f"a # was stripped from a .dtrx file: {tags}"
    assert normalized("a = 1 # note\n", DCFG_KIND) == "a = 1", "a # comment survived in a .dcfg file"


def _check_cross_package_names_exclude_system() -> None:
    with _planted_workspace() as root:
        names = take_census(root).cross_package_names
    expected = {"orders.dcfg": [_ALPHA, _BETA], "orders.dtrx": [_ALPHA, _BETA]}
    assert names == expected, f"cross-package names: expected {expected}, got {names}"


def _check_shared_files_counted() -> None:
    with _planted_workspace() as root:
        shared = [_relative(fixture.path, root) for fixture in take_census(root).shared_files]
    assert shared == _SHARED_PLANTED, f"shared files: expected {_SHARED_PLANTED}, got {shared}"


def _check_corpus_reads_found() -> None:
    with _planted_workspace() as root:
        census = take_census(root)
        readers = {
            scenario: [_relative(module, root) for module in modules]
            for scenario, modules in census.scenario_readers.items()
        }
    assert census.scenarios == ("seeded", "shop"), f"corpus entries: {census.scenarios}"
    expected = {"seeded": ["datrix-beta/tests/test_seeded.py"], "shop": ["datrix-alpha/tests/test_shop.py"]}
    assert readers == expected, f"corpus reads: expected {expected}, got {readers}"
    assert unread_corpus_failures(census) == [], f"every planted entry is read: {unread_corpus_failures(census)}"


def _check_unread_corpus_entry_fails() -> None:
    with _planted_workspace() as root:
        frozen, _ = _quiet_budget(root, update_baseline=True)
        write_files(root, _UNREAD_ENTRY)
        # The entry is also one more shared file: pin the baseline at the new tree so only the read rule can fail.
        write_counts_json(
            root / BASELINE_RELATIVE, take_census(root).counts(), comment=_BASELINE_COMMENT, table_key=BASELINE_TABLE
        )
        code, output = _quiet_budget(root, update_baseline=False)
        refused, _ = _quiet_budget(root, update_baseline=True)
    assert frozen == EXIT_PASS, f"freezing the planted workspace must pass, got {frozen}"
    assert code == EXIT_VIOLATION, f"an unread corpus entry must exit {EXIT_VIOLATION}, got {code}"
    assert "corpus entry 'unread'" in output, f"the failure must name the unread entry: {output}"
    assert "corpus entry 'shop'" not in output, f"a read entry was reported unread: {output}"
    assert "rose from baseline" not in output, f"only the unread entry may fail here: {output}"
    assert refused == EXIT_VIOLATION, f"-UpdateBaseline over an unread entry must exit {EXIT_VIOLATION}, got {refused}"


def _check_missing_corpus_root_refused() -> None:
    with _planted_workspace() as root:
        shutil.rmtree(root / _CORPUS)
        try:
            take_census(root)
        except FixtureScanError as exc:
            assert "corpus" in str(exc), f"the refusal must name the corpus root: {exc}"
            return
    raise AssertionError("a missing corpus root was read as a corpus with no entries")


def _check_ambiguous_corpus_entry_refused() -> None:
    with _planted_workspace() as root:
        write_files(root, {f"{_CORPUS}/shop/system.dtrx": "system StoreRoot {\n}\n"})
        try:
            take_census(root)
        except FixtureScanError as exc:
            assert "'shop'" in str(exc), f"the refusal must name the ambiguous entry: {exc}"
            return
    raise AssertionError("a scenario written in both entry forms was accepted")


def _check_missing_baseline_refused() -> None:
    with _planted_workspace() as root:
        code, output = _quiet_budget(root, update_baseline=False)
    assert code == EXIT_USAGE, f"a missing baseline must exit {EXIT_USAGE}, got {code}"
    assert "does not exist" in output, f"the refusal must say the baseline is missing: {output}"


def _check_count_above_baseline_fails() -> None:
    with _planted_workspace() as root:
        frozen, _ = _quiet_budget(root, update_baseline=True)
        clean, _ = _quiet_budget(root, update_baseline=False)
        write_files(root, {"datrix-beta/tests/fixtures/added.dtrx": "service Added {\n}\n"})
        code, output = _quiet_budget(root, update_baseline=False)
        refused, _ = _quiet_budget(root, update_baseline=True)
        baseline = load_counts_json(root / BASELINE_RELATIVE, table_key=BASELINE_TABLE)
    assert (frozen, clean) == (EXIT_PASS, EXIT_PASS), f"freeze then check must pass, got {(frozen, clean)}"
    assert code == EXIT_VIOLATION, f"a count above the baseline must exit {EXIT_VIOLATION}, got {code}"
    assert "datrix-beta fixture_files rose from baseline 5 to 6" in output, f"the failure must name it: {output}"
    assert refused == EXIT_USAGE, f"-UpdateBaseline over a rise must exit {EXIT_USAGE}, got {refused}"
    assert baseline[package_key(_BETA, FIXTURE_FILES)] == 5, "a refused -UpdateBaseline rewrote the baseline"


def _check_fall_is_banked() -> None:
    with _planted_workspace() as root:
        _quiet_budget(root, update_baseline=True)
        (root / "datrix-beta/tests/fixtures/url-copy.dtrx").unlink()
        code, _ = _quiet_budget(root, update_baseline=True)
        baseline = load_counts_json(root / BASELINE_RELATIVE, table_key=BASELINE_TABLE)
    assert code == EXIT_PASS, f"-UpdateBaseline over a fall must exit {EXIT_PASS}, got {code}"
    assert baseline[package_key(_BETA, FIXTURE_FILES)] == 4, f"the fall was not banked: {baseline}"
    assert baseline[TOTAL_FIXTURES] == _PLANTED_TOTAL - 1, f"the total's fall was not banked: {baseline}"


def _check_total_fixtures_counted() -> None:
    with _planted_workspace() as root:
        counts = take_census(root).counts()
    assert counts[TOTAL_FIXTURES] == _PLANTED_TOTAL, f"total_fixtures: expected {_PLANTED_TOTAL}, got {counts}"
    assert SHARED_FILES not in counts, f"shared_files must not be pinned: {counts}"


def _check_total_fixtures_rise_fails() -> None:
    added = {f"{SHARED_PACKAGE}/{SHARED_FIXTURES_RELATIVE.as_posix()}/added.dtrx": "service SharedAdded {\n}\n"}
    with _planted_workspace() as root:
        _quiet_budget(root, update_baseline=True)
        write_files(root, added)
        code, output = _quiet_budget(root, update_baseline=False)
        refused, _ = _quiet_budget(root, update_baseline=True)
        baseline = load_counts_json(root / BASELINE_RELATIVE, table_key=BASELINE_TABLE)
    assert code == EXIT_VIOLATION, f"a rise of total_fixtures must exit {EXIT_VIOLATION}, got {code}"
    rise = f"{TOTAL_FIXTURES} rose from baseline {_PLANTED_TOTAL} to {_PLANTED_TOTAL + 1}"
    assert rise in output, f"the failure must name the total: {output}"
    assert output.count("rose from baseline") == 1, f"only the total may rise for a new shared file: {output}"
    assert refused == EXIT_USAGE, f"-UpdateBaseline over a rise of the total must exit {EXIT_USAGE}, got {refused}"
    assert baseline[TOTAL_FIXTURES] == _PLANTED_TOTAL, "a refused -UpdateBaseline rewrote the total"


def _check_package_fixtures_moved_to_shared_pass() -> None:
    # More shared files than the whole planted tree holds, each moved out of a package, so the total holds.
    moved = {f"orders-{index}.dtrx": f"service Moved{index} {{\n}}\n" for index in range(_MOVED_TO_SHARED)}
    shared_dir = f"{SHARED_PACKAGE}/{SHARED_FIXTURES_RELATIVE.as_posix()}"
    with _planted_workspace() as root:
        write_files(root, {f"{_BETA}/tests/fixtures/moved/{name}": text for name, text in moved.items()})
        frozen, _ = _quiet_budget(root, update_baseline=True)
        shutil.rmtree(root / _BETA / "tests" / "fixtures" / "moved")
        write_files(root, {f"{shared_dir}/moved/{name}": text for name, text in moved.items()})
        code, output = _quiet_budget(root, update_baseline=False)
        shared = len(take_census(root).shared_files)
    assert frozen == EXIT_PASS, f"freezing the planted workspace must pass, got {frozen}"
    assert shared == len(_SHARED_PLANTED) + _MOVED_TO_SHARED, f"the moved files must be shared files: {shared}"
    assert code == EXIT_PASS, f"moving package fixtures into the shared set must exit {EXIT_PASS}, got {code}"
    assert "rose from baseline" not in output, f"a move into the shared set raised a count: {output}"


def _check_missing_shared_directory_refused() -> None:
    with _planted_workspace() as root:
        shutil.rmtree(root / SHARED_PACKAGE / SHARED_FIXTURES_RELATIVE)
        try:
            take_census(root)
        except FixtureScanError as exc:
            assert "fixtures_data" in str(exc), f"the refusal must name the directory: {exc}"
            return
    raise AssertionError("a missing shared fixture directory was read as zero shared files")


def _check_unparsable_test_module_refused() -> None:
    with _planted_workspace() as root:
        write_files(root, {"datrix-beta/tests/test_broken.py": "def broken(:\n"})
        try:
            take_census(root)
        except FixtureScanError as exc:
            assert "test_broken.py" in str(exc), f"the refusal must name the module: {exc}"
            return
    raise AssertionError("an unparsable test module was skipped instead of refused")


_SELF_TEST_CHECKS: Final[list[NamedCheck]] = named_checks(
    [
        _check_fixture_files_counted_per_package,
        _check_skipped_directory_and_link_not_entered,
        _check_inline_literals_counted,
        _check_docstring_not_counted,
        _check_duplicate_copies_counted,
        _check_comment_markers_inside_strings_and_dtrx_hash_kept,
        _check_cross_package_names_exclude_system,
        _check_shared_files_counted,
        _check_corpus_reads_found,
        _check_unread_corpus_entry_fails,
        _check_missing_corpus_root_refused,
        _check_ambiguous_corpus_entry_refused,
        _check_missing_baseline_refused,
        _check_count_above_baseline_fails,
        _check_fall_is_banked,
        _check_total_fixtures_counted,
        _check_total_fixtures_rise_fails,
        _check_package_fixtures_moved_to_shared_pass,
        _check_missing_shared_directory_refused,
        _check_unparsable_test_module_refused,
    ]
)


def build_parser() -> argparse.ArgumentParser:
    """The gate's options: exactly the wrapper's parameters, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description="Fixture budget ratchet: count and cap the .dtrx/.dcfg test fixtures",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--show-files", action="store_true",
        help="Print every counted file, inline literal site, duplicate group and cross-package name.",
    )
    parser.add_argument("--base-dir", default="", help="Workspace root (default: the workspace)")
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Freeze the first baseline, or tighten it; refused when any count rises.",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run only the harness self-test, the census checks over a planted workspace and the wrapper seam check.",
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Print the interpreter and the arguments."
    )
    return parser


def _base_dir(raw: str) -> Path:
    base_dir = Path(raw).resolve() if raw else WORKSPACE_DIR
    if not base_dir.is_dir():
        raise UsageError(f"-BaseDir {base_dir} is not a directory. Expected the workspace root holding datrix-*.")
    return base_dir


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, or the census once the census checks have passed."""
    if args.debug:
        print_command()
    if args.self_test:
        code = wrappers.run_self_test(
            [wrappers.self_test_check("harness_self_test", harness_self_test), *_SELF_TEST_CHECKS],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.RATCHET_GATES_DIR,
        )
        return EXIT_PASS if code == EXIT_PASS else EXIT_USAGE
    base_dir = _base_dir(args.base_dir)
    report_step("Self-test: fixture budget census checks")
    if not run_checks(_SELF_TEST_CHECKS):
        print("\nERROR: self-test failed; the census is not trusted for a real scan. Fix the gate first.")
        return EXIT_USAGE
    try:
        return run_budget(base_dir, update_baseline=args.update_baseline, show_files=args.show_files)
    except (FixtureScanError, ValueError) as exc:
        print(f"\nERROR: {exc}")
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
