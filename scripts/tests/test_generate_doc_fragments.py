"""Tests for generate_doc_fragments script.

Tests verify:
- Phase extraction from Python source via AST parsing
- Human-readable label generation from function names
- Fragment markdown generation with auto-generated markers
- Check mode detects stale fragments
- CLI help fragment wrapping in markdown code blocks
- Error handling for missing class/method in source
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dev.generate_doc_fragments import (
    _build_cli_help_fragment,
    _build_semantic_fragment,
    _check_fragment,
    _extract_phase_names,
    _function_name_to_label,
    ANALYZER_RELATIVE_PATH,
)
from shared.venv import get_datrix_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_ANALYZER_SOURCE = '''\
class SemanticAnalyzer:
    """Minimal analyzer for testing."""

    def analyze(self, app: "Application") -> "AnalysisResult":
        """Run analysis."""
        diagnostics: list = []

        self.collect_symbols(app, diagnostics)
        self.resolve_references(app, diagnostics)
        self.check_types(app, diagnostics)

        return AnalysisResult(app=app, diagnostics=diagnostics)
'''

EMPTY_CLASS_SOURCE = '''\
class SemanticAnalyzer:
    """Empty analyzer."""

    def not_analyze(self, app: "Application") -> None:
        """Wrong method name."""
        pass
'''

NO_CLASS_SOURCE = '''\
def standalone_function() -> None:
    """No class at all."""
    pass
'''


# ---------------------------------------------------------------------------
# Semantic pipeline extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractPhaseNames:
    """Test phase extraction from Python source strings."""

    def test_extracts_three_phases_from_minimal_source(self) -> None:
        """Minimal source with 3 function calls extracts all 3 in order."""
        phases = _extract_phase_names(MINIMAL_ANALYZER_SOURCE)
        assert len(phases) == 3, (
            f"Expected 3 phases from minimal source, got {len(phases)}: {phases}"
        )
        assert phases == ["collect_symbols", "resolve_references", "check_types"]

    def test_extracts_phases_from_real_analyzer(self) -> None:
        """Real analyzer.py produces exactly 13 phases."""
        datrix_root = get_datrix_root()
        analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
        source = analyzer_path.read_text(encoding="utf-8")
        phases = _extract_phase_names(source)
        assert len(phases) == 13, (
            f"Expected 13 phases from real analyzer, got {len(phases)}: {phases}"
        )

    def test_phase_names_are_snake_case_strings(self) -> None:
        """Extracted phase names are non-empty snake_case strings."""
        datrix_root = get_datrix_root()
        analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
        source = analyzer_path.read_text(encoding="utf-8")
        phases = _extract_phase_names(source)
        for phase in phases:
            assert isinstance(phase, str), f"Phase should be str, got {type(phase)}"
            assert len(phase) > 0, "Phase name must not be empty"
            assert phase == phase.lower(), (
                f"Phase name should be lowercase, got: {phase}"
            )

    def test_raises_when_class_not_found(self) -> None:
        """ValueError raised when SemanticAnalyzer class is missing."""
        with pytest.raises(ValueError, match="SemanticAnalyzer"):
            _extract_phase_names(NO_CLASS_SOURCE)

    def test_raises_when_analyze_method_not_found(self) -> None:
        """ValueError raised when analyze method is missing."""
        with pytest.raises(ValueError, match="analyze"):
            _extract_phase_names(EMPTY_CLASS_SOURCE)

    def test_raises_on_empty_source(self) -> None:
        """ValueError raised when source has no SemanticAnalyzer class."""
        with pytest.raises(ValueError, match="SemanticAnalyzer"):
            _extract_phase_names("")


@pytest.mark.unit
class TestFunctionNameToLabel:
    """Test human-readable label generation from function names."""

    def test_converts_underscores_to_spaces(self) -> None:
        """Underscores become spaces."""
        result = _function_name_to_label("resolve_field_types")
        assert result == "Resolve field types"

    def test_capitalizes_first_letter(self) -> None:
        """First letter is capitalized."""
        result = _function_name_to_label("check_types")
        assert result == "Check types"

    def test_single_word(self) -> None:
        """Single word is capitalized."""
        result = _function_name_to_label("validate")
        assert result == "Validate"

    def test_labels_from_real_analyzer_are_readable(self) -> None:
        """Labels derived from real analyzer phases are title-cased and readable."""
        datrix_root = get_datrix_root()
        analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
        source = analyzer_path.read_text(encoding="utf-8")
        phases = _extract_phase_names(source)
        for phase in phases:
            label = _function_name_to_label(phase)
            assert "_" not in label, (
                f"Label should not contain underscores: {label}"
            )
            assert label[0].isupper(), (
                f"Label should start with uppercase: {label}"
            )


# ---------------------------------------------------------------------------
# Fragment generation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildSemanticFragment:
    """Test semantic pipeline markdown fragment generation."""

    def test_fragment_has_auto_generated_markers(self) -> None:
        """Fragment starts with AUTO-GENERATED marker and ends with END marker."""
        phases = ["collect_symbols", "resolve_references", "check_types"]
        fragment = _build_semantic_fragment(phases)
        assert "<!-- AUTO-GENERATED" in fragment, (
            "Fragment must contain AUTO-GENERATED marker"
        )
        assert "<!-- END AUTO-GENERATED -->" in fragment, (
            "Fragment must contain END AUTO-GENERATED marker"
        )

    def test_fragment_includes_phase_count(self) -> None:
        """Fragment text includes the correct phase count."""
        phases = ["collect_symbols", "resolve_references", "check_types"]
        fragment = _build_semantic_fragment(phases)
        assert "3 phases" in fragment, (
            f"Fragment should mention '3 phases', got:\n{fragment}"
        )

    def test_fragment_lists_all_phases_in_order(self) -> None:
        """Fragment includes numbered list of all phases."""
        phases = ["collect_symbols", "resolve_references", "check_types"]
        fragment = _build_semantic_fragment(phases)
        assert "1. Collect symbols" in fragment
        assert "2. Resolve references" in fragment
        assert "3. Check types" in fragment

    def test_fragment_with_real_phases(self) -> None:
        """Fragment from real analyzer has correct count in text."""
        datrix_root = get_datrix_root()
        analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
        source = analyzer_path.read_text(encoding="utf-8")
        phases = _extract_phase_names(source)
        fragment = _build_semantic_fragment(phases)
        assert f"{len(phases)} phases" in fragment


# ---------------------------------------------------------------------------
# Check mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckFragment:
    """Test check mode for detecting stale fragments."""

    def test_check_detects_stale_fragment(self, tmp_path: Path) -> None:
        """Check returns False when file content does not match expected."""
        output_path = tmp_path / "stale.md"
        output_path.write_text("old content\n", encoding="utf-8")
        result = _check_fragment(
            output_path,
            expected_content="new content\n",
            fragment_name="test-fragment",
            verbose=False,
        )
        assert result is False, "Stale fragment should return False"

    def test_check_returns_true_when_up_to_date(self, tmp_path: Path) -> None:
        """Check returns True when file content matches expected."""
        content = "matching content\n"
        output_path = tmp_path / "current.md"
        output_path.write_text(content, encoding="utf-8")
        result = _check_fragment(
            output_path,
            expected_content=content,
            fragment_name="test-fragment",
            verbose=False,
        )
        assert result is True, "Up-to-date fragment should return True"

    def test_check_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        """Check returns False when the fragment file does not exist."""
        output_path = tmp_path / "nonexistent.md"
        result = _check_fragment(
            output_path,
            expected_content="anything\n",
            fragment_name="test-fragment",
            verbose=False,
        )
        assert result is False, "Missing fragment file should return False"


# ---------------------------------------------------------------------------
# CLI help fragment
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildCliHelpFragment:
    """Test CLI help markdown fragment generation."""

    def test_output_wrapped_in_code_block(self) -> None:
        """CLI help output is wrapped in a markdown code block."""
        help_text = "Usage: datrix generate [OPTIONS]\n\nOptions:\n  --help"
        fragment = _build_cli_help_fragment(help_text)
        assert "```text" in fragment, "Fragment must contain opening code fence"
        assert fragment.rstrip().endswith("```\n<!-- END AUTO-GENERATED -->"), (
            f"Fragment must end with closing code fence before END marker, "
            f"got:\n{fragment[-100:]}"
        )

    def test_fragment_has_auto_generated_markers(self) -> None:
        """CLI help fragment has AUTO-GENERATED markers."""
        help_text = "Usage: datrix generate [OPTIONS]"
        fragment = _build_cli_help_fragment(help_text)
        assert "<!-- AUTO-GENERATED" in fragment
        assert "<!-- END AUTO-GENERATED -->" in fragment

    def test_fragment_preserves_help_content(self) -> None:
        """CLI help text is included verbatim in the fragment."""
        help_text = "Usage: datrix generate [OPTIONS]\n\n  --source  Path\n  --language  python"
        fragment = _build_cli_help_fragment(help_text)
        assert help_text in fragment, (
            "Help text should appear verbatim inside the fragment"
        )


@pytest.mark.unit
class TestCliHelpCapture:
    """Test CLI help capture from the real venv environment."""

    def test_cli_help_contains_expected_flags(self) -> None:
        """Captured CLI help output contains --source, --language, --hosting flags."""
        # Import here to avoid polluting other tests if this fails
        from dev.generate_doc_fragments import _capture_cli_help

        datrix_root = get_datrix_root()
        help_text = _capture_cli_help(datrix_root)
        expected_flags = ["--source", "--language", "--hosting"]
        for flag in expected_flags:
            assert flag in help_text, (
                f"CLI help should contain '{flag}', got:\n{help_text[:500]}"
            )

    def test_cli_help_fragment_is_markdown_code_block(self) -> None:
        """Full CLI help fragment is properly wrapped in a markdown code block."""
        from dev.generate_doc_fragments import _capture_cli_help

        datrix_root = get_datrix_root()
        help_text = _capture_cli_help(datrix_root)
        fragment = _build_cli_help_fragment(help_text)
        assert "```text" in fragment
        assert "```" in fragment.split("```text", maxsplit=1)[1], (
            "Code block must have a closing fence"
        )
