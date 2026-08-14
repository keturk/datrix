"""Pooled-cache member-slice realization gate.

For every registered ``datrix.languages`` / ``datrix.platforms`` target,
asserts that a pooled cache member's declared slice
(``PooledMember.slice_index`` -- ``datrix_codegen_common.pooling.contract``)
actually reaches that target's own emitted-output-facing source, not merely
that the shared pooling pre-pass computed it. A target that does not yet
realize the slice must carry a typed exemption (axis + target + reason) in
``scripts/config/pooled-cache-realization-exemptions.json``; the file's own
``pinned_count`` is a hand-reviewed field that must equal the live entry
count on every change, so a target quietly losing its realization (a
regression) fails the same way a target that never had one does.

DETECTION IS STATIC, over each target package's own ``src/`` tree -- this
gate never invokes ``generate.ps1`` and never generates a project. A target
"realizes" the slice when its own source contains at least one function
(module-level or class method) that (a) reads a ``.slice_index`` attribute
AND (b) is actually CALLED from elsewhere in that same source tree (not dead
code). Declaration-plus-consumption is the same two-part shape
``block_realization_parity.py`` checks for platform capability declarations;
here the "declaration" is a real attribute read and the "consumption" is
call-reachability, both settled by parsing structure (Python ``ast``) rather
than a substring/regex scan.

Two independent axes: LANGUAGES (python/typescript/java/dotnet/...) and
PLATFORMS (aws/azure/docker/...), both discovered from
``importlib.metadata.entry_points()`` at runtime -- never a hardcoded name
list, so a new ``datrix-codegen-<x>`` package is picked up automatically.
The gate refuses to run with fewer than two registered targets on the axis
being checked (a realization comparison over < 2 targets cannot distinguish
"realized" from "the only target there is").
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Final, Protocol

logger = logging.getLogger(__name__)

AXIS_LANGUAGES: Final[str] = "languages"
AXIS_PLATFORMS: Final[str] = "platforms"
_AXIS_ENTRY_POINT_GROUPS: Final[dict[str, str]] = {
    AXIS_LANGUAGES: "datrix.languages",
    AXIS_PLATFORMS: "datrix.platforms",
}
_MIN_TARGETS_PER_AXIS: Final[int] = 2

# This file: datrix/scripts/library/test/pooled_cache_realization_gate.py --
# parents[0]=.../library/test, [1]=.../library, [2]=.../scripts, [3]=<datrix>,
# [4]=<the monorepo workspace root>. Mirrors parallel_implementation_drift.py's
# identical-depth path math.
_HERE: Final[Path] = Path(__file__).resolve()
DATRIX_DIR: Final[Path] = _HERE.parents[3]
WORKSPACE_ROOT: Final[Path] = _HERE.parents[4]
EXEMPTIONS_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "pooled-cache-realization-exemptions.json"

#: The pooled-cache example fixture -- the only source this gate's real
#: (non-self-test) run reads (never generates). Every target is checked
#: against this SAME two-member pooled-cache fixture; this gate never edits it.
_FIXTURE_SYSTEM_DTRX: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "examples" / "02-features" / "03-infrastructure-blocks" / "cache" / "system.dtrx"
)
#: catalog-service.dcfg and pricing-service.dcfg both join a cache block to
#: this pool group -- the fixture's one pooled-cache group. Counted directly
#: off the fixture's own config/ files (see `_fixture_pooled_cache_member_count`)
#: rather than hardcoded, so an edit to the fixture's member count is
#: reflected here automatically instead of silently drifting stale.
_FIXTURE_CACHE_GROUP_NAME: Final[str] = "shared-lookup-cache"
_CACHE_GROUP_DECLARATION_LITERAL: Final[str] = f'cacheGroup = "{_FIXTURE_CACHE_GROUP_NAME}"'

#: The one field every resource-sharing isolation mechanism must read
#: (PooledMember.slice_index / PooledMemberRenderContext.slice_index) --
#: this gate's whole detection is "is a `.slice_index` attribute access
#: reachable from a real call site in this target's own source".
_SLICE_INDEX_ATTR: Final[str] = "slice_index"

_PACKAGE_DIR_PREFIX: Final[str] = "datrix-"
_SRC_SUBDIR_NAME: Final[str] = "src"
#: `ast.stmt` attribute names whose value is itself a statement list this
#: scanner must descend into to find a def nested inside a non-function,
#: non-class container (If/While/For/With/Try's main body + else + finally).
_CONTAINER_BODY_ATTRS: Final[tuple[str, ...]] = ("body", "orelse", "finalbody")

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_VACUOUS: Final[int] = 2

_FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef

#: Self-test-only synthetic function names, chosen to be unmistakably not a
#: real target's own symbol -- proving the AST detector is driven entirely by
#: the source it is pointed at, never a hardcoded per-language function name.
_SELF_TEST_REALIZED_FUNC_NAME: Final[str] = "self_test_consume_slice"
_SELF_TEST_SEVERED_FUNC_NAME: Final[str] = "self_test_dead_consume_slice"
_SELF_TEST_SINGLE_TARGET: Final[str] = "self_test_only_one_target"


@dataclass(frozen=True)
class RealizationExemption:
    """One typed, reviewed exemption: this target does not yet realize the
    pooled-cache slice, and here is why."""

    axis: str
    target: str
    reason: str


@dataclass(frozen=True)
class RealizationResult:
    """Outcome of checking one target for slice realization."""

    axis: str
    target: str
    realized: bool
    member_slices_observed: tuple[str, ...]
    """The distinct per-member slice markers this target's emitted output
    carried (env var value, key prefix, secret content fragment, ...), in
    member order. Realized == True requires len(set(...)) == member count."""


class SliceRealizationProbe(Protocol):
    """A callable that, for one target on one axis, returns the emitted
    per-member slice markers observed for the pooled-cache example fixture
    (or synthetic fixture data, for the self-test). Swapping the probe is
    what lets the self-test exercise this gate's DETECTION logic without
    touching a real target's source tree."""

    def __call__(self, axis: str, target: str) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class _SliceIndexConsumerSite:
    """One function/method whose body reads a `.slice_index` attribute."""

    function_name: str
    file_path: Path
    line_number: int


def discover_registered_targets(axis: str) -> frozenset[str]:
    """Registered target names on *axis*, read from entry_points() -- never
    a hardcoded language/platform list.

    Raises:
        ValueError: *axis* is not one of AXIS_LANGUAGES / AXIS_PLATFORMS.
    """
    group = _AXIS_ENTRY_POINT_GROUPS.get(axis)
    if group is None:
        raise ValueError(
            f"Unknown axis {axis!r}. Valid options: "
            f"{sorted(_AXIS_ENTRY_POINT_GROUPS)}. Pass one of these axis names."
        )
    return frozenset(ep.name for ep in entry_points(group=group))


# ---------------------------------------------------------------------------
# Fixture (read-only -- this gate never edits or generates the fixture)
# ---------------------------------------------------------------------------


def _fixture_pooled_cache_member_count() -> int:
    """Count of pooled-cache members the example fixture actually declares.

    Counted directly off the fixture's own config/*.dcfg text (the exact
    literal ``cacheGroup = "shared-lookup-cache"`` declaration) instead of a
    bare hardcoded constant, so a future edit to the fixture's member count
    is reflected here automatically rather than silently going stale. This
    gate only reads the fixture; it never edits or generates it.

    Raises:
        ValueError: The fixture declares fewer than `_MIN_TARGETS_PER_AXIS`
            members joined to its pooled-cache group -- this gate's
            realization probe needs a genuinely pooled (>=2-member) group to
            tell a distinguishing implementation from a collapsed one.
    """
    config_dir = _FIXTURE_SYSTEM_DTRX.parent / "config"
    count = sum(
        dcfg_file.read_text(encoding="utf-8").count(_CACHE_GROUP_DECLARATION_LITERAL)
        for dcfg_file in sorted(config_dir.glob("*.dcfg"))
    )
    if count < _MIN_TARGETS_PER_AXIS:
        raise ValueError(
            f"Fixture config under {config_dir} declares only {count} member(s) "
            f"joined to cacheGroup {_FIXTURE_CACHE_GROUP_NAME!r}; need at least "
            f"{_MIN_TARGETS_PER_AXIS}. Fix: restore the fixture's pooled-cache "
            f"group membership, or update this gate's expected group name "
            f"({_FIXTURE_CACHE_GROUP_NAME!r}) if the fixture was intentionally "
            f"restructured."
        )
    return count


# ---------------------------------------------------------------------------
# On-disk package resolution (per single target -- never a hardcoded
# datrix-codegen-{name} string-format assumption)
# ---------------------------------------------------------------------------


def _resolve_target_src_dir(axis: str, target: str, monorepo_root: Path) -> Path:
    """Resolve one registered target's on-disk package `src/<import_name>` dir.

    Reads the entry point's DECLARED module rather than importing and
    instantiating the plugin (a platform plugin needs generation context to
    construct; this gate only needs to know which package the code lives in).

    Args:
        axis: AXIS_LANGUAGES or AXIS_PLATFORMS.
        target: A registered target name on that axis.
        monorepo_root: The workspace root containing every `datrix-*` checkout.

    Returns:
        The absolute `src/<import_name>` directory for *target*.

    Raises:
        ValueError: *target* has no entry point on *axis*, or its declared
            module root resolves to no on-disk `datrix-*` package.
    """
    group = _AXIS_ENTRY_POINT_GROUPS[axis]
    module_roots = {ep.name: ep.module.split(".")[0] for ep in entry_points(group=group)}
    import_name = module_roots.get(target)
    if import_name is None:
        raise ValueError(
            f"Registered {axis} target {target!r} has no entry point in group "
            f"{group!r}. Registered entry points: {sorted(module_roots)}. Fix: "
            f"pass one of these registered target names."
        )
    for candidate in sorted(monorepo_root.iterdir()):
        if not candidate.is_dir() or not candidate.name.startswith(_PACKAGE_DIR_PREFIX):
            continue
        src_dir = candidate / _SRC_SUBDIR_NAME / import_name
        if src_dir.is_dir():
            return src_dir
    raise ValueError(
        f"Could not resolve an on-disk src/ directory for {axis} target "
        f"{target!r} (its registered plugin lives in module root "
        f"{import_name!r}). Expected a 'datrix-*' directory under "
        f"{monorepo_root} whose src/ tree contains a {import_name!r} package "
        f"directory."
    )


# ---------------------------------------------------------------------------
# AST-based declared+reachable slice_index detector (the real check)
# ---------------------------------------------------------------------------


def _collect_module_and_method_defs(body: list[ast.stmt]) -> list[_FunctionDefNode]:
    """Recursively collect every module-level or class-method function def,
    reachable through non-function statement containers (If/While/For/With/
    Try) -- mirrors parallel_implementation_drift.py's own def-collector.

    Never descends into a FunctionDef/AsyncFunctionDef's own body: a function
    nested inside another function is a closure, not a module-level-or-
    class-method declaration this scanner tracks.

    Args:
        body: A statement list (a module body or a class body).

    Returns:
        Every module-level or class-method function/async-function def node,
        in source order.
    """
    found: list[_FunctionDefNode] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            found.extend(_collect_module_and_method_defs(stmt.body))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(stmt)
            continue
        for attr in _CONTAINER_BODY_ATTRS:
            nested_body = getattr(stmt, attr, None)
            if nested_body:
                found.extend(_collect_module_and_method_defs(nested_body))
        for handler in getattr(stmt, "handlers", ()):
            found.extend(_collect_module_and_method_defs(handler.body))
    return found


def _parse_python_file(py_file: Path) -> ast.Module:
    """Parse one `.py` file's source into an AST module.

    Raises:
        SyntaxError: The file cannot be parsed.
    """
    source = py_file.read_text(encoding="utf-8-sig")
    try:
        return ast.parse(source, filename=str(py_file))
    except SyntaxError as exc:
        raise SyntaxError(
            f"Failed to parse {py_file} while scanning for pooled-cache "
            f"slice_index consumption: {exc}"
        ) from exc


def _references_slice_index_attr(node: ast.AST) -> bool:
    """True iff *node*'s subtree contains a `.slice_index` attribute read."""
    return any(
        isinstance(child, ast.Attribute) and child.attr == _SLICE_INDEX_ATTR
        for child in ast.walk(node)
    )


def _functions_reading_slice_index(src_dir: Path) -> list[_SliceIndexConsumerSite]:
    """Every module-level/class-method function under *src_dir* whose body
    reads a `.slice_index` attribute -- the DECLARATION half of this gate's
    two-part check.

    Args:
        src_dir: A target package's source root.

    Returns:
        One site per qualifying function, in file-then-source order. Empty
        if *src_dir* does not exist.
    """
    hits: list[_SliceIndexConsumerSite] = []
    if not src_dir.is_dir():
        return hits
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = _parse_python_file(py_file)
        for node in _collect_module_and_method_defs(tree.body):
            if _references_slice_index_attr(node):
                hits.append(_SliceIndexConsumerSite(node.name, py_file, node.lineno))
    return hits


def _called_bare_names(src_dir: Path) -> frozenset[str]:
    """Every bare function/method name invoked (`ast.Call`) anywhere under
    *src_dir* -- the CONSUMPTION half of this gate's two-part check (a name
    that never appears here is dead code: declared but never reached).

    Args:
        src_dir: A target package's source root.

    Returns:
        Frozenset of called bare names. Empty if *src_dir* does not exist.
    """
    names: set[str] = set()
    if not src_dir.is_dir():
        return frozenset(names)
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = _parse_python_file(py_file)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return frozenset(names)


def slice_index_realization_for_src_dir(src_dir: Path) -> tuple[bool, tuple[str, ...]]:
    """Pure, dependency-injected core check: does *src_dir*'s own source
    structurally realize the pooled-cache slice?

    True iff at least one function in *src_dir* both reads `.slice_index`
    AND is called from elsewhere in the same tree (declared AND reachable --
    not dead code). Exercised directly by the self-test against synthetic
    source trees, never through a live package/entry-point resolution.

    Args:
        src_dir: A target package's source root.

    Returns:
        `(is_realized, reachable_sites)` -- `reachable_sites` names each
        declared-and-reachable consumer as `"{function}@{file}:{line}"`,
        sorted, for diagnostic logging.
    """
    declaring = _functions_reading_slice_index(src_dir)
    called = _called_bare_names(src_dir)
    reachable_sites = tuple(
        sorted(
            f"{site.function_name}@{site.file_path.name}:{site.line_number}"
            for site in declaring
            if site.function_name in called
        )
    )
    return bool(reachable_sites), reachable_sites


def real_generation_probe(axis: str, target: str) -> tuple[str, ...]:
    """Realization probe backed by a STATIC scan of *target*'s own source --
    never a `generate.ps1` run.

    Resolves *target*'s on-disk package `src/` tree and runs
    `slice_index_realization_for_src_dir` against it. When realized, returns
    one marker per member of the example fixture (read from the fixture's
    own config, never hardcoded) so the caller's arithmetic
    (`len(set(markers)) == len(markers) >= member count`) requires the count
    to match the fixture's real member count. When not realized, returns a
    single marker -- always failing that arithmetic's `>= member count`
    requirement.

    Args:
        axis: AXIS_LANGUAGES or AXIS_PLATFORMS.
        target: A registered target name on that axis.

    Returns:
        The observed slice markers -- see module docstring for what
        "realized" means structurally.
    """
    src_dir = _resolve_target_src_dir(axis, target, WORKSPACE_ROOT)
    is_realized, sites = slice_index_realization_for_src_dir(src_dir)
    if not is_realized:
        logger.debug("axis=%s target=%s slice_index_consumer_sites=none (declared-but-dead or absent)", axis, target)
        return (f"{target}:slice_index_unconsumed",)
    logger.debug("axis=%s target=%s slice_index_consumer_sites=%s", axis, target, sites)
    member_count = _fixture_pooled_cache_member_count()
    return tuple(f"{target}:member{i}:slice_index_consumed" for i in range(member_count))


def check_target(axis: str, target: str, probe: SliceRealizationProbe) -> RealizationResult:
    """Run *probe* for one target and classify realized vs. not."""
    markers = probe(axis, target)
    return RealizationResult(
        axis=axis,
        target=target,
        realized=len(set(markers)) == len(markers) and len(markers) >= _MIN_TARGETS_PER_AXIS,
        member_slices_observed=markers,
    )


# ---------------------------------------------------------------------------
# Exemption file (reviewed, typed holes -- never silence)
# ---------------------------------------------------------------------------

_EXEMPTION_REQUIRED_STRING_FIELDS: Final[tuple[str, ...]] = ("axis", "target", "reason")


def load_exemptions(config_path: Path) -> tuple[list[RealizationExemption], int]:
    """Parse the exemption file. Returns (exemptions, pinned_count).

    Raises:
        ValueError: The file is missing, malformed, an entry is missing a
            non-empty required field or names an unknown axis, or the file's
            own exemption count does not equal its pinned `pinned_count`
            field (the file is internally inconsistent -- caught here rather
            than silently trusting whichever is read first).
    """
    if not config_path.exists():
        raise ValueError(
            f"Missing exemption file {config_path}. It pins the catalogued "
            f"pooled-cache realization gaps. Restore it from git; the gate "
            f"never creates it."
        )
    data = json.loads(config_path.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    pinned_count = data.get("pinned_count")
    if not isinstance(entries, list) or not isinstance(pinned_count, int) or isinstance(pinned_count, bool):
        raise ValueError(
            f"Malformed exemption file {config_path}: expected an object "
            f"with 'pinned_count' (int) and 'exemptions' (array of "
            f"{{axis, target, reason}})."
        )
    exemptions: list[RealizationExemption] = []
    for entry in entries:
        for field_name in _EXEMPTION_REQUIRED_STRING_FIELDS:
            if not isinstance(entry.get(field_name), str) or not entry[field_name].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} in {config_path} is missing a "
                    f"non-empty {field_name!r}."
                )
        if entry["axis"] not in _AXIS_ENTRY_POINT_GROUPS:
            raise ValueError(
                f"Exemption entry {entry!r} in {config_path} has axis "
                f"{entry['axis']!r}, not one of {sorted(_AXIS_ENTRY_POINT_GROUPS)}."
            )
        exemptions.append(
            RealizationExemption(axis=entry["axis"], target=entry["target"], reason=entry["reason"])
        )
    if len(exemptions) != pinned_count:
        raise ValueError(
            f"Exemption file {config_path} has {len(exemptions)} entries but "
            f"'pinned_count' is pinned at {pinned_count}. Update pinned_count "
            f"in the same change that adds or removes an entry."
        )
    return exemptions, pinned_count


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> None:
    """Non-vacuity self-test, step 1 of every invocation.

    Three independent proofs, printed for CLI visibility:
      1. `check_target`'s classification arithmetic: a synthetic REALIZED
         probe (two distinct marker strings) must pass; a synthetic SEVERED
         probe (two identical markers) must fail.
      2. The REAL AST-based structural detector
         (`slice_index_realization_for_src_dir`) -- the function
         `real_generation_probe` actually uses -- against synthetic source
         trees it has never seen: a declared-and-reachable `.slice_index`
         consumer must classify realized; a declared-but-dead (never called)
         one must classify NOT realized.
      3. `run_gate`'s own vacuity guard, invoked for real (the same code
         path a live run takes, via its `target_names` override) against a
         synthetic single-target axis.

    Raises:
        AssertionError: Any of the three proofs failed -- the gate aborts
            before any real (non-self-test) comparison is trusted.
    """
    realized = check_target(
        AXIS_LANGUAGES, "_self_test_realized", lambda axis, target: ("db=0", "db=1")
    )
    severed = check_target(
        AXIS_LANGUAGES, "_self_test_severed", lambda axis, target: ("db=0", "db=0")
    )
    print(
        "[OK] check_target: two distinct markers -> realized"
        if realized.realized
        else "[FAIL] check_target: two distinct markers did not classify realized"
    )
    assert realized.realized, "self-test: a distinct-marker probe must classify realized"
    print(
        "[OK] check_target: two identical markers -> NOT realized"
        if not severed.realized
        else "[FAIL] check_target: two identical markers classified realized"
    )
    assert not severed.realized, "self-test: a collapsed-marker probe must classify NOT realized"

    tmp_root = Path(tempfile.mkdtemp(prefix="pooled-cache-realization-selftest-"))
    try:
        realized_dir = tmp_root / "realized_pkg"
        severed_dir = tmp_root / "severed_pkg"
        realized_dir.mkdir(parents=True, exist_ok=True)
        severed_dir.mkdir(parents=True, exist_ok=True)

        # REALIZED: a function reads .slice_index AND is called elsewhere.
        (realized_dir / "consume.py").write_text(
            f"def {_SELF_TEST_REALIZED_FUNC_NAME}(member):\n"
            f"    return f'db={{member.slice_index}}'\n",
            encoding="utf-8",
        )
        (realized_dir / "caller.py").write_text(
            "def render_cache_connection(member):\n"
            f"    return {_SELF_TEST_REALIZED_FUNC_NAME}(member)\n",
            encoding="utf-8",
        )
        is_realized, realized_sites = slice_index_realization_for_src_dir(realized_dir)
        print(
            f"[OK] AST detector: declared+called consumer -> realized (sites={realized_sites})"
            if is_realized
            else f"[FAIL] AST detector: declared+called consumer did not classify realized (sites={realized_sites})"
        )
        assert is_realized, (
            "self-test: a slice_index-reading function that IS called elsewhere "
            "must classify realized"
        )

        # SEVERED: the exact regression shape a realization task could
        # introduce -- the reading function exists but nothing calls it.
        (severed_dir / "consume.py").write_text(
            f"def {_SELF_TEST_SEVERED_FUNC_NAME}(member):\n"
            f"    return f'db={{member.slice_index}}'\n",
            encoding="utf-8",
        )
        (severed_dir / "unrelated.py").write_text(
            "def render_cache_connection(member):\n"
            "    return 'static-value-never-reads-slice-index'\n",
            encoding="utf-8",
        )
        is_severed_realized, severed_sites = slice_index_realization_for_src_dir(severed_dir)
        print(
            "[OK] AST detector: declared-but-dead consumer -> NOT realized"
            if not is_severed_realized
            else f"[FAIL] AST detector: dead consumer wrongly classified realized (sites={severed_sites})"
        )
        assert not is_severed_realized, (
            "self-test: a slice_index-reading function that is NEVER called must "
            "classify NOT realized (severed/dead code)"
        )

        vacuous_exit = run_gate(
            AXIS_LANGUAGES,
            tmp_root / "unused-config.json",
            probe=real_generation_probe,
            target_names=frozenset({_SELF_TEST_SINGLE_TARGET}),
        )
        print(
            f"[OK] run_gate refuses a single-target axis as vacuous (exit={vacuous_exit})"
            if vacuous_exit == EXIT_VACUOUS
            else f"[FAIL] run_gate did not refuse a single-target axis (exit={vacuous_exit}, expected {EXIT_VACUOUS})"
        )
        assert vacuous_exit == EXIT_VACUOUS, (
            f"self-test: run_gate must refuse a single-target axis with exit code "
            f"{EXIT_VACUOUS}, got {vacuous_exit}"
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Full gate run
# ---------------------------------------------------------------------------


def run_gate(
    axis: str,
    config_path: Path,
    *,
    probe: SliceRealizationProbe,
    target_names: frozenset[str] | None = None,
) -> int:
    """Full gate run for one axis. Returns a process exit code (0/1/2).

    Args:
        axis: AXIS_LANGUAGES or AXIS_PLATFORMS.
        config_path: The exemption file to load.
        probe: The realization probe (production callers pass
            `real_generation_probe`; the self-test injects synthetic probes).
        target_names: Override for the registered target set on this axis.
            Production callers omit it (the live entry-point-derived set
            from `discover_registered_targets` is used); the self-test
            passes a synthetic restricted set to prove the vacuity guard for
            real, against the SAME code path a live run takes, without
            needing to uninstall a registered package.

    Returns:
        0: live exemption count equals `pinned_count` and every exempted
           target is still genuinely unrealized (no realized-but-still-
           exempted stale entry).
        1: a non-exempted target failed realization, a previously-exempted
           target now realizes the slice (stale exemption), or the
           exemption file's live entry count does not match `pinned_count`.
        2: fewer than `_MIN_TARGETS_PER_AXIS` targets are registered on
           *axis*.
    """
    targets = target_names if target_names is not None else discover_registered_targets(axis)
    if len(targets) < _MIN_TARGETS_PER_AXIS:
        logger.error(
            "pooled_cache_gate_vacuous axis=%s target_count=%d minimum=%d",
            axis, len(targets), _MIN_TARGETS_PER_AXIS,
        )
        return EXIT_VACUOUS

    try:
        exemptions, pinned_count = load_exemptions(config_path)
    except ValueError as exc:
        logger.error("POOLED-CACHE REALIZATION EXEMPTION FILE INVALID: %s", exc)
        return EXIT_FAIL

    axis_exemptions = {e.target: e.reason for e in exemptions if e.axis == axis}
    results = {target: check_target(axis, target, probe) for target in sorted(targets)}

    realized_targets = sorted(t for t, r in results.items() if r.realized)
    unrealized_targets = sorted(t for t, r in results.items() if not r.realized)
    unexempted_gaps = sorted(t for t in unrealized_targets if t not in axis_exemptions)
    stale_exemptions = sorted(t for t in realized_targets if t in axis_exemptions)

    for target in sorted(results):
        result = results[target]
        if result.realized:
            status = "REALIZED_BUT_STILL_EXEMPTED" if target in axis_exemptions else "REALIZED"
        else:
            status = "EXEMPTED" if target in axis_exemptions else "GAP"
        logger.info(
            "pooled_cache_realization axis=%s target=%s status=%s markers=%s",
            axis, target, status, result.member_slices_observed,
        )

    logger.info(
        "POOLED-CACHE REALIZATION CENSUS (axis=%s): targets_checked=%d realized=%d "
        "exempt=%d unexempted_gaps=%d stale_exemptions=%d live_exemption_count=%d "
        "pinned_count=%d",
        axis, len(results), len(realized_targets), len(axis_exemptions),
        len(unexempted_gaps), len(stale_exemptions), len(exemptions), pinned_count,
    )

    if unexempted_gaps or stale_exemptions:
        if unexempted_gaps:
            logger.error(
                "POOLED-CACHE REALIZATION GAP (axis=%s): %d target(s) do not "
                "realize the declared pooled-cache member slice and carry no "
                "exemption: %s. Fix: add a reviewed entry to %s "
                "({\"axis\": %r, \"target\": <name>, \"reason\": <why>}) and "
                "increment pinned_count, or realize the slice.",
                axis, len(unexempted_gaps), unexempted_gaps, config_path, axis,
            )
        if stale_exemptions:
            logger.error(
                "POOLED-CACHE REALIZATION STALE EXEMPTION (axis=%s): %d "
                "target(s) are exempted in %s but now realize the slice: %s. "
                "Fix: remove the exemption entry and decrement pinned_count "
                "in the same change.",
                axis, len(stale_exemptions), config_path, stale_exemptions,
            )
        return EXIT_FAIL

    logger.info(
        "POOLED-CACHE REALIZATION HOLDS (axis=%s): every registered target "
        "realizes the slice or carries a reviewed exemption.",
        axis,
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point.

    Returns:
        0: self-test passed and, for every axis checked, every registered
           target realizes the pooled-cache member slice or carries a
           reviewed exemption (or `--self-test` was passed and it passed).
        1: an unexempted gap or a stale exemption was found on some checked
           axis, or the exemption file's live count does not match its
           pinned_count.
        2: the self-test failed, or fewer than two targets are registered
           on an axis being checked.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Pooled-cache member-slice realization gate: for every registered "
            "datrix.languages / datrix.platforms target, asserts (via static "
            "source analysis, never generation) that a pooled cache member's "
            "declared slice_index actually reaches that target's own emitted-"
            "output-facing source, or carries a reviewed exemption."
        ),
    )
    parser.add_argument(
        "--axis",
        choices=(AXIS_LANGUAGES, AXIS_PLATFORMS),
        default=None,
        help="Which axis to check. Omit to check both.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real check",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        run_self_test()
    except AssertionError as exc:
        logger.error("NON-VACUITY SELF-TEST FAILED: %s", exc)
        return EXIT_VACUOUS
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    axes = (args.axis,) if args.axis else (AXIS_LANGUAGES, AXIS_PLATFORMS)
    worst = EXIT_OK
    for axis in axes:
        code = run_gate(axis, EXEMPTIONS_PATH, probe=real_generation_probe)
        worst = max(worst, code)
    return worst


__all__ = [
    "AXIS_LANGUAGES",
    "AXIS_PLATFORMS",
    "EXIT_FAIL",
    "EXIT_OK",
    "EXIT_VACUOUS",
    "EXEMPTIONS_PATH",
    "RealizationExemption",
    "RealizationResult",
    "check_target",
    "discover_registered_targets",
    "load_exemptions",
    "real_generation_probe",
    "run_gate",
    "run_self_test",
    "slice_index_realization_for_src_dir",
]


if __name__ == "__main__":
    sys.exit(main())
