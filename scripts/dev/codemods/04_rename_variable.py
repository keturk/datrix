"""
Rename a variable or constant everywhere: assignments and references.

Usage:
  .\run-codemod.ps1 04_rename_variable OLD_NAME NEW_NAME [paths...]
  bowler run scripts/dev/codemods/04_rename_variable.py -- MAX_RETRIES max_retries datrix-language/src

Use .diff() to preview, .idiff() to apply interactively.
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
        old_name = "old_var"
        new_name = "new_var"

    (
        Query(*paths)
        .select_var(old_name)
        .rename(new_name)
        .diff()
    )


if __name__ == "__main__":
    main()
