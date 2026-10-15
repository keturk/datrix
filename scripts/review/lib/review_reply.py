"""A local model's review reply: the request every review tier sends, and the parsing of its answer.

Tier 1 (one task, ``review.py``) and Tier 2 (the phase, ``tier2_local.py``) ask the same way and
read the answer the same way, so both live here.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from datrix_scripts.local_llm import ChatRequest, LocalLlmPool, LocalLlmReply
from review_schema import Finding, ReviewResult

logger = logging.getLogger(__name__)

# The review request shape. Structured JSON output for a long task file needs room to
# answer and time to produce it.
REVIEW_SYSTEM_PROMPT = (
    "You are a task file reviewer. You review task files for defects. "
    "You output ONLY a JSON object with keys: schema_version, source, model, "
    "scope, target, generated_at, verdict, findings, summary. "
    "Your response must start with { and end with }. No other text."
)
REVIEW_TEMPERATURE = 0.3
REVIEW_MAX_TOKENS = 32768
REVIEW_GENERATE_TIMEOUT_MS = 180000
# A local model's answer that does not parse as a review is asked for again; a server
# that fails outright is dropped by the pool and the next one answers instead.
REVIEW_ATTEMPTS = 3


def request_review(prompt: str, pool: LocalLlmPool, context_window: int) -> LocalLlmReply:
    """Ask a local model for a review. Raises LocalLlmUnavailable when no server can answer."""
    return pool.chat(ChatRequest(
        system=REVIEW_SYSTEM_PROMPT,
        user=prompt,
        temperature=REVIEW_TEMPERATURE,
        max_tokens=REVIEW_MAX_TOKENS,
        context_window=context_window,
    ))


_REVIEW_KEYS = {"verdict", "findings", "schema_version", "summary"}


def _looks_like_review(data: dict) -> bool:
    """Check if a parsed dict has enough review-schema keys to be a real review.

    Prevents accepting random JSON fragments (from prompt context, canonical
    modules, or model preamble) as valid review responses.
    """
    return bool(_REVIEW_KEYS & data.keys())


def _top_level_objects(text: str) -> list[str]:
    """Every top-level ``{ ... }`` block in ``text``, found by brace matching outside strings."""
    candidates: list[str] = []
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            break
        found_end = _matching_brace(text, start)
        if found_end == -1:
            break
        candidates.append(text[start : found_end + 1])
        idx = found_end + 1
    return candidates


def _matching_brace(text: str, start: int) -> int:
    """Index of the ``}`` closing the ``{`` at ``start``; -1 when it never closes."""
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
        elif c == "\\":
            escape_next = True
        elif c == '"':
            in_string = not in_string
        elif not in_string and c == "{":
            depth += 1
        elif not in_string and c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _review_or_none(candidate: str) -> dict | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) and _looks_like_review(parsed) else None


def extract_json_from_response(response: str) -> dict | None:
    """Extract JSON from a model response using multiple strategies.

    Local models frequently wrap JSON in markdown fences, add preamble text,
    or include trailing commentary. This function tries several extraction
    strategies in order of specificity.

    After extraction, validates that the result contains at least one
    review-schema key (verdict, findings, schema_version, summary) to avoid
    matching unrelated JSON from the prompt context.

    Strategies (tried in order):
    1. Direct parse (clean JSON response)
    2. Strip markdown fences (```json ... ``` or ``` ... ```)
    3. Find largest { ... } block via brace matching
    """
    text = response.strip()
    direct = _review_or_none(text)
    if direct is not None:
        return direct
    # Matches ```json\n...\n``` or ```\n...\n``` (with optional language tag)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence_match:
        fenced = _review_or_none(fence_match.group(1).strip())
        if fenced is not None:
            return fenced
    # The review JSON is typically the biggest object in the response.
    for candidate in sorted(_top_level_objects(text), key=len, reverse=True):
        parsed = _review_or_none(candidate)
        if parsed is not None:
            return parsed
    return None


def parse_model_response(response: str, model: str) -> dict | None:
    """Parse a model answer (reasoning already stripped by datrix_scripts.local_llm) as a review."""
    result = extract_json_from_response(response)
    if result is None:
        logger.warning("parse_failed model=%s response_length=%d", model, len(response))
    return result


def compute_verdict(findings: list[Finding]) -> str:
    """Compute verdict from findings based on highest severity."""
    severities = {f.severity for f in findings}
    if "blocking" in severities:
        return "blocking"
    if "major" in severities:
        return "needs_fixes"
    if "minor" in severities:
        return "warnings_only"
    return "pass"


def dict_to_review_result(data: dict, task_path: Path) -> ReviewResult:
    """Convert parsed JSON dict to ReviewResult dataclass.

    Tolerates missing fields from local models that don't always
    produce perfect schema conformance. Missing fields get sensible defaults.
    """
    raw_findings = data.get("findings", [])
    findings: list[Finding] = []
    for f in raw_findings:
        if not isinstance(f, dict):
            continue
        findings.append(
            Finding(
                id=f.get("id", f"F-{len(findings) + 1:03d}"),
                severity=f.get("severity", "minor"),
                category=f.get("category", "other"),
                location=f.get("location", str(task_path)),
                description=f.get("description", "(no description)"),
                evidence=f.get("evidence", ""),
                suggested_fix=f.get("suggested_fix", ""),
                rule_reference=f.get("rule_reference"),
            )
        )

    return ReviewResult(
        schema_version=data.get("schema_version", "1.0"),
        source=data.get("source", "local"),
        model=data.get("model", "unknown"),
        scope=data.get("scope", "task"),
        target=data.get("target", str(task_path)),
        generated_at=data.get("generated_at", datetime.now(UTC).isoformat()),
        verdict=data.get("verdict", "warnings_only"),
        findings=findings,
        summary=data.get("summary", "(no summary)"),
    )
