"""
Remove a parameter from a function and from all call sites (API migration).

Usage:
  .\run-codemod.ps1 06_remove_function_argument FUNC_NAME ARG_NAME [paths...]
  bowler run scripts/dev/codemods/06_remove_function_argument.py -- build verbose datrix-common/src

Use .diff() to preview, .write() to apply.
"""

from __future__ import annotations

import sys

from bowler import Query


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 3:
        func_name = sys.argv[1]
        arg_name = sys.argv[2]
        if len(sys.argv) > 3:
            paths = sys.argv[3:]
    else:
        func_name = "my_func"
        arg_name = "param_to_remove"

    (
        Query(*paths)
        .select_function(func_name)
        .remove_argument(arg_name)
        .diff()
    )


if __name__ == "__main__":
    main()
