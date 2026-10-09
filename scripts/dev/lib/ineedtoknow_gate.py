#!/usr/bin/env python3
"""Repo-level gate for ineedtoknow (datrix_scripts.knowledge, dev/lib/ineedtoknow_cli.py).

Every check builds a real workspace in a temporary directory (framework repositories plus a
customer-style repository beside them), uses real SQLite files, and talks to a real
Ollama-shaped HTTP server on loopback (datrix_scripts.local_llm_loopback) whose answers depend on
the prompt it receives. Nothing
here contacts the network's model servers, and nothing touches the machine's own knowledge base.

Run through dev/ineedtoknow-gate.ps1.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from datrix_scripts.knowledge.gather import Gathered, gather
from datrix_scripts.knowledge.learned_files import (
    entry_key,
    learned_dir,
    parse_entry,
    prune_stale,
    render_entry,
    sync_learned,
)
from datrix_scripts.knowledge.lookup import lookup
from datrix_scripts.knowledge.seed import chunk_markdown, sync_curated
from datrix_scripts.knowledge.store import KIND_CURATED, KIND_LEARNED, KnowledgeBase, KnowledgeError, LearnedEntry
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings, LocalLlmUnavailable
from datrix_scripts.local_llm_loopback import LOOPBACK, Chat, ChatAnswer, LoopbackOllama, answering, closed_port
from datrix_scripts.local_reading import ReadScope
from datrix_scripts.paths import script_env

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"
_CLI = Path(__file__).resolve().parent / "ineedtoknow_cli.py"

_TENANCY_DOC = """# Tenancy Pack

## Cross Tenant Bodies

A crossTenant body is the only way a handler reaches rows across tenants. The tenant middleware stays
unchanged and every other route stays fail closed.

## Gateways

Gateway realizations consume one shared route enumeration, so the public surface never diverges
between platforms.

```text
# not a heading, inside a fence
```

| Platform | Edge |
|---|---|
| nginx | location blocks |
"""

_ARCH_DOC = "# Alpha\n\nThe alpha package owns the widget registry and every widget factory it exposes.\n"
_TENANCY_PATH = "datrix/docs/architecture/packs/tenancy.md"
_ALPHA_PATH = "datrix-alpha/docs/architecture.md"
_CUSTOMER_DOC = "# Customer\n\nAcme's private warehouse routing rules live in this document and nowhere else.\n"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    """Run every check, catching only AssertionError. Returns True iff all passed."""
    all_passed = True
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            _fail(f"{check.__name__}: {exc}")
            all_passed = False
        else:
            _ok(check.__name__)
    return all_passed


# ===========================================================================
# fixtures
# ===========================================================================


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@contextmanager
def _workspace() -> Iterator[Path]:
    with TemporaryDirectory(prefix="ineedtoknow-gate-") as temp:
        root = Path(temp)
        for repo in ("datrix", "datrix-alpha", "acme-shop"):
            (root / repo / ".git").mkdir(parents=True)
        _write(root / _TENANCY_PATH, _TENANCY_DOC)
        _write(root / _ALPHA_PATH, _ARCH_DOC)
        _write(root / "acme-shop" / "docs" / "architecture.md", _CUSTOMER_DOC)
        yield root


def _pool(ollama_port: int, usage_log: Path) -> LocalLlmPool:
    settings = LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                allow_load=False, ollama_port=ollama_port, usage_log=usage_log, caller="gate")
    return LocalLlmPool(settings, report=lambda _line: None)


_HEADER = re.compile(r"^=== (.+?) ===$", re.MULTILINE)
_FIRST_NUMBER = re.compile(r"^(\d+)\| ", re.MULTILINE)


def _sent_location(user: str) -> str:
    """A path:line the prompt really carries: the first file header and the first numbered line after it."""
    header = _HEADER.search(user)
    assert header is not None, f"the prompt carries no file header: {user[:200]!r}"
    number = _FIRST_NUMBER.search(user, header.end())
    assert number is not None, "the prompt carries no numbered line under its first header"
    return f"{header.group(1)}:{number.group(1)}"


def _grounded(chat: Chat) -> str:
    return f"Gateways share one route enumeration, so the public surface cannot diverge ({_sent_location(chat.user)})."


QUESTION = "how do gateways share enumeration zebra quokka"


# ===========================================================================
# chunking, sync, lookup
# ===========================================================================


def check_chunks_keep_the_documents_own_line_numbers() -> None:
    lines = _TENANCY_DOC.splitlines()
    chunks = chunk_markdown(_TENANCY_DOC, "tenancy")
    assert [chunk.topic for chunk in chunks] == [
        "tenancy > Tenancy Pack > Cross Tenant Bodies", "tenancy > Tenancy Pack > Gateways"], \
        [chunk.topic for chunk in chunks]
    for chunk in chunks:
        original = [line.strip() for line in lines[chunk.line_start - 1:chunk.line_end]]
        assert [line.strip() for line in chunk.body.splitlines()] == original, \
            f"chunk {chunk.topic} does not equal lines {chunk.line_start}-{chunk.line_end} of the document"
    gateways = chunks[1]
    assert "# not a heading, inside a fence" in gateways.body and "| nginx |" in gateways.body, \
        "a '#' line inside a code fence must not start a new section, and a table must stay in its section"


def check_long_sections_split_into_bounded_chunks_that_keep_every_line() -> None:
    text = "# Long\n\n" + "\n".join(f"- item number {n} says something specific about topic {n}" for n in range(200))
    chunks = chunk_markdown(text, "long")
    assert len(chunks) > 3 and all(len(chunk.body) <= 2200 for chunk in chunks), [len(c.body) for c in chunks]
    lines = text.splitlines()
    for chunk in chunks:
        assert [line.strip() for line in chunk.body.splitlines()] == \
            [line.strip() for line in lines[chunk.line_start - 1:chunk.line_end]], chunk.line_start
    covered = {n for chunk in chunks for n in range(chunk.line_start, chunk.line_end + 1)}
    assert all(n in covered for n in range(3, len(lines) + 1)), "a line of a long section was dropped"


def check_sync_adds_updates_and_removes_docs_and_never_reads_a_customer_repo() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        scope = ReadScope(root)
        first = sync_curated(kb, scope)
        assert (first.added, first.updated, first.removed) == (2, 0, 0), first
        assert set(kb.curated_docs()) == {_TENANCY_PATH, _ALPHA_PATH}, kb.curated_docs()
        assert not any("acme" in answer.entry.source_path
                       for answer in lookup(kb, scope, "Acme private warehouse routing rules")), \
            "a customer repository must never reach the knowledge base"
        assert sync_curated(kb, scope).changed() is False, "an unchanged tree must change nothing"
        _write(root / _ALPHA_PATH, _ARCH_DOC + "\nIt also owns the gadget registry and the gadget factory.\n")
        assert sync_curated(kb, scope).updated == 1
        (root / _ALPHA_PATH).unlink()
        assert sync_curated(kb, scope).removed == 1 and set(kb.curated_docs()) == {_TENANCY_PATH}


def check_lookup_answers_covered_questions_only() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        scope = ReadScope(root)
        sync_curated(kb, scope)
        found = lookup(kb, scope, "how does the crossTenant body reach rows")
        assert found and found[0].entry.topic.endswith("Cross Tenant Bodies"), \
            "a camelCase identifier in the doc must match the same words in a question"
        assert found[0].entry.line_start == 3, found[0].entry
        assert lookup(kb, scope, "what colour is the database logo") == [], "an unrelated question must find nothing"
        assert lookup(kb, scope, "cross tenant kubernetes helm charts") == [], \
            "a chunk that covers two of five significant words does not answer the question"
        assert lookup(kb, scope, "the and of") == [], "a question of stopwords only must find nothing"


def check_a_section_titled_for_the_subject_outranks_a_mention() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        _write(root / "datrix/docs/architecture/packs/other.md",
               "# Other\n\n## Overview\n\nThe gateway route enumeration is mentioned here: gateway route enumeration, "
               "and again gateway route enumeration, so a body match alone would rank this paragraph first.\n")
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        scope = ReadScope(root)
        sync_curated(kb, scope)
        found = lookup(kb, scope, "gateway route enumeration")
        assert len(found) >= 2, [answer.entry.topic for answer in found]
        assert found[0].entry.topic.endswith("Gateways"), \
            f"the section titled for the subject must come first: {[a.entry.topic for a in found]}"


# ===========================================================================
# the committed text copy and two machines
# ===========================================================================


def check_learned_file_round_trips_and_rejects_tampering() -> None:
    sha = "ab" * 32
    question = "How are tenants isolated?"
    entry = LearnedEntry(entry_key(question), question, "Every route is fail closed (a/b.py:3).", "gate-model",
                         "2026-10-03T12:00:00Z", {"datrix/docs/a.md": sha})
    assert parse_entry(render_entry(entry), "t.md") == entry, "a learned file must read back as written"
    for name, text in (
        ("hand-edited id", render_entry(entry).replace(f"id: {entry.key}", "id: 000000000000")),
        ("no front matter", "just text"),
        ("bad source hash", render_entry(entry).replace(sha, "nothex")),
        ("no answer", render_entry(entry).replace(entry.answer, "")),
    ):
        try:
            parse_entry(text, "t.md")
        except KnowledgeError:
            continue
        raise AssertionError(f"a learned file with {name} was accepted")


def _learn_with_model(root: Path, kb: KnowledgeBase, respond: ChatAnswer) -> Gathered:
    scope = ReadScope(root)
    with TemporaryDirectory(prefix="ineedtoknow-log-") as logs, LoopbackOllama(respond) as server:
        return gather(kb, scope, _pool(server.port, Path(logs) / "usage.jsonl"), QUESTION, [])


def check_a_second_machine_converges_from_the_text_files() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        scope = ReadScope(root)
        machine_a = KnowledgeBase(Path(db_dir) / "a.db")
        sync_curated(machine_a, scope)
        learned = _learn_with_model(root, machine_a, _grounded)
        assert learned.stored, learned.problems
        files = sorted(learned_dir(scope).glob("*.md"))
        assert len(files) == 1, files

        machine_b = KnowledgeBase(Path(db_dir) / "b.db")
        sync_curated(machine_b, scope)
        assert machine_b.learned() == {}, "a fresh machine starts with nothing learned"
        assert sync_learned(machine_b, scope).imported == 1
        assert machine_b.learned() == machine_a.learned(), "both machines must hold the same learned answers"

        machine_b.clear()
        sync_curated(machine_b, scope)
        sync_learned(machine_b, scope)
        assert machine_b.learned() == machine_a.learned(), "a rebuild from scratch must restore the learned answers"

        files[0].unlink()
        assert sync_learned(machine_a, scope).dropped == 1 and machine_a.learned() == {}, \
            "an answer whose text file was deleted elsewhere must leave the database"


def check_an_answer_expires_when_a_cited_file_changes() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        scope = ReadScope(root)
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        sync_curated(kb, scope)
        assert _learn_with_model(root, kb, _grounded).stored
        found = lookup(kb, scope, QUESTION)
        assert found and found[0].entry.kind == KIND_LEARNED, \
            f"the learned answer covers every word of its own question: {[a.entry.kind for a in found]}"
        _write(root / _TENANCY_PATH, _TENANCY_DOC + "\nA new paragraph changes what the document says.\n")
        assert all(answer.entry.kind == KIND_CURATED for answer in lookup(kb, scope, QUESTION)), \
            "an answer drawn from a file that changed must not be returned"
        assert kb.learned() == {}, "and it must leave the database"
        other = KnowledgeBase(Path(db_dir) / "other.db")
        sync_curated(other, scope)
        report = sync_learned(other, scope)
        assert (report.imported, report.stale) == (0, 1), "another machine must not import it either"
        assert len(list(learned_dir(scope).glob("*.md"))) == 1, "syncing must never delete a committed file"
        assert prune_stale(scope) and not list(learned_dir(scope).glob("*.md")), \
            "pruning is the explicit way to delete a stale file"


# ===========================================================================
# gathering
# ===========================================================================


def check_gather_reads_real_line_numbers_and_stores_a_grounded_answer() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        sync_curated(kb, ReadScope(root))
        scope = ReadScope(root)
        with TemporaryDirectory(prefix="ineedtoknow-log-") as logs, LoopbackOllama(_grounded) as server:
            gathered = gather(kb, scope, _pool(server.port, Path(logs) / "usage.jsonl"), QUESTION, [])
            prompt = server.chats[0].user
        assert gathered.stored and gathered.models, gathered
        assert f"=== {_TENANCY_PATH} ===" in prompt and "\n10| Gateway realizations consume" in prompt, \
            "the model must be sent the closest chunk with the document's own line numbers"
        assert "crossTenant" not in prompt, "a chunk that matches none of the question's words must not be sent"
        assert "acme" not in prompt.lower(), "no customer text may be sent"
        entry = next(iter(kb.learned().values()))
        assert list(entry.sources) == [_TENANCY_PATH], entry.sources
        committed = next(learned_dir(scope).glob("*.md")).read_text(encoding="utf-8")
        assert entry.model == "gate-model" and LOOPBACK not in committed and "http" not in committed, \
            f"a committed learned file must name the model, never the server's address: {committed[:300]!r}"


def _rejected(respond: ChatAnswer, what: str) -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        sync_curated(kb, ReadScope(root))
        gathered = _learn_with_model(root, kb, respond)
        assert not gathered.stored, f"{what}: the answer was stored"
        assert gathered.problems, f"{what}: no reason was given"
        assert kb.learned() == {} and not list(learned_dir(ReadScope(root)).glob("*.md")), \
            f"{what}: something was written"


def check_gather_never_stores_an_ungrounded_answer() -> None:
    _rejected(answering("Gateways share one route enumeration."), "no citation")
    _rejected(answering("It is in datrix-alpha/src/ghost.py:3 somewhere."), "citation of an unsent file")
    _rejected(lambda chat: f"See {_sent_location(chat.user).split(':')[0]}:999 for it.", "citation of an unsent line")
    _rejected(lambda chat: f"Per {_sent_location(chat.user)} it runs `def invented_function_nobody_wrote(x): return x`.",
              "quoted code that was not sent")
    _rejected(answering("NOTHING RELEVANT"), "a model that found nothing")


def check_gather_reports_a_missing_model_server() -> None:
    with _workspace() as root, TemporaryDirectory(prefix="ineedtoknow-db-") as db_dir:
        kb = KnowledgeBase(Path(db_dir) / "kb.db")
        scope = ReadScope(root)
        sync_curated(kb, scope)
        try:
            gather(kb, scope, _pool(closed_port(), Path(db_dir) / "usage.jsonl"), QUESTION, [])
        except LocalLlmUnavailable:
            return
        raise AssertionError("gather must raise LocalLlmUnavailable when no model server answers")


def check_cli_help_runs_and_names_its_actions() -> None:
    result = subprocess.run([sys.executable, str(_CLI), "--help"], capture_output=True, text=True, timeout=60,
                            check=False, env=script_env())
    assert result.returncode == 0, result.stderr
    for flag in ("--status", "--rebuild", "--prune", "--refresh", "--no-learn", "--in"):
        assert flag in result.stdout, f"{flag} missing from --help"


# ===========================================================================
# harness
# ===========================================================================


def _deliberately_failing_check() -> None:
    assert False, "deliberately failing check for --harness-self-test"


def harness_self_test() -> bool:
    print("=== Harness self-test: a deliberately-failing check must be reported FAILED ===")
    if run_checks([_deliberately_failing_check]):
        _fail("harness self-test: the deliberately-failing check was NOT reported as failed")
        return False
    _ok("harness self-test: the deliberately-failing check was correctly reported FAILED")
    return True


_ALL_CHECKS: list[CheckFunc] = [
    check_chunks_keep_the_documents_own_line_numbers,
    check_long_sections_split_into_bounded_chunks_that_keep_every_line,
    check_sync_adds_updates_and_removes_docs_and_never_reads_a_customer_repo,
    check_lookup_answers_covered_questions_only,
    check_a_section_titled_for_the_subject_outranks_a_mention,
    check_learned_file_round_trips_and_rejects_tampering,
    check_a_second_machine_converges_from_the_text_files,
    check_an_answer_expires_when_a_cited_file_changes,
    check_gather_reads_real_line_numbers_and_stores_a_grounded_answer,
    check_gather_never_stores_an_ungrounded_answer,
    check_gather_reports_a_missing_model_server,
    check_cli_help_runs_and_names_its_actions,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for ineedtoknow.")
    parser.add_argument("--harness-self-test", action="store_true",
                        help="Run only the harness self-test (a deliberately-failing dummy check).")
    parser.add_argument("--only", metavar="PREFIX", help="Run only the checks whose name starts with PREFIX.")
    args = parser.parse_args()
    if args.harness_self_test:
        return 0 if harness_self_test() else 1
    checks = _ALL_CHECKS
    if args.only:
        checks = [check for check in _ALL_CHECKS if check.__name__.startswith(args.only)]
        if not checks:
            print(f"Error: no check name starts with {args.only!r}. Checks: "
                  f"{', '.join(c.__name__ for c in _ALL_CHECKS)}.", file=sys.stderr)
            return 2
    print(f"Running {len(checks)} ineedtoknow checks...\n")
    passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} ineedtoknow checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
