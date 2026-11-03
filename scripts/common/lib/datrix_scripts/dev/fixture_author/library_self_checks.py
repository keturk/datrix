"""The self-test of the corpus library plan and check, on planted needs and planted copies of the corpus.

The plan is proven on a planted inventory: a local test is not placed, a platform package's test reads its
platform's entry, a minority system choice moves its test to a split entry while prose about the system
moves nothing, and each declaration lands in its family (``core`` when its test declares no block). The
check is proven against copies of the bundled corpus's ``library`` scenario under the real analyzer: the
library provides its own declarations, a planted absent need and a fact its declaration does not hold are
reported, a fact whose key names nothing is unprovided, an entry with an error diagnostic fails, an unknown
entry fails naming the scenarios, and a family every service holds is reported until a control service
lacking it is added.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import CheckFunc, write_files

if TYPE_CHECKING:
    from datrix_scripts.dev.fixture_author.library_check import EntryCheck
    from datrix_scripts.dev.fixture_author.library_plan import NeededTest
    from datrix_scripts.dev.fixture_author.needs_reading import Declaration

_PLATFORM_PACKAGE: Final = "datrix-codegen-planted"
_PLATFORM_ENTRY: Final = "planted"
_PACKAGE: Final = "datrix-alpha"
_SCENARIO: Final = "library"
_BOOK_FILE: Final = "services/book.dtrx"
_ENTRY_FILE: Final = "library.dtrx"
_ABSENT_ENTITY: Final = "library.BookService.db.Ghost"
_TITLE: Final = "BookService.db.Book.title"
_WRONG_TYPE: Final = "type Integer"
_NO_KEY_FACT: Final = "banana yes"

#: A service holding no block and no API, with its owner config: the control service of the library.
_PLAIN_SERVICE: Final = """service library.PlainService('config/plain-service.dcfg') : version('1.0.0') {
    enum Shade { Light, Dark }
}
"""
_PLAIN_CONFIG: Final = """config service library.PlainService {
  base {
    port = 8002;
    replicas = 1;
    resources {
      requests {
        cpu = "100m";
        memory = "256Mi";
      }
      limits {
        cpu = "500m";
        memory = "512Mi";
      }
    }
    healthCheck {
      path = "/health";
      initialDelay = "10s";
    }
    httpSecurity {
      allowedHosts = ["plain-service.example.com", "localhost"];
      corsOrigins = ["https://app.example.com"];
      corsMethods = ["GET", "OPTIONS"];
      corsHeaders = ["Authorization", "Content-Type"];
    }
  }

  profile test as "test" extends base {
    alias env = "TEST";
    alias resource = "test";
  }
}
"""


def _declaration(kind: str, path: str, *facts: str) -> Declaration:
    from datrix_scripts.dev.fixture_author.needs_reading import Declaration

    return Declaration(kind, path, facts)


def _test(name: str, *declarations: Declaration, package: str = _PACKAGE) -> NeededTest:
    from datrix_scripts.dev.fixture_author.library_plan import NeededTest

    return NeededTest(package, f"{package}/tests/test_planted.py", name, declarations)


@contextmanager
def _library_copy() -> Iterator[Path]:
    """A copy of the bundled corpus's ``library`` scenario: the copy's corpus root."""
    from datrix_testing.corpus import CORPUS_ROOT, corpus_copy
    from datrix_testing.parsing import register_installed_parsers

    register_installed_parsers()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "corpus"
        corpus_copy(CORPUS_ROOT, _SCENARIO, root)
        yield root


def _own_needs() -> tuple[Declaration, ...]:
    """Declarations the bundled library holds, read through every resolution path of the check."""
    return (
        _declaration("System", "anything.Named", "version 1.0.0"),
        _declaration("Service", "library.BookService", "type Service", "description Book catalogue"),
        _declaration("RdbmsBlock", "library.BookService.db", "type RdbmsBlock"),
        _declaration("Entity", "library.BookService.db.Book", "type Entity", "field isbn"),
        _declaration("Field", _TITLE, "type String"),
        _declaration("Field", "LoanService.db.Loan.bookId", "indexed", "type UUID"),
        _declaration("Endpoint", "library.LoanService.LoanAPI", "route GET /api/v1/loans/{id}", "method GET"),
        _declaration("RestApi", "LoanAPI", "basePath /api/v1/loans", "default_rdbms_block_name db"),
        _declaration("Enum", "LoanService.LoanStatus", "values Overdue"),
        _declaration("IdentityProvider", "identity.loans", "type IdentityProvider"),
        _declaration("ConfigDecl", "library.BookService", "port 8000", "type service"),
        _declaration("ConfigDecl", "identity.loans", "audience customer", "clientSecret 'loans_client_secret'"),
        _declaration("ConfigDecl", "config/system.dcfg", "engine file"),
    )


def _check_entry(root: Path, *needs: Declaration) -> EntryCheck:
    from datrix_scripts.dev.fixture_author.library_check import check_entry
    from datrix_scripts.dev.fixture_author.library_plan import NeedsInventory, plan_library
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds

    families = block_families(node_kinds())
    inventory = NeedsInventory(tests=(_test("test_reads", *needs),), local=0)
    plan = plan_library(inventory, families, {}, lambda _kind, _key, _value: False)
    return check_entry(root, plan.entry(_SCENARIO), families)


def _check_the_library_provides_its_own_needs() -> None:
    with _library_copy() as root:
        result = _check_entry(root, *_own_needs())
    assert result.profiles == ("test",), result.profiles
    assert result.errors == (), result.errors
    assert result.unprovided == (), [(each.kind, each.path, each.fact, each.reason) for each in result.unprovided]


def _check_a_planted_need_absent_from_the_corpus_is_reported() -> None:
    from datrix_scripts.dev.fixture_author.library_check import FactState

    absent = _declaration("Entity", _ABSENT_ENTITY, "type Entity")
    wrong = _declaration("Field", _TITLE, _WRONG_TYPE)
    with _library_copy() as root:
        result = _check_entry(root, *_own_needs(), absent, wrong)
    reported = {(each.kind, each.path, each.fact) for each in result.unprovided}
    assert reported == {("Entity", _ABSENT_ENTITY, None), ("Field", _TITLE, _WRONG_TYPE)}, reported
    held = next(each for each in result.unprovided if each.fact == _WRONG_TYPE)
    assert held.reason.startswith(FactState.NOT_HELD.value) and "String" in held.reason, held.reason
    assert result.errors == () and not result.passed, result


def _check_a_fact_whose_key_names_nothing_is_unprovided() -> None:
    from datrix_scripts.dev.fixture_author.library_check import FactState

    with _library_copy() as root:
        result = _check_entry(root, _declaration("Service", "library.BookService", "type Service", _NO_KEY_FACT))
    reported = [(each.fact, each.reason) for each in result.unprovided]
    assert reported == [(_NO_KEY_FACT, FactState.NO_KEY.value)], reported


def _check_an_entry_with_an_error_diagnostic_fails() -> None:
    with _library_copy() as root:
        book = root / _BOOK_FILE
        text = book.read_text(encoding="utf-8")
        book.write_text(text.replace("Integer publicationYear;", "Integer publicationYear;\n            Ghosted ghost;"),
                        encoding="utf-8")
        result = _check_entry(root, *_own_needs())
        missing = _check_entry(root / "absent", *_own_needs())
    assert result.errors and all(error.startswith("test: ") for error in result.errors), result.errors
    assert not result.passed and result.unprovided == (), result
    assert len(missing.errors) == 1 and "not a directory" in missing.errors[0], missing.errors
    assert len(missing.unprovided) == len(_own_needs()), missing.unprovided


def _check_a_config_naming_an_absent_template_is_an_entry_error() -> None:
    with _library_copy() as root:
        config = root / "config/book-service.dcfg"
        text = config.read_text(encoding="utf-8")
        config.write_text(text.replace("from postgresContainer(", "from rabbitmqContainer("), encoding="utf-8")
        result = _check_entry(root, *_own_needs())
    assert not result.passed and result.errors, result.errors
    assert all("Template 'rabbitmqContainer' not found" in error and "book-service.dcfg" in error
               and error.startswith("test: ") for error in result.errors), result.errors


def _check_a_family_every_service_holds_needs_a_control_service() -> None:
    with _library_copy() as root:
        before = _check_entry(root, *_own_needs())
        write_files(root, {"services/plain.dtrx": _PLAIN_SERVICE, "config/plain-service.dcfg": _PLAIN_CONFIG})
        entry = root / _ENTRY_FILE
        text = entry.read_text(encoding="utf-8")
        entry.write_text(text.replace("include 'services/loan.dtrx';",
                                      "include 'services/loan.dtrx';\ninclude 'services/plain.dtrx';"),
                         encoding="utf-8")
        after = _check_entry(root, *_own_needs())
    assert before.uncontrolled == ("api", "rdbms"), before.uncontrolled
    assert after.errors == () and after.unprovided == (), (after.errors, after.unprovided)
    assert after.uncontrolled == () and after.passed, after.uncontrolled


def _check_needs_are_placed_by_entry_family_and_system_choice() -> None:
    from datrix_testing.corpus import CORPUS_ROOT

    from datrix_scripts.dev.fixture_author.library_check import library_choices
    from datrix_scripts.dev.fixture_author.library_plan import (
        CORE_FAMILY,
        LIBRARY_ENTRY,
        NeedsInventory,
        plan_library,
    )
    from datrix_scripts.dev.fixture_author.needs_command import block_families
    from datrix_scripts.dev.fixture_author.needs_reading import node_kinds

    system = "System"
    tests = (
        _test("test_one", _declaration(system, "a.S", "version 1.0.0"),
              _declaration("Service", "a.Orders"), _declaration("RdbmsBlock", "a.Orders.db"),
              _declaration("Entity", "a.Orders.db.Order"), _declaration("Struct", "a.Orders.Money")),
        _test("test_two", _declaration(system, "b.S", "version '1.0.0'")),
        _test("test_three", _declaration(system, "c.S", "version 2.0.0"), _declaration("Service", "c.Plain")),
        _test("test_prose", _declaration(system, "d.S", "version is the newest one")),
        _test("test_platform", _declaration(system, "e.S", "version 2.0.0"), package=_PLATFORM_PACKAGE),
    )
    families = block_families(node_kinds())
    plan = plan_library(NeedsInventory(tests, local=1), families, {_PLATFORM_PACKAGE: _PLATFORM_ENTRY},
                        library_choices(CORPUS_ROOT))
    placed = {entry.entry: sorted(test.name for test in entry.tests) for entry in plan.entries}
    assert placed == {
        LIBRARY_ENTRY: ["test_one", "test_prose", "test_two"],
        "version-2-0-0": ["test_three"],
        _PLATFORM_ENTRY: ["test_platform"],
    }, placed
    assert plan.local == 1, plan.local
    library = plan.entry(LIBRARY_ENTRY)
    assert {need.path for need in library.families["rdbms"]} == {"a.Orders", "a.Orders.db", "a.Orders.db.Order",
                                                                 "a.Orders.Money"}, library.families
    assert [need.path for need in plan.entry("version-2-0-0").families[CORE_FAMILY]] == ["c.Plain"]
    assert [need.facts for need in library.system if need.path == "a.S"] == [("version 1.0.0",)], library.system


def _check_the_inventory_is_read_without_its_local_tests() -> None:
    from datrix_scripts.dev.fixture_author.library_plan import LibraryPlanError, read_needs_inventory

    row = {
        "kind": "module", "module": f"{_PACKAGE}/tests/test_x.py", "package": _PACKAGE, "inputs": [],
        "tests": [
            {"name": "test_shared", "local": None,
             "declarations": [{"kind": "Service", "path": "a.S", "facts": ["type Service"]}]},
            {"name": "test_local", "local": "the input is a syntax error", "declarations": []},
        ],
    }
    tree = {"kind": "tree", "module": f"{_PACKAGE}/src/reader.py", "package": _PACKAGE, "symbol": "f", "reads": "x"}
    with tempfile.TemporaryDirectory() as tmp:
        needs = Path(tmp) / "needs.json"
        needs.write_text(json.dumps({"rows": [row, tree]}), encoding="utf-8")
        inventory = read_needs_inventory(needs)
        needs.write_text(json.dumps({"rows": [{"kind": "module", "module": "m"}]}), encoding="utf-8")
        try:
            read_needs_inventory(needs)
        except LibraryPlanError as error:
            refused = str(error)
        else:
            refused = ""
    assert [test.name for test in inventory.tests] == ["test_shared"] and inventory.local == 1, inventory
    assert inventory.tests[0].declarations[0].facts == ("type Service",), inventory.tests[0]
    assert "has no 'package'" in refused, refused


CHECKS: Final[list[CheckFunc]] = [
    _check_the_inventory_is_read_without_its_local_tests,
    _check_needs_are_placed_by_entry_family_and_system_choice,
    _check_the_library_provides_its_own_needs,
    _check_a_planted_need_absent_from_the_corpus_is_reported,
    _check_a_fact_whose_key_names_nothing_is_unprovided,
    _check_an_entry_with_an_error_diagnostic_fails,
    _check_a_config_naming_an_absent_template_is_an_entry_error,
    _check_a_family_every_service_holds_needs_a_control_service,
]
