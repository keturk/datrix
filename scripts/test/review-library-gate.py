#!/usr/bin/env python3
"""Repo-level gate absorbing 5 orphaned pytest files from `scripts/library/review/tests/`.

`datrix/scripts/library/review/tests/` held pytest files that no runner ever executed (the
`datrix` showcase repo hosts no test suite of any kind -- see CLAUDE.md "Datrix Showcase Repo
Boundaries"). This gate absorbs the valuable, non-vacuous coverage from 5 of those 8 files as a
plain-Python check harness (the other 3 -- test_tier2_integration.py, test_ollama_integration.py,
test_integration_full_pipeline.py -- are network/subprocess integration tests dispositioned
separately) and re-expresses each file's distinct behavioral classes as named ``_check_*``
functions:

  - test_review_schema.py         -> review/review_schema.py (Finding, ReviewResult, serializers)
  - test_canonical_modules_cache.py -> review/canonical_modules.py (package discovery, module
    scanning, digest building, cache validity, prompt formatting)
  - test_escalation.py            -> review/escalation.py (should_escalate_to_tier2)
  - test_model_parsing.py         -> review/review.py (extract_json_from_response,
    parse_model_response)
  - test_orchestrator_core.py     -> review/review.py (resolve_task_context, discover_phase_tasks,
    dict_to_review_result, build_reviewer_prompt)

Repo-level validation script, not a pytest suite (per the datrix showcase boundary). Uses only
``assert`` + a small harness that catches ``AssertionError`` per check and prints [OK]/[FAIL] --
no pytest, no mocks/fakes, real ``tempfile.TemporaryDirectory()`` fixtures for every filesystem
case.

Exit codes: 0 = every check passed, 1 = at least one check (or the harness self-test) failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from review import (  # noqa: E402
    build_canonical_modules_digest,
    build_reviewer_prompt,
    check_cache_validity,
    dict_to_review_result,
    discover_datrix_packages,
    discover_phase_tasks,
    extract_json_from_response,
    format_canonical_modules_for_prompt,
    parse_model_response,
    resolve_task_context,
    scan_package_modules,
)
from review.escalation import should_escalate_to_tier2  # noqa: E402
from review.review_schema import (  # noqa: E402
    Finding,
    ReviewResult,
    finding_to_dict,
    review_result_to_dict,
)

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


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
            task_file, context, prompt_template_file, canonical_modules_digest
        )

        assert "# Reviewer Prompt Template" in prompt
        assert "# Task 43-01: Foo" in prompt
        assert "# Canonical Modules" in prompt
        task_pos = prompt.index("# Task 43-01: Foo")
        template_pos = prompt.index("# Reviewer Prompt Template")
        assert task_pos < template_pos, "task content must come before template instructions"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("finding_construction", _check_finding_construction),
    ("finding_to_dict_preserves_none_rule_reference", _check_finding_to_dict_preserves_none_rule_reference),
    ("review_result_construction", _check_review_result_construction),
    ("review_result_to_dict_serializes_findings_list", _check_review_result_to_dict_serializes_findings_list),
    ("discover_datrix_packages_only_matches_datrix_prefixed_with_src", _check_discover_datrix_packages_only_matches_datrix_prefixed_with_src),
    ("scan_package_modules_builds_dotted_names", _check_scan_package_modules_builds_dotted_names),
    ("build_canonical_modules_digest_keys_by_package", _check_build_canonical_modules_digest_keys_by_package),
    ("cache_validity_missing_file_is_invalid", _check_cache_validity_missing_file_is_invalid),
    ("cache_validity_malformed_json_is_invalid", _check_cache_validity_malformed_json_is_invalid),
    ("cache_validity_fresh_cache_with_no_git_repo_is_valid", _check_cache_validity_fresh_cache_with_no_git_repo_is_valid),
    ("format_canonical_modules_for_prompt_shape", _check_format_canonical_modules_for_prompt_shape),
    ("escalate_manual_override_always_escalates", _check_escalate_manual_override_always_escalates),
    ("no_escalate_mode_off", _check_no_escalate_mode_off),
    ("escalate_threshold_blocking", _check_escalate_threshold_blocking),
    ("escalate_threshold_major", _check_escalate_threshold_major),
    ("no_escalate_threshold_below", _check_no_escalate_threshold_below),
    ("escalate_phase_gate_always_escalates", _check_escalate_phase_gate_always_escalates),
    ("no_escalate_when_tier2_disabled_even_with_override", _check_no_escalate_when_tier2_disabled_even_with_override),
    ("no_escalate_mode_manual_without_override", _check_no_escalate_mode_manual_without_override),
    ("no_escalate_unknown_mode", _check_no_escalate_unknown_mode),
    ("escalate_threshold_mixed_verdicts_counts_correctly", _check_escalate_threshold_mixed_verdicts_counts_correctly),
    ("extract_direct_json", _check_extract_direct_json),
    ("extract_json_with_whitespace", _check_extract_json_with_whitespace),
    ("extract_json_from_markdown_fences", _check_extract_json_from_markdown_fences),
    ("extract_json_from_plain_fences", _check_extract_json_from_plain_fences),
    ("extract_json_with_preamble", _check_extract_json_with_preamble),
    ("extract_json_with_trailing_text", _check_extract_json_with_trailing_text),
    ("extract_json_with_preamble_and_fences", _check_extract_json_with_preamble_and_fences),
    ("extract_nested_braces", _check_extract_nested_braces),
    ("extract_json_with_strings_containing_braces", _check_extract_json_with_strings_containing_braces),
    ("extract_returns_none_for_garbage", _check_extract_returns_none_for_garbage),
    ("extract_returns_none_for_invalid_json_in_fences", _check_extract_returns_none_for_invalid_json_in_fences),
    ("extract_rejects_non_review_json", _check_extract_rejects_non_review_json),
    ("extract_picks_review_json_over_other_json", _check_extract_picks_review_json_over_other_json),
    ("extract_picks_largest_review_json", _check_extract_picks_largest_review_json),
    ("parse_model_valid_json", _check_parse_model_valid_json),
    ("parse_model_fenced_json", _check_parse_model_fenced_json),
    ("parse_model_with_preamble", _check_parse_model_with_preamble),
    ("parse_model_invalid_json", _check_parse_model_invalid_json),
    ("parse_model_with_think_tags", _check_parse_model_with_think_tags),
    ("parse_model_think_tags_then_fences", _check_parse_model_think_tags_then_fences),
    ("parse_model_think_tags_then_preamble_then_json", _check_parse_model_think_tags_then_preamble_then_json),
    ("parse_model_no_think_tags", _check_parse_model_no_think_tags),
    ("parse_model_invalid_json_after_stripping_think_tags", _check_parse_model_invalid_json_after_stripping_think_tags),
    ("resolve_task_context_extracts_design_reference_and_agent_rules", _check_resolve_task_context_extracts_design_reference_and_agent_rules),
    ("discover_phase_tasks_searches_every_datrix_repo", _check_discover_phase_tasks_searches_every_datrix_repo),
    ("dict_to_review_result_converts_findings", _check_dict_to_review_result_converts_findings),
    ("build_reviewer_prompt_orders_task_content_before_template", _check_build_reviewer_prompt_orders_task_content_before_template),
]


def _dummy_intentionally_failing_check() -> None:
    """Registered ONLY under --harness-self-test.

    Always fails on purpose -- this is the proof that run_checks() actually
    detects and reports a failing check, rather than vacuously swallowing
    every AssertionError and reporting green regardless of what the checks do.
    """
    raise AssertionError("intentional harness self-test failure (expected -- proves non-vacuity)")


def run_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check.

    Args:
        checks: Named zero-argument callables; each raises AssertionError on
            failure and returns normally on success.

    Returns:
        True iff every check passed.
    """
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except AssertionError as e:
            _fail(f"{name}: {e}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repo-level gate absorbing 5 orphaned review/tests/*.py pytest files "
            "(review_schema, canonical_modules, escalation, review.py parsing + orchestrator core)."
        )
    )
    parser.add_argument(
        "--harness-self-test",
        action="store_true",
        help=(
            "Demonstration mode: run one intentionally-failing dummy check through "
            "the harness and report the result. Always reports [FAIL] and exits 1 -- "
            "this is the proof that the harness's pass/fail detection is not vacuous."
        ),
    )
    args = parser.parse_args()

    if args.harness_self_test:
        _step("Harness self-test: intentionally-failing dummy check (must report FAIL, exit 1)")
        harness_ok = run_checks(
            [("dummy_intentionally_failing_check", _dummy_intentionally_failing_check)]
        )
        return 0 if harness_ok else 1

    _step("review-library-gate: review_schema, canonical_modules, escalation, review.py")
    passed = run_checks(_CHECKS)

    print()
    if passed:
        print(
            f"{_GREEN}GATE PASSED{_RESET}: all {len(_CHECKS)} absorbed review-library checks passed."
        )
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
