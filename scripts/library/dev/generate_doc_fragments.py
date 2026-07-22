#!/usr/bin/env python3
"""Generate documentation fragments from source code.

Extracts documentation from source-of-truth code locations and writes
markdown fragment files. Two fragment types are supported:

1. **semantic-pipeline** — Ordered list of semantic analyzer phases,
   extracted from SemanticAnalyzer.analyze() via AST parsing.
2. **cli-help** — Full `datrix generate --help` output captured via
   subprocess invocation.

Fragments are written to ``datrix/docs/generated/`` with auto-generated
markers so humans know not to edit them manually.

Usage::

    python generate_doc_fragments.py                    # generate all
    python generate_doc_fragments.py --fragment all     # same
    python generate_doc_fragments.py --fragment semantic-pipeline
    python generate_doc_fragments.py --fragment cli-help
    python generate_doc_fragments.py --check            # verify mode (non-zero if stale)
    python generate_doc_fragments.py --verbose          # debug output
"""

from __future__ import annotations

import argparse
import ast
import io
import logging
import signal
import subprocess
import sys
from pathlib import Path

# ── UTF-8 for Windows ──
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _sigint_handler(_signum: int, _frame: object) -> None:
    sys.exit(130)


signal.signal(signal.SIGINT, _sigint_handler)

# ── sys.path setup ──
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.logging_utils import ColorCodes, colorize  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ──
VALID_FRAGMENTS = frozenset({"semantic-pipeline", "cli-help", "all"})
ANALYZER_RELATIVE_PATH = Path(
    "datrix-common/src/datrix_common/semantic/analyzer.py"
)
OUTPUT_DIR_NAME = Path("datrix/docs/generated")
SEMANTIC_OUTPUT_FILENAME = "semantic-pipeline-stages.md"
CLI_HELP_OUTPUT_FILENAME = "cli-generate-help.md"


# ---------------------------------------------------------------------------
# Fragment 1: Semantic pipeline stage list
# ---------------------------------------------------------------------------


def _function_name_to_label(name: str) -> str:
    """Convert a snake_case function name to a human-readable label.

    Replaces underscores with spaces and capitalizes the first letter.

    Args:
        name: Snake-case function name (e.g. ``register_stdlib_symbols``).

    Returns:
        Human-readable label (e.g. ``Register stdlib symbols``).
    """
    label = name.replace("_", " ")
    return label[0].upper() + label[1:]


def _extract_phase_names(analyzer_source: str) -> list[str]:
    """Extract ordered phase function names from SemanticAnalyzer.analyze().

    Parses the Python source using the ``ast`` module, locates the
    ``SemanticAnalyzer`` class and its ``analyze`` method, then collects
    all top-level function-call statements in the method body. The last
    statement (the ``return``) is excluded.

    Args:
        analyzer_source: Full source text of ``analyzer.py``.

    Returns:
        Ordered list of function names called as phases.

    Raises:
        ValueError: If the expected class or method cannot be found, or
            if no phase calls are detected.
    """
    tree = ast.parse(analyzer_source)

    analyzer_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SemanticAnalyzer":
            analyzer_class = node
            break

    if analyzer_class is None:
        raise ValueError(
            "Could not find class 'SemanticAnalyzer' in analyzer.py. "
            "Has the class been renamed or moved?"
        )

    analyze_method: ast.FunctionDef | None = None
    for item in analyzer_class.body:
        if isinstance(item, ast.FunctionDef) and item.name == "analyze":
            analyze_method = item
            break

    if analyze_method is None:
        raise ValueError(
            "Could not find method 'analyze' in SemanticAnalyzer. "
            "Has the method been renamed?"
        )

    phase_names: list[str] = []
    for stmt in analyze_method.body:
        # Skip non-expression statements (assignments, returns, docstrings)
        if not isinstance(stmt, ast.Expr):
            continue
        # Must be a function call
        if not isinstance(stmt.value, ast.Call):
            continue

        call = stmt.value
        func_name: str | None = None

        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr

        if func_name is not None:
            phase_names.append(func_name)

    if not phase_names:
        raise ValueError(
            "No phase function calls found in SemanticAnalyzer.analyze(). "
            "The method body may have changed structure."
        )

    return phase_names


def _build_semantic_fragment(phase_names: list[str]) -> str:
    """Build the markdown fragment for semantic pipeline stages.

    Args:
        phase_names: Ordered list of phase function names.

    Returns:
        Complete markdown fragment with auto-generated markers.
    """
    lines: list[str] = []
    lines.append(
        "<!-- AUTO-GENERATED from SemanticAnalyzer.analyze() "
        "— do not edit manually -->"
    )
    lines.append(
        f"The semantic analyzer runs an ordered pipeline "
        f"of {len(phase_names)} phases:"
    )
    lines.append("")

    for i, name in enumerate(phase_names, start=1):
        label = _function_name_to_label(name)
        lines.append(f"{i}. {label}")

    lines.append("<!-- END AUTO-GENERATED -->")
    lines.append("")  # trailing newline
    return "\n".join(lines)


def generate_semantic_pipeline_fragment(
    datrix_root: Path,
    output_dir: Path,
    *,
    check: bool = False,
    verbose: bool = False,
) -> bool:
    """Generate the semantic pipeline stages fragment.

    Args:
        datrix_root: Datrix workspace root directory.
        output_dir: Directory to write the fragment file into.
        check: If True, verify existing fragment matches without writing.
        verbose: If True, print detailed output.

    Returns:
        True if the fragment is up-to-date (or was written successfully).
        False if ``--check`` was used and the fragment is stale.

    Raises:
        FileNotFoundError: If ``analyzer.py`` cannot be found.
        ValueError: If parsing fails.
    """
    analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
    if not analyzer_path.is_file():
        raise FileNotFoundError(
            f"Semantic analyzer source not found at: {analyzer_path}\n"
            f"Expected relative path: {ANALYZER_RELATIVE_PATH}"
        )

    source_text = analyzer_path.read_text(encoding="utf-8")
    phase_names = _extract_phase_names(source_text)

    if verbose:
        print(f"  Found {len(phase_names)} semantic phases:")
        for i, name in enumerate(phase_names, start=1):
            print(f"    {i}. {name}")

    fragment = _build_semantic_fragment(phase_names)
    output_path = output_dir / SEMANTIC_OUTPUT_FILENAME

    if check:
        return _check_fragment(output_path, fragment, "semantic-pipeline", verbose)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(fragment, encoding="utf-8")
    print(
        colorize(
            f"  Written: {output_path.relative_to(datrix_root)}",
            ColorCodes.GREEN,
        )
    )
    return True


# ---------------------------------------------------------------------------
# Fragment 2: CLI help output
# ---------------------------------------------------------------------------


def _get_venv_python(datrix_root: Path) -> Path:
    """Locate the Python executable in the Datrix venv.

    Checks both Windows (``Scripts/python.exe``) and Unix
    (``bin/python``) layouts.

    Args:
        datrix_root: Datrix workspace root directory.

    Returns:
        Path to the Python executable.

    Raises:
        FileNotFoundError: If the executable cannot be found.
    """
    venv_dir = datrix_root / ".venv"
    candidates = [
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Could not find Python executable in venv.\n"
        f"Searched: {searched}\n"
        f"Ensure the venv exists at: {venv_dir}"
    )


# Python snippet that imports the Typer app, converts to Click, and
# invokes its help. Uses Click's CliRunner to capture help text cleanly,
# avoiding encoding issues with binary entry-point wrappers on Windows.
_CLI_HELP_SNIPPET = (
    "import typer.main, click.testing; "
    "from datrix_cli.main import app; "
    "cli = typer.main.get_command(app); "
    "r = click.testing.CliRunner().invoke(cli, ['generate', '--help']); "
    "print(r.output, end='')"
)


def _capture_cli_help(datrix_root: Path, verbose: bool = False) -> str:
    """Capture ``datrix generate --help`` output via subprocess.

    Invokes the venv Python with a Click CliRunner to capture help text
    cleanly, avoiding encoding issues with binary entry-point wrappers
    on Windows.

    Args:
        datrix_root: Datrix workspace root directory.
        verbose: If True, print the command being run.

    Returns:
        Captured help text (stdout).

    Raises:
        FileNotFoundError: If the Python executable is not found.
        RuntimeError: If the subprocess fails.
    """
    python_exe = _get_venv_python(datrix_root)

    cmd = [
        str(python_exe),
        "-c",
        _CLI_HELP_SNIPPET,
    ]

    if verbose:
        print(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(datrix_root),
        timeout=30,
    )

    if result.returncode != 0:
        stderr_text = result.stderr.strip()
        raise RuntimeError(
            f"Failed to capture CLI help output (exit code {result.returncode}).\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr: {stderr_text}"
        )

    return result.stdout.strip()


def _build_cli_help_fragment(help_text: str) -> str:
    """Build the markdown fragment for CLI help output.

    Args:
        help_text: Raw help text from ``datrix generate --help``.

    Returns:
        Complete markdown fragment with auto-generated markers.
    """
    lines: list[str] = []
    lines.append(
        "<!-- AUTO-GENERATED from `datrix generate --help` "
        "— do not edit manually -->"
    )
    lines.append("```text")
    lines.append(help_text)
    lines.append("```")
    lines.append("<!-- END AUTO-GENERATED -->")
    lines.append("")  # trailing newline
    return "\n".join(lines)


def generate_cli_help_fragment(
    datrix_root: Path,
    output_dir: Path,
    *,
    check: bool = False,
    verbose: bool = False,
) -> bool:
    """Generate the CLI help output fragment.

    Args:
        datrix_root: Datrix workspace root directory.
        output_dir: Directory to write the fragment file into.
        check: If True, verify existing fragment matches without writing.
        verbose: If True, print detailed output.

    Returns:
        True if the fragment is up-to-date (or was written successfully).
        False if ``--check`` was used and the fragment is stale.

    Raises:
        RuntimeError: If CLI help capture fails.
    """
    help_text = _capture_cli_help(datrix_root, verbose)

    if verbose:
        line_count = help_text.count("\n") + 1
        print(f"  Captured {line_count} lines of CLI help output")

    fragment = _build_cli_help_fragment(help_text)
    output_path = output_dir / CLI_HELP_OUTPUT_FILENAME

    if check:
        return _check_fragment(output_path, fragment, "cli-help", verbose)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(fragment, encoding="utf-8")
    print(
        colorize(
            f"  Written: {output_path.relative_to(datrix_root)}",
            ColorCodes.GREEN,
        )
    )
    return True


# ---------------------------------------------------------------------------
# Check mode (shared)
# ---------------------------------------------------------------------------


def _check_fragment(
    output_path: Path,
    expected_content: str,
    fragment_name: str,
    verbose: bool,
) -> bool:
    """Compare existing fragment file against expected content.

    Args:
        output_path: Path to the existing fragment file.
        expected_content: The content that should be in the file.
        fragment_name: Human-readable name for messages.
        verbose: If True, print diff details.

    Returns:
        True if the file matches expected content, False if stale or missing.
    """
    if not output_path.is_file():
        print(
            colorize(
                f"  STALE: {fragment_name} — file does not exist: {output_path}",
                ColorCodes.RED,
            )
        )
        return False

    existing = output_path.read_text(encoding="utf-8")
    if existing == expected_content:
        print(
            colorize(
                f"  OK: {fragment_name} is up-to-date",
                ColorCodes.GREEN,
            )
        )
        return True

    print(
        colorize(
            f"  STALE: {fragment_name} — content does not match source",
            ColorCodes.RED,
        )
    )
    if verbose:
        existing_lines = existing.splitlines()
        expected_lines = expected_content.splitlines()
        print(f"    Existing: {len(existing_lines)} lines")
        print(f"    Expected: {len(expected_lines)} lines")
    return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for this script.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate documentation fragments from source code. "
            "Ensures docs stay synchronized with their source of truth."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fragment",
        choices=sorted(VALID_FRAGMENTS),
        default="all",
        help=(
            "Which fragment to generate: "
            "semantic-pipeline, cli-help, or all (default: all)"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verify mode: check that existing fragments are up-to-date. "
            "Exits with non-zero status if any fragment is stale."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output during generation.",
    )
    return parser


def main() -> int:
    """Entry point for generate-doc-fragments script.

    Returns:
        Exit code: 0 on success, 1 on failure or stale fragments.
    """
    parser = _build_parser()
    args = parser.parse_args()

    fragment: str = args.fragment
    check: bool = args.check
    verbose: bool = args.verbose

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    datrix_root = get_datrix_root()
    output_dir = datrix_root / OUTPUT_DIR_NAME

    mode_label = "Checking" if check else "Generating"
    print(f"{mode_label} doc fragments...")
    print()

    all_ok = True
    run_semantic = fragment in ("all", "semantic-pipeline")
    run_cli = fragment in ("all", "cli-help")

    if run_semantic:
        print(colorize("Semantic pipeline stages:", ColorCodes.CYAN))
        try:
            ok = generate_semantic_pipeline_fragment(
                datrix_root, output_dir, check=check, verbose=verbose
            )
            if not ok:
                all_ok = False
        except (FileNotFoundError, ValueError) as exc:
            print(colorize(f"  ERROR: {exc}", ColorCodes.RED))
            all_ok = False
        print()

    if run_cli:
        print(colorize("CLI generate help:", ColorCodes.CYAN))
        try:
            ok = generate_cli_help_fragment(
                datrix_root, output_dir, check=check, verbose=verbose
            )
            if not ok:
                all_ok = False
        except RuntimeError as exc:
            print(colorize(f"  ERROR: {exc}", ColorCodes.RED))
            all_ok = False
        print()

    if all_ok:
        print(colorize("All fragments OK.", ColorCodes.GREEN))
        return 0

    if check:
        print(
            colorize(
                "One or more fragments are stale. "
                "Re-run without --check to regenerate.",
                ColorCodes.YELLOW,
            )
        )
    else:
        print(
            colorize(
                "One or more fragments failed to generate.",
                ColorCodes.RED,
            )
        )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
