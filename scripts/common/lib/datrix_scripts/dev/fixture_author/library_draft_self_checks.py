"""The self-test of drafting the corpus library, over a loopback model server on copies of the bundled corpus.

A planted plan asks the ``library`` entry for a service holding no block, its enum and its owner config's
port. The loopback model's draft is checked under the real analyzer: one that provides every need lands
(the family file, its config and the entry's include, needed − provided = ∅ and the control service the
library lacked); one holding a secret-looking literal is queued after its one request and nothing is
written; one still lacking a need after the last round is queued with why and its last draft, nothing
written; a need that collides is renamed and the rename recorded, a rename onto a needed path sent back
first; a new entry (a platform's) gets its drafted system, its config and the include of its family, and a
family whose entries never run is queued unchecked, never asked and never written; no local model exits 3 and writes nothing; a
file name answered as the source goes back, and every request carries the run's one window and an answer
budget above the default; a unit no request holds whole is queued unasked; and the command refuses a package
and a missing inventory.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import CheckFunc

if TYPE_CHECKING:
    from datrix_scripts.dev.fixture_author.library_check import EntryCheck
    from datrix_scripts.dev.fixture_author.library_plan import LibraryPlan
    from datrix_scripts.dev.fixture_author.needs_reading import Declaration
    from datrix_scripts.local_llm_loopback import Chat, LoopbackOllama

_CALLER: Final = "fixture-author-library-self-test"
_PACKAGE: Final = "datrix-alpha"
_ENTRY: Final = "library"
_PLATFORM_ENTRY: Final = "planted"
_SERVICE: Final = "library.ShelfService"
_RENAMED: Final = "library.StacksService"
_SHELF: Final = "description Shelf of the library scenario"
_STACKS: Final = "description Stacks of the library scenario"
_DARK: Final = "values Dark"
_PORT: Final = "port 8002"
_CORE_FILE: Final = "services/core.dtrx"
_CONFIG_FILE: Final = "config/shelf-service.dcfg"
_STACKS_CONFIG_FILE: Final = "config/stacks-service.dcfg"
_QUEUE_FILE: Final = "library-core.md"
# An access key id of the documented example shape: assembled, so no literal of it is committed.
_SECRET: Final = "AKIA" + "IOSFODNN7" + "EXAMPLE"

_SERVICE_TEXT: Final = """service {name}('{config}') : version('1.0.0'), description('{about} of the library scenario') {{
    enum Shade {{ {values} }}
}}
"""
_CONFIG_TEXT: Final = """config service {name} {{
  import "config/templates/datasources.dcfg";

  base {{
    port = {port};
    replicas = 1;{extra}
    resources {{
      requests {{
        cpu = "100m";
        memory = "256Mi";
      }}
      limits {{
        cpu = "500m";
        memory = "512Mi";
      }}
    }}
    healthCheck {{
      path = "/health";
      initialDelay = "10s";
    }}
    httpSecurity {{
      allowedHosts = ["{host}.example.com", "localhost"];
      corsOrigins = ["https://app.example.com"];
      corsMethods = ["GET", "OPTIONS"];
      corsHeaders = ["Authorization", "Content-Type"];
    }}
  }}

  profile test as "test" extends base {{
    alias env = "TEST";
    alias resource = "test";
  }}
}}
"""
#: The system config of the planted entry.
_SYSTEM_CONFIG_TEXT: Final = """config system test.System {
  base {
    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    configStore {
      engine = "file";
      flavor = "container";
      applicationName = "planted";
      environment = "test";
      profiles {
        settings {
          kind = "freeform";
          keys {
            Boolean debugMode : description("Enable debug mode.") = false;
          }
        }
      }
    }
  }

  profile test as "test" extends base {
    alias env = "TEST";
    alias resource = "test";
  }
}
"""


@dataclass(frozen=True)
class _Corpus:
    """A copy of the bundled corpus with the queue and renames file a run writes beside it."""

    root: Path
    queue: Path
    renames: Path

    def files(self) -> dict[str, bytes]:
        """Every file of the copy, by relative path, with its bytes."""
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}


@contextmanager
def _corpus() -> Iterator[_Corpus]:
    from datrix_testing.corpus import CORPUS_ROOT

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "corpus"
        shutil.copytree(CORPUS_ROOT, root)
        yield _Corpus(root, Path(tmp) / "queue", Path(tmp) / "renames.json")


def _declaration(kind: str, path: str, *facts: str) -> Declaration:
    from datrix_scripts.dev.fixture_author.needs_reading import Declaration

    return Declaration(kind, path, facts)


def _plan(*tests: tuple[Declaration, ...], platforms: dict[str, str] | None = None) -> LibraryPlan:
    from datrix_scripts.dev.fixture_author.library_plan import NeededTest, NeedsInventory, plan_library
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds

    planted = tuple(NeededTest(_PACKAGE, f"{_PACKAGE}/tests/test_shelf.py", f"test_{index}", declarations)
                    for index, declarations in enumerate(tests))
    return plan_library(NeedsInventory(planted, local=0), block_families(node_kinds()), platforms or {},
                        lambda _kind, _key, _value: False)


def _shelf_needs() -> tuple[Declaration, ...]:
    return (
        _declaration("Service", _SERVICE, _SHELF),
        _declaration("Enum", f"{_SERVICE}.Shade", _DARK),
        _declaration("ConfigDecl", _SERVICE, _PORT),
    )


def _service(name: str, config: str, about: str, values: str) -> str:
    return _SERVICE_TEXT.format(name=name, config=config, about=about, values=values)


def _config(name: str, port: int, host: str, extra: str = "") -> str:
    return _CONFIG_TEXT.format(name=name, port=port, host=host, extra=extra)


def _answer(source: str, configs: dict[str, str], renames: list[dict[str, object]] | None = None) -> str:
    files = [{"path": path, "text": text} for path, text in configs.items()]
    return json.dumps({"source": source, "configs": files, "renames": renames or []})


def _shelf_answer(values: str = "Light, Dark", extra: str = "") -> Callable[[Chat], str]:
    answer = _answer(_service(_SERVICE, _CONFIG_FILE, "Shelf", values),
                     {_CONFIG_FILE: _config(_SERVICE, 8002, "shelf-service", extra)})
    return lambda _chat: answer


def _run(corpus: _Corpus, server: LoopbackOllama, plan: LibraryPlan) -> tuple[int, str]:
    from datrix_scripts.dev.fixture_author.library import LibraryDrafter, run_library
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds
    from datrix_scripts.local_llm import LocalLlmPool
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    pool = LocalLlmPool(server.settings(_CALLER), report=lambda _line: None)
    drafter = LibraryDrafter(pool, ContentFilter(WORKSPACE_DIR), corpus.root, block_families(node_kinds()), "",
                             queue_dir=corpus.queue, renames_file=corpus.renames)
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = run_library(drafter, plan)
    return code, printed.getvalue()


def _entry_check(corpus: _Corpus, plan: LibraryPlan, name: str = _ENTRY) -> EntryCheck:
    """The entry *name* of *corpus* checked against *plan*, with the renames the run recorded applied."""
    from datrix_scripts.dev.fixture_author.library_check import check_entry
    from datrix_scripts.dev.fixture_author.library_drafts import apply_renames, read_renames
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds

    entry = plan.entry(name)
    recorded = read_renames(corpus.renames)
    families = {family: apply_renames(needs, recorded) for family, needs in entry.families.items()}
    return check_entry(corpus.root, replace(entry, families=families), block_families(node_kinds()))


def _check_a_loopback_library_draft_provides_every_need() -> None:
    from datrix_scripts.dev.fixture_author.library_check import EntryCheck
    from datrix_scripts.dev.fixture_author.library_drafts import LACKING_HEADING, TEMPLATES
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    plan = _plan(_shelf_needs())
    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(_shelf_answer()) as server:
            code, printed = _run(corpus, server, plan)
            chats = list(server.chats)
        after = corpus.files()
        check = _entry_check(corpus, plan)
        queued = sorted(corpus.queue.glob("*.md")) if corpus.queue.is_dir() else []
        renamed = corpus.renames.exists()
    assert code == 0, printed
    assert isinstance(check, EntryCheck) and check.passed, check
    assert check.unprovided == () and check.uncontrolled == (), (check.unprovided, check.uncontrolled)
    changed = sorted(path for path in after if before.get(path) != after[path])
    assert changed == [_CONFIG_FILE, "library.dtrx", _CORE_FILE], changed
    assert "include 'services/core.dtrx';" in after["library.dtrx"].decode(), "the entry includes the family file"
    assert len(chats) == 1, f"only the lacking unit is asked, once: {[chat.user[:80] for chat in chats]}"
    (chat,) = chats
    assert f"UNIT: core; FILE: {_CORE_FILE}" in chat.user and f"Service {_SERVICE}; facts: {_SHELF}" in chat.user
    assert LACKING_HEADING in chat.user and "control service" in chat.user, "the lacking needs and control are sent"
    assert TEMPLATES in chat.system and "template postgresContainer" in chat.system, "the templates are sent"
    assert queued == [] and not renamed, (queued, renamed)


def _check_a_secret_literal_draft_is_refused_and_never_written() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.skill.common import EXIT_NO_MODEL

    extra = f'\n    accessKeyId = "{_SECRET}";'
    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(_shelf_answer(extra=extra)) as server:
            code, printed = _run(corpus, server, _plan(_shelf_needs()))
            asked = len(server.chats)
        after = corpus.files()
        queue = (corpus.queue / _QUEUE_FILE).read_text(encoding="utf-8")
    assert code not in (0, EXIT_NO_MODEL), printed
    assert after == before, "nothing of a refused draft is written to the corpus"
    assert asked == 1, f"a refused draft is queued at once, never asked again: {asked} request(s)"
    assert "looks like a raw secret" in queue and _SECRET not in queue, "queued with why, the value not repeated"


def _check_a_unit_still_failing_after_the_last_round_is_queued() -> None:
    from datrix_scripts.dev.fixture_author.drafting import MAX_ROUNDS
    from datrix_scripts.dev.fixture_author.prompting import FEEDBACK_HEADING, PREVIOUS_DRAFT_HEADING
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(_shelf_answer(values="Light")) as server:
            code, printed = _run(corpus, server, _plan(_shelf_needs()))
            chats = list(server.chats)
        after = corpus.files()
        queue = (corpus.queue / _QUEUE_FILE).read_text(encoding="utf-8")
    assert code == 1, printed
    assert len(chats) == MAX_ROUNDS, f"asked once per round: {len(chats)}"
    assert FEEDBACK_HEADING in chats[1].user and PREVIOUS_DRAFT_HEADING in chats[1].user, "a failed draft goes back"
    assert f"fact '{_DARK}'" in chats[1].user, "with the need it still lacks"
    assert after == before, "a unit still failing writes nothing to the corpus"
    assert f"fact '{_DARK}'" in queue and "## Last draft" in queue and "enum Shade { Light }" in queue, queue


def _collision_answer(chat: Chat) -> str:
    """A rename onto a needed path first; once that is sent back, the rename to a new service."""
    from datrix_scripts.dev.fixture_author.prompting import FEEDBACK_HEADING

    to = _RENAMED if FEEDBACK_HEADING in chat.user else _SERVICE
    source = _service(_SERVICE, _CONFIG_FILE, "Shelf", "Light, Dark") + _service(
        _RENAMED, _STACKS_CONFIG_FILE, "Stacks", "Light")
    configs = {_CONFIG_FILE: _config(_SERVICE, 8002, "shelf-service"),
               _STACKS_CONFIG_FILE: _config(_RENAMED, 8003, "stacks-service")}
    return _answer(source, configs, [{"kind": "Service", "path": _SERVICE, "to": to, "facts": [_STACKS]}])


def _check_a_colliding_need_is_renamed_and_recorded() -> None:
    from datrix_scripts.dev.fixture_author.library_check import EntryCheck
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    plan = _plan(_shelf_needs(), (_declaration("Service", _SERVICE, _STACKS),))
    with _corpus() as corpus:
        with LoopbackOllama(_collision_answer) as server:
            code, printed = _run(corpus, server, plan)
            chats = list(server.chats)
        check = _entry_check(corpus, plan)
        renames = json.loads(corpus.renames.read_text(encoding="utf-8"))
    assert code == 0, printed
    assert len(chats) == 2 and "takes a path a need" in chats[1].user, "a rename onto a needed path goes back"
    assert renames == {"renames": [{"kind": "Service", "path": _SERVICE, "to": _RENAMED, "facts": [_STACKS]}]}, renames
    assert isinstance(check, EntryCheck) and check.passed, check


def _new_entry_answer(chat: Chat) -> str:
    """The new entry's system with its config (no gateway: none of its services is gateway-routed), and the
    shelf service for the family."""
    from datrix_scripts.dev.fixture_author.library_drafts import new_system_config, system_unit_name

    if f"UNIT: {system_unit_name(_PLATFORM_ENTRY)};" not in chat.user:
        return _shelf_answer()(chat)
    config = new_system_config(_PLATFORM_ENTRY)
    source = f"system test.System('{config}') : version('1.0.0') {{\n}}\n"
    return _answer(source, {config: _SYSTEM_CONFIG_TEXT})


def _check_a_new_entry_is_drafted_with_its_system_and_includes() -> None:
    from datrix_scripts.dev.fixture_author.library import ENTRY_HEADER
    from datrix_scripts.dev.fixture_author.library_drafts import new_system_config, system_unit_name
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    needs = (_declaration("System", "planted.System", "version 1.0.0"), *_shelf_needs())
    plan = _plan(needs, platforms={_PACKAGE: _PLATFORM_ENTRY})
    with _corpus() as corpus:
        with LoopbackOllama(_new_entry_answer) as server:
            code, printed = _run(corpus, server, plan)
            asked = [chat.user.split(";", 1)[0] for chat in server.chats]
        check = _entry_check(corpus, plan, _PLATFORM_ENTRY)
        entry = (corpus.root / f"{_PLATFORM_ENTRY}.dtrx").read_text(encoding="utf-8")
        config = (corpus.root / new_system_config(_PLATFORM_ENTRY)).is_file()
        library = (corpus.root / "library.dtrx").read_text(encoding="utf-8")
    assert code == 0, printed
    assert check.passed and check.profiles == ("test",), check
    assert asked == [f"UNIT: {system_unit_name(_PLATFORM_ENTRY)}", "UNIT: core"], "the system first, then the family it runs"
    assert entry.startswith(ENTRY_HEADER.format(entry=_PLATFORM_ENTRY)) and f"include '{_CORE_FILE}';" in entry, entry
    assert config, "the drafted system config is written"
    assert _CORE_FILE not in library, f"the family is included by the entry reading it only: {library}"


def _check_a_family_whose_entries_never_run_is_queued_unchecked() -> None:
    from datrix_scripts.dev.fixture_author.library_drafts import system_unit_name
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    needs = (_declaration("System", "planted.System", "version 1.0.0"), *_shelf_needs())
    plan = _plan(needs, platforms={_PACKAGE: _PLATFORM_ENTRY})
    # A system draft whose config never resolves: configStore lacks its required profiles.
    broken = _answer(f"system test.System('config/{_PLATFORM_ENTRY}-system.dcfg') : version('1.0.0') {{\n}}\n",
                     {f"config/{_PLATFORM_ENTRY}-system.dcfg": _SYSTEM_CONFIG_TEXT.replace("profiles {", "unread {")})
    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(lambda _chat: broken) as server:
            code, printed = _run(corpus, server, plan)
            asked = {chat.user.split(";", 1)[0] for chat in server.chats}
        after = corpus.files()
        core = (corpus.queue / _QUEUE_FILE).read_text(encoding="utf-8")
        system = (corpus.queue / f"library-{system_unit_name(_PLATFORM_ENTRY)}.md").read_text(encoding="utf-8")
    assert code == 1 and after == before, printed
    assert asked == {f"UNIT: {system_unit_name(_PLATFORM_ENTRY)}"}, f"a family waiting on its entry is not asked: {asked}"
    assert "none of which runs clean, so its needs stay unchecked" in core, core
    assert "Missing required key 'profiles'" in system, system


def _check_no_local_model_exits_3_and_writes_nothing() -> None:
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.skill.common import EXIT_NO_MODEL

    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(answering("{}"), models=()) as server:
            code, printed = _run(corpus, server, _plan(_shelf_needs()))
        after = corpus.files()
        wrote = corpus.queue.exists() or corpus.renames.exists()
    assert code == EXIT_NO_MODEL, printed
    assert after == before and not wrote, "no model: nothing is written"


def _path_then_shelf_answer(chat: Chat) -> str:
    """The unit's file name as its source first; once that is sent back, the whole file."""
    if "the source is the file name" in chat.user:
        return _shelf_answer()(chat)
    return _answer(_CORE_FILE, {_CONFIG_FILE: _config(_SERVICE, 8002, "shelf-service")})


def _check_a_file_name_as_source_goes_back_and_every_request_carries_one_window() -> None:
    from datrix_scripts.dev.fixture_author.needs_reading import ANSWER_TOKENS, MIN_CONTEXT_TOKENS
    from datrix_scripts.local_llm_loopback import LoopbackOllama

    with _corpus() as corpus:
        with LoopbackOllama(_path_then_shelf_answer) as server:
            code, printed = _run(corpus, server, _plan(_shelf_needs()))
            chats = list(server.chats)
    assert code == 0, printed
    assert len(chats) == 2, f"the file name goes back once, then the file lands: {len(chats)} request(s)"
    assert "never its path" in chats[0].system, "the answer shape says the source is the file's text"
    assert f"the whole .dtrx text of {_CORE_FILE}" in chats[1].user, chats[1].user[-600:]
    options = [chat.body.get("options") for chat in chats]
    assert all(isinstance(each, dict) for each in options), options
    windows = {each["num_ctx"] for each in options if isinstance(each, dict)}
    predicted = [each["num_predict"] for each in options if isinstance(each, dict)]
    assert len(windows) == 1 and min(windows) >= MIN_CONTEXT_TOKENS, f"one window per run: {windows}"
    assert all(isinstance(each, int) and each > ANSWER_TOKENS for each in predicted), predicted


def _check_a_unit_no_request_holds_is_queued_unasked() -> None:
    from datrix_scripts.dev.fixture_author.library import MAX_REQUEST_TOKENS
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN

    huge = _declaration("Service", _SERVICE, "description " + "x" * (MAX_REQUEST_TOKENS * CHARS_PER_TOKEN))
    with _corpus() as corpus:
        before = corpus.files()
        with LoopbackOllama(_shelf_answer()) as server:
            code, printed = _run(corpus, server, _plan((huge,)))
            asked = [chat.user[:60] for chat in server.chats]
        after = corpus.files()
        queue = (corpus.queue / _QUEUE_FILE).read_text(encoding="utf-8")
    assert code == 1, printed
    assert asked == [], f"a unit no request holds whole is never asked: {asked}"
    assert after == before, "nothing of it is written"
    assert "no model reads it whole" in queue and str(MAX_REQUEST_TOKENS) in queue, queue[-800:]


def _check_the_library_takes_no_package_and_needs_the_inventory() -> None:
    from datrix_scripts.dev.fixture_author.cli import LIBRARY_KIND, main
    from datrix_scripts.dev.fixture_author.library import run_library_command
    from datrix_scripts.gate_harness import EXIT_USAGE, expect_usage_error
    from datrix_scripts.local_llm import LocalLlmSettings

    printed = io.StringIO()
    with redirect_stdout(printed):
        code = main(["--kind", LIBRARY_KIND, "--package", "datrix-common"])
    assert code == EXIT_USAGE, (code, printed.getvalue())
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "needs.json"
        expect_usage_error(lambda: run_library_command(LocalLlmSettings(caller=_CALLER), missing), "fixture-author.ps1 needs")


CHECKS: Final[list[CheckFunc]] = [
    _check_a_loopback_library_draft_provides_every_need,
    _check_a_secret_literal_draft_is_refused_and_never_written,
    _check_a_unit_still_failing_after_the_last_round_is_queued,
    _check_a_colliding_need_is_renamed_and_recorded,
    _check_a_new_entry_is_drafted_with_its_system_and_includes,
    _check_a_family_whose_entries_never_run_is_queued_unchecked,
    _check_no_local_model_exits_3_and_writes_nothing,
    _check_a_file_name_as_source_goes_back_and_every_request_carries_one_window,
    _check_a_unit_no_request_holds_is_queued_unasked,
    _check_the_library_takes_no_package_and_needs_the_inventory,
]
