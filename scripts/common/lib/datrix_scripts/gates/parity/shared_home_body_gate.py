#!/usr/bin/env python3
"""Shared-home body gate: no function outside a shared home may carry the
body of a shared-home function.

A function with a shared home has exactly one definition. The homes are
``datrix_codegen_common``, ``datrix_codegen_kernel`` and ``datrix_common``. A
private copy elsewhere is usually a renamed one, so equality is measured on a
normalized AST rather than on names or text:

- the function's own name, decorators, annotations and docstring are dropped;
- every parameter and every locally bound name becomes a positional token;
- every constant collapses to its type name;
- attribute names, keyword-argument names and the names of non-local call
  targets are KEPT -- two functions that read different attributes or call
  different functions never compare equal.

A function qualifies at ``MIN_BODY_LINES`` lines and ``MIN_BODY_NODES`` AST
nodes (measured on the docstring-free body), which removes Protocol ``...``
stubs and one-line accessors. A function in package P is a hit when its
normalized body equals that of a home function -- public or private -- in a
package other than P. The verdict is a decrease-only per-package count pinned in
``scripts/config/shared-home-body-baseline.toml``: an increase fails, a
decrease passes. The self-test runs first on every invocation.

Usage (through the wrapper, ``scripts/gates/parity/shared-home-body-gate.ps1``):
    shared-home-body-gate.ps1 -SelfTest
    shared-home-body-gate.ps1 [-Hits] [-Symbol name[,name...]] [-Dbg]
    shared-home-body-gate.ps1 -UpdateBaseline
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.behaviour_skeleton import SkeletonError
from datrix_scripts.body_digest import (
    MIN_BODY_LINES,
    MIN_BODY_NODES,
    NormalizedFunction,
    measure_body,
    normalized_digest,
    qualifying_functions,
)
from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.function_sources import collect_function_sources
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.parity.gate_entry import ParityGate, gate_parser
from datrix_scripts.registered_targets import (
    DATRIX_DIR,
    WORKSPACE_ROOT,
    discover_all_package_locations,
)

logger = logging.getLogger(__name__)

GATE: Final = "shared-home-body"
WRAPPER: Final = "shared-home-body-gate"
MODULE: Final = "datrix_scripts.gates.parity.shared_home_body_gate"

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The packages whose functions are the shared homes (import names).
HOME_PACKAGES: Final[frozenset[str]] = frozenset(
    {"datrix_codegen_common", "datrix_codegen_kernel", "datrix_common"}
)

BASELINE_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "shared-home-body-baseline.toml"
_BASELINE_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"package", "count", "seed", "reason"})
_BASELINE_TABLE_KEY: Final[str] = "baseline"
SEED_REASON: Final[str] = (
    "Seeded from this gate's first measurement: private copies of a shared-home function that a "
    "consolidation change has not yet removed. The count only ever drops; it is never raised."
)
_BASELINE_HEADER: Final[str] = (
    "# Decrease-only per-package pin of shared-home duplicate bodies\n"
    "# (datrix_scripts.gates.parity.shared_home_body_gate, wrapped by scripts/gates/parity/shared-home-body-gate.ps1).\n"
    "#\n"
    "# `count` is the number of functions in `package` (an import name) whose normalized body equals\n"
    "# the body of a function in another package's shared home. A live count ABOVE `count`\n"
    "# fails the gate; a count below it passes and is lowered with -UpdateBaseline. A package with no\n"
    "# entry is pinned at 0. `seed` is the first measurement and never changes: the closing check\n"
    "# proves every package's count strictly below its seed. Every entry carries a written `reason`;\n"
    "# -UpdateBaseline reads it back and re-emits it.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   package = "datrix_codegen_python"\n'
    "#   count = <int>\n"
    "#   seed = <int>\n"
    '#   reason = "what the remaining duplicates are and why they remain"\n'
)

HIT_LINE_PREFIX: Final[str] = "SHARED-HOME BODY HIT:"

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class GateError(Exception):
    """The gate cannot produce a trustworthy verdict (unreadable baseline,
    unparseable source, missing home package). Never caught and silenced."""


class BaselineRiseError(GateError):
    """``--update-baseline`` was asked to raise a pinned count."""


# ---------------------------------------------------------------------------
# Comparison (normalization and enumeration: datrix_scripts.body_digest and
# datrix_scripts.function_sources)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BodyHit:
    """A function (``copy``) whose body equals a home function's."""

    copy: NormalizedFunction
    home: NormalizedFunction


def find_hits(
    functions_by_package: Mapping[str, Sequence[NormalizedFunction]],
    home_packages: frozenset[str] = HOME_PACKAGES,
) -> list[BodyHit]:
    """Every function whose digest equals a home function's digest where the
    home function lives in a different package.

    A private home function counts as much as a public one: a copy of either
    is the same fact in two homes, and the copy should call the home (made
    public when another package needs it) instead.
    """
    homes_by_digest: dict[str, list[NormalizedFunction]] = defaultdict(list)
    for package in sorted(home_packages & set(functions_by_package)):
        for function in functions_by_package[package]:
            homes_by_digest[function.digest].append(function)
    hits: list[BodyHit] = []
    for package in sorted(functions_by_package):
        for function in functions_by_package[package]:
            hits.extend(
                BodyHit(copy=function, home=home)
                for home in homes_by_digest.get(function.digest, ())
                if home.package != package
            )
    return hits


def count_by_package(hits: Sequence[BodyHit]) -> dict[str, int]:
    """Distinct copy functions per package (a copy matching two homes counts once)."""
    copies: dict[str, set[tuple[Path, int]]] = defaultdict(set)
    for hit in hits:
        copies[hit.copy.package].add(hit.copy.identity)
    return {package: len(identities) for package, identities in sorted(copies.items())}


def measure(workspace_root: Path) -> list[BodyHit]:
    """Scan every ``datrix-*`` package's ``src/`` under *workspace_root*.

    Raises:
        GateError: A home package is not on disk (the gate would be vacuous).
        SkeletonError: A source file cannot be parsed -- propagated, never skipped.
    """
    locations = discover_all_package_locations(workspace_root)
    absent = sorted(HOME_PACKAGES - set(locations))
    if absent:
        raise GateError(
            f"Home package(s) {absent} not found under {workspace_root}; discovered packages: "
            f"{sorted(locations)}. Fix: check out the missing repo(s) or run the gate from the workspace root."
        )
    functions_by_package = {
        package: qualifying_functions(collect_function_sources(src_dir, package))
        for package, src_dir in sorted(locations.items())
    }
    return find_hits(functions_by_package)


def hit_line(hit: BodyHit, workspace_root: Path) -> str:
    copy_path = hit.copy.file_path.relative_to(workspace_root).as_posix()
    home_path = hit.home.file_path.relative_to(workspace_root).as_posix()
    return (
        f"{HIT_LINE_PREFIX} {hit.copy.package}: {copy_path}:{hit.copy.line_number} {hit.copy.qualified_name} "
        f"== {hit.home.package}: {home_path}:{hit.home.line_number} {hit.home.qualified_name}"
    )


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PackageBaseline:
    """One package's pin, its first measurement and the written reason."""

    count: int
    seed: int
    reason: str


def _require_count(value: object, where: str, key: str) -> int:
    if type(value) is not int or value < 0:
        raise GateError(
            f"{where}: {key} must be a non-negative integer; got {value!r}. "
            f"Fix: write the live count measured by the gate."
        )
    return value


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, PackageBaseline]:
    """Load and strictly validate the baseline.

    Raises:
        GateError: The file is missing, is not valid TOML, has a top-level key
            other than ``baseline``, an entry with a missing or unrecognized key,
            a duplicate package, a negative/non-integer count, ``count > seed``
            or an empty ``reason`` -- naming the file and the offender.
    """
    raw = _read_baseline_toml(path)
    entries: dict[str, PackageBaseline] = {}
    for index, entry in enumerate(raw.get(_BASELINE_TABLE_KEY, [])):
        package, baseline = _baseline_entry(entry, f"{path}: [[{_BASELINE_TABLE_KEY}]] entry {index}", entries)
        entries[package] = baseline
    return entries


def _read_baseline_toml(path: Path) -> dict[str, object]:
    """The baseline file's TOML table, refusing an unreadable file or an unknown top-level key."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateError(
            f"Cannot read the baseline {path} ({exc}). Fix: seed it with "
            f"`shared-home-body-gate.ps1 -UpdateBaseline`."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise GateError(f"{path} is not valid TOML ({exc}). Fix: correct the syntax.") from exc
    unknown = sorted(set(raw) - {_BASELINE_TABLE_KEY})
    if unknown:
        raise GateError(f"{path}: unrecognized top-level key(s) {unknown}; expected only [[{_BASELINE_TABLE_KEY}]].")
    return raw


def _baseline_entry(
    entry: object, where: str, entries: Mapping[str, PackageBaseline]
) -> tuple[str, PackageBaseline]:
    """One validated ``[[baseline]]`` entry (see ``load_baseline`` for what is refused)."""
    if not isinstance(entry, dict) or set(entry) != _BASELINE_ENTRY_KEYS:
        raise GateError(
            f"{where} must carry exactly {sorted(_BASELINE_ENTRY_KEYS)}; got "
            f"{sorted(entry) if isinstance(entry, dict) else entry!r}. Fix: add or remove the key(s)."
        )
    package = entry["package"]
    reason = entry["reason"]
    if not isinstance(package, str) or not package:
        raise GateError(f"{where}: package must be a non-empty import name; got {package!r}.")
    if package in entries:
        raise GateError(f"{where}: package {package!r} appears twice. Fix: keep one entry per package.")
    if not isinstance(reason, str) or not reason.strip():
        raise GateError(f"{where} ({package}): reason is empty. Fix: write what the remaining duplicates are.")
    count = _require_count(entry["count"], where, "count")
    seed = _require_count(entry["seed"], where, "seed")
    if count > seed:
        raise GateError(
            f"{where} ({package}): count {count} exceeds seed {seed}. Fix: a count above the first "
            f"measurement means a copy was added; remove it instead of raising the pin."
        )
    return package, PackageBaseline(count=count, seed=seed, reason=reason)


def write_baseline(path: Path, entries: Mapping[str, PackageBaseline]) -> None:
    """Write *entries* sorted by package; the reason is a TOML basic string."""
    lines = [_BASELINE_HEADER]
    for package, entry in sorted(entries.items()):
        lines.append(f"\n[[{_BASELINE_TABLE_KEY}]]\n")
        lines.append(f'package = "{package}"\n')
        lines.append(f"count = {entry.count}\n")
        lines.append(f"seed = {entry.seed}\n")
        lines.append(f"reason = {json.dumps(entry.reason)}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def updated_baseline(
    counts: Mapping[str, int], previous: Mapping[str, PackageBaseline] | None
) -> dict[str, PackageBaseline]:
    """The baseline ``--update-baseline`` writes: a seed when *previous* is
    ``None``, otherwise every count lowered to the live value.

    Raises:
        BaselineRiseError: A live count is above its pin.
    """
    if previous is None:
        return {
            package: PackageBaseline(count=count, seed=count, reason=SEED_REASON)
            for package, count in sorted(counts.items())
            if count > 0
        }
    risen = sorted(
        package for package, count in counts.items() if count > (previous[package].count if package in previous else 0)
    )
    if risen:
        raise BaselineRiseError(
            f"Refusing to raise the pin of {risen}: live counts {[counts[p] for p in risen]} are above the pinned "
            f"{[previous[p].count if p in previous else 0 for p in risen]}. Fix: delete the copies the gate "
            f"lists (-Hits); a pin is never raised."
        )
    return {
        package: PackageBaseline(count=counts.get(package, 0), seed=entry.seed, reason=entry.reason)
        for package, entry in sorted(previous.items())
    }


def ratchet_problems(
    counts: Mapping[str, int],
    baseline: Mapping[str, PackageBaseline],
    known_packages: frozenset[str],
) -> list[str]:
    """One problem per package whose live count exceeds its pin (a missing
    entry pins 0) and one per baseline entry naming a package not on disk. A
    decrease is never a problem."""
    problems: list[str] = []
    for package in sorted(counts):
        pinned = baseline[package].count if package in baseline else 0
        if counts[package] > pinned:
            problems.append(
                f"{package}: {counts[package]} duplicate-body function(s) EXCEED the pinned {pinned} "
                f"(+{counts[package] - pinned}). A private copy of a shared-home function was added. "
                f"Fix: delete it and call the shared function; run with -Hits to list the copies; "
                f"never raise the pin in {BASELINE_PATH.name}."
            )
    for package in sorted(set(baseline) - known_packages):
        problems.append(
            f"{package}: the baseline names a package that is not on disk (known: {sorted(known_packages)}). "
            f"Fix: correct the package name or remove the entry."
        )
    return problems


# ---------------------------------------------------------------------------
# Self-test (fixture tree under the workspace .tmp; plant / observe / revert)
# ---------------------------------------------------------------------------

SELF_TEST_SCRATCH_ROOT: Final[Path] = WORKSPACE_ROOT / ".tmp" / "shared_home_body_selftest"
_COMMON_REPO, _COMMON_PKG = "datrix-codegen-common", "datrix_codegen_common"
_KERNEL_REPO, _KERNEL_PKG = "datrix-codegen-kernel", "datrix_codegen_kernel"
_DATRIX_COMMON_REPO, _DATRIX_COMMON_PKG = "datrix-common", "datrix_common"
_PYTHON_REPO, _PYTHON_PKG = "datrix-codegen-python", "datrix_codegen_python"
_TYPESCRIPT_REPO, _TYPESCRIPT_PKG = "datrix-codegen-typescript", "datrix_codegen_typescript"
_SELF_TEST_REASON: Final[str] = "self-test synthetic entry"

_HOME_PUBLIC_SOURCE: Final[str] = '''
def locate_entry(registry, key):
    """Find the entry stored under key."""
    wanted = str(key)
    for group in registry.groups.values():
        entry = group.entries.get(wanted)
        if entry is None:
            continue
        found = list(entry.items.values())
        if len(found) != 1:
            raise ValueError(f"Entry '{wanted}' has {len(found)} items; expected 1.")
        return found[0]
    raise ValueError(f"Entry '{wanted}' not found in registry '{registry.name}'.")
'''

_HOME_SHORT_SOURCE: Final[str] = '''
def short_home(item):
    return item.name.strip()
'''

_HOME_PRIVATE_SOURCE: Final[str] = '''
def _collect_private(registry, key):
    names = []
    for group in registry.groups.values():
        for entry in group.entries.values():
            if entry.key == key:
                names.append(entry.name)
            else:
                names.extend(entry.aliases)
    if not names:
        raise ValueError(f"No entry matches '{key}'.")
    return sorted(set(names))
'''

#: Renamed function, parameters, locals, string text and docstring; decorated
#: and annotated -- but the same attributes, call targets and control flow.
_COPY_RENAMED_SOURCE: Final[str] = '''
@some_decorator
def find_row(table: Table, name: str) -> Row:
    """Return the single row for name."""
    label = str(name)
    for section in table.groups.values():
        row = section.entries.get(label)
        if row is None:
            continue
        rows = list(row.items.values())
        if len(rows) != 1:
            raise ValueError(f"Row '{label}' holds {len(rows)} items.")
        return rows[0]
    raise ValueError(f"Row '{label}' is absent from '{table.name}'.")
'''

_COPY_DOCSTRING_ONLY_SOURCE: Final[str] = _HOME_PUBLIC_SOURCE.replace("locate_entry", "locate_again").replace(
    "Find the entry stored under key.", "A completely different docstring."
)
_COPY_CONSTANT_ONLY_SOURCE: Final[str] = _HOME_PUBLIC_SOURCE.replace("locate_entry", "locate_other").replace(
    "!= 1", "!= 2"
)
_COPY_ATTRIBUTE_SOURCE: Final[str] = _HOME_PUBLIC_SOURCE.replace("locate_entry", "locate_attr").replace(
    "group.entries.get", "group.rows.get"
)
_COPY_CALL_TARGET_SOURCE: Final[str] = _HOME_PUBLIC_SOURCE.replace("locate_entry", "locate_call").replace(
    "list(entry.items.values())", "tuple(entry.items.values())"
)
_COPY_SHORT_SOURCE: Final[str] = '''
def short_copy(thing):
    return thing.name.strip()
'''
_COPY_PRIVATE_BODY_SOURCE: Final[str] = '''
def gather_names(table, wanted):
    found = []
    for section in table.groups.values():
        for row in section.entries.values():
            if row.key == wanted:
                found.append(row.name)
            else:
                found.extend(row.aliases)
    if not found:
        raise ValueError(f"Nothing matches '{wanted}'.")
    return sorted(set(found))
'''
_BROKEN_SOURCE: Final[str] = "def broken(:\n"


def _check(label: str, condition: bool) -> bool:
    if condition:
        logger.info("[OK] %s", label)
    else:
        logger.error("[FAIL] %s", label)
    return condition


def _first_function(source: str) -> _FunctionNode:
    statement = ast.parse(source).body[0]
    if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise GateError(f"Self-test source does not start with a function: {source[:60]!r}.")
    return statement


def _ensure_package(root: Path, repo: str, package: str) -> Path:
    package_dir = root / repo / "src" / package
    package_dir.mkdir(parents=True, exist_ok=True)
    init_file = package_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")
    return package_dir


def _write_module(root: Path, repo: str, package: str, module: str, source: str) -> Path:
    path = _ensure_package(root, repo, package) / f"{module}.py"
    path.write_text(source, encoding="utf-8")
    return path


def _build_fixture(root: Path) -> None:
    """Three home packages (the shared homes live in codegen-common) plus two
    consuming packages."""
    _write_module(root, _COMMON_REPO, _COMMON_PKG, "homes", _HOME_PUBLIC_SOURCE + _HOME_SHORT_SOURCE + _HOME_PRIVATE_SOURCE)
    for repo, package in (
        (_KERNEL_REPO, _KERNEL_PKG),
        (_DATRIX_COMMON_REPO, _DATRIX_COMMON_PKG),
        (_PYTHON_REPO, _PYTHON_PKG),
        (_TYPESCRIPT_REPO, _TYPESCRIPT_PKG),
    ):
        _ensure_package(root, repo, package)


def _fixture_counts(root: Path) -> dict[str, int]:
    return count_by_package(measure(root))


def _case_normalization() -> bool:
    home = normalized_digest(_first_function(_HOME_PUBLIC_SOURCE))
    ok = _check(
        "a renamed, decorated, annotated copy has the home's digest",
        normalized_digest(_first_function(_COPY_RENAMED_SOURCE)) == home,
    )
    ok &= _check("a docstring-only difference keeps the digest", normalized_digest(_first_function(_COPY_DOCSTRING_ONLY_SOURCE)) == home)
    ok &= _check("a constant-only difference keeps the digest", normalized_digest(_first_function(_COPY_CONSTANT_ONLY_SOURCE)) == home)
    ok &= _check("a different attribute name changes the digest", normalized_digest(_first_function(_COPY_ATTRIBUTE_SOURCE)) != home)
    ok &= _check("a different call target changes the digest", normalized_digest(_first_function(_COPY_CALL_TARGET_SOURCE)) != home)
    return ok


def _case_floors() -> bool:
    lines, nodes = measure_body(_first_function(_HOME_PUBLIC_SOURCE))
    short_lines, short_nodes = measure_body(_first_function(_HOME_SHORT_SOURCE))
    ok = _check(f"the home function clears the floor ({lines} lines, {nodes} nodes)", lines >= MIN_BODY_LINES and nodes >= MIN_BODY_NODES)
    ok &= _check(f"the one-line accessor is below the floor ({short_lines} lines, {short_nodes} nodes)", short_lines < MIN_BODY_LINES)
    return ok


def _case_plant_observe_revert(root: Path) -> bool:
    _build_fixture(root)
    known = frozenset(discover_all_package_locations(root))
    pin = {_PYTHON_PKG: PackageBaseline(count=0, seed=0, reason=_SELF_TEST_REASON)}
    ok = _check("the clean fixture has no hit", _fixture_counts(root) == {})
    planted = _write_module(root, _PYTHON_REPO, _PYTHON_PKG, "planted", _COPY_RENAMED_SOURCE)
    hits = measure(root)
    counts = count_by_package(hits)
    ok &= _check("a planted renamed copy raises the python count by exactly 1", counts == {_PYTHON_PKG: 1})
    ok &= _check(
        "the hit names the copy and the home function",
        [(hit.copy.qualified_name, hit.home.qualified_name) for hit in hits] == [("find_row", "locate_entry")],
    )
    problems = ratchet_problems(counts, pin, known)
    ok &= _check(
        "the ratchet fails naming the package, the live count and the pin",
        len(problems) == 1 and _PYTHON_PKG in problems[0] and "1" in problems[0] and "pinned 0" in problems[0],
    )
    planted.unlink()
    ok &= _check("reverting the plant clears the hit", _fixture_counts(root) == {})
    ok &= _check("the ratchet passes after the revert", ratchet_problems(_fixture_counts(root), pin, known) == [])
    return ok


def _case_non_hits_and_near_hits(root: Path) -> bool:
    _build_fixture(root)
    ok = True
    for label, source, expected in (
        ("a docstring-only difference IS a hit", _COPY_DOCSTRING_ONLY_SOURCE, {_PYTHON_PKG: 1}),
        ("a constant-only difference IS a hit", _COPY_CONSTANT_ONLY_SOURCE, {_PYTHON_PKG: 1}),
        ("a different attribute name is NOT a hit", _COPY_ATTRIBUTE_SOURCE, {}),
        ("a different call target is NOT a hit", _COPY_CALL_TARGET_SOURCE, {}),
        ("a below-floor copy of a below-floor home is NOT a hit", _COPY_SHORT_SOURCE, {}),
        ("a copy of a PRIVATE home function IS a hit", _COPY_PRIVATE_BODY_SOURCE, {_PYTHON_PKG: 1}),
    ):
        _write_module(root, _PYTHON_REPO, _PYTHON_PKG, "variant", source)
        ok &= _check(label, _fixture_counts(root) == expected)
    return ok


def _case_home_package_pairs(root: Path) -> bool:
    _build_fixture(root)
    ok = True
    _write_module(root, _COMMON_REPO, _COMMON_PKG, "twin", _COPY_RENAMED_SOURCE)
    ok &= _check("an equal body inside the SAME home package is NOT a hit", _fixture_counts(root) == {})
    twin = _write_module(root, _KERNEL_REPO, _KERNEL_PKG, "twin", _COPY_RENAMED_SOURCE)
    ok &= _check(
        "an equal body in ANOTHER home package counts for both (symmetric)",
        _fixture_counts(root) == {_COMMON_PKG: 2, _KERNEL_PKG: 1},
    )
    twin.unlink()
    ok &= _check("deleting the twin clears kernel's count", _KERNEL_PKG not in _fixture_counts(root))
    return ok


def _case_ratchet_verdicts() -> bool:
    known = frozenset({_PYTHON_PKG, _TYPESCRIPT_PKG})
    pinned = {_PYTHON_PKG: PackageBaseline(count=2, seed=5, reason=_SELF_TEST_REASON)}
    above = ratchet_problems({_PYTHON_PKG: 3}, pinned, known)
    ok = _check("a count above the pin fails once, naming 3 and the pin 2", len(above) == 1 and "3" in above[0] and "pinned 2" in above[0])
    ok &= _check("a count below the pin passes", ratchet_problems({_PYTHON_PKG: 1}, pinned, known) == [])
    ok &= _check("a package with no entry is pinned at 0", len(ratchet_problems({_TYPESCRIPT_PKG: 1}, pinned, known)) == 1)
    ghost = {"datrix_not_a_package": PackageBaseline(count=0, seed=0, reason=_SELF_TEST_REASON)}
    ok &= _check("a baseline entry for an unknown package fails", len(ratchet_problems({}, ghost, known)) == 1)
    return ok


def _expect_gate_error(label: str, action_text: str, path: Path) -> bool:
    path.write_text(action_text, encoding="utf-8")
    try:
        load_baseline(path)
    except GateError as exc:
        return _check(label, path.name in str(exc) or "entry" in str(exc))
    return _check(label, False)


def _case_baseline_round_trip(root: Path) -> bool:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "baseline.toml"
    seeded = updated_baseline({_PYTHON_PKG: 3, _TYPESCRIPT_PKG: 0}, None)
    ok = _check("seeding writes count == seed for packages above 0 only", seeded == {_PYTHON_PKG: PackageBaseline(3, 3, SEED_REASON)})
    write_baseline(path, seeded)
    ok &= _check("a written baseline loads back equal", load_baseline(path) == seeded)
    lowered = updated_baseline({_PYTHON_PKG: 1}, load_baseline(path))
    ok &= _check(
        "lowering keeps seed and reason",
        lowered == {_PYTHON_PKG: PackageBaseline(1, 3, SEED_REASON)},
    )
    try:
        updated_baseline({_PYTHON_PKG: 2}, lowered)
    except BaselineRiseError:
        ok &= _check("raising a pin is refused", True)
    else:
        ok &= _check("raising a pin is refused", False)
    entry = 'package = "{p}"\ncount = {c}\nseed = {s}\nreason = {r}\n'
    ok &= _expect_gate_error("an empty reason is refused", "[[baseline]]\n" + entry.format(p=_PYTHON_PKG, c=1, s=2, r='""'), path)
    ok &= _expect_gate_error("count above seed is refused", "[[baseline]]\n" + entry.format(p=_PYTHON_PKG, c=3, s=2, r='"x"'), path)
    ok &= _expect_gate_error("an unrecognized key is refused", "[[baseline]]\n" + entry.format(p=_PYTHON_PKG, c=1, s=2, r='"x"') + "extra = 1\n", path)
    ok &= _expect_gate_error("an unrecognized top-level key is refused", "[other]\nx = 1\n", path)
    missing = root / "absent.toml"
    try:
        load_baseline(missing)
    except GateError:
        ok &= _check("a missing baseline is refused (never an empty pin)", True)
    else:
        ok &= _check("a missing baseline is refused (never an empty pin)", False)
    return ok


def _case_unparseable_fails_closed(root: Path) -> bool:
    _build_fixture(root)
    _write_module(root, _PYTHON_REPO, _PYTHON_PKG, "broken", _BROKEN_SOURCE)
    try:
        measure(root)
    except SkeletonError as exc:
        return _check("an unparseable file fails the scan naming the file", "broken.py" in str(exc))
    return _check("an unparseable file fails the scan naming the file", False)


def run_self_test() -> bool:
    """Plant / observe / revert on a fixture tree, floors, near-misses, home
    pairs, ratchet verdicts, baseline round trip, fail-closed parsing."""
    SELF_TEST_SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="fixture-", dir=SELF_TEST_SCRATCH_ROOT))
    try:
        results = [
            _case_normalization(),
            _case_floors(),
            _case_plant_observe_revert(scratch / "plant"),
            _case_non_hits_and_near_hits(scratch / "variants"),
            _case_home_package_pairs(scratch / "pairs"),
            _case_ratchet_verdicts(),
            _case_baseline_round_trip(scratch / "baseline"),
            _case_unparseable_fails_closed(scratch / "unparseable"),
        ]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return all(results)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options ``shared-home-body-gate.ps1`` passes: ``-Hits``, ``-Symbol``, ``-UpdateBaseline``,
    ``-Dbg`` and ``-SelfTest``."""
    parser = gate_parser(
        WRAPPER,
        "Shared-home body gate: a pinned, decrease-only count of functions whose normalized body "
        "equals a shared-home function's.",
    )
    parser.add_argument("--hits", action="store_true", help="Print every hit line.")
    parser.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="A bare function name, repeatable or comma-separated; print only the hit lines whose copy has one "
        "of these names. A report filter only: it never changes the count or the exit code.",
    )
    parser.add_argument("--update-baseline", action="store_true", help="Seed the baseline, or lower every count.")
    return parser


def _selected_hits(hits: Sequence[BodyHit], symbols: frozenset[str] | None) -> list[BodyHit]:
    return list(hits) if symbols is None else [hit for hit in hits if hit.copy.bare_name in symbols]


def _log_hits(hits: Sequence[BodyHit], *, show: bool, symbols: frozenset[str] | None) -> None:
    if not show and symbols is None:
        return
    selected = _selected_hits(hits, symbols)
    for hit in selected:
        logger.info(hit_line(hit, WORKSPACE_ROOT))
    logger.info("SHARED-HOME BODY HITS: %d hit line(s) shown", len(selected))


def _symbols(arguments: Sequence[str] | None) -> frozenset[str] | None:
    if arguments is None:
        return None
    return frozenset(comma_values(arguments))


def _write_updated_baseline(counts: Mapping[str, int]) -> int:
    previous = load_baseline(BASELINE_PATH) if BASELINE_PATH.exists() else None
    try:
        write_baseline(BASELINE_PATH, updated_baseline(counts, previous))
    except BaselineRiseError as exc:
        logger.error("SHARED-HOME BODY BASELINE: %s", exc)
        return EXIT_FAIL
    logger.info(
        "SHARED-HOME BODY BASELINE: written to %s (%d package(s) with duplicates)",
        BASELINE_PATH.name,
        sum(1 for c in counts.values() if c),
    )
    return EXIT_OK


def run_scan(args: argparse.Namespace) -> int:
    """The real measurement: the ratchet verdict, or with ``--update-baseline`` the baseline rewrite."""
    try:
        hits = measure(WORKSPACE_ROOT)
        counts = count_by_package(hits)
        _log_hits(hits, show=args.hits, symbols=_symbols(args.symbol))
        if args.update_baseline:
            return _write_updated_baseline(counts)
        return _check_against_baseline(counts)
    except (GateError, SkeletonError) as exc:
        logger.error("SHARED-HOME BODY GATE CANNOT RUN: %s", exc)
        return EXIT_USAGE


def _check_against_baseline(counts: Mapping[str, int]) -> int:
    baseline = load_baseline(BASELINE_PATH)
    known = frozenset(discover_all_package_locations(WORKSPACE_ROOT))
    for package in sorted(set(counts) | set(baseline)):
        entry = baseline.get(package)
        logger.info(
            "SHARED-HOME BODY PACKAGE: %s count=%d pin=%d seed=%d",
            package,
            counts.get(package, 0),
            0 if entry is None else entry.count,
            0 if entry is None else entry.seed,
        )
    problems = ratchet_problems(counts, baseline, known)
    for problem in problems:
        logger.error("SHARED-HOME BODY RATCHET: %s", problem)
    logger.info(
        "SHARED-HOME BODY GATE: %d duplicate function(s) in %d package(s); pinned total %d",
        sum(counts.values()),
        len(counts),
        sum(entry.count for entry in baseline.values()),
    )
    if not problems and any(counts.get(p, 0) < e.count for p, e in baseline.items()):
        logger.info("SHARED-HOME BODY RATCHET: a count dropped below its pin; lower it with -UpdateBaseline.")
    return EXIT_FAIL if problems else EXIT_OK


GATE_SPEC: Final = ParityGate(
    gate=GATE,
    wrapper=WRAPPER,
    module=MODULE,
    build_parser=build_parser,
    self_test=run_self_test,
    compare=run_scan,
    self_test_failed=EXIT_USAGE,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: 0 = within the pins, 1 = a count rose (or a baseline rise was refused),
    2 = self-test failure or the gate cannot produce a trustworthy verdict."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, GATE_SPEC.run), argv)


if __name__ == "__main__":
    sys.exit(main())
