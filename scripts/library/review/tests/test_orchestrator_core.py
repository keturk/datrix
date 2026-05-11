"""Unit tests for orchestrator core logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review import (
    build_reviewer_prompt,
    dict_to_review_result,
    discover_phase_tasks,
    resolve_task_context,
)
from review_schema import Finding, ReviewResult


def test_resolve_task_context_extracts_design_reference(tmp_path):
    """Test that resolve_task_context parses **Design reference:** line."""
    task_file = tmp_path / "task-43-01-foo.md"
    task_file.write_text(
        "# Task 43-01: Foo\n\n**Design reference:** design.md -- Section(s) 4.2\n\nContent here.",
        encoding="utf-8",
    )

    config = {"paths": {"datrix_root": str(tmp_path)}}

    # Create minimal ai-agent-rules.md
    (tmp_path / "datrix-common/docs/contributing").mkdir(parents=True)
    (tmp_path / "datrix-common/docs/contributing/ai-agent-rules.md").write_text(
        "# AI Agent Rules\n\nRules here.",
        encoding="utf-8",
    )

    context = resolve_task_context(task_file, config)

    assert "task_content" in context
    assert "# Task 43-01: Foo" in context["task_content"]
    assert "agent_rules_subdocs" in context


def test_discover_phase_tasks_finds_all_repos(tmp_path):
    """Test that discover_phase_tasks searches all datrix* repos."""
    config = {"paths": {"datrix_root": str(tmp_path)}}

    # Create tasks in multiple repos
    (tmp_path / "datrix-common/.tasks/phase-43").mkdir(parents=True)
    (tmp_path / "datrix-common/.tasks/phase-43/task-43-01-foo.md").write_text(
        "# Task 43-01"
    )

    (tmp_path / "datrix-codegen-python/.tasks/phase-43").mkdir(parents=True)
    (tmp_path / "datrix-codegen-python/.tasks/phase-43/task-43-02-bar.md").write_text(
        "# Task 43-02"
    )

    tasks = discover_phase_tasks(43, config)

    assert len(tasks) == 2
    assert any("task-43-01" in str(t) for t in tasks)
    assert any("task-43-02" in str(t) for t in tasks)


def test_dict_to_review_result_converts_findings():
    """Test dict to ReviewResult conversion."""
    data = {
        "schema_version": "1.0",
        "source": "local",
        "model": "qwen2.5-coder:14b",
        "scope": "task",
        "target": "task.md",
        "generated_at": "2026-05-10T12:00:00Z",
        "verdict": "needs_fixes",
        "findings": [
            {
                "id": "F-001",
                "severity": "major",
                "category": "anti_pattern",
                "location": "task.md line 10",
                "description": "Uses dict.get",
                "evidence": "x = d.get('key', None)",
                "suggested_fix": "Raise KeyError",
                "rule_reference": None,
            }
        ],
        "summary": "One major issue",
    }

    result = dict_to_review_result(data, Path("task.md"))

    assert result.verdict == "needs_fixes"
    assert len(result.findings) == 1
    assert result.findings[0].id == "F-001"


def test_build_reviewer_prompt_includes_task_and_context(tmp_path):
    """Test that build_reviewer_prompt combines template, task, and context."""
    task_file = tmp_path / "task.md"
    task_file.write_text("# Task 43-01: Foo")

    prompt_template_file = tmp_path / "prompt.md"
    prompt_template_file.write_text("# Reviewer Prompt Template")

    context = {
        "task_content": "# Task 43-01: Foo",
        "design_section": "",
        "agent_rules_subdocs": "# Agent Rules\nRule 1",
    }

    canonical_modules_digest = {
        "datrix-common": ["datrix_common", "datrix_common.utils"],
    }

    prompt = build_reviewer_prompt(
        task_file, context, prompt_template_file, canonical_modules_digest
    )

    assert "# Reviewer Prompt Template" in prompt
    assert "# Task 43-01: Foo" in prompt
    assert "# Canonical Modules" in prompt
    # Prompt structure: task content first, then modules, then template (instructions last)
    task_pos = prompt.index("# Task 43-01: Foo")
    template_pos = prompt.index("# Reviewer Prompt Template")
    assert task_pos < template_pos, "Task content should come before template instructions"
