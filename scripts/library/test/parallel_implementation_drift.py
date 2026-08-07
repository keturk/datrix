#!/usr/bin/env python3
"""Parallel-implementation drift report for Datrix language codegen packages.

Reports every function (module-level def or class method) defined under two
or more registered `datrix.languages` packages' src/ trees, and NOWHERE else
in the monorepo -- a candidate that was never hoisted to datrix-codegen-common
(or was hoisted and one copy left behind). Classifies each such name as
IDENTICAL (every definition's source text is byte-for-byte equal) or DRIFTED
(at least one definition differs), and records a decrease-only baseline of
the DRIFTED count.

This is deliberately a REPORT with a count baseline, not a pass/fail gate on
individual names: a name-keyed check cannot distinguish an intentional
per-language emission difference (e.g. a `_render_endpoint_handler` method,
which must legitimately differ per target language) from a genuine
unreconciled divergence, and a gate that cannot make that distinction gets
turned off. Classification of drifted groups is a separate, deliberate,
human-reviewed pass over this report's output.

The target set (which packages count as "a language package") is derived
from shared.registered_targets.registered_language_names() at runtime --
never a hardcoded four -- so installing a fifth datrix-codegen-<lang> package
extends this report's coverage automatically. The "everywhere else" side is
likewise pure filesystem discovery over every `datrix-*` package directory
with a `src/` tree (mirrors dev/check-import-boundaries.py's own
`discover_packages`) -- never a hardcoded package list.

Usage:
    python parallel_implementation_drift.py                # full report
    python parallel_implementation_drift.py --self-test     # non-vacuity only
    python parallel_implementation_drift.py --update-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

# Add scripts/library to sys.path to import shared.registered_targets (this
# file lives at library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_common.errors.plugin import PluginError  # noqa: E402

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/parallel_implementation_drift.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root. Mirrors
# reference_example_parity.py's own identical-depth path math.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]
WORKSPACE_ROOT: Path = _HERE.parents[4]
DRIFT_BASELINE_PATH: Path = (
    DATRIX_DIR / "scripts" / "config" / "parallel-implementation-drift-baseline.json"
)

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

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
        package_dirs = sorted(
            d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix")
        )
        if not package_dirs:
            continue
        locations[package_dirs[0].name] = package_dirs[0]
    return locations


def discover_language_package_src_dirs(
    languages: frozenset[str], monorepo_root: Path
) -> dict[str, Path]:
    """Resolve each registered language name to its package's `src/<import_name>`
    directory, via each language's own `LanguagePlugin` class module root (the
    same technique `type_mapping_completeness.import_language_mappings` uses)
    matched against the filesystem package map -- never a hardcoded
    `datrix-codegen-{language}` string-format assumption.

    Args:
        languages: Registered `datrix.languages` names to resolve.
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        `{language_name: absolute src package directory}`, one entry per
        successfully resolved language.

    Raises:
        ValueError: If a registered language's plugin resolves to an import
            root with no matching on-disk package -- a real configuration
            error, never silently skipped (shrinking the target set quietly
            would hide the exact drift this report exists to surface).
    """
    from datrix_common.generation.discovery import get_language_plugin

    all_locations = _discover_all_package_locations(monorepo_root)
    result: dict[str, Path] = {}
    for language in sorted(languages):
        plugin = get_language_plugin(language)
        import_name = type(plugin).__module__.split(".")[0]
        src_dir = all_locations.get(import_name)
        if src_dir is None:
            raise ValueError(
                f"Could not resolve an on-disk src/ directory for language "
                f"{language!r} (its registered LanguagePlugin class lives in "
                f"module root {import_name!r}). Expected a 'datrix-*' "
                f"directory under {monorepo_root} whose src/ tree contains a "
                f"{import_name!r} package directory. Discovered package "
                f"roots: {sorted(all_locations)}."
            )
        result[language] = src_dir
    return result


def discover_all_other_package_src_dirs(
    monorepo_root: Path, exclude_dirs: frozenset[Path]
) -> list[Path]:
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
    return sorted(
        src_dir for src_dir in all_locations.values() if src_dir not in exclude_dirs
    )


# ---------------------------------------------------------------------------
# AST scanning
# ---------------------------------------------------------------------------


def _collect_defs(
    body: list[ast.stmt], enclosing_class: str | None
) -> list[tuple[_FunctionDefNode, str | None]]:
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
            qualified_name = (
                f"{enclosing_class}.{node.name}" if enclosing_class else node.name
            )
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
    language_src_dirs: dict[str, Path],
    other_package_src_dirs: list[Path],
) -> list[ParallelImplementationGroup]:
    """Core scan: find every bare function/method name defined in >= 2 of
    `language_src_dirs` and in ZERO of `other_package_src_dirs`.

    Dependency-injected, no entry-point/registry calls inside this function
    -- the CLI boundary in `main()` is the only place that resolves the live
    registry, so this function is what the self-test exercises directly with
    a synthetic package map.

    Args:
        language_src_dirs: `{language_name: src_dir}` for every language
            package to compare.
        other_package_src_dirs: Every OTHER package's src dir -- a name
            appearing here excludes that name from the report entirely.

    Returns:
        One `ParallelImplementationGroup` per qualifying bare name, sorted
        by name. `verdict` is "identical" iff every declaration's
        `source_text` is equal across the whole group, else "drifted".
    """
    by_bare_name: dict[str, list[FunctionDeclaration]] = {}
    for package, src_dir in language_src_dirs.items():
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
        if len(distinct_packages) < _MIN_LANGUAGES_FOR_COMPARISON:
            continue
        if bare_name in other_bare_names:
            continue
        source_texts = {d.source_text for d in declarations}
        verdict: Literal["identical", "drifted"] = (
            "identical" if len(source_texts) == 1 else "drifted"
        )
        groups.append(
            ParallelImplementationGroup(
                name=bare_name, declarations=tuple(declarations), verdict=verdict
            )
        )
    return sorted(groups, key=lambda group: group.name)


def _require_min_languages(languages: frozenset[str]) -> None:
    """Raise if fewer than `_MIN_LANGUAGES_FOR_COMPARISON` languages are
    given -- the CLI-facing guard against a vacuous parallel-implementation
    comparison. Exercised directly by the self-test (never through a live
    entry-point scan) and by `main()` against the real registered set.

    Args:
        languages: The candidate target set to validate.

    Raises:
        ValueError: If `len(languages) < _MIN_LANGUAGES_FOR_COMPARISON`,
            naming how many ARE registered.
    """
    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"Parallel-implementation drift comparison requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} registered 'datrix.languages' "
            f"targets; got {len(languages)} ({sorted(languages)})."
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
            f"Malformed {path}: expected an object with a non-negative "
            f"integer 'drifted_count' field, got {data!r}."
        )
    return count


def write_drift_baseline(count: int, path: Path = DRIFT_BASELINE_PATH) -> None:
    """Write `count` to the baseline JSON. Called ONLY by `--update-baseline`,
    a deliberate, manual re-freeze (mirrors `write_blessed_count`'s role for
    `regen-parity-baselines.ps1` -- the check side of the ratchet is
    `check_drift_ratchet`, applied on every ordinary run against whatever was
    last frozen here).

    Args:
        count: The freshly computed drifted-group count.
        path: The baseline file to write. Defaults to the real committed
            file; tests pass a synthetic temp path.
    """
    payload = {
        "_comment": [
            "Decrease-only ratchet: the count of DRIFTED parallel-implementation",
            "groups reported by parallel-implementation-drift-gate.ps1 (a function",
            "name defined identically-in-shape but divergent-in-source across two",
            "or more registered language codegen packages, and nowhere else in the",
            "monorepo). A run whose LIVE drifted count is HIGHER than this value",
            "fails -- new drift appeared with nothing reconciling it.",
            "parallel-implementation-drift-gate.ps1 -UpdateBaseline is the only",
            "writer; run it once the real scanner is landed to seed the initial",
            "count from the live tree (do not hand-guess the number).",
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

        shared_body = (
            f"def {_SELF_TEST_SHARED_HELPER_NAME}(value: str) -> str:\n"
            f"    return value.strip()\n"
        )
        (lang_a_src / "module.py").write_text(shared_body, encoding="utf-8")
        (lang_b_src / "module.py").write_text(shared_body, encoding="utf-8")
        (other_src / "module.py").write_text(
            "def unrelated() -> None:\n    pass\n", encoding="utf-8"
        )

        groups = find_parallel_implementations(
            {_SELF_TEST_LANGUAGE_A: lang_a_src, _SELF_TEST_LANGUAGE_B: lang_b_src},
            [other_src],
        )
        matching = [g for g in groups if g.name == _SELF_TEST_SHARED_HELPER_NAME]
        ok &= _assert(
            len(matching) == 1, "identical synthetic pair reports exactly one group"
        )
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
            "a name also present in an 'other' package is excluded even though "
            ">=2 language packages define it",
        )

        # >=2-registered-targets refusal: the CLI-facing guard, exercised
        # directly against a synthetic single-language map (never through a
        # live entry-point scan).
        try:
            _require_min_languages(frozenset({_SELF_TEST_LANGUAGE_A}))
            guard_refused = False
        except ValueError:
            guard_refused = True
        ok &= _assert(
            guard_refused,
            "single-target guard refuses a one-language map (never a silent pass)",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _log_report(groups: list[ParallelImplementationGroup], language_count: int) -> None:
    """Log the per-name verdict lines plus the summary line."""
    drifted = [g for g in groups if g.verdict == "drifted"]
    identical = [g for g in groups if g.verdict == "identical"]
    for group in drifted:
        locations = ", ".join(
            f"{decl.package}:{decl.file_path}:{decl.line_number}"
            for decl in group.declarations
        )
        logger.info("DRIFTED name=%s locations=[%s]", group.name, locations)
    for group in identical:
        logger.debug(
            "identical name=%s packages=%s",
            group.name,
            sorted({d.package for d in group.declarations}),
        )
    logger.info(
        "PARALLEL-IMPLEMENTATION DRIFT REPORT: %d name(s) found in >=2 of %d "
        "registered language package(s) and nowhere else -- %d identical, "
        "%d drifted.",
        len(groups), language_count, len(identical), len(drifted),
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
        logger.error(
            "NON-VACUITY SELF-TEST FAILED -- aborting before any real scan is trusted."
        )
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    languages = registered_language_names()
    try:
        _require_min_languages(languages)
        language_src_dirs = discover_language_package_src_dirs(languages, WORKSPACE_ROOT)
        other_src_dirs = discover_all_other_package_src_dirs(
            WORKSPACE_ROOT, frozenset(language_src_dirs.values())
        )
        groups = find_parallel_implementations(language_src_dirs, other_src_dirs)
    except (ValueError, ImportError, SyntaxError, PluginError) as exc:
        logger.error("PARALLEL-IMPLEMENTATION DRIFT REPORT CANNOT RUN: %s", exc)
        return EXIT_USAGE

    _log_report(groups, len(languages))
    drifted_count = sum(1 for g in groups if g.verdict == "drifted")

    if args.update_baseline:
        write_drift_baseline(drifted_count)
        logger.info(
            "Baseline updated: drifted_count=%d written to %s",
            drifted_count, DRIFT_BASELINE_PATH,
        )
        return EXIT_OK

    baseline_count = load_drift_baseline()
    failure = check_drift_ratchet(drifted_count, baseline_count)
    if failure:
        logger.error(failure)
        return EXIT_FAIL

    logger.info(
        "Drift ratchet holds: %d drifted group(s) <= baseline %d.",
        drifted_count, baseline_count,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
