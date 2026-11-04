"""The model-contract capture's secret screen, run over the corpus as it would be once copies move.

Capture loads every ``.dcfg`` under the corpus after a package's own, in each package holding
``tests/test_model_contracts.py``, and raises on a secret finding. Before a ``.dcfg`` copy moves into the
corpus, the screen builds the would-be state in a temporary directory -- the corpus with each placed text
written at its shared path, and each such package's ``tests/`` without the copies the move deletes -- and
runs ``collect_samples`` there with the package's real model set. A finding on a placed text names the
group whose move would make that package's capture raise.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_testing.model_contracts.capture import CaptureError, collect_samples
from datrix_testing.model_contracts.discovery import ModelDiscoveryError, model_set

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.ratchet.fixture_budget_gate import PYTHON_SUFFIX, walk_files

#: The test module whose presence makes a package capture ``.dcfg`` samples.
MODEL_CONTRACTS_MODULE: Final = "test_model_contracts.py"
_FINDING_PATH_END: Final = " ("
_CORPUS_DIR: Final = "corpus"
_TESTS_DIR: Final = "tests"


class ScreenError(Exception):
    """The screen cannot run: a package's models do not import, or its capture refuses (exit 2)."""


@dataclass(frozen=True)
class PlacedText:
    """A text the move would write into the corpus.

    Attributes:
        key: The group it belongs to.
        relative: Its path under the corpus root.
        content: Its bytes.
    """

    key: str
    relative: Path
    content: bytes


def screened_packages(packages: Sequence[Path]) -> list[Path]:
    """The packages among *packages* whose capture loads the corpus (they hold ``tests/test_model_contracts.py``)."""
    return [package for package in packages if (package / PackageMarker.TESTS.value / MODEL_CONTRACTS_MODULE).is_file()]


def _copy_tree_files(source: Path, destination: Path, skipped: Set[Path]) -> None:
    """Every non-Python file under *source* (``walk_files``) but *skipped*, copied to *destination*."""
    for path in walk_files(source):
        if path.suffix == PYTHON_SUFFIX or path in skipped:
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _write_corpus(corpus: Path, destination: Path, placed: Sequence[PlacedText]) -> dict[str, list[Path]]:
    _copy_tree_files(corpus, destination, frozenset())
    written: dict[str, list[Path]] = {}
    for text in placed:
        target = destination / text.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.content)
        written.setdefault(text.key, []).append(target)
    return written


def _package_findings(package: Path, tests: Path, corpus: Path) -> list[str]:
    try:
        models = model_set(package)
        return collect_samples(tests, models, corpus).secret_findings
    except (ModelDiscoveryError, CaptureError) as exc:
        raise ScreenError(
            f"the capture of {package.name} cannot run over the would-be corpus ({type(exc).__name__}: {exc}); "
            "without it no .dcfg copy is proven safe to move. Fix the package's capture first."
        ) from exc


def screen(
    corpus: Path, packages: Sequence[Path], placed: Sequence[PlacedText], removed: Set[Path]
) -> dict[str, list[str]]:
    """The secret findings each placed group would raise in the capture of *packages*, by group key.

    *corpus* is the corpus root, *placed* the texts written into it, *removed* the package copies deleted.
    A finding is reported with the placed text's corpus-relative path, never the temporary one.

    Raises:
        ScreenError: A package's model set or capture cannot run.
    """
    findings: dict[str, list[str]] = {}
    if not placed:
        return findings
    with tempfile.TemporaryDirectory(prefix="fixture-dedupe-screen-") as scratch:
        root = Path(scratch)
        would_be = root / _CORPUS_DIR
        written = _write_corpus(corpus, would_be, placed)
        for package in packages:
            tests = root / _TESTS_DIR / package.name
            _copy_tree_files(package / PackageMarker.TESTS.value, tests, removed)
            reported = _package_findings(package, tests, would_be)
            _attribute(findings, written, reported, package.name, would_be)
    return findings


def _attribute(
    findings: dict[str, list[str]],
    written: Mapping[str, list[Path]],
    reported: Sequence[str],
    package: str,
    would_be: Path,
) -> None:
    for key, targets in written.items():
        for target in targets:
            prefix = f"{target}{_FINDING_PATH_END}"
            relative = target.relative_to(would_be).as_posix()
            for finding in reported:
                if finding.startswith(prefix):
                    findings.setdefault(key, []).append(f"{package}: {relative}{finding[len(str(target)):]}")
