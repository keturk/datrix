"""The mechanical half of /consolidate-findings: the atomic-finding index, and the no-loss check.

INDEX (a lead, checked)
    A local model splits each findings file into atomic findings -- one defect, one root cause --
    and names the seam each sits on, the owning packages and the ``path:line`` citations it carries.
    The script then checks the split against the file: a citation the model lists that the file does
    not contain is reported as invented, and a citation the file contains that no finding carries is
    reported as unassigned. The skill groups themes from the index instead of deriving it by hand.

CHECK (exact)
    Before the superseded files are deleted: every ``path:line`` citation and every backticked file
    path in a file about to be deleted appears in a file that remains; every ``**Related:**`` pointer
    in a remaining file names a consolidated file that remains; no remaining file carries mojibake;
    no raw (agent-written) file is left behind un-superseded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from common import (
    ContentFilter,
    ask_json,
    citations_in,
    object_list,
    parallel,
    read_text,
    section_body,
    string_list,
    workspace_label,
)
from datrix_scripts.local_llm import LocalLlmPool

LOG = logging.getLogger(__name__)

CONSOLIDATED_PREFIX = "consolidated-"
_CONSOLIDATED_NUMBER = re.compile(r"consolidated-(\d{3})")
_BACKTICKED_PATH = re.compile(r"`([\w.\-]+(?:/[\w.\-]+)+\.[A-Za-z0-9]+)`")
_RELATED_LINE = re.compile(r"^\*\*Related:\*\*(.*)$", re.MULTILINE)
MOJIBAKE = ("â€", "Â§", "Ã©", "â†")

EXTRACT_SYSTEM = (
    "You split one findings file from Datrix, a multi-language code generator, into atomic findings: one "
    "defect with one root cause each. A file that lists several independent defects becomes several "
    "findings; a sub-item with the same root cause as its parent stays inside it. For each finding give: "
    "title (one line naming the defect, not the symptoms); seam (the construct, contract or subsystem it "
    "sits on, in a few words, e.g. 'gateway edge auth', 'redis connection settings', 'CDN purge "
    "identifiers'); packages (the datrix-* packages it involves); defect (one clause); citations (every "
    "path:line or path:first-last the file gives for THIS finding, copied exactly as written). Use only what "
    "the file says. Lines are numbered 'N| text'; never copy the numbers into citations.")

EXTRACT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "seam": {"type": "string"},
                    "packages": {"type": "array", "items": {"type": "string"}},
                    "defect": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "seam", "packages", "defect", "citations"],
            },
        },
    },
    "required": ["findings"],
}


@dataclass(frozen=True)
class AtomicFinding:
    source: str
    title: str
    seam: str
    packages: tuple[str, ...]
    defect: str
    citations: tuple[str, ...]


@dataclass
class FileExtraction:
    source: str
    findings: list[AtomicFinding] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    note: str = ""


def finding_files(directory: Path) -> list[Path]:
    """Every ``*.md`` directly in the findings folder, by name."""
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def is_consolidated(path: Path) -> bool:
    return path.name.startswith(CONSOLIDATED_PREFIX)


def _normalized(reference: str) -> str:
    return reference.strip().strip("`").replace("\\", "/")


def references(text: str) -> set[str]:
    """Every ``path:line`` citation and every backticked file path in ``text``."""
    found = {_normalized(c) for c in citations_in(text)}
    found |= {_normalized(p) for p in _BACKTICKED_PATH.findall(text)}
    return found


def _source_citation(given: str, source_citations: set[str]) -> str:
    """The file's own citation ``given`` names: the same text, or one it is the tail of (``x.py:9`` for
    ``pkg/src/x.py:9``); empty when it names none. Text the model gave that is in the file but is not a
    citation (a bare path) names none and is not an invention either."""
    if given in source_citations:
        return given
    tails = [c for c in source_citations if c.endswith("/" + given)]
    return tails[0] if len(tails) == 1 else ""


def extract_file(workspace: Path, pool: LocalLlmPool, content: ContentFilter, path: Path) -> FileExtraction:
    """One file's atomic findings, with its citations checked against the file."""
    label = workspace_label(workspace, path)
    text = read_text(path)
    section = content.section(label, text)
    answer = ask_json(pool, EXTRACT_SYSTEM, section_body(section), EXTRACT_SCHEMA)
    source_citations = {_normalized(c) for c in citations_in(text)}
    findings: list[AtomicFinding] = []
    claimed: set[str] = set()
    invented: list[str] = []
    for item in object_list(answer.get("findings")):
        cited: list[str] = []
        for given in string_list(item.get("citations")):
            matched = _source_citation(_normalized(given), source_citations)
            if matched:
                cited.append(matched)
            elif _normalized(given) not in text.replace("\\", "/"):
                invented.append(_normalized(given))
        claimed |= set(cited)
        findings.append(AtomicFinding(path.name, str(item.get("title", "")).strip(), str(item.get("seam", "")).strip(),
                                      tuple(string_list(item.get("packages"))), str(item.get("defect", "")).strip(),
                                      tuple(dict.fromkeys(cited))))
    unassigned = sorted(source_citations - claimed)
    return FileExtraction(path.name, findings, unassigned, list(dict.fromkeys(invented)), section.note)


def build_index(workspace: Path, pool: LocalLlmPool, directory: Path) -> list[FileExtraction]:
    """The atomic findings of every file in the folder (raw and consolidated alike)."""
    content = ContentFilter(workspace)
    return parallel(finding_files(directory), lambda path: extract_file(workspace, pool, content, path))


def render_index(extractions: list[FileExtraction]) -> str:
    """The index the skill groups themes from: one row per atomic finding, sorted by seam then package."""
    rows = sorted((f for e in extractions for f in e.findings),
                  key=lambda f: (f.seam.lower(), ",".join(sorted(p.lower() for p in f.packages)), f.source))
    total = sum(len(e.findings) for e in extractions)
    lines = ["# Findings index", "",
             f"{len(extractions)} file(s), {total} atomic finding(s), sorted by seam then package. Written by a "
             "local model and checked against each file's citations; carry evidence from the files themselves.",
             "", "| Seam | Packages | Defect | Source | Citations |", "|---|---|---|---|---|"]
    for f in rows:
        defect = (f.title or f.defect).replace("|", "\\|")
        lines.append(f"| {f.seam} | {', '.join(f.packages)} | {defect} | {f.source} | {len(f.citations)} |")
    problems = [e for e in extractions if e.unassigned or e.invented or e.note or not e.findings]
    if problems:
        lines += ["", "## Check these files yourself", ""]
    for e in problems:
        if not e.findings:
            lines.append(f"- {e.source}: the model found no finding in it.")
        if e.unassigned:
            lines.append(f"- {e.source}: citations no finding carries (they must still land in a section): "
                         + ", ".join(f"`{c}`" for c in e.unassigned))
        if e.invented:
            lines.append(f"- {e.source}: citations the model invented (dropped from the index): "
                         + ", ".join(f"`{c}`" for c in e.invented))
        if e.note:
            lines.append(f"- {e.note} Redact that content when you carry the finding.")
    return "\n".join(lines) + "\n"


@dataclass
class ConsolidationCheck:
    lost: dict[str, list[str]] = field(default_factory=dict)
    dangling_related: dict[str, list[str]] = field(default_factory=dict)
    mojibake: list[str] = field(default_factory=list)
    raw_left: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.lost or self.dangling_related or self.mojibake or self.raw_left)


def check_consolidation(directory: Path, delete: list[Path]) -> ConsolidationCheck:
    """Would deleting ``delete`` lose a citation, leave a dangling pointer, or leave a raw file behind?"""
    doomed = {path.resolve() for path in delete}
    remaining = [path for path in finding_files(directory) if path.resolve() not in doomed]
    texts = {path.name: read_text(path) for path in remaining}
    kept_refs: set[str] = set().union(*(references(text) for text in texts.values())) if texts else set()
    result = ConsolidationCheck()
    for path in delete:
        lost = sorted(references(read_text(path)) - kept_refs)
        if lost:
            result.lost[path.name] = lost
    kept_numbers = {m.group(1) for name in texts if (m := _CONSOLIDATED_NUMBER.match(name))}
    for name, text in texts.items():
        pointed = {n for line in _RELATED_LINE.findall(text) for n in _CONSOLIDATED_NUMBER.findall(line)}
        dangling = sorted(pointed - kept_numbers)
        if dangling:
            result.dangling_related[name] = [f"consolidated-{n}" for n in dangling]
        if any(mark in text for mark in MOJIBAKE):
            result.mojibake.append(name)
    result.raw_left = sorted(name for name in texts if not name.startswith(CONSOLIDATED_PREFIX))
    return result


def render_check(result: ConsolidationCheck) -> str:
    if result.passed:
        return "PASS: every citation and file path of the files to delete survives in a remaining file; " \
               "Related pointers resolve; no mojibake; no raw file left.\n"
    lines = ["FAIL: do not delete yet.", ""]
    for name, refs in result.lost.items():
        lines.append(f"- {name}: not carried into any remaining file: " + ", ".join(f"`{r}`" for r in refs))
    for name, targets in result.dangling_related.items():
        lines.append(f"- {name}: **Related** names a file that will not exist: {', '.join(targets)}")
    lines += [f"- {name}: carries mojibake (restore the intended characters)" for name in result.mojibake]
    lines += [f"- {name}: a raw file that is neither superseded nor in the delete list" for name in result.raw_left]
    return "\n".join(lines) + "\n"
