"""Compare two .dtrx applications and report their schema changes.

The module behind ``visualize/schema-diff.ps1`` (and its ``.sh`` twin). Loads both applications
the way generation does (``visualization.application_loader``, profile ``test``), diffs their
structure, and renders a Markdown or JSON report (to ``--output``, or stdout) that marks breaking
and non-breaking changes. Relative paths are taken from the workspace root. A JSON snapshot is
refused: a diff reads two ``.dtrx`` sources.

Exit codes: 0 = the report was produced; 1 = an input is missing or failed to load;
2 = ``--before`` or ``--after`` not given.

Usage:
    python -m datrix_scripts.visualize.schema_diff --before=<v1/system.dtrx> --after=<v2/system.dtrx>
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, expect_usage_error, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.visualization.application_loader import load_application
from datrix_scripts.visualization.differ import diff_applications, render_diff_json, render_diff_markdown
from datrix_scripts.visualize.projects import plant_example, workspace_path

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

MODULE: Final = "datrix_scripts.visualize.schema_diff"
WRAPPER: Final = "schema-diff"
DIFF_PROFILE: Final = "test"
FORMATS: Final = ("markdown", "json")
SNAPSHOT_SUFFIX: Final = ".json"


def _load(path: Path) -> Application:
    """The application at *path* (a ``.dtrx`` file or a directory holding ``system.dtrx``).

    Raises:
        ValueError: *path* is a JSON snapshot, or parsing or analysis failed.
        FileNotFoundError: No ``.dtrx`` entry point at *path*.
    """
    if path.suffix == SNAPSHOT_SUFFIX:
        raise ValueError(f"A JSON snapshot cannot be diffed: {path}. Pass .dtrx files for both -Before and -After.")
    return load_application(path, DIFF_PROFILE)


def schema_diff(before_value: str, after_value: str, output_format: str, output: str | None) -> int:
    """Diff *before_value* against *after_value*; returns the exit code."""
    before_path = workspace_path(before_value)
    after_path = workspace_path(after_value)
    for label, path in (("Before", before_path), ("After", after_path)):
        if not path.exists():
            print(colorize(f"ERROR: {label} file not found: {path}", ColorCodes.RED), file=sys.stderr)
            return 1

    print(f"Before: {before_path}")
    print(f"After:  {after_path}")
    print()

    apps: list[Application] = []
    for label, path in (("before", before_path), ("after", after_path)):
        try:
            apps.append(_load(path))
        except Exception as e:
            print(colorize(f"ERROR: Failed to load '{label}': {e}", ColorCodes.RED), file=sys.stderr)
            return 1

    diff = diff_applications(apps[0], apps[1])
    report = json.dumps(render_diff_json(diff), indent=2) if output_format == "json" else render_diff_markdown(diff)

    if output:
        output_path = workspace_path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Report written to: {output_path}")
    else:
        print(report)

    if not diff.has_changes:
        print(colorize("\nNo changes detected.", ColorCodes.GREEN))
    elif diff.breaking_changes:
        print(colorize(f"\n{len(diff.breaking_changes)} breaking change(s) detected.", ColorCodes.RED))
    else:
        print(colorize("\nNo breaking changes.", ColorCodes.GREEN))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/schema-diff.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--before", help="Path to the earlier .dtrx file (baseline).")
    parser.add_argument("--after", help="Path to the later .dtrx file (comparison target).")
    parser.add_argument("--format", default="markdown", choices=FORMATS, help="Output format (default: markdown).")
    parser.add_argument("--output", help="Output file path (default: stdout).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted example diffed with itself, and the refusals.")
    return parser


def _check_a_planted_example_has_no_changes_against_itself() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = plant_example("01-foundation", Path(tmp)) / "system.dtrx"
        output = Path(tmp) / "diff.json"
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = schema_diff(str(source), str(source), "json", str(output))
        assert code == 0, printed.getvalue()
        assert "No changes detected." in printed.getvalue(), printed.getvalue()
        assert isinstance(json.loads(output.read_text(encoding="utf-8")), dict)


def _check_bad_inputs_are_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snapshot.json"
        snapshot.write_text("{}", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            assert schema_diff(str(Path(tmp) / "no-such.dtrx"), str(snapshot), "markdown", None) == 1
            assert schema_diff(str(snapshot), str(snapshot), "markdown", None) == 1
        assert "Before file not found" in errors.getvalue() and "cannot be diffed" in errors.getvalue(), errors.getvalue()
    expect_usage_error(lambda: _run(build_parser().parse_args(["--before=a.dtrx"])), "-After")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_example_has_no_changes_against_itself, _check_bad_inputs_are_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    if not args.before or not args.after:
        raise UsageError("-Before and -After are required: the baseline .dtrx and the one to compare with it.")
    return schema_diff(args.before, args.after, args.format, args.output)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
