"""``fixture-author.ps1 repoint -Package <p>``: rewrite a package's test modules to read the shared fixture corpus.

Every module row ``needs.json`` holds for the package is one job. A module holding tests serves those tests:
each test whose input can be shared reads the corpus entry the library plan places it in (``library_plan``),
with the renames of ``renames.json`` applied to its needs; a test with a ``local`` reason keeps its input in
the package, marked ``// @local <reason>`` (``repoint_drafts``). A module holding no test (a ``conftest.py``,
a helper) serves the tests of the modules that depend on it: every test module under a conftest's directory,
every test module importing a helper; those are what proves its rewrite, and a helper no test module imports
is queued unasked (nothing could prove it).

A module already done (below) is skipped. Each round asks the model for
every module left at once, then takes the answers one at a time: a draft adding a secret-looking literal is
queued at once and never written; one the read-only checks refuse goes back. Otherwise the module and its
files are saved to ``.tmp/fixture-author/undo/`` and written, and the rewrite is kept only when the module
keeps every test it had, its assertion count (``assert`` plus ``pytest.raises`` blocks, by AST) has not
fallen, it reads no input but a ``// @local`` one, it names a corpus accessor when it holds a test with no
local reason, and ``test.ps1 <p> -Specific`` over the modules that prove it passes. Otherwise every file is written back from the undo copy byte for byte (never a git command) and the
failure goes back. After at most :data:`MAX_ROUNDS` rounds a module still failing is written to
``queue/repoint-<package>--<module>.md`` with why and its last draft. A run finding an undo record left by an
interrupted run writes it back first.

The run ends on the package's set comparison, in code: inventoried − rewritten − local, where a module is
done when it reads no input but a ``// @local`` one and names a corpus accessor if it holds a test with no
local reason; it is local when every test it holds keeps a local input
and it reads no corpus entry, rewritten otherwise. The run exits 0 only when that remainder is empty.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_testing.corpus import CORPUS_ROOT, ENTRY_SUFFIX, corpus_reached_files
from datrix_testing.parsing import register_installed_parsers

from datrix_scripts.dev.fixture_author.drafting import FEEDBACK_OUTPUT_LINES, MAX_ROUNDS, QUEUE_DIR
from datrix_scripts.dev.fixture_author.library import RENAMES_FILE
from datrix_scripts.dev.fixture_author.library_check import library_choices
from datrix_scripts.dev.fixture_author.library_drafts import LibraryDraftError, Rename, read_renames
from datrix_scripts.dev.fixture_author.library_plan import (
    InventoriedModule,
    LibraryPlan,
    LibraryPlanError,
    plan_library,
    platform_entries,
    read_inventory_modules,
    read_needs_inventory,
)
from datrix_scripts.dev.fixture_author.needs import (
    ModuleInput,
    NeedsScanError,
    current_inputs,
    needs_packages,
)
from datrix_scripts.dev.fixture_author.needs_command import EXIT_INCOMPLETE, NEEDS_FILE, block_families
from datrix_scripts.dev.fixture_author.needs_reading import context_window, node_kinds
from datrix_scripts.dev.fixture_author.repoint_drafts import (
    REPOINT_RULES,
    REPOINT_SCHEMA,
    ModuleDraft,
    ModulePrompt,
    assertion_count,
    defined_tests,
    draft_problems,
    module_queue_text,
    need_names,
    new_secret_sites,
    parse_module_answer,
    repoint_user_prompt,
    unread_corpus,
    unshared_inputs,
)
from datrix_scripts.dev.fixture_author.repoint_jobs import (
    UNDO_DIR,
    ModuleJob,
    PackageStatus,
    RepointError,
    SpecificRunner,
    UndoStore,
    module_inputs_now,
    package_status,
    plan_jobs,
    queue_file,
    run_specific,
)
from datrix_scripts.gate_harness import UsageError
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings, LocalLlmUnavailable
from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import (
    EXIT_NO_MODEL,
    JSON_MAX_TOKENS,
    AssistError,
    ContentFilter,
    NoModelAnswer,
    ask_json,
    parallel,
)

logger = logging.getLogger(__name__)

_ENCODING: Final = "utf-8"


# --------------------------------------------------------------------------- the run


@dataclass(frozen=True)
class Repointer:
    """What repointing one package reads: the model pool, the content filter, the package, its inventoried
    modules and jobs, the renames, the runner proving a rewrite, and where it saves, queues and reads."""

    pool: LocalLlmPool
    content: ContentFilter
    package_dir: Path
    rows: tuple[InventoriedModule, ...]
    jobs: tuple[ModuleJob, ...]
    renames: tuple[Rename, ...]
    runner: SpecificRunner
    workspace: Path = WORKSPACE_DIR
    corpus: Path = CORPUS_ROOT
    undo: UndoStore = UndoStore(UNDO_DIR)
    queue_dir: Path = QUEUE_DIR
    max_rounds: int = MAX_ROUNDS


@dataclass(frozen=True)
class RepointOutcome:
    """What one run kept, found done, queued, wrote back first, and the package's status after it."""

    kept: tuple[str, ...]
    done: tuple[str, ...]
    queued: Mapping[str, tuple[str, ...]]
    recovered: str | None
    status: PackageStatus
    queue_files: tuple[Path, ...]


@dataclass
class _Run:
    repointer: Repointer
    prompts: dict[str, ModulePrompt]
    originals: dict[str, bytes]
    done: set[str]
    window: int = 0
    drafts: dict[str, ModuleDraft] = field(default_factory=dict)
    problems: dict[str, list[str]] = field(default_factory=dict)
    kept: set[str] = field(default_factory=set)
    queued: dict[str, list[str]] = field(default_factory=dict)
    entry_files: dict[str, dict[str, str]] = field(default_factory=dict)


def _reached(run: _Run, entry: str) -> dict[str, str]:
    """The text of every corpus file *entry* reaches, by path relative to the corpus root."""
    if entry not in run.entry_files:
        corpus = run.repointer.corpus.resolve()
        run.entry_files[entry] = {
            path.relative_to(corpus).as_posix(): path.read_text(encoding=_ENCODING)
            for path in corpus_reached_files(run.repointer.corpus, entry)
        }
    return run.entry_files[entry]


def _entry_files(run: _Run, job: ModuleJob) -> dict[str, str]:
    """Each entry file of *job*, and every file those entries reach that names something its tests need."""
    names = need_names(need for test in job.tests for need in test.needs)
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(names))) + r")\b") if names else None
    files: dict[str, str] = {}
    for entry in job.entries:
        for path, text in _reached(run, entry).items():
            if path == f"{entry}{ENTRY_SUFFIX}" or (pattern is not None and pattern.search(text)):
                files[path] = text
    return files


def _prompt(run: _Run, job: ModuleJob, inputs: tuple[ModuleInput, ...]) -> ModulePrompt:
    text = run.originals[job.module].decode(_ENCODING)
    return ModulePrompt(job.module, text, job.tests, job.run_files, inputs, _entry_files(run, job),
                        run.repointer.renames)


def _queue_at_once(run: _Run, job: ModuleJob) -> str | None:
    """Why *job* is queued without asking: its module is gone, or no test module could prove it."""
    if not (run.repointer.workspace / job.module).is_file():
        return "the module no longer exists. Fix: rerun fixture-author.ps1 needs."
    if not job.run_files:
        return "no test module imports or sits under this module, so no -Specific run can prove a rewrite."
    return None


def _start(repointer: Repointer) -> _Run:
    found = module_inputs_now(repointer.package_dir, repointer.workspace)
    status = package_status(repointer.rows, found, repointer.workspace)
    done = {job.module for job in repointer.jobs if job.module not in status.pending}
    originals = {job.module: (repointer.workspace / job.module).read_bytes() for job in repointer.jobs
                 if (repointer.workspace / job.module).is_file()}
    run = _Run(repointer, {}, originals, done)
    for job in repointer.jobs:
        if job.module in done:
            continue
        reason = _queue_at_once(run, job)
        if reason is not None:
            run.queued[job.module] = [reason]
            continue
        run.prompts[job.module] = _prompt(run, job, found.get(job.module, ()))
    windows = [context_window(REPOINT_RULES, repoint_user_prompt(prompt, [], None) + prompt.text * 2)
               for prompt in run.prompts.values()]
    run.window = max(windows, default=0)
    return run


def _ask(run: _Run, module: str, user: str) -> ModuleDraft | str:
    text = run.prompts[module].text
    try:
        answer = ask_json(run.repointer.pool, REPOINT_RULES, user, REPOINT_SCHEMA,
                          max_tokens=len(text) // CHARS_PER_TOKEN + JSON_MAX_TOKENS, context_window=run.window)
    except NoModelAnswer as error:
        return str(error)
    return parse_module_answer(answer)


def _queue(run: _Run, module: str, problems: Sequence[str]) -> None:
    run.queued[module] = list(problems)


def _replace_problems(run: _Run, module: str, draft: ModuleDraft) -> list[str]:
    """Why *draft* may not replace a file it lists: another module of the package reads it."""
    workspace = run.repointer.workspace
    existing = {(workspace / path).resolve() for path, _ in draft.files if (workspace / path).is_file()}
    if not existing:
        return []
    readers: dict[Path, list[str]] = {path: [] for path in existing}
    for reader, inputs in module_inputs_now(run.repointer.package_dir, workspace).items():
        for each in inputs:
            if reader != module and each.path is not None and each.path.resolve() in readers:
                readers[each.path.resolve()].append(reader)
    return [f"file {path.relative_to(workspace.resolve()).as_posix()!r} is read by {sorted(set(names))}; create a "
            "new file or read it unchanged." for path, names in readers.items() if names]


def _write(run: _Run, module: str, draft: ModuleDraft) -> None:
    workspace = run.repointer.workspace
    targets = [(workspace / module, draft.module), *((workspace / path, text) for path, text in draft.files)]
    run.repointer.undo.save(module, [path for path, _ in targets])
    for path, text in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=_ENCODING, newline="")


def _output_tail(output: str) -> str:
    return "\n".join(output.strip().splitlines()[-FEEDBACK_OUTPUT_LINES:])


def _read_problems(run: _Run, module: str) -> list[str]:
    """Why the written *module* is not kept, read without running it: a test or an assertion it lost, an
    input it may not read, a corpus entry its shared tests do not read (the package status's own rule)."""
    repointer = run.repointer
    path = repointer.workspace / module
    original = ast.parse(run.originals[module].decode(_ENCODING))
    rewritten = ast.parse(path.read_text(encoding=_ENCODING))
    problems: list[str] = []
    lost = defined_tests(original) - defined_tests(rewritten)
    if lost:
        problems.append(f"the rewrite drops the tests {sorted(lost)}; every test stays.")
    before, after = assertion_count(original), assertion_count(rewritten)
    if after < before:
        problems.append(f"the assertion count fell from {before} to {after} (assert statements plus pytest.raises "
                        "blocks); every assertion stays.")
    try:
        problems.extend(unshared_inputs(current_inputs(path, repointer.package_dir, repointer.workspace)))
    except (NeedsScanError, FixtureScanError) as error:
        problems.append(str(error))
    row = next(row for row in repointer.rows if row.module == module)
    problems.extend(unread_corpus(row.tests, rewritten))
    return problems


def _judge(run: _Run, job: ModuleJob) -> list[str]:
    """Why *job*'s written rewrite is not kept; empty when it is."""
    repointer = run.repointer
    problems = _read_problems(run, job.module)
    if problems:
        return problems
    verdict = repointer.runner(repointer.package_dir, job.run_files)
    if not verdict.passed:
        problems.append(f"test.ps1 {repointer.package_dir.name} -Specific {list(job.run_files)} failed:\n"
                        f"{_output_tail(verdict.output)}")
    return problems


def _write_back(run: _Run, module: str) -> None:
    """Write *module*'s rewrite back from the undo copy and prove the module holds its original bytes.

    Raises:
        RepointError: the module does not hold its original bytes after the write-back.
    """
    run.repointer.undo.restore()
    path = run.repointer.workspace / module
    if path.read_bytes() != run.originals[module]:
        raise RepointError(f"{path} does not hold its original bytes after the write-back from "
                           f"{run.repointer.undo.root}. Fix: restore it by hand before any other run.")


def _take(run: _Run, job: ModuleJob, answer: ModuleDraft | str) -> None:
    """Record *job*'s answer: sent back, refused and queued, or written and judged (kept or written back)."""
    module = job.module
    if isinstance(answer, str):
        run.problems[module] = [answer]
        return
    secrets = new_secret_sites(run.prompts[module].text, answer)
    if secrets:
        run.drafts.pop(module, None)
        _queue(run, module, [f"the draft adds a string literal that looks like a raw secret at {secrets}; it is "
                             "refused and never written (the value is not repeated)."])
        return
    run.drafts[module] = answer
    problems = [*draft_problems(run.repointer.package_dir.name, answer), *_replace_problems(run, module, answer)]
    if problems:
        run.problems[module] = problems
        return
    _write(run, module, answer)
    problems = _judge(run, job)
    if problems:
        _write_back(run, module)
        run.problems[module] = problems
        return
    run.repointer.undo.clear()
    run.kept.add(module)
    run.problems.pop(module, None)


def _round(run: _Run) -> bool:
    """Ask for every module not done, kept or queued, then take each answer in turn; whether anything was
    asked."""
    users: dict[str, str] = {}
    for module, prompt in run.prompts.items():
        if module in run.kept or module in run.queued:
            continue
        user = repoint_user_prompt(prompt, run.problems.get(module, []), run.drafts.get(module))
        if run.repointer.content.carries_term(user):
            _queue(run, module, ["the request carries a registered customer term, so it is never sent to a "
                                 "model; finish the module by hand."])
            continue
        users[module] = user
    if not users:
        return False
    asking = list(users)
    answers = parallel(asking, lambda module: _ask(run, module, users[module]))
    jobs = {job.module: job for job in run.repointer.jobs}
    for module, answer in zip(asking, answers, strict=True):
        _take(run, jobs[module], answer)
    return True


def _write_queues(run: _Run) -> list[Path]:
    repointer = run.repointer
    package = repointer.package_dir.name
    files: list[Path] = []
    for job in repointer.jobs:
        path = queue_file(repointer.queue_dir, package, job.module)
        if job.module not in run.queued:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        prompt = run.prompts.get(job.module) or ModulePrompt(job.module, "", job.tests, job.run_files, (), {}, ())
        path.write_text(module_queue_text(prompt, run.queued[job.module], run.drafts.get(job.module)),
                        encoding=_ENCODING)
        files.append(path)
    return files


def repoint_package(repointer: Repointer) -> RepointOutcome:
    """Rewrite every module of *repointer* not done, keep what passes, queue the rest.

    Raises:
        LocalLlmUnavailable: No local model can serve; a round's answers are all in before any is written, so
            no module is left written and unjudged.
        RepointError: A rewrite could not be written back byte for byte.
    """
    recovered = repointer.undo.restore()
    register_installed_parsers()
    run = _start(repointer)
    if run.prompts:
        repointer.pool.activate(run.window)
        for _ in range(repointer.max_rounds):
            if not _round(run):
                break
    for module in run.prompts:
        if module not in run.kept and module not in run.queued:
            _queue(run, module, run.problems.get(module, ["no answer was kept."]))
    queue_files = tuple(_write_queues(run))
    status = package_status(repointer.rows, module_inputs_now(repointer.package_dir, repointer.workspace),
                            repointer.workspace)
    queued = {module: tuple(problems) for module, problems in sorted(run.queued.items())}
    return RepointOutcome(tuple(sorted(run.kept)), tuple(sorted(run.done)), queued, recovered, status, queue_files)


def print_repoint_outcome(outcome: RepointOutcome) -> None:
    """One line per module kept, done and queued, then the package's set comparison and the queue files."""
    if outcome.recovered is not None:
        print(f"[UNDO] {outcome.recovered}: written back from the record an interrupted run left")
    for module in outcome.done:
        print(f"[ OK ] {module}: already done")
    for module in outcome.kept:
        print(f"[ OK ] {module}: rewritten and kept")
    for module, problems in outcome.queued.items():
        print(f"[QUEUE] {module}: {len(problems)} problem(s), queued")
    status = outcome.status
    remainder = sorted(status.remainder())
    print(f"inventoried {len(status.inventoried)} - rewritten {len(status.rewritten)} - local {len(status.local)} "
          f"= {len(remainder)} not done{f': {remainder}' if remainder else ''}")
    for path in outcome.queue_files:
        print(f"  wrote {path}")


def run_repoint(repointer: Repointer) -> int:
    """Repoint the package; the exit code: 0 every inventoried module is rewritten or local, 1 a module is not
    done (queued) or a rewrite could not be written back, :data:`EXIT_NO_MODEL` no local model could serve
    (with none from the start, nothing is written)."""
    try:
        outcome = repoint_package(repointer)
    except LocalLlmUnavailable as error:
        print(f"ERROR: no local model can repoint {repointer.package_dir.name}; a module kept in an earlier round "
              f"stays, none is left written and unjudged, and no queue file is written: {error}")
        return EXIT_NO_MODEL
    except (RepointError, NeedsScanError, FixtureScanError) as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    print_repoint_outcome(outcome)
    return EXIT_INCOMPLETE if outcome.status.remainder() else 0


def package_dir_named(package: str, workspace: Path) -> Path:
    """The directory of the workspace package *package*, which holds ``tests/``.

    Raises:
        UsageError: no workspace package of that name holds ``tests/``.
    """
    packages = {path.name: path for path in needs_packages(workspace)}
    if package not in packages:
        raise UsageError(f"-Package {package!r} is no workspace package holding tests/; the packages that do: "
                         f"{sorted(packages)}.")
    return packages[package]


def _plan(needs_file: Path, corpus: Path) -> LibraryPlan:
    register_installed_parsers()
    return plan_library(read_needs_inventory(needs_file), block_families(node_kinds()), platform_entries(),
                        library_choices(corpus))


def run_repoint_command(package: str, settings: LocalLlmSettings, needs_file: Path = NEEDS_FILE,
                        corpus: Path = CORPUS_ROOT) -> int:
    """``fixture-author.ps1 repoint -Package <package>``: rewrite the package's inventoried modules.

    Raises:
        UsageError: *package* is empty or no workspace package holding tests, *needs_file* does not exist, or
            it lists no module of *package*.
    """
    if not package:
        raise UsageError("-Package is required: the package whose test modules are repointed.")
    package_dir = package_dir_named(package, WORKSPACE_DIR)
    if not needs_file.is_file():
        raise UsageError(f"{needs_file} does not exist. Fix: run `fixture-author.ps1 needs` first; the modules are "
                         "repointed from its inventory.")
    try:
        rows = tuple(row for row in read_inventory_modules(needs_file) if row.package == package)
        renames = read_renames(RENAMES_FILE)
        jobs = plan_jobs(rows, _plan(needs_file, corpus), renames, package_dir, WORKSPACE_DIR)
        content = ContentFilter(WORKSPACE_DIR)
    except (LibraryPlanError, LibraryDraftError, RepointError, AssistError, ValueError, FileNotFoundError) as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    if not rows:
        raise UsageError(f"{needs_file} lists no module of {package}. Fix: rerun `fixture-author.ps1 needs`.")
    from datrix_scripts.venv import require_packages

    if not require_packages():
        print("ERROR: the package install check failed, so no test.ps1 -Specific run could prove a rewrite.")
        return EXIT_INCOMPLETE
    pool = LocalLlmPool(settings, report=lambda line: logger.info("%s", line))
    return run_repoint(Repointer(pool, content, package_dir, rows, jobs, renames, run_specific, corpus=corpus))


__all__ = [
    "RepointOutcome",
    "Repointer",
    "package_dir_named",
    "print_repoint_outcome",
    "repoint_package",
    "run_repoint",
    "run_repoint_command",
]
