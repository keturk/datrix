"""
Rename a class everywhere: definition, subclasses, instantiations, imports.

Usage:
  .\run-codemod.ps1 02_rename_class OLD_NAME NEW_NAME [paths...]
  bowler run scripts/codemods/lib/02_rename_class.py -- TreeSitterParser DatrixParser datrix-language/src

Previews a diff; run-codemod -Write writes it.
"""

from __future__ import annotations

import sys

from _shared import finish
from bowler import Query


def main() -> None:
    paths = ["."]
    if len(sys.argv) >= 3:
        old_name = sys.argv[1]
        new_name = sys.argv[2]
        if len(sys.argv) > 3:
            paths = sys.argv[3:]
    else:
        old_name = "OldClass"
        new_name = "NewClass"

    finish(Query(*paths).select_class(old_name).rename(new_name))


if __name__ == "__main__":
    main()
