"""The size rules of an implement-design-direct ledger, and the changed-files list the verify step reads.

Every unit session re-reads the whole ledger, so what it holds is paid again by each later session. The ledger
is the work plan and nothing else: a ``## Units`` table and a ``## Decisions`` list, bounded as a whole file
(``MAX_LEDGER_BYTES``) and line by line. Detail belongs in the unit's proof file, which no session re-reads.

The files a unit changed are not kept in the ledger. Each unit lists them under ``## Files changed`` in its own
proof file (``<ledger name>-proof/<id>.md``); ``write_files_supplement`` gathers them into the supplement file
``<ledger name>-files.md`` that ``/verify-implementation`` takes as its ``FILES`` input.
"""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.gate_harness import write_files

MAX_LEDGER_BYTES: Final = 24_000
MAX_CELL_CHARS: Final = 400
MAX_STATE_CELL_CHARS: Final = 240
MAX_TEXT_LINE_CHARS: Final = 300
ALLOWED_SECTIONS: Final = ("units", "decisions")
MAX_REPORTED: Final = 5

SECTION_HEADING: Final = re.compile(r"^##\s+(.*?)\s*$")
FILES_CHANGED_HEADING: Final = re.compile(r"^##\s+Files changed\s*$", re.IGNORECASE)
CELL_SEPARATOR: Final = re.compile(r"(?<!\\)\|")
LIST_MARKER: Final = re.compile(r"^\s*[-*]\s+")
TRAILING_NOTE: Final = re.compile(r"\s+\([^)]*\)$")


def row_cells(line: str) -> list[str]:
    """The cells of one markdown table row; a ``|`` written ``\\|`` stays inside its cell."""
    parts = CELL_SEPARATOR.split(line.strip())
    return parts[1:-1] if len(parts) > 2 and not parts[-1].strip() else parts[1:]


def line_violations(number: int, line: str, section: str) -> list[str]:
    """What is wrong with one ledger line: an over-long table cell, an over-long text line, or a section
    heading other than ``ALLOWED_SECTIONS``."""
    if line.lstrip().startswith("|"):
        cells = row_cells(line)
        found = [f"line {number}: a table cell holds {len(cell.strip())} chars (max {MAX_CELL_CHARS})"
                 for cell in cells[:-1] if len(cell.strip()) > MAX_CELL_CHARS]
        if cells and len(cells[-1].strip()) > MAX_STATE_CELL_CHARS:
            found.append(f"line {number}: the state cell holds {len(cells[-1].strip())} chars "
                         f"(max {MAX_STATE_CELL_CHARS}; one line, the detail goes to the proof file)")
        return found
    heading = SECTION_HEADING.match(line)
    if heading and heading.group(1).lower() not in ALLOWED_SECTIONS:
        return [f"line {number}: section '## {heading.group(1)}' is not allowed (only "
                f"{', '.join('## ' + name.title() for name in ALLOWED_SECTIONS)})"]
    if len(line) > MAX_TEXT_LINE_CHARS:
        where = f"a line in '{section}'" if section else "a line"
        return [f"line {number}: {where} holds {len(line)} chars (max {MAX_TEXT_LINE_CHARS})"]
    return []


def text_violations(text: str) -> list[str]:
    """Every way *text* breaks the ledger rules, the whole-file size first; empty when it keeps them."""
    size = len(text.encode("utf-8"))
    found = [f"the ledger is {size} bytes (max {MAX_LEDGER_BYTES})"] if size > MAX_LEDGER_BYTES else []
    section = ""
    for number, line in enumerate(text.splitlines(), start=1):
        heading = SECTION_HEADING.match(line)
        section = heading.group(1) if heading else section
        found.extend(line_violations(number, line, section))
    return found


def ledger_violations(ledger: Path) -> list[str]:
    """The rule breaks of the ledger file, as reported lines (at most ``MAX_REPORTED``, then a count of the
    rest); empty when there is no ledger or it keeps the rules."""
    if not ledger.is_file():
        return []
    found = text_violations(ledger.read_text(encoding="utf-8-sig"))
    if len(found) <= MAX_REPORTED:
        return found
    return [*found[:MAX_REPORTED], f"and {len(found) - MAX_REPORTED} more"]


def proof_dir(ledger: Path) -> Path:
    """The folder of the unit proof files of *ledger*."""
    return ledger.with_name(f"{ledger.stem}-proof")


def files_supplement(ledger: Path) -> Path:
    """The supplement file listing the files the units changed, for ``/verify-implementation``."""
    return ledger.with_name(f"{ledger.stem}-files.md")


def section_paths(text: str) -> list[str]:
    """The paths listed under ``## Files changed`` in one proof file's *text*, one per line; a list marker,
    backticks and a trailing parenthesised note are dropped."""
    paths: list[str] = []
    inside = False
    for line in text.splitlines():
        if SECTION_HEADING.match(line):
            inside = bool(FILES_CHANGED_HEADING.match(line))
            continue
        path = TRAILING_NOTE.sub("", LIST_MARKER.sub("", line).strip().strip("`")).strip().strip("`")
        if inside and path and path.lower() != "none":
            paths.append(path)
    return paths


def changed_files(ledger: Path) -> list[str]:
    """Every path the unit proof files of *ledger* list as changed, each once, in proof-file order."""
    folder = proof_dir(ledger)
    if not folder.is_dir():
        return []
    paths: dict[str, None] = {}
    for proof in sorted(folder.glob("*.md")):
        paths.update(dict.fromkeys(section_paths(proof.read_text(encoding="utf-8-sig"))))
    return list(paths)


def write_files_supplement(ledger: Path) -> list[str]:
    """Write the supplement file from the proof files and return its paths; no file is written when they list none."""
    paths = changed_files(ledger)
    if paths:
        files_supplement(ledger).write_text("# Files changed\n\n" + "\n".join(paths) + "\n", encoding="utf-8")
    return paths


GOOD_LEDGER: Final = (
    "# Ledger\n\nDOCUMENT: d.md\n\n## Units\n\n| id | change | state |\n|---|---|---|\n"
    "| U01 | a \\| b | [x] `test.ps1 pkg` pass 3, proof p.md |\n\n## Decisions\n\n- D0 one sentence, rule.\n"
)


def _check_a_ledger_inside_the_limits_has_no_violation() -> None:
    assert text_violations(GOOD_LEDGER) == [], text_violations(GOOD_LEDGER)
    assert row_cells("| U01 | a \\| b | [x] |") == [" U01 ", " a \\| b ", " [x] "]


def _check_a_file_of_a_hundred_thousand_short_lines_is_refused() -> None:
    with TemporaryDirectory() as raw:
        ledger = Path(raw) / "ledger.md"
        write_files(ledger.parent, {ledger.name: GOOD_LEDGER + "- d\n" * 100_000})
        found = ledger_violations(ledger)
        assert found and found[0].startswith("the ledger is "), found
        assert ledger_violations(ledger.with_name("absent.md")) == []


def _check_each_limit_names_the_line_it_breaks() -> None:
    cases = (
        (GOOD_LEDGER + "| U02 | " + "x" * (MAX_CELL_CHARS + 1) + " | [ ] |\n", "a table cell holds 401 chars"),
        (GOOD_LEDGER + "| U02 | c | [ ] " + "y" * MAX_STATE_CELL_CHARS + " |\n", "the state cell holds"),
        (GOOD_LEDGER + "- " + "z" * MAX_TEXT_LINE_CHARS + "\n", "a line in 'Decisions' holds"),
        (GOOD_LEDGER + "\n## Files changed\n- a.py\n", "section '## Files changed' is not allowed"),
        (GOOD_LEDGER + "\n## Findings filed\n", "section '## Findings filed' is not allowed"),
    )
    for text, expected in cases:
        found = text_violations(text)
        assert len(found) == 1 and expected in found[0], (expected, found)


def _check_the_changed_files_come_from_the_proof_files() -> None:
    with TemporaryDirectory() as raw:
        ledger = Path(raw) / "implement-direct-d.md"
        assert changed_files(ledger) == [] and write_files_supplement(ledger) == []
        write_files(proof_dir(ledger), {
            "U01.md": "## Commands\n- `a.py` is not a changed file\n\n## Files changed\n- `pkg/a.py`\n- pkg/b.py (deleted)\n",
            "U02.md": "## files changed\n\npkg/a.py\nnone\n\n## Notes\npkg/c.py\n",
        })
        assert changed_files(ledger) == ["pkg/a.py", "pkg/b.py"], changed_files(ledger)
        assert write_files_supplement(ledger) == ["pkg/a.py", "pkg/b.py"]
        assert files_supplement(ledger).read_text(encoding="utf-8") == "# Files changed\n\npkg/a.py\npkg/b.py\n"


LEDGER_CHECKS: Final = (
    _check_a_ledger_inside_the_limits_has_no_violation,
    _check_a_file_of_a_hundred_thousand_short_lines_is_refused,
    _check_each_limit_names_the_line_it_breaks,
    _check_the_changed_files_come_from_the_proof_files,
)
