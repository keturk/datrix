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
for a genDSL `<namespace>.<module>.<name>` reference (read from the
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
import ast
import enum
import functools
import importlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_common.config.datasource.identity_config import (
    IdentityProvider as ConfigIdentityProvider,
)
from datrix_common.plugin.capability_resolution import (
    declaration_for_language,
)

from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.registered_targets import (
    AXIS_LANGUAGES,
    entry_point_module_roots,
    owned_identity_provider_type_names,
    registered_language_names,
    registered_platform_names,
)
from datrix_scripts.target_literal_positions import (
    target_name_literal_hits,
)


@dataclass(frozen=True)
class BoundaryRule:
    """Per-package boundary rule: forbidden prefixes plus subtree carve-outs.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of ``allowed_subtrees`` -- used where a package may reach
    a narrow, reviewed part of an otherwise-forbidden package (the test
    harness's kernel import).
    """

    forbidden_prefixes: tuple[str, ...]
    allowed_subtrees: frozenset[str] = frozenset()


# Language-core packages: a package holding one language's transpiler core,
# language profile and web-client mechanics, split out of that language's
# backend generator so a frontend target emitting the same file language can
# depend on it without depending on the backend. It registers no entry point
# (it is a library, not a plugin), so the taxonomy cannot discover its role;
# each one is named here with the language package it serves.
#
# The language it serves and every frontend target emitting that language may
# import it; every other language (and that language's own core) is a sibling
# it may not reach, and the platform, SQL, component and extension packages --
# forbidden the language layer -- are forbidden it too.
LANGUAGE_CORE_PACKAGES: dict[str, str] = {
    "datrix_codegen_typescript_core": "datrix_codegen_typescript",
}

# ---------------------------------------------------------------------------
# Generator taxonomy -- DISCOVERED from the manifests on disk, never declared.
#
# Datrix is a multi-language, multi-platform generator: these sets grow. A
# package's ROLE cannot be inferred from its name (datrix_codegen_sql and
# datrix_codegen_component are neither language nor platform generators), and a
# hand-written list of roles is exactly the closed-world inventory the parity
# program forbids ("gate inventories are derived from registration, never
# hand-authored lists"). The role IS registration: a package is a language
# generator iff its pyproject.toml registers a ``datrix.languages`` entry point
# and a platform generator iff it registers ``datrix.platforms`` -- the same
# groups PluginRegistry resolves at runtime -- so the scanner reads every
# ``datrix-*/pyproject.toml`` under the monorepo root and classifies from that.
# No installed environment is needed, and a package is classified, and guarded,
# from the commit that registers its entry point.
#
# Every boundary rule below is DERIVED from the discovered taxonomy
# (build_boundary_rules). Two fail-loud conditions replace the old "absent from
# the list, silently unguarded" hole: a package registering BOTH groups is
# rejected (rules are per class), and main() refuses to scan while any
# discovered package has no rule at all -- a generator that registers neither
# group (SQL, Component, and the Angular and Flutter client targets
# today) must carry an explicit entry.
LANGUAGES_ENTRY_POINT_GROUP = "datrix.languages"
PLATFORMS_ENTRY_POINT_GROUP = "datrix.platforms"
GENERATORS_ENTRY_POINT_GROUP = "datrix.generators"
EXTENSIONS_ENTRY_POINT_GROUP = "datrix.extensions"

# The four entry-point groups PluginRegistry resolves at runtime
# (datrix_common.plugin.registry: GENERATOR_GROUP, PLATFORM_GROUP,
# EXTENSION_GROUP, LANGUAGES_GROUP). A package registering ANY of these is a
# generator/extension/target package, not a shared layer; a package
# registering NONE of them is shared.
SHARED_PACKAGE_CLASSIFIER_GROUPS: frozenset[str] = frozenset(
    {
        LANGUAGES_ENTRY_POINT_GROUP,
        PLATFORMS_ENTRY_POINT_GROUP,
        GENERATORS_ENTRY_POINT_GROUP,
        EXTENSIONS_ENTRY_POINT_GROUP,
    }
)

# GenDSL's own entry-point-group axis -- a SEPARATE, cross-cutting
# registration mechanism from the four taxonomy groups above (mirrors
# datrix_common.plugin.registry's GENDSL_FILE_LANGUAGES_GROUP/
# GENDSL_ITERATION_TARGETS_GROUP/GENDSL_CONTEXT_NAMESPACES_GROUP, plus
# datrix_codegen_kernel.gendsl.target_registry's
# GENDSL_GENERATOR_TARGETS_GROUP -- read for the canonical spellings only,
# same as the four taxonomy groups; this scanner does not import either
# module). Confirmed against the real manifests (not assumed): every
# language, every platform, the frontend targets, SQL, AND the shared
# packages datrix-codegen-kernel and datrix-codegen-common register into this
# axis, so its presence carries NO taxonomy signal -- folding it into
# SHARED_PACKAGE_CLASSIFIER_GROUPS would misclassify every one of those as
# shared, and treating it as "unrecognized" would make
# discover_shared_packages abort on the shared packages themselves.
_GENDSL_AUXILIARY_ENTRY_POINT_GROUPS: frozenset[str] = frozenset(
    {
        "datrix.gendsl_file_languages",
        "datrix.gendsl_iteration_targets",
        "datrix.gendsl_context_namespaces",
        "datrix.gendsl_generator_targets",
    }
)


class GeneratorTaxonomyError(ValueError):
    """A manifest cannot be classified (unparseable, or in both classes)."""


@dataclass(frozen=True)
class GeneratorTaxonomy:
    """The language and platform generator packages a monorepo declares.

    Both tuples hold IMPORT package names (``datrix_codegen_python``), sorted,
    derived from each entry point's object reference
    (``datrix_codegen_python.language_plugin:PythonLanguagePlugin`` ->
    ``datrix_codegen_python``); a distribution registering several entries in
    one group (docker's ``docker`` + ``local``, azure's ``azure`` +
    ``azure-vm``) folds into one package.
    """

    language_packages: tuple[str, ...]
    platform_packages: tuple[str, ...]


def _entry_point_import_roots(entry_points: object, manifest: Path, group: str) -> set[str]:
    """The import-package roots named by one entry-point group's values."""
    if not isinstance(entry_points, dict):
        raise GeneratorTaxonomyError(
            f"{manifest}: [project.entry-points.\"{group}\"] must be a table of "
            f"name = \"module:attr\" entries, got {type(entry_points).__name__}."
        )
    roots: set[str] = set()
    for entry_name, reference in entry_points.items():
        if not isinstance(reference, str) or not reference:
            raise GeneratorTaxonomyError(
                f"{manifest}: entry point {group}.{entry_name} must be a non-empty "
                f"\"module:attr\" string, got {reference!r}."
            )
        module_path = reference.split(":", 1)[0].strip()
        root = module_path.split(".", 1)[0]
        if not root:
            raise GeneratorTaxonomyError(
                f"{manifest}: entry point {group}.{entry_name} = {reference!r} names "
                f"no module; expected \"package.module:Attribute\"."
            )
        roots.add(root)
    return roots


def discover_generator_taxonomy(base_dir: Path) -> GeneratorTaxonomy:
    """Classify every ``datrix-*`` package under *base_dir* from its manifest.

    Args:
        base_dir: Monorepo root holding the ``datrix-*`` package directories.

    Returns:
        The discovered taxonomy. A directory with no ``pyproject.toml`` (the
        VS Code client, the showcase repo) contributes nothing.

    Raises:
        GeneratorTaxonomyError: If a manifest is unparseable, an entry-point
            value is malformed, or one package registers BOTH groups.
    """
    languages: set[str] = set()
    platforms: set[str] = set()
    for candidate in sorted(base_dir.iterdir()):
        manifest = candidate / "pyproject.toml"
        if not candidate.is_dir() or not candidate.name.startswith("datrix-"):
            continue
        if not manifest.is_file():
            continue
        try:
            with manifest.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as e:
            raise GeneratorTaxonomyError(f"{manifest}: cannot parse manifest: {e}") from e
        project = data.get("project")
        groups = project.get("entry-points", {}) if isinstance(project, dict) else {}
        if not isinstance(groups, dict):
            raise GeneratorTaxonomyError(
                f"{manifest}: [project.entry-points] must be a table, got "
                f"{type(groups).__name__}."
            )
        if LANGUAGES_ENTRY_POINT_GROUP in groups:
            languages |= _entry_point_import_roots(
                groups[LANGUAGES_ENTRY_POINT_GROUP], manifest, LANGUAGES_ENTRY_POINT_GROUP
            )
        if PLATFORMS_ENTRY_POINT_GROUP in groups:
            platforms |= _entry_point_import_roots(
                groups[PLATFORMS_ENTRY_POINT_GROUP], manifest, PLATFORMS_ENTRY_POINT_GROUP
            )
    both = sorted(languages & platforms)
    if both:
        raise GeneratorTaxonomyError(
            f"Package(s) {both} register BOTH {LANGUAGES_ENTRY_POINT_GROUP!r} and "
            f"{PLATFORMS_ENTRY_POINT_GROUP!r} entry points. The boundary rules are "
            f"per class (a language forbids sibling languages; a platform forbids "
            f"sibling platforms and language packages), so one package cannot be "
            f"both. Fix: split the package, one class per distribution."
        )
    return GeneratorTaxonomy(
        language_packages=tuple(sorted(languages)),
        platform_packages=tuple(sorted(platforms)),
    )


def discover_shared_packages(
    base_dir: Path, packages: dict[str, PackageInfo]
) -> tuple[str, ...]:
    """Derive the shared-package set: every discovered ``datrix-*`` package
    whose manifest registers NONE of the four target-taxonomy entry-point
    groups (``datrix.languages``/``datrix.platforms``/``datrix.generators``/
    ``datrix.extensions``). Deriving the set means a new shared package is
    scanned the moment it exists, with no hand-kept list to update.

    Classification walks every ``datrix-*/pyproject.toml`` directly (the same
    directory walk ``discover_generator_taxonomy`` uses), independent of
    whether the package has a ``src/`` tree yet, so the fail-loud
    unclassifiable check (below) fires even for a manifest-only package with
    nothing to scan. The RETURNED set, however, is intersected against
    *packages* (as returned by ``discover_packages``, which already resolves
    each distribution directory's real import-package name from its ``src/``
    subdirectory) -- a package with no ``src/`` tree yet contributes no files
    to scan, so it is correctly classified but not returned (mirrors the
    existing "a package with no src/ tree yet contributes no files and no
    baseline entries" note for language packages).

    A package with an EMPTY [project.entry-points] table (or none at all) is
    shared. A package registering at least one of the four known groups is a
    generator/platform/language/extension package, never shared.

    A package can ALSO register entry-point groups that carry no taxonomy
    signal at all and must never affect this classification:

    * A group outside the ``datrix.`` namespace entirely (e.g. pytest's own
      ``pytest11`` plugin-discovery group -- ``datrix-common`` registers its
      feature-tag pytest plugin this way, alongside zero taxonomy groups) is
      a third-party mechanism, not a Datrix plugin-kind signal, and is
      ignored unconditionally.
    * GenDSL's own cross-cutting registration axis
      (``_GENDSL_AUXILIARY_ENTRY_POINT_GROUPS`` -- ``datrix_common.plugin.registry``'s
      ``GENDSL_FILE_LANGUAGES_GROUP``/``GENDSL_ITERATION_TARGETS_GROUP``/
      ``GENDSL_CONTEXT_NAMESPACES_GROUP``, plus
      ``datrix_codegen_kernel.gendsl.target_registry.GENDSL_GENERATOR_TARGETS_GROUP``)
      is registered by packages spanning EVERY taxonomy class alike --
      the shared ``datrix-codegen-kernel`` and ``datrix-codegen-common``,
      every language, every platform, the frontend targets, and SQL all
      register into it, so its presence says nothing about which of the four
      taxonomy groups a package belongs to (or doesn't). Confirmed against the
      real monorepo manifests, not assumed: ``datrix-codegen-kernel``
      registers ONLY ``gendsl_file_languages``/``gendsl_iteration_targets``
      and ``datrix-codegen-common`` ONLY ``gendsl_iteration_targets``; both
      are shared packages.

    A package registering a NON-EMPTY [project.entry-points] table whose
    ``datrix.``-namespaced group name(s) are ALL outside the four known
    taxonomy groups AND outside the known GenDSL auxiliary axis is
    UNCLASSIFIABLE: folding it into "shared" would silently widen ratchet
    scope to a package that is plausibly a not-yet-recognized plugin kind,
    and excluding it would silently leave a real generator unpoliced by
    either the shared ratchets or the boundary-rule taxonomy -- so the scan
    aborts instead, naming the package and its unrecognized group(s).

    Args:
        base_dir: Monorepo root holding the ``datrix-*`` package directories.
        packages: Package name -> PackageInfo, as returned by
            ``discover_packages(base_dir)`` -- supplies the accurate import
            root for each distribution directory that has a ``src/`` tree.

    Returns:
        Import package names (``datrix_common``, not ``datrix-common``) that
        are both classified shared AND present in *packages*, sorted.

    Raises:
        GeneratorTaxonomyError: If a manifest is unparseable (propagated from
            the same per-manifest parsing ``discover_generator_taxonomy``
            uses), or a manifest registers a ``datrix.``-namespaced
            entry-point group outside both the four taxonomy groups and the
            known GenDSL auxiliary axis.
    """
    root_by_dir: dict[Path, str] = {info.root: name for name, info in packages.items()}
    shared: set[str] = set()
    for candidate in sorted(base_dir.iterdir()):
        manifest = candidate / "pyproject.toml"
        if not candidate.is_dir() or not candidate.name.startswith("datrix-"):
            continue
        if not manifest.is_file():
            continue
        try:
            with manifest.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as e:
            raise GeneratorTaxonomyError(f"{manifest}: cannot parse manifest: {e}") from e
        project = data.get("project")
        groups = project.get("entry-points", {}) if isinstance(project, dict) else {}
        if not isinstance(groups, dict):
            raise GeneratorTaxonomyError(
                f"{manifest}: [project.entry-points] must be a table, got "
                f"{type(groups).__name__}."
            )
        if set(groups) & SHARED_PACKAGE_CLASSIFIER_GROUPS:
            continue  # a real generator/platform/language/extension package
        unrecognized_datrix_groups = {
            group
            for group in groups
            if group.startswith("datrix.")
            and group not in _GENDSL_AUXILIARY_ENTRY_POINT_GROUPS
        }
        if unrecognized_datrix_groups:
            raise GeneratorTaxonomyError(
                f"{manifest}: registers entry-point group(s) "
                f"{sorted(unrecognized_datrix_groups)}, none of which is "
                f"{sorted(SHARED_PACKAGE_CLASSIFIER_GROUPS)} (the four taxonomy "
                f"groups) or {sorted(_GENDSL_AUXILIARY_ENTRY_POINT_GROUPS)} "
                f"(GenDSL's own non-taxonomy registration axis). This package "
                f"cannot be classified as shared or as a taxonomy member -- add an "
                f"explicit classification before the I1/I6 shared-layer ratchets "
                f"can be trusted to scan (or skip) it."
            )
        import_root = root_by_dir.get(candidate)
        if import_root is not None:
            shared.add(import_root)
    return tuple(sorted(shared))


def _siblings(package: str, group: tuple[str, ...]) -> tuple[str, ...]:
    """Every member of ``group`` except ``package`` itself."""
    return tuple(name for name in group if name != package)


def build_boundary_rules(taxonomy: GeneratorTaxonomy) -> dict[str, BoundaryRule]:
    """Boundary rules: source package -> BoundaryRule, derived from *taxonomy*.

    forbidden_prefixes: imports whose prefix matches are forbidden.
    allowed_subtrees: specific sub-prefixes that override the broader forbidden prefix.
    """
    language_packages = taxonomy.language_packages
    platform_packages = taxonomy.platform_packages
    language_cores = tuple(sorted(LANGUAGE_CORE_PACKAGES))
    return {
        "datrix_common": BoundaryRule(
            forbidden_prefixes=(
                "datrix_language",
                "datrix_cli",
                "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
                "datrix_extensions",
                # datrix-migration depends on the core; the core names its
                # run-scoped state transaction through a Protocol instead.
                "datrix_migration",
                # datrix-semantic depends on the core; a fact both the core's
                # consumers and a semantic phase read lives in the core.
                "datrix_semantic",
            ),
        ),
        "datrix_language": BoundaryRule(
            forbidden_prefixes=(
                "datrix_cli",
                "datrix_codegen_",  # Wildcard
            ),
        ),
        "datrix_codegen_common": BoundaryRule(
            forbidden_prefixes=(
                *language_packages, *language_cores, *platform_packages, "datrix_cli",
            ),
        ),
        # Language generators: each forbids every SIBLING language package, and every
        # language-core package that serves a sibling. They share code through
        # datrix-codegen-common, never through direct imports -- importing a sibling
        # re-introduces the O(N^2) coupling the shared layer exists to prevent (see
        # "Cross-language parity is verified by per-language conformance, never by
        # comparison" in datrix-common/docs/architecture/import-boundaries.md).
        **{
            language: BoundaryRule(
                forbidden_prefixes=(
                    *_siblings(language, language_packages),
                    *(
                        core
                        for core in language_cores
                        if LANGUAGE_CORE_PACKAGES[core] != language
                    ),
                )
            )
            for language in language_packages
        },
        # Language-core packages sit below the backend language generator they
        # serve and every frontend target emitting that language: an import of any
        # of them -- or of any other generator, the parser, the semantic layer, the
        # CLI or the extension packs -- would put a consumer back underneath its own
        # dependency. Each package's own import-linter contract enforces the same
        # fence on src/ with TYPE_CHECKING imports counted.
        **{
            core: BoundaryRule(
                forbidden_prefixes=(
                    *language_packages,
                    *_siblings(core, language_cores),
                    *platform_packages,
                    "datrix_codegen_sql",
                    "datrix_codegen_component",
                    "datrix_codegen_angular",
                    "datrix_codegen_flutter",
                    "datrix_language",
                    "datrix_semantic",
                    "datrix_cli",
                    "datrix_extensions",
                ),
            )
            for core in language_cores
        },
        # SQL generator: forbidden from every language package, from the whole of
        # datrix_codegen_common, and from datrix_cli. SQL is a schema/DDL generator, not a
        # language generator: every target-neutral fact it consumes (the GenDSL engine,
        # the migration adapter protocol and chain model, the parity declaration types,
        # the pure-SQL index facts) lives in datrix_codegen_kernel, which it depends on
        # instead. Its tests use the target-neutral conformance kit in datrix_testing --
        # datrix_codegen_common is forbidden identically in src/ and tests/, with no
        # test-only exception.
        "datrix_codegen_sql": BoundaryRule(
            forbidden_prefixes=(
                *language_packages,
                *language_cores,
                "datrix_codegen_common",
                "datrix_cli",
            ),
        ),
        # Component generator: forbidden from every language package, from the whole of
        # datrix_codegen_common, and from datrix_cli. Component is a language-agnostic
        # scaffolding generator: the GenDSL engine, the serverless plan and the NoSQL
        # collection facts it consumes live in datrix_codegen_kernel, which it depends
        # on instead. Its tests use the target-neutral conformance kit in datrix_testing --
        # datrix_codegen_common is forbidden identically in src/ and tests/, with no
        # test-only exception.
        "datrix_codegen_component": BoundaryRule(
            forbidden_prefixes=(
                *language_packages, *language_cores, "datrix_codegen_common", "datrix_cli",
            ),
        ),
        # Client-target generators: forbidden from every backend language generator, from every
        # other client target, and from datrix_cli -- a frontend client target is not a language
        # generator, but (like Component and Flutter) it legitimately imports
        # datrix_codegen_common freely (the shared client contract builder, the transpiler it
        # renders DSL bodies with), so datrix_codegen_common is NOT on its forbidden list. The
        # web target (Angular) renders TypeScript through datrix_codegen_typescript_core, a
        # language-core library that registers no entry point, so it is not a language package
        # and needs no carved-out allowed_subtrees -- the backend TypeScript generator stays
        # forbidden whole. Flutter emits Dart, so every language core is forbidden to it. Without
        # these entries the scanner would have NO rule for these packages at all, which main()
        # refuses to run with -- silently unguarded is not a state this gate allows.
        "datrix_codegen_angular": BoundaryRule(
            forbidden_prefixes=(
                *language_packages, "datrix_codegen_flutter", "datrix_cli",
            ),
        ),
        "datrix_codegen_flutter": BoundaryRule(
            forbidden_prefixes=(
                *language_packages, *language_cores, "datrix_codegen_angular", "datrix_cli",
            ),
        ),
        # Platform generators are forbidden the whole of datrix_codegen_common: every
        # target-neutral service they consume (the GenDSL engine, the provider library,
        # pooling, secrets, seed planning, dashboards, the serverless and replayable-
        # ingestion plans, the shared enums) lives in datrix_codegen_kernel, which they
        # depend on instead. Their tests use the target-neutral conformance kit in
        # datrix_testing -- datrix_codegen_common is forbidden identically in src/ and
        # tests/, with no test-only exception.
        #
        # SIBLING PLATFORM PLUGINS ARE FORBIDDEN TOO. Each platform
        # forbids every OTHER platform. This edge was once missing from every
        # platform's rule -- not because it was permitted, but because nobody had
        # written it, so a silent checker was mistaken for an approving one. A platform
        # plugin importing a sibling platform plugin (e.g. aws importing docker to
        # reuse the base-image tag algorithm) means the importing platform can no
        # longer be installed without the imported one, and would grow into a
        # three-way coupling the moment a second platform needed the same code.
        # The correct home for anything two platforms share is the generation
        # kernel (datrix_codegen_kernel): shared layers ask, target plugins answer
        # (design principle 16; CLAUDE.md's generality-preserving design rule).
        **{
            platform: BoundaryRule(
                forbidden_prefixes=(
                    "datrix_codegen_common",
                    *language_packages,
                    *language_cores,
                    *_siblings(platform, platform_packages),
                    "datrix_cli",
                ),
            )
            for platform in platform_packages
        },
        "datrix_extensions": BoundaryRule(
            forbidden_prefixes=(
                "datrix_cli",
                *language_packages,
                *language_cores,
                "datrix_codegen_common",
                *platform_packages,
                "datrix_language",
            ),
        ),
        # The shared test harness sits on the foundation alone: every other
        # package lists it as a dev dependency, so an import of any of them
        # would close a cycle through that package's dev install. Parser
        # implementations reach it only through the calling test session's
        # registration (datrix_testing.parsing.register_test_parser), never
        # through an import.
        #
        # The one generation package it may import is the kernel: its assertion,
        # I/O, pipeline and determinism helpers build and compare the kernel's
        # GeneratedFile/Generator values. The kernel takes datrix-testing only
        # as a dev extra, so that edge closes no runtime cycle.
        "datrix_testing": BoundaryRule(
            forbidden_prefixes=(
                "datrix_language",
                "datrix_cli",
                "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
                "datrix_extensions",
            ),
            allowed_subtrees=frozenset({"datrix_codegen_kernel"}),
        ),
        # The generation kernel (generator base classes, template engine,
        # discovery, the shared route and runtime derivations, the GenDSL data
        # model, the Seed datasets) sits on the core alone. Every language,
        # platform and frontend generator, the language layer and the CLI
        # depend on it, so an import of any of them -- or of the parser or the
        # semantic layer -- would put that package back in every platform's
        # dependency path. Its own import-linter contract enforces the same
        # fence on src/ with TYPE_CHECKING imports counted.
        "datrix_codegen_kernel": BoundaryRule(
            forbidden_prefixes=(
                "datrix_codegen_",  # Wildcard: every other datrix_codegen_* package
                "datrix_language",
                "datrix_semantic",
                "datrix_cli",
                "datrix_extensions",
            ),
        ),
        # The migration package (schema snapshot, diff, change policy, revision
        # ledger, state store) sits on the core alone. Every generator, the
        # codegen layer and the CLI consume it, so an import of any of them --
        # or of the semantic layer above the core -- would close a cycle. Its
        # tests reach the parser only through the root conftest's registration.
        "datrix_migration": BoundaryRule(
            forbidden_prefixes=(
                "datrix_language",
                "datrix_cli",
                "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
                "datrix_extensions",
                "datrix_semantic",
            ),
        ),
        # The semantic-analysis package (the analyzer, every domain validator,
        # auth-contract lowering) sits on the core alone. The parser, the CLI
        # and the test harness depend on it, and every generator and the
        # migration package sit beside it on the core, so an import of any of
        # them would close a cycle or couple two siblings. Its tests reach the
        # parser only through the root conftest's registration.
        "datrix_semantic": BoundaryRule(
            forbidden_prefixes=(
                "datrix_language",
                "datrix_cli",
                "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
                "datrix_extensions",
                "datrix_migration",
            ),
        ),
        # The CLI is the composition root: it may import any installed package
        # (generator and platform packages are still reached through entry
        # points, never imported by name -- see datrix-cli's own tests). The
        # rule is explicit and empty so the "every discovered package has a
        # rule" check in main() can tell "deliberately unrestricted" from
        # "nobody wrote one".
        "datrix_cli": BoundaryRule(forbidden_prefixes=()),
    }


def unruled_packages(
    packages: dict[str, PackageInfo], rules: dict[str, BoundaryRule]
) -> list[str]:
    """Discovered packages with no boundary rule -- silently unguarded if scanned."""
    return sorted(set(packages) - set(rules))


# ---------------------------------------------------------------------------
# I1 Target-Literal Ratchet (Decision D1, Invariant I1)
#
# The I1 ratchet polices the DERIVED shared-package set
# (discover_shared_packages -- every discovered package registering none of
# datrix.languages/datrix.platforms/datrix.generators/datrix.extensions;
# datrix_common, datrix_codegen_common, and datrix_cli today, never a
# hardcoded list). "Shared layers ask questions, target plugins answer
# them" — datrix_language and the leaf
# datrix_codegen_{python,typescript,aws,azure,docker,sql,component} packages
# are OWNERS of target identity and are exempt from this scan (they always
# register a taxonomy entry point, so discover_shared_packages never
# classifies them as shared).

# Central table / dict / class names known TODAY to encode closed-world target
# policy in a shared layer. The list is frozen: each entry is scheduled for
# deletion (the inline comment records where it lived and when it went), and
# the ratchet's job is to make sure nothing NEW joins this list while the
# remaining entries are removed.
TARGET_LITERAL_CENTRAL_NAMES: frozenset[str] = frozenset(
    {
        "Language",  # enums.py:13-18 (deleted 07-03)
        "ProjectLanguage",  # enums.py:26-30 (deleted 07-03)
        "GENERATORS_BY_LANGUAGE",  # enums.py:33 (deleted 06-04)
        "DeploymentProvider",  # enums.py:82-97 (deleted 07-03)
        "PROVIDER_GENERATORS",  # enums.py:289 (deleted 07-03)
        "_TARGET_KIND_MAP",  # gendsl/parser.py:36, validator.py:30 (deleted 06-02)
        "_KNOWN_DEFINITION_MODULES",  # gendsl/compiler.py:153-161 (deleted 06-02)
        "EMAIL_REALIZATION",  # provisioning.py:60-81 (deleted 07-04)
        "SMS_REALIZATION",  # provisioning.py:92-109 (deleted 07-04)
        "PUSH_REALIZATION",  # provisioning.py:~129 (deleted 07-04)
        "_DEFAULT_BACKEND_BY_PROVIDER",  # secret_backend.py:175-178 (deleted 07-04)
        "VALID_PROVIDERS_BY_RUNTIME",  # deployment_validation.py:29-42 (deleted 07-04)
        "_SERVERLESS_PLATFORM_BY_PROVIDER",  # hosting_validation.py:22-26 (deleted 07-04)
        "_PLATFORM_INFRA_CLASSES",  # auth_resolver.py:54-71 (deleted 07-05)
    }
)

# Enum-qualified member accesses (Attribute nodes like `DeploymentProvider.AWS`)
# recognized as target-literal references. Keyed by the enum class name so a
# bare identifier collision (e.g. a local variable named `AWS`) never matches --
# only `<ClassName>.<MEMBER>` attribute access counts.
TARGET_LITERAL_ENUM_MEMBERS: dict[str, frozenset[str]] = {
    "Language": frozenset({"PYTHON", "TYPESCRIPT", "SQL"}),
    "ProjectLanguage": frozenset({"PYTHON", "TYPESCRIPT"}),
    "DeploymentProvider": frozenset({"LOCAL", "EXISTING", "AWS", "AZURE"}),
}

# Platform-token identifier-shape match: mirrors
# _identifier_carries_target_name (G2, language tokens) but over registered
# PLATFORM tokens, restricted to the same declaration/type-reference
# positions scan_file_for_shared_target_names already scopes to (class/
# function defs, annotated/plain module- or class-level assignment targets,
# type references) -- reusing _identifier_segments and
# _identifiers_in_type_expression unmodified. "local" is EXCLUDED from the
# platform-token vocabulary for this check specifically: it is a registered
# datrix.platforms id that is also an ordinary English word, the exact reason
# G2 excludes platforms entirely. The vocabulary stays derived from the
# registry; only this word-collision set is hand-kept, and the self-test
# asserts every excluded token is still a registered platform so a stale
# exclusion fails loud.
_PLATFORM_TOKEN_EXCLUSIONS: frozenset[str] = frozenset({"local"})


def _platform_token_vocabulary() -> frozenset[str]:
    """Registered platform tokens, minus the English-word collision(s)."""
    return frozenset(registered_platform_names()) - _PLATFORM_TOKEN_EXCLUSIONS


def _target_literal_vocabulary() -> frozenset[str]:
    """Registered language names union registered platform names, INCLUDING
    "local" (unlike _platform_token_vocabulary, which excludes it as an
    English-word collision for the identifier-segment shape), union the identity
    provider types an installed platform package owns. In a str-equality/
    key/isinstance/import-path position "local" is a target identity, not
    English prose, and the measured collision count for these new kinds is 0.
    An identity provider type's rules belong to the package that integrates the
    provider, so a shared layer comparing against one is the same defect as a
    shared layer comparing against a platform name; the owned types are derived
    from the installed platform declarations, never listed here."""
    return (
        frozenset(registered_language_names())
        | frozenset(registered_platform_names())
        | _owned_identity_types()
    )


@functools.lru_cache(maxsize=1)
def _owned_identity_types() -> frozenset[str]:
    """The identity provider types an installed platform package owns, read once per run."""
    return owned_identity_provider_type_names()


#: Files that define or bridge the closed ``.dcfg`` identity provider vocabulary
#: (the enum itself, its bridge to the planner's open identifiers, and the built-in
#: ``external`` rules): they may name the enum's members and the provider-type
#: strings, and they are exempt from the identity rules below.
IDENTITY_VOCABULARY_HOME_SUFFIXES: tuple[str, ...] = (
    "config/datasource/identity_config.py",
    "identity/planner/config_bridge.py",
    "identity/authored_issuer_rules.py",
)

#: The shared tree where NO identity provider type's rule may live: a hit of an
#: identity kind here is a hard failure, and no baseline entry is admitted for it.
IDENTITY_RULES_HARD_ZERO_PREFIX: str = "datrix-common/src/datrix_common/identity/"

#: The target-literal kinds that name an identity provider type.
IDENTITY_RULE_KINDS: frozenset[str] = frozenset(
    {"identity_provider_member", "target_name_literal", "target_type_check", "target_module_import"}
)


def _is_identity_vocabulary_home(file_path: Path) -> bool:
    """Whether *file_path* is one of the identity vocabulary's home files."""
    posix = file_path.as_posix()
    return any(posix.endswith(suffix) for suffix in IDENTITY_VOCABULARY_HOME_SUFFIXES)


def _identity_provider_member_hits(
    tree: ast.AST, flagged_values: frozenset[str]
) -> list[tuple[str, int, str]]:
    """Find ``IdentityProvider.<MEMBER>`` attribute reads naming a flagged provider type.

    The enum is recognised through the names an ``identity_config`` import binds
    ``IdentityProvider`` to (any ``as`` alias), so ``IdentityProviderType.ZITADEL`` and
    ``ConfigIdentityProvider.ZITADEL`` are as visible as ``IdentityProvider.ZITADEL``.
    A member is flagged when its VALUE is in *flagged_values* (the owned provider
    types and the built-in ``external``); the credential kind ``apiKey`` names no
    provider product and is never flagged.

    Returns:
        ``(identifier, line_number, matched provider type)`` per hit.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[-1] == "identity_config"
        ):
            for imported in node.names:
                if imported.name == "IdentityProvider":
                    aliases.add(imported.asname or imported.name)
    if not aliases:
        return []
    value_by_member = {member.name: member.value for member in ConfigIdentityProvider}
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and value_by_member.get(node.attr) in flagged_values
        ):
            hits.append((f"{node.value.id}.{node.attr}", node.lineno, value_by_member[node.attr]))
    return hits


def _identity_flagged_values() -> frozenset[str]:
    """Provider types whose members/literals a shared layer must not name: the owned
    types plus the built-in ``external`` type."""
    return _owned_identity_types() | {ConfigIdentityProvider.EXTERNAL.value}


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
    "datrix_migration",
    "datrix_testing",
)

# Root name(s) recognized as "the deployment/infrastructure provider" for the
# `.value`/`str(...)` detection forms below. Restricting to these roots (a
# bare `deployment` variable, or `self._deployment` / `self.deployment`) is
# what separates a genuine deployment-provider comparison from the many OTHER
# provider axes in the same files (StorageProvider, EmailProvider, SmsProvider,
# SearchProvider, PaymentProvider, metrics/tracing provider) which all reach
# their own `.provider` off a *different* config object (e.g. `cfg.provider`,
# `email_config.provider`, `metrics_config.provider`) and must NOT ratchet here.
_DEPLOYMENT_ROOT_ATTRS: frozenset[str] = frozenset({"deployment", "_deployment"})


def _is_providerid_call(node: ast.AST) -> bool:
    """True if *node* is a call to the ``ProviderId`` constructor (bare or
    module-qualified), e.g. ``ProviderId("azure")`` or ``identity.ProviderId(x)``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "ProviderId"
    if isinstance(func, ast.Attribute):
        return func.attr == "ProviderId"
    return False


def _is_deployment_root(node: ast.AST) -> bool:
    """True if *node* is the deployment-config object itself: a bare
    ``deployment`` name, or an attribute access ending in ``deployment``/
    ``_deployment`` (e.g. ``self._deployment``, ``self.deployment``).
    """
    if isinstance(node, ast.Name):
        return node.id in _DEPLOYMENT_ROOT_ATTRS
    if isinstance(node, ast.Attribute):
        return node.attr in _DEPLOYMENT_ROOT_ATTRS
    return False


def _is_deployment_provider_attr(node: ast.AST) -> bool:
    """True if *node* is ``<deployment-root>.provider`` (the raw provider
    field read off the deployment config, before any ``.value``/``str()``).
    """
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "provider"
        and _is_deployment_root(node.value)
    )


def _is_deployment_provider_value_expr(node: ast.AST) -> bool:
    """True if *node* stringifies the DEPLOYMENT provider specifically --
    ``<deployment-root>.provider.value`` or ``str(<deployment-root>.provider)``
    (including the redundant ``str(<deployment-root>.provider.value)`` form).
    Deliberately narrower than "any `.provider.value`" so the many other
    provider axes (storage/email/sms/search/payment/metrics/tracing) --
    which share the `.provider`/`.value` shape but hang off a *different*
    config object -- never match (see ``_DEPLOYMENT_ROOT_ATTRS``).
    """
    if isinstance(node, ast.Attribute) and node.attr == "value":
        return _is_deployment_provider_attr(node.value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        arg = node.args[0]
        return _is_deployment_provider_attr(arg) or _is_deployment_provider_value_expr(
            arg
        )
    return False


def _provider_conditional_compare_kind(
    node: ast.Compare,
) -> Literal["providerid_compare", "deployment_provider_value_compare"] | None:
    """Classify a single ``ast.Compare`` node as a provider-conditional hit,
    or ``None`` if it isn't one.

    Only simple binary comparisons (exactly one operator) are considered --
    chained comparisons (``a == b == c``) are not a shape this ratchet's
    known sites use. Two forms match, checked against BOTH sides of the
    comparison:

      - ``providerid_compare``: either side is a call to ``ProviderId(...)``
        (covers ``== ProviderId(...)``, ``ProviderId(...) ==``, ``!=
        ProviderId(...)``, and a ``match``/``case`` guard's ``p ==
        ProviderId("aws")`` -- ``ProviderId`` names exactly ONE axis
        (deployment/infrastructure provider identity), so no other-axis
        exclusion is needed for this form).
      - ``deployment_provider_value_compare``: either side stringifies the
        deployment provider specifically (``_is_deployment_provider_value_expr``),
        covering ``deployment.provider.value == "..."`` and
        ``str(self._deployment.provider) != "aws"``.

    Only Eq/NotEq operators count (``==``/``!=``) -- an ``in``/``not in``
    membership test (e.g. a dict-dispatch-table lookup) is a different
    successor shape not yet in this ratchet's scope.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None

    sides = [node.left, node.comparators[0]]

    if any(_is_providerid_call(side) for side in sides):
        return "providerid_compare"
    if any(_is_deployment_provider_value_expr(side) for side in sides):
        return "deployment_provider_value_compare"
    return None


def _match_subject_is_provider(subject: ast.AST) -> bool:
    """True if a ``match`` statement's subject expression names a provider
    identity (e.g. ``match provider_id:``) -- a bare ``Name`` or the ``attr``
    of an ``Attribute`` chain whose final segment contains "provider"
    (case-insensitive).
    """
    if isinstance(subject, ast.Name):
        return "provider" in subject.id.lower()
    if isinstance(subject, ast.Attribute):
        return "provider" in subject.attr.lower()
    return False


def _string_literal_value(node: ast.AST) -> str | None:
    """Bare string-literal value of *node*, or None for any other expression
    shape (a Name, an f-string, a call, ...). Both D5 sub-patterns below only
    fire on an ACTUAL literal, never a variable that merely happens to be
    assigned a provider-id string elsewhere -- that keeps the ratchet
    precise (see ``_provider_literal_compare_kind``'s docstring for why a
    look-alike like ``"consul"`` must never match).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _provider_literal_compare_kind(
    node: ast.Compare, provider_ids: frozenset[str]
) -> Literal["provider_literal_compare"] | None:
    """D5's first provider-literal sub-pattern (invariant I6 successor,
    second AST pattern class): a plain Eq/NotEq comparison whose comparand
    (either side) is a bare string literal exactly equal to a REGISTERED
    platform provider id -- e.g. ``backend == "azure"``. This is the
    successor form the existing ``_provider_conditional_compare_kind`` does
    not cover: no ``ProviderId(...)`` wrapper, no ``.provider`` root, just a
    plain variable compared to a plain provider-name string.

    Only called for a Compare node the FIRST (ProviderId-shaped) pattern
    already rejected -- see ``_walk_for_provider_conditionals`` -- so the two
    never double-count the same node.

    Specificity comes entirely from membership in *provider_ids* (enumerated
    from the installed ``datrix.platforms`` entry points at scan time, never
    hardcoded): a literal equal to some OTHER string -- e.g. ``"consul"``, a
    service-discovery type, or ``"elasticsearch"``, a search backend -- never
    matches, however provider-adjacent the surrounding code looks.

    Args:
        node: The `ast.Compare` node under consideration.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        ``"provider_literal_compare"`` on a match, else ``None``.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None
    sides = [node.left, node.comparators[0]]
    if any(_string_literal_value(side) in provider_ids for side in sides):
        return "provider_literal_compare"
    return None


def _provider_literal_container_ids(
    node: ast.AST, provider_ids: frozenset[str]
) -> frozenset[str]:
    """Provider ids among a List/Tuple/Set literal's OWN elements (D5's
    second provider-literal sub-pattern).

    Catches a closed-world provider-id collection literal wherever it is
    DEFINED -- ``frozenset({"azure"})``, ``{"aws", "azure"}``,
    ``("aws", "azure")`` -- not only when it sits directly inside a
    ``Compare``/``in`` test. A module-level
    ``_ALWAYS_REQUIRES_CREDENTIALS = frozenset({"azure"})`` is a
    collection-literal DEFINITION; a later ``backend in
    _ALWAYS_REQUIRES_CREDENTIALS`` membership test (a different line) compares
    against a bare ``Name``, which a Compare-only scan would never resolve
    back to the literal. Scanning every qualifying collection literal as its
    own node -- independent of its parent -- closes that gap.

    CLOSED-WORLD requirement (the precision fix a real scan run surfaced):
    every string-literal element of the collection must ITSELF be a
    registered provider id, not merely at-least-one. A collection that mixes
    a provider id with an OTHER axis's own literal -- e.g.
    ``SUPPORTED_STORAGE_PROVIDERS = frozenset({"s3", "minio", "azure_blob",
    "local"})`` in a language package's storage generator -- is that
    StorageProvider axis's own closed
    world (``s3``/``minio``/``azure_blob`` are never registered platform
    provider ids), not a platform-identity collection; "local" landing in it
    is coincidental token overlap, not a deployment-platform conditional, and
    must not ratchet. A genuine platform-identity collection (like
    ``_ALWAYS_REQUIRES_CREDENTIALS`` above) is drawn ENTIRELY from
    ``provider_ids`` with no off-axis sibling literal, so the subset check
    below distinguishes the two without any axis-name heuristic.

    Args:
        node: Any AST node; only `ast.List`/`ast.Tuple`/`ast.Set` produce hits.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        *node*'s string-literal elements when they are a non-empty subset of
        *provider_ids* (i.e. closed-world), else an empty frozenset.
    """
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return frozenset()
    string_literals = frozenset(
        value for elt in node.elts if (value := _string_literal_value(elt)) is not None
    )
    if not string_literals or not string_literals.issubset(provider_ids):
        return frozenset()
    return string_literals


@dataclass(frozen=True)
class ProviderConditionalHit:
    """One occurrence of a platform-identity conditional in a language-package file."""

    file_path: Path
    line_number: int
    kind: Literal[
        "providerid_compare",
        "deployment_provider_value_compare",
        "match_case_provider_subject",
        "provider_literal_compare",
        "provider_literal_container",
    ]


@dataclass(frozen=True)
class PackageInfo:
    """Package metadata for scanning."""

    name: str  # e.g., datrix_common
    root: Path  # e.g., d:/datrix/datrix-common
    src_dir: Path  # e.g., d:/datrix/datrix-common/src/datrix_common


@dataclass(frozen=True)
class Violation:
    """Represents a single import boundary violation."""

    file_path: Path
    line_number: int
    imported_module: str
    source_package: str
    forbidden_prefix: str


@dataclass(frozen=True)
class AllowlistEntry:
    """Represents a single allowlist entry."""

    file_pattern: str
    import_prefix: str
    issue_url: str


@dataclass(frozen=True)
class TargetLiteralHit:
    """One occurrence of a target-literal identifier in a shared-layer file."""

    file_path: Path
    line_number: int
    identifier: str
    kind: Literal[
        "central_table_name",
        "enum_member_qualified",
        "platform_token_identifier",
        "platform_token_module_name",
        "target_name_literal",
        "target_type_check",
        "target_module_import",
        "identity_provider_member",
    ]
    # The registered target token *identifier* carries as a segment, is
    # exactly equal to, or (for target_module_import) appears as a dotted-
    # path segment of. Populated for the two platform_token_* kinds and the
    # three target_* kinds -- the frozen-name matches (central_table_name /
    # enum_member_qualified) match an exact known name, not a vocabulary
    # member, so they carry no "matched" vocabulary member.
    matched_target: str | None = None


@dataclass(frozen=True)
class TargetLiteralBaselineEntry:
    """One frozen per-file count in the I1 ratchet baseline."""

    file: str  # path relative to monorepo root, forward slashes
    count: int


@dataclass(frozen=True)
class FunctionLevelImportHit:
    """One function-level (non-module-top) import statement in a
    ``datrix-common`` file (invariant I6 successor)."""

    file_path: Path
    line_number: int


def is_forbidden_import(
    source_package: str,
    imported_module: str,
    forbidden_prefix: str,
    allowed_subtrees: frozenset[str] = frozenset(),
) -> bool:
    """Check if an import violates a forbidden prefix rule.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of the ``allowed_subtrees`` entries -- used to admit a
    narrow, reviewed part of an otherwise-forbidden package.

    Subtree matching uses an exact-or-child rule:
        subtree ``s`` matches ``m`` when ``m == s`` or ``m.startswith(s + ".")``.
    This ensures ``enums`` matches ``enums`` and ``enums.foo`` but never
    ``enums_other``.

    Args:
        source_package: The package doing the importing (e.g., datrix_common)
        imported_module: The full dotted import name (e.g., datrix_language.parser)
        forbidden_prefix: The forbidden prefix (may end with _ for wildcard)
        allowed_subtrees: Fully-qualified subtree roots that override the
            forbidden prefix for this source package.

    Returns:
        True if the import is forbidden, False otherwise
    """
    # Self-imports are always allowed
    if (
        imported_module.startswith(source_package + ".")
        or imported_module == source_package
    ):
        return False

    # Handle wildcard prefixes (e.g., datrix_codegen_)
    if forbidden_prefix.endswith("_"):
        # Wildcard match: imported module starts with prefix
        matched = imported_module.startswith(forbidden_prefix)
    else:
        # Exact prefix match (or module.submodule)
        matched = (
            imported_module.startswith(forbidden_prefix + ".")
            or imported_module == forbidden_prefix
        )

    if not matched:
        return False

    # The import matches a forbidden prefix; check whether an allowed subtree
    # carves it out.  A subtree ``s`` covers ``m`` when ``m == s`` or
    # ``m.startswith(s + ".")``.
    for subtree in allowed_subtrees:
        if imported_module == subtree or imported_module.startswith(subtree + "."):
            return False

    return True


def extract_imports_from_file(file_path: Path) -> list[tuple[int, str]]:
    """Extract all imports from a Python file using AST.

    Args:
        file_path: Path to Python source file

    Returns:
        List of (line_number, imported_module_name) tuples

    Raises:
        SyntaxError: If the file cannot be parsed
        OSError: If the file cannot be read
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import foo, bar.baz
            for alias in node.names:
                imports.append((node.lineno, alias.name))

        elif isinstance(node, ast.ImportFrom):
            # from foo import bar
            # Skip relative imports (node.level > 0)
            if node.level == 0 and node.module is not None:
                imports.append((node.lineno, node.module))

    return imports


def discover_packages(base_dir: Path) -> dict[str, PackageInfo]:
    """Discover all datrix-* packages in the monorepo.

    Args:
        base_dir: Monorepo root directory

    Returns:
        Dictionary mapping package names to PackageInfo objects
    """
    packages: dict[str, PackageInfo] = {}

    for candidate in base_dir.iterdir():
        if not candidate.is_dir():
            continue

        # Only process datrix-* directories
        if not candidate.name.startswith("datrix-"):
            continue

        src_dir = candidate / "src"
        if not src_dir.exists():
            continue

        # Find the package name by looking for the actual package directory under src/
        # e.g., datrix-common/src/datrix_common/ -> package name is datrix_common
        package_dirs = [
            d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix")
        ]

        if not package_dirs:
            continue

        # Use the first datrix* directory name as the package name
        package_name = package_dirs[0].name
        packages[package_name] = PackageInfo(
            name=package_name,
            root=candidate,
            src_dir=src_dir / package_name,
        )

    return packages


def scan_package_for_violations(
    package_info: PackageInfo,
    monorepo_root: Path,
    verbose: bool,
    rules: dict[str, BoundaryRule],
) -> list[Violation]:
    """Scan a single package for import boundary violations.

    Args:
        package_info: Package metadata
        monorepo_root: Monorepo root for relative path calculation
        verbose: Print each file being scanned
        rules: The boundary rules (``build_boundary_rules`` over the discovered
            taxonomy). Every scanned package must have an entry -- main()
            refuses to run otherwise (``unruled_packages``), so a missing rule
            here is a programming error, not a permissive default.

    Returns:
        List of violations found
    """
    violations: list[Violation] = []

    if package_info.name not in rules:
        raise KeyError(
            f"No boundary rule for package {package_info.name!r}. main() must reject "
            f"unruled packages before scanning; got rules for {sorted(rules)}."
        )
    rule = rules[package_info.name]

    # Directories to scan: src/, tests/, fixtures/, helpers/
    scan_dirs = [package_info.src_dir]

    # Add optional directories if they exist
    for dir_name in ["tests", "fixtures", "helpers"]:
        optional_dir = package_info.root / dir_name
        if optional_dir.exists() and optional_dir.is_dir():
            scan_dirs.append(optional_dir)

    # Walk all .py files under all scan directories, all held to the same
    # allowed_subtrees -- src/, tests/, fixtures/ and helpers/ alike. There is
    # no test-tree carve-out: a subtree forbidden in production code is
    # forbidden in tests too.
    permitted_subtrees = rule.allowed_subtrees
    for scan_dir in scan_dirs:
        for py_file in scan_dir.rglob("*.py"):
            if verbose:
                rel_path = py_file.relative_to(monorepo_root)
                print(f"Scanning: {rel_path}", file=sys.stderr)

            try:
                imports = extract_imports_from_file(py_file)
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

            # Check each import against forbidden prefixes, respecting allowed subtrees
            for line_num, imported_module in imports:
                for forbidden_prefix in rule.forbidden_prefixes:
                    if is_forbidden_import(
                        package_info.name,
                        imported_module,
                        forbidden_prefix,
                        permitted_subtrees,
                    ):
                        violations.append(
                            Violation(
                                file_path=py_file,
                                line_number=line_num,
                                imported_module=imported_module,
                                source_package=package_info.name,
                                forbidden_prefix=forbidden_prefix,
                            )
                        )
                        break  # Only report first matching forbidden prefix

    return violations


# A heuristic dotted-import-path shape: one or more '.'-separated Python
# identifier segments, at least two segments (a bare identifier is never a
# module path). Matches "datrix_codegen_aws.gendsl.aws_definitions"; never
# matches a plain single word or a non-identifier string.
_DOTTED_MODULE_PATH_RE: re.Pattern[str] = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+"
)


def _platform_token_in_dotted_string(
    value: str, platform_names: frozenset[str]
) -> str | None:
    """The platform token a dotted-module-path-shaped string carries in any
    of its '.'-separated segments, or ``None`` -- ``value`` itself is never
    matched whole; only a genuine dotted-path shape is considered, and each
    segment is matched via the same identifier-segment algorithm
    ``_identifier_carries_target_name`` already applies to real identifiers.
    """
    if not _DOTTED_MODULE_PATH_RE.fullmatch(value):
        return None
    for segment in value.split("."):
        matched = _identifier_carries_target_name(segment, platform_names)
        if matched is not None:
            return matched
    return None


def _scoped_plain_assign_values(tree: ast.Module) -> list[tuple[ast.expr, int]]:
    """Every ``(value, line_number)`` of a plain (unannotated) ``ast.Assign``
    declared at MODULE top level or immediate CLASS-BODY level -- the exact
    same scope ``_scoped_plain_assign_targets`` restricts its TARGETS to,
    applied to the VALUE side instead so a dotted-module-path string literal
    assigned there can be inspected. A function-body-local assignment is out
    of scope for the same reason it is out of scope for
    ``_scoped_plain_assign_targets``: an ordinary local variable's value is
    not a declaration.
    """
    values: list[tuple[ast.expr, int]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            values.append((stmt.value, stmt.lineno))
        elif isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, ast.Assign):
                    values.append((class_stmt.value, class_stmt.lineno))
    return values


def _platform_token_module_path_string_hits(
    tree: ast.Module, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(string, line_number, matched_platform)`` for every dotted-module-
    path-shaped string literal assigned as a plain value, a dict value, or a
    list/tuple/set element, at the same module-/class-body scope
    ``_scoped_plain_assign_values`` restricts to -- an ordinary function-
    local string is out of scope, exactly like the identifier-shape match.
    """
    hits: list[tuple[str, int, str]] = []

    def _check_constant(node: ast.expr) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            matched = _platform_token_in_dotted_string(node.value, platform_names)
            if matched is not None:
                hits.append((node.value, node.lineno, matched))

    for value, _line in _scoped_plain_assign_values(tree):
        if isinstance(value, ast.Dict):
            for element in value.values:
                _check_constant(element)
        elif isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for element in value.elts:
                _check_constant(element)
        else:
            _check_constant(value)
    return hits


def _platform_token_identifier_hits(
    tree: ast.Module, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(identifier, line_number, matched_platform)`` for every declaration
    or type-reference identifier carrying a registered platform token as an
    identifier segment.

    Scoped to the EXACT declaration/type-reference positions
    ``scan_file_for_shared_target_names`` (the shared-target-name ratchet) already restricts language-
    token matching to -- class/function/method DEFINITIONS, a dataclass
    field or type alias at module/class-body level (annotated or plain
    assignment), and a type reference (isinstance/issubclass argument, base
    class, parameter/return annotation, the value of a ``TypeAlias``
    annotated assignment -- a string in any other annotated value is data,
    not a forward reference). Never a
    bare local variable, function parameter, loop variable, or attribute
    READ -- an unscoped scan over an open, runtime-derived vocabulary is
    exactly what produced G2's own 305-false-positive result for the
    (excluded) "local" case; the same false-positive mode would reproduce
    for every OTHER platform token (e.g. "aws" as a local variable name) if
    this match were not scoped identically.
    """
    hits: list[tuple[str, int, str]] = []

    def _emit(identifier: str, line_number: int) -> None:
        matched = _identifier_carries_target_name(identifier, platform_names)
        if matched is not None:
            hits.append((identifier, line_number, matched))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _emit(node.name, node.lineno)
            for base in node.bases:
                for identifier, lineno in _identifiers_in_type_expression(base):
                    _emit(identifier, lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit(node.name, node.lineno)
            all_args = [
                *node.args.args,
                *node.args.kwonlyargs,
                node.args.vararg,
                node.args.kwarg,
            ]
            for arg in all_args:
                if arg is not None and arg.annotation is not None:
                    for identifier, lineno in _identifiers_in_type_expression(
                        arg.annotation
                    ):
                        _emit(identifier, lineno)
            if node.returns is not None:
                for identifier, lineno in _identifiers_in_type_expression(node.returns):
                    _emit(identifier, lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _emit(node.target.id, node.lineno)
            if node.value is not None and _annotation_declares_type_alias(node.annotation):
                for identifier, lineno in _identifiers_in_type_expression(node.value):
                    _emit(identifier, lineno)
            for identifier, lineno in _identifiers_in_type_expression(node.annotation):
                _emit(identifier, lineno)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _TYPE_REFERENCE_CALL_NAMES:
                for call_arg in node.args[1:]:
                    for identifier, lineno in _identifiers_in_type_expression(call_arg):
                        _emit(identifier, lineno)

    for identifier, line_number in _scoped_plain_assign_targets(tree):
        _emit(identifier, line_number)

    return hits


def _platform_token_module_name_hits(
    file_path: Path, monorepo_root: Path, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(component, line_number, matched_platform)`` for every path
    component of *file_path*'s path relative to *monorepo_root* (directory
    names and the filename stem, split on '/' by the relative-path
    computation and on '_'/camelCase by ``_identifier_carries_target_name``)
    that carries a registered platform token as a segment -- catches a file
    at a path like ``deployment/azure_naming.py``. Reported at line 1: this
    is a file-level match, not tied to any single AST node.
    """
    hits: list[tuple[str, int, str]] = []
    rel_parts = file_path.relative_to(monorepo_root).parts
    components = (*rel_parts[:-1], Path(rel_parts[-1]).stem)
    for component in components:
        matched = _identifier_carries_target_name(component, platform_names)
        if matched is not None:
            hits.append((component, 1, matched))
    return hits


# ---------------------------------------------------------------------------
# Target-Literal Ratchet -- key/comparand/isinstance/import-path shapes
#
# The pre-existing target-literal kinds above match a frozen central-table/
# enum-member name list plus a declaration/type-reference identifier shape.
# They miss a target name used as a dict key, a `.get()` argument, an
# `==`/`in` comparand, an `isinstance`/`issubclass` class argument, or a
# dotted import-module segment -- real target-identity leaks a shared layer
# must not carry, in positions the identifier-shape match never visits. The
# three kinds below close that gap, scoped to exactly the AST positions
# enumerated in each kind's docstring -- never a generic "any string near a
# vocabulary word" scan, which would flag every docstring and log message.


def _owning_package_import_root(file_path: Path, monorepo_root: Path) -> str | None:
    """The import-root directory name (e.g. ``datrix_codegen_typescript_core``)
    that *file_path* lives under, resolved via *monorepo_root*-relative path
    segments only -- the same ``<package-dir>/src/<import-root>/...`` layout
    ``_platform_token_module_name_hits`` already assumes, never a substring
    match on the path string. Returns ``None`` when the path does not have
    at least that three-segment prefix (never expected for a file this
    scanner actually reaches, since every caller iterates a discovered
    package's own ``src_dir``).
    """
    rel_parts = file_path.relative_to(monorepo_root).parts
    if len(rel_parts) < 3 or rel_parts[1] != "src":
        return None
    return rel_parts[2]


def _language_core_own_language_names() -> dict[str, str]:
    """Map each ``LANGUAGE_CORE_PACKAGES`` key (a language-core library's own
    import root, e.g. ``datrix_codegen_typescript_core``) to the registered
    language name of the backend package it serves (e.g. ``typescript``),
    read live from ``entry_point_module_roots(AXIS_LANGUAGES)`` (inverted) --
    never a hardcoded core-package-to-language literal.

    Returns:
        ``{core import root: served language's registered name}``.

    Raises:
        ValueError: A ``LANGUAGE_CORE_PACKAGES`` value names a backend import
            root with no matching installed ``datrix.languages`` entry
            point -- a real configuration inconsistency between the mapping
            and the installed distributions, never silently skipped.
    """
    import_root_to_language = {
        import_root: language_name
        for language_name, import_root in entry_point_module_roots(AXIS_LANGUAGES).items()
    }
    served: dict[str, str] = {}
    for core_import_root, backend_import_root in LANGUAGE_CORE_PACKAGES.items():
        language_name = import_root_to_language.get(backend_import_root)
        if language_name is None:
            raise ValueError(
                f"LANGUAGE_CORE_PACKAGES entry {core_import_root!r} names backend "
                f"import root {backend_import_root!r}, which has no matching "
                f"installed 'datrix.languages' entry point. Installed entry-point "
                f"import roots: {sorted(import_root_to_language)}. Fix: verify the "
                f"backend package is installed into the active environment and its "
                f"pyproject.toml entry-point module path matches "
                f"{backend_import_root!r}."
            )
        served[core_import_root] = language_name
    return served


def _is_own_language_excluded(
    file_path: Path, monorepo_root: Path, matched_target: str
) -> bool:
    """True when *matched_target* names the language whose own core package
    *file_path* lives under (``LANGUAGE_CORE_PACKAGES``) -- e.g. a
    "typescript" hit inside ``datrix_codegen_typescript_core`` is that
    language's own home, not a target-identity leak. Scoped ONLY to the
    three new target-literal kinds; the two pre-existing
    platform-token kinds keep their own, separate
    ``_PLATFORM_TOKEN_EXCLUSIONS`` mechanism and never call this.
    """
    owning_root = _owning_package_import_root(file_path, monorepo_root)
    if owning_root is None or owning_root not in LANGUAGE_CORE_PACKAGES:
        return False
    served_language = _language_core_own_language_names()[owning_root]
    return matched_target.casefold() == served_language.casefold()


def _target_type_check_hits(
    tree: ast.Module, target_literal_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(identifier, line_number, matched_target)`` for every
    ``isinstance``/``issubclass`` call whose second argument (or a ``Tuple``
    element of it) is a type expression carrying a *target_literal_names*
    token as an identifier segment (``_identifier_carries_target_name``).

    Reuses ``_identifiers_in_type_expression`` -- the same type-expression
    walk the pre-existing ``platform_token_identifier`` kind already applies
    to ``isinstance``/``issubclass`` arguments -- against the full
    languages-union-platforms vocabulary rather than the platform-only one,
    so a language-named class (``isinstance(c, PythonRuntimeConfig)``) is
    caught here even though it is invisible to the platform-scoped kind.
    """
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in _TYPE_REFERENCE_CALL_NAMES:
            continue
        for call_arg in node.args[1:]:
            for identifier, lineno in _identifiers_in_type_expression(call_arg):
                matched = _identifier_carries_target_name(identifier, target_literal_names)
                if matched is not None:
                    hits.append((identifier, lineno, matched))
    return hits


def _target_module_import_hits(
    tree: ast.Module, target_literal_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(dotted module path, line_number, matched_target)`` for every
    ``ast.ImportFrom``/``ast.Import`` node whose dotted module path
    (``node.module`` for ``ImportFrom``, each ``alias.name`` for ``Import``)
    has a ``.``-split segment exactly equal to a *target_literal_names*
    member (``from datrix_common.config.platform.docker import X`` yields
    one hit naming ``docker``). Exact per-segment string equality only --
    unlike the identifier-shape kinds, a module path is never re-split on
    ``_``/camelCase, so ``datrix_codegen_python`` (one dotted segment) is
    not itself a hit. One hit per qualifying module path -- the first
    matching segment -- since a single import statement is one occurrence
    of the shape.
    """
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module_paths = [node.module]
        elif isinstance(node, ast.Import):
            module_paths = [alias.name for alias in node.names]
        else:
            continue

        for module_path in module_paths:
            for segment in module_path.split("."):
                if segment in target_literal_names:
                    hits.append((module_path, node.lineno, segment))
                    break
    return hits


def scan_file_for_target_literals(
    file_path: Path,
    monorepo_root: Path,
    platform_names: frozenset[str],
    target_literal_names: frozenset[str],
) -> list[TargetLiteralHit]:
    """AST-walk *file_path* for target-literal identifiers.

    Seven match kinds:
      - ``central_table_name``: any ``ast.Name``/``ast.ClassDef``/``ast.FunctionDef``
        (or ``ast.AsyncFunctionDef``) whose identifier is exactly one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (definition sites AND reference sites
        both count -- a table is a defect whether it's being defined or
        consumed), plus any ``ast.Attribute`` whose ``attr`` itself is one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (e.g. a module-qualified
        ``enums.GENERATORS_BY_LANGUAGE`` reference).
      - ``enum_member_qualified``: any ``ast.Attribute`` node whose ``value`` is
        an ``ast.Name`` with ``id`` in ``TARGET_LITERAL_ENUM_MEMBERS`` and whose
        ``attr`` is in the corresponding member frozenset (e.g. `Language.PYTHON`,
        `DeploymentProvider.AWS`) -- NOT a bare `AWS` identifier alone.
      - ``platform_token_identifier``: a declaration/type-reference identifier
        (class/function def, module-/class-level field or type alias, type
        reference) carrying a registered platform token as an identifier
        segment -- see ``_platform_token_identifier_hits``. ``"local"`` is
        excluded (English-word collision, see ``_PLATFORM_TOKEN_EXCLUSIONS``).
      - ``platform_token_module_name``: the file's own path (relative to
        *monorepo_root*, split on both ``/`` and ``_``/camelCase) or a
        dotted-module-path-shaped string literal assigned at module-/class-
        level scope carries a registered platform token -- see
        ``_platform_token_module_name_hits`` / ``_platform_token_module_path_string_hits``.
      - ``target_name_literal``: a string constant exactly equal to a
        ``_target_literal_vocabulary()`` member (registered language names
        UNION registered platform names, INCLUDING ``"local"``) in a
        comparison/key/``.get()``/dict-key/match-value position -- see
        ``_target_name_literal_hits``.
      - ``target_type_check``: an ``isinstance``/``issubclass`` call whose
        class argument carries a ``_target_literal_vocabulary()`` token as
        an identifier segment -- see ``_target_type_check_hits``.
      - ``target_module_import``: an ``ast.ImportFrom``/``ast.Import`` node
        whose dotted module path has a ``.``-split segment exactly equal to
        a ``_target_literal_vocabulary()`` member -- see
        ``_target_module_import_hits``.

    The three new kinds above are dropped for a file inside a
    ``LANGUAGE_CORE_PACKAGES`` package when the matched token names that
    package's own served language (``_is_own_language_excluded``). The two
    pre-existing platform-token kinds are unaffected; they keep their own,
    separate ``_PLATFORM_TOKEN_EXCLUSIONS`` mechanism.

    Args:
        file_path: Path to Python source file.
        monorepo_root: Monorepo root, for the module-name-from-path match and
            the own-language exclusion's package resolution.
        platform_names: Registered platform tokens minus the "local"
            English-word collision, from ``_platform_token_vocabulary()`` --
            feeds the two pre-existing platform-token kinds only.
        target_literal_names: Registered language names UNION registered
            platform names, INCLUDING "local", from
            ``_target_literal_vocabulary()`` -- feeds the three new kinds
            only.

    Returns:
        List of hits found in the file, in AST-walk order (the two
        pre-existing platform-token kinds, then the three new kinds, are
        appended after the frozen-name-match walk).

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[TargetLiteralHit] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in TARGET_LITERAL_CENTRAL_NAMES:
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.id,
                    kind="central_table_name",
                )
            )
        elif (
            isinstance(node, ast.ClassDef) and node.name in TARGET_LITERAL_CENTRAL_NAMES
        ):
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.name,
                    kind="central_table_name",
                )
            )
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in TARGET_LITERAL_CENTRAL_NAMES
        ):
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.name,
                    kind="central_table_name",
                )
            )
        elif isinstance(node, ast.Attribute):
            if node.attr in TARGET_LITERAL_CENTRAL_NAMES:
                hits.append(
                    TargetLiteralHit(
                        file_path=file_path,
                        line_number=node.lineno,
                        identifier=node.attr,
                        kind="central_table_name",
                    )
                )
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in TARGET_LITERAL_ENUM_MEMBERS
                and node.attr in TARGET_LITERAL_ENUM_MEMBERS[node.value.id]
            ):
                hits.append(
                    TargetLiteralHit(
                        file_path=file_path,
                        line_number=node.lineno,
                        identifier=f"{node.value.id}.{node.attr}",
                        kind="enum_member_qualified",
                    )
                )

    for identifier, line_number, matched in _platform_token_identifier_hits(
        tree, platform_names
    ):
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=identifier,
                kind="platform_token_identifier",
                matched_target=matched,
            )
        )

    for identifier, line_number, matched in _platform_token_module_name_hits(
        file_path, monorepo_root, platform_names
    ):
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=identifier,
                kind="platform_token_module_name",
                matched_target=matched,
            )
        )

    for identifier, line_number, matched in _platform_token_module_path_string_hits(
        tree, platform_names
    ):
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=identifier,
                kind="platform_token_module_name",
                matched_target=matched,
            )
        )

    identity_home = _is_identity_vocabulary_home(file_path)

    for value, line_number in target_name_literal_hits(tree, target_literal_names):
        if _is_own_language_excluded(file_path, monorepo_root, value):
            continue
        if identity_home and value in _owned_identity_types():
            continue
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=value,
                kind="target_name_literal",
                matched_target=value,
            )
        )

    for identifier, line_number, matched in _target_type_check_hits(
        tree, target_literal_names
    ):
        if _is_own_language_excluded(file_path, monorepo_root, matched):
            continue
        if identity_home and matched in _owned_identity_types():
            continue
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=identifier,
                kind="target_type_check",
                matched_target=matched,
            )
        )

    for module_path, line_number, matched in _target_module_import_hits(
        tree, target_literal_names
    ):
        if _is_own_language_excluded(file_path, monorepo_root, matched):
            continue
        if identity_home and matched in _owned_identity_types():
            continue
        hits.append(
            TargetLiteralHit(
                file_path=file_path,
                line_number=line_number,
                identifier=module_path,
                kind="target_module_import",
                matched_target=matched,
            )
        )

    if not identity_home:
        for identifier, line_number, matched in _identity_provider_member_hits(
            tree, _identity_flagged_values()
        ):
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=line_number,
                    identifier=identifier,
                    kind="identity_provider_member",
                    matched_target=matched,
                )
            )

    return hits


def scan_target_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    shared_packages: tuple[str, ...],
) -> dict[Path, list[TargetLiteralHit]]:
    """Scan every ``.py`` file under each of *shared_packages*' ``src/`` tree
    (via *packages*, as already discovered by ``discover_packages``) for
    target-literal identifiers.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        shared_packages: The DERIVED shared-package set
            (``discover_shared_packages``) -- every discovered package
            registering none of the four taxonomy entry-point groups.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[TargetLiteralHit]] = {}
    platform_names = _platform_token_vocabulary()
    target_literal_names = _target_literal_vocabulary()

    for package_name in shared_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_target_literals(
                    py_file, monorepo_root, platform_names, target_literal_names
                )
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


def load_target_literal_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the baseline TOML.

    Args:
        baseline_path: Path to the target-literal baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run,
        before this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue

        file_rel = entry.get("file", "")
        count = entry.get("count")

        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_target_literal_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the baseline TOML as ``[[baseline]] file=... count=...``
    entries, sorted by file for deterministic diffs.

    Args:
        baseline_path: Path to the target-literal baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# I1 Target-Literal Ratchet Baseline\n"
        "#\n"
        "# Frozen per-file counts of target-literal identifiers (language/provider\n"
        "# names hardcoded in a shared layer -- Decision D1, Invariant I1).\n"
        "# Any INCREASE in a file's count fails datrix/scripts/scan/check-import-boundaries.ps1\n"
        "# --check-target-literals. Decreases are always allowed and should be captured\n"
        "# by re-running with --update-baseline once a later change deletes an identifier\n"
        "# (the terminal state is 0 for every entry here).\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_target_literal_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: target-literal count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


def check_identity_rules_hard_zero(
    hits_by_file: dict[Path, list[TargetLiteralHit]],
    baseline: dict[str, int],
    monorepo_root: Path,
) -> list[str]:
    """Hold the shared identity tree at a HARD ZERO for identity provider type rules.

    An identity provider type's issuer / JWKS / audience rules belong to the package
    that integrates the provider and are resolved from the plugin registry; nothing
    under ``IDENTITY_RULES_HARD_ZERO_PREFIX`` may name an owned provider type (as a
    comparison, key, type check or import path) or an ``IdentityProvider`` member of
    one. Unlike the decrease-only ratchet, no baseline entry is admitted for that tree.

    Args:
        hits_by_file: The target-literal scan result.
        baseline: The frozen per-file counts.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        One message per identity-rule hit in the tree, and one per baseline entry
        naming a file in it.
    """
    owned = _owned_identity_types()
    messages: list[str] = []
    for file_path, hits in sorted(hits_by_file.items()):
        rel = str(file_path.relative_to(monorepo_root)).replace("\\", "/")
        if not rel.startswith(IDENTITY_RULES_HARD_ZERO_PREFIX):
            continue
        for hit in hits:
            names_identity_type = hit.kind == "identity_provider_member" or (
                hit.kind in IDENTITY_RULE_KINDS and hit.matched_target in owned
            )
            if names_identity_type:
                messages.append(
                    f"{rel}:{hit.line_number}: identity provider type "
                    f"{hit.matched_target!r} is named here ({hit.kind}: {hit.identifier}); "
                    f"the shared identity tree holds no provider type's rules -- they belong "
                    f"to the package that integrates the provider (hard zero, no baseline)"
                )
    for rel in sorted(baseline):
        if rel.startswith(IDENTITY_RULES_HARD_ZERO_PREFIX):
            messages.append(
                f"{rel}: the target-literal baseline names a file in the shared identity "
                f"tree, which is held at hard zero -- delete the entry"
            )
    return messages


def _walk_for_provider_conditionals(
    node: ast.AST,
    file_path: Path,
    hits: list[ProviderConditionalHit],
    provider_ids: frozenset[str],
) -> None:
    """Recursively walk *node* collecting ``ProviderConditionalHit``s.

    A custom walker (rather than ``ast.walk``) is required for exactly one
    reason: a ``match provider_id:`` statement is counted ONCE, as the
    ``match_case_provider_subject`` hit at the ``match`` line -- NOT once
    plus once again per ``case p if p == ProviderId(...):`` guard. Each
    ``case`` guard is itself an ``ast.Compare`` that would otherwise ALSO
    satisfy ``providerid_compare``, double-counting the same logical site.
    So when a qualifying ``ast.Match`` is found, its ``case`` guards are
    skipped while patterns and bodies are still walked normally (a guard
    is only ever the provider-identity check the match already counted;
    unrelated real conditionals inside a case body are not exempted).

    D5 second pattern class (added by this task): every ``ast.Compare`` node
    the existing ``ProviderId``-shaped pattern rejects is ALSO checked against
    ``_provider_literal_compare_kind`` (a bare literal comparand), and every
    ``ast.List``/``ast.Tuple``/``ast.Set`` node encountered anywhere in the
    walk is checked against ``_provider_literal_container_ids`` (a
    closed-world provider-id collection literal). Neither new check can
    double-count a node the first three forms already claimed, because the
    literal-compare check only runs when the ProviderId-shaped check returned
    ``None``, and the container check is a disjoint node type (a Compare node
    is never simultaneously a List/Tuple/Set node).
    """
    if isinstance(node, ast.Match):
        if _match_subject_is_provider(node.subject):
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    kind="match_case_provider_subject",
                )
            )
        for case in node.cases:
            # Deliberately skip case.guard -- see docstring above.
            for stmt in case.body:
                _walk_for_provider_conditionals(stmt, file_path, hits, provider_ids)
        return

    if isinstance(node, ast.Compare):
        compare_kind: (
            Literal[
                "providerid_compare",
                "deployment_provider_value_compare",
                "provider_literal_compare",
            ]
            | None
        ) = _provider_conditional_compare_kind(node)
        if compare_kind is None:
            compare_kind = _provider_literal_compare_kind(node, provider_ids)
        kind = compare_kind
        if kind is not None:
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path, line_number=node.lineno, kind=kind
                )
            )
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        if _provider_literal_container_ids(node, provider_ids):
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    kind="provider_literal_container",
                )
            )

    for child in ast.iter_child_nodes(node):
        _walk_for_provider_conditionals(child, file_path, hits, provider_ids)


def scan_file_for_provider_conditionals(
    file_path: Path, provider_ids: frozenset[str]
) -> list[ProviderConditionalHit]:
    """AST-walk *file_path* for platform-identity conditionals (I6 successor
    ratchet, DI-4/DI-5, plus the D5 provider-literal patterns).

    See ``_provider_conditional_compare_kind``, ``_match_subject_is_provider``,
    ``_provider_literal_compare_kind``, and ``_provider_literal_container_ids``
    for the exact matched/excluded shapes.

    Args:
        file_path: Path to Python source file.
        provider_ids: The registered platform provider ids this scan run
            checks literals against (see ``registered_platform_names()``).

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

    hits: list[ProviderConditionalHit] = []
    _walk_for_provider_conditionals(tree, file_path, hits, provider_ids)
    return hits


def scan_provider_conditionals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    language_packages: tuple[str, ...],
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each language package's ``src/`` tree
    (via *packages*, as already discovered by ``discover_packages``) for
    platform-identity conditionals. Provider ids are derived once per call
    via ``registered_platform_names()`` -- never hardcoded -- and passed to
    every per-file scan.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        language_packages: The discovered taxonomy's language packages
            (``GeneratorTaxonomy.language_packages``).

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in language_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
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


def load_provider_conditional_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the provider-conditional
    baseline TOML.

    Args:
        baseline_path: Path to the provider-conditional baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run, before
        this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue

        file_rel = entry.get("file", "")
        count = entry.get("count")

        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_provider_conditional_baseline(
    baseline_path: Path, counts: dict[str, int]
) -> None:
    """Write ``counts`` to the provider-conditional baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the provider-conditional baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# I6 Successor Ratchet Baseline (invariant I6, DI-4/DI-5)\n"
        "#\n"
        "# Frozen per-file counts of platform-identity CONDITIONALS in the language\n"
        "# packages (datrix_codegen_python, datrix_codegen_typescript) -- the successor\n"
        "# form of the removed DeploymentProvider branches (the literal\n"
        "# `grep DeploymentProvider.` is already empty; DI-3 deleted the enum). These\n"
        "# sites are DI-5-deferred: legitimate today, but frozen so they cannot grow\n"
        "# while each cluster is migrated onto a decision engine.\n"
        "# Any INCREASE in a file's count fails datrix/scripts/scan/check-import-boundaries.ps1\n"
        "# --check-provider-conditionals. Decreases are always allowed and should be\n"
        "# captured by re-running with --update-baseline once a DI-5 change collapses a\n"
        "# cluster -- reaching 0 everywhere is the DI-5 end-state.\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_provider_conditional_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens (and reaching 0 is the DI-5 goal).

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: provider-conditional count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


def scan_shared_package_provider_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    shared_packages: tuple[str, ...],
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each of *shared_packages*' ``src/`` tree
    for platform-identity conditionals -- REUSES
    ``scan_file_for_provider_conditionals`` (the two D5 sub-patterns plus the
    pre-existing ``ProviderId``/``match``-case forms) unmodified; only the
    package SCOPE differs from ``scan_provider_conditionals`` (which targets
    the discovered taxonomy's language packages).

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        shared_packages: The DERIVED shared-package set
            (``discover_shared_packages``) -- every discovered package
            registering none of the four taxonomy entry-point groups.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in shared_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
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


def check_shared_package_provider_literals(
    hits_by_file: dict[Path, list[ProviderConditionalHit]],
    monorepo_root: Path,
) -> list[str]:
    """Return one message per hit found in a shared package -- ANY hit fails.

    Unlike ``check_provider_conditional_ratchet`` (decrease-only against a
    frozen, non-zero baseline for the language packages), this comparator
    has no baseline at all: a shared package's provider-literal count must
    be exactly zero, always. Returns an empty list only when
    ``hits_by_file`` is empty.

    Args:
        hits_by_file: Output of `scan_shared_package_provider_literals`.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        List of human-readable failure messages, one per hit, sorted by
        (file, line).
    """
    messages: list[str] = []
    for file_path in sorted(hits_by_file):
        rel_path = file_path.relative_to(monorepo_root)
        for hit in sorted(hits_by_file[file_path], key=lambda h: h.line_number):
            messages.append(
                f"{rel_path}:{hit.line_number}: shared-package provider-literal "
                f"conditional ({hit.kind}) -- shared layers must never encode "
                "platform-specific policy (Principle 10, D1). Fix: replace this "
                "conditional with a PlatformCapabilityDeclaration/LanguagePlugin "
                "field the affected platform declares, and ask the resolved "
                "plugin instead of comparing a provider identifier here."
            )
    return messages


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
        "# datrix-common, datrix-semantic, datrix-migration and datrix-testing, plus\n"
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
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: function-level-import count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


# ---------------------------------------------------------------------------
# G1 Shared-Vocabulary Ratchet (Decision D3, Invariant I2)
#
# Fails when a datrix-codegen-{lang} module declares a module-level
# frozenset/set/dict whose normalized member set equals a member set already
# declared in datrix_codegen_kernel.enums, OR in one of the additional
# non-enums.py canonical homes named in
# _ADDITIONAL_SHARED_VOCABULARY_SOURCES (a vocabulary moved out of enums.py
# for a layering reason, e.g. LOG_BUILTIN_METHODS). The LANGUAGE packages
# this ratchet polices are the discovered taxonomy's ``language_packages``
# (discover_generator_taxonomy), threaded in by main(), so a new language
# generator is policed from the commit that registers its entry point.


def _import_shared_enums_module() -> ModuleType:
    """Import and return ``datrix_codegen_kernel.enums``, the single module
    every G1 canonical-source harvest function (Enum and non-Enum alike)
    reads live at scan time -- never a hardcoded mirror of its content.

    Returns:
        The imported ``datrix_codegen_kernel.enums`` module object.

    Raises:
        RuntimeError: if the module cannot be imported (the shared
            vocabulary layer is not installed in the active venv).
    """
    try:
        from datrix_codegen_kernel import enums as shared_enums
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import datrix_codegen_kernel.enums -- the G1 "
            "shared-vocabulary ratchet requires datrix-codegen-kernel "
            "installed in the active environment (D:\\datrix\\.venv). Fix: "
            "run this script via check-import-boundaries.ps1, which "
            "activates the venv first."
        ) from exc
    return shared_enums


def _shared_enum_members() -> dict[str, dict[str, str]]:
    """Every ``str, Enum`` class declared in ``datrix_codegen_kernel.enums``,
    keyed by class name, mapped to ``{member_name: member_value}``.

    Read from the INSTALLED package at scan time -- never a hardcoded mirror
    of enums.py's content -- so an Enum vocabulary added there later is
    picked up with zero edit to this scanner. This covers ONLY the ``str,
    Enum`` half of the canonical source; ``_shared_non_enum_vocabularies``
    covers the plain dict/set/frozenset half (Decision D3's DSL exception-
    status map, the NoSQL unsupported-method map, and the NoSQL
    supported-method set are deliberately not Enums -- see that function).

    Returns:
        Mapping of enum class name -> {member name -> member value}.

    Raises:
        RuntimeError: if datrix_codegen_kernel.enums cannot be imported (the
            shared vocabulary layer is not installed in the active venv).
    """
    shared_enums = _import_shared_enums_module()

    members: dict[str, dict[str, str]] = {}
    for name, candidate in vars(shared_enums).items():
        if (
            isinstance(candidate, type)
            and issubclass(candidate, enum.Enum)
            and candidate is not enum.Enum
        ):
            members[name] = {item.name: str(item.value) for item in candidate}
    return members


# AST call-target names recognized as wrapping a set/frozenset display when
# deciding whether a module-level assignment in enums.py is a container
# constant (see ``_is_module_level_container_assignment``).
_VOCABULARY_CONTAINER_CALL_NAMES: frozenset[str] = frozenset({"frozenset", "set"})


def _is_module_level_container_assignment(stmt: ast.stmt) -> str | None:
    """Return the assigned name if *stmt* is a module-level ``Assign``/
    ``AnnAssign`` to a single bare ``Name`` whose right-hand side is a dict
    display, a set display, or a ``frozenset(...)``/``set(...)`` call --
    else ``None``.

    This is a SHAPE test only (does this statement declare a container
    constant?), never a name test -- no vocabulary name is ever hardcoded
    here, so a new dict/set/frozenset constant added to ``enums.py`` later
    is picked up with zero edit to this scanner, mirroring
    ``_shared_enum_members``'s "read live, never mirrored" property for the
    Enum half. The RHS's own inner shape is deliberately not inspected any
    further here (a ``frozenset(...)`` call's argument may be a literal
    display or a generator expression -- both count as "container-shaped";
    the actual member VALUES always come from
    the live imported object in ``_non_enum_vocabulary_member_set``, never
    from re-parsing this argument).

    Args:
        stmt: A top-level statement from ``enums.py``'s module body.

    Returns:
        The assigned identifier, or ``None`` if *stmt* is not a qualifying
        module-level container assignment.
    """
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None
        name_node = stmt.targets[0]
        value_node = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if not isinstance(stmt.target, ast.Name):
            return None
        name_node = stmt.target
        value_node = stmt.value
    else:
        return None

    if isinstance(value_node, (ast.Dict, ast.Set)):
        return name_node.id
    if (
        isinstance(value_node, ast.Call)
        and isinstance(value_node.func, ast.Name)
        and value_node.func.id in _VOCABULARY_CONTAINER_CALL_NAMES
    ):
        return name_node.id
    return None


def _non_enum_vocabulary_member_set(name: str, runtime_value: object) -> frozenset[str]:
    """Resolve *runtime_value* (the live object bound to *name* in the
    imported ``enums.py``) to its canonical member-value set.

    A ``dict``'s canonical member set is its KEYS -- that is what a
    redeclaring copy duplicates (e.g. ``DSL_EXCEPTION_HTTP_STATUS``'s keys,
    never its status-code values). A ``set``/``frozenset``'s canonical
    member set is its elements directly.

    Args:
        name: The module-level identifier this value is bound to (for error
            messages only).
        runtime_value: The actual object ``getattr(enums_module, name)``.

    Returns:
        The frozenset of canonical member strings.

    Raises:
        TypeError: if *runtime_value* is not a dict/set/frozenset, or any of
            its keys/elements is not a string. A canonical declaration whose
            members cannot be determined must fail loudly here, never be
            silently skipped -- a silently-skipped canonical source is the
            exact coverage gap this harvest exists to close.
    """
    if isinstance(runtime_value, dict):
        candidate_members = runtime_value.keys()
        shape = "dict keys"
    elif isinstance(runtime_value, (frozenset, set)):
        candidate_members = runtime_value
        shape = "set/frozenset elements"
    else:
        raise TypeError(
            f"G1 harvest: '{name}' in datrix_codegen_kernel.enums has a "
            f"module-level dict/set/frozenset assignment shape but its live "
            f"value is a {type(runtime_value).__name__}, not a dict/set/"
            f"frozenset. Expected the runtime type to match the declared "
            f"shape. Fix: keep '{name}' bound to a dict/set/frozenset, or "
            f"restructure it so it is no longer a bare module-level "
            f"assignment (e.g. move it behind a function)."
        )

    members: set[str] = set()
    for element in candidate_members:
        if not isinstance(element, str):
            raise TypeError(
                f"G1 harvest: '{name}' in datrix_codegen_kernel.enums has a "
                f"non-string member ({element!r}, type "
                f"{type(element).__name__}) among its {shape}. Expected "
                f"every member to be a str so it can be compared against a "
                f"redeclaring copy's string literals. Fix: make '{name}' "
                f"string-keyed/valued, or valid options are to exclude it "
                f"from module-level container declarations in enums.py."
            )
        members.add(element)
    return frozenset(members)


# Declared homes for a canonical shared vocabulary that lives OUTSIDE
# enums.py. Each entry is (dotted module path, attribute name). This exists
# only for a vocabulary that was deliberately MOVED out of enums.py because
# its derivation is shaped like the layer it lives beside (e.g.
# LOG_BUILTIN_METHODS is `frozenset(method for category, method in
# BUILTIN_REGISTRY if category == "Log")`, and enums.py -- the
# target-neutral vocabulary module -- must not import the transpiler to
# compute it; see datrix_codegen_common/transpiler/builtin_registry.py).
#
# This is deliberately NOT a general "scan every container in this module"
# rule the way `_shared_non_enum_vocabularies` scans enums.py: a home module
# outside enums.py may also declare module-level containers whose members
# are not strings (e.g. builtin_registry.py's `UI_BUILTIN_GROUPS`, a
# frozenset of `BuiltinGroup` enum members, and `BUILTIN_REGISTRY`, a dict
# keyed by `(category, method)` tuples) -- `_non_enum_vocabulary_member_set`
# correctly raises TypeError on those, so scanning the whole module would
# break the ratchet on every run instead of harvesting the one vocabulary
# that was actually moved there. Naming the exact attribute keeps the
# harvest working without hardcoding a mirror of the moved value, and the
# `hasattr` check below fails loud (not silently) the moment the declared
# attribute is renamed or removed, so this list cannot go silently stale.
_ADDITIONAL_SHARED_VOCABULARY_SOURCES: tuple[tuple[str, str], ...] = (
    ("datrix_codegen_common.transpiler.builtin_registry", "LOG_BUILTIN_METHODS"),
)


def _additional_shared_non_enum_vocabularies() -> dict[str, frozenset[str]]:
    """Canonical member sets for the shared vocabularies declared in
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES`` -- vocabulary homes outside
    ``enums.py`` that hold a canonical set moved there for a layering
    reason.

    Returns:
        Mapping of attribute name -> canonical member-value set, one entry
        per declared source.

    Raises:
        RuntimeError: if a declared module cannot be imported, or if a
            declared attribute is missing from the imported module (the
            declared home has gone stale -- renamed, removed, or moved
            again without updating this list).
        TypeError: if a declared attribute's members cannot be determined
            as strings (propagated from ``_non_enum_vocabulary_member_set``).
    """
    vocabularies: dict[str, frozenset[str]] = {}
    for module_path, attr_name in _ADDITIONAL_SHARED_VOCABULARY_SOURCES:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise RuntimeError(
                f"G1 harvest: failed to import declared shared-vocabulary "
                f"home '{module_path}' (for attribute '{attr_name}') -- is "
                f"the package that provides it installed in the active "
                f"environment (D:\\datrix\\.venv)? Fix: run this script via "
                f"check-import-boundaries.ps1, which activates the venv "
                f"first, or correct the module path in "
                f"_ADDITIONAL_SHARED_VOCABULARY_SOURCES if the module moved."
            ) from exc
        if not hasattr(module, attr_name):
            raise RuntimeError(
                f"G1 harvest: declared shared-vocabulary home "
                f"'{module_path}.{attr_name}' is missing -- '{attr_name}' "
                f"is not an attribute of the imported '{module_path}' "
                f"module. Expected _ADDITIONAL_SHARED_VOCABULARY_SOURCES "
                f"and the installed package to agree. Fix: reinstall the "
                f"owning package in the active environment, or if "
                f"'{attr_name}' was renamed or moved again, update "
                f"_ADDITIONAL_SHARED_VOCABULARY_SOURCES in "
                f"check_import_boundaries.py to match -- never drop the "
                f"entry, or this vocabulary silently stops being policed."
            )
        runtime_value = getattr(module, attr_name)
        vocabularies[attr_name] = _non_enum_vocabulary_member_set(attr_name, runtime_value)
    return vocabularies


def _shared_non_enum_vocabularies() -> dict[str, frozenset[str]]:
    """Every module-level ``dict``/``set``/``frozenset`` constant DECLARED IN
    ``enums.py``'s own source (never an imported symbol merely visible
    through it, e.g. ``BUILTIN_REGISTRY``) that is not a ``str, Enum`` class,
    mapped to its canonical member-value set -- merged with the additional
    declared homes in ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES`` (canonical
    vocabularies that were moved out of enums.py; see that constant).

    Covers value-derived declarations the AST cannot evaluate on its own --
    e.g. a ``frozenset(<generator expression>)`` derived from another
    table, not a literal display. The AST is used ONLY to decide WHICH names are
    container-shaped constants (``_is_module_level_container_assignment``);
    the member set always comes from the live imported object, which
    already carries the fully-derived value regardless of how it was
    computed.

    No vocabulary name is ever hardcoded for the enums.py half: a dict/set/
    frozenset constant added to ``enums.py`` later is harvested with zero
    edit here, the same generality property ``_shared_enum_members`` already
    has for the Enum half (Decision D3, Invariant I2; design principle 16 --
    shared layers ask, target plugins answer). Only a vocabulary that no
    longer lives in enums.py needs an entry in
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES``.

    Returns:
        Mapping of module-level constant name -> canonical member-value set.

    Raises:
        RuntimeError: if datrix_codegen_kernel.enums cannot be imported, if
            a name the AST identifies as a module-level assignment is
            missing from the imported module (source/installed-package
            mismatch), or if a declared additional home is missing or
            unimportable (propagated from
            ``_additional_shared_non_enum_vocabularies``).
        TypeError: if a qualifying container's members cannot be determined
            as strings (propagated from ``_non_enum_vocabulary_member_set``).
    """
    shared_enums = _import_shared_enums_module()
    source_path = Path(shared_enums.__file__)
    source_code = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(source_path))

    vocabularies: dict[str, frozenset[str]] = {}
    for stmt in tree.body:
        name = _is_module_level_container_assignment(stmt)
        if name is None:
            continue
        if not hasattr(shared_enums, name):
            raise RuntimeError(
                f"G1 harvest: '{name}' is assigned at module level in "
                f"{source_path} but is not an attribute of the imported "
                f"datrix_codegen_kernel.enums module. Expected the source "
                f"file and the installed package to agree. Fix: reinstall "
                f"datrix-codegen-kernel in the active environment (D:\\"
                f"datrix\\.venv)."
            )
        runtime_value = getattr(shared_enums, name)
        vocabularies[name] = _non_enum_vocabulary_member_set(name, runtime_value)

    vocabularies.update(_additional_shared_non_enum_vocabularies())
    return vocabularies


@dataclass(frozen=True)
class SharedVocabularyHit:
    """One module-level container in a language package whose normalized
    member set duplicates a datrix_codegen_kernel.enums vocabulary -- an
    Enum class's value set or a plain module-level dict/set/frozenset's
    key/element set alike."""

    file_path: Path
    line_number: int
    container_name: str
    matched_vocabulary: str


def _resolve_vocabulary_element(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> tuple[str, bool] | None:
    """Resolve one set/frozenset/dict-key element to ``(value, is_bare)``.

    ``is_bare`` is True for a plain string constant (``"all"``), False for a
    qualified enum-member reference (``QueryTerminal.ALL``) resolved through
    *enum_members* to the member's real value (``"all"``) -- both forms
    compare equal once resolved, but only the bare form counts toward
    "hardcodes the literal" (see ``_normalize_container`` docstring).

    Returns:
        ``None`` for any other node shape (a Name, an f-string, a call, an
        ``EnumClass.MEMBER`` pair the enum does not actually declare, ...) --
        such an element means the container is not a closed vocabulary
        literal at all, and the caller skips it entirely.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        member_map = enum_members.get(node.value.id)
        if member_map is not None and node.attr in member_map:
            return member_map[node.attr], False
    return None


@dataclass(frozen=True)
class _NormalizedContainer:
    """A module-level container literal, resolved to its member value set."""

    values: frozenset[str]
    has_bare_literal: bool


def _normalize_container(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> _NormalizedContainer | None:
    """Normalize a module-level ``frozenset(...)``/``set(...)``/``{...}``/
    dict-literal RHS to its member value set, resolving both bare string
    literals and qualified ``EnumClass.MEMBER`` references to the same
    underlying strings so the two forms compare equal (see
    ``_resolve_vocabulary_element``).

    Returns:
        ``None`` if *node* is not a recognized set/frozenset/dict literal,
        has zero elements, or contains any element that is not a bare string
        or a resolvable qualified enum-member reference -- an unrecognized
        element means "not provably a closed vocabulary literal", not
        "clean"; the caller simply cannot compare a partially-unresolvable
        container against a specific enum's exact member set.
    """
    elements: list[ast.AST]
    if isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        elements = list(node.args[0].elts)
    elif isinstance(node, ast.Set):
        elements = list(node.elts)
    elif isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None  # a **spread entry -- not a closed literal
        elements = [key for key in node.keys if key is not None]
    else:
        return None

    if not elements:
        return None

    values: set[str] = set()
    has_bare_literal = False
    for element in elements:
        resolved = _resolve_vocabulary_element(element, enum_members)
        if resolved is None:
            return None
        value, is_bare = resolved
        values.add(value)
        has_bare_literal = has_bare_literal or is_bare

    return _NormalizedContainer(
        values=frozenset(values), has_bare_literal=has_bare_literal
    )


def scan_file_for_shared_vocabulary(
    file_path: Path,
    enum_members: dict[str, dict[str, str]],
    non_enum_vocabularies: dict[str, frozenset[str]],
) -> list[SharedVocabularyHit]:
    """AST-walk *file_path* for module-level set/frozenset/dict declarations
    whose normalized member set equals a ``datrix_codegen_kernel.enums``
    vocabulary's own value set (Decision D3, Invariant I2) -- an Enum
    class's value set, or a plain module-level dict's key set / set's
    frozenset's element set (``non_enum_vocabularies``) alike. G1's own
    specification never restricts the canonical side to Enum classes; a
    name -> value lookup table like ``DSL_EXCEPTION_HTTP_STATUS`` or a
    member set like ``NOSQL_SUPPORTED_METHODS`` is exactly as canonical as
    ``HTTPMethod``, and a bare-literal redeclaration of either is the same
    defect.

    A hit requires TWO conditions: the normalized member set exactly equals
    some enum class's value set, AND the container includes at least one
    BARE STRING LITERAL element. A container built ENTIRELY from qualified
    enum-member references (e.g. ``frozenset({QueryTerminal.ALL,
    QueryTerminal.FIRST, QueryTerminal.FIRST_OR_FAIL, QueryTerminal.COUNT})``,
    the real, already-compliant case at
    ``datrix-codegen-python/.../_transpiler_query_builder.py:19-24``) is
    CONSUMING the enum, not hardcoding it, and must not be flagged -- only a
    container containing at least one hand-spelled string is "the DSL
    vocabulary re-scattered after being centralised" (design doc S2.3).

    Only module-level (top-of-file) ``Assign``/``AnnAssign`` statements are
    scanned -- a set built inside a function body is a local computation,
    never a closed-world vocabulary table.

    Args:
        file_path: Path to Python source file.
        enum_members: Output of ``_shared_enum_members()``.
        non_enum_vocabularies: Output of ``_shared_non_enum_vocabularies()``.

    Returns:
        List of hits found in the file, in source order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    canonical_value_sets: dict[str, frozenset[str]] = {
        class_name: frozenset(values.values())
        for class_name, values in enum_members.items()
    }
    canonical_value_sets.update(non_enum_vocabularies)

    hits: list[SharedVocabularyHit] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        normalized = _normalize_container(value_node, enum_members)
        if normalized is None or not normalized.has_bare_literal:
            continue

        matched_vocabulary = next(
            (
                vocabulary_name
                for vocabulary_name, value_set in canonical_value_sets.items()
                if value_set == normalized.values
            ),
            None,
        )
        if matched_vocabulary is None:
            continue

        container_name = ", ".join(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        hits.append(
            SharedVocabularyHit(
                file_path=file_path,
                line_number=stmt.lineno,
                container_name=container_name or "<unknown>",
                matched_vocabulary=matched_vocabulary,
            )
        )

    return hits


def scan_shared_vocabulary(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    language_packages: tuple[str, ...],
) -> dict[Path, list[SharedVocabularyHit]]:
    """Scan every ``.py`` file under each language package's ``src/`` tree
    for module-level vocabulary duplication against
    ``datrix_codegen_kernel.enums``.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        language_packages: The discovered taxonomy's language packages
            (``GeneratorTaxonomy.language_packages``).

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[SharedVocabularyHit]] = {}
    enum_members = _shared_enum_members()
    non_enum_vocabularies = _shared_non_enum_vocabularies()

    for package_name in language_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_shared_vocabulary(
                    py_file, enum_members, non_enum_vocabularies
                )
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


def load_shared_vocabulary_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the shared-vocabulary
    baseline TOML.

    Args:
        baseline_path: Path to the shared-vocabulary baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run, before
        this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue
        file_rel = entry.get("file", "")
        count = entry.get("count")
        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_shared_vocabulary_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the shared-vocabulary baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the shared-vocabulary baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# G1 Shared-Vocabulary Ratchet Baseline (Decision D3, Invariant I2)\n"
        "#\n"
        "# Frozen per-file counts of module-level frozenset/set/dict\n"
        "# declarations in the four datrix-codegen-{lang} packages whose\n"
        "# normalized member set duplicates a datrix_codegen_kernel.enums\n"
        "# vocabulary. Any INCREASE in a file's count fails\n"
        "# datrix/scripts/scan/check-import-boundaries.ps1 --check-shared-vocabulary.\n"
        "# Decreases are always allowed and should be captured by re-running\n"
        "# with --update-baseline once a later change deletes a redundant\n"
        "# container (the terminal state is 0 for every entry here).\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_shared_vocabulary_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []
    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: shared-vocabulary count increased from baseline "
                f"{frozen} to {current}"
            )
    return messages


# ---------------------------------------------------------------------------
# G2 Shared-Layer Target-Name Ratchet (Decision D4, Invariant I3)
#
# The shared codegen packages this ratchet polices: the language layer and the
# generation kernel (which took the GenDSL data model and catalog modules out of
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

# Registered-target identifier-segment call names this ratchet treats as a
# TYPE reference (the second argument names a class/type, not a value).
_TYPE_REFERENCE_CALL_NAMES: frozenset[str] = frozenset({"isinstance", "issubclass"})

_CAMEL_TO_SNAKE_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_RE2 = re.compile(r"([a-z0-9])([A-Z])")


def _identifier_segments(identifier: str) -> tuple[str, ...]:
    """Tokenize *identifier* into lowercase segments, splitting on ``_`` and
    at camelCase word boundaries (``fooBar`` -> ``foo``, ``bar``;
    ``PythonStructFieldRow`` -> ``python``, ``struct``, ``field``, ``row``).
    """
    with_boundaries = _CAMEL_TO_SNAKE_RE1.sub(r"\1_\2", identifier)
    with_boundaries = _CAMEL_TO_SNAKE_RE2.sub(r"\1_\2", with_boundaries)
    return tuple(seg.lower() for seg in with_boundaries.split("_") if seg)


def _identifier_carries_target_name(
    identifier: str, target_names: frozenset[str]
) -> str | None:
    """Return the registered target name *identifier* carries as a segment
    (or a contiguous run of adjacent camelCase segments -- e.g.
    ``TypeScript`` tokenizes as ``type`` + ``script``, which must still
    match the single registered target name ``typescript``), or ``None`` if
    it carries none.

    Segment-EXACT matching (never bare substring) is deliberate: ``java``
    must never match inside a hypothetical ``javascript`` identifier (a
    single, unsplit segment, since it has no internal capital or
    underscore) -- only a genuine identifier segment, or an exact
    concatenation of adjacent segments, counts.

    Args:
        identifier: The identifier to test.
        target_names: Registered language names and their declared alias
            tokens, lowercased (``shared_target_name_vocabulary()``).

    Returns:
        The matched target name or alias token, or ``None``.
    """
    segments = _identifier_segments(identifier)
    for start in range(len(segments)):
        for end in range(start + 1, len(segments) + 1):
            candidate = "".join(segments[start:end])
            if candidate in target_names:
                return candidate
    return None


_TYPE_ALIAS_ANNOTATION_NAME = "TypeAlias"


def _annotation_declares_type_alias(annotation: ast.AST) -> bool:
    """True when *annotation* is ``TypeAlias`` or a dotted ``<module>.TypeAlias``
    (``typing.TypeAlias``, ``typing_extensions.TypeAlias``).

    The value of an annotated assignment is a type expression only under this
    annotation, where a string element really is a forward reference
    (``X: TypeAlias = "Foo | Bar"``). Under any other annotation the value is
    data (``EXTS: tuple[str, ...] = ("js", "css")``) and a string in it is not
    an identifier.
    """
    if isinstance(annotation, ast.Name):
        return annotation.id == _TYPE_ALIAS_ANNOTATION_NAME
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == _TYPE_ALIAS_ANNOTATION_NAME
    return False


def _identifiers_in_type_expression(node: ast.AST) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` pair reachable from *node* by
    walking ONLY the syntactic shapes a type expression / isinstance
    argument can take: a bare name, a dotted attribute (``mod.Name``), a
    ``X | Y`` union, a generic subscript (``Callable[..., X | Y]``,
    ``Union[X, Y]``), a tuple of names (the ``isinstance(x, (A, B))`` form),
    or a string forward-reference.

    Does NOT descend into a function/lambda body, a comprehension, or any
    other executable-statement context -- this is only ever called on an
    annotation / isinstance-argument / base-class / type-alias-value
    expression, which is what keeps an ordinary local variable (e.g.
    ``local_cache = {}`` inside a function body) out of scope entirely: it
    is never a type expression (see the module docstring for why this
    matters -- a bare local variable can coincidentally be named after a
    registered language, e.g. ``python = fetch_stat()``).
    """
    results: list[tuple[str, int]] = []
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Name):
            results.append((current.id, current.lineno))
        elif isinstance(current, ast.Attribute):
            results.append((current.attr, current.lineno))
        elif isinstance(current, ast.BinOp) and isinstance(current.op, ast.BitOr):
            stack.extend([current.left, current.right])
        elif isinstance(current, ast.Subscript):
            stack.append(current.value)
            stack.append(current.slice)
        elif isinstance(current, (ast.Tuple, ast.List)):
            stack.extend(current.elts)
        elif isinstance(current, ast.Constant) and isinstance(current.value, str):
            results.append((current.value, current.lineno))
    return results


@dataclass(frozen=True)
class SharedTargetNameHit:
    """One shared-layer identifier carrying a registered target name as an
    identifier segment (Decision D4, Invariant I3)."""

    file_path: Path
    line_number: int
    identifier: str
    matched_target: str
    kind: Literal["class_def", "function_def", "field_or_alias", "type_reference"]


def _scoped_plain_assign_targets(tree: ast.Module) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` target of a plain (unannotated)
    ``ast.Assign`` statement declared at MODULE top level or immediate
    CLASS-BODY level -- never inside a function/method body.

    This is the scoped counterpart to the ``ast.AnnAssign`` handling in
    ``scan_file_for_shared_target_names``: an annotated declaration
    (``StructSliceBuilder: TypeAlias = ...``) is always a genuine module- or
    class-level declaration syntactically, but a PLAIN assignment
    (``PYTHON_DEFAULT_PORT = 8000``) is syntactically identical
    to an ordinary function-local variable assignment -- the only thing
    that distinguishes a real module constant from
    ``def f(): python_helper = 1`` is WHERE the statement sits in the tree.
    Restricting to ``tree.body`` and each ``ClassDef.body`` (a SCOPED
    traversal, never a blanket ``ast.walk``) is what keeps a function-body
    assignment out of scope, exactly like the declaration/type-reference-only
    dispatch in ``scan_file_for_shared_target_names`` keeps a bare local
    variable out of scope.

    Args:
        tree: The parsed module AST.

    Returns:
        ``(identifier, line_number)`` pairs for every ``ast.Name`` target of
        a qualifying plain ``Assign`` statement.
    """
    targets: list[tuple[str, int]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets.extend(
                (target.id, stmt.lineno)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
        elif isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, ast.Assign):
                    targets.extend(
                        (target.id, class_stmt.lineno)
                        for target in class_stmt.targets
                        if isinstance(target, ast.Name)
                    )
    return targets


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

    def _emit(identifier: str, line_number: int, kind: str) -> None:
        matched = _identifier_carries_target_name(identifier, target_names)
        if matched is not None:
            hits.append(
                SharedTargetNameHit(
                    file_path=file_path,
                    line_number=line_number,
                    identifier=identifier,
                    matched_target=matched,
                    kind=kind,  # type: ignore[arg-type]
                )
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _emit(node.name, node.lineno, "class_def")
            for base in node.bases:
                for identifier, lineno in _identifiers_in_type_expression(base):
                    _emit(identifier, lineno, "type_reference")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit(node.name, node.lineno, "function_def")
            all_args = [
                *node.args.args,
                *node.args.kwonlyargs,
                node.args.vararg,
                node.args.kwarg,
            ]
            for arg in all_args:
                if arg is not None and arg.annotation is not None:
                    for identifier, lineno in _identifiers_in_type_expression(arg.annotation):
                        _emit(identifier, lineno, "type_reference")
            if node.returns is not None:
                for identifier, lineno in _identifiers_in_type_expression(node.returns):
                    _emit(identifier, lineno, "type_reference")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _emit(node.target.id, node.lineno, "field_or_alias")
            if node.value is not None and _annotation_declares_type_alias(node.annotation):
                for identifier, lineno in _identifiers_in_type_expression(node.value):
                    _emit(identifier, lineno, "type_reference")
            for identifier, lineno in _identifiers_in_type_expression(node.annotation):
                _emit(identifier, lineno, "type_reference")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _TYPE_REFERENCE_CALL_NAMES:
                for call_arg in node.args[1:]:
                    for identifier, lineno in _identifiers_in_type_expression(call_arg):
                        _emit(identifier, lineno, "type_reference")

    for identifier, line_number in _scoped_plain_assign_targets(tree):
        _emit(identifier, line_number, "field_or_alias")

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


@dataclass(frozen=True)
class SharedTargetNameBaseline:
    """The frozen shared-target-name baseline: a count per file plus the
    written reason for every entry that carries one. A reason is part of the
    frozen record: ``--update-baseline`` reads it back and re-emits it."""

    counts: dict[str, int]
    reasons: dict[str, str]


def load_shared_target_name_baseline(baseline_path: Path) -> SharedTargetNameBaseline:
    """Load ``{relative_file: frozen_count}`` and ``{relative_file: reason}``
    from the shared-target-name baseline TOML. A ``reason`` is accepted only
    when it is a non-blank string. Returns an empty baseline if the file does
    not exist yet."""
    if not baseline_path.exists():
        return SharedTargetNameBaseline(counts={}, reasons={})

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue
        file_rel = entry.get("file", "")
        count = entry.get("count")
        if not (file_rel and isinstance(count, int)):
            continue
        counts[file_rel] = count
        reason = entry.get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons[file_rel] = reason

    return SharedTargetNameBaseline(counts=counts, reasons=reasons)


def write_shared_target_name_baseline(
    baseline_path: Path, counts: dict[str, int], reasons: dict[str, str]
) -> None:
    """Write ``counts`` to the shared-target-name baseline TOML as
    ``[[baseline]] file=... count=... [reason=...]`` entries, sorted by file.

    A ``reason`` is emitted for every file in ``reasons`` that still has a
    count, as a TOML basic string, so a hand-written reason survives every
    ``--update-baseline`` regeneration. A file without a reason is written
    without one -- a reason is never invented here."""
    header = (
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


def check_shared_target_name_reasons(baseline: SharedTargetNameBaseline) -> list[str]:
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
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens."""
    messages: list[str] = []
    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: shared-target-name count increased from baseline "
                f"{frozen} to {current}"
            )
    return messages


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


def _language_name_tokens(language_name: str) -> frozenset[str]:
    """One language's identifier vocabulary: its registered name plus every
    declared alias (``declaration_for_language(...).name_tokens``), lowercase."""
    return frozenset(
        token.lower()
        for token in (*declaration_for_language(language_name).name_tokens, language_name)
    )


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


def load_own_target_name_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{package_name: frozen_count}`` from the own-target-name
    baseline TOML. Returns an empty dict if the file does not exist yet.
    Mirrors ``load_shared_target_name_baseline`` exactly, keyed by
    ``package`` instead of ``file``.
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue
        package_name = entry.get("package", "")
        count = entry.get("count")
        if package_name and isinstance(count, int):
            counts[package_name] = count

    return counts


def write_own_target_name_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write *counts* to the own-target-name baseline TOML as
    ``[[baseline]] package=... count=...`` entries, sorted by package name.
    Mirrors ``write_shared_target_name_baseline``."""
    header = (
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

    lines = [header]
    for package_name in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'package = "{package_name}"\n')
        lines.append(f"count = {counts[package_name]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_own_target_name_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    package whose count INCREASED (baseline missing == baseline 0). Mirrors
    ``check_shared_target_name_ratchet`` exactly -- never flags a decrease."""
    messages: list[str] = []
    for package_name in sorted(current_counts.keys()):
        current = current_counts[package_name]
        frozen = baseline.get(package_name, 0)
        if current > frozen:
            messages.append(
                f"{package_name}: own-target-name count increased from baseline "
                f"{frozen} to {current}"
            )
    return messages


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
    elements: list[ast.AST]
    if isinstance(node, ast.Tuple):
        elements = list(node.elts)
    elif isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        elements = list(node.args[0].elts)
    elif isinstance(node, ast.Set):
        elements = list(node.elts)
    elif isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None  # a **spread entry -- not a closed literal
        elements = [key for key in node.keys if key is not None]
    else:
        return None

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
    declarations_by_package: dict[str, list[_ModuleContainerDeclaration]] = {}
    for package_name, package_info in sorted(packages.items()):
        package_declarations: list[_ModuleContainerDeclaration] = []
        for py_file in sorted(package_info.src_dir.rglob("*.py")):
            try:
                package_declarations.extend(
                    _scan_file_for_module_containers(py_file)
                )
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
        declarations_by_package[package_name] = package_declarations

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


@dataclass(frozen=True)
class CrossPackageVocabularyBaseline:
    """The frozen G3 baseline: one count per file, plus the written reason
    for every entry a design REQUIRES to stay duplicated (Decision 36 D9).

    ``reasons`` is keyed by the same relative file path as ``counts`` and
    holds only the entries that carry a ``reason`` key. A reason is part
    of the frozen record, not a comment beside it: ``--update-baseline``
    reads it back through this type and re-emits it, so a regenerated
    baseline can never silently turn a reviewed duplicate into an
    unexplained count.
    """

    counts: dict[str, int]
    reasons: dict[str, str]


def load_cross_package_vocabulary_baseline(
    baseline_path: Path,
) -> CrossPackageVocabularyBaseline:
    """Load the cross-package-vocabulary baseline TOML: ``{relative_file:
    frozen_count}`` plus ``{relative_file: reason}`` for every entry that
    carries a written D9 reason.

    Args:
        baseline_path: Path to the cross-package-vocabulary baseline TOML file.

    Returns:
        Empty counts and reasons if the file does not exist yet.
    """
    if not baseline_path.exists():
        return CrossPackageVocabularyBaseline(counts={}, reasons={})

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue
        file_rel = entry.get("file", "")
        count = entry.get("count")
        if not (file_rel and isinstance(count, int)):
            continue
        counts[file_rel] = count
        reason = entry.get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons[file_rel] = reason

    return CrossPackageVocabularyBaseline(counts=counts, reasons=reasons)


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
    header = (
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


def check_cross_package_vocabulary_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []
    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: cross-package-vocabulary count increased from "
                f"baseline {frozen} to {current}"
            )
    return messages


# ---------------------------------------------------------------------------
# Re-export facade ratchet: a name has exactly one import path.
#
# Opt-in via --check-reexport-facades, it AST-scans every discovered
# package's src/ and tests/ trees (discover_packages() -- the same set every
# other whole-workspace ratchet in this file uses), every .py file under this
# repo's own datrix/scripts/ tree, and every .py file under
# datrix/claude-config/.claude/hooks/ (if any), for the shapes of re-export
# facade -- a name with a second, redundant import path on top of its real,
# single home -- all attributed to the PROVIDING module (the module through
# which the second path runs), never to the file where a consumer statement
# happens to appear. A providing module is a Datrix module or a test-tree
# module (``tests.<module>``, anchored at the importing file's own package).
# Shapes 1 and 2 follow; the module-object, entry-point and unresolved shapes
# are described below them:
#
# 1. Provider side. A module whose top-level `from <datrix module> import N`
#    binds a name N that is listed in the module's own __all__, or imported
#    as `N as N`, while the module does not itself define N ("defines" means
#    a top-level def/class/assignment target, including under a top-level
#    if/try -- an if is walked on both branches unconditionally, so a name
#    defined only under `if TYPE_CHECKING: ... else: ...` still counts as
#    defined).
# 2. Consumer side. Any `from M import N` anywhere in a scanned file (not
#    only at module top) where M is a Datrix module that does not define N,
#    and N does not itself resolve to a submodule of M (`from pkg import
#    submodule` is a normal package traversal, never a facade hit).
#
# Module-object shape. A module held as an object (`import a.b as m`,
# `from a import b`) whose attribute is read as `m.attr` or `getattr(m,
# "attr")` while the module does not define `attr` -- a module passed whole as
# a delegation table binds its names at run time, so emptying it by rewriting
# `from M import N` statements alone breaks there, not at import. Not a hit: a
# submodule, a module dunder, a name the module imports from a non-Datrix
# module, `hasattr` / `getattr` with a default (existence probes), and a read
# inside `pytest.raises(AttributeError)`. Tracked per scope.
#
# genDSL-bound names. The kernel resolver looks a `<namespace>.<module>.<name>`
# genDSL reference up as an attribute of the module the namespace reaches, so a
# name imported there only to be bound for genDSL is not a provider-side hit;
# the allowlist is read from the definitions text and fails closed.
#
# Every `[project.entry-points.*]` value shaped "module.path:attr" in a
# discovered package's pyproject.toml is a site too: an attr the module does
# not define is a hit attributed to module.path.
#
# A `from M import N` where M is a dotted path under a Datrix import root
# that resolves to no module on disk at all is ALSO a hit -- once a facade's
# __all__ is emptied and its consumers are rewritten one at a time, this is
# what proves every rewritten import lands on something that actually
# exists, rather than silently accepting any string.
#
# Relative imports (`from .a import X`, `from . import sub`) are resolved to
# their absolute dotted module from the scanned file's own dotted name, on
# both the provider and the consumer side; a file outside every package's
# src/ tree has no dotted name, so its relative imports (which can only
# name sibling files of that tree, never a Datrix module) are not followed.
#
# This is a HARD ZERO with no baseline: any hit fails. Hits are grouped by
# the PROVIDING module -- its own relative file path when it resolves to a
# real file, or (only for the unresolved-import shape, where by definition
# no such file exists) the dotted module path itself.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReexportFacadeHit:
    """One occurrence of a re-export facade, attributed to the PROVIDING
    module.

    ``providing_module`` is the grouping key: the module's own
    relative file path when it resolves to a real file on disk, or -- only
    for an "unresolved" hit, where by definition no such file exists -- the
    dotted module path that failed to resolve. ``providing_module_dotted``
    is the same module's dotted import path when known (always known for
    consumer/entry-point/unresolved hits; known for a provider hit only when
    the scanned file is itself part of a discovered package's ``src/``
    tree), used solely to let ``-FacadeModule`` filter by dotted name.
    """

    providing_module: str
    kind: Literal[
        "provider", "consumer", "module_attribute", "entry_point", "unresolved"
    ]
    name: str
    site_file: Path
    site_line: int
    defining_module: str | None = None
    providing_module_dotted: str | None = None


@dataclass(frozen=True)
class _ResolvedDatrixModule:
    """A policed dotted module path resolved to the real file that defines
    it -- either an ordinary module (``foo/bar.py``) or a package
    (``foo/bar/__init__.py``, ``is_package=True``). A test-tree directory
    with no ``__init__.py`` is a namespace package (``is_namespace=True``):
    ``file_path`` is then the directory itself and it defines no names."""

    file_path: Path
    is_package: bool
    is_namespace: bool = False


_DATRIX_MODULE_ROOT_PREFIX = "datrix"
_TEST_TREE_ROOT = "tests"


def _is_datrix_module_path(dotted_module: str) -> bool:
    """True when *dotted_module*'s root segment looks like a Datrix package
    import root (``datrix_common``, ``datrix_codegen_kernel``, ...) --
    scopes the re-export-facade scan to Datrix's own module graph, excluding
    every third-party and standard-library import."""
    return dotted_module.split(".", 1)[0].startswith(_DATRIX_MODULE_ROOT_PREFIX)


def _resolve_datrix_module(
    dotted_module: str, packages: dict[str, PackageInfo]
) -> _ResolvedDatrixModule | None:
    """Resolve *dotted_module* to the real file that defines it, or
    ``None`` if its root package is not discovered or the path does not
    exist on disk under that package's ``src/`` tree."""
    segments = dotted_module.split(".")
    package_info = packages.get(segments[0])
    if package_info is None:
        return None
    remainder = segments[1:]
    target_dir = package_info.src_dir.joinpath(*remainder)
    if remainder:
        module_file = target_dir.with_suffix(".py")
        if module_file.is_file():
            return _ResolvedDatrixModule(file_path=module_file, is_package=False)
    package_init = target_dir / "__init__.py"
    if package_init.is_file():
        return _ResolvedDatrixModule(file_path=package_init, is_package=True)
    return None


def _is_policed_module_path(dotted_module: str) -> bool:
    """True when *dotted_module* is a Datrix module or a test-tree module
    (``tests.<module>``) -- every module a facade can hide a name behind."""
    return (
        _is_datrix_module_path(dotted_module)
        or dotted_module.split(".", 1)[0] == _TEST_TREE_ROOT
    )


def _owning_package(
    file_path: Path, packages: dict[str, PackageInfo]
) -> PackageInfo | None:
    """The discovered package whose repository directory contains *file_path*."""
    for package_info in packages.values():
        try:
            file_path.relative_to(package_info.root)
        except ValueError:
            continue
        return package_info
    return None


def _resolve_test_tree_module(
    dotted_module: str, owner: PackageInfo
) -> _ResolvedDatrixModule | None:
    """Resolve ``tests.<module>`` against *owner*'s own ``tests/`` tree -- the
    pytest rootdir anchors ``tests`` per package, so the same dotted name
    names a different file in every package."""
    remainder = dotted_module.split(".")[1:]
    target = (owner.root / _TEST_TREE_ROOT).joinpath(*remainder)
    if remainder:
        module_file = target.with_suffix(".py")
        if module_file.is_file():
            return _ResolvedDatrixModule(file_path=module_file, is_package=False)
    package_init = target / "__init__.py"
    if package_init.is_file():
        return _ResolvedDatrixModule(file_path=package_init, is_package=True)
    if target.is_dir():
        return _ResolvedDatrixModule(
            file_path=target, is_package=True, is_namespace=True
        )
    return None


def _resolve_policed_module(
    dotted_module: str, packages: dict[str, PackageInfo], context_file: Path
) -> _ResolvedDatrixModule | None:
    """Resolve a Datrix or test-tree module path. A test-tree path is
    anchored at the package that owns *context_file* (the importing file);
    a file outside every package has no ``tests`` root to resolve against."""
    if dotted_module.split(".", 1)[0] != _TEST_TREE_ROOT:
        return _resolve_datrix_module(dotted_module, packages)
    owner = _owning_package(context_file, packages)
    if owner is None:
        return None
    return _resolve_test_tree_module(dotted_module, owner)


def _is_submodule_member(resolved: _ResolvedDatrixModule, name: str) -> bool:
    """True when *name* is itself an importable submodule/subpackage of the
    resolved package -- a plain package traversal (`from pkg import
    submodule`), never a facade hit."""
    if not resolved.is_package:
        return False
    package_dir = (
        resolved.file_path if resolved.is_namespace else resolved.file_path.parent
    )
    # Python module names are case-sensitive but a Windows/macOS filesystem
    # is not, so `Crypto` would otherwise "exist" as `crypto.py`. Match the
    # directory listing's own spelling instead of probing the path.
    entries = {entry.name for entry in package_dir.iterdir()}
    if f"{name}.py" in entries:
        return True
    return name in entries and (package_dir / name / "__init__.py").is_file()


def _dotted_module_name_for_file(
    file_path: Path, packages: dict[str, PackageInfo]
) -> str | None:
    """The dotted module path a ``src/`` or ``tests/`` file corresponds to,
    for the provider-side shape's ``-FacadeModule`` filter/display name and
    for resolving the file's own relative imports -- ``datrix_x.mod`` for a
    ``src/`` file, ``tests.mod`` for a file in a package's ``tests/`` tree,
    ``None`` for any other file (a ``datrix/scripts/*.py`` utility or a
    package root-level ``conftest.py`` has no importable module identity of
    its own, so it is filtered by its relative file path only)."""
    for package_name, package_info in packages.items():
        try:
            relative = file_path.relative_to(package_info.src_dir)
        except ValueError:
            continue
        parts = list(relative.parts)
        if parts and parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][: -len(".py")]
        return ".".join([package_name, *parts]) if parts else package_name
    return _test_tree_module_name(file_path, packages)


def _test_tree_module_name(
    file_path: Path, packages: dict[str, PackageInfo]
) -> str | None:
    """``tests.<module>`` for a file under a discovered package's ``tests/``
    tree, ``None`` for every other file."""
    owner = _owning_package(file_path, packages)
    if owner is None:
        return None
    try:
        relative = file_path.relative_to(owner.root / _TEST_TREE_ROOT)
    except ValueError:
        return None
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join([_TEST_TREE_ROOT, *parts])


def _absolute_import_module(
    stmt: ast.ImportFrom, file_path: Path, own_dotted: str | None
) -> str | None:
    """The absolute dotted module a ``from ... import`` statement names.

    An absolute import returns its own ``module``. A relative import
    (``level > 0``) is resolved against the scanned file's own dotted name
    *own_dotted* (``from . import sub`` names the file's package itself,
    ``from .a import X`` names ``<package>.a``). Returns ``None`` when the
    statement has no module to resolve to (``from . import x`` in a file
    with no dotted name -- a file outside every package's ``src/`` tree can
    only name its own siblings, never a Datrix module).

    Raises:
        ValueError: A relative import climbs above the file's top-level
            package, which Python itself rejects at import time.
    """
    if stmt.level == 0:
        return stmt.module
    if own_dotted is None:
        return None
    own_parts = own_dotted.split(".")
    package_parts = own_parts if file_path.name == "__init__.py" else own_parts[:-1]
    ascend = stmt.level - 1
    if ascend >= len(package_parts):
        raise ValueError(
            f"{file_path}:{stmt.lineno}: relative import with level {stmt.level} climbs "
            f"above the top-level package of {own_dotted!r}; use an import that stays "
            f"inside the package, or the absolute module path."
        )
    base_parts = package_parts[: len(package_parts) - ascend]
    module_parts = stmt.module.split(".") if stmt.module else []
    return ".".join([*base_parts, *module_parts])


def _assignment_target_names(target: ast.expr) -> set[str]:
    """Every ``Name`` id bound by an assignment target, including nested
    tuple/list/starred unpacking."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_assignment_target_names(elt))
        return names
    if isinstance(target, ast.Starred):
        return _assignment_target_names(target.value)
    return set()


def _collect_top_level_defined_names(body: list[ast.stmt]) -> set[str]:
    """Every name *body* DEFINES at its own top level: a ``def``/``class``,
    or an assignment target -- including under an ``if``/``try`` (both
    branches of every ``if`` are walked unconditionally, which is what makes
    a name defined only under ``if TYPE_CHECKING: ... else: ...`` still
    count as defined, with no special-casing of that one condition)."""
    names: set[str] = set()
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                names.update(_assignment_target_names(target))
        elif isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
            names.update(_assignment_target_names(stmt.target))
        elif isinstance(stmt, ast.AugAssign):
            names.update(_assignment_target_names(stmt.target))
        elif isinstance(stmt, ast.If):
            names.update(_collect_top_level_defined_names(stmt.body))
            names.update(_collect_top_level_defined_names(stmt.orelse))
        elif isinstance(stmt, ast.Try):
            names.update(_collect_top_level_defined_names(stmt.body))
            for handler in stmt.handlers:
                names.update(_collect_top_level_defined_names(handler.body))
            names.update(_collect_top_level_defined_names(stmt.orelse))
            names.update(_collect_top_level_defined_names(stmt.finalbody))
    return names


@dataclass(frozen=True)
class _ModuleFacadeInfo:
    """Everything the re-export-facade scan needs about one already-parsed
    module: the names it defines at its own top level, the names listed in
    its own ``__all__``, and every top-level ``from <datrix module> import
    N`` it declares (bound name -> (source module, source name, is a self
    alias), plus the reporting line for each bound name)."""

    defined_names: frozenset[str]
    all_names: frozenset[str]
    datrix_imports: dict[str, tuple[str, str, bool]]
    import_lines: dict[str, int]
    foreign_import_names: frozenset[str] = frozenset()


@functools.lru_cache(maxsize=None)
def _parse_module_source(file_path: Path) -> ast.Module:
    """Parse *file_path* once; every re-export-facade helper below shares
    this single cached parse instead of re-reading the file."""
    source = file_path.read_text(encoding="utf-8-sig")
    return ast.parse(source, filename=str(file_path))


@functools.lru_cache(maxsize=None)
def _analyze_module_file(file_path: Path, own_dotted: str | None) -> _ModuleFacadeInfo:
    """Compute *file_path*'s ``_ModuleFacadeInfo`` from its top-level
    statements only -- "defines" and "declares __all__" are both top-level
    facts by the check's own definition. *own_dotted* is the file's own
    dotted module name (``None`` outside every package's ``src/`` tree); it
    resolves the file's relative imports to absolute modules."""
    tree = _parse_module_source(file_path)
    defined_names = frozenset(_collect_top_level_defined_names(tree.body))
    all_names: set[str] = set()
    datrix_imports: dict[str, tuple[str, str, bool]] = {}
    import_lines: dict[str, int] = {}
    foreign_import_names: set[str] = set()
    for stmt in tree.body:
        source_module = (
            _absolute_import_module(stmt, file_path, own_dotted)
            if isinstance(stmt, ast.ImportFrom)
            else None
        )
        if (
            isinstance(stmt, ast.ImportFrom)
            and source_module is not None
            and _is_policed_module_path(source_module)
        ):
            for alias in stmt.names:
                bound = alias.asname or alias.name
                datrix_imports[bound] = (
                    source_module,
                    alias.name,
                    alias.asname == alias.name,
                )
                import_lines[bound] = alias.lineno
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            foreign_import_names.update(
                alias.asname or alias.name.split(".", 1)[0] for alias in stmt.names
            )
        elif isinstance(stmt, (ast.Assign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            targets_all = any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in targets
            )
            if targets_all and isinstance(stmt.value, (ast.List, ast.Tuple)):
                for elt in stmt.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        all_names.add(elt.value)
    return _ModuleFacadeInfo(
        defined_names=defined_names,
        all_names=frozenset(all_names),
        datrix_imports=datrix_imports,
        import_lines=import_lines,
        foreign_import_names=frozenset(foreign_import_names),
    )


def _resolve_defining_module(
    module_dotted: str,
    name: str,
    packages: dict[str, PackageInfo],
    context_file: Path,
    _seen: frozenset[Path] = frozenset(),
) -> str | None:
    """Follow *module_dotted*'s own re-export chain for *name* to the module
    that actually defines it, for the ``-ShowFiles`` worklist report only --
    never used for baseline attribution. *context_file* is the file whose
    import named *module_dotted* (it anchors a ``tests.<module>`` path).
    Returns ``None`` on a cycle, an unresolved link in the chain, or a dead
    end (the module neither defines the name nor re-exports it further)."""
    resolved = _resolve_policed_module(module_dotted, packages, context_file)
    if resolved is None or resolved.is_namespace or resolved.file_path in _seen:
        return None
    info = _analyze_module_file(resolved.file_path, module_dotted)
    if name in info.defined_names:
        return module_dotted
    next_hop = info.datrix_imports.get(name)
    if next_hop is None:
        return None
    next_module, next_name, _self_aliased = next_hop
    return _resolve_defining_module(
        next_module,
        next_name,
        packages,
        resolved.file_path,
        _seen | {resolved.file_path},
    )


def _analyze_scanned_file(
    file_path: Path, packages: dict[str, PackageInfo]
) -> _ModuleFacadeInfo:
    """``_analyze_module_file`` for a file of the scan scope, with the file's
    own dotted module name supplied so its relative imports resolve."""
    return _analyze_module_file(
        file_path, _dotted_module_name_for_file(file_path, packages)
    )


def _reexport_facade_scan_files(
    packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[Path]:
    """Every ``.py`` file the re-export-facade check scans: every discovered
    package's ``src/`` and ``tests/`` trees plus its root-level ``*.py``
    files (``conftest.py`` and the like), this repo's own
    ``datrix/scripts/`` tree, and ``datrix/claude-config/.claude/hooks/`` (a
    facade emptied later would otherwise break a script or a hook silently,
    with no static warning from this check). Prints an informational note
    when the hooks tree exists but nothing under it imports a Datrix
    module -- confirmed by scanning it, never assumed."""
    files: list[Path] = []
    for package_info in packages.values():
        files.extend(sorted(package_info.src_dir.rglob("*.py")))
        files.extend(sorted(package_info.root.glob("*.py")))
        tests_dir = package_info.root / "tests"
        if tests_dir.is_dir():
            files.extend(sorted(tests_dir.rglob("*.py")))
    scripts_dir = monorepo_root / "datrix" / "scripts"
    if scripts_dir.is_dir():
        files.extend(sorted(scripts_dir.rglob("*.py")))
    hooks_dir = monorepo_root / "datrix" / "claude-config" / ".claude" / "hooks"
    if hooks_dir.is_dir():
        hook_files = sorted(hooks_dir.rglob("*.py"))
        files.extend(hook_files)
        hooks_import_datrix = any(
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.level == 0
            and _is_datrix_module_path(node.module)
            for hook_file in hook_files
            for node in ast.walk(_parse_module_source(hook_file))
        )
        if hook_files and not hooks_import_datrix:
            print(
                f"Note: {len(hook_files)} file(s) under "
                f"{hooks_dir.relative_to(monorepo_root)} were scanned for "
                f"re-export facades; none imports a Datrix module.",
                file=sys.stderr,
            )
    return files


def _reexport_facade_provider_hits(
    py_file: Path,
    info: _ModuleFacadeInfo,
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    gendsl_bound: frozenset[tuple[Path, str]] = frozenset(),
) -> list[ReexportFacadeHit]:
    """The provider-side shape for one already-analyzed file: every bound
    name it imports from a Datrix or test-tree module and passes through --
    via a self-aliased import or its own ``__all__`` -- without defining it.
    A bound name that is itself a submodule of the module it is imported from
    (``from . import sub``) is a package traversal, never a facade, and a
    name in *gendsl_bound* (see ``_gendsl_bound_names``) is bound for a
    genDSL ``<namespace>.<module>.<name>`` reference, not re-exported."""
    hits: list[ReexportFacadeHit] = []
    providing_module = str(py_file.relative_to(monorepo_root)).replace("\\", "/")
    providing_module_dotted = _dotted_module_name_for_file(py_file, packages)
    for bound_name, (source_module, source_name, self_aliased) in sorted(
        info.datrix_imports.items()
    ):
        if bound_name in info.defined_names:
            continue
        if not (self_aliased or bound_name in info.all_names):
            continue
        if (py_file, bound_name) in gendsl_bound:
            continue
        resolved_source = _resolve_policed_module(source_module, packages, py_file)
        if resolved_source is not None and _is_submodule_member(
            resolved_source, source_name
        ):
            continue
        hits.append(
            ReexportFacadeHit(
                providing_module=providing_module,
                kind="provider",
                name=bound_name,
                site_file=py_file,
                site_line=info.import_lines[bound_name],
                providing_module_dotted=providing_module_dotted,
            )
        )
    return hits


def _reexport_facade_consumer_hits(
    py_file: Path, packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[ReexportFacadeHit]:
    """The consumer-side and unresolved-import shapes for one file: every
    ``from M import N`` ANYWHERE in the file (module top or nested -- unlike
    the provider-side shape, this one is not limited to module top), for
    every M that is a Datrix module or a test-tree module (``tests.<m>``,
    resolved against the importing file's own package). A relative import is
    resolved to its absolute M from the file's own dotted name first."""
    hits: list[ReexportFacadeHit] = []
    tree = _parse_module_source(py_file)
    own_dotted = _dotted_module_name_for_file(py_file, packages)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        node_module = _absolute_import_module(node, py_file, own_dotted)
        if node_module is None or not _is_policed_module_path(node_module):
            continue
        if (
            node_module.split(".", 1)[0] == _TEST_TREE_ROOT
            and _owning_package(py_file, packages) is None
        ):
            continue
        resolved = _resolve_policed_module(node_module, packages, py_file)
        for alias in node.names:
            if alias.name == "*":
                continue
            site_line = alias.lineno
            if resolved is None or (
                resolved.is_namespace
                and not _is_submodule_member(resolved, alias.name)
            ):
                hits.append(
                    ReexportFacadeHit(
                        providing_module=node_module,
                        kind="unresolved",
                        name=alias.name,
                        site_file=py_file,
                        site_line=site_line,
                        providing_module_dotted=node_module,
                    )
                )
                continue
            if resolved.is_namespace:
                continue
            info = _analyze_module_file(resolved.file_path, node_module)
            if alias.name in info.defined_names:
                continue
            if _is_submodule_member(resolved, alias.name):
                continue
            providing_module = str(
                resolved.file_path.relative_to(monorepo_root)
            ).replace("\\", "/")
            defining_module = _resolve_defining_module(
                node_module, alias.name, packages, py_file
            )
            hits.append(
                ReexportFacadeHit(
                    providing_module=providing_module,
                    kind="consumer",
                    name=alias.name,
                    site_file=py_file,
                    site_line=site_line,
                    defining_module=defining_module,
                    providing_module_dotted=node_module,
                )
            )
    return hits


#: ``getattr(m, "name")`` with no default raises when ``name`` is gone, so it
#: is a hard dependency on the attribute. ``hasattr`` and ``getattr`` with a
#: default are existence probes -- the tests that assert a name was REMOVED are
#: written with them -- and are not read as a use.
_MODULE_ATTRIBUTE_GETTER = "getattr"


def _dotted_chain(node: ast.expr) -> str | None:
    """``a.b.c`` for a ``Name``/``Attribute`` chain, ``None`` for any other
    expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_chain(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


_COMPREHENSION_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED_SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    *_COMPREHENSION_NODES,
)


def _scope_roots(scope: ast.AST) -> list[ast.AST]:
    """The child nodes a scope's own code is made of."""
    if isinstance(scope, ast.Lambda):
        return [scope.body]
    if isinstance(scope, ast.DictComp):
        return [scope.key, scope.value, *scope.generators]
    if isinstance(scope, _COMPREHENSION_NODES):
        return [scope.elt, *scope.generators]
    return list(getattr(scope, "body"))


def _own_scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """Every node that belongs to *scope* itself: its own code, and each
    nested scope's node (where that scope's name is bound) but not that
    scope's interior. A comprehension's first iterable is evaluated in the
    enclosing scope, so it belongs to the enclosing scope."""
    nodes: list[ast.AST] = []
    stack = list(reversed(_scope_roots(scope)))
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(node, _COMPREHENSION_NODES):
            stack.append(node.generators[0].iter)
        if isinstance(node, _NESTED_SCOPE_NODES):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return nodes


def _scope_rebound_names(scope: ast.AST, own_nodes: list[ast.AST]) -> set[str]:
    """Every name *scope* binds by something other than an import: a
    parameter, an assignment/``for``/``with``/comprehension target, a
    ``def``/``class`` or an ``except ... as`` name."""
    names: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = scope.args
        for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
            names.add(arg.arg)
        for special in (arguments.vararg, arguments.kwarg):
            if special is not None:
                names.add(special.arg)
    for node in own_nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            names.add(node.name)
    return names


def _scope_import_aliases(
    own_nodes: list[ast.AST],
    py_file: Path,
    own_dotted: str | None,
    packages: dict[str, PackageInfo],
) -> tuple[dict[str, str], set[str]]:
    """The module objects one scope's imports bind, and every name those
    imports bind at all. The mapping holds each expression a scope uses to
    hold a policed MODULE OBJECT -> that module's absolute dotted path:
    ``import a.b as m`` (``m``), ``import a.b.c`` (``a``, ``a.b`` and
    ``a.b.c``, each a real module) and ``from a import b`` where ``b`` is a
    submodule of ``a`` (``b``)."""
    aliases: dict[str, str] = {}
    bound: set[str] = set()
    for node in own_nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".", 1)[0])
                if not _is_policed_module_path(alias.name):
                    continue
                if alias.asname:
                    aliases[alias.asname] = alias.name
                    continue
                segments = alias.name.split(".")
                for depth in range(1, len(segments) + 1):
                    prefix = ".".join(segments[:depth])
                    aliases[prefix] = prefix
        elif isinstance(node, ast.ImportFrom):
            bound.update(
                alias.asname or alias.name for alias in node.names if alias.name != "*"
            )
            node_module = _absolute_import_module(node, py_file, own_dotted)
            if node_module is None or not _is_policed_module_path(node_module):
                continue
            resolved = _resolve_policed_module(node_module, packages, py_file)
            if resolved is None:
                continue
            for alias in node.names:
                if alias.name != "*" and _is_submodule_member(resolved, alias.name):
                    aliases[alias.asname or alias.name] = f"{node_module}.{alias.name}"
    return aliases, bound


def _is_attribute_error_raises(item: ast.withitem) -> bool:
    """True for a ``with pytest.raises(AttributeError, ...)`` item."""
    call = item.context_expr
    if not isinstance(call, ast.Call) or not call.args:
        return False
    if _dotted_chain(call.func) not in ("raises", "pytest.raises"):
        return False
    expected = call.args[0]
    candidates = expected.elts if isinstance(expected, ast.Tuple) else [expected]
    return any(_dotted_chain(c) == "AttributeError" for c in candidates)


def _absence_asserted_node_ids(tree: ast.Module) -> frozenset[int]:
    """The ids of every node inside a ``with pytest.raises(AttributeError)``
    body: a read there asserts that the attribute is GONE, which is the
    opposite of depending on it."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            _is_attribute_error_raises(item) for item in node.items
        ):
            for stmt in node.body:
                ids.update(id(inner) for inner in ast.walk(stmt))
    return frozenset(ids)


def _scope_attribute_uses(
    own_nodes: list[ast.AST], aliases: dict[str, str], absence_asserted: frozenset[int]
) -> set[tuple[str, str, int]]:
    """Every ``(module dotted path, attribute, line)`` the scope reads off a
    module object in *aliases*: ``m.attr`` in load position, and
    ``getattr(m, "attr")`` with a literal name and no default. A read inside
    a ``pytest.raises(AttributeError)`` body (*absence_asserted*) is skipped."""
    uses: set[tuple[str, str, int]] = set()
    for node in own_nodes:
        if id(node) in absence_asserted:
            continue
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            chain = _dotted_chain(node.value)
            if chain in aliases:
                uses.add((aliases[chain], node.attr, node.lineno))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == _MODULE_ATTRIBUTE_GETTER
            and len(node.args) == 2
            and not node.keywords
        ):
            chain = _dotted_chain(node.args[0])
            attr_arg = node.args[1]
            if (
                chain in aliases
                and isinstance(attr_arg, ast.Constant)
                and isinstance(attr_arg.value, str)
            ):
                uses.add((aliases[chain], attr_arg.value, node.lineno))
    return uses


def _module_attribute_uses(
    tree: ast.Module,
    py_file: Path,
    own_dotted: str | None,
    packages: dict[str, PackageInfo],
) -> list[tuple[str, str, int]]:
    """Every attribute use of a policed module object in the file, resolved
    scope by scope: a name is a module object only where an import in that
    scope (or an enclosing one) binds it and nothing in the scope rebinds it
    some other way. A name a scope both imports and rebinds, or rebinds
    where an enclosing scope imports it, is not tracked there -- which
    binding a use reads is flow-dependent, and guessing would report code
    that never touches the module."""
    uses: set[tuple[str, str, int]] = set()
    absence_asserted = _absence_asserted_node_ids(tree)
    pending: list[tuple[ast.AST, dict[str, str]]] = [(tree, {})]
    while pending:
        scope, inherited = pending.pop()
        own_nodes = _own_scope_nodes(scope)
        import_aliases, import_bound = _scope_import_aliases(
            own_nodes, py_file, own_dotted, packages
        )
        rebound = _scope_rebound_names(scope, own_nodes)
        shadowed = rebound | import_bound
        aliases = {
            key: module
            for key, module in inherited.items()
            if key.split(".", 1)[0] not in shadowed
        }
        aliases.update(
            (key, module)
            for key, module in import_aliases.items()
            if key.split(".", 1)[0] not in rebound
        )
        if aliases:
            uses.update(_scope_attribute_uses(own_nodes, aliases, absence_asserted))
        pending.extend(
            (node, aliases) for node in own_nodes if isinstance(node, _NESTED_SCOPE_NODES)
        )
    return sorted(uses)


def _reexport_facade_module_attribute_hits(
    py_file: Path, packages: dict[str, PackageInfo], monorepo_root: Path
) -> list[ReexportFacadeHit]:
    """The module-object shape for one file: a policed module held as an
    object (``import a.b as m``, ``from a import b``) whose attribute is read
    with ``m.attr`` or ``getattr(m, "attr")`` while the module
    does not itself define ``attr`` (and ``attr`` is not one of its
    submodules or a module dunder). A module passed whole as a delegation
    table, or probed by ``getattr``, binds its attributes at run time, so
    emptying it by rewriting ``from M import N`` statements alone breaks at
    run time, not at import."""
    tree = _parse_module_source(py_file)
    own_dotted = _dotted_module_name_for_file(py_file, packages)
    hits: list[ReexportFacadeHit] = []
    for module_dotted, attr, line in _module_attribute_uses(
        tree, py_file, own_dotted, packages
    ):
        if attr.startswith("__") and attr.endswith("__"):
            continue
        resolved = _resolve_policed_module(module_dotted, packages, py_file)
        if resolved is None or resolved.is_namespace:
            continue
        info = _analyze_module_file(resolved.file_path, module_dotted)
        if (
            attr in info.defined_names
            or attr in info.foreign_import_names
            or _is_submodule_member(resolved, attr)
        ):
            continue
        hits.append(
            ReexportFacadeHit(
                providing_module=str(
                    resolved.file_path.relative_to(monorepo_root)
                ).replace("\\", "/"),
                kind="module_attribute",
                name=attr,
                site_file=py_file,
                site_line=line,
                defining_module=_resolve_defining_module(
                    module_dotted, attr, packages, py_file
                ),
                providing_module_dotted=module_dotted,
            )
        )
    return hits


#: A genDSL function reference as the definitions text spells it: ``builder
#: <ref>``, ``call <ref>(...)`` or ``from <ref>`` (the ``context T from`` /
#: ``appends X from`` forms), where ``<ref>`` is ``<namespace>.<module>.<name>``.
_GENDSL_REFERENCE_PATTERN = re.compile(
    r"(?<![\w.])(?:builder|call|from)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)"
)

ContextModuleResolver = Callable[[str], str | None]


def _registry_context_module_resolver() -> ContextModuleResolver:
    """Resolve a genDSL ``<namespace>.<module>`` path to its real module path
    through the kernel's own registry -- the single resolver the genDSL
    executor uses -- or ``None`` when no registered namespace prefixes it."""
    from datrix_codegen_kernel.gendsl import target_registry
    from datrix_common.errors.generation import GenerationError

    def resolve(module_path: str) -> str | None:
        try:
            return target_registry.resolve_gendsl_context_module(module_path)
        except GenerationError:
            return None

    return resolve


def _gendsl_bound_names(
    files: list[Path],
    packages: dict[str, PackageInfo],
    resolve_context_module: ContextModuleResolver,
) -> frozenset[tuple[Path, str]]:
    """Every ``(module file, name)`` a genDSL reference in the scanned
    packages' ``src/`` trees resolves to. The kernel genDSL resolver looks a
    ``<namespace>.<module>.<name>`` reference up as an ATTRIBUTE of the
    module the namespace reaches, so a name imported into that module only
    to be bound for genDSL is not a re-export for Python callers.

    The allowlist is read from the definitions text itself (string constants,
    f-string literal parts included). A reference the text spells in a way
    this pattern does not match is simply not exempted, so the scan fails
    closed: an under-read allowlist reports a hit, never hides one."""
    src_dirs = [info.src_dir for info in packages.values()]
    resolved_modules: dict[str, _ResolvedDatrixModule | None] = {}
    bound: set[tuple[Path, str]] = set()
    for py_file in files:
        if not any(src_dir in py_file.parents for src_dir in src_dirs):
            continue
        try:
            tree = _parse_module_source(py_file)
        except (SyntaxError, OSError, UnicodeDecodeError):
            # Not skipped for good: ``scan_reexport_facades`` parses every
            # scanned file next and aborts the run, naming the file.
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for match in _GENDSL_REFERENCE_PATTERN.finditer(node.value):
                module_path, _, name = match.group(1).rpartition(".")
                if not module_path:
                    continue
                if module_path not in resolved_modules:
                    actual = resolve_context_module(module_path)
                    resolved_modules[module_path] = (
                        None if actual is None else _resolve_datrix_module(actual, packages)
                    )
                target = resolved_modules[module_path]
                if target is not None and not target.is_namespace:
                    bound.add((target.file_path, name))
    return frozenset(bound)


def _reexport_facade_entry_point_targets(manifest: Path) -> list[tuple[str, str, str]]:
    """Every ``(group, entry name, "module.path:attr")`` triple a package's
    ``pyproject.toml`` declares under ``[project.entry-points.*]``."""
    with manifest.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project")
    groups = project.get("entry-points", {}) if isinstance(project, dict) else {}
    if not isinstance(groups, dict):
        return []
    targets: list[tuple[str, str, str]] = []
    for group, entries in groups.items():
        if not isinstance(entries, dict):
            continue
        for entry_name, reference in entries.items():
            if isinstance(reference, str) and ":" in reference:
                targets.append((group, entry_name, reference))
    return targets


def _reexport_facade_entry_point_line(manifest_lines: list[str], reference: str) -> int:
    """The 1-based line in *manifest_lines* naming *reference* verbatim, or
    line 1 if the exact string cannot be found (never fails the scan over a
    reporting nicety)."""
    for line_number, line in enumerate(manifest_lines, start=1):
        if reference in line:
            return line_number
    return 1


def scan_reexport_facades(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    context_module_resolver: ContextModuleResolver | None = None,
) -> dict[str, list[ReexportFacadeHit]]:
    """Scan every re-export-facade shape -- provider side, consumer side,
    module-object attribute use, pyproject.toml entry points, and unresolved
    imports -- across the whole scan scope, and group every hit by its
    PROVIDING module.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        context_module_resolver: Resolves a genDSL ``<namespace>.<module>``
            path to its real module path, or ``None`` for an unregistered
            namespace; defaults to the kernel registry's resolver.

    Returns:
        Mapping of providing-module key (see ``ReexportFacadeHit``) -> hits
        attributed to it (keys with zero hits omitted).
    """
    results: dict[str, list[ReexportFacadeHit]] = {}

    def _add(hit: ReexportFacadeHit) -> None:
        results.setdefault(hit.providing_module, []).append(hit)

    scan_files = _reexport_facade_scan_files(packages, monorepo_root)
    gendsl_bound = _gendsl_bound_names(
        scan_files,
        packages,
        context_module_resolver or _registry_context_module_resolver(),
    )
    for py_file in scan_files:
        try:
            info = _analyze_scanned_file(py_file, packages)
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

        for hit in _reexport_facade_provider_hits(
            py_file, info, packages, monorepo_root, gendsl_bound
        ):
            _add(hit)
        for hit in _reexport_facade_consumer_hits(py_file, packages, monorepo_root):
            _add(hit)
        for hit in _reexport_facade_module_attribute_hits(
            py_file, packages, monorepo_root
        ):
            _add(hit)

    for package_name, package_info in sorted(packages.items()):
        manifest = package_info.root / "pyproject.toml"
        if not manifest.is_file():
            continue
        targets = _reexport_facade_entry_point_targets(manifest)
        if not targets:
            continue
        try:
            manifest_lines = manifest.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            rel_path = manifest.relative_to(monorepo_root)
            print(
                f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                f"cannot be read would escape this scan; resolve the read error.",
                file=sys.stderr,
            )
            sys.exit(2)
        for _group, _entry_name, reference in targets:
            module_path, _, attr = reference.partition(":")
            module_path = module_path.strip()
            attr = attr.strip()
            if not module_path or not attr or not _is_datrix_module_path(module_path):
                continue
            site_line = _reexport_facade_entry_point_line(manifest_lines, reference)
            resolved = _resolve_datrix_module(module_path, packages)
            if resolved is not None:
                defined = _analyze_module_file(
                    resolved.file_path, module_path
                ).defined_names
                if attr in defined:
                    continue
                providing_module = str(
                    resolved.file_path.relative_to(monorepo_root)
                ).replace("\\", "/")
            else:
                providing_module = module_path
            _add(
                ReexportFacadeHit(
                    providing_module=providing_module,
                    kind="entry_point",
                    name=attr,
                    site_file=manifest,
                    site_line=site_line,
                    providing_module_dotted=module_path,
                )
            )

    return results


def check_reexport_facades(
    hits_by_module: dict[str, list[ReexportFacadeHit]], monorepo_root: Path
) -> list[str]:
    """Return one message per re-export-facade hit -- ANY hit fails.

    No baseline: a name with a second import path is removed, never
    grandfathered, so a new facade fails outright. Returns an empty list only
    when ``hits_by_module`` holds no hit at all.

    Args:
        hits_by_module: Output of ``scan_reexport_facades``.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        One failure message per hit, sorted by providing module, then site
        file, then line.
    """
    return format_reexport_facade_worklist(hits_by_module, monorepo_root)


def format_reexport_facade_worklist(
    hits_by_module: dict[str, list[ReexportFacadeHit]],
    monorepo_root: Path,
    *,
    facade_modules: frozenset[str] = frozenset(),
    consumer_packages: frozenset[str] = frozenset(),
) -> list[str]:
    """The per-site worklist report for ``-ShowFiles``: one line per hit,
    filtered by ``-FacadeModule``/``-ConsumerPackage`` when given.

    Args:
        hits_by_module: The scan result, as returned by
            ``scan_reexport_facades``.
        monorepo_root: Monorepo root, for the site file's relative path.
        facade_modules: If non-empty, keep only hits whose providing module
            matches one of these -- either the grouping-key form (a relative
            file path, or a dotted path for an unresolved entry) or the
            dotted form (``providing_module_dotted``).
        consumer_packages: If non-empty, keep only hits whose site file
            lives under one of these repo directory names.

    Returns:
        One formatted line per surviving hit, sorted by providing module
        then site file then line.
    """
    lines: list[str] = []
    for providing_module in sorted(hits_by_module):
        for hit in sorted(
            hits_by_module[providing_module], key=lambda h: (str(h.site_file), h.site_line)
        ):
            if facade_modules and not (
                providing_module in facade_modules
                or (
                    hit.providing_module_dotted is not None
                    and hit.providing_module_dotted in facade_modules
                )
            ):
                continue
            site_rel = str(hit.site_file.relative_to(monorepo_root)).replace("\\", "/")
            if consumer_packages and site_rel.split("/", 1)[0] not in consumer_packages:
                continue
            defining_suffix = (
                f" (defined by {hit.defining_module})"
                if hit.kind == "consumer" and hit.defining_module
                else ""
            )
            lines.append(
                f"{providing_module} [{hit.kind}] {site_rel}:{hit.site_line} "
                f"{hit.name}{defining_suffix}"
            )
    return lines


def load_allowlist(allowlist_path: Path) -> list[AllowlistEntry]:
    """Load allowlist entries from TOML file.

    Args:
        allowlist_path: Path to allowlist TOML file

    Returns:
        List of allowlist entries (empty if file doesn't exist)
    """
    if not allowlist_path.exists():
        return []

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for allowlist support.",
                file=sys.stderr,
            )
            return []

    with allowlist_path.open("rb") as f:
        data = tomllib.load(f)

    entries: list[AllowlistEntry] = []
    for entry in data.get("allow", []):
        if not isinstance(entry, dict):
            continue

        file_pattern = entry.get("file", "")
        import_prefix = entry.get("import", "")
        issue_url = entry.get("issue", "")

        if file_pattern and import_prefix and issue_url:
            entries.append(
                AllowlistEntry(
                    file_pattern=file_pattern,
                    import_prefix=import_prefix,
                    issue_url=issue_url,
                )
            )

    return entries


def is_allowlisted(
    violation: Violation, allowlist: list[AllowlistEntry], monorepo_root: Path
) -> bool:
    """Check if a violation is allowlisted.

    Args:
        violation: The violation to check
        allowlist: List of allowlist entries
        monorepo_root: Monorepo root for relative path matching

    Returns:
        True if the violation is allowlisted, False otherwise
    """
    # Normalize to forward slashes for cross-platform matching
    rel_path = str(violation.file_path.relative_to(monorepo_root)).replace("\\", "/")

    for entry in allowlist:
        # Normalize allowlist pattern to forward slashes too
        pattern = entry.file_pattern.replace("\\", "/")
        # Simple substring matching for file patterns
        if pattern in rel_path and violation.imported_module.startswith(
            entry.import_prefix
        ):
            return True

    return False


def format_violation(violation: Violation, monorepo_root: Path) -> str:
    """Format a violation for output.

    Args:
        violation: The violation to format
        monorepo_root: Monorepo root for relative path calculation

    Returns:
        Formatted violation string
    """
    rel_path = violation.file_path.relative_to(monorepo_root)
    # Use forward slashes for consistency
    rel_path_str = str(rel_path).replace("\\", "/")

    return (
        f"{rel_path_str}:{violation.line_number}\n"
        f"  forbidden import: {violation.imported_module}\n"
        f"  rule: {violation.source_package} must not import {violation.forbidden_prefix}"
    )




# ---------------------------------------------------------------------------
# Self-Test (--self-test)
#
# Proves the rule model, the AST scanners, and the ratchet comparators are
# non-vacuous: every check below is exercised against both a known-good and a
# known-bad case, and the CLI mutation proof plants a real regression in an
# isolated fixture and proves detection + clearing on revert. Runs
# automatically as step 1 of every normal invocation (see main()); can also
# be run standalone via --self-test. Real files are written under
# D:\datrix\.tmp\ per this project's temp-file policy -- never
# unittest.mock/SimpleNamespace.
# ---------------------------------------------------------------------------

_SELF_TEST_SCRATCH_ROOT = Path("D:/datrix/.tmp/check_import_boundaries_selftest")

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _step(message: str) -> None:
    print(f"\n{_CYAN}=== {message}{_RESET}")


def _check(label: str, condition: bool) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    if condition:
        print(f"{_GREEN}[OK]{_RESET} {label}")
    else:
        print(f"{_RED}[FAIL]{_RESET} {label}")
    return condition


def _rule_forbids(
    rules: dict[str, BoundaryRule],
    source_package: str,
    imported_module: str,
) -> bool:
    """True if any of source_package's forbidden_prefixes flags imported_module.

    The same ``allowed_subtrees`` applies whether the import lives in src/,
    tests/, fixtures/, or helpers/ -- there is no test-only carve-out.
    """
    rule = rules[source_package]
    return any(
        is_forbidden_import(source_package, imported_module, prefix, rule.allowed_subtrees)
        for prefix in rule.forbidden_prefixes
    )


def _real_repo_rules() -> tuple[GeneratorTaxonomy, dict[str, BoundaryRule]]:
    """The taxonomy discovered from THIS monorepo's manifests, and its rules.

    The rule-model self-tests (1-4) assert over the real repository, so they
    resolve it the same way main() does for a no-``--base-dir`` run.
    """
    taxonomy = discover_generator_taxonomy(WORKSPACE_DIR)
    return taxonomy, build_boundary_rules(taxonomy)


#: Formerly carved out of datrix_codegen_common for platforms, SQL and
#: component; now in the kernel. Each must be forbidden in src/ AND tests/.
_FORMER_CARVE_OUT_MODULES: tuple[str, ...] = (
    "datrix_codegen_common.gendsl",
    "datrix_codegen_common.gendsl.compiler",
    "datrix_codegen_common.dashboards.builder",
    "datrix_codegen_common.algorithms.serverless",
    "datrix_codegen_common.context_models.serverless",
    "datrix_codegen_common.context_models.migration",
    "datrix_codegen_common.orchestration.migration_adapter",
    "datrix_codegen_common.enums",
    "datrix_codegen_common.platform.runtime",
    "datrix_codegen_common.pooling.contract",
    "datrix_codegen_common.secrets.manifest",
    "datrix_codegen_common.seed.config_seed_plan",
    "datrix_codegen_common.parity.domain_declaration",
)
#: The kernel home of the same facts: never forbidden to any target.
_KERNEL_TARGET_MODULES: tuple[str, ...] = (
    "datrix_codegen_kernel.gendsl.compiler",
    "datrix_codegen_kernel.dashboards.builder",
    "datrix_codegen_kernel.algorithms.serverless",
    "datrix_codegen_kernel.context_models.migration",
    "datrix_codegen_kernel.orchestration.migration_adapter",
    "datrix_codegen_kernel.enums",
    "datrix_codegen_kernel.platform.runtime",
    "datrix_codegen_kernel.pooling.contract",
    "datrix_codegen_kernel.parity.domain_declaration",
    "datrix_codegen_kernel.generation.gendsl_ir",
)


def _kernel_consumer_packages(taxonomy: GeneratorTaxonomy) -> tuple[str, ...]:
    """Every package that depends on the kernel and never on the language layer."""
    return (*taxonomy.platform_packages, "datrix_codegen_sql", "datrix_codegen_component")


def _self_test_no_testkit_carve_out(
    taxonomy: GeneratorTaxonomy, rules: dict[str, BoundaryRule]
) -> bool:
    """Platforms, SQL and component forbid datrix_codegen_common in tests/
    exactly as in src/ -- the test-only carve-out is gone, not merely absent
    from allowed_subtrees. The derived datrix_testing rule forbids
    datrix_codegen_common too (already true via its datrix_codegen_ wildcard
    prefix -- this asserts the invariant explicitly rather than leaving it
    implicit), and a real plant/observe/revert CLI proof shows a planted
    testkit import in a platform's test tree is reported by the default
    (unratcheted) boundary scan."""
    _step(
        "Self-test 1/24: platforms, SQL and component forbid "
        "datrix_codegen_common in tests/ exactly as in src/"
    )
    ok = True

    for source in _kernel_consumer_packages(taxonomy):
        rule = rules[source]
        ok &= _check(
            f"{source} carries no allowed_subtrees",
            rule.allowed_subtrees == frozenset(),
        )
        ok &= _check(
            f"{source} forbids datrix_codegen_common",
            _rule_forbids(rules, source, "datrix_codegen_common"),
        )
        for imported in _FORMER_CARVE_OUT_MODULES:
            ok &= _check(
                f"former carve-out forbidden: {source} -> {imported}",
                _rule_forbids(rules, source, imported),
            )
        for imported in _KERNEL_TARGET_MODULES:
            ok &= _check(
                f"kernel module NOT forbidden: {source} -> {imported}",
                not _rule_forbids(rules, source, imported),
            )
        ok &= _check(
            f"conformance testkit forbidden -- no carve-out: {source} -> "
            "datrix_codegen_common.testkit.gates",
            _rule_forbids(rules, source, "datrix_codegen_common.testkit.gates"),
        )
        ok &= _check(
            "a named former-carve-out module is forbidden: "
            f"{source} -> datrix_codegen_common.testkit.gates.dispatch_ladder",
            _rule_forbids(
                rules, source, "datrix_codegen_common.testkit.gates.dispatch_ladder"
            ),
        )

    platform_source = "datrix_codegen_aws"
    for imported in (
        "datrix_codegen_common.transpiler.parity_checker",
        "datrix_codegen_common.context_models.entity",
        "datrix_codegen_common.algorithms.cqrs",
        "datrix_codegen_common.generation.type_resolver",
        "datrix_codegen_python",
        "datrix_codegen_python.generators.api",
        "datrix_codegen_typescript",
    ):
        ok &= _check(
            f"language-layer/language import flagged: {platform_source} -> {imported}",
            _rule_forbids(rules, platform_source, imported),
        )

    ok &= _check(
        "the derived datrix_testing rule forbids datrix_codegen_common "
        "(already true via its datrix_codegen_ wildcard prefix)",
        _rule_forbids(rules, "datrix_testing", "datrix_codegen_common"),
    )

    ok &= _self_test_platform_test_tree_testkit_forbidden()

    return ok


def _self_test_platform_test_tree_testkit_forbidden() -> bool:
    """Real plant/observe/revert CLI proof (the design's specific acceptance
    case): an isolated fixture monorepo with one platform-classified package
    carrying a test file that imports the conformance testkit is reported by
    the default, unratcheted import-boundary scan -- the carve-out that used
    to admit this import from a test tree is gone, so a platform's tests/ is
    held to the same forbidden set as its src/."""
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"no-testkit-carveout-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-aws", "datrix_codegen_aws",
            entry_point_groups={PLATFORMS_ENTRY_POINT_GROUP: {"aws": "AwsPlatform"}},
        )
        package_src = tmp_root / "datrix-codegen-aws" / "src" / "datrix_codegen_aws"
        package_src.mkdir(parents=True, exist_ok=True)
        (package_src / "__init__.py").write_text("", encoding="utf-8")
        tests_dir = tmp_root / "datrix-codegen-aws" / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        test_file = tests_dir / "test_dispatch_ladder.py"

        test_file.write_text(
            "from datrix_codegen_common.testkit.gates.dispatch_ladder import X\n",
            encoding="utf-8",
        )
        violating_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "a planted platform-test testkit import is reported by the default "
            f"scan (no carve-out), got exit {violating_result.returncode}",
            violating_result.returncode == 1,
        )
        combined = violating_result.stdout + violating_result.stderr
        ok &= _check(
            "the failure names datrix_codegen_common and the planted test file",
            "datrix_codegen_common" in combined
            and "test_dispatch_ladder.py" in combined,
        )

        test_file.write_text(
            "def test_noop() -> None:\n    assert True\n", encoding="utf-8"
        )
        fixed_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "removing the testkit import clears the failure, got exit "
            f"{fixed_result.returncode}",
            fixed_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_dotted_precision_and_carveout(rules: dict[str, BoundaryRule]) -> bool:
    """Subtree matching is exact-or-child (not raw prefix), and the one
    surviving carve-out (datrix_testing's kernel allowed_subtrees) never
    leaks to a package that did not opt in."""
    _step("Self-test 2/24: dotted-boundary precision and kernel-carve-out non-leakage")
    ok = True
    platform_source = "datrix_codegen_aws"
    ok &= _check(
        "the retired testkit carve-out leaves both forms forbidden: 'testkit_other' "
        f"and 'testkit.fixtures.fixturelang' -> {platform_source}",
        _rule_forbids(rules, platform_source, "datrix_codegen_common.testkit_other")
        and _rule_forbids(
            rules, platform_source, "datrix_codegen_common.testkit.fixtures.fixturelang"
        ),
    )
    web_source = "datrix_codegen_angular"
    ok &= _check(
        "a forbidden prefix matches a dotted child: angular -> "
        "datrix_codegen_typescript.plugin is forbidden",
        _rule_forbids(rules, web_source, "datrix_codegen_typescript.plugin"),
    )
    ok &= _check(
        "a forbidden prefix never matches a longer sibling name: angular -> "
        "datrix_codegen_typescript_core.transpiler.core is allowed",
        not _rule_forbids(rules, web_source, "datrix_codegen_typescript_core.transpiler.core"),
    )

    ok &= _check(
        "datrix_common's BoundaryRule has empty allowed_subtrees",
        rules["datrix_common"].allowed_subtrees == frozenset(),
    )
    ok &= _check(
        "datrix_common still forbids datrix_codegen_python (no carve-out to leak from)",
        _rule_forbids(rules, "datrix_common", "datrix_codegen_python"),
    )
    ok &= _check(
        "datrix_codegen_common itself still forbids datrix_codegen_python",
        _rule_forbids(rules, "datrix_codegen_common", "datrix_codegen_python"),
    )

    # The generation kernel sits on the core alone: the language layer is
    # forbidden to it, its own modules are not, and the test harness's one
    # admitted generation package is the kernel -- never the language layer.
    ok &= _check(
        "datrix_codegen_kernel forbids the language layer (datrix_codegen_common)",
        _rule_forbids(rules, "datrix_codegen_kernel", "datrix_codegen_common.generation.orchestrator"),
    )
    ok &= _check(
        "datrix_codegen_kernel forbids the semantic layer",
        _rule_forbids(rules, "datrix_codegen_kernel", "datrix_semantic.analyzer"),
    )
    ok &= _check(
        "datrix_codegen_kernel may import its own modules",
        not _rule_forbids(rules, "datrix_codegen_kernel", "datrix_codegen_kernel.generation.generator"),
    )
    ok &= _check(
        "datrix_testing may import datrix_codegen_kernel",
        not _rule_forbids(rules, "datrix_testing", "datrix_codegen_kernel.generation.generator"),
    )
    ok &= _check(
        "datrix_testing's kernel carve-out does not leak to datrix_codegen_kernel_other",
        _rule_forbids(rules, "datrix_testing", "datrix_codegen_kernel_other"),
    )
    ok &= _check(
        "datrix_testing still forbids datrix_codegen_common",
        _rule_forbids(rules, "datrix_testing", "datrix_codegen_common.generation.orchestrator"),
    )

    return ok


def _self_test_sql_and_component_coverage(rules: dict[str, BoundaryRule]) -> bool:
    """The rule table covers datrix_codegen_sql and datrix_codegen_component,
    each enforcing the sibling-language prohibition absolutely."""
    _step("Self-test 3/24: SQL and Component boundary rule coverage")
    ok = True

    ok &= _check(
        "datrix_codegen_sql has a boundary-rule entry",
        "datrix_codegen_sql" in rules,
    )
    for imported in ("datrix_codegen_typescript", "datrix_codegen_python", "datrix_cli"):
        ok &= _check(
            f"SQL sibling-language/CLI import forbidden: {imported}",
            _rule_forbids(rules, "datrix_codegen_sql", imported),
        )
    for imported in (
        "datrix_codegen_kernel.gendsl.compiler",
        "datrix_codegen_kernel.context_models.migration",
        "datrix_codegen_kernel.algorithms.postgresql_fulltext",
    ):
        ok &= _check(
            f"SQL kernel import NOT forbidden: {imported}",
            not _rule_forbids(rules, "datrix_codegen_sql", imported),
        )
    for imported in (
        "datrix_codegen_common.algorithms.postgresql_fulltext",
        "datrix_codegen_common.transpiler.parity_checker",
        "datrix_codegen_common.generation.type_resolver",
    ):
        ok &= _check(
            f"SQL codegen_common import forbidden: {imported}",
            _rule_forbids(rules, "datrix_codegen_sql", imported),
        )

    ok &= _check(
        "datrix_codegen_component has a boundary-rule entry",
        "datrix_codegen_component" in rules,
    )
    for imported in ("datrix_codegen_typescript", "datrix_codegen_python", "datrix_cli"):
        ok &= _check(
            f"Component sibling-language/CLI import forbidden: {imported}",
            _rule_forbids(rules, "datrix_codegen_component", imported),
        )
    for imported in (
        "datrix_codegen_common.gendsl.compiler",
        "datrix_codegen_common.algorithms.nosql_connection",
    ):
        ok &= _check(
            f"Component codegen_common import forbidden: {imported}",
            _rule_forbids(rules, "datrix_codegen_component", imported),
        )
    for imported in (
        "datrix_codegen_kernel.gendsl.compiler",
        "datrix_codegen_kernel.algorithms.nosql_connection",
    ):
        ok &= _check(
            f"Component kernel import NOT forbidden: {imported}",
            not _rule_forbids(rules, "datrix_codegen_component", imported),
        )

    ok &= _self_test_client_target_and_language_core_rules(rules)
    return ok


def _self_test_client_target_and_language_core_rules(rules: dict[str, BoundaryRule]) -> bool:
    """The client targets and the language-core packages each carry a rule.

    A client target carries no carve-out: the web target reaches the
    TypeScript transpiler core and web-client mechanics through the
    language-core package, which no rule forbids it, while the backend
    TypeScript generator stays forbidden whole. A language core imports none
    of its consumers, and no client target imports another."""
    ok = True
    for client_target in ("datrix_codegen_angular", "datrix_codegen_flutter"):
        ok &= _check(f"{client_target} has a boundary-rule entry", client_target in rules)
        ok &= _check(
            f"{client_target} carries no allowed_subtrees carve-out",
            rules[client_target].allowed_subtrees == frozenset(),
        )
    web_target = "datrix_codegen_angular"
    for imported in (
        "datrix_codegen_typescript_core.transpiler.core",
        "datrix_codegen_typescript_core.web_client.source_text",
        "datrix_codegen_typescript_core.profile",
    ):
        ok &= _check(
            f"{web_target} TypeScript language-core import NOT forbidden: {imported}",
            not _rule_forbids(rules, web_target, imported),
        )
    for imported in (
        "datrix_codegen_typescript",
        "datrix_codegen_typescript.generators.entity",
        "datrix_codegen_typescript.language_plugin",
        "datrix_codegen_python",
        "datrix_cli",
    ):
        ok &= _check(
            f"{web_target} backend/sibling import forbidden: {imported}",
            _rule_forbids(rules, web_target, imported),
        )
    ok &= _check(
        "datrix_codegen_flutter admits no TypeScript surface (backend or language core)",
        _rule_forbids(rules, "datrix_codegen_flutter", "datrix_codegen_typescript.plugin")
        and _rule_forbids(
            rules, "datrix_codegen_flutter", "datrix_codegen_typescript_core.web_client.source_text"
        ),
    )
    for core, owner in sorted(LANGUAGE_CORE_PACKAGES.items()):
        ok &= _check(f"language core {core} has a boundary-rule entry", core in rules)
        for imported in (
            f"{owner}.plugin",
            "datrix_codegen_angular.gendsl",
            "datrix_codegen_python",
            "datrix_language.parser",
            "datrix_cli",
        ):
            ok &= _check(
                f"language core {core} cannot import its consumer or a generator: {imported}",
                _rule_forbids(rules, core, imported),
            )
        ok &= _check(
            f"language core {core} may import the language layer",
            not _rule_forbids(rules, core, "datrix_codegen_common.transpiler.profile"),
        )
        ok &= _check(
            f"the language {owner} it serves may import language core {core}",
            not _rule_forbids(rules, owner, f"{core}.transpiler.core"),
        )
        for source in ("datrix_codegen_common", "datrix_codegen_sql", "datrix_codegen_component"):
            ok &= _check(
                f"{source} cannot import language core {core}",
                _rule_forbids(rules, source, f"{core}.profile"),
            )
    for source, imported in (
        ("datrix_codegen_angular", "datrix_codegen_flutter.gendsl"),
        ("datrix_codegen_flutter", "datrix_codegen_angular.gendsl"),
    ):
        ok &= _check(
            f"client target {source} cannot import client target {imported}",
            _rule_forbids(rules, source, imported),
        )
    return ok


#: A cross-target rule model proven over fewer than two members of a class is
#: vacuous (there is no sibling to forbid), so discovery must find at least
#: this many of each class in the real repository.
_MIN_DISCOVERED_PER_CLASS = 2


def _self_test_write_manifest(
    tmp_root: Path,
    dist_name: str,
    import_package: str,
    *,
    entry_point_groups: dict[str, dict[str, str]],
) -> Path:
    """Write a minimal ``pyproject.toml`` for a fixture package.

    Creates ``<tmp_root>/<dist_name>/pyproject.toml`` declaring *dist_name*
    and the given ``[project.entry-points."<group>"]`` tables (each value is
    an object reference rooted at *import_package*). The scanner's taxonomy
    discovery reads exactly this shape.
    """
    package_dir = tmp_root / dist_name
    package_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "[project]",
        f'name = "{dist_name}"',
        'version = "0.0.0"',
        "",
    ]
    for group, entries in entry_point_groups.items():
        lines.append(f'[project.entry-points."{group}"]')
        for entry_name, attribute in entries.items():
            lines.append(f'{entry_name} = "{import_package}.plugin:{attribute}"')
        lines.append("")
    manifest = package_dir / "pyproject.toml"
    manifest.write_text("\n".join(lines), encoding="utf-8")
    return manifest


def _self_test_taxonomy_discovery_fixture() -> bool:
    """Discovery classifies from manifests, folds multi-entry groups, rejects
    a both-classes package, and leaves an entry-point-less package unclassed."""
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"taxonomy-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-lang-a", "datrix_codegen_lang_a",
            entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"lang_a": "LangAPlugin"}},
        )
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-plat-b", "datrix_codegen_plat_b",
            entry_point_groups={
                PLATFORMS_ENTRY_POINT_GROUP: {"plat_b": "PlatB", "plat_b_vm": "PlatBVm"}
            },
        )
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-neither", "datrix_codegen_neither",
            entry_point_groups={"datrix.generators": {"neither": "NeitherGenerator"}},
        )
        taxonomy = discover_generator_taxonomy(tmp_root)
        ok &= _check(
            "a datrix.languages manifest is classified as a language package",
            taxonomy.language_packages == ("datrix_codegen_lang_a",),
        )
        ok &= _check(
            "two datrix.platforms entries in one manifest fold into ONE platform package",
            taxonomy.platform_packages == ("datrix_codegen_plat_b",),
        )
        rules = build_boundary_rules(taxonomy)
        ok &= _check(
            "a manifest registering neither group gets no derived rule",
            "datrix_codegen_neither" not in rules,
        )
        ok &= _check(
            "the derived platform rule forbids the discovered language package",
            _rule_forbids(rules, "datrix_codegen_plat_b", "datrix_codegen_lang_a"),
        )

        _self_test_write_manifest(
            tmp_root, "datrix-codegen-both", "datrix_codegen_both",
            entry_point_groups={
                LANGUAGES_ENTRY_POINT_GROUP: {"both": "BothLang"},
                PLATFORMS_ENTRY_POINT_GROUP: {"both": "BothPlat"},
            },
        )
        try:
            discover_generator_taxonomy(tmp_root)
            both_rejected = False
        except GeneratorTaxonomyError as e:
            both_rejected = "datrix_codegen_both" in str(e)
        ok &= _check(
            "a manifest registering BOTH groups is rejected by name",
            both_rejected,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_platform_to_platform_prohibition(
    taxonomy: GeneratorTaxonomy, rules: dict[str, BoundaryRule]
) -> bool:
    """A platform plugin may never import a SIBLING platform plugin.

    The pre-existing self-tests only ever proved platform -> LANGUAGE imports
    are flagged; the platform -> PLATFORM edge was absent from every rule, so
    an aws -> docker import passed the checker in silence. This check pins the
    prohibition in the rule model for every ordered sibling pair of the
    DISCOVERED platform set, and proves the shared-layer escape route
    (importing the same algorithm from
    ``datrix_codegen_kernel.platform.container_image_supply``) is NOT flagged
    -- otherwise the rule would forbid the correct fix along with the wrong one.

    It also proves discovery itself is non-vacuous: the real repository must
    yield at least two languages and two platforms, and a synthetic fixture
    monorepo must classify exactly as its manifests say.
    """
    _step(
        "Self-test 4/24: taxonomy discovery + platform -> sibling-platform "
        "import prohibition"
    )
    ok = True

    ok &= _check(
        f"discovery finds >= {_MIN_DISCOVERED_PER_CLASS} language packages in the real "
        f"repository, got {list(taxonomy.language_packages)}",
        len(taxonomy.language_packages) >= _MIN_DISCOVERED_PER_CLASS,
    )
    ok &= _check(
        f"discovery finds >= {_MIN_DISCOVERED_PER_CLASS} platform packages in the real "
        f"repository, got {list(taxonomy.platform_packages)}",
        len(taxonomy.platform_packages) >= _MIN_DISCOVERED_PER_CLASS,
    )
    ok &= _self_test_taxonomy_discovery_fixture()

    platforms = taxonomy.platform_packages
    for source in platforms:
        for sibling in _siblings(source, platforms):
            ok &= _check(
                f"sibling platform import forbidden: {source} -> {sibling}",
                _rule_forbids(rules, source, sibling),
            )
            ok &= _check(
                f"sibling platform submodule import forbidden: {source} -> "
                f"{sibling}.generators.infra.docker_generator",
                _rule_forbids(rules, source, f"{sibling}.generators.infra.docker_generator"),
            )

    # The correct home for shared platform logic must stay importable, or the
    # rule above would forbid the fix as well as the defect.
    for source in platforms:
        ok &= _check(
            f"shared container-image-supply layer NOT forbidden: {source} -> "
            "datrix_codegen_kernel.platform.container_image_supply",
            not _rule_forbids(
                rules, source, "datrix_codegen_kernel.platform.container_image_supply"
            ),
        )

    # A platform importing ITSELF is not a sibling import.
    for source in platforms:
        ok &= _check(
            f"self-import not flagged: {source} -> {source}.generators",
            not _rule_forbids(rules, source, f"{source}.generators"),
        )

    return ok


def _self_test_build_platform_fixture_monorepo(
    tmp_root: Path, *, import_sibling: bool
) -> Path:
    """Build a minimal isolated monorepo with a real datrix-codegen-aws package.

    Its one module imports either a SIBLING PLATFORM (docker -- a violation)
    or the kernel's container-image-supply module (the correct, permitted
    edge), so the same fixture proves both directions. Both
    packages carry a manifest registering ``datrix.platforms`` -- that is
    what makes them platforms to the scanner, which discovers the taxonomy
    from manifests rather than from a declared list.
    """
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-aws", "datrix_codegen_aws",
        entry_point_groups={PLATFORMS_ENTRY_POINT_GROUP: {"aws": "AwsPlatform"}},
    )
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-docker", "datrix_codegen_docker",
        entry_point_groups={PLATFORMS_ENTRY_POINT_GROUP: {"docker": "DockerPlatform"}},
    )
    package_src = tmp_root / "datrix-codegen-aws" / "src" / "datrix_codegen_aws"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "deploy_supply_context.py"
    module_path.write_text(
        _self_test_platform_module_source(import_sibling=import_sibling),
        encoding="utf-8",
    )
    return module_path


def _self_test_platform_module_source(*, import_sibling: bool) -> str:
    """Source for the platform fixture module: the violating import, or the fix."""
    if import_sibling:
        import_line = (
            "from datrix_codegen_docker.generators.infra.docker_generator import (\n"
            "    shared_base_image_directory,\n"
            ")"
        )
    else:
        import_line = (
            "from datrix_codegen_kernel.platform.container_image_supply import (\n"
            "    shared_base_image_directory,\n"
            ")"
        )
    return f"{import_line}\n\n\ndef f() -> str:\n    return shared_base_image_directory('x')\n"


def _self_test_run_boundary_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script's plain import-boundary scan against an isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_platform_cli_non_vacuity() -> bool:
    """End-to-end proof the platform -> platform prohibition actually FIRES.

    Plants a real aws -> docker import in a real, isolated fixture monorepo,
    proves the scanner exits 1 and names it, then rewrites the SAME module to
    import the generation kernel instead and proves the failure
    clears (exit 0) -- i.e. the rule flags the defect and permits the fix.
    """
    _step(
        "Self-test 10/24: platform -> platform CLI mutation non-vacuity "
        "(plant a real aws -> docker import, prove detection, prove the shared-layer fix clears it)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"platform-boundary-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_build_platform_fixture_monorepo(
            tmp_root, import_sibling=True
        )

        violating_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "aws -> docker sibling-platform import exits 1, got "
            f"{violating_result.returncode}",
            violating_result.returncode == 1,
        )
        combined = violating_result.stdout + violating_result.stderr
        ok &= _check(
            "failure output names the forbidden imported package (datrix_codegen_docker)",
            "datrix_codegen_docker" in combined,
        )
        ok &= _check(
            "failure output names the violating file (deploy_supply_context.py)",
            "deploy_supply_context.py" in combined,
        )

        module_path.write_text(
            _self_test_platform_module_source(import_sibling=False), encoding="utf-8"
        )
        fixed_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "rewriting the SAME import to the generation kernel clears the "
            f"failure, got exit {fixed_result.returncode}",
            fixed_result.returncode == 0,
        )
        ok &= _self_test_platform_testkit_scope(tmp_root, module_path)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


_TESTKIT_IMPORT_LINE: str = (
    "from datrix_codegen_common.testkit.gates import closed_compilation  # noqa: F401\n"
)


def _self_test_platform_testkit_scope(tmp_root: Path, module_path: Path) -> bool:
    """The conformance testkit is forbidden to a platform in tests/ exactly
    as in src/ -- there is no test-only carve-out: the same import exits 1
    from both trees."""
    ok = True
    tests_dir = tmp_root / "datrix-codegen-aws" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_kit.py").write_text(_TESTKIT_IMPORT_LINE, encoding="utf-8")
    tests_result = _self_test_run_boundary_cli(tmp_root)
    ok &= _check(
        "a platform TEST importing the conformance testkit exits 1 -- no "
        f"carve-out, got {tests_result.returncode}",
        tests_result.returncode == 1,
    )
    ok &= _check(
        "the tests/ failure names datrix_codegen_common",
        "datrix_codegen_common" in tests_result.stdout + tests_result.stderr,
    )
    (tests_dir / "test_kit.py").unlink()
    clean_source = module_path.read_text(encoding="utf-8")
    module_path.write_text(_TESTKIT_IMPORT_LINE + clean_source, encoding="utf-8")
    src_result = _self_test_run_boundary_cli(tmp_root)
    ok &= _check(
        "the SAME testkit import from platform src/ exits 1, got "
        f"{src_result.returncode}",
        src_result.returncode == 1,
    )
    ok &= _check(
        "the src/ failure names datrix_codegen_common",
        "datrix_codegen_common" in src_result.stdout + src_result.stderr,
    )
    module_path.write_text(clean_source, encoding="utf-8")
    return ok


def _self_test_provider_literal_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    (a LANGUAGE package by its manifest's ``datrix.languages`` entry point)
    with a module carrying NO provider-literal conditional, plus a baseline
    TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-python", "datrix_codegen_python",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"python": "PythonLanguagePlugin"}},
    )
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_backend.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "provider-conditional-baseline.toml"
    baseline_path.write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_backend.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_provider_literal_run_cli(
    tmp_root: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-provider-conditionals",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the D5 provider-literal ratchet actually FIRES.

    Plants a real ``== "azure"`` conditional in a real, isolated fixture
    monorepo whose baseline freezes the file at 0, proves the scanner exits 1
    and names the file plus the exact count delta, then reverts the mutation
    and proves the failure clears (exit 0). This is the manifest's required
    NEGATIVE acceptance proof ("a planted new `== \"azure\"` conditional in
    ANY language package fails the ratchet"), run against a synthetic fixture
    monorepo rather than the real committed baseline.
    """
    _step(
        "Self-test 11/24: provider-literal ratchet CLI mutation non-vacuity "
        '(plant a real == "azure" conditional, prove detection, prove it clears on revert)'
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"provider-literal-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_provider_literal_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture (no provider literal) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"planted '== \"azure\"' conditional exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_backend.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_package_provider_literal_build_fixture_monorepo(
    tmp_root: Path,
) -> Path:
    """Build a minimal isolated monorepo: one datrix-common package with a
    module carrying NO provider-literal conditional (clean shared-package
    fixture -- no baseline file needed, since the shared-package check has
    none). Carries a manifest registering NO entry-point groups so
    ``discover_shared_packages`` classifies it as shared -- the DERIVED set
    main() now threads into ``scan_shared_package_provider_literals``,
    replacing the old hardcoded shared-package tuple this fixture used to
    rely on implicitly."""
    _self_test_write_manifest(
        tmp_root, "datrix-common", "datrix_common", entry_point_groups={}
    )
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_orchestrator.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    # The shared-package check has no baseline of its own, but it shares the
    # --check-provider-conditionals flag with the language-package ratchet,
    # which DOES require its baseline file to exist. This fixture monorepo
    # has no language package, so an empty (header-only) baseline is correct
    # -- it must merely exist, not carry any [[baseline]] entries.
    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "provider-conditional-baseline.toml").write_text(
        "# empty: no language package present in this fixture monorepo\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_package_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the shared-package zero-tolerance check actually FIRES.

    Plants a real ``== "azure"`` conditional in a SHARED package (datrix-common)
    in an isolated fixture monorepo carrying NO baseline entry for it (there
    is no baseline mechanism for shared packages at all), proves the scanner
    exits 1, then reverts and proves it clears. This is the manifest's
    required NEGATIVE acceptance proof for D6.1's shared-package half.
    """
    _step(
        "Self-test 12/24: shared-package provider-literal zero-tolerance CLI "
        'mutation non-vacuity (plant a real == "azure" conditional in '
        "datrix-common, prove detection, prove it clears on revert)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-provider-literal-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_package_provider_literal_build_fixture_monorepo(
            tmp_root
        )

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            "planted shared-package '== \"azure\"' conditional exits 1, got "
            f"{failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated shared-package file",
            "sample_orchestrator.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output identifies it as a SHARED-package violation, not "
            "a baseline-ratchet message",
            "shared-package provider-literal" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_vocabulary_scanner() -> bool:
    """scan_file_for_shared_vocabulary detects a bare-literal redeclaration
    of a known enum's member set, does NOT flag a container built entirely
    from qualified enum-member references, and does NOT flag an unrelated
    container whose members don't match any known vocabulary -- PLUS (added
    when the canonical-source harvest was widened past ``str, Enum``
    classes) the non-Enum harvest actually contains the three enums.py-
    declared dict/frozenset canonical vocabularies plus one vocabulary
    declared OUTSIDE enums.py (``LOG_BUILTIN_METHODS``, harvested via
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES``), a harvest restricted to Enum
    classes alone would have missed every one of them, and each non-Enum
    shape's bare-literal redeclaration is detected while its importing form
    is not."""
    _step(
        "Self-test 13/24: shared-vocabulary scanner (detection + exemption "
        "non-vacuity, Enum and non-Enum canonical sources alike)"
    )
    ok = True

    enum_members = {
        "QueryTerminal": {
            "ALL": "all",
            "FIRST": "first",
            "FIRST_OR_FAIL": "firstOrFail",
            "COUNT": "count",
        },
    }

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        bare_literal_file = scratch_dir / "bare_literal.py"
        bare_literal_file.write_text(
            '_TERMINAL_METHODS = frozenset({"all", "first", "firstOrFail", "count"})\n',
            encoding="utf-8",
        )
        bare_hits = scan_file_for_shared_vocabulary(bare_literal_file, enum_members, {})
        ok &= _check(
            "bare-string redeclaration of QueryTerminal's four members is flagged",
            len(bare_hits) == 1 and bare_hits[0].matched_vocabulary == "QueryTerminal",
        )

        qualified_only_file = scratch_dir / "qualified_only.py"
        qualified_only_file.write_text(
            "from datrix_codegen_kernel.enums import QueryTerminal\n\n"
            "_QB_EXECUTE_TERMINALS = frozenset({\n"
            "    QueryTerminal.ALL,\n"
            "    QueryTerminal.FIRST,\n"
            "    QueryTerminal.FIRST_OR_FAIL,\n"
            "    QueryTerminal.COUNT,\n"
            "})\n",
            encoding="utf-8",
        )
        qualified_hits = scan_file_for_shared_vocabulary(
            qualified_only_file, enum_members, {}
        )
        ok &= _check(
            "a container built entirely from qualified QueryTerminal.X references is NOT flagged",
            qualified_hits == [],
        )

        unrelated_file = scratch_dir / "unrelated.py"
        unrelated_file.write_text(
            '_HTTP_STATUS_CATEGORIES = frozenset({"informational", "success", "error"})\n',
            encoding="utf-8",
        )
        unrelated_hits = scan_file_for_shared_vocabulary(unrelated_file, enum_members, {})
        ok &= _check(
            "an unrelated container matching no known vocabulary is NOT flagged",
            unrelated_hits == [],
        )

        # --- Non-Enum canonical-source harvest completeness -----------------
        # A harvest restricted to `str, Enum` classes (the pre-widening
        # behaviour) is what `_shared_enum_members()` alone still returns;
        # proving these three names are ABSENT from it, while the widened
        # `_shared_non_enum_vocabularies()` DOES contain them, is the direct
        # proof that an Enum-only harvest would FAIL to cover them.
        from datrix_codegen_kernel.enums import (
            DSL_EXCEPTION_HTTP_STATUS,
            NOSQL_SUPPORTED_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        enum_only_harvest = _shared_enum_members()
        non_enum_harvest = _shared_non_enum_vocabularies()
        for vocabulary_name in (
            "DSL_EXCEPTION_HTTP_STATUS",
            "NOSQL_UNSUPPORTED_METHODS",
            "NOSQL_SUPPORTED_METHODS",
        ):
            ok &= _check(
                f"a str,Enum-only harvest does not contain {vocabulary_name} "
                f"(proves an Enum-only harvest FAILS to cover a non-Enum "
                f"canonical source)",
                vocabulary_name not in enum_only_harvest,
            )
        ok &= _check(
            "the widened harvest contains DSL_EXCEPTION_HTTP_STATUS's keys",
            non_enum_harvest.get("DSL_EXCEPTION_HTTP_STATUS")
            == frozenset(DSL_EXCEPTION_HTTP_STATUS.keys()),
        )
        ok &= _check(
            "the widened harvest contains NOSQL_UNSUPPORTED_METHODS's keys",
            non_enum_harvest.get("NOSQL_UNSUPPORTED_METHODS")
            == frozenset(NOSQL_UNSUPPORTED_METHODS.keys()),
        )
        ok &= _check(
            "the widened harvest contains NOSQL_SUPPORTED_METHODS's members",
            non_enum_harvest.get("NOSQL_SUPPORTED_METHODS")
            == frozenset(NOSQL_SUPPORTED_METHODS),
        )

        # --- Container-shape detection: a value-DERIVED frozenset ------------
        # enums.py declares no generator-expression-derived constant today,
        # so a synthetic module proves the AST shape test still counts a
        # ``frozenset(<genexpr>)`` assignment (plain and annotated) as a
        # container constant, and still rejects a non-container call.
        derived_shape_source = (
            "_ROWS = (('Log', 'info'), ('Log', 'warn'), ('Http', 'get'))\n"
            "DERIVED_PLAIN = frozenset(m for c, m in _ROWS if c == 'Log')\n"
            "DERIVED_ANNOTATED: frozenset[str] = frozenset(m for c, m in _ROWS)\n"
            "NOT_A_CONTAINER = sorted(m for c, m in _ROWS)\n"
        )
        derived_shape_names = [
            _is_module_level_container_assignment(stmt)
            for stmt in ast.parse(derived_shape_source).body
        ]
        ok &= _check(
            "a frozenset(<generator expression>) assignment is container-shaped, "
            "plain and annotated alike, while a non-container call is not",
            derived_shape_names == [None, "DERIVED_PLAIN", "DERIVED_ANNOTATED", None],
        )

        # --- Non-Enum shape 1: dict-keys (DSL_EXCEPTION_HTTP_STATUS) --------
        dict_shape_bare_file = scratch_dir / "dict_shape_bare.py"
        dict_shape_bare_file.write_text(
            f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
            encoding="utf-8",
        )
        dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring DSL_EXCEPTION_HTTP_STATUS's keys is flagged",
            len(dict_shape_bare_hits) == 1
            and dict_shape_bare_hits[0].matched_vocabulary
            == "DSL_EXCEPTION_HTTP_STATUS",
        )

        dict_shape_importing_file = scratch_dir / "dict_shape_importing.py"
        dict_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import DSL_EXCEPTION_HTTP_STATUS\n\n"
            "def status_for(exc_name: str) -> int:\n"
            "    return DSL_EXCEPTION_HTTP_STATUS[exc_name]\n",
            encoding="utf-8",
        )
        dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing DSL_EXCEPTION_HTTP_STATUS instead of redeclaring it is NOT flagged",
            dict_shape_importing_hits == [],
        )

        # --- Non-Enum shape 2: dict-keys (NOSQL_UNSUPPORTED_METHODS) --------
        second_dict_shape_bare_file = scratch_dir / "second_dict_shape_bare.py"
        second_dict_shape_bare_file.write_text(
            f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
            encoding="utf-8",
        )
        second_dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring NOSQL_UNSUPPORTED_METHODS's keys is flagged",
            len(second_dict_shape_bare_hits) == 1
            and second_dict_shape_bare_hits[0].matched_vocabulary
            == "NOSQL_UNSUPPORTED_METHODS",
        )

        second_dict_shape_importing_file = scratch_dir / "second_dict_shape_importing.py"
        second_dict_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import NOSQL_UNSUPPORTED_METHODS\n\n"
            "def reason_for(method: str) -> str:\n"
            "    return NOSQL_UNSUPPORTED_METHODS[method]\n",
            encoding="utf-8",
        )
        second_dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing NOSQL_UNSUPPORTED_METHODS instead of redeclaring it is NOT flagged",
            second_dict_shape_importing_hits == [],
        )

        # --- Non-Enum shape 3: frozenset elements (NOSQL_SUPPORTED_METHODS) -
        frozenset_shape_bare_file = scratch_dir / "frozenset_shape_bare.py"
        frozenset_shape_bare_file.write_text(
            f"_NOSQL_SUPPORTED = {frozenset(NOSQL_SUPPORTED_METHODS)!r}\n",
            encoding="utf-8",
        )
        frozenset_shape_bare_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare frozenset literal redeclaring NOSQL_SUPPORTED_METHODS's members is flagged",
            len(frozenset_shape_bare_hits) == 1
            and frozenset_shape_bare_hits[0].matched_vocabulary == "NOSQL_SUPPORTED_METHODS",
        )

        frozenset_shape_importing_file = scratch_dir / "frozenset_shape_importing.py"
        frozenset_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import NOSQL_SUPPORTED_METHODS\n\n"
            "def is_nosql_supported(method: str) -> bool:\n"
            "    return method in NOSQL_SUPPORTED_METHODS\n",
            encoding="utf-8",
        )
        frozenset_shape_importing_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing NOSQL_SUPPORTED_METHODS instead of redeclaring it is NOT flagged",
            frozenset_shape_importing_hits == [],
        )

        # --- Non-Enum shape 4: a vocabulary moved OUT of enums.py -----------
        # LOG_BUILTIN_METHODS used to live in enums.py; it now lives in
        # datrix_codegen_common.transpiler.builtin_registry (a kernel-closure
        # cut: enums.py must not import the transpiler). Proves
        # _ADDITIONAL_SHARED_VOCABULARY_SOURCES actually harvests a moved
        # declaration -- without this, a language package that hand-copies
        # the Log builtin method set would go unflagged (the exact coverage
        # gap this list exists to close).
        from datrix_codegen_common.transpiler.builtin_registry import LOG_BUILTIN_METHODS
        from datrix_codegen_kernel import enums as shared_enums_module

        ok &= _check(
            "LOG_BUILTIN_METHODS is not an attribute of enums.py itself "
            "(proves it truly moved out, so its harvest coverage can only "
            "come from _ADDITIONAL_SHARED_VOCABULARY_SOURCES, not from the "
            "enums.py AST scan)",
            not hasattr(shared_enums_module, "LOG_BUILTIN_METHODS"),
        )
        ok &= _check(
            "the widened harvest contains LOG_BUILTIN_METHODS's members even "
            "though it is declared outside enums.py",
            non_enum_harvest.get("LOG_BUILTIN_METHODS") == frozenset(LOG_BUILTIN_METHODS),
        )

        moved_shape_bare_file = scratch_dir / "moved_shape_bare.py"
        moved_shape_bare_file.write_text(
            f"_LOG_METHODS = {frozenset(LOG_BUILTIN_METHODS)!r}\n",
            encoding="utf-8",
        )
        moved_shape_bare_hits = scan_file_for_shared_vocabulary(
            moved_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a language package hand-copying LOG_BUILTIN_METHODS's members "
            "as a bare frozenset literal is flagged even though the "
            "canonical source moved out of enums.py",
            len(moved_shape_bare_hits) == 1
            and moved_shape_bare_hits[0].matched_vocabulary == "LOG_BUILTIN_METHODS",
        )

        moved_shape_importing_file = scratch_dir / "moved_shape_importing.py"
        moved_shape_importing_file.write_text(
            "from datrix_codegen_common.transpiler.builtin_registry import (\n"
            "    LOG_BUILTIN_METHODS,\n"
            ")\n\n"
            "def is_log_method(method: str) -> bool:\n"
            "    return method in LOG_BUILTIN_METHODS\n",
            encoding="utf-8",
        )
        moved_shape_importing_hits = scan_file_for_shared_vocabulary(
            moved_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing LOG_BUILTIN_METHODS from its moved home instead of "
            "redeclaring it is NOT flagged",
            moved_shape_importing_hits == [],
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return ok


def _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    (a LANGUAGE package by its manifest's ``datrix.languages`` entry point)
    whose module IMPORTS QueryTerminal (clean, no local redeclaration), plus
    a baseline TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-python", "datrix_codegen_python",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"python": "PythonLanguagePlugin"}},
    )
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_query_chain.py"
    module_path.write_text(
        "from datrix_codegen_kernel.enums import QueryTerminal\n\n"
        "def is_terminal(method: str) -> bool:\n"
        "    return method in {t.value for t in QueryTerminal}\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shared-vocabulary-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_query_chain.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_vocabulary_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-shared-vocabulary",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_vocabulary_non_enum_cli_cycle(
    tmp_root: Path,
    module_path: Path,
    clean_source: str,
    *,
    vocabulary_name: str,
    container_name: str,
    literal_source: str,
) -> bool:
    """Run one mutate -> detect -> revert -> clear CLI round-trip for a
    single non-Enum canonical vocabulary against the already-clean fixture
    at *module_path*, restoring *clean_source* before returning either way.

    Args:
        tmp_root: The isolated fixture monorepo root (for CLI invocation).
        module_path: The fixture module file to mutate in place.
        clean_source: The known-clean source to append to / restore.
        vocabulary_name: The canonical vocabulary this cycle redeclares
            (for assertion messages only).
        container_name: The bare container's assigned name in the planted
            source line (e.g. ``_EXCEPTION_STATUS_MAP``).
        literal_source: The full ``name = <literal>`` statement to append.

    Returns:
        True iff every assertion in this cycle passed.
    """
    ok = True
    module_path.write_text(clean_source + "\n" + literal_source, encoding="utf-8")
    failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"redeclaring {vocabulary_name} as a bare {container_name} literal "
        f"exits 1, got {failing_result.returncode}",
        failing_result.returncode == 1,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the mutated file",
        module_path.name in failing_result.stdout,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the exact count delta (0 -> 1)",
        "increased from baseline 0 to 1" in failing_result.stdout,
    )

    module_path.write_text(clean_source, encoding="utf-8")
    reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"reverting the {vocabulary_name} mutation clears the failure, "
        f"got exit {reverted_result.returncode}",
        reverted_result.returncode == 0,
    )
    return ok


def _self_test_shared_vocabulary_cli_non_vacuity() -> bool:
    """End-to-end proof the G1 shared-vocabulary ratchet actually FIRES --
    for the Enum-sourced case AND, added when the harvest was widened past
    ``str, Enum`` classes, for each of the three non-Enum canonical shapes.

    Starts from a fixture that IMPORTS QueryTerminal (the design's required
    POSITIVE case: exits 0), mutates it to ALSO bare-string-redeclare
    QueryTerminal's four members (the required NEGATIVE case: exits 1, names
    the file and the exact count delta), reverts and proves it clears, then
    repeats one mutate/detect/revert cycle per non-Enum vocabulary
    (``DSL_EXCEPTION_HTTP_STATUS`` and ``NOSQL_UNSUPPORTED_METHODS`` as bare
    dict literals redeclaring their keys, ``NOSQL_SUPPORTED_METHODS`` as a bare
    frozenset literal redeclaring its members) against the SAME clean
    fixture file.
    """
    _step(
        "Self-test 14/24: shared-vocabulary ratchet CLI mutation non-vacuity "
        "(fixture importing QueryTerminal exits 0; redeclaring its four "
        "members as bare literals exits 1; reverting clears it -- plus one "
        "mutate/detect/revert cycle per non-Enum canonical vocabulary)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"fixture importing QueryTerminal (no redeclaration) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        from datrix_codegen_kernel.enums import QueryTerminal

        # The redeclaration is built from the live enum, so the mutation
        # stays a full-vocabulary copy whenever a member is added or removed.
        query_terminal_literal = frozenset(member.value for member in QueryTerminal)
        module_path.write_text(
            clean_source + f"\n_TERMINAL_METHODS = {query_terminal_literal!r}\n",
            encoding="utf-8",
        )
        failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"redeclaring every QueryTerminal member as a bare literal exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_query_chain.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        from datrix_codegen_kernel.enums import (
            DSL_EXCEPTION_HTTP_STATUS,
            NOSQL_SUPPORTED_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="DSL_EXCEPTION_HTTP_STATUS",
            container_name="dict",
            literal_source=f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="NOSQL_UNSUPPORTED_METHODS",
            container_name="dict",
            literal_source=f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="NOSQL_SUPPORTED_METHODS",
            container_name="frozenset",
            literal_source=f"_NOSQL_SUPPORTED = {frozenset(NOSQL_SUPPORTED_METHODS)!r}\n",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_target_name_scanner() -> bool:
    """_identifier_carries_target_name detects a target-name segment
    (including a compound camelCase target like TypeScript across two
    adjacent segments), rejects a look-alike single-segment word (java vs.
    javascript) and every sql/nosql-substring look-alike named in the
    design, and the full scanner does not flag a bare local variable inside
    a function body but DOES detect a plain module-level constant via the
    scoped Assign path."""
    _step("Self-test 15/24: shared-target-name scanner (segment matching + non-flood proof)")
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
            str(Path(__file__).resolve()),
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
    _step(
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


def _self_test_provider_conditional_scanner() -> bool:
    """scan_file_for_provider_conditionals detects every known DI-5-deferred
    conditional shape (ProviderId-shaped, deployment-provider-value, match/case,
    and -- added by this task -- the two D5 provider-literal sub-patterns) and
    excludes every look-alike that must not ratchet."""
    _step("Self-test 5/24: provider-conditional AST scanner (detection + exclusion)")
    ok = True
    provider_ids = registered_platform_names()
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"provider-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cases: tuple[tuple[str, str, int, str], ...] = (
        (
            "providerid_eq.py",
            "def f(provider):\n    if provider == ProviderId('azure'):\n        return True\n"
            "    return False\n",
            1,
            "providerid_compare",
        ),
        (
            "providerid_ne_helper.py",
            "def f(deployment):\n    if resolve_provider_identity(deployment) != ProviderId('aws'):\n"
            "        return None\n    return 1\n",
            1,
            "providerid_compare",
        ),
        (
            "deployment_value_eq.py",
            "class G:\n    def f(self):\n        if self._deployment.provider.value == 'azure':\n"
            "            return True\n        return False\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "deployment_str_ne.py",
            "class G:\n    def f(self):\n        if str(self._deployment.provider) != 'aws':\n"
            "            return []\n        return None\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "match_case.py",
            "def f(provider_id):\n"
            "    match provider_id:\n"
            "        case p if p == ProviderId('aws'):\n"
            "            return 'a'\n"
            "        case p if p == ProviderId('azure'):\n"
            "            return 'b'\n"
            "        case _:\n"
            "            raise ValueError('unknown')\n",
            1,
            "match_case_provider_subject",
        ),
        (
            "other_axis_excluded.py",
            "class G:\n"
            "    def f(self, storage_block, email_config):\n"
            "        a = storage_block.config.provider == StorageProvider.MINIO\n"
            "        b = str(email_config.provider.value) == 'sendgrid'\n"
            "        return a, b\n",
            0,
            "",
        ),
        (
            "boundary_rewrap_excluded.py",
            "def resolve_provider_identity(deployment):\n"
            "    return ProviderId(deployment.provider.value)\n",
            0,
            "",
        ),
        (
            "dict_dispatch_excluded.py",
            "_DEPLOYED = frozenset({ProviderId('aws'), ProviderId('azure')})\n\n"
            "def f(provider):\n    if provider not in _DEPLOYED:\n        return []\n"
            "    return None\n",
            0,
            "",
        ),
        (
            "non_deployment_rooted_excluded.py",
            "def f(cfg):\n"
            "    return cfg.container if str(cfg.provider) == 'azure_blob' else cfg.bucket\n",
            0,
            "",
        ),
        (
            "provider_literal_eq.py",
            "def f(backend):\n    if backend == 'azure':\n        return True\n"
            "    return False\n",
            1,
            "provider_literal_compare",
        ),
        (
            "provider_literal_container.py",
            "_ALWAYS_REQUIRES_CREDENTIALS: frozenset = frozenset({'azure'})\n\n"
            "def f(backend):\n    return backend in _ALWAYS_REQUIRES_CREDENTIALS\n",
            1,
            "provider_literal_container",
        ),
        (
            "provider_literal_inline_membership.py",
            "def f(provider_name):\n    return provider_name in ('aws', 'azure')\n",
            1,
            "provider_literal_container",
        ),
        (
            "non_provider_literal_excluded.py",
            "def f(discovery_type):\n    return discovery_type.lower() == 'consul'\n",
            0,
            "",
        ),
        (
            "provider_literal_in_log_excluded.py",
            "import logging\n\n_LOGGER = logging.getLogger(__name__)\n\n"
            "def f() -> None:\n    _LOGGER.info('azure backend selected')\n",
            0,
            "",
        ),
        (
            "provider_literal_in_docstring_excluded.py",
            'def f() -> None:\n    """Selects the azure backend when configured."""\n'
            "    return None\n",
            0,
            "",
        ),
        (
            "provider_literal_mixed_axis_excluded.py",
            "SUPPORTED_STORAGE_PROVIDERS: frozenset = frozenset(\n"
            "    {'s3', 'minio', 'azure_blob', 'local'}\n)\n",
            0,
            "",
        ),
    )
    try:
        for filename, source, expected_count, expected_kind in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_provider_conditionals(file_path, provider_ids)
            ok &= _check(
                f"{filename}: expected {expected_count} hit(s), got {len(hits)}",
                len(hits) == expected_count,
            )
            if expected_kind and hits:
                ok &= _check(
                    f"{filename}: hit kind == {expected_kind!r}",
                    hits[0].kind == expected_kind,
                )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_function_level_import_scanner() -> bool:
    """scan_file_for_function_level_imports counts zero for module-top
    imports and exactly one for each nested (function/TYPE_CHECKING/
    try-except) import."""
    _step("Self-test 6/24: function-level-import AST scanner")
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


def _self_test_ratchets() -> bool:
    """All three ratchet comparators fire on any per-file increase, never on
    a decrease, and treat a baseline-absent file as baseline 0."""
    _step("Self-test 7/24: ratchet comparators (regression / no-regression / missing-baseline-as-zero)")
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
        SharedTargetNameBaseline(
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
        loaded = load_shared_target_name_baseline(round_trip_path)
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
    """Invoke THIS script as a real subprocess against the isolated fixture.

    --skip-auto-self-test prevents the nested invocation from recursively
    re-running the self-test (which would otherwise spawn this same
    subprocess again, without end).
    """
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--base-dir",
        str(tmp_root),
        "--check-function-level-imports",
        "--skip-auto-self-test",
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
    _step(
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
    _step(
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


def _self_test_cross_package_vocabulary_scanner() -> bool:
    """scan_cross_package_vocabulary finds a normalized value-set duplicate
    across two real discovered packages, does NOT flag a set genuinely
    unique to one package, does NOT flag the same set declared twice within
    ONE package, does NOT flag a container built entirely from qualified
    EnumClass.MEMBER references, and DOES recognize a bare tuple literal as
    a candidate container shape."""
    _step(
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
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-cross-package-vocabulary",
            "--skip-auto-self-test",
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
    _step(
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
        regenerated = load_cross_package_vocabulary_baseline(baseline_path)
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
        after_vanish = load_cross_package_vocabulary_baseline(baseline_path)
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
            str(Path(__file__).resolve()),
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
    _step(
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

    # -- Baseline loader/writer round-trip, and a missing file loading as {}.
    baseline_scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"own-target-baseline-{uuid.uuid4().hex}"
    baseline_scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path = baseline_scratch_dir / "own-target-name-baseline.toml"
        ok &= _check(
            "load_own_target_name_baseline on a missing file returns {}",
            load_own_target_name_baseline(baseline_path) == {},
        )
        round_trip_counts = {"datrix_codegen_python": 3, "datrix_codegen_typescript": 0}
        write_own_target_name_baseline(baseline_path, round_trip_counts)
        ok &= _check(
            "write_own_target_name_baseline then load_own_target_name_baseline round-trips exactly",
            load_own_target_name_baseline(baseline_path) == round_trip_counts,
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


def _self_test_shared_package_classification_fixture() -> bool:
    """``discover_shared_packages`` excludes a taxonomy-classified package,
    includes an entry-point-less package that has a real ``src/`` tree, and
    raises ``GeneratorTaxonomyError`` -- naming the package and the
    unrecognized group -- for a package registering only an unrecognized
    entry-point group, even with no ``src/`` tree at all to scan (the
    fail-loud check fires from the manifest walk alone)."""
    _step(
        "Self-test 20/24: shared-package classification (derivation "
        "excludes/includes correctly; fail-loud on an unclassifiable package)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-pkg-classification-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-lang-x", "datrix_codegen_lang_x",
            entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"lang_x": "LangXPlugin"}},
        )
        lang_src = tmp_root / "datrix-codegen-lang-x" / "src" / "datrix_codegen_lang_x"
        lang_src.mkdir(parents=True, exist_ok=True)
        (lang_src / "__init__.py").write_text("", encoding="utf-8")

        _self_test_write_manifest(
            tmp_root, "datrix-shared-y", "datrix_shared_y", entry_point_groups={},
        )
        shared_src = tmp_root / "datrix-shared-y" / "src" / "datrix_shared_y"
        shared_src.mkdir(parents=True, exist_ok=True)
        (shared_src / "__init__.py").write_text("", encoding="utf-8")

        packages = discover_packages(tmp_root)
        shared = discover_shared_packages(tmp_root, packages)
        ok &= _check(
            "a datrix.languages-registering package is NOT in the derived shared set",
            "datrix_codegen_lang_x" not in shared,
        )
        ok &= _check(
            "an entry-point-less package with a real src/ tree IS in the derived shared set",
            "datrix_shared_y" in shared,
        )

        _self_test_write_manifest(
            tmp_root, "datrix-mystery-z", "datrix_mystery_z",
            entry_point_groups={"datrix.something_new": {"mystery": "MysteryThing"}},
        )
        error_text = ""
        try:
            discover_shared_packages(tmp_root, packages)
            unclassifiable_rejected = False
        except GeneratorTaxonomyError as e:
            error_text = str(e)
            unclassifiable_rejected = (
                "datrix-mystery-z" in error_text and "datrix.something_new" in error_text
            )
        ok &= _check(
            f"a package registering only an unrecognized group is rejected by "
            f"name, got {error_text!r}",
            unclassifiable_rejected,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_platform_token_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one ``datrix-common`` package (no
    entry points -> classified SHARED by ``discover_shared_packages``) with
    a module carrying NO platform-token identifier, plus a target-literal
    baseline TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-common", "datrix_common", entry_point_groups={}
    )
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_platform_neutral.py"
    module_path.write_text(
        "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "target-literal-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-common/src/datrix_common/sample_platform_neutral.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_platform_token_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-target-literals",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_platform_token_scanner() -> bool:
    """The I1 platform-token identifier/module-name shape match: a
    declaration named ``build_azure_thing`` is a ``platform_token_identifier``
    hit naming ``azure``; ``local_cache`` produces ZERO hits (the "local"
    English-word exclusion holds); a file at ``deployment/azure_naming.py``
    is a ``platform_token_module_name`` hit naming ``azure``; every excluded
    token is still a registered platform name (a stale exclusion fails
    loud) -- PLUS a real CLI mutation proof (plant ``build_azure_thing`` in
    a derived shared-package fixture, prove the I1 ratchet fires, prove it
    clears on revert), mirroring the G2 shared-target-name ratchet's own
    CLI-mutation non-vacuity shape rather than an in-process call alone."""
    _step(
        "Self-test 21/24: platform-token identifier/module-name shape match "
        "(direct scanner assertions + CLI mutation non-vacuity)"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"platform-token-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()

        azure_file = scratch_dir / "azure_thing.py"
        azure_file.write_text(
            "def build_azure_thing() -> None:\n    return None\n", encoding="utf-8"
        )
        azure_hits = scan_file_for_target_literals(
            azure_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "build_azure_thing() is a platform_token_identifier hit naming 'azure'",
            any(
                h.kind == "platform_token_identifier" and h.matched_target == "azure"
                for h in azure_hits
            ),
        )

        local_file = scratch_dir / "local_helper.py"
        local_file.write_text("local_cache: dict = {}\n", encoding="utf-8")
        local_hits = scan_file_for_target_literals(
            local_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "a module-level 'local_cache' declaration produces ZERO hits -- "
            "'local' is excluded from the platform-token vocabulary",
            local_hits == [],
        )

        module_name_dir = scratch_dir / "deployment"
        module_name_dir.mkdir(parents=True, exist_ok=True)
        module_name_file = module_name_dir / "azure_naming.py"
        module_name_file.write_text("VALUE = 1\n", encoding="utf-8")
        module_name_hits = scan_file_for_target_literals(
            module_name_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "deployment/azure_naming.py is a platform_token_module_name hit naming 'azure'",
            any(
                h.kind == "platform_token_module_name" and h.matched_target == "azure"
                for h in module_name_hits
            ),
        )

        ok &= _check(
            "every _PLATFORM_TOKEN_EXCLUSIONS member is a registered platform name "
            "(a stale exclusion for a retired platform fails loud)",
            _PLATFORM_TOKEN_EXCLUSIONS <= frozenset(registered_platform_names()),
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"platform-token-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_platform_token_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def build_azure_thing() -> None:\n    return None\n", encoding="utf-8"
        )
        failing_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"planted build_azure_thing exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_platform_neutral.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
        )
        reverted_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def _self_test_target_literal_new_kinds() -> bool:
    """The key/comparand/isinstance/import-path target-literal shapes:
    direct scanner assertions for every one-hit and zero-hit case the design
    enumerates, the own-language exclusion holding for all three new kinds
    inside a language-core package and NOT holding for an ordinary shared
    package -- PLUS a real CLI mutation proof (plant a bare `== "python"`
    comparison in a derived shared-package fixture, prove the ratchet
    fires, prove it clears on revert), reusing
    ``_self_test_platform_token_build_fixture_monorepo`` /
    ``_self_test_platform_token_run_cli`` (the fixture shape is generic to
    any target-literal-ratchet mutation, not specific to the platform-token
    kinds)."""
    _step(
        "Self-test 22/24: target-literal key/comparand/isinstance/import-path "
        "shapes (direct scanner assertions + own-language exclusion + CLI "
        "mutation non-vacuity)"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"target-literal-new-kinds-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()
        new_kinds = ("target_name_literal", "target_type_check", "target_module_import")

        def _scan(relative_name: str, source: str) -> list[TargetLiteralHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            return scan_file_for_target_literals(
                file_path, scratch_dir, platform_names, target_literal_names
            )

        # One-hit cases.
        get_hits = _scan("dot_get.py", 'def f(configs):\n    return configs.get("azure")\n')
        ok &= _check(
            "configs.get('azure') is one target_name_literal hit naming 'azure'",
            sum(
                1
                for h in get_hits
                if h.kind == "target_name_literal" and h.matched_target == "azure"
            )
            == 1,
        )

        eq_hits = _scan(
            "eq_compare.py", 'def f(language):\n    return language.value == "python"\n'
        )
        ok &= _check(
            "language.value == 'python' is one target_name_literal hit naming 'python'",
            sum(
                1
                for h in eq_hits
                if h.kind == "target_name_literal" and h.matched_target == "python"
            )
            == 1,
        )

        in_hits = _scan(
            "in_compare.py", 'def f(x):\n    return x in ("python", "typescript")\n'
        )
        ok &= _check(
            'x in ("python", "typescript") is exactly two target_name_literal hits',
            sum(1 for h in in_hits if h.kind == "target_name_literal") == 2,
        )

        subscript_hits = _scan("subscript.py", 'def f(m):\n    return m["docker"]\n')
        ok &= _check(
            "m['docker'] is one target_name_literal hit naming 'docker'",
            sum(
                1
                for h in subscript_hits
                if h.kind == "target_name_literal" and h.matched_target == "docker"
            )
            == 1,
        )

        dict_hits = _scan("dict_key.py", 'VALUE = {"typescript": 1}\n')
        ok &= _check(
            "{'typescript': 1} is one target_name_literal hit naming 'typescript'",
            sum(
                1
                for h in dict_hits
                if h.kind == "target_name_literal" and h.matched_target == "typescript"
            )
            == 1,
        )

        isinstance_hits = _scan(
            "isinstance_azure.py",
            "class AzurePlatformConfig:\n    pass\n\n\n"
            "def f(c):\n    return isinstance(c, AzurePlatformConfig)\n",
        )
        ok &= _check(
            "isinstance(c, AzurePlatformConfig) is one target_type_check hit naming 'azure'",
            sum(
                1
                for h in isinstance_hits
                if h.kind == "target_type_check" and h.matched_target == "azure"
            )
            == 1,
        )

        import_hits = _scan(
            "module_import.py", "from datrix_common.config.platform.docker import X\n"
        )
        ok &= _check(
            "importing datrix_common.config.platform.docker is one "
            "target_module_import hit naming 'docker'",
            sum(
                1
                for h in import_hits
                if h.kind == "target_module_import" and h.matched_target == "docker"
            )
            == 1,
        )

        # Zero-hit cases.
        docstring_hits = _scan("docstring.py", '"""Mentions python in prose, not code."""\n')
        ok &= _check(
            "a module docstring mentioning 'python' produces ZERO new-kind hits",
            not any(h.kind in new_kinds for h in docstring_hits),
        )

        log_hits = _scan(
            "log_call.py",
            "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
            'def f():\n    logger.info("python")\n',
        )
        ok &= _check(
            "logger.info('python') produces ZERO new-kind hits",
            not any(h.kind in new_kinds for h in log_hits),
        )

        substring_hits = _scan("substring_compare.py", 'def f(x):\n    return "pythonic" == x\n')
        ok &= _check(
            "'pythonic' == x produces ZERO hits -- substring, not exact equality",
            not any(h.kind in new_kinds for h in substring_hits),
        )

        isinstance_base_hits = _scan(
            "isinstance_base.py",
            "class BasePlatformConfig:\n    pass\n\n\n"
            "def f(c):\n    return isinstance(c, BasePlatformConfig)\n",
        )
        ok &= _check(
            "isinstance(c, BasePlatformConfig) produces ZERO target_type_check hits "
            "-- no vocabulary token as a segment",
            not any(h.kind == "target_type_check" for h in isinstance_base_hits),
        )

        import_base_hits = _scan(
            "module_import_base.py", "from datrix_common.config.platform.base import X\n"
        )
        ok &= _check(
            "importing datrix_common.config.platform.base produces ZERO "
            "target_module_import hits -- 'base' is not a vocabulary member",
            not any(h.kind == "target_module_import" for h in import_base_hits),
        )

        # Own-language exclusion: the SAME content, once inside
        # datrix_codegen_typescript_core (excluded) and once inside an
        # ordinary shared package (not excluded), for all three new kinds.
        core_source = (
            "class TypescriptPlatformConfig:\n    pass\n\n\n"
            "def f(configs, c):\n"
            '    configs.get("typescript")\n'
            "    isinstance(c, TypescriptPlatformConfig)\n"
            "    from datrix_common.config.platform.typescript import X\n"
        )
        core_file = (
            scratch_dir
            / "datrix-codegen-typescript-core"
            / "src"
            / "datrix_codegen_typescript_core"
            / "own_language.py"
        )
        core_file.parent.mkdir(parents=True, exist_ok=True)
        core_file.write_text(core_source, encoding="utf-8")
        core_hits = scan_file_for_target_literals(
            core_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "a 'typescript' hit of all three new kinds is suppressed inside "
            "datrix_codegen_typescript_core (own-language exclusion)",
            not any(
                h.kind in new_kinds and h.matched_target == "typescript" for h in core_hits
            ),
        )

        other_file = scratch_dir / "datrix-common" / "src" / "datrix_common" / "own_language.py"
        other_file.parent.mkdir(parents=True, exist_ok=True)
        other_file.write_text(core_source, encoding="utf-8")
        other_hits = scan_file_for_target_literals(
            other_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "the SAME 'typescript' hits are NOT suppressed inside any other package",
            sum(
                1
                for h in other_hits
                if h.kind in new_kinds and h.matched_target == "typescript"
            )
            == 3,
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"target-literal-new-kinds-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_platform_token_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            'def resolve_something(language) -> bool:\n    return language == "python"\n',
            encoding="utf-8",
        )
        failing_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"planted == 'python' comparison exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_platform_neutral.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
        )
        reverted_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def _self_test_identity_provider_rules() -> bool:
    """Identity provider type rules stay out of the shared layers.

    Direct scanner assertions for the owned-type string literal and the
    ``IdentityProvider`` member kind (planted ``provider_type == <owned type>`` and two
    ``IdentityProviderType.<member>`` reads), the zero-hit cases (a docstring, the
    credential kind ``apiKey``, the vocabulary's own home files), and the hard-zero
    check over the shared identity tree."""
    _step(
        "Self-test 25/25: identity provider type rules (owned-type literal, "
        "IdentityProvider member, home-file exemption, hard zero)"
    )
    ok = True
    owned = sorted(_owned_identity_types())
    ok &= _check(
        "at least two identity provider types are owned by installed platform packages "
        "(the vocabulary is derived, and non-vacuous)",
        len(owned) >= 2,
    )
    if len(owned) < 2:
        return False
    first, second = owned[0], owned[1]
    members = {m.value: m.name for m in ConfigIdentityProvider}
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"identity-rules-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()
        ok &= _check(
            "the target-literal vocabulary carries every owned identity provider type",
            frozenset(owned) <= target_literal_names,
        )

        def _scan(relative_name: str, source: str) -> list[TargetLiteralHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            return scan_file_for_target_literals(
                file_path, scratch_dir, platform_names, target_literal_names
            )

        compare_hits = _scan(
            "owned_compare.py", f'def f(provider_type):\n    return provider_type == "{first}"\n'
        )
        ok &= _check(
            f"provider_type == '{first}' is one target_name_literal hit naming it",
            sum(
                1
                for h in compare_hits
                if h.kind == "target_name_literal" and h.matched_target == first
            )
            == 1,
        )

        import_line = (
            "from datrix_common.config.datasource.identity_config import "
            "IdentityProvider as IdentityProviderType\n\n\n"
        )
        member_hits = _scan(
            "owned_member.py",
            import_line
            + "def f(t):\n"
            + f"    return t in (IdentityProviderType.{members[first]}, "
            + f"IdentityProviderType.{members[second]})\n",
        )
        ok &= _check(
            "two IdentityProviderType.<owned member> reads are exactly two "
            "identity_provider_member hits (an import alias is followed)",
            sum(1 for h in member_hits if h.kind == "identity_provider_member") == 2,
        )

        docstring_hits = _scan("owned_docstring.py", f'"""Mentions {first} in prose."""\n')
        ok &= _check(
            "an owned type named in a docstring is ZERO identity-kind hits",
            not any(h.kind in IDENTITY_RULE_KINDS for h in docstring_hits),
        )

        api_key_hits = _scan(
            "api_key_member.py",
            import_line
            + f"def f(t):\n    return t is IdentityProviderType.{members['apiKey']}\n",
        )
        ok &= _check(
            "the credential kind apiKey is NOT an identity_provider_member hit",
            not any(h.kind == "identity_provider_member" for h in api_key_hits),
        )

        home_hits = _scan(
            "config/datasource/identity_config.py",
            import_line + f'def f(t):\n    return t == "{first}" or t is IdentityProviderType.{members[first]}\n',
        )
        ok &= _check(
            "the vocabulary's own home file (identity_config.py) is exempt from both kinds",
            not any(h.kind in IDENTITY_RULE_KINDS for h in home_hits),
        )

        identity_tree_file = (
            scratch_dir / "datrix-common" / "src" / "datrix_common" / "identity" / "rules.py"
        )
        identity_tree_file.parent.mkdir(parents=True, exist_ok=True)
        identity_tree_file.write_text(
            f'def f(provider_type):\n    return provider_type == "{first}"\n', encoding="utf-8"
        )
        tree_hits = scan_file_for_target_literals(
            identity_tree_file, scratch_dir, platform_names, target_literal_names
        )
        hard_zero = check_identity_rules_hard_zero(
            {identity_tree_file: tree_hits}, {}, scratch_dir
        )
        ok &= _check(
            "an owned type compared inside the shared identity tree is a hard-zero failure",
            len(hard_zero) == 1 and first in hard_zero[0],
        )
        baseline_message = check_identity_rules_hard_zero(
            {}, {"datrix-common/src/datrix_common/identity/rules.py": 1}, scratch_dir
        )
        ok &= _check(
            "a baseline entry naming a file in the shared identity tree is refused",
            len(baseline_message) == 1,
        )
        clean = check_identity_rules_hard_zero({}, {}, scratch_dir)
        ok &= _check("no hits and no baseline entries is clean", clean == [])
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_reexport_facade_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one fixture package
    (``datrix-codegen-fixture``) with a clean ``__init__.py`` (defines
    nothing, re-exports nothing) and a ``sub.py`` defining ``VALUE``. The
    fixture carries NO re-export-facade baseline file: the check is a hard
    zero and never reads one. Registers a ``datrix.languages`` entry point so
    the scanner classifies it (a discovered package with no rule at all stops
    the scan by design). Returns the ``__init__.py`` path."""
    _self_test_write_manifest(
        tmp_root,
        "datrix-codegen-fixture",
        "datrix_codegen_fixture",
        entry_point_groups={
            LANGUAGES_ENTRY_POINT_GROUP: {"fixture": "FixtureLanguagePlugin"}
        },
    )
    fixture_src = tmp_root / "datrix-codegen-fixture" / "src" / "datrix_codegen_fixture"
    fixture_src.mkdir(parents=True, exist_ok=True)
    init_path = fixture_src / "__init__.py"
    init_path.write_text('"""Fixture package."""\n', encoding="utf-8")
    (fixture_src / "sub.py").write_text("VALUE = 1\n", encoding="utf-8")
    # The manifest's own entry point (module=<import_package>.plugin) must
    # resolve to a real module defining the referenced attribute, or the
    # entry-point shape would itself flag a hit and break the "clean"
    # baseline this fixture is meant to establish.
    (fixture_src / "plugin.py").write_text(
        "class FixtureLanguagePlugin:\n    pass\n", encoding="utf-8"
    )
    return init_path


def _self_test_reexport_facade_run_cli(
    tmp_root: Path, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-reexport-facades",
            "--skip-auto-self-test",
            *extra_args,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_reexport_facade_extended_shapes(
    scratch_dir: Path, fixture_src: Path, packages: dict[str, PackageInfo]
) -> bool:
    """Scanner assertions for the three shapes a plain ``from <datrix module>
    import N`` scan cannot see: test-tree modules (``tests.<module>``) as
    providers, module objects read by attribute or ``getattr``, and names
    bound for a genDSL ``<namespace>.<module>.<name>`` reference. Every case
    runs the real scanner functions over real fixture files, the negative
    (zero-hit) case beside the positive one."""
    ok = True

    def _write(relative: str, source: str) -> Path:
        file_path = scratch_dir / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source, encoding="utf-8")
        _analyze_module_file.cache_clear()
        _parse_module_source.cache_clear()
        return file_path

    def _consumer(file_path: Path, known: dict[str, PackageInfo]) -> list[ReexportFacadeHit]:
        return _reexport_facade_consumer_hits(file_path, known, scratch_dir)

    def _attribute(file_path: Path) -> list[ReexportFacadeHit]:
        return sorted(
            _reexport_facade_module_attribute_hits(file_path, packages, scratch_dir),
            key=lambda hit: hit.site_line,
        )

    (fixture_src / "pkg" / "sub.py").write_text("X = 1\nY = 2\n", encoding="utf-8")

    # Test-tree modules are providers: ``tests.<module>`` resolves against the
    # importing file's own package.
    _write("tests/__init__.py", "")
    helpers = _write(
        "tests/helpers.py", "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n"
    )
    _write("tests/clean_helpers.py", "X = 1\n")
    provider_hits = _reexport_facade_provider_hits(
        helpers, _analyze_scanned_file(helpers, packages), packages, scratch_dir
    )
    ok &= _check(
        "a tests/ module re-exporting a Datrix name is exactly one provider hit "
        "named by its dotted tests.<module> path",
        len(provider_hits) == 1
        and provider_hits[0].kind == "provider"
        and provider_hits[0].providing_module_dotted == "tests.helpers",
    )
    test_use = _write("tests/test_use.py", "from tests.helpers import X\n")
    test_hits = _consumer(test_use, packages)
    ok &= _check(
        "from tests.helpers import X is exactly one consumer hit, attributed to "
        "tests/helpers.py and resolved to the module that defines X",
        len(test_hits) == 1
        and test_hits[0].kind == "consumer"
        and test_hits[0].providing_module == "tests/helpers.py"
        and test_hits[0].defining_module == "datrix_fixture.pkg.sub",
    )
    ok &= _check(
        "from tests.clean_helpers import X is zero hits when that module defines X",
        _consumer(_write("tests/test_clean.py", "from tests.clean_helpers import X\n"), packages)
        == [],
    )
    missing_hits = _consumer(
        _write("tests/test_missing.py", "from tests.nope import X\n"), packages
    )
    ok &= _check(
        "from tests.nope import X is one unresolved hit",
        len(missing_hits) == 1
        and missing_hits[0].kind == "unresolved"
        and missing_hits[0].providing_module == "tests.nope",
    )
    relative_init = _write(
        "tests/relpkg/__init__.py", "from .a import X\n\n__all__ = ['X']\n"
    )
    _write("tests/relpkg/a.py", "X = 1\n")
    relative_provider_hits = _reexport_facade_provider_hits(
        relative_init, _analyze_scanned_file(relative_init, packages), packages, scratch_dir
    )
    ok &= _check(
        "a relative import inside the tests/ tree resolves: from .a import X + "
        "__all__ is one provider hit and zero consumer hits",
        len(relative_provider_hits) == 1 and _consumer(relative_init, packages) == [],
    )
    _write("tests/ns/mod.py", "VALUE = 1\n")
    ok &= _check(
        "a tests/ directory without __init__.py is a namespace package: importing "
        "its submodule is zero hits",
        _consumer(_write("tests/test_ns.py", "from tests.ns import mod\n"), packages) == [],
    )
    namespace_hits = _consumer(
        _write("tests/test_ns_absent.py", "from tests.ns import absent\n"), packages
    )
    ok &= _check(
        "importing a name that is not a submodule of a namespace package is one "
        "unresolved hit",
        len(namespace_hits) == 1 and namespace_hits[0].kind == "unresolved",
    )
    ok &= _check(
        "a file outside every package has no tests/ root to resolve against: zero hits",
        _consumer(test_use, {}) == [],
    )

    # Module objects: ``m.attr`` and ``getattr(m, "attr")`` read the attribute at
    # run time, so a facade emptied by rewriting its imports breaks there.
    module_use = _write(
        "datrix_fixture/module_use.py",
        "import datrix_fixture.pkg as m\n"
        "import datrix_fixture.pkg.sub as s\n"
        "from datrix_fixture.pkg import sub\n\n"
        "A = m.X\n"
        "B = m.sub\n"
        "C = m.__name__\n"
        "D = s.X\n"
        "E = sub.Y\n"
        "F = sub.Missing\n"
        "G = getattr(m, 'X')\n"
        "H = getattr(m, 'X', None)\n"
        "I = hasattr(m, 'X')\n",
    )
    attribute_hits = _attribute(module_use)
    ok &= _check(
        "m.attr and getattr(m, 'attr') on a name the module only re-exports, and "
        "an undefined attribute, are exactly three module_attribute hits",
        [(hit.name, hit.site_line) for hit in attribute_hits]
        == [("X", 5), ("Missing", 10), ("X", 11)]
        and all(hit.kind == "module_attribute" for hit in attribute_hits),
    )
    ok &= _check(
        "a module-attribute hit is attributed to the re-exporting module and "
        "resolved to the module that defines the name",
        attribute_hits[0].providing_module == "datrix_fixture/pkg/__init__.py"
        and attribute_hits[0].defining_module == "datrix_fixture.pkg.sub",
    )
    ok &= _check(
        "a defined name, a submodule, a module dunder, getattr with a default and "
        "hasattr are all zero module_attribute hits",
        {hit.site_line for hit in attribute_hits}.isdisjoint({6, 7, 8, 9, 12, 13}),
    )
    scoped = _write(
        "datrix_fixture/module_scope.py",
        "import datrix_fixture.pkg as m\n\n"
        "def uses_module():\n"
        "    return m.X\n\n"
        "def shadowed(m):\n"
        "    return m.X\n\n"
        "def reimported():\n"
        "    import datrix_fixture.pkg.sub as m\n"
        "    return m.X\n",
    )
    ok &= _check(
        "module-object tracking is scope-aware: a parameter or a function-local "
        "import of another module rebinding the name is not a use of the facade",
        [hit.site_line for hit in _attribute(scoped)] == [4],
    )
    absent = _write(
        "datrix_fixture/module_absent.py",
        "import pytest\n"
        "import datrix_fixture.pkg as m\n\n"
        "def test_gone() -> None:\n"
        "    with pytest.raises(AttributeError):\n"
        "        m.X\n"
        "    with pytest.raises(AttributeError):\n"
        "        getattr(m, 'X')\n",
    )
    ok &= _check(
        "a read inside pytest.raises(AttributeError) asserts the name is gone: zero hits",
        _attribute(absent) == [],
    )
    _write("datrix_fixture/foreign.py", "import shutil\nVALUE = 1\n")
    foreign = _write(
        "datrix_fixture/foreign_use.py",
        "import datrix_fixture.foreign as f\nA = f.shutil\nB = f.nope\nC = f.VALUE\n",
    )
    ok &= _check(
        "a stdlib module the target imports is not a re-exported Datrix name, while "
        "an attribute it neither defines nor imports is one hit",
        [hit.name for hit in _attribute(foreign)] == ["nope"],
    )
    tests_module_use = _write(
        "tests/test_module_use.py",
        "from tests import helpers\n\nA = helpers.X\nB = getattr(helpers, 'X')\n",
    )
    ok &= _check(
        "a tests/ module held as an object is tracked like a Datrix module: "
        "helpers.X and getattr(helpers, 'X') are two hits",
        [hit.site_line for hit in _attribute(tests_module_use)] == [3, 4],
    )

    # genDSL-bound names: the kernel resolver looks ``<namespace>.<module>.<name>``
    # up as an attribute of the module the namespace reaches.
    bound_module = _write(
        "datrix_fixture/gendsl_mod.py",
        "from datrix_fixture.pkg.sub import X as X\nfrom datrix_fixture.pkg.sub import Y as Y\n",
    )
    definitions = _write(
        "datrix_fixture/defs.py",
        "TEXT = 'builder fx.builders.X => call fx.builders.X(item); "
        "when call other.thing.f(item);'\n",
    )

    def _resolve_fixture_namespace(module_path: str) -> str | None:
        return {"fx.builders": "datrix_fixture.gendsl_mod"}.get(module_path)

    bound = _gendsl_bound_names([definitions], packages, _resolve_fixture_namespace)
    ok &= _check(
        "the genDSL allowlist holds exactly the (module, name) pairs the definitions "
        "text references through a registered namespace",
        bound == frozenset({(bound_module, "X")}),
    )
    bound_info = _analyze_scanned_file(bound_module, packages)
    ok &= _check(
        "a name bound for a genDSL reference is not a provider hit; an unreferenced "
        "import in the same module still is",
        [
            hit.name
            for hit in _reexport_facade_provider_hits(
                bound_module, bound_info, packages, scratch_dir, bound
            )
        ]
        == ["Y"]
        and [
            hit.name
            for hit in _reexport_facade_provider_hits(
                bound_module, bound_info, packages, scratch_dir
            )
        ]
        == ["X", "Y"],
    )
    ok &= _check(
        "a Python caller importing a genDSL-bound name through that module is still "
        "a consumer hit",
        len(
            _consumer(
                _write("datrix_fixture/gendsl_caller.py", "from datrix_fixture.gendsl_mod import X\n"),
                packages,
            )
        )
        == 1,
    )
    return ok


def _self_test_reexport_facade_scanner() -> bool:
    """Direct scanner assertions for the re-export-facade check's exactly-
    one-hit and zero-hit cases, PLUS a real CLI mutation proof (plant a
    provider-side facade in a fixture package, prove the ratchet fires and
    names the exact delta, prove it clears on revert), PLUS a
    ``-FacadeModule``/``-ConsumerPackage``-filtered ``-ShowFiles`` run
    proving the worklist prints the planted sites with the consumer hit's
    resolved defining module."""
    _step(
        "Self-test 23/24: re-export-facade scanner (provider/consumer/"
        "entry-point/unresolved shapes, TYPE_CHECKING definition, submodule "
        "exemption) + CLI mutation non-vacuity + filtered worklist"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"reexport-facade-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        fixture_src = scratch_dir / "datrix_fixture"
        pkg_dir = fixture_src / "pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text(
            "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n", encoding="utf-8"
        )
        (pkg_dir / "sub.py").write_text("X = 1\n", encoding="utf-8")
        packages = {
            "datrix_fixture": PackageInfo(
                name="datrix_fixture", root=scratch_dir, src_dir=fixture_src
            )
        }

        def _provider_hits(relative_name: str, source: str) -> list[ReexportFacadeHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            _analyze_module_file.cache_clear()
            _parse_module_source.cache_clear()
            info = _analyze_scanned_file(file_path, packages)
            return _reexport_facade_provider_hits(file_path, info, packages, scratch_dir)

        # One-hit case: __all__ = ["X"] + from a.b import X.
        all_hits = _provider_hits(
            "one_all.py", "from datrix_fixture.pkg.sub import X\n\n__all__ = ['X']\n"
        )
        ok &= _check(
            "__all__ = ['X'] + from ...sub import X is exactly one provider hit",
            len(all_hits) == 1 and all_hits[0].kind == "provider" and all_hits[0].name == "X",
        )

        # One-hit case: from a.b import X as X.
        self_alias_hits = _provider_hits(
            "one_self_alias.py", "from datrix_fixture.pkg.sub import X as X\n"
        )
        ok &= _check(
            "from ...sub import X as X is exactly one provider hit",
            len(self_alias_hits) == 1 and self_alias_hits[0].kind == "provider",
        )

        # Zero-hit case: imports X and uses it without listing it in __all__.
        unlisted_hits = _provider_hits(
            "zero_unlisted.py", "from datrix_fixture.pkg.sub import X\n\nprint(X)\n"
        )
        ok &= _check(
            "importing X and using it without __all__/self-alias is zero provider hits",
            unlisted_hits == [],
        )

        # Zero-hit case: a name defined under if TYPE_CHECKING: ... else: ...
        # despite also being self-aliased from an external module.
        type_checking_hits = _provider_hits(
            "zero_type_checking.py",
            "from typing import TYPE_CHECKING\n"
            "from datrix_fixture.pkg.sub import X as X\n\n"
            "if TYPE_CHECKING:\n"
            "    class X:\n"
            "        pass\n"
            "else:\n"
            "    class X:\n"
            "        pass\n",
        )
        ok &= _check(
            "a name defined under if TYPE_CHECKING: ... else: ... is zero "
            "provider hits even when self-aliased",
            type_checking_hits == [],
        )

        # One-hit case (consumer side): from pkg import X where pkg/__init__
        # only imports X (never defines it) -- resolves the defining module
        # through the re-export chain to pkg.sub.
        consumer_file = scratch_dir / "consumer.py"
        consumer_file.write_text("from datrix_fixture.pkg import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        consumer_hits = _reexport_facade_consumer_hits(consumer_file, packages, scratch_dir)
        ok &= _check(
            "from pkg import X where pkg/__init__ only imports X is exactly "
            "one consumer hit, resolved to the module that actually defines it",
            len(consumer_hits) == 1
            and consumer_hits[0].kind == "consumer"
            and consumer_hits[0].providing_module
            == "datrix_fixture/pkg/__init__.py"
            and consumer_hits[0].defining_module == "datrix_fixture.pkg.sub",
        )

        # Zero-hit case: from pkg import submodule is a normal traversal.
        submodule_file = scratch_dir / "submodule_consumer.py"
        submodule_file.write_text("from datrix_fixture.pkg import sub\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        submodule_hits = _reexport_facade_consumer_hits(
            submodule_file, packages, scratch_dir
        )
        ok &= _check(
            "from pkg import submodule is zero consumer hits (submodule exemption)",
            submodule_hits == [],
        )

        # One-hit case: a facade name that differs from a submodule's file
        # stem only by case is NOT that submodule -- a case-insensitive
        # filesystem must not exempt it.
        case_pkg_dir = fixture_src / "pkg_case"
        case_pkg_dir.mkdir(parents=True, exist_ok=True)
        (case_pkg_dir / "__init__.py").write_text(
            "from datrix_fixture.pkg_case.sub import Sub\n\n__all__ = ['Sub']\n",
            encoding="utf-8",
        )
        (case_pkg_dir / "sub.py").write_text("Sub = 1\n", encoding="utf-8")
        case_file = scratch_dir / "case_consumer.py"
        case_file.write_text("from datrix_fixture.pkg_case import Sub\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        case_hits = _reexport_facade_consumer_hits(case_file, packages, scratch_dir)
        ok &= _check(
            "from pkg import Sub where pkg also has sub.py is one consumer hit "
            "(the submodule exemption is case-exact)",
            len(case_hits) == 1
            and case_hits[0].kind == "consumer"
            and case_hits[0].defining_module == "datrix_fixture.pkg_case.sub",
        )

        # Unresolved-import case: the module segment does not exist on disk.
        unresolved_file = scratch_dir / "unresolved_consumer.py"
        unresolved_file.write_text(
            "from datrix_fixture.no_such_module import X\n", encoding="utf-8"
        )
        _parse_module_source.cache_clear()
        unresolved_hits = _reexport_facade_consumer_hits(
            unresolved_file, packages, scratch_dir
        )
        ok &= _check(
            "an import of a module that resolves to nothing on disk is one "
            "unresolved hit",
            len(unresolved_hits) == 1
            and unresolved_hits[0].kind == "unresolved"
            and unresolved_hits[0].providing_module == "datrix_fixture.no_such_module",
        )

        # Entry-point case: a pyproject.toml `module:attr` value is a site. An
        # attr the module defines is zero hits; an attr it does not define is
        # one entry_point hit attributed to the module's file; a module that
        # resolves to nothing on disk is one entry_point hit attributed to the
        # dotted path.
        ep_repo = scratch_dir / "ep_repo"
        ep_root = ep_repo / "datrix-fixture-ep"
        ep_src = ep_root / "src" / "datrix_fixture_ep"
        ep_src.mkdir(parents=True, exist_ok=True)
        (ep_src / "__init__.py").write_text('"""Fixture."""\n', encoding="utf-8")
        (ep_src / "plugin.py").write_text(
            "class DefinedPlugin:\n    pass\n", encoding="utf-8"
        )
        ep_packages = {
            "datrix_fixture_ep": PackageInfo(
                name="datrix_fixture_ep", root=ep_root, src_dir=ep_src
            )
        }

        def _entry_point_hits(
            import_package: str, attribute: str
        ) -> list[ReexportFacadeHit]:
            _self_test_write_manifest(
                ep_repo,
                "datrix-fixture-ep",
                import_package,
                entry_point_groups={"datrix.languages": {"fixture": attribute}},
            )
            _analyze_module_file.cache_clear()
            _parse_module_source.cache_clear()
            scanned = scan_reexport_facades(ep_packages, ep_repo)
            return [
                hit
                for hits in scanned.values()
                for hit in hits
                if hit.kind == "entry_point"
            ]

        ok &= _check(
            "an entry point naming an attr its module defines is zero entry_point hits",
            _entry_point_hits("datrix_fixture_ep", "DefinedPlugin") == [],
        )
        undefined_attr_hits = _entry_point_hits("datrix_fixture_ep", "MissingPlugin")
        ok &= _check(
            "an entry point naming an attr its module does not define is exactly "
            "one entry_point hit attributed to that module's file",
            len(undefined_attr_hits) == 1
            and undefined_attr_hits[0].name == "MissingPlugin"
            and undefined_attr_hits[0].providing_module.endswith(
                "src/datrix_fixture_ep/plugin.py"
            ),
        )
        unresolved_ep_hits = _entry_point_hits("datrix_fixture_ep.nowhere", "DefinedPlugin")
        ok &= _check(
            "an entry point naming a module that resolves to nothing on disk is "
            "exactly one entry_point hit attributed to the dotted path",
            len(unresolved_ep_hits) == 1
            and unresolved_ep_hits[0].providing_module
            == "datrix_fixture_ep.nowhere.plugin",
        )

        # Relative imports resolve to their absolute module from the file's
        # own dotted name, on both the provider and the consumer side.
        rel_pkg_dir = fixture_src / "relpkg"
        rel_pkg_dir.mkdir(parents=True, exist_ok=True)
        (rel_pkg_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        relative_all_hits = _provider_hits(
            "datrix_fixture/relpkg/__init__.py",
            "from .a import X\n\n__all__ = ['X']\n",
        )
        ok &= _check(
            "from .a import X + __all__ = ['X'] is exactly one provider hit",
            len(relative_all_hits) == 1
            and relative_all_hits[0].kind == "provider"
            and relative_all_hits[0].name == "X",
        )

        relative_own_consumer_hits = _reexport_facade_consumer_hits(
            rel_pkg_dir / "__init__.py", packages, scratch_dir
        )
        ok &= _check(
            "from .a import X is zero consumer hits when a.py defines X",
            relative_own_consumer_hits == [],
        )

        rel_sub_dir = fixture_src / "relsub"
        rel_sub_dir.mkdir(parents=True, exist_ok=True)
        (rel_sub_dir / "a.py").write_text("X = 1\n", encoding="utf-8")
        relative_submodule_hits = _provider_hits(
            "datrix_fixture/relsub/__init__.py",
            "from . import a\n\n__all__ = ['a']\n",
        )
        relative_submodule_consumer_hits = _reexport_facade_consumer_hits(
            rel_sub_dir / "__init__.py", packages, scratch_dir
        )
        ok &= _check(
            "from . import submodule is zero provider and zero consumer hits",
            relative_submodule_hits == [] and relative_submodule_consumer_hits == [],
        )

        relative_consumer_file = rel_pkg_dir / "relative_consumer.py"
        relative_consumer_file.write_text("from . import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        relative_consumer_hits = _reexport_facade_consumer_hits(
            relative_consumer_file, packages, scratch_dir
        )
        ok &= _check(
            "a relative consumer importing a re-exported name through a facade "
            "is exactly one consumer hit, resolved to the defining module",
            len(relative_consumer_hits) == 1
            and relative_consumer_hits[0].kind == "consumer"
            and relative_consumer_hits[0].providing_module
            == "datrix_fixture/relpkg/__init__.py"
            and relative_consumer_hits[0].defining_module == "datrix_fixture.relpkg.a",
        )

        relative_unresolved_file = rel_pkg_dir / "relative_unresolved.py"
        relative_unresolved_file.write_text("from .no_such import X\n", encoding="utf-8")
        _parse_module_source.cache_clear()
        relative_unresolved_hits = _reexport_facade_consumer_hits(
            relative_unresolved_file, packages, scratch_dir
        )
        ok &= _check(
            "a relative import of a module that resolves to nothing on disk is "
            "one unresolved hit",
            len(relative_unresolved_hits) == 1
            and relative_unresolved_hits[0].kind == "unresolved"
            and relative_unresolved_hits[0].providing_module
            == "datrix_fixture.relpkg.no_such",
        )

        # A package's root-level modules (conftest.py) are in the scan scope.
        conftest_package_root = scratch_dir / "datrix-root-scan"
        (conftest_package_root / "src" / "datrix_root_scan").mkdir(parents=True)
        (conftest_package_root / "conftest.py").write_text("\n", encoding="utf-8")
        scoped_files = _reexport_facade_scan_files(
            {
                "datrix_root_scan": PackageInfo(
                    name="datrix_root_scan",
                    root=conftest_package_root,
                    src_dir=conftest_package_root / "src" / "datrix_root_scan",
                )
            },
            scratch_dir,
        )
        ok &= _check(
            "a package's root-level conftest.py is in the re-export-facade scan scope",
            conftest_package_root / "conftest.py" in scoped_files,
        )

        ok &= _self_test_reexport_facade_extended_shapes(scratch_dir, fixture_src, packages)
    finally:
        _analyze_module_file.cache_clear()
        _parse_module_source.cache_clear()
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"reexport-facade-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        init_path = _self_test_reexport_facade_build_fixture_monorepo(tmp_root)
        clean_source = init_path.read_text(encoding="utf-8")

        baseline_path = (
            tmp_root / "datrix" / "scripts" / "config" / "reexport-facade-baseline.toml"
        )
        ok &= _check(
            "the fixture carries no re-export-facade baseline file",
            not baseline_path.exists(),
        )

        clean_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture package exits 0 with the baseline file absent, "
            f"got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        init_path.write_text(
            "from datrix_codegen_fixture.sub import VALUE\n\n__all__ = ['VALUE']\n",
            encoding="utf-8",
        )
        failing_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"planted provider-side facade exits 1 with the baseline file absent, "
            f"got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file, line and name",
            "__init__.py:1 VALUE" in failing_result.stdout,
        )

        # A hand-authored baseline at the old path must not suppress the
        # planted facade, and the check must not resurrect or rewrite it.
        stray_baseline = (
            "[[baseline]]\n"
            'file = "datrix-codegen-fixture/src/datrix_codegen_fixture/__init__.py"\n'
            "count = 5\n"
        )
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(stray_baseline, encoding="utf-8")
        stray_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"a stray hand-authored baseline does not suppress a planted facade, "
            f"got exit {stray_result.returncode}",
            stray_result.returncode == 1,
        )
        ok &= _check(
            "the check leaves a stray baseline file untouched",
            baseline_path.read_text(encoding="utf-8") == stray_baseline,
        )
        baseline_path.unlink()

        update_result = _self_test_reexport_facade_run_cli(tmp_root, "--update-baseline")
        ok &= _check(
            f"--update-baseline cannot make a planted facade pass, "
            f"got exit {update_result.returncode}",
            update_result.returncode == 1,
        )
        ok &= _check(
            "--update-baseline writes no re-export-facade baseline file",
            not baseline_path.exists(),
        )

        init_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        # Filtered worklist: plant the same provider-side facade AND a
        # consumer that imports through it, then prove -ShowFiles
        # -FacadeModule prints both sites, the consumer line naming the
        # module that actually defines the name.
        init_path.write_text(
            "from datrix_codegen_fixture.sub import VALUE\n\n__all__ = ['VALUE']\n",
            encoding="utf-8",
        )
        fixture_src_dir = tmp_root / "datrix-codegen-fixture" / "src" / "datrix_codegen_fixture"
        consumer_path = fixture_src_dir / "consumer.py"
        consumer_path.write_text(
            "from datrix_codegen_fixture import VALUE\n", encoding="utf-8"
        )
        worklist_result = _self_test_reexport_facade_run_cli(
            tmp_root,
            "--verbose",
            "--facade-module",
            "datrix_codegen_fixture",
        )
        ok &= _check(
            "the filtered worklist prints the planted provider hit",
            "[provider]" in worklist_result.stdout and "VALUE" in worklist_result.stdout,
        )
        ok &= _check(
            "the filtered worklist prints the consumer hit with its "
            "resolved defining module",
            "[consumer]" in worklist_result.stdout
            and "(defined by datrix_codegen_fixture.sub)" in worklist_result.stdout,
        )

        consumer_package_result = _self_test_reexport_facade_run_cli(
            tmp_root,
            "--verbose",
            "--consumer-package",
            "datrix-codegen-fixture",
        )
        ok &= _check(
            "-ConsumerPackage matching the site's own repo keeps its line",
            "consumer.py" in consumer_package_result.stdout,
        )

        consumer_path.unlink()
        init_path.write_text(clean_source, encoding="utf-8")
        final_result = _self_test_reexport_facade_run_cli(tmp_root)
        ok &= _check(
            f"removing both mutations clears the failure, got exit {final_result.returncode}",
            final_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def _self_test_non_utf8_source_handling() -> bool:
    """A non-UTF-8 ``.py`` file under a scanned tree is reported by path and
    exits 2, exactly like every other unreadable/unparseable file -- never an
    uncaught ``UnicodeDecodeError`` traceback. ``UnicodeDecodeError`` is a
    ``ValueError`` subclass, so a bare ``except (SyntaxError, OSError)`` does
    not catch it; every policed-file read site widens its ``OSError`` clause
    to ``(OSError, UnicodeDecodeError)`` so a stray non-UTF-8 file fails
    closed with the same clean message every other bad file gets, instead of
    crashing the whole scan."""
    _step(
        "Self-test 24/24: a non-UTF-8 source file is reported by path, "
        "never an uncaught crash"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"non-utf8-source-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        _self_test_write_manifest(
            tmp_root, "datrix-codegen-aws", "datrix_codegen_aws",
            entry_point_groups={PLATFORMS_ENTRY_POINT_GROUP: {"aws": "AwsPlatform"}},
        )
        package_src = tmp_root / "datrix-codegen-aws" / "src" / "datrix_codegen_aws"
        package_src.mkdir(parents=True, exist_ok=True)
        (package_src / "__init__.py").write_text("", encoding="utf-8")
        bad_file = package_src / "bad_encoding.py"
        # A lone UTF-8 continuation byte (0x80) is invalid at every position --
        # guaranteed to raise UnicodeDecodeError, never silently decode.
        bad_file.write_bytes(b"# \x80 not valid utf-8\n")

        result = _self_test_run_boundary_cli(tmp_root)
        combined = result.stdout + result.stderr
        ok &= _check(
            f"a non-UTF-8 .py file exits 2 (clean, fail-closed), got {result.returncode}",
            result.returncode == 2,
        )
        ok &= _check(
            "the failure names the unreadable file by path rather than crashing",
            "bad_encoding.py" in combined and "Failed to read" in combined,
        )
        ok &= _check(
            "no uncaught traceback reaches the output",
            "Traceback (most recent call last)" not in combined,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def run_self_test() -> bool:
    """Run every self-test check; return True iff all passed.

    This is the checker's own non-vacuity proof: the rule-model constants,
    the AST scanners, and the ratchet comparators are exercised against
    known-good and known-bad cases (including a real mutation-based CLI
    proof), so a change that silently breaks any of them is caught before
    the checker's findings are trusted.
    """
    try:
        taxonomy, rules = _real_repo_rules()
    except (FileNotFoundError, GeneratorTaxonomyError) as e:
        print(f"{_RED}[FAIL]{_RESET} cannot discover the real repository's taxonomy: {e}")
        return False
    results = [
        _self_test_no_testkit_carve_out(taxonomy, rules),
        _self_test_dotted_precision_and_carveout(rules),
        _self_test_sql_and_component_coverage(rules),
        _self_test_platform_to_platform_prohibition(taxonomy, rules),
        _self_test_provider_conditional_scanner(),
        _self_test_function_level_import_scanner(),
        _self_test_ratchets(),
        _self_test_cli_non_vacuity(),
        _self_test_function_level_scope_and_entries(),
        _self_test_platform_cli_non_vacuity(),
        _self_test_provider_literal_cli_non_vacuity(),
        _self_test_shared_package_provider_literal_cli_non_vacuity(),
        _self_test_shared_vocabulary_scanner(),
        _self_test_shared_vocabulary_cli_non_vacuity(),
        _self_test_shared_target_name_scanner(),
        _self_test_shared_target_name_cli_non_vacuity(),
        _self_test_cross_package_vocabulary_scanner(),
        _self_test_cross_package_vocabulary_cli_non_vacuity(),
        _self_test_own_target_name_cli_non_vacuity(),
        _self_test_shared_package_classification_fixture(),
        _self_test_platform_token_scanner(),
        _self_test_target_literal_new_kinds(),
        _self_test_identity_provider_rules(),
        _self_test_reexport_facade_scanner(),
        _self_test_non_utf8_source_handling(),
    ]
    print()
    if all(results):
        print(f"{_GREEN}SELF-TEST PASSED{_RESET}: rule model, scanners, and ratchets are non-vacuous.")
        return True
    print(f"{_RED}SELF-TEST FAILED{_RESET}: see failures above.")
    return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = violations found, 2 = error)
    """
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

    args = parser.parse_args()

    if args.skip_auto_self_test and args.self_test:
        print(
            "Error: --self-test and --skip-auto-self-test are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    if not args.skip_auto_self_test:
        self_test_passed = run_self_test()
        if args.self_test:
            return 0 if self_test_passed else 1
        if not self_test_passed:
            print(
                "\nError: self-test failed -- the checker itself is not provably "
                "correct, so its findings cannot be trusted. Fix the self-test "
                "failure(s) above before relying on this gate's result.",
                file=sys.stderr,
            )
            return 1

    monorepo_root = args.base_dir.resolve() if args.base_dir else WORKSPACE_DIR

    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return 2

    # Load allowlist
    allowlist_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "import-boundary-allowlist.toml"
    )
    allowlist = load_allowlist(allowlist_path)

    # Discover packages
    packages = discover_packages(monorepo_root)
    if not packages:
        print(f"Error: No datrix packages found in {monorepo_root}", file=sys.stderr)
        return 2

    # Discover the generator taxonomy from the manifests and derive the rules.
    # A discovered package with no rule would be scanned against nothing and
    # read as clean, so that state is refused rather than tolerated.
    try:
        taxonomy = discover_generator_taxonomy(monorepo_root)
    except GeneratorTaxonomyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    rules = build_boundary_rules(taxonomy)
    unruled = unruled_packages(packages, rules)
    if unruled:
        print(
            f"Error: discovered package(s) {unruled} have no boundary rule. A package "
            f"is classified from its pyproject.toml entry points -- register "
            f"'{LANGUAGES_ENTRY_POINT_GROUP}' (language generator) or "
            f"'{PLATFORMS_ENTRY_POINT_GROUP}' (platform generator) -- or, for a "
            f"generator that is neither (SQL, Component, a client target), add an explicit "
            f"entry to build_boundary_rules(). Refusing to scan a package against no "
            f"rule: that would report it clean without checking anything.",
            file=sys.stderr,
        )
        return 2

    # Derive the shared-package set the I1 target-literal ratchet and the I6
    # shared-package hard-zero check scan. A package this derivation cannot
    # classify (registers only unrecognized entry-point groups) aborts the
    # whole scan rather than being silently folded into either bucket.
    try:
        shared_packages = discover_shared_packages(monorepo_root, packages)
    except GeneratorTaxonomyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"Found {len(packages)} packages:", file=sys.stderr)
        for pkg_name in sorted(packages.keys()):
            print(f"  - {pkg_name}", file=sys.stderr)
        print(
            f"Taxonomy (from manifests): languages={list(taxonomy.language_packages)} "
            f"platforms={list(taxonomy.platform_packages)}",
            file=sys.stderr,
        )
        print("", file=sys.stderr)

    # Scan all packages
    all_violations: list[Violation] = []
    for package_name, package_info in sorted(packages.items()):
        violations = scan_package_for_violations(
            package_info,
            monorepo_root,
            args.verbose,
            rules,
        )
        all_violations.extend(violations)

    # Filter out allowlisted violations
    non_allowlisted_violations = [
        v for v in all_violations if not is_allowlisted(v, allowlist, monorepo_root)
    ]

    # I1 target-literal ratchet (invariant I1) — opt-in via
    # --check-target-literals so existing no-flag import-boundary callers
    # keep their current behavior.
    target_literal_baseline_path = (
        monorepo_root / "datrix" / "scripts" / "config" / "target-literal-baseline.toml"
    )
    # I6 successor ratchet (invariant I6, DI-4/DI-5) — opt-in via
    # --check-provider-conditionals.
    provider_conditional_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "provider-conditional-baseline.toml"
    )
    # Function-level-import ratchet — opt-in
    # via --check-function-level-imports.
    function_level_import_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "function-level-import-baseline.toml"
    )
    # G1 shared-vocabulary ratchet (Decision D3, Invariant I2) — opt-in
    # via --check-shared-vocabulary.
    shared_vocabulary_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "shared-vocabulary-baseline.toml"
    )
    # G2 shared-layer target-name ratchet (Decision D4, Invariant I3) — opt-in
    # via --check-shared-target-names.
    shared_target_name_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "shared-target-name-baseline.toml"
    )
    # G3 cross-package vocabulary ratchet (Decision D2.1-D2.4) — opt-in via
    # --check-cross-package-vocabulary.
    cross_package_vocabulary_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "cross-package-vocabulary-baseline.toml"
    )
    # I4 own-target-name ratchet (Decision D5, Invariant I4) — opt-in via
    # --check-own-target-names.
    own_target_name_baseline_path = (
        monorepo_root / "datrix" / "scripts" / "config" / "own-target-name-baseline.toml"
    )
    # D6.1 shared-package zero-tolerance check (distinct from the I6
    # language-package ratchet above) -- runs UNCONDITIONALLY whenever
    # --check-provider-conditionals is passed, in both --update-baseline and
    # normal-scan modes. It has no baseline file to seed or grandfather into,
    # so it is computed once here rather than inside either mode's branch.
    shared_package_provider_literal_messages: list[str] = []
    if args.check_provider_conditionals:
        shared_package_hits_by_file = scan_shared_package_provider_literals(
            packages, monorepo_root, shared_packages
        )
        shared_package_provider_literal_messages = check_shared_package_provider_literals(
            shared_package_hits_by_file, monorepo_root
        )

    # Re-export-facade check (exactly one import path per symbol) -- a hard
    # zero with no baseline file, computed unconditionally for the same
    # reason as the shared-package check above: a real hit must fail even
    # inside an --update-baseline run requested for a different flag.
    reexport_facade_messages: list[str] = []
    reexport_facade_hits_by_module: dict[str, list[ReexportFacadeHit]] = {}
    if args.check_reexport_facades:
        reexport_facade_hits_by_module = scan_reexport_facades(packages, monorepo_root)
        reexport_facade_messages = check_reexport_facades(
            reexport_facade_hits_by_module, monorepo_root
        )

    if args.update_baseline:
        updated_any = False

        # Provider-conditional baseline updates when explicitly requested via
        # --check-provider-conditionals. Function-level-import baseline
        # updates when explicitly requested via --check-function-level-imports.
        # Target-literal baseline updates unless one of those two OTHER
        # ratchets was requested without --check-target-literals also being
        # requested (preserves the pre-existing --update-baseline-alone =>
        # target-literal behavior for existing callers).
        if args.check_provider_conditionals:
            provider_hits_by_file = scan_provider_conditionals(
                packages, monorepo_root, taxonomy.language_packages
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in provider_hits_by_file.items()
            }
            write_provider_conditional_baseline(
                provider_conditional_baseline_path, current_counts
            )
            print(
                f"Updated I6 provider-conditional baseline: {len(current_counts)} file(s) "
                f"recorded at {provider_conditional_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_function_level_imports:
            if not function_level_import_baseline_path.exists():
                print(
                    f"Error: function-level-import baseline not found at "
                    f"{function_level_import_baseline_path}. The baseline is "
                    f"decrease-only: --update-baseline lowers an existing record and "
                    f"never creates one. Restore the file from version control.",
                    file=sys.stderr,
                )
                return 2
            try:
                frozen_baseline = load_function_level_import_baseline(
                    function_level_import_baseline_path
                )
            except FunctionLevelImportBaselineError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2
            function_level_hits_by_file = scan_function_level_imports(
                packages, monorepo_root, frozenset(frozen_baseline.counts)
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in function_level_hits_by_file.items()
            }
            increases = check_function_level_import_ratchet(
                current_counts, frozen_baseline.counts
            )
            if increases:
                print(
                    f"Error: refusing to raise the function-level-import baseline -- "
                    f"{len(increases)} file(s) are above it. The ratchet is "
                    f"decrease-only: promote the new deferred imports to module top, or "
                    f"record a cycle-forced deferral by hand with its reason:\n"
                )
                for message in increases:
                    print(message)
                print()
                return 1
            lowered_baseline, dropped = lowered_function_level_import_baseline(
                frozen_baseline, current_counts
            )
            write_function_level_import_baseline(
                function_level_import_baseline_path,
                lowered_baseline.counts,
                lowered_baseline.reasons,
            )
            for file_rel in dropped:
                print(
                    f"Dropped function-level-import baseline entry {file_rel}: it has no "
                    f"function-level import left.",
                    file=sys.stderr,
                )
            print(
                f"Updated function-level-import baseline: {len(lowered_baseline.counts)} "
                f"file(s) recorded at "
                f"{function_level_import_baseline_path.relative_to(monorepo_root)} "
                f"({len(dropped)} dropped, none raised)"
            )
            updated_any = True

        if args.check_shared_vocabulary:
            shared_vocabulary_hits_by_file = scan_shared_vocabulary(
                packages, monorepo_root, taxonomy.language_packages
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in shared_vocabulary_hits_by_file.items()
            }
            write_shared_vocabulary_baseline(shared_vocabulary_baseline_path, current_counts)
            print(
                f"Updated G1 shared-vocabulary baseline: {len(current_counts)} file(s) "
                f"recorded at {shared_vocabulary_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_shared_target_names:
            shared_target_name_hits_by_file = scan_shared_target_names(
                packages, monorepo_root
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in shared_target_name_hits_by_file.items()
            }
            # Reasons are part of the frozen record: carry every written reason
            # across the regeneration, and name any reasoned entry whose hit
            # has since vanished so the reviewer sees it.
            previous_reasons = load_shared_target_name_baseline(
                shared_target_name_baseline_path
            ).reasons
            write_shared_target_name_baseline(
                shared_target_name_baseline_path, current_counts, previous_reasons
            )
            for vanished in sorted(previous_reasons.keys() - current_counts.keys()):
                print(
                    f"Warning: G2 baseline entry {vanished} carried a reason but has "
                    f"no shared-target-name hit any more; its entry and reason were "
                    f"dropped. Expected only when the identifier was deliberately "
                    f"renamed or removed -- if it still exists, the scanner no longer "
                    f"sees it.",
                    file=sys.stderr,
                )
            print(
                f"Updated G2 shared-target-name baseline: {len(current_counts)} file(s) "
                f"recorded at {shared_target_name_baseline_path.relative_to(monorepo_root)} "
                f"({len(previous_reasons.keys() & current_counts.keys())} carrying a reason)"
            )
            updated_any = True

        if args.check_cross_package_vocabulary:
            cross_package_vocabulary_hits_by_file = scan_cross_package_vocabulary(
                packages, monorepo_root
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in cross_package_vocabulary_hits_by_file.items()
            }
            # Reasons are part of the frozen record: carry every written D9
            # reason across the regeneration, and name any reasoned entry
            # whose declaration has since vanished so the reviewer sees it.
            previous_reasons = load_cross_package_vocabulary_baseline(
                cross_package_vocabulary_baseline_path
            ).reasons
            write_cross_package_vocabulary_baseline(
                cross_package_vocabulary_baseline_path, current_counts, previous_reasons
            )
            for vanished in sorted(previous_reasons.keys() - current_counts.keys()):
                print(
                    f"Warning: G3 baseline entry {vanished} carried a D9 reason but "
                    f"has no cross-package hit any more; its entry and reason were "
                    f"dropped. Expected only when that declaration was deliberately "
                    f"removed -- if it still exists, the scanner no longer sees it.",
                    file=sys.stderr,
                )
            print(
                f"Updated G3 cross-package-vocabulary baseline: {len(current_counts)} "
                f"file(s) recorded at "
                f"{cross_package_vocabulary_baseline_path.relative_to(monorepo_root)} "
                f"({len(previous_reasons.keys() & current_counts.keys())} carrying a "
                f"D9 reason)"
            )
            updated_any = True

        if args.check_own_target_names:
            own_target_name_hits_by_package = scan_own_target_names(
                packages, monorepo_root, taxonomy.language_packages
            )
            current_counts = {
                package_name: len(own_target_name_hits_by_package.get(package_name, []))
                for package_name in taxonomy.language_packages
            }
            write_own_target_name_baseline(own_target_name_baseline_path, current_counts)
            print(
                f"Updated I4 own-target-name baseline: {len(current_counts)} package(s) "
                f"recorded at {own_target_name_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        # The re-export-facade check has no baseline, so requesting it alone
        # must not fall through to the target-literal default and overwrite an
        # unrelated baseline.
        if args.check_target_literals or not (
            args.check_provider_conditionals
            or args.check_function_level_imports
            or args.check_shared_vocabulary
            or args.check_shared_target_names
            or args.check_cross_package_vocabulary
            or args.check_own_target_names
            or args.check_reexport_facades
        ):
            target_literal_hits_by_file = scan_target_literals(
                packages, monorepo_root, shared_packages
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in target_literal_hits_by_file.items()
            }
            write_target_literal_baseline(target_literal_baseline_path, current_counts)
            print(
                f"Updated I1 target-literal baseline: {len(current_counts)} file(s) "
                f"recorded at {target_literal_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if shared_package_provider_literal_messages:
            print(
                f"Error: shared-package provider-literal zero-tolerance check failed "
                f"for {len(shared_package_provider_literal_messages)} occurrence(s) -- "
                "these packages have no baseline to update; fix the code instead:\n"
            )
            for message in shared_package_provider_literal_messages:
                print(message)
            print()
            return 1

        if reexport_facade_messages:
            print(
                f"Error: re-export-facade check failed for "
                f"{len(reexport_facade_messages)} site(s) -- there is no "
                "baseline to update; fix the code instead:\n"
            )
            for message in reexport_facade_messages:
                print(message)
            print()
            return 1

        if updated_any:
            return 0

    target_literal_messages: list[str] = []
    if args.check_target_literals:
        if not target_literal_baseline_path.exists():
            print(
                f"Error: I1 target-literal baseline not found at "
                f"{target_literal_baseline_path}. Run "
                f"'check_import_boundaries.py --check-target-literals --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_target_literal_baseline(target_literal_baseline_path)
        target_literal_hits_by_file = scan_target_literals(
            packages, monorepo_root, shared_packages
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in target_literal_hits_by_file.items()
        }
        target_literal_messages = check_target_literal_ratchet(current_counts, baseline)
        target_literal_messages += check_identity_rules_hard_zero(
            target_literal_hits_by_file, baseline, monorepo_root
        )

    provider_conditional_messages: list[str] = []
    if args.check_provider_conditionals:
        if not provider_conditional_baseline_path.exists():
            print(
                f"Error: I6 provider-conditional baseline not found at "
                f"{provider_conditional_baseline_path}. Run "
                f"'check_import_boundaries.py --check-provider-conditionals --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_provider_conditional_baseline(
            provider_conditional_baseline_path
        )
        provider_hits_by_file = scan_provider_conditionals(
            packages, monorepo_root, taxonomy.language_packages
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in provider_hits_by_file.items()
        }
        provider_conditional_messages = check_provider_conditional_ratchet(
            current_counts, baseline
        )

    function_level_import_messages: list[str] = []
    if args.check_function_level_imports:
        if not function_level_import_baseline_path.exists():
            print(
                f"Error: function-level-import baseline not found at "
                f"{function_level_import_baseline_path}. The ratchet cannot run "
                f"without its frozen record; restore the file from version control.",
                file=sys.stderr,
            )
            return 2

        try:
            function_level_baseline = load_function_level_import_baseline(
                function_level_import_baseline_path
            )
        except FunctionLevelImportBaselineError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        function_level_hits_by_file = scan_function_level_imports(
            packages, monorepo_root, frozenset(function_level_baseline.counts)
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in function_level_hits_by_file.items()
        }
        function_level_import_messages = check_function_level_import_baseline_entries(
            function_level_baseline, packages, monorepo_root
        ) + check_function_level_import_ratchet(
            current_counts, function_level_baseline.counts
        )

    shared_vocabulary_messages: list[str] = []
    if args.check_shared_vocabulary:
        if not shared_vocabulary_baseline_path.exists():
            print(
                f"Error: G1 shared-vocabulary baseline not found at "
                f"{shared_vocabulary_baseline_path}. Run "
                f"'check_import_boundaries.py --check-shared-vocabulary --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_shared_vocabulary_baseline(shared_vocabulary_baseline_path)
        shared_vocabulary_hits_by_file = scan_shared_vocabulary(
            packages, monorepo_root, taxonomy.language_packages
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in shared_vocabulary_hits_by_file.items()
        }
        shared_vocabulary_messages = check_shared_vocabulary_ratchet(
            current_counts, baseline
        )

    shared_target_name_messages: list[str] = []
    if args.check_shared_target_names:
        if not shared_target_name_baseline_path.exists():
            print(
                f"Error: G2 shared-target-name baseline not found at "
                f"{shared_target_name_baseline_path}. Run "
                f"'check_import_boundaries.py --check-shared-target-names --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        shared_target_name_baseline = load_shared_target_name_baseline(
            shared_target_name_baseline_path
        )
        shared_target_name_hits_by_file = scan_shared_target_names(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in shared_target_name_hits_by_file.items()
        }
        shared_target_name_messages = check_shared_target_name_ratchet(
            current_counts, shared_target_name_baseline.counts
        ) + check_shared_target_name_reasons(shared_target_name_baseline)

    cross_package_vocabulary_messages: list[str] = []
    if args.check_cross_package_vocabulary:
        if not cross_package_vocabulary_baseline_path.exists():
            print(
                f"Error: G3 cross-package-vocabulary baseline not found at "
                f"{cross_package_vocabulary_baseline_path}. Run "
                f"'check_import_boundaries.py --check-cross-package-vocabulary "
                f"--update-baseline' first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        cross_package_vocabulary_baseline = load_cross_package_vocabulary_baseline(
            cross_package_vocabulary_baseline_path
        )
        cross_package_vocabulary_hits_by_file = scan_cross_package_vocabulary(
            packages, monorepo_root
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in cross_package_vocabulary_hits_by_file.items()
        }
        cross_package_vocabulary_messages = check_cross_package_vocabulary_ratchet(
            current_counts, cross_package_vocabulary_baseline.counts
        )

    own_target_name_messages: list[str] = []
    own_target_name_current_counts: dict[str, int] = {}
    if args.check_own_target_names:
        if not own_target_name_baseline_path.exists():
            print(
                f"Error: I4 own-target-name baseline not found at "
                f"{own_target_name_baseline_path}. Run "
                f"'check_import_boundaries.py --check-own-target-names --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_own_target_name_baseline(own_target_name_baseline_path)
        own_target_name_hits_by_package = scan_own_target_names(
            packages, monorepo_root, taxonomy.language_packages
        )
        own_target_name_current_counts = {
            package_name: len(own_target_name_hits_by_package.get(package_name, []))
            for package_name in taxonomy.language_packages
        }
        own_target_name_messages = check_own_target_name_ratchet(
            own_target_name_current_counts, baseline
        )

    if args.check_reexport_facades:
        if args.verbose:
            worklist = format_reexport_facade_worklist(
                reexport_facade_hits_by_module,
                monorepo_root,
                facade_modules=frozenset(args.facade_module),
                consumer_packages=frozenset(args.consumer_package),
            )
            print(f"Re-export-facade worklist ({len(worklist)} site(s)):")
            for line in worklist:
                print(line)
            print()

    # Report violations / ratchet failures
    if (
        non_allowlisted_violations
        or target_literal_messages
        or provider_conditional_messages
        or shared_package_provider_literal_messages
        or function_level_import_messages
        or shared_vocabulary_messages
        or shared_target_name_messages
        or cross_package_vocabulary_messages
        or own_target_name_messages
        or reexport_facade_messages
    ):
        mode = "Warning" if args.warn else "Error"

        if non_allowlisted_violations:
            print(
                f"{mode}: Found {len(non_allowlisted_violations)} import boundary violations:\n"
            )
            for violation in non_allowlisted_violations:
                print(format_violation(violation, monorepo_root))
                print()  # Blank line between violations

        if target_literal_messages:
            print(
                f"{mode}: I1 target-literal ratchet failed for "
                f"{len(target_literal_messages)} file(s):\n"
            )
            for message in target_literal_messages:
                print(message)
            print()

        if provider_conditional_messages:
            print(
                f"{mode}: I6 provider-conditional ratchet failed for "
                f"{len(provider_conditional_messages)} file(s):\n"
            )
            for message in provider_conditional_messages:
                print(message)
            print()

        if shared_package_provider_literal_messages:
            print(
                f"{mode}: shared-package provider-literal zero-tolerance check "
                f"failed for {len(shared_package_provider_literal_messages)} "
                f"occurrence(s) (no baseline -- any hit fails):\n"
            )
            for message in shared_package_provider_literal_messages:
                print(message)
            print()

        if function_level_import_messages:
            print(
                f"{mode}: function-level-import ratchet failed with "
                f"{len(function_level_import_messages)} finding(s):\n"
            )
            for message in function_level_import_messages:
                print(message)
            print()

        if shared_vocabulary_messages:
            print(
                f"{mode}: G1 shared-vocabulary ratchet failed for "
                f"{len(shared_vocabulary_messages)} file(s):\n"
            )
            for message in shared_vocabulary_messages:
                print(message)
            print()

        if shared_target_name_messages:
            print(
                f"{mode}: G2 shared-target-name ratchet failed for "
                f"{len(shared_target_name_messages)} file(s):\n"
            )
            for message in shared_target_name_messages:
                print(message)
            print()

        if cross_package_vocabulary_messages:
            print(
                f"{mode}: G3 cross-package-vocabulary ratchet failed for "
                f"{len(cross_package_vocabulary_messages)} file(s):\n"
            )
            for message in cross_package_vocabulary_messages:
                print(message)
            print()

        if own_target_name_messages:
            print(
                f"{mode}: I4 own-target-name ratchet failed for "
                f"{len(own_target_name_messages)} package(s):\n"
            )
            for message in own_target_name_messages:
                print(message)
            print()

        if reexport_facade_messages:
            print(
                f"{mode}: re-export-facade check failed for "
                f"{len(reexport_facade_messages)} site(s) (no baseline -- "
                f"any hit fails):\n"
            )
            for message in reexport_facade_messages:
                print(message)
            print()

        if args.warn:
            return 0
        return 1

    # Clean
    if args.check_provider_conditionals:
        shared_package_list = ", ".join(shared_packages)
        print(
            "Shared-package provider-literal zero-tolerance check: 0 hits "
            f"({shared_package_list})."
        )

    if args.check_reexport_facades:
        print("Re-export-facade check: 0 hits.")

    if args.check_own_target_names:
        print("I4 own-target-name live counts (per registered language package):")
        for package_name in sorted(own_target_name_current_counts):
            print(f"  {package_name}: {own_target_name_current_counts[package_name]}")
        if not own_target_name_current_counts:
            print("  (no registered language package discovered)")

    if args.verbose:
        print("No import boundary violations found.", file=sys.stderr)
        if args.check_target_literals:
            print("No I1 target-literal ratchet regressions found.", file=sys.stderr)
        if args.check_provider_conditionals:
            print(
                "No I6 provider-conditional ratchet regressions found.", file=sys.stderr
            )
        if args.check_function_level_imports:
            print(
                "No function-level-import ratchet regressions found.", file=sys.stderr
            )
        if args.check_shared_vocabulary:
            print(
                "No G1 shared-vocabulary ratchet regressions found.", file=sys.stderr
            )
        if args.check_shared_target_names:
            print(
                "No G2 shared-target-name ratchet regressions found.", file=sys.stderr
            )
        if args.check_cross_package_vocabulary:
            print(
                "No G3 cross-package-vocabulary ratchet regressions found.",
                file=sys.stderr,
            )
        if args.check_own_target_names:
            print(
                "No I4 own-target-name ratchet regressions found.", file=sys.stderr
            )
        if args.check_reexport_facades:
            print("No re-export-facade hits found.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
