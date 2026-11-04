"""Where the fixtures of a workspace lie: the shared datrix-testing fixture set, its corpus, the corpus's
shared directory, and the tree each fixture's references resolve within."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from datrix_testing.corpus import SHARED_DIR

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    CORPUS_RELATIVE,
    SHARED_FIXTURES_RELATIVE,
    SHARED_PACKAGE,
)


class TreeRoots:
    """The tree each fixture's references resolve within: its package's ``tests/``; for a copy moved to the
    corpus's shared directory, ``shared/<package>/tests/``, the place its package's ``tests/`` moved to (so a
    path naming no file in its own tree names none in another project's either); else the shared set."""

    def __init__(self, base_dir: Path, packages: Sequence[Path]) -> None:
        self._shared = shared_fixtures_dir(base_dir).resolve()
        self._moved = shared_root(base_dir).resolve()
        self._roots = [(package / PackageMarker.TESTS.value).resolve() for package in packages]

    def __call__(self, path: Path) -> Path:
        """The tree root of the fixture at *path* (its own directory when it lies in no known tree)."""
        resolved = path.resolve()
        if resolved.is_relative_to(self._moved):
            parts = resolved.relative_to(self._moved).parts
            if len(parts) > 2 and parts[1] == PackageMarker.TESTS.value:
                return self._moved / parts[0] / parts[1]
        if resolved.is_relative_to(self._shared):
            return self._shared
        return next((root for root in self._roots if resolved.is_relative_to(root)), resolved.parent)


def shared_fixtures_dir(base_dir: Path) -> Path:
    """The shared ``datrix-testing`` fixture directory under *base_dir*."""
    return base_dir / SHARED_PACKAGE / SHARED_FIXTURES_RELATIVE


def corpus_root(base_dir: Path) -> Path:
    """The corpus root under *base_dir*."""
    return base_dir / SHARED_PACKAGE / CORPUS_RELATIVE


def shared_root(base_dir: Path) -> Path:
    """The shared directory of the corpus under *base_dir*."""
    return corpus_root(base_dir) / SHARED_DIR
