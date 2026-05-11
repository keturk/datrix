"""Escalation logic for Tier 1 → Tier 2 decision."""

from __future__ import annotations

import logging

try:
    from review_schema import ReviewResult
except ImportError:
    from .review_schema import ReviewResult

logger = logging.getLogger(__name__)


def should_escalate_to_tier2(
    tier1_results: list[ReviewResult],
    config: dict,
    manual_override: bool = False,
) -> bool:
    """Determine if Tier 2 should run based on escalation mode and thresholds.

    Args:
        tier1_results: List of Tier 1 review results for the phase
        config: Configuration dict from config.toml
        manual_override: True if --codex flag was passed

    Returns:
        True if Tier 2 should run, False otherwise
    """
    tier2_config = config.get("tier2", {})

    # Tier 2 disabled
    if not tier2_config.get("enabled", True):
        logger.info("tier2_disabled")
        return False

    # Manual override (--codex flag)
    if manual_override:
        logger.info("escalating_tier2 reason=manual_override")
        return True

    mode = tier2_config.get("mode", "off")

    if mode == "off":
        logger.info("escalation_mode_off")
        return False

    if mode == "manual":
        # Manual mode requires explicit --codex flag (handled by manual_override above)
        logger.info("escalation_mode_manual_no_override")
        return False

    if mode == "threshold":
        # Escalate if:
        # - Any blocking finding, OR
        # - Total major+blocking findings >= threshold
        threshold_blocking = tier2_config.get("threshold_blocking", 1)
        threshold_total_major = tier2_config.get("threshold_total_major", 5)

        blocking_count = sum(1 for r in tier1_results if r.verdict == "blocking")
        major_count = sum(
            1
            for r in tier1_results
            if r.verdict in ("blocking", "needs_fixes")
        )

        if blocking_count >= threshold_blocking:
            logger.info(
                "escalating_tier2 reason=threshold_blocking count=%d threshold=%d",
                blocking_count,
                threshold_blocking,
            )
            return True

        if major_count >= threshold_total_major:
            logger.info(
                "escalating_tier2 reason=threshold_major count=%d threshold=%d",
                major_count,
                threshold_total_major,
            )
            return True

        logger.info(
            "no_escalation blocking=%d major=%d thresholds=(%d,%d)",
            blocking_count,
            major_count,
            threshold_blocking,
            threshold_total_major,
        )
        return False

    if mode == "phase-gate":
        # Phase-gate mode: always escalate (Tier 2 runs after apply+verify)
        logger.info("escalating_tier2 reason=phase_gate")
        return True

    logger.warning("unknown_escalation_mode mode=%s", mode)
    return False
