"""
Remove a parameter from a function and from all call sites (API migration).

Usage:
  .\run-codemod.ps1 06_remove_function_argument FUNC_NAME ARG_NAME [paths...]
  bowler run scripts/codemods/lib/06_remove_function_argument.py -- build verbose datrix-common/src

Previews a diff; run-codemod -Write writes it.
"""

from __future__ import annotations

import sys

from _shared import finish
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

    finish(Query(*paths).select_function(func_name).remove_argument(arg_name))


if __name__ == "__main__":
    main()
