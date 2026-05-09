"""Unit tests for the docs lint script (check_docs.py).

Tests each lint check function with real temporary files using the tmp_path
fixture. Covers both positive (drift detected) and negative (clean docs) cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── sys.path setup for script imports ──
_library_dir = Path(__file__).resolve().parent.parent / "library"
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

# check_docs.py replaces sys.stdout/stderr with TextIOWrapper on Windows
# at import time (guarded by sys.platform == "win32"), which breaks pytest's
# capture mechanism. Temporarily override sys.platform to skip that block.
_real_platform = sys.platform
sys.platform = "linux"  # skip the Windows UTF-8 wrapper during import

from dev.check_docs import (  # noqa: E402
    LintResult,
    check_capability_status_labels,
    check_cdx_filenames,
    check_cdx_structure,
    check_deprecated_cli_flags,
    check_fixed_phase_count,
)

sys.platform = _real_platform


# ── Helpers ──


def _write_md(directory: Path, filename: str, content: str) -> Path:
    """Write a markdown file into the given directory and return its path."""
    file_path = directory / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


def _run_check_deprecated_flags(docs_dir: Path) -> LintResult:
    """Run the deprecated CLI flags check and return the result."""
    result = LintResult()
    check_deprecated_cli_flags([docs_dir], result)
    return result


def _run_check_fixed_phase_count(docs_dir: Path) -> LintResult:
    """Run the fixed phase count check and return the result."""
    result = LintResult()
    check_fixed_phase_count([docs_dir], result)
    return result


def _run_check_cdx_filenames(design_dir: Path) -> LintResult:
    """Run the CDX filename check and return the result."""
    result = LintResult()
    check_cdx_filenames(design_dir, result)
    return result


def _run_check_cdx_structure(design_dir: Path) -> LintResult:
    """Run the CDX structure check and return the result."""
    result = LintResult()
    check_cdx_structure(design_dir, result)
    return result


def _run_check_capability_labels(docs_dir: Path) -> LintResult:
    """Run the capability status labels check and return the result."""
    result = LintResult()
    check_capability_status_labels([docs_dir], result)
    return result


# ── Deprecated CLI flag check ──


class TestDeprecatedCliFlags:
    """Tests for check_deprecated_cli_flags."""

    @pytest.mark.unit
    def test_lowercase_p_in_generate_example_is_flagged(
        self, tmp_path: Path
    ) -> None:
        """A '-p' flag in a 'datrix generate' example line is flagged."""
        _write_md(
            tmp_path,
            "example.md",
            "```\ndatrix generate -p my-project\n```\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert result.has_failures, "Expected -p in generate example to be flagged"
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "deprecated-cli-flag"
        assert "-p" in result.findings[0].suggestion

    @pytest.mark.unit
    def test_lowercase_l_in_generate_example_is_flagged(
        self, tmp_path: Path
    ) -> None:
        """A '-l' flag in a 'datrix generate' example line is flagged."""
        _write_md(
            tmp_path,
            "example.md",
            "```\ndatrix generate -l python\n```\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert result.has_failures, "Expected -l in generate example to be flagged"
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "deprecated-cli-flag"
        assert "-l" in result.findings[0].suggestion

    @pytest.mark.unit
    def test_valid_uppercase_flags_are_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """Valid uppercase flags -L and -P in CLI examples are NOT flagged."""
        _write_md(
            tmp_path,
            "example.md",
            "```\ndatrix generate -L python -P my-project\n```\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert not result.has_failures, (
            f"Uppercase -L and -P should not be flagged, got: "
            f"{[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_lowercase_p_in_prose_not_flagged(self, tmp_path: Path) -> None:
        """A '-p' in prose text (not a CLI context) is NOT flagged."""
        _write_md(
            tmp_path,
            "readme.md",
            "Use the option -p to specify a path in your terminal.\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert not result.has_failures, (
            f"Prose usage of -p should not be flagged, got: "
            f"{[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_lowercase_p_in_non_datrix_command_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """A '-p' in a non-datrix command context is NOT flagged."""
        _write_md(
            tmp_path,
            "other.md",
            "Run `ls -p /tmp` to list directories.\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert not result.has_failures, (
            f"Non-datrix usage of -p should not be flagged, got: "
            f"{[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_no_findings_on_clean_docs(self, tmp_path: Path) -> None:
        """A doc with no deprecated flags produces no findings."""
        _write_md(
            tmp_path,
            "clean.md",
            "# Getting Started\n\nRun `datrix generate -L python`.\n",
        )
        result = _run_check_deprecated_flags(tmp_path)
        assert not result.has_failures


# ── Fixed phase count check ──


class TestFixedPhaseCount:
    """Tests for check_fixed_phase_count."""

    @pytest.mark.unit
    def test_digit_phase_count_is_flagged(self, tmp_path: Path) -> None:
        """A '6-phase' digit reference is flagged."""
        _write_md(
            tmp_path,
            "arch.md",
            "The pipeline has a 6-phase execution model.\n",
        )
        result = _run_check_fixed_phase_count(tmp_path)
        assert result.has_failures, "Expected '6-phase' to be flagged"
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "fixed-phase-count"
        assert "6" in result.findings[0].suggestion

    @pytest.mark.unit
    def test_other_digit_phase_count_is_flagged(self, tmp_path: Path) -> None:
        """A '7-phase' digit reference is also flagged."""
        _write_md(
            tmp_path,
            "arch.md",
            "The 7-phase pipeline runs sequentially.\n",
        )
        result = _run_check_fixed_phase_count(tmp_path)
        assert result.has_failures, "Expected '7-phase' to be flagged"
        assert len(result.findings) == 1

    @pytest.mark.unit
    def test_spelled_out_phase_count_not_matched(
        self, tmp_path: Path
    ) -> None:
        """Spelled-out phase counts like 'six-phase' are not matched by the
        digit-only pattern, so they are NOT flagged."""
        _write_md(
            tmp_path,
            "arch.md",
            "The six-phase pipeline runs sequentially.\n",
        )
        result = _run_check_fixed_phase_count(tmp_path)
        assert not result.has_failures, (
            "Spelled-out 'six-phase' does not match the digit pattern"
        )

    @pytest.mark.unit
    def test_delivery_phase_reference_not_flagged(
        self, tmp_path: Path
    ) -> None:
        """Delivery phase references like 'Phase 01' are NOT flagged
        because they do not match the N-phase pattern."""
        _write_md(
            tmp_path,
            "delivery.md",
            "Phase 01 covers foundation work.\n",
        )
        result = _run_check_fixed_phase_count(tmp_path)
        assert not result.has_failures, (
            "Delivery phase 'Phase 01' should not be flagged"
        )

    @pytest.mark.unit
    def test_no_findings_on_clean_docs(self, tmp_path: Path) -> None:
        """A doc without phase count references produces no findings."""
        _write_md(
            tmp_path,
            "clean.md",
            "# Architecture\n\nThe pipeline processes .dtrx files.\n",
        )
        result = _run_check_fixed_phase_count(tmp_path)
        assert not result.has_failures


# ── CDX filename validation ──


class TestCdxFilenames:
    """Tests for check_cdx_filenames."""

    @pytest.mark.unit
    def test_valid_cdx_filename_passes(self, tmp_path: Path) -> None:
        """A valid CDX filename like CDX-04-docs-pipeline.md passes."""
        _write_md(tmp_path, "CDX-04-docs-pipeline.md", "# CDX-04\n")
        result = _run_check_cdx_filenames(tmp_path)
        assert not result.has_failures, (
            "Valid CDX filename should pass"
        )

    @pytest.mark.unit
    def test_invalid_cdx_filename_without_dash_fails(
        self, tmp_path: Path
    ) -> None:
        """A CDX filename missing the dash (CDX04-docs.md) is flagged."""
        _write_md(tmp_path, "CDX04-docs.md", "# CDX04\n")
        result = _run_check_cdx_filenames(tmp_path)
        assert result.has_failures, "Expected CDX04-docs.md to be flagged"
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "cdx-filename"

    @pytest.mark.unit
    def test_non_cdx_files_are_ignored(self, tmp_path: Path) -> None:
        """Files not starting with 'CDX' are completely ignored."""
        _write_md(tmp_path, "README.md", "# Readme\n")
        _write_md(tmp_path, "design-notes.md", "# Notes\n")
        result = _run_check_cdx_filenames(tmp_path)
        assert not result.has_failures

    @pytest.mark.unit
    def test_valid_cdx_with_multi_segment_slug(
        self, tmp_path: Path
    ) -> None:
        """A CDX filename with a multi-segment slug passes."""
        _write_md(tmp_path, "CDX-12-multi-segment-slug.md", "# CDX-12\n")
        result = _run_check_cdx_filenames(tmp_path)
        assert not result.has_failures

    @pytest.mark.unit
    def test_cdx_with_uppercase_slug_fails(self, tmp_path: Path) -> None:
        """A CDX filename with uppercase letters in the slug is flagged."""
        _write_md(tmp_path, "CDX-01-BadSlug.md", "# CDX-01\n")
        result = _run_check_cdx_filenames(tmp_path)
        assert result.has_failures, "Expected uppercase slug to be flagged"

    @pytest.mark.unit
    def test_nonexistent_design_dir_produces_no_findings(
        self, tmp_path: Path
    ) -> None:
        """A nonexistent design directory produces no findings (logs warning)."""
        result = _run_check_cdx_filenames(tmp_path / "nonexistent")
        assert not result.has_failures


# ── CDX structure validation ──


class TestCdxStructure:
    """Tests for check_cdx_structure."""

    @pytest.mark.unit
    def test_doc_with_all_required_sections_passes(
        self, tmp_path: Path
    ) -> None:
        """A CDX doc with all required sections passes validation."""
        content = (
            "# CDX-04: Docs Sync\n"
            "\n"
            "Status: Draft\n"
            "\n"
            "## Summary\n"
            "\n"
            "Summary content.\n"
            "\n"
            "## Goals\n"
            "\n"
            "Goals content.\n"
            "\n"
            "## Implementation\n"
            "\n"
            "Implementation content.\n"
            "\n"
            "## Verification\n"
            "\n"
            "Verification content.\n"
        )
        _write_md(tmp_path, "CDX-04-docs-sync.md", content)
        result = _run_check_cdx_structure(tmp_path)
        assert not result.has_failures, (
            f"All required sections present, should pass. "
            f"Findings: {[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_doc_missing_verification_section_fails(
        self, tmp_path: Path
    ) -> None:
        """A CDX doc missing the 'Verification' section is flagged."""
        content = (
            "# CDX-04: Docs Sync\n"
            "\n"
            "Status: Draft\n"
            "\n"
            "## Summary\n"
            "\n"
            "Summary content.\n"
            "\n"
            "## Goals\n"
            "\n"
            "Goals content.\n"
            "\n"
            "## Implementation\n"
            "\n"
            "Implementation content.\n"
        )
        _write_md(tmp_path, "CDX-04-docs-sync.md", content)
        result = _run_check_cdx_structure(tmp_path)
        assert result.has_failures, "Expected missing Verification to be flagged"
        missing_sections = [f.content for f in result.findings]
        found_verification = any("Verification" in s for s in missing_sections)
        assert found_verification, (
            f"Expected 'Verification' in findings, got: {missing_sections}"
        )

    @pytest.mark.unit
    def test_doc_missing_status_line_fails(self, tmp_path: Path) -> None:
        """A CDX doc missing the 'Status:' line is flagged."""
        content = (
            "# CDX-04: Docs Sync\n"
            "\n"
            "## Summary\n"
            "\n"
            "Summary content.\n"
            "\n"
            "## Goals\n"
            "\n"
            "Goals content.\n"
            "\n"
            "## Implementation\n"
            "\n"
            "Implementation content.\n"
            "\n"
            "## Verification\n"
            "\n"
            "Verification content.\n"
        )
        _write_md(tmp_path, "CDX-04-docs-sync.md", content)
        result = _run_check_cdx_structure(tmp_path)
        assert result.has_failures, "Expected missing Status line to be flagged"
        missing_sections = [f.content for f in result.findings]
        found_status = any("Status" in s for s in missing_sections)
        assert found_status, (
            f"Expected 'Status' in findings, got: {missing_sections}"
        )

    @pytest.mark.unit
    def test_doc_with_status_as_header_passes(self, tmp_path: Path) -> None:
        """A CDX doc with '## Status' as a section header also passes."""
        content = (
            "# CDX-04: Docs Sync\n"
            "\n"
            "## Status\n"
            "\n"
            "Draft\n"
            "\n"
            "## Summary\n"
            "\n"
            "Summary content.\n"
            "\n"
            "## Goals\n"
            "\n"
            "Goals content.\n"
            "\n"
            "## Implementation\n"
            "\n"
            "Implementation content.\n"
            "\n"
            "## Verification\n"
            "\n"
            "Verification content.\n"
        )
        _write_md(tmp_path, "CDX-04-docs-sync.md", content)
        result = _run_check_cdx_structure(tmp_path)
        assert not result.has_failures, (
            f"Status as section header should pass. "
            f"Findings: {[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_implementation_options_variant_passes(
        self, tmp_path: Path
    ) -> None:
        """'## Implementation Options' satisfies the Implementation requirement."""
        content = (
            "# CDX-04: Docs Sync\n"
            "\n"
            "Status: Draft\n"
            "\n"
            "## Summary\n"
            "\n"
            "Summary content.\n"
            "\n"
            "## Goals\n"
            "\n"
            "Goals content.\n"
            "\n"
            "## Implementation Options\n"
            "\n"
            "Options content.\n"
            "\n"
            "## Verification\n"
            "\n"
            "Verification content.\n"
        )
        _write_md(tmp_path, "CDX-04-docs-sync.md", content)
        result = _run_check_cdx_structure(tmp_path)
        assert not result.has_failures, (
            f"'Implementation Options' should satisfy Implementation requirement. "
            f"Findings: {[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_non_cdx_files_in_design_dir_ignored(
        self, tmp_path: Path
    ) -> None:
        """Non-CDX files in the design directory are ignored."""
        _write_md(tmp_path, "README.md", "# Design Directory\n")
        result = _run_check_cdx_structure(tmp_path)
        assert not result.has_failures


# ── Capability status label check ──


class TestCapabilityStatusLabels:
    """Tests for check_capability_status_labels."""

    @pytest.mark.unit
    def test_section_with_inline_stable_label_passes(
        self, tmp_path: Path
    ) -> None:
        """A ### section with '(Stable)' in the title passes."""
        content = (
            "# Pipeline and Capabilities\n"
            "\n"
            "## Capabilities\n"
            "\n"
            "### Search Engine (Stable)\n"
            "\n"
            "Provides full-text search.\n"
        )
        _write_md(tmp_path, "pipeline-and-capabilities.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert not result.has_failures, (
            f"Section with (Stable) label should pass. "
            f"Findings: {[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_section_with_body_status_label_passes(
        self, tmp_path: Path
    ) -> None:
        """A ### section with 'Status: Beta' in the body passes."""
        content = (
            "# Pipeline and Capabilities\n"
            "\n"
            "## Capabilities\n"
            "\n"
            "### Search Engine\n"
            "\n"
            "Status: Beta\n"
            "\n"
            "Provides full-text search.\n"
        )
        _write_md(tmp_path, "pipeline-and-capabilities.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert not result.has_failures, (
            f"Section with Status: Beta in body should pass. "
            f"Findings: {[f.content for f in result.findings]}"
        )

    @pytest.mark.unit
    def test_section_without_label_is_flagged(self, tmp_path: Path) -> None:
        """A ### section without any status label is flagged."""
        content = (
            "# Pipeline and Capabilities\n"
            "\n"
            "## Capabilities\n"
            "\n"
            "### Search Engine\n"
            "\n"
            "Provides full-text search.\n"
        )
        _write_md(tmp_path, "pipeline-and-capabilities.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert result.has_failures, "Expected missing status label to be flagged"
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "capability-status-label"

    @pytest.mark.unit
    def test_non_capabilities_file_is_ignored(self, tmp_path: Path) -> None:
        """Files not named 'pipeline-and-capabilities.md' are ignored."""
        content = (
            "# Some Other Doc\n"
            "\n"
            "### Some Section\n"
            "\n"
            "No status label needed.\n"
        )
        _write_md(tmp_path, "other-doc.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert not result.has_failures

    @pytest.mark.unit
    def test_multiple_sections_mixed_labels(self, tmp_path: Path) -> None:
        """When multiple ### sections exist, only those without labels are flagged."""
        content = (
            "# Pipeline and Capabilities\n"
            "\n"
            "## Capabilities\n"
            "\n"
            "### Search Engine (Stable)\n"
            "\n"
            "Has a label.\n"
            "\n"
            "### Cache Layer\n"
            "\n"
            "Missing a label.\n"
            "\n"
            "### Messaging (Experimental)\n"
            "\n"
            "Has a label.\n"
        )
        _write_md(tmp_path, "pipeline-and-capabilities.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert result.has_failures, "Expected Cache Layer to be flagged"
        assert len(result.findings) == 1
        assert "Cache Layer" in result.findings[0].content

    @pytest.mark.unit
    def test_all_valid_labels_accepted(self, tmp_path: Path) -> None:
        """All valid status labels are accepted in titles."""
        labels = ["Stable", "Beta", "Experimental", "Planned", "Illustrative", "Deprecated"]
        sections = "\n\n".join(
            f"### Feature {i} ({label})\n\nDescription."
            for i, label in enumerate(labels)
        )
        content = f"# Pipeline and Capabilities\n\n## Capabilities\n\n{sections}\n"
        _write_md(tmp_path, "pipeline-and-capabilities.md", content)
        result = _run_check_capability_labels(tmp_path)
        assert not result.has_failures, (
            f"All valid labels should pass. "
            f"Findings: {[f.content for f in result.findings]}"
        )


# ── LintResult data class ──


class TestLintResult:
    """Tests for the LintResult data class behavior."""

    @pytest.mark.unit
    def test_empty_result_has_no_failures(self) -> None:
        """A fresh LintResult has no failures."""
        result = LintResult()
        assert not result.has_failures
        assert len(result.findings) == 0

    @pytest.mark.unit
    def test_add_creates_finding(self) -> None:
        """Adding a finding increments the count and sets has_failures."""
        result = LintResult()
        result.add(
            check_name="test-check",
            file_path=Path("test.md"),
            line_number=1,
            content="test content",
            suggestion="fix it",
        )
        assert result.has_failures
        assert len(result.findings) == 1
        assert result.findings[0].check_name == "test-check"
        assert result.findings[0].line_number == 1
