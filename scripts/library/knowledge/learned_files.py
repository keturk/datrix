"""The committed text copy of every learned answer, one markdown file per answer.

The SQLite database lives under the workspace root and is per machine; these files live in the
showcase repository, so they travel with git. Each machine rebuilds or updates its database from
them (``sync_learned``), and every answer learned on one machine reaches the other with the next pull.

One file per answer, named by the hash of its question, so two machines learning different things
never conflict, and one learning the same thing writes the same file name. A file records the
content hash of every source file its answer was drawn from; a machine imports it only while those
files still hash the same there, so an answer never outlives the code or docs it described.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from knowledge.seed import in_scope
from knowledge.store import KnowledgeBase, KnowledgeError, LearnedEntry, file_sha256
from shared.local_reading import ReadScope

LOG = logging.getLogger(__name__)

LEARNED_DIR_RELATIVE = "datrix/docs/knowledge/learned"
KEY_LENGTH = 12
FRONT_MATTER_FENCE = "---"
_SOURCE_PREFIX = "source: "
_WHITESPACE = re.compile(r"\s+")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LearnedSync:
    imported: int
    stale: int
    dropped: int

    def render(self) -> str:
        return f"learned files: {self.imported} imported, {self.stale} stale (not imported), {self.dropped} dropped"


def normalize_question(question: str) -> str:
    return _WHITESPACE.sub(" ", question).strip()


def entry_key(question: str) -> str:
    return hashlib.sha256(normalize_question(question).lower().encode("utf-8")).hexdigest()[:KEY_LENGTH]


def learned_dir(scope: ReadScope) -> Path:
    return scope.workspace / LEARNED_DIR_RELATIVE


def render_entry(entry: LearnedEntry) -> str:
    lines = [FRONT_MATTER_FENCE, f"id: {entry.key}", f"question: {normalize_question(entry.question)}",
             f"model: {entry.model}", f"learned: {entry.created_at}"]
    lines.extend(f"{_SOURCE_PREFIX}{path} {sha}" for path, sha in sorted(entry.sources.items()))
    lines.extend([FRONT_MATTER_FENCE, "", entry.answer.strip(), ""])
    return "\n".join(lines)


def parse_entry(text: str, origin: str) -> LearnedEntry:
    """Read one learned file back; a file that does not parse is an error naming it, never skipped."""
    lines = text.splitlines()
    if not lines or lines[0] != FRONT_MATTER_FENCE:
        raise KnowledgeError(f"{origin}: a learned file starts with a '---' front-matter line. Fix or delete it.")
    try:
        end = lines.index(FRONT_MATTER_FENCE, 1)
    except ValueError:
        raise KnowledgeError(f"{origin}: the front matter is not closed by a second '---' line.") from None
    fields: dict[str, str] = {}
    sources: dict[str, str] = {}
    for line in lines[1:end]:
        if line.startswith(_SOURCE_PREFIX):
            path, _, sha = line[len(_SOURCE_PREFIX):].rpartition(" ")
            if not path or not _SHA256.match(sha):
                raise KnowledgeError(f"{origin}: malformed source line '{line}' (expected 'source: <path> <sha256>').")
            sources[path] = sha
            continue
        name, _, value = line.partition(": ")
        fields[name] = value
    missing = [name for name in ("id", "question", "model", "learned") if not fields.get(name)]
    answer = "\n".join(lines[end + 1:]).strip()
    if missing or not answer or not sources:
        raise KnowledgeError(
            f"{origin}: a learned file needs id, question, model, learned, at least one source and an answer "
            f"(missing: {', '.join(missing) or 'answer or source'}).")
    if fields["id"] != entry_key(fields["question"]):
        raise KnowledgeError(f"{origin}: id {fields['id']} is not the hash of its question; the file was edited by hand.")
    return LearnedEntry(fields["id"], fields["question"], answer, fields["model"], fields["learned"], sources)


def write_entry(scope: ReadScope, entry: LearnedEntry) -> Path:
    directory = learned_dir(scope)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entry.key}.md"
    path.write_text(render_entry(entry), encoding="utf-8", newline="\n")
    return path


def read_entries(scope: ReadScope) -> dict[str, LearnedEntry]:
    directory = learned_dir(scope)
    if not directory.is_dir():
        return {}
    found: dict[str, LearnedEntry] = {}
    for path in sorted(directory.glob("*.md")):
        entry = parse_entry(path.read_text(encoding="utf-8"), scope.label(path.resolve()))
        if path.stem != entry.key:
            raise KnowledgeError(f"{scope.label(path.resolve())}: file name does not match its id {entry.key}.")
        found[entry.key] = entry
    return found


def stale_sources(scope: ReadScope, entry: LearnedEntry) -> list[str]:
    """The sources whose content on this machine is not the content the answer was drawn from."""
    stale: list[str] = []
    for label, sha in entry.sources.items():
        path = (scope.workspace / label).resolve()
        if not (path.is_file() and in_scope(scope, path)) or file_sha256(path) != sha:
            stale.append(label)
    return stale


def sync_learned(kb: KnowledgeBase, scope: ReadScope) -> LearnedSync:
    """Make the database's learned answers the current ones among the committed text files.

    A text file is imported when it is new or changed and its sources still match; an answer in the
    database whose file is gone (deleted on another machine) or whose sources changed is dropped from
    the database. Files are never deleted here: only learning an answer again or pruning rewrites them.
    """
    files = read_entries(scope)
    stored = kb.learned()
    imported = stale = dropped = 0
    for key, entry in files.items():
        if stale_sources(scope, entry):
            stale += 1
            if key in stored:
                kb.remove_learned(key)
                dropped += 1
            continue
        if stored.get(key) == entry:
            continue
        kb.upsert_learned(entry)
        imported += 1
    for key in stored:
        if key not in files:
            kb.remove_learned(key)
            dropped += 1
    report = LearnedSync(imported, stale, dropped)
    if imported or dropped:
        LOG.info("knowledge base %s", report.render())
    return report


def prune_stale(scope: ReadScope) -> list[str]:
    """Delete the learned files whose sources changed on this machine; returns the files removed."""
    removed: list[str] = []
    for key, entry in read_entries(scope).items():
        if stale_sources(scope, entry):
            (learned_dir(scope) / f"{key}.md").unlink()
            removed.append(f"{LEARNED_DIR_RELATIVE}/{key}.md")
    return removed
