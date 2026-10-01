"""Read workspace files and logs with a local model, so an agent receives the answer, not the text.

The local-model MCP tools (``dev/local_llm_mcp.py``) are built on this module. An agent names
files or a log and asks a question; this module reads them on this machine, numbers their
lines, sends them to a local model server (``shared.local_llm``) in chunks that fit the
smallest context in the pool, and returns a short answer that cites ``path:line``. The bulk
text never enters the agent's context: that is the whole saving.

SCOPE
    Only framework source and test output may be sent: files inside the framework
    repositories (``datrix`` and every ``datrix-*`` git repository at the workspace root,
    discovered, never listed) and the workspace's ``.test-output`` folder. Everything else
    is refused -- ``.tmp`` (generated projects), ``reports``, ``design``, any other
    repository at the workspace root, and anything inside a ``.git`` directory -- so
    customer project content never leaves the machine through these tools. Paths are
    resolved (symbolic links followed) before the check, so ``..`` cannot escape it.

AN ANSWER IS A LEAD
    A local model can misread code. Every answer cites the lines it rests on and ends by
    saying so; the agent opens those lines with a ranged Read before acting on it.
"""

from __future__ import annotations

import glob
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from shared.framework_repos import framework_repos
from shared.local_llm import ChatRequest, LocalLlmPool

# Workspace folders outside the repositories that hold framework test output.
WORKSPACE_OUTPUT_DIRS: tuple[str, ...] = (".test-output",)
GIT_DIR_NAME = ".git"
GLOB_CHARS = frozenset("*?[")

MAX_FILES = 40
# The smallest per-request context in the pool sets this: llama-server splits its context
# across slots (32,768 tokens over 2 slots on the T5820 = 16,384 each). 36,000 characters
# of code is about 10,000 tokens, leaving room for the instructions and the answer.
MAX_CHUNK_CHARS = 36_000
# More than this many chunks is too much to read in one call: narrow the request.
MAX_CHUNKS = 12
MAX_LINE_CHARS = 2_000
ANSWER_MAX_TOKENS = 1_200
ANSWER_TEMPERATURE = 0.1
MAP_WORKERS = 4
NOTHING_RELEVANT = "NOTHING RELEVANT"

# A log too large to read whole is cut down to the lines around these markers.
LOG_MARKER = re.compile(
    r"error|fail|exception|traceback|assert|fatal|panic|denied|refused|timed? ?out|^E\s", re.IGNORECASE)
LOG_CONTEXT_BEFORE = 3
LOG_CONTEXT_AFTER = 12

_CITE_RULES = (
    "The text is given file by file, each under a header line '=== ' + file path + ' ===', and every line "
    "starts with its line number and '| '. Cite every claim with the file path copied exactly from its header, "
    "a colon, and the line number or range, for example datrix-cli/src/datrix_cli/main.py:42 or "
    "datrix-cli/src/datrix_cli/main.py:40-55. Use only line numbers shown. Be concise: at most 15 lines, no "
    "preamble, no restating the question. If the text does not answer the question, say so plainly; never "
    "guess and never invent a line number."
)
ASK_SYSTEM = (
    "You answer a question about source files or logs from Datrix, a multi-language, multi-platform code "
    "generator. " + _CITE_RULES
)
MAP_SYSTEM = (
    "You answer a question about ONE PART of a larger set of source files or logs from Datrix, a code "
    f"generator. Answer only from this part. If this part holds nothing relevant, reply exactly "
    f"'{NOTHING_RELEVANT}' and nothing else. " + _CITE_RULES
)
REDUCE_SYSTEM = (
    "You merge partial answers to one question, each written from a different part of the same files, into "
    "one concise answer of at most 15 lines. Keep every file:line citation exactly as written, drop "
    "duplicates, and do not add anything the partial answers do not say. No preamble."
)
DIGEST_QUESTION = (
    "List each distinct failure or error in this log, one entry per distinct cause: the error type and "
    "message, how many times it occurs, the first log line where it appears, and the source file:line it "
    "points at when the log names one. Group repeats of the same cause. Ignore passing output, and ignore "
    "warnings unless nothing failed."
)


class ReadScopeError(ValueError):
    """A request names something these tools may not read, or too much to read in one call."""


@dataclass(frozen=True)
class Section:
    """One file's text with its lines numbered, ready to be sent."""

    label: str
    lines: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class LocalAnswer:
    text: str
    models: tuple[str, ...]
    files: int
    lines: int
    chunks: int
    notes: tuple[str, ...]

    def render(self) -> str:
        notes = "".join(f"\n- {note}" for note in self.notes)
        return (
            f"{self.text}\n\n---\nRead by a local model ({', '.join(self.models)}) from {self.files} file(s), "
            f"{self.lines:,} lines, in {self.chunks} chunk(s).{notes}\nA lead, not a finding: open the cited lines "
            f"with a ranged Read before acting on it."
        )


class ReadScope:
    """What the tools may read in one workspace, and the files a request names."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.roots = tuple(repo.resolve() for repo in framework_repos(self.workspace)) + tuple(
            (self.workspace / name).resolve() for name in WORKSPACE_OUTPUT_DIRS)

    def _allowed(self, path: Path) -> bool:
        return GIT_DIR_NAME not in path.parts and any(path.is_relative_to(root) for root in self.roots)

    def _refusal(self, spec: str) -> ReadScopeError:
        names = ", ".join(sorted(root.name for root in self.roots))
        return ReadScopeError(
            f"'{spec}' is outside what local-model tools may read. They read only files inside the framework "
            f"repositories and workspace test output ({names}), never .git internals, generated projects in "
            f".tmp, reports or design docs. Pass a workspace-relative path such as "
            f"datrix-common/src/datrix_common/utils/text.py, or a glob such as datrix-cli/src/**/*.py.")

    def files(self, specs: list[str]) -> list[Path]:
        """Every file the specs name, in the order named; refuses anything out of scope."""
        found: dict[Path, None] = {}
        for spec in specs:
            for path in self._expand(spec):
                found[path] = None
        if len(found) > MAX_FILES:
            raise ReadScopeError(
                f"The request names {len(found)} files; at most {MAX_FILES} are read per call. Narrow the glob, "
                f"or split the question across calls.")
        return list(found)

    def _expand(self, spec: str) -> list[Path]:
        raw = Path(spec.strip())
        anchored = raw if raw.is_absolute() else self.workspace / raw
        if GLOB_CHARS & set(spec):
            matches = sorted(Path(m).resolve() for m in glob.glob(str(anchored), recursive=True))
            files = [m for m in matches if m.is_file()]
            if not files:
                raise ReadScopeError(f"The glob '{spec}' matches no file (it is taken relative to {self.workspace}).")
            if not all(self._allowed(m) for m in files):
                raise self._refusal(spec)
            return files
        path = anchored.resolve()
        if not self._allowed(path):
            raise self._refusal(spec)
        if not path.is_file():
            raise ReadScopeError(f"'{spec}' is not a file (resolved to {path}). Pass a file, or a glob for several.")
        return [path]

    def label(self, path: Path) -> str:
        return path.relative_to(self.workspace).as_posix()


def read_section(scope: ReadScope, path: Path) -> Section:
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        raise ReadScopeError(f"'{scope.label(path)}' is a binary file; only text can be read.")
    text = data.decode("utf-8-sig", errors="replace")
    lines = tuple(
        f"{number}| {line[:MAX_LINE_CHARS]}" for number, line in enumerate(text.splitlines(), start=1))
    return Section(scope.label(path), lines)


def _chars(lines: tuple[str, ...]) -> int:
    return sum(len(line) + 1 for line in lines)


def _within(lines: tuple[str, ...], budget_chars: int, *, from_end: bool) -> tuple[str, ...]:
    """The longest run of ``lines`` from the start (or the end) that fits the budget."""
    ordered = reversed(lines) if from_end else iter(lines)
    kept: list[str] = []
    size = 0
    for line in ordered:
        size += len(line) + 1
        if size > budget_chars:
            break
        kept.append(line)
    return tuple(reversed(kept)) if from_end else tuple(kept)


def reduce_log(section: Section, budget_chars: int) -> Section:
    """The lines of a log that fit the budget, each keeping its original line number: the whole
    log when it fits; otherwise the lines around error markers (the earliest first, since a
    first failure often causes the rest); and when no line carries a marker, the end of the
    log, where a run's summary is written."""
    if _chars(section.lines) <= budget_chars:
        return section
    keep: set[int] = set()
    for index, line in enumerate(section.lines):
        if LOG_MARKER.search(line.split("| ", 1)[-1]):
            keep.update(range(max(0, index - LOG_CONTEXT_BEFORE), min(len(section.lines), index + LOG_CONTEXT_AFTER + 1)))
    total = f"{section.label}: {len(section.lines):,} lines, too many to read whole"
    if not keep:
        tail = _within(section.lines, budget_chars, from_end=True)
        return Section(section.label, tail, f"{total}; no error marker found, so read its last {len(tail):,} lines.")
    marked = tuple(section.lines[index] for index in sorted(keep))
    kept = _within(marked, budget_chars, from_end=False)
    cut = f", of which the first {len(kept):,} fit" if len(kept) < len(marked) else ""
    return Section(section.label, kept,
                   f"{total}; read the {len(marked):,} lines around error markers{cut} ({LOG_MARKER.pattern}).")


def chunk_sections(sections: list[Section], max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack the sections into chunks of at most ``max_chars``; a file longer than a chunk is
    split at line boundaries, each part under its own header naming the file."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for section in sections:
        header = f"=== {section.label} ==="
        pending_header = True
        for line in section.lines:
            needed = len(line) + 1 + (len(header) + 1 if pending_header else 0)
            if current and size + needed > max_chars:
                chunks.append("\n".join(current))
                current, size, pending_header = [], 0, True
                needed = len(line) + 1 + len(header) + 1
            if pending_header:
                current.append(header)
                size += len(header) + 1
                pending_header = False
            current.append(line)
            size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


_CITATION = re.compile(r"([\w.\-/]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?")


def unmatched_citations(text: str, sections: list[Section], *, only_sent_files: bool) -> list[str]:
    """Each path:line the answer cites that names a file or a line it was not sent.

    ``only_sent_files`` checks only citations of the files that were sent: a log names source
    locations of its own (a compiler error's file:line), and citing those is the point.
    """
    sent: dict[str, set[int]] = {}
    for section in sections:
        numbers = sent.setdefault(section.label, set())
        numbers.update(int(line.split("|", 1)[0]) for line in section.lines)
    unmatched: list[str] = []
    for match in _CITATION.finditer(text):
        path, first, last = match.group(1), int(match.group(2)), int(match.group(3) or match.group(2))
        if path not in sent:
            if not only_sent_files:
                unmatched.append(match.group(0))
        elif first not in sent[path] or last not in sent[path]:
            unmatched.append(match.group(0))
    return list(dict.fromkeys(unmatched))


def _checked(answer: LocalAnswer, sections: list[Section], *, only_sent_files: bool) -> LocalAnswer:
    unmatched = unmatched_citations(answer.text, sections, only_sent_files=only_sent_files)
    if not unmatched:
        return answer
    note = (f"These citations name a file or line the model was not sent, so they are wrong: "
            f"{', '.join(unmatched)}.")
    return replace(answer, notes=(*answer.notes, note))


def _request(system: str, question: str, body: str) -> ChatRequest:
    return ChatRequest(system=system, user=f"Question: {question}\n\n{body}", temperature=ANSWER_TEMPERATURE,
                       max_tokens=ANSWER_MAX_TOKENS)


def ask_local(pool: LocalLlmPool, question: str, sections: list[Section], *,
              only_sent_files: bool = False) -> LocalAnswer:
    """Answer ``question`` over ``sections``, with its citations checked against what was sent."""
    return _checked(_answer(pool, question, sections), sections, only_sent_files=only_sent_files)


def _answer(pool: LocalLlmPool, question: str, sections: list[Section]) -> LocalAnswer:
    """One request when the sections fit one chunk; otherwise one per chunk (in parallel, spread
    over the pool) and a final request merging the partial answers."""
    chunks = chunk_sections(sections)
    if len(chunks) > MAX_CHUNKS:
        raise ReadScopeError(
            f"That is {len(chunks)} chunks of text (about {sum(map(len, chunks)) // 4:,} tokens); at most "
            f"{MAX_CHUNKS} are read per call. Name fewer files, or ask about a narrower glob.")
    notes = tuple(section.note for section in sections if section.note)
    files = len({section.label for section in sections})
    lines = sum(len(section.lines) for section in sections)
    if len(chunks) == 1:
        reply = pool.chat(_request(ASK_SYSTEM, question, chunks[0]))
        return LocalAnswer(reply.text, (reply.host.label(),), files, lines, 1, notes)
    with ThreadPoolExecutor(max_workers=MAP_WORKERS) as workers:
        partials = list(workers.map(lambda chunk: pool.chat(_request(MAP_SYSTEM, question, chunk)), chunks))
    models = tuple(dict.fromkeys(reply.host.label() for reply in partials))
    relevant = [reply.text for reply in partials if reply.text.strip() != NOTHING_RELEVANT]
    if not relevant:
        return LocalAnswer("Nothing in these files answers the question.", models, files, lines, len(chunks), notes)
    if len(relevant) == 1:
        return LocalAnswer(relevant[0], models, files, lines, len(chunks), notes)
    merged = pool.chat(_request(REDUCE_SYSTEM, question, "\n\n".join(
        f"Partial answer {n}:\n{text}" for n, text in enumerate(relevant, start=1))))
    return LocalAnswer(merged.text, tuple(dict.fromkeys((*models, merged.host.label()))), files, lines,
                       len(chunks), notes)


def ask_files(scope: ReadScope, pool: LocalLlmPool, specs: list[str], question: str) -> LocalAnswer:
    sections = [read_section(scope, path) for path in scope.files(specs)]
    return ask_local(pool, question, sections)


def digest_log(scope: ReadScope, pool: LocalLlmPool, spec: str, focus: str) -> LocalAnswer:
    paths = scope.files([spec])
    if len(paths) != 1:
        raise ReadScopeError(f"'{spec}' names {len(paths)} files; digest_log reads one log. Name the file itself.")
    section = reduce_log(read_section(scope, paths[0]), MAX_CHUNK_CHARS * MAX_CHUNKS)
    question = f"{DIGEST_QUESTION} Focus: {focus}" if focus.strip() else DIGEST_QUESTION
    return ask_local(pool, question, [section], only_sent_files=True)
