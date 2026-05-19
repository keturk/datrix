#!/usr/bin/env python3
r"""
Generate all example projects.

Usage:
    python scripts/library/dev/generate.py [--language python] [--platform docker]
    [--output-base .generated] [--test-set all]

    Or use the PowerShell wrapper:
        .\scripts\dev\generate.ps1 -All [-Language <lang>] [-Platform <platform>] [-TestSet <set>]
"""

import argparse
import atexit
import io
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
# library/dev -> library (where shared/ is located)
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root, get_venv_python
from shared.logging_utils import LogConfig, TeeLogger, ColorCodes, colorize, strip_ansi
from shared.test_projects import get_test_projects, get_default_output_path

# Add datrix-common to path so we can use DATRIX_FILE_EXTENSION
_datrix_root = get_datrix_root()
_datrix_common_src = _datrix_root / "datrix-common" / "src"
if _datrix_common_src.exists() and str(_datrix_common_src) not in sys.path:
    sys.path.insert(0, str(_datrix_common_src))
from datrix_common import DATRIX_FILE_EXTENSION

_GENERATE_LOG_FILE_ENV = "DATRIX_GENERATE_LOG_FILE"


def _append_datrix_generate_cli_overrides(cmd_args: list[str], args: argparse.Namespace) -> None:
    """Append --language flag for datrix generate from script args."""
    if args.language != "python":
        cmd_args.extend(["--language", args.language])
    if getattr(args, "profile", None) is not None:
        cmd_args.extend(["--profile", args.profile])


def _append_log_only_lines(lines: list[str]) -> None:
    """Append lines to the wrapper log file without emitting console output."""
    log_file = os.environ.get(_GENERATE_LOG_FILE_ENV)
    if not log_file:
        return

    log_path = Path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(f"{line}\n")
    except Exception:
        # Logging must never break generation.
        pass


# Pattern to detect spinner/progress lines that should be filtered from logs
_SPINNER_PATTERN = re.compile(r'^[\s\[\]0-9;?]*[2K|25[lh]]|^[\\|/\-]?\s*(Generating|Loading|Processing)')
_PROGRESS_LINE_PATTERN = re.compile(r'^\[?[2K\x1b]|^[\\|/\-⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s')


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
    print("Cleaning up subprocesses...", file=sys.stderr)
    cleanup_processes()
    sys.exit(1)


# Register cleanup handler and signal handlers
atexit.register(cleanup_processes)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)




def generate_single_project(
    project: dict,
    project_index: int,
    total_projects: int,
    args,
    datrix_root: Path,
    python_exe: str,
    verbose: bool = True,
) -> Tuple[bool, str, Path, Path, List[str], List[str], List[str]]:
    """
    Generate a single project.

    Returns:
        Tuple of (success, project_name, project_path, output_path, warnings, errors, full_output)

    Args:
        verbose: If True, print generation output in real-time. If False, only capture for logs.

    Returns:
        Tuple of (success: bool, project_name: str, project_path: Path, output_path: Path, warnings: list[str], errors: list[str])
    """
    project_name = project["name"]
    project_path = None
    output_path = None

    try:
        # Ensure path is absolute
        project_path = Path(project["path"]).resolve()

        # Calculate output path
        # Use custom output base if provided, otherwise use default from project config
        if args.output_base and args.output_base != ".generated":
            output_base = Path(args.output_base)
            # Build relative path from examples directory
            examples_dir = datrix_root / "datrix" / "examples"
            if examples_dir in project_path.parents:
                rel_path = project_path.relative_to(examples_dir)
                from shared.test_projects import build_output_path
                rel_path_str = f"examples/{rel_path}"
                # Use runtime and provider for output path (defaults: docker-compose, local)
                runtime_segment = args.runtime or "docker-compose"
                provider_segment = args.provider or "local"
                output_relative = build_output_path(rel_path_str, args.language, f"{runtime_segment}/{provider_segment}")
                output_path = datrix_root / output_base / output_relative
            else:
                # Fallback: use project name under language/platform
                # Use runtime and provider for output path (defaults: docker-compose, local)
                runtime_segment = args.runtime or "docker-compose"
                provider_segment = args.provider or "local"
                output_name = f"{args.language}/{runtime_segment}/{provider_segment}/{project_name}"
                output_path = datrix_root / output_base / output_name
        else:
            # Use default from project config if available (from get_test_projects)
            if "output" in project and project["output"]:
                output_path = Path(project["output"])
            else:
                # Fallback: build from source path
                from shared.test_projects import build_output_path
                examples_dir = datrix_root / "datrix" / "examples"
                if examples_dir in project_path.parents:
                    rel_path = project_path.relative_to(examples_dir)
                    rel_path_str = f"examples/{rel_path}"
                    # Use runtime and provider for output path (defaults: docker-compose, local)
                runtime_segment = args.runtime or "docker-compose"
                provider_segment = args.provider or "local"
                output_relative = build_output_path(rel_path_str, args.language, f"{runtime_segment}/{provider_segment}")
                    output_path = datrix_root / ".generated" / output_relative
                else:
                    # Use runtime and provider for output path (defaults: docker-compose, local)
                runtime_segment = args.runtime or "docker-compose"
                provider_segment = args.provider or "local"
                output_name = f"{args.language}/{runtime_segment}/{provider_segment}/{project_name}"
                    output_path = datrix_root / ".generated" / output_name

        # Build datrix generate command. Language override can be passed via --language.
        # Runtime and provider are used only for output path derivation and are NOT
        # forwarded to datrix generate (deployment is read from config).
        import os
        import tempfile

        # Get venv path from python_exe
        venv_path = Path(python_exe).parent.parent

        runtime_segment = args.runtime or "docker-compose"
        provider_segment = args.provider or "local"
        _append_log_only_lines(
            [
                f"Generating project: {project_name}",
                f" Source: {project_path}",
                f" Output: {output_path}",
                f" Language: {args.language}",
                f" Runtime (output path): {runtime_segment}",
                f" Provider (output path): {provider_segment}",
                "",
            ]
        )

        # Try to find datrix command in venv
        if os.name == "nt":
            datrix_cmd_path = venv_path / "Scripts" / "datrix.exe"
        else:
            datrix_cmd_path = venv_path / "bin" / "datrix"

        # Build command arguments
        # The command structure is: datrix generate [OPTIONS]
        # Language and platform come from the project's config/system-config.yaml
        cmd_args = [
        "generate",
        "--source",
        str(project_path),
        "--output",
        str(output_path),
        ]
        _append_datrix_generate_cli_overrides(cmd_args, args)

        # Add verbose flag if debug is enabled
        if hasattr(args, 'debug') and args.debug:
            cmd_args.append("--verbose")
 
        # Use datrix command if available, otherwise use python to call Typer app directly
        temp_script = None
        if datrix_cmd_path.exists():
            cmd = [str(datrix_cmd_path)] + cmd_args
        else:
            # Fallback: use python to run the Typer app by importing and calling it
            # Create a temporary script file that sets up sys.argv and calls the app
            args_str = ", ".join([repr(arg) for arg in cmd_args])
            script_content = f"""import sys
sys.argv = ["datrix", {args_str}]
from datrix_cli.main import app
app()
"""
            # Write to temp file and execute it
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                temp_script = f.name
            cmd = [python_exe, temp_script]

        # Run command
        process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(datrix_root),
        encoding="utf-8",
        errors="replace",
        bufsize=1, # Line buffered
        )

        # Register process for cleanup
        register_process(process)

        try:
            # Read output line by line and print immediately
            output_lines = []
            warnings = []
            errors = []

            if process.stdout:
                for line in process.stdout:
                    # Strip ANSI escape sequences for clean logging
                    plain_line = strip_ansi(line).rstrip()
                    # Print all output in real-time (only in verbose mode)
                    if verbose:
                        print(plain_line, flush=True)
                    output_lines.append(plain_line)
                    # Capture warning and error lines for the summary.
                    # Warnings match:
                    #   - "Warning: ..." (CLI-style)
                    #   - "WARNING logger.name ..." (Python logging default format)
                    # Errors match:
                    #   - "Error: ..." (CLI-style)
                    #   - "ERROR logger.name ..." (Python logging default format)
                    stripped = plain_line.lstrip()
                    if stripped.startswith("Warning:") or stripped.startswith("WARNING "):
                        warnings.append(plain_line.strip())
                    elif stripped.startswith("Error:") or stripped.startswith("ERROR "):
                        errors.append(plain_line.strip())

            # Wait for process to complete
            exit_code = process.wait()

            # Ensure all output is flushed
            sys.stdout.flush()
            sys.stderr.flush()

            # If the subprocess itself failed, capture error-like lines BEFORE
            # promoting warnings/errors to failures, so we don't pollute the
            # errors list with arbitrary trailing output from warning-only runs.
            subprocess_failed = exit_code != 0

            # Any warning or error emitted during generation is treated as a
            # hard failure: they indicate silent fallbacks, incomplete mappings,
            # or contract violations that must not be allowed to ship.
            if (warnings or errors) and exit_code == 0:
                exit_code = 1

            # If the subprocess failed and we didn't already capture specific
            # ERROR lines from the output, extract error-like lines to avoid
            # dumping the full log. Warning/error-only failures keep their
            # already-captured lists (reported in the summary).
            if subprocess_failed and not errors:
                meaningful = [line for line in output_lines if line.strip()]
                if meaningful:
                    error_indicators = (
                        "[ERROR", "Error:", "Traceback", "Exception", "Error ",
                        "RuffError", "GenerationError", "PipelineError", " File ",
                        "Suggestions:",
                    )
                    error_lines = [
                        line for line in meaningful
                        if any(ind in line for ind in error_indicators)
                    ]
                    if not error_lines:
                        error_lines = meaningful[-25:]
                    errors = error_lines
                else:
                    errors = [f"Generation failed with exit code {exit_code}"]

            return (exit_code == 0, project_name, project_path, output_path, warnings, errors, output_lines)
        finally:
            # Unregister process after completion
            unregister_process(process)
            # Clean up temp script if we created one
            if temp_script and Path(temp_script).exists():
                try:
                    Path(temp_script).unlink()
                except Exception:
                    pass  # Ignore cleanup errors
    except Exception as e:
        error_msg = f"Error generating {project_name}: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return (False, project_name, project_path, output_path, [], [error_msg], [])


def _print_generation_summary(
    projects: list,
    success_count: int,
    fail_count: int,
    failed_projects: List[str],
    project_warnings: dict,
    project_errors: dict,
    logger: Optional[TeeLogger],
) -> int:
    """
    Print the generation summary. Failed projects, Warnings, and Errors sections
    are printed first; the compact summary (counts) is printed last so it is
    visible at the end of the log without scrolling.
    Called always at the end, including on interrupt or exception.
    Returns the exit code (0 = success, 1 = failures).
    """
    total_warnings = sum(len(w) for w in project_warnings.values())
    total_errors = sum(len(e) for e in project_errors.values())

    # 1. Warnings section
    if project_warnings:
        if logger:
            logger.write_warning("Warnings:")
            for pname, warnings in sorted(project_warnings.items()):
                logger.write_warning(f" {pname}:")
                for warning in warnings:
                    logger.write_warning(f" - {warning}")
            logger.write("")
        else:
            print(colorize("Warnings:", ColorCodes.YELLOW))
            for pname, warnings in sorted(project_warnings.items()):
                print(colorize(f" {pname}:", ColorCodes.YELLOW))
                for warning in warnings:
                    print(colorize(f" - {warning}", ColorCodes.YELLOW))
            print()

    # 2. Errors section (detail)
    if project_errors:
        if logger:
            logger.write_error("Errors:")
            for pname, errors in sorted(project_errors.items()):
                logger.write_error(f" {pname}:")
                for error in errors:
                    logger.write_error(f" - {error}")
            logger.write("")
        else:
            print(colorize("Errors:", ColorCodes.RED))
            for pname, errors in sorted(project_errors.items()):
                print(colorize(f" {pname}:", ColorCodes.RED))
                for error in errors:
                    print(colorize(f" - {error}", ColorCodes.RED))
            print()

    # 3. Generation Summary (counts) at the very end so it is visible without scrolling
    # Always show summary, even in quiet mode
    summary_banner = "########## Generation Summary ##########"
    if logger:
        logger.write_console(summary_banner)
        logger.write_console("")
        logger.write_console(f" Total projects: {len(projects)}")
        if success_count > 0:
            logger.write_console(colorize(f" Successful: {success_count}", ColorCodes.GREEN))
        else:
            logger.write_console(f" Successful: {success_count}")
        if fail_count > 0:
            logger.write_console(colorize(f" Failed: {fail_count}", ColorCodes.RED))
        else:
            logger.write_console(f" Failed: {fail_count}")
        if total_warnings > 0:
            logger.write_console(colorize(f" Warnings: {total_warnings}", ColorCodes.YELLOW))
        else:
            logger.write_console(f" Warnings: {total_warnings}")
        if total_errors > 0:
            logger.write_console(colorize(f" Errors: {total_errors}", ColorCodes.RED))
        else:
            logger.write_console(f" Errors: {total_errors}")
        logger.write_console("")
    else:
        print(colorize(summary_banner, ColorCodes.CYAN), flush=True)
        print("")
        print(f" Total projects: {len(projects)}")
        print(colorize(f" Successful: {success_count}", ColorCodes.GREEN if success_count > 0 else ""))
        if fail_count > 0:
            print(colorize(f" Failed: {fail_count}", ColorCodes.RED))
        else:
            print(f" Failed: {fail_count}")
        if total_warnings > 0:
            print(colorize(f" Warnings: {total_warnings}", ColorCodes.YELLOW))
        else:
            print(f" Warnings: {total_warnings}")
        if total_errors > 0:
            print(colorize(f" Errors: {total_errors}", ColorCodes.RED))
        else:
            print(f" Errors: {total_errors}")
        print()

    # 4. Failed projects list (below summary so counts are first at end of log)
    # Always show failed projects, even in quiet mode
    if fail_count > 0:
        if logger:
            logger.write_console(colorize("Failed projects:", ColorCodes.RED))
            for failed_project in failed_projects:
                logger.write_console(colorize(f" - {failed_project}", ColorCodes.RED))
            logger.write_console("")
        else:
            print(colorize("Failed projects:", ColorCodes.RED))
            for failed_project in failed_projects:
                print(colorize(f" - {failed_project}", ColorCodes.RED))
            print()

    if fail_count > 0 or total_errors > 0 or total_warnings > 0:
        if total_warnings > 0 and fail_count == 0 and total_errors == 0:
            # Warnings-only failure: make the failure reason explicit.
            msg = (
                "Generation failed: warnings are treated as errors. "
                "Fix the warnings above (they indicate silent fallbacks or "
                "incomplete mappings in the generators) and re-run."
            )
            if logger:
                logger.write_console(colorize(msg, ColorCodes.RED))
            else:
                print(colorize(msg, ColorCodes.RED))
        return 1
    if logger:
        logger.write_console(colorize("All projects generated successfully!", ColorCodes.GREEN))
    else:
        print(colorize("All projects generated successfully!", ColorCodes.GREEN))
    return 0


def main():
    """Main entry point for generation script."""
    parser = argparse.ArgumentParser(
    description="Generate Datrix projects from source files",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    )
 
    # Single project mode
    parser.add_argument("--source", type=str, help="Path to source .dtrx file")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory. When omitted, derived as .generated/<language>/<platform>/… "
        "from the source path using --language and --platform (see test-projects path rules).",
    )
 
    # Batch mode
    parser.add_argument("--language", type=str.lower, default="python", choices=["python", "typescript"], help="Target language")
    parser.add_argument("--runtime", type=str.lower, default=None, choices=["docker-compose", "kubernetes", "azure-container-apps", "azure-app-service", "ecs-fargate", "app-runner"], help="Optional output path runtime segment; generation reads runtime from resolved config")
    parser.add_argument("--provider", type=str.lower, default=None, choices=["local", "existing", "aws", "azure"], help="Optional output path provider segment; generation reads provider from resolved config")
    parser.add_argument("--output-base", type=str, default=".generated", help="Output base directory")
    parser.add_argument("--test-set", type=str, default="all", help="Test set to use (e.g. all, foundation, non-foundation, features, domains)")
    parser.add_argument("--profile", type=str, default=None, help="Config profile for YAML resolution (e.g., test, development, production)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
 
    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    try:
        python_exe = str(get_venv_python())
        if not Path(python_exe).exists():
            python_exe = sys.executable
    except Exception:
        python_exe = sys.executable

    create_log_file = sys.stdout.isatty() and not os.environ.get("DATRIX_DISABLE_LOG", "")
    log_file_path = None
    logger = None

    # Set up logging if enabled (standalone mode, not called from PS1 wrapper)
    if create_log_file:
        log_dir = datrix_root / ".generated" / ".results"
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file_path = log_dir / f"generate-results-{timestamp}.log"

        log_config = LogConfig(
            log_dir=str(log_dir),
            prefix="generate-results",
            project_name="datrix-generate",
            save_to_file=True,
            quiet_mode=not args.verbose,
        )
        logger = TeeLogger(log_config, datrix_root)
        logger.__enter__()

        logger.write("Generate Results Log")
        logger.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.write("=" * 80)
        logger.write("")
        logger.write(f"Log file: {log_file_path}")
        logger.write("")

    # Run generation (always, regardless of logging mode)
    try:
        if args.source:
            source_path = Path(args.source).resolve()
            if not args.output:
                try:
                    runtime_seg = args.runtime or "docker-compose"
                    provider_seg = args.provider or "local"
                    args.output = str(
                        get_default_output_path(
                            str(source_path),
                            language=args.language,
                            platform=f"{runtime_seg}/{provider_seg}",
                        )
                    )
                except (ValueError, FileNotFoundError):
                    error_msg = (
                        f"Cannot derive output path for: {source_path}\n"
                        f"  Output path auto-derivation only works for projects under examples/.\n"
                        f"  For external projects, provide --output explicitly.\n"
                        f"  Example: generate.ps1 <source> <output-dir> -L {args.language}"
                    )
                    if logger:
                        logger.write_error(error_msg)
                    else:
                        print(f"ERROR: {error_msg}")
                    return 1
            output_path = Path(args.output).resolve()
            if not source_path.exists():
                error_msg = f"Source file not found: {source_path}"
                if logger:
                    logger.write_error(error_msg)
                else:
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                return 1
            # If source is a project directory, use system.dtrx inside it.
            if source_path.is_dir():
                system_dtrx = source_path / "system.dtrx"
                if system_dtrx.exists():
                    source_path = system_dtrx
                else:
                    error_msg = f"Source path is a directory and no system.dtrx found: {source_path}"
                    if logger:
                        logger.write_error(error_msg)
                    else:
                        print(f"ERROR: {error_msg}", file=sys.stderr)
                    return 1
            if source_path.name == "system.dtrx":
                project_name = source_path.parent.name
            elif source_path.suffix == DATRIX_FILE_EXTENSION:
                project_name = source_path.stem
            else:
                project_name = source_path.parent.name
            projects = [{
                "name": project_name,
                "path": str(source_path),
                "output": str(output_path),
                "description": f"Single project: {project_name}",
            }]
            runtime_display = args.runtime or "config/default"
            provider_display = args.provider or "config/default"
            if logger:
                logger.write(f"Generating single project: {project_name}")
                logger.write(f" Source: {source_path}")
                logger.write(f" Output: {output_path}")
                logger.write(f" Language: {args.language}")
                logger.write(f" Runtime: {runtime_display}")
                logger.write(f" Provider: {provider_display}")
                logger.write("")
            else:
                # Always print source/output so PS1's Write-TeeOutput captures them in the log.
                # These brief context lines are appropriate to show on the console in all modes.
                print(f"Generating single project: {project_name}", flush=True)
                print(f" Source: {source_path}", flush=True)
                print(f" Output: {output_path}", flush=True)
                print(f" Language: {args.language}", flush=True)
                print(f" Runtime: {runtime_display}", flush=True)
                print(f" Provider: {provider_display}", flush=True)
                print(flush=True)
        else:
            try:
                runtime_seg = args.runtime or "docker-compose"
                provider_seg = args.provider or "local"
                projects = get_test_projects(
                    test_set=args.test_set,
                    language=args.language,
                    platform=f"{runtime_seg}/{provider_seg}",
                )
            except Exception as e:
                error_msg = f"Error loading test projects: {e}"
                if logger:
                    logger.write_error(error_msg)
                else:
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                return 1

            if not projects:
                error_msg = f"No projects found in test set '{args.test_set}'"
                if logger:
                    logger.write_error(error_msg)
                else:
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                return 1

            if logger:
                logger.write(f"Generating {len(projects)} projects from test set '{args.test_set}'...")
                logger.write("")
            else:
                if args.verbose:
                    print(f"Generating {len(projects)} projects from test set '{args.test_set}'...")
                    print()

        success_count = 0
        fail_count = 0
        failed_projects = []
        project_warnings = {}
        project_errors = {}

        interrupted = False
        return_code = 0
        try:
            for i, project in enumerate(projects):
                project_index = i + 1
                project_name = project.get("name", "unknown")

                source_path = project.get("path", "")
                output_path = project.get("output", "")

                banner_text = f" Project [{project_index}/{len(projects)}]: {project_name} "
                banner_width = 80
                padding = banner_width - len(banner_text)
                left_pad = padding // 2
                right_pad = padding - left_pad
                banner_line = "#" * left_pad + banner_text + "#" * right_pad

                if logger:
                    logger.write("")
                    logger.write(banner_line)
                    logger.write("")
                    if source_path:
                        logger.write(f" Source: {source_path}")
                    if output_path:
                        logger.write(f" Output: {output_path}")
                    logger.write("-" * banner_width)
                else:
                    if args.verbose:
                        print("", flush=True)
                        print(colorize(banner_line, ColorCodes.CYAN), flush=True)
                        print("", flush=True)
                    # Always print source/output so PS1's Write-TeeOutput captures them in
                    # the log regardless of verbose mode. These brief context lines are
                    # appropriate to show on the console in all modes.
                    if source_path:
                        print(f" Source: {source_path}", flush=True)
                    if output_path:
                        print(f" Output: {output_path}", flush=True)
                    if args.verbose:
                        print("-" * banner_width)
                        sys.stdout.flush()

                try:
                    success, project_name, project_path, output_path, warnings, errors, full_output = generate_single_project(
                        project,
                        project_index,
                        len(projects),
                        args,
                        datrix_root,
                        python_exe,
                        verbose=args.verbose,
                    )

                    # Write full subprocess output to stdout for PowerShell to capture (always, regardless of verbose mode)
                    # When called from PS1, logger is None and PowerShell handles logging
                    # When run standalone, logger handles it
                    if full_output:
                        output_lines_text = [
                            "",
                            f"=== Detailed output for {project_name} ===",
                            *full_output,
                            f"=== End output for {project_name} ===",
                            ""
                        ]
                        if logger:
                            for line in output_lines_text:
                                logger.write(line)
                        else:
                            # No logger means PowerShell is handling logging - write to stdout
                            for line in output_lines_text:
                                print(line, flush=True)

                    if warnings:
                        project_warnings[project_name] = warnings
                    if errors:
                        project_errors[project_name] = errors
                    if logger:
                        if success:
                            logger.write_success(f"[{project_index}/{len(projects)}] {project_name}: Success")
                            success_count += 1
                        else:
                            logger.write_error(f"[{project_index}/{len(projects)}] {project_name}: Failed")
                            fail_count += 1
                            failed_projects.append(project_name)
                    else:
                        if success:
                            print(colorize(f"[{project_index}/{len(projects)}] {project_name}: Success", ColorCodes.GREEN))
                            success_count += 1
                        else:
                            print(colorize(f"[{project_index}/{len(projects)}] {project_name}: Failed", ColorCodes.RED))
                            fail_count += 1
                            failed_projects.append(project_name)
                    sys.stdout.flush()
                except Exception as e:
                    error_msg = f"Exception while generating {project_name}: {e}"
                    if logger:
                        logger.write_error(error_msg)
                        logger.write("")
                        logger.write("-" * 80)
                        logger.write_error(f"[{project_index}/{len(projects)}] Failed: {project_name}")
                        logger.write("-" * 80)
                        logger.write("")
                    else:
                        print(f"ERROR: {error_msg}", file=sys.stderr)
                        print()
                        print("-" * 80)
                        print(colorize(f"[{project_index}/{len(projects)}] Failed: {project_name}", ColorCodes.RED))
                        print("-" * 80)
                        print()
                        sys.stdout.flush()
                    fail_count += 1
                    failed_projects.append(project_name)
                    if project_name not in project_errors:
                        project_errors[project_name] = []
                    project_errors[project_name].append(error_msg)
        except KeyboardInterrupt:
            if logger:
                logger.write_warning("Interrupted by user. Cleaning up...")
            else:
                print("Interrupted by user. Cleaning up...", file=sys.stderr)
            cleanup_processes()
            interrupted = True
        finally:
            return_code = _print_generation_summary(
                projects,
                success_count,
                fail_count,
                failed_projects,
                project_warnings,
                project_errors,
                logger,
            )
            if interrupted:
                raise KeyboardInterrupt
    finally:
        if logger:
            logger.__exit__(None, None, None)

    if log_file_path:
        print(f"\nLog saved to: {log_file_path}")

    return return_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
