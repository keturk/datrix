#!/usr/bin/env python3
"""Run ast-grep structural searches across Datrix Python code.

Loads saved YAML rule files from scripts/config/ast-grep-rules/ or runs a
one-off Python pattern. Directory targets are expanded into explicit ``.py``
files so scans work from the non-git Datrix workspace root.

Usage:
    python scripts/library/dev/ast_grep.py --all --pattern "raise Exception($MSG)"
    python scripts/library/dev/ast_grep.py datrix-common --rule broad-exception
    python scripts/library/dev/ast_grep.py --all --list-rules

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\ast-grep.ps1 -All -Pattern "raise Exception($MSG)"
        .\\scripts\\dev\\ast-grep.ps1 datrix-common -Rule broad-exception
        .\\scripts\\dev\\ast-grep.ps1 -ListRules
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402

_RULES_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "ast-grep-rules"

SKIP_DIRS = frozenset({
    "__pycache__",
    ".venv",
    ".git",
    ".generated",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".tox",
    "dist",
    "build",
})

# npm installs ast-grep as a .cmd shim on Windows, which hits cmd.exe's
# shorter command-line limit before CreateProcess' native limit.
MAX_CMD_LEN = 6_000 if sys.platform == "win32" else 28_000


def get_rules_dir() -> Path:
    """Return the ast-grep rule directory, creating it if needed."""
    _RULES_DIR.mkdir(parents=True, exist_ok=True)
    return _RULES_DIR


def list_available_rules() -> list[str]:
    """Return sorted saved rule names."""
    rules_dir = get_rules_dir()
    return sorted(p.stem for p in rules_dir.glob("*.y*ml") if p.is_file())


def resolve_rule_paths(rule_names: list[str] | None) -> list[Path]:
    """Return saved ast-grep rule paths."""
    if not rule_names:
        return []

    rules_dir = get_rules_dir()
    paths: list[Path] = []
    for name in rule_names:
        clean = name.removesuffix(".yaml").removesuffix(".yml")
        candidates = [rules_dir / f"{clean}.yaml", rules_dir / f"{clean}.yml"]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            available = list_available_rules()
            raise FileNotFoundError(
                f"Rule '{clean}' not found. Available: {available}"
            )
        paths.append(path)
    return paths


def resolve_scan_targets(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_tests: bool = True,
) -> list[Path]:
    """Return project src/tests directories to scan."""
    if scan_all:
        targets: list[Path] = []
        for directory in sorted(datrix_root.iterdir()):
            if directory.is_dir() and directory.name.startswith("datrix") and (directory / "src").is_dir():
                targets.append(directory / "src")
                tests_dir = directory / "tests"
                if include_tests and tests_dir.is_dir():
                    targets.append(tests_dir)
        return targets

    targets = []
    for name in project_names:
        clean = name.rstrip("/\\")
        project_dir = datrix_root / clean
        if not project_dir.is_dir():
            available = sorted(
                directory.name
                for directory in datrix_root.iterdir()
                if directory.is_dir() and directory.name.startswith("datrix")
            )
            raise FileNotFoundError(
                f"Project '{clean}' not found. Available: {available}"
            )
        src_dir = project_dir / "src"
        if src_dir.is_dir():
            targets.append(src_dir)
        tests_dir = project_dir / "tests"
        if include_tests and tests_dir.is_dir():
            targets.append(tests_dir)
    return targets


def _expand_to_files(targets: list[Path]) -> list[Path]:
    """Expand targets into Python source files."""
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix == ".py" and not target.name.endswith(".j2"):
            files.append(target)
            continue
        if not target.is_dir():
            continue
        for child in sorted(target.rglob("*.py")):
            if any(part in SKIP_DIRS or part.startswith(".") for part in child.parts):
                continue
            if not child.name.endswith(".j2"):
                files.append(child)
    return files


def _batch_files(files: list[Path], max_len: int = MAX_CMD_LEN) -> list[list[Path]]:
    """Split files into batches that fit within Windows command-line limits."""
    batches: list[list[Path]] = []
    current: list[Path] = []
    current_len = 0
    for file_path in files:
        path_text = str(file_path)
        if current and current_len + len(path_text) + 1 > max_len:
            batches.append(current)
            current = []
            current_len = 0
        current.append(file_path)
        current_len += len(path_text) + 1
    if current:
        batches.append(current)
    return batches


def _ast_grep_bin() -> str:
    """Return the ast-grep executable name or path."""
    configured = os.environ.get("AST_GREP_BIN")
    if configured:
        return configured
    command_names = (
        "sg.cmd",
        "ast-grep.cmd",
        "sg.exe",
        "ast-grep.exe",
        "sg",
        "ast-grep",
    ) if sys.platform == "win32" else ("sg", "ast-grep")
    found = next((path for name in command_names if (path := shutil.which(name))), None)
    if found:
        return found
    return "sg"


def _run_command(cmd: list[str]) -> tuple[str, str, int]:
    """Run ast-grep and return stdout, stderr, exit code."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "", "ERROR: ast-grep not found. Install with: npm install -g @ast-grep/cli", 127
    return result.stdout, result.stderr, result.returncode


def _parse_json_output(output: str) -> list[dict[str, Any]]:
    """Parse ast-grep JSON output into normalized findings."""
    if not output.strip():
        return []

    raw_items: list[Any] = []
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw_items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for key in ("matches", "results", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_items = value
                    break
            if not raw_items:
                raw_items = [data]

    return [_normalize_finding(item) for item in raw_items if isinstance(item, dict)]


def _normalize_finding(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize ast-grep result shapes across CLI JSON styles."""
    range_data = item.get("range")
    start = range_data.get("start", {}) if isinstance(range_data, dict) else {}
    end = range_data.get("end", {}) if isinstance(range_data, dict) else {}

    rule_id = (
        item.get("rule_id")
        or item.get("ruleId")
        or item.get("id")
        or item.get("rule")
        or "pattern"
    )
    if isinstance(rule_id, dict):
        rule_id = rule_id.get("id", "pattern")

    message = item.get("message") or item.get("note") or item.get("text") or ""
    if isinstance(message, dict):
        message = json.dumps(message, ensure_ascii=False)

    line = start.get("line") or item.get("line")
    column = start.get("column") or item.get("column")

    return {
        "rule_id": str(rule_id),
        "path": str(item.get("file") or item.get("path") or item.get("filename") or "?"),
        "line": int(line) + 1 if isinstance(line, int) else 0,
        "column": int(column) + 1 if isinstance(column, int) else 0,
        "end_line": end.get("line") or 0,
        "message": str(message).strip().replace("\n", " ")[:180],
        "raw": item,
    }


def _run_pattern_batch(pattern: str, files: list[Path], json_output: bool) -> tuple[str, str, int]:
    cmd = [
        _ast_grep_bin(),
        "run",
        "--pattern",
        pattern,
        "--lang",
        "python",
    ]
    if json_output:
        cmd.append("--json=compact")
    cmd.extend(str(file_path) for file_path in files)
    return _run_command(cmd)


def _run_rule_batch(rule_path: Path, files: list[Path], json_output: bool) -> tuple[str, str, int]:
    cmd = [_ast_grep_bin(), "scan", "--rule", str(rule_path)]
    if json_output:
        cmd.append("--json=compact")
    cmd.extend(str(file_path) for file_path in files)
    return _run_command(cmd)


def _scan_batched(
    files: list[Path],
    runner: Any,
    *,
    verbose: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []

    for batch in _batch_files(files):
        stdout, stderr, exit_code = runner(batch, True)
        if exit_code == 127:
            raise RuntimeError(stderr)

        batch_findings = _parse_json_output(stdout)
        findings.extend(batch_findings)

        expected_diagnostic_exit = (
            exit_code == 1
            and batch_findings
            and "Scan succeeded and found error level diagnostics" in stderr
        )
        if stderr.strip() and not expected_diagnostic_exit:
            errors.append(stderr.strip())
        if exit_code not in (0, 1) and not batch_findings:
            errors.append(stdout.strip() or f"ast-grep exited with code {exit_code}")

        if verbose:
            raw_stdout, raw_stderr, _ = runner(batch, False)
            if raw_stdout.strip():
                print(raw_stdout)
            if raw_stderr.strip():
                print(raw_stderr, file=sys.stderr)

    return findings, errors


def scan_with_pattern(
    pattern: str,
    targets: list[Path],
    *,
    verbose: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one ast-grep pattern across target files."""
    files = _expand_to_files(targets)
    if not files:
        return [], []

    print(f"  Running pattern: {pattern} ...", end="", flush=True)
    findings, errors = _scan_batched(
        files,
        lambda batch, json_output: _run_pattern_batch(pattern, batch, json_output),
        verbose=verbose,
    )
    print(f" {len(findings)} findings, {len(errors)} errors")
    return findings, errors


def scan_with_rules(
    rule_paths: list[Path],
    targets: list[Path],
    *,
    verbose: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run saved ast-grep YAML rules across target files."""
    files = _expand_to_files(targets)
    if not files:
        return [], []

    all_findings: list[dict[str, Any]] = []
    all_errors: list[str] = []

    for rule_path in rule_paths:
        print(f"  Running rule: {rule_path.stem} ...", end="", flush=True)
        findings, errors = _scan_batched(
            files,
            lambda batch, json_output, path=rule_path: _run_rule_batch(path, batch, json_output),
            verbose=verbose,
        )
        for finding in findings:
            if finding["rule_id"] == "pattern":
                finding["rule_id"] = rule_path.stem
        all_findings.extend(findings)
        all_errors.extend(errors)
        print(f" {len(findings)} findings, {len(errors)} errors")

    return all_findings, all_errors


def print_summary(
    findings: list[dict[str, Any]],
    errors: list[str],
    targets: list[Path],
    projects: list[str],
    rule_names: list[str],
    pattern: str | None,
) -> None:
    """Print console summary."""
    print()
    print("=" * 60)
    print("AST-GREP STRUCTURAL SCAN")
    print("=" * 60)
    print(f"  Projects   : {', '.join(projects)}")
    if pattern:
        print(f"  Pattern    : {pattern}")
    if rule_names:
        print(f"  Rules      : {len(rule_names)} ({', '.join(rule_names)})")
    print(f"  Directories: {len(targets)}")
    print(f"  Findings   : {len(findings)}")
    print(f"  Errors     : {len(errors)}")
    print()

    if findings:
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            by_rule.setdefault(str(finding.get("rule_id", "unknown")), []).append(finding)

        print("-" * 60)
        print("FINDINGS BY RULE")
        print("-" * 60)
        for rule_id in sorted(by_rule):
            hits = by_rule[rule_id]
            print(f"\n  [{rule_id}] ({len(hits)} hits)")
            for hit in hits[:15]:
                path = hit.get("path", "?")
                line = hit.get("line", 0)
                message = hit.get("message", "")
                print(f"    {path}:{line}  {message}")
            if len(hits) > 15:
                print(f"    ... and {len(hits) - 15} more")

    if errors:
        print()
        print("-" * 60)
        print(f"AST-GREP ERRORS ({len(errors)})")
        print("-" * 60)
        for error in errors[:20]:
            print(f"  {error}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
    print()


def write_report(
    findings: list[dict[str, Any]],
    errors: list[str],
    report_path: Path,
    projects: list[str],
    targets: list[Path],
    rule_names: list[str],
    pattern: str | None,
) -> None:
    """Write a markdown report."""
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        by_rule.setdefault(str(finding.get("rule_id", "unknown")), []).append(finding)

    with open(report_path, "w", encoding="utf-8") as out:
        out.write("# ast-grep Structural Scan Report\n\n")
        out.write(f"**Projects:** {', '.join(projects)}\n\n")
        if pattern:
            out.write(f"**Pattern:** `{pattern}`\n\n")
        if rule_names:
            out.write(f"**Rules:** {', '.join(rule_names)}\n\n")
        out.write(f"**Directories scanned:** {len(targets)}\n\n")
        out.write(f"**Total findings:** {len(findings)}\n\n")

        if not findings:
            out.write("No structural matches detected.\n\n")
        else:
            for rule_id in sorted(by_rule):
                hits = by_rule[rule_id]
                out.write(f"## {rule_id} ({len(hits)})\n\n")
                for hit in hits:
                    path = hit.get("path", "?")
                    line = hit.get("line", 0)
                    message = hit.get("message", "")
                    out.write(f"- `{path}:{line}` - {message}\n")
                out.write("\n")

        if errors:
            out.write(f"## ast-grep Errors ({len(errors)})\n\n")
            for error in errors:
                out.write(f"- {error}\n")
            out.write("\n")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run ast-grep structural searches across Datrix Python code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names to scan (e.g. datrix-common datrix-language)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        dest="scan_all",
        help="Scan all projects in the monorepo",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=None,
        help="Run a one-off ast-grep Python pattern",
    )
    parser.add_argument(
        "--rule",
        type=str,
        action="append",
        dest="rules",
        help="Run only this saved rule (repeatable)",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List available saved rules and exit",
    )
    parser.add_argument(
        "--report",
        "-r",
        type=str,
        default=None,
        help="Write markdown report to this path (relative to monorepo root)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show raw ast-grep output for each invocation",
    )
    args = parser.parse_args()

    if args.list_rules:
        rules = list_available_rules()
        print("Available ast-grep rules:")
        for name in rules:
            print(f"  {name}")
        if not rules:
            print(f"  (none found in {get_rules_dir()})")
        return 0

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all to scan the entire monorepo.")
        return 1

    if args.pattern and args.rules:
        print("ERROR: Use either --pattern or --rule, not both.", file=sys.stderr)
        return 1

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    try:
        targets = resolve_scan_targets(
            datrix_root, args.projects, args.scan_all, include_tests=True
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not targets:
        print("No directories found to scan.")
        return 0

    try:
        rule_paths = resolve_rule_paths(args.rules)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not args.pattern and not rule_paths:
        try:
            rule_paths = resolve_rule_paths(list_available_rules())
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if not rule_paths:
            print("ERROR: Provide --pattern or add saved rules under scripts/config/ast-grep-rules.", file=sys.stderr)
            return 1

    rule_names = [path.stem for path in rule_paths]
    project_names = sorted(set(
        args.projects if not args.scan_all
        else [
            directory.name
            for directory in datrix_root.iterdir()
            if directory.is_dir()
            and directory.name.startswith("datrix")
            and (directory / "src").is_dir()
        ]
    ))

    print(f"Scanning {len(targets)} directories across {len(project_names)} project(s)")
    if args.pattern:
        print("Running one pattern...\n")
    else:
        print(f"Running {len(rule_paths)} rule(s)...\n")

    try:
        if args.pattern:
            findings, errors = scan_with_pattern(
                args.pattern,
                targets,
                verbose=args.verbose,
            )
        else:
            findings, errors = scan_with_rules(
                rule_paths,
                targets,
                verbose=args.verbose,
            )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_summary(findings, errors, targets, project_names, rule_names, args.pattern)

    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = datrix_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(
            findings,
            errors,
            report_path,
            project_names,
            targets,
            rule_names,
            args.pattern,
        )
        print(f"Report written to: {report_path}")

    if errors:
        return 2
    if findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
