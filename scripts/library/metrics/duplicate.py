#!/usr/bin/env python3
"""
Run Pylint duplicate-code detection (R0801) on Datrix project(s) Python code.

By default scans src/. With --tests, scans src/ and tests/ together.
Finds similar/duplicated code blocks across files. Exits 0 if no duplicates
above threshold; exits 1 if any found.

Supports one or more --project-root; multiple roots run one analysis across
all projects (e.g. monorepo duplicate detection).

Usage:
    python duplicate.py --project-root D:\\datrix\\datrix-common
    python duplicate.py --project-root D:\\datrix\\datrix-common --min-lines 6
    python duplicate.py --project-root D:\\datrix\\datrix-common --tests
    python duplicate.py --project-root D:\\datrix\\datrix-common --project-root D:\\datrix\\datrix-language
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
from pathlib import Path

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.ollama_utils import (  # noqa: E402
    OLLAMA_DEFAULT_URL,
    call_ollama as _call_ollama,
)

DEFAULT_MIN_LINES = 4
DEFAULT_LLM_MODEL = "qwen3-coder:30b-ctx32k"
DEFAULT_LLM_TIMEOUT_SECONDS = 180
DEFAULT_LLM_NUM_PREDICT = 4096
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_KEEP_ALIVE = "10m"
DEFAULT_LLM_GROUP_LIMIT = 20

_DUPLICATE_START_RE = re.compile(
    r"^(.+?):(\d+):(?:(\d+):)? R0801: Similar lines in (\d+) files"
)
_DUPLICATE_FILE_RE = re.compile(r"^==(.+):\[(\d+):(\d+)\]")


def _parse_duplicate_groups(pylint_output: str) -> list[dict[str, object]]:
    """Parse Pylint R0801 output into duplicate groups for advisory review."""
    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_lines: list[str] = []

    for line in pylint_output.splitlines():
        start_match = _DUPLICATE_START_RE.match(line)
        if start_match:
            if current is not None:
                current["raw"] = "\n".join(current_lines).strip()
                groups.append(current)
            file_path, line_number, _column, file_count = start_match.groups()
            current = {
                "reported_file": file_path,
                "reported_line": int(line_number),
                "file_count": int(file_count),
                "locations": [],
            }
            current_lines = [line]
            continue

        if current is None:
            continue

        current_lines.append(line)
        location_match = _DUPLICATE_FILE_RE.match(line)
        if location_match:
            file_path, start_line, end_line = location_match.groups()
            locations = current["locations"]
            if isinstance(locations, list):
                locations.append({
                    "file": file_path,
                    "start_line": int(start_line),
                    "end_line": int(end_line),
                })

    if current is not None:
        current["raw"] = "\n".join(current_lines).strip()
        groups.append(current)

    return groups


def _build_llm_refactor_prompt(
    groups: list[dict[str, object]],
    project_roots: list[Path],
    min_lines: int,
    include_tests: bool,
    limit: int,
) -> str:
    """Build a compact advisory prompt from deterministic duplicate groups."""
    selected = groups[: max(0, limit)]
    parts: list[str] = [
        "Review these deterministic Pylint R0801 duplicate-code groups for Datrix.",
        "",
        "Datrix is a backend microservices application generator with separate Python, TypeScript, cloud, and deployment codegen packages.",
        "",
        "For each duplicate group, assess:",
        "- whether duplication is likely intentional parity",
        "- whether a shared helper or extraction is reasonable",
        "- the risk of over-abstraction",
        "",
        "Local rule:",
        "- Do not recommend collapsing language-parity implementations unless the shared abstraction already exists or the extraction is clearly low-risk.",
        "",
        "Guardrails:",
        "- Advisory only. Do not say to edit, delete, or refactor automatically.",
        "- Preserve the deterministic Pylint findings; this review only prioritizes follow-up.",
        "- If evidence is insufficient, say what local context should be inspected before action.",
        "",
        "Return markdown with:",
        "1. Overall duplicate-code triage summary.",
        "2. A table with columns: group, files, parity assessment, possible extraction, over-abstraction risk, recommended next action.",
        "",
        f"project_roots: {[str(root) for root in project_roots]}",
        f"min_similarity_lines: {min_lines}",
        f"tests_included: {include_tests}",
        "",
        "Duplicate groups:",
    ]

    if not selected:
        parts.append("No duplicate groups were reported.")
        return "\n".join(parts)

    for index, group in enumerate(selected, start=1):
        parts.extend([
            "",
            f"### Group {index}",
            f"reported_file: {group.get('reported_file')}",
            f"reported_line: {group.get('reported_line')}",
            f"file_count: {group.get('file_count')}",
            "locations:",
        ])
        for location in group.get("locations", []):
            if not isinstance(location, dict):
                continue
            parts.append(
                f"- {location.get('file')}:[{location.get('start_line')}:{location.get('end_line')}]"
            )
        raw = str(group.get("raw", "")).strip()
        if raw:
            parts.extend(["pylint_evidence:", "```text", raw[:5000], "```"])

    return "\n".join(parts)


def _run_llm_refactor_plan(
    groups: list[dict[str, object]],
    project_roots: list[Path],
    min_lines: int,
    include_tests: bool,
    limit: int,
    ollama_url: str,
    model: str,
    timeout_seconds: int,
    num_predict: int,
    temperature: float,
    keep_alive: str,
) -> str:
    """Run advisory local LLM planning over duplicate-code groups."""
    prompt = _build_llm_refactor_prompt(
        groups,
        project_roots,
        min_lines,
        include_tests,
        limit,
    )
    system_prompt = (
        "You are reviewing duplicate-code findings for refactor planning. "
        "You do not edit files or override Pylint. You produce advisory markdown only."
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
        return "LLM refactor plan failed: Ollama returned no response."
    return response.strip()


def _ensure_utf8_stdio() -> None:
    """Avoid UnicodeEncodeError when printing pylint output on Windows (cp1252)."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError):
                pass
        elif hasattr(stream, "buffer"):
            name = "stdout" if stream is sys.stdout else "stderr"
            setattr(sys, name, io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Pylint duplicate-code detection for a Datrix project.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        action="append",
        required=True,
        dest="project_roots",
        help="Path(s) to project root(s) (containing src/). May be repeated for mono run.",
    )
    parser.add_argument(
    "--min-lines",
    type=int,
    default=DEFAULT_MIN_LINES,
    metavar="N",
    help=f"Minimum similar lines to report (default: {DEFAULT_MIN_LINES}).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Also include tests/ in duplicate-code detection.",
    )
    parser.add_argument(
        "--llm-refactor-plan",
        action="store_true",
        help="Add an advisory local LLM refactor plan for duplicate-code groups.",
    )
    parser.add_argument(
        "--llm-limit",
        type=int,
        default=DEFAULT_LLM_GROUP_LIMIT,
        metavar="N",
        help=f"Maximum duplicate groups to include in LLM plan (default: {DEFAULT_LLM_GROUP_LIMIT}).",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=OLLAMA_DEFAULT_URL,
        help=f"Ollama server URL (default: {OLLAMA_DEFAULT_URL}).",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=DEFAULT_LLM_MODEL,
        help=f"Local LLM model for advisory plan (default: {DEFAULT_LLM_MODEL}).",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"Ollama request timeout for LLM plan (default: {DEFAULT_LLM_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--llm-num-predict",
        type=int,
        default=DEFAULT_LLM_NUM_PREDICT,
        metavar="N",
        help=f"Ollama max generated tokens for LLM plan (default: {DEFAULT_LLM_NUM_PREDICT}).",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=DEFAULT_LLM_TEMPERATURE,
        metavar="FLOAT",
        help=f"Ollama temperature for LLM plan (default: {DEFAULT_LLM_TEMPERATURE}).",
    )
    parser.add_argument(
        "--llm-keep-alive",
        type=str,
        default=DEFAULT_LLM_KEEP_ALIVE,
        metavar="DURATION",
        help=f"Ollama keep_alive for LLM plan (default: {DEFAULT_LLM_KEEP_ALIVE}).",
    )

    args = parser.parse_args()
    _ensure_utf8_stdio()
    project_roots = [p.resolve() for p in args.project_roots]
    for root in project_roots:
        if not root.is_dir():
            print(
                f"Error: project root is not a directory: {root}",
                file=sys.stderr,
            )
            return 1

    scan_paths: list[Path] = []
    for project_root in project_roots:
        src_dir = project_root / "src"
        if not src_dir.is_dir():
            print(
                f"Warning: skipping {project_root} (no src/)",
                file=sys.stderr,
            )
            continue
        scan_paths.append(src_dir)
        if args.tests:
            tests_dir = project_root / "tests"
            if tests_dir.is_dir():
                scan_paths.append(tests_dir)
            else:
                print(
                    f"Warning: --tests specified but no tests/ in {project_root}",
                    file=sys.stderr,
                )

    if not scan_paths:
        print("Error: no project has src/ to scan.", file=sys.stderr)
        return 1

    # Mono (multi-root) runs: default to 30 lines so cross-language (Python vs TS) pairs are not reported
    min_lines = max(2, args.min_lines)
    if len(project_roots) > 1 and args.min_lines == DEFAULT_MIN_LINES:
        min_lines = max(min_lines, 30)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "pylint",
        "--disable=all",
        "--enable=R0801",
        f"--min-similarity-lines={min_lines}",
    ]
    cmd.extend(str(path) for path in scan_paths)

    cwd = str(project_roots[0])
    # Pylint R0801 embeds source snippets; Windows cp1252 stdout raises UnicodeEncodeError.
    child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=child_env,
        )
    except FileNotFoundError:
        print(
            "Error: pylint is not installed. Install with: pip install pylint",
            file=sys.stderr,
        )
        return 2

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    elif result.stdout and args.verbose and result.returncode == 0:
        print(result.stdout, end="")

    if args.llm_refactor_plan:
        groups = _parse_duplicate_groups(result.stdout or "")
        print("\n---\n## Local LLM Advisory Refactor Plan\n")
        print("This section is advisory only. It does not change deterministic Pylint findings or authorize refactoring.\n")
        if not groups:
            print("No duplicate-code groups were available for advisory review.")
        else:
            plan = _run_llm_refactor_plan(
                groups,
                project_roots,
                min_lines,
                args.tests,
                args.llm_limit,
                args.ollama_url,
                args.llm_model,
                args.llm_timeout,
                args.llm_num_predict,
                args.llm_temperature,
                args.llm_keep_alive,
            )
            print(plan)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
