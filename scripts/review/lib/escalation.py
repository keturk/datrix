"""Escalation logic for Tier 1 → Tier 2 decision."""

from __future__ import annotations

import logging
from typing import Final

from review_schema import ReviewResult

logger = logging.getLogger(__name__)

#: The ``[tier2] mode`` values (config.toml); ``--tier2-on-threshold`` / ``--tier2-phase-gate``
#: override the configured one for a run.
MODE_OFF: Final = "off"
MODE_MANUAL: Final = "manual"
MODE_THRESHOLD: Final = "threshold"
MODE_PHASE_GATE: Final = "phase-gate"


def should_escalate_to_tier2(
    tier1_results: list[ReviewResult],
    config: dict,
    manual_override: bool = False,
    mode_override: str | None = None,
) -> bool:
    """Determine if Tier 2 should run based on escalation mode and thresholds.

    Args:
        tier1_results: List of Tier 1 review results for the phase
        config: Configuration dict from config.toml
        manual_override: True if --tier2 was passed
        mode_override: The mode a --tier2-on-threshold / --tier2-phase-gate flag chose for this
            run, replacing ``[tier2] mode``; None keeps the configured mode

    Returns:
        True if Tier 2 should run, False otherwise
    """
    tier2_config = config.get("tier2", {})

    # Tier 2 disabled
    if not tier2_config.get("enabled", True):
        logger.info("tier2_disabled")
        return False

    # Manual override (--tier2 flag)
    if manual_override:
        logger.info("escalating_tier2 reason=manual_override")
        return True

    mode = mode_override or tier2_config.get("mode", MODE_OFF)

    if mode == MODE_OFF:
        logger.info("escalation_mode_off")
        return False

    if mode == MODE_MANUAL:
        # Manual mode requires an explicit --tier2 flag (handled by manual_override above)
        logger.info("escalation_mode_manual_no_override")
        return False

    if mode == MODE_THRESHOLD:
        return _threshold_breached(tier1_results, tier2_config)

    if mode == MODE_PHASE_GATE:
        # Phase-gate mode: always escalate (Tier 2 runs after apply+verify)
        logger.info("escalating_tier2 reason=phase_gate")
        return True

    logger.warning("unknown_escalation_mode mode=%s", mode)
    return False


def _threshold_breached(tier1_results: list[ReviewResult], tier2_config: dict) -> bool:
    """Escalate on any blocking finding, or on enough major+blocking findings combined."""
    threshold_blocking = tier2_config.get("threshold_blocking", 1)
    threshold_total_major = tier2_config.get("threshold_total_major", 5)

    blocking_count = sum(1 for r in tier1_results if r.verdict == "blocking")
    major_count = sum(1 for r in tier1_results if r.verdict in ("blocking", "needs_fixes"))

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
