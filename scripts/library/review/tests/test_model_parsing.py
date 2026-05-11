"""Unit tests for model response parsing and JSON extraction."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from review import extract_json_from_response, parse_model_response


# --- extract_json_from_response tests ---


def test_extract_direct_json() -> None:
    """Direct valid JSON with review keys is parsed."""
    response = '{"verdict": "pass", "findings": []}'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_with_whitespace() -> None:
    """JSON with leading/trailing whitespace is parsed."""
    response = '  \n  {"verdict": "pass"}  \n  '

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_from_markdown_fences() -> None:
    """JSON wrapped in ```json ... ``` fences is extracted."""
    response = '```json\n{"verdict": "pass", "findings": []}\n```'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_from_plain_fences() -> None:
    """JSON wrapped in ``` ... ``` fences (no language tag) is extracted."""
    response = '```\n{"verdict": "pass", "findings": []}\n```'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_with_preamble() -> None:
    """JSON preceded by preamble text is extracted via brace matching."""
    response = 'Here is my review:\n\n{"verdict": "pass", "findings": []}'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_with_trailing_text() -> None:
    """JSON followed by trailing commentary is extracted via brace matching."""
    response = '{"verdict": "pass", "findings": []}\n\nI hope this helps!'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_json_with_preamble_and_fences() -> None:
    """Preamble + fenced JSON is extracted."""
    response = (
        "I reviewed the task file. Here is my assessment:\n\n"
        '```json\n{"verdict": "needs_fixes", "findings": [{"id": "F-001"}]}\n```\n'
    )

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "needs_fixes"


def test_extract_nested_braces() -> None:
    """JSON with nested objects is correctly extracted via brace matching."""
    response = (
        'Some text before\n'
        '{"verdict": "needs_fixes", "findings": [{"id": "F-001", "nested": {"key": "value"}}]}\n'
        'Some text after'
    )

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "needs_fixes"
    assert result["findings"][0]["nested"]["key"] == "value"


def test_extract_json_with_strings_containing_braces() -> None:
    """JSON with braces inside string values doesn't break brace matching."""
    response = '{"description": "Missing { and } in code", "verdict": "pass"}'

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"


def test_extract_returns_none_for_garbage() -> None:
    """Completely invalid response returns None."""
    response = "This is not JSON at all, just random text without any braces"

    result = extract_json_from_response(response)

    assert result is None


def test_extract_returns_none_for_invalid_json_in_fences() -> None:
    """Invalid JSON inside fences returns None."""
    response = '```json\n{invalid json content}\n```'

    result = extract_json_from_response(response)

    assert result is None


def test_extract_rejects_non_review_json() -> None:
    """Valid JSON without review-schema keys is rejected."""
    response = '{"name": "some module", "version": "1.0", "dependencies": []}'

    result = extract_json_from_response(response)

    assert result is None


def test_extract_picks_review_json_over_other_json() -> None:
    """When response contains multiple JSON objects, the review one is picked."""
    response = (
        'Some context: {"name": "module", "type": "package"}\n\n'
        'My review:\n'
        '{"verdict": "pass", "findings": [], "summary": "All good"}\n'
    )

    result = extract_json_from_response(response)

    assert result is not None
    assert result["verdict"] == "pass"
    assert result["summary"] == "All good"


def test_extract_picks_largest_review_json() -> None:
    """When multiple review-like JSON objects exist, picks the largest."""
    small = '{"verdict": "pass"}'
    large = '{"schema_version": "1.0", "verdict": "pass", "findings": [], "summary": "Detailed review"}'
    response = f'{small}\n\nActually, here is the full review:\n{large}'

    result = extract_json_from_response(response)

    assert result is not None
    assert "schema_version" in result
    assert result["summary"] == "Detailed review"


# --- parse_model_response tests ---


def test_parse_model_valid_json() -> None:
    """Unified parser handles clean JSON."""
    response = '{"schema_version": "1.0", "source": "local", "verdict": "pass", "findings": [], "summary": "OK"}'

    result = parse_model_response(response, "qwen3-coder:30b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_fenced_json() -> None:
    """Unified parser extracts JSON from markdown fences."""
    response = '```json\n{"schema_version": "1.0", "source": "local", "verdict": "pass", "findings": [], "summary": "OK"}\n```'

    result = parse_model_response(response, "qwen3-coder:30b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_with_preamble() -> None:
    """Unified parser extracts JSON after preamble text."""
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


def test_parse_model_invalid_json() -> None:
    """Unified parser with invalid JSON returns None."""
    response = "This is not JSON"

    result = parse_model_response(response, "qwen3-coder:30b")

    assert result is None


def test_parse_model_with_think_tags() -> None:
    """Unified parser strips <think> tags (deepseek-r1, qwen3)."""
    response = '''
<think>
I need to review this task carefully...
Checking for anti-patterns...
</think>
{"schema_version": "1.0", "source": "local", "verdict": "pass", "findings": [], "summary": "OK"}
'''

    result = parse_model_response(response, "deepseek-r1:32b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_think_tags_then_fences() -> None:
    """Unified parser handles <think> tags followed by fenced JSON."""
    response = (
        "<think>\nLet me analyze the task...\n</think>\n\n"
        '```json\n{"schema_version": "1.0", "source": "local", "verdict": "pass", '
        '"findings": [], "summary": "All good"}\n```'
    )

    result = parse_model_response(response, "qwen3-coder:30b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_think_tags_then_preamble_then_json() -> None:
    """Unified parser handles <think> + preamble + JSON."""
    response = (
        "<think>\nReasoning here...\n</think>\n"
        "Here is my review:\n"
        '{"verdict": "pass", "findings": []}'
    )

    result = parse_model_response(response, "deepseek-r1:32b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_no_think_tags() -> None:
    """Unified parser handles response without <think> tags."""
    response = '{"schema_version": "1.0", "source": "local", "verdict": "pass", "findings": [], "summary": "OK"}'

    result = parse_model_response(response, "deepseek-r1:32b")

    assert result is not None
    assert result["verdict"] == "pass"


def test_parse_model_invalid_json_after_stripping() -> None:
    """Unified parser returns None if JSON invalid after stripping tags."""
    response = "<think>Reasoning</think>Not JSON at all"

    result = parse_model_response(response, "deepseek-r1:32b")

    assert result is None
