"""Temporary guard: public showcase repo evacuation is incomplete.

This test is intentionally marked xfail(strict=True). It exists only to keep
the incomplete cleanup of ``datrix/tests/`` visible on every CI run until
FUP-1, FUP-2, and FUP-3 from design 002 are complete.

How this guard works
--------------------
- **While evacuation is incomplete (current state):** the assertion inside the
  test body FAILS (product test files still exist in ``datrix/tests/integration/``).
  pytest reports this as XFAILED — expected failure, visible in the report but
  does NOT make the suite red.
- **After FUP-3 lands and ``datrix/tests/`` is deleted:** this file will no
  longer exist and the guard is gone. If someone deletes the integration tests
  but forgets to delete this guard, the assertion would PASS → with strict=True
  pytest reports XPASS → hard failure, forcing the guard's removal.

Removal condition
-----------------
Delete this file as part of FUP-3 (see design 002, FUP-3) when:
  1. FUP-1 is complete: per-generator determinism tests live in each codegen
     package's own suite.
  2. FUP-2 is complete: identity multitarget artifact tests and per-language
     reason-code conformance tests live in the appropriate target packages.
  3. ``datrix/tests/`` has been deleted from the public showcase repo and
     ``datrix`` has been removed from ``Get-DatrixTestablePackageNames``.

References
----------
- design/001-language-conformance-against-abstract-contracts.md  (Open Follow-ups)
- design/002-public-showcase-test-evacuation.md  (FUP-1, FUP-2, FUP-3)
"""

from __future__ import annotations

from pathlib import Path

import pytest

_TESTS_INTEGRATION_DIR = Path(__file__).parent / "integration"


@pytest.mark.xfail(
    reason=(
        "datrix/tests still present — public-repo evacuation incomplete; "
        "see design/001-language-conformance-against-abstract-contracts.md "
        "and design/002-public-showcase-test-evacuation.md (FUP-1/FUP-2/FUP-3). "
        "Remove this guard when datrix/tests is deleted."
    ),
    strict=True,
)
def test_public_repo_evacuation_complete() -> None:
    """Assert that the public showcase repo contains no product integration tests.

    This assertion holds ONLY after FUP-1, FUP-2, and FUP-3 land and
    ``datrix/tests/integration/`` is deleted. While product tests remain, this
    test fails (reported as XFAILED — visible but not CI-red).
    """
    assert not _TESTS_INTEGRATION_DIR.exists(), (
        "datrix/tests/integration/ still exists — product integration tests have "
        "not yet been evacuated from the public showcase repo. "
        "Complete FUP-1 (re-home test_byte_identical_regeneration.py into each "
        "codegen package) and FUP-2 (re-home identity multitarget / token-validation "
        "tests into target packages) then delete datrix/tests/ as FUP-3. "
        "See design/001-language-conformance-against-abstract-contracts.md (Open "
        "Follow-ups) and design/002-public-showcase-test-evacuation.md."
    )
