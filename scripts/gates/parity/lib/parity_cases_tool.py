"""The parity rows' authoring tool (``parity-cases.ps1``): observe, new, migrate, accept, check.

``observe <input> <probe> <selector>``
    Build the fixture for every target of the probe's axis and print each target's reading of
    the selector. Writes nothing (fixtures go under ``D:\\datrix\\.tmp\\parity-cases``).
``new <area> --id ... --tags ... --input ... --probe ... --selector ... --expectation ... --reason ...``
    Validate one authored row against the parity checks and every committed row, read it on
    every target (it must be readable), and append it to ``cases/<area>.parity.yaml``.
    Refused while the approval gate is armed for the parity cases directory.
``migrate <input> <probe> --area <area> [--tags ...] [--replaces <gate>]``
    Propose one row per selector the probe's return offers on any target, with every target's
    reading beside it and NO expectation: the reviewer authors each expectation, the tool never
    blesses a reading. The proposal is a case-proposal document under the case proposals
    directory, so Jon approves it exactly as a case proposal.
``accept <proposal>``
    Move an approved proposal's rows into ``cases/<area>.parity.yaml``; refuses a proposal no
    approval covers and any row without an expectation. A proposal that ``replaces`` a gate
    also deletes the gate's wrapper, its ``lib/`` module and its quick-reference section.
``check``
    Every committed row parses, names a probe with readings, a fixture the probe accepts, a
    facet with its keys, an expectation of the facet's shape and documented tags; no id or fact
    is written twice.

Exit codes: 0 done and clean; 1 refused, or problems found; 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_common.testing.tag_vocabulary import documented_tags
from datrix_testing.cases.approvals import ApprovalError, approval_of, armed_tests_root, proposals_dir
from datrix_testing.cases.authoring import AuthoringError, expectation_of, selector_of, split_tags
from datrix_testing.cases.compare import EXPECTATION_FORM
from datrix_testing.cases.model import Case, CaseFileError, id_segment, require_area
from datrix_testing.cases.parity import (
    FACET_KEY,
    PARITY_FILE_SUFFIX,
    PARITY_STAGE,
    ParityRowError,
    append_parity_rows,
    corpus_problems,
    load_parity_rows,
    probe_axis,
)

from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.test_projects import list_projects
from parity_cases import CASES_DIR, CannotCompare, LiveTargets, ProbeCache, committed_rows, read_row
from parity_observers import PROBE_READINGS, observer_specs

EXIT_OK: Final[int] = 0
EXIT_REFUSED: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The tag every parity row carries.
PARITY_TAG: Final[str] = "parity"
#: The gate families' root, where a replaced gate's wrapper sits.
GATES_DIR: Final[Path] = SCRIPTS_DIR / "gates"
_GATE_SUFFIX: Final[str] = ".ps1"
_LIB_MODULE_RE: Final[re.Pattern[str]] = re.compile(r'"lib\\([A-Za-z0-9_]+\.py)"')
_QUICK_REFERENCE: Final[str] = "quick-reference.md"
_SECTION_RULE: Final[str] = "---"
_PROPOSAL_KIND: Final[str] = "parity"
_CASE_DISPOSITION: Final[str] = "case"
_OBSERVE_REASON: Final[str] = "Observed with parity-cases observe."


class ToolError(ValueError):
    """A command is refused; nothing has been written."""


def _out(*lines: str) -> None:
    sys.stdout.write("".join(f"{line}\n" for line in lines))


@dataclass
class _Session:
    """The targets and the probe cache one command reads through: a fixture is built once per command."""

    targets: LiveTargets = field(default_factory=LiveTargets)
    cache: ProbeCache = field(default_factory=ProbeCache)


_SESSION: Final[_Session] = _Session()


def _readings_of(row: Case) -> dict[str, str]:
    try:
        outcome = read_row(row, _SESSION.targets, _SESSION.cache)
    except CannotCompare as error:
        raise ToolError(f"row {row.id!r} cannot be read: {error}") from error
    readings = {target: reading.rendered() for target, reading in sorted(outcome.readings.items())}
    readings.update({target: f"<n/a: {reason}>" for target, reason in sorted(outcome.not_applicable.items())})
    return readings


def _probe(name: str) -> None:
    probe_axis(name)
    if name not in PROBE_READINGS:
        raise ToolError(f"probe {name!r} has no parity readings; probes with readings: {sorted(PROBE_READINGS)}")


def observe(input_name: str, probe: str, selector_text: str) -> list[str]:
    """Every target's reading of *selector_text* on *probe* for *input_name*."""
    _probe(probe)
    row = Case.model_validate(
        {
            "id": "observe.row",
            "tags": [PARITY_TAG],
            "input": input_name,
            "stage": PARITY_STAGE,
            "observer": probe,
            "selector": selector_of(selector_text),
            "reason": _OBSERVE_REASON,
        }
    )
    facet = PROBE_READINGS[probe].facet_reading(row.selector).facet
    lines = [f"shape: {facet.shape.value} -- write the expectation as {EXPECTATION_FORM[facet.shape]}"]
    lines.extend(f"{target}: {reading}" for target, reading in _readings_of(row).items())
    return lines


def _refuse_while_armed() -> None:
    armed = armed_tests_root()
    if armed is not None and armed == CASES_DIR.resolve():
        raise ToolError(
            f"the approval gate is armed for {CASES_DIR}: a row reaches it only through an approved proposal (accept)."
        )


def _corpus_check(rows: Sequence[Case]) -> None:
    problems = corpus_problems(rows, observer_specs(list_projects()), documented_tags())
    if problems:
        raise ToolError("refused:\n" + "\n".join(f"  {problem}" for problem in problems))


def new(area: str, fields: Mapping[str, str], expectation_text: str) -> Path:
    """Validate, read and append one authored row; the parity file written."""
    _refuse_while_armed()
    require_area(area)
    row = Case.model_validate(
        {
            "id": fields["id"],
            "tags": list(split_tags(fields["tags"])),
            "input": fields["input"],
            "stage": PARITY_STAGE,
            "observer": fields["probe"],
            "selector": selector_of(fields["selector"]),
            "expectation": expectation_of(expectation_text),
            "reason": fields["reason"],
        }
    )
    _corpus_check((*load_parity_rows(CASES_DIR), row))
    for target, reading in _readings_of(row).items():
        _out(f"  {target}: {reading}")
    path = CASES_DIR / f"{area}{PARITY_FILE_SUFFIX}"
    append_parity_rows(path, [row])
    return path


def _offered_selectors(input_name: str, probe: str) -> list[dict[str, object]]:
    readings = PROBE_READINGS[probe]
    targets = _SESSION.targets
    cache = _SESSION.cache
    offered: list[dict[str, object]] = []
    for name, facet in readings.facets.items():
        if facet.offers is None:
            if not facet.facet.keys:
                offered.append({FACET_KEY: name})
            continue
        seen: set[str] = set()
        for target in targets.targets(probe_axis(probe)):
            if targets.not_applicable(target, readings):
                continue
            probe_row = _probe_row(input_name, probe, {FACET_KEY: name})
            for selector in facet.offers(cache.result(targets, target, readings, probe_row)):
                key = json.dumps(selector, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    offered.append({FACET_KEY: name, **selector})
    return offered


def _probe_row(input_name: str, probe: str, selector: Mapping[str, object]) -> Case:
    return Case.model_validate(
        {
            "id": "migrate.row",
            "tags": [PARITY_TAG],
            "input": input_name,
            "stage": PARITY_STAGE,
            "observer": probe,
            "selector": dict(selector),
            "reason": _OBSERVE_REASON,
        }
    )


def _row_id(area: str, selector: Mapping[str, object]) -> str:
    parts = [str(value) for key, value in selector.items() if key != FACET_KEY]
    return ".".join([area, id_segment(str(selector[FACET_KEY])), *(id_segment(part) for part in parts)])


def migrate(input_name: str, probe: str, area: str, tags: Sequence[str], replaces: str) -> Path:
    """Write a proposal of rows (no expectations) for every selector *probe* offers on *input_name*."""
    _probe(probe)
    require_area(area)
    if replaces:
        _gate_files(replaces)
    records: list[dict[str, object]] = []
    for selector in _offered_selectors(input_name, probe):
        case = {
            "id": _row_id(area, selector),
            "tags": [PARITY_TAG, *tags],
            "input": input_name,
            "stage": PARITY_STAGE,
            "observer": probe,
            "selector": selector,
            "reason": "",
        }
        row = _probe_row(input_name, probe, selector)
        records.append({"disposition": _CASE_DISPOSITION, "case": case, "readings": _readings_of(row)})
    document = {"kind": _PROPOSAL_KIND, "area": area, "replaces": replaces, "records": records}
    directory = proposals_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"parity-{area}-{id_segment(probe)}.proposal.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _gate_files(gate: str) -> tuple[Path, Path, Path]:
    """``(wrapper, lib module, quick-reference)`` of the gate named *gate* (its wrapper's name without ``.ps1``).

    Raises:
        ToolError: No family holds exactly one such wrapper, or it names no lib module.
    """
    wrappers = sorted(GATES_DIR.glob(f"*/{gate}{_GATE_SUFFIX}"))
    if len(wrappers) != 1:
        raise ToolError(f"{len(wrappers)} gate wrapper(s) named {gate}{_GATE_SUFFIX} under {GATES_DIR}; exactly one is replaced")
    wrapper = wrappers[0]
    modules = _LIB_MODULE_RE.findall(wrapper.read_text(encoding="utf-8"))
    if len(set(modules)) != 1:
        raise ToolError(f"{wrapper.name} runs {sorted(set(modules))}; a replaced gate runs exactly one lib module")
    return wrapper, wrapper.parent / "lib" / modules[0], wrapper.parent / _QUICK_REFERENCE


def without_section(text: str, wrapper: Path) -> str:
    """*text* (a family quick-reference) without the section headed by *wrapper*'s entry.

    Raises:
        ToolError: The quick-reference has no section for the wrapper.
    """
    heading = f"## `gates\\{wrapper.parent.name}\\{wrapper.name}`"
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip() == heading]
    if len(starts) != 1:
        raise ToolError(f"the quick-reference holds {len(starts)} section(s) headed {heading}; exactly one is removed")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    if end < len(lines):
        # A later section follows: cut through the rule that separates this section from it.
        rule = next((index for index in range(end - 1, start, -1) if lines[index].strip() == _SECTION_RULE), end - 1)
        kept = lines[:start] + lines[rule + 1 :]
    else:
        # The last section: cut from the rule that separates it from the one before.
        rule = next((index for index in range(start - 1, -1, -1) if lines[index].strip() == _SECTION_RULE), start)
        kept = lines[:rule]
    return re.sub(r"\n{3,}", "\n\n", "".join(kept)).rstrip("\n") + "\n"


def _proposal_rows(document: Mapping[str, object]) -> list[Case]:
    records = document["records"] if "records" in document else None
    if not isinstance(records, list) or not records:
        raise ToolError("the proposal holds no records")
    rows: list[Case] = []
    for record in records:
        if not isinstance(record, dict) or record["disposition"] != _CASE_DISPOSITION:
            continue
        case = record["case"]
        if not isinstance(case, dict) or "expectation" not in case:
            label = case["id"] if isinstance(case, dict) and "id" in case else record
            raise ToolError(f"row {label!r} has no expectation: every expectation is authored before accept")
        try:
            rows.append(Case.model_validate(case))
        except ValueError as error:
            raise ToolError(f"a proposed row breaks the case schema: {error}") from error
    return rows


def accept(proposal: Path, cases_dir: Path = CASES_DIR) -> list[str]:
    """Accept the approved parity *proposal*; the lines reporting what was written and deleted."""
    approval_of(proposal)
    document = json.loads(proposal.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document["kind"] != _PROPOSAL_KIND:
        raise ToolError(f"{proposal.name} is not a parity proposal (written by parity-cases migrate)")
    area = require_area(str(document["area"]))
    rows = _proposal_rows(document)
    _corpus_check((*load_parity_rows(cases_dir), *rows))
    replaces = str(document["replaces"]) if document["replaces"] else ""
    # Every refusal happens before anything is written: the gate is resolved and its section cut first.
    removal = _GateRemoval.of(replaces) if replaces else None
    path = cases_dir / f"{area}{PARITY_FILE_SUFFIX}"
    append_parity_rows(path, rows)
    report = [f"Wrote {len(rows)} row(s) to {path}"]
    if removal is not None:
        report.append(removal.apply())
    return report


@dataclass(frozen=True)
class _GateRemoval:
    """A replaced gate's files and its quick-reference text without the gate's section."""

    wrapper: Path
    module: Path
    quick_reference: Path
    trimmed: str

    @classmethod
    def of(cls, gate: str) -> _GateRemoval:
        wrapper, module, quick_reference = _gate_files(gate)
        return cls(wrapper, module, quick_reference, without_section(quick_reference.read_text(encoding="utf-8"), wrapper))

    def apply(self) -> str:
        self.quick_reference.write_text(self.trimmed, encoding="utf-8")
        self.wrapper.unlink()
        self.module.unlink()
        return f"Deleted {self.wrapper.name}, lib/{self.module.name} and its {_QUICK_REFERENCE} section"


def check() -> list[str]:
    """The committed rows' problems; one OK line when there are none."""
    rows = committed_rows()
    return [f"{len(rows)} parity row(s) in {CASES_DIR}", "OK"]


def parser() -> argparse.ArgumentParser:
    """The tool's argument parser."""
    root = argparse.ArgumentParser(prog="parity-cases", description="Author, migrate and check parity rows.")
    commands = root.add_subparsers(dest="command", required=True)
    observe_command = commands.add_parser("observe")
    for name in ("input", "probe", "selector"):
        observe_command.add_argument(name)
    new_command = commands.add_parser("new")
    new_command.add_argument("area")
    for name in ("--id", "--tags", "--input", "--probe", "--selector", "--expectation", "--reason"):
        new_command.add_argument(name, required=True)
    migrate_command = commands.add_parser("migrate")
    migrate_command.add_argument("input")
    migrate_command.add_argument("probe")
    migrate_command.add_argument("--area", required=True)
    migrate_command.add_argument("--tags", default="")
    migrate_command.add_argument("--replaces", default="")
    accept_command = commands.add_parser("accept")
    accept_command.add_argument("proposal")
    commands.add_parser("check")
    return root


def _run(arguments: argparse.Namespace) -> list[str]:
    if arguments.command == "observe":
        return observe(arguments.input, arguments.probe, arguments.selector)
    if arguments.command == "new":
        fields = {name: getattr(arguments, name) for name in ("id", "tags", "input", "probe", "selector", "reason")}
        return [f"Added {arguments.id} to {new(arguments.area, fields, arguments.expectation)}"]
    if arguments.command == "migrate":
        path = migrate(arguments.input, arguments.probe, arguments.area, split_tags(arguments.tags), arguments.replaces)
        return [f"Proposal: {path}", "Author every expectation and reason; Jon approves it before accept."]
    if arguments.command == "accept":
        return accept(Path(arguments.proposal))
    return check()


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; its exit code."""
    arguments = parser().parse_args(argv)
    try:
        _out(*_run(arguments))
    except (ToolError, ApprovalError, AuthoringError, CaseFileError, ParityRowError, KeyError, ValueError) as error:
        _out(f"Refused: {error}")
        return EXIT_REFUSED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
