"""
Update imports when a module is renamed or moved. All "import old_module" and
"from old_module import ..." are updated to use the new module name.

Usage:
  .\run-codemod.ps1 08_rename_module_imports OLD_MODULE NEW_MODULE [paths...]
  bowler run scripts/dev/codemods/08_rename_module_imports.py -- datrix_language.parser datrix_language.parsing datrix-language/src

Use .diff() to preview. Does not rename the module file itself—only import references.
"""

from __future__ import annotations

import sys

from bowler import Query


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 3:
        old_module = sys.argv[1]
        new_module = sys.argv[2]
        if len(sys.argv) > 3:
            paths = sys.argv[3:]
    else:
        old_module = "old_module"
        new_module = "new_module"

    (
        Query(*paths)
        .select_module(old_module)
        .rename(new_module)
        .diff()
    )


if __name__ == "__main__":
    main()
