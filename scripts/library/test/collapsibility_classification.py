#!/usr/bin/env python3
"""Collapsibility-classification enforcement gate for the two parallel-implementation
drift classification files (language axis + platform axis).

`parallel_implementation_drift.py` MEASURES drift: it reports which function
names are defined divergently across >=2 registered target packages and nowhere
else, and ratchets the aggregate DRIFTED count down. `parallel-implementation-drift-
classification.json` then records, per drifted name, WHETHER the
divergence is legitimate (`status: intentional`/`tracked`) -- but answers neither "is
this collapsible" nor "by what mechanism". This module is the enforcement layer for
that missing second field (`collapsibility`): it does not compute drift itself (that
stays the drift scanner's sole surface, imported here rather than re-implemented -- a second
scanner would be a duplicated implementation inside the instrument that exists to find
duplicated implementations), it only asserts that every name the scanner currently
calls DRIFTED carries a schema-valid collapsibility verdict in its axis's
classification file.

**Two independent checks per axis, with different strictness:**
1. Hard, unconditional (once the axis's classification file exists): the file's
   entry COUNT equals the live drifted-name count exactly, and every entry carries
   a `status`. No ratchet -- these two either hold or the gate fails.
2. A decrease-only ratchet on the UNCLASSIFIED-COLLAPSIBILITY count: entries missing
   `collapsibility.mechanism`, carrying a mechanism outside the closed vocabulary, or
   (when `mechanism == "none"`) missing a `collapsibility.reason` distinct from the
   entry's own legitimacy `reason`. Ratcheted (not hard) so the gate is green the
   moment this module lands, even though 625 language-axis entries have no
   `collapsibility` field yet; each classification chunk decrements the ratchet by
   exactly the count it classifies.

**A classification file that does not exist yet is a violation only when the axis is
declared EXPECTED.** `EXPECTED_CLASSIFIED_AXES` is the declared set of axes whose
classification file must exist; an axis outside that set with no file yet is skipped
(logged, never failed) and its unclassified count is trivially 0. An axis INSIDE that
set with an absent file is a HARD violation -- this is what stops the enforcement from
being silenced by deleting its own input: without a declared expectation, "file absent"
and "axis not yet in scope" are indistinguishable, which is exactly the gap that let the
platform axis's classification file be optional right up until the change that created
it also added the platform axis to `EXPECTED_CLASSIFIED_AXES`.

Usage:
    python collapsibility_classification.py                        # languages
    python collapsibility_classification.py --axis platforms
    python collapsibility_classification.py --self-test             # non-vacuity only
    python collapsibility_classification.py --axis platforms --update-baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from test.parallel_implementation_drift import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    WORKSPACE_ROOT,
    discover_all_other_package_src_dirs,
    discover_target_package_src_dirs,
    find_parallel_implementations,
)
from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    registered_platform_names,
)

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/collapsibility_classification.py -- same
# depth as parallel_implementation_drift.py, so the same parents[N] math applies.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]

LANGUAGE_CLASSIFICATION_PATH: Path = DATRIX_DIR / "scripts" / "config" / "parallel-implementation-drift-classification.json"
PLATFORM_CLASSIFICATION_PATH: Path = DATRIX_DIR / "scripts" / "config" / "platform-implementation-drift-classification.json"
LANGUAGE_UNCLASSIFIED_BASELINE_PATH: Path = DATRIX_DIR / "scripts" / "config" / "collapsibility-unclassified-baseline.json"
PLATFORM_UNCLASSIFIED_BASELINE_PATH: Path = DATRIX_DIR / "scripts" / "config" / "platform-collapsibility-unclassified-baseline.json"

_AXIS_NAME_RESOLVERS: Final[dict[str, Callable[[], frozenset[str]]]] = {
    AXIS_LANGUAGES: registered_language_names,
    AXIS_PLATFORMS: registered_platform_names,
}
_AXIS_CLASSIFICATION_PATHS: Final[dict[str, Path]] = {
    AXIS_LANGUAGES: LANGUAGE_CLASSIFICATION_PATH,
    AXIS_PLATFORMS: PLATFORM_CLASSIFICATION_PATH,
}
_AXIS_UNCLASSIFIED_BASELINE_PATHS: Final[dict[str, Path]] = {
    AXIS_LANGUAGES: LANGUAGE_UNCLASSIFIED_BASELINE_PATH,
    AXIS_PLATFORMS: PLATFORM_UNCLASSIFIED_BASELINE_PATH,
}

#: Closed collapsibility-mechanism vocabulary -- the named consolidation mechanisms
#: identified across the language-axis reason families and the platform-axis
#: predicate worklist. "none" is a valid mechanism value meaning "not collapsible" --
#: it is the ONLY value that additionally requires a `collapsibility.reason` distinct
#: from the entry's legitimacy `reason`.
MECHANISM_NONE: Final[str] = "none"
COLLAPSIBILITY_MECHANISMS: Final[frozenset[str]] = frozenset(
    {
        "framework-shape-plan-module",
        "naming-profile-caser",
        "shared-jinja-macro",
        "shared-raise-site",
        "declared-dependency-table",
        "signature-alignment",
        "shared-vocabulary-per-language-map",
        "rename",
        "capability-gap-defect",
        "shared-predicate-hoist",
        MECHANISM_NONE,
    }
)

_STATUSES: Final[frozenset[str]] = frozenset({"intentional", "tracked"})

#: The declared set of axes whose classification file MUST exist. An absent file for
#: an axis in this set is a hard violation (`missing_expected_classification_file`),
#: never a silent skip -- this is what stops the enforcement from being disarmed by
#: simply deleting its own input. An axis NOT in this set (none currently -- both
#: registered axes are expected) is skipped, never failed, the same as before this
#: set existed. Adding a new axis's classification file must add it here in the same
#: change, or its absence would silently pass forever.
EXPECTED_CLASSIFIED_AXES: Final[frozenset[str]] = frozenset({AXIS_LANGUAGES, AXIS_PLATFORMS})

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

ViolationKind = Literal[
    "entry_count_mismatch",
    "missing_status",
    "missing_mechanism",
    "invalid_mechanism",
    "empty_none_reason",
    "duplicate_none_reason",
    "missing_expected_classification_file",
    "intentional_capability_gap",
]

#: The closed-vocabulary mechanism value meaning "this entry's divergence is an
#: emission or capability gap" -- the STRUCTURAL signal `check_no_intentional_
#: capability_gap` reads, never a keyword scan over the free-text `reason` field
#: (see that function's docstring for why a text scan is unsound on this file).
CAPABILITY_GAP_MECHANISM: Final[str] = "capability-gap-defect"

_SELF_TEST_NAME_VALID: Final[str] = "self_test_valid_entry"
_SELF_TEST_NAME_MISSING: Final[str] = "self_test_missing_collapsibility"
_SELF_TEST_NAME_DUPLICATE: Final[str] = "self_test_duplicate_reason_entry"
_SELF_TEST_NAME_INTENTIONAL_GAP: Final[str] = "self_test_intentional_capability_gap"
_SELF_TEST_AXIS_EXPECTED: Final[str] = "self_test_axis_expected"
_SELF_TEST_AXIS_UNEXPECTED: Final[str] = "self_test_axis_unexpected"
#: A synthetic expected-axes set, deliberately DISJOINT from the real
#: `EXPECTED_CLASSIFIED_AXES` (AXIS_LANGUAGES/AXIS_PLATFORMS) so the self-test proves
#: the axis-membership branch itself, independent of which real axes happen to be
#: expected today or in the future.
_SELF_TEST_EXPECTED_AXES: Final[frozenset[str]] = frozenset({_SELF_TEST_AXIS_EXPECTED})


@dataclass(frozen=True)
class CollapsibilityViolation:
    """One schema violation found for one classification entry.

    `message` always carries the repo's mandated four parts: what went wrong, what
    was expected, the valid options, and a fix suggestion -- built by
    `_four_part_message` so every violation kind is worded consistently.
    """

    name: str
    kind: ViolationKind
    message: str


def _four_part_message(what: str, expected: str, valid_options: str, fix: str) -> str:
    """Compose the repo-mandated four-part error/violation message.

    Args:
        what: What went wrong.
        expected: What was expected instead.
        valid_options: The valid values/shape.
        fix: A concrete fix suggestion.

    Returns:
        A single formatted message string.
    """
    return f"{what} Expected: {expected} Valid options: {valid_options} Fix: {fix}"


# ---------------------------------------------------------------------------
# Live drift + classification loading
# ---------------------------------------------------------------------------


def compute_live_drifted_names(axis: str) -> frozenset[str]:
    """Fresh live drifted-name set for *axis*, computed the same way
    `parallel_implementation_drift.main()` does. Never reads a baseline file --
    baselines ratchet a COUNT, they are not an authoritative name list.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.

    Returns:
        Every name the live scan classifies `verdict == "drifted"`.
    """
    target_names = _AXIS_NAME_RESOLVERS[axis]()
    target_src_dirs = discover_target_package_src_dirs(axis, target_names, WORKSPACE_ROOT)
    other_src_dirs = discover_all_other_package_src_dirs(WORKSPACE_ROOT, frozenset(target_src_dirs.values()))
    groups = find_parallel_implementations(target_src_dirs, other_src_dirs)
    return frozenset(g.name for g in groups if g.verdict == "drifted")


def load_classifications(path: Path) -> dict[str, dict[str, object]]:
    """Load a classification file's `classifications` map.

    Args:
        path: A classification JSON file (language or platform axis).

    Returns:
        `{}` if *path* does not exist yet (the axis has no classification file);
        otherwise the parsed `classifications` object.

    Raises:
        ValueError: If the file exists but its top-level shape is wrong.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    classifications = data.get("classifications")
    if not isinstance(classifications, dict):
        raise ValueError(
            _four_part_message(
                what=f"Malformed classification file {path}: top-level 'classifications' key is {type(classifications).__name__}, not an object.",
                expected="an object mapping each drifted name to its {status, reason, collapsibility} entry.",
                valid_options="{'_comment': [...], 'classifications': {name: {...}, ...}}",
                fix="regenerate the file via that axis's classification process (a per-name curation pass over a fresh drifted-name report) rather than hand-editing its top-level structure.",
            )
        )
    return classifications


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_entry_count_and_status(
    axis: str,
    classification_path: Path,
    classifications: dict[str, dict[str, object]],
    live_drifted_names: frozenset[str],
    *,
    expected_axes: frozenset[str] = EXPECTED_CLASSIFIED_AXES,
) -> list[CollapsibilityViolation]:
    """Hard checks 1 and 2 -- entry count equals the live drifted count, and every
    entry carries a valid `status`. When *classification_path* does not exist yet,
    the outcome depends on whether *axis* is declared in *expected_axes*: an
    UNEXPECTED axis is skipped (logged, never failed); an EXPECTED axis with no file
    is itself a hard violation, so deleting a required classification file cannot
    silently disarm this gate.

    Args:
        axis: The axis being checked, named in violation messages.
        classification_path: The file *classifications* was loaded from.
        classifications: The loaded classification map.
        live_drifted_names: The fresh live drifted-name set for *axis*.
        expected_axes: The declared set of axes whose classification file must
            exist. Defaults to the real `EXPECTED_CLASSIFIED_AXES`; the
            non-vacuity self-test overrides it with a synthetic set so it can
            prove both directions without touching real axis names or files.

    Returns:
        Violations found (empty if the file does not exist yet and *axis* is not
        expected, or if all checks pass).
    """
    if not classification_path.exists():
        if axis in expected_axes:
            return [
                CollapsibilityViolation(
                    name="<file>",
                    kind="missing_expected_classification_file",
                    message=_four_part_message(
                        what=f"axis={axis!r} is declared in EXPECTED_CLASSIFIED_AXES but its classification file {classification_path} does not exist.",
                        expected="a classification file present for every axis in EXPECTED_CLASSIFIED_AXES.",
                        valid_options=f"create {classification_path} (one entry per name in a fresh -Axis {axis} drifted-name report), or remove {axis!r} from EXPECTED_CLASSIFIED_AXES in the same change if this axis is being deliberately retired from collapsibility classification.",
                        fix=f"run the axis's classification task and commit the resulting file at {classification_path}; do not delete a classification file without also removing its axis from EXPECTED_CLASSIFIED_AXES.",
                    ),
                )
            ]
        logger.info(
            "axis=%s classification file %s does not exist yet and is not in EXPECTED_CLASSIFIED_AXES -- count/status checks skipped until it is created.",
            axis,
            classification_path,
        )
        return []

    violations: list[CollapsibilityViolation] = []
    if len(classifications) != len(live_drifted_names):
        violations.append(
            CollapsibilityViolation(
                name="<file>",
                kind="entry_count_mismatch",
                message=_four_part_message(
                    what=f"axis={axis}: classification file has {len(classifications)} entries but the live drifted count is {len(live_drifted_names)}.",
                    expected="entry count == live drifted_count exactly (hard equality, never a ratchet).",
                    valid_options=f"add missing entries or remove stale ones so the key set matches the live drifted-name set for axis={axis}.",
                    fix=f"run the axis's classification task / aggregator against a fresh `parallel-implementation-drift-gate.ps1 -Axis {axis} -Dbg` run and reconcile the diff.",
                ),
            )
        )
    for name, entry in classifications.items():
        status = entry.get("status")
        if status not in _STATUSES:
            violations.append(
                CollapsibilityViolation(
                    name=name,
                    kind="missing_status",
                    message=_four_part_message(
                        what=f"entry {name!r} has status={status!r}.",
                        expected="a `status` field.",
                        valid_options=str(sorted(_STATUSES)),
                        fix=f"set {name!r}'s `status` to 'intentional' or 'tracked'; either way give a `reason` -- for 'tracked', state the defect and name the target whose behaviour is the reference. Never record a task or design-doc identifier here: this file is committed, and those identifiers are not.",
                    ),
                )
            )
    return violations


def check_no_intentional_capability_gap(
    axis: str,
    classifications: dict[str, dict[str, object]],
) -> list[CollapsibilityViolation]:
    """Hard check -- an entry whose `collapsibility.mechanism` is the closed
    vocabulary's `"capability-gap-defect"` value may never carry
    `status: "intentional"`.

    Structural signal only: this never inspects the free-text `reason` field.
    `collapsibility.mechanism` is a deliberate, closed-vocabulary classification
    act (each per-chunk collapsibility-classification pass), unlike `reason`,
    which many genuinely legitimate entries word using the same vocabulary
    ("gap", "no equivalent") a keyword scan would false-positive on -- e.g. an
    entry can legitimately say a language "has no equivalent ... layer" while
    still being a permanent, intentional architecture difference rather than a
    defect. Reading `collapsibility.mechanism` instead sidesteps that ambiguity
    entirely: assigning `"capability-gap-defect"` is itself the classification
    decision, not a word choice in prose.

    Args:
        axis: The axis being checked, named in violation messages.
        classifications: The loaded classification map.

    Returns:
        One violation per offending entry.
    """
    violations: list[CollapsibilityViolation] = []
    for name, entry in classifications.items():
        collapsibility = entry.get("collapsibility")
        if not isinstance(collapsibility, dict):
            continue
        if collapsibility.get("mechanism") != CAPABILITY_GAP_MECHANISM:
            continue
        if entry.get("status") == "intentional":
            violations.append(
                CollapsibilityViolation(
                    name=name,
                    kind="intentional_capability_gap",
                    message=_four_part_message(
                        what=f"axis={axis}: entry {name!r} has collapsibility.mechanism="
                        f"{CAPABILITY_GAP_MECHANISM!r} but status='intentional'.",
                        expected="status='tracked' for any entry classified as a capability-gap defect.",
                        valid_options="status must be 'tracked' whenever mechanism is "
                        f"{CAPABILITY_GAP_MECHANISM!r}.",
                        fix=f"flip {name!r}'s status to 'tracked' with a reason naming the defect "
                        "and its reference language -- never 'intentional' for a known defect.",
                    ),
                )
            )
    return violations


def count_unclassified_collapsibility(
    classifications: dict[str, dict[str, object]],
) -> tuple[int, list[CollapsibilityViolation]]:
    """Checks 3 and 4 -- every entry carries a closed-vocabulary
    `collapsibility.mechanism`, and every `mechanism: "none"` entry carries a
    `collapsibility.reason` that is non-empty and distinct from the entry's own
    legitimacy `reason`.

    Args:
        classifications: The loaded classification map.

    Returns:
        `(unclassified_count, violations)` -- unclassified_count is the number of
        DISTINCT entry names carrying >=1 violation (the ratcheted quantity), never
        the raw violation count.
    """
    violations: list[CollapsibilityViolation] = []
    unclassified_names: set[str] = set()
    for name, entry in classifications.items():
        collapsibility = entry.get("collapsibility")
        if not isinstance(collapsibility, dict):
            violations.append(
                CollapsibilityViolation(
                    name=name,
                    kind="missing_mechanism",
                    message=_four_part_message(
                        what=f"entry {name!r} has no `collapsibility` object.",
                        expected="a `collapsibility` object with a `mechanism` field.",
                        valid_options=str(sorted(COLLAPSIBILITY_MECHANISMS)),
                        fix=f"add `collapsibility: {{mechanism: <one of the above>}}` to {name!r} (plus `reason` if mechanism is 'none').",
                    ),
                )
            )
            unclassified_names.add(name)
            continue
        mechanism = collapsibility.get("mechanism")
        if mechanism not in COLLAPSIBILITY_MECHANISMS:
            violations.append(
                CollapsibilityViolation(
                    name=name,
                    kind="invalid_mechanism",
                    message=_four_part_message(
                        what=f"entry {name!r} has collapsibility.mechanism={mechanism!r}.",
                        expected="a mechanism drawn from the closed vocabulary.",
                        valid_options=str(sorted(COLLAPSIBILITY_MECHANISMS)),
                        fix=f"set {name!r}'s collapsibility.mechanism to one of the valid options.",
                    ),
                )
            )
            unclassified_names.add(name)
            continue
        if mechanism == MECHANISM_NONE:
            collapsibility_reason = collapsibility.get("reason")
            legitimacy_reason = entry.get("reason")
            if not collapsibility_reason:
                violations.append(
                    CollapsibilityViolation(
                        name=name,
                        kind="empty_none_reason",
                        message=_four_part_message(
                            what=f"entry {name!r} has mechanism='none' with no collapsibility.reason.",
                            expected="a non-empty one-line collapsibility.reason.",
                            valid_options="any non-empty string distinct from the entry's legitimacy `reason`.",
                            fix=f"write a one-line reason on {name!r} explaining why NO mechanism collapses it.",
                        ),
                    )
                )
                unclassified_names.add(name)
            elif collapsibility_reason == legitimacy_reason:
                violations.append(
                    CollapsibilityViolation(
                        name=name,
                        kind="duplicate_none_reason",
                        message=_four_part_message(
                            what=f"entry {name!r}'s collapsibility.reason is string-identical to its legitimacy `reason`.",
                            expected="a collapsibility.reason answering a DIFFERENT question than the legitimacy reason (\"is this collapsible\" vs \"is this divergence legitimate\").",
                            valid_options="any non-empty string distinct from the legitimacy `reason`.",
                            fix=f"write a collapsibility-specific reason for {name!r}, not a copy of its legitimacy reason.",
                        ),
                    )
                )
                unclassified_names.add(name)
    return len(unclassified_names), violations


# ---------------------------------------------------------------------------
# Baseline (decrease-only ratchet on the unclassified-collapsibility count)
# ---------------------------------------------------------------------------


def load_unclassified_baseline(path: Path) -> int:
    """Load the decrease-only unclassified-collapsibility count baseline.

    Args:
        path: The baseline file for one axis.

    Returns:
        The recorded count, or 0 if the file does not exist yet.

    Raises:
        ValueError: If the file exists but is malformed.
    """
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    count = data.get("unclassified_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            _four_part_message(
                what=f"Malformed {path}: 'unclassified_count' is {count!r}.",
                expected="a non-negative integer 'unclassified_count' field.",
                valid_options="any integer >= 0.",
                fix="regenerate via `collapsibility-classification-gate.ps1 -UpdateBaseline`, never hand-edit.",
            )
        )
    return count


def write_unclassified_baseline(count: int, path: Path, axis: str) -> None:
    """Write *count* as the new unclassified-collapsibility baseline for *axis*.
    Called ONLY by `--update-baseline`.

    Args:
        count: The freshly computed unclassified-collapsibility count.
        path: The baseline file to write.
        axis: The axis this baseline belongs to, named in the file's comment.
    """
    payload = {
        "_comment": [
            "Decrease-only ratchet: the count of classification entries on the",
            f"datrix.{axis} axis that are NOT yet fully collapsibility-classified",
            "(missing collapsibility.mechanism, an invalid mechanism, or a",
            "mechanism:'none' entry with no reason / a reason duplicating its",
            "legitimacy reason). A live count HIGHER than this value fails --",
            "new unclassified entries appeared with nothing reconciling them.",
            "collapsibility-classification-gate.ps1 -UpdateBaseline is the only",
            "writer; do not hand-guess the number.",
        ],
        "unclassified_count": count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_unclassified_ratchet(current_count: int, baseline_count: int) -> str | None:
    """Compare the live unclassified-collapsibility count against the ratchet.

    Args:
        current_count: Freshly computed unclassified-collapsibility count.
        baseline_count: The pinned count.

    Returns:
        A failure message if `current_count > baseline_count`, else None.
    """
    if current_count > baseline_count:
        return (
            f"COLLAPSIBILITY-CLASSIFICATION REGRESSION: {current_count} entries "
            f"are unclassified for collapsibility, but the recorded baseline "
            f"expects at most {baseline_count}. New unclassified entries appeared "
            f"with nothing reconciling them -- classify them, or if reviewed and "
            f"intentional, re-run with --update-baseline."
        )
    return None


# ---------------------------------------------------------------------------
# Non-vacuity self-test: plant / observe / revert
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    if condition:
        print(f"[OK] {label}")
    else:
        print(f"[FAIL] {label}")
    return condition


def run_non_vacuity_self_test() -> bool:
    """Plant known-bad classification entries, observe the checks flag them with
    the exact expected count delta, then revert each and observe the count clear.
    A gate that cannot detect its own planted violation must not be trusted to
    detect a real one.

    Returns:
        True iff every assertion passed.
    """
    ok = True

    live_names = frozenset({_SELF_TEST_NAME_VALID, _SELF_TEST_NAME_MISSING})
    tmp_dir = Path(tempfile.mkdtemp(prefix="collapsibility-selftest-"))
    try:
        classification_path = tmp_dir / "classification.json"

        # PLANT: one entry short of the live count, and no status on it either.
        classification_path.write_text(
            json.dumps({"classifications": {_SELF_TEST_NAME_VALID: {}}}), encoding="utf-8"
        )
        classifications = load_classifications(classification_path)
        violations = check_entry_count_and_status(AXIS_LANGUAGES, classification_path, classifications, live_names)
        ok &= _assert(
            any(v.kind == "entry_count_mismatch" for v in violations),
            "planted short classification file is flagged entry_count_mismatch",
        )
        ok &= _assert(
            any(v.kind == "missing_status" for v in violations),
            "planted entry with no status is flagged missing_status",
        )

        # REVERT: complete the file to match the live count, with valid statuses.
        classification_path.write_text(
            json.dumps(
                {
                    "classifications": {
                        _SELF_TEST_NAME_VALID: {"status": "intentional", "reason": "r1"},
                        _SELF_TEST_NAME_MISSING: {"status": "intentional", "reason": "r2"},
                    }
                }
            ),
            encoding="utf-8",
        )
        classifications = load_classifications(classification_path)
        violations = check_entry_count_and_status(AXIS_LANGUAGES, classification_path, classifications, live_names)
        ok &= _assert(not violations, "reverted classification file clears both hard checks")

        # A NONEXISTENT file for an axis NOT in EXPECTED_CLASSIFIED_AXES must be
        # skipped, never failed, even against a nonzero live count.
        missing_path = tmp_dir / "does-not-exist.json"
        violations = check_entry_count_and_status(
            _SELF_TEST_AXIS_UNEXPECTED,
            missing_path,
            {},
            live_names,
            expected_axes=_SELF_TEST_EXPECTED_AXES,
        )
        ok &= _assert(
            not violations,
            "an UNEXPECTED axis's missing classification file is skipped, not failed",
        )

        # A NONEXISTENT file for an axis THAT IS in EXPECTED_CLASSIFIED_AXES must be
        # a hard failure -- the vacuity hole this self-test exists to close: deleting
        # a required classification file must not silently disarm the gate.
        still_expected_missing_path = tmp_dir / "expected-but-absent.json"
        violations = check_entry_count_and_status(
            _SELF_TEST_AXIS_EXPECTED,
            still_expected_missing_path,
            {},
            live_names,
            expected_axes=_SELF_TEST_EXPECTED_AXES,
        )
        ok &= _assert(
            any(v.kind == "missing_expected_classification_file" for v in violations),
            "an EXPECTED axis's missing classification file is flagged missing_expected_classification_file",
        )

        # -- unclassified-collapsibility ratchet checks --
        classifications = {
            _SELF_TEST_NAME_VALID: {
                "status": "intentional",
                "reason": "language-specific fact",
                "collapsibility": {"mechanism": "shared-jinja-macro"},
            },
            _SELF_TEST_NAME_MISSING: {"status": "intentional", "reason": "some reason"},
        }
        count_before, violations = count_unclassified_collapsibility(classifications)
        ok &= _assert(count_before == 1, "one entry missing collapsibility.mechanism -> unclassified count == 1")
        ok &= _assert(
            any(v.name == _SELF_TEST_NAME_MISSING and v.kind == "missing_mechanism" for v in violations),
            "the planted entry is named in the violation",
        )

        classifications[_SELF_TEST_NAME_MISSING]["collapsibility"] = {"mechanism": "rename"}
        count_after, violations = count_unclassified_collapsibility(classifications)
        ok &= _assert(count_after == count_before - 1 == 0, "reverting the planted entry clears the delta exactly")

        classifications[_SELF_TEST_NAME_DUPLICATE] = {
            "status": "intentional",
            "reason": "same text",
            "collapsibility": {"mechanism": MECHANISM_NONE, "reason": "same text"},
        }
        count_dup, violations = count_unclassified_collapsibility(classifications)
        ok &= _assert(count_dup == 1, "mechanism:'none' with a duplicate reason is flagged")
        ok &= _assert(
            any(v.kind == "duplicate_none_reason" for v in violations),
            "the duplicate-reason violation kind is reported",
        )

        classifications[_SELF_TEST_NAME_DUPLICATE]["collapsibility"]["reason"] = "a different, collapsibility-specific reason"
        count_clear, _violations = count_unclassified_collapsibility(classifications)
        ok &= _assert(count_clear == 0, "a distinct none-reason clears the violation")

        classifications[_SELF_TEST_NAME_DUPLICATE]["collapsibility"]["mechanism"] = "not-a-real-mechanism"
        count_invalid, violations = count_unclassified_collapsibility(classifications)
        ok &= _assert(count_invalid == 1, "a mechanism outside the closed vocabulary is rejected")
        ok &= _assert(
            any(v.kind == "invalid_mechanism" for v in violations),
            "the invalid-mechanism violation kind is reported",
        )

        # -- capability-gap-defect mechanism must never carry status: intentional --
        capability_gap_entry = {
            _SELF_TEST_NAME_INTENTIONAL_GAP: {
                "status": "intentional",
                "reason": "planted capability-gap fixture",
                "collapsibility": {"mechanism": CAPABILITY_GAP_MECHANISM},
            }
        }
        violations = check_no_intentional_capability_gap(AXIS_LANGUAGES, capability_gap_entry)
        ok &= _assert(
            any(v.name == _SELF_TEST_NAME_INTENTIONAL_GAP and v.kind == "intentional_capability_gap" for v in violations),
            "an intentional-status entry with mechanism=capability-gap-defect is flagged",
        )

        capability_gap_entry[_SELF_TEST_NAME_INTENTIONAL_GAP]["status"] = "tracked"
        violations = check_no_intentional_capability_gap(AXIS_LANGUAGES, capability_gap_entry)
        ok &= _assert(not violations, "flipping the planted entry's status to tracked clears the violation")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    ok &= _assert(check_unclassified_ratchet(5, 5) is None, "ratchet holds at equality")
    ok &= _assert(check_unclassified_ratchet(4, 5) is None, "ratchet holds on a decrease")
    ok &= _assert(check_unclassified_ratchet(6, 5) is not None, "ratchet fails on an increase")

    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point.

    Returns:
        0 (clean run, successful --update-baseline, or --self-test passed),
        1 (a hard violation or a ratchet regression), 2 (self-test failed or a
        discovery/parse error).
    """
    parser = argparse.ArgumentParser(
        description="Collapsibility-classification enforcement gate for the parallel-implementation drift classification files.",
    )
    parser.add_argument("--axis", choices=(AXIS_LANGUAGES, AXIS_PLATFORMS), default=AXIS_LANGUAGES)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")

    if not run_non_vacuity_self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real check is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    axis: str = args.axis
    classification_path = _AXIS_CLASSIFICATION_PATHS[axis]
    baseline_path = _AXIS_UNCLASSIFIED_BASELINE_PATHS[axis]

    try:
        live_drifted = compute_live_drifted_names(axis)
        classifications = load_classifications(classification_path)
    except (ValueError, ImportError, SyntaxError) as exc:
        logger.error("COLLAPSIBILITY GATE CANNOT RUN: %s", exc)
        return EXIT_USAGE

    hard_violations = [
        *check_entry_count_and_status(axis, classification_path, classifications, live_drifted),
        *check_no_intentional_capability_gap(axis, classifications),
    ]
    unclassified_count, soft_violations = count_unclassified_collapsibility(classifications)
    for violation in (*hard_violations, *soft_violations):
        logger.info("VIOLATION axis=%s kind=%s name=%s -- %s", axis, violation.kind, violation.name, violation.message)

    if args.update_baseline:
        write_unclassified_baseline(unclassified_count, baseline_path, axis)
        logger.info("Baseline updated: axis=%s unclassified_count=%d written to %s", axis, unclassified_count, baseline_path)
        return EXIT_OK

    if hard_violations:
        logger.error("%d hard collapsibility-schema violation(s) on axis=%s.", len(hard_violations), axis)
        return EXIT_FAIL

    baseline_count = load_unclassified_baseline(baseline_path)
    failure = check_unclassified_ratchet(unclassified_count, baseline_count)
    if failure:
        logger.error(failure)
        return EXIT_FAIL

    logger.info(
        "Collapsibility ratchet holds (axis=%s): %d unclassified <= baseline %d.",
        axis,
        unclassified_count,
        baseline_count,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
