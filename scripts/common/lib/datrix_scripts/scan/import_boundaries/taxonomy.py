"""Generator taxonomy, boundary rule model, package scan and the allowlist."""

from __future__ import annotations

import ast
import functools
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.registered_targets import discover_all_package_locations
from datrix_scripts.scan.import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_COMMAND,
    LANGUAGE_CORE_PACKAGES,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    self_test_check,
)

#: A workspace directory is a manifest-bearing package when it holds a ``pyproject.toml``.
_MANIFEST_MARKER: frozenset[PackageMarker] = frozenset({PackageMarker.PYPROJECT})


@dataclass(frozen=True)
class BoundaryRule:
    """Per-package boundary rule: forbidden prefixes plus subtree carve-outs.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of ``allowed_subtrees`` -- used where a package may reach
    a narrow, reviewed part of an otherwise-forbidden package (the test
    harness's kernel import, the semantic layer's migration SQL lowering).
    """

    forbidden_prefixes: tuple[str, ...]
    allowed_subtrees: frozenset[str] = frozenset()


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

# DAL generator's own entry-point-group axis -- a SEPARATE, cross-cutting
# registration mechanism from the four taxonomy groups above (mirrors
# datrix_common.plugin.registry's DGEN_FILE_LANGUAGES_GROUP/
# DGEN_ITERATION_TARGETS_GROUP/DGEN_CONTEXT_NAMESPACES_GROUP, plus
# datrix_codegen_kernel.dgen.target_registry's
# DGEN_GENERATOR_TARGETS_GROUP -- read for the canonical spellings only,
# same as the four taxonomy groups; this scanner does not import either
# module). Confirmed against the real manifests (not assumed): every
# language, every platform, the frontend targets, SQL, AND the shared
# packages datrix-codegen-kernel and datrix-codegen-common register into this
# axis, so its presence carries NO taxonomy signal -- folding it into
# SHARED_PACKAGE_CLASSIFIER_GROUPS would misclassify every one of those as
# shared, and treating it as "unrecognized" would make
# discover_shared_packages abort on the shared packages themselves.
_DGEN_AUXILIARY_ENTRY_POINT_GROUPS: frozenset[str] = frozenset(
    {
        "datrix.dgen_file_languages",
        "datrix.dgen_iteration_targets",
        "datrix.dgen_context_namespaces",
        "datrix.dgen_generator_targets",
    }
)

# The parser seam (datrix_common.protocols.parser's PARSERS_GROUP, read for
# its canonical spelling only): datrix-language declares its DSL and stdlib
# parsers under it so the packages below the parser reach them without an
# import. It names no generation target, so it carries no taxonomy signal.
_PARSER_ENTRY_POINT_GROUPS: frozenset[str] = frozenset({"datrix.parsers"})

# Every datrix.-namespaced entry-point group that is neither a taxonomy group
# nor unrecognized.
_NON_TAXONOMY_ENTRY_POINT_GROUPS: frozenset[str] = (
    _DGEN_AUXILIARY_ENTRY_POINT_GROUPS | _PARSER_ENTRY_POINT_GROUPS
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
    for _candidate, manifest, groups in _manifest_entry_point_groups(base_dir):
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
    * DAL generator's own cross-cutting registration axis
      (``_DGEN_AUXILIARY_ENTRY_POINT_GROUPS`` -- ``datrix_common.plugin.registry``'s
      ``DGEN_FILE_LANGUAGES_GROUP``/``DGEN_ITERATION_TARGETS_GROUP``/
      ``DGEN_CONTEXT_NAMESPACES_GROUP``, plus
      ``datrix_codegen_kernel.dgen.target_registry.DGEN_GENERATOR_TARGETS_GROUP``)
      is registered by packages spanning EVERY taxonomy class alike --
      the shared ``datrix-codegen-kernel`` and ``datrix-codegen-common``,
      every language, every platform, the frontend targets, and SQL all
      register into it, so its presence says nothing about which of the four
      taxonomy groups a package belongs to (or doesn't). Confirmed against the
      real monorepo manifests, not assumed: ``datrix-codegen-kernel``
      registers ONLY ``dgen_file_languages``/``dgen_iteration_targets``
      and ``datrix-codegen-common`` ONLY ``dgen_iteration_targets``; both
      are shared packages.
    * The parser seam (``_PARSER_ENTRY_POINT_GROUPS``) through which
      datrix-language supplies its parsers to the packages below it names no
      generation target, so it is no taxonomy signal either.

    A package registering a NON-EMPTY [project.entry-points] table whose
    ``datrix.``-namespaced group name(s) are ALL outside the four known
    taxonomy groups AND outside the known DAL generator auxiliary axis is
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
            known DAL generator auxiliary axis.
    """
    root_by_dir: dict[Path, str] = {info.root: name for name, info in packages.items()}
    shared: set[str] = set()
    for candidate, manifest, groups in _manifest_entry_point_groups(base_dir):
        if set(groups) & SHARED_PACKAGE_CLASSIFIER_GROUPS:
            continue  # a real generator/platform/language/extension package
        _require_classifiable(manifest, groups)
        import_root = root_by_dir.get(candidate)
        if import_root is not None:
            shared.add(import_root)
    return tuple(sorted(shared))


def _manifest_entry_point_groups(
    base_dir: Path,
) -> Iterator[tuple[Path, Path, dict[str, object]]]:
    """``(package dir, manifest, [project.entry-points] table)`` for every
    ``datrix-*`` package directory carrying a ``pyproject.toml``, read one at
    a time; a manifest without the table yields an empty one.

    Raises:
        GeneratorTaxonomyError: A manifest is unparseable, or its
            ``[project.entry-points]`` is not a table.
    """
    for candidate in workspace_package_dirs(base_dir, any_of=_MANIFEST_MARKER):
        manifest = candidate / PackageMarker.PYPROJECT
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
        yield candidate, manifest, groups


def _require_classifiable(manifest: Path, groups: dict[str, object]) -> None:
    """Refuse a manifest registering no taxonomy group but a ``datrix.``
    group outside the known non-taxonomy axes (the DAL generator
    registration axis and the parser seam).

    Raises:
        GeneratorTaxonomyError: The package cannot be classified.
    """
    unrecognized_datrix_groups = {
        group
        for group in groups
        if group.startswith("datrix.")
        and group not in _NON_TAXONOMY_ENTRY_POINT_GROUPS
    }
    if unrecognized_datrix_groups:
        raise GeneratorTaxonomyError(
            f"{manifest}: registers entry-point group(s) "
            f"{sorted(unrecognized_datrix_groups)}, none of which is "
            f"{sorted(SHARED_PACKAGE_CLASSIFIER_GROUPS)} (the four taxonomy "
            f"groups) or {sorted(_NON_TAXONOMY_ENTRY_POINT_GROUPS)} "
            f"(DAL generator's registration axis and the parser seam). This package "
            f"cannot be classified as shared or as a taxonomy member -- add an "
            f"explicit classification before the I1/I6 shared-layer ratchets "
            f"can be trusted to scan (or skip) it."
        )


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
        # language generator: every target-neutral fact it consumes (the DAL generator engine,
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
        # scaffolding generator: the DAL generator engine, the serverless plan and the NoSQL
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
        # target-neutral service they consume (the DAL generator engine, the provider library,
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
        # implementations reach it only through the datrix.parsers entry point
        # (datrix_testing.parsing.register_installed_parsers), never through
        # an import.
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
        # discovery, the shared route and runtime derivations, the DAL generator data
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
        # tests reach the parser only through the datrix.parsers entry point.
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
        # auth-contract lowering) sits on the core and on the migration
        # package's SQL lowering, which it runs to refuse at analysis a column
        # default no registered dialect can express. The parser, the CLI and
        # the test harness depend on it, and every generator sits beside it on
        # the core, so an import of any of them would close a cycle or couple
        # two siblings. The rest of the migration package (snapshot, diff,
        # policy, ledger, state store) stays fenced: the analyzer lowers
        # expressions, it never reads schema state. Its tests reach the parser
        # only through the datrix.parsers entry point.
        "datrix_semantic": BoundaryRule(
            forbidden_prefixes=(
                "datrix_language",
                "datrix_cli",
                "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
                "datrix_extensions",
                "datrix_migration",
            ),
            allowed_subtrees=frozenset({"datrix_migration.sql_lowering"}),
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
    return {
        import_name: PackageInfo(name=import_name, root=import_dir.parents[1], src_dir=import_dir)
        for import_name, import_dir in discover_all_package_locations(base_dir).items()
    }


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

    # Every scanned file is held to the same allowed_subtrees -- src/, tests/,
    # fixtures/, helpers/ and the root-level files alike. There is no
    # test-tree carve-out: a subtree forbidden in production code is
    # forbidden in tests too.
    for py_file in boundary_scan_files(package_info):
        if verbose:
            print(f"Scanning: {py_file.relative_to(monorepo_root)}", file=sys.stderr)
        for line_num, imported_module in _read_imports_or_exit(py_file, monorepo_root):
            forbidden_prefix = _first_forbidden_prefix(
                package_info.name, imported_module, rule
            )
            if forbidden_prefix is None:
                continue
            violations.append(
                Violation(
                    file_path=py_file,
                    line_number=line_num,
                    imported_module=imported_module,
                    source_package=package_info.name,
                    forbidden_prefix=forbidden_prefix,
                )
            )

    return violations


#: Trees under a package root, besides ``src/<package>``, whose ``.py`` files
#: the boundary scan reads.
_BOUNDARY_SCAN_DIRS: tuple[str, ...] = ("tests", "fixtures", "helpers")


def boundary_scan_files(package_info: PackageInfo) -> list[Path]:
    """Every ``.py`` file the boundary scan holds to *package_info*'s rule.

    The ``src/`` tree, the ``tests/``, ``fixtures/`` and ``helpers/`` trees,
    and the package's root-level ``*.py`` files (``conftest.py`` and the
    like). pytest loads a root ``conftest.py`` for every test of the package,
    so an import there is the package's own import; a scan that skipped it
    would let a forbidden import hide one directory above ``tests/``.
    """
    files = sorted(package_info.src_dir.rglob("*.py"))
    files.extend(sorted(package_info.root.glob("*.py")))
    for dir_name in _BOUNDARY_SCAN_DIRS:
        optional_dir = package_info.root / dir_name
        if optional_dir.is_dir():
            files.extend(sorted(optional_dir.rglob("*.py")))
    return files


def _read_imports_or_exit(py_file: Path, monorepo_root: Path) -> list[tuple[int, str]]:
    """The imports of *py_file*; exits 2 when it cannot be read or parsed,
    because a policed file the scan cannot read would be a silent blind spot."""
    rel_path = py_file.relative_to(monorepo_root)
    try:
        return extract_imports_from_file(py_file)
    except SyntaxError as e:
        print(
            f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
            f"A policed file that cannot be parsed would escape this scan "
            f"(a silent blind spot); fix its syntax or encoding.",
            file=sys.stderr,
        )
        sys.exit(2)
    except (OSError, UnicodeDecodeError) as e:
        print(
            f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
            f"cannot be read would escape this scan; resolve the read error.",
            file=sys.stderr,
        )
        sys.exit(2)


def _first_forbidden_prefix(
    source_package: str, imported_module: str, rule: BoundaryRule
) -> str | None:
    """The first of *rule*'s forbidden prefixes *imported_module* violates, or
    ``None`` when the import is permitted."""
    for forbidden_prefix in rule.forbidden_prefixes:
        if is_forbidden_import(
            source_package, imported_module, forbidden_prefix, rule.allowed_subtrees
        ):
            return forbidden_prefix
    return None


def load_allowlist(allowlist_path: Path) -> list[AllowlistEntry]:
    """Load allowlist entries from TOML file.

    Args:
        allowlist_path: Path to allowlist TOML file

    Returns:
        List of allowlist entries (empty if file doesn't exist)
    """
    if not allowlist_path.exists():
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


@functools.cache
def _real_repo_rules() -> tuple[GeneratorTaxonomy, dict[str, BoundaryRule]]:
    """The taxonomy discovered from THIS monorepo's manifests, and its rules.

    The rule-model self-tests (1-4) assert over the real repository, so they
    resolve it the same way main() does for a no-``--base-dir`` run, once per
    process however many of them run.
    """
    taxonomy = discover_generator_taxonomy(WORKSPACE_DIR)
    return taxonomy, build_boundary_rules(taxonomy)


#: Formerly carved out of datrix_codegen_common for platforms, SQL and
#: component; now in the kernel. Each must be forbidden in src/ AND tests/.
_FORMER_CARVE_OUT_MODULES: tuple[str, ...] = (
    "datrix_codegen_common.dgen",
    "datrix_codegen_common.dgen.compiler",
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
    "datrix_codegen_kernel.dgen.compiler",
    "datrix_codegen_kernel.dashboards.builder",
    "datrix_codegen_kernel.algorithms.serverless",
    "datrix_codegen_kernel.context_models.migration",
    "datrix_codegen_kernel.orchestration.migration_adapter",
    "datrix_codegen_kernel.enums",
    "datrix_codegen_kernel.platform.runtime",
    "datrix_codegen_kernel.pooling.contract",
    "datrix_codegen_kernel.parity.domain_declaration",
    "datrix_codegen_kernel.generation.dgen_ir",
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
    report_step(
        "Self-test 1/24: platforms, SQL and component forbid "
        "datrix_codegen_common in tests/ exactly as in src/; a package's "
        "root-level files are held to its rule too"
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
    ok &= _self_test_root_level_files_scanned()

    return ok


def _self_test_root_level_files_scanned() -> bool:
    """A forbidden import in a package's root-level ``conftest.py`` is a
    violation located in that file, and the same file importing nothing
    forbidden is clean -- the root of a package is no hiding place."""
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"root-level-scan-{uuid.uuid4().hex}"
    package_root = tmp_root / "datrix-root-guard"
    src_dir = package_root / "src" / "datrix_root_guard"
    src_dir.mkdir(parents=True, exist_ok=True)
    try:
        (src_dir / "__init__.py").write_text("", encoding="utf-8")
        conftest = package_root / "conftest.py"
        package_info = PackageInfo(
            name="datrix_root_guard", root=package_root, src_dir=src_dir
        )
        rules = {"datrix_root_guard": BoundaryRule(forbidden_prefixes=("datrix_language",))}
        absent_before = conftest not in boundary_scan_files(package_info)
        conftest.write_text("", encoding="utf-8")
        ok &= _check(
            "a package's root-level conftest.py is in the boundary scan scope",
            absent_before and conftest in boundary_scan_files(package_info),
        )
        conftest.write_text(
            "from datrix_language.registration import register_all\n", encoding="utf-8"
        )
        planted = scan_package_for_violations(package_info, tmp_root, False, rules)
        ok &= _check(
            "a forbidden import planted in a root-level conftest.py is one violation there",
            [(v.file_path, v.line_number, v.imported_module) for v in planted]
            == [(conftest, 1, "datrix_language.registration")],
        )
        conftest.write_text(
            "from datrix_testing.parsing import register_installed_parsers\n",
            encoding="utf-8",
        )
        ok &= _check(
            "the same root-level conftest.py importing nothing forbidden is clean",
            scan_package_for_violations(package_info, tmp_root, False, rules) == [],
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
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
    """Subtree matching is exact-or-child (not raw prefix), and each
    carve-out (datrix_testing's kernel, datrix_semantic's migration SQL
    lowering) admits only its own subtree and never leaks to a package that
    did not opt in."""
    report_step("Self-test 2/24: dotted-boundary precision and carve-out non-leakage")
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

    # The semantic layer reaches the migration package's SQL lowering and
    # nothing else of it; the migration package never reaches back.
    ok &= _check(
        "datrix_semantic may import datrix_migration.sql_lowering.lower",
        not _rule_forbids(rules, "datrix_semantic", "datrix_migration.sql_lowering.lower"),
    )
    ok &= _check(
        "datrix_semantic still forbids datrix_migration.snapshot_diff",
        _rule_forbids(rules, "datrix_semantic", "datrix_migration.snapshot_diff"),
    )
    ok &= _check(
        "datrix_semantic's lowering carve-out does not leak to datrix_migration.sql_lowering_other",
        _rule_forbids(rules, "datrix_semantic", "datrix_migration.sql_lowering_other"),
    )
    ok &= _check(
        "datrix_migration still forbids datrix_semantic",
        _rule_forbids(rules, "datrix_migration", "datrix_semantic.analyzer"),
    )

    return ok


def _self_test_sql_and_component_coverage(rules: dict[str, BoundaryRule]) -> bool:
    """The rule table covers datrix_codegen_sql and datrix_codegen_component,
    each enforcing the sibling-language prohibition absolutely."""
    report_step("Self-test 3/24: SQL and Component boundary rule coverage")
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
        "datrix_codegen_kernel.dgen.compiler",
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
        "datrix_codegen_common.dgen.compiler",
        "datrix_codegen_common.algorithms.nosql_connection",
    ):
        ok &= _check(
            f"Component codegen_common import forbidden: {imported}",
            _rule_forbids(rules, "datrix_codegen_component", imported),
        )
    for imported in (
        "datrix_codegen_kernel.dgen.compiler",
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
            "datrix_codegen_angular.dgen",
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
        ("datrix_codegen_angular", "datrix_codegen_flutter.dgen"),
        ("datrix_codegen_flutter", "datrix_codegen_angular.dgen"),
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
    report_step(
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
    """Run the plain import-boundary scan as a subprocess against an isolated fixture."""
    return subprocess.run(
        [
            *CLI_COMMAND,
            "--base-dir",
            str(tmp_root),
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
    report_step(
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


def _self_test_shared_package_classification_fixture() -> bool:
    """``discover_shared_packages`` excludes a taxonomy-classified package,
    includes an entry-point-less package that has a real ``src/`` tree, and
    raises ``GeneratorTaxonomyError`` -- naming the package and the
    unrecognized group -- for a package registering only an unrecognized
    entry-point group, even with no ``src/`` tree at all to scan (the
    fail-loud check fires from the manifest walk alone)."""
    report_step(
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
            tmp_root, "datrix-parser-p", "datrix_parser_p",
            entry_point_groups={"datrix.parsers": {"p": "ParserFactory"}},
        )
        parser_src = tmp_root / "datrix-parser-p" / "src" / "datrix_parser_p"
        parser_src.mkdir(parents=True, exist_ok=True)
        (parser_src / "__init__.py").write_text("", encoding="utf-8")
        packages = discover_packages(tmp_root)
        ok &= _check(
            "a package registering only the datrix.parsers seam is classified shared",
            "datrix_parser_p" in discover_shared_packages(tmp_root, packages),
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


def _self_test_non_utf8_source_handling() -> bool:
    """A non-UTF-8 ``.py`` file under a scanned tree is reported by path and
    exits 2, exactly like every other unreadable/unparseable file -- never an
    uncaught ``UnicodeDecodeError`` traceback. ``UnicodeDecodeError`` is a
    ``ValueError`` subclass, so a bare ``except (SyntaxError, OSError)`` does
    not catch it; every policed-file read site widens its ``OSError`` clause
    to ``(OSError, UnicodeDecodeError)`` so a stray non-UTF-8 file fails
    closed with the same clean message every other bad file gets, instead of
    crashing the whole scan."""
    report_step(
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


def self_test_checks() -> list[NamedCheck]:
    """The rule-model and boundary-scan self-tests, each a check the CLI's ``--self-test`` runs.

    The rule-model checks resolve the real repository's taxonomy when they run, so a manifest
    that cannot be read fails those checks (``GeneratorTaxonomyError``), not the whole list.
    """
    return [
        self_test_check(
            lambda: _self_test_no_testkit_carve_out(*_real_repo_rules()), "no_testkit_carve_out"
        ),
        self_test_check(
            lambda: _self_test_dotted_precision_and_carveout(_real_repo_rules()[1]),
            "dotted_precision_and_carveout",
        ),
        self_test_check(
            lambda: _self_test_sql_and_component_coverage(_real_repo_rules()[1]),
            "sql_and_component_coverage",
        ),
        self_test_check(
            lambda: _self_test_platform_to_platform_prohibition(*_real_repo_rules()),
            "platform_to_platform_prohibition",
        ),
        self_test_check(_self_test_platform_cli_non_vacuity),
        self_test_check(_self_test_shared_package_classification_fixture),
        self_test_check(_self_test_non_utf8_source_handling),
    ]
