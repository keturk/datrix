#!/usr/bin/env python3
"""Build the apply-reviews worklist for a phase.

Mechanizes Steps 1-2 of the apply-reviews skill
(d:/datrix/.claude/skills/apply-reviews/SKILL.md):

- Discover Tier 1 artifacts ``*.review.local.json`` in every repo's
  ``.tasks/phase-{NN}/`` folder and the Tier 2 artifact
  ``<base>/.review/phase-{NN}.review.codex.json`` (the path tier2_codex.py
  writes to).
- Load findings using the field and enum definitions from review_schema.py
  (the single source of truth for the review JSON contract).
- Drop findings already applied: a local finding is dropped when its ID is in
  the sibling ``<task>.review.applied.json`` marker's ``applied_findings``;
  a codex (phase-level) finding is dropped when its ID appears in ANY of the
  phase's applied markers (codex finding IDs are phase-scoped and the skill
  marks them in each affected task's marker).
- Group by ``target``, sorted blocking -> major -> minor -> nit within each
  target.

Console output is minimal; the worklist JSON carries everything. Review
artifacts and task files are DATA — never modified here.

Usage:
  python scripts/library/review/apply_reviews_prep.py --phase 31
  python scripts/library/review/apply_reviews_prep.py --phase 31 --source local
  .\\scripts\\review\\apply-reviews-prep.ps1 -Phase 31 [-Source local|codex|all]
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import cast, get_args, get_type_hints

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import local script modules
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from review.review_schema import Finding
from shared.venv import get_datrix_root

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
OUTPUT_CATEGORY = "review"

EXIT_DONE = 0
EXIT_USAGE = 2

SOURCE_LOCAL = "local"
SOURCE_CODEX = "codex"
SOURCE_ALL = "all"

LOCAL_ARTIFACT_SUFFIX = ".review.local.json"
APPLIED_MARKER_SUFFIX = ".review.applied.json"
CODEX_ARTIFACT_TEMPLATE = "phase-{phase}.review.codex.json"
CODEX_REVIEW_DIRNAME = ".review"
TASK_FILE_SUFFIX = ".md"

# Field and enum definitions come from review_schema.Finding — the review JSON
# contract's single source of truth (Tier 1/2/3 all conform to it).
FINDING_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(Finding)
)
_FINDING_HINTS = get_type_hints(Finding)
VALID_SEVERITIES: frozenset[str] = frozenset(
    cast(tuple[str, ...], get_args(_FINDING_HINTS["severity"]))
)
SEVERITY_ORDER: dict[str, int] = {"blocking": 0, "major": 1, "minor": 2, "nit": 3}
_OPTIONAL_FINDING_FIELDS = frozenset({"rule_reference"})


def _severity_rank(severity: str) -> int:
    if severity not in SEVERITY_ORDER:
        raise ValueError(
            f"Unknown severity '{severity}'. Valid severities (from "
            f"review_schema.Finding): {sorted(VALID_SEVERITIES)}."
        )
    return SEVERITY_ORDER[severity]


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Review artifact {path} is not valid JSON ({exc}). Regenerate it "
            "with review.py or fix the file."
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"Review artifact {path} must contain a JSON object (the "
            "ReviewResult schema from review_schema.py)."
        )
    return cast(dict[str, object], raw)


def _parse_finding(item: object, artifact: Path, index: int) -> dict[str, object]:
    """Validate one finding against the review_schema.Finding field set."""
    context = f"{artifact}, findings[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{context}: each finding must be a JSON object.")
    data = cast(dict[str, object], item)
    finding: dict[str, object] = {}
    for name in FINDING_FIELD_NAMES:
        if name not in data:
            if name in _OPTIONAL_FINDING_FIELDS:
                finding[name] = None
                continue
            raise ValueError(
                f"{context}: missing required key '{name}'. Findings must carry "
                f"the review_schema.Finding fields: {list(FINDING_FIELD_NAMES)}."
            )
        finding[name] = data[name]
    severity = finding["severity"]
    if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
        raise ValueError(
            f"{context}: severity {severity!r} is invalid. Valid severities: "
            f"{sorted(VALID_SEVERITIES)}. Fix the artifact."
        )
    identifier = finding["id"]
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(f"{context}: 'id' must be a non-empty string.")
    return finding


def _parse_artifact(path: Path) -> tuple[str, str, list[dict[str, object]]]:
    """Return (target, source, findings) from one review artifact."""
    data = _load_json_object(path)
    target = data.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError(
            f"Review artifact {path}: 'target' must be a non-empty string "
            "(a task file name/path or 'phase-NN')."
        )
    source = data.get("source")
    if source not in (SOURCE_LOCAL, SOURCE_CODEX):
        raise ValueError(
            f"Review artifact {path}: 'source' must be 'local' or 'codex', "
            f"got {source!r}."
        )
    findings_value = data.get("findings")
    if not isinstance(findings_value, list):
        raise ValueError(
            f"Review artifact {path}: 'findings' must be a list (may be empty)."
        )
    findings = [
        _parse_finding(item, path, index) for index, item in enumerate(findings_value)
    ]
    return target, str(source), findings


def _load_applied_ids(marker: Path) -> frozenset[str]:
    data = _load_json_object(marker)
    applied = data.get("applied_findings")
    if not isinstance(applied, list) or not all(isinstance(x, str) for x in applied):
        raise ValueError(
            f"Applied marker {marker}: 'applied_findings' must be a list of "
            "finding IDs (see the apply-reviews skill's marker format)."
        )
    return frozenset(str(x) for x in applied)


def _phase_dirs(base_dir: Path, phase_label: str) -> list[Path]:
    dirs: list[Path] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("datrix"):
            continue
        phase_dir = child / ".tasks" / f"phase-{phase_label}"
        if phase_dir.is_dir():
            dirs.append(phase_dir)
    return dirs


def _discover_local_artifacts(base_dir: Path, phase_label: str) -> list[Path]:
    artifacts: list[Path] = []
    for phase_dir in _phase_dirs(base_dir, phase_label):
        artifacts.extend(sorted(phase_dir.glob(f"*{LOCAL_ARTIFACT_SUFFIX}")))
    return artifacts


def _discover_codex_artifact(base_dir: Path, phase_label: str) -> Path | None:
    candidate = (
        base_dir / CODEX_REVIEW_DIRNAME / CODEX_ARTIFACT_TEMPLATE.format(phase=phase_label)
    )
    return candidate if candidate.is_file() else None


def _all_applied_ids(base_dir: Path, phase_label: str) -> frozenset[str]:
    """Union of applied finding IDs across every marker of the phase."""
    applied: set[str] = set()
    for phase_dir in _phase_dirs(base_dir, phase_label):
        for marker in sorted(phase_dir.glob(f"*{APPLIED_MARKER_SUFFIX}")):
            applied.update(_load_applied_ids(marker))
    return frozenset(applied)


def _local_artifact_context(artifact: Path) -> tuple[Path, str | None]:
    """(applied marker path, task file path if it exists) for a local artifact."""
    stem = artifact.name[: -len(LOCAL_ARTIFACT_SUFFIX)]
    marker = artifact.with_name(stem + APPLIED_MARKER_SUFFIX)
    task_file = artifact.with_name(stem + TASK_FILE_SUFFIX)
    task_path = str(task_file.resolve()) if task_file.is_file() else None
    return marker, task_path


def _collect_local(
    artifacts: list[Path],
) -> tuple[list[dict[str, object]], int]:
    """Findings from Tier 1 artifacts, minus already-applied ones."""
    collected: list[dict[str, object]] = []
    skipped = 0
    for artifact in artifacts:
        target, source, findings = _parse_artifact(artifact)
        marker, task_path = _local_artifact_context(artifact)
        applied = _load_applied_ids(marker) if marker.is_file() else frozenset()
        for finding in findings:
            if finding["id"] in applied:
                skipped += 1
                continue
            finding["source"] = source
            finding["artifact"] = str(artifact.resolve())
            finding["target"] = target
            finding["task_path"] = task_path
            finding["applied_marker"] = str(marker.resolve()) if marker.is_file() else str(marker)
            collected.append(finding)
    return collected, skipped


def _collect_codex(
    artifact: Path, applied_anywhere: frozenset[str]
) -> tuple[list[dict[str, object]], int]:
    """Findings from the Tier 2 artifact, minus ones applied in any marker."""
    collected: list[dict[str, object]] = []
    skipped = 0
    target, source, findings = _parse_artifact(artifact)
    for finding in findings:
        if finding["id"] in applied_anywhere:
            skipped += 1
            continue
        finding["source"] = source
        finding["artifact"] = str(artifact.resolve())
        finding["target"] = target
        finding["task_path"] = None
        finding["applied_marker"] = None
        collected.append(finding)
    return collected, skipped


def _group_by_target(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for finding in findings:
        target = finding["target"]
        if not isinstance(target, str):  # unreachable: validated in _parse_artifact
            raise ValueError(f"Finding {finding['id']!r} has a non-string target.")
        grouped.setdefault(target, []).append(finding)
    targets: list[dict[str, object]] = []
    for target in sorted(grouped):
        ordered = sorted(
            grouped[target],
            key=lambda finding: (
                _severity_rank(str(finding["severity"])),
                str(finding["id"]),
            ),
        )
        targets.append({"target": target, "findings": ordered})
    return targets


def build_worklist(base_dir: Path, phase: int, source: str) -> dict[str, object]:
    """Assemble the worklist payload for apply-reviews."""
    phase_label = f"{phase:02d}"
    local_artifacts = (
        _discover_local_artifacts(base_dir, phase_label)
        if source in (SOURCE_LOCAL, SOURCE_ALL)
        else []
    )
    codex_artifact = (
        _discover_codex_artifact(base_dir, phase_label)
        if source in (SOURCE_CODEX, SOURCE_ALL)
        else None
    )

    findings, skipped = _collect_local(local_artifacts)
    if codex_artifact is not None:
        codex_findings, codex_skipped = _collect_codex(
            codex_artifact, _all_applied_ids(base_dir, phase_label)
        )
        findings.extend(codex_findings)
        skipped += codex_skipped

    artifacts = [str(path.resolve()) for path in local_artifacts]
    if codex_artifact is not None:
        artifacts.append(str(codex_artifact.resolve()))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "base_dir": str(base_dir),
        "source_filter": source,
        "artifacts": artifacts,
        "targets": _group_by_target(findings),
        "total": len(findings),
        "skipped_already_applied": skipped,
    }


def _write_output(payload: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the apply-reviews worklist for a phase"
    )
    parser.add_argument("--phase", type=int, required=True, help="Phase number (e.g. 31)")
    parser.add_argument(
        "--source",
        choices=(SOURCE_LOCAL, SOURCE_CODEX, SOURCE_ALL),
        default=SOURCE_ALL,
        help="Which review tier(s) to include (default: all)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Workspace root containing the datrix* repos (default: auto-detected)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <workspace>/.tmp/review/phase-NN-worklist.json)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    base_dir = args.base_dir if args.base_dir is not None else get_datrix_root()
    if not base_dir.is_dir():
        print(f"ERROR: Base directory does not exist: {base_dir}", file=sys.stderr)
        return EXIT_USAGE

    try:
        payload = build_worklist(base_dir, args.phase, args.source)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    phase_label = f"{args.phase:02d}"
    output_path = (
        args.output
        if args.output is not None
        else get_datrix_root() / ".tmp" / OUTPUT_CATEGORY / f"phase-{phase_label}-worklist.json"
    )
    _write_output(payload, output_path)

    artifacts = payload["artifacts"]
    targets = payload["targets"]
    artifact_count = len(artifacts) if isinstance(artifacts, list) else 0
    target_count = len(targets) if isinstance(targets, list) else 0
    if artifact_count == 0:
        print(
            "No review files found for phase %s (source=%s) under %s"
            % (phase_label, args.source, base_dir)
        )
    else:
        print(
            "Phase %s: %s findings across %s targets from %s artifact(s); "
            "skipped already-applied: %s"
            % (
                phase_label,
                payload["total"],
                target_count,
                artifact_count,
                payload["skipped_already_applied"],
            )
        )
    print(f"Details: {output_path.resolve()}")
    return EXIT_DONE


if __name__ == "__main__":
    sys.exit(main())
