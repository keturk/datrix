#!/usr/bin/env python3
r"""Audit generated Python code for placeholders and syntax errors.

Scans .generated/python/docker (or a given path) for:
- Python syntax errors (ast.parse)
- Placeholder patterns: pass, raise NotImplementedError, "# Test fixtures placeholder"

Paths matching db/base.py or _microservice_helpers.py are allowlisted (excluded from
--fail-on-placeholders). See datrix/scripts/scan/quick-reference.md.

The module behind ``scan/audit.ps1`` (and its ``.sh`` twin). With no argument at all it prints the
usage and exits 1. Exit codes: 0, 1 the generated root is missing, 2 a syntax error under
``--fail-on-syntax``, 3 an actionable placeholder under ``--fail-on-placeholders``.

Usage:
    python -m datrix_scripts.scan.audit --report=examples-generated-audit-report.md [--output-base=.generated]
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NamedTuple

from datrix_scripts.gate_harness import write_files
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalLlmSettings,
    add_wrapper_llm_arguments,
    advisory_text,
    wrapper_llm_settings,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import wrapper_usage
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.scan.audit"
WRAPPER: Final = "audit"

_USAGE: Final = (
    wrapper_usage(
        WRAPPER,
        ["-Report <path>", "-Report examples-generated-audit-report.md [-FailOnSyntax] [-FailOnPlaceholders]"],
        get_help=False,
    )
    + "\n\nReport path is under repository root. Use Get-Help .\\audit.ps1 -Full for detailed help."
)

DEFAULT_OUTPUT_BASE: Final = ".generated"
#: The generated tree audited under the output base.
GENERATED_SUBPATH: Final = "python/docker"
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 180
_SHOWN_SYNTAX_ERRORS: Final = 20

# Patterns for placeholder scan (path -> list of (line_no, line_text))
PATTERN_PASS = re.compile(r"\bpass\b")
PATTERN_NOT_IMPLEMENTED = re.compile(r"raise\s+NotImplementedError\s*\(")
PATTERN_TEST_PLACEHOLDER = re.compile(r"#\s*Test\s+fixtures\s+placeholder", re.I)

# Path substrings that are allowlisted (intentional placeholders; excluded from --fail-on-placeholders)
ALLOWLIST_PATH_SUBSTRINGS = ("db/base.py", "_microservice_helpers.py")
DEFAULT_LLM_NUM_PREDICT = 4096
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_FINDING_LIMIT = 30


def _path_is_allowlisted(path_str: str) -> bool:
    """Return True if path matches an allowlist pattern (intentional placeholder)."""
    normalized = path_str.replace("\\", "/")
    return any(sub in normalized for sub in ALLOWLIST_PATH_SUBSTRINGS)


def _split_placeholders(
    placeholder_hits: dict[str, list[tuple[int, str]]],
) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[tuple[int, str]]]]:
    """Split placeholder hits into actionable vs allowlisted."""
    actionable: dict[str, list[tuple[int, str]]] = {}
    allowlisted: dict[str, list[tuple[int, str]]] = {}
    for path, hits in placeholder_hits.items():
        if _path_is_allowlisted(path):
            allowlisted[path] = hits
        else:
            actionable[path] = hits
    return actionable, allowlisted


def _find_py_files(root: Path) -> list[Path]:
    """Return sorted list of .py files under root."""
    return sorted(root.rglob("*.py"))


def check_syntax(root: Path) -> list[tuple[str, int, str]]:
    """Run ast.parse on each .py under root. Return list of (path, line, msg)."""
    errors: list[tuple[str, int, str]] = []
    for py in _find_py_files(root):
        try:
            ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            errors.append((str(py), e.lineno or 0, e.msg))
    return errors


def scan_placeholders(root: Path) -> dict[str, list[tuple[int, str]]]:
    """Scan for pass, NotImplementedError, Test fixtures placeholder. Return path -> [(line_no, line)]."""
    results: dict[str, list[tuple[int, str]]] = {}
    for py in _find_py_files(root):
        path_str = str(py)
        try:
            lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        hits: list[tuple[int, str]] = []
        for i, line in enumerate(lines, start=1):
            if PATTERN_PASS.search(line):
                hits.append((i, line.strip()[:80]))
            elif PATTERN_NOT_IMPLEMENTED.search(line):
                hits.append((i, line.strip()[:80]))
            elif PATTERN_TEST_PLACEHOLDER.search(line):
                hits.append((i, line.strip()[:80]))
        if hits:
            results[path_str] = hits
    return results


def write_report(
    output_path: Path,
    syntax_errors: list[tuple[str, int, str]],
    actionable_hits: dict[str, list[tuple[int, str]]],
    allowlisted_hits: dict[str, list[tuple[int, str]]],
    root: Path,
) -> None:
    """Write a markdown report to output_path. Actionable hits fail CI; allowlisted are excluded."""
    total_py = len(_find_py_files(root))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated Code Audit Report\n\n")
        f.write(f"**Generated root:** `{root}`\n\n")
        f.write(f"**Python files scanned:** {total_py}\n\n")
        f.write("## Syntax check (ast.parse)\n\n")
        if not syntax_errors:
            f.write("**Result:** 0 errors.\n\n")
        else:
            f.write(f"**Result:** {len(syntax_errors)} file(s) with syntax errors.\n\n")
            for path, line, msg in sorted(syntax_errors):
                f.write(f"- `{path}` line {line}: {msg}\n")
        f.write("\n## Placeholder scan\n\n")
        f.write(
            f"**Actionable:** {len(actionable_hits)} files "
            f"(allowlisted excluded: {len(allowlisted_hits)}).\n\n"
        )
        for path in sorted(actionable_hits.keys()):
            f.write(f"### {path}\n\n")
            for line_no, line in actionable_hits[path]:
                f.write(f"- L{line_no}: `{line}`\n")
            f.write("\n")
        if allowlisted_hits:
            f.write("## Allowlisted (excluded from failure)\n\n")
            f.write(
                f"**Files:** {len(allowlisted_hits)} "
                f"(paths matching `db/base.py` or `_microservice_helpers.py`).\n\n"
            )
            for path in sorted(allowlisted_hits.keys()):
                f.write(f"### {path}\n\n")
                for line_no, line in allowlisted_hits[path]:
                    f.write(f"- L{line_no}: `{line}`\n")
                f.write("\n")


def _build_llm_audit_prompt(
    root: Path,
    syntax_errors: list[tuple[str, int, str]],
    actionable_hits: dict[str, list[tuple[int, str]]],
    allowlisted_hits: dict[str, list[tuple[int, str]]],
    limit: int,
) -> str:
    """Build a compact advisory prompt from deterministic generated-code audit findings."""
    syntax_items = [
        {"file": path, "line": line, "message": msg}
        for path, line, msg in sorted(syntax_errors)[:limit]
    ]
    placeholder_items: list[dict[str, object]] = []
    for path in sorted(actionable_hits.keys()):
        for line_no, line in actionable_hits[path]:
            if len(placeholder_items) >= limit:
                break
            placeholder_items.append({"file": path, "line": line_no, "content": line})
        if len(placeholder_items) >= limit:
            break

    return "\n".join([
        "Review this deterministic generated-code audit result for Datrix.",
        "",
        "For each cluster or finding type, infer:",
        "- probable generator/template or generated area to inspect",
        "- whether placeholder is intentional, stale, or actionable",
        "- suggested next inspection path",
        "",
        "Guardrails:",
        "- Advisory only. Do not edit files.",
        "- Deterministic syntax/placeholder audit owns pass/fail.",
        "- If evidence is insufficient, say what local source should be inspected.",
        "",
        "Return markdown with a concise triage summary and prioritized next steps.",
        "",
        json.dumps(
            {
                "generated_root": str(root),
                "syntax_error_count": len(syntax_errors),
                "actionable_placeholder_file_count": len(actionable_hits),
                "allowlisted_placeholder_file_count": len(allowlisted_hits),
                "syntax_errors": syntax_items,
                "actionable_placeholders": placeholder_items,
                "allowlisted_sample": [
                    {"file": path, "hits": len(hits)}
                    for path, hits in sorted(allowlisted_hits.items())[:10]
                ],
            },
            indent=2,
        ),
    ])


def _run_llm_audit_triage(
    root: Path,
    syntax_errors: list[tuple[str, int, str]],
    actionable_hits: dict[str, list[tuple[int, str]]],
    allowlisted_hits: dict[str, list[tuple[int, str]]],
    limit: int,
    settings: LocalLlmSettings,
    num_predict: int,
    temperature: float,
) -> str:
    """Run advisory local LLM triage over generated-code audit findings."""
    prompt = _build_llm_audit_prompt(
        root,
        syntax_errors,
        actionable_hits,
        allowlisted_hits,
        limit,
    )
    request = ChatRequest(
        system="You are a Datrix generated-code audit triage assistant. You produce advisory markdown only.",
        user=prompt,
        temperature=temperature,
        max_tokens=num_predict,
    )
    return advisory_text(settings, request, "LLM audit triage")


class AuditFindings(NamedTuple):
    """What one audit of a generated tree found."""

    root: Path
    syntax_errors: list[tuple[str, int, str]]
    actionable_hits: dict[str, list[tuple[int, str]]]
    allowlisted_hits: dict[str, list[tuple[int, str]]]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/audit.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--output-base", default=DEFAULT_OUTPUT_BASE,
                        help=f"Output base directory under the workspace (default: {DEFAULT_OUTPUT_BASE}).")
    parser.add_argument("--report", help="Write a markdown report to this path (relative to the workspace).")
    parser.add_argument("--fail-on-syntax", action="store_true", help="Exit 2 if any syntax errors are found.")
    parser.add_argument("--fail-on-placeholders", action="store_true",
                        help="Exit 3 if any actionable placeholder patterns are found.")
    parser.add_argument("--llm-triage", action="store_true", help="Append advisory local LLM triage for audit findings.")
    parser.add_argument("--llm-limit", type=int, default=DEFAULT_LLM_FINDING_LIMIT,
                        help=f"Maximum findings to include in LLM triage (default: {DEFAULT_LLM_FINDING_LIMIT}).")
    parser.add_argument("--llm-num-predict", type=int, default=DEFAULT_LLM_NUM_PREDICT,
                        help=f"Max generated tokens (default: {DEFAULT_LLM_NUM_PREDICT}).")
    parser.add_argument("--llm-temperature", type=float, default=DEFAULT_LLM_TEMPERATURE,
                        help=f"Sampling temperature (default: {DEFAULT_LLM_TEMPERATURE}).")
    add_wrapper_llm_arguments(parser, timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted syntax error and placeholder are found and set "
                             "exit 2 / 3, an allowlisted placeholder is not actionable, the report is written, a "
                             "missing generated root is refused, the usage is printed with no argument, and the "
                             "wrapper seam holds.")
    parser.set_defaults(debug=False)
    return parser


def _report_path(report: str, datrix_root: Path) -> Path:
    report_path = Path(report)
    return report_path if report_path.is_absolute() else datrix_root / report_path


def _print_summary(findings: AuditFindings, total_py: int) -> None:
    placeholder_files = len(findings.actionable_hits) + len(findings.allowlisted_hits)
    print(f"Scanned: {findings.root}")
    print(f"Python files: {total_py}")
    print(f"Syntax errors: {len(findings.syntax_errors)}")
    print(f"Files with placeholder patterns: {placeholder_files} (actionable: {len(findings.actionable_hits)}, "
          f"allowlisted: {len(findings.allowlisted_hits)})")
    for path, line, msg in sorted(findings.syntax_errors)[:_SHOWN_SYNTAX_ERRORS]:
        print(f"  {path}:{line} {msg}")
    if len(findings.syntax_errors) > _SHOWN_SYNTAX_ERRORS:
        print(f"  ... and {len(findings.syntax_errors) - _SHOWN_SYNTAX_ERRORS} more")


def _llm_triage(args: argparse.Namespace, findings: AuditFindings, report_path: Path | None) -> None:
    """Append the advisory local-model triage to the report, or print it when there is none."""
    llm_text = _run_llm_audit_triage(
        findings.root,
        findings.syntax_errors,
        findings.actionable_hits,
        findings.allowlisted_hits,
        args.llm_limit,
        wrapper_llm_settings(args),
        args.llm_num_predict,
        args.llm_temperature,
    )
    llm_section = (
        "\n\n---\n\n## Local LLM Advisory Audit Triage\n\n"
        "This section is advisory only. Deterministic syntax and placeholder checks own pass/fail.\n\n"
        + llm_text
        + "\n"
    )
    if report_path is None:
        print(llm_section)
        return
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(llm_section)


def audit(args: argparse.Namespace, datrix_root: Path) -> int:
    """Audit ``<output-base>/python/docker`` under *datrix_root*: 0, 1 missing root, 2 syntax, 3 placeholders."""
    root = datrix_root / args.output_base / GENERATED_SUBPATH.replace("/", os.sep)
    if not root.is_dir():
        print(f"ERROR: Generated root not found: {root}", file=sys.stderr)
        return 1

    actionable_hits, allowlisted_hits = _split_placeholders(scan_placeholders(root))
    findings = AuditFindings(root, check_syntax(root), actionable_hits, allowlisted_hits)
    _print_summary(findings, len(_find_py_files(root)))

    report_path = _report_path(args.report, datrix_root) if args.report else None
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report_path, findings.syntax_errors, actionable_hits, allowlisted_hits, root)
        print(f"Report written: {report_path}")
    if args.llm_triage:
        _llm_triage(args, findings, report_path)

    if args.fail_on_syntax and findings.syntax_errors:
        return 2
    if args.fail_on_placeholders and actionable_hits:
        return 3
    return 0


def run_audit(args: argparse.Namespace, datrix_root: Path) -> int:
    """``audit``, then the report's full path whenever ``--report`` was given (as the wrapper always printed it)."""
    code = audit(args, datrix_root)
    if args.report:
        print(f"Report written to: {_report_path(args.report, datrix_root)}")
    return code


def _planted_audit(extra: Sequence[str]) -> tuple[int, str]:
    """``run_audit`` over a planted generated tree with *extra* options: the exit code and its output."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "generated"
        write_files(base / GENERATED_SUBPATH, {
            "svc/broken.py": "def f(:\n",
            "svc/stub.py": "def g() -> None:\n    pass\n",
            "svc/db/base.py": "class Base:\n    pass\n",
            "svc/clean.py": "VALUE = 1\n",
        })
        args = build_parser().parse_args([f"--output-base={base}", *extra])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = run_audit(args, Path(tmp))
        return code, out.getvalue()


def _check_a_syntax_error_fails_on_syntax() -> None:
    code, out = _planted_audit(["--fail-on-syntax", "--fail-on-placeholders"])
    assert code == 2 and "Syntax errors: 1" in out and "broken.py:1" in out, f"got {code}: {out!r}"


def _check_an_actionable_placeholder_fails_on_placeholders() -> None:
    code, out = _planted_audit(["--fail-on-placeholders"])
    assert code == 3 and "(actionable: 1, allowlisted: 1)" in out, f"got {code}: {out!r}"


def _check_the_report_is_written() -> None:
    code, out = _planted_audit(["--report=audit.md"])
    assert code == 0 and "Report written:" in out and "Report written to:" in out, f"got {code}: {out!r}"


def _check_a_missing_root_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err:
        code = audit(build_parser().parse_args(["--output-base=nothing-here"]), Path(tmp))
    assert code == 1 and "Generated root not found" in err.getvalue(), f"got {code}: {err.getvalue()!r}"


def _check_no_argument_prints_the_usage() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main([])
    assert code == 1 and out.getvalue().strip() == _USAGE, f"got {code}: {out.getvalue()!r}"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_a_syntax_error_fails_on_syntax,
            _check_an_actionable_placeholder_fails_on_placeholders,
            _check_the_report_is_written,
            _check_a_missing_root_is_refused,
            _check_no_argument_prints_the_usage,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    return run_audit(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: with no argument at all, the usage (exit 1), as the wrapper printed it."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(_USAGE)
        return 1
    return module_main(build_parser(), _run, arguments)


if __name__ == "__main__":
    sys.exit(main())
