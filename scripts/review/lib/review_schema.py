"""Review JSON schema as typed dataclasses.

This module defines the contract between Tier 1 (a local model, per task), Tier 2 (a local
model, per phase) and Tier 3 (Apply Reviews skill). All reviewers emit JSON conforming to this schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Finding:
    """A single review finding."""

    id: str  # e.g., "F-001"
    severity: Literal["blocking", "major", "minor", "nit"]
    category: Literal[
        "anti_pattern",
        "missing_section",
        "broken_reference",
        "dependency_error",
        "test_coverage",
        "doc_coverage",
        "ambiguity",
        "scope",
        "other",
    ]
    location: str  # e.g., "task-05-03-foo.md, Files to Create §2"
    description: str  # Concrete description in reviewer's words
    evidence: str  # Quoted line(s) from task file or referenced doc
    suggested_fix: str  # What Claude Code should change
    rule_reference: str | None  # e.g., "ai-agent-rules/prohibited-patterns.md §3"


@dataclass(frozen=True)
class ReviewResult:
    """Complete review result from a single reviewer (Tier 1 or Tier 2)."""

    schema_version: str  # "1.0"
    source: Literal["local", "phase"]  # Tier 1 (one task) or Tier 2 (the phase)
    model: str  # e.g., "qwen3-coder:30b-ctx32k", "nemotron-3-super:120b"
    scope: Literal["task", "phase"]
    target: str  # file path or "phase-NN"
    generated_at: str  # ISO-8601 timestamp
    verdict: Literal["pass", "warnings_only", "needs_fixes", "blocking"]
    findings: list[Finding]
    summary: str  # One-paragraph summary for human reviewers


def finding_to_dict(finding: Finding) -> dict[str, str | None]:
    """Convert Finding to JSON-serializable dict."""
    return {
        "id": finding.id,
        "severity": finding.severity,
        "category": finding.category,
        "location": finding.location,
        "description": finding.description,
        "evidence": finding.evidence,
        "suggested_fix": finding.suggested_fix,
        "rule_reference": finding.rule_reference,
    }


def review_result_to_dict(result: ReviewResult) -> dict:
    """Convert ReviewResult to JSON-serializable dict."""
    return {
        "schema_version": result.schema_version,
        "source": result.source,
        "model": result.model,
        "scope": result.scope,
        "target": result.target,
        "generated_at": result.generated_at,
        "verdict": result.verdict,
        "findings": [finding_to_dict(f) for f in result.findings],
        "summary": result.summary,
    }
