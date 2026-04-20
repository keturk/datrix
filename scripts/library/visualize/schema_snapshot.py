#!/usr/bin/env python3
"""Save a .dtrx Application as a JSON snapshot for future diffs.

Supports single-file and batch modes. Snapshots capture the full
structural model (services, entities, endpoints, events) in a
JSON-serializable format.
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
from shared.test_projects import get_test_projects  # noqa: E402
from shared.visualization.serializer import serialize_application  # noqa: E402


def _parse_and_snapshot(
    source_path: Path,
    output_path: Path,
) -> tuple[bool, str]:
    """Parse a .dtrx file and write JSON snapshot.

    Returns (success, error_message).
    """
    # Resolve system.dtrx if directory given
    if source_path.is_dir():
        system_dtrx = source_path / "system.dtrx"
        if system_dtrx.exists():
            source_path = system_dtrx
        else:
            return False, f"No system.dtrx found in {source_path}"

    if not source_path.exists():
        return False, f"Source file not found: {source_path}"

    try:
        from datrix_language.parser import TreeSitterParser
        from datrix_common.semantic import SemanticAnalyzer

        parser = TreeSitterParser()
        ast = parser.parse_file(source_path)
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(ast)
        app = result.app
    except Exception as e:
        return False, f"Parse error: {e}"

    try:
        data = serialize_application(app)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        return False, f"Serialization error: {e}"

    return True, ""


def main() -> int:
    """Entry point for schema-snapshot script."""
    parser = argparse.ArgumentParser(
        description="Save .dtrx Application as JSON snapshot for future diffs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", type=str, default=None, help="Path to .dtrx file or directory")
    parser.add_argument("--all", action="store_true", dest="batch_all", help="All projects from test-projects.json")
    parser.add_argument("--tutorial", action="store_true", help="Tutorial examples only")
    parser.add_argument("--domains", action="store_true", help="Domain examples only")
    parser.add_argument("--test-set", type=str, default="all", help="Named test set")
    parser.add_argument("--output", type=str, default=None, help="Explicit output file path (overrides default)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    batch_mode = args.batch_all or args.tutorial or args.domains

    if not batch_mode and not args.source:
        parser.error("Either --source or a batch flag (--all, --tutorial, --domains) is required.")

    success_count = 0
    fail_count = 0

    if args.source:
        # Single project mode — snapshot goes next to the .dtrx source
        source_path = Path(args.source)
        if not source_path.is_absolute():
            source_path = datrix_root / source_path

        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = datrix_root / output_path
        else:
            project_dir = source_path.parent if source_path.is_file() else source_path
            output_path = project_dir / "docs" / "snapshots" / f"{source_path.stem}.json"

        print(f"Source: {source_path}")
        print(f"Output: {output_path}")
        ok, err = _parse_and_snapshot(source_path, output_path)
        if ok:
            success_count += 1
            print(colorize("Snapshot saved.", ColorCodes.GREEN))
        else:
            fail_count += 1
            print(colorize(f"ERROR: {err}", ColorCodes.RED), file=sys.stderr)
    else:
        # Batch mode
        test_set = "all"
        if args.tutorial:
            test_set = "tutorial-all"
        elif args.domains:
            test_set = "domains"
        elif args.test_set != "all":
            test_set = args.test_set

        try:
            projects = get_test_projects(test_set=test_set)
        except Exception as e:
            print(colorize(f"ERROR: Failed to load test projects: {e}", ColorCodes.RED), file=sys.stderr)
            return 1

        if not projects:
            print(colorize(f"No projects found in test set '{test_set}'", ColorCodes.YELLOW))
            return 1

        total = len(projects)
        print(f"Creating snapshots for {total} projects\n")

        for i, project in enumerate(projects):
            idx = i + 1
            project_name = project.get("name", "unknown")
            source = project.get("path", "")

            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = datrix_root / source
            # Snapshot goes next to the .dtrx source (language-agnostic)
            project_dir = source_path.parent if source_path.is_file() else source_path
            output_path = project_dir / "docs" / "snapshots" / f"{project_name}.json"

            print(f"[{idx}/{total}] {project_name} ... ", end="", flush=True)
            ok, err = _parse_and_snapshot(source_path, output_path)
            if ok:
                success_count += 1
                print(colorize("OK", ColorCodes.GREEN))
            else:
                fail_count += 1
                print(colorize(f"FAILED: {err}", ColorCodes.RED))

    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
