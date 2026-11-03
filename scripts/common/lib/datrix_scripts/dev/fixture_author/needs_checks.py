"""The self-test of ``fixture-author.ps1 needs``: input discovery and the tree readers, on planted inputs.

A planted workspace holds one package whose test modules read inputs in every form discovery knows: a
fixture file named by a literal (alone, joined with ``/``, equally near two files, written by the test
itself, found only among the shared fixtures), an inline literal, a syntax probe, a ``FIXTURE_SYSTEM*``
constant (aliased and by attribute), and conftest pair fixtures (the nearer conftest winning, a computed
file name, a hand-written fixture that is no pair). The checks assert exactly the inputs found, by form,
name, line and the file each resolves to.

Reading is proven over a loopback model server on the same workspace: every module with a test function
is asked once, its answer parsed per test (the syntax probe's carrying its ``local`` reason), a cached
rerun asks nothing, an answer naming an unknown kind or test goes back once and is refused the second
time, no local model stops the reading with nothing cached, and a run sends every request in one context
window holding its largest prompt and a resend, caching each clean answer as it arrives.

The command is proven on the same workspace: the inventory is written sorted, with the summary per
package and per block family, and a rerun (cached or not) writes the same bytes; an inventory missing a
module found is refused naming it, as is a run whose answer for a module is refused, and nothing is
written; no local model writes nothing; ``-Package`` is optional and a non-package is a usage error. On
the real workspace, over a loopback model, every module discovery finds has its row and every tree
reader its tree row.
"""

from __future__ import annotations

import ast
import dataclasses
import io
import json
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, redirect_stdout
from itertools import takewhile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import CheckFunc, write_files

if TYPE_CHECKING:
    from datrix_scripts.dev.fixture_author.needs import ModuleInputs, Unresolved
    from datrix_scripts.dev.fixture_author.needs_reading import NeedsReader
    from datrix_scripts.local_llm_loopback import Chat, LoopbackOllama
    from datrix_scripts.skill.common import ContentFilter

_PACKAGE: Final = "datrix-alpha"
_SHARED_FILE: Final = "shared.dtrx"
_CALLER: Final = "fixture-author-needs-self-test"
_PROBE_MODULE: Final = "test_syntax_probe.py"
_INLINE_MODULE: Final = "test_inline.py"
_SYNTAX_LOCAL: Final = "the input is a syntax error"
_KNOWN_KIND: Final = "Service"
_UNKNOWN_KIND: Final = "Banana"
_GHOST_TEST: Final = "test_ghost"
_DECLARED_PATH: Final = "alpha.Inline"
_DECLARED_FACTS: Final = ("entity Item", "declared", "declared")
_CACHE: Final = "needs-cache"

_READS_FILE: Final = '''"""Reads orders.dtrx: a docstring mention, not a read."""

from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_orders() -> None:
    assert (FIXTURES / "orders.dtrx").exists()


def test_nearest() -> None:
    assert (FIXTURES / "one" / "system.dtrx").exists()
    assert (FIXTURES / "system.dtrx").exists()


def test_shared_and_written(tmp_path: Path) -> None:
    assert "shared.dtrx" and (tmp_path / "scratch.dcfg")
'''

_INLINE: Final = '''DTRX = "service Inline {\\n  entity Item {\\n  }\\n}\\n"


def test_inline() -> None:
    assert DTRX
'''

_SYNTAX_PROBE: Final = '''BROKEN = "service Broken {\\n  entity {\\n"


def test_broken_is_refused() -> None:
    assert BROKEN
'''

_SHARED_NAME: Final = '''from datrix_testing import fixture_names
from datrix_testing.fixture_names import FIXTURE_SYSTEM_BASIC as BASIC


def test_basic() -> None:
    assert BASIC and fixture_names.FIXTURE_SYSTEM_WITH_API
'''

_CONFTEST: Final = '''from datrix_testing.conftest_plugin import FixturePairSpec
from datrix_testing.fixture_names import FIXTURE_SYSTEM_BASIC

NAME_AT_RUN_TIME = "computed".upper()
SPECS = [
    FixturePairSpec("orders", "orders.dtrx"),
    FixturePairSpec(name="basic", dtrx_filename=FIXTURE_SYSTEM_BASIC),
    FixturePairSpec("computed", NAME_AT_RUN_TIME),
]
'''

_PAIR: Final = '''import pytest


def test_orders(app_with_orders: object) -> None:
    assert app_with_orders


def test_basic(request: pytest.FixtureRequest) -> None:
    assert request.getfixturevalue("service_with_basic")


def test_computed(app_with_computed: object) -> None:
    assert app_with_computed


def test_hand_written(app_with_unregistered: object) -> None:
    assert app_with_unregistered
'''

_DEEP_CONFTEST: Final = '''from datrix_testing.conftest_plugin import FixturePairSpec

SPECS = [FixturePairSpec("orders", "deep-orders.dtrx")]
'''

_DEEP: Final = '''def test_deep(app_with_orders: object) -> None:
    assert app_with_orders
'''

_NO_INPUT: Final = '''def test_nothing() -> None:
    assert "orders"
'''

_ORDERS_TEXT: Final = "service Orders {\n}\n"

_CLASS_TESTS: Final = '''FIXTURE = "orders.dtrx"


class TestOrders:
    def test_a(self) -> None:
        assert FIXTURE

    class TestNested:
        def test_b(self) -> None:
            assert FIXTURE

    def helper(self) -> None:
        return None


class Helper:
    def test_not_collected(self) -> None:
        assert FIXTURE
'''

#: ``(module, form, name, lines, resolved file or None, unresolved reason or None)``.
_Row = tuple[str, str, str, tuple[int, ...], str | None, "Unresolved | None"]


def _line(source: str, fragment: str) -> int:
    """The 1-based line of *source* holding *fragment*, which must occur on exactly one line."""
    lines = [number for number, text in enumerate(source.splitlines(), start=1) if fragment in text]
    assert len(lines) == 1, f"{fragment!r} occurs on lines {lines}"
    return lines[0]


@contextmanager
def _planted_workspace() -> Iterator[Path]:
    from datrix_testing.fixture_names import FIXTURE_SYSTEM_BASIC

    from datrix_scripts.gates.ratchet.fixture_budget_gate import SHARED_FIXTURES_RELATIVE, SHARED_PACKAGE

    tests = f"{_PACKAGE}/tests"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_files(root, {
            f"{tests}/fixtures/orders.dtrx": _ORDERS_TEXT,
            f"{tests}/fixtures/{FIXTURE_SYSTEM_BASIC}": "system Basic {\n}\n",
            f"{tests}/fixtures/one/system.dtrx": "system One {\n}\n",
            f"{tests}/fixtures/two/system.dtrx": "system Two {\n}\n",
            f"{tests}/deep/fixtures/deep-orders.dtrx": "service DeepOrders {\n}\n",
            f"{tests}/conftest.py": _CONFTEST,
            f"{tests}/deep/conftest.py": _DEEP_CONFTEST,
            f"{tests}/deep/test_deep.py": _DEEP,
            f"{tests}/unit/test_reads_file.py": _READS_FILE,
            f"{tests}/unit/test_inline.py": _INLINE,
            f"{tests}/unit/test_syntax_probe.py": _SYNTAX_PROBE,
            f"{tests}/unit/test_shared_name.py": _SHARED_NAME,
            f"{tests}/unit/test_pair.py": _PAIR,
            f"{tests}/unit/test_none.py": _NO_INPUT,
            f"{(Path(SHARED_PACKAGE) / SHARED_FIXTURES_RELATIVE).as_posix()}/{_SHARED_FILE}": "service Shared {\n}\n",
            "datrix-beta/src/datrix_beta/__init__.py": "",
            "other/tests/test_outside.py": 'NAME = "orders.dtrx"\n',
        })
        yield root


def _rows(found: list[ModuleInputs], root: Path) -> list[_Row]:
    rows: list[_Row] = []
    for module in found:
        for each in module.inputs:
            resolved = None if each.path is None else each.path.relative_to(root).as_posix()
            rows.append((module.module.relative_to(root).as_posix(), each.form.value, each.name, each.lines,
                         resolved, each.unresolved))
    return rows


def _expected_rows() -> list[_Row]:
    from datrix_testing.fixture_names import FIXTURE_SYSTEM_BASIC

    from datrix_scripts.dev.fixture_author.needs import InputForm, Unresolved
    from datrix_scripts.gates.ratchet.fixture_budget_gate import SHARED_FIXTURES_RELATIVE, SHARED_PACKAGE

    tests = f"{_PACKAGE}/tests"
    fixtures = f"{tests}/fixtures"
    basic = f"{fixtures}/{FIXTURE_SYSTEM_BASIC}"
    shared = f"{(Path(SHARED_PACKAGE) / SHARED_FIXTURES_RELATIVE).as_posix()}/{_SHARED_FILE}"
    file, pair, name, inline = InputForm.FILE, InputForm.PAIR, InputForm.SHARED_NAME, InputForm.INLINE
    return [
        (f"{tests}/conftest.py", file, "orders.dtrx", (_line(_CONFTEST, '"orders.dtrx"'),), f"{fixtures}/orders.dtrx", None),
        (f"{tests}/conftest.py", name, "FIXTURE_SYSTEM_BASIC", (_line(_CONFTEST, "dtrx_filename=FIXTURE"),), basic, None),
        (f"{tests}/deep/conftest.py", file, "deep-orders.dtrx", (_line(_DEEP_CONFTEST, "deep-orders"),),
         f"{tests}/deep/fixtures/deep-orders.dtrx", None),
        (f"{tests}/deep/test_deep.py", pair, "app_with_orders", (1,), f"{tests}/deep/fixtures/deep-orders.dtrx", None),
        (f"{tests}/unit/test_inline.py", inline, "line 1", (1,), None, None),
        (f"{tests}/unit/test_pair.py", pair, "app_with_computed", (_line(_PAIR, "def test_computed"),), None,
         Unresolved.COMPUTED),
        (f"{tests}/unit/test_pair.py", pair, "app_with_orders", (_line(_PAIR, "def test_orders"),),
         f"{fixtures}/orders.dtrx", None),
        (f"{tests}/unit/test_pair.py", pair, "service_with_basic", (_line(_PAIR, '"service_with_basic"'),), basic, None),
        (f"{tests}/unit/test_reads_file.py", file, "one/system.dtrx", (_line(_READS_FILE, '"one"'),),
         f"{fixtures}/one/system.dtrx", None),
        (f"{tests}/unit/test_reads_file.py", file, "orders.dtrx", (_line(_READS_FILE, '/ "orders.dtrx"'),),
         f"{fixtures}/orders.dtrx", None),
        (f"{tests}/unit/test_reads_file.py", file, "scratch.dcfg", (_line(_READS_FILE, "scratch"),), None,
         Unresolved.NOT_FOUND),
        (f"{tests}/unit/test_reads_file.py", file, "shared.dtrx", (_line(_READS_FILE, "scratch"),), shared, None),
        (f"{tests}/unit/test_reads_file.py", file, "system.dtrx", (_line(_READS_FILE, 'FIXTURES / "system.dtrx"'),),
         None, Unresolved.AMBIGUOUS),
        (f"{tests}/unit/test_shared_name.py", name, "FIXTURE_SYSTEM_BASIC", (_line(_SHARED_NAME, "assert BASIC"),),
         basic, None),
        (f"{tests}/unit/test_shared_name.py", name, "FIXTURE_SYSTEM_WITH_API", (_line(_SHARED_NAME, "assert BASIC"),),
         None, Unresolved.NOT_FOUND),
        (f"{tests}/unit/test_syntax_probe.py", inline, "line 1", (1,), None, None),
    ]


def _check_every_input_form_is_found_and_resolved() -> None:
    from datrix_scripts.dev.fixture_author.needs import needs_packages, workspace_inputs

    with _planted_workspace() as root:
        packages = needs_packages(root)
        found = workspace_inputs(root, packages)
        rows = _rows(found, root)
    assert [package.name for package in packages] == [_PACKAGE], f"only packages with tests/: {packages}"
    expected = _expected_rows()
    missing = [row for row in expected if row not in rows]
    unexpected = [row for row in rows if row not in expected]
    assert not missing and not unexpected, f"missing {missing}; unexpected {unexpected}"
    assert rows == expected, f"inputs are listed by module, then form and name, inline last: {rows}"


def _check_inputs_carry_the_text_read() -> None:
    from datrix_scripts.dev.fixture_author.needs import InputForm, package_inputs

    with _planted_workspace() as root:
        found = {each.module.name: each.inputs for each in package_inputs(root / _PACKAGE, root)}
    orders = next(each for each in found["test_reads_file.py"] if each.name == "orders.dtrx")
    assert orders.text == _ORDERS_TEXT, f"a resolved file carries its text: {orders.text!r}"
    (inline,) = found["test_inline.py"]
    assert inline.form is InputForm.INLINE and inline.text.startswith("service Inline {"), inline
    unresolved = [each for each in found["test_reads_file.py"] if each.path is None]
    assert unresolved and all(each.text == "" for each in unresolved), "an unresolved name carries no text"


def _check_an_unparsable_module_or_a_missing_shared_root_stops_discovery() -> None:
    from datrix_scripts.dev.fixture_author.needs import NeedsScanError, package_inputs
    from datrix_scripts.gates.ratchet.fixture_budget_gate import SHARED_PACKAGE, FixtureScanError

    with _planted_workspace() as root:
        write_files(root, {f"{_PACKAGE}/tests/unit/test_bad.py": "def broken(:\n"})
        try:
            package_inputs(root / _PACKAGE, root)
        except FixtureScanError as exc:
            assert "test_bad.py" in str(exc), exc
        else:
            raise AssertionError("an unparsable test module is refused, never skipped")
    with _planted_workspace() as root:
        shutil.rmtree(root / SHARED_PACKAGE)
        try:
            package_inputs(root / _PACKAGE, root)
        except NeedsScanError as exc:
            assert "shared fixture directory" in str(exc), exc
        else:
            raise AssertionError("a missing shared fixture directory is refused")


def _check_the_tree_readers_exist_and_a_moved_one_is_named() -> None:
    from datrix_scripts.dev.fixture_author.needs import TREE_READERS, tree_reader_failures
    from datrix_scripts.paths import WORKSPACE_DIR

    assert tree_reader_failures(WORKSPACE_DIR) == [], tree_reader_failures(WORKSPACE_DIR)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first, *rest = TREE_READERS
        write_files(root, {first.module: "def renamed() -> int:\n    return 1\n"})
        failures = tree_reader_failures(root)
    assert len(failures) == len(TREE_READERS), failures
    assert first.symbol in failures[0] and "renamed" in failures[0], failures[0]
    assert all(reader.module in message for reader, message in zip(rest, failures[1:], strict=True)), failures


def _asked_module(chat: Chat) -> str:
    from datrix_scripts.dev.fixture_author.needs_reading import MODULE_LABEL

    return chat.user.split(f"{MODULE_LABEL}: ", 1)[1].splitlines()[0]


def _asked_tests(chat: Chat) -> list[str]:
    from datrix_scripts.dev.fixture_author.needs_reading import BULLET, TESTS_HEADING

    listed = chat.user.split(f"{TESTS_HEADING}:\n", 1)[1].splitlines()
    return [line.removeprefix(BULLET) for line in takewhile(lambda line: line.startswith(BULLET), listed)]


def _declared(kind: str) -> list[dict[str, object]]:
    return [{"kind": kind, "path": _DECLARED_PATH, "facts": list(_DECLARED_FACTS)}]


def _answer_text(tests: Sequence[str], declarations: list[dict[str, object]], local: str | None) -> str:
    return json.dumps({"tests": [{"name": name, "declarations": declarations, "local": local} for name in tests]})


def _planted_answer(chat: Chat) -> str:
    """Every test declares one known node; the syntax probe's tests declare nothing and say why it is local."""
    if _asked_module(chat).endswith(_PROBE_MODULE):
        return _answer_text(_asked_tests(chat), [], _SYNTAX_LOCAL)
    return _answer_text(_asked_tests(chat), _declared(_KNOWN_KIND), None)


def _reader(root: Path, server: LoopbackOllama, content: ContentFilter) -> NeedsReader:
    from datrix_scripts.dev.fixture_author.needs_reading import NeedsReader
    from datrix_scripts.local_llm import LocalLlmPool

    return NeedsReader(root, LocalLlmPool(server.settings(_CALLER), report=lambda _line: None), content,
                       cache_dir=root / _CACHE)


def _found(root: Path, names: frozenset[str] = frozenset()) -> list[ModuleInputs]:
    from datrix_scripts.dev.fixture_author.needs import needs_packages, workspace_inputs

    found = workspace_inputs(root, needs_packages(root))
    return [each for each in found if not names or each.module.name in names]


def _check_answers_are_parsed_per_test_and_a_cached_rerun_asks_nothing() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import (
        MIN_CONTEXT_TOKENS,
        NEEDS_TEMPERATURE,
        Declaration,
        module_tests,
        read_needs,
    )
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    content = ContentFilter(WORKSPACE_DIR)
    with _planted_workspace() as root:
        write_files(root, {f"{_PACKAGE}/tests/unit/test_class.py": _CLASS_TESTS})
        found = _found(root)
        with_tests = {each.module.relative_to(root).as_posix(): each for each in found
                      if module_tests(_parsed(each.module))}
        with LoopbackOllama(_planted_answer) as server:
            first = read_needs(_reader(root, server, content), found)
            asked = list(server.chats)
            second = read_needs(_reader(root, server, content), found)
            rerun_chats = server.chats[len(asked):]
        cached = sorted(path.name for path in (root / _CACHE).iterdir())
    assert first.refused == (), first.refused
    assert [each.found.module for each in first.needs] == [each.module for each in found], "every module, in order"
    assert sorted(_asked_module(chat) for chat in asked) == sorted(with_tests), "each module with a test asked once"
    assert len(cached) == len(asked), f"each kept answer is cached: {cached}"
    assert rerun_chats == [] and second == first, f"a cached rerun asks nothing and reads the same: {rerun_chats}"
    needs = {each.found.module.relative_to(root).as_posix(): each.tests for each in first.needs}
    unit = f"{_PACKAGE}/tests/unit"
    assert needs[f"{_PACKAGE}/tests/conftest.py"] == (), "a module with no test function needs nothing"
    assert [test.name for test in needs[f"{unit}/test_class.py"]] == ["TestOrders.test_a", "TestOrders.TestNested.test_b"]
    assert [test.name for test in needs[f"{unit}/test_pair.py"]] == [
        "test_orders", "test_basic", "test_computed", "test_hand_written"], "tests in source order"
    (probe,) = needs[f"{unit}/{_PROBE_MODULE}"]
    assert probe.local == _SYNTAX_LOCAL and probe.declarations == (), f"the syntax probe is local, with why: {probe}"
    (inline,) = needs[f"{unit}/{_INLINE_MODULE}"]
    facts = tuple(sorted(set(_DECLARED_FACTS)))
    assert inline.declarations == (Declaration(_KNOWN_KIND, _DECLARED_PATH, facts),) and inline.local is None, inline
    _assert_requests(asked, unit, NEEDS_TEMPERATURE, MIN_CONTEXT_TOKENS)


def _parsed(module: Path) -> ast.Module:
    return ast.parse(module.read_text(encoding="utf-8"))


def _assert_requests(asked: Sequence[Chat], unit: str, temperature: float, min_context: int) -> None:
    """The reads-file module is sent its source and its inputs' text, unresolved ones named as such, to the
    schema naming its tests, unsampled, in a context holding the prompt."""
    from datrix_common.config.dcfg.ast_nodes import ConfigDecl

    from datrix_scripts.dev.fixture_author.needs_reading import KINDS_HEADING

    (chat,) = [chat for chat in asked if _asked_module(chat) == f"{unit}/test_reads_file.py"]
    assert "def test_orders" in chat.user and _ORDERS_TEXT.splitlines()[0] in chat.user, "source and input text sent"
    assert "scratch.dcfg" in chat.user and "not read" in chat.user, "an unresolved input is named, not dropped"
    assert f"{KINDS_HEADING}: " in chat.system and ConfigDecl.__name__ in chat.system, "the kinds are offered"
    options = chat.body["options"]
    assert isinstance(options, dict) and options["temperature"] == temperature, options
    assert isinstance(options["num_ctx"], int) and options["num_ctx"] >= min_context, options
    schema = json.dumps(chat.body["format"])
    assert '"enum": ["test_orders", "test_nearest", "test_shared_and_written"]' in schema, schema


def _check_an_unknown_kind_or_test_goes_back_once_then_the_module_is_refused() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import FEEDBACK_HEADING, read_needs
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    def answer(chat: Chat) -> str:
        tests = _asked_tests(chat)
        if _asked_module(chat).endswith(_PROBE_MODULE):
            return _answer_text(tests, _declared(_UNKNOWN_KIND), None)
        if FEEDBACK_HEADING in chat.user:
            return _answer_text(tests, _declared(_KNOWN_KIND), None)
        return _answer_text([*tests, _GHOST_TEST], _declared(_UNKNOWN_KIND), None)

    content = ContentFilter(WORKSPACE_DIR)
    with _planted_workspace() as root:
        found = _found(root, frozenset({_PROBE_MODULE, _INLINE_MODULE}))
        with LoopbackOllama(answer) as server:
            reading = read_needs(_reader(root, server, content), found)
            chats = list(server.chats)
            cached = sorted((root / _CACHE).iterdir())
            again = read_needs(_reader(root, server, content), found)
            rerun = server.chats[len(chats):]
    inline_chats = [chat for chat in chats if _asked_module(chat).endswith(_INLINE_MODULE)]
    probe_chats = [chat for chat in chats if _asked_module(chat).endswith(_PROBE_MODULE)]
    assert (len(inline_chats), len(probe_chats)) == (2, 2), "each failing answer goes back exactly once"
    feedback = inline_chats[1].user.split(FEEDBACK_HEADING, 1)[1]
    assert _UNKNOWN_KIND in feedback and _GHOST_TEST in feedback, "the resend names the unknown kind and test"
    ((inline,),) = [each.tests for each in reading.needs]
    assert inline.declarations[0].kind == _KNOWN_KIND, inline
    (refused,) = reading.refused
    assert refused.module.name == _PROBE_MODULE and any(_UNKNOWN_KIND in each for each in refused.problems), refused
    assert len(cached) == 1, f"a refused answer is never cached: {cached}"
    assert again == reading and [_asked_module(chat) for chat in rerun] == [_asked_module(probe_chats[0])] * 2, (
        "on a rerun the kept answer is read back and only the refused module is asked again")


def _check_no_local_model_stops_the_reading_and_caches_nothing() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import read_needs
    from datrix_scripts.local_llm import LocalLlmUnavailable
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    outage = ""
    with _planted_workspace() as root, LoopbackOllama(answering("{}"), models=()) as server:
        try:
            read_needs(_reader(root, server, ContentFilter(WORKSPACE_DIR)), _found(root))
        except LocalLlmUnavailable as exc:
            outage = str(exc)
        else:
            raise AssertionError("no local model stops the reading; nothing falls back")
        cache_written = (root / _CACHE).exists()
    assert outage and server.chats == [] and not cache_written, (outage, server.chats, cache_written)


def _padded_inline(prompt_tokens: int) -> str:
    """The inline-literal module, its source grown by comment lines to about *prompt_tokens* tokens (short
    lines: the content filter caps a line's length)."""
    from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN

    line = f"# {'pad ' * 19}\n"
    return _INLINE + line * (prompt_tokens * CHARS_PER_TOKEN // len(line))


def _num_ctx(chat: Chat) -> int:
    options = chat.body["options"]
    assert isinstance(options, dict) and isinstance(options["num_ctx"], int), options
    return options["num_ctx"]


def _check_a_run_sends_one_context_window_and_caches_each_answer_as_it_arrives() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import (
        ANSWER_TOKENS,
        CONTEXT_STEP_TOKENS,
        FEEDBACK_HEADING,
        MIN_CONTEXT_TOKENS,
        context_window,
        read_needs,
        run_window,
    )
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    assert run_window([]) == MIN_CONTEXT_TOKENS
    assert run_window([("", "")]) == max(MIN_CONTEXT_TOKENS, 2 * ANSWER_TOKENS)
    base = MIN_CONTEXT_TOKENS - ANSWER_TOKENS
    cached_at_resend: list[int] = []
    with _planted_workspace() as root:
        write_files(root, {
            f"{_PACKAGE}/tests/unit/test_wider.py": _padded_inline(base + CONTEXT_STEP_TOKENS * 3 // 2),
            f"{_PACKAGE}/tests/unit/test_wide.py": _padded_inline(base + CONTEXT_STEP_TOKENS // 2),
        })
        cache = root / _CACHE

        def answer(chat: Chat) -> str:
            """The wide module's first answer names an unknown kind, so it is resent after every first answer."""
            if FEEDBACK_HEADING in chat.user:
                cached_at_resend.append(len(list(cache.iterdir())))
            elif _asked_module(chat).endswith("test_wide.py"):
                return _answer_text(_asked_tests(chat), _declared(_UNKNOWN_KIND), None)
            return _planted_answer(chat)

        with LoopbackOllama(answer) as server:
            reading = read_needs(_reader(root, server, ContentFilter(WORKSPACE_DIR)), _found(root))
            chats = list(server.chats)
            loads = list(server.generate_bodies)
    assert reading.refused == (), reading.refused
    first = [chat for chat in chats if FEEDBACK_HEADING not in chat.user]
    own = sorted({context_window(chat.system, chat.user) for chat in first})
    assert len(own) >= 3, f"the planted modules each need a window of their own: {own}"
    windows = {_num_ctx(chat) for chat in chats}
    assert windows == {own[-1] + ANSWER_TOKENS}, (
        f"every request, the resend included, goes out in one window holding the largest prompt and a resend: "
        f"{windows}, own windows {own}")
    assert [load.get("options") for load in loads] == [{"num_ctx": own[-1] + ANSWER_TOKENS}], (
        f"the model is loaded once, in the window every request carries, before the first request: {loads}")
    assert cached_at_resend == [len(first) - 1], (
        f"each clean first answer is cached as it arrives, before the resend: {cached_at_resend} of {len(first)}")


_CUT_OFF_ANSWER: Final = '{"tests": [{"name": "test_inline", "declarations": ['
_PARTS_AT_MOST: Final = 2


def _check_a_module_whose_answer_is_cut_off_is_asked_in_halves_and_kept_whole() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import ModuleNeeds, read_needs
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    tests = 6
    source = _INLINE + "".join(f"\n\ndef test_more_{n}() -> None:\n    assert DTRX\n" for n in range(tests - 1))

    def answer(chat: Chat) -> str:
        """An answer for more than ``_PARTS_AT_MOST`` test functions is cut off, as one past the token cap is."""
        return _CUT_OFF_ANSWER if len(_asked_tests(chat)) > _PARTS_AT_MOST else _planted_answer(chat)

    with _planted_workspace() as root:
        write_files(root, {f"{_PACKAGE}/tests/unit/test_many.py": source})
        found = _found(root, frozenset({"test_many.py"}))
        content = ContentFilter(WORKSPACE_DIR)
        with LoopbackOllama(answer) as server:
            reading = read_needs(_reader(root, server, content), found)
            asked = sorted({len(_asked_tests(chat)) for chat in server.chats})
        assert reading.refused == (), reading.refused
        [module] = reading.needs
        assert [each.name for each in module.tests] == ["test_inline", *(f"test_more_{n}" for n in range(tests - 1))], \
            f"the parts' answers are joined in source order: {[each.name for each in module.tests]}"
        assert asked == [1, 2, 3, 6], f"a request is halved until its answer is not cut off: {asked}"
        with LoopbackOllama(answer) as server:
            again = read_needs(_reader(root, server, content), found)
            assert server.chats == [], f"the joined answer is kept as the whole module's: {server.chats}"
        assert again.needs == (ModuleNeeds(module.found, module.tests),), "a rerun reads back the same needs"

        write_files(root, {f"{_PACKAGE}/tests/unit/test_many.py": _INLINE})
        with LoopbackOllama(lambda _chat: _CUT_OFF_ANSWER) as server:
            refused = read_needs(_reader(root, server, content), _found(root, frozenset({"test_many.py"}))).refused
    assert len(refused) == 1 and "valid JSON" in refused[0].problems[0], (
        f"a single test function cut off cannot be halved and is refused: {refused}")


def _check_declarations_with_one_path_and_kind_are_ordered_by_their_facts() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import parse_needs

    same = [{"kind": _KNOWN_KIND, "path": _DECLARED_PATH, "facts": [fact]} for fact in ("type Integer", "min(0)", "a")]
    for declarations in (same, same[::-1], same[1:] + same[:1]):
        [test] = parse_needs(json.loads(_answer_text(["test_a"], declarations, None)), ["test_a"])
        assert [each.facts for each in test.declarations] == [("a",), ("min(0)",), ("type Integer",)], (
            f"a set's order varies from one process to the next, so the order is the declarations' own: "
            f"{[each.facts for each in test.declarations]}")


def _check_an_unnamed_declaration_is_told_how_to_be_named() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import answer_problems, node_kinds

    tests = ["test_a"]
    unnamed = json.loads(_answer_text(tests, [{"kind": _KNOWN_KIND, "path": "", "facts": ["declared"]}], None))
    [problem] = answer_problems(unnamed, node_kinds(), tests)
    assert "no qualified name" in problem and "enclosing" in problem, (
        f"the resend tells the model what an unnamed declaration's path is: {problem}")

    from datrix_scripts.dev.fixture_author.needs_reading import FEEDBACK_HEADING, read_needs
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    def answer(chat: Chat) -> str:
        """The first answer leaves the path empty; the resend, constrained to a named path, names it."""
        path = _DECLARED_PATH if FEEDBACK_HEADING in chat.user else ""
        return _answer_text(_asked_tests(chat), [{"kind": _KNOWN_KIND, "path": path, "facts": ["declared"]}], None)

    with _planted_workspace() as root, LoopbackOllama(answer) as server:
        reading = read_needs(_reader(root, server, ContentFilter(WORKSPACE_DIR)),
                             _found(root, frozenset({_INLINE_MODULE})))
        chats = list(server.chats)
    assert reading.refused == (), reading.refused

    def path_schema(chat: Chat) -> dict[str, object]:
        [schema] = [chat.body["format"]]
        return schema["properties"]["tests"]["items"]["properties"]["declarations"]["items"]["properties"]["path"]

    first, resend = chats
    assert "minLength" not in path_schema(first) and path_schema(resend)["minLength"] == 1, (
        "only the resend forbids an empty path (the first schema is part of every cached answer's key)")


def _check_kinds_are_the_model_node_classes_and_the_context_holds_the_prompt() -> None:
    from datrix_common.config.dcfg.ast_nodes import ConfigDecl
    from datrix_common.datrix_model.base import Node

    from datrix_scripts.dev.fixture_author.needs_reading import (
        ANSWER_TOKENS,
        CONTEXT_STEP_TOKENS,
        MIN_CONTEXT_TOKENS,
        answer_problems,
        context_window,
        node_kinds,
    )
    from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN

    kinds = node_kinds()
    named = ("Service", "RdbmsBlock", "Entity", "Field", "Endpoint", "CacheBlock", ConfigDecl.__name__)
    assert all(kind in kinds for kind in named), [kind for kind in named if kind not in kinds]
    assert list(kinds) == sorted(kinds) and not [kind for kind in kinds if kind.startswith("_")], list(kinds)
    assert all(issubclass(each, (Node, ConfigDecl)) for each in kinds.values()), "every kind is a node class"
    assert context_window("", "") == MIN_CONTEXT_TOKENS
    large = context_window("", "x" * (CHARS_PER_TOKEN * MIN_CONTEXT_TOKENS * 2))
    assert large >= MIN_CONTEXT_TOKENS * 2 + ANSWER_TOKENS and large % CONTEXT_STEP_TOKENS == 0, large
    tests = ["test_a"]
    good = json.loads(_answer_text(tests, _declared(_KNOWN_KIND), None))
    assert answer_problems(good, kinds, tests) == []
    for broken in ({"tests": "none"}, {"tests": [], "extra": 1}, json.loads(_answer_text(tests, _declared(_KNOWN_KIND), ""))):
        assert answer_problems(broken, kinds, tests), f"refused: {broken}"


#: What every planted test with a declaration needs: blocks enclosing what lies under them, and two
#: declarations (the service, its configuration) under no block.
_BLOCK_DECLARATIONS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Service", "shop.Orders", "service Orders"),
    ("RdbmsBlock", "shop.Orders.db", "rdbms db"),
    ("Entity", "shop.Orders.db.Order", "entity Order"),
    ("Field", "shop.Orders.db.Order.total", "type Decimal"),
    ("CacheBlock", "shop.Orders.cache", "cache cache"),
    ("Field", "shop.Orders.cache.ttl", "seconds 60"),
    ("ConfigDecl", "shop.Orders.config", "profile test"),
    ("RestApi", "shop.Orders.OrdersApi", "rest_api OrdersApi"),
    ("Endpoint", "shop.Orders.OrdersApi.getOrder", "route GET /orders/{id}"),
    ("IdentityBlock", "shop.Orders.identity", "provider jwt"),
)
_FAMILY_LINES: Final = (
    "family api: Endpoint, RestApi",
    "family cache: CacheBlock, Field",
    "family identity: IdentityBlock",
    "family rdbms: Entity, Field, RdbmsBlock",
)


def _block_answer(chat: Chat) -> str:
    """Every test needs ``_BLOCK_DECLARATIONS``; the syntax probe's tests need nothing and say why they are local."""
    if _asked_module(chat).endswith(_PROBE_MODULE):
        return _answer_text(_asked_tests(chat), [], _SYNTAX_LOCAL)
    declared: list[dict[str, object]] = [
        {"kind": kind, "path": path, "facts": [fact]} for kind, path, fact in _BLOCK_DECLARATIONS
    ]
    return _answer_text(_asked_tests(chat), declared, None)


def _listed_tests_answer(chat: Chat) -> str:
    return _answer_text(_asked_tests(chat), [], None)


def _summary_line(found: Sequence[ModuleInputs]) -> str:
    """The summary line ``_block_answer`` gives the planted package."""
    from datrix_scripts.dev.fixture_author.needs_reading import module_tests

    tests = {each.module.name: module_tests(_parsed(each.module)) for each in found}
    local = len(tests.get(_PROBE_MODULE, ()))
    declaring = sum(len(names) for name, names in tests.items() if name != _PROBE_MODULE)
    declarations = declaring * len(_BLOCK_DECLARATIONS)
    paths = len({path for _kind, path, _fact in _BLOCK_DECLARATIONS}) if declaring else 0
    inputs = sum(len(each.inputs) for each in found)
    return (f"{_PACKAGE}: {len(found)} module(s), {inputs} input(s) read, {declarations} declaration(s) needed, "
            f"{paths} distinct path(s), {local} local test(s)")


def _rows_of(rendered: bytes) -> list[dict[str, object]]:
    document = json.loads(rendered.decode("utf-8"))
    assert isinstance(document, dict) and list(document) == ["rows"], document
    rows = document["rows"]
    assert isinstance(rows, list), rows
    return rows


def _check_the_inventory_is_written_whole_sorted_and_identical_on_a_rerun() -> None:
    from datrix_scripts.dev.fixture_author.needs import needs_packages
    from datrix_scripts.dev.fixture_author.needs_command import MODULE_ROW, render, run_needs
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    content = ContentFilter(WORKSPACE_DIR)
    printed = io.StringIO()
    with _planted_workspace() as root:
        packages, found = needs_packages(root), _found(root)
        out = root / "out"
        with LoopbackOllama(_block_answer) as server, redirect_stdout(printed):
            codes = [run_needs(_reader(root, server, content), packages, out / "first.json")]
            asked = len(server.chats)
            codes.append(run_needs(_reader(root, server, content), packages, out / "second.json"))
            rerun_chats = server.chats[asked:]
            fresh = dataclasses.replace(_reader(root, server, content), cache_dir=root / "fresh-cache")
            codes.append(run_needs(fresh, packages, out / "fresh.json"))
        first, second, uncached = (out / name for name in ("first.json", "second.json", "fresh.json"))
        texts = [path.read_bytes() for path in (first, second, uncached)]
        labels = sorted(each.module.relative_to(root).as_posix() for each in found)
        summary = _summary_line(found)
    assert codes == [0, 0, 0], codes
    assert rerun_chats == [] and texts[0] == texts[1] == texts[2], "a rerun, cached or not, writes the same bytes"
    rows = _rows_of(texts[0])
    assert [row["module"] for row in rows] == labels and {row["kind"] for row in rows} == {MODULE_ROW}, rows
    assert render({"rows": rows}) == texts[0], "keys sorted, fixed separators, one trailing newline"
    lines = printed.getvalue().splitlines()
    assert summary in lines, lines
    assert [line for line in lines if line.startswith("family ")] == list(_FAMILY_LINES) * 3, lines


def _check_a_module_not_inventoried_is_named_and_nothing_is_written() -> None:
    from datrix_scripts.dev.fixture_author.needs import needs_packages
    from datrix_scripts.dev.fixture_author.needs_command import (
        EXIT_INCOMPLETE,
        needs_document,
        render,
        run_needs,
        uninventoried,
    )
    from datrix_scripts.dev.fixture_author.needs_reading import ModuleNeeds, NeedsReading
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    def answer(chat: Chat) -> str:
        if _asked_module(chat).endswith(_PROBE_MODULE):
            return _answer_text(_asked_tests(chat), _declared(_UNKNOWN_KIND), None)
        return _planted_answer(chat)

    printed = io.StringIO()
    with _planted_workspace() as root:
        found = _found(root)
        whole = NeedsReading(tuple(ModuleNeeds(each, ()) for each in found), ())
        dropped = dataclasses.replace(whole, needs=whole.needs[1:])
        assert uninventoried(found, render(needs_document(whole, (), root)), root) == []
        missing = uninventoried(found, render(needs_document(dropped, (), root)), root)
        assert missing == [found[0].module.relative_to(root).as_posix()], missing
        output = root / "needs.json"
        with LoopbackOllama(answer) as server, redirect_stdout(printed):
            code = run_needs(_reader(root, server, ContentFilter(WORKSPACE_DIR)), needs_packages(root), output)
        written = output.exists()
        probe = next(each for each in found if each.module.name == _PROBE_MODULE).module.relative_to(root).as_posix()
    report = printed.getvalue()
    assert code == EXIT_INCOMPLETE and not written, (code, written)
    assert f"{probe}: " in report and _UNKNOWN_KIND in report, f"the refused module is named, with why: {report}"


def _check_no_local_model_exits_3_and_writes_nothing() -> None:
    from datrix_scripts.dev.fixture_author.needs import needs_packages
    from datrix_scripts.dev.fixture_author.needs_command import run_needs
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import EXIT_NO_MODEL, ContentFilter

    with _planted_workspace() as root, LoopbackOllama(answering("{}"), models=()) as server:
        output = root / "needs.json"
        with redirect_stdout(io.StringIO()):
            code = run_needs(_reader(root, server, ContentFilter(WORKSPACE_DIR)), needs_packages(root), output)
        written = output.exists()
    assert code == EXIT_NO_MODEL and not written, (code, written)


def _check_the_package_is_optional_and_a_non_package_is_a_usage_error() -> None:
    from datrix_scripts.dev.fixture_author.cli import NEEDS_KIND, main
    from datrix_scripts.dev.fixture_author.needs_command import select_packages
    from datrix_scripts.gate_harness import expect_usage_error

    with _planted_workspace() as root:
        every = [package.name for package in select_packages(root, "")]
        named = [package.name for package in select_packages(root, _PACKAGE)]
        expect_usage_error(lambda: select_packages(root, "datrix-beta"), "datrix-beta")
    assert every == named == [_PACKAGE], (every, named)
    assert main(["--kind", NEEDS_KIND, "--package", "datrix-no-such-package"]) == 2
    assert main(["--kind", NEEDS_KIND, "--plan"]) == 2, "an option only diagnostics reads is refused"


def _check_block_families_are_the_block_classes() -> None:
    from datrix_common.datrix_model.base import Block, QualifiedBlock

    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds

    families = block_families(node_kinds())
    assert families["RdbmsBlock"] == "rdbms" and families["CacheBlock"] == "cache", families
    assert families["IdentityBlock"] == "identity", families
    assert {families[kind] for kind in ("RestApi", "GraphqlApi", "WebsocketApi")} == {"api"}, families
    assert Block.__name__ not in families and QualifiedBlock.__name__ not in families, families
    assert "Service" not in families and "Entity" not in families, families


def _check_the_real_tree_is_inventoried_whole() -> None:
    from datrix_scripts.dev.fixture_author.needs import TREE_READERS, needs_packages
    from datrix_scripts.dev.fixture_author.needs_command import MODULE_ROW, TREE_ROW, build_inventory
    from datrix_scripts.dev.fixture_author.needs_reading import NeedsReader
    from datrix_scripts.local_llm import LocalLlmPool
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    content = ContentFilter(WORKSPACE_DIR)
    with tempfile.TemporaryDirectory() as tmp, LoopbackOllama(_listed_tests_answer) as server:
        pool = LocalLlmPool(server.settings(_CALLER), report=lambda _line: None)
        inventory = build_inventory(NeedsReader(WORKSPACE_DIR, pool, content, cache_dir=Path(tmp)),
                                    needs_packages(WORKSPACE_DIR))
    rows = _rows_of(inventory.rendered)
    inventoried = {row["module"] for row in rows if row["kind"] == MODULE_ROW}
    found = {each.module.relative_to(WORKSPACE_DIR).as_posix() for each in inventory.found}
    assert inventory.missing == () and inventory.reading.refused == (), (inventory.missing, inventory.reading.refused)
    assert found and inventoried == found, f"found − inventoried {sorted(found - inventoried)[:5]}"
    trees = sorted(str(row["module"]) for row in rows if row["kind"] == TREE_ROW)
    assert trees == sorted(reader.module for reader in TREE_READERS), trees


CHECKS: Final[list[CheckFunc]] = [
    _check_every_input_form_is_found_and_resolved,
    _check_inputs_carry_the_text_read,
    _check_an_unparsable_module_or_a_missing_shared_root_stops_discovery,
    _check_the_tree_readers_exist_and_a_moved_one_is_named,
    _check_answers_are_parsed_per_test_and_a_cached_rerun_asks_nothing,
    _check_an_unknown_kind_or_test_goes_back_once_then_the_module_is_refused,
    _check_no_local_model_stops_the_reading_and_caches_nothing,
    _check_a_run_sends_one_context_window_and_caches_each_answer_as_it_arrives,
    _check_a_module_whose_answer_is_cut_off_is_asked_in_halves_and_kept_whole,
    _check_declarations_with_one_path_and_kind_are_ordered_by_their_facts,
    _check_an_unnamed_declaration_is_told_how_to_be_named,
    _check_kinds_are_the_model_node_classes_and_the_context_holds_the_prompt,
    _check_the_inventory_is_written_whole_sorted_and_identical_on_a_rerun,
    _check_a_module_not_inventoried_is_named_and_nothing_is_written,
    _check_no_local_model_exits_3_and_writes_nothing,
    _check_the_package_is_optional_and_a_non_package_is_a_usage_error,
    _check_block_families_are_the_block_classes,
    _check_the_real_tree_is_inventoried_whole,
]
