"""The self-test of ``dev/fixture-dedupe.ps1``: the dedupe rules over a planted workspace.

The planted workspace holds three packages (``datrix-alpha``, ``datrix-beta``, ``datrix-gamma``), the
shared ``datrix-testing`` fixture set with its corpus, and a ``datrix-common`` whose ``tests/`` holds
``test_model_contracts.py``: its ``src/datrix_common`` names the installed package, so the secret screen
runs the real capture with the real model set. The write checks run the real write over that workspace;
the semantic-baseline check analyzes the installed corpus (a planted package's dump would hold builtins
paths outside its workspace). No check fakes a collaborator.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Final

from datrix_testing.corpus import CORPUS_ROOT
from datrix_testing.parsing import register_installed_parsers
from datrix_testing.semantic_baseline import SemanticBaselineCorpus

from datrix_scripts.dev.fixture_dedupe.baseline import (
    AS_IS,
    BaselineAfter,
    BaselineBefore,
    Translation,
    baseline_failures,
    entry_hashes,
    updated_manifest,
)
from datrix_scripts.dev.fixture_dedupe.follow import placed_text
from datrix_scripts.dev.fixture_dedupe.layout import TreeRoots, corpus_root, shared_root
from datrix_scripts.dev.fixture_dedupe.listing import dry_run
from datrix_scripts.dev.fixture_dedupe.plan import (
    BYTES_REASON,
    FOLLOW_REASON,
    LONE_COPY_REASON,
    READER_REASON,
    SCREEN_REASON,
    SHARED_SET_REASON,
    TEXT_REASON,
    FilePlacement,
    LiteralPlacement,
    Plan,
    build_plan,
    moved_copies,
)
from datrix_scripts.dev.fixture_dedupe.proof import PlannedTree, WriteSet, prove, write_set
from datrix_scripts.dev.fixture_dedupe.references import FILE_RULE, PROJECT_RULE, fixture_references, resolve_reference
from datrix_scripts.dev.fixture_dedupe.sites import (
    ACCESSOR,
    ACCESSOR_IMPORT,
    PAIR_SITE,
    PATH_SITE,
    accessor_argument,
    rewritten_source,
)
from datrix_scripts.dev.fixture_dedupe.static_paths import ModuleScope, StaticEvaluator, UnevaluableError
from datrix_scripts.dev.fixture_dedupe.walks import DIAGNOSTICS_COLLECTOR, SITE_READ
from datrix_scripts.dev.fixture_dedupe.write import (
    OLD_DIR,
    RECORD_DIR,
    RECORD_FILE,
    WriteTransaction,
    old_bytes,
    write_plan,
    write_run,
)
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, NamedCheck, named_checks, write_files

_ALPHA: Final = "datrix-alpha/tests/fixtures"
_BETA: Final = "datrix-beta/tests/fixtures"
_GAMMA: Final = "datrix-gamma/tests/fixtures"
_SHARED_SET: Final = "datrix-testing/src/datrix_testing/fixtures_data"
_SHARED: Final = f"{_SHARED_SET}/corpus/shared"

_CATALOG: Final = "service shop.Catalog('catalog.dcfg') {\n}\n"
_SYSTEM: Final = "include 'orders.dtrx';\nsystem Shop('config/system.dcfg') {\n}\n"
_ORDERS: Final = "service shop.Orders('orders.dcfg') {\n}\n"
_ORDERS_OTHER: Final = "service shop.Orders('orders.dcfg') {\n  struct Line {\n    String note;\n  }\n}\n"
_DEPLOYMENT: Final = "  base {\n    deployment {\n      runtime = \"docker-compose\";\n      provider = \"local\";\n    }\n  }\n\n"
_TEST_PROFILE: Final = "  profile test as \"test\" extends base {\n  }\n}\n"
_SYSTEM_CONFIG: Final = f"config system Shop {{\n{_DEPLOYMENT}{_TEST_PROFILE}"
# A service document missing its required port: the capture refuses it, a negative fixture.
_NEGATIVE: Final = f"config service shop.Negative {{\n{_DEPLOYMENT}{_TEST_PROFILE}"
_WALKED: Final = "service shop.Walked('walked.dcfg') {\n}\n"
_RULE: Final = "service shop.Rule('rule.dcfg') {\n}\n"
_AREA: Final = "service shop.Area('area.dcfg') {\n}\n"
# Texts the formatter's corpus walk refuses: a partial source and a format template.
_PARTIAL: Final = "service shop.Head('head.dcfg') {\n"
_TEMPLATE: Final = "service shop.Template('template.dcfg') {{\n  {body}\n}}\n"
# A value the capture's secret screen flags (a credential prefix), in a document a datrix-common model reads.
_PUSH: Final = (
    "config app shop.PushApp {\n  base {\n    targets = [\"flutter\"];\n    appId = \"com.example.push\";\n"
    "    firebase {\n      projectId = \"shop-push-app\";\n      apiKey = \"AIzaSyExamplePushAppPublicKey00000000\";\n"
    "      messagingSenderId = \"100000000002\";\n    }\n  }\n\n  profile test as \"test\" extends base {\n  }\n}\n"
)

_WALK_MODULE: Final = '''from pathlib import Path

from datrix_testing.semantic_baseline import PROJECT_FIXTURES

_PROJECT_FIXTURES = Path(__file__).resolve().parent / PROJECT_FIXTURES
PROJECTS = sorted(_PROJECT_FIXTURES.glob("*/system.dtrx"))
'''
_CONFTEST: Final = '''from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """The lint fixtures."""
    return Path(__file__).parent / "fixtures" / "lint"
'''
_LINT_MODULE: Final = '''def test_lint(fixtures_dir):
    files = list(fixtures_dir.glob("*.dtrx"))
    assert files
'''
_UNKNOWN_WALK_MODULE: Final = '''def test_walk(project_FIXTURES):
    assert list(project_FIXTURES.iterdir())
'''
_HELPER_READ_MODULE: Final = '''from pathlib import Path

from datrix_testing.tenant_fixtures import fixture_set_mismatch

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tenancy"


def test_on_disk() -> None:
    assert fixture_set_mismatch(_FIXTURE_DIR, []) == []


def test_planted(fixture_dir: Path) -> None:
    assert fixture_set_mismatch(fixture_dir, []) == []
'''
_ALPHA_LITERALS: Final = f'''ORDERS = "service shop.Orders('orders.dcfg') {{\\n}}\\n"
PUSH_CONFIG = """{_PUSH}"""


def check(text: str) -> str:
    return text


def test_inline() -> None:
    check("service shop.Orders('orders.dcfg') {{\\n}}\\n")
'''
_BETA_LITERALS: Final = f'''SVC: str = "service shop.Orders('orders.dcfg') {{\\n}}\\n"
PUSH_CONFIG = """{_PUSH}"""
'''
# SPACED is one fixture with ORDERS and SVC (equal normalized text) but not their exact text: it stays as written.
_GAMMA_LITERALS: Final = '''NAME = "Orders"
FORMATTED = f"service shop.{NAME}('orders.dcfg') {{\\n}}\\n"
SPACED = "service   shop.Orders('orders.dcfg') {\\n}\\n"
'''
_ALPHA_COLLIDE: Final = '''X = "service shop.Alpha('alpha.dcfg') {\\n}\\n"\nX = "service shop.Beta('beta.dcfg') {\\n}\\n"\n'''
_BETA_COLLIDE: Final = '''Y = "service shop.Alpha('alpha.dcfg') {\\n}\\n"\nZ = "service shop.Beta('beta.dcfg') {\\n}\\n"\n'''
# Each test function binds its own `source`: one name, two texts, two placements.
_ALPHA_SCOPED: Final = '''class TestScoped:
    def test_one(self) -> None:
        source = "service shop.One('one.dcfg') {\\n}\\n"

    def test_two(self) -> None:
        source = "service shop.Two('two.dcfg') {\\n}\\n"
'''
_BETA_SCOPED: Final = '''ONE = "service shop.One('one.dcfg') {\\n}\\n"\nTWO = "service shop.Two('two.dcfg') {\\n}\\n"\n'''

_PLANTED: Final[Mapping[str, str]] = {
    f"{_SHARED_SET}/corpus/shop.dtrx": "system Store {\n}\n",
    f"{_SHARED_SET}/catalog.dtrx": _CATALOG,
    f"{_ALPHA}/catalog.dtrx": _CATALOG,
    f"{_BETA}/catalog.dtrx": "// beta copy\n" + _CATALOG,
    f"{_GAMMA}/catalog.dtrx": _CATALOG,
    f"{_ALPHA}/app/system.dtrx": _SYSTEM,
    f"{_ALPHA}/app/orders.dtrx": _ORDERS,
    f"{_ALPHA}/app/config/system.dcfg": _SYSTEM_CONFIG,
    f"{_BETA}/app/system.dtrx": _SYSTEM,
    f"{_BETA}/app/orders.dtrx": _ORDERS_OTHER,
    f"{_BETA}/app/config/system.dcfg": _SYSTEM_CONFIG,
    f"{_GAMMA}/app/system.dtrx": _SYSTEM,
    f"{_GAMMA}/app/orders.dtrx": _ORDERS,
    f"{_GAMMA}/app/config/system.dcfg": _SYSTEM_CONFIG,
    f"{_ALPHA}/walked.dtrx": _WALKED,
    f"{_BETA}/projects/walked.dtrx": _WALKED,
    f"{_GAMMA}/walked.dtrx": _WALKED,
    "datrix-beta/tests/test_walk.py": _WALK_MODULE,
    f"{_ALPHA}/rule.dtrx": _RULE,
    f"{_GAMMA}/lint/rule.dtrx": _RULE,
    "datrix-gamma/tests/conftest.py": _CONFTEST,
    "datrix-gamma/tests/test_lint.py": _LINT_MODULE,
    f"{_ALPHA}/diagnostics/area.dtrx": _AREA,
    f"{_BETA}/area.dtrx": _AREA,
    f"{_GAMMA}/area.dtrx": _AREA,
    f"{_ALPHA}/config/negative.dcfg": _NEGATIVE,
    f"{_BETA}/config/negative.dcfg": _NEGATIVE,
    "datrix-alpha/tests/test_negative.py": f'NEGATIVE_CONFIG = """{_NEGATIVE}"""\n',
    "datrix-beta/tests/test_negative.py": f'NEGATIVE_CONFIG = """{_NEGATIVE}"""\n',
    f"{_ALPHA}/fragment/head.dtrx": _PARTIAL,
    f"{_BETA}/fragment/head.dtrx": _PARTIAL,
    "datrix-alpha/tests/test_template.py": f'TEMPLATE = """{_TEMPLATE}"""\n',
    "datrix-beta/tests/test_template.py": f'TEMPLATE = """{_TEMPLATE}"""\n',
    f"{_ALPHA}/config/push.dcfg": _PUSH,
    f"{_BETA}/config/push.dcfg": _PUSH,
    "datrix-alpha/tests/test_literals.py": _ALPHA_LITERALS,
    "datrix-beta/tests/test_literals.py": _BETA_LITERALS,
    "datrix-gamma/tests/test_literals.py": _GAMMA_LITERALS,
    "datrix-alpha/tests/test_collide.py": _ALPHA_COLLIDE,
    "datrix-beta/tests/test_collide.py": _BETA_COLLIDE,
    "datrix-alpha/tests/test_scoped.py": _ALPHA_SCOPED,
    "datrix-beta/tests/test_scoped.py": _BETA_SCOPED,
    "datrix-common/src/datrix_common/__init__.py": "",
    "datrix-common/tests/test_model_contracts.py": "VALUE = 1\n",
}
_UNKNOWN_WALK: Final = "datrix-gamma/tests/test_unknown.py"

# beta's and gamma's billing system is one fixture: it includes billing.dtrx and names config/pay.dcfg, each
# one fixture with alpha's lib/ copy, which sorts first. The system moves to beta's shared place, so both of
# its references must reach alpha's shared copies.
_BILLING: Final = "service shop.Billing('billing.dcfg') {\n}\n"
_PAY_CONFIG: Final = f"config system Pay {{\n{_DEPLOYMENT}{_TEST_PROFILE}"
_BILLING_SYSTEM: Final = "include 'billing.dtrx';\nsystem Pay('config/pay.dcfg') {\n}\n"
_BILLING_PLANTED: Final[Mapping[str, str]] = {
    f"{_ALPHA}/lib/billing.dtrx": _BILLING,
    f"{_ALPHA}/lib/config/pay.dcfg": _PAY_CONFIG,
    f"{_BETA}/billing/billing.dtrx": _BILLING,
    f"{_BETA}/billing/config/pay.dcfg": _PAY_CONFIG,
    f"{_BETA}/billing/system.dtrx": _BILLING_SYSTEM,
    f"{_GAMMA}/billing/billing.dtrx": _BILLING,
    f"{_GAMMA}/billing/config/pay.dcfg": _PAY_CONFIG,
    f"{_GAMMA}/billing/system.dtrx": _BILLING_SYSTEM,
}
# A unique .dcfg of beta that stays and imports beta's pay.dcfg: the loader confines an import to the project.
_CONFINED_READER: Final = f"{_BETA}/billing/config/main.dcfg"
# A shared-set entry naming config/deep.dcfg from deep/; beta's and gamma's sub/config/deep.dcfg are one and
# move to beta's shared place, sub/config/deep.dcfg, nearer the entry than the file it names.
_SHADOWED_READER: Final = f"{_SHARED}/datrix-beta/tests/fixtures/deep/sub/entry.dtrx"
_SHADOWED_PLANTED: Final[Mapping[str, str]] = {
    _SHADOWED_READER: "system Deep('config/deep.dcfg') {\n}\n",
    f"{_SHARED}/datrix-beta/tests/fixtures/deep/config/deep.dcfg": f"config system Deep {{\n{_DEPLOYMENT}{_TEST_PROFILE}",
    f"{_BETA}/deep/sub/config/deep.dcfg": f"config system Shadow {{\n{_DEPLOYMENT}{_TEST_PROFILE}",
    f"{_GAMMA}/deep/sub/config/deep.dcfg": f"config system Shadow {{\n{_DEPLOYMENT}{_TEST_PROFILE}",
}
_TO_WORKSPACE: Final = "../../../.."

# Each file group, in the order of its first copy's path, as (kind, moved to, moved from, deleted, kept with the
# start of its reason). orders.dtrx: alpha's and gamma's are one, beta's differs; system.dtrx: beta's includes
# that other orders.dtrx, so it is no copy of the others; system.dcfg: all three are one.
_EXPECTED_FILES: Final = [
    (".dcfg", f"{_SHARED}/datrix-alpha/tests/fixtures/app/config/system.dcfg", f"{_ALPHA}/app/config/system.dcfg",
     (f"{_BETA}/app/config/system.dcfg", f"{_GAMMA}/app/config/system.dcfg"), ()),
    (".dtrx", f"{_SHARED}/datrix-alpha/tests/fixtures/app/orders.dtrx", f"{_ALPHA}/app/orders.dtrx",
     (f"{_GAMMA}/app/orders.dtrx",), ()),
    (".dtrx", f"{_SHARED}/datrix-alpha/tests/fixtures/app/system.dtrx", f"{_ALPHA}/app/system.dtrx",
     (f"{_GAMMA}/app/system.dtrx",), ()),
    (".dtrx", f"{_SHARED}/datrix-alpha/tests/fixtures/catalog.dtrx", f"{_ALPHA}/catalog.dtrx",
     (f"{_GAMMA}/catalog.dtrx",), ((f"{_SHARED_SET}/catalog.dtrx", SHARED_SET_REASON), (f"{_BETA}/catalog.dtrx", BYTES_REASON))),
    (".dcfg", None, None, (), ((f"{_ALPHA}/config/negative.dcfg", SCREEN_REASON), (f"{_BETA}/config/negative.dcfg", SCREEN_REASON))),
    (".dcfg", None, None, (), ((f"{_ALPHA}/config/push.dcfg", SCREEN_REASON), (f"{_BETA}/config/push.dcfg", SCREEN_REASON))),
    (".dtrx", f"{_SHARED}/datrix-beta/tests/fixtures/area.dtrx", f"{_BETA}/area.dtrx",
     (f"{_GAMMA}/area.dtrx",), ((f"{_ALPHA}/diagnostics/area.dtrx", DIAGNOSTICS_COLLECTOR),)),
    (".dtrx", None, None, (), ((f"{_ALPHA}/fragment/head.dtrx", SCREEN_REASON), (f"{_BETA}/fragment/head.dtrx", SCREEN_REASON))),
    (".dtrx", None, None, (),
     ((f"{_GAMMA}/lint/rule.dtrx", f"datrix-gamma/tests/test_lint.py:2 {SITE_READ}"), (f"{_ALPHA}/rule.dtrx", LONE_COPY_REASON))),
    (".dtrx", f"{_SHARED}/datrix-alpha/tests/fixtures/walked.dtrx", f"{_ALPHA}/walked.dtrx",
     (f"{_GAMMA}/walked.dtrx",), ((f"{_BETA}/projects/walked.dtrx", f"datrix-beta/tests/test_walk.py:6 {SITE_READ}"),)),
]


@contextlib.contextmanager
def _planted(extra: Mapping[str, str] | None = None) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="fixture-dedupe-selftest-") as scratch:
        root = Path(scratch)
        write_files(root, {**_PLANTED, **(extra or {})})
        yield root


def _rel(path: Path | None, root: Path) -> str | None:
    return None if path is None else path.relative_to(root).as_posix()


def _file_view(placement: FilePlacement, root: Path) -> tuple[object, ...]:
    kept = tuple((_rel(copy.path, root), copy.reason) for copy in placement.kept)
    return (
        placement.group.kind,
        _rel(placement.target, root),
        _rel(placement.source, root),
        tuple(_rel(path, root) for path in placement.deleted),
        kept,
    )


def _matches(actual: tuple[object, ...], expected: tuple[object, ...]) -> bool:
    if actual[:4] != expected[:4]:
        return False
    kept_actual = actual[4]
    kept_expected = expected[4]
    assert isinstance(kept_actual, tuple) and isinstance(kept_expected, tuple)
    return len(kept_actual) == len(kept_expected) and all(
        path == want_path and str(reason).startswith(want_reason)
        for (path, reason), (want_path, want_reason) in zip(kept_actual, kept_expected, strict=True)
    )


def _plan(root: Path) -> Plan:
    with contextlib.redirect_stdout(io.StringIO()):
        return build_plan(root)


def _literal(plan: Plan, first: str) -> LiteralPlacement:
    found = [placement for placement in plan.literals if _rel(placement.group.members[0].module, plan.base_dir) == first]
    assert found, f"no literal group starts in {first}: {[_rel(p.group.members[0].module, plan.base_dir) for p in plan.literals]}"
    return found[0]


def _check_file_groups_placed_and_kept() -> None:
    with _planted() as root:
        plan = _plan(root)
        views = [_file_view(placement, root) for placement in plan.files]
    assert len(views) == len(_EXPECTED_FILES), f"file groups: expected {len(_EXPECTED_FILES)}, got {views}"
    for actual, want in zip(views, _EXPECTED_FILES, strict=True):
        assert _matches(actual, want), f"file group: expected {want}, got {actual}"


def _check_reference_difference_splits_a_group() -> None:
    with _planted() as root:
        plan = _plan(root)
        parts = {tuple(_rel(path, root) for path in part) for split in plan.splits for part in split.parts}
    assert (f"{_ALPHA}/app/system.dtrx", f"{_GAMMA}/app/system.dtrx") in parts, f"system.dtrx not one fixture: {parts}"
    assert (f"{_BETA}/app/system.dtrx",) in parts, f"beta's system.dtrx (its include differs) joined a group: {parts}"


def _check_literal_groups_placed() -> None:
    with _planted() as root:
        plan = _plan(root)
        orders = _literal(plan, "datrix-alpha/tests/test_literals.py")
        assert orders.target is not None, f"the Orders literal group moves nothing: {orders.refusal}"
        assert _rel(orders.target, root) == f"{_SHARED}/inline/datrix-alpha/tests/test_literals/ORDERS.dtrx", orders.target
        rewritten = [(_rel(site.module, root), site.name) for site in orders.rewritten]
        members = {site.name for site in orders.group.members}
        spaced = [(refused.site.name, refused.reason) for refused in orders.refused]
        push = [p for p in plan.literals if p.group.members[0].name == "PUSH_CONFIG"]
        negative = [p for p in plan.literals if p.group.members[0].name == "NEGATIVE_CONFIG"]
        template = [p for p in plan.literals if p.group.members[0].name == "TEMPLATE"]
        head = [p for p in plan.files if _rel(p.group.members[0].path, root) == f"{_ALPHA}/fragment/head.dtrx"]
        collisions = [p for p in plan.literals if _rel(p.group.members[0].module, root) == "datrix-alpha/tests/test_collide.py"]
        scoped = sorted(
            _rel(p.target, root) or ""
            for p in plan.literals
            if _rel(p.group.members[0].module, root) == "datrix-alpha/tests/test_scoped.py"
        )
    inline = f"{_SHARED}/inline/datrix-alpha/tests/test_scoped/TestScoped"
    assert scoped == [f"{inline}.test_one/source.dtrx", f"{inline}.test_two/source.dtrx"], f"function-scoped placements: {scoped}"
    assert rewritten == [("datrix-alpha/tests/test_literals.py", "ORDERS"), ("datrix-beta/tests/test_literals.py", "SVC")], rewritten
    assert members == {"ORDERS", "SVC", "SPACED"}, f"an f-string or an unassigned literal joined the group: {members}"
    assert spaced == [("SPACED", TEXT_REASON)], f"a literal of other exact text is not refused: {spaced}"
    assert len(push) == 1 and push[0].target is None and str(push[0].refusal).startswith(SCREEN_REASON), push
    assert len(negative) == 1 and negative[0].target is None and "refused load" in str(negative[0].refusal), negative
    assert len(template) == 1 and template[0].target is None and "formatter's walk refuses" in str(template[0].refusal), template
    assert len(head) == 1 and head[0].target is None and "formatter's walk refuses" in str(head[0].refusal), head
    moved = [p for p in collisions if p.target is not None]
    refused = [p for p in collisions if p.target is None]
    assert len(moved) == 1 and len(refused) == 1, f"colliding placements: {collisions}"
    assert "is taken by another group" in str(refused[0].refusal) and len(refused[0].refused) == 2, refused[0]


def _check_unevaluable_walk_site_refused_and_fails() -> None:
    with _planted({_UNKNOWN_WALK: _UNKNOWN_WALK_MODULE}) as root:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = dry_run(root)
    assert code == EXIT_VIOLATION, f"an unevaluable walk site must fail the listing (exit 1); got {code}"
    assert f"{_UNKNOWN_WALK}:2" in output.getvalue(), "the refused walk site is not listed"
    assert "project_FIXTURES is bound by no" in output.getvalue(), "the refusal does not say why"


def _check_helper_read_keeps_its_directory() -> None:
    """A directory handed to a tenant-fixture helper is read whole; a tmp directory it is handed is no site."""
    tenancy = "tenancy/system-no-tenant.dtrx"
    copies = {
        f"{package}/{tenancy}": "service shop.Tenancy('tenancy.dcfg') {\n}\n" for package in (_ALPHA, _BETA)
    }
    modules = {f"{name}/tests/test_tenancy.py": _HELPER_READ_MODULE for name in ("datrix-alpha", "datrix-beta")}
    with _planted({**copies, **modules}) as root:
        plan = _plan(root)
        found = [p for p in plan.files if _rel(p.group.members[0].path, root) == f"{_ALPHA}/{tenancy}"]
        assert len(found) == 1, f"the planted tenancy group is not one group: {found}"
        placement = found[0]
        assert placement.source is None, f"a copy read through the helper moves: {placement.source}"
        assert placement.deleted == (), f"a copy read through the helper is deleted: {placement.deleted}"
        kept = {_rel(copy.path, root) for copy in placement.kept}
        assert kept == set(copies), f"kept copies: {kept}"
        sites = {(_rel(walk.module, root), walk.reason) for walk in plan.walks.refused}
        assert not plan.walks.refused, f"the helper's tmp directory argument was taken for a fixture site: {sites}"


def _check_dry_run_lists_the_plan() -> None:
    with _planted() as root:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = dry_run(root)
        before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        listed = output.getvalue()
        after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    assert code == EXIT_PASS, f"dry run exit {code}:\n{listed}"
    for line in (
        f"-> {_SHARED}/datrix-alpha/tests/fixtures/catalog.dtrx",
        f"delete {_GAMMA}/catalog.dtrx",
        f"keep   {_BETA}/catalog.dtrx ({BYTES_REASON})",
        f"refuse  datrix-gamma/tests/test_literals.py:3 ({TEXT_REASON})",
        f"keep   {_SHARED_SET}/catalog.dtrx",
        "rewrite datrix-beta/tests/test_literals.py:1 SVC",
        "Summary: file groups 10 (move 6, delete 7, keep 12)",
        f"rewrite {_BETA}/app/system.dtrx: 'config/system.dcfg' -> '{_TO_WORKSPACE}/{_SHARED}/datrix-alpha/",
        "References: rewritten 1, refused 0",
    ):
        assert line in listed, f"dry run does not list {line!r}:\n{listed}"
    assert before == after, "the dry run wrote files"


def _check_missing_corpus_refused() -> None:
    with _planted() as root:
        shutil.rmtree(corpus_root(root))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = dry_run(root)
    assert code == EXIT_USAGE and "corpus root" in output.getvalue(), f"exit {code}: {output.getvalue()}"


def _check_references_resolve_by_their_rule() -> None:
    with _planted({f"{_ALPHA}/app/config/extra.dcfg": 'import "config/system.dcfg";\n'}) as root:
        tests = root / "datrix-alpha" / "tests"
        system = root / _ALPHA / "app" / "system.dtrx"
        found = [(ref.literal, ref.rule, _rel(ref.target, root)) for ref in fixture_references(system, ".dtrx", tests, ())]
        nested = root / _ALPHA / "app" / "config" / "extra.dcfg"
        imported = [(ref.rule, _rel(ref.target, root)) for ref in fixture_references(nested, ".dcfg", tests, ())]
        escaping = resolve_reference(system, "../../../../datrix-beta/tests/fixtures/area.dtrx", FILE_RULE, tests)
        route = resolve_reference(system, "/products/export.csv", PROJECT_RULE, tests)
    assert found == [
        ("orders.dtrx", FILE_RULE, f"{_ALPHA}/app/orders.dtrx"),
        ("config/system.dcfg", PROJECT_RULE, f"{_ALPHA}/app/config/system.dcfg"),
    ], found
    assert imported == [(PROJECT_RULE, f"{_ALPHA}/app/config/system.dcfg")], f"a .dcfg import resolves by the project root: {imported}"
    assert escaping is None, f"a reference leaving the tests tree resolved: {escaping}"
    assert route is None, f"a route literal resolved as a file: {route}"


def _rewrites(plan: Plan) -> set[tuple[str | None, str, str]]:
    return {(_rel(r.placed, plan.base_dir), r.reference.literal, r.literal) for r in plan.followed.rewrites}


def _apply_moves(plan: Plan) -> None:
    """Write *plan*'s moves into its workspace: each moved copy at its shared place with its rewrites, each
    staying file with its rewrites, each deleted copy gone."""
    rewrites = plan.followed.rewrites
    moved_to = moved_copies(plan.files)
    readers = {rewrite.reference.source for rewrite in rewrites} | set(moved_to)
    texts = {reader: placed_text(reader, rewrites) for reader in readers}
    for leaving in plan.followed.moves:
        leaving.unlink()
    for reader, text in texts.items():
        place = moved_to.get(reader, reader)
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_bytes(text.encode("utf-8", errors="surrogateescape"))


def _check_references_follow_their_file() -> None:
    shared_alpha = f"{_SHARED}/datrix-alpha/tests/fixtures"
    with _planted(_BILLING_PLANTED) as root:
        plan = _plan(root)
        rewrites = _rewrites(plan)
        moves = {_rel(old, root): _rel(new, root) for old, new in plan.followed.moves.items()}
        untouched = [r for r in plan.followed.rewrites if _rel(r.reference.source, root) == f"{_ALPHA}/app/system.dtrx"]
        named = {r.target: r.reference.target.read_bytes() for r in plan.followed.rewrites}
        _apply_moves(plan)
        tree_root_of = TreeRoots(root, plan.packages)
        for rewrite in plan.followed.rewrites:
            found = resolve_reference(
                rewrite.placed, rewrite.literal, rewrite.reference.rule, tree_root_of(rewrite.placed), reach=(shared_root(root),)
            )
            assert found is not None and found.target == rewrite.target, f"{rewrite} reads back as {found}"
            assert rewrite.target.read_bytes() == named[rewrite.target], f"{rewrite.literal} names other bytes"
    assert rewrites == {
        (f"{_SHARED}/datrix-beta/tests/fixtures/billing/system.dtrx", "billing.dtrx", f"{_TO_WORKSPACE}/datrix-alpha/tests/fixtures/lib/billing.dtrx"),
        (f"{_SHARED}/datrix-beta/tests/fixtures/billing/system.dtrx", "config/pay.dcfg", f"{_TO_WORKSPACE}/datrix-alpha/tests/fixtures/lib/config/pay.dcfg"),
        (f"{_BETA}/app/system.dtrx", "config/system.dcfg", f"{_TO_WORKSPACE}/{shared_alpha}/app/config/system.dcfg"),
    }, rewrites
    assert not plan.followed.refused, plan.followed.refused
    assert moves[f"{_GAMMA}/billing/billing.dtrx"] == f"{shared_alpha}/lib/billing.dtrx", moves
    assert moves[f"{_ALPHA}/app/system.dtrx"] == f"{shared_alpha}/app/system.dtrx", moves
    assert not untouched, f"a reference that still resolves from the shared place was rewritten: {untouched}"


def _check_reference_that_cannot_follow_holds_its_copy() -> None:
    with _planted({**_BILLING_PLANTED, _CONFINED_READER: 'import "config/pay.dcfg";\n'}) as root:
        plan = _plan(root)
        views = {_rel(p.group.members[0].path, root): p for p in plan.files}
        confined = [r for r in plan.followed.rewrites if _rel(r.reference.source, root) == _CONFINED_READER]
    pay = views[f"{_ALPHA}/lib/config/pay.dcfg"]
    kept_pay = {_rel(kept.path, root): kept.reason for kept in pay.kept}
    assert _rel(pay.source, root) == f"{_ALPHA}/lib/config/pay.dcfg", f"pay.dcfg's other copies stop sharing: {pay}"
    assert kept_pay[f"{_BETA}/billing/config/pay.dcfg"].startswith(READER_REASON), kept_pay
    assert "its loader confines it to" in kept_pay[f"{_BETA}/billing/config/pay.dcfg"], kept_pay
    system = views[f"{_BETA}/billing/system.dtrx"]
    assert system.target is None and str(system.refusal).startswith(FOLLOW_REASON), system
    assert "in another package's tests/ tree" in str(system.refusal), system.refusal
    assert not confined, f"a confined import was rewritten out of its project: {confined}"
    assert not plan.followed.refused, plan.followed.refused


def _check_shadowed_reference_refused_and_fails() -> None:
    with _planted(_SHADOWED_PLANTED) as root:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = dry_run(root)
        before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    listed = output.getvalue()
    assert code == EXIT_VIOLATION, f"a reference that cannot be read back must fail the listing (exit 1); got {code}:\n{listed}"
    assert f"refuse  {_SHADOWED_READER}: 'config/deep.dcfg' (the rewritten path" in listed, listed
    assert "References: rewritten 1, refused 1" in listed, listed
    assert f"{_SHARED}/datrix-beta/tests/fixtures/deep/sub/config/deep.dcfg" not in before, "the listing wrote the placement"


def _check_static_paths_follow_the_text() -> None:
    module = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "KIND = 'dtrx'\n"
        "NAMED = ROOT.joinpath('fixtures', f'orders.{KIND}').with_suffix('.dcfg')\n"
        "OPENED = open('x')\n"
    )
    # Two modules of one tests tree importing a name from each other: a cycle the evaluator refuses.
    cycle = {
        "datrix-alpha/tests/unit/cycle_a.py": "from tests.unit.cycle_b import LOOP\n",
        "datrix-alpha/tests/unit/cycle_b.py": "from tests.unit.cycle_a import LOOP\n",
    }
    with _planted({"datrix-alpha/tests/unit/test_paths.py": module, **cycle}) as root:
        tests = root / "datrix-alpha" / "tests"
        path = tests / "unit" / "test_paths.py"
        evaluator = StaticEvaluator()
        scope = evaluator.scope(path, tests)
        named = evaluator.path(ast.parse("NAMED", mode="eval").body, scope)
        refusal = _refusal(evaluator, "OPENED", scope)
        looped = _refusal(evaluator, "LOOP", evaluator.scope(tests / "unit" / "cycle_a.py", tests))
    assert named == path.resolve().parents[1] / "fixtures" / "orders.dcfg", named
    assert refusal.startswith("open is bound by no"), f"a call the text does not show was evaluated: {refusal!r}"
    assert looped.endswith("(a cycle)"), f"an import cycle was not refused: {looped!r}"


def _refusal(evaluator: StaticEvaluator, expression: str, scope: ModuleScope) -> str:
    """Why *evaluator* cannot evaluate *expression* in *scope* (empty when it can)."""
    try:
        evaluator.evaluate(ast.parse(expression, mode="eval").body, scope)
    except UnevaluableError as exc:
        return str(exc)
    return ""


# Test modules of gamma reading copies that leave: its catalog.dtrx, app/system.dtrx, app/orders.dtrx, area.dtrx
# and walked.dtrx are deleted; lint/rule.dtrx stays (a walk reads it).
_SITES_MODULE: Final = "datrix-gamma/tests/unit/test_sites.py"
_PAIRS_MODULE: Final = "datrix-gamma/tests/test_pairs.py"
_CONFLICT_MODULE: Final = "datrix-gamma/tests/test_conflict.py"
_SITES_PLANTED: Final[Mapping[str, str]] = {
    _SITES_MODULE: '''from pathlib import Path

from datrix_testing.conftest_plugin import FixturePairSpec, build_spec_app
from datrix_testing.fixture_names import FIXTURE_SYSTEM

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CATALOG = FIXTURES / "catalog.dtrx"
SYSTEM = FIXTURES.joinpath("app", FIXTURE_SYSTEM)
AREA = Path(__file__).resolve().parents[2] / "tests/fixtures/area.dtrx"
RULE = FIXTURES / "lint" / "rule.dtrx"
WALKED = (FIXTURES / "walked.dtrx").read_text()
WHERE = (FIXTURES / "app" / "orders.dtrx").parent


def read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_by_name() -> None:
    assert read("orders.dtrx")


def test_spec(tmp_dir: Path) -> None:
    build_spec_app(tmp_dir, FixturePairSpec("catalog", "catalog.dtrx"))


def test_example(root: Path) -> None:
    assert (root / "examples" / "catalog.dtrx").exists()


SPLIT = (
    FIXTURES
    / "catalog.dtrx"
)
''',
    _PAIRS_MODULE: '''from pathlib import Path

from datrix_testing.conftest_plugin import FixturePairSpec, register_fixture_pairs

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SPECS = [
    FixturePairSpec("orders", "app/orders.dtrx"),
    FixturePairSpec("rule", dtrx_filename="lint/rule.dtrx"),
]
register_fixture_pairs(FIXTURES_DIR, SPECS, globals())
''',
}
_CONFLICT_PLANTED: Final[Mapping[str, str]] = {
    _CONFLICT_MODULE: '''from pathlib import Path

from tests.helpers import shared_fixture

CATALOG = Path(__file__).resolve().parent / "fixtures" / "catalog.dtrx"
''',
}
_SHARED_ALPHA_ARGUMENT: Final = "datrix-alpha/tests/fixtures"


def _check_test_sites_rewritten() -> None:
    with _planted(_SITES_PLANTED) as root:
        # CRLF line endings, so a rewrite spanning lines must match the module's bytes as written.
        crlf = root / _SITES_MODULE
        crlf.write_bytes(_SITES_PLANTED[_SITES_MODULE].replace("\n", "\r\n").encode("utf-8"))
        plan = _plan(root)
        edits = {_rel(edit.module, root): edit for edit in plan.sites.edits}
        sites_edit = edits[_SITES_MODULE]
        written = {(r.written, r.replacement, r.kind) for r in sites_edit.rewrites}
        pairs = {(r.written, r.replacement, r.kind) for r in edits[_PAIRS_MODULE].rewrites}
        literal = edits["datrix-alpha/tests/test_literals.py"]
        sites_source = rewritten_source(sites_edit).decode("utf-8")
        literal_source = rewritten_source(literal).decode("utf-8")
        for rewrite in plan.sites.rewrites:
            assert shared_root(root) / accessor_argument(rewrite.replacement) == rewrite.shared, rewrite
            if rewrite.read is not None:
                assert plan.followed.moves[rewrite.read] == rewrite.shared, f"{rewrite} reads no copy that leaves"
    assert written == {
        ('FIXTURES / "catalog.dtrx"', f'{ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx")', PATH_SITE),
        ('FIXTURES.joinpath("app", FIXTURE_SYSTEM)', f'{ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/app/system.dtrx")', PATH_SITE),
        (
            'Path(__file__).resolve().parents[2] / "tests/fixtures/area.dtrx"',
            f'{ACCESSOR}("datrix-beta/tests/fixtures/area.dtrx")',
            PATH_SITE,
        ),
        ('FIXTURES / "walked.dtrx"', f'{ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/walked.dtrx")', PATH_SITE),
        ('FIXTURES\r\n    / "catalog.dtrx"', f'{ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx")', PATH_SITE),
    }, written
    assert pairs == {('"app/orders.dtrx"', f'{ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/app/orders.dtrx")', PAIR_SITE)}, pairs
    assert sites_edit.import_after == 4, f"the accessor import goes after the last import: {sites_edit.import_after}"
    ast.parse(sites_source)
    lines = sites_source.splitlines()
    assert lines[4] == ACCESSOR_IMPORT, lines[:6]
    for line in (
        f'CATALOG = {ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx")',
        f'WALKED = ({ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/walked.dtrx")).read_text()',
        'RULE = FIXTURES / "lint" / "rule.dtrx"',
        'WHERE = (FIXTURES / "app" / "orders.dtrx").parent',
    ):
        assert line in lines, f"rewritten module lacks {line!r}:\n{sites_source}"
    split = f'SPLIT = (\r\n    {ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx")\r\n)\r\n'
    assert split in sites_source, f"the multi-line site is not rewritten in place, CRLF kept:\n{sites_source!r}"
    assert lines[4] + "\r\n" in sites_source, "the accessor import does not take the module's line ending"
    ast.parse(literal_source)
    literal_lines = literal_source.splitlines()
    inline = "inline/datrix-alpha/tests/test_literals/ORDERS.dtrx"
    assert literal_lines[0] == ACCESSOR_IMPORT, literal_lines[:2]
    assert literal_lines[1] == f'ORDERS = {ACCESSOR}("{inline}").read_text(encoding="utf-8")', literal_lines[:2]


def _check_unevaluable_test_site_refused() -> None:
    with _planted({**_SITES_PLANTED, **_CONFLICT_PLANTED}) as root:
        modules = [root / _SITES_MODULE, root / _PAIRS_MODULE, root / _CONFLICT_MODULE]
        before = [module.read_bytes() for module in modules]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = dry_run(root)
        after = [module.read_bytes() for module in modules]
    listed = output.getvalue()
    assert code == EXIT_PASS, f"a refused test site is a hand edit, not a failed listing; got {code}:\n{listed}"
    for line in (
        f'refuse  {_SITES_MODULE}:12 FIXTURES / "app" / "orders.dtrx" (it reads .parent of {_GAMMA}/app/orders.dtrx',
        f'refuse  {_SITES_MODULE}:20 "orders.dtrx" (it names a copy that leaves in an expression the script cannot',
        f'refuse  {_SITES_MODULE}:24 "catalog.dtrx" (it names a copy that leaves, and tmp_dir is bound by no',
        f"refuse  {_CONFLICT_MODULE}:5 Path(__file__)",
        f"the module binds {ACCESSOR} to something else",
        "Test sites: rewritten 14 (path 5, pair 1, literal 8), refused 4",
    ):
        assert line in listed, f"dry run does not list {line!r}:\n{listed}"
    site_lines = "".join(line for line in listed.splitlines() if line.startswith(("  rewrite", "  refuse")))
    assert "rule.dtrx" not in site_lines, f"a site reading a kept copy was rewritten or refused:\n{listed}"
    assert '"examples"' not in site_lines, f"a path whose literal tail ends no leaving copy was refused:\n{listed}"
    assert before == after, "the listing rewrote a test module"


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under *root* but the run records, by workspace-relative path."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_relative_to(root / RECORD_DIR)
    }


def _tree_dirs(root: Path) -> set[str]:
    """Every directory under *root* but the run records."""
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir() and not path.is_relative_to(root / ".tmp")}


def _check_planted_run_writes_and_records() -> None:
    with _planted({**_SITES_PLANTED, **_BILLING_PLANTED}) as root:
        plan = _plan(root)
        moves = {_rel(old, root): _rel(new, root) for old, new in plan.followed.moves.items()}
        before = _tree_bytes(root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = write_run(root, corpus_root(root))
        after = _tree_bytes(root)
        records = sorted((root / RECORD_DIR).glob(f"*/{RECORD_FILE}"))
        record = json.loads(records[0].read_text(encoding="utf-8")) if records else {}
        kept = records[0].parent / OLD_DIR if records else root
        replaced = [*record.get("changed", []), *record.get("deleted", [])]
        old_kept = {rel: (kept / rel).read_bytes() for rel in replaced}
        pruned = not (root / _GAMMA / "billing").exists()
    assert code == EXIT_PASS and len(records) == 1, f"exit {code}, records {records}:\n{output.getvalue()}"
    assert record["moves"] == moves, f"the record's old -> new is not the plan's: {record['moves']}"
    assert set(after) == (set(before) - set(moves)) | set(record["created"]), "the written tree holds other files"
    assert old_kept == {rel: before[rel] for rel in replaced}, "the record does not hold each replaced file's old bytes"
    assert after[f"{_SHARED}/{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx"] == before[f"{_ALPHA}/catalog.dtrx"], "the moved copy's bytes changed"
    assert after[f"{_BETA}/catalog.dtrx"] == before[f"{_BETA}/catalog.dtrx"], "a copy of other bytes was not kept"
    billing = after[f"{_SHARED}/datrix-beta/tests/fixtures/billing/system.dtrx"]
    assert f"'{_TO_WORKSPACE}/datrix-alpha/tests/fixtures/lib/billing.dtrx'".encode() in billing, billing
    assert f'CATALOG = {ACCESSOR}("{_SHARED_ALPHA_ARGUMENT}/catalog.dtrx")'.encode() in after[_SITES_MODULE], after[_SITES_MODULE]
    assert pruned, "a directory every copy left was not removed"
    written = record["proof"][1]
    assert written["failures"] == 0 and written["texts"] and written["references"] and written["sites"], record["proof"]
    assert [(site["module"], site["line"]) for site in record["refused_sites"]] == [
        (_SITES_MODULE, 12), (_SITES_MODULE, 20), (_SITES_MODULE, 24)
    ], record["refused_sites"]
    assert "semantic baselines proven in 0 package(s)" in output.getvalue(), output.getvalue()


def _check_included_service_stays_with_its_entry() -> None:
    """A service whose config path resolves from the entry including it stays beside that entry."""
    service = "service shop.Push('config/push.dcfg') {\n}\n"
    entries = {f"{package}/push/system.dtrx": f"include 'push.dtrx';\nsystem {name}('config/s.dcfg') {{\n}}\n"
               for package, name in ((_ALPHA, "Alpha"), (_BETA, "Beta"))}
    copies = {f"{package}/push/push.dtrx": service for package in (_ALPHA, _BETA)}
    configs = {f"{package}/push/config/push.dcfg": "config service push {\n}\n" for package in (_ALPHA, _BETA)}
    with _planted({**entries, **copies, **configs}) as root:
        plan = _plan(root)
        placement = next(p for p in plan.files if _rel(p.group.members[0].path, root) == f"{_ALPHA}/push/push.dtrx")
        kept = {_rel(copy.path, root) for copy in placement.kept}
        config = next(p for p in plan.files if _rel(p.group.members[0].path, root) == f"{_ALPHA}/push/config/push.dcfg")
    assert placement.source is None and placement.deleted == (), f"an included service moves: {placement.source}"
    assert kept == set(copies), f"kept copies: {kept}"
    assert config.source is not None, "the service's own config lost its shared copy: only the service must stay"


def _check_second_run_reads_what_the_first_rewrote() -> None:
    """A reference the first run rewrote into the shared directory is a reference to the second."""
    with _planted({**_SITES_PLANTED, **_BILLING_PLANTED}) as root:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            first = write_run(root, corpus_root(root))
            written = _tree_bytes(root)
            plan = build_plan(root)
            second = write_run(root, corpus_root(root))
        into_shared = [
            placed for placed, expected in plan.followed.expected.items()
            if not placed.is_relative_to(shared_root(root)) and any(t.is_relative_to(shared_root(root)) for t in expected)
        ]
        again = _tree_bytes(root)
    assert first == EXIT_PASS and second == EXIT_PASS, f"exits {first}, {second}:\n{output.getvalue()}"
    assert into_shared, "no fixture staying in a package names a shared copy: the check proves nothing"
    assert not plan.followed.moves, f"the second run moves more: {plan.followed.moves}"
    assert again == written, "the second run changed the tree"


def _check_mismatch_refused_and_nothing_written() -> None:
    with _planted() as root:
        plan = _plan(root)
        # A deleted copy edited after planning, so its bytes differ from the copy replacing it.
        edited = root / _GAMMA / "catalog.dtrx"
        edited.write_bytes(edited.read_bytes() + b"// edited after planning\r\n")
        before, dirs = _tree_bytes(root), _tree_dirs(root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            mismatch = write_plan(plan, corpus_root(root))
            elsewhere = write_plan(plan, CORPUS_ROOT)
        unchanged = _tree_bytes(root) == before and _tree_dirs(root) == dirs
        recorded = (root / RECORD_DIR).exists()
    listed = output.getvalue()
    assert mismatch == EXIT_VIOLATION and elsewhere == EXIT_VIOLATION, f"exits {mismatch}, {elsewhere}:\n{listed}"
    assert f"differ from {_GAMMA}/catalog.dtrx, which it replaces" in listed, listed
    assert "the accessor the rewritten tests import reads the corpus" in listed, listed
    assert unchanged and not recorded, "a refused write wrote a file"


def _check_unresolved_reference_refused() -> None:
    with _planted() as root:
        plan = _plan(root)
        # beta's system.dtrx stays and includes its own orders.dtrx, which is deleted after planning.
        (root / _BETA / "app" / "orders.dtrx").unlink()
        before = _tree_bytes(root)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = write_plan(plan, corpus_root(root))
        unchanged = _tree_bytes(root) == before
    listed = output.getvalue()
    assert code == EXIT_VIOLATION, f"exit {code}:\n{listed}"
    assert f"{_BETA}/app/system.dtrx: names {_BETA}/app/orders.dtrx, which is no file (consumed - produced)" in listed, listed
    assert unchanged, "a refused write wrote a file"


def _check_changed_site_and_text_refused() -> None:
    with _planted(_SITES_PLANTED) as root:
        plan = _plan(root)
        write = write_set(plan)
        old = old_bytes(write)
        clean = prove(plan, PlannedTree(write), old)
        module = root / _SITES_MODULE
        catalog = shared_root(root) / _SHARED_ALPHA_ARGUMENT / "catalog.dtrx"
        literal = shared_root(root) / "inline/datrix-alpha/tests/test_literals/ORDERS.dtrx"
        swapped = write.changed[module].replace(b'catalog.dtrx")', b'walked.dtrx")', 1)
        site = prove(plan, PlannedTree(WriteSet(write.created, {**write.changed, module: swapped}, write.deleted)), old)
        bytes_changed = {**write.created, catalog: write.created[catalog] + b"// x\r\n", literal: write.created[literal] + b" "}
        texts = prove(plan, PlannedTree(WriteSet(bytes_changed, write.changed, write.deleted)), old)
    assert not clean.failures and clean.texts and clean.references and clean.sites, clean
    assert any(failure.startswith(f"{_SITES_MODULE}: cannot be read back") for failure in site.failures), site.failures
    expected = (
        f"differ from {_GAMMA}/catalog.dtrx, which it replaces",
        f"reads other bytes than {_GAMMA}/catalog.dtrx",
        "does not read back as the text of datrix-alpha/tests/test_literals.py:1 ORDERS",
        "datrix-alpha/tests/test_literals.py:1: ",
    )
    for fragment in expected:
        assert any(fragment in failure for failure in texts.failures), f"no failure holds {fragment!r}: {texts.failures}"


# alpha's and gamma's lone.dtrx are one and move; their config path names no file in their package, while the
# corpus holds a config/system.dcfg above the shared directory, in another project.
_LONE_PLANTED: Final[Mapping[str, str]] = {
    f"{_ALPHA}/lone/lone.dtrx": "system Lone('config/system.dcfg') {\n}\n",
    f"{_GAMMA}/lone/lone.dtrx": "system Lone('config/system.dcfg') {\n}\n",
    f"{_SHARED_SET}/corpus/config/system.dcfg": "config system Store {\n  profile test as \"test\" {\n  }\n}\n",
}


def _check_moved_copy_names_no_other_project() -> None:
    with _planted(_LONE_PLANTED) as root:
        plan = _plan(root)
        write = write_set(plan)
        proof = prove(plan, PlannedTree(write), old_bytes(write))
        moved = shared_root(root) / "datrix-alpha" / "tests" / "fixtures" / "lone" / "lone.dtrx"
        tree_root = TreeRoots(root, plan.packages)(moved)
        expected = plan.followed.expected.get(moved)
    assert expected == (), f"the moved lone.dtrx is not planned to name nothing: {expected}"
    assert tree_root == (shared_root(root) / "datrix-alpha" / "tests").resolve(), tree_root
    assert not proof.failures, f"a moved copy names a file of another project: {proof.failures}"


def _check_untranslated_hash_change_named() -> None:
    register_installed_parsers()
    corpus = SemanticBaselineCorpus(package_root=CORPUS_ROOT.parents[3])
    book = (CORPUS_ROOT / "services" / "book.dtrx").resolve()
    library = (CORPUS_ROOT / "library.dtrx").resolve()
    to_shared = Translation({book: CORPUS_ROOT.resolve() / "shared" / "datrix-alpha" / "book.dtrx"}, {})
    unrelated = Translation({(CORPUS_ROOT / "absent.dtrx").resolve(): CORPUS_ROOT.resolve() / "shared" / "absent.dtrx"}, {})
    header = Translation({}, {library: {"config/system.dcfg": "../config/system.dcfg"}})
    include = Translation({}, {library: {"services/book.dtrx": "shared/book.dtrx"}})
    other_file = Translation({}, {book: {"config/system.dcfg": "../config/system.dcfg"}})
    plain, translated, untouched, by_header, by_include, by_other = entry_hashes(
        library, corpus, (AS_IS, to_shared, unrelated, header, include, other_file)
    )
    assert plain != translated, "an entry reaching a moved file hashes the same with the move mapped"
    assert plain == untouched, "an entry reaching no moved file changes its hash with the move mapped"
    assert len({plain, by_header, by_include}) == 3, "a rewritten header config path or include is not dumped as its new text"
    assert plain == by_other, "a reference text rewritten in another file changes the dump of this one"
    before = BaselineBefore(
        corpus, {"lib": plain, "other": "o1", "gone": "g1"}, {"lib": translated, "other": "o1", "gone": "g1"}, frozenset({"gone"})
    )
    legal = BaselineAfter({"lib": translated, "other": "o1", "shared/new.dtrx": "s1"}, frozenset({"shared/new.dtrx"}))
    assert baseline_failures(before, legal) == [], baseline_failures(before, legal)
    assert updated_manifest({"lib": plain, "other": "stale", "gone": "g1"}, before, legal) == {
        "lib": translated, "other": "stale", "shared/new.dtrx": "s1"
    }
    assert updated_manifest({"lib": "drifted", "other": "o1", "gone": "g1"}, before, legal) == {
        "lib": "drifted", "other": "o1", "shared/new.dtrx": "s1"
    }, "a translated key whose committed hash was already stale takes its new hash: drift the move did not cause is banked"
    for after, named in (
        (BaselineAfter({"lib": translated, "other": "o2"}, frozenset()), "other: semantic output CHANGED"),
        (BaselineAfter({"lib": plain + "x", "other": "o1"}, frozenset()), "lib: hashes"),
        (BaselineAfter({"lib": translated, "other": "o1", "stray": "s"}, frozenset()), "stray: appeared"),
    ):
        failures = baseline_failures(before, after)
        assert any(failure.startswith(named) for failure in failures), f"{named!r} not named: {failures}"


def _check_rollback_puts_every_byte_back() -> None:
    with _planted({**_SITES_PLANTED, **_BILLING_PLANTED}) as root:
        plan = _plan(root)
        write = write_set(plan)
        before, dirs = _tree_bytes(root), _tree_dirs(root)
        transaction = WriteTransaction(root, old_bytes(write), root / RECORD_DIR / "rollback")
        transaction.keep_old()
        transaction.apply(write, [package / PackageMarker.TESTS.value for package in plan.packages])
        written = _tree_bytes(root)
        transaction.restore()
        restored, restored_dirs = _tree_bytes(root), _tree_dirs(root)
    assert written != before, "the write changed nothing"
    assert restored == before, f"the rollback left other files: {sorted(set(restored) ^ set(before))}"
    assert restored_dirs == dirs, f"the rollback left other directories: {sorted(restored_dirs ^ dirs)}"


_PROCESS_MODULES: Final = frozenset({"subprocess", "multiprocessing", "pty", "pexpect", "sh", "plumbum"})
_PROCESS_PREFIXES: Final = ("system", "popen", "startfile", "exec", "spawn", "posix_spawn", "fork")


def _process_uses(module: Path) -> list[str]:
    """Each import of a process-running module and each ``os`` process call in *module*."""
    found: list[str] = []
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
        if isinstance(node, ast.ImportFrom):
            names = [node.module or "", *(alias.name for alias in node.names)]
        found.extend(f"{module.name}:{node.lineno} imports {name}" for name in names if name.split(".")[0] in _PROCESS_MODULES)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr.startswith(_PROCESS_PREFIXES):
            found.append(f"{module.name}:{node.lineno} calls os.{node.attr}")
    return found


def _check_runs_no_process() -> None:
    with tempfile.TemporaryDirectory(prefix="fixture-dedupe-process-") as scratch:
        planted = write_files(Path(scratch), {"runs.py": "import os\nfrom subprocess import run\n\nos.system('x')\n"})[0]
        caught = _process_uses(planted)
    assert caught == ["runs.py:2 imports subprocess", "runs.py:4 calls os.system"], f"the matcher misses a process: {caught}"
    package = Path(__file__).resolve().parent
    found = [use for module in sorted(package.glob("*.py")) for use in _process_uses(module)]
    assert not found, f"the script can start a process (a git command among them): {found}"


CHECKS: Final[list[NamedCheck]] = named_checks(
    [
        _check_references_resolve_by_their_rule,
        _check_static_paths_follow_the_text,
        _check_file_groups_placed_and_kept,
        _check_reference_difference_splits_a_group,
        _check_literal_groups_placed,
        _check_unevaluable_walk_site_refused_and_fails,
        _check_helper_read_keeps_its_directory,
        _check_included_service_stays_with_its_entry,
        _check_second_run_reads_what_the_first_rewrote,
        _check_references_follow_their_file,
        _check_reference_that_cannot_follow_holds_its_copy,
        _check_shadowed_reference_refused_and_fails,
        _check_test_sites_rewritten,
        _check_unevaluable_test_site_refused,
        _check_dry_run_lists_the_plan,
        _check_missing_corpus_refused,
        _check_planted_run_writes_and_records,
        _check_mismatch_refused_and_nothing_written,
        _check_unresolved_reference_refused,
        _check_changed_site_and_text_refused,
        _check_moved_copy_names_no_other_project,
        _check_untranslated_hash_change_named,
        _check_rollback_puts_every_byte_back,
        _check_runs_no_process,
    ]
)
