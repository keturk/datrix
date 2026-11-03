"""What repointing a package works on: one job per inventoried module, the package's status in code, the
undo record of a rewrite, and the ``test.ps1 -Specific`` run that proves one.

A module holding tests is proven by its own run; a module holding none (a ``conftest.py``, a helper) by the
run of the test modules depending on it. A module is done when it reads no input but a ``// @local`` one and,
holding a test with no local reason, names a corpus accessor (a conftest or helper answers to its inputs
only: its dependents carry the corpus rule); the package's status is the set comparison inventoried −
rewritten − local, which must be empty.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.dev.fixture_author.library_drafts import Rename, apply_renames
from datrix_scripts.dev.fixture_author.library_plan import (
    InventoriedModule,
    LibraryPlan,
)
from datrix_scripts.dev.fixture_author.needs import (
    CONFTEST_FILE,
    ModuleInput,
    package_inputs,
)
from datrix_scripts.dev.fixture_author.repoint_drafts import (
    JobTest,
    reads_corpus,
    unread_corpus,
    unshared_inputs,
)
from datrix_scripts.gates.ratchet.fixture_budget_gate import PYTHON_SUFFIX, parse_module, walk_files
from datrix_scripts.paths import WORKSPACE_DIR, script_env
from datrix_scripts.test.test import MODULE as TEST_MODULE
from datrix_scripts.test.test import PACKAGES_ENSURED_ENV, PACKAGES_ENSURED_VALUE

#: Where each module's original and the files its rewrite replaces are saved until the rewrite is judged.
UNDO_DIR: Final[Path] = WORKSPACE_DIR / ".tmp" / "fixture-author" / "undo"
#: The queue file of a module: this prefix, the package, :data:`QUEUE_SEPARATOR`, the module's dotted path.
QUEUE_PREFIX: Final = "repoint-"
QUEUE_SEPARATOR: Final = "--"
#: How long one ``test.ps1 -Specific`` run may take, in seconds.
RUN_TIMEOUT_SECONDS: Final = 1800
_QUEUE_SUFFIX: Final = ".md"
_TESTS_DIR: Final = "tests"
_TEST_FILE: Final = re.compile(r"^(test_.*|.*_test)\.py$")
_MANIFEST: Final = "pending.json"
_COPIES: Final = "files"
_ENCODING: Final = "utf-8"


class RepointError(Exception):
    """The inventory and the library plan disagree, or a rewrite could not be written back."""


@dataclass(frozen=True)
class RunVerdict:
    """What a ``-Specific`` run of a module's proving files said: whether it passed, and its output."""

    passed: bool
    output: str


#: Runs the package-relative test files of the package directory given; the verdict.
SpecificRunner = Callable[[Path, Sequence[str]], RunVerdict]


def specific_command(package: str, files: Sequence[str]) -> list[str]:
    """The ``test.ps1 <package> -Specific "<files>"`` run, as the venv runs the module behind the wrapper."""
    return [sys.executable, "-m", TEST_MODULE, package, "--specific", ",".join(files), "--no-digest"]


def run_specific(package_dir: Path, files: Sequence[str]) -> RunVerdict:
    """Run *files* of the workspace package at *package_dir* through ``test.ps1 -Specific``."""
    command = specific_command(package_dir.name, files)
    environment = {**script_env(), PACKAGES_ENSURED_ENV: PACKAGES_ENSURED_VALUE}
    try:
        done = subprocess.run(command, cwd=WORKSPACE_DIR, env=environment, capture_output=True, text=True,
                              encoding=_ENCODING, errors="replace", timeout=RUN_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return RunVerdict(False, f"test.ps1 {package_dir.name} -Specific {list(files)} did not finish in "
                                 f"{RUN_TIMEOUT_SECONDS} s.")
    return RunVerdict(done.returncode == 0, f"{done.stdout}{done.stderr}")


# --------------------------------------------------------------------------- undo


@dataclass(frozen=True)
class UndoStore:
    """The original bytes of every file one rewrite writes, under *root*, until the rewrite is judged."""

    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / _MANIFEST

    def save(self, module: str, paths: Sequence[Path]) -> None:
        """Save each of *paths* as it is now (absent ones recorded as absent, with the directories a write
        would create) before *module*'s rewrite writes them."""
        copies = self.root / _COPIES
        copies.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, str | None]] = []
        created: set[str] = set()
        for index, path in enumerate(paths):
            if path.is_file():
                (copies / str(index)).write_bytes(path.read_bytes())
                files.append({"path": str(path), "copy": str(index)})
                continue
            files.append({"path": str(path), "copy": None})
            parent = path.parent
            while not parent.exists():
                created.add(str(parent))
                parent = parent.parent
        record = {"module": module, "files": files, "created_dirs": sorted(created)}
        self.manifest.write_text(json.dumps(record, indent=1), encoding=_ENCODING)

    def restore(self) -> str | None:
        """Write every saved file back byte for byte, remove each file and directory the rewrite created, and
        clear the record; the module it belonged to, ``None`` when nothing was saved."""
        if not self.manifest.is_file():
            return None
        record = json.loads(self.manifest.read_text(encoding=_ENCODING))
        for entry in record["files"]:
            path = Path(entry["path"])
            if entry["copy"] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes((self.root / _COPIES / entry["copy"]).read_bytes())
        for directory in sorted(map(Path, record["created_dirs"]), key=lambda each: len(each.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        self.clear()
        return str(record["module"])

    def clear(self) -> None:
        """Forget the saved files: the rewrite was kept or written back."""
        copies = self.root / _COPIES
        if copies.is_dir():
            shutil.rmtree(copies)
        self.manifest.unlink(missing_ok=True)


# --------------------------------------------------------------------------- jobs


@dataclass(frozen=True)
class ModuleJob:
    """One module to rewrite: the tests it serves and the package-relative test files that prove it."""

    module: str
    tests: tuple[JobTest, ...]
    run_files: tuple[str, ...]

    @property
    def entries(self) -> tuple[str, ...]:
        return tuple(sorted({test.entry for test in self.tests if test.entry is not None}))


def _is_test_file(path: Path) -> bool:
    return bool(_TEST_FILE.match(path.name))


def _imported(module: Path, package_dir: Path) -> set[tuple[str, ...]]:
    """Every module *module* imports, as dotted parts; a relative import resolved against its own path."""
    own = module.relative_to(package_dir).with_suffix("").parts
    targets: set[tuple[str, ...]] = set()
    for node in ast.walk(parse_module(module)):
        if isinstance(node, ast.Import):
            targets.update(tuple(alias.name.split(".")) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = tuple(node.module.split(".")) if node.module else ()
            if node.level:
                base = own[: len(own) - node.level] + base
            targets.add(base)
            targets.update((*base, alias.name) for alias in node.names)
    return {target for target in targets if target}


def dependents(module: Path, package_dir: Path) -> list[Path]:
    """The test modules of *package_dir* whose run proves *module*: every one under a conftest's directory, or
    every one importing it (matched by the tail of its dotted path, so a run may hold more, never fewer)."""
    tests = [path for path in walk_files(package_dir / _TESTS_DIR)
             if path.suffix == PYTHON_SUFFIX and _is_test_file(path)]
    if module.name == CONFTEST_FILE:
        return sorted(path for path in tests if path.is_relative_to(module.parent))
    parts = module.relative_to(package_dir).with_suffix("").parts
    return sorted(
        path for path in tests
        if path != module and any(parts[-len(target):] == target for target in _imported(path, package_dir))
    )


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _job_tests(row: InventoriedModule, entries: Mapping[tuple[str, str], str], renames: Sequence[Rename],
               prefix: str) -> Iterator[JobTest]:
    for test in row.tests:
        if test.local is not None:
            yield JobTest(f"{prefix}{test.name}", None, test.declarations, test.local)
            continue
        entry = entries.get((row.module, test.name))
        if entry is None:
            raise RepointError(f"{row.module}::{test.name} has no local reason and the library plan places it in "
                               "no entry. Fix: rerun fixture-author.ps1 needs, then library.")
        yield JobTest(f"{prefix}{test.name}", entry, apply_renames(test.declarations, renames), None)


def _job_order(job: ModuleJob) -> tuple[int, str]:
    name = Path(job.module).name
    rank = 2 if name == CONFTEST_FILE else 0 if _is_test_file(Path(job.module)) else 1
    return rank, job.module


def plan_jobs(rows: Sequence[InventoriedModule], plan: LibraryPlan, renames: Sequence[Rename], package_dir: Path,
              workspace: Path) -> tuple[ModuleJob, ...]:
    """One job per module of *rows*: test modules first, then helpers, then conftests.

    Raises:
        RepointError: a test with no local reason is placed in no entry of *plan*.
    """
    entries = {(test.module, test.name): entry.entry for entry in plan.entries for test in entry.tests}
    by_module = {row.module: row for row in rows}
    jobs: list[ModuleJob] = []
    for row in rows:
        path = workspace / row.module
        if row.tests:
            tests = tuple(_job_tests(row, entries, renames, ""))
            run = (_relative(path, package_dir),)
        else:
            found = dependents(path, package_dir) if path.is_file() else []
            labels = [_relative(each, workspace) for each in found]
            tests = tuple(test for label in labels if label in by_module
                          for test in _job_tests(by_module[label], entries, renames, f"{label}::"))
            run = tuple(_relative(each, package_dir) for each in found)
        jobs.append(ModuleJob(row.module, tests, run))
    return tuple(sorted(jobs, key=_job_order))


# --------------------------------------------------------------------------- package status


@dataclass(frozen=True)
class PackageStatus:
    """The package's modules by what the code holds now: done ones split into rewritten and local, and each
    module still reading an input it may not with why."""

    inventoried: frozenset[str]
    rewritten: frozenset[str]
    local: frozenset[str]
    pending: Mapping[str, tuple[str, ...]]

    def remainder(self) -> frozenset[str]:
        """inventoried − rewritten − local: the modules not yet done."""
        return self.inventoried - self.rewritten - self.local


def module_inputs_now(package_dir: Path, workspace: Path) -> dict[str, tuple[ModuleInput, ...]]:
    """Every input each module of the package at *package_dir* reads now, by workspace-relative module path.

    Raises:
        NeedsScanError: the shared fixture directory is missing or an input cannot be read.
        FixtureScanError: a test module cannot be parsed.
    """
    return {_relative(each.module, workspace): each.inputs for each in package_inputs(package_dir, workspace)}


def package_status(rows: Sequence[InventoriedModule], found: Mapping[str, Sequence[ModuleInput]],
                   workspace: Path) -> PackageStatus:
    """The status of *rows*, the inventoried modules of one package, from *found*, the inputs each of its
    modules reads now (:func:`module_inputs_now`)."""
    pending: dict[str, tuple[str, ...]] = {}
    corpus_readers: set[str] = set()
    for row in rows:
        path = workspace / row.module
        if not path.is_file():
            pending[row.module] = ("the module no longer exists. Fix: rerun fixture-author.ps1 needs.",)
            continue
        tree = parse_module(path)
        reasons = [*unshared_inputs(found.get(row.module, ())), *unread_corpus(row.tests, tree)]
        if reasons:
            pending[row.module] = tuple(reasons)
        elif reads_corpus(tree):
            corpus_readers.add(row.module)
    inventoried = frozenset(row.module for row in rows)
    done = inventoried - pending.keys()
    local = frozenset(
        row.module for row in rows
        if row.module in done and row.module not in corpus_readers
        and row.tests and all(test.local is not None for test in row.tests)
    )
    return PackageStatus(inventoried, done - local, local, pending)


def queue_file(queue_dir: Path, package: str, module: str) -> Path:
    """The queue file of *module* (workspace-relative) of *package*."""
    relative = Path(module).relative_to(package).with_suffix("")
    return queue_dir / f"{QUEUE_PREFIX}{package}{QUEUE_SEPARATOR}{'.'.join(relative.parts)}{_QUEUE_SUFFIX}"


def package_queue_files(queue_dir: Path, package: str) -> list[Path]:
    """The queue files of *package*'s modules a person still has to finish."""
    return sorted(queue_dir.glob(f"{QUEUE_PREFIX}{package}{QUEUE_SEPARATOR}*{_QUEUE_SUFFIX}"))


__all__ = [
    "QUEUE_PREFIX",
    "QUEUE_SEPARATOR",
    "RUN_TIMEOUT_SECONDS",
    "UNDO_DIR",
    "ModuleJob",
    "PackageStatus",
    "RepointError",
    "RunVerdict",
    "SpecificRunner",
    "UndoStore",
    "dependents",
    "module_inputs_now",
    "package_queue_files",
    "package_status",
    "plan_jobs",
    "queue_file",
    "run_specific",
    "specific_command",
]
