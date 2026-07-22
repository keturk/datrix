#!/usr/bin/env python3
"""Parse test or generation logs and group failures by root cause.

Reads pytest output, generation result logs, or deploy test logs and groups
failures by likely root cause. Produces a triage report suitable for driving
checkpoint-based debugging sessions.

Usage:
  python scripts/library/dev/triage_failures.py <log-path> [--format pytest|generate|deploy] [--output <file>]
  .\\scripts\\dev\\triage-failures.ps1 "path/to/results.log"
"""

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.ollama_utils import OLLAMA_DEFAULT_URL  # noqa: E402
from shared.ollama_utils import call_ollama as _call_ollama  # noqa: E402

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DEFAULT_LLM_MODEL = "qwen3-coder:30b-ctx32k"
DEFAULT_LLM_TIMEOUT_SECONDS = 180
DEFAULT_LLM_NUM_PREDICT = 4096
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_KEEP_ALIVE = "10m"
DEFAULT_LLM_GROUP_LIMIT = 10


@dataclass
class Failure:
    """A single parsed failure."""

    test_id: str = ""
    error_type: str = ""
    error_message: str = ""
    file_path: str = ""
    traceback_lines: list[str] = field(default_factory=list)


def detect_format(content: str) -> str:
    """Auto-detect log format from content.

    Args:
        content: Full log file content.

    Returns:
        Detected format: 'pytest', 'generate', or 'deploy'.
    """
    if re.search(r"FAILED\s+tests/", content) or re.search(r"={3,}\s*(FAILURES|ERRORS)", content):
        return "pytest"
    if re.search(r"generate-results|Generation (completed|failed)", content):
        return "generate"
    if re.search(r"deploy-test|docker-compose", content):
        return "deploy"
    return "pytest"  # Default


def parse_pytest(lines: list[str]) -> list[Failure]:
    """Parse pytest output into failure objects.

    Args:
        lines: Lines from the pytest output log.

    Returns:
        List of Failure objects.
    """
    failures: list[Failure] = []
    in_failure_section = False
    current: Failure | None = None

    for line in lines:
        # Detect FAILURES/ERRORS section
        if re.match(r"^={3,}\s*(FAILURES|ERRORS)\s*={3,}$", line):
            in_failure_section = True
            continue

        # End of failures section
        if in_failure_section and re.match(r"^={3,}\s*(short test summary|[\d]+ (failed|passed))", line):
            in_failure_section = False
            if current:
                failures.append(current)
                current = None
            continue

        # Individual failure header
        header_match = re.match(r"^_{3,}\s*(.+?)\s*_{3,}$", line)
        if in_failure_section and header_match:
            if current:
                failures.append(current)
            current = Failure(test_id=header_match.group(1).strip())
            continue

        if current:
            current.traceback_lines.append(line)

            # Extract error type from traceback
            err_match = re.match(r"^E\s+(\w+(?:Error|Exception)):\s*(.+)$", line)
            if err_match:
                current.error_type = err_match.group(1)
                current.error_message = err_match.group(2)
            elif not current.error_type:
                err_match2 = re.match(r"^(\w+(?:Error|Exception)):\s*(.+)$", line)
                if err_match2:
                    current.error_type = err_match2.group(1)
                    current.error_message = err_match2.group(2)

            # Extract file reference
            file_match = re.match(r"^\s*([\w/\\._-]+\.py):(\d+):", line)
            if file_match and not current.file_path:
                current.file_path = file_match.group(1)

    if current:
        failures.append(current)

    # Also parse short summary lines (FAILED tests/...)
    seen_ids = {f.test_id for f in failures if f.test_id}
    for line in lines:
        summary_match = re.match(r"^FAILED\s+([\w/.:-]+)", line)
        if summary_match:
            test_id = summary_match.group(1)
            # Check if already captured
            short_name = test_id.split("::")[-1] if "::" in test_id else test_id
            if not any(short_name in sid for sid in seen_ids):
                error_info = ""
                info_match = re.search(r"-\s+(.+)$", line)
                if info_match:
                    error_info = info_match.group(1)
                error_type_match = re.search(r"(\w+Error)", error_info)
                failures.append(Failure(
                    test_id=test_id,
                    error_type=error_type_match.group(1) if error_type_match else "Unknown",
                    error_message=error_info,
                ))

    return failures


def parse_generation(lines: list[str]) -> list[Failure]:
    """Parse generation log into failure objects.

    Args:
        lines: Lines from the generation log.

    Returns:
        List of Failure objects.
    """
    failures: list[Failure] = []

    for line in lines:
        # Match ERROR/FAIL/Exception lines
        if re.search(r"(ERROR|FAIL|Exception|Traceback)", line, re.IGNORECASE):
            error_type_match = re.search(r"(\w+(?:Error|Exception))", line)
            file_match = re.search(r"([\w/\\._-]+\.(py|ts|j2)):?(\d*)", line)
            failures.append(Failure(
                error_type=error_type_match.group(1) if error_type_match else "GenerationError",
                error_message=line.strip(),
                file_path=file_match.group(1) if file_match else "",
                traceback_lines=[line],
            ))

        # Match explicit FAILED/SKIPPED/ERROR status lines
        status_match = re.match(r".*(FAILED|SKIPPED|ERROR)\s*[-|]\s*(.+)", line)
        if status_match:
            failures.append(Failure(
                test_id=status_match.group(2).strip(),
                error_type=status_match.group(1),
                error_message=status_match.group(2).strip(),
                traceback_lines=[line],
            ))

    return failures


def group_by_root_cause(failures: list[Failure]) -> dict[str, list[Failure]]:
    """Group failures by likely root cause.

    Args:
        failures: List of parsed failures.

    Returns:
        Dict mapping root cause key to list of failures.
    """
    groups: dict[str, list[Failure]] = defaultdict(list)

    for f in failures:
        key = _classify_failure(f)
        groups[key].append(f)

    return dict(groups)


def _classify_failure(f: Failure) -> str:
    """Classify a failure into a root cause group key."""
    if f.error_type in ("ImportError", "ModuleNotFoundError"):
        module_match = re.search(r"No module named '([^']+)'", f.error_message)
        if module_match:
            return f"Import: missing '{module_match.group(1)}'"
        return f"Import: {_truncate(f.error_message, 60)}"

    if f.error_type == "TypeError":
        if "unexpected keyword argument" in f.error_message:
            kwarg_match = re.search(r"'([^']+)'", f.error_message)
            kwarg = kwarg_match.group(1) if kwarg_match else "?"
            return f"TypeError: unexpected kwarg '{kwarg}'"
        if "missing" in f.error_message and "required" in f.error_message:
            return "TypeError: missing required args"
        return f"TypeError: {_truncate(f.error_message, 60)}"

    if f.error_type == "AttributeError":
        attr_match = re.search(r"'(\w+)' object has no attribute '(\w+)'", f.error_message)
        if attr_match:
            return f"AttributeError: {attr_match.group(1)}.{attr_match.group(2)}"
        return f"AttributeError: {_truncate(f.error_message, 60)}"

    if f.error_type == "AssertionError":
        return f"Assertion: {_truncate(f.test_id or f.error_message, 60)}"

    if f.error_type == "SyntaxError":
        return f"SyntaxError: {_truncate(f.error_message, 60)}"

    if f.file_path:
        return f"{f.error_type or 'Error'}: in {f.file_path}"

    msg = f.error_message or f.test_id or "unknown"
    return f"{f.error_type or 'Unknown'}: {_truncate(msg, 60)}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max length."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def priority_label(key: str, count: int) -> str:
    """Determine priority label for a root cause group."""
    if key.startswith("Import"):
        return "HIGH (blocks other tests)"
    if key.startswith(("TypeError", "AttributeError", "SyntaxError")):
        return "HIGH"
    if count >= 5:
        return "HIGH (widespread)"
    return "MEDIUM"


def generate_report(
    log_path: str,
    format_name: str,
    failures: list[Failure],
    groups: dict[str, list[Failure]],
) -> str:
    """Generate the triage report as Markdown.

    Args:
        log_path: Path to the original log file.
        format_name: Detected/forced format name.
        failures: All parsed failures.
        groups: Grouped failures by root cause.

    Returns:
        Markdown report string.
    """
    lines: list[str] = []
    lines.append("# Failure Triage Report")
    lines.append("")
    lines.append(f"**Log:** `{log_path}`")
    lines.append(f"**Format:** {format_name}")
    lines.append(f"**Total failures:** {len(failures)}")
    lines.append(f"**Distinct root causes:** {len(groups)}")
    lines.append("")
    lines.append("## Root Causes (ordered by count)")
    lines.append("")
    lines.append("| # | Root Cause | Failures | Priority |")
    lines.append("|---|-----------|----------|----------|")

    sorted_groups = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    for i, (key, group_failures) in enumerate(sorted_groups, 1):
        priority = priority_label(key, len(group_failures))
        lines.append(f"| {i} | {key} | {len(group_failures)} | {priority} |")

    lines.append("")
    lines.append("## Details")
    lines.append("")

    for i, (key, group_failures) in enumerate(sorted_groups, 1):
        lines.append(f"### {i}. {key}")
        lines.append("")
        lines.append(f"**Affected tests ({len(group_failures)}):**")
        for f in group_failures:
            test_ref = f.test_id or f.error_message or "(unknown)"
            lines.append(f"- `{test_ref}`")
        lines.append("")

    return "\n".join(lines)


def _failure_excerpt(failure: Failure, max_lines: int = 18) -> str:
    """Return a compact representative traceback/log excerpt."""
    lines = [line for line in failure.traceback_lines if line.strip()]
    if not lines:
        return failure.error_message[:1200]
    return "\n".join(lines[:max_lines])[:3000]


def _build_llm_triage_prompt(
    log_path: str,
    format_name: str,
    failures: list[Failure],
    groups: dict[str, list[Failure]],
    limit: int,
) -> str:
    """Build a compact prompt from deterministic triage groups."""
    sorted_groups = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    payload: list[dict[str, object]] = []
    for group_id, (key, group_failures) in enumerate(sorted_groups[: max(0, limit)], start=1):
        representative = group_failures[0]
        payload.append({
            "group_id": group_id,
            "root_cause_key": key,
            "failure_count": len(group_failures),
            "priority": priority_label(key, len(group_failures)),
            "representative": {
                "test_id": representative.test_id,
                "error_type": representative.error_type,
                "error_message": representative.error_message,
                "file_path": representative.file_path,
                "excerpt": _failure_excerpt(representative),
            },
            "affected": [
                f.test_id or f.error_message or "(unknown)"
                for f in group_failures[:12]
            ],
        })

    return "\n".join([
        "Review this deterministic failure triage summary for Datrix.",
        "",
        "For each group, provide:",
        "- probable root cause",
        "- first files or generated artifacts to inspect",
        "- category: codegen, template, runtime, test, deploy, or environment",
        "- concise next command to run",
        "",
        "Guardrails:",
        "- Advisory only. Do not edit files.",
        "- Deterministic group IDs and counts are the source of truth.",
        "- Use only the summary and representative excerpts below.",
        "- If evidence is insufficient, say what should be inspected next.",
        "",
        "Return markdown with an overall summary and a table by group_id.",
        "",
        json.dumps(
            {
                "log_path": log_path,
                "format": format_name,
                "total_failures": len(failures),
                "distinct_groups": len(groups),
                "groups": payload,
            },
            indent=2,
        ),
    ])


def _run_llm_triage(
    log_path: str,
    format_name: str,
    failures: list[Failure],
    groups: dict[str, list[Failure]],
    limit: int,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
) -> str:
    """Run advisory local LLM triage over deterministic failure groups."""
    prompt = _build_llm_triage_prompt(log_path, format_name, failures, groups, limit)
    system_prompt = (
        "You are a Datrix failure triage assistant. You do not modify files or "
        "decide pass/fail. You produce advisory markdown only."
    )
    response = _call_ollama(
        system_prompt,
        prompt,
        ollama_url=ollama_url,
        ollama_model=model,
        timeout=timeout_seconds,
        num_predict=num_predict,
        temperature=temperature,
        keep_alive=keep_alive,
    )
    if response is None:
        return "LLM triage failed: Ollama returned no response."
    return response.strip()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parse test/generation logs and group failures by root cause",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("log_path", help="Path to log file")
    parser.add_argument("--format", choices=["pytest", "generate", "deploy"], default="", help="Force parser format")
    parser.add_argument("--output", "-o", default="", help="Write report to file (Markdown)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--llm-summary", action="store_true", help="Append advisory local LLM triage summary")
    parser.add_argument("--llm-limit", type=int, default=DEFAULT_LLM_GROUP_LIMIT, help=f"Maximum failure groups to include in LLM summary (default: {DEFAULT_LLM_GROUP_LIMIT})")
    parser.add_argument("--ollama-url", default=OLLAMA_DEFAULT_URL, help=f"Ollama server URL (default: {OLLAMA_DEFAULT_URL})")
    parser.add_argument("--llm-model", default=DEFAULT_LLM_MODEL, help=f"Local LLM model (default: {DEFAULT_LLM_MODEL})")
    parser.add_argument("--llm-timeout", type=int, default=DEFAULT_LLM_TIMEOUT_SECONDS, help=f"Ollama timeout seconds (default: {DEFAULT_LLM_TIMEOUT_SECONDS})")
    parser.add_argument("--llm-num-predict", type=int, default=DEFAULT_LLM_NUM_PREDICT, help=f"Ollama max generated tokens (default: {DEFAULT_LLM_NUM_PREDICT})")
    parser.add_argument("--llm-temperature", type=float, default=DEFAULT_LLM_TEMPERATURE, help=f"Ollama temperature (default: {DEFAULT_LLM_TEMPERATURE})")
    parser.add_argument("--llm-keep-alive", default=DEFAULT_LLM_KEEP_ALIVE, help=f"Ollama keep_alive (default: {DEFAULT_LLM_KEEP_ALIVE})")

    args = parser.parse_args()

    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"ERROR: File not found: {log_path}", file=sys.stderr)
        return 1

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
    except OSError as e:
        print(f"ERROR: Cannot read file: {e}", file=sys.stderr)
        return 1

    # Detect or use forced format
    format_name = args.format or detect_format(content)
    if args.debug:
        print(f"[DEBUG] Using format: {format_name}", file=sys.stderr)

    # Parse
    if format_name == "pytest":
        failures = parse_pytest(lines)
    elif format_name in ("generate", "deploy"):
        failures = parse_generation(lines)
    else:
        failures = parse_pytest(lines)

    if not failures:
        print("No failures found in log.")
        return 0

    # Group by root cause
    groups = group_by_root_cause(failures)

    # Generate report
    report = generate_report(str(log_path), format_name, failures, groups)
    if args.llm_summary:
        llm_text = _run_llm_triage(
            str(log_path),
            format_name,
            failures,
            groups,
            args.llm_limit,
            args.ollama_url,
            args.llm_model,
            args.llm_timeout,
            args.llm_num_predict,
            args.llm_temperature,
            args.llm_keep_alive,
        )
        report += (
            "\n\n---\n\n## Local LLM Advisory Triage\n\n"
            "This section is advisory only. Deterministic failure groups remain the source of truth.\n\n"
            + llm_text
        )

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        print(f"Triage report written to: {output_path}")
        print(f"Summary: {len(failures)} failures from {len(groups)} root causes")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
