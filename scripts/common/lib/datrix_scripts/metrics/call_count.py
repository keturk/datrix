"""Count calls to named functions while one workload runs in this process.

The module behind ``metrics/call-count.ps1`` (and its ``.sh`` twin).

A workload is either one ``datrix generate`` (in-process, through the CLI's own Typer app) or
importing named modules. Counters are installed BEFORE any workload module is imported, so a
name a module binds with ``from x import y`` at import time is the counted wrapper. Subprocess
launches (``subprocess.Popen``) are always counted.

Targets are ``module:qualname`` -- ``importlib.metadata:entry_points``,
``jinja2.environment:Environment.compile``, ``pathlib:Path.resolve``. Expectations are
``<target><op><n>`` with ``<=``, ``==`` or ``>=`` (``subprocess`` names the launch counter).

A self-test runs as step 1 of every invocation: it counts a planted function and a planted
method through the same installer and fails the run (exit 2) if a counter does not count, so a
probe that silently stopped counting can never report a clean zero.

Exit codes: 0 = workload succeeded and every expectation holds; 1 = an expectation failed or
the workload failed; 2 = usage error or self-test failure.
"""

from __future__ import annotations

import argparse
import functools
import importlib
import json
import re
import subprocess
import sys
import time
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import require_packages

MODULE: Final = "datrix_scripts.metrics.call_count"
WRAPPER: Final = "call-count"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

SUBPROCESS_COUNTER = "subprocess"
DEFAULT_OUTPUT_ROOT = WORKSPACE_DIR / ".tmp" / "call-count"
EXPECTATION_PATTERN = re.compile(r"^(?P<name>[^<>=]+?)\s*(?P<op><=|==|>=)\s*(?P<count>\d+)$")
OPERATORS: dict[str, Callable[[int, int], bool]] = {
    "<=": lambda actual, bound: actual <= bound,
    "==": lambda actual, bound: actual == bound,
    ">=": lambda actual, bound: actual >= bound,
}


class ProbeUsageError(Exception):
    """A target or expectation the probe cannot use, named with what was expected."""


@dataclass
class Counters:
    """Call counts keyed by target name, plus the subprocess launch count."""

    counts: dict[str, int] = field(default_factory=dict)

    def bump(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1


@dataclass(frozen=True)
class Expectation:
    """One ``<name><op><count>`` bound checked after the workload."""

    name: str
    op: str
    count: int

    def holds(self, actual: int) -> bool:
        return OPERATORS[self.op](actual, self.count)

    def render(self) -> str:
        return f"{self.name}{self.op}{self.count}"


def parse_expectation(raw: str) -> Expectation:
    """Parse ``name<=n`` / ``name==n`` / ``name>=n``.

    Raises:
        ProbeUsageError: The text is not of that shape.
    """
    match = EXPECTATION_PATTERN.match(raw.strip())
    if match is None:
        raise ProbeUsageError(
            f"Expectation {raw!r} is not '<target><op><count>'. Expected e.g. "
            f"'importlib.metadata:entry_points<=3' or 'subprocess==0'; operators: <=, ==, >=."
        )
    return Expectation(match["name"].strip(), match["op"], int(match["count"]))


def _resolve_owner(target: str) -> tuple[object, str]:
    """Return (object holding the attribute, attribute name) for ``module:qualname``."""
    module_name, separator, qualname = target.partition(":")
    if not separator or not module_name or not qualname:
        raise ProbeUsageError(
            f"Target {target!r} is not 'module:qualname'. Expected e.g. "
            f"'importlib.metadata:entry_points' or 'jinja2.environment:Environment.compile'."
        )
    try:
        owner: object = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProbeUsageError(f"Target {target!r}: module {module_name!r} does not import: {exc}.") from exc
    *parents, attribute = qualname.split(".")
    for part in parents:
        if not hasattr(owner, part):
            raise ProbeUsageError(f"Target {target!r}: {module_name}.{part} does not exist.")
        owner = getattr(owner, part)
    if not callable(getattr(owner, attribute, None)):
        raise ProbeUsageError(f"Target {target!r}: {qualname} is not a callable attribute of {module_name}.")
    return owner, attribute


def install_counter(target: str, counters: Counters) -> None:
    """Replace the target callable with a counting wrapper that delegates to it."""
    owner, attribute = _resolve_owner(target)
    original = getattr(owner, attribute)
    is_static = isinstance(owner, type) and isinstance(owner.__dict__.get(attribute), staticmethod)

    @functools.wraps(original)
    def counting(*args: object, **kwargs: object) -> object:
        counters.bump(target)
        return original(*args, **kwargs)

    setattr(owner, attribute, staticmethod(counting) if is_static else counting)
    _rebind_imported_references(original, counting)
    counters.counts.setdefault(target, 0)


def _rebind_imported_references(original: object, replacement: object) -> None:
    """Point every module global that already holds *original* at *replacement*.

    Resolving one target imports its module, and that import may run ``from x import y`` for
    another target before that target's counter exists; without this, such a binding keeps the
    uncounted original and the probe under-counts.
    """
    for module in list(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        for name, value in list(namespace.items()):
            if value is original:
                setattr(module, name, replacement)


def install_subprocess_counter(counters: Counters) -> None:
    """Count every ``subprocess.Popen`` construction (``run``/``check_output`` go through it)."""
    original_init = subprocess.Popen.__init__

    @functools.wraps(original_init)
    def counting_init(self: subprocess.Popen[bytes], *args: object, **kwargs: object) -> None:
        counters.bump(SUBPROCESS_COUNTER)
        original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = counting_init  # type: ignore[method-assign]
    counters.counts.setdefault(SUBPROCESS_COUNTER, 0)


def counter_failures() -> list[str]:
    """Prove the installer counts a planted function and a planted method; return failures."""
    planted = types.ModuleType("_call_count_planted")

    def planted_function() -> int:
        return 1

    class PlantedClass:
        def method(self) -> int:
            return 2

    planted.planted_function = planted_function  # type: ignore[attr-defined]
    planted.PlantedClass = PlantedClass  # type: ignore[attr-defined]
    # A module that bound the function by name before the counter existed (`from x import y`).
    early_importer = types.ModuleType("_call_count_early_importer")
    early_importer.planted_function = planted_function  # type: ignore[attr-defined]
    sys.modules[planted.__name__] = planted
    sys.modules[early_importer.__name__] = early_importer
    counters = Counters()
    try:
        install_counter("_call_count_planted:planted_function", counters)
        install_counter("_call_count_planted:PlantedClass.method", counters)
        bound = planted.planted_function  # type: ignore[attr-defined]
        early = early_importer.planted_function  # type: ignore[attr-defined]
        results = [bound(), bound(), early(), PlantedClass().method()]
    finally:
        del sys.modules[planted.__name__]
        del sys.modules[early_importer.__name__]
    failures: list[str] = []
    if results != [1, 1, 1, 2]:
        failures.append(f"wrapped callables changed their results: {results} != [1, 1, 1, 2]")
    if counters.counts.get("_call_count_planted:planted_function") != 3:
        failures.append(f"function counter read {counters.counts} after 3 calls (one through an early import)")
    if counters.counts.get("_call_count_planted:PlantedClass.method") != 1:
        failures.append(f"method counter read {counters.counts} after 1 call")
    if not parse_expectation("x:y<=3").holds(3) or parse_expectation("x:y==0").holds(1):
        failures.append("expectation operators evaluate wrongly")
    return failures


def _run_generation(source: Path, language: str, output_root: Path) -> int:
    """Run one ``datrix generate`` in this process; return its exit code."""
    output = output_root / time.strftime("%Y%m%d-%H%M%S")
    argv = ["datrix", "generate", "--source", str(source), "--output", str(output), "--language", language]
    saved_argv = sys.argv
    sys.argv = argv
    try:
        from datrix_cli.main import app

        app()
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_FAILED
    finally:
        sys.argv = saved_argv
    return EXIT_OK


def _run_imports(modules: Sequence[str]) -> int:
    for module in modules:
        importlib.import_module(module)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/call-count.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    workload = parser.add_mutually_exclusive_group()
    workload.add_argument("--source", type=Path, help="system.dtrx to generate (generate workload)")
    workload.add_argument("--import", dest="import_modules", default="",
                          help="comma-separated modules to import (import workload)")
    parser.add_argument("--language", default="", help="generation language (generate workload)")
    parser.add_argument("--count", default="", help="comma-separated module:qualname targets to count")
    parser.add_argument("--expect", default="", help="comma-separated <target><op><n> bounds")
    parser.add_argument("--json", type=Path, default=None, help="also write the result JSON here")
    parser.add_argument("--self-test", action="store_true",
                        help="run only the self-test: the counter and the wrapper seam")
    parser.set_defaults(debug=False)
    return parser


def _split(raw: str) -> list[str]:
    return comma_values([raw])


def _check_the_counter_counts_planted_calls() -> None:
    failures = counter_failures()
    assert not failures, "; ".join(failures)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


def _workload_usage(args: argparse.Namespace) -> str:
    """Why *args* names no runnable workload, or ``""``."""
    if args.source is None and not args.import_modules:
        return "Usage: give --source <system.dtrx> --language <lang>, or --import <m1,m2>."
    if args.source is not None and not args.language:
        return "Usage: --source needs --language (any registered datrix.languages target)."
    return ""


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test([_check_the_counter_counts_planted_calls], wrapper=WRAPPER, module=MODULE,
                             parser=build_parser(), folder=METRICS_SCRIPTS_DIR)
    failures = counter_failures()
    if failures:
        print("CALL_COUNT self-test FAILED: " + "; ".join(failures), file=sys.stderr)
        return EXIT_USAGE
    usage = _workload_usage(args)
    if usage:
        print(usage, file=sys.stderr)
        return EXIT_USAGE
    # Both workloads import the datrix-* packages; checked before the counters exist, so the check's
    # own child processes are not counted.
    if not require_packages():
        return EXIT_FAILED
    try:
        expectations = [parse_expectation(raw) for raw in _split(args.expect)]
        counters = Counters()
        install_subprocess_counter(counters)
        for target in _split(args.count):
            install_counter(target, counters)
    except ProbeUsageError as exc:
        print(f"CALL_COUNT usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    unknown = [e.name for e in expectations if e.name not in counters.counts]
    if unknown:
        print(f"CALL_COUNT usage error: expectations name targets not counted: {unknown}. Add them to --count.", file=sys.stderr)
        return EXIT_USAGE
    return _measure(args, expectations, counters)


def _measure(args: argparse.Namespace, expectations: Sequence[Expectation], counters: Counters) -> int:
    """Run the workload with the counters installed, print the result, and judge the bounds."""
    started = time.perf_counter()
    if args.source is not None:
        workload_exit = _run_generation(args.source.resolve(), args.language, DEFAULT_OUTPUT_ROOT)
    else:
        workload_exit = _run_imports(_split(args.import_modules))
    wall_s = round(time.perf_counter() - started, 2)

    verdicts = {e.render(): e.holds(counters.counts[e.name]) for e in expectations}
    result = {"wall_s": wall_s, "workload_exit": workload_exit, "counts": counters.counts, "expectations": verdicts}
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered + "\n", encoding="utf-8")
    passed = workload_exit == EXIT_OK and all(verdicts.values())
    print(f"CALL_COUNT {'PASSED' if passed else 'FAILED'} wall_s={wall_s} workload_exit={workload_exit}")
    return EXIT_OK if passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
