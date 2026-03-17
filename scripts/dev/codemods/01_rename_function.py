"""
Rename a function everywhere: definition, call sites, and imports.

Usage:
  .\run-codemod.ps1 01_rename_function OLD_NAME NEW_NAME [paths...]
  bowler run scripts/dev/codemods/01_rename_function.py -- parse_file parse_path datrix-language/src

If no paths given, uses current directory. Use .diff() to preview, .idiff() to apply interactively.
"""

from __future__ import annotations

import sys

from bowler import Query


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 3:
        old_name = sys.argv[1]
        new_name = sys.argv[2]
        if len(sys.argv) > 3:
            paths = sys.argv[3:]
    else:
        old_name = "old_func"
        new_name = "new_func"

    (
        Query(*paths)
        .select_function(old_name)
        .rename(new_name)
        .diff()
    )


if __name__ == "__main__":
    main()
