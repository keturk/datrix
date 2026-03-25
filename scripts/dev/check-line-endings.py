#!/usr/bin/env python3
"""Verify all shell scripts use LF line endings.

This script checks that shell scripts (.sh, .sh.j2, .bash) use Unix (LF) line
endings, not Windows (CRLF) line endings. Shell scripts with CRLF will fail
when executed in Linux containers with errors like: $'\r': command not found

Usage:
    python check-line-endings.py [--fix]

Options:
    --fix    Automatically convert CRLF to LF (requires dos2unix)

Exit codes:
    0: All files have correct line endings
    1: Files with incorrect line endings found
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def has_crlf(file_path: Path) -> bool:
    """Check if file contains CRLF line endings.

    Args:
        file_path: Path to file to check.

    Returns:
        True if file contains any CRLF (\r\n) or CR (\r) bytes.
    """
    try:
        content = file_path.read_bytes()
        return b"\r\n" in content or b"\r" in content
    except Exception as e:
        print(f"[WARN] Error reading {file_path}: {e}", file=sys.stderr)
        return False


def convert_to_lf(file_path: Path) -> bool:
    """Convert file from CRLF to LF using dos2unix.

    Args:
        file_path: Path to file to convert.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    try:
        result = subprocess.run(
            ["dos2unix", str(file_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print(f"[OK] Converted: {file_path}")
            return True
        else:
            print(f"[ERROR] Failed to convert {file_path}: {result.stderr}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print(
            "[ERROR] dos2unix not found. Install it or run without --fix.",
            file=sys.stderr,
        )
        return False


def main() -> int:
    """Check (and optionally fix) line endings in shell scripts."""
    parser = argparse.ArgumentParser(
        description="Verify shell scripts use LF line endings"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically convert CRLF to LF (requires dos2unix)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent.parent
    print(f"Checking shell scripts in: {repo_root}")

    patterns = ["**/*.sh", "**/*.sh.j2", "**/*.bash"]
    files_with_crlf: list[Path] = []

    for pattern in patterns:
        for file_path in repo_root.glob(pattern):
            # Skip hidden directories and common ignore patterns
            if any(part.startswith(".") for part in file_path.parts):
                continue
            if "node_modules" in file_path.parts:
                continue
            if ".venv" in file_path.parts or "venv" in file_path.parts:
                continue

            if has_crlf(file_path):
                files_with_crlf.append(file_path)

    if not files_with_crlf:
        print("[PASS] All shell scripts have LF line endings")
        return 0

    print(f"\n[FAIL] Found {len(files_with_crlf)} file(s) with CRLF line endings:\n")
    for file_path in files_with_crlf:
        rel_path = file_path.relative_to(repo_root)
        print(f"  {rel_path}")

    if args.fix:
        print("\n[FIX] Converting files to LF...\n")
        success_count = 0
        for file_path in files_with_crlf:
            if convert_to_lf(file_path):
                success_count += 1

        if success_count == len(files_with_crlf):
            print(f"\n[PASS] Successfully converted all {success_count} file(s)")
            return 0
        else:
            print(
                f"\n[WARN] Converted {success_count}/{len(files_with_crlf)} file(s)",
                file=sys.stderr,
            )
            return 1
    else:
        print("\nRun with --fix to automatically convert these files.")
        print("Or manually run: dos2unix <file>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
