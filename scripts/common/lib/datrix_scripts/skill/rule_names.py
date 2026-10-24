"""Names for unnamed ``validate`` rules: proposed by a local model, checked exactly, applied only on request.

A rule the database can enforce needs a name, its check constraint's subject. The implementer collects the
rules analysis refuses for lacking one (``path:line`` sites) and passes them here. A local model reads each
file's rules and proposes a camelCase name per rule, saying what the rule ensures. Every proposal is checked
before it is offered:

* the name is a camelCase identifier of 3..40 characters;
* it is unique among the proposals for its entity and collides with no identifier the entity already uses;
* the site's line still holds the rule's first line, and that line carries no name yet.

A rule whose text carries a registered customer term never reaches a model; it is listed for the implementer
to name. ``--apply`` writes only the proposals that passed, each only while its line is unchanged.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.skill.common import (
    AssistError,
    ContentFilter,
    ask_json,
    object_list,
    parallel,
    read_text,
    workspace_label,
)

LOG = logging.getLogger(__name__)

MAX_RULE_LINES: Final = 8
STATUS_OK: Final = "ok"
STATUS_WITHHELD: Final = "withheld"
_NAME: Final = re.compile(r"^[a-z][A-Za-z0-9]{2,39}$")
_NAMED_RULE: Final = re.compile(r"^\s*[A-Za-z_]\w*\s*:(?!:)")
_ENTITY: Final = re.compile(r"^\s*(?:abstract\s+)?entity\s+([A-Za-z_]\w*)")
_IDENTIFIER: Final = re.compile(r"\b[A-Za-z_]\w*\b")
_SITE: Final = re.compile(r"^(.+):(\d+)$")

NAME_SYSTEM: Final = (
    "You name validation rules of a domain model. Each rule is numbered 'N| text'. For EVERY rule give a "
    "camelCase name (letters and digits, starting lowercase, 3 to 40 characters) saying what the rule "
    "ensures, such as positivePrice or totalCoversSubtotal. Use the entity's own field names. Never reuse a "
    "name for two rules of one entity.")
NAME_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {"names": {"type": "array", "items": {
        "type": "object",
        "properties": {"line": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["line", "name"]}}},
    "required": ["names"],
}


@dataclass(frozen=True)
class RuleSite:
    path: Path
    line: int
    entity: str
    entity_identifiers: frozenset[str]
    rule: str
    first_line: str


@dataclass(frozen=True)
class Proposal:
    site: RuleSite
    name: str
    status: str

    @property
    def named_line(self) -> str:
        """The rule's first line with the name before the rule, the indentation kept."""
        text = self.site.first_line
        indent = text[: len(text) - len(text.lstrip())]
        return f"{indent}{self.name}: {text.lstrip()}"


def _resolve(workspace: Path, spec: str) -> tuple[Path, int]:
    match = _SITE.match(spec.strip())
    if match is None:
        raise AssistError(f"'{spec}' is not a rule site. Pass path:line, e.g. "
                          "datrix/examples/shop/system.dtrx:42.")
    path = Path(match.group(1))
    path = path if path.is_absolute() else workspace / path
    if not path.is_file():
        raise AssistError(f"Rule site '{spec}': {path} is not a file. Pass an existing .dtrx path.")
    return path.resolve(), int(match.group(2))


def _entity_of(lines: Sequence[str], index: int) -> tuple[str, frozenset[str]]:
    """The enclosing entity's name and every identifier its text uses (up to the next entity), scanning up
    from ``index``."""
    for start in range(index, -1, -1):
        match = _ENTITY.match(lines[start])
        if match:
            end = next((i for i in range(start + 1, len(lines)) if _ENTITY.match(lines[i])), len(lines))
            return match.group(1), frozenset(_IDENTIFIER.findall("\n".join(lines[start:end])))
    raise AssistError(f"Line {index + 1} lies in no 'entity' declaration; a validate rule belongs to an entity.")


def read_site(workspace: Path, spec: str) -> RuleSite:
    """The rule at ``spec`` (``path:line``): its text up to the closing ``;`` and its entity."""
    path, number = _resolve(workspace, spec)
    lines = read_text(path).replace("\r\n", "\n").split("\n")
    if not 1 <= number <= len(lines) or not lines[number - 1].strip():
        raise AssistError(f"{spec}: line {number} holds no rule (the file has {len(lines)} lines).")
    if _NAMED_RULE.match(lines[number - 1]):
        raise AssistError(f"{spec}: the rule already carries a name: {lines[number - 1].strip()!r}.")
    rule_lines = []
    for line in lines[number - 1: number - 1 + MAX_RULE_LINES]:
        rule_lines.append(line.strip())
        if line.rstrip().endswith(";"):
            break
    entity, identifiers = _entity_of(lines, number - 1)
    return RuleSite(path, number, entity, identifiers, " ".join(rule_lines), lines[number - 1])


def _check_names(proposals: Sequence[Proposal]) -> list[Proposal]:
    """Each proposal with its status: ``ok``, or why its name cannot be used."""
    checked: list[Proposal] = []
    taken: dict[tuple[Path, str], set[str]] = {}
    for proposal in proposals:
        if proposal.status != STATUS_OK:
            checked.append(proposal)
            continue
        key = (proposal.site.path, proposal.site.entity)
        used = taken.setdefault(key, set())
        checked.append(replace(proposal, status=_name_status(proposal, used)))
        used.add(proposal.name)
    return checked


def _name_status(proposal: Proposal, used: set[str]) -> str:
    if not _NAME.match(proposal.name):
        return f"not a camelCase identifier of 3..40 characters: {proposal.name!r}"
    if proposal.name in used:
        return f"repeats another rule's name in entity {proposal.site.entity}"
    if proposal.name in proposal.site.entity_identifiers:
        return f"collides with an identifier entity {proposal.site.entity} already uses"
    return STATUS_OK


def _ask_file(pool: LocalLlmPool, sites: Sequence[RuleSite]) -> list[Proposal]:
    user = "\n".join(f"{site.line}| entity {site.entity}: {site.rule}" for site in sites)
    answer = ask_json(pool, NAME_SYSTEM, user, NAME_SCHEMA)
    names = {item.get("line"): str(item.get("name", "")).strip() for item in object_list(answer.get("names"))}
    return [Proposal(site, names[site.line], STATUS_OK) if site.line in names
            else Proposal(site, "", "the model proposed no name") for site in sites]


def propose_names(workspace: Path, pool: LocalLlmPool, specs: Sequence[str]) -> list[Proposal]:
    """A checked name proposal for every rule site, the model asked once per file."""
    sites = [read_site(workspace, spec) for spec in specs]
    content = ContentFilter(workspace)
    withheld = [Proposal(site, "", STATUS_WITHHELD) for site in sites if content.carries_term(site.rule)]
    by_file: dict[Path, list[RuleSite]] = {}
    for site in sites:
        if not content.carries_term(site.rule):
            by_file.setdefault(site.path, []).append(site)
    asked = parallel(list(by_file.values()), lambda group: _ask_file(pool, group))
    return _check_names([proposal for group in asked for proposal in group]) + withheld


def apply_names(proposals: Sequence[Proposal]) -> list[str]:
    """Write every ``ok`` proposal whose line is unchanged; the sites written, as ``path:line``."""
    written: list[str] = []
    by_file: dict[Path, list[Proposal]] = {}
    for proposal in proposals:
        if proposal.status == STATUS_OK:
            by_file.setdefault(proposal.site.path, []).append(proposal)
    for path, group in by_file.items():
        raw = path.read_text(encoding="utf-8")
        newline = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.replace("\r\n", "\n").split("\n")
        for proposal in group:
            if lines[proposal.site.line - 1] != proposal.site.first_line:
                raise AssistError(f"{path}:{proposal.site.line} changed since the proposal was made; run "
                                  "rule-names again before --apply.")
            lines[proposal.site.line - 1] = proposal.named_line
            written.append(f"{path}:{proposal.site.line}")
        path.write_text(newline.join(lines), encoding="utf-8", newline="")
    return written


def render_proposals(workspace: Path, proposals: Sequence[Proposal], written: Sequence[str]) -> str:
    ok = sum(1 for proposal in proposals if proposal.status == STATUS_OK)
    lines = ["# Rule names", "", f"{ok} of {len(proposals)} proposal(s) passed the checks; "
             f"{len(written)} written.", "", "| Site | Entity | Name | Status | Rule |", "|---|---|---|---|---|"]
    lines += [f"| {workspace_label(workspace, p.site.path)}:{p.site.line} | {p.site.entity} | `{p.name}` | "
              f"{p.status} | `{p.site.rule}` |" for p in proposals]
    return "\n".join(lines) + "\n"
