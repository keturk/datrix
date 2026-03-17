"""
Apply a refactor only to files matching a pattern (conditional/context-aware).

Example: rename a function only in test files, or only in one package.
Edit INCLUDE and EXCLUDE below (regex), then run. Use .diff() to preview.

Usage:
  .\run-codemod.ps1 11_filter_by_filename FUNC_NAME NEW_NAME [paths...]
  bowler run scripts/dev/codemods/11_filter_by_filename.py -- fixture setup_fixture datrix-language/tests

With defaults: only files matching INCLUDE and not matching EXCLUDE are modified.
"""

from __future__ import annotations

import sys

from bowler import Query

# Restrict to files whose path matches this regex; None = no filter.
INCLUDE: str | None = r"test_.*\.py"
# Skip files matching this regex; None = no filter.
EXCLUDE: str | None = None


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 3:
        old_name = sys.argv[1]
        new_name = sys.argv[2]
        if len(sys.argv) > 3:
            paths = sys.argv[3:]
    else:
        old_name = "old_helper"
        new_name = "new_helper"

    query = Query(*paths).select_function(old_name)
    if INCLUDE is not None:
        query = query.is_filename(include=INCLUDE)
    if EXCLUDE is not None:
        query = query.is_filename(exclude=EXCLUDE)
    query.rename(new_name).diff()


if __name__ == "__main__":
    main()
