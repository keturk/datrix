"""The test files that name what a fix session changed.

A fix is proven by the tests the session wrote and by the tests elsewhere that mention the code names it touched.
The names are the code-shaped words (``snake_case`` or ``camelCase``/``PascalCase``) in the text the session put into
and took out of its source and test files. A name that only a few test files mention picks those files out; a name
many test files mention says nothing about this change and selects none. The same name spelled ``app_user`` or
``appUser`` is one name.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

from datrix_scripts.logging_utils import say
from datrix_scripts.skill.common import read_text

TESTS_DIRNAME: Final = "tests"
MAX_TESTS_PER_NAME: Final = 25
MAX_REFERENCING_TESTS: Final = 40
_WORD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]{5,}")
_CODE_SHAPED: Final = re.compile(r"[a-z0-9][A-Z]|[A-Za-z0-9]_[A-Za-z0-9]")
_NAMES_SHOWN: Final = 4


def name_key(word: str) -> str:
    """The spelling-independent form of a code name: ``app_user`` and ``appUser`` are both ``appuser``."""
    return word.replace("_", "").lower()


def code_names(texts: Iterable[str]) -> dict[str, str]:
    """The code-shaped names in *texts*, by ``name_key``, each with the spelling met first."""
    names: dict[str, str] = {}
    for text in texts:
        for word in _WORD.findall(text):
            if _CODE_SHAPED.search(word):
                names.setdefault(name_key(word), word)
    return names


def _test_files(directory: Path) -> Iterable[Path]:
    base = directory / TESTS_DIRNAME
    return sorted(base.rglob("test_*.py")) if base.is_dir() else []


def _named_in_tests(packages: Mapping[str, Path], keys: frozenset[str],
                    skip: frozenset[Path]) -> dict[str, list[tuple[str, str]]]:
    """For each key, the (package, package-relative path) of every test file outside *skip* that names it."""
    hits: dict[str, list[tuple[str, str]]] = {}
    for package, directory in packages.items():
        for path in _test_files(directory):
            if path.resolve() in skip:
                continue
            present = {name_key(word) for word in _WORD.findall(read_text(path))} & keys
            relative = path.relative_to(directory).as_posix()
            for key in present:
                hits.setdefault(key, []).append((package, relative))
    return hits


def referencing_tests(packages: Mapping[str, Path], names: Mapping[str, str],
                      skip: frozenset[Path]) -> dict[str, tuple[list[str], list[str]]]:
    """The test files, by package, that name what changed: ``package -> (relative paths, names that picked them)``.

    A name that more than ``MAX_TESTS_PER_NAME`` test files mention is left out, and so is any name that would take
    the total past ``MAX_REFERENCING_TESTS`` files (rarest names first); the output says which.
    """
    hits = _named_in_tests(packages, frozenset(names), skip)
    chosen: dict[str, tuple[list[str], list[str]]] = {}
    taken: set[tuple[str, str]] = set()
    crowded: list[str] = []
    over_limit: list[str] = []
    for key in sorted(hits, key=lambda key: (len(hits[key]), key)):
        files = hits[key]
        if len(files) > MAX_TESTS_PER_NAME:
            crowded.append(names[key])
        elif len(taken | set(files)) > MAX_REFERENCING_TESTS:
            over_limit.append(names[key])
        else:
            taken.update(files)
            _record(chosen, names[key], files)
    _say_left_out(crowded, f"each named in more than {MAX_TESTS_PER_NAME} test files, so none says which are about "
                           "this change")
    _say_left_out(over_limit, f"taking the tests naming changed code past {MAX_REFERENCING_TESTS} files")
    return {package: (sorted(paths), picked) for package, (paths, picked) in chosen.items()}


def _record(chosen: dict[str, tuple[list[str], list[str]]], name: str, files: Iterable[tuple[str, str]]) -> None:
    for package, relative in files:
        paths, picked = chosen.setdefault(package, ([], []))
        if relative not in paths:
            paths.append(relative)
        if name not in picked:
            picked.append(name)


def _say_left_out(left_out: list[str], why: str) -> None:
    if left_out:
        say(f"  related names left out ({len(left_out)}): {describe_names(left_out)}; {why}")


def describe_names(picked: list[str]) -> str:
    """The names that picked a package's tests, for a run's stated reason."""
    shown = ", ".join(f"'{name}'" for name in picked[:_NAMES_SHOWN])
    return shown + (f" and {len(picked) - _NAMES_SHOWN} more" if len(picked) > _NAMES_SHOWN else "")
