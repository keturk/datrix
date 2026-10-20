#!/usr/bin/env python3
"""Per-domain census of one target's compiled DAL generator definitions.

Consolidates the recurring temp-script pattern of ``count_16_26.py``,
``count_clauses_16_17.py`` (``D:\\datrix\\.scripts``): walk every domain of a
target's compiled ``GeneratorDefinition`` IR, count declared file clauses
(domain-level files plus the recursive ``iteration``/``children`` block
files) and domain builders, and flag the hazard shape those scripts hunted by
hand:

* **double-emit offender** -- a domain that DECLARES file clauses while still
  carrying one or more imperative domain builders. Declared files and domain
  builders both render unconditionally, so a declaring domain that keeps its
  builder can emit the same path twice.

The target name is resolved against the dgen target registry at runtime
(``datrix.platforms`` + ``datrix.dgen_generator_targets`` entry points) --
the installed target set is NEVER hardcoded; Datrix is a multi-language,
multi-platform generator and new targets appear with no edit here.

The module behind ``scan/dgen-census.ps1`` (and its ``.sh`` twin). The non-vacuity self-test runs as
step 1 of every census; ``--self-test`` runs it (with the wrapper seam) alone.

Usage:
  python -m datrix_scripts.scan.dgen_census --language=python
  python -m datrix_scripts.scan.dgen_census --self-test

Exit codes: 0 = no double-emit offenders, 1 = at least one, 2 = usage error
(no, unknown or definition-less target) or the non-vacuity self-test failed.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_codegen_kernel.dgen import target_registry
from datrix_codegen_kernel.dgen.compiler import target_definitions
from datrix_codegen_kernel.generation.dgen_ir import (
    DomainBuilderDefinition,
    DomainDefinition,
    FileDefinition,
    GeneratorDefinition,
    IterationBlock,
    ResolvedFunctionRef,
)

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.scan.dgen_census"
WRAPPER: Final = "dgen-census"

_NO_LANGUAGE: Final = (
    "Error: -Language is required unless -SelfTest is passed. Expected an installed dgen target, "
    "e.g. .\\dgen-census.ps1 python."
)

SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_OFFENDERS = 1
EXIT_USAGE = 2

#: Default output location (cross-cutting output per the script conventions).
OUTPUT_SUBDIRS: tuple[str, ...] = (".tmp", "dev")
OUTPUT_FILENAME_TEMPLATE = "dgen-census-{language}.json"


#: Definition name used only by the self-test fixtures below -- deliberately
#: not a real compiled definition name.
_SELF_TEST_DEFINITION_NAME = "__dgen_census_self_test__"


@dataclass(frozen=True)
class DomainCensus:
    """Census row for one DAL generator domain of one compiled definition."""

    definition: str
    domain: str
    file_clauses: int
    domain_builders: int
    has_domain_builder: bool
    declares_files: bool
    double_emit_offender: bool

    def to_json(self) -> dict[str, object]:
        """Serialize for the output payload."""
        return {
            "definition": self.definition,
            "domain": self.domain,
            "file_clauses": self.file_clauses,
            "domain_builders": self.domain_builders,
            "has_domain_builder": self.has_domain_builder,
            "declares_files": self.declares_files,
            "double_emit_offender": self.double_emit_offender,
        }


@dataclass(frozen=True)
class CensusTotals:
    """Aggregate counts over every censused domain."""

    domains: int
    file_clauses: int
    declaring_domains: int
    domains_with_builders: int
    double_emit_offenders: int

    def to_json(self) -> dict[str, int]:
        """Serialize for the output payload."""
        return {
            "domains": self.domains,
            "file_clauses": self.file_clauses,
            "declaring_domains": self.declaring_domains,
            "domains_with_builders": self.domains_with_builders,
            "double_emit_offenders": self.double_emit_offenders,
        }


def resolve_target_kind(language: str) -> str:
    """Resolve *language* against the installed dgen targets, failing loud.

    Args:
        language: Requested dgen target name (e.g. ``python``).

    Returns:
        The target's registered kind (``language``/``platform``/...).

    Raises:
        UsageError: If the name is not an installed target; the message lists
            every target that IS installed so the caller can correct the name.
    """
    kinds = target_registry.target_kind_map()
    if language not in kinds:
        installed = ", ".join(f"{name} ({kind})" for name, kind in sorted(kinds.items()))
        raise UsageError(
            f"Unknown dgen target {language!r}. Installed targets (discovered from "
            f"the datrix.platforms / datrix.dgen_generator_targets entry points): "
            f"{installed}. Pass one of those names, or install the package that "
            f"contributes the target you want."
        )
    return kinds[language]


def _iteration_blocks(domain: DomainDefinition) -> list[IterationBlock]:
    """Flatten a domain's ``iteration`` tree (top-level blocks + all children).

    Args:
        domain: A compiled domain definition.

    Returns:
        Every ``IterationBlock`` reachable from the domain.
    """
    blocks: list[IterationBlock] = []
    stack: list[IterationBlock] = list(domain.iteration)
    while stack:
        block = stack.pop()
        blocks.append(block)
        stack.extend(block.children)
    return blocks


def census_domain(definition_name: str, domain: DomainDefinition) -> DomainCensus:
    """Compute the census row for one domain.

    The file-clause count is ``len(domain.files)`` plus every ``files`` tuple
    of the recursive ``iteration``/``children`` block tree -- the exact
    recursion the ``count_16_26.py``/``count_clauses_16_17.py`` temp scripts
    used. Domain builders are counted at domain scope AND iteration scope.

    Args:
        definition_name: Name of the owning ``GeneratorDefinition``.
        domain: The compiled domain definition.

    Returns:
        The census row, including the double-emit flag.
    """
    file_defs: list[FileDefinition] = list(domain.files)
    builder_count = len(domain.domain_builders)
    for block in _iteration_blocks(domain):
        file_defs.extend(block.files)
        builder_count += len(block.domain_builders)

    file_clauses = len(file_defs)
    declares_files = file_clauses > 0
    has_domain_builder = builder_count > 0
    return DomainCensus(
        definition=definition_name,
        domain=domain.name,
        file_clauses=file_clauses,
        domain_builders=builder_count,
        has_domain_builder=has_domain_builder,
        declares_files=declares_files,
        double_emit_offender=declares_files and has_domain_builder,
    )


def _self_test_domain(name: str, *, with_builder: bool) -> DomainDefinition:
    """A domain declaring one template file clause; *with_builder* also gives
    it a domain-level ``builder`` line (the planted double-emit defect)."""

    def _builder() -> list[object]:
        return []

    builders = (
        (DomainBuilderDefinition(builder=ResolvedFunctionRef(ref="self_test.emit", callable_=_builder)),)
        if with_builder
        else ()
    )
    return DomainDefinition(
        name=name,
        feature_gates=(),
        semantic_requirements=(),
        context=None,
        iteration=(),
        files=(
            FileDefinition(
                name="model",
                language="python",
                template_name="model.py.j2",
                builder=None,
                path_template="{entity.name}.py",
                collects=None,
            ),
        ),
        appends=(),
        domain_builders=builders,
    )


def comparator_self_test() -> None:
    """Prove ``census_domain`` can detect a forced double-emit defect and
    correctly leaves a clean domain unflagged, before trusting the flag
    against real data.

    Mirrors the house non-vacuity pattern
    (``datrix_scripts.gates.parity.supported_domain_parity_gate.run_self_test``):
    feed the comparator a synthetic CLEAN case (must report zero offenders)
    and a synthetic DEFECT case (must report exactly the planted defect).

    Raises:
        AssertionError: If either synthetic case does not produce the
            expected result.
    """
    clean_row = census_domain(
        _SELF_TEST_DEFINITION_NAME, _self_test_domain("clean_domain", with_builder=False)
    )
    if clean_row.double_emit_offender:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: census_domain flagged a synthetic "
            f"CLEAN domain as an offender ({clean_row}) -- the comparator is "
            f"over-triggering and cannot be trusted to judge real data."
        )

    defect_row = census_domain(
        _SELF_TEST_DEFINITION_NAME, _self_test_domain("double_emit_domain", with_builder=True)
    )
    if not defect_row.double_emit_offender:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: census_domain did not detect the "
            f"forced double-emit defect ({defect_row}) -- a census that cannot "
            f"detect a real double-emit domain is worthless."
        )


def run_census(language: str) -> tuple[str, list[GeneratorDefinition], list[DomainCensus]]:
    """Compile-and-walk the census for one installed dgen target.

    Args:
        language: The dgen target name (validated against the registry).

    Returns:
        ``(target_kind, definitions, rows)`` -- one row per domain across
        every compiled definition registered for the target.

    Raises:
        UsageError: If the target is unknown or registers no definitions.
    """
    target_kind = resolve_target_kind(language)
    try:
        definitions = list(target_definitions(language))
    except ValueError as error:
        raise UsageError(
            f"Target {language!r} (kind={target_kind}) is installed but supplies "
            f"no compiled DAL generator definitions -- there is nothing to census: {error} "
            f"If the target should have definitions, check its "
            f"datrix.dgen_generator_targets contribution's definition_modules."
        ) from error
    rows: list[DomainCensus] = []
    for definition in definitions:
        logger.debug(
            "census_definition name=%s domains=%d",
            definition.name,
            len(definition.domains),
        )
        rows.extend(census_domain(definition.name, domain) for domain in definition.domains)
    return target_kind, definitions, rows


def compute_totals(rows: list[DomainCensus]) -> CensusTotals:
    """Aggregate the census rows.

    Args:
        rows: Per-domain census rows.

    Returns:
        The aggregate totals.
    """
    return CensusTotals(
        domains=len(rows),
        file_clauses=sum(row.file_clauses for row in rows),
        declaring_domains=sum(1 for row in rows if row.declares_files),
        domains_with_builders=sum(1 for row in rows if row.has_domain_builder),
        double_emit_offenders=sum(1 for row in rows if row.double_emit_offender),
    )


def build_payload(
    language: str,
    target_kind: str,
    definition_count: int,
    rows: list[DomainCensus],
    totals: CensusTotals,
) -> dict[str, object]:
    """Assemble the output JSON payload.

    Args:
        language: The censused target name.
        target_kind: The target's registered kind.
        definition_count: Number of compiled definitions for the target.
        rows: Per-domain census rows.
        totals: Aggregate totals over *rows*.

    Returns:
        The JSON-serializable payload (schema_version 1).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "language": language,
        "target_kind": target_kind,
        "definition_count": definition_count,
        "domains": [row.to_json() for row in rows],
        "totals": totals.to_json(),
        "double_emit_offenders": [row.domain for row in rows if row.double_emit_offender],
    }


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/dgen-census.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument(
        "--language",
        help="Installed dgen target name (e.g. python). Unknown names fail loud "
        "listing every installed target. Not required with --self-test.",
    )
    parser.add_argument(
        "--output",
        help="Override the output JSON path (default: <workspace>/.tmp/dev/dgen-census-<language>.json).",
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: the double-emit comparator flags a forced defect and leaves a clean "
        "domain alone, a census without a language is refused, and the wrapper seam holds.",
    )
    return parser


def census(language: str, output: str | None) -> int:
    """Census *language*, write the JSON to *output* (or the default path); 0, 1 offenders, 2 usage error."""
    try:
        target_kind, definitions, rows = run_census(language)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    totals = compute_totals(rows)
    payload = build_payload(language, target_kind, len(definitions), rows, totals)
    output_path = (
        Path(output).resolve()
        if output
        else WORKSPACE_DIR.joinpath(*OUTPUT_SUBDIRS) / OUTPUT_FILENAME_TEMPLATE.format(language=language)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        f"{language}: {totals.domains} domains, {totals.file_clauses} file clauses, "
        f"{totals.double_emit_offenders} double-emit offenders"
    )
    print(f"Details: {output_path}")
    return EXIT_OFFENDERS if totals.double_emit_offenders else EXIT_OK


def _check_a_census_without_a_language_is_refused() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = _run(build_parser().parse_args([]))
    assert code == EXIT_USAGE and out.getvalue().strip() == _NO_LANGUAGE, f"got {code}: {out.getvalue()!r}"


def _run(args: argparse.Namespace) -> int:
    if not args.debug:
        logging.getLogger().setLevel(logging.WARNING)
    if args.self_test:
        checks = [comparator_self_test, _check_a_census_without_a_language_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    if not args.language:
        print(_NO_LANGUAGE)
        return EXIT_USAGE
    # Step 1 of every census: a comparator that cannot detect a planted defect proves nothing.
    try:
        comparator_self_test()
    except AssertionError as exc:
        logger.error("%s", exc)
        return EXIT_USAGE
    return census(str(args.language), args.output)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
