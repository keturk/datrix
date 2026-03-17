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
import os
import re
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


def _get_step2_log_path(paths: dict[str, Path]) -> Path:
    """Return log file path for step 2 (same convention as generate.ps1)."""
    log_dir = paths["datrix_root"] / ".generated" / ".results"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"generate-results-{timestamp}.log"


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


def step1_syntax_checker(paths: dict[str, Path]) -> bool:
    """Step 1: Run syntax checker"""
    print_step(1, "Syntax Checker")

    # Use PowerShell wrapper which handles venv activation and tree-sitter installation
    script_path = paths["datrix_dir"] / "scripts" / "dev" / "syntax-checker.ps1"

    if not script_path.exists():
        print_error(f"Syntax checker not found at: {script_path}")
        return False

    # Determine PowerShell executable
    import platform
    import shutil

    pwsh_exe = None
    if shutil.which("pwsh"):
        pwsh_exe = "pwsh"
    elif platform.system() == "Windows" and shutil.which("powershell"):
        pwsh_exe = "powershell"
    else:
        print_error("PowerShell not found. Please install PowerShell (pwsh) or Windows PowerShell.")
        return False

    success, _ = run_command(
        [pwsh_exe, "-File", str(script_path)],
        cwd=paths["datrix_root"],
        description="Checking syntax of all .dtrx files in all repositories",
    )
    return success


def step2_generate(all_examples: bool, paths: dict[str, Path], example_path: Optional[str] = None, output_path: Optional[str] = None, language: str = "python", platform: str = "docker", test_set: str = "generate-all") -> bool:
    """Step 2: Generate examples. Writes output to a log file (same location as generate.ps1)."""
    log_path = _get_step2_log_path(paths)
    header = (
        "Generate Results Log\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "Step 2 (run_complete)\n"
        "=" * 80
        + "\n\n"
    )
    log_path.write_text(header, encoding="utf-8")
    print_info(f"Log file: {log_path}")

    if all_examples:
        print_step(2, "Generate Examples")
        # Run generate.py
        script_path = paths["datrix_dir"] / "scripts" / "library" / "dev" / "generate.py"

        if not script_path.exists():
            print_error(f"generate.py not found at: {script_path}")
            return False

        python_exe = get_venv_python()
        success, _ = run_command(
            [str(python_exe), str(script_path), "--language", language, "--platform", platform, "--test-set", test_set],
            cwd=paths["datrix_root"],
            description="Generating all examples",
            log_file=log_path,
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\nStep 2 completed: {'success' if success else 'failed'} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print_info(f"Log saved to: {log_path}")
        return success
    else:
        if not example_path or not output_path:
            print_error("Example path and output path are required when -All is not specified")
            return False

        print_step(2, f"Generate Example: {Path(example_path).name}")

        # Resolve paths to absolute paths first
        source_file = Path(example_path).resolve()
        output_dir = Path(output_path).resolve()

        if not source_file.exists():
            print_error(f"Example file not found at: {source_file}")
            return False

        # Use datrix CLI command - try to find datrix.exe first, then fall back to Python module
        # Language and platform are read from config files (system-config.yaml),
        # not from CLI flags. The --generators/--platforms flags were removed.
        python_exe = get_venv_python()
        import os
        import tempfile

        # Get venv path from python_exe
        venv_path = Path(python_exe).parent.parent

        # Try to find datrix command in venv
        if os.name == "nt":
            datrix_cmd_path = venv_path / "Scripts" / "datrix.exe"
        else:
            datrix_cmd_path = venv_path / "bin" / "datrix"

        # Build command arguments
        cmd_args = [
        "generate",
        "--source", str(source_file),
        "--output", str(output_dir),
        ]
 
        # Use datrix command if available, otherwise use python to call Typer app directly
        temp_script = None
        if datrix_cmd_path.exists():
            cmd = [str(datrix_cmd_path)] + cmd_args
        else:
            args_str = ", ".join([f'"{arg}"' for arg in cmd_args])
            script_content = f"""import sys
sys.argv = ["datrix", {args_str}]
from datrix_cli.main import app
app()
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                temp_script = f.name
            cmd = [str(python_exe), temp_script]

        try:
            success, _ = run_command(
                cmd,
                cwd=paths["datrix_root"],
                description=f"Generating example: {source_file.name}",
                log_file=log_path,
            )
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\nStep 2 completed: {'success' if success else 'failed'} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            print_info(f"Log saved to: {log_path}")
            return success
        finally:
            if temp_script and Path(temp_script).exists():
                try:
                    os.unlink(temp_script)
                except Exception:
                    pass


def parse_test_statistics(output: str) -> dict:
    """Parse test statistics from run_tests.py or deploy_test.py output.

    Supports two formats:
    - run_tests.py summary format: "Total Passed: 35"
    - pytest summary line format: "===== 35 passed, 1 failed in 8.48s ====="
    """
    stats = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }

    if not output:
        return stats

    # Try run_tests.py "Total Passed: X" format first
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

    # Get container names: docker compose -f <file> ps -a --format "{{.Name}}"
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "ps", "-a", "--format", "{{.Name}}"],
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

    try:
        subprocess.run(
            [
                "docker", "compose",
                "-f", str(compose_file),
                "down", "-v", "--rmi", "local", "--remove-orphans",
            ],
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
                if result["passed"] > 0:
                    test_info.append(f"passed: {result['passed']}")
                if result["failed"] > 0:
                    test_info.append(f"failed: {result['failed']}")
                if result["errors"] > 0:
                    test_info.append(f"errors: {result['errors']}")
                if result["skipped"] > 0:
                    test_info.append(f"skipped: {result['skipped']}")
                if test_info:
                    f.write(f"   Tests: {', '.join(test_info)}\n")
            f.write("\n")

        if failed_projects:
            f.write(f"Failed Projects ({len(failed_projects)}):\n")
            for result in failed_projects:
                f.write(f" ✗ {result['name']}\n")
                # Show test counts
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
                    f.write(f"   Tests: {', '.join(test_info)}\n")
            f.write("\n")
 
        f.write("=" * 60 + "\n")
 
        return log_path


def _run_single_project_unit_tests(project: Path, generated_base: Path, parallel: bool = False) -> dict:
    """
    Helper function to run unit tests for a single project.
    Returns a dictionary with project result information.

    Args:
        project: Path to the project directory
        generated_base: Base path for generated projects
        parallel: If True, suppress real-time output (for parallel execution)
    """
    project_name = project.relative_to(generated_base)

    run_tests_script = project / "tests" / "run_tests.py"
    if run_tests_script.exists():
        python_exe = get_venv_python()
        cmd = [str(python_exe), str(run_tests_script), "--unit", "--parallel"]
        success, output = run_command(
            cmd,
            cwd=project,
            description=f"Unit tests for {project_name}" if not parallel else "",
            capture_output=True,
        )
        stats = parse_test_statistics(output) if output else {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
        project_result = {
            "name": str(project_name),
            "success": success,
            "passed": stats["passed"],
            "failed": stats["failed"],
            "errors": stats["errors"],
            "skipped": stats["skipped"],
            "output": output if parallel else None,
        }
        return project_result
    else:
        # No run_tests.py: treat as failure so step reports failure
        return {
            "name": str(project_name),
            "success": False,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "output": None,
        }


def step4_run_unit_tests(all_examples: bool, paths: dict[str, Path], output_path: Optional[str] = None, test_set: Optional[str] = None, language: str = "python", platform: str = "docker") -> bool:
    """Step 4: Run unit tests for generated projects using run_tests.py"""
    if all_examples:
        print_step(4, "Run Unit Tests for Generated Projects")
        generated_base = paths["datrix_root"] / ".generated"
        # Find generated projects: by test set or by scanning .generated
        projects = []
        if test_set:
            proj_list = get_test_projects(test_set=test_set, language=language, platform=platform)
            projects = [Path(p["output"]) for p in proj_list if Path(p["output"]).exists()]
        elif generated_base.exists():
            for item in generated_base.rglob("run_tests.py"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    projects.append(project_dir)

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

                    run_tests_script = project / "tests" / "run_tests.py"
                    if not run_tests_script.exists():
                        print_warning(f" [SKIP] No run_tests.py found for {project_name}")

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
        total_passed_tests = sum(r["passed"] for r in project_results)
        total_failed_tests = sum(r["failed"] for r in project_results)
        total_error_tests = sum(r["errors"] for r in project_results)
        total_skipped_tests = sum(r["skipped"] for r in project_results)
 
        # Save summary to log file
        log_path = save_test_summary_log(
        step_num=4,
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
        print_info("STEP 4 SUMMARY: Unit Tests for Generated Projects")
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
                if result["passed"] > 0:
                    test_info.append(f"passed: {result['passed']}")
                if result["failed"] > 0:
                    test_info.append(f"failed: {result['failed']}")
                if result["errors"] > 0:
                    test_info.append(f"errors: {result['errors']}")
                if result["skipped"] > 0:
                    test_info.append(f"skipped: {result['skipped']}")
                if test_info:
                    print_info(f"   Tests: {', '.join(test_info)}")
            print_info("")

        if failed_projects:
            print_error(f"Failed Projects ({len(failed_projects)}):")
            for result in failed_projects:
                print_error(f" ✗ {result['name']}")
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
                    print_info(f"   Tests: {', '.join(test_info)}")

        print_info("=" * 60)
        print_info(f"Summary log saved to: {log_path.relative_to(paths['datrix_root'])}")

        return fail_count == 0
    else:
        if not output_path:
            print_error("Output path is required when -All is not specified")
            return False

        print_step(4, f"Run Unit Tests: {Path(output_path).name}")

        # Resolve path to absolute first
        project_path_abs = Path(output_path).resolve()

        if not project_path_abs.exists():
            print_error(f"Generated project not found at: {project_path_abs}")
            return False

        project_name = project_path_abs.name

        run_tests_script = project_path_abs / "tests" / "run_tests.py"
        if run_tests_script.exists():
            print_info(f"Running unit tests for {project_name}...")
            python_exe = get_venv_python()
            cmd = [str(python_exe), str(run_tests_script), "--unit", "--parallel"]
            success, output = run_command(
                cmd,
                cwd=project_path_abs,
                description=f"Unit tests for {project_name}",
                capture_output=True,
            )
 
            if output:
                stats = parse_test_statistics(output)
                print_info("")
                print_info("Test Statistics:")
                print_info(f" Passed: {stats['passed']}")
                if stats['failed'] > 0:
                    print_error(f" Failed: {stats['failed']}")
                if stats['errors'] > 0:
                    print_error(f" Errors: {stats['errors']}")
                if stats['skipped'] > 0:
                    print_info(f" Skipped: {stats['skipped']}")

            if success:
                print_success(f"[OK] Unit tests passed for {project_name}")
                return True
            else:
                print_error(f"Unit tests failed for {project_name}")
                return False
        else:
            print_warning(f"No run_tests.py found for {project_name}")
            return True


def step5_run_deployment_tests(all_examples: bool, paths: dict[str, Path], output_path: Optional[str] = None, test_set: Optional[str] = None, language: str = "python", platform: str = "docker") -> bool:
    """Step 5: Run deployment/integration tests for generated projects using deploy_test.py"""
    if all_examples:
        print_step(5, "Run Deployment Tests for Generated Projects")
        generated_base = paths["datrix_root"] / ".generated"
        # Find generated projects: by test set or by scanning .generated
        projects = []
        if test_set:
            proj_list = get_test_projects(test_set=test_set, language=language, platform=platform)
            projects = [Path(p["output"]) for p in proj_list if Path(p["output"]).exists()]
        elif generated_base.exists():
            for item in generated_base.rglob("deploy_test.py"):
                if item.parent.name == "tests":
                    project_dir = item.parent.parent
                    projects.append(project_dir)

        if not projects:
            print_warning("No generated projects found to test")
            return True

        print_info(f"Found {len(projects)} generated projects to test")

        step5_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        success_count = 0
        fail_count = 0
        project_results = []  # Store per-project statistics

        for project in projects:
            project_name = project.relative_to(generated_base)

            # Create per-project timestamped deploy-test folder
            deploy_test_dir = project / ".test_results" / f"deploy-test-{step5_timestamp}"
            deploy_test_dir.mkdir(parents=True, exist_ok=True)
            (deploy_test_dir / "docker-logs").mkdir(parents=True, exist_ok=True)

            print()
            print_info(f"Running deployment tests for: {project_name}")
            print("-" * 60)

            deploy_test_script = project / "tests" / "deploy_test.py"
            if deploy_test_script.exists():
                python_exe = get_venv_python()
                try:
                    success, output = run_command(
                        [str(python_exe), str(deploy_test_script), "--results-dir", str(deploy_test_dir)],
                        cwd=project,
                        description=f"Deployment tests for {project_name}",
                        capture_output=True,
                    )
                finally:
                    # deploy_test.py saves docker logs before teardown via --results-dir.
                    # Fallback: try saving logs here in case deploy_test.py was killed.
                    _save_docker_logs_for_project(project, deploy_test_dir)
                    _ensure_docker_cleanup(project)

                stats = parse_test_statistics(output) if output else {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
                project_result = {
                    "name": str(project_name),
                    "success": success,
                    "passed": stats["passed"],
                    "failed": stats["failed"],
                    "errors": stats["errors"],
                    "skipped": stats["skipped"],
                }
                project_results.append(project_result)

                # Persist full stdout/stderr for debugging (failure messages, pytest output)
                if output is not None:
                    output_log = deploy_test_dir / "deploy-test-output.log"
                    output_log.write_text(output, encoding="utf-8")

                if success:
                    print_success(f" [OK] Deployment tests passed for {project_name}")
                    success_count += 1
                else:
                    print_error(f" [FAILED] Deployment tests failed for {project_name}")
                    fail_count += 1

                # Save per-project summary
                save_test_summary_log(
                    step_num=5,
                    step_name=f"Deployment Tests for {project_name}",
                    paths=paths,
                    project_results=[project_result],
                    total_projects=1,
                    success_count=1 if success else 0,
                    fail_count=0 if success else 1,
                    total_passed_tests=stats["passed"],
                    total_failed_tests=stats["failed"],
                    total_error_tests=stats["errors"],
                    total_skipped_tests=stats["skipped"],
                    step5_output_dir=deploy_test_dir,
                )
            else:
                print_warning(f" [SKIP] No deploy_test.py found for {project_name}")
                project_results.append({
                    "name": str(project_name),
                    "success": False,
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                })
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

        # Separate successful and failed projects
        successful_projects = [r for r in project_results if r["success"]]
        failed_projects = [r for r in project_results if not r["success"]]

        if successful_projects:
            print_success(f"Successful Projects ({len(successful_projects)}):")
            for result in successful_projects:
                print_success(f" ✓ {result['name']}")
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
                    print_info(f"   Tests: {', '.join(test_info)}")
            print_info("")

        if failed_projects:
            print_error(f"Failed Projects ({len(failed_projects)}):")
            for result in failed_projects:
                print_error(f" ✗ {result['name']}")
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
                    print_info(f"   Tests: {', '.join(test_info)}")

        print_info("=" * 60)

        return fail_count == 0
    else:
        if not output_path:
            print_error("Output path is required when -All is not specified")
            return False

        print_step(5, f"Run Deployment Tests: {Path(output_path).name}")

        # Resolve path to absolute first
        project_path_abs = Path(output_path).resolve()

        if not project_path_abs.exists():
            print_error(f"Generated project not found at: {project_path_abs}")
            return False

        project_name = project_path_abs.name

        step5_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        deploy_test_dir = project_path_abs / ".test_results" / f"deploy-test-{step5_timestamp}"
        deploy_test_dir.mkdir(parents=True, exist_ok=True)
        (deploy_test_dir / "docker-logs").mkdir(parents=True, exist_ok=True)

        # Run deployment tests (deploy_test.py)
        deploy_test_script = project_path_abs / "tests" / "deploy_test.py"
        if deploy_test_script.exists():
            print_info(f"Running deployment tests for {project_name}...")
            python_exe = get_venv_python()
            try:
                success, output = run_command(
                    [str(python_exe), str(deploy_test_script), "--results-dir", str(deploy_test_dir)],
                    cwd=project_path_abs,
                    description=f"Deployment tests for {project_name}",
                    capture_output=True,
                )
            finally:
                # deploy_test.py saves docker logs before teardown via --results-dir.
                # Fallback: try saving logs here in case deploy_test.py was killed.
                _save_docker_logs_for_project(project_path_abs, deploy_test_dir, project_slug=None)
                _ensure_docker_cleanup(project_path_abs)

            stats = parse_test_statistics(output) if output else {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
            project_result = {
                "name": project_name,
                "success": success,
                "passed": stats["passed"],
                "failed": stats["failed"],
                "errors": stats["errors"],
                "skipped": stats["skipped"],
            }
            if output is not None:
                (deploy_test_dir / "deploy-test-output.log").write_text(output, encoding="utf-8")
            log_path = save_test_summary_log(
                step_num=5,
                step_name="Deployment Tests for Generated Projects",
                paths=paths,
                project_results=[project_result],
                total_projects=1,
                success_count=1 if success else 0,
                fail_count=0 if success else 1,
                total_passed_tests=stats["passed"],
                total_failed_tests=stats["failed"],
                total_error_tests=stats["errors"],
                total_skipped_tests=stats["skipped"],
                step5_output_dir=deploy_test_dir,
            )
            print_info(f"Summary log saved to: {log_path.relative_to(paths['datrix_root'])}")
            if output:
                print_info("")
                print_info("Test Statistics:")
                print_info(f" Passed: {stats['passed']}")
                if stats['failed'] > 0:
                    print_error(f" Failed: {stats['failed']}")
                if stats['errors'] > 0:
                    print_error(f" Errors: {stats['errors']}")
                if stats['skipped'] > 0:
                    print_info(f" Skipped: {stats['skipped']}")
            if success:
                print_success(f"[OK] Deployment tests passed for {project_name}")
                return True
            else:
                print_error(f"Deployment tests failed for {project_name}")
                return False
        else:
            print_warning(f"No deploy_test.py found for {project_name}")
            return True


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
    python scripts/library/test/run_complete.py -Skip4 -Skip5 # Skip Steps 4 and 5
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
    default="generate-all",
    help="Test set name (e.g. generate-all, tutorial-all). Only used with -All."
    )
    parser.add_argument(
    "-Language",
    "--language",
    dest="language",
    default="python",
    help="Target language (default: python). Options: python, typescript"
    )
    parser.add_argument(
    "-Platform",
    "--platform",
    dest="platform",
    default="docker",
    help="Target platform (default: docker)"
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
    "-Skip4",
    action="store_true",
    help="Skip Step 4 (unit tests for generated projects)"
    )
    parser.add_argument(
    "-Skip5",
    action="store_true",
    help="Skip Step 5 (deployment tests for generated projects)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (DEBUG level instead of INFO)")

    args = parser.parse_args()

    # Validate arguments: when not -All, example_path is required; output_path is derived from config if omitted
    if not args.All:
        if not args.example_path:
            parser.error("example_path is required when -All is not specified")
        if not args.output_path:
            try:
                args.output_path = str(get_default_output_path(args.example_path))
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
    if args.Skip4:
        skip_info.append("Step 4 (Unit Tests)")
    if args.Skip5:
        skip_info.append("Step 5 (Deployment Tests)")

    if skip_info:
        print_info("Skipped Steps: " + ", ".join(skip_info))

    print_info(f"Working Directory: {paths['datrix_root']}")
    print_info("=" * 60)

    # Track failures but continue through all steps
    failed_steps = []

    try:
        if args.Skip1:
            print_step(1, "Syntax Checker")
            print_warning("Skipping Step 1 as requested (-Skip1 flag)")
        else:
            if not step1_syntax_checker(paths):
                print_warning("Step 1 failed. Continuing to next step...")
                failed_steps.append("Step 1: Syntax Checker")

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
                args.test_set if args.All else "generate-all",
            ):
                print_warning("Step 2 failed. Continuing to next step...")
                failed_steps.append("Step 2: Code Generation")

        if args.Skip4:
            print_step(4, "Run Unit Tests for Generated Projects")
            print_warning("Skipping Step 4 as requested (-Skip4 flag)")
        else:
            if not step4_run_unit_tests(
                args.All,
                paths,
                args.output_path if not args.All else None,
                args.test_set if args.All else None,
                args.language,
                args.platform,
            ):
                print_warning("Step 4 failed. Continuing to next step...")
                failed_steps.append("Step 4: Unit Tests")

        if args.Skip5:
            print_step(5, "Run Deployment Tests for Generated Projects")
            print_warning("Skipping Step 5 as requested (-Skip5 flag)")
        else:
            if not step5_run_deployment_tests(
                args.All,
                paths,
                args.output_path if not args.All else None,
                args.test_set if args.All else None,
                args.language,
                args.platform,
            ):
                print_warning("Step 5 failed. Continuing to final summary...")
                failed_steps.append("Step 5: Deployment Tests")

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
