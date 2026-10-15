"""Local-model triage of one service's semantic transpilation, before any hosted evaluation.

``evaluate-services.ps1`` hands every ``service-*.prompt.md`` to ``/evaluate-generated-service``
through ``claude -p``. The skill's model work is Phase 3.5: reading the transpiled code of
computed fields, lifecycle hooks, validation blocks, REST endpoint logic and event handlers and
confirming it means what the DSL says. This script asks the local model servers that question
first, once per category the service has:

1. it runs the service scan (``evaluate_service_scan``) into the evaluation folder and reads it;
2. for each Phase 3.5 category present, it asks one question over the service's DSL source and
   the generated files the scan maps that category to (``local_reading.ask_files``, through a
   ``ReadScope`` whose extra roots are the project's source and generated trees; every line read
   from them is checked against the customer-term corpus);
3. it writes ``service-<name>.local-triage.json``: per category ``clean``, ``finding`` or
   ``unverifiable``, with the model's cited lines.

When every category is ``clean`` and the scan has no failed artifact check, it writes the
service's report into ``evaluated/`` (marked "local triage only") and exits 0, so no hosted run
is needed. A ``finding`` or ``unverifiable`` category, or any failed artifact check (which needs
the hosted judgment the triage does not make), exits ``EXIT_NEEDS_REVIEW``: the caller sends the
service to the hosted evaluation with the triage file appended. No model server answering makes every category
``unverifiable``. The triage is a lead, never a verdict on its own: a ``finding`` is confirmed by
the hosted evaluation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory
from typing import Final, TypedDict, cast

from datrix_common.paths import ServicePaths

from datrix_scripts.customer_domain_isolation import corpus_path
from datrix_scripts.evaluate_reports import SERVICE_MECHANICAL_TEMPLATE
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_VIOLATION,
    NamedCheck,
    UsageError,
    named_checks,
    run_checks,
    run_main,
)
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from datrix_scripts.local_llm_loopback import LOOPBACK, LoopbackOllama, answering, closed_port
from datrix_scripts.local_reading import ReadScope, ReadScopeError, ask_files
from datrix_scripts.paths import WORKSPACE_DIR
from evaluate_generated_scan import DEFAULT_CONFIG_PROFILE, PROMPT_TEMPLATE, ScanInputError
from evaluate_service_scan import SERVICE_SCAN_FILENAME_TEMPLATE, STATUS_PASS, run_service_scan

#: Exit code when a category needs the hosted evaluation (a finding, or nothing could verify it).
EXIT_NEEDS_REVIEW: Final = 3

TRIAGE_FILENAME_TEMPLATE: Final = "service-{name}.local-triage.json"
REPORT_FILENAME_TEMPLATE: Final = "service-{name}-evaluation.md"
EVALUATED_DIR: Final = "evaluated"
_PROMPT_NAME_RE: Final = re.compile(r"^service-(?P<name>.+)\.prompt\.md$")
_PROMPT_FIELD_RE: Final = re.compile(r"^\*\*(?P<label>[^*]+):\*\*\s+`?(?P<value>[^`\r\n]+?)`?\s*$", re.MULTILINE)
_QUALIFIED_NAME: Final = "Qualified Name"
_GENERATED_DIR: Final = "Generated Directory"
_PROJECT_SOURCE: Final = "Project Source"
_SERVICE_SOURCE: Final = "Source .dtrx"
_VERDICT_RE: Final = re.compile(r"^\s*VERDICT:\s*(?P<verdict>clean|finding)\b", re.IGNORECASE)


class Category(StrEnum):
    """The Phase 3.5 categories of ``/evaluate-generated-service``."""

    COMPUTED_FIELDS = "computed_fields"
    LIFECYCLE_HOOKS = "lifecycle_hooks"
    VALIDATIONS = "validations"
    REST_ENDPOINTS = "rest_endpoints"
    EVENT_HANDLERS = "event_handlers"


class Verdict(StrEnum):
    CLEAN = "clean"
    FINDING = "finding"
    UNVERIFIABLE = "unverifiable"


_DESCRIPTIONS: Final[dict[Category, str]] = {
    Category.COMPUTED_FIELDS: "computed fields (each @property or getter must compute exactly the DSL expression)",
    Category.LIFECYCLE_HOOKS: "lifecycle hooks (beforeCreate/afterCreate/... bodies, field assignments, conditions)",
    Category.VALIDATIONS: "validation blocks (each rule's expression, its error message, cross-field references)",
    Category.REST_ENDPOINTS: "REST endpoint logic (parameters, business logic, responses, error handling)",
    Category.EVENT_HANDLERS: "event handlers (payload handling, handler logic, published events)",
}
#: The scan's artifact checks that hold each entity category's generated files.
_ENTITY_CHECKS: Final = frozenset({"orm_model", "schema_dto", "service_layer"})
#: (scan scope, artifact check) holding each block category's generated files.
_BLOCK_CHECKS: Final[dict[Category, tuple[str, str]]] = {
    Category.REST_ENDPOINTS: ("block:rest_api", "routes"),
    Category.EVENT_HANDLERS: ("block:pubsub", "consumer"),
}
_BLOCK_FEATURES: Final[dict[Category, str]] = {
    Category.REST_ENDPOINTS: "rest_api",
    Category.EVENT_HANDLERS: "pubsub",
}


class ArtifactCheck(TypedDict):
    """One expected-artifact existence check of the service scan."""

    scope: str
    check: str
    status: str
    matched: list[str]


class EntityDetail(TypedDict):
    entity: str
    computed_fields: list[str]
    lifecycle_hooks: dict[str, int]
    validation_count: int


class DslInventory(TypedDict):
    entity_details: list[EntityDetail]


class ServiceScan(TypedDict):
    """The parts of ``service-<name>-scan.json`` the triage reads."""

    generated_dir: str
    features: dict[str, bool]
    dsl: DslInventory
    artifact_checks: list[ArtifactCheck]


@dataclass(frozen=True)
class ServicePrompt:
    """What a ``service-*.prompt.md`` names: the service and where its source and output are."""

    name: str
    qualified_name: str
    project_source: Path
    service_source: Path
    generated_dir: Path


@dataclass(frozen=True)
class CategoryQuestion:
    category: Category
    items: tuple[str, ...]
    files: tuple[Path, ...]


@dataclass(frozen=True)
class CategoryResult:
    category: Category
    verdict: Verdict
    detail: str
    files: tuple[Path, ...]

    def to_json(self) -> dict[str, object]:
        return {"verdict": str(self.verdict), "detail": self.detail, "files": [str(f) for f in self.files]}


def read_prompt(prompt_path: Path) -> ServicePrompt:
    """The service and paths a ``service-*.prompt.md`` names."""
    name_match = _PROMPT_NAME_RE.match(prompt_path.name)
    if name_match is None:
        raise UsageError(f"{prompt_path.name} is not a service prompt; expected service-<name>.prompt.md.")
    fields = {m.group("label").strip(): m.group("value").strip()
              for m in _PROMPT_FIELD_RE.finditer(prompt_path.read_text(encoding="utf-8"))}
    missing = [label for label in (_QUALIFIED_NAME, _GENERATED_DIR, _PROJECT_SOURCE) if label not in fields]
    if missing:
        raise UsageError(f"{prompt_path} names no {', '.join(missing)}; regenerate it with /evaluate-generated.")
    project_source = Path(fields[_PROJECT_SOURCE])
    service_source = Path(fields[_SERVICE_SOURCE]) if fields.get(_SERVICE_SOURCE, "").endswith(".dtrx") \
        else project_source
    return ServicePrompt(name_match.group("name"), fields[_QUALIFIED_NAME], project_source, service_source,
                         Path(fields[_GENERATED_DIR]))


def _check_files(scan: ServiceScan, scope: str, checks: frozenset[str]) -> list[Path]:
    root = Path(scan["generated_dir"])
    files: list[Path] = []
    for result in scan["artifact_checks"]:
        if result["scope"] == scope and result["check"] in checks and result["status"] == STATUS_PASS:
            files.extend(root / rel for rel in result["matched"])
    return files


def mechanical_failures(scan: ServiceScan) -> list[str]:
    """``scope/check`` of every failed artifact-existence check: each needs the hosted judgment."""
    return [f"{result['scope']}/{result['check']}" for result in scan["artifact_checks"]
            if result["status"] != STATUS_PASS]


def _entity_items(entity: EntityDetail, category: Category) -> list[str]:
    if category is Category.COMPUTED_FIELDS:
        return list(entity["computed_fields"])
    if category is Category.LIFECYCLE_HOOKS:
        return [hook for hook, count in entity["lifecycle_hooks"].items() if count]
    return [f"{entity['validation_count']} validation rule(s)"] if entity["validation_count"] else []


def _entity_question(scan: ServiceScan, category: Category) -> list[CategoryQuestion]:
    """The category's question over every entity carrying it; none when no entity does."""
    items: list[str] = []
    files: list[Path] = []
    for entity in scan["dsl"]["entity_details"]:
        names = _entity_items(entity, category)
        if names:
            items += [f"{entity['entity']}.{name}" for name in names]
            files += _check_files(scan, f"entity:{entity['entity']}", _ENTITY_CHECKS)
    return [CategoryQuestion(category, tuple(items), tuple(dict.fromkeys(files)))] if items else []


def category_questions(scan: ServiceScan) -> list[CategoryQuestion]:
    """One question per Phase 3.5 category the scanned service has, with the files it maps to."""
    questions = [question
                 for category in (Category.COMPUTED_FIELDS, Category.LIFECYCLE_HOOKS, Category.VALIDATIONS)
                 for question in _entity_question(scan, category)]
    for category, (scope, check) in _BLOCK_CHECKS.items():
        if scan["features"][_BLOCK_FEATURES[category]]:
            files = tuple(_check_files(scan, scope, frozenset({check})))
            questions.append(CategoryQuestion(category, (scope,), files))
    return questions


def question_text(question: CategoryQuestion) -> str:
    return (
        f"Compare the DSL source with the generated code for the {_DESCRIPTIONS[question.category]} of: "
        f"{', '.join(question.items)}. Does the generated code implement exactly what the DSL says? "
        f"Start your answer with one line 'VERDICT: clean' when every item is implemented correctly, or "
        f"'VERDICT: finding' followed by each discrepancy, citing the DSL line and the generated line."
    )


def verdict_of(answer: str) -> Verdict:
    """``clean`` or ``finding`` from the answer's first line; anything else cannot be trusted."""
    first = next((line for line in answer.splitlines() if line.strip()), "")
    match = _VERDICT_RE.match(first)
    return Verdict(match.group("verdict").lower()) if match else Verdict.UNVERIFIABLE


def triage(question: CategoryQuestion, source: Path, scope: ReadScope, pool: LocalLlmPool) -> CategoryResult:
    """One category's verdict; any reason it cannot be read or answered makes it unverifiable."""
    if not question.files:
        return CategoryResult(question.category, Verdict.UNVERIFIABLE,
                              "the scan maps no generated file to this category", ())
    try:
        answer = ask_files(scope, pool, [str(source), *map(str, question.files)], question_text(question))
    except (ReadScopeError, LocalLlmUnavailable, OSError) as exc:
        return CategoryResult(question.category, Verdict.UNVERIFIABLE, f"{type(exc).__name__}: {exc}",
                              question.files)
    return CategoryResult(question.category, verdict_of(answer.text), answer.render(), question.files)


def render_report(prompt: ServicePrompt, results: list[CategoryResult], mechanical: Path) -> str:
    lines = [f"# Service Evaluation: {prompt.name} (local triage only)", "",
             "Every Phase 3.5 category was judged clean by a local model; no hosted evaluation ran.",
             "A lead, not a proof: open the cited lines before relying on it.", "",
             f"Mechanical findings: `{mechanical}`", ""]
    for result in results:
        lines += [f"## {result.category}: {result.verdict}", "", result.detail, ""]
    if not results:
        lines.append("The service has no computed field, lifecycle hook, validation, REST API or event handler.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-test: a prompt rendered by the real template, a planted scan, a model on loopback
# ---------------------------------------------------------------------------

_CLEAN_ANSWER: Final = "VERDICT: clean\nEvery item matches."
_SELF_TEST_SERVICE: Final = "shop.CatalogService"


def _planted_scan(generated: Path) -> ServiceScan:
    return {
        "generated_dir": str(generated),
        "features": {"rest_api": True, "pubsub": False},
        "dsl": {"entity_details": [
            {"entity": "Product", "computed_fields": ["label"], "lifecycle_hooks": {"beforeCreate": 1, "afterCreate": 0},
             "validation_count": 0},
            {"entity": "Variant", "computed_fields": [], "lifecycle_hooks": {}, "validation_count": 2},
        ]},
        "artifact_checks": [
            {"scope": "entity:Product", "check": "orm_model", "status": STATUS_PASS, "matched": ["models/product.py"]},
            {"scope": "entity:Variant", "check": "schema_dto", "status": STATUS_PASS, "matched": ["schemas/variant.py"]},
            {"scope": "entity:Variant", "check": "orm_model", "status": "FAIL", "matched": []},
            {"scope": "block:rest_api", "check": "routes", "status": STATUS_PASS, "matched": ["routes/products.py"]},
        ],
    }


def _check_prompt_fields_are_read_from_the_rendered_template() -> None:
    with TemporaryDirectory(prefix="service-triage-") as temp:
        prompt_path = Path(temp) / "service-catalog-service.prompt.md"
        values = dict.fromkeys((name for _, name, _, _ in Formatter().parse(PROMPT_TEMPLATE) if name), "x")
        values |= {"qualified_name": _SELF_TEST_SERVICE, "service_dtrx": "/src/catalog.dtrx",
                   "generated_dir": "/gen/catalog_service", "system_dtrx": "/src/system.dtrx"}
        prompt_path.write_text(PROMPT_TEMPLATE.format(**values), encoding="utf-8")
        prompt = read_prompt(prompt_path)
    assert (prompt.name, prompt.qualified_name) == ("catalog-service", _SELF_TEST_SERVICE), prompt
    assert prompt.project_source == Path("/src/system.dtrx") and prompt.service_source == Path("/src/catalog.dtrx")
    assert prompt.generated_dir == Path("/gen/catalog_service"), prompt.generated_dir


def _check_categories_map_to_the_scanned_files() -> None:
    generated = Path("/gen/catalog_service")
    questions = {q.category: q for q in category_questions(_planted_scan(generated))}
    assert set(questions) == {Category.COMPUTED_FIELDS, Category.LIFECYCLE_HOOKS, Category.VALIDATIONS,
                              Category.REST_ENDPOINTS}, set(questions)
    assert questions[Category.COMPUTED_FIELDS].items == ("Product.label",)
    assert questions[Category.LIFECYCLE_HOOKS].items == ("Product.beforeCreate",), "a hook with no body is not asked"
    assert questions[Category.VALIDATIONS].files == (generated / "schemas/variant.py",), "a FAIL check maps no file"
    assert questions[Category.REST_ENDPOINTS].files == (generated / "routes/products.py",)
    assert mechanical_failures(_planted_scan(generated)) == ["entity:Variant/orm_model"], \
        "a failed artifact check is reported, so the service is never skipped past the hosted judgment"


def _check_a_clean_service_report_is_marked_local_triage_only() -> None:
    prompt = ServicePrompt("catalog-service", _SELF_TEST_SERVICE, Path("s.dtrx"), Path("s.dtrx"), Path("g"))
    result = CategoryResult(Category.COMPUTED_FIELDS, Verdict.CLEAN, "Every item matches. [s.dtrx:1]", ())
    with TemporaryDirectory(prefix="service-triage-") as temp:
        report = write_local_report(Path(temp), prompt, [result], Path(temp) / "mechanical.md")
        text = report.read_text(encoding="utf-8")
        assert report == Path(temp) / EVALUATED_DIR / "service-catalog-service-evaluation.md", report
    assert "(local triage only)" in text and "computed_fields: clean" in text and "[s.dtrx:1]" in text, text


def _check_only_a_leading_verdict_line_is_trusted() -> None:
    assert verdict_of("\nVERDICT: clean\nok") is Verdict.CLEAN
    assert verdict_of("VERDICT: Finding\n- line 3") is Verdict.FINDING
    assert verdict_of("Looks fine.\nVERDICT: clean") is Verdict.UNVERIFIABLE, "a verdict not on the first line"
    assert verdict_of("") is Verdict.UNVERIFIABLE


def _check_triage_over_loopback_and_with_no_server() -> None:
    with TemporaryDirectory(prefix="service-triage-ws-") as ws, TemporaryDirectory(prefix="service-triage-") as temp, \
            LoopbackOllama(answering(_CLEAN_ANSWER)) as server:
        workspace, project = Path(ws), Path(temp)
        (workspace / "datrix" / ".git").mkdir(parents=True)
        corpus = corpus_path(workspace / "datrix")
        corpus.parent.mkdir(parents=True)
        corpus.write_text(json.dumps({"algorithm": "sha256", "min_token_length": 5, "terms": []}), encoding="utf-8")
        source = project / "src" / "catalog.dtrx"
        generated = project / "gen" / "catalog_service"
        for path, text in ((source, "entity Product { label: String = #\"{name}\" }\n"),
                           (generated / "models" / "product.py", "def label(self): return f\"{self.name}\"\n")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        scope = ReadScope(workspace, extra_roots=(project / "src", project / "gen"))
        question = CategoryQuestion(Category.COMPUTED_FIELDS, ("Product.label",), (generated / "models" / "product.py",))

        def pool(port: int) -> LocalLlmPool:
            settings = LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                        allow_load=False, ollama_port=port, usage_log=workspace / "usage.jsonl",
                                        caller="gate")
            return LocalLlmPool(settings, report=lambda _line: None)

        answered = triage(question, source, scope, pool(server.port))
        assert answered.verdict is Verdict.CLEAN, answered
        assert "1| entity Product" in server.chats[-1].user, "the DSL source is sent with numbered lines"
        unanswered = triage(question, source, scope, pool(closed_port()))
        assert unanswered.verdict is Verdict.UNVERIFIABLE and "LocalLlmUnavailable" in unanswered.detail, unanswered
        unmapped = triage(CategoryQuestion(Category.REST_ENDPOINTS, ("block:rest_api",), ()), source, scope,
                          pool(server.port))
        assert unmapped.verdict is Verdict.UNVERIFIABLE, "a category with no mapped file is never judged clean"


def self_test_checks() -> list[NamedCheck]:
    return named_checks([
        _check_prompt_fields_are_read_from_the_rendered_template,
        _check_categories_map_to_the_scanned_files,
        _check_only_a_leading_verdict_line_is_trusted,
        _check_a_clean_service_report_is_marked_local_triage_only,
        _check_triage_over_loopback_and_with_no_server,
    ])


def run(args: argparse.Namespace) -> int:
    if args.self_test:
        return EXIT_PASS if run_checks(self_test_checks()) else EXIT_VIOLATION
    if not (args.prompt and args.source_dir and args.generated_dir):
        raise UsageError("--prompt, --source-dir and --generated-dir are required (or pass --self-test).")
    prompt_path = Path(args.prompt).resolve()
    if not prompt_path.is_file():
        raise UsageError(f"Prompt file not found: {prompt_path}. Pass a service-<name>.prompt.md.")
    prompt = read_prompt(prompt_path)
    eval_dir = prompt_path.parent
    scan_path = eval_dir / SERVICE_SCAN_FILENAME_TEMPLATE.format(name=prompt.name)
    try:
        scanned = run_service_scan(prompt.project_source, prompt.qualified_name, prompt.generated_dir,
                                   Path(args.generated_dir).resolve(), scan_path, args.profile)
    except ScanInputError as exc:
        raise UsageError(f"The service scan of {prompt.name} cannot run: {exc}") from exc
    if scanned != EXIT_PASS:
        raise UsageError(f"The service scan of {prompt.name} failed; see its output above.")
    scan = cast(ServiceScan, json.loads(scan_path.read_text(encoding="utf-8")))
    scope = ReadScope(WORKSPACE_DIR, extra_roots=(Path(args.source_dir).resolve(), Path(args.generated_dir).resolve()))
    pool = LocalLlmPool(local_llm_settings(args))
    results = [triage(question, prompt.service_source, scope, pool) for question in category_questions(scan)]
    triage_path = eval_dir / TRIAGE_FILENAME_TEMPLATE.format(name=prompt.name)
    failed_checks = mechanical_failures(scan)
    needs_review = bool(failed_checks) or any(result.verdict is not Verdict.CLEAN for result in results)
    triage_path.write_text(json.dumps({
        "service": prompt.qualified_name,
        "scan": str(scan_path),
        "needs_review": needs_review,
        "failed_artifact_checks": failed_checks,
        "categories": {str(result.category): result.to_json() for result in results},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{prompt.name}: " + (", ".join(f"{r.category}={r.verdict}" for r in results) or "no Phase 3.5 category"))
    print(f"Triage: {triage_path}")
    if needs_review:
        return EXIT_NEEDS_REVIEW
    mechanical = scan_path.parent / SERVICE_MECHANICAL_TEMPLATE.format(
        name=ServicePaths(prompt.qualified_name).kebab_resource)
    print(f"Report (local triage only): {write_local_report(eval_dir, prompt, results, mechanical)}")
    return EXIT_PASS


def write_local_report(eval_dir: Path, prompt: ServicePrompt, results: list[CategoryResult], mechanical: Path) -> Path:
    """Write the triage-only report into ``evaluated/``, where the hosted evaluation's reports go."""
    report_dir = eval_dir / EVALUATED_DIR
    report_dir.mkdir(exist_ok=True)
    report = report_dir / REPORT_FILENAME_TEMPLATE.format(name=prompt.name)
    report.write_text(render_report(prompt, results, mechanical), encoding="utf-8")
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local-model triage of one service's Phase 3.5 categories.")
    parser.add_argument("--prompt", help="The service-<name>.prompt.md to triage.")
    parser.add_argument("--source-dir", help="The project source directory (read scope).")
    parser.add_argument("--generated-dir", help="The generated project root (read scope).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the triage's checks over a planted prompt, scan and loopback model.")
    parser.add_argument("--profile", default=DEFAULT_CONFIG_PROFILE,
                        help=f"Config profile the project was generated with (default: {DEFAULT_CONFIG_PROFILE}).")
    parser.add_argument("--debug", action="store_true", help="Log at DEBUG level.")
    add_local_llm_arguments(parser)
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run_main(_parse_args, run))
