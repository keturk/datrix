"""Script catalogue gate: every scripts folder's quick-reference documents what the folder holds.

Four rules over ``datrix/scripts``, read from Markdown's token stream (``markdown-it-py``) and
from PowerShell's own parser (``datrix_scripts.powershell_ast``), never from regex over prose:

1. ``undocumented-script`` -- every ``.ps1`` directly in a folder that has a ``quick-reference.md``
   appears in it as a ``##``/``###`` heading holding the script's path (folder − documented).
2. ``undeclared-flag`` -- every ``-Flag`` that follows a script's name inside one inline code span
   or one line of a fenced block resolves to a parameter or alias the script's ``param()`` block
   declares (documented flags − declared). A flag after ``|``, ``;`` or ``&&`` belongs to the
   next command, not the script.
3. ``readme-beside-quick-reference`` -- no folder under ``scripts/`` other than ``scripts/``
   itself holds both a ``quick-reference.md`` and a ``README.md``.
4. ``dangling-link`` -- every relative link in a ``quick-reference.md`` or ``README.md`` under
   ``scripts/`` resolves to an existing file (anchors are not checked).

The root ``scripts/quick-reference.md`` is the index of the folders, so rule 1 does not apply to
it. A script named that is not under ``scripts/`` (a generated project's runner) is not checked.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.token import Token

from datrix_scripts.gate_harness import NamedCheck, check_list_main, write_files
from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.powershell_ast import ScriptFacts, parse_scripts

QUICK_REFERENCE: Final = "quick-reference.md"
README: Final = "README.md"
SCRIPT_SUFFIX: Final = ".ps1"
_DOCUMENTING_HEADINGS: Final = frozenset({"h2", "h3"})
_SKIP_DIRS: Final = frozenset({"__pycache__", ".pytest_cache", "node_modules", "lib"})
_SCRIPT_TOKEN_RE: Final = re.compile(r"[\w.:/\\-]*?([\w.-]+\.ps1)\b", re.IGNORECASE)
_FLAG_RE: Final = re.compile(r"(?<![\w-])-([A-Za-z][A-Za-z0-9]*)\b")
_COMMAND_BREAK_RE: Final = re.compile(r"\||;|&&")
_EXTERNAL_LINK_RE: Final = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
#: PowerShell's common parameters: every advanced script accepts them without declaring them.
_COMMON_PARAMETERS: Final = frozenset({
    "verbose", "debug", "erroraction", "warningaction", "informationaction", "errorvariable",
    "warningvariable", "informationvariable", "outvariable", "outbuffer", "pipelinevariable",
    "progressaction", "whatif", "confirm",
})


class Rule(StrEnum):
    UNDOCUMENTED_SCRIPT = "undocumented-script"
    UNDECLARED_FLAG = "undeclared-flag"
    README_BESIDE_QUICK_REFERENCE = "readme-beside-quick-reference"
    DANGLING_LINK = "dangling-link"


@dataclass(frozen=True)
class Hit:
    rule: Rule
    location: str
    detail: str

    def render(self) -> str:
        return f"[{self.rule}] {self.location}: {self.detail}"


@dataclass(frozen=True)
class FlagUse:
    """``-flag`` written after ``script`` in one code span or fence line of a document."""

    script: str
    flag: str
    line: int


def _markdown() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table")


def _relative(path: Path, scripts_dir: Path) -> str:
    return path.relative_to(scripts_dir).as_posix()


def _documents(scripts_dir: Path) -> list[Path]:
    """Every quick-reference.md and README.md under ``scripts_dir``."""
    return sorted(
        path for name in (QUICK_REFERENCE, README) for path in scripts_dir.rglob(name)
        if not _SKIP_DIRS & set(path.relative_to(scripts_dir).parts)
    )


def _catalogue_folders(scripts_dir: Path) -> list[Path]:
    """Every folder below ``scripts_dir`` holding a quick-reference (the root's is the index)."""
    return sorted(
        path.parent for path in scripts_dir.rglob(QUICK_REFERENCE)
        if path.parent != scripts_dir and not _SKIP_DIRS & set(path.relative_to(scripts_dir).parts)
    )


def _inline_code(tokens: list[Token]) -> Iterator[tuple[str, int]]:
    """(text, line) of every inline code span and every fenced/indented code line."""
    for token in tokens:
        line = token.map[0] + 1 if token.map else 0
        if token.type in ("fence", "code_block"):
            for offset, text in enumerate(token.content.splitlines(), start=1):
                yield text, line + offset
        for child in token.children or ():
            if child.type == "code_inline":
                yield child.content, line


def documented_scripts(text: str) -> set[str]:
    """Script file names a ``##``/``###`` heading of the document holds (lowercase)."""
    tokens = _markdown().parse(text)
    names: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag in _DOCUMENTING_HEADINGS:
            heading = tokens[index + 1].content
            names.update(match.group(1).lower() for match in _SCRIPT_TOKEN_RE.finditer(heading))
    return names


def flag_uses(text: str) -> list[FlagUse]:
    """Every ``-Flag`` written after a script name in one code span or code line."""
    uses: list[FlagUse] = []
    for code, line in _inline_code(_markdown().parse(text)):
        for segment in _COMMAND_BREAK_RE.split(code):
            uses.extend(_segment_flags(segment, line))
    return uses


def _segment_flags(segment: str, line: int) -> list[FlagUse]:
    uses: list[FlagUse] = []
    scripts = list(_SCRIPT_TOKEN_RE.finditer(segment))
    for position, script in enumerate(scripts):
        end = scripts[position + 1].start() if position + 1 < len(scripts) else len(segment)
        arguments = _without_quoted(segment[script.end():end])
        uses.extend(FlagUse(script.group(1).lower(), flag.group(1), line) for flag in _FLAG_RE.finditer(arguments))
    return uses


def _without_quoted(text: str) -> str:
    """``text`` with quoted strings removed: a dash inside a quoted value is no flag."""
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", text)


def links(text: str) -> list[tuple[str, int]]:
    """(href, line) of every link in the document."""
    found: list[tuple[str, int]] = []
    for token in _markdown().parse(text):
        line = token.map[0] + 1 if token.map else 0
        for child in token.children or ():
            if child.type == "link_open":
                found.append((str(child.attrGet("href") or ""), line))
    return found


def _scripts_by_name(scripts_dir: Path) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = {}
    for path in sorted(scripts_dir.rglob(f"*{SCRIPT_SUFFIX}")):
        if not _SKIP_DIRS & set(path.relative_to(scripts_dir).parts):
            by_name.setdefault(path.name.lower(), []).append(path)
    return by_name


def undocumented_scripts(scripts_dir: Path) -> list[Hit]:
    hits: list[Hit] = []
    for folder in _catalogue_folders(scripts_dir):
        documented = documented_scripts((folder / QUICK_REFERENCE).read_text(encoding="utf-8"))
        for script in sorted(folder.glob(f"*{SCRIPT_SUFFIX}")):
            if script.name.lower() not in documented:
                hits.append(Hit(Rule.UNDOCUMENTED_SCRIPT, _relative(script, scripts_dir),
                                f"not a heading of {_relative(folder / QUICK_REFERENCE, scripts_dir)}; "
                                f"add a ## or ### section for it"))
    return hits


def _resolve_script(name: str, document: Path, by_name: dict[str, list[Path]]) -> Path | None:
    """The script a document means: the one in its own folder first, else the only one so named."""
    candidates = by_name.get(name, [])
    local = [path for path in candidates if path.parent == document.parent]
    if local:
        return local[0]
    return candidates[0] if len(candidates) == 1 else None


def undeclared_flags(scripts_dir: Path) -> list[Hit]:
    by_name = _scripts_by_name(scripts_dir)
    uses: list[tuple[Path, FlagUse, Path]] = []
    for document in _documents(scripts_dir):
        for use in flag_uses(document.read_text(encoding="utf-8")):
            script = _resolve_script(use.script, document, by_name)
            if script is not None:
                uses.append((document, use, script))
    facts: dict[Path, ScriptFacts] = parse_scripts(sorted({script for _, _, script in uses}))
    hits: list[Hit] = []
    for document, use, script in uses:
        declared = facts[script.resolve()]
        if use.flag.lower() not in _COMMON_PARAMETERS and not declared.declares(use.flag):
            hits.append(Hit(Rule.UNDECLARED_FLAG, f"{_relative(document, scripts_dir)}:{use.line}",
                            f"-{use.flag} is not a parameter of {_relative(script, scripts_dir)}; "
                            f"declared: {', '.join(p.name for p in declared.parameters) or 'none'}"))
    return hits


def readmes_beside_quick_references(scripts_dir: Path) -> list[Hit]:
    return [
        Hit(Rule.README_BESIDE_QUICK_REFERENCE, _relative(folder / README, scripts_dir),
            "move what the quick-reference lacks into it under its own heading, then delete the README")
        for folder in _catalogue_folders(scripts_dir) if (folder / README).is_file()
    ]


def dangling_links(scripts_dir: Path) -> list[Hit]:
    hits: list[Hit] = []
    for document in _documents(scripts_dir):
        for href, line in links(document.read_text(encoding="utf-8")):
            target = href.split("#", 1)[0]
            if not target or _EXTERNAL_LINK_RE.match(target):
                continue
            if not (document.parent / target).exists():
                hits.append(Hit(Rule.DANGLING_LINK, f"{_relative(document, scripts_dir)}:{line}",
                                f"{href} resolves to nothing"))
    return hits


def catalogue_hits(scripts_dir: Path) -> list[Hit]:
    """Every rule's hits over ``scripts_dir``."""
    return [*undocumented_scripts(scripts_dir), *undeclared_flags(scripts_dir),
            *readmes_beside_quick_references(scripts_dir), *dangling_links(scripts_dir)]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_DOCUMENTED_SCRIPT: Final = "[CmdletBinding()]\nparam([switch]$All, [Alias('L')][string]$Language)\n"
_PLANTED_REFERENCE: Final = """# Planted

## `x\\a.ps1`

Run `.\\x\\a.ps1 -All -L python | Out-File -FilePath out.txt` or:

```powershell
.\\x\\a.ps1 -Verbose -Language python
```

See [the index](../quick-reference.md#planted) and [here](missing.md).
"""


def _planted_tree(root: Path, *, defects: bool) -> Path:
    """A scripts tree with one folder; ``defects`` adds one hit of every rule."""
    reference = _PLANTED_REFERENCE if defects else _PLANTED_REFERENCE.replace(" and [here](missing.md)", "")
    files = {"quick-reference.md": "# Index\n", "x/a.ps1": _DOCUMENTED_SCRIPT,
             "x/quick-reference.md": reference.replace("-L python |", "-Nope python |") if defects else reference}
    if defects:
        files |= {"x/b.ps1": _DOCUMENTED_SCRIPT, "x/README.md": "# Stale\n"}
    write_files(root, files)
    return root


def _check_a_clean_tree_has_no_hit() -> None:
    with TemporaryDirectory(prefix="script-catalogue-") as temp:
        hits = catalogue_hits(_planted_tree(Path(temp), defects=False))
    assert hits == [], [hit.render() for hit in hits]


def _check_every_rule_reports_its_planted_defect() -> None:
    with TemporaryDirectory(prefix="script-catalogue-") as temp:
        hits = catalogue_hits(_planted_tree(Path(temp), defects=True))
    found = {(hit.rule, hit.location.split(":")[0]) for hit in hits}
    expected = {
        (Rule.UNDOCUMENTED_SCRIPT, "x/b.ps1"),
        (Rule.UNDECLARED_FLAG, "x/quick-reference.md"),
        (Rule.README_BESIDE_QUICK_REFERENCE, "x/README.md"),
        (Rule.DANGLING_LINK, "x/quick-reference.md"),
    }
    assert found == expected, [hit.render() for hit in hits]
    flagged = [hit.detail for hit in hits if hit.rule is Rule.UNDECLARED_FLAG]
    assert len(flagged) == 1 and flagged[0].startswith("-Nope "), flagged


def _check_flags_belong_to_the_script_they_follow() -> None:
    uses = flag_uses("Run `.\\a.ps1 -All | Out-File -FilePath f` then `b.ps1 -Tag 'x -y'; c -Z`.\n")
    assert [(use.script, use.flag) for use in uses] == [("a.ps1", "All"), ("b.ps1", "Tag")], uses


def _check_scripts_tree_catalogue_is_clean() -> None:
    hits = catalogue_hits(SCRIPTS_DIR)
    assert not hits, f"{len(hits)} catalogue hit(s):\n" + "\n".join(hit.render() for hit in hits)


_SELF_TEST: Final = [
    NamedCheck("a_clean_tree_has_no_hit", _check_a_clean_tree_has_no_hit),
    NamedCheck("every_rule_reports_its_planted_defect", _check_every_rule_reports_its_planted_defect),
    NamedCheck("flags_belong_to_the_script_they_follow", _check_flags_belong_to_the_script_they_follow),
]
_CHECKS: Final = [*_SELF_TEST, NamedCheck("scripts_tree_catalogue_is_clean", _check_scripts_tree_catalogue_is_clean)]


def main() -> int:
    return check_list_main(
        "Script catalogue: each scripts folder's quick-reference documents its scripts and their flags.",
        "script-catalogue",
        _CHECKS,
        self_test=_SELF_TEST,
    )


if __name__ == "__main__":
    sys.exit(main())
