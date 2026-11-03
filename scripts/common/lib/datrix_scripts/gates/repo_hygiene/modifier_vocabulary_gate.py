#!/usr/bin/env python
"""Every word of the field and relationship modifier vocabularies has a reader in framework source.

``datrix_common.datrix_model.modifier_vocabulary`` declares the closed set of words a
field or relationship may carry after its ``:``; semantic analysis refuses any other
word, and the ``Field``/``Relationship`` readers refuse to be asked for one, so a
reader can never ask for an undeclared word. This gate proves the other direction: a
declared word nothing reads would be accepted by analysis and dropped by every
target -- the silent drop the vocabulary exists to end.

A word counts as read when any ``src/`` module of a scanned package, other than the
vocabulary module itself, either

A. references a vocabulary constant naming it (``FIELD_MODIFIER_SENSITIVE``, or a
   tuple/frozenset constant such as ``INPUT_TRANSFORM_MODIFIERS`` that holds it), or
B. passes the word as a literal to ``has_modifier(...)`` / ``get_modifier(...)``, or
   compares it with a ``<x>.name``.

The scan is by AST, never text. Self-test runs first on every invocation: a planted
vocabulary with one unread word must be reported, and the same vocabulary read through
both shapes must pass -- so a scanner that can only return zero fails here.

This module is what ``gates/repo-hygiene/modifier-vocabulary-gate.ps1`` (and its ``.sh`` twin) runs,
in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] modifier-vocabulary PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = every declared word is read (or a successful --self-test), 1 = a
declared word has no reader, 2 = usage error, no packages discovered, a stale install
that could not be refreshed, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, print_command
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import (
    base_dir_gate_parser,
    packages_current,
    requested_base_dir,
)
from datrix_scripts.test import wrappers

GATE: Final = "modifier-vocabulary"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.modifier_vocabulary_gate"
WRAPPER: Final = "modifier-vocabulary-gate"

#: The vocabulary module: its constants define the words, so its own references are not reads.
_VOCABULARY_MODULE: Final = "datrix_common.datrix_model.modifier_vocabulary"
_VOCABULARY_FILE: Final = Path("datrix_common", "datrix_model", "modifier_vocabulary.py")
#: The vocabularies the gate holds to a reader, by the kind a report names.
_VOCABULARIES: Final[tuple[tuple[str, str], ...]] = (
    ("field", "FIELD_MODIFIERS"),
    ("relationship", "RELATIONSHIP_MODIFIERS"),
    ("cache entry field", "CACHE_ENTRY_FIELD_MODIFIERS"),
)
#: The reader methods a literal word is passed to.
_READER_METHODS: Final[frozenset[str]] = frozenset({"has_modifier", "get_modifier"})


@dataclass(frozen=True)
class Vocabulary:
    """The words one declaration kind accepts, and the constants that name them."""

    kind: str
    words: frozenset[str]


@dataclass(frozen=True)
class UnreadWord:
    """A declared word no framework module reads."""

    kind: str
    word: str

    def render(self) -> str:
        """One reviewer-facing line."""
        return f"  {self.kind} modifier '{self.word}' is declared but nothing reads it"


def _string_constant(node: ast.expr) -> str | None:
    """The value of a string-literal node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_reads(tree: ast.AST) -> set[str]:
    """Shape B: words passed to a reader method or compared with ``<x>.name``."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _READER_METHODS:
                found.update(word for word in map(_string_constant, node.args) if word is not None)
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(isinstance(o, ast.Attribute) and o.attr == "name" for o in operands):
                found.update(word for word in map(_string_constant, operands) if word is not None)
    return found


def _constant_reads(tree: ast.AST, constants: Mapping[str, frozenset[str]]) -> set[str]:
    """Shape A: words named by a vocabulary constant the module references."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            found.update(constants.get(node.id, frozenset()))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            found.update(constants.get(node.attr, frozenset()))
    return found


def words_read(source: str, constants: Mapping[str, frozenset[str]]) -> set[str]:
    """Every vocabulary word one module's source reads; a module that does not parse reads none."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return _literal_reads(tree) | _constant_reads(tree, constants)


def unread_words(vocabularies: Sequence[Vocabulary], read: set[str]) -> list[UnreadWord]:
    """The declared words of *vocabularies* missing from *read*, in kind then word order."""
    return [
        UnreadWord(kind=vocabulary.kind, word=word)
        for vocabulary in vocabularies
        for word in sorted(vocabulary.words - read)
    ]


def vocabulary_constants(module: ModuleType, vocabularies: Sequence[Vocabulary]) -> dict[str, frozenset[str]]:
    """Each upper-case constant of *module* that names declared words, with the words it names.

    A collection holding every word of a vocabulary is that vocabulary (or the readers'
    guard over it), not a reader of its words, so it names none.
    """
    words = frozenset().union(*(vocabulary.words for vocabulary in vocabularies))
    constants: dict[str, frozenset[str]] = {}
    for name, value in vars(module).items():
        if not name.isupper():
            continue
        if isinstance(value, str) and value in words:
            constants[name] = frozenset({value})
        elif isinstance(value, (tuple, frozenset)) and value and all(isinstance(v, str) for v in value):
            named = frozenset(value)
            if named <= words and not any(vocabulary.words <= named for vocabulary in vocabularies):
                constants[name] = named
    return constants


def discover_source_files(base_dir: Path) -> list[Path]:
    """Every ``src/`` Python file of every datrix package except the vocabulary module, sorted."""
    files: list[Path] = []
    for package in workspace_package_dirs(base_dir):
        src = package / "src"
        if not src.is_dir():
            continue
        files.extend(
            sorted(
                path for path in src.rglob("*.py")
                if "__pycache__" not in path.parts and not path.as_posix().endswith(_VOCABULARY_FILE.as_posix())
            )
        )
    return files


def _scan(files: Iterable[Path], constants: Mapping[str, frozenset[str]]) -> set[str]:
    read: set[str] = set()
    for path in files:
        read |= words_read(path.read_text(encoding="utf-8", errors="replace"), constants)
    return read


_SELF_TEST_VOCABULARY: Final = (Vocabulary("field", frozenset({"alpha", "beta", "gamma"})),)
_SELF_TEST_CONSTANTS: Final = {"ALPHA": frozenset({"alpha"}), "GREEK": frozenset({"alpha", "gamma"})}
_SELF_TEST_DIRTY: Final = """
def read(field):
    return field.has_modifier(ALPHA)
"""
_SELF_TEST_CLEAN: Final = """
def read(field, modifiers):
    names = GREEK
    return field.get_modifier("beta") or any(m.name == "gamma" for m in modifiers) or names
"""


def run_self_test() -> bool:
    """A planted unread word is reported; the same vocabulary read through both shapes passes."""
    ok = True
    dirty = unread_words(_SELF_TEST_VOCABULARY, words_read(_SELF_TEST_DIRTY, _SELF_TEST_CONSTANTS))
    if [(u.kind, u.word) for u in dirty] != [("field", "beta"), ("field", "gamma")]:
        print(f"[FAIL] self-test: expected 'beta' and 'gamma' unread, got {[u.word for u in dirty]}")
        ok = False
    clean = unread_words(_SELF_TEST_VOCABULARY, words_read(_SELF_TEST_CLEAN, _SELF_TEST_CONSTANTS))
    if clean:
        print(f"[FAIL] self-test: a fully read vocabulary reported {[u.word for u in clean]}")
        ok = False
    planted = ModuleType("planted_vocabulary")
    planted.ALPHA = "alpha"
    planted.EVERY_FIELD_WORD = frozenset({"alpha", "beta", "gamma"})
    planted.lower_case = "beta"
    named = vocabulary_constants(planted, _SELF_TEST_VOCABULARY)
    if named != {"ALPHA": frozenset({"alpha"})}:
        print(f"[FAIL] self-test: the whole vocabulary or a non-constant was taken for a reader: {sorted(named)}")
        ok = False
    if ok:
        print(
            "[OK] self-test: an unread word is reported, a word read by either shape is not, "
            "and the vocabulary itself reads nothing"
        )
    return ok


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/modifier-vocabulary-gate.ps1``: one per wrapper parameter."""
    return base_dir_gate_parser(
        WRAPPER, "Every declared field and relationship modifier has a reader in framework source."
    )


def _load_vocabularies() -> tuple[list[Vocabulary], dict[str, frozenset[str]]]:
    """The installed vocabularies and the constants naming their words."""
    module = importlib.import_module(_VOCABULARY_MODULE)
    vocabularies = [Vocabulary(kind, frozenset(getattr(module, attribute))) for kind, attribute in _VOCABULARIES]
    return vocabularies, vocabulary_constants(module, vocabularies)


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, then hold every declared word to a reader."""
    if args.debug:
        print_command()
    if not run_self_test():
        return EXIT_USAGE
    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )
    base_dir = requested_base_dir(args.base_dir)
    if not base_dir.is_dir():
        print(f"Base directory not found: {base_dir}")
        return EXIT_USAGE
    files = discover_source_files(base_dir)
    if not files:
        print(f"No package source found under {base_dir} -- refusing to pass vacuously")
        return EXIT_USAGE
    if not packages_current():
        print("The datrix packages could not be brought current in the shared venv -- refusing to judge the tree")
        return EXIT_USAGE
    vocabularies, constants = _load_vocabularies()
    if args.show_files:
        for path in files:
            print(f"  scanning {path}")
    unread = unread_words(vocabularies, _scan(files, constants))
    print(f"Scanned {len(files)} file(s); {sum(len(v.words) for v in vocabularies)} declared word(s)")
    if unread:
        print(f"\nMODIFIER VOCABULARY GATE FAILED: {len(unread)} declared word(s) without a reader\n")
        for word in unread:
            print(word.render())
        print(
            "\nAnalysis accepts every declared word, so one nothing reads is dropped by every target. "
            "Give it a reader (through its constant in modifier_vocabulary), or remove it from the vocabulary."
        )
        return EXIT_VIOLATION
    print("[OK] every declared field and relationship modifier has a reader")
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
