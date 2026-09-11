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

Beyond path and module spans, two claim families are checked whose rot no
path check can see. **Anchor links** (``[text](<doc>.md#anchor)`` and
``[text](#anchor)``) must name a heading that exists in the target doc, by
the GitHub-flavoured slug the heading produces -- a heading gaining a status
suffix silently breaks every link to it. **Decision status**: every
``### Decision N:`` heading carries a status from a closed vocabulary; a
``**Status:**`` paragraph, when present, agrees with the heading; an
in-progress decision must carry one (it is the checklist of what remains);
and every ``*.ps1`` gate a decision section names exists under
``datrix/scripts/test`` or ``datrix/scripts/dev``.

For path and module spans this is a v1 scanner with a **deliberate scope
boundary**: it only checks
path-reference candidates that are **fully package-qualified** (start with
one of the 13 known package directory names, or a ``D:\datrix\`` /
``d:/datrix/`` absolute prefix) and module-reference candidates that are
**fully import-qualified** (start with one of the 12 known Python import
names). A bare, package-relative shorthand span with no package/import
anchor at all (e.g. a doc writing `` `gendsl/_naming.py` `` instead of the
fully-qualified `` `datrix-codegen-common/gendsl/_naming.py` `` or `` `src/`
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

import argparse
import ast
import json
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
    "datrix-codegen-dotnet/docs/architecture.md",
    "datrix-codegen-python/docs/architecture.md",
    "datrix-codegen-sql/docs/architecture.md",
    "datrix-codegen-typescript/docs/architecture.md",
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
    "datrix-common/docs/architecture/semantic-validators.md",
    "datrix-language/docs/architecture.md",
    "datrix-language/docs/architecture/model-metaprogramming.md",
    "datrix-language/docs/architecture/parser-design.md",
    "datrix-language/docs/architecture/parser-overview.md",
    "datrix-language/docs/architecture/semantic-design.md",
)

# The monorepo root, resolved the same way auto_detect_base_dir() resolves it
# (this script lives at datrix/scripts/test/, i.e. three levels below the root).
# Needed at module scope so the package tables below can be discovered from disk.
_MONOREPO_ROOT: Path = Path(__file__).resolve().parents[3]


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
        child.name
        for child in monorepo_root.iterdir()
        if child.is_dir() and (child.name == "datrix" or child.name.startswith("datrix-"))
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
    prefix OR its first ``/``-or-``\\``-separated segment is one of the 13
    known package directory names -- UNLESS it contains an elision marker
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
        if first_segment in _PACKAGE_DIRS:
            candidates.append((line_number, span))
    return candidates


def extract_module_candidates(doc_text: str) -> list[tuple[int, str]]:
    """Extract module-reference candidates from *doc_text* (extraction step 1).

    A backtick span is a module-reference candidate iff, after trimming
    whitespace, it matches a dotted lowercase identifier chain
    (``^[a-z][a-z0-9_]*(\\.[a-z_][a-zA-Z0-9_]*)+$``) whose first segment is
    one of the 12 known Python import names. A trailing segment that starts
    with an uppercase letter (a class name, e.g. ``...DefaultCacheHooks``)
    fails this regex and is deliberately excluded -- this v1 only resolves
    module/function/attribute paths, not class-qualified symbol chains.

    Args:
        doc_text: Full text of one architecture doc file.

    Returns:
        List of (1-based line number, span text) tuples for every
        module-reference candidate found, in document order.
    """
    candidates: list[tuple[int, str]] = []
    for line_number, span in _iter_backtick_spans(doc_text):
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
    only" scoping check-import-boundaries.py's shared-vocabulary scanner
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
    (e.g. ``datrix_common.generation.type_resolver._dispatch`` resolves via
    the 2-segment prefix ``generation/type_resolver.py``).

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
    Markdown anchor link whose target heading does not exist, or a decision
    whose heading status, status paragraph, and named checks disagree.
    """

    doc: str
    line: int
    span: str
    kind: Literal["path", "module", "anchor", "decision"]


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
_SCRIPT_DIRS: tuple[str, ...] = ("datrix/scripts/test", "datrix/scripts/dev")


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
            if not any((monorepo_root / directory / script).is_file() for directory in _SCRIPT_DIRS):
                fail(section.line, f"{label}: names `{script}`, which exists under none of {_SCRIPT_DIRS}")
    return failures


def scan_docs(
    monorepo_root: Path, doc_files: tuple[str, ...]
) -> list[UnresolvedReference]:
    """Scan every doc in *doc_files* for unresolved path/module references.

    Args:
        monorepo_root: Monorepo root directory.
        doc_files: Repo-relative paths of architecture docs to scan (the
            curated ``ARCHITECTURE_DOC_FILES`` constant in normal use).

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
    for doc_rel in doc_files:
        doc_path = monorepo_root / doc_rel
        if not doc_path.exists():
            raise FileNotFoundError(
                f"Architecture doc {doc_rel} (listed in ARCHITECTURE_DOC_FILES) "
                f"no longer exists at {doc_path}. Update the ARCHITECTURE_DOC_FILES "
                f"constant in check-docs-conformance.py to match the current tree."
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
        unresolved.extend(check_decision_status(doc_rel, doc_text, monorepo_root))

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
# pattern established by test-specific-selection-gate.py.
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


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
    doc_text = "See `datrix_common.generation.type_resolver` for details."
    candidates = extract_module_candidates(doc_text)
    assert len(candidates) == 1, f"expected 1 candidate, got {candidates}"
    assert candidates[0][1] == "datrix_common.generation.type_resolver"


def _check_generic_dotted_identifier_without_known_import_name_is_excluded() -> None:
    doc_text = "Set `service.name` to the desired value."
    candidates = extract_module_candidates(doc_text)
    assert candidates == [], f"unknown import-name-first segment must be excluded, got {candidates}"


def _check_trailing_class_name_segment_is_excluded_from_extraction() -> None:
    doc_text = "See `datrix_codegen_common.orchestration.hooks.cache_hooks.DefaultCacheHooks`."
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
        target = (
            root / "datrix-common" / "src" / "datrix_common" / "generation" / "type_resolver.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("class TypeResolver: ...\n", encoding="utf-8")
        resolved = resolve_module_candidate("datrix_common.generation.type_resolver", root)
        assert resolved is True, "exact module path must resolve"


def _check_trailing_symbol_name_is_tolerated() -> None:
    with tempfile.TemporaryDirectory(prefix="docs-conformance-selftest-") as tmp:
        root = Path(tmp)
        target = (
            root / "datrix-common" / "src" / "datrix_common" / "generation" / "type_resolver.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("def _dispatch(): ...\n", encoding="utf-8")
        resolved = resolve_module_candidate(
            "datrix_common.generation.type_resolver._dispatch", root
        )
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


def _self_test_checks() -> list[tuple[str, Callable[[], None]]]:
    """Every named self-test check, resolved at call time so a check may be
    defined anywhere in this module."""
    return [
    ("windows_absolute_span_is_a_candidate", _check_windows_absolute_span_is_a_candidate),
    ("package_prefixed_span_is_a_candidate", _check_package_prefixed_span_is_a_candidate),
    ("bare_span_with_no_package_prefix_is_excluded", _check_bare_span_with_no_package_prefix_is_excluded),
    ("ellipsis_elided_span_is_rejected", _check_ellipsis_elided_span_is_rejected),
    ("placeholder_span_is_rejected", _check_placeholder_span_is_rejected),
    ("glob_span_is_rejected", _check_glob_span_is_rejected),
    (
        "line_ref_suffix_is_captured_verbatim_by_extraction",
        _check_line_ref_suffix_is_captured_verbatim_by_extraction,
    ),
    ("line_number_is_tracked_per_span", _check_line_number_is_tracked_per_span),
    ("fully_qualified_module_span_is_a_candidate", _check_fully_qualified_module_span_is_a_candidate),
    (
        "generic_dotted_identifier_without_known_import_name_is_excluded",
        _check_generic_dotted_identifier_without_known_import_name_is_excluded,
    ),
    (
        "trailing_class_name_segment_is_excluded_from_extraction",
        _check_trailing_class_name_segment_is_excluded_from_extraction,
    ),
    ("tier1_literal_match_resolves", _check_tier1_literal_match_resolves),
    (
        "tier1_directory_hint_requires_a_real_directory",
        _check_tier1_directory_hint_requires_a_real_directory,
    ),
    ("genuinely_missing_path_stays_unresolved", _check_genuinely_missing_path_stays_unresolved),
    (
        "line_ref_suffix_is_stripped_before_resolution",
        _check_line_ref_suffix_is_stripped_before_resolution,
    ),
    ("tier2_src_shorthand_match_resolves", _check_tier2_src_shorthand_match_resolves),
    (
        "tier2_tests_shorthand_match_resolves_with_two_segment_omission",
        _check_tier2_tests_shorthand_match_resolves_with_two_segment_omission,
    ),
    (
        "tier2_is_skipped_when_next_segment_is_already_tests",
        _check_tier2_is_skipped_when_next_segment_is_already_tests,
    ),
    ("ambiguous_tier2_match_stays_unresolved", _check_ambiguous_tier2_match_stays_unresolved),
    (
        "leading_underscore_path_symbol_resolves",
        _check_leading_underscore_path_symbol_resolves,
    ),
    (
        "path_symbol_suffix_naming_nonexistent_symbol_stays_unresolved",
        _check_path_symbol_suffix_naming_nonexistent_symbol_stays_unresolved,
    ),
    ("exact_module_match_resolves", _check_exact_module_match_resolves),
    ("trailing_symbol_name_is_tolerated", _check_trailing_symbol_name_is_tolerated),
    ("package_init_module_resolves", _check_package_init_module_resolves),
    (
        "genuinely_missing_module_stays_unresolved",
        _check_genuinely_missing_module_stays_unresolved,
    ),
    ("unknown_import_name_stays_unresolved", _check_unknown_import_name_stays_unresolved),
    (
        "span_present_in_baseline_is_removed_from_failures",
        _check_span_present_in_baseline_is_removed_from_failures,
    ),
    (
        "span_absent_from_baseline_remains_a_failure",
        _check_span_absent_from_baseline_remains_a_failure,
    ),
    (
        "load_exceptions_reads_span_to_reason_mapping",
        _check_load_exceptions_reads_span_to_reason_mapping,
    ),
    ("load_exceptions_raises_when_file_missing", _check_load_exceptions_raises_when_file_missing),
    (
        "heading_slug_matches_github_for_punctuated_headings",
        _check_heading_slug_matches_github_for_punctuated_headings,
    ),
    ("duplicate_headings_get_numbered_slugs", _check_duplicate_headings_get_numbered_slugs),
    (
        "explicit_heading_id_is_an_anchor_and_text_slug_excludes_it",
        _check_explicit_heading_id_is_an_anchor_and_text_slug_excludes_it,
    ),
    (
        "anchor_link_to_existing_heading_resolves_across_docs",
        _check_anchor_link_to_existing_heading_resolves_across_docs,
    ),
    ("anchor_link_to_missing_heading_or_doc_fails", _check_anchor_link_to_missing_heading_or_doc_fails),
    ("decision_heading_without_status_fails", _check_decision_heading_without_status_fails),
    (
        "adopted_decision_without_status_paragraph_is_accepted",
        _check_adopted_decision_without_status_paragraph_is_accepted,
    ),
    (
        "in_progress_decision_requires_status_paragraph",
        _check_in_progress_decision_requires_status_paragraph,
    ),
    (
        "heading_and_status_paragraph_disagreement_fails",
        _check_heading_and_status_paragraph_disagreement_fails,
    ),
    ("landed_status_paragraph_counts_as_adopted", _check_landed_status_paragraph_counts_as_adopted),
    ("named_gate_script_must_exist_on_disk", _check_named_gate_script_must_exist_on_disk),
    ]


def _check_heading_slug_matches_github_for_punctuated_headings() -> None:
    cases = {
        "Decision 14: Runtime Configuration & Secrets — Zero-Environment Architecture": (
            "decision-14-runtime-configuration--secrets--zero-environment-architecture"
        ),
        "Decision 2: `datrix-codegen-*` Naming": "decision-2-datrix-codegen--naming",
        "Decision 25: .NET / ASP.NET Core Language Generator (Adopted)": (
            "decision-25-net--aspnet-core-language-generator-adopted"
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
        doc = (
            "### Decision 9: Store (Adopted)\n\n"
            "Held by `real-gate.ps1` and by `imaginary-gate.ps1`.\n"
        )
        failures = check_decision_status("d.md", doc, root)
        assert len(failures) == 1 and "imaginary-gate.ps1" in failures[0].span, failures


def _dummy_intentionally_failing_check() -> None:
    """Registered ONLY under --harness-self-test. Always fails on purpose --
    this is the proof that run_self_test_checks() actually detects and
    reports a failing check, rather than vacuously swallowing every
    AssertionError and reporting green regardless of what the checks do."""
    assert False, "intentional harness self-test failure (expected -- proves non-vacuity)"  # noqa: B011


def run_self_test_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check.

    Args:
        checks: Named zero-argument callables; each raises AssertionError on
            failure and returns normally on success.

    Returns:
        True iff every check passed.
    """
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except AssertionError as e:
            _fail(f"{name}: {e}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


def auto_detect_base_dir(script_path: Path) -> Path:
    """Auto-detect monorepo root by walking up from script location.

    Args:
        script_path: Path to this script (``datrix/scripts/test/check-docs-conformance.py``).

    Returns:
        Monorepo root directory.

    Raises:
        FileNotFoundError: If monorepo root cannot be found.
    """
    current = script_path.resolve().parent
    for _ in range(3):
        current = current.parent

    if (current / "datrix-common").exists():
        return current

    raise FileNotFoundError(
        f"Could not auto-detect monorepo root from {script_path}. "
        f"Use --base-dir to specify manually."
    )


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = unresolved references found,
        2 = usage error / missing baseline / missing architecture doc).
    """
    parser = argparse.ArgumentParser(
        description="Docs-conformance gate for Datrix architecture documentation (I5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run only the self-test suite (plain-Python edge-case checks on "
            "this scanner's own functions) and exit -- skips the real docs "
            "scan. The same checks also run automatically, unconditionally, "
            "as step 1 of every normal invocation."
        ),
    )
    parser.add_argument(
        "--harness-self-test",
        action="store_true",
        help=(
            "Demonstration mode: run one intentionally-failing dummy check "
            "through the self-test harness and report the result. Always "
            "reports [FAIL] and exits 1 -- this is the proof that the "
            "harness's pass/fail detection is not vacuous."
        ),
    )
    args = parser.parse_args()

    if args.harness_self_test:
        _step("Harness self-test: intentionally-failing dummy check (must report FAIL, exit 1)")
        harness_ok = run_self_test_checks(
            [("dummy_intentionally_failing_check", _dummy_intentionally_failing_check)]
        )
        return 0 if harness_ok else 1

    _step("Self-test: I5 docs-conformance gate scanner edge cases")
    self_test_passed = run_self_test_checks(_self_test_checks())
    if args.self_test:
        return 0 if self_test_passed else 1
    if not self_test_passed:
        print(
            "\nError: self-test failed -- refusing to trust the scanner for a "
            "real docs scan. Fix the scanner before re-running.",
            file=sys.stderr,
        )
        return 2

    if args.base_dir:
        monorepo_root = args.base_dir.resolve()
    else:
        try:
            monorepo_root = auto_detect_base_dir(Path(__file__))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

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
        print(f"Scanning {len(ARCHITECTURE_DOC_FILES)} architecture doc files:", file=sys.stderr)
        for doc_rel in ARCHITECTURE_DOC_FILES:
            print(f"  - {doc_rel}", file=sys.stderr)
        print("", file=sys.stderr)

    try:
        unresolved = scan_docs(monorepo_root, ARCHITECTURE_DOC_FILES)
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
