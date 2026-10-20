"""Cross-package-vocabulary scanner and its ratchet."""

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
from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.scan.import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_COMMAND,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    load_count_baseline,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from datrix_scripts.scan.import_boundaries.shared_vocabulary import _NormalizedContainer
from datrix_scripts.scan.import_boundaries.taxonomy import LANGUAGES_ENTRY_POINT_GROUP, discover_packages

# ---------------------------------------------------------------------------
# G3 Cross-Package Vocabulary Ratchet (Decision D2.1-D2.4, Property 2)
#
# Fails when a module-level set/frozenset/dict/tuple literal's normalized
# member set is declared -- with at least one bare string literal -- in TWO
# OR MORE DISTINCT datrix-* packages. Unlike G1 (source-keyed: "does this
# language package redeclare something datrix_codegen_kernel.enums
# declares?"), G3 is keyed on duplication ACROSS packages with no notion of
# a canonical source -- it catches a vocabulary hand-copied between two
# packages that have no shared enum to key off at all. Scope is every
# package discover_packages() finds (not just the language packages), since a
# cross-package duplicate can involve any two datrix-* packages, including
# a language package and a shared layer.
# ---------------------------------------------------------------------------


def _resolve_g3_vocabulary_element(node: ast.AST) -> tuple[str, bool] | None:
    """Resolve one set/frozenset/dict-key/tuple element to ``(value,
    is_bare)`` for G3's classification -- PURELY BY AST SHAPE, never by
    resolving a qualified reference's runtime value the way G1's
    ``_resolve_vocabulary_element`` does. G3 must never consult
    ``datrix_codegen_kernel.enums`` (that canonical-vocabulary comparison
    is G1's job; G3 compares packages against EACH OTHER); reusing G1's
    resolver -- which can only recognize a qualified ``EnumClass.MEMBER``
    reference when ``EnumClass`` happens to be harvested from
    ``datrix_codegen_kernel.enums`` -- would silently make every qualified
    reference to any OTHER enum (e.g. ``ChangeKind`` from
    ``datrix_migration.differ``, ``TracingProvider`` from
    ``datrix_common.config.observability.models``) unresolvable, which
    would drop the WHOLE container (not just exempt it) and could hide a
    genuinely duplicated bare-literal sibling in the same container.

    A qualified reference (``EnumClass.MEMBER``, i.e. ``ast.Attribute``
    whose value is a bare ``ast.Name``) is recognized by shape alone and
    treated as non-bare (``is_bare=False``) -- it is "consuming" a named
    fact, not hardcoding one, regardless of which module that name comes
    from. Its symbolic dotted form (``"EnumClass.MEMBER"``) stands in as
    its comparison value: this is exact for a container built ENTIRELY of
    qualified references (excluded via ``has_bare_literal`` regardless of
    what its value resolves to) and is a documented, deliberate
    approximation for the rare MIXED bare+qualified container, where it
    still correctly keeps the bare portion in scope for comparison instead
    of silently dropping the entire container.

    Returns:
        ``None`` for any other node shape (a Name, an f-string, a call,
        ...) -- such an element means the container is not a closed
        vocabulary literal at all, and the caller skips it entirely.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}", False
    return None


def _normalize_container_g3(node: ast.AST) -> _NormalizedContainer | None:
    """Same contract as ``_normalize_container``, extended to recognize a
    bare module-level ``ast.Tuple`` RHS (``_X = ("a", "b")``, no
    ``frozenset()``/``set()`` wrapper) -- G1 never needed this shape; G3's
    own scope explicitly includes it ("set/frozenset/dict/tuple" literals).
    Per-element resolution uses ``_resolve_g3_vocabulary_element`` (shape-
    based, never consults ``datrix_codegen_kernel.enums``), so a qualified
    ``EnumClass.MEMBER`` element still counts as "consuming", not
    "declaring", exactly as it does for G1, and a partially-dynamic tuple
    (an element that is neither a bare string nor a qualified attribute
    reference) is still "not provably a closed vocabulary literal" and
    returns ``None``, the same as every other unrecognized shape.

    Returns:
        ``None`` if *node* is not a recognized set/frozenset/dict/tuple
        literal, has zero elements, or contains any element that is not a
        bare string or a qualified attribute reference.
    """
    elements = _container_elements_g3(node)
    if not elements:
        return None

    values: set[str] = set()
    has_bare_literal = False
    for element in elements:
        resolved = _resolve_g3_vocabulary_element(element)
        if resolved is None:
            return None
        value, is_bare = resolved
        values.add(value)
        has_bare_literal = has_bare_literal or is_bare

    return _NormalizedContainer(
        values=frozenset(values), has_bare_literal=has_bare_literal
    )


def _container_elements_g3(node: ast.AST) -> list[ast.AST] | None:
    """The elements of a set/frozenset/dict/tuple literal (a dict's keys), or
    ``None`` when *node* is no such literal or a dict carries a ``**`` spread
    entry (not a closed literal)."""
    if isinstance(node, (ast.Tuple, ast.Set)):
        return list(node.elts)
    if isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        return list(node.args[0].elts)
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None
        return [key for key in node.keys if key is not None]
    return None


@dataclass(frozen=True)
class CrossPackageVocabularyHit:
    """One module-level container in ``file_path`` whose normalized member
    set is ALSO declared (identically, with at least one bare string
    literal) in at least one other datrix-* package."""

    file_path: Path
    line_number: int
    container_name: str
    matched_packages: frozenset[str]  # every OTHER package declaring the same set


@dataclass(frozen=True)
class _ModuleContainerDeclaration:
    """One module-level bare-literal container declaration found while
    scanning a single file -- an intermediate value used only to group
    declarations across packages by normalized member set; never returned
    to a caller outside this ratchet's own scan pipeline."""

    file_path: Path
    line_number: int
    container_name: str
    values: frozenset[str]


def _scan_file_for_module_containers(
    file_path: Path,
) -> list[_ModuleContainerDeclaration]:
    """AST-walk *file_path* for module-level ``Assign``/``AnnAssign``
    statements whose value is a bare-literal set/frozenset/dict/tuple
    container (``_normalize_container_g3``), returning one declaration per
    qualifying statement in source order. A container built entirely from
    qualified ``EnumClass.MEMBER`` references (no bare string literal) is
    excluded here -- the same ``has_bare_literal`` gate G1 uses -- since it
    is consumption, not declaration.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of declarations found in the file, in source order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    declarations: list[_ModuleContainerDeclaration] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        normalized = _normalize_container_g3(value_node)
        if normalized is None or not normalized.has_bare_literal:
            continue

        container_name = ", ".join(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        declarations.append(
            _ModuleContainerDeclaration(
                file_path=file_path,
                line_number=stmt.lineno,
                container_name=container_name or "<unknown>",
                values=normalized.values,
            )
        )
    return declarations


def scan_cross_package_vocabulary(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[CrossPackageVocabularyHit]]:
    """AST-walk EVERY discovered datrix-* package's src/ tree (not just
    the language packages) for module-level set/frozenset/dict/tuple literals;
    group by normalized member set across ALL packages; report one hit per
    (file, container) whose normalized set is also declared, with a bare
    string literal, in >=1 OTHER package. Applies the same qualified-
    reference exemption G1 does -- a container built entirely from
    qualified ``EnumClass.MEMBER`` references (no bare string literal) is
    consumption, not duplication, and is never flagged -- but classifies it
    PURELY BY AST SHAPE (``_resolve_g3_vocabulary_element``), never by
    resolving against ``datrix_codegen_kernel.enums`` the way G1's
    ``scan_file_for_shared_vocabulary`` does: that canonical-vocabulary
    comparison is G1's job, and G3 compares packages against each other
    directly, with no notion of a canonical source or which specific enum
    module a qualified reference happens to come from.

    The grouping key is the normalized member-value set's CONTENT, never
    the container's name or file path -- a re-spelled table under a
    different name is exactly the case this ratchet exists to catch. A
    value set declared twice within the SAME package (even across two
    files) is a different, already-tracked defect (G1/DRY, not G3) and is
    never counted here: a "group" only counts once it spans two or more
    DISTINCT packages.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    declarations_by_package = {
        package_name: _package_module_containers(package_info, monorepo_root)
        for package_name, package_info in sorted(packages.items())
    }
    return _cross_package_hits(declarations_by_package)


def _package_module_containers(
    package_info: PackageInfo, monorepo_root: Path
) -> list[_ModuleContainerDeclaration]:
    """Every module-level container declaration of one package's ``src/``
    tree, file by file in sorted order. A file that cannot be parsed or read
    exits 2: it would escape the scan."""
    package_declarations: list[_ModuleContainerDeclaration] = []
    for py_file in sorted(package_info.src_dir.rglob("*.py")):
        try:
            package_declarations.extend(_scan_file_for_module_containers(py_file))
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
    return package_declarations


def _cross_package_hits(
    declarations_by_package: dict[str, list[_ModuleContainerDeclaration]],
) -> dict[Path, list[CrossPackageVocabularyHit]]:
    """One hit per declaration whose value set two or more DISTINCT packages
    declare, naming every other package that declares it."""
    # Group by normalized value set -> the set of DISTINCT packages that
    # declare it with a bare literal.
    packages_by_value_set: dict[frozenset[str], set[str]] = {}
    for package_name, package_declarations in declarations_by_package.items():
        for declaration in package_declarations:
            packages_by_value_set.setdefault(declaration.values, set()).add(
                package_name
            )

    results: dict[Path, list[CrossPackageVocabularyHit]] = {}
    for package_name, package_declarations in declarations_by_package.items():
        for declaration in package_declarations:
            member_packages = packages_by_value_set[declaration.values]
            if len(member_packages) < 2:
                continue
            other_packages = frozenset(member_packages - {package_name})
            results.setdefault(declaration.file_path, []).append(
                CrossPackageVocabularyHit(
                    file_path=declaration.file_path,
                    line_number=declaration.line_number,
                    container_name=declaration.container_name,
                    matched_packages=other_packages,
                )
            )
    return results


_CROSS_PACKAGE_VOCABULARY_BASELINE_HEADER = (
    "# G3 Cross-Package Vocabulary Ratchet Baseline (Decision D2.1-D2.4, Property 2)\n"
    "#\n"
    "# Frozen per-file counts of module-level set/frozenset/dict/tuple\n"
    "# declarations whose normalized member set is declared -- with a\n"
    "# bare string literal -- identically in two or more datrix-*\n"
    "# packages (every package discover_packages() finds, not only the\n"
    "# language packages). Any INCREASE in a file's count fails\n"
    "# datrix/scripts/scan/check-import-boundaries.ps1\n"
    "# --check-cross-package-vocabulary. Decreases are always allowed\n"
    "# and should be captured by re-running with --update-baseline once\n"
    "# a later change deletes or hoists a redundant container.\n"
    "#\n"
    "# An entry carrying a `reason` is a KNOWN-LEGITIMATE duplicate that\n"
    "# a design requires (Decision 36: per-platform capability\n"
    "# declarations and per-target realized-provider sets are declared\n"
    "# once per target because their governing decisions forbid a shared\n"
    "# table). Such an entry must never be driven to zero, and its reason\n"
    "# is part of the frozen record: --update-baseline reads every reason\n"
    "# back and re-emits it. Every entry WITHOUT a reason drives to 0 as\n"
    "# later consolidation work removes the redundant copy.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
    "#   count = <int>\n"
    '#   reason = "why a design requires this duplicate (optional)"\n'
)


def write_cross_package_vocabulary_baseline(
    baseline_path: Path, counts: dict[str, int], reasons: dict[str, str]
) -> None:
    """Write ``counts`` to the cross-package-vocabulary baseline TOML as
    ``[[baseline]] file=... count=... [reason=...]`` entries, sorted by file
    for deterministic diffs.

    A ``reason`` is the written D9 record that a file's duplicate is one a
    design requires (a per-platform capability declaration, a per-target
    realized-provider set) and must never be driven to zero. It is emitted
    for every file in ``reasons`` that still has a count, encoded as a TOML
    basic string, so a hand-written reason survives every
    ``--update-baseline`` regeneration. A reasoned file that no longer has
    any hit is dropped from the file -- its declaration is gone, so there
    is nothing left to explain -- and the caller reports it.

    Args:
        baseline_path: Path to the cross-package-vocabulary baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
        reasons: Mapping of relative file path -> written D9 reason.
    """
    write_count_baseline(
        baseline_path, counts, header=_CROSS_PACKAGE_VOCABULARY_BASELINE_HEADER, reasons=reasons
    )


def check_cross_package_vocabulary_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose cross-package-vocabulary count rose above
    its baseline, sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "cross-package-vocabulary")


def _self_test_cross_package_vocabulary_scanner() -> bool:
    """scan_cross_package_vocabulary finds a normalized value-set duplicate
    across two real discovered packages, does NOT flag a set genuinely
    unique to one package, does NOT flag the same set declared twice within
    ONE package, does NOT flag a container built entirely from qualified
    EnumClass.MEMBER references, and DOES recognize a bare tuple literal as
    a candidate container shape."""
    report_step(
        "Self-test 17/24: cross-package-vocabulary scanner (cross-package "
        "duplicate detection + same-package/qualified-enum/uniqueness "
        "exemptions + bare-tuple recognition)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cross-pkg-vocab-scanner-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        alpha_src = tmp_root / "datrix-codegen-alpha" / "src" / "datrix_codegen_alpha"
        beta_src = tmp_root / "datrix-codegen-beta" / "src" / "datrix_codegen_beta"
        alpha_src.mkdir(parents=True, exist_ok=True)
        beta_src.mkdir(parents=True, exist_ok=True)
        (alpha_src / "__init__.py").write_text("", encoding="utf-8")
        (beta_src / "__init__.py").write_text("", encoding="utf-8")

        # alpha.dup and beta.dup: genuine cross-package duplicate.
        (alpha_src / "dup.py").write_text(
            '_ALPHA_TERMINALS = ("all", "first", "count")\n', encoding="utf-8"
        )
        (beta_src / "dup.py").write_text(
            '_BETA_TERMINALS = ("all", "first", "count")\n', encoding="utf-8"
        )
        # alpha.unique: genuinely unique to alpha -- never flagged.
        (alpha_src / "unique.py").write_text(
            '_ALPHA_UNIQUE = frozenset({"only", "in", "alpha"})\n', encoding="utf-8"
        )
        # beta.same_package_twice_a / _b: same value set, twice, but both
        # declarations are in package beta -- not cross-package, never flagged.
        (beta_src / "same_package_twice_a.py").write_text(
            '_BETA_LOCAL_A = frozenset({"local", "only"})\n', encoding="utf-8"
        )
        (beta_src / "same_package_twice_b.py").write_text(
            '_BETA_LOCAL_B = frozenset({"local", "only"})\n', encoding="utf-8"
        )

        packages = discover_packages(tmp_root)
        hits = scan_cross_package_vocabulary(packages, tmp_root)

        alpha_dup_hits = hits.get(alpha_src / "dup.py", [])
        beta_dup_hits = hits.get(beta_src / "dup.py", [])
        ok &= _check(
            "a bare tuple literal duplicated across alpha and beta is flagged "
            "on both sides",
            len(alpha_dup_hits) == 1
            and len(beta_dup_hits) == 1
            and alpha_dup_hits[0].matched_packages == frozenset({"datrix_codegen_beta"})
            and beta_dup_hits[0].matched_packages == frozenset({"datrix_codegen_alpha"}),
        )

        ok &= _check(
            "a value set unique to one package is not flagged",
            (alpha_src / "unique.py") not in hits,
        )

        ok &= _check(
            "the same value set declared twice within ONE package is not "
            "cross-package and is not flagged",
            (beta_src / "same_package_twice_a.py") not in hits
            and (beta_src / "same_package_twice_b.py") not in hits,
        )

        # A container built entirely from qualified EnumClass.MEMBER
        # references must never be flagged, even when duplicated verbatim
        # across packages -- it is consumption, not declaration.
        (alpha_src / "qualified.py").write_text(
            "import enum\n\n"
            "class Sample(enum.Enum):\n"
            '    ALL = "all"\n'
            '    FIRST = "first"\n\n'
            "_ALPHA_QUALIFIED = frozenset({Sample.ALL, Sample.FIRST})\n",
            encoding="utf-8",
        )
        (beta_src / "qualified.py").write_text(
            "import enum\n\n"
            "class Sample(enum.Enum):\n"
            '    ALL = "all"\n'
            '    FIRST = "first"\n\n'
            "_BETA_QUALIFIED = frozenset({Sample.ALL, Sample.FIRST})\n",
            encoding="utf-8",
        )
        packages = discover_packages(tmp_root)
        hits_with_qualified = scan_cross_package_vocabulary(packages, tmp_root)
        ok &= _check(
            "a container built entirely from qualified EnumClass.MEMBER "
            "references is never flagged, even duplicated across packages",
            (alpha_src / "qualified.py") not in hits_with_qualified
            and (beta_src / "qualified.py") not in hits_with_qualified,
        )

        # A MIXED container (one bare literal + one qualified reference to
        # an enum from an ARBITRARY module -- not datrix_codegen_kernel.enums)
        # must still have its bare portion recognized: G3 classifies the
        # qualified element by AST SHAPE alone (never by resolving it
        # against datrix_codegen_kernel.enums), so an enum from any other
        # module must not silently make the whole container invisible.
        (alpha_src / "mixed.py").write_text(
            "import enum\n\n"
            "class OtherEnum(enum.Enum):\n"
            '    JAEGER = "jaeger"\n\n'
            '_ALPHA_MIXED = frozenset({OtherEnum.JAEGER, "otel"})\n',
            encoding="utf-8",
        )
        (beta_src / "mixed.py").write_text(
            "import enum\n\n"
            "class OtherEnum(enum.Enum):\n"
            '    JAEGER = "jaeger"\n\n'
            '_BETA_MIXED = frozenset({OtherEnum.JAEGER, "otel"})\n',
            encoding="utf-8",
        )
        packages = discover_packages(tmp_root)
        hits_with_mixed = scan_cross_package_vocabulary(packages, tmp_root)
        alpha_mixed_hits = hits_with_mixed.get(alpha_src / "mixed.py", [])
        beta_mixed_hits = hits_with_mixed.get(beta_src / "mixed.py", [])
        ok &= _check(
            "a MIXED bare+qualified container (qualified element from an "
            "enum outside datrix_codegen_kernel.enums) still has its bare "
            "portion recognized and flagged as a cross-package duplicate, "
            "not silently dropped",
            len(alpha_mixed_hits) == 1 and len(beta_mixed_hits) == 1,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_cross_package_vocabulary_build_fixture_monorepo(
    tmp_root: Path,
) -> tuple[Path, Path]:
    """Build a minimal isolated monorepo with TWO fixture packages
    (datrix-codegen-alpha, datrix-codegen-beta), neither importing anything
    from datrix_codegen_kernel.enums, and a baseline TOML freezing both
    files at count 0. Returns (alpha_module_path, beta_module_path).

    Both register a ``datrix.languages`` entry point so the scanner classifies
    them (a discovered package with no rule at all stops the scan by design)."""
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-alpha", "datrix_codegen_alpha",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"alpha": "AlphaLanguagePlugin"}},
    )
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-beta", "datrix_codegen_beta",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"beta": "BetaLanguagePlugin"}},
    )
    alpha_src = tmp_root / "datrix-codegen-alpha" / "src" / "datrix_codegen_alpha"
    beta_src = tmp_root / "datrix-codegen-beta" / "src" / "datrix_codegen_beta"
    alpha_src.mkdir(parents=True, exist_ok=True)
    beta_src.mkdir(parents=True, exist_ok=True)
    (alpha_src / "__init__.py").write_text("", encoding="utf-8")
    (beta_src / "__init__.py").write_text("", encoding="utf-8")

    alpha_module = alpha_src / "sample_alpha.py"
    beta_module = beta_src / "sample_beta.py"
    # Clean fixtures: each package declares its OWN, non-overlapping constant.
    alpha_module.write_text('_ALPHA_ONLY = frozenset({"a", "b"})\n', encoding="utf-8")
    beta_module.write_text('_BETA_ONLY = frozenset({"c", "d"})\n', encoding="utf-8")

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "cross-package-vocabulary-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-alpha/src/datrix_codegen_alpha/sample_alpha.py"\n'
        "count = 0\n\n"
        "[[baseline]]\n"
        'file = "datrix-codegen-beta/src/datrix_codegen_beta/sample_beta.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return alpha_module, beta_module


def _self_test_cross_package_vocabulary_run_cli(
    tmp_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *CLI_COMMAND,
            "--base-dir",
            str(tmp_root),
            "--check-cross-package-vocabulary",
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_cross_package_vocabulary_cli_non_vacuity() -> bool:
    """End-to-end proof the G3 ratchet actually FIRES: two clean,
    non-overlapping fixture packages exit 0; mutating beta to redeclare
    alpha's exact member set (a genuine cross-package duplicate) exits 1,
    names BOTH files, and reports the exact count delta; reverting clears
    it. Also proves a same-package (not cross-package) duplicate is NOT
    flagged by G3, and that a bare tuple literal is recognized (proven by
    the scanner-level self-test, ``_self_test_cross_package_vocabulary_scanner``,
    which this CLI proof complements with a real subprocess round-trip)."""
    report_step(
        "Self-test 18/24: cross-package-vocabulary ratchet CLI mutation "
        "non-vacuity (two non-overlapping fixture packages exit 0; "
        "redeclaring alpha's set in beta exits 1; reverting clears it; a "
        "written D9 reason survives --update-baseline and a vanished "
        "reasoned entry is dropped and named)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cross-pkg-vocab-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        alpha_module, beta_module = _self_test_cross_package_vocabulary_build_fixture_monorepo(
            tmp_root
        )
        clean_beta_source = beta_module.read_text(encoding="utf-8")

        clean_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"two non-overlapping fixture packages exit 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        # Cross-package duplicate: beta redeclares alpha's exact member set.
        beta_module.write_text(
            clean_beta_source + '\n_BETA_DUPLICATE = frozenset({"a", "b"})\n',
            encoding="utf-8",
        )
        failing_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"cross-package duplicate exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the beta file",
            beta_module.name in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        beta_module.write_text(clean_beta_source, encoding="utf-8")
        reverted_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"reverting clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        # D9 reasons are part of the frozen record: a hand-written reason on
        # alpha's entry survives --update-baseline verbatim (including a
        # character TOML must escape), beta's reasonless entry gains none,
        # and the loader reads the reason back.
        baseline_path = tmp_root / "datrix" / "scripts" / "config" / (
            "cross-package-vocabulary-baseline.toml"
        )
        alpha_rel = "datrix-codegen-alpha/src/datrix_codegen_alpha/sample_alpha.py"
        beta_rel = "datrix-codegen-beta/src/datrix_codegen_beta/sample_beta.py"
        planted_reason = 'per-target "realized" set -- a design forbids a shared table'
        beta_module.write_text(
            clean_beta_source + '\n_BETA_DUPLICATE = frozenset({"a", "b"})\n',
            encoding="utf-8",
        )
        write_cross_package_vocabulary_baseline(
            baseline_path, {alpha_rel: 0, beta_rel: 0}, {alpha_rel: planted_reason}
        )
        update_result = _self_test_cross_package_vocabulary_run_cli(
            tmp_root, "--update-baseline"
        )
        ok &= _check(
            f"--update-baseline exits 0, got {update_result.returncode}",
            update_result.returncode == 0,
        )
        regenerated = load_count_baseline(baseline_path)
        ok &= _check(
            "regenerated baseline records both duplicated files at count 1",
            regenerated.counts == {alpha_rel: 1, beta_rel: 1},
        )
        ok &= _check(
            "alpha's planted D9 reason survives --update-baseline verbatim",
            regenerated.reasons.get(alpha_rel) == planted_reason,
        )
        ok &= _check(
            "beta's reasonless entry gains no reason",
            beta_rel not in regenerated.reasons,
        )
        ok &= _check(
            "update output reports the number of entries carrying a D9 reason",
            "(1 carrying a D9 reason)" in update_result.stdout,
        )

        # A reasoned entry whose declaration vanished is dropped AND named.
        beta_module.write_text(clean_beta_source, encoding="utf-8")
        vanish_result = _self_test_cross_package_vocabulary_run_cli(
            tmp_root, "--update-baseline"
        )
        after_vanish = load_count_baseline(baseline_path)
        ok &= _check(
            "a reasoned entry with no remaining hit is dropped from the baseline",
            after_vanish.counts == {} and after_vanish.reasons == {},
        )
        ok &= _check(
            "the dropped reasoned entry is named on stderr",
            f"G3 baseline entry {alpha_rel} carried a D9 reason" in vanish_result.stderr,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The cross-package vocabulary scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [
        self_test_check(_self_test_cross_package_vocabulary_scanner),
        self_test_check(_self_test_cross_package_vocabulary_cli_non_vacuity),
    ]
