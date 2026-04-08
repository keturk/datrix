#!/usr/bin/env python3
"""Compare two .dtrx files or snapshots and generate a schema diff report.

Supports Markdown and JSON output formats.
"""

from __future__ import annotations

import argparse
import io
import json
import signal
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

from shared.venv import get_datrix_root  # noqa: E402

datrix_root = get_datrix_root()
for sub in ("datrix-common/src", "datrix-language/src"):
    p = datrix_root / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from shared.logging_utils import ColorCodes, colorize  # noqa: E402
from shared.visualization.differ import (  # noqa: E402
    diff_applications,
    render_diff_json,
    render_diff_markdown,
)


def _load_application(path: Path) -> object:
    """Load an Application from a .dtrx file or JSON snapshot.

    Args:
        path: Path to .dtrx file or .json snapshot.

    Returns:
        Resolved Application object.

    Raises:
        ValueError: If file type is not recognized.
    """
    if path.suffix == ".json":
        # JSON snapshot — not yet supported for diff (would need deserialization)
        raise ValueError(
            f"JSON snapshot diff not yet supported: {path}. "
            "Use .dtrx files for both --before and --after."
        )

    from datrix_language.parser import TreeSitterParser
    from datrix_common.semantic import SemanticAnalyzer

    parser = TreeSitterParser()

    # Handle directory with system.dtrx
    actual_path = path
    if path.is_dir():
        system_dtrx = path / "system.dtrx"
        if system_dtrx.exists():
            actual_path = system_dtrx
        else:
            raise FileNotFoundError(f"No system.dtrx found in {path}")

    ast = parser.parse_file(actual_path)
    analyzer = SemanticAnalyzer()
    result = analyzer.analyze(ast)
    return result.app


def main() -> int:
    """Entry point for schema-diff script."""
    parser = argparse.ArgumentParser(
        description="Compare two .dtrx files and generate a schema diff report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--before", type=str, required=True, help="Path to the 'before' .dtrx file")
    parser.add_argument("--after", type=str, required=True, help="Path to the 'after' .dtrx file")
    parser.add_argument("--format", type=str, default="markdown", choices=["markdown", "json"], help="Output format")
    parser.add_argument("--output", type=str, default=None, help="Output file path (default: stdout)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    before_path = Path(args.before)
    after_path = Path(args.after)

    if not before_path.is_absolute():
        before_path = datrix_root / before_path
    if not after_path.is_absolute():
        after_path = datrix_root / after_path

    # Validate inputs exist
    if not before_path.exists():
        print(colorize(f"ERROR: Before file not found: {before_path}", ColorCodes.RED), file=sys.stderr)
        return 1
    if not after_path.exists():
        print(colorize(f"ERROR: After file not found: {after_path}", ColorCodes.RED), file=sys.stderr)
        return 1

    # Load both applications
    print(f"Before: {before_path}")
    print(f"After:  {after_path}")
    print()

    try:
        before_app = _load_application(before_path)
    except Exception as e:
        print(colorize(f"ERROR: Failed to load 'before': {e}", ColorCodes.RED), file=sys.stderr)
        return 1

    try:
        after_app = _load_application(after_path)
    except Exception as e:
        print(colorize(f"ERROR: Failed to load 'after': {e}", ColorCodes.RED), file=sys.stderr)
        return 1

    # Diff
    diff = diff_applications(before_app, after_app)

    # Render
    if args.format == "json":
        output = json.dumps(render_diff_json(diff), indent=2)
    else:
        output = render_diff_markdown(diff)

    # Write output
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = datrix_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"Report written to: {output_path}")
    else:
        print(output)

    # Summary
    if diff.has_changes:
        breaking_count = len(diff.breaking_changes)
        if breaking_count > 0:
            print(colorize(f"\n{breaking_count} breaking change(s) detected.", ColorCodes.RED))
        else:
            print(colorize("\nNo breaking changes.", ColorCodes.GREEN))
    else:
        print(colorize("\nNo changes detected.", ColorCodes.GREEN))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
