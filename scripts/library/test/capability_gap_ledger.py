"""Capability gap ledger census, decrease-only two-directional pin, and the
standing check that catches a gap every registered target of an axis shares.

Every target package (language, client target, platform) carries its own gaps as
``CapabilityGap(surface, detail)`` rows on its own capability declaration -- there
is no separate committed ledger file, the declarations ARE the ledger. This gate
censuses them from the installed entry points, compares the live row count (total
and per target) with the pin in ``scripts/config/capability-gap-baseline.toml`` in
BOTH directions, and fails a surface that every registered implementation of one
axis carries a row for: such a surface is a defect in the shared layer, never a
per-target gap.

A row suppresses nothing. This gate never reads a row to set anything aside; it
counts the ledger and bounds it. The row count is printed on every run.

Target sets are NEVER hardcoded: languages, client targets and platforms are
enumerated from the installed ``datrix.languages`` / ``datrix.generators`` /
``datrix.platforms`` entry points at run time
(:mod:`shared.registered_targets`). Registered names that share ONE on-disk
implementation (two platforms served by one package) fold into a single
implementation, so the two-implementations-per-axis floor and the shared-layer
comparison count distinct implementations, never raw entry-point names.

Runs a built-in non-vacuity self-test on every invocation before trusting any
real census. Exit codes: 0 = ledger matches the pin and no shared-layer defect,
1 = ratchet or shared-layer violation, 2 = self-test failed, fewer than two
implementations on an axis, or an unreadable baseline.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import logging
import sys
import tomllib
from pathlib import Path
from typing import Final

# This file lives at library/test/; shared/ is the sibling library/shared/.
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    DATRIX_DIR,
    WORKSPACE_ROOT,
    discover_client_target_generator_src_dirs,
    discover_target_package_src_dirs,
    registered_client_target_generator_names,
    registered_language_names,
    registered_platform_names,
)

from datrix_common.plugin.capability_gap import CapabilityGap  # noqa: E402
from datrix_common.plugin.capability_resolution import (  # noqa: E402
    declaration_for_language,
    declaration_for_provider,
)
from datrix_common.plugin.registry import PluginRegistry  # noqa: E402

logger = logging.getLogger(__name__)

AXIS_CLIENT_TARGETS: Final[str] = "client_targets"
_AXES: Final[tuple[str, ...]] = (AXIS_LANGUAGES, AXIS_CLIENT_TARGETS, AXIS_PLATFORMS)
_MIN_IMPLEMENTATIONS_PER_AXIS: Final[int] = 2
_LABEL_JOIN_SEPARATOR: Final[str] = "+"
BASELINE_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "capability-gap-baseline.toml"
_BASELINE_TOTAL_KEY: Final[str] = "total"
_BASELINE_PER_TARGET_KEY: Final[str] = "per_target"
_BASELINE_KEYS: Final[frozenset[str]] = frozenset({_BASELINE_TOTAL_KEY, _BASELINE_PER_TARGET_KEY})

EXIT_OK: Final[int] = 0
EXIT_VIOLATION: Final[int] = 1
EXIT_CANNOT_RUN: Final[int] = 2

#: axis -> implementation label -> the registered names that implementation serves.
ImplementationGroups = dict[str, dict[str, tuple[str, ...]]]
#: axis -> registered name -> that target's own gap rows.
DeclaredGaps = dict[str, dict[str, tuple[CapabilityGap, ...]]]


@dataclasses.dataclass(frozen=True)
class GapRow:
    """One target's capability gap, as censused from its live declaration."""

    axis: str
    target: str
    surface: str
    detail: str


@dataclasses.dataclass(frozen=True)
class GapBaseline:
    """The pinned ledger size: the total and its per-axis, per-target split."""

    total: int
    per_target: dict[str, dict[str, int]]


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


def discover_implementation_groups() -> ImplementationGroups:
    """Resolve every registered target on all three axes to its implementation group.

    Raises:
        ValueError: The groups do not partition exactly the registered names of an axis.
    """
    registered = {
        AXIS_LANGUAGES: registered_language_names(),
        AXIS_CLIENT_TARGETS: registered_client_target_generator_names(),
        AXIS_PLATFORMS: registered_platform_names(),
    }
    folded = {
        AXIS_LANGUAGES: discover_target_package_src_dirs(
            AXIS_LANGUAGES, registered[AXIS_LANGUAGES], WORKSPACE_ROOT
        ),
        AXIS_CLIENT_TARGETS: discover_client_target_generator_src_dirs(
            registered[AXIS_CLIENT_TARGETS], WORKSPACE_ROOT
        ),
        AXIS_PLATFORMS: discover_target_package_src_dirs(
            AXIS_PLATFORMS, registered[AXIS_PLATFORMS], WORKSPACE_ROOT
        ),
    }
    groups: ImplementationGroups = {
        axis: {label: tuple(label.split(_LABEL_JOIN_SEPARATOR)) for label in by_label}
        for axis, by_label in folded.items()
    }
    for axis, by_label in groups.items():
        members = frozenset(name for names in by_label.values() for name in names)
        if members != registered[axis]:
            raise ValueError(
                f"Implementation groups for axis {axis!r} cover {sorted(members)} but "
                f"{sorted(registered[axis])} are registered. Fix: align "
                "shared.registered_targets' folding with the installed entry points."
            )
    return groups


def load_declared_gaps(groups: ImplementationGroups) -> DeclaredGaps:
    """Read ``capability_gaps`` off every registered target's live declaration."""
    client_registry = PluginRegistry()
    readers = {
        AXIS_LANGUAGES: lambda name: declaration_for_language(name).capability_gaps,
        AXIS_CLIENT_TARGETS: lambda name: client_registry.get_client_target_capabilities(name).capability_gaps,
        AXIS_PLATFORMS: lambda name: declaration_for_provider(name).capability_gaps,
    }
    return {
        axis: {name: readers[axis](name) for names in by_label.values() for name in names}
        for axis, by_label in groups.items()
    }


def census_gap_rows(declared: DeclaredGaps) -> list[GapRow]:
    """Flatten every target's gap rows, in a stable (axis, target, surface) order."""
    rows = [
        GapRow(axis=axis, target=name, surface=gap.surface, detail=gap.detail)
        for axis, by_name in declared.items()
        for name, gaps in by_name.items()
        for gap in gaps
    ]
    return sorted(rows, key=lambda row: (row.axis, row.target, row.surface))


def floor_problems(groups: ImplementationGroups) -> list[str]:
    """Every axis must hold at least two distinct implementations, else the shared-layer
    comparison is vacuous."""
    problems: list[str] = []
    for axis in _AXES:
        implementations = sorted(groups.get(axis, {}))
        if len(implementations) < _MIN_IMPLEMENTATIONS_PER_AXIS:
            problems.append(
                f"axis {axis!r} has {len(implementations)} distinct implementation(s) "
                f"{implementations}; {_MIN_IMPLEMENTATIONS_PER_AXIS} are required for the "
                "shared-layer comparison to mean anything. Fix: install the missing "
                "datrix-codegen-<x> package(s) into D:\\datrix\\.venv."
            )
    return problems


# ---------------------------------------------------------------------------
# Baseline and two-directional ratchet
# ---------------------------------------------------------------------------


def _require_count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{where} must be a non-negative integer, got {value!r}. "
            "Fix: write the live row count, e.g. 3."
        )
    return value


def parse_baseline(text: str) -> GapBaseline:
    """Parse and validate the baseline TOML text.

    Raises:
        ValueError: Malformed TOML, an unrecognized key or axis, a negative or non-integer
            count, or a ``total`` that is not the sum of the per-target counts.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"capability-gap baseline is not valid TOML: {error}") from error
    unknown = sorted(set(data) - _BASELINE_KEYS)
    if unknown or _BASELINE_TOTAL_KEY not in data:
        raise ValueError(
            f"capability-gap baseline keys {sorted(data)} must be exactly "
            f"{sorted(_BASELINE_KEYS)} (unrecognized: {unknown}). Fix: keep 'total' and "
            "a [per_target.<axis>] table per axis that carries rows."
        )
    total = _require_count(data[_BASELINE_TOTAL_KEY], "total")
    raw_split = data.get(_BASELINE_PER_TARGET_KEY, {})
    if not isinstance(raw_split, dict):
        raise ValueError("per_target must be a table of per-axis tables.")
    per_target: dict[str, dict[str, int]] = {}
    for axis, targets in raw_split.items():
        if axis not in _AXES or not isinstance(targets, dict):
            raise ValueError(
                f"per_target.{axis} is not a recognized axis table. Valid axes: {list(_AXES)}."
            )
        per_target[axis] = {
            name: _require_count(count, f"per_target.{axis}.{name}") for name, count in targets.items()
        }
    split_sum = sum(count for targets in per_target.values() for count in targets.values())
    if split_sum != total:
        raise ValueError(
            f"capability-gap baseline total={total} but the per-target counts sum to "
            f"{split_sum}. Fix: make 'total' the sum of the per-target counts."
        )
    return GapBaseline(total=total, per_target=per_target)


def load_baseline(path: Path = BASELINE_PATH) -> GapBaseline:
    """Load the pinned total and per-target split from *path*.

    Raises:
        ValueError: Missing file or any :func:`parse_baseline` failure.
    """
    if not path.is_file():
        raise ValueError(f"capability-gap baseline not found at {path}. Fix: seed it from a live census.")
    return parse_baseline(path.read_text(encoding="utf-8"))


def _compare_count(label: str, live: int, pinned: int) -> list[str]:
    if live > pinned:
        return [
            f"RATCHET UP {label}: live={live} > pin={pinned}. A gap row was added. Fix: "
            "realize the capability and remove the row; the pin only ever decreases."
        ]
    if live < pinned:
        return [
            f"RATCHET DOWN {label}: live={live} < pin={pinned}. Rows were removed without "
            f"lowering the pin. Fix: set the pin to {live} in capability-gap-baseline.toml "
            "in the same change."
        ]
    return []


def evaluate_ratchet(rows: list[GapRow], baseline: GapBaseline) -> list[str]:
    """Two-directional: the live total and each target's live count must equal the pin.

    More rows than pinned is a new gap; fewer rows than pinned is a pin that was not
    lowered with the fix. A target absent from the pin is pinned at zero.
    """
    live_by_target = collections.Counter((row.axis, row.target) for row in rows)
    pinned_by_target = {
        (axis, name): count for axis, targets in baseline.per_target.items() for name, count in targets.items()
    }
    problems = _compare_count("total", len(rows), baseline.total)
    for axis, name in sorted(set(live_by_target) | set(pinned_by_target)):
        problems += _compare_count(
            f"{axis}.{name}", live_by_target.get((axis, name), 0), pinned_by_target.get((axis, name), 0)
        )
    return problems


# ---------------------------------------------------------------------------
# Shared-layer standing check
# ---------------------------------------------------------------------------

_SHARED_LAYER_SHAPES: Final[str] = (
    "(1) a builtin group obligated on the wrong axis, (2) a config surface with no "
    "consumer, (3) an obligation that should not exist at all"
)


def find_shared_layer_defects(rows: list[GapRow], groups: ImplementationGroups) -> list[str]:
    """A surface every distinct implementation of one axis carries a row for.

    An implementation carries a surface when any registered name it serves does. When
    every implementation of an axis carries it, the capability is not missing from the
    targets, it is mis-obligated in the shared layer.
    """
    declaring: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    label_of = {
        (axis, name): label for axis, by_label in groups.items() for label, names in by_label.items() for name in names
    }
    for row in rows:
        declaring[(row.axis, row.surface)].add(label_of[(row.axis, row.target)])
    problems: list[str] = []
    for (axis, surface), labels in sorted(declaring.items()):
        if labels == set(groups[axis]):
            problems.append(
                f"SHARED-LAYER DEFECT axis={axis} surface={surface}: every implementation "
                f"{sorted(labels)} carries a gap row for it. That is a defect in the shared "
                f"layer, not in the targets. Known shapes: {_SHARED_LAYER_SHAPES}. Fix: "
                "correct the obligation in the shared layer and delete every row."
            )
    return problems


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SYNTHETIC_GROUPS: Final[ImplementationGroups] = {
    AXIS_LANGUAGES: {"alpha": ("alpha",), "beta": ("beta",)},
    AXIS_CLIENT_TARGETS: {"gamma": ("gamma",), "delta": ("delta",)},
    AXIS_PLATFORMS: {"eps": ("eps",), "zeta+eta": ("eta", "zeta")},
}


def _row(axis: str, target: str, surface: str) -> GapRow:
    return GapRow(axis=axis, target=target, surface=surface, detail="planted")


def _synthetic_rows() -> list[GapRow]:
    return [
        _row(AXIS_LANGUAGES, "alpha", "builtin_group:one"),
        _row(AXIS_LANGUAGES, "alpha", "builtin_group:two"),
        _row(AXIS_PLATFORMS, "eta", "config:one"),
    ]


_SYNTHETIC_BASELINE_TEXT: Final[str] = (
    "total = 3\n[per_target.languages]\nalpha = 2\n[per_target.platforms]\neta = 1\n"
)


def _self_test_checks() -> list[tuple[str, bool]]:
    rows = _synthetic_rows()
    baseline = parse_baseline(_SYNTHETIC_BASELINE_TEXT)
    over = dataclasses.replace(baseline, total=baseline.total - 1)
    under = dataclasses.replace(baseline, total=baseline.total + 1)
    skewed = GapBaseline(
        total=3, per_target={AXIS_LANGUAGES: {"alpha": 1}, AXIS_PLATFORMS: {"eta": 2}}
    )
    unpinned_row = rows + [_row(AXIS_CLIENT_TARGETS, "gamma", "push:one")]
    shared = [
        _row(AXIS_LANGUAGES, "alpha", "builtin_group:shared"),
        _row(AXIS_LANGUAGES, "beta", "builtin_group:shared"),
    ]
    folded_partial = [_row(AXIS_PLATFORMS, "eps", "config:x"), _row(AXIS_PLATFORMS, "eta", "config:x")]
    folded_all = folded_partial + [_row(AXIS_PLATFORMS, "zeta", "config:y")]
    single_axis_groups = {**_SYNTHETIC_GROUPS, AXIS_PLATFORMS: {"only+one": ("one", "only")}}
    return [
        ("over-count against the pin (live above pin) is a ratchet violation",
         bool(evaluate_ratchet(rows, over))),
        ("unpinned under-count (live below pin) is a ratchet violation",
         bool(evaluate_ratchet(rows, under))),
        ("same total with a different per-target split is a ratchet violation",
         bool(evaluate_ratchet(rows, skewed))),
        ("a row on a target absent from the pin is a ratchet violation",
         bool(evaluate_ratchet(unpinned_row, baseline))),
        ("a surface every target of a 2-target synthetic axis carries is a shared-layer defect",
         len(find_shared_layer_defects(shared, _SYNTHETIC_GROUPS)) == 1),
        ("a surface carried by only some implementations is not a shared-layer defect",
         not find_shared_layer_defects(rows + folded_partial[:1], _SYNTHETIC_GROUPS)),
        ("a folded implementation counts once: eps plus the folded pair carrying one surface is a defect",
         len(find_shared_layer_defects(folded_partial, _SYNTHETIC_GROUPS)) == 1),
        ("a surface on the folded pair alone is not a defect",
         not find_shared_layer_defects(folded_all[2:], _SYNTHETIC_GROUPS)),
        ("a matching census and pin report zero ratchet violations",
         not evaluate_ratchet(rows, baseline)),
        ("a matching census reports zero shared-layer defects",
         not find_shared_layer_defects(rows, _SYNTHETIC_GROUPS)),
        ("two registered names folded into one implementation breach the two-implementation floor",
         bool(floor_problems(single_axis_groups))),
        ("two implementations on every axis satisfy the floor",
         not floor_problems(_SYNTHETIC_GROUPS)),
        ("a baseline whose total is not the per-target sum is refused",
         _raises_value_error("total = 5\n[per_target.languages]\nalpha = 2\n")),
        ("a baseline with an unrecognized key is refused",
         _raises_value_error("total = 0\nextra = 1\n")),
        ("a baseline with a negative count is refused",
         _raises_value_error("total = -1\n")),
        ("census flattens declared gaps into one row per gap",
         len(census_gap_rows({AXIS_LANGUAGES: {"alpha": (CapabilityGap("domain:one", "planted"),)}})) == 1),
    ]


def _raises_value_error(text: str) -> bool:
    try:
        parse_baseline(text)
    except ValueError:
        return True
    return False


def run_self_test() -> list[str]:
    """Plant every violation shape and the clean case; return the failed expectations."""
    failures: list[str] = []
    for description, passed in _self_test_checks():
        if passed:
            logger.info("[OK] %s", description)
        else:
            failures.append(description)
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _log_census(rows: list[GapRow], groups: ImplementationGroups) -> None:
    for row in rows:
        logger.debug("ROW axis=%s target=%s surface=%s detail=%s", row.axis, row.target, row.surface, row.detail)
    counts = collections.Counter((row.axis, row.target) for row in rows)
    split = {f"{axis}.{target}": count for (axis, target), count in sorted(counts.items())}
    logger.info(
        "Capability gap ledger: %d row(s) across %d implementation(s); per target: %s",
        len(rows),
        sum(len(by_label) for by_label in groups.values()),
        split if split else "(none)",
    )


def run_gate(baseline_path: Path) -> int:
    """Census the live declarations and apply the ratchet and the shared-layer check."""
    try:
        baseline = load_baseline(baseline_path)
        groups = discover_implementation_groups()
    except ValueError as error:
        logger.error("LEDGER GATE CANNOT RUN: %s", error)
        return EXIT_CANNOT_RUN
    floor = floor_problems(groups)
    if floor:
        for problem in floor:
            logger.error("LEDGER GATE CANNOT RUN: %s", problem)
        return EXIT_CANNOT_RUN
    rows = census_gap_rows(load_declared_gaps(groups))
    _log_census(rows, groups)
    problems = evaluate_ratchet(rows, baseline) + find_shared_layer_defects(rows, groups)
    for problem in problems:
        logger.error("%s", problem)
    if problems:
        return EXIT_VIOLATION
    logger.info("Ledger holds: %d row(s) equal the pin and no surface is carried by every implementation.", len(rows))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        0 = ledger matches the pin with no shared-layer defect, 1 = violation,
        2 = self-test failed, an axis has fewer than two implementations, or the baseline
        is unreadable.
    """
    parser = argparse.ArgumentParser(
        description="Census every registered target's capability gap rows, pin them in both "
        "directions, and fail a surface every implementation of an axis carries."
    )
    parser.add_argument("--debug", action="store_true", help="Print every censused row")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test")
    parser.add_argument(
        "--baseline", type=Path, default=BASELINE_PATH, help="Baseline TOML to compare against"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")

    failures = run_self_test()
    if failures:
        for failure in failures:
            logger.error("SELF-TEST FAILED: %s", failure)
        return EXIT_CANNOT_RUN
    logger.info("Non-vacuity self-test passed.")
    if args.self_test:
        return EXIT_OK
    return run_gate(args.baseline)


if __name__ == "__main__":
    sys.exit(main())
