"""The formatter's corpus walk, run over each ``.dtrx`` text the move would place in the corpus.

The formatter's corpus test reads every ``.dtrx`` under the corpus on its own, and requires it to format
losslessly and idempotently. A template, a partial source or a deliberately broken text does not, so a group
holding one stays with the tests that read it. The text is checked without its path: every reference it makes
is proven separately, and the walk's verdict on a text that parses does not rest on what it includes.
"""

from __future__ import annotations

from collections.abc import Sequence

from datrix_common.errors.base import DatrixError
from datrix_language.formatting.formatter import FormatOptions, format_dtrx_source
from datrix_language.formatting.verification import verify_lossless
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
from datrix_testing.cases.inputs import without_cursor_markers

from datrix_scripts.dev.fixture_dedupe.secret_screen import PlacedText


def _refusal(content: bytes, parser: TreeSitterParser) -> str | None:
    """Why the walk fails on *content*, or ``None`` when it passes. The error's text is not repeated: it may
    quote the document."""
    options = FormatOptions()
    try:
        source = without_cursor_markers(content.decode("utf-8"))
        formatted = format_dtrx_source(source, options, parser)
        verify_lossless(source, formatted, parser)
        if format_dtrx_source(formatted, options, parser) != formatted:
            return "a second format changes it"
    except (DatrixError, UnicodeDecodeError) as exc:
        return type(exc).__name__
    return None


def format_findings(placed: Sequence[PlacedText]) -> dict[str, list[str]]:
    """What the formatter's corpus walk refuses among *placed*, by group key."""
    findings: dict[str, list[str]] = {}
    if not placed:
        return findings
    parser = TreeSitterParser()
    for text in placed:
        refusal = _refusal(text.content, parser)
        if refusal is not None:
            findings.setdefault(text.key, []).append(f"{text.relative.as_posix()} (the formatter's walk refuses it: {refusal})")
    return findings
