"""Shared-target-name scanner and its ratchet."""

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
from datrix_scripts.registered_targets import (
    registered_language_names,
)
from import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_SCRIPT,
    CountBaseline,
    DeclarationKind,
    PackageInfo,
    _check,
    _identifier_carries_target_name,
    _language_name_tokens,
    declaration_identifiers,
    load_count_baseline,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from import_boundaries.function_level_imports import check_function_level_import_ratchet
from import_boundaries.provider_conditionals import check_provider_conditional_ratchet
from import_boundaries.shared_vocabulary import check_shared_vocabulary_ratchet

# ---------------------------------------------------------------------------
# G2 Shared-Layer Target-Name Ratchet (Decision D4, Invariant I3)
#
# The shared codegen packages this ratchet polices: the language layer and the
# generation kernel (which took the DAL generator data model and catalog modules out of
# the language layer, so leaving it out would drop them from this check).
# `datrix_common` and
# `datrix_cli` are deliberately excluded (design §8): they hold platform
# config-schema models (AwsPlatformConfig, AzureCosmosConfig,
# DockerHealthcheckConfig, ...) whose relocation into the platform packages
# is a separate Decision-22-shaped question. (The per-language transpiler
# file scopes are not among them: they live beside each language's own
# transpiler core, so the shared transpiler holds only the neutral base.) Kept
# as its own tuple (not reused from the I1/I6 DERIVED shared-package set,
# whose scope is computed once by discover_shared_packages and belongs to
# those two ratchets only) per this file's established one-tuple/one-scope-
# per-ratchet precedent.
SHARED_TARGET_NAME_PACKAGES: tuple[str, ...] = (
    "datrix_codegen_common",
    "datrix_codegen_kernel",
)


@dataclass(frozen=True)
class SharedTargetNameHit:
    """One shared-layer identifier carrying a registered target name as an
    identifier segment (Decision D4, Invariant I3)."""

    file_path: Path
    line_number: int
    identifier: str
    matched_target: str
    kind: DeclarationKind


def scan_file_for_shared_target_names(
    file_path: Path, target_names: frozenset[str]
) -> list[SharedTargetNameHit]:
    """AST-walk *file_path* for shared-layer identifiers that carry a
    registered target name as an identifier segment: a class or
    function/method DEFINITION, a dataclass field or type alias declared at
    module or class-body level (either annotated, e.g. ``x: TypeAlias =
    ...``, or a plain assignment, e.g. ``PYTHON_DEFAULT_PORT = ...``), or
    a type reference (an ``isinstance()``/``issubclass()`` argument, a base
    class, a type annotation, or a type-alias union member).

    Deliberately scoped to DECLARATION and TYPE-REFERENCE positions only --
    never a bare local variable, function parameter, loop variable, or
    attribute READ inside a function body. A qualified attribute access
    (``some_obj.python_package``) is never emitted as its own hit kind: it is
    a READ of a field declared somewhere else -- G2's own contract is
    declarations "in datrix_codegen_common source", and counting a read as a
    declaration is a scanner false positive, not a genuine hit (confirmed by
    the residual-hit review: every attribute-access hit measured was a read
    of a ``datrix_common.paths.ServicePaths`` field, a package this design
    explicitly fences out of scope). A type expression's own attribute chain
    (``mod.Name`` in an annotation, base class, or ``isinstance`` argument)
    still resolves via ``_identifiers_in_type_expression`` and is still
    emitted as ``type_reference`` -- that is a genuine signal a plain
    attribute-access sweep would also have caught, so removing the blanket
    attribute-access kind loses no real coverage. See the module-level
    "vocabulary is datrix.languages only" note in this task's spec: an
    unscoped scan flagged 305 unrelated occurrences of the segment "local" in
    datrix-common/src alone, zero of them a target-named SURFACE -- part of
    why platforms are excluded from the vocabulary entirely. Restricting to
    declaration/type-reference positions catches every confirmed offender
    (the struct-slice dataclasses, the ``StructSliceBuilder`` union, the
    ``build_struct_context`` isinstance ladder,
    ``CqrsBusRegistration.import_line_python``, and the plain module-level
    constant ``PYTHON_DEFAULT_PORT``) while leaving ordinary local code and
    reads of out-of-scope packages' fields untouched.

    Args:
        file_path: Path to Python source file.
        target_names: Registered language names and their declared alias
            tokens (lowercased), from ``shared_target_name_vocabulary()``.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[SharedTargetNameHit] = []
    for identifier, line_number, kind in declaration_identifiers(tree):
        matched = _identifier_carries_target_name(identifier, target_names)
        if matched is not None:
            hits.append(
                SharedTargetNameHit(
                    file_path=file_path,
                    line_number=line_number,
                    identifier=identifier,
                    matched_target=matched,
                    kind=kind,
                )
            )
    return hits


def scan_shared_target_names(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[SharedTargetNameHit]]:
    """Scan every ``.py`` file under each of ``SHARED_TARGET_NAME_PACKAGES``'
    ``src/`` tree for identifiers carrying a registered target-name segment.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[SharedTargetNameHit]] = {}
    target_names = shared_target_name_vocabulary()

    for package_name in SHARED_TARGET_NAME_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_shared_target_names(py_file, target_names)
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

            if hits:
                results[py_file] = hits

    return results


_SHARED_TARGET_NAME_BASELINE_HEADER = (
    "# G2 Shared-Layer Target-Name Ratchet Baseline (Decision D4, Invariant I3)\n"
    "#\n"
    "# Frozen per-file counts of shared-layer identifiers (class, function,\n"
    "# dataclass field, type alias, or type reference) carrying a registered\n"
    "# language name OR one of that language's declared alias tokens\n"
    "# (declaration_for_language(lang).name_tokens) as an identifier segment,\n"
    "# in datrix_codegen_common and datrix_codegen_kernel.\n"
    "# Any INCREASE in a file's count fails\n"
    "# datrix/scripts/scan/check-import-boundaries.ps1 --check-shared-target-names.\n"
    "# Decreases are always allowed and should be captured by re-running with\n"
    "# --update-baseline once a later change deletes a target-named surface.\n"
    "# Every entry is a reviewed exemption and MUST carry a written `reason`\n"
    "# naming the identifiers, why they stay, and what drives them to zero;\n"
    "# an entry without one fails the check. --update-baseline reads every\n"
    "# reason back and re-emits it, and names a reasoned entry that no longer\n"
    "# has a hit. The four sql/nosql-substring identifiers considered during\n"
    "# this ratchet's design (sql_engine, sql_dialect, NoSQLSeedWriter,\n"
    "# NoSqlFilterSyntax) are NOT hits under this ratchet's languages-only\n"
    "# vocabulary (sql is not a registered datrix.languages entry) -- they are\n"
    "# proven non-matches by this ratchet's own self-test, not baseline entries.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
    "#   count = <int>\n"
    '#   reason = "identifiers, why they stay, what drives them to zero"\n'
)


def write_shared_target_name_baseline(
    baseline_path: Path, counts: dict[str, int], reasons: dict[str, str]
) -> None:
    """Write ``counts`` to the shared-target-name baseline TOML as
    ``[[baseline]] file=... count=... [reason=...]`` entries, sorted by file,
    re-emitting every written reason that still has a count."""
    write_count_baseline(
        baseline_path, counts, header=_SHARED_TARGET_NAME_BASELINE_HEADER, reasons=reasons
    )


def check_shared_target_name_reasons(baseline: CountBaseline) -> list[str]:
    """Return one message per baseline entry that carries no written reason.
    Every surviving entry is a reviewed exemption, never a silent count."""
    return [
        f"{file_rel}: baseline entry carries no reason. Every surviving "
        f"shared-target-name entry is a reviewed exemption: add reason = "
        f'"<identifiers, why they stay, what drives them to zero>", or rename '
        f"the identifiers and lower the count."
        for file_rel in sorted(baseline.counts.keys())
        if file_rel not in baseline.reasons
    ]


def check_shared_target_name_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose shared-target-name count rose above its
    baseline, sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "shared-target-name")


def shared_target_name_vocabulary() -> frozenset[str]:
    """Every registered language's name and declared alias tokens.

    A registered language name is spelled by ``registered_language_names()``
    (the installed ``datrix.languages`` entry points); the aliases are that
    language's own declaration, never a literal list in this script.
    """
    vocabulary: set[str] = set()
    for language_name in sorted(registered_language_names()):
        vocabulary |= _language_name_tokens(language_name)
    return frozenset(vocabulary)


def _self_test_shared_target_name_scanner() -> bool:
    """_identifier_carries_target_name detects a target-name segment
    (including a compound camelCase target like TypeScript across two
    adjacent segments), rejects a look-alike single-segment word (java vs.
    javascript) and every sql/nosql-substring look-alike named in the
    design, and the full scanner does not flag a bare local variable inside
    a function body but DOES detect a plain module-level constant via the
    scoped Assign path."""
    report_step("Self-test 15/24: shared-target-name scanner (segment matching + non-flood proof)")
    ok = True

    # Synthetic vocabulary: "java" is kept only as the short name whose
    # look-alike ("javascript") proves segment matching is not substring matching.
    target_names = frozenset({"python", "typescript", "java"})

    ok &= _check(
        "PythonStructFieldRow carries the segment 'python'",
        _identifier_carries_target_name("PythonStructFieldRow", target_names) == "python",
    )
    ok &= _check(
        "TypeScriptStructTemplateSlice carries 'typescript' across two adjacent camelCase segments",
        _identifier_carries_target_name("TypeScriptStructTemplateSlice", target_names) == "typescript",
    )
    ok &= _check(
        "import_line_python carries the segment 'python'",
        _identifier_carries_target_name("import_line_python", target_names) == "python",
    )
    ok &= _check(
        "a hypothetical 'javascript' identifier does NOT match 'java' (no bare-substring false positive)",
        _identifier_carries_target_name("javascript", target_names) is None,
    )
    ok &= _check(
        "a target-neutral name (FooSliceProtocol) matches nothing",
        _identifier_carries_target_name("FooSliceProtocol", target_names) is None,
    )

    # The design named these four sql/nosql-substring identifiers as
    # look-alikes: the substring denotes a database technology
    # (postgresql/mysql dialects, the NoSQL store category), "sql" is not a
    # registered datrix.languages entry, and widening this vocabulary to any
    # group containing "sql" must break these assertions loudly.
    for lookalike in ("sql_engine", "sql_dialect", "NoSQLSeedWriter", "NoSqlFilterSyntax"):
        ok &= _check(
            f"{lookalike!r} is NOT flagged ('sql' is not a registered language)",
            _identifier_carries_target_name(lookalike, target_names) is None,
        )

    # Declared alias tokens: an alias segment matches, the name-only
    # vocabulary misses the same identifier (the non-vacuity pair), and the
    # match is segment-exact so ordinary words containing the alias do not hit.
    alias_vocabulary = frozenset({"python", "py", "typescript", "ts"})
    name_only_vocabulary = frozenset({"python", "typescript"})
    ok &= _check(
        "GraphqlTsFieldSpec carries the declared alias segment 'ts'",
        _identifier_carries_target_name("GraphqlTsFieldSpec", alias_vocabulary) == "ts",
    )
    ok &= _check(
        "GraphqlTsFieldSpec is MISSED by the registered-name-only vocabulary",
        _identifier_carries_target_name("GraphqlTsFieldSpec", name_only_vocabulary) is None,
    )
    for ordinary_word in ("tsunami", "timestamps"):
        ok &= _check(
            f"{ordinary_word!r} does NOT match the alias 'ts' (segment-exact, not substring)",
            _identifier_carries_target_name(ordinary_word, alias_vocabulary) is None,
        )
    live_vocabulary = shared_target_name_vocabulary()
    registered_names = frozenset(name.lower() for name in registered_language_names())
    ok &= _check(
        "shared_target_name_vocabulary() contains every registered language name",
        registered_names <= live_vocabulary,
    )
    ok &= _check(
        "at least one registered language declares an alias, so the vocabulary "
        "is strictly larger than the registered names (a vacuous extension is not a pass)",
        live_vocabulary > registered_names,
    )

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-target-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        non_flood_file = scratch_dir / "non_flood.py"
        non_flood_file.write_text(
            "def resolve_something() -> dict[str, object]:\n"
            "    local_cache = {}\n"
            "    is_local = True\n"
            "    for local in range(3):\n"
            "        local_cache[local] = is_local\n"
            "    return local_cache\n",
            encoding="utf-8",
        )
        non_flood_hits = scan_file_for_shared_target_names(non_flood_file, target_names)
        ok &= _check(
            "bare local variables/loop variables named 'local'/'local_cache'/'is_local' "
            "inside a function body produce ZERO hits",
            non_flood_hits == [],
        )

        function_body_assign_file = scratch_dir / "function_body_assign.py"
        function_body_assign_file.write_text(
            "def f() -> None:\n    python_helper = 1\n    return None\n",
            encoding="utf-8",
        )
        function_body_assign_hits = scan_file_for_shared_target_names(
            function_body_assign_file, target_names
        )
        ok &= _check(
            "a plain assignment INSIDE a function body (python_helper = 1) is NOT "
            "flagged -- the scoped Assign path covers module/class level only",
            function_body_assign_hits == [],
        )

        declaration_file = scratch_dir / "declaration.py"
        declaration_file.write_text("class PythonFooSlice:\n    value: str\n", encoding="utf-8")
        declaration_hits = scan_file_for_shared_target_names(declaration_file, target_names)
        ok &= _check(
            "a class declaration carrying a target-name segment IS flagged",
            len(declaration_hits) >= 1
            and any(h.matched_target == "python" for h in declaration_hits),
        )

        module_constant_file = scratch_dir / "module_constant.py"
        module_constant_file.write_text(
            "PYTHON_DEFAULT_PORT = 8000\n", encoding="utf-8"
        )
        module_constant_hits = scan_file_for_shared_target_names(
            module_constant_file, target_names
        )
        ok &= _check(
            "a plain MODULE-level constant (PYTHON_DEFAULT_PORT) IS flagged via "
            "the scoped Assign path, matched_target == 'python'",
            len(module_constant_hits) == 1
            and module_constant_hits[0].matched_target == "python"
            and module_constant_hits[0].kind == "field_or_alias",
        )

        # Declaration-vs-read precision pair (D4 residual-hit review): a
        # module DECLARING a field named for a target must still be flagged
        # after attribute_access was dropped as a declaration kind, while a
        # module that only READS an identically-named attribute off some
        # other object -- e.g. datrix-common's own ``ServicePaths.python_package``
        # -- must NOT be, because a read is not a declaration under G2's own
        # contract. Both live in ONE file so a single AST walk exercises the
        # AnnAssign declaration path and the plain-Attribute read in the same
        # scan, proving the narrowing removed exactly the false-positive kind
        # and nothing else.
        declaration_vs_read_file = scratch_dir / "declaration_vs_read.py"
        declaration_vs_read_file.write_text(
            "python_package: str = 'shared_pkg'\n"
            "\n"
            "def describe(paths: object) -> str:\n"
            "    return paths.python_package\n",
            encoding="utf-8",
        )
        declaration_vs_read_hits = scan_file_for_shared_target_names(
            declaration_vs_read_file, target_names
        )
        ok &= _check(
            "a module-level DECLARATION named 'python_package' IS flagged "
            "(exactly once, via the scoped Assign path)",
            len(declaration_vs_read_hits) == 1
            and declaration_vs_read_hits[0].identifier == "python_package"
            and declaration_vs_read_hits[0].matched_target == "python"
            and declaration_vs_read_hits[0].kind == "field_or_alias",
        )

        read_only_file = scratch_dir / "read_only.py"
        read_only_file.write_text(
            "def describe(paths: object) -> str:\n"
            "    return paths.python_package\n",
            encoding="utf-8",
        )
        read_only_hits = scan_file_for_shared_target_names(read_only_file, target_names)
        ok &= _check(
            "a bare READ of 'some_obj.python_package' (no local declaration of "
            "that name) produces ZERO hits -- attribute_access was dropped as a "
            "declaration kind because a read is not a declaration",
            read_only_hits == [],
        )

        # Annotated-assignment VALUE scope: a string in the value is a forward
        # reference only under a TypeAlias annotation; under any other
        # annotation it is data. Both forms live in one file, so the pair
        # proves the matcher still fires on the alias (non-vacuity).
        value_scope_file = scratch_dir / "value_scope.py"
        value_scope_file.write_text(
            "import typing\n"
            "from typing import TypeAlias\n"
            "EXTENSIONS: tuple[str, ...] = ('python', 'typescript')\n"
            "NEUTRAL: TypeAlias = 'python'\n"
            "QUALIFIED: typing.TypeAlias = 'typescript'\n",
            encoding="utf-8",
        )
        value_scope_refs = [
            (hit.line_number, hit.matched_target)
            for hit in scan_file_for_shared_target_names(value_scope_file, target_names)
            if hit.kind == "type_reference"
        ]
        ok &= _check(
            "string VALUES of a non-TypeAlias annotated assignment (line 3) are "
            "not type references; the same strings under TypeAlias / "
            "typing.TypeAlias (lines 4, 5) still are",
            sorted(value_scope_refs) == [(4, "python"), (5, "typescript")],
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return ok


def _self_test_shared_target_name_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-common package
    with a module declaring a target-NEUTRAL class, plus a baseline TOML
    freezing that file at count 0."""
    package_src = tmp_root / "datrix-codegen-common" / "src" / "datrix_codegen_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_slice.py"
    module_path.write_text(
        "class FooSliceProtocol:\n    value: str\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shared-target-name-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-common/src/datrix_codegen_common/sample_slice.py"\n'
        "count = 0\n"
        'reason = "fixture entry pinned at zero for the plant/observe/revert proof"\n',
        encoding="utf-8",
    )
    return module_path


def _self_test_live_alias_token() -> str | None:
    """A declared alias that is not any registered language's name, or None
    when no registered language declares one."""
    registered = {name.lower() for name in registered_language_names()}
    aliases = sorted(shared_target_name_vocabulary() - registered)
    return max(aliases, key=len) if aliases else None


def _self_test_shared_target_name_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--base-dir",
            str(tmp_root),
            "--check-shared-target-names",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_target_name_cli_non_vacuity() -> bool:
    """End-to-end proof the G2 shared-target-name ratchet actually FIRES.

    Starts from a fixture declaring a target-NEUTRAL class (the design's
    required POSITIVE case: exits 0), mutates it to a target-NAMED class
    (the required NEGATIVE case: exits 1, names the file), then reverts and
    proves it clears.
    """
    report_step(
        "Self-test 16/24: shared-target-name ratchet CLI mutation non-vacuity "
        "('class PythonFooSlice' and a live alias-token class exit 1; "
        "'class FooSliceProtocol' exits 0)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-target-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_target_name_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"target-neutral fixture (FooSliceProtocol) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text("class PythonFooSlice:\n    value: str\n", encoding="utf-8")
        failing_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"target-named fixture (PythonFooSlice) exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_slice.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        alias = _self_test_live_alias_token()
        ok &= _check(
            "the live registry declares at least one alias token that is not a "
            "registered language name (otherwise the alias case below is vacuous)",
            alias is not None,
        )
        if alias is not None:
            module_path.write_text(
                f"class {alias.capitalize()}FooSlice:\n    value: str\n", encoding="utf-8"
            )
            registered_name_hits = scan_file_for_shared_target_names(
                module_path, frozenset(name.lower() for name in registered_language_names())
            )
            ok &= _check(
                f"the registered-NAME-only vocabulary reports zero hits on "
                f"'{alias.capitalize()}FooSlice' (the failure below is caused by alias matching)",
                registered_name_hits == [],
            )
            alias_result = _self_test_shared_target_name_run_cli(tmp_root)
            ok &= _check(
                f"alias-token fixture ({alias.capitalize()}FooSlice) exits 1, "
                f"got {alias_result.returncode}",
                alias_result.returncode == 1,
            )
            ok &= _check(
                "alias failure output names the mutated file",
                "sample_slice.py" in alias_result.stdout,
            )
            ok &= _check(
                "alias failure output names the exact count delta (0 -> 1)",
                "increased from baseline 0 to 1" in alias_result.stdout,
            )
            module_path.write_text(clean_source, encoding="utf-8")
            alias_reverted_result = _self_test_shared_target_name_run_cli(tmp_root)
            ok &= _check(
                f"reverting the alias mutation clears the failure, got exit "
                f"{alias_reverted_result.returncode}",
                alias_reverted_result.returncode == 0,
            )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_ratchets() -> bool:
    """All three ratchet comparators fire on any per-file increase, never on
    a decrease, and treat a baseline-absent file as baseline 0."""
    report_step("Self-test 7/24: ratchet comparators (regression / no-regression / missing-baseline-as-zero)")
    ok = True

    clean = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check("provider-conditional ratchet: clean when current == baseline", clean == [])

    increase = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 4},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check(
        "provider-conditional ratchet: fires once on a real increase, naming file + delta",
        len(increase) == 1 and "foo.py" in increase[0] and "increased from baseline 3 to 4" in increase[0],
    )

    decrease = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 1},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check("provider-conditional ratchet: allows a decrease", decrease == [])

    missing_baseline = check_provider_conditional_ratchet(
        {"datrix-codegen-typescript/src/datrix_codegen_typescript/new_file.py": 1}, {}
    )
    ok &= _check(
        "provider-conditional ratchet: a file absent from baseline is treated as baseline 0",
        len(missing_baseline) == 1 and "increased from baseline 0 to 1" in missing_baseline[0],
    )

    fli_clean = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 2},
        {"datrix-common/src/datrix_common/foo.py": 2},
    )
    ok &= _check("function-level-import ratchet: clean when current == baseline", fli_clean == [])

    fli_increase = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 3},
        {"datrix-common/src/datrix_common/foo.py": 2},
    )
    ok &= _check(
        "function-level-import ratchet: fires once on a real increase, naming file + delta",
        len(fli_increase) == 1
        and "foo.py" in fli_increase[0]
        and "increased from baseline 2 to 3" in fli_increase[0],
    )

    fli_decrease = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 1},
        {"datrix-common/src/datrix_common/foo.py": 5},
    )
    ok &= _check("function-level-import ratchet: allows a decrease", fli_decrease == [])

    fli_missing_baseline = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/new_file.py": 1}, {}
    )
    ok &= _check(
        "function-level-import ratchet: a file absent from baseline is treated as baseline 0",
        len(fli_missing_baseline) == 1
        and "increased from baseline 0 to 1" in fli_missing_baseline[0],
    )

    shared_vocab_clean = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
    )
    ok &= _check(
        "shared-vocabulary ratchet: clean when current == baseline", shared_vocab_clean == []
    )

    shared_vocab_increase = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
    )
    ok &= _check(
        "shared-vocabulary ratchet: fires once on a real increase, naming file + delta",
        len(shared_vocab_increase) == 1
        and "foo.py" in shared_vocab_increase[0]
        and "increased from baseline 2 to 3" in shared_vocab_increase[0],
    )

    shared_vocab_decrease = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 1},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 5},
    )
    ok &= _check(
        "shared-vocabulary ratchet: allows a decrease", shared_vocab_decrease == []
    )

    shared_vocab_missing_baseline = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/new_file.py": 1}, {}
    )
    ok &= _check(
        "shared-vocabulary ratchet: a file absent from baseline is treated as baseline 0",
        len(shared_vocab_missing_baseline) == 1
        and "increased from baseline 0 to 1" in shared_vocab_missing_baseline[0],
    )

    shared_target_name_clean = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
    )
    ok &= _check(
        "shared-target-name ratchet: clean when current == baseline",
        shared_target_name_clean == [],
    )

    shared_target_name_increase = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 3},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
    )
    ok &= _check(
        "shared-target-name ratchet: fires once on a real increase, naming file + delta",
        len(shared_target_name_increase) == 1
        and "foo.py" in shared_target_name_increase[0]
        and "increased from baseline 2 to 3" in shared_target_name_increase[0],
    )

    shared_target_name_decrease = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 1},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 5},
    )
    ok &= _check(
        "shared-target-name ratchet: allows a decrease", shared_target_name_decrease == []
    )

    shared_target_name_missing_baseline = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/new_file.py": 1}, {}
    )
    ok &= _check(
        "shared-target-name ratchet: a file absent from baseline is treated as baseline 0",
        len(shared_target_name_missing_baseline) == 1
        and "increased from baseline 0 to 1" in shared_target_name_missing_baseline[0],
    )

    reasoned_file = "datrix-codegen-common/src/datrix_codegen_common/reasoned.py"
    reasonless_file = "datrix-codegen-common/src/datrix_codegen_common/reasonless.py"
    awkward_reason = 'identifiers "Foo" and C:\\bar stay; driven to zero by a rename'
    reason_messages = check_shared_target_name_reasons(
        CountBaseline(
            counts={reasoned_file: 1, reasonless_file: 2},
            reasons={reasoned_file: awkward_reason},
        )
    )
    ok &= _check(
        "shared-target-name reasons: fires once, for the entry without a reason only",
        len(reason_messages) == 1
        and reasonless_file in reason_messages[0]
        and "baseline entry carries no reason" in reason_messages[0],
    )

    reason_scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-target-reasons-{uuid.uuid4().hex}"
    reason_scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        round_trip_path = reason_scratch_dir / "baseline.toml"
        write_shared_target_name_baseline(
            round_trip_path,
            {reasoned_file: 1, reasonless_file: 2},
            {reasoned_file: awkward_reason},
        )
        loaded = load_count_baseline(round_trip_path)
        ok &= _check(
            "shared-target-name baseline: a reason with a double quote and a backslash "
            "survives write/load byte-for-byte",
            loaded.reasons.get(reasoned_file) == awkward_reason,
        )
        ok &= _check(
            "shared-target-name baseline: an entry written without a reason loads without "
            "one (a reason is never invented) and counts round-trip",
            reasonless_file not in loaded.reasons
            and loaded.counts == {reasoned_file: 1, reasonless_file: 2},
        )
    finally:
        shutil.rmtree(reason_scratch_dir, ignore_errors=True)

    return ok


def self_test_checks() -> list[NamedCheck]:
    """The shared-target-name scanner's and the ratchets' self-tests, each a check the CLI runs."""
    return [
        self_test_check(_self_test_ratchets),
        self_test_check(_self_test_shared_target_name_scanner),
        self_test_check(_self_test_shared_target_name_cli_non_vacuity),
    ]
