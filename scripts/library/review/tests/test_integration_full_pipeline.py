"""Integration test for full Tier 1 review pipeline."""

import pytest
import json
import subprocess
import sys
from pathlib import Path

# This test requires Ollama running
pytestmark = pytest.mark.integration


@pytest.fixture
def temp_phase_dir(tmp_path):
    """Create temporary phase directory with test tasks."""
    phase_dir = tmp_path / "datrix" / ".tasks" / "phase-99"
    phase_dir.mkdir(parents=True)

    # Create a known-bad task (missing ## Targeted Tests section)
    bad_task = phase_dir / "task-99-01-bad.md"
    bad_task.write_text(
        """
> **Peruse 'd:\\datrix\\datrix-common\\docs\\contributing\\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task 99-01: Bad Task Example

## Overview

This task is missing the ## Targeted Tests section.

**Package:** `datrix` (`d:\\datrix\\datrix\\`)
**Design reference:** Test design -- Section 1
**Depends on:** None

## Files to Create

### 1. `test_file.py` -- Test file

```python
def foo():
    pass  # Placeholder code (anti-pattern)
```

## Success Criteria

1. Tests pass
2. Code works
""".strip(),
        encoding="utf-8",
    )

    # Create a known-good task
    good_task = phase_dir / "task-99-02-good.md"
    good_task.write_text(
        """
> **Peruse 'd:\\datrix\\datrix-common\\docs\\contributing\\ai-agent-rules.md' (and its sub-documents) and follow the rules**

# Task 99-02: Good Task Example

## Overview

This task follows all template rules.

**Package:** `datrix` (`d:\\datrix\\datrix\\`)
**Design reference:** Test design -- Section 2
**Depends on:** None

## Files to Create

### 1. `test_file.py` -- Test file

```python
def foo() -> int:
    return 42
```

## Targeted Tests

**Package:** `datrix`
**Test command:**
```
python -m pytest tests/test_file.py
```

## Success Criteria

1. Tests pass
2. Type hints present
""".strip(),
        encoding="utf-8",
    )

    # Create a temporary config.toml
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""[tier1]
endpoint = "http://10.94.0.100:11434"
primary_model = "qwen2.5-coder:14b"
fallback_model = "deepseek-r1:32b"
context_window = 32768
fallback_after_failures = 2
target_latency_seconds = 30

[tier2]
enabled = false

[paths]
datrix_root = "{str(tmp_path).replace('\\', '\\\\')}"
review_artifacts = "{str(tmp_path / '.review').replace('\\', '\\\\')}"
canonical_modules_cache = "{str(tmp_path / '.review' / '.canonical-modules-cache.json').replace('\\', '\\\\')}"
""",
        encoding="utf-8",
    )

    return tmp_path


def check_ollama_available() -> bool:
    """Check if Ollama is reachable."""
    import urllib.request

    try:
        req = urllib.request.Request("http://10.94.0.100:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.skipif(not check_ollama_available(), reason="Ollama not reachable")
def test_full_tier1_pipeline(temp_phase_dir, capsys) -> None:
    """Test full Tier 1 pipeline: review → findings → apply → verify → cleared."""
    # Step 1: Run review on phase 99
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "review.py"),
            "--phase",
            "99",
            "--config",
            str(temp_phase_dir / "config.toml"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Verify review ran
    assert result.returncode in (
        0,
        1,
    ), f"Review failed: {result.stderr}"

    # Step 2: Verify review artifacts created
    bad_task_review = (
        temp_phase_dir
        / "datrix"
        / ".tasks"
        / "phase-99"
        / "task-99-01-bad.review.local.json"
    )
    good_task_review = (
        temp_phase_dir
        / "datrix"
        / ".tasks"
        / "phase-99"
        / "task-99-02-good.review.local.json"
    )

    assert bad_task_review.exists(), "Bad task review artifact missing"
    assert good_task_review.exists(), "Good task review artifact missing"

    # Step 3: Verify bad task has findings
    with bad_task_review.open("r", encoding="utf-8") as f:
        bad_review = json.load(f)

    assert bad_review["verdict"] in (
        "needs_fixes",
        "warnings_only",
    ), "Bad task should have findings"
    assert len(bad_review["findings"]) > 0, "Bad task should have at least one finding"

    # Check that findings have categories (specific category depends on model)
    finding_categories = [f["category"] for f in bad_review["findings"]]
    assert len(finding_categories) > 0, "Findings should have categories"

    # Step 4: Verify good task passes
    with good_task_review.open("r", encoding="utf-8") as f:
        good_review = json.load(f)

    assert good_review["verdict"] in (
        "pass",
        "warnings_only",
    ), f"Good task should pass, got {good_review['verdict']}"

    # Step 5: Simulate fix application (create .review.applied.json marker)
    applied_marker = (
        temp_phase_dir
        / "datrix"
        / ".tasks"
        / "phase-99"
        / "task-99-01-bad.review.applied.json"
    )
    applied_marker.write_text(
        json.dumps(
            {
                "applied_at": "2026-05-10T12:00:00Z",
                "applied_findings": [f["id"] for f in bad_review["findings"]],
                "skipped_findings": [],
                "skipped_reason": {},
            }
        ),
        encoding="utf-8",
    )

    # Step 6: Re-run review with --verify flag
    verify_result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "review.py"),
            "--phase",
            "99",
            "--verify",
            "--config",
            str(temp_phase_dir / "config.toml"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Verify verification ran
    assert verify_result.returncode == 0, f"Verification failed: {verify_result.stderr}"

    # Step 7: Verify .review.local.verified.json created
    verified_artifact = (
        temp_phase_dir
        / "datrix"
        / ".tasks"
        / "phase-99"
        / "task-99-01-bad.review.local.verified.json"
    )
    assert verified_artifact.exists(), "Verified review artifact missing"

    print("✓ Full Tier 1 pipeline test passed")
    print(f"  - Reviewed 2 tasks (1 bad, 1 good)")
    print(f"  - Bad task findings: {len(bad_review['findings'])}")
    print(f"  - Good task verdict: {good_review['verdict']}")
    print(f"  - Applied fixes and verified")


def test_review_json_schema_compliance(temp_phase_dir) -> None:
    """Test that review JSON output conforms to schema."""
    # Run review
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "review.py"),
            "--phase",
            "99",
            "--config",
            str(temp_phase_dir / "config.toml"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Load review artifact
    review_file = (
        temp_phase_dir
        / "datrix"
        / ".tasks"
        / "phase-99"
        / "task-99-01-bad.review.local.json"
    )
    if not review_file.exists():
        pytest.skip("Review artifact not created (Ollama may be unreachable)")

    with review_file.open("r", encoding="utf-8") as f:
        review = json.load(f)

    # Verify schema compliance
    required_fields = [
        "schema_version",
        "source",
        "model",
        "scope",
        "target",
        "generated_at",
        "verdict",
        "findings",
        "summary",
    ]
    for field in required_fields:
        assert field in review, f"Missing required field: {field}"

    assert review["schema_version"] == "1.0"
    assert review["source"] in ("local", "codex")
    assert review["scope"] in ("task", "phase")
    assert review["verdict"] in ("pass", "warnings_only", "needs_fixes", "blocking")

    # Verify findings structure
    for finding in review["findings"]:
        assert "id" in finding
        assert "severity" in finding
        assert finding["severity"] in ("blocking", "major", "minor", "nit")
        assert "category" in finding
        assert "location" in finding
        assert "description" in finding
        assert "evidence" in finding
        assert "suggested_fix" in finding

    print("✓ Review JSON schema compliance verified")
