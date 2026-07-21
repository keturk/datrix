#!/usr/bin/env python3
"""Task Review System Orchestrator.

Coordinates Tier 1 (local Ollama reviewer) and optional Tier 2 (Codex reviewer)
to review task files before execution.

Usage:
  python review.py --phase 05
  python review.py --task path/to/task.md
  python review.py --phase 05 --codex-phase-gate
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

# Local imports
try:
    # When run as a script
    from canonical_modules import (
        format_canonical_modules_for_prompt,
        load_or_build_cache,
    )
    from review_schema import Finding, ReviewResult, review_result_to_dict
    from tier2_codex import invoke_tier2_codex
    from escalation import should_escalate_to_tier2
except ImportError:
    # When imported as a module in the review package
    from .canonical_modules import (
        format_canonical_modules_for_prompt,
        load_or_build_cache,
    )
    from .review_schema import Finding, ReviewResult, review_result_to_dict
    from .tier2_codex import invoke_tier2_codex
    from .escalation import should_escalate_to_tier2

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load config.toml. Raises if file missing or malformed."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("rb") as f:
        return tomllib.load(f)


def call_ollama(
    prompt: str,
    ollama_url: str,
    model: str,
    timeout: int = 300,
) -> str | None:
    """Call Ollama API. Returns response text or None on error."""
    system_msg = (
        "You are a task file reviewer. You review task files for defects. "
        "You output ONLY a JSON object with keys: schema_version, source, model, "
        "scope, target, generated_at, verdict, findings, summary. "
        "Your response must start with { and end with }. No other text."
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 32768},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["message"]["content"]
    except urllib.error.URLError as e:
        logger.error("ollama_connection_failed url=%s error=%s", ollama_url, e)
        return None
    except TimeoutError:
        logger.error("ollama_timeout seconds=%d", timeout)
        return None


_REVIEW_KEYS = {"verdict", "findings", "schema_version", "summary"}


def _looks_like_review(data: dict) -> bool:
    """Check if a parsed dict has enough review-schema keys to be a real review.

    Prevents accepting random JSON fragments (from prompt context, canonical
    modules, or model preamble) as valid review responses.
    """
    return bool(_REVIEW_KEYS & data.keys())


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

    # Strategy 1: direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and _looks_like_review(parsed):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    # Matches ```json\n...\n``` or ```\n...\n``` (with optional language tag)
    fence_match = re.search(
        r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL
    )
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            if isinstance(parsed, dict) and _looks_like_review(parsed):
                return parsed
        except json.JSONDecodeError:
            pass

    # Strategy 3: find the LARGEST top-level JSON object via brace matching.
    # We collect all top-level objects and pick the largest one that validates.
    candidates: list[str] = []
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape_next = False
        found_end = -1
        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    found_end = i
                    break
        if found_end != -1:
            candidates.append(text[start : found_end + 1])
            idx = found_end + 1
        else:
            break

    # Try candidates from largest to smallest — the review JSON is typically
    # the biggest object in the response.
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and _looks_like_review(parsed):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def dump_raw_response(
    response: str,
    task_path: Path,
    model: str,
    attempt: int,
) -> None:
    """Dump raw model response to file for debugging parse failures."""
    dump_dir = task_path.parent / ".review-debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    safe_model = model.replace(":", "-").replace("/", "-")
    dump_path = dump_dir / f"{task_path.stem}.{safe_model}.attempt-{attempt}.txt"
    dump_path.write_text(response, encoding="utf-8")
    logger.info("raw_response_dumped path=%s bytes=%d", dump_path, len(response))


def parse_model_response(response: str, model: str) -> dict | None:
    """Parse model response, handling model-specific quirks.

    Strips <think> blocks (deepseek-r1, qwen3) before JSON extraction.
    """
    cleaned = response
    # Strip thinking blocks used by reasoning models (deepseek-r1, qwen3)
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()

    result = extract_json_from_response(cleaned)
    if result is None:
        logger.warning("parse_failed model=%s response_length=%d", model, len(cleaned))
    return result


def resolve_task_context(task_path: Path, config: dict) -> dict[str, str]:
    """Resolve context for a single task: design doc section, referenced sub-docs.

    Returns:
        dict with keys: "task_content", "design_section", "agent_rules_subdocs"
    """
    task_content = task_path.read_text(encoding="utf-8")

    # Parse "**Design reference:**" line
    design_ref_match = None
    for line in task_content.splitlines():
        if line.startswith("**Design reference:**"):
            design_ref_match = line
            break

    design_section = ""
    if design_ref_match:
        # Extract design doc path and section(s)
        # Format: **Design reference:** {path} -- Section(s) {X.Y}
        # For operationalized tasks, this line contains inlined content, not a path
        # So skip design doc loading (content is inline in task file itself)
        pass

    # Load ai-agent-rules.md index
    datrix_root = Path(config["paths"]["datrix_root"])
    agent_rules_path = datrix_root / "datrix-common/docs/contributing/ai-agent-rules.md"
    agent_rules_content = ""
    if agent_rules_path.exists():
        agent_rules_content = agent_rules_path.read_text(encoding="utf-8")

    # Parse task for sub-doc references and load them
    # For Phase 3, just include the index
    agent_rules_subdocs = agent_rules_content

    return {
        "task_content": task_content,
        "design_section": design_section,
        "agent_rules_subdocs": agent_rules_subdocs,
    }


_REQUIRED_SECTIONS = [
    "## Overview",
    "## Files to Review Before Starting",
    "## Files to Create",
    "## Anti-Patterns to Avoid",
    "## Success Criteria",
    "## Targeted Tests",
]

_REQUIRED_METADATA = ["**Package:**", "**Design reference:**", "**Depends on:**"]

_TITLE_PATTERN = re.compile(r"^# Task \d+-\d+:")


def validate_task_structure(task_content: str, task_name: str) -> list[Finding]:
    """Deterministically validate task file structure.

    Checks for required sections, metadata, title format, and success criteria
    count. These are objective checks that don't need an LLM.
    """
    lines = task_content.splitlines()
    findings: list[Finding] = []
    finding_num = 0

    def _add(severity: str, desc: str, fix: str) -> None:
        nonlocal finding_num
        finding_num += 1
        findings.append(Finding(
            id=f"F-{finding_num:03d}",
            severity=severity,
            category="missing_section",
            location=task_name,
            description=desc,
            evidence="",
            suggested_fix=fix,
            rule_reference=None,
        ))

    # First line must start with '> **Peruse'
    if not lines or not lines[0].strip().startswith("> **Peruse"):
        _add("blocking",
             "First line must start with '> **Peruse'.",
             "Add '> **Peruse ...' as the first line.")

    # Title format: # Task NN-TT: Title
    title_found = False
    for line in lines:
        if line.startswith("# ") and not line.startswith("##"):
            title_found = True
            if not _TITLE_PATTERN.match(line):
                _add("blocking",
                     f"Title format incorrect: '{line}'. Expected '# Task NN-TT: Title'.",
                     "Fix title to match '# Task NN-TT: Title' format.")
            break
    if not title_found:
        _add("blocking",
             "No title heading (# ...) found.",
             "Add a title in '# Task NN-TT: Title' format.")

    # Required sections
    headings = {line.strip() for line in lines if line.startswith("## ")}
    for section in _REQUIRED_SECTIONS:
        if section not in headings:
            _add("blocking",
                 f"Missing required section: '{section}'.",
                 f"Add a '{section}' section.")

    # Required metadata
    for meta_key in _REQUIRED_METADATA:
        if not any(line.strip().startswith(meta_key) for line in lines):
            _add("blocking",
                 f"Missing required metadata line: '{meta_key}'.",
                 f"Add a '{meta_key}' line with appropriate value.")

    # Success Criteria must have >= 5 items
    in_success = False
    criteria_count = 0
    for line in lines:
        if line.startswith("## Success Criteria"):
            in_success = True
            continue
        if in_success and line.startswith("## "):
            break
        if in_success and re.match(r"^\d+\.", line.strip()):
            criteria_count += 1
    if in_success and criteria_count < 5:
        _add("blocking",
             f"Success Criteria has only {criteria_count} items (minimum 5 required).",
             "Add more success criteria items (at least 5 total).")

    return findings


def validate_anti_patterns_static(task_content: str, task_name: str) -> list[Finding]:
    """Statically detect anti-patterns in code blocks."""
    lines = task_content.splitlines()
    findings: list[Finding] = []
    in_code = False
    code_section = task_name

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            if line.startswith("## "):
                code_section = stripped
            continue

        fid = f"F-AP-{len(findings) + 1:03d}"
        if "dict.get(" in line and "None)" in line:
            findings.append(Finding(
                id=fid, severity="major", category="anti_pattern",
                location=code_section,
                description="dict.get(key, None) — must raise KeyError on missing keys.",
                evidence=stripped, suggested_fix="Use dict[key] instead.", rule_reference=None,
            ))
        if re.match(r".*except\s*:.*pass", line):
            findings.append(Finding(
                id=fid, severity="major", category="anti_pattern",
                location=code_section,
                description="except: pass — must log and re-raise.",
                evidence=stripped, suggested_fix="Handle specific exceptions, log, re-raise.",
                rule_reference=None,
            ))
        if stripped == "pass" or "# TODO" in line:
            findings.append(Finding(
                id=fid, severity="major", category="anti_pattern",
                location=code_section,
                description="Placeholder code (pass/TODO) — must implement completely.",
                evidence=stripped, suggested_fix="Replace with complete implementation.",
                rule_reference=None,
            ))
        if "MagicMock" in line or "SimpleNamespace" in line or "Mock(" in line:
            findings.append(Finding(
                id=fid, severity="major", category="anti_pattern",
                location=code_section,
                description="Mock/SimpleNamespace in tests — must use real objects.",
                evidence=stripped, suggested_fix="Replace with real objects per test guidelines.",
                rule_reference=None,
            ))

    return findings


def build_reviewer_prompt(
    task_path: Path,
    context: dict[str, str],
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
    model_name: str = "qwen2.5-coder:14b",
) -> str:
    """Build the LLM reviewer prompt for subjective checks only.

    Structure and anti-pattern checks are done deterministically in Python.
    The LLM only handles: ambiguity detection, module reference verification,
    and test coverage assessment.
    """
    prompt_template = prompt_template_path.read_text(encoding="utf-8")

    # Replace placeholders in template with actual values
    target_name = task_path.name
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prompt_template = prompt_template.replace("MODEL_PLACEHOLDER", model_name)
    prompt_template = prompt_template.replace("TARGET_PLACEHOLDER", target_name)
    prompt_template = prompt_template.replace("TIMESTAMP_PLACEHOLDER", timestamp)

    canonical_modules_formatted = format_canonical_modules_for_prompt(
        canonical_modules_digest
    )

    full_prompt = f"""## Task File to Review

**Path:** {task_path}

{context["task_content"]}

---

## Canonical Modules Reference

{canonical_modules_formatted}

---

{prompt_template}
"""
    return full_prompt


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
        generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
        verdict=data.get("verdict", "warnings_only"),
        findings=findings,
        summary=data.get("summary", "(no summary)"),
    )


def _compute_verdict(findings: list[Finding]) -> str:
    """Compute verdict from findings based on highest severity."""
    severities = {f.severity for f in findings}
    if "blocking" in severities:
        return "blocking"
    if "major" in severities:
        return "needs_fixes"
    if "minor" in severities:
        return "warnings_only"
    return "pass"


def review_task_with_retry(
    task_path: Path,
    context: dict[str, str],
    config: dict,
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
) -> ReviewResult:
    """Review a task: deterministic checks + LLM subjective checks."""
    task_content = context["task_content"]
    task_name = task_path.name
    primary_model = config["tier1"]["primary_model"]

    # Phase 1: Deterministic structural validation (no false positives)
    structure_findings = validate_task_structure(task_content, task_name)
    anti_pattern_findings = validate_anti_patterns_static(task_content, task_name)

    # Phase 2: LLM subjective checks (ambiguity, module refs, test coverage)
    llm_findings: list[Finding] = []
    prompt = build_reviewer_prompt(
        task_path, context, prompt_template_path, canonical_modules_digest,
        model_name=primary_model,
    )

    primary_timeout = config["tier1"].get("target_latency_seconds", 120)
    fallback_timeout = config["tier1"].get("fallback_latency_seconds", 180)

    llm_result_dict = None

    # Try primary model
    for attempt in range(1, 3):  # 2 attempts
        logger.info("tier1_attempt model=%s attempt=%d", primary_model, attempt)
        response = call_ollama(
            prompt,
            config["tier1"]["endpoint"],
            primary_model,
            timeout=primary_timeout,
        )

        if response:
            llm_result_dict = parse_model_response(response, primary_model)
            if llm_result_dict:
                break
            else:
                dump_raw_response(response, task_path, primary_model, attempt)

    # Fallback to secondary model if primary failed
    if not llm_result_dict:
        fallback_model = config["tier1"]["fallback_model"]
        logger.info("falling_back_to_model model=%s", fallback_model)
        fallback_prompt = build_reviewer_prompt(
            task_path, context, prompt_template_path, canonical_modules_digest,
            model_name=fallback_model,
        )
        response = call_ollama(
            fallback_prompt,
            config["tier1"]["endpoint"],
            fallback_model,
            timeout=fallback_timeout,
        )

        if response:
            llm_result_dict = parse_model_response(response, fallback_model)
            if not llm_result_dict:
                dump_raw_response(response, task_path, fallback_model, 1)

    # Extract LLM findings, filtering out "Required Sections" category
    # (those are handled deterministically above — LLM has false positives there)
    if llm_result_dict:
        raw_findings = llm_result_dict.get("findings", [])
        for f in raw_findings:
            if not isinstance(f, dict):
                continue
            category = f.get("category", "")
            # Skip structural findings from LLM — we handle those deterministically
            if "required" in category.lower() or "missing_section" in category.lower():
                continue
            if "missing_metadata" in category.lower():
                continue
            if "missing_success" in category.lower():
                continue
            # Normalize LLM category to valid Literal values
            raw_cat = f.get("category", "other").lower()
            if "anti" in raw_cat or "pattern" in raw_cat:
                norm_cat = "anti_pattern"
            elif "module" in raw_cat or "import" in raw_cat or "reference" in raw_cat:
                norm_cat = "broken_reference"
            elif "test" in raw_cat:
                norm_cat = "test_coverage"
            elif "ambig" in raw_cat or "vague" in raw_cat:
                norm_cat = "ambiguity"
            else:
                norm_cat = "other"

            llm_findings.append(Finding(
                id=f.get("id", f"F-LLM-{len(llm_findings) + 1:03d}"),
                severity=f.get("severity", "minor"),
                category=norm_cat,
                location=f.get("location", task_name),
                description=f.get("description", "(no description)"),
                evidence=f.get("evidence", ""),
                suggested_fix=f.get("suggested_fix", ""),
                rule_reference=f.get("rule_reference"),
            ))

    # Phase 3: Merge all findings and renumber sequentially
    from dataclasses import replace as _dc_replace
    all_findings = [
        _dc_replace(f, id=f"F-{i:03d}")
        for i, f in enumerate(
            structure_findings + anti_pattern_findings + llm_findings, 1
        )
    ]

    verdict = _compute_verdict(all_findings)
    model_used = primary_model
    if not llm_result_dict:
        logger.warning("llm_review_failed task=%s (deterministic checks only)", task_path)
        model_used = f"{primary_model} (deterministic only)"

    # Build summary
    summary_parts: list[str] = []
    if structure_findings:
        summary_parts.append(f"{len(structure_findings)} structural issue(s)")
    if anti_pattern_findings:
        summary_parts.append(f"{len(anti_pattern_findings)} anti-pattern(s)")
    if llm_findings:
        summary_parts.append(f"{len(llm_findings)} subjective issue(s) from LLM")
    summary = ". ".join(summary_parts) if summary_parts else "No issues found."

    return ReviewResult(
        schema_version="1.0",
        source="local",
        model=model_used,
        scope="task",
        target=task_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        verdict=verdict,
        findings=all_findings,
        summary=summary,
    )


def discover_phase_tasks(phase_num: int, config: dict) -> list[Path]:
    """Discover all task files for a given phase across all repos."""
    datrix_root = Path(config["paths"]["datrix_root"])
    tasks = []

    # Search all repos for .tasks/phase-{NN}/ directories
    for repo_dir in datrix_root.glob("datrix*"):
        phase_dir = repo_dir / f".tasks/phase-{phase_num:02d}"
        if phase_dir.exists():
            tasks.extend(phase_dir.glob("task-*.md"))

    return sorted(tasks)


def review_phase(
    phase_num: int,
    config: dict,
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
    verify_mode: bool = False,
) -> list[ReviewResult]:
    """Review all tasks in a phase sequentially."""
    tasks = discover_phase_tasks(phase_num, config)
    logger.info("discovered_tasks phase=%d count=%d", phase_num, len(tasks))

    results = []
    for task_path in tasks:
        # Skip if verify mode and no .review.applied.json marker
        if verify_mode:
            applied_marker = task_path.with_suffix(".review.applied.json")
            if not applied_marker.exists():
                logger.info("skipping_task_no_applied_marker task=%s", task_path)
                continue
            logger.info("verifying_task task=%s", task_path)

        context = resolve_task_context(task_path, config)
        result = review_task_with_retry(
            task_path, context, config, prompt_template_path, canonical_modules_digest
        )

        # Write artifact
        if verify_mode:
            output_path = task_path.with_suffix(".review.local.verified.json")
        else:
            output_path = task_path.with_suffix(".review.local.json")

        write_review_artifact(result, output_path)
        results.append(result)

    return results


def check_ollama_reachable(config: dict) -> bool:
    """Ping Ollama to verify it's reachable."""
    try:
        req = urllib.request.Request(f"{config['tier1']['endpoint']}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def write_review_artifact(result: ReviewResult, output_path: Path) -> None:
    """Write ReviewResult to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(review_result_to_dict(result), f, indent=2)
    logger.info("review_written path=%s", output_path)


def main() -> int:
    """Orchestrator entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Review task files")
    parser.add_argument("--task", type=Path, help="Review a single task file")
    parser.add_argument("--phase", type=int, help="Review all tasks in a phase")
    parser.add_argument(
        "--config", type=Path, default=Path("scripts/review/config.toml")
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Re-review tasks with .review.applied.json markers",
    )
    parser.add_argument(
        "--codex", action="store_true", help="Force Tier 2 (Codex) review"
    )
    parser.add_argument(
        "--codex-on-threshold",
        action="store_true",
        help="Escalate to Tier 2 if threshold breached",
    )
    parser.add_argument(
        "--codex-phase-gate",
        action="store_true",
        help="Run Tier 2 after Tier 1 as quality gate",
    )

    args = parser.parse_args()

    if not args.task and not args.phase:
        parser.error("Must specify --task or --phase")

    config = load_config(args.config)
    prompt_template_path = Path("scripts/review/prompts/local-reviewer.md")

    # Load canonical modules cache
    cache_path = Path(config["paths"]["canonical_modules_cache"])
    datrix_root = Path(config["paths"]["datrix_root"])
    canonical_modules_digest = load_or_build_cache(cache_path, datrix_root)
    logger.info("canonical_modules_loaded packages=%d", len(canonical_modules_digest))

    # Check Ollama reachable
    if not check_ollama_reachable(config):
        if args.codex or args.codex_on_threshold or args.codex_phase_gate:
            logger.warning("ollama_unreachable_skipping_tier1")
            print("Ollama unreachable. Skipping Tier 1.")
            # Tier 2 (Codex) is a separate reviewer and does not need Ollama.
            return 0
        else:
            logger.error("ollama_unreachable_no_fallback")
            print("ERROR: Ollama unreachable. Exiting.")
            return 3

    if args.task:
        logger.info("reviewing_single_task path=%s", args.task)
        context = resolve_task_context(args.task, config)
        result = review_task_with_retry(
            args.task, context, config, prompt_template_path, canonical_modules_digest
        )

        output_path = args.task.with_suffix(".review.local.json")
        write_review_artifact(result, output_path)

        print(f"Review complete: {output_path}")
        print(f"Verdict: {result.verdict}")
        if result.findings:
            print(f"Findings: {len(result.findings)}")
        return 0 if result.verdict in ("pass", "warnings_only") else 1

    if args.phase:
        logger.info("reviewing_phase phase=%d", args.phase)
        results = review_phase(
            args.phase,
            config,
            prompt_template_path,
            canonical_modules_digest,
            verify_mode=args.verify,
        )

        # Determine if Tier 2 should run
        manual_codex = args.codex
        should_run_tier2 = should_escalate_to_tier2(
            results, config, manual_override=manual_codex
        )

        if should_run_tier2:
            logger.info("tier2_escalation_triggered phase=%d", args.phase)

            # Collect Tier 1 artifacts
            phase_tasks = discover_phase_tasks(args.phase, config)
            tier1_artifacts = [
                task_path.with_suffix(".review.local.json")
                for task_path in phase_tasks
            ]

            tier2_result = invoke_tier2_codex(
                args.phase,
                phase_tasks,
                tier1_artifacts,
                canonical_modules_digest,
                config,
            )

            if tier2_result:
                print(f"\nTier 2 (Codex) Review Complete")
                print(f"Verdict: {tier2_result.verdict}")
                print(f"Additional findings: {len(tier2_result.findings)}")
            else:
                print("\nTier 2 review failed or rate-limited. See logs.")
        else:
            logger.info("tier2_skipped phase=%d", args.phase)

        # Summary
        blocking_count = sum(1 for r in results if r.verdict == "blocking")
        major_count = sum(
            1 for r in results if r.verdict in ("blocking", "needs_fixes")
        )
        parse_failure_count = sum(
            1
            for r in results
            if any(f.id == "F-000" and "failed to produce valid JSON" in f.description for f in r.findings)
        )

        print(f"\nPhase {args.phase} Review Complete (Tier 1)")
        print(f"Tasks reviewed: {len(results)}")
        print(f"Blocking issues: {blocking_count}")
        print(f"Major+ issues: {major_count}")
        if parse_failure_count > 0:
            print(f"Parse failures: {parse_failure_count}/{len(results)}")
            print("  Raw responses dumped to .review-debug/ directories for inspection.")

        if parse_failure_count == len(results) and len(results) > 0:
            print("\nWARNING: ALL tasks failed to parse. Review infrastructure issue.")
            return 2
        if blocking_count > 0:
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
