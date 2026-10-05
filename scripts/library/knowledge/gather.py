"""Gather an answer the knowledge base does not hold, with a local model, and keep it if it holds up.

The model is shown the closest chunks of the docs (with their real line numbers) and any files the
caller named, and asked a short, cited answer. The answer is kept only when it is grounded: it cites
at least one line, every citation names a file and line the model was actually sent, and every piece
of code it quotes is in what it was sent. A kept answer is written to the knowledge base and to its
committed text file, with the content hash of each cited file so it expires when they change. An
answer that fails the checks is reported, never stored: a wrong answer in the base would be repeated
to every agent that asks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from knowledge.learned_files import entry_key, normalize_question, write_entry
from knowledge.lookup import candidates
from knowledge.seed import in_scope
from knowledge.store import KIND_CURATED, KnowledgeBase, LearnedEntry, file_sha256
from shared.local_llm import LocalLlmPool
from shared.local_reading import (
    CITATION,
    MAX_LINE_CHARS,
    NOTHING_RELEVANT,
    ReadScope,
    Section,
    ask_local,
    read_section,
    unmatched_citations,
    unmatched_quotes,
)

LOG = logging.getLogger(__name__)

GATHER_CHUNKS = 8
CANDIDATE_POOL = 40
MAX_ANSWER_CHARS = 4000
NO_ANSWER_MARKERS = ("Nothing in these files answers the question.", NOTHING_RELEVANT)
BRIEF_INSTRUCTION = (
    "Answer in at most 8 short lines. Cite path:line for every claim, using only the files given. "
    "If the files do not answer it, say exactly: NOTHING RELEVANT.")


@dataclass(frozen=True)
class Gathered:
    """What a gather produced: the stored answer, or why nothing was stored."""

    stored: bool
    text: str
    models: tuple[str, ...]
    problems: tuple[str, ...]
    leads: tuple[str, ...]


_MODEL_NAME = re.compile(r"model '([^']+)'")


def model_names(labels: tuple[str, ...]) -> str:
    """The model names in a model server's labels, and nothing else: a learned answer is committed, and the
    label also names the server's address, which is internal to this network."""
    names = dict.fromkeys(match.group(1) for label in labels if (match := _MODEL_NAME.search(label)))
    return ", ".join(names) or "local model"


def _chunk_sections(kb: KnowledgeBase, question: str) -> tuple[list[Section], tuple[str, ...]]:
    sections: list[Section] = []
    leads: list[str] = []
    for hit in candidates(kb, question, CANDIDATE_POOL):
        entry = hit.entry
        if entry.kind != KIND_CURATED:
            continue
        lines = tuple(f"{entry.line_start + offset}| {line[:MAX_LINE_CHARS]}"
                      for offset, line in enumerate(entry.body.splitlines()))
        sections.append(Section(entry.source_path, lines))
        leads.append(f"{entry.source_path}:{entry.line_start}-{entry.line_end}  ({entry.topic})")
        if len(sections) == GATHER_CHUNKS:
            break
    return sections, tuple(leads)


def leads_for(kb: KnowledgeBase, question: str) -> tuple[str, ...]:
    """The closest places in the docs to read, for a caller that cannot ask a model."""
    return _chunk_sections(kb, question)[1]


def _cited_sources(scope: ReadScope, text: str) -> dict[str, str]:
    sources: dict[str, str] = {}
    for match in CITATION.finditer(text):
        label = match.group(1)
        path = (scope.workspace / label).resolve()
        if path.is_file() and in_scope(scope, path):
            sources[label] = file_sha256(path)
    return sources


def gather(kb: KnowledgeBase, scope: ReadScope, pool: LocalLlmPool, question: str,
           extra_specs: list[str]) -> Gathered:
    """Ask a local model ``question`` over the closest docs and the named files; keep a grounded answer.

    Raises ``LocalLlmUnavailable`` when no model server can answer, and ``ReadScopeError`` when a named
    file is out of scope or too much text was asked for.
    """
    sections, leads = _chunk_sections(kb, question)
    sections.extend(read_section(scope, path) for path in scope.files(extra_specs))
    if not sections:
        return Gathered(False, "No document is close to this question and no files were named with --in, so "
                        "there is nothing to read an answer from.", (), (), ())
    answer = ask_local(pool, f"{question}\n{BRIEF_INSTRUCTION}", sections, only_sent_files=False)
    text = answer.text.strip()
    problems = _problems(text, sections)
    if problems:
        return Gathered(False, "The local model's answer was not stored.", answer.models, tuple(problems), leads)
    entry = LearnedEntry(entry_key(question), normalize_question(question), text, model_names(answer.models),
                         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         _cited_sources(scope, text))
    kb.upsert_learned(entry)
    path = write_entry(scope, entry)
    LOG.info("knowledge base learned %s (%s)", entry.key, scope.label(path.resolve()))
    return Gathered(True, text, answer.models, (), leads)


def _problems(text: str, sections: list[Section]) -> list[str]:
    if not text or text in NO_ANSWER_MARKERS or text.startswith(NO_ANSWER_MARKERS[0]):
        return ["the files it was shown do not answer the question"]
    if len(text) > MAX_ANSWER_CHARS:
        return [f"the answer is {len(text):,} characters; a stored answer is at most {MAX_ANSWER_CHARS:,}"]
    problems: list[str] = []
    if not CITATION.search(text):
        problems.append("it cites no path:line, so nothing in it can be checked")
    wrong = unmatched_citations(text, sections, only_sent_files=False)
    if wrong:
        problems.append(f"it cites a file or line it was not sent: {', '.join(wrong)}")
    invented = unmatched_quotes(text, sections)
    if invented:
        shown = "; ".join(snippet.replace("\n", " ")[:90] for snippet in invented[:3])
        problems.append(f"it quotes code that is not in what it was sent: {shown}")
    return problems
