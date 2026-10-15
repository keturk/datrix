#!/usr/bin/env python3
"""Per-package GeneratedFile-construction ratchet scanner (Invariant I5).

Counts direct ``GeneratedFile(...)`` constructor calls -- a bare
``GeneratedFile(...)`` call or a module-qualified ``<module>.GeneratedFile(...)``
call -- in every ``.py`` file under each discovered ``datrix-*`` package's
``src/`` tree. Deliberately excludes:

  - Everything under a package's ``tests/`` directory (this scanner only
    walks ``src/``, never ``tests/``).
  - ``datrix-codegen-kernel/src/datrix_codegen_kernel/dgen/executor.py``
    (the declared-file render path's own internals -- constructing
    ``GeneratedFile`` there IS the render mechanism, not a hand-coded
    duplicate of a DAL generator declaration).

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
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.count_ratchet import (
    RatchetMode,
    compare,
    load_counts_json,
    write_counts_json,
)
from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    NamedCheck,
    gate_argument_parser,
    harness_self_test,
    named_checks,
    report_step,
    run_checks,
)
from datrix_scripts.paths import WORKSPACE_DIR

BASELINE_TABLE = "baseline"

# The declared-file render path's own internals: constructing GeneratedFile
# here IS the render mechanism (executor.py implements declared rendering),
# not a hand-coded duplicate of a declaration. Path is relative to the
# monorepo root, forward slashes.
EXCLUDED_FILES: frozenset[str] = frozenset(
    {
        "datrix-codegen-kernel/src/datrix_codegen_kernel/dgen/executor.py",
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
    return {
        directory.name: PackageInfo(name=directory.name, src_dir=directory / PackageMarker.SRC.value)
        for directory in workspace_package_dirs(base_dir, any_of=frozenset({PackageMarker.SRC}))
    }


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

    Raises:
        ValueError: the file does not exist or its table is malformed. A missing baseline
            never reads as empty; the first freeze is an explicit ``--update-baseline``.
    """
    return load_counts_json(baseline_path, table_key=BASELINE_TABLE)


_BASELINE_COMMENT = (
    "I5 GeneratedFile-construction ratchet baseline "
    "(Invariant I5). Frozen per-package counts of direct "
    "GeneratedFile(...) constructor calls in each package's src/ "
    "tree (tests/ excluded; datrix-codegen-kernel/.../dgen/"
    "executor.py excluded as the declared-render path's own "
    "internals). Any INCREASE fails "
    "datrix/scripts/gates/ratchet/check-generated-file-ratchet.ps1. Decreases "
    "are always allowed and should be captured by re-running with "
    "--update-baseline once a migration converts hand-coded "
    "construction into a DAL generator declaration."
)


def write_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write *counts* to the baseline JSON, sorted by package name."""
    write_counts_json(baseline_path, counts, comment=_BASELINE_COMMENT, table_key=BASELINE_TABLE)


def check_ratchet(current_counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """Compare *current_counts* against *baseline* (tighten-only); one message per regressed package.

    A package absent from the baseline has an implicit baseline of 0. Never
    flags a decrease -- the ratchet only tightens.
    """
    return [
        f"{delta.key}: GeneratedFile construction count increased from "
        f"baseline {delta.frozen} to {delta.current}. Fix: declare the new "
        f"file(s) in DAL generator instead of constructing GeneratedFile "
        f"directly, or (if this increase is an intentional, "
        f"reviewed exception) rerun with --update-baseline -- "
        f"which only accepts decreases once a baseline exists, so "
        f"an increase must be resolved by removing the direct "
        f"construction first."
        for delta in compare(current_counts, baseline, RatchetMode.TIGHTEN_ONLY)
    ]



# ---------------------------------------------------------------------------
# --self-test: plain-Python edge-case checks for this scanner's own functions
# (Invariant I5). Real tempfile.TemporaryDirectory() fixtures and
# assert statements only -- no pytest, no unittest.mock/SimpleNamespace, per
# project test guidelines. These are the same edge cases the (now-deleted)
# pytest suite covered: bare vs. module-qualified GeneratedFile(...) calls,
# .from_content(...) NOT counted, tests/ never scanned, the dgen/executor.py
# exclusion, ratchet regression/no-regression/missing-baseline behavior, and
# package-discovery filtering. Runs automatically as an unconditional first
# step of every invocation (see main()), and can be run in isolation via
# --self-test. Runs through datrix_scripts.gate_harness.
# ---------------------------------------------------------------------------

def _check_bare_constructor_call_counted() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        file_path = Path(tmp) / "sample.py"
        file_path.write_text(
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    return GeneratedFile(path=None, content='', language='python')\n",
            encoding="utf-8",
        )
        count = count_generated_file_constructions(file_path)
        assert count == 1, f"expected 1 bare constructor call, got {count}"


def _check_qualified_constructor_call_counted() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        file_path = Path(tmp) / "sample.py"
        file_path.write_text(
            "import datrix_codegen_kernel.generation.generator as gen\n"
            "def f():\n"
            "    return gen.GeneratedFile(path=None, content='', language='python')\n",
            encoding="utf-8",
        )
        count = count_generated_file_constructions(file_path)
        assert count == 1, f"expected 1 module-qualified constructor call, got {count}"


def _check_from_content_factory_not_counted() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        file_path = Path(tmp) / "sample.py"
        file_path.write_text(
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    return GeneratedFile.from_content(path=None, content='', language='python')\n",
            encoding="utf-8",
        )
        count = count_generated_file_constructions(file_path)
        assert count == 0, f"from_content(...) must never be counted, got {count}"


def _check_multiple_constructions_counted() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        file_path = Path(tmp) / "sample.py"
        file_path.write_text(
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    a = GeneratedFile(path=None, content='a', language='python')\n"
            "    b = GeneratedFile(path=None, content='b', language='python')\n"
            "    return [a, b]\n",
            encoding="utf-8",
        )
        count = count_generated_file_constructions(file_path)
        assert count == 2, f"expected 2 constructor calls, got {count}"


def _check_no_construction_returns_zero() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        file_path = Path(tmp) / "sample.py"
        file_path.write_text("def f():\n    return 1\n", encoding="utf-8")
        count = count_generated_file_constructions(file_path)
        assert count == 0, f"file with no construction must count 0, got {count}"


def _check_tests_directory_never_scanned() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        root = Path(tmp)
        pkg_dir = root / "datrix-codegen-fake"
        src_dir = pkg_dir / "src" / "datrix_codegen_fake"
        src_dir.mkdir(parents=True)
        (src_dir / "gen.py").write_text("x = 1\n", encoding="utf-8")

        tests_dir = pkg_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_gen.py").write_text(
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n"
            "GeneratedFile(path=None, content='', language='python')\n",
            encoding="utf-8",
        )

        package = PackageInfo(name="datrix-codegen-fake", src_dir=pkg_dir / "src")
        total = scan_package(package, root, verbose=False)
        assert total == 0, f"tests/ must never be scanned, got total={total}"


def _check_excluded_executor_file_never_counted() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        root = Path(tmp)
        pkg_dir = root / "datrix-codegen-kernel"
        executor_dir = pkg_dir / "src" / "datrix_codegen_kernel" / "dgen"
        executor_dir.mkdir(parents=True)
        (executor_dir / "executor.py").write_text(
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n"
            "GeneratedFile(path=None, content='', language='python')\n",
            encoding="utf-8",
        )
        # Non-vacuity: the planted file must be the one EXCLUDED_FILES names,
        # so this check cannot pass merely because it planted a path nothing
        # scans or excludes.
        planted = (executor_dir / "executor.py").relative_to(root).as_posix()
        assert planted in EXCLUDED_FILES, (
            f"self-test planted {planted}, which EXCLUDED_FILES does not name: "
            f"{sorted(EXCLUDED_FILES)}"
        )

        package = PackageInfo(name="datrix-codegen-kernel", src_dir=pkg_dir / "src")
        total = scan_package(package, root, verbose=False)
        assert total == 0, f"dgen/executor.py must be excluded, got total={total}"


def _check_ratchet_no_regression_when_equal_to_baseline() -> None:
    messages = check_ratchet({"pkg": 5}, {"pkg": 5})
    assert messages == [], f"equal-to-baseline must not regress, got {messages}"


def _check_ratchet_no_regression_when_below_baseline() -> None:
    messages = check_ratchet({"pkg": 3}, {"pkg": 5})
    assert messages == [], f"below-baseline must not regress, got {messages}"


def _check_ratchet_regression_when_above_baseline() -> None:
    """Adversarial case: a count above baseline MUST produce exactly one
    message naming the package and both the frozen and current counts. If
    this ever silently returns [], the ratchet's whole reason for existing
    (catching a regression) is gone."""
    messages = check_ratchet({"pkg": 6}, {"pkg": 5})
    assert len(messages) == 1, f"expected exactly 1 regression message, got {messages}"
    assert "pkg" in messages[0], f"message must name the package: {messages[0]}"
    assert "5" in messages[0], f"message must cite the frozen baseline 5: {messages[0]}"
    assert "6" in messages[0], f"message must cite the current count 6: {messages[0]}"


def _check_ratchet_missing_baseline_entry_treated_as_zero() -> None:
    messages = check_ratchet({"pkg": 1}, {})
    assert len(messages) == 1, f"expected exactly 1 regression message, got {messages}"
    assert "baseline 0" in messages[0], f"missing entry must read as baseline 0: {messages[0]}"


def _check_discover_packages_only_datrix_prefixed_with_src() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        root = Path(tmp)
        (root / "datrix-codegen-fake" / "src").mkdir(parents=True)
        (root / "datrix-no-src").mkdir()
        (root / "not-datrix-prefixed" / "src").mkdir(parents=True)

        packages = discover_packages(root)

        assert "datrix-codegen-fake" in packages, "datrix-prefixed dir with src/ must be discovered"
        assert "datrix-no-src" not in packages, "datrix-prefixed dir WITHOUT src/ must be excluded"
        assert "not-datrix-prefixed" not in packages, "non-datrix-prefixed dir must be excluded"


def _check_missing_baseline_is_refused_never_read_as_empty() -> None:
    with tempfile.TemporaryDirectory(prefix="ratchet-selftest-") as tmp:
        missing = Path(tmp) / "generated-file-ratchet.json"
        try:
            load_baseline(missing)
        except ValueError as exc:
            assert missing.name in str(exc), f"the refusal must name the file: {exc}"
            return
        raise AssertionError("a missing baseline read as an empty one, which passes every count")


_SELF_TEST_CHECKS: list[NamedCheck] = named_checks(
    [
        _check_bare_constructor_call_counted,
        _check_qualified_constructor_call_counted,
        _check_from_content_factory_not_counted,
        _check_multiple_constructions_counted,
        _check_no_construction_returns_zero,
        _check_tests_directory_never_scanned,
        _check_excluded_executor_file_never_counted,
        _check_ratchet_no_regression_when_equal_to_baseline,
        _check_ratchet_no_regression_when_below_baseline,
        _check_ratchet_regression_when_above_baseline,
        _check_ratchet_missing_baseline_entry_treated_as_zero,
        _check_discover_packages_only_datrix_prefixed_with_src,
        _check_missing_baseline_is_refused_never_read_as_empty,
    ]
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
        "\nFix: resolve the increase (declare the file(s) in DAL generator) "
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
            return EXIT_USAGE

    write_baseline(baseline_path, current_counts)
    action = "Updated" if baseline_already_existed else "Froze initial"
    print(
        f"{action} I5 GeneratedFile-construction baseline: "
        f"{len(current_counts)} package(s) recorded at "
        f"{baseline_path.relative_to(monorepo_root)}"
    )
    return 0


def _scan_and_compare(args: argparse.Namespace) -> int:
    monorepo_root = args.base_dir.resolve() if args.base_dir else WORKSPACE_DIR
    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return EXIT_USAGE

    packages = discover_packages(monorepo_root)
    if not packages:
        print(f"Error: No datrix packages found in {monorepo_root}", file=sys.stderr)
        return EXIT_USAGE

    current_counts = scan_all_packages(packages, monorepo_root, args.verbose)
    baseline_path = monorepo_root / "datrix" / "scripts" / "config" / "generated-file-ratchet.json"
    if args.update_baseline:
        return _run_update_baseline(current_counts, baseline_path, monorepo_root)

    try:
        baseline = load_baseline(baseline_path)
    except ValueError as exc:
        print(
            f"Error: {exc} Run 'check-generated-file-ratchet.ps1 -UpdateBaseline' to freeze it.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    messages = check_ratchet(current_counts, baseline)
    if messages:
        mode = "Warning" if args.warn else "Error"
        print(f"{mode}: I5 GeneratedFile ratchet failed for {len(messages)} package(s):\n")
        for message in messages:
            print(message)
            print()
        return EXIT_PASS if args.warn else EXIT_VIOLATION

    if args.verbose:
        print("No I5 GeneratedFile ratchet regressions found.", file=sys.stderr)
    return EXIT_PASS


def main() -> int:
    parser = gate_argument_parser("I5 GeneratedFile-construction ratchet scanner", update_baseline=True)
    parser.add_argument("-w", "--warn", action="store_true", help="Report but exit 0")
    parser.add_argument("-b", "--base-dir", type=Path, help="Monorepo root (default: auto-detect)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each file scanned")
    args = parser.parse_args()

    if args.harness_self_test:
        return EXIT_PASS if harness_self_test() else EXIT_VIOLATION

    report_step("Self-test: I5 GeneratedFile-construction ratchet scanner edge cases")
    self_test_passed = run_checks(_SELF_TEST_CHECKS)
    if args.self_test:
        return EXIT_PASS if self_test_passed else EXIT_VIOLATION
    if not self_test_passed:
        print(
            "\nError: self-test failed -- refusing to trust the scanner for a "
            "real scan. Fix the scanner before re-running.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    return _scan_and_compare(args)


if __name__ == "__main__":
    sys.exit(main())
