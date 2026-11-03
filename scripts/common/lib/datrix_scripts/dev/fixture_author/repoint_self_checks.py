"""The self-test of repointing a package, over a loopback model server on a planted package.

The planted workspace holds a package with two inventoried modules: one whose test reads its own fixture
file (its input can be shared: the library plan places it in the ``library`` entry) and one whose test reads
an inline fragment that is a syntax error (a ``local`` input). The rewrites are judged by the real checks;
the planted workspace is not a workspace package ``test.ps1`` can run, so a rewrite's tests are run by
importing the planted module and calling each test function (the production runner, ``test.ps1
-Specific``, is checked by parsing the command it builds with the runner's own parser). A rewrite reading
``corpus_project`` is kept and a local input moved to a ``// @local`` file is kept, and the package's set
comparison inventoried − rewritten − local is empty; a rewrite dropping an assertion, one whose test
fails, and one building its own project instead of reading the corpus are written back byte for byte and
queued with why; a rewrite adding a secret-looking literal is
queued after its one request and never written; an interrupted rewrite's undo record is written back first,
and with no local model the run exits 3 and writes nothing else; the tool runs no git command.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import tempfile
import traceback
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import CheckFunc

if TYPE_CHECKING:
    from datrix_scripts.dev.fixture_author.library_plan import InventoriedModule
    from datrix_scripts.dev.fixture_author.repoint import RepointOutcome
    from datrix_scripts.dev.fixture_author.repoint_jobs import RunVerdict
    from datrix_scripts.local_llm_loopback import Chat, LoopbackOllama

_CALLER: Final = "fixture-author-repoint-self-test"
_PACKAGE: Final = "datrix-planted"
_SHELF: Final = f"{_PACKAGE}/tests/test_shelf.py"
_PARSE: Final = f"{_PACKAGE}/tests/test_parse.py"
_FIXTURE: Final = f"{_PACKAGE}/tests/fixtures/shelf.dtrx"
_LOCAL_FILE: Final = f"{_PACKAGE}/tests/fixtures/parser/service.dtrx.false"
_SHARED_FIXTURES: Final = "datrix-testing/src/datrix_testing/fixtures_data"
_SHELF_TEST: Final = "test_shelf_entry_names_its_system"
_PARSE_TEST: Final = "test_fragment_is_unclosed"
_LOCAL_REASON: Final = "the input is a syntax error"
_SENT_BACK: Final = "PROBLEMS OF YOUR LAST ANSWER"
# An access key id of the documented example shape: assembled, so no literal of it is committed.
_SECRET: Final = "AKIA" + "IOSFODNN7" + "EXAMPLE"

_SHELF_SOURCE: Final = '''"""Planted: reads its own fixture file."""

from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "shelf.dtrx"


def test_shelf_entry_names_its_system() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    assert "system" in text
    assert "include" in text
'''
_SHELF_FIXTURE: Final = """include 'services/shelf.dtrx';

system test.System('config/system.dcfg') : version('1.0.0') {
}
"""
_PARSE_SOURCE: Final = '''"""Planted: reads an inline fragment that does not close."""

FRAGMENT = """
service test.ShelfService {
"""


def test_fragment_is_unclosed() -> None:
    assert FRAGMENT.count("{") == 1
'''
_CORPUS_SHELF: Final = '''"""Planted: reads the corpus library entry."""

from datrix_testing.corpus import corpus_project


def test_shelf_entry_names_its_system() -> None:
    text = corpus_project("library").read_text(encoding="utf-8")
    assert "system" in text
    assert {last}
'''
_LOCAL_PARSE: Final = '''"""Planted: reads a local fragment that does not close."""

from pathlib import Path

FRAGMENT = Path(__file__).parent / "fixtures" / "parser" / "service.dtrx.false"


def test_fragment_is_unclosed() -> None:
    assert FRAGMENT.read_text(encoding="utf-8").count("{") == 1
'''
_LOCAL_FRAGMENT: Final = f"// @local {_LOCAL_REASON}\nservice test.ShelfService {{\n"


@dataclass(frozen=True)
class _Planted:
    """A planted workspace with its package, the undo record and the queue a run writes beside it."""

    workspace: Path
    undo: Path
    queue: Path

    @property
    def package_dir(self) -> Path:
        return self.workspace / _PACKAGE

    def files(self) -> dict[str, bytes]:
        """Every file of the planted package, by workspace-relative path, with its bytes."""
        return {path.relative_to(self.workspace).as_posix(): path.read_bytes()
                for path in self.package_dir.rglob("*") if path.is_file() and "__pycache__" not in path.parts}


@contextmanager
def _planted() -> Iterator[_Planted]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        (workspace / _SHARED_FIXTURES).mkdir(parents=True)
        for relative, text in ((_SHELF, _SHELF_SOURCE), (_FIXTURE, _SHELF_FIXTURE), (_PARSE, _PARSE_SOURCE)):
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        yield _Planted(workspace, Path(tmp) / "undo", Path(tmp) / "queue")


def _rows(*modules: str) -> tuple[InventoriedModule, ...]:
    from datrix_scripts.dev.fixture_author.library_plan import InventoriedModule, InventoriedTest
    from datrix_scripts.dev.fixture_author.needs_reading import Declaration

    shelf = InventoriedModule(_PACKAGE, _SHELF, (
        InventoriedTest(_SHELF_TEST, (Declaration("System", "test.System", ()),), None),
    ))
    parse = InventoriedModule(_PACKAGE, _PARSE, (InventoriedTest(_PARSE_TEST, (), _LOCAL_REASON),))
    return tuple(row for row in (shelf, parse) if row.module in modules)


def _planted_runner(package_dir: Path, files: Sequence[str]) -> RunVerdict:
    """Import each planted test module of *files* and call its test functions; a failed assertion fails the run
    with its traceback."""
    from datrix_scripts.dev.fixture_author.repoint_jobs import RunVerdict

    failures: list[str] = []
    for relative in files:
        spec = importlib.util.spec_from_file_location(f"_planted_{uuid.uuid4().hex}", package_dir / relative)
        assert spec is not None and spec.loader is not None, relative
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, value in sorted(vars(module).items()):
            if not (name.startswith("test") and callable(value)):
                continue
            try:
                value()
            except AssertionError:
                failures.append(f"{relative}::{name} FAILED\n{traceback.format_exc()}")
    return RunVerdict(not failures, "\n".join(failures) or f"{len(files)} module(s) passed")


def _repoint(planted: _Planted, server: LoopbackOllama, rows: tuple[InventoriedModule, ...], *,
             max_rounds: int = 2) -> tuple[int, str, RepointOutcome | None]:
    from datrix_scripts.dev.fixture_author.library_plan import NeededTest, NeedsInventory, plan_library
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds
    from datrix_scripts.dev.fixture_author.repoint import Repointer, repoint_package, run_repoint
    from datrix_scripts.dev.fixture_author.repoint_jobs import UndoStore, plan_jobs
    from datrix_scripts.local_llm import LocalLlmPool
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    shared = tuple(NeededTest(row.package, row.module, test.name, test.declarations)
                   for row in rows for test in row.tests if test.local is None)
    plan = plan_library(NeedsInventory(shared, local=0), block_families(node_kinds()), {}, lambda *_: False)
    jobs = plan_jobs(rows, plan, (), planted.package_dir, planted.workspace)
    pool = LocalLlmPool(server.settings(_CALLER), report=lambda _line: None)
    repointer = Repointer(pool, ContentFilter(WORKSPACE_DIR), planted.package_dir, rows, jobs, (), _planted_runner,
                          workspace=planted.workspace, undo=UndoStore(planted.undo), queue_dir=planted.queue,
                          max_rounds=max_rounds)
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = run_repoint(repointer)
    outcome = repoint_package(repointer) if code == 0 else None
    return code, printed.getvalue(), outcome


def _answer(module: str, files: dict[str, str] | None = None) -> str:
    return json.dumps({"module": module, "files": [{"path": path, "text": text} for path, text in (files or {}).items()]})


def _by_module(answers: dict[str, Callable[[Chat], str]]) -> Callable[[Chat], str]:
    def answer(chat: Chat) -> str:
        for module, respond in answers.items():
            if chat.user.startswith(f"MODULE: {module}\n"):
                return respond(chat)
        raise AssertionError(f"a request names no planted module: {chat.user[:80]!r}")

    return answer


def _local_answer(chat: Chat) -> str:
    """A fragment file without its ``// @local`` line first; once that is sent back, with it."""
    text = _LOCAL_FRAGMENT if _SENT_BACK in chat.user else _LOCAL_FRAGMENT.split("\n", 1)[1]
    return _answer(_LOCAL_PARSE, {_LOCAL_FILE: text})


def _queue_text(planted: _Planted) -> str:
    files = sorted(planted.queue.glob("*.md")) if planted.queue.is_dir() else []
    assert len(files) == 1, files
    return files[0].read_text(encoding="utf-8")


def _check_a_loopback_rewrite_reading_the_corpus_is_kept_and_nothing_is_left() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    good = _answer(_CORPUS_SHELF.format(last='"include" in text'))
    with _planted() as planted, LoopbackOllama(_by_module({_SHELF: lambda _chat: good, _PARSE: _local_answer})) as server:
        code, printed, outcome = _repoint(planted, server, _rows(_SHELF, _PARSE))
        chats = list(server.chats)
        files = planted.files()
        undo_left = planted.undo.exists() and any(planted.undo.iterdir())
        queued = sorted(planted.queue.glob("*.md")) if planted.queue.is_dir() else []
    assert code == 0, printed
    assert outcome is not None, printed
    status = outcome.status
    assert status.inventoried == {_SHELF, _PARSE} and status.rewritten == {_SHELF}, status
    assert status.local == {_PARSE} and status.remainder() == frozenset(), status
    assert set(outcome.done) == {_SHELF, _PARSE}, "a second run finds both modules done and asks nothing"
    assert files[_SHELF].decode() == _CORPUS_SHELF.format(last='"include" in text'), "the corpus rewrite is kept"
    assert files[_LOCAL_FILE].decode() == _LOCAL_FRAGMENT, "the local fragment is written with its @local line"
    assert not undo_left and queued == [], (undo_left, queued)
    shelf_chats = [chat for chat in chats if chat.user.startswith(f"MODULE: {_SHELF}\n")]
    parse_chats = [chat for chat in chats if chat.user.startswith(f"MODULE: {_PARSE}\n")]
    assert len(shelf_chats) == 1 and len(parse_chats) == 2, (len(shelf_chats), len(parse_chats))
    (shelf,) = shelf_chats
    assert f"{_SHELF_TEST}: ENTRY library" in shelf.user and "=== library.dtrx ===" in shelf.user, shelf.user[:600]
    assert "fixtures/shelf.dtrx" in shelf.user, "the current inputs are sent"
    assert f"{_PARSE_TEST}: LOCAL {_LOCAL_REASON}" in parse_chats[0].user
    assert "does not open with `// @local <reason>`" in parse_chats[1].user, "an unmarked local file goes back"
    assert "inventoried 2 - rewritten 1 - local 1 = 0 not done" in printed, printed


def _check_a_rewrite_dropping_an_assertion_is_written_back_byte_for_byte_and_queued() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.skill.common import EXIT_NO_MODEL

    dropped = _answer(_CORPUS_SHELF.format(last='"system" in text').replace('    assert "system" in text\n', "", 1))
    with _planted() as planted, LoopbackOllama(answering(dropped)) as server:
        before = planted.files()
        code, printed, _ = _repoint(planted, server, _rows(_SHELF))
        chats = list(server.chats)
        after = planted.files()
        queue = _queue_text(planted)
        undo_left = (planted.undo / "pending.json").exists()
    assert code not in (0, EXIT_NO_MODEL), printed
    assert after == before, "a rewrite dropping an assertion is written back byte for byte"
    assert len(chats) == 2 and _SENT_BACK in chats[1].user, "the failure goes back once, then the module is queued"
    assert "assertion count fell from 2 to 1" in chats[1].user and "assertion count fell from 2 to 1" in queue, queue
    assert "## Last draft" in queue and not undo_left, queue
    assert f"= 1 not done: ['{_SHELF}']" in printed, printed


def _check_a_rewrite_whose_test_fails_is_written_back_and_queued_with_the_failure() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering

    failing = _answer(_CORPUS_SHELF.format(last='"no-such-declaration" in text'))
    with _planted() as planted, LoopbackOllama(answering(failing)) as server:
        before = planted.files()
        code, printed, _ = _repoint(planted, server, _rows(_SHELF), max_rounds=1)
        after = planted.files()
        queue = _queue_text(planted)
    assert code == 1, printed
    assert after == before, "a rewrite whose test fails is written back byte for byte"
    assert f"{_SHELF_TEST} FAILED" in queue and "no-such-declaration" in queue, queue


def _check_a_rewrite_building_its_own_project_is_written_back() -> None:
    """Dropping the fixture file for text the test builds itself reads no committed input, yet shares nothing:
    a test with no local reason reads its corpus entry."""
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering

    own = _answer(_SHELF_SOURCE.replace('FIXTURE.read_text(encoding="utf-8")', '"system include"'))
    with _planted() as planted, LoopbackOllama(answering(own)) as server:
        before = planted.files()
        code, printed, _ = _repoint(planted, server, _rows(_SHELF), max_rounds=1)
        after = planted.files()
        queue = _queue_text(planted)
    assert code == 1, printed
    assert after == before, "a rewrite reading no corpus entry is written back byte for byte"
    assert f"the tests ['{_SHELF_TEST}'] have no local reason" in queue, queue


def _check_a_secret_literal_rewrite_is_refused_and_never_written() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering

    secret = _answer(_CORPUS_SHELF.format(last='"include" in text') + f'\nTOKEN = "{_SECRET}"\n')
    with _planted() as planted, LoopbackOllama(answering(secret)) as server:
        before = planted.files()
        code, printed, _ = _repoint(planted, server, _rows(_SHELF))
        asked = len(server.chats)
        after = planted.files()
        queue = _queue_text(planted)
    assert code == 1, printed
    assert after == before and asked == 1, f"refused at once, never written: {asked} request(s)"
    assert "looks like a raw secret" in queue and _SECRET not in queue, queue


def _check_an_interrupted_rewrite_is_written_back_and_no_model_exits_3() -> None:
    from datrix_scripts.dev.fixture_author.repoint_jobs import UndoStore
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.skill.common import EXIT_NO_MODEL

    with _planted() as planted:
        before = planted.files()
        module, created = planted.workspace / _SHELF, planted.workspace / _LOCAL_FILE
        UndoStore(planted.undo).save(_SHELF, [module, created])
        module.write_text("interrupted\n", encoding="utf-8")
        created.parent.mkdir(parents=True)
        created.write_text("interrupted\n", encoding="utf-8")
        with LoopbackOllama(answering("{}"), models=()) as server:
            code, printed, _ = _repoint(planted, server, _rows(_SHELF))
        after = planted.files()
        parser_dir = created.parent.exists()
        queued = planted.queue.exists()
    assert code == EXIT_NO_MODEL, printed
    assert after == before and not parser_dir, "the interrupted rewrite is written back, its new directory removed"
    assert not queued, "no model: no queue file is written"


def _check_dependents_prove_a_helper_and_a_conftest() -> None:
    from datrix_scripts.dev.fixture_author.repoint_jobs import dependents

    with _planted() as planted:
        tests = planted.package_dir / "tests"
        (tests / "unit").mkdir()
        (tests / "helpers.py").write_text("SHELF = 1\n", encoding="utf-8")
        (tests / "conftest.py").write_text("", encoding="utf-8")
        (tests / "unit" / "test_reads_helper.py").write_text("from tests.helpers import SHELF\n", encoding="utf-8")
        (tests / "unit" / "test_relative.py").write_text("from .. import helpers\n", encoding="utf-8")
        helper = [path.relative_to(tests).as_posix() for path in dependents(tests / "helpers.py", planted.package_dir)]
        conftest = [path.relative_to(tests).as_posix() for path in dependents(tests / "conftest.py", planted.package_dir)]
    assert helper == ["unit/test_reads_helper.py", "unit/test_relative.py"], helper
    assert conftest == ["test_parse.py", "test_shelf.py", "unit/test_reads_helper.py", "unit/test_relative.py"], conftest


def _check_the_proving_run_is_a_test_ps1_specific_run() -> None:
    from datrix_scripts.dev.fixture_author.repoint_jobs import specific_command
    from datrix_scripts.test.test import MODULE, build_parser

    command = specific_command("datrix-planted", ["tests/test_a.py", "tests/test_b.py"])
    assert command[1:3] == ["-m", MODULE], command
    args = build_parser().parse_args(command[3:])
    assert args.positional_projects == ["datrix-planted"] and args.specific == "tests/test_a.py,tests/test_b.py", args
    assert not (args.all or args.rerun or args.keyword or args.tag), "a -Specific run, never a sweep"


def _check_the_tool_runs_no_git_command() -> None:
    from datrix_scripts.dev.fixture_author import repoint, repoint_jobs

    for module in (repoint, repoint_jobs):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        commands = [node.value for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.split()[:1] in (["git"], ["git.exe"])]
        assert commands == [], f"{module.__name__} holds a git command: {commands}"


def _check_repoint_needs_a_package_and_refuses_diagnostics_switches() -> None:
    from datrix_scripts.dev.fixture_author.cli import REPOINT_KIND, main
    from datrix_scripts.gate_harness import EXIT_USAGE

    for argv in (["--kind", REPOINT_KIND], ["--kind", REPOINT_KIND, "--package", _PACKAGE, "--plan"]):
        printed = io.StringIO()
        with redirect_stdout(printed):
            code = main(argv)
        assert code == EXIT_USAGE, (argv, code, printed.getvalue())


CHECKS: Final[list[CheckFunc]] = [
    _check_a_loopback_rewrite_reading_the_corpus_is_kept_and_nothing_is_left,
    _check_a_rewrite_dropping_an_assertion_is_written_back_byte_for_byte_and_queued,
    _check_a_rewrite_whose_test_fails_is_written_back_and_queued_with_the_failure,
    _check_a_rewrite_building_its_own_project_is_written_back,
    _check_a_secret_literal_rewrite_is_refused_and_never_written,
    _check_an_interrupted_rewrite_is_written_back_and_no_model_exits_3,
    _check_dependents_prove_a_helper_and_a_conftest,
    _check_the_proving_run_is_a_test_ps1_specific_run,
    _check_the_tool_runs_no_git_command,
    _check_repoint_needs_a_package_and_refuses_diagnostics_switches,
]
