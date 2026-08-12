#!/usr/bin/env python3
"""Parallel-implementation drift report for Datrix codegen packages.

Reports every function (module-level def or class method) defined under two
or more registered target packages' src/ trees, and NOWHERE else
in the monorepo -- a candidate that was never hoisted to datrix-codegen-common
(or was hoisted and one copy left behind). Classifies each such name as
IDENTICAL (every definition's source text is byte-for-byte equal) or DRIFTED
(at least one definition differs), and records a decrease-only baseline of
the DRIFTED count.

**Two axes, one scanner.** `--axis languages` (the default, and the only
behaviour this script had originally) compares the registered
`datrix.languages` packages; `--axis platforms` compares the registered
`datrix.platforms` packages. Each axis carries its OWN baseline file; nothing
is shared between them but the scan itself. Writing a second copy of this
scanner to measure the platform axis would be self-refuting -- a duplicated
implementation inside the instrument that exists to find duplicated
implementations.

**The platform axis is MANY-TO-ONE, and that is why the comparison unit is the
PACKAGE, not the registered name.** Five platform names resolve to three
packages today (`azure` and `azure-vm` both live in `datrix_codegen_azure`;
`docker` and `local` both live in `datrix_codegen_docker`), whereas every
language name maps to its own package. Keying the scan by registered name
would compare `azure` against `azure-vm` -- the same src tree against itself --
and report every function in it as a parallel implementation of itself. Names
sharing a package are therefore folded into ONE entry labelled with the joined
names (e.g. `azure+azure-vm`). For the 1:1 language axis this folding is a
no-op, so the language report is unchanged.

This is deliberately a REPORT with a count baseline, not a pass/fail gate on
individual names: a name-keyed check cannot distinguish an intentional
per-language emission difference (e.g. a `_render_endpoint_handler` method,
which must legitimately differ per target language) from a genuine
unreconciled divergence, and a gate that cannot make that distinction gets
turned off. Classification of drifted groups is a separate, deliberate,
human-reviewed pass over this report's output.

The target set is derived from shared.registered_targets at runtime --
never a hardcoded list -- so installing a fifth datrix-codegen-<lang> package
(or a fourth platform package) extends this report's coverage automatically.
The "everywhere else" side is likewise pure filesystem discovery over every
`datrix-*` package directory with a `src/` tree (mirrors
dev/check-import-boundaries.py's own `discover_packages`) -- never a hardcoded
package list. Note that "everywhere else" is axis-relative: on the platform
axis the language packages are part of the exclusion set and vice versa, so a
name shared between a language and a platform package is reported by neither.

Usage:
    python parallel_implementation_drift.py                        # languages
    python parallel_implementation_drift.py --axis platforms
    python parallel_implementation_drift.py --self-test            # non-vacuity only
    python parallel_implementation_drift.py --axis platforms --update-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

# Add scripts/library to sys.path to import shared.registered_targets (this
# file lives at library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.errors.plugin import PluginError  # noqa: E402
from datrix_common.plugin.registry import (  # noqa: E402
    LANGUAGES_GROUP,
    PLATFORM_GROUP,
    entry_points,
)
from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    registered_platform_names,
)

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/parallel_implementation_drift.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root. Mirrors
# reference_example_parity.py's own identical-depth path math.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]
WORKSPACE_ROOT: Path = _HERE.parents[4]
DRIFT_BASELINE_PATH: Path = DATRIX_DIR / "scripts" / "config" / "parallel-implementation-drift-baseline.json"
PLATFORM_DRIFT_BASELINE_PATH: Path = DATRIX_DIR / "scripts" / "config" / "platform-implementation-drift-baseline.json"

#: The two comparison axes. Each carries its own registered-name resolver, its
#: own entry-point group (for on-disk package resolution), and its OWN baseline
#: file -- the axes never share a ratchet.
AXIS_LANGUAGES: Final[str] = "languages"
AXIS_PLATFORMS: Final[str] = "platforms"
_AXIS_NAME_RESOLVERS: Final[dict[str, Callable[[], frozenset[str]]]] = {
    AXIS_LANGUAGES: registered_language_names,
    AXIS_PLATFORMS: registered_platform_names,
}
_AXIS_ENTRY_POINT_GROUPS: Final[dict[str, str]] = {
    AXIS_LANGUAGES: LANGUAGES_GROUP,
    AXIS_PLATFORMS: PLATFORM_GROUP,
}
_AXIS_BASELINE_PATHS: Final[dict[str, Path]] = {
    AXIS_LANGUAGES: DRIFT_BASELINE_PATH,
    AXIS_PLATFORMS: PLATFORM_DRIFT_BASELINE_PATH,
}

#: Separator joining the registered names that share ONE package into a single
#: comparison entry (see the module docstring's many-to-one paragraph).
_SHARED_PACKAGE_LABEL_SEPARATOR: Final[str] = "+"

_MIN_TARGETS_FOR_COMPARISON: Final[int] = 2

#: Directory-name prefix identifying a Datrix package at the workspace root
#: (e.g. "datrix-common", "datrix-codegen-python"). The `datrix` showcase
#: repo itself has no trailing hyphen and is never matched.
_PACKAGE_DIR_PREFIX: Final[str] = "datrix-"
#: Source subdirectory name every scanned package's importable code lives under.
_SRC_SUBDIR_NAME: Final[str] = "src"
#: `ast.stmt` attribute names whose value is itself a statement list this
#: scanner must descend into to find a def nested inside a non-function,
#: non-class container (If/While/For/With/Try's main body + else + finally).
_CONTAINER_BODY_ATTRS: Final[tuple[str, ...]] = ("body", "orelse", "finalbody")

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: Self-test-only synthetic package names, chosen to be unmistakably not one
#: of the real registered languages -- proving the scan is driven by the
#: injected package map, never a hardcoded literal.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_LANGUAGE_C: Final[str] = "self_test_lang_c"
_SELF_TEST_SHARED_HELPER_NAME: Final[str] = "self_test_shared_helper"

_FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class FunctionDeclaration:
    """One `def`/`async def` (module-level or class method) in a language
    package's src/ tree."""

    package: str  # registered language name, e.g. "python"
    file_path: Path
    line_number: int
    qualified_name: str  # e.g. "ClassName.method_name" or "bare_function_name"
    source_text: str  # verbatim source, decorators included


@dataclass(frozen=True)
class ParallelImplementationGroup:
    """Every declaration of ONE bare function/method name across >=2
    language packages, verified absent from every other datrix-* package."""

    name: str
    declarations: tuple[FunctionDeclaration, ...]  # one per declaration site
    verdict: Literal["identical", "drifted"]


# ---------------------------------------------------------------------------
# Filesystem package discovery
# ---------------------------------------------------------------------------


def _discover_all_package_locations(monorepo_root: Path) -> dict[str, Path]:
    """Every `datrix-*` package directory with a `src/<import_name>/` tree,
    mapped `import_name -> src_dir`.

    Pure filesystem discovery -- mirrors `dev/check-import-boundaries.py`'s
    own `discover_packages`. No `datrix-codegen-{lang}` naming-convention
    assumption anywhere: the import name is read off whichever directory
    actually exists under `src/`, never synthesized from a language name.

    Args:
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        `{import_name: src_dir}` for every package with a resolvable src tree.
    """
    locations: dict[str, Path] = {}
    for candidate in sorted(monorepo_root.iterdir()):
        if not candidate.is_dir() or not candidate.name.startswith(_PACKAGE_DIR_PREFIX):
            continue
        src_dir = candidate / _SRC_SUBDIR_NAME
        if not src_dir.is_dir():
            continue
        package_dirs = sorted(d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix"))
        if not package_dirs:
            continue
        locations[package_dirs[0].name] = package_dirs[0]
    return locations


def fold_names_by_src_dir(names_by_src_dir: dict[Path, list[str]]) -> dict[str, Path]:
    """Fold registered names sharing ONE package into a single labelled entry.

    Pure and dependency-injected so the self-test can exercise the many-to-one
    case directly, without a live registry that happens to contain one.

    Args:
        names_by_src_dir: `{src_dir: [registered names backed by it]}`.

    Returns:
        `{joined label: src_dir}`, one entry per distinct package.
    """
    return {_SHARED_PACKAGE_LABEL_SEPARATOR.join(sorted(names)): src_dir for src_dir, names in names_by_src_dir.items()}


def _entry_point_module_roots(axis: str) -> dict[str, str]:
    """Map each registered target name on *axis* to its entry point's module root.

    Read from the entry point's DECLARED module rather than by importing and
    instantiating the plugin: a platform plugin needs generation context to
    construct, and this report only needs to know which package the code lives
    in. For the language axis this is provably the same answer the plugin-class
    route gives -- asserted every run by the self-test's
    `_language_entry_point_roots_match_plugin_roots` check, so the two can
    never silently diverge.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.

    Returns:
        `{registered name: top-level module name}`.
    """
    group = _AXIS_ENTRY_POINT_GROUPS[axis]
    return {ep.name: ep.module.split(".")[0] for ep in entry_points(group=group)}


def discover_target_package_src_dirs(axis: str, target_names: frozenset[str], monorepo_root: Path) -> dict[str, Path]:
    """Resolve the registered target names on *axis* to their packages'
    `src/<import_name>` directories, matched against the filesystem package map
    -- never a hardcoded `datrix-codegen-{name}` string-format assumption.

    **Names sharing one package are folded into a single entry** whose label
    joins them (e.g. `azure+azure-vm`), because the comparison unit is the
    package: two registered names backed by the same src tree are not parallel
    implementations of each other. On the 1:1 language axis every group has
    exactly one member, so each label is just the language name and the report
    is unchanged.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.
        target_names: Registered names on that axis to resolve.
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        `{label: absolute src package directory}`, one entry per distinct
        package.

    Raises:
        ValueError: If a registered name resolves to an import root with no
            matching on-disk package, or has no entry point at all -- a real
            configuration error, never silently skipped (shrinking the target
            set quietly would hide the exact drift this report exists to
            surface).
    """
    all_locations = _discover_all_package_locations(monorepo_root)
    module_roots = _entry_point_module_roots(axis)

    names_by_src_dir: dict[Path, list[str]] = {}
    for name in sorted(target_names):
        import_name = module_roots.get(name)
        if import_name is None:
            raise ValueError(
                f"Registered {axis} target {name!r} has no entry point in group "
                f"{_AXIS_ENTRY_POINT_GROUPS[axis]!r}. Registered entry points: "
                f"{sorted(module_roots)}."
            )
        src_dir = all_locations.get(import_name)
        if src_dir is None:
            raise ValueError(
                f"Could not resolve an on-disk src/ directory for {axis} target "
                f"{name!r} (its registered plugin lives in module root "
                f"{import_name!r}). Expected a 'datrix-*' directory under "
                f"{monorepo_root} whose src/ tree contains a {import_name!r} "
                f"package directory. Discovered package roots: "
                f"{sorted(all_locations)}."
            )
        names_by_src_dir.setdefault(src_dir, []).append(name)

    folded = fold_names_by_src_dir(names_by_src_dir)
    if len(folded) < len(target_names):
        logger.info(
            "axis=%s folded %d registered name(s) into %d distinct package(s): %s",
            axis,
            len(target_names),
            len(folded),
            sorted(folded),
        )
    return folded


def discover_all_other_package_src_dirs(monorepo_root: Path, exclude_dirs: frozenset[Path]) -> list[Path]:
    """Every OTHER datrix-* package's src/ tree -- literally every discovered
    package directory not already covered by
    `discover_language_package_src_dirs` (datrix-common, datrix-codegen-common,
    datrix-cli, every non-language datrix-codegen-* package, datrix-extensions,
    datrix-language, and any future package) -- the "nowhere else" half of
    the report's own definition. Never a hardcoded package list: a new
    `datrix-*` package appearing on disk is picked up automatically.

    Args:
        monorepo_root: The workspace root containing every `datrix-*` checkout.
        exclude_dirs: The set of language-package src dirs already covered
            by `discover_language_package_src_dirs`.

    Returns:
        Sorted list of every other discovered package's src directory.
    """
    all_locations = _discover_all_package_locations(monorepo_root)
    return sorted(src_dir for src_dir in all_locations.values() if src_dir not in exclude_dirs)


# ---------------------------------------------------------------------------
# AST scanning
# ---------------------------------------------------------------------------


def _collect_defs(body: list[ast.stmt], enclosing_class: str | None) -> list[tuple[_FunctionDefNode, str | None]]:
    """Recursively collect every module-level or class-method function def
    reachable through non-function statement containers (If/While/For/With/
    Try), pairing each with its nearest enclosing class name (None if none).

    Never descends into a FunctionDef/AsyncFunctionDef's own body -- a
    function nested inside another function is a closure, not a
    module-level-or-class-method declaration this report tracks. A class
    nested inside another class resets `enclosing_class` to its own name
    (single-level qualification, matching `ClassName.method_name`).

    Args:
        body: A statement list (a module body or a class body).
        enclosing_class: The nearest enclosing class's name, or None.

    Returns:
        `(node, enclosing_class)` pairs, in source order.
    """
    found: list[tuple[_FunctionDefNode, str | None]] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            found.extend(_collect_defs(stmt.body, stmt.name))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((stmt, enclosing_class))
            continue
        for attr in _CONTAINER_BODY_ATTRS:
            nested_body = getattr(stmt, attr, None)
            if nested_body:
                found.extend(_collect_defs(nested_body, enclosing_class))
        for handler in getattr(stmt, "handlers", ()):
            found.extend(_collect_defs(handler.body, enclosing_class))
    return found


def _decorated_source_segment(source_lines: list[str], node: _FunctionDefNode) -> str:
    """The verbatim source text of *node*, INCLUDING its decorators.

    `ast.get_source_segment` anchors at the `def` line and excludes
    decorators; a decorator difference between two otherwise-identical
    bodies is itself a real behavioral divergence this report must not
    hide, so decorators are folded into the compared text by taking whole
    source lines from the first decorator's line (or the `def` line, if
    undecorated) through the function's last line. Whitespace/formatting is
    NEVER normalized -- the report's own rationale is that even a small
    divergence should surface as "drifted".

    Args:
        source_lines: The file's source, split with `splitlines(keepends=True)`.
        node: The function/method AST node.

    Returns:
        The decorator(s) + def + body, as literal source text.

    Raises:
        ValueError: If `node.end_lineno` is unavailable (should not happen
            for a module parsed by a Python new enough to set it).
    """
    if node.end_lineno is None:
        raise ValueError(
            f"AST node for {node.name!r} at line {node.lineno} has no "
            f"end_lineno -- expected ast.parse() to populate it "
            f"(requires Python >= 3.8)."
        )
    start_line = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    return "".join(source_lines[start_line - 1 : node.end_lineno])


def collect_function_declarations(src_dir: Path, package: str) -> list[FunctionDeclaration]:
    """AST-walk every `.py` file under `src_dir` for module-level and
    class-method function/method declarations, recording each as one
    `FunctionDeclaration` with its exact source text (decorators included).

    Args:
        src_dir: A package's source root (e.g. a language's
            `src/datrix_codegen_python` directory, or any other package's
            `src/<import_name>` directory).
        package: A label stored on every returned declaration (a registered
            language name for a language package, or any other identifying
            label for a non-language package -- purely descriptive).

    Returns:
        Every module-level or class-method function/method declaration
        found, in file-then-source order. Empty if `src_dir` does not exist.

    Raises:
        SyntaxError: If a `.py` file under `src_dir` cannot be parsed.
    """
    declarations: list[FunctionDeclaration] = []
    if not src_dir.is_dir():
        return declarations
    for py_file in sorted(src_dir.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            raise SyntaxError(
                f"Failed to parse {py_file} while scanning package "
                f"{package!r} for parallel-implementation candidates: {exc}"
            ) from exc
        source_lines = source.splitlines(keepends=True)
        for node, enclosing_class in _collect_defs(tree.body, None):
            qualified_name = f"{enclosing_class}.{node.name}" if enclosing_class else node.name
            source_text = _decorated_source_segment(source_lines, node).rstrip("\n")
            declarations.append(
                FunctionDeclaration(
                    package=package,
                    file_path=py_file,
                    line_number=node.lineno,
                    qualified_name=qualified_name,
                    source_text=source_text,
                )
            )
    return declarations


# ---------------------------------------------------------------------------
# Core scan (pure, dependency-injected)
# ---------------------------------------------------------------------------


def find_parallel_implementations(
    target_src_dirs: dict[str, Path],
    other_package_src_dirs: list[Path],
) -> list[ParallelImplementationGroup]:
    """Core scan: find every bare function/method name defined in >= 2 of
    `target_src_dirs` and in ZERO of `other_package_src_dirs`.

    Dependency-injected, no entry-point/registry calls inside this function
    -- the CLI boundary in `main()` is the only place that resolves the live
    registry, so this function is what the self-test exercises directly with
    a synthetic package map.

    Args:
        target_src_dirs: `{label: src_dir}` for every package to compare, one
            entry per DISTINCT package (registered names sharing a package are
            already folded by `discover_target_package_src_dirs`).
        other_package_src_dirs: Every OTHER package's src dir -- a name
            appearing here excludes that name from the report entirely.

    Returns:
        One `ParallelImplementationGroup` per qualifying bare name, sorted
        by name. `verdict` is "identical" iff every declaration's
        `source_text` is equal across the whole group, else "drifted".
    """
    by_bare_name: dict[str, list[FunctionDeclaration]] = {}
    for package, src_dir in target_src_dirs.items():
        for decl in collect_function_declarations(src_dir, package):
            bare_name = decl.qualified_name.rsplit(".", 1)[-1]
            by_bare_name.setdefault(bare_name, []).append(decl)

    other_bare_names: set[str] = set()
    for src_dir in other_package_src_dirs:
        label = f"other:{src_dir.parent.parent.name}"
        for decl in collect_function_declarations(src_dir, label):
            other_bare_names.add(decl.qualified_name.rsplit(".", 1)[-1])

    groups: list[ParallelImplementationGroup] = []
    for bare_name, declarations in by_bare_name.items():
        distinct_packages = {d.package for d in declarations}
        if len(distinct_packages) < _MIN_TARGETS_FOR_COMPARISON:
            continue
        if bare_name in other_bare_names:
            continue
        source_texts = {d.source_text for d in declarations}
        verdict: Literal["identical", "drifted"] = "identical" if len(source_texts) == 1 else "drifted"
        groups.append(ParallelImplementationGroup(name=bare_name, declarations=tuple(declarations), verdict=verdict))
    return sorted(groups, key=lambda group: group.name)


def _require_min_targets(axis: str, comparable_labels: frozenset[str]) -> None:
    """Raise if fewer than `_MIN_TARGETS_FOR_COMPARISON` COMPARABLE targets
    remain -- the CLI-facing guard against a vacuous parallel-implementation
    comparison. Exercised directly by the self-test (never through a live
    entry-point scan) and by `main()` against the real registered set.

    Counts DISTINCT PACKAGES, not registered names: on the platform axis five
    names fold into three packages, and a hypothetical axis whose every name
    shared one package would be vacuous no matter how many names it had.

    Args:
        axis: The axis being validated, named in the error.
        comparable_labels: The folded package labels to validate.

    Raises:
        ValueError: If fewer than `_MIN_TARGETS_FOR_COMPARISON` remain,
            naming how many ARE comparable.
    """
    if len(comparable_labels) < _MIN_TARGETS_FOR_COMPARISON:
        raise ValueError(
            f"Parallel-implementation drift comparison requires at least "
            f"{_MIN_TARGETS_FOR_COMPARISON} distinct registered "
            f"'datrix.{axis}' packages; got {len(comparable_labels)} "
            f"({sorted(comparable_labels)}). Registered names that share one "
            f"package are folded into a single comparison entry, so a name "
            f"count above this floor does not imply a comparable package count "
            f"above it."
        )


# ---------------------------------------------------------------------------
# Baseline (decrease-only ratchet)
# ---------------------------------------------------------------------------


def load_drift_baseline(path: Path = DRIFT_BASELINE_PATH) -> int:
    """Load the decrease-only `drifted_count` baseline.

    Args:
        path: The baseline file. Defaults to the real committed file; tests
            pass a synthetic temp path.

    Returns:
        The recorded count, or 0 if the file does not exist yet (first-ever
        run, before `--update-baseline` freezes it).

    Raises:
        ValueError: If the file exists but is malformed (not an object with
            a non-negative integer `drifted_count` field).
    """
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    count = data.get("drifted_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            f"Malformed {path}: expected an object with a non-negative integer 'drifted_count' field, got {data!r}."
        )
    return count


def write_drift_baseline(count: int, path: Path = DRIFT_BASELINE_PATH, axis: str = AXIS_LANGUAGES) -> None:
    """Write `count` to the baseline JSON. Called ONLY by `--update-baseline`,
    a deliberate, manual re-freeze (mirrors `write_blessed_count`'s role for
    `regen-parity-baselines.ps1` -- the check side of the ratchet is
    `check_drift_ratchet`, applied on every ordinary run against whatever was
    last frozen here).

    Args:
        count: The freshly computed drifted-group count.
        path: The baseline file to write. Defaults to the real committed
            file; tests pass a synthetic temp path.
        axis: The axis this baseline belongs to, named in the file's comment
            so the two baselines can never be mistaken for each other.
    """
    axis_flag = "" if axis == AXIS_LANGUAGES else f" -Axis {axis}"
    payload = {
        "_comment": [
            "Decrease-only ratchet: the count of DRIFTED parallel-implementation",
            f"groups reported by parallel-implementation-drift-gate.ps1{axis_flag} (a",
            "function name defined identically-in-shape but divergent-in-source",
            f"across two or more registered datrix.{axis} PACKAGES, and nowhere",
            "else in the monorepo). Registered names sharing one package are",
            "folded into a single comparison entry, so this counts packages, not",
            "names. A run whose LIVE drifted count is HIGHER than this value",
            "fails -- new drift appeared with nothing reconciling it.",
            f"parallel-implementation-drift-gate.ps1{axis_flag} -UpdateBaseline is",
            "the only writer; do not hand-guess the number.",
        ],
        "drifted_count": count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_drift_ratchet(current_drifted_count: int, baseline_count: int) -> str | None:
    """Compare the live drifted-group count against the recorded ratchet.

    Args:
        current_drifted_count: Freshly computed drifted-group count.
        baseline_count: The pinned count (`load_drift_baseline`).

    Returns:
        A failure message if `current_drifted_count > baseline_count`, else
        None. Never flags a DECREASE -- the ratchet only tightens; drift
        reconciled by a later fix re-pins the baseline lower via
        `--update-baseline`.
    """
    if current_drifted_count > baseline_count:
        return (
            f"PARALLEL-IMPLEMENTATION DRIFT REGRESSION: {current_drifted_count} "
            f"drifted parallel-implementation group(s) found, but the recorded "
            f"baseline expects at most {baseline_count}. New drift appeared "
            f"with nothing reconciling it -- reconcile the new divergence(s), "
            f"or if reviewed and intentional, re-run with --update-baseline."
        )
    return None


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    if condition:
        print(f"[OK] {label}")
    else:
        print(f"[FAIL] {label}")
    return condition


def run_non_vacuity_self_test() -> bool:
    """Prove `find_parallel_implementations` is driven entirely by its
    injected package maps, never a hardcoded language list, and that the
    CLI-facing minimum-target guard actually refuses a single-target map.

    Returns:
        True iff every assertion passed.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix="parallel-drift-selftest-"))
    ok = True
    try:
        lang_a_src = tmp_root / "lang_a"
        lang_b_src = tmp_root / "lang_b"
        other_src = tmp_root / "other_pkg"
        for directory in (lang_a_src, lang_b_src, other_src):
            directory.mkdir(parents=True, exist_ok=True)

        shared_body = f"def {_SELF_TEST_SHARED_HELPER_NAME}(value: str) -> str:\n    return value.strip()\n"
        (lang_a_src / "module.py").write_text(shared_body, encoding="utf-8")
        (lang_b_src / "module.py").write_text(shared_body, encoding="utf-8")
        (other_src / "module.py").write_text("def unrelated() -> None:\n    pass\n", encoding="utf-8")

        groups = find_parallel_implementations(
            {_SELF_TEST_LANGUAGE_A: lang_a_src, _SELF_TEST_LANGUAGE_B: lang_b_src},
            [other_src],
        )
        matching = [g for g in groups if g.name == _SELF_TEST_SHARED_HELPER_NAME]
        ok &= _assert(len(matching) == 1, "identical synthetic pair reports exactly one group")
        ok &= _assert(
            bool(matching) and matching[0].verdict == "identical",
            "identical pair verdict is 'identical'",
        )

        # Mutate B to diverge by one token.
        (lang_b_src / "module.py").write_text(
            shared_body.replace("value.strip()", "value.strip().lower()"),
            encoding="utf-8",
        )
        groups_after_drift = find_parallel_implementations(
            {_SELF_TEST_LANGUAGE_A: lang_a_src, _SELF_TEST_LANGUAGE_B: lang_b_src},
            [other_src],
        )
        drifted = [g for g in groups_after_drift if g.name == _SELF_TEST_SHARED_HELPER_NAME]
        ok &= _assert(
            bool(drifted) and drifted[0].verdict == "drifted",
            "one-token divergence reports 'drifted'",
        )

        # A third, non-hardcoded synthetic language -- proves no fixed language count.
        lang_c_src = tmp_root / "lang_c"
        lang_c_src.mkdir(parents=True, exist_ok=True)
        (lang_c_src / "module.py").write_text(shared_body, encoding="utf-8")
        groups_three = find_parallel_implementations(
            {_SELF_TEST_LANGUAGE_A: lang_a_src, _SELF_TEST_LANGUAGE_C: lang_c_src},
            [other_src],
        )
        ok &= _assert(
            any(g.name == _SELF_TEST_SHARED_HELPER_NAME for g in groups_three),
            "a third, never-hardcoded synthetic language is picked up with no code change",
        )

        # "Nowhere else": add the same bare name to the OTHER-package tree.
        (other_src / "collision.py").write_text(shared_body, encoding="utf-8")
        groups_excluded = find_parallel_implementations(
            {_SELF_TEST_LANGUAGE_A: lang_a_src, _SELF_TEST_LANGUAGE_B: lang_b_src},
            [other_src],
        )
        ok &= _assert(
            not any(g.name == _SELF_TEST_SHARED_HELPER_NAME for g in groups_excluded),
            "a name also present in an 'other' package is excluded even though >=2 language packages define it",
        )

        # >=2-registered-targets refusal: the CLI-facing guard, exercised
        # directly against a synthetic single-language map (never through a
        # live entry-point scan).
        try:
            _require_min_targets(AXIS_LANGUAGES, frozenset({_SELF_TEST_LANGUAGE_A}))
            guard_refused = False
        except ValueError:
            guard_refused = True
        ok &= _assert(
            guard_refused,
            "single-target guard refuses a one-target map (never a silent pass)",
        )

        # Many-to-one folding: two registered names backed by ONE package must
        # collapse to a single comparison entry, or the scan would compare that
        # package's src tree against itself and report every function in it.
        shared_dir = tmp_root / "shared_pkg"
        folded = fold_names_by_src_dir({shared_dir: ["beta", "alpha"], lang_a_src: [_SELF_TEST_LANGUAGE_A]})
        ok &= _assert(
            len(folded) == 2 and "alpha+beta" in folded,
            "two names sharing one package fold into one entry, labelled with both",
        )
        try:
            _require_min_targets(AXIS_PLATFORMS, frozenset(fold_names_by_src_dir({shared_dir: ["beta", "alpha"]})))
            fold_guard_refused = False
        except ValueError:
            fold_guard_refused = True
        ok &= _assert(
            fold_guard_refused,
            "an axis whose every name shares ONE package is refused as vacuous, even though it has 2 registered names",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    ok &= _assert(
        _language_entry_point_roots_match_plugin_roots(),
        "entry-point module root equals the resolved plugin class's module root "
        "for every registered language (the two package-resolution routes agree)",
    )
    return ok


def _language_entry_point_roots_match_plugin_roots() -> bool:
    """Prove the entry-point route this scanner uses agrees with the
    plugin-class route it replaced, for every registered language.

    `discover_target_package_src_dirs` reads the entry point's declared module
    instead of importing and instantiating the plugin, because a platform
    plugin needs generation context to construct. That substitution is only
    safe while the two routes give the same package for every target, so it is
    re-proven on every run rather than assumed once. Languages are the only
    axis that can be checked this way -- they are the axis whose plugins are
    constructible without generation context.

    Returns:
        True iff every registered language's entry-point module root equals
        its resolved `LanguagePlugin` class's module root.
    """
    from datrix_common.generation.discovery import get_language_plugin

    module_roots = _entry_point_module_roots(AXIS_LANGUAGES)
    for name in sorted(registered_language_names()):
        plugin_root = type(get_language_plugin(name)).__module__.split(".")[0]
        if module_roots.get(name) != plugin_root:
            logger.error(
                "package-resolution routes disagree for language %r: entry point says %r, plugin class says %r",
                name,
                module_roots.get(name),
                plugin_root,
            )
            return False
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _log_report(groups: list[ParallelImplementationGroup], target_count: int, axis: str) -> None:
    """Log the per-name verdict lines plus the summary line."""
    drifted = [g for g in groups if g.verdict == "drifted"]
    identical = [g for g in groups if g.verdict == "identical"]
    for group in drifted:
        locations = ", ".join(f"{decl.package}:{decl.file_path}:{decl.line_number}" for decl in group.declarations)
        logger.info("DRIFTED name=%s locations=[%s]", group.name, locations)
    for group in identical:
        logger.debug(
            "identical name=%s packages=%s",
            group.name,
            sorted({d.package for d in group.declarations}),
        )
    logger.info(
        "PARALLEL-IMPLEMENTATION DRIFT REPORT (axis=%s): %d name(s) found in >=2 "
        "of %d registered %s package(s) and nowhere else -- %d identical, "
        "%d drifted.",
        axis,
        len(groups),
        target_count,
        axis,
        len(identical),
        len(drifted),
    )


def main() -> int:
    """CLI entry point.

    Returns:
        0 (report ran and drifted count <= baseline, a successful
        `--update-baseline`, or `--self-test` passed), 1 (drifted count
        exceeds baseline), or 2 (self-test failed, fewer than two registered
        languages, or a discovery/parse error).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Parallel-implementation drift report: every function/method name "
            "defined in >= 2 registered 'datrix.languages' packages and nowhere "
            "else in the monorepo, with a per-name identical/drifted verdict "
            "and a decrease-only drifted-count baseline."
        ),
    )
    parser.add_argument(
        "--axis",
        choices=(AXIS_LANGUAGES, AXIS_PLATFORMS),
        default=AXIS_LANGUAGES,
        help=(
            "Which registered target set to compare. Each axis has its own "
            "baseline file; the axes never share a ratchet."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real report",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the live drifted-group count as the new baseline",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not run_non_vacuity_self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real scan is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    axis: str = args.axis
    baseline_path = _AXIS_BASELINE_PATHS[axis]
    target_names = _AXIS_NAME_RESOLVERS[axis]()
    try:
        target_src_dirs = discover_target_package_src_dirs(axis, target_names, WORKSPACE_ROOT)
        _require_min_targets(axis, frozenset(target_src_dirs))
        other_src_dirs = discover_all_other_package_src_dirs(WORKSPACE_ROOT, frozenset(target_src_dirs.values()))
        groups = find_parallel_implementations(target_src_dirs, other_src_dirs)
    except (ValueError, ImportError, SyntaxError, PluginError) as exc:
        logger.error("PARALLEL-IMPLEMENTATION DRIFT REPORT CANNOT RUN: %s", exc)
        return EXIT_USAGE

    _log_report(groups, len(target_src_dirs), axis)
    drifted_count = sum(1 for g in groups if g.verdict == "drifted")

    if args.update_baseline:
        write_drift_baseline(drifted_count, baseline_path, axis)
        logger.info(
            "Baseline updated: axis=%s drifted_count=%d written to %s",
            axis,
            drifted_count,
            baseline_path,
        )
        return EXIT_OK

    baseline_count = load_drift_baseline(baseline_path)
    failure = check_drift_ratchet(drifted_count, baseline_count)
    if failure:
        logger.error(failure)
        return EXIT_FAIL

    logger.info(
        "Drift ratchet holds (axis=%s): %d drifted group(s) <= baseline %d.",
        axis,
        drifted_count,
        baseline_count,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
