#!/usr/bin/env python3
"""Detect leftover debug/logging artifacts in source code.

Scans Python and TypeScript source files for common debug patterns that should
not be committed: print(), console.log(), breakpoint(), debugger statements,
and temporary markers.

Python files are scanned STRING-LITERAL-AWARE: a pattern that matches inside a
string literal is not code and is never reported. Without this, any test that
embeds a child-process script as a triple-quoted source string is flagged for
every `print(` that script uses to report its result back over stdout -- a
false positive that cannot be resolved by editing the test, because writing to
stdout is the child process's only channel to its parent.

TypeScript files stay line-based: a correct TS lexer is not available here, and
inventing a partial one would trade these false positives for wrong answers.
The equivalent TS case (a `console.log` inside a template literal) is therefore
still reported; fix that by teaching this scanner a real TS lexer, never by
loosening the regexes.

A self-test proving both directions -- a real artifact is still detected, and
the same artifact inside a string literal is not -- runs as step 1 of every
invocation, so the scanner can never silently degrade into a vacuous check.

Usage:
  python scripts/library/dev/check_debug_artifacts.py [path ...] [--strict] [--debug]
  python scripts/library/dev/check_debug_artifacts.py --self-test
  .\\scripts\\dev\\check-debug-artifacts.ps1 -All
"""

import argparse
import io
import os
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402

# Directories to skip during file discovery
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache", ".generated", ".test_results",
})


class Finding(NamedTuple):
    """A single debug artifact finding."""

    file_path: Path
    line_number: int
    label: str
    severity: str
    content: str


@dataclass
class PatternDef:
    """Definition of a debug pattern to scan for."""

    regex: re.Pattern[str]
    label: str
    severity: str


# ── Pattern definitions ─────────────────────────────────────────────────────

_PYTHON_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r"^\s*print\("), "print()", "HIGH"),
    PatternDef(re.compile(r"^\s*breakpoint\(\)"), "breakpoint()", "CRITICAL"),
    PatternDef(re.compile(r"^\s*import\s+pdb"), "import pdb", "CRITICAL"),
    PatternDef(re.compile(r"^\s*pdb\.set_trace\(\)"), "pdb.set_trace()", "CRITICAL"),
    PatternDef(re.compile(r"^\s*import\s+ipdb"), "import ipdb", "CRITICAL"),
    PatternDef(re.compile(r"logger\.(warning|error)\(.*DEBUG", re.IGNORECASE), "debug-labeled logger", "HIGH"),
    PatternDef(re.compile(r"logger\.(warning|error)\(.*TEMP", re.IGNORECASE), "temp-labeled logger", "HIGH"),
    PatternDef(re.compile(r"#\s*DEBUG"), "# DEBUG comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*TEMP"), "# TEMP comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*HACK"), "# HACK comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*XXX"), "# XXX comment", "MEDIUM"),
]

_PYTHON_STRICT_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r'logger\.(debug|info)\(f["\']'), "logger with f-string (likely temp)", "LOW"),
]

_TYPESCRIPT_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r"^\s*console\.(log|warn|error|debug)\("), "console.log()", "HIGH"),
    PatternDef(re.compile(r"^\s*debugger\b"), "debugger statement", "CRITICAL"),
    PatternDef(re.compile(r"//\s*DEBUG"), "// DEBUG comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*TEMP"), "// TEMP comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*HACK"), "// HACK comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*XXX"), "// XXX comment", "MEDIUM"),
]


#: Token types whose text is string-literal content rather than code. The
#: f-string trio exists only on Python 3.12+, where an f-string is tokenized as
#: START/MIDDLE/END around its interpolations; the interpolated expressions are
#: emitted as ordinary code tokens and so are correctly NOT covered here -- a
#: `print(` inside an f-string's `{...}` really is code and stays reported.
_STRING_TOKEN_TYPES: frozenset[int] = frozenset(
    {tokenize.STRING}
    | {
        token_type
        for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
        if (token_type := getattr(tokenize, name, None)) is not None
    }
)


def string_literal_spans(source: str) -> dict[int, list[tuple[int, int]]]:
    """Map each 1-based line number to the column spans covered by string literals.

    A multi-line string contributes a span to every line it covers: from its
    opening column to end-of-line on the first line, the whole of each interior
    line, and up to its closing column on the last line. This keeps the first
    line's real code (e.g. ``source = textwrap.dedent(\"\"\"\\``) scannable while
    treating the embedded body as the string content it is.

    Args:
        source: Full Python source text.

    Returns:
        ``{line_number: [(start_col, end_col), ...]}`` -- half-open column spans.

    Raises:
        tokenize.TokenError: The source cannot be tokenized (unterminated
            construct); callers handle this per file rather than aborting.
        SyntaxError: The source is not lexically valid Python.
    """
    spans: dict[int, list[tuple[int, int]]] = {}
    lines = source.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in _STRING_TOKEN_TYPES:
            continue
        start_row, start_col = token.start
        end_row, end_col = token.end
        for row in range(start_row, end_row + 1):
            first_col = start_col if row == start_row else 0
            if row == end_row:
                last_col = end_col
            else:
                last_col = len(lines[row - 1]) if row <= len(lines) else first_col
            spans.setdefault(row, []).append((first_col, last_col))
    return spans


def _spans_or_warn(source: str, file_path: Path) -> dict[int, list[tuple[int, int]]]:
    """Compute string spans for *source*, warning loudly if it cannot be tokenized.

    A file this scanner cannot tokenize is not valid Python, which is a finding
    of its own kind -- it is reported on stderr and then scanned line-based, so
    the scan never silently skips a file and never under-reports.
    """
    try:
        return string_literal_spans(source)
    except (tokenize.TokenError, SyntaxError) as exc:
        print(
            f"WARNING: {file_path}: could not tokenize ({exc}); scanning "
            "line-based -- matches inside string literals may be reported.",
            file=sys.stderr,
        )
        return {}


def _match_is_inside_string(column: int, spans: list[tuple[int, int]]) -> bool:
    """Return True when *column* on this line falls inside a string literal."""
    return any(start <= column < end for start, end in spans)


def find_source_files(
    root: Path,
    skip_dirs: frozenset[str],
    extensions: tuple[str, ...],
) -> list[Path]:
    """Recursively find source files under root, excluding skip_dirs."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dir_path, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(extensions):
                out.append(Path(dir_path) / name)
    return sorted(out)


def scan_source(
    source: str,
    patterns: list[PatternDef],
    file_path: Path,
    *,
    string_aware: bool,
) -> list[Finding]:
    """Scan source text for debug patterns, attributing findings to *file_path*.

    Args:
        source: The full source text to scan.
        patterns: Patterns to apply, in priority order.
        file_path: Path recorded on each finding (and named in any warning).
        string_aware: When True, a match whose start column lies inside a string
            literal is skipped -- that text is data, not code. Only meaningful
            for Python source; the caller decides by file type.

    Returns:
        At most one finding per line: the first pattern that matches OUTSIDE a
        string literal. A pattern matching inside one does not consume the line,
        so a genuine artifact later on the same line is still reported.
    """
    lines = source.splitlines()
    spans = _spans_or_warn(source, file_path) if string_aware else {}
    findings: list[Finding] = []
    for index, line in enumerate(lines):
        line_spans = spans.get(index + 1, [])
        for pattern in patterns:
            match = pattern.regex.search(line)
            if match is None:
                continue
            if _match_is_inside_string(match.start(), line_spans):
                continue
            findings.append(Finding(
                file_path=file_path,
                line_number=index + 1,
                label=pattern.label,
                severity=pattern.severity,
                content=line.strip(),
            ))
            break  # One finding per line
    return findings


def scan_file(
    file_path: Path,
    patterns: list[PatternDef],
    debug: bool,
    *,
    string_aware: bool = False,
) -> list[Finding]:
    """Read and scan a single file for debug patterns."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if debug:
        print(f"[DEBUG] Scanning: {file_path}", file=sys.stderr)

    return scan_source(source, patterns, file_path, string_aware=string_aware)


def scan_project(
    project_path: Path,
    strict: bool,
    include_generated: bool,
    debug: bool,
) -> list[Finding]:
    """Scan a project for debug artifacts in all source files."""
    findings: list[Finding] = []
    skip = set(_SKIP_DIRS)
    if not include_generated:
        skip.add(".generated")

    # Scan src/ and tests/ directories
    scan_dirs: list[Path] = []
    src_dir = project_path / "src"
    tests_dir = project_path / "tests"
    if src_dir.is_dir():
        scan_dirs.append(src_dir)
    if tests_dir.is_dir():
        scan_dirs.append(tests_dir)

    if not scan_dirs:
        if debug:
            print(f"[DEBUG] Skipping {project_path.name} (no src/ or tests/)", file=sys.stderr)
        return findings

    for scan_dir in scan_dirs:
        # Python files
        py_patterns = _PYTHON_PATTERNS + (_PYTHON_STRICT_PATTERNS if strict else [])
        py_files = find_source_files(scan_dir, frozenset(skip), (".py",))
        for f in py_files:
            findings.extend(scan_file(f, py_patterns, debug, string_aware=True))

        # TypeScript files
        ts_files = find_source_files(scan_dir, frozenset(skip), (".ts",))
        for f in ts_files:
            findings.extend(scan_file(f, _TYPESCRIPT_PATTERNS, debug))

    return findings


#: Source fixture reproducing the exact false positive this scanner exists to
#: avoid: a test that embeds a child-process checker script as a triple-quoted
#: string, where the child's `print(` is its only way to report a result back.
#: Line 1 is a real artifact; the `print(`/`breakpoint()` inside the string are
#: not code. `_SELF_TEST_REAL_ARTIFACT_LINES` names the lines that must be
#: reported, so the fixture and its expectation cannot drift apart silently.
_SELF_TEST_SOURCE = '''print("a real leftover debug print")
checker_source = """
print("child reports its result over stdout")
breakpoint()
"""
value = f"{compute(print)} and {'print(' } literals"
print(f"a second real one")
'''

_SELF_TEST_REAL_ARTIFACT_LINES: frozenset[int] = frozenset({1, 7})


def run_self_test() -> bool:
    """Prove the scanner detects real artifacts and ignores string-literal text.

    Three checks, the third of which is the non-vacuity proof:

    1. String-aware scanning reports exactly the real artifacts.
    2. Every line inside the embedded script string is silent.
    3. WITHOUT string-awareness the embedded lines DO match -- so check 1 passes
       because the span logic works, not because the patterns stopped matching.

    Returns:
        True when every check passes.
    """
    fixture = Path("<self-test>")
    ok = True

    aware = scan_source(
        _SELF_TEST_SOURCE, _PYTHON_PATTERNS, fixture, string_aware=True
    )
    aware_lines = {f.line_number for f in aware}
    if aware_lines == _SELF_TEST_REAL_ARTIFACT_LINES:
        print("[OK] real debug artifacts detected (string-aware)")
    else:
        ok = False
        print(
            f"[FAIL] string-aware scan reported lines {sorted(aware_lines)}, "
            f"expected {sorted(_SELF_TEST_REAL_ARTIFACT_LINES)}"
        )

    embedded_lines = {3, 4}
    leaked = embedded_lines & aware_lines
    if not leaked:
        print("[OK] artifacts inside a string literal are not reported")
    else:
        ok = False
        print(f"[FAIL] string-literal content reported as code on lines {sorted(leaked)}")

    naive = scan_source(
        _SELF_TEST_SOURCE, _PYTHON_PATTERNS, fixture, string_aware=False
    )
    naive_lines = {f.line_number for f in naive}
    if embedded_lines <= naive_lines:
        print("[OK] non-vacuity: the same lines DO match without string-awareness")
    else:
        ok = False
        print(
            "[FAIL] non-vacuity: line-based scan did not match the embedded "
            f"lines {sorted(embedded_lines)} (got {sorted(naive_lines)}) -- the "
            "string-aware check above proves nothing"
        )

    return ok


def severity_rank(severity: str) -> int:
    """Return sort rank for severity (lower = more severe)."""
    ranks = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return ranks.get(severity, 4)


def report_findings(
    findings_by_project: dict[str, list[Finding]],
    workspace_root: Path,
    debug: bool,
) -> None:
    """Print findings report to stdout."""
    total = sum(len(f) for f in findings_by_project.values())

    print()
    print(f"DEBUG ARTIFACTS DETECTED: {total} finding(s)")
    print("=" * 60)
    print()

    for project_name in sorted(findings_by_project.keys()):
        findings = findings_by_project[project_name]
        print(f"  {project_name} ({len(findings)} findings)")

        sorted_findings = sorted(findings, key=lambda f: severity_rank(f.severity))
        for finding in sorted_findings:
            rel_path = str(finding.file_path).replace(str(workspace_root), "").lstrip("\\/")
            print(f"    [{finding.severity}] {rel_path}:{finding.line_number} — {finding.label}")
            if debug:
                print(f"           {finding.content}")
        print()

    print(f"Summary: {total} artifact(s) across {len(findings_by_project)} project(s)")
    if not debug:
        print("Run with --debug to see matching line content.")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect leftover debug/logging artifacts in source code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=str,
        help="Project directory paths to scan",
    )
    parser.add_argument("--strict", action="store_true", help="Also flag f-string logger calls")
    parser.add_argument("--include-generated", action="store_true", help="Include .generated/ directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the detection/false-positive self-test and exit",
    )

    args = parser.parse_args()

    # Step 1 of every invocation: a scanner that has silently stopped detecting
    # is worse than no scanner, so prove it works before reporting any result.
    if not run_self_test():
        print("ERROR: self-test failed — scanner results are not trustworthy", file=sys.stderr)
        return 2
    if args.self_test:
        return 0

    if not args.paths:
        print("ERROR: No paths provided", file=sys.stderr)
        return 2

    try:
        workspace_root = get_datrix_root()
    except FileNotFoundError:
        workspace_root = Path(args.paths[0]).parent

    findings_by_project: dict[str, list[Finding]] = {}

    for path_str in args.paths:
        project_path = Path(path_str)
        if not project_path.is_dir():
            print(f"WARNING: Not a directory: {project_path}", file=sys.stderr)
            continue

        project_name = project_path.name
        findings = scan_project(
            project_path,
            strict=args.strict,
            include_generated=args.include_generated,
            debug=args.debug,
        )

        if findings:
            findings_by_project[project_name] = findings

    if not findings_by_project:
        print("No debug artifacts found.")
        return 0

    report_findings(findings_by_project, workspace_root, args.debug)
    return 1


if __name__ == "__main__":
    sys.exit(main())
