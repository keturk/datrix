"""The self-test of ``dev/fixture-author.ps1``: needs, area plan, scaffold, verification and drafting on planted inputs.

The checks of the ``needs`` inventory live in ``needs_checks``, those of the corpus library plan and check
in ``library_self_checks``, those of drafting the library in ``library_draft_self_checks``, those of
repointing a package in ``repoint_self_checks`` and those of pruning one in ``prune_self_checks``; they run
after these.

The needs and the plan are proven on a planted catalog whose codes no real catalog declares; the
scaffold on a temporary project root; verification on a planted package whose area project the real
analyzer runs: one annotated variant no clean project provokes, one service declaring a version
that is no semver (a cascade until its variants are annotated), and the same area annotated with
exactly what it reports.

Drafting is proven over a loopback model server on a planted package. The two variants of its
area are read off the real analyzer first (what a loose and a non-semver service version report),
so the self-test names none: the model answers one cleanly, and the other first with an extra
service provoking the first variant unannotated -- a cascade, sent back with the instruction to
move the construct -- then without it, and both land. A draft holding a secret-looking literal is
queued and never written; a run with no model to serve exits non-zero and writes nothing.
"""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.dev.fixture_author.library_draft_self_checks import CHECKS as LIBRARY_DRAFT_CHECKS
from datrix_scripts.dev.fixture_author.library_self_checks import CHECKS as LIBRARY_CHECKS
from datrix_scripts.dev.fixture_author.needs_checks import CHECKS as NEEDS_CHECKS
from datrix_scripts.dev.fixture_author.prune_self_checks import CHECKS as PRUNE_CHECKS
from datrix_scripts.dev.fixture_author.repoint_self_checks import CHECKS as REPOINT_CHECKS
from datrix_scripts.gate_harness import CheckFunc, write_files

if TYPE_CHECKING:
    from datrix_semantic.diagnostics.catalog import DiagnosticCatalog
    from datrix_testing.cases.package import PackageCases

    from datrix_scripts.local_llm import LocalLlmSettings
    from datrix_scripts.local_llm_loopback import Chat, LoopbackOllama

#: A planted catalog: an analysis family with two codes, a seed-document family, and a
#: target-check code. No real catalog declares these codes.
_PLANTED_CATALOG: Final = """\
[PLANTA001]
severity = "error"
summary = "A planted analysis code"

[PLANTA001.first]
placeholders = []
problem = "The first planted variant."
expected = "nothing"
fix = "Nothing."

[PLANTA001.second]
placeholders = []
problem = "The second planted variant."
expected = "nothing"
fix = "Nothing."

[PLANTA002]
severity = "error"
summary = "A planted code that ends analysis"

[PLANTA002.stops]
placeholders = []
problem = "The planted halting variant."
expected = "nothing"
fix = "Nothing."

[PLANTS001]
severity = "error"
summary = "A planted seed-document code"

[PLANTS001.row]
placeholders = []
problem = "The planted seed variant."
expected = "nothing"
fix = "Nothing."

[PLANTT001]
severity = "error"
summary = "A planted target-check code"

[PLANTT001.target]
target_check = true
placeholders = []
problem = "The planted target-check variant."
expected = "nothing"
fix = "Nothing."
"""

_FIRST: Final = "PLANTA001.first"
_SECOND: Final = "PLANTA001.second"
_STOPS: Final = "PLANTA002.stops"
_SEED_ROW: Final = "PLANTS001.row"
_TARGET: Final = "PLANTT001.target"
_HALTING: Final = frozenset({"PLANTA002"})
_SEEDED: Final = frozenset({"PLANTS001"})
_LANGUAGES: Final = ("beta", "alpha")

_CENSUS: Final = f'PROVEN_BY_CODE_TEST: dict[str, str] = {{"{_SECOND}": "unit/test_x.py::test_y"}}\n'
_MENTION: Final = '"""Names PROVEN_BY_CODE_TEST in prose only."""\n'

#: The planted area's one service: ``shop.PlantService``, configured at ``config/plant-service.dcfg``.
_PLANT_STEM: Final = "plant"
_CLEAN_VERSION: Final = "1.0.0"
_NO_SEMVER: Final = "banana"


def _catalog() -> DiagnosticCatalog:
    from datrix_semantic.diagnostics.catalog import parse_catalog

    return parse_catalog(_PLANTED_CATALOG, "planted catalog")


def _check_needs_exclude_target_checks_and_proven_by_code() -> None:
    from datrix_scripts.dev.fixture_author.diagnostics import package_needs

    catalog = _catalog()
    analysis = package_needs(catalog, owns_target_checks=False, proven_by_code={_SECOND})
    targets = package_needs(catalog, owns_target_checks=True, proven_by_code={_SECOND})
    assert analysis == (_FIRST, _STOPS, _SEED_ROW), f"analysis needs are {analysis}"
    assert targets == (_TARGET,), f"target-check needs are {targets}"


def _check_the_proven_by_code_module_is_the_one_assigning_it() -> None:
    from datrix_scripts.dev.fixture_author.diagnostics import FixtureAuthorError, proven_by_code_module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_files(root, {"tests/unit/test_census.py": _CENSUS, "tests/unit/test_other.py": _MENTION})
        assert proven_by_code_module(root) == "tests.unit.test_census"
        write_files(root, {"tests/fixtures/diagnostics/test_planted.py": _CENSUS})
        assert proven_by_code_module(root) == "tests.unit.test_census", "a file under tests/fixtures is no test module"
        write_files(root, {"tests/unit/test_second.py": _CENSUS})
        try:
            proven_by_code_module(root)
        except FixtureAuthorError as error:
            assert "2 test module(s)" in str(error), str(error)
        else:
            raise AssertionError("two modules assigning the mapping must be refused")


def _check_a_halting_code_plans_to_its_halt_area_and_a_seed_code_to_a_seeded_area() -> None:
    from datrix_scripts.dev.fixture_author.diagnostics import plan_areas

    areas = plan_areas((_FIRST, _STOPS, _SEED_ROW), owns_target_checks=False, halting=_HALTING, seed_document_codes=_SEEDED)
    shape = [(a.name, a.variants, a.seeded, a.target_checks) for a in areas]
    assert shape == [
        ("planta", (_FIRST,), False, False),
        ("planta-halt", (_STOPS,), False, False),
        ("plants-seeded", (_SEED_ROW,), True, False),
    ], f"the plan is {shape}"
    diagnostics = Path("diagnostics")
    assert areas[2].entry(diagnostics) == diagnostics / "plants-seeded" / "system.dtrx"
    assert areas[0].entry(diagnostics) == diagnostics / "planta.dtrx"


def _check_target_checks_plan_one_area_naming_no_language() -> None:
    from datrix_scripts.dev.fixture_author.diagnostics import TARGETS_AREA, plan_areas
    from datrix_scripts.dev.fixture_author.drafting import area_header

    areas = plan_areas((_TARGET,), owns_target_checks=True, halting=_HALTING, seed_document_codes=_SEEDED)
    shape = [(a.name, a.variants, a.seeded, a.target_checks) for a in areas]
    assert shape == [(TARGETS_AREA, (_TARGET,), False, True)], shape
    header = area_header(areas[0], [_TARGET], [])
    analysis = [line for line in header if "@analysis" in line]
    assert analysis == ["// @analysis targets"], f"the header declares its target checks, naming no language: {header}"
    none = plan_areas((), owns_target_checks=True, halting=_HALTING, seed_document_codes=_SEEDED)
    assert none == (), f"no target-check need plans no area: {none}"


def _check_every_language_input_of_an_area_is_verified() -> None:
    from datrix_testing.cases.annotations import DIAGNOSTIC_INPUT_PREFIX

    from datrix_scripts.dev.fixture_author.diagnostics import (
        TARGETS_AREA,
        AreaVerdict,
        area_input_names,
        not_provoked_inputs,
    )

    first, second = sorted(_LANGUAGES)
    area = f"{DIAGNOSTIC_INPUT_PREFIX}{TARGETS_AREA}"
    inputs = [f"{area}+{first}", f"{area}+{second}@edge", f"{area}+{second}", f"{area}-shaped+{first}", "other"]
    selected = area_input_names(inputs, TARGETS_AREA)
    assert selected == [f"{area}+{first}", f"{area}+{second}", f"{area}+{second}@edge"], selected

    annotated = frozenset({_TARGET})
    provoked = AreaVerdict(f"{area}+{first}", reported=annotated, annotated=annotated)
    missed = AreaVerdict(f"{area}+{second}", reported=frozenset(), annotated=annotated)
    assert provoked.passed and not missed.passed, (provoked, missed)
    assert missed.not_provoked == (_TARGET,), missed
    gaps = not_provoked_inputs([provoked, missed])
    assert gaps == {_TARGET: (f"{area}+{second}",)}, f"a variant reported under one language only: {gaps}"


def _check_the_scaffold_is_copied_once_and_never_overwritten() -> None:
    from datrix_scripts.dev.fixture_author.diagnostics import (
        SCAFFOLD_FILES,
        SYSTEM_CONFIG,
        ensure_scaffold,
        system_owner,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        written = ensure_scaffold(root)
        assert sorted(written) == sorted(root / relative for relative in SCAFFOLD_FILES), f"wrote {written}"
        owner = system_owner(root)
        assert "." in owner, f"the corpus system owner {owner!r} is a qualified name"
        edited = (root / SYSTEM_CONFIG).read_text(encoding="utf-8") + "\n// kept\n"
        (root / SYSTEM_CONFIG).write_text(edited, encoding="utf-8")
        assert ensure_scaffold(root) == [], "a present scaffold file is never written again"
        assert (root / SYSTEM_CONFIG).read_text(encoding="utf-8") == edited


def _area_text(owner: str, version: str, annotated: list[str]) -> str:
    from datrix_scripts.dev.fixture_author.prompting import VariantNames, service_shape

    expects = "".join(f"// @expect {variant}\n" for variant in annotated)
    service = service_shape(VariantNames(_PLANT_STEM, _PLANT_STEM.title()), version, None)
    return (
        "// @tags semantic-analysis\n"
        "// @reason The planted area of the fixture author's self-test.\n"
        f"system {owner}('config/system.dcfg') : version('1.0.0') {{\n}}\n\n"
        f"{expects}{service}"
    )


def _check_verification_reports_a_cascade_and_a_variant_not_provoked() -> None:
    from datrix_semantic.diagnostics.report import CATALOG
    from datrix_testing.cases.core import core_registry
    from datrix_testing.cases.inputs import CaseInputs
    from datrix_testing.cases.package import PackageCases
    from datrix_testing.parsing import register_installed_parsers

    from datrix_scripts.dev.fixture_author.diagnostics import (
        catalog_variants,
        ensure_scaffold,
        system_owner,
        verify_areas,
    )
    from datrix_scripts.dev.fixture_author.prompting import VariantNames, owner_config_shape

    register_installed_parsers()
    unprovoked = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    names = VariantNames(_PLANT_STEM, _PLANT_STEM.title())
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        diagnostics = root / "tests" / "fixtures" / "diagnostics"
        ensure_scaffold(diagnostics)
        owner = system_owner(diagnostics)
        area = diagnostics / "plant.dtrx"
        write_files(diagnostics, {names.config: owner_config_shape(names)})
        package = PackageCases(root, root / "tests", CaseInputs(), core_registry())

        area.write_text(_area_text(owner, _CLEAN_VERSION, [unprovoked]), encoding="utf-8")
        (clean,) = verify_areas(package, ["plant"])
        assert (clean.refused, clean.cascade, clean.not_provoked) == ("", (), (unprovoked,)), clean

        area.write_text(_area_text(owner, _NO_SEMVER, [unprovoked]), encoding="utf-8")
        (cascading,) = verify_areas(package, ["plant"])
        assert not cascading.refused and cascading.cascade, f"a version that is no semver reports nothing: {cascading}"
        assert cascading.not_provoked == (unprovoked,), cascading

        area.write_text(_area_text(owner, _NO_SEMVER, list(cascading.cascade)), encoding="utf-8")
        (passing,) = verify_areas(package, ["plant"])
        assert passing.passed, f"the area annotated with what it reports must pass: {passing}"


_LOOSE_VERSION: Final = "1.0"
_CALLER: Final = "fixture-author-self-test"
_AREA: Final = "plant"


def _check_the_secret_screen_flags_a_credential_and_spares_a_uuid() -> None:
    from datrix_scripts.dev.fixture_author.drafting import secret_literal_lines

    credential = "AKIA" + "Q" * 16
    text = f'token = "{credential}";\nid: "{uuid.uuid4()}";\n// "{credential}" in a comment\nname = "plain";\n'
    assert secret_literal_lines(text) == [1], secret_literal_lines(text)
    assert secret_literal_lines(f'id: "{str(uuid.uuid4()).upper()}";') == [1], "only a canonical lowercase UUID is spared"


def _check_a_profile_is_appended_where_it_is_missing() -> None:
    from datrix_language.parser.dcfg_parser import parse_dcfg
    from datrix_testing.corpus import CORPUS_ROOT

    from datrix_scripts.dev.fixture_author.diagnostics import DATASOURCE_TEMPLATES
    from datrix_scripts.dev.fixture_author.drafting import with_profiles
    from datrix_scripts.dev.fixture_author.prompting import owner_config_shape, variant_names

    owner = owner_config_shape(variant_names(_FIRST))
    updated = with_profiles(owner, ("test", "strict"), "owner.dcfg")
    assert [profile.name for profile in parse_dcfg(updated).profiles] == ["test", "strict"], updated
    assert with_profiles(updated, ("test", "strict"), "owner.dcfg") == updated, "a declared profile is never added twice"
    templates = (CORPUS_ROOT / DATASOURCE_TEMPLATES).read_text(encoding="utf-8")
    assert with_profiles(templates, ("test", "strict"), "templates.dcfg") == templates, "a template library is left alone"


def _check_a_prompt_part_carrying_a_customer_term_is_withheld() -> None:
    from datrix_semantic.diagnostics.report import CATALOG

    from datrix_scripts.dev.fixture_author.diagnostics import AreaPlan, catalog_variants
    from datrix_scripts.dev.fixture_author.prompting import WITHHELD, user_prompt

    variant = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    marker = "zorbquix"
    prompt = user_prompt(
        variant=variant, catalog=CATALOG, area=AreaPlan(_AREA, (variant,)), example=f"service {marker}",
        reference="", feedback="", previous=None, withheld=lambda text: marker in text,
    )
    assert WITHHELD in prompt and marker not in prompt, prompt
    assert variant in prompt, "the variant itself is always sent"


@contextmanager
def _planted_package() -> Iterator[PackageCases]:
    """A package root with an empty case session; its diagnostics directory is not created."""
    from datrix_testing.cases.core import core_registry
    from datrix_testing.cases.inputs import CaseInputs
    from datrix_testing.cases.package import PackageCases
    from datrix_testing.parsing import register_installed_parsers

    register_installed_parsers()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        yield PackageCases(root, root / "tests", CaseInputs(), core_registry())


def _model_settings(server: LoopbackOllama) -> LocalLlmSettings:
    return server.settings(_CALLER)


def _fragment(variant: str, version: str, *, cascade_version: str | None = None) -> str:
    """A model's answer for *variant*: one service declaring *version*, annotated; with
    *cascade_version*, a second, unannotated service declaring that version too."""
    from datrix_scripts.dev.fixture_author.prompting import (
        VariantNames,
        owner_config_shape,
        service_shape,
        variant_names,
    )

    names = variant_names(variant)
    services = [(names, version, variant)]
    if cascade_version is not None:
        services.append((VariantNames(f"{names.kebab}-extra", f"{names.pascal}Extra"), cascade_version, None))
    return json.dumps({
        "source": "\n".join(service_shape(each, declared, expect) for each, declared, expect in services),
        "configs": [{"path": each.config, "text": owner_config_shape(each)} for each, _, _ in services],
    })


def _variant_asked(chat: Chat) -> str:
    from datrix_scripts.dev.fixture_author.prompting import VARIANT_LABEL

    return chat.user.split(VARIANT_LABEL, 1)[1].splitlines()[0]


def _reported_by(package: PackageCases, owner: str, version: str, unprovoked: str) -> str:
    """The one variant a service declaring *version* reports, read off the real analyzer."""
    from datrix_scripts.dev.fixture_author.diagnostics import verify_areas
    from datrix_scripts.dev.fixture_author.prompting import owner_config_shape, service_shape, variant_names

    diagnostics = package.tests_root / "fixtures" / "diagnostics"
    names = variant_names(unprovoked)
    probe = diagnostics / "probe.dtrx"
    probe.write_text(
        f"// @tags error-messages\n// @reason The fixture author's self-test reads what a version reports.\n"
        f"system {owner}('config/system.dcfg') : version('1.0.0') {{}}\n\n{service_shape(names, version, unprovoked)}",
        encoding="utf-8",
    )
    write_files(diagnostics, {names.config: owner_config_shape(names)})
    (verdict,) = verify_areas(package, ["probe"])
    probe.unlink()
    (diagnostics / names.config).unlink()
    assert not verdict.refused and len(verdict.cascade) == 1, f"version {version!r} reports {verdict}"
    return verdict.cascade[0]


def _check_a_draft_passes_and_a_cascade_is_sent_back_and_fixed() -> None:
    from datrix_semantic.diagnostics.report import CATALOG

    from datrix_scripts.dev.fixture_author.diagnostics import (
        AreaPlan,
        catalog_variants,
        ensure_scaffold,
        system_owner,
        verify_areas,
    )
    from datrix_scripts.dev.fixture_author.drafting import Drafter, draft_area
    from datrix_scripts.dev.fixture_author.prompting import CASCADE_INSTRUCTION, FEEDBACK_HEADING, SYNTAX_REFERENCE
    from datrix_scripts.local_llm import LocalLlmPool
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    unprovoked = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    with _planted_package() as package:
        diagnostics = package.tests_root / "fixtures" / "diagnostics"
        ensure_scaffold(diagnostics)
        owner = system_owner(diagnostics)
        loose = _reported_by(package, owner, _LOOSE_VERSION, unprovoked)
        invalid = _reported_by(package, owner, "banana", unprovoked)
        assert loose != invalid, (loose, invalid)

        def answer(chat: Chat) -> str:
            asked = _variant_asked(chat)
            if asked == loose:
                return _fragment(loose, _LOOSE_VERSION)
            if FEEDBACK_HEADING in chat.user:
                return _fragment(invalid, "banana")
            return _fragment(invalid, "banana", cascade_version=_LOOSE_VERSION)

        area = AreaPlan(_AREA, tuple(sorted((loose, invalid))))
        queue = package.root / "queue"
        with LoopbackOllama(answer) as server:
            drafter = Drafter(package, CATALOG, LocalLlmPool(_model_settings(server), report=lambda _line: None),
                              ContentFilter(WORKSPACE_DIR), queue, SYNTAX_REFERENCE.read_text(encoding="utf-8"),
                              diagnostics)
            outcome = draft_area(drafter, area)
            invalid_chats = [chat for chat in server.chats if _variant_asked(chat) == invalid]
            loose_chats = [chat for chat in server.chats if _variant_asked(chat) == loose]
        assert (outcome.landed, outcome.queued) == (area.variants, ()), outcome
        assert len(loose_chats) == 1, f"the clean draft is asked once: {len(loose_chats)}"
        assert len(invalid_chats) == 2, f"the cascading draft is asked twice: {len(invalid_chats)}"
        assert CASCADE_INSTRUCTION in invalid_chats[1].user, "the cascade goes back with the instruction to move it"
        assert not list(diagnostics.glob("config/*-extra-service.dcfg")), "the cascading draft's extra file is removed"
        assert outcome.queue_file is None and not queue.exists(), "an area that lands every variant queues none"
        (verdict,) = verify_areas(package, [_AREA])
        assert verdict.passed, f"the written area reports exactly what it annotates: {verdict}"


def _check_a_fragment_the_parser_refuses_goes_back_alone() -> None:
    """A fragment declaring its own ``system`` would make the whole area unparseable: it is sent
    back on its own, and its sibling lands in the same round."""
    from datrix_semantic.diagnostics.report import CATALOG

    from datrix_scripts.dev.fixture_author.diagnostics import (
        AreaPlan,
        catalog_variants,
        ensure_scaffold,
        system_owner,
        verify_areas,
    )
    from datrix_scripts.dev.fixture_author.drafting import Drafter, draft_area
    from datrix_scripts.dev.fixture_author.prompting import FEEDBACK_HEADING, SYNTAX_REFERENCE
    from datrix_scripts.local_llm import LocalLlmPool
    from datrix_scripts.local_llm_loopback import LoopbackOllama
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    unprovoked = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    with _planted_package() as package:
        diagnostics = package.tests_root / "fixtures" / "diagnostics"
        ensure_scaffold(diagnostics)
        owner = system_owner(diagnostics)
        loose = _reported_by(package, owner, _LOOSE_VERSION, unprovoked)
        invalid = _reported_by(package, owner, "banana", unprovoked)
        second_system = f"system {owner}('config/system.dcfg') : version('1.0.0') {{}}\n\n"

        def answer(chat: Chat) -> str:
            asked = _variant_asked(chat)
            if asked == loose:
                return _fragment(loose, _LOOSE_VERSION)
            if FEEDBACK_HEADING in chat.user:
                return _fragment(invalid, "banana")
            refused = json.loads(_fragment(invalid, "banana"))
            refused["source"] = second_system + refused["source"]
            return json.dumps(refused)

        area = AreaPlan(_AREA, tuple(sorted((loose, invalid))))
        with LoopbackOllama(answer) as server:
            drafter = Drafter(package, CATALOG, LocalLlmPool(_model_settings(server), report=lambda _line: None),
                              ContentFilter(WORKSPACE_DIR), package.root / "queue",
                              SYNTAX_REFERENCE.read_text(encoding="utf-8"), diagnostics)
            outcome = draft_area(drafter, area)
            invalid_chats = [chat for chat in server.chats if _variant_asked(chat) == invalid]
            loose_chats = [chat for chat in server.chats if _variant_asked(chat) == loose]
        assert (outcome.landed, outcome.queued) == (area.variants, ()), outcome
        assert len(loose_chats) == 1, f"the sibling lands in the first round: asked {len(loose_chats)} time(s)"
        assert len(invalid_chats) == 2, f"the refused fragment is asked again: {len(invalid_chats)}"
        assert "system" in invalid_chats[1].user.split(FEEDBACK_HEADING, 1)[1], "the refusal goes back with it"
        (verdict,) = verify_areas(package, [_AREA])
        assert verdict.passed, f"the written area reports exactly what it annotates: {verdict}"


def _check_a_secret_literal_draft_is_queued_and_never_written() -> None:
    from datrix_semantic.diagnostics.report import CATALOG

    from datrix_scripts.dev.fixture_author.diagnostics import SCAFFOLD_FILES, AreaPlan, catalog_variants
    from datrix_scripts.dev.fixture_author.drafting import draft_package
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import ContentFilter

    variant = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    credential = "AKIA" + "Q" * 16
    planted = json.loads(_fragment(variant, "1.0.0"))
    planted["configs"][0]["text"] = planted["configs"][0]["text"].replace("port = 8000;", f'port = 8000;\n    token = "{credential}";')
    with _planted_package() as package, LoopbackOllama(answering(json.dumps(planted))) as server:
        queue = package.root / "queue"
        code = draft_package(package, CATALOG, [AreaPlan(_AREA, (variant,))], _model_settings(server),
                             content=ContentFilter(WORKSPACE_DIR), queue_dir=queue)
        diagnostics = package.tests_root / "fixtures" / "diagnostics"
        written = sorted(path.relative_to(diagnostics) for path in diagnostics.rglob("*") if path.is_file())
        queued = (queue / f"{_AREA}.md").read_text(encoding="utf-8")
    assert code == 1, f"a queued variant exits 1: {code}"
    assert written == sorted(SCAFFOLD_FILES), f"nothing but the scaffold is written: {written}"
    assert variant in queued and credential not in queued, "the queue names the variant and never repeats the value"
    assert len(server.chats) == 1, "a secret is refused at once, never sent back"


def _check_no_local_model_exits_non_zero_and_writes_nothing() -> None:
    from datrix_semantic.diagnostics.report import CATALOG

    from datrix_scripts.dev.fixture_author.diagnostics import AreaPlan, catalog_variants
    from datrix_scripts.dev.fixture_author.drafting import draft_package
    from datrix_scripts.local_llm_loopback import LoopbackOllama, answering
    from datrix_scripts.paths import WORKSPACE_DIR
    from datrix_scripts.skill.common import EXIT_NO_MODEL, ContentFilter

    variant = sorted(catalog_variants(CATALOG, target_checks=False))[0]
    with _planted_package() as package, LoopbackOllama(answering("{}"), models=()) as server:
        queue = package.root / "queue"
        code = draft_package(package, CATALOG, [AreaPlan(_AREA, (variant,))], _model_settings(server),
                             content=ContentFilter(WORKSPACE_DIR), queue_dir=queue)
        written = [path for path in package.root.rglob("*") if path.is_file()]
    assert code == EXIT_NO_MODEL and code != 0, f"no model exits {EXIT_NO_MODEL}: {code}"
    assert written == [], f"no model writes nothing: {written}"


CHECKS: Final[list[CheckFunc]] = [
    _check_needs_exclude_target_checks_and_proven_by_code,
    _check_the_proven_by_code_module_is_the_one_assigning_it,
    _check_a_halting_code_plans_to_its_halt_area_and_a_seed_code_to_a_seeded_area,
    _check_target_checks_plan_one_area_naming_no_language,
    _check_every_language_input_of_an_area_is_verified,
    _check_the_scaffold_is_copied_once_and_never_overwritten,
    _check_verification_reports_a_cascade_and_a_variant_not_provoked,
    _check_the_secret_screen_flags_a_credential_and_spares_a_uuid,
    _check_a_profile_is_appended_where_it_is_missing,
    _check_a_prompt_part_carrying_a_customer_term_is_withheld,
    _check_a_draft_passes_and_a_cascade_is_sent_back_and_fixed,
    _check_a_fragment_the_parser_refuses_goes_back_alone,
    _check_a_secret_literal_draft_is_queued_and_never_written,
    _check_no_local_model_exits_non_zero_and_writes_nothing,
    *NEEDS_CHECKS,
    *LIBRARY_CHECKS,
    *LIBRARY_DRAFT_CHECKS,
    *REPOINT_CHECKS,
    *PRUNE_CHECKS,
]
