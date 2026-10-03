"""Curated knowledge: the project's own docs, cut into chunks by heading and kept in step with them.

The docs stay the source of truth; the database holds a searchable copy keyed by each doc's content
hash, so an edited doc is re-cut on the next question and a deleted one disappears. Only files inside
the framework repositories are read (``shared.local_reading.ReadScope`` decides), so a customer
checkout beside them can never enter the knowledge base.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from knowledge.store import Chunk, KnowledgeBase, file_sha256
from shared.local_reading import GIT_DIR_NAME, ReadScope

LOG = logging.getLogger(__name__)

# The one place to add a doc to the knowledge base: workspace-relative globs. A doc that is not
# matched here is still readable with --in; it just is not answered from without being asked for.
CURATED_PATTERNS: tuple[str, ...] = (
    "datrix/docs/architecture/*.md",
    "datrix/docs/architecture/packs/*.md",
    "datrix/docs/architecture/architecture/*.md",
    "datrix-common/docs/contributing/ai-agent-rules.md",
    "datrix-common/docs/contributing/ai-agent-rules/*.md",
    "datrix-common/docs/contributing/test-guidelines/*.md",
    "datrix/claude-config/.claude/CLAUDE.md",
    "datrix/claude-config/.claude/rules/*.md",
    "datrix/claude-config/.claude/skills/_shared/*.md",
    "datrix/scripts/quick-reference.md",
    "datrix/scripts/*/quick-reference.md",
    "datrix-*/docs/architecture.md",
    "datrix-language/docs/reference/*.md",
)

MAX_CHUNK_CHARS = 1800
MIN_CHUNK_CHARS = 60
MAX_HEADING_LEVEL = 4

_HEADING = re.compile(rf"^(#{{1,{MAX_HEADING_LEVEL}}})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TOPIC_SEPARATOR = " > "


@dataclass(frozen=True)
class SyncReport:
    added: int
    updated: int
    removed: int

    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)

    def render(self) -> str:
        return f"docs: {self.added} added, {self.updated} updated, {self.removed} removed"


def _plain(heading: str) -> str:
    return _LINK.sub(r"\1", heading).replace("`", "").strip()


def _pieces(lines: list[str], first_line: int) -> list[tuple[int, list[str]]]:
    """Split one section's lines at blank lines into runs of at most MAX_CHUNK_CHARS (a single block
    longer than that, such as a big table, is split by line)."""
    blocks: list[tuple[int, list[str]]] = []
    start = first_line
    block: list[str] = []
    for offset, line in enumerate(lines):
        number = first_line + offset
        if line.strip() == "" and block:
            blocks.append((start, block))
            block = []
            continue
        if line.strip() == "":
            continue
        if not block:
            start = number
        block.append(line)
    if block:
        blocks.append((start, block))
    return _pack(blocks)


def _pack(blocks: list[tuple[int, list[str]]]) -> list[tuple[int, list[str]]]:
    packed: list[tuple[int, list[str]]] = []
    current: list[str] = []
    current_start = 0
    current_next = 0
    for start, block in blocks:
        for piece_start, piece in _split_long(start, block):
            size = sum(len(line) + 1 for line in current)
            adds = sum(len(line) + 1 for line in piece)
            if current and size + adds > MAX_CHUNK_CHARS:
                packed.append((current_start, current))
                current = []
            if not current:
                current_start = piece_start
                current = list(piece)
            else:
                gap = piece_start - current_next
                current.extend([""] * gap)
                current.extend(piece)
            current_next = piece_start + len(piece)
    if current:
        packed.append((current_start, current))
    return packed


def _split_long(start: int, block: list[str]) -> list[tuple[int, list[str]]]:
    if sum(len(line) + 1 for line in block) <= MAX_CHUNK_CHARS:
        return [(start, block)]
    parts: list[tuple[int, list[str]]] = []
    part: list[str] = []
    part_start = start
    size = 0
    for offset, line in enumerate(block):
        if part and size + len(line) + 1 > MAX_CHUNK_CHARS:
            parts.append((part_start, part))
            part = []
            size = 0
            part_start = start + offset
        part.append(line)
        size += len(line) + 1
    if part:
        parts.append((part_start, part))
    return parts


def chunk_markdown(text: str, title: str) -> list[Chunk]:
    """Cut a markdown document into chunks under their heading path (``title > H2 > H3``).

    A chunk's body is the document's own lines verbatim, so ``line_start + i`` is the real line
    number of body line ``i``: an answer built from chunks can cite a line that exists.
    """
    lines = text.splitlines()
    sections: list[tuple[str, int, list[str]]] = []
    stack: list[tuple[int, str]] = []
    start = 1
    current: list[str] = []
    in_fence = False
    topic = title
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading is not None:
            sections.append((topic, start, current))
            level = len(heading.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, _plain(heading.group(2))))
            topic = _TOPIC_SEPARATOR.join([title, *(name for _, name in stack)])
            start = number
            current = []
        current.append(line)
    sections.append((topic, start, current))

    chunks: list[Chunk] = []
    for section_topic, section_start, section_lines in sections:
        for piece_start, piece in _pieces(section_lines, section_start):
            body = "\n".join(piece)
            if len(body.strip()) >= MIN_CHUNK_CHARS:
                chunks.append(Chunk(section_topic, body, piece_start, piece_start + len(piece) - 1))
    return chunks


def in_scope(scope: ReadScope, path: Path) -> bool:
    resolved = path.resolve()
    return GIT_DIR_NAME not in resolved.parts and any(resolved.is_relative_to(root) for root in scope.roots)


def curated_files(scope: ReadScope) -> dict[str, Path]:
    """Workspace-relative path -> file, for every doc the patterns match inside the read scope."""
    found: dict[str, Path] = {}
    for pattern in CURATED_PATTERNS:
        for path in sorted(scope.workspace.glob(pattern)):
            if path.is_file() and in_scope(scope, path):
                found[scope.label(path.resolve())] = path.resolve()
    return found


def sync_curated(kb: KnowledgeBase, scope: ReadScope) -> SyncReport:
    """Bring the curated chunks up to date with the docs on disk."""
    wanted = curated_files(scope)
    stored = kb.curated_docs()
    added = updated = 0
    for label, path in wanted.items():
        sha = file_sha256(path)
        if stored.get(label) == sha:
            continue
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        kb.replace_curated_doc(label, sha, chunk_markdown(text, path.stem))
        if label in stored:
            updated += 1
        else:
            added += 1
    removed = 0
    for label in stored:
        if label not in wanted:
            kb.remove_curated_doc(label)
            removed += 1
    report = SyncReport(added, updated, removed)
    if report.changed():
        LOG.info("knowledge base %s", report.render())
    return report
