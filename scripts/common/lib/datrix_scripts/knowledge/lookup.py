"""Answer a question from the knowledge base alone: full-text search, then a coverage check.

Full-text ranking says which chunk is closest, not whether it answers. A chunk answers only when it
carries most of the question's significant words, so a question about something the base does not
hold comes back empty (and the caller may then gather the answer) instead of returning the nearest
unrelated paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass

from datrix_scripts.knowledge.learned_files import stale_sources
from datrix_scripts.knowledge.store import KIND_CURATED, Entry, Hit, KnowledgeBase, LearnedEntry
from datrix_scripts.knowledge.store import split_words as words
from datrix_scripts.local_reading import ReadScope

CANDIDATE_LIMIT = 40
DEFAULT_ANSWERS = 3
BRIEF_CHARS = 700
MAX_TOPIC_CHARS = 110
MIN_COVERAGE = 0.6
HEADING_WEIGHT = 2.0
MIN_TERM_LENGTH = 2
MAX_TERMS = 24

_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its my of on or should so that the "
    "their there this to was we what when where which who why will with without you your need know want find "
    "get use used using about into than then them these those if not no yes any all each".split())


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def query_terms(question: str) -> list[str]:
    """The question's significant words, de-duplicated, in order."""
    found = dict.fromkeys(
        word for word in words(question) if len(word) >= MIN_TERM_LENGTH and word not in _STOPWORDS)
    return list(found)[:MAX_TERMS]


def match_expression(terms: list[str]) -> str:
    return " OR ".join(f'"{term}"' for term in terms)


def _share(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    present = {stem(word) for word in words(text)}
    return sum(1 for term in terms if stem(term) in present) / len(terms)


def coverage(terms: list[str], entry: Entry) -> float:
    return _share(terms, f"{entry.topic} {entry.body} {entry.question}")


def heading_share(terms: list[str], entry: Entry) -> float:
    """How much of the question the entry's heading path (or a learned answer's question) carries: a
    section titled for the subject outranks a paragraph that merely mentions it."""
    return _share(terms, f"{entry.topic} {entry.question}")


@dataclass(frozen=True)
class Answer:
    entry: Entry
    coverage: float
    heading_share: float

    @property
    def score(self) -> float:
        """Coverage says whether a chunk answers; the heading weighs double in which answers best, so
        generic words in a paragraph ("package", "owns") cannot outrank a section named for the subject."""
        return self.coverage + HEADING_WEIGHT * self.heading_share


def candidates(kb: KnowledgeBase, question: str, limit: int = CANDIDATE_LIMIT) -> list[Hit]:
    terms = query_terms(question)
    if not terms:
        return []
    return kb.search(match_expression(terms), limit)


def lookup(kb: KnowledgeBase, scope: ReadScope, question: str, limit: int = DEFAULT_ANSWERS) -> list[Answer]:
    """The entries that answer ``question``, best first: authored docs before learned answers at equal
    coverage, then by relevance. A learned answer whose sources changed is dropped, not returned."""
    terms = query_terms(question)
    answers: list[tuple[Answer, float]] = []
    for hit in candidates(kb, question):
        share = coverage(terms, hit.entry)
        if share < MIN_COVERAGE:
            continue
        if hit.entry.kind != KIND_CURATED and _is_stale(kb, scope, hit.entry):
            kb.remove_learned(hit.entry.entry_key)
            continue
        answers.append((Answer(hit.entry, share, heading_share(terms, hit.entry)), hit.rank))
    answers.sort(key=lambda pair: (-round(pair[0].score, 2), pair[0].entry.kind != KIND_CURATED, pair[1]))
    return [answer for answer, _ in answers[:limit]]


def _is_stale(kb: KnowledgeBase, scope: ReadScope, entry: Entry) -> bool:
    learned = LearnedEntry(entry.entry_key, entry.question, entry.body, entry.model, entry.created_at,
                           kb.sources_of(entry.id))
    return bool(stale_sources(scope, learned))


def brief(text: str, limit: int = BRIEF_CHARS) -> str:
    """``text`` cut at a line boundary to about ``limit`` characters, saying how much was left out."""
    lines = text.strip().splitlines()
    kept: list[str] = []
    size = 0
    for line in lines:
        if kept and size + len(line) + 1 > limit:
            break
        kept.append(line)
        size += len(line) + 1
    left = len(lines) - len(kept)
    return "\n".join(kept) + (f"\n… (+{left} more line(s))" if left else "")


def _short(topic: str) -> str:
    """The heading path with its deepest headings kept when it is long."""
    if len(topic) <= MAX_TOPIC_CHARS:
        return topic
    return "…" + topic[-(MAX_TOPIC_CHARS - 1):]


def render(answers: list[Answer]) -> str:
    blocks: list[str] = []
    for answer in answers:
        entry = answer.entry
        if entry.kind == KIND_CURATED:
            header = f"[doc] {_short(entry.topic)}  — {entry.source_path}:{entry.line_start}-{entry.line_end}"
            blocks.append(f"{header}\n{brief(entry.body)}")
            continue
        header = f"[learned by {entry.model} on {entry.created_at[:10]}] {entry.question}"
        blocks.append(f"{header}\n{brief(entry.body, BRIEF_CHARS * 2)}")
    return "\n\n".join(blocks)
