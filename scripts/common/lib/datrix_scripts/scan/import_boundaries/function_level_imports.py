"""Function-level-import scanner and its ratchet."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.scan.import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_COMMAND,
    PackageInfo,
    _check,
    self_test_check,
    tighten_only_messages,
)

# ---------------------------------------------------------------------------
# I6 Successor Ratchet (invariant I6, DI-4/DI-5)
#
# The literal `DeploymentProvider.` grep is already empty (DI-3 deleted the
# enum). I6's successor form is a closed-world platform-identity CONDITIONAL
# built on the open `ProviderId` value object (datrix_common.plugin.identity)
# instead of the retired enum. These conditionals are legitimate TODAY (DI-4
# scope was reduced to the 3 Python + 1 TypeScript sites; every other site is
# deliberately deferred to DI-5) but must not be allowed to grow while they
# wait for a decision-engine replacement. Only the LANGUAGE (leaf/owner)
# packages are policed here -- unlike I1, this is NOT a shared-layer scan;
# leaf packages are the legitimate
# owners of target identity, so the defect is the CONDITIONAL shape
# itself (branch-per-provider, DI-5's job to collapse), not package location.
#
# The policed set is the discovered taxonomy's ``language_packages``
# (discover_generator_taxonomy), threaded into scan_provider_conditionals by
# main(), so a new language generator is policed by this ratchet from the
# commit that registers its ``datrix.languages`` entry point. A package with
# no src/ tree yet contributes no files and no baseline entries.


# D6.1 second half: the provider-literal pattern's scan scope also extends
# to the DERIVED shared-package set (discover_shared_packages -- the same
# set the I1 ratchet polices, threaded into main() once and passed to
# scan_shared_package_provider_literals below), held at a HARD ZERO (not the
# language packages' decrease-only ratchet against a grandfathered baseline
# -- see check_shared_package_provider_literals below for why the
# enforcement shape is deliberately different): the shared layer must never
# encode platform-specific policy itself.


# ---------------------------------------------------------------------------
# Function-Level-Import Ratchet
#
# The rule: deferred function-level imports move back to module top under a
# decrease-only ratchet. A function-level import is any `Import`/`ImportFrom`
# AST node that is not a direct top-level statement of its module -- nested
# inside a function body, a method body, an `if TYPE_CHECKING:` block, or a
# `try`/`except`.
#
# The ratchet polices the code that was `datrix-common`'s before the
# foundation packages were extracted from it, wherever that code now lives --
# a move must read as a rename, never as the ratchet losing sight of the file:
#   * every src/ file of the packages whose WHOLE tree came out of
#     `datrix-common` (the tuple below: the core itself and the three packages
#     extracted from it whole); and
#   * every file a baseline entry names in any other discovered package -- a
#     former `datrix-common` module that moved into a layer above, whose entry
#     moved with it as a rename.
# The scope is exactly this and no wider: the other packages' own modules were
# never part of this layering effort, and folding them in would admit their
# whole deferral count at once instead of ratcheting the code this baseline
# was frozen over.
#
# Every baseline entry must name a Python file under a discovered package's
# src/ tree (anything else is an inert entry the scan never reads), must count
# at least one import (a zero entry polices nothing), and must carry a written
# reason: the import cycle that forces the deferral (both modules) or its
# measured import cost. An entry failing any of the three fails the flag.
FUNCTION_LEVEL_IMPORT_PACKAGES: tuple[str, ...] = (
    "datrix_common",
    "datrix_semantic",
    "datrix_rdbms_schema",
    "datrix_testing",
)


@dataclass(frozen=True)
class FunctionLevelImportHit:
    """One function-level (non-module-top) import statement in a
    ``datrix-common`` file (invariant I6 successor)."""

    file_path: Path
    line_number: int


def scan_file_for_function_level_imports(
    file_path: Path,
) -> list[FunctionLevelImportHit]:
    """AST-walk *file_path* for function-level imports.

    A hit is any ``ast.Import``/``ast.ImportFrom`` node that is NOT a direct
    top-level statement of the module -- i.e., not a member of ``tree.body``
    itself, but nested one or more levels deeper (inside a function/method
    body, an ``if TYPE_CHECKING:`` block, a ``try``/``except``, etc.).
    Implementation: collect the ``id()`` of every node in ``tree.body`` (the
    top-level statement list) into a set, then ``ast.walk(tree)`` collecting
    every ``Import``/``ImportFrom`` node; a node counts as a hit iff its
    ``id()`` is not in the top-level set.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    top_level_ids = {id(node) for node in tree.body}

    hits: list[FunctionLevelImportHit] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Import, ast.ImportFrom))
            and id(node) not in top_level_ids
        ):
            hits.append(
                FunctionLevelImportHit(file_path=file_path, line_number=node.lineno)
            )
    return hits


def _scan_one_policed_file_for_function_level_imports(
    py_file: Path, monorepo_root: Path
) -> list[FunctionLevelImportHit]:
    """Scan one policed file, exiting 2 when it cannot be read or parsed --
    a policed file the scan cannot read would otherwise escape it silently."""
    try:
        return scan_file_for_function_level_imports(py_file)
    except SyntaxError as e:
        rel_path = py_file.relative_to(monorepo_root)
        print(
            f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
            f"A policed file that cannot be parsed would escape this scan "
            f"(a silent blind spot); fix its syntax or encoding.",
            file=sys.stderr,
        )
        sys.exit(2)
    except (OSError, UnicodeDecodeError) as e:
        rel_path = py_file.relative_to(monorepo_root)
        print(
            f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
            f"cannot be read would escape this scan; resolve the read error.",
            file=sys.stderr,
        )
        sys.exit(2)


def scan_function_level_imports(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    tracked_files: frozenset[str],
) -> dict[Path, list[FunctionLevelImportHit]]:
    """Scan the function-level-import ratchet's policed files.

    The policed files are every ``.py`` file under each of
    ``FUNCTION_LEVEL_IMPORT_PACKAGES``' ``src/`` trees, plus every file in
    *tracked_files* (the baseline's own entries) that lies in another
    package -- a former ``datrix-common`` module that moved up a layer. A
    tracked file that does not exist is not scanned here; it is reported by
    :func:`check_function_level_import_baseline_entries` instead.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        tracked_files: Monorepo-relative paths (forward slashes) the baseline
            names.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).

    Raises:
        SystemExit: (exit 2) when a policed package is not discovered -- its
            whole tree would otherwise leave the scan without a word.
    """
    results: dict[Path, list[FunctionLevelImportHit]] = {}
    policed_dirs: list[Path] = []

    for package_name in FUNCTION_LEVEL_IMPORT_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            print(
                f"ERROR: the function-level-import ratchet polices package "
                f"'{package_name}', but no datrix-* directory under {monorepo_root} "
                f"holds src/{package_name}. Discovered: {sorted(packages)}. A policed "
                f"package that is not discovered would drop its whole tree from the "
                f"scan; restore it, or remove it from FUNCTION_LEVEL_IMPORT_PACKAGES "
                f"together with its baseline entries.",
                file=sys.stderr,
            )
            sys.exit(2)
        policed_dirs.append(package_info.src_dir)
        for py_file in package_info.src_dir.rglob("*.py"):
            hits = _scan_one_policed_file_for_function_level_imports(py_file, monorepo_root)
            if hits:
                results[py_file] = hits

    for file_rel in sorted(tracked_files):
        py_file = monorepo_root / file_rel
        if not py_file.is_file() or any(py_file.is_relative_to(d) for d in policed_dirs):
            continue
        hits = _scan_one_policed_file_for_function_level_imports(py_file, monorepo_root)
        if hits:
            results[py_file] = hits

    return results


@dataclass(frozen=True)
class FunctionLevelImportBaseline:
    """The frozen function-level-import baseline: one count per policed file
    and the written reason that forces each file's surviving deferrals.

    A reason is part of the frozen record, not a comment beside it:
    ``--update-baseline`` reads it back through this type and re-emits it.
    """

    counts: dict[str, int]
    reasons: dict[str, str]


class FunctionLevelImportBaselineError(ValueError):
    """The function-level-import baseline file is malformed."""


def load_function_level_import_baseline(baseline_path: Path) -> FunctionLevelImportBaseline:
    """Load the function-level-import baseline TOML: ``{relative_file:
    frozen_count}`` plus ``{relative_file: reason}`` for every entry that
    carries one.

    Args:
        baseline_path: Path to the function-level-import baseline TOML file.

    Returns:
        The frozen counts and reasons.

    Raises:
        FunctionLevelImportBaselineError: An entry has no string ``file``, no
            integer ``count``, or names a file twice -- a malformed entry is
            never skipped, because a skipped entry would stop policing its file.
    """
    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for index, entry in enumerate(data.get("baseline", [])):
        file_rel = entry.get("file") if isinstance(entry, dict) else None
        count = entry.get("count") if isinstance(entry, dict) else None
        if not isinstance(file_rel, str) or not file_rel or not isinstance(count, int):
            raise FunctionLevelImportBaselineError(
                f"{baseline_path}: [[baseline]] entry #{index + 1} is malformed ({entry!r}). "
                f"Expected: file = \"<monorepo-relative path>\", count = <int>, "
                f"reason = \"<the cycle (both modules) or measured import cost>\". "
                f"Fix the entry; a malformed entry is never skipped."
            )
        if file_rel in counts:
            raise FunctionLevelImportBaselineError(
                f"{baseline_path}: '{file_rel}' has two [[baseline]] entries. "
                f"Expected exactly one per file; merge them into one entry."
            )
        counts[file_rel] = count
        reason = entry.get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons[file_rel] = reason

    return FunctionLevelImportBaseline(counts=counts, reasons=reasons)


def write_function_level_import_baseline(
    baseline_path: Path, counts: dict[str, int], reasons: dict[str, str]
) -> None:
    """Write the function-level-import baseline TOML as ``[[baseline]]
    file=... count=... reason=...`` entries, sorted by file for deterministic
    diffs. Every entry's reason in *reasons* is re-emitted.

    Args:
        baseline_path: Path to the function-level-import baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
        reasons: Mapping of relative file path -> written reason.
    """
    header = (
        "# Function-Level-Import Ratchet Baseline\n"
        "#\n"
        "# Frozen per-file counts of function-level imports (any Import/ImportFrom\n"
        "# AST node that is not a direct top-level statement of its module --\n"
        "# nested in a function/method body, an `if TYPE_CHECKING:` block, or a\n"
        "# `try`/`except`) in the code that was datrix-common's before the\n"
        "# foundation packages were extracted from it: every src/ file of\n"
        "# datrix-common, datrix-semantic, datrix-rdbms-schema and datrix-testing, plus\n"
        "# each file an entry below names in another package (a former\n"
        "# datrix-common module that moved up a layer; its entry moved with it).\n"
        "#\n"
        "# Decrease-only. Any INCREASE in a file's count fails\n"
        "# datrix/scripts/scan/check-import-boundaries.ps1\n"
        "# --check-function-level-imports, which check-import-boundaries.ps1 runs on\n"
        "# every check invocation. --update-baseline only lowers counts and drops\n"
        "# emptied entries; it refuses to raise one. A module that moves keeps its\n"
        "# entry under the new path at the same count (a rename).\n"
        "#\n"
        "# Every entry carries a reason: the import cycle that forces its deferrals\n"
        "# (both modules) or their measured import cost. An entry without one, an\n"
        "# entry naming a file no scan reads, and a zero-count entry all fail the flag.\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
        '#   reason = "the cycle (both modules) or the measured import cost"\n'
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")
        if file_rel in reasons:
            # json.dumps yields a TOML basic string: the escapes it emits
            # (\" \\ \n \r \t \b \f \uXXXX) are all TOML basic-string escapes.
            lines.append(f"reason = {json.dumps(reasons[file_rel])}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_function_level_import_baseline_entries(
    baseline: FunctionLevelImportBaseline,
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> list[str]:
    """Fail-closed consistency check over the baseline's own entries.

    An entry is inert -- it polices nothing -- when its path names no Python
    file under a discovered package's ``src/`` tree (a module moved without
    its entry being renamed, a deleted module, a path outside every package).
    A zero-count entry polices nothing either. An entry without a written
    reason records a deferral nobody has justified. Each of these fails the
    flag, naming the entry, so none can recur silently.

    Args:
        baseline: The loaded baseline.
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root the entries are relative to.

    Returns:
        One message per offending entry, sorted by path.
    """
    src_dirs = [info.src_dir for info in packages.values()]
    messages: list[str] = []
    for file_rel in sorted(baseline.counts):
        path = monorepo_root / file_rel
        if path.suffix != ".py" or not path.is_file():
            messages.append(
                f"{file_rel}: baseline entry names no existing Python file, so no scan "
                f"reads it. A moved module's entry is renamed with it at the same count; "
                f"a deleted module's entry is removed."
            )
        elif not any(path.is_relative_to(src_dir) for src_dir in src_dirs):
            messages.append(
                f"{file_rel}: baseline entry lies outside every discovered package's "
                f"src/ tree, so no scan reads it. Expected a module under "
                f"datrix-*/src/<package>/; remove the entry."
            )
        if baseline.counts[file_rel] <= 0:
            messages.append(
                f"{file_rel}: baseline entry counts {baseline.counts[file_rel]} "
                f"function-level imports; a zero entry polices nothing. Remove it."
            )
        if file_rel not in baseline.reasons:
            messages.append(
                f"{file_rel}: baseline entry carries no reason. Every surviving "
                f"deferral names the import cycle that forces it (both modules) or its "
                f"measured import cost: add reason = \"...\", or promote the imports "
                f"to module top."
            )
    return messages


def lowered_function_level_import_baseline(
    baseline: FunctionLevelImportBaseline,
    current_counts: dict[str, int],
) -> tuple[FunctionLevelImportBaseline, list[str]]:
    """The baseline ``--update-baseline`` writes: every entry lowered to its
    current count, emptied entries dropped, reasons carried across.

    Returns the lowered baseline and the paths of the dropped entries. Never
    raises a count or adds an entry -- the caller refuses the update when
    :func:`check_function_level_import_ratchet` reports any increase.

    Args:
        baseline: The frozen baseline.
        current_counts: Relative file path -> current hit count.

    Returns:
        ``(lowered baseline, dropped entry paths)``.
    """
    counts = {
        file_rel: min(frozen, current_counts[file_rel])
        for file_rel, frozen in baseline.counts.items()
        if current_counts.get(file_rel, 0) > 0
    }
    reasons = {file_rel: reason for file_rel, reason in baseline.reasons.items() if file_rel in counts}
    dropped = sorted(baseline.counts.keys() - counts.keys())
    return FunctionLevelImportBaseline(counts=counts, reasons=reasons), dropped


def check_function_level_import_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose function-level-import count rose above its
    baseline, sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "function-level-import")


def _self_test_function_level_import_scanner() -> bool:
    """scan_file_for_function_level_imports counts zero for module-top
    imports and exactly one for each nested (function/TYPE_CHECKING/
    try-except) import."""
    report_step("Self-test 6/24: function-level-import AST scanner")
    ok = True
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"fli-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cases: tuple[tuple[str, str, int], ...] = (
        (
            "module_top.py",
            "from __future__ import annotations\n\nimport os\nfrom pathlib import Path\n\n\n"
            "def f() -> None:\n    return None\n",
            0,
        ),
        ("function_body.py", "def f() -> object:\n    import json\n\n    return json\n", 1),
        (
            "type_checking_block.py",
            "from __future__ import annotations\n\nfrom typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from pathlib import Path\n\n\n"
            'def f(p: "Path") -> None:\n    return None\n',
            1,
        ),
        (
            "try_except.py",
            "try:\n    import tomllib\nexcept ImportError:\n    tomllib = None\n",
            1,
        ),
    )
    try:
        for filename, source, expected_count in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_function_level_imports(file_path)
            ok &= _check(
                f"{filename}: expected {expected_count} hit(s), got {len(hits)}",
                len(hits) == expected_count,
            )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_module_source(function_level_import_count: int) -> str:
    """A module with exactly *function_level_import_count* function-body imports."""
    lines = ["def f() -> None:"]
    if function_level_import_count == 0:
        lines.append("    return None")
    else:
        for i in range(function_level_import_count):
            lines.append(f"    import json as _json_{i}")
        lines.append("    return None")
    return "\n".join(lines) + "\n"


#: The fixture's policed module, and the former-core module it tracks in a
#: package above the policed set. The tracked module's package is one whose
#: boundary rule is static (no entry-point classification), so the fixture
#: needs no ``pyproject.toml`` for the checker to accept it.
_FLI_FIXTURE_MODULE = "datrix-common/src/datrix_common/sample_module.py"
_FLI_FIXTURE_MOVED_MODULE = "datrix-codegen-common/src/datrix_codegen_common/moved_module.py"
_FLI_FIXTURE_REASON = "sample_module <-> sample_partner: each calls the other at import"


def _self_test_function_level_baseline_text(
    entries: tuple[tuple[str, int, str | None], ...],
) -> str:
    """Baseline TOML text for *entries* -- ``(file, count, reason or None)``."""
    lines: list[str] = []
    for file_rel, count, reason in entries:
        lines.extend(["[[baseline]]", f'file = "{file_rel}"', f"count = {count}"])
        if reason is not None:
            lines.append(f"reason = {json.dumps(reason)}")
        lines.append("")
    return "\n".join(lines)


def _self_test_build_fixture_monorepo(tmp_root: Path, initial_import_count: int) -> Path:
    """Build a minimal isolated monorepo: every policed package, one module
    in datrix-common carrying *initial_import_count* function-level imports,
    one tracked former-core module in a package above the policed set, and a
    reasoned baseline TOML freezing exactly those counts."""
    for package_name in FUNCTION_LEVEL_IMPORT_PACKAGES:
        package_src = tmp_root / package_name.replace("_", "-") / "src" / package_name
        package_src.mkdir(parents=True, exist_ok=True)
        (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = tmp_root / _FLI_FIXTURE_MODULE
    module_path.write_text(_self_test_module_source(initial_import_count), encoding="utf-8")

    moved_path = tmp_root / _FLI_FIXTURE_MOVED_MODULE
    moved_path.parent.mkdir(parents=True, exist_ok=True)
    (moved_path.parent / "__init__.py").write_text("", encoding="utf-8")
    moved_path.write_text(_self_test_module_source(1), encoding="utf-8")

    _self_test_write_function_level_baseline(
        tmp_root,
        (
            (_FLI_FIXTURE_MODULE, initial_import_count, _FLI_FIXTURE_REASON),
            (_FLI_FIXTURE_MOVED_MODULE, 1, _FLI_FIXTURE_REASON),
        ),
    )
    return module_path


def _self_test_write_function_level_baseline(
    tmp_root: Path, entries: tuple[tuple[str, int, str | None], ...]
) -> Path:
    """Write the fixture's function-level-import baseline and return its path."""
    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "function-level-import-baseline.toml"
    baseline_path.write_text(
        _self_test_function_level_baseline_text(entries), encoding="utf-8"
    )
    return baseline_path


def _self_test_run_cli(
    tmp_root: Path, *, update_baseline: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run the boundary scan as a real subprocess against the isolated fixture.

    ``CLI_COMMAND`` is the scan alone, so the nested run never re-runs the
    self-test (which would otherwise spawn this same subprocess again,
    without end).
    """
    command = [
        *CLI_COMMAND,
        "--base-dir",
        str(tmp_root),
        "--check-function-level-imports",
    ]
    if update_baseline:
        command.append("--update-baseline")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_cli_non_vacuity() -> bool:
    """End-to-end proof that --check-function-level-imports actually detects
    a regression: run as a real subprocess against a real, isolated,
    temporarily-mutated fixture tree -- never a simulated one, and never the
    real datrix-common source tree."""
    report_step(
        "Self-test 8/24: function-level-import CLI mutation non-vacuity "
        "(plant a real regression, prove detection, prove it clears on revert)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cli-non-vacuity-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_build_fixture_monorepo(tmp_root, initial_import_count=1)

        clean_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture (count matches baseline) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(_self_test_module_source(2), encoding="utf-8")
        failing_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"mutated fixture (count exceeds baseline) exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_module.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (1 -> 2)",
            "increased from baseline 1 to 2" in failing_result.stdout,
        )

        module_path.write_text(_self_test_module_source(1), encoding="utf-8")
        reverted_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_function_level_scope_and_entries() -> bool:
    """The widened scope and the fail-closed entry check, end to end: a new
    deferral in every policed package is caught, a tracked former-core module
    in a package above is still policed, and an inert, reasonless or empty
    entry each fails the flag and clears when removed. ``--update-baseline``
    refuses to raise a count and lowers one, keeping its reason."""
    report_step(
        "Self-test 9/24: function-level-import scope (every policed package, "
        "tracked moved modules) and fail-closed baseline entries"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"fli-scope-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        _self_test_build_fixture_monorepo(tmp_root, initial_import_count=1)
        clean_entries = (
            (_FLI_FIXTURE_MODULE, 1, _FLI_FIXTURE_REASON),
            (_FLI_FIXTURE_MOVED_MODULE, 1, _FLI_FIXTURE_REASON),
        )

        for package_name in FUNCTION_LEVEL_IMPORT_PACKAGES[1:]:
            planted = (
                tmp_root / package_name.replace("_", "-") / "src" / package_name / "planted.py"
            )
            planted.write_text(_self_test_module_source(1), encoding="utf-8")
            result = _self_test_run_cli(tmp_root)
            ok &= _check(
                f"a new deferral in {package_name} exits 1, got {result.returncode}",
                result.returncode == 1 and "planted.py" in result.stdout,
            )
            planted.unlink()

        moved_path = tmp_root / _FLI_FIXTURE_MOVED_MODULE
        moved_path.write_text(_self_test_module_source(2), encoding="utf-8")
        result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"a tracked former-core module above the policed set is still policed "
            f"(1 -> 2 exits 1), got {result.returncode}",
            result.returncode == 1 and "moved_module.py" in result.stdout,
        )
        moved_path.write_text(_self_test_module_source(1), encoding="utf-8")

        inert_cases: tuple[tuple[str, tuple[str, int, str | None]], ...] = (
            (
                "an entry naming a file that does not exist",
                ("datrix-common/src/datrix_common/moved_away.py", 1, _FLI_FIXTURE_REASON),
            ),
            (
                "an entry outside every package's src/ tree",
                ("datrix/tools/inert_entry.py", 1, _FLI_FIXTURE_REASON),
            ),
            ("an entry without a reason", (_FLI_FIXTURE_MOVED_MODULE, 1, None)),
            ("a zero-count entry", (_FLI_FIXTURE_MOVED_MODULE, 0, _FLI_FIXTURE_REASON)),
        )
        outside_file = tmp_root / "datrix" / "tools" / "inert_entry.py"
        outside_file.parent.mkdir(parents=True, exist_ok=True)
        outside_file.write_text(_self_test_module_source(1), encoding="utf-8")
        for label, planted_entry in inert_cases:
            entries = tuple(
                entry for entry in clean_entries if entry[0] != planted_entry[0]
            ) + (planted_entry,)
            _self_test_write_function_level_baseline(tmp_root, entries)
            result = _self_test_run_cli(tmp_root)
            ok &= _check(
                f"{label} exits 1 naming the entry, got {result.returncode}",
                result.returncode == 1 and planted_entry[0] in result.stdout,
            )
            _self_test_write_function_level_baseline(tmp_root, clean_entries)
            result = _self_test_run_cli(tmp_root)
            ok &= _check(
                f"removing {label} clears the failure, got exit {result.returncode}",
                result.returncode == 0,
            )

        moved_path.write_text(_self_test_module_source(2), encoding="utf-8")
        refused = _self_test_run_cli(tmp_root, update_baseline=True)
        ok &= _check(
            f"--update-baseline refuses to raise a count (exit 1), got {refused.returncode}",
            refused.returncode == 1,
        )
        ok &= _check(
            "the refused update left the baseline unchanged",
            load_function_level_import_baseline(
                tmp_root / "datrix" / "scripts" / "config" / "function-level-import-baseline.toml"
            ).counts
            == {entry[0]: entry[1] for entry in clean_entries},
        )
        moved_path.write_text(_self_test_module_source(0), encoding="utf-8")
        lowered = _self_test_run_cli(tmp_root, update_baseline=True)
        lowered_baseline = load_function_level_import_baseline(
            tmp_root / "datrix" / "scripts" / "config" / "function-level-import-baseline.toml"
        )
        ok &= _check(
            f"--update-baseline lowers and drops an emptied entry, keeping the other's "
            f"reason, got exit {lowered.returncode}",
            lowered.returncode == 0
            and lowered_baseline.counts == {_FLI_FIXTURE_MODULE: 1}
            and lowered_baseline.reasons == {_FLI_FIXTURE_MODULE: _FLI_FIXTURE_REASON},
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The function-level import scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [
        self_test_check(_self_test_function_level_import_scanner),
        self_test_check(_self_test_cli_non_vacuity, "function_level_import_cli_non_vacuity"),
        self_test_check(_self_test_function_level_scope_and_entries),
    ]
