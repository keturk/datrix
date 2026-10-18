#!/usr/bin/env python3
"""
Complete Workflow Runner for Datrix
Executes all validation, generation, and testing steps in sequence

Usage:
    python scripts/test/lib/run_complete.py <example_path> [output_path]  # output_path optional (from test-projects.json)
    python scripts/test/lib/run_complete.py -All # Run all examples
    python scripts/test/lib/run_complete.py -All --test-set foundation # Run foundation examples only
    (PYTHONPATH=scripts/common/lib; run-complete.ps1 sets it)
"""

import argparse
import atexit
import contextlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

logger = logging.getLogger(__name__)

# Sentinel: git SHA not yet resolved from disk (env vars checked first each call).
_GIT_HEAD_SHA_UNSET = object()
_git_head_sha_memo: Any = _GIT_HEAD_SHA_UNSET

# Ensure stdout/stderr handle Unicode (Docker output contains progress bars, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from datrix_codegen_kernel.generation.test_runner_entry_point import (  # noqa: E402
    DEPLOY_TESTS_SWITCH,
    PARALLEL_ARGUMENT,
    RESULTS_DIR_ARGUMENT,
    TEST_RUNNER_ENTRY_POINT,
    UNIT_TESTS_SWITCH,
    VERBOSE_ARGUMENT,
)

from datrix_scripts.aggregate_test_writer import AggregateTestWriter  # noqa: E402
from datrix_scripts.deploy_test_aggregate_writer import DeployTestAggregateWriter  # noqa: E402
from datrix_scripts.deploy_test_log_writer import DeployTestLogWriter  # noqa: E402
from datrix_scripts.generated_test_log_writer import GeneratedTestLogWriter  # noqa: E402
from datrix_scripts.local_llm import (  # noqa: E402
    ChatRequest,
    LocalLlmSettings,
    add_local_llm_arguments,
    advisory_text,
    local_llm_settings,
)
from datrix_scripts.logging_utils import ColorCodes, colorize  # noqa: E402
from datrix_scripts.paths import WORKSPACE_DIR  # noqa: E402
from datrix_scripts.powershell_ast import parse_scripts  # noqa: E402
from datrix_scripts.registered_targets import registered_language_names  # noqa: E402
from datrix_scripts.test_projects import (  # noqa: E402
    get_default_output_path,
    get_test_projects,
)
from datrix_scripts.venv import get_venv_python  # noqa: E402

# Global set to track all active subprocesses
_active_processes = set()
_process_lock = threading.Lock()
DEFAULT_LLM_NUM_PREDICT = 4096
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_CLUSTER_LIMIT = 12
# A captured child silent this long gets a one-time "in progress" note.
_PROGRESS_NOTE_AFTER_SECONDS = 2
_OUTPUT_POLL_SECONDS = 0.5


def register_process(process):
    """Register a subprocess for cleanup on exit."""
    with _process_lock:
        _active_processes.add(process)


def unregister_process(process):
    """Unregister a subprocess after it completes."""
    with _process_lock:
        _active_processes.discard(process)


def cleanup_processes():
    """Kill all active subprocesses."""
    with _process_lock:
        processes_to_kill = list(_active_processes)

        for process in processes_to_kill:
            _terminate_process(process)


def signal_handler(signum, frame):
    """Handle interrupt signals by cleaning up subprocesses."""
    print("\n\nInterrupted! Cleaning up subprocesses...", flush=True)
    cleanup_processes()
    sys.exit(130) # Exit code 130 indicates SIGINT (Ctrl-C)


# Register cleanup handler and signal handlers
atexit.register(cleanup_processes)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def print_step(step_num: int, title: str) -> None:
    """Print step header"""
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"STEP {step_num}: {title}", flush=True)
    print("=" * 60, flush=True)
    print(flush=True)


def print_success(message: str) -> None:
    """Print success message."""
    colored = colorize(message, ColorCodes.GREEN)
    print(colored, flush=True)


def print_info(message: str) -> None:
    """Print info message."""
    colored = colorize(message, ColorCodes.CYAN)
    print(colored, flush=True)


def print_warning(message: str) -> None:
    """Print warning message."""
    colored = colorize(message, ColorCodes.YELLOW)
    print(colored, flush=True)


def print_error(message: str) -> None:
    """Print error message."""
    colored = colorize(message, ColorCodes.RED)
    print(colored, flush=True)


def _strip_ansi(line: str) -> str:
    """Remove ANSI escape sequences for plain log output."""
    return re.sub(r"\x1b\[[0-9;]*m", "", line)



def _try_git_rev_parse(repo: Path) -> str | None:
    """Return current HEAD SHA if ``repo`` is a git checkout, else None."""
    try:
        if not repo.is_dir():
            return None
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip()
        if len(line) >= 7 and re.fullmatch(r"[0-9a-fA-F]+", line):
            return line.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_datrix_repo_sha() -> str | None:
    """SHA of the datrix repo for provenance (env override, else ``git rev-parse`` at datrix root)."""
    env_sha = (os.environ.get("DATRIX_REPO_SHA") or os.environ.get("DATRIX_CODEGEN_SHA") or "").strip()
    if env_sha:
        return env_sha
    global _git_head_sha_memo
    if _git_head_sha_memo is not _GIT_HEAD_SHA_UNSET:
        return _git_head_sha_memo
    try:
        root = get_paths()["datrix_root"]
    except Exception:
        _git_head_sha_memo = None
        return None
    _git_head_sha_memo = _try_git_rev_parse(root)
    return _git_head_sha_memo


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    description: str = "",
    capture_output: bool = False,
    log_file: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    """
    Run a command and return True if successful

    Args:
        cmd: Command and arguments as list
        cwd: Working directory
        description: Description of what the command does
        capture_output: If True, capture and return stdout/stderr while still displaying it
        log_file: If set, tee stdout/stderr to this file (plain text, no ANSI)
        env_overrides: Variables set in the child's environment on top of this process's

    Returns:
        Tuple of (success: bool, output: Optional[str])
    """
    if description:
        print_info(f"Running: {description}")

    print_info(f"Command: {' '.join(str(c) for c in cmd)}")

    env = (
        _child_env(env_overrides)
        if capture_output or log_file is not None or env_overrides
        else None
    )
    if log_file is not None:
        # Tee subprocess output to console and log file (same behavior as generate.ps1)
        return _report_exit(_run_teed(cmd, cwd, env, log_file), None)
    if capture_output:
        returncode, output = _run_captured(cmd, cwd, env)
        return _report_exit(returncode, output)
    try:
        run_env = _child_env(None) if env is None and get_datrix_repo_sha() else env
        result = subprocess.run(cmd, cwd=cwd, env=run_env)
    except KeyboardInterrupt:
        print("\n\nInterrupted!", flush=True)
        raise
    return _report_exit(result.returncode, None)


def _child_env(env_overrides: dict[str, str] | None) -> dict[str, str]:
    """This process's environment, unbuffered, carrying the datrix repo SHA
    when known, with *env_overrides* on top."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    sha = get_datrix_repo_sha()
    if sha:
        env["DATRIX_REPO_SHA"] = sha
    env.update(env_overrides or {})
    return env


def _report_exit(returncode: int, output: str | None) -> tuple[bool, str | None]:
    """Print the child's outcome and return ``(succeeded, output)``."""
    if returncode == 0:
        print_success("[OK] Success")
        return True, output
    print_error(f"[FAILED] Exit code: {returncode}")
    return False, output


def _popen_merged(
    cmd: list[str], cwd: Path | None, env: dict[str, str] | None
) -> subprocess.Popen[str]:
    """Start *cmd* line-buffered with stderr merged into a text stdout pipe,
    registered for cleanup on exit."""
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    register_process(process)
    return process


def _terminate_process(process: subprocess.Popen[str]) -> None:
    """Terminate a still-running child, killing it when it has not exited
    two seconds later. A child that is already gone is left alone."""
    with contextlib.suppress(OSError):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def _finish_process(process: subprocess.Popen[str]) -> str:
    """Unregister a child, give it a moment to exit, and return the output
    still unread on its pipe."""
    unregister_process(process)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=0.1)
    return process.stdout.read()


def _run_teed(
    cmd: list[str], cwd: Path | None, env: dict[str, str] | None, log_file: Path
) -> int:
    """Run *cmd*, printing each output line and appending it, ANSI-stripped,
    to *log_file*; return the exit code."""
    process = _popen_merged(cmd, cwd, env)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            for line in _teed_lines(process):
                print(line, end="", flush=True)
                f.write(_strip_ansi(line))
                f.flush()
    except KeyboardInterrupt:
        print("\n\nInterrupted! Terminating subprocess...", flush=True)
        _terminate_process(process)
        raise
    finally:
        remaining = _finish_process(process)
        if remaining:
            print(remaining, flush=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(_strip_ansi(remaining))
    return process.returncode


def _teed_lines(process: subprocess.Popen[str]) -> Iterator[str]:
    """Each output line of *process*, newline kept, until it exits."""
    while True:
        line = process.stdout.readline()
        if line:
            yield line
        elif process.poll() is not None:
            return


def _run_captured(
    cmd: list[str], cwd: Path | None, env: dict[str, str] | None
) -> tuple[int, str]:
    """Run *cmd*, printing and capturing each output line; return the exit
    code and the captured lines joined by newlines."""
    process = _popen_merged(cmd, cwd, env)
    output_lines: list[str] = []
    try:
        for line in _captured_lines(process):
            output_lines.append(line)
            print(line, flush=True)
    except KeyboardInterrupt:
        print("\n\nInterrupted! Terminating subprocess...", flush=True)
        _terminate_process(process)
        raise
    finally:
        _capture_remaining(_finish_process(process), output_lines)
    return process.returncode, "\n".join(output_lines)


def _captured_lines(process: subprocess.Popen[str]) -> Iterator[str]:
    """Each output line of *process*, newline stripped, until it exits. After
    two silent seconds a one-time progress note is printed, re-armed by the
    next line."""
    last_output_time = time.time()
    progress_shown = False
    while True:
        line = process.stdout.readline()
        if line:
            yield line.rstrip("\n\r")
            last_output_time = time.time()
            progress_shown = False
            continue
        if process.poll() is not None:
            return
        if time.time() - last_output_time > _PROGRESS_NOTE_AFTER_SECONDS:
            if not progress_shown:
                print(" [Test execution in progress - please wait for output...]", flush=True)
            progress_shown = True
        time.sleep(_OUTPUT_POLL_SECONDS)


def _capture_remaining(remaining: str, output_lines: list[str]) -> None:
    """Print the output left on a finished child's pipe, capturing its
    non-blank lines."""
    if not remaining:
        return
    for line in remaining.rstrip("\n\r").split("\n"):
        if line.strip():
            output_lines.append(line)
        print(line, flush=True)


def get_paths() -> dict[str, Path]:
    """Get all necessary paths relative to this script location"""
    script_dir = Path(__file__).parent.resolve()
    datrix_root = WORKSPACE_DIR
    datrix_dir = datrix_root / "datrix"

    return {
    "script_dir": script_dir,
    "datrix_root": datrix_root,
    "datrix_dir": datrix_dir,
    }


def _latest_aggregate_indexes(paths: dict[str, Path], max_files: int = 4) -> list[Path]:
    """Return newest aggregate-index.json files from generated test results."""
    root = paths["datrix_root"] / ".generated" / ".test_results"
    if not root.is_dir():
        return []
    candidates = sorted(
        root.rglob("aggregate-index.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    return candidates[:max_files]


def _load_aggregate_summary(index_path: Path, limit: int) -> dict[str, Any] | None:
    """Load a bounded aggregate index summary for LLM triage."""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    clusters = data.get("cross_project_clusters", [])
    suite_clusters = data.get("suite_failure_clusters", [])
    failed_projects = data.get("failed_projects", [])
    if not isinstance(clusters, list):
        clusters = []
    if not isinstance(suite_clusters, list):
        suite_clusters = []
    if not isinstance(failed_projects, list):
        failed_projects = []
    return {
        "aggregate_index": str(index_path),
        "language": data.get("language"),
        "platform": data.get("platform"),
        "total_projects": data.get("total_projects"),
        "projects_passed": data.get("projects_passed"),
        "projects_failed": data.get("projects_failed"),
        "total_counts": data.get("total_counts"),
        "cross_project_clusters": clusters[:limit],
        "suite_failure_clusters": suite_clusters[:limit],
        "failed_projects": failed_projects[:limit],
    }


def _run_llm_post_run_summary(
    paths: dict[str, Path],
    failed_steps: list[str],
    limit: int,
    settings: LocalLlmSettings,
    num_predict: int,
    temperature: float,
) -> str:
    """Run advisory local LLM summary over latest aggregate test indexes."""
    summaries = [
        item
        for path in _latest_aggregate_indexes(paths)
        for item in [_load_aggregate_summary(path, limit)]
        if item is not None
    ]
    prompt = "\n".join([
        "Review this Datrix complete workflow post-run test summary.",
        "",
        "Use only aggregate-index.json data and failed step names.",
        "Summarize:",
        "- top root causes",
        "- likely owning generator/template",
        "- recommended fix order",
        "- suspected transient failures to ignore or rerun",
        "",
        "Guardrails:",
        "- Advisory only. Do not modify files or decide pass/fail.",
        "- Never use full logs by default; rely on aggregate indexes and representative cluster metadata.",
        "- If evidence is insufficient, identify which index/error file to inspect next.",
        "",
        json.dumps(
            {
                "failed_steps": failed_steps,
                "aggregate_summaries": summaries,
            },
            indent=2,
        ),
    ])
    request = ChatRequest(
        system="You are a Datrix generated-test triage assistant. You produce advisory markdown only.",
        user=prompt,
        temperature=temperature,
        max_tokens=num_predict,
    )
    return advisory_text(settings, request, "LLM post-run summary")


def _print_llm_post_run_summary(args: argparse.Namespace, paths: dict[str, Path], failed_steps: list[str]) -> None:
    """Print an optional advisory LLM post-run summary."""
    if not args.llm_summary:
        return
    print()
    print_info("---")
    print_info("Local LLM Advisory Post-Run Summary")
    print_info("This section is advisory only. Deterministic workflow results own pass/fail.")
    text = _run_llm_post_run_summary(
        paths,
        failed_steps,
        args.llm_limit,
        local_llm_settings(args),
        args.llm_num_predict,
        args.llm_temperature,
    )
    print(text, flush=True)


def _find_powershell() -> str | None:
    """Find PowerShell executable (pwsh preferred, powershell on Windows)."""
    import platform as platform_mod

    if shutil.which("pwsh"):
        return "pwsh"
    if platform_mod.system() == "Windows" and shutil.which("powershell"):
        return "powershell"
    return None


def step1_syntax_checker(paths: dict[str, Path]) -> bool:
    """Step 1: Run syntax checker"""
    print_step(1, "Syntax Checker")

    script_path = paths["datrix_dir"] / "scripts" / "scan" / "syntax-checker.ps1"
    if not script_path.exists():
        print_error(f"Syntax checker not found at: {script_path}")
        return False

    pwsh_exe = _find_powershell()
    if pwsh_exe is None:
        print_error("PowerShell not found. Please install PowerShell (pwsh) or Windows PowerShell.")
        return False

    success, _ = run_command(
        [pwsh_exe, "-File", str(script_path)],
        cwd=paths["datrix_root"],
        description="Checking syntax of all .dtrx files in all repositories",
    )
    return success


def step2_generate(
    all_examples: bool,
    paths: dict[str, Path],
    example_path: str | None = None,
    output_path: str | None = None,
    language: str = "python",
    platform: str = "docker",
    test_set: str = "all",
    hosting: str | None = None,
) -> bool:
    """Step 2: Generate examples via generate.ps1.

    Delegates to generate.ps1 which handles package installation checks
    (Ensure-DatrixPackagesInstalled) before running the generation pipeline.
    This ensures changed source files are always picked up.

    Note: generate.ps1 creates its own log file under .generated/.results/.
    We do NOT create a separate log here to avoid file contention (both
    scripts use the same directory and naming pattern).
    """
    pwsh_exe = _find_powershell()
    if pwsh_exe is None:
        print_error("PowerShell not found. Please install PowerShell (pwsh) or Windows PowerShell.")
        return False

    script_path = paths["datrix_dir"] / "scripts" / "dev" / "generate.ps1"
    if not script_path.exists():
        print_error(f"generate.ps1 not found at: {script_path}")
        return False

    cmd: list[str] = [pwsh_exe, "-File", str(script_path)]

    if all_examples:
        print_step(2, "Generate Examples")
        cmd.append("-All")
        cmd.extend(_generate_target_arguments(language, platform))
        if test_set != "all":
            cmd.extend(["-TestSet", test_set])
    else:
        example_arguments = _generate_example_arguments(example_path, output_path)
        if example_arguments is None:
            return False
        cmd.extend(example_arguments)
        cmd.extend(_generate_target_arguments(language, platform))

    if hosting:
        cmd.extend(["-Hosting", hosting])

    success, _ = run_command(
        cmd,
        cwd=paths["datrix_root"],
        description="Generating via generate.ps1",
    )
    return success


def _generate_target_arguments(language: str, platform: str) -> list[str]:
    """generate.ps1's ``-Language`` and, when known, ``-Runtime`` arguments.

    Only the runtime segment of *platform* (the part before any ``/``) is
    passed: generate.ps1 reads each project's provider from its
    ``config/system.dcfg``.
    """
    arguments = ["-Language", language]
    runtime = platform.split("/", 1)[0] if platform else None
    if runtime:
        arguments.extend(["-Runtime", runtime])
    return arguments


def _generate_example_arguments(
    example_path: str | None, output_path: str | None
) -> list[str] | None:
    """generate.ps1's source-file and output-dir arguments for one example,
    with the step header printed; ``None`` (error printed) when either path
    is missing or the source file does not exist."""
    if not example_path or not output_path:
        print_error("Example path and output path are required when -All is not specified")
        return None

    print_step(2, f"Generate Example: {Path(example_path).name}")

    source_file = Path(example_path).resolve()
    output_dir = Path(output_path).resolve()

    if not source_file.exists():
        print_error(f"Example file not found at: {source_file}")
        return None
    return [str(source_file), str(output_dir)]


def _jest_suite_failures_from_output(output: str) -> int:
    m = re.search(r"Test Suites:\s+(.+?total)", output)
    if not m:
        return 0
    failed_m = re.search(r"(\d+) failed", m.group(1))
    return int(failed_m.group(1)) if failed_m else 0


def parse_test_statistics(output: str) -> dict:
    """Parse test statistics from unit_tests.py, deploy_test.py, or Jest output.

    Supports three formats:
    - unit_tests.py summary format: "Total Passed: 35"
    - pytest summary line format: "===== 35 passed, 1 failed in 8.48s ====="
    - Jest summary format: "Tests: ... total" plus "Test Suites: ..." (``suiteFailures`` is
      tracked separately from ``errors`` so suite compile failures are not double-counted).

    Mirrors ``parseTestStatistics`` in generated ``tests/unit-tests.js``.
    """
    stats: dict[str, int] = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "suiteFailures": 0,
    }

    if not output:
        return stats

    # Try unit_tests.py "Total Passed: X" format first
    _read_summary_totals(output, stats)
    # If no results found, try pytest summary line format.
    if stats["passed"] == 0 and stats["failed"] == 0:
        _add_pytest_summary_counts(output, stats)
    # If still no results, try Jest summary format (align with unit-tests.js).
    if stats["passed"] == 0 and stats["failed"] == 0:
        _read_jest_summary(output, stats)
    return stats


#: ``(stats key, label)`` of each "Total <label>: N" summary line.
_SUMMARY_TOTAL_LABELS = (
    ("passed", "Passed"),
    ("failed", "Failed"),
    ("errors", "Errors"),
    ("skipped", "Skipped"),
)
#: ``(stats key, word)`` of each "N <word>" count on a pytest summary line.
_PYTEST_COUNT_WORDS = (
    ("passed", "passed"),
    ("failed", "failed"),
    ("errors", "error"),
    ("skipped", "skipped"),
)
#: ``(stats key, word)`` of each "N <word>" count on a Jest "Tests:" line.
_JEST_COUNT_WORDS = (("passed", "passed"), ("failed", "failed"), ("skipped", "skipped"))


def _first_count(pattern: str, text: str) -> int | None:
    """The integer *pattern*'s first group captures in *text*, or ``None``."""
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _read_summary_totals(output: str, stats: dict[str, int]) -> None:
    """Set each count a unit_tests.py "Total <label>: N" line states."""
    for key, label in _SUMMARY_TOTAL_LABELS:
        count = _first_count(rf"Total {label}:\s+(\d+)", output)
        if count is not None:
            stats[key] = count


def _is_pytest_summary_line(line: str) -> bool:
    """Whether a stripped line is a pytest summary line, such as
    ``===== 35 passed in 8.48s =====``. The leading ``=`` keeps unrelated
    output from matching."""
    return (
        line.startswith("=")
        and ("passed" in line or "failed" in line or "error" in line)
        and re.search(r" in \d", line) is not None
    )


def _add_pytest_summary_counts(output: str, stats: dict[str, int]) -> None:
    """Add the counts of every pytest summary line in *output*."""
    for raw_line in output.split("\n"):
        line = raw_line.strip()
        if not _is_pytest_summary_line(line):
            continue
        for key, word in _PYTEST_COUNT_WORDS:
            count = _first_count(rf"(\d+) {word}", line)
            if count is not None:
                stats[key] += count


def _read_jest_summary(output: str, stats: dict[str, int]) -> None:
    """Set the counts of Jest's first ``Tests: ... total`` line and the failed
    suite count. Failed suites count as errors when no test ran (a suite that
    does not compile runs none), or when there is no ``Tests:`` line at all."""
    suites_failed = _jest_suite_failures_from_output(output)
    stats["suiteFailures"] = suites_failed
    tests_line = next(
        (
            line
            for line in (raw_line.strip() for raw_line in output.split("\n"))
            if line.startswith("Tests:") and "total" in line
        ),
        None,
    )
    if tests_line is None:
        if suites_failed > 0:
            stats["errors"] = suites_failed
        return
    for key, word in _JEST_COUNT_WORDS:
        count = _first_count(rf"(\d+) {word}", tests_line)
        if count is not None:
            stats[key] = count
    total = _first_count(r"(\d+)\s*total", tests_line)
    if total is None:
        total = stats["passed"] + stats["failed"] + stats["skipped"]
    if total == 0 and suites_failed > 0:
        stats["errors"] = suites_failed


def _sanitize_log_filename(name: str) -> str:
    """Replace characters invalid in filenames with underscore."""
    invalid_chars = '/\\:*?"<>|'
    result = name
    for c in invalid_chars:
        result = result.replace(c, '_')
    return result or "container"


def _save_docker_logs_for_project(
    project: Path,
    deploy_test_dir: Path,
    project_slug: str | None = None,
) -> None:
    """
    Discover containers for the project via docker compose and save each container's
    logs under deploy_test_dir/docker-logs/. Does not fail Step 5 on docker errors.
    """
    docker_logs_dir = deploy_test_dir / "docker-logs"
    docker_logs_dir.mkdir(parents=True, exist_ok=True)

    compose_file = next(
        (
            candidate
            for candidate in (project / "docker-compose.yml", project / "docker-compose.yaml")
            if candidate.exists()
        ),
        None,
    )
    if compose_file is None:
        return

    names = _compose_container_names(project, compose_file)
    if not names:
        return

    prefix = _sanitize_log_filename(project_slug) + "-" if project_slug else ""

    for container_name in names:
        safe_name = _sanitize_log_filename(container_name)
        log_file = docker_logs_dir / f"{prefix}{safe_name}.log"
        try:
            log_result = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            content = (log_result.stdout or "") + (log_result.stderr or "")
            log_file.write_text(content, encoding="utf-8")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            print_warning(f"Could not save docker logs for {container_name}: {e}")


def _compose_container_names(project: Path, compose_file: Path) -> list[str]:
    """Every container of every compose project *compose_file* defines
    (``docker compose -p <name> -f <file> ps -a``). A compose project whose
    listing fails is skipped with a warning; when docker is missing or times
    out, nothing is returned."""
    names: list[str] = []
    for compose_project in _compose_project_names(compose_file):
        ps_cmd = ["docker", "compose", "-p", compose_project, "-f", str(compose_file),
                  "ps", "-a", "--format", "{{.Name}}"]
        try:
            result = subprocess.run(
                ps_cmd,
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            print_warning(f"Could not list docker containers for {project.name}: {e}")
            return []

        if result.returncode != 0:
            if result.stderr:
                print_warning(f"Docker compose ps failed for {project.name}: {result.stderr.strip()}")
            continue
        names.extend(n.strip() for n in result.stdout.splitlines() if n.strip())
    return names


_DATRIX_CONFIG_PATH_MARKERS = (".generated", ".projects")


def _list_compose_projects() -> list[dict[str, str]]:
    """Every compose project docker knows of, running or stopped (``docker compose ls -a``).

    Returns an empty list when docker is unavailable or answers with an error:
    the callers are cleanup safety nets that must never fail a test step.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ls", "-a", "--format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print_warning(f"Could not list compose projects: {exc}")
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def _compose_project_names(compose_file: Path) -> list[str]:
    """Names of the compose projects started from *compose_file*, as docker records them.

    A generated project's deploy runner picks its own compose project name, so the
    name is read back from docker -- every project whose config files include this
    one -- rather than from the runner, whose language this tool never needs to know.
    """
    target = os.path.normcase(str(compose_file.resolve()))
    return sorted(
        project["Name"]
        for project in _list_compose_projects()
        if target in {
            os.path.normcase(str(Path(config).resolve()))
            for config in project["ConfigFiles"].split(",")
            if config
        }
    )


def _is_datrix_compose_project(config_files: str) -> bool:
    """Return True if the compose project belongs to a datrix-generated example.

    Checks whether the config file path contains ``.generated`` or
    ``.projects`` — both are datrix-specific output directories.
    """
    config_lower = config_files.replace("\\", "/").lower()
    return any(marker in config_lower for marker in _DATRIX_CONFIG_PATH_MARKERS)


def _cleanup_all_datrix_compose_projects() -> None:
    """Tear down ALL datrix-related Docker Compose projects before tests.

    Discovers running/stopped compose projects via ``docker compose ls -a``
    and tears down any whose config-file path is under ``.generated`` or
    ``.projects``.  Idempotent and failure-tolerant — never blocks the test
    step on cleanup errors.
    """
    datrix_projects = [
        p for p in _list_compose_projects()
        if _is_datrix_compose_project(p.get("ConfigFiles", ""))
    ]

    if not datrix_projects:
        return

    print_info(f"Pre-flight cleanup: tearing down {len(datrix_projects)} datrix compose project(s)")
    for proj in datrix_projects:
        name = proj["Name"]
        print_info(f"  [cleanup] {name}")
        try:
            subprocess.run(
                ["docker", "compose", "-p", name, "down", "-v", "--remove-orphans"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            print_warning(f"Cleanup warning for project {name}: {exc}")

        # Remove orphaned volumes that compose down -v may have missed
        try:
            vol_result = subprocess.run(
                ["docker", "volume", "ls", "--filter", f"name={name}", "--quiet"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if vol_result.returncode == 0 and vol_result.stdout.strip():
                for vol_name in vol_result.stdout.strip().splitlines():
                    subprocess.run(
                        ["docker", "volume", "rm", vol_name.strip()],
                        capture_output=True,
                        check=False,
                    )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


def _ensure_docker_cleanup(project: Path) -> None:
    """Safety net: tear down Docker containers, volumes, and images for a project.

    Runs after each project's deploy run to ensure no resources are left
    behind, regardless of how the run exited (success, failure, or killed).
    Idempotent — safe to call even if containers are already stopped/removed.
    """
    compose_file = project / "docker-compose.yml"
    if not compose_file.exists():
        compose_file = project / "docker-compose.yaml"
        if not compose_file.exists():
            return

    for compose_project in _compose_project_names(compose_file):
        cmd = ["docker", "compose", "-p", compose_project, "-f", str(compose_file),
               "down", "-v", "--rmi", "local", "--remove-orphans"]
        try:
            subprocess.run(
                cmd,
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            print_warning(f"Docker cleanup warning for {project.name}: {exc}")


def save_test_summary_log(
    step_num: int,
    step_name: str,
    paths: dict[str, Path],
    project_results: list[dict],
    total_projects: int,
    success_count: int,
    fail_count: int,
    total_passed_tests: int,
    total_failed_tests: int,
    total_error_tests: int,
    total_skipped_tests: int,
    step5_output_dir: Path | None = None,
) -> Path:
    """Save test summary to a log file.

    When step5_output_dir is set, write to step5_output_dir/deploy-test-summary.log.
    Otherwise fall back to .generated/.test_results/ (Step 4 unit tests).
    """
    log_path = _summary_log_path(step_num, step_name, paths, step5_output_dir)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"STEP {step_num} SUMMARY: {step_name}\n")
        f.write("=" * 60 + "\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
 
        # Overall statistics
        f.write(f"Total Projects Tested: {total_projects}\n")
        f.write(f" Successful Projects: {success_count}\n")
        f.write(f" Failed Projects: {fail_count}\n")
        f.write("\n")
        f.write("Total Tests:\n")
        f.write(f" Passed: {total_passed_tests}\n")
        f.write(f" Failed: {total_failed_tests}\n")
        f.write(f" Errors: {total_error_tests}\n")
        f.write(f" Skipped: {total_skipped_tests}\n")
        f.write("\n")
 
        # Per-project breakdown - separate successful and failed
        f.write("Per-Project Breakdown:\n")
        f.write("-" * 60 + "\n")
 
        successful_projects = [r for r in project_results if r["success"]]
        failed_projects = [r for r in project_results if not r["success"]]
        # The successful group is set off from the rule above it by a blank line.
        _write_summary_project_group(f, "\nSuccessful Projects", "✓", successful_projects)
        _write_summary_project_group(f, "Failed Projects", "✗", failed_projects)

        f.write("=" * 60 + "\n")

    if step5_output_dir is not None:
        fail_json = step5_output_dir / "failures.json"
        if fail_json.is_file():
            _append_deploy_failure_index_to_summary(log_path, fail_json)

    return log_path


def _summary_log_path(
    step_num: int, step_name: str, paths: dict[str, Path], step5_output_dir: Path | None
) -> Path:
    """``deploy-test-summary.log`` under *step5_output_dir* when set, else a
    timestamped ``step<N>-<name>-<time>.log`` under ``.generated/.test_results/``."""
    if step5_output_dir is not None:
        return step5_output_dir / "deploy-test-summary.log"
    test_results_dir = paths["datrix_root"] / ".generated" / ".test_results"
    test_results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_filename = f"step{step_num}-{step_name.lower().replace(' ', '-')}-{timestamp}.log"
    return test_results_dir / log_filename


def _append_deploy_failure_index_to_summary(summary_log: Path, failures_json: Path) -> None:
    """Append human-readable failure lines from failures.json (deploy / Jest / pytest)."""
    try:
        data = json.loads(failures_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    failures = data.get("failures") or []
    if not failures:
        return
    lines = [
        "",
        "=" * 60,
        "Failure index (from failures.json)",
        "=" * 60,
    ]
    for item in failures:
        svc = item.get("service", "")
        full_name = item.get("fullName", "")
        file_path = item.get("testFilePath", "")
        line = item.get("line")
        loc = f":{line}" if line is not None else ""
        msg = ((item.get("message") or "").split("\n")[0])[:400]
        lines.append(f"- [{svc}] {full_name}")
        lines.append(f"    file: {file_path}{loc}")
        if msg:
            lines.append(f"    message: {msg}")
    with summary_log.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


#: Layout every generated project follows under ``.generated``:
#: ``{language}/{runtime}/{provider}/{category}/.../{example}``. The first three
#: segments name the TARGET; every segment after them names the example, and that
#: suffix is what maps back to ``datrix/examples/{example}/system.dtrx``.
_GENERATED_TARGET_SEGMENTS = 3


def _derive_generated_project_metadata(project: Path) -> tuple[str, str, str]:
    """Return ``(project_name, example, dtrx_source)`` for a generated project.

    The example is the LONGEST trailing run of *project*'s own path segments that
    names a real ``datrix/examples/{example}/system.dtrx`` -- resolved against the
    file that must exist, never counted off positionally from a caller-supplied
    base. Two defects follow from the positional form and both are closed here:

    * Single-project mode deliberately passes the project's own parent as
      ``generated_base`` so ``relative_to`` yields just the leaf name for display.
      Slicing the example off that collapsed path wrote
      ``datrix/examples/serverless/system.dtrx`` -- which does not exist -- for a
      project whose real source is
      ``datrix/examples/02-features/02-service-architecture/serverless``. One
      parameter cannot serve both the display name and the source lookup, so the
      lookup no longer reads it.
    * A fixed ``{language}/{runtime}/{provider}`` prefix count only holds under
      ``.generated``. ``generate.ps1 -OutputBase`` is a documented, supported flow,
      and a project generated elsewhere is not a tooling error -- it simply has a
      different number of leading segments. Matching from the tail makes the prefix
      length irrelevant.

    Longest-first is what makes the match the most specific one: a nested example
    is preferred over any shorter suffix that happens to also resolve.

    Raises:
        ValueError: If no trailing run of segments names a real ``system.dtrx``.
            This stays loud rather than degrading to a guess: ``dtrx_source`` is
            copied verbatim into the ``--- Codegen Hint ---`` block of every error
            file, and a wrong pointer written silently is a wrong pointer that gets
            believed.
    """
    datrix_root = get_paths()["datrix_root"]
    examples_root = datrix_root / "datrix" / "examples"
    parts = project.resolve().parts

    for start in range(len(parts)):
        candidate = "/".join(parts[start:])
        if (examples_root / candidate / "system.dtrx").is_file():
            example = candidate
            # Re-attach the target segments that precede the example
            # (``{language}/{runtime}/{provider}``) so the display name is the
            # project's full identity under its output base, identical in
            # single-project and batch mode.
            name_start = max(0, start - _GENERATED_TARGET_SEGMENTS)
            return "/".join(parts[name_start:]), example, f"datrix/examples/{example}/system.dtrx"

    raise ValueError(
        f"Cannot derive the example for generated project {project}: no trailing run "
        f"of its path segments names an existing {examples_root}/{{example}}/system.dtrx. "
        f"Expected the project to be generated at "
        f"{{output-base}}/{{language}}/{{runtime}}/{{provider}}/{{example}}, where "
        f"{{example}} is its source example's path under datrix/examples. Either the "
        f"example was renamed or removed after this project was generated, or the "
        f"project was written outside that layout — regenerate it from its current "
        f"example path."
    )


def _snapshot_run_dirs(project: Path, test_type: str) -> set[Path]:
    """Return the run directories that exist under *project* before a test run.

    Args:
        project: Generated project directory.
        test_type: ``unit``, ``spec`` or ``integration``.

    Returns:
        Every ``.test_results/{test_type}-tests-*`` directory present right now.
    """
    base = project / ".test_results"
    if not base.is_dir():
        return set()
    prefix = f"{test_type}-tests-"
    return {d for d in base.iterdir() if d.is_dir() and d.name.startswith(prefix)}


def _run_dir_created_by(project: Path, test_type: str, before: set[Path]) -> Path | None:
    """Return the run directory a just-finished test run created, if any.

    A generated project's own test runner (started through
    ``tests/run-tests.ps1``) time-stamps and creates its own output directory,
    so the caller learns which one it got only by diffing against *before*.
    Taking "the newest directory" instead would hand the previous run's results
    to the structured writer whenever this run died before creating its own --
    stamping a stale verdict with a fresh timestamp.

    Args:
        project: Generated project directory.
        test_type: ``unit``, ``spec`` or ``integration``.
        before: Result of :func:`_snapshot_run_dirs` taken before the run.

    Returns:
        The newly created run directory, or None when the run created none.
    """
    created = _snapshot_run_dirs(project, test_type) - before
    if not created:
        return None
    return max(created, key=lambda d: d.name)


def _warn_on_verdict_mismatch(index_path: Path, runner_success: bool) -> None:
    """Warn when ``index.json`` and the test runner disagree about a run.

    The two verdicts are computed independently -- the runner from the exit codes
    it saw, the index from the per-service reports found on disk afterwards -- so
    a disagreement means a service the runner judged is missing from the index.
    ``run-complete.ps1 -Rerun`` selects work from the index alone, so a falsely
    green one silently drops a failing project out of the re-run set.

    Args:
        index_path: Path to the index.json just written.
        runner_success: Whether the project's test runner reported success.
    """
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print_warning(f"  Structured output: cannot read {index_path}: {exc}")
        return

    if (index.get("result") == "PASSED") == runner_success:
        return

    print_warning(
        f"  Structured output: {index_path} records "
        f"{index.get('result')!r} but the test runner reported "
        f"{'success' if runner_success else 'failure'} — a service's outcome is "
        f"missing from the index; re-run selection reads the index and will "
        f"believe it"
    )


def _produce_structured_output_for_run(
    project: Path,
    generated_base: Path,
    language: str,
    test_type: str,
    before_run_dirs: set[Path],
    runner_success: bool,
) -> Path | None:
    """Index the run directory a generated project's own test runner created.

    Every generated project ships its own runner behind ``tests/run-tests.ps1``,
    which creates and time-stamps its own output directory. This locates that
    directory, writes the structured index into it, and checks the index against
    the runner's verdict.

    Args:
        project: Generated project directory.
        generated_base: Base path used for the project's display name.
        language: Generation language recorded in the index.
        test_type: ``unit``, ``spec`` or ``integration``.
        before_run_dirs: Result of :func:`_snapshot_run_dirs` taken before the run.
        runner_success: Whether the project's test runner reported success.

    Returns:
        Path to the written index.json, or None when there was nothing to index.
    """
    run_dir = _run_dir_created_by(project, test_type, before_run_dirs)
    if run_dir is None:
        print_warning(
            f"  Structured output: no {test_type}-tests-* directory was created "
            f"for {project.name} — its test runner wrote no results to index"
        )
        return None

    index_path = _produce_structured_output(
        project, generated_base, language, "docker", run_dir, 0.0,
    )
    if index_path is not None:
        _warn_on_verdict_mismatch(index_path, runner_success)
    return index_path


def _produce_structured_output(
    project: Path,
    generated_base: Path,
    language: str,
    platform: str,
    results_dir: Path,
    duration_seconds: float,
) -> Path | None:
    """Produce structured test output (index.json, summary.txt, error files).

    Scans the results directory for JUnit XML (Python) or Jest JSON
    (TypeScript) files and writes structured output via GeneratedTestLogWriter.
    A service that produced neither is recorded as failed rather than skipped.

    Returns the path to index.json on success, None if no service produced any
    result at all.

    Raises:
        ValueError: If *project*'s example and .dtrx source cannot be derived --
            see :func:`_derive_generated_project_metadata`.
    """
    _ = generated_base
    project_name, example, dtrx_source = _derive_generated_project_metadata(project)

    writer = GeneratedTestLogWriter(
        project_path=project_name,
        language=language,
        platform=platform,
        example=example,
        run_dir=results_dir,
        dtrx_source=dtrx_source,
    )

    # Each service's report in services/{name}/; a runner may instead write it
    # in a top-level {service}/ directory, beside a top-level {service}-unit-tests.log
    found_structured_data = _index_services_layout(writer, results_dir / "services")
    if not found_structured_data:
        found_structured_data = _index_top_level_layout(writer, results_dir)

    if not found_structured_data:
        return None

    try:
        index_path = writer.write(duration_seconds)
        return index_path
    except Exception as exc:
        print_warning(f"  Structured output: failed to write for {project_name}: {exc}")
        return None


def _index_services_layout(writer: GeneratedTestLogWriter, services_dir: Path) -> bool:
    """Index every ``services/{name}/`` directory: its ``junit.xml``, else
    its ``jest-results.json``, else it is recorded as failed. Returns whether
    any service directory was found."""
    if not services_dir.is_dir():
        return False
    found = False
    for svc_dir in sorted(services_dir.iterdir()):
        if not svc_dir.is_dir():
            continue
        service_log = svc_dir / "service.log"
        junit_xml = svc_dir / "junit.xml"
        jest_json = svc_dir / "jest-results.json"
        if junit_xml.is_file():
            _add_service_report(
                writer, writer.add_service_junit_xml, svc_dir.name, junit_xml, service_log, "JUnit XML"
            )
        elif jest_json.is_file():
            _add_service_report(
                writer, writer.add_service_jest_json, svc_dir.name, jest_json, service_log, "Jest JSON"
            )
        else:
            _add_unreported_service(writer, svc_dir.name, service_log)
        found = True
    return found


def _index_top_level_layout(writer: GeneratedTestLogWriter, results_dir: Path) -> bool:
    """Index every top-level ``{service}/`` directory (other than
    ``services/``) the runner attempted. Returns whether any was indexed."""
    found = False
    for item in sorted(results_dir.iterdir()):
        if item.is_dir() and item.name != "services":
            found = _index_top_level_service(writer, results_dir, item) or found
    return found


def _index_top_level_service(
    writer: GeneratedTestLogWriter, results_dir: Path, item: Path
) -> bool:
    """Index one top-level service directory: its ``jest-results.json``, else
    a failed service when its sibling log exists. Returns whether it was indexed.

    The sibling log is what makes this directory a SERVICE the runner
    attempted rather than an incidental directory: a runner using this
    layout writes one per service before Jest ever runs. Without it there is
    nothing to distinguish a service whose Jest run died from a stray
    directory, and guessing either way is wrong.
    """
    jest_json = item / "jest-results.json"
    log_path = results_dir / f"{item.name}-unit-tests.log"
    if not log_path.exists():
        log_path = results_dir / f"{item.name}-tests.log"
    if jest_json.is_file():
        _add_service_report(
            writer, writer.add_service_jest_json, item.name, jest_json, log_path, "Jest JSON"
        )
        return True
    if log_path.exists():
        _add_unreported_service(writer, item.name, log_path)
        return True
    return False


def _add_service_report(
    writer: GeneratedTestLogWriter,
    add_report: Callable[[str, Path, Path], object],
    service: str,
    report: Path,
    service_log: Path,
    report_kind: str,
) -> None:
    """Add one service's test report; a report that cannot be parsed records
    the service as unreported, with a warning naming *report_kind*."""
    try:
        add_report(service, report, service_log)
    except Exception as exc:
        print_warning(f"  Structured output: failed to parse {report_kind} for {service}: {exc}")
        writer.add_unreported_service(service, service_log)


def _add_unreported_service(
    writer: GeneratedTestLogWriter, service: str, service_log: Path
) -> None:
    """Record a service that produced no test report as failed."""
    print_warning(
        f"  Structured output: {service} produced no test report "
        f"— recording it as failed (the build did not reach the tests)"
    )
    writer.add_unreported_service(service, service_log)


ProjectResult = dict[str, Any]

_COUNT_KEYS = ("passed", "failed", "errors", "skipped")
_RULE = "=" * 60
_UNIT_TEST_TYPE = "unit"


def _empty_stats() -> dict[str, int]:
    return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "suiteFailures": 0}


def _workspace_venv_env() -> dict[str, str]:
    """The environment a generated project's runners see: the workspace venv, activated.

    A runner the entry point starts by command name resolves it on ``PATH``, and a
    runner that installs its project's requirements installs them into whatever
    interpreter runs it -- so it must find the workspace venv first, exactly as in a
    shell where the venv is activated.
    """
    venv_bin = get_venv_python().parent
    return {
        "VIRTUAL_ENV": str(venv_bin.parent),
        "PATH": f"{venv_bin}{os.pathsep}{os.environ['PATH']}",
    }


def _missing_entry_point_result(project_name: str) -> ProjectResult:
    """A failed result for a generated project that carries no test entry point."""
    print_error(
        f" [ERROR] {project_name} carries no {TEST_RUNNER_ENTRY_POINT}. Every language "
        f"generator emits it as the project's one test entry point "
        f"(datrix_codegen_kernel.generation.test_runner_entry_point), so a project without "
        f"one is a generation defect, not a project without tests. Fix: regenerate the "
        f"project; if it is still missing, make its language generator emit the file "
        f"through build_test_runner_entry_point."
    )
    return _error_result(project_name)


def _run_entry_point(
    project: Path,
    switch: str,
    arguments: list[str],
    description: str,
) -> tuple[bool, str | None]:
    """Run *project*'s ``tests/run-tests.ps1`` with ``-<switch>`` and *arguments* forwarded."""
    powershell = _find_powershell()
    if powershell is None:
        print_error("PowerShell not found. Please install PowerShell (pwsh) or Windows PowerShell.")
        return False, None
    cmd = [
        powershell, "-NoProfile", "-NonInteractive", "-File",
        str(project / TEST_RUNNER_ENTRY_POINT), f"-{switch}", *arguments,
    ]
    return run_command(
        cmd,
        cwd=project,
        description=description,
        capture_output=True,
        env_overrides=_workspace_venv_env(),
    )


def _run_single_project_unit_tests(
    project: Path,
    generated_base: Path,
    language: str,
    *,
    verbose: bool = False,
) -> ProjectResult:
    """Run one generated project's unit tests through its ``tests/run-tests.ps1 -Unit``.

    Args:
        project: Path to the project directory
        generated_base: Base path the project's display name is relative to
        language: Generation language recorded in the structured index
        verbose: If True, forward ``--verbose`` to the project's unit runner
    """
    project_name = str(project.relative_to(generated_base))
    if not (project / TEST_RUNNER_ENTRY_POINT).is_file():
        return _missing_entry_point_result(project_name)

    arguments = [PARALLEL_ARGUMENT, *([VERBOSE_ARGUMENT] if verbose else [])]
    before_run_dirs = _snapshot_run_dirs(project, _UNIT_TEST_TYPE)
    success, output = _run_entry_point(
        project, UNIT_TESTS_SWITCH, arguments, f"Unit tests for {project_name}",
    )
    stats = parse_test_statistics(output) if output else _empty_stats()

    # Index the reports this run wrote. Without it a project never gets an
    # index.json, and `-Rerun` -- which treats "no index" as "never tested" --
    # re-runs it forever.
    index_path = _produce_structured_output_for_run(
        project, generated_base, language, _UNIT_TEST_TYPE, before_run_dirs, success,
    )

    result: ProjectResult = {
        "name": project_name,
        "success": success,
        "passed": stats["passed"],
        "failed": stats["failed"],
        "errors": stats["errors"],
        "skipped": stats["skipped"],
        "output": None,
    }
    if index_path is not None:
        result["index_json_path"] = str(index_path)
    return result


@dataclass(frozen=True)
class StepTotals:
    """What one step's project loop produced."""

    project_results: list[ProjectResult]
    success_count: int
    fail_count: int
    log_path: Path


def _generated_projects(
    generated_base: Path,
    test_set: str | None,
    language: str,
    platform: str,
    *,
    deploy: bool,
) -> list[Path]:
    """The generated projects a test step runs, sorted.

    With a test set, its projects that exist on disk. Otherwise every directory under
    ``generated_base`` holding the test entry point every language emits
    (``tests/run-tests.ps1``); with ``deploy`` only those whose entry point declares
    the ``-Deploy`` switch, read with PowerShell's own parser.
    """
    if test_set:
        listed = get_test_projects(test_set=test_set, language=language, runtime=platform)
        return [Path(p["output"]) for p in listed if Path(p["output"]).exists()]
    if not generated_base.exists():
        return []
    depth = len(TEST_RUNNER_ENTRY_POINT.parts)
    entry_points = sorted(
        script for script in generated_base.rglob(TEST_RUNNER_ENTRY_POINT.name)
        if script.parts[-depth:] == TEST_RUNNER_ENTRY_POINT.parts
    )
    if deploy:
        facts = parse_scripts(entry_points)
        entry_points = [
            script for script in entry_points
            if facts[script.resolve()].declares(DEPLOY_TESTS_SWITCH)
        ]
    return [script.parents[depth - 1] for script in entry_points]


def _format_counts(result: ProjectResult) -> str:
    return ", ".join(f"{key}: {result[key]}" for key in _COUNT_KEYS if result.get(key, 0) > 0)


def _write_summary_project_group(
    f: TextIO, heading: str, mark: str, results: list[ProjectResult]
) -> None:
    """One summary-log project group: its heading and count, then each
    project's name and non-zero test counts. An empty group writes nothing."""
    if not results:
        return
    f.write(f"{heading} ({len(results)}):\n")
    for result in results:
        f.write(f" {mark} {result['name']}\n")
        counts = _format_counts(result)
        if counts:
            f.write(f"   Tests: {counts}\n")
    f.write("\n")


def _error_result(project_name: str) -> ProjectResult:
    return {"name": project_name, "success": False, "passed": 0, "failed": 0, "errors": 1,
            "skipped": 0, "output": None}


def _run_one_project(
    project: Path,
    project_name: str,
    run_one: Callable[[Path, str], ProjectResult | None],
) -> ProjectResult | None:
    try:
        result = run_one(project, project_name)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - one project's crash is that project's failure
        print_error(f" [ERROR] Exception while running tests for {project_name}: {exc}")
        return _error_result(project_name)
    if result is None:
        print_warning(f" [SKIP] {project_name} has no tests for this step")
        return None
    print()
    if result["success"]:
        print_success(f" [OK] Tests passed for {project_name}")
    else:
        print_error(f" [FAILED] Tests failed for {project_name}")
    counts = _format_counts(result)
    if counts:
        print_info(f" Tests: {counts}")
    return result


def _print_project_group(heading: str, results: list[ProjectResult], *, success: bool) -> None:
    if not results:
        return
    report = print_success if success else print_error
    mark = "✓" if success else "✗"
    report(f"{heading} ({len(results)}):")
    for result in results:
        report(f" {mark} {result['name']}")
        counts = _format_counts(result)
        if counts:
            print_info(f"   Tests: {counts}")
    print_info("")


def _print_step_summary(step_number: int, title: str, total_projects: int, totals: StepTotals) -> None:
    results = totals.project_results
    print()
    print_info(_RULE)
    print_info(f"STEP {step_number} SUMMARY: {title}")
    print_info(_RULE)
    print_info(f"Total Projects Tested: {total_projects}")
    print_info(f" Successful Projects: {totals.success_count}")
    print_info(f" Failed Projects: {totals.fail_count}")
    print_info("")
    print_info("Total Tests:")
    print_info(f" Passed: {sum(r.get('passed', 0) for r in results)}")
    for key, label in (("failed", "Failed"), ("errors", "Errors"), ("skipped", "Skipped")):
        total = sum(r.get(key, 0) for r in results)
        if total > 0:
            (print_info if key == "skipped" else print_error)(f" {label}: {total}")
    print_info("")
    print_info("Per-Project Breakdown:")
    print_info("-" * 60)
    _print_project_group("Successful Projects", [r for r in results if r["success"]], success=True)
    _print_project_group("Failed Projects", [r for r in results if not r["success"]], success=False)
    print_info(_RULE)


def _run_projects(
    step_number: int,
    title: str,
    projects: list[Path],
    generated_base: Path,
    paths: dict[str, Path],
    run_one: Callable[[Path, str], ProjectResult | None],
) -> StepTotals:
    """Run every project one at a time, print and log the step summary.

    ``run_one(project, project_name)`` returns the project's result, or None when the
    project has nothing to run for this step (reported as skipped, not counted).
    """
    print_info(f"Found {len(projects)} generated projects to test")
    results: list[ProjectResult] = []
    try:
        for index, project in enumerate(projects, 1):
            project_name = str(project.relative_to(generated_base))
            print()
            print_info(f"[{index}/{len(projects)}] Running step {step_number} tests for: {project_name}")
            print("-" * 60)
            result = _run_one_project(project, project_name, run_one)
            if result is not None:
                results.append(result)
    except KeyboardInterrupt:
        print()
        print_warning(f"STEP {step_number} INTERRUPTED BY USER after {len(results)} of {len(projects)} projects")
        raise
    results.sort(key=lambda result: result["name"])
    success_count = sum(1 for result in results if result["success"])
    fail_count = len(results) - success_count
    log_path = save_test_summary_log(
        step_num=step_number,
        step_name=title,
        paths=paths,
        project_results=results,
        total_projects=len(projects),
        success_count=success_count,
        fail_count=fail_count,
        total_passed_tests=sum(r.get("passed", 0) for r in results),
        total_failed_tests=sum(r.get("failed", 0) for r in results),
        total_error_tests=sum(r.get("errors", 0) for r in results),
        total_skipped_tests=sum(r.get("skipped", 0) for r in results),
    )
    totals = StepTotals(results, success_count, fail_count, log_path)
    _print_step_summary(step_number, title, len(projects), totals)
    print_info(f"Summary log saved to: {log_path.relative_to(paths['datrix_root'])}")
    return totals


def step3_run_unit_tests(all_examples: bool, paths: dict[str, Path], output_path: str | None = None, test_set: str | None = None, language: str = "python", platform: str = "docker", verbose: bool = False) -> bool:
    """Step 3: Run unit tests for generated projects through each one's tests/run-tests.ps1 -Unit"""
    if all_examples:
        return _run_all_unit_tests(paths, test_set, language, platform, verbose)

    project_path_abs = _single_project_path(3, "Run Unit Tests", output_path)
    if project_path_abs is None:
        return False

    # Reuse the same helper as batch mode — parent serves as base so
    # relative_to produces just the leaf directory name.
    result = _run_single_project_unit_tests(
        project_path_abs, project_path_abs.parent, language, verbose=verbose,
    )
    return _report_single_project(result, result["name"], "Unit tests")


def _run_all_unit_tests(
    paths: dict[str, Path],
    test_set: str | None,
    language: str,
    platform: str,
    verbose: bool,
) -> bool:
    """Step 3 over every generated project, then their aggregate structured output."""
    print_step(3, "Run Unit Tests for Generated Projects")
    generated_base = paths["datrix_root"] / ".generated"
    projects = _generated_projects(generated_base, test_set, language, platform, deploy=False)
    if not projects:
        print_warning("No generated projects found to test")
        return True

    print_info("Running projects sequentially (services within each project run in parallel)...")

    def run_one(project: Path, _project_name: str) -> ProjectResult:
        return _run_single_project_unit_tests(project, generated_base, language, verbose=verbose)

    totals = _run_projects(3, "Unit Tests for Generated Projects", projects, generated_base, paths, run_one)
    _write_unit_aggregate(totals.project_results, generated_base, language, platform)
    return totals.fail_count == 0


def _write_unit_aggregate(
    project_results: list[ProjectResult], generated_base: Path, language: str, platform: str
) -> None:
    """Aggregate structured output across every project that wrote an index."""
    index_paths = [
        Path(r["index_json_path"])
        for r in project_results
        if r.get("index_json_path")
    ]
    if not index_paths:
        return
    try:
        aggregate_dir = generated_base / ".test_results" / f"unit-tests-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        aggregate_dir.mkdir(parents=True, exist_ok=True)
        agg_writer = AggregateTestWriter(
            language=language,
            platform=platform,
            output_dir=aggregate_dir,
        )
        for ip in index_paths:
            agg_writer.add_project_results(ip)
        agg_path = agg_writer.write()
        print_info(f"Aggregate structured output: {agg_path}")
    except Exception as exc:
        print_warning(f"Aggregate structured output failed: {exc}")


def _single_project_path(step_number: int, title: str, output_path: str | None) -> Path | None:
    """The generated project a single-project step runs, with the step header
    printed; ``None`` (error printed) when no path was given or it does not exist."""
    if not output_path:
        print_error("Output path is required when -All is not specified")
        return None

    print_step(step_number, f"{title}: {Path(output_path).name}")

    project_path_abs = Path(output_path).resolve()
    if not project_path_abs.exists():
        print_error(f"Generated project not found at: {project_path_abs}")
        return None
    return project_path_abs


def _report_single_project(result: ProjectResult, project_name: str, tests_label: str) -> bool:
    """Print a single project's test statistics and verdict; return whether it passed."""
    counts = _format_counts(result)
    if counts:
        print_info("")
        print_info(f"Test Statistics: {counts}")

    if result["success"]:
        print_success(f"[OK] {tests_label} passed for {project_name}")
        return True
    print_error(f"{tests_label} failed for {project_name}")
    return False




def step4_run_deployment_tests(all_examples: bool, paths: dict[str, Path], output_path: str | None = None, test_set: str | None = None, language: str = "python", platform: str = "docker", verbose: bool = False) -> bool:
    """Step 4: Run deployment tests (spec + integration) through each project's tests/run-tests.ps1 -Deploy"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Pre-flight: tear down all datrix compose projects to prevent port conflicts
    _cleanup_all_datrix_compose_projects()

    return _run_deployment_tests(all_examples, paths, output_path, test_set, language, platform, verbose, timestamp)


def _run_deployment_tests(
    all_examples: bool,
    paths: dict[str, Path],
    output_path: str | None,
    test_set: str | None,
    language: str,
    platform: str,
    verbose: bool,
    timestamp: str,
) -> bool:
    """Step 4 after its pre-flight teardown: every deploy project, or the one at *output_path*."""
    if all_examples:
        return _run_all_deployment_tests(paths, test_set, language, platform, verbose, timestamp)

    project_path_abs = _single_project_path(4, "Run Deployment Tests", output_path)
    if project_path_abs is None:
        return False

    project_name = project_path_abs.name
    result = _run_single_project_deploy_tests(
        project_path_abs, project_name, paths, timestamp, language, verbose=verbose,
    )

    if result is None:
        print_warning(
            f"{project_name} has no deploy tests: its {TEST_RUNNER_ENTRY_POINT} declares "
            f"no -{DEPLOY_TESTS_SWITCH} switch (the deployment starts no container orchestration)"
        )
        return True
    return _report_single_project(result, project_name, "Deployment tests")


def _run_all_deployment_tests(
    paths: dict[str, Path],
    test_set: str | None,
    language: str,
    platform: str,
    verbose: bool,
    timestamp: str,
) -> bool:
    """Step 4 over every deploy project, then their aggregate structured output."""
    print_step(4, "Run Deployment Tests (Spec + Integration) for Generated Projects")
    generated_base = paths["datrix_root"] / ".generated"
    projects = _generated_projects(generated_base, test_set, language, platform, deploy=True)
    if not projects:
        print_warning("No generated projects found to test")
        return True

    def run_one(project: Path, project_name: str) -> ProjectResult | None:
        return _run_single_project_deploy_tests(
            project, project_name, paths, timestamp, language, verbose=verbose,
        )

    totals = _run_projects(4, "Deployment Tests for Generated Projects", projects, generated_base, paths, run_one)
    _write_deploy_aggregate(totals, generated_base, timestamp, language, platform)
    return totals.fail_count == 0


def _write_deploy_aggregate(
    totals: StepTotals, generated_base: Path, timestamp: str, language: str, platform: str
) -> None:
    """Deploy test aggregate structured output across every project that wrote an index."""
    project_index_paths = [
        r["_index_path"] for r in totals.project_results
        if r.get("_index_path") is not None
    ]
    if not project_index_paths:
        return
    try:
        aggregate_dir = generated_base / ".test_results" / f"deploy-tests-{timestamp}"
        aggregate_dir.mkdir(parents=True, exist_ok=True)
        agg_writer = DeployTestAggregateWriter(
            aggregate_dir=aggregate_dir,
            language=language,
            platform=platform,
        )
        agg_path = agg_writer.write(
            project_index_paths=project_index_paths,
            timestamp=datetime.strptime(timestamp, "%Y%m%d-%H%M%S"),
            full_log_path=totals.log_path,
        )
        print_info(f"Deploy test aggregate output: {agg_path}")
    except Exception:
        logger.exception("deploy_aggregate_output_failed")


def _write_deploy_structured_output(
    project: Path,
    project_name: str,
    deploy_test_dir: Path,
    paths: dict[str, Path],
    timestamp: str,
    language: str,
) -> Path | None:
    """Write structured deploy test output for a project (advisory — never fails the pipeline).

    Returns:
        Path to the index.json file, or None if writing failed.
    """
    try:
        generated_base = paths["datrix_root"] / ".generated"
        # Derive example path from project relative to generated_base/language/runtime/provider
        try:
            rel_parts = project.relative_to(generated_base).parts
            # Skip language/runtime/provider prefix (3 segments, e.g. "python/docker-compose/local/")
            example = "/".join(rel_parts[3:]) if len(rel_parts) > 3 else str(project.name)
        except ValueError:
            example = str(project.name)

        # Resolve .dtrx source from example path
        dtrx_source = f"datrix/examples/{example}/system.dtrx"

        writer = DeployTestLogWriter(
            project_name=project_name,
            run_dir=deploy_test_dir,
            project_path=project,
            language=language,
            platform="docker",
            example=example,
            dtrx_source=dtrx_source,
        )
        ts = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
        index_path = writer.write(timestamp=ts)
        return index_path
    except Exception:
        logger.exception(
            "deploy_structured_output_failed project=%s",
            project_name,
        )
        return None


def _run_single_project_deploy_tests(
    project: Path,
    project_name: str,
    paths: dict[str, Path],
    timestamp: str,
    language: str,
    *,
    verbose: bool = False,
) -> ProjectResult | None:
    """Run one generated project's deploy tests through its ``tests/run-tests.ps1 -Deploy``.

    The project's deploy runner owns the whole container lifecycle (down, build, up,
    test, logs, down); this saves whatever containers it left and tears them down
    afterwards, however the run ended.

    Returns:
        The project's result, or None when its entry point declares no ``-Deploy``
        switch -- a deployment with no container orchestration has no deploy tests.
    """
    entry_point = project / TEST_RUNNER_ENTRY_POINT
    if not entry_point.is_file():
        return _missing_entry_point_result(project_name)
    if not parse_scripts([entry_point])[entry_point.resolve()].declares(DEPLOY_TESTS_SWITCH):
        return None

    deploy_test_dir = project / ".test_results" / f"deploy-test-{timestamp}"
    (deploy_test_dir / "docker-logs").mkdir(parents=True, exist_ok=True)
    arguments = [RESULTS_DIR_ARGUMENT, str(deploy_test_dir), *([VERBOSE_ARGUMENT] if verbose else [])]
    try:
        success, output = _run_entry_point(
            project, DEPLOY_TESTS_SWITCH, arguments, f"Deployment tests for {project_name}",
        )
    finally:
        _save_docker_logs_for_project(project, deploy_test_dir)
        _ensure_docker_cleanup(project)

    stats = parse_test_statistics(output) if output else _empty_stats()
    result: ProjectResult = {
        "name": project_name,
        "success": success,
        **stats,
    }

    if output is not None:
        # The runner may already have written its own copy of this log; keep it and
        # add what this run captured from the console.
        output_log = deploy_test_dir / "deploy-test-output.log"
        existing = output_log.read_text(encoding="utf-8") + "\n" if output_log.exists() else ""
        output_log.write_text(existing + _strip_ansi(output), encoding="utf-8")

    save_test_summary_log(
        step_num=5,
        step_name=f"Deployment Tests for {project_name}",
        paths=paths,
        project_results=[result],
        total_projects=1,
        success_count=1 if success else 0,
        fail_count=0 if success else 1,
        total_passed_tests=stats["passed"],
        total_failed_tests=stats["failed"],
        total_error_tests=stats["errors"],
        total_skipped_tests=stats["skipped"],
        step5_output_dir=deploy_test_dir,
    )
    result["_index_path"] = _write_deploy_structured_output(
        project, project_name, deploy_test_dir, paths, timestamp, language,
    )
    return result


def _build_parser() -> argparse.ArgumentParser:
    """The workflow runner's command line."""
    parser = argparse.ArgumentParser(
    description="Complete workflow runner for Datrix",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
    python scripts/test/lib/run_complete.py <example_path> [output_path]  # output_path optional (from test-projects.json)
    python scripts/test/lib/run_complete.py -All # Run all examples
    python scripts/test/lib/run_complete.py -All --test-set foundation # Run foundation examples only
    python scripts/test/lib/run_complete.py -Skip1 # Skip Step 1 (syntax checker)
    python scripts/test/lib/run_complete.py -Skip3 -Skip4 -Skip5 # Skip Steps 3, 4, and 5
    """
    )
    parser.add_argument(
    "example_path",
    nargs="?",
    help="Path to the .dtrx file to generate (required when -All is not specified)"
    )
    parser.add_argument(
    "output_path",
    nargs="?",
    default=None,
    help="Output directory for the generated project. When omitted, derived from test-projects.json (defaultLanguage, defaultPlatform) and the example path."
    )
    parser.add_argument(
    "-All",
    dest="All",
    action="store_true",
    help="Run all examples instead of a single example"
    )
    parser.add_argument(
    "--test-set",
    dest="test_set",
    type=str,
    default="all",
    help="Test set name (e.g. all, foundation, features, domains). Only used with -All."
    )
    parser.add_argument(
    "-Language",
    "--language",
    dest="language",
    default="python",
    choices=sorted(registered_language_names()),
    help="Target generation language, forwarded through generate.ps1 to "
         "datrix generate --language -- the real generation target, not just "
         "an output-path label (default: python; any registered "
         "datrix.languages target)"
    )
    parser.add_argument(
    "-Platform",
    "--platform",
    dest="platform",
    default="docker-compose",
    help="Target runtime for output-path derivation (default: docker-compose). "
         "Options: docker-compose, azure-app-service, ecs-fargate, app-runner. "
         "The provider segment is read from each project's config/system.dcfg, not this flag. "
         "A legacy 'runtime/provider' value is accepted; only the runtime half is used."
    )
    parser.add_argument(
    "-Hosting",
    "--hosting",
    dest="hosting",
    default=None,
    help="Hosting platform override (docker, aws, azure)"
    )
    parser.add_argument(
    "-Skip1",
    action="store_true",
    help="Skip Step 1 (syntax checker)"
    )
    parser.add_argument(
    "-Skip2",
    action="store_true",
    help="Skip Step 2 (code generation)"
    )
    parser.add_argument(
    "-Skip3",
    action="store_true",
    help="Skip Step 3 (unit tests for generated projects)"
    )
    parser.add_argument(
    "-Skip4",
    action="store_true",
    help="Skip Step 4 (spec tests for generated projects)"
    )
    parser.add_argument(
    "-Skip5",
    action="store_true",
    help="Skip Step 5 (deployment tests for generated projects)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (DEBUG level instead of INFO)")
    parser.add_argument("--llm-summary", action="store_true", help="Print advisory local LLM post-run summary from aggregate indexes")
    parser.add_argument("--llm-limit", type=int, default=DEFAULT_LLM_CLUSTER_LIMIT, help=f"Maximum clusters/projects per aggregate index for LLM summary (default: {DEFAULT_LLM_CLUSTER_LIMIT})")
    parser.add_argument("--llm-num-predict", type=int, default=DEFAULT_LLM_NUM_PREDICT, help=f"Max generated tokens (default: {DEFAULT_LLM_NUM_PREDICT})")
    parser.add_argument("--llm-temperature", type=float, default=DEFAULT_LLM_TEMPERATURE, help=f"Sampling temperature (default: {DEFAULT_LLM_TEMPERATURE})")
    add_local_llm_arguments(parser)
    return parser


#: The banner's mode label for each -All test set; any other set is "ALL EXAMPLES".
_TEST_SET_MODE_LABELS = {
    "foundation": "FOUNDATION EXAMPLES",
    "non-foundation": "NON-FOUNDATION EXAMPLES",
    "domains": "DOMAINS EXAMPLES",
    "patterns": "PATTERNS EXAMPLES",
    "builtins": "BUILTINS EXAMPLES",
    "reference": "REFERENCE EXAMPLES",
}

#: ``(skip flag, step label)`` the banner lists when the flag is set.
_SKIP_FLAG_LABELS = (
    ("Skip1", "Step 1 (Syntax Checker)"),
    ("Skip2", "Step 2 (Code Generation)"),
    ("Skip3", "Step 3 (Unit Tests)"),
    ("Skip4", "Step 4 (Spec Tests)"),
    ("Skip5", "Step 5 (Deployment Tests)"),
)

_STEP3_TITLE = "Run Unit Tests for Generated Projects"
_STEP4_TITLE = "Run Deployment Tests (Spec + Integration) for Generated Projects"


def main(argv: list[str] | None = None) -> int:
    """Main entry point; *argv* defaults to the process's command line."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Only the runtime segment of --platform is used (a "runtime/provider"
    # value keeps its runtime half): each project's config/system.dcfg
    # supplies the provider segment of the output path.
    args.platform = args.platform.split("/", 1)[0]
    _resolve_single_example_paths(parser, args)

    paths = get_paths()
    start_time = datetime.now()
    _print_workflow_banner(args, paths, start_time)

    try:
        failed_steps = _run_workflow_steps(args, paths)
        return _finish_workflow(args, paths, failed_steps, start_time)
    except KeyboardInterrupt:
        _print_workflow_interrupted(start_time)
        return 130


def _resolve_single_example_paths(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Without -All, require the example path and derive a missing output
    path from test-projects.json; a failure is a usage error."""
    if args.All:
        return
    if not args.example_path:
        parser.error("example_path is required when -All is not specified")
    if not args.output_path:
        try:
            args.output_path = str(get_default_output_path(
                args.example_path,
                language=args.language,
                runtime=args.platform,
            ))
        except (ValueError, FileNotFoundError) as e:
            parser.error(str(e))


def _print_workflow_banner(args: argparse.Namespace, paths: dict[str, Path], start_time: datetime) -> None:
    """The run's header: start time, mode, skipped steps and working directory."""
    print_info("=" * 60)
    print_info("Datrix COMPLETE WORKFLOW")
    print_info("=" * 60)
    print_info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.All:
        mode_label = _TEST_SET_MODE_LABELS.get(args.test_set, "ALL EXAMPLES")
        print_info(f"Mode: {mode_label}")
    else:
        print_info("Mode: SINGLE EXAMPLE")
        print_info(f" Example: {args.example_path}")
        print_info(f" Output: {args.output_path}")
        print_info(f" Language: {args.language}")
        print_info(f" Runtime: {args.platform}")

    skip_info = [label for flag, label in _SKIP_FLAG_LABELS if getattr(args, flag)]
    if skip_info:
        print_info("Skipped Steps: " + ", ".join(skip_info))
    print_info(f"Working Directory: {paths['datrix_root']}")
    print_info("=" * 60)


def _run_workflow_steps(args: argparse.Namespace, paths: dict[str, Path]) -> list[str]:
    """Run every step not skipped; return the labels of the steps that failed.
    Steps 3–4 run only if every non-skipped step among 1–2 succeeded."""
    failed_steps: list[str] = []
    early_steps_failed = _run_early_steps(args, paths, failed_steps)
    _run_test_steps(args, paths, failed_steps, early_steps_failed)
    # Deployment tests (Step 4) cover spec and integration tests; -Skip5 selects no step.
    if args.Skip5:
        print_warning("Note: Step 5 has been merged into Step 4. -Skip5 flag is deprecated.")
    return failed_steps


def _run_early_steps(args: argparse.Namespace, paths: dict[str, Path], failed_steps: list[str]) -> bool:
    """Steps 1 (syntax check) and 2 (generation); return whether either ran and failed."""
    step1_failed = False
    step2_failed = False
    if args.Skip1:
        print_step(1, "Syntax Checker")
        print_warning("Skipping Step 1 as requested (-Skip1 flag)")
    elif not step1_syntax_checker(paths):
        print_warning("Step 1 failed; Steps 3 and 4 will be skipped.")
        failed_steps.append("Step 1: Syntax Checker")
        step1_failed = True

    single_example = None if args.All else args.example_path
    single_output = None if args.All else args.output_path
    test_set = args.test_set if args.All else "all"
    if args.Skip2:
        print_step(2, "Code Generation")
        print_warning("Skipping Step 2 as requested (-Skip2 flag)")
    elif not step2_generate(
        args.All, paths, single_example, single_output, args.language, args.platform, test_set, args.hosting,
    ):
        print_warning("Step 2 failed; Steps 3 and 4 will be skipped.")
        failed_steps.append("Step 2: Code Generation")
        step2_failed = True
    return step1_failed or step2_failed


def _run_test_steps(
    args: argparse.Namespace, paths: dict[str, Path], failed_steps: list[str], early_steps_failed: bool
) -> None:
    """Steps 3 (unit tests) and 4 (deployment tests), each skipped when
    requested or when an earlier step failed."""
    single_output = None if args.All else args.output_path
    test_set = args.test_set if args.All else None
    if args.Skip3:
        print_step(3, _STEP3_TITLE)
        print_warning("Skipping Step 3 as requested (-Skip3 flag)")
    elif early_steps_failed:
        print_step(3, _STEP3_TITLE)
        print_warning("Skipping Step 3 (not run; Step 1 or Step 2 failed).")
    elif not step3_run_unit_tests(
        args.All, paths, single_output, test_set, args.language, args.platform, verbose=args.verbose,
    ):
        print_warning("Step 3 failed. Continuing to Step 4...")
        failed_steps.append("Step 3: Unit Tests")

    if args.Skip4:
        print_step(4, _STEP4_TITLE)
        print_warning("Skipping Step 4 as requested (-Skip4 flag)")
    elif early_steps_failed:
        print_step(4, _STEP4_TITLE)
        print_warning("Skipping Step 4 (not run; Step 1 or Step 2 failed).")
    elif not step4_run_deployment_tests(
        args.All, paths, single_output, test_set, args.language, args.platform, verbose=args.verbose,
    ):
        print_warning("Step 4 failed. Continuing to final summary...")
        failed_steps.append("Step 4: Deployment Tests")


def _finish_workflow(
    args: argparse.Namespace, paths: dict[str, Path], failed_steps: list[str], start_time: datetime
) -> int:
    """Print the final summary and the optional LLM summary; return the exit code."""
    end_time = datetime.now()
    duration = end_time - start_time

    print()
    if failed_steps:
        print_error("=" * 60)
        print_error("WORKFLOW COMPLETED WITH FAILURES")
        print_error("=" * 60)
        print_info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Duration: {duration}")
        print()
        print_error(f"Failed Steps ({len(failed_steps)}):")
        for step in failed_steps:
            print_error(f" [X] {step}")
        print_error("=" * 60)
        _print_llm_post_run_summary(args, paths, failed_steps)
        return 1
    print_success("=" * 60)
    print_success("ALL STEPS COMPLETED SUCCESSFULLY!")
    print_success("=" * 60)
    print_info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Duration: {duration}")
    print_success("=" * 60)
    _print_llm_post_run_summary(args, paths, failed_steps)
    return 0


def _print_workflow_interrupted(start_time: datetime) -> None:
    """The banner a run interrupted by the user ends on."""
    print()
    print_warning("=" * 60)
    print_warning("WORKFLOW INTERRUPTED BY USER")
    print_warning("=" * 60)
    end_time = datetime.now()
    duration = end_time - start_time
    print_info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Interrupted: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Duration: {duration}")
    print_warning("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
