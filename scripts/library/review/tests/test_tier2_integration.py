"""Unit tests for Tier 2 Codex integration."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tier2_codex import invoke_tier2_codex, dict_to_review_result


def test_invoke_tier2_prepares_context_files(tmp_path, monkeypatch):
    """Test that invoke_tier2_codex writes context files."""
    config = {
        "paths": {"review_artifacts": str(tmp_path / ".review")},
        "tier2": {"codex_command": "codex", "skill_name": "review-tasks"},
    }

    phase_tasks = [tmp_path / "task-43-01.md", tmp_path / "task-43-02.md"]
    for task in phase_tasks:
        task.write_text("# Task content", encoding="utf-8")

    tier1_artifacts = [tmp_path / "task-43-01.review.local.json"]
    tier1_artifacts[0].write_text('{"verdict": "pass"}', encoding="utf-8")

    canonical_modules = {"datrix-common": ["datrix_common.utils"]}

    # Mock subprocess.run to avoid actual Codex invocation
    def mock_run(*args, **kwargs):
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""

        # Write stub Codex output
        output_path = (
            Path(config["paths"]["review_artifacts"])
            / "phase-43.review.codex.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source": "codex",
                    "model": "gpt-5.x-codex",
                    "scope": "phase",
                    "target": "phase-43",
                    "generated_at": "2026-05-10T12:00:00Z",
                    "verdict": "pass",
                    "findings": [],
                    "summary": "No issues",
                }
            ),
            encoding="utf-8",
        )
        return MockResult()

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = invoke_tier2_codex(
        43, phase_tasks, tier1_artifacts, canonical_modules, config
    )

    assert result is not None
    assert result.verdict == "pass"
    assert result.source == "codex"
    assert result.scope == "phase"

    # Verify context files were created
    context_dir = (
        Path(config["paths"]["review_artifacts"]) / "phase-43-context"
    )
    assert (context_dir / "tasks.txt").exists()
    assert (context_dir / "tier1-artifacts.txt").exists()
    assert (context_dir / "canonical-modules.json").exists()

    # Verify tasks.txt content
    tasks_content = (context_dir / "tasks.txt").read_text(encoding="utf-8")
    assert "task-43-01.md" in tasks_content
    assert "task-43-02.md" in tasks_content


def test_dict_to_review_result():
    """Test conversion from JSON dict to ReviewResult."""
    data = {
        "schema_version": "1.0",
        "source": "codex",
        "model": "gpt-5.0-codex",
        "scope": "phase",
        "target": "phase-43",
        "generated_at": "2026-05-10T12:00:00Z",
        "verdict": "needs_fixes",
        "findings": [
            {
                "id": "C-001",
                "severity": "major",
                "category": "test_coverage",
                "location": "phase-43",
                "description": "Missing quality gate",
                "evidence": "8 code tasks, no quality gate",
                "suggested_fix": "Add quality gate task",
                "rule_reference": None,
            }
        ],
        "summary": "1 issue found",
    }

    result = dict_to_review_result(data, Path("phase-43"))

    assert result.verdict == "needs_fixes"
    assert result.source == "codex"
    assert result.scope == "phase"
    assert len(result.findings) == 1
    assert result.findings[0].id == "C-001"
    assert result.findings[0].severity == "major"


def test_invoke_tier2_handles_rate_limit(tmp_path, monkeypatch, capsys):
    """Test that invoke_tier2_codex handles rate limit gracefully."""
    config = {
        "paths": {"review_artifacts": str(tmp_path / ".review")},
        "tier2": {"codex_command": "codex", "skill_name": "review-tasks"},
    }

    phase_tasks = [tmp_path / "task-43-01.md"]
    phase_tasks[0].write_text("# Task content", encoding="utf-8")

    tier1_artifacts = []
    canonical_modules = {}

    # Mock subprocess.run to simulate rate limit
    def mock_run(*args, **kwargs):
        class MockResult:
            returncode = 1
            stdout = ""
            stderr = "Error: rate limit exceeded"

        return MockResult()

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = invoke_tier2_codex(
        43, phase_tasks, tier1_artifacts, canonical_modules, config
    )

    assert result is None

    # Verify error message was printed
    captured = capsys.readouterr()
    assert "rate limit" in captured.out.lower()


def test_invoke_tier2_handles_codex_not_found(tmp_path, monkeypatch, capsys):
    """Test that invoke_tier2_codex handles Codex CLI not found."""
    config = {
        "paths": {"review_artifacts": str(tmp_path / ".review")},
        "tier2": {"codex_command": "nonexistent-codex", "skill_name": "review-tasks"},
    }

    phase_tasks = [tmp_path / "task-43-01.md"]
    phase_tasks[0].write_text("# Task content", encoding="utf-8")

    tier1_artifacts = []
    canonical_modules = {}

    # Mock subprocess.run to raise FileNotFoundError
    def mock_run(*args, **kwargs):
        raise FileNotFoundError()

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = invoke_tier2_codex(
        43, phase_tasks, tier1_artifacts, canonical_modules, config
    )

    assert result is None

    # Verify error message was printed
    captured = capsys.readouterr()
    assert "Codex CLI not found" in captured.out
