#!/usr/bin/env python3
r"""Docs-conformance gate for Datrix architecture documentation (design 026, Invariant I5).

Extracts repo-relative path references and Python module references from
every package's **architecture documentation** (the curated 36-file set in
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

This is a v1 scanner with a **deliberate scope boundary**: it only checks
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
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# The curated 36-file architecture-doc set (see module docstring for why this
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
    "datrix-codegen-aws/docs/architecture.md",
    "datrix-codegen-azure/docs/architecture.md",
    "datrix-codegen-common/docs/architecture.md",
    "datrix-codegen-component/docs/architecture.md",
    "datrix-codegen-docker/docs/architecture.md",
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

# The 13 known installable-package directory names (12 toolchain packages +
# the datrix showcase repo itself). This is the closed scope boundary for
# path-reference candidates -- it enumerates installable Datrix packages,
# never target languages/providers. A new datrix-codegen-* package added
# later requires adding one entry here (and to _IMPORT_NAME_TO_PACKAGE_DIR
# below), exactly like check-import-boundaries.py's own package-list
# precedent.
_PACKAGE_DIRS: frozenset[str] = frozenset(
    {
        "datrix",
        "datrix-cli",
        "datrix-codegen-aws",
        "datrix-codegen-azure",
        "datrix-codegen-common",
        "datrix-codegen-component",
        "datrix-codegen-docker",
        "datrix-codegen-python",
        "datrix-codegen-sql",
        "datrix-codegen-typescript",
        "datrix-common",
        "datrix-extensions",
        "datrix-language",
    }
)

# The 12 known Python import names (package directory name -> installed
# import name), excluding the datrix showcase repo (it has no importable
# package). Fixed 12-entry table: the import name maps to its owning
# package directory for module-reference resolution (step 4).
_IMPORT_NAME_TO_PACKAGE_DIR: dict[str, str] = {
    "datrix_cli": "datrix-cli",
    "datrix_codegen_aws": "datrix-codegen-aws",
    "datrix_codegen_azure": "datrix-codegen-azure",
    "datrix_codegen_common": "datrix-codegen-common",
    "datrix_codegen_component": "datrix-codegen-component",
    "datrix_codegen_docker": "datrix-codegen-docker",
    "datrix_codegen_python": "datrix-codegen-python",
    "datrix_codegen_sql": "datrix-codegen-sql",
    "datrix_codegen_typescript": "datrix-codegen-typescript",
    "datrix_common": "datrix-common",
    "datrix_extensions": "datrix-extensions",
    "datrix_language": "datrix-language",
}

# Tier-2 search roots, in the order they are inspected. Deliberately scoped
# to exactly these two subtrees under each package -- never the whole
# package directory (which would also match docs/, .tasks/, etc.).
_TIER2_SEARCH_ROOTS: tuple[str, ...] = ("src", "tests")

_INLINE_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_WINDOWS_ABS_PREFIX_RE = re.compile(r"^[Dd]:[\\/]datrix[\\/]")
_WINDOWS_ABS_STRIP_RE = re.compile(r"^[Dd]:/datrix/")
_LINE_REF_SUFFIX_RE = re.compile(r":\d+(-\d+)?(,\d+(-\d+)?)*$")
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
    with an uppercase letter (a class name, e.g. ``...SeedGeneratorHooks``)
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


def _tier2_resolve(package_name: str, suffix: str, monorepo_root: Path) -> bool:
    """Tier-2 shorthand resolution: does exactly one file/dir under
    ``<package_name>/src/`` or ``<package_name>/tests/`` have a
    root-relative posix path ending with *suffix*?

    Scoped to exactly ``src/`` and ``tests/`` (never the whole package
    directory, which would also match ``docs/``, ``.tasks/``, etc.). Total
    hit count is summed across BOTH roots; zero hits or 2+ hits (ambiguous)
    both resolve to ``False`` -- an ambiguous match is never silently
    guessed.

    Args:
        package_name: Package directory name (e.g. ``datrix-codegen-common``).
        suffix: The candidate's path segments after the package name,
            forward-slash joined, with no leading/trailing slash.
        monorepo_root: Monorepo root directory.

    Returns:
        True iff exactly one file/dir across both search roots ends with
        *suffix*.
    """
    package_dir = monorepo_root / package_name
    match_count = 0
    for root_name in _TIER2_SEARCH_ROOTS:
        root_dir = package_dir / root_name
        if not root_dir.exists():
            continue
        for candidate_path in root_dir.rglob("*"):
            rel = candidate_path.relative_to(root_dir).as_posix()
            if rel.endswith(suffix):
                match_count += 1
    return match_count == 1


def resolve_path_candidate(span: str, monorepo_root: Path) -> bool:
    """Resolve a path-reference candidate (extraction step 3: Tier 1 + Tier 2).

    Normalizes backslashes to forward slashes, strips a ``D:/datrix/`` /
    ``d:/datrix/`` prefix, and strips a trailing line-ref suffix
    (``:148`` or ``:262,282``/``:262-291`` forms). Tier 1 checks the
    normalized path exists verbatim under *monorepo_root* (a trailing-slash
    candidate must resolve as a directory). Tier 2 (only attempted when
    Tier 1 fails AND the segment immediately after the package name is not
    already ``src`` or ``tests``) searches for a unique shorthand match under
    the package's ``src/``/``tests/`` trees.

    Args:
        span: The raw backtick-span text (path-reference candidate).
        monorepo_root: Monorepo root directory.

    Returns:
        True iff the candidate resolves to a real file/directory (Tier 1 or
        an unambiguous Tier 2 match).
    """
    normalized = span.replace("\\", "/")
    normalized = _WINDOWS_ABS_STRIP_RE.sub("", normalized)
    normalized = _LINE_REF_SUFFIX_RE.sub("", normalized)

    is_dir_hint = normalized.endswith("/")
    normalized_stripped = normalized.rstrip("/")

    full_path = monorepo_root / normalized_stripped
    tier1_resolved = full_path.exists() and (full_path.is_dir() if is_dir_hint else True)
    if tier1_resolved:
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
    return _tier2_resolve(package_name, suffix, monorepo_root)


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
    """One backtick span that failed resolution against the live tree."""

    doc: str
    line: int
    span: str
    kind: Literal["path", "module"]


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
        description="Docs-conformance gate for Datrix architecture documentation (design 026, I5)",
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
    args = parser.parse_args()

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
            f"(design 026, Invariant I5):\n"
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
