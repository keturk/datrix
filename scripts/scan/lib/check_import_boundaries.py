#!/usr/bin/env python3
"""Cross-package import boundary scanner for Datrix monorepo.

Enforces architectural dependency rules by scanning all Python source files
in each package's src/, tests/, fixtures/, and helpers/ directories (when they
exist) and checking imports against forbidden prefix rules. Uses AST parsing -
no package installation required.

Also implements the I1 target-literal ratchet:
opt-in via --check-target-literals, it AST-scans the DERIVED shared-package
src/ trees (discover_shared_packages: every discovered package registering
none of datrix.languages/datrix.platforms/datrix.generators/
datrix.extensions -- datrix_common, datrix_codegen_common, and datrix_cli
today, never a hardcoded list) for known closed-world target-identity
identifiers PLUS a platform-token identifier/module-name shape match
(mirrors the G2 language-token shape match, minus the "local" collision --
see _platform_token_vocabulary) PLUS a key/comparand/.get()/dict-key/
match-value literal-equality shape, an isinstance/issubclass type-check
shape, and an import-module-path shape -- each of these three newer kinds
scoped to the registered languages-union-platforms vocabulary INCLUDING
"local" (see _target_literal_vocabulary) and each carrying an own-language
exclusion for a language-core package's own served language (see
LANGUAGE_CORE_PACKAGES / _is_own_language_excluded) -- and fails if any
file's count increases past its frozen baseline
(scripts/config/target-literal-baseline.toml).
--update-baseline recomputes and overwrites that baseline.

Also implements the I6 successor ratchet (invariant I6, DI-4/DI-5):
opt-in via --check-provider-conditionals, it AST-scans the LANGUAGE
package src/ trees (the packages whose manifests register a
``datrix.languages`` entry point -- see discover_generator_taxonomy) for
platform-identity CONDITIONALS -- the successor forms of the removed
DeploymentProvider branches (`== ProviderId(...)`, `.value == "..."`,
`match`/`case` over a provider), PLUS a second AST pattern class: a
bare `<var> == "<provider-id>"` comparison with no `ProviderId`/`.provider`
wrapper, and a closed-world provider-id collection literal such as
`frozenset({"azure"})` -- and fails if any file's count increases past its
frozen baseline (scripts/config/provider-conditional-baseline.toml).
These sites are DI-5-deferred; the ratchet freezes them so they cannot grow,
and drives to zero as each cluster is migrated onto a decision engine.
--update-baseline (combined with --check-provider-conditionals) recomputes
and overwrites that baseline.

Also implements a DISTINCT, stricter D6.1 check that runs unconditionally
whenever --check-provider-conditionals is passed: the same two D5 patterns
plus the pre-existing ProviderId/match-case forms, applied to the DERIVED
shared-package set (discover_shared_packages -- datrix_common,
datrix_codegen_common, and datrix_cli today, never a hardcoded list) and
held at a hard zero with no baseline file to grandfather a hit into -- any
single occurrence fails, since shared layers must never encode
platform-specific policy (Principle 10, D1).

Also implements the function-level-import ratchet:
via --check-function-level-imports, it AST-scans the code that was
datrix-common's before the foundation packages were extracted from it (the
src/ trees of FUNCTION_LEVEL_IMPORT_PACKAGES, plus each file a baseline entry
names in another package) for function-level imports (an Import/ImportFrom
AST node that is not a direct top-level statement of its module -- nested in
a function/method body, an `if TYPE_CHECKING:` block, or a `try`/`except`)
and fails if any file's count increases past its frozen baseline
(scripts/config/function-level-import-baseline.toml), or if any baseline
entry is inert, empty, or carries no written reason (the cycle that forces
the deferral, or its measured import cost).
--update-baseline (combined with --check-function-level-imports) lowers that
baseline to the current counts and drops emptied entries; it refuses to
raise any count.

Also implements the G1 shared-vocabulary ratchet (Decision D3, Invariant I2):
opt-in via --check-shared-vocabulary, it AST-scans the LANGUAGE package src/
trees (the ``datrix.languages`` packages the manifests declare) for a module-level
frozenset/set/dict whose normalized member set duplicates a vocabulary
already declared in datrix_codegen_kernel.enums (read live from the
installed package at scan time, never mirrored) -- the DSL vocabulary
re-scattered as hand-rolled string literals after being centralised -- and
fails if any file's count increases past its frozen baseline
(scripts/config/shared-vocabulary-baseline.toml). A container built entirely
from qualified EnumClass.MEMBER references is CONSUMING the enum, not
hardcoding it, and is never flagged. The canonical side of this comparison
covers every module-level member-set declaration in enums.py, not only
``str, Enum`` classes: a plain module-level dict's KEY set (e.g.
DSL_EXCEPTION_HTTP_STATUS, NOSQL_UNSUPPORTED_METHODS) or a set/frozenset's
element set (e.g. NOSQL_SUPPORTED_METHODS) is exactly as canonical as an Enum class's value
set, and a bare-literal redeclaration of either is the same defect.
--update-baseline (combined with --check-shared-vocabulary) recomputes and
overwrites that baseline.

Also implements the G2 shared-layer target-name ratchet (Decision D4, Invariant I3):
opt-in via --check-shared-target-names, it AST-scans ONLY the src/ trees of
SHARED_TARGET_NAME_PACKAGES (datrix_codegen_common and datrix_codegen_kernel --
deliberately narrower than I1's derived shared-package scope) for any class,
function, dataclass field, type alias, or type reference whose identifier carries
a registered LANGUAGE name OR one of that language's declared ALIAS tokens
(``declaration_for_language(lang).name_tokens``, e.g. ``ts``) as an identifier
segment (read live via shared_target_name_vocabulary() --
datrix.platforms is never consulted, since the registered platform name "local" is
also an ordinary English word). This is a DIFFERENT check from I1 -- I1 matches a
frozen list of specific central-table names, G2 matches the SHAPE of an identifier
against an open, runtime-derived vocabulary, so it would catch a brand-new
language-named class I1's frozen list has never heard of. Fails if any file's
count increases past its frozen baseline
(scripts/config/shared-target-name-baseline.toml), or if a baseline entry carries
no written ``reason``.
--update-baseline (combined with --check-shared-target-names) recomputes the
counts and preserves every written reason.

Also implements the I4 own-target-name ratchet (Decision D5, Invariant I4):
opt-in via --check-own-target-names, it AST-scans EVERY registered LANGUAGE
package's own src/ tree (the discovered taxonomy's language_packages -- the
same source I6/G1 already use, never a hardcoded per-language tuple) for a
function or method DEFINITION whose name carries THAT SAME package's own
registered language id or declared alias (read live via
``declaration_for_language(lang).name_tokens | {lang}``, never a hardcoded
per-language literal set) as an identifier segment. This is the mirror image
of G2 -- G2 holds the ONE shared-layer package to zero symbols carrying ANY
registered language's name; I4 holds EVERY language package to zero
functions carrying ITS OWN name -- the token that hides a parallel
implementation from a name-keyed behaviour-parity scan (a function inside
datrix_codegen_python does not need "python" in its name; the package already
says it). Scope is FUNCTION/METHOD DEFINITION names only -- never a class
name, dataclass field, or type reference (a language package legitimately
references its own types by name everywhere). Fails if any package's count
increases past its frozen baseline
(scripts/config/own-target-name-baseline.toml).
--update-baseline (combined with --check-own-target-names) recomputes and
overwrites that baseline.

Also implements the G3 cross-package vocabulary ratchet (Decision D2.1-D2.4):
opt-in via --check-cross-package-vocabulary, it AST-scans EVERY discovered
datrix-* package's src/ tree (via discover_packages() -- not only the four
LANGUAGE packages G1 scans) for a module-level set/frozenset/dict/tuple
literal, normalizes each one's member set, and fails when the SAME
normalized member set is declared with a bare string literal in two or
more DISTINCT packages -- independent of whether either copy also
duplicates a datrix_codegen_kernel.enums vocabulary (that comparison is
G1's job; G3 compares packages against each other directly, with no
notion of a canonical source). A value set declared twice within the SAME
package is a different, already-tracked defect (intra-package DRY, not
G3) and is never counted here. A container built entirely from qualified
EnumClass.MEMBER references is CONSUMING a vocabulary, not hardcoding it,
and is never flagged -- the same has_bare_literal gate G1 uses, classified
PURELY BY AST SHAPE (never by resolving against datrix_codegen_kernel.enums
the way G1 does -- G3 must never consult that module). Fails if
any file's count increases past its frozen baseline
(scripts/config/cross-package-vocabulary-baseline.toml).
--update-baseline (combined with --check-cross-package-vocabulary)
recomputes and overwrites that baseline. An entry carrying a `reason`
key is a duplicate a design requires (Decision 36 D9) and the reason is
part of the frozen record: the regeneration reads every reason back and
re-emits it, and names any reasoned entry that no longer has a hit.

Also implements the re-export-facade ratchet: opt-in via
--check-reexport-facades, it AST-scans every discovered package's `src/`
and `tests/` trees, every `.py` file under this repo's own `datrix/scripts/`
tree, and every `.py` file under `datrix/claude-config/.claude/hooks/` (if
any), for a name that has a second, redundant import path on top of its
real, single home -- a re-export facade -- reporting five shapes, all
attributed to the PROVIDING module (the module through which the second
path runs), never to the file where a consumer statement happens to
appear: a module whose top-level `from <datrix module> import N` binds a
name listed in its own `__all__` or imported as `N as N` while the module
does not itself define N (provider side); any `from M import N` anywhere
in a scanned file where M is a Datrix module that does not define N and N
is not itself a submodule of M (consumer side); a module held as an object
(`import M as m`, `from pkg import M`) whose attribute is read as `m.N` or
`getattr(m, "N")` while M does not define N (module-object side); a
`pyproject.toml` `[project.entry-points.*]` value naming an attribute its
target module does not define (entry-point side); and a `from M import N`
whose M does not resolve to any module on disk at all (unresolved). A
test-tree module (`tests.<module>`, resolved against the importing file's
own package) is a provider like any Datrix module, and a name bound only
for a DAL generator `<namespace>.<module>.<name>` reference (read from the
definitions text, namespace resolved by the kernel registry) is not a
provider-side hit. Relative imports
(`from .a import X`, `from . import sub`) are resolved to their absolute
module from the scanned file's own dotted name, on both the provider and the
consumer side, and every package's root-level `.py` files (e.g. `conftest.py`)
are scanned too. This is a HARD ZERO with NO
baseline file: any hit fails, one failure message per hit, and
--update-baseline has no effect on this check (there is nothing to seed).
`--facade-module`/`--consumer-package` (repeatable) narrow the `--verbose`
per-site worklist to one providing module or one repo.

Self-test (--self-test): proves the rule model (the manifest-discovered
generator taxonomy, build_boundary_rules over it, the allowed-
subtree carve-outs), the AST scanners (provider-conditional,
function-level-import, shared-vocabulary, shared-target-name,
own-target-name, cross-package-vocabulary, target-literal,
re-export-facade),
and the ratchet comparators are non-vacuous --
including a real mutation-based CLI proof (plants a
regression in an isolated fixture monorepo, proves the CLI detects it,
proves it clears on revert). The self-test runs automatically as step 1 of
EVERY normal invocation of this script (not only when --self-test is
passed): a run whose self-test fails aborts before any real finding is
reported, since a checker that cannot prove its own logic cannot be trusted.
Pass --self-test alone to run only the self-test and skip the real scan.
--skip-auto-self-test is an internal flag used solely by the self-test's own
nested CLI invocation (to avoid it recursively re-running the self-test on
itself) and is not intended for direct use.

Exit codes:
    0: Clean (no violations) or --warn mode
    1: Violations found in fail mode (import-boundary and/or I1/I6/function-
       level-import/shared-vocabulary/shared-target-name/own-target-name/
       cross-package-vocabulary/re-export-facade ratchets), or a
       self-test failure
    2: Usage error, configuration error, or (with --check-target-literals,
       --check-provider-conditionals, --check-function-level-imports,
       --check-shared-vocabulary, --check-shared-target-names,
       --check-own-target-names, or --check-cross-package-vocabulary) a
       missing baseline file
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    report_fail,
    report_ok,
    run_checks,
)
from datrix_scripts.paths import WORKSPACE_DIR
from import_boundaries import (
    cross_package_vocabulary,
    function_level_imports,
    own_target_names,
    provider_conditionals,
    reexport_facades,
    shared_target_names,
    shared_vocabulary,
    target_literals,
)
from import_boundaries import taxonomy as taxonomy_scanner
from import_boundaries._ast_common import CountBaseline, PackageInfo, load_count_baseline
from import_boundaries.cross_package_vocabulary import (
    check_cross_package_vocabulary_ratchet,
    scan_cross_package_vocabulary,
    write_cross_package_vocabulary_baseline,
)
from import_boundaries.function_level_imports import (
    FunctionLevelImportBaseline,
    FunctionLevelImportBaselineError,
    check_function_level_import_baseline_entries,
    check_function_level_import_ratchet,
    load_function_level_import_baseline,
    lowered_function_level_import_baseline,
    scan_function_level_imports,
    write_function_level_import_baseline,
)
from import_boundaries.own_target_names import (
    OWN_TARGET_NAME_BASELINE_KEY,
    check_own_target_name_ratchet,
    scan_own_target_names,
    write_own_target_name_baseline,
)
from import_boundaries.provider_conditionals import (
    check_provider_conditional_ratchet,
    check_shared_package_provider_literals,
    scan_provider_conditionals,
    scan_shared_package_provider_literals,
    write_provider_conditional_baseline,
)
from import_boundaries.reexport_facades import (
    check_reexport_facades,
    format_reexport_facade_worklist,
    scan_reexport_facades,
)
from import_boundaries.shared_target_names import (
    check_shared_target_name_ratchet,
    check_shared_target_name_reasons,
    scan_shared_target_names,
    write_shared_target_name_baseline,
)
from import_boundaries.shared_vocabulary import (
    check_shared_vocabulary_ratchet,
    scan_shared_vocabulary,
    write_shared_vocabulary_baseline,
)
from import_boundaries.target_literals import (
    check_identity_rules_hard_zero,
    check_target_literal_ratchet,
    scan_target_literals,
    write_target_literal_baseline,
)
from import_boundaries.taxonomy import (
    LANGUAGES_ENTRY_POINT_GROUP,
    PLATFORMS_ENTRY_POINT_GROUP,
    AllowlistEntry,
    BoundaryRule,
    GeneratorTaxonomy,
    GeneratorTaxonomyError,
    Violation,
    build_boundary_rules,
    discover_generator_taxonomy,
    discover_packages,
    discover_shared_packages,
    format_violation,
    is_allowlisted,
    load_allowlist,
    scan_package_for_violations,
    unruled_packages,
)

#: Every scanner module, in the order its self-tests run.
_SCANNER_MODULES: tuple[ModuleType, ...] = (
    taxonomy_scanner,
    provider_conditionals,
    function_level_imports,
    shared_target_names,
    shared_vocabulary,
    cross_package_vocabulary,
    own_target_names,
    target_literals,
    reexport_facades,
)

#: Where the allowlist and every baseline live, relative to the monorepo root.
_CONFIG_DIR_PARTS: tuple[str, ...] = ("datrix", "scripts", "config")
_ALLOWLIST_FILE = "import-boundary-allowlist.toml"
_TARGET_LITERAL_BASELINE = "target-literal-baseline.toml"
_PROVIDER_CONDITIONAL_BASELINE = "provider-conditional-baseline.toml"
_FUNCTION_LEVEL_IMPORT_BASELINE = "function-level-import-baseline.toml"
_SHARED_VOCABULARY_BASELINE = "shared-vocabulary-baseline.toml"
_SHARED_TARGET_NAME_BASELINE = "shared-target-name-baseline.toml"
_CROSS_PACKAGE_VOCABULARY_BASELINE = "cross-package-vocabulary-baseline.toml"
_OWN_TARGET_NAME_BASELINE = "own-target-name-baseline.toml"

_UNTRUSTED_CHECKER = (
    "\nError: self-test failed -- the checker itself is not provably "
    "correct, so its findings cannot be trusted. Fix the self-test "
    "failure(s) above before relying on this gate's result."
)


class _ConfigurationError(Exception):
    """The scan cannot run as configured (exit 2); printed as ``Error: <message>``."""


class _UpdateRefused(Exception):
    """A baseline update refused to proceed (exit 1) after printing why."""


@dataclass(frozen=True)
class _ScanContext:
    """The discovered monorepo every check of one run scans, and how it reports."""

    root: Path
    allowlist: list[AllowlistEntry]
    packages: dict[str, PackageInfo]
    taxonomy: GeneratorTaxonomy
    rules: dict[str, BoundaryRule]
    shared_packages: tuple[str, ...]
    verbose: bool
    facade_modules: frozenset[str]
    consumer_packages: frozenset[str]

    def config_path(self, file_name: str) -> Path:
        return self.root.joinpath(*_CONFIG_DIR_PARTS, file_name)

    def relative(self, path: Path) -> Path:
        return path.relative_to(self.root)

    def file_counts(self, hits_by_file: Mapping[Path, Sequence[object]]) -> dict[str, int]:
        """``{root-relative file, forward slashes: hit count}``."""
        return {self.relative(path).as_posix(): len(hits) for path, hits in hits_by_file.items()}


@dataclass(frozen=True)
class _Outcome:
    """One check's result: its failure messages, and what it prints otherwise.

    ``preamble`` is printed before the report of a checking run; ``clean_lines`` only when the
    whole run is clean.
    """

    messages: list[str]
    clean_lines: tuple[str, ...] = ()
    preamble: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Check:
    """One opt-in check: when it runs, how it reports, and how it computes its outcome.

    A ``hard_zero`` check has no baseline; it runs in an ``--update-baseline`` run too, where
    a hit refuses the run with ``update_header``.
    """

    enabled: Callable[[argparse.Namespace], bool]
    header: str
    clean_note: str
    run: Callable[[_ScanContext], _Outcome]
    hard_zero: bool = False
    update_header: str = ""


@dataclass(frozen=True)
class _Update:
    """One baseline an ``--update-baseline`` run rewrites when its flag is passed."""

    enabled: Callable[[argparse.Namespace], bool]
    run: Callable[[_ScanContext], None]


def run_self_test() -> bool:
    """Run every scanner module's self-test checks; return True iff all passed.

    This is the checker's own non-vacuity proof: the rule-model constants,
    the AST scanners, and the ratchet comparators are exercised against
    known-good and known-bad cases (including a real mutation-based CLI
    proof), so a change that silently breaks any of them is caught before
    the checker's findings are trusted.
    """
    checks = [check for module in _SCANNER_MODULES for check in module.self_test_checks()]
    passed = run_checks(checks, also_failing=(FileNotFoundError, GeneratorTaxonomyError))
    print()
    if passed:
        report_ok("SELF-TEST PASSED: rule model, scanners, and ratchets are non-vacuous.")
    else:
        report_fail("SELF-TEST FAILED: see failures above.")
    return passed


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _scan_context(args: argparse.Namespace) -> _ScanContext:
    """Discover the packages, the taxonomy, its rules and the shared-package set.

    A discovered package with no rule would be scanned against nothing and read
    as clean, so that state is refused rather than tolerated; so is a package
    the shared-package derivation cannot classify.
    """
    root = args.base_dir.resolve() if args.base_dir else WORKSPACE_DIR
    if not root.exists():
        raise _ConfigurationError(f"Monorepo root not found: {root}")
    allowlist = load_allowlist(root.joinpath(*_CONFIG_DIR_PARTS, _ALLOWLIST_FILE))
    packages = discover_packages(root)
    if not packages:
        raise _ConfigurationError(f"No datrix packages found in {root}")
    try:
        taxonomy = discover_generator_taxonomy(root)
    except GeneratorTaxonomyError as exc:
        raise _ConfigurationError(str(exc)) from exc
    rules = build_boundary_rules(taxonomy)
    unruled = unruled_packages(packages, rules)
    if unruled:
        raise _ConfigurationError(
            f"discovered package(s) {unruled} have no boundary rule. A package "
            f"is classified from its pyproject.toml entry points -- register "
            f"'{LANGUAGES_ENTRY_POINT_GROUP}' (language generator) or "
            f"'{PLATFORMS_ENTRY_POINT_GROUP}' (platform generator) -- or, for a "
            f"generator that is neither (SQL, Component, a client target), add an explicit "
            f"entry to build_boundary_rules(). Refusing to scan a package against no "
            f"rule: that would report it clean without checking anything."
        )
    try:
        shared_packages = discover_shared_packages(root, packages)
    except GeneratorTaxonomyError as exc:
        raise _ConfigurationError(str(exc)) from exc
    return _ScanContext(
        root=root,
        allowlist=allowlist,
        packages=packages,
        taxonomy=taxonomy,
        rules=rules,
        shared_packages=shared_packages,
        verbose=args.verbose,
        facade_modules=frozenset(args.facade_module),
        consumer_packages=frozenset(args.consumer_package),
    )


def _print_discovery(ctx: _ScanContext) -> None:
    print(f"Found {len(ctx.packages)} packages:", file=sys.stderr)
    for package_name in sorted(ctx.packages):
        print(f"  - {package_name}", file=sys.stderr)
    print(
        f"Taxonomy (from manifests): languages={list(ctx.taxonomy.language_packages)} "
        f"platforms={list(ctx.taxonomy.platform_packages)}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def _boundary_violations(ctx: _ScanContext) -> list[Violation]:
    """Every import-boundary violation the allowlist does not exempt."""
    violations = [
        violation
        for _, package_info in sorted(ctx.packages.items())
        for violation in scan_package_for_violations(package_info, ctx.root, ctx.verbose, ctx.rules)
    ]
    return [v for v in violations if not is_allowlisted(v, ctx.allowlist, ctx.root)]


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def _existing_baseline(ctx: _ScanContext, file_name: str, label: str, flag: str) -> Path:
    """The baseline's path; a missing baseline refuses the check (exit 2)."""
    path = ctx.config_path(file_name)
    if not path.exists():
        raise _ConfigurationError(
            f"{label} baseline not found at {path}. Run "
            f"'check_import_boundaries.py {flag} --update-baseline' "
            f"first to freeze the initial baseline."
        )
    return path


def _function_level_baseline(ctx: _ScanContext, remedy: str) -> FunctionLevelImportBaseline:
    """The function-level-import baseline; missing or malformed refuses the run (exit 2)."""
    path = ctx.config_path(_FUNCTION_LEVEL_IMPORT_BASELINE)
    if not path.exists():
        raise _ConfigurationError(f"function-level-import baseline not found at {path}. {remedy}")
    try:
        return load_function_level_import_baseline(path)
    except FunctionLevelImportBaselineError as exc:
        raise _ConfigurationError(str(exc)) from exc


def _previous_reasons(path: Path) -> dict[str, str]:
    """The written reasons of the baseline being regenerated (none on its first freeze)."""
    return load_count_baseline(path).reasons if path.exists() else {}


def _report_update(
    ctx: _ScanContext, label: str, count: int, unit: str, path: Path, suffix: str = ""
) -> None:
    print(f"Updated {label} baseline: {count} {unit} recorded at {ctx.relative(path)}{suffix}")


def _print_block(header: str, messages: list[str]) -> None:
    print(header)
    for message in messages:
        print(message)
    print()


def _warn_vanished_reasons(previous: dict[str, str], current: dict[str, int], warning: str) -> None:
    """Name every reasoned entry the regeneration dropped (``warning`` takes ``{entry}``)."""
    for vanished in sorted(previous.keys() - current.keys()):
        print(warning.format(entry=vanished), file=sys.stderr)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _target_literal_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx, _TARGET_LITERAL_BASELINE, "I1 target-literal", "--check-target-literals"
    )
    baseline = load_count_baseline(path).counts
    hits = scan_target_literals(ctx.packages, ctx.root, ctx.shared_packages)
    return _Outcome(
        check_target_literal_ratchet(ctx.file_counts(hits), baseline)
        + check_identity_rules_hard_zero(hits, baseline, ctx.root)
    )


def _provider_conditional_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx,
        _PROVIDER_CONDITIONAL_BASELINE,
        "I6 provider-conditional",
        "--check-provider-conditionals",
    )
    hits = scan_provider_conditionals(ctx.packages, ctx.root, ctx.taxonomy.language_packages)
    return _Outcome(
        check_provider_conditional_ratchet(ctx.file_counts(hits), load_count_baseline(path).counts)
    )


def _shared_package_provider_literal_outcome(ctx: _ScanContext) -> _Outcome:
    hits = scan_shared_package_provider_literals(ctx.packages, ctx.root, ctx.shared_packages)
    clean = (
        "Shared-package provider-literal zero-tolerance check: 0 hits "
        f"({', '.join(ctx.shared_packages)}).",
    )
    return _Outcome(check_shared_package_provider_literals(hits, ctx.root), clean_lines=clean)


def _function_level_import_outcome(ctx: _ScanContext) -> _Outcome:
    baseline = _function_level_baseline(
        ctx,
        "The ratchet cannot run without its frozen record; restore the file from version control.",
    )
    hits = scan_function_level_imports(ctx.packages, ctx.root, frozenset(baseline.counts))
    return _Outcome(
        check_function_level_import_baseline_entries(baseline, ctx.packages, ctx.root)
        + check_function_level_import_ratchet(ctx.file_counts(hits), baseline.counts)
    )


def _shared_vocabulary_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx, _SHARED_VOCABULARY_BASELINE, "G1 shared-vocabulary", "--check-shared-vocabulary"
    )
    hits = scan_shared_vocabulary(ctx.packages, ctx.root, ctx.taxonomy.language_packages)
    return _Outcome(
        check_shared_vocabulary_ratchet(ctx.file_counts(hits), load_count_baseline(path).counts)
    )


def _shared_target_name_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx, _SHARED_TARGET_NAME_BASELINE, "G2 shared-target-name", "--check-shared-target-names"
    )
    baseline: CountBaseline = load_count_baseline(path)
    hits = scan_shared_target_names(ctx.packages, ctx.root)
    return _Outcome(
        check_shared_target_name_ratchet(ctx.file_counts(hits), baseline.counts)
        + check_shared_target_name_reasons(baseline)
    )


def _cross_package_vocabulary_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx,
        _CROSS_PACKAGE_VOCABULARY_BASELINE,
        "G3 cross-package-vocabulary",
        "--check-cross-package-vocabulary",
    )
    hits = scan_cross_package_vocabulary(ctx.packages, ctx.root)
    return _Outcome(
        check_cross_package_vocabulary_ratchet(
            ctx.file_counts(hits), load_count_baseline(path).counts
        )
    )


def _own_target_name_counts(ctx: _ScanContext) -> dict[str, int]:
    """``{registered language package: own-target-name hit count}``, zero included."""
    hits = scan_own_target_names(ctx.packages, ctx.root, ctx.taxonomy.language_packages)
    return {name: len(hits.get(name, [])) for name in ctx.taxonomy.language_packages}


def _own_target_name_outcome(ctx: _ScanContext) -> _Outcome:
    path = _existing_baseline(
        ctx, _OWN_TARGET_NAME_BASELINE, "I4 own-target-name", "--check-own-target-names"
    )
    baseline = load_count_baseline(path, key_field=OWN_TARGET_NAME_BASELINE_KEY).counts
    counts = _own_target_name_counts(ctx)
    live = [f"  {name}: {counts[name]}" for name in sorted(counts)] or [
        "  (no registered language package discovered)"
    ]
    return _Outcome(
        check_own_target_name_ratchet(counts, baseline),
        clean_lines=("I4 own-target-name live counts (per registered language package):", *live),
    )


def _reexport_facade_outcome(ctx: _ScanContext) -> _Outcome:
    hits_by_module = scan_reexport_facades(ctx.packages, ctx.root)
    preamble: tuple[str, ...] = ()
    if ctx.verbose:
        worklist = format_reexport_facade_worklist(
            hits_by_module,
            ctx.root,
            facade_modules=ctx.facade_modules,
            consumer_packages=ctx.consumer_packages,
        )
        preamble = (f"Re-export-facade worklist ({len(worklist)} site(s)):", *worklist, "")
    return _Outcome(
        check_reexport_facades(hits_by_module, ctx.root),
        clean_lines=("Re-export-facade check: 0 hits.",),
        preamble=preamble,
    )


#: Every opt-in check, in report order.
_CHECKS: tuple[_Check, ...] = (
    _Check(
        enabled=lambda args: args.check_target_literals,
        header="I1 target-literal ratchet failed for {count} file(s)",
        clean_note="No I1 target-literal ratchet regressions found.",
        run=_target_literal_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_provider_conditionals,
        header="I6 provider-conditional ratchet failed for {count} file(s)",
        clean_note="No I6 provider-conditional ratchet regressions found.",
        run=_provider_conditional_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_provider_conditionals,
        header=(
            "shared-package provider-literal zero-tolerance check failed for {count} "
            "occurrence(s) (no baseline -- any hit fails)"
        ),
        clean_note="",
        run=_shared_package_provider_literal_outcome,
        hard_zero=True,
        update_header=(
            "Error: shared-package provider-literal zero-tolerance check failed "
            "for {count} occurrence(s) -- "
            "these packages have no baseline to update; fix the code instead:\n"
        ),
    ),
    _Check(
        enabled=lambda args: args.check_function_level_imports,
        header="function-level-import ratchet failed with {count} finding(s)",
        clean_note="No function-level-import ratchet regressions found.",
        run=_function_level_import_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_shared_vocabulary,
        header="G1 shared-vocabulary ratchet failed for {count} file(s)",
        clean_note="No G1 shared-vocabulary ratchet regressions found.",
        run=_shared_vocabulary_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_shared_target_names,
        header="G2 shared-target-name ratchet failed for {count} file(s)",
        clean_note="No G2 shared-target-name ratchet regressions found.",
        run=_shared_target_name_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_cross_package_vocabulary,
        header="G3 cross-package-vocabulary ratchet failed for {count} file(s)",
        clean_note="No G3 cross-package-vocabulary ratchet regressions found.",
        run=_cross_package_vocabulary_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_own_target_names,
        header="I4 own-target-name ratchet failed for {count} package(s)",
        clean_note="No I4 own-target-name ratchet regressions found.",
        run=_own_target_name_outcome,
    ),
    _Check(
        enabled=lambda args: args.check_reexport_facades,
        header="re-export-facade check failed for {count} site(s) (no baseline -- any hit fails)",
        clean_note="No re-export-facade hits found.",
        run=_reexport_facade_outcome,
        hard_zero=True,
        update_header=(
            "Error: re-export-facade check failed for {count} site(s) -- there is no "
            "baseline to update; fix the code instead:\n"
        ),
    ),
)


# ---------------------------------------------------------------------------
# Baseline updates
# ---------------------------------------------------------------------------


def _update_provider_conditional_baseline(ctx: _ScanContext) -> None:
    path = ctx.config_path(_PROVIDER_CONDITIONAL_BASELINE)
    hits = scan_provider_conditionals(ctx.packages, ctx.root, ctx.taxonomy.language_packages)
    counts = ctx.file_counts(hits)
    write_provider_conditional_baseline(path, counts)
    _report_update(ctx, "I6 provider-conditional", len(counts), "file(s)", path)


def _update_function_level_import_baseline(ctx: _ScanContext) -> None:
    """Lower the decrease-only baseline to the live counts; refuse to raise any count."""
    path = ctx.config_path(_FUNCTION_LEVEL_IMPORT_BASELINE)
    frozen = _function_level_baseline(
        ctx,
        "The baseline is decrease-only: --update-baseline lowers an existing record and "
        "never creates one. Restore the file from version control.",
    )
    hits = scan_function_level_imports(ctx.packages, ctx.root, frozenset(frozen.counts))
    counts = ctx.file_counts(hits)
    increases = check_function_level_import_ratchet(counts, frozen.counts)
    if increases:
        _print_block(
            f"Error: refusing to raise the function-level-import baseline -- "
            f"{len(increases)} file(s) are above it. The ratchet is "
            f"decrease-only: promote the new deferred imports to module top, or "
            f"record a cycle-forced deferral by hand with its reason:\n",
            increases,
        )
        raise _UpdateRefused
    lowered, dropped = lowered_function_level_import_baseline(frozen, counts)
    write_function_level_import_baseline(path, lowered.counts, lowered.reasons)
    for file_rel in dropped:
        print(
            f"Dropped function-level-import baseline entry {file_rel}: it has no "
            f"function-level import left.",
            file=sys.stderr,
        )
    _report_update(
        ctx,
        "function-level-import",
        len(lowered.counts),
        "file(s)",
        path,
        f" ({len(dropped)} dropped, none raised)",
    )


def _update_shared_vocabulary_baseline(ctx: _ScanContext) -> None:
    path = ctx.config_path(_SHARED_VOCABULARY_BASELINE)
    hits = scan_shared_vocabulary(ctx.packages, ctx.root, ctx.taxonomy.language_packages)
    counts = ctx.file_counts(hits)
    write_shared_vocabulary_baseline(path, counts)
    _report_update(ctx, "G1 shared-vocabulary", len(counts), "file(s)", path)


def _update_shared_target_name_baseline(ctx: _ScanContext) -> None:
    """Recompute the counts, carrying every written reason across the regeneration."""
    path = ctx.config_path(_SHARED_TARGET_NAME_BASELINE)
    counts = ctx.file_counts(scan_shared_target_names(ctx.packages, ctx.root))
    previous = _previous_reasons(path)
    write_shared_target_name_baseline(path, counts, previous)
    _warn_vanished_reasons(
        previous,
        counts,
        "Warning: G2 baseline entry {entry} carried a reason but has "
        "no shared-target-name hit any more; its entry and reason were "
        "dropped. Expected only when the identifier was deliberately "
        "renamed or removed -- if it still exists, the scanner no longer "
        "sees it.",
    )
    _report_update(
        ctx,
        "G2 shared-target-name",
        len(counts),
        "file(s)",
        path,
        f" ({len(previous.keys() & counts.keys())} carrying a reason)",
    )


def _update_cross_package_vocabulary_baseline(ctx: _ScanContext) -> None:
    """Recompute the counts, carrying every written D9 reason across the regeneration."""
    path = ctx.config_path(_CROSS_PACKAGE_VOCABULARY_BASELINE)
    counts = ctx.file_counts(scan_cross_package_vocabulary(ctx.packages, ctx.root))
    previous = _previous_reasons(path)
    write_cross_package_vocabulary_baseline(path, counts, previous)
    _warn_vanished_reasons(
        previous,
        counts,
        "Warning: G3 baseline entry {entry} carried a D9 reason but "
        "has no cross-package hit any more; its entry and reason were "
        "dropped. Expected only when that declaration was deliberately "
        "removed -- if it still exists, the scanner no longer sees it.",
    )
    _report_update(
        ctx,
        "G3 cross-package-vocabulary",
        len(counts),
        "file(s)",
        path,
        f" ({len(previous.keys() & counts.keys())} carrying a D9 reason)",
    )


def _update_own_target_name_baseline(ctx: _ScanContext) -> None:
    path = ctx.config_path(_OWN_TARGET_NAME_BASELINE)
    counts = _own_target_name_counts(ctx)
    write_own_target_name_baseline(path, counts)
    _report_update(ctx, "I4 own-target-name", len(counts), "package(s)", path)


def _update_target_literal_baseline(ctx: _ScanContext) -> None:
    path = ctx.config_path(_TARGET_LITERAL_BASELINE)
    hits = scan_target_literals(ctx.packages, ctx.root, ctx.shared_packages)
    counts = ctx.file_counts(hits)
    write_target_literal_baseline(path, counts)
    _report_update(ctx, "I1 target-literal", len(counts), "file(s)", path)


#: The baselines an ``--update-baseline`` run rewrites, each when its flag is passed.
_UPDATES: tuple[_Update, ...] = (
    _Update(lambda args: args.check_provider_conditionals, _update_provider_conditional_baseline),
    _Update(lambda args: args.check_function_level_imports, _update_function_level_import_baseline),
    _Update(lambda args: args.check_shared_vocabulary, _update_shared_vocabulary_baseline),
    _Update(lambda args: args.check_shared_target_names, _update_shared_target_name_baseline),
    _Update(
        lambda args: args.check_cross_package_vocabulary,
        _update_cross_package_vocabulary_baseline,
    ),
    _Update(lambda args: args.check_own_target_names, _update_own_target_name_baseline),
)


def _updates_target_literals(args: argparse.Namespace) -> bool:
    """The target-literal baseline updates when asked, and when no other check was asked.

    The re-export-facade check has no baseline, so requesting it alone must not fall through
    to the target-literal default and overwrite an unrelated baseline.
    """
    other_check_requested = args.check_reexport_facades or any(
        update.enabled(args) for update in _UPDATES
    )
    return args.check_target_literals or not other_check_requested


def _update_baselines(args: argparse.Namespace, ctx: _ScanContext) -> bool:
    """Rewrite every requested baseline; True iff one was written."""
    requested = [update for update in _UPDATES if update.enabled(args)]
    for update in requested:
        update.run(ctx)
    if _updates_target_literals(args):
        _update_target_literal_baseline(ctx)
        return True
    return bool(requested)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _report_findings(
    args: argparse.Namespace,
    ctx: _ScanContext,
    violations: list[Violation],
    failed: list[tuple[_Check, _Outcome]],
) -> int:
    """Print the boundary violations and every failed check's messages; return the exit code."""
    mode = "Warning" if args.warn else "Error"
    if violations:
        print(f"{mode}: Found {len(violations)} import boundary violations:\n")
        for violation in violations:
            print(format_violation(violation, ctx.root))
            print()
    for check, outcome in failed:
        header = check.header.format(count=len(outcome.messages))
        _print_block(f"{mode}: {header}:\n", outcome.messages)
    return EXIT_PASS if args.warn else EXIT_VIOLATION


def _report_clean(args: argparse.Namespace, results: list[tuple[_Check, _Outcome]]) -> int:
    """Print each check's clean summary (and, verbose, its clean note); return the exit code."""
    for _, outcome in results:
        for line in outcome.clean_lines:
            print(line)
    if args.verbose:
        print("No import boundary violations found.", file=sys.stderr)
        for check, _ in results:
            if check.clean_note:
                print(check.clean_note, file=sys.stderr)
    return EXIT_PASS


def _report(
    args: argparse.Namespace,
    ctx: _ScanContext,
    violations: list[Violation],
    results: list[tuple[_Check, _Outcome]],
) -> int:
    """Print the findings (or the clean summary) and return the exit code."""
    for _, outcome in results:
        for line in outcome.preamble:
            print(line)
    failed = [(check, outcome) for check, outcome in results if outcome.messages]
    if violations or failed:
        return _report_findings(args, ctx, violations, failed)
    return _report_clean(args, results)


def _run(args: argparse.Namespace) -> int:
    ctx = _scan_context(args)
    if args.verbose:
        _print_discovery(ctx)
    violations = _boundary_violations(ctx)
    enabled = [check for check in _CHECKS if check.enabled(args)]
    # A hard-zero check has nothing to baseline: it runs before any update, so a real hit
    # fails even an --update-baseline run requested for a different flag.
    outcomes = {check: check.run(ctx) for check in enabled if check.hard_zero}
    if args.update_baseline:
        updated = _update_baselines(args, ctx)
        refused = [check for check in enabled if check.hard_zero and outcomes[check].messages]
        if refused:
            messages = outcomes[refused[0]].messages
            _print_block(refused[0].update_header.format(count=len(messages)), messages)
            return EXIT_VIOLATION
        if updated:
            return EXIT_PASS
    results = [(check, outcomes[check] if check.hard_zero else check.run(ctx)) for check in enabled]
    return _report(args, ctx, violations, results)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-package import boundary scanner for Datrix monorepo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-w",
        "--warn",
        action="store_true",
        help="Warning mode: report violations but exit 0",
    )
    parser.add_argument(
        "-b",
        "--base-dir",
        type=Path,
        help="Monorepo root directory (default: auto-detect)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each file being scanned",
    )
    parser.add_argument(
        "--check-target-literals",
        action="store_true",
        help=(
            "Run the I1 target-literal ratchet check (invariant I1) "
            "in addition to the import-boundary check"
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Recompute current per-file counts and overwrite the frozen baseline(s), "
            "then exit 0. Updates target-literal-baseline.toml unless "
            "--check-provider-conditionals is passed (without --check-target-literals), "
            "in which case it updates provider-conditional-baseline.toml instead. "
            "Pass both --check-target-literals and --check-provider-conditionals to "
            "update both baselines in one run."
        ),
    )
    parser.add_argument(
        "--check-provider-conditionals",
        action="store_true",
        help=(
            "Run the I6 successor ratchet check (invariant I6, DI-4/DI-5) -- both the "
            "ProviderId-shaped pattern and the plain-string-literal pattern -- "
            "in addition to the import-boundary check"
        ),
    )
    parser.add_argument(
        "--check-function-level-imports",
        action="store_true",
        help=(
            "Run the function-level-import ratchet check "
            "in addition to the import-boundary check. Scoped to "
            "datrix-common's src/ tree only."
        ),
    )
    parser.add_argument(
        "--check-shared-vocabulary",
        action="store_true",
        help=(
            "Run the G1 shared-vocabulary ratchet check (Decision D3, "
            "Invariant I2) in addition to the import-boundary check. Fails "
            "when a datrix-codegen-{lang} module declares a module-level "
            "frozenset/set/dict whose normalized member set duplicates a "
            "vocabulary already declared in datrix_codegen_kernel.enums."
        ),
    )
    parser.add_argument(
        "--check-shared-target-names",
        action="store_true",
        help=(
            "Run the G2 shared-layer target-name ratchet check (Decision D4, "
            "Invariant I3) in addition to the import-boundary check. Fails "
            "when a class, function, dataclass field, type alias, or type "
            "reference declared in datrix_codegen_common carries a "
            "registered LANGUAGE name (datrix.languages only, never "
            "datrix.platforms) as an identifier segment."
        ),
    )
    parser.add_argument(
        "--check-cross-package-vocabulary",
        action="store_true",
        help=(
            "Run the G3 cross-package vocabulary ratchet check (Decision "
            "D2.1-D2.4) in addition to the import-boundary check. Fails "
            "when a module-level set/frozenset/dict/tuple literal's "
            "normalized member set is declared, with a bare string "
            "literal, identically in two or more datrix-* packages -- "
            "every discovered package, not only the language "
            "packages G1 scans -- independent of whether either copy "
            "also duplicates a datrix_codegen_kernel.enums vocabulary."
        ),
    )
    parser.add_argument(
        "--check-own-target-names",
        action="store_true",
        help=(
            "Run the I4 own-target-name ratchet check (Decision D5, "
            "Invariant I4) in addition to the import-boundary check. "
            "Fails when a function or method DEFINED in a registered "
            "datrix.languages package carries THAT SAME package's own "
            "registered language id or declared alias "
            "(declaration_for_language(lang).name_tokens) as an identifier "
            "segment -- a name-keyed behaviour-parity scan cannot see a "
            "parallel implementation hiding behind its own language's name "
            "in the function name."
        ),
    )
    parser.add_argument(
        "--check-reexport-facades",
        action="store_true",
        help=(
            "Run the re-export-facade check in addition to the "
            "import-boundary check. Fails when a name has a second import "
            "path through a facade: a module that passes through a name it "
            "does not itself define via its own __all__ or a self-aliased "
            "import (provider side); a from-M-import-N anywhere that "
            "reaches through such a facade instead of the module that "
            "actually defines N (consumer side); a pyproject.toml entry "
            "point naming an attribute its target module does not define; "
            "or an import whose module resolves to nothing on disk at all. "
            "Hard zero, no baseline: any hit fails, and --update-baseline "
            "has no effect on this check."
        ),
    )
    parser.add_argument(
        "--facade-module",
        action="append",
        default=[],
        metavar="MODULE",
        help=(
            "With --check-reexport-facades --verbose, narrow the printed "
            "per-site worklist to hits attributed to this providing module "
            "(dotted module path, or its relative file path). Repeatable."
        ),
    )
    parser.add_argument(
        "--consumer-package",
        action="append",
        default=[],
        metavar="REPO",
        help=(
            "With --check-reexport-facades --verbose, narrow the printed "
            "per-site worklist to hits whose site lives under this repo "
            "directory name (e.g. datrix-codegen-python). Repeatable."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run the self-test suite (rule-model, AST-scanner, and ratchet "
            "invariants, including a real mutation-based CLI non-vacuity proof) "
            "and exit -- does not run the import-boundary scan itself. The "
            "self-test also runs automatically as step 1 of every OTHER "
            "invocation of this script; pass this flag to run only the self-test."
        ),
    )
    parser.add_argument(
        "--skip-auto-self-test",
        action="store_true",
        help=argparse.SUPPRESS,  # internal: used only by the self-test's own nested CLI call
    )
    return parser


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = violations found, 2 = error)
    """
    args = _argument_parser().parse_args()
    if args.skip_auto_self_test and args.self_test:
        print(
            "Error: --self-test and --skip-auto-self-test are mutually exclusive.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.self_test:
        return EXIT_PASS if run_self_test() else EXIT_VIOLATION
    if not args.skip_auto_self_test and not run_self_test():
        print(_UNTRUSTED_CHECKER, file=sys.stderr)
        return EXIT_VIOLATION
    try:
        return _run(args)
    except _ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except _UpdateRefused:
        return EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main())
