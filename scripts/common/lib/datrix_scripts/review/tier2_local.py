"""Tier 2: a phase-scope review by a local model, over every task file and its Tier 1 review.

Tier 1 (``review.py``) reviews one task at a time. Tier 2 asks what only the whole phase shows
(``prompts/phase-reviewer.md``): dependency gaps between tasks, scope two tasks both claim,
design-reference coverage, and a canonical module a task re-creates. It runs on the larger local
models (``TIER2_MODELS``), sends ``[tier2] context_window`` as ``num_ctx``, and writes
``phase-NN.review.phase.json`` into the review artifacts folder, where ``apply-reviews-prep``
reads it (``-Source phase``).

A phase whose prompt does not fit the window is split by task: each part carries the canonical
digest and the instructions, and the parts' findings merge into one result.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings
from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.review.canonical_modules import format_canonical_modules_for_prompt
from datrix_scripts.review.review_reply import (
    REVIEW_ATTEMPTS,
    REVIEW_MAX_TOKENS,
    compute_verdict,
    dict_to_review_result,
    parse_model_response,
    request_review,
)
from datrix_scripts.review.review_schema import Finding, ReviewResult, review_result_to_dict

logger = logging.getLogger(__name__)

#: The models Tier 2 runs on, best first (installed on the review machines).
TIER2_MODELS: Final = ("nemotron-3-super:120b", "qwen3.6:35b")
PHASE_PROMPT_PATH: Final = SCRIPTS_DIR / "review" / "prompts" / "phase-reviewer.md"
PHASE_ARTIFACT_TEMPLATE: Final = "phase-{phase:02d}.review.phase.json"
PHASE_SOURCE: Final = "phase"
PHASE_SCOPE: Final = "phase"
PHASE_FINDING_PREFIX: Final = "P-"
#: A rough size of a token, to keep a prompt inside the window it is sent with.
CHARS_PER_TOKEN: Final = 4


class Tier2Unanswered(RuntimeError):
    """A tier-2 model answered, but never with a reply that parses as a review."""


@dataclass(frozen=True)
class PhaseContext:
    """What every part of one phase review carries besides its tasks."""

    phase_num: int
    canonical_digest: str
    instructions: str

    @property
    def target(self) -> str:
        return f"phase-{self.phase_num:02d}"


def phase_artifact_path(config: dict, phase_num: int) -> Path:
    return Path(config["paths"]["review_artifacts"]) / PHASE_ARTIFACT_TEMPLATE.format(phase=phase_num)


def task_section(task_path: Path, tier1: ReviewResult | None) -> str:
    """One task file, and its Tier 1 review when there is one."""
    review = (json.dumps(review_result_to_dict(tier1), indent=1) if tier1 is not None
              else "(no Tier 1 review of this task)")
    return (f"## Task file: {task_path.name}\n\n{task_path.read_text(encoding='utf-8')}\n\n"
            f"### Tier 1 review of {task_path.name}\n\n```json\n{review}\n```\n")


def _prompt(context: PhaseContext, sections: list[str], part: int, parts: int) -> str:
    title = f"# Phase {context.phase_num:02d}" + (f" (part {part} of {parts}: these tasks only)" if parts > 1 else "")
    return f"{title}\n\n{''.join(sections)}\n---\n\n{context.canonical_digest}\n\n---\n\n{context.instructions}\n"


def phase_prompts(context: PhaseContext, sections: list[str], budget_chars: int) -> list[str]:
    """The phase's prompts: one when it fits ``budget_chars``, else one per group of whole tasks.

    A single task larger than the budget still gets a part of its own: a task is never cut.
    """
    fixed = len(_prompt(context, [], 2, 2))
    groups: list[list[str]] = [[]]
    size = fixed
    for section in sections:
        if groups[-1] and size + len(section) > budget_chars:
            groups.append([])
            size = fixed
        groups[-1].append(section)
        size += len(section)
    return [_prompt(context, group, n, len(groups)) for n, group in enumerate(groups, start=1)]


def _review_part(prompt: str, pool: LocalLlmPool, context_window: int, target: str) -> ReviewResult:
    for attempt in range(1, REVIEW_ATTEMPTS + 1):
        reply = request_review(prompt, pool, context_window)
        data = parse_model_response(reply.text, reply.host.model)
        if data is not None:
            parsed = dict_to_review_result(data, Path(target))
            return replace(parsed, model=reply.host.model, source=PHASE_SOURCE, scope=PHASE_SCOPE, target=target)
        logger.warning("tier2_unparsed target=%s model=%s attempt=%d", target, reply.host.model, attempt)
    raise Tier2Unanswered(f"no tier-2 answer for {target} parsed as a review in {REVIEW_ATTEMPTS} attempts")


def merge_results(parts: list[ReviewResult], target: str) -> ReviewResult:
    """One phase result from its parts: every finding, renumbered, and the verdict they make.

    A phase finding is numbered ``P-NNN``, never ``F-NNN``: apply-reviews matches a phase
    finding against every task's applied marker of the phase, where ``F-NNN`` are task findings.
    """
    findings: list[Finding] = [
        replace(finding, id=f"{PHASE_FINDING_PREFIX}{n:03d}")
        for n, finding in enumerate((f for part in parts for f in part.findings), start=1)
    ]
    return ReviewResult(
        schema_version="1.0",
        source=PHASE_SOURCE,
        model=", ".join(dict.fromkeys(part.model for part in parts)),
        scope=PHASE_SCOPE,
        target=target,
        generated_at=datetime.now(UTC).isoformat(),
        verdict=compute_verdict(findings),
        findings=findings,
        summary=" ".join(part.summary for part in parts),
    )


def run_tier2(
    phase_num: int,
    phase_tasks: list[Path],
    tier1_results: list[ReviewResult],
    canonical_modules_digest: dict[str, list[str]],
    config: dict,
    settings: LocalLlmSettings,
) -> ReviewResult:
    """Review the phase on a tier-2 model and write ``phase-NN.review.phase.json``.

    Raises:
        LocalLlmUnavailable: No tier-2 model can answer.
        Tier2Unanswered: A tier-2 model answered, but never with a review.
    """
    context = PhaseContext(phase_num, format_canonical_modules_for_prompt(canonical_modules_digest),
                           PHASE_PROMPT_PATH.read_text(encoding="utf-8"))
    tier1_by_task = {result.target: result for result in tier1_results}
    sections = [task_section(task, tier1_by_task.get(task.name)) for task in phase_tasks]
    context_window = int(config["tier2"]["context_window"])
    budget_chars = (context_window - REVIEW_MAX_TOKENS) * CHARS_PER_TOKEN
    pool = LocalLlmPool(replace(settings, models=TIER2_MODELS))
    prompts = phase_prompts(context, sections, budget_chars)
    logger.info("tier2_phase_review phase=%d tasks=%d parts=%d", phase_num, len(phase_tasks), len(prompts))
    result = merge_results([_review_part(p, pool, context_window, context.target) for p in prompts], context.target)
    artifact = phase_artifact_path(config, phase_num)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(review_result_to_dict(result), indent=2), encoding="utf-8")
    logger.info("tier2_review_written path=%s", artifact)
    return result
