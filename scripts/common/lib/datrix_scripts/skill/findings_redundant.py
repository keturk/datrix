"""The mechanical and model halves of /delete-redundant-findings: which findings files add nothing beyond
another file, and the deletion of the ones the skill confirms.

FILES
    The findings are the ``*.md`` directly in the folder given (the inbox) and in its subfolders (the area
    folders ``organize-findings.ps1`` fills), compared across all of them. A file is named by its path under
    the folder, ``azure/<name>.md``; pointers to it elsewhere name its stem.

REDUNDANT (a lead, checked)
    A file is a candidate for deletion when it holds one finding (a raw file, or a theme file with at most
    one section) and another file's unit -- a raw file, or one ``## N.`` section of a theme file -- of higher
    rank could state the same defect. A unit is a candidate survivor when it cites every ``path:line`` and
    backticked path the file cites, or when the two share enough of their words. A local model then reads both
    texts and answers SAME, PARTIAL or DIFFERENT; SAME stands only when the model lists nothing the doomed file
    has that the survivor lacks, and quotes one line of each file that really occurs in that file. Everything
    else stays. A proposal is marked for deletion only when the survivor also cites everything the doomed file
    cites; a pair that matches by words alone is reported with the citations the survivor lacks.

    Rank orders the files by citations, then length, then name (the earlier name survives a tie), so two
    copies never doom each other and a doomed file's survivor is never itself doomed.

DELETE (exact)
    Deletes the proposals the skill left marked for deletion, and only when the doomed file is unchanged since
    it was judged (its hash), the survivor still cites everything the doomed file cites, no other findings
    file names a doomed file, and ``check_consolidation`` passes. Otherwise nothing is deleted.

A proposal is never deleted on the model's word alone: the plan names the doomed file's hash, the skill reads
both files, and the delete step proves the rest.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.skill.common import (
    AssistError,
    ContentFilter,
    ask_json,
    markdown_sections,
    parallel,
    read_text,
    section_body,
    string_list,
)
from datrix_scripts.skill.finding_inbox import inbox_markdown, referrers
from datrix_scripts.skill.findings import check_consolidation, references, render_check

LOG = logging.getLogger(__name__)

VERDICT_SAME = "SAME"
VERDICT_PARTIAL = "PARTIAL"
VERDICT_DIFFERENT = "DIFFERENT"
VERDICT_UNCLEAR = "UNCLEAR"
_VERDICTS = (VERDICT_SAME, VERDICT_PARTIAL, VERDICT_DIFFERENT)

SURVIVORS_PER_FILE = 3
LEXICAL_THRESHOLD = 0.25
MIN_WORD_CHARS = 4
SECTION_LEVEL = 2

_WORD = re.compile(rf"\w{{{MIN_WORD_CHARS},}}")
_LINE_NUMBER = re.compile(r"^\d+\|\s*")
_BLANKS = re.compile(r"\s+")
# A theme file's sections are "## 3. Title"; a raw file's "## Issue" / "## Impact" are parts of one finding.
_NUMBERED_HEADING = re.compile(r"\d+\.\s")

JUDGE_SYSTEM = (
    "You compare two findings files from Datrix, a multi-language code generator. FIRST is a candidate for "
    "deletion; SECOND stays. Answer SAME only when SECOND states the same defect as FIRST (the same root cause, "
    "or the same wrong behaviour of the same construct, on every target FIRST names) AND everything FIRST says "
    "-- each claim, symptom, impact, location and suggested direction -- is also in SECOND. Answer PARTIAL when "
    "it is the same defect but FIRST carries something SECOND lacks: list each such thing in unique_in_first. "
    "Answer DIFFERENT for a different defect, even on the same seam, package or fix site. Quote one line of "
    "FIRST and one line of SECOND that show the match, copied exactly and without line numbers. Use only what "
    "the files say. Lines are numbered 'N| text'; never copy the numbers.")

JUDGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(_VERDICTS)},
        "unique_in_first": {"type": "array", "items": {"type": "string"}},
        "quote_first": {"type": "string"},
        "quote_second": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "unique_in_first", "quote_first", "quote_second", "reason"],
}


@dataclass(frozen=True)
class Unit:
    """One finding's text: a whole raw file, or one ``##`` section of a theme file."""

    file: str
    heading: str
    text: str
    refs: frozenset[str]
    words: frozenset[str]

    @property
    def label(self) -> str:
        return f"{self.file} {self.heading}".strip()


@dataclass(frozen=True)
class FileUnits:
    name: str
    text: str
    units: tuple[Unit, ...]
    refs: frozenset[str]


@dataclass(frozen=True)
class Judgement:
    verdict: str
    reason: str
    notes: tuple[str, ...] = ()


@dataclass
class Proposal:
    """One doomed file, the file and section that already say everything it says, and the evidence."""

    doomed: str
    survivor: str
    section: str
    verdict: str
    reason: str
    exact: str
    sha256: str
    delete: bool
    notes: list[str] = field(default_factory=list)
    referrers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Kept:
    """A pair that looked alike and stays."""

    file: str
    other: str
    verdict: str
    reason: str


@dataclass
class Redundancy:
    proposals: list[Proposal] = field(default_factory=list)
    kept: list[Kept] = field(default_factory=list)
    multi_section: list[str] = field(default_factory=list)
    candidates: int = 0
    files: int = 0
    unjudged: list[Kept] = field(default_factory=list)


@dataclass
class DeleteResult:
    deleted: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    check_report: str = ""

    @property
    def passed(self) -> bool:
        return not self.problems


def _words(text: str) -> frozenset[str]:
    return frozenset(word.lower() for word in _WORD.findall(text))


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 0.0


def _unit(name: str, heading: str, text: str) -> Unit:
    return Unit(name, heading, text, frozenset(references(text)), _words(text))


def _relative_name(directory: Path, path: Path) -> str:
    """The id of a findings file: its path under ``directory`` (the inbox) in posix form."""
    return path.resolve().relative_to(directory.resolve()).as_posix()


def _squash(text: str) -> str:
    return _BLANKS.sub(" ", text).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_units(name: str, text: str) -> FileUnits:
    """The units of one file: its ``##`` sections when it has two or more, else the whole file."""
    lines = text.splitlines()
    sections = [s for s in markdown_sections(lines, SECTION_LEVEL)
                if s.level == SECTION_LEVEL and _NUMBERED_HEADING.match(s.heading)]
    if len(sections) < 2:
        return FileUnits(name, text, (_unit(name, "", text),), frozenset(references(text)))
    units = [_unit(name, s.heading, "\n".join(lines[s.start - 1:s.end])) for s in sections]
    return FileUnits(name, text, tuple(units), frozenset(references(text)))


def _ranked(files: list[FileUnits]) -> list[FileUnits]:
    """Lowest rank first. More citations, then more text, outranks; on a tie the earlier name does."""
    by_name = sorted(files, key=lambda f: f.name, reverse=True)
    return sorted(by_name, key=lambda f: (len(f.refs), len(f.text)))


def _candidates(doomed: Unit, higher: list[FileUnits]) -> list[Unit]:
    """The units of higher-ranked files that could say everything ``doomed`` says, nearest first."""
    scored = [(_similarity(doomed.words, u.words), u) for f in higher for u in f.units]
    near = [(score, u) for score, u in scored if score >= LEXICAL_THRESHOLD or (doomed.refs and doomed.refs <= u.refs)]
    near.sort(key=lambda pair: pair[0], reverse=True)
    return [u for _score, u in near[:SURVIVORS_PER_FILE]]


def _quote_in(quote: str, text: str) -> bool:
    cleaned = _squash(_LINE_NUMBER.sub("", quote))
    return bool(cleaned) and cleaned in _squash(text)


def _check_answer(answer: dict[str, object], doomed: Unit, survivor: Unit) -> Judgement:
    """The model's answer, kept only as far as it holds against the two texts."""
    verdict = str(answer.get("verdict", "")).upper()
    reason = str(answer.get("reason", "")).strip()
    if verdict not in _VERDICTS:
        return Judgement(VERDICT_UNCLEAR, reason, ("the model gave no usable verdict",))
    if verdict != VERDICT_SAME:
        return Judgement(verdict, reason)
    unique = string_list(answer.get("unique_in_first"))
    if unique:
        return Judgement(VERDICT_PARTIAL, reason, tuple(f"only in the doomed file: {item}" for item in unique))
    quotes = (("doomed", str(answer.get("quote_first", "")), doomed.text),
              ("survivor", str(answer.get("quote_second", "")), survivor.text))
    missing = [name for name, quote, text in quotes if not _quote_in(quote, text)]
    if missing:
        return Judgement(VERDICT_UNCLEAR, reason,
                         tuple(f"the model's {name} quote does not occur in that file" for name in missing))
    return Judgement(VERDICT_SAME, reason)


def judge(pool: LocalLlmPool, content: ContentFilter, doomed: Unit, survivor: Unit) -> Judgement:
    """Ask a local model whether ``survivor`` already says everything ``doomed`` says."""
    first = content.section(doomed.label, doomed.text)
    second = content.section(survivor.label, survivor.text)
    prompt = "FIRST (candidate for deletion):\n" + section_body(first) + "\n\nSECOND (stays):\n" + section_body(second)
    result = _check_answer(ask_json(pool, JUDGE_SYSTEM, prompt, JUDGE_SCHEMA), doomed, survivor)
    withheld = tuple(note for note in (first.note, second.note) if note)
    if withheld and result.verdict == VERDICT_SAME:
        return Judgement(VERDICT_UNCLEAR, result.reason, withheld)
    return Judgement(result.verdict, result.reason, result.notes + withheld)


def _proposal(directory: Path, doomed: FileUnits, survivor: Unit, judgement: Judgement) -> Proposal:
    unit = doomed.units[0]
    notes = list(judgement.notes)
    lost = sorted(unit.refs - survivor.refs)
    if not unit.refs:
        exact = "no citations to compare"
        notes.append("the file cites nothing, so the check cannot prove the match: read both files")
    elif lost:
        exact = "the survivor lacks " + ", ".join(f"`{item}`" for item in lost)
        notes.append("if those citations are evidence of the same defect, add them to the survivor and run "
                     "findings-redundant again; if not, the file is not redundant")
    else:
        exact = "survivor cites every citation of the doomed file"
    return Proposal(doomed.name, survivor.file, survivor.heading, judgement.verdict, judgement.reason, exact,
                    _sha256(doomed.text), bool(unit.refs) and not notes, notes,
                    referrers(directory / doomed.name, directory))


def find_redundant(directory: Path, pool: LocalLlmPool | None, content: ContentFilter | None) -> Redundancy:
    """Every file another file already covers. ``pool`` None lists the candidates without a model."""
    files = [file_units(_relative_name(directory, path), read_text(path)) for path in inbox_markdown(directory)]
    ranked = _ranked(files)
    result = Redundancy(files=len(files))
    jobs: list[tuple[int, FileUnits, Unit]] = []
    for index, doomed in enumerate(ranked):
        if len(doomed.units) > 1:
            result.multi_section.append(doomed.name)
            continue
        jobs += [(index, doomed, survivor) for survivor in _candidates(doomed.units[0], ranked[index + 1:])]
    result.candidates = len(jobs)
    if pool is None or content is None:
        result.unjudged = [Kept(doomed.name, survivor.label, "", "") for _index, doomed, survivor in jobs]
        return result
    judged = parallel(jobs, lambda job: judge(pool, content, job[1].units[0], job[2]))
    doomed_names: set[str] = set()
    pairs = sorted(zip(jobs, judged, strict=True), key=lambda pair: pair[0][0], reverse=True)
    for (_index, doomed, survivor), judgement in pairs:
        if judgement.verdict == VERDICT_SAME and doomed.name not in doomed_names \
                and survivor.file not in doomed_names:
            doomed_names.add(doomed.name)
            result.proposals.append(_proposal(directory, doomed, survivor, judgement))
        else:
            result.kept.append(Kept(doomed.name, survivor.label, judgement.verdict, judgement.reason))
    result.kept = [k for k in result.kept if k.file not in doomed_names]
    result.proposals.sort(key=lambda p: p.doomed)
    return result


def plan_json(result: Redundancy) -> str:
    return json.dumps({"proposals": [asdict(p) for p in result.proposals]}, indent=2) + "\n"


def load_plan(path: Path) -> list[Proposal]:
    """The proposals of a plan file, as the skill left them; refuses a file that is not one."""
    try:
        data = json.loads(read_text(path))
        return [Proposal(**item) for item in data["proposals"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise AssistError(f"'{path}' is not a findings-redundant plan ({exc}). Pass the plan "
                          "findings-redundant wrote.") from exc


def render(result: Redundancy, plan: Path | None) -> str:
    lines = ["# Redundant findings", "",
             f"{result.files} file(s); {result.candidates} candidate pair(s); {len(result.proposals)} proposed "
             f"for deletion, {len(result.kept)} pair(s) that looked alike and stay. "
             + ("No model judged them." if result.unjudged else
                "A local model judged each pair and its quotes were checked against the files; it is a lead.")]
    if plan is not None:
        lines += ["", f"Plan: `{plan}`. Set `delete` to false for every proposal you reject after reading both "
                      "files, then run `findings-redundant-delete`."]
    lines += ["", "## Proposed for deletion", ""] if result.proposals else []
    for p in result.proposals:
        where = f"{p.survivor} {p.section}".strip()
        lines += [f"- **{p.doomed}** -> {where} | delete: {str(p.delete).lower()} | {p.exact}",
                  f"  - model: {p.reason}"]
        lines += [f"  - note: {note}" for note in p.notes]
        if p.referrers:
            lines.append(f"  - named by {', '.join(p.referrers)}: repoint those mentions before deleting")
    lines += ["", "## Candidate pairs, not judged (read both files of each)", ""] if result.unjudged else []
    lines += [f"- {k.file} may be covered by {k.other}" for k in result.unjudged]
    lines += ["", "## Looked alike, kept", ""] if result.kept else []
    lines += [f"- {k.file} vs {k.other}: {k.verdict} -- {k.reason}" for k in result.kept]
    if result.multi_section:
        lines += ["", "## Never deleted here (several sections)", ""] + [f"- {name}" for name in result.multi_section]
    return "\n".join(lines) + "\n"


def delete_redundant(directory: Path, proposals: list[Proposal]) -> DeleteResult:
    """Delete the proposals still marked for deletion, or nothing at all when any proof fails."""
    chosen = [p for p in proposals if p.delete]
    result = DeleteResult()
    doomed_names = {p.doomed for p in chosen}
    for p in chosen:
        problem = _blocker(directory, p, doomed_names)
        if problem:
            result.problems.append(f"{p.doomed}: {problem}")
    if chosen and not result.problems:
        check = check_consolidation(directory, [directory / p.doomed for p in chosen], raw_may_remain=True,
                                    scope=inbox_markdown(directory))
        result.check_report = render_check(check)
        if not check.passed:
            result.problems.append("findings-check failed; nothing deleted.")
    if chosen and not result.problems:
        for p in chosen:
            (directory / p.doomed).unlink()
            result.deleted.append(p.doomed)
    return result


def _blocker(directory: Path, proposal: Proposal, doomed_names: set[str]) -> str:
    """The reason this proposal cannot be carried out; empty when every proof holds."""
    doomed, survivor = directory / proposal.doomed, directory / proposal.survivor
    outside = [p for p in (doomed, survivor) if not p.resolve().is_relative_to(directory.resolve())]
    if outside:
        return f"{outside[0].name} is outside the findings folder"
    if not doomed.is_file():
        return "the file does not exist"
    if _sha256(read_text(doomed)) != proposal.sha256:
        return "the file changed since it was judged; run findings-redundant again"
    if proposal.survivor in doomed_names:
        return f"its survivor {proposal.survivor} is itself being deleted"
    if not survivor.is_file():
        return f"its survivor {proposal.survivor} does not exist"
    lost = sorted(references(read_text(doomed)) - references(read_text(survivor)))
    if lost:
        return "the survivor does not cite " + ", ".join(f"`{item}`" for item in lost)
    named_by = [name for name in referrers(doomed, directory) if name not in doomed_names]
    if named_by:
        return f"named by {', '.join(named_by)}: repoint those mentions to {proposal.survivor}"
    return ""
