#!/usr/bin/env python3
"""Compare the feature tags a package's tests carry with the documented vocabulary.

The vocabulary in ``datrix-common/docs/contributing/test-guidelines/feature-tags.md``
(``## Vocabulary`` table) is free-form -- a new tag is added whenever none fits -- but its rule
is "reuse one when it fits, spelled exactly", and reuse only works when the table lists what is
in use. A tag missing from the table is how near-synonyms (``auth`` / ``authentication`` /
``authorization``) appear, and a ``-Tag`` run on one of them then selects only part of the
behaviour.

For each named package this AST-parses every ``tests/**/*.py`` (``pytest.mark.tag(...)`` in
decorators, ``pytestmark`` assignments and ``pytest.param(marks=...)`` alike -- every call whose
callee ends in ``mark.tag``) and prints the tags in use that the table does not list, with
where each is first applied. Packages without a pytest ``tests/`` tree (Node suites) are named
and skipped. Report only: the exit code is 0 unless the vocabulary doc cannot be read (2). The
table is read by ``datrix_common.testing.tag_vocabulary``, the one reader the feature-tag plugin
also uses to refuse an unlisted tag at collection in every ``test.ps1`` session. ``test.ps1
-ListTags`` (``datrix_scripts.test.test``) runs it after the listings.

Usage:
    python -m datrix_scripts.test.tag_vocabulary PACKAGE [PACKAGE ...]
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_common.testing.tag_vocabulary import VOCABULARY_DOC, documented_tags
from datrix_scripts.paths import WORKSPACE_DIR

EXIT_OK: Final[int] = 0
EXIT_NO_VOCABULARY: Final[int] = 2
TAG_CALL_SUFFIX: Final[tuple[str, str]] = ("mark", "tag")
TESTS_DIR_NAME: Final[str] = "tests"
SOURCE_ENCODING: Final[str] = "utf-8-sig"


def _is_tag_call(node: ast.Call) -> bool:
    parts: list[str] = []
    target: ast.expr = node.func
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    return tuple(reversed(parts[:2])) == TAG_CALL_SUFFIX


def tags_in(tree: ast.Module) -> list[tuple[str, int]]:
    """``(tag, line)`` for every string argument of every ``*.mark.tag(...)`` call."""
    return [
        (argument.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_tag_call(node)
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]


def package_tags(tests_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Tag -> first ``path:line`` applying it, and the files that could not be parsed."""
    first_use: dict[str, str] = {}
    unparseable: list[str] = []
    for path in sorted(tests_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding=SOURCE_ENCODING), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            unparseable.append(path.relative_to(WORKSPACE_DIR).as_posix())
            continue
        for tag, line in tags_in(tree):
            first_use.setdefault(tag, f"{path.relative_to(WORKSPACE_DIR).as_posix()}:{line}")
    return first_use, unparseable


def report(package: str, vocabulary: frozenset[str]) -> None:
    tests_dir = WORKSPACE_DIR / package / TESTS_DIR_NAME
    if not tests_dir.is_dir():
        print(f"{package}: no pytest tests/ tree; vocabulary not compared.")
        return
    first_use, unparseable = package_tags(tests_dir)
    missing = sorted(set(first_use) - vocabulary)
    print(f"{package}: {len(first_use)} tag(s) in use, {len(missing)} not in the vocabulary table.")
    for tag in missing:
        print(f"  {tag}  (first applied at {first_use[tag]})")
    for path in unparseable:
        print(f"  UNPARSEABLE {path} (its tags were not read)")


def main(argv: Sequence[str]) -> int:
    if not argv:
        print("Usage: python -m datrix_scripts.test.tag_vocabulary PACKAGE [PACKAGE ...]", file=sys.stderr)
        return EXIT_NO_VOCABULARY
    try:
        vocabulary = documented_tags()
    except (OSError, ValueError) as exc:
        print(f"Cannot read the tag vocabulary: {exc}", file=sys.stderr)
        return EXIT_NO_VOCABULARY
    print(f"Vocabulary ({VOCABULARY_DOC.relative_to(WORKSPACE_DIR).as_posix()}): {len(vocabulary)} tag(s) listed.")
    for package in argv:
        report(package, vocabulary)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
