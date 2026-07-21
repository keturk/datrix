#!/usr/bin/env python3
"""Per-domain census of one target's compiled genDSL definitions.

Consolidates the recurring temp-script pattern of ``count_16_26.py``,
``count_clauses_16_17.py`` and ``find_bridgeless_declaring_domain.py``
(``D:\\datrix\\.scripts``): walk every domain of a target's compiled
``GeneratorDefinition`` IR, count declared file clauses (domain-level files
plus the recursive ``iteration``/``children`` block files), and flag the two
hazard shapes those scripts hunted by hand:

* **double-emit offender** -- a domain that DECLARES file clauses while still
  carrying one or more imperative domain builders. Declared files and domain
  builders both render unconditionally (the ``render_declared_files``
  opt-out was removed), so a declaring domain that keeps its
  builder can emit the same path twice (the hazard ``gate_16_19_verify.py``
  CHECK 6 polices).
* **bridgeless declaring** -- a declaring domain none of whose bridge
  callables (domain-builder callables plus declared-file builder callables,
  the same scan as ``registry_adapter._owning_bridge_callables``) carries the
  ``MICRO_GENERATOR_CLS`` owning-class attribute (the D4 bridge).

The target name is resolved against the gendsl target registry at runtime
(``datrix.platforms`` + ``datrix.gendsl_generator_targets`` entry points) --
the installed target set is NEVER hardcoded; Datrix is a multi-language,
multi-platform generator and new targets appear with no edit here.

Usage:
  python scripts/library/dev/gendsl_census.py --language python
  .\\scripts\\dev\\gendsl-census.ps1 python

Exit codes: 0 = no double-emit offenders, 1 = offenders found,
2 = usage error (unknown/definition-less target).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.venv import get_datrix_root  # noqa: E402

from datrix_codegen_common.gendsl import target_registry  # noqa: E402
from datrix_codegen_common.gendsl.compiler import get_definitions  # noqa: E402
from datrix_codegen_common.gendsl.registry_adapter import MICRO_GENERATOR_ATTR  # noqa: E402
from datrix_common.generation.gendsl_ir import (  # noqa: E402
    CallExpression,
    DomainDefinition,
    FileDefinition,
    GeneratorDefinition,
    IterationBlock,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_OFFENDERS = 1
EXIT_USAGE = 2

#: Default output location (cross-cutting output per the script conventions).
OUTPUT_SUBDIRS: tuple[str, ...] = (".tmp", "dev")
OUTPUT_FILENAME_TEMPLATE = "gendsl-census-{language}.json"


class UsageError(Exception):
    """Invalid usage or unresolvable input; the script exits with code 2."""


@dataclass(frozen=True)
class DomainCensus:
    """Census row for one genDSL domain of one compiled definition."""

    definition: str
    domain: str
    file_clauses: int
    domain_builders: int
    has_domain_builder: bool
    declares_files: bool
    double_emit_offender: bool
    bridgeless_declaring: bool

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
            "bridgeless_declaring": self.bridgeless_declaring,
        }


@dataclass(frozen=True)
class CensusTotals:
    """Aggregate counts over every censused domain."""

    domains: int
    file_clauses: int
    declaring_domains: int
    domains_with_builders: int
    double_emit_offenders: int
    bridgeless_declaring: int

    def to_json(self) -> dict[str, int]:
        """Serialize for the output payload."""
        return {
            "domains": self.domains,
            "file_clauses": self.file_clauses,
            "declaring_domains": self.declaring_domains,
            "domains_with_builders": self.domains_with_builders,
            "double_emit_offenders": self.double_emit_offenders,
            "bridgeless_declaring": self.bridgeless_declaring,
        }


def resolve_target_kind(language: str) -> str:
    """Resolve *language* against the installed gendsl targets, failing loud.

    Args:
        language: Requested gendsl target name (e.g. ``python``).

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
            f"Unknown gendsl target {language!r}. Installed targets (discovered from "
            f"the datrix.platforms / datrix.gendsl_generator_targets entry points): "
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


def _file_builder_callable(file_def: FileDefinition) -> Callable[..., object] | None:
    """Return the resolved content callable of a ``builder``-kind file clause.

    Mirrors ``registry_adapter._file_builder_callables``: a declared file's
    ``builder`` is a ``ResolvedFunctionRef`` or a ``CallExpression`` wrapping
    one; the D4 bridge attribute lives on the resolved callable.

    Args:
        file_def: A compiled file clause.

    Returns:
        The resolved callable, or ``None`` for template-kind files.
    """
    builder = file_def.builder
    if builder is None:
        return None
    if isinstance(builder, CallExpression):
        return builder.function_ref.callable_
    return builder.callable_


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
        The census row, including the double-emit and bridgeless flags.
    """
    blocks = _iteration_blocks(domain)

    file_defs: list[FileDefinition] = list(domain.files)
    builder_count = len(domain.domain_builders)
    bridge_callables: list[Callable[..., object]] = [
        builder.builder.callable_ for builder in domain.domain_builders
    ]
    for block in blocks:
        file_defs.extend(block.files)
        builder_count += len(block.domain_builders)
        bridge_callables.extend(
            builder.builder.callable_ for builder in block.domain_builders
        )

    for file_def in file_defs:
        resolved = _file_builder_callable(file_def)
        if resolved is not None:
            bridge_callables.append(resolved)

    file_clauses = len(file_defs)
    declares_files = file_clauses > 0
    has_domain_builder = builder_count > 0
    bridged = any(
        getattr(callable_, MICRO_GENERATOR_ATTR, None) is not None
        for callable_ in bridge_callables
    )
    return DomainCensus(
        definition=definition_name,
        domain=domain.name,
        file_clauses=file_clauses,
        domain_builders=builder_count,
        has_domain_builder=has_domain_builder,
        declares_files=declares_files,
        double_emit_offender=declares_files and has_domain_builder,
        bridgeless_declaring=declares_files and not bridged,
    )


def run_census(language: str) -> tuple[str, list[GeneratorDefinition], list[DomainCensus]]:
    """Compile-and-walk the census for one installed gendsl target.

    Args:
        language: The gendsl target name (validated against the registry).

    Returns:
        ``(target_kind, definitions, rows)`` -- one row per domain across
        every compiled definition registered for the target.

    Raises:
        UsageError: If the target is unknown or registers no definitions.
    """
    target_kind = resolve_target_kind(language)
    definitions = get_definitions(language)
    if not definitions:
        raise UsageError(
            f"Target {language!r} (kind={target_kind}) is installed but registers "
            f"no compiled genDSL definitions -- there is nothing to census. If the "
            f"target should have definitions, check its "
            f"datrix.gendsl_generator_targets contribution's definition_modules."
        )
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
        bridgeless_declaring=sum(1 for row in rows if row.bridgeless_declaring),
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
        "bridgeless_declaring_domains": [
            row.domain for row in rows if row.bridgeless_declaring
        ],
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (without the program name).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Per-domain census of one gendsl target's compiled definitions: file "
            "clauses, domain builders, double-emit offenders, bridgeless declaring "
            "domains. Targets are discovered from installed entry points at runtime."
        ),
    )
    parser.add_argument(
        "--language",
        required=True,
        help="Installed gendsl target name (e.g. python). Unknown names fail loud "
        "listing every installed target.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the output JSON path (default: "
        "<workspace>/.tmp/dev/gendsl-census-<language>.json).",
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 = no double-emit offenders, 1 = offenders,
        2 = usage error.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    language = str(args.language)
    try:
        target_kind, definitions, rows = run_census(language)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    totals = compute_totals(rows)
    payload = build_payload(language, target_kind, len(definitions), rows, totals)
    output_path = (
        Path(args.output).resolve()
        if args.output
        else get_datrix_root().joinpath(*OUTPUT_SUBDIRS)
        / OUTPUT_FILENAME_TEMPLATE.format(language=language)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        f"{language}: {totals.domains} domains, {totals.file_clauses} file clauses, "
        f"{totals.double_emit_offenders} double-emit offenders, "
        f"{totals.bridgeless_declaring} bridgeless"
    )
    print(f"Details: {output_path}")
    return EXIT_OFFENDERS if totals.double_emit_offenders else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
