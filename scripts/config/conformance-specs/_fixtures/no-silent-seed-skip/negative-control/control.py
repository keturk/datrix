"""Negative-control fixture for the no-silent-seed-skip conformance spec.

Deliberately contains the forbidden pattern that spec's ``must_not_contain``
assertion polices, so the assertion is proven non-vacuous: the conformance
runner refuses to credit a ``must_not_contain`` check whose pattern is absent
from BOTH the real target tree AND this control tree, since that would prove
nothing about the target.

This file is never imported or executed by anything. It exists only as scan
input, and lives outside every package's ``src/`` so it can never enter a real
import graph.
"""


def _never_called_control_fixture() -> str:
    """Exists only so this file is syntactically valid Python worth scanning."""
    return "seed_skipped reason=no_rdbms_components service=%s"
