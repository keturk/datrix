#!/usr/bin/env python3
"""Prove a code change is output-neutral: generate a corpus twice and byte-diff.

Promotes the hand-rolled ``byte_identity_16_*.ps1/.py`` / ``gen_16_17.ps1`` /
``diff_16_17.py`` / ``31-09-verify-31-03-tag-stability.py`` family from
``D:\\datrix\\.scripts`` into a permanent utility. Two generations of the same
examples are compared byte-for-byte:

* **BEFORE** -- the sources of one or more named packages snapshotted at a git
  ref via ``git archive`` (READ-ONLY: no checkout/reset/stash of any kind), or
  a caller-supplied prebuilt source overlay dir. The snapshot ``src`` dirs are
  put on ``PYTHONPATH`` of a dedicated worker subprocess: the editable
  installs are plain ``.pth`` entries, so ``PYTHONPATH`` wins -- the proven
  temp-script shadowing trick. BEFORE always runs in a subprocess because
  ``PYTHONPATH`` shadowing cannot be applied reliably in-process after
  imports.
* **AFTER** -- the working tree as installed (a subprocess with ``PYTHONPATH``
  removed, for symmetry).

CRITICAL TRAP (verbatim from the temp scripts): the two output roots MUST have
equal-length absolute paths. Python's post-generation hooks batch ruff
invocations by total command-line CHARACTER count
(``hooks/language_hooks.py::_run_ruff_batched``), so a longer output path
shifts ruff's batch boundaries and produces phantom formatting diffs. The
roots are therefore baked in as ``.../byte-identity/bef`` and
``.../byte-identity/aft`` -- the caller can never choose unequal roots.

Generation and hashing REUSE ``test/reference_example_parity.py`` -- the real
``GenerationPipeline`` invocation with the same ``PipelineConfig`` defaults,
and its sha256 tree manifest with the canonical volatile exclusion set
(``.datrix/``, ``.ruff_cache/``, ``.tsc_cache/``, ``node_modules/``,
``__pycache__/``).

Usage:
  python scripts/library/dev/byte_identity_generate.py \
      --example 01-foundation --before-ref HEAD --packages datrix-codegen-common
  .\\scripts\\dev\\byte-identity-generate.ps1 -Example 01-foundation \
      -BeforeRef HEAD -Packages datrix-codegen-common

Exit codes: 0 = byte-identical, 1 = differences found, 2 = usage error or a
generation failure (the failing side is named).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared and sibling modules
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.test_projects import load_config, normalize_path  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402
from test.reference_example_parity import (  # noqa: E402
    EXAMPLES_ROOT,
    ManifestDiff,
    _register_language_plugins,
    build_manifest,
    diff_manifests,
    example_id,
    generate_example,
    render_unified_diff,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
EXIT_IDENTICAL = 0
EXIT_DIFFERENCES = 1
EXIT_USAGE = 2

#: Output home: <workspace>/.test-output/byte-identity/{bef,aft,report.json,report.md}
OUTPUT_SUBDIRS: tuple[str, ...] = (".test-output", "byte-identity")
#: The two generation roots. EQUAL LENGTH is load-bearing -- see module docstring.
BEFORE_DIRNAME = "bef"
AFTER_DIRNAME = "aft"
REPORT_JSON_NAME = "report.json"
REPORT_MD_NAME = "report.md"

#: Where --before-ref package snapshots are extracted (scratch, per policy).
SNAPSHOT_SUBDIRS: tuple[str, ...] = (".tmp", "byte-identity", "before-src")

SIDE_BEFORE = "BEFORE"
SIDE_AFTER = "AFTER"

WORKER_OK_PREFIX = "WORKER-OK"
WORKER_FAIL_PREFIX = "WORKER-FAIL"
#: Tail lines of a failed worker's output surfaced on the console.
MAX_FAILURE_OUTPUT_LINES = 15
#: Per-example cap on rendered unified diffs in report.md (every changed path
#: is still LISTED in both reports; only the rendered diffs are capped).
MAX_DIFFED_FILES_PER_EXAMPLE = 40

EXAMPLES_PATH_PREFIX = "examples/"
SYSTEM_DTRX_SUFFIX = "/system.dtrx"
SYSTEM_DTRX_NAME = "system.dtrx"


class UsageError(Exception):
    """Invalid usage or unresolvable input; the script exits with code 2."""


class GenerationError(Exception):
    """One side's generation subprocess failed."""

    def __init__(self, side: str, detail: str) -> None:
        super().__init__(f"{side} generation failed")
        self.side = side
        self.detail = detail


@dataclass(frozen=True)
class BeforeStrategy:
    """How the BEFORE code state is materialized."""

    pythonpath: str
    description: str
    detail: dict[str, object]


@dataclass(frozen=True)
class ExampleComparison:
    """Byte-level manifest delta for one example."""

    example: str
    ex_id: str
    before_files: int
    after_files: int
    delta: ManifestDiff


# ---------------------------------------------------------------------------
# Example resolution
# ---------------------------------------------------------------------------


def _split_csv(values: list[str] | None) -> list[str]:
    """Split repeatable/comma-separated argument values, preserving order.

    Args:
        values: Raw ``--example``-style argument occurrences.

    Returns:
        The flattened, stripped entries.
    """
    entries: list[str] = []
    for raw in values or []:
        entries.extend(part.strip() for part in raw.split(",") if part.strip())
    return entries


def _example_relpath_from_project_path(project_path: str) -> str:
    """Convert a test-projects.json project path to an example dir relpath.

    Args:
        project_path: e.g. ``examples/01-foundation/system.dtrx``.

    Returns:
        The example directory relative to ``datrix/examples/``.

    Raises:
        UsageError: If the path is not an ``examples/**/system.dtrx`` entry --
            byte-identity generates whole example systems, exactly like the
            reference-example parity gate.
    """
    normalized = normalize_path(project_path)
    if not normalized.startswith(EXAMPLES_PATH_PREFIX):
        raise UsageError(
            f"Test-set project path {project_path!r} is not under 'examples/'. "
            f"byte-identity only generates examples from datrix/examples/."
        )
    rel = normalized[len(EXAMPLES_PATH_PREFIX):]
    if not rel.endswith(SYSTEM_DTRX_SUFFIX):
        raise UsageError(
            f"Test-set project path {project_path!r} is not a system.dtrx project. "
            f"byte-identity generates whole systems (a per-service .dtrx is not "
            f"independently generable); pick a test set of system.dtrx examples."
        )
    return rel[: -len(SYSTEM_DTRX_SUFFIX)]


def _test_set_examples(test_set: str) -> list[str]:
    """Resolve a named test set to example dir relpaths.

    Reuses the test-projects.json loader from ``shared/test_projects.py`` (the
    provider/output-path derivation of ``get_test_projects`` is irrelevant
    here, so only the raw name->path mapping is consumed).

    Args:
        test_set: Test set name from test-projects.json.

    Returns:
        Example dir relpaths in test-set order.

    Raises:
        UsageError: On an unknown test set or a malformed config entry.
    """
    config = load_config()
    test_sets = config.get("testSets")
    if not isinstance(test_sets, dict) or test_set not in test_sets:
        available = sorted(test_sets) if isinstance(test_sets, dict) else []
        raise UsageError(
            f"Test set {test_set!r} not found in test-projects.json. "
            f"Available: {available}."
        )
    names = test_sets[test_set]
    if not isinstance(names, list):
        raise UsageError(
            f"Test set {test_set!r} in test-projects.json must be a list of "
            f"project names, got {type(names).__name__}."
        )

    paths_by_name: dict[str, str] = {}
    categories = config.get("projects")
    if not isinstance(categories, dict):
        raise UsageError("test-projects.json has no 'projects' object.")
    for category in categories.values():
        if not isinstance(category, list):
            continue
        for entry in category:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            path = entry.get("path")
            if isinstance(name, str) and isinstance(path, str):
                paths_by_name[name] = path

    relpaths: list[str] = []
    for name in names:
        if not isinstance(name, str) or name not in paths_by_name:
            raise UsageError(
                f"Test set {test_set!r} names project {name!r}, which has no "
                f"definition under 'projects' in test-projects.json."
            )
        relpaths.append(_example_relpath_from_project_path(paths_by_name[name]))
    return relpaths


def resolve_examples(example_args: list[str] | None, test_set: str | None) -> list[str]:
    """Resolve and validate the example set to generate.

    Args:
        example_args: ``--example`` occurrences (repeatable, comma-separated).
        test_set: ``--test-set`` name.

    Returns:
        Deduplicated example dir relpaths, each containing a ``system.dtrx``.

    Raises:
        UsageError: When neither/both selectors are given, or an example does
            not exist.
    """
    entries = _split_csv(example_args)
    if bool(entries) == bool(test_set):
        raise UsageError(
            "Pass exactly one of -Example <relpath> (repeatable/comma-separated, "
            "relative to datrix/examples) or -TestSet <name>."
        )
    relpaths = entries if entries else _test_set_examples(str(test_set))

    seen: set[str] = set()
    unique: list[str] = []
    for rel in relpaths:
        normalized = rel.replace("\\", "/").strip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        dtrx = EXAMPLES_ROOT / normalized / SYSTEM_DTRX_NAME
        if not dtrx.is_file():
            raise UsageError(
                f"Example {normalized!r} has no {SYSTEM_DTRX_NAME} under "
                f"{EXAMPLES_ROOT / normalized}. Pass a directory relative to "
                f"datrix/examples/ (e.g. '01-foundation')."
            )
        unique.append(normalized)
    return unique


# ---------------------------------------------------------------------------
# BEFORE source materialization
# ---------------------------------------------------------------------------


def _extract_archive(tar_path: Path, dest: Path, package: str) -> None:
    """Safely extract a ``git archive`` tar into *dest*.

    Every member path is validated to stay inside *dest* before extraction
    (equivalent protection to the stdlib ``data`` filter, expressed explicitly
    so it holds on every interpreter version).

    Args:
        tar_path: The archive written by ``git archive --output``.
        dest: Extraction root.
        package: Package name, for error messages.

    Raises:
        UsageError: If the archive contains a member escaping *dest*.
    """
    dest_resolved = dest.resolve()
    with tarfile.open(tar_path) as archive:
        for member in archive.getmembers():
            member_target = (dest / member.name).resolve()
            if not member_target.is_relative_to(dest_resolved):
                raise UsageError(
                    f"git archive for package {package!r} contains an unsafe member "
                    f"path {member.name!r} escaping the snapshot dir. Refusing to "
                    f"extract."
                )
        archive.extractall(dest)


def snapshot_packages(
    ref: str, packages: list[str], workspace: Path, snapshot_root: Path
) -> list[Path]:
    """Snapshot each package's ``src/`` at *ref* via READ-ONLY ``git archive``.

    Never uses checkout/reset/stash/restore -- the working tree is not touched
    in any way.

    Args:
        ref: Git ref for the BEFORE state (e.g. ``HEAD``).
        packages: Package directory names (each its own git repo).
        workspace: Monorepo root.
        snapshot_root: Where the snapshots are extracted (cleared first).

    Returns:
        The extracted ``<snapshot>/<pkg>/src`` paths, in package order.

    Raises:
        UsageError: On a missing/non-git package, a failing ``git archive``
            (bad ref, no ``src/`` at that ref), or a missing git executable.
    """
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root)
    snapshot_root.mkdir(parents=True)

    src_paths: list[Path] = []
    for package in packages:
        package_dir = workspace / package
        if not (package_dir / ".git").exists():
            raise UsageError(
                f"Package {package!r} is not a git repository at {package_dir}. "
                f"-Packages takes datrix package directory names (each package is "
                f"its own git repo)."
            )
        tar_path = snapshot_root / f"{package}.tar"
        command = [
            "git", "-C", str(package_dir), "archive", "--format=tar",
            f"--output={tar_path}", ref, "src",
        ]
        logger.debug("snapshot_package cmd=%s", command)
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise UsageError(f"Could not run git ({exc}). Is git on PATH?") from exc
        if completed.returncode != 0:
            raise UsageError(
                f"git archive failed for package {package!r} at ref {ref!r}: "
                f"{completed.stderr.strip()}. Check the ref exists in that package's "
                f"repo and that it contains a src/ directory."
            )
        dest = snapshot_root / package
        dest.mkdir(parents=True)
        _extract_archive(tar_path, dest, package)
        tar_path.unlink()
        src_dir = dest / "src"
        if not src_dir.is_dir():
            raise UsageError(
                f"git archive of {package!r} at {ref!r} produced no src/ directory "
                f"under {dest}. The package must keep its sources under src/."
            )
        src_paths.append(src_dir)
    return src_paths


def build_before_strategy(
    before_ref: str | None,
    packages_arg: str | None,
    before_tree: str | None,
    workspace: Path,
) -> BeforeStrategy:
    """Validate the BEFORE selector and materialize its PYTHONPATH overlay.

    Args:
        before_ref: ``--before-ref`` value.
        packages_arg: ``--packages`` comma-separated value.
        before_tree: ``--before-tree`` value.
        workspace: Monorepo root.

    Returns:
        The strategy carrying the worker PYTHONPATH and report metadata.

    Raises:
        UsageError: When not exactly one strategy is selected, or its inputs
            are invalid.
    """
    packages = _split_csv([packages_arg] if packages_arg else None)
    if bool(before_ref) == bool(before_tree):
        raise UsageError(
            "Pass exactly one BEFORE strategy: -BeforeRef <git-ref> -Packages "
            "<pkg,pkg> (read-only git archive snapshot) OR -BeforeTree <dir> "
            "(prebuilt source overlay)."
        )
    if before_ref:
        if not packages:
            raise UsageError(
                "-BeforeRef requires -Packages <pkg,pkg>: the packages (own git "
                "repos) whose src/ is snapshotted at the ref."
            )
        snapshot_root = workspace.joinpath(*SNAPSHOT_SUBDIRS)
        src_paths = snapshot_packages(before_ref, packages, workspace, snapshot_root)
        return BeforeStrategy(
            pythonpath=os.pathsep.join(str(p) for p in src_paths),
            description=f"git:{before_ref} packages={','.join(packages)}",
            detail={
                "strategy": "git-ref",
                "ref": before_ref,
                "packages": packages,
                "snapshot_src_paths": [str(p) for p in src_paths],
            },
        )
    if packages:
        raise UsageError(
            "-Packages only applies to -BeforeRef; a -BeforeTree overlay is used "
            "as-is on PYTHONPATH."
        )
    tree = Path(str(before_tree)).resolve()
    if not tree.is_dir():
        raise UsageError(
            f"-BeforeTree directory does not exist: {tree}. Pass a prebuilt source "
            f"overlay dir (a src-style dir whose top-level entries are importable "
            f"packages, e.g. a copy of <pkg>/src with the change reverted)."
        )
    return BeforeStrategy(
        pythonpath=str(tree),
        description=f"tree:{tree}",
        detail={"strategy": "tree", "tree": str(tree)},
    )


# ---------------------------------------------------------------------------
# Generation (worker + orchestration)
# ---------------------------------------------------------------------------


def run_worker(output_root: Path, examples: list[str]) -> int:
    """Generate every example into ``output_root/<ex_id>`` via the REAL pipeline.

    Runs inside a dedicated subprocess so the parent's PYTHONPATH choice
    (snapshot overlay for BEFORE, none for AFTER) governs which sources the
    pipeline imports.

    Args:
        output_root: Side root (``.../bef`` or ``.../aft``).
        examples: Example dir relpaths.

    Returns:
        0 when every example generated; 1 on the first failure (reported with
        the example name and the raised error, verbatim).
    """
    _register_language_plugins()
    for rel in examples:
        dtrx = EXAMPLES_ROOT / rel / SYSTEM_DTRX_NAME
        target = output_root / example_id(dtrx)
        try:
            generate_example(dtrx, target)
        except Exception as exc:  # noqa: BLE001 -- reported verbatim, never swallowed
            print(f"{WORKER_FAIL_PREFIX} {rel}: {exc}")
            return 1
        print(f"{WORKER_OK_PREFIX} {rel}")
    return 0


def run_side(
    side: str,
    output_root: Path,
    examples: list[str],
    pythonpath: str | None,
    debug: bool,
) -> None:
    """Run one side's generation in a dedicated worker subprocess.

    The worker env's ``PYTHONPATH`` is set EXACTLY to *pythonpath* (or removed
    when ``None``) -- an inherited value is never passed through, so a stray
    caller PYTHONPATH cannot poison either side.

    Args:
        side: ``BEFORE`` or ``AFTER`` (for failure reporting).
        output_root: Side root; cleared before generating.
        examples: Example dir relpaths.
        pythonpath: The source overlay for the worker, or ``None``.
        debug: Forward ``--debug`` to the worker.

    Raises:
        GenerationError: If the worker exits non-zero; carries the tail of the
            worker's verbatim output.
    """
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath

    command = [sys.executable, str(Path(__file__).resolve()),
               "--generate-worker", str(output_root)]
    for rel in examples:
        command.extend(["--example", rel])
    if debug:
        command.append("--debug")
    logger.debug("run_side side=%s pythonpath=%s", side, pythonpath)

    completed = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    if completed.returncode != 0:
        combined = (completed.stdout + "\n" + completed.stderr).strip()
        tail = "\n".join(combined.splitlines()[-MAX_FAILURE_OUTPUT_LINES:])
        raise GenerationError(side, tail)


def compare_examples(
    examples: list[str], before_root: Path, after_root: Path
) -> list[ExampleComparison]:
    """Byte-diff each example's two generated trees via sha256 manifests.

    Args:
        examples: Example dir relpaths.
        before_root: BEFORE side root.
        after_root: AFTER side root.

    Returns:
        One comparison per example, in input order.
    """
    comparisons: list[ExampleComparison] = []
    for rel in examples:
        ex_id = example_id(EXAMPLES_ROOT / rel / SYSTEM_DTRX_NAME)
        before_manifest = build_manifest(before_root / ex_id)
        after_manifest = build_manifest(after_root / ex_id)
        comparisons.append(
            ExampleComparison(
                example=rel,
                ex_id=ex_id,
                before_files=len(before_manifest),
                after_files=len(after_manifest),
                delta=diff_manifests(before_manifest, after_manifest),
            )
        )
    return comparisons


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_report_json(
    report_path: Path,
    strategy: BeforeStrategy,
    comparisons: list[ExampleComparison],
    before_root: Path,
    after_root: Path,
) -> dict[str, int]:
    """Write report.json naming EVERY added/removed/changed path.

    Args:
        report_path: Destination path.
        strategy: The BEFORE strategy metadata.
        comparisons: Per-example deltas.
        before_root: BEFORE side root.
        after_root: AFTER side root.

    Returns:
        Totals: ``{"added": A, "removed": R, "changed": C, "projects": P}``
        where P counts examples with at least one difference.
    """
    added = sum(len(c.delta.added) for c in comparisons)
    removed = sum(len(c.delta.removed) for c in comparisons)
    changed = sum(len(c.delta.changed) for c in comparisons)
    differing = sum(1 for c in comparisons if not c.delta.is_empty)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "before": strategy.detail,
        "before_output_root": str(before_root),
        "after_output_root": str(after_root),
        "verdict": "IDENTICAL" if added + removed + changed == 0 else "DIFFERENT",
        "examples": [
            {
                "example": c.example,
                "ex_id": c.ex_id,
                "before_files": c.before_files,
                "after_files": c.after_files,
                "changed": c.delta.changed,
                "added": c.delta.added,
                "removed": c.delta.removed,
            }
            for c in comparisons
        ],
        "totals": {
            "examples": len(comparisons),
            "projects_with_differences": differing,
            "added": added,
            "removed": removed,
            "changed": changed,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"added": added, "removed": removed, "changed": changed, "projects": differing}


def _example_md_section(
    comparison: ExampleComparison, before_root: Path, after_root: Path
) -> list[str]:
    """Render one example's report.md section (paths + unified diffs).

    Args:
        comparison: The example's delta.
        before_root: BEFORE side root.
        after_root: AFTER side root.

    Returns:
        Markdown lines.
    """
    delta = comparison.delta
    lines = [
        f"## {comparison.example}",
        "",
        f"before={comparison.before_files} files, after={comparison.after_files} files: "
        f"changed={len(delta.changed)} added={len(delta.added)} removed={len(delta.removed)}",
        "",
    ]
    for title, paths in (("Added", delta.added), ("Removed", delta.removed)):
        if paths:
            lines.append(f"### {title}")
            lines.extend(f"- `{p}`" for p in paths)
            lines.append("")
    if not delta.changed:
        return lines
    lines.append("### Changed")
    before_tree = before_root / comparison.ex_id
    after_tree = after_root / comparison.ex_id
    for rel in delta.changed[:MAX_DIFFED_FILES_PER_EXAMPLE]:
        lines.extend([f"#### `{rel}`", "", "```diff"])
        # render_unified_diff prepends a fixed 6-space report indent; strip
        # exactly that (never lstrip -- a unified diff's leading space is the
        # context-line marker).
        lines.extend(
            line.removeprefix("      ")
            for line in render_unified_diff(rel, before_tree, after_tree)
        )
        lines.extend(["```", ""])
    if len(delta.changed) > MAX_DIFFED_FILES_PER_EXAMPLE:
        lines.append(
            f"... {len(delta.changed) - MAX_DIFFED_FILES_PER_EXAMPLE} more changed "
            f"file(s) not diffed here; every path is listed in report.json."
        )
        lines.append("")
    return lines


def write_report_md(
    report_path: Path,
    strategy: BeforeStrategy,
    comparisons: list[ExampleComparison],
    before_root: Path,
    after_root: Path,
) -> None:
    """Write report.md with per-file unified diffs for changed text files.

    Args:
        report_path: Destination path.
        strategy: The BEFORE strategy metadata.
        comparisons: Per-example deltas.
        before_root: BEFORE side root.
        after_root: AFTER side root.
    """
    lines = [
        "# Byte-identity report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Before: {strategy.description}",
        "",
    ]
    for comparison in comparisons:
        if comparison.delta.is_empty:
            lines.append(f"## {comparison.example}")
            lines.append("")
            lines.append(
                f"BYTE-IDENTICAL ({comparison.before_files} files per side)"
            )
            lines.append("")
        else:
            lines.extend(_example_md_section(comparison, before_root, after_root))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _assert_equal_length_roots(before_root: Path, after_root: Path) -> None:
    """Enforce the equal-length output-root invariant.

    The ruff post-format hook batches files by command-line character count,
    so unequal root path lengths yield phantom formatting diffs. The roots are
    module constants; this guard fails loud if a future edit breaks them.

    Args:
        before_root: BEFORE side root.
        after_root: AFTER side root.

    Raises:
        UsageError: If the absolute path lengths differ.
    """
    if len(str(before_root)) != len(str(after_root)):
        raise UsageError(
            f"Output roots must have EQUAL-LENGTH absolute paths "
            f"({before_root} vs {after_root}): the ruff post-format hook batches "
            f"by command-line length, so unequal roots produce phantom diffs. "
            f"Restore BEFORE_DIRNAME/AFTER_DIRNAME to equal-length names."
        )


def orchestrate(args: argparse.Namespace) -> int:
    """Run the full byte-identity flow (both sides, diff, reports, console).

    Args:
        args: Parsed CLI arguments.

    Returns:
        Process exit code.

    Raises:
        UsageError: On invalid inputs.
        GenerationError: When a side fails to generate.
    """
    workspace = get_datrix_root()
    examples = resolve_examples(args.example, args.test_set)
    strategy = build_before_strategy(
        args.before_ref, args.packages, args.before_tree, workspace
    )

    output_home = workspace.joinpath(*OUTPUT_SUBDIRS)
    before_root = output_home / BEFORE_DIRNAME
    after_root = output_home / AFTER_DIRNAME
    _assert_equal_length_roots(before_root, after_root)

    run_side(SIDE_BEFORE, before_root, examples, strategy.pythonpath, bool(args.debug))
    run_side(SIDE_AFTER, after_root, examples, None, bool(args.debug))

    comparisons = compare_examples(examples, before_root, after_root)
    report_json = (
        Path(args.output).resolve() if args.output else output_home / REPORT_JSON_NAME
    )
    report_md = report_json.with_name(REPORT_MD_NAME)
    totals = write_report_json(report_json, strategy, comparisons, before_root, after_root)
    write_report_md(report_md, strategy, comparisons, before_root, after_root)

    total = totals["added"] + totals["removed"] + totals["changed"]
    if total == 0:
        print(f"IDENTICAL -- {len(examples)} example(s), before={strategy.description}")
    else:
        print(
            f"{total} differences ({totals['added']} added, {totals['removed']} "
            f"removed, {totals['changed']} changed) across {totals['projects']} "
            f"project(s)"
        )
    print(f"Details: {report_json}")
    return EXIT_IDENTICAL if total == 0 else EXIT_DIFFERENCES


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (without the program name).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove a code change is output-neutral: generate the named examples "
            "under a BEFORE code state (git-archive snapshot on PYTHONPATH, or a "
            "prebuilt overlay) and under the working tree, then byte-diff the two "
            "trees via sha256 manifests."
        ),
    )
    parser.add_argument(
        "--example",
        action="append",
        default=None,
        metavar="RELPATH",
        help="Example dir relative to datrix/examples (repeatable; comma-separated).",
    )
    parser.add_argument(
        "--test-set", default=None,
        help="Named test set from scripts/config/test-projects.json.",
    )
    parser.add_argument(
        "--before-ref", default=None,
        help="Git ref for the BEFORE state (READ-ONLY git archive; requires --packages).",
    )
    parser.add_argument(
        "--packages", default=None,
        help="Comma-separated package dir names (own git repos) snapshotted at --before-ref.",
    )
    parser.add_argument(
        "--before-tree", default=None,
        help="Prebuilt BEFORE source overlay dir (prepended to the worker PYTHONPATH).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Override the report.json path (report.md lands next to it). The two "
        "generation roots are fixed and equal-length -- never configurable.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--generate-worker", default=None, metavar="OUTPUT_ROOT", help=argparse.SUPPRESS
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = byte-identical, 1 = differences, 2 = usage
        error or a generation failure.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    # The pipeline logs a stage line per generator at INFO; keep it at WARNING
    # unless --debug (same rationale as reference_example_parity.py).
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.generate_worker:
        worker_examples = _split_csv(args.example)
        if not worker_examples:
            print(f"{WORKER_FAIL_PREFIX} no --example given to the worker")
            return 1
        return run_worker(Path(args.generate_worker), worker_examples)

    try:
        return orchestrate(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except GenerationError as exc:
        print(f"GENERATION FAILED on the {exc.side} side. Worker output tail:")
        print(exc.detail)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
