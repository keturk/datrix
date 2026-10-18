#!/usr/bin/env python3
r"""Docs-conformance gate for Datrix architecture documentation (Invariant I5).

Extracts repo-relative path references and Python module references from
every package's **architecture documentation** (the curated 38-file set in
``ARCHITECTURE_DOC_FILES`` below) and fails if any reference does not resolve
to a real file/directory/module in the tree, unless the reference is recorded
in the committed exceptions baseline
(``datrix/scripts/config/docs-conformance-exceptions.json``) for a
legitimately non-existent claim (a "what was removed" migration-history
reference, a "must never exist" prohibition claim, or another confirmed
intentional non-existence).

``ARCHITECTURE_DOC_FILES`` is a literal, reviewable constant rather than a
directory glob computed at scan time. "Architecture docs" is a curated
concept (a package's `docs/architecture.md` and/or `docs/architecture/`
tree), not something reliably derivable by globbing every `*.md` under a
package's `docs/` tree -- the other ~168 non-architecture markdown files
across these packages' `docs/` trees are dominated by illustrative or
generated-project example paths, not real repo-path claims, and scanning
them would drown real drift in noise. A NEW architecture doc file added
later is a deliberate, reviewed addition to this constant.

Beyond path and module spans, three claim families are checked whose rot no
path check can see. **Class members**: a doc that binds a class name to a
workspace class (a ``from <module> import Name`` line or a qualified
``package.module.Name`` span) and writes ``Name.member`` in a span or a code
fence claims the member exists; the class's source, its re-exports and its
bases must declare it. **Anchor links** (``[text](<doc>.md#anchor)`` and
``[text](#anchor)``) must name a heading that exists in the target doc, by
the GitHub-flavoured slug the heading produces -- a heading gaining a status
suffix silently breaks every link to it. **Decision status**: every
``### Decision N:`` heading carries a status from a closed vocabulary; a
``**Status:**`` paragraph, when present, agrees with the heading; an
in-progress decision must carry one (it is the checklist of what remains);
and every ``*.ps1`` gate a decision section names exists somewhere under
``datrix/scripts``.

For path and module spans this is a v1 scanner with a **deliberate scope
boundary**: it only checks
path-reference candidates that are **fully package-qualified** (start with
one of the 13 known package directory names, or a ``D:\datrix\`` /
``d:/datrix/`` absolute prefix) and module-reference candidates that are
**fully import-qualified** (start with one of the 12 known Python import
names). A bare, package-relative shorthand span with no package/import
anchor at all (e.g. a doc writing `` `dgen/_naming.py` `` instead of the
fully-qualified `` `datrix-codegen-common/dgen/_naming.py` `` or `` `src/`
`` form) is never a candidate: such bare spans are pervasive across these
docs and dominated by illustrative/generic filenames (``api.py``,
``base.py``, ``0001_initial.py``) that are not real repo-path claims at
all, and there is no anchor to reliably resolve them against. A future
increment could add a "resolve bare spans relative to the doc's own owning
package" tier if the docs' own citation conventions are first made
consistent -- out of scope here.

Exit codes:
    0: No unresolved references (after exceptions-baseline filtering), or
       --warn mode.
    1: At least one unresolved, non-excepted reference was found (fail mode).
    2: Usage error, missing exceptions-baseline file, or an entry in
       ARCHITECTURE_DOC_FILES that no longer exists on disk.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import (
    NamedCheck,
    gate_argument_parser,
    harness_self_test,
    named_checks,
    report_step,
    run_checks,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.pyproject_deps import (
    DATRIX_PREFIX,
    discover_packages,
    parse_package_name,
    read_project_dependencies,
)

# ---------------------------------------------------------------------------
# The curated 38-file architecture-doc set (see module docstring for why this
# is a literal constant, never a directory glob). Verified against the live
# tree: datrix-common and datrix-language each ship BOTH a top-level
# docs/architecture.md AND a docs/architecture/ directory of further .md
# files -- both are in scope for each package that has them.
# ---------------------------------------------------------------------------
ARCHITECTURE_DOC_FILES: tuple[str, ...] = (
    "datrix/docs/architecture/architecture-cheat-sheet.md",
    "datrix/docs/architecture/architecture-overview.md",
    "datrix/docs/architecture/codegen-migration-strategy.md",
    "datrix/docs/architecture/design-principles-cheat-sheet.md",
    "datrix/docs/architecture/design-principles.md",
    "datrix/docs/architecture/rdbms-migration-decisions.md",
    "datrix/docs/architecture/packs/ai-agents.md",
    "datrix/docs/architecture/packs/auth.md",
    "datrix/docs/architecture/packs/codegen-engine.md",
    "datrix/docs/architecture/packs/dsl-features.md",
    "datrix/docs/architecture/packs/frontend-clients.md",
    "datrix/docs/architecture/packs/language-server.md",
    "datrix/docs/architecture/packs/migrations.md",
    "datrix/docs/architecture/packs/parity-and-obligation.md",
    "datrix/docs/architecture/packs/pipeline-stages.md",
    "datrix/docs/architecture/packs/runtime-and-deploy.md",
    "datrix/docs/architecture/packs/shared-layer-and-one-fact.md",
    "datrix/docs/architecture/packs/target-plugins.md",
    "datrix/docs/architecture/architecture/builtin-traits-enums.md",
    "datrix/docs/architecture/architecture/pipeline-and-capabilities.md",
    "datrix/docs/architecture/architecture/repository-architecture.md",
    "datrix-cli/docs/architecture.md",
    "datrix-codegen-angular/docs/architecture.md",
    "datrix-codegen-aws/docs/architecture.md",
    "datrix-codegen-azure/docs/architecture.md",
    "datrix-codegen-common/docs/architecture.md",
    "datrix-codegen-component/docs/architecture.md",
    "datrix-codegen-docker/docs/architecture.md",
    "datrix-codegen-flutter/docs/architecture.md",
    "datrix-codegen-kernel/docs/architecture.md",
    "datrix-codegen-python/docs/architecture.md",
    "datrix-codegen-sql/docs/architecture.md",
    "datrix-codegen-typescript/docs/architecture.md",
    "datrix-codegen-typescript-core/docs/architecture.md",
    "datrix-common/docs/architecture.md",
    "datrix-common/docs/architecture/ast-parent-containment.md",
    "datrix-common/docs/architecture/code-generation.md",
    "datrix-common/docs/architecture/codegen-consolidation.md",
    "datrix-common/docs/architecture/codegen-design.md",
    "datrix-common/docs/architecture/config-migration-rationale.md",
    "datrix-common/docs/architecture/config-system.md",
    "datrix-common/docs/architecture/gateway-architecture.md",
    "datrix-common/docs/architecture/identity.md",
    "datrix-common/docs/architecture/import-boundaries.md",
    "datrix-common/docs/architecture/migration.md",
    "datrix-common/docs/architecture/output-path-contract.md",
    "datrix-language/docs/architecture.md",
    "datrix-language/docs/architecture/model-metaprogramming.md",
    "datrix-language/docs/architecture/parser-design.md",
    "datrix-language/docs/architecture/parser-overview.md",
    "datrix-language/docs/architecture/semantic-design.md",
    "datrix-migration/docs/architecture.md",
    "datrix-semantic/docs/architecture.md",
    "datrix-semantic/docs/architecture/semantic-validators.md",
    "datrix-testing/docs/architecture.md",
)

# API and reference docs. They get the path, module and anchor checks; the
# Decision-status check stays on ARCHITECTURE_DOC_FILES only.
REFERENCE_DOC_FILES: tuple[str, ...] = (
    "datrix-language/docs/datrix-language-api.md",
    "datrix-language/docs/reference/datrix-stdlib-reference.md",
    "datrix-language/docs/reference/datrix-syntax-reference.md",
    "datrix-common/docs/datrix-common-api.md",
    "datrix-cli/docs/commands.md",
    "datrix-cli/docs/commands/generate.md",
)

# The monorepo root -- the default for --base-dir. Needed at module scope so the
# package tables below can be discovered from disk.
_MONOREPO_ROOT: Path = WORKSPACE_DIR


def _discover_package_dirs(monorepo_root: Path) -> frozenset[str]:
    """Discover the Datrix package directory names under the monorepo root.

    This is the scope boundary for path-reference candidates: it enumerates installable
    Datrix packages, never target languages/providers.

    Discovered rather than hardcoded. Datrix is a multi-language, multi-platform generator,
    so a new ``datrix-codegen-<lang>`` package must become a recognized reference scope
    without an edit here -- a hardcoded table silently stops policing references into any
    package added after it was written, which is the failure mode this gate exists to catch.
    """
    if not monorepo_root.is_dir():
        return frozenset()
    return frozenset(
        child.name for child in workspace_package_dirs(monorepo_root, include_showcase=True)
    )


def _build_import_name_map(package_dirs: frozenset[str]) -> dict[str, str]:
    """Map each package's Python import name to its package directory name.

    Every Datrix package derives its import name from its directory name by the same rule
    (``datrix-codegen-python`` -> ``datrix_codegen_python``), so the map is derived, not
    tabulated. The ``datrix`` showcase repo is excluded: it ships no importable package.
    """
    return {
        name.replace("-", "_"): name for name in sorted(package_dirs) if name != "datrix"
    }


_PACKAGE_DIRS: frozenset[str] = _discover_package_dirs(_MONOREPO_ROOT)

_IMPORT_NAME_TO_PACKAGE_DIR: dict[str, str] = _build_import_name_map(_PACKAGE_DIRS)

# Tier-2 search roots, in the order they are inspected. Deliberately scoped
# to exactly these two subtrees under each package -- never the whole
# package directory (which would also match docs/, .tasks/, etc.).
_TIER2_SEARCH_ROOTS: tuple[str, ...] = ("src", "tests")

_INLINE_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_WINDOWS_ABS_PREFIX_RE = re.compile(r"^[Dd]:[\\/]datrix[\\/]")
_WINDOWS_ABS_STRIP_RE = re.compile(r"^[Dd]:/datrix/")
_LINE_REF_SUFFIX_RE = re.compile(r":\d+(-\d+)?(,\d+(-\d+)?)*$")
_PATH_SYMBOL_SUFFIX_RE = re.compile(r"::([A-Za-z_][A-Za-z0-9_]*)$")
_MODULE_CANDIDATE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z_][a-zA-Z0-9_]*)+$")
_CALL_SPAN_SUFFIX = "()"

# A path-reference candidate containing any of these markers is rejected --
# never a candidate, never needs a baseline entry (step 2: elision marker,
# template placeholder, or glob pattern).
_PATH_REJECTION_MARKERS: tuple[str, ...] = ("...", "<", ">", "*")


def _iter_backtick_spans(doc_text: str) -> list[tuple[int, str]]:
    """Yield ``(line_number, trimmed_span_text)`` for every single-backtick
    inline code span in *doc_text*, scanned one line at a time so a span can
    never contain an embedded newline (per the extraction algorithm's own
    definition of a candidate span).

    Args:
        doc_text: Full text of one architecture doc file.

    Returns:
        List of (1-based line number, trimmed backtick-span text) tuples, in
        document order.
    """
    spans: list[tuple[int, str]] = []
    for line_number, line in enumerate(doc_text.splitlines(), start=1):
        for match in _INLINE_CODE_SPAN_RE.finditer(line):
            spans.append((line_number, match.group(1).strip()))
    return spans


def extract_path_candidates(doc_text: str) -> list[tuple[int, str]]:
    """Extract path-reference candidates from *doc_text* (extraction step 1 + 2).

    A backtick span is a path-reference candidate iff, after trimming
    whitespace, it matches a Windows-absolute ``D:\\datrix\\``/``d:/datrix/``
    prefix OR its first ``/``-or-``\\``-separated segment is one of the
    known package directory names or a known Python import name (an
    import-name path such as ``datrix_language/foundation.dtrx`` resolves
    under ``<package dir>/src/``) -- UNLESS it contains an elision marker
    (``...``), a template placeholder (``<``/``>``), or a glob (``*``), in
    which case it is rejected outright (never a candidate).

    Args:
        doc_text: Full text of one architecture doc file.

    Returns:
        List of (1-based line number, span text) tuples for every
        path-reference candidate found, in document order.
    """
    candidates: list[tuple[int, str]] = []
    for line_number, span in _iter_backtick_spans(doc_text):
        if any(marker in span for marker in _PATH_REJECTION_MARKERS):
            continue
        if _WINDOWS_ABS_PREFIX_RE.match(span):
            candidates.append((line_number, span))
            continue
        first_segment = re.split(r"[\\/]", span, maxsplit=1)[0]
        if first_segment in _PACKAGE_DIRS or (
            first_segment in _IMPORT_NAME_TO_PACKAGE_DIR and first_segment != span
        ):
            candidates.append((line_number, span))
    return candidates


def extract_module_candidates(doc_text: str) -> list[tuple[int, str]]:
    """Extract module-reference candidates from *doc_text* (extraction step 1).

    A backtick span is a module-reference candidate iff, after trimming
    whitespace, it matches a dotted lowercase identifier chain
    (``^[a-z][a-z0-9_]*(\\.[a-z_][a-zA-Z0-9_]*)+$``) whose first segment is
    one of the 12 known Python import names. A trailing ``()`` call suffix is
    stripped before matching, and the stripped span is the candidate. A trailing segment that starts
    with an uppercase letter (a class name, e.g. ``...DefaultMigrationHooks``)
    fails this regex and is deliberately excluded -- this v1 only resolves
    module/function/attribute paths, not class-qualified symbol chains.

    Args:
        doc_text: Full text of one architecture doc file.

    Returns:
        List of (1-based line number, span text) tuples for every
        module-reference candidate found, in document order.
    """
    candidates: list[tuple[int, str]] = []
    for line_number, raw_span in _iter_backtick_spans(doc_text):
        span = raw_span.removesuffix(_CALL_SPAN_SUFFIX)
        if not _MODULE_CANDIDATE_RE.match(span):
            continue
        first_segment = span.split(".", 1)[0]
        if first_segment in _IMPORT_NAME_TO_PACKAGE_DIR:
            candidates.append((line_number, span))
    return candidates


def _tier2_resolve_path(package_name: str, suffix: str, monorepo_root: Path) -> Path | None:
    """Tier-2 shorthand resolution: return the one file/dir under
    ``<package_name>/src/`` or ``<package_name>/tests/`` whose root-relative
    posix path ends with *suffix*, or ``None`` if there is no such match or
    more than one.

    Scoped to exactly ``src/`` and ``tests/`` (never the whole package
    directory, which would also match ``docs/``, ``.tasks/``, etc.). Matches
    are collected across BOTH roots; zero matches or 2+ matches (ambiguous)
    both resolve to ``None`` -- an ambiguous match is never silently
    guessed. Returning the matched ``Path`` (not just a bool) lets a caller
    with a ``::Symbol`` suffix verify the symbol against the one real file
    Tier 2 found, the same way Tier 1 already can.

    Args:
        package_name: Package directory name (e.g. ``datrix-codegen-common``).
        suffix: The candidate's path segments after the package name,
            forward-slash joined, with no leading/trailing slash.
        monorepo_root: Monorepo root directory.

    Returns:
        The unique matched path, or ``None`` if zero or multiple matches
        were found across both search roots.
    """
    package_dir = monorepo_root / package_name
    matches: list[Path] = []
    for root_name in _TIER2_SEARCH_ROOTS:
        root_dir = package_dir / root_name
        if not root_dir.exists():
            continue
        for candidate_path in root_dir.rglob("*"):
            rel = candidate_path.relative_to(root_dir).as_posix()
            if rel.endswith(suffix):
                matches.append(candidate_path)
    if len(matches) == 1:
        return matches[0]
    return None


def _module_level_symbol_exists(file_path: Path, symbol_name: str) -> bool:
    """Return True iff *symbol_name* is declared as a module-level name in
    the Python source at *file_path* -- an Assign/AnnAssign target, or a
    (possibly async) top-level FunctionDef/ClassDef name. Only top-level
    (module.body) statements are inspected, matching the same "module-level
    only" scoping check_import_boundaries.py's shared-vocabulary scanner
    already uses for a structurally identical reason (a name buried inside
    a function body is not a citable module-level symbol).

    Returns False (never raises) if *file_path* does not exist, is not
    valid Python, or cannot be read -- this function only answers "is the
    symbol here", it does not decide whether the base path itself resolved;
    that remains resolve_path_candidate's job.

    Args:
        file_path: Path to the Python source file the ``::Symbol`` suffix
            was appended to.
        symbol_name: The bare identifier named after ``::`` in the span.

    Returns:
        True iff *symbol_name* is a module-level Assign/AnnAssign target
        name, or a top-level (possibly async) function/class name.
    """
    if not file_path.is_file():
        return False
    try:
        source_code = file_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source_code, filename=str(file_path))
    except (OSError, SyntaxError, ValueError):
        return False

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if stmt.name == symbol_name:
                return True
            continue
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == symbol_name:
                return True

    return False


def resolve_path_candidate(span: str, monorepo_root: Path) -> bool:
    """Resolve a path-reference candidate (extraction step 3: Tier 1 + Tier 2).

    Normalizes backslashes to forward slashes, strips a ``D:/datrix/`` /
    ``d:/datrix/`` prefix, then strips and separately verifies a trailing
    ``::SYMBOL_NAME`` suffix (a citation of a module-level declared name,
    e.g. ``plugin.py::_PYTHON_STUB_PATTERNS``) BEFORE stripping a trailing
    line-ref suffix (``:148`` or ``:262,282``/``:262-291`` forms) -- the two
    suffixes point at semantically different things (a declared name vs. a
    line range) and are stripped and checked independently. Tier 1 checks
    the normalized path exists verbatim under *monorepo_root* (a
    trailing-slash candidate must resolve as a directory). Tier 2 (only
    attempted when Tier 1 fails AND the segment immediately after the
    package name is not already ``src`` or ``tests``) searches for a unique
    shorthand match under the package's ``src/``/``tests/`` trees. When a
    ``::SYMBOL_NAME`` suffix was present, whichever tier resolves the base
    path must ALSO find *symbol_name* declared at module level in that file
    (via ``_module_level_symbol_exists``) -- a resolved base path with a
    nonexistent symbol still fails.

    Args:
        span: The raw backtick-span text (path-reference candidate).
        monorepo_root: Monorepo root directory.

    Returns:
        True iff the candidate resolves to a real file/directory (Tier 1 or
        an unambiguous Tier 2 match), and, when a ``::SYMBOL_NAME`` suffix
        was present, that symbol is genuinely declared at module level in
        the resolved file.
    """
    normalized = span.replace("\\", "/")
    normalized = _WINDOWS_ABS_STRIP_RE.sub("", normalized)

    import_name, separator, import_rest = normalized.partition("/")
    import_package_dir = _IMPORT_NAME_TO_PACKAGE_DIR.get(import_name)
    if separator and import_package_dir is not None:
        normalized = f"{import_package_dir}/src/{import_name}/{import_rest}"

    symbol_match = _PATH_SYMBOL_SUFFIX_RE.search(normalized)
    symbol_name: str | None = None
    if symbol_match is not None:
        symbol_name = symbol_match.group(1)
        normalized = normalized[: symbol_match.start()]

    normalized = _LINE_REF_SUFFIX_RE.sub("", normalized)

    is_dir_hint = normalized.endswith("/")
    normalized_stripped = normalized.rstrip("/")

    full_path = monorepo_root / normalized_stripped
    tier1_resolved = full_path.exists() and (full_path.is_dir() if is_dir_hint else True)

    if tier1_resolved:
        if symbol_name is not None:
            return not is_dir_hint and _module_level_symbol_exists(full_path, symbol_name)
        return True

    segments = normalized_stripped.split("/")
    if len(segments) < 2:
        return False

    package_name = segments[0]
    if package_name not in _PACKAGE_DIRS:
        return False

    next_segment = segments[1]
    if next_segment in _TIER2_SEARCH_ROOTS:
        return False

    suffix = "/".join(segments[1:])
    tier2_resolved_path = _tier2_resolve_path(package_name, suffix, monorepo_root)
    if tier2_resolved_path is None:
        return False
    if symbol_name is not None:
        return _module_level_symbol_exists(tier2_resolved_path, symbol_name)
    return True


def resolve_module_candidate(span: str, monorepo_root: Path) -> bool:
    """Resolve a module-reference candidate (extraction step 4).

    Splits the dotted candidate on ``.``; the import name (first segment)
    maps to its package directory via ``_IMPORT_NAME_TO_PACKAGE_DIR``. Walks
    decreasing-length prefixes of the remaining segments, longest to length
    1: the candidate resolves if any prefix matches
    ``<package>/src/<import_name>/<prefix>.py`` or
    ``<package>/src/<import_name>/<prefix>/__init__.py``. This tolerates a
    trailing symbol/attribute/function name appended to a real module path
    (e.g. ``datrix_codegen_kernel.generation.template_generator._dispatch`` resolves via
    the 2-segment prefix ``generation/template_generator.py``).

    Args:
        span: The raw backtick-span text (module-reference candidate).
        monorepo_root: Monorepo root directory.

    Returns:
        True iff any prefix of length >= 1 resolves to a real module file
        or package ``__init__.py``.
    """
    segments = span.split(".")
    import_name = segments[0]
    package_dir_name = _IMPORT_NAME_TO_PACKAGE_DIR.get(import_name)
    if package_dir_name is None:
        return False

    package_src = monorepo_root / package_dir_name / "src" / import_name
    remaining = segments[1:]

    for prefix_len in range(len(remaining), 0, -1):
        prefix_path = package_src.joinpath(*remaining[:prefix_len])
        if prefix_path.with_suffix(".py").exists():
            return True
        if (prefix_path / "__init__.py").exists():
            return True

    return False


def load_exceptions(baseline_path: Path) -> dict[str, str]:
    """Load the committed exceptions baseline: span text -> human reason.

    Args:
        baseline_path: Path to ``docs-conformance-exceptions.json``.

    Returns:
        Mapping of exact backtick-span text to its recorded reason.

    Raises:
        FileNotFoundError: If *baseline_path* does not exist. This baseline
            is a hand-edited, checked-in file (no ``--update-baseline``
            auto-write path exists for it) -- a missing file is a real
            configuration error, never a silent empty-baseline fallback.
    """
    if not baseline_path.exists():
        raise FileNotFoundError(
            f"Docs-conformance exceptions baseline not found at {baseline_path}. "
            f"This file is hand-edited and checked in (never auto-generated); "
            f"restore it from version control."
        )

    with baseline_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    exceptions: dict[str, str] = {}
    for entry in data.get("exceptions", []):
        span = str(entry["span"])
        reason = str(entry["reason"])
        exceptions[span] = reason
    return exceptions


@dataclass(frozen=True)
class UnresolvedReference:
    """One documentation claim that failed resolution against the live tree.

    ``kind`` names the check family: a backtick path or module span, a
    Markdown anchor link whose target heading does not exist, a
    ``Class.member`` claim naming a member the class does not have, a
    decision whose heading status, status paragraph, and named checks disagree,
    a dependency-graph edge the manifests do not declare (or a declared one not
    drawn), a numeric package or repository count, or a Code Quality tool no
    scripts quick-reference documents.
    """

    doc: str
    line: int
    span: str
    kind: Literal["path", "module", "anchor", "member", "decision", "graph", "count", "tooling"]


# ---------------------------------------------------------------------------
# Anchor links: every ``[text](<doc>.md#anchor)`` / ``[text](#anchor)`` link in a
# curated doc must name a heading that exists in the target doc. Path/module
# spans catch a file that moved; only this catches a heading that was renamed
# (a decision heading gaining a status suffix changes its slug), which is how
# several links to a decision's old heading text rotted unnoticed.
# ---------------------------------------------------------------------------

_MD_ANCHOR_LINK_RE = re.compile(r"\]\(([^)\s#]*\.md)?#([^)\s]+)\)")
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
#: An explicit heading id in the ``## Title {#custom-id}`` form these docs use
#: for stable cross-doc anchors. The id is an anchor in its own right, and the
#: heading's text slug is computed WITHOUT the ``{#...}`` suffix.
_EXPLICIT_HEADING_ID_RE = re.compile(r"\s*\{#([^}\s]+)\}\s*$")


def github_heading_slug(heading_text: str) -> str:
    """The anchor GitHub-flavoured Markdown derives from a heading's text.

    Lower-case; every character that is not a word character, whitespace, or
    a hyphen is dropped (so ``&``, ``—``, ``:``, backticks, ``*`` and
    parentheses vanish, leaving the double hyphens the repo's existing links
    carry); whitespace becomes hyphens. Duplicate headings get ``-1``, ``-2``
    suffixes in document order, handled by :func:`heading_slugs`.
    """
    stripped = _SLUG_STRIP_RE.sub("", heading_text.strip().lower())
    return re.sub(r"\s", "-", stripped)


def heading_slugs(doc_text: str) -> set[str]:
    """Every anchor the headings of *doc_text* produce, duplicates suffixed.

    A heading carrying an explicit ``{#custom-id}`` contributes that id as
    well as the slug of its remaining text.
    """
    slugs: set[str] = set()
    seen: dict[str, int] = {}
    for line in doc_text.splitlines():
        if not line.startswith("#"):
            continue
        text = line.lstrip("#")
        if not text.startswith(" "):
            continue
        explicit = _EXPLICIT_HEADING_ID_RE.search(text)
        if explicit is not None:
            slugs.add(explicit.group(1))
            text = text[: explicit.start()]
        base = github_heading_slug(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        slugs.add(base if count == 0 else f"{base}-{count}")
    return slugs


def extract_anchor_links(doc_text: str) -> list[tuple[int, str | None, str]]:
    """Every ``(line, target_doc_or_None, anchor)`` Markdown anchor link in *doc_text*."""
    links: list[tuple[int, str | None, str]] = []
    for line_number, line in enumerate(doc_text.splitlines(), start=1):
        for match in _MD_ANCHOR_LINK_RE.finditer(line):
            target = match.group(1) or None
            links.append((line_number, target, match.group(2)))
    return links


def check_anchor_links(doc_rel: str, doc_text: str, monorepo_root: Path) -> list[UnresolvedReference]:
    """Anchor links in *doc_text* whose target heading (or target doc) does not exist."""
    failures: list[UnresolvedReference] = []
    doc_path = monorepo_root / doc_rel
    slug_cache: dict[Path, set[str] | None] = {}
    for line_number, target, anchor in extract_anchor_links(doc_text):
        target_path = doc_path if target is None else (doc_path.parent / target).resolve()
        if target_path not in slug_cache:
            slug_cache[target_path] = (
                heading_slugs(target_path.read_text(encoding="utf-8-sig"))
                if target_path.is_file()
                else None
            )
        slugs = slug_cache[target_path]
        span = f"{target or ''}#{anchor}"
        if slugs is None:
            failures.append(
                UnresolvedReference(doc=doc_rel, line=line_number, span=span, kind="anchor")
            )
        elif anchor not in slugs:
            failures.append(
                UnresolvedReference(doc=doc_rel, line=line_number, span=span, kind="anchor")
            )
    return failures


# ---------------------------------------------------------------------------
# Class member claims: a doc that binds a short class name to a workspace class
# -- a ``from <package module> import Name`` line, or a fully qualified
# ``package.module.Name`` span -- and then writes ``Name.member`` in a backtick
# span or a code-fence line claims that the class has that member. A module span
# only proves the module exists; this family is what catches a method removed
# from a class the docs still call (a ``TypeRegistry.get_python_type`` example
# outlived the method, and a script copied from it crashed on the call).
#
# Members are read from the source, never by importing a workspace module: the
# class body's functions, nested classes and assignments, every ``self.x`` /
# ``cls.x`` assignment in it, and everything its bases contribute. A base outside
# the workspace is introspected (``dir()``); a class whose members cannot be
# enumerated (a ``__getattr__``, an unresolvable or non-class base, a
# module-level name that is not a class) is open, and every claim on it holds.
# ---------------------------------------------------------------------------

_FENCE_DELIMITER = "```"
_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([a-z_][\w.]*)\s+import\s+\(?([^()#]+?)\)?\s*(?:#.*)?$")
_QUALIFIED_CLASS_SPAN_RE = re.compile(r"^([a-z][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+)\.([A-Z]\w*)$")
#: The member must end the identifier: ``Transpiler.visit_<kind>`` and
#: ``Transpiler.visit_*`` name a family of members, not a member.
_MEMBER_CLAIM_RE = re.compile(r"(?<![\w.])([A-Z]\w*)\.([A-Za-z_]\w*)(?![\w*<])")
_IMPORT_ALIAS_WORD = "as"
_SELF_NAMES: frozenset[str] = frozenset({"self", "cls"})
_DYNAMIC_MEMBER_HOOK = "__getattr__"
_BUILTINS_MODULE = "builtins"
#: Base-class chains are short; the bound only stops a cyclic re-export.
_MAX_CLASS_RESOLUTION_DEPTH = 32


@dataclass(frozen=True)
class ClassMembers:
    """The members a class is known to have; ``is_open`` when that set is incomplete."""

    names: frozenset[str]
    is_open: bool


_OPEN_MEMBERS = ClassMembers(names=frozenset(), is_open=True)


class UnresolvedClassError(LookupError):
    """A doc binds a name to a workspace module that does not define or re-export it."""


@dataclass(frozen=True)
class _ModuleNamespace:
    """The module-level names of one workspace module that a class lookup reads."""

    module: str
    classes: dict[str, ast.ClassDef]
    imported_names: dict[str, tuple[str, str]]
    imported_modules: dict[str, str]
    other_names: frozenset[str]


def _doc_code_texts(doc_text: str) -> list[tuple[int, str]]:
    """Every ``(line, code text)`` of *doc_text*: each code-fence line whole, and
    each backtick span of a prose line."""
    texts: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(doc_text.splitlines(), start=1):
        if line.lstrip().startswith(_FENCE_DELIMITER):
            in_fence = not in_fence
            continue
        if in_fence:
            texts.append((line_number, line))
            continue
        texts.extend(
            (line_number, match.group(1).strip()) for match in _INLINE_CODE_SPAN_RE.finditer(line)
        )
    return texts


def _bound_names(text: str) -> list[tuple[str, str, str]]:
    """``(local name, module, imported name)`` for each name *text* binds: a qualified
    ``package.module.Class`` span, or a single-line ``from module import ...``."""
    span_match = _QUALIFIED_CLASS_SPAN_RE.match(text.removesuffix(_CALL_SPAN_SUFFIX))
    if span_match is not None:
        return [(span_match.group(2), span_match.group(1), span_match.group(2))]
    import_match = _FROM_IMPORT_RE.match(text)
    if import_match is None:
        return []
    bound: list[tuple[str, str, str]] = []
    for item in import_match.group(2).split(","):
        words = item.split()
        if len(words) == 1:
            bound.append((words[0], import_match.group(1), words[0]))
        elif len(words) == 3 and words[1] == _IMPORT_ALIAS_WORD:
            bound.append((words[2], import_match.group(1), words[0]))
    return bound


def extract_class_bindings(code_texts: list[tuple[int, str]]) -> dict[str, set[tuple[str, str]]]:
    """Map each capitalized name the doc binds to a workspace module onto every
    ``(module, imported name)`` it is bound to; a name bound twice differently is
    ambiguous and its claims are never checked."""
    bindings: dict[str, set[tuple[str, str]]] = {}
    for _, text in code_texts:
        for local, module, imported in _bound_names(text):
            if not local[:1].isupper():
                continue
            if module.split(".", 1)[0] not in _IMPORT_NAME_TO_PACKAGE_DIR:
                continue
            bindings.setdefault(local, set()).add((module, imported))
    return bindings


def _workspace_module_file(module: str, monorepo_root: Path) -> Path | None:
    """The source file of workspace *module*, or ``None`` when it is not a workspace module file."""
    segments = module.split(".")
    if segments[0] not in _IMPORT_NAME_TO_PACKAGE_DIR:
        return None
    base = monorepo_root / _IMPORT_NAME_TO_PACKAGE_DIR[segments[0]] / "src" / Path(*segments)
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _absolute_import_source(stmt: ast.ImportFrom, module: str, is_package: bool) -> str:
    """The absolute module a (possibly relative) ``from ... import`` in *module* reads."""
    if stmt.level == 0:
        return stmt.module or ""
    parts = module.split(".") if is_package else module.split(".")[:-1]
    anchor = parts[: len(parts) - (stmt.level - 1)]
    return ".".join([*anchor, stmt.module] if stmt.module else anchor)


def _module_namespace(tree: ast.Module, module: str, is_package: bool) -> _ModuleNamespace:
    classes: dict[str, ast.ClassDef] = {}
    imported_names: dict[str, tuple[str, str]] = {}
    imported_modules: dict[str, str] = {}
    other_names: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            classes[stmt.name] = stmt
        elif isinstance(stmt, ast.ImportFrom):
            source = _absolute_import_source(stmt, module, is_package)
            for alias in stmt.names:
                imported_names[alias.asname or alias.name] = (source, alias.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                imported_modules[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            other_names.add(stmt.name)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            other_names.update(t.id for t in targets if isinstance(t, ast.Name))
    return _ModuleNamespace(module, classes, imported_names, imported_modules, frozenset(other_names))


def _self_assigned_names(node: ast.ClassDef) -> set[str]:
    """Every ``self.x`` / ``cls.x`` the class body assigns, at any depth."""
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
            targets = [sub.target]
        else:
            continue
        for target in targets:
            names.update(
                element.attr
                for element in ast.walk(target)
                if isinstance(element, ast.Attribute)
                and isinstance(element.value, ast.Name)
                and element.value.id in _SELF_NAMES
            )
    return names


def _class_level_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """The statements of a class body, including those nested in its ``if``
    (``if TYPE_CHECKING:``), ``try`` and ``with`` blocks."""
    statements: list[ast.stmt] = []
    for stmt in body:
        statements.append(stmt)
        if isinstance(stmt, ast.If):
            statements.extend(_class_level_statements(stmt.body + stmt.orelse))
        elif isinstance(stmt, ast.Try):
            nested = stmt.body + stmt.orelse + stmt.finalbody
            nested.extend(inner for handler in stmt.handlers for inner in handler.body)
            statements.extend(_class_level_statements(nested))
        elif isinstance(stmt, ast.With):
            statements.extend(_class_level_statements(stmt.body))
    return statements


def _class_body_names(node: ast.ClassDef) -> set[str]:
    """The members the class body itself declares."""
    names = _self_assigned_names(node)
    for stmt in _class_level_statements(node.body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            names.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return names


def _external_class_members(module: str, name: str) -> ClassMembers:
    """Members of a class outside the workspace, by introspection; open when it cannot be loaded."""
    try:
        loaded = importlib.import_module(module)
    except ImportError:
        return _OPEN_MEMBERS
    if not hasattr(loaded, name):
        return _OPEN_MEMBERS
    candidate = getattr(loaded, name)
    if not isinstance(candidate, type):
        return _OPEN_MEMBERS
    return ClassMembers(names=frozenset(dir(candidate)), is_open=False)


class ClassMemberIndex:
    """Resolves ``(module, class name)`` to its members, caching parsed workspace modules."""

    def __init__(self, monorepo_root: Path) -> None:
        self._monorepo_root = monorepo_root
        self._namespaces: dict[str, _ModuleNamespace] = {}

    def _namespace(self, module: str, source_file: Path) -> _ModuleNamespace:
        if module not in self._namespaces:
            try:
                tree = ast.parse(source_file.read_text(encoding="utf-8-sig"), filename=str(source_file))
            except (OSError, SyntaxError, ValueError) as error:
                raise UnresolvedClassError(
                    f"cannot read {source_file} to resolve a class of module {module}: {error}"
                ) from error
            is_package = source_file.name == "__init__.py"
            self._namespaces[module] = _module_namespace(tree, module, is_package)
        return self._namespaces[module]

    def members(self, module: str, name: str, depth: int = 0) -> ClassMembers:
        """The members of class *name* as module *module* exposes it.

        Raises:
            UnresolvedClassError: *module* is a workspace module that neither
                defines nor re-exports *name*.
        """
        if depth > _MAX_CLASS_RESOLUTION_DEPTH:
            return _OPEN_MEMBERS
        source_file = _workspace_module_file(module, self._monorepo_root)
        if source_file is None:
            if module.split(".", 1)[0] in _IMPORT_NAME_TO_PACKAGE_DIR:
                raise UnresolvedClassError(f"workspace module {module} does not exist")
            return _external_class_members(module, name)
        namespace = self._namespace(module, source_file)
        if name in namespace.classes:
            return self._declared_class_members(namespace, namespace.classes[name], depth)
        if name in namespace.imported_names:
            source_module, source_name = namespace.imported_names[name]
            return self.members(source_module, source_name, depth + 1)
        if name in namespace.other_names:
            return _OPEN_MEMBERS
        raise UnresolvedClassError(f"{module} defines no {name}")

    def _base_target(self, base: ast.expr, namespace: _ModuleNamespace) -> tuple[str, str] | None:
        """The ``(module, name)`` a base-class expression names, or ``None`` when it is not a plain name."""
        if isinstance(base, ast.Subscript):
            return self._base_target(base.value, namespace)
        if isinstance(base, ast.Name):
            if base.id in namespace.classes:
                return (namespace.module, base.id)
            if base.id in namespace.imported_names:
                return namespace.imported_names[base.id]
            if hasattr(builtins, base.id):
                return (_BUILTINS_MODULE, base.id)
            return None
        if isinstance(base, ast.Attribute):
            head, _, rest = ast.unparse(base).partition(".")
            if head not in namespace.imported_modules:
                return None
            module_path, _, class_name = f"{namespace.imported_modules[head]}.{rest}".rpartition(".")
            return (module_path, class_name)
        return None

    def _declared_class_members(
        self, namespace: _ModuleNamespace, node: ast.ClassDef, depth: int
    ) -> ClassMembers:
        names = _class_body_names(node)
        is_open = _DYNAMIC_MEMBER_HOOK in names
        for base in node.bases:
            target = self._base_target(base, namespace)
            if target is None:
                is_open = True
                continue
            try:
                inherited = self.members(target[0], target[1], depth + 1)
            except UnresolvedClassError:
                is_open = True
                continue
            names |= inherited.names
            is_open = is_open or inherited.is_open
        return ClassMembers(names=frozenset(names), is_open=is_open)

    def has_member(self, module: str, name: str, member: str) -> bool:
        """Whether class *name* of *module* has *member* (always, when its members are open)."""
        try:
            resolved = self.members(module, name)
        except UnresolvedClassError:
            return False
        return resolved.is_open or member in resolved.names


def check_member_claims(
    doc_rel: str, doc_text: str, member_index: ClassMemberIndex
) -> list[UnresolvedReference]:
    """``Class.member`` claims in *doc_text* naming a member the bound class does not have."""
    code_texts = _doc_code_texts(doc_text)
    bindings = extract_class_bindings(code_texts)
    failures: list[UnresolvedReference] = []
    seen: set[tuple[int, str]] = set()
    for line_number, text in code_texts:
        for match in _MEMBER_CLAIM_RE.finditer(text):
            local, member = match.group(1), match.group(2)
            if local not in bindings or len(bindings[local]) != 1:
                continue
            claim = f"{local}.{member}"
            if (line_number, claim) in seen:
                continue
            seen.add((line_number, claim))
            module, name = next(iter(bindings[local]))
            if not member_index.has_member(module, name, member):
                failures.append(
                    UnresolvedReference(doc=doc_rel, line=line_number, span=claim, kind="member")
                )
    return failures


# ---------------------------------------------------------------------------
# Decision status: every ``### Decision N: ... (Status)`` heading carries a
# status from the closed vocabulary; a ``**Status:**`` paragraph in the section,
# when present, agrees with it; an in-progress decision MUST carry one (it is
# the checklist of what remains); and every ``*.ps1`` gate the section names
# exists under the repo's script trees. A heading that says "in progress" over
# a paragraph that says everything landed, and a decision with no status
# paragraph at all, are the two shapes that shipped unnoticed.
# ---------------------------------------------------------------------------

_DECISION_HEADING_RE = re.compile(r"^### Decision (\d+): (.+?)(?: \(([^()]+)\))?\s*$")
_STATUS_PARAGRAPH_RE = re.compile(r"^\*\*Status:\*\*\s*(.+)$")
_HEADING_STATUS_CLASS: dict[str, str] = {
    "Adopted": "adopted",
    "Implemented": "adopted",
    "Stable": "adopted",
    "Approved — Implementation In Progress": "in-progress",
}
_STATUS_PARAGRAPH_CLASS_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Adopted", "adopted"),
    ("Landed", "adopted"),
    ("Implemented", "adopted"),
    ("Stable", "adopted"),
    ("Approved", "in-progress"),
)
_NAMED_SCRIPT_RE = re.compile(r"`([a-z0-9-]+\.ps1)`")
#: Every folder of the scripts tree holds wrappers (test/, dev/, gates/<family>/, ...), so a
#: named gate is looked up anywhere beneath it.
_SCRIPTS_ROOT: str = "datrix/scripts"


@dataclass(frozen=True)
class DecisionSection:
    """One ``### Decision N:`` section of an architecture doc."""

    number: int
    line: int
    heading_status: str | None
    status_line: int | None
    status_text: str | None
    body: str


def extract_decision_sections(doc_text: str) -> list[DecisionSection]:
    """Every decision section: heading facts, the first status paragraph, the body."""
    lines = doc_text.splitlines()
    starts = [
        (index, match)
        for index, line in enumerate(lines)
        for match in [_DECISION_HEADING_RE.match(line)]
        if match is not None
    ]
    sections: list[DecisionSection] = []
    for position, (index, match) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body_lines = lines[index + 1 : end]
        status_line: int | None = None
        status_text: str | None = None
        for offset, line in enumerate(body_lines):
            status_match = _STATUS_PARAGRAPH_RE.match(line)
            if status_match is not None:
                status_line = index + 2 + offset
                status_text = status_match.group(1).strip()
                break
        sections.append(
            DecisionSection(
                number=int(match.group(1)),
                line=index + 1,
                heading_status=match.group(3),
                status_line=status_line,
                status_text=status_text,
                body="\n".join(body_lines),
            )
        )
    return sections


def _status_paragraph_class(status_text: str) -> str | None:
    for prefix, status_class in _STATUS_PARAGRAPH_CLASS_PREFIXES:
        if status_text.startswith(prefix):
            return status_class
    return None


def check_decision_status(
    doc_rel: str, doc_text: str, monorepo_root: Path
) -> list[UnresolvedReference]:
    """Decision sections whose heading, status paragraph, or named checks disagree."""
    failures: list[UnresolvedReference] = []

    def fail(line: int, message: str) -> None:
        failures.append(UnresolvedReference(doc=doc_rel, line=line, span=message, kind="decision"))

    scripts_root = monorepo_root / _SCRIPTS_ROOT
    known_scripts = frozenset(path.name for path in scripts_root.rglob("*.ps1"))
    for section in extract_decision_sections(doc_text):
        label = f"Decision {section.number}"
        heading_class = (
            _HEADING_STATUS_CLASS.get(section.heading_status)
            if section.heading_status is not None
            else None
        )
        if heading_class is None:
            fail(
                section.line,
                f"{label}: heading carries no status from {sorted(_HEADING_STATUS_CLASS)} "
                f"(found {section.heading_status!r})",
            )
        if section.status_text is None:
            if heading_class == "in-progress":
                fail(
                    section.line,
                    f"{label}: an in-progress decision must carry a **Status:** paragraph "
                    "naming what has landed and what remains",
                )
        else:
            paragraph_class = _status_paragraph_class(section.status_text)
            status_line = section.status_line if section.status_line is not None else section.line
            if paragraph_class is None:
                fail(
                    status_line,
                    f"{label}: **Status:** paragraph starts with an unrecognized status "
                    f"({section.status_text[:40]!r}); expected one of "
                    f"{[prefix for prefix, _ in _STATUS_PARAGRAPH_CLASS_PREFIXES]}",
                )
            elif heading_class is not None and paragraph_class != heading_class:
                fail(
                    status_line,
                    f"{label}: heading says {section.heading_status!r} but the **Status:** "
                    f"paragraph says {section.status_text[:40]!r}",
                )
        for script in sorted(set(_NAMED_SCRIPT_RE.findall(section.body))):
            if script not in known_scripts:
                fail(section.line, f"{label}: names `{script}`, which exists nowhere under {_SCRIPTS_ROOT}")
    return failures


# ---------------------------------------------------------------------------
# Numeric package counts: a curated architecture doc states no count of the
# packages or repositories. A count is a second copy of the list in
# ``.claude/rules/repo-boundaries.md``, and three copies of it disagreed with
# each other and with the disk. A number (digits or an English number word)
# directly before ``packages`` / ``repos`` / ``repositories``, optionally through
# up to two qualifiers (``installable``, ``core``, ``package``, ``toolchain``), in a
# prose line is a claim; Markdown emphasis around the number (``**nineteen**``)
# does not hide it. Code fences are not prose. A count of something other
# than the package set (a measurement, "two packages share a group") is an
# exceptions-baseline entry keyed by the claim's context span.
# ---------------------------------------------------------------------------

_NUMBER_UNIT_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
)
_NUMBER_TENS_WORDS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_NUMBER_RE = (
    rf"(?:\d+|(?:{_NUMBER_TENS_WORDS})(?:[- ](?:{_NUMBER_UNIT_WORDS}))?|{_NUMBER_UNIT_WORDS})"
)
_MARKDOWN_EMPHASIS_RE = r"(?:\*\*|__|\*|_)?"
_MAX_COUNT_QUALIFIERS = 2
_PACKAGE_COUNT_RE = re.compile(
    rf"(?<!\w){_MARKDOWN_EMPHASIS_RE}\b{_NUMBER_RE}\b{_MARKDOWN_EMPHASIS_RE}\s+"
    rf"(?:(?:installable|core|package|toolchain)\s+){{0,{_MAX_COUNT_QUALIFIERS}}}"
    r"(?:packages|repos|repositories)\b",
    re.IGNORECASE,
)
#: Words of the line kept on each side of a count claim in its span, so a baseline entry
#: excuses that one sentence and not every "two packages" a later edit writes.
_COUNT_CONTEXT_WORDS = 5
_COUNT_SPAN_PREFIX = "package count: "


def _prose_lines(doc_text: str) -> list[tuple[int, str]]:
    """Every ``(line, text)`` of *doc_text* outside a code fence (fence delimiters excluded)."""
    lines: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(doc_text.splitlines(), start=1):
        if line.lstrip().startswith(_FENCE_DELIMITER):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((line_number, line))
    return lines


_COUNT_CONTEXT_BEFORE_RE = re.compile(rf"(?<!\S)(?:\S+\s+){{0,{_COUNT_CONTEXT_WORDS}}}$")
_COUNT_CONTEXT_AFTER_RE = re.compile(rf"^(?:\s*\S+){{0,{_COUNT_CONTEXT_WORDS}}}")


def _count_claim_span(line: str, match: re.Match[str]) -> str:
    """The claim with up to five words of its line on each side, whitespace collapsed."""
    before = _COUNT_CONTEXT_BEFORE_RE.search(line[: match.start()])
    after = _COUNT_CONTEXT_AFTER_RE.match(line[match.end() :])
    context = (before.group(0) if before else "") + match.group(0) + (after.group(0) if after else "")
    return _COUNT_SPAN_PREFIX + " ".join(context.split())


def check_package_counts(doc_rel: str, doc_text: str) -> list[UnresolvedReference]:
    """Prose lines of *doc_text* stating a numeric package or repository count."""
    return [
        UnresolvedReference(
            doc=doc_rel, line=line_number, span=_count_claim_span(line, match), kind="count"
        )
        for line_number, line in _prose_lines(doc_text)
        for match in _PACKAGE_COUNT_RE.finditer(line)
    ]


# ---------------------------------------------------------------------------
# Overview claims: the dependency graph and the tooling lines of the overview are
# the claims readers act on most, and both had drifted -- the graph drew most edges
# backwards and invented the generator -> CLI edges, and the tooling lines named a
# type checker as if a script ran it for everyone. Both are read from the one doc
# that makes them; a missing section fails rather than checking nothing.
# ---------------------------------------------------------------------------

OVERVIEW_DOC: str = "datrix/docs/architecture/architecture-overview.md"
_GRAPH_HEADING = "## Dependency Graph"
_MERMAID_FENCE = "```mermaid"
_MERMAID_HEADER_RE = re.compile(r"^graph\s+(?:TD|TB|BT|LR|RL)$")
_MERMAID_NODE_RE = re.compile(r"^([A-Za-z_]\w*)(?:\[([^\[\]]+)\])?$")
_MERMAID_ARROW = "-->"
_GRAPH_SPAN_PREFIX = "dependency graph: "
_TOOLING_SECTION_HEADING = "## Technology Stack"
_TOOLING_SUBSECTION_HEADING = "### Code Quality"
_TOOL_BULLET_RE = re.compile(r"^- \*\*([^*]+)\*\*")
_TOOLING_SPAN_PREFIX = "tooling: "
_QUICK_REFERENCE_NAME = "quick-reference.md"
_PYPROJECT_FILE = "pyproject.toml"
_DISTRIBUTION_NAME_SEPARATORS_RE = re.compile(r"[-_.]+")
_SECTION_STOP_MARKERS: frozenset[str] = frozenset({"#", "##"})
_SUBSECTION_STOP_MARKERS: frozenset[str] = frozenset({"#", "##", "###"})


def _normalized_distribution_name(name: str) -> str:
    """The PEP 503 normalized form of a distribution name (``Datrix_Common`` -> ``datrix-common``)."""
    return _DISTRIBUTION_NAME_SEPARATORS_RE.sub("-", name).lower()


def manifest_dependency_edges(monorepo_root: Path) -> frozenset[tuple[str, str]]:
    """Every ``(dependent, dependency)`` pair a package's ``[project] dependencies`` declares
    between Datrix packages. An unreadable manifest propagates: a package silently dropped
    would make the graph check pass against a smaller set."""
    edges: set[tuple[str, str]] = set()
    for name, project_root in discover_packages(monorepo_root).items():
        for spec in read_project_dependencies(project_root / _PYPROJECT_FILE):
            dependency = _normalized_distribution_name(parse_package_name(spec))
            if dependency.startswith(DATRIX_PREFIX):
                edges.add((name, dependency))
    return frozenset(edges)


def _numbered_lines(doc_text: str) -> list[tuple[int, str]]:
    return list(enumerate(doc_text.splitlines(), start=1))


def _section_lines(
    lines: list[tuple[int, str]], heading: str, stop_markers: frozenset[str]
) -> list[tuple[int, str]] | None:
    """The ``(line, text)`` pairs under the exact *heading*, up to the next heading whose
    ``#`` marker is in *stop_markers*; ``None`` when there is no such heading."""
    for index, (_, line) in enumerate(lines):
        if line.strip() != heading:
            continue
        section: list[tuple[int, str]] = []
        for line_number, body_line in lines[index + 1 :]:
            if body_line.startswith("#") and body_line.split(" ", 1)[0] in stop_markers:
                break
            section.append((line_number, body_line))
        return section
    return None


def _mermaid_block(section: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]] | None:
    """``(fence line, stripped lines)`` of the first ```` ```mermaid ```` fence of *section*;
    ``None`` when there is none or it is never closed."""
    fence_line: int | None = None
    block: list[tuple[int, str]] = []
    for line_number, line in section:
        stripped = line.strip()
        if fence_line is None:
            if stripped == _MERMAID_FENCE:
                fence_line = line_number
            continue
        if stripped.startswith(_FENCE_DELIMITER):
            return fence_line, block
        block.append((line_number, stripped))
    return None


@dataclass(frozen=True)
class DrawnGraph:
    """The edges a mermaid ``graph`` draws, by node label, and the lines it could not read."""

    edges: dict[tuple[str, str], int]
    problems: list[tuple[int, str]]


def _record_node(
    match: re.Match[str], line_number: int, labels: dict[str, str], problems: list[tuple[int, str]]
) -> str:
    node_id, label = match.group(1), match.group(2)
    if label is not None:
        label = label.strip()
        if labels.setdefault(node_id, label) != label:
            problems.append(
                (line_number, f"node {node_id} is labelled both {labels[node_id]!r} and {label!r}")
            )
    return node_id


def parse_mermaid_graph(block: list[tuple[int, str]]) -> DrawnGraph:
    """Read a ``graph TD`` block of ``Id[label]`` nodes and ``A --> B`` edges.

    A line of any other shape (another arrow form, a subgraph, a style line) is a
    problem, never skipped: an edge the parser cannot read would be an edge the
    comparison silently loses.
    """
    labels: dict[str, str] = {}
    problems: list[tuple[int, str]] = []
    id_edges: list[tuple[int, str, str]] = []
    for line_number, line in block:
        if not line or _MERMAID_HEADER_RE.match(line):
            continue
        matches = [_MERMAID_NODE_RE.match(part.strip()) for part in line.split(_MERMAID_ARROW)]
        nodes = [match for match in matches if match is not None]
        if len(nodes) != len(matches):
            problems.append(
                (line_number, f"unreadable mermaid line {line!r}; expected `Id[label]` nodes joined by `-->`")
            )
            continue
        ids = [_record_node(match, line_number, labels, problems) for match in nodes]
        id_edges.extend((line_number, source, target) for source, target in zip(ids, ids[1:]))
    edges: dict[tuple[str, str], int] = {}
    for line_number, source, target in id_edges:
        unlabelled = [node_id for node_id in (source, target) if node_id not in labels]
        if unlabelled:
            problems.append((line_number, f"node {unlabelled[0]} has no [label] naming its package"))
            continue
        edges.setdefault((labels[source], labels[target]), line_number)
    return DrawnGraph(edges=edges, problems=problems)


def check_dependency_graph(
    doc_rel: str, doc_text: str, declared: frozenset[tuple[str, str]]
) -> list[UnresolvedReference]:
    """The dependency graph's edges, drawn dependent --> dependency, against *declared*.

    Every drawn edge must be a declared dependency and every declared dependency must be
    drawn; a reversed edge fails both ways.
    """

    def fail(line: int, message: str) -> UnresolvedReference:
        return UnresolvedReference(doc=doc_rel, line=line, span=_GRAPH_SPAN_PREFIX + message, kind="graph")

    section = _section_lines(_numbered_lines(doc_text), _GRAPH_HEADING, _SECTION_STOP_MARKERS)
    found = _mermaid_block(section) if section is not None else None
    if found is None:
        return [fail(1, f"no closed ```mermaid block under {_GRAPH_HEADING!r}")]
    heading_line, block = found
    drawn = parse_mermaid_graph(block)
    failures = [fail(line, message) for line, message in drawn.problems]
    for dependent, dependency in sorted(set(drawn.edges) - declared):
        failures.append(
            fail(
                drawn.edges[(dependent, dependency)],
                f"{dependent} --> {dependency} is drawn, but {dependent}'s [project] "
                f"dependencies do not name {dependency} (edges point dependent --> dependency)",
            )
        )
    for dependent, dependency in sorted(declared - set(drawn.edges)):
        failures.append(
            fail(
                heading_line,
                f"{dependent} --> {dependency} is declared in {dependent}/{_PYPROJECT_FILE} "
                "but not drawn",
            )
        )
    return failures


def documented_tool_text(monorepo_root: Path) -> str:
    """The lower-cased text of every ``quick-reference.md`` under the scripts tree."""
    scripts_root = monorepo_root / _SCRIPTS_ROOT
    return "\n".join(
        path.read_text(encoding="utf-8-sig").lower()
        for path in sorted(scripts_root.rglob(_QUICK_REFERENCE_NAME))
    )


def check_tooling_claims(
    doc_rel: str, doc_text: str, documented_text: str
) -> list[UnresolvedReference]:
    """Tools the Technology Stack's Code Quality lines name that no scripts quick-reference
    documents. *documented_text* is :func:`documented_tool_text`."""

    def fail(line: int, message: str) -> UnresolvedReference:
        return UnresolvedReference(doc=doc_rel, line=line, span=_TOOLING_SPAN_PREFIX + message, kind="tooling")

    stack = _section_lines(_numbered_lines(doc_text), _TOOLING_SECTION_HEADING, _SECTION_STOP_MARKERS)
    tooling = (
        _section_lines(stack, _TOOLING_SUBSECTION_HEADING, _SUBSECTION_STOP_MARKERS)
        if stack is not None
        else None
    )
    if tooling is None:
        return [fail(1, f"no {_TOOLING_SUBSECTION_HEADING!r} under {_TOOLING_SECTION_HEADING!r}")]
    tools = [
        (line_number, match.group(1).strip())
        for line_number, line in tooling
        for match in [_TOOL_BULLET_RE.match(line)]
        if match is not None
    ]
    if not tools:
        return [fail(1, f"{_TOOLING_SUBSECTION_HEADING!r} names no `- **tool**` line")]
    return [
        fail(line_number, f"{tool} is named, but no {_SCRIPTS_ROOT}/**/{_QUICK_REFERENCE_NAME} documents it")
        for line_number, tool in tools
        if re.search(rf"(?<![\w-]){re.escape(tool.lower())}(?![\w-])", documented_text) is None
    ]


def check_overview_claims(monorepo_root: Path) -> list[UnresolvedReference]:
    """The overview's dependency graph and tooling lines, against the manifests and the
    scripts' quick-references.

    Raises:
        FileNotFoundError: If the overview no longer exists.
    """
    doc_path = monorepo_root / OVERVIEW_DOC
    if not doc_path.is_file():
        raise FileNotFoundError(
            f"The architecture overview {OVERVIEW_DOC} no longer exists at {doc_path}; the "
            "dependency-graph and tooling checks read it. Update OVERVIEW_DOC in "
            "check_docs_conformance.py to the doc that carries them."
        )
    doc_text = doc_path.read_text(encoding="utf-8-sig")
    return [
        *check_dependency_graph(OVERVIEW_DOC, doc_text, manifest_dependency_edges(monorepo_root)),
        *check_tooling_claims(OVERVIEW_DOC, doc_text, documented_tool_text(monorepo_root)),
    ]


def scan_docs(
    monorepo_root: Path, doc_files: tuple[str, ...], *, architecture_docs: bool
) -> list[UnresolvedReference]:
    """Scan every doc in *doc_files* for unresolved path/module/anchor/member references.

    Args:
        monorepo_root: Monorepo root directory.
        doc_files: Repo-relative paths of docs to scan (the curated
            ``ARCHITECTURE_DOC_FILES`` or ``REFERENCE_DOC_FILES`` constant in
            normal use).
        architecture_docs: Whether the architecture-only checks also run: the
            Decision-status check and the numeric package-count check.
            Reference docs carry no decision sections and are not curated
            architecture prose.

    Returns:
        Every unresolved reference found, across all docs, in doc-then-line
        order.

    Raises:
        FileNotFoundError: If an entry in *doc_files* does not exist on
            disk -- a curated doc file disappearing is itself a defect
            (the constant must be kept in sync with the tree), never a
            silently-skipped file.
    """
    unresolved: list[UnresolvedReference] = []
    member_index = ClassMemberIndex(monorepo_root)
    for doc_rel in doc_files:
        doc_path = monorepo_root / doc_rel
        if not doc_path.exists():
            raise FileNotFoundError(
                f"Doc {doc_rel} (listed in ARCHITECTURE_DOC_FILES or REFERENCE_DOC_FILES) "
                f"no longer exists at {doc_path}. Update the constant in "
                f"check_docs_conformance.py to match the current tree."
            )

        doc_text = doc_path.read_text(encoding="utf-8-sig")

        for line_number, span in extract_path_candidates(doc_text):
            if not resolve_path_candidate(span, monorepo_root):
                unresolved.append(
                    UnresolvedReference(doc=doc_rel, line=line_number, span=span, kind="path")
                )

        for line_number, span in extract_module_candidates(doc_text):
            if not resolve_module_candidate(span, monorepo_root):
                unresolved.append(
                    UnresolvedReference(doc=doc_rel, line=line_number, span=span, kind="module")
                )

        unresolved.extend(check_anchor_links(doc_rel, doc_text, monorepo_root))
        unresolved.extend(check_member_claims(doc_rel, doc_text, member_index))
        if architecture_docs:
            unresolved.extend(check_decision_status(doc_rel, doc_text, monorepo_root))
            unresolved.extend(check_package_counts(doc_rel, doc_text))

    return unresolved


def check_against_exceptions(
    unresolved: list[UnresolvedReference], exceptions: dict[str, str]
) -> list[UnresolvedReference]:
    """Filter *unresolved* against the exceptions baseline.

    Args:
        unresolved: Every unresolved reference found by ``scan_docs``.
        exceptions: Span text -> reason, as returned by ``load_exceptions``.

    Returns:
        The subset of *unresolved* whose span text is NOT present in
        *exceptions* -- these are the actual gate failures.
    """
    return [ref for ref in unresolved if ref.span not in exceptions]



# ---------------------------------------------------------------------------
# --self-test: plain-Python edge-case checks for this scanner's own functions
# (Invariant I5). Real tempfile.TemporaryDirectory() fixtures and
# assert statements only -- no pytest, no unittest.mock/SimpleNamespace, per
# project test guidelines. Fixtures are built under the REAL package/import
# names (``datrix-common``, ``datrix-codegen-common``) inside a tmp dir
# acting as a fake monorepo root, because resolve_path_candidate /
# resolve_module_candidate hardcode the fixed 13 package-directory names / 12
# import names as module-level constants (by design). Runs automatically as
# an unconditional first step of every invocation (see main()), and can be
# run in isolation via --self-test. Mirrors the _ok/_fail/_step harness
# pattern established by test_specific_selection_gate.py.
# ---------------------------------------------------------------------------

def _check_windows_absolute_span_is_a_candidate() -> None:
    doc_text = "See `D:\\datrix\\datrix-common\\src\\datrix_common\\foo.py` for details."
    candidates = extract_path_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][1] == "D:\\datrix\\datrix-common\\src\\datrix_common\\foo.py"


def _check_package_prefixed_span_is_a_candidate() -> None:
    doc_text = "See `datrix-common/src/datrix_common/foo.py` for details."
    candidates = extract_path_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][1] == "datrix-common/src/datrix_common/foo.py"


def _check_bare_span_with_no_package_prefix_is_excluded() -> None:
    doc_text = "See `foo.py` for details."
    candidates = extract_path_candidates(doc_text)
    assert candidates == [], f"bare span with no package anchor must be excluded, got {candidates}"


def _check_ellipsis_elided_span_is_rejected() -> None:
    doc_text = "See `datrix-codegen-common/.../subdir/file.py` for details."
    candidates = extract_path_candidates(doc_text)
    assert candidates == [], f"ellipsis-elided span must be rejected, got {candidates}"


def _check_placeholder_span_is_rejected() -> None:
    doc_text = (
        "Baselines live at "
        "`datrix-codegen-common/tests/parity/baselines/<example_id>/<language>.sha256`."
    )
    candidates = extract_path_candidates(doc_text)
    assert candidates == [], f"placeholder span must be rejected, got {candidates}"


def _check_glob_span_is_rejected() -> None:
    doc_text = "See `datrix-common/src/datrix_common/*.py` for details."
    candidates = extract_path_candidates(doc_text)
    assert candidates == [], f"glob span must be rejected, got {candidates}"


def _check_line_ref_suffix_is_captured_verbatim_by_extraction() -> None:
    doc_text = "See `datrix-common/src/datrix_common/foo.py:42` for details."
    candidates = extract_path_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][1] == "datrix-common/src/datrix_common/foo.py:42"


def _check_line_number_is_tracked_per_span() -> None:
    doc_text = "line one\nline two\n`datrix-common/src/datrix_common/foo.py`\n"
    candidates = extract_path_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][0] == 3, f"expected line 3, got {candidates[0][0]}"


def _check_fully_qualified_module_span_is_a_candidate() -> None:
    doc_text = "See `datrix_codegen_kernel.generation.template_generator` for details."
    candidates = extract_module_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][1] == "datrix_codegen_kernel.generation.template_generator"


def _check_generic_dotted_identifier_without_known_import_name_is_excluded() -> None:
    doc_text = "Set `service.name` to the desired value."
    candidates = extract_module_candidates(doc_text)
    assert candidates == [], f"unknown import-name-first segment must be excluded, got {candidates}"


def _check_trailing_class_name_segment_is_excluded_from_extraction() -> None:
    doc_text = "See `datrix_codegen_kernel.orchestration.hooks.migration_hooks.DefaultMigrationHooks`."
    candidates = extract_module_candidates(doc_text)
    assert candidates == [], f"trailing PascalCase class name must break the regex, got {candidates}"


def _check_tier1_literal_match_resolves() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        assert resolve_path_candidate("datrix-common/src/datrix_common/foo.py", root) is True


def _check_tier1_directory_hint_requires_a_real_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        (root / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)
        file_masquerading_as_dir = root / "datrix-common" / "src" / "datrix_common" / "notadir"
        file_masquerading_as_dir.write_text("x\n", encoding="utf-8")
        resolved = resolve_path_candidate("datrix-common/src/datrix_common/notadir/", root)
        assert resolved is False, "a file at a trailing-slash candidate's path must not resolve"


def _check_genuinely_missing_path_stays_unresolved() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        (root / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)
        resolved = resolve_path_candidate("datrix-common/src/datrix_common/nope.py", root)
        assert resolved is False, "a genuinely missing path must stay unresolved"


def _check_line_ref_suffix_is_stripped_before_resolution() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        assert resolve_path_candidate("datrix-common/src/datrix_common/foo.py:42", root) is True
        assert (
            resolve_path_candidate("datrix-common/src/datrix_common/foo.py:262-291", root) is True
        )
        assert (
            resolve_path_candidate("datrix-common/src/datrix_common/foo.py:262,282", root) is True
        )


def _check_tier2_src_shorthand_match_resolves() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = (
            root
            / "datrix-codegen-common"
            / "src"
            / "datrix_codegen_common"
            / "orchestration"
            / "hooks"
            / "seed_hooks.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        resolved = resolve_path_candidate(
            "datrix-codegen-common/orchestration/hooks/seed_hooks.py", root
        )
        assert resolved is True, "unique Tier-2 shorthand match under src/ must resolve"


def _check_tier2_tests_shorthand_match_resolves_with_two_segment_omission() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "tests" / "unit" / "generation" / "test_foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("def test_x(): ...\n", encoding="utf-8")
        resolved = resolve_path_candidate("datrix-common/generation/test_foo.py", root)
        assert resolved is True, "unique Tier-2 shorthand match under tests/ must resolve"


def _check_tier2_is_skipped_when_next_segment_is_already_tests() -> None:
    """A candidate that already writes 'tests/' explicitly is never expanded
    by Tier 2 -- if the exact literal path doesn't exist, it stays
    unresolved. This is what real doc drift looked like: a doc citing
    'datrix-common/tests/generation/x.py' when the real file is one level
    deeper at 'datrix-common/tests/unit/generation/x.py'."""
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "tests" / "unit" / "generation" / "test_foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("def test_x(): ...\n", encoding="utf-8")
        resolved = resolve_path_candidate("datrix-common/tests/generation/test_foo.py", root)
        assert resolved is False, "Tier 2 must be skipped when next segment is already 'tests'"


def _check_ambiguous_tier2_match_stays_unresolved() -> None:
    """Adversarial case: two real files whose relative paths both end with
    the same suffix. An ambiguous Tier-2 match MUST stay unresolved -- if
    this ever silently picked one, the gate would produce a false negative
    (a doc citing the wrong file would pass)."""
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        first = root / "datrix-common" / "src" / "datrix_common" / "foo" / "bar.py"
        second = root / "datrix-common" / "src" / "datrix_common" / "baz" / "bar.py"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        first.write_text("x = 1\n", encoding="utf-8")
        second.write_text("y = 2\n", encoding="utf-8")
        resolved = resolve_path_candidate("datrix-common/bar.py", root)
        assert resolved is False, "an ambiguous Tier-2 match must never be silently guessed"


def _check_exact_module_match_resolves() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "config" / "parser.py"
        target.parent.mkdir(parents=True)
        target.write_text("class ConfigParser: ...\n", encoding="utf-8")
        resolved = resolve_module_candidate("datrix_common.config.parser", root)
        assert resolved is True, "exact module path must resolve"


def _check_trailing_symbol_name_is_tolerated() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "config" / "parser.py"
        target.parent.mkdir(parents=True)
        target.write_text("def _dispatch(): ...\n", encoding="utf-8")
        resolved = resolve_module_candidate("datrix_common.config.parser._dispatch", root)
        assert resolved is True, "a trailing symbol/attribute name must be tolerated"


def _check_leading_underscore_path_symbol_resolves() -> None:
    """A path-form `module.py::_CONSTANT` reference to a REAL module-level
    leading-underscore constant must resolve -- the exact shape of the
    three previously-false-positive doc references this task fixes."""
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "plugin.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "_SOME_STUB_PATTERNS: tuple[int, ...] = (1, 2, 3)\n",
            encoding="utf-8",
        )
        resolved = resolve_path_candidate(
            "datrix-common/src/datrix_common/plugin.py::_SOME_STUB_PATTERNS", root
        )
        assert resolved is True, "a real module-level leading-underscore constant must resolve"


def _check_path_symbol_suffix_naming_nonexistent_symbol_stays_unresolved() -> None:
    """A path-form `module.py::Symbol` reference where the BASE FILE exists
    but the symbol does not must still fail -- proves the fix performs real
    symbol verification rather than merely stripping the `::Symbol` suffix
    and checking file existence (the acceptance property's required
    negative control)."""
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "plugin.py"
        target.parent.mkdir(parents=True)
        target.write_text("_REAL_CONSTANT = 1\n", encoding="utf-8")
        resolved = resolve_path_candidate(
            "datrix-common/src/datrix_common/plugin.py::NoSuchSymbol", root
        )
        assert resolved is False, "a nonexistent symbol on a real file must NOT resolve"


def _check_package_init_module_resolves() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "stdlib" / "__init__.py"
        target.parent.mkdir(parents=True)
        target.write_text("", encoding="utf-8")
        assert resolve_module_candidate("datrix_common.stdlib", root) is True


def _check_genuinely_missing_module_stays_unresolved() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        (root / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)
        resolved = resolve_module_candidate("datrix_common.nonexistent.module", root)
        assert resolved is False, "a genuinely missing module must stay unresolved"


def _check_unknown_import_name_stays_unresolved() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        resolved = resolve_module_candidate("not_a_real_import.foo", root)
        assert resolved is False, "an unknown import name must never resolve"


def _check_span_present_in_baseline_is_removed_from_failures() -> None:
    unresolved = [
        UnresolvedReference(doc="pkg/docs/architecture.md", line=5, span="a/b.py", kind="path"),
        UnresolvedReference(doc="pkg/docs/architecture.md", line=9, span="c/d.py", kind="path"),
    ]
    exceptions = {"a/b.py": "legitimately removed, see migration notes"}
    failures = check_against_exceptions(unresolved, exceptions)
    assert failures == [
        UnresolvedReference(doc="pkg/docs/architecture.md", line=9, span="c/d.py", kind="path")
    ], f"exception-listed span must be removed from failures, got {failures}"


def _check_span_absent_from_baseline_remains_a_failure() -> None:
    unresolved = [
        UnresolvedReference(doc="pkg/docs/architecture.md", line=5, span="a/b.py", kind="path"),
    ]
    failures = check_against_exceptions(unresolved, {})
    assert failures == unresolved, f"span absent from baseline must remain a failure, got {failures}"


def _check_load_exceptions_reads_span_to_reason_mapping() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        baseline_path = Path(tmp) / "docs-conformance-exceptions.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "exceptions": [
                        {
                            "span": "a/b.py",
                            "doc": "pkg/docs/architecture.md",
                            "reason": "removed",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        exceptions = load_exceptions(baseline_path)
        assert exceptions == {"a/b.py": "removed"}, f"unexpected mapping: {exceptions}"


def _check_load_exceptions_raises_when_file_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        missing_path = Path(tmp) / "does-not-exist.json"
        try:
            load_exceptions(missing_path)
        except FileNotFoundError:
            return
        raise AssertionError("load_exceptions() must raise FileNotFoundError for a missing baseline")


def _self_test_checks() -> list[NamedCheck]:
    """Every named self-test check, resolved at call time so a check may be
    defined anywhere in this module."""
    return named_checks(
        [
            _check_windows_absolute_span_is_a_candidate,
            _check_package_prefixed_span_is_a_candidate,
            _check_bare_span_with_no_package_prefix_is_excluded,
            _check_ellipsis_elided_span_is_rejected,
            _check_placeholder_span_is_rejected,
            _check_glob_span_is_rejected,
            _check_line_ref_suffix_is_captured_verbatim_by_extraction,
            _check_line_number_is_tracked_per_span,
            _check_fully_qualified_module_span_is_a_candidate,
            _check_generic_dotted_identifier_without_known_import_name_is_excluded,
            _check_trailing_class_name_segment_is_excluded_from_extraction,
            _check_tier1_literal_match_resolves,
            _check_tier1_directory_hint_requires_a_real_directory,
            _check_genuinely_missing_path_stays_unresolved,
            _check_line_ref_suffix_is_stripped_before_resolution,
            _check_tier2_src_shorthand_match_resolves,
            _check_tier2_tests_shorthand_match_resolves_with_two_segment_omission,
            _check_tier2_is_skipped_when_next_segment_is_already_tests,
            _check_ambiguous_tier2_match_stays_unresolved,
            _check_leading_underscore_path_symbol_resolves,
            _check_path_symbol_suffix_naming_nonexistent_symbol_stays_unresolved,
            _check_exact_module_match_resolves,
            _check_trailing_symbol_name_is_tolerated,
            _check_package_init_module_resolves,
            _check_genuinely_missing_module_stays_unresolved,
            _check_unknown_import_name_stays_unresolved,
            _check_span_present_in_baseline_is_removed_from_failures,
            _check_span_absent_from_baseline_remains_a_failure,
            _check_load_exceptions_reads_span_to_reason_mapping,
            _check_load_exceptions_raises_when_file_missing,
            _check_heading_slug_matches_github_for_punctuated_headings,
            _check_duplicate_headings_get_numbered_slugs,
            _check_explicit_heading_id_is_an_anchor_and_text_slug_excludes_it,
            _check_anchor_link_to_existing_heading_resolves_across_docs,
            _check_anchor_link_to_missing_heading_or_doc_fails,
            _check_decision_heading_without_status_fails,
            _check_adopted_decision_without_status_paragraph_is_accepted,
            _check_in_progress_decision_requires_status_paragraph,
            _check_heading_and_status_paragraph_disagreement_fails,
            _check_landed_status_paragraph_counts_as_adopted,
            _check_named_gate_script_must_exist_on_disk,
            _check_import_name_path_that_exists_resolves,
            _check_import_name_path_that_does_not_exist_stays_unresolved,
            _check_call_suffixed_module_span_is_extracted_and_resolved,
            _check_reference_doc_is_scanned_without_the_decision_check,
            _check_member_claim_on_missing_method_fails_and_real_members_resolve,
            _check_member_claim_follows_reexports_and_inherited_members,
            _check_member_claim_on_open_or_unbound_name_is_not_checked,
            _check_member_claim_on_name_the_module_does_not_define_fails,
            _check_graph_drawing_exactly_the_manifest_edges_passes,
            _check_reversed_graph_edge_fails,
            _check_missing_graph_edge_fails,
            _check_unreadable_graph_line_or_missing_graph_fails,
            _check_numeric_package_count_fails,
            _check_count_of_another_noun_or_in_a_fence_is_not_a_claim,
            _check_documented_tools_pass_and_only_code_quality_is_read,
            _check_undocumented_tool_fails,
            _check_missing_or_empty_tooling_section_fails,
        ]
    )


_MEMBER_FIXTURE_REGISTRY = (
    "from typing import TYPE_CHECKING\n"
    "\n"
    "class Registry:\n"
    "    LIMIT = 3\n"
    "    kind: str\n"
    "\n"
    "    def __init__(self) -> None:\n"
    "        self.count = 0\n"
    "\n"
    "    @classmethod\n"
    "    def resolve_name(cls, name: str) -> str:\n"
    "        return name\n"
    "\n"
    "    if TYPE_CHECKING:\n"
    "        def typed_only(self) -> None: ...\n"
    "\n"
    "class Failure(Exception):\n"
    "    pass\n"
    "\n"
    "class Dynamic:\n"
    "    def __getattr__(self, name: str) -> str:\n"
    "        return name\n"
    "\n"
    "class Unknowable(SomethingUndefined):\n"
    "    pass\n"
    "\n"
    "TABLE = {}\n"
)


def _write_member_fixture(root: Path) -> None:
    """A fake ``datrix_common`` with a class module, a subclass module and a re-exporting package."""
    package = root / "datrix-common" / "src" / "datrix_common" / "types"
    package.mkdir(parents=True)
    (package / "registry.py").write_text(_MEMBER_FIXTURE_REGISTRY, encoding="utf-8")
    (package / "child.py").write_text(
        "from .registry import Registry\n\nclass Child(Registry):\n    def own(self) -> None: ...\n",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text("from .child import Child as Child\n", encoding="utf-8")


def _member_claim_spans(root: Path, doc_text: str) -> list[str]:
    return [ref.span for ref in check_member_claims("d.md", doc_text, ClassMemberIndex(root))]


def _check_member_claim_on_missing_method_fails_and_real_members_resolve() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        _write_member_fixture(root)
        doc_text = (
            "```python\n"
            "from datrix_common.types.registry import Registry\n"
            "Registry.resolve_name('x'); Registry.LIMIT; Registry.kind; Registry.typed_only\n"
            "```\n"
            "Raised by `Registry.count` and by `Registry.get_python_type`.\n"
        )
        assert _member_claim_spans(root, doc_text) == ["Registry.get_python_type"]
        qualified = "See `datrix_common.types.registry.Registry`; call `Registry.gone()`, `Registry.visit_<kind>`.\n"
        failures = check_member_claims("d.md", qualified, ClassMemberIndex(root))
        assert [(f.span, f.line, f.kind) for f in failures] == [("Registry.gone", 1, "member")], failures


def _check_member_claim_follows_reexports_and_inherited_members() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        _write_member_fixture(root)
        doc_text = (
            "```python\n"
            "from datrix_common.types import Child\n"
            "from datrix_common.types.registry import Failure as Raised\n"
            "Child.own(); Child.resolve_name('x'); Child.count; Child.missing\n"
            "Raised.args; Raised.with_traceback; Raised.nonexistent\n"
            "```\n"
        )
        assert _member_claim_spans(root, doc_text) == ["Child.missing", "Raised.nonexistent"]


def _check_member_claim_on_open_or_unbound_name_is_not_checked() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        _write_member_fixture(root)
        doc_text = (
            "```python\n"
            "from datrix_common.types.registry import Dynamic, Unknowable, TABLE\n"
            "from pathlib import Path\n"
            "Dynamic.anything; Unknowable.anything; TABLE.keys(); Path.no_such; Other.no_such\n"
            "```\n"
        )
        assert _member_claim_spans(root, doc_text) == []


def _check_member_claim_on_name_the_module_does_not_define_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        _write_member_fixture(root)
        doc_text = (
            "```python\n"
            "from datrix_common.types.registry import Removed\n"
            "from datrix_common.types.gone import Vanished\n"
            "Removed.attr; Vanished.attr\n"
            "```\n"
        )
        assert _member_claim_spans(root, doc_text) == ["Removed.attr", "Vanished.attr"]


def _check_heading_slug_matches_github_for_punctuated_headings() -> None:
    cases = {
        "Decision 14: Runtime Configuration & Secrets — Zero-Environment Architecture": (
            "decision-14-runtime-configuration--secrets--zero-environment-architecture"
        ),
        "Decision 2: `datrix-codegen-*` Naming": "decision-2-datrix-codegen--naming",
        "Decision 99: .Web / ASP.Style Client Generator (Adopted)": (
            "decision-99-web--aspstyle-client-generator-adopted"
        ),
    }
    for heading, expected in cases.items():
        assert github_heading_slug(heading) == expected, (heading, github_heading_slug(heading))


def _check_duplicate_headings_get_numbered_slugs() -> None:
    slugs = heading_slugs("## Result\n\ntext\n\n## Result\n")
    assert slugs == {"result", "result-1"}, slugs


def _check_explicit_heading_id_is_an_anchor_and_text_slug_excludes_it() -> None:
    slugs = heading_slugs("## Transpiler modules {#transpiler-modules}\n")
    assert slugs == {"transpiler-modules"}, slugs
    slugs = heading_slugs("## Target-Rendering Contract {#target-rendering-contract}\n")
    assert slugs == {"target-rendering-contract"}, slugs


def _check_anchor_link_to_existing_heading_resolves_across_docs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "target.md").write_text("## Real Heading\n", encoding="utf-8")
        (root / "docs" / "source.md").write_text(
            "See [it](target.md#real-heading) and [self](#local).\n\n## Local\n",
            encoding="utf-8",
        )
        failures = check_anchor_links("docs/source.md", (root / "docs" / "source.md").read_text(), root)
        assert failures == [], failures


def _check_anchor_link_to_missing_heading_or_doc_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "target.md").write_text("## Real Heading\n", encoding="utf-8")
        source = "See [a](target.md#renamed-heading) and [b](gone.md#anything).\n"
        (root / "docs" / "source.md").write_text(source, encoding="utf-8")
        failures = check_anchor_links("docs/source.md", source, root)
        assert [f.span for f in failures] == ["target.md#renamed-heading", "gone.md#anything"], failures
        assert all(f.kind == "anchor" for f in failures)


def _check_decision_heading_without_status_fails() -> None:
    doc = "### Decision 7: Extension Naming\n\nbody\n"
    failures = check_decision_status("d.md", doc, Path("."))
    assert len(failures) == 1 and "carries no status" in failures[0].span, failures


def _check_adopted_decision_without_status_paragraph_is_accepted() -> None:
    doc = "### Decision 1: No Separate IR Layer (Adopted)\n\n**Rationale:** because.\n"
    assert check_decision_status("d.md", doc, Path(".")) == []


def _check_in_progress_decision_requires_status_paragraph() -> None:
    doc = "### Decision 43: Frontend (Approved — Implementation In Progress)\n\nbody\n"
    failures = check_decision_status("d.md", doc, Path("."))
    assert len(failures) == 1 and "must carry a **Status:**" in failures[0].span, failures


def _check_heading_and_status_paragraph_disagreement_fails() -> None:
    doc = (
        "### Decision 25: Language Generator (Approved — Implementation In Progress)\n\n"
        "**Status:** Adopted. Every increment landed.\n"
    )
    failures = check_decision_status("d.md", doc, Path("."))
    assert len(failures) == 1 and "heading says" in failures[0].span, failures
    assert failures[0].line == 3


def _check_landed_status_paragraph_counts_as_adopted() -> None:
    doc = "### Decision 30: Floor (Adopted)\n\n**Status:** Landed across every platform.\n"
    assert check_decision_status("d.md", doc, Path(".")) == []


def _check_named_gate_script_must_exist_on_disk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "datrix" / "scripts" / "test").mkdir(parents=True)
        (root / "datrix" / "scripts" / "test" / "real-gate.ps1").write_text("", encoding="utf-8")
        nested = root / "datrix" / "scripts" / "gates" / "parity"
        nested.mkdir(parents=True)
        (nested / "nested-gate.ps1").write_text("", encoding="utf-8")
        doc = (
            "### Decision 9: Store (Adopted)\n\n"
            "Held by `real-gate.ps1`, by `nested-gate.ps1` and by `imaginary-gate.ps1`.\n"
        )
        failures = check_decision_status("d.md", doc, root)
        assert len(failures) == 1 and "imaginary-gate.ps1" in failures[0].span, failures


def _check_import_name_path_that_exists_resolves() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-language" / "src" / "datrix_language" / "foundation.dtrx"
        target.parent.mkdir(parents=True)
        target.write_text("module datrix.foundation\n", encoding="utf-8")
        doc_text = "Source: `datrix_language/foundation.dtrx`."
        candidates = extract_path_candidates(doc_text)
        assert [span for _, span in candidates] == ["datrix_language/foundation.dtrx"], candidates
        assert resolve_path_candidate(candidates[0][1], root) is True


def _check_import_name_path_that_does_not_exist_stays_unresolved() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        (root / "datrix-language" / "src" / "datrix_language").mkdir(parents=True)
        doc_text = "Source: `datrix_language/stdlib/auth.dtrx`."
        candidates = extract_path_candidates(doc_text)
        assert len(candidates) == 1, f"an import-name path must be a candidate, got {candidates}"
        assert resolve_path_candidate(candidates[0][1], root) is False


def _check_call_suffixed_module_span_is_extracted_and_resolved() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = root / "datrix-common" / "src" / "datrix_common" / "stdlib" / "catalog.py"
        target.parent.mkdir(parents=True)
        target.write_text("def parse_stdlib_modules(): ...\n", encoding="utf-8")
        doc_text = "Call `datrix_common.stdlib.catalog.parse_stdlib_modules()` once."
        candidates = extract_module_candidates(doc_text)
        assert [span for _, span in candidates] == [
            "datrix_common.stdlib.catalog.parse_stdlib_modules"
        ], candidates
        assert resolve_module_candidate(candidates[0][1], root) is True
        missing = extract_module_candidates("Call `datrix_common.stdlib.nope.parse()`.")
        assert len(missing) == 1 and resolve_module_candidate(missing[0][1], root) is False


def _check_reference_doc_is_scanned_without_the_decision_check() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        doc = root / "datrix-language" / "docs" / "ref.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(
            "### Decision 1: No status\n\nSee `datrix_language/stdlib/auth.dtrx`.\n",
            encoding="utf-8",
        )
        rel = ("datrix-language/docs/ref.md",)
        reference = scan_docs(root, rel, architecture_docs=False)
        assert [(r.kind, r.span) for r in reference] == [("path", "datrix_language/stdlib/auth.dtrx")], reference
        architecture = scan_docs(root, rel, architecture_docs=True)
        assert any(r.kind == "decision" for r in architecture), architecture


def _write_manifest(root: Path, package: str, dependencies: list[str]) -> None:
    project = root / package
    project.mkdir(parents=True, exist_ok=True)
    declared = ", ".join(f'"{dependency}"' for dependency in dependencies)
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "{package}"\ndependencies = [{declared}]\n', encoding="utf-8"
    )


def _graph_failure_spans(*edge_lines: str) -> list[str]:
    """The graph check's spans for a doc drawing *edge_lines*, against three fake manifests:
    datrix-language -> datrix-common, datrix-cli -> datrix-common and datrix-cli ->
    datrix-language (written un-normalized, with an extra and a bound)."""
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        _write_manifest(root, "datrix-common", ["pydantic>=2"])
        _write_manifest(root, "datrix-language", ["datrix-common>=0.1.0"])
        _write_manifest(root, "datrix-cli", ["datrix-common", "Datrix_Language[lsp]>=0.1.0"])
        doc = "\n".join(
            ["# Overview", "", _GRAPH_HEADING, "", _MERMAID_FENCE, "graph TD", *edge_lines, "```", "", "## Next"]
        )
        return [f.span for f in check_dependency_graph("o.md", doc, manifest_dependency_edges(root))]


_CORRECT_GRAPH_LINES = (
    " A[datrix-common]",
    " B[datrix-language] --> A",
    " C[datrix-cli] --> B",
    " C --> A",
)


def _check_graph_drawing_exactly_the_manifest_edges_passes() -> None:
    assert _graph_failure_spans(*_CORRECT_GRAPH_LINES) == []
    assert _graph_failure_spans(" A[datrix-common]", " C[datrix-cli] --> B[datrix-language] --> A", " C --> A") == []


def _check_reversed_graph_edge_fails() -> None:
    spans = _graph_failure_spans(" A[datrix-common] --> B[datrix-language]", " C[datrix-cli] --> B", " C --> A")
    assert len(spans) == 2, spans
    assert "datrix-common --> datrix-language is drawn, but" in spans[0], spans
    assert "datrix-language --> datrix-common is declared in datrix-language/pyproject.toml" in spans[1], spans


def _check_missing_graph_edge_fails() -> None:
    spans = _graph_failure_spans(*_CORRECT_GRAPH_LINES[:3])
    assert spans == [
        _GRAPH_SPAN_PREFIX + "datrix-cli --> datrix-common is declared in datrix-cli/pyproject.toml but not drawn"
    ], spans


def _check_unreadable_graph_line_or_missing_graph_fails() -> None:
    spans = _graph_failure_spans(*_CORRECT_GRAPH_LINES, " C -.-> A", " D --> A")
    assert len(spans) == 2, spans
    assert "unreadable mermaid line" in spans[0] and "node D has no [label]" in spans[1], spans
    missing = check_dependency_graph("o.md", "## Dependency Graph\n\nNo block.\n", frozenset())
    assert len(missing) == 1 and "no closed ```mermaid block" in missing[0].span, missing


def _check_numeric_package_count_fails() -> None:
    doc = (
        "The toolchain ships as 17 packages today.\n"
        "Eighteen core packages plus extensions; 19 repos and twenty-one package repos.\n"
        "Split into **nineteen** installable packages (seventeen core toolchain packages).\n"
    )
    failures = check_package_counts("d.md", doc)
    assert [f.span for f in failures] == [
        "package count: The toolchain ships as 17 packages today.",
        "package count: Eighteen core packages plus extensions; 19 repos and",
        "package count: Eighteen core packages plus extensions; 19 repos and twenty-one package repos.",
        "package count: plus extensions; 19 repos and twenty-one package repos.",
        "package count: Split into **nineteen** installable packages (seventeen core toolchain packages).",
        "package count: seventeen core toolchain packages).",
    ], failures
    assert [f.line for f in failures] == [1, 2, 2, 2, 3, 3] and all(f.kind == "count" for f in failures)


def _check_count_of_another_noun_or_in_a_fence_is_not_a_claim() -> None:
    doc = "Two generator packages share a group; each package is one repo.\n```\n17 packages\n```\n"
    assert check_package_counts("d.md", doc) == []


def _tooling_doc(*quality_lines: str) -> str:
    return "\n".join(
        [
            _TOOLING_SECTION_HEADING,
            "",
            "### Code Generation",
            "- **Jinja2** - templates",
            "",
            _TOOLING_SUBSECTION_HEADING,
            *quality_lines,
            "",
            "### CLI",
            "- **Rich** - terminal UI",
            "",
            "## Next",
        ]
    )


_DOCUMENTED_TOOLS = "runs `ruff check` over the tree; pytest runs the suite."


def _check_documented_tools_pass_and_only_code_quality_is_read() -> None:
    doc = _tooling_doc("- **ruff** - lint", "- **pytest** - tests")
    assert check_tooling_claims("o.md", doc, _DOCUMENTED_TOOLS) == []


def _check_undocumented_tool_fails() -> None:
    doc = _tooling_doc("- **ruff** - lint", "- **flake9** - lint", "- **ruf** - a prefix of ruff")
    failures = check_tooling_claims("o.md", doc, _DOCUMENTED_TOOLS)
    assert [f.span.split(" is named")[0] for f in failures] == ["tooling: flake9", "tooling: ruf"], failures
    assert [f.line for f in failures] == [8, 9] and all(f.kind == "tooling" for f in failures), failures


def _check_missing_or_empty_tooling_section_fails() -> None:
    missing = check_tooling_claims("o.md", "## Technology Stack\n\n### CLI\n- **Rich** - UI\n", _DOCUMENTED_TOOLS)
    assert len(missing) == 1 and "no '### Code Quality'" in missing[0].span, missing
    empty = check_tooling_claims("o.md", _tooling_doc("Linting happens."), _DOCUMENTED_TOOLS)
    assert len(empty) == 1 and "names no" in empty[0].span, empty


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = unresolved references found,
        2 = usage error / missing baseline / missing architecture doc).
    """
    # A package-count span quotes prose; a console codepage that cannot encode one of its
    # characters must not abort the report half-way.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = gate_argument_parser("Docs-conformance gate for Datrix architecture documentation")
    parser.add_argument(
        "-w",
        "--warn",
        action="store_true",
        help="Warning mode: report unresolved references but exit 0",
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
        help="Print each doc file being scanned",
    )
    args = parser.parse_args()

    if args.harness_self_test:
        return 0 if harness_self_test() else 1

    report_step("Self-test: I5 docs-conformance gate scanner edge cases")
    self_test_passed = run_checks(_self_test_checks())
    if args.self_test:
        return 0 if self_test_passed else 1
    if not self_test_passed:
        print(
            "\nError: self-test failed -- refusing to trust the scanner for a "
            "real docs scan. Fix the scanner before re-running.",
            file=sys.stderr,
        )
        return 2

    monorepo_root = args.base_dir.resolve() if args.base_dir else _MONOREPO_ROOT

    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return 2

    exceptions_path = (
        monorepo_root / "datrix" / "scripts" / "config" / "docs-conformance-exceptions.json"
    )
    try:
        exceptions = load_exceptions(exceptions_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        scanned = ARCHITECTURE_DOC_FILES + REFERENCE_DOC_FILES
        print(
            f"Scanning {len(ARCHITECTURE_DOC_FILES)} architecture and "
            f"{len(REFERENCE_DOC_FILES)} reference doc files:",
            file=sys.stderr,
        )
        for doc_rel in scanned:
            print(f"  - {doc_rel}", file=sys.stderr)
        print("", file=sys.stderr)

    try:
        unresolved = scan_docs(monorepo_root, ARCHITECTURE_DOC_FILES, architecture_docs=True)
        unresolved.extend(scan_docs(monorepo_root, REFERENCE_DOC_FILES, architecture_docs=False))
        unresolved.extend(check_overview_claims(monorepo_root))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    failures = check_against_exceptions(unresolved, exceptions)

    if failures:
        mode = "Warning" if args.warn else "Error"
        print(
            f"{mode}: {len(failures)} unresolved docs-conformance reference(s) "
            f"(Invariant I5):\n"
        )
        for ref in sorted(failures, key=lambda r: (r.doc, r.line, r.span)):
            print(f"{ref.doc}:{ref.line}: {ref.span}")

        if args.warn:
            return 0
        return 1

    if args.verbose:
        print("No docs-conformance violations found.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
