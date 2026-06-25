"""Cross-repo namespace-literal grep gate.

Invariant: the frozen identity-namespace UUID literal
``c9a255a1-350b-4414-beb9-7f06f7dfd92d`` must appear in exactly ONE
production-source location in the repository: ``datrix-common`` (in
``datrix_common.identity.provider_plan``).

Neither ``datrix-codegen-python`` nor ``datrix-codegen-typescript`` may declare
this literal.  A stray literal in a codegen package means a future divergence is
possible — a developer might update one and not the other, silently re-keying
users on one language target.

The single-source guarantee is enforced here by:

1. Asserting **zero** occurrences of the literal anywhere under the Python and
   TypeScript codegen package ``src`` trees (both ``.py`` files and ``.j2``
   template files).
2. Asserting **exactly one** occurrence under the ``datrix-common`` ``src``
   tree — the ``DATRIX_IDENTITY_NAMESPACE`` constant definition.

Both codegen generators read the namespace at runtime from the plan JSON
(``localIdentity.namespace``); they must not re-declare it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo layout constants
# ---------------------------------------------------------------------------

#: Absolute path to the repository root (two levels up from this test file).
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent.parent

#: Source root for datrix-codegen-python (Python files + Jinja2 templates).
CODEGEN_PY_SRC: Path = _REPO_ROOT / "datrix-codegen-python" / "src"

#: Source root for datrix-codegen-typescript (Python files + Jinja2 templates).
CODEGEN_TS_SRC: Path = _REPO_ROOT / "datrix-codegen-typescript" / "src"

#: Source root for datrix-common — the ONLY permitted home of the literal.
DATRIX_COMMON_SRC: Path = _REPO_ROOT / "datrix-common" / "src"

#: The frozen identity-namespace UUID literal that must appear exactly once,
#: only in datrix-common.
NAMESPACE_LITERAL: str = "c9a255a1-350b-4414-beb9-7f06f7dfd92d"

#: File extensions to scan (Python source and Jinja2 templates).
_SCANNED_EXTENSIONS: frozenset[str] = frozenset({".py", ".j2"})


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _grep_literal(root: Path, literal: str) -> list[str]:
    """Return all file paths (relative to ``root``) containing ``literal``.

    Scans ``.py`` and ``.j2`` files recursively under ``root``.  Returns
    a sorted list of relative paths so the assertion message is stable across
    platforms.

    Args:
        root: Directory to scan.
        literal: Exact string to search for (no regex).

    Returns:
        Sorted list of file paths (relative to ``root``) that contain
        ``literal``.
    """
    hits: list[str] = []
    if not root.is_dir():
        return hits
    pattern = re.compile(re.escape(literal))
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in _SCANNED_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pattern.search(text):
            hits.append(str(path.relative_to(root)))
    return hits


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_stray_namespace_literal_in_codegen_python() -> None:
    """The frozen namespace literal must not appear anywhere under datrix-codegen-python src.

    The Python codegen reads the namespace from the plan at runtime
    (``localIdentity["namespace"]``).  A literal in the codegen package would
    create a second definition that could drift from the single source of truth
    in datrix-common.
    """
    hits = _grep_literal(CODEGEN_PY_SRC, NAMESPACE_LITERAL)
    assert hits == [], (
        "Stray identity-namespace literal '%s' found in datrix-codegen-python/src.\n"
        "The namespace must be defined ONLY in datrix-common "
        "(datrix_common.identity.provider_plan.DATRIX_IDENTITY_NAMESPACE) and read "
        "from the plan at runtime — never redeclared in a codegen package.\n"
        "Remove the literal from:\n%s"
        % (NAMESPACE_LITERAL, "\n".join("  " + h for h in hits))
    )


@pytest.mark.unit
def test_no_stray_namespace_literal_in_codegen_typescript() -> None:
    """The frozen namespace literal must not appear anywhere under datrix-codegen-typescript src.

    The TypeScript codegen reads the namespace from the plan at runtime
    (``providerEntry.localIdentity.namespace``).  A literal in the codegen
    package would create a second definition that could drift from the single
    source of truth in datrix-common.
    """
    hits = _grep_literal(CODEGEN_TS_SRC, NAMESPACE_LITERAL)
    assert hits == [], (
        "Stray identity-namespace literal '%s' found in datrix-codegen-typescript/src.\n"
        "The namespace must be defined ONLY in datrix-common "
        "(datrix_common.identity.provider_plan.DATRIX_IDENTITY_NAMESPACE) and read "
        "from the plan at runtime — never redeclared in a codegen package.\n"
        "Remove the literal from:\n%s"
        % (NAMESPACE_LITERAL, "\n".join("  " + h for h in hits))
    )


@pytest.mark.unit
def test_namespace_literal_appears_exactly_once_in_datrix_common() -> None:
    """The frozen namespace literal must appear exactly once under datrix-common src.

    The ONLY permitted definition is in
    ``datrix_common.identity.provider_plan.DATRIX_IDENTITY_NAMESPACE``.
    If this count drops to zero the constant was removed; if it rises above one
    a duplicate definition was introduced.  Either is a defect in the single-
    source-of-truth invariant.
    """
    hits = _grep_literal(DATRIX_COMMON_SRC, NAMESPACE_LITERAL)
    assert len(hits) == 1, (
        "Expected exactly 1 occurrence of the frozen namespace literal '%s' "
        "under datrix-common/src, but found %d.\n"
        "The only permitted definition is "
        "datrix_common.identity.provider_plan.DATRIX_IDENTITY_NAMESPACE.\n"
        "Found in:\n%s"
        % (
            NAMESPACE_LITERAL,
            len(hits),
            "\n".join("  " + h for h in hits) if hits else "  (none)",
        )
    )
