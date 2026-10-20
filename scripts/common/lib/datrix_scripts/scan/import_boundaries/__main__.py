"""The boundary scan alone: ``python -m datrix_scripts.scan.import_boundaries [check options]``.

Runs exactly the checks its options ask for, with no self-test and no always-on checks. The scanners'
CLI non-vacuity self-tests run it as a real subprocess against their planted fixture monorepos, so a
nested run never re-runs the self-test that started it. ``scan/check-import-boundaries.ps1`` runs
``datrix_scripts.scan.check_import_boundaries``, never this.
"""

from __future__ import annotations

import sys

from datrix_scripts.scan.check_import_boundaries import scan, scan_parser

if __name__ == "__main__":
    sys.exit(scan(scan_parser().parse_args()))
