#!/usr/bin/env python3
"""Run Semgrep with Datrix-specific rules across the monorepo.

Loads individual YAML rule files from scripts/config/semgrep-rules/ and runs
them one at a time (or all together).  Each rule can be tested independently.

Rules (in scripts/config/semgrep-rules/):

    silent-fallback-none    : dict.get(key, None)
    default-type-mapping    : type_map.get(t, "Any")
    empty-except-pass       : except: pass / except Exception: pass
    missing-encoding-read   : Path.read_text() without encoding=
    missing-encoding-write  : Path.write_text() without encoding=
    banned-mock-import      : from unittest.mock import MagicMock/Mock/patch
    banned-simple-namespace : from types import SimpleNamespace
    return-none-lookup      : return None in get_*/find_*/lookup_*/resolve_*
    string-concat-codegen   : f"class {name}:" code generation
    todo-comment            : # TODO comments
    magic-number-status     : bare 200/404/500 comparisons
    redundant-case-conversion : to_*_case(str(x)) and other re-derived case variants

The module behind ``scan/semgrep.ps1`` (and its ``.sh`` twin). ``--list-rules`` wins over a scan,
and ``--all`` over named projects; neither a project nor ``--all`` prints the usage and exits 1.
Exit codes: 0 no finding, 1 a finding, an unknown project or rule, or a semgrep failure.

Usage:
    python -m datrix_scripts.scan.semgrep --all --rule=missing-encoding-read
    python -m datrix_scripts.scan.semgrep --projects=datrix-common --rule=return-none-lookup
    python -m datrix_scripts.scan.semgrep --projects=datrix-common --rule=a --rule=b --single-pass
    python -m datrix_scripts.scan.semgrep --list-rules
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import write_files
from datrix_scripts.logic_map import resolve_scan_paths
from datrix_scripts.paths import CONFIG_DIR, WORKSPACE_DIR
from datrix_scripts.scan.selection import SelectionRefused, expect_refusal, require_selection, wrapper_usage
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

MODULE: Final = "datrix_scripts.scan.semgrep"
WRAPPER: Final = "semgrep"

_USAGE: Final = wrapper_usage(
    WRAPPER, ["<project> [project2 ...]", "-All [-Rule <name>] [-Report <path>]", "-ListRules"]
)

_RULES_DIR = CONFIG_DIR / "semgrep-rules"

#: The module semgrep runs as (``python -m semgrep``), so the shared venv's copy runs, never one PATH finds.
_SEMGREP_MODULE: Final = "semgrep"

#: Exit code the run functions return when this interpreter cannot import semgrep.
SEMGREP_MISSING_EXIT = 127

#: ``platform.machine()`` of Windows on ARM: the one platform the ``scripts`` dependency group of
#: datrix/pyproject.toml leaves semgrep out of (its marker tests the same value), as semgrep
#: publishes no Windows ARM64 wheel.
_WINDOWS_ARM64_MACHINE = "ARM64"


def semgrep_missing_message() -> str:
    """Why this interpreter cannot import semgrep, and the fix, for this interpreter's platform."""
    if sys.platform == "win32" and platform.machine() == _WINDOWS_ARM64_MACHINE:
        return (
            "ERROR: semgrep not found. semgrep publishes no Windows ARM64 wheel, so the 'scripts' "
            "dependency group of datrix/pyproject.toml leaves it out of a native Windows ARM64 venv. "
            "Run this scan on a platform semgrep ships for (Windows x64, macOS, Linux)."
        )
    return f"ERROR: {missing_declared_tool('semgrep', SCRIPTS_DEPENDENCY_GROUP)}"


SKIP_DIRS = frozenset({
    "__pycache__", ".venv", ".git", ".generated", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules", ".tox", "dist", "build",
})


# ---------------------------------------------------------------------------
# Rule discovery
# ---------------------------------------------------------------------------

def get_rules_dir() -> Path:
    """Return the path to the semgrep-rules config directory.

    Raises:
        FileNotFoundError: If the rules directory does not exist.
    """
    if not _RULES_DIR.is_dir():
        raise FileNotFoundError(
            f"Semgrep rules directory not found: {_RULES_DIR}"
        )
    return _RULES_DIR


def list_available_rules() -> list[str]:
    """Return sorted rule names (filenames without .yaml extension)."""
    rules_dir = get_rules_dir()
    return sorted(p.stem for p in rules_dir.glob("*.yaml"))


def resolve_rule_paths(rule_names: list[str] | None) -> list[Path]:
    """Return paths to rule YAML files.

    Args:
        rule_names: Specific rules to use, or None for all rules.

    Raises:
        FileNotFoundError: If a requested rule file does not exist.
    """
    rules_dir = get_rules_dir()

    if rule_names is None:
        return sorted(rules_dir.glob("*.yaml"))

    paths = []
    for name in rule_names:
        clean = name.removesuffix(".yaml")
        path = rules_dir / f"{clean}.yaml"
        if not path.is_file():
            available = list_available_rules()
            raise FileNotFoundError(
                f"Rule '{clean}' not found. Available: {available}"
            )
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Scan targets
# ---------------------------------------------------------------------------

def resolve_scan_targets(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_tests: bool = True,
) -> list[Path]:
    """Return directories to pass to semgrep.

    Args:
        include_tests: If False, only each project's ``src/`` is included (when
            ``scan_all`` is False). When ``scan_all`` is True, the same flag
            controls whether ``tests/`` trees are appended.

    Raises:
        FileNotFoundError: If a requested project does not exist.
    """
    pairs = resolve_scan_paths(datrix_root, project_names, scan_all, include_tests=include_tests)
    return [directory for _, directory in pairs]


# ---------------------------------------------------------------------------
# Semgrep execution
# ---------------------------------------------------------------------------

def _expand_to_files(targets: list[Path]) -> list[Path]:
    """Expand directory targets into individual .py files.

    Semgrep uses ``git ls-files`` for file discovery in directories.
    In non-git workspaces this returns zero files.  We bypass this by
    expanding directories into explicit file paths ourselves.
    """
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
            continue
        for child in sorted(target.rglob("*.py")):
            if any(part in SKIP_DIRS or part.startswith(".") for part in child.parts):
                continue
            if child.suffix == ".py" and not child.name.endswith(".j2"):
                files.append(child)
    return files


MAX_CMD_LEN = 28_000


def _batch_files(files: list[Path], max_len: int = MAX_CMD_LEN) -> list[list[Path]]:
    """Split files into batches that fit within command-line length limits."""
    batches: list[list[Path]] = []
    current: list[Path] = []
    current_len = 0
    for f in files:
        s = str(f)
        if current and current_len + len(s) + 1 > max_len:
            batches.append(current)
            current = []
            current_len = 0
        current.append(f)
        current_len += len(s) + 1
    if current:
        batches.append(current)
    return batches


def _run_semgrep_batch(
    rules_path: Path,
    files: list[Path],
    json_output: bool,
) -> tuple[str, int]:
    """Run semgrep on a single batch of files."""
    cmd = [
        sys.executable, "-m", _SEMGREP_MODULE, "scan",
        "--config", str(rules_path),
        "--no-git-ignore",
    ]
    if json_output:
        cmd.append("--json")
    cmd.extend(str(f) for f in files)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout
    if result.stderr and not json_output:
        output += "\n" + result.stderr
    return output, result.returncode


def _run_semgrep_batch_multi_configs(
    rules_paths: list[Path],
    files: list[Path],
    json_output: bool,
) -> tuple[str, int]:
    """Run semgrep once per batch with multiple rule files (one filesystem pass)."""
    cmd: list[str] = [sys.executable, "-m", _SEMGREP_MODULE, "scan", "--no-git-ignore"]
    for rules_path in rules_paths:
        cmd.extend(["--config", str(rules_path)])
    if json_output:
        cmd.append("--json")
    cmd.extend(str(f) for f in files)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout
    if result.stderr and not json_output:
        output += "\n" + result.stderr
    return output, result.returncode


def run_semgrep(
    rules_path: Path,
    targets: list[Path],
    json_output: bool = False,
) -> tuple[str, int]:
    """Run semgrep scan with a single rule file and return (stdout, exit_code).

    Expands directory targets into individual ``.py`` files so that semgrep
    works correctly even in non-git workspaces.  Large file lists are batched
    to stay within Windows command-line length limits. Refused up front, with
    ``SEMGREP_MISSING_EXIT``, when this interpreter cannot import semgrep.
    """
    if importlib.util.find_spec(_SEMGREP_MODULE) is None:
        return semgrep_missing_message(), SEMGREP_MISSING_EXIT
    files = _expand_to_files(targets)
    if not files:
        return '{"results":[],"errors":[]}' if json_output else "No files to scan.", 0

    batches = _batch_files(files)
    if len(batches) == 1:
        return _run_semgrep_batch(rules_path, batches[0], json_output)

    all_findings: list[dict] = []
    all_errors: list[dict] = []
    last_exit = 0

    for batch in batches:
        output, code = _run_semgrep_batch(rules_path, batch, json_output=True)
        if code != 0:
            last_exit = code
        findings, errors = parse_json_output(output)
        all_findings.extend(findings)
        all_errors.extend(errors)

    if json_output:
        merged = json.dumps({"results": all_findings, "errors": all_errors})
        return merged, last_exit

    lines = [f"Batched scan: {len(batches)} batches, {len(all_findings)} findings"]
    return "\n".join(lines), last_exit


def run_semgrep_multi_configs(
    rules_paths: list[Path],
    targets: list[Path],
    json_output: bool = False,
) -> tuple[str, int]:
    """Run semgrep with multiple rule YAMLs in one invocation per file batch.

    Faster than calling :func:`run_semgrep` once per rule when several rules
    apply to the same files (one parse pass per batch instead of N). Refused up
    front, with ``SEMGREP_MISSING_EXIT``, when this interpreter cannot import semgrep.
    """
    if not rules_paths:
        return '{"results":[],"errors":[]}' if json_output else "No rules.", 0
    if importlib.util.find_spec(_SEMGREP_MODULE) is None:
        return semgrep_missing_message(), SEMGREP_MISSING_EXIT

    files = _expand_to_files(targets)
    if not files:
        return '{"results":[],"errors":[]}' if json_output else "No files to scan.", 0

    batches = _batch_files(files)
    if len(batches) == 1:
        return _run_semgrep_batch_multi_configs(rules_paths, batches[0], json_output)

    all_findings: list[dict] = []
    all_errors: list[dict] = []
    last_exit = 0

    for batch in batches:
        output, code = _run_semgrep_batch_multi_configs(rules_paths, batch, json_output=True)
        if code != 0:
            last_exit = code
        findings, errors = parse_json_output(output)
        all_findings.extend(findings)
        all_errors.extend(errors)

    if json_output:
        merged = json.dumps({"results": all_findings, "errors": all_errors})
        return merged, last_exit

    lines = [
        f"Batched multi-rule scan: {len(batches)} batches, {len(all_findings)} findings"
    ]
    return "\n".join(lines), last_exit


def _clean_rule_id(check_id: str) -> str:
    """Strip config-path prefix from semgrep check_id.

    Semgrep prefixes rule IDs with the config file path, e.g.
    ``scripts.config.semgrep-rules.return-none-lookup.datrix.return-none-lookup``.
    We want just ``datrix.return-none-lookup``.
    """
    marker = ".datrix."
    idx = check_id.find(marker)
    if idx != -1:
        return "datrix." + check_id[idx + len(marker):]
    if check_id.startswith("datrix."):
        return check_id
    return check_id


def parse_json_output(json_str: str) -> tuple[list[dict], list[dict]]:
    """Parse semgrep JSON output into (findings, errors)."""
    try:
        data = json.loads(json_str)
        results = data.get("results", [])
        for r in results:
            if "check_id" in r:
                r["check_id"] = _clean_rule_id(r["check_id"])
        errors = data.get("errors", [])
        return results, errors
    except (json.JSONDecodeError, KeyError):
        return [], []


def scan_with_rules(
    rule_paths: list[Path],
    targets: list[Path],
    verbose: bool = False,
    single_pass: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Run semgrep, aggregating findings and errors.

    Args:
        rule_paths: YAML rule files.
        targets: Directories (or files) to scan.
        verbose: If True, print raw semgrep text for each rule (non-single-pass).
        single_pass: If True, pass all ``rule_paths`` as ``--config`` to one
            semgrep process per batch (much faster for many rules on the same
            tree). If False, run semgrep once per rule file (legacy behavior).
    """
    all_findings: list[dict] = []
    all_errors: list[dict] = []

    if single_pass and rule_paths:
        names = ", ".join(p.stem for p in rule_paths)
        print(
            f"  Running rules in one Semgrep pass: {names} ...",
            end="",
            flush=True,
        )
        json_output, exit_code = run_semgrep_multi_configs(
            rule_paths, targets, json_output=True
        )
        if exit_code == SEMGREP_MISSING_EXIT:
            print(" SEMGREP NOT FOUND")
            print(json_output, file=sys.stderr)
            raise RuntimeError("semgrep not found")
        findings, errors = parse_json_output(json_output)
        all_findings.extend(findings)
        all_errors.extend(errors)
        print(f" {len(findings)} findings, {len(errors)} errors")
        if verbose and findings:
            text_output, _ = run_semgrep_multi_configs(
                rule_paths, targets, json_output=False
            )
            print(text_output)
        return all_findings, all_errors

    for rule_path in rule_paths:
        rule_name = rule_path.stem
        print(f"  Running rule: {rule_name} ...", end="", flush=True)

        json_output, exit_code = run_semgrep(rule_path, targets, json_output=True)

        if exit_code == SEMGREP_MISSING_EXIT:
            print(" SEMGREP NOT FOUND")
            print(json_output, file=sys.stderr)
            raise RuntimeError("semgrep not found")

        findings, errors = parse_json_output(json_output)
        all_findings.extend(findings)
        all_errors.extend(errors)

        print(f" {len(findings)} findings, {len(errors)} errors")

        if verbose and findings:
            text_output, _ = run_semgrep(rule_path, targets, json_output=False)
            print(text_output)

    return all_findings, all_errors


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(
    findings: list[dict],
    errors: list[dict],
    targets: list[Path],
    projects: list[str],
    rule_names: list[str],
) -> None:
    """Print console summary."""
    print()
    print("=" * 60)
    print("SEMGREP ANTI-PATTERN SCAN")
    print("=" * 60)
    print(f"  Projects   : {', '.join(projects)}")
    print(f"  Rules      : {len(rule_names)} ({', '.join(rule_names)})")
    print(f"  Directories: {len(targets)}")
    print(f"  Findings   : {len(findings)}")
    print(f"  Errors     : {len(errors)}")
    print()

    if findings:
        by_rule: dict[str, list[dict]] = {}
        for f in findings:
            rule_id = f.get("check_id", "unknown")
            by_rule.setdefault(rule_id, []).append(f)

        print("-" * 60)
        print("FINDINGS BY RULE")
        print("-" * 60)
        for rule_id in sorted(by_rule):
            hits = by_rule[rule_id]
            severity = hits[0].get("extra", {}).get("severity", "?")
            print(f"\n  [{rule_id}] severity={severity} ({len(hits)} hits)")
            for h in hits[:15]:
                path = h.get("path", "?")
                line = h.get("start", {}).get("line", 0)
                msg = h.get("extra", {}).get("message", "").strip().replace("\n", " ")[:100]
                print(f"    {path}:{line}  {msg}")
            if len(hits) > 15:
                print(f"    ... and {len(hits) - 15} more")

    if errors:
        print()
        print("-" * 60)
        print(f"SEMGREP ERRORS ({len(errors)})")
        print("-" * 60)
        for err in errors[:20]:
            err_type = err.get("type", "unknown")
            err_msg = err.get("long_msg") or err.get("short_msg") or err.get("message", "?")
            err_path = err.get("path", "")
            if err_path:
                print(f"  [{err_type}] {err_path}: {err_msg}")
            else:
                print(f"  [{err_type}] {err_msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
    print()


def write_report(
    findings: list[dict],
    errors: list[dict],
    report_path: Path,
    projects: list[str],
    targets: list[Path],
    rule_names: list[str],
) -> None:
    """Write a markdown report."""
    by_rule: dict[str, list[dict]] = {}
    for f in findings:
        rule_id = f.get("check_id", "unknown")
        by_rule.setdefault(rule_id, []).append(f)

    with open(report_path, "w", encoding="utf-8") as out:
        out.write("# Semgrep Anti-Pattern Scan Report\n\n")
        out.write(f"**Projects:** {', '.join(projects)}\n\n")
        out.write(f"**Rules:** {', '.join(rule_names)}\n\n")
        out.write(f"**Directories scanned:** {len(targets)}\n\n")
        out.write(f"**Total findings:** {len(findings)}\n\n")

        if not findings:
            out.write("No anti-patterns detected.\n\n")
        else:
            for rule_id in sorted(by_rule):
                hits = by_rule[rule_id]
                severity = hits[0].get("extra", {}).get("severity", "?")
                out.write(f"## {rule_id} [{severity}] ({len(hits)})\n\n")
                for h in hits:
                    path = h.get("path", "?")
                    line = h.get("start", {}).get("line", 0)
                    msg = h.get("extra", {}).get("message", "").strip().replace("\n", " ")
                    out.write(f"- `{path}:{line}` — {msg}\n")
                out.write("\n")

        if errors:
            out.write(f"## Semgrep Errors ({len(errors)})\n\n")
            for err in errors:
                err_type = err.get("type", "unknown")
                err_msg = err.get("long_msg") or err.get("short_msg") or err.get("message", "?")
                err_path = err.get("path", "")
                if err_path:
                    out.write(f"- [{err_type}] `{err_path}`: {err_msg}\n")
                else:
                    out.write(f"- [{err_type}] {err_msg}\n")
            out.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/semgrep.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--projects", action="append", default=[],
                        help="A project name to scan, e.g. datrix-common (repeatable).")
    parser.add_argument("--all", action="store_true", dest="scan_all", help="Scan all projects in the monorepo.")
    parser.add_argument("--rule", action="append", dest="rules",
                        help="Run only this rule (repeatable, e.g. --rule=empty-except-pass --rule=todo-comment).")
    parser.add_argument("--list-rules", action="store_true", help="List available rules and exit.")
    parser.add_argument("--report", help="Write a markdown report to this path (relative to monorepo root).")
    parser.add_argument("--show-raw", action="store_true", help="Show raw semgrep output for each rule.")
    parser.add_argument(
        "--single-pass",
        action="store_true",
        dest="single_pass",
        help=(
            "Run all selected rules in one semgrep invocation per file batch "
            "(faster than the default one-invocation-per-rule)."
        ),
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: the rule set lists and resolves, an unknown rule and an "
                             "unknown project are refused, the usage is printed when nothing is selected, and "
                             "the wrapper seam holds. Runs no semgrep process.")
    parser.set_defaults(debug=False)
    return parser


def print_rules() -> int:
    """Print the available rule names; 1 when the rules directory is missing."""
    try:
        rules = list_available_rules()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Available semgrep rules:")
    for name in rules:
        print(f"  {name}")
    return 0


def _project_names(args: argparse.Namespace, datrix_root: Path) -> list[str]:
    if not args.scan_all:
        return sorted(set(args.projects))
    return sorted({
        d.name for d in workspace_package_dirs(datrix_root, any_of=frozenset({PackageMarker.SRC}), include_showcase=True)
    })


def _announce(targets: Sequence[Path], project_names: Sequence[str], rule_count: int, single_pass: bool) -> None:
    print(f"Scanning {len(targets)} directories across {len(project_names)} project(s)")
    if single_pass and rule_count > 1:
        print(
            f"Running {rule_count} rule(s) in single-pass mode "
            f"(one semgrep invocation per batch)...\n"
        )
    else:
        print(f"Running {rule_count} rule(s)...\n")


def _check_the_rule_set_lists_and_resolves() -> None:
    names = list_available_rules()
    assert names, f"no rule found in {_RULES_DIR}"
    resolved = [path.stem for path in resolve_rule_paths(names)]
    assert resolved == names, f"each listed rule must resolve to its file; listed {names}, resolved {resolved}"


def _check_an_unknown_rule_is_refused() -> None:
    try:
        resolve_rule_paths(["no-such-rule"])
    except FileNotFoundError as exc:
        assert "no-such-rule" in str(exc), f"the refusal must name the rule; got {exc}"
    else:
        raise AssertionError("an unknown rule must be refused")


def _check_an_unknown_project_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"datrix-planted/src/planted.py": "VALUE = 1\n"})
        found = resolve_scan_targets(Path(tmp), ["datrix-planted"], False)
        assert found == [Path(tmp) / "datrix-planted" / "src"], f"the planted project's src/ must be the target: {found}"
        try:
            resolve_scan_targets(Path(tmp), ["datrix-absent"], False)
        except FileNotFoundError as exc:
            assert "datrix-absent" in str(exc), f"the refusal must name the project; got {exc}"
        else:
            raise AssertionError("an unknown project must be refused")


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: require_selection([], False, _USAGE, refuse_both=False), 1, _USAGE)


def _report_and_exit(
    report: str | None,
    findings: list[dict],
    errors: list[dict],
    datrix_root: Path,
    project_names: list[str],
    targets: list[Path],
    rule_names: list[str],
) -> int:
    """Write *report* when given; 1 when there is a finding, else 0."""
    if report:
        report_path = Path(report)
        if not report_path.is_absolute():
            report_path = datrix_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(findings, errors, report_path, project_names, targets, rule_names)
        print(f"Report written to: {report_path}")

    if findings:
        return 1
    return 0


def scan_projects(args: argparse.Namespace, datrix_root: Path) -> int:
    """Run the selected rules over the selected projects under *datrix_root*; 1 on any finding or refusal."""
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

    rule_names = [p.stem for p in rule_paths]
    project_names = _project_names(args, datrix_root)
    _announce(targets, project_names, len(rule_paths), args.single_pass)

    try:
        findings, errors = scan_with_rules(
            rule_paths,
            targets,
            verbose=args.show_raw,
            single_pass=args.single_pass,
        )
    except RuntimeError:
        return 1

    print_summary(findings, errors, targets, project_names, rule_names)
    return _report_and_exit(args.report, findings, errors, datrix_root, project_names, targets, rule_names)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_the_rule_set_lists_and_resolves,
            _check_an_unknown_rule_is_refused,
            _check_an_unknown_project_is_refused,
            _check_nothing_selected_prints_the_usage,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    if args.list_rules:
        return print_rules()
    try:
        require_selection(args.projects, args.scan_all, _USAGE, refuse_both=False)
    except SelectionRefused as refused:
        return refused.report()
    return scan_projects(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
