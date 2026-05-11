"""Unit tests for review schema dataclasses."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_schema import Finding, ReviewResult, finding_to_dict, review_result_to_dict


def test_finding_construction():
    """Test Finding dataclass creation."""
    finding = Finding(
        id="F-001",
        severity="major",
        category="anti_pattern",
        location="task-43-01-foo.md, line 10",
        description="Uses dict.get fallback",
        evidence='value = config.get("key", None)',
        suggested_fix='Raise KeyError if "key" missing',
        rule_reference="ai-agent-rules/prohibited-patterns.md §1",
    )
    assert finding.id == "F-001"
    assert finding.severity == "major"


def test_finding_to_dict():
    """Test Finding serialization."""
    finding = Finding(
        id="F-002",
        severity="blocking",
        category="broken_reference",
        location="task-43-02.md",
        description="References non-existent module",
        evidence="from foo.bar import Baz",
        suggested_fix="Remove or fix import",
        rule_reference=None,
    )
    result = finding_to_dict(finding)
    assert result["id"] == "F-002"
    assert result["rule_reference"] is None


def test_review_result_construction():
    """Test ReviewResult dataclass creation."""
    review = ReviewResult(
        schema_version="1.0",
        source="local",
        model="qwen2.5-coder:14b",
        scope="task",
        target="task-43-01-foo.md",
        generated_at=datetime.now(timezone.utc).isoformat(),
        verdict="pass",
        findings=[],
        summary="All checks passed.",
    )
    assert review.verdict == "pass"
    assert len(review.findings) == 0


def test_review_result_to_dict():
    """Test ReviewResult serialization."""
    finding = Finding(
        id="F-003",
        severity="minor",
        category="ambiguity",
        location="task.md",
        description="Vague requirement",
        evidence="Handle errors appropriately",
        suggested_fix="Specify error handling strategy",
        rule_reference=None,
    )
    review = ReviewResult(
        schema_version="1.0",
        source="local",
        model="deepseek-r1:32b",
        scope="task",
        target="task.md",
        generated_at="2026-05-10T12:00:00Z",
        verdict="warnings_only",
        findings=[finding],
        summary="One minor issue found.",
    )
    result = review_result_to_dict(review)
    assert result["verdict"] == "warnings_only"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["id"] == "F-003"
