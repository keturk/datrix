#!/usr/bin/env python3
"""Lint documentation for common drift patterns.

Checks Datrix monorepo docs for:
 1. Deprecated CLI flags in examples
 2. Fixed phase-count language
 3. CDX design doc filename validation
 4. CDX design doc structure validation
 5. Missing capability status labels

Usage:
  python scripts/library/dev/check_docs.py [docs_dirs ...]
  .\\scripts\\dev\\check-docs.ps1
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# ── UTF-8 for Windows ──
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


def _sigint_handler(_signum: int, _frame: object) -> None:
    sys.exit(130)


signal.signal(signal.SIGINT, _sigint_handler)

# ── sys.path setup ──
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402
from shared.logging_utils import ColorCodes, colorize  # noqa: E402

logger = logging.getLogger(__name__)

# ── Named constants ──

# Valid short CLI flags (uppercase or lowercase that actually exist).
VALID_SHORT_FLAGS: frozenset[str] = frozenset(
    {"-s", "-o", "-L", "-H", "-P", "-V", "-S", "-v", "-w", "-n"}
)

# Deprecated lowercase short flags that don't exist in the CLI.
# These are the ones we want to flag when they appear as generation examples.
DEPRECATED_FLAG_PATTERN: re.Pattern[str] = re.compile(
    r"""
    (?:^|\s)                   # start of line or whitespace
    (-[lp])                    # capture -l or -p (deprecated lowercase flags)
    (?:\s|$|[=])               # followed by space, end of line, or =
    """,
    re.VERBOSE,
)

# Heuristic indicators that a line is a CLI example.
_CLI_EXAMPLE_INDICATORS: tuple[str, ...] = (
    "generate",
    "datrix",
    ".ps1",
    ".sh",
    "python",
    "powershell",
    "run-complete",
)

# Fixed phase-count references (e.g., "6-phase", "7-phase").
FIXED_PHASE_COUNT_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d+)-phase\b", re.IGNORECASE
)

# CDX design doc filename pattern: CDX-{NN}-{slug}.md
CDX_FILENAME_PATTERN: re.Pattern[str] = re.compile(
    r"^CDX-(\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)

# Required sections in CDX design docs.
CDX_REQUIRED_SECTIONS: tuple[str, ...] = (
    "Status",
    "Summary",
    "Goals",
    "Implementation",  # matches "Implementation Options" or "Implementation"
    "Verification",
)

# Valid capability status labels.
CAPABILITY_STATUS_LABELS: frozenset[str] = frozenset(
    {"Stable", "Beta", "Experimental", "Planned", "Illustrative", "Deprecated"}
)

# Capability section header pattern — matches ### headers in
# pipeline-and-capabilities.md that describe capability groups.
CAPABILITY_SECTION_PATTERN: re.Pattern[str] = re.compile(
    r"^###\s+(.+)$"
)

# Directories to skip during file discovery.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".generated",
        ".generated_old",
        ".test_results",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

PIPELINE_AND_CAPABILITIES_FILENAME = "pipeline-and-capabilities.md"

# ── Callable type aliases for check registry ──

DocsCheckFn = Callable[[list[Path], "LintResult"], None]
DesignCheckFn = Callable[[Path, "LintResult"], None]


@dataclass
class LintFinding:
    """A single docs lint finding."""

    check_name: str
    file_path: Path
    line_number: int
    content: str
    suggestion: str


@dataclass
class LintResult:
    """Aggregated lint results."""

    findings: list[LintFinding] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return len(self.findings) > 0

    def add(
        self,
        check_name: str,
        file_path: Path,
        line_number: int,
        content: str,
        suggestion: str,
    ) -> None:
        self.findings.append(
            LintFinding(
                check_name=check_name,
                file_path=file_path,
                line_number=line_number,
                content=content.rstrip(),
                suggestion=suggestion,
            )
        )


# ── Check implementations ──


def _collect_markdown_files(dirs: list[Path]) -> list[Path]:
    """Collect all .md files under the given directories, skipping excluded dirs."""
    md_files: list[Path] = []
    for base_dir in dirs:
        if not base_dir.is_dir():
            logger.warning("Directory does not exist, skipping: %s", base_dir)
            continue
        for dir_path, dir_names, file_names in os.walk(base_dir, followlinks=False):
            # Prune excluded directories in-place
            dir_names[:] = [
                d for d in dir_names if d not in SKIP_DIRS
            ]
            root_path = Path(dir_path)
            for fname in file_names:
                if fname.endswith(".md"):
                    md_files.append(root_path / fname)
    return sorted(md_files)


def check_deprecated_cli_flags(
    docs_dirs: list[Path], result: LintResult
) -> None:
    """Check 1: Search docs for deprecated -l, -p generation examples."""
    md_files = _collect_markdown_files(docs_dirs)
    for md_file in md_files:
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", md_file, exc)
            continue

        for line_num, line in enumerate(lines, start=1):
            match = DEPRECATED_FLAG_PATTERN.search(line)
            if match:
                flag = match.group(1)
                if _looks_like_cli_example(line):
                    result.add(
                        check_name="deprecated-cli-flag",
                        file_path=md_file,
                        line_number=line_num,
                        content=line,
                        suggestion=(
                            f"Flag '{flag}' is deprecated. "
                            f"Valid short flags: {', '.join(sorted(VALID_SHORT_FLAGS))}"
                        ),
                    )


def _looks_like_cli_example(line: str) -> bool:
    """Heuristic: does this line look like a CLI invocation or script example?"""
    lower = line.strip().lower()
    return any(indicator in lower for indicator in _CLI_EXAMPLE_INDICATORS)


def check_fixed_phase_count(
    docs_dirs: list[Path], result: LintResult
) -> None:
    """Check 2: Search for 'N-phase' fixed-count references."""
    md_files = _collect_markdown_files(docs_dirs)
    for md_file in md_files:
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", md_file, exc)
            continue

        for line_num, line in enumerate(lines, start=1):
            match = FIXED_PHASE_COUNT_PATTERN.search(line)
            if match:
                count = match.group(1)
                result.add(
                    check_name="fixed-phase-count",
                    file_path=md_file,
                    line_number=line_num,
                    content=line,
                    suggestion=(
                        f"Fixed '{count}-phase' reference found. "
                        "Semantic analysis phase count may change; "
                        "avoid hardcoding the number of phases."
                    ),
                )


def check_cdx_filenames(
    design_dir: Path, result: LintResult
) -> None:
    """Check 3: Validate CDX design doc filenames follow CDX-{NN}-{slug}.md."""
    if not design_dir.is_dir():
        logger.warning(
            "Design directory does not exist, skipping CDX filename check: %s",
            design_dir,
        )
        return

    for entry in sorted(design_dir.iterdir()):
        if not entry.is_file():
            continue
        name = entry.name
        # Only check files that start with "CDX"
        if not name.startswith("CDX"):
            continue
        if not CDX_FILENAME_PATTERN.match(name):
            result.add(
                check_name="cdx-filename",
                file_path=entry,
                line_number=0,
                content=name,
                suggestion=(
                    "CDX design doc filename must match pattern "
                    "'CDX-{NN}-{slug}.md' (e.g., CDX-04-docs-sync.md). "
                    "Slug should be lowercase with hyphens."
                ),
            )


def check_cdx_structure(
    design_dir: Path, result: LintResult
) -> None:
    """Check 4: Each CDX doc must have required sections."""
    if not design_dir.is_dir():
        logger.warning(
            "Design directory does not exist, skipping CDX structure check: %s",
            design_dir,
        )
        return

    for entry in sorted(design_dir.iterdir()):
        if not entry.is_file() or not entry.name.startswith("CDX"):
            continue
        if not entry.name.endswith(".md"):
            continue

        try:
            content = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", entry, exc)
            continue

        # Extract section headers (## level)
        headers = _extract_section_headers(content)
        header_text_lower = [h.lower() for h in headers]

        for required in CDX_REQUIRED_SECTIONS:
            required_lower = required.lower()
            # "Implementation" matches "Implementation Options" or "Implementation"
            found = any(
                h.startswith(required_lower) for h in header_text_lower
            )
            if not found:
                # Check for top-level "Status:" line (not a ## header)
                if required_lower == "status" and _has_status_line(content):
                    continue

                result.add(
                    check_name="cdx-structure",
                    file_path=entry,
                    line_number=0,
                    content=f"Missing section: {required}",
                    suggestion=(
                        f"CDX design docs must include a '{required}' section. "
                        f"Required sections: {', '.join(CDX_REQUIRED_SECTIONS)}"
                    ),
                )


def _extract_section_headers(content: str) -> list[str]:
    """Extract ## level section header texts from markdown content."""
    headers: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            header_text = stripped[3:].strip()
            headers.append(header_text)
    return headers


def _has_status_line(content: str) -> bool:
    """Check if the content has a top-level 'Status: ...' line."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("status:"):
            return True
    return False


def check_capability_status_labels(
    docs_dirs: list[Path], result: LintResult
) -> None:
    """Check 5: Check capability sections for presence of status labels."""
    target_files: list[Path] = []
    for docs_dir in docs_dirs:
        if not docs_dir.is_dir():
            continue
        for dir_path, dir_names, file_names in os.walk(docs_dir, followlinks=False):
            dir_names[:] = [d for d in dir_names if d not in SKIP_DIRS]
            for fname in file_names:
                if fname == PIPELINE_AND_CAPABILITIES_FILENAME:
                    target_files.append(Path(dir_path) / fname)

    if not target_files:
        logger.info(
            "No %s found in docs directories, skipping capability status check",
            PIPELINE_AND_CAPABILITIES_FILENAME,
        )
        return

    for target_file in target_files:
        _check_single_capabilities_file(target_file, result)


def _check_single_capabilities_file(
    file_path: Path, result: LintResult
) -> None:
    """Check a single pipeline-and-capabilities.md for status labels."""
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Cannot read %s: %s", file_path, exc)
        return

    # Collect ### section headers with their positions.
    capability_sections: list[tuple[int, str, int]] = []

    for idx, line in enumerate(lines):
        match = CAPABILITY_SECTION_PATTERN.match(line)
        if match:
            title = match.group(1).strip()
            capability_sections.append((idx + 1, title, idx))

    for i, (line_num, title, start_idx) in enumerate(capability_sections):
        # Check title for inline status label, e.g. "### Search engine (Stable)"
        if _title_has_status_label(title):
            continue

        # Section body extends from the header to the next ### header or EOF.
        if i + 1 < len(capability_sections):
            end_idx = capability_sections[i + 1][2]
        else:
            end_idx = len(lines)

        section_body = "\n".join(lines[start_idx + 1 : end_idx])

        if not _section_has_status_label(section_body):
            result.add(
                check_name="capability-status-label",
                file_path=file_path,
                line_number=line_num,
                content=f"### {title}",
                suggestion=(
                    "Capability section is missing a status label. "
                    "Add one of: "
                    + ", ".join(sorted(CAPABILITY_STATUS_LABELS))
                ),
            )


def _title_has_status_label(title: str) -> bool:
    """Check if a section title contains an inline status label like '(Stable)'."""
    for label in CAPABILITY_STATUS_LABELS:
        if re.search(rf"\({re.escape(label)}\)", title):
            return True
    return False


def _section_has_status_label(section_body: str) -> bool:
    """Check if a section body contains a capability status declaration."""
    for label in CAPABILITY_STATUS_LABELS:
        if re.search(rf"\bStatus:\s*{re.escape(label)}\b", section_body):
            return True
    return False


# ── Check registry ──

DOCS_DIR_CHECKS: dict[str, DocsCheckFn] = {
    "deprecated-cli-flags": check_deprecated_cli_flags,
    "fixed-phase-count": check_fixed_phase_count,
    "capability-status-labels": check_capability_status_labels,
}

DESIGN_DIR_CHECKS: dict[str, DesignCheckFn] = {
    "cdx-filenames": check_cdx_filenames,
    "cdx-structure": check_cdx_structure,
}

AVAILABLE_CHECK_NAMES: frozenset[str] = frozenset(
    list(DOCS_DIR_CHECKS.keys()) + list(DESIGN_DIR_CHECKS.keys())
)


# ── Output formatting ──


def _print_findings(result: LintResult, verbose: bool) -> None:
    """Print lint findings in a structured format."""
    if not result.findings:
        print(colorize("All docs lint checks passed.", ColorCodes.GREEN))
        return

    # Group by check name
    by_check: dict[str, list[LintFinding]] = {}
    for finding in result.findings:
        by_check.setdefault(finding.check_name, []).append(finding)

    total = len(result.findings)
    print(
        colorize(
            f"Found {total} docs lint issue{'s' if total != 1 else ''}:",
            ColorCodes.RED,
        )
    )
    print()

    for check_name, findings in sorted(by_check.items()):
        print(
            colorize(
                f"  [{check_name}] ({len(findings)} issue{'s' if len(findings) != 1 else ''})",
                ColorCodes.YELLOW,
            )
        )
        for finding in findings:
            line_info = (
                f":{finding.line_number}" if finding.line_number > 0 else ""
            )
            print(f"    {finding.file_path}{line_info}")
            if verbose:
                print(f"      Content:    {finding.content}")
                print(f"      Suggestion: {finding.suggestion}")
        print()


# ── Main ──


def main() -> int:
    """Entry point for check-docs lint script."""
    parser = argparse.ArgumentParser(
        description="Lint documentation for common drift patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available checks:\n"
            "  deprecated-cli-flags       Deprecated -l, -p flag examples\n"
            "  fixed-phase-count          Fixed N-phase references\n"
            "  cdx-filenames              CDX-{NN}-{slug}.md naming\n"
            "  cdx-structure              CDX required section structure\n"
            "  capability-status-labels   Missing status labels in capabilities\n"
        ),
    )
    parser.add_argument(
        "docs_dirs",
        nargs="*",
        help=(
            "Documentation directories to scan. "
            "Defaults to all docs/ directories in the monorepo."
        ),
    )
    parser.add_argument(
        "--check",
        action="append",
        dest="checks",
        choices=sorted(AVAILABLE_CHECK_NAMES),
        help="Run only the specified check(s). Can be repeated.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output including content and suggestions.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    datrix_root = get_datrix_root()

    # Resolve docs directories
    if args.docs_dirs:
        docs_dirs = [Path(d).resolve() for d in args.docs_dirs]
    else:
        docs_dirs = _discover_docs_dirs(datrix_root)

    # Resolve design directory
    design_dir = datrix_root / "design"

    # Determine which checks to run
    checks_to_run: list[str]
    if args.checks:
        checks_to_run = args.checks
    else:
        checks_to_run = sorted(AVAILABLE_CHECK_NAMES)

    logger.debug("Datrix root: %s", datrix_root)
    logger.debug("Docs dirs: %s", docs_dirs)
    logger.debug("Design dir: %s", design_dir)
    logger.debug("Checks: %s", checks_to_run)

    result = LintResult()

    for check_name in checks_to_run:
        logger.debug("Running check: %s", check_name)
        if check_name in DOCS_DIR_CHECKS:
            DOCS_DIR_CHECKS[check_name](docs_dirs, result)
        elif check_name in DESIGN_DIR_CHECKS:
            DESIGN_DIR_CHECKS[check_name](design_dir, result)

    _print_findings(result, verbose=args.verbose)

    return 1 if result.has_failures else 0


def _discover_docs_dirs(datrix_root: Path) -> list[Path]:
    """Discover all docs/ directories in the monorepo."""
    root = datrix_root
    docs_dirs: list[Path] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name in SKIP_DIRS:
            continue
        docs_path = entry / "docs"
        if docs_path.is_dir():
            docs_dirs.append(docs_path)

    if not docs_dirs:
        logger.warning("No docs/ directories found under %s", datrix_root)

    return docs_dirs


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
