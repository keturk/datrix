#!/usr/bin/env python3
"""Repo-level gate for task orientation and citation validation (library/tasks).

Checks, over real temporary workspaces (framework repositories with real Python, task files under
``.tasks/phase-NN``, the real code index) and, for explanations, a real model server on loopback:

* the ``## Orientation`` block: parsed by the one task parser, every malformed entry rejected with
  what to write instead, and a question that asks where something is defined or who calls it rejected
  (a local model invents those answers);
* the resolver: facts exact from the code index, a stale entry reported as such, an explanation marked
  as a lead, no model server leaving the facts intact;
* the citation checker: a missing file or an out-of-range line is an error; an abbreviated path, a
  path or file name that several repositories carry, and a file another task of the phase creates are
  NOT; a name written beside a citation that is nowhere near its lines is a warning; names elsewhere in
  the sentence, language names and code fences are ignored;
* the validator end to end, and its exit codes.

Run through test/task-orientation-gate.ps1.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from code_index.session import open_session  # noqa: E402
from shared.local_llm import LocalLlmPool, LocalLlmSettings  # noqa: E402
from shared.local_llm_usage import USAGE_LOG_VARIABLE  # noqa: E402
from shared.local_reading import ReadScope, ask_files  # noqa: E402
from tasks.task_citations import (  # noqa: E402
    LEVEL_ERROR,
    LEVEL_WARN,
    CitationContext,
    RepoFiles,
    check_citations,
)
from tasks.retrofit_orientation import (  # noqa: E402
    OUTCOME_CONVERTED,
    OUTCOME_SKIPPED,
    RetrofitResult,
    convert,
)
from tasks.retrofit_orientation import apply as apply_retrofit  # noqa: E402
from tasks.task_metadata import parse_task_file, parse_task_text, task_prose_lines  # noqa: E402
from tasks.task_orientation import (  # noqa: E402
    MAX_EXPLAIN_ITEMS,
    MAX_ITEMS,
    OrientationItem,
    parse_orientation,
    resolve_orientation,
)
from tasks.validate_task import (  # noqa: E402
    EXIT_FINDINGS,
    EXIT_OK,
    RECORD_WARN_LINES,
    TASK_ERROR_LINES,
    TASK_WARN_LINES,
    Validator,
    main as validate_main,
)

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"
_LOOPBACK = "127.0.0.1"
_ANSWER = "The test builds the service with a factory (datrix-alpha/src/alpha_pkg/core.py:4)."

_CORE = (
    '"""Core."""\n\n\ndef alpha_function(x: int) -> int:\n    """Add one."""\n    return x + 1\n\n\n'
    'def caller() -> int:\n    return alpha_function(2)\n'
)


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


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _lines(count: int) -> str:
    return "".join(f"LINE_{n} = {n}\n" for n in range(1, count + 1))


def _task(name: str, body: str, *, repo: str = "datrix-alpha", phase: int = 90, number: int = 1,
          extra_sections: str = "") -> str:
    return (f"# Task {phase}-{number:02d}: {name}\n\n## Overview\nA fixture.\n\n**Package:** `{repo}`\n"
            f"**Depends on:** None\n\n## Files to Review Before Starting\n1. `rules.md` -- rules\n{extra_sections}\n"
            f"## Notes\n{body}\n")


@contextmanager
def _workspace() -> Iterator[Path]:
    """Framework repositories datrix, datrix-alpha, datrix-beta (git repos) with real files."""
    with TemporaryDirectory(prefix="task-gate-") as temp:
        root = Path(temp)
        for repo in ("datrix", "datrix-alpha", "datrix-beta"):
            (root / repo).mkdir()
            subprocess.run(["git", "-C", str(root / repo), "init", "-q"], check=True, capture_output=True)
        _write(root / "datrix-alpha/src/alpha_pkg/__init__.py", "")
        _write(root / "datrix-alpha/src/alpha_pkg/core.py", _CORE)
        _write(root / "datrix-alpha/src/alpha_pkg/long.py", _lines(100))
        # The same relative path and the same bare name in two repositories: ambiguous.
        _write(root / "datrix-alpha/src/alpha_pkg/plugin/capability.py", _lines(20))
        _write(root / "datrix-beta/src/beta_pkg/plugin/capability.py", _lines(90))
        _write(root / "datrix-beta/src/beta_pkg/only_beta.py", _lines(30))
        yield root


class _ModelServer:
    """An OpenAI-compatible server on loopback answering every chat with ``_ANSWER``."""

    def __init__(self) -> None:
        self.chats = 0
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._send({"data": [{"id": "gate-model"}]})

            def do_POST(self) -> None:  # noqa: N802 -- http.server's dispatch name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if body.get("max_tokens") != 1:
                    server.chats += 1
                self._send({"choices": [{"message": {"content": _ANSWER}, "finish_reason": "stop"}]})

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


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


def _settings(openai_port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=_closed_port(), openai_ports=(openai_port,),
                            usage_log=usage_log, caller="gate")


# ===========================================================================
# the Orientation block
# ===========================================================================


def check_orientation_block_is_read_by_the_one_task_parser() -> None:
    with _workspace() as root:
        block = ("```orientation\n# comment\nsymbol: alpha_function\n\nrefs: alpha_pkg.core.alpha_function\n```\n")
        other = "```python\nsymbol: not_orientation\n```\n"
        task = _write(root / "datrix-alpha/.tasks/phase-90/task-90-01-a.md",
                      _task("A", other, extra_sections=f"\n## Orientation\n{block}"))
        meta = parse_task_file(task)
        assert meta.orientation == ["# comment", "symbol: alpha_function", "refs: alpha_pkg.core.alpha_function"], \
            meta.orientation
        assert [item.kind for item in parse_orientation(meta.orientation).items] == ["symbol", "refs"], \
            "the parser keeps the block's lines; comments are dropped when it is read"
        assert meta.to_dict()["orientation"] == meta.orientation
        bare = parse_task_file(_write(root / "datrix-alpha/.tasks/phase-90/task-90-02-b.md", _task("B", "text", number=2)))
        assert bare.orientation == [], "a task with no block has none"
        prose = [text for _, text in task_prose_lines(task.read_text(encoding="utf-8"))]
        assert not any("not_orientation" in line or "symbol: alpha_function" in line for line in prose), \
            "lines inside a code fence are not prose"


def check_malformed_entries_are_rejected_with_what_to_write() -> None:
    cases = {
        "wrong kind": ("grep: alpha", "is not '<kind>: <argument>'"),
        "no colon": ("alpha_function", "is not '<kind>: <argument>'"),
        "no argument": ("symbol:", "has no argument"),
        "explain without separator": ("explain: a.py", "the '::' is missing"),
        "explain with no files": ("explain:  :: How does this module build its result", "names 0 files"),
        "explain too short": ("explain: a.py :: What is it", "too short"),
    }
    for label, (line, expected) in cases.items():
        parsed = parse_orientation([line])
        assert not parsed.items and len(parsed.errors) == 1 and expected in parsed.errors[0], (label, parsed)
    parsed = parse_orientation(["explain: " + "; ".join(f"f{n}.py" for n in range(9)) + " :: How does this build it"])
    assert "names 9 files" in parsed.errors[0], parsed
    many = parse_orientation([f"symbol: name_{n}" for n in range(MAX_ITEMS + 1)])
    assert any(f"at most {MAX_ITEMS}" in error for error in many.errors), many.errors
    explains = parse_orientation([f"explain: a.py :: How does this module number {n} build its result" for n in range(MAX_EXPLAIN_ITEMS + 1)])
    assert any(f"at most {MAX_EXPLAIN_ITEMS}" in error for error in explains.errors), explains.errors
    good = parse_orientation(["symbol: alpha", "outline: a.py", "canonical: text/to-snake",
                              "explain: a.py; b.py :: How does this module build its result?"])
    assert not good.errors and [i.kind for i in good.items] == ["symbol", "outline", "canonical", "explain"], good


def check_lookup_questions_are_rejected_because_a_model_invents_the_answer() -> None:
    lookups = (
        "Where is enum_imports_used_in_body defined?",
        "Where are these helpers implemented in the tree?",
        "Who calls the resolver and with what argument?",
        "What calls transpile_statement in these files?",
        "List all the usages of the helper in these files.",
        "Find the callers of the helper across these modules.",
        "Which functions call the resolver in these files?",
        "Which files import the helper from the shared module?",
    )
    for question in lookups:
        parsed = parse_orientation([f"explain: a.py :: {question}"])
        assert not parsed.items and "use 'symbol: <name>' or 'refs: <dotted.path>'" in parsed.errors[0], (question, parsed)
    fine = ("How does this module decide that an enum is used in a body?",
            "What does the factory in these files build, and which arguments does it take?")
    for question in fine:
        assert not parse_orientation([f"explain: a.py :: {question}"]).errors, question


# ===========================================================================
# the resolver
# ===========================================================================


def check_facts_are_exact_stale_entries_are_called_out_and_explanations_are_leads() -> None:
    with _workspace() as root, _ModelServer() as server, contextlib.closing(open_session(root)) as session:
        session.refresh()
        scope = ReadScope(root)
        pool = LocalLlmPool(_settings(server.port, root / "usage.jsonl"), report=lambda _line: None)

        def ask(item: OrientationItem) -> str:
            return ask_files(scope, pool, list(item.paths), item.question).render()

        lines = ["symbol: alpha_function", "refs: alpha_pkg.core.alpha_function", "symbol: renamed_away_function",
                 "outline: datrix-alpha/src/alpha_pkg/core.py", "outline: datrix-alpha/src/alpha_pkg/missing.py",
                 f"explain: {root / 'datrix-alpha/src/alpha_pkg/core.py'} :: How does this module build its result?"]
        resolved = resolve_orientation(lines, session.conn, ask)
        text = resolved.render("task-90-01")
        assert "core.py:4  def alpha_function(x: int) -> int" in text, text
        assert "core.py: 10 call" in text, "the references give the call site's line"
        assert resolved.unresolved == ("symbol renamed_away_function", "outline datrix-alpha/src/alpha_pkg/missing.py"), \
            resolved.unresolved
        assert "STALE TASK PREMISE" in text and "UNRESOLVED" in text, text
        assert _ANSWER in text and "A lead, not a finding" in text, "an explanation is the model's, marked as a lead"
        assert server.chats == 1, f"one explain entry is one model read, got {server.chats}"
        offline = resolve_orientation(lines[:1] + [lines[-1]], session.conn,
                                      lambda item: ask_files(scope, LocalLlmPool(_settings(_closed_port(), root / "u.jsonl"),
                                                                                  report=lambda _l: None),
                                                             list(item.paths), item.question).render())
        offline_text = offline.render("task-90-01")
        assert "def alpha_function" in offline_text and "UNAVAILABLE" in offline_text and _ANSWER not in offline_text, \
            "with no model server the facts stand and the explanation says it is unavailable"
        assert resolve_orientation([], session.conn, None).render("task-90-01") == "", "no block, no output"


# ===========================================================================
# the citation checker
# ===========================================================================


def _context(root: Path, repo: str = "datrix-alpha", creates: frozenset[Path] = frozenset(),
             listed: dict[str, list[Path]] | None = None) -> CitationContext:
    repos = tuple(root / name for name in ("datrix", "datrix-alpha", "datrix-beta") if name != repo)
    return CitationContext(root, root / repo, listed or {}, creates, RepoFiles(), repos)


def _findings(root: Path, text: str, creates: frozenset[Path] = frozenset(),
              listed: dict[str, list[Path]] | None = None) -> list[tuple[str, str]]:
    return [(f.level, f.citation) for f in check_citations(text, _context(root, creates=creates, listed=listed))]


def check_citations_error_on_a_missing_file_or_a_line_past_the_end() -> None:
    with _workspace() as root:
        core = root / "datrix-alpha/src/alpha_pkg/core.py"
        text = (f"The helper is at `{core}:4-6`.\nIt moved to `{core}:900`.\nAnd `{core}:8-3` is backwards.\n"
                f"Gone: `{root / 'datrix-alpha/src/alpha_pkg/gone.py'}:1`.\n")
        found = _findings(root, text)
        assert found == [(LEVEL_ERROR, f"{core}:900"), (LEVEL_ERROR, f"{core}:8-3"),
                         (LEVEL_ERROR, f"{root / 'datrix-alpha/src/alpha_pkg/gone.py'}:1")], found


def check_citations_do_not_guess_which_file_was_meant() -> None:
    with _workspace() as root:
        # plugin/capability.py has 20 lines in alpha and 90 in beta: either could be meant.
        assert _findings(root, "See `plugin/capability.py:50-60`.") == [], "a path two repositories carry is skipped"
        assert _findings(root, "See `capability.py:50`.") == [], "a bare name two repositories carry is skipped"
        # A name only ONE repository carries is checked, even from a task of another repository.
        assert _findings(root, "See `only_beta.py:99`.") == [(LEVEL_ERROR, "only_beta.py:99")]
        assert _findings(root, "See `only_beta.py:20`.") == []
        # A relative tail that names exactly one file is found from the workspace, the repo, or a subdirectory.
        assert _findings(root, "See `alpha_pkg/long.py:101`.") == [(LEVEL_ERROR, "alpha_pkg/long.py:101")]
        assert _findings(root, "See `alpha_pkg/long.py:100`.") == []
        # The task's own file list does not turn an ambiguous name into a certain one.
        listed = {"capability.py": [root / "datrix-beta/src/beta_pkg/plugin/capability.py"]}
        assert _findings(root, "See `capability.py:50`.", listed=listed) == []
        # An abbreviated path names no file.
        assert _findings(root, "See `.../tests/unit/x.py:5` and `…/y.py:5`.") == []


def check_citations_allow_a_file_the_phase_creates() -> None:
    with _workspace() as root:
        future = root / "datrix-alpha/src/alpha_pkg/future.py"
        text = f"The new module `{future}:10` and `alpha_pkg/future.py:12`."
        assert _findings(root, text) == [(LEVEL_ERROR, f"{future}:10"), (LEVEL_ERROR, "alpha_pkg/future.py:12")]
        assert _findings(root, text, creates=frozenset({future.resolve()})) == [], \
            "a file that a task of the phase creates need not exist yet"


def check_citations_warn_only_when_the_name_beside_them_is_not_near_the_lines() -> None:
    with _workspace() as root:
        core = root / "datrix-alpha/src/alpha_pkg/core.py"
        beside = f"`{core}:4-6` `alpha_function(x)` adds one."
        assert _findings(root, beside) == [], "the name beside the citation is at the cited lines"
        moved = f"`{core}:9-10` `alpha_function(x)` adds one."
        assert _findings(root, moved) == [], "within three lines of the range still counts"
        far = f"`{core}:9-10` `completely_other_name` adds one."
        assert _findings(root, far) == [(LEVEL_WARN, f"{core}:9-10")], "a name that is nowhere near the lines is drift"
        before = f"`gone_function` is at `{core}:5`."
        assert _findings(root, before) == [(LEVEL_WARN, f"{core}:5")], "the span before the citation counts too"
        elsewhere = f"`{core}:5` is read, much further along in this same sentence, by `completely_other_name`."
        assert _findings(root, elsewhere) == [], "a name far from the citation says nothing about its lines"
        noise = f"`{core}:9-10` raises `ValueError` here."
        assert _findings(root, noise) == [], "a language name is not evidence"
        fenced = f"```\n{core}:900 and `{core}:901`\n```\n"
        assert _findings(root, fenced) == [], "a code fence holds code to write, not claims about the tree"


# ===========================================================================
# the validator
# ===========================================================================


def check_validator_reports_stale_orientation_and_citations_and_sets_the_exit_code() -> None:
    with _workspace() as root:
        core = root / "datrix-alpha/src/alpha_pkg/core.py"
        good = _write(root / "datrix-alpha/.tasks/phase-90/task-90-01-good.md", _task(
            "Good", f"`{core}:4-6` `alpha_function(x)`.",
            extra_sections="\n## Orientation\n```orientation\nsymbol: alpha_function\nrefs: alpha_pkg.core.alpha_function\n"
                           "outline: datrix-alpha/src/alpha_pkg/core.py\n```\n"))
        stale = _write(root / "datrix-alpha/.tasks/phase-90/task-90-02-stale.md", _task(
            "Stale", f"`{core}:90` is beyond the file.", number=2,
            extra_sections="\n## Orientation\n```orientation\nsymbol: renamed_away_function\n"
                           "explain: datrix-alpha/../../etc/passwd :: How does this module build its result\n"
                           "explain: a.py :: Where is the resolver defined in this tree\n```\n"))
        validator = Validator(root)
        try:
            assert validator.validate(good) == [], "a task whose orientation resolves and whose citations hold is clean"
            findings = [f"{f.level} {f.message}" for f in validator.validate(stale)]
        finally:
            validator.close()
        joined = "\n".join(findings)
        assert "'symbol renamed_away_function' does not resolve against the tree as it is now" in joined, joined
        assert "outside what local-model tools may read" in joined, "an explain over files a model may not read"
        assert "asks where something is defined" in joined, joined
        assert "lines 90-90 are not in core.py, which has 10 lines" in joined, joined
        required = Validator(root, require_orientation=True)
        try:
            bare = _write(root / "datrix-alpha/.tasks/phase-90/task-90-03-bare.md", _task("Bare", "Nothing.", number=3))
            assert [f.message for f in required.validate(bare)] == [
                "no '## Orientation' block (required by --require-orientation)"]
        finally:
            required.close()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert validate_main([str(good), "--base-dir", str(root)]) == EXIT_OK
            assert validate_main([str(stale), "--base-dir", str(root)]) == EXIT_FINDINGS
            assert validate_main(["--phase", "90", "--base-dir", str(root)]) == EXIT_FINDINGS
        assert "task-90-01-good.md: OK" in output.getvalue() and "task(s)" in output.getvalue(), output.getvalue()


def check_validator_phase_mode_counts_files_other_tasks_create() -> None:
    with _workspace() as root:
        future = root / "datrix-alpha/src/alpha_pkg/future.py"
        _write(root / "datrix-alpha/.tasks/phase-90/task-90-01-creates.md", _task(
            "Creates", "Nothing.", extra_sections=f"\n## Files to Create\n### 1. `{future}` -- the module\n"))
        citing = _write(root / "datrix-alpha/.tasks/phase-90/task-90-02-cites.md",
                        _task("Cites", f"The new module is at `{future}:3`.", number=2))
        validator = Validator(root)
        try:
            assert validator.validate(citing) == [], "task 90-01 creates the file task 90-02 cites"
        finally:
            validator.close()
        _write(root / "datrix-alpha/.tasks/phase-90/task-90-01-creates.md", _task("Creates", "Nothing."))
        validator = Validator(root)
        try:
            assert [f.level for f in validator.validate(citing)] == [LEVEL_ERROR], "nothing creates it now"
        finally:
            validator.close()


def check_validator_bounds_task_length_and_the_executor_record() -> None:
    padding = "\n".join(f"line {n}" for n in range(TASK_ERROR_LINES + 1))
    warn_padding = "\n".join(f"line {n}" for n in range(TASK_WARN_LINES + 1))
    record = "\n".join(f"- decision {n}" for n in range(RECORD_WARN_LINES + 1))
    with _workspace() as root:
        oversized = _write(root / "datrix-alpha/.tasks/phase-90/task-90-01-big.md", _task("Big", padding))
        long = _write(root / "datrix-alpha/.tasks/phase-90/task-90-02-long.md", _task("Long", warn_padding, number=2))
        chatty = _write(root / "datrix-alpha/.tasks/phase-90/task-90-03-chatty.md",
                        _task("Chatty", "Nothing.", number=3, extra_sections=f"\n## How Solved\n{record}\n"))
        done = _write(root / "datrix-alpha/.tasks/phase-90/task-90-04-done.md",
                      _task("Done", padding, number=4).replace("# Task", "# COMPLETED: Task", 1))
        validator = Validator(root)
        try:
            levels = {path.name: [f.level for f in validator.validate(path)]
                      for path in (oversized, long, chatty, done)}
        finally:
            validator.close()
        assert levels["task-90-01-big.md"] == [LEVEL_ERROR], f"over {TASK_ERROR_LINES} lines must fail: {levels}"
        assert levels["task-90-02-long.md"] == [LEVEL_WARN], f"over {TASK_WARN_LINES} lines must warn: {levels}"
        assert levels["task-90-03-chatty.md"] == [LEVEL_WARN], f"a long record must warn: {levels}"
        assert levels["task-90-04-done.md"] == [], f"a COMPLETED task is exempt from the length limit: {levels}"


# ===========================================================================
# the retrofit
# ===========================================================================


def _retrofit_task(root: Path, name: str, review: list[str], body: str = "", modify: list[str] | None = None,
                   *, number: int = 5, category: str = "", newline: str = "\n") -> Path:
    edits = "".join(f"### {n}. `{path}` -- change it\n" for n, path in enumerate(modify or [], start=1))
    text = (f"# Task 90-{number:02d}: {name}\n\n## Overview\nA fixture.\n\n**Package:** `datrix-alpha`\n"
            f"{f'**Category:** {category}{chr(10)}' if category else ''}**Depends on:** None\n\n"
            f"## Files to Review Before Starting\n{chr(10).join(review)}\n\n"
            f"## Files to Modify\n{edits}\n## Notes\n{body}\n")
    path = root / f"datrix-alpha/.tasks/phase-90/task-90-{number:02d}-{name.lower().replace(' ', '-')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def _retrofit(root: Path, task: Path, *, write: bool = False) -> RetrofitResult:
    session = open_session(root)
    try:
        session.refresh()
        result = convert(task, root, session)
        if write and result.outcome == OUTCOME_CONVERTED:
            apply_retrofit(result, root, "gate")
        return result
    finally:
        session.close()


def check_retrofit_converts_only_whole_file_orientation_items_and_nothing_else() -> None:
    with _workspace() as root:
        src = root / "datrix-alpha/src/alpha_pkg"
        _write(src / "helper.py", "def helper_function(x: int) -> int:\n    return x\n")
        _write(src / "other.py", "def lonely_function(x: int) -> int:\n    return x\n")
        _write(src / "twin_a.py", "def dup_function() -> int:\n    return 1\n")
        _write(src / "twin_b.py", "def dup_function() -> int:\n    return 2\n")
        edited = src / "edited.py"
        _write(edited, "def edited_function() -> int:\n    return 3\n")
        core, long = src / "core.py", src / "long.py"
        task = _retrofit_task(
            root, "Retrofit fixture",
            [f"1. `rules.md` -- the rules", f"2. `{core}` -- the module it works with", f"3. `{long}` (lines 10-20)",
             f"4. `{edited}` -- the file it edits", f"5. `{src / 'helper.py'}` -- a helper",
             f"6. `{core}` and `{src / 'helper.py'}` -- two files on one item"],
            body=(f"`{src / 'other.py'}:1` `lonely_function(x)` is cited, and `{src / 'twin_a.py'}:1` `dup_function()` too.\n"),
            modify=[str(edited)])
        before = task.read_bytes()
        planned = _retrofit(root, task)
        assert task.read_bytes() == before, "a dry run writes nothing"
        assert planned.outcome == OUTCOME_CONVERTED and planned.outlines == (
            "datrix-alpha/src/alpha_pkg/core.py", "datrix-alpha/src/alpha_pkg/helper.py"), planned
        assert planned.symbols == ("symbol: lonely_function",), (
            "a unique definition in a file the task does not edit; an ambiguous name is not guessed", planned.symbols)
        written = _retrofit(root, task, write=True)
        assert written.removed_lines == 2
        after = task.read_text(encoding="utf-8")
        review = after.split("## Files to Review Before Starting")[1].split("## Orientation")[0]
        assert "`rules.md`" in review and f"`{long}` (lines 10-20)" in review and f"`{edited}`" in review, \
            "rules, a ranged read and an edit site stay in the review list"
        assert f"`{core}` and" in review, "an item naming two files is left alone"
        assert [line.split(".")[0] for line in review.splitlines() if line[:1].isdigit()] == ["1", "2", "3", "4"], \
            "the remaining items are numbered 1..n again"
        assert "```orientation\noutline: datrix-alpha/src/alpha_pkg/core.py\noutline: " in after and "symbol: lonely_function" in after
        assert "are not listed here" in after
        meta, old = parse_task_file(task), parse_task_text(task, before.decode("utf-8"))
        assert meta.depends_on == old.depends_on and meta.files_to_create_modify == old.files_to_create_modify
        validator = Validator(root)
        try:
            errors = [f.message for f in validator.validate(task) if f.level == LEVEL_ERROR]
        finally:
            validator.close()
        assert not errors, f"a retrofitted task validates: {errors}"
        backup = next((root / ".tmp/retrofit-orientation/gate").iterdir())
        assert backup.read_bytes() == before, "the original is copied aside before the task is rewritten"
        assert _retrofit(root, task).outcome == OUTCOME_SKIPPED, "a converted task has a block: idempotent"


def check_retrofit_leaves_alone_what_it_should() -> None:
    with _workspace() as root:
        core = root / "datrix-alpha/src/alpha_pkg/core.py"
        gate = _retrofit_task(root, "Gate", [f"1. `{core}` -- verify it"], number=6, category="Quality Gate")
        assert _retrofit(root, gate).reason.startswith("quality gate"), "reading the code is a quality gate's job"
        none = _retrofit_task(root, "Nothing", ["1. `rules.md` -- the rules", f"2. `{core}` (lines 1-5)"], number=7)
        assert _retrofit(root, none).reason.startswith("nothing the index can answer"), "only a ranged item"
        absent = _retrofit_task(root, "Absent", [f"1. `{root / 'datrix-alpha/src/alpha_pkg/gone.py'}` -- gone"], number=8)
        assert _retrofit(root, absent).outcome == OUTCOME_SKIPPED, "a file that does not exist is not converted"
        noreview = root / "datrix-alpha/.tasks/phase-90/task-90-09-no-review.md"
        noreview.write_text("# Task 90-09: No review\n\n## Overview\nNothing.\n", encoding="utf-8")
        assert _retrofit(root, noreview).reason == "no Files to Review section"


def check_retrofit_preserves_line_endings_and_respects_the_caps() -> None:
    with _workspace() as root:
        src = root / "datrix-alpha/src/alpha_pkg"
        for n in range(10):
            _write(src / f"mod{n}.py", f"def function_{n}() -> int:\n    return {n}\n")
        review = [f"{n + 1}. `{src / f'mod{n}.py'}` -- module {n}" for n in range(10)]
        crlf = _retrofit_task(root, "Crlf", review, number=10, newline="\r\n")
        result = _retrofit(root, crlf, write=True)
        assert len(result.outlines) == 8 and result.removed_lines == 8, "at most 8 outline entries"
        raw = crlf.read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), "line endings are kept as the task had them"
        left = [line for line in raw.decode("utf-8").split("\r\n") if line[:1].isdigit() and "`" in line]
        assert len(left) == 2 and left[0].startswith("1. ") and left[1].startswith("2. "), left
        assert "mod8.py" in left[0] and "mod9.py" in left[1], "the items past the cap stay, to be read as before"


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
    check_orientation_block_is_read_by_the_one_task_parser,
    check_malformed_entries_are_rejected_with_what_to_write,
    check_lookup_questions_are_rejected_because_a_model_invents_the_answer,
    check_facts_are_exact_stale_entries_are_called_out_and_explanations_are_leads,
    check_citations_error_on_a_missing_file_or_a_line_past_the_end,
    check_citations_do_not_guess_which_file_was_meant,
    check_citations_allow_a_file_the_phase_creates,
    check_citations_warn_only_when_the_name_beside_them_is_not_near_the_lines,
    check_validator_reports_stale_orientation_and_citations_and_sets_the_exit_code,
    check_validator_phase_mode_counts_files_other_tasks_create,
    check_validator_bounds_task_length_and_the_executor_record,
    check_retrofit_converts_only_whole_file_orientation_items_and_nothing_else,
    check_retrofit_leaves_alone_what_it_should,
    check_retrofit_preserves_line_endings_and_respects_the_caps,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for task orientation and citation validation.")
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
    print(f"Running {len(checks)} task orientation checks...\n")
    with TemporaryDirectory(prefix="task-gate-usage-") as temp:
        os.environ[USAGE_LOG_VARIABLE] = str(Path(temp) / "usage.jsonl")
        passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} task orientation checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
