#!/usr/bin/env python3
"""Java/Python SUPPORTED-and-shared-39 parity gate (design 036 G3, task 40-51).

G3 requires java's derived SUPPORTED set, restricted to the seven rich
cross-language domains (design 025 D4/D9) that are also shared-39 members, to
equal python's derived SUPPORTED set over that same restricted domain
universe -- exactly, with zero symmetric difference. This is the executable
cross-language comparison G3 names by name; it is genuinely a proof over TWO
generator packages' derived output, not a property either package can prove
about itself alone.

This check previously lived as two pytest tests
(``datrix-codegen-java/tests/support/test_shared39_progression.py`` and its
``shared39_progression.py`` helper) that imported ``datrix_codegen_python``
directly from java's own test suite. That module's own docstring argued the
cross-package import was "acceptable ONLY here" because nothing under
``src/datrix_codegen_java/`` imports it -- true, but irrelevant: the
CLAUDE.md rule is not "no production coupling", it is "no cross-package
test", full stop ("A test that imports two generator packages ... does not
belong in datrix -- or anywhere"). The proof is inherently repo-level -- it
spans exactly two generator packages by design -- so it belongs as a script
under ``datrix/scripts/test/``, the same home as the other repo-level parity
gates (``type-mapping-completeness.ps1``, ``gendsl-corpus-resolution-gate.ps1``),
not inside either package's own test suite. Java keeps its OWN half of G3 (its
derived supported-and-shared-39 set is exactly the seven rich domains) as a
package-local, python-import-free assertion in
``datrix-codegen-java/tests/integration/test_domain_self_consistency.py``.

**Safe to import both plugins in one process.** Unlike the genDSL corpus
resolution gate (which isolates each package import in its own subprocess
because ``@generator_definition`` writes into one shared, mutable, global
reference-resolution registry that both packages would otherwise pollute),
each ``LanguagePlugin.domain_declarations`` is a pure, package-local
computation (``derive_domain_declarations`` over that package's OWN
registered sub-generator specs) fixed at class-definition time -- reading it
for two packages in one process cannot leak state between them. This mirrors
``type_mapping_completeness.py``, which likewise imports multiple language
packages into one process against the deliberately shared, multi-language
``global_registry``.

Usage:
    python shared39_supported_parity.py
    python shared39_supported_parity.py --debug
"""

from __future__ import annotations

import argparse
import logging
import sys

from datrix_codegen_common.parity.domain_declaration import DomainDeclarations
from datrix_codegen_common.parity.domain_registry import (
    _RICH_CONTEXT_TYPES,
    SHARED_CONTEXT_TYPES,
)

#: The seven rich cross-language domains (design 025 D4/D9) that are also
#: shared-39 members -- every one of the seven IS shared-39 (verified: all
#: seven keys of `_RICH_CONTEXT_TYPES` are also keys of `SHARED_CONTEXT_TYPES`,
#: since `_build_shared_context_types` maps every COMMON registration's
#: domain id, rich or not). This is the restriction G3 names: java's/python's
#: derived-SUPPORTED sets are compared ONLY over this set -- a language may
#: legitimately commit its OWN additional structural glob outside the seven
#: rich domains (e.g. Java's `function`), which is a documented, intentional
#: per-language divergence, not a G3 violation.
_RICH_AND_SHARED39_IDS: frozenset[str] = frozenset(_RICH_CONTEXT_TYPES) & frozenset(SHARED_CONTEXT_TYPES)

#: Task 40-51's 8 infra-family `_test` domains (cache_test/storage_test/
#: nosql_test/cqrs_test/jobs_test/integration_test/module_function_test/
#: resilience_test): shared-39 members, but none is one of the seven rich
#: domains -- they must be correctly absent from BOTH languages' derived
#: supported-and-shared39 sets (D9: 'unsupported' means 'no committed
#: structural glob', not 'broken').
_INFRA_FAMILY_TEST_DOMAINS: frozenset[str] = frozenset({
    "cache_test", "storage_test", "nosql_test", "cqrs_test",
    "jobs_test", "integration_test", "module_function_test", "resilience_test",
})


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def supported_shared39_ids(domain_declarations: DomainDeclarations) -> frozenset[str]:
    """Return the subset of *domain_declarations* that are 'supported' AND
    both a shared-39 member AND one of the seven rich cross-language domains.

    Restricted to the seven rich domains (not the full shared-39 set) because
    a language may commit its OWN additional structural glob for a
    non-rich domain (Java's `function`, `helper`, `dev_scripts`) without that
    being a G3 parity violation -- G3 requires the SUPPORTED sets to agree
    only over the domains BOTH languages could plausibly commit a
    cross-language-stable structural glob for.

    Args:
        domain_declarations: A language plugin's derived
            ``domain_declarations`` (e.g. ``JavaLanguagePlugin.domain_declarations``).

    Returns:
        The frozenset of domain ids that are rich-and-shared39 members and
        derive ``status == "supported"`` for this language.
    """
    return frozenset(
        domain_id
        for domain_id, decl in domain_declarations.items()
        if domain_id in _RICH_AND_SHARED39_IDS and decl.status == "supported"
    )


def check_supported_shared39_parity() -> int:
    """Compare java's and python's derived supported-and-shared39 sets.

    Returns:
        Exit code (0 = the sets agree and the infra-family domains are
        correctly excluded from both, 1 = a divergence was found).
    """
    logger = logging.getLogger(__name__)

    # Imported here (not at module scope) so `--debug` logging is configured
    # before either package's plugin module import runs.
    from datrix_codegen_java.language_plugin import JavaLanguagePlugin
    from datrix_codegen_python.language_plugin import PythonLanguagePlugin

    java_ids = supported_shared39_ids(JavaLanguagePlugin.domain_declarations)
    python_ids = supported_shared39_ids(PythonLanguagePlugin.domain_declarations)

    ok = True

    symmetric_difference = java_ids ^ python_ids
    if symmetric_difference:
        ok = False
        logger.error(
            "G3 VIOLATION: java's and python's derived supported-and-shared39 "
            "sets disagree. java=%s python=%s symmetric_difference=%s",
            sorted(java_ids), sorted(python_ids), sorted(symmetric_difference),
        )
    else:
        logger.info(
            "G3 holds: java's and python's derived supported-and-shared39 "
            "sets are identical: %s", sorted(java_ids),
        )

    java_infra_leak = _INFRA_FAMILY_TEST_DOMAINS & java_ids
    python_infra_leak = _INFRA_FAMILY_TEST_DOMAINS & python_ids
    if java_infra_leak or python_infra_leak:
        ok = False
        logger.error(
            "G3 VIOLATION: infra-family `_test` domains must never appear in "
            "a supported-and-shared39 set (none is one of the seven rich "
            "domains). java_leak=%s python_leak=%s",
            sorted(java_infra_leak), sorted(python_infra_leak),
        )

    return 0 if ok else 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = G3 holds, 1 = a divergence was found).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove java's and python's derived SUPPORTED-and-shared-39 "
            "domain sets are identical (design 036 G3)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    return check_supported_shared39_parity()


if __name__ == "__main__":
    sys.exit(main())
