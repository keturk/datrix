"""
Add a new parameter to a function and update all call sites with the default value.

Usage:
  .\run-codemod.ps1 03_add_function_argument FUNC_NAME ARG_NAME DEFAULT_VALUE [paths...]
  bowler run scripts/dev/codemods/03_add_function_argument.py -- build "" "None" datrix-common/src

Use .diff() to preview. For a keyword-only arg, the default is used in the definition only.
"""

from __future__ import annotations

import sys

from bowler import Query


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 4:
        func_name = sys.argv[1]
        arg_name = sys.argv[2]
        default_value = sys.argv[3]
        if len(sys.argv) > 4:
            paths = sys.argv[4:]
    else:
        func_name = "my_func"
        arg_name = "new_param"
        default_value = "None"

    (
        Query(*paths)
        .select_function(func_name)
        .add_argument(arg_name, default_value, positional=False)
        .diff()
    )


if __name__ == "__main__":
    main()
