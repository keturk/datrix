"""Dependency-declaration-only-path ratchet (W4 / design-principle F5 enforcement).

Enumerates registered languages from the ``datrix.languages`` entry-point group at
runtime -- via ``datrix_scripts.registered_targets.registered_language_names()``, never a
hardcoded list -- and reports, per language, every site in the ``src/`` tree
(and ``templates/`` tree) of EVERY package implementing that language -- its
backend and each language core the backend requires -- that decides a
dependency PACKAGE NAME outside the language's ``generation/dependency_tables.py``
table. The catalog universe is the union of those packages' ``defaults.yaml``
files, so a decision site that moved into a core is matched against the catalog
it decides from.

This is the permanent census for the declared-table migration: a language's
migration is complete when this scan reports ZERO out-of-table sites for that
package -- never when a hand-written list in a task description is exhausted.
It lands seeded at the LIVE out-of-table count as a decrease-only ratchet, so
it is green immediately and each migration task decrements it by exactly the
number of sites it converts, in the same change.

The unit this scan counts is a dependency-SET decision site -- a place that
SELECTS OR RETURNS dependency package names for a generated manifest -- never
a bare catalog-name-shaped string literal anywhere in the tree. An earlier
version of this scanner matched any string literal equal to a registered
catalog package name, anywhere under ``src/`` and ``templates/``; that
over-matched by roughly two orders of magnitude (module-authoring constants
like a cache-ENGINE identifier set, or an import-deduplication helper's
MODULE-name constants, happen to share a spelling with a real package name
without ever deciding a manifest's dependency set) and under a corpus that
size a language's migration could never structurally reach zero. Both passes
below are scoped to the actual decision surface instead.

Two structural detection passes, neither a text regex over raw source:
1. Python source: for every ``.py`` file under the language's ``src/`` tree,
   AST-walk for string-literal ``ast.Constant`` nodes whose value is a member
   of that language's registered ``DependencyCatalog`` package universe (read
   from the same ``defaults.yaml`` the language's own generators resolve
   versions against) -- but ONLY when the literal sits inside (a) the body of
   a ``get_dependencies``/``get_npm_dependencies``/``get_nuget_dependencies``/
   ``_collect_*_deps``-shaped function at any nesting depth, or (b) a
   module-TOP-LEVEL (never class- or function-nested) assignment whose target
   name is shaped the same way -- e.g. ``ENGINE_PACKAGE_NAMES``,
   ``EMAIL_COORDINATES``. Both shapes are recognized by a documented
   whole-token naming vocabulary, ``_DEPENDENCY_DECISION_NAME_TOKENS`` --
   never a hardcoded function/constant-name allowlist that would silently
   miss a new one. A literal elsewhere in the file (a cache-engine identifier,
   an import-module-name constant, an unrelated docstring) is not a decision
   site and is not counted, by design.
2. Jinja templates: parse every ``.j2`` file under the language's
   ``templates/`` tree into its Jinja AST and take the ``nodes.Const``
   literals that DECIDE a dependency -- a version-map subscript key (the
   ``'pkg'`` of ``v['pkg']``), the needle of a membership test against a
   decision-named collection (``'pkg' in deps``), or a literal assigned to a
   decision-named variable (``{% set npm_deps = [...] %}``) -- for the same
   catalog-membership match: the structural analogue of the Python pass's
   decision-span gating. A literal in any other expression position (an
   equality test of a parameter's pipe kind that happens to spell a package
   name) decides nothing and is not counted. Raw ``TemplateData`` text (the literal characters between tags) is
   deliberately NOT scanned by containment: it degrades to a text search over
   a template's entire RENDERED OUTPUT, including plain generated code
   (``import stripe`` in a payment-client template) and even doc comments
   (a doc comment explaining why a package coordinate is NOT yet used was
   observed matching under the old approach) -- none of that is a
   dependency-set decision.

A literal passed straight to a ``DependencyQualifier(...)`` call is never
counted in either position: it is a qualifier value (an engine or vendor on
one axis) selecting rows of the declared table, not a package decision, even
when it shares a package's spelling.

Built-in non-vacuity self-test, every invocation: this module names no
registered target (``datrix_scripts.registered_targets.self_test_gate_names_no_target``);
a synthetic two-language
package tree proves the scan finds exactly its planted out-of-table sites and
that moving a planted site into a synthetic ``dependency_tables.py`` drops the
count by exactly one; a synthetic Jinja template proves the template pass is
independently exercised, and counts its three decision shapes but not an
equality test against an unrelated attribute; a synthetic non-qualifying
reference proves the narrowing itself (a second, non-qualifying use of the
same planted literal does not add a second site); a fixture language split
into a backend and a core proves a decision site in the core is found against
the backend's catalog and missed by a backend-only scan; a live-tree check
proves every registered language's real catalog contains every package its
real declared table names and that a real declared name planted into a
decision site is reported against it; a qualifier value is not counted while
a bare literal of the same name is; and, for every registered language, every
reported site is a catalog literal the earlier, over-broad matcher also finds,
while at least one real catalog literal it finds is excluded.
Refuses to run (exit 2) with fewer than two registered languages.

Usage:
    python dependency_declaration_ratchet.py
    python dependency_declaration_ratchet.py --debug
    python dependency_declaration_ratchet.py --self-test
    python dependency_declaration_ratchet.py --update-baseline
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
from typing import Final

import jinja2
import jinja2.nodes
import yaml
from datrix_common.config.project.catalog import DependencyCatalog

from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.registered_targets import (
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
    registered_language_names,
    self_test_gate_names_no_target,
)

logger = logging.getLogger(__name__)

DATRIX_DIR: Final[Path] = SHOWCASE_DIR
RATCHET_BASELINE_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "dependency-declaration-ratchet-baseline.json"
)

#: Relative path, under a language package's `src/datrix_codegen_<lang>/` root,
#: of the ONE module a dependency-name literal is allowed to live in.
_DECLARED_TABLE_RELATIVE_PATH: Final[Path] = Path("generation") / "dependency_tables.py"

#: The one filename every language package's dependency version catalog ships
#: as, sitting directly at the package's own `src/datrix_codegen_<lang>/` root
#: -- the same file `datrix_codegen_kernel.generation.generator.Generator
#: .get_project_defaults()` loads via `importlib.resources`. A language with no
#: such file has declared no
#: dependency catalog at all, which is a legitimate empty package universe --
#: not an error -- so no literal can ever match for it.
_DEFAULTS_YAML_NAME: Final[str] = "defaults.yaml"
_TEMPLATES_SUBDIR_NAME: Final[str] = "templates"

#: Jinja's `Operand.op` spellings of a membership test (`in` / `not in`).
_JINJA_MEMBERSHIP_OPS: Final[frozenset[str]] = frozenset({"in", "notin"})

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The keyword a declared-table row names its package with
#: (`DependencyRow(package="...")`) -- read structurally by the live
#: non-vacuity check, which takes its real package names from the declared
#: tables rather than from a pinned coordinate that a migration invalidates.
_DECLARED_ROW_PACKAGE_KEYWORD: Final[str] = "package"

#: The typed predicate (`datrix_codegen_common.generation.dependency_dsl
#: .DependencyQualifier`) a generator narrows a declared-table lookup with; a
#: literal passed to it is a qualifier value, never a package decision.
_QUALIFIER_CALL_NAME: Final[str] = "DependencyQualifier"

#: Whole snake_case tokens (an identifier split on `_`, never a substring
#: search) that mark a function or module-level constant as a dependency-SET
#: decision site. Empirically derived by investigating every real
#: out-of-table site the earlier, over-broad matcher reported across the
#: registered language packages: the
#: `get_dependencies`/`get_npm_dependencies`/`_collect_*_deps`-shaped
#: functions, PLUS their module-level table equivalents that investigation
#: found necessary to include for the count to be non-vacuous across every
#: language -- a package-registry coordinate map is conventionally named
#: `*_COORDINATES` / `*_COORDINATE` rather than `*_PACKAGE_NAMES`, and several
#: genuine decision functions/constants in
#: Python/TypeScript use "package"/"deps" without a `get_`/`collect_` prefix
#: (e.g. `_append_cache_helper_dependencies`, `deps_from_cache`,
#: `_resolve_native_helper_packages`, `_BACKEND_PACKAGES_FOR_ENGINE`).
#: Token, not substring, matching means `resolve_cache_engine` and
#: `SUPPORTED_CACHE_ENGINES` -- a cache-ENGINE identifier set, not a package
#: decision, and the exact false positive this narrowing exists to fix --
#: do NOT match ("engine" and "engines" are not in this vocabulary).
#: This is a naming-shape heuristic, not an exhaustive semantic analysis: a
#: real decision site named entirely outside this vocabulary (e.g. a future
#: function called `_wire_up_stripe`) is under-counted until it is renamed or
#: this vocabulary is deliberately extended here -- accepted per this
#: module's own "under-reporting is as dangerous as over-reporting, so state
#: the rule" discipline, in preference to a hardcoded per-function allowlist
#: that would drift silently out of sync with the code it polices.
_DEPENDENCY_DECISION_NAME_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "dependency",
        "dependencies",
        "deps",
        "package",
        "packages",
        "coordinate",
        "coordinates",
    }
)

#: Self-test-only synthetic identifiers, chosen to be unmistakably not one of
#: the real registered languages or catalog packages -- proving the scan is
#: driven entirely by its injected package tree, never a hardcoded literal.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_dep_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_dep_lang_b"
_SELF_TEST_PACKAGE_A: Final[str] = "self-test-dep-package-a"
_SELF_TEST_PACKAGE_B: Final[str] = "self-test-dep-package-b"
_SELF_TEST_LANGUAGE_TMPL: Final[str] = "self_test_dep_lang_tmpl"
_SELF_TEST_TEMPLATE_PACKAGE: Final[str] = "self-test-dep-template-package"
_SELF_TEST_LANGUAGE_CORE: Final[str] = "self_test_dep_lang_split"
_SELF_TEST_CORE_PACKAGE: Final[str] = "self-test-dep-core-package"

@dataclass(frozen=True)
class OutOfTableSite:
    """One dependency-name decision site found outside a language's declared table."""

    language: str
    file_path: Path
    line_number: int
    package_name: str


# ---------------------------------------------------------------------------
# Catalog resolution
# ---------------------------------------------------------------------------


def _catalog_package_names(language_src_dir: Path, language: str) -> frozenset[str]:
    """The language's registered dependency-catalog package universe.

    Reads the same `defaults.yaml` shape `datrix_codegen_kernel.generation.generator
    .Generator.get_project_defaults()` loads for real generation, then hands
    the parsed `dependencies.<language>` mapping to `DependencyCatalog` itself
    (`packages_for`) rather than reading its keys directly, so the scanner's
    notion of "a dependency package name" can never drift from the catalog
    class the language's own generators resolve versions against.

    A missing `defaults.yaml`, or one with no `dependencies.<language>`
    section, is a legitimate EMPTY package universe -- not
    an error, and not a silently-swallowed lookup failure, because no key was
    ever expected to resolve to a default.

    Args:
        language_src_dir: The language package's `src/datrix_codegen_<lang>`
            root (where `defaults.yaml` lives, sibling to `generation/`).
        language: The registered language name (e.g. `"typescript"`), also the
            key `defaults.yaml`'s `dependencies` mapping uses for this package.

    Returns:
        Every package name this language's catalog declares a version for.

    Raises:
        ValueError: If `defaults.yaml` (or its `dependencies`/
            `dependencies.<language>` sections) is present but malformed --
            a real authoring defect, never silently narrowed to "no packages".
    """
    defaults_path = language_src_dir / _DEFAULTS_YAML_NAME
    if not defaults_path.is_file():
        return frozenset()

    raw = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    if raw is None:
        return frozenset()
    if not isinstance(raw, dict):
        raise ValueError(
            f"{defaults_path} must contain a YAML mapping, got {type(raw).__name__}. "
            "Expected the same defaults.yaml shape Generator.get_project_defaults() "
            "parses. Fix: correct the file's top-level structure."
        )

    dependencies_section = raw.get("dependencies", {})
    if not isinstance(dependencies_section, dict):
        raise ValueError(
            f"{defaults_path} key 'dependencies' must be a mapping of "
            f"language -> {{package: version}}, got {type(dependencies_section).__name__}. "
            "Fix: correct the 'dependencies' section's structure."
        )

    language_packages = dependencies_section.get(language, {})
    if not isinstance(language_packages, dict):
        raise ValueError(
            f"{defaults_path} key 'dependencies.{language}' must be a mapping of "
            f"package -> version, got {type(language_packages).__name__}. "
            f"Fix: correct the 'dependencies.{language}' section's structure."
        )

    catalog = DependencyCatalog({language: language_packages})
    return frozenset(catalog.packages_for(language))


# ---------------------------------------------------------------------------
# Structural detection passes
# ---------------------------------------------------------------------------


def _is_declared_table_file(candidate: Path, language_src_dir: Path) -> bool:
    """True when *candidate* IS the language's own `generation/dependency_tables.py`.

    Compared by path relative to `language_src_dir`, resolved (never a
    filename-only or substring match), so a same-named file anywhere else in
    the tree is never mistaken for the one declared-table module.
    """
    declared_table = (language_src_dir / _DECLARED_TABLE_RELATIVE_PATH).resolve()
    return candidate.resolve() == declared_table


def _tokenize_identifier(identifier: str) -> frozenset[str]:
    """Split a snake_case identifier into its lower-cased, non-empty tokens."""
    return frozenset(token for token in identifier.lower().split("_") if token)


def _is_dependency_decision_name(identifier: str) -> bool:
    """True when *identifier* (a function or module-constant name) is shaped
    like a dependency-SET decision site -- see `_DEPENDENCY_DECISION_NAME_TOKENS`.

    Whole-token membership, never a substring search: `resolve_cache_engine`
    does not match ("engine" is not a member), `_collect_cache_deps` does
    ("deps" is).
    """
    return bool(_tokenize_identifier(identifier) & _DEPENDENCY_DECISION_NAME_TOKENS)


@dataclass(frozen=True)
class _LineSpan:
    """An inclusive `[start, end]` source-line range."""

    start: int
    end: int

    def contains(self, lineno: int) -> bool:
        return self.start <= lineno <= self.end


def _dependency_decision_function_spans(tree: ast.Module) -> list[_LineSpan]:
    """Every `FunctionDef`/`AsyncFunctionDef` (at any nesting depth -- a free
    function or a method) whose name matches the dependency-decision naming
    shape, as the line span covering its entire body."""
    spans: list[_LineSpan] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_dependency_decision_name(
            node.name
        ):
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            spans.append(_LineSpan(node.lineno, end))
    return spans


def _dependency_decision_module_constant_spans(tree: ast.Module) -> list[_LineSpan]:
    """Every module-TOP-LEVEL `Assign`/`AnnAssign` (a direct child of the
    module body -- never nested inside a function or class) whose single
    `Name` target matches the dependency-decision naming shape, as the line
    span covering its value expression.

    Module-level only, per this scan's own documented scope: a class-body
    constant with the same naming shape is not currently covered (no live
    instance required it at authoring time; see this module's docstring's
    "under-reporting is as dangerous as over-reporting" discipline).
    """
    spans: list[_LineSpan] = []
    for node in tree.body:
        target_name: str | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
        if target_name is not None and _is_dependency_decision_name(target_name):
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            spans.append(_LineSpan(node.lineno, end))
    return spans


def _qualifier_argument_constants(tree: ast.Module) -> set[int]:
    """``id()`` of every string constant passed straight to a
    ``DependencyQualifier(...)`` call.

    Such a literal names a qualifier VALUE (an engine or vendor on one axis)
    that selects rows of the declared table -- the declaration-only path
    itself -- so it decides no package even when the engine shares its
    spelling with one (the ``redis`` engine and the ``redis`` package).
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name != _QUALIFIER_CALL_NAME:
            continue
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        found.update(id(argument) for argument in arguments if isinstance(argument, ast.Constant))
    return found


def _scan_python_source(
    src_dir: Path, language: str, package_names: frozenset[str]
) -> list[OutOfTableSite]:
    """AST-walk *src_dir* for string-literal package-name references that sit
    inside a dependency-SET decision site, outside `generation/dependency_tables.py`.

    Structural (`ast.walk` over `ast.Constant` nodes, gated by structurally
    computed function/module-constant line spans), never a text regex. A
    qualifying literal's value equals a member of *package_names* exactly --
    never a substring match. A literal is only counted when its line falls
    inside a span from `_dependency_decision_function_spans` or
    `_dependency_decision_module_constant_spans` -- see
    `_DEPENDENCY_DECISION_NAME_TOKENS` for the naming shape those recognize.

    Args:
        src_dir: The language package's `src/datrix_codegen_<lang>` root.
        language: The registered language name, stamped on every result.
        package_names: The language's registered dependency-catalog universe.

    Returns:
        One `OutOfTableSite` per distinct `(file, line, literal)` found,
        sorted by file then line then literal. Multiple AST nodes on the same
        line naming the same literal (e.g. a dict key and a sibling function
        argument both spelling the same package) collapse to one site -- they
        are one decision, not two.

    Raises:
        SyntaxError: If a `.py` file under `src_dir` cannot be parsed.
    """
    if not src_dir.is_dir() or not package_names:
        return []

    found: set[tuple[Path, int, str]] = set()
    for py_file in sorted(src_dir.rglob("*.py")):
        if _is_declared_table_file(py_file, src_dir):
            continue
        source = py_file.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            raise SyntaxError(
                f"Failed to parse {py_file} while scanning language {language!r} "
                f"for out-of-table dependency-name literals: {exc}"
            ) from exc

        spans = _dependency_decision_function_spans(tree) + _dependency_decision_module_constant_spans(tree)
        if not spans:
            continue

        resolved = py_file.resolve()
        qualifier_values = _qualifier_argument_constants(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in package_names
                and id(node) not in qualifier_values
                and any(span.contains(node.lineno) for span in spans)
            ):
                found.add((resolved, node.lineno, node.value))

    return [
        OutOfTableSite(language=language, file_path=path, line_number=line, package_name=literal)
        for path, line, literal in sorted(found, key=lambda t: (str(t[0]), t[1], t[2]))
    ]


def _is_decision_named_jinja_reference(node: jinja2.nodes.Node) -> bool:
    """True when *node* is a template variable or attribute whose own name is
    dependency-decision shaped (`deps`, `npm_dependencies`, `ctx.packages`)."""
    if isinstance(node, jinja2.nodes.Name):
        return _is_dependency_decision_name(node.name)
    if isinstance(node, jinja2.nodes.Getattr):
        return _is_dependency_decision_name(node.attr)
    return False


def _jinja_decision_constants(template_ast: jinja2.nodes.Template) -> list[jinja2.nodes.Const]:
    """Every literal a template uses to DECIDE a dependency: the structural
    Jinja analogue of the Python pass's decision-site spans.

    Three shapes, each read off the Jinja AST, never the text:

    1. A subscript key -- the `'pkg'` of a manifest's `v['pkg']` version
       lookup: selecting a package from a version map.
    2. The needle of a membership test against a decision-named collection --
       `'pkg' in deps` / `'pkg' not in ctx.packages`.
    3. Any literal assigned to a decision-named template variable --
       `{% set npm_deps = ['pkg'] %}`.

    A literal anywhere else -- an equality test against an unrelated
    attribute (`qp.pipe == 'uuid'` compares a parameter's pipe KIND that
    happens to share a package's spelling), a filter argument, a printed
    value -- decides no dependency and is not returned.
    """
    constants: list[jinja2.nodes.Const] = []
    for getitem in template_ast.find_all(jinja2.nodes.Getitem):
        if isinstance(getitem.arg, jinja2.nodes.Const):
            constants.append(getitem.arg)
    for compare in template_ast.find_all(jinja2.nodes.Compare):
        if isinstance(compare.expr, jinja2.nodes.Const) and any(
            operand.op in _JINJA_MEMBERSHIP_OPS and _is_decision_named_jinja_reference(operand.expr)
            for operand in compare.ops
        ):
            constants.append(compare.expr)
    for assign in template_ast.find_all(jinja2.nodes.Assign):
        if isinstance(assign.target, jinja2.nodes.Name) and _is_dependency_decision_name(assign.target.name):
            constants.extend(assign.node.find_all(jinja2.nodes.Const))
    return constants


def _scan_jinja_templates(
    templates_dir: Path, language: str, package_names: frozenset[str]
) -> list[OutOfTableSite]:
    """Parse every `.j2` file's Jinja AST for literal package-name segments
    that DECIDE a dependency inside a template expression.

    Uses `jinja2.Environment().parse(source)` and keeps the `nodes.Const`
    literals `_jinja_decision_constants` returns -- a version-map subscript
    key (e.g. the `'pkg'` in a manifest template's `v['pkg']` version lookup),
    the needle of a membership test against a decision-named collection, or a
    literal assigned to a decision-named variable -- matched by EXACT
    equality, the structural analogue of the Python pass's decision-span
    gated `ast.Constant` matching. This is never a text regex over the
    template source.

    Raw `TemplateData` (the literal characters of a template BETWEEN tags,
    i.e. its rendered output) is deliberately NOT scanned: a package name can
    appear there for reasons that are not a dependency-set decision at all --
    a code template's own `import stripe` statement, or even a doc comment
    describing why a coordinate is NOT used (both observed in this scan's own
    investigation) -- and matching by containment over that text degenerates
    into exactly the "text regex over source" this module's non-`Const` pass
    was built to avoid. A genuine template-embedded manifest decision (e.g.
    `package.json.j2` hardcoding `"pkg": "{{ v['pkg'] }}"`) still carries its
    literal into a `nodes.Const` inside the accompanying `{{ }}` expression,
    so this narrower pass still finds it.

    Args:
        templates_dir: The language package's `templates/` root.
        language: The registered language name, stamped on every result.
        package_names: The language's registered dependency-catalog universe.

    Returns:
        One `OutOfTableSite` per distinct `(file, line, literal)` found.

    Raises:
        jinja2.TemplateSyntaxError: If a `.j2` file cannot be parsed -- a scan
            error, never a silently-skipped file (a template failing to parse
            syntactically, as opposed to failing to RENDER without a runtime
            context, is a real authoring defect).
    """
    if not templates_dir.is_dir() or not package_names:
        return []

    env = jinja2.Environment()
    found: set[tuple[Path, int, str]] = set()
    for j2_file in sorted(templates_dir.rglob("*.j2")):
        source = j2_file.read_text(encoding="utf-8-sig")
        try:
            template_ast = env.parse(source, filename=str(j2_file))
        except jinja2.TemplateSyntaxError as exc:
            raise jinja2.TemplateSyntaxError(
                f"Failed to parse {j2_file} while scanning language {language!r} "
                f"for out-of-table dependency-name literals: {exc.message}",
                exc.lineno or 0,
                filename=str(j2_file),
            ) from exc
        resolved = j2_file.resolve()
        for const_node in _jinja_decision_constants(template_ast):
            if isinstance(const_node.value, str) and const_node.value in package_names:
                found.add((resolved, const_node.lineno, const_node.value))

    return [
        OutOfTableSite(language=language, file_path=path, line_number=line, package_name=literal)
        for path, line, literal in sorted(found, key=lambda t: (str(t[0]), t[1], t[2]))
    ]


def scan_language(language: str, package_src_roots: tuple[Path, ...]) -> list[OutOfTableSite]:
    """Both structural passes over every package implementing one registered
    language -- its backend and every language core it requires.

    The language's catalog universe is the union of every root's
    `defaults.yaml` (a core ships none and scans against its backend's), so a
    decision site that moved into a core is still matched against the
    catalog it decides from. Each root's own `generation/dependency_tables.py`
    is the table the exclusion honours.

    Args:
        language: The registered language name (or a folded label -- kept
            generic like `discover_target_package_src_dirs`'s own label).
        package_src_roots: `(backend src root, *core src roots)`.

    Returns:
        Every out-of-table site found by either pass in any root, sorted by
        file, line, then literal.
    """
    package_names = frozenset[str]().union(*(_catalog_package_names(root, language) for root in package_src_roots))
    sites: list[OutOfTableSite] = []
    for root in package_src_roots:
        sites.extend(_scan_python_source(root, language, package_names))
        sites.extend(_scan_jinja_templates(root / _TEMPLATES_SUBDIR_NAME, language, package_names))
    return sorted(sites, key=lambda site: (str(site.file_path), site.line_number, site.package_name))


def _require_min_languages(language_names: frozenset[str]) -> None:
    """Raise if fewer than `_MIN_LANGUAGES_FOR_COMPARISON` languages are given.

    The CLI-facing guard against a vacuous scan. Exercised directly by the
    self-test against a synthetic single-name set (never through a live
    entry-point scan), and by `scan_all_registered_languages` against the
    real registered set.

    Args:
        language_names: The registered language names to validate.

    Raises:
        SystemExit: `EXIT_USAGE`, naming how many languages ARE registered.
    """
    if len(language_names) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "Dependency-declaration ratchet requires at least %d registered "
            "'datrix.languages' packages; got %d (%s). A per-language "
            "out-of-table census over fewer than %d languages is vacuous.",
            _MIN_LANGUAGES_FOR_COMPARISON,
            len(language_names),
            sorted(language_names),
            _MIN_LANGUAGES_FOR_COMPARISON,
        )
        raise SystemExit(EXIT_USAGE)


def scan_all_registered_languages() -> dict[str, list[OutOfTableSite]]:
    """Run `scan_language` for every name `registered_language_names()` returns,
    resolved to every package implementing it (backend plus language cores)
    via `datrix_scripts.registered_targets.discover_target_package_src_dirs` (never a
    hardcoded `datrix-codegen-{name}` string-format assumption).

    Raises:
        SystemExit: `EXIT_USAGE` if fewer than `_MIN_LANGUAGES_FOR_COMPARISON`
            languages are registered.
        ValueError: If a registered language cannot be resolved to an on-disk
            `src/` directory (propagated from `discover_target_package_src_dirs`).
    """
    language_names = registered_language_names()
    _require_min_languages(language_names)
    target_src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    return {label: scan_language(label, src_dirs) for label, src_dirs in sorted(target_src_dirs.items())}


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


def _write_synthetic_language(language_dir: Path, language: str, package_name: str) -> None:
    """Plant one synthetic language package: a `defaults.yaml` declaring
    *package_name*, and a `.py` file referencing it as a bare string literal
    outside any `dependency_tables.py`."""
    language_dir.mkdir(parents=True, exist_ok=True)
    (language_dir / _DEFAULTS_YAML_NAME).write_text(
        f"dependencies:\n  {language}:\n    {package_name}: '>=1.0.0'\n",
        encoding="utf-8",
    )
    (language_dir / "module.py").write_text(
        f'_SYNTHETIC_DEPENDENCY_NAME = "{package_name}"\n',
        encoding="utf-8",
    )


def _move_planted_literal_into_declared_table(language_dir: Path) -> None:
    """Move the planted literal's file into a synthetic
    `generation/dependency_tables.py`, so the site becomes excluded."""
    declared_table = language_dir / _DECLARED_TABLE_RELATIVE_PATH
    declared_table.parent.mkdir(parents=True, exist_ok=True)
    source = language_dir / "module.py"
    declared_table.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    source.unlink()


def _write_non_qualifying_decoy(language_dir: Path, package_name: str) -> None:
    """Add a SECOND file to an already-planted synthetic language package: a
    non-qualifying module-level constant and a non-qualifying function, both
    referencing the SAME planted *package_name* outside any function/constant
    whose name matches `_DEPENDENCY_DECISION_NAME_TOKENS`.

    Mirrors the real, previously-misflagged shape this narrowing exists to
    fix (a cache-ENGINE identifier set, and a `resolve_*_engine`-shaped
    function) -- proving the narrowing itself: scanning after this file is
    added must NOT add a second site for the same literal.
    """
    (language_dir / "decoy.py").write_text(
        f'_SUPPORTED_ENGINES = frozenset({{"{package_name}"}})\n'
        "\n\n"
        "def resolve_engine() -> str:\n"
        f'    return "{package_name}"\n',
        encoding="utf-8",
    )


def _self_test_jinja_pass(tmp_root: Path) -> bool:
    """Plant a synthetic language whose ONLY out-of-table site lives in a
    `.j2` template, proving the template pass is exercised independently of
    the Python-source pass (which the two-language planted-site fixture above
    already covers)."""
    language_dir = tmp_root / "lang_tmpl"
    language_dir.mkdir(parents=True, exist_ok=True)
    (language_dir / _DEFAULTS_YAML_NAME).write_text(
        f"dependencies:\n  {_SELF_TEST_LANGUAGE_TMPL}:\n    {_SELF_TEST_TEMPLATE_PACKAGE}: '>=1.0.0'\n",
        encoding="utf-8",
    )
    templates_dir = language_dir / _TEMPLATES_SUBDIR_NAME
    templates_dir.mkdir(parents=True, exist_ok=True)
    template_source = '{\n  "%s": "{{ v[\'%s\'] }}"\n}\n' % (
        _SELF_TEST_TEMPLATE_PACKAGE,
        _SELF_TEST_TEMPLATE_PACKAGE,
    )
    (templates_dir / "manifest.json.j2").write_text(template_source, encoding="utf-8")

    sites = scan_language(_SELF_TEST_LANGUAGE_TMPL, (language_dir,))
    return len(sites) == 1 and sites[0].package_name == _SELF_TEST_TEMPLATE_PACKAGE


def _self_test_jinja_decision_shapes(tmp_root: Path) -> bool:
    """The template pass counts a membership test against a decision-named
    collection and a literal assigned to a decision-named variable, and does
    NOT count an equality test against an unrelated attribute that happens to
    spell a package name (a parameter's pipe KIND, for instance)."""
    language_dir = tmp_root / "lang_tmpl_shapes"
    templates_dir = language_dir / _TEMPLATES_SUBDIR_NAME
    templates_dir.mkdir(parents=True, exist_ok=True)
    (language_dir / _DEFAULTS_YAML_NAME).write_text(
        f"dependencies:\n  {_SELF_TEST_LANGUAGE_TMPL}:\n    {_SELF_TEST_TEMPLATE_PACKAGE}: '>=1.0.0'\n",
        encoding="utf-8",
    )
    decoy = "{%% if qp.pipe == '%s' %%}pipe{%% endif %%}\n" % _SELF_TEST_TEMPLATE_PACKAGE
    (templates_dir / "decoy.ts.j2").write_text(decoy, encoding="utf-8")
    decoy_sites = scan_language(_SELF_TEST_LANGUAGE_TMPL, (language_dir,))
    decisions = (
        "{%% if '%s' in deps %%}yes{%% endif %%}\n{%% set npm_dependencies = ['%s'] %%}\n"
        % (_SELF_TEST_TEMPLATE_PACKAGE, _SELF_TEST_TEMPLATE_PACKAGE)
    )
    (templates_dir / "decisions.json.j2").write_text(decisions, encoding="utf-8")
    decision_sites = scan_language(_SELF_TEST_LANGUAGE_TMPL, (language_dir,))
    return not decoy_sites and [site.line_number for site in decision_sites] == [1, 2]


def _self_test_language_core(tmp_root: Path) -> bool:
    """A fixture language split into a backend and a core: the decision site
    planted in the CORE (which ships no catalog of its own) is found when the
    language is scanned as backend plus core, against the backend's catalog;
    scanning the backend alone -- the pre-split blindness -- finds nothing."""
    backend_dir = tmp_root / "lang_split_backend"
    core_dir = tmp_root / "lang_split_core"
    backend_dir.mkdir(parents=True, exist_ok=True)
    core_dir.mkdir(parents=True, exist_ok=True)
    (backend_dir / _DEFAULTS_YAML_NAME).write_text(
        f"dependencies:\n  {_SELF_TEST_LANGUAGE_CORE}:\n    {_SELF_TEST_CORE_PACKAGE}: '>=1.0.0'\n",
        encoding="utf-8",
    )
    (core_dir / "core_module.py").write_text(
        f'def get_dependencies() -> list[str]:\n    return ["{_SELF_TEST_CORE_PACKAGE}"]\n', encoding="utf-8"
    )
    split_sites = scan_language(_SELF_TEST_LANGUAGE_CORE, (backend_dir, core_dir))
    backend_only = scan_language(_SELF_TEST_LANGUAGE_CORE, (backend_dir,))
    return (
        [site.file_path for site in split_sites] == [(core_dir / "core_module.py").resolve()]
        and not backend_only
    )


def _declared_row_packages(src_roots: tuple[Path, ...]) -> frozenset[str]:
    """Every `package=` string a language's declared table(s) name a row with,
    read off the AST of each root's `generation/dependency_tables.py`."""
    names: set[str] = set()
    for root in src_roots:
        table = root / _DECLARED_TABLE_RELATIVE_PATH
        if not table.is_file():
            continue
        tree = ast.parse(table.read_text(encoding="utf-8-sig"), filename=str(table))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == _DECLARED_ROW_PACKAGE_KEYWORD
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    names.add(keyword.value.value)
    return frozenset(names)


def _live_catalog_matches_real_declarations(tmp_root: Path) -> bool:
    """Prove the matcher works against the REAL tree, not only synthetic
    fixtures, without pinning a coordinate a migration is expected to remove.

    For every registered language: its live catalog universe (the union over
    every package implementing it) must contain every package its live
    declared table names, and the declared table must name at least one; and
    a real declared package name, planted into a synthetic decision-named
    function and scanned against that live universe, must be reported as
    exactly one site. A matcher reading an empty or wrong universe -- a
    catalog that moved, a core scanned without its backend's catalog -- fails
    here instead of reporting a vacuous zero.
    """
    target_src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, registered_language_names(), WORKSPACE_ROOT)
    languages_proven = 0
    for language, src_roots in sorted(target_src_dirs.items()):
        universe = frozenset[str]().union(*(_catalog_package_names(root, language) for root in src_roots))
        declared = _declared_row_packages(src_roots)
        if not declared or not declared <= universe:
            logger.error(
                "live check: language=%s declares %d table package(s), %d outside its %d-package catalog: %s",
                language,
                len(declared),
                len(declared - universe),
                len(universe),
                sorted(declared - universe),
            )
            return False
        planted_dir = tmp_root / f"live_{language}"
        planted_dir.mkdir(parents=True, exist_ok=True)
        planted_name = sorted(declared)[0]
        (planted_dir / "planted.py").write_text(
            f'def get_dependencies() -> list[str]:\n    return ["{planted_name}"]\n', encoding="utf-8"
        )
        sites = _scan_python_source(planted_dir, language, universe)
        if [site.package_name for site in sites] != [planted_name]:
            return False
        languages_proven += 1
    return languages_proven >= _MIN_LANGUAGES_FOR_COMPARISON


def _catalog_literal_sites(src_dir: Path, package_names: frozenset[str]) -> set[tuple[Path, int, str]]:
    """The EARLIER, over-broad matcher: every string constant anywhere in a
    `.py` file under *src_dir* (outside the declared table) equal to a catalog
    package name, decision site or not."""
    found: set[tuple[Path, int, str]] = set()
    for py_file in sorted(src_dir.rglob("*.py")):
        if _is_declared_table_file(py_file, src_dir):
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
        resolved = py_file.resolve()
        found.update(
            (resolved, node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in package_names
        )
    return found


def _live_scan_narrows_real_tree() -> bool:
    """Prove the narrowing actually narrows on the REAL tree, without pinning a
    language or a coordinate: for every registered language, every site the
    Python pass reports is also a catalog literal the over-broad matcher finds,
    and the over-broad matcher finds at least one real catalog literal the
    Python pass excludes (an engine identifier, an import-module constant, a
    qualifier value). A narrowing that excluded nothing, or a scan reporting a
    site no catalog literal backs, fails here."""
    target_src_dirs = discover_target_package_src_dirs(
        AXIS_LANGUAGES, registered_language_names(), WORKSPACE_ROOT
    )
    for language, src_roots in sorted(target_src_dirs.items()):
        universe = frozenset[str]().union(*(_catalog_package_names(root, language) for root in src_roots))
        broad: set[tuple[Path, int, str]] = set()
        narrowed: set[tuple[Path, int, str]] = set()
        for root in src_roots:
            broad |= _catalog_literal_sites(root, universe)
            narrowed.update(
                (site.file_path, site.line_number, site.package_name)
                for site in _scan_python_source(root, language, universe)
            )
        excluded = len(broad - narrowed)
        logger.debug(
            "live narrowing language=%s broad=%d reported=%d excluded=%d", language, len(broad), len(narrowed), excluded
        )
        if not narrowed <= broad or excluded == 0:
            return False
    return bool(target_src_dirs)


def _self_test_qualifier_value_excluded(tmp_root: Path) -> bool:
    """Inside one decision-named function, a catalog name passed to
    `DependencyQualifier(...)` (an engine qualifier sharing the package's
    spelling) is not counted, while a bare literal of the same name is."""
    language_dir = tmp_root / "lang_qualifier"
    language_dir.mkdir(parents=True, exist_ok=True)
    (language_dir / _DEFAULTS_YAML_NAME).write_text(
        f"dependencies:\n  {_SELF_TEST_LANGUAGE_A}:\n    {_SELF_TEST_PACKAGE_A}: '>=1.0.0'\n",
        encoding="utf-8",
    )
    (language_dir / "qualified.py").write_text(
        "def _collect_cache_deps(catalog):\n"
        "    rows = lookup(\n"
        f'        "cache", {_QUALIFIER_CALL_NAME}(axis="engine", value="{_SELF_TEST_PACKAGE_A}"),\n'
        "    )\n"
        f'    return rows + ["{_SELF_TEST_PACKAGE_A}"]\n',
        encoding="utf-8",
    )
    sites = scan_language(_SELF_TEST_LANGUAGE_A, (language_dir,))
    return [site.line_number for site in sites] == [5]


def _self_test_names_no_target() -> bool:
    """This gate enumerates languages from registration and must name none."""
    failures = self_test_gate_names_no_target(__file__)
    for line in failures:
        print(f"  FAIL: {line}")
    return _assert(not failures, "this gate names no registered target (imports and name literals)")


def self_test() -> bool:
    """Non-vacuity self-test, run as step 1 of every invocation.

    0. Assert this module names no registered target
       (`datrix_scripts.registered_targets.self_test_gate_names_no_target`).
    1. Build a synthetic two-language package tree under
       `tempfile.TemporaryDirectory`, each with a real `defaults.yaml` and one
       `src/` literal outside any `dependency_tables.py`; assert the scan
       finds exactly those two planted sites.
    2. Add a non-qualifying decoy (a `resolve_engine`-shaped function and a
       `SUPPORTED_*`-shaped constant) referencing the SAME planted literal;
       assert the site count for that language does not increase -- the
       narrowing itself.
    3. Move one planted literal into a synthetic
       `generation/dependency_tables.py`; assert the combined count drops by
       exactly one.
    4. Plant a synthetic language whose only out-of-table site lives in a
       `.j2` template; assert the Jinja pass finds it independently.
    5. Assert the Jinja pass counts a membership test against a
       decision-named collection and a decision-named `set`, and not an
       equality test against an unrelated attribute.
    6. Plant a fixture language split into a backend and a core; assert a
       decision site in the core is found against the backend's catalog, and
       that scanning the backend alone misses it.
    7. Assert the LIVE catalogs contain every package the live declared tables
       name, and that a real declared name planted into a decision site is
       reported against the live universe.
    8. Assert a catalog name passed to `DependencyQualifier(...)` is not
       counted while a bare literal of the same name in the same function is.
    9. Assert, for every registered LIVE language, every reported site is a
       catalog literal and at least one real catalog literal is excluded.
    10. Assert the minimum-language guard refuses a single-language set with
       `SystemExit(EXIT_USAGE)`, never a silent pass.

    Returns:
        True if every assertion holds.
    """
    ok = _self_test_names_no_target()
    tmp_root = Path(tempfile.mkdtemp(prefix="dependency-declaration-ratchet-selftest-"))
    try:
        lang_a_dir = tmp_root / "lang_a"
        lang_b_dir = tmp_root / "lang_b"
        _write_synthetic_language(lang_a_dir, _SELF_TEST_LANGUAGE_A, _SELF_TEST_PACKAGE_A)
        _write_synthetic_language(lang_b_dir, _SELF_TEST_LANGUAGE_B, _SELF_TEST_PACKAGE_B)

        sites_a = scan_language(_SELF_TEST_LANGUAGE_A, (lang_a_dir,))
        sites_b = scan_language(_SELF_TEST_LANGUAGE_B, (lang_b_dir,))
        ok &= _assert(
            len(sites_a) == 1 and len(sites_b) == 1,
            "synthetic two-language tree yields exactly two planted out-of-table sites",
        )

        _write_non_qualifying_decoy(lang_a_dir, _SELF_TEST_PACKAGE_A)
        sites_a_with_decoy = scan_language(_SELF_TEST_LANGUAGE_A, (lang_a_dir,))
        ok &= _assert(
            len(sites_a_with_decoy) == 1,
            "a non-qualifying function/constant referencing the same planted "
            "literal outside any dependency-decision-shaped name adds no new "
            "site (the narrowing itself)",
        )

        _move_planted_literal_into_declared_table(lang_a_dir)
        sites_a_after = scan_language(_SELF_TEST_LANGUAGE_A, (lang_a_dir,))
        combined_after = len(sites_a_after) + len(sites_b)
        ok &= _assert(
            len(sites_a_after) == 0 and combined_after == 1,
            "moving the planted literal into generation/dependency_tables.py "
            "drops the combined count by exactly one",
        )

        ok &= _assert(
            _self_test_jinja_pass(tmp_root),
            "synthetic Jinja template literal is detected by the template pass "
            "independently of the Python-source pass",
        )

        ok &= _assert(
            _self_test_jinja_decision_shapes(tmp_root),
            "the template pass counts a membership test against a decision-named collection and a "
            "decision-named set, and not an equality test against an unrelated attribute",
        )

        ok &= _assert(
            _self_test_language_core(tmp_root),
            "a fixture language split into a backend and a core: a decision site planted in the core is "
            "found against the backend's catalog; scanning the backend alone misses it",
        )

        ok &= _assert(
            _live_catalog_matches_real_declarations(tmp_root),
            "live tree: every registered language's catalog contains every package its declared table "
            "names, and a real declared name planted into a decision site is reported against it",
        )

        ok &= _assert(
            _self_test_qualifier_value_excluded(tmp_root),
            "a catalog name passed to DependencyQualifier(...) is a qualifier value and is not counted; "
            "a bare literal of the same name in the same function is",
        )

        ok &= _assert(
            _live_scan_narrows_real_tree(),
            "live scan (real tree): for every registered language each reported site is a catalog literal "
            "and at least one real catalog literal outside any decision site is excluded",
        )

        try:
            _require_min_languages(frozenset({_SELF_TEST_LANGUAGE_A}))
            guard_refused = False
        except SystemExit as exc:
            guard_refused = exc.code == EXIT_USAGE
        ok &= _assert(
            guard_refused,
            "single-language guard refuses a one-language set with EXIT_USAGE, never a silent pass",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


# ---------------------------------------------------------------------------
# Baseline (decrease-only ratchet)
# ---------------------------------------------------------------------------


def load_baseline() -> int:
    """Read the decrease-only `out_of_table_count` baseline.

    Returns:
        The recorded count, or 0 if the file does not exist yet (first-ever
        run, before `--update-baseline` freezes it).

    Raises:
        ValueError: If the file exists but is malformed (not an object with a
            non-negative integer `out_of_table_count` field).
    """
    if not RATCHET_BASELINE_PATH.exists():
        return 0
    data = json.loads(RATCHET_BASELINE_PATH.read_text(encoding="utf-8"))
    count = data.get("out_of_table_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            f"Malformed {RATCHET_BASELINE_PATH}: expected an object with a "
            f"non-negative integer 'out_of_table_count' field, got {data!r}."
        )
    return count


def write_baseline(count: int) -> None:
    """The only writer of `RATCHET_BASELINE_PATH` -- invoked solely via
    `--update-baseline`, a deliberate, manual re-freeze."""
    payload = {
        "_comment": [
            "Decrease-only ratchet: the count of dependency PACKAGE-NAME literal",
            "decision sites found outside each registered language's own",
            "generation/dependency_tables.py table (Python AST string constants",
            "plus Jinja template literal segments matching that language's",
            "registered DependencyCatalog package universe), summed across every",
            "registered datrix.languages package. A run whose LIVE count is",
            "HIGHER than this value fails -- a new out-of-table decision site",
            "appeared with nothing reconciling it.",
            "dependency-declaration-ratchet-gate.ps1 -UpdateBaseline is the only",
            "writer; do not hand-guess the number.",
        ],
        "out_of_table_count": count,
    }
    RATCHET_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RATCHET_BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _log_report(sites_by_language: dict[str, list[OutOfTableSite]]) -> int:
    """Log the per-language site breakdown plus the summary line.

    Returns:
        The total out-of-table count across every scanned language.
    """
    total = 0
    for language in sorted(sites_by_language):
        sites = sites_by_language[language]
        total += len(sites)
        for site in sites:
            logger.debug(
                "OUT-OF-TABLE language=%s site=%s:%d literal=%r",
                site.language,
                site.file_path,
                site.line_number,
                site.package_name,
            )
        logger.info("language=%s out_of_table_count=%d", language, len(sites))
    logger.info(
        "DEPENDENCY-DECLARATION RATCHET REPORT: %d registered language(s) scanned, "
        "%d out-of-table dependency-name decision site(s) total.",
        len(sites_by_language),
        total,
    )
    return total


def main(argv: list[str] | None = None) -> int:
    """Entry point: self-test, then (unless --self-test) the real scan against
    the decrease-only baseline; --update-baseline re-pins it downward.

    Returns:
        0 (report ran and out-of-table count <= baseline, a successful
        `--update-baseline`, or `--self-test` passed), 1 (out-of-table count
        exceeds baseline), or 2 (self-test failed, fewer than two registered
        languages, or a discovery/parse error).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Dependency-declaration-only-path ratchet: every dependency "
            "PACKAGE-NAME decision site found outside each registered "
            "'datrix.languages' package's own generation/dependency_tables.py "
            "table, with a decrease-only count baseline."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real scan",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the live out-of-table count as the new baseline",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real scan is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        sites_by_language = scan_all_registered_languages()
    except (ValueError, SyntaxError, jinja2.TemplateSyntaxError) as exc:
        logger.error("DEPENDENCY-DECLARATION RATCHET CANNOT RUN: %s", exc)
        return EXIT_USAGE

    total_count = _log_report(sites_by_language)

    if args.update_baseline:
        write_baseline(total_count)
        logger.info(
            "Baseline updated: out_of_table_count=%d written to %s",
            total_count,
            RATCHET_BASELINE_PATH,
        )
        return EXIT_OK

    baseline_count = load_baseline()
    if total_count > baseline_count:
        logger.error(
            "DEPENDENCY-DECLARATION RATCHET REGRESSION: %d out-of-table site(s) "
            "found, but the recorded baseline expects at most %d. New "
            "out-of-table dependency-name decision site(s) appeared with "
            "nothing reconciling them -- move the new site(s) into "
            "generation/dependency_tables.py, or if reviewed and intentional, "
            "re-run with --update-baseline.",
            total_count,
            baseline_count,
        )
        return EXIT_FAIL

    logger.info(
        "Dependency-declaration ratchet holds: %d out-of-table site(s) <= baseline %d.",
        total_count,
        baseline_count,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
