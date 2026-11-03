"""What the packages' tests need from their inputs: a local model reads each test module.

For each module discovery found (``needs.package_inputs``), the local model reads the module's source and
the text of every input it reads, and answers, per test function, with the declarations its assertions
depend on::

    {"tests": [{"name": str, "declarations": [{"kind": str, "path": str, "facts": [str]}], "local": str | null}]}

Every line sent passes the customer-term filter (``skill.common.ContentFilter``) and goes only to the
local model pool. An answer is checked before it is kept:

- its shape, against the schema the request also constrains the model with;
- each ``kind``, against the node classes of ``datrix_common.datrix_model`` (every module of it imported)
  and ``ConfigDecl``, the declaration of a ``.dcfg`` document;
- its test names, against the module's test functions (``test*`` at module level and in ``Test*``
  classes, a method named ``Class.test``): none missing, none extra, none twice.

An answer failing a check goes back once with its problems; failing again, the module is refused. A
module with no test function (a conftest, a helper) is not asked: it needs nothing of its own.

Modules are asked in parallel, all in one context window sized for the largest prompt and a resend:
Ollama reloads a model for each window it is asked in, and a model that has been serving can hold off a
reload until its keep-alive ends, past the request timeout. The pool loads the model in that window before
the first request (a model held at another window is unloaded first), so no request meets a reload. Each
answer is logged as it arrives (``needs <n>/<total> <module>: <state>``).

A kept answer is cached under the sha256 of the exact request, so a rerun on an unchanged tree asks the
model nothing and reads the same answers. ``LocalLlmUnavailable`` stops the reading, with no fallback.
"""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import logging
from collections import Counter
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

from datrix_common import datrix_model
from datrix_common.config.dcfg.ast_nodes import ConfigDecl
from datrix_common.datrix_model.base import Node
from datrix_testing.model_contracts.discovery import import_package_modules

from datrix_scripts.dev.fixture_author.needs import ModuleInput, ModuleInputs, NeedsScanError
from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import ContentFilter, NoModelAnswer, ask_json, parallel, section_body

logger = logging.getLogger(__name__)

#: Where kept answers are cached, one file per request.
NEEDS_CACHE_DIR: Final[Path] = WORKSPACE_DIR / ".tmp" / "fixture-author" / "needs-cache"
#: Sampling for an answer a rerun must reproduce.
NEEDS_TEMPERATURE: Final[float] = 0.0
#: The tokens an answer may take; the context window holds the prompt and this.
ANSWER_TOKENS: Final[int] = 8192
MIN_CONTEXT_TOKENS: Final[int] = 16384
CONTEXT_STEP_TOKENS: Final[int] = 4096
#: pytest's default collection prefixes.
TEST_FUNCTION_PREFIX: Final[str] = "test"
TEST_CLASS_PREFIX: Final[str] = "Test"
TEST_NAME_SEPARATOR: Final[str] = "."
FEEDBACK_HEADING: Final[str] = "PROBLEMS WITH YOUR LAST ANSWER"
KINDS_HEADING: Final[str] = "KINDS"
MODULE_LABEL: Final[str] = "MODULE"
TESTS_HEADING: Final[str] = "TEST FUNCTIONS"
#: How a prompt lists an item: a test function under ``TESTS_HEADING``, a problem under ``FEEDBACK_HEADING``.
BULLET: Final[str] = "- "

_TESTS: Final = "tests"
_NAME: Final = "name"
_DECLARATIONS: Final = "declarations"
_LOCAL: Final = "local"
_KIND: Final = "kind"
_PATH: Final = "path"
_FACTS: Final = "facts"
_TEST_KEYS: Final = frozenset({_NAME, _DECLARATIONS, _LOCAL})
_DECLARATION_KEYS: Final = frozenset({_KIND, _PATH, _FACTS})
_CACHE_SUFFIX: Final = ".json"
_PRIVATE_PREFIX: Final = "_"

_SYSTEM_PROMPT: Final = f"""You read one Python test module of the Datrix code generator and the inputs it reads (.dtrx domain \
specifications, .dcfg configurations, .dseed seed data). For each test function, list the declarations its \
assertions depend on.

Answer with one JSON object and nothing else:
{{"{_TESTS}": [{{"{_NAME}": str, "{_DECLARATIONS}": [{{"{_KIND}": str, "{_PATH}": str, "{_FACTS}": [str]}}], "{_LOCAL}": str or null}}]}}
- "{_TESTS}" holds every test function listed under {TESTS_HEADING}, each once, by the name given there.
- "{_KIND}" is the name of one class listed under {KINDS_HEADING}; a .dcfg declaration is {ConfigDecl.__name__}.
- "{_PATH}" is the declaration's qualified name as the input spells it, e.g. shop.OrderService.db.Order.total.
- "{_FACTS}" are the properties of the declaration an assertion reads, e.g. "type Decimal", "indexed", \
"route GET /orders/{{id}}".
- "{_LOCAL}" is null, unless the test's input cannot be shared with other tests; then it is the reason: the \
input is a syntax error, the input file is missing, it declares a second system, or the variant the test \
proves is the absence of a block.
A test whose assertions read no declaration has an empty "{_DECLARATIONS}" list.
"""


@dataclass(frozen=True)
class Declaration:
    """One declaration a test's assertions depend on: its node *kind*, qualified *path* and the *facts* read."""

    kind: str
    path: str
    facts: tuple[str, ...]


@dataclass(frozen=True)
class TestNeeds:
    """What one test function needs: its declarations, sorted, and why its input is *local*, if it is."""

    name: str
    declarations: tuple[Declaration, ...]
    local: str | None


@dataclass(frozen=True)
class ModuleNeeds:
    """One module's inputs and, per test function in source order, what it needs."""

    found: ModuleInputs
    tests: tuple[TestNeeds, ...]


@dataclass(frozen=True)
class RefusedModule:
    """A module whose answer failed its checks after the one resend, with the problems of the last answer."""

    module: Path
    problems: tuple[str, ...]


@dataclass(frozen=True)
class NeedsReading:
    """Every module read, in the order given: the ones answered and the ones refused."""

    needs: tuple[ModuleNeeds, ...]
    refused: tuple[RefusedModule, ...]


@dataclass(frozen=True)
class NeedsReader:
    """What reading needs: the workspace the labels are relative to, the model pool, the term filter, the
    cache and the kind vocabulary."""

    workspace: Path
    pool: LocalLlmPool
    content: ContentFilter
    cache_dir: Path = NEEDS_CACHE_DIR
    kinds: tuple[str, ...] = field(default_factory=lambda: tuple(node_kinds()))


@dataclass(frozen=True)
class _ModuleRequest:
    """The request for one module: its expected test names, the prompts and the schema."""

    found: ModuleInputs
    tests: tuple[str, ...]
    system: str
    user: str
    schema: dict[str, object] = field(hash=False)

    @property
    def key(self) -> str:
        """The sha256 of everything the model is sent, naming the cache file."""
        sent = json.dumps({"system": self.system, "user": self.user, "schema": self.schema}, sort_keys=True)
        return hashlib.sha256(sent.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Answer:
    """One module's answer: its tests when it passed every check, else the problems of the last answer."""

    tests: tuple[TestNeeds, ...]
    problems: tuple[str, ...]


def _subclasses(base: type[Node]) -> Iterator[type[Node]]:
    pending = [base]
    seen: set[type[Node]] = set()
    while pending:
        for subclass in pending.pop().__subclasses__():
            if subclass not in seen:
                seen.add(subclass)
                pending.append(subclass)
                yield subclass


def node_kinds() -> dict[str, type[object]]:
    """Every public node class of ``datrix_common.datrix_model`` by name, with ``ConfigDecl``, sorted.

    Raises:
        NeedsScanError: two node classes share a name, so a kind would name neither.
    """
    package = datrix_model.__name__
    import_package_modules((package,))
    classes = [
        node for node in _subclasses(Node)
        if (node.__module__ == package or node.__module__.startswith(package + TEST_NAME_SEPARATOR))
        and not node.__name__.startswith(_PRIVATE_PREFIX)
    ]
    shared = sorted(name for name, count in Counter(node.__name__ for node in classes).items() if count > 1)
    if shared:
        raise NeedsScanError(
            f"node classes of {package} share the names {shared}, so a declaration kind cannot name one. Fix: "
            "give each node class a distinct name."
        )
    kinds: dict[str, type[object]] = {node.__name__: node for node in classes}
    kinds[ConfigDecl.__name__] = ConfigDecl
    return dict(sorted(kinds.items()))


def _tests_in(body: Sequence[ast.stmt], prefix: str) -> Iterator[str]:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(TEST_FUNCTION_PREFIX):
            yield prefix + node.name
        elif isinstance(node, ast.ClassDef) and node.name.startswith(TEST_CLASS_PREFIX):
            yield from _tests_in(node.body, f"{prefix}{node.name}{TEST_NAME_SEPARATOR}")


def module_tests(tree: ast.Module) -> tuple[str, ...]:
    """The test functions pytest collects from *tree*, in source order; a method as ``Class.test``."""
    return tuple(_tests_in(tree.body, ""))


def needs_schema(kinds: Sequence[str], tests: Sequence[str], *, named: bool = False) -> dict[str, object]:
    """The JSON schema of one module's answer: its test names and the kinds are the only values allowed.

    With *named* a declaration's path cannot be empty. The first request leaves it open (its schema is part
    of the cache key of every kept answer); the resend of an answer with an empty path is *named*.
    """
    declaration = {
        "type": "object",
        "properties": {
            _KIND: {"type": "string", "enum": list(kinds)},
            _PATH: {"type": "string", **({"minLength": 1} if named else {})},
            _FACTS: {"type": "array", "items": {"type": "string"}},
        },
        "required": sorted(_DECLARATION_KEYS),
        "additionalProperties": False,
    }
    test = {
        "type": "object",
        "properties": {
            _NAME: {"type": "string", "enum": list(tests)},
            _DECLARATIONS: {"type": "array", "items": declaration},
            _LOCAL: {"type": ["string", "null"]},
        },
        "required": sorted(_TEST_KEYS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {_TESTS: {"type": "array", "items": test}},
        "required": [_TESTS],
        "additionalProperties": False,
    }


def _key_problems(value: Mapping[str, object], expected: frozenset[str], where: str) -> list[str]:
    if set(value) == expected:
        return []
    return [f"{where} has the keys {sorted(value)}; expected exactly {sorted(expected)}"]


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _declaration_problems(value: object, where: str, kinds: Collection[str]) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where} is not an object"]
    problems = _key_problems(value, _DECLARATION_KEYS, where)
    kind = value.get(_KIND)
    if not isinstance(kind, str) or kind not in kinds:
        problems.append(f"{where} has the unknown kind {kind!r}; a kind is the name of one class under {KINDS_HEADING}")
    if not _is_text(value.get(_PATH)):
        problems.append(
            f"{where} has no qualified name in '{_PATH}'; a declaration with no name of its own (built in "
            f"Python without one, or anonymous in the input) takes the qualified name of the declaration "
            f"enclosing it, then '.', then its kind (shop.OrderService.CqrsBlock); with nothing enclosing it, "
            f"its kind alone (SeedDocument)"
        )
    facts = value.get(_FACTS)
    if not isinstance(facts, list) or not all(_is_text(fact) for fact in facts):
        problems.append(f"{where} must list its facts as non-empty strings in '{_FACTS}'")
    return problems


def _test_problems(index: int, value: object, kinds: Collection[str]) -> list[str]:
    where = f"test entry {index}"
    if not isinstance(value, dict):
        return [f"{where} is not an object"]
    if isinstance(value.get(_NAME), str):
        where = f"test {value[_NAME]!r}"
    problems = _key_problems(value, _TEST_KEYS, where)
    local = value.get(_LOCAL)
    if local is not None and not _is_text(local):
        problems.append(f"{where} has '{_LOCAL}' {local!r}; it is null or the reason the input cannot be shared")
    declarations = value.get(_DECLARATIONS)
    if not isinstance(declarations, list):
        return [*problems, f"{where} must list its declarations in '{_DECLARATIONS}'"]
    for number, declaration in enumerate(declarations):
        problems.extend(_declaration_problems(declaration, f"{where} declaration {number}", kinds))
    return problems


def _name_problems(names: Sequence[str], tests: Sequence[str]) -> list[str]:
    problems: list[str] = []
    missing = [test for test in tests if test not in names]
    if missing:
        problems.append(f"the answer leaves out the test functions {missing}; answer every one under {TESTS_HEADING}")
    unknown = sorted(set(names) - set(tests))
    if unknown:
        problems.append(f"the answer names {unknown}, which are not test functions of the module; use only {list(tests)}")
    twice = sorted(name for name, count in Counter(names).items() if count > 1)
    if twice:
        problems.append(f"the answer lists {twice} more than once; list each test function once")
    return problems


def answer_problems(answer: Mapping[str, object], kinds: Collection[str], tests: Sequence[str]) -> list[str]:
    """Every way *answer* breaks the schema, names a kind outside *kinds*, or misses or adds a test of *tests*."""
    problems = _key_problems(answer, frozenset({_TESTS}), "the answer")
    entries = answer.get(_TESTS)
    if not isinstance(entries, list):
        return [*problems, f"'{_TESTS}' must be a list of test entries"]
    for index, entry in enumerate(entries):
        problems.extend(_test_problems(index, entry, kinds))
    names = [entry[_NAME] for entry in entries if isinstance(entry, dict) and isinstance(entry.get(_NAME), str)]
    problems.extend(_name_problems(names, tests))
    return problems


def _declaration(value: Mapping[str, object]) -> Declaration:
    facts = cast("list[str]", value[_FACTS])
    return Declaration(str(value[_KIND]), str(value[_PATH]), tuple(sorted(set(facts))))


def _test_needs(value: Mapping[str, object]) -> TestNeeds:
    declarations = cast("list[Mapping[str, object]]", value[_DECLARATIONS])
    local = value[_LOCAL]
    return TestNeeds(
        str(value[_NAME]),
        tuple(sorted({_declaration(each) for each in declarations}, key=lambda each: (each.path, each.kind, each.facts))),
        None if local is None else str(local),
    )


def parse_needs(answer: Mapping[str, object], tests: Sequence[str]) -> tuple[TestNeeds, ...]:
    """The needs of an *answer* that passed ``answer_problems``, in the order of *tests*."""
    by_name = {str(entry[_NAME]): _test_needs(entry) for entry in cast("list[Mapping[str, object]]", answer[_TESTS])}
    return tuple(by_name[test] for test in tests)


def context_window(system: str, user: str) -> int:
    """The context, in tokens, that holds the whole prompt and an answer; a prompt is never cut."""
    needed = (len(system) + len(user)) // CHARS_PER_TOKEN + ANSWER_TOKENS
    steps = -(-needed // CONTEXT_STEP_TOKENS)
    return max(MIN_CONTEXT_TOKENS, steps * CONTEXT_STEP_TOKENS)


def _label(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def _read_source(module: Path) -> str:
    try:
        return module.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise NeedsScanError(
            f"cannot read test module {module}: {exc}. A module that cannot be read cannot be inventoried. Fix: "
            "resolve the read error or the file's encoding (UTF-8)."
        ) from exc


def _filtered(reader: NeedsReader, label: str, text: str) -> list[str]:
    section = reader.content.section(label, text)
    return [section_body(section), *([section.note] if section.note else [])]


def _input_part(reader: NeedsReader, module_label: str, each: ModuleInput) -> list[str]:
    lines = ", ".join(str(line) for line in each.lines)
    heading = f"INPUT {each.form.value} {each.name} (module lines {lines})"
    if each.path is not None:
        label = _label(each.path, reader.workspace)
        return [f"{heading}: {label}", *_filtered(reader, label, each.text)]
    if each.unresolved is not None:
        return [f"{heading}: not read: {each.unresolved.value}"]
    return [heading, *_filtered(reader, f"{module_label} {each.name}", each.text)]


def module_request(reader: NeedsReader, found: ModuleInputs, only: Sequence[str] | None = None) -> _ModuleRequest:
    """The request for *found*: its source and every input's text, filtered, with its test functions, or with
    only those of *only* (a part of them: ``_halves``)."""
    source = _read_source(found.module)
    tests = tuple(only) if only is not None else module_tests(ast.parse(source, filename=str(found.module)))
    label = _label(found.module, reader.workspace)
    parts = [
        f"{MODULE_LABEL}: {label}",
        f"{TESTS_HEADING}:",
        *(f"{BULLET}{test}" for test in tests),
        *_filtered(reader, label, source),
    ]
    for each in found.inputs:
        parts.extend(_input_part(reader, label, each))
    system = f"{_SYSTEM_PROMPT}\n{KINDS_HEADING}: {', '.join(reader.kinds)}\n"
    return _ModuleRequest(found, tests, system, "\n".join(parts), needs_schema(reader.kinds, tests))


def _cache_path(reader: NeedsReader, request: _ModuleRequest) -> Path:
    return reader.cache_dir / f"{request.key}{_CACHE_SUFFIX}"


def _cached_answer(reader: NeedsReader, request: _ModuleRequest) -> dict[str, object]:
    """The kept answer to *request*; empty when none is cached or the cached one no longer passes its checks."""
    path = _cache_path(reader, request)
    if not path.is_file():
        return {}
    try:
        answer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("needs cache %s is unreadable (%s); the module is asked again", path, exc)
        return {}
    problems = answer_problems(answer, reader.kinds, request.tests) if isinstance(answer, dict) else ["not an object"]
    if problems:
        logger.warning("needs cache %s fails its checks (%s); the module is asked again", path, "; ".join(problems))
        return {}
    return cast("dict[str, object]", answer)


def _settled_answers(reader: NeedsReader, requests: Sequence[_ModuleRequest]) -> dict[int, _Answer]:
    """The answers known without asking, by request index: a module with no test needs nothing, and a
    cached answer is read back."""
    answers: dict[int, _Answer] = {}
    for index, request in enumerate(requests):
        if not request.tests:
            answers[index] = _Answer((), ())
            continue
        cached = _cached_answer(reader, request)
        if cached:
            answers[index] = _Answer(parse_needs(cached, request.tests), ())
    return answers


def _feedback(problems: Sequence[str], answer: Mapping[str, object]) -> str:
    return "\n".join([
        "",
        f"{FEEDBACK_HEADING}:",
        *(f"{BULLET}{problem}" for problem in problems),
        "YOUR LAST ANSWER:",
        json.dumps(answer, sort_keys=True),
        "Answer again, fixing every problem above.",
    ])


@dataclass(frozen=True)
class _Turn:
    """One message for one request: the request's index, the user prompt sent and the schema it constrains
    the answer with."""

    index: int
    user: str
    schema: dict[str, object] = field(hash=False)


@dataclass(frozen=True)
class _Attempt:
    """What one turn got back: the answer and its problems, or why no model answered."""

    answer: dict[str, object]
    problems: tuple[str, ...]
    error: str


def run_window(prompts: Sequence[tuple[str, str]]) -> int:
    """The one context window a run sends every request with: it holds the largest of *prompts* (system,
    user) with room for a resend, which carries the last answer back.

    Ollama reloads a model whenever a request's window differs from the one it holds, and a reload waits
    until the loaded runner is released, which a runner that has been serving can hold until its
    keep-alive ends: a request of another window then waits past the timeout and the pool drops a model
    that is serving. One window per run loads the model once.
    """
    reserve = " " * (ANSWER_TOKENS * CHARS_PER_TOKEN)
    return max((context_window(system, user + reserve) for system, user in prompts), default=MIN_CONTEXT_TOKENS)


def _attempt(
    reader: NeedsReader, request: _ModuleRequest, user: str, schema: dict[str, object], window: int,
) -> _Attempt:
    """One turn for *request* in the run's *window*, or a wider one when its prompt needs it (a prompt is
    never cut); an answer passing every check is cached as it arrives, so an interrupted run keeps what it
    was answered."""
    needed = max(window, context_window(request.system, user))
    try:
        answer = ask_json(reader.pool, request.system, user, schema, temperature=NEEDS_TEMPERATURE,
                          max_tokens=ANSWER_TOKENS, context_window=needed)
    except NoModelAnswer as error:
        return _Attempt({}, (), str(error))
    problems = tuple(answer_problems(answer, reader.kinds, request.tests))
    if not problems:
        _keep(reader, request, answer)
    return _Attempt(answer, problems, "")


def _keep(reader: NeedsReader, request: _ModuleRequest, answer: Mapping[str, object]) -> None:
    reader.cache_dir.mkdir(parents=True, exist_ok=True)
    _cache_path(reader, request).write_text(json.dumps(answer, sort_keys=True, indent=1), encoding="utf-8")


def _answer_of(tests: Sequence[TestNeeds]) -> dict[str, object]:
    """*tests* as an answer, the form ``parse_needs`` reads back to the same tests."""
    return {_TESTS: [
        {
            _NAME: each.name,
            _DECLARATIONS: [
                {_KIND: declaration.kind, _PATH: declaration.path, _FACTS: list(declaration.facts)}
                for declaration in each.declarations
            ],
            _LOCAL: each.local,
        }
        for each in tests
    ]}


def _send(
    reader: NeedsReader, requests: Sequence[_ModuleRequest], turns: Sequence[_Turn], window: int,
) -> dict[int, _Attempt]:
    """Send *turns* in parallel in *window*, by request index.

    Raises:
        LocalLlmUnavailable: no local model can serve.
    """
    arrived = itertools.count(1)

    def send(turn: _Turn) -> _Attempt:
        attempt = _attempt(reader, requests[turn.index], turn.user, turn.schema, window)
        state = attempt.error or ("problems" if attempt.problems else "answered")
        request = requests[turn.index]
        module = _label(request.found.module, reader.workspace)
        logger.info("needs %d/%d %s (%d tests): %s", next(arrived), len(turns), module, len(request.tests), state)
        return attempt

    attempts = parallel(turns, send)
    return {turn.index: attempt for turn, attempt in zip(turns, attempts, strict=True)}


def _kept(request: _ModuleRequest, attempt: _Attempt) -> _Answer:
    """*attempt* as *request*'s answer: refused with its problems, else parsed."""
    if attempt.error:
        return _Answer((), (attempt.error,))
    if attempt.problems:
        return _Answer((), attempt.problems)
    return _Answer(parse_needs(attempt.answer, request.tests), ())


def _halves(reader: NeedsReader, request: _ModuleRequest) -> tuple[_ModuleRequest, _ModuleRequest]:
    """*request* as two requests, for the first and the last half of its test functions, over the same
    source and inputs."""
    middle = len(request.tests) // 2
    return (
        module_request(reader, request.found, request.tests[:middle]),
        module_request(reader, request.found, request.tests[middle:]),
    )


def _joined(reader: NeedsReader, request: _ModuleRequest, parts: Sequence[_Answer]) -> _Answer:
    """The answer to *request* from the answers to its parts, kept as *request*'s own answer so a rerun asks
    nothing; the problems of the parts when one was refused."""
    problems = tuple(problem for part in parts for problem in part.problems)
    if problems:
        return _Answer((), problems)
    tests = tuple(each for part in parts for each in part.tests)
    _keep(reader, request, _answer_of(tests))
    return _Answer(tests, ())


def _ask(reader: NeedsReader, requests: Sequence[_ModuleRequest], window: int) -> list[_Answer]:
    """Ask for the answers to *requests* in *window*, resending once each answer with problems; kept answers
    are cached.

    An answer cut off at ``ANSWER_TOKENS`` is not valid JSON, and asking again gives the same answer, so a
    request for more than one test function is asked as two requests for half of them each, and so on until
    each part fits; the parts' answers are joined.

    Raises:
        LocalLlmUnavailable: no local model can serve.
    """
    indexes = range(len(requests))
    first = _send(
        reader, requests, [_Turn(index, requests[index].user, requests[index].schema) for index in indexes], window)
    resend = [
        _Turn(index, requests[index].user + _feedback(attempt.problems, attempt.answer),
              needs_schema(reader.kinds, requests[index].tests, named=True))
        for index, attempt in first.items() if attempt.problems
    ]
    last = {**first, **_send(reader, requests, resend, window)}
    answers = [_kept(requests[index], last[index]) for index in indexes]
    unusable = [index for index in indexes if last[index].error and len(requests[index].tests) > 1]
    parts = {index: _halves(reader, requests[index]) for index in unusable}
    if unusable:
        asked = iter(_ask(reader, [part for index in unusable for part in parts[index]], window))
        for index in unusable:
            answers[index] = _joined(reader, requests[index], [next(asked) for _ in parts[index]])
    return answers


def read_needs(reader: NeedsReader, found: Sequence[ModuleInputs]) -> NeedsReading:
    """What each module of *found* needs, read by the local model, or why its answer was refused.

    A module with no test function and a module with a cached answer send nothing; the pool is activated
    only when a module must be asked, and those are asked in parallel, all in one context window.

    Raises:
        LocalLlmUnavailable: no local model can serve; nothing more is asked.
        NeedsScanError: a module cannot be read.
    """
    requests = [module_request(reader, each) for each in found]
    answers = _settled_answers(reader, requests)
    asking = [index for index in range(len(requests)) if index not in answers]
    if asking:
        window = run_window([(requests[index].system, requests[index].user) for index in asking])
        reader.pool.activate(window)
        answers.update(zip(asking, _ask(reader, [requests[index] for index in asking], window), strict=True))
    needs = tuple(ModuleNeeds(r.found, answers[i].tests) for i, r in enumerate(requests) if not answers[i].problems)
    refused = tuple(
        RefusedModule(r.found.module, answers[i].problems) for i, r in enumerate(requests) if answers[i].problems
    )
    logger.info("needs reading modules=%d asked=%d refused=%d", len(requests), len(asking), len(refused))
    return NeedsReading(needs, refused)


__all__ = [
    "ANSWER_TOKENS",
    "BULLET",
    "CONTEXT_STEP_TOKENS",
    "FEEDBACK_HEADING",
    "KINDS_HEADING",
    "MIN_CONTEXT_TOKENS",
    "MODULE_LABEL",
    "NEEDS_CACHE_DIR",
    "NEEDS_TEMPERATURE",
    "TESTS_HEADING",
    "Declaration",
    "ModuleNeeds",
    "NeedsReader",
    "NeedsReading",
    "RefusedModule",
    "TestNeeds",
    "answer_problems",
    "context_window",
    "module_request",
    "module_tests",
    "needs_schema",
    "node_kinds",
    "parse_needs",
    "read_needs",
    "run_window",
]
