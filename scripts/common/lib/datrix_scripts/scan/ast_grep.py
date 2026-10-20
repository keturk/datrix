#!/usr/bin/env python3
"""Run ast-grep structural searches across Datrix Python code.

Loads saved YAML rule files from scripts/config/ast-grep-rules/ or runs a
one-off Python pattern. Directory targets are expanded into explicit ``.py``
files so scans work from the non-git Datrix workspace root.

The module behind ``scan/ast-grep.ps1`` (and its ``.sh`` twin). ``--list-rules`` wins over a scan,
and ``--all`` over named projects; neither a project nor ``--all`` prints the usage and exits 1.
Exit codes: 0 no finding, 1 a finding or a refusal, 2 an ast-grep error.

Usage:
    python -m datrix_scripts.scan.ast_grep --all --pattern="raise Exception($MSG)"
    python -m datrix_scripts.scan.ast_grep --projects=datrix-common --rule=broad-exception
    python -m datrix_scripts.scan.ast_grep --list-rules
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import write_files
from datrix_scripts.logic_map import resolve_scan_paths
from datrix_scripts.paths import CONFIG_DIR, SCRIPTS_DIR, SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.scan.selection import SelectionRefused, expect_refusal, require_selection, wrapper_usage
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.scan.ast_grep"
WRAPPER: Final = "ast-grep"

_USAGE: Final = wrapper_usage(
    WRAPPER,
    [
        "<project> [project2 ...] -Pattern <pattern>",
        "-All -Pattern <pattern> [-Report <path>]",
        "-All [-Rule <name>] [-Report <path>]",
        "-ListRules",
    ],
)

_RULES_DIR = CONFIG_DIR / "ast-grep-rules"

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
    """Return project src/tests directories to scan.

    The showcase repo has no src/ or tests/: its Python is the repo tooling under
    scripts/, so that tree is scanned whenever the showcase is in scope (``--all``
    or named). A rule confines itself to part of it through its own ``files:``.

    Raises:
        FileNotFoundError: If a requested project does not exist.
    """
    pairs = resolve_scan_paths(datrix_root, project_names, scan_all, include_tests=include_tests)
    targets = [directory for _, directory in pairs]
    named_dirs = {(datrix_root / name.rstrip("/\\")).resolve() for name in project_names}
    if scan_all or SHOWCASE_DIR.resolve() in named_dirs:
        targets.append(SCRIPTS_DIR)
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
    # `ast-grep` first: current releases print a deprecation warning for the `sg` alias on every run.
    command_names = (
        "ast-grep.cmd",
        "ast-grep.exe",
        "ast-grep",
        "sg.cmd",
        "sg.exe",
        "sg",
    ) if sys.platform == "win32" else ("ast-grep", "sg")
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


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/ast-grep.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--projects", action="append", default=[],
                        help="A project name to scan, e.g. datrix-common (repeatable).")
    parser.add_argument("--all", action="store_true", dest="scan_all", help="Scan all projects in the monorepo.")
    parser.add_argument("--pattern", help="Run a one-off ast-grep Python pattern.")
    parser.add_argument("--rule", action="append", dest="rules", help="Run only this saved rule (repeatable).")
    parser.add_argument("--list-rules", action="store_true", help="List available saved rules and exit.")
    parser.add_argument("--report", help="Write a markdown report to this path (relative to monorepo root).")
    parser.add_argument("--show-raw", action="store_true", help="Show raw ast-grep output for each invocation.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a saved rule finds a planted violation and passes a clean "
                             "file, the rule set resolves, an unknown rule and --pattern with --rule are refused, "
                             "the usage is printed when nothing is selected, and the wrapper seam holds.")
    parser.set_defaults(debug=False)
    return parser


def print_rules() -> int:
    """Print the saved rule names."""
    rules = list_available_rules()
    print("Available ast-grep rules:")
    for name in rules:
        print(f"  {name}")
    if not rules:
        print(f"  (none found in {get_rules_dir()})")
    return 0


def _selected_rule_paths(args: argparse.Namespace) -> list[Path]:
    """The ``--rule`` files, or every saved rule when neither ``--rule`` nor ``--pattern`` is given.

    Raises:
        FileNotFoundError: a named rule does not exist, or there is neither a pattern nor a saved rule.
    """
    rule_paths = resolve_rule_paths(args.rules)
    if args.pattern or rule_paths:
        return rule_paths
    rule_paths = resolve_rule_paths(list_available_rules())
    if not rule_paths:
        raise FileNotFoundError("Provide --pattern or add saved rules under scripts/config/ast-grep-rules.")
    return rule_paths


def _project_names(args: argparse.Namespace, datrix_root: Path) -> list[str]:
    if not args.scan_all:
        return sorted(set(args.projects))
    return sorted({
        directory.name
        for directory in workspace_package_dirs(datrix_root, any_of=frozenset({PackageMarker.SRC}), include_showcase=True)
    })


def _report_path(report: str, datrix_root: Path) -> Path:
    """The report file *report* names, relative to *datrix_root* unless absolute, with its folder created."""
    report_path = Path(report)
    if not report_path.is_absolute():
        report_path = datrix_root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return report_path


def scan_projects(args: argparse.Namespace, datrix_root: Path) -> int:
    """Run the pattern or the selected rules over the selected projects under *datrix_root*.

    0 no finding, 1 a finding or a refusal, 2 an ast-grep error."""
    try:
        targets = resolve_scan_targets(datrix_root, args.projects, args.scan_all, include_tests=True)
        if not targets:
            print("No directories found to scan.")
            return 0
        rule_paths = _selected_rule_paths(args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rule_names = [path.stem for path in rule_paths]
    project_names = _project_names(args, datrix_root)
    print(f"Scanning {len(targets)} directories across {len(project_names)} project(s)")
    print("Running one pattern...\n" if args.pattern else f"Running {len(rule_paths)} rule(s)...\n")

    try:
        if args.pattern:
            findings, errors = scan_with_pattern(args.pattern, targets, verbose=args.show_raw)
        else:
            findings, errors = scan_with_rules(rule_paths, targets, verbose=args.show_raw)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_summary(findings, errors, targets, project_names, rule_names, args.pattern)
    if args.report:
        report_path = _report_path(args.report, datrix_root)
        write_report(findings, errors, report_path, project_names, targets, rule_names, args.pattern)
        print(f"Report written to: {report_path}")
    if errors:
        return 2
    return 1 if findings else 0


def selected_scan_refusal(args: argparse.Namespace) -> int | None:
    """The exit code of a run *args* cannot start (the usage, or ``--pattern`` with ``--rule``), else None."""
    try:
        require_selection(args.projects, args.scan_all, _USAGE, refuse_both=False)
    except SelectionRefused as refused:
        return refused.report()
    if args.pattern and args.rules:
        print("ERROR: Use either --pattern or --rule, not both.", file=sys.stderr)
        return 1
    return None


def _planted_scan(source: str) -> tuple[int, str]:
    """Scan one planted project holding *source* with the ``empty-except-pass`` rule: exit code and output."""
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"datrix-planted/src/planted.py": source})
        args = build_parser().parse_args(["--projects=datrix-planted", "--rule=empty-except-pass"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = scan_projects(args, Path(tmp))
        return code, out.getvalue()


def _check_a_saved_rule_finds_a_planted_violation() -> None:
    code, out = _planted_scan("def f():\n    try:\n        return 1\n    except Exception:\n        pass\n")
    assert code == 1 and "Findings   : 1" in out, f"the planted except/pass must be the one finding (exit 1): {out!r}"


def _check_a_saved_rule_passes_a_clean_file() -> None:
    code, out = _planted_scan("VALUE = 1\n")
    assert code == 0 and "Findings   : 0" in out, f"a clean file must give no finding (exit 0): {out!r}"


def _check_the_rule_set_resolves() -> None:
    names = list_available_rules()
    assert names, f"no saved rule found in {_RULES_DIR}"
    resolved = [path.stem for path in resolve_rule_paths(names)]
    assert resolved == names, f"each listed rule must resolve to its file; listed {names}, resolved {resolved}"


def _check_an_unknown_rule_is_refused() -> None:
    try:
        resolve_rule_paths(["no-such-rule"])
    except FileNotFoundError as exc:
        assert "no-such-rule" in str(exc), f"the refusal must name the rule; got {exc}"
    else:
        raise AssertionError("an unknown rule must be refused")


def _check_a_pattern_with_a_rule_is_refused() -> None:
    args = build_parser().parse_args(["--projects=x", "--pattern=pass", "--rule=empty-except-pass"])
    with contextlib.redirect_stderr(io.StringIO()):
        refusal = selected_scan_refusal(args)
    assert refusal == 1, f"--pattern together with --rule must exit 1; got {refusal}"


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: require_selection([], False, _USAGE, refuse_both=False), 1, _USAGE)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_a_saved_rule_finds_a_planted_violation,
            _check_a_saved_rule_passes_a_clean_file,
            _check_the_rule_set_resolves,
            _check_an_unknown_rule_is_refused,
            _check_a_pattern_with_a_rule_is_refused,
            _check_nothing_selected_prints_the_usage,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    if args.list_rules:
        return print_rules()
    refusal = selected_scan_refusal(args)
    if refusal is not None:
        return refusal
    return scan_projects(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
