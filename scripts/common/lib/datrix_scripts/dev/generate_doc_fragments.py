"""Generate documentation fragments from source code.

The module behind ``dev/generate-doc-fragments.ps1`` (and its ``.sh`` twin).
Extracts documentation from source-of-truth code locations and writes
markdown fragment files. Two fragment types are supported:

1. **semantic-pipeline** — Ordered list of semantic analyzer phases, in
   the order derived from their declared requires/produces edges (the
   order SemanticAnalyzer.analyze() runs them).
2. **cli-help** — Full `datrix generate --help` output captured via
   subprocess invocation.

Fragments are written to ``datrix/docs/generated/`` with auto-generated
markers so humans know not to edit them manually.

Usage::

    python -m datrix_scripts.dev.generate_doc_fragments                    # generate all
    python -m datrix_scripts.dev.generate_doc_fragments --fragment=semantic-pipeline
    python -m datrix_scripts.dev.generate_doc_fragments --fragment=cli-help
    python -m datrix_scripts.dev.generate_doc_fragments --check            # verify mode (non-zero if stale)
    python -m datrix_scripts.dev.generate_doc_fragments --dbg              # detailed output
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.dev.generate_doc_fragments"
WRAPPER: Final = "generate-doc-fragments"

# ── Constants ──
VALID_FRAGMENTS = frozenset({"semantic-pipeline", "cli-help", "all"})
ANALYZER_RELATIVE_PATH = Path(
    "datrix-semantic/src/datrix_semantic/analyzer.py"
)
OUTPUT_DIR_NAME = Path("datrix/docs/generated")
SEMANTIC_OUTPUT_FILENAME = "semantic-pipeline-stages.md"
CLI_HELP_OUTPUT_FILENAME = "cli-generate-help.md"


# ---------------------------------------------------------------------------
# Fragment 1: Semantic pipeline stage list
# ---------------------------------------------------------------------------


def _function_name_to_label(name: str) -> str:
    """Convert a snake_case function name to a human-readable label.

    Drops a private name's leading underscores, replaces the remaining
    underscores with spaces and capitalizes the first letter.

    Args:
        name: Snake-case function name (e.g. ``register_stdlib_symbols``).

    Returns:
        Human-readable label (e.g. ``Register stdlib symbols``).
    """
    label = name.lstrip("_").replace("_", " ")
    return label[0].upper() + label[1:]


def _derive_phase_names() -> list[str]:
    """Return the semantic analyzer's phase names in execution order.

    ``SemanticAnalyzer.analyze()`` holds no call sequence to read: it builds
    the declared phase list and walks the order derived from each phase's
    ``requires``/``produces`` edges. This asks the same two functions
    ``analyze()`` asks, so the fragment is the order the analyzer actually
    runs, with the shipped stdlib enabled (the production setting).

    Returns:
        Ordered list of phase names.

    Raises:
        ValueError: If the derived order is empty.
    """
    from datrix_common.stage_graph import topologically_sort_phases
    from datrix_semantic.analyzer import _build_phases

    phase_names = [
        phase.name
        for phase in topologically_sort_phases(_build_phases(stdlib_enabled=True))
    ]
    if not phase_names:
        raise ValueError(
            "The semantic analyzer declares no phases: "
            "datrix_semantic.analyzer._build_phases returned an empty "
            "order. Expected the declared phase list analyze() walks; check "
            "that _build_phases still returns it."
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
        ValueError: If the analyzer declares no phases.
    """
    analyzer_path = datrix_root / ANALYZER_RELATIVE_PATH
    if not analyzer_path.is_file():
        raise FileNotFoundError(
            f"Semantic analyzer source not found at: {analyzer_path}\n"
            f"Expected relative path: {ANALYZER_RELATIVE_PATH}"
        )

    phase_names = _derive_phase_names()

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


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/generate-doc-fragments.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate documentation fragments from source code. "
            "Ensures docs stay synchronized with their source of truth."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("positional_fragment", nargs="?", choices=sorted(VALID_FRAGMENTS), metavar="FRAGMENT",
                        help="as --fragment, for a caller of the .sh twin")
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
        WRAPPER_DEBUG_FLAG,
        dest="debug",
        action="store_true",
        help="Print detailed output during generation.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: a fragment is reported OK, STALE or missing against a planted file.",
    )
    return parser


def _check_check_mode_reports_ok_stale_and_missing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp) / SEMANTIC_OUTPUT_FILENAME
        expected = _build_semantic_fragment(["_phase_one", "_phase_two"])
        assert "of 2 phases:" in expected and expected.endswith("<!-- END AUTO-GENERATED -->\n"), expected
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            missing = _check_fragment(planted, expected, "semantic-pipeline", verbose=False)
            planted.write_text(expected, encoding="utf-8")
            current = _check_fragment(planted, expected, "semantic-pipeline", verbose=False)
            planted.write_text(expected + "edited\n", encoding="utf-8")
            stale = _check_fragment(planted, expected, "semantic-pipeline", verbose=False)
        assert (missing, current, stale) == (False, True, False), (missing, current, stale, out.getvalue())
        report = out.getvalue()
        assert "file does not exist" in report and "is up-to-date" in report and "content does not match" in report, report


def _check_the_fragment_defaults_to_all() -> None:
    parser = build_parser()
    assert _fragment(parser.parse_args([])) == "all"
    assert _fragment(parser.parse_args(["cli-help"])) == "cli-help"
    assert _fragment(parser.parse_args(["--fragment=semantic-pipeline"])) == "semantic-pipeline"


def _fragment(args: argparse.Namespace) -> str:
    """The fragment *args* names: ``--fragment``, else the positional, else all."""
    if args.positional_fragment is not None and args.fragment != "all":
        raise UsageError(f"the fragment was given twice ({args.fragment} and {args.positional_fragment}); give it once")
    return args.positional_fragment if args.positional_fragment is not None else args.fragment


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


def _run(args: argparse.Namespace) -> int:
    """Generate (or with ``--check`` verify) the fragments *args* names.

    Returns:
        Exit code: 0 on success, 1 on failure or stale fragments.
    """
    if args.self_test:
        checks = [_check_check_mode_reports_ok_stale_and_missing, _check_the_fragment_defaults_to_all]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    fragment = _fragment(args)
    check: bool = args.check
    verbose: bool = args.debug

    datrix_root = WORKSPACE_DIR
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
    sys.exit(main())
