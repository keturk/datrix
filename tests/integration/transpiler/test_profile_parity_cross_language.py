"""Cross-language profile parity canary tests.

Relocated from datrix-codegen-common/tests/integration/test_repo_level_parity_meta.py
because importing PYTHON_PROFILE and TS_PROFILE in the same test file requires
cross-package imports that are forbidden from datrix-codegen-common.

These tests use the real Python and TypeScript profiles to verify the live parity
gate (validate_profile_completeness) would not reject either language package.
They act as canaries: if a language profile regresses, these tests fail first.
"""

from __future__ import annotations

import pytest

from datrix_codegen_common.transpiler.parity_checker import validate_profile_completeness
from datrix_codegen_python.profile import PYTHON_PROFILE
from datrix_codegen_typescript.profile import TS_PROFILE


@pytest.mark.integration
class TestRealProfileParityGatePasses:
    """The real Python and TypeScript generators pass validate_profile_completeness."""

    def test_real_python_typescript_parity_gate_passes(self) -> None:
        """Both real profiles pass the operator completeness gate.

        Uses the real profiles (not stubs) to prove the live parity gate
        would not reject the actual language packages. This test also acts as
        a canary: if a language profile regresses, this test fails first.
        """
        for lang, profile in [("python", PYTHON_PROFILE), ("typescript", TS_PROFILE)]:
            issues = validate_profile_completeness(profile)
            binary_issues = [i for i in issues if "binary_ops" in i]
            unary_issues = [i for i in issues if "unary_ops" in i]
            assign_issues = [i for i in issues if "assignment_ops" in i]
            assert binary_issues == [], f"{lang} binary_ops gap: {binary_issues}"
            assert unary_issues == [], f"{lang} unary_ops gap: {unary_issues}"
            assert assign_issues == [], f"{lang} assignment_ops gap: {assign_issues}"
