"""Repo-level gate for the review library, behind ``review/review-library-gate.ps1`` (and its ``.sh`` twin).

Named ``_check_*`` functions cover each part of ``datrix_scripts.review``:

  - ``review_schema`` (Finding, ReviewResult, serializers)
  - ``canonical_modules`` (package discovery, module scanning, digest building, cache validity,
    prompt formatting)
  - ``escalation`` (should_escalate_to_tier2)
  - ``review_reply`` (extract_json_from_response, parse_model_response, dict_to_review_result)
  - ``review`` (resolve_task_context, discover_phase_tasks, build_reviewer_prompt, a phase-gate run
    against a model server on loopback)
  - ``tier2_local`` (the phase artifact, splitting a phase too large for the context window)

A repo-level validation script, not a pytest suite (the datrix showcase repo hosts none): plain
``assert`` checks run by the shared gate harness, which prints [OK]/[FAIL] per check and the
gate's verdict line; real ``tempfile.TemporaryDirectory()`` fixtures for every filesystem case, and
nothing contacts the network's model servers.

Exit codes: 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import (
    WRAPPER_DEBUG_FLAG,
    CheckFunc,
    NamedCheck,
    check_list_main,
    check_list_parser,
)
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.local_llm import LocalLlmSettings
from datrix_scripts.local_llm_loopback import LOOPBACK, Chat, LoopbackOllama
from datrix_scripts.review.canonical_modules import (
    build_canonical_modules_digest,
    check_cache_validity,
    discover_datrix_packages,
    format_canonical_modules_for_prompt,
    scan_package_modules,
)
from datrix_scripts.review.escalation import should_escalate_to_tier2
from datrix_scripts.review.review import (
    EXIT_CLEAN,
    EXIT_TIER2_MISSING,
    LOCAL_REVIEWER_PROMPT,
    build_reviewer_prompt,
    discover_phase_tasks,
    resolve_task_context,
    run_review,
)
from datrix_scripts.review.review_reply import dict_to_review_result, extract_json_from_response, parse_model_response
from datrix_scripts.review.review_schema import (
    Finding,
    ReviewResult,
    finding_to_dict,
    review_result_to_dict,
)
from datrix_scripts.review.tier2_local import TIER2_MODELS, PhaseContext, phase_artifact_path, phase_prompts
from datrix_scripts.test.wrappers import REVIEW_SCRIPTS_DIR, seam_checks

MODULE: Final = "datrix_scripts.review.review_library_gate"
WRAPPER: Final = "review-library-gate"
GATE: Final = "review-library"

# ---------------------------------------------------------------------------
# review_schema.py -- Finding, ReviewResult, finding_to_dict, review_result_to_dict
# ---------------------------------------------------------------------------


def _check_finding_construction() -> None:
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


def _check_finding_to_dict_preserves_none_rule_reference() -> None:
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


def _check_review_result_construction() -> None:
    review = ReviewResult(
        schema_version="1.0",
        source="local",
        model="qwen2.5-coder:14b",
        scope="task",
        target="task-43-01-foo.md",
        generated_at=datetime.now(UTC).isoformat(),
        verdict="pass",
        findings=[],
        summary="All checks passed.",
    )
    assert review.verdict == "pass"
    assert len(review.findings) == 0


def _check_review_result_to_dict_serializes_findings_list() -> None:
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


# ---------------------------------------------------------------------------
# canonical_modules.py
# ---------------------------------------------------------------------------


def _check_discover_datrix_packages_only_matches_datrix_prefixed_with_src() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-discover-") as tmp:
        root = Path(tmp)
        (root / "datrix-common" / "src").mkdir(parents=True)
        (root / "datrix-language" / "src").mkdir(parents=True)
        (root / "not-a-datrix-package" / "src").mkdir(parents=True)

        packages = discover_datrix_packages(root)

        names = {p.name for p in packages}
        assert names == {"datrix-common", "datrix-language"}, (
            f"expected exactly the two datrix-prefixed src/ dirs, got {names}"
        )


def _check_scan_package_modules_builds_dotted_names() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-scan-") as tmp:
        package_dir = Path(tmp) / "datrix-common"
        (package_dir / "src/datrix_common/utils").mkdir(parents=True)
        (package_dir / "src/datrix_common/utils/__init__.py").write_text("", encoding="utf-8")
        (package_dir / "src/datrix_common/utils/text.py").write_text("", encoding="utf-8")

        modules = scan_package_modules(package_dir)

        assert "datrix_common.utils" in modules
        assert "datrix_common.utils.text" in modules


def _check_build_canonical_modules_digest_keys_by_package() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-digest-") as tmp:
        root = Path(tmp)
        (root / "datrix-common/src/datrix_common").mkdir(parents=True)
        (root / "datrix-common/src/datrix_common/__init__.py").write_text("", encoding="utf-8")

        digest = build_canonical_modules_digest(root)

        assert "datrix-common" in digest
        assert "datrix_common" in digest["datrix-common"]


def _check_cache_validity_missing_file_is_invalid() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-cache-missing-") as tmp:
        root = Path(tmp)
        cache_path = root / "cache.json"

        assert not check_cache_validity(cache_path, root)


def _check_cache_validity_malformed_json_is_invalid() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-cache-malformed-") as tmp:
        root = Path(tmp)
        cache_path = root / "cache.json"
        cache_path.write_text("{ invalid json", encoding="utf-8")

        assert not check_cache_validity(cache_path, root)


def _check_cache_validity_fresh_cache_with_no_git_repo_is_valid() -> None:
    # The comparator must also ACCEPT a good cache -- a check that only ever
    # rejects would prove nothing. A tempdir is never inside a git repo, so
    # canonical_modules.get_git_modification_time() returns None for every
    # discovered package and the cache is never invalidated by "newer" commits.
    with tempfile.TemporaryDirectory(prefix="review-gate-cache-valid-") as tmp:
        root = Path(tmp)
        (root / "datrix-common/src").mkdir(parents=True)
        cache_path = root / "cache.json"
        cache_path.write_text(
            json.dumps({"built_at": datetime.now(UTC).isoformat(), "digest": {}}),
            encoding="utf-8",
        )

        assert check_cache_validity(cache_path, root)


def _check_format_canonical_modules_for_prompt_shape() -> None:
    digest = {
        "datrix-common": ["datrix_common", "datrix_common.utils.text"],
        "datrix-language": ["datrix_language.parser"],
    }

    formatted = format_canonical_modules_for_prompt(digest)

    assert "# Canonical Modules" in formatted
    assert "## datrix-common" in formatted
    assert "- datrix_common.utils.text" in formatted


# ---------------------------------------------------------------------------
# escalation.py -- should_escalate_to_tier2
# ---------------------------------------------------------------------------


def _make_result(verdict: str) -> ReviewResult:
    return ReviewResult(
        schema_version="1.0",
        source="local",
        model="qwen2.5-coder:14b",
        scope="task",
        target="task.md",
        generated_at="2026-05-10T12:00:00Z",
        verdict=verdict,  # type: ignore[arg-type]
        findings=[],
        summary="Test result",
    )


def _check_escalate_manual_override_always_escalates() -> None:
    config = {"tier2": {"enabled": True, "mode": "off"}}
    results = [_make_result("pass")]

    assert should_escalate_to_tier2(results, config, manual_override=True)


def _check_no_escalate_mode_off() -> None:
    config = {"tier2": {"enabled": True, "mode": "off"}}
    results = [_make_result("blocking")]

    assert not should_escalate_to_tier2(results, config)


def _check_escalate_threshold_blocking() -> None:
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 1,
            "threshold_total_major": 5,
        }
    }
    results = [_make_result("blocking")]

    assert should_escalate_to_tier2(results, config)


def _check_escalate_threshold_major() -> None:
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 10,
            "threshold_total_major": 3,
        }
    }
    results = [_make_result("needs_fixes"), _make_result("needs_fixes"), _make_result("needs_fixes")]

    assert should_escalate_to_tier2(results, config)


def _check_no_escalate_threshold_below() -> None:
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 1,
            "threshold_total_major": 5,
        }
    }
    results = [_make_result("warnings_only"), _make_result("pass")]

    assert not should_escalate_to_tier2(results, config)


def _check_escalate_phase_gate_always_escalates() -> None:
    config = {"tier2": {"enabled": True, "mode": "phase-gate"}}
    results = [_make_result("pass")]

    assert should_escalate_to_tier2(results, config)


def _check_no_escalate_when_tier2_disabled_even_with_override() -> None:
    config = {"tier2": {"enabled": False, "mode": "manual"}}
    results = [_make_result("blocking")]

    assert not should_escalate_to_tier2(results, config, manual_override=True)


def _check_no_escalate_mode_manual_without_override() -> None:
    config = {"tier2": {"enabled": True, "mode": "manual"}}
    results = [_make_result("blocking")]

    assert not should_escalate_to_tier2(results, config, manual_override=False)


def _check_no_escalate_unknown_mode() -> None:
    config = {"tier2": {"enabled": True, "mode": "unknown"}}
    results = [_make_result("blocking")]

    assert not should_escalate_to_tier2(results, config)


def _check_escalate_threshold_mixed_verdicts_counts_correctly() -> None:
    config = {
        "tier2": {
            "enabled": True,
            "mode": "threshold",
            "threshold_blocking": 2,
            "threshold_total_major": 3,
        }
    }
    results = [
        _make_result("blocking"),  # 1 blocking, 1 major
        _make_result("needs_fixes"),  # 0 blocking, 1 major
        _make_result("pass"),
        _make_result("warnings_only"),
    ]

    # blocking_count = 1 (< 2), major_count = 2 (< 3): must NOT escalate yet.
    assert not should_escalate_to_tier2(results, config)

    results.append(_make_result("blocking"))
    # blocking_count = 2 (>= 2): must escalate now.
    assert should_escalate_to_tier2(results, config)


# ---------------------------------------------------------------------------
# review.py -- extract_json_from_response
# ---------------------------------------------------------------------------


def _check_extract_direct_json() -> None:
    result = extract_json_from_response('{"verdict": "pass", "findings": []}')
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_with_whitespace() -> None:
    result = extract_json_from_response('  \n  {"verdict": "pass"}  \n  ')
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_from_markdown_fences() -> None:
    result = extract_json_from_response('```json\n{"verdict": "pass", "findings": []}\n```')
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_from_plain_fences() -> None:
    result = extract_json_from_response('```\n{"verdict": "pass", "findings": []}\n```')
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_with_preamble() -> None:
    response = 'Here is my review:\n\n{"verdict": "pass", "findings": []}'
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_with_trailing_text() -> None:
    response = '{"verdict": "pass", "findings": []}\n\nI hope this helps!'
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_json_with_preamble_and_fences() -> None:
    response = (
        "I reviewed the task file. Here is my assessment:\n\n"
        '```json\n{"verdict": "needs_fixes", "findings": [{"id": "F-001"}]}\n```\n'
    )
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "needs_fixes"


def _check_extract_nested_braces() -> None:
    response = (
        "Some text before\n"
        '{"verdict": "needs_fixes", "findings": [{"id": "F-001", "nested": {"key": "value"}}]}\n'
        "Some text after"
    )
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "needs_fixes"
    assert result["findings"][0]["nested"]["key"] == "value"


def _check_extract_json_with_strings_containing_braces() -> None:
    response = '{"description": "Missing { and } in code", "verdict": "pass"}'
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "pass"


def _check_extract_returns_none_for_garbage() -> None:
    response = "This is not JSON at all, just random text without any braces"
    assert extract_json_from_response(response) is None


def _check_extract_returns_none_for_invalid_json_in_fences() -> None:
    response = "```json\n{invalid json content}\n```"
    assert extract_json_from_response(response) is None


def _check_extract_rejects_non_review_json() -> None:
    response = '{"name": "some module", "version": "1.0", "dependencies": []}'
    assert extract_json_from_response(response) is None


def _check_extract_picks_review_json_over_other_json() -> None:
    response = (
        'Some context: {"name": "module", "type": "package"}\n\n'
        "My review:\n"
        '{"verdict": "pass", "findings": [], "summary": "All good"}\n'
    )
    result = extract_json_from_response(response)
    assert result is not None
    assert result["verdict"] == "pass"
    assert result["summary"] == "All good"


def _check_extract_picks_largest_review_json() -> None:
    small = '{"verdict": "pass"}'
    large = (
        '{"schema_version": "1.0", "verdict": "pass", "findings": [], '
        '"summary": "Detailed review"}'
    )
    response = f"{small}\n\nActually, here is the full review:\n{large}"
    result = extract_json_from_response(response)
    assert result is not None
    assert "schema_version" in result
    assert result["summary"] == "Detailed review"


# ---------------------------------------------------------------------------
# review.py -- parse_model_response
# ---------------------------------------------------------------------------


def _check_parse_model_valid_json() -> None:
    response = (
        '{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "OK"}'
    )
    result = parse_model_response(response, "qwen3-coder:30b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_fenced_json() -> None:
    response = (
        '```json\n{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "OK"}\n```'
    )
    result = parse_model_response(response, "qwen3-coder:30b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_with_preamble() -> None:
    response = (
        "Based on my review of the task file, here are my findings:\n\n"
        '{"schema_version": "1.0", "source": "local", "verdict": "warnings_only", '
        '"findings": [{"id": "F-001", "severity": "minor", "category": "ambiguity", '
        '"location": "Files to Create", "description": "Vague language", '
        '"evidence": "handle appropriately", "suggested_fix": "Be specific", '
        '"rule_reference": null}], '
        '"summary": "One minor issue found."}'
    )
    result = parse_model_response(response, "qwen2.5-coder:14b")
    assert result is not None
    assert result["verdict"] == "warnings_only"
    assert len(result["findings"]) == 1


def _check_parse_model_invalid_json() -> None:
    assert parse_model_response("This is not JSON", "qwen3-coder:30b") is None


def _check_parse_model_with_think_tags() -> None:
    response = (
        "\n<think>\nI need to review this task carefully...\n"
        "Checking for anti-patterns...\n</think>\n"
        '{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "OK"}\n'
    )
    result = parse_model_response(response, "deepseek-r1:32b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_think_tags_then_fences() -> None:
    response = (
        "<think>\nLet me analyze the task...\n</think>\n\n"
        '```json\n{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "All good"}\n```'
    )
    result = parse_model_response(response, "qwen3-coder:30b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_think_tags_then_preamble_then_json() -> None:
    response = (
        "<think>\nReasoning here...\n</think>\n"
        "Here is my review:\n"
        '{"verdict": "pass", "findings": []}'
    )
    result = parse_model_response(response, "deepseek-r1:32b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_no_think_tags() -> None:
    response = (
        '{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "OK"}'
    )
    result = parse_model_response(response, "deepseek-r1:32b")
    assert result is not None
    assert result["verdict"] == "pass"


def _check_parse_model_invalid_json_after_stripping_think_tags() -> None:
    response = "<think>Reasoning</think>Not JSON at all"
    assert parse_model_response(response, "deepseek-r1:32b") is None


# ---------------------------------------------------------------------------
# review.py -- resolve_task_context, discover_phase_tasks, dict_to_review_result,
# build_reviewer_prompt
# ---------------------------------------------------------------------------


def _check_resolve_task_context_extracts_design_reference_and_agent_rules() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-context-") as tmp:
        root = Path(tmp)
        task_file = root / "task-43-01-foo.md"
        task_file.write_text(
            "# Task 43-01: Foo\n\n**Design reference:** design.md -- Section(s) 4.2\n\n"
            "Content here.",
            encoding="utf-8",
        )
        (root / "datrix-common/docs/contributing").mkdir(parents=True)
        (root / "datrix-common/docs/contributing/ai-agent-rules.md").write_text(
            "# AI Agent Rules\n\nRules here.", encoding="utf-8"
        )

        config = {"paths": {"datrix_root": str(root)}}
        context = resolve_task_context(task_file, config)

        assert "task_content" in context
        assert "# Task 43-01: Foo" in context["task_content"]
        assert "agent_rules_subdocs" in context
        assert "Rules here." in context["agent_rules_subdocs"]


def _check_discover_phase_tasks_searches_every_datrix_repo() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-phase-tasks-") as tmp:
        root = Path(tmp)
        (root / "datrix-common/.tasks/phase-43").mkdir(parents=True)
        (root / "datrix-common/.tasks/phase-43/task-43-01-foo.md").write_text(
            "# Task 43-01", encoding="utf-8"
        )
        (root / "datrix-codegen-python/.tasks/phase-43").mkdir(parents=True)
        (root / "datrix-codegen-python/.tasks/phase-43/task-43-02-bar.md").write_text(
            "# Task 43-02", encoding="utf-8"
        )

        config = {"paths": {"datrix_root": str(root)}}
        tasks = discover_phase_tasks(43, config)

        assert len(tasks) == 2
        assert any("task-43-01" in str(t) for t in tasks)
        assert any("task-43-02" in str(t) for t in tasks)


def _check_dict_to_review_result_converts_findings() -> None:
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


def _check_build_reviewer_prompt_orders_task_content_before_template() -> None:
    with tempfile.TemporaryDirectory(prefix="review-gate-prompt-") as tmp:
        root = Path(tmp)
        task_file = root / "task.md"
        task_file.write_text("# Task 43-01: Foo", encoding="utf-8")
        prompt_template_file = root / "prompt.md"
        prompt_template_file.write_text("# Reviewer Prompt Template", encoding="utf-8")

        context = {
            "task_content": "# Task 43-01: Foo",
            "design_section": "",
            "agent_rules_subdocs": "# Agent Rules\nRule 1",
        }
        canonical_modules_digest = {
            "datrix-common": ["datrix_common", "datrix_common.utils"],
        }

        prompt = build_reviewer_prompt(
            task_file, context, prompt_template_file, canonical_modules_digest,
            model_name="gate-model:1b",
        )

        assert "# Reviewer Prompt Template" in prompt
        assert "# Task 43-01: Foo" in prompt
        assert "# Canonical Modules" in prompt
        task_pos = prompt.index("# Task 43-01: Foo")
        template_pos = prompt.index("# Reviewer Prompt Template")
        assert task_pos < template_pos, "task content must come before template instructions"


# ---------------------------------------------------------------------------
# Tier 2: a phase review on a local model (tier2_local.py), against a loopback Ollama
# ---------------------------------------------------------------------------

_PHASE = 7
_WELL_FORMED_TASK = """> **Peruse** the files below before starting.

# Task 07-01: Add the widget registry

**Package:** datrix-alpha
**Design reference:** widget registry
**Depends on:** none

## Overview

Add a registry of widgets.

## Files to Review Before Starting

- src/alpha/registry.py

## Files to Create

- src/alpha/widgets.py

## Anti-Patterns to Avoid

- No silent fallbacks.

## Success Criteria

1. The registry lists every widget.
2. An unknown widget raises KeyError.
3. Widgets are sorted by name.
4. The registry is immutable.
5. Every widget has a docstring.

## Targeted Tests

- tests/unit/test_widgets.py
"""
_TASK_REVIEW = json.dumps({"schema_version": "1.0", "source": "local", "model": "m", "scope": "task",
                           "target": "task-07-01-widget.md", "generated_at": "2026-10-14T00:00:00Z",
                           "verdict": "pass", "findings": [], "summary": "No subjective issues found."})
_PHASE_REVIEW = json.dumps({
    "schema_version": "1.0", "source": "phase", "model": "m", "scope": "phase", "target": "phase-07",
    "generated_at": "2026-10-14T00:00:00Z", "verdict": "warnings_only",
    "findings": [{"id": "F-001", "severity": "minor", "category": "other", "location": "task-07-01-widget.md",
                  "description": "The registry module is named twice.", "evidence": "registry.py",
                  "suggested_fix": "Name it once.", "rule_reference": None}],
    "summary": "One minor phase-level issue."})


def _canned_review(chat: Chat) -> str:
    """The phase verdict for the phase prompt, a clean task verdict for a task prompt."""
    return _PHASE_REVIEW if f"# Phase {_PHASE:02d}" in chat.user else _TASK_REVIEW


def _phase_review_exit(models: tuple[str, ...]) -> tuple[int, Path, bool]:
    """Run a phase-gate review over one well-formed task; (exit code, phase artifact, its existence)."""
    with tempfile.TemporaryDirectory(prefix="review-tier2-") as temp, \
            LoopbackOllama(_canned_review, models) as server:
        workspace = Path(temp)
        task = workspace / "datrix-alpha" / ".tasks" / f"phase-{_PHASE:02d}" / "task-07-01-widget.md"
        task.parent.mkdir(parents=True)
        task.write_text(_WELL_FORMED_TASK, encoding="utf-8")
        config = {
            "tier1": {"context_window": 32768},
            "tier2": {"enabled": True, "mode": "phase-gate", "context_window": 65536},
            "paths": {"datrix_root": str(workspace), "review_artifacts": str(workspace / ".review")},
        }
        settings = LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, load_timeout_ms=5000,
                                    generate_timeout_ms=5000, ollama_port=server.port,
                                    usage_log=workspace / "usage.jsonl", caller="gate")
        args = argparse.Namespace(task=None, phase=_PHASE, verify=False, tier2=False, tier2_mode=None)
        code = run_review(args, config, LOCAL_REVIEWER_PROMPT, {}, settings)
        artifact = phase_artifact_path(config, _PHASE)
        written = artifact.is_file() and json.loads(artifact.read_text(encoding="utf-8"))
        return code, artifact, bool(written) and written["source"] == "phase" and \
            [f["id"] for f in written["findings"]] == ["P-001"]


def _check_tier2_phase_review_writes_the_phase_artifact() -> None:
    code, artifact, written = _phase_review_exit(("tier1-model:7b", TIER2_MODELS[-1]))
    assert code == EXIT_CLEAN, f"a phase review with a clean Tier 1 and an answered Tier 2 exits 0, got {code}"
    assert written, f"{artifact.name} holds the phase finding as P-001, source 'phase'"


def _check_tier2_unavailable_exits_tier2_missing() -> None:
    code, artifact, written = _phase_review_exit(("tier1-model:7b",))
    assert code == EXIT_TIER2_MISSING, f"no tier-2 model must exit EXIT_TIER2_MISSING, got {code}"
    assert not written, f"{artifact.name} must not exist when Tier 2 did not run"


def _check_a_phase_too_large_for_the_window_is_split_by_task() -> None:
    context = PhaseContext(_PHASE, "digest", "instructions")
    sections = ["## Task file: a\n" + "x" * 400, "## Task file: b\n" + "y" * 400, "## Task file: c\n" + "z" * 50]
    assert len(phase_prompts(context, sections, budget_chars=100_000)) == 1
    split = phase_prompts(context, sections, budget_chars=700)
    assert len(split) == 2 and all("digest" in p and "instructions" in p for p in split), split
    assert "## Task file: a" in split[0] and "## Task file: b" in split[1] and "## Task file: c" in split[1]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_CHECK_PREFIX = "_check_"

_CHECK_FUNCTIONS: tuple[CheckFunc, ...] = (
    _check_finding_construction,
    _check_finding_to_dict_preserves_none_rule_reference,
    _check_review_result_construction,
    _check_review_result_to_dict_serializes_findings_list,
    _check_discover_datrix_packages_only_matches_datrix_prefixed_with_src,
    _check_scan_package_modules_builds_dotted_names,
    _check_build_canonical_modules_digest_keys_by_package,
    _check_cache_validity_missing_file_is_invalid,
    _check_cache_validity_malformed_json_is_invalid,
    _check_cache_validity_fresh_cache_with_no_git_repo_is_valid,
    _check_format_canonical_modules_for_prompt_shape,
    _check_escalate_manual_override_always_escalates,
    _check_no_escalate_mode_off,
    _check_escalate_threshold_blocking,
    _check_escalate_threshold_major,
    _check_no_escalate_threshold_below,
    _check_escalate_phase_gate_always_escalates,
    _check_no_escalate_when_tier2_disabled_even_with_override,
    _check_no_escalate_mode_manual_without_override,
    _check_no_escalate_unknown_mode,
    _check_escalate_threshold_mixed_verdicts_counts_correctly,
    _check_extract_direct_json,
    _check_extract_json_with_whitespace,
    _check_extract_json_from_markdown_fences,
    _check_extract_json_from_plain_fences,
    _check_extract_json_with_preamble,
    _check_extract_json_with_trailing_text,
    _check_extract_json_with_preamble_and_fences,
    _check_extract_nested_braces,
    _check_extract_json_with_strings_containing_braces,
    _check_extract_returns_none_for_garbage,
    _check_extract_returns_none_for_invalid_json_in_fences,
    _check_extract_rejects_non_review_json,
    _check_extract_picks_review_json_over_other_json,
    _check_extract_picks_largest_review_json,
    _check_parse_model_valid_json,
    _check_parse_model_fenced_json,
    _check_parse_model_with_preamble,
    _check_parse_model_invalid_json,
    _check_parse_model_with_think_tags,
    _check_parse_model_think_tags_then_fences,
    _check_parse_model_think_tags_then_preamble_then_json,
    _check_parse_model_no_think_tags,
    _check_parse_model_invalid_json_after_stripping_think_tags,
    _check_resolve_task_context_extracts_design_reference_and_agent_rules,
    _check_discover_phase_tasks_searches_every_datrix_repo,
    _check_dict_to_review_result_converts_findings,
    _check_build_reviewer_prompt_orders_task_content_before_template,
    _check_tier2_phase_review_writes_the_phase_artifact,
    _check_tier2_unavailable_exits_tier2_missing,
    _check_a_phase_too_large_for_the_window_is_split_by_task,
)

_CHECKS: list[NamedCheck] = [
    NamedCheck(check.__name__.removeprefix(_CHECK_PREFIX), check) for check in _CHECK_FUNCTIONS
]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``review/review-library-gate.ps1``: one per wrapper parameter, spelled exactly."""
    return check_list_parser(
        "Repo-level gate for the review library (review_schema, canonical_modules, escalation, "
        "review_reply parsing, the review orchestrator and Tier 2).",
        debug_flag=WRAPPER_DEBUG_FLAG,
        allow_abbrev=False,
    )


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the harness reports a deliberate failure, and the wrapper is the template rendered
    # with this parser's options.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        GATE,
        _CHECKS,
        self_test=seam_checks(wrapper=WRAPPER, module=MODULE, parser=parser, folder=REVIEW_SCRIPTS_DIR),
        argv=argv,
        parser=parser,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
