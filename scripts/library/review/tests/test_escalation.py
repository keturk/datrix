"""Unit tests for escalation logic."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from escalation import should_escalate_to_tier2
from review_schema import ReviewResult, Finding


def make_result(verdict: str) -> ReviewResult:
    """Helper to create ReviewResult with given verdict."""
    return ReviewResult(
        schema_version="1.0",
        source="local",
        model="qwen2.5-coder:14b",
        scope="task",
        target="task.md",
        generated_at="2026-05-10T12:00:00Z",
        verdict=verdict,
        findings=[],
        summary="Test result",
    )


def test_escalate_manual_override():
    """Test manual override always escalates."""
    config = {"tier2": {"enabled": True, "mode": "off"}}
    results = [make_result("pass")]

    assert should_escalate_to_tier2(results, config, manual_override=True)


def test_escalate_mode_off():
    """Test off mode never escalates."""
    config = {"tier2": {"enabled": True, "mode": "off"}}
    results = [make_result("blocking")]

    assert not should_escalate_to_tier2(results, config)


def test_escalate_threshold_blocking():
    """Test threshold mode escalates on blocking finding."""
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 1,
            "threshold_total_major": 5,
        }
    }
    results = [make_result("blocking")]

    assert should_escalate_to_tier2(results, config)


def test_escalate_threshold_major():
    """Test threshold mode escalates when major+blocking >= threshold."""
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 10,  # Won't trigger
            "threshold_total_major": 3,
        }
    }
    results = [
        make_result("needs_fixes"),  # major
        make_result("needs_fixes"),  # major
        make_result("needs_fixes"),  # major
    ]

    assert should_escalate_to_tier2(results, config)


def test_no_escalate_threshold_below():
    """Test threshold mode doesn't escalate when below threshold."""
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 1,
            "threshold_total_major": 5,
        }
    }
    results = [make_result("warnings_only"), make_result("pass")]

    assert not should_escalate_to_tier2(results, config)


def test_escalate_phase_gate():
    """Test phase-gate mode always escalates."""
    config = {"tier2": {"enabled": True, "mode": "phase-gate"}}
    results = [make_result("pass")]

    assert should_escalate_to_tier2(results, config)


def test_tier2_disabled():
    """Test Tier 2 disabled never escalates."""
    config = {"tier2": {"enabled": False, "mode": "manual"}}
    results = [make_result("blocking")]

    assert not should_escalate_to_tier2(results, config, manual_override=True)


def test_escalate_mode_manual_without_override():
    """Test manual mode without override doesn't escalate."""
    config = {"tier2": {"enabled": True, "mode": "manual"}}
    results = [make_result("blocking")]

    assert not should_escalate_to_tier2(results, config, manual_override=False)


def test_escalate_unknown_mode():
    """Test unknown mode doesn't escalate."""
    config = {"tier2": {"enabled": True, "mode": "unknown"}}
    results = [make_result("blocking")]

    assert not should_escalate_to_tier2(results, config)


def test_escalate_threshold_mixed_verdicts():
    """Test threshold with mixed verdicts counts correctly."""
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 2,
            "threshold_total_major": 3,
        }
    }
    results = [
        make_result("blocking"),  # counts as 1 blocking, 1 major
        make_result("needs_fixes"),  # counts as 0 blocking, 1 major
        make_result("pass"),  # counts as 0 blocking, 0 major
        make_result("warnings_only"),  # counts as 0 blocking, 0 major
    ]

    # blocking_count = 1 (< 2), major_count = 2 (< 3), should NOT escalate
    assert not should_escalate_to_tier2(results, config)

    # Add one more blocking to trigger
    results.append(make_result("blocking"))
    # blocking_count = 2 (>= 2), should escalate
    assert should_escalate_to_tier2(results, config)
