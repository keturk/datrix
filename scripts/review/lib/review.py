#!/usr/bin/env python3
"""Task Review System Orchestrator.

Coordinates Tier 1 (one task at a time) and optional Tier 2 (the whole phase), both on local
models discovered on the network by datrix_scripts.local_llm, to review task files before
execution.

Usage (through the wrapper, which puts the shared scripts package on the path):
  .\\scripts\\review\\review.ps1 --phase 05
  .\\scripts\\review\\review.ps1 --task path/to/task.md
  .\\scripts\\review\\review.ps1 --phase 05 --tier2-phase-gate
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from canonical_modules import (
    format_canonical_modules_for_prompt,
    load_or_build_cache,
)
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from datrix_scripts.paths import SCRIPTS_DIR
from escalation import MODE_PHASE_GATE, MODE_THRESHOLD, should_escalate_to_tier2
from review_reply import (
    REVIEW_ATTEMPTS,
    REVIEW_GENERATE_TIMEOUT_MS,
    compute_verdict,
    parse_model_response,
    request_review,
)
from review_schema import Finding, ReviewResult, review_result_to_dict
from tier2_local import Tier2Unanswered, phase_artifact_path, run_tier2

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """Load config.toml. Raises if file missing or malformed."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("rb") as f:
        return tomllib.load(f)


# Exit codes. Only EXIT_CLEAN means a complete review found nothing blocking; every
# review that did not fully happen exits non-zero so it can never pass as a clean one.
EXIT_CLEAN = 0
EXIT_BLOCKING = 1
EXIT_ALL_PARSE_FAILED = 2
EXIT_NO_LOCAL_MODEL = 3
EXIT_TIER2_MISSING = 4


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
    model_name: str,
) -> str:
    """Build the LLM reviewer prompt for subjective checks only.

    Structure and anti-pattern checks are done deterministically in Python.
    The LLM only handles: ambiguity detection, module reference verification,
    and test coverage assessment.
    """
    prompt_template = prompt_template_path.read_text(encoding="utf-8")

    # Replace placeholders in template with actual values
    target_name = task_path.name
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def review_task_with_retry(
    task_path: Path,
    context: dict[str, str],
    config: dict,
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
    pool: LocalLlmPool,
) -> ReviewResult:
    """Review a task: deterministic checks + LLM subjective checks.

    Raises LocalLlmUnavailable when no local server can answer.
    """
    task_content = context["task_content"]
    task_name = task_path.name
    context_window = config["tier1"]["context_window"]

    # Phase 1: Deterministic structural validation (no false positives)
    structure_findings = validate_task_structure(task_content, task_name)
    anti_pattern_findings = validate_anti_patterns_static(task_content, task_name)

    # Phase 2: LLM subjective checks (ambiguity, module refs, test coverage)
    llm_findings: list[Finding] = []
    llm_result_dict = None
    model_used = pool.activate().model

    for attempt in range(1, REVIEW_ATTEMPTS + 1):
        # The prompt names the model it expects to answer, so it is rebuilt for
        # whichever model the pool is on now -- a failover can change it.
        model_used = pool.activate().model
        prompt = build_reviewer_prompt(
            task_path, context, prompt_template_path, canonical_modules_digest,
            model_name=model_used,
        )
        logger.info("tier1_attempt model=%s attempt=%d", model_used, attempt)
        reply = request_review(prompt, pool, context_window)
        model_used = reply.host.model
        llm_result_dict = parse_model_response(reply.text, model_used)
        if llm_result_dict:
            break
        dump_raw_response(reply.text, task_path, model_used, attempt)

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

    verdict = compute_verdict(all_findings)
    if not llm_result_dict:
        logger.warning("llm_review_failed task=%s (deterministic checks only)", task_path)
        model_used = f"{model_used} (deterministic only)"

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
        generated_at=datetime.now(UTC).isoformat(),
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
    pool: LocalLlmPool,
    verify_mode: bool = False,
) -> list[ReviewResult]:
    """Review all tasks in a phase sequentially.

    Raises LocalLlmUnavailable when no local server can answer.
    """
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
            task_path, context, config, prompt_template_path, canonical_modules_digest, pool
        )

        # Write artifact
        if verify_mode:
            output_path = task_path.with_suffix(".review.local.verified.json")
        else:
            output_path = task_path.with_suffix(".review.local.json")

        write_review_artifact(result, output_path)
        results.append(result)

    return results


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
        "--config", type=Path, default=SCRIPTS_DIR / "review" / "config.toml"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Re-review tasks with .review.applied.json markers",
    )
    parser.add_argument(
        "--tier2", action="store_true", help="Force the Tier 2 (phase) review"
    )
    tier2_mode = parser.add_mutually_exclusive_group()
    tier2_mode.add_argument(
        "--tier2-on-threshold",
        action="store_const",
        dest="tier2_mode",
        const=MODE_THRESHOLD,
        help="Escalate to Tier 2 if the config.toml [tier2] thresholds are breached",
    )
    tier2_mode.add_argument(
        "--tier2-phase-gate",
        action="store_const",
        dest="tier2_mode",
        const=MODE_PHASE_GATE,
        help="Run Tier 2 after Tier 1 as a quality gate",
    )
    add_local_llm_arguments(parser, generate_timeout_ms=REVIEW_GENERATE_TIMEOUT_MS)

    args = parser.parse_args()

    if not args.task and not args.phase:
        parser.error("Must specify --task or --phase")

    config = load_config(args.config)
    prompt_template_path = SCRIPTS_DIR / "review" / "prompts" / "local-reviewer.md"

    # Load canonical modules cache
    cache_path = Path(config["paths"]["canonical_modules_cache"])
    datrix_root = Path(config["paths"]["datrix_root"])
    canonical_modules_digest = load_or_build_cache(cache_path, datrix_root)
    logger.info("canonical_modules_loaded packages=%d", len(canonical_modules_digest))

    return run_review(args, config, prompt_template_path, canonical_modules_digest, local_llm_settings(args))


def run_review(
    args: argparse.Namespace,
    config: dict,
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
    settings: LocalLlmSettings,
) -> int:
    """Run the review ``args`` asks for on the servers ``settings`` names; return its exit code."""
    pool = LocalLlmPool(settings)
    try:
        return _run_review(args, config, prompt_template_path, canonical_modules_digest, pool, settings)
    except LocalLlmUnavailable as exc:
        # Tier 2 reviews Tier 1's artifacts, so without Tier 1 neither tier runs -- a
        # --tier2 flag does not make a review happen, and exit 0 would read as a clean one.
        logger.error("local_llm_unavailable_no_review error=%s", exc)
        print(f"ERROR: No local model server can answer, so no review ran (Tier 2 reviews Tier 1's "
              f"output and cannot run without it). {exc}")
        return EXIT_NO_LOCAL_MODEL


def _run_review(
    args: argparse.Namespace,
    config: dict,
    prompt_template_path: Path,
    canonical_modules_digest: dict[str, list[str]],
    pool: LocalLlmPool,
    settings: LocalLlmSettings,
) -> int:
    """Run Tier 1 (and Tier 2 when due). Raises LocalLlmUnavailable when no server can answer."""
    # Tier 1 needs a model before any task is read: fail here, not after the first task.
    pool.activate()

    if args.task:
        logger.info("reviewing_single_task path=%s", args.task)
        context = resolve_task_context(args.task, config)
        result = review_task_with_retry(
            args.task, context, config, prompt_template_path, canonical_modules_digest, pool
        )

        output_path = args.task.with_suffix(".review.local.json")
        write_review_artifact(result, output_path)

        print(f"Review complete: {output_path}")
        print(f"Verdict: {result.verdict}")
        if result.findings:
            print(f"Findings: {len(result.findings)}")
        return EXIT_CLEAN if result.verdict in ("pass", "warnings_only") else EXIT_BLOCKING

    if args.phase:
        logger.info("reviewing_phase phase=%d", args.phase)
        results = review_phase(
            args.phase,
            config,
            prompt_template_path,
            canonical_modules_digest,
            pool,
            verify_mode=args.verify,
        )

        # Determine if Tier 2 should run
        should_run_tier2 = should_escalate_to_tier2(
            results, config, manual_override=args.tier2, mode_override=args.tier2_mode
        )
        tier2_missing = False

        if should_run_tier2:
            logger.info("tier2_escalation_triggered phase=%d", args.phase)
            phase_tasks = discover_phase_tasks(args.phase, config)
            try:
                tier2_result = run_tier2(args.phase, phase_tasks, results, canonical_modules_digest, config,
                                         settings)
                print("\nTier 2 (phase) Review Complete")
                print(f"Verdict: {tier2_result.verdict}")
                print(f"Additional findings: {len(tier2_result.findings)}")
                print(f"Written: {phase_artifact_path(config, args.phase)}")
            except (LocalLlmUnavailable, Tier2Unanswered) as exc:
                print(f"\nERROR: Tier 2 was due but no phase review was produced, so the phase review is "
                      f"incomplete: {exc}")
                tier2_missing = True
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
            return EXIT_ALL_PARSE_FAILED
        if blocking_count > 0:
            return EXIT_BLOCKING
        if tier2_missing:
            return EXIT_TIER2_MISSING
        return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
