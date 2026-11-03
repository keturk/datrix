"""Run the related test selections of different packages side by side, the runs of one package one after another.

Each unit is one ``test.ps1`` run of one package. Units of the same package never overlap: they share the
package's ``.test_results`` and its install. Units of different packages start only while the packages already
running leave cores free (``datrix_scripts.test.affected_gate.admits_next``, the rule the affected gate uses), each
package capped to the xdist worker count its predicted share of the work earns
(``proportional_worker_allotment``), so the machine is never asked for more workers than it has cores.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Final, TypeVar

from datrix_scripts.test.affected_gate import (
    admits_next,
    predicted_cpu_seconds,
    proportional_worker_allotment,
)
from datrix_scripts.test.test import child_environment

XDIST_WORKERS_ENV: Final = "PYTEST_XDIST_AUTO_NUM_WORKERS"

Result = TypeVar("Result")


def worker_allotment(package_dirs: Mapping[str, Path], packages: Sequence[str], cores: int) -> dict[str, int]:
    """The xdist workers of each of *packages*, in proportion to its predicted CPU work within the whole set."""
    return proportional_worker_allotment({name: predicted_cpu_seconds(package_dirs[name]) for name in packages}, cores)


def logical_cores() -> int:
    return os.cpu_count() or 1


def run_units(units: Sequence[tuple[str, int]], run_one: Callable[[int, dict[str, str]], Result],
              allotment: Mapping[str, int], cores: int) -> dict[int, Result]:
    """Run every unit, ``(package, number)``, through ``run_one(number, environment)``; the results by number.

    A package's units run in the order given, on one thread; packages overlap while their worker allotments fit
    in *cores*. When a unit raises, no new package starts, the running ones finish, and the first error is raised.
    """
    chains: dict[str, list[int]] = {}
    for package, number in units:
        chains.setdefault(package, []).append(number)
    pending = sorted(chains, key=lambda name: (-allotment[name], -len(chains[name])))
    results: dict[int, Result] = {}
    running: dict[Future[dict[int, Result]], str] = {}
    failure: Exception | None = None
    with ThreadPoolExecutor(max_workers=max(1, len(chains))) as pool:
        while pending or running:
            while failure is None and pending and admits_next(
                sum(allotment[name] for name in running.values()), len(running), allotment[pending[0]], cores, None
            ):
                package = pending.pop(0)
                environment = {**child_environment(os.environ), XDIST_WORKERS_ENV: str(allotment[package])}
                running[pool.submit(_run_chain, chains[package], run_one, environment)] = package
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                del running[future]
                try:
                    results.update(future.result())
                except Exception as exc:
                    failure = failure or exc
    if failure is not None:
        raise failure
    return results


def _run_chain(numbers: Sequence[int], run_one: Callable[[int, dict[str, str]], Result],
               environment: dict[str, str]) -> dict[int, Result]:
    return {number: run_one(number, environment) for number in numbers}
