"""Tier 2 (Codex CLI) integration for phase-scope review."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

try:
    from review_schema import ReviewResult, Finding
except ImportError:
    from .review_schema import ReviewResult, Finding

logger = logging.getLogger(__name__)


def dict_to_review_result(data: dict, target_path: Path) -> ReviewResult:
    """Convert JSON dict to ReviewResult instance.

    Args:
        data: JSON dict from review artifact
        target_path: Path object for the target (used as fallback for target field)

    Returns:
        ReviewResult instance

    Raises:
        KeyError: If required fields missing in data
        ValueError: If field values invalid
    """
    findings = []
    for f_data in data.get("findings", []):
        finding = Finding(
            id=f_data["id"],
            severity=f_data["severity"],
            category=f_data["category"],
            location=f_data["location"],
            description=f_data["description"],
            evidence=f_data["evidence"],
            suggested_fix=f_data["suggested_fix"],
            rule_reference=f_data.get("rule_reference"),
        )
        findings.append(finding)

    return ReviewResult(
        schema_version=data.get("schema_version", "1.0"),
        source=data["source"],
        model=data["model"],
        scope=data["scope"],
        target=data.get("target", str(target_path)),
        generated_at=data["generated_at"],
        verdict=data["verdict"],
        findings=findings,
        summary=data["summary"],
    )


def invoke_tier2_codex(
    phase_num: int,
    phase_tasks: list[Path],
    tier1_artifacts: list[Path],
    canonical_modules_digest: dict[str, list[str]],
    config: dict,
) -> ReviewResult | None:
    """Invoke Codex CLI for Tier 2 phase review.

    Args:
        phase_num: Phase number to review
        phase_tasks: List of task file paths in the phase
        tier1_artifacts: List of Tier 1 review artifact paths
        canonical_modules_digest: Canonical modules from all repos
        config: Configuration dict from config.toml

    Returns:
        ReviewResult or None if Codex invocation fails
    """
    review_artifacts_dir = Path(config["paths"]["review_artifacts"])
    context_dir = review_artifacts_dir / f"phase-{phase_num:02d}-context"
    context_dir.mkdir(parents=True, exist_ok=True)

    # Write task files list
    tasks_list_file = context_dir / "tasks.txt"
    with tasks_list_file.open("w", encoding="utf-8") as f:
        for task_path in phase_tasks:
            f.write(f"{task_path}\n")

    # Write Tier 1 artifacts list
    tier1_list_file = context_dir / "tier1-artifacts.txt"
    with tier1_list_file.open("w", encoding="utf-8") as f:
        for artifact_path in tier1_artifacts:
            f.write(f"{artifact_path}\n")

    # Write canonical modules digest
    modules_file = context_dir / "canonical-modules.json"
    with modules_file.open("w", encoding="utf-8") as f:
        json.dump(canonical_modules_digest, f, indent=2)

    # Invoke Codex CLI
    tier2_config = config.get("tier2", {})
    codex_cmd = tier2_config.get("codex_command", "codex")
    skill_name = tier2_config.get("skill_name", "review-tasks")

    logger.info(
        "invoking_codex phase=%d context_dir=%s",
        phase_num,
        context_dir,
    )

    try:
        result = subprocess.run(
            [
                codex_cmd,
                "exec",
                "--skill",
                skill_name,
                "--args",
                f"phase={phase_num},context_dir={context_dir}",
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
        )

        if result.returncode != 0:
            if "rate limit" in result.stderr.lower() or "quota" in result.stderr.lower():
                logger.error("codex_rate_limited phase=%d", phase_num)
                print(
                    f"\nCodex rate limit reached. "
                    f"Tier 1 artifacts available at: {review_artifacts_dir}"
                )
                return None
            else:
                logger.error(
                    "codex_failed returncode=%d stderr=%s",
                    result.returncode,
                    result.stderr,
                )
                return None

    except subprocess.TimeoutExpired:
        logger.error("codex_timeout phase=%d", phase_num)
        return None
    except FileNotFoundError:
        logger.error("codex_not_found command=%s", codex_cmd)
        print(
            f"\nERROR: Codex CLI not found. "
            f"Install from: https://github.com/anthropics/codex-cli"
        )
        return None

    # Read Codex output
    output_path = review_artifacts_dir / f"phase-{phase_num:02d}.review.codex.json"
    if not output_path.exists():
        logger.error("codex_output_missing path=%s", output_path)
        return None

    try:
        with output_path.open("r", encoding="utf-8") as f:
            codex_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("codex_output_invalid path=%s error=%s", output_path, e)
        return None

    return dict_to_review_result(codex_data, Path(f"phase-{phase_num:02d}"))
