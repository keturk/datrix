"""No import-time registration: importing a framework module registers nothing.

A registry filled as a side effect of importing a module answers differently
depending on what happened to be imported first, and a reader that saw only part
of the imports gets part of the answer. Registries are handed to the run as
values instead (a declared tuple, a plugin's own declaration). This gate keeps the
side-effect shape from coming back, over every ``src/`` tree of every ``datrix-*``
package on disk, parsed with ``ast``:

* a call statement executed on import (in the module body, or in an ``if``,
  ``for``, ``while``, ``try``, ``with`` or ``class`` body beneath it -- never inside
  a function) whose callee name contains ``register``; an assignment from such a
  call is a value the module keeps, not a call statement, and is not reported;
* an ``import`` carrying ``# noqa: F401`` whose comment mentions registration --
  an import kept only for what importing it does.

The terminal state is zero: there is no baseline and no allowlist.

Built-in non-vacuity self-test, every invocation: a planted ``src/`` tree must be
reported at exactly the planted lines, and its clean shapes and its ``tests/`` tree
not at all.

Run it through ``gates/repo-hygiene/no-import-registration-gate.ps1`` or its ``.sh`` twin; it runs in gate
mode (``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] no-import-registration PASSED|FAILED exit=<n> log=<path>`` verdict last.
"""

from __future__ import annotations

import argparse
import ast
import io
import logging
import re
import sys
import tempfile
import textwrap
import tokenize
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import (
    check_requested_roots_split_on_commas,
    report_by_printing,
    requested_roots,
    roots_gate_parser,
)
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "no-import-registration"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.no_import_registration"
WRAPPER: Final = "no-import-registration-gate"

_EXIT_OK: Final[int] = 0
_EXIT_FINDINGS: Final[int] = 1
_EXIT_GATE_BROKEN: Final[int] = 2

#: A callee whose name holds this word registers something.
REGISTER_WORD: Final[str] = "register"

#: The comment an import kept only for its side effect carries.
NOQA_UNUSED_IMPORT: Final[re.Pattern[str]] = re.compile(r"#\s*noqa\s*:\s*[^#]*\bF401\b", re.IGNORECASE)

#: Registration, in any of its spellings (register, registers, registration, registry).
REGISTRATION_WORDS: Final[re.Pattern[str]] = re.compile(r"regist", re.IGNORECASE)

#: Package subtree the gate scans.
SOURCE_SUBTREE: Final[str] = "src"

#: Directories under a source tree that hold no framework source.
SKIP_DIRS: Final[frozenset[str]] = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"})

#: Statement kinds whose bodies run on import, besides the module body itself.
_IMPORT_TIME_BLOCKS: Final[tuple[type[ast.stmt], ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.ClassDef,
    ast.Match,
)

#: Kind label of a module-level registration call.
KIND_CALL: Final[str] = "import-time-register-call"
#: Kind label of a registration-only import.
KIND_IMPORT: Final[str] = "registration-import"


class GateInputError(Exception):
    """A source file the gate must read cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One import-time registration."""

    path: Path
    line: int
    kind: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


def _callee_name(call: ast.Call) -> str:
    """The called name: ``f`` of ``f()``, ``g`` of ``a.b.g()``; empty for any other callee."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _child_bodies(node: ast.stmt) -> Iterator[list[ast.stmt]]:
    """The statement lists beneath *node* that run when the module is imported."""
    if isinstance(node, ast.Match):
        for case in node.cases:
            yield case.body
        return
    for field in ("body", "orelse", "finalbody"):
        body = getattr(node, field, None)
        if body:
            yield body
    for handler in getattr(node, "handlers", ()):
        yield handler.body


def _import_time_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Every statement of *body* that runs on import, nested blocks included, functions excluded."""
    for statement in body:
        yield statement
        if isinstance(statement, _IMPORT_TIME_BLOCKS):
            for child in _child_bodies(statement):
                yield from _import_time_statements(child)


def _register_calls(path: Path, tree: ast.Module) -> list[Finding]:
    findings: list[Finding] = []
    for statement in _import_time_statements(tree.body):
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
            continue
        name = _callee_name(statement.value)
        if REGISTER_WORD in name.lower():
            findings.append(Finding(path, statement.lineno, KIND_CALL, f"{name}(...) runs when the module is imported"))
    return findings


def _comments_by_line(source: str) -> dict[int, str]:
    comments: dict[int, str] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comments[token.start[0]] = token.string
    return comments


def _registration_imports(path: Path, tree: ast.Module, source: str) -> list[Finding]:
    comments = _comments_by_line(source)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        end = node.end_lineno if node.end_lineno is not None else node.lineno
        for line in range(node.lineno, end + 1):
            comment = comments.get(line, "")
            if NOQA_UNUSED_IMPORT.search(comment) and REGISTRATION_WORDS.search(comment):
                findings.append(Finding(path, line, KIND_IMPORT, f"import kept for its side effect: {comment.strip()}"))
    return findings


def scan_file(path: Path) -> list[Finding]:
    """Every import-time registration in the Python file *path*.

    Raises:
        GateInputError: The file is not valid Python or not UTF-8.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise GateInputError(
            f"Cannot parse {path}: {error}. Expected: a UTF-8 Python source file. "
            f"Fix: correct the file, since the gate never skips a file it cannot read."
        ) from error
    return _register_calls(path, tree) + _registration_imports(path, tree, source)


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


def default_roots(workspace: Path) -> list[Path]:
    """The ``src/`` tree of every ``datrix-*`` package on disk."""
    return [
        package / SOURCE_SUBTREE
        for package in workspace_package_dirs(workspace, any_of=frozenset({PackageMarker.SRC}))
    ]


def scan(roots: Sequence[Path]) -> tuple[list[Finding], int]:
    """Every finding under *roots*, and how many files were read."""
    findings: list[Finding] = []
    files = 0
    for root in roots:
        for path in _python_files(root):
            files += 1
            findings.extend(scan_file(path))
    return findings, files


_PLANTED_SOURCE: Final[str] = textwrap.dedent(
    """\
    import pkg.elements  # noqa: F401 -- registers the library elements
    import pkg.reexport  # noqa: F401  (re-exported for callers)
    from pkg import (  # noqa: F401  (registration side effect)
        widgets,
    )

    register_all()
    X = register_capability(1)
    print("register")

    if X:
        registry.register_widget(X)

    for family in FAMILIES:
        family.register()

    try:
        Registrar.Register(X)
    except ValueError:
        pass_through(X)


    class Holder:
        register_kind("holder")


    def lazily() -> None:
        register_all()
    """
)

#: The planted lines that must be reported, by kind.
_PLANTED_EXPECTED: Final[frozenset[tuple[int, str]]] = frozenset(
    {
        (1, KIND_IMPORT),
        (3, KIND_IMPORT),
        (7, KIND_CALL),
        (12, KIND_CALL),
        (15, KIND_CALL),
        (18, KIND_CALL),
        (24, KIND_CALL),
    }
)


def self_test() -> bool:
    """The gate reports every planted shape at its line, and nothing else."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR, prefix="no-import-registration-") as scratch:
        package = Path(scratch) / "datrix-planted"
        source = package / SOURCE_SUBTREE / "planted" / "module.py"
        test = package / "tests" / "test_module.py"
        for path in (source, test):
            path.parent.mkdir(parents=True)
            path.write_text(_PLANTED_SOURCE, encoding="utf-8")
        roots = default_roots(Path(scratch))
        findings, files = scan(roots)
    found = {(finding.line, finding.kind) for finding in findings}
    if roots != [package / SOURCE_SUBTREE] or files != 1:
        logger.error("self_test_failed roots=%s files=%d", roots, files)
        return False
    if found != _PLANTED_EXPECTED or len(findings) != len(_PLANTED_EXPECTED):
        logger.error(
            "self_test_failed missed=%s unexpected=%s",
            sorted(_PLANTED_EXPECTED - found),
            sorted(found - _PLANTED_EXPECTED),
        )
        return False
    logger.info("self_test_passed findings=%d", len(findings))
    return True


def run_gate(roots: Sequence[Path]) -> int:
    """Scan *roots*; print each finding and a count."""
    try:
        findings, files = scan(roots)
    except GateInputError as error:
        print(f"FAIL {error}")
        return _EXIT_GATE_BROKEN
    for finding in findings:
        print(f"FAIL {finding.render()}")
    print(f"{files} file(s) under {len(roots)} src tree(s), {len(findings)} import-time registration(s)")
    return _EXIT_FINDINGS if findings else _EXIT_OK


def _check_planted_registrations_are_reported_exactly() -> None:
    assert self_test(), "the scan did not report exactly the planted registrations (see the self_test_failed record)"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/no-import-registration-gate.ps1``: one per wrapper parameter, spelled
    exactly."""
    return roots_gate_parser(WRAPPER, "Fail if importing a framework module registers anything.", debug=True)


def _run(args: argparse.Namespace) -> int:
    report_by_printing(args.debug)
    if args.self_test:
        return wrappers.run_self_test(
            [_check_planted_registrations_are_reported_exactly, check_requested_roots_split_on_commas],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    if not self_test():
        print("No-import-registration gate self-test failed: the gate cannot tell a registration from clean code.")
        return _EXIT_GATE_BROKEN
    requested = requested_roots(args.roots)
    return run_gate([Path(root) for root in requested] if requested else default_roots(WORKSPACE_DIR))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
