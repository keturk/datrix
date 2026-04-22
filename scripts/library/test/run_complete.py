#!/usr/bin/env python3
"""
Complete Workflow Runner for Datrix
Executes all validation, generation, and testing steps in sequence

Usage:
    python scripts/library/test/run_complete.py <example_path> [output_path]  # output_path optional (from test-projects.json)
    python scripts/library/test/run_complete.py -All # Run all examples
    python scripts/library/test/run_complete.py -All --test-set tutorial-all # Run tutorial examples only
"""

import argparse
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Ensure stdout/stderr handle Unicode (Docker output contains progress bars, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add library directory to path to import shared modules
# library/test -> library (where shared/ is located)
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root, get_venv_python
from shared.logging_utils import LogConfig, TeeLogger, ColorCodes, colorize
from shared.test_projects import get_test_projects, get_default_output_path

# Global set to track all active subprocesses
_active_processes = set()
_process_lock = threading.Lock()


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
            try:
                if process.poll() is None:  # Still running
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    except Exception:
                        pass  # Ignore errors during cleanup
            except Exception:
                pass  # Ignore errors during cleanup


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



def run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    description: str = "",
    capture_output: bool = False,
    log_file: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Run a command and return True if successful

    Args:
        cmd: Command and arguments as list
        cwd: Working directory
        description: Description of what the command does
        capture_output: If True, capture and return stdout/stderr while still displaying it
        log_file: If set, tee stdout/stderr to this file (plain text, no ANSI)

    Returns:
        Tuple of (success: bool, output: Optional[str])
    """
    if description:
        print_info(f"Running: {description}")

    print_info(f"Command: {' '.join(str(c) for c in cmd)}")

    if capture_output or log_file is not None:
        # Set environment variables for unbuffered output
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
    else:
        env = None

    if log_file is not None:
        # Tee subprocess output to console and log file (same behavior as generate.ps1)
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
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                while True:
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        continue
                    print(line, end="", flush=True)
                    f.write(_strip_ansi(line))
                    f.flush()
        except KeyboardInterrupt:
            print("\n\nInterrupted! Terminating subprocess...", flush=True)
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except Exception:
                pass
            raise
        finally:
            unregister_process(process)
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            remaining = process.stdout.read()
            if remaining:
                print(remaining, flush=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(_strip_ansi(remaining))
        returncode = process.returncode
        if returncode == 0:
            print_success("[OK] Success")
            return True, None
        print_error(f"[FAILED] Exit code: {returncode}")
        return False, None

    if capture_output:
        # Use Popen to capture output while still displaying it
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,  # Line buffered
            env=env,
        )

        # Register process for cleanup
        register_process(process)

        output_lines = []
        import time

        # Read output line by line and both display and capture it
        last_output_time = time.time()
        progress_shown = False

        try:
            try:
                while True:
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        current_time = time.time()
                        if current_time - last_output_time > 2:
                            if not progress_shown:
                                print(" [Test execution in progress - please wait for output...]", flush=True)
                            progress_shown = True
                        time.sleep(0.5)
                        continue

                    line = line.rstrip('\n\r')
                    output_lines.append(line)
                    print(line, flush=True)
                    last_output_time = time.time()
                    progress_shown = False
            except KeyboardInterrupt:
                print("\n\nInterrupted! Terminating subprocess...", flush=True)
                try:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        except Exception:
                            pass
                except Exception:
                    pass
                raise
        finally:
            unregister_process(process)
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            remaining = process.stdout.read()
            if remaining:
                remaining_lines = remaining.rstrip('\n\r').split('\n')
                for line in remaining_lines:
                    if line.strip():
                        output_lines.append(line)
                    print(line, flush=True)

        output = '\n'.join(output_lines)
        returncode = process.returncode
    else:
        try:
            result = subprocess.run(cmd, cwd=cwd)
            returncode = result.returncode
            output = None
        except KeyboardInterrupt:
            print("\n\nInterrupted!", flush=True)
            raise

    if returncode == 0:
        print_success(f"[OK] Success")
        return True, output
    else:
        print_error(f"[FAILED] Exit code: {returncode}")
        return False, output


def get_paths() -> dict[str, Path]:
    """Get all necessary paths relative to this script location"""
    # This script is in datrix/scripts/library/test/
    script_dir = Path(__file__).parent.resolve()
    # script_dir -> library -> scripts -> datrix -> datrix-root
    datrix_root = get_datrix_root()
    datrix_dir = datrix_root / "datrix"

    return {
    "script_dir": script_dir,
    "datrix_root": datrix_root,
    "datrix_dir": datrix_dir,
    }


def _find_powershell() -> Optional[str]:
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

    script_path = paths["datrix_dir"] / "scripts" / "dev" / "syntax-checker.ps1"
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
    example_path: Optional[str] = None,
    output_path: Optional[str] = None,
    language: str = "python",
    platform: str = "docker",
    test_set: str = "all",
    hosting: Optional[str] = None,
    *,
    skip_install: bool = False,
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
        cmd.extend(["-Language", language])
        cmd.extend(["-Platform", platform])
        if test_set != "all":
            cmd.extend(["-TestSet", test_set])
    else:
        if not example_path or not output_path:
            print_error("Example path and output path are required when -All is not specified")
            return False

        print_step(2, f"Generate Example: {Path(example_path).name}")

        source_file = Path(example_path).resolve()
        output_dir = Path(output_path).resolve()

        if not source_file.exists():
            print_error(f"Example file not found at: {source_file}")
            return False

        cmd.extend([str(source_file), str(output_dir)])
        cmd.extend(["-Language", language])
        cmd.extend(["-Platform", platform])

    if hosting:
        cmd.extend(["-Hosting", hosting])

    if skip_install:
        cmd.append("-SkipInstall")

    success, _ = run_command(
        cmd,
        cwd=paths["datrix_root"],
        description="Generating via generate.ps1",
    )
    return success


def parse_test_statistics(output: str) -> dict:
    """Parse test statistics from unit_tests.py, deploy_test.py, or Jest output.

    Supports three formats:
    - unit_tests.py summary format: "Total Passed: 35"
    - pytest summary line format: "===== 35 passed, 1 failed in 8.48s ====="
    - Jest summary format: "Tests:       5 passed, 5 total" or "Tests:  1 failed, 4 passed, 1 skipped, 6 total"
    """
    stats = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }

    if not output:
        return stats

    # Try unit_tests.py "Total Passed: X" format first
    match = re.search(r"Total Passed:\s+(\d+)", output)
    if match:
        stats["passed"] = int(match.group(1))

    match = re.search(r"Total Failed:\s+(\d+)", output)
    if match:
        stats["failed"] = int(match.group(1))

    match = re.search(r"Total Errors:\s+(\d+)", output)
    if match:
        stats["errors"] = int(match.group(1))

    match = re.search(r"Total Skipped:\s+(\d+)", output)
    if match:
        stats["skipped"] = int(match.group(1))

    # If no results found, try pytest summary line format.
    # Pytest summary lines look like: "===== 35 passed in 8.48s ====="
    # Require leading "=" to avoid matching unrelated output.
    if stats["passed"] == 0 and stats["failed"] == 0:
        for line in output.split("\n"):
            line = line.strip()
            if (
                line.startswith("=")
                and ("passed" in line or "failed" in line or "error" in line)
                and re.search(r" in \d", line)
            ):
                m = re.search(r"(\d+) passed", line)
                if m:
                    stats["passed"] += int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    stats["failed"] += int(m.group(1))
                m = re.search(r"(\d+) error", line)
                if m:
                    stats["errors"] += int(m.group(1))
                m = re.search(r"(\d+) skipped", line)
                if m:
                    stats["skipped"] += int(m.group(1))

    # If still no results, try Jest summary format.
    # Jest outputs: "Tests:       5 passed, 5 total"
    # or: "Tests:  1 failed, 4 passed, 1 skipped, 6 total"
    if stats["passed"] == 0 and stats["failed"] == 0:
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("Tests:") and "total" in line:
                m = re.search(r"(\d+) passed", line)
                if m:
                    stats["passed"] = int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    stats["failed"] = int(m.group(1))
                m = re.search(r"(\d+) skipped", line)
                if m:
                    stats["skipped"] = int(m.group(1))
                break

    return stats


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
    project_slug: Optional[str] = None,
) -> None:
    """
    Discover containers for the project via docker compose and save each container's
    logs under deploy_test_dir/docker-logs/. Does not fail Step 5 on docker errors.
    """
    docker_logs_dir = deploy_test_dir / "docker-logs"
    docker_logs_dir.mkdir(parents=True, exist_ok=True)

    compose_file = project / "docker-compose.yml"
    if not compose_file.exists():
        compose_file = project / "docker-compose.yaml"
        if not compose_file.exists():
            return

    # Get container names: docker compose [-p name] -f <file> ps -a --format "{{.Name}}"
    ps_cmd = ["docker", "compose"]
    project_name = _extract_compose_project_name(project)
    if project_name:
        ps_cmd.extend(["-p", project_name])
    ps_cmd.extend(["-f", str(compose_file), "ps", "-a", "--format", "{{.Name}}"])
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
        return

    if result.returncode != 0:
        if result.stderr:
            print_warning(f"Docker compose ps failed for {project.name}: {result.stderr.strip()}")
        return

    names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
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


_COMPOSE_NAME_RE_PY = re.compile(
    r'^COMPOSE_PROJECT_NAME\s*=\s*["\']([^"\']+)["\']', re.MULTILINE,
)
_COMPOSE_NAME_RE_JS = re.compile(
    r"const\s+COMPOSE_PROJECT_NAME\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE,
)

_DATRIX_CONFIG_PATH_MARKERS = (".generated", ".projects")


def _extract_compose_project_name(project: Path) -> str | None:
    """Extract the compose project name from the generated deploy test script.

    Searches ``tests/deploy_test.py`` (Python) and ``tests/deploy-test.js``
    (TypeScript) for the ``COMPOSE_PROJECT_NAME`` constant.
    Returns ``None`` if no test script is found or the constant is missing.
    """
    candidates: list[tuple[str, re.Pattern[str]]] = [
        ("tests/deploy_test.py", _COMPOSE_NAME_RE_PY),
        ("tests/deploy-test.js", _COMPOSE_NAME_RE_JS),
    ]
    for filename, pattern in candidates:
        test_file = project / filename
        if test_file.exists():
            try:
                content = test_file.read_text(encoding="utf-8")
                match = pattern.search(content)
                if match:
                    return match.group(1)
            except OSError:
                pass
    return None


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
        return

    if result.returncode != 0 or not result.stdout.strip():
        return

    try:
        projects = json.loads(result.stdout)
    except json.JSONDecodeError:
        return

    datrix_projects = [
        p for p in projects
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

    Runs after each deploy_test.py subprocess to ensure no resources are left
    behind, regardless of how the subprocess exited (success, failure, or killed).
    Idempotent — safe to call even if containers are already stopped/removed.
    """
    compose_file = project / "docker-compose.yml"
    if not compose_file.exists():
        compose_file = project / "docker-compose.yaml"
        if not compose_file.exists():
            return

    cmd = ["docker", "compose"]
    project_name = _extract_compose_project_name(project)
    if project_name:
        cmd.extend(["-p", project_name])
    cmd.extend(["-f", str(compose_file), "down", "-v", "--rmi", "local", "--remove-orphans"])

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
    step5_output_dir: Optional[Path] = None,
) -> Path:
    """Save test summary to a log file.

    When step5_output_dir is set, write to step5_output_dir/deploy-test-summary.log.
    Otherwise fall back to .generated/.test_results/ (Step 4 unit tests).
    """
    if step5_output_dir is not None:
        log_path = step5_output_dir / "deploy-test-summary.log"
    else:
        generated_base = paths["datrix_root"] / ".generated"
        test_results_dir = generated_base / ".test_results"
        test_results_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_filename = f"step{step_num}-{step_name.lower().replace(' ', '-')}-{timestamp}.log"
        log_path = test_results_dir / log_filename

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
        f.write(f"Total Tests:\n")
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
 
        if successful_projects:
            f.write(f"\nSuccessful Projects ({len(successful_projects)}):\n")
            for result in successful_projects:
                f.write(f" ✓ {result['name']}\n")
                # Show test counts
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    f.write(f"   Tests: {', '.join(test_info)}\n")
            f.write("\n")

        if failed_projects:
            f.write(f"Failed Projects ({len(failed_projects)}):\n")
            for result in failed_projects:
                f.write(f" ✗ {result['name']}\n")
                # Show test counts
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    f.write(f"   Tests: {', '.join(test_info)}\n")
            f.write("\n")
 
        f.write("=" * 60 + "\n")
 
        return log_path


def _has_test_script(pkg_json: Path) -> bool:
    """Check whether a package.json has a "test" script."""
    if not pkg_json.exists():
        return False
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        return "test" in data.get("scripts", {})
    except (json.JSONDecodeError, OSError):
        return False


def _find_ts_service_dirs(project: Path) -> list[Path]:
    """Find TypeScript service directories within a generated project.

    Generated TypeScript projects have the layout:
        project_root/
            service_a/          <-- service dir (has package.json, jest.config.ts, test/)
            service_b/
            docker-compose.yml
            tests/              <-- project-level deploy tests
    """
    service_dirs: list[Path] = []
    if not project.is_dir():
        return service_dirs
    for child in sorted(project.iterdir()):
        if not child.is_dir():
            continue
        pkg_json = child / "package.json"
        if _has_test_script(pkg_json):
            service_dirs.append(child)
    return service_dirs


def _is_typescript_project(project: Path) -> bool:
    """Check whether a generated project contains TypeScript services with tests."""
    return len(_find_ts_service_dirs(project)) > 0


def _find_pnpm() -> Optional[str]:
    """Find pnpm executable on the system."""
    return shutil.which("pnpm")


def _find_typescript_root(project: Path) -> Optional[Path]:
    """Find the TypeScript output root by walking up path components.

    Looks for a path component named ``typescript``, then returns the
    full path up to and including that component. Returns None if not
    found. Works with any output base directory.
    """
    parts = project.resolve().parts
    for idx, part in enumerate(parts):
        if part == "typescript":
            return Path(*parts[: idx + 1])
    return None


def _shared_ts_node_modules_exists(project: Path) -> bool:
    """Check if a shared node_modules exists at the TypeScript root.

    Returns True if the TypeScript root has both ``node_modules/`` and
    ``.tsc_cache/`` (the marker created by hooks.py shared install).
    """
    ts_root = _find_typescript_root(project)
    if ts_root is None:
        return False
    return (ts_root / "node_modules").exists() and (ts_root / ".tsc_cache").exists()


def _run_pnpm_install(service_dir: Path, label: str, parallel: bool) -> bool:
    """Run pnpm install for a TypeScript service if node_modules is missing."""
    node_modules = service_dir / "node_modules"
    if node_modules.exists():
        return True

    pnpm = _find_pnpm()
    if pnpm is None:
        print_error(f" pnpm not found on PATH — cannot install dependencies for {label}")
        return False

    success, _ = run_command(
        [pnpm, "install"],
        cwd=service_dir,
        description=f"pnpm install for {label}" if not parallel else "",
        capture_output=True,
    )
    return success


def _write_ts_unit_unit_tests_summary_log(
    project: Path,
    results_dir: Path,
    *,
    total_passed: int,
    total_failed: int,
    total_errors: int,
    total_skipped: int,
    all_success: bool,
) -> None:
    """
    Write unit-tests-summary.log for TypeScript unit test runs.

    Matches the filename and markers parsed by status_unit_tests.py (same as
    generated Python tests/unit_tests.py). The previous summary.log name was
    never picked up by the status reporter.
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "=" * 40,
        "Run Tests Summary Log",
        "=" * 40,
        f"Project: {project}",
        f"Timestamp: {stamp}",
        "=" * 40,
        "",
        f"Total Passed: {total_passed}",
        f"Total Failed: {total_failed}",
        f"Total Errors: {total_errors}",
        f"Total Skipped: {total_skipped}",
        "",
    ]
    total_issues = total_failed + total_errors
    if not all_success or total_issues > 0:
        lines.append("Tests FAILED!")
    elif total_passed == 0:
        lines.append("NO TESTS COLLECTED — nothing passed!")
    else:
        lines.append("All tests PASSED!")
    summary_path = results_dir / "unit-tests-summary.log"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_single_project_unit_tests(project: Path, generated_base: Path, parallel: bool = False, test_type: str = "unit") -> dict:
    """
    Helper function to run tests for a single project.
    Returns a dictionary with project result information.

    Supports both Python (unit_tests.py) and TypeScript (unit-tests.js / pnpm test) projects.
    TypeScript projects have per-service package.json files in subdirectories.

    Args:
        project: Path to the project directory
        generated_base: Base path for generated projects
        parallel: If True, suppress real-time output (for parallel execution)
        test_type: Type of tests to run ("unit", "spec", "integration")
    """
    project_name = project.relative_to(generated_base)
    empty_stats = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    # --- Python project: tests/unit_tests.py ---
    unit_tests_script = project / "tests" / "unit_tests.py"
    if unit_tests_script.exists():
        python_exe = get_venv_python()
        cmd = [str(python_exe), str(unit_tests_script), "--parallel"]
        test_desc = f"{test_type.capitalize()} tests for {project_name}" if not parallel else ""
        success, output = run_command(
            cmd,
            cwd=project,
            description=test_desc,
            capture_output=True,
        )
        stats = parse_test_statistics(output) if output else empty_stats
        return {
            "name": str(project_name),
            "success": success,
            "passed": stats["passed"],
            "failed": stats["failed"],
            "errors": stats["errors"],
            "skipped": stats["skipped"],
            "output": output if parallel else None,
        }

    # --- TypeScript project: prefer generated tests/unit-tests.js ---
    ts_unit_tests_js = project / "tests" / "unit-tests.js"
    if ts_unit_tests_js.exists():
        node = shutil.which("node")
        if node is None:
            print_error(f" node not found on PATH — skipping {project_name}")
            return {"name": str(project_name), "success": False, **empty_stats, "output": None}
        cmd = [node, str(ts_unit_tests_js)]
        if parallel:
            cmd.append("--parallel")
        test_desc = f"{test_type.capitalize()} tests for {project_name}" if not parallel else ""
        success, output = run_command(
            cmd,
            cwd=project,
            description=test_desc,
            capture_output=True,
        )
        stats = parse_test_statistics(output) if output else empty_stats
        return {
            "name": str(project_name),
            "success": success,
            "passed": stats["passed"],
            "failed": stats["failed"],
            "errors": stats["errors"],
            "skipped": stats["skipped"],
            "output": output if parallel else None,
        }

    # --- TypeScript project fallback: per-service package.json with "test" script ---
    ts_service_dirs = _find_ts_service_dirs(project)
    if ts_service_dirs:
        pnpm = _find_pnpm()
        if pnpm is None:
            print_error(f" pnpm not found on PATH — skipping {project_name}")
            return {"name": str(project_name), "success": False, **empty_stats, "output": None}

        # Create results directory (mirrors Python unit_tests.py behaviour)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        results_dir = project / ".test_results" / f"{test_type}-tests-{timestamp}"
        results_dir.mkdir(parents=True, exist_ok=True)

        all_success = True
        total_passed = 0
        total_failed = 0
        total_errors = 0
        total_skipped = 0
        combined_output: list[str] = []

        # Check for shared node_modules at the TypeScript root (created by hooks.py)
        shared_available = _shared_ts_node_modules_exists(project)

        for svc_dir in ts_service_dirs:
            svc_label = f"{project_name}/{svc_dir.name}"

            # Skip per-service install if shared node_modules is available
            if not shared_available:
                if not _run_pnpm_install(svc_dir, svc_label, parallel):
                    all_success = False
                    total_errors += 1
                    combined_output.append(f"pnpm install failed for {svc_dir.name}")
                    continue

            # Run Jest via pnpm test
            cmd = [pnpm, "test", "--", "--forceExit", "--no-cache"]
            success, output = run_command(
                cmd,
                cwd=svc_dir,
                description=f"Jest tests for {svc_label}" if not parallel else "",
                capture_output=True,
            )
            if not success:
                all_success = False
            if output:
                combined_output.append(output)
                stats = parse_test_statistics(output)
                total_passed += stats["passed"]
                total_failed += stats["failed"]
                total_errors += stats["errors"]
                total_skipped += stats["skipped"]
                # Save per-service output to results dir
                svc_log = results_dir / f"{svc_dir.name}-tests.log"
                svc_log.write_text(_strip_ansi(output), encoding="utf-8")

        _write_ts_unit_unit_tests_summary_log(
            project,
            results_dir,
            total_passed=total_passed,
            total_failed=total_failed,
            total_errors=total_errors,
            total_skipped=total_skipped,
            all_success=all_success,
        )
        if not parallel:
            print_info(f" Results saved to: {results_dir.relative_to(project)}")

        return {
            "name": str(project_name),
            "success": all_success,
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "skipped": total_skipped,
            "output": "\n".join(combined_output) if parallel else None,
        }

    # --- No test runner found ---
    return {
        "name": str(project_name),
        "success": False,
        **empty_stats,
        "output": None,
    }


def step3_run_unit_tests(all_examples: bool, paths: dict[str, Path], output_path: Optional[str] = None, test_set: Optional[str] = None, language: str = "python", platform: str = "docker") -> bool:
    """Step 3: Run unit tests for generated projects using unit_tests.py"""
    if all_examples:
        print_step(3, "Run Unit Tests for Generated Projects")
        generated_base = paths["datrix_root"] / ".generated"
        # Find generated projects: by test set or by scanning .generated
        projects = []
        if test_set:
            proj_list = get_test_projects(test_set=test_set, language=language, platform=platform)
            projects = [Path(p["output"]) for p in proj_list if Path(p["output"]).exists()]
        elif generated_base.exists():
            # Scan for Python projects (tests/unit_tests.py)
            for item in generated_base.rglob("unit_tests.py"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    projects.append(project_dir)
            # Scan for TypeScript projects (service subdirs with package.json + test script)
            seen = {p.resolve() for p in projects}
            for item in generated_base.rglob("package.json"):
                # package.json is inside a service dir; project root is one level up
                service_dir = item.parent
                project_dir = service_dir.parent
                if project_dir.resolve() not in seen and _has_test_script(item):
                    projects.append(project_dir)
                    seen.add(project_dir.resolve())

        if not projects:
            print_warning("No generated projects found to test")
            return True

        print_info(f"Found {len(projects)} generated projects to test")
        print_info(f"Running projects sequentially (services within each project run in parallel)...")
        print()

        # Run projects SEQUENTIALLY (one at a time)
        # But services within each project will run in parallel (via --parallel flag)
        project_results = []
        success_count = 0
        fail_count = 0

        try:
            for idx, project in enumerate(projects, 1):
                project_name = project.relative_to(generated_base)

                print()
                print_info(f"[{idx}/{len(projects)}] Running unit tests for: {project_name}")
                print("-" * 60)

                try:
                    project_result = _run_single_project_unit_tests(project, generated_base, parallel=False)
                    project_results.append(project_result)

                    print()
                    if project_result["success"]:
                        print_success(f" [OK] Unit tests passed for {project_name}")
                        success_count += 1
                    else:
                        print_error(f" [FAILED] Unit tests failed for {project_name}")
                        fail_count += 1

                    test_info = []
                    if project_result["passed"] > 0:
                        test_info.append(f"passed: {project_result['passed']}")
                    if project_result["failed"] > 0:
                        test_info.append(f"failed: {project_result['failed']}")
                    if project_result["errors"] > 0:
                        test_info.append(f"errors: {project_result['errors']}")
                    if project_result["skipped"] > 0:
                        test_info.append(f"skipped: {project_result['skipped']}")

                    if test_info:
                        print_info(f" Tests: {', '.join(test_info)}")

                    has_python_runner = (project / "tests" / "unit_tests.py").exists()
                    has_ts_runner = _is_typescript_project(project)
                    if not has_python_runner and not has_ts_runner:
                        print_warning(f" [SKIP] No test runner found for {project_name}")

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print_error(f" [ERROR] Exception while running tests for {project_name}: {e}")
                    project_results.append({
                        "name": str(project_name),
                        "success": False,
                        "passed": 0,
                        "failed": 0,
                        "errors": 1,
                        "skipped": 0,
                        "output": None,
                    })
                    fail_count += 1
        except KeyboardInterrupt:
            print()
            print_warning("=" * 60)
            print_warning("STEP 3 INTERRUPTED BY USER")
            print_warning("=" * 60)
            print_warning(f"Interrupted after testing {success_count + fail_count} of {len(projects)} projects")
            print_warning("Cleaning up and exiting...")
            print_warning("=" * 60)
            raise

        project_results.sort(key=lambda x: x["name"])

        # Calculate overall statistics
        total_passed_tests = sum(r["passed"] for r in project_results)
        total_failed_tests = sum(r["failed"] for r in project_results)
        total_error_tests = sum(r["errors"] for r in project_results)
        total_skipped_tests = sum(r["skipped"] for r in project_results)
 
        # Save summary to log file
        log_path = save_test_summary_log(
        step_num=3,
        step_name="Unit Tests for Generated Projects",
        paths=paths,
        project_results=project_results,
        total_projects=len(projects),
        success_count=success_count,
        fail_count=fail_count,
        total_passed_tests=total_passed_tests,
        total_failed_tests=total_failed_tests,
        total_error_tests=total_error_tests,
        total_skipped_tests=total_skipped_tests,
        )
 
        # Print comprehensive summary
        print()
        print_info("=" * 60)
        print_info("STEP 3 SUMMARY: Unit Tests for Generated Projects")
        print_info("=" * 60)
 
        print_info(f"Total Projects Tested: {len(projects)}")
        print_info(f" Successful Projects: {success_count}")
        print_info(f" Failed Projects: {fail_count}")
        print_info("")
        print_info(f"Total Tests:")
        print_info(f" Passed: {total_passed_tests}")
        if total_failed_tests > 0:
            print_error(f" Failed: {total_failed_tests}")
        if total_error_tests > 0:
            print_error(f" Errors: {total_error_tests}")
        if total_skipped_tests > 0:
            print_info(f" Skipped: {total_skipped_tests}")
 
        # Per-project breakdown
        print_info("")
        print_info("Per-Project Breakdown:")
        print_info("-" * 60)
 
        # Separate successful and failed projects
        successful_projects = [r for r in project_results if r["success"]]
        failed_projects = [r for r in project_results if not r["success"]]

        if successful_projects:
            print_success(f"Successful Projects ({len(successful_projects)}):")
            for result in successful_projects:
                print_success(f" ✓ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")
            print_info("")

        if failed_projects:
            print_error(f"Failed Projects ({len(failed_projects)}):")
            for result in failed_projects:
                print_error(f" ✗ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")

        print_info("=" * 60)
        print_info(f"Summary log saved to: {log_path.relative_to(paths['datrix_root'])}")

        return fail_count == 0
    else:
        if not output_path:
            print_error("Output path is required when -All is not specified")
            return False

        print_step(3, f"Run Unit Tests: {Path(output_path).name}")

        project_path_abs = Path(output_path).resolve()
        if not project_path_abs.exists():
            print_error(f"Generated project not found at: {project_path_abs}")
            return False

        # Reuse the same helper as batch mode — parent serves as base so
        # relative_to produces just the leaf directory name.
        result = _run_single_project_unit_tests(
            project_path_abs, project_path_abs.parent, parallel=False,
        )

        project_name = result["name"]

        # Print statistics
        test_info = []
        if result["passed"] > 0:
            test_info.append(f"passed: {result['passed']}")
        if result["failed"] > 0:
            test_info.append(f"failed: {result['failed']}")
        if result["errors"] > 0:
            test_info.append(f"errors: {result['errors']}")
        if result["skipped"] > 0:
            test_info.append(f"skipped: {result['skipped']}")
        if test_info:
            print_info("")
            print_info(f"Test Statistics: {', '.join(test_info)}")

        has_runner = (project_path_abs / "tests" / "unit_tests.py").exists() or _is_typescript_project(project_path_abs)
        if not has_runner:
            print_warning(f"No test runner found for {project_name}")
            return True

        if result["success"]:
            print_success(f"[OK] Unit tests passed for {project_name}")
            return True
        else:
            print_error(f"Unit tests failed for {project_name}")
            return False




def step4_run_deployment_tests(all_examples: bool, paths: dict[str, Path], output_path: Optional[str] = None, test_set: Optional[str] = None, language: str = "python", platform: str = "docker") -> bool:
    """Step 4: Run deployment tests (spec + integration) for generated projects using deploy_test.py"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Pre-flight: tear down all datrix compose projects to prevent port conflicts
    _cleanup_all_datrix_compose_projects()

    if all_examples:
        print_step(4, "Run Deployment Tests (Spec + Integration) for Generated Projects")
        generated_base = paths["datrix_root"] / ".generated"
        # Find generated projects: by test set or by scanning .generated
        projects = []
        if test_set:
            proj_list = get_test_projects(test_set=test_set, language=language, platform=platform)
            projects = [Path(p["output"]) for p in proj_list if Path(p["output"]).exists()]
        elif generated_base.exists():
            # Scan for Python projects (tests/deploy_test.py)
            for item in generated_base.rglob("deploy_test.py"):
                if item.parent.name == "tests":
                    projects.append(item.parent.parent)
            # Scan for TypeScript projects (tests/jest-deploy.config.ts or tests/deploy-test.js)
            seen = {p.resolve() for p in projects}
            for item in generated_base.rglob("jest-deploy.config.ts"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    if project_dir.resolve() not in seen:
                        projects.append(project_dir)
                        seen.add(project_dir.resolve())
            for item in generated_base.rglob("deploy-test.js"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    if project_dir.resolve() not in seen:
                        projects.append(project_dir)
                        seen.add(project_dir.resolve())

        if not projects:
            print_warning("No generated projects found to test")
            return True

        print_info(f"Found {len(projects)} generated projects to test")
        print()

        # Run deployment tests SEQUENTIALLY (one at a time)
        project_results = []
        success_count = 0
        fail_count = 0

        try:
            for idx, project in enumerate(projects, 1):
                project_name = str(project.relative_to(generated_base))

                print()
                print_info(f"[{idx}/{len(projects)}] Running deployment tests for: {project_name}")
                print("-" * 60)

                try:
                    project_result = _run_single_project_deploy_tests(project, project_name, paths, timestamp)
                    if project_result is None:
                        # Project was skipped (no deploy_test.py)
                        print_warning(f" [SKIP] No deployment test script found for {project_name}")
                        continue
                    project_results.append(project_result)

                    print()
                    if project_result["success"]:
                        print_success(f" [OK] Deployment tests passed for {project_name}")
                        success_count += 1
                    else:
                        print_error(f" [FAILED] Deployment tests failed for {project_name}")
                        fail_count += 1

                    test_info = []
                    if project_result.get("passed", 0) > 0:
                        test_info.append(f"passed: {project_result['passed']}")
                    if project_result.get("failed", 0) > 0:
                        test_info.append(f"failed: {project_result['failed']}")
                    if project_result.get("errors", 0) > 0:
                        test_info.append(f"errors: {project_result['errors']}")
                    if project_result.get("skipped", 0) > 0:
                        test_info.append(f"skipped: {project_result['skipped']}")

                    if test_info:
                        print_info(f" Tests: {', '.join(test_info)}")

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print_error(f" [ERROR] Exception while running tests for {project_name}: {e}")
                    project_results.append({
                        "name": str(project_name),
                        "success": False,
                        "passed": 0,
                        "failed": 0,
                        "errors": 1,
                        "skipped": 0,
                        "output": None,
                    })
                    fail_count += 1
        except KeyboardInterrupt:
            print()
            print_warning("=" * 60)
            print_warning("STEP 4 INTERRUPTED BY USER")
            print_warning("=" * 60)
            print_warning(f"Interrupted after testing {success_count + fail_count} of {len(projects)} projects")
            print_warning("Cleaning up and exiting...")
            print_warning("=" * 60)
            raise

        project_results.sort(key=lambda x: x["name"])

        # Calculate overall statistics
        total_passed_tests = sum(r.get("passed", 0) for r in project_results)
        total_failed_tests = sum(r.get("failed", 0) for r in project_results)
        total_error_tests = sum(r.get("errors", 0) for r in project_results)
        total_skipped_tests = sum(r.get("skipped", 0) for r in project_results)

        # Save summary to log file
        log_path = save_test_summary_log(
        step_num=4,
        step_name="Deployment Tests for Generated Projects",
        paths=paths,
        project_results=project_results,
        total_projects=len(projects),
        success_count=success_count,
        fail_count=fail_count,
        total_passed_tests=total_passed_tests,
        total_failed_tests=total_failed_tests,
        total_error_tests=total_error_tests,
        total_skipped_tests=total_skipped_tests,
        )
 
        # Print comprehensive summary
        print()
        print_info("=" * 60)
        print_info("STEP 4 SUMMARY: Deployment Tests for Generated Projects")
        print_info("=" * 60)
 
        print_info(f"Total Projects Tested: {len(projects)}")
        print_info(f" Successful Projects: {success_count}")
        print_info(f" Failed Projects: {fail_count}")
        print_info("")
        print_info(f"Total Tests:")
        print_info(f" Passed: {total_passed_tests}")
        if total_failed_tests > 0:
            print_error(f" Failed: {total_failed_tests}")
        if total_error_tests > 0:
            print_error(f" Errors: {total_error_tests}")
        if total_skipped_tests > 0:
            print_info(f" Skipped: {total_skipped_tests}")
 
        # Per-project breakdown
        print_info("")
        print_info("Per-Project Breakdown:")
        print_info("-" * 60)
 
        # Separate successful and failed projects
        successful_projects = [r for r in project_results if r["success"]]
        failed_projects = [r for r in project_results if not r["success"]]

        if successful_projects:
            print_success(f"Successful Projects ({len(successful_projects)}):")
            for result in successful_projects:
                print_success(f" ✓ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")
            print_info("")

        if failed_projects:
            print_error(f"Failed Projects ({len(failed_projects)}):")
            for result in failed_projects:
                print_error(f" ✗ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")

        print_info("=" * 60)
        print_info(f"Summary log saved to: {log_path.relative_to(paths['datrix_root'])}")

        return fail_count == 0
    else:
        if not output_path:
            print_error("Output path is required when -All is not specified")
            return False

        print_step(4, f"Run Deployment Tests: {Path(output_path).name}")

        project_path_abs = Path(output_path).resolve()
        if not project_path_abs.exists():
            print_error(f"Generated project not found at: {project_path_abs}")
            return False

        project_name = project_path_abs.name
        result = _run_single_project_deploy_tests(project_path_abs, project_name, paths, timestamp)

        if result is None:
            print_warning(f"No deployment test script found for {project_name}")
            return True

        # Print statistics
        test_info = []
        if result.get("passed", 0) > 0:
            test_info.append(f"passed: {result['passed']}")
        if result.get("failed", 0) > 0:
            test_info.append(f"failed: {result['failed']}")
        if result.get("errors", 0) > 0:
            test_info.append(f"errors: {result['errors']}")
        if result.get("skipped", 0) > 0:
            test_info.append(f"skipped: {result['skipped']}")
        if test_info:
            print_info("")
            print_info(f"Test Statistics: {', '.join(test_info)}")

        if result["success"]:
            print_success(f"[OK] Deployment tests passed for {project_name}")
            return True
        else:
            print_error(f"Deployment tests failed for {project_name}")
            return False


def _run_single_project_deploy_tests(
    project: Path,
    project_name: str,
    paths: dict[str, Path],
    timestamp: str,
) -> dict | None:
    """Run deployment tests for one project.  Returns result dict, or None if skipped."""
    deploy_test_script_py = project / "tests" / "deploy_test.py"
    deploy_test_script_js = project / "tests" / "deploy-test.js"
    empty_stats = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    # --- Python project: tests/deploy_test.py ---
    if deploy_test_script_py.exists():
        deploy_test_dir = project / ".test_results" / f"deploy-test-{timestamp}"
        deploy_test_dir.mkdir(parents=True, exist_ok=True)
        (deploy_test_dir / "docker-logs").mkdir(parents=True, exist_ok=True)

        python_exe = get_venv_python()
        try:
            success, output = run_command(
                [str(python_exe), str(deploy_test_script_py), "--results-dir", str(deploy_test_dir)],
                cwd=project,
                description=f"Deployment tests for {project_name}",
                capture_output=True,
            )
        finally:
            _save_docker_logs_for_project(project, deploy_test_dir)
            _ensure_docker_cleanup(project)

        stats = parse_test_statistics(output) if output else empty_stats
        result = {
            "name": project_name,
            "success": success,
            **stats,
        }

        if output is not None:
            (deploy_test_dir / "deploy-test-output.log").write_text(output, encoding="utf-8")

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
        return result

    # --- TypeScript project: tests/deploy-test.js (preferred) ---
    if deploy_test_script_js.exists():
        deploy_test_dir = project / ".test_results" / f"deploy-test-{timestamp}"
        deploy_test_dir.mkdir(parents=True, exist_ok=True)

        node = shutil.which("node")
        if node is None:
            print_error(f" node not found on PATH — cannot run deploy tests for {project_name}")
            return {"name": project_name, "success": False, **empty_stats}

        # The deploy-test.js script manages the full Docker lifecycle internally
        # (down → build → up → test → logs → down), just like Python's deploy_test.py
        try:
            success, output = run_command(
                [node, str(deploy_test_script_js), "--results-dir", str(deploy_test_dir)],
                cwd=project,
                description=f"Deployment tests for {project_name}",
                capture_output=True,
            )
        finally:
            # deploy-test.js saves its own Docker logs, but ensure cleanup happens
            _ensure_docker_cleanup(project)

        stats = parse_test_statistics(output) if output else empty_stats
        result = {
            "name": project_name,
            "success": success,
            **stats,
        }

        # Note: deploy-test.js writes its own deploy-test-output.log, but we save
        # the captured stdout here as well for consistency with run_complete.py's logging
        if output is not None:
            output_log = deploy_test_dir / "deploy-test-output.log"
            # Append to existing log if deploy-test.js already created it
            if output_log.exists():
                existing = output_log.read_text(encoding="utf-8")
                combined = existing + "\n" + _strip_ansi(output)
                output_log.write_text(combined, encoding="utf-8")
            else:
                output_log.write_text(_strip_ansi(output), encoding="utf-8")

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
        return result

    # --- TypeScript project: tests/jest-deploy.config.ts (fallback for projects without deploy_test.py) ---
    # Runner manages Docker Compose lifecycle (mirrors Python deploy_test.py):
    #   compose down → compose build → compose up → jest (health checks) → compose down
    jest_deploy_config = project / "tests" / "jest-deploy.config.ts"
    if jest_deploy_config.exists() and _is_typescript_project(project):
        deploy_test_dir = project / ".test_results" / f"deploy-test-{timestamp}"
        deploy_test_dir.mkdir(parents=True, exist_ok=True)
        (deploy_test_dir / "docker-logs").mkdir(parents=True, exist_ok=True)

        pnpm = _find_pnpm()
        if pnpm is None:
            print_error(f" pnpm not found on PATH — cannot run deploy tests for {project_name}")
            return {"name": project_name, "success": False, **empty_stats}

        tests_dir = project / "tests"

        # Install test dependencies (jest, ts-jest, typescript)
        if not _run_pnpm_install(tests_dir, f"{project_name}/tests", parallel=False):
            result = {"name": project_name, "success": False, **empty_stats}
            (deploy_test_dir / "deploy-test-output.log").write_text(
                f"pnpm install failed for {project_name}/tests\n", encoding="utf-8",
            )
            save_test_summary_log(
                step_num=5,
                step_name=f"Deployment Tests for {project_name}",
                paths=paths,
                project_results=[result],
                total_projects=1,
                success_count=0,
                fail_count=1,
                total_passed_tests=0,
                total_failed_tests=0,
                total_error_tests=0,
                total_skipped_tests=0,
                step5_output_dir=deploy_test_dir,
            )
            return result

        # Docker Compose lifecycle — managed by runner, not Jest
        compose_file = project / "docker-compose.yml"
        if not compose_file.exists():
            compose_file = project / "docker-compose.yaml"

        compose_available = compose_file.exists()
        compose_started = False

        if compose_available:
            # Ensure .env exists (docker-compose needs it for ${VAR} substitution).
            # Copy from .env.example if available; otherwise create an empty file.
            env_file = project / ".env"
            if not env_file.exists():
                env_example = project / ".env.example"
                if env_example.exists():
                    shutil.copy2(env_example, env_file)
                    print_info(f" [compose] Copied .env.example -> .env")
                else:
                    env_file.write_text("# Auto-created for deploy tests\n", encoding="utf-8")
                    print_info(f" [compose] Created empty .env (no .env.example found)")

            try:
                # Tear down any leftover containers
                print_info(f" [compose] Tearing down previous containers...")
                run_command(
                    ["docker", "compose", "-f", str(compose_file), "down", "-v", "--remove-orphans"],
                    cwd=project,
                    description="",
                )

                # Build images
                print_info(f" [compose] Building images...")
                build_ok, build_output = run_command(
                    ["docker", "compose", "-f", str(compose_file), "build", "--no-cache"],
                    cwd=project,
                    description="docker compose build",
                    capture_output=True,
                )
                if not build_ok:
                    print_error(f" [compose] Build failed for {project_name}")
                    _save_docker_logs_for_project(project, deploy_test_dir)
                    _ensure_docker_cleanup(project)
                    result = {"name": project_name, "success": False, **empty_stats}
                    if build_output is not None:
                        (deploy_test_dir / "deploy-test-output.log").write_text(
                            _strip_ansi(build_output), encoding="utf-8",
                        )
                    save_test_summary_log(
                        step_num=5,
                        step_name=f"Deployment Tests for {project_name}",
                        paths=paths,
                        project_results=[result],
                        total_projects=1,
                        success_count=0,
                        fail_count=1,
                        total_passed_tests=0,
                        total_failed_tests=0,
                        total_error_tests=0,
                        total_skipped_tests=0,
                        step5_output_dir=deploy_test_dir,
                    )
                    return result

                # Start services
                print_info(f" [compose] Starting services...")
                run_command(
                    ["docker", "compose", "-f", str(compose_file), "up", "-d"],
                    cwd=project,
                    description="docker compose up -d",
                )
                compose_started = True

            except Exception as exc:
                print_error(f" [compose] Error starting services: {exc}")
                _save_docker_logs_for_project(project, deploy_test_dir)
                _ensure_docker_cleanup(project)
                result = {"name": project_name, "success": False, **empty_stats}
                (deploy_test_dir / "deploy-test-output.log").write_text(
                    f"Docker compose failed: {exc}\n", encoding="utf-8",
                )
                save_test_summary_log(
                    step_num=5,
                    step_name=f"Deployment Tests for {project_name}",
                    paths=paths,
                    project_results=[result],
                    total_projects=1,
                    success_count=0,
                    fail_count=1,
                    total_passed_tests=0,
                    total_failed_tests=0,
                    total_error_tests=0,
                    total_skipped_tests=0,
                    step5_output_dir=deploy_test_dir,
                )
                return result

        # Run Jest deploy tests (health checks + endpoint validation)
        try:
            success, output = run_command(
                [pnpm, "exec", "jest", "--config", "jest-deploy.config.ts", "--forceExit", "--no-cache"],
                cwd=tests_dir,
                description=f"Jest deployment tests for {project_name}",
                capture_output=True,
            )
        finally:
            _save_docker_logs_for_project(project, deploy_test_dir)
            if compose_started:
                _ensure_docker_cleanup(project)

        stats = parse_test_statistics(output) if output else empty_stats
        result = {
            "name": project_name,
            "success": success,
            **stats,
        }

        if output is not None:
            (deploy_test_dir / "deploy-test-output.log").write_text(
                _strip_ansi(output), encoding="utf-8",
            )

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
        return result

    print_warning(f" [SKIP] No deploy_test.py or jest-deploy.config.ts found for {project_name}")
    return {"name": project_name, "success": False, **empty_stats}


def step5_run_deployment_tests(all_examples: bool, paths: dict[str, Path], output_path: Optional[str] = None, test_set: Optional[str] = None, language: str = "python", platform: str = "docker") -> bool:
    """Step 5: Run deployment/integration tests for generated projects using deploy_test.py"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if all_examples:
        print_step(5, "Run Deployment Tests for Generated Projects")
        generated_base = paths["datrix_root"] / ".generated"
        projects = []
        if test_set:
            proj_list = get_test_projects(test_set=test_set, language=language, platform=platform)
            projects = [Path(p["output"]) for p in proj_list if Path(p["output"]).exists()]
        elif generated_base.exists():
            # Scan for Python projects (tests/deploy_test.py)
            for item in generated_base.rglob("deploy_test.py"):
                if item.parent.name == "tests":
                    projects.append(item.parent.parent)
            # Scan for TypeScript projects (tests/jest-deploy.config.ts)
            seen = {p.resolve() for p in projects}
            for item in generated_base.rglob("jest-deploy.config.ts"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    if project_dir.resolve() not in seen:
                        projects.append(project_dir)
                        seen.add(project_dir.resolve())

        if not projects:
            print_warning("No generated projects found to test")
            return True

        print_info(f"Found {len(projects)} generated projects to test")

        success_count = 0
        fail_count = 0
        project_results = []

        for project in projects:
            project_name = str(project.relative_to(generated_base))
            print()
            print_info(f"Running deployment tests for: {project_name}")
            print("-" * 60)

            result = _run_single_project_deploy_tests(project, project_name, paths, timestamp)
            if result is None:
                continue  # Skipped (e.g. TypeScript)

            project_results.append(result)
            if result["success"]:
                print_success(f" [OK] Deployment tests passed for {project_name}")
                success_count += 1
            else:
                print_error(f" [FAILED] Deployment tests failed for {project_name}")
                fail_count += 1

        # Calculate overall statistics
        total_passed_tests = sum(r["passed"] for r in project_results)
        total_failed_tests = sum(r["failed"] for r in project_results)
        total_error_tests = sum(r["errors"] for r in project_results)
        total_skipped_tests = sum(r["skipped"] for r in project_results)

        # Print comprehensive summary
        print()
        print_info("=" * 60)
        print_info("STEP 5 SUMMARY: Deployment Tests for Generated Projects")
        print_info("=" * 60)

        print_info(f"Total Projects Tested: {len(projects)}")
        print_info(f" Successful Projects: {success_count}")
        print_info(f" Failed Projects: {fail_count}")
        print_info("")
        print_info("Total Tests:")
        print_info(f" Passed: {total_passed_tests}")
        if total_failed_tests > 0:
            print_error(f" Failed: {total_failed_tests}")
        if total_error_tests > 0:
            print_error(f" Errors: {total_error_tests}")
        if total_skipped_tests > 0:
            print_info(f" Skipped: {total_skipped_tests}")

        # Per-project breakdown
        print_info("")
        print_info("Per-Project Breakdown:")
        print_info("-" * 60)

        successful_projects = [r for r in project_results if r["success"]]
        failed_projects = [r for r in project_results if not r["success"]]

        if successful_projects:
            print_success(f"Successful Projects ({len(successful_projects)}):")
            for result in successful_projects:
                print_success(f" ✓ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")
            print_info("")

        if failed_projects:
            print_error(f"Failed Projects ({len(failed_projects)}):")
            for result in failed_projects:
                print_error(f" ✗ {result['name']}")
                test_info = []
                if result.get("passed", 0) > 0:
                    test_info.append(f"passed: {result.get('passed', 0)}")
                if result.get("failed", 0) > 0:
                    test_info.append(f"failed: {result.get('failed', 0)}")
                if result.get("errors", 0) > 0:
                    test_info.append(f"errors: {result.get('errors', 0)}")
                if result.get("skipped", 0) > 0:
                    test_info.append(f"skipped: {result.get('skipped', 0)}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")

        print_info("=" * 60)

        return fail_count == 0
    else:
        if not output_path:
            print_error("Output path is required when -All is not specified")
            return False

        print_step(5, f"Run Deployment Tests: {Path(output_path).name}")

        project_path_abs = Path(output_path).resolve()
        if not project_path_abs.exists():
            print_error(f"Generated project not found at: {project_path_abs}")
            return False

        project_name = project_path_abs.name

        result = _run_single_project_deploy_tests(
            project_path_abs, project_name, paths, timestamp,
        )
        if result is None:
            return True  # Skipped (TypeScript)

        # Print statistics
        test_info = []
        if result["passed"] > 0:
            test_info.append(f"passed: {result['passed']}")
        if result["failed"] > 0:
            test_info.append(f"failed: {result['failed']}")
        if result["errors"] > 0:
            test_info.append(f"errors: {result['errors']}")
        if result["skipped"] > 0:
            test_info.append(f"skipped: {result['skipped']}")
        if test_info:
            print_info("")
            print_info(f"Test Statistics: {', '.join(test_info)}")

        if result["success"]:
            print_success(f"[OK] Deployment tests passed for {project_name}")
            return True
        else:
            print_error(f"Deployment tests failed for {project_name}")
            return False


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
    description="Complete workflow runner for Datrix",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
    python scripts/library/test/run_complete.py <example_path> [output_path]  # output_path optional (from test-projects.json)
    python scripts/library/test/run_complete.py -All # Run all examples
    python scripts/library/test/run_complete.py -All --test-set tutorial-all # Run tutorial examples only
    python scripts/library/test/run_complete.py -Skip1 # Skip Step 1 (syntax checker)
    python scripts/library/test/run_complete.py -Skip3 -Skip4 -Skip5 # Skip Steps 3, 4, and 5
    python scripts/library/test/run_complete.py --skip-install -All  # Offline: no pip (set DATRIX_OFFLINE for subprocesses)
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
    help="Test set name (e.g. all, tutorial-all). Only used with -All."
    )
    parser.add_argument(
    "-Language",
    "--language",
    dest="language",
    default="python",
    choices=["python", "typescript"],
    help="Target language (default: python). Options: python, typescript"
    )
    parser.add_argument(
    "-Platform",
    "--platform",
    dest="platform",
    default="docker",
    choices=["docker", "kubernetes", "k8s"],
    help="Target platform (default: docker). Options: docker, kubernetes, k8s"
    )
    parser.add_argument(
    "-Hosting",
    "--hosting",
    dest="hosting",
    default=None,
    help="Hosting platform override (docker, kubernetes, aws, azure)"
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
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (DEBUG level instead of INFO)")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="No pip/network installs: set DATRIX_OFFLINE for subprocesses and pass -SkipInstall to generate.ps1",
    )

    args = parser.parse_args()

    if args.skip_install:
        os.environ["DATRIX_OFFLINE"] = "1"

    # Validate arguments: when not -All, example_path is required; output_path is derived from config if omitted
    if not args.All:
        if not args.example_path:
            parser.error("example_path is required when -All is not specified")
        if not args.output_path:
            try:
                args.output_path = str(get_default_output_path(
                    args.example_path,
                    language=args.language,
                    platform=args.platform,
                ))
            except (ValueError, FileNotFoundError) as e:
                parser.error(str(e))

    # Get all paths and run workflow (both -All and single-example modes)
    paths = get_paths()
    start_time = datetime.now()

    print_info("=" * 60)
    print_info("Datrix COMPLETE WORKFLOW")
    print_info("=" * 60)
    print_info(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.All:
        _mode_labels = {
            "tutorial-all": "TUTORIAL EXAMPLES",
            "domains": "DOMAINS EXAMPLES",
            "patterns": "PATTERNS EXAMPLES",
            "builtins": "BUILTINS EXAMPLES",
            "reference": "REFERENCE EXAMPLES",
        }
        mode_label = _mode_labels.get(args.test_set, "ALL EXAMPLES")
        print_info(f"Mode: {mode_label}")
    else:
        print_info("Mode: SINGLE EXAMPLE")
        print_info(f" Example: {args.example_path}")
        print_info(f" Output: {args.output_path}")
        print_info(f" Language: {args.language}")
        print_info(f" Platform: {args.platform}")

    # Show which steps will be skipped
    skip_info = []
    if args.Skip1:
        skip_info.append("Step 1 (Syntax Checker)")
    if args.Skip2:
        skip_info.append("Step 2 (Code Generation)")
    if args.Skip3:
        skip_info.append("Step 3 (Unit Tests)")
    if args.Skip4:
        skip_info.append("Step 4 (Spec Tests)")
    if args.Skip5:
        skip_info.append("Step 5 (Deployment Tests)")

    if skip_info:
        print_info("Skipped Steps: " + ", ".join(skip_info))
    if args.skip_install:
        print_info("Skip install: DATRIX_OFFLINE=1 (no pip during workflow)")

    print_info(f"Working Directory: {paths['datrix_root']}")
    print_info("=" * 60)

    # Track failures. Steps 3–4 run only if every non-skipped step among 1–2 succeeded.
    failed_steps = []

    try:
        step1_failed = False
        step2_failed = False

        if args.Skip1:
            print_step(1, "Syntax Checker")
            print_warning("Skipping Step 1 as requested (-Skip1 flag)")
        else:
            if not step1_syntax_checker(paths):
                print_warning("Step 1 failed; Steps 3 and 4 will be skipped.")
                failed_steps.append("Step 1: Syntax Checker")
                step1_failed = True

        if args.Skip2:
            print_step(2, "Code Generation")
            print_warning("Skipping Step 2 as requested (-Skip2 flag)")
        else:
            if not step2_generate(
                args.All,
                paths,
                args.example_path if not args.All else None,
                args.output_path if not args.All else None,
                args.language,
                args.platform,
                args.test_set if args.All else "all",
                args.hosting,
                skip_install=args.skip_install,
            ):
                print_warning("Step 2 failed; Steps 3 and 4 will be skipped.")
                failed_steps.append("Step 2: Code Generation")
                step2_failed = True

        early_steps_failed = step1_failed or step2_failed

        if args.Skip3:
            print_step(3, "Run Unit Tests for Generated Projects")
            print_warning("Skipping Step 3 as requested (-Skip3 flag)")
        elif early_steps_failed:
            print_step(3, "Run Unit Tests for Generated Projects")
            print_warning("Skipping Step 3 (not run; Step 1 or Step 2 failed).")
        else:
            if not step3_run_unit_tests(
                args.All,
                paths,
                args.output_path if not args.All else None,
                args.test_set if args.All else None,
                args.language,
                args.platform,
            ):
                print_warning("Step 3 failed. Continuing to Step 4...")
                failed_steps.append("Step 3: Unit Tests")

        if args.Skip4:
            print_step(4, "Run Deployment Tests (Spec + Integration) for Generated Projects")
            print_warning("Skipping Step 4 as requested (-Skip4 flag)")
        elif early_steps_failed:
            print_step(4, "Run Deployment Tests (Spec + Integration) for Generated Projects")
            print_warning("Skipping Step 4 (not run; Step 1 or Step 2 failed).")
        else:
            if not step4_run_deployment_tests(
                args.All,
                paths,
                args.output_path if not args.All else None,
                args.test_set if args.All else None,
                args.language,
                args.platform,
            ):
                print_warning("Step 4 failed. Continuing to final summary...")
                failed_steps.append("Step 4: Deployment Tests")

        # Step 5 has been merged into Step 4 (deployment tests now include spec + integration)
        if args.Skip5:
            print_warning("Note: Step 5 has been merged into Step 4. -Skip5 flag is deprecated.")

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
            return 1
        else:
            print_success("=" * 60)
            print_success("ALL STEPS COMPLETED SUCCESSFULLY!")
            print_success("=" * 60)
            print_info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print_info(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print_info(f"Duration: {duration}")
            print_success("=" * 60)
            return 0
    except KeyboardInterrupt:
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
        return 130


if __name__ == "__main__":
    sys.exit(main())
