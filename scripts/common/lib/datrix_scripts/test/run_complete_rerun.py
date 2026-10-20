"""Which projects of a test set ``run-complete -Rerun`` runs again: the ones whose latest results did not pass.

A project is selected when its generated output has no ``.test_results`` at all, or when a test type the run
does not skip did not pass last time:

- unit tests (unless ``-Skip3``): no ``unit-tests-*`` run, no ``index.json`` in any of them, or the newest
  ``index.json`` (by modification time) does not read ``"result": "PASSED"``;
- deployment tests (unless ``-Skip4``): no ``deploy-test-*`` run, the newest one (by its timestamped name) has
  no ``failures.json`` (it never finished), or its ``summary.total`` is not 0.

A result file that cannot be read as that shape (no ``result``, no integer ``summary.total``) counts as not
passed: a project is skipped only on a result that says it passed.

The output directory is ``.generated/<language>/<runtime>/<provider>/<project>``. The provider segment comes
from each project's ``config/system.dcfg`` at generation time, so it is found on disk: the first provider
directory (in name order) that holds the project, else the ``local`` layout of a project never generated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

TEST_RESULTS_DIR: Final = ".test_results"
GENERATED_DIR: Final = ".generated"
SHOWCASE_DIR_NAME: Final = "datrix"
EXAMPLES_PREFIX: Final = "examples/"
SYSTEM_FILE_SUFFIX: Final = "/system.dtrx"
DATRIX_FILE_SUFFIX: Final = ".dtrx"
UNGENERATED_PROVIDER: Final = "local"
UNIT_RUN_PREFIX: Final = "unit-tests-"
DEPLOY_RUN_PREFIX: Final = "deploy-test-"
INDEX_FILE: Final = "index.json"
FAILURES_FILE: Final = "failures.json"
PASSED_RESULT: Final = "PASSED"
DOMAINS_TEST_SET: Final = "domains"


class RerunConfigError(Exception):
    """test-projects.json does not have the shape a rerun reads."""


class UnknownTestSetError(Exception):
    """The test set named for a rerun is not in test-projects.json."""

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(f"Test set '{name}' not found in test-projects.json.")
        self.name = name
        self.available = available


@dataclass(frozen=True)
class RerunProject:
    """A project to run again: its name, its source file and its generated output directory."""

    name: str
    example_path: Path
    output_path: Path


@dataclass(frozen=True)
class RerunSelection:
    """The projects of *test_set* that need running again, out of *total* names the set lists."""

    test_set: str
    total: int
    projects: list[RerunProject]


def rerun_test_set(domains: bool, test_set: str) -> str:
    """The test set a rerun scans: ``domains`` for ``-Domains``, else ``-TestSet`` (default ``all``)."""
    return DOMAINS_TEST_SET if domains else test_set


def project_base(source_path: str) -> str:
    """``examples/02-domains/shop/system.dtrx`` -> ``02-domains/shop``; ``examples/x/y.dtrx`` -> ``x/y``."""
    relative = source_path.replace("\\", "/").removeprefix(EXAMPLES_PREFIX)
    if relative.endswith(SYSTEM_FILE_SUFFIX):
        return relative.removesuffix(SYSTEM_FILE_SUFFIX)
    return relative.removesuffix(DATRIX_FILE_SUFFIX)


def _subdirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted((entry for entry in path.iterdir() if entry.is_dir()), key=lambda entry: entry.name.casefold())


def project_output_dir(generated_root: Path, language: str, runtime: str, base: str) -> Path:
    """The project's generated output under the first provider directory that holds it, else under ``local``."""
    runtime_dir = generated_root / language / runtime
    for provider_dir in _subdirs(runtime_dir):
        if (provider_dir / base).exists():
            return provider_dir / base
    return runtime_dir / UNGENERATED_PROVIDER / base


def _runs(results_dir: Path, prefix: str) -> list[Path]:
    return [entry for entry in _subdirs(results_dir) if entry.name.casefold().startswith(prefix)]


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def unit_tests_need_rerun(results_dir: Path) -> bool:
    """True unless the newest unit-test ``index.json`` reads ``"result": "PASSED"``."""
    indexes = [run / INDEX_FILE for run in _runs(results_dir, UNIT_RUN_PREFIX) if (run / INDEX_FILE).is_file()]
    if not indexes:
        return True
    latest = max(indexes, key=lambda index: index.stat().st_mtime)
    data = _read_json(latest)
    return not (isinstance(data, dict) and data.get("result") == PASSED_RESULT)


def _failure_total(data: object) -> int | None:
    summary = data.get("summary") if isinstance(data, dict) else None
    total = summary.get("total") if isinstance(summary, dict) else None
    return total if isinstance(total, int) else None


def deploy_tests_need_rerun(results_dir: Path) -> bool:
    """True unless the newest deploy-test run finished with ``summary.total`` 0 in its ``failures.json``."""
    runs = _runs(results_dir, DEPLOY_RUN_PREFIX)
    if not runs:
        return True
    failures = max(runs, key=lambda run: run.name) / FAILURES_FILE
    if not failures.is_file():
        return True
    return _failure_total(_read_json(failures)) != 0


def needs_rerun(output_dir: Path, *, check_unit: bool, check_deploy: bool) -> bool:
    """Whether the project at *output_dir* is run again, inspecting only the test types not skipped."""
    results_dir = output_dir / TEST_RESULTS_DIR
    if not results_dir.exists():
        return check_unit or check_deploy
    if check_unit and unit_tests_need_rerun(results_dir):
        return True
    return check_deploy and deploy_tests_need_rerun(results_dir)


def _projects_by_name(config: dict[str, object]) -> dict[str, dict[str, str]]:
    categories = config.get("projects")
    if not isinstance(categories, dict):
        raise RerunConfigError(
            "test-projects.json has no 'projects' object. Expected categories mapping to lists of "
            "{name, path} projects; restore scripts/config/test-projects.json."
        )
    return {project["name"]: project for category in categories.values() for project in category}


def _test_set_names(config: dict[str, object], test_set: str) -> list[str]:
    test_sets = config.get("testSets")
    if not isinstance(test_sets, dict):
        raise RerunConfigError(
            "test-projects.json has no 'testSets' object. Expected test-set names mapping to project-name "
            "lists; restore scripts/config/test-projects.json."
        )
    if test_set not in test_sets:
        raise UnknownTestSetError(test_set, list(test_sets))
    return list(test_sets[test_set])


def select_rerun_projects(
    config: dict[str, object],
    test_set: str,
    *,
    workspace: Path,
    language: str,
    runtime: str,
    check_unit: bool,
    check_deploy: bool,
) -> RerunSelection:
    """The projects of *test_set* (from the test-projects.json *config*) that need running again.

    A name the set lists but no category defines is skipped, as generation skips it.
    """
    names = _test_set_names(config, test_set)
    projects = _projects_by_name(config)
    generated_root = workspace / GENERATED_DIR
    selected: list[RerunProject] = []
    for name in names:
        if name not in projects:
            continue
        source = projects[name]["path"].replace("\\", "/")
        output_dir = project_output_dir(generated_root, language, runtime, project_base(source))
        if needs_rerun(output_dir, check_unit=check_unit, check_deploy=check_deploy):
            selected.append(RerunProject(name, workspace / SHOWCASE_DIR_NAME / source, output_dir))
    return RerunSelection(test_set, len(names), selected)
