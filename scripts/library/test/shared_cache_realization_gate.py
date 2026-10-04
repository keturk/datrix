"""Shared-cache realization gate.

A service that ``uses`` a shared cache container realizes that container's cache block next to its
own blocks (``datrix_common.datrix_model.shared_cache_scope.realized_cache_blocks``). Every
registered ``datrix.languages`` target must emit the connection, typed access and operations of each
realized block, and every registered ``datrix.platforms`` target must wire the connection keys and
network reach of each realized block and prove it supplied every key the connection surface
declares (``require_cache_keys_supplied``).

DETECTION IS STATIC, over each target's own ``src/`` trees (the backend package plus every language
core it requires) -- this gate never generates a project. A language target realizes shared
consumption when its source CALLS ``realized_cache_blocks``; a platform target realizes it when its
source calls ``realized_cache_blocks`` AND ``require_cache_keys_supplied``. Both are settled by
parsing structure (Python ``ast``), never by a substring scan. The behavioural assertions per
language and platform (key equality, per-block clients, read-only typed access, owner wiring,
consumer-only admission) live in each package's own tests; this gate pins that no registered target
silently lacks the realized-block walk they depend on.

Both axes are enumerated from the installed entry points at run time -- never a hardcoded language
or platform list -- and the gate refuses to pass with fewer than two targets on an axis.

A non-vacuity self-test runs first on every invocation: a planted consumer-blind source tree (it reads
only the service's own cache block and so emits nothing for a consumed one) must classify NOT
realized, a tree that walks the realized blocks must classify realized, and a single-target axis
must be refused as vacuous.
"""

from __future__ import annotations

import argparse
import ast
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    discover_target_package_src_dirs,
    registered_language_names,
    registered_platform_names,
)

logger = logging.getLogger(__name__)

#: A comparison over 0 or 1 target cannot tell "realized" from "the only target there is".
_MIN_TARGETS_PER_AXIS: Final[int] = 2

#: The realized-block walk every target must reach.
_REALIZED_WALK: Final[str] = "realized_cache_blocks"
#: The D10 seam check every platform must reach.
_KEYS_SUPPLIED_CHECK: Final[str] = "require_cache_keys_supplied"

#: Callees each axis must reach, in addition to nothing else.
_REQUIRED_CALLEES: Final[dict[str, frozenset[str]]] = {
    AXIS_LANGUAGES: frozenset({_REALIZED_WALK}),
    AXIS_PLATFORMS: frozenset({_REALIZED_WALK, _KEYS_SUPPLIED_CHECK}),
}

_HERE: Final[Path] = Path(__file__).resolve()
WORKSPACE_ROOT: Final[Path] = _HERE.parents[4]

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_VACUOUS: Final[int] = 2

#: ``label -> src dirs`` resolver (production: entry points + the filesystem package map).
TargetResolver = Callable[[str], dict[str, tuple[Path, ...]]]


def called_names(src_dirs: tuple[Path, ...]) -> frozenset[str]:
    """Every bare function/method name invoked (``ast.Call``) anywhere under *src_dirs*."""
    names: set[str] = set()
    for src_dir in src_dirs:
        if not src_dir.is_dir():
            continue
        for py_file in sorted(src_dir.rglob("*.py")):
            source = py_file.read_text(encoding="utf-8-sig")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError as exc:
                raise SyntaxError(
                    f"Failed to parse {py_file} while scanning for shared-cache realization: {exc}"
                ) from exc
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
    return frozenset(names)


def missing_callees(axis: str, src_dirs: tuple[Path, ...]) -> frozenset[str]:
    """The callees *axis* requires that no source under *src_dirs* calls."""
    return _REQUIRED_CALLEES[axis] - called_names(src_dirs)


def _registered(axis: str) -> frozenset[str]:
    return registered_language_names() if axis == AXIS_LANGUAGES else registered_platform_names()


def _production_resolver(axis: str, names: frozenset[str]) -> dict[str, tuple[Path, ...]]:
    return discover_target_package_src_dirs(axis, names, WORKSPACE_ROOT)


def run_gate(
    axis: str,
    *,
    target_names: frozenset[str] | None = None,
    resolve: Callable[[str, frozenset[str]], dict[str, tuple[Path, ...]]] = _production_resolver,
) -> int:
    """Full gate run for one axis. Returns a process exit code (0/1/2).

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        target_names: Override for the registered target set (the self-test passes a synthetic
            restricted set to prove the vacuity guard through the same code path a live run takes).
        resolve: ``(axis, names) -> {label: src dirs}``.
    """
    names = target_names if target_names is not None else _registered(axis)
    if len(names) < _MIN_TARGETS_PER_AXIS:
        logger.error(
            "shared_cache_gate_vacuous axis=%s target_count=%d minimum=%d",
            axis,
            len(names),
            _MIN_TARGETS_PER_AXIS,
        )
        return EXIT_VACUOUS

    gaps: dict[str, frozenset[str]] = {}
    targets = resolve(axis, names)
    for label, src_dirs in sorted(targets.items()):
        missing = missing_callees(axis, src_dirs)
        logger.info(
            "shared_cache_realization axis=%s target=%s status=%s missing=%s",
            axis,
            label,
            "GAP" if missing else "REALIZED",
            sorted(missing),
        )
        if missing:
            gaps[label] = missing

    if gaps:
        for label, missing in sorted(gaps.items()):
            logger.error(
                "SHARED-CACHE REALIZATION GAP (axis=%s): target %s never calls %s. A target must "
                "walk realized_cache_blocks(service) to emit every cache block a service realizes "
                "(its own and the shared ones it consumes)%s.",
                axis,
                label,
                sorted(missing),
                (
                    " and call require_cache_keys_supplied for the blocks it provisions"
                    if axis == AXIS_PLATFORMS
                    else ""
                ),
            )
        return EXIT_FAIL

    logger.info(
        "SHARED-CACHE REALIZATION HOLDS (axis=%s): %d target(s) realize shared cache consumption.",
        axis,
        len(targets),
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

_SELF_TEST_TARGET_A: Final[str] = "self_test_target_a"
_SELF_TEST_TARGET_B: Final[str] = "self_test_target_b"


def run_self_test() -> None:
    """Non-vacuity self-test, step 1 of every invocation.

    Raises:
        AssertionError: A proof failed -- the gate aborts before trusting any real comparison.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix="shared-cache-realization-selftest-"))
    try:
        walking = tmp_root / "walking_pkg"
        blind = tmp_root / "consumer_blind_pkg"
        walking.mkdir(parents=True)
        blind.mkdir(parents=True)
        (walking / "emit.py").write_text(
            "def emit(service):\n"
            "    return [block for block in realized_cache_blocks(service)]\n"
            "def check(service, supplied):\n"
            "    require_cache_keys_supplied(service, supplied, platform='x', blocks=[])\n",
            encoding="utf-8",
        )
        # The planted consumer-blind target: it reads only the service's own block, so a
        # consumed shared block gets no connection module, no client and no wiring.
        (blind / "emit.py").write_text(
            "def emit(service):\n    return [service.cache_block]\n",
            encoding="utf-8",
        )

        for axis in (AXIS_LANGUAGES, AXIS_PLATFORMS):
            assert not missing_callees(axis, (walking,)), (
                f"self-test: a tree that walks realized blocks must classify realized on {axis}"
            )
            planted = missing_callees(axis, (blind,))
            assert _REALIZED_WALK in planted, (
                f"self-test: a consumer-blind tree must be detected on {axis}"
            )
            print(f"[OK] {axis}: walking tree realized; consumer-blind tree detected {sorted(planted)}")

        def resolve(axis: str, names: frozenset[str]) -> dict[str, tuple[Path, ...]]:
            return {_SELF_TEST_TARGET_A: (walking,), _SELF_TEST_TARGET_B: (blind,)}

        planted_exit = run_gate(
            AXIS_LANGUAGES,
            target_names=frozenset({_SELF_TEST_TARGET_A, _SELF_TEST_TARGET_B}),
            resolve=resolve,
        )
        assert planted_exit == EXIT_FAIL, (
            f"self-test: run_gate must fail on a planted consumer-blind target, got {planted_exit}"
        )
        print(f"[OK] run_gate fails a planted consumer-blind target (exit={planted_exit})")

        vacuous_exit = run_gate(
            AXIS_LANGUAGES, target_names=frozenset({_SELF_TEST_TARGET_A}), resolve=resolve
        )
        assert vacuous_exit == EXIT_VACUOUS, (
            f"self-test: run_gate must refuse a single-target axis, got {vacuous_exit}"
        )
        print(f"[OK] run_gate refuses a single-target axis as vacuous (exit={vacuous_exit})")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main() -> int:
    """CLI entry point; returns 0 (holds / self-test passed), 1 (gap), 2 (vacuous or self-test failed)."""
    parser = argparse.ArgumentParser(
        description=(
            "Shared-cache realization gate: every registered language and platform walks the "
            "realized cache blocks of a service (static source analysis, never generation)."
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
    return max(run_gate(axis) for axis in axes)


if __name__ == "__main__":
    sys.exit(main())
