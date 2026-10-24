"""The checking phases of /absorb-design: did every unit of the design land in the docs, and what still
points at the design.

TRANSFER CHECK (a lead, cited)
    For each section of the design, a local model reads the target docs and answers PRESENT, PARTIAL
    or MISSING, citing the target lines that carry it. Citations are checked against what it was sent.
    The skill reads the PARTIAL and MISSING units itself; PRESENT ones it spot-checks by citation.

REFERENCES (exact)
    Every line in the framework repositories (and any extra paths named) that mentions the design's
    file name, its stem, its title or its number in a design-reference form (the word "design" or
    "design doc" followed by the number, or "design/" and the number), and every line of another design
    in the design folder that names it, by those forms or by its bare number as its file name spells it
    ("090 D1"). Task folders are not searched: they are gitignored orchestration files that may cite
    designs.

DELETE (exact)
    Deletes the design only when it lies in the workspace's design folder, its deletion licence holds
    and no line names it any more. The licence is, in order: a verify proof (the saved replies of
    /verify-implementation whose last "Design conformance:" line reads PROVEN and which name this
    design), or the design's own Status line reading Implemented, or the skill's statement that the
    design is knowledge only.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.framework_repos import framework_repos
from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.local_reading import ReadScope, ask_local, read_section
# The chain (datrix_scripts.skill.chain) writes the verify proof as .tmp/verify-proven-<design stem>.md and
# reads its verdict with the same pattern.
from datrix_scripts.skill.chain import PROOF_PREFIX, PROVEN, VERDICT_PATTERN
from datrix_scripts.skill.common import (
    EXIT_CHECK_FAILED,
    EXIT_FAILED,
    EXIT_OK,
    ContentFilter,
    markdown_sections,
    parallel,
    read_text,
    workspace_label,
)

LOG = logging.getLogger(__name__)

SEARCH_SUFFIXES = frozenset({".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml", ".toml", ".ps1", ".psm1",
                             ".j2", ".txt", ".dtrx", ".mjs"})
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tasks", ".test_results",
                       ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build", "out", ".state"})
MAX_SEARCH_BYTES = 2_000_000
MIN_TITLE_CHARS = 20
MAX_UNIT_CHARS = 8000
_DESIGN_NUMBER = re.compile(r"^(\d{2,4})[-_]")
_TITLE_PREFIX = re.compile(r"^\s*#\s+(?:\d+\s*[:.-]\s*)?")
VERDICT_PRESENT = "PRESENT"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_MISSING = "MISSING"
VERDICTS = (VERDICT_PRESENT, VERDICT_PARTIAL, VERDICT_MISSING)
TRANSFER_QUESTION = (
    "This section of a design document is being moved into the documentation files you are given:\n\n"
    "----- design section -----\n{unit}\n----- end -----\n\n"
    "Is its knowledge (each rule, decision, contract and fact it states) present in these files? Wording may "
    "differ. Begin your answer with exactly one of PRESENT, PARTIAL or MISSING on its own line. Then, in at "
    "most 6 lines, cite path:line where each part is stated, and for PARTIAL name what is absent.")
DESIGN_DIR = "design"
DESIGN_SUFFIX = ".md"
_STATUS_LINE = re.compile(r"^\W*Status:\W*(\w+)", re.MULTILINE)
STATUS_IMPLEMENTED = "implemented"


@dataclass(frozen=True)
class Reference:
    file: str
    line: int
    text: str
    matched: str


@dataclass(frozen=True)
class UnitCheck:
    heading: str
    first: int
    last: int
    verdict: str
    answer: str


def design_identifiers(design: Path) -> tuple[list[str], re.Pattern[str] | None]:
    """The literal strings that name the design, and the pattern for its number in a reference form."""
    literals = [design.name, design.stem]
    lines = read_text(design).splitlines()
    title = next((_TITLE_PREFIX.sub("", line).strip() for line in lines if line.lstrip().startswith("# ")), "")
    if len(title) >= MIN_TITLE_CHARS:
        literals.append(title)
    match = _DESIGN_NUMBER.match(design.name)
    number = None
    if match:
        digits = match.group(1).lstrip("0") or "0"
        number = re.compile(rf"\bdesign(?:\s+doc(?:ument)?)?[\s/#:-]*0*{digits}\b", re.IGNORECASE)
    return literals, number


def _searchable(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    found: list[Path] = []
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS]
        found += [Path(directory) / name for name in files if Path(name).suffix.lower() in SEARCH_SUFFIXES]
    return found


def _matches(line: str, literals: list[str], number: re.Pattern[str] | None) -> str:
    lowered = line.lower()
    for literal in literals:
        if literal.lower() in lowered:
            return literal
    hit = number.search(line) if number else None
    return hit.group(0) if hit else ""


def sibling_number(design: Path) -> re.Pattern[str] | None:
    """How another design of the folder names *design*: its number as the file name spells it (``090 D1``,
    ``090 §4``, ``090's gate``), the form the design series uses for each other."""
    match = _DESIGN_NUMBER.match(design.name)
    return re.compile(rf"(?<![\w.]){re.escape(match.group(1))}(?![\w.])") if match else None


def _references_in(workspace: Path, path: Path, literals: list[str], number: re.Pattern[str] | None) -> list[Reference]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    found: list[Reference] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        matched = _matches(line, literals, number)
        if matched:
            found.append(Reference(workspace_label(workspace, path), line_number, line.strip(), matched))
    return found


def find_references(workspace: Path, design: Path, extra: list[Path]) -> list[Reference]:
    """Every line that names the design, across the framework repositories, the extra paths and the other
    designs of its folder (which also name it by its bare number)."""
    literals, number = design_identifiers(design)
    own = design.resolve()
    found: list[Reference] = []
    for root in [*framework_repos(workspace), *extra]:
        for path in _searchable(root):
            if path.resolve() != own and path.stat().st_size <= MAX_SEARCH_BYTES:
                found += _references_in(workspace, path, literals, number)
    siblings = sibling_number(design)
    if design.parent.name == DESIGN_DIR and siblings is not None:
        for path in sorted(design.parent.glob(f"*{DESIGN_SUFFIX}")):
            if path.resolve() != own:
                found += _references_in(workspace, path, literals, siblings)
    return found


def render_references(design_label: str, references: list[Reference]) -> str:
    if not references:
        return f"No line in the framework repositories, the extra paths or the other designs names {design_label}.\n"
    lines = [f"{len(references)} line(s) name {design_label}. Replace each with a pointer to where the content "
             "now lives, or remove it:", ""]
    lines += [f"- {r.file}:{r.line} (matched `{r.matched}`): {r.text}" for r in references]
    return "\n".join(lines) + "\n"


def _proof_failures(design: Path, proof: Path) -> list[str]:
    """Why ``proof`` does not prove ``design``; empty when its last verdict is PROVEN and it names the design."""
    if not proof.is_file():
        return [f"the verify proof {proof} does not exist: /verify-implementation must run again"]
    text = read_text(proof)
    verdicts = VERDICT_PATTERN.findall(text)
    reasons: list[str] = []
    if not verdicts:
        reasons.append(f"the verify proof {proof} carries no 'Design conformance:' line: verify must run again")
    elif verdicts[-1] != PROVEN:
        reasons.append(f"the verify proof {proof} ends 'Design conformance: {verdicts[-1]}', not PROVEN: "
                       "verify must run again")
    if proof.name != f"{PROOF_PREFIX}{design.stem}{DESIGN_SUFFIX}" and design.stem not in text:
        reasons.append(f"the verify proof {proof} names another design: pass {PROOF_PREFIX}{design.stem}"
                       f"{DESIGN_SUFFIX}, or a proof whose text names {design.name}")
    return reasons


def licence_failures(design: Path, proof: Path | None, knowledge_only: bool) -> list[str]:
    """Why the deletion licence does not hold; empty when it does (proof, else Status: Implemented, else
    the skill's statement that the design is knowledge only)."""
    if proof is not None:
        return _proof_failures(design, proof)
    if knowledge_only:
        return []
    status = _STATUS_LINE.search(read_text(design))
    if status and status.group(1).lower() == STATUS_IMPLEMENTED:
        return []
    found = f"its Status line reads '{status.group(1)}'" if status else "it has no Status line"
    return [f"no deletion licence: no --verified proof was passed, --knowledge-only was not given, and {found}, "
            "not Implemented. Pass the verify-proven file, or keep the design and ask Jon whether to delete it"]


def delete_design(workspace: Path, design: Path, proof: Path | None, knowledge_only: bool,
                  extra: list[Path]) -> tuple[str, int]:
    """Delete ``design`` when it is in the design folder, its licence holds and no line names it."""
    design_root = (workspace / DESIGN_DIR).resolve()
    if not design.is_relative_to(design_root) or design.suffix.lower() != DESIGN_SUFFIX:
        return (f"Refused: {design} is not a {DESIGN_SUFFIX} file under {design_root}. absorb-delete deletes "
                "only design documents; pass a file in the workspace's design folder."), EXIT_FAILED
    label = workspace_label(workspace, design)
    reasons = licence_failures(design, proof, knowledge_only)
    references = find_references(workspace, design, extra)
    if references:
        reasons.append(render_references(label, references).rstrip())
    if reasons:
        return "\n".join([f"Not deleted: {label}", *(f"  - {reason}" for reason in reasons)]), EXIT_CHECK_FAILED
    design.unlink()
    LOG.info("Deleted design %s", design)
    return f"Deleted: {label}", EXIT_OK


def _verdict(text: str) -> str:
    first = text.strip().splitlines()[0].strip().upper() if text.strip() else ""
    return next((v for v in VERDICTS if first.startswith(v)), VERDICT_MISSING)


def transfer_check(workspace: Path, pool: LocalLlmPool, design: Path, targets: list[str]) -> list[UnitCheck]:
    """For each section of the design that carries text: is it present in the target docs? (leads)."""
    scope = ReadScope(workspace)
    sections = [read_section(scope, path) for path in scope.files(targets)]
    text = read_text(design)
    lines = text.splitlines()
    filtered = ContentFilter(workspace).section(workspace_label(workspace, design), text)
    units = [s for s in markdown_sections(lines, max_level=3)
             if any(line.strip() for line in lines[s.start:s.end])]

    def ask(unit_index: int) -> UnitCheck:
        unit = units[unit_index]
        body = "\n".join(line.split("| ", 1)[-1] for line in filtered.lines[unit.start - 1:unit.end])
        answer = ask_local(pool, TRANSFER_QUESTION.format(unit=body[:MAX_UNIT_CHARS]), sections)
        return UnitCheck(unit.heading or "(preamble)", unit.start, unit.end, _verdict(answer.text), answer.render())

    return parallel(list(range(len(units))), ask)


def render_transfer(design_label: str, checks: list[UnitCheck]) -> str:
    short = [c for c in checks if c.verdict != VERDICT_PRESENT]
    lines = [f"# Transfer check -- {design_label}", "",
             f"{len(checks)} section(s): {len(checks) - len(short)} present, {len(short)} partial or missing "
             "(local-model leads, citations checked).", ""]
    for check in [*short, *[c for c in checks if c.verdict == VERDICT_PRESENT]]:
        lines += [f"## {check.verdict}: {check.heading} ({design_label}:{check.first}-{check.last})", "",
                  check.answer, ""]
    return "\n".join(lines) + "\n"
