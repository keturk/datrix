"""What every skill assist shares: where output goes, how text reaches a model, how answers are read.

CONTENT FILTER
    Design documents and findings files are framework documents, but a line can still carry a
    registered customer term. Every line is checked against the customer-term corpus before it is
    sent to a local model, exactly as ``shared.local_reading`` does for source and logs; a line that
    carries one is replaced by a placeholder that keeps its line number. Without the corpus nothing
    is sent: an unfiltered send is what the filter exists to stop.

EXIT CODES (shared by every assist command)
    0  done
    1  the request could not be carried out (the message says what to pass instead)
    2  the assist ran and its check found something the skill must act on
    3  no local model answered: the skill does this phase itself, as it did before the assist
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from dev.customer_domain_isolation import TermCorpus, scan_text
from shared.local_llm import ChatRequest, LocalLlmPool
from shared.local_reading import (
    CITATION,
    ReadScopeError,
    Section,
    filtered_section,
    load_workspace_term_corpus,
)

LOG = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CHECK_FAILED = 2
EXIT_NO_MODEL = 3

OUTPUT_DIR_PARTS = (".tmp", "assist")
JSON_TEMPERATURE = 0.1
JSON_MAX_TOKENS = 6000
JSON_ATTEMPTS = 2
MAP_WORKERS = 4
ANSWER_EXCERPT_CHARS = 200
BINARY_PROBE_BYTES = 8192
FENCE = "```"

T = TypeVar("T")
R = TypeVar("R")


class AssistError(RuntimeError):
    """The request cannot be carried out; the message says what was wrong and what to pass instead."""


class NoModelAnswer(RuntimeError):
    """A local model answered, but never with output the assist can use."""


def output_dir(workspace: Path) -> Path:
    """``<workspace>/.tmp/assist``, created if missing: every assist writes its output there."""
    directory = workspace.joinpath(*OUTPUT_DIR_PARTS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def workspace_label(workspace: Path, path: Path) -> str:
    """``path`` relative to the workspace in posix form, or the full path when it lies outside."""
    resolved = path.resolve()
    if resolved.is_relative_to(workspace.resolve()):
        return resolved.relative_to(workspace.resolve()).as_posix()
    return resolved.as_posix()


def read_text(path: Path) -> str:
    """The text of a file; refuses a missing or binary file with a message naming it."""
    if not path.is_file():
        raise AssistError(f"'{path}' is not a file. Pass the path of an existing text file.")
    data = path.read_bytes()
    if b"\0" in data[:BINARY_PROBE_BYTES]:
        raise AssistError(f"'{path}' is a binary file; only text files can be read.")
    return data.decode("utf-8-sig", errors="replace")


class ContentFilter:
    """Withholds every line that carries a registered customer term before text is sent to a model."""

    def __init__(self, workspace: Path) -> None:
        try:
            self._corpus: TermCorpus = load_workspace_term_corpus(workspace)
        except ReadScopeError as exc:
            raise AssistError(str(exc)) from exc

    def section(self, label: str, text: str) -> Section:
        """``text`` with every line numbered, and each line carrying a registered term withheld."""
        return filtered_section(label, text, self._corpus)

    def carries_term(self, text: str) -> bool:
        """True when any line of ``text`` carries a registered customer term."""
        return bool(scan_text(text, self._corpus))


def section_body(section: Section, first: int = 1, last: int | None = None) -> str:
    """The numbered lines ``first``..``last`` of ``section`` under a header naming it."""
    end = len(section.lines) if last is None else last
    return "\n".join([f"=== {section.label} ===", *section.lines[first - 1:end]])


def _json_object(text: str) -> dict[str, object]:
    """The JSON object in a model's answer, with a surrounding code fence removed."""
    body = text.strip()
    if body.startswith(FENCE):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit(FENCE, 1)[0]
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def ask_json(pool: LocalLlmPool, system: str, user: str, schema: dict[str, object]) -> dict[str, object]:
    """A JSON object answering ``user``, constrained by ``schema``; asked again once if it does not parse.

    Raises NoModelAnswer when no attempt parses, and LocalLlmUnavailable when no server answers.
    """
    request = ChatRequest(system=system, user=user, temperature=JSON_TEMPERATURE, max_tokens=JSON_MAX_TOKENS,
                          json_schema=schema)
    failure = ""
    for _attempt in range(JSON_ATTEMPTS):
        reply = pool.chat(request)
        try:
            return _json_object(reply.text)
        except ValueError as exc:
            failure = f"{reply.host.label()}: {exc}; the answer began: {reply.text[:ANSWER_EXCERPT_CHARS]!r}"
            LOG.warning("Unusable JSON from a local model: %s", failure)
    raise NoModelAnswer(f"No local model answer was valid JSON after {JSON_ATTEMPTS} attempts. Last: {failure}")


def string_list(value: object) -> list[str]:
    """The strings of a JSON array; anything else yields an empty list."""
    return [str(item) for item in value] if isinstance(value, list) else []


def object_list(value: object) -> list[dict[str, object]]:
    """The objects of a JSON array; anything else yields an empty list."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def parallel(items: Sequence[T], work: Callable[[T], R]) -> list[R]:
    """``work`` over ``items``, a few at a time (the pool spreads them over the model servers), in order."""
    if len(items) <= 1:
        return [work(item) for item in items]
    with ThreadPoolExecutor(max_workers=MAP_WORKERS) as workers:
        return list(workers.map(work, items))


def citations_in(text: str) -> list[str]:
    """Every ``path:line`` or ``path:first-last`` citation in ``text``, in order, each once."""
    return list(dict.fromkeys(match.group(0) for match in CITATION.finditer(text)))


@dataclass(frozen=True)
class MarkdownSection:
    """One heading of a markdown file and the lines under it (1-based, inclusive, heading line first)."""

    heading: str
    level: int
    start: int
    end: int


def _heading(line: str) -> tuple[int, str] | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    rest = stripped[level:]
    if not rest.startswith(" "):
        return None
    return level, rest.strip()


def markdown_sections(lines: Sequence[str], max_level: int) -> list[MarkdownSection]:
    """The sections headed at ``max_level`` or above, ignoring ``#`` lines inside code fences.

    Text before the first such heading becomes a section with an empty heading (level 0) when it
    holds anything but blank lines.
    """
    starts: list[tuple[int, int, str]] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        found = None if in_fence else _heading(line)
        if found is not None and found[0] <= max_level:
            starts.append((number, found[0], found[1]))
    sections: list[MarkdownSection] = []
    first = starts[0][0] if starts else len(lines) + 1
    if any(line.strip() for line in lines[:first - 1]):
        sections.append(MarkdownSection("", 0, 1, first - 1))
    for index, (start, level, heading) in enumerate(starts):
        end = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(lines)
        sections.append(MarkdownSection(heading, level, start, end))
    return sections


def write_output(workspace: Path, name: str, text: str) -> Path:
    """Write ``text`` to ``<workspace>/.tmp/assist/<name>`` and return the path."""
    path = output_dir(workspace) / name
    path.write_text(text, encoding="utf-8")
    return path
