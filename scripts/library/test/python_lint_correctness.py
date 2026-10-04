#!/usr/bin/env python
"""Python lint-correctness gate: pyflakes (`ruff --select F`) is a hard zero.

WHY THIS EXISTS
---------------
No repo gate ran ruff, so every pyflakes finding -- an unused import, an
undefined name, a test function silently shadowed by a same-named redefinition
(the first definition never runs) -- stayed invisible until someone happened to
lint that one file. This gate makes the whole class visible on every run and
the commit path (``git/commit-and-push.ps1``) refuses to let a new one land.

WHAT THIS COMPUTES
------------------
Targets are derived from disk, never listed: every workspace directory named
``datrix*`` holding a ``pyproject.toml`` contributes its ``src/`` and ``tests/``
trees when present, and the showcase repo (``datrix``) contributes ``scripts/``.
For each tree, ``ruff check --select F --output-format json`` runs from the
package root so that package's own ``per-file-ignores`` apply. ``--select F`` is
explicit so a package whose config narrowed its rule selection cannot hide a
pyflakes finding.

HARD ZERO, NO BASELINE
----------------------
Any finding fails. A finding that is genuinely required (an import kept for a
documented side effect) is suppressed only by a line-level ``# noqa: <code>``
carrying the reason on the same line; ``RUF100`` already reports a stale one.
A decrease-only baseline would let the count sit.

RULE SET: F ONLY
----------------
The style families (UP037, I001, UP031, ...) are not correctness defects and
would bury the pyflakes signal.

NON-VACUITY
-----------
A scan that found no trees is broken, not clean. Every run first proves, on a
temporary fixture package, that the scanner reports exactly a planted F401 and
F821, reports nothing for the clean package, and honours a fixture
``per-file-ignores`` for the F401 only; and the live run must have scanned at
least one tree for every discovered package.

Exit codes:
  0 = zero pyflakes findings in every scanned tree
  1 = at least one finding, or the self-test failed
  2 = usage error, or ruff could not run
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = SCRIPT_DIR.parent
DATRIX_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(LIBRARY_DIR))

from shared.framework_repos import SHOWCASE_REPO_NAME  # noqa: E402

logger = logging.getLogger(__name__)

PACKAGE_PREFIX = "datrix"
PYPROJECT_FILE = "pyproject.toml"
PACKAGE_TREES = ("src", "tests")
SHOWCASE_TREES = ("scripts",)
RULE_SELECTION = "F"
RUFF_OK_EXIT_CODES = frozenset({0, 1})
# Windows CreateProcess rejects a command line over 32767 characters; the path
# arguments of one ruff run stay well under it, the fixed arguments take the rest.
MAX_PATH_ARGUMENT_CHARS = 24000
CODE_UNUSED_IMPORT = "F401"
CODE_UNDEFINED_NAME = "F821"
EXAMPLES_DIR = "examples"
GENERATED_DIR = "generated"

FIXTURE_PACKAGE = "fixture_pkg"
FIXTURE_MODULE = f"src/{FIXTURE_PACKAGE}/a.py"
FIXTURE_DIRTY_SOURCE = "import os\n\n\ndef f() -> int:\n    return missing_name\n"
FIXTURE_CLEAN_SOURCE = "def f() -> int:\n    return 1\n"
FIXTURE_PYPROJECT = '[project]\nname = "fixture-pkg"\nversion = "0"\n'
FIXTURE_IGNORING_PYPROJECT = (
    FIXTURE_PYPROJECT
    + f'\n[tool.ruff.lint.per-file-ignores]\n"{FIXTURE_MODULE}" = ["{CODE_UNUSED_IMPORT}"]\n'
)


class LintGateError(RuntimeError):
    """The gate cannot run: ruff failed or its output could not be read."""


@dataclass(frozen=True)
class Finding:
    """One pyflakes finding."""

    path: str
    line: int
    col: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.col} {self.code} {self.message}"


@dataclass(frozen=True)
class Target:
    """One package tree to lint, run from its package root."""

    package: str
    root: Path
    tree: str


def package_roots(workspace_root: Path) -> list[Path]:
    """Every workspace ``datrix*`` directory holding a ``pyproject.toml``."""
    return [
        child
        for child in sorted(workspace_root.iterdir())
        if child.is_dir()
        and child.name.startswith(PACKAGE_PREFIX)
        and (child / PYPROJECT_FILE).is_file()
    ]


def discover_targets(workspace_root: Path) -> list[Target]:
    """Derive the trees to lint from disk: each package's src/tests, plus the showcase scripts."""
    targets: list[Target] = []
    for root in package_roots(workspace_root):
        trees = PACKAGE_TREES + (SHOWCASE_TREES if root.name == SHOWCASE_REPO_NAME else ())
        targets.extend(Target(root.name, root, tree) for tree in trees if (root / tree).is_dir())
    return targets


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def ruff_check(python_exe: str, cwd: Path, paths: list[str]) -> list[Finding]:
    """Run ``ruff check --select F`` from ``cwd`` over ``paths`` and parse its JSON."""
    command = [
        python_exe,
        "-m",
        "ruff",
        "check",
        "--select",
        RULE_SELECTION,
        "--output-format",
        "json",
        "--no-cache",
        *paths,
    ]
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode not in RUFF_OK_EXIT_CODES:
        raise LintGateError(
            f"ruff exited {result.returncode} in {cwd}: {(result.stderr or result.stdout).strip()}"
        )
    try:
        records = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise LintGateError(f"ruff produced unreadable JSON in {cwd}: {exc}") from exc
    return [
        Finding(
            path=_relative_posix(Path(record["filename"]), cwd),
            line=record["location"]["row"],
            col=record["location"]["column"],
            code=record["code"],
            message=record["message"],
        )
        for record in records
    ]


def scan_targets(python_exe: str, targets: list[Target]) -> list[tuple[Target, Finding]]:
    """Lint every target; return each finding with the target that produced it."""
    hits: list[tuple[Target, Finding]] = []
    for target in targets:
        hits.extend((target, f) for f in ruff_check(python_exe, target.root, [target.tree]))
    return hits


def uncovered_packages(workspace_root: Path, targets: list[Target]) -> list[str]:
    """Discovered packages for which no tree was scanned."""
    covered = {target.package for target in targets}
    return [root.name for root in package_roots(workspace_root) if root.name not in covered]


def is_generated_example(rel_path: str) -> bool:
    """True for a file under an example's checked-in ``generated/`` output tree.

    That tree is the generators' output, regenerated from the example source: a
    finding in it is a defect of the emitter that wrote the line, held by the
    generators' own tests, and the file is replaced on the next generation.
    """
    parts = rel_path.split("/")
    return parts[0] == EXAMPLES_DIR and GENERATED_DIR in parts[1:-1]


def pending_python_files(repo_path: Path, rel_paths: list[str]) -> list[str]:
    """The authored ``.py`` files among ``rel_paths`` that still exist.

    A generated example's output is excluded (see :func:`is_generated_example`).
    """
    return [
        p
        for p in rel_paths
        if p.endswith(".py") and not is_generated_example(p) and (repo_path / p).is_file()
    ]


def scan_pending(python_exe: str, repo_path: Path, rel_paths: list[str]) -> list[Finding]:
    """Lint only a repo's pending ``.py`` files, from the repo root."""
    files = pending_python_files(repo_path, rel_paths)
    findings: list[Finding] = []
    for batch in path_batches(files, MAX_PATH_ARGUMENT_CHARS):
        findings.extend(ruff_check(python_exe, repo_path, batch))
    return findings


def path_batches(paths: list[str], max_chars: int) -> list[list[str]]:
    """Split ``paths`` into consecutive batches whose joined length stays within ``max_chars``.

    A single path longer than the budget still gets its own batch.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    used = 0
    for path in paths:
        cost = len(path) + 1
        if current and used + cost > max_chars:
            batches.append(current)
            current, used = [], 0
        current.append(path)
        used += cost
    if current:
        batches.append(current)
    return batches


def _write_fixture(root: Path, pyproject: str, source: str) -> None:
    module = root / FIXTURE_MODULE
    module.parent.mkdir(parents=True, exist_ok=True)
    (root / PYPROJECT_FILE).write_text(pyproject, encoding="utf-8")
    module.write_text(source, encoding="utf-8")


def self_test(python_exe: str) -> list[str]:
    """Prove the scanner sees planted findings, passes clean code and honours per-file-ignores."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lint-gate-selftest-") as tmp:
        base = Path(tmp)

        dirty = base / "dirty"
        _write_fixture(dirty, FIXTURE_PYPROJECT, FIXTURE_DIRTY_SOURCE)
        codes = sorted(f.code for f in ruff_check(python_exe, dirty, ["src"]))
        if codes != [CODE_UNUSED_IMPORT, CODE_UNDEFINED_NAME]:
            failures.append(f"planted F401 + F821 must report exactly those two, got {codes}")

        clean = base / "clean"
        _write_fixture(clean, FIXTURE_PYPROJECT, FIXTURE_CLEAN_SOURCE)
        found = ruff_check(python_exe, clean, ["src"])
        if found:
            failures.append(f"clean fixture must report zero, got {[f.render() for f in found]}")

        ignoring = base / "ignoring"
        _write_fixture(ignoring, FIXTURE_IGNORING_PYPROJECT, FIXTURE_DIRTY_SOURCE)
        codes = [f.code for f in ruff_check(python_exe, ignoring, ["src"])]
        if codes != [CODE_UNDEFINED_NAME]:
            failures.append(f"per-file-ignores of F401 must leave only F821, got {codes}")

        failures.extend(_batching_failures(python_exe, base / "batched"))
        failures.extend(_generated_example_failures(python_exe, base / "examples-tree"))
    return failures


def _generated_example_failures(python_exe: str, root: Path) -> list[str]:
    """A dirty file under ``examples/**/generated/`` is skipped; the same file elsewhere is not."""
    _write_fixture(root, FIXTURE_PYPROJECT, FIXTURE_DIRTY_SOURCE)
    generated_rel = f"{EXAMPLES_DIR}/shop/{GENERATED_DIR}/python-docker/a.py"
    authored_rel = f"{EXAMPLES_DIR}/shop/config/a.py"
    for rel in (generated_rel, authored_rel):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(FIXTURE_DIRTY_SOURCE, encoding="utf-8")
    scanned = pending_python_files(root, [generated_rel, authored_rel])
    if scanned != [authored_rel]:
        return [f"only the authored example file may be scanned, got {scanned}"]
    codes = sorted(f.code for f in scan_pending(python_exe, root, [generated_rel, authored_rel]))
    if codes != [CODE_UNUSED_IMPORT, CODE_UNDEFINED_NAME]:
        return [f"the authored example file must still report F401 + F821, got {codes}"]
    return []


def _batching_failures(python_exe: str, root: Path) -> list[str]:
    """A pending set whose paths exceed the OS command-line limit must still be linted in full."""
    _write_fixture(root, FIXTURE_PYPROJECT, FIXTURE_DIRTY_SOURCE)
    package_dir = (root / FIXTURE_MODULE).parent
    padding = "p" * 40
    rel_paths = [f"src/{FIXTURE_PACKAGE}/{padding}_{index:03d}.py" for index in range(500)]
    for rel in rel_paths:
        (root / rel).write_text(FIXTURE_CLEAN_SOURCE, encoding="utf-8")
    rel_paths.append(f"src/{FIXTURE_PACKAGE}/{(root / FIXTURE_MODULE).name}")
    total = sum(len(p) + 1 for p in rel_paths)
    if total <= MAX_PATH_ARGUMENT_CHARS or not package_dir.is_dir():
        return [f"batching fixture must exceed the batch budget, got {total} chars"]
    codes = sorted(f.code for f in scan_pending(python_exe, root, rel_paths))
    if codes != [CODE_UNUSED_IMPORT, CODE_UNDEFINED_NAME]:
        return [f"batched pending scan must still report the planted F401 + F821, got {codes}"]
    return []


def run_scan(python_exe: str, workspace_root: Path) -> int:
    targets = discover_targets(workspace_root)
    missing = uncovered_packages(workspace_root, targets)
    if not targets or missing:
        print(
            "PYTHON LINT-CORRECTNESS GATE CANNOT RUN: a scan that found no trees is broken, "
            f"not clean. Packages with no scanned tree: {missing or 'all'}.",
            file=sys.stderr,
        )
        return 2
    hits = scan_targets(python_exe, targets)
    for target, finding in hits:
        print(f"{target.package}/{finding.render()}")
    packages = len({t.package for t in targets})
    if hits:
        print(
            f"PYTHON LINT-CORRECTNESS GATE FAILED: {len(hits)} pyflakes finding(s) across "
            f"{len(targets)} tree(s) in {packages} package(s). Fix the code; suppress only with a "
            f"line-level `# noqa: <code>` carrying the reason."
        )
        return 1
    print(f"Python lint-correctness: clean across {len(targets)} tree(s) in {packages} package(s).")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        failures = self_test(sys.executable)
        if failures:
            print("PYTHON LINT-CORRECTNESS GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print("Self-test passed: planted F401 + F821 seen, clean passes, per-file-ignores honoured.")
        if args.self_test:
            return 0
        return run_scan(sys.executable, DATRIX_ROOT.parent)
    except LintGateError as exc:
        print(f"PYTHON LINT-CORRECTNESS GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
