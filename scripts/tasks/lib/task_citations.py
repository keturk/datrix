"""Do the ``path:line`` citations in a task file still point at what the task says they do?

A task is written against the tree as it was that day, and carries line-exact claims
("``_messaging_helpers.py:113-131`` ``enum_imports_used_in_body(service, body)``"). Phases run
for days while other tasks change the same files, so by the time an implementer is dispatched
the lines may have moved, or the file may be gone. The implementer then spends tokens finding
out. This checker finds out first, deterministically, and says which citation is wrong.

WHAT IS CHECKED
    Every ``path:line`` or ``path:first-last`` in the prose of the task (never inside a code
    fence, where ``name:1`` is code to write, not a claim about the tree):

    * ERROR -- the file does not exist (unless the task itself says it creates it);
    * ERROR -- the cited line range is past the end of the file, or is empty (``first > last``);
    * WARN  -- a name quoted right beside the citation (the backticked span just before or just
      after it) appears nowhere within three lines of the cited range: the lines have most likely
      moved. Names elsewhere in the sentence are not evidence about this range and are ignored.

HOW A PATH IS RESOLVED
    Absolute paths as written. Relative paths from the workspace, then from the task's own
    repository, then as the tail of a path in any framework repository. A bare file name
    (``_messaging_helpers.py``) is looked up among the task's own file lists and the files every
    framework repository tracks. A tail or a bare name that more than one file carries is skipped:
    a task discusses several packages at once, and guessing which file was meant would report a
    stale citation that is not one. A path with ``...`` in it is an abbreviation and is skipped.
"""

from __future__ import annotations

import builtins
import keyword
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.task_metadata import task_prose_lines

LEVEL_ERROR = "ERROR"
LEVEL_WARN = "WARN"
DRIFT_WINDOW = 3
MIN_IDENTIFIER_CHARS = 4
# The most text between a citation and the name it is about.
MAX_ADJACENT_GAP = 12
_CONNECTORS = r"(?:(?:is|are|at|in|of|as|see|defined|located)\s+){0,3}"
_AFTER_GAP = re.compile(rf"^\s*(?:\(|--|—|–|:)?\s*{_CONNECTORS}$")
_BEFORE_GAP = re.compile(rf"^\s*(?:{_CONNECTORS}|(?:--|—|–|:)\s*)$")
GIT_TIMEOUT_SECONDS = 60

_CITATION = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/])?[\w.\-/\\…]*[\w\-]\.[A-Za-z0-9]{1,6}):(?P<first>\d+)(?:-(?P<last>\d+))?(?![\w/])"
)
_BACKTICK = re.compile(r"`([^`\n]+)`")
_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\(.*\))?$")
_ABBREVIATED = ("...", "…")
# Names every Python file may mention without the cited lines being about them.
_LANGUAGE_NAMES = frozenset(dir(builtins)) | frozenset(keyword.kwlist) | {"TYPE_CHECKING", "TypeVar", "Final"}


@dataclass(frozen=True)
class CitationFinding:
    level: str
    line: int
    citation: str
    message: str

    def render(self) -> str:
        return f"{self.level} line {self.line}: {self.citation}: {self.message}"


class RepoFiles:
    """The files a repository tracks, by bare file name; read once per run."""

    def __init__(self) -> None:
        self._by_name: dict[Path, dict[str, list[Path]]] = {}

    def candidates(self, repo: Path, name: str) -> list[Path]:
        if repo not in self._by_name:
            self._by_name[repo] = self._index(repo)
        return self._by_name[repo].get(name, [])

    def ending_with(self, repo: Path, relative: str) -> list[Path]:
        """The files of ``repo`` whose path ends with ``relative`` (a path abbreviated from a subdirectory)."""
        suffix = "/" + relative.strip("/")
        return [path for path in self.candidates(repo, relative.rsplit("/", 1)[-1])
                if path.as_posix().endswith(suffix)]

    @staticmethod
    def _index(repo: Path) -> dict[str, list[Path]]:
        command = ["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
        try:
            result = subprocess.run(command, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if result.returncode != 0:
            return {}
        by_name: dict[str, list[Path]] = {}
        for rel in result.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
            if rel:
                by_name.setdefault(Path(rel).name, []).append(repo / rel)
        return by_name


@dataclass(frozen=True)
class CitationContext:
    """Where a task lives and what it says it creates, so its citations can be resolved."""

    workspace: Path
    repo: Path
    listed: dict[str, list[Path]]
    # Files this task, or another task of its phase, says it creates or modifies: a citation of one
    # that does not exist yet is not an error, because the task that makes it runs first.
    creates: frozenset[Path]
    repo_files: RepoFiles
    other_repos: tuple[Path, ...] = ()


def _is_created(spec: str, path: Path, creates: frozenset[Path]) -> bool:
    suffix = "/" + spec.replace("\\", "/").strip("/")
    return path.resolve() in creates or any(created.as_posix().endswith(suffix) for created in creates)


def _resolve(spec: str, context: CitationContext) -> list[Path]:
    """The files ``spec`` can mean: none when it is abbreviated or names nothing.

    A relative path with directories may be written from the workspace, from the repository, or
    from a subdirectory of any framework repository (``generators/messaging/x.py``); the first
    two readings win when they find a file. A subdirectory path that several repositories carry
    (``plugin/capability.py`` exists in every platform package) is ambiguous and is skipped: the
    writer's repository is a guess, not evidence, and a wrong guess reports a stale citation that
    is not one. A path that matches nothing at all is reported missing.
    """
    if any(mark in spec for mark in _ABBREVIATED):
        return []
    text = spec.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", text):
        return [Path(text)]
    if "/" in text:
        for base in (context.workspace, context.repo):
            if (base / text).exists():
                return [base / text]
        found = [path for repo in (context.repo, *context.other_repos)
                 for path in context.repo_files.ending_with(repo, text)]
        return found or [context.workspace / text]
    # A bare file name is unambiguous only when ONE file of that name exists anywhere in the framework:
    # a task discusses several packages at once, so "unique in the task's repository" proves nothing
    # about which file the writer meant. The task's own lists count as well, and several distinct
    # files mean skip.
    named = [*context.listed.get(text, [])]
    for repo in (context.repo, *context.other_repos):
        named.extend(context.repo_files.candidates(repo, text))
    return list({path.resolve(): path for path in named}.values())


def _line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _identifier_of(span: str) -> str | None:
    """The name a backticked span quotes, when it quotes one (``Class.method(args)`` -> ``method``)."""
    if ":" in span or "/" in span or "\\" in span or not _IDENTIFIER.match(span.strip()):
        return None
    name = re.split(r"\(", span.strip(), maxsplit=1)[0].split(".")[-1]
    return name if len(name) >= MIN_IDENTIFIER_CHARS and name not in _LANGUAGE_NAMES else None


def _citation_bounds(citation: re.Match[str], spans: list[tuple[int, int, str]]) -> tuple[int, int]:
    """The citation's extent, widened to its backticked span when it is written inside one."""
    for span_start, span_end, _ in spans:
        if span_start < citation.start() and citation.end() < span_end:
            return span_start, span_end
    return citation.start(), citation.end()


def _gap_to(position: tuple[int, int], bounds: tuple[int, int]) -> int:
    """Characters between two extents (0 when they touch or overlap)."""
    if bounds[1] <= position[0]:
        return position[0] - bounds[1]
    if bounds[0] >= position[1]:
        return bounds[0] - position[1]
    return 0


def _adjacent_identifiers(line: str, citation: re.Match[str]) -> list[str]:
    """The names a writer put right at a citation, as the thing it points at.

    ```_messaging_helpers.py:113-131` `enum_imports_used_in_body(service, body)` `` and
    ``... `name` at `file.py:12` `` both say the name is at those lines. Nothing else in a sentence
    is evidence about the range, so a name counts only when it is the FIRST span after the citation,
    after nothing but a space, a dash, an opening parenthesis, a colon or "at/in/is/as"; or the LAST
    span before it, after nothing but "at/in/of/is/see", a dash or a colon; and only when no other
    citation in the line is nearer to it. A name after "to", "and", a closing parenthesis or a comma, or
    the second item of a list, belongs to something else.
    """
    spans = [(m.start(), m.end(), m.group(1)) for m in _BACKTICK.finditer(line)]
    mine = _citation_bounds(citation, spans)
    others = [_citation_bounds(other, spans) for other in _CITATION.finditer(line)
              if other.start() != citation.start()]
    after = next(((s, e, t) for s, e, t in spans if s >= mine[1]), None)
    before = next(((s, e, t) for s, e, t in reversed(spans) if e <= mine[0]), None)
    names: list[str] = []
    for span, gap_text, kind in ((after, line[mine[1]:after[0]] if after else "", "after"),
                                 (before, line[before[1]:mine[0]] if before else "", "before")):
        if span is None or len(gap_text) > MAX_ADJACENT_GAP:
            continue
        if not (_AFTER_GAP if kind == "after" else _BEFORE_GAP).match(gap_text):
            continue
        nearest = min((_gap_to((span[0], span[1]), other) for other in others), default=len(gap_text) + 1)
        precedes = any(other[1] <= span[0] for other in others)
        if nearest < len(gap_text) or (nearest == len(gap_text) and kind == "before" and precedes):
            continue  # another citation is nearer: the name is about that one
        name = _identifier_of(span[2])
        if name is not None:
            names.append(name)
    return list(dict.fromkeys(names))


def cited_identifiers(line: str) -> list[str]:
    """The names a line writes right beside its ``path:line`` citations, in order, each once."""
    names: list[str] = []
    for match in _CITATION.finditer(line):
        names.extend(_adjacent_identifiers(line, match))
    return list(dict.fromkeys(names))


def _where_now(path: Path, names: list[str]) -> str:
    """Where each name is now: its definition line when the file defines it, else its first mention.

    Makes a drift warning actionable: the writer corrects the range instead of searching for it.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    found: list[str] = []
    for name in names:
        word = re.compile(rf"\b{re.escape(name)}\b")
        definition = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*[:=]")
        at = next((n for n, text in enumerate(lines, start=1) if definition.search(text)), None) or \
            next((n for n, text in enumerate(lines, start=1) if word.search(text)), None)
        found.append(f"{name} is now at line {at}" if at else f"{name} is not in {path.name} at all")
    return "; ".join(found)


def _drift(path: Path, first: int, last: int, names: list[str]) -> list[str]:
    """The line's identifiers, when NONE of them is near the cited range; empty when any is.

    A sentence names related things (a raised error, a helper defined elsewhere), so one absent
    name proves nothing. A range that holds none of what the sentence is about has moved.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    window = "\n".join(lines[max(0, first - 1 - DRIFT_WINDOW):last + DRIFT_WINDOW])
    return [] if not names or any(name in window for name in names) else names


def check_citations(text: str, context: CitationContext) -> list[CitationFinding]:
    """Every wrong citation in the prose of a task, in file order."""
    findings: list[CitationFinding] = []
    for number, line in task_prose_lines(text):
        matches = list(_CITATION.finditer(line))
        for match in matches:
            first, last = int(match.group("first")), int(match.group("last") or match.group("first"))
            citation = match.group(0)
            candidates = _resolve(match.group("path"), context)
            if len(candidates) != 1:
                continue
            path = candidates[0]
            if not path.is_file():
                if not _is_created(match.group("path"), path, context.creates):
                    findings.append(CitationFinding(LEVEL_ERROR, number, citation, f"{path} does not exist"))
                continue
            total = _line_count(path)
            if first < 1 or first > last or last > total:
                findings.append(CitationFinding(
                    LEVEL_ERROR, number, citation,
                    f"lines {first}-{last} are not in {path.name}, which has {total} lines"))
                continue
            moved = _drift(path, first, last, _adjacent_identifiers(line, match))
            if moved:
                findings.append(CitationFinding(
                    LEVEL_WARN, number, citation,
                    f"{', '.join(moved)}, written beside the citation, is not within {DRIFT_WINDOW} lines of the "
                    f"cited range in {path.name}: the lines have probably moved ({_where_now(path, moved)})"))
    return findings
