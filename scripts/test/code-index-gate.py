#!/usr/bin/env python3
"""Repo-level gate for the code index (``scripts/library/code_index``) and its entry points.

The datrix showcase repo hosts no pytest suite, so the index's behaviour is held here as
plain checks, in the shape of ``shared-library-gate.py``: each ``check_*`` builds a real
workspace of git repositories in a fresh temporary directory, runs the real index over
it, and raises ``AssertionError`` naming what differed. No mocks: model-server checks
talk to a real HTTP server on loopback, and the MCP checks drive the real server, both
in-process and as a subprocess speaking over its standard streams.

``--only PREFIX`` runs the checks whose name starts with PREFIX. ``--harness-self-test``
proves the harness reports a deliberately failing check as failed.

Exit codes: 0 = every check passed, 1 = at least one check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from code_index.extract import (  # noqa: E402
    REF_ATTR_CALL,
    REF_CALL,
    SYMBOL_ATTRIBUTE,
    SYMBOL_CLASS,
    SYMBOL_FUNCTION,
    SYMBOL_METHOD,
    SYMBOL_VARIABLE,
    extract_file,
)
from code_index.queries import (  # noqa: E402
    REF_IMPORT,
    find_canonical,
    find_references,
    find_symbol,
    outline,
    search,
    topic_matches,
)
from code_index.session import IndexSession  # noqa: E402
from code_index.sources import LOGIC_MAP_DB, CodeIndexConfig, index_dir, module_name  # noqa: E402
from code_index.store import open_index  # noqa: E402
from code_index.summaries import MIN_SUMMARY_LINES, summarize  # noqa: E402
from code_index.usage import usage_report  # noqa: E402
from dev.code_index_mcp import TOOLS, CodeIndexServer, serve  # noqa: E402
from dev.code_scan import (  # noqa: E402
    VERDICT_DEAD,
    VERDICT_REFUTED,
    VERDICT_TEST_ONLY,
    VERDICT_TEST_SUPPORT,
    VERDICT_UNMATCHED,
    CodeScanError,
    _string_names,
    fingerprint,
    index_verdict,
    named_in_strings,
    select_packages,
    write_state,
)
from dev.generate_test_rules import Proposal, drop_unknown_see_refs, seed_topics_from_index  # noqa: E402
from dev.logic_map import parse_markers  # noqa: E402
from metrics.dead_code_report import Finding  # noqa: E402
from shared.local_llm import LocalLlmPool, LocalLlmSettings  # noqa: E402
from code_index.background import (  # noqa: E402
    LOCK_STALE_SECONDS,
    SummarizeBusy,
    start_background_summaries,
    summarize_lock,
)
from shared.capped_log import rotated_path  # noqa: E402
from shared.local_llm_usage import USAGE_LOG_VARIABLE  # noqa: E402

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"

_LOOPBACK = "127.0.0.1"
_GIT_IDENTITY = ("-c", "user.name=code-index-gate", "-c", "user.email=gate@example.invalid",
                 "-c", "commit.gpgsign=false")
_MCP_SCRIPT = _LIBRARY_DIR / "dev" / "code_index_mcp.py"
_USAGE_HOOK = _SCRIPT_DIR.parent.parent / "claude-config" / ".claude" / "hooks" / "record-search-usage.py"
_REGISTRATION_MODULE = "_mcp_registration.py"
_HOOK_LOG_MODULE = "_hook_log.py"
_PROJECT_DIR_VARIABLE = "CLAUDE_PROJECT_DIR"

_CONFIG = CodeIndexConfig(exclude=("alpha/generated/*",), module_roots=("*/src",), summarize=("*/src/*",))

_TEXT_PY = '''"""Text helpers for the fixture."""

# @canonical(text/to-words): Split an identifier into words
# @rule: Callers pass raw identifiers, never
# pre-split text.
# @anti-pattern: Splitting on spaces
# @see: text/other
def to_words(value: str) -> list[str]:
    """Split an identifier into lowercase words.

    Second paragraph is not part of the summary line.
    """
    return value.split("_")


class Splitter:
    """Splits identifiers using the canonical helper."""

    limit: int = 3

    def split(self, value: str) -> list[str]:
        return to_words(value)


if True:
    def guarded() -> int:
        return 1

WORD_LIMIT = 40
'''

_FIXTURE_FILES = {
    "src/alpha_pkg/__init__.py": "from alpha_pkg.text import to_words\n",
    "src/alpha_pkg/text.py": _TEXT_PY,
    "src/alpha_pkg/use_alias.py": (
        "from alpha_pkg.text import to_words as words\n\n\n"
        "def run() -> list[str]:\n"
        "    # to_words in a comment is not a use\n"
        "    label = \"to_words\"\n"
        "    return words(label)\n"
    ),
    "src/alpha_pkg/use_reexport.py": "from alpha_pkg import to_words\n\nVALUE = to_words(\"x_y\")\n",
    "src/alpha_pkg/use_module.py": (
        "from alpha_pkg import text\n\n\n"
        "def go(splitter: object) -> list[str]:\n"
        "    splitter.split(\"z\")\n"
        "    return text.to_words(\"q\")\n"
    ),
    "src/alpha_pkg/sub/__init__.py": "",
    "src/alpha_pkg/sub/rel.py": "from ..text import to_words\n\nPARTS = to_words(\"r_s\")\n",
    "src/alpha_pkg/broken.py": "def broken(:\n    pass\n\n# @pattern(fixture/broken-file): Still extracted\n",
    "tests/test_text.py": (
        "from alpha_pkg.text import Splitter\n\n\n"
        "# @test-rule(text/splitting): Splitting yields words\n"
        "# @dim: language=fixture\n"
        "def test_split() -> None:\n"
        "    assert Splitter().split(\"a_b\") == [\"a\", \"b\"]\n"
    ),
    "generated/out.py": "def generated_output() -> None:\n    return None\n",
    "ignored_dir/skip.py": "def ignored_function() -> None:\n    return None\n",
}


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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *_GIT_IDENTITY, "-C", str(repo), *args], check=True, capture_output=True)


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@contextmanager
def _workspace(extra: dict[str, str] | None = None) -> Iterator[IndexSession]:
    """A workspace holding git repository ``alpha`` and a plain directory, with its index open."""
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        repo = workspace / "alpha"
        repo.mkdir()
        _git(repo, "init", "-q")
        _write(repo, {**_FIXTURE_FILES, **(extra or {}), ".gitignore": "ignored_dir/\n"})
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "fixture")
        _write(workspace, {"not_a_repo/loose.py": "def loose_function() -> None:\n    return None\n"})
        session = IndexSession(open_index(index_dir(workspace)), workspace, _CONFIG)
        try:
            yield session
        finally:
            session.close()


def _names(session: IndexSession, name: str) -> list[str]:
    return [hit.dotted for hit in find_symbol(session.conn, name).hits]


def _site_map(session: IndexSession, target: str) -> dict[str, set[tuple[int, str]]]:
    result = find_references(session.conn, target)
    return {path: {(s.line, s.kind) for s in sites} for path, sites in result.sites.items()}


# ===========================================================================
# extraction
# ===========================================================================


def check_extract_records_symbols_imports_and_references() -> None:
    facts = extract_file(_TEXT_PY.encode("utf-8"), "alpha/src/alpha_pkg/text.py", "alpha_pkg.text", False)
    kinds = {s.qualname: s.kind for s in facts.symbols}
    expected = {
        "to_words": SYMBOL_FUNCTION, "Splitter": SYMBOL_CLASS, "Splitter.limit": SYMBOL_ATTRIBUTE,
        "Splitter.split": SYMBOL_METHOD, "guarded": SYMBOL_FUNCTION, "WORD_LIMIT": SYMBOL_VARIABLE,
    }
    assert kinds == expected, f"symbols {kinds} != {expected}"
    to_words = next(s for s in facts.symbols if s.name == "to_words")
    assert to_words.signature == "def to_words(value: str) -> list[str]", to_words.signature
    assert to_words.doc == "Split an identifier into lowercase words.", to_words.doc
    assert (to_words.line, to_words.end_line) == (8, 13), (to_words.line, to_words.end_line)
    assert facts.module_doc == "Text helpers for the fixture.", facts.module_doc
    refs = {(r.name, r.kind) for r in facts.refs}
    assert ("to_words", REF_CALL) in refs and ("split", REF_ATTR_CALL) in refs, refs
    assert not any(name in {"str", "self", "list"} for name, _ in refs), f"builtins/self recorded: {refs}"
    assert [m.topic for m in facts.markers] == ["text/to-words"], facts.markers

    relative = extract_file(b"from ..text import to_words as w\nimport os.path\n",
                            "alpha/src/alpha_pkg/sub/rel.py", "alpha_pkg.sub.rel", False)
    imports = {(i.module, i.name, i.alias, i.bound_name) for i in relative.imports}
    assert imports == {("alpha_pkg.text", "to_words", "w", "w"), ("os.path", "", "", "os")}, imports
    package = extract_file(b"from . import text\n", "alpha/src/alpha_pkg/__init__.py", "alpha_pkg", True)
    assert [(i.module, i.name) for i in package.imports] == [("alpha_pkg", "text")], package.imports


def check_extract_keeps_markers_of_a_file_with_a_syntax_error() -> None:
    facts = extract_file(_FIXTURE_FILES["src/alpha_pkg/broken.py"].encode("utf-8"), "alpha/src/alpha_pkg/broken.py",
                         "alpha_pkg.broken", False)
    assert facts.parse_error.startswith("SyntaxError"), facts.parse_error
    assert not facts.symbols and not facts.refs, "a file that does not parse must record no definitions"
    assert [m.topic for m in facts.markers] == ["fixture/broken-file"], facts.markers


def check_wrapped_rule_lines_belong_to_the_rule() -> None:
    markers = parse_markers(_TEXT_PY.splitlines(), "text.py")
    marker = markers[0]
    assert marker.rules == ["Callers pass raw identifiers, never pre-split text."], marker.rules
    assert marker.anti_patterns == ["Splitting on spaces"], marker.anti_patterns
    assert marker.see_refs == ["text/other"], marker.see_refs
    assert marker.description == "", f"rule continuation leaked into the description: {marker.description!r}"
    described = parse_markers(["# @pattern(a/b): Summary", "# A description line.", "# @rule: R1"], "x.py")[0]
    assert described.description == "A description line." and described.rules == ["R1"], described


def check_marker_shaped_lines_inside_strings_are_not_markers() -> None:
    source = (
        '"""Module docstring.\n\n    # @canonical(doc/example): Shown as syntax, not declared\n"""\n'
        f"FIXTURE = '''{_TEXT_PY}'''\n"
        'TEMPLATE = f"""\n# @pattern(fstring/example): {FIXTURE}\n"""\n'
        "# @invariant(real/marker): Declared in a comment\n"
        "X = 1\n"
    )
    topics = [m.topic for m in parse_markers(source.splitlines(), "strings.py")]
    assert topics == ["real/marker"], f"a marker-shaped line inside a string literal was extracted: {topics}"


def check_generate_test_rules_drops_see_refs_to_unknown_topics() -> None:
    def proposal(topic: str, see: list[str]) -> Proposal:
        return Proposal(file="tests/test_x.py", qualname=topic, name=topic, def_line=1, col=0,
                        applicable=True, topic=topic, see=see)

    first = proposal("text/splitting", ["text/to-words", "text/invented", "text/joining"])
    second = proposal("text/joining", ["text/splitting"])
    dropped = drop_unknown_see_refs([first, second], frozenset({"text/to-words"}))
    assert dropped == 1, dropped
    assert first.see == ["text/to-words", "text/joining"], first.see
    assert second.see == ["text/splitting"], second.see


def check_module_names_follow_the_configured_roots() -> None:
    cases = {
        "alpha/src/alpha_pkg/text.py": "alpha_pkg.text",
        "alpha/src/alpha_pkg/__init__.py": "alpha_pkg",
        "alpha/tests/unit/test_x.py": "tests.unit.test_x",
        "alpha/setup.py": "setup",
    }
    for rel_path, expected in cases.items():
        actual = module_name(rel_path, _CONFIG)
        assert actual == expected, f"{rel_path}: {actual} != {expected}"


# ===========================================================================
# refresh
# ===========================================================================


def check_refresh_indexes_only_what_git_sees_minus_excludes() -> None:
    with _workspace() as session:
        report = session.refresh()
        paths = {str(r[0]) for r in session.conn.execute("SELECT path FROM files")}
        expected = {f"alpha/{p}" for p in _FIXTURE_FILES if not p.startswith(("generated/", "ignored_dir/"))}
        assert paths == expected, f"indexed {sorted(paths ^ expected)} differently from git's view"
        assert report.total == len(expected) and report.parsed == len(expected), report
        assert report.parse_errors == 1, report
        (session.workspace / "alpha/src/alpha_pkg/fresh.py").write_text("def fresh() -> None:\n    return None\n",
                                                                          encoding="utf-8")
        assert session.refresh().parsed == 1, "an untracked, unignored file must be indexed"
        assert _names(session, "fresh") == ["alpha_pkg.fresh.fresh"], _names(session, "fresh")


def check_refresh_parses_only_changed_content() -> None:
    with _workspace() as session:
        session.refresh()
        text_py = session.workspace / "alpha/src/alpha_pkg/text.py"
        stat = text_py.stat()
        os.utime(text_py, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        touched = session.refresh()
        assert touched.parsed == 0 and not touched.markers_rewritten, f"an unchanged file was re-parsed: {touched}"
        text_py.write_text(_TEXT_PY.replace("WORD_LIMIT = 40", "WORD_LIMIT = 40\nNEW_LIMIT = 2"), encoding="utf-8")
        changed = session.refresh()
        assert changed.parsed == 1, changed
        assert _names(session, "NEW_LIMIT") == ["alpha_pkg.text.NEW_LIMIT"], _names(session, "NEW_LIMIT")
        (session.workspace / "alpha/src/alpha_pkg/use_reexport.py").unlink()
        removed = session.refresh()
        assert removed.removed == 1 and removed.parsed == 0, removed
        assert _names(session, "VALUE") == [], "a deleted file's definitions must leave the index"


def check_logic_map_rewritten_only_when_markers_change() -> None:
    with _workspace() as session:
        first = session.refresh()
        db = session.workspace / LOGIC_MAP_DB
        assert first.markers_rewritten and db.exists(), "the first refresh must write markers.db"
        # closing(): a connection's own context manager commits but leaves the file open.
        with closing(sqlite3.connect(db)) as conn:
            topics = {str(r[0]) for r in conn.execute("SELECT topic FROM markers")}
            rules = [str(r[0]) for r in conn.execute("SELECT text FROM rules")]
        assert topics == {"text/to-words", "fixture/broken-file", "text/splitting"}, topics
        assert rules == ["Callers pass raw identifiers, never pre-split text."], rules
        use_alias = session.workspace / "alpha/src/alpha_pkg/use_alias.py"
        use_alias.write_text(use_alias.read_text(encoding="utf-8") + "\nEXTRA = 1\n", encoding="utf-8")
        unmarked = session.refresh()
        assert unmarked.parsed == 1 and not unmarked.markers_rewritten, unmarked
        use_alias.write_text(use_alias.read_text(encoding="utf-8") + "# @invariant(fixture/new): Added\nX = 2\n",
                             encoding="utf-8")
        assert session.refresh().markers_rewritten, "a new marker must rewrite markers.db"
        with closing(sqlite3.connect(db)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM markers WHERE topic = 'fixture/new'").fetchone()[0] == 1


# ===========================================================================
# queries
# ===========================================================================


def check_references_resolve_aliases_reexports_and_module_imports() -> None:
    with _workspace() as session:
        session.refresh()
        sites = _site_map(session, "to_words")
        expected = {
            "alpha/src/alpha_pkg/__init__.py": {(1, REF_IMPORT)},
            "alpha/src/alpha_pkg/text.py": {(22, REF_CALL)},
            "alpha/src/alpha_pkg/use_alias.py": {(1, REF_IMPORT), (7, REF_CALL)},
            "alpha/src/alpha_pkg/use_reexport.py": {(1, REF_IMPORT), (3, REF_CALL)},
            "alpha/src/alpha_pkg/use_module.py": {(6, REF_ATTR_CALL)},
            "alpha/src/alpha_pkg/sub/rel.py": {(1, REF_IMPORT), (3, REF_CALL)},
        }
        assert sites == expected, f"references differ:\n  got      {sites}\n  expected {expected}"
        dotted = _site_map(session, "alpha_pkg.text.to_words")
        assert dotted == sites, "a dotted target must resolve to the same uses as its unique bare name"


def check_references_to_a_method_say_receivers_are_unchecked() -> None:
    with _workspace() as session:
        session.refresh()
        result = find_references(session.conn, "Splitter.split")
        assert "receiver types are not checked" in result.resolution, result.resolution
        found = {(path, s.line) for path, sites in result.sites.items() for s in sites}
        # text.py:13 is ``value.split("_")`` on a str: exactly the unchecked-receiver case the answer states.
        expected = {("alpha/src/alpha_pkg/text.py", 13), ("alpha/src/alpha_pkg/use_module.py", 5),
                    ("alpha/tests/test_text.py", 7)}
        assert found == expected, found
        assert list(result.sites)[-1] == "alpha/tests/test_text.py", "production code must be listed before tests"


def check_symbol_lookup_forms_and_suggestions() -> None:
    with _workspace() as session:
        session.refresh()
        assert _names(session, "Splitter.split") == ["alpha_pkg.text.Splitter.split"]
        assert _names(session, "alpha_pkg.text.Splitter") == ["alpha_pkg.text.Splitter"]
        assert _names(session, "*Words") == [] and _names(session, "to_*") == ["alpha_pkg.text.to_words"]
        assert "loose_function" not in {str(r[0]) for r in session.conn.execute("SELECT name FROM symbols")}, \
            "a directory that is not a git repository must not be indexed"
        missing = find_symbol(session.conn, "Splitte")
        assert not missing.hits and "Splitter" in missing.suggestions, missing
        text = outline(session.conn, "alpha_pkg/text.py").render()
        for fragment in ("[alpha_pkg.text]", "L8-13 def to_words(value: str) -> list[str]", "  L19 limit: int = 3"):
            assert fragment in text, f"outline lacks {fragment!r}:\n{text}"


def check_search_matches_identifier_words_and_docstrings() -> None:
    with _workspace() as session:
        session.refresh()
        by_words = [h.ref for h in search(session.conn, "words split").hits]
        assert "to_words" in by_words, f"identifier words not searchable: {by_words}"
        by_doc = [h.ref for h in search(session.conn, "canonical helper").hits]
        assert "Splitter" in by_doc, f"docstring words not searchable: {by_doc}"


def check_canonical_matches_topic_segments_and_hides_test_rules() -> None:
    assert topic_matches("text/to-words", "words") and topic_matches("text/to-words", "text/to")
    assert not topic_matches("python/api-test-cases", "case"), "a partial segment must not match"
    with _workspace() as session:
        session.refresh()
        hits = find_canonical(session.conn, "words").hits
        assert [h.topic for h in hits] == ["text/to-words"], hits
        assert hits[0].rules == ["Callers pass raw identifiers, never pre-split text."], hits[0].rules
        default_kinds = {h.kind for h in find_canonical(session.conn, "splitting").hits}
        assert "test-rule" not in default_kinds, f"test-rule markers are opt-in: {default_kinds}"
        with_rules = [h.topic for h in find_canonical(session.conn, "splitting", include_test_rules=True).hits]
        assert with_rules[:1] == ["text/splitting"], f"a topic match must come before text matches: {with_rules}"


def check_generate_test_rules_seeds_topics_from_the_index() -> None:
    with _workspace() as session:
        seed = seed_topics_from_index(session.workspace)
        assert seed.test_rules == {"text/splitting"}, seed.test_rules
        assert seed.every == {"text/splitting", "text/to-words", "fixture/broken-file"}, seed.every


# ===========================================================================
# summaries (a real model server on loopback)
# ===========================================================================


def _closed_port() -> int:
    """A loopback port nothing listens on: bound, read, released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


class _ModelServer:
    """An OpenAI-compatible server on an ephemeral loopback port that answers every chat with ``answer``."""

    def __init__(self, model: str, answer: str) -> None:
        self.prompts: list[str] = []
        prompts = self.prompts

        class _Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._send({"data": [{"id": model}]})

            def do_POST(self) -> None:  # noqa: N802 -- http.server's dispatch name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if body.get("max_tokens") != 1:
                    prompts.append(str(body["messages"][-1]["content"]))
                self._send({"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._httpd = ThreadingHTTPServer((_LOOPBACK, 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> _ModelServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def check_summaries_are_stored_by_content_hash_and_searchable() -> None:
    big = "\n".join(['"""A long module about quasar calibration."""'] +
                    [f"CONSTANT_{n} = {n}" for n in range(MIN_SUMMARY_LINES + 5)]) + "\n"
    with _workspace({"src/alpha_pkg/big.py": big}) as session, \
            _ModelServer("gate-model", "Calibrates nebula telescopes for the fixture.") as server:
        session.refresh()
        settings = LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                    ollama_port=_closed_port(), openai_ports=(server.port,))
        run = summarize(session.conn, session.workspace, session.config, LocalLlmPool(settings, report=lambda _: None),
                        workers=2, report=lambda _: None)
        assert run.summarized == 1 and run.pending_after == 0, run
        assert len(server.prompts) == 1 and "Module: alpha_pkg.big" in server.prompts[0], server.prompts
        assert "Calibrates nebula" in outline(session.conn, "alpha_pkg.big").summary
        assert [h.ref for h in search(session.conn, "nebula telescopes").hits] == ["alpha_pkg.big"]
        again = summarize(session.conn, session.workspace, session.config,
                          LocalLlmPool(settings, report=lambda _: None), workers=2, report=lambda _: None)
        assert again.summarized == 0 and len(server.prompts) == 1, "an unchanged module must not be sent again"


_BIG_MODULE = "\n".join(['"""A long module about quasar calibration."""'] +
                        [f"CONSTANT_{n} = {n}" for n in range(MIN_SUMMARY_LINES + 5)]) + "\n"


class _RecordingLauncher:
    """Collects the commands a background summarize run would be started with, instead of starting one."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.logs: list[Path] = []

    def __call__(self, command: list[str], log: Path) -> None:
        self.commands.append(command)
        self.logs.append(log)


def check_summarize_lock_is_exclusive_and_breaks_when_stale() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        with summarize_lock(workspace):
            try:
                with summarize_lock(workspace):
                    raise AssertionError("a second summarize run took the lock while the first held it")
            except SummarizeBusy as exc:
                assert "already holds" in str(exc), exc
        lock = index_dir(workspace) / "summarize.lock"
        assert not lock.exists(), "the lock must be released when the run ends"
        # Too old, though its owner (this process) is alive and nothing refreshed it.
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        stale = time.time() - LOCK_STALE_SECONDS - 60
        os.utime(lock, (stale, stale))
        with summarize_lock(workspace):
            assert lock.read_text(encoding="utf-8").strip() == str(os.getpid()), "a stale lock must be taken over"
        # A live owner that keeps refreshing the lock holds it however long the run takes.
        with summarize_lock(workspace) as keep_fresh:
            os.utime(lock, (stale, stale))
            keep_fresh()
            assert time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS, "touch must refresh the lock"
            try:
                with summarize_lock(workspace):
                    raise AssertionError("a refreshed lock of a live run must hold")
            except SummarizeBusy:
                pass


def check_summarize_lock_of_a_dead_process_is_taken_over_at_once() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        lock = index_dir(workspace) / "summarize.lock"
        lock.parent.mkdir(parents=True)
        exited = subprocess.Popen([sys.executable, "-c", "pass"])
        exited.wait()
        lock.write_text(f"{exited.pid}\n", encoding="utf-8")  # just written: fresh by age
        assert time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS, "fixture: the lock must look fresh by age"
        with summarize_lock(workspace):
            assert lock.read_text(encoding="utf-8").strip() == str(os.getpid()), (
                "a lock whose process is gone (a killed run never releases it) must be taken over at once")
        # Non-vacuity: the same lock held by a live process is respected.
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        try:
            with summarize_lock(workspace):
                raise AssertionError("a lock held by a live process must be respected")
        except SummarizeBusy:
            pass


def check_background_summaries_start_only_when_pending_and_unlocked() -> None:
    with _workspace({"src/alpha_pkg/big.py": _BIG_MODULE}) as session:
        session.refresh()
        launcher = _RecordingLauncher()
        with summarize_lock(session.workspace):
            assert not start_background_summaries(session, launcher), "no second run while one holds the lock"
        assert start_background_summaries(session, launcher), "a pending module with no run going must start one"
        command = launcher.commands[0]
        assert command[0] == sys.executable and command[1].endswith("code_index_cli.py"), command
        assert command[2:] == ["summarize", "--limit", "0"], command
        assert launcher.logs[0] == index_dir(session.workspace) / "summarize.log", launcher.logs
    with _workspace() as session:
        session.refresh()
        assert not start_background_summaries(session, _RecordingLauncher()), "nothing pending: nothing to start"


def check_mcp_server_starts_summaries_when_its_refresh_changes_files() -> None:
    with _workspace({"src/alpha_pkg/big.py": _BIG_MODULE}) as session:
        launcher = _RecordingLauncher()
        factory = lambda: IndexSession(open_index(index_dir(session.workspace)), session.workspace, _CONFIG)  # noqa: E731
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "find_symbol", "arguments": {"name": "to_words"}}}
        server = CodeIndexServer(session_factory=factory, summary_launcher=launcher)
        assert server.handle(call) is not None and len(launcher.commands) == 1, "the first call finds the pending module"
        server.handle(call)
        assert len(launcher.commands) == 1, "a call whose refresh changed nothing starts no run"
        _write(session.workspace / "alpha", {"src/alpha_pkg/big.py": _BIG_MODULE + "EXTRA = 1\n"})
        server.handle(call)
        assert len(launcher.commands) == 2, "an edit seen by the refresh starts a run for the changed module"
        server.close()


# ===========================================================================
# MCP server
# ===========================================================================


def _mcp_exchange(server: CodeIndexServer, messages: list[object]) -> list[dict[str, object]]:
    stdin = io.BytesIO(b"".join(
        (m if isinstance(m, bytes) else json.dumps(m).encode("utf-8")) + b"\n" for m in messages))
    stdout = io.BytesIO()
    serve(server, stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def check_mcp_server_answers_the_protocol_and_tools() -> None:
    with _workspace() as session:
        server = CodeIndexServer(session_factory=lambda: IndexSession(open_index(index_dir(session.workspace)),
                                                                      session.workspace, _CONFIG))
        responses = _mcp_exchange(server, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "find_symbol", "arguments": {"name": "to_words"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "find_symbol", "arguments": {"name": ""}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "no/such/method"},
            b"{not json",
        ])
        by_id = {r.get("id"): r for r in responses}
        assert len(responses) == 7, f"a notification must get no response: {responses}"
        init = by_id[1]["result"]
        assert init["protocolVersion"] == "2025-03-26" and init["serverInfo"]["name"] == "datrix-code-index", init
        names = [t["name"] for t in by_id[2]["result"]["tools"]]
        assert names == [t.name for t in TOOLS], names
        found = by_id[3]["result"]
        assert not found["isError"] and "alpha_pkg.text.to_words" in found["content"][0]["text"], found
        assert by_id[4]["result"]["isError"] and "non-empty string" in by_id[4]["result"]["content"][0]["text"]
        assert by_id[5]["error"]["code"] == -32602 and by_id[6]["error"]["code"] == -32601
        assert by_id[None]["error"]["code"] == -32700, by_id[None]


def check_mcp_server_stdout_carries_only_protocol() -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ]
    stdin = "".join(json.dumps(r) + "\n" for r in requests).encode("utf-8")
    result = subprocess.run([sys.executable, str(_MCP_SCRIPT)], input=stdin, capture_output=True, timeout=60,
                            check=False)
    assert result.returncode == 0, f"server exited {result.returncode}: {result.stderr.decode(errors='replace')}"
    lines = result.stdout.decode("utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [p["id"] for p in parsed] == [1, 2, 3], f"stdout must hold exactly the three responses: {lines}"
    assert parsed[0]["result"]["protocolVersion"] == "2025-06-18", parsed[0]


# ===========================================================================
# code scan (dev/code_scan.py): what it adds on top of the scanners
# ===========================================================================

_SCAN_EXTRA = {
    "pyproject.toml": "[project]\nname = \"alpha\"\n",
    "src/alpha_pkg/extra.py": (
        "def lonely() -> None:\n    return None\n\n\n"
        "def tested() -> int:\n    return 1\n\n\n"
        "def by_string() -> int:\n    return 2\n"
    ),
    "src/alpha_pkg/lookup.py": "import alpha_pkg.extra as extra\n\nFN = getattr(extra, \"by_string\")\n",
    "src/alpha_pkg/testkit/helpers.py": (
        "def support() -> int:\n    return 3\n\n\n"
        "@staticmethod\n@staticmethod\ndef decorated() -> int:\n    return 4\n"
    ),
    "tests/test_extra.py": (
        "from alpha_pkg.extra import tested\nfrom alpha_pkg.testkit.helpers import support\n\n\n"
        "def test_it() -> None:\n    assert tested() + support() == 4\n"
    ),
}


def _finding(session: IndexSession, rel: str, line: int, symbol: str, kind: str) -> Finding:
    return Finding(str(session.workspace / rel), line, f"unused {kind} '{symbol}'", 60, symbol, kind)


def check_code_scan_index_verdicts() -> None:
    with _workspace(_SCAN_EXTRA) as session:
        session.refresh()
        verdicts = {
            symbol: index_verdict(session.conn, session.workspace, _finding(session, rel, line, symbol, kind))
            for rel, line, symbol, kind in (
                ("alpha/src/alpha_pkg/extra.py", 1, "lonely", "function"),
                ("alpha/src/alpha_pkg/extra.py", 5, "tested", "function"),
                ("alpha/src/alpha_pkg/text.py", 8, "to_words", "function"),
                ("alpha/src/alpha_pkg/extra.py", 3, "nowhere", "function"),
                ("alpha/src/alpha_pkg/testkit/helpers.py", 1, "support", "function"),
                # Vulture reports a decorated definition at its first decorator (line 5); the def is line 7.
                ("alpha/src/alpha_pkg/testkit/helpers.py", 5, "decorated", "function"),
            )
        }
        assert verdicts == {"lonely": VERDICT_DEAD, "tested": VERDICT_TEST_ONLY, "to_words": VERDICT_REFUTED,
                            "nowhere": VERDICT_UNMATCHED, "support": VERDICT_TEST_SUPPORT,
                            "decorated": VERDICT_DEAD}, verdicts


def check_code_scan_sees_names_used_through_strings() -> None:
    source = (
        '"""Module prose mentions lonely_word, which is not a use."""\n'
        'A = getattr(obj, "by_attr")\n'
        'B = {"resolver_ref": "pkg.module.by_path"}\n'
        'C = "{{ ctx.by_template }} and more"\n'
        'def gen() -> None:\n'
        '    """\n'
        '    generator g : g {\n'
        '      domain d {\n'
        '        each item where call ns.mod.by_gendsl_call(item) {\n'
        '          context Ctx from ns.mod.by_gendsl_context;\n'
        '        }\n'
        '      }\n'
        '    }\n'
        '    """\n'
    )
    names = _string_names(source)
    assert {"by_attr", "by_path", "by_template", "resolver_ref", "by_gendsl_call",
            "by_gendsl_context"} <= names, names
    assert "lonely_word" not in names, f"docstring prose must not count as a use: {names}"
    with _workspace(_SCAN_EXTRA) as session:
        session.refresh()
        assert "by_string" in named_in_strings(session.conn, session.workspace)


def check_code_scan_selects_only_changed_packages() -> None:
    with _workspace(_SCAN_EXTRA) as session:
        session.refresh()
        # A src/ tree without a pyproject.toml (a TypeScript repo) is not a Python package.
        ts_repo = session.workspace / "typescript_client"
        (ts_repo / "src").mkdir(parents=True)
        _git(ts_repo, "init", "-q")
        assert select_packages(session.conn, session.workspace, [], False) == ["alpha"], \
            "with no scan state every scannable package is due"
        write_state(session.workspace, {"alpha": fingerprint(session.conn, "alpha")})
        assert select_packages(session.conn, session.workspace, [], False) == [], "an unchanged package is not due"
        extra = session.workspace / "alpha/src/alpha_pkg/extra.py"
        extra.write_text(extra.read_text(encoding="utf-8") + "\nNEW = 1\n", encoding="utf-8")
        session.refresh()
        assert select_packages(session.conn, session.workspace, [], False) == ["alpha"], "a changed package is due"
        assert select_packages(session.conn, session.workspace, ["alpha"], False) == ["alpha"]
        alpha = session.workspace / "alpha"
        folder_forms = [str(alpha), f"{alpha}\\", f"{alpha}/", str(alpha / "src" / "alpha_pkg")]
        for form in folder_forms:
            assert select_packages(session.conn, session.workspace, [form], False) == ["alpha"], form
        previous = Path.cwd()
        os.chdir(session.workspace)
        try:
            assert select_packages(session.conn, session.workspace, [".\\alpha\\"], False) == ["alpha"], \
                "a relative folder is read against the current directory"
        finally:
            os.chdir(previous)
        try:
            select_packages(session.conn, session.workspace, ["nope"], False)
        except CodeScanError as exc:
            assert "scannable packages: alpha" in str(exc), exc
        else:
            raise AssertionError("an unknown package must be refused")


# ===========================================================================
# usage log (the record-search-usage hook -> code_index.usage)
# ===========================================================================


@dataclass(frozen=True)
class _HookSandbox:
    workspace: Path
    hook: Path
    env: dict[str, str]


_CODE_INDEX_SERVER = "datrix-code-index"
_LOCAL_LLM_SERVER = "datrix-local-llm"


@contextmanager
def _hook_sandbox(registered_directory: str | None,
                  servers: tuple[str, ...] = (_CODE_INDEX_SERVER,)) -> Iterator[_HookSandbox]:
    """A copy of the usage hook in a temp workspace laid out like the real one, run under a temp
    user profile whose Claude Code config registers ``servers`` for ``registered_directory`` only
    (for no directory when None).

    The hook finds its workspace and the scripts library from its own real path, so the copy logs
    into the temp workspace and loads the copied library; the real workspace, the real user config
    and the ``datrix`` repository are never touched.
    """
    with TemporaryDirectory() as temp:
        workspace = Path(temp) / "workspace"
        hooks = workspace / "datrix" / "claude-config" / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for name in (_USAGE_HOOK.name, _REGISTRATION_MODULE, _HOOK_LOG_MODULE):
            shutil.copyfile(_USAGE_HOOK.parent / name, hooks / name)
        library = workspace / "datrix" / "scripts" / "library"
        for package in ("code_index", "shared"):
            shutil.copytree(_LIBRARY_DIR / package, library / package, ignore=shutil.ignore_patterns("__pycache__"))
        profile = Path(temp) / "profile"
        profile.mkdir()
        server = {"type": "stdio", "command": sys.executable, "args": [str(_MCP_SCRIPT)]}
        projects = {} if registered_directory is None else {registered_directory: {"mcpServers": {
            name: server for name in servers}}}
        (profile / ".claude.json").write_text(json.dumps({"projects": projects}), encoding="utf-8")
        # The gate may itself run inside a Claude Code session, whose project directory must not leak in.
        env = {key: value for key, value in os.environ.items() if key != _PROJECT_DIR_VARIABLE}
        env.update({"USERPROFILE": str(profile), "HOME": str(profile)})
        yield _HookSandbox(workspace, hooks / _USAGE_HOOK.name, env)


def _run_hook(sandbox: _HookSandbox, payload: object, project_dir: str = "") -> subprocess.CompletedProcess[bytes]:
    stdin = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    env = {**sandbox.env, _PROJECT_DIR_VARIABLE: project_dir} if project_dir else sandbox.env
    return subprocess.run([sys.executable, str(sandbox.hook)], input=stdin, capture_output=True, timeout=30,
                          check=False, env=env)


def check_usage_hook_log_is_what_the_report_reads() -> None:
    with _hook_sandbox(None) as sandbox:
        workspace = sandbox.workspace
        big_py = str(workspace / "alpha" / "src" / "big.py")
        payloads: list[object] = [
            {"tool_name": "mcp__datrix-code-index__find_symbol", "tool_input": {"name": "x"},
             "tool_response": "r" * 100, "session_id": "s1"},
            {"tool_name": "Grep", "tool_input": {"pattern": "\\bto_snake_case\\b"}, "tool_response": "g" * 4000,
             "session_id": "s1"},
            {"tool_name": "Grep", "tool_input": {"pattern": "tenant.*header"}, "tool_response": "g",
             "session_id": "s1"},
            {"tool_name": "Read", "tool_input": {"file_path": big_py}, "tool_response": "c" * 9000,
             "session_id": "s2"},
            {"tool_name": "Read", "tool_input": {"file_path": big_py, "offset": 10, "limit": 20},
             "tool_response": "c" * 9000, "session_id": "s2"},
            {"tool_name": "Read", "tool_input": {"file_path": str(workspace / "notes.md")}, "tool_response": "m",
             "session_id": "s2"},
            {"tool_name": "PowerShell", "tool_input": {"command": "rg -n foo D:/datrix"}, "tool_response": "s",
             "session_id": "s2"},
            {"tool_name": "PowerShell", "tool_input": {"command": "git status"}, "tool_response": "s",
             "session_id": "s2"},
            {"tool_name": "PowerShell", "tool_input": {"command": "& test.ps1 x | Select-String FAILED"},
             "tool_response": "s", "session_id": "s2"},
            {"tool_name": "PowerShell",
             "tool_input": {"command": "Get-ChildItem -Recurse -Filter *.py | Select-String -Pattern foo"},
             "tool_response": "s", "session_id": "s2"},
            b"not json",
        ]
        codes = [_run_hook(sandbox, payload).returncode for payload in payloads]
        assert codes == [0] * len(payloads), f"the hook must always exit 0: {codes}"
        report = usage_report(workspace, 0)
        calls = {name: tally.calls for name, tally in report.categories.items()}
        # The output filter (``| Select-String FAILED``) is not a code search; the file-listing pipe is.
        assert calls == {"index": 1, "grep": 2, "read": 2, "shell_search": 2}, calls
        assert report.identifier_greps.calls == 1 and report.large_full_reads.calls == 1, report
        assert report.top_full_reads == {"alpha/src/big.py": 1}, report.top_full_reads
        assert report.sessions == 2 and report.replaceable == 4, report
        assert "20% (1 of 5)" in report.render(), report.render()
        # After a rotation the report still counts what the rotated file holds.
        log = workspace / ".code-index" / "usage.jsonl"
        log.replace(rotated_path(log))
        assert _run_hook(sandbox, payloads[2]).returncode == 0
        rotated = usage_report(workspace, 0)
        assert rotated.categories["grep"].calls == 3 and log.read_text(encoding="utf-8").count("\n") == 1, (
            "the report must read the rotated log and the current one")


def _hook_hint(sandbox: _HookSandbox, payload: dict[str, object], project_dir: str = "") -> str:
    result = _run_hook(sandbox, payload, project_dir)
    assert result.returncode == 0, result.stderr
    out = result.stdout.decode("utf-8").strip()
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


def check_usage_hook_points_at_the_index_a_few_times_per_session() -> None:
    # Registered with forward slashes, asked from a backslash spelling: separators are normalised.
    with _hook_sandbox("D:/registered/workspace") as sandbox:
        cwd = "D:\\registered\\workspace"
        identifier = {"tool_name": "Grep", "tool_input": {"pattern": "\\bto_snake_case\\b"},
                      "tool_response": "g", "session_id": "s1", "cwd": cwd}
        hinted = [_hook_hint(sandbox, identifier) for _ in range(4)]
        assert all("find_references" in text and "select:mcp__datrix-code-index__" in text for text in hinted[:3]), \
            hinted
        assert hinted[3] == "", "a session gets three identifier hints, then silence"
        subagent = {**identifier, "agent_id": "a1"}
        assert "find_symbol" in _hook_hint(sandbox, subagent), \
            "a subagent has a fresh context: the main thread's spent hints must not silence it"
        for silent in (
            {"tool_name": "Grep", "tool_input": {"pattern": "tenant.*header"}, "session_id": "s1", "cwd": cwd},
            {"tool_name": "Grep", "tool_input": {"pattern": "to_snake_case", "glob": "*.j2"}, "session_id": "s1",
             "cwd": cwd},
            {"tool_name": "Read", "tool_input": {"file_path": "x.py", "offset": 1}, "tool_response": "c" * 9000,
             "session_id": "s1", "cwd": cwd},
        ):
            assert _hook_hint(sandbox, silent) == "", f"no hint for {silent['tool_input']}"
        large_read = {"tool_name": "Read", "tool_input": {"file_path": "big.py"}, "tool_response": "c" * 9000,
                      "session_id": "s1", "cwd": cwd}
        assert "select:mcp__datrix-code-index__outline" in _hook_hint(sandbox, large_read), \
            "a whole read of a large Python file points at outline"
        assert (sandbox.workspace / ".code-index" / "usage.jsonl").is_file(), "the log lands in the hook's workspace"
        # The agent changed directory: the payload's cwd moved, the session's project directory did not.
        moved = {"tool_name": "Grep", "tool_input": {"pattern": "\\bto_snake_case\\b"}, "tool_response": "g",
                 "session_id": "s3", "cwd": "D:\\registered\\workspace\\pkg\\src"}
        assert "select:mcp__datrix-code-index__" in _hook_hint(sandbox, moved, project_dir=cwd), \
            "registration is looked up for the directory the session started in, not the shell's current one"


def check_usage_hook_names_the_shell_where_the_session_has_no_index_tools() -> None:
    # Registered for one directory; the session runs in another, or reports none.
    with _hook_sandbox("D:/registered/workspace") as sandbox:
        for session, cwd in (("s1", "D:/elsewhere"), ("s2", "")):
            identifier = {"tool_name": "Grep", "tool_input": {"pattern": "\\bto_snake_case\\b"},
                          "tool_response": "g", "session_id": session, "cwd": cwd}
            text = _hook_hint(sandbox, identifier)
            assert "code-index.ps1\" -Symbol to_snake_case" in text and "-Setup" in text, text
            assert "ToolSearch" not in text, f"an unregistered session must not be sent to a ToolSearch: {text}"
            large_read = {"tool_name": "Read", "tool_input": {"file_path": "big.py"}, "tool_response": "c" * 9000,
                          "session_id": session, "cwd": cwd}
            text = _hook_hint(sandbox, large_read)
            assert "-Outline <path>" in text and "ToolSearch" not in text, text


def check_usage_hook_points_at_local_models_only_where_registered() -> None:
    cwd = "D:/registered/workspace"
    big_log = {"tool_name": "Read", "tool_input": {"file_path": "D:/registered/workspace/.test-output/run/full.txt"},
               "tool_response": "l" * 9000, "session_id": "s1", "cwd": cwd}
    big_py = {"tool_name": "Read", "tool_input": {"file_path": "big.py"}, "tool_response": "c" * 9000,
              "session_id": "s1", "cwd": cwd}
    with _hook_sandbox(cwd, servers=(_CODE_INDEX_SERVER, _LOCAL_LLM_SERVER)) as sandbox:
        log_hint = _hook_hint(sandbox, big_log)
        assert "select:mcp__datrix-local-llm__digest_log" in log_hint, log_hint
        assert _hook_hint(sandbox, {**big_log, "tool_input": {**big_log["tool_input"], "limit": 50}}) == "", \
            "a ranged log read is already cheap: no hint"
        assert _hook_hint(sandbox, {**big_log, "tool_response": "short"}) == "", "a small log read gets no hint"
        assert "mcp__datrix-local-llm__ask_files" in _hook_hint(sandbox, big_py), \
            "a whole read of a large Python file also points at ask_files when the session has it"
        assert not (sandbox.workspace / ".code-index" / "usage.jsonl").exists() or "full.txt" not in (
            sandbox.workspace / ".code-index" / "usage.jsonl").read_text(encoding="utf-8"), \
            "a log read is not a code search and must not enter the code-index usage log"
    with _hook_sandbox(cwd, servers=(_CODE_INDEX_SERVER,)) as sandbox:
        assert _hook_hint(sandbox, big_log) == "", "no local-model tools in the session: no digest_log hint"
        assert "ask_files" not in _hook_hint(sandbox, big_py), "no local-model tools: ask_files is not named"


def check_usage_report_counts_redirected_reads() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        log = workspace / ".code-index" / "usage.jsonl"
        log.parent.mkdir()
        notice = {"category": "read_redirect", "tool": "Read", "detail": "alpha/src/big.py", "response_chars": 8000,
                  "session": "s1", "agent": "a1", "ts": datetime.now(UTC).isoformat(timespec="seconds")}
        repeat = {**notice, "category": "read_redirect_repeat", "response_chars": 0}
        log.write_text("".join(json.dumps(e) + "\n" for e in (notice, notice, repeat)), encoding="utf-8")
        rendered = usage_report(workspace, 0).render()
        assert ("answered with an outline or digest instead: 2 (the notices cost ~4,000 tokens in all); "
                "the agent read the whole file anyway after 1 of them") in rendered, rendered


def check_usage_hook_never_writes_into_the_datrix_repository() -> None:
    stray = _USAGE_HOOK.parents[2] / ".code-index"
    assert not stray.exists(), (
        f"{stray} exists: the usage hook (or a check running it) logged inside the datrix repository. The hook "
        f"derives its workspace from its real path; delete the directory and find what ran the hook from a copy "
        f"outside the workspace layout.")


# ===========================================================================
# Harness self-test and main
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
    check_extract_records_symbols_imports_and_references,
    check_extract_keeps_markers_of_a_file_with_a_syntax_error,
    check_wrapped_rule_lines_belong_to_the_rule,
    check_marker_shaped_lines_inside_strings_are_not_markers,
    check_module_names_follow_the_configured_roots,
    check_refresh_indexes_only_what_git_sees_minus_excludes,
    check_refresh_parses_only_changed_content,
    check_logic_map_rewritten_only_when_markers_change,
    check_references_resolve_aliases_reexports_and_module_imports,
    check_references_to_a_method_say_receivers_are_unchecked,
    check_symbol_lookup_forms_and_suggestions,
    check_search_matches_identifier_words_and_docstrings,
    check_canonical_matches_topic_segments_and_hides_test_rules,
    check_generate_test_rules_seeds_topics_from_the_index,
    check_generate_test_rules_drops_see_refs_to_unknown_topics,
    check_summaries_are_stored_by_content_hash_and_searchable,
    check_summarize_lock_is_exclusive_and_breaks_when_stale,
    check_summarize_lock_of_a_dead_process_is_taken_over_at_once,
    check_background_summaries_start_only_when_pending_and_unlocked,
    check_mcp_server_starts_summaries_when_its_refresh_changes_files,
    check_mcp_server_answers_the_protocol_and_tools,
    check_mcp_server_stdout_carries_only_protocol,
    check_usage_hook_log_is_what_the_report_reads,
    check_usage_hook_points_at_the_index_a_few_times_per_session,
    check_usage_hook_names_the_shell_where_the_session_has_no_index_tools,
    check_usage_hook_points_at_local_models_only_where_registered,
    check_usage_report_counts_redirected_reads,
    check_usage_hook_never_writes_into_the_datrix_repository,
    check_code_scan_index_verdicts,
    check_code_scan_sees_names_used_through_strings,
    check_code_scan_selects_only_changed_packages,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for the code index and its entry points.")
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
    print(f"Running {len(checks)} code-index behaviour checks...\n")
    # The checks' own loopback model servers must never count as real use of the machines.
    with TemporaryDirectory(prefix="code-index-gate-") as temp:
        os.environ[USAGE_LOG_VARIABLE] = str(Path(temp) / "usage.jsonl")
        passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} code-index behaviour checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
