#!/usr/bin/env python3
"""Per-package GeneratedFile-construction ratchet scanner (design 025, Invariant I5).

Counts direct ``GeneratedFile(...)`` constructor calls -- a bare
``GeneratedFile(...)`` call or a module-qualified ``<module>.GeneratedFile(...)``
call -- in every ``.py`` file under each discovered ``datrix-*`` package's
``src/`` tree. Deliberately excludes:

  - Everything under a package's ``tests/`` directory (this scanner only
    walks ``src/``, never ``tests/``).
  - ``datrix-codegen-common/src/datrix_codegen_common/gendsl/executor.py``
    (the declared-file render path's own internals -- constructing
    ``GeneratedFile`` there IS the render mechanism, not a hand-coded
    duplicate of a genDSL declaration).

``GeneratedFile.from_content(...)`` (the factory classmethod) is a distinct
call shape (``Attribute(attr="from_content")``) and is never counted -- only
the direct dataclass constructor matches, per Invariant I5's "direct
GeneratedFile construction outside the declared-render path".

Exit codes:
    0: Every package's count is at or below its frozen baseline (or, with
       --update-baseline, the baseline was successfully frozen/tightened).
    1: At least one package's count exceeds its frozen baseline.
    2: Usage error, missing baseline file, or (with --update-baseline) an
       attempted increase over an EXISTING baseline (the ratchet only
       tightens once a baseline has been frozen). The very first
       --update-baseline run -- when no baseline file exists yet -- is the
       bootstrap freeze and always succeeds regardless of counts; there is
       no prior baseline for a first-ever measurement to "increase" over.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# The declared-file render path's own internals: constructing GeneratedFile
# here IS the render mechanism (executor.py implements declared rendering),
# not a hand-coded duplicate of a declaration. Path is relative to the
# monorepo root, forward slashes.
EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "datrix-codegen-common/src/datrix_codegen_common/gendsl/executor.py",
    }
)


@dataclass(frozen=True)
class PackageInfo:
    """Package metadata for scanning."""

    name: str  # e.g., datrix-codegen-aws (directory name, not the src package)
    src_dir: Path  # e.g., d:/datrix/datrix-codegen-aws/src


def discover_packages(base_dir: Path) -> dict[str, PackageInfo]:
    """Discover every ``datrix-*`` package directory with a ``src/`` tree.

    Args:
        base_dir: Monorepo root directory.

    Returns:
        Mapping of package directory name (e.g. ``datrix-codegen-aws``) to
        its ``PackageInfo``. Packages without a ``src/`` directory (e.g. the
        ``datrix`` showcase repo itself) are skipped.
    """
    packages: dict[str, PackageInfo] = {}
    for candidate in base_dir.iterdir():
        if not candidate.is_dir() or not candidate.name.startswith("datrix-"):
            continue
        src_dir = candidate / "src"
        if not src_dir.exists():
            continue
        packages[candidate.name] = PackageInfo(name=candidate.name, src_dir=src_dir)
    return packages


def count_generated_file_constructions(file_path: Path) -> int:
    """AST-count direct ``GeneratedFile(...)`` constructor calls in *file_path*.

    Matches a bare ``GeneratedFile(...)`` call (``ast.Name(id="GeneratedFile")``)
    or a module-qualified ``<module>.GeneratedFile(...)`` call
    (``ast.Attribute(attr="GeneratedFile")``). Does NOT match
    ``GeneratedFile.from_content(...)`` or any other factory/helper -- only
    the direct dataclass constructor call.

    Args:
        file_path: Path to a Python source file.

    Returns:
        Number of direct ``GeneratedFile(...)`` constructor calls found.

    Raises:
        SyntaxError: propagated from ``ast.parse``.
        OSError: propagated if the file cannot be read.
    """
    source = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(file_path))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "GeneratedFile":
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == "GeneratedFile":
            count += 1
    return count


def scan_package(package: PackageInfo, monorepo_root: Path, verbose: bool) -> int:
    """Sum direct ``GeneratedFile(...)`` construction counts across *package*'s ``src/`` tree.

    Args:
        package: The package to scan.
        monorepo_root: Monorepo root, for excluded-file relative-path matching.
        verbose: Print each file being scanned.

    Returns:
        Total direct construction count for the package (0 if none).
    """
    total = 0
    for py_file in package.src_dir.rglob("*.py"):
        rel_path = py_file.relative_to(monorepo_root).as_posix()
        if rel_path in EXCLUDED_FILES:
            continue
        if verbose:
            print(f"Scanning: {rel_path}", file=sys.stderr)
        try:
            total += count_generated_file_constructions(py_file)
        except SyntaxError as e:
            print(
                f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                f"A policed file that cannot be parsed would escape this scan "
                f"(a silent blind spot); fix its syntax or encoding.",
                file=sys.stderr,
            )
            sys.exit(2)
        except OSError as e:
            print(
                f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                f"cannot be read would escape this scan; resolve the read error.",
                file=sys.stderr,
            )
            sys.exit(2)
    return total


def scan_all_packages(
    packages: dict[str, PackageInfo], monorepo_root: Path, verbose: bool
) -> dict[str, int]:
    """Scan every discovered package. Returns package name -> total count."""
    return {
        name: scan_package(package, monorepo_root, verbose)
        for name, package in sorted(packages.items())
    }


def load_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{package_name: frozen_count}`` from the baseline JSON.

    Args:
        baseline_path: Path to ``generated-file-ratchet.json``.

    Returns:
        The frozen per-package baseline. Empty dict if the file does not
        exist (first-ever run, before ``--update-baseline`` freezes it).
    """
    if not baseline_path.exists():
        return {}
    with baseline_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    baseline = data.get("baseline", {})
    return {str(k): int(v) for k, v in baseline.items()}


def write_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write *counts* to the baseline JSON, sorted by package name.

    Args:
        baseline_path: Path to ``generated-file-ratchet.json``.
        counts: Package name -> current GeneratedFile-construction count.
    """
    payload = {
        "_comment": (
            "I5 GeneratedFile-construction ratchet baseline (design 025, "
            "Invariant I5). Frozen per-package counts of direct "
            "GeneratedFile(...) constructor calls in each package's src/ "
            "tree (tests/ excluded; datrix-codegen-common/.../gendsl/"
            "executor.py excluded as the declared-render path's own "
            "internals). Any INCREASE fails "
            "datrix/scripts/test/check-generated-file-ratchet.py. Decreases "
            "are always allowed and should be captured by re-running with "
            "--update-baseline once a migration task converts hand-coded "
            "construction into a genDSL declaration."
        ),
        "baseline": {name: counts[name] for name in sorted(counts)},
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_ratchet(current_counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """Compare *current_counts* against *baseline*; one message per regressed package.

    A package absent from the baseline has an implicit baseline of 0. Never
    flags a decrease -- the ratchet only tightens.

    Args:
        current_counts: Package name -> current count.
        baseline: Package name -> frozen baseline count.

    Returns:
        Human-readable ratchet-failure messages, sorted by package name.
    """
    messages: list[str] = []
    for name in sorted(current_counts):
        current = current_counts[name]
        frozen = baseline.get(name, 0)
        if current > frozen:
            messages.append(
                f"{name}: GeneratedFile construction count increased from "
                f"baseline {frozen} to {current}. Fix: declare the new "
                f"file(s) in genDSL instead of constructing GeneratedFile "
                f"directly, or (if this increase is an intentional, "
                f"reviewed exception) rerun with --update-baseline -- "
                f"which only accepts decreases once a baseline exists, so "
                f"an increase must be resolved by removing the direct "
                f"construction first."
            )
    return messages


def auto_detect_base_dir(script_path: Path) -> Path:
    """Auto-detect monorepo root by walking up from script location."""
    current = script_path.resolve().parent
    for _ in range(3):
        current = current.parent
    if (current / "datrix-common").exists():
        return current
    raise FileNotFoundError(
        f"Could not auto-detect monorepo root from {script_path}. Use --base-dir."
    )


def _report_update_baseline_increases(increases: list[str]) -> None:
    """Print the standard --update-baseline rejection message for *increases*."""
    print(
        "Error: --update-baseline only permits decreases once a baseline "
        "exists (monotonic ratchet). The following package(s) would "
        "INCREASE the baseline:\n",
        file=sys.stderr,
    )
    for message in increases:
        print(f"  {message}", file=sys.stderr)
    print(
        "\nFix: resolve the increase (declare the file(s) in genDSL) "
        "before updating the baseline.",
        file=sys.stderr,
    )


def _run_update_baseline(
    current_counts: dict[str, int], baseline_path: Path, monorepo_root: Path
) -> int:
    """Handle ``--update-baseline``: bootstrap-freeze or monotonic-tighten *baseline_path*.

    When *baseline_path* does not exist yet, this is the first-ever freeze --
    there is no prior baseline for a fresh measurement to "increase" over, so
    it always succeeds and writes *current_counts* verbatim. When
    *baseline_path* already exists, the write only proceeds if every
    package's new count is <= its existing frozen count (the monotonic
    ratchet: --update-baseline can tighten the baseline, never loosen it).

    Args:
        current_counts: Package name -> current GeneratedFile-construction count.
        baseline_path: Path to the baseline JSON to freeze/tighten.
        monorepo_root: Monorepo root, for the printed relative path.

    Returns:
        0 on success, 2 if an existing baseline would be loosened.
    """
    baseline_already_existed = baseline_path.exists()

    if baseline_already_existed:
        existing_baseline = load_baseline(baseline_path)
        increases = [
            f"{name}: {current_counts[name]} > frozen {existing_baseline.get(name, 0)}"
            for name in sorted(current_counts)
            if current_counts[name] > existing_baseline.get(name, 0)
        ]
        if increases:
            _report_update_baseline_increases(increases)
            return 2

    write_baseline(baseline_path, current_counts)
    action = "Updated" if baseline_already_existed else "Froze initial"
    print(
        f"{action} I5 GeneratedFile-construction baseline: "
        f"{len(current_counts)} package(s) recorded at "
        f"{baseline_path.relative_to(monorepo_root)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="I5 GeneratedFile-construction ratchet scanner (design 025)",
    )
    parser.add_argument("-w", "--warn", action="store_true", help="Report but exit 0")
    parser.add_argument("-b", "--base-dir", type=Path, help="Monorepo root (default: auto-detect)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each file scanned")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Recompute current per-package counts and write the frozen "
            "baseline, then exit 0. If no baseline file exists yet, this is "
            "the bootstrap freeze and always succeeds. If a baseline "
            "already exists, this only succeeds (monotonic ratchet: tighten "
            "never loosen) when every package's new count is <= its "
            "existing baseline; otherwise exits 2 naming the offending "
            "package(s)."
        ),
    )
    args = parser.parse_args()

    if args.base_dir:
        monorepo_root = args.base_dir.resolve()
    else:
        try:
            monorepo_root = auto_detect_base_dir(Path(__file__))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return 2

    packages = discover_packages(monorepo_root)
    if not packages:
        print(f"Error: No datrix packages found in {monorepo_root}", file=sys.stderr)
        return 2

    current_counts = scan_all_packages(packages, monorepo_root, args.verbose)
    baseline_path = monorepo_root / "datrix" / "scripts" / "config" / "generated-file-ratchet.json"

    if args.update_baseline:
        return _run_update_baseline(current_counts, baseline_path, monorepo_root)

    if not baseline_path.exists():
        print(
            f"Error: I5 baseline not found at {baseline_path}. Run "
            f"'check-generated-file-ratchet.py --update-baseline' first to "
            f"freeze the initial baseline.",
            file=sys.stderr,
        )
        return 2

    baseline = load_baseline(baseline_path)
    messages = check_ratchet(current_counts, baseline)

    if messages:
        mode = "Warning" if args.warn else "Error"
        print(f"{mode}: I5 GeneratedFile ratchet failed for {len(messages)} package(s):\n")
        for message in messages:
            print(message)
            print()
        return 0 if args.warn else 1

    if args.verbose:
        print("No I5 GeneratedFile ratchet regressions found.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
