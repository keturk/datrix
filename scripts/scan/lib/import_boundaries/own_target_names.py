"""Own-target-name scanner and its ratchet."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_common.plugin.capability_resolution import (
    declaration_for_language,
)

from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.registered_targets import (
    AXIS_LANGUAGES,
    entry_point_module_roots,
)
from import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_SCRIPT,
    PackageInfo,
    _check,
    _identifier_carries_target_name,
    _language_name_tokens,
    _self_test_write_manifest,
    load_count_baseline,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from import_boundaries.taxonomy import LANGUAGES_ENTRY_POINT_GROUP

# ---------------------------------------------------------------------------
# I4 Own-Target-Name Ratchet (Decision D5, Invariant I4)
#
# The mirror image of G2 -- G2 holds the ONE shared-layer package
# (datrix_codegen_common) to zero symbols carrying ANY registered language's
# name; I4 holds EVERY registered LANGUAGE package to zero function/method
# DEFINITIONS carrying THAT SAME package's own registered language id or
# declared alias -- the token that defeats a name-keyed behaviour-parity
# scan's grouping of members across packages (a `build_python_thing` inside
# `datrix_codegen_python` does not need "python" in its name; the package
# already says it). Scope is function/method
# DEFINITION names only -- never a class name, dataclass field, or type
# reference (a language package legitimately imports and references its own
# language's types by name everywhere; that is what G2's declaration/type-
# reference scan already covers, for the ONE shared package it polices).
#
# The policed package set is the discovered taxonomy's `language_packages`
# (the same source I6/G1 already thread through their own scan functions) --
# never a hardcoded per-language tuple, so a fifth `datrix-codegen-<lang>`
# package is policed automatically the moment its manifest registers a
# `datrix.languages` entry point. The per-package VOCABULARY is read live
# from `declaration_for_language(lang).name_tokens` (the registered language
# id resolved from the package's own import root via
# `entry_point_module_roots`), never a hardcoded per-language literal set.


@dataclass(frozen=True)
class OwnTargetNameHit:
    """One function/method definition whose name carries its own package's
    language id or declared alias as an identifier segment (Decision D5,
    Invariant I4).

    Attributes:
        file_path: File containing the definition.
        line_number: Definition's line number.
        identifier: The bare function/method name.
        matched_token: The registered token it carries (from
            ``declaration_for_language(lang).name_tokens | {lang}``).
    """

    file_path: Path
    line_number: int
    identifier: str
    matched_token: str


def scan_file_for_own_target_names(
    file_path: Path, own_tokens: frozenset[str]
) -> list[OwnTargetNameHit]:
    """AST-walk *file_path* for ``FunctionDef``/``AsyncFunctionDef`` NAMES
    only (module-level and class-method) carrying a segment in *own_tokens*
    -- reuses ``_identifier_carries_target_name`` (G2, above) unchanged.

    Deliberately narrower than G2's shared-target-name scan: I4 is about a
    function's OWN name, never a class name, dataclass field, or type
    reference (a language package legitimately imports and references its
    own language's types by name everywhere).

    Args:
        file_path: Path to Python source file.
        own_tokens: This package's own ``name_tokens | {registered_name}``.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))
    hits: list[OwnTargetNameHit] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            matched = _identifier_carries_target_name(node.name, own_tokens)
            if matched is not None:
                hits.append(OwnTargetNameHit(file_path, node.lineno, node.name, matched))
    return hits


def _own_target_name_tokens_by_package(
    language_packages: tuple[str, ...],
) -> dict[str, frozenset[str]]:
    """Map each language package's IMPORT name (e.g. ``datrix_codegen_python``,
    as ``GeneratorTaxonomy.language_packages`` holds) to its own
    ``declaration_for_language(lang).name_tokens | {lang}``, read live --
    never a hardcoded per-language literal set.

    ``declaration_for_language`` takes the REGISTERED ``datrix.languages``
    entry-point name (e.g. ``"python"``), not the import root, so each import
    name is resolved back to its registered name via
    ``entry_point_module_roots`` (the same live entry-point map
    ``discover_target_package_src_dirs`` itself builds from), inverted.

    Args:
        language_packages: Import package names to resolve (e.g. from
            ``GeneratorTaxonomy.language_packages``).

    Returns:
        Import package name -> its own declared name-token vocabulary.

    Raises:
        ValueError: If an import name has no registered ``datrix.languages``
            entry point pointing at it -- a real configuration inconsistency
            between a package's manifest and its installed entry point,
            never silently skipped.
    """
    import_root_to_language = {
        import_root: language_name
        for language_name, import_root in entry_point_module_roots(AXIS_LANGUAGES).items()
    }
    tokens_by_package: dict[str, frozenset[str]] = {}
    for import_name in language_packages:
        language_name = import_root_to_language.get(import_name)
        if language_name is None:
            raise ValueError(
                f"Language package {import_name!r} (declared by its manifest's "
                f"'datrix.languages' entry point) has no matching installed "
                f"'datrix.languages' entry point. Installed entry-point names: "
                f"{sorted(import_root_to_language.values())}. Fix: verify the "
                f"package is installed into the active virtual environment and "
                f"its pyproject.toml entry-point name matches the installed one."
            )
        tokens_by_package[import_name] = _language_name_tokens(language_name)
    return tokens_by_package


def scan_own_target_names(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    language_packages: tuple[str, ...],
) -> dict[str, list[OwnTargetNameHit]]:
    """Scan every registered language package's OWN ``src/`` tree against ITS
    OWN tokens only -- never another language's, and never the shared
    ``datrix_codegen_common`` package (that is G2's job).

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        language_packages: The discovered taxonomy's language packages
            (``GeneratorTaxonomy.language_packages``).

    Returns:
        Mapping of package name -> hits in that package (packages with zero
        hits omitted).
    """
    results: dict[str, list[OwnTargetNameHit]] = {}
    tokens_by_package = _own_target_name_tokens_by_package(language_packages)

    for package_name in language_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        own_tokens = tokens_by_package[package_name]
        package_hits: list[OwnTargetNameHit] = []
        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                package_hits.extend(scan_file_for_own_target_names(py_file, own_tokens))
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. A policed "
                    f"file that cannot be parsed would escape this scan; fix its syntax "
                    f"or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except (OSError, UnicodeDecodeError) as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that cannot "
                    f"be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

        if package_hits:
            results[package_name] = package_hits

    return results


#: The entry key of the own-target-name baseline: it is kept per package, not per file.
OWN_TARGET_NAME_BASELINE_KEY = "package"

_OWN_TARGET_NAME_BASELINE_HEADER = (
    "# I4 Own-Target-Name Ratchet Baseline (Decision D5, Invariant I4)\n"
    "#\n"
    "# Frozen per-PACKAGE counts of function/method definitions whose name\n"
    "# carries that package's OWN registered language id or declared alias\n"
    "# (declaration_for_language(lang).name_tokens | {lang}) as a whole\n"
    "# underscore-delimited identifier segment. Any INCREASE fails\n"
    "# datrix/scripts/scan/check-import-boundaries.ps1 --check-own-target-names.\n"
    "# Decreases are always allowed and should be captured by re-running with\n"
    "# --update-baseline once a rename removes a remaining hit. The terminal\n"
    "# state is zero for every package, then the baseline file itself is\n"
    "# deleted and the check runs hard-zero.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   package = "datrix_codegen_python"\n'
    "#   count = <int>\n"
    '#   reason = "free text, not read by the loader"\n'
)


def write_own_target_name_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write *counts* to the own-target-name baseline TOML as
    ``[[baseline]] package=... count=...`` entries, sorted by package name."""
    write_count_baseline(
        baseline_path,
        counts,
        key_field=OWN_TARGET_NAME_BASELINE_KEY,
        header=_OWN_TARGET_NAME_BASELINE_HEADER,
    )


def check_own_target_name_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per package whose own-target-name count rose above its
    baseline, sorted by package name."""
    return tighten_only_messages(current_counts, baseline, "own-target-name")


def _self_test_own_target_name_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    (a LANGUAGE package by its manifest's ``datrix.languages`` entry point,
    exactly like ``_self_test_shared_vocabulary_build_fixture_monorepo``)
    with a module declaring a target-NEUTRAL function, plus a baseline TOML
    freezing that package at count 0."""
    _self_test_write_manifest(
        tmp_root,
        "datrix-codegen-python",
        "datrix_codegen_python",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"python": "PythonLanguagePlugin"}},
    )
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_module.py"
    module_path.write_text("def build_thing() -> None:\n    pass\n", encoding="utf-8")

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "own-target-name-baseline.toml"
    baseline_path.write_text(
        '[[baseline]]\npackage = "datrix_codegen_python"\ncount = 0\n', encoding="utf-8"
    )
    return module_path


def _self_test_own_target_name_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--base-dir",
            str(tmp_root),
            "--check-own-target-names",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_own_target_name_cli_non_vacuity() -> bool:
    """End-to-end proof the I4 own-target-name ratchet actually FIRES.

    Covers all four proof categories this ratchet's own test plan
    requires: the scanner's shape (function/method names only, never a class
    name), the ratchet comparator's regression/no-regression/missing-
    baseline-as-zero behavior, the baseline loader/writer round-trip, and
    (the real end-to-end proof) a mutation-based CLI non-vacuity check:
    starts from a fixture declaring a target-NEUTRAL function name (exits
    0), mutates it to carry the package's OWN registered language token
    (``build_python_thing``, exits 1, names the package and the exact
    delta), then reverts and proves it clears.
    """
    report_step(
        "Self-test 19/24: own-target-name ratchet (scanner shape, ratchet "
        "comparator, baseline round-trip, and CLI mutation non-vacuity: "
        "'build_python_thing' exits 1; 'build_thing' exits 0)"
    )
    ok = True

    # -- Scanner shape: function/method DEFINITION names only, never a class
    # name, using python's REAL declared name_tokens (the declaration already
    # includes "python" itself in PYTHON_LANGUAGE_CAPABILITY_DECLARATION).
    python_tokens = declaration_for_language("python").name_tokens | {"python"}
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"own-target-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        neutral_function_file = scratch_dir / "neutral_function.py"
        neutral_function_file.write_text(
            "def build_thing() -> None:\n    pass\n", encoding="utf-8"
        )
        ok &= _check(
            "a target-neutral function name (build_thing) is NOT a hit",
            scan_file_for_own_target_names(neutral_function_file, python_tokens) == [],
        )

        own_token_function_file = scratch_dir / "own_token_function.py"
        own_token_function_file.write_text(
            "def build_python_thing() -> None:\n    pass\n", encoding="utf-8"
        )
        own_token_hits = scan_file_for_own_target_names(own_token_function_file, python_tokens)
        ok &= _check(
            "a function name carrying the package's own token (build_python_thing) IS a hit",
            len(own_token_hits) == 1
            and own_token_hits[0].identifier == "build_python_thing"
            and own_token_hits[0].matched_token == "python",
        )

        own_token_class_file = scratch_dir / "own_token_class.py"
        own_token_class_file.write_text("class PythonThing:\n    value: str\n", encoding="utf-8")
        ok &= _check(
            "a CLASS carrying the package's own token (PythonThing) is NOT a "
            "hit -- I4 scope is function/method names only",
            scan_file_for_own_target_names(own_token_class_file, python_tokens) == [],
        )

        own_token_method_file = scratch_dir / "own_token_method.py"
        own_token_method_file.write_text(
            "class Converter:\n    def to_python_dict(self) -> dict[str, object]:\n        return {}\n",
            encoding="utf-8",
        )
        method_hits = scan_file_for_own_target_names(own_token_method_file, python_tokens)
        ok &= _check(
            "a METHOD carrying the package's own token (to_python_dict) IS a "
            "hit -- class methods are in scope",
            len(method_hits) == 1 and method_hits[0].identifier == "to_python_dict",
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    # -- Ratchet comparator: regression / no-regression / missing-baseline-as-zero.
    own_target_clean = check_own_target_name_ratchet(
        {"datrix_codegen_python": 2}, {"datrix_codegen_python": 2}
    )
    ok &= _check("own-target-name ratchet: clean when current == baseline", own_target_clean == [])

    own_target_increase = check_own_target_name_ratchet(
        {"datrix_codegen_python": 3}, {"datrix_codegen_python": 2}
    )
    ok &= _check(
        "own-target-name ratchet: fires once on a real increase, naming package + delta",
        len(own_target_increase) == 1
        and "datrix_codegen_python" in own_target_increase[0]
        and "increased from baseline 2 to 3" in own_target_increase[0],
    )

    own_target_decrease = check_own_target_name_ratchet(
        {"datrix_codegen_python": 1}, {"datrix_codegen_python": 5}
    )
    ok &= _check("own-target-name ratchet: allows a decrease", own_target_decrease == [])

    own_target_missing_baseline = check_own_target_name_ratchet(
        {"datrix_codegen_typescript": 1}, {}
    )
    ok &= _check(
        "own-target-name ratchet: a package absent from baseline is treated as baseline 0",
        len(own_target_missing_baseline) == 1
        and "increased from baseline 0 to 1" in own_target_missing_baseline[0],
    )

    # -- Baseline loader/writer round-trip, and a missing file refused.
    baseline_scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"own-target-baseline-{uuid.uuid4().hex}"
    baseline_scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path = baseline_scratch_dir / "own-target-name-baseline.toml"
        try:
            load_count_baseline(baseline_path, key_field=OWN_TARGET_NAME_BASELINE_KEY)
            missing_refused = False
        except FileNotFoundError:
            missing_refused = True
        ok &= _check(
            "load_count_baseline refuses a missing own-target-name baseline (FileNotFoundError)",
            missing_refused,
        )
        round_trip_counts = {"datrix_codegen_python": 3, "datrix_codegen_typescript": 0}
        write_own_target_name_baseline(baseline_path, round_trip_counts)
        ok &= _check(
            "write_own_target_name_baseline then load_count_baseline round-trips exactly",
            load_count_baseline(baseline_path, key_field=OWN_TARGET_NAME_BASELINE_KEY).counts
            == round_trip_counts,
        )
    finally:
        shutil.rmtree(baseline_scratch_dir, ignore_errors=True)

    # -- Real end-to-end CLI mutation non-vacuity proof.
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"own-target-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_own_target_name_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_own_target_name_run_cli(tmp_root)
        ok &= _check(
            f"target-neutral fixture (build_thing) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )
        ok &= _check(
            "clean fixture's clean output names the scanned package and its live count",
            "datrix_codegen_python: 0" in clean_result.stdout,
        )

        module_path.write_text("def build_python_thing() -> None:\n    pass\n", encoding="utf-8")
        failing_result = _self_test_own_target_name_run_cli(tmp_root)
        ok &= _check(
            f"own-token fixture (build_python_thing) exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated package",
            "datrix_codegen_python" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_own_target_name_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The own-target-name scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [self_test_check(_self_test_own_target_name_cli_non_vacuity)]
