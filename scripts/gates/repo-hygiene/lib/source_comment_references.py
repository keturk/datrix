"""Source comment-reference gate.

A comment or docstring in framework source that names a module is a pointer
nothing follows: imports are proven by importing, but a module that moves, is
split or is renamed leaves every comment naming it pointing at code that is not
there. This gate resolves every module a framework ``src/`` comment or
docstring cites.

Prose is read, never code: comment tokens (``tokenize``) and string-literal
expression statements (module, class and function docstrings, attribute
docstrings). An ordinary string literal is code and is not read as prose.

Two citation shapes, both resolved against what exists, never a hand-written
list:

  - Dotted references. Every ``datrix_*`` dotted reference resolves through the
    shared ``datrix_scripts.framework_references`` resolver (importable module
    prefix, then members). A reference whose first segment is no importable
    package is read relative to the citing module's own top-level package
    (``datrix_model.ui`` written inside ``datrix_common`` is
    ``datrix_common.datrix_model.ui``) and must resolve there.
  - File citations. ``foo.py`` or ``a/b/foo.py`` (a ``.py.j2`` template name is
    not a module citation and is not read):

      * a citation anchored at a framework repository (``datrix-codegen-x/...``,
        ``datrix/scripts/...``) or an import name (``datrix_codegen_x/...``)
        must name a file that exists in the workspace;
      * a citation anchored at an importable third-party package
        (``pygls/io_.py``) must name a file under that package;
      * a bare or relative citation must name a ``.py`` file of the citing
        package or of a package in its runtime dependency closure (read from
        each ``pyproject.toml``). A bare name is the reader's shorthand for
        "the module you can reach from here"; a module of any other package is
        cited by its anchored path or its dotted import path, which this gate
        then resolves. Without that rule a stale bare name passes whenever an
        unrelated package happens to own a file of the same name.

    A citation that resolves none of those ways still passes when it names a
    file the generators emit: a ``*.py.j2`` template's output name, a genDSL
    output path (``=> "cdk/app.py"``), or a code string literal whose whole
    value is a ``*.py`` path (``"settings_loader.py"``). Generated files are
    cited in prose constantly (``deploy.py``, ``auth.py``) and are not
    framework modules. A longer string that only mentions a ``.py`` name (an
    error message's "Fix: edit x.py") names a framework module, not an output,
    and excuses nothing. A citation inside a URL is not a module citation and
    is skipped.

The terminal state is zero: there is no baseline and no exemption file. A
citation that does not resolve is rewritten -- to the module's current home,
to its anchored or dotted path, or to a description of the behaviour.

Built-in non-vacuity self-test, every invocation: a planted three-package
workspace carries every passing shape and every failing shape (a bare name
owned only by a package outside the dependency closure, a name owned by no
package, a name only an error message mentions, an anchored path to a missing
file, a removed dotted module, a missing member), and each must be classified
correctly before the live scan is trusted. The live scan must also see at least one citation of each shape.

Usage:
    python source_comment_references.py
    python source_comment_references.py --debug
    python source_comment_references.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import logging
import re
import sys
import tempfile
import tokenize
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.framework_references import FRAMEWORK_REFERENCE, ReferenceResolver
from datrix_scripts.framework_repos import SHOWCASE_REPO_NAME
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.pyproject_deps import (
    DATRIX_PREFIX,
    discover_packages,
    parse_package_name,
    read_project_dependencies,
)

logger = logging.getLogger(__name__)

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_USAGE: Final = 2

SCRATCH_ROOT: Final[Path] = WORKSPACE_DIR / ".tmp"
SOURCE_DIR_NAME: Final = "src"
PYPROJECT_NAME: Final = "pyproject.toml"
PYTHON_SUFFIX: Final = ".py"
TEMPLATE_SUFFIX: Final = ".py.j2"
IMPORT_NAME_PREFIX: Final = "datrix_"
URL_SCHEME_SEPARATOR: Final = "://"
#: Characters that mark a path segment as a placeholder or glob, not a name.
PLACEHOLDER_CHARACTERS: Final = frozenset("<>{}*$%")
#: What delimits a token that may hold a path.
TOKEN_DELIMITERS: Final = (" ", "\t", "`", "'", '"', "(", "[")

#: Directory names never walked when collecting a repository's ``.py`` files.
SKIPPED_DIR_NAMES: Final = frozenset(
    {"node_modules", "__pycache__", "build", "dist", ".test_results"}
)

#: A file citation: optional ``segment/`` path, then ``stem.py``. Never read
#: when it continues as ``.py.j2`` or ``.pyc``, and never started inside a
#: longer token (a ``{placeholder}_x.py``, a ``*_x.py`` glob, ``<x>.py``, a
#: dotted or hyphenated name, a Windows path segment).
FILE_CITATION: Final = re.compile(
    r"(?<![\w.\\{}<>*$%@-])"
    r"(?P<prefix>(?:[A-Za-z_][A-Za-z0-9_.-]*/)*)"
    r"(?P<stem>[A-Za-z_][A-Za-z0-9_]*)\.py(?![\w.])"
)
#: A code string literal (or f-string fragment) whose whole value is a ``*.py``
#: path: an emitted file name. A longer string that merely mentions a ``.py``
#: name -- an error message's "Fix: edit dependency_tables.py" -- names a
#: framework module, not an output, and must not excuse a citation of it.
CODE_STRING_FILE: Final = re.compile(r"(?:[^\s/]*/)*(?P<stem>[A-Za-z_][A-Za-z0-9_]*)\.py")
#: A genDSL output path: ``=> "cdk/stacks/vpc_stack.py"``.
GENDSL_OUTPUT_PATH: Final = re.compile(r"=>\s*\"([^\"]+)\"")
#: A quoted ``*.py.j2`` template name: the template renders ``<stem>.py``.
QUOTED_TEMPLATE: Final = re.compile(r"[\"'](?:[^\"'\s]*/)?([A-Za-z_][A-Za-z0-9_]*)\.py\.j2[\"']")


# ---------------------------------------------------------------------------
# Prose extraction
# ---------------------------------------------------------------------------


def _docstring_nodes(tree: ast.Module) -> list[ast.Constant]:
    """Every string-literal expression statement (a docstring of any kind)."""
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]


def prose_lines(text: str, tree: ast.Module) -> list[tuple[int, str]]:
    """``(line, text)`` for every comment and every docstring line of a module."""
    lines: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            lines.append((token.start[0], token.string))
    for node in _docstring_nodes(tree):
        for offset, line in enumerate(str(node.value).splitlines()):
            lines.append((node.lineno + offset, line))
    return sorted(lines)


def emitted_names_in_module(tree: ast.Module) -> set[str]:
    """Stems of the ``*.py`` files a module's code strings and genDSL name."""
    docstrings = {id(node) for node in _docstring_nodes(tree)}
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        for match in GENDSL_OUTPUT_PATH.finditer(node.value):
            names.add(Path(match.group(1)).name.removesuffix(PYTHON_SUFFIX))
        for match in QUOTED_TEMPLATE.finditer(node.value):
            names.add(match.group(1))
        emitted_file = CODE_STRING_FILE.fullmatch(node.value)
        if emitted_file is not None and id(node) not in docstrings:
            names.add(emitted_file.group("stem"))
    return names


# ---------------------------------------------------------------------------
# Workspace model
# ---------------------------------------------------------------------------


def repository_python_files(repo: Path) -> list[str]:
    """Every ``.py`` file of *repo*, repo-relative POSIX, skipping hidden and build dirs."""
    found: list[str] = []
    pending = [repo]
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            if entry.is_dir():
                if not entry.name.startswith(".") and entry.name not in SKIPPED_DIR_NAMES:
                    pending.append(entry)
            elif entry.suffix == PYTHON_SUFFIX:
                found.append(entry.relative_to(repo).as_posix())
    return sorted(found)


def dependency_closure(package: str, dependencies: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """*package* plus every framework package it reaches through runtime dependencies."""
    reached = {package}
    pending = [package]
    while pending:
        for dependency in dependencies[pending.pop()]:
            if dependency not in reached:
                reached.add(dependency)
                pending.append(dependency)
    return frozenset(reached)


@dataclass(frozen=True)
class Workspace:
    """What a citation can resolve against."""

    #: Framework package name -> its repository root.
    packages: Mapping[str, Path]
    #: Framework package name -> the framework packages its pyproject declares.
    dependencies: Mapping[str, frozenset[str]]
    #: Repository name (packages plus the showcase) -> its ``.py`` files, repo-relative.
    repository_files: Mapping[str, tuple[str, ...]]
    #: Stems of every file the generators emit.
    emitted_names: frozenset[str]
    #: Parsed sources of every package's ``src/`` tree.
    sources: Mapping[Path, tuple[str, ast.Module]] = field(repr=False)


def _framework_dependencies(packages: Mapping[str, Path]) -> dict[str, frozenset[str]]:
    dependencies: dict[str, frozenset[str]] = {}
    for name, root in packages.items():
        declared = {
            parse_package_name(spec)
            for spec in read_project_dependencies(root / PYPROJECT_NAME)
        }
        dependencies[name] = frozenset(
            dependency
            for dependency in declared
            if dependency.startswith(DATRIX_PREFIX) and dependency in packages
        )
    return dependencies


def load_workspace(workspace_root: Path) -> Workspace:
    """Parse every framework package's ``src/`` tree and index what citations can name."""
    packages = {
        name: root
        for name, root in discover_packages(workspace_root).items()
        if (root / SOURCE_DIR_NAME).is_dir()
    }
    sources: dict[Path, tuple[str, ast.Module]] = {}
    emitted: set[str] = set()
    for root in packages.values():
        source_root = root / SOURCE_DIR_NAME
        emitted.update(
            template.name.removesuffix(TEMPLATE_SUFFIX)
            for template in source_root.rglob(f"*{TEMPLATE_SUFFIX}")
        )
        for path in sorted(source_root.rglob(f"*{PYTHON_SUFFIX}")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
            sources[path] = (text, tree)
            emitted.update(emitted_names_in_module(tree))
    repositories = dict(packages)
    showcase = workspace_root / SHOWCASE_REPO_NAME
    if showcase.is_dir():
        repositories[SHOWCASE_REPO_NAME] = showcase
    return Workspace(
        packages=packages,
        dependencies=_framework_dependencies(packages),
        repository_files={
            name: tuple(repository_python_files(root)) for name, root in repositories.items()
        },
        emitted_names=frozenset(emitted),
        sources=sources,
    )


# ---------------------------------------------------------------------------
# Citation resolution
# ---------------------------------------------------------------------------


def _ends_with_path(files: Iterable[str], cited: str) -> bool:
    suffix = f"/{cited}"
    return any(candidate == cited or candidate.endswith(suffix) for candidate in files)


def _third_party_file_exists(first_segment: str, remainder: str) -> bool:
    """Whether an importable non-framework package *first_segment* holds *remainder*."""
    if first_segment.startswith(IMPORT_NAME_PREFIX):
        return False
    try:
        spec = importlib.util.find_spec(first_segment)
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.submodule_search_locations:
        return False
    return any(
        (Path(location) / remainder).is_file() for location in spec.submodule_search_locations
    )


def _anchored_citation_resolves(cited: str, workspace: Workspace) -> bool | None:
    """Resolve a citation anchored at a repository, import name or third-party package.

    Returns ``None`` when the citation carries no such anchor. A first segment
    that is merely importable (a ``tests`` package on the path) without holding
    the file is no anchor: the citation is repository-relative and falls
    through to the closure check.
    """
    first, _, remainder = cited.partition("/")
    if not remainder:
        return None
    if first in workspace.repository_files:
        return _ends_with_path(workspace.repository_files[first], remainder)
    if first.startswith(IMPORT_NAME_PREFIX):
        return any(
            _ends_with_path(files, cited) for files in workspace.repository_files.values()
        )
    if _third_party_file_exists(first, remainder):
        return True
    return None


def citation_resolves(cited: str, package: str, workspace: Workspace) -> bool:
    """Whether the file citation *cited*, written in *package*'s source, resolves."""
    anchored = _anchored_citation_resolves(cited, workspace)
    if anchored:
        return True
    if anchored is None:
        reachable = dependency_closure(package, workspace.dependencies)
        if any(_ends_with_path(workspace.repository_files[name], cited) for name in reachable):
            return True
    return Path(cited).name.removesuffix(PYTHON_SUFFIX) in workspace.emitted_names


def _token_head(line: str, start: int) -> str:
    """The part of the whitespace/quote-delimited token on *line* that precedes *start*."""
    token_start = max(line.rfind(delimiter, 0, start) for delimiter in TOKEN_DELIMITERS) + 1
    return line[token_start:start]


def file_citations(line: str) -> Iterator[str]:
    """Every file citation on a prose line, path separators normalised to ``/``.

    A match whose token starts earlier with a URL scheme or a placeholder
    segment (``datrix-codegen-<platform>/tests/...``,
    ``{package}/workers/x.py``) is part of a URL or a path pattern, not a
    module citation.
    """
    normalised = line.replace("\\", "/")
    for match in FILE_CITATION.finditer(normalised):
        head = _token_head(normalised, match.start())
        if URL_SCHEME_SEPARATOR in head or PLACEHOLDER_CHARACTERS.intersection(head):
            continue
        yield f"{match.group('prefix')}{match.group('stem')}{PYTHON_SUFFIX}"


@dataclass(frozen=True)
class Violation:
    """One citation that does not resolve."""

    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


@dataclass
class ScanResult:
    """Counts and violations of one scan."""

    dotted_seen: int = 0
    files_seen: int = 0
    violations: list[Violation] = field(default_factory=list)


def _closure_text(package: str, workspace: Workspace) -> str:
    return ", ".join(sorted(dependency_closure(package, workspace.dependencies)))


def _top_level_importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def dotted_unresolved_reason(
    reference: str, import_root: str, resolver: ReferenceResolver
) -> str | None:
    """Why *reference*, written in a module under *import_root*, resolves neither absolutely
    nor relative to *import_root*; ``None`` when it resolves."""
    reason = resolver.unresolved_reason(reference)
    if reason is None:
        return None
    first_segment = reference.split(".", 1)[0]
    if first_segment == import_root or _top_level_importable(first_segment):
        return reason
    if resolver.unresolved_reason(f"{import_root}.{reference}") is None:
        return None
    return f"{reason}, and '{import_root}.{reference}' does not resolve either"


def scan_module(
    path: Path,
    package: str,
    workspace: Workspace,
    resolver: ReferenceResolver,
    result: ScanResult,
) -> None:
    """Resolve every dotted reference and file citation in one module's prose."""
    text, tree = workspace.sources[path]
    import_root = path.relative_to(workspace.packages[package] / SOURCE_DIR_NAME).parts[0]
    for line_number, line in prose_lines(text, tree):
        for match in FRAMEWORK_REFERENCE.finditer(line):
            result.dotted_seen += 1
            reason = dotted_unresolved_reason(match.group(0), import_root, resolver)
            if reason is not None:
                result.violations.append(
                    Violation(
                        path,
                        line_number,
                        f"unresolved module reference '{match.group(0)}' ({reason}). Fix: "
                        f"name the module that defines it now, or describe the behaviour in "
                        f"words.",
                    )
                )
        for cited in file_citations(line):
            result.files_seen += 1
            if not citation_resolves(cited, package, workspace):
                result.violations.append(
                    Violation(
                        path,
                        line_number,
                        f"'{cited}' is no module of {package} or of the packages it depends "
                        f"on ({_closure_text(package, workspace)}) and no generated file "
                        f"name. Fix: cite a module of another package by its anchored path "
                        f"(datrix-<package>/src/...) or dotted import path, point at the "
                        f"module's current home, or describe the behaviour in words.",
                    )
                )


def scan_workspace(workspace: Workspace, resolver: ReferenceResolver) -> ScanResult:
    """Scan the prose of every framework package's ``src/`` tree."""
    result = ScanResult()
    for package, root in sorted(workspace.packages.items()):
        source_root = root / SOURCE_DIR_NAME
        for path in workspace.sources:
            if path.is_relative_to(source_root):
                scan_module(path, package, workspace, resolver, result)
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SELF_TEST_PACKAGES: Final[Mapping[str, tuple[str, ...]]] = {
    "datrix-fixture-core": (),
    "datrix-fixture-language": ("datrix-fixture-core",),
    "datrix-fixture-platform": ("datrix-fixture-core",),
}
_LIVE_RESOLVING_REFERENCE: Final = "datrix_scripts.framework_references.ReferenceResolver"
_LIVE_REMOVED_REFERENCE: Final = "datrix_scripts.no_such_module_here.ReferenceResolver"
_LIVE_MISSING_MEMBER: Final = "datrix_scripts.framework_references.no_such_member_here"
_LIVE_CHAIN_INTERIOR: Final = "datrix_scripts.datrix_no_such_segment.x"
_LIVE_INSTANCE_ATTRIBUTE: Final = "datrix_scripts.framework_references.ReferenceResolver._verdicts"
#: A Pydantic field with no class attribute, on live framework source.
_LIVE_MODEL_FIELD: Final = "datrix_common.config.datasource.models.PubsubConfig.engine"

#: The citing module, in datrix-fixture-language. Each entry: (prose line, must fail).
_SELF_TEST_PROSE: Final[tuple[tuple[str, bool], ...]] = (
    ("# Own module: ``language_spec.py``.", False),
    ("# Dependency module: ``naming.py``.", False),
    ("# Own test file, first segment importable elsewhere: ``tests/unit/test_spec.py``.", False),
    ("# Owned only outside the closure: ``resource_mapper.py``'s ``resolve``.", True),
    ("# Owned by nobody: extracted from ``_gone_monolith.py``.", True),
    ("# Anchored: ``datrix-fixture-platform/src/datrix_fixture_platform/resource_mapper.py``.", False),
    ("# Anchored import path: ``datrix_fixture_platform/resource_mapper.py``.", False),
    ("# Anchored but missing: ``datrix-fixture-platform/src/datrix_fixture_platform/gone.py``.", True),
    ("# Emitted by a template: the generated ``deploy.py``.", False),
    ("# Emitted by genDSL: ``cdk/app.py``.", False),
    ("# Emitted by a code string: ``settings_loader.py``.", False),
    ("# Only an error message names it: ``_gone_code.py``.", True),
    ("# Template name, not a module: ``deploy.py.j2``.", False),
    (
        "# Placeholder: ``{block}_client.py``, ``workers/*_handler.py``, "
        "``datrix-codegen-<platform>/tests/unit/test_gone.py``.",
        False,
    ),
    ("# URL: https://example.invalid/tree/main/gone_remote.py", False),
    (f"# Dotted, resolving: ``{_LIVE_RESOLVING_REFERENCE}``.", False),
    (f"# Dotted, removed module: ``{_LIVE_REMOVED_REFERENCE}``.", True),
    (f"# Dotted, missing member: ``{_LIVE_MISSING_MEMBER}``.", True),
    (f"# Dotted, chain interior is not a reference: ``x.{_LIVE_CHAIN_INTERIOR}``.", False),
    (f"# Dotted, instance attribute set in __init__: ``{_LIVE_INSTANCE_ATTRIBUTE}``.", False),
    (f"# Dotted, model field: ``{_LIVE_MODEL_FIELD}``.", False),
)

#: A module planted under the live ``datrix_common`` import root, so a
#: package-relative reference resolves against real source. Each entry:
#: (prose line, must fail).
_SELF_TEST_RELATIVE_IMPORT_ROOT: Final = "datrix_common"
_SELF_TEST_RELATIVE_PROSE: Final[tuple[tuple[str, bool], ...]] = (
    ("# Package-relative, resolving: ``datrix_model.containers``.", False),
    ("# Package-relative, missing: ``datrix_model.no_such_module_here``.", True),
)

_SELF_TEST_PLATFORM_MODULE: Final = '''"""Fixture platform module."""

OUTPUT = "settings_loader.py"


def emitter() -> None:
    """
    builder fixture.emit_app => "cdk/app.py";
    """
'''

#: Five dotted references on the citing module's prose (the chain interior is
#: none) and two package-relative ones.
_SELF_TEST_DOTTED_SEEN: Final = 7
#: Twelve file citations on the citing module's prose plus the platform
#: module's genDSL output path. A code string literal is not prose and is
#: never counted.
_SELF_TEST_FILES_SEEN: Final = 13


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _prose_module(docstring: str, prose: tuple[tuple[str, bool], ...], tail: str) -> str:
    body = "\n".join(line for line, _ in prose)
    return f'"""{docstring}"""\n\n{body}\n{tail}'


def _plant_workspace(root: Path) -> tuple[Path, Path]:
    """Plant the three-package fixture workspace; returns the two citing modules' paths."""
    for package, dependencies in _SELF_TEST_PACKAGES.items():
        declared = ", ".join(f'"{dependency}>=0"' for dependency in dependencies)
        _write(
            root / package / PYPROJECT_NAME,
            f'[project]\nname = "{package}"\nversion = "0"\ndependencies = [{declared}]\n',
        )
    _write(root / "datrix-fixture-core/src/datrix_fixture_core/naming.py", '"""Naming."""\n')
    _write(root / "datrix-fixture-language/tests/unit/test_spec.py", '"""Spec test."""\n')
    platform = root / "datrix-fixture-platform/src/datrix_fixture_platform"
    _write(platform / "resource_mapper.py", _SELF_TEST_PLATFORM_MODULE)
    _write(platform / "templates/deploy.py.j2", "# template\n")
    citing = root / "datrix-fixture-language/src/datrix_fixture_language/language_spec.py"
    _write(
        citing,
        _prose_module("Fixture citing module.", _SELF_TEST_PROSE, '\nMESSAGE = "see _gone_code.py"\n'),
    )
    relative = root / f"datrix-fixture-core/src/{_SELF_TEST_RELATIVE_IMPORT_ROOT}/relative.py"
    _write(relative, _prose_module("Fixture relative module.", _SELF_TEST_RELATIVE_PROSE, ""))
    return citing, relative


def _failing_lines(path: Path, prose: tuple[tuple[str, bool], ...]) -> set[tuple[str, int]]:
    """``(path, line)`` of each failing prose entry; prose starts on line 3."""
    first_prose_line = 3
    return {
        (str(path), first_prose_line + index) for index, (_, fails) in enumerate(prose) if fails
    }


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run_self_test() -> list[str]:
    """Prove every shape is classified correctly; returns the failures (empty = sound)."""
    failures: list[str] = []
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH_ROOT) as scratch:
        root = Path(scratch)
        citing, relative = _plant_workspace(root)
        workspace = load_workspace(root)
        result = scan_workspace(workspace, ReferenceResolver())
    expected = _failing_lines(citing, _SELF_TEST_PROSE) | _failing_lines(
        relative, _SELF_TEST_RELATIVE_PROSE
    )
    flagged = {(str(violation.path), violation.line) for violation in result.violations}
    _expect(
        flagged == expected and len(result.violations) == len(expected),
        f"flagged {sorted(flagged)}, expected exactly {sorted(expected)}: {result.violations}",
        failures,
    )
    _expect(
        result.dotted_seen == _SELF_TEST_DOTTED_SEEN,
        f"saw {result.dotted_seen} dotted references, expected {_SELF_TEST_DOTTED_SEEN}",
        failures,
    )
    _expect(
        result.files_seen == _SELF_TEST_FILES_SEEN,
        f"saw {result.files_seen} file citations, expected {_SELF_TEST_FILES_SEEN}",
        failures,
    )
    return failures


# ---------------------------------------------------------------------------
# Live run
# ---------------------------------------------------------------------------


def run_live() -> int:
    """Scan the real workspace; returns the exit code."""
    workspace = load_workspace(WORKSPACE_DIR)
    if not workspace.packages:
        print(f"ERROR: no datrix-* package with a src/ tree under {WORKSPACE_DIR}.")
        return EXIT_USAGE
    result = scan_workspace(workspace, ReferenceResolver())
    if result.dotted_seen == 0 or result.files_seen == 0:
        print(
            f"ERROR: saw {result.dotted_seen} dotted reference(s) and {result.files_seen} file "
            f"citation(s) in {len(workspace.sources)} module(s) -- a matcher that sees nothing "
            f"proves nothing."
        )
        return EXIT_USAGE
    print(
        f"Source comment references: {len(workspace.sources)} module(s) in "
        f"{len(workspace.packages)} package(s); {result.dotted_seen} dotted reference(s), "
        f"{result.files_seen} file citation(s)"
    )
    for violation in result.violations:
        print(f"VIOLATION: {violation}")
    if result.violations:
        print(f"Source comment-reference gate FAILED: {len(result.violations)} violation(s)")
        return EXIT_FAIL
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    failures = run_self_test()
    if failures:
        for failure in failures:
            print(f"SELF-TEST FAILURE: {failure}")
        return EXIT_USAGE
    print("Self-test passed")
    if args.self_test:
        return EXIT_OK
    return run_live()


if __name__ == "__main__":
    sys.exit(main())
